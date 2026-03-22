from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import random
import string
import hashlib
import base64
import json
import secrets
from io import BytesIO
from sqlalchemy import event, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.ext.hybrid import hybrid_property
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ===================== BASE MIXINS =====================

class TimestampMixin:
    """Add created_at and updated_at timestamps"""
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class SoftDeleteMixin:
    """Add soft delete capability"""
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_reason = db.Column(db.String(255), nullable=True)
    
    def soft_delete(self, user_id=None, reason=None):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.deleted_by_id = user_id
        self.deleted_reason = reason
    
    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by_id = None
        self.deleted_reason = None

class AuditMixin:
    """Add created_by and updated_by audit fields"""
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    def set_created_by(self, user_id):
        self.created_by_id = user_id
    
    def set_updated_by(self, user_id):
        self.updated_by_id = user_id

class BarcodeMixin:
    """Add barcode generation capability"""
    
    def generate_barcode(self, prefix='BC'):
        """Generate a unique barcode"""
        unique_string = f"{prefix}-{datetime.now().timestamp()}-{random.randint(1000, 9999)}"
        hash_obj = hashlib.sha256(unique_string.encode())
        barcode = hash_obj.hexdigest()[:12].upper()
        # Add check digit
        check_digit = sum(ord(c) for c in barcode) % 10
        return f"{prefix}{barcode}{check_digit}"
    
    def generate_barcode_image(self, barcode_text):
        """Generate barcode image as base64"""
        try:
            import barcode
            from barcode.writer import ImageWriter
            
            barcode_class = barcode.get_barcode_class('code128')
            barcode_obj = barcode_class(barcode_text, writer=ImageWriter())
            
            buffer = BytesIO()
            barcode_obj.write(buffer)
            buffer.seek(0)
            
            barcode_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{barcode_base64}"
        except ImportError:
            # Fallback to text barcode
            return f"data:text/plain;base64,{base64.b64encode(barcode_text.encode()).decode()}"

# ===================== CORE MODELS =====================

class User(db.Model, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """Enhanced user model with comprehensive profile and security features"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Authentication
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Personal info
    full_name = db.Column(db.String(200))
    service_number = db.Column(db.String(50), unique=True, index=True)
    rank = db.Column(db.String(50))
    unit = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    
    # ========== NEW REGISTRATION FIELDS ==========
    # Additional contact info
    office_phone = db.Column(db.String(20), nullable=True)  # Office phone number
    address = db.Column(db.Text, nullable=True)  # Residential address
    city = db.Column(db.String(100), nullable=True)  # City of residence
    office_address = db.Column(db.Text, nullable=True)  # Office address
    
    # Demographic info
    gender = db.Column(db.String(10), nullable=True)  # male, female, other
    nationality = db.Column(db.String(50), nullable=True)  # Nigerian, Other
    date_of_birth = db.Column(db.Date, nullable=True)  # Date of birth
    occupation = db.Column(db.String(100), nullable=True)  # Job/Occupation
    # ========== END NEW FIELDS ==========
    
    # Profile
    profile_picture = db.Column(db.String(255))
    bio = db.Column(db.Text)
    preferences = db.Column(db.JSON, default={})
    
    # Role & Permissions
    role = db.Column(db.String(20), default='user', nullable=False, index=True)  # user, librarian, cataloger, admin
    permissions = db.Column(db.JSON, default=[])  # Additional permissions
    
    # Authentication status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verified_at = db.Column(db.DateTime)
    phone_verified = db.Column(db.Boolean, default=False, nullable=False)
    
    # Profile completion tracking
    profile_complete = db.Column(db.Boolean, default=False, nullable=False)
    
    # Login tracking
    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(45))
    login_count = db.Column(db.Integer, default=0)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    
    # Two-factor authentication
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32))
    two_factor_backup_codes = db.Column(db.JSON)
    two_factor_method = db.Column(db.String(20), default='app')  # app, sms, email
    
    # Approval workflow
    approval_status = db.Column(db.String(20), default='pending', index=True)  # pending, approved, rejected
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    
    # Membership
    membership_status = db.Column(db.String(20), default='pending', index=True)  # active, suspended, expired
    membership_type = db.Column(db.String(20), default='regular')  # regular, student, officer, staff
    membership_expiry = db.Column(db.DateTime)
    
    # Security clearance
    security_clearance = db.Column(db.String(20), default='basic', index=True)  # basic, confidential, secret, top_secret
    requires_approval_for_restricted = db.Column(db.Boolean, default=True)
    
    # Statistics
    total_books_borrowed = db.Column(db.Integer, default=0)
    total_books_reserved = db.Column(db.Integer, default=0)
    total_downloads = db.Column(db.Integer, default=0)
    total_fines_paid = db.Column(db.Float, default=0.0)
    total_fines_waived = db.Column(db.Float, default=0.0)
    
    # Notification settings
    notification_settings = db.Column(db.JSON, default={
        'email': True,
        'sms': False,
        'push': True,
        'circulation': True,
        'fines': True,
        'reservations': True,
        'newsletter': False
    })
    
    # API access
    api_key = db.Column(db.String(64), unique=True)
    api_key_created_at = db.Column(db.DateTime)
    api_key_expires_at = db.Column(db.DateTime)
    
    # ==================== RELATIONSHIPS ====================
    
    # Core relationships
    library_card = db.relationship('LibraryCard', backref='user', uselist=False, 
                                   cascade='all, delete-orphan',
                                   foreign_keys='LibraryCard.user_id')
    
    # Reading relationships - ALL with explicit foreign_keys
    reading_history = db.relationship('ReadingHistory', backref='user', lazy='dynamic', 
                                      cascade='all, delete-orphan',
                                      foreign_keys='ReadingHistory.user_id')
    reading_progress = db.relationship('ReadingProgress', backref='user', lazy='dynamic', 
                                       cascade='all, delete-orphan',
                                       foreign_keys='ReadingProgress.user_id')
    reading_sessions = db.relationship('ReadingSession', backref='user', lazy='dynamic', 
                                       cascade='all, delete-orphan',
                                       foreign_keys='ReadingSession.user_id')
    bookmarks = db.relationship('Bookmark', backref='user', lazy='dynamic', 
                                cascade='all, delete-orphan',
                                foreign_keys='Bookmark.user_id')
    annotations = db.relationship('Annotation', backref='user', lazy='dynamic', 
                                  cascade='all, delete-orphan',
                                  foreign_keys='Annotation.user_id')
    reviews = db.relationship('Review', backref='user', lazy='dynamic', 
                              cascade='all, delete-orphan',
                              foreign_keys='Review.user_id')
    wishlist = db.relationship('Wishlist', backref='user', lazy='dynamic', 
                               cascade='all, delete-orphan',
                               foreign_keys='Wishlist.user_id')
    
    # Circulation relationships - UPDATED with back_populates
    borrow_records = db.relationship('BorrowRecord', backref='user', lazy='dynamic', 
                                     cascade='all, delete-orphan',
                                     foreign_keys='BorrowRecord.user_id')
    
    circulations = db.relationship(
        'CirculationRecord', 
        foreign_keys='CirculationRecord.user_id', 
        back_populates='patron',
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    
    reservations = db.relationship('Reservation', backref='user', lazy='dynamic', 
                                   cascade='all, delete-orphan',
                                   foreign_keys='Reservation.user_id')
    
    fines = db.relationship('Fine', 
                           foreign_keys='Fine.user_id', 
                           back_populates='user',
                           lazy='dynamic', 
                           cascade='all, delete-orphan')
    
    # Download tracking
    download_logs = db.relationship('DownloadLog', backref='user', lazy='dynamic', 
                                    cascade='all, delete-orphan',
                                    foreign_keys='DownloadLog.user_id')
    
    # Activity tracking
    activities = db.relationship('RecentActivity', backref='user', lazy='dynamic', 
                                 cascade='all, delete-orphan',
                                 foreign_keys='RecentActivity.user_id')
    sessions = db.relationship('UserSession', backref='user', lazy='dynamic', 
                               cascade='all, delete-orphan',
                               foreign_keys='UserSession.user_id')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', 
                                    cascade='all, delete-orphan',
                                    foreign_keys='Notification.user_id')
    
    # Special requests
    special_requests_submitted = db.relationship('SpecialRequest', 
                                                foreign_keys='SpecialRequest.user_id',
                                                back_populates='requester', 
                                                lazy='dynamic', 
                                                cascade='all, delete-orphan')
    special_requests_reviewed = db.relationship('SpecialRequest', 
                                               foreign_keys='SpecialRequest.reviewed_by',
                                               back_populates='reviewer', 
                                               lazy='dynamic')
    
    # Workflow relationships
    acquisition_requests = db.relationship('AcquisitionRequest', 
                                          foreign_keys='AcquisitionRequest.requested_by',
                                          backref='requester', 
                                          lazy='dynamic', 
                                          cascade='all, delete-orphan')
    reviewed_acquisitions = db.relationship('AcquisitionRequest', 
                                           foreign_keys='AcquisitionRequest.reviewed_by',
                                           backref='reviewer', 
                                           lazy='dynamic')
    created_pos = db.relationship('PurchaseOrder', 
                             foreign_keys='PurchaseOrder.created_by_id',
                             backref='creator', 
                             lazy='dynamic', 
                             cascade='all, delete-orphan')
    cataloging_tasks = db.relationship('CatalogingQueue', 
                                      foreign_keys='CatalogingQueue.assigned_to',
                                      backref='cataloger', 
                                      lazy='dynamic')
    
    # Staff operations - UPDATED with back_populates
    checkout_operations = db.relationship(
        'CirculationRecord', 
        foreign_keys='CirculationRecord.checkout_staff',
        back_populates='checkout_operator',
        lazy='dynamic'
    )
    
    return_operations = db.relationship(
        'CirculationRecord', 
        foreign_keys='CirculationRecord.return_staff',
        back_populates='return_operator',
        lazy='dynamic'
    )
    
    waived_fines = db.relationship('Fine', 
                              foreign_keys='Fine.waived_by', 
                              back_populates='waiving_officer',
                              lazy='dynamic')
    
    # Audit relationships
    approved_by = db.relationship('User', remote_side=[id], foreign_keys='User.approved_by_id')
    created_by = db.relationship('User', remote_side=[id], foreign_keys='User.created_by_id')
    updated_by = db.relationship('User', remote_side=[id], foreign_keys='User.updated_by_id')
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_users_username_lookup', 'username'),
        Index('idx_users_email_lookup', 'email'),
        Index('idx_users_service_number', 'service_number'),
        Index('idx_users_role_status', 'role', 'membership_status'),
        Index('idx_users_approval_clearance', 'approval_status', 'security_clearance'),
        Index('idx_users_created', 'created_at'),
        Index('idx_users_gender', 'gender'),
        Index('idx_users_nationality', 'nationality'),
        Index('idx_users_occupation', 'occupation'),
        Index('idx_users_city', 'city'),
        CheckConstraint('role IN ("user", "librarian", "cataloger", "admin")', name='check_valid_role'),
        CheckConstraint('approval_status IN ("pending", "approved", "rejected")', name='check_valid_approval'),
        CheckConstraint('membership_status IN ("active", "suspended", "expired", "pending")', name='check_valid_membership'),
        CheckConstraint('security_clearance IN ("basic", "confidential", "secret", "top_secret")', name='check_valid_clearance'),
        CheckConstraint('gender IN ("male", "female", "other")', name='check_valid_gender'),
    )
    
    # ==================== METHODS ====================
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def generate_api_key(self):
        """Generate new API key"""
        self.api_key = secrets.token_urlsafe(32)
        self.api_key_created_at = datetime.utcnow()
        self.api_key_expires_at = datetime.utcnow() + timedelta(days=365)
        return self.api_key
    
    def enable_two_factor(self):
        """Enable 2FA and generate secret"""
        try:
            import pyotp
            self.two_factor_secret = pyotp.random_base32()
            self.two_factor_enabled = True
            self.two_factor_backup_codes = self._generate_backup_codes()
            return self.two_factor_secret
        except ImportError:
            return None
    
    def _generate_backup_codes(self):
        """Generate backup codes for 2FA"""
        codes = []
        for _ in range(10):
            codes.append(''.join(random.choices(string.ascii_uppercase + string.digits, k=8)))
        return codes
    
    def verify_two_factor(self, token):
        """Verify 2FA token"""
        if not self.two_factor_enabled:
            return True
        try:
            import pyotp
            totp = pyotp.TOTP(self.two_factor_secret)
            return totp.verify(token)
        except ImportError:
            return False
    
    def get_two_factor_qr(self):
        """Get QR code for 2FA setup"""
        if not self.two_factor_secret:
            return None
        try:
            import pyotp
            import qrcode
            totp = pyotp.TOTP(self.two_factor_secret)
            uri = totp.provisioning_uri(self.email, issuer_name="Nigerian Army E-Library")
            img = qrcode.make(uri)
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            return base64.b64encode(buffer.getvalue()).decode()
        except ImportError:
            return None
    
    def is_locked(self):
        """Check if account is locked"""
        return self.locked_until and self.locked_until > datetime.utcnow()
    
    def increment_failed_login(self):
        """Increment failed login count and lock if needed"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)
    
    def reset_failed_login(self):
        """Reset failed login counter"""
        self.failed_login_attempts = 0
        self.locked_until = None
    
    def has_permission(self, permission):
        """Check if user has specific permission"""
        # Admin has all permissions
        if self.role == 'admin':
            return True
        
        # Check role-based permissions
        role_permissions = {
            'librarian': ['view_users', 'manage_books', 'manage_circulation', 'manage_fines'],
            'cataloger': ['manage_books', 'view_cataloging', 'edit_metadata'],
            'user': ['view_books', 'borrow_books', 'download_books', 'write_reviews']
        }
        
        if permission in role_permissions.get(self.role, []):
            return True
        
        # Check custom permissions
        return permission in (self.permissions or [])
    
    def has_clearance(self, required_level):
        """Check if user has required security clearance"""
        levels = {'basic': 1, 'confidential': 2, 'secret': 3, 'top_secret': 4}
        user_level = levels.get(self.security_clearance, 1)
        required_level = levels.get(required_level, 1)
        return user_level >= required_level
    
    def calculate_age(self):
        """Calculate user's age from date of birth"""
        if not self.date_of_birth:
            return None
        today = datetime.now().date()
        age = today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return age
    
    def is_adult(self):
        """Check if user is 18 or older"""
        age = self.calculate_age()
        return age is not None and age >= 18
    
    @hybrid_property
    def is_admin(self):
        return self.role == 'admin'
    
    @hybrid_property
    def is_librarian(self):
        return self.role in ['admin', 'librarian']
    
    @hybrid_property
    def is_approved(self):
        return self.approval_status == 'approved'
    
    @hybrid_property
    def is_pending(self):
        return self.approval_status == 'pending'
    
    @hybrid_property
    def is_rejected(self):
        return self.approval_status == 'rejected'
    
    @hybrid_property
    def has_library_card(self):
        return self.library_card is not None and self.library_card.is_active
    
    def get_card_status(self):
        """Get detailed card status"""
        if not self.library_card:
            return None
        return self.library_card.to_dict()
    
    def get_approval_info(self):
        """Get approval workflow info"""
        if self.approval_status == 'approved' and self.approved_by:
            return {
                'status': 'approved',
                'by': self.approved_by.username,
                'by_id': self.approved_by.id,
                'at': self.approved_at.isoformat() if self.approved_at else None
            }
        elif self.approval_status == 'rejected':
            return {
                'status': 'rejected',
                'reason': self.rejection_reason,
                'by': self.approved_by.username if self.approved_by else None,
                'by_id': self.approved_by.id if self.approved_by else None,
                'at': self.approved_at.isoformat() if self.approved_at else None
            }
        return {'status': 'pending'}
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'service_number': self.service_number,
            'rank': self.rank,
            'unit': self.unit,
            'gender': self.gender,
            'nationality': self.nationality,
            'date_of_birth': self.date_of_birth.isoformat() if self.date_of_birth else None,
            'age': self.calculate_age(),
            'occupation': self.occupation,
            'address': self.address,
            'city': self.city,
            'phone': self.phone,
            'office_phone': self.office_phone,
            'office_address': self.office_address,
            'membership_status': self.membership_status,
            'approval_status': self.approval_status,
            'security_clearance': self.security_clearance,
            'total_books_borrowed': self.total_books_borrowed,
            'total_downloads': self.total_downloads,
            'last_login': self.last_login_at.isoformat() if self.last_login_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<User {self.username}>'


class LibraryCard(db.Model, TimestampMixin, AuditMixin, BarcodeMixin):
    """Enhanced library card with barcode and RFID support"""
    __tablename__ = 'library_cards'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    
    # Identification
    card_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False, index=True)
    barcode_image = db.Column(db.Text, nullable=True)
    rfid_tag = db.Column(db.String(100), unique=True, nullable=True)
    
    # Card details
    card_type = db.Column(db.String(20), default='standard', nullable=False)  # standard, premium, student, officer
    card_holder_name = db.Column(db.String(200), nullable=False)
    
    # Dates
    issued_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)
    last_renewed = db.Column(db.DateTime)
    renewal_count = db.Column(db.Integer, default=0)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(20), default='active', nullable=False)  # active, expired, suspended, lost, damaged, replaced
    status_reason = db.Column(db.String(255))
    
    # Security
    pin = db.Column(db.String(128), nullable=True)  # For card PIN verification
    has_chip = db.Column(db.Boolean, default=False)
    
    # Replacement tracking
    replaced_by_id = db.Column(db.Integer, db.ForeignKey('library_cards.id'), nullable=True)
    original_card_id = db.Column(db.Integer, db.ForeignKey('library_cards.id'), nullable=True)
    replacement_reason = db.Column(db.String(50))  # lost, damaged, stolen
    
    # ==================== RELATIONSHIPS ====================
    replaced_by = db.relationship('LibraryCard', remote_side=[id], foreign_keys='LibraryCard.replaced_by_id')
    original_card = db.relationship('LibraryCard', remote_side=[id], foreign_keys='LibraryCard.original_card_id')    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_cards_number', 'card_number'),
        Index('idx_cards_barcode', 'barcode'),
        Index('idx_cards_rfid', 'rfid_tag'),
        Index('idx_cards_expiry', 'expiry_date'),
        Index('idx_cards_status', 'status'),
        CheckConstraint('status IN ("active", "expired", "suspended", "lost", "damaged", "replaced")', 
                       name='check_valid_card_status'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.card_number:
            self.card_number = self.generate_card_number()
        if not self.barcode:
            self.barcode = self.generate_barcode('LC')
        if not self.barcode_image:
            self.barcode_image = self.generate_barcode_image(self.barcode)
        if not self.expiry_date:
            self.expiry_date = datetime.now() + timedelta(days=365)
        if not self.card_holder_name and hasattr(self, 'user') and self.user:
            self.card_holder_name = self.user.full_name or self.user.username
    
    def generate_card_number(self):
        """Generate unique card number"""
        year = datetime.now().strftime('%Y')
        random_part = ''.join(random.choices(string.digits, k=8))
        return f"NAEL-{year}-{random_part}"
    
    def set_pin(self, pin):
        """Set card PIN"""
        self.pin = generate_password_hash(pin)
    
    def verify_pin(self, pin):
        """Verify card PIN"""
        if not self.pin:
            return True
        return check_password_hash(self.pin, pin)
    
    def is_expired(self):
        """Check if card is expired"""
        return datetime.now() > self.expiry_date
    
    def days_until_expiry(self):
        """Get days until expiry"""
        if self.is_expired():
            return 0
        delta = self.expiry_date - datetime.now()
        return delta.days
    
    def renew(self, days=365):
        """Renew library card"""
        self.last_renewed = datetime.utcnow()
        self.expiry_date = datetime.now() + timedelta(days=days)
        self.renewal_count += 1
        self.is_active = True
        self.status = 'active'
        return True
    
    def suspend(self, reason=None):
        """Suspend card"""
        self.is_active = False
        self.status = 'suspended'
        self.status_reason = reason
    
    def activate(self):
        """Activate card"""
        self.is_active = True
        self.status = 'active'
        self.status_reason = None
    
    def report_lost(self):
        """Report card as lost"""
        self.is_active = False
        self.status = 'lost'
    
    def report_damaged(self):
        """Report card as damaged"""
        self.is_active = False
        self.status = 'damaged'
    
    def replace(self, reason='lost', new_card=None):
        """Replace this card"""
        self.is_active = False
        self.status = 'replaced'
        self.replacement_reason = reason
        if new_card:
            self.replaced_by_id = new_card.id
            new_card.original_card_id = self.id
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'card_number': self.card_number,
            'barcode': self.barcode,
            'barcode_image': self.barcode_image,
            'rfid_tag': self.rfid_tag,
            'card_type': self.card_type,
            'card_holder_name': self.card_holder_name,
            'issued_date': self.issued_date.isoformat() if self.issued_date else None,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'days_until_expiry': self.days_until_expiry(),
            'is_expired': self.is_expired(),
            'is_active': self.is_active,
            'status': self.status,
            'renewal_count': self.renewal_count,
            'last_renewed': self.last_renewed.isoformat() if self.last_renewed else None
        }
    
    def __repr__(self):
        return f'<LibraryCard {self.card_number}>'


