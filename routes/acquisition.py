from flask import Blueprint, jsonify

acquisition_bp = Blueprint('acquisition', __name__, url_prefix='/acquisition')

@acquisition_bp.route('/')
def index():
    return jsonify({'message': 'acquisition blueprint is working'})