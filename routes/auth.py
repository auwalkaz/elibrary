from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, LibraryCard, ReadingHistory, Wishlist, Review, BorrowRecord, DownloadLog, BookReservation, SpecialRequest, Book
from datetime import datetime, timedelta
import random
import string
from functools import wraps
import os
import imghdr
import uuid
import logging
import re
import secrets
import requests
import base64
import json
from urllib.parse import urlencode
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

# ===================== CONSTANTS =====================

MILITARY_EMAIL_DOMAIN = '@army.mil.ng'
SERVICE_NUMBER_PATTERN = r'^NA\/[0-9]{3}\/[0-9]{2}$'
PASSWORD_MIN_LENGTH = 8

# ===================== VALIDATION FUNCTIONS =====================

def validate_military_email(email):
    """Validate military email format"""
    if not email or not isinstance(email, str):
        return False, "Email is required"
    
    email = email.lower().strip()
    
    if not email:
        return False, "Email is required"
    
    if not email.endswith(MILITARY_EMAIL_DOMAIN):
        return False, f"Military email must end with {MILITARY_EMAIL_DOMAIN}"
    
    pattern = r'^[a-zA-Z0-9._%+-]+@army\.mil\.ng$'
    if not re.match(pattern, email):
        return False, "Please use a valid Nigerian Army email format (e.g., name@army.mil.ng)"
    
    return True, "Valid army email"


def validate_civilian_email(email):
    """Validate civilian email (any valid email format)"""
    if not email or not isinstance(email, str):
        return False, "Email is required"
    
    email = email.lower().strip()
    
    if not email:
        return False, "Email is required"
    
    # Basic email validation for civilians
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Please enter a valid email address"
    
    return True, "Valid email"


def validate_army_email(email):
    """Legacy function - for backward compatibility"""
    return validate_military_email(email)


def validate_service_number(service_number):
    """Validate service number format NA/xxx/xx"""
    if not service_number or not isinstance(service_number, str):
        return False, "Service number is required for military personnel"
    
    service_number = service_number.upper().strip()
    
    if not re.match(SERVICE_NUMBER_PATTERN, service_number):
        return False, "Invalid service number format. Use NA/xxx/xx (e.g., NA/123/23)"
    
    return True, "Valid service number"


def validate_password_strength(password):
    """Validate password strength"""
    if not password:
        return False, "Password is required"
    
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
    
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    return True, "Password strength acceptable"


