"""
Simplified financial analysis flow
"""

import asyncio
from typing import List, Dict, Any, Callable
from dotenv import load_dotenv
from asgiref.sync import sync_to_async

load_dotenv()

from .monitoring.error_handling import deep_serialize_for_crew
from .analysis.core.analysis_processor import FinancialAnalysisProcessor
from .analysis.query_decom.LLMDecom import process_with_metrics
from .monitoring.llm_usage_tracker import llm_usage_tracker, LLMType
from .analysis.db_chat_main import generate_financial_response


class FinancialAnalysisFlow:
    def __init__(self):
        self.processor = FinancialAnalysisProcessor()
    
    async def run_analysis(
        self,
        query: str,
        available_companies: List[str],
        get_company_tables_func: Callable,
        get_data_func: Callable,
    ) -> Dict[str, Any]:
        session_id = llm_usage_tracker.start_session(query)
        self.processor.recursion_tracker.clear_all()
        
        # Decompose query
        enhanced_result, metrics_focus, usage, duration = await process_with_metrics(
            query, available_companies, get_company_tables_func
        )
        
        llm_usage_tracker.record_llm_usage(
            llm_type=LLMType.QUERY_DECOMPOSITION,
            usage_data=usage,
            duration_ms=duration,
            success=True,
            additional_info={'metrics_focus': metrics_focus, 'result_count': len(enhanced_result)}
        )
        
        # Separate available and unavailable queries
        available_queries = [item for item in enhanced_result 
                           if item.get('company_available_status') and item.get('period_available_status')]
        not_available_queries = [item for item in enhanced_result 
                               if item not in available_queries]
        
        # if not available_queries:
        #     return self._no_data_response(not_available_queries)
        
        # Process queries
        retrieved_results = await self.processor.process_company_queries(
            available_queries, metrics_focus, get_company_tables_func, 
            get_data_func, recursion_depth=0, max_concurrent=3
        )
        
        successful_results = [r for r in retrieved_results if not isinstance(r, Exception) and "error" not in r]
        failed_results = [r for r in retrieved_results if r not in successful_results]
        errors = [r.get("error") for r in failed_results if "error" in r]
        
        # Generate response
        response_input = deep_serialize_for_crew({
            'crew_input': query,
            'fetch_result': successful_results,
            'calculation_required': "None",
            'errors': errors,
            'failed_queries': failed_results,
            'not_available_queries': not_available_queries,
         
        })
        
        final_response_raw = generate_financial_response(response_input)
        
        llm_usage_tracker.record_llm_usage(
            llm_type=LLMType.RESPONSE_GENERATION,
            usage_data={},
            duration_ms=0,
            success=True,
            additional_info={'response_type': 'crew_ai_response'}
        )
        
        final_response = (final_response_raw.raw if hasattr(final_response_raw, 'raw') 
                         else str(final_response_raw))
        
        llm_usage_tracker.end_session()
        
        return {
            'result': final_response,
            'fetch_result': deep_serialize_for_crew(successful_results),
            'errors': deep_serialize_for_crew(errors),
            'coordinates_count': len(successful_results),
            'partial_success': len(successful_results) > 0
        }
    
    def _no_data_response(self, not_available_queries):
        return deep_serialize_for_crew({
            'result': 'Company name not found in Database or no data available for the requested metrics.',
            'fetch_result': [],
            'errors': [],
            'coordinates_count': 0,
            'partial_success': False,
            'summary': {
                'total_queries': 0,
                'successful_count': 0,
                'failed_count': 0,
                'not_available_count': len(not_available_queries)
            }
        })


async def main_analysis_function(query: str) -> Dict[str, Any]:
    from .models import Company
    from .analysis.data.Retrive_data import get_financial_data,fetch_tables_for_company
    from .agents.db_agents import db_agents_chat_stream_2
    @sync_to_async
    def get_all_companies():
        return list(Company.objects.values_list('slug', flat=True).distinct())
    

    
    available_companies = await get_all_companies()
    result = await db_agents_chat_stream_2(businesses=available_companies,query=query)
    return result