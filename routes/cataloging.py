from flask import Blueprint, jsonify

cataloging_bp = Blueprint('cataloging', __name__, url_prefix='/cataloging')

@cataloging_bp.route('/')
def index():
    return jsonify({'message': 'cataloging blueprint is working'})