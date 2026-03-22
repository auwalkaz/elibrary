#!/usr/bin/env python3
# scripts/add_special_request_fields.py
import sqlite3
import os

def add_special_request_fields():
    """Add special request fields to existing tables"""
    
    print("=" * 60)
    print("🔐 ADDING SPECIAL REQUEST FIELDS")
    print("=" * 60)
    
    db_path = 'instance/elibrary.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Add fields to books table
    print("\n📚 Updating books table...")
    book_columns = [
        ('requires_special_request', 'BOOLEAN DEFAULT 0'),
        ('special_request_notes', 'TEXT'),
        ('security_classification', 'VARCHAR(50)'),
        ('approved_roles', 'VARCHAR(200)')
    ]
    
    cursor.execute("PRAGMA table_info(books)")
    existing = [col[1] for col in cursor.fetchall()]
    
    for col_name, col_type in book_columns:
        if col_name not in existing:
            print(f"  ➕ Adding {col_name} to books...")
            cursor.execute(f"ALTER TABLE books ADD COLUMN {col_name} {col_type}")
    
    # Add fields to users table
    print("\n👤 Updating users table...")
    user_columns = [
        ('security_clearance', "VARCHAR(50) DEFAULT 'basic'"),
        ('requires_approval_for_restricted', 'BOOLEAN DEFAULT 1')
    ]
    
    cursor.execute("PRAGMA table_info(users)")
    existing = [col[1] for col in cursor.fetchall()]
    
    for col_name, col_type in user_columns:
        if col_name not in existing:
            print(f"  ➕ Adding {col_name} to users...")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
    
    # Create special_requests table
    print("\n📋 Creating special_requests table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS special_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            request_type VARCHAR(20) NOT NULL,
            reason TEXT NOT NULL,
            additional_notes TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            reviewed_by INTEGER,
            reviewed_at TIMESTAMP,
            review_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (book_id) REFERENCES books (id),
            FOREIGN KEY (reviewed_by) REFERENCES users (id)
        )
    ''')
    print("  ✅ Created special_requests table")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅✅✅ SPECIAL REQUEST FIELDS ADDED! ✅✅✅")
    print("=" * 60)

if __name__ == '__main__':
    add_special_request_fields()