class Book(db.Model, TimestampMixin, SoftDeleteMixin, AuditMixin, BarcodeMixin):
    """Comprehensive book model with digital and physical formats"""
    __tablename__ = 'books'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # ==================== BASIC METADATA ====================
    title = db.Column(db.String(500), nullable=False, index=True)
    subtitle = db.Column(db.String(500))
    author = db.Column(db.String(500), nullable=False, index=True)
    category = db.Column(db.String(100), index=True)  # Legacy field - kept for backward compatibility
    subcategory = db.Column(db.String(100))  # Legacy field
    
    description = db.Column(db.Text)
    
    # ==================== IDENTIFIERS ====================
    isbn = db.Column(db.String(20), unique=True, index=True)
    issn = db.Column(db.String(20))
    doi = db.Column(db.String(100))
    oclc_number = db.Column(db.String(50))
    lccn = db.Column(db.String(50))  # Library of Congress Control Number
    
    # ==================== PUBLICATION DETAILS ====================
    publisher = db.Column(db.String(255))
    published_date = db.Column(db.Date)
    published_year = db.Column(db.Integer)
    edition = db.Column(db.String(50))
    volume = db.Column(db.String(50))
    series = db.Column(db.String(255))
    language = db.Column(db.String(50), default='English', nullable=False)
    original_language = db.Column(db.String(50))
    translator = db.Column(db.String(255))
    
    # ==================== PHYSICAL DESCRIPTION ====================
    pages = db.Column(db.Integer)
    dimensions = db.Column(db.String(50))
    weight = db.Column(db.Float)  # in grams
    binding = db.Column(db.String(50))  # hardcover, paperback, etc.
    
    # ==================== CLASSIFICATION ====================
    dewey_decimal = db.Column(db.String(20))
    library_of_congress = db.Column(db.String(50))
    subjects = db.Column(db.JSON)  # Array of subjects
    keywords = db.Column(db.JSON)  # Array of keywords
    audience = db.Column(db.String(50))  # children, young adult, adult, academic
    
    # ==================== DIGITAL CONTENT ====================
    has_digital = db.Column(db.Boolean, default=False, nullable=False)
    filename = db.Column(db.String(255))
    file_size = db.Column(db.Integer)  # in bytes
    mime_type = db.Column(db.String(100))
    file_hash = db.Column(db.String(64))  # SHA-256 for integrity
    file_format = db.Column(db.String(20))  # pdf, epub, mobi
    
    # Digital rights management
    drm_enabled = db.Column(db.Boolean, default=False)
    drm_type = db.Column(db.String(50))
    concurrent_users = db.Column(db.Integer, default=1)
    loan_period_days = db.Column(db.Integer, default=14)
    allow_download = db.Column(db.Boolean, default=True)
    allow_print = db.Column(db.Boolean, default=True)
    allow_copy = db.Column(db.Boolean, default=False)
    watermark_enabled = db.Column(db.Boolean, default=False)
    
    # ==================== PHYSICAL COPIES ====================
    has_physical = db.Column(db.Boolean, default=False, nullable=False)
    total_copies = db.Column(db.Integer, default=0)
    available_copies = db.Column(db.Integer, default=0)
    reserved_copies = db.Column(db.Integer, default=0)
    damaged_copies = db.Column(db.Integer, default=0)
    lost_copies = db.Column(db.Integer, default=0)
    reference_copies = db.Column(db.Integer, default=0)  # Non-circulating copies
    
    # Physical location (default location)
    shelf_location = db.Column(db.String(100))
    floor = db.Column(db.String(10))
    section = db.Column(db.String(50))
    
    # ==================== IDENTIFICATION ====================
    accession_number = db.Column(db.String(50), unique=True)
    barcode = db.Column(db.String(50), unique=True)
    barcode_image = db.Column(db.Text)
    
    # ==================== MEDIA ====================
    cover_image = db.Column(db.String(255))
    cover_image_url = db.Column(db.String(500))
    thumbnail_url = db.Column(db.String(500))
    sample_url = db.Column(db.String(500))
    preview_url = db.Column(db.String(500))
    
    # ==================== EXTERNAL LINKS ====================
    google_books_id = db.Column(db.String(50))
    open_library_id = db.Column(db.String(50))
    worldcat_id = db.Column(db.String(50))
    amazon_url = db.Column(db.String(500))
    goodreads_url = db.Column(db.String(500))
    
    # ==================== STATISTICS ====================
    view_count = db.Column(db.Integer, default=0)
    download_count = db.Column(db.Integer, default=0)
    borrow_count = db.Column(db.Integer, default=0)
    reserve_count = db.Column(db.Integer, default=0)
    average_rating = db.Column(db.Float, default=0.0)
    review_count = db.Column(db.Integer, default=0)
    wishlist_count = db.Column(db.Integer, default=0)
    
    # ==================== STATUS FLAGS ====================
    is_featured = db.Column(db.Boolean, default=False)
    is_new_arrival = db.Column(db.Boolean, default=False)
    is_bestseller = db.Column(db.Boolean, default=False)
    is_recommended = db.Column(db.Boolean, default=False)
    is_restricted = db.Column(db.Boolean, default=False)
    is_reference = db.Column(db.Boolean, default=False)  # Reference only, cannot be borrowed
    is_serial = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    
    # ==================== ACCESS CONTROL ====================
    is_public = db.Column(db.Boolean, default=True)
    requires_library_card = db.Column(db.Boolean, default=True)
    requires_special_request = db.Column(db.Boolean, default=False)
    special_request_notes = db.Column(db.Text)
    security_classification = db.Column(db.String(50))  # unclassified, confidential, secret, top_secret
    approved_roles = db.Column(db.JSON)  # Array of roles that can access
    minimum_clearance = db.Column(db.String(20), default='basic')
    
    # ==================== CATALOGING ====================
    cataloging_status = db.Column(db.String(20), default='pending', index=True)  # pending, in_progress, completed
    cataloged_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    cataloged_at = db.Column(db.DateTime)
    cataloging_notes = db.Column(db.Text)
    
    # MARC record
    marc_record = db.Column(db.Text)  # MARC21 XML
    marc_modified = db.Column(db.DateTime)
    
    # ==================== RELATIONSHIPS ====================
    
    # Core relationships
    copies = db.relationship('ItemCopy', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    cataloging_record = db.relationship('CatalogingQueue', backref='book', uselist=False, cascade='all, delete-orphan')
    
    # Reading relationships
    reading_history = db.relationship('ReadingHistory', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    reading_progress = db.relationship('ReadingProgress', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    reading_sessions = db.relationship('ReadingSession', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    bookmarks = db.relationship('Bookmark', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    annotations = db.relationship('Annotation', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    wishlist = db.relationship('Wishlist', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    
    # Circulation relationships
    borrow_records = db.relationship('BorrowRecord', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    reservations = db.relationship('BookReservation', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    download_logs = db.relationship('DownloadLog', backref='book', lazy='dynamic', cascade='all, delete-orphan')
    
    # Special requests
    special_requests = db.relationship('SpecialRequest', back_populates='book', lazy='dynamic', cascade='all, delete-orphan')
    
    # Cataloging
    cataloged_by = db.relationship('User', foreign_keys=[cataloged_by_id])
    
    # ==================== NEW RELATIONSHIPS FOR DYNAMIC CATEGORIES/TAGS ====================
    
    # Many-to-many with categories
    categories_assoc = db.relationship('BookCategory', back_populates='book', 
                                       lazy='dynamic', cascade='all, delete-orphan')
    
    # Many-to-many with tags
    tags_assoc = db.relationship('BookTag', back_populates='book', 
                                 lazy='dynamic', cascade='all, delete-orphan')
    
    # ==================== HELPER METHODS FOR CATEGORIES/TAGS ====================
    
    @property
    def categories(self):
        """Get all categories for this book"""
        return [assoc.category for assoc in self.categories_assoc]
    
    @property
    def primary_category(self):
        """Get primary category"""
        primary = self.categories_assoc.filter_by(is_primary=True).first()
        return primary.category if primary else None
    
    @property
    def tags(self):
        """Get all tags for this book"""
        return [assoc.tag for assoc in self.tags_assoc]
    
    def add_category(self, category, is_primary=False, weight=1.0):
        """Add a category to the book"""
        existing = BookCategory.query.filter_by(
            book_id=self.id, 
            category_id=category.id
        ).first()
        
        if not existing:
            assoc = BookCategory(
                book_id=self.id,
                category_id=category.id,
                is_primary=is_primary,
                weight=weight
            )
            db.session.add(assoc)
            
            # If this is primary, unset other primary categories
            if is_primary:
                BookCategory.query.filter(
                    BookCategory.book_id == self.id,
                    BookCategory.id != assoc.id
                ).update({'is_primary': False})
            
            # Update category book count
            category.book_count = BookCategory.query.filter_by(category_id=category.id).count()
            return assoc
        return existing
    
    def remove_category(self, category):
        """Remove a category from the book"""
        assoc = BookCategory.query.filter_by(
            book_id=self.id,
            category_id=category.id
        ).first()
        
        if assoc:
            was_primary = assoc.is_primary
            db.session.delete(assoc)
            
            # Update category book count
            category.book_count = BookCategory.query.filter_by(category_id=category.id).count()
            
            # If this was primary, set another as primary if exists
            if was_primary:
                new_primary = self.categories_assoc.first()
                if new_primary:
                    new_primary.is_primary = True
            return True
        return False
    
    def add_tag(self, tag, confidence=1.0, auto_generated=False):
        """Add a tag to the book"""
        existing = BookTag.query.filter_by(
            book_id=self.id,
            tag_id=tag.id
        ).first()
        
        if not existing:
            assoc = BookTag(
                book_id=self.id,
                tag_id=tag.id,
                confidence=confidence,
                is_auto_generated=auto_generated
            )
            db.session.add(assoc)
            
            # Update tag usage count and trending score
            tag.update_usage_count()
            tag.update_trending_score()
            return assoc
        return existing
    
    def remove_tag(self, tag):
        """Remove a tag from the book"""
        assoc = BookTag.query.filter_by(
            book_id=self.id,
            tag_id=tag.id
        ).first()
        
        if assoc:
            db.session.delete(assoc)
            
            # Update tag usage count and trending score
            tag.update_usage_count()
            tag.update_trending_score()
            return True
        return False
    
    def set_categories(self, category_ids, primary_id=None):
        """Set all categories for the book"""
        # Clear existing
        BookCategory.query.filter_by(book_id=self.id).delete()
        
        # Add new
        for i, cat_id in enumerate(category_ids):
            category = Category.query.get(cat_id)
            if category:
                is_primary = (cat_id == primary_id) or (primary_id is None and i == 0)
                self.add_category(category, is_primary=is_primary)
    
    def set_tags(self, tag_ids, auto_generated=False):
        """Set all tags for the book"""
        # Clear existing
        BookTag.query.filter_by(book_id=self.id).delete()
        
        # Add new
        for tag_id in tag_ids:
            tag = Tag.query.get(tag_id)
            if tag:
                self.add_tag(tag, auto_generated=auto_generated)
    
    def get_category_names(self):
        """Get comma-separated list of category names"""
        return ', '.join([c.name for c in self.categories])
    
    def get_tag_names(self):
        """Get comma-separated list of tag names"""
        return ', '.join([t.name for t in self.tags])
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_books_title_author', 'title', 'author'),
        Index('idx_books_category', 'category'),
        Index('idx_books_isbn', 'isbn'),
        Index('idx_books_barcode', 'barcode'),
        Index('idx_books_publication', 'published_year'),
        Index('idx_books_rating', 'average_rating'),
        Index('idx_books_downloads', 'download_count'),
        Index('idx_books_views', 'view_count'),
        Index('idx_books_created', 'created_at'),
        Index('idx_books_restricted', 'requires_special_request', 'security_classification'),
        Index('idx_books_cataloging', 'cataloging_status'),
        CheckConstraint('average_rating BETWEEN 0 AND 5', name='check_valid_rating'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.barcode and self.has_physical:
            self.barcode = self.generate_barcode('BK')
        if not self.barcode_image and self.barcode:
            self.barcode_image = self.generate_barcode_image(self.barcode)
    
    def update_rating(self):
        """Update average rating from reviews"""
        from sqlalchemy import func
        result = db.session.query(
            func.avg(Review.rating).label('avg'),
            func.count(Review.id).label('count')
        ).filter(Review.book_id == self.id).first()
        
        if result and result.count > 0:
            self.average_rating = round(result.avg, 2)
            self.review_count = result.count
        else:
            self.average_rating = 0.0
            self.review_count = 0
    
    def increment_view(self):
        """Increment view count"""
        self.view_count += 1
    
    def increment_download(self):
        """Increment download count"""
        self.download_count += 1
    
    def increment_borrow(self):
        """Increment borrow count"""
        self.borrow_count += 1
    
    def is_available(self):
        """Check if any copy is available"""
        if self.has_physical:
            return self.available_copies > 0
        return self.has_digital
    
    def has_digital_copy(self):
        """Check if digital copy exists"""
        return self.has_digital and self.filename is not None
    
    def has_physical_copy(self):
        """Check if physical copies exist"""
        return self.has_physical and self.total_copies > 0
    
    def get_available_formats(self):
        """Get list of available formats"""
        formats = []
        if self.has_digital_copy():
            formats.append('digital')
        if self.has_physical_copy():
            formats.append('physical')
        return formats
    
    def requires_approval(self):
        """Check if book requires approval"""
        return self.requires_special_request
    
    def get_required_clearance(self):
        """Get required security clearance"""
        return self.minimum_clearance or 'basic'
    
    def can_access(self, user):
        """Check if user can access this book"""
        if self.is_public:
            return True
        if not user:
            return False
        if user.role == 'admin':
            return True
        if self.requires_special_request:
            # Check if user has approved special request
            request = SpecialRequest.query.filter_by(
                user_id=user.id,
                book_id=self.id,
                status='approved'
            ).first()
            return request is not None
        if self.security_classification:
            return user.has_clearance(self.get_required_clearance())
        return True
    
    def can_borrow(self, user):
        """Check if user can borrow physical copy"""
        if not self.has_physical_copy():
            return False
        if self.available_copies <= 0:
            return False
        if not user.has_library_card:
            return False
        if user.membership_status != 'active':
            return False
        if not self.can_access(user):
            return False
        return True
    
    def can_read_online(self, user):
        """Check if user can read online"""
        if not self.has_digital_copy():
            return False
        return self.can_access(user)
    
    def can_download(self, user):
        """Check if user can download"""
        if not self.allow_download:
            return False
        return self.can_read_online(user)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'subtitle': self.subtitle,
            'author': self.author,
            'category': self.category,
            'description': self.description,
            'isbn': self.isbn,
            'publisher': self.publisher,
            'published_year': self.published_year,
            'language': self.language,
            'pages': self.pages,
            'cover_image': self.cover_image,
            'barcode': self.barcode,
            'has_digital': self.has_digital,
            'has_physical': self.has_physical,
            'available_copies': self.available_copies,
            'total_copies': self.total_copies,
            'average_rating': self.average_rating,
            'review_count': self.review_count,
            'download_count': self.download_count,
            'view_count': self.view_count,
            'requires_special_request': self.requires_special_request,
            'security_classification': self.security_classification,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'categories': self.get_category_names(),
            'tags': self.get_tag_names()
        }
    
    def __repr__(self):
        categories_preview = ', '.join([c.name for c in self.categories[:3]])
        tags_preview = ', '.join([t.name for t in self.tags[:3]])
        return f'<Book {self.title} by {self.author} | Cats: {categories_preview} | Tags: {tags_preview}>'


# ===================== READING MODELS =====================

class ReadingHistory(db.Model, TimestampMixin):
    """Track user reading history"""
    __tablename__ = 'reading_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Reading progress
    last_read = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    progress = db.Column(db.Integer, default=0)  # Percentage
    last_page = db.Column(db.Integer, default=0)
    total_pages = db.Column(db.Integer)
    
    # Statistics
    read_count = db.Column(db.Integer, default=1)
    total_time_seconds = db.Column(db.Integer, default=0)
    
    # Completion
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'book_id', name='unique_user_book_history'),
        Index('idx_history_user', 'user_id'),
        Index('idx_history_book', 'book_id'),
        Index('idx_history_last_read', 'last_read'),
    )
    
    def update_progress(self, page=None, seconds=0):
        """Update reading progress"""
        self.last_read = datetime.utcnow()
        if page is not None:
            self.last_page = page
            if self.total_pages:
                self.progress = int((page / self.total_pages) * 100)
        if seconds:
            self.total_time_seconds += seconds
        if self.progress >= 100:
            self.completed = True
            self.completed_at = datetime.utcnow()
    
    def __repr__(self):
        return f'<ReadingHistory user={self.user_id} book={self.book_id}>'


class ReadingProgress(db.Model, TimestampMixin):
    """Real-time reading progress for e-books"""
    __tablename__ = 'reading_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Progress tracking
    current_page = db.Column(db.Integer, default=0)
    progress_percentage = db.Column(db.Float, default=0.0)
    
    # Reading position
    last_location = db.Column(db.String(255))  # Chapter or section
    last_position = db.Column(db.Float)  # Percentage or position in e-reader
    
    # Time tracking
    reading_time_seconds = db.Column(db.Integer, default=0)
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Device info
    device_type = db.Column(db.String(50))
    device_id = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    # Book metadata cache
    total_pages = db.Column(db.Integer)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'book_id', name='unique_user_book_progress'),
        Index('idx_progress_user', 'user_id'),
        Index('idx_progress_book', 'book_id'),
        Index('idx_progress_last', 'last_accessed'),
    )
    
    def update_progress(self, page=None, position=None, location=None, seconds=0):
        """Update reading progress"""
        if page is not None:
            self.current_page = page
            if self.total_pages:
                self.progress_percentage = (page / self.total_pages) * 100
        
        if position is not None:
            self.last_position = position
        
        if location is not None:
            self.last_location = location
        
        if seconds:
            self.reading_time_seconds += seconds
        
        self.last_accessed = datetime.utcnow()
        
        if self.progress_percentage >= 99.9:
            # Mark as completed in history
            history = ReadingHistory.query.filter_by(
                user_id=self.user_id,
                book_id=self.book_id
            ).first()
            if history:
                history.completed = True
                history.completed_at = datetime.utcnow()
    
    def get_reading_time_formatted(self):
        """Format reading time"""
        hours = self.reading_time_seconds // 3600
        minutes = (self.reading_time_seconds % 3600) // 60
        seconds = self.reading_time_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def __repr__(self):
        return f'<ReadingProgress user={self.user_id} book={self.book_id} {self.progress_percentage:.1f}%>'


class ReadingSession(db.Model, TimestampMixin):
    """Individual reading sessions"""
    __tablename__ = 'reading_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Session timing
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_time = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)
    
    # Pages read
    start_page = db.Column(db.Integer, default=0)
    end_page = db.Column(db.Integer)
    pages_read = db.Column(db.Integer)
    
    # Location
    ip_address = db.Column(db.String(45))
    device_type = db.Column(db.String(50))
    
    __table_args__ = (
        Index('idx_sessions_user', 'user_id'),
        Index('idx_sessions_book', 'book_id'),
        Index('idx_sessions_start', 'start_time'),
    )
    
    def end_session(self, end_page):
        """End reading session"""
        self.end_time = datetime.utcnow()
        self.end_page = end_page
        self.pages_read = end_page - self.start_page
        self.duration_seconds = int((self.end_time - self.start_time).total_seconds())
        
        # Update reading progress
        progress = ReadingProgress.query.filter_by(
            user_id=self.user_id,
            book_id=self.book_id
        ).first()
        if progress:
            progress.update_progress(
                page=end_page,
                seconds=self.duration_seconds
            )
    
    def __repr__(self):
        return f'<ReadingSession {self.id} user={self.user_id}>'


class Bookmark(db.Model, TimestampMixin):
    """User bookmarks/highlights"""
    __tablename__ = 'bookmarks'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Location
    page_number = db.Column(db.Integer, nullable=False)
    chapter = db.Column(db.String(255))
    position = db.Column(db.Float)  # For e-books
    
    # Content
    title = db.Column(db.String(255))
    note = db.Column(db.Text)
    color = db.Column(db.String(20), default='yellow')
    
    # Type
    bookmark_type = db.Column(db.String(20), default='bookmark')  # bookmark, highlight, note
    
    # Highlight (if type is highlight)
    highlight_text = db.Column(db.Text)
    highlight_color = db.Column(db.String(20))
    
    __table_args__ = (
        UniqueConstraint('user_id', 'book_id', 'page_number', name='unique_bookmark'),
        Index('idx_bookmarks_user', 'user_id'),
        Index('idx_bookmarks_book', 'book_id'),
        Index('idx_bookmarks_type', 'bookmark_type'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'page': self.page_number,
            'chapter': self.chapter,
            'title': self.title,
            'note': self.note,
            'type': self.bookmark_type,
            'color': self.color,
            'highlight_text': self.highlight_text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Bookmark {self.id} page={self.page_number}>'


class Annotation(db.Model, TimestampMixin):
    """User annotations/highlights"""
    __tablename__ = 'annotations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Location
    page_number = db.Column(db.Integer, nullable=False)
    chapter = db.Column(db.String(255))
    position = db.Column(db.Float)
    
    # Content
    text = db.Column(db.Text, nullable=False)
    note = db.Column(db.Text)
    color = db.Column(db.String(20), default='yellow')
    
    # Annotation type
    annotation_type = db.Column(db.String(20), default='note')  # note, highlight, underline, comment
    
    # For highlights
    highlight_text = db.Column(db.Text)
    highlight_start = db.Column(db.Integer)  # Character position
    highlight_end = db.Column(db.Integer)
    
    # For selections
    selected_text = db.Column(db.Text)
    
    # Privacy
    is_private = db.Column(db.Boolean, default=True)
    
    __table_args__ = (
        Index('idx_annotations_user', 'user_id'),
        Index('idx_annotations_book', 'book_id'),
        Index('idx_annotations_page', 'page_number'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'page': self.page_number,
            'chapter': self.chapter,
            'text': self.text,
            'note': self.note,
            'type': self.annotation_type,
            'color': self.color,
            'highlight_text': self.highlight_text,
            'selected_text': self.selected_text,
            'is_private': self.is_private,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Annotation {self.id} type={self.annotation_type}>'


class Review(db.Model, TimestampMixin):
    """Book reviews and ratings"""
    __tablename__ = 'reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Rating
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    
    # Content
    title = db.Column(db.String(255))
    content = db.Column(db.Text)
    pros = db.Column(db.JSON)  # Array of pros
    cons = db.Column(db.JSON)  # Array of cons
    
    # Status
    status = db.Column(db.String(20), default='published', index=True)  # published, pending, hidden
    
    # Engagement
    helpful_count = db.Column(db.Integer, default=0)
    not_helpful_count = db.Column(db.Integer, default=0)
    report_count = db.Column(db.Integer, default=0)
    
    # Moderation
    moderated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    moderated_at = db.Column(db.DateTime)
    moderation_reason = db.Column(db.String(255))
    
    __table_args__ = (
        UniqueConstraint('user_id', 'book_id', name='unique_user_book_review'),
        Index('idx_reviews_book', 'book_id'),
        Index('idx_reviews_rating', 'rating'),
        CheckConstraint('rating BETWEEN 1 AND 5', name='check_valid_rating'),
    )
    
    def mark_helpful(self):
        """Mark review as helpful"""
        self.helpful_count += 1
    
    def mark_not_helpful(self):
        """Mark review as not helpful"""
        self.not_helpful_count += 1
    
    def report(self):
        """Report review"""
        self.report_count += 1
        if self.report_count >= 5:
            self.status = 'pending'
    
    def moderate(self, user_id, action, reason=None):
        """Moderate review"""
        self.moderated_by = user_id
        self.moderated_at = datetime.utcnow()
        self.moderation_reason = reason
        self.status = action  # 'published' or 'hidden'
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'book_id': self.book_id,
            'rating': self.rating,
            'title': self.title,
            'content': self.content,
            'helpful_count': self.helpful_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Review {self.id} rating={self.rating}>'


class Wishlist(db.Model, TimestampMixin):
    """User wishlist"""
    __tablename__ = 'wishlist'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Wishlist details
    notes = db.Column(db.Text)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    reason = db.Column(db.String(255))
    
    # Notification
    notify_when_available = db.Column(db.Boolean, default=True)
    notification_sent = db.Column(db.Boolean, default=False)
    notification_sent_at = db.Column(db.DateTime)
    
    # Added via
    added_from = db.Column(db.String(50))  # search, recommendation, etc.
    
    __table_args__ = (
        UniqueConstraint('user_id', 'book_id', name='unique_user_book_wishlist'),
        Index('idx_wishlist_user', 'user_id'),
        Index('idx_wishlist_book', 'book_id'),
        Index('idx_wishlist_priority', 'priority'),
    )
    
    def __repr__(self):
        return f'<Wishlist user={self.user_id} book={self.book_id}>'


# ===================== CIRCULATION MODELS =====================

class BorrowRecord(db.Model, TimestampMixin):
    """Traditional borrowing records (legacy)"""
    __tablename__ = 'borrow_records'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Borrowing details
    borrow_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime)
    
    # Status
    status = db.Column(db.String(20), default='borrowed', index=True)  # borrowed, returned, overdue, lost
    
    # Fine
    fine_amount = db.Column(db.Float, default=0.0)
    fine_paid = db.Column(db.Boolean, default=False)
    
    # Renewals
    renewal_count = db.Column(db.Integer, default=0)
    max_renewals = db.Column(db.Integer, default=2)
    
    __table_args__ = (
        Index('idx_borrow_user', 'user_id'),
        Index('idx_borrow_book', 'book_id'),
        Index('idx_borrow_dates', 'borrow_date', 'due_date'),
    )
    
    def calculate_fine(self):
        """Calculate fine if overdue"""
        if self.return_date:
            return 0
        if datetime.now() > self.due_date:
            days_overdue = (datetime.now() - self.due_date).days
            fine_rate = 50  # 50 NGN per day
            return days_overdue * fine_rate
        return 0
    
    def can_renew(self):
        """Check if can be renewed"""
        if self.renewal_count >= self.max_renewals:
            return False
        if self.status != 'borrowed':
            return False
        return True
    
    def __repr__(self):
        return f'<BorrowRecord {self.id}>'


class ItemCopy(db.Model, TimestampMixin, AuditMixin, BarcodeMixin):
    """Individual physical copies of a book"""
    __tablename__ = 'item_copies'
    
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Unique identifiers
    barcode = db.Column(db.String(50), unique=True, nullable=False, index=True)
    accession_number = db.Column(db.String(50), unique=True, index=True)
    rfid_tag = db.Column(db.String(100), unique=True)
    
    # Copy-specific
    copy_number = db.Column(db.Integer, default=1)
    
    # Location
    shelf_location = db.Column(db.String(100))
    floor = db.Column(db.String(10))
    section = db.Column(db.String(50))
    collection = db.Column(db.String(50), default='General')
    
    # Status
    status = db.Column(db.String(20), default='available', nullable=False, index=True)  # available, checked_out, reserved, lost, damaged, in_transit, reference
    condition = db.Column(db.String(20), default='good')  # new, good, fair, poor, damaged
    notes = db.Column(db.Text)
    
    # Acquisition info
    acquisition_date = db.Column(db.DateTime)
    acquisition_type = db.Column(db.String(20), default='purchase')  # purchase, donation, transfer
    cost = db.Column(db.Float)
    vendor = db.Column(db.String(200))
    invoice_number = db.Column(db.String(50))
    
    # Circulation tracking
    current_circulation_id = db.Column(db.Integer, db.ForeignKey('circulation_records.id'), nullable=True)
    total_checkouts = db.Column(db.Integer, default=0)
    last_checkout = db.Column(db.DateTime)
    last_return = db.Column(db.DateTime)
    
    # Reference only (cannot be borrowed)
    is_reference_only = db.Column(db.Boolean, default=False)
    
    # Disposal
    disposed = db.Column(db.Boolean, default=False)
    disposal_date = db.Column(db.DateTime)
    disposal_reason = db.Column(db.String(100))
    disposal_notes = db.Column(db.Text)
    
    # ==================== FIXED RELATIONSHIPS ====================
    # Current circulation (one-to-one)
    current_circulation = db.relationship(
        'CirculationRecord', 
        foreign_keys=[current_circulation_id],
        backref=db.backref('current_copy', uselist=False),
        post_update=True
    )
    
    # All circulations for this copy - using string reference for foreign key
    circulations = db.relationship(
        'CirculationRecord', 
        primaryjoin="ItemCopy.id == CirculationRecord.copy_id",
        back_populates='item_copy',
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    
    # Reservations for this specific copy
    reservations = db.relationship(
        'Reservation', 
        primaryjoin="ItemCopy.id == Reservation.copy_id",
        backref='copy', 
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    
    # Reservations fulfilled by this copy
    fulfilled_reservations = db.relationship(
        'Reservation', 
        primaryjoin="ItemCopy.id == Reservation.fulfilled_copy_id",
        backref='fulfilled_copy', 
        lazy='dynamic'
    )
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_copies_book', 'book_id'),
        Index('idx_copies_barcode', 'barcode'),
        Index('idx_copies_rfid', 'rfid_tag'),
        Index('idx_copies_status', 'status'),
        Index('idx_copies_location', 'shelf_location'),
        UniqueConstraint('book_id', 'copy_number', name='unique_book_copy'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.barcode:
            self.barcode = self.generate_barcode('CP')
    
    def checkout(self, user_id, staff_id, due_date):
        """Check out this copy"""
        if self.status != 'available':
            return False, "Copy not available"
        
        if self.is_reference_only:
            return False, "Reference copy cannot be borrowed"
        
        circulation = CirculationRecord(
            copy_id=self.id,
            user_id=user_id,
            due_date=due_date,
            checkout_staff=staff_id,
            status='active'
        )
        db.session.add(circulation)
        db.session.flush()
        
        self.status = 'checked_out'
        self.current_circulation_id = circulation.id
        self.total_checkouts += 1
        self.last_checkout = datetime.utcnow()
        
        # Update book stats
        self.book.available_copies -= 1
        self.book.borrow_count += 1
        
        return True, circulation
    
    def checkin(self, staff_id):
        """Check in this copy"""
        if self.status != 'checked_out':
            return False, "Copy not checked out"
        
        circulation = self.current_circulation
        if circulation:
            circulation.return_date = datetime.utcnow()
            circulation.return_staff = staff_id
            circulation.status = 'returned'
            
            # Calculate fine
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
        
        self.status = 'available'
        self.current_circulation_id = None
        self.last_return = datetime.utcnow()
        
        # Update book stats
        self.book.available_copies += 1
        
        # Check for reservations
        next_reservation = Reservation.query.filter_by(
            book_id=self.book_id,
            status='active'
        ).order_by(Reservation.position).first()
        
        if next_reservation:
            self.status = 'reserved'
            next_reservation.notify_patron()
        
        return True, circulation
    
    def reserve(self, user_id):
        """Place reservation on this copy"""
        if self.status != 'available':
            return False, "Copy not available"
        
        reservation = Reservation(
            copy_id=self.id,
            user_id=user_id,
            status='active'
        )
        db.session.add(reservation)
        
        self.status = 'reserved'
        self.book.reserved_copies += 1
        
        return True, reservation
    
    def mark_lost(self, user_id=None, reason=None):
        """Mark copy as lost"""
        self.status = 'lost'
        self.notes = f"Marked lost: {reason}" if reason else "Marked lost"
        self.book.lost_copies += 1
        self.book.available_copies -= 1
        
        # Create fine if checked out
        if self.current_circulation:
            fine = Fine(
                circulation_id=self.current_circulation.id,
                user_id=self.current_circulation.user_id,
                amount=self.book.replacement_cost or 5000,
                reason='lost'
            )
            db.session.add(fine)
    
    def mark_damaged(self, notes=None):
        """Mark copy as damaged"""
        self.status = 'damaged'
        self.condition = 'damaged'
        self.notes = notes
        self.book.damaged_copies += 1
        self.book.available_copies -= 1
    
    def is_available(self):
        """Check if copy is available"""
        return self.status == 'available' and not self.is_reference_only
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'barcode': self.barcode,
            'copy_number': self.copy_number,
            'status': self.status,
            'condition': self.condition,
            'location': self.shelf_location,
            'is_reference_only': self.is_reference_only,
            'total_checkouts': self.total_checkouts
        }
    
    def __repr__(self):
        return f'<ItemCopy {self.barcode} ({self.status})>'


class CirculationRecord(db.Model, TimestampMixin):
    """Enhanced circulation records for modern checkout system"""
    __tablename__ = 'circulation_records'
    
    id = db.Column(db.Integer, primary_key=True)
    copy_id = db.Column(db.Integer, db.ForeignKey('item_copies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Checkout details
    checkout_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    checkout_staff = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Renewal tracking
    renewal_count = db.Column(db.Integer, default=0)
    max_renewals = db.Column(db.Integer, default=2)
    last_renewal_date = db.Column(db.DateTime)
    
    # Return details
    return_date = db.Column(db.DateTime)
    return_staff = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Status
    status = db.Column(db.String(20), default='active', index=True)  # active, returned, overdue, lost
    
    # Fine
    fine_amount = db.Column(db.Float, default=0.0)
    fine_paid = db.Column(db.Boolean, default=False)
    fine_paid_date = db.Column(db.DateTime)
    
    # Fine calculation
    fine_rate_per_day = db.Column(db.Float, default=50.0)  # 50 NGN per day
    max_fine = db.Column(db.Float, default=5000.0)  # Maximum fine
    
    # Notes
    notes = db.Column(db.Text)
    
    # ==================== FIXED RELATIONSHIPS ====================
    # The item copy being circulated - using explicit join condition
    item_copy = db.relationship(
        'ItemCopy', 
        primaryjoin="CirculationRecord.copy_id == ItemCopy.id",
        back_populates='circulations'
    )
    
    # The patron
    patron = db.relationship(
        'User', 
        foreign_keys=[user_id],
        back_populates='circulations'
    )
    
    # Staff who checked out
    checkout_operator = db.relationship(
        'User', 
        foreign_keys=[checkout_staff],
        back_populates='checkout_operations'
    )
    
    # Staff who processed return
    return_operator = db.relationship(
        'User', 
        foreign_keys=[return_staff],
        back_populates='return_operations'
    )
    
    # Fines associated with this circulation
    fines = db.relationship(
        'Fine', 
        primaryjoin="CirculationRecord.id == Fine.circulation_id",
        back_populates='circulation_record', 
        lazy='dynamic', 
        cascade='all, delete-orphan'
    )
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_circulation_copy', 'copy_id'),
        Index('idx_circulation_user', 'user_id'),
        Index('idx_circulation_dates', 'checkout_date', 'due_date', 'return_date'),
        Index('idx_circulation_status', 'status'),
    )
    
    # ==================== METHODS ====================
    
    def calculate_fine(self):
        """Calculate current fine amount"""
        if self.return_date:
            # Already returned
            if self.return_date > self.due_date:
                days_overdue = (self.return_date - self.due_date).days
                return min(days_overdue * self.fine_rate_per_day, self.max_fine)
            return 0
        elif self.status == 'active' and datetime.utcnow() > self.due_date:
            # Currently overdue
            days_overdue = (datetime.utcnow() - self.due_date).days
            return min(days_overdue * self.fine_rate_per_day, self.max_fine)
        return 0
    
    def update_fine(self):
        """Update fine amount in database"""
        self.fine_amount = self.calculate_fine()
    
    def can_renew(self):
        """Check if item can be renewed"""
        if self.renewal_count >= self.max_renewals:
            return False
        if self.status != 'active':
            return False
        if self.calculate_fine() > 0:
            return False
        # Check if reserved by another user
        reservation = Reservation.query.filter_by(
            book_id=self.item_copy.book_id,
            status='active'
        ).first()
        return not reservation
    
    def renew(self):
        """Renew the item"""
        if not self.can_renew():
            return False
        
        self.renewal_count += 1
        self.last_renewal_date = datetime.utcnow()
        self.due_date += timedelta(days=14)
        return True
    
    def is_overdue(self):
        """Check if item is overdue"""
        return (self.status == 'active' and 
                datetime.utcnow() > self.due_date and 
                not self.return_date)
    
    @hybrid_property
    def days_overdue(self):
        """Get days overdue"""
        if self.return_date and self.return_date > self.due_date:
            return (self.return_date - self.due_date).days
        elif self.status == 'active' and datetime.utcnow() > self.due_date:
            return (datetime.utcnow() - self.due_date).days
        return 0
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_title': self.item_copy.book.title if self.item_copy and self.item_copy.book else None,
            'book_author': self.item_copy.book.author if self.item_copy and self.item_copy.book else None,
            'copy_barcode': self.item_copy.barcode if self.item_copy else None,
            'patron_name': self.patron.full_name if self.patron else None,
            'patron_username': self.patron.username if self.patron else None,
            'checkout_date': self.checkout_date.isoformat() if self.checkout_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'return_date': self.return_date.isoformat() if self.return_date else None,
            'status': self.status,
            'renewal_count': self.renewal_count,
            'fine': self.calculate_fine(),
            'days_overdue': self.days_overdue
        }
    
    def __repr__(self):
        return f'<CirculationRecord {self.id} {self.status}>'


class Reservation(db.Model, TimestampMixin):
    """Book holds/reservations"""
    __tablename__ = 'reservations'
    
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    copy_id = db.Column(db.Integer, db.ForeignKey('item_copies.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Reservation details
    reservation_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expiration_date = db.Column(db.DateTime)
    position = db.Column(db.Integer)  # Position in queue
    
    # Status
    status = db.Column(db.String(20), default='active', index=True)  # active, fulfilled, expired, cancelled
    
    # Notification
    notification_sent = db.Column(db.Boolean, default=False)
    notification_date = db.Column(db.DateTime)
    
    # Fulfillment
    fulfilled_date = db.Column(db.DateTime)
    fulfilled_copy_id = db.Column(db.Integer, db.ForeignKey('item_copies.id'), nullable=True)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_reservations_book', 'book_id'),
        Index('idx_reservations_user', 'user_id'),
        Index('idx_reservations_status', 'status'),
        Index('idx_reservations_dates', 'reservation_date', 'expiration_date'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.expiration_date:
            self.expiration_date = datetime.utcnow() + timedelta(days=3)
        if not self.position:
            self.position = self.calculate_position()
    
    def calculate_position(self):
        """Calculate position in queue"""
        last = Reservation.query.filter_by(
            book_id=self.book_id,
            status='active'
        ).order_by(Reservation.position.desc()).first()
        return (last.position + 1) if last else 1
    
    def fulfill(self, copy_id=None):
        """Mark reservation as fulfilled"""
        self.status = 'fulfilled'
        self.fulfilled_date = datetime.utcnow()
        if copy_id:
            self.fulfilled_copy_id = copy_id
    
    def cancel(self):
        """Cancel reservation"""
        self.status = 'cancelled'
    
    def expire(self):
        """Mark as expired"""
        self.status = 'expired'
    
    def is_expired(self):
        """Check if reservation has expired"""
        return self.expiration_date and self.expiration_date < datetime.utcnow()
    
    def notify_patron(self):
        """Send notification to patron"""
        self.notification_sent = True
        self.notification_date = datetime.utcnow()
    
    @classmethod
    def get_next_in_queue(cls, book_id):
        """Get next patron in queue"""
        return cls.query.filter_by(
            book_id=book_id,
            status='active'
        ).order_by(cls.position).first()
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'reservation_date': self.reservation_date.isoformat() if self.reservation_date else None,
            'expiration_date': self.expiration_date.isoformat() if self.expiration_date else None,
            'position': self.position,
            'status': self.status
        }
    
    def __repr__(self):
        return f'<Reservation {self.id} pos={self.position}>'


class Fine(db.Model, TimestampMixin):
    """Monetary fines for overdue/lost items"""
    __tablename__ = 'fines'
    
    id = db.Column(db.Integer, primary_key=True)
    circulation_id = db.Column(db.Integer, db.ForeignKey('circulation_records.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Fine details
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(50), default='overdue')  # overdue, lost, damaged
    description = db.Column(db.Text)
    
    # Dates
    assessed_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    due_date = db.Column(db.DateTime)
    
    # Payment
    paid = db.Column(db.Boolean, default=False, index=True)
    paid_date = db.Column(db.DateTime)
    payment_method = db.Column(db.String(50))  # cash, card, online, waiver
    transaction_id = db.Column(db.String(100))
    payment_reference = db.Column(db.String(100))
    
    # Waiver
    waived = db.Column(db.Boolean, default=False)
    waived_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    waived_date = db.Column(db.DateTime)
    waiver_reason = db.Column(db.Text)
    
    # Notes
    notes = db.Column(db.Text)
    
    # ==================== FIXED RELATIONSHIPS ====================
    # All relationships now use back_populates consistently
    
    circulation_record = db.relationship(
        'CirculationRecord', 
        foreign_keys=[circulation_id],
        back_populates='fines'
    )
    
    user = db.relationship(
        'User', 
        foreign_keys=[user_id],
        back_populates='fines'
    )
    
    waiving_officer = db.relationship(
        'User', 
        foreign_keys=[waived_by],
        back_populates='waived_fines'
    )
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_fines_user', 'user_id'),
        Index('idx_fines_circulation', 'circulation_id'),
        Index('idx_fines_status', 'paid', 'waived'),
    )
    
    # ==================== METHODS ====================
    
    def mark_paid(self, method='cash', transaction_id=None, reference=None):
        """Mark fine as paid"""
        self.paid = True
        self.paid_date = datetime.utcnow()
        self.payment_method = method
        self.transaction_id = transaction_id
        self.payment_reference = reference
        
        # Update user stats
        user = User.query.get(self.user_id)
        if user:
            user.total_fines_paid += self.amount
    
    def waive(self, user_id, reason=None):
        """Waive fine"""
        self.waived = True
        self.waived_by = user_id
        self.waived_date = datetime.utcnow()
        self.waiver_reason = reason
        
        # Update user stats
        user = User.query.get(self.user_id)
        if user:
            user.total_fines_waived += self.amount
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'amount': self.amount,
            'reason': self.reason,
            'assessed_date': self.assessed_date.isoformat() if self.assessed_date else None,
            'paid': self.paid,
            'paid_date': self.paid_date.isoformat() if self.paid_date else None,
            'waived': self.waived
        }
    
    def __repr__(self):
        return f'<Fine {self.id} amount={self.amount}>'


class BookReservation(db.Model):
    """Legacy book reservations (kept for backward compatibility)"""
    __tablename__ = 'book_reservations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    reservation_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    notification_sent = db.Column(db.Boolean, default=False)


# ===================== DOWNLOAD AND ACTIVITY MODELS =====================

class DownloadLog(db.Model, TimestampMixin):
    """Track book downloads"""
    __tablename__ = 'download_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Download details
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    format = db.Column(db.String(20))  # pdf, epub, etc.
    file_size = db.Column(db.Integer)
    download_duration = db.Column(db.Float)  # seconds
    
    # Success/Failure
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    
    __table_args__ = (
        Index('idx_downloads_user', 'user_id'),
        Index('idx_downloads_book', 'book_id'),
        Index('idx_downloads_date', 'timestamp'),
    )
    
    def __repr__(self):
        return f'<DownloadLog user={self.user_id} book={self.book_id}>'


class RecentActivity(db.Model, TimestampMixin):
    """Track user activity for dashboards"""
    __tablename__ = 'recent_activities'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    activity_type = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=True)
    
    # Additional data
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    data = db.Column(db.JSON)
    
    __table_args__ = (
        Index('idx_activity_user', 'user_id'),
        Index('idx_activity_type', 'activity_type', 'timestamp'),
    )
    
    @classmethod
    def log(cls, user_id, activity_type, description=None, book_id=None, 
            ip_address=None, user_agent=None, data=None):
        """Create a new activity log"""
        activity = cls(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            book_id=book_id,
            ip_address=ip_address,
            user_agent=user_agent,
            data=data
        )
        db.session.add(activity)
        db.session.commit()
        return activity
    
    def __repr__(self):
        return f'<RecentActivity {self.activity_type}>'


# ===================== WORKFLOW MODELS =====================

class SpecialRequest(db.Model, TimestampMixin):
    """Requests for special/restricted access"""
    __tablename__ = 'special_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    request_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    # Request details
    request_type = db.Column(db.String(50), default='access')  # access, purchase, digitization
    reason = db.Column(db.Text, nullable=False)
    justification = db.Column(db.Text)
    
    # Dates
    requested_date = db.Column(db.Date, default=datetime.utcnow().date)
    needed_by = db.Column(db.Date)
    
    # Review
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)
    
    # Status
    status = db.Column(db.String(20), default='pending', index=True)  # pending, approved, denied, fulfilled
    approval_level = db.Column(db.String(20))  # supervisor, department_head, command
    
    # Fulfillment
    fulfilled_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    fulfilled_at = db.Column(db.DateTime)
    fulfillment_notes = db.Column(db.Text)
    
    # Expiry
    expiry_date = db.Column(db.DateTime)
    
    # ==================== RELATIONSHIPS ====================
    
    requester = db.relationship('User', foreign_keys=[user_id], back_populates='special_requests_submitted')
    book = db.relationship('Book', back_populates='special_requests')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], back_populates='special_requests_reviewed')
    fulfiller = db.relationship('User', foreign_keys=[fulfilled_by])
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_special_user', 'user_id'),
        Index('idx_special_book', 'book_id'),
        Index('idx_special_status', 'status'),
        Index('idx_special_dates', 'created_at', 'needed_by'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.request_number:
            self.request_number = self.generate_request_number()
    
    def generate_request_number(self):
        """Generate unique request number"""
        year = datetime.now().strftime('%Y')
        random_part = ''.join(random.choices(string.digits, k=8))
        return f"SR-{year}-{random_part}"
    
    def approve(self, user_id, notes=None):
        """Approve request"""
        self.status = 'approved'
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes
    
    def deny(self, user_id, notes=None):
        """Deny request"""
        self.status = 'denied'
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes
    
    def fulfill(self, user_id, notes=None):
        """Mark as fulfilled"""
        self.status = 'fulfilled'
        self.fulfilled_by = user_id
        self.fulfilled_at = datetime.utcnow()
        self.fulfillment_notes = notes
    
    def is_expired(self):
        """Check if request has expired"""
        return self.expiry_date and self.expiry_date < datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'request_number': self.request_number,
            'user_id': self.user_id,
            'username': self.requester.username if self.requester else None,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'request_type': self.request_type,
            'reason': self.reason,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'review_notes': self.review_notes
        }
    
    def __repr__(self):
        return f'<SpecialRequest {self.request_number} ({self.status})>'


class AcquisitionRequest(db.Model, TimestampMixin, AuditMixin):
    """Requests for new acquisitions"""
    __tablename__ = 'acquisition_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    request_number = db.Column(db.String(50), unique=True, nullable=False)
    
    # Item details
    title = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(500))
    isbn = db.Column(db.String(20))
    issn = db.Column(db.String(20))
    publisher = db.Column(db.String(255))
    publication_year = db.Column(db.Integer)
    edition = db.Column(db.String(50))
    
    # Request details
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    request_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    justification = db.Column(db.Text)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, urgent
    
    # Material details
    material_type = db.Column(db.String(50), default='book')  # book, journal, dvd, etc.
    format_type = db.Column(db.String(50), default='physical')  # physical, digital, both
    quantity_requested = db.Column(db.Integer, default=1)
    
    # Budget
    estimated_cost = db.Column(db.Float)
    currency = db.Column(db.String(3), default='NGN')
    budget_code = db.Column(db.String(50))
    fund_source = db.Column(db.String(100))
    
    # Status
    status = db.Column(db.String(20), default='pending', index=True)  # pending, approved, rejected, ordered, received
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)
    
    # Order details
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'))
    order_date = db.Column(db.DateTime)
    expected_delivery = db.Column(db.Date)
    
    # Receiving
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    received_date = db.Column(db.DateTime)
    received_condition = db.Column(db.String(50))
    received_notes = db.Column(db.Text)
    
    # ==================== RELATIONSHIPS ====================
    
    purchase_order = db.relationship('PurchaseOrder', backref='acquisition_requests')
    po_items = db.relationship('PurchaseOrderItem', backref='acquisition_request', lazy='dynamic')
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_acquisition_status', 'status'),
        Index('idx_acquisition_priority', 'priority'),
        Index('idx_acquisition_date', 'request_date'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.request_number:
            self.request_number = self.generate_request_number()
    
    def generate_request_number(self):
        """Generate unique request number"""
        year = datetime.now().strftime('%Y')
        random_part = ''.join(random.choices(string.digits, k=6))
        return f"ACQ-{year}-{random_part}"
    
    def approve(self, user_id, notes=None):
        """Approve request"""
        self.status = 'approved'
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes
    
    def reject(self, user_id, notes=None):
        """Reject request"""
        self.status = 'rejected'
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes
    
    def receive(self, user_id, condition=None, notes=None):
        """Mark as received"""
        self.status = 'received'
        self.received_by = user_id
        self.received_date = datetime.utcnow()
        self.received_condition = condition
        self.received_notes = notes
        self.actual_delivery = datetime.utcnow().date()
    
    def to_dict(self):
        return {
            'id': self.id,
            'request_number': self.request_number,
            'title': self.title,
            'author': self.author,
            'isbn': self.isbn,
            'requested_by': self.requester.username if self.requester else None,
            'request_date': self.request_date.isoformat() if self.request_date else None,
            'priority': self.priority,
            'status': self.status,
            'estimated_cost': self.estimated_cost
        }
    
    def __repr__(self):
        return f'<AcquisitionRequest {self.request_number} ({self.status})>'


class PurchaseOrder(db.Model, TimestampMixin, AuditMixin):
    """Purchase orders to vendors"""
    __tablename__ = 'purchase_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(50), unique=True, nullable=False)
    
    # Vendor
    vendor_name = db.Column(db.String(255), nullable=False)
    vendor_address = db.Column(db.Text)
    vendor_contact = db.Column(db.String(100))
    vendor_email = db.Column(db.String(255))
    vendor_phone = db.Column(db.String(50))
    vendor_tax_id = db.Column(db.String(50))
    
    # Dates
    order_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expected_delivery = db.Column(db.Date)
    actual_delivery = db.Column(db.Date)
    
    # Financial
    subtotal = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    shipping = db.Column(db.Float, default=0.0)
    total_cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='NGN')
    
    # Payment
    payment_terms = db.Column(db.String(255))
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, partial
    payment_date = db.Column(db.DateTime)
    payment_method = db.Column(db.String(50))
    payment_reference = db.Column(db.String(100))
    
    # Status
    status = db.Column(db.String(20), default='draft', index=True)  # draft, sent, confirmed, shipped, received, cancelled
    
    # Shipping
    shipping_method = db.Column(db.String(100))
    tracking_number = db.Column(db.String(100))
    shipping_notes = db.Column(db.Text)
    
    # Notes
    notes = db.Column(db.Text)
    internal_notes = db.Column(db.Text)
    
    # ==================== RELATIONSHIPS ====================
    
    items = db.relationship('PurchaseOrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_po_number', 'po_number'),
        Index('idx_po_status', 'status'),
        Index('idx_po_dates', 'order_date', 'expected_delivery'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.po_number:
            self.po_number = self.generate_po_number()
    
    def generate_po_number(self):
        """Generate unique PO number"""
        year = datetime.now().strftime('%Y')
        month = datetime.now().strftime('%m')
        random_part = ''.join(random.choices(string.digits, k=6))
        return f"PO-{year}{month}-{random_part}"
    
    def calculate_totals(self):
        """Calculate total from items"""
        self.subtotal = sum(item.total_price for item in self.items)
        self.total_cost = self.subtotal + self.tax + self.shipping
        return self.total_cost
    
    def send(self):
        """Mark as sent"""
        self.status = 'sent'
        self.order_date = datetime.utcnow()
    
    def confirm(self):
        """Mark as confirmed"""
        self.status = 'confirmed'
    
    def ship(self, tracking_number=None):
        """Mark as shipped"""
        self.status = 'shipped'
        if tracking_number:
            self.tracking_number = tracking_number
    
    def receive(self, date=None):
        """Mark as received"""
        self.status = 'received'
        self.actual_delivery = date or datetime.utcnow().date()
    
    def cancel(self):
        """Cancel order"""
        self.status = 'cancelled'
    
    def mark_paid(self, method=None, reference=None):
        """Mark as paid"""
        self.payment_status = 'paid'
        self.payment_date = datetime.utcnow()
        self.payment_method = method
        self.payment_reference = reference
    
    def to_dict(self):
        return {
            'id': self.id,
            'po_number': self.po_number,
            'vendor_name': self.vendor_name,
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'expected_delivery': self.expected_delivery.isoformat() if self.expected_delivery else None,
            'total_cost': self.total_cost,
            'status': self.status,
            'payment_status': self.payment_status,
            'item_count': self.items.count()
        }
    
    def __repr__(self):
        return f'<PurchaseOrder {self.po_number} ({self.status})>'


class PurchaseOrderItem(db.Model):
    """Items within a purchase order"""
    __tablename__ = 'purchase_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('acquisition_requests.id'), nullable=True)
    
    # Item details
    title = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(500))
    isbn = db.Column(db.String(20))
    publisher = db.Column(db.String(255))
    
    # Quantity
    quantity_ordered = db.Column(db.Integer, default=1, nullable=False)
    quantity_received = db.Column(db.Integer, default=0)
    quantity_invoiced = db.Column(db.Integer, default=0)
    
    # Pricing
    unit_price = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, nullable=False)
    
    # Receiving
    received_date = db.Column(db.DateTime)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    received_condition = db.Column(db.String(50))
    
    # Notes
    notes = db.Column(db.Text)
    
    # ==================== RELATIONSHIPS ====================
    
    receiver = db.relationship('User', foreign_keys=[received_by])
    cataloging_entry = db.relationship('CatalogingQueue', backref='po_item', uselist=False, cascade='all, delete-orphan')
    
    # ==================== METHODS ====================
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calculate_total()
    
    def calculate_total(self):
        """Calculate total price"""
        self.total_price = self.quantity_ordered * self.unit_price * (1 - self.discount/100)
        return self.total_price
    
    def receive(self, quantity, user_id, condition=None):
        """Receive items"""
        self.quantity_received += quantity
        self.received_date = datetime.utcnow()
        self.received_by = user_id
        self.received_condition = condition
    
    def create_cataloging_entry(self):
        """Create cataloging queue entry for received items"""
        if self.quantity_received > 0 and not self.cataloging_entry:
            entry = CatalogingQueue(
                po_item_id=self.id,
                status='pending'
            )
            db.session.add(entry)
            return entry
        return None
    
    def __repr__(self):
        return f'<PurchaseOrderItem {self.title[:50]}>'


class CatalogingQueue(db.Model, TimestampMixin):
    """Queue for items awaiting cataloging"""
    __tablename__ = 'cataloging_queue'
    
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=True)
    po_item_id = db.Column(db.Integer, db.ForeignKey('purchase_order_items.id'), nullable=True)
    
    # Task details
    task_type = db.Column(db.String(50), default='new')  # new, revision, metadata_update
    priority = db.Column(db.Integer, default=5)  # 1-10, higher = more urgent
    
    # Assignment
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))  # <-- This is the cataloger
    assigned_date = db.Column(db.DateTime)
    
    # Status
    status = db.Column(db.String(20), default='pending', index=True)  # pending, in_progress, review, completed, rejected
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Cataloging metadata
    dewey_decimal = db.Column(db.String(20))
    library_of_congress = db.Column(db.String(50))
    subjects = db.Column(db.JSON)
    summary = db.Column(db.Text)
    contents = db.Column(db.Text)  # Table of contents
    
    # Notes
    cataloger_notes = db.Column(db.Text)
    reviewer_notes = db.Column(db.Text)
    
    # Quality control
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    quality_score = db.Column(db.Integer)  # 1-10
    
    # Time tracking
    estimated_hours = db.Column(db.Float)
    actual_hours = db.Column(db.Float)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_cataloging_status', 'status'),
        Index('idx_cataloging_priority', 'priority'),
        Index('idx_cataloging_assigned', 'assigned_to'),
    )
    
    # ==================== METHODS ====================
    
    def assign(self, user_id):
        """Assign to cataloger"""
        self.assigned_to = user_id
        self.assigned_date = datetime.utcnow()
        self.status = 'in_progress'
        self.started_at = datetime.utcnow()
    
    def complete(self, user_id, notes=None):
        """Mark as completed"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.cataloger_notes = notes
        
        # Update actual hours
        if self.started_at:
            self.actual_hours = (self.completed_at - self.started_at).total_seconds() / 3600
    
    def submit_for_review(self):
        """Submit for quality review"""
        self.status = 'review'
    
    def approve_review(self, user_id, notes=None, score=None):
        """Approve cataloging"""
        self.status = 'completed'
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        self.reviewer_notes = notes
        if score:
            self.quality_score = score
    
    def reject_review(self, user_id, notes=None):
        """Reject cataloging and send back"""
        self.status = 'in_progress'
        self.reviewed_by = user_id
        self.reviewed_at = datetime.utcnow()
        self.reviewer_notes = notes
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'status': self.status,
            'priority': self.priority,
            'assigned_to': self.cataloger.username if self.cataloger else None,
            'assigned_date': self.assigned_date.isoformat() if self.assigned_date else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
    
    def __repr__(self):
        return f'<CatalogingQueue {self.id} ({self.status})>'


# ===================== NEW SYSTEM MODELS =====================

class SystemSetting(db.Model, TimestampMixin):
    """System configuration settings"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    type = db.Column(db.String(20), default='string')  # string, integer, boolean, json, float
    
    # Metadata
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    is_public = db.Column(db.Boolean, default=False)
    is_editable = db.Column(db.Boolean, default=True)
    
    # Audit
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_settings_category', 'category'),
    )
    
    # ==================== METHODS ====================
    
    @classmethod
    def get(cls, key, default=None):
        """Get setting value by key"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if setting.type == 'boolean':
            return setting.value.lower() == 'true'
        elif setting.type == 'integer':
            return int(setting.value)
        elif setting.type == 'float':
            return float(setting.value)
        elif setting.type == 'json':
            return json.loads(setting.value)
        return setting.value
    
    @classmethod
    def set(cls, key, value, user_id=None, description=None, category=None):
        """Set setting value"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(key=key)
            db.session.add(setting)
        
        # Determine type and store value
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
        
        if description:
            setting.description = description
        if category:
            setting.category = category
        
        setting.updated_by = user_id
        db.session.commit()
        return setting
    
    @classmethod
    def get_all(cls, category=None):
        """Get all settings, optionally filtered by category"""
        query = cls.query
        if category:
            query = query.filter_by(category=category)
        settings = {}
        for setting in query.all():
            settings[setting.key] = cls.get(setting.key)
        return settings
    
    def __repr__(self):
        return f'<SystemSetting {self.key}={self.value}>'


