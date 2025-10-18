# views.py
import json
import threading
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from yfinance import download as yf_download
import pandas as pd
from decimal import Decimal
import pandas as pd
from .models import (
    Company,QueryUser,StockPriceHistory,TestingQuery
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
from django.http import HttpResponse
import ast

from datetime import datetime
import requests

class FinancialDataScraperAPI(APIView):
    """
    REST API for scraping financial data from multiple companies
    
    POST /api/scrape-financial-data/
    
    Request Body:
    {
        "companies" : ["CENTENKA", "ABLBL", "ABFRL", "BIRLAMONEY", "ABSLAMC", "ABREL", "ABCAPITAL", "HINDALCO", "GRASIM", "ULTRACEMCO", "ACC", "SHREECEM","AMBUJACEM"],
        "sections": ["quarters", "profit-loss", "balance-sheet"],  // Optional
        "save_to_db": true,  // Optional, default: true
        "save_csv": true,    // Optional, default: true
        "async_mode": false  // Optional, default: false
    }
    """
    
    # permission_classes = [IsAuthenticated]  # Uncomment to require authentication
    
    def post(self, request):
        try:
            # Extract and validate request data
            companies = request.data.get('companies', [])
            sections = request.data.get('sections', None)  # None means scrape all sections
            save_to_db = request.data.get('save_to_db', True)
            save_csv = request.data.get('save_csv', True)
            async_mode = request.data.get('async_mode', True)
            
            # Validation
            if not companies:
                # return Response({
                #     'error': 'Companies list is required',
                #     'message': 'Please provide a list of company slugs to scrape'
                # }, status=status.HTTP_400_BAD_REQUEST)
                company_names = list(Company.objects.values_list('slug', flat=True))
            
            if not isinstance(companies, list):
                return Response({
                    'error': 'Companies must be a list',
                    'message': 'Companies should be an array of company slugs'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate sections if provided
            valid_sections = ['quarters', 'profit-loss', 'balance-sheet', 'ratios', 'cash-flow', 'shareholding', 'peers']
            if sections:
                invalid_sections = [s for s in sections if s not in valid_sections]
                if invalid_sections:
                    return Response({
                        'error': 'Invalid sections',
                        'message': f'Invalid sections: {invalid_sections}. Valid sections: {valid_sections}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate unique job ID for tracking
            job_id = str(uuid.uuid4())
            available_companies = []
            for company in companies:
                url = f"https://www.screener.in/company/{company}/"
                response = requests.get(url)
                if response.status_code == 200:
                    available_companies.append(company)
                else:
                    print(f"[API] Company {company} not found (status code {response.status_code})")
            if async_mode:
                # Run scraping in background thread
                thread = threading.Thread(
                    target=self._run_scraping_async,
                    args=(job_id, available_companies, sections, save_to_db, save_csv)
                )
                thread.start()
                
                return Response({
                    'status': 'started',
                    'job_id': job_id,
                    'message': 'Scraping started in background',
                    'companies_requested': companies,
                    'total_companies': len(companies),
                    'estimated_time_minutes': len(companies) * 2,  # Rough estimate
                    'sections': sections or valid_sections,
                    'check_status_url': f'/api/scrape-status/{job_id}/'
                }, status=status.HTTP_202_ACCEPTED)
            
            else:
                # Run scraping synchronously
                return self._run_scraping_sync(available_companies, sections, save_to_db, save_csv)
        
        except Exception as e:
            return Response({
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
                results['scraping_results'][available_companies[0]] = {
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



@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def scrape_stock_price(request):
    """Simple version that works directly with yfinance output"""
    try:
        # body = json.loads(request.body)
        companies = request.data.get("companies", [])
        
        results = []
        
        for company_slug in companies:
            try:
                company = Company.objects.get(slug=company_slug, is_active=True)
                
                # Download data - yfinance returns DataFrame directly
                stock_data = yf_download(
                    f'{company_slug}.NS',
                    period='5y',
                    interval='1mo',
                    progress=False
                )
                
                if stock_data.empty:
                    results.append({"company": company_slug, "status": "no_data"})
                    continue
                
                # Handle MultiIndex columns
                if isinstance(stock_data.columns, pd.MultiIndex):
                    # Drop the ticker level, keep only price type
                    stock_data.columns = stock_data.columns.droplevel(1)
                
                saved_count = 0
                
                # Direct iteration without extra DataFrame conversion
                for timestamp, row in stock_data.iterrows():
                    try:
                        close_price = row.get('Close') or row.get('Adj Close')
                        
                        if pd.notna(close_price):
                            StockPriceHistory.objects.update_or_create(
                                company=company,
                                date=timestamp.date(),
                                defaults={'price': Decimal(str(round(float(close_price), 2)))}
                            )
                            saved_count += 1
                    except:
                        continue
                
                results.append({
                    "company": company_slug,
                    "status": "success", 
                    "saved": saved_count
                })
                
            except Exception as e:
                results.append({
                    "company": company_slug,
                    "status": "error",
                    "message": str(e)
                })
        
        return JsonResponse({"status": "completed", "results": results})
        
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

from .agents.db_agents import db_agents_chat_stream_2
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


from .models import TestingQuery

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def financial_chat_test(request):
        if request.method == 'OPTIONS':
            return Response(status=status.HTTP_200_OK)

    # try:
        query = request.data.get("query", "")
        user_name = request.data.get("user_name", None)
        actual_response = request.data.get("actual_response", None)
        expected_response = request.data.get("expected_response", None)
        query_status = request.data.get("status", None)
        query_issues = request.data.get("issues", 'None')
        
        testing_obj = TestingQuery.objects.create(query=query,user_name=user_name,actual_response=actual_response,expected_response=expected_response,query_status=query_status,issues=query_issues)
        testing_obj.save()
        return Response({
            'query_id': str(testing_obj.id),
            'status': 'processing',
            'message': 'Testing Query submitted'
        }, status=status.HTTP_202_ACCEPTED)
    # except Exception as e:
    #     return Response({
    #         "error": str(e)
    #     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    




import pandas as pd
from django.http import JsonResponse
from django.views import View
from .models import TransformedData
import os

class UploadCSVView(View):
    def get(self, request):
        # try:
            # Load CSV
            # TransformedData.objects.all().delete()
            file_path = os.path.join("Main", "data.csv")
            df = pd.read_csv(file_path)
            df = df[df['table_name'].isin(['qbr_data'])]
            # --- Data Engineering ---
            # Combine year + month (handling missing months)
            df['year'] = df['quarter'].fillna('').astype(str) +' '+df['year'].astype(str)

            # Split metrics into 3 parts
            df[['data_type', 'metric_name', 'significance']] = (
                df['metrics'].str.split('_', n=2, expand=True)
            )

            # Fill NaNs with empty strings (to avoid NULL issues in CharFields)
            df = df.fillna("")

            # --- Save to DB ---
            objs = []
            for _, row in df.iterrows():
                obj = TransformedData(
                    company=row['business_name'],
                    year=row['year'],
                    table_name=row['table_name'],
                    metric_name=row['metric_name'],
                    significance=row['significance'],
                    data_type=row['data_type'],
                    value=str(row['value'])  # model field is CharField
                )
                objs.append(obj)

            # Bulk insert for performance
            TransformedData.objects.bulk_create(objs, ignore_conflicts=True)

            return JsonResponse({"status": "success", "rows_inserted": len(objs)})
        
        # except Exception as e:
        #     return JsonResponse({"status": "error", "message": str(e)}, status=500)




from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from Main.models import Company
import yfinance as yf
from datetime import datetime

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