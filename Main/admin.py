from django.contrib import admin
from .models import (
    Company, 
    FinancialDataTable, 
    KeyFinancialMetric, 
    TableDataHistory, 
    ScrapingSession, 
    StockPriceHistory,
    QueryUser,
    TransformedData
)

# =========================
# INLINE ADMIN
# =========================
class FinancialDataTableInline(admin.TabularInline):
    model = FinancialDataTable
    fields = ('table_type', 'data_type', 'table_title', 'scraped_at', 'is_active')
    extra = 0
    readonly_fields = ('scraped_at',)
    show_change_link = True


class KeyFinancialMetricInline(admin.TabularInline):
    model = KeyFinancialMetric
    fields = ('metric_name', 'period', 'raw_value', 'numeric_value', 'unit')
    extra = 0
    readonly_fields = ('metric_name', 'period', 'raw_value', 'numeric_value', 'unit')
    can_delete = False
    show_change_link = True


# =========================
# COMPANY ADMIN
# =========================
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        'slug', 'is_active', 'updated_at'
    )
    list_filter = [ 'is_active']
    search_fields = ['slug']
    # ordering = ('slug',)
    inlines = [FinancialDataTableInline, KeyFinancialMetricInline]
    readonly_fields = ('created_at', 'updated_at', 'last_scraped')


# =========================
# FINANCIAL DATA TABLE ADMIN
# =========================
@admin.register(FinancialDataTable)
class FinancialDataTableAdmin(admin.ModelAdmin):
    list_display = (
        'company', 'table_type', 'data_type', 'table_title',
        'total_rows', 'total_columns', 'scraped_at', 'is_active'
    )
    list_filter = ('table_type', 'data_type', 'is_active', 'scraped_at')
    search_fields = ( 'company__slug', 'table_title')
    ordering = ('-scraped_at',)
    inlines = [ KeyFinancialMetricInline]

    readonly_fields = ('scraped_at', 'updated_at', 'total_rows', 'total_columns')
    autocomplete_fields = ('company',)


# =========================
# KEY FINANCIAL METRIC ADMIN
# =========================
@admin.register(KeyFinancialMetric)
class KeyFinancialMetricAdmin(admin.ModelAdmin):
    list_display = (
        'company', 'metric_name', 'period', 'period_type', 
        'raw_value', 'numeric_value', 'unit'
    )
    list_filter = ('metric_category', 'period_type','company__slug')
    search_fields = ('metric_name', 'period',  'company__slug')
    ordering = ( 'metric_name', 'period')
    autocomplete_fields = ('company', 'source_table')


# =========================
# TABLE DATA HISTORY ADMIN
# =========================
@admin.register(TableDataHistory)
class TableDataHistoryAdmin(admin.ModelAdmin):
    list_display = ('original_table', 'archived_at', 'archive_reason')
    list_filter = ('archive_reason', 'archived_at')
    search_fields = ['original_table__company__slug']
    ordering = ('-archived_at',)
    readonly_fields = ('archived_column_headers', 'archived_table_data')


# =========================
# SCRAPING SESSION ADMIN
# =========================
@admin.register(ScrapingSession)
class ScrapingSessionAdmin(admin.ModelAdmin):
    list_display = (
        'session_id', 'status', 'tables_created', 'metrics_extracted', 
        'started_at', 'completed_at', 'duration_minutes'
    )
    list_filter = ('status', 'started_at')
    search_fields = ('session_id',)
    ordering = ('-started_at',)
    readonly_fields = (
        'started_at', 'completed_at', 'duration_minutes', 
        'companies_completed', 'companies_failed', 'error_log'
    )


# =========================
# STOCK PRICE HISTORY ADMIN
# =========================
@admin.register(StockPriceHistory)
class StockPriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('company', 'date', 'price')
    list_filter = ['date']
    search_fields = ['company__slug']
    ordering = ('-date',)
    autocomplete_fields = ['company']