# ===================== DECORATORS =====================

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": "Please login to access this page."}), 401
            flash("Please login to access this page.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": "Admin access required."}), 403
            flash("Admin access required.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def profile_complete_required(f):
    """Decorator to require complete profile before accessing certain features"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        if user and not user.profile_complete:
            flash("Please complete your profile before accessing this feature.")
            return redirect(url_for('auth.complete_profile'))
        return f(*args, **kwargs)
    return decorated_function


# ===================== NOTIFICATION HELPERS =====================

def send_user_notification(user, subject, message):
    """Send notification to user based on their preference"""
    try:
        print(f"📧 Email to {user.email}: {subject}")
        print(f"Message: {message}")
    except Exception as e:
        logger.error(f"Error sending notification: {e}")


def get_approval_email_template(user, status, reason=None):
    """Generate approval email template"""
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5010')
    
    if status == 'approved':
        return f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #1a3c1a, #2d5a2d); padding: 30px; text-align: center; }}
                .header h1 {{ color: white; margin: 0; }}
                .content {{ background: white; padding: 30px; border: 2px solid #1a3c1a; border-top: none; }}
                .button {{ display: inline-block; background: #1a3c1a; color: white; padding: 12px 30px; 
                         text-decoration: none; border-radius: 25px; margin-top: 20px; }}
                .info-box {{ background: #f0f9f0; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Nigerian Army E-Library</h1>
                </div>
                <div class="content">
                    <h2 style="color: #1a3c1a;">Welcome, {user.full_name or user.username}!</h2>
                    <p>Your registration has been <span style="color: #10b981; font-weight: bold;">APPROVED</span>.</p>
                    
                    <p>Please login to your account and complete your profile to activate your library card.</p>
                    
                    <div class="info-box">
                        <p><strong>Username:</strong> {user.username}</p>
                        <p><strong>Email:</strong> {user.email}</p>
                        <p><strong>Status:</strong> Approved - Awaiting Profile Completion</p>
                    </div>
                    
                    <p>After completing your profile, your library card will be generated automatically.</p>
                    
                    <a href="{base_url}/auth/login" class="button">Login to Complete Profile</a>
                    
                    <div class="footer">
                        <p>If you have any questions, please contact the library administrator.</p>
                        <p>© Nigerian Army E-Library</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    else:
        return f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #8b0000, #a52a2a); padding: 30px; text-align: center; }}
                .header h1 {{ color: white; margin: 0; }}
                .content {{ background: white; padding: 30px; border: 2px solid #8b0000; border-top: none; }}
                .button {{ display: inline-block; background: #8b0000; color: white; padding: 12px 30px; 
                         text-decoration: none; border-radius: 25px; margin-top: 20px; }}
                .info-box {{ background: #fef2f2; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .footer {{ margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Nigerian Army E-Library</h1>
                </div>
                <div class="content">
                    <h2 style="color: #8b0000;">Registration Update</h2>
                    <p>Your registration has been <span style="color: #dc2626; font-weight: bold;">REJECTED</span>.</p>
                    
                    <div class="info-box">
                        <p><strong>Reason:</strong> {reason or 'Not specified'}</p>
                    </div>
                    
                    <p>If you believe this is an error, please contact the library administrator.</p>
                    <a href="{base_url}/contact" class="button">Contact Support</a>
                    
                    <div class="footer">
                        <p>© Nigerian Army E-Library</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """


def get_welcome_email_template(user):
    """Generate welcome email template for new users"""
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5010')
    
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .header {{ background: linear-gradient(135deg, #1a3c1a, #2d5a2d); padding: 30px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; }}
            .content {{ background: white; padding: 30px; border: 2px solid #1a3c1a; border-top: none; }}
            .info-box {{ background: #f0f9f0; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .footer {{ margin-top: 30px; color: #666; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to Nigerian Army E-Library</h1>
            </div>
            <div class="content">
                <h2 style="color: #1a3c1a;">Thank you for registering, {user.full_name or user.username}!</h2>
                
                <p>Your registration has been submitted successfully and is now pending administrator approval.</p>
                
                <div class="info-box">
                    <p><strong>Username:</strong> {user.username}</p>
                    <p><strong>Email:</strong> {user.email}</p>
                    <p><strong>Registration Date:</strong> {user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else 'N/A'}</p>
                    <p><strong>Status:</strong> Pending Approval</p>
                </div>
                
                <p>You will receive a notification once your account has been reviewed. This typically takes 1-2 business days.</p>
                
                <p>After approval, you'll need to login and complete your profile to activate your library card.</p>
                
                <p>If you have any questions, please contact the library administrator.</p>
                
                <div class="footer">
                    <p>© Nigerian Army E-Library</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


# ===================== HELPER FUNCTIONS =====================

def allowed_file(filename, allowed_set):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def validate_image(stream):
    """Validate image file"""
    header = stream.read(512)
    stream.seek(0)
    format = imghdr.what(None, header)
    if not format:
        return None
    return '.' + format if format != 'jpeg' else '.jpg'


def generate_library_card_number():
    """Generate a unique library card number"""
    prefix = "NAEL"
    timestamp = datetime.now().strftime("%y%m")
    random_part = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}-{timestamp}-{random_part}"


def generate_barcode():
    """Generate a unique barcode"""
    return ''.join(random.choices(string.digits + string.ascii_uppercase, k=12))


def get_user_download_stats(user_id):
    """Get download statistics for a user"""
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(weeks=1)
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


def generate_username_from_email(email):
    """Generate a username from email address"""
    username = email.split('@')[0]
    username = re.sub(r'[^a-zA-Z0-9_]', '', username)
    
    base_username = username
    counter = 1
    while User.query.filter_by(username=username).first():
        username = f"{base_username}{counter}"
        counter += 1
    
    return username


def send_validation_email(email, validation_url, name):
    """Send validation email"""
    try:
        print(f"\n=== VALIDATION EMAIL ===\nTo: {email}\nName: {name}\nLink: {validation_url}\n=====================\n")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# ===================== OAUTH HELPER FUNCTIONS =====================

def get_na_oauth_auth_url():
    """Generate the NA OAuth authorization URL"""
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    
    params = {
        'client_id': current_app.config['NA_OAUTH_CLIENT_ID'],
        'redirect_uri': url_for('auth.na_oauth_callback', _external=True),
        'response_type': 'code',
        'scope': current_app.config['NA_OAUTH_SCOPE'],
        'state': state
    }
    
    auth_url = current_app.config['NA_OAUTH_AUTHORIZATION_URL'] + '?' + urlencode(params)
    return auth_url


def exchange_code_for_token(code):
    """Exchange authorization code for access token"""
    token_url = current_app.config['NA_OAUTH_TOKEN_URL']
    
    # Basic authentication using client_id and client_secret
    credentials = f"{current_app.config['NA_OAUTH_CLIENT_ID']}:{current_app.config['NA_OAUTH_CLIENT_SECRET']}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': url_for('auth.na_oauth_callback', _external=True)
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        return token_data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error exchanging code for token: {e}")
        return None


def get_user_info_from_oauth(access_token):
    """Get user information from NA OAuth userinfo endpoint"""
    userinfo_url = current_app.config['NA_OAUTH_USERINFO_URL']
    
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.get(userinfo_url, headers=headers, timeout=10)
        response.raise_for_status()
        user_data = response.json()
        return user_data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting user info from OAuth: {e}")
        return None


# ===================== NA OAUTH ROUTES =====================

@auth_bp.route("/na-oauth-login")
def na_oauth_login():
    """Initiate NA OAuth login - redirects to NA authentication portal"""
    # Check if OAuth is configured
    if not current_app.config.get('NA_OAUTH_CONFIGURED', False):
        flash("NA OAuth is not configured yet. Please contact the administrator.", "error")
        return redirect(url_for('auth.login'))
    
    # Check if we have the required credentials
    if not current_app.config['NA_OAUTH_CLIENT_ID'] or current_app.config['NA_OAUTH_CLIENT_ID'] == 'your_actual_client_id_from_NA_IT':
        flash("NA OAuth credentials not configured. Please contact the administrator.", "error")
        return redirect(url_for('auth.login'))
    
    # Generate the authorization URL
    auth_url = get_na_oauth_auth_url()
    
    # Redirect to NA authentication portal
    return redirect(auth_url)


@auth_bp.route("/na-oauth-callback")
def na_oauth_callback():
    """Callback URL for NA OAuth - receives the authorization code"""
    # Verify state to prevent CSRF
    received_state = request.args.get('state')
    if not received_state or received_state != session.get('oauth_state'):
        flash("Invalid OAuth state. Possible CSRF attack.", "error")
        return redirect(url_for('auth.login'))
    
    # Check for error
    error = request.args.get('error')
    if error:
        error_description = request.args.get('error_description', 'No description provided')
        flash(f"OAuth error: {error} - {error_description}", "error")
        return redirect(url_for('auth.login'))
    
    # Get authorization code
    code = request.args.get('code')
    if not code:
        flash("No authorization code received.", "error")
        return redirect(url_for('auth.login'))
    
    # Exchange code for access token
    token_data = exchange_code_for_token(code)
    if not token_data:
        flash("Failed to exchange code for access token.", "error")
        return redirect(url_for('auth.login'))
    
    access_token = token_data.get('access_token')
    if not access_token:
        flash("No access token received.", "error")
        return redirect(url_for('auth.login'))
    
    # Get user information
    user_data = get_user_info_from_oauth(access_token)
    if not user_data:
        flash("Failed to get user information from NA portal.", "error")
        return redirect(url_for('auth.login'))
    
    # Extract user data (adjust field names based on NA OAuth response)
    email = user_data.get('email', '').lower().strip()
    full_name = user_data.get('name', user_data.get('full_name', ''))
    service_number = user_data.get('service_number', user_data.get('serviceNumber', ''))
    rank = user_data.get('rank', '')
    unit = user_data.get('unit', '')
    
    # Validate email
    if not email:
        flash("No email received from NA portal.", "error")
        return redirect(url_for('auth.login'))
    
    if not email.endswith('@army.mil.ng'):
        flash("Invalid military email.", "error")
        return redirect(url_for('auth.login'))
    
    # Check if user exists
    user = User.query.filter_by(email=email).first()
    
    if not user:
        # Auto-create account from OAuth data
        username = generate_username_from_email(email)
        
        # Generate name from email if not provided
        if not full_name:
            name_parts = email.split('@')[0].split('.')
            full_name = ' '.join([p.capitalize() for p in name_parts]) if name_parts else username
        
        user = User(
            username=username,
            email=email,
            password_hash=None,  # No password for OAuth users
            full_name=full_name,
            service_number=service_number if service_number else None,
            rank=rank if rank else None,
            unit=unit if unit else None,
            membership_status='active',
            approval_status='approved',
            security_clearance='confidential',
            requires_approval_for_restricted=False,
            profile_complete=False,
            email_verified=True,
            created_at=datetime.utcnow()
        )
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"New military account created via OAuth: {email}")
        flash("✅ Military account created! Please complete your profile.", "success")
    else:
        # Update existing user with latest info from NA portal
        if service_number and not user.service_number:
            user.service_number = service_number
        if rank and not user.rank:
            user.rank = rank
        if unit and not user.unit:
            user.unit = unit
        db.session.commit()
    
    # Check if user is approved
    if user.approval_status == 'pending':
        flash("⏳ Your account is pending administrator approval.", "info")
        return redirect(url_for('auth.login'))
    
    if user.approval_status == 'rejected':
        flash("❌ Your registration was rejected.", "error")
        return redirect(url_for('auth.login'))
    
    # Log the user in
    session["user_id"] = user.id
    session["username"] = user.username
    session["email"] = user.email
    session["role"] = user.role
    session["full_name"] = user.full_name
    session["is_military"] = True
    session["oauth_login"] = True
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    user.login_count = (user.login_count or 0) + 1
    db.session.commit()
    
    # Clear OAuth state
    session.pop('oauth_state', None)
    
    # Redirect based on profile completion
    if not user.profile_complete:
        flash("Please complete your profile to activate your library card.", "info")
        return redirect(url_for('auth.complete_profile'))
    
    # Redirect to home page after successful login
    return redirect(url_for('books.home'))


# ===================== LOGIN ROUTES =====================

@auth_bp.route("/login", methods=["GET"])
def login():
    """Render the login page"""
    return render_template("auth/login.html", now=datetime.utcnow())


@auth_bp.route("/login/authenticate", methods=["POST"])
def login_authenticate():
    """Handle login form submission for civilians"""
    login_input = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    
    # Determine if input is email or username
    user = None
    if '@' in login_input:
        # Check if it's a military email
        if login_input.endswith('@army.mil.ng'):
            # Military personnel should use OAuth
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": "Military personnel should use the 'Login with Nigerian Army' button."})
            flash("Military personnel should use the 'Login with Nigerian Army' button.")
            return redirect(url_for('auth.login'))
        
        # Civilian email login
        user = User.query.filter_by(email=login_input.lower()).first()
    else:
        # Username login
        user = User.query.filter_by(username=login_input).first()

    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "message": "Invalid username/email or password."})
        flash("Invalid username/email or password.")
        return redirect(url_for('auth.login'))

    # Check if user is military (should have used OAuth)
    if user.email and user.email.endswith('@army.mil.ng'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "message": "Military personnel should use the 'Login with Nigerian Army' button."})
        flash("Military personnel should use the 'Login with Nigerian Army' button.")
        return redirect(url_for('auth.login'))

    # Check approval status
    if user.approval_status == 'pending':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "message": "Your account is pending administrator approval."})
        flash("⏳ Your account is pending administrator approval.")
        return redirect(url_for('auth.login'))
    
    if user.approval_status == 'rejected':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "message": f"Your registration was rejected."})
        flash(f"❌ Your registration was rejected.")
        return redirect(url_for('auth.login'))
    
    # Check membership status
    if user.membership_status != 'active':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "message": f"Your account is {user.membership_status}."})
        flash(f"Your account is {user.membership_status}.")
        return redirect(url_for('auth.login'))
    
    # Set session
    session["user_id"] = user.id
    session["username"] = user.username
    session["email"] = user.email
    session["role"] = user.role
    session["full_name"] = user.full_name
    session["is_military"] = False
    session["oauth_login"] = False
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    user.login_count = (user.login_count or 0) + 1
    db.session.commit()
    
    # Redirect to home page after successful login
    redirect_url = url_for('books.home')
    
    # Handle AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            "success": True,
            "message": f"Welcome back, {user.full_name or user.username}!",
            "redirect": redirect_url,
            "role": user.role,
            "profile_complete": user.profile_complete
        })
    
    flash(f"Welcome back, {user.full_name or user.username}!")
    return redirect(redirect_url)


