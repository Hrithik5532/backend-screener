from langchain_core.tools import tool
from typing import Dict, Any, Optional
from datetime import datetime
import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger(__name__)

@tool
def get_indian_stock_info(
    company: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    info_type: str = "price",
    exchange: str = "NSE"
) -> Dict[str, Any]:
    """
    Fetch stock price and company information for Indian companies.
    
    Args:
        company: Stock ticker symbol (e.g., 'ULTRACEMCO', 'TCS', 'RELIANCE', 'INFY')
        start_date: Start date in format 'YYYY-MM-DD'. Defaults to 1 year ago.
        end_date: End date in format 'YYYY-MM-DD'. Defaults to today.
        info_type: Type of data to retrieve:
            - 'price': Historical price data
            - 'summary': Current price and key metrics
            - 'full': Complete company info and current metrics
            - 'all': Everything (price data + full info)
        exchange: Indian stock exchange ('NSE' or 'BSE'). Defaults to NSE.
    
    Returns:
        Dictionary with requested stock information for Indian stocks
    """
    try:
        # Normalize ticker symbol
        ticker_symbol = company.upper().strip()
        
        # Add exchange suffix
        if exchange.upper() == "NSE":
            ticker_symbol = f"{ticker_symbol}.NS"
        elif exchange.upper() == "BSE":
            ticker_symbol = f"{ticker_symbol}.BO"
        else:
            return {
                'error': f"Invalid exchange: {exchange}. Use 'NSE' or 'BSE'",
                'ticker': company.upper()
            }
        
        logger.info(f"Fetching Indian stock: {ticker_symbol}")
        
        # Create ticker object
        ticker = yf.Ticker(ticker_symbol)
        
        # Set default dates
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if start_date is None:
            start_date = (pd.Timestamp(end_date) - pd.DateOffset(years=1)).strftime('%Y-%m-%d')
        
        logger.info(f"Date range: {start_date} to {end_date}")
        
        result = {
            'ticker': ticker_symbol,
            'company': company.upper(),
            'exchange': exchange.upper(),
            'period': {'start': start_date, 'end': end_date}
        }
        
        # Get historical price data
        if info_type in ['price', 'all']:
            logger.info("Fetching historical price data...")
            hist = ticker.history(start=start_date, end=end_date)
            
            logger.info(f"Retrieved {len(hist)} trading records")
            
            if not hist.empty:
                result['price_data'] = {
                    'latest': {
                        'date': hist.index[-1].strftime('%Y-%m-%d'),
                        'open': float(hist.iloc[-1]['Open']) if pd.notna(hist.iloc[-1]['Open']) else None,
                        'close': float(hist.iloc[-1]['Close']) if pd.notna(hist.iloc[-1]['Close']) else None,
                        'high': float(hist.iloc[-1]['High']) if pd.notna(hist.iloc[-1]['High']) else None,
                        'low': float(hist.iloc[-1]['Low']) if pd.notna(hist.iloc[-1]['Low']) else None,
                        'volume': int(hist.iloc[-1]['Volume']) if pd.notna(hist.iloc[-1]['Volume']) else None,
                    },
                    'period_statistics': {
                        'min_price': float(hist['Close'].min()),
                        'max_price': float(hist['Close'].max()),
                        'average_price': float(hist['Close'].mean()),
                        'total_trading_days': len(hist),
                        'price_change': float(hist.iloc[-1]['Close'] - hist.iloc[0]['Close']),
                        'price_change_percent': float(((hist.iloc[-1]['Close'] - hist.iloc[0]['Close']) / hist.iloc[0]['Close']) * 100)
                    }
                }
            else:
                logger.warning(f"No historical data found for {ticker_symbol}")
                result['price_data'] = {'error': 'No historical data found for this period'}
        
        # Get current info and metrics
        if info_type in ['summary', 'full', 'all']:
            logger.info("Fetching company info...")
            try:
                info = ticker.info
                
                if info:
                    result['company_info'] = {
                        'name': info.get('longName', 'N/A'),
                        'sector': info.get('sector', 'N/A'),
                        'industry': info.get('industry', 'N/A'),
                        'website': info.get('website', 'N/A'),
                        'description': (info.get('longBusinessSummary', 'N/A')[:300] + '...')
                            if info.get('longBusinessSummary') else 'N/A'
                    }
                    
                    result['current_metrics'] = {
                        'current_price': info.get('currentPrice', 'N/A'),
                        'market_cap': info.get('marketCap', 'N/A'),
                        'pe_ratio': info.get('trailingPE', 'N/A'),
                        'dividend_yield': info.get('dividendYield', 'N/A'),
                        '52_week_high': info.get('fiftyTwoWeekHigh', 'N/A'),
                        '52_week_low': info.get('fiftyTwoWeekLow', 'N/A'),
                        '52_week_change': info.get('52WeekChange', 'N/A'),
                        'eps': info.get('trailingEps', 'N/A'),
                        'book_value': info.get('bookValue', 'N/A'),
                    }
                else:
                    logger.warning("No info available for ticker")
                    result['company_info'] = {'error': 'Company info not available'}
            except Exception as info_error:
                logger.warning(f"Error fetching company info: {info_error}")
                result['company_info'] = {'error': 'Could not fetch company info'}
        
        logger.info(f"Successfully fetched data for {ticker_symbol}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to fetch data for {company}: {str(e)}", exc_info=True)
        return {
            'error': f"Failed to fetch data for {company}: {str(e)}",
            'ticker': company.upper(),
            'note': 'Make sure you use valid Indian company ticker symbols (e.g., ULTRACEMCO, TCS, RELIANCE, INFY)'
        }