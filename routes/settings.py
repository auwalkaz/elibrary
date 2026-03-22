from flask import Blueprint, jsonify

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
def index():
    return jsonify({'message': 'settings blueprint is working'})