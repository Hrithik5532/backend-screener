# Main/tasks.py
from celery import shared_task
from django.utils import timezone
from .models import QueryUser
from .multi_agentic_understanding import main_analysis_function
import logging
import asyncio

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_financial_query(self, query_id):
    """
    Background task to process financial queries (handles async function).
    Includes retries with exponential backoff if something fails.
    """
    try:
        # Get the query object
        query_obj = QueryUser.objects.get(uid=query_id)
        query_obj.status = 'processing'
        query_obj.save(update_fields=['status', 'updated_at'])

        # Run async financial analysis safely
        result_dict = asyncio.run(main_analysis_function(query_obj.query))
        # result_dict = main_analysis_function(query_obj.query)
        result = result_dict
        table_fetched = []


        query_obj.response = result
        query_obj.status = 'completed'
        query_obj.table_fetched = table_fetched
        query_obj.updated_at = timezone.now()
        query_obj.save()

        logger.info(f"✅ Completed processing for query: {query_obj.query}")

        return {
            'query_id': str(query_id),
            'status': 'completed',
            'response': result
        }

    except QueryUser.DoesNotExist:
        logger.error(f"❌ Query with ID {query_id} not found")
        return {
            'query_id': str(query_id),
            'status': 'failed',
            'error': 'Query not found'
        }

    except Exception as e:
        logger.error(f"⚠️ Error processing query {query_id}: {str(e)}")

        # Update query status to failed only if object exists
        try:
            query_obj = QueryUser.objects.get(uid=query_id)
            query_obj.status = 'failed'
            query_obj.error_message = str(e)
            query_obj.save(update_fields=['status', 'error_message', 'updated_at'])
        except Exception:
            pass

        # Will be retried automatically (due to autoretry_for)
        raise
