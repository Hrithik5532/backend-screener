from langchain_core.tools import tool
from typing import Any, Dict, List, Optional
import logging
import json
from Main.agents.tools.llms.decompose import QueryValidator



class DecomposeQuery:
    def __init__(self, businesses: Optional[List[str]] = None):
        self.businesses = businesses or []

    def create_tool(self):
        """Create a properly bound tool instance"""
        
        @tool
        async def decompose_financial_query(query: str) -> str:
            """
            ALWAYS use this tool FIRST to decompose any financial query before retrieving data.
            
            Decomposes complex financial queries into structured sub-queries by extracting:
            - Company names mentioned
            - Time periods (quarters, months, years)
            - Financial metrics (revenue, EBITDA, profit, etc.)
            - Data types (actual, projected, year-over-year)
            
            Args:
                query: The user's financial question to analyze
            
            Returns:
                JSON string with decomposed query components needed for data retrieval
            """
            try:
                logging.info("=" * 80)
                logging.info("DECOMPOSE TOOL CALLED")
                # tool_logger = ToolLogger()
                # tool_logger.start("decompose_financial_query")

                
                validator = QueryValidator()
                llm_result, usage, duration = validator.validate_query(query, self.businesses)
                
                result = {
                    "success": True,
                    "original_query": query,
                    "understanding": llm_result.get("understanding", ""),
                    "decomposed_queries": llm_result.get("companies_data", []),
                    "token_usage": usage,
                    "processing_time_seconds": duration
                }
                
                logging.info("Decomposition result:")
                logging.info(json.dumps(result, indent=2))
                # tool_logger.log_interaction(
                #     tool_name="decompose_financial_query",
                #     input_data={"query": query},
                #     output_data=result,
                #     success=True
                # )
                return json.dumps(result, indent=2)
                
            except Exception as e:
                logging.error(f"Error in decompose: {str(e)}", exc_info=True)
                return json.dumps({
                    "success": False,
                    "error": str(e),
                    "original_query": query
                })
        
        return decompose_financial_query