from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from models import db, User, Book, BorrowRecord, BookReservation
from datetime import datetime, timedelta
from functools import wraps

borrow_bp = Blueprint('borrow', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@borrow_bp.route("/borrow/<int:book_id>", methods=["POST"])
@login_required
def borrow_book(book_id):
    book = Book.query.get_or_404(book_id)
    user = User.query.get(session['user_id'])
    
    if not user.has_library_card():
        flash("You need a valid library card to borrow books.")
        return redirect(url_for('auth.profile'))
    
    if not book.is_available():
        flash("This book is currently not available.")
        return redirect(url_for('books.read', book_id=book_id))
    
    existing_borrow = BorrowRecord.query.filter_by(
        user_id=user.id,
        book_id=book_id,
        status='borrowed'
    ).first()
    
    if existing_borrow:
        flash("You already have this book borrowed.")
        return redirect(url_for('books.read', book_id=book_id))
    
    borrow_record = BorrowRecord(
        user_id=user.id,
        book_id=book_id,
        due_date=datetime.now() + timedelta(days=14),
        status='borrowed'
    )
    
    book.available_copies -= 1
    user.total_books_borrowed += 1
    
    db.session.add(borrow_record)
    db.session.commit()
    
    flash(f"Book borrowed successfully! Due date: {borrow_record.due_date.strftime('%Y-%m-%d')}")
    return redirect(url_for('borrow.my_borrowings'))


@borrow_bp.route("/return/<int:borrow_id>", methods=["POST"])
@login_required
def return_book(borrow_id):
    borrow_record = BorrowRecord.query.get_or_404(borrow_id)
    
    if borrow_record.user_id != session['user_id'] and session.get('role') != 'admin':
        flash("Unauthorized access.")
        return redirect(url_for('books.home'))
    
    if borrow_record.status != 'borrowed':
        flash("This book has already been returned.")
        return redirect(url_for('borrow.my_borrowings'))
    
    borrow_record.return_date = datetime.now()
    borrow_record.status = 'returned'
    borrow_record.fine_amount = borrow_record.calculate_fine()
    
    book = Book.query.get(borrow_record.book_id)
    book.available_copies += 1
    
    db.session.commit()
    
    flash(f"Book returned successfully. Fine: ₦{borrow_record.fine_amount}")
    return redirect(url_for('borrow.my_borrowings'))


@borrow_bp.route("/my-borrowings")
@login_required
def my_borrowings():
    current_borrowings = BorrowRecord.query.filter_by(
        user_id=session['user_id'],
        status='borrowed'
    ).order_by(BorrowRecord.due_date).all()
    
    borrowing_history = BorrowRecord.query.filter_by(
        user_id=session['user_id']
    ).filter(BorrowRecord.status != 'borrowed').order_by(BorrowRecord.return_date.desc()).limit(10).all()
    
    return render_template("my_borrowings.html",
                         current_borrowings=current_borrowings,
                         borrowing_history=borrowing_history)


@borrow_bp.route("/reserve/<int:book_id>", methods=["POST"])
@login_required
def reserve_book(book_id):
    book = Book.query.get_or_404(book_id)
    user = User.query.get(session['user_id'])
    
    if not user.has_library_card():
        flash("You need a valid library card to reserve books.")
        return redirect(url_for('auth.profile'))
    
    existing_reservation = BookReservation.query.filter_by(
        user_id=user.id,
        book_id=book_id,
        status='pending'
    ).first()
    
    if existing_reservation:
        flash("You already have a pending reservation for this book.")
        return redirect(url_for('books.read', book_id=book_id))
    
    reservation = BookReservation(
        user_id=user.id,
        book_id=book_id,
        status='pending'
    )
    
    db.session.add(reservation)
    db.session.commit()
    
    flash("Book reserved successfully! You'll be notified when it becomes available.")
    return redirect(url_for('books.read', book_id=book_id))