from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.urls import path, reverse
from django.utils.safestring import mark_safe
import markdown
from weasyprint import HTML, CSS
from django.shortcuts import get_object_or_404

from .models import QueryUser



class TableFetchedFilter(admin.SimpleListFilter):
    title = 'Table Fetched'
    parameter_name = 'table_fetched_status'

    def lookups(self, request, model_admin):
        return [
            ('none', 'Not Fetched'),
            ('fetched', 'Fetched'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'none':
            return queryset.filter(table_fetched__isnull=True) | queryset.filter(table_fetched='')
        if self.value() == 'fetched':
            return queryset.exclude(table_fetched__isnull=True).exclude(table_fetched='')
        return queryset


@admin.register(QueryUser)
class QueryUserAdmin(admin.ModelAdmin):
    list_display = ("uid_short", "query_preview", "user_name", "status", "download_pdf_button", "created_at")
    list_filter = ("status", "user_name", "created_at", TableFetchedFilter)
    search_fields = ("query", "user_name", "uid")
    readonly_fields = ("uid", "task_id", "formatted_response", "formatted_table_fetched", "created_at", "updated_at")
    
    fieldsets = (
        ("Query Information", {
            "fields": ("uid", "query", "user_name", "status")
        }),
        ("Processing Details", {
            "fields": ("task_id", "error_message", "formatted_table_fetched"),
            "classes": ("collapse",)
        }),
        ("Response", {
            "fields": ("formatted_response",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def uid_short(self, obj):
        """Show first 8 characters of UID"""
        return str(obj.uid)[:8] + "..."
    uid_short.short_description = "UID"
    
    def query_preview(self, obj):
        """Show first 60 characters of query"""
        return obj.query[:60] + "..." if len(obj.query) > 60 else obj.query
    query_preview.short_description = "Query"

    def formatted_response(self, obj):
        """Display formatted response in admin"""
        if obj.response:
            html = markdown.markdown(obj.response, extensions=["fenced_code", "tables", "codehilite"])
            return mark_safe(f'<div style="max-height: 500px; overflow-y: auto; border: 1px solid #ddd; padding: 15px; background: #f9f9f9;">{html}</div>')
        return "No response available"
    formatted_response.short_description = "Response (Formatted)"

    def formatted_table_fetched(self, obj):
        """Display formatted table fetched data"""
        if obj.table_fetched:
            try:
                # Try to format as JSON if it's JSON data
                import json
                data = json.loads(obj.table_fetched)
                formatted_json = json.dumps(data, indent=2)
                return mark_safe(f'<pre style="max-height: 300px; overflow-y: auto; background: #f4f4f4; padding: 10px; border-radius: 5px;">{formatted_json}</pre>')
            except:
                # If not JSON, display as plain text
                return mark_safe(f'<pre style="max-height: 300px; overflow-y: auto; background: #f4f4f4; padding: 10px; border-radius: 5px;">{obj.table_fetched}</pre>')
        return "No table data"
    formatted_table_fetched.short_description = "Table Data (Formatted)"

    def download_pdf_button(self, obj):
        """Create download PDF button"""
        if obj.pk:
            url = reverse('admin:download_queryuser_pdf', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" target="_blank" style="background: #417690; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px;">📄 Download PDF</a>',
                url
            )
        return "Save first"
    download_pdf_button.short_description = "PDF Download"
    download_pdf_button.allow_tags = True

    def get_urls(self):
        """Add custom URL for PDF download"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'download-pdf/<int:query_id>/',
                self.admin_site.admin_view(self.generate_pdf),
                name='download_queryuser_pdf',
            ),
        ]
        return custom_urls + urls

    def generate_pdf(self, request, query_id):
        """Generate and return PDF for the query"""
        try:
            obj = get_object_or_404(QueryUser, pk=query_id)
            
            # Convert markdown response to HTML
            response_html = markdown.markdown(
                obj.response or "No response available", 
                extensions=["fenced_code", "tables", "codehilite"]
            )
            
            # Format table data
            table_data_html = ""
            if obj.table_fetched:
                try:
                    import json
                    data = json.loads(obj.table_fetched)
                    formatted_json = json.dumps(data, indent=2)
                    table_data_html = f'<pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-wrap: break-word; white-space: pre-wrap;">{formatted_json}</pre>'
                except:
                    table_data_html = f'<pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-wrap: break-word; white-space: pre-wrap;">{obj.table_fetched}</pre>'
            else:
                table_data_html = '<p style="color: #666; font-style: italic;">No table data available</p>'

            # Error message section
            error_section = ""
            if obj.error_message:
                error_section = f"""
                <div class="section">
                    <div class="section-title">⚠️ Error Information</div>
                    <div class="error-box">
                        {obj.error_message}
                    </div>
                </div>
                """

            # Enhanced HTML template
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Query Report - {obj.uid}</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        margin: 30px;
                        line-height: 1.6;
                        color: #333;
                        font-size: 12px;
                    }}
                    
                    .header {{
                        border-bottom: 3px solid #417690;
                        padding-bottom: 20px;
                        margin-bottom: 30px;
                    }}
                    
                    .title {{
                        color: #417690;
                        font-size: 24px;
                        font-weight: bold;
                        margin: 0;
                    }}
                    
                    .subtitle {{
                        color: #666;
                        font-size: 14px;
                        margin: 5px 0 0 0;
                    }}
                    
                    .section {{
                        margin-bottom: 30px;
                        page-break-inside: avoid;
                    }}
                    
                    .section-title {{
                        background: #f8f9fa;
                        border-left: 4px solid #417690;
                        padding: 10px 15px;
                        font-size: 16px;
                        font-weight: bold;
                        color: #417690;
                        margin-bottom: 15px;
                    }}
                    
                    .query-box {{
                        background: #fff3cd;
                        border: 1px solid #ffeaa7;
                        border-radius: 5px;
                        padding: 15px;
                        margin-bottom: 20px;
                        font-style: italic;
                    }}
                    
                    .response-box {{
                        border: 1px solid #e9ecef;
                        border-radius: 5px;
                        padding: 20px;
                        background: #ffffff;
                    }}
                    
                    .error-box {{
                        background: #f8d7da;
                        border: 1px solid #f5c6cb;
                        border-radius: 5px;
                        padding: 15px;
                        color: #721c24;
                    }}
                    
                    .metadata {{
                        background: #f8f9fa;
                        border-radius: 5px;
                        padding: 15px;
                        font-size: 11px;
                        color: #666;
                    }}
                    
                    .metadata-row {{
                        display: flex;
                        justify-content: space-between;
                        margin-bottom: 8px;
                        border-bottom: 1px solid #eee;
                        padding-bottom: 5px;
                    }}
                    
                    .metadata-row:last-child {{
                        border-bottom: none;
                        margin-bottom: 0;
                    }}
                    
                    .status {{
                        padding: 4px 10px;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 10px;
                        text-transform: uppercase;
                    }}
                    
                    .status-completed {{ background: #d4edda; color: #155724; }}
                    .status-pending {{ background: #fff3cd; color: #856404; }}
                    .status-processing {{ background: #cce7ff; color: #004085; }}
                    .status-failed {{ background: #f8d7da; color: #721c24; }}
                    
                    .uid-display {{
                        font-family: 'Courier New', monospace;
                        background: #f1f3f4;
                        padding: 2px 6px;
                        border-radius: 3px;
                        font-size: 10px;
                    }}
                    
                    h1, h2, h3, h4, h5, h6 {{
                        color: #2c3e50;
                        margin-top: 25px;
                        margin-bottom: 15px;
                    }}
                    
                    pre, code {{
                        background: #f4f4f4;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        padding: 8px 12px;
                        font-family: 'Courier New', monospace;
                        font-size: 10px;
                        overflow-wrap: break-word;
                    }}
                    
                    pre {{
                        white-space: pre-wrap;
                        word-wrap: break-word;
                        max-width: 100%;
                    }}
                    
                    table {{
                        border-collapse: collapse;
                        width: 100%;
                        margin: 15px 0;
                        font-size: 10px;
                    }}
                    
                    th, td {{
                        border: 1px solid #ddd;
                        padding: 8px;
                        text-align: left;
                    }}
                    
                    th {{
                        background-color: #f2f2f2;
                        font-weight: bold;
                    }}
                    
                    blockquote {{
                        border-left: 4px solid #ddd;
                        margin: 15px 0;
                        padding-left: 15px;
                        color: #666;
                    }}
                    
                    .page-break {{
                        page-break-before: always;
                    }}
                    
                    .footer {{
                        margin-top: 40px;
                        padding-top: 20px;
                        border-top: 1px solid #eee;
                        font-size: 10px;
                        color: #999;
                        text-align: center;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1 class="title">Financial Query Analysis Report</h1>
                    <p class="subtitle">Generated on: {obj.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>

                <div class="section">
                    <div class="section-title">📋 Query Metadata</div>
                    <div class="metadata">
                        <div class="metadata-row">
                            <span><strong>Query UID:</strong></span>
                            <span class="uid-display">{obj.uid}</span>
                        </div>
                        <div class="metadata-row">
                            <span><strong>User:</strong></span>
                            <span>{obj.user_name or 'Anonymous'}</span>
                        </div>
                        <div class="metadata-row">
                            <span><strong>Status:</strong></span>
                            <span class="status status-{obj.status}">{obj.get_status_display()}</span>
                        </div>
                        <div class="metadata-row">
                            <span><strong>Task ID:</strong></span>
                            <span class="uid-display">{obj.task_id or 'N/A'}</span>
                        </div>
                        <div class="metadata-row">
                            <span><strong>Created:</strong></span>
                            <span>{obj.created_at.strftime('%Y-%m-%d %H:%M:%S')}</span>
                        </div>
                        <div class="metadata-row">
                            <span><strong>Last Updated:</strong></span>
                            <span>{obj.updated_at.strftime('%Y-%m-%d %H:%M:%S')}</span>
                        </div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-title">❓ Original Query</div>
                    <div class="query-box">
                        {obj.query}
                    </div>
                </div>

                <div class="section">
                    <div class="section-title">📊 Analysis Response</div>
                    <div class="response-box">
                        {response_html}
                    </div>
                </div>

                {error_section}

                <div class="section page-break">
                    <div class="section-title">🗃️ Retrieved Table Data</div>
                    <div class="response-box">
                        {table_data_html}
                    </div>
                </div>

                <div class="footer">
                    <p>Financial Analysis System | Report generated automatically | UID: {obj.uid}</p>
                </div>
            </body>
            </html>
            """

            # Generate PDF
            css = CSS(string='''
                @page {
                    margin: 2cm;
                    size: A4;
                    @top-right {
                        content: "Page " counter(page) " of " counter(pages);
                    }
                }
                
                @media print {
                    .page-break {
                        page-break-before: always;
                    }
                }
            ''')

            pdf_file = HTML(string=html_content).write_pdf(stylesheets=[css])

            # Create response
            response = HttpResponse(pdf_file, content_type="application/pdf")
            filename = f"query_report_{str(obj.uid)[:8]}_{obj.user_name or 'anonymous'}_{obj.created_at.strftime('%Y%m%d_%H%M')}.pdf"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            
            return response

        except QueryUser.DoesNotExist:
            return HttpResponse("Query not found", status=404)
        except Exception as e:
            return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

    def changelist_view(self, request, extra_context=None):
        """Add custom context to changelist view"""
        extra_context = extra_context or {}
        extra_context['title'] = 'Financial Query Users with PDF Export'
        return super().changelist_view(request, extra_context=extra_context)

    class Meta:
        verbose_name = "Query User"
        verbose_name_plural = "Query Users"


# Admin action for bulk PDF generation
@admin.action(description='Download selected queries as PDF')
def download_selected_queries_as_pdf(modeladmin, request, queryset):
    """Bulk download action for multiple queries"""
    if queryset.count() == 1:
        # Single query - redirect to individual PDF
        query = queryset.first()
        url = reverse('admin:download_queryuser_pdf', args=[query.pk])
        return HttpResponse(f'<script>window.open("{url}");</script>')
    
    # Multiple queries - create combined PDF
    html_parts = []
    
    for query in queryset.order_by('-created_at'):
        response_html = markdown.markdown(
            query.response or "No response available", 
            extensions=["fenced_code", "tables"]
        )
        
        status_class = f"status-{query.status}"
        
        html_parts.append(f"""
            <div class="query-section">
                <div class="query-header">
                    <h2>Query: {str(query.uid)[:8]}... - {query.user_name or 'Anonymous'}</h2>
                    <div class="status {status_class}">{query.get_status_display()}</div>
                    <div class="timestamp">Created: {query.created_at.strftime('%Y-%m-%d %H:%M')}</div>
                </div>
                <div class="query-content">
                    <h3>Original Query:</h3>
                    <div class="query">{query.query}</div>
                    <h3>Response:</h3>
                    <div class="response">{response_html}</div>
                </div>
            </div>
            <div style="page-break-after: always;"></div>
        """)
    
    combined_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Bulk Query Report</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; font-size: 12px; }}
            .query-section {{ margin-bottom: 40px; }}
            .query-header {{ background: #f8f9fa; padding: 15px; margin-bottom: 15px; border-radius: 5px; }}
            .query-header h2 {{ margin: 0 0 10px 0; color: #2c3e50; }}
            .status {{ padding: 4px 8px; border-radius: 3px; font-weight: bold; font-size: 10px; display: inline-block; }}
            .status-completed {{ background: #d4edda; color: #155724; }}
            .status-pending {{ background: #fff3cd; color: #856404; }}
            .status-processing {{ background: #cce7ff; color: #004085; }}
            .status-failed {{ background: #f8d7da; color: #721c24; }}
            .timestamp {{ color: #666; font-size: 10px; margin-top: 5px; }}
            .query {{ background: #fff3cd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .response {{ padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
            h3 {{ color: #417690; margin-top: 20px; }}
            pre {{ background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-wrap: break-word; }}
        </style>
    </head>
    <body>
        <h1>Bulk Query Report</h1>
        <p style="color: #666;">Generated on: {queryset.first().created_at.strftime('%Y-%m-%d %H:%M:%S') if queryset.first() else 'N/A'} | Total Queries: {queryset.count()}</p>
        {''.join(html_parts)}
    </body>
    </html>
    """
    
    pdf_file = HTML(string=combined_html).write_pdf()
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="bulk_queries_{queryset.count()}_reports.pdf"'
    return response

# Add the bulk action to the admin
QueryUserAdmin.actions = [download_selected_queries_as_pdf]



from .models import TestingQuery

@admin.register(TestingQuery)
class TestingQueryAdmin(admin.ModelAdmin):


    list_display = (
        "id",
        "user_name",
        "query_status",
        "query_preview",
    )
    list_filter = ("query_status", "user_name")
    search_fields = ("query", "user_name", "issues", "expected_response", "actual_response")

    def query_preview(self, obj):
        return obj.query[:75] + "..." if len(obj.query) > 75 else obj.query
    query_preview.short_description = "Query"



@admin.register(TransformedData)
class TransformedDataAdmin(admin.ModelAdmin):
    list_display = (
        'company', 'metric_name', 'year', 'table_name',
        'value', 'significance', 'data_type'
    )
    list_filter = ('metric_name', 'year','company')
    search_fields = ('metric_name', 'year','company')
    ordering = ( 'metric_name', 'year')
