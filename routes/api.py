from flask import Blueprint, jsonify, request
from models import db, Book, User, BorrowRecord

api_bp = Blueprint('api', __name__)

@api_bp.route("/search-suggestions")
def search_suggestions():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    books = Book.query.filter(
        (Book.title.ilike(f"%{query}%")) | 
        (Book.author.ilike(f"%{query}%"))
    ).limit(5).all()
    
    suggestions = [{"id": b.id, "title": b.title, "author": b.author} for b in books]
    return jsonify(suggestions)


@api_bp.route("/book/<int:book_id>/status")
def book_status(book_id):
    book = Book.query.get_or_404(book_id)
    return jsonify({
        'available': book.is_available(),
        'available_copies': book.available_copies,
        'total_copies': book.total_copies
    })


@api_bp.route("/user/<int:user_id>/borrowings")
def user_borrowings(user_id):
    user = User.query.get_or_404(user_id)
    borrowings = BorrowRecord.query.filter_by(user_id=user_id, status='borrowed').all()
    
    result = [{
        'id': b.id,
        'book_title': b.book.title,
        'borrow_date': b.borrow_date.isoformat(),
        'due_date': b.due_date.isoformat(),
        'fine': b.calculate_fine()
    } for b in borrowings]
    
    return jsonify(result)