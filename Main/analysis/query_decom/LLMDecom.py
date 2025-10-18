"""
Simplified query decomposition with single LLM call
"""

import os
import datetime
import json
import time
from typing import List, Dict, Any, Tuple
from openai import AzureOpenAI


class FinancialYearManager:
    def __init__(self):
        now = datetime.datetime.now()
        self.current_year = now.year if now.month >= 4 else now.year
        self.current_fy_end = f"Mar {now.year + 1 if now.month >= 4 else now.year}"
        self.current_date = now.strftime("%Y-%m-%d")
    
    def get_fy_context(self) -> str:
        return f"FY{self.current_year} ends on {self.current_fy_end}"


class QueryValidator:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.environ.get('AZURE_API_KEY'),
            api_version="2024-04-01-preview",
            azure_endpoint=os.environ.get('AZURE_API_BASE')
        )
        self.model = "gpt-4.1"
        self.fy_manager = FinancialYearManager()
    
    def _build_prompt(self, query: str, companies: List[str]) -> List[Dict[str, str]]:
        available_tables = {
            'mbr_data': 'mbr_data table consist important metrices like ocf, fcff and ebitda of companies having monthly results.',
            'qbr_data': 'qbr_data table consist important metrices like ocf, fcff and ebitda of companies having quarterly results.',
        }
        
        system_prompt = f"""You are a financial query analyzer. Your task is to extract and structure information from user queries about Indian companies.

**CONTEXT:**
**CURRENT DATE:** {self.fy_manager.current_date} 
**CURRENT FY CONTEXT:** {self.fy_manager.get_fy_context()}
**QUERY TO ANALYZE:** "{query}"

**POTENTIAL COMPANIES IN THIS QUERY:**
{companies}

**AVAILABLE TABLES:**
{json.dumps(available_tables, indent=2)}

**ANALYSIS TASKS:**

1. **COMPANY IDENTIFICATION:**
   - Extract company names from the query
   - Match them against the potential companies list
   - Set company_status: true if found, false if not found
   - Use exact matches from the potential companies list

2. **TIME PERIOD NORMALIZATION** (Indian FY: Apr-Mar)
   - Monthly periods → "March YYYY" format with period_type="mbr"
   - Quarter periods → "Q1/Q2/Q3/Q4 YYYY" format with period_type="qbr"
   - No time mentioned → default to current FY end: "{self.fy_manager.current_fy_end}" with period_type="mbr"
   - If year or period not mentioned and stated consider last FY or last quarter respectively, then always prefered completed Financial year or Quarter.
   - Always Consider completed Financial year
   
   **Period Type Classification:**
   - "mbr": FY mentions, yearly data, or default
   - "qbr": Q1/Q2/Q3/Q4 mentions or quarterly data

3. **DATA TYPE DETECTION:**
   - "ftm": Query mentions for this month
   - "ytd": Query mentions year till date
   - "qtd": Query mentions quarter till date
   - If Data type not mentioned then by default set "ftm" (for this month) for monthly and "qtd" (quarter till date) for quarterly

4. **METRICS EXTRACTION:**
   - Extract financial terms: revenue, sales, profit, margin, EBITDA, etc.
   - If compound metrics mentioned (e.g., "Net Profit / Revenue"), split into separate metrics
   - Return meaningful metric names
   - Apply same metrics to all periods unless specified otherwise

5. **SIGNIFICANCE DETECTION:**
    - Try to understand significance of extracted metric from query.
    - significance could be:
        - "ly": last year value of metric
        - "actual": Actual value of metric
        - "p_b": Projected value of metric
        - "dev": Deviation between actual and p_b value of metric
    - If significance is not clearly mentioned or confusing to extract then set default as 'actual'.

6. **SUGGEST TABLE FOR EACH METRIC:**
    - Understand the metric name provided by the user.
    - Analyze the available tables and their descriptions.
    - Select the most relevant table based on the metric name.
    - Provide a clear explanation of your reasoning.
    - If you think, no table is related to the metric name, then give None as table name. But do not assume by yourself

**OUTPUT REQUIREMENTS:**
- Always return valid JSON
- Create separate entry for each company-metric-period combination
- Each entry should have all required fields

Return in this exact JSON structure:
{{
  "query": "original query text",
  "understanding": "brief explanation of extracted requirements",
  "companies_data": [
    {{
      "company": "EXACT_COMPANY_NAME_FROM_LIST",
      "period": "March 2024",
      "period_type": "mbr",
      "metrics": "revenue",
      "data_type": "ftm",
      "significance": "actual",
      "table_name": "mbr_data",
      "company_available_status": true
    }}
  ]
}}"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze this query: '{query}'"}
        ]
    
    def validate_query(self, query: str, companies: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any], float]:
        start_time = time.time()
        
        messages = self._build_prompt(query, companies)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            max_tokens=20000,
            response_format={"type": "json_object"}
        )
        
        duration_ms = (time.time() - start_time) * 1000
        
        usage = {
            'input_tokens': response.usage.prompt_tokens,
            'output_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        } if response.usage else {}
        
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        
        return json.loads(content.strip()), usage, duration_ms


def extract_periods_from_api(api_response: Dict[str, Any]) -> List[str]:
    """Extract unique time periods from API response"""
    periods = set()
    
    if 'overview' in api_response:
        for table in api_response['overview']:
            if 'columns' in table:
                for col in table['columns']:
                    if col and col != "" and col != "TTM" and any(c.isdigit() for c in col):
                        periods.add(col)
    
    return sorted(list(periods))


async def process_with_metrics(
    query: str,
    available_companies: List[str],
    get_company_tables_func
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any], float]:
    """Main processing function - single LLM call"""
    
    # Step 1: Validate query with LLM
    validator = QueryValidator()
    llm_result, usage, duration = validator.validate_query(query, available_companies)
    
    # Step 2: Process results
    results = []
    metrics_focus = set()
    
    for company_data in llm_result.get('companies_data', []):
        # Fetch available periods if company exists
        # available_periods = []
        # if company_data.get('company_available_status', False):
        #     api_response = await get_company_tables_func(company_data['company'])
        #     available_periods = extract_periods_from_api(api_response)
        
        # # Add to results
        # period_available = company_data.get('period', '') in available_periods
        
        results.append({
            'id': f"#{len(results)}",
            'company': company_data.get('company', ''),
            'metric_name': company_data.get('metrics', ''),
            'period': company_data.get('period', ''),
            'period_type': company_data.get('period_type', 'mbr'),
            'period_available_status': True,
            'data_type': company_data.get('data_type', 'ftm'),
            'significance': company_data.get('significance', 'actual'),
            'table_name': company_data.get('table_name'),
            'company_available_status': company_data.get('company_available_status', False)
        })
        
        # Collect metrics
        if company_data.get('metrics'):
            metrics_focus.add(company_data['metrics'])
    
    return results, list(metrics_focus), usage, duration