from flask import Blueprint, render_template, request, session, flash, redirect, url_for, current_app, send_from_directory, abort, jsonify, make_response, g
from models import db, User, Book, BorrowRecord, LibraryCard, DownloadLog, BookReservation, Review, ReadingHistory, Wishlist, Bookmark, Annotation, ReadingProgress, RecentActivity, SpecialRequest, AcquisitionRequest, PurchaseOrder, PurchaseOrderItem, CatalogingQueue, ItemCopy, CirculationRecord, Reservation, Fine, Notification, Announcement, AuditLog, ApiKey, BackupLog, ScheduledReport, Vendor, Budget, SystemSetting, ReadingSession, UserSession
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import uuid
import imghdr
import random
import csv
import json
import time
from functools import wraps
from sqlalchemy import func, desc, and_, or_, case
from sqlalchemy.exc import SQLAlchemyError
from io import StringIO, BytesIO
import base64
import secrets
from flask import make_response
from werkzeug.security import generate_password_hash
import hashlib


admin_bp = Blueprint('admin', __name__)

# ===================== DECORATORS =====================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash("⛔ Unauthorized access. Admin privileges required.")
            return redirect(url_for('books.home'))
        
        # Log admin access for audit
        try:
            user = User.query.get(session['user_id'])
            if user:
                AuditLog.log(
                    user_id=user.id,
                    action='admin_access',
                    description=f"Accessed {request.endpoint}",
                    target_type='route',
                    target_name=request.endpoint,
                    request=request
                )
        except:
            pass
        
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    """Decorator for checking specific permissions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("⛔ Please log in first.")
                return redirect(url_for('auth.login'))
            
            user = User.query.get(session['user_id'])
            if not user or not user.has_permission(permission):
                flash(f"⛔ You don't have permission: {permission}")
                return redirect(url_for('admin.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def clearance_required(level):
    """Decorator for checking security clearance"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("⛔ Please log in first.")
                return redirect(url_for('auth.login'))
            
            user = User.query.get(session['user_id'])
            if not user or not user.has_clearance(level):
                flash(f"⛔ Security clearance {level} required")
                return redirect(url_for('admin.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@admin_bp.route("/debug-template")
@admin_required
def debug_template():
    """Debug template loading"""
    from flask import current_app
    import os
    import sys
    
    template_folder = current_app.template_folder
    admin_template_path = os.path.join(template_folder, 'admin', 'cataloging_queue.html')
    
    # List all admin templates
    admin_dir = os.path.join(template_folder, 'admin')
    admin_files = []
    if os.path.exists(admin_dir):
        admin_files = os.listdir(admin_dir)
    
    return {
        'template_folder': template_folder,
        'template_folder_exists': os.path.exists(template_folder),
        'admin_folder_exists': os.path.exists(admin_dir),
        'admin_template_path': admin_template_path,
        'file_exists': os.path.exists(admin_template_path),
        'absolute_path': os.path.abspath(admin_template_path),
        'file_size': os.path.getsize(admin_template_path) if os.path.exists(admin_template_path) else 0,
        'admin_files': admin_files,
        'current_working_dir': os.getcwd(),
        'python_path': sys.path
    }



@admin_bp.route('/test-image/<path:filepath>')
def test_image(filepath):
    """Simple test route to serve images"""
    import os
    from flask import send_file
    
    upload_folder = current_app.config['UPLOAD_FOLDER']
    full_path = os.path.join(upload_folder, filepath)
    print(f"Looking for: {full_path}")  # This will show in console
    
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_file(full_path)
    return f"File not found: {full_path}", 404
# ===================== FILE HANDLING =====================

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def allowed_pdf(filename):
    return allowed_file(filename, current_app.config.get('ALLOWED_EXTENSIONS', {'pdf', 'epub', 'mobi'}))

def allowed_image(filename):
    return allowed_file(filename, current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'}))

def validate_image(stream):
    header = stream.read(512)
    stream.seek(0)
    format = imghdr.what(None, header)
    if not format:
        return None
    return '.' + format if format != 'jpeg' else '.jpg'

def secure_file_upload(file, subfolder=''):
    """Securely upload file with virus scanning"""
    if not file or file.filename == '':
        return None, "No file selected"
    
    # Generate secure filename
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    
    # Create subfolder if needed
    upload_path = current_app.config["UPLOAD_FOLDER"]
    if subfolder:
        upload_path = os.path.join(upload_path, subfolder)
        os.makedirs(upload_path, exist_ok=True)
    
    file_path = os.path.join(upload_path, unique_filename)
    
    # Save file
    file.save(file_path)
    
    # Get file info
    file_size = os.path.getsize(file_path)
    with open(file_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    
    return {
        'filename': unique_filename,
        'original_filename': filename,
        'path': file_path,
        'size': file_size,
        'hash': file_hash,
        'mime_type': file.mimetype
    }, None


# ===================== NOTIFICATION HELPERS =====================

def send_user_notification(user, subject, message, notification_type='info', category=None, link=None):
    """Send notification to user via multiple channels"""
    try:
        user_id = user.id if hasattr(user, 'id') else user
        
        # Create notification in database
        notification = Notification(
            user_id=user_id,
            title=subject,
            message=message,
            type=notification_type,
            category=category,
            link=link
        )
        db.session.add(notification)
        db.session.commit()
        
        # Send email if enabled
        user_obj = user if hasattr(user, 'id') else User.query.get(user_id)
        if user_obj and user_obj.notification_settings.get('email', True):
            try:
                from flask_mail import Message
                from flask import current_app
                
                msg = Message(
                    subject=subject,
                    recipients=[user_obj.email],
                    html=message,
                    sender=current_app.config['MAIL_DEFAULT_SENDER']
                )
                from app import mail
                mail.send(msg)
                notification.email_sent = True
                notification.email_sent_at = datetime.utcnow()
                db.session.commit()
            except Exception as e:
                current_app.logger.error(f"Email send failed: {e}")
        
        return notification
    except Exception as e:
        current_app.logger.error(f"Error sending notification: {e}")
        return None


def get_approval_email_template(user, status, reason=None):
    """Generate approval email template"""
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5010')
    
    if status == 'approved':
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1a3c1a, #2d5a2d); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">Nigerian Army E-Library</h1>
            </div>
            <div style="background: white; padding: 30px; border: 2px solid #1a3c1a; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #1a3c1a;">Welcome, {user.full_name or user.username}!</h2>
                <p style="font-size: 16px; line-height: 1.5;">Your registration has been <span style="color: #10b981; font-weight: bold;">APPROVED</span>.</p>
                <div style="background: #f0f9f0; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Username:</strong> {user.username}</p>
                    <p style="margin: 5px 0;"><strong>Library Card:</strong> {user.library_card.card_number if user.library_card else 'Pending'}</p>
                    <p style="margin: 5px 0;"><strong>Membership Status:</strong> Active</p>
                </div>
                <p>You can now login and access the library resources:</p>
                <a href="{base_url}/auth/login" 
                   style="display: inline-block; background: #1a3c1a; color: white; padding: 12px 30px; text-decoration: none; border-radius: 25px; margin-top: 20px;">
                    Login to Your Account
                </a>
                <p style="margin-top: 30px; color: #666; font-size: 14px;">
                    If you have any questions, please contact the library administrator.
                </p>
            </div>
        </body>
        </html>
        """
    else:
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #8b0000, #a52a2a); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">Nigerian Army E-Library</h1>
            </div>
            <div style="background: white; padding: 30px; border: 2px solid #8b0000; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #8b0000;">Registration Update</h2>
                <p style="font-size: 16px; line-height: 1.5;">Your registration has been <span style="color: #dc2626; font-weight: bold;">REJECTED</span>.</p>
                <div style="background: #fef2f2; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Reason:</strong> {reason or 'Not specified'}</p>
                </div>
                <p>If you believe this is an error, please contact the library administrator.</p>
                <a href="{base_url}/contact" 
                   style="display: inline-block; background: #8b0000; color: white; padding: 12px 30px; text-decoration: none; border-radius: 25px; margin-top: 20px;">
                    Contact Support
                </a>
            </div>
        </body>
        </html>
        """


# ===================== SOLR INDEXING HELPERS =====================

def trigger_solr_index(book_id, delay=True):
    """Trigger Solr indexing for a book"""
    try:
        from tasks.indexing_tasks import index_book_task
        if delay:
            index_book_task.delay(book_id)
        else:
            from services.solr_client import solr_client
            book = Book.query.get(book_id)
            if book:
                solr_client.index_book(book)
    except ImportError:
        current_app.logger.warning("Solr tasks not available")
    except Exception as e:
        current_app.logger.error(f"Error triggering Solr index: {e}")


def trigger_solr_delete(book_id):
    """Trigger Solr deletion for a book"""
    try:
        from tasks.indexing_tasks import delete_book_task
        delete_book_task.delay(book_id)
    except ImportError:
        current_app.logger.warning("Solr tasks not available")
    except Exception as e:
        current_app.logger.error(f"Error triggering Solr delete: {e}")


def trigger_bulk_reindex():
    """Trigger full Solr reindex"""
    try:
        from tasks.indexing_tasks import reindex_all_task
        task = reindex_all_task.delay()
        return task.id
    except ImportError:
        current_app.logger.warning("Solr tasks not available")
        return None
    except Exception as e:
        current_app.logger.error(f"Error triggering reindex: {e}")
        return None


# ===================== ACTIVITY LOGGING =====================

def log_admin_activity(user_id, action, description=None, book_id=None, metadata=None):
    """Log admin activity with enhanced details"""
    try:
        activity = RecentActivity(
            user_id=user_id,
            activity_type=f"admin_{action}",
            book_id=book_id,
            description=description or f"Admin action: {action}",
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
            data=metadata or {}
        )
        db.session.add(activity)
        
        # Log to AuditLog
        try:
            AuditLog.log(
                user_id=user_id,
                action=action,
                description=description,
                target_type='book' if book_id else None,
                target_id=book_id,
                metadata=metadata,
                request=request
            )
        except:
            pass
        
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to log admin activity: {e}")
        db.session.rollback()


# ===================== SYSTEM HEALTH HELPERS =====================

def get_database_size():
    """Get database size in MB"""
    try:
        result = db.session.execute("SELECT pg_database_size(current_database())").scalar()
        return result / (1024 * 1024) if result else 0
    except:
        return 0

def get_folder_size(path):
    """Get folder size in MB"""
    total_size = 0
    if os.path.exists(path):
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)

def get_cache_hit_rate():
    """Get cache hit rate (placeholder)"""
    return 95.5

def get_background_job_count():
    """Get count of background jobs"""
    try:
        from celery import current_app
        i = current_app.control.inspect()
        active = i.active() or {}
        scheduled = i.scheduled() or {}
        reserved = i.reserved() or {}
        total = sum(len(v) for v in active.values()) if active else 0
        total += sum(len(v) for v in scheduled.values()) if scheduled else 0
        total += sum(len(v) for v in reserved.values()) if reserved else 0
        return total
    except:
        return 0


# ===================== MAIN DASHBOARD =====================

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    """Main admin dashboard with all metrics"""
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    # Basic stats
    total_users = User.query.count()
    total_books = Book.query.count()
    active_borrowings = BorrowRecord.query.filter_by(status='borrowed').count()
    
    # Pending user approvals
    pending_users = User.query.filter_by(approval_status='pending').count()
    approved_today = User.query.filter(
        User.approval_status == 'approved',
        User.approved_at >= today_start
    ).count()
    
    # Library Card Stats
    total_cards = LibraryCard.query.count()
    expired_cards = LibraryCard.query.filter(LibraryCard.expiry_date < now).count()
    expiring_soon = LibraryCard.query.filter(
        LibraryCard.expiry_date >= now,
        LibraryCard.expiry_date <= now + timedelta(days=30)
    ).count()
    
    # WORKFLOW STATS
    # Acquisition stats
    pending_requests = AcquisitionRequest.query.filter_by(status='pending').count()
    approved_requests = AcquisitionRequest.query.filter_by(status='approved').count()
    total_orders = PurchaseOrder.query.count()
    
    # Cataloging stats
    pending_cataloging = CatalogingQueue.query.filter_by(status='pending').count()
    in_progress_cataloging = CatalogingQueue.query.filter_by(status='in_progress').count()
    completed_cataloging = CatalogingQueue.query.filter_by(status='completed').count()
    
    # Circulation stats
    active_checkouts = CirculationRecord.query.filter_by(status='active').count()
    overdue_items = CirculationRecord.query.filter(
        CirculationRecord.status == 'active',
        CirculationRecord.due_date < now
    ).count()
    active_reservations = Reservation.query.filter_by(status='active').count()
    
    # Overdue books (existing)
    overdue_books = BorrowRecord.query.filter(
        BorrowRecord.status == 'borrowed',
        BorrowRecord.due_date < now
    ).count()
    
    # Download stats
    total_downloads = DownloadLog.query.count()
    downloads_today = DownloadLog.query.filter(
        DownloadLog.timestamp >= today_start
    ).count()
    
    # Special requests stats
    pending_requests_special = SpecialRequest.query.filter_by(status='pending').count()
    approved_requests_today = SpecialRequest.query.filter(
        SpecialRequest.status == 'approved',
        SpecialRequest.reviewed_at >= today_start
    ).count()
    
    # Reading stats
    total_reading_sessions = ReadingProgress.query.count()
    active_readers_today = ReadingProgress.query.filter(
        ReadingProgress.last_accessed >= today_start
    ).count()
    
    total_bookmarks = Bookmark.query.count()
    total_annotations = Annotation.query.count()
    
    # New users
    new_users_today = User.query.filter(
        User.created_at >= today_start
    ).count()
    new_users_this_week = User.query.filter(
        User.created_at >= week_ago
    ).count()
    new_users_this_month = User.query.filter(
        User.created_at >= month_ago
    ).count()
    
    # New books
    new_books_today = Book.query.filter(
        Book.created_at >= today_start
    ).count()
    new_books_this_week = Book.query.filter(
        Book.created_at >= week_ago
    ).count()
    
    # Restricted books count
    restricted_books = Book.query.filter_by(requires_special_request=True).count()
    
    # Books without covers
    books_without_covers = Book.query.filter_by(cover_image=None).count()
    
    # Pending reservations
    pending_reservations = BookReservation.query.filter_by(status='pending').count()
    
    # Total fines
    total_fines = db.session.query(db.func.sum(Fine.amount)).filter_by(paid=False).scalar() or 0
    
    # ===== NEW STATS FOR ENHANCED MODELS =====
    
    # Category stats
    category_stats = db.session.query(
        Book.category, func.count(Book.id).label('count')
    ).group_by(Book.category).order_by(desc('count')).all()
    total_categories = len([c for c in category_stats if c[0]])
    
    # Tag stats
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    all_tags = set()
    for book in all_books:
        if book.keywords:
            all_tags.update(book.keywords)
    total_tags = len(all_tags)
    
    # Notification stats
    notification_stats = {
        'unread_notifications': Notification.query.filter_by(is_read=False).count(),
        'total_notifications': Notification.query.count(),
    }
    
    # API stats
    api_stats = {
        'total_api_keys': ApiKey.query.count(),
        'active_api_keys': ApiKey.query.filter_by(is_active=True).count(),
    }
    
    # Budget stats
    current_year = now.year
    budget_stats = {
        'total_allocated': db.session.query(func.sum(Budget.allocated)).filter_by(fiscal_year=current_year).scalar() or 0,
        'total_committed': db.session.query(func.sum(Budget.committed)).filter_by(fiscal_year=current_year).scalar() or 0,
        'total_expended': db.session.query(func.sum(Budget.expended)).filter_by(fiscal_year=current_year).scalar() or 0,
    }
    
    # Announcement stats
    announcement_stats = {
        'total': Announcement.query.count(),
        'active': Announcement.query.filter_by(is_active=True).count(),
    }
    
    # Audit stats
    audit_stats = {
        'total_logs': AuditLog.query.count(),
        'logs_today': AuditLog.query.filter(AuditLog.timestamp >= today_start).count(),
    }
    
    # Vendor stats
    vendor_stats = {
        'total': Vendor.query.count(),
        'active': Vendor.query.filter_by(is_active=True).count(),
    }
    
    # Backup stats
    backup_stats = {
        'total': BackupLog.query.count(),
        'latest': BackupLog.query.order_by(BackupLog.created_at.desc()).first(),
    }
    
    # Solr status (if available)
    solr_status = None
    solr_doc_count = 0
    try:
        from services.solr_client import solr_client
        if hasattr(current_app.extensions, 'solr') and current_app.extensions.get('solr'):
            solr_doc_count = solr_client.count()
            solr_status = "connected"
        else:
            solr_status = "disconnected"
    except:
        solr_status = "unavailable"
    
    # Weekly activity for chart
    weekly_activity = []
    for i in range(7):
        day = now - timedelta(days=i)
        next_day = day + timedelta(days=1)
        
        downloads = DownloadLog.query.filter(
            DownloadLog.timestamp >= day,
            DownloadLog.timestamp < next_day
        ).count()
        
        reading_sessions = ReadingProgress.query.filter(
            ReadingProgress.last_accessed >= day,
            ReadingProgress.last_accessed < next_day
        ).count()
        
        reading_sessions_count = ReadingSession.query.filter(
            ReadingSession.start_time >= day,
            ReadingSession.start_time < next_day
        ).count()
        
        new_users = User.query.filter(
            User.created_at >= day,
            User.created_at < next_day
        ).count()
        
        new_requests = SpecialRequest.query.filter(
            SpecialRequest.created_at >= day,
            SpecialRequest.created_at < next_day
        ).count()
        
        new_registrations = User.query.filter(
            User.created_at >= day,
            User.created_at < next_day,
            User.approval_status == 'pending'
        ).count()
        
        new_acquisitions = AcquisitionRequest.query.filter(
            AcquisitionRequest.request_date >= day,
            AcquisitionRequest.request_date < next_day
        ).count()
        
        new_checkouts = CirculationRecord.query.filter(
            CirculationRecord.checkout_date >= day,
            CirculationRecord.checkout_date < next_day
        ).count()
        
        new_card_expiries = LibraryCard.query.filter(
            LibraryCard.expiry_date >= day,
            LibraryCard.expiry_date < next_day
        ).count()
        
        new_audit_logs = AuditLog.query.filter(
            AuditLog.timestamp >= day,
            AuditLog.timestamp < next_day
        ).count()
        
        weekly_activity.append({
            'day': day.strftime('%a'),
            'downloads': downloads,
            'reading_sessions': reading_sessions,
            'new_users': new_users,
            'new_requests': new_requests,
            'new_registrations': new_registrations,
            'new_acquisitions': new_acquisitions,
            'new_checkouts': new_checkouts,
            'new_card_expiries': new_card_expiries,
            'new_audit_logs': new_audit_logs,
            'total': downloads + reading_sessions + new_users + new_requests + new_registrations + new_acquisitions + new_checkouts + new_card_expiries + new_audit_logs
        })
    weekly_activity.reverse()
    
    # Top categories
    top_categories = []
    for cat in category_stats[:5]:
        top_categories.append({
            'name': cat[0] or 'Uncategorized',
            'count': cat[1]
        })
    
    # Top tags
    tag_counts = {}
    for book in all_books:
        if book.keywords:
            for tag in book.keywords:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    top_tags = [{'name': k, 'count': v} for k, v in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Most read books
    most_read_books = db.session.query(
        Book.id, Book.title, Book.author, Book.cover_image,
        func.count(ReadingHistory.id).label('read_count')
    ).join(ReadingHistory, ReadingHistory.book_id == Book.id)\
     .group_by(Book.id)\
     .order_by(desc('read_count'))\
     .limit(5).all()
    
    # Most downloaded books
    most_downloaded = db.session.query(
        Book.id, Book.title, Book.author, Book.cover_image,
        func.count(DownloadLog.id).label('download_count')
    ).join(DownloadLog, DownloadLog.book_id == Book.id)\
     .group_by(Book.id)\
     .order_by(desc('download_count'))\
     .limit(5).all()
    
    # Recent users
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    # Recent pending users
    recent_pending = User.query.filter_by(approval_status='pending')\
        .order_by(User.created_at.desc()).limit(5).all()
    
    # Recent borrowings
    recent_borrowings = BorrowRecord.query.order_by(
        BorrowRecord.borrow_date.desc()
    ).limit(5).all()
    
    # Recent downloads
    recent_downloads = DownloadLog.query.order_by(
        DownloadLog.timestamp.desc()
    ).limit(5).all()
    
    # Recent reading activity
    recent_reading = ReadingProgress.query.order_by(
        ReadingProgress.last_accessed.desc()
    ).limit(5).all()
    
    # Recent special requests
    recent_requests = SpecialRequest.query.order_by(
        SpecialRequest.created_at.desc()
    ).limit(5).all()
    
    # Recent acquisition requests
    recent_acquisitions = AcquisitionRequest.query.order_by(
        AcquisitionRequest.request_date.desc()
    ).limit(5).all()
    
    # Recent cataloging
    recent_cataloging = CatalogingQueue.query.filter(CatalogingQueue.completed_at.isnot(None))\
        .order_by(CatalogingQueue.completed_at.desc()).limit(5).all()
    
    # Recent checkouts
    recent_checkouts = CirculationRecord.query.order_by(
        CirculationRecord.checkout_date.desc()
    ).limit(5).all()
    
    # Recent card expiries
    recent_expiries = LibraryCard.query.filter(
        LibraryCard.expiry_date >= now
    ).order_by(LibraryCard.expiry_date.asc()).limit(5).all()
    
    # ===== NEW RECENT ITEMS =====
    
    recent_notifications = Notification.query.order_by(
        Notification.created_at.desc()
    ).limit(5).all()
    
    recent_announcements = Announcement.query.filter_by(is_active=True)\
        .order_by(Announcement.created_at.desc()).limit(5).all()
    
    recent_audit_logs = AuditLog.query.order_by(
        AuditLog.timestamp.desc()
    ).limit(5).all()
    
    # System health
    system_health = {
        'database_size': get_database_size(),
        'upload_folder_size': get_folder_size(current_app.config['UPLOAD_FOLDER']),
        'cache_hit_rate': get_cache_hit_rate(),
        'background_jobs': get_background_job_count(),
    }
    
    return render_template("admin/admin_dashboard.html",
                         total_users=total_users,
                         total_books=total_books,
                         total_categories=total_categories,
                         total_tags=total_tags,
                         top_tags=top_tags,
                         active_borrowings=active_borrowings,
                         overdue_books=overdue_books,
                         total_downloads=total_downloads,
                         downloads_today=downloads_today,
                         pending_users=pending_users,
                         approved_today=approved_today,
                         total_cards=total_cards,
                         expired_cards=expired_cards,
                         expiring_soon=expiring_soon,
                         pending_requests=pending_requests_special,
                         approved_requests_today=approved_requests_today,
                         total_reading_sessions=total_reading_sessions,
                         active_readers_today=active_readers_today,
                         total_bookmarks=total_bookmarks,
                         total_annotations=total_annotations,
                         new_users_today=new_users_today,
                         new_users_this_week=new_users_this_week,
                         new_users_this_month=new_users_this_month,
                         new_books_today=new_books_today,
                         new_books_this_week=new_books_this_week,
                         restricted_books=restricted_books,
                         books_without_covers=books_without_covers,
                         pending_reservations=pending_reservations,
                         solr_status=solr_status,
                         solr_doc_count=solr_doc_count,
                         weekly_activity=weekly_activity,
                         top_categories=top_categories,
                         most_read_books=most_read_books,
                         most_downloaded=most_downloaded,
                         recent_users=recent_users,
                         recent_pending=recent_pending,
                         recent_borrowings=recent_borrowings,
                         recent_downloads=recent_downloads,
                         recent_reading=recent_reading,
                         recent_requests=recent_requests,
                         pending_requests_acq=pending_requests,
                         approved_requests=approved_requests,
                         total_orders=total_orders,
                         pending_cataloging=pending_cataloging,
                         in_progress_cataloging=in_progress_cataloging,
                         completed_cataloging=completed_cataloging,
                         active_checkouts=active_checkouts,
                         overdue_items=overdue_items,
                         active_reservations=active_reservations,
                         total_fines=total_fines,
                         recent_acquisitions=recent_acquisitions,
                         recent_cataloging=recent_cataloging,
                         recent_checkouts=recent_checkouts,
                         recent_expiries=recent_expiries,
                         # New stats
                         notification_stats=notification_stats,
                         api_stats=api_stats,
                         budget_stats=budget_stats,
                         announcement_stats=announcement_stats,
                         audit_stats=audit_stats,
                         vendor_stats=vendor_stats,
                         backup_stats=backup_stats,
                         recent_notifications=recent_notifications,
                         recent_announcements=recent_announcements,
                         recent_audit_logs=recent_audit_logs,
                         system_health=system_health,
                         now=now)


# ===================== CATEGORY MANAGEMENT =====================

@admin_bp.route("/manage-categories")
@admin_required
def manage_categories():
    """Manage book categories"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '').strip()
    
    # Get all unique categories with counts and metadata
    query = db.session.query(
        Book.category,
        func.count(Book.id).label('book_count'),
        func.max(Book.created_at).label('last_added'),
        func.sum(case([(Book.has_digital == True, 1)], else_=0)).label('digital_count'),
        func.sum(case([(Book.has_physical == True, 1)], else_=0)).label('physical_count'),
        func.sum(case([(Book.requires_special_request == True, 1)], else_=0)).label('restricted_count')
    ).filter(
        Book.category.isnot(None),
        Book.category != ''
    ).group_by(Book.category)
    
    if search:
        query = query.filter(Book.category.ilike(f'%{search}%'))
    
    # Get total count for pagination
    total = query.count()
    
    # Get paginated results
    categories = query.order_by(Book.category).offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Get all books for each category (for detailed view)
    category_books = {}
    for cat in categories:
        if cat.category:
            books = Book.query.filter_by(category=cat.category).order_by(Book.title).limit(10).all()
            category_books[cat.category] = books
    
    # Get category usage statistics
    stats = {
        'total_categories': total,
        'most_books': db.session.query(
            Book.category, func.count(Book.id).label('count')
        ).filter(
            Book.category.isnot(None),
            Book.category != ''
        ).group_by(Book.category).order_by(desc('count')).first(),
        'least_books': db.session.query(
            Book.category, func.count(Book.id).label('count')
        ).filter(
            Book.category.isnot(None),
            Book.category != ''
        ).group_by(Book.category).order_by('count').first(),
        'categories_with_most_digital': db.session.query(
            Book.category, func.count(Book.id).label('count')
        ).filter(
            Book.category.isnot(None),
            Book.category != '',
            Book.has_digital == True
        ).group_by(Book.category).order_by(desc('count')).first(),
        'empty_categories': 0  # Categories with no books - not applicable as we only show categories with books
    }
    
    return render_template("admin/manage_categories.html",
                         categories=categories,
                         category_books=category_books,
                         stats=stats,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         search=search)


@admin_bp.route("/manage-categories/<path:category_name>")
@admin_required
def view_category(category_name):
    """View all books in a specific category"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get all books in this category
    books_query = Book.query.filter_by(category=category_name, is_deleted=False)
    total = books_query.count()
    books = books_query.order_by(Book.title).offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Get category statistics
    stats = {
        'total_books': total,
        'digital_books': books_query.filter_by(has_digital=True).count(),
        'physical_books': books_query.filter_by(has_physical=True).count(),
        'restricted_books': books_query.filter_by(requires_special_request=True).count(),
        'featured_books': books_query.filter_by(is_featured=True).count(),
        'new_arrivals': books_query.filter_by(is_new_arrival=True).count(),
        'avg_publication_year': db.session.query(func.avg(Book.published_year)).filter_by(category=category_name).scalar() or 0,
        'total_downloads': db.session.query(func.sum(Book.download_count)).filter_by(category=category_name).scalar() or 0,
        'total_views': db.session.query(func.sum(Book.view_count)).filter_by(category=category_name).scalar() or 0
    }
    
    # Get subcategories if any
    subcategories = db.session.query(
        Book.subcategory, func.count(Book.id).label('count')
    ).filter(
        Book.category == category_name,
        Book.subcategory.isnot(None),
        Book.subcategory != ''
    ).group_by(Book.subcategory).order_by(Book.subcategory).all()
    
    return render_template("admin/view_category.html",
                         category_name=category_name,
                         books=books,
                         stats=stats,
                         subcategories=subcategories,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/manage-categories/merge", methods=["POST"])
@admin_required
def merge_categories():
    """Merge multiple categories into one"""
    data = request.get_json()
    source_categories = data.get('source_categories', [])
    target_category = data.get('target_category')
    
    if not source_categories or not target_category:
        return jsonify({"success": False, "message": "Source and target categories required"}), 400
    
    if target_category in source_categories:
        return jsonify({"success": False, "message": "Target category cannot be in source list"}), 400
    
    count = 0
    for cat in source_categories:
        books = Book.query.filter_by(category=cat).all()
        for book in books:
            book.category = target_category
            count += 1
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='merge_categories',
        description=f"Merged {len(source_categories)} categories into '{target_category}' affecting {count} books",
        metadata={'source': source_categories, 'target': target_category, 'books_affected': count}
    )
    
    return jsonify({
        "success": True,
        "message": f"Merged {len(source_categories)} categories into '{target_category}'",
        "books_affected": count
    })


@admin_bp.route("/manage-categories/rename", methods=["POST"])
@admin_required
def rename_category():
    """Rename a category"""
    data = request.get_json()
    old_name = data.get('old_name')
    new_name = data.get('new_name')
    
    if not old_name or not new_name:
        return jsonify({"success": False, "message": "Old and new names required"}), 400
    
    if old_name == new_name:
        return jsonify({"success": False, "message": "New name must be different"}), 400
    
    # Check if new name already exists
    existing = Book.query.filter_by(category=new_name).first()
    if existing:
        return jsonify({
            "success": False, 
            "message": f"Category '{new_name}' already exists. Use merge instead."
        }), 400
    
    books = Book.query.filter_by(category=old_name).all()
    count = len(books)
    
    for book in books:
        book.category = new_name
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='rename_category',
        description=f"Renamed category '{old_name}' to '{new_name}' affecting {count} books"
    )
    
    return jsonify({
        "success": True,
        "message": f"Category renamed from '{old_name}' to '{new_name}'",
        "books_affected": count
    })


@admin_bp.route("/manage-categories/delete", methods=["POST"])
@admin_required
def delete_category():
    """Delete a category (set to NULL for all books)"""
    data = request.get_json()
    category_name = data.get('category_name')
    reassign_to = data.get('reassign_to')
    
    if not category_name:
        return jsonify({"success": False, "message": "Category name required"}), 400
    
    books = Book.query.filter_by(category=category_name).all()
    count = len(books)
    
    if reassign_to:
        # Reassign to another category
        for book in books:
            book.category = reassign_to
        message = f"Category '{category_name}' deleted and {count} books reassigned to '{reassign_to}'"
    else:
        # Set to NULL
        for book in books:
            book.category = None
        message = f"Category '{category_name}' deleted and {count} books uncategorized"
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='delete_category',
        description=message,
        metadata={'category': category_name, 'books_affected': count, 'reassigned_to': reassign_to}
    )
    
    return jsonify({
        "success": True,
        "message": message,
        "books_affected": count
    })


@admin_bp.route("/api/categories/stats")
@admin_required
def category_stats_api():
    """API endpoint for category statistics"""
    # Distribution pie chart data
    distribution = db.session.query(
        Book.category,
        func.count(Book.id).label('count')
    ).filter(
        Book.category.isnot(None),
        Book.category != ''
    ).group_by(Book.category).order_by(desc('count')).all()
    
    # Activity over time (last 30 days)
    now = datetime.utcnow()
    activity = []
    for i in range(30):
        day = now - timedelta(days=i)
        next_day = day + timedelta(days=1)
        
        # Books added per category on this day
        daily_counts = db.session.query(
            Book.category,
            func.count(Book.id).label('count')
        ).filter(
            Book.category.isnot(None),
            Book.category != '',
            Book.created_at >= day,
            Book.created_at < next_day
        ).group_by(Book.category).all()
        
        activity.append({
            'date': day.strftime('%Y-%m-%d'),
            'categories': [{'name': c[0], 'count': c[1]} for c in daily_counts]
        })
    
    return jsonify({
        'distribution': [{'name': d[0] or 'Uncategorized', 'count': d[1]} for d in distribution],
        'activity': activity,
        'total_categories': len([d for d in distribution if d[0]]),
        'total_books': Book.query.count(),
        'uncategorized_books': Book.query.filter(
            (Book.category.is_(None)) | (Book.category == '')
        ).count()
    })


# ===================== TAGS MANAGEMENT =====================

@admin_bp.route("/manage-tags")
@admin_required
def manage_tags():
    """Manage book tags/keywords"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'name')  # name, count, recent
    
    # Get all unique tags with counts
    tags_data = []
    
    # Get all books with keywords
    books_with_tags = Book.query.filter(
        Book.keywords.isnot(None),
        Book.keywords != '[]',
        Book.is_deleted == False
    ).all()
    
    # Build tag dictionary
    tag_dict = {}
    for book in books_with_tags:
        if book.keywords:
            for tag in book.keywords:
                if tag not in tag_dict:
                    tag_dict[tag] = {
                        'name': tag,
                        'count': 0,
                        'books': [],
                        'last_used': book.created_at
                    }
                tag_dict[tag]['count'] += 1
                if len(tag_dict[tag]['books']) < 5:  # Store up to 5 sample books
                    tag_dict[tag]['books'].append({
                        'id': book.id,
                        'title': book.title,
                        'author': book.author
                    })
                if book.created_at > tag_dict[tag]['last_used']:
                    tag_dict[tag]['last_used'] = book.created_at
    
    # Convert to list and filter by search
    tags_list = list(tag_dict.values())
    if search:
        tags_list = [t for t in tags_list if search.lower() in t['name'].lower()]
    
    # Sort
    if sort_by == 'count':
        tags_list.sort(key=lambda x: x['count'], reverse=True)
    elif sort_by == 'recent':
        tags_list.sort(key=lambda x: x['last_used'], reverse=True)
    else:  # name
        tags_list.sort(key=lambda x: x['name'].lower())
    
    total = len(tags_list)
    
    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    tags = tags_list[start:end]
    total_pages = (total + per_page - 1) // per_page
    
    # Get tag usage statistics
    stats = {
        'total_tags': total,
        'total_books_with_tags': len(books_with_tags),
        'avg_tags_per_book': sum(len(b.keywords or []) for b in books_with_tags) / len(books_with_tags) if books_with_tags else 0,
        'most_used': tags_list[0] if tags_list else None,
        'least_used': tags_list[-1] if tags_list else None,
    }
    
    # Get recent tags (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.created_at >= thirty_days_ago
    ).all()
    
    recent_tags = {}
    for book in recent_books:
        if book.keywords:
            for tag in book.keywords:
                recent_tags[tag] = recent_tags.get(tag, 0) + 1
    
    recent_tags = [{'name': k, 'count': v} for k, v in sorted(recent_tags.items(), key=lambda x: x[1], reverse=True)[:10]]
    
    return render_template("admin/manage_tags.html",
                         tags=tags,
                         stats=stats,
                         recent_tags=recent_tags,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         search=search,
                         sort_by=sort_by)


@admin_bp.route("/manage-tags/<path:tag_name>")
@admin_required
def view_tag(tag_name):
    """View all books with a specific tag"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Find all books containing this tag
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    
    # Filter books with this tag
    tagged_books = []
    for book in all_books:
        if book.keywords and tag_name in book.keywords:
            tagged_books.append(book)
    
    total = len(tagged_books)
    
    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    books = tagged_books[start:end]
    total_pages = (total + per_page - 1) // per_page
    
    # Get tag statistics
    stats = {
        'total_books': total,
        'digital_books': sum(1 for b in tagged_books if b.has_digital),
        'physical_books': sum(1 for b in tagged_books if b.has_physical),
        'restricted_books': sum(1 for b in tagged_books if b.requires_special_request),
        'featured_books': sum(1 for b in tagged_books if b.is_featured),
        'total_downloads': sum(b.download_count or 0 for b in tagged_books),
        'total_views': sum(b.view_count or 0 for b in tagged_books),
    }
    
    # Get related tags (tags that appear with this tag)
    related_tags = {}
    for book in tagged_books[:50]:  # Check first 50 books
        if book.keywords:
            for tag in book.keywords:
                if tag != tag_name:
                    related_tags[tag] = related_tags.get(tag, 0) + 1
    
    related_tags = [{'name': k, 'count': v} for k, v in sorted(related_tags.items(), key=lambda x: x[1], reverse=True)[:10]]
    
    return render_template("admin/view_tag.html",
                         tag_name=tag_name,
                         books=books,
                         stats=stats,
                         related_tags=related_tags,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/manage-tags/merge", methods=["POST"])
@admin_required
def merge_tags():
    """Merge multiple tags into one"""
    data = request.get_json()
    source_tags = data.get('source_tags', [])
    target_tag = data.get('target_tag')
    
    if not source_tags or not target_tag:
        return jsonify({"success": False, "message": "Source and target tags required"}), 400
    
    if target_tag in source_tags:
        return jsonify({"success": False, "message": "Target tag cannot be in source list"}), 400
    
    count = 0
    # Find all books with source tags
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    
    for book in all_books:
        if book.keywords:
            original_keywords = list(book.keywords)
            new_keywords = []
            changed = False
            
            for tag in original_keywords:
                if tag in source_tags:
                    if target_tag not in new_keywords:
                        new_keywords.append(target_tag)
                    changed = True
                else:
                    new_keywords.append(tag)
            
            if changed:
                book.keywords = new_keywords
                count += 1
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='merge_tags',
        description=f"Merged {len(source_tags)} tags into '{target_tag}' affecting {count} books",
        metadata={'source': source_tags, 'target': target_tag, 'books_affected': count}
    )
    
    return jsonify({
        "success": True,
        "message": f"Merged {len(source_tags)} tags into '{target_tag}'",
        "books_affected": count
    })


@admin_bp.route("/manage-tags/rename", methods=["POST"])
@admin_required
def rename_tag():
    """Rename a tag"""
    data = request.get_json()
    old_name = data.get('old_name')
    new_name = data.get('new_name')
    
    if not old_name or not new_name:
        return jsonify({"success": False, "message": "Old and new names required"}), 400
    
    if old_name == new_name:
        return jsonify({"success": False, "message": "New name must be different"}), 400
    
    count = 0
    # Find all books with this tag
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    
    for book in all_books:
        if book.keywords and old_name in book.keywords:
            keywords = list(book.keywords)
            keywords = [new_name if k == old_name else k for k in keywords]
            book.keywords = keywords
            count += 1
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='rename_tag',
        description=f"Renamed tag '{old_name}' to '{new_name}' affecting {count} books"
    )
    
    return jsonify({
        "success": True,
        "message": f"Tag renamed from '{old_name}' to '{new_name}'",
        "books_affected": count
    })


@admin_bp.route("/manage-tags/delete", methods=["POST"])
@admin_required
def delete_tag():
    """Delete a tag (remove from all books)"""
    data = request.get_json()
    tag_name = data.get('tag_name')
    
    if not tag_name:
        return jsonify({"success": False, "message": "Tag name required"}), 400
    
    count = 0
    # Find all books with this tag
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    
    for book in all_books:
        if book.keywords and tag_name in book.keywords:
            keywords = list(book.keywords)
            keywords = [k for k in keywords if k != tag_name]
            book.keywords = keywords
            count += 1
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='delete_tag',
        description=f"Deleted tag '{tag_name}' from {count} books"
    )
    
    return jsonify({
        "success": True,
        "message": f"Tag '{tag_name}' deleted from {count} books",
        "books_affected": count
    })


