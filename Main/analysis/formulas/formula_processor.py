
from typing import Dict, Any, List, Callable
import asyncio
from asgiref.sync import sync_to_async
from collections import defaultdict
from ...models import  FinancialDataTable
from ...monitoring.llm_usage_tracker import (
    llm_usage_tracker as llm_usage_tracker,
    LLMType,
    enhanced_log_usage_summary as log_usage_summary
)
import logging


logger = logging.getLogger(__name__)

from ...monitoring.error_handling import (
    AnalysisError, 
    AnalysisErrorType, 
    RecursionTracker,
 
)


class FormulaProcessor:
    """Handles formula generation and processing"""
    
    async def generate_formulas_for_metrics(
        self, 
        calculation_metrics: List[str], 
        max_concurrent: int = 3
    ) -> Dict[str, Dict[str, Any]]:
        """Generate formulas for metrics that need calculation"""
        try:
            from Main.cutils import FinancialAnalysisLLM
            analyzer = FinancialAnalysisLLM()
            
            # Parallel formula generation with controlled concurrency
            formula_semaphore = asyncio.Semaphore(max_concurrent)
            
            async def controlled_formula_generation(metric_name):
                async with formula_semaphore:
                    formula_response, usage_dict, duration = await analyzer.generate_formula(metric_name)
                    
                    # Record LLM usage for formula generation
                    try:
                        llm_usage_tracker.record_llm_usage(
                            llm_type=LLMType.FORMULA_GENERATION,
                            usage_data=usage_dict,
                            duration_ms=duration,
                            company_slug='multiple',
                            metric_name=metric_name,
                            recursion_depth=0,
                            success=True
                        )
                    except ImportError:
                        logger.debug("LLM usage tracker not available")
                    
                    return formula_response
            
            # formula_tasks = [controlled_formula_generation(metric) for metric in calculation_metrics]
            # formula_param_result = await asyncio.gather(*formula_tasks, return_exceptions=True)
            formula_response, usage_dict, duration = await analyzer.generate_formula(calculation_metrics)

            # formula_param_result = formula_param_result.get('result')
            # Filter out errors and unpack the tuples
            key = list(formula_response.keys())[0]

            formula_response = formula_response.get(key, [])
         
            valid_results = [
                result for result in formula_response
                if not isinstance(result, Exception)
            ]

            # Extract formulas from responses
            valid_formulas = []
            for result in valid_results:
                if isinstance(result, tuple):
                    valid_formulas.append(result[0])
                else:
                    valid_formulas.append(result)

            if valid_formulas:
                
                formula_param_lookup = {
                    item['metric_name']: {
                        'formula': item['formula'],
                        'required_parameters': item.get('required_parameters', [])
                    } for item in valid_formulas if 'metric_name' in item and 'formula' in item
                }
                return formula_param_lookup
            
            return {}
            
        except Exception as e:
            logger.error(f"Formula generation failed: {e}")
            raise AnalysisError(
                error_type=AnalysisErrorType.FORMULA_GENERATION_ERROR,
                message=f"Formula generation failed: {str(e)}",
                metric_name=str(calculation_metrics),
                original_exception=e
            )


