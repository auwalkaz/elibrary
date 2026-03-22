from flask import Blueprint, render_template, request, session, flash, redirect, url_for, current_app, send_from_directory, abort, jsonify, make_response
from models import db, Book, Wishlist, Review, ReadingHistory, DownloadLog, User, Bookmark, ReadingProgress, ReadingSession, Annotation, RecentActivity, SpecialRequest, AcquisitionRequest, CatalogingQueue, ItemCopy, CirculationRecord, Reservation, Fine
from datetime import datetime, timedelta
import math
import os
import json
from werkzeug.utils import secure_filename
from functools import wraps
import hashlib

# Create blueprint FIRST - this is the most important fix
books_bp = Blueprint('books', __name__)

# ===================== DECORATORS =====================

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return {"success": False, "message": "Please login first"}, 401
            flash("Please login to access this page.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def check_download_limit(f):
    """Decorator to check download limits"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to download documents.")
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        
        # Admin has unlimited downloads
        if user.role == 'admin':
            return f(*args, **kwargs)
        
        # Get download limits from config
        max_per_day = current_app.config.get('MAX_DOWNLOADS_PER_DAY', 5)
        max_per_week = current_app.config.get('MAX_DOWNLOADS_PER_WEEK', 20)
        max_per_month = current_app.config.get('MAX_DOWNLOADS_PER_MONTH', 50)
        
        # Calculate time periods
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Count downloads in each period
        downloads_today = DownloadLog.query.filter(
            DownloadLog.user_id == session['user_id'],
            DownloadLog.timestamp >= day_ago
        ).count()
        
        downloads_this_week = DownloadLog.query.filter(
            DownloadLog.user_id == session['user_id'],
            DownloadLog.timestamp >= week_ago
        ).count()
        
        downloads_this_month = DownloadLog.query.filter(
            DownloadLog.user_id == session['user_id'],
            DownloadLog.timestamp >= month_ago
        ).count()
        
        # Check limits
        if downloads_today >= max_per_day:
            flash(f"⚠️ Daily download limit reached ({max_per_day} per day). Please try again tomorrow.")
            return redirect(url_for('books.home'))
        
        if downloads_this_week >= max_per_week:
            flash(f"⚠️ Weekly download limit reached ({max_per_week} per week).")
            return redirect(url_for('books.home'))
        
        if downloads_this_month >= max_per_month:
            flash(f"⚠️ Monthly download limit reached ({max_per_month} per month).")
            return redirect(url_for('books.home'))
        
        return f(*args, **kwargs)
    return decorated_function


def check_special_access(book_id, user_id, request_type='read'):
    """Check if user has special access to a restricted book"""
    book = Book.query.get(book_id)
    user = User.query.get(user_id)
    
    if not book.requires_special_request:
        return True, None
    
    # Admin always has access
    if user.role == 'admin':
        return True, None
    
    # Check if user has approved request
    approved = SpecialRequest.query.filter_by(
        user_id=user_id,
        book_id=book_id,
        request_type=request_type,
        status='approved'
    ).first()
    
    if approved:
        return True, None
    
    # Check if there's a pending request
    pending = SpecialRequest.query.filter_by(
        user_id=user_id,
        book_id=book_id,
        request_type=request_type,
        status='pending'
    ).first()
    
    if pending:
        return False, 'pending'
    
    return False, 'none'


def check_reading_access(f):
    """Decorator to check if user can read a book"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        book_id = kwargs.get('book_id')
        if not book_id:
            return f(*args, **kwargs)
        
        book = Book.query.get_or_404(book_id)
        
        # Check if book requires special request
        if book.requires_special_request:
            if 'user_id' not in session:
                if request.is_json:
                    return {"success": False, "message": "Please login to request access"}, 401
                flash("This book requires special approval. Please login to request access.")
                return redirect(url_for('auth.login', next=request.url))
            
            has_access, status = check_special_access(book_id, session['user_id'], 'read')
            
            if has_access:
                return f(*args, **kwargs)
            elif status == 'pending':
                flash("Your request for this book is still pending approval.")
                return redirect(url_for('books.book_details', book_id=book_id))
            else:
                return redirect(url_for('books.request_special_access', book_id=book_id))
        
        # Check if book is public
        if book.is_public and current_app.config.get('ALLOW_PUBLIC_READING', False):
            return f(*args, **kwargs)
        
        # Check if user is logged in
        if 'user_id' not in session:
            if request.is_json:
                return {"success": False, "message": "Please login to read"}, 401
            flash("Please login to read this book.")
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        
        # Admin has access
        if user.role == 'admin':
            return f(*args, **kwargs)
        
        # Check if library card is required
        if book.requires_library_card and current_app.config.get('REQUIRE_LIBRARY_CARD_FOR_READING', True):
            if not user.has_library_card():
                flash("⚠️ A valid library card is required to read this book.")
                return redirect(url_for('books.book_details', book_id=book_id))
        
        return f(*args, **kwargs)
    return decorated_function

# ===================== HELPER FUNCTIONS =====================

def get_unique_categories():
    """Get unique categories from all books"""
    books = Book.query.all()
    categories = []
    for book in books:
        if book.category and book.category not in categories:
            categories.append(book.category)
    return sorted(categories)


def filter_books(query=None, category=None, sort=None, page=1, per_page=12):
    """Filter and paginate books using database"""
    books_query = Book.query
    
    if query:
        search = f"%{query}%"
        books_query = books_query.filter(
            (Book.title.ilike(search)) | 
            (Book.author.ilike(search)) | 
            (Book.category.ilike(search))
        )
    
    if category:
        books_query = books_query.filter_by(category=category)
    
    # Apply sorting - FIXED: Use correct attribute names
    if sort == 'newest':
        books_query = books_query.order_by(Book.created_at.desc())
    elif sort == 'oldest':
        books_query = books_query.order_by(Book.created_at.asc())
    elif sort == 'title':
        books_query = books_query.order_by(Book.title.asc())
    elif sort == 'author':
        books_query = books_query.order_by(Book.author.asc())
    elif sort == 'rating':
        # FIXED: Changed from Book.rating to Book.average_rating
        books_query = books_query.order_by(Book.average_rating.desc())
    elif sort == 'popular':
        # FIXED: Changed from Book.downloads to Book.download_count
        books_query = books_query.order_by(Book.download_count.desc())
    else:
        books_query = books_query.order_by(Book.created_at.desc())
    
    # Get total count before pagination
    total_results = books_query.count()
    
    # Apply pagination
    books = books_query.offset((page - 1) * per_page).limit(per_page).all()
    
    return books, total_results


def solr_search(query, filters=None, page=1, per_page=12, sort=None):
    """Search using Solr if available, fallback to database"""
    try:
        from services.solr_client import solr_client
        
        # Check if Solr is available
        if hasattr(current_app.extensions, 'solr') and current_app.extensions.get('solr'):
            results = solr_client.search(query, filters, page, per_page, sort)
            
            if results['success'] and results['book_ids']:
                # Fetch books from database maintaining Solr order
                books = Book.query.filter(Book.id.in_(results['book_ids'])).all()
                book_dict = {book.id: book for book in books}
                ordered_books = [book_dict[bid] for bid in results['book_ids'] if bid in book_dict]
                
                return {
                    'books': ordered_books,
                    'total': results['total'],
                    'highlighting': results.get('highlighting', {}),
                    'using_solr': True
                }
    except Exception as e:
        current_app.logger.warning(f"Solr search failed, falling back to database: {e}")
    
    # Fallback to database search
    books, total = filter_books(query, filters.get('category') if filters else None, sort, page, per_page)
    return {
        'books': books,
        'total': total,
        'highlighting': {},
        'using_solr': False
    }


def get_user_download_stats(user_id):
    """Get download statistics for a user"""
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    stats = {
        'today': DownloadLog.query.filter(
            DownloadLog.user_id == user_id,
            DownloadLog.timestamp >= day_ago
        ).count(),
        'this_week': DownloadLog.query.filter(
            DownloadLog.user_id == user_id,
            DownloadLog.timestamp >= week_ago
        ).count(),
        'this_month': DownloadLog.query.filter(
            DownloadLog.user_id == user_id,
            DownloadLog.timestamp >= month_ago
        ).count(),
        'total': DownloadLog.query.filter_by(user_id=user_id).count()
    }
    
    return stats


def log_activity(user_id, activity_type, book_id=None, description=None, metadata=None):
    """Log user activity for dashboard"""
    try:
        activity = RecentActivity(
            user_id=user_id,
            activity_type=activity_type,
            book_id=book_id,
            description=description,
            data=metadata or {}
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to log activity: {e}")
        db.session.rollback()


def get_reading_progress(user_id, book_id):
    """Get reading progress for a user and book"""
    progress = ReadingProgress.query.filter_by(
        user_id=user_id,
        book_id=book_id
    ).first()
    
    if progress:
        return {
            'current_page': progress.current_page,
            'percentage': progress.progress_percentage,
            'last_accessed': progress.last_accessed.isoformat() if progress.last_accessed else None,
            'reading_time': progress.reading_time_seconds
        }
    return None


def generate_etag(content):
    """Generate ETag for caching"""
    return hashlib.md5(content.encode()).hexdigest()

# ===================== ROUTES =====================

# Test route to verify books are working
@books_bp.route('/test-books')
def test_books():
    """Test endpoint to verify books are working"""
    try:
        featured_books = Book.query.filter_by(is_featured=True).order_by(Book.created_at.desc()).limit(6).all()
        books_list = [{"id": b.id, "title": b.title, "author": b.author} for b in featured_books]
        return {"status": "success", "books": books_list, "count": len(featured_books)}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@books_bp.route("/")
def home():
    """Home page and search results"""
    # Get filter parameters
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    sort = request.args.get('sort', 'newest')
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('BOOKS_PER_PAGE', 12)
    
    # If search query exists, show search results
    if query or category:
        # Try Solr search first
        filters = {}
        if category:
            filters['category'] = category
        
        search_results = solr_search(query, filters, page, per_page, sort)
        books = search_results['books']
        total_results = search_results['total']
        highlighting = search_results['highlighting']
        using_solr = search_results['using_solr']
        
        categories = get_unique_categories()
        
        # Calculate pagination
        total_pages = math.ceil(total_results / per_page) if total_results > 0 else 1
        
        # Get wishlist for logged in user
        wishlist_ids = []
        if session.get('user_id'):
            wishlist = Wishlist.query.filter_by(user_id=session['user_id']).all()
            wishlist_ids = [item.book_id for item in wishlist]
        
        return render_template("search_results.html", 
                             books=books, 
                             categories=categories,
                             total_results=total_results,
                             search_query=query,
                             selected_category=category,
                             selected_sort=sort,
                             wishlist_ids=wishlist_ids,
                             page=page,
                             total_pages=total_pages,
                             per_page=per_page,
                             highlighting=highlighting,
                             using_solr=using_solr)
    
    # Home page with curated sections
    featured_books = Book.query.filter_by(is_featured=True).order_by(Book.created_at.desc()).limit(6).all()
    new_arrivals = Book.query.filter_by(is_new_arrival=True).order_by(Book.created_at.desc()).limit(8).all()
    
    # FIXED: Changed from Book.downloads to Book.download_count
    bestsellers = Book.query.filter_by(is_bestseller=True).order_by(Book.download_count.desc()).limit(6).all()
    
    # FIXED: Changed from Book.rating to Book.average_rating
    recommended = Book.query.filter_by(is_recommended=True).order_by(Book.average_rating.desc()).limit(4).all()
    
    # Get restricted books count for badge (optional)
    restricted_count = Book.query.filter_by(requires_special_request=True).count()
    
    # Get wishlist for logged in user
    wishlist_ids = []
    if session.get('user_id'):
        wishlist = Wishlist.query.filter_by(user_id=session['user_id']).all()
        wishlist_ids = [item.book_id for item in wishlist]
    
    # Get recent activity for logged in user
    recent_activity = []
    if session.get('user_id'):
        recent_activity = RecentActivity.query.filter_by(
            user_id=session['user_id']
        ).order_by(RecentActivity.timestamp.desc()).limit(5).all()
    
    return render_template("index.html", 
                         featured_books=featured_books,
                         new_arrivals=new_arrivals,
                         bestsellers=bestsellers,
                         recommended=recommended,
                         wishlist_ids=wishlist_ids,
                         total_books=Book.query.count(),
                         categories=get_unique_categories()[:8],
                         recent_activity=recent_activity,
                         restricted_count=restricted_count)


@books_bp.route("/book/<int:book_id>")
def book_details(book_id):
    """Book details page"""
    book = Book.query.get_or_404(book_id)
    
    # Increment view count
    book.view_count += 1
    db.session.commit()
    
    # Get reviews for this book
    reviews = Review.query.filter_by(book_id=book_id).order_by(Review.created_at.desc()).all()
    
    # Check if book is in user's wishlist
    in_wishlist = False
    special_request_status = None
    if session.get('user_id'):
        in_wishlist = Wishlist.query.filter_by(
            user_id=session['user_id'],
            book_id=book_id
        ).first() is not None
        
        # Check special request status if book requires approval
        if book.requires_special_request:
            request_record = SpecialRequest.query.filter_by(
                user_id=session['user_id'],
                book_id=book_id
            ).first()
            if request_record:
                special_request_status = request_record.status
    
    # Get reading progress if user is logged in
    reading_progress = None
    if session.get('user_id'):
        progress = get_reading_progress(session['user_id'], book_id)
        if progress:
            reading_progress = progress
    
    # Get similar books (same category)
    similar_books = Book.query.filter(
        Book.category == book.category,
        Book.id != book_id
    ).order_by(Book.download_count.desc()).limit(4).all()
    
    # Get download stats for display
    download_stats = None
    if session.get('user_id'):
        user = User.query.get(session['user_id'])
        if user.role != 'admin':
            stats = get_user_download_stats(session['user_id'])
            download_stats = {
                'today': stats['today'],
                'max_per_day': current_app.config.get('MAX_DOWNLOADS_PER_DAY', 5),
                'remaining_today': max(0, current_app.config.get('MAX_DOWNLOADS_PER_DAY', 5) - stats['today'])
            }
    
    # Get available copies for physical books
    available_copies = 0
    if book.has_physical:
        available_copies = ItemCopy.query.filter_by(
            book_id=book.id,
            status='available'
        ).count()
    
    # FIXED: Removed 'admin/' from the template path
    return render_template("book_details.html", 
                         book=book, 
                         reviews=reviews,
                         in_wishlist=in_wishlist,
                         special_request_status=special_request_status,
                         similar_books=similar_books,
                         download_stats=download_stats,
                         reading_progress=reading_progress,
                         available_copies=available_copies)


@books_bp.route("/debug-path/<int:book_id>")
def debug_path(book_id):
    """Debug the actual file path and URL"""
    import os
    from flask import current_app
    
    book = Book.query.get_or_404(book_id)
    
    if not book.cover_image:
        return {"error": "No cover image"}
    
    # Get the upload folder
    upload_folder = current_app.config['UPLOAD_FOLDER']
    
    # Try different path combinations
    paths = {
        'covers_only': os.path.join(upload_folder, 'covers', book.cover_image),
        'uploads_covers': os.path.join(upload_folder, 'uploads', 'covers', book.cover_image),
        'direct': os.path.join(upload_folder, book.cover_image),
    }
    
    results = {
        'book_id': book.id,
        'cover_image': book.cover_image,
        'upload_folder': upload_folder,
        'upload_folder_exists': os.path.exists(upload_folder),
        'paths': {}
    }
    
    for name, path in paths.items():
        results['paths'][name] = {
            'path': path,
            'exists': os.path.exists(path),
            'size': os.path.getsize(path) if os.path.exists(path) else None
        }
    
    # Show the URLs that would be generated
    results['urls'] = {
        'covers_only': url_for('admin.uploaded_file', filename='covers/' + book.cover_image, _external=True),
        'uploads_covers': url_for('admin.uploaded_file', filename='uploads/covers/' + book.cover_image, _external=True),
        'direct': url_for('admin.uploaded_file', filename=book.cover_image, _external=True),
    }
    
    # List contents of upload folder
    if os.path.exists(upload_folder):
        results['upload_folder_contents'] = os.listdir(upload_folder)
        
        covers_path = os.path.join(upload_folder, 'covers')
        if os.path.exists(covers_path):
            results['covers_folder_contents'] = os.listdir(covers_path)
        
        uploads_covers_path = os.path.join(upload_folder, 'uploads', 'covers')
        if os.path.exists(uploads_covers_path):
            results['uploads_covers_contents'] = os.listdir(uploads_covers_path)
    
    return results

@books_bp.route("/read/<int:book_id>")
@check_reading_access
def read(book_id):
    """Read a book online with PDF.js viewer"""
    book = Book.query.get_or_404(book_id)
    
    # Check if book has digital copy
    if not book.has_digital_copy():
        flash("This book doesn't have a digital version available for online reading.")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    # Update reading history
    if session.get('user_id'):
        # Update or create reading history
        history = ReadingHistory.query.filter_by(
            user_id=session['user_id'], 
            book_id=book_id
        ).first()
        
        if history:
            history.last_read = datetime.utcnow()
            history.read_count = (history.read_count or 0) + 1
        else:
            history = ReadingHistory(
                user_id=session['user_id'], 
                book_id=book_id,
                read_count=1
            )
            db.session.add(history)
        
        # Update or create reading progress
        progress = ReadingProgress.query.filter_by(
            user_id=session['user_id'],
            book_id=book_id
        ).first()
        
        if not progress:
            progress = ReadingProgress(
                user_id=session['user_id'],
                book_id=book_id
            )
            db.session.add(progress)
        
        # Start a reading session
        session_data = ReadingSession(
            user_id=session['user_id'],
            book_id=book_id,
            start_page=progress.current_page if progress else 0,
            ip_address=request.remote_addr
        )
        db.session.add(session_data)
        db.session.commit()
        
        # Store session ID in flask session for later
        session['current_reading_session'] = session_data.id
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='read',
            book_id=book_id,
            description=f"Started reading {book.title}"
        )
    
    # Increment view count
    book.view_count += 1  # FIXED: Changed from views to view_count
    db.session.commit()
    
    # Get bookmarks for this user
    bookmarks = []
    if session.get('user_id'):
        bookmarks = Bookmark.query.filter_by(
            user_id=session['user_id'],
            book_id=book_id
        ).order_by(Bookmark.page_number).all()
    
    # Get annotations for this user
    annotations = []
    if session.get('user_id'):
        annotations = Annotation.query.filter_by(
            user_id=session['user_id'],
            book_id=book_id
        ).order_by(Annotation.page_number).all()
    
    # Get reading progress
    reading_progress = None
    if session.get('user_id'):
        progress = ReadingProgress.query.filter_by(
            user_id=session['user_id'],
            book_id=book_id
        ).first()
        if progress:
            reading_progress = {
                'current_page': progress.current_page,
                'percentage': progress.progress_percentage
            }
    
    # Get user preferences for viewer
    viewer_config = {
        'zoom_level': current_app.config.get('DEFAULT_ZOOM_LEVEL', 100),
        'allow_zoom': current_app.config.get('ALLOW_ZOOM_CONTROLS', True),
        'allow_fullscreen': current_app.config.get('ALLOW_FULLSCREEN', True),
        'allow_text_selection': current_app.config.get('ALLOW_TEXT_SELECTION', True),
        'allow_printing': current_app.config.get('ALLOW_PRINTING', False),
        'allow_download': current_app.config.get('ALLOW_DOWNLOAD', False),
        'auto_save_interval': current_app.config.get('AUTO_SAVE_INTERVAL', 30) * 1000,  # Convert to ms
    }
    
    return render_template("read.html",  
                         book=book,
                         bookmarks=bookmarks,
                         annotations=annotations,
                         reading_progress=reading_progress,
                         viewer_config=viewer_config,
                         pdf_url=url_for('books.serve_pdf', filename=book.filename))


@books_bp.route("/pdf/<filename>")
def serve_pdf(filename):
    """Serve PDF for inline viewing with caching and range support"""
    # Security: prevent directory traversal
    if '..' in filename or filename.startswith('/') or not filename:
        abort(404)
    
    # Secure the filename
    filename = secure_filename(filename)
    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    
    if not os.path.exists(file_path):
        abort(404)
    
    # Get file stats for caching
    stat = os.stat(file_path)
    etag = generate_etag(f"{filename}-{stat.st_mtime}-{stat.st_size}")
    
    # Check If-None-Match header
    if request.headers.get('If-None-Match') == etag:
        return '', 304
    
    # Create response with caching headers
    response = make_response(send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=False,
        mimetype='application/pdf'
    ))
    
    # Add caching headers
    response.headers['Cache-Control'] = 'public, max-age=3600'
    response.headers['ETag'] = etag
    response.headers['Accept-Ranges'] = 'bytes'
    
    return response


