#!/usr/bin/env python
import os
import sys
from app import create_app, db

def init_database():
    print("Initializing database...")
    app = create_app('production')
    with app.app_context():
        # Check if tables exist
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if not tables:
            print("Creating all tables...")
            db.create_all()
            print("✓ Database tables created successfully!")
        else:
            print(f"Tables already exist: {', '.join(tables)}")

if __name__ == "__main__":
    init_database()