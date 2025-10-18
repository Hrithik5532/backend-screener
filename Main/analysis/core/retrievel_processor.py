
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
from django.db import connection

logger = logging.getLogger(__name__)




class DataRetrieverMain:
    """Handles data retrieval operations with optimization"""
    
    def __init__(self):
        self.cache = {}

    def group_queries_by_metrics(self, available_queries):
        """
        Groups queries by table_name and data_type, returning a list of JSON objects
        where each object has table_name as key and list of queries as value.
        
        Args:
            available_queries (list): List of query dictionaries
            
        Returns:
            list: List of JSON objects in format:
                  [{ table_name: [queries with same table_name and data_type] }]
        """
        from collections import defaultdict
        
        # Create a dictionary to group queries by (table_name, data_type)
        grouped_queries = defaultdict(list)
        
        for query in available_queries:
            # Create a key tuple from the two fields we want to group by
            key = (query['table_name'], query['data_type'], query['company_slug'])
            grouped_queries[key].append(query)
        
        # Convert to list of JSON objects with table_name as key
        result = []
        for (table_name, data_type, company_slug), queries in grouped_queries.items():
            # Create a JSON object with table_name as key and queries as value
            table_group = {f'{table_name}_{company_slug}': queries}
            result.append(table_group)
        
        return result
    
    @sync_to_async
    def fetch_table_info(self, table_name: str, data_type: str = None, company: str = None) -> Dict[str, Any]:
        """
        Fetch metrics info from transformed_data using raw SQL.
        """

        where_conditions = ["td.table_name = %s"]
        params = [table_name]

        if data_type:
            where_conditions.append("td.data_type = %s")
            params.append(data_type)

        if company:
            where_conditions.append("td.company = %s")
            params.append(company)

        where_clause = " AND ".join(where_conditions)

        query = f"""
            SELECT 
                td.metric_name,
                td.year,
                td.data_type,
                COUNT(*) AS metric_count
            FROM transformed_data td
            WHERE {where_clause}
            GROUP BY td.metric_name, td.year, td.data_type
            ORDER BY td.metric_name, td.year, td.data_type
        """

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            return {
                "table_name": table_name,
                "data_type": data_type,
                "company": company,
                "message": f"No financial metrics available for table: {table_name}",
                "metrics_list": [],
                "column_headers": [],
                "total_metrics": 0,
                "data_types_available": []
            }

        # Process results
        metrics_list = set()
        column_headers = set()
        data_types_found = set()
        total_metrics = 0

        grouped_data = defaultdict(lambda: {
            "metrics_list": set(),
            "column_headers": set(),
            "total_metrics": 0
        })

        for metric_name, year, dt, count in rows:
            metrics_list.add(metric_name)
            column_headers.add(year)
            data_types_found.add(dt)
            total_metrics += count

            grouped_data[dt]["metrics_list"].add(metric_name)
            grouped_data[dt]["column_headers"].add(year)
            grouped_data[dt]["total_metrics"] += count

        result = {
            "table_name": table_name,
            "metrics_list": sorted(list(metrics_list)),
            "column_headers": sorted(list(column_headers)),
            "total_metrics": total_metrics,
            "data_types_available": sorted(list(data_types_found)),
        }

        return result


    async def retrieve_with_retry(
        self, 
        metrics_json,  
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Retrieve data with retry logic and caching"""

        # cache_key = f"{query['company_slug']}_{query['metric_name']}_{query.get('table_name', '')}_{query.get('data_type', '')}_{query.get('period', '')}"
        
        # if cache_key in self.cache:
        #     logger.info(f"Cache hit for {cache_key}")
        #     return self.cache[cache_key]
        
        for attempt in range(max_retries):
            try:
                # Add jitter to prevent thundering herd
                if attempt > 0:
                    await asyncio.sleep(0.1 * attempt)

                result = await self._execute_retrieval(metrics_json)


                return result
                
            except Exception as e:
                logger.warning(f"Retrieval attempt {attempt + 1} failed : {e}")
                
                if attempt == max_retries - 1:
                    # Return error response instead of raising exception
                    error_response = {
                        "error": {
                            "error_type": "DATA_RETRIEVAL_ERROR",
                            "message": f"Retrieval failed after {max_retries} attempts: {str(e)}",
                            "metric_name": 'multiple',
                            "company_slug": 'multiple',
                            "retry_count": attempt + 1
                        },
                        "metrics_json": metrics_json,
                        "retrieval_status": False
                    }
                    return error_response

    async def _execute_retrieval(self, metrics_json):
        """Execute the actual retrieval logic"""
        try:
            logger.info(f"Metric Json : {metrics_json}")
          
            # logger.info(f"Fetching table info for {query}")
            filtered_tables = metrics_json.get("table_name")
            company_slug = metrics_json.get("company")
            metrics = metrics_json.get("metrics")
            # logger.info(f"Filtered Tables: {filtered_tables}, Company Slug: {
            # Get company table data with timeout
            company_tables_data = await asyncio.wait_for(
                # get_company_tables_func(query['company_slug']),
                self.fetch_table_info(table_name=filtered_tables, company=company_slug),
                timeout=30.0
            )

            logger.info(f"Company tables data fetched successfully for {metrics_json}")
        except asyncio.TimeoutError:
            raise Exception(f"Company tables fetch timed out for {metrics_json}")
        except Exception as e:
            raise Exception(f"Failed to fetch company tables for {metrics_json}: {str(e)}")

        try:

            from Main.cutils import DataRetriever as CutilsDataRetriever
            analyzer = CutilsDataRetriever()
            

            retrieval_response = await asyncio.wait_for(
                analyzer.RetrievalLLM(
                    # company_slug=query['company_slug'],
                    metrics=metrics,
                    company_slug=company_slug,
                    table_structures=company_tables_data,
                ),
                timeout=45.0
            )
            logging.info("!!!!!!!! ------ \n\n")
            logging.info(f'{company_tables_data}\n \n{metrics_json}')
            logger.info(f"Retrieval Response Raw: {retrieval_response}")
            logging.info("!!!!!!!! ------\n\n")

            
            retrieval_result = retrieval_response.get('retrieval_parameters', [])
          

                    

            for result in retrieval_result:
                # Normalize the result
                if result.get("metrics")  in [None, [None],[],["None"]]:
                    result["retrieval_status"] = False
                    result["metrics"] = [result.get("metric_name")]
                else:
                    result["metrics"] = [result.get("metrics")]

            # logger.info(f"Retrieval result: {retrieval_result}")
            return retrieval_result
 
        except Exception as e:
            raise Exception(f"Data retrieval failed for metric '{metrics_json}': {str(e)}")

