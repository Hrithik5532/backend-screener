# Main/models.py - UPDATED WITH LARGER FIELD SIZES
from django.db import models
import uuid
from datetime import datetime

class Company(models.Model):
    """Detailed company profile with financial summary - UPDATED FIELD SIZES"""

    # Basic identifiers
    slug = models.CharField(max_length=50, unique=True, db_index=True, help_text="Company code like ULTRACEMCO")
    name = models.CharField(max_length=200, help_text="Full company_name",null=True, blank=True)
    

    # Category info
    sector = models.CharField(max_length=100, null=True, blank=True)
    industry = models.CharField(max_length=100, null=True, blank=True)

    # Descriptions
    about_company = models.TextField(null=True, blank=True)
    key_points = models.TextField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_scraped = models.DateTimeField(null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'companies'
        verbose_name_plural = 'Companies'

    def __str__(self):
        return f"{self.slug}"


# Rest of your models remain the same...
class FinancialDataTable(models.Model):
    """
    Stores dynamic financial tables with any structure
    Each table can have different columns and rows - completely flexible
    """
    
    # Table Types based on your PDF
    TABLE_TYPES = [
        ('balance-sheet', 'Balance Sheet'),
        ('profit-loss', 'Profit & Loss'),
        ('cash-flow', 'Cash Flow'),
        ('quarters', 'Quarterly Results'),
        ('ratios', 'Financial Ratios'),
        ('peers', 'Peer Comparison'),
        ('shareholding', 'Shareholding Pattern'),
        ('company-info','Company Info')
    ]
    
    # Data presentation types
    DATA_TYPES = [
        ('consolidated', 'Consolidated'),
        ('standalone', 'Standalone'), 
    ]
    
    # Identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='financial_tables')
    
    # Table classification
    table_type = models.CharField(max_length=50, choices=TABLE_TYPES, db_index=True)
    data_type = models.CharField(max_length=20, choices=DATA_TYPES, default='default', db_index=True)
    
    # Table structure - completely dynamic
    column_headers = models.JSONField(
        default=list, 
        help_text="List of column headers like ['Mar 2014', 'Mar 2015', 'Mar 2016', ...]"
    )
    
    # Table data - array of rows, each row is array of cells
    table_data = models.JSONField(
        default=list,
        help_text="Array of rows: [['Row Header', 'Cell1', 'Cell2', ...], [...]]"
    )
    
    # Metadata about the table
    total_columns = models.IntegerField(default=0, help_text="Number of columns in table")
    total_rows = models.IntegerField(default=0, help_text="Number of rows in table") 
    
    # Additional table info
    table_title = models.CharField(max_length=200, null=True, blank=True, help_text="Title of the table section")
    notes = models.TextField(null=True, blank=True, help_text="Any additional notes or context")
    
    # Timestamps
    scraped_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'financial_data_tables'
        unique_together = ['company', 'table_type', 'data_type']
        indexes = [
            models.Index(fields=['company', 'table_type', 'data_type']),
            models.Index(fields=['table_type', 'scraped_at']),
            models.Index(fields=['company', 'scraped_at']),
        ]
        ordering = ['-scraped_at']
    
    def __str__(self):
        return f"{self.company.slug} - {self.get_table_type_display()} ({self.get_data_type_display()})"
    
    def save(self, *args, **kwargs):
        """Auto-calculate table dimensions"""
        if self.table_data:
            self.total_rows = len(self.table_data)
            if self.table_data and isinstance(self.table_data[0], list):
                self.total_columns = len(self.table_data[0])
        if self.column_headers:
            self.total_columns = max(self.total_columns, len(self.column_headers))
        super().save(*args, **kwargs)
    
    def get_data_preview(self):
        """Get a preview of the table data"""
        if not self.table_data:
            return "No data"
        
        preview = []
        # Show first 3 rows
        for i, row in enumerate(self.table_data[:3]):
            if isinstance(row, list) and len(row) > 0:
                # Show first few cells of each row
                row_preview = row[:4]  # First 4 columns
                if len(row) > 4:
                    row_preview.append("...")
                preview.append(row_preview)
        
        if len(self.table_data) > 3:
            preview.append(["..."])
            
        return preview


class KeyFinancialMetric(models.Model):
    """
    Stores individual financial metrics/ratios extracted from tables
    This makes it easier to query specific metrics across companies
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='key_metrics')
    source_table = models.ForeignKey(FinancialDataTable, on_delete=models.CASCADE, related_name='extracted_metrics')
    
    # Metric details
    metric_name = models.CharField(max_length=150, db_index=True, help_text="Name of the metric like 'Sales', 'Net Profit', 'ROCE %'")
    metric_category = models.CharField(max_length=100, null=True, blank=True, help_text="Category like 'Revenue', 'Profitability', 'Ratios'")
    
    # Time period this metric belongs to
    period = models.CharField(max_length=50, help_text="Time period like 'Mar 2025', 'Q1 2025', 'TTM'")
    period_type = models.CharField(max_length=20, choices=[
        ('annual', 'Annual'),
        ('quarterly', 'Quarterly'),
        ('ttm', 'TTM'),
        ('other','Other')
    ], default='annual')
    
    # Value storage - INCREASED PRECISION
    raw_value = models.CharField(max_length=100, help_text="Original value as scraped")
    numeric_value = models.DecimalField(max_digits=25, decimal_places=4, null=True, blank=True, help_text="Numeric value if parseable")
    unit = models.CharField(max_length=20, null=True, blank=True, help_text="Unit like %, ₹, Cr., times")
    
    # Position in source table
    row_index = models.IntegerField(help_text="Row position in source table")
    column_index = models.IntegerField(help_text="Column position in source table")
    
    # Timestamps
    extracted_at = models.DateTimeField(auto_now_add=True)

    # Self-referential parent relation
    parent_relation = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children"
    )

    class Meta:
        db_table = 'key_financial_metrics'
        unique_together = ['company', 'metric_name', 'period', 'source_table']
        indexes = [
            models.Index(fields=['company', 'metric_name', 'period']),
            models.Index(fields=['metric_name', 'period']),
            models.Index(fields=['company', 'period_type']),
        ]
    
    def __str__(self):
        return f"{self.company.slug} - {self.metric_name} ({self.period}): {self.raw_value}"


# Rest of models remain the same...
class TableDataHistory(models.Model):
    """
    Archive of old table data when tables are updated
    Keeps historical versions of financial data
    """
    original_table = models.ForeignKey(FinancialDataTable, on_delete=models.CASCADE, related_name='history')
    
    # Archived data
    archived_column_headers = models.JSONField()
    archived_table_data = models.JSONField()
    archived_total_columns = models.IntegerField()
    archived_total_rows = models.IntegerField()
    
    # Archive metadata
    archived_at = models.DateTimeField(auto_now_add=True)
    original_scraped_at = models.DateTimeField()
    archive_reason = models.CharField(max_length=100, default="Data Update")
    
    class Meta:
        db_table = 'table_data_history'
        ordering = ['-archived_at']
    
    def __str__(self):
        return f"Archive of {self.original_table} - {self.archived_at.strftime('%Y-%m-%d %H:%M')}"


class ScrapingSession(models.Model):
    """
    Tracks each scraping session - when scraper runs for companies
    """
    
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
    ]
    
    # Session info
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    companies_targeted = models.JSONField(help_text="List of company slugs to scrape")
    table_types_targeted = models.JSONField(help_text="List of table types to scrape")
    
    # Status tracking  
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    
    # Results
    companies_completed = models.JSONField(default=list, help_text="Companies successfully scraped")
    companies_failed = models.JSONField(default=list, help_text="Companies that failed")
    tables_created = models.IntegerField(default=0)
    metrics_extracted = models.IntegerField(default=0)
    
    # Error tracking
    error_log = models.TextField(null=True, blank=True)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'scraping_sessions'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Scraping Session {self.session_id.hex[:8]} - {self.status} ({self.started_at.strftime('%Y-%m-%d %H:%M')})"
    
    def mark_completed(self):
        """Mark session as completed and calculate duration"""
        self.completed_at = datetime.now()
        self.status = 'completed'
        if self.started_at and self.completed_at:
            duration = self.completed_at - self.started_at
            self.duration_minutes = int(duration.total_seconds / 60)
        self.save()


class StockPriceHistory(models.Model):
    """
    Historical stock prices for companies
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stock_price_history')
    
    # Price details
    date = models.DateField(db_index=True)
    price = models.DecimalField(max_digits=15, decimal_places=2, help_text="Closing stock price on this date")
    
    class Meta:
        db_table = 'stock_price_history'
        unique_together = ['company', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.company.slug} - {self.date} Prices"



class QueryUser(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    uid = models.UUIDField(default=uuid.uuid4, editable=False)
    query = models.TextField(help_text="query")
    user_name = models.CharField(max_length=50, null=True, blank=True)
    table_fetched = models.TextField(null=True,blank=True)
    # Processing info
    task_id = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    response = models.TextField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.query[:50]}... ({self.status})"

    class Meta:
        ordering = ['-created_at']




class TestingQuery(models.Model):
    query = models.TextField()
    user_name = models.CharField(max_length=30)
    actual_response = models.TextField()
    expected_response = models.TextField()
    query_status = models.CharField(max_length=30)
    issues = models.TextField(blank=True,null=True)





class Companies2(models.Model):
    id = models.UUIDField(primary_key=True)
    slug = models.CharField(unique=True, max_length=50)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    last_scraped = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField()
    about_company = models.TextField(blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True)
    key_points = models.TextField(blank=True, null=True)
    name = models.CharField(max_length=200, blank=True, null=True)
    sector = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'companies_2'


class FinancialDataTables2(models.Model):
    id = models.UUIDField(primary_key=True)
    table_type = models.CharField(max_length=50)
    data_type = models.CharField(max_length=20)
    column_headers = models.JSONField()
    table_data = models.JSONField()
    total_columns = models.IntegerField()
    total_rows = models.IntegerField()
    table_title = models.CharField(max_length=200, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    scraped_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    is_active = models.BooleanField()
    company = models.ForeignKey(Companies2, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'financial_data_tables_2'
        unique_together = (('company', 'table_type', 'data_type'),)


class KeyFinancialMetrics2(models.Model):
    metric_name = models.TextField(blank=True, null=True)
    metric_category = models.TextField(blank=True, null=True)
    period = models.TextField(blank=True, null=True)
    period_type = models.TextField(blank=True, null=True)
    notes = models.TextField(db_column='Notes', blank=True, null=True)  
    raw_value = models.FloatField(blank=True, null=True)
    numeric_value = models.FloatField(blank=True, null=True)
    unit = models.TextField(blank=True, null=True)
    row_index = models.BigIntegerField(blank=True, null=True)
    column_index = models.BigIntegerField(blank=True, null=True)
    extracted_at = models.TextField(blank=True, null=True)
    company_id = models.TextField(blank=True, null=True)
    source_table_id = models.TextField(blank=True, null=True)
    parent_relation_id = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'key_financial_metrics_2'




class TransformedData(models.Model):
    company  = models.CharField(max_length=100)
    year = models.CharField(max_length=100)
    table_name = models.CharField(max_length=100)
    metric_name = models.CharField(max_length=100)
    significance = models.CharField(max_length=100)
    data_type = models.CharField(max_length=100)
    value = models.CharField(max_length=500)

    class Meta:
        db_table = 'transformed_data'
        # managed = True  <- remove managed = False

