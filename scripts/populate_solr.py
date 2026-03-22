#!/usr/bin/env python
# scripts/populate_solr.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models import Book
from services.solr_client import solr_client

def main():
    app = create_app()
    with app.app_context():
        print("📚 Starting Solr population...")
        
        # Clear existing index
        print("🗑️  Clearing existing index...")
        solr_client.delete_all()
        
        # Get all books
        books = Book.query.all()
        print(f"📖 Found {len(books)} books to index")
        
        # Index each book
        success_count = 0
        for i, book in enumerate(books, 1):
            if solr_client.index_book(book):
                success_count += 1
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(books)}")
        
        print(f"✅ Done! Indexed {success_count}/{len(books)} books")

if __name__ == '__main__':
    main()