"""
Simplified async data retrieval using SQLAlchemy with proper multiprocessing support
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, String
import logging
from sqlalchemy import func
from urllib.parse import quote_plus
from contextlib import asynccontextmanager
import asyncio
import os


# SQLAlchemy setup
Base = declarative_base()

class TransformedData(Base):
    __tablename__ = 'transformed_data'
    
    id = Column(String, primary_key=True)
    company = Column(String)
    year = Column(String)
    table_name = Column(String)
    metric_name = Column(String)
    significance = Column(String)
    data_type = Column(String)
    value = Column(String)


# Global variables for lazy initialization
_engine: Optional[AsyncEngine] = None
_async_session_maker = None
_current_pid = None  # Track which process created the engine


def _reset_engine():
    """Reset engine if we're in a different process"""
    global _engine, _async_session_maker, _current_pid
    current_pid = os.getpid()
    
    if _current_pid != current_pid:
        # We're in a new process, reset everything
        _engine = None
        _async_session_maker = None
        _current_pid = current_pid


def get_engine() -> AsyncEngine:
    """Lazy initialization of engine - creates one per process"""
    global _engine, _current_pid
    
    _reset_engine()
    
    if _engine is None:
        password = quote_plus("sky@#!123")
        DATABASE_URL = f"postgresql+asyncpg://screeneradmin:{password}@52.22.136.221:5432/screenerdb"
        _engine = create_async_engine(
            DATABASE_URL, 
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            poolclass=None,  # Use NullPool to avoid connection pool issues in forked processes
        )
    return _engine


def get_session_maker():
    """Lazy initialization of session maker"""
    global _async_session_maker
    
    _reset_engine()
    
    if _async_session_maker is None:
        _async_session_maker = sessionmaker(
            get_engine(), 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    return _async_session_maker


@asynccontextmanager
async def get_session():
    """Context manager for database sessions with proper cleanup"""
    session_maker = get_session_maker()
    session = session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_financial_data(coordinates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Retrieve financial data for given coordinates
    
    Args:
        coordinates: List of dicts with: company, table_name, data_type, 
                    metric_name (or metrics), period (or columns), significance (optional)
    
    Returns:
        Dict with retrieved_data and summary
    """
    logging.info("Fetching financial data")

    if not coordinates:
        return {'retrieved_data': [], 'summary': {'total': 0, 'success': 0}}
    
    results = {'retrieved_data': [], 'summary': {'total': len(coordinates), 'success': 0}}
    
    try:
        async with get_session() as session:
            for coord in coordinates:
                # Parse input
                company = coord.get('company')
                table_name = coord.get('table_name')
                data_type = coord.get('data_type')
                significance = coord.get('significance')
                
                metrics = ([coord['metric_name']] if 'metric_name' in coord 
                          else coord.get('metrics', []))
                periods = ([coord['period']] if 'period' in coord 
                          else coord.get('columns', []))
                
                if not all([company, table_name, data_type, metrics, periods]):
                    continue
                
                # Build query
                filters = [
                    func.lower(func.trim(TransformedData.company)) == company.lower().strip(),
                    func.lower(func.trim(TransformedData.table_name)) == table_name.lower().strip(),
                    func.lower(func.trim(TransformedData.data_type)) == data_type.lower().strip(),
                    func.lower(func.trim(TransformedData.metric_name)).in_([m.lower().strip() for m in metrics]),
                    func.lower(func.trim(TransformedData.year)).in_([p.lower().strip() for p in periods])
                ]

                if significance:
                    filters.append(func.lower(func.trim(TransformedData.significance)) == significance.lower().strip())
                
                # Execute query
                stmt = select(TransformedData).where(and_(*filters))
                result = await session.execute(stmt)
                rows = result.scalars().all()
                
                if not rows:
                    continue
                
                # Organize data
                data_matrix = {}
                for row in rows:
                    if row.metric_name not in data_matrix:
                        data_matrix[row.metric_name] = {}
                    
                    data_matrix[row.metric_name][row.year] = {
                        'value': row.value,
                        'numeric_value': _to_float(row.value),
                        'significance': row.significance,
                        'data_type': row.data_type
                    }
                
                results['retrieved_data'].append({
                    'company': company,
                    'table_name': table_name,
                    'data_type': data_type,
                    'significance': significance,
                    'data': data_matrix
                })
                results['summary']['success'] += 1
    finally:
        # Clean up engine after each call to prevent connection leaks
        await cleanup_engine()
    
    print("#######", results)
    return results


def _to_float(value: str) -> float:
    """Convert string to float, return None if invalid"""
    if not value:
        return None
    try:
        return float(value.replace(',', ''))
    except (ValueError, AttributeError):
        return None
    

async def fetch_tables_for_company(company_slug: str) -> Dict[str, Any]:
    """
    Fetch financial tables metadata for a company using SQLAlchemy
    """
    print("Fetching tables for company")
    logging.info("Fetching tables for company")
    
    try:
        async with get_session() as session:
            # Get distinct tables
            stmt = select(TransformedData.table_name).where(
                TransformedData.company == company_slug
            ).distinct()
            result = await session.execute(stmt)
            tables = [row[0] for row in result.all()]
            
            if not tables:
                return {
                    'company': company_slug,
                    'message': 'No financial data available for this company',
                    'overview': []
                }
            
            # Get metrics and periods for each table
            overview = []
            for table in tables:
                stmt = select(
                    TransformedData.metric_name,
                    TransformedData.year
                ).where(
                    and_(
                        TransformedData.company == company_slug,
                        TransformedData.table_name == table
                    )
                ).distinct()
                
                result = await session.execute(stmt)
                rows = result.all()
                
                metrics = set()
                periods = set()
                for metric_name, year in rows:
                    metrics.add(metric_name)
                    if year:
                        periods.add(year)
                
                overview.append({
                    'table_name': table,
                    'columns': sorted(list(periods)),
                    'metrics': sorted(list(metrics)),
                    'total_tables': 1
                })
            
            overview.sort(key=lambda x: x['table_name'])
            
            return {
                'company': company_slug,
                'overview': overview,
                'total_combinations': len(overview)
            }
    finally:
        await cleanup_engine()


async def cleanup_engine():
    """Safely cleanup engine and connections"""
    global _engine, _async_session_maker
    
    if _engine:
        try:
            # Dispose of the engine, which closes all connections
            await _engine.dispose()
        except Exception as e:
            logging.warning(f"Error during engine disposal: {e}")
        finally:
            _engine = None
            _async_session_maker = None


async def cleanup():
    """Call this on application shutdown"""
    await cleanup_engine()