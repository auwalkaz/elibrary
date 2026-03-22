# utils/whatsapp_notifier.py
import os
from flask import current_app
from twilio.rest import Client
import logging

logger = logging.getLogger(__name__)

def send_whatsapp_notification(phone_number, message):
    """
    Send WhatsApp notification using Twilio
    
    Args:
        phone_number: Recipient's phone number (e.g., +2348012345678)
        message: Message text to send
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    if not current_app.config.get('WHATSAPP_CONFIGURED', False):
        logger.info("WhatsApp not configured - skipping notification")
        return False
    
    if not phone_number:
        logger.warning("No phone number provided for WhatsApp notification")
        return False
    
    try:
        # Format phone number
        phone_number = format_phone_number(phone_number)
        
        # Initialize Twilio client
        client = Client(
            current_app.config['TWILIO_ACCOUNT_SID'],
            current_app.config['TWILIO_AUTH_TOKEN']
        )
        
        # Send message
        message = client.messages.create(
            body=message,
            from_=current_app.config['TWILIO_WHATSAPP_NUMBER'],
            to=f'whatsapp:{phone_number}'
        )
        
        logger.info(f"WhatsApp message sent! SID: {message.sid} to {phone_number}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {e}")
        return False


def format_phone_number(phone):
    """
    Format phone number to international format
    Examples:
        08012345678 -> +2348012345678
        8012345678 -> +2348012345678
        +2348012345678 -> +2348012345678
    """
    if not phone:
        return None
    
    # Remove any spaces or special characters
    phone = ''.join(filter(str.isdigit, phone))
    
    # Nigerian numbers
    if phone.startswith('0') and len(phone) == 11:
        # 08012345678 -> 2348012345678
        phone = '234' + phone[1:]
    elif len(phone) == 10 and not phone.startswith('0'):
        # 8012345678 -> 2348012345678
        phone = '234' + phone
    elif phone.startswith('234') and len(phone) == 13:
        # Already in international format
        pass
    else:
        # Assume it's already formatted correctly
        if not phone.startswith('+'):
            phone = '+' + phone
    
    # Ensure it starts with +
    if not phone.startswith('+'):
        phone = '+' + phone
    
    return phone


def send_approval_notification(user, reason=None):
    """Send approval notification via WhatsApp"""
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5010')
    login_url = f"{base_url}/auth/login"
    
    message = f"""
🎉 *Nigerian Army E-Library - Registration Approved!*

Hello *{user.full_name or user.username}*! 👋

Your library registration has been APPROVED! ✅

📚 *Your Account Details:*
• Username: {user.username}
• Email: {user.email}

🔐 *Next Steps:*
1. Login to complete your profile: {login_url}
2. Upload your profile picture
3. Your library card will be generated automatically

Need help? Contact our support team.

Thank you for joining Nigerian Army E-Library! 📖
    """
    
    return send_whatsapp_notification(user.phone, message)


def send_rejection_notification(user, reason):
    """Send rejection notification via WhatsApp"""
    message = f"""
❌ *Nigerian Army E-Library - Registration Update*

Hello *{user.full_name or user.username}*,

Your registration has been REJECTED. ❌

*Reason:* {reason or 'Not specified'}

If you believe this is an error, please contact support.

Thank you.
    """
    
    return send_whatsapp_notification(user.phone, message)


def send_welcome_notification(user):
    """Send welcome notification via WhatsApp"""
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5010')
    
    message = f"""
📚 *Welcome to Nigerian Army E-Library!* 🇳🇬

Hello *{user.full_name or user.username}*! Your registration has been submitted successfully.

⏳ *Status:* Pending Approval

You will receive a WhatsApp notification once your account is approved. This typically takes 1-2 business days.

After approval, you'll need to:
1. Login to complete your profile: {base_url}/auth/login
2. Generate your library card

Thank you for joining our community!
    """
    
    return send_whatsapp_notification(user.phone, message)


def send_library_card_notification(user):
    """Send library card notification via WhatsApp"""
    if not user.library_card:
        return False
    
    message = f"""
🎫 *Your Library Card is Ready!*

Hello *{user.full_name or user.username}*,

Your Nigerian Army E-Library card has been generated!

🆔 *Card Number:* {user.library_card.card_number}
📅 *Expiry Date:* {user.library_card.expiry_date.strftime('%Y-%m-%d')}
🔢 *Barcode:* {user.library_card.barcode}

You can now borrow books and access all library resources!

Happy reading! 📚
    """
    
    return send_whatsapp_notification(user.phone, message)


def send_admin_notification(admin, message):
    """Send notification to admin via WhatsApp"""
    return send_whatsapp_notification(admin.phone, message)