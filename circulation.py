# Create circulation.py in the routes directory
cat > routes/circulation.py << 'EOF'
from flask import Blueprint, jsonify

circulation_bp = Blueprint('circulation', __name__, url_prefix='/circulation')

@circulation_bp.route('/')
def index():
    return jsonify({'message': 'circulation blueprint is working'})
EOF

# Create acquisition.py
cat > routes/acquisition.py << 'EOF'
from flask import Blueprint, jsonify

acquisition_bp = Blueprint('acquisition', __name__, url_prefix='/acquisition')

@acquisition_bp.route('/')
def index():
    return jsonify({'message': 'acquisition blueprint is working'})
EOF

# Create cataloging.py
cat > routes/cataloging.py << 'EOF'
from flask import Blueprint, jsonify

cataloging_bp = Blueprint('cataloging', __name__, url_prefix='/cataloging')

@cataloging_bp.route('/')
def index():
    return jsonify({'message': 'cataloging blueprint is working'})
EOF

# Create reports.py
cat > routes/reports.py << 'EOF'
from flask import Blueprint, jsonify

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
def index():
    return jsonify({'message': 'reports blueprint is working'})
EOF

# Create settings.py
cat > routes/settings.py << 'EOF'
from flask import Blueprint, jsonify

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
def index():
    return jsonify({'message': 'settings blueprint is working'})
EOF

# Create notifications.py
cat > routes/notifications.py << 'EOF'
from flask import Blueprint, jsonify

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

@notifications_bp.route('/')
def index():
    return jsonify({'message': 'notifications blueprint is working'})
EOF