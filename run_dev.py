#!/usr/bin/env python3
"""
Development runner for Nigerian Army E-Library
"""
import os
import sys

# Get absolute path to the database
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'library.db')

# Force development mode
os.environ['FLASK_CONFIG'] = 'development'
os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

print("="*60)
print("🚀 Starting Nigerian Army E-Library (Development Mode)")
print("="*60)
print(f"📋 FLASK_CONFIG: {os.environ.get('FLASK_CONFIG')}")
print(f"📋 DATABASE_URL: {os.environ.get('DATABASE_URL')}")
print(f"📁 Database file: {db_path}")
print(f"📁 Database exists: {os.path.exists(db_path)}")
print("-"*60)

try:
    # Import the app
    print("📦 Importing app...")
    from app import app
    print("✅ App imported successfully")
    
    # Get port
    port = int(os.environ.get('PORT', 5010))
    
    print(f"\n🌐 Server running at: http://localhost:{port}")
    print(f"🔧 Debug mode: {app.debug}")
    print(f"💾 Database: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')}")
    print("="*60 + "\n")
    
    # Run the app
    app.run(debug=True, host='0.0.0.0', port=port)
    
except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    print("\nPlease install required packages:")
    print("pip install flask flask-sqlalchemy flask-login python-dotenv")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)