# ===================== LOGOUT =====================

@auth_bp.route("/logout")
def logout():
    session.clear()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"success": True, "message": "Logged out successfully.", "redirect": url_for('books.home')})
    
    flash("Logged out successfully.")
    return redirect(url_for("books.home"))


# ===================== CIVILIAN REGISTRATION =====================

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Civilian user registration with admin approval"""
    if request.method == "GET":
        return render_template("auth/register.html", now=datetime.utcnow(), timedelta=timedelta)
    
    # Handle POST
    email = request.form.get("email", "").lower().strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    full_name = request.form.get("full_name", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    
    logger.info(f"Civilian registration attempt - email: {email}, phone: {phone_number}")
    
    # Validate
    if not full_name:
        flash("Full name is required", "error")
        return redirect(url_for("auth.register"))
    
    # Validate civilian email (any valid email)
    is_valid_email, email_message = validate_civilian_email(email)
    if not is_valid_email:
        flash(email_message, "error")
        return redirect(url_for("auth.register"))
    
    # Prevent civilians from using military emails
    if email.endswith('@army.mil.ng'):
        flash("Military personnel should use the 'Login with Nigerian Army' button. This registration is for civilians only.", "error")
        return redirect(url_for("auth.register"))
    
    # Check if email already exists
    existing_user_by_email = User.query.filter_by(email=email).first()
    if existing_user_by_email:
        flash("❌ This email is already registered. Please login instead.", "error")
        return redirect(url_for("auth.login"))
    
    # Check if phone number already exists (if provided)
    if phone_number:
        existing_user_by_phone = User.query.filter_by(phone=phone_number).first()
        if existing_user_by_phone:
            flash("❌ This phone number is already registered. Please contact support if you need assistance.", "error")
            return redirect(url_for("auth.register"))
    
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.register"))
    
    # Validate password strength
    is_valid_password, password_message = validate_password_strength(password)
    if not is_valid_password:
        flash(password_message, "error")
        return redirect(url_for("auth.register"))
    
    # Create civilian user
    username = generate_username_from_email(email)
    
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        full_name=full_name,
        phone=phone_number,
        service_number=None,
        membership_status='pending',
        approval_status='pending',
        security_clearance='basic',
        requires_approval_for_restricted=True,
        profile_picture=None,
        profile_complete=False,
        address=None,
        rank=None,
        unit=None,
        created_at=datetime.utcnow(),
        email_verified=False
    )
    
    try:
        db.session.add(user)
        db.session.commit()
        
        # Send welcome email
        welcome_message = get_welcome_email_template(user)
        send_user_notification(user, "Registration Received - Pending Approval", welcome_message)
        
        # Notify admins
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            admin_message = f"New Civilian registration pending: {full_name} ({email})"
            send_user_notification(admin, f"New Civilian User: {username}", admin_message)
        
        # For AJAX request (if form is submitted via AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                "success": True,
                "message": "✅ Registration successful! Your account is pending approval. You will receive an email once approved.",
                "redirect": url_for('books.home')
            })
        
        # For regular form submission - redirect to home page
        flash("✅ Registration submitted successfully! An administrator will review your application.", "success")
        return redirect(url_for('books.home'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {e}")
        flash("❌ An error occurred during registration. Please try again.", "error")
        return redirect(url_for("auth.register"))

# ===================== NA REGISTRATION =====================

@auth_bp.route("/na-register", methods=["GET", "POST"])
def na_register():
    """NA Personnel registration with email validation"""
    if request.method == "GET":
        return render_template("auth/na_register.html", now=datetime.utcnow())
    
    # Handle POST
    email = request.form.get("email", "").lower().strip()
    full_name = request.form.get("full_name")
    service_number = request.form.get("service_number", "").upper().strip()
    rank = request.form.get("rank")
    unit = request.form.get("unit")
    phone = request.form.get("phone")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")
    
    # Validate
    if not full_name:
        flash("Full name is required", "error")
        return redirect(url_for('auth.na_register'))
    
    if not email.endswith('@army.mil.ng'):
        flash("❌ Please use a valid Nigerian Army email (@army.mil.ng)", "error")
        return redirect(url_for('auth.na_register'))
    
    if not re.match(r'^NA\/[0-9]{3}\/[0-9]{2}$', service_number):
        flash("❌ Invalid service number format. Use NA/xxx/xx", "error")
        return redirect(url_for('auth.na_register'))
    
    if password != confirm_password:
        flash("Passwords do not match", "error")
        return redirect(url_for('auth.na_register'))
    
    if len(password) < PASSWORD_MIN_LENGTH:
        flash(f"Password must be at least {PASSWORD_MIN_LENGTH} characters", "error")
        return redirect(url_for('auth.na_register'))
    
    if User.query.filter_by(email=email).first():
        flash("❌ Email already registered", "error")
        return redirect(url_for('auth.na_register'))
    
    if User.query.filter_by(service_number=service_number).first():
        flash("❌ Service number already registered", "error")
        return redirect(url_for('auth.na_register'))
    
    # Create user
    username = generate_username_from_email(email)
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        full_name=full_name,
        service_number=service_number,
        rank=rank,
        unit=unit,
        phone=phone,
        membership_status='pending',
        approval_status='approved',
        email_verified=False,
        security_clearance='confidential',
        requires_approval_for_restricted=True,
        profile_complete=False
    )
    
    db.session.add(user)
    db.session.commit()
    
    # Generate validation token
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = serializer.dumps(email, salt='email-validation')
    validation_url = url_for('auth.validate_email', token=token, _external=True)
    
    # Send email
    send_validation_email(email, validation_url, full_name)
    
    flash("✅ Registration successful! Please check your @army.mil.ng email to validate your account.", "success")
    return redirect(url_for('auth.login', tab='na'))


@auth_bp.route("/validate-email/<token>")
def validate_email(token):
    """Validate email address"""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    
    try:
        email = serializer.loads(token, salt='email-validation', max_age=86400)
    except SignatureExpired:
        flash("❌ Validation link has expired. Please request a new one.", "error")
        return redirect(url_for('auth.login', tab='na'))
    except BadSignature:
        flash("❌ Invalid validation link.", "error")
        return redirect(url_for('auth.login', tab='na'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("❌ User not found", "error")
        return redirect(url_for('auth.login', tab='na'))
    
    if user.email_verified:
        flash("✅ Email already verified. You can login now.", "success")
    else:
        user.email_verified = True
        user.membership_status = 'active'
        db.session.commit()
        flash("✅ Email validated successfully! You can now login.", "success")
    
    return redirect(url_for('auth.login', tab='na'))


@auth_bp.route("/resend-validation", methods=["POST"])
def resend_validation():
    """Resend validation email"""
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip() if data else ''
        
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'})
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'success': False, 'message': 'Email not found'})
        
        if user.email_verified:
            return jsonify({'success': False, 'message': 'Email already verified'})
        
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = serializer.dumps(email, salt='email-validation')
        validation_url = url_for('auth.validate_email', token=token, _external=True)
        
        send_validation_email(email, validation_url, user.full_name)
        return jsonify({'success': True, 'message': 'Validation email sent'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'})


# ===================== COMPLETE PROFILE =====================

@auth_bp.route("/complete-profile", methods=["GET", "POST"])
@login_required
def complete_profile():
    """Complete profile after admin approval - upload photo, add details, generate library card"""
    user = User.query.get_or_404(session['user_id'])
    
    # Check if user is approved
    if user.approval_status != 'approved':
        flash("Your account is not yet approved. Please wait for admin approval.")
        return redirect(url_for('auth.dashboard'))
    
    # Check if profile is already complete
    if user.profile_complete and user.library_card:
        flash("Your profile is already complete.")
        return redirect(url_for('auth.library_card'))
    
    if request.method == "POST":
        # Get form data
        address = request.form.get("address", "")
        rank = request.form.get("rank", "")
        unit = request.form.get("unit", "")
        date_of_birth = request.form.get("date_of_birth")
        if date_of_birth:
            try:
                date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
            except:
                date_of_birth = None
        
        # Handle service number for military personnel (OAuth users)
        service_number = request.form.get("service_number", "").upper().strip()
        if user.email.endswith('@army.mil.ng') and service_number:
            is_valid, message = validate_service_number(service_number)
            if not is_valid:
                flash(message)
                return redirect(url_for('auth.complete_profile'))
            if User.query.filter_by(service_number=service_number).first() and user.service_number != service_number:
                flash("Service number already registered.")
                return redirect(url_for('auth.complete_profile'))
            user.service_number = service_number
        
        # Handle profile picture upload
        profile_picture = user.profile_picture
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                if allowed_file(file.filename, current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})):
                    file_ext = validate_image(file.stream)
                    if file_ext:
                        # Delete old profile picture if exists
                        if user.profile_picture:
                            old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profiles', user.profile_picture)
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        
                        filename = f"profile_{user.id}_{uuid.uuid4().hex}{file_ext}"
                        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profiles', filename)
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        file.save(file_path)
                        profile_picture = filename
                else:
                    flash("Invalid image format. Allowed: PNG, JPG, JPEG, GIF")
                    return redirect(url_for('auth.complete_profile'))
        
        # For civilians, profile picture is recommended but not required
        # For military, profile picture is optional
        
        # Update user profile
        user.address = address
        if rank:
            user.rank = rank
        if unit:
            user.unit = unit
        user.date_of_birth = date_of_birth
        if profile_picture:
            user.profile_picture = profile_picture
        user.profile_complete = True
        
        # Generate library card if not exists
        if not user.library_card:
            library_card = LibraryCard(
                user_id=user.id,
                card_number=generate_library_card_number(),
                barcode=generate_barcode(),
                issued_date=datetime.now(),
                expiry_date=datetime.now() + timedelta(days=365),
                is_active=True,
                status='active'
            )
            db.session.add(library_card)
        
        db.session.commit()
        
        flash("✅ Profile completed successfully! Your library card has been generated.")
        return redirect(url_for('auth.library_card'))
    
    return render_template("auth/complete_profile.html", user=user)


# ===================== LIBRARY CARD =====================

@auth_bp.route("/library-card")
@login_required
def library_card():
    """View library card"""
    user = User.query.get(session['user_id'])
    
    if not user.library_card:
        if not user.profile_complete:
            flash("Please complete your profile to generate your library card.")
            return redirect(url_for("auth.complete_profile"))
        else:
            flash("Library card not found. Please contact administrator.")
            return redirect(url_for("auth.profile"))
    
    # Check if card is active
    if not user.library_card.is_active:
        flash("Your library card is inactive. Please contact the administrator.")
        return redirect(url_for("auth.profile"))
    
    return render_template("auth/library_card.html", 
                         user=user, 
                         card=user.library_card,
                         now=datetime.utcnow())


# ===================== DASHBOARD =====================

@auth_bp.route("/dashboard")
@login_required
def dashboard():
    """User dashboard with statistics and activity"""
    user = User.query.get_or_404(session['user_id'])
    
    # Check if profile is complete
    if not user.profile_complete:
        flash("Please complete your profile to access the dashboard.")
        return redirect(url_for('auth.complete_profile'))
    
    # Statistics
    reading_history_count = ReadingHistory.query.filter_by(user_id=user.id).count()
    wishlist_count = Wishlist.query.filter_by(user_id=user.id).count()
    reviews_count = Review.query.filter_by(user_id=user.id).count()
    total_downloads = DownloadLog.query.filter_by(user_id=user.id).count()
    
    # Current borrowings
    current_borrowings = BorrowRecord.query.filter_by(
        user_id=user.id, 
        status='borrowed'
    ).order_by(BorrowRecord.due_date).all()
    
    # Borrowing history
    borrowing_history = BorrowRecord.query.filter_by(
        user_id=user.id
    ).filter(BorrowRecord.status != 'borrowed').order_by(
        BorrowRecord.return_date.desc()
    ).limit(5).all()
    
    # Download stats with limits
    download_stats = get_user_download_stats(user.id)
    download_stats['max_per_day'] = current_app.config.get('MAX_DOWNLOADS_PER_DAY', 5)
    download_stats['max_per_week'] = current_app.config.get('MAX_DOWNLOADS_PER_WEEK', 20)
    download_stats['max_per_month'] = current_app.config.get('MAX_DOWNLOADS_PER_MONTH', 50)
    
    # Pending reservations
    pending_reservations = BookReservation.query.filter_by(
        user_id=user.id,
        status='pending'
    ).all()
    
    # Recent activity feed
    recent_activity = []
    
    # Recent downloads
    recent_downloads = DownloadLog.query.filter_by(user_id=user.id)\
        .order_by(DownloadLog.timestamp.desc()).limit(3).all()
    for dl in recent_downloads:
        recent_activity.append({
            'icon': 'download',
            'description': f'Downloaded "{dl.book.title}"',
            'time': dl.timestamp.strftime('%H:%M, %d %b'),
            'timestamp': dl.timestamp
        })
    
    # Recent reads
    recent_reads = ReadingHistory.query.filter_by(user_id=user.id)\
        .order_by(ReadingHistory.last_read.desc()).limit(3).all()
    for read in recent_reads:
        recent_activity.append({
            'icon': 'book-open',
            'description': f'Read "{read.book.title}"',
            'time': read.last_read.strftime('%H:%M, %d %b'),
            'timestamp': read.last_read
        })
    
    # Recent reviews
    recent_reviews = Review.query.filter_by(user_id=user.id)\
        .order_by(Review.created_at.desc()).limit(3).all()
    for review in recent_reviews:
        recent_activity.append({
            'icon': 'star',
            'description': f'Reviewed "{review.book.title}"',
            'time': review.created_at.strftime('%H:%M, %d %b'),
            'timestamp': review.created_at
        })
    
    # Recent wishlist additions
    recent_wishlist = Wishlist.query.filter_by(user_id=user.id)\
        .order_by(Wishlist.created_at.desc()).limit(3).all()
    for item in recent_wishlist:
        recent_activity.append({
            'icon': 'heart',
            'description': f'Added "{item.book.title}" to wishlist',
            'time': item.created_at.strftime('%H:%M, %d %b'),
            'timestamp': item.created_at
        })
    
    # Sort by timestamp (most recent first)
    recent_activity.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_activity = recent_activity[:8]
    
    # Wishlist items for preview
    wishlist_items = Wishlist.query.filter_by(user_id=user.id)\
        .order_by(Wishlist.created_at.desc()).limit(6).all()
    
    # Calculate total fines
    total_fines = sum(borrow.calculate_fine() for borrow in current_borrowings)
    
    # Check if library card is expiring soon (within 30 days)
    card_expiring_soon = False
    if user.library_card and user.library_card.expiry_date:
        days_to_expiry = (user.library_card.expiry_date - datetime.now()).days
        card_expiring_soon = days_to_expiry <= 30 and days_to_expiry > 0
    
    return render_template("auth/dashboard.html",
                         user=user,
                         reading_history=reading_history_count,
                         wishlist_count=wishlist_count,
                         reviews_count=reviews_count,
                         total_downloads=total_downloads,
                         current_borrowings=current_borrowings,
                         borrowing_history=borrowing_history,
                         download_stats=download_stats,
                         pending_reservations=pending_reservations,
                         recent_activity=recent_activity,
                         wishlist_items=wishlist_items,
                         total_fines=total_fines,
                         card_expiring_soon=card_expiring_soon,
                         now=datetime.utcnow())


# ===================== PROFILE MANAGEMENT =====================

@auth_bp.route("/profile")
@login_required
def profile():
    """User profile page"""
    user = User.query.get_or_404(session['user_id'])
    
    # Get user statistics
    reading_history_count = ReadingHistory.query.filter_by(user_id=user.id).count()
    wishlist_count = Wishlist.query.filter_by(user_id=user.id).count()
    reviews_count = Review.query.filter_by(user_id=user.id).count()
    downloads_count = DownloadLog.query.filter_by(user_id=user.id).count()
    
    # Get recent activity
    recent_downloads = DownloadLog.query.filter_by(user_id=user.id)\
        .order_by(DownloadLog.timestamp.desc()).limit(5).all()
    
    recent_reads = ReadingHistory.query.filter_by(user_id=user.id)\
        .order_by(ReadingHistory.last_read.desc()).limit(5).all()
    
    # Get approval info
    approver = None
    if user.approved_by_id:
        approver = User.query.get(user.approved_by_id)
    
    return render_template("auth/profile.html",
                         user=user,
                         reading_history=reading_history_count,
                         wishlist_count=wishlist_count,
                         reviews_count=reviews_count,
                         downloads_count=downloads_count,
                         recent_downloads=recent_downloads,
                         recent_reads=recent_reads,
                         approver=approver)


@auth_bp.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    """Edit user profile"""
    user = User.query.get_or_404(session['user_id'])
    
    if request.method == "POST":
        user.full_name = request.form.get("full_name", user.full_name)
        user.phone = request.form.get("phone_number", user.phone)
        user.address = request.form.get("address", user.address)
        user.rank = request.form.get("rank", user.rank)
        user.unit = request.form.get("unit", user.unit)
        
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                if allowed_file(file.filename, current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})):
                    file_ext = validate_image(file.stream)
                    if file_ext:
                        # Delete old profile picture if exists
                        if user.profile_picture:
                            old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profiles', user.profile_picture)
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        
                        filename = f"profile_{user.id}_{uuid.uuid4().hex}{file_ext}"
                        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profiles', filename)
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        file.save(file_path)
                        user.profile_picture = filename
        
        # Update email if changed and not taken
        new_email = request.form.get("email", "").lower().strip()
        if new_email and new_email != user.email:
            if new_email.endswith('@army.mil.ng'):
                # Military email - validate
                is_valid, message = validate_military_email(new_email)
                if not is_valid:
                    flash(message)
                    return redirect(url_for("auth.edit_profile"))
            else:
                # Civilian email
                is_valid, message = validate_civilian_email(new_email)
                if not is_valid:
                    flash(message)
                    return redirect(url_for("auth.edit_profile"))
            
            if User.query.filter_by(email=new_email).first():
                flash("Email already exists.")
                return redirect(url_for("auth.edit_profile"))
            user.email = new_email
        
        db.session.commit()
        flash("Profile updated successfully.")
        return redirect(url_for("auth.profile"))
    
    return render_template("auth/edit_profile.html", user=user)


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Change user password"""
    user = User.query.get_or_404(session['user_id'])
    
    # OAuth users (military) don't have passwords
    if not user.password_hash:
        flash("Your account uses military authentication. No password is required.")
        return redirect(url_for("auth.profile"))
    
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    if not check_password_hash(user.password_hash, current_password):
        flash("Current password is incorrect.")
        return redirect(url_for("auth.profile"))
    
    if new_password != confirm_password:
        flash("New passwords do not match.")
        return redirect(url_for("auth.profile"))
    
    # Validate new password strength
    is_valid, message = validate_password_strength(new_password)
    if not is_valid:
        flash(message)
        return redirect(url_for("auth.profile"))
    
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    
    flash("Password changed successfully.")
    return redirect(url_for("auth.profile"))


