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
    WHATSAPP_ENABLED = os.environ.get('WHATSAPP_ENABLED', 'False').lower() == 'true'
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    WHATSAPP_BUSINESS_API_URL = os.environ.get('WHATSAPP_BUSINESS_API_URL')
    WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    WHATSAPP_APPROVAL_TEMPLATE = os.environ.get('WHATSAPP_APPROVAL_TEMPLATE', 'registration_approved')
    WHATSAPP_REJECTION_TEMPLATE = os.environ.get('WHATSAPP_REJECTION_TEMPLATE', 'registration_rejected')
    WHATSAPP_WELCOME_TEMPLATE = os.environ.get('WHATSAPP_WELCOME_TEMPLATE', 'welcome_message')
    
    @property
    def WHATSAPP_CONFIGURED(self):
        if not self.WHATSAPP_ENABLED:
            return False
        return all([
            self.TWILIO_ACCOUNT_SID,
            self.TWILIO_AUTH_TOKEN,
            self.TWILIO_WHATSAPP_NUMBER
        ])
    
    # ========== NIGERIAN ARMY OAUTH CONFIGURATION ==========
    NA_OAUTH_CLIENT_ID = os.environ.get('NA_OAUTH_CLIENT_ID')
    NA_OAUTH_CLIENT_SECRET = os.environ.get('NA_OAUTH_CLIENT_SECRET')
    NA_OAUTH_AUTHORIZATION_URL = os.environ.get('NA_OAUTH_AUTHORIZATION_URL', 'https://auth.army.mil.ng/oauth/authorize')
    NA_OAUTH_TOKEN_URL = os.environ.get('NA_OAUTH_TOKEN_URL', 'https://auth.army.mil.ng/oauth/token')
    NA_OAUTH_USERINFO_URL = os.environ.get('NA_OAUTH_USERINFO_URL', 'https://auth.army.mil.ng/oauth/userinfo')
    NA_OAUTH_SCOPE = os.environ.get('NA_OAUTH_SCOPE', 'email profile service_number rank unit')
    
    @property
    def NA_OAUTH_CONFIGURED(self):
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
    
    # ========== Celery Configuration ==========
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'Africa/Lagos'
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 30 * 60
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    
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
    PDFJS_PATH = os.path.join(BASE_DIR, 'static', 'pdfjs')
    PDF_VIEWER_MODE = 'pdfjs'
    TRACK_READING_PROGRESS = True
    AUTO_SAVE_INTERVAL = 30
    MAX_BOOKMARKS_PER_BOOK = 50
    MAX_ANNOTATIONS_PER_BOOK = 100
    ALLOW_PUBLIC_READING = False
    REQUIRE_LIBRARY_CARD_FOR_READING = True
    COLLECT_READING_ANALYTICS = True
    RETAIN_READING_SESSIONS_DAYS = 30
    EXTRACT_PDF_TEXT_FOR_SEARCH = False
    PDF_TEXT_EXTRACTION_METHOD = 'pypdf2'
    PDF_TEXT_EXTRACTION_TIMEOUT = 60
    DEFAULT_ZOOM_LEVEL = 100
    ALLOW_ZOOM_CONTROLS = True
    ALLOW_FULLSCREEN = True
    ALLOW_TEXT_SELECTION = True
    ALLOW_PRINTING = False
    ALLOW_DOWNLOAD = False
    MAX_CONCURRENT_READERS_PER_BOOK = 10
    READING_TIMEOUT_MINUTES = 30
    
    # ========== BACKUP SETTINGS ==========
    BACKUP_ENABLED = os.environ.get('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_PATH = os.path.join(BASE_DIR, "backups")
    BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', 30))
    AUTO_BACKUP_SCHEDULE = os.environ.get('AUTO_BACKUP_SCHEDULE', '0 2 * * *')
    
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
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 5


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    
    SESSION_COOKIE_SECURE = False
    EXPLAIN_TEMPLATE_LOADING = False
    DEBUG_TB_ENABLED = True
    PROPAGATE_EXCEPTIONS = True
    
    BASE_DIR = '/home/auwalkz/elibrary1'
    
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    BOOK_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "books")
    COVER_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "covers")
    SAMPLE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "samples")
    BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")
    LOG_FOLDER = os.path.join(BASE_DIR, "logs")
    DATABASE_PATH = os.path.join(BASE_DIR, "library.db")
    
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_ECHO = True
    
    MAX_DOWNLOADS_PER_DAY = 10
    MAX_DOWNLOADS_PER_WEEK = 40
    MAX_DOWNLOADS_PER_MONTH = 100
    
    ADMIN_REGISTRATION_ENABLED = True
    ADMIN_SECRET_KEY = os.environ.get('ADMIN_SECRET_KEY', 'dev-secret-key-123')
    ADMIN_CODE = os.environ.get('ADMIN_CODE', 'dev-admin-code-456')
    
    TWO_FACTOR_ENABLED = False
    TWO_FACTOR_REQUIRED_ROLES = []
    
    SOLR_ENABLED = os.environ.get('SOLR_ENABLED', 'False').lower() == 'true'
    SOLR_URL = os.environ.get('SOLR_URL', 'http://localhost:8983/solr/')
    SOLR_CORE = os.environ.get('SOLR_CORE', 'nigerian_army_library_dev')
    
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_TASK_EAGER_PROPAGATES = True
    
    EXTRACT_PDF_TEXT_FOR_SEARCH = True
    ALLOW_PUBLIC_READING = True
    REQUIRE_LIBRARY_CARD_FOR_READING = False
    ALLOW_DOWNLOAD = True
    ALLOW_PRINTING = True
    COLLECT_READING_ANALYTICS = True
    
    MAX_BOOKMARKS_PER_BOOK = 100
    MAX_ANNOTATIONS_PER_BOOK = 200
    
    BACKUP_ENABLED = False
    AUTO_BACKUP_SCHEDULE = None
    
    API_RATE_LIMIT = "10000/day;1000/hour"
    API_KEY_EXPIRY_DAYS = 3650
    
    WHATSAPP_ENABLED = os.environ.get('WHATSAPP_ENABLED', 'False').lower() == 'true'
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', 'test_account_sid')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', 'test_auth_token')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    @property
    def WHATSAPP_CONFIGURED(self):
        return self.WHATSAPP_ENABLED and bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_ACCOUNT_SID != 'test_account_sid')
    
    NA_OAUTH_CLIENT_ID = os.environ.get('NA_OAUTH_CLIENT_ID')
    NA_OAUTH_CLIENT_SECRET = os.environ.get('NA_OAUTH_CLIENT_SECRET')
    
    @property
    def NA_OAUTH_CONFIGURED(self):
        return bool(self.NA_OAUTH_CLIENT_ID and self.NA_OAUTH_CLIENT_SECRET)


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ECHO = False
    
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    
    UPLOAD_FOLDER = os.path.join(Config.BASE_DIR, "test_uploads")
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024
    
    MAX_DOWNLOADS_PER_DAY = 100
    MAX_DOWNLOADS_PER_WEEK = 500
    MAX_DOWNLOADS_PER_MONTH = 2000
    
    ADMIN_REGISTRATION_ENABLED = True
    ADMIN_SECRET_KEY = 'test-secret-key'
    ADMIN_CODE = 'test-admin-code'
    
    TWO_FACTOR_ENABLED = False
    SOLR_ENABLED = False
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    
    EXTRACT_PDF_TEXT_FOR_SEARCH = False
    ALLOW_PUBLIC_READING = True
    REQUIRE_LIBRARY_CARD_FOR_READING = False
    COLLECT_READING_ANALYTICS = False
    RETAIN_READING_SESSIONS_DAYS = 1
    
    BACKUP_ENABLED = False
    API_ENABLED = True
    API_RATE_LIMIT = "10000/minute"
    
    WHATSAPP_ENABLED = False
    
    NA_OAUTH_CLIENT_ID = 'test_client_id'
    NA_OAUTH_CLIENT_SECRET = 'test_client_secret'
    
    @property
    def NA_OAUTH_CONFIGURED(self):
        return True


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # ========== FIXED: Use writable log path for Render ==========
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'WARNING')
    LOG_FILE = os.environ.get('LOG_FILE', os.path.join(Config.BASE_DIR, 'logs', 'app.log'))
    
    MAX_DOWNLOADS_PER_DAY = 5
    MAX_DOWNLOADS_PER_WEEK = 15
    MAX_DOWNLOADS_PER_MONTH = 40
    
    ADMIN_REGISTRATION_ENABLED = os.environ.get('ADMIN_REGISTRATION_ENABLED', 'False').lower() == 'true'
    
    @property
    def ADMIN_SECRET_KEY(self):
        key = os.environ.get('ADMIN_SECRET_KEY')
        if not key and self.ADMIN_REGISTRATION_ENABLED:
            raise ValueError("ADMIN_SECRET_KEY must be set in production")
        return key or 'change-this-in-production'
    
    @property
    def ADMIN_CODE(self):
        code = os.environ.get('ADMIN_CODE')
        if not code and self.ADMIN_REGISTRATION_ENABLED:
            raise ValueError("ADMIN_CODE must be set in production")
        return code or 'change-this-in-production'
    
    TWO_FACTOR_ENABLED = os.environ.get('TWO_FACTOR_ENABLED', 'True').lower() == 'true'
    TWO_FACTOR_REQUIRED_ROLES = os.environ.get('TWO_FACTOR_REQUIRED_ROLES', 'admin,librarian').split(',')
    
    SOLR_ENABLED = os.environ.get('SOLR_ENABLED', 'True').lower() == 'true'
    SOLR_URL = os.environ.get('SOLR_URL', 'http://solr:8983/solr/')
    SOLR_CORE = os.environ.get('SOLR_CORE', 'nigerian_army_library_prod')
    SOLR_TIMEOUT = int(os.environ.get('SOLR_TIMEOUT', 30))
    
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_WORKER_CONCURRENCY = int(os.environ.get('CELERY_WORKER_CONCURRENCY', 4))
    CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.environ.get('CELERY_WORKER_MAX_TASKS_PER_CHILD', 100))
    
    EXTRACT_PDF_TEXT_FOR_SEARCH = os.environ.get('EXTRACT_PDF_TEXT_FOR_SEARCH', 'True').lower() == 'true'
    PDF_TEXT_EXTRACTION_METHOD = os.environ.get('PDF_TEXT_EXTRACTION_METHOD', 'textract')
    
    ALLOW_PUBLIC_READING = False
    REQUIRE_LIBRARY_CARD_FOR_READING = True
    ALLOW_DOWNLOAD = os.environ.get('ALLOW_DOWNLOAD', 'False').lower() == 'true'
    ALLOW_PRINTING = os.environ.get('ALLOW_PRINTING', 'False').lower() == 'true'
    ALLOW_TEXT_SELECTION = os.environ.get('ALLOW_TEXT_SELECTION', 'True').lower() == 'true'
    MAX_CONCURRENT_READERS_PER_BOOK = int(os.environ.get('MAX_CONCURRENT_READERS_PER_BOOK', 5))
    READING_TIMEOUT_MINUTES = int(os.environ.get('READING_TIMEOUT_MINUTES', 15))
    
    BACKUP_ENABLED = os.environ.get('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_PATH = os.environ.get('BACKUP_PATH', os.path.join(Config.BASE_DIR, 'backups'))
    BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', 30))
    
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_BUCKET_NAME = os.environ.get('AWS_BUCKET_NAME')
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    PROMETHEUS_METRICS = os.environ.get('PROMETHEUS_METRICS', 'True').lower() == 'true'
    
    API_ENABLED = os.environ.get('API_ENABLED', 'True').lower() == 'true'
    API_RATE_LIMIT = os.environ.get('API_RATE_LIMIT', '1000/day;100/hour')
    API_KEY_EXPIRY_DAYS = int(os.environ.get('API_KEY_EXPIRY_DAYS', 365))
    
    @property
    def WHATSAPP_ENABLED(self):
        return os.environ.get('WHATSAPP_ENABLED', 'False').lower() == 'true'
    
    @property
    def TWILIO_ACCOUNT_SID(self):
        sid = os.environ.get('TWILIO_ACCOUNT_SID')
        if self.WHATSAPP_ENABLED and not sid:
            raise ValueError("TWILIO_ACCOUNT_SID must be set in production")
        return sid
    
    @property
    def TWILIO_AUTH_TOKEN(self):
        token = os.environ.get('TWILIO_AUTH_TOKEN')
        if self.WHATSAPP_ENABLED and not token:
            raise ValueError("TWILIO_AUTH_TOKEN must be set in production")
        return token
    
    @property
    def TWILIO_WHATSAPP_NUMBER(self):
        return os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    @property
    def WHATSAPP_CONFIGURED(self):
        if not self.WHATSAPP_ENABLED:
            return False
        return all([
            self.TWILIO_ACCOUNT_SID,
            self.TWILIO_AUTH_TOKEN,
            self.TWILIO_WHATSAPP_NUMBER
        ])
    
    @property
    def NA_OAUTH_CLIENT_ID(self):
        client_id = os.environ.get('NA_OAUTH_CLIENT_ID')
        if not client_id:
            raise ValueError("NA_OAUTH_CLIENT_ID must be set in production")
        return client_id
    
    @property
    def NA_OAUTH_CLIENT_SECRET(self):
        client_secret = os.environ.get('NA_OAUTH_CLIENT_SECRET')
        if not client_secret:
            raise ValueError("NA_OAUTH_CLIENT_SECRET must be set in production")
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
        return all([
            os.environ.get('NA_OAUTH_CLIENT_ID'),
            os.environ.get('NA_OAUTH_CLIENT_SECRET')
        ])
    
    @property
    def SECRET_KEY(self):
        key = os.environ.get('SECRET_KEY')
        if not key:
            raise ValueError("SECRET_KEY must be set in production")
        return key
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        uri = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')
        if not uri:
            return f"sqlite:///{os.path.join(Config.BASE_DIR, 'library.db')}"
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
    
    # Create logs directory
    log_dir = os.path.dirname(config_instance.LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    return config_instance