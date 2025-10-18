"""
Data Retriever as LangChain Tool - Using existing SQLAlchemy functions
"""

from typing import Dict, Any, List, Optional
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
import asyncio
import logging
from dotenv import load_dotenv
from collections import defaultdict

import os
load_dotenv()
# logger = logging.getLogger(__name__)
from langchain_core.tools import tool

# Import your existing data retrieval functions
from django.shortcuts import get_object_or_404
from Main.models import Company,FinancialDataTable,KeyFinancialMetric

def fetch_tables_for_company(company, table_name, data_type):
    """
    Fetch financial tables for a company directly from Django models
    """
    logging.info(f"=== FETCH_TABLES_FOR_COMPANY CALLED ===")
    logging.info(f"Input params - company: {company}, table_name: {table_name}, data_type: {data_type}")
    
    try:
        company_obj = get_object_or_404(Company, slug=company)
        logging.info(f"Company object retrieved: {company_obj}")
        
        # NORMALIZE data_type to lowercase to match database values
        data_type_normalized = data_type.lower()
        logging.info(f"Normalized data_type: {data_type_normalized}")
        
        table = FinancialDataTable.objects.get(
            company=company_obj,
            table_type=table_name,
            data_type=data_type_normalized,  # Use normalized value
            is_active=True
        )
        logging.info(f"Table retrieved: {table}")

        metrics = KeyFinancialMetric.objects.filter(
            source_table=table
        ).values_list('metric_name').distinct()
        
        metrics_list = list(metrics)
        logging.info(f"Metrics count: {len(metrics_list)}")
    

        return metrics_list
        
    except Exception as e:
        logging.error(f"=== ERROR IN FETCH_TABLES_FOR_COMPANY ===")
        logging.error(f"Error type: {type(e).__name__}")
        logging.error(f"Error message: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return []




class MetricsQueryInput(BaseModel):
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

# class DataRetrieverTool:
#     """Handles financial data retrieval operations"""
@tool    
def retrieve_metrics(
        table_name: str,
        company: str,
        metric: str,
        data_type: str ,
        period_type: str ,
        period: str

    ) -> Dict[str, Any]:
        """
        Retrieve financial metrics for a company
        
        Args:
            table_name: Financial table name
            company: Company identifier
            metric: Metric name to retrieve
            data_type: Consolidated/Standalone
            period_type: Quarterly/Yearly
            period: Time period (e.g., 'Q1 2024')
        
        Returns:
            Dictionary with retrieval results
        """
        
        try:
            # Fetch table info using existing function
            logging.info("Fetching table info...")
            logging.info("Company: %s | Table: %s | Data type: %s | Period: %s | Period type: %s | Metric: %s",
             company, table_name, data_type, period, period_type, metric)
            # tool_logger = ToolLogger()
            # tool_logger.start("retrieve_financial_metrics")
            available_metrics = fetch_tables_for_company(company,table_name,data_type)
             
            
            logging.info("Table info fetched.")          
            
            
            
            # Use the retrieval LLM
            from Main.agents.tools.llms.retrieval import DataRetriever as CutilsDataRetriever
            analyzer = CutilsDataRetriever()
            logging.info("Calling Retrieval LLM...")
            logging.info(f"Available metrics in table: {available_metrics}")

            retrieval_response = analyzer.RetrievalLLM(
                    metrics=metric,
                    company_slug=company,
                    table_structures={
                        "table_name": table_name,
                        "metrics_list": available_metrics,
                    }
                )
            logging.info("!!!!!!!!")
            logging.info(retrieval_response)
           
            retrieval_result = retrieval_response.get('retrieval_parameter', {})
            
            # Normalize results
            if retrieval_result.get("valid_metric_name") in [None, [None], [], ["None"]]:
                    retrieval_result["retrieval_status"] = False

            logging.info("Retrieval successful.")

            final_result = {
                "table_name": table_name,
                "company": company,
                "metric": metric,
                "data_type": data_type,
                "period_type": period_type,
                "valid_metric_name": retrieval_result["valid_metric_name"],
                "period": period,
                "retrieval_status": retrieval_result.get("retrieval_status", False),
                "reasoning": retrieval_result.get("reasoning", ""),
                "token_usage": retrieval_response.get("token_usage", {}),
                "processing_time_seconds": retrieval_response.get("processing_time_seconds", 0)
            }
            logging.info(f"Final Result for SQL: {final_result}")

            # tool_logger.log_interaction(
            #     tool_name="retrieve_financial_metrics",
            #     input_data={
            #         "table_name": table_name,
            #         "company": company,
            #         "metric": metric,
            #         "data_type": data_type,
            #         "significance": significance,   
            #         "period": period
            #     },
            #     output_data=final_result,
            #     success=True
            # )
            return final_result

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Request timed out. Please try again.",
                "data": []
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error retrieving data: {str(e)}",
                "data": []
            }