@admin_bp.route("/manage-tags/bulk-add", methods=["POST"])
@admin_required
def bulk_add_tags():
    """Add tags to multiple books"""
    data = request.get_json()
    book_ids = data.get('book_ids', [])
    tags = data.get('tags', [])
    
    if not book_ids or not tags:
        return jsonify({"success": False, "message": "Books and tags required"}), 400
    
    count = 0
    for book_id in book_ids:
        book = Book.query.get(book_id)
        if book:
            current_tags = set(book.keywords or [])
            current_tags.update(tags)
            book.keywords = list(current_tags)
            count += 1
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='bulk_add_tags',
        description=f"Added tags {tags} to {count} books"
    )
    
    return jsonify({
        "success": True,
        "message": f"Added tags to {count} books",
        "books_affected": count
    })


@admin_bp.route("/manage-tags/bulk-remove", methods=["POST"])
@admin_required
def bulk_remove_tags():
    """Remove tags from multiple books"""
    data = request.get_json()
    book_ids = data.get('book_ids', [])
    tags = data.get('tags', [])
    
    if not book_ids or not tags:
        return jsonify({"success": False, "message": "Books and tags required"}), 400
    
    count = 0
    for book_id in book_ids:
        book = Book.query.get(book_id)
        if book and book.keywords:
            current_tags = set(book.keywords)
            current_tags.difference_update(tags)
            book.keywords = list(current_tags)
            count += 1
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='bulk_remove_tags',
        description=f"Removed tags {tags} from {count} books"
    )
    
    return jsonify({
        "success": True,
        "message": f"Removed tags from {count} books",
        "books_affected": count
    })


