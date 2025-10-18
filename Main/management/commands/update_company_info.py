from django.core.management.base import BaseCommand
from Main.models import Company
import yfinance as yf
import time
from datetime import datetime

class Command(BaseCommand):
    help = 'Update sector and industry info for existing companies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--slug',
            type=str,
            help='Update specific company by slug'
        )

    def handle(self, *args, **options):
        if options['slug']:
            companies = Company.objects.filter(slug=options['slug'])
        else:
            companies = Company.objects.filter(is_active=True)
        
        total = companies.count()
        updated = 0
        failed = 0
        
        self.stdout.write(f'Updating {total} companies...\n')
        
        for idx, company in enumerate(companies, 1):
            try:
                # Try NSE first, then BSE
                stock = None
                for suffix in ['.NS', '.BO']:
                    try:
                        stock = yf.Ticker(f"{company.slug}{suffix}")
                        info = stock.info
                        if info and len(info) > 5:
                            break
                    except:
                        continue
                
                if stock and info:
                    company.sector = info.get('sector', company.sector)
                    company.industry = info.get('industry', company.industry)
                    company.about_company = info.get('longBusinessSummary', company.about_company)
                    company.name = info.get('longName', company.name)
                    company.last_scraped = datetime.now()
                    company.save()
                    
                    updated += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[{idx}/{total}] ✓ Updated {company.slug}: {company.sector or "No sector"}'
                        )
                    )
                else:
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(f'[{idx}/{total}] ⚠ No data for {company.slug}')
                    )
                
                time.sleep(0.3)
                
            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f'[{idx}/{total}] ✗ Failed {company.slug}: {str(e)}')
                )
        
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Updated: {updated}'))
        self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
        self.stdout.write('='*50)