class Notification(db.Model, TimestampMixin):
    """User notifications"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Content
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')  # info, success, warning, error
    category = db.Column(db.String(50))  # circulation, fine, reservation, system, newsletter
    
    # Links
    link = db.Column(db.String(500))
    link_text = db.Column(db.String(100))
    
    # Status
    is_read = db.Column(db.Boolean, default=False, index=True)
    read_at = db.Column(db.DateTime)
    is_archived = db.Column(db.Boolean, default=False)
    
    # Delivery tracking
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_at = db.Column(db.DateTime)
    sms_sent = db.Column(db.Boolean, default=False)
    push_sent = db.Column(db.Boolean, default=False)
    
    # Priority
    priority = db.Column(db.Integer, default=0)  # 0-10, higher = more important
    
    # Expiry
    expires_at = db.Column(db.DateTime)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_notifications_user', 'user_id', 'is_read'),
        Index('idx_notifications_type', 'type', 'created_at'),
        Index('idx_notifications_priority', 'priority'),
    )
    
    # ==================== METHODS ====================
    
    def mark_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.read_at = datetime.utcnow()
    
    def mark_unread(self):
        """Mark as unread"""
        self.is_read = False
        self.read_at = None
    
    def archive(self):
        """Archive notification"""
        self.is_archived = True
    
    def is_expired(self):
        """Check if notification has expired"""
        return self.expires_at and self.expires_at < datetime.utcnow()
    
    @classmethod
    def send(cls, user_id, title, message, type='info', category=None, 
             link=None, link_text=None, priority=0):
        """Create and send notification"""
        notification = cls(
            user_id=user_id,
            title=title,
            message=message,
            type=type,
            category=category,
            link=link,
            link_text=link_text,
            priority=priority
        )
        db.session.add(notification)
        db.session.commit()
        
        # TODO: Trigger actual delivery (email, SMS, push)
        return notification
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'category': self.category,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'link': self.link,
            'link_text': self.link_text
        }
    
    def __repr__(self):
        return f'<Notification {self.id} ({self.type})>'


class Announcement(db.Model, TimestampMixin):
    """Library announcements and news"""
    __tablename__ = 'announcements'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    
    # Type
    type = db.Column(db.String(50), default='general')  # general, maintenance, event, holiday, emergency
    
    # Scheduling
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    # Targeting
    target_roles = db.Column(db.JSON)  # Array of roles to show to
    is_public = db.Column(db.Boolean, default=True)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_featured = db.Column(db.Boolean, default=False)
    is_pinned = db.Column(db.Boolean, default=False)
    
    # Views
    view_count = db.Column(db.Integer, default=0)
    
    # Author
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_announcements_active', 'is_active', 'published_at'),
        Index('idx_announcements_type', 'type'),
    )
    
    # ==================== METHODS ====================
    
    def is_expired(self):
        """Check if announcement has expired"""
        return self.expires_at and self.expires_at < datetime.utcnow()
    
    def can_view(self, user):
        """Check if user can view this announcement"""
        if not self.is_active:
            return False
        if self.is_expired():
            return False
        if self.is_public:
            return True
        if not user:
            return False
        if not self.target_roles:
            return True
        return user.role in self.target_roles
    
    def increment_view(self):
        """Increment view count"""
        self.view_count += 1
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'type': self.type,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'is_active': self.is_active,
            'is_featured': self.is_featured,
            'is_pinned': self.is_pinned
        }
    
    def __repr__(self):
        return f'<Announcement {self.title}>'


class AuditLog(db.Model):
    """Comprehensive audit trail"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # User info
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(80))
    user_role = db.Column(db.String(20))
    
    # Action details
    action = db.Column(db.String(50), nullable=False, index=True)
    category = db.Column(db.String(50))
    description = db.Column(db.Text)
    
    # Target
    target_type = db.Column(db.String(50))  # book, user, circulation, etc.
    target_id = db.Column(db.Integer)
    target_name = db.Column(db.String(255))
    
    # Request context
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    endpoint = db.Column(db.String(255))
    method = db.Column(db.String(10))
    
    # Data changes
    old_values = db.Column(db.JSON)
    new_values = db.Column(db.JSON)
    metadata_json = db.Column(db.JSON)
    
    # Result
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_audit_user', 'user_id'),
        Index('idx_audit_action', 'action'),
        Index('idx_audit_target', 'target_type', 'target_id'),
        Index('idx_audit_category', 'category'),
    )
    
    # ==================== METHODS ====================
    
    @classmethod
    def log(cls, user_id, action, description=None, target_type=None, 
            target_id=None, target_name=None, request=None, old_values=None, 
            new_values=None, metadata=None, success=True, error_message=None):
        """Create audit log entry"""
        from flask import request as flask_request
        
        if request is None and flask_request:
            request = flask_request
        
        user = User.query.get(user_id) if user_id else None
        
        log_entry = cls(
            user_id=user_id,
            username=user.username if user else None,
            user_role=user.role if user else None,
            action=action,
            description=description,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
            endpoint=request.endpoint if request else None,
            method=request.method if request else None,
            old_values=old_values,
            new_values=new_values,
            metadata=metadata,
            success=success,
            error_message=error_message
        )
        
        db.session.add(log_entry)
        db.session.commit()
        
        return log_entry
    
    def __repr__(self):
        return f'<AuditLog {self.id} {self.action}>'


