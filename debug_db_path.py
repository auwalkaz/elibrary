# test_home_query.py
from app import app, db
from models import Book
import traceback

def test_home_query():
    with app.app_context():
        print("=" * 50)
        print("TESTING HOME PAGE QUERY")
        print("=" * 50)
        
        # Test 1: Simple count
        try:
            total = Book.query.count()
            print(f"✅ Total books: {total}")
        except Exception as e:
            print(f"❌ Error counting books: {e}")
            traceback.print_exc()
        
        # Test 2: Featured books
        try:
            featured = Book.query.filter_by(is_featured=True).count()
            print(f"✅ Featured books: {featured}")
        except Exception as e:
            print(f"❌ Error counting featured books: {e}")
            traceback.print_exc()
        
        # Test 3: The exact home page query
        try:
            print("\n🔍 Running exact home page query...")
            featured_books = Book.query.filter_by(is_featured=True).order_by(Book.created_at.desc()).limit(6).all()
            print(f"✅ Found {len(featured_books)} featured books for home page")
            
            for book in featured_books:
                print(f"   - {book.title} (ID: {book.id}, Featured: {book.is_featured})")
                
        except Exception as e:
            print(f"❌ Error in home page query: {e}")
            traceback.print_exc()
        
        # Test 4: Check created_at column
        try:
            print("\n🔍 Checking created_at column...")
            book = Book.query.first()
            if book:
                print(f"✅ created_at exists: {book.created_at}")
                print(f"   Type: {type(book.created_at)}")
            else:
                print("⚠️ No books found to check created_at")
        except Exception as e:
            print(f"❌ Error accessing created_at: {e}")
            traceback.print_exc()
        
        # Test 5: Raw SQL query
        try:
            print("\n🔍 Testing raw SQL query...")
            result = db.session.execute("SELECT id, title, is_featured FROM books LIMIT 5")
            rows = result.fetchall()
            print(f"✅ Raw SQL found {len(rows)} books")
            for row in rows:
                print(f"   - {row[1]} (Featured: {row[2]})")
        except Exception as e:
            print(f"❌ Error in raw SQL: {e}")
            traceback.print_exc()
        
        print("\n" + "=" * 50)

if __name__ == "__main__":
    test_home_query()