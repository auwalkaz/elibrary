from flask import Blueprint, jsonify

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

@notifications_bp.route('/')
def index():
    return jsonify({'message': 'notifications blueprint is working'})