class ApiKey(db.Model, TimestampMixin):
    """API keys for programmatic access"""
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100))
    description = db.Column(db.Text)
    
    # Permissions
    permissions = db.Column(db.JSON)  # Array of allowed endpoints
    rate_limit = db.Column(db.String(50))  # e.g., "100/hour"
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    expires_at = db.Column(db.DateTime)
    last_used_at = db.Column(db.DateTime)
    
    # Usage tracking
    total_requests = db.Column(db.Integer, default=0)
    total_bytes_sent = db.Column(db.Integer, default=0)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_api_key', 'key'),
        Index('idx_api_expiry', 'expires_at'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.key:
            self.key = self.generate_key()
    
    def generate_key(self):
        """Generate new API key"""
        return secrets.token_urlsafe(32)
    
    def record_usage(self, bytes_sent=0):
        """Record API usage"""
        self.total_requests += 1
        self.total_bytes_sent += bytes_sent
        self.last_used_at = datetime.utcnow()
    
    def is_valid(self):
        """Check if key is valid"""
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True
    
    def revoke(self):
        """Revoke API key"""
        self.is_active = False
    
    def __repr__(self):
        return f'<ApiKey {self.name}>'


class BackupLog(db.Model, TimestampMixin):
    """Database backup tracking"""
    __tablename__ = 'backup_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)  # in bytes
    file_path = db.Column(db.String(500))
    
    # Backup details
    backup_type = db.Column(db.String(20))  # full, incremental
    status = db.Column(db.String(20), default='completed', index=True)  # completed, failed, in_progress
    error_message = db.Column(db.Text)
    
    # Metadata
    database_size = db.Column(db.Integer)
    table_count = db.Column(db.Integer)
    record_count = db.Column(db.Integer)
    
    # S3/Cloud backup
    s3_key = db.Column(db.String(500))
    s3_uploaded = db.Column(db.Boolean, default=False)
    s3_uploaded_at = db.Column(db.DateTime)
    
    # Restoration
    restored_at = db.Column(db.DateTime)
    restored_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Retention
    expires_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    
    # ==================== METHODS ====================
    
    @property
    def file_size_formatted(self):
        """Format file size"""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024*1024:
            return f"{self.file_size/1024:.1f} KB"
        elif self.file_size < 1024*1024*1024:
            return f"{self.file_size/(1024*1024):.1f} MB"
        else:
            return f"{self.file_size/(1024*1024*1024):.1f} GB"
    
    def mark_uploaded(self, s3_key):
        """Mark as uploaded to cloud"""
        self.s3_uploaded = True
        self.s3_uploaded_at = datetime.utcnow()
        self.s3_key = s3_key
    
    def mark_restored(self, user_id):
        """Mark as restored"""
        self.restored_at = datetime.utcnow()
        self.restored_by = user_id
    
    def __repr__(self):
        return f'<BackupLog {self.filename}>'


class ScheduledReport(db.Model, TimestampMixin):
    """Scheduled report generation"""
    __tablename__ = 'scheduled_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    # Report type
    report_type = db.Column(db.String(50), nullable=False)  # circulation, acquisition, usage, fines, etc.
    format = db.Column(db.String(20), default='pdf')  # pdf, excel, csv, html
    
    # Schedule
    frequency = db.Column(db.String(20))  # daily, weekly, monthly, quarterly
    day_of_week = db.Column(db.Integer)  # 0-6 for weekly
    day_of_month = db.Column(db.Integer)  # 1-31 for monthly
    time = db.Column(db.Time)
    
    # Parameters
    parameters = db.Column(db.JSON)
    
    # Recipients
    recipients = db.Column(db.JSON)  # Array of email addresses
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    error_count = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)
    
    # Audit
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_reports_schedule', 'next_run', 'is_active'),
        Index('idx_reports_type', 'report_type'),
    )
    
    # ==================== METHODS ====================
    
    def calculate_next_run(self):
        """Calculate next run datetime"""
        from dateutil.relativedelta import relativedelta
        
        now = datetime.now()
        
        if self.frequency == 'daily':
            next_run = datetime.combine(now.date(), self.time)
            if next_run <= now:
                next_run += timedelta(days=1)
        
        elif self.frequency == 'weekly':
            days_ahead = self.day_of_week - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_date = now.date() + timedelta(days=days_ahead)
            next_run = datetime.combine(next_date, self.time)
            if next_run <= now:
                next_run += timedelta(days=7)
        
        elif self.frequency == 'monthly':
            next_date = now.date().replace(day=self.day_of_month)
            if next_date <= now.date():
                next_date += relativedelta(months=1)
            next_run = datetime.combine(next_date, self.time)
        
        else:
            next_run = now + timedelta(days=1)
        
        self.next_run = next_run
        return self.next_run
    
    def mark_run(self, success=True, error=None):
        """Mark report as run"""
        self.last_run = datetime.utcnow()
        if success:
            self.error_count = 0
            self.last_error = None
        else:
            self.error_count += 1
            self.last_error = error
        self.calculate_next_run()
    
    def __repr__(self):
        return f'<ScheduledReport {self.name}>'


