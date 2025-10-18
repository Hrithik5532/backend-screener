from django.core.management.base import BaseCommand
from Main.models import Company
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import pandas as pd

class Command(BaseCommand):
    help = 'Fetch all NSE/BSE listed companies and populate database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--exchange',
            type=str,
            default='NSE',
            help='Exchange to fetch from (NSE or BSE)'
        )

    def get_nse_company_list(self):
        """Get all NSE listed companies"""
        try:
            self.stdout.write('Fetching NSE company list...')
            
            # NSE equity list
            url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            df = pd.read_csv(url)
            
            # Extract symbol and name
            companies = []
            for _, row in df.iterrows():
                companies.append({
                    'symbol': row['SYMBOL'].strip(),
                    'name': row['NAME OF COMPANY'].strip()
                })
            
            self.stdout.write(self.style.SUCCESS(f'Found {len(companies)} NSE companies'))
            return companies
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error fetching NSE list: {str(e)}'))
            return []

    def get_bse_company_list(self):
        """Get all BSE listed companies"""
        try:
            self.stdout.write('Fetching BSE company list...')
            
            # BSE equity list
            url = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active"
            
            response = requests.get(url, timeout=30)
            data = response.json()
            
            companies = []
            for item in data.get('Table', []):
                companies.append({
                    'symbol': item.get('scrip_cd', ''),
                    'name': item.get('scrip_name', '')
                })
            
            self.stdout.write(self.style.SUCCESS(f'Found {len(companies)} BSE companies'))
            return companies
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error fetching BSE list: {str(e)}'))
            return []

    def fetch_company_details(self, symbol, name, exchange='NSE'):
        """Fetch detailed company info from Yahoo Finance"""
        try:
            # Add exchange suffix
            ticker_symbol = f"{symbol}.NS" if exchange == 'NSE' else f"{symbol}.BO"
            
            stock = yf.Ticker(ticker_symbol)
            info = stock.info
            
            if not info or len(info) < 5:  # Basic validation
                return None
            
            return {
                'slug': symbol,
                'name': name or info.get('longName', ''),
                'sector': info.get('sector', None),
                'industry': info.get('industry', None),
                'about_company': info.get('longBusinessSummary', None),
                'is_active': True,
                'last_scraped': datetime.now()
            }
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Could not fetch {symbol}: {str(e)}'))
            return None

    def handle(self, *args, **options):
        exchange = options['exchange'].upper()
        
        # Get company list
        if exchange == 'NSE':
            company_list = self.get_nse_company_list()
        elif exchange == 'BSE':
            company_list = self.get_bse_company_list()
        else:
            self.stdout.write(self.style.ERROR('Invalid exchange. Use NSE or BSE'))
            return
        
        if not company_list:
            self.stdout.write(self.style.ERROR('No companies found'))
            return
        
        total = len(company_list)
        created = 0
        updated = 0
        failed = 0
        
        self.stdout.write(f'\nProcessing {total} companies...\n')
        
        for idx, company_data in enumerate(company_list, 1):
            symbol = company_data['symbol']
            name = company_data['name']
            
            try:
                # Fetch detailed info
                details = self.fetch_company_details(symbol, name, exchange)
                
                if details:
                    # Create or update company
                    company, is_created = Company.objects.update_or_create(
                        slug=symbol,
                        defaults=details
                    )
                    
                    if is_created:
                        created += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'[{idx}/{total}] ✓ Created {symbol}: {details.get("sector", "Unknown")}')
                        )
                    else:
                        updated += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'[{idx}/{total}] ↻ Updated {symbol}: {details.get("sector", "Unknown")}')
                        )
                else:
                    failed += 1
                    # Still create basic entry
                    Company.objects.update_or_create(
                        slug=symbol,
                        defaults={
                            'name': name,
                            'is_active': True,
                            'last_scraped': datetime.now()
                        }
                    )
                    self.stdout.write(
                        self.style.WARNING(f'[{idx}/{total}] ⚠ Basic entry for {symbol}')
                    )
                
                # Rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f'[{idx}/{total}] ✗ Failed {symbol}: {str(e)}')
                )
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Completed!'))
        self.stdout.write(f'Total: {total}')
        self.stdout.write(self.style.SUCCESS(f'Created: {created}'))
        self.stdout.write(self.style.SUCCESS(f'Updated: {updated}'))
        self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
        self.stdout.write('='*50)