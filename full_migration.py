# add_columns.py
from app import app, db
from models import User
import sqlite3

def add_columns():
    """Add new columns to users table"""
    conn = sqlite3.connect('/home/auwalkz/elibrary1/library.db')
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    new_columns = {
        'office_phone': 'VARCHAR(20)',
        'address': 'TEXT',
        'city': 'VARCHAR(100)',
        'office_address': 'TEXT',
        'gender': 'VARCHAR(10)',
        'nationality': 'VARCHAR(50)',
        'date_of_birth': 'DATE',
        'occupation': 'VARCHAR(100)'
    }
    
    for col_name, col_type in new_columns.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                print(f"✅ Added column: {col_name}")
            except Exception as e:
                print(f"❌ Error adding {col_name}: {e}")
        else:
            print(f"⏭️ Column already exists: {col_name}")
    
    conn.commit()
    conn.close()
    print("\n✅ Migration completed!")

if __name__ == "__main__":
    add_columns()