class Vendor(db.Model, TimestampMixin):
    """Vendor/supplier management"""
    __tablename__ = 'vendors'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(50), unique=True)
    
    # Contact info
    contact_person = db.Column(db.String(255))
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    website = db.Column(db.String(255))
    
    # Business details
    tax_id = db.Column(db.String(50))
    payment_terms = db.Column(db.String(100))
    currency = db.Column(db.String(3), default='NGN')
    
    # Performance
    rating = db.Column(db.Float, default=0.0)
    total_orders = db.Column(db.Integer, default=0)
    total_spent = db.Column(db.Float, default=0.0)
    avg_delivery_days = db.Column(db.Float)
    
    # Categories
    categories = db.Column(db.JSON)  # Types of materials they supply
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_vendors_code', 'code'),
        Index('idx_vendors_active', 'is_active'),
    )
    
    # ==================== METHODS ====================
    
    def update_stats(self):
        """Update vendor statistics"""
        from sqlalchemy import func
        
        # Count orders
        self.total_orders = PurchaseOrder.query.filter_by(vendor_name=self.name).count()
        
        # Calculate total spent
        result = db.session.query(
            func.sum(PurchaseOrder.total_cost)
        ).filter(PurchaseOrder.vendor_name == self.name).first()
        self.total_spent = result[0] or 0.0
        
        # Calculate average delivery days
        delivered_orders = PurchaseOrder.query.filter(
            PurchaseOrder.vendor_name == self.name,
            PurchaseOrder.actual_delivery.isnot(None),
            PurchaseOrder.expected_delivery.isnot(None)
        ).all()
        
        if delivered_orders:
            total_days = sum(
                (order.actual_delivery - order.expected_delivery).days
                for order in delivered_orders
            )
            self.avg_delivery_days = total_days / len(delivered_orders)
    
    def __repr__(self):
        return f'<Vendor {self.name}>'