@books_bp.route("/download/<filename>")
@login_required
@check_download_limit
def download(filename):
    """Download a book PDF with restrictions"""
    # Security: prevent directory traversal
    if '..' in filename or filename.startswith('/') or not filename:
        abort(404)
    
    # Secure the filename
    filename = secure_filename(filename)
    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    
    if not os.path.exists(file_path):
        abort(404)
    
    # Find the book
    book = Book.query.filter_by(filename=filename).first()
    if not book:
        abort(404)
    
    # Check if book requires special request for download
    if book.requires_special_request and session.get('user_id'):
        has_access, status = check_special_access(book.id, session['user_id'], 'download')
        if not has_access:
            if status == 'pending':
                flash("Your request to download this book is still pending.")
            else:
                flash("This book requires special approval to download.")
            return redirect(url_for('books.book_details', book_id=book.id))
    
    user = User.query.get(session['user_id'])
    
    # Log the download (unless admin)
    if user.role != 'admin':
        log_entry = DownloadLog(
            user_id=session['user_id'],
            book_id=book.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )
        db.session.add(log_entry)
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='download',
            book_id=book.id,
            description=f"Downloaded {book.title}"
        )
    
    # Increment download count
    book.download_count += 1  # FIXED: Changed from downloads to download_count
    
    # Update user's total downloads
    user.total_downloads = (user.total_downloads or 0) + 1
    
    db.session.commit()
    
    # Get remaining downloads for response headers
    stats = get_user_download_stats(session['user_id'])
    max_per_day = current_app.config.get('MAX_DOWNLOADS_PER_DAY', 5)
    remaining = max(0, max_per_day - stats['today'])
    
    # Serve the file as attachment
    response = send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=True,
        download_name=f"{book.title}.pdf"
    )
    
    # Add headers with download limits info
    response.headers['X-Remaining-Downloads-Today'] = str(remaining)
    response.headers['X-Download-Limit-Per-Day'] = str(max_per_day)
    
    return response