@admin_bp.route("/api/tags/stats")
@admin_required
def tag_stats_api():
    """API endpoint for tag statistics"""
    # Get all books with tags
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    
    # Build tag cloud data
    tag_cloud = {}
    for book in all_books:
        if book.keywords:
            for tag in book.keywords:
                tag_cloud[tag] = tag_cloud.get(tag, 0) + 1
    
    tag_cloud = [{'tag': k, 'count': v} for k, v in sorted(tag_cloud.items(), key=lambda x: x[1], reverse=True)[:50]]
    
    # Tag growth over time (last 30 days)
    now = datetime.utcnow()
    growth = []
    for i in range(30):
        day = now - timedelta(days=i)
        next_day = day + timedelta(days=1)
        
        # Books added on this day
        day_books = [b for b in all_books if day <= b.created_at < next_day]
        
        # Unique tags from these books
        day_tags = set()
        for book in day_books:
            if book.keywords:
                day_tags.update(book.keywords)
        
        growth.append({
            'date': day.strftime('%Y-%m-%d'),
            'new_tags': len(day_tags)
        })
    
    # Books with most tags
    books_with_most_tags = sorted(
        [b for b in all_books if b.keywords],
        key=lambda x: len(x.keywords or []),
        reverse=True
    )[:10]
    
    return jsonify({
        'tag_cloud': tag_cloud,
        'growth': growth,
        'total_tags': len(tag_cloud),
        'books_with_tags': len(all_books),
        'books_with_most_tags': [{
            'id': b.id,
            'title': b.title,
            'tag_count': len(b.keywords or []),
            'tags': (b.keywords or [])[:10]
        } for b in books_with_most_tags]
    })


# ===================== PATRON MANAGEMENT =====================

@admin_bp.route("/patrons")
@admin_required
def manage_patrons():
    """Manage library patrons"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    filter_by = request.args.get('filter', 'all')
    search = request.args.get('search', '').strip()
    
    query = User.query.filter_by(is_deleted=False)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (User.username.ilike(search_term)) |
            (User.email.ilike(search_term)) |
            (User.full_name.ilike(search_term)) |
            (User.service_number.ilike(search_term))
        )
    
    if filter_by == 'pending':
        query = query.filter_by(approval_status='pending')
    elif filter_by == 'active':
        query = query.filter_by(membership_status='active', approval_status='approved')
    elif filter_by == 'suspended':
        query = query.filter_by(membership_status='suspended')
    elif filter_by == 'expired':
        expired_user_ids = [lc.user_id for lc in LibraryCard.query.all() 
                           if lc.is_expired()]
        query = query.filter(User.id.in_(expired_user_ids))
    elif filter_by == 'expiring_soon':
        thirty_days = datetime.utcnow() + timedelta(days=30)
        expiring_ids = []
        for lc in LibraryCard.query.all():
            if not lc.is_expired() and lc.expiry_date <= thirty_days:
                expiring_ids.append(lc.user_id)
        query = query.filter(User.id.in_(expiring_ids))
    elif filter_by == 'verified':
        query = query.filter_by(email_verified=True)
    elif filter_by == 'two_factor':
        query = query.filter_by(two_factor_enabled=True)
    elif filter_by == 'librarians':
        query = query.filter(User.role.in_(['admin', 'librarian']))
    
    total = query.count()
    patrons = query.order_by(User.created_at.desc())\
        .offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Get counts for filters
    counts = {
        'all': User.query.filter_by(is_deleted=False).count(),
        'pending': User.query.filter_by(approval_status='pending', is_deleted=False).count(),
        'active': User.query.filter_by(membership_status='active', approval_status='approved', is_deleted=False).count(),
        'suspended': User.query.filter_by(membership_status='suspended', is_deleted=False).count(),
        'expired': len([u for u in User.query.filter_by(is_deleted=False).all() if u.library_card and u.library_card.is_expired()]),
        'expiring_soon': len([u for u in User.query.filter_by(is_deleted=False).all() if u.library_card and 
                             not u.library_card.is_expired() and 
                             u.library_card.days_until_expiry() <= 30]),
        'verified': User.query.filter_by(email_verified=True, is_deleted=False).count(),
        'two_factor': User.query.filter_by(two_factor_enabled=True, is_deleted=False).count(),
        'librarians': User.query.filter(User.role.in_(['admin', 'librarian']), User.is_deleted==False).count(),
    }
    
    return render_template("admin/manage_patrons.html",
                         patrons=patrons,
                         counts=counts,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         current_filter=filter_by,
                         search=search)


@admin_bp.route("/patron/<int:user_id>/view")
@admin_required
def view_user(user_id):
    """View user details with enhanced information"""
    user = User.query.get_or_404(user_id)
    
    # Get user statistics
    total_borrowings = BorrowRecord.query.filter_by(user_id=user_id).count()
    current_borrowings = BorrowRecord.query.filter_by(user_id=user_id, status='borrowed').count()
    total_downloads = DownloadLog.query.filter_by(user_id=user_id).count()
    total_reviews = Review.query.filter_by(user_id=user_id).count()
    
    # Special requests statistics
    total_special_requests = SpecialRequest.query.filter_by(user_id=user_id).count()
    pending_special_requests = SpecialRequest.query.filter_by(user_id=user_id, status='pending').count()
    approved_special_requests = SpecialRequest.query.filter_by(user_id=user_id, status='approved').count()
    
    # Reading statistics
    total_reading_sessions = ReadingProgress.query.filter_by(user_id=user_id).count()
    total_bookmarks = Bookmark.query.filter_by(user_id=user_id).count()
    total_annotations = Annotation.query.filter_by(user_id=user_id).count()
    
    # Reading progress
    reading_progress = ReadingProgress.query.filter_by(user_id=user_id).order_by(
        ReadingProgress.last_accessed.desc()
    ).limit(10).all()
    
    # Recent activity
    recent_borrowings = BorrowRecord.query.filter_by(user_id=user_id)\
        .order_by(BorrowRecord.borrow_date.desc()).limit(5).all()
    
    recent_downloads = DownloadLog.query.filter_by(user_id=user_id)\
        .order_by(DownloadLog.timestamp.desc()).limit(5).all()
    
    recent_reading = ReadingProgress.query.filter_by(user_id=user_id)\
        .order_by(ReadingProgress.last_accessed.desc()).limit(5).all()
    
    recent_special_requests = SpecialRequest.query.filter_by(user_id=user_id)\
        .order_by(SpecialRequest.created_at.desc()).limit(5).all()
    
    # Circulation history
    circulation_history = CirculationRecord.query.filter_by(user_id=user_id)\
        .order_by(CirculationRecord.checkout_date.desc()).limit(10).all()
    
    # Fines
    unpaid_fines = Fine.query.filter_by(user_id=user_id, paid=False, waived=False).all()
    total_fines = sum(f.amount for f in unpaid_fines)
    
    # Library card info
    library_card = user.library_card
    card_status = None
    if library_card:
        card_status = {
            'number': library_card.card_number,
            'barcode': library_card.barcode,
            'expiry': library_card.expiry_date.strftime('%Y-%m-%d'),
            'days_left': library_card.days_until_expiry() if hasattr(library_card, 'days_until_expiry') else 0,
            'is_expired': library_card.is_expired(),
            'is_active': library_card.is_active
        }
    
    # Approval info
    approver = None
    if user.approved_by:
        approver = User.query.get(user.approved_by)
    
    # Wishlist
    wishlist = Wishlist.query.filter_by(user_id=user_id).all()
    
    # ===== NEW SECTIONS =====
    
    # Notifications
    notifications = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc()).limit(20).all()
    
    # Sessions
    sessions = UserSession.query.filter_by(user_id=user_id)\
        .order_by(UserSession.login_time.desc()).limit(10).all()
    
    return render_template("admin/view_user.html",
                         user=user,
                         total_borrowings=total_borrowings,
                         current_borrowings=current_borrowings,
                         total_downloads=total_downloads,
                         total_reviews=total_reviews,
                         total_special_requests=total_special_requests,
                         pending_special_requests=pending_special_requests,
                         approved_special_requests=approved_special_requests,
                         total_reading_sessions=total_reading_sessions,
                         total_bookmarks=total_bookmarks,
                         total_annotations=total_annotations,
                         reading_progress=reading_progress,
                         recent_borrowings=recent_borrowings,
                         recent_downloads=recent_downloads,
                         recent_reading=recent_reading,
                         recent_special_requests=recent_special_requests,
                         circulation_history=circulation_history,
                         unpaid_fines=unpaid_fines,
                         total_fines=total_fines,
                         library_card=card_status,
                         approver=approver,
                         wishlist=wishlist,
                         notifications=notifications,
                         sessions=sessions)


@admin_bp.route("/patron/<int:user_id>/card")
@admin_required
def view_patron_card(user_id):
    """View patron's library card"""
    user = User.query.get_or_404(user_id)
    
    if not user.library_card:
        flash("This patron doesn't have a library card.")
        return redirect(url_for('admin.view_user', user_id=user_id))
    
    return render_template("admin/patron_card.html", 
                         user=user, 
                         card=user.library_card,
                         now=datetime.utcnow())


@admin_bp.route("/patron/<int:user_id>/renew-card", methods=["POST"])
@admin_required
def renew_patron_card(user_id):
    """Renew patron's library card"""
    user = User.query.get_or_404(user_id)
    
    if not user.library_card:
        return jsonify({"success": False, "message": "No library card found"}), 404
    
    data = request.get_json()
    days = data.get('days', 365)
    
    old_expiry = user.library_card.expiry_date
    user.library_card.renew(days)
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='renew_card',
        description=f"Renewed library card for {user.username} for {days} days",
        metadata={'user_id': user.id, 'days': days, 'old_expiry': old_expiry.isoformat()}
    )
    
    # Send notification
    send_user_notification(
        user,
        "Library Card Renewed",
        f"Your library card has been renewed until {user.library_card.expiry_date.strftime('%Y-%m-%d')}",
        'success',
        'circulation'
    )
    
    return jsonify({
        "success": True,
        "message": f"Card renewed until {user.library_card.expiry_date.strftime('%Y-%m-%d')}",
        "new_expiry": user.library_card.expiry_date.strftime('%Y-%m-%d'),
        "days_until_expiry": user.library_card.days_until_expiry() if hasattr(user.library_card, 'days_until_expiry') else 0
    })


@admin_bp.route("/patron/<int:user_id>/suspend-card", methods=["POST"])
@admin_required
def suspend_patron_card(user_id):
    """Suspend patron's library card"""
    user = User.query.get_or_404(user_id)
    
    if not user.library_card:
        return jsonify({"success": False, "message": "No library card found"}), 404
    
    data = request.get_json()
    reason = data.get('reason', 'No reason provided')
    
    user.library_card.suspend(reason)
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='suspend_card',
        description=f"Suspended library card for {user.username}",
        metadata={'user_id': user.id, 'reason': reason}
    )
    
    # Send notification
    send_user_notification(
        user,
        "Library Card Suspended",
        f"Your library card has been suspended. Reason: {reason}",
        'warning',
        'circulation'
    )
    
    return jsonify({"success": True, "message": "Card suspended"})


@admin_bp.route("/patron/<int:user_id>/activate-card", methods=["POST"])
@admin_required
def activate_patron_card(user_id):
    """Activate patron's library card"""
    user = User.query.get_or_404(user_id)
    
    if not user.library_card:
        return jsonify({"success": False, "message": "No library card found"}), 404
    
    user.library_card.activate()
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='activate_card',
        description=f"Activated library card for {user.username}"
    )
    
    # Send notification
    send_user_notification(
        user,
        "Library Card Activated",
        "Your library card has been activated.",
        'success',
        'circulation'
    )
    
    return jsonify({"success": True, "message": "Card activated"})


@admin_bp.route("/patron/<int:user_id>/replace-card", methods=["POST"])
@admin_required
def replace_patron_card(user_id):
    """Replace lost/damaged library card"""
    user = User.query.get_or_404(user_id)
    
    if not user.library_card:
        return jsonify({"success": False, "message": "No library card found"}), 404
    
    data = request.get_json()
    reason = data.get('reason', 'lost')
    
    old_card = user.library_card
    old_number = old_card.card_number
    
    # Create new card
    new_card = LibraryCard(
        user_id=user.id,
        card_type=old_card.card_type,
        card_holder_name=user.full_name,
        expiry_date=datetime.utcnow() + timedelta(days=365)
    )
    
    # Deactivate old card
    if hasattr(old_card, 'replace'):
        old_card.replace(reason, new_card)
    else:
        old_card.is_active = False
        old_card.status = 'replaced'
    
    db.session.add(new_card)
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='replace_card',
        description=f"Replaced library card for {user.username} (old: {old_number}, new: {new_card.card_number})",
        metadata={'user_id': user.id, 'reason': reason}
    )
    
    # Send notification
    send_user_notification(
        user,
        "Library Card Replaced",
        f"Your library card has been replaced. New card number: {new_card.card_number}",
        'info',
        'circulation'
    )
    
    return jsonify({
        "success": True,
        "message": "Card replaced successfully",
        "new_card_number": new_card.card_number,
        "new_barcode": new_card.barcode
    })


@admin_bp.route("/patrons/expiring")
@admin_required
def expiring_patrons():
    """View patrons with expiring cards"""
    thirty_days = datetime.utcnow() + timedelta(days=30)
    
    expiring_cards = []
    for card in LibraryCard.query.filter(LibraryCard.is_active == True).all():
        if not card.is_expired() and card.expiry_date <= thirty_days:
            expiring_cards.append({
                'card': card,
                'user': card.user,
                'days_left': card.days_until_expiry() if hasattr(card, 'days_until_expiry') else 0,
                'expiry_date': card.expiry_date.strftime('%Y-%m-%d')
            })
    
    # Sort by days left
    expiring_cards.sort(key=lambda x: x['days_left'])
    
    return render_template("admin/expiring_patrons.html",
                         expiring_cards=expiring_cards,
                         now=datetime.utcnow(),
                         thirty_days=thirty_days)


@admin_bp.route("/api/patron/<int:user_id>/card-status")
@admin_required
def patron_card_status(user_id):
    """API endpoint to get patron card status"""
    user = User.query.get_or_404(user_id)
    
    if not user.library_card:
        return jsonify({"has_card": False})
    
    card = user.library_card
    return jsonify({
        "has_card": True,
        "card_number": card.card_number,
        "barcode": card.barcode,
        "issued_date": card.issued_date.strftime('%Y-%m-%d'),
        "expiry_date": card.expiry_date.strftime('%Y-%m-%d'),
        "days_until_expiry": card.days_until_expiry() if hasattr(card, 'days_until_expiry') else 0,
        "is_expired": card.is_expired(),
        "is_active": card.is_active,
        "status": card.status,
        "renewal_count": card.renewal_count
    })


@admin_bp.route("/patrons/export")
@admin_required
def export_patrons():
    """Export patrons to CSV"""
    import csv
    from io import StringIO
    
    # Get filter params
    filter_by = request.args.get('filter', 'all')
    
    query = User.query.filter_by(is_deleted=False)
    
    if filter_by == 'active':
        query = query.filter_by(membership_status='active', approval_status='approved')
    elif filter_by == 'pending':
        query = query.filter_by(approval_status='pending')
    elif filter_by == 'suspended':
        query = query.filter_by(membership_status='suspended')
    
    patrons = query.order_by(User.created_at.desc()).all()
    
    # Create CSV
    si = StringIO()
    cw = csv.writer(si)
    
    # Headers
    cw.writerow([
        'ID', 'Username', 'Full Name', 'Email', 'Phone', 'Service Number',
        'Rank', 'Unit', 'Role', 'Membership Status', 'Approval Status',
        'Security Clearance', 'Email Verified', '2FA Enabled',
        'Total Borrowed', 'Total Downloads', 'Created At'
    ])
    
    # Data
    for p in patrons:
        cw.writerow([
            p.id,
            p.username,
            p.full_name or '',
            p.email,
            p.phone or '',
            p.service_number or '',
            p.rank or '',
            p.unit or '',
            p.role,
            p.membership_status,
            p.approval_status,
            p.security_clearance,
            'Yes' if p.email_verified else 'No',
            'Yes' if p.two_factor_enabled else 'No',
            p.total_books_borrowed,
            p.total_downloads,
            p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else ''
        ])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=patrons.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output


# ===================== WORKFLOW DASHBOARD =====================

@admin_bp.route("/workflow")
@admin_required
def workflow_dashboard():
    """Main workflow dashboard"""
    now = datetime.utcnow()
    
    # Acquisition stats
    pending_requests = AcquisitionRequest.query.filter_by(status='pending').count()
    approved_requests = AcquisitionRequest.query.filter_by(status='approved').count()
    ordered_requests = AcquisitionRequest.query.filter_by(status='ordered').count()
    received_requests = AcquisitionRequest.query.filter_by(status='received').count()
    total_orders = PurchaseOrder.query.count()
    
    # Cataloging stats
    pending_cataloging = CatalogingQueue.query.filter_by(status='pending').count()
    in_progress_cataloging = CatalogingQueue.query.filter_by(status='in_progress').count()
    completed_cataloging = CatalogingQueue.query.filter_by(status='completed').count()
    
    # Circulation stats
    active_checkouts = CirculationRecord.query.filter_by(status='active').count()
    overdue_items = CirculationRecord.query.filter(
        CirculationRecord.status == 'active',
        CirculationRecord.due_date < datetime.utcnow()
    ).count()
    active_reservations = Reservation.query.filter_by(status='active').count()
    
    # Totals
    total_books = Book.query.count()
    total_users = User.query.count()
    total_fines = db.session.query(db.func.sum(Fine.amount)).filter_by(paid=False).scalar() or 0
    total_copies = ItemCopy.query.count()
    available_copies = ItemCopy.query.filter_by(status='available').count()
    
    # Recent activity
    recent_activities = []
    
    # Recent acquisitions
    recent_reqs = AcquisitionRequest.query.order_by(AcquisitionRequest.request_date.desc()).limit(3).all()
    for req in recent_reqs:
        recent_activities.append({
            'type': 'acquisition',
            'description': f"New acquisition request: {req.title}",
            'time': req.request_date.strftime('%H:%M, %d %b'),
            'status': req.status,
            'user': req.requester.username if req.requester else None
        })
    
    # Recent cataloging
    recent_cat = CatalogingQueue.query.filter(CatalogingQueue.completed_at.isnot(None))\
        .order_by(CatalogingQueue.completed_at.desc()).limit(3).all()
    for cat in recent_cat:
        recent_activities.append({
            'type': 'cataloging',
            'description': f"Cataloged: {cat.book.title if cat.book else 'New book'}",
            'time': cat.completed_at.strftime('%H:%M, %d %b'),
            'status': 'completed',
            'user': cat.cataloger.username if cat.cataloger else None
        })
    
    # Recent circulations
    recent_circ = CirculationRecord.query.order_by(CirculationRecord.checkout_date.desc()).limit(3).all()
    for circ in recent_circ:
        # Access relationships safely
        book_title = circ.item_copy.book.title if circ.item_copy and circ.item_copy.book else "Unknown"
        patron_name = circ.patron.full_name if circ.patron else "Unknown"
        operator_name = circ.checkout_operator.username if circ.checkout_operator else None
        
        recent_activities.append({
            'type': 'circulation',
            'description': f"Checked out: {book_title} to {patron_name}",
            'time': circ.checkout_date.strftime('%H:%M, %d %b'),
            'status': circ.status,
            'user': operator_name
        })
    
    # Recent card renewals
    recent_renewals = LibraryCard.query.order_by(LibraryCard.last_renewed.desc()).limit(3).all()
    for renewal in recent_renewals:
        if renewal.last_renewed:
            recent_activities.append({
                'type': 'renewal',
                'description': f"Card renewed for {renewal.user.full_name or renewal.user.username}",
                'time': renewal.last_renewed.strftime('%H:%M, %d %b'),
                'status': 'completed',
                'user': None
            })
    
    # Sort by time
    recent_activities.sort(key=lambda x: x['time'], reverse=True)
    
    return render_template("admin/workflow_dashboard.html",
                         pending_requests=pending_requests,
                         approved_requests=approved_requests,
                         ordered_requests=ordered_requests,
                         received_requests=received_requests,
                         total_orders=total_orders,
                         pending_cataloging=pending_cataloging,
                         in_progress_cataloging=in_progress_cataloging,
                         completed_cataloging=completed_cataloging,
                         active_checkouts=active_checkouts,
                         overdue_items=overdue_items,
                         active_reservations=active_reservations,
                         total_books=total_books,
                         total_users=total_users,
                         total_fines=total_fines,
                         total_copies=total_copies,
                         available_copies=available_copies,
                         recent_activities=recent_activities[:10],
                         now=now)


