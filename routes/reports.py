from flask import Blueprint, jsonify

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
def index():
    return jsonify({'message': 'reports blueprint is working'})