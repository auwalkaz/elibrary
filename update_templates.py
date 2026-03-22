#!/usr/bin/env python3
"""
Template Update Script
This script updates all Flask template files to use the correct blueprint endpoint names.
Run this after restructuring your routes into blueprints.
"""

import os
import re
import sys

def update_template_file(filepath):
    """Update a single template file with new url_for patterns"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Define replacements (pattern, replacement)
        replacements = [
            # Auth routes
            (r"url_for\(\s*'home'\s*\)", "url_for('books.home')"),
            (r"url_for\(\s*'index'\s*\)", "url_for('books.home')"),
            (r"url_for\(\s*'login'\s*\)", "url_for('auth.login')"),
            (r"url_for\(\s*'register'\s*\)", "url_for('auth.register')"),
            (r"url_for\(\s*'logout'\s*\)", "url_for('auth.logout')"),
            (r"url_for\(\s*'profile'\s*\)", "url_for('auth.profile')"),
            (r"url_for\(\s*'library-card'\s*\)", "url_for('auth.library_card')"),
            
            # Book routes
            (r"url_for\(\s*'read',\s*book_id=(\w+)\s*\)", r"url_for('books.read', book_id=\1)"),
            (r"url_for\(\s*'download',\s*filename=(\w+)\s*\)", r"url_for('books.download', filename=\1)"),
            (r"url_for\(\s*'wishlist'\s*\)", "url_for('books.view_wishlist')"),
            (r"url_for\(\s*'add_to_wishlist',\s*book_id=(\w+)\s*\)", r"url_for('books.add_to_wishlist', book_id=\1)"),
            (r"url_for\(\s*'remove_from_wishlist',\s*book_id=(\w+)\s*\)", r"url_for('books.remove_from_wishlist', book_id=\1)"),
            (r"url_for\(\s*'toggle_wishlist',\s*book_id=(\w+)\s*\)", r"url_for('books.toggle_wishlist', book_id=\1)"),
            
            # Admin routes
            (r"url_for\(\s*'upload'\s*\)", "url_for('admin.upload')"),
            (r"url_for\(\s*'admin.dashboard'\s*\)", "url_for('admin.dashboard')"),
            (r"url_for\(\s*'admin.manage_users'\s*\)", "url_for('admin.manage_users')"),
            (r"url_for\(\s*'admin.manage_books'\s*\)", "url_for('admin.manage_books')"),
            (r"url_for\(\s*'admin.manage_borrowings'\s*\)", "url_for('admin.manage_borrowings')"),
            (r"url_for\(\s*'uploaded_file',\s*filename=(\w+)\s*\)", r"url_for('admin.uploaded_file', filename=\1)"),
            
            # Borrow routes
            (r"url_for\(\s*'my-borrowings'\s*\)", "url_for('borrow.my_borrowings')"),
            (r"url_for\(\s*'borrow_book',\s*book_id=(\w+)\s*\)", r"url_for('borrow.borrow_book', book_id=\1)"),
            (r"url_for\(\s*'return_book',\s*borrow_id=(\w+)\s*\)", r"url_for('borrow.return_book', borrow_id=\1)"),
            (r"url_for\(\s*'reserve_book',\s*book_id=(\w+)\s*\)", r"url_for('borrow.reserve_book', book_id=\1)"),
            
            # API routes
            (r"url_for\(\s*'api.search_suggestions'\s*\)", "url_for('api.search_suggestions')"),
            (r"url_for\(\s*'api.book_status',\s*book_id=(\w+)\s*\)", r"url_for('api.book_status', book_id=\1)"),
        ]
        
        # Apply replacements
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
        
        # Check if content changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Updated: {filepath}")
            return True
        else:
            print(f"⏭️  No changes: {filepath}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating {filepath}: {e}")
        return False


def create_backup(filepath):
    """Create a backup of the original file"""
    backup_path = filepath + '.bak'
    try:
        with open(filepath, 'r', encoding='utf-8') as source:
            with open(backup_path, 'w', encoding='utf-8') as target:
                target.write(source.read())
        print(f"💾 Backup created: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Error creating backup for {filepath}: {e}")
        return False


def main():
    """Main function to update all templates"""
    print("=" * 60)
    print("🔧 Template Update Script")
    print("=" * 60)
    
    # Get templates directory
    templates_dir = 'templates'
    if not os.path.exists(templates_dir):
        print(f"❌ Templates directory '{templates_dir}' not found!")
        sys.exit(1)
    
    # Ask for confirmation
    print(f"\n📁 Found templates directory: {os.path.abspath(templates_dir)}")
    response = input("\nDo you want to create backups before updating? (y/n): ").lower()
    create_backups = response == 'y'
    
    # Find all HTML files
    html_files = []
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                html_files.append(os.path.join(root, file))
    
    print(f"\n📄 Found {len(html_files)} template files to process")
    
    if create_backups:
        print("💾 Creating backups...")
        for filepath in html_files:
            create_backup(filepath)
    
    print("\n🔄 Updating templates...")
    updated_count = 0
    for filepath in html_files:
        if update_template_file(filepath):
            updated_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ Update complete! {updated_count} of {len(html_files)} files were updated.")
    print("=" * 60)
    
    if create_backups:
        print("\n💡 Backup files (.bak) were created in the same directory.")
    print("\n📝 Next steps:")
    print("   1. Review the changes made to your templates")
    print("   2. Test your application to ensure all links work")
    print("   3. If something broke, restore from .bak files")


if __name__ == "__main__":
    main()