# ===================== CATALOGING PAGE =====================

@admin_bp.route("/cataloging", methods=["GET", "POST"])
@admin_required
def cataloging():
    """Cataloging page - Upload new books and view queue"""
    if request.method == "POST":
        # DEBUG: Print form data to verify CSRF token is received
        print("="*50)
        print("FORM DATA RECEIVED:")
        for key in request.form.keys():
            if key == 'csrf_token':
                print(f"  {key}: {request.form.get(key)[:30]}... (truncated)")
            else:
                print(f"  {key}: {request.form.get(key)}")
        print("FILES RECEIVED:")
        for key in request.files.keys():
            print(f"  {key}: {request.files.get(key).filename if request.files.get(key) else 'None'}")
        print("="*50)
        
        # Handle file upload
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("❌ No file selected.")
            return redirect(request.url)

        if not allowed_pdf(file.filename):
            flash("❌ Only PDF, EPUB, and MOBI files are allowed.")
            return redirect(request.url)

        # Securely upload file
        file_info, error = secure_file_upload(file, 'books')
        if error:
            flash(f"❌ {error}")
            return redirect(request.url)

        # Handle cover image
        cover_info = None
        cover_file = request.files.get('cover_image')
        if cover_file and cover_file.filename:
            if allowed_image(cover_file.filename):
                cover_info, error = secure_file_upload(cover_file, 'covers')
                if error:
                    flash(f"❌ {error}")
                    return redirect(request.url)
            else:
                flash("❌ Invalid image format. Allowed: PNG, JPG, JPEG, GIF, WEBP")
                return redirect(request.url)

        # Get form data
        has_digital = 'has_digital' in request.form
        has_physical = 'has_physical' in request.form
        
        # Parse keywords/tags
        keywords = [k.strip() for k in request.form.get('keywords', '').split(',') if k.strip()]

        # Create book record
        book = Book(
            title=request.form["title"],
            author=request.form["author"],
            category=request.form.get("category"),
            description=request.form.get("description"),
            isbn=request.form.get("isbn"),
            publisher=request.form.get("publisher"),
            published_year=request.form.get("published_year", type=int),
            language=request.form.get("language", "English"),
            pages=request.form.get("pages", type=int),
            keywords=keywords,
            has_digital=has_digital,
            has_physical=has_physical,
            filename=file_info['filename'] if has_digital and file_info else None,
            file_size=file_info['size'] if has_digital and file_info else None,
            mime_type=file_info['mime_type'] if has_digital and file_info else None,
            file_hash=file_info['hash'] if has_digital and file_info else None,
            cover_image=cover_info['filename'] if cover_info else None,
            total_copies=request.form.get("total_copies", 0, type=int) if has_physical else 0,
            available_copies=request.form.get("total_copies", 0, type=int) if has_physical else 0,
            shelf_location=request.form.get("shelf_location") if has_physical else None,
            is_featured='is_featured' in request.form,
            is_new_arrival='is_new_arrival' in request.form,
            created_by_id=session['user_id']  # This is for Book model - it HAS this field
        )

        db.session.add(book)
        db.session.flush()
        
        # Create item copies if physical
        if has_physical and book.total_copies > 0:
            for i in range(book.total_copies):
                copy = ItemCopy(
                    book_id=book.id,
                    copy_number=i+1,
                    shelf_location=book.shelf_location,
                    status='available',
                    acquisition_date=datetime.utcnow()
                )
                db.session.add(copy)
        
        # Add to cataloging queue - FIXED: removed created_by_id (DOESN'T EXIST in CatalogingQueue)
        queue = CatalogingQueue(
            book_id=book.id,
            status='pending',
            cataloger_notes=f"Added via cataloging page by {session.get('username')}"
            # created_by_id REMOVED - this field doesn't exist in CatalogingQueue model
        )
        db.session.add(queue)
        
        db.session.commit()
        
        # Trigger Solr indexing
        if has_digital:
            trigger_solr_index(book.id, delay=True)
        
        log_admin_activity(
            user_id=session['user_id'],
            action='upload',
            description=f"Uploaded book: {book.title}",
            book_id=book.id
        )

        flash("✅ Book uploaded successfully and added to cataloging queue!")
        return redirect(url_for('admin.cataloging_queue'))

    # GET request - show cataloging upload form (NOT the queue)
    # Get categories for dropdown
    categories = db.session.query(Book.category).distinct().order_by(Book.category).all()
    
    # Get popular tags for suggestions
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    tag_counts = {}
    for b in all_books:
        if b.keywords:
            for tag in b.keywords:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    
    return render_template("admin/cataloging.html",
                         categories=categories,
                         popular_tags=popular_tags)

# ===================== ACQUISITION MANAGEMENT =====================

@admin_bp.route("/acquisition/requests")
@admin_required
def acquisition_requests():
    """View acquisition requests"""
    status = request.args.get('status', 'pending')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = AcquisitionRequest.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    # Counts for stats
    counts = {
        'pending': AcquisitionRequest.query.filter_by(status='pending').count(),
        'approved': AcquisitionRequest.query.filter_by(status='approved').count(),
        'ordered': AcquisitionRequest.query.filter_by(status='ordered').count(),
        'received': AcquisitionRequest.query.filter_by(status='received').count(),
        'rejected': AcquisitionRequest.query.filter_by(status='rejected').count()
    }
    
    total = query.count()
    requests = query.order_by(AcquisitionRequest.request_date.desc())\
        .offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/acquisition_requests.html",
                         requests=requests,
                         counts=counts,
                         current_status=status,
                         page=page,
                         total_pages=total_pages)


@admin_bp.route("/acquisition/new", methods=["GET", "POST"])
@admin_required
def new_acquisition_request():
    """Create new acquisition request"""
    if request.method == "POST":
        req = AcquisitionRequest(
            title=request.form['title'],
            author=request.form['author'],
            isbn=request.form.get('isbn'),
            publisher=request.form.get('publisher'),
            publication_year=request.form.get('publication_year', type=int),
            requested_by=session['user_id'],
            justification=request.form.get('justification'),
            priority=request.form.get('priority', 'medium'),
            material_type=request.form.get('material_type', 'book'),
            format_type=request.form.get('format_type', 'physical'),
            estimated_cost=request.form.get('estimated_cost', type=float),
            budget_code=request.form.get('budget_code')
        )
        db.session.add(req)
        db.session.commit()
        
        log_admin_activity(session['user_id'], 'acquisition_request', 
                          description=f"Created acquisition request: {req.title}")
        
        flash('✅ Acquisition request submitted successfully!')
        return redirect(url_for('admin.acquisition_requests'))
    
    return render_template("admin/new_acquisition_request.html")


@admin_bp.route("/acquisition/<int:request_id>/review", methods=["POST"])
@admin_required
def review_acquisition_request(request_id):
    """Approve or reject acquisition request"""
    req = AcquisitionRequest.query.get_or_404(request_id)
    data = request.get_json()
    
    action = data.get('action')
    notes = data.get('notes', '')
    
    if action == 'approve':
        req.status = 'approved'
    elif action == 'reject':
        req.status = 'rejected'
    else:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    
    req.reviewed_by = session['user_id']
    req.reviewed_at = datetime.utcnow()
    req.review_notes = notes
    
    db.session.commit()
    
    log_admin_activity(session['user_id'], f'acquisition_{action}', 
                      description=f"{action}d request for {req.title}")
    
    return jsonify({"success": True, "message": f"Request {action}d"})


@admin_bp.route("/acquisition/<int:request_id>/receive", methods=["POST"])
@admin_required
def receive_acquisition(request_id):
    """Mark acquisition request as received"""
    req = AcquisitionRequest.query.get_or_404(request_id)
    req.status = 'received'
    req.reviewed_by = session['user_id']
    req.reviewed_at = datetime.utcnow()
    
    # Create cataloging queue entry - FIXED: removed created_by_id
    queue = CatalogingQueue(
        status='pending',
        cataloger_notes=f"From acquisition request #{req.id}"
        # No created_by_id - this field doesn't exist in CatalogingQueue model
    )
    db.session.add(queue)
    
    db.session.commit()
    
    return jsonify({"success": True, "message": "Item marked as received"})


# ===================== PURCHASE ORDER MANAGEMENT =====================

@admin_bp.route("/purchase-orders")
@admin_required
def purchase_orders():
    """View purchase orders"""
    status = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = PurchaseOrder.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    purchase_orders = query.order_by(PurchaseOrder.order_date.desc())\
        .offset((page-1)*per_page).limit(per_page).all()
    
    return render_template("admin/purchase_orders.html",
                         purchase_orders=purchase_orders,
                         current_status=status)


@admin_bp.route("/purchase-order/new", methods=["GET", "POST"])
@admin_required
def new_purchase_order():
    """Create new purchase order"""
    if request.method == "POST":
        # Generate PO number
        po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        
        po = PurchaseOrder(
            po_number=po_number,
            vendor_name=request.form['vendor_name'],
            vendor_contact=request.form.get('vendor_contact'),
            vendor_email=request.form.get('vendor_email'),
            expected_delivery=datetime.strptime(request.form['expected_delivery'], '%Y-%m-%d') if request.form.get('expected_delivery') else None,
            subtotal=float(request.form.get('subtotal', 0)),
            tax=float(request.form.get('tax', 0)),
            shipping=float(request.form.get('shipping', 0)),
            total_cost=float(request.form.get('total_cost', 0)),
            notes=request.form.get('notes'),
            created_by=session['user_id'],
            status='draft'
        )
        db.session.add(po)
        db.session.flush()
        
        # Add items
        titles = request.form.getlist('item_title[]')
        authors = request.form.getlist('item_author[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')
        
        for i in range(len(titles)):
            if titles[i]:
                item = PurchaseOrderItem(
                    po_id=po.id,
                    title=titles[i],
                    author=authors[i] if i < len(authors) else None,
                    quantity=int(quantities[i]) if i < len(quantities) else 1,
                    unit_price=float(prices[i]) if i < len(prices) else 0,
                    total_price=int(quantities[i]) * float(prices[i]) if i < len(quantities) and i < len(prices) else 0
                )
                db.session.add(item)
        
        db.session.commit()
        
        log_admin_activity(session['user_id'], 'purchase_order', 
                          description=f"Created purchase order: {po_number}")
        
        flash('✅ Purchase order created successfully!')
        return redirect(url_for('admin.purchase_orders'))
    
    # Get approved acquisition requests for pre-filling
    approved_requests = AcquisitionRequest.query.filter_by(status='approved').all()
    
    return render_template("admin/new_purchase_order.html",
                         approved_requests=approved_requests)


@admin_bp.route("/purchase-order/<int:po_id>/send", methods=["POST"])
@admin_required
def send_purchase_order(po_id):
    """Mark purchase order as sent"""
    po = PurchaseOrder.query.get_or_404(po_id)
    po.status = 'sent'
    db.session.commit()
    
    log_admin_activity(session['user_id'], 'purchase_order_send', 
                      description=f"Sent purchase order: {po.po_number}")
    
    return jsonify({"success": True, "message": "Purchase order marked as sent"})


@admin_bp.route("/purchase-order/<int:po_id>/receive", methods=["GET", "POST"])
@admin_required
def receive_purchase_order(po_id):
    """Receive items from purchase order"""
    po = PurchaseOrder.query.get_or_404(po_id)
    
    if request.method == "POST":
        po.actual_delivery = datetime.utcnow()
        po.status = 'received'
        
        # Update received quantities
        for item in po.items:
            qty_received = int(request.form.get(f'qty_received_{item.id}', 0))
            item.quantity_received = qty_received
            item.received_date = datetime.utcnow()
            item.received_by = session['user_id']
            
            # Create cataloging queue entries for each received item - FIXED
            if qty_received > 0:
                for _ in range(qty_received):
                    queue = CatalogingQueue(
                        po_item_id=item.id,
                        status='pending',
                        cataloger_notes=f"From PO: {po.po_number}"
                        # No created_by_id - this field doesn't exist in CatalogingQueue model
                    )
                    db.session.add(queue)
        
        db.session.commit()
        
        log_admin_activity(session['user_id'], 'purchase_order_receive', 
                          description=f"Received purchase order: {po.po_number}")
        
        flash('✅ Purchase order received successfully!')
        return redirect(url_for('admin.purchase_orders'))
    
    return render_template("admin/receive_purchase_order.html", po=po)


@admin_bp.route("/purchase-order/<int:po_id>/view")
@admin_required
def view_purchase_order(po_id):
    """View purchase order details"""
    po = PurchaseOrder.query.get_or_404(po_id)
    return render_template("admin/view_purchase_order.html", po=po)


# ===================== CATALOGING MANAGEMENT =====================

@admin_bp.route("/cataloging-queue")
@admin_required
def cataloging_queue():
    """View and manage cataloging queue"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    status = request.args.get('status', 'pending')
    
    query = CatalogingQueue.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    total = query.count()
    queue_items = query.order_by(CatalogingQueue.created_at.asc())\
        .offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Get counts for each status
    counts = {
        'pending': CatalogingQueue.query.filter_by(status='pending').count(),
        'in_progress': CatalogingQueue.query.filter_by(status='in_progress').count(),
        'completed': CatalogingQueue.query.filter_by(status='completed').count()
    }
    
    # Get available catalogers (users with cataloging permission)
    catalogers = User.query.filter_by(role='admin').all()
    
    return render_template("admin/cataloging_queue.html",
                         queue_items=queue_items,
                         counts=counts,
                         current_status=status,
                         catalogers=catalogers,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/cataloging/<int:queue_id>/assign", methods=["POST"])
@admin_required
def assign_cataloging(queue_id):
    """Assign cataloging task to a cataloger"""
    queue_item = CatalogingQueue.query.get_or_404(queue_id)
    data = request.get_json()
    
    queue_item.assigned_to = data.get('cataloger_id')
    queue_item.assigned_date = datetime.utcnow()
    queue_item.status = 'in_progress'
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='assign_cataloging',
        description=f"Assigned cataloging task #{queue_id} to user {queue_item.assigned_to}"
    )
    
    return jsonify({"success": True, "message": "Task assigned successfully"})


@admin_bp.route("/cataloging/<int:queue_id>/complete", methods=["POST"])
@admin_required
def complete_cataloging(queue_id):
    """Mark cataloging task as complete"""
    queue_item = CatalogingQueue.query.get_or_404(queue_id)
    data = request.get_json()
    
    # Update cataloging metadata
    queue_item.dewey_decimal = data.get('dewey_decimal')
    queue_item.library_of_congress = data.get('library_of_congress')
    queue_item.subjects = data.get('subjects')
    queue_item.cataloger_notes = data.get('notes')
    queue_item.status = 'completed'
    queue_item.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='complete_cataloging',
        description=f"Completed cataloging for item #{queue_item.id}"
    )
    
    return jsonify({"success": True, "message": "Cataloging completed"})


@admin_bp.route("/cataloging/stats")
@admin_required
def cataloging_stats():
    """View cataloging statistics"""
    # Items cataloged per day for last 30 days
    now = datetime.utcnow()
    daily_stats = []
    for i in range(30):
        day = now - timedelta(days=i)
        next_day = day + timedelta(days=1)
        count = CatalogingQueue.query.filter(
            CatalogingQueue.completed_at >= day,
            CatalogingQueue.completed_at < next_day
        ).count()
        daily_stats.append({
            'date': day.strftime('%Y-%m-%d'),
            'count': count
        })
    
    # Stats by cataloger
    cataloger_stats = db.session.query(
        User.username, func.count(CatalogingQueue.id).label('count')
    ).join(CatalogingQueue, CatalogingQueue.assigned_to == User.id)\
     .filter(CatalogingQueue.status == 'completed')\
     .group_by(User.id)\
     .order_by(desc('count')).all()
    
    # Average time to catalog
    avg_time = db.session.query(
        func.avg(func.julianday(CatalogingQueue.completed_at) - func.julianday(CatalogingQueue.created_at)) * 24
    ).filter(CatalogingQueue.completed_at.isnot(None)).scalar() or 0
    
    return render_template("admin/cataloging_stats.html",
                         daily_stats=daily_stats,
                         cataloger_stats=cataloger_stats,
                         avg_time=round(avg_time, 1))


# ===================== CIRCULATION MANAGEMENT =====================

@admin_bp.route("/circulation")
@admin_required
def circulation():
    """Manage circulation - FIXED with explicit joins"""
    filter_by = request.args.get('filter', 'active')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # FIXED: Explicit join conditions to avoid ambiguous foreign keys
    query = CirculationRecord.query.join(
        ItemCopy, 
        CirculationRecord.copy_id == ItemCopy.id
    ).join(
        Book, 
        ItemCopy.book_id == Book.id
    )
    
    if filter_by == 'active':
        query = query.filter(CirculationRecord.status == 'active')
    elif filter_by == 'overdue':
        query = query.filter(
            CirculationRecord.status == 'active',
            CirculationRecord.due_date < datetime.utcnow()
        )
    elif filter_by == 'history':
        query = query.filter(CirculationRecord.status == 'returned')
    
    total = query.count()
    transactions = query.order_by(CirculationRecord.checkout_date.desc())\
        .offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Stats
    stats = {
        'active': CirculationRecord.query.filter_by(status='active').count(),
        'overdue': CirculationRecord.query.filter(
            CirculationRecord.status == 'active',
            CirculationRecord.due_date < datetime.utcnow()
        ).count(),
        'reservations': Reservation.query.filter_by(status='active').count(),
        'fines': db.session.query(db.func.sum(Fine.amount)).filter_by(paid=False).scalar() or 0
    }
    
    return render_template("admin/circulation.html",
                         transactions=transactions,
                         stats=stats,
                         current_filter=filter_by,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/checkout", methods=["GET", "POST"])
@admin_required
def checkout():
    """Enhanced checkout with barcode scanning"""
    if request.method == "POST":
        data = request.get_json()
        
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        patron_id = data.get('patron_id')
        barcodes = data.get('barcodes', [])
        due_date = datetime.fromisoformat(data.get('due_date').replace('Z', '+00:00'))
        
        if not patron_id:
            return jsonify({"success": False, "message": "Patron ID required"}), 400
        
        if not barcodes:
            return jsonify({"success": False, "message": "No barcodes provided"}), 400
        
        # Get patron
        patron = User.query.get(patron_id)
        if not patron:
            return jsonify({"success": False, "message": "Patron not found"}), 404
        
        # Check if patron's card is valid
        if not patron.library_card:
            return jsonify({"success": False, "message": "Patron has no library card"}), 400
        
        if patron.library_card.is_expired():
            return jsonify({"success": False, "message": "Patron's library card has expired"}), 400
        
        if not patron.library_card.is_active:
            return jsonify({"success": False, "message": "Patron's library card is not active"}), 400
        
        # Check patron's borrowing limit
        current_borrowings = CirculationRecord.query.filter_by(
            user_id=patron_id,
            status='active'
        ).count()
        
        max_borrowings = 5
        try:
            max_borrowings = SystemSetting.get('max_borrowings', 5)
        except:
            pass
        
        if current_borrowings >= max_borrowings:
            return jsonify({
                "success": False, 
                "message": f"Patron has reached maximum borrowing limit ({max_borrowings})"
            }), 400
        
        successful = []
        failed = []
        
        for barcode in barcodes:
            # Find copy by barcode
            copy = ItemCopy.query.filter_by(barcode=barcode).first()
            
            if not copy:
                failed.append({"barcode": barcode, "reason": "Copy not found"})
                continue
            
            if copy.status != 'available':
                failed.append({"barcode": barcode, "reason": f"Copy is {copy.status}"})
                continue
            
            if copy.is_reference_only:
                failed.append({"barcode": barcode, "reason": "Reference copy cannot be borrowed"})
                continue
            
            # Check if book requires special approval
            if copy.book.requires_special_request:
                has_approval = SpecialRequest.query.filter_by(
                    user_id=patron_id,
                    book_id=copy.book_id,
                    status='approved'
                ).first()
                
                if not has_approval and patron.security_clearance != 'top_secret':
                    failed.append({"barcode": barcode, "reason": "Special approval required"})
                    continue
            
            # Check security clearance
            if copy.book.security_classification:
                required_level = copy.book.minimum_clearance or 'basic'
                if not patron.has_clearance(required_level):
                    failed.append({
                        "barcode": barcode, 
                        "reason": f"Security clearance {required_level} required"
                    })
                    continue
            
            # Create circulation record
            circulation = CirculationRecord(
                copy_id=copy.id,
                user_id=patron_id,
                due_date=due_date,
                checkout_staff=session['user_id'],
                status='active'
            )
            db.session.add(circulation)
            
            # Update copy status
            copy.status = 'checked_out'
            copy.current_circulation_id = circulation.id
            copy.total_checkouts += 1
            copy.last_checkout = datetime.utcnow()
            
            # Update book stats
            copy.book.available_copies -= 1
            copy.book.borrow_count += 1
            
            # Update patron stats
            patron.total_books_borrowed += 1
            
            successful.append({
                "barcode": barcode,
                "title": copy.book.title,
                "due_date": due_date.strftime('%Y-%m-%d'),
                "circulation_id": circulation.id
            })
        
        db.session.commit()
        
        log_admin_activity(session['user_id'], 'checkout', 
                          description=f"Checked out {len(successful)} books")
        
        return jsonify({
            "success": True,
            "message": f"Checked out {len(successful)} books",
            "successful": successful,
            "failed": failed
        })
    
    # GET request - show checkout form
    return render_template("admin/checkout.html")


@admin_bp.route("/checkin", methods=["GET", "POST"])
@admin_required
def checkin():
    """Enhanced checkin with barcode scanning"""
    if request.method == "POST":
        data = request.get_json()
        
        barcode = data.get('barcode')
        
        if not barcode:
            return jsonify({"success": False, "message": "No barcode provided"}), 400
        
        # Find copy by barcode
        copy = ItemCopy.query.filter_by(barcode=barcode).first()
        
        if not copy:
            return jsonify({"success": False, "message": "Item not found"}), 404
        
        # Find active circulation
        circulation = CirculationRecord.query.filter_by(
            copy_id=copy.id,
            status='active'
        ).first()
        
        if not circulation:
            return jsonify({"success": False, "message": "Item is not checked out"}), 400
        
        # Process checkin
        circulation.return_date = datetime.utcnow()
        circulation.return_staff = session['user_id']
        circulation.status = 'returned'
        
        # Calculate fine if overdue
        fine_amount = circulation.calculate_fine()
        if fine_amount > 0:
            fine = Fine(
                circulation_id=circulation.id,
                user_id=circulation.user_id,
                amount=fine_amount,
                reason='overdue'
            )
            db.session.add(fine)
            circulation.fine_amount = fine_amount
        
        # Update copy status
        copy.status = 'available'
        copy.current_circulation_id = None
        copy.last_return = datetime.utcnow()
        
        # Update book stats
        copy.book.available_copies += 1
        
        # Check if there's a reservation for this book
        next_reservation = Reservation.query.filter_by(
            book_id=copy.book_id,
            status='active'
        ).order_by(Reservation.position).first()
        
        if next_reservation:
            copy.status = 'reserved'
            copy.book.reserved_copies += 1
            
            # Notify the patron
            send_user_notification(
                next_reservation.user,
                "Book Available for Pickup",
                f"The book you reserved, '{copy.book.title}', is now available. Please pick it up within 3 days.",
                'success',
                'reservation',
                url_for('books.book_details', book_id=copy.book_id)
            )
        
        db.session.commit()
        
        log_admin_activity(session['user_id'], 'checkin', 
                          description=f"Checked in: {copy.book.title}")
        
        return jsonify({
            "success": True,
            "message": "Item checked in successfully",
            "book_title": copy.book.title,
            "patron_name": circulation.patron.full_name if circulation.patron else None,
            "due_date": circulation.due_date.strftime('%Y-%m-%d'),
            "return_date": circulation.return_date.strftime('%Y-%m-%d'),
            "fine": fine_amount,
            "has_reservation": next_reservation is not None
        })
    
    return render_template("admin/checkin.html")


@admin_bp.route("/circulation/<int:circ_id>/renew", methods=["POST"])
@admin_required
def renew_circulation(circ_id):
    """Renew a checked out item"""
    circulation = CirculationRecord.query.get_or_404(circ_id)
    
    if circulation.status != 'active':
        return jsonify({"success": False, "message": "Item is not active"}), 400
    
    if not circulation.can_renew():
        return jsonify({"success": False, "message": "Item cannot be renewed"}), 400
    
    circulation.renew()
    db.session.commit()
    
    log_admin_activity(session['user_id'], 'renew', 
                      description=f"Renewed item for {circulation.patron.username}")
    
    return jsonify({"success": True, "message": "Item renewed successfully"})


# ===================== RESERVATION MANAGEMENT =====================

@admin_bp.route("/reservations")
@admin_required
def reservations():
    """Manage reservations"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    reservations = Reservation.query.order_by(Reservation.reservation_date.asc())\
        .offset((page-1)*per_page).limit(per_page).all()
    
    total = Reservation.query.count()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/reservations.html",
                         reservations=reservations,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/reservation/<int:res_id>/cancel", methods=["POST"])