# ===================== SPECIAL ACCESS REQUESTS =====================

@books_bp.route("/request-access/<int:book_id>", methods=["GET", "POST"])
@login_required
def request_special_access(book_id):
    """Request special access to a restricted book"""
    book = Book.query.get_or_404(book_id)
    
    if not book.requires_special_request:
        flash("This book does not require special access.")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    request_type = request.args.get('type', 'read')
    
    if request.method == "POST":
        reason = request.form.get('reason')
        additional_notes = request.form.get('notes', '')
        
        if not reason:
            flash("Please provide a reason for your request.")
            return redirect(request.url)
        
        # Check if request already exists
        existing = SpecialRequest.query.filter_by(
            user_id=session['user_id'],
            book_id=book_id,
            request_type=request_type,
            status='pending'
        ).first()
        
        if existing:
            flash("You already have a pending request for this material.")
            return redirect(url_for('books.book_details', book_id=book_id))
        
        # Create request
        special_request = SpecialRequest(
            user_id=session['user_id'],
            book_id=book_id,
            request_type=request_type,
            reason=reason,
            additional_notes=additional_notes
        )
        
        db.session.add(special_request)
        db.session.commit()
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='special_request',
            book_id=book_id,
            description=f"Requested {request_type} access to restricted material"
        )
        
        flash("Your request has been submitted and is pending approval.")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    return render_template("request_access.html", book=book, request_type=request_type)


