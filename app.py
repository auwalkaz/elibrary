import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, g, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_cors import CORS
from flask_talisman import Talisman
from flask_compress import Compress
from prometheus_flask_exporter import PrometheusMetrics
from redis import Redis
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from celery import Celery
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import json
from config import config, get_config
from models import db, User, SystemSetting, AuditLog
from werkzeug.security import generate_password_hash
import datetime

# Load environment variables from .env file
load_dotenv()

# Initialize extensions
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
cache = Cache()
limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()
cors = CORS()
talisman = Talisman()
compress = Compress()
metrics = PrometheusMetrics.for_app_factory()
celery = Celery(__name__)
scheduler = BackgroundScheduler()

# Import blueprints with error handling
try:
    from routes.auth import auth_bp
    from routes.books import books_bp
    from routes.borrow import borrow_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.circulation import circulation_bp
    from routes.acquisition import acquisition_bp
    from routes.cataloging import cataloging_bp
    from routes.reports import reports_bp
    from routes.settings import settings_bp
    from routes.notifications import notifications_bp
except ImportError as e:
    print(f"❌ Error importing blueprints: {e}")
    print("Make sure all blueprint files exist in the routes directory")
    print("Required files:")
    print("  - routes/auth.py")
    print("  - routes/books.py")
    print("  - routes/borrow.py")
    print("  - routes/admin.py")
    print("  - routes/api.py")
    print("  - routes/circulation.py")
    print("  - routes/acquisition.py")
    print("  - routes/cataloging.py")
    print("  - routes/reports.py")
    print("  - routes/settings.py")
    print("  - routes/notifications.py")
    print("  - routes/__init__.py")
    raise