@admin_required
def cancel_reservation(res_id):
    """Cancel a reservation"""
    reservation = Reservation.query.get_or_404(res_id)
    reservation.status = 'cancelled'
    db.session.commit()
    
    return jsonify({"success": True, "message": "Reservation cancelled"})


@admin_bp.route("/reservation/<int:res_id>/fulfill", methods=["POST"])
@admin_required
def fulfill_reservation(res_id):
    """Mark reservation as fulfilled (when book is checked out)"""
    reservation = Reservation.query.get_or_404(res_id)
    reservation.status = 'fulfilled'
    reservation.fulfilled_date = datetime.utcnow()
    db.session.commit()
    
    return jsonify({"success": True, "message": "Reservation fulfilled"})


# ===================== FINE MANAGEMENT =====================

@admin_bp.route("/fines")
@admin_required
def fines():
    """Manage fines"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    status = request.args.get('status', 'unpaid')
    
    query = Fine.query
    if status == 'unpaid':
        query = query.filter_by(paid=False, waived=False)
    elif status == 'paid':
        query = query.filter_by(paid=True)
    elif status == 'waived':
        query = query.filter_by(waived=True)
    
    total = query.count()
    fines = query.order_by(Fine.assessed_date.desc())\
        .offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Summary
    total_unpaid = db.session.query(db.func.sum(Fine.amount)).filter_by(paid=False, waived=False).scalar() or 0
    total_paid = db.session.query(db.func.sum(Fine.amount)).filter_by(paid=True).scalar() or 0
    
    return render_template("admin/fines.html",
                         fines=fines,
                         total_unpaid=total_unpaid,
                         total_paid=total_paid,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         current_status=status)


@admin_bp.route("/fine/<int:fine_id>/pay", methods=["POST"])
@admin_required
def pay_fine(fine_id):
    """Mark fine as paid"""
    fine = Fine.query.get_or_404(fine_id)
    data = request.get_json()
    
    fine.paid = True
    fine.paid_date = datetime.utcnow()
    fine.payment_method = data.get('payment_method', 'cash')
    fine.transaction_id = data.get('transaction_id')
    
    db.session.commit()
    
    return jsonify({"success": True, "message": "Fine marked as paid"})


@admin_bp.route("/fine/<int:fine_id>/waive", methods=["POST"])
@admin_required
def waive_fine(fine_id):
    """Waive a fine"""
    fine = Fine.query.get_or_404(fine_id)
    data = request.get_json()
    
    fine.waived = True
    fine.waived_by = session['user_id']
    fine.waived_date = datetime.utcnow()
    fine.waiver_reason = data.get('reason', 'Admin discretion')
    
    db.session.commit()
    
    log_admin_activity(session['user_id'], 'waive_fine', 
                      description=f"Waived fine #{fine_id}")
    
    return jsonify({"success": True, "message": "Fine waived"})


# ===================== USER APPROVAL MANAGEMENT =====================

@admin_bp.route("/pending-users")
@admin_required
def pending_users():
    """View pending user registrations"""
    filter_by = request.args.get('filter', 'pending')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = User.query.filter_by(is_deleted=False)
    
    if filter_by == 'pending':
        query = query.filter_by(approval_status='pending')
    elif filter_by == 'approved':
        query = query.filter_by(approval_status='approved')
    elif filter_by == 'rejected':
        query = query.filter_by(approval_status='rejected')
    
    # Statistics
    stats = {
        'pending': User.query.filter_by(approval_status='pending', is_deleted=False).count(),
        'approved': User.query.filter(
            User.approval_status == 'approved',
            User.approved_at >= datetime.utcnow().date(),
            User.is_deleted == False
        ).count(),
        'total': User.query.filter_by(is_deleted=False).count()
    }
    
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/pending_users.html",
                         users=users,
                         stats=stats,
                         current_filter=filter_by,
                         page=page,
                         total_pages=total_pages)


@admin_bp.route("/user/<int:user_id>/approve", methods=["POST"])
@admin_required
def approve_user(user_id):
    """Approve user registration"""
    try:
        print(f"=== APPROVE USER CALLED ===")
        print(f"User ID: {user_id}")
        print(f"Session user_id: {session.get('user_id')}")
        print(f"Session role: {session.get('role')}")
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        print(f"Found user: {user.username}, approval_status: {user.approval_status}")
        
        if user.approval_status != 'pending':
            return jsonify({"success": False, "message": f"User already {user.approval_status}"}), 400
        
        # Update user status
        user.approval_status = 'approved'
        user.approved_by_id = session.get('user_id')
        user.approved_at = datetime.utcnow()
        user.membership_status = 'active'
        
        # Activate library card if exists
        if user.library_card:
            user.library_card.is_active = True
            user.library_card.status = 'active'
        
        db.session.commit()
        print(f"User {user.username} approved successfully!")
        
        # Send notification
        try:
            subject = "Your Library Registration has been Approved!"
            message = get_approval_email_template(user, 'approved')
            send_user_notification(user, subject, message)
        except Exception as e:
            current_app.logger.error(f"Error sending approval email: {e}")
        
        # Log activity
        log_admin_activity(
            user_id=session['user_id'],
            action='approve_user',
            description=f"Approved user: {user.username}",
            metadata={'user_id': user.id}
        )
        
        return jsonify({
            "success": True,
            "message": f"User {user.username} approved successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route("/user/<int:user_id>/reject", methods=["POST"])
@admin_required
def reject_user(user_id):
    """Reject user registration"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        data = request.get_json()
        reason = data.get('reason', 'No reason provided')
        
        if user.approval_status != 'pending':
            return jsonify({"success": False, "message": f"User already {user.approval_status}"}), 400
        
        # Update user status
        user.approval_status = 'rejected'
        user.approved_by_id = session.get('user_id')
        user.approved_at = datetime.utcnow()
        user.rejection_reason = reason
        user.membership_status = 'suspended'
        
        # Deactivate library card
        if user.library_card:
            user.library_card.is_active = False
            user.library_card.status = 'suspended'
        
        db.session.commit()
        
        # Send notification
        try:
            subject = "Update on Your Library Registration"
            message = get_approval_email_template(user, 'rejected', reason)
            send_user_notification(user, subject, message)
        except Exception as e:
            current_app.logger.error(f"Error sending rejection email: {e}")
        
        # Log activity
        log_admin_activity(
            user_id=session['user_id'],
            action='reject_user',
            description=f"Rejected user: {user.username}",
            metadata={'user_id': user.id, 'reason': reason}
        )
        
        return jsonify({
            "success": True,
            "message": f"User {user.username} rejected successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route("/user/<int:user_id>/resend-notification", methods=["POST"])
@admin_required
def resend_user_notification(user_id):
    """Resend approval/rejection notification"""
    user = User.query.get_or_404(user_id)
    
    if user.approval_status == 'pending':
        return jsonify({"success": False, "message": "User still pending"}), 400
    
    if user.approval_status == 'approved':
        subject = "Your Library Registration has been Approved!"
        message = get_approval_email_template(user, 'approved')
    else:
        subject = "Update on Your Library Registration"
        message = get_approval_email_template(user, 'rejected', user.rejection_reason)
    
    send_user_notification(user, subject, message)
    
    log_admin_activity(
        user_id=session['user_id'],
        action='resend_notification',
        description=f"Resent notification to user: {user.username}",
        metadata={'user_id': user.id, 'status': user.approval_status}
    )
    
    return jsonify({"success": True, "message": "Notification resent"})


@admin_bp.route("/user/bulk-approve", methods=["POST"])
@admin_required
def bulk_approve_users():
    """Bulk approve multiple users"""
    data = request.get_json()
    user_ids = data.get('user_ids', [])
    
    if not user_ids:
        return jsonify({"success": False, "message": "No users selected"}), 400
    
    count = 0
    for user_id in user_ids:
        user = User.query.get(user_id)
        if user and user.approval_status == 'pending':
            user.approval_status = 'approved'
            user.approved_by_id = session['user_id']
            user.approved_at = datetime.utcnow()
            user.membership_status = 'active'
            if user.library_card:
                user.library_card.is_active = True
            count += 1
            
            # Send notification
            subject = "Your Library Registration has been Approved!"
            message = get_approval_email_template(user, 'approved')
            send_user_notification(user, subject, message)
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='bulk_approve',
        description=f"Bulk approved {count} users"
    )
    
    return jsonify({
        "success": True,
        "message": f"{count} users approved successfully"
    })


# ===================== BOOK MANAGEMENT =====================

@admin_bp.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    """Enhanced book upload with all new fields"""
    if request.method == "POST":
        # Handle main file
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("❌ No file selected.")
            return redirect(request.url)

        if not allowed_pdf(file.filename):
            flash("❌ Only PDF, EPUB, and MOBI files are allowed.")
            return redirect(request.url)

        # Securely upload file
        file_info, error = secure_file_upload(file, 'books')
        if error:
            flash(f"❌ {error}")
            return redirect(request.url)

        # Handle cover image
        cover_info = None
        cover_file = request.files.get('cover_image')
        if cover_file and cover_file.filename:
            if allowed_image(cover_file.filename):
                cover_info, error = secure_file_upload(cover_file, 'covers')
                if error:
                    flash(f"❌ {error}")
                    return redirect(request.url)
            else:
                flash("❌ Invalid image format. Allowed: PNG, JPG, JPEG, GIF, WEBP")
                return redirect(request.url)

        # Handle sample file (optional)
        sample_info = None
        sample_file = request.files.get('sample_file')
        if sample_file and sample_file.filename:
            sample_info, error = secure_file_upload(sample_file, 'samples')
            if error:
                flash(f"❌ {error}")
                return redirect(request.url)

        # Get form data
        has_digital = 'has_digital' in request.form
        has_physical = 'has_physical' in request.form
        
        # Parse subjects and keywords
        subjects = [s.strip() for s in request.form.get('subjects', '').split(',') if s.strip()]
        keywords = [k.strip() for k in request.form.get('keywords', '').split(',') if k.strip()]
        
        # Parse approved roles
        approved_roles = [r.strip() for r in request.form.get('approved_roles', '').split(',') if r.strip()]

        # Create book record
        book = Book(
            # Basic metadata
            title=request.form["title"],
            subtitle=request.form.get('subtitle'),
            author=request.form["author"],
            category=request.form["category"],
            subcategory=request.form.get('subcategory'),
            description=request.form["description"],
            
            # Identifiers
            isbn=request.form.get("isbn"),
            issn=request.form.get('issn'),
            doi=request.form.get('doi'),
            oclc_number=request.form.get('oclc_number'),
            lccn=request.form.get('lccn'),
            
            # Publication details
            publisher=request.form.get("publisher"),
            published_year=request.form.get("published_year", type=int),
            edition=request.form.get('edition'),
            volume=request.form.get('volume'),
            series=request.form.get('series'),
            language=request.form.get("language", "English"),
            original_language=request.form.get('original_language'),
            translator=request.form.get('translator'),
            
            # Physical description
            pages=request.form.get("pages", type=int),
            dimensions=request.form.get('dimensions'),
            weight=request.form.get('weight', type=float),
            binding=request.form.get('binding'),
            
            # Classification
            dewey_decimal=request.form.get('dewey_decimal'),
            library_of_congress=request.form.get('library_of_congress'),
            subjects=subjects,
            keywords=keywords,
            audience=request.form.get('audience'),
            
            # Format flags
            has_digital=has_digital,
            has_physical=has_physical,
            
            # Digital fields
            filename=file_info['filename'] if has_digital and file_info else None,
            file_size=file_info['size'] if has_digital and file_info else None,
            mime_type=file_info['mime_type'] if has_digital and file_info else None,
            file_hash=file_info['hash'] if has_digital and file_info else None,
            file_format=request.form.get('file_format', 'pdf'),
            
            # DRM settings
            drm_enabled='drm_enabled' in request.form,
            concurrent_users=request.form.get('concurrent_users', 1, type=int),
            loan_period_days=request.form.get('loan_period_days', 14, type=int),
            allow_download='allow_download' in request.form,
            allow_print='allow_print' in request.form,
            allow_copy='allow_copy' in request.form,
            watermark_enabled='watermark_enabled' in request.form,
            
            # Physical fields
            total_copies=request.form.get("total_copies", 0, type=int) if has_physical else 0,
            available_copies=request.form.get("total_copies", 0, type=int) if has_physical else 0,
            shelf_location=request.form.get("shelf_location") if has_physical else None,
            accession_number=request.form.get("accession_number") if has_physical else None,
            floor=request.form.get('floor'),
            section=request.form.get('section'),
            
            # Media
            cover_image=cover_info['filename'] if cover_info else None,
            sample_url=sample_info['filename'] if sample_info else None,
            
            # External links
            google_books_id=request.form.get('google_books_id'),
            open_library_id=request.form.get('open_library_id'),
            worldcat_id=request.form.get('worldcat_id'),
            amazon_url=request.form.get('amazon_url'),
            goodreads_url=request.form.get('goodreads_url'),
            
            # Status flags
            is_featured='is_featured' in request.form,
            is_new_arrival='is_new_arrival' in request.form,
            is_bestseller='is_bestseller' in request.form,
            is_recommended='is_recommended' in request.form,
            is_restricted='is_restricted' in request.form,
            is_reference='is_reference' in request.form,
            is_serial='is_serial' in request.form,
            
            # Access control
            is_public='is_public' in request.form,
            requires_library_card='requires_library_card' in request.form,
            requires_special_request='requires_special_request' in request.form,
            special_request_notes=request.form.get("special_request_notes"),
            security_classification=request.form.get("security_classification"),
            minimum_clearance=request.form.get("minimum_clearance", 'basic'),
            approved_roles=approved_roles,
            
            # Audit
            created_by_id=session['user_id']
        )

        db.session.add(book)
        db.session.flush()
        
        # Create item copies if physical
        if has_physical and book.total_copies > 0:
            for i in range(book.total_copies):
                copy = ItemCopy(
                    book_id=book.id,
                    copy_number=i+1,
                    accession_number=f"{book.accession_number}-{i+1}" if book.accession_number else None,
                    shelf_location=book.shelf_location,
                    floor=book.floor,
                    section=book.section,
                    status='available',
                    acquisition_date=datetime.utcnow(),
                    acquisition_type='purchase',
                    cost=request.form.get('cost', type=float),
                    vendor=request.form.get('vendor')
                )
                db.session.add(copy)
        
        # Add to cataloging queue - FIXED: removed created_by_id
        queue = CatalogingQueue(
            book_id=book.id,
            status='pending',
            cataloger_notes=f"Added via upload by {session.get('username')}"
            # created_by_id REMOVED - this field doesn't exist in CatalogingQueue model
        )
        db.session.add(queue)
        
        db.session.commit()
        
        # Trigger Solr indexing
        if has_digital:
            trigger_solr_index(book.id, delay=True)
        
        # Log admin activity
        log_admin_activity(
            user_id=session['user_id'],
            action='upload',
            description=f"Uploaded book: {book.title}",
            book_id=book.id,
            metadata={
                'has_digital': has_digital,
                'has_physical': has_physical,
                'requires_special_request': book.requires_special_request
            }
        )

        flash("✅ Book uploaded successfully and added to cataloging queue!")
        return redirect(url_for("admin.cataloging_queue"))

    # Get categories for dropdown
    categories = db.session.query(Book.category).distinct().order_by(Book.category).all()
    
    # Get popular tags for suggestions
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    tag_counts = {}
    for b in all_books:
        if b.keywords:
            for tag in b.keywords:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    
    return render_template("admin/upload.html", 
                         categories=categories,
                         popular_tags=popular_tags)


@admin_bp.route("/manage-books")
@admin_required
def manage_books():
    """Manage books"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    filter_type = request.args.get('filter', 'all')
    category = request.args.get('category', '')
    tag = request.args.get('tag', '')
    
    books_query = Book.query.filter_by(is_deleted=False)
    
    if filter_type == 'restricted':
        books_query = books_query.filter_by(requires_special_request=True)
    elif filter_type == 'digital':
        books_query = books_query.filter_by(has_digital=True)
    elif filter_type == 'physical':
        books_query = books_query.filter_by(has_physical=True)
    elif filter_type == 'featured':
        books_query = books_query.filter_by(is_featured=True)
    elif filter_type == 'new':
        books_query = books_query.filter_by(is_new_arrival=True)
    
    if category:
        books_query = books_query.filter_by(category=category)
    
    if tag:
        # Filter books containing this tag
        all_books = books_query.all()
        book_ids = []
        for book in all_books:
            if book.keywords and tag in book.keywords:
                book_ids.append(book.id)
        books_query = books_query.filter(Book.id.in_(book_ids))
    
    books_query = books_query.order_by(Book.created_at.desc())
    total = books_query.count()
    books = books_query.offset((page - 1) * per_page).limit(per_page).all()
    
    total_pages = (total + per_page - 1) // per_page
    
    # Get all categories for filter dropdown
    all_categories = db.session.query(Book.category).distinct().order_by(Book.category).all()
    
    # Get popular tags for filter dropdown
    all_books_with_tags = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    tag_counts = {}
    for b in all_books_with_tags:
        if b.keywords:
            for t in b.keywords:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    
    return render_template("admin/manage_books.html",
                         books=books,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         filter_type=filter_type,
                         current_category=category,
                         current_tag=tag,
                         categories=all_categories,
                         popular_tags=popular_tags)


@admin_bp.route("/book/<int:book_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_book(book_id):
    """Edit book details"""
    book = Book.query.get_or_404(book_id)
    
    if request.method == "POST":
        old_title = book.title
        
        # Update basic info
        book.title = request.form["title"]
        book.author = request.form["author"]
        book.category = request.form["category"]
        book.description = request.form["description"]
        
        # Handle tags/keywords
        tags_input = request.form.get("tags", "")
        if tags_input:
            tags = [t.strip() for t in tags_input.split(',') if t.strip()]
            book.keywords = tags
        
        # Update format flags
        book.has_digital = 'has_digital' in request.form
        book.has_physical = 'has_physical' in request.form
        
        # Update common fields
        book.pages = request.form.get("pages", type=int)
        book.total_pages = request.form.get("pages", type=int)
        book.isbn = request.form.get("isbn")
        book.publisher = request.form.get("publisher")
        book.published_year = request.form.get("published_year", type=int)
        book.language = request.form.get("language", "English")
        
        # Update physical fields
        book.total_copies = request.form.get("total_copies", 0, type=int)
        book.available_copies = request.form.get("available_copies", book.total_copies, type=int)
        book.shelf_location = request.form.get("shelf_location")
        book.accession_number = request.form.get("accession_number")
        
        # Update status flags
        book.is_featured = 'is_featured' in request.form
        book.is_new_arrival = 'is_new_arrival' in request.form
        book.is_bestseller = 'is_bestseller' in request.form
        book.is_recommended = 'is_recommended' in request.form
        
        # Update access control fields
        book.is_public = 'is_public' in request.form
        book.requires_library_card = 'requires_library_card' in request.form
        book.requires_special_request = 'requires_special_request' in request.form
        book.special_request_notes = request.form.get("special_request_notes")
        book.security_classification = request.form.get("security_classification")
        book.approved_roles = request.form.get("approved_roles")
        
        db.session.commit()
        
        # Trigger Solr re-index if digital
        if book.has_digital:
            trigger_solr_index(book.id, delay=True)
        
        # Log admin activity
        log_admin_activity(
            user_id=session['user_id'],
            action='edit',
            description=f"Edited book: {old_title}",
            book_id=book.id
        )
        
        flash("✅ Book updated successfully.")
        return redirect(url_for('admin.manage_books'))
    
    # Get all categories for dropdown
    categories = db.session.query(Book.category).distinct().order_by(Book.category).all()
    
    # Get popular tags for suggestions
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    tag_counts = {}
    for b in all_books:
        if b.keywords:
            for tag in b.keywords:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    popular_tags = [{'name': t[0], 'count': t[1]} for t in popular_tags]
    
    return render_template("admin/edit_book.html", 
                         book=book, 
                         categories=categories,
                         popular_tags=popular_tags)


@admin_bp.route("/book/<int:book_id>/delete", methods=["POST"])
@admin_required
def delete_book(book_id):
    """Delete a book"""
    book = Book.query.get_or_404(book_id)
    book_title = book.title
    
    # Delete PDF file if exists
    if book.filename:
        try:
            file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], book.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            current_app.logger.error(f"Error deleting file: {e}")
    
    # Delete cover image if exists
    if book.cover_image:
        try:
            cover_path = os.path.join(current_app.config["UPLOAD_FOLDER"], book.cover_image)
            if os.path.exists(cover_path):
                os.remove(cover_path)
        except Exception as e:
            current_app.logger.error(f"Error deleting cover: {e}")
    
    # Delete item copies
    ItemCopy.query.filter_by(book_id=book.id).delete()
    
    # Trigger Solr deletion if digital
    if book.has_digital:
        trigger_solr_delete(book.id)
    
    # Log admin activity
    log_admin_activity(
        user_id=session['user_id'],
        action='delete',
        description=f"Deleted book: {book_title}"
    )
    
    db.session.delete(book)
    db.session.commit()
    
    return {"success": True, "message": "Book deleted successfully"}


@admin_bp.route("/book/<int:book_id>/copies")
@admin_required
def book_copies(book_id):
    """View all copies of a book"""
    book = Book.query.get_or_404(book_id)
    copies = ItemCopy.query.filter_by(book_id=book_id).all()
    
    return render_template("admin/book_copies.html",
                         book=book, 
                         copies=copies)


@admin_bp.route("/copy/<int:copy_id>/update-status", methods=["POST"])
@admin_required
def update_copy_status(copy_id):
    """Update the status of a physical copy"""
    copy = ItemCopy.query.get_or_404(copy_id)
    data = request.get_json()
    
    new_status = data.get('status')
    valid_statuses = ['available', 'checked_out', 'reserved', 'lost', 'damaged', 'in_transit']
    
    if new_status not in valid_statuses:
        return jsonify({"success": False, "message": "Invalid status"}), 400
    
    old_status = copy.status
    copy.status = new_status
    copy.condition = data.get('condition', copy.condition)
    copy.notes = data.get('notes', copy.notes)
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='update_copy_status',
        description=f"Updated copy {copy.id} status from {old_status} to {new_status}",
        book_id=copy.book_id,
        metadata={'copy_id': copy_id, 'old_status': old_status, 'new_status': new_status}
    )
    
    return jsonify({"success": True, "message": "Copy status updated"})


# ===================== SPECIAL REQUESTS MANAGEMENT =====================

@admin_bp.route("/special-requests")
@admin_required
def manage_special_requests():
    """Manage special access requests"""
    status = request.args.get('status', 'pending')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = SpecialRequest.query
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    # Get counts for tabs
    counts = {
        'pending': SpecialRequest.query.filter_by(status='pending').count(),
        'approved': SpecialRequest.query.filter_by(status='approved').count(),
        'denied': SpecialRequest.query.filter_by(status='denied').count(),
        'total': SpecialRequest.query.count()
    }
    
    # Get requests with pagination
    requests = query.order_by(
        SpecialRequest.created_at.desc()
    ).offset((page - 1) * per_page).limit(per_page).all()
    
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/special_requests.html",
                         requests=requests,
                         counts=counts,
                         current_status=status,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/special-request/<int:request_id>/review", methods=["POST"])
@admin_required
def review_special_request(request_id):
    """Approve or deny a special request"""
    special_request = SpecialRequest.query.get_or_404(request_id)
    
    data = request.get_json()
    action = data.get('action')  # 'approve' or 'deny'
    review_notes = data.get('notes', '')
    
    if action not in ['approve', 'deny']:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    
    # Update request
    special_request.status = 'approved' if action == 'approve' else 'denied'
    special_request.reviewed_by = session['user_id']
    special_request.reviewed_at = datetime.utcnow()
    special_request.review_notes = review_notes
    
    db.session.commit()
    
    # Log admin activity
    log_admin_activity(
        user_id=session['user_id'],
        action=f'special_request_{action}',
        description=f"{action}d request for {special_request.book.title} from {special_request.user.username}",
        metadata={
            'request_id': request_id,
            'user_id': special_request.user_id,
            'book_id': special_request.book_id,
            'notes': review_notes
        }
    )
    
    # Send notification
    status_text = "approved" if action == 'approve' else "denied"
    send_user_notification(
        special_request.user,
        f"Special Request {status_text.title()}",
        f"Your request for '{special_request.book.title}' has been {status_text}.",
        'success' if action == 'approve' else 'error',
        'special_request'
    )
    
    # Get updated counts
    counts = {
        'pending': SpecialRequest.query.filter_by(status='pending').count(),
        'approved': SpecialRequest.query.filter_by(status='approved').count(),
        'denied': SpecialRequest.query.filter_by(status='denied').count()
    }
    
    return jsonify({
        "success": True,
        "message": f"Request {action}d successfully",
        "request": special_request.to_dict() if hasattr(special_request, 'to_dict') else {},
        "counts": counts
    })


@admin_bp.route("/special-requests/bulk", methods=["POST"])
@admin_required
def bulk_review_requests():
    """Bulk approve/deny multiple requests"""
    data = request.get_json()
    action = data.get('action')
    request_ids = data.get('request_ids', [])
    review_notes = data.get('notes', 'Bulk action')
    
    if action not in ['approve', 'deny']:
        return jsonify({"success": False, "message": "Invalid action"}), 400
    
    count = 0
    for req_id in request_ids:
        special_request = SpecialRequest.query.get(req_id)
        if special_request and special_request.status == 'pending':
            special_request.status = 'approved' if action == 'approve' else 'denied'
            special_request.reviewed_by = session['user_id']
            special_request.reviewed_at = datetime.utcnow()
            special_request.review_notes = review_notes
            count += 1
    
    db.session.commit()
    
    # Log admin activity
    log_admin_activity(
        user_id=session['user_id'],
        action=f'bulk_{action}',
        description=f"Bulk {action}d {count} requests"
    )
    
    # Get updated counts
    counts = {
        'pending': SpecialRequest.query.filter_by(status='pending').count(),
        'approved': SpecialRequest.query.filter_by(status='approved').count(),
        'denied': SpecialRequest.query.filter_by(status='denied').count()
    }
    
    return jsonify({
        "success": True,
        "message": f"{count} requests {action}d",
        "counts": counts
    })


@admin_bp.route("/special-requests/export")
@admin_required
def export_special_requests():
    """Export special requests as CSV"""
    import csv
    from io import StringIO
    from flask import make_response
    
    # Create CSV in memory
    si = StringIO()
    cw = csv.writer(si)
    
    # Write headers
    cw.writerow(['ID', 'User', 'Book', 'Request Type', 'Reason', 'Status', 'Created', 'Reviewed By', 'Review Notes'])
    
    # Write data
    requests = SpecialRequest.query.order_by(SpecialRequest.created_at.desc()).all()
    for req in requests:
        cw.writerow([
            req.id,
            req.user.username if req.user else 'N/A',
            req.book.title if req.book else 'N/A',
            req.request_type,
            req.reason,
            req.status,
            req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else 'N/A',
            req.reviewer.username if req.reviewer else 'N/A',
            req.review_notes or ''
        ])
    
    # Create response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=special_requests.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output


# ===================== USER MANAGEMENT =====================

@admin_bp.route("/manage-users")
@admin_required
def manage_users():
    """Manage users"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    users_query = User.query.order_by(User.created_at.desc())
    total = users_query.count()
    users = users_query.offset((page - 1) * per_page).limit(per_page).all()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/manage_users.html",
                         users=users,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/user/<int:user_id>/update-clearance", methods=["POST"])
@admin_required
def update_user_clearance(user_id):
    """Update user security clearance"""
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    new_clearance = data.get('security_clearance')
    requires_approval = data.get('requires_approval_for_restricted', True)
    
    valid_clearances = ['basic', 'confidential', 'secret', 'top_secret']
    if new_clearance not in valid_clearances:
        return jsonify({"success": False, "message": "Invalid clearance level"}), 400
    
    old_clearance = user.security_clearance
    user.security_clearance = new_clearance
    user.requires_approval_for_restricted = requires_approval
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='update_clearance',
        description=f"Updated {user.username} clearance from {old_clearance} to {new_clearance}"
    )
    
    return jsonify({
        "success": True,
        "message": "Clearance updated successfully"
    })


