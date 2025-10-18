#  Main/urls.py - Comprehensive API endpoints for agents
from django.urls import path
from . import views

urlpatterns = [
    # =============================================================================
    # EXISTING ENDPOINTS (your current ones)
    # =============================================================================
    
    # Main scraping API endpoint
    path('scrape-financial-data/', views.FinancialDataScraperAPI.as_view(), name='scrape_financial_data_api'),

    path('companies/', views.get_all_companies, name='all_companies'),
 
    path('companies/search', views.get_all_companies, name='companies_search'),
   

    path('financial/chat/', views.financial_chat, name="financial_chat"),
    
    # Check query status
    path('financial/status/<uuid:query_id>/', views.check_query_status, name="check_query_status"),
    
    # Get all queries (optional)
    path('financial/queries/', views.get_all_queries, name="get_all_queries"),
    path('financial/chat/test/history', views.financial_chat_history, name="financial_chat_history"),



    path('companies/fetch/', views.fetch_companies_api, name='fetch_companies'),
    path('companies/list/', views.get_companies_list, name='companies_list'),
    path('companies/<str:slug>/', views.get_company_detail, name='company_detail'),



]




