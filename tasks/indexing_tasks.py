# tasks/indexing_tasks.py
from .celery_app import celery  # This will work now
from models import Book
from services.solr_client import solr_client
import logging

logger = logging.getLogger(__name__)

@celery.task(bind=True, max_retries=3)
def index_book_task(self, book_id):
    """Index a single book"""
    try:
        # App context is automatically provided by ContextTask
        book = Book.query.get(book_id)
        if book:
            success = solr_client.index_book(book)
            if success:
                logger.info(f"✅ Indexed book {book_id}")
                return {'status': 'success', 'book_id': book_id}
            else:
                raise Exception("Indexing failed")
        else:
            logger.warning(f"❌ Book {book_id} not found")
            return {'status': 'not_found', 'book_id': book_id}
    except Exception as exc:
        logger.error(f"❌ Error indexing book {book_id}: {exc}")
        self.retry(exc=exc, countdown=60)

# ... rest of your tasks


@celery.task
def bulk_index_task(book_ids):
    """Index multiple books"""
    # Create Flask app context for this task
    app = create_app()
    with app.app_context():
        results = {'success': [], 'failed': []}
        
        for book_id in book_ids:
            try:
                book = Book.query.get(book_id)
                if book and solr_client.index_book(book):
                    results['success'].append(book_id)
                else:
                    results['failed'].append(book_id)
            except Exception as e:
                logger.error(f"Failed to index book {book_id}: {e}")
                results['failed'].append(book_id)
        
        logger.info(f"✅ Bulk indexed {len(results['success'])} books, {len(results['failed'])} failed")
        return results


@celery.task
def delete_book_task(book_id):
    """Remove book from index"""
    app = create_app()
    with app.app_context():
        success = solr_client.delete_book(book_id)
        return {'status': 'success' if success else 'failed', 'book_id': book_id}


@celery.task
def reindex_all_task():
    """Rebuild entire index"""
    app = create_app()
    with app.app_context():
        from models import Book
        
        # Clear existing index
        solr_client.delete_all()
        
        # Get all books
        books = Book.query.all()
        book_ids = [book.id for book in books]
        
        # Process in batches
        batch_size = 50
        for i in range(0, len(book_ids), batch_size):
            batch = book_ids[i:i+batch_size]
            bulk_index_task.delay(batch)
        
        return {'total': len(book_ids), 'message': f'Started reindexing {len(book_ids)} books'}