from app import app, db
import os

with app.app_context():
    # Print database location
    db_path = app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')
    print(f"Database URI: {db_path}")
    
    # Check if database file exists
    if 'sqlite' in db_path:
        db_file = db_path.replace('sqlite:///', '')
        print(f"Database file: {db_file}")
        print(f"File exists: {os.path.exists(db_file)}")
    
    # Try to create tables
    print("\nCreating tables...")
    db.create_all()
    print("Tables created successfully!")
    
    # List tables
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"\nTables in database: {tables}")
    
    # Count records in each table
    for table in tables:
        try:
            result = db.session.execute(f"SELECT COUNT(*) FROM {table}").scalar()
            print(f"  {table}: {result} records")
        except:
            print(f"  {table}: could not count records")