@books_bp.route("/my-requests")
@login_required
def my_requests():
    """View user's special access requests"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    requests = SpecialRequest.query.filter_by(user_id=session['user_id'])\
        .order_by(SpecialRequest.created_at.desc())\
        .offset((page - 1) * per_page).limit(per_page).all()
    
    total = SpecialRequest.query.filter_by(user_id=session['user_id']).count()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("my_requests.html",
                         requests=requests,
                         page=page,
                         total_pages=total_pages,
                         total=total)


# ===================== READING PROGRESS API =====================

@books_bp.route("/api/reading/progress", methods=["POST"])
@login_required
def update_reading_progress():
    """Update reading progress for a book"""
    data = request.get_json()
    
    book_id = data.get('book_id')
    current_page = data.get('current_page', 0)
    total_pages = data.get('total_pages')
    reading_time = data.get('reading_time', 0)
    
    if not book_id:
        return jsonify({"success": False, "message": "Book ID required"}), 400
    
    book = Book.query.get_or_404(book_id)
    
    # Update or create reading progress
    progress = ReadingProgress.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id
    ).first()
    
    if not progress:
        progress = ReadingProgress(
            user_id=session['user_id'],
            book_id=book_id
        )
        db.session.add(progress)
    
    progress.current_page = current_page
    if total_pages:
        progress.progress_percentage = (current_page / total_pages) * 100
        progress.progress_percentage = round(progress.progress_percentage, 2)
    
    if reading_time:
        progress.reading_time_seconds += reading_time
    
    progress.last_accessed = datetime.utcnow()
    
    # Update reading history
    history = ReadingHistory.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id
    ).first()
    
    if history:
        history.last_read = datetime.utcnow()
        history.last_page = current_page
        if total_pages:
            history.total_pages = total_pages
            history.progress = int((current_page / total_pages) * 100)
    
    db.session.commit()
    
    # Update reading session if active
    if session.get('current_reading_session'):
        reading_session = ReadingSession.query.get(session['current_reading_session'])
        if reading_session and reading_session.book_id == book_id:
            reading_session.end_page = current_page
            reading_session.pages_read = current_page - reading_session.start_page
            db.session.commit()
    
    return jsonify({
        "success": True,
        "progress": {
            "current_page": progress.current_page,
            "percentage": progress.progress_percentage,
            "reading_time": progress.reading_time_seconds
        }
    })


@books_bp.route("/api/reading/progress/<int:book_id>")
@login_required
def get_reading_progress_api(book_id):
    """Get reading progress for a book"""
    progress = get_reading_progress(session['user_id'], book_id)
    
    if progress:
        return jsonify({"success": True, "progress": progress})
    else:
        return jsonify({"success": False, "message": "No progress found"})


@books_bp.route("/api/reading/session/end", methods=["POST"])
@login_required
def end_reading_session():
    """End the current reading session"""
    if not session.get('current_reading_session'):
        return jsonify({"success": False, "message": "No active session"})
    
    reading_session = ReadingSession.query.get(session['current_reading_session'])
    if reading_session:
        reading_session.end_time = datetime.utcnow()
        db.session.commit()
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='reading_session',
            book_id=reading_session.book_id,
            description=f"Read for {reading_session.pages_read} pages",
            metadata={
                'pages_read': reading_session.pages_read,
                'duration': (reading_session.end_time - reading_session.start_time).total_seconds()
            }
        )
        
        del session['current_reading_session']
        
        return jsonify({"success": True, "message": "Session ended"})
    
    return jsonify({"success": False, "message": "Session not found"})


# ===================== BOOKMARKS API =====================

@books_bp.route("/api/bookmarks", methods=["POST"])
@login_required
def add_bookmark():
    """Add a bookmark"""
    data = request.get_json()
    
    book_id = data.get('book_id')
    page_number = data.get('page_number')
    note = data.get('note', '')
    
    if not book_id or not page_number:
        return jsonify({"success": False, "message": "Book ID and page number required"}), 400
    
    # Check if bookmark already exists
    existing = Bookmark.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id,
        page_number=page_number
    ).first()
    
    if existing:
        return jsonify({"success": False, "message": "Bookmark already exists on this page"}), 400
    
    # Check max bookmarks limit
    max_bookmarks = current_app.config.get('MAX_BOOKMARKS_PER_BOOK', 50)
    bookmark_count = Bookmark.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id
    ).count()
    
    if bookmark_count >= max_bookmarks:
        return jsonify({"success": False, "message": f"Maximum bookmarks reached ({max_bookmarks})"}), 400
    
    bookmark = Bookmark(
        user_id=session['user_id'],
        book_id=book_id,
        page_number=page_number,
        note=note
    )
    db.session.add(bookmark)
    db.session.commit()
    
    # Log activity
    log_activity(
        user_id=session['user_id'],
        activity_type='bookmark',
        book_id=book_id,
        description=f"Bookmarked page {page_number}"
    )
    
    return jsonify({
        "success": True,
        "message": "Bookmark added",
        "bookmark": {
            "id": bookmark.id,
            "page_number": bookmark.page_number,
            "note": bookmark.note,
            "created_at": bookmark.created_at.isoformat()
        }
    })


@books_bp.route("/api/bookmarks/<int:bookmark_id>", methods=["DELETE"])
@login_required
def remove_bookmark(bookmark_id):
    """Remove a bookmark"""
    bookmark = Bookmark.query.get_or_404(bookmark_id)
    
    # Check ownership
    if bookmark.user_id != session['user_id']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    db.session.delete(bookmark)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Bookmark removed"})


@books_bp.route("/api/bookmarks/<int:book_id>")
@login_required
def get_bookmarks(book_id):
    """Get all bookmarks for a book"""
    bookmarks = Bookmark.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id
    ).order_by(Bookmark.page_number).all()
    
    return jsonify({
        "success": True,
        "bookmarks": [{
            "id": b.id,
            "page_number": b.page_number,
            "note": b.note,
            "created_at": b.created_at.isoformat()
        } for b in bookmarks]
    })


# ===================== ANNOTATIONS API =====================

@books_bp.route("/api/annotations", methods=["POST"])
@login_required
def add_annotation():
    """Add an annotation/highlight"""
    data = request.get_json()
    
    book_id = data.get('book_id')
    page_number = data.get('page_number')
    highlight_text = data.get('highlight_text')
    note = data.get('note', '')
    color = data.get('color', 'yellow')
    position_data = data.get('position_data')
    
    if not book_id or not page_number:
        return jsonify({"success": False, "message": "Book ID and page number required"}), 400
    
    # Check max annotations limit
    max_annotations = current_app.config.get('MAX_ANNOTATIONS_PER_BOOK', 100)
    annotation_count = Annotation.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id
    ).count()
    
    if annotation_count >= max_annotations:
        return jsonify({"success": False, "message": f"Maximum annotations reached ({max_annotations})"}), 400
    
    annotation = Annotation(
        user_id=session['user_id'],
        book_id=book_id,
        page_number=page_number,
        highlight_text=highlight_text,
        note=note,
        color=color,
        position_data=position_data
    )
    db.session.add(annotation)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "Annotation added",
        "annotation": {
            "id": annotation.id,
            "page_number": annotation.page_number,
            "highlight_text": annotation.highlight_text,
            "note": annotation.note,
            "color": annotation.color,
            "position_data": annotation.position_data,
            "created_at": annotation.created_at.isoformat()
        }
    })


@books_bp.route("/api/annotations/<int:annotation_id>", methods=["DELETE"])
@login_required
def remove_annotation(annotation_id):
    """Remove an annotation"""
    annotation = Annotation.query.get_or_404(annotation_id)
    
    # Check ownership
    if annotation.user_id != session['user_id']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    db.session.delete(annotation)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Annotation removed"})


@books_bp.route("/api/annotations/<int:book_id>")
@login_required
def get_annotations(book_id):
    """Get all annotations for a book"""
    annotations = Annotation.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id
    ).order_by(Annotation.page_number).all()
    
    return jsonify({
        "success": True,
        "annotations": [{
            "id": a.id,
            "page_number": a.page_number,
            "highlight_text": a.highlight_text,
            "note": a.note,
            "color": a.color,
            "position_data": a.position_data,
            "created_at": a.created_at.isoformat()
        } for a in annotations]
    })


# ===================== DOWNLOAD STATUS API =====================

@books_bp.route("/api/download-status")
@login_required
def download_status():
    """API endpoint to check download status"""
    user = User.query.get(session['user_id'])
    
    if user.role == 'admin':
        return jsonify({
            'role': 'admin',
            'unlimited': True
        })
    
    stats = get_user_download_stats(session['user_id'])
    limits = {
        'per_day': current_app.config.get('MAX_DOWNLOADS_PER_DAY', 5),
        'per_week': current_app.config.get('MAX_DOWNLOADS_PER_WEEK', 20),
        'per_month': current_app.config.get('MAX_DOWNLOADS_PER_MONTH', 50)
    }
    
    remaining = {
        'today': max(0, limits['per_day'] - stats['today']),
        'this_week': max(0, limits['per_week'] - stats['this_week']),
        'this_month': max(0, limits['per_month'] - stats['this_month'])
    }
    
    return jsonify({
        'role': 'user',
        'used': stats,
        'limits': limits,
        'remaining': remaining,
        'can_download': remaining['today'] > 0
    })


# ===================== WISHLIST API =====================

@books_bp.route("/wishlist/add/<int:book_id>", methods=["POST"])
def add_to_wishlist(book_id):
    """Add a book to wishlist"""
    if not session.get('user_id'):
        return {"success": False, "message": "Please login first"}, 401
    
    # Check if book exists
    book = Book.query.get(book_id)
    if not book:
        return {"success": False, "message": "Book not found"}, 404
    
    wishlist_item = Wishlist.query.filter_by(
        user_id=session['user_id'], 
        book_id=book_id
    ).first()
    
    if not wishlist_item:
        wishlist_item = Wishlist(
            user_id=session['user_id'], 
            book_id=book_id
        )
        db.session.add(wishlist_item)
        db.session.commit()
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='wishlist_add',
            book_id=book_id,
            description=f"Added {book.title} to wishlist"
        )
        
        return {"success": True, "message": "Added to wishlist", "action": "added"}
    
    return {"success": False, "message": "Already in wishlist"}, 400


@books_bp.route("/wishlist/remove/<int:book_id>", methods=["POST"])
def remove_from_wishlist(book_id):
    """Remove a book from wishlist"""
    if not session.get('user_id'):
        return {"success": False, "message": "Please login first"}, 401
    
    wishlist_item = Wishlist.query.filter_by(
        user_id=session['user_id'], 
        book_id=book_id
    ).first()
    
    if wishlist_item:
        db.session.delete(wishlist_item)
        db.session.commit()
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='wishlist_remove',
            book_id=book_id
        )
        
        return {"success": True, "message": "Removed from wishlist", "action": "removed"}
    
    return {"success": False, "message": "Not in wishlist"}, 404


@books_bp.route("/wishlist")
@login_required
def view_wishlist():
    """View user's wishlist"""
    wishlist_items = Wishlist.query.filter_by(user_id=session['user_id']).all()
    books = [item.book for item in wishlist_items]
    
    return render_template("wishlist.html", 
                         books=books,
                         count=len(books))


