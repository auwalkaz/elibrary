from flask import Blueprint, render_template, request, session, flash, redirect, url_for, current_app, jsonify
from models import db, CirculationRecord, ItemCopy, Book, User, Fine
from datetime import datetime, timedelta
from functools import wraps

circulation_bp = Blueprint('circulation', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash("Admin access required.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@circulation_bp.route('/circulation')
@admin_required
def circulation():
    """Main circulation dashboard"""
    # Get active circulations
    active_circulations = CirculationRecord.query.filter_by(status='active').order_by(CirculationRecord.due_date).all()
    
    # Get overdue items
    overdue_items = CirculationRecord.query.filter(
        CirculationRecord.status == 'active',
        CirculationRecord.due_date < datetime.utcnow()
    ).all()
    
    # Get today's checkouts
    today = datetime.utcnow().date()
    today_checkouts = CirculationRecord.query.filter(
        CirculationRecord.checkout_date >= today
    ).count()
    
    # Get today's returns
    today_returns = CirculationRecord.query.filter(
        CirculationRecord.return_date >= today
    ).count()
    
    return render_template('circulation.html',
                         active_circulations=active_circulations,
                         overdue_items=overdue_items,
                         today_checkouts=today_checkouts,
                         today_returns=today_returns)

@circulation_bp.route('/circulation/checkout', methods=['GET', 'POST'])
@admin_required
def checkout():
    """Checkout a book"""
    if request.method == 'POST':
        barcode = request.form.get('barcode')
        user_id = request.form.get('user_id')
        due_date_days = int(request.form.get('due_date', 14))
        
        # Find the copy by barcode
        copy = ItemCopy.query.filter_by(barcode=barcode).first()
        if not copy:
            flash("Book copy not found.")
            return redirect(url_for('circulation.checkout'))
        
        # Check if copy is available
        if copy.status != 'available':
            flash(f"Copy is {copy.status}. Cannot checkout.")
            return redirect(url_for('circulation.checkout'))
        
        # Find user
        user = User.query.get(user_id)
        if not user:
            flash("User not found.")
            return redirect(url_for('circulation.checkout'))
        
        # Calculate due date
        due_date = datetime.utcnow() + timedelta(days=due_date_days)
        
        # Create circulation record
        circulation = CirculationRecord(
            copy_id=copy.id,
            user_id=user.id,
            due_date=due_date,
            checkout_staff=session['user_id'],
            status='active'
        )
        
        db.session.add(circulation)
        
        # Update copy status
        copy.status = 'checked_out'
        copy.current_circulation_id = circulation.id
        copy.last_checkout = datetime.utcnow()
        
        # Update book stats
        copy.book.available_copies -= 1
        copy.book.borrow_count += 1
        
        db.session.commit()
        
        flash(f"Successfully checked out to {user.full_name or user.username}")
        return redirect(url_for('circulation.circulation'))
    
    # GET request - show checkout form
    return render_template('checkout.html')

@circulation_bp.route('/circulation/checkin', methods=['GET', 'POST'])
@admin_required
def checkin():
    """Checkin a book"""
    if request.method == 'POST':
        barcode = request.form.get('barcode')
        
        # Find the copy by barcode
        copy = ItemCopy.query.filter_by(barcode=barcode).first()
        if not copy:
            flash("Book copy not found.")
            return redirect(url_for('circulation.checkin'))
        
        # Check if copy is checked out
        if copy.status != 'checked_out':
            flash(f"Copy is {copy.status}. Cannot checkin.")
            return redirect(url_for('circulation.checkin'))
        
        # Get active circulation
        circulation = CirculationRecord.query.get(copy.current_circulation_id)
        if not circulation:
            flash("No active circulation found for this copy.")
            return redirect(url_for('circulation.checkin'))
        
        # Calculate fine if overdue
        fine_amount = 0
        if circulation.due_date < datetime.utcnow():
            days_overdue = (datetime.utcnow() - circulation.due_date).days
            fine_amount = days_overdue * 50  # ₦50 per day
        
        condition = request.form.get('condition', 'good')
        notes = request.form.get('notes', '')
        
        # Update circulation
        circulation.return_date = datetime.utcnow()
        circulation.return_staff = session['user_id']
        circulation.status = 'returned'
        circulation.notes = notes
        
        # Create fine if applicable
        if fine_amount > 0:
            fine = Fine(
                circulation_id=circulation.id,
                user_id=circulation.user_id,
                amount=fine_amount,
                reason='overdue',
                description=f"Overdue by {days_overdue} days"
            )
            db.session.add(fine)
            circulation.fine_amount = fine_amount
        
        # Update copy status
        copy.status = 'available'
        copy.current_circulation_id = None
        copy.last_return = datetime.utcnow()
        copy.condition = condition
        
        # Update book stats
        copy.book.available_copies += 1
        
        db.session.commit()
        
        flash(f"Successfully checked in. Fine: ₦{fine_amount}" if fine_amount > 0 else "Successfully checked in.")
        return redirect(url_for('circulation.circulation'))
    
    # GET request - show checkin form
    return render_template('checkin.html')

@circulation_bp.route('/circulation/renew/<int:circulation_id>', methods=['POST'])
@admin_required
def renew(circulation_id):
    """Renew a circulation"""
    circulation = CirculationRecord.query.get_or_404(circulation_id)
    
    if circulation.can_renew():
        circulation.renew()
        db.session.commit()
        flash("Successfully renewed.")
    else:
        flash("Cannot renew this item.")
    
    return redirect(url_for('circulation.circulation'))

@circulation_bp.route('/api/circulation/search')
@admin_required
def search():
    """API endpoint to search for users/books by barcode"""
    query = request.args.get('q', '')
    type = request.args.get('type', '')  # 'user' or 'book'
    
    if type == 'user':
        users = User.query.filter(
            (User.username.ilike(f'%{query}%')) |
            (User.email.ilike(f'%{query}%')) |
            (User.full_name.ilike(f'%{query}%'))
        ).limit(10).all()
        
        return jsonify([{
            'id': u.id,
            'text': f"{u.full_name or u.username} ({u.email})",
            'username': u.username
        } for u in users])
    
    elif type == 'book':
        copies = ItemCopy.query.join(Book).filter(
            (ItemCopy.barcode.ilike(f'%{query}%')) |
            (Book.title.ilike(f'%{query}%')) |
            (Book.author.ilike(f'%{query}%'))
        ).limit(10).all()
        
        return jsonify([{
            'id': c.id,
            'barcode': c.barcode,
            'text': f"{c.book.title} by {c.book.author} - {c.barcode}",
            'status': c.status
        } for c in copies])
    
    return jsonify([])