class Budget(db.Model, TimestampMixin):
    """Budget tracking for acquisitions"""
    __tablename__ = 'budgets'
    
    id = db.Column(db.Integer, primary_key=True)
    fiscal_year = db.Column(db.Integer, nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    
    # Amounts
    allocated = db.Column(db.Float, nullable=False)
    committed = db.Column(db.Float, default=0.0)  # Purchase orders
    expended = db.Column(db.Float, default=0.0)   # Received/invoiced
    remaining = db.Column(db.Float)
    
    # Department
    department = db.Column(db.String(100))
    fund_source = db.Column(db.String(100))
    
    # Period
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_budgets_year', 'fiscal_year'),
        Index('idx_budgets_code', 'code'),
        UniqueConstraint('fiscal_year', 'code', name='unique_budget_year_code'),
    )
    
    # ==================== METHODS ====================
    
    def calculate_remaining(self):
        """Calculate remaining budget"""
        self.remaining = self.allocated - self.committed - self.expended
        return self.remaining
    
    def commit_amount(self, amount):
        """Commit amount to budget"""
        self.committed += amount
        self.calculate_remaining()
    
    def expend_amount(self, amount):
        """Expend amount from budget"""
        self.expended += amount
        self.calculate_remaining()
    
    def release_commitment(self, amount):
        """Release committed amount"""
        self.committed -= amount
        self.calculate_remaining()
    
    def can_commit(self, amount):
        """Check if amount can be committed"""
        return (self.allocated - self.committed - self.expended) >= amount
    
    @property
    def utilization_percentage(self):
        """Calculate budget utilization percentage"""
        if self.allocated == 0:
            return 0
        return ((self.committed + self.expended) / self.allocated) * 100
    
    def __repr__(self):
        return f'<Budget {self.code} {self.fiscal_year}>'