def create_app(config_name=None):
    """Application factory function"""
    if config_name is None:
        config_name = os.getenv('FLASK_CONFIG', 'default')
    
    app = Flask(__name__)
    
    # Load configuration
    config_obj = get_config(config_name)
    app.config.from_object(config_obj)
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    cors.init_app(app)
    compress.init_app(app)
    metrics.init_app(app)
    
    # Initialize Celery
    celery.conf.update(app.config)
    
    # Initialize Talisman (security headers) if in production
    if app.config['SESSION_COOKIE_SECURE']:
        talisman.init_app(
            app,
            content_security_policy={
                'default-src': "'self'",
                'img-src': "'self' data: https:",
                'script-src': "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com",
                'style-src': "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                'font-src': "'self' https://cdn.jsdelivr.net",
                'connect-src': "'self'",
            },
            force_https=app.config['SESSION_COOKIE_SECURE']
        )
    
    # Initialize Sentry for error tracking
    if app.config.get('SENTRY_DSN'):
        sentry_sdk.init(
            dsn=app.config['SENTRY_DSN'],
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
            environment=config_name
        )
    
    # Configure logging
    configure_logging(app)
    
    # Register context processors
    register_context_processors(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register template filters
    register_template_filters(app)
    
    # Register blueprints (without prefixes for main routes)
    register_blueprints(app)
    
    # Initialize scheduler
    init_scheduler(app)
    
    # Setup login manager
    setup_login_manager(app)
    
    # Shell context
    @app.shell_context_processor
    def make_shell_context():
        return {
            'db': db,
            'User': User,
            'SystemSetting': SystemSetting,
            'AuditLog': AuditLog,
            'datetime': datetime
        }
    
    # Before request handlers
    @app.before_request
    def before_request():
        """Set up before request"""
        # Store request start time for performance tracking
        g.start_time = datetime.datetime.utcnow()
        
        # Load settings into g if needed
        if not hasattr(g, 'settings'):
            g.settings = load_settings(app)
        
        # Track user session
        if hasattr(login_manager, '_user_id') and login_manager._user_id:
            update_user_session()
    
    # After request handlers
    @app.after_request
    def after_request(response):
        """After request processing"""
        # Log slow requests
        if hasattr(g, 'start_time'):
            duration = (datetime.datetime.utcnow() - g.start_time).total_seconds()
            if duration > 1.0:  # Log requests taking more than 1 second
                app.logger.warning(f"Slow request: {request.path} took {duration:.2f}s")
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
    
    return app

def configure_logging(app):
    """Configure application logging"""
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(app.config['LOG_FILE'])
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # File handler
    file_handler = RotatingFileHandler(
        app.config['LOG_FILE'],
        maxBytes=app.config['LOG_MAX_BYTES'],
        backupCount=app.config['LOG_BACKUP_COUNT']
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(getattr(logging, app.config['LOG_LEVEL']))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    
    # Add handlers
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(getattr(logging, app.config['LOG_LEVEL']))
    app.logger.info('🚀 Nigerian Army E-Library application startup')

def register_context_processors(app):
    """Register Jinja2 context processors"""
    @app.context_processor
    def inject_global_vars():
        """Inject global variables into templates"""
        return {
            'now': datetime.datetime.utcnow(),
            'app_name': app.config.get('APP_NAME', 'Nigerian Army E-Library'),
            'app_version': app.config.get('APP_VERSION', '2.0.0'),
            'settings': getattr(g, 'settings', {}),
            'cdn_url': app.config.get('CDN_URL', ''),
            'base_url': app.config.get('BASE_URL', 'http://localhost:5010'),
            'debug': app.debug
        }
    
    @app.context_processor
    def inject_user_notifications():
        """Inject user notification count"""
        if hasattr(login_manager, '_user_id') and login_manager._user_id:
            try:
                from models import Notification
                unread_count = Notification.query.filter_by(
                    user_id=login_manager._user_id,
                    is_read=False
                ).count()
                return {'unread_notifications': unread_count}
            except:
                pass
        return {'unread_notifications': 0}
    
    @app.context_processor
    def inject_feature_flags():
        """Inject feature flags into templates"""
        return {
            'feature_reading_progress': app.config.get('FEATURE_READING_PROGRESS', True),
            'feature_bookmarks': app.config.get('FEATURE_BOOKMARKS', True),
            'feature_annotations': app.config.get('FEATURE_ANNOTATIONS', True),
            'feature_wishlist': app.config.get('FEATURE_WISHLIST', True),
            'feature_reviews': app.config.get('FEATURE_REVIEWS', True),
            'feature_barcode_scanning': app.config.get('FEATURE_BARCODE_SCANNING', True),
        }
    
    # ADDED: CSRF token context processor
    @app.context_processor
    def inject_csrf_token():
        """Make csrf_token available in all templates"""
        return dict(csrf_token=generate_csrf)

def register_error_handlers(app):
    """Register error handlers"""
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.info(f'Page not found: {request.url}')
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f'Server Error: {error}')
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        app.logger.warning(f'Forbidden access: {request.url}')
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(429)
    def ratelimit_error(error):
        app.logger.warning(f'Rate limit exceeded: {request.remote_addr}')
        return render_template('errors/429.html'), 429
    
    @app.errorhandler(401)
    def unauthorized_error(error):
        flash('Please log in to access this page.')
        return redirect(url_for('auth.login', next=request.url))

def register_template_filters(app):
    """Register custom template filters"""
    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M'):
        if value is None:
            return ''
        return value.strftime(format)
    
    @app.template_filter('date')
    def format_date(value, format='%Y-%m-%d'):
        if value is None:
            return ''
        return value.strftime(format)
    
    @app.template_filter('time')
    def format_time(value, format='%H:%M'):
        if value is None:
            return ''
        return value.strftime(format)
    
    @app.template_filter('timesince')
    def timesince_filter(value):
        """Format timedelta as time since"""
        if not value:
            return ''
        delta = datetime.datetime.utcnow() - value
        if delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        return "just now"
    
    @app.template_filter('currency')
    def currency_filter(value):
        """Format as currency"""
        if value is None:
            return '₦0.00'
        return f"₦{value:,.2f}"
    
    @app.template_filter('file_size')
    def file_size_filter(size):
        """Format file size"""
        if size is None:
            return ''
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    @app.template_filter('pluralize')
    def pluralize_filter(number, singular='', plural='s'):
        if number == 1:
            return singular
        return plural

def register_blueprints(app):
    """Register Flask blueprints"""
    # Register blueprints with appropriate prefixes
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(books_bp)  # No prefix - root level access
    app.register_blueprint(borrow_bp, url_prefix='/borrow')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(circulation_bp, url_prefix='/circulation')
    app.register_blueprint(acquisition_bp, url_prefix='/acquisition')
    app.register_blueprint(cataloging_bp, url_prefix='/cataloging')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(notifications_bp, url_prefix='/notifications')
    
    # Health check endpoint (no authentication required)
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring"""
        return {
            'status': 'healthy',
            'message': 'Nigerian Army E-Library API is running',
            'version': app.config.get('APP_VERSION', '2.0.0'),
            'environment': os.getenv('FLASK_CONFIG', 'default'),
            'timestamp': datetime.datetime.utcnow().isoformat()
        }, 200
    
    # Robots.txt
    @app.route('/robots.txt')
    def robots_txt():
        """Serve robots.txt"""
        return app.send_static_file('robots.txt')

def init_scheduler(app):
    """Initialize background scheduler"""
    if app.config.get('BACKUP_ENABLED', False):
        try:
            from tasks.backup_tasks import perform_backup
            
            # Add backup job
            scheduler.add_job(
                func=lambda: perform_backup(app=app),
                trigger='cron',
                hour=2,
                minute=0,
                id='daily_backup',
                replace_existing=True
            )
            
            # Add cleanup job
            scheduler.add_job(
                func=lambda: cleanup_old_sessions(app),
                trigger='cron',
                hour=3,
                minute=0,
                id='cleanup_sessions',
                replace_existing=True
            )
            
            scheduler.start()
            app.logger.info("✅ Background scheduler started")
            
            # Shutdown scheduler when exiting the app
            atexit.register(lambda: scheduler.shutdown())
        except Exception as e:
            app.logger.error(f"❌ Failed to start scheduler: {e}")

def setup_login_manager(app):
    """Setup Flask-Login"""
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    @login_manager.unauthorized_handler
    def unauthorized():
        flash('⛔ Please log in to access this page.')
        return redirect(url_for('auth.login', next=request.path))
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '⛔ Please log in to access this page.'
    login_manager.login_message_category = 'error'

def load_settings(app):
    """Load system settings into cache"""
    settings = cache.get('system_settings')
    if settings is None:
        try:
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
            
            # Cache for 5 minutes
            cache.set('system_settings', settings, timeout=300)
        except:
            settings = {}
    return settings

def update_user_session():
    """Update user session tracking"""
    try:
        from models import UserSession
        from flask import session
        
        user_id = session.get('user_id')
        session_id = session.get('_id')
        
        if user_id and session_id:
            user_session = UserSession.query.filter_by(
                session_id=session_id,
                is_active=True
            ).first()
            
            if user_session:
                user_session.last_activity = datetime.datetime.utcnow()
                db.session.commit()
    except:
        pass

def cleanup_old_sessions(app):
    """Cleanup old user sessions"""
    with app.app_context():
        try:
            from models import UserSession
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            old_sessions = UserSession.query.filter(
                UserSession.login_time < cutoff,
                UserSession.is_active == True
            ).all()
            
            for session in old_sessions:
                session.is_active = False
                session.logout_time = datetime.datetime.utcnow()
            
            db.session.commit()
            app.logger.info(f"🧹 Cleaned up {len(old_sessions)} old sessions")
        except Exception as e:
            app.logger.error(f"❌ Session cleanup failed: {e}")

def migrate_database(app):
    """Add missing columns to existing database"""
    from sqlalchemy import text, inspect
    
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            
            # Get list of existing tables
            existing_tables = inspector.get_table_names()
            app.logger.info(f"📊 Existing tables: {existing_tables}")
            
            # ===================== ENHANCED USER TABLE MIGRATION =====================
            if 'users' in existing_tables:
                user_columns = [col['name'] for col in inspector.get_columns('users')]
                
                # Complete list of user columns to add from enhanced models
                user_columns_to_add = {
                    'created_at': 'TIMESTAMP',
                    'updated_at': 'TIMESTAMP',
                    'full_name': 'VARCHAR(200)',
                    'phone': 'VARCHAR(20)',
                    'service_number': 'VARCHAR(50)',
                    'rank': 'VARCHAR(50)',
                    'unit': 'VARCHAR(100)',
                    'address': 'TEXT',
                    'date_of_birth': 'DATE',
                    'profile_picture': 'VARCHAR(255)',
                    'bio': 'TEXT',
                    'preferences': 'JSON',
                    'permissions': 'JSON',
                    'email_verified': 'BOOLEAN DEFAULT 0',
                    'email_verified_at': 'TIMESTAMP',
                    'phone_verified': 'BOOLEAN DEFAULT 0',
                    'last_login_at': 'TIMESTAMP',
                    'last_login_ip': 'VARCHAR(45)',
                    'login_count': 'INTEGER DEFAULT 0',
                    'failed_login_attempts': 'INTEGER DEFAULT 0',
                    'locked_until': 'TIMESTAMP',
                    'two_factor_enabled': 'BOOLEAN DEFAULT 0',
                    'two_factor_secret': 'VARCHAR(32)',
                    'two_factor_backup_codes': 'JSON',
                    'two_factor_method': 'VARCHAR(20) DEFAULT "app"',
                    'approval_status': 'VARCHAR(20) DEFAULT "pending"',
                    'approved_by_id': 'INTEGER',
                    'approved_at': 'TIMESTAMP',
                    'rejection_reason': 'TEXT',
                    'membership_status': 'VARCHAR(20) DEFAULT "pending"',
                    'membership_type': 'VARCHAR(20) DEFAULT "regular"',
                    'membership_expiry': 'TIMESTAMP',
                    'security_clearance': 'VARCHAR(20) DEFAULT "basic"',
                    'requires_approval_for_restricted': 'BOOLEAN DEFAULT 1',
                    'total_books_borrowed': 'INTEGER DEFAULT 0',
                    'total_books_reserved': 'INTEGER DEFAULT 0',
                    'total_downloads': 'INTEGER DEFAULT 0',
                    'total_fines_paid': 'FLOAT DEFAULT 0',
                    'total_fines_waived': 'FLOAT DEFAULT 0',
                    'notification_settings': 'JSON',
                    'api_key': 'VARCHAR(64)',
                    'api_key_created_at': 'TIMESTAMP',
                    'api_key_expires_at': 'TIMESTAMP',
                    'is_deleted': 'BOOLEAN DEFAULT 0',
                    'deleted_at': 'TIMESTAMP',
                    'deleted_by_id': 'INTEGER',
                    'deleted_reason': 'VARCHAR(255)',
                    'created_by_id': 'INTEGER',
                    'updated_by_id': 'INTEGER'
                }
                
                for col_name, col_type in user_columns_to_add.items():
                    if col_name not in user_columns:
                        app.logger.info(f"  ➕ Adding {col_name} to users table...")
                        try:
                            db.session.execute(text(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}'))
                            db.session.commit()
                            app.logger.info(f"    ✅ Added {col_name}")
                        except Exception as e:
                            app.logger.warning(f"    ⚠️ Note: {col_name} may already exist - {e}")
                            db.session.rollback()
            
            # ===================== ENHANCED BOOK TABLE MIGRATION =====================
            if 'books' in existing_tables:
                book_columns = [col['name'] for col in inspector.get_columns('books')]
                
                # Complete list of book columns to add from enhanced models
                book_columns_to_add = {
                    'subtitle': 'VARCHAR(500)',
                    'subcategory': 'VARCHAR(100)',
                    'issn': 'VARCHAR(20)',
                    'doi': 'VARCHAR(100)',
                    'oclc_number': 'VARCHAR(50)',
                    'lccn': 'VARCHAR(50)',
                    'published_date': 'DATE',
                    'edition': 'VARCHAR(50)',
                    'volume': 'VARCHAR(50)',
                    'series': 'VARCHAR(255)',
                    'original_language': 'VARCHAR(50)',
                    'translator': 'VARCHAR(255)',
                    'dimensions': 'VARCHAR(50)',
                    'weight': 'FLOAT',
                    'binding': 'VARCHAR(50)',
                    'dewey_decimal': 'VARCHAR(20)',
                    'library_of_congress': 'VARCHAR(50)',
                    'subjects': 'JSON',
                    'keywords': 'JSON',
                    'audience': 'VARCHAR(50)',
                    'file_hash': 'VARCHAR(64)',
                    'file_format': 'VARCHAR(20)',
                    'drm_enabled': 'BOOLEAN DEFAULT 0',
                    'drm_type': 'VARCHAR(50)',
                    'concurrent_users': 'INTEGER DEFAULT 1',
                    'loan_period_days': 'INTEGER DEFAULT 14',
                    'allow_download': 'BOOLEAN DEFAULT 1',
                    'allow_print': 'BOOLEAN DEFAULT 1',
                    'allow_copy': 'BOOLEAN DEFAULT 0',
                    'watermark_enabled': 'BOOLEAN DEFAULT 0',
                    'reserved_copies': 'INTEGER DEFAULT 0',
                    'damaged_copies': 'INTEGER DEFAULT 0',
                    'lost_copies': 'INTEGER DEFAULT 0',
                    'reference_copies': 'INTEGER DEFAULT 0',
                    'floor': 'VARCHAR(10)',
                    'section': 'VARCHAR(50)',
                    'barcode': 'VARCHAR(50)',
                    'barcode_image': 'TEXT',
                    'cover_image_url': 'VARCHAR(500)',
                    'thumbnail_url': 'VARCHAR(500)',
                    'sample_url': 'VARCHAR(500)',
                    'preview_url': 'VARCHAR(500)',
                    'google_books_id': 'VARCHAR(50)',
                    'open_library_id': 'VARCHAR(50)',
                    'worldcat_id': 'VARCHAR(50)',
                    'amazon_url': 'VARCHAR(500)',
                    'goodreads_url': 'VARCHAR(500)',
                    'view_count': 'INTEGER DEFAULT 0',
                    'download_count': 'INTEGER DEFAULT 0',
                    'borrow_count': 'INTEGER DEFAULT 0',
                    'reserve_count': 'INTEGER DEFAULT 0',
                    'average_rating': 'FLOAT DEFAULT 0',
                    'review_count': 'INTEGER DEFAULT 0',
                    'wishlist_count': 'INTEGER DEFAULT 0',
                    'is_restricted': 'BOOLEAN DEFAULT 0',
                    'is_serial': 'BOOLEAN DEFAULT 0',
                    'is_archived': 'BOOLEAN DEFAULT 0',
                    'minimum_clearance': 'VARCHAR(20) DEFAULT "basic"',
                    'cataloging_status': 'VARCHAR(20) DEFAULT "pending"',
                    'cataloged_by_id': 'INTEGER',
                    'cataloged_at': 'TIMESTAMP',
                    'cataloging_notes': 'TEXT',
                    'marc_record': 'TEXT',
                    'marc_modified': 'TIMESTAMP',
                    'is_deleted': 'BOOLEAN DEFAULT 0',
                    'deleted_at': 'TIMESTAMP',
                    'deleted_by_id': 'INTEGER',
                    'deleted_reason': 'VARCHAR(255)',
                    'created_by_id': 'INTEGER',
                    'updated_by_id': 'INTEGER'
                }
                
                for col_name, col_type in book_columns_to_add.items():
                    if col_name not in book_columns:
                        app.logger.info(f"  ➕ Adding {col_name} to books table...")
                        try:
                            db.session.execute(text(f'ALTER TABLE books ADD COLUMN {col_name} {col_type}'))
                            db.session.commit()
                            app.logger.info(f"    ✅ Added {col_name}")
                        except Exception as e:
                            app.logger.warning(f"    ⚠️ Note: {col_name} may already exist - {e}")
                            db.session.rollback()
            
            # ===================== NEW ENHANCED TABLES =====================
            # List of all tables that should exist
            required_tables = [
                'users', 'books', 'library_cards', 'reading_history', 'wishlist',
                'reviews', 'bookmarks', 'reading_progress', 'reading_sessions',
                'annotations', 'download_logs', 'recent_activities',
                'special_requests', 'acquisition_requests', 'purchase_orders',
                'purchase_order_items', 'cataloging_queue', 'item_copies',
                'circulation_records', 'reservations', 'fines', 'notifications',
                'announcements', 'audit_logs', 'api_keys', 'backup_logs',
                'scheduled_reports', 'vendors', 'budgets', 'system_settings',
                'user_sessions'
            ]
            
            for table in required_tables:
                if table not in existing_tables:
                    app.logger.info(f"  ➕ Creating {table} table...")
                    db.create_all()
                    app.logger.info(f"    ✅ Created {table} table")
            
            app.logger.info("✅ Database migration complete!")
            
        except Exception as e:
            app.logger.error(f"❌ Migration error: {e}")
            db.session.rollback()

# Create the app instance FIRST
app = create_app(os.getenv('FLASK_CONFIG') or 'default')

# THEN define CLI commands (after app is created)
@app.cli.command("init-db")
def init_db():
    """Initialize the database."""
    with app.app_context():
        db.create_all()
        app.logger.info("✅ Database tables created")
        
        # Create default admin
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                email="admin@example.com",
                role="admin",
                full_name="System Administrator",
                approval_status='approved',
                membership_status='active',
                security_clearance='top_secret',
                email_verified=True
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            app.logger.info("✅ Admin user created (username: admin, password: admin123)")
        else:
            app.logger.info("ℹ️ Admin user already exists")
        
        # Create demo user
        if not User.query.filter_by(username="user").first():
            demo_user = User(
                username="user",
                email="user@example.com",
                role="user",
                full_name="Demo User",
                approval_status='approved',
                membership_status='active',
                security_clearance='basic',
                email_verified=True
            )
            demo_user.set_password("user123")
            db.session.add(demo_user)
            db.session.commit()
            app.logger.info("✅ Demo user created (username: user, password: user123)")
        else:
            app.logger.info("ℹ️ Demo user already exists")
        
        # Create default settings
        from models import SystemSetting
        default_settings = {
            'site_name': ('Nigerian Army E-Library', 'Site name', 'general'),
            'site_description': ('Official Digital Library of the Nigerian Army', 'Site description', 'general'),
            'items_per_page': ('20', 'Number of items per page', 'general'),
            'allow_registration': ('true', 'Allow user registration', 'security'),
            'require_email_verification': ('true', 'Require email verification', 'security'),
            'require_admin_approval': ('true', 'Require admin approval for new users', 'security'),
            'max_borrow_days': ('14', 'Maximum borrow days', 'circulation'),
            'max_borrow_books': ('5', 'Maximum books per patron', 'circulation'),
            'max_renewals': ('2', 'Maximum renewals allowed', 'circulation'),
            'fine_per_day': ('50.0', 'Fine per day (NGN)', 'fines'),
            'max_fine': ('5000.0', 'Maximum fine amount (NGN)', 'fines'),
            'enable_notifications': ('true', 'Enable notifications', 'notifications'),
            'enable_solr': ('false', 'Enable Solr search', 'search'),
            'backup_enabled': ('true', 'Enable automated backups', 'backup'),
            'backup_frequency': ('daily', 'Backup frequency', 'backup'),
            'retention_days': ('30', 'Backup retention days', 'backup'),
            'session_timeout': ('120', 'Session timeout in minutes', 'security'),
            'max_login_attempts': ('5', 'Max login attempts before lockout', 'security'),
            'lockout_minutes': ('30', 'Account lockout duration in minutes', 'security'),
        }
        
        for key, (value, description, category) in default_settings.items():
            if not SystemSetting.query.filter_by(key=key).first():
                setting = SystemSetting(
                    key=key,
                    value=value,
                    description=description,
                    category=category
                )
                if value.lower() in ['true', 'false']:
                    setting.type = 'boolean'
                elif value.replace('.', '').isdigit():
                    setting.type = 'float' if '.' in value else 'integer'
                db.session.add(setting)
        
        db.session.commit()
        app.logger.info("✅ Default settings created")


if __name__ == "__main__":
    with app.app_context():
        print("\n" + "="*70)
        print("🚀 Starting Nigerian Army E-Library System v2.0")
        print("="*70)
        
        # Show current configuration
        config_name = os.getenv('FLASK_CONFIG', 'default')
        print(f"📋 Configuration: {config_name}")
        print(f"🔧 Debug mode: {app.debug}")
        print(f"📁 Upload folder: {app.config.get('UPLOAD_FOLDER')}")
        print(f"📁 Backup folder: {app.config.get('BACKUP_PATH')}")
        print(f"📁 Log folder: {os.path.dirname(app.config.get('LOG_FILE'))}")
        
        # Create necessary directories
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config.get('BOOK_UPLOAD_FOLDER', os.path.join(app.config['UPLOAD_FOLDER'], 'books')), exist_ok=True)
        os.makedirs(app.config.get('COVER_UPLOAD_FOLDER', os.path.join(app.config['UPLOAD_FOLDER'], 'covers')), exist_ok=True)
        os.makedirs(app.config.get('BACKUP_PATH', 'backups'), exist_ok=True)
        os.makedirs(os.path.dirname(app.config['LOG_FILE']), exist_ok=True)
        
        # Create tables if they don't exist
        db.create_all()
        print("✅ Database tables created/verified")
        
        # Run migration for existing tables
        print("\n📦 Running database migration...")
        migrate_database(app)
        
        # Create default users if they don't exist
        print("\n👤 Checking default users...")
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                email="admin@example.com",
                role="admin",
                full_name="System Administrator",
                approval_status='approved',
                membership_status='active',
                security_clearance='top_secret',
                email_verified=True
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin user created")
        else:
            print("✅ Admin user already exists")
        
        if not User.query.filter_by(username="user").first():
            demo_user = User(
                username="user",
                email="user@example.com",
                role="user",
                full_name="Demo User",
                approval_status='approved',
                membership_status='active',
                security_clearance='basic',
                email_verified=True
            )
            demo_user.set_password("user123")
            db.session.add(demo_user)
            db.session.commit()
            print("✅ Demo user created")
        else:
            print("✅ Demo user already exists")
        
        print("\n" + "="*70)
        print(f"🌐 Server running at: http://localhost:{app.config.get('PORT', 5010)}")
        print(f"📚 Library home: http://localhost:{app.config.get('PORT', 5010)}/")
        print(f"🔑 Admin login: http://localhost:{app.config.get('PORT', 5010)}/auth/login (admin/admin123)")
        print(f"👤 Demo login: http://localhost:{app.config.get('PORT', 5010)}/auth/login (user/user123)")
        print(f"📊 Admin dashboard: http://localhost:{app.config.get('PORT', 5010)}/admin/dashboard")
        print(f"🔍 Test endpoint: http://localhost:{app.config.get('PORT', 5010)}/test-books")
        print(f"⚙️  Environment: {config_name}")
        print(f"📝 Log file: {app.config.get('LOG_FILE')}")
        print("="*70 + "\n")

    # Get port from environment or use default 5010
    port = int(os.environ.get('PORT', 5010))
    app.run(debug=app.debug, host='0.0.0.0', port=port)