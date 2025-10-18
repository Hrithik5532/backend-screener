# Main/views.py
import json
import threading
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from yfinance import download as yf_download

import pandas as pd
from .models import (
    Company,QueryUser,TestingQuery
)
import time
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .scrapperMain.scraper_service import scrape_companies_to_json,save_company_data_to_db

from rest_framework.views import APIView



from .tasks import process_financial_query
from celery.result import AsyncResult
import uuid
import ast

from datetime import datetime
import requests

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from Main.models import Company
import yfinance as yf
from datetime import datetime

import time
import requests
import threading
import logging
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)


class FinancialDataScraperAPI(APIView):
    """
    REST API for scraping financial data from multiple companies
    Optimized for large-scale scraping (2000+ companies)
    
    POST /api/scrape-financial-data/
    
    Request examples:
    1. Diagnose network:
       {"diagnose": true}
    
    2. Scrape with parallel method:
       {
           "companies": ["MANAKSIA", "KANPRPLA", ...],
           "validation_method": "parallel",
           "max_workers": 10,
           "async_mode": true
       }
    
    3. Scrape with batch method:
       {
           "companies": ["MANAKSIA", "KANPRPLA", ...],
           "validation_method": "batch",
           "batch_size": 50,
           "async_mode": true
       }
    """
    
    def diagnose_network(self):
        """Diagnose network connectivity issues"""
        logger.info("="*80)
        logger.info("🔍 NETWORK DIAGNOSTICS STARTED")
        logger.info("="*80)
        
        test_urls = [
            "https://www.screener.in",
         
        ]
        
        results = {}
        for url in test_urls:
            try:
                logger.info(f"Testing connection to: {url}")
                response = requests.get(url, timeout=5)
                results[url] = f"✓ OK (Status: {response.status_code})"
                logger.info(f"  ✓ Success - Status: {response.status_code}")
                print(f"✓ {url} - OK (Status: {response.status_code})")
            except Exception as e:
                error_msg = str(e)
                results[url] = f"✗ FAILED ({error_msg})"
                logger.error(f"  ✗ Failed - {error_msg}")
                print(f"✗ {url} - FAILED: {error_msg}")
        
        logger.info("="*80)
        logger.info("🔍 NETWORK DIAGNOSTICS COMPLETE")
        logger.info("="*80)
        
        return results
    
    def _create_session_with_retry(self):
        """Create a requests session with retry strategy"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=20,
            pool_maxsize=20
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        return session
    
    def _check_company_availability(self, company, session, rate_limiter, delay=0.5):
        """Check if a single company is available on screener.in"""
        url = f"https://www.screener.in/company/{company}/"
        
        try:
            # Acquire rate limit token
            rate_limiter.acquire()
            
            # Add delay between requests to avoid rate limiting
            time.sleep(delay)
            
            logger.debug(f"Checking availability for {company}...")
            response = session.get(url, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✓ FOUND: {company}")
                return {'company': company, 'available': True, 'status': 200}
            
            elif response.status_code == 429:
                logger.warning(f"⚠ Rate limited for {company}. Waiting 3s before retry...")
                time.sleep(3)
                
                try:
                    response = session.get(url, timeout=10)
                    if response.status_code == 200:
                        logger.info(f"✓ FOUND (retry successful): {company}")
                        return {'company': company, 'available': True, 'status': 200}
                except Exception as retry_error:
                    logger.error(f"✗ Retry failed for {company}: {str(retry_error)}")
                
                logger.error(f"✗ NOT FOUND: {company} (Status: {response.status_code})")
                return {'company': company, 'available': False, 'status': response.status_code}
            
            else:
                logger.error(f"✗ NOT FOUND: {company} (Status: {response.status_code})")
                return {'company': company, 'available': False, 'status': response.status_code}
        
        except requests.exceptions.Timeout:
            logger.error(f"✗ TIMEOUT: {company} - Request took too long")
            return {'company': company, 'available': False, 'error': 'Timeout'}
        
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"✗ CONNECTION ERROR: {company} - {str(conn_err)}")
            return {'company': company, 'available': False, 'error': 'Connection Error'}
        
        except Exception as e:
            logger.error(f"✗ ERROR: {company} - {str(e)}")
            return {'company': company, 'available': False, 'error': str(e)}
        
        finally:
            rate_limiter.release()
    
    def _validate_companies_availability_parallel(self, companies, max_workers=10):
        """Validate companies in parallel using ThreadPoolExecutor"""
        session = self._create_session_with_retry()
        available_companies = []
        failed_companies = []
        
        # Semaphore to limit concurrent requests
        rate_limiter = threading.Semaphore(max_workers)
        
        logger.info("="*80)
        logger.info("🚀 STARTING PARALLEL VALIDATION")
        logger.info(f"📊 Total companies: {len(companies)}")
        logger.info(f"👷 Max workers: {max_workers}")
        logger.info(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        
        print(f"\n{'='*80}")
        print(f"🚀 PARALLEL VALIDATION STARTED")
        print(f"   Total companies: {len(companies)}")
        print(f"   Max workers: {max_workers}")
        print(f"{'='*80}\n")
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._check_company_availability, company, session, rate_limiter): company
                for company in companies
            }
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                try:
                    result = future.result()
                    if result['available']:
                        available_companies.append(result['company'])
                    else:
                        failed_companies.append(result['company'])
                    
                    # Log progress every 50 companies
                    if completed % 50 == 0:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        remaining = len(companies) - completed
                        eta_seconds = remaining / rate if rate > 0 else 0
                        
                        progress_msg = (f"📈 PROGRESS: {completed}/{len(companies)} | "
                                      f"Found: {len(available_companies)} ✓ | "
                                      f"Failed: {len(failed_companies)} ✗ | "
                                      f"Rate: {rate:.1f}/sec | "
                                      f"ETA: {int(eta_seconds/60)}m {int(eta_seconds%60)}s")
                        logger.info(progress_msg)
                        
                        print(f"\n{'='*80}")
                        print(f"📊 PROGRESS UPDATE #{completed//50}")
                        print(f"   Processed: {completed}/{len(companies)}")
                        print(f"   Found: {len(available_companies)} ✓")
                        print(f"   Failed: {len(failed_companies)} ✗")
                        print(f"   Rate: {rate:.2f} companies/second")
                        print(f"   ETA: {int(eta_seconds/60)}m {int(eta_seconds%60)}s")
                        print(f"{'='*80}\n")
                
                except Exception as e:
                    logger.error(f"❌ Error processing result: {str(e)}")
        
        session.close()
        
        elapsed_time = time.time() - start_time
        logger.info("="*80)
        logger.info("✅ PARALLEL VALIDATION COMPLETE!")
        logger.info(f"📊 Results: {len(available_companies)}/{len(companies)} companies found")
        logger.info(f"⏱️  Time taken: {int(elapsed_time/60)}m {int(elapsed_time%60)}s")
        logger.info(f"⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        
        print(f"\n{'='*80}")
        print(f"✅ PARALLEL VALIDATION COMPLETE!")
        print(f"   Found: {len(available_companies)} companies ✓")
        print(f"   Failed: {len(failed_companies)} companies ✗")
        print(f"   Time: {int(elapsed_time/60)}m {int(elapsed_time%60)}s")
        print(f"{'='*80}\n")
        
        return available_companies
    
    def _validate_companies_availability_batch(self, companies, batch_size=50):
        """Validate companies in safe batches"""
        session = self._create_session_with_retry()
        available_companies = []
        
        logger.info("="*80)
        logger.info("🚀 STARTING BATCH VALIDATION")
        logger.info(f"📊 Total companies: {len(companies)}")
        logger.info(f"📦 Batch size: {batch_size}")
        logger.info(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        
        print(f"\n{'='*80}")
        print(f"🚀 BATCH VALIDATION STARTED")
        print(f"   Total companies: {len(companies)}")
        print(f"   Batch size: {batch_size}")
        print(f"{'='*80}\n")
        
        start_time = time.time()
        total_batches = (len(companies) + batch_size - 1) // batch_size
        
        for batch_num, i in enumerate(range(0, len(companies), batch_size), 1):
            batch = companies[i:i + batch_size]
            batch_results = {}
            
            logger.info(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} companies)...")
            
            def check_company(company):
                url = f"https://www.screener.in/company/{company}/"
                try:
                    time.sleep(0.3)  # Delay between requests
                    response = session.get(url, timeout=10)
                    if response.status_code == 200:
                        logger.debug(f"✓ Found: {company}")
                        batch_results[company] = True
                    else:
                        logger.debug(f"✗ Not found: {company} (Status: {response.status_code})")
                        batch_results[company] = False
                except Exception as e:
                    logger.debug(f"✗ Error: {company} - {str(e)}")
                    batch_results[company] = False
            
            # Create threads for batch
            threads = []
            for company in batch:
                t = threading.Thread(target=check_company, args=(company,), daemon=True)
                threads.append(t)
                t.start()
            
            # Wait for batch to complete
            for t in threads:
                t.join(timeout=60)
            
            # Collect results
            batch_found = [c for c, available in batch_results.items() if available]
            available_companies.extend(batch_found)
            
            elapsed = time.time() - start_time
            logger.info(f"✅ Batch {batch_num} complete: Found {len(batch_found)}/{len(batch)} | "
                       f"Total: {len(available_companies)} | Time: {int(elapsed)}s")
            
            print(f"\n{'='*80}")
            print(f"📦 BATCH {batch_num}/{total_batches}")
            print(f"   Companies in batch: {len(batch)}")
            print(f"   Found in batch: {len(batch_found)}")
            print(f"   Total found so far: {len(available_companies)}")
            print(f"   Elapsed time: {int(elapsed)}s")
            print(f"{'='*80}\n")
            
            # Small delay between batches
            time.sleep(2)
        
        session.close()
        
        elapsed_time = time.time() - start_time
        logger.info("="*80)
        logger.info("✅ BATCH VALIDATION COMPLETE!")
        logger.info(f"📊 Results: {len(available_companies)}/{len(companies)} companies found")
        logger.info(f"⏱️  Time taken: {int(elapsed_time/60)}m {int(elapsed_time%60)}s")
        logger.info(f"⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        
        print(f"\n{'='*80}")
        print(f"✅ BATCH VALIDATION COMPLETE!")
        print(f"   Found: {len(available_companies)} companies ✓")
        print(f"   Time: {int(elapsed_time/60)}m {int(elapsed_time%60)}s")
        print(f"{'='*80}\n")
        
        return available_companies
    
    def post(self, request):
        """Handle POST requests"""
        try:
            # Check if user is running diagnostics
            run_diagnostics = request.data.get('diagnose', False)
            
            if run_diagnostics:
                logger.info("🔧 Diagnostic request received")
                diag_results = self.diagnose_network()
                return Response({
                    'status': 'diagnostics_complete',
                    'results': diag_results,
                    'timestamp': timezone.now().isoformat()
                }, status=status.HTTP_200_OK)
            
            # Extract request parameters
            companies = request.data.get('companies', [])
            sections = request.data.get('sections', None)
            save_to_db = request.data.get('save_to_db', True)
            save_csv = request.data.get('save_csv', True)
            async_mode = request.data.get('async_mode', True)
            validation_method = request.data.get('validation_method', 'batch')
            max_workers = request.data.get('max_workers', 5)
            batch_size = request.data.get('batch_size', 50)
            
            # Validate companies list
            if not companies:
                companies = list(Company.objects.values_list('slug', flat=True))
            
            if not isinstance(companies, list):
                return Response({
                    'error': 'Companies must be a list',
                    'message': 'Companies should be an array of company slugs'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate sections
            valid_sections = ['quarters', 'profit-loss', 'balance-sheet', 'ratios', 'cash-flow', 'shareholding']
            if sections:
                invalid_sections = [s for s in sections if s not in valid_sections]
                if invalid_sections:
                    return Response({
                        'error': 'Invalid sections',
                        'message': f'Invalid sections: {invalid_sections}. Valid sections: {valid_sections}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            job_id = str(uuid.uuid4())
            
            logger.info("="*80)
            logger.info(f"📋 NEW JOB CREATED")
            logger.info(f"   Job ID: {job_id}")
            logger.info(f"   Companies: {len(companies)}")
            logger.info(f"   Validation method: {validation_method}")
            logger.info(f"   Async mode: {async_mode}")
            logger.info("="*80)
            
            # Validate companies
            if validation_method == 'batch':
                logger.info("Using BATCH validation method")
                available_companies = self._validate_companies_availability_batch(companies, batch_size)
            else:
                logger.info("Using PARALLEL validation method")
                available_companies = self._validate_companies_availability_parallel(companies, max_workers)
            
            if not available_companies:
                logger.error("❌ No valid companies found!")
                return Response({
                    'error': 'No valid companies found',
                    'message': 'None of the requested companies are available on screener.in',
                    'job_id': job_id
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"✅ Validation complete! Found {len(available_companies)} companies")
            
            return Response({
                'status': 'success',
                'job_id': job_id,
                'message': f'Successfully found {len(available_companies)} companies',
                'companies_requested': len(companies),
                'companies_found': len(available_companies),
                'available_companies': available_companies[:10],  # Show first 10
                'total_found': len(available_companies),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"❌ ERROR: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': 'Internal server error',
                'message': str(e),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _run_scraping_sync(self, companies, sections, save_to_db, save_csv):
        """Run scraping synchronously and return results"""
        start_time = time.time()
        
        try:
            # Run the scraper
            print(f"[API] Starting synchronous scraping for {len(companies)} companies")

            

            scraped_data = scrape_companies_to_json(companies, sections, save_csv)

            # Process results
            results = {
                'status': 'completed',
                'started_at': datetime.fromtimestamp(start_time).isoformat(),
                'completed_at': timezone.now().isoformat(),
                'duration_seconds': round(time.time() - start_time, 2),
                'companies_requested': companies,
                'total_companies': len(companies),
                'sections_scraped': sections or ['quarters', 'profit-loss', 'balance-sheet', 'ratios', 'cash-flow', 'shareholding', 'peers'],
                'scraping_results': {},
                'database_results': {},
                'summary': {
                    'companies_completed': 0,
                    'companies_failed': 0,
                    'total_tables_scraped': 0,
                    'total_metrics_created': 0,
                    'total_errors': 0
                }
            }
            
            # Handle single vs multiple company results
            if len(companies) == 1:
                # Single company result
                company_data = scraped_data
                results['scraping_results']['available_companies'][0] = {
                    'status': company_data.get('status', 'unknown'),
                    'sections_completed': company_data.get('summary', {}).get('total_sections_completed', 0),
                    'tables_scraped': company_data.get('summary', {}).get('total_tables_scraped', 0),
                    'errors': company_data.get('errors', [])
                }
                
                # Save to database if requested
                if save_to_db:
                    db_result = save_company_data_to_db(company_data, companies[0])
                    results['database_results'][companies[0]] = db_result
                    
                    if db_result.get('success'):
                        results['summary']['companies_completed'] = 1
                        results['summary']['total_metrics_created'] = db_result.get('metrics_created', 0)
                    else:
                        results['summary']['companies_failed'] = 1
                
                results['summary']['total_tables_scraped'] = company_data.get('summary', {}).get('total_tables_scraped', 0)
                results['summary']['total_errors'] = len(company_data.get('errors', []))
            
            else:
                # Multiple companies result
                for company_data in scraped_data.get('companies_data', []):
                    company_slug = company_data.get('company_slug')
                    if not company_slug:
                        continue
                    
                    results['scraping_results'][company_slug] = {
                        'status': company_data.get('status', 'unknown'),
                        'sections_completed': company_data.get('summary', {}).get('total_sections_completed', 0),
                        'tables_scraped': company_data.get('summary', {}).get('total_tables_scraped', 0),
                        'errors': company_data.get('errors', [])
                    }
                    
                    # Save to database if requested
                    if save_to_db:
                        db_result = save_company_data_to_db(company_data, company_slug)
                        results['database_results'][company_slug] = db_result
                        
                        if db_result.get('success'):
                            results['summary']['companies_completed'] += 1
                            results['summary']['total_metrics_created'] += db_result.get('metrics_created', 0)
                        else:
                            results['summary']['companies_failed'] += 1
                    
                    results['summary']['total_tables_scraped'] += company_data.get('summary', {}).get('total_tables_scraped', 0)
                    results['summary']['total_errors'] += len(company_data.get('errors', []))
                
                # Update summary from scraped_data if available
                if 'summary' in scraped_data:
                    results['summary'].update(scraped_data['summary'])
            
            print(f"[API] Scraping completed in {results['duration_seconds']} seconds")
            
            return Response(results, status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"[API] Scraping failed: {str(e)}")
            return Response({
                'status': 'failed',
                'error': str(e),
                'started_at': datetime.fromtimestamp(start_time).isoformat(),
                'failed_at': timezone.now().isoformat(),
                'duration_seconds': round(time.time() - start_time, 2),
                'companies_requested': companies
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _run_scraping_async(self, job_id, companies, sections, save_to_db, save_csv):
        """Run scraping asynchronously in background thread"""
        # Note: In production, use Celery or similar task queue instead of threads
        try:
            print(f"[API] Starting async scraping job {job_id} for {len(companies)} companies")
            
            # Store job status (in production, use Redis or database)
            # For now, we'll just print status updates
            
            scraped_data = scrape_companies_to_json(companies, sections, save_csv)
            
            # Process database saving if requested
            if save_to_db:
                if len(companies) == 1:
                    save_company_data_to_db(scraped_data, companies[0])
                else:
                    for company_data in scraped_data.get('companies_data', []):
                        company_slug = company_data.get('company_slug')
                        if company_slug:
                            save_company_data_to_db(company_data, company_slug)
            
            print(f"[API] Async scraping job {job_id} completed successfully")
            
        except Exception as e:
            print(f"[API] Async scraping job {job_id} failed: {str(e)}")




# from .agents.db_agents import db_agents_chat_stream_2
from django.views.decorators.csrf import csrf_exempt
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
import json

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
async def financial_chat(request):
    # Handle OPTIONS for CORS
    if request.method == 'OPTIONS':
        response = JsonResponse({'status': 'ok'})
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    try:
        # Parse JSON body
        body = json.loads(request.body.decode('utf-8'))
        query = body.get("query", "")
        user_name = body.get("user_name", None)
        companies = body.get("companies", [])
        
        if not query:
            return JsonResponse({
                'error': 'Query is required'
            }, status=400)
        
        if not companies:
            from asgiref.sync import sync_to_async
            from Main.models import Company
            companies = await sync_to_async(list)(
                Company.objects.values_list('slug', flat=True)
            )

        # Get the async generator
        async def stream_response():
            try:
                async for chunk in db_agents_chat_stream_2(
                    user=user_name,
                    query=query,
                    businesses=companies
                ):
                    if chunk:
                        yield chunk
            except Exception as e:
                yield f"\n\nError: {str(e)}"

        # Return streaming response with CORS headers
        response = StreamingHttpResponse(
            stream_response(),
            content_type="text/plain; charset=utf-8"
        )
        response["Access-Control-Allow-Origin"] = "*"
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        
        return response

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Error: {str(e)}'
        }, status=500)



@csrf_exempt
@api_view(['GET', 'OPTIONS'])
@permission_classes([AllowAny])
def get_all_companies(request):
    try:
        companies = Company.objects.filter(is_active=True).order_by('name')
        companies_data = [
            {
                'name': c.slug,
               'sector': c.sector,
                'industry': c.industry
            } for c in companies
        ]
        return JsonResponse({
            'status': 'success',
            'total_companies': len(companies_data),
            'companies': companies_data
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@api_view(['GET','OPTIONS'])
@permission_classes([AllowAny])
def check_query_status(request, query_id):
    """
    Check the status of a financial query

    """
    if request.method == 'OPTIONS':
        return Response(status=status.HTTP_200_OK)
    try:
        query_obj = QueryUser.objects.get(uid=query_id)
        
        # If task is still running, check Celery status
        if query_obj.status == 'processing' and query_obj.task_id:
            task_result = AsyncResult(query_obj.task_id)
            
            if task_result.ready():
                if task_result.successful():
                    # Task completed successfully
                    result = task_result.result
                    query_obj.status = 'completed'
                    query_obj.response = result.get('response', '')
                    query_obj.save()
                else:
                    # Task failed
                    query_obj.status = 'failed'
                    query_obj.error_message = str(task_result.info)
                    query_obj.save()


        try:
                table_value = query_obj.table_fetched
                if isinstance(table_value, str):
                    try:
                        # Convert Python repr string → Python object
                        table_value = ast.literal_eval(table_value)
                    except Exception:
                        pass  # Maybe it's already JSON

                # Now dump valid JSON
                table_json = json.dumps(table_value)
        except Exception:
                table_json = "null"
        
        response_data = {
            'query_id': str(query_obj.uid),
            'query': query_obj.query,
            'status': query_obj.status,
            'created_at': query_obj.created_at,
            'updated_at': query_obj.updated_at,
            'table': table_json,  # ✅ Convert to proper JSON
            

        }
        
        if query_obj.status == 'completed':
            response_data.update({
                'markdown_response': query_obj.response,
                'query': query_obj.query
            })
        elif query_obj.status == 'failed':
            response_data['error_message'] = query_obj.error_message
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except QueryUser.DoesNotExist:
        return Response({
            'error': 'Query not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Error checking query status: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def get_all_queries(request):
    """
    Get all queries for a user (optional)
    """
    if request.method == 'OPTIONS':
        return Response(status=status.HTTP_200_OK)
    try:
        user_name = request.GET.get('user_name', None)
        if user_name:
            queries = QueryUser.objects.filter(user_name=user_name).order_by('created_at')
        else:
            queries = QueryUser.objects.all().order_by('created_at')
        print(user_name)
            
        queries_data = []
        for query in queries:
            try:
                table_value = query.table_fetched
                if isinstance(table_value, str):
                    try:
                        # Convert Python repr string → Python object
                        table_value = ast.literal_eval(table_value)
                    except Exception:
                        pass  # Maybe it's already JSON

                # Now dump valid JSON
                table_json = json.dumps(table_value)
            except Exception:
                table_json = "null"
            query_data = {
                'query_id': str(query.uid),
                'query': query.query,
                'status': query.status,
                'created_at': query.created_at,
                'updated_at': query.updated_at,
                'table': table_json # ✅ Convert to proper JSON

            }
            
            if query.status == 'completed':
                query_data['markdown_response'] = query.response
            elif query.status == 'failed':
                query_data['error_message'] = 'Server issue : Task not created'
                
            queries_data.append(query_data)
        
        return Response({
            'queries': queries_data,
            'count': len(queries_data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Error fetching queries: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def delete_all_data(request):
        try:
            print("Deleting all data from DB")
            # Delete all records from Company
            Company.objects.all().delete()
            return JsonResponse({
                "status": "success",
                "message": "All data deleted from Company"
            })
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": f"Error deleting data: {str(e)}"
            }, status=500)
    




@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def financial_chat_history(request):
    if request.method == 'OPTIONS':
        return Response(status=status.HTTP_200_OK)

    try:
        user_name = request.GET.get("user_name", None)

        if user_name:
            history = TestingQuery.objects.filter(user_name=user_name)
       

        # serialize data
        history_data = []
        for h in history:
            history_data.append({
                "id": str(h.id),
                "query": h.query,
                "user_name": h.user_name,
                "actual_response": h.actual_response,
                "expected_response": h.expected_response,
                "query_status": h.query_status,
                "issues": h.issues,
            })

        return Response({
            "count": history.count(),
            "history": history_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@csrf_exempt
async def fetch_companies_api(request):
    """API to trigger company fetch"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        import subprocess
        
        # Run management command in background
        exchange = request.POST.get('exchange', 'NSE')
        
        # Run command
        subprocess.Popen([
            'python', 'manage.py', 'fetch_all_companies', 
            '--exchange', exchange
        ])
        
        return JsonResponse({
            'status': 'started',
            'message': f'Fetching {exchange} companies in background'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def get_companies_list(request):
    """API to get all companies with filters"""
    try:
        sector = request.GET.get('sector')
        industry = request.GET.get('industry')
        
        companies = Company.objects.filter(is_active=True)
        
        if sector:
            companies = companies.filter(sector__icontains=sector)
        if industry:
            companies = companies.filter(industry__icontains=industry)
        
        data = list(companies.values(
            'slug', 'name', 'sector', 'industry', 'about_company', 'last_scraped'
        ))
        
        return JsonResponse({
            'status': 'success',
            'count': len(data),
            'companies': data
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def get_company_detail(request, slug):
    """Get single company detail"""
    try:
        company = Company.objects.get(slug=slug.upper())
        
        return JsonResponse({
            'status': 'success',
            'company': {
                'slug': company.slug,
                'name': company.name,
                'sector': company.sector,
                'industry': company.industry,
                'about_company': company.about_company,
                'key_points': company.key_points,
                'last_scraped': company.last_scraped,
                'is_active': company.is_active
            }
        })
        
    except Company.DoesNotExist:
        return JsonResponse({'error': 'Company not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)