@books_bp.route("/api/wishlist/toggle/<int:book_id>", methods=["POST"])
def toggle_wishlist(book_id):
    """Toggle wishlist status (API endpoint)"""
    if not session.get('user_id'):
        return {"success": False, "message": "Please login first"}, 401
    
    # Check if book exists
    book = Book.query.get(book_id)
    if not book:
        return {"success": False, "message": "Book not found"}, 404
    
    wishlist_item = Wishlist.query.filter_by(
        user_id=session['user_id'], 
        book_id=book_id
    ).first()
    
    if wishlist_item:
        db.session.delete(wishlist_item)
        db.session.commit()
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='wishlist_remove',
            book_id=book_id
        )
        
        return {"success": True, "message": "Removed from wishlist", "action": "removed"}
    else:
        wishlist_item = Wishlist(
            user_id=session['user_id'], 
            book_id=book_id
        )
        db.session.add(wishlist_item)
        db.session.commit()
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='wishlist_add',
            book_id=book_id,
            description=f"Added {book.title} to wishlist"
        )
        
        return {"success": True, "message": "Added to wishlist", "action": "added"}


# ===================== CATEGORY ROUTES =====================

@books_bp.route("/category/<string:category_name>")
def category_view(category_name):
    """View books by category"""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('BOOKS_PER_PAGE', 12)
    
    books_query = Book.query.filter_by(category=category_name)
    total_results = books_query.count()
    books = books_query.order_by(Book.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    
    total_pages = math.ceil(total_results / per_page) if total_results > 0 else 1
    
    wishlist_ids = []
    if session.get('user_id'):
        wishlist = Wishlist.query.filter_by(user_id=session['user_id']).all()
        wishlist_ids = [item.book_id for item in wishlist]
    
    return render_template("category.html",
                         books=books,
                         category=category_name,
                         total_results=total_results,
                         page=page,
                         total_pages=total_pages,
                         wishlist_ids=wishlist_ids)


# ===================== REVIEW ROUTES =====================

@books_bp.route("/review/<int:book_id>", methods=["POST"])
@login_required
def add_review(book_id):
    """Add a review for a book"""
    book = Book.query.get_or_404(book_id)
    
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()
    
    if not rating or rating < 1 or rating > 5:
        flash("Please provide a valid rating (1-5 stars)")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    # Check if user already reviewed this book
    existing_review = Review.query.filter_by(
        user_id=session['user_id'],
        book_id=book_id
    ).first()
    
    if existing_review:
        # Update existing review
        existing_review.rating = rating
        existing_review.comment = comment
        existing_review.created_at = datetime.utcnow()
        flash("Your review has been updated!")
    else:
        # Create new review
        review = Review(
            user_id=session['user_id'],
            book_id=book_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)
        flash("Thank you for your review!")
        
        # Log activity
        log_activity(
            user_id=session['user_id'],
            activity_type='review',
            book_id=book_id,
            description=f"Reviewed {book.title} with {rating} stars"
        )
    
    # Update book's average rating - FIXED: Use average_rating
    all_reviews = Review.query.filter_by(book_id=book_id).all()
    if all_reviews:
        avg_rating = sum(r.rating for r in all_reviews) / len(all_reviews)
        book.average_rating = round(avg_rating, 1)  # Changed from book.rating to book.average_rating
    
    db.session.commit()
    
    return redirect(url_for('books.book_details', book_id=book_id))


@books_bp.route("/review/delete/<int:review_id>", methods=["POST"])
@login_required
def delete_review(review_id):
    """Delete a review"""
    review = Review.query.get_or_404(review_id)
    
    # Check ownership or admin
    if review.user_id != session['user_id'] and session.get('role') != 'admin':
        flash("You don't have permission to delete this review")
        return redirect(url_for('books.book_details', book_id=review.book_id))
    
    book_id = review.book_id
    db.session.delete(review)
    
    # Update book's average rating - FIXED: Use average_rating
    book = Book.query.get(book_id)
    all_reviews = Review.query.filter_by(book_id=book_id).all()
    if all_reviews:
        avg_rating = sum(r.rating for r in all_reviews) / len(all_reviews)
        book.average_rating = round(avg_rating, 1)  # Changed from book.rating to book.average_rating
    else:
        book.average_rating = 0.0  # Changed from book.rating to book.average_rating
    
    db.session.commit()
    
    flash("Review deleted successfully")
    return redirect(url_for('books.book_details', book_id=book_id))


# ===================== BORROW ROUTE =====================

@books_bp.route("/borrow/<int:book_id>", methods=["GET", "POST"])
@login_required
def borrow(book_id):
    """Borrow a physical book"""
    book = Book.query.get_or_404(book_id)
    
    if not book.has_physical:
        flash("This book is not available in physical format.")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    if book.available_copies <= 0:
        flash("No copies of this book are currently available.")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    user = User.query.get(session['user_id'])
    
    # Check if user has library card
    if not user.library_card or not user.library_card.is_active:
        flash("You need an active library card to borrow books.")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    if user.library_card.is_expired():
        flash("Your library card has expired. Please renew it to borrow books.")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    # Check borrowing limit
    current_borrowings = CirculationRecord.query.filter_by(
        user_id=user.id,
        status='active'
    ).count()
    
    max_borrowings = current_app.config.get('MAX_BORROWINGS_PER_USER', 5)
    
    if current_borrowings >= max_borrowings:
        flash(f"You have reached the maximum borrowing limit ({max_borrowings} books).")
        return redirect(url_for('books.book_details', book_id=book_id))
    
    if request.method == "POST":
        borrow_days = request.form.get('borrow_days', 14, type=int)
        
        # Find an available copy
        copy = ItemCopy.query.filter_by(
            book_id=book.id,
            status='available'
        ).first()
        
        if not copy:
            flash("No copies available at the moment.")
            return redirect(url_for('books.book_details', book_id=book_id))
        
        due_date = datetime.utcnow() + timedelta(days=borrow_days)
        
        # Create circulation record
        circulation = CirculationRecord(
            copy_id=copy.id,
            user_id=user.id,
            due_date=due_date,
            checkout_staff=None,  # Self-checkout
            status='active'
        )
        db.session.add(circulation)
        
        # Update copy status
        copy.status = 'checked_out'
        copy.current_circulation_id = circulation.id
        copy.last_checkout = datetime.utcnow()
        
        # Update book stats
        book.available_copies -= 1
        book.borrow_count += 1
        
        # Update user stats
        user.total_books_borrowed += 1
        
        db.session.commit()
        
        # Log activity
        log_activity(
            user_id=user.id,
            activity_type='borrow',
            book_id=book.id,
            description=f"Borrowed {book.title}"
        )
        
        flash(f"✅ You have successfully borrowed '{book.title}'. Due date: {due_date.strftime('%Y-%m-%d')}")
        return redirect(url_for('books.book_details', book_id=book.id))
    
    return render_template("borrow.html", book=book)


# ===================== CONTEXT PROCESSOR =====================

@books_bp.context_processor
def inject_user_data():
    """Inject user-specific data into all templates"""
    data = {}
    
    if session.get('user_id'):
        # Get wishlist count
        data['wishlist_count'] = Wishlist.query.filter_by(user_id=session['user_id']).count()
        
        # Get pending special requests count
        data['pending_requests_count'] = SpecialRequest.query.filter_by(
            user_id=session['user_id'],
            status='pending'
        ).count()
        
        # Get user object
        user = User.query.get(session['user_id'])
        if user:
            data['user_clearance'] = user.security_clearance
            data['user_role'] = user.role
    else:
        data['wishlist_count'] = 0
        data['pending_requests_count'] = 0
    
    return data


    # ===================== barcode =====================
    # ===================== BARCODE BORROWING =====================

@books_bp.route("/borrow/barcode")
@login_required
def borrow_barcode():
    """Page for borrowing books by barcode"""
    return render_template("auth/borrow_barcode.html")


@books_bp.route("/api/barcode/validate/<barcode>")
@login_required
def validate_barcode(barcode):
    """Validate a book barcode and return book info"""
    # Find the copy by barcode
    copy = ItemCopy.query.filter_by(barcode=barcode).first()
    
    if not copy:
        return jsonify({"success": False, "message": "Invalid barcode. Book not found."})
    
    # Check if copy is available
    if copy.status != 'available':
        return jsonify({"success": False, "message": f"Book is {copy.status}. Not available for borrowing."})
    
    # Check if book is reference only
    if copy.is_reference_only:
        return jsonify({"success": False, "message": "This is a reference copy and cannot be borrowed."})
    
    # Check if user already has this book borrowed
    existing = CirculationRecord.query.filter_by(
        copy_id=copy.id,
        user_id=session['user_id'],
        status='active'
    ).first()
    
    if existing:
        return jsonify({"success": False, "message": "You already have this book borrowed."})
    
    return jsonify({
        "success": True,
        "book": {
            "id": copy.book.id,
            "title": copy.book.title,
            "author": copy.book.author,
            "isbn": copy.book.isbn
        },
        "copy_id": copy.id,
        "barcode": copy.barcode
    })


@books_bp.route("/api/borrow/barcode", methods=["POST"])
@login_required
def borrow_by_barcode():
    """Borrow books by barcode"""
    data = request.get_json()
    barcodes = data.get('barcodes', [])
    borrow_days = data.get('borrow_days', 14)
    
    if not barcodes:
        return jsonify({"success": False, "message": "No barcodes provided"}), 400
    
    user = User.query.get(session['user_id'])
    
    # Check if user has active library card
    if not user.library_card or not user.library_card.is_active:
        return jsonify({"success": False, "message": "You need an active library card to borrow books."})
    
    if user.library_card.is_expired():
        return jsonify({"success": False, "message": "Your library card has expired. Please renew it."})
    
    # Check borrowing limit
    current_borrowings = CirculationRecord.query.filter_by(
        user_id=user.id,
        status='active'
    ).count()
    
    max_borrowings = current_app.config.get('MAX_BORROWINGS_PER_USER', 5)
    
    if current_borrowings + len(barcodes) > max_borrowings:
        return jsonify({
            "success": False, 
            "message": f"You can only borrow {max_borrowings - current_borrowings} more book(s)."
        })
    
    borrowed_books = []
    failed_books = []
    
    for barcode in barcodes:
        # Find copy by barcode
        copy = ItemCopy.query.filter_by(barcode=barcode).first()
        
        if not copy:
            failed_books.append({"barcode": barcode, "reason": "Invalid barcode"})
            continue
        
        if copy.status != 'available':
            failed_books.append({"barcode": barcode, "reason": f"Book is {copy.status}"})
            continue
        
        if copy.is_reference_only:
            failed_books.append({"barcode": barcode, "reason": "Reference copy cannot be borrowed"})
            continue
        
        # Check if user already has this copy
        existing = CirculationRecord.query.filter_by(
            copy_id=copy.id,
            user_id=user.id,
            status='active'
        ).first()
        
        if existing:
            failed_books.append({"barcode": barcode, "reason": "Already borrowed"})
            continue
        
        due_date = datetime.utcnow() + timedelta(days=borrow_days)
        
        # Create circulation record
        circulation = CirculationRecord(
            copy_id=copy.id,
            user_id=user.id,
            due_date=due_date,
            checkout_staff=None,  # Self-checkout
            status='active'
        )
        db.session.add(circulation)
        
        # Update copy status
        copy.status = 'checked_out'
        copy.current_circulation_id = circulation.id
        copy.last_checkout = datetime.utcnow()
        
        # Update book stats
        copy.book.available_copies -= 1
        copy.book.borrow_count = (copy.book.borrow_count or 0) + 1
        
        # Update user stats
        user.total_books_borrowed = (user.total_books_borrowed or 0) + 1
        
        borrowed_books.append({
            "barcode": barcode,
            "title": copy.book.title,
            "due_date": due_date.strftime('%Y-%m-%d')
        })
        
        # Log activity
        log_activity(
            user_id=user.id,
            activity_type='borrow',
            book_id=copy.book_id,
            description=f"Borrowed {copy.book.title} via barcode"
        )
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "borrowed_count": len(borrowed_books),
        "borrowed_books": borrowed_books,
        "failed_books": failed_books
    })