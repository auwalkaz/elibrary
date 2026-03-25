# init_db.py
import os
import sys
from app import create_app, db
from sqlalchemy import inspect

print("=" * 50)
print("Initializing Database...")
print("=" * 50)

app = create_app(os.getenv('FLASK_CONFIG') or 'production')

with app.app_context():
    try:
        # Create all tables
        print("Creating database tables...")
        db.create_all()
        print("✓ Tables created successfully!")
        
        # Check if admin user exists
        from models import User, LibraryCard
        
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("Creating admin user...")
            admin = User(
                username='admin',
                email='admin@library.gov.ng',
                full_name='System Administrator',
                role='admin',
                approval_status='approved',
                membership_status='active',
                security_clearance='top_secret'
            )
            admin.set_password('Admin@123')
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
            print("✓ Admin user created!")
        else:
            print("✓ Admin user already exists")
        
        print("=" * 50)
        print("Database initialization complete!")
        print("=" * 50)
        
    except Exception as e:
        print(f"Error during initialization: {e}")
        db.session.rollback()
        sys.exit(1)