# ===================== HISTORY PAGES =====================

@auth_bp.route("/borrowing-history")
@login_required
@profile_complete_required
def borrowing_history():
    """View complete borrowing history"""
    user = User.query.get_or_404(session['user_id'])
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    borrowings = BorrowRecord.query.filter_by(user_id=user.id)\
        .order_by(BorrowRecord.borrow_date.desc())\
        .offset((page - 1) * per_page).limit(per_page).all()
    
    total = BorrowRecord.query.filter_by(user_id=user.id).count()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("auth/borrowing_history.html",
                         borrowings=borrowings,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@auth_bp.route("/download-history")
@login_required
@profile_complete_required
def download_history():
    """View complete download history"""
    user = User.query.get_or_404(session['user_id'])
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    downloads = DownloadLog.query.filter_by(user_id=user.id)\
        .order_by(DownloadLog.timestamp.desc())\
        .offset((page - 1) * per_page).limit(per_page).all()
    
    total = DownloadLog.query.filter_by(user_id=user.id).count()
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("auth/download_history.html",
                         downloads=downloads,
                         page=page,
                         total_pages=total_pages,
                         total=total)


# ===================== API ENDPOINTS =====================

@auth_bp.route("/api/user/stats")
@login_required
def api_user_stats():
    """API endpoint for user statistics"""
    user = User.query.get(session['user_id'])
    
    return jsonify({
        'reading_history': ReadingHistory.query.filter_by(user_id=user.id).count(),
        'wishlist': Wishlist.query.filter_by(user_id=user.id).count(),
        'reviews': Review.query.filter_by(user_id=user.id).count(),
        'downloads': DownloadLog.query.filter_by(user_id=user.id).count(),
        'current_borrowings': BorrowRecord.query.filter_by(user_id=user.id, status='borrowed').count(),
        'total_fines': sum(b.calculate_fine() for b in BorrowRecord.query.filter_by(user_id=user.id, status='borrowed').all())
    })


@auth_bp.route("/api/user/download-stats")
@login_required
def api_download_stats():
    """API endpoint for download statistics"""
    user = User.query.get(session['user_id'])
    
    if user.role == 'admin':
        return jsonify({'role': 'admin', 'unlimited': True})
    
    stats = get_user_download_stats(user.id)
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


# ===================== CLEARANCE & SECURITY =====================

@auth_bp.route("/security-clearance")
@login_required
@profile_complete_required
def security_clearance():
    """View security clearance information"""
    user = User.query.get_or_404(session['user_id'])
    
    # Get user's clearance level and permissions
    clearance_levels = ['basic', 'confidential', 'secret', 'top_secret']
    current_level_index = clearance_levels.index(user.security_clearance) if user.security_clearance and user.security_clearance in clearance_levels else 0
    
    # Get number of restricted books user has accessed
    restricted_access_count = DownloadLog.query.join(
        Book, DownloadLog.book_id == Book.id
    ).filter(
        DownloadLog.user_id == user.id,
        Book.requires_special_request == True
    ).count()
    
    # Get pending special requests
    pending_requests = SpecialRequest.query.filter_by(
        user_id=user.id,
        status='pending'
    ).count() if 'SpecialRequest' in dir() else 0
    
    return render_template("auth/security_clearance.html",
                         user=user,
                         clearance_levels=clearance_levels,
                         current_level_index=current_level_index,
                         restricted_access_count=restricted_access_count,
                         pending_requests=pending_requests)


# ===================== FORGOT PASSWORD =====================

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Handle forgot password requests"""
    if request.method == "GET":
        return render_template("auth/forgot_password.html", now=datetime.utcnow())
    
    email = request.form.get("email", "").lower().strip()
    
    if not email:
        flash("Email is required", "error")
        return redirect(url_for('auth.forgot_password'))
    
    user = User.query.filter_by(email=email).first()
    
    # Check if user is military (OAuth users can't reset password)
    if user and user.email and user.email.endswith('@army.mil.ng'):
        flash("Military personnel login with Nigerian Army credentials. Please use the 'Login with Nigerian Army' button.", "info")
        return redirect(url_for('auth.login'))
    
    if user and user.password_hash:
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = serializer.dumps(email, salt='password-reset')
        reset_url = url_for('auth.reset_password', token=token, _external=True)
        
        subject = "Password Reset Request"
        message = f"""
        You requested a password reset for your Nigerian Army E-Library account.
        
        Please click the following link to reset your password:
        {reset_url}
        
        This link will expire in 1 hour.
        
        If you did not request this, please ignore this email.
        """
        send_user_notification(user, subject, message)
        logger.info(f"Password reset requested for {email}")
    
    flash("If an account exists with this email, you will receive password reset instructions.", "info")
    return redirect(url_for('auth.login'))


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Reset password using token"""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    
    try:
        email = serializer.loads(token, salt='password-reset', max_age=3600)
    except SignatureExpired:
        flash('The password reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Invalid password reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    user = User.query.filter_by(email=email).first()
    
    # Check if user is military (OAuth users can't reset password)
    if user and user.email and user.email.endswith('@army.mil.ng'):
        flash("Military personnel login with Nigerian Army credentials. Please use the 'Login with Nigerian Army' button.", "info")
        return redirect(url_for('auth.login'))
    
    if request.method == "POST":
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template("auth/reset_password.html", token=token, now=datetime.utcnow())
        
        is_valid, message = validate_password_strength(password)
        if not is_valid:
            flash(message, 'error')
            return render_template("auth/reset_password.html", token=token, now=datetime.utcnow())
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.login'))
        
        user.password_hash = generate_password_hash(password)
        user.last_password_change = datetime.utcnow()
        
        if hasattr(user, 'failed_login_attempts'):
            user.failed_login_attempts = 0
        if hasattr(user, 'locked_until'):
            user.locked_until = None
        
        db.session.commit()
        
        subject = "Password Changed Successfully"
        message = "Your password has been changed successfully."
        send_user_notification(user, subject, message)
        
        flash('Password reset successful! Please login with your new password.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template("auth/reset_password.html", token=token, now=datetime.utcnow())


# ===================== RESEND VERIFICATION =====================

@auth_bp.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    """Resend email verification"""
    user = User.query.get(session['user_id'])
    
    if user.email_verified:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Email already verified'})
        flash('Email already verified', 'info')
        return redirect(url_for('auth.profile'))
    
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = serializer.dumps(user.email, salt='email-verification')
    verify_url = url_for('auth.verify_email', token=token, _external=True)
    
    subject = "Verify Your Email Address"
    message = f"""
    Please click the following link to verify your email address:
    {verify_url}
    
    This link will expire in 24 hours.
    """
    send_user_notification(user, subject, message)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Verification email sent'})
    
    flash('Verification email sent', 'success')
    return redirect(url_for('auth.profile'))


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    """Verify email address"""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    
    try:
        email = serializer.loads(token, salt='email-verification', max_age=86400)
    except SignatureExpired:
        flash('The verification link has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.login'))
    except BadSignature:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('auth.login'))
    
    if user.email_verified:
        flash('Email already verified', 'info')
    else:
        user.email_verified = True
        user.email_verified_at = datetime.utcnow()
        db.session.commit()
        flash('Email verified successfully!', 'success')
    
    return redirect(url_for('auth.login'))


# ===================== ADMIN REGISTRATION =====================

@auth_bp.route("/register/admin", methods=["GET", "POST"])
def register_admin():
    """Secure admin registration route - hidden from public"""
    if not current_app.config.get('ADMIN_REGISTRATION_ENABLED', False):
        abort(404)
    
    if request.method == "GET":
        return render_template("admin/register_admin.html", now=datetime.utcnow())
    
    # Handle POST
    secret_key = request.form.get('secret_key')
    admin_code = request.form.get('admin_code')
    full_name = request.form.get('full_name')
    email = request.form.get('email', '').lower().strip()
    phone = request.form.get('phone_number')
    password = request.form.get('password')
    
    if secret_key != current_app.config.get('ADMIN_SECRET_KEY'):
        flash('❌ Invalid registration key', 'danger')
        return redirect(url_for('auth.register_admin'))
    
    if admin_code != current_app.config.get('ADMIN_CODE'):
        flash('❌ Invalid admin code', 'danger')
        return redirect(url_for('auth.register_admin'))
    
    is_valid_email, email_message = validate_military_email(email)
    if not is_valid_email:
        flash(email_message, 'danger')
        return redirect(url_for('auth.register_admin'))
    
    if User.query.filter_by(email=email).first():
        flash('❌ Email already exists', 'danger')
        return redirect(url_for('auth.register_admin'))
    
    username = generate_username_from_email(email)
    
    is_valid_password, password_message = validate_password_strength(password)
    if not is_valid_password:
        flash(password_message, 'danger')
        return redirect(url_for('auth.register_admin'))
    
    admin = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role='admin',
        full_name=full_name,
        phone=phone,
        membership_status='active',
        approval_status='approved',
        approved_at=datetime.utcnow(),
        security_clearance='top_secret',
        requires_approval_for_restricted=False,
        profile_complete=True
    )
    
    try:
        db.session.add(admin)
        db.session.flush()
        
        library_card = LibraryCard(
            user_id=admin.id,
            card_number=generate_library_card_number(),
            barcode=generate_barcode(),
            issued_date=datetime.now(),
            expiry_date=datetime.now() + timedelta(days=3*365),
            is_active=True,
            status='active'
        )
        db.session.add(library_card)
        db.session.commit()
        
        logger.info(f"New admin account created: {username}")
        
        subject = "Welcome Administrator!"
        message = f"Your administrator account has been created successfully."
        send_user_notification(admin, subject, message)
        
        flash('✅ Admin account created successfully! You can now login.', 'success')
        return redirect(url_for('auth.login'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating admin: {e}")
        flash('❌ An error occurred. Please try again.', 'danger')
        return redirect(url_for('auth.register_admin'))


# ===================== DEBUG ENDPOINT =====================

@auth_bp.route("/debug-oauth-config")
@admin_required
def debug_oauth_config():
    """Debug endpoint to check OAuth configuration (admin only)"""
    config_status = {
        'client_id_configured': bool(current_app.config.get('NA_OAUTH_CLIENT_ID')) and current_app.config['NA_OAUTH_CLIENT_ID'] != 'your_actual_client_id_from_NA_IT',
        'client_secret_configured': bool(current_app.config.get('NA_OAUTH_CLIENT_SECRET')),
        'authorization_url': current_app.config.get('NA_OAUTH_AUTHORIZATION_URL'),
        'token_url': current_app.config.get('NA_OAUTH_TOKEN_URL'),
        'userinfo_url': current_app.config.get('NA_OAUTH_USERINFO_URL'),
        'scope': current_app.config.get('NA_OAUTH_SCOPE'),
        'oauth_configured': current_app.config.get('NA_OAUTH_CONFIGURED', False)
    }
    return jsonify(config_status)