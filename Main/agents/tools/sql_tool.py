
"""
Financial Query Analysis Agent using LangGraph ReAct
Uses decomposer tool and retrieval tool
"""

import os
import json
from typing import List, Dict, Any, Optional
from langchain.tools import StructuredTool
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from dotenv import load_dotenv
# from app.agents2.agents.db.data_fetch import get_financial_data
import logging
# from app.agents2.agents.tool_logging import ToolLogger
load_dotenv()
from langchain_core.tools import tool

import logging
from typing import Dict, Any, List, Optional
from django.db.models import Q
from Main.models import Company, FinancialDataTable, KeyFinancialMetric

def get_financial_data(coord: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve financial metric values from the database
    
    Args:
        coord: Dictionary containing:
            - company: Company slug (e.g., 'ULTRACEMCO')
            - table_name: Table type (e.g., 'quarters')
            - metric: Metric name (e.g., 'Sales')
            - period: Time period (e.g., 'March 2025')
            - data_type: 'consolidated' or 'standalone'
            - period_type: 'annual' or 'quarterly'
    
    Returns:
        Dictionary with retrieved data and metadata
    """
    logging.info(f"=== GET_FINANCIAL_DATA CALLED ===")
    logging.info(f"Coordinates: {coord}")
    
    try:
        # Extract parameters
        company_slug = coord.get('company')
        table_name = coord.get('table_name')
        metric = coord.get('metrics')  # This should be the valid_metric_name from retrieval
        period = coord.get('columns')
        data_type = coord.get('data_type', 'Consolidated').lower()
        period_type = coord.get('period_type', 'Annual').lower()
        
        # Validate required parameters
        if not all([company_slug, table_name, metric, period, data_type]):

            return {
                'success': False,
                'error': 'Missing required parameters',
                'retrieved_data': [],
                'summary': {'success': 0, 'failed': 1}
            }
        
        # Get company
        try:
            company = Company.objects.get(slug=company_slug)
            logging.info(f"Company found: {company}")
        except Company.DoesNotExist:
            return {
                'success': False,
                'error': f'Company {company_slug} not found',
                'retrieved_data': [],
                'summary': {'success': 0, 'failed': 1}
            }
        
        # Get financial table
        try:
            source_table = FinancialDataTable.objects.get(
                company=company,
                table_type=table_name,
                data_type=data_type,
                is_active=True
            )
            logging.info(f"Table found: {source_table}")
        except FinancialDataTable.DoesNotExist:
            return {
                'success': False,
                'error': f'Table {table_name} not found for {company_slug}',
                'retrieved_data': [],
                'summary': {'success': 0, 'failed': 1}
            }
        
        # Query for the metric
        query = Q(
            company=company,
            source_table=source_table,
            metric_name=metric,
            period = period,
            period_type = period_type
        )
        
        
        logging.info(f"!!!!!!!!!!!!!!!!!!! {query}")
        # Retrieve metrics
        metric_obj = KeyFinancialMetric.objects.get(
            company = company,
            source_table = source_table,
            metric_name = metric,
            period = period,
        )
            
        # Format results
        retrieved_data = {
                'company': company_slug,
                'metric_name': metric_obj.metric_name,
                'period': metric_obj.period,
                'period_type': metric_obj.period_type,
                'value': metric_obj.raw_value,
                'numeric_value': float(metric_obj.numeric_value) if metric_obj.numeric_value else None,
                'unit': metric_obj.unit,
                'metric_category': metric_obj.metric_category,
                'parent_metric': metric_obj.parent_relation.metric_name if metric_obj.parent_relation else None,
                'table_type': table_name,
                'data_type': data_type
            }
        
        logging.info(f"Retrieved: {metric_obj.metric_name} = {metric_obj.raw_value} {metric_obj.unit or ''}")
        
        # Build response
        result = {
            'success': len(retrieved_data) > 0,
            'retrieved_data': retrieved_data,
            'summary': {
                'success': len(retrieved_data),
                'failed': 0 if retrieved_data else 1,
                'total_requested': 1
            },
            'query_params': coord
        }
        
        logging.info(f"=== DATA RETRIEVAL COMPLETE ===")
        logging.info(f"Retrieved {len(retrieved_data)} data points")
        
        return result
        
    except Exception as e:
        logging.error(f"=== ERROR IN GET_FINANCIAL_DATA ===")
        logging.error(f"Error: {str(e)}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        
        return {
            'success': False,
            'error': str(e),
            'retrieved_data': [],
            'summary': {'success': 0, 'failed': 1}
        }



class FinancialDataInput(BaseModel):
    """Input schema for financial data retrieval"""
    company: str = Field(description="Company name (e.g., 'AB Capital', 'TCS')")
    table_name: str = Field(description="Table name (e.g., 'qbr_data', 'mbr_data')")
    metric: str = Field(description="Metric name (e.g., 'EBITDA')")
    period: str = Field(description="Time period (e.g., 'Q1 2024')")
    data_type: str = Field(
        description="Data type: 'ftm' (for this month), 'ytd' (year to date), 'qtd' (quarter to date)",
        default="ftm"
    )
    significance: Optional[str] = Field(
        description="Significance: 'actual', 'ly' (last year), 'p_b' (projected), 'dev' (deviation)",
        default="actual"
    )


@tool
def get_financial_data_tool(
    company: str,
    table_name: str,
    metric: str,
    period: str,
    data_type: str,
    period_type: str
) -> str:
    """
    Retrieve financial data from database using coordinates.
    
    This tool fetches specific financial metrics for a company from the database.
    Use this after decomposing the user's query to get the actual data values.
    
    Args:
        company: Company name (exact match from decomposition json)
        table_name: Financial table (exact match from decomposition json)
        metric: Metric to retrieve for company (exact match from decomposition json)
        period: Time periods (exact match from decomposition json)
        data_type: Type of data (exact match from decomposition json)
        period_type: Data significance (exact match from decomposition json)
    
    Returns:
        JSON string with retrieved financial data
    """
    try:
        logging.info(f"Retrieving data for {company}: {metric} from {table_name}")
        # tool_logger = ToolLogger()
        # tool_logger.start("get_financial_data")

        # Build coordinate for get_financial_data
        coord = {
            "company": company,
            "table_name": table_name,
            "metrics": metric,
            "columns": period,  # periods mapped to columns
            "data_type": data_type,
            "period_type": period_type
        }
        
        # Call the existing function
        result =  get_financial_data(coord)
        
        logging.info(f"Data retrieval result: {result}")
        # Format the response
        if result['summary']['success'] > 0:
            response = {
                "success": True,
                "company": company,
                "table_name": table_name,
                "data": result['retrieved_data'],
                "message": f"Successfully retrieved data for {company}"
            }
        else:
            response = {
                "success": False,
                "company": company,
                "table_name": table_name,
                "data": [],
                "message": f"No data found for {company} with specified parameters"
            }
        
        # tool_logger.log_interaction(
        #     tool_name="get_financial_data",
        #     input_data=coord,
        #     output_data=response,
        #     success=response.get("success", False)
        # )
        return json.dumps(response, indent=2)
        
    except Exception as e:
        logging.info(f"Error retrieving financial data: {str(e)}")
        error_response = {
            "success": False,
            "error": str(e),
            "company": company,
            "data": []
        }
        return json.dumps(error_response, indent=2)