@admin_bp.route("/user/<int:user_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_user_status(user_id):
    """Toggle user membership status"""
    user = User.query.get_or_404(user_id)
    
    if user.id == session['user_id']:
        return {"success": False, "message": "Cannot change your own status"}, 400
    
    old_status = user.membership_status
    user.membership_status = 'suspended' if user.membership_status == 'active' else 'active'
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='toggle_user',
        description=f"Changed user {user.username} status from {old_status} to {user.membership_status}",
        metadata={'user_id': user.id, 'old_status': old_status, 'new_status': user.membership_status}
    )
    
    return {"success": True, "message": f"User status updated to {user.membership_status}"}


@admin_bp.route("/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    user = User.query.get_or_404(user_id)
    
    if user.id == session['user_id']:
        return {"success": False, "message": "Cannot delete your own account"}, 400
    
    username = user.username
    
    # Soft delete instead of hard delete
    if hasattr(user, 'soft_delete'):
        user.soft_delete(session['user_id'], "Deleted by admin")
    else:
        db.session.delete(user)
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='delete_user',
        description=f"Deleted user: {username}"
    )
    
    return {"success": True, "message": "User deleted successfully"}


@admin_bp.route("/user/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_user_password(user_id):
    """Reset user password"""
    from werkzeug.security import generate_password_hash
    
    user = User.query.get_or_404(user_id)
    
    # Generate a random temporary password
    import random
    import string
    temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    user.password = generate_password_hash(temp_password)
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='reset_password',
        description=f"Reset password for user: {user.username}",
        metadata={'user_id': user.id}
    )
    
    # Send notification with new password
    send_user_notification(
        user,
        "Password Reset",
        f"Your password has been reset by an administrator. Your temporary password is: <strong>{temp_password}</strong><br>Please change it after logging in.",
        'warning',
        'security'
    )
    
    return {"success": True, "message": f"Password reset successful", "temp_password": temp_password}


# ===================== BORROWING MANAGEMENT =====================

@admin_bp.route("/manage-borrowings")
@admin_required
def manage_borrowings():
    """Manage borrowings"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    status = request.args.get('status', 'all')
    
    query = BorrowRecord.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    total = query.count()
    borrowings = query.order_by(BorrowRecord.borrow_date.desc())\
        .offset((page - 1) * per_page).limit(per_page).all()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/manage_borrowings.html",
                         borrowings=borrowings,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         status=status)


@admin_bp.route("/borrowing/<int:borrow_id>/mark-returned", methods=["POST"])
@admin_required
def mark_borrowing_returned(borrow_id):
    """Mark a borrowing as returned"""
    borrow = BorrowRecord.query.get_or_404(borrow_id)
    
    if borrow.status != 'borrowed':
        return {"success": False, "message": "Book already returned"}, 400
    
    borrow.return_date = datetime.utcnow()
    borrow.status = 'returned'
    borrow.fine_amount = borrow.calculate_fine()
    
    # Update book copies
    book = Book.query.get(borrow.book_id)
    if book.has_physical:
        book.available_copies += 1
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='mark_returned',
        description=f"Marked borrowing #{borrow_id} as returned",
        metadata={'borrow_id': borrow_id, 'book_id': borrow.book_id, 'user_id': borrow.user_id}
    )
    
    return {"success": True, "message": "Book marked as returned"}


@admin_bp.route("/borrowing/<int:borrow_id>/extend", methods=["POST"])
@admin_required
def extend_borrowing(borrow_id):
    """Extend borrowing due date"""
    borrow = BorrowRecord.query.get_or_404(borrow_id)
    days = request.json.get('days', 7)
    
    if borrow.status != 'borrowed':
        return {"success": False, "message": "Cannot extend returned book"}, 400
    
    old_due = borrow.due_date
    borrow.due_date = borrow.due_date + timedelta(days=days)
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='extend_borrowing',
        description=f"Extended borrowing #{borrow_id} by {days} days",
        metadata={'borrow_id': borrow_id, 'days': days, 'old_due': old_due.isoformat(), 'new_due': borrow.due_date.isoformat()}
    )
    
    return {"success": True, "message": f"Due date extended by {days} days"}


# ===================== DOWNLOAD LOGS =====================

@admin_bp.route("/download-logs")
@admin_required
def download_logs():
    """View download logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    logs_query = DownloadLog.query.order_by(DownloadLog.timestamp.desc())
    total = logs_query.count()
    logs = logs_query.offset((page - 1) * per_page).limit(per_page).all()
    
    total_pages = (total + per_page - 1) // per_page
    
    # Summary statistics
    today = datetime.utcnow().date()
    downloads_today = DownloadLog.query.filter(
        func.date(DownloadLog.timestamp) == today
    ).count()
    
    this_week = DownloadLog.query.filter(
        DownloadLog.timestamp >= datetime.utcnow() - timedelta(days=7)
    ).count()
    
    this_month = DownloadLog.query.filter(
        DownloadLog.timestamp >= datetime.utcnow() - timedelta(days=30)
    ).count()
    
    # Top downloaded books
    top_books = db.session.query(
        Book.id, Book.title, Book.author, func.count(DownloadLog.id).label('count')
    ).join(DownloadLog, DownloadLog.book_id == Book.id)\
     .group_by(Book.id)\
     .order_by(desc('count'))\
     .limit(5).all()
    
    # Top downloading users
    top_users = db.session.query(
        User.id, User.username, User.full_name, func.count(DownloadLog.id).label('count')
    ).join(DownloadLog, DownloadLog.user_id == User.id)\
     .group_by(User.id)\
     .order_by(desc('count'))\
     .limit(5).all()
    
    return render_template("admin/download_logs.html",
                         logs=logs,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         downloads_today=downloads_today,
                         downloads_this_week=this_week,
                         downloads_this_month=this_month,
                         top_books=top_books,
                         top_users=top_users)


@admin_bp.route("/api/download-stats")
@admin_required
def download_stats_api():
    """API endpoint for download statistics"""
    now = datetime.utcnow()
    
    # Daily stats for last 30 days
    daily_stats = []
    for i in range(30):
        day = now - timedelta(days=i)
        next_day = day + timedelta(days=1)
        count = DownloadLog.query.filter(
            DownloadLog.timestamp >= day,
            DownloadLog.timestamp < next_day
        ).count()
        daily_stats.append({
            'date': day.strftime('%Y-%m-%d'),
            'count': count
        })
    
    # User stats
    user_stats = []
    user_query = db.session.query(
        User.username, func.count(DownloadLog.id).label('count')
    ).join(DownloadLog, DownloadLog.user_id == User.id)\
     .group_by(User.id)\
     .order_by(desc('count'))\
     .limit(10).all()
    
    for username, count in user_query:
        user_stats.append({'username': username, 'count': count})
    
    return jsonify({
        'total': DownloadLog.query.count(),
        'daily': daily_stats,
        'by_user': user_stats
    })


# ===================== READING ANALYTICS =====================

@admin_bp.route("/reading-analytics")
@admin_required
def reading_analytics():
    """View reading analytics"""
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    
    # Basic stats
    total_readers = ReadingProgress.query.count()
    active_today = ReadingProgress.query.filter(
        ReadingProgress.last_accessed >= today_start
    ).count()
    
    total_bookmarks = Bookmark.query.count()
    total_annotations = Annotation.query.count()
    
    # Reading sessions
    total_sessions = ReadingSession.query.count()
    avg_session_duration = db.session.query(func.avg(ReadingSession.duration_seconds)).scalar() or 0
    
    # Most read books
    most_read = db.session.query(
        Book.id, Book.title, Book.author,
        func.count(ReadingProgress.id).label('read_count'),
        func.avg(ReadingProgress.progress_percentage).label('avg_progress')
    ).join(ReadingProgress, ReadingProgress.book_id == Book.id)\
     .group_by(Book.id)\
     .order_by(desc('read_count'))\
     .limit(10).all()
    
    # Reading time stats
    total_reading_time = db.session.query(
        func.sum(ReadingProgress.reading_time_seconds)
    ).scalar() or 0
    
    # Books with most bookmarks
    most_bookmarked = db.session.query(
        Book.id, Book.title, Book.author,
        func.count(Bookmark.id).label('bookmark_count')
    ).join(Bookmark, Bookmark.book_id == Book.id)\
     .group_by(Book.id)\
     .order_by(desc('bookmark_count'))\
     .limit(5).all()
    
    return render_template("admin/reading_analytics.html",
                         total_readers=total_readers,
                         active_today=active_today,
                         total_bookmarks=total_bookmarks,
                         total_annotations=total_annotations,
                         total_sessions=total_sessions,
                         avg_session_duration=avg_session_duration,
                         most_read=most_read,
                         total_reading_time=total_reading_time,
                         most_bookmarked=most_bookmarked)


