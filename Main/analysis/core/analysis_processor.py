
# Main/analysis_processor.py
"""
Core analysis processing logic for financial data
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Callable
from collections import defaultdict
import copy
import gc
from django.db.models import Q
import json

from django.shortcuts import get_object_or_404
from asgiref.sync import sync_to_async

from ...monitoring.error_handling import (
    AnalysisError, 
    AnalysisErrorType, 
    RecursionTracker,
 
)
from ...models import Company, FinancialDataTable, KeyFinancialMetric, TransformedData
from ...monitoring.llm_usage_tracker import (
    llm_usage_tracker as llm_usage_tracker,
    LLMType,
    enhanced_log_usage_summary as log_usage_summary
)

from .retrievel_processor import DataRetrieverMain
from Main.analysis.formulas.formula_processor import FormulaProcessor
logger = logging.getLogger(__name__)



class FinancialAnalysisProcessor:
    """
    Main processor for financial analysis operations
    """
    
    def __init__(self, max_recursion_depth: int = 3):
        self.recursion_tracker = RecursionTracker(max_depth=max_recursion_depth)
        self.data_retriever = DataRetrieverMain()
        self.formula_processor = FormulaProcessor()

    
    async def process_company_queries(
        self,
        available_queries: List[Dict],
        unique_metrics: List[str],
        get_company_tables_func,
        get_data_func,
        recursion_depth: int = 0,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Process queries for a company with optimized parallel processing
        """
        

        try:

            def transform_for_retrieval(data):
                result = {}
                for item in data:
                    table = item["table_name"]
                    metric = item["metric_name"]
                    company_slug = item["company"]
                    key = f"{table}_{company_slug}"

                    if key not in result:
                        result[key] = {
                            "table_name": table,
                            "company": company_slug,
                            "metrics": set()   # set avoids duplicates
                        }

                    result[key]["metrics"].add(metric)

                # Convert sets -> lists
                final_result = {}
                for key, value in result.items():
                    final_result[key] = {
                        "table_name": value["table_name"],
                        "company": value["company"],
                        "metrics": sorted(list(value["metrics"]))
                    }

                return final_result   # wrapped in list

            available_queries_temp = copy.deepcopy(available_queries)
            mapped_metrics = transform_for_retrieval(available_queries_temp)
            logger.info(f"Mapped Metrics for Retrieval: {mapped_metrics}")
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def controlled_retrieval(metrics_json):
                async with semaphore:
                    return await self.data_retriever.retrieve_with_retry(metrics_json)

            
            # Process retrievals
            retrieval_tasks = [controlled_retrieval(mapped_metrics[metrics_json]) for metrics_json in list(mapped_metrics.keys())]
            all_retrieval_result = await asyncio.gather(*retrieval_tasks, return_exceptions=True)
            
            # Handle exceptions in results
            processed_results = []
            for results in all_retrieval_result:
                for item in results:
                    for query in available_queries_temp:
                        if item['metric_name'] == query['metric_name'] and item['company'] == query['company']:
                            query['metrics'] = item['metrics']
                            query['columns'] = [query['period']]
                            query['retrieval_status'] = item['retrieval_status']
                            query['table_type'] = query['data_type']
                            processed_results.append(query)


            logger.info(" !!!!"*50)

            logger.info(f"{processed_results}")

            # Step 4: Identify metrics needing formula calculation
            calculation_metrics = self._identify_calculation_metrics(processed_results)
  
            logger.info(f"Metrics needing formula calculation: {calculation_metrics}")
            # Step 5: Process successful retrievals
            final_results = await self._process_successful_retrievals(
                processed_results, get_data_func
            )
            logger.info(f"Final results after successful retrievals: {final_results}")

            return final_results
            
        except Exception as e:
            logger.error(f"Unexpected error in optimized analysis: {e}")
            error = AnalysisError(
                error_type=AnalysisErrorType.GENERAL_ERROR,
                message=f"Unexpected error in analysis: {str(e)}",
                metric_name=str(unique_metrics),
                company_slug="multiple",
                original_exception=e
            )
            return [{"error": error, "unique_metrics": unique_metrics}]
        
        finally:
            # Cleanup to prevent memory leaks
            if 'available_queries_temp' in locals():
                del available_queries_temp
            gc.collect()

    def _identify_calculation_metrics(self, retrieval_results: List[Dict[str, Any]]) -> List[str]:
        """Identify metrics that need formula calculation"""
        calculation_metrics_raw = []
        
        for result in retrieval_results:
            if (
                result['retrieval_status'] == False and
                result.get('table_type') not in ['shareholding-pattern'] 
            ):
                metrics = result.get('metrics', [])
                if metrics:
                    calculation_metrics_raw.extend(metrics)
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(calculation_metrics_raw))
    
    async def _process_successful_retrievals(
        self, 
        retrieval_results: List[Dict[str, Any]], 
        get_data_func
    ) -> List[Dict[str, Any]]:
        """Process successful retrievals with batch database queries"""
        successful_results = [result for result in retrieval_results if result['retrieval_status'] in ['true', True]]
        
        logger.info(f"Successful results to process: {successful_results}")
        if not successful_results:
            return []
        
        # Batch database queries for better performance
        database_params = [result for result in successful_results]
        
        try:
            fetched_data_batch = await asyncio.wait_for(
                get_data_func(database_params),
                timeout=60.0
            )
            
            
            return fetched_data_batch.get('retrieved_data', [])
            
        except asyncio.TimeoutError:
            logger.error("Database batch query timed out")
            # Return error results for timeout
            return [
                {
                    **result,
                    'fetched_data': 'error: database timeout'
                } for result in successful_results
            ]
        except Exception as e:
            logger.error(f"Database batch query failed: {e}")
            # Return error results for database failure
            return [
                {
                    **result,
                    'fetched_data': f'error: {e}'
                } for result in successful_results
            ]
        