class UserSession(db.Model):
    """Track user login sessions"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    session_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    # Location (if available)
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # Device info
    device_type = db.Column(db.String(50))  # mobile, tablet, desktop
    browser = db.Column(db.String(100))
    browser_version = db.Column(db.String(50))
    os = db.Column(db.String(100))
    os_version = db.Column(db.String(50))
    
    # Timing
    login_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    logout_time = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    # ==================== TABLE ARGS ====================
    
    __table_args__ = (
        Index('idx_sessions_user', 'user_id'),
        Index('idx_sessions_active', 'is_active', 'last_activity'),
    )
    
    # ==================== METHODS ====================
    
    def update_activity(self):
        """Update last activity time"""
        self.last_activity = datetime.utcnow()
    
    def end_session(self):
        """End the session"""
        self.is_active = False
        self.logout_time = datetime.utcnow()
    
    def get_duration(self):
        """Get session duration"""
        end = self.logout_time or datetime.utcnow()
        return (end - self.login_time).total_seconds()
    
    def get_duration_formatted(self):
        """Get formatted duration"""
        seconds = self.get_duration()
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    
    def __repr__(self):
        return f'<UserSession {self.user_id} {self.device_type}>'


# ===================== DYNAMIC CATEGORY & TAG SYSTEM =====================
# (These models must be defined before they're referenced in relationships)

class Category(db.Model, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """Dynamic category system with hierarchy"""
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    
    # Hierarchy (self-referential)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    level = db.Column(db.Integer, default=0)  # For hierarchy depth
    
    # Metadata
    icon = db.Column(db.String(50))  # Font Awesome icon class
    color = db.Column(db.String(20))  # Theme color
    image = db.Column(db.String(255))  # Category image
    
    # Statistics
    book_count = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)
    
    # SEO
    meta_title = db.Column(db.String(200))
    meta_description = db.Column(db.Text)
    meta_keywords = db.Column(db.String(500))
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_featured = db.Column(db.Boolean, default=False)
    display_order = db.Column(db.Integer, default=0)
    
    # ==================== RELATIONSHIPS ====================
    parent = db.relationship('Category', remote_side=[id], backref=db.backref('children', lazy='dynamic'))
    books = db.relationship('BookCategory', back_populates='category', lazy='dynamic', cascade='all, delete-orphan')
    
    # ==================== TABLE ARGS ====================
    __table_args__ = (
        Index('idx_categories_slug', 'slug'),
        Index('idx_categories_parent', 'parent_id'),
        Index('idx_categories_active', 'is_active', 'display_order'),
        UniqueConstraint('name', 'parent_id', name='unique_category_name_per_parent'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.slug:
            self.slug = self.generate_slug()
    
    def generate_slug(self):
        """Generate URL-friendly slug from name"""
        import re
        slug = re.sub(r'[^\w\s-]', '', self.name.lower())
        slug = re.sub(r'[-\s]+', '-', slug).strip('-')
        return slug
    
    def update_book_count(self):
        """Update the count of books in this category"""
        self.book_count = self.books.count()
        return self.book_count
    
    def get_full_path(self):
        """Get full category path (e.g., Fiction > Science Fiction > Cyberpunk)"""
        if self.parent:
            return f"{self.parent.get_full_path()} > {self.name}"
        return self.name
    
    def get_ancestors(self):
        """Get all ancestor categories"""
        ancestors = []
        parent = self.parent
        while parent:
            ancestors.append(parent)
            parent = parent.parent
        return ancestors[::-1]  # Reverse to get top-down
    
    def get_descendants(self, include_self=False):
        """Get all descendant categories"""
        descendants = []
        if include_self:
            descendants.append(self)
        for child in self.children:
            descendants.extend(child.get_descendants(include_self=True))
        return descendants
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'parent_id': self.parent_id,
            'level': self.level,
            'icon': self.icon,
            'color': self.color,
            'book_count': self.book_count,
            'is_active': self.is_active,
            'is_featured': self.is_featured,
            'full_path': self.get_full_path()
        }
    
    def __repr__(self):
        return f'<Category {self.name}>'


class Tag(db.Model, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """Professional tagging system with metadata"""
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    
    # Tag type/category
    type = db.Column(db.String(20), default='general')  # general, subject, genre, format, audience
    
    # Metadata
    color = db.Column(db.String(20))  # Theme color for UI
    icon = db.Column(db.String(50))  # Font Awesome icon
    
    # Statistics
    usage_count = db.Column(db.Integer, default=0)
    trending_score = db.Column(db.Float, default=0.0)  # For trending tags
    
    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_featured = db.Column(db.Boolean, default=False)
    
    # ==================== RELATIONSHIPS ====================
    books = db.relationship('BookTag', back_populates='tag', lazy='dynamic', cascade='all, delete-orphan')
    
    # ==================== TABLE ARGS ====================
    __table_args__ = (
        Index('idx_tags_slug', 'slug'),
        Index('idx_tags_type', 'type'),
        Index('idx_tags_trending', 'trending_score', 'usage_count'),
    )
    
    # ==================== METHODS ====================
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.slug:
            self.slug = self.generate_slug()
    
    def generate_slug(self):
        """Generate URL-friendly slug from name"""
        import re
        slug = re.sub(r'[^\w\s-]', '', self.name.lower())
        slug = re.sub(r'[-\s]+', '-', slug).strip('-')
        return slug
    
    def update_usage_count(self):
        """Update tag usage count"""
        self.usage_count = self.books.count()
        return self.usage_count
    
    def update_trending_score(self, period_days=7):
        """Calculate trending score based on recent usage"""
        from sqlalchemy import func
        from datetime import datetime, timedelta
        
        recent_cutoff = datetime.utcnow() - timedelta(days=period_days)
        
        # Count recent uses
        recent_count = BookTag.query.filter(
            BookTag.tag_id == self.id,
            BookTag.created_at >= recent_cutoff
        ).count()
        
        # Calculate score (can be customized)
        # Simple formula: recent_uses * 2 + total_uses * 0.1
        self.trending_score = (recent_count * 2) + (self.usage_count * 0.1)
        return self.trending_score
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'type': self.type,
            'color': self.color,
            'icon': self.icon,
            'usage_count': self.usage_count,
            'trending_score': self.trending_score,
            'is_active': self.is_active,
            'is_featured': self.is_featured
        }
    
    def __repr__(self):
        return f'<Tag {self.name}>'


# Association tables for many-to-many relationships
class BookCategory(db.Model, TimestampMixin):
    """Association table for books and categories (many-to-many)"""
    __tablename__ = 'book_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    
    # Additional metadata
    is_primary = db.Column(db.Boolean, default=False)  # Primary category
    weight = db.Column(db.Float, default=1.0)  # Relevance weight
    
    # ==================== RELATIONSHIPS ====================
    book = db.relationship('Book', back_populates='categories_assoc')
    category = db.relationship('Category', back_populates='books')
    
    # ==================== TABLE ARGS ====================
    __table_args__ = (
        UniqueConstraint('book_id', 'category_id', name='unique_book_category'),
        Index('idx_book_categories_book', 'book_id'),
        Index('idx_book_categories_category', 'category_id'),
    )


class BookTag(db.Model, TimestampMixin):
    """Association table for books and tags (many-to-many)"""
    __tablename__ = 'book_tags'
    
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), nullable=False)
    
    # Additional metadata
    confidence = db.Column(db.Float, default=1.0)  # Auto-tagging confidence
    is_auto_generated = db.Column(db.Boolean, default=False)
    
    # ==================== RELATIONSHIPS ====================
    book = db.relationship('Book', back_populates='tags_assoc')
    tag = db.relationship('Tag', back_populates='books')
    
    # ==================== TABLE ARGS ====================
    __table_args__ = (
        UniqueConstraint('book_id', 'tag_id', name='unique_book_tag'),
        Index('idx_book_tags_book', 'book_id'),
        Index('idx_book_tags_tag', 'tag_id'),
    )


# ===================== EVENT LISTENERS =====================

@event.listens_for(Book, 'after_insert')
def book_after_insert(mapper, connection, target):
    """Index book after insert"""
    try:
        from tasks.indexing_tasks import index_book_task
        index_book_task.delay(target.id)
    except ImportError:
        pass

@event.listens_for(Book, 'after_update')
def book_after_update(mapper, connection, target):
    """Re-index book after update"""
    try:
        from tasks.indexing_tasks import index_book_task
        index_book_task.delay(target.id)
    except ImportError:
        pass

@event.listens_for(Book, 'after_delete')
def book_after_delete(mapper, connection, target):
    """Remove book from index after delete"""
    try:
        from tasks.indexing_tasks import delete_book_task
        delete_book_task.delay(target.id)
    except ImportError:
        pass

@event.listens_for(Review, 'after_insert')
@event.listens_for(Review, 'after_update')
@event.listens_for(Review, 'after_delete')
def update_book_rating(mapper, connection, target):
    """Update book average rating when review changes"""
    book = Book.query.get(target.book_id)
    if book:
        book.update_rating()
        db.session.commit()

@event.listens_for(CirculationRecord, 'after_insert')
@event.listens_for(CirculationRecord, 'after_update')
def update_copy_status(mapper, connection, target):
    """Update copy status when circulation changes"""
    copy = ItemCopy.query.get(target.copy_id)
    if copy and target.status == 'active':
        copy.status = 'checked_out'
    elif copy and target.status == 'returned':
        copy.status = 'available'
    db.session.commit()


# ===================== INITIALIZATION FUNCTION =====================

def init_db():
    """Initialize database with default data"""
    # Create tables
    db.create_all()
    
    # Create default admin user if not exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@library.gov.ng',
            full_name='System Administrator',
            role='admin',
            approval_status='approved',
            membership_status='active',
            security_clearance='top_secret'
        )
        admin.set_password('Admin@123')  # Change this in production!
        db.session.add(admin)
        db.session.flush()
        
        # Create library card for admin
        card = LibraryCard(
            user_id=admin.id,
            card_type='admin',
            card_holder_name=admin.full_name
        )
        db.session.add(card)
        
        db.session.commit()
    
    # Create default settings
    default_settings = {
        'site_name': ('Nigerian Army E-Library', 'Site name', 'general'),
        'site_description': ('Official Digital Library of the Nigerian Army', 'Site description', 'general'),
        'items_per_page': ('20', 'Number of items per page', 'general'),
        'allow_registration': ('true', 'Allow user registration', 'security'),
        'require_email_verification': ('true', 'Require email verification', 'security'),
        'require_admin_approval': ('true', 'Require admin approval for new users', 'security'),
        'max_borrow_days': ('14', 'Maximum borrow days', 'circulation'),
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
        'two_factor_required': ('false', 'Require two-factor authentication for admin', 'security'),
        'maintenance_mode': ('false', 'Maintenance mode', 'system'),
        'maintenance_message': ('System under maintenance. Please try again later.', 'Maintenance message', 'system'),
        'contact_email': ('admin@library.gov.ng', 'Contact email', 'general'),
        'support_phone': ('+234123456789', 'Support phone', 'general'),
    }
    
    for key, (value, description, category) in default_settings.items():
        if not SystemSetting.query.filter_by(key=key).first():
            SystemSetting.set(key, value, description=description, category=category)
    
    # Create some default categories
    if Category.query.count() == 0:
        fiction = Category(name='Fiction', icon='book', color='#1a3c1a', is_featured=True)
        non_fiction = Category(name='Non-Fiction', icon='book-open', color='#2d5a2d', is_featured=True)
        science = Category(name='Science', icon='flask', color='#2563eb', parent=non_fiction)
        history = Category(name='History', icon='landmark', color='#b45309', parent=non_fiction)
        
        db.session.add_all([fiction, non_fiction, science, history])
        db.session.commit()
    
    # Create some default tags
    if Tag.query.count() == 0:
        tags = [
            Tag(name='Bestseller', type='status', color='#f59e0b', icon='star'),
            Tag(name='New Release', type='status', color='#10b981', icon='sparkles'),
            Tag(name='Classic', type='genre', color='#6b7280', icon='crown'),
            Tag(name='Military Strategy', type='subject', color='#1a3c1a', icon='shield'),
            Tag(name='Leadership', type='subject', color='#2563eb', icon='users'),
            Tag(name='Cyber Security', type='subject', color='#dc2626', icon='shield'),
            Tag(name='PDF', type='format', color='#059669', icon='file-pdf'),
            Tag(name='EPUB', type='format', color='#7c3aed', icon='file'),
        ]
        db.session.add_all(tags)
        db.session.commit()
    
    print("Database initialized successfully!")