# ===================== FILE SERVING =====================

@admin_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    import os
    from flask import send_from_directory, current_app, abort
    
    # Security check
    if '..' in filename or filename.startswith('/'):
        abort(404)
    
    upload_folder = current_app.config['UPLOAD_FOLDER']
    full_path = os.path.join(upload_folder, filename)
    
    # Debug logging (remove after fixing)
    print(f"📁 Upload request: {filename}")
    print(f"📂 Full path: {full_path}")
    print(f"✅ Exists: {os.path.exists(full_path)}")
    
    try:
        return send_from_directory(upload_folder, filename)
    except FileNotFoundError:
        print(f"❌ File not found: {full_path}")
        abort(404)
    except Exception as e:
        print(f"❌ Error serving file: {e}")
        abort(500)

# ===================== RESERVATION MANAGEMENT =====================

@admin_bp.route("/manage-reservations")
@admin_required
def manage_reservations():
    """Manage book reservations"""
    reservations = BookReservation.query.order_by(
        BookReservation.reservation_date.desc()
    ).all()
    
    return render_template("admin/manage_reservations.html", reservations=reservations)


@admin_bp.route("/reservation/<int:res_id>/update", methods=["POST"])
@admin_required
def update_reservation(res_id):
    """Update reservation status"""
    reservation = BookReservation.query.get_or_404(res_id)
    new_status = request.json.get('status')
    
    if new_status in ['pending', 'fulfilled', 'cancelled']:
        old_status = reservation.status
        reservation.status = new_status
        db.session.commit()
        
        log_admin_activity(
            user_id=session['user_id'],
            action='update_reservation',
            description=f"Reservation #{res_id} status changed from {old_status} to {new_status}",
            metadata={'reservation_id': res_id, 'old_status': old_status, 'new_status': new_status}
        )
        
        return {"success": True, "message": f"Reservation {new_status}"}
    
    return {"success": False, "message": "Invalid status"}, 400


# ===================== NEW: API KEY MANAGEMENT =====================

@admin_bp.route("/api-keys")
@admin_required
def manage_api_keys():
    """Manage API keys"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = ApiKey.query.order_by(ApiKey.created_at.desc())
    total = query.count()
    api_keys = query.offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/api/api_keys.html",
                         api_keys=api_keys,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/api-keys/new", methods=["POST"])
@admin_required
def create_api_key():
    """Create new API key"""
    data = request.get_json()
    
    key = ApiKey(
        user_id=session['user_id'],
        name=data.get('name'),
        description=data.get('description'),
        permissions=data.get('permissions', []),
        rate_limit=data.get('rate_limit', '1000/day'),
        expires_at=datetime.utcnow() + timedelta(days=data.get('expiry_days', 365))
    )
    
    if hasattr(key, 'generate_key'):
        key.generate_key()
    
    db.session.add(key)
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='create_api_key',
        description=f"Created API key: {key.name}"
    )
    
    return jsonify({
        "success": True,
        "message": "API key created successfully",
        "key": key.key if hasattr(key, 'key') else None,
        "id": key.id
    })


@admin_bp.route("/api-keys/<int:key_id>/revoke", methods=["POST"])
@admin_required
def revoke_api_key(key_id):
    """Revoke API key"""
    key = ApiKey.query.get_or_404(key_id)
    
    if hasattr(key, 'revoke'):
        key.revoke()
    else:
        key.is_active = False
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='revoke_api_key',
        description=f"Revoked API key: {key.name}"
    )
    
    return jsonify({"success": True, "message": "API key revoked"})


# ===================== NEW: NOTIFICATION MANAGEMENT =====================

@admin_bp.route("/notifications")
@admin_required
def manage_notifications():
    """Manage system notifications"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    filter_by = request.args.get('filter', 'all')
    
    query = Notification.query
    
    if filter_by == 'unread':
        query = query.filter_by(is_read=False)
    elif filter_by == 'sent':
        query = query.filter(Notification.email_sent == True)
    
    total = query.count()
    notifications = query.order_by(Notification.created_at.desc())\
        .offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("admin/notifications/manage.html",
                         notifications=notifications,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         current_filter=filter_by)


@admin_bp.route("/notifications/send", methods=["POST"])
@admin_required
def send_notification():
    """Send notification to users"""
    data = request.get_json()
    
    title = data.get('title')
    message = data.get('message')
    type = data.get('type', 'info')
    category = data.get('category')
    recipient_type = data.get('recipient_type', 'all')  # all, active, specific
    user_ids = data.get('user_ids', [])
    
    if recipient_type == 'all':
        users = User.query.filter_by(is_deleted=False).all()
    elif recipient_type == 'active':
        users = User.query.filter_by(membership_status='active', is_deleted=False).all()
    elif recipient_type == 'specific' and user_ids:
        users = User.query.filter(User.id.in_(user_ids)).all()
    else:
        return jsonify({"success": False, "message": "Invalid recipient selection"}), 400
    
    count = 0
    for user in users:
        send_user_notification(user, title, message, type, category)
        count += 1
    
    log_admin_activity(
        user_id=session['user_id'],
        action='send_notification',
        description=f"Sent notification to {count} users: {title}"
    )
    
    return jsonify({
        "success": True,
        "message": f"Notification sent to {count} users"
    })


# ===================== NEW: ANNOUNCEMENT MANAGEMENT =====================

@admin_bp.route("/announcements")
@admin_required
def manage_announcements():
    """Manage announcements"""
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements/manage.html", announcements=announcements)


@admin_bp.route("/announcements/new", methods=["POST"])
@admin_required
def create_announcement():
    """Create new announcement"""
    data = request.get_json()
    
    announcement = Announcement(
        title=data.get('title'),
        content=data.get('content'),
        type=data.get('type', 'general'),
        is_public=data.get('is_public', True),
        is_featured=data.get('is_featured', False),
        is_pinned=data.get('is_pinned', False),
        target_roles=data.get('target_roles'),
        published_at=datetime.fromisoformat(data.get('published_at')) if data.get('published_at') else datetime.utcnow(),
        expires_at=datetime.fromisoformat(data.get('expires_at')) if data.get('expires_at') else None,
        created_by=session['user_id']
    )
    
    db.session.add(announcement)
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='create_announcement',
        description=f"Created announcement: {announcement.title}"
    )
    
    return jsonify({
        "success": True,
        "message": "Announcement created",
        "announcement": {
            "id": announcement.id,
            "title": announcement.title
        }
    })


@admin_bp.route("/announcements/<int:ann_id>/update", methods=["POST"])
@admin_required
def update_announcement(ann_id):
    """Update announcement"""
    announcement = Announcement.query.get_or_404(ann_id)
    data = request.get_json()
    
    announcement.title = data.get('title', announcement.title)
    announcement.content = data.get('content', announcement.content)
    announcement.type = data.get('type', announcement.type)
    announcement.is_public = data.get('is_public', announcement.is_public)
    announcement.is_featured = data.get('is_featured', announcement.is_featured)
    announcement.is_pinned = data.get('is_pinned', announcement.is_pinned)
    announcement.target_roles = data.get('target_roles', announcement.target_roles)
    announcement.is_active = data.get('is_active', announcement.is_active)
    
    if data.get('published_at'):
        announcement.published_at = datetime.fromisoformat(data.get('published_at'))
    if data.get('expires_at'):
        announcement.expires_at = datetime.fromisoformat(data.get('expires_at'))
    
    db.session.commit()
    
    return jsonify({"success": True, "message": "Announcement updated"})


@admin_bp.route("/announcements/<int:ann_id>/delete", methods=["POST"])
@admin_required
def delete_announcement(ann_id):
    """Delete announcement"""
    announcement = Announcement.query.get_or_404(ann_id)
    
    db.session.delete(announcement)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Announcement deleted"})


# ===================== NEW: AUDIT LOG VIEWER =====================

