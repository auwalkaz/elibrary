cat > test_db.py << 'EOF'
import sqlite3

conn = sqlite3.connect('library.db')
cursor = conn.cursor()

# Check if books table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='books'")
if cursor.fetchone():
    print("✅ books table exists")
    
    # Count books
    cursor.execute("SELECT COUNT(*) FROM books")
    count = cursor.fetchone()[0]
    print(f"📚 Total books: {count}")
    
    # Show column names
    cursor.execute("PRAGMA table_info(books)")
    columns = cursor.fetchall()
    print(f"\n📋 Books table columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
else:
    print("❌ books table does not exist")

conn.close()
EOF