# Enhanced urls.py - Comprehensive API endpoints for agents
from django.urls import path
from . import views

urlpatterns = [
    # =============================================================================
    # EXISTING ENDPOINTS (your current ones)
    # =============================================================================
    
    # Main scraping API endpoint
    path('scrape-financial-data/', views.FinancialDataScraperAPI.as_view(), name='scrape_financial_data_api'),
    path('scrape-stock-price/', views.scrape_stock_price, name='scrape_stock_price'),
    
    # # Get scraping status
    # path('scraping-status/', views.get_scraping_status, name='scraping_status'),
    # path('scraping-status/<uuid:session_id>/', views.get_scraping_status, name='scraping_status_detail'),
    
    # # Get company data
    path('companies/', views.get_all_companies, name='all_companies'),
    # path('companies/<str:company_slug>/', views.get_company_data, name='company_data'),

    # =============================================================================
    
    # # Company overview and details
    # path('company/<str:company_slug>/tables/', views.company_financial_overview, name='company_overview'),
    # # path('company/<str:company_slug>/table/<str:table_type>/', views.company_table_view, name='company_table'),
    
    # # Company search and listing
    path('companies/search', views.get_all_companies, name='companies_search'),
    # # path('companies/list/', views.companies_search_view, name='companies_list'),  # Same endpoint
    # path(
    # 'company/<str:company_slug>/table/<str:table_type>/data/<str:data_type>/',
    # views.company_table_detail,
    # name='company_table_detail'
    # ),

    # path(
    # 'company/<str:company_slug>/table/<str:table_type>/data/<str:data_type>/value/',
    # views.company_table_value_detail,
    # name='company_table_value_detail'
    # ),

    
    # path('company/<str:company_slug>/table/<str:table_type>/data/<str:data_type>/filteration/',views.company_table_details_filteration,name="company_table_details_filteration"),

  
    # path('query/',views.find_parameter_in_tables,name="find_parameter_in_tables"),




    # path('stock/history/<str:company_slug>/', views.stock_history_view, name='stock_history'),

    path('financial/chat/', views.financial_chat, name="financial_chat"),
    
    # Check query status
    path('financial/status/<uuid:query_id>/', views.check_query_status, name="check_query_status"),
    
    # Get all queries (optional)
    path('financial/queries/', views.get_all_queries, name="get_all_queries"),
    path('financial/chat/test/', views.financial_chat_test, name="financial_chat_test"),
    path('financial/chat/test/history', views.financial_chat_history, name="financial_chat_history"),


    path('upload-csv/', views.UploadCSVView.as_view(), name='upload_csv'),

    path('companies/fetch/', views.fetch_companies_api, name='fetch_companies'),
    path('companies/list/', views.get_companies_list, name='companies_list'),
    path('companies/<str:slug>/', views.get_company_detail, name='company_detail'),



]