@admin_bp.route("/audit-logs")
@admin_required
def audit_logs():
    """View audit logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    query = AuditLog.query
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    if action:
        query = query.filter_by(action=action)
    if date_from:
        query = query.filter(AuditLog.timestamp >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(AuditLog.timestamp <= datetime.fromisoformat(date_to))
    
    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc())\
        .offset((page-1)*per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Get unique actions for filter dropdown
    actions = db.session.query(AuditLog.action).distinct().all()
    
    return render_template("admin/audit/logs.html",
                         logs=logs,
                         actions=actions,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@admin_bp.route("/audit-logs/export")
@admin_required
def export_audit_logs():
    """Export audit logs to CSV"""
    import csv
    from io import StringIO
    
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    query = AuditLog.query
    
    if date_from:
        query = query.filter(AuditLog.timestamp >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(AuditLog.timestamp <= datetime.fromisoformat(date_to))
    
    logs = query.order_by(AuditLog.timestamp.desc()).limit(10000).all()
    
    si = StringIO()
    cw = csv.writer(si)
    
    cw.writerow(['Timestamp', 'User', 'Action', 'Category', 'Description', 
                 'Target Type', 'Target ID', 'IP Address', 'Success', 'Error'])
    
    for log in logs:
        cw.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.username or 'System',
            log.action,
            log.category or '',
            log.description or '',
            log.target_type or '',
            log.target_id or '',
            log.ip_address or '',
            'Yes' if log.success else 'No',
            log.error_message or ''
        ])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=audit_logs.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output


# ===================== NEW: BACKUP MANAGEMENT =====================

@admin_bp.route("/backups")
@admin_required
def manage_backups():
    """Manage database backups"""
    backups = BackupLog.query.order_by(BackupLog.created_at.desc()).all()
    
    # Get backup settings
    backup_enabled = True
    backup_frequency = 'daily'
    retention_days = 30
    try:
        backup_enabled = SystemSetting.get('backup_enabled', True)
        backup_frequency = SystemSetting.get('backup_frequency', 'daily')
        retention_days = SystemSetting.get('retention_days', 30)
    except:
        pass
    
    return render_template("admin/backups/manage.html",
                         backups=backups,
                         backup_enabled=backup_enabled,
                         backup_frequency=backup_frequency,
                         retention_days=retention_days)


@admin_bp.route("/backups/create", methods=["POST"])
@admin_required
def create_backup():
    """Create new database backup"""
    try:
        from tasks.backup_tasks import perform_backup
        
        # Trigger async backup
        task = perform_backup.delay(created_by=session['user_id'])
        
        return jsonify({
            "success": True,
            "message": "Backup started",
            "task_id": task.id
        })
    except:
        return jsonify({
            "success": False,
            "message": "Backup service not available"
        }), 500


@admin_bp.route("/backups/<int:backup_id>/restore", methods=["POST"])
@admin_required
def restore_backup(backup_id):
    """Restore from backup"""
    backup = BackupLog.query.get_or_404(backup_id)
    
    try:
        from tasks.backup_tasks import restore_backup
        task = restore_backup.delay(backup.id, restored_by=session['user_id'])
        
        return jsonify({
            "success": True,
            "message": "Restore started",
            "task_id": task.id
        })
    except:
        return jsonify({
            "success": False,
            "message": "Restore service not available"
        }), 500


@admin_bp.route("/backups/<int:backup_id>/download")
@admin_required
def download_backup(backup_id):
    """Download backup file"""
    backup = BackupLog.query.get_or_404(backup_id)
    
    if not os.path.exists(backup.file_path):
        abort(404)
    
    return send_from_directory(
        directory=os.path.dirname(backup.file_path),
        path=os.path.basename(backup.file_path),
        as_attachment=True
    )


@admin_bp.route("/backups/<int:backup_id>/delete", methods=["POST"])
@admin_required
def delete_backup(backup_id):
    """Delete backup"""
    backup = BackupLog.query.get_or_404(backup_id)
    
    # Delete file
    if os.path.exists(backup.file_path):
        os.remove(backup.file_path)
    
    db.session.delete(backup)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Backup deleted"})


# ===================== NEW: SYSTEM SETTINGS =====================

@admin_bp.route("/settings")
@admin_required
def system_settings():
    """System settings management"""
    settings = SystemSetting.query.order_by(SystemSetting.category, SystemSetting.key).all()
    
    # Group by category
    grouped_settings = {}
    for setting in settings:
        if setting.category not in grouped_settings:
            grouped_settings[setting.category] = []
        grouped_settings[setting.category].append(setting)
    
    return render_template("admin/settings/index.html", grouped_settings=grouped_settings)


@admin_bp.route("/settings/update", methods=["POST"])
@admin_required
def update_settings():
    """Update system settings"""
    data = request.get_json()
    
    for key, value in data.items():
        if hasattr(SystemSetting, 'set'):
            SystemSetting.set(key, value, user_id=session['user_id'])
        else:
            setting = SystemSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = str(value)
                setting.updated_by = session['user_id']
                setting.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    log_admin_activity(
        user_id=session['user_id'],
        action='update_settings',
        description="Updated system settings"
    )
    
    return jsonify({"success": True, "message": "Settings updated"})


@admin_bp.route("/settings/backup", methods=["POST"])
@admin_required
def backup_settings():
    """Export settings as JSON"""
    settings = {}
    for setting in SystemSetting.query.all():
        if setting.type == 'json':
            settings[setting.key] = json.loads(setting.value) if setting.value else None
        elif setting.type == 'boolean':
            settings[setting.key] = setting.value.lower() == 'true' if setting.value else False
        elif setting.type == 'integer':
            settings[setting.key] = int(setting.value) if setting.value else 0
        elif setting.type == 'float':
            settings[setting.key] = float(setting.value) if setting.value else 0.0
        else:
            settings[setting.key] = setting.value
    
    response = make_response(json.dumps(settings, indent=2))
    response.headers["Content-Disposition"] = "attachment; filename=settings_backup.json"
    response.headers["Content-type"] = "application/json"
    
    return response


@admin_bp.route("/settings/restore", methods=["POST"])
@admin_required
def restore_settings():
    """Restore settings from JSON"""
    file = request.files.get('file')
    
    if not file:
        return jsonify({"success": False, "message": "No file uploaded"}), 400
    
    try:
        settings = json.load(file)
        for key, value in settings.items():
            if hasattr(SystemSetting, 'set'):
                SystemSetting.set(key, value, user_id=session['user_id'])
            else:
                setting = SystemSetting.query.filter_by(key=key).first()
                if not setting:
                    setting = SystemSetting(key=key)
                    db.session.add(setting)
                
                if isinstance(value, bool):
                    setting.type = 'boolean'
                    setting.value = str(value).lower()
                elif isinstance(value, int):
                    setting.type = 'integer'
                    setting.value = str(value)
                elif isinstance(value, float):
                    setting.type = 'float'
                    setting.value = str(value)
                elif isinstance(value, (dict, list)):
                    setting.type = 'json'
                    setting.value = json.dumps(value)
                else:
                    setting.type = 'string'
                    setting.value = str(value)
                
                setting.updated_by = session['user_id']
        
        db.session.commit()
        
        return jsonify({"success": True, "message": "Settings restored"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# ===================== NEW: VENDOR MANAGEMENT =====================

@admin_bp.route("/vendors")
@admin_required
def manage_vendors():
    """Manage vendors"""
    vendors = Vendor.query.order_by(Vendor.name).all()
    return render_template("admin/vendors/manage.html", vendors=vendors)


@admin_bp.route("/vendors/new", methods=["POST"])
@admin_required
def create_vendor():
    """Create new vendor"""
    data = request.get_json()
    
    vendor = Vendor(
        name=data.get('name'),
        code=data.get('code'),
        contact_person=data.get('contact_person'),
        email=data.get('email'),
        phone=data.get('phone'),
        address=data.get('address'),
        website=data.get('website'),
        tax_id=data.get('tax_id'),
        payment_terms=data.get('payment_terms'),
        currency=data.get('currency', 'NGN'),
        categories=data.get('categories', []),
        notes=data.get('notes')
    )
    
    db.session.add(vendor)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "Vendor created",
        "vendor": {
            "id": vendor.id,
            "name": vendor.name
        }
    })


@admin_bp.route("/vendors/<int:vendor_id>/edit", methods=["POST"])
@admin_required
def edit_vendor(vendor_id):
    """Edit vendor"""
    vendor = Vendor.query.get_or_404(vendor_id)
    data = request.get_json()
    
    vendor.name = data.get('name', vendor.name)
    vendor.contact_person = data.get('contact_person', vendor.contact_person)
    vendor.email = data.get('email', vendor.email)
    vendor.phone = data.get('phone', vendor.phone)
    vendor.address = data.get('address', vendor.address)
    vendor.website = data.get('website', vendor.website)
    vendor.payment_terms = data.get('payment_terms', vendor.payment_terms)
    vendor.categories = data.get('categories', vendor.categories)
    vendor.is_active = data.get('is_active', vendor.is_active)
    vendor.notes = data.get('notes', vendor.notes)
    
    db.session.commit()
    
    return jsonify({"success": True, "message": "Vendor updated"})


# ===================== NEW: BUDGET MANAGEMENT =====================

@admin_bp.route("/budgets")
@admin_required
def manage_budgets():
    """Manage budgets"""
    year = request.args.get('year', datetime.utcnow().year, type=int)
    
    budgets = Budget.query.filter_by(fiscal_year=year).order_by(Budget.code).all()
    
    # Summary
    total_allocated = sum(b.allocated for b in budgets)
    total_committed = sum(b.committed for b in budgets)
    total_expended = sum(b.expended for b in budgets)
    
    return render_template("admin/budgets/manage.html",
                         budgets=budgets,
                         year=year,
                         total_allocated=total_allocated,
                         total_committed=total_committed,
                         total_expended=total_expended)


@admin_bp.route("/budgets/new", methods=["POST"])
@admin_required
def create_budget():
    """Create new budget"""
    data = request.get_json()
    
    budget = Budget(
        fiscal_year=data.get('fiscal_year', datetime.utcnow().year),
        code=data.get('code'),
        name=data.get('name'),
        allocated=data.get('allocated', 0),
        department=data.get('department'),
        fund_source=data.get('fund_source'),
        start_date=datetime.fromisoformat(data.get('start_date')) if data.get('start_date') else None,
        end_date=datetime.fromisoformat(data.get('end_date')) if data.get('end_date') else None,
        notes=data.get('notes')
    )
    
    if hasattr(budget, 'calculate_remaining'):
        budget.calculate_remaining()
    
    db.session.add(budget)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "Budget created",
        "budget": {
            "id": budget.id,
            "code": budget.code
        }
    })


@admin_bp.route("/budgets/<int:budget_id>/edit", methods=["POST"])
@admin_required
def edit_budget(budget_id):
    """Edit budget"""
    budget = Budget.query.get_or_404(budget_id)
    data = request.get_json()
    
    budget.name = data.get('name', budget.name)
    budget.allocated = data.get('allocated', budget.allocated)
    budget.department = data.get('department', budget.department)
    budget.fund_source = data.get('fund_source', budget.fund_source)
    budget.is_active = data.get('is_active', budget.is_active)
    budget.notes = data.get('notes', budget.notes)
    
    if data.get('start_date'):
        budget.start_date = datetime.fromisoformat(data.get('start_date'))
    if data.get('end_date'):
        budget.end_date = datetime.fromisoformat(data.get('end_date'))
    
    if hasattr(budget, 'calculate_remaining'):
        budget.calculate_remaining()
    
    db.session.commit()
    
    return jsonify({"success": True, "message": "Budget updated"})


# ===================== NEW: REPORT SCHEDULER =====================

@admin_bp.route("/scheduled-reports")
@admin_required
def scheduled_reports():
    """Manage scheduled reports"""
    reports = ScheduledReport.query.order_by(ScheduledReport.next_run).all()
    return render_template("admin/reports/scheduled.html", reports=reports)


@admin_bp.route("/scheduled-reports/new", methods=["POST"])
@admin_required
def create_scheduled_report():
    """Create scheduled report"""
    data = request.get_json()
    
    report = ScheduledReport(
        name=data.get('name'),
        description=data.get('description'),
        report_type=data.get('report_type'),
        format=data.get('format', 'pdf'),
        frequency=data.get('frequency'),
        day_of_week=data.get('day_of_week'),
        day_of_month=data.get('day_of_month'),
        time=datetime.strptime(data.get('time'), '%H:%M').time() if data.get('time') else None,
        parameters=data.get('parameters', {}),
        recipients=data.get('recipients', []),
        created_by=session['user_id']
    )
    
    if hasattr(report, 'calculate_next_run'):
        report.calculate_next_run()
    
    db.session.add(report)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "Scheduled report created",
        "report": {
            "id": report.id,
            "name": report.name
        }
    })


@admin_bp.route("/scheduled-reports/<int:report_id>/toggle", methods=["POST"])
@admin_required
def toggle_scheduled_report(report_id):
    """Toggle scheduled report active status"""
    report = ScheduledReport.query.get_or_404(report_id)
    report.is_active = not report.is_active
    db.session.commit()
    
    return jsonify({
        "success": True,
        "is_active": report.is_active
    })


@admin_bp.route("/scheduled-reports/<int:report_id>/run-now", methods=["POST"])
@admin_required
def run_scheduled_report_now(report_id):
    """Run scheduled report immediately"""
    report = ScheduledReport.query.get_or_404(report_id)
    
    try:
        from tasks.report_tasks import generate_report
        task = generate_report.delay(report.id)
        
        return jsonify({
            "success": True,
            "message": "Report generation started",
            "task_id": task.id
        })
    except:
        return jsonify({
            "success": False,
            "message": "Report service not available"
        }), 500


# ===================== NEW: API ENDPOINTS =====================

@admin_bp.route("/api/patron/search")
@admin_required
def api_patron_search():
    """API endpoint for patron search"""
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify([])
    
    patrons = User.query.filter(
        db.or_(
            User.username.ilike(f"%{query}%"),
            User.email.ilike(f"%{query}%"),
            User.full_name.ilike(f"%{query}%"),
            User.service_number.ilike(f"%{query}%")
        ),
        User.is_deleted == False
    ).limit(10).all()
    
    return jsonify([{
        'id': p.id,
        'text': f"{p.full_name or p.username} ({p.email})",
        'card_number': p.library_card.card_number if p.library_card else None,
        'has_card': p.library_card is not None
    } for p in patrons])


@admin_bp.route("/api/book/search")
@admin_required
def api_book_search():
    """API endpoint for book search"""
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify([])
    
    books = Book.query.filter(
        db.or_(
            Book.title.ilike(f"%{query}%"),
            Book.author.ilike(f"%{query}%"),
            Book.isbn.ilike(f"%{query}%")
        ),
        Book.is_deleted == False
    ).limit(10).all()
    
    return jsonify([{
        'id': b.id,
        'text': f"{b.title} by {b.author}",
        'available_copies': b.available_copies,
        'has_physical': b.has_physical
    } for b in books])


@admin_bp.route("/api/category/search")
@admin_required
def api_category_search():
    """API endpoint for category search"""
    query = request.args.get('q', '')
    
    if len(query) < 1:
        # Return all categories if no query
        categories = db.session.query(Book.category).distinct()\
            .filter(Book.category.isnot(None), Book.category != '')\
            .order_by(Book.category).limit(20).all()
        return jsonify([{'name': c[0], 'value': c[0]} for c in categories])
    
    # Search categories
    categories = db.session.query(Book.category).distinct()\
        .filter(
            Book.category.isnot(None),
            Book.category != '',
            Book.category.ilike(f"%{query}%")
        ).order_by(Book.category).limit(10).all()
    
    return jsonify([{'name': c[0], 'value': c[0]} for c in categories])


@admin_bp.route("/api/tags/search")
@admin_required
def api_tag_search():
    """API endpoint for tag search/autocomplete"""
    query = request.args.get('q', '').lower()
    limit = request.args.get('limit', 10, type=int)
    
    # Get all unique tags
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    
    tag_counts = {}
    for book in all_books:
        if book.keywords:
            for tag in book.keywords:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Filter and sort
    if query:
        tags = [{'name': t, 'count': c} for t, c in tag_counts.items() if query in t.lower()]
    else:
        # Return most popular tags if no query
        tags = [{'name': t, 'count': c} for t, c in tag_counts.items()]
    
    tags.sort(key=lambda x: x['count'], reverse=True)
    tags = tags[:limit]
    
    return jsonify(tags)


@admin_bp.route("/api/barcode/lookup")
@admin_required
def api_barcode_lookup():
    """API endpoint for barcode lookup"""
    barcode = request.args.get('barcode', '')
    
    if not barcode:
        return jsonify({"success": False, "message": "No barcode provided"}), 400
    
    # Try patron card first
    card = LibraryCard.query.filter_by(barcode=barcode).first()
    if card:
        return jsonify({
            "success": True,
            "type": "patron",
            "data": {
                'id': card.user.id,
                'name': card.user.full_name or card.user.username,
                'email': card.user.email,
                'card_number': card.card_number,
                'card_status': card.status,
                'is_expired': card.is_expired(),
                'days_until_expiry': card.days_until_expiry() if hasattr(card, 'days_until_expiry') else 0
            }
        })
    
    # Try item copy
    copy = ItemCopy.query.filter_by(barcode=barcode).first()
    if copy:
        return jsonify({
            "success": True,
            "type": "book",
            "data": {
                'id': copy.book.id,
                'copy_id': copy.id,
                'title': copy.book.title,
                'author': copy.book.author,
                'status': copy.status,
                'is_reference': copy.is_reference_only,
                'location': copy.shelf_location
            }
        })
    
    return jsonify({"success": False, "message": "No item found with this barcode"}), 404


# ===================== REPORTS =====================

@admin_bp.route("/reports")
@admin_required
def reports():
    """Generate reports"""
    return render_template("admin/reports.html")


@admin_bp.route("/api/reports/borrowings")
@admin_required
def borrowings_report():
    """Generate borrowings report"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    query = BorrowRecord.query
    
    if start_date:
        query = query.filter(BorrowRecord.borrow_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(BorrowRecord.borrow_date <= datetime.strptime(end_date, '%Y-%m-%d'))
    
    data = query.order_by(BorrowRecord.borrow_date.desc()).all()
    
    return render_template("admin/reports_borrowings.html", data=data)


@admin_bp.route("/api/reports/downloads")
@admin_required
def downloads_report():
    """Generate downloads report"""
    period = request.args.get('period', 'month')
    
    now = datetime.utcnow()
    
    if period == 'day':
        start = now - timedelta(days=1)
        group_by = func.strftime('%H', DownloadLog.timestamp)
    elif period == 'week':
        start = now - timedelta(days=7)
        group_by = func.strftime('%Y-%m-%d', DownloadLog.timestamp)
    elif period == 'month':
        start = now - timedelta(days=30)
        group_by = func.strftime('%Y-%m-%d', DownloadLog.timestamp)
    else:  # year
        start = now - timedelta(days=365)
        group_by = func.strftime('%Y-%m', DownloadLog.timestamp)
    
    stats = db.session.query(
        group_by.label('period'),
        func.count(DownloadLog.id).label('count')
    ).filter(DownloadLog.timestamp >= start)\
     .group_by(group_by)\
     .order_by(group_by).all()
    
    return jsonify([{'period': s.period, 'count': s.count} for s in stats])


@admin_bp.route("/api/reports/users")
@admin_required
def users_report():
    """Generate user registration report"""
    period = request.args.get('period', 'month')
    
    now = datetime.utcnow()
    
    if period == 'week':
        start = now - timedelta(days=7)
        group_by = func.strftime('%Y-%m-%d', User.created_at)
    elif period == 'month':
        start = now - timedelta(days=30)
        group_by = func.strftime('%Y-%m-%d', User.created_at)
    else:  # year
        start = now - timedelta(days=365)
        group_by = func.strftime('%Y-%m', User.created_at)
    
    stats = db.session.query(
        group_by.label('period'),
        func.count(User.id).label('count')
    ).filter(User.created_at >= start)\
     .group_by(group_by)\
     .order_by(group_by).all()
    
    return jsonify([{'period': s.period, 'count': s.count} for s in stats])


@admin_bp.route("/api/reports/special-requests")
@admin_required
def special_requests_report():
    """Generate special requests report"""
    period = request.args.get('period', 'month')
    
    now = datetime.utcnow()
    
    if period == 'week':
        start = now - timedelta(days=7)
        group_by = func.strftime('%Y-%m-%d', SpecialRequest.created_at)
    elif period == 'month':
        start = now - timedelta(days=30)
        group_by = func.strftime('%Y-%m-%d', SpecialRequest.created_at)
    else:  # year
        start = now - timedelta(days=365)
        group_by = func.strftime('%Y-%m', SpecialRequest.created_at)
    
    # Requests by status
    status_stats = db.session.query(
        SpecialRequest.status,
        func.count(SpecialRequest.id).label('count')
    ).filter(SpecialRequest.created_at >= start)\
     .group_by(SpecialRequest.status)\
     .all()
    
    # Requests over time
    time_stats = db.session.query(
        group_by.label('period'),
        func.count(SpecialRequest.id).label('count')
    ).filter(SpecialRequest.created_at >= start)\
     .group_by(group_by)\
     .order_by(group_by).all()
    
    return jsonify({
        'by_status': [{'status': s[0], 'count': s[1]} for s in status_stats],
        'over_time': [{'period': t[0], 'count': t[1]} for t in time_stats]
    })


# ===================== WORKFLOW REPORTS =====================

@admin_bp.route("/api/reports/acquisition")
@admin_required
def acquisition_report():
    """Generate acquisition report"""
    period = request.args.get('period', 'month')
    
    now = datetime.utcnow()
    
    if period == 'week':
        start = now - timedelta(days=7)
        group_by = func.strftime('%Y-%m-%d', AcquisitionRequest.request_date)
    elif period == 'month':
        start = now - timedelta(days=30)
        group_by = func.strftime('%Y-%m-%d', AcquisitionRequest.request_date)
    else:
        start = now - timedelta(days=365)
        group_by = func.strftime('%Y-%m', AcquisitionRequest.request_date)
    
    # Requests by status
    status_stats = db.session.query(
        AcquisitionRequest.status,
        func.count(AcquisitionRequest.id).label('count')
    ).filter(AcquisitionRequest.request_date >= start)\
     .group_by(AcquisitionRequest.status)\
     .all()
    
    # Requests over time
    time_stats = db.session.query(
        group_by.label('period'),
        func.count(AcquisitionRequest.id).label('count')
    ).filter(AcquisitionRequest.request_date >= start)\
     .group_by(group_by)\
     .order_by(group_by).all()
    
    return jsonify({
        'by_status': [{'status': s[0], 'count': s[1]} for s in status_stats],
        'over_time': [{'period': t[0], 'count': t[1]} for t in time_stats]
    })


@admin_bp.route("/api/reports/circulation")
@admin_required
def circulation_report():
    """Generate circulation report"""
    period = request.args.get('period', 'month')
    
    now = datetime.utcnow()
    
    if period == 'week':
        start = now - timedelta(days=7)
        group_by = func.strftime('%Y-%m-%d', CirculationRecord.checkout_date)
    elif period == 'month':
        start = now - timedelta(days=30)
        group_by = func.strftime('%Y-%m-%d', CirculationRecord.checkout_date)
    else:
        start = now - timedelta(days=365)
        group_by = func.strftime('%Y-%m', CirculationRecord.checkout_date)
    
    # Checkouts over time
    checkout_stats = db.session.query(
        group_by.label('period'),
        func.count(CirculationRecord.id).label('count')
    ).filter(CirculationRecord.checkout_date >= start)\
     .group_by(group_by)\
     .order_by(group_by).all()
    
    # Currently checked out
    active_checkouts = CirculationRecord.query.filter_by(status='active').count()
    overdue_checkouts = CirculationRecord.query.filter(
        CirculationRecord.status == 'active',
        CirculationRecord.due_date < datetime.utcnow()
    ).count()
    
    return jsonify({
        'checkouts': [{'period': t[0], 'count': t[1]} for t in checkout_stats],
        'active': active_checkouts,
        'overdue': overdue_checkouts
    })


# ===================== CATEGORY REPORTS =====================

@admin_bp.route("/api/reports/categories")
@admin_required
def category_reports():
    """Generate category reports"""
    period = request.args.get('period', 'month')
    
    now = datetime.utcnow()
    
    if period == 'week':
        start = now - timedelta(days=7)
    elif period == 'month':
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=365)
    
    # Category distribution
    distribution = db.session.query(
        Book.category,
        func.count(Book.id).label('count')
    ).filter(
        Book.category.isnot(None),
        Book.category != ''
    ).group_by(Book.category).order_by(desc('count')).all()
    
    # Category activity (new books per category)
    activity = db.session.query(
        Book.category,
        func.count(Book.id).label('count')
    ).filter(
        Book.category.isnot(None),
        Book.category != '',
        Book.created_at >= start
    ).group_by(Book.category).order_by(desc('count')).all()
    
    # Most popular categories (by downloads)
    popular = db.session.query(
        Book.category,
        func.count(DownloadLog.id).label('downloads')
    ).join(DownloadLog, DownloadLog.book_id == Book.id)\
     .filter(
        Book.category.isnot(None),
        Book.category != '',
        DownloadLog.timestamp >= start
     ).group_by(Book.category).order_by(desc('downloads')).limit(10).all()
    
    return jsonify({
        'distribution': [{'name': d[0], 'count': d[1]} for d in distribution],
        'activity': [{'name': a[0], 'count': a[1]} for a in activity],
        'popular': [{'name': p[0], 'downloads': p[1]} for p in popular],
        'total_categories': len(distribution)
    })


# ===================== TAGS REPORTS =====================

@admin_bp.route("/api/reports/tags")
@admin_required
def tags_report():
    """Generate tags report"""
    period = request.args.get('period', 'month')
    
    now = datetime.utcnow()
    
    if period == 'week':
        start = now - timedelta(days=7)
    elif period == 'month':
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=365)
    
    # Get all books with tags
    all_books = Book.query.filter(
        Book.keywords.isnot(None),
        Book.is_deleted == False
    ).all()
    
    # Most used tags
    tag_counts = {}
    for book in all_books:
        if book.keywords:
            for tag in book.keywords:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    popular = [{'tag': k, 'usage': v} for k, v in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]]
    
    # Tag usage over time
    usage_over_time = []
    for i in range(7):
        day = now - timedelta(days=i)
        next_day = day + timedelta(days=1)
        
        day_books = [b for b in all_books if day <= b.created_at < next_day]
        day_tag_counts = {}
        for book in day_books:
            if book.keywords:
                for tag in book.keywords:
                    day_tag_counts[tag] = day_tag_counts.get(tag, 0) + 1
        
        top_day_tags = sorted(day_tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        usage_over_time.append({
            'date': day.strftime('%Y-%m-%d'),
            'tags': [{'name': t[0], 'count': t[1]} for t in top_day_tags]
        })
    
    # Books with most tags
    books_with_most_tags = sorted(
        [b for b in all_books if b.keywords],
        key=lambda x: len(x.keywords or []),
        reverse=True
    )[:10]
    
    return jsonify({
        'popular': popular,
        'usage_over_time': usage_over_time,
        'books_with_most_tags': [{
            'id': b.id,
            'title': b.title,
            'tag_count': len(b.keywords or []),
            'tags': (b.keywords or [])[:10]
        } for b in books_with_most_tags]
    })


# ===================== SOLR MANAGEMENT =====================

@admin_bp.route("/solr/dashboard")
@admin_required
def solr_dashboard():
    """Solr search engine management dashboard"""
    solr_status = "disconnected"
    doc_count = 0
    error = None
    
    try:
        from services.solr_client import solr_client
        if hasattr(current_app.extensions, 'solr') and current_app.extensions.get('solr'):
            doc_count = solr_client.count()
            solr_status = "connected"
    except Exception as e:
        error = str(e)
        solr_status = "error"
    
    # Get database counts
    db_book_count = Book.query.count()
    
    return render_template("admin/solr_dashboard.html",
                         solr_status=solr_status,
                         doc_count=doc_count,
                         db_book_count=db_book_count,
                         error=error,
                         difference=abs(db_book_count - doc_count))


@admin_bp.route("/solr/reindex", methods=["POST"])
@admin_required
def solr_reindex():
    """Trigger full Solr reindex"""
    task_id = trigger_bulk_reindex()
    
    if task_id:
        log_admin_activity(
            user_id=session['user_id'],
            action='solr_reindex',
            description="Started full Solr reindex"
        )
        return jsonify({"success": True, "message": "Reindexing started", "task_id": task_id})
    else:
        return jsonify({"success": False, "message": "Failed to start reindexing"}), 500


@admin_bp.route("/solr/status")
@admin_required
def solr_status():
    """Get Solr status"""
    try:
        from services.solr_client import solr_client
        if hasattr(current_app.extensions, 'solr') and current_app.extensions.get('solr'):
            doc_count = solr_client.count()
            return jsonify({
                "connected": True,
                "doc_count": doc_count,
                "db_count": Book.query.count()
            })
    except Exception as e:
        return jsonify({
            "connected": False,
            "error": str(e)
        })
    
    return jsonify({"connected": False})


@admin_bp.route("/solr/index-book/<int:book_id>", methods=["POST"])
@admin_required
def solr_index_book(book_id):
    """Index a single book in Solr"""
    book = Book.query.get_or_404(book_id)
    
    trigger_solr_index(book_id, delay=False)  # Immediate indexing
    
    return jsonify({
        "success": True,
        "message": f"Indexing {book.title}"
    })


# ===================== DEBUG ENDPOINTS =====================

@admin_bp.route("/debug-endpoints")
@admin_required
def debug_endpoints():
    """List all available admin endpoints"""
    import werkzeug.routing
    endpoints = []
    for rule in current_app.url_map.iter_rules():
        if rule.endpoint and rule.endpoint.startswith('admin.'):
            endpoints.append({
                'endpoint': rule.endpoint,
                'methods': list(rule.methods),
                'url': str(rule)
            })
    return jsonify(sorted(endpoints, key=lambda x: x['endpoint']))


# ===================== CONTEXT PROCESSORS =====================

@admin_bp.context_processor
def inject_workflow_counts():
    """Inject workflow counts for navigation badges"""
    try:
        # Get counts for workflow sections
        pending_acquisition = AcquisitionRequest.query.filter_by(status='pending').count()
        pending_cataloging = CatalogingQueue.query.filter_by(status='pending').count()
        active_checkouts = CirculationRecord.query.filter_by(status='active').count()
        pending_users = User.query.filter_by(approval_status='pending', is_deleted=False).count()
        pending_special = SpecialRequest.query.filter_by(status='pending').count()
        expiring_cards = LibraryCard.query.filter(
            LibraryCard.expiry_date >= datetime.utcnow(),
            LibraryCard.expiry_date <= datetime.utcnow() + timedelta(days=30)
        ).count()
        
        # Get counts for specific statuses
        overdue_items = CirculationRecord.query.filter(
            CirculationRecord.status == 'active',
            CirculationRecord.due_date < datetime.utcnow()
        ).count()
        
        active_reservations = Reservation.query.filter_by(status='active').count()
        total_fines = db.session.query(db.func.sum(Fine.amount)).filter_by(paid=False, waived=False).scalar() or 0
        
        # Get unread notifications for current admin
        unread_notifications = 0
        if 'user_id' in session:
            unread_notifications = Notification.query.filter_by(
                user_id=session['user_id'],
                is_read=False
            ).count()
        
        # Get total tags count
        all_books = Book.query.filter(
            Book.keywords.isnot(None),
            Book.is_deleted == False
        ).all()
        all_tags = set()
        for book in all_books:
            if book.keywords:
                all_tags.update(book.keywords)
        total_tags = len(all_tags)
        
        return {
            'pending_requests': pending_acquisition,
            'pending_cataloging': pending_cataloging,
            'active_checkouts': active_checkouts,
            'pending_users': pending_users,
            'pending_special_requests': pending_special,
            'overdue_items': overdue_items,
            'active_reservations': active_reservations,
            'total_fines': total_fines,
            'expiring_cards': expiring_cards,
            'unread_notifications': unread_notifications,
            'total_tags': total_tags,
            'now': datetime.utcnow()
        }
    except Exception as e:
        # Return default values if any error occurs
        current_app.logger.error(f"Error in workflow counts context processor: {e}")
        return {
            'pending_requests': 0,
            'pending_cataloging': 0,
            'active_checkouts': 0,
            'pending_users': 0,
            'pending_special_requests': 0,
            'overdue_items': 0,
            'active_reservations': 0,
            'total_fines': 0,
            'expiring_cards': 0,
            'unread_notifications': 0,
            'total_tags': 0,
            'now': datetime.utcnow()
        }


# ===================== ERROR HANDLERS =====================

@admin_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('admin/errors/404.html'), 404


@admin_bp.errorhandler(403)
def forbidden(error):
    """Handle 403 errors"""
    return render_template('admin/errors/403.html'), 403


@admin_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    current_app.logger.error(f"Internal server error: {error}")
    return render_template('admin/errors/500.html'), 500