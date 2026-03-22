import os
from datetime import timedelta

class Config:
    # Base directory - will be overridden by environment-specific configs
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB limit
    
    # Create upload subfolders
    BOOK_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "books")
    COVER_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "covers")
    SAMPLE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "samples")
    BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")
    LOG_FOLDER = os.path.join(BASE_DIR, "logs")
    
    # Database
    DATABASE_PATH = os.path.join(BASE_DIR, "library.db")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    
    # Security - use default for all configs, will be overridden in production
    SECRET_KEY = os.environ.get('SECRET_KEY') or "dev-secret-key-change-in-production"
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or SECRET_KEY
    WTF_CSRF_TIME_LIMIT = 3600
    
    # Rate Limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200/day;50/hour"
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True
    
    # Cache
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_KEY_PREFIX = "nael_cache:"
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {"pdf", "epub", "mobi", "djvu"}
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
    
    # Pagination
    BOOKS_PER_PAGE = 12
    USERS_PER_PAGE = 20
    ADMIN_ITEMS_PER_PAGE = 50
    
    # Borrowing settings
    MAX_BORROW_DAYS = 14
    MAX_BORROW_BOOKS = 5
    MAX_RENEWALS = 2
    FINE_PER_DAY = 50  # Naira
    MAX_FINE_AMOUNT = 5000  # Maximum fine cap
    FINE_GRACE_PERIOD_DAYS = 0  # Days before fines start accruing
    
    # Reservation settings
    RESERVATION_EXPIRY_DAYS = 3  # Days to pick up reserved book
    MAX_ACTIVE_RESERVATIONS = 3  # Max active reservations per user
    
    # DOWNLOAD RESTRICTIONS
    MAX_DOWNLOADS_PER_DAY = 5      # Downloads per day
    MAX_DOWNLOADS_PER_WEEK = 20     # Downloads per week
    MAX_DOWNLOADS_PER_MONTH = 50    # Downloads per month
    
    # Application settings
    APP_NAME = "Nigerian Army E-Library"
    APP_VERSION = "2.0.0"
    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5010')
    
    # ========== EMAIL CONFIGURATION ==========
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@army.mil.ng')
    MAIL_MAX_EMAILS = 100
    
    # ========== SMS SETTINGS (Africa's Talking) ==========
    SMS_ENABLED = os.environ.get('SMS_ENABLED', 'False').lower() == 'true'
    SMS_API_KEY = os.environ.get('SMS_API_KEY')
    SMS_SENDER_ID = os.environ.get('SMS_SENDER_ID', 'NAEL')
    
    # ========== WHATSAPP NOTIFICATION CONFIGURATION ==========
    # Using Twilio WhatsApp API
    WHATSAPP_ENABLED = os.environ.get('WHATSAPP_ENABLED', 'False').lower() == 'true'
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    # WhatsApp Business API (if you have official approval)
    WHATSAPP_BUSINESS_API_URL = os.environ.get('WHATSAPP_BUSINESS_API_URL')
    WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    
    # WhatsApp message templates
    WHATSAPP_APPROVAL_TEMPLATE = os.environ.get('WHATSAPP_APPROVAL_TEMPLATE', 'registration_approved')
    WHATSAPP_REJECTION_TEMPLATE = os.environ.get('WHATSAPP_REJECTION_TEMPLATE', 'registration_rejected')
    WHATSAPP_WELCOME_TEMPLATE = os.environ.get('WHATSAPP_WELCOME_TEMPLATE', 'welcome_message')
    
    @property
    def WHATSAPP_CONFIGURED(self):
        """Check if WhatsApp is properly configured"""
        if not self.WHATSAPP_ENABLED:
            return False
        return all([
            self.TWILIO_ACCOUNT_SID,
            self.TWILIO_AUTH_TOKEN,
            self.TWILIO_WHATSAPP_NUMBER
        ])
    
    # ========== NIGERIAN ARMY OAUTH CONFIGURATION ==========
    # Get these from NA IT department
    NA_OAUTH_CLIENT_ID = os.environ.get('NA_OAUTH_CLIENT_ID')
    NA_OAUTH_CLIENT_SECRET = os.environ.get('NA_OAUTH_CLIENT_SECRET')
    NA_OAUTH_AUTHORIZATION_URL = os.environ.get('NA_OAUTH_AUTHORIZATION_URL', 'https://auth.army.mil.ng/oauth/authorize')
    NA_OAUTH_TOKEN_URL = os.environ.get('NA_OAUTH_TOKEN_URL', 'https://auth.army.mil.ng/oauth/token')
    NA_OAUTH_USERINFO_URL = os.environ.get('NA_OAUTH_USERINFO_URL', 'https://auth.army.mil.ng/oauth/userinfo')
    NA_OAUTH_SCOPE = os.environ.get('NA_OAUTH_SCOPE', 'email profile service_number rank unit')
    
    @property
    def NA_OAUTH_CONFIGURED(self):
        """Check if NA OAuth is properly configured"""
        return all([
            self.NA_OAUTH_CLIENT_ID,
            self.NA_OAUTH_CLIENT_SECRET,
            self.NA_OAUTH_CLIENT_ID != 'your_actual_client_id_from_NA_IT',
            self.NA_OAUTH_CLIENT_SECRET != 'your_actual_client_secret_from_NA_IT'
        ])
    
    # ========== ADMIN REGISTRATION SECURITY ==========
    ADMIN_REGISTRATION_ENABLED = os.environ.get('ADMIN_REGISTRATION_ENABLED', 'False').lower() == 'true'
    ADMIN_SECRET_KEY = os.environ.get('ADMIN_SECRET_KEY', 'change-this-in-production')
    ADMIN_CODE = os.environ.get('ADMIN_CODE', 'change-this-in-production')
    
    # ========== TWO-FACTOR AUTHENTICATION ==========
    TWO_FACTOR_ENABLED = os.environ.get('TWO_FACTOR_ENABLED', 'False').lower() == 'true'
    TWO_FACTOR_ISSUER = "Nigerian Army E-Library"
    TWO_FACTOR_REQUIRED_ROLES = ['admin', 'librarian']
    TWO_FACTOR_BACKUP_CODES_COUNT = 10
    
    # ========== SOLR Configuration ==========
    SOLR_ENABLED = os.environ.get('SOLR_ENABLED', 'False').lower() == 'true'
    SOLR_URL = os.environ.get('SOLR_URL', 'http://localhost:8983/solr/')
    SOLR_CORE = os.environ.get('SOLR_CORE', 'nigerian_army_library')
    SOLR_TIMEOUT = int(os.environ.get('SOLR_TIMEOUT', 10))
    SOLR_BATCH_SIZE = int(os.environ.get('SOLR_BATCH_SIZE', 100))
    
    # ========== Celery Configuration (for async tasks) ==========
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'Africa/Lagos'
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    
    # Celery Beat Schedule (periodic tasks)
    CELERY_BEAT_SCHEDULE = {
        'check-overdue-items': {
            'task': 'tasks.circulation_tasks.check_overdue_items',
            'schedule': timedelta(hours=1),
        },
        'send-due-date-reminders': {
            'task': 'tasks.circulation_tasks.send_due_date_reminders',
            'schedule': timedelta(hours=6),
        },
        'expire-reservations': {
            'task': 'tasks.circulation_tasks.expire_reservations',
            'schedule': timedelta(hours=1),
        },
        'generate-scheduled-reports': {
            'task': 'tasks.report_tasks.generate_scheduled_reports',
            'schedule': timedelta(minutes=30),
        },
        'cleanup-old-sessions': {
            'task': 'tasks.cleanup_tasks.cleanup_old_sessions',
            'schedule': timedelta(days=1),
        },
        'perform-backup': {
            'task': 'tasks.backup_tasks.perform_automated_backup',
            'schedule': timedelta(days=1),
        },
    }
    
    # ========== Online Reading Configuration ==========
    # PDF.js settings
    PDFJS_PATH = os.path.join(BASE_DIR, 'static', 'pdfjs')
    PDF_VIEWER_MODE = 'pdfjs'  # 'pdfjs' or 'embed' or 'custom'
    
    # Reading session settings
    TRACK_READING_PROGRESS = True  # Track user reading progress
    AUTO_SAVE_INTERVAL = 30  # Auto-save reading progress every 30 seconds
    MAX_BOOKMARKS_PER_BOOK = 50  # Maximum bookmarks per user per book
    MAX_ANNOTATIONS_PER_BOOK = 100  # Maximum annotations per user per book
    
    # Reading access control
    ALLOW_PUBLIC_READING = False  # Allow reading without login
    REQUIRE_LIBRARY_CARD_FOR_READING = True  # Require library card to read
    
    # Reading analytics
    COLLECT_READING_ANALYTICS = True  # Track reading sessions for analytics
    RETAIN_READING_SESSIONS_DAYS = 30  # How long to keep session data
    
    # PDF text extraction for search
    EXTRACT_PDF_TEXT_FOR_SEARCH = False  # Set to True to extract text for Solr
    PDF_TEXT_EXTRACTION_METHOD = 'pypdf2'  # 'pypdf2' or 'textract' or 'pdfminer'
    PDF_TEXT_EXTRACTION_TIMEOUT = 60  # Timeout in seconds
    
    # Reading interface customization
    DEFAULT_ZOOM_LEVEL = 100  # Default zoom percentage
    ALLOW_ZOOM_CONTROLS = True
    ALLOW_FULLSCREEN = True
    ALLOW_TEXT_SELECTION = True  # Allow users to select/copy text
    ALLOW_PRINTING = False  # Allow printing of PDFs (security consideration)
    ALLOW_DOWNLOAD = False  # Allow downloading of PDFs (set to True if you want users to download)
    
    # Reading limits
    MAX_CONCURRENT_READERS_PER_BOOK = 10  # Max simultaneous readers for same book
    READING_TIMEOUT_MINUTES = 30  # Session timeout for inactive readers
    
    # ========== BACKUP SETTINGS ==========
    BACKUP_ENABLED = os.environ.get('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_PATH = os.path.join(BASE_DIR, "backups")
    BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', 30))
    AUTO_BACKUP_SCHEDULE = os.environ.get('AUTO_BACKUP_SCHEDULE', '0 2 * * *')  # Daily at 2 AM
    
    # AWS S3 (for cloud backups)
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME', 'nael-backups')
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN')
    
    # ========== MONITORING ==========
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    PROMETHEUS_METRICS = os.environ.get('PROMETHEUS_METRICS', 'False').lower() == 'true'
    PROMETHEUS_PORT = int(os.environ.get('PROMETHEUS_PORT', 9100))
    
    # ========== API SETTINGS ==========
    API_ENABLED = os.environ.get('API_ENABLED', 'True').lower() == 'true'
    API_RATE_LIMIT = os.environ.get('API_RATE_LIMIT', '1000/day;100/hour')
    API_KEY_EXPIRY_DAYS = int(os.environ.get('API_KEY_EXPIRY_DAYS', 365))
    API_DOCS_ENABLED = os.environ.get('API_DOCS_ENABLED', 'True').lower() == 'true'
    
    # ========== FEATURE FLAGS ==========
    FEATURE_READING_PROGRESS = os.environ.get('FEATURE_READING_PROGRESS', 'True').lower() == 'true'
    FEATURE_BOOKMARKS = os.environ.get('FEATURE_BOOKMARKS', 'True').lower() == 'true'
    FEATURE_ANNOTATIONS = os.environ.get('FEATURE_ANNOTATIONS', 'True').lower() == 'true'
    FEATURE_WISHLIST = os.environ.get('FEATURE_WISHLIST', 'True').lower() == 'true'
    FEATURE_REVIEWS = os.environ.get('FEATURE_REVIEWS', 'True').lower() == 'true'
    FEATURE_SOCIAL_SHARING = os.environ.get('FEATURE_SOCIAL_SHARING', 'False').lower() == 'true'
    FEATURE_BARCODE_SCANNING = os.environ.get('FEATURE_BARCODE_SCANNING', 'True').lower() == 'true'
    FEATURE_RFID = os.environ.get('FEATURE_RFID', 'False').lower() == 'true'
    
    # ========== LOGGING ==========
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', os.path.join(BASE_DIR, 'logs', 'app.log'))
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    
    # Development-specific settings
    SESSION_COOKIE_SECURE = False  # HTTP in development
    EXPLAIN_TEMPLATE_LOADING = False
    DEBUG_TB_ENABLED = True  # Flask-DebugToolbar
    
    # Better error messages
    PROPAGATE_EXCEPTIONS = True
    
    # FIXED: Set BASE_DIR to the correct elibrary1 path
    BASE_DIR = '/home/auwalkz/elibrary1'
    
    # Override paths with correct elibrary1 paths
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    BOOK_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "books")
    COVER_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "covers")
    SAMPLE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "samples")
    BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")
    LOG_FOLDER = os.path.join(BASE_DIR, "logs")
    DATABASE_PATH = os.path.join(BASE_DIR, "library.db")
    
    # Update database URI
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_ECHO = True  # Log SQL queries
    
    # Development download limits (can be higher for testing)
    MAX_DOWNLOADS_PER_DAY = 10      # Higher for testing
    MAX_DOWNLOADS_PER_WEEK = 40
    MAX_DOWNLOADS_PER_MONTH = 100
    
    # ========== DEVELOPMENT ADMIN REGISTRATION ==========
    ADMIN_REGISTRATION_ENABLED = True  # Enable for testing
    ADMIN_SECRET_KEY = os.environ.get('ADMIN_SECRET_KEY', 'dev-secret-key-123')
    ADMIN_CODE = os.environ.get('ADMIN_CODE', 'dev-admin-code-456')
    
    # ========== DEVELOPMENT TWO-FACTOR ==========
    TWO_FACTOR_ENABLED = False  # Disable for easier testing
    TWO_FACTOR_REQUIRED_ROLES = []  # No roles required
    
    # ========== DEVELOPMENT SOLR SETTINGS ==========
    SOLR_ENABLED = os.environ.get('SOLR_ENABLED', 'False').lower() == 'true'
    SOLR_URL = os.environ.get('SOLR_URL', 'http://localhost:8983/solr/')
    SOLR_CORE = os.environ.get('SOLR_CORE', 'nigerian_army_library_dev')
    
    # ========== DEVELOPMENT CELERY SETTINGS ==========
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_TASK_ALWAYS_EAGER = False  # Set to True for synchronous tasks (easier debugging)
    CELERY_TASK_EAGER_PROPAGATES = True
    
    # ========== DEVELOPMENT READING SETTINGS ==========
    EXTRACT_PDF_TEXT_FOR_SEARCH = True  # Enable in development
    ALLOW_PUBLIC_READING = True  # Allow testing without login
    REQUIRE_LIBRARY_CARD_FOR_READING = False  # Don't require library card in dev
    ALLOW_DOWNLOAD = True  # Allow downloads in dev for testing
    ALLOW_PRINTING = True  # Allow printing in dev
    COLLECT_READING_ANALYTICS = True
    
    # Increase limits for development
    MAX_BOOKMARKS_PER_BOOK = 100
    MAX_ANNOTATIONS_PER_BOOK = 200
    
    # ========== DEVELOPMENT BACKUP ==========
    BACKUP_ENABLED = False  # Disable backups in development
    AUTO_BACKUP_SCHEDULE = None
    
    # ========== DEVELOPMENT API ==========
    API_RATE_LIMIT = "10000/day;1000/hour"  # Much higher in development
    API_KEY_EXPIRY_DAYS = 3650  # 10 years
    
    # ========== DEVELOPMENT WHATSAPP ==========
    WHATSAPP_ENABLED = os.environ.get('WHATSAPP_ENABLED', 'False').lower() == 'true'
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', 'test_account_sid')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', 'test_auth_token')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    @property
    def WHATSAPP_CONFIGURED(self):
        """In development, WhatsApp is optional"""
        return self.WHATSAPP_ENABLED and bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_ACCOUNT_SID != 'test_account_sid')
    
    # ========== DEVELOPMENT NA OAUTH ==========
    # In development, you can use test credentials or disable
    NA_OAUTH_CLIENT_ID = os.environ.get('NA_OAUTH_CLIENT_ID')
    NA_OAUTH_CLIENT_SECRET = os.environ.get('NA_OAUTH_CLIENT_SECRET')
    
    @property
    def NA_OAUTH_CONFIGURED(self):
        """In development, we can still use OAuth if credentials are provided"""
        return bool(self.NA_OAUTH_CLIENT_ID and self.NA_OAUTH_CLIENT_SECRET)


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    
    # Use in-memory database for tests
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ECHO = False
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False
    
    # Disable rate limiting for tests
    RATELIMIT_ENABLED = False
    
    # Test-specific settings
    UPLOAD_FOLDER = os.path.join(Config.BASE_DIR, "test_uploads")
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1MB limit for tests
    
    # Testing download limits
    MAX_DOWNLOADS_PER_DAY = 100      # Unlimited for testing
    MAX_DOWNLOADS_PER_WEEK = 500
    MAX_DOWNLOADS_PER_MONTH = 2000
    
    # ========== TESTING ADMIN REGISTRATION ==========
    ADMIN_REGISTRATION_ENABLED = True  # Enable for testing
    ADMIN_SECRET_KEY = 'test-secret-key'
    ADMIN_CODE = 'test-admin-code'
    
    # ========== TESTING TWO-FACTOR ==========
    TWO_FACTOR_ENABLED = False
    
    # ========== TESTING SOLR SETTINGS ==========
    SOLR_ENABLED = False  # Disable Solr for tests
    
    # ========== TESTING CELERY SETTINGS ==========
    CELERY_TASK_ALWAYS_EAGER = True  # Run tasks synchronously for testing
    CELERY_TASK_EAGER_PROPAGATES = True
    
    # ========== TESTING READING SETTINGS ==========
    EXTRACT_PDF_TEXT_FOR_SEARCH = False  # Disable to speed up tests
    ALLOW_PUBLIC_READING = True
    REQUIRE_LIBRARY_CARD_FOR_READING = False
    COLLECT_READING_ANALYTICS = False  # Disable analytics in tests
    RETAIN_READING_SESSIONS_DAYS = 1  # Short retention for tests
    
    # ========== TESTING BACKUP ==========
    BACKUP_ENABLED = False
    
    # ========== TESTING API ==========
    API_ENABLED = True
    API_RATE_LIMIT = "10000/minute"  # Unlimited for tests
    
    # ========== TESTING WHATSAPP ==========
    WHATSAPP_ENABLED = False
    
    # ========== TESTING NA OAUTH ==========
    NA_OAUTH_CLIENT_ID = 'test_client_id'
    NA_OAUTH_CLIENT_SECRET = 'test_client_secret'
    
    @property
    def NA_OAUTH_CONFIGURED(self):
        return True


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    
    # Override security settings for production
    SESSION_COOKIE_SECURE = True  # HTTPS only
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'  # More strict in production
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)  # Shorter sessions
    
    # Production cache
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Production rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'WARNING')
    LOG_FILE = os.environ.get('LOG_FILE', '/var/log/nael/app.log')
    
    # Production download limits (stricter)
    MAX_DOWNLOADS_PER_DAY = 5
    MAX_DOWNLOADS_PER_WEEK = 15
    MAX_DOWNLOADS_PER_MONTH = 40
    
    # ========== PRODUCTION ADMIN REGISTRATION ==========
    ADMIN_REGISTRATION_ENABLED = os.environ.get('ADMIN_REGISTRATION_ENABLED', 'False').lower() == 'true'
    
    @property
    def ADMIN_SECRET_KEY(self):
        key = os.environ.get('ADMIN_SECRET_KEY')
        if not key and self.ADMIN_REGISTRATION_ENABLED:
            raise ValueError("ADMIN_SECRET_KEY must be set in production environment when admin registration is enabled")
        return key or 'change-this-in-production'
    
    @property
    def ADMIN_CODE(self):
        code = os.environ.get('ADMIN_CODE')
        if not code and self.ADMIN_REGISTRATION_ENABLED:
            raise ValueError("ADMIN_CODE must be set in production environment when admin registration is enabled")
        return code or 'change-this-in-production'
    
    # ========== PRODUCTION TWO-FACTOR ==========
    TWO_FACTOR_ENABLED = os.environ.get('TWO_FACTOR_ENABLED', 'True').lower() == 'true'
    TWO_FACTOR_REQUIRED_ROLES = os.environ.get('TWO_FACTOR_REQUIRED_ROLES', 'admin,librarian').split(',')
    
    # ========== PRODUCTION SOLR SETTINGS ==========
    SOLR_ENABLED = os.environ.get('SOLR_ENABLED', 'True').lower() == 'true'
    SOLR_URL = os.environ.get('SOLR_URL', 'http://solr:8983/solr/')  # Docker service name
    SOLR_CORE = os.environ.get('SOLR_CORE', 'nigerian_army_library_prod')
    SOLR_TIMEOUT = int(os.environ.get('SOLR_TIMEOUT', 30))  # Longer timeout in production
    
    # ========== PRODUCTION CELERY SETTINGS ==========
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_WORKER_CONCURRENCY = int(os.environ.get('CELERY_WORKER_CONCURRENCY', 4))
    CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.environ.get('CELERY_WORKER_MAX_TASKS_PER_CHILD', 100))
    
    # ========== PRODUCTION READING SETTINGS ==========
    EXTRACT_PDF_TEXT_FOR_SEARCH = os.environ.get('EXTRACT_PDF_TEXT_FOR_SEARCH', 'True').lower() == 'true'
    PDF_TEXT_EXTRACTION_METHOD = os.environ.get('PDF_TEXT_EXTRACTION_METHOD', 'textract')
    
    # Stricter access control
    ALLOW_PUBLIC_READING = False
    REQUIRE_LIBRARY_CARD_FOR_READING = True
    
    # Security settings
    ALLOW_DOWNLOAD = os.environ.get('ALLOW_DOWNLOAD', 'False').lower() == 'true'
    ALLOW_PRINTING = os.environ.get('ALLOW_PRINTING', 'False').lower() == 'true'
    ALLOW_TEXT_SELECTION = os.environ.get('ALLOW_TEXT_SELECTION', 'True').lower() == 'true'
    
    # Limits
    MAX_CONCURRENT_READERS_PER_BOOK = int(os.environ.get('MAX_CONCURRENT_READERS_PER_BOOK', 5))
    READING_TIMEOUT_MINUTES = int(os.environ.get('READING_TIMEOUT_MINUTES', 15))
    
    # ========== PRODUCTION BACKUP ==========
    BACKUP_ENABLED = os.environ.get('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_PATH = os.environ.get('BACKUP_PATH', '/var/backups/nael')
    BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', 30))
    
    # AWS S3 for backups
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME')
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    
    # ========== PRODUCTION MONITORING ==========
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    PROMETHEUS_METRICS = os.environ.get('PROMETHEUS_METRICS', 'True').lower() == 'true'
    
    # ========== PRODUCTION API ==========
    API_ENABLED = os.environ.get('API_ENABLED', 'True').lower() == 'true'
    API_RATE_LIMIT = os.environ.get('API_RATE_LIMIT', '1000/day;100/hour')
    API_KEY_EXPIRY_DAYS = int(os.environ.get('API_KEY_EXPIRY_DAYS', 365))
    
    # ========== PRODUCTION WHATSAPP ==========
    @property
    def WHATSAPP_ENABLED(self):
        return os.environ.get('WHATSAPP_ENABLED', 'False').lower() == 'true'
    
    @property
    def TWILIO_ACCOUNT_SID(self):
        sid = os.environ.get('TWILIO_ACCOUNT_SID')
        if self.WHATSAPP_ENABLED and not sid:
            raise ValueError("TWILIO_ACCOUNT_SID must be set in production when WhatsApp is enabled")
        return sid
    
    @property
    def TWILIO_AUTH_TOKEN(self):
        token = os.environ.get('TWILIO_AUTH_TOKEN')
        if self.WHATSAPP_ENABLED and not token:
            raise ValueError("TWILIO_AUTH_TOKEN must be set in production when WhatsApp is enabled")
        return token
    
    @property
    def TWILIO_WHATSAPP_NUMBER(self):
        return os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    @property
    def WHATSAPP_CONFIGURED(self):
        """Check if WhatsApp is properly configured in production"""
        if not self.WHATSAPP_ENABLED:
            return False
        return all([
            self.TWILIO_ACCOUNT_SID,
            self.TWILIO_AUTH_TOKEN,
            self.TWILIO_WHATSAPP_NUMBER
        ])
    
    # ========== PRODUCTION NA OAUTH ==========
    # These MUST be set in production environment variables
    @property
    def NA_OAUTH_CLIENT_ID(self):
        client_id = os.environ.get('NA_OAUTH_CLIENT_ID')
        if not client_id:
            raise ValueError("NA_OAUTH_CLIENT_ID must be set in production environment")
        return client_id
    
    @property
    def NA_OAUTH_CLIENT_SECRET(self):
        client_secret = os.environ.get('NA_OAUTH_CLIENT_SECRET')
        if not client_secret:
            raise ValueError("NA_OAUTH_CLIENT_SECRET must be set in production environment")
        return client_secret
    
    @property
    def NA_OAUTH_AUTHORIZATION_URL(self):
        return os.environ.get('NA_OAUTH_AUTHORIZATION_URL', 'https://auth.army.mil.ng/oauth/authorize')
    
    @property
    def NA_OAUTH_TOKEN_URL(self):
        return os.environ.get('NA_OAUTH_TOKEN_URL', 'https://auth.army.mil.ng/oauth/token')
    
    @property
    def NA_OAUTH_USERINFO_URL(self):
        return os.environ.get('NA_OAUTH_USERINFO_URL', 'https://auth.army.mil.ng/oauth/userinfo')
    
    @property
    def NA_OAUTH_SCOPE(self):
        return os.environ.get('NA_OAUTH_SCOPE', 'email profile service_number rank unit')
    
    @property
    def NA_OAUTH_CONFIGURED(self):
        """Check if NA OAuth is properly configured in production"""
        return all([
            os.environ.get('NA_OAUTH_CLIENT_ID'),
            os.environ.get('NA_OAUTH_CLIENT_SECRET')
        ])
    
    @property
    def SECRET_KEY(self):
        """Validate SECRET_KEY only when accessed in production"""
        key = os.environ.get('SECRET_KEY')
        if not key:
            raise ValueError("SECRET_KEY must be set in production environment")
        return key
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        """Validate DATABASE_URL only when accessed in production"""
        uri = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')
        if not uri:
            raise ValueError("DATABASE_URL must be set in production environment")
        return uri


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# Helper function to get config
def get_config(config_name=None):
    """Get configuration by name, default to development"""
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    config_class = config.get(config_name, DevelopmentConfig)
    
    # Create folders if they don't exist
    config_instance = config_class()
    
    # Create necessary directories
    os.makedirs(config_instance.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config_instance.BOOK_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config_instance.COVER_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config_instance.SAMPLE_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config_instance.BACKUP_FOLDER, exist_ok=True)
    os.makedirs(os.path.dirname(config_instance.LOG_FILE), exist_ok=True)
    
    return config_instance