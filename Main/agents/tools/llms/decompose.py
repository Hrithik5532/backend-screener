"""
Simplified query decomposition with single LLM call
"""

import logging
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
            api_key=os.environ.get('AZURE_OPENAI_API_KEY'),
            api_version="2024-04-01-preview",
            azure_endpoint=os.environ.get('AZURE_OPENAI_ENDPOINT')
        )
        self.model = "gpt-4.1"
        self.fy_manager = FinancialYearManager()

    def _build_prompt(self, query: str, businesses: List[str]) -> List[Dict[str, str]]:
        logging.info("Building prompt for LLM...")

        logging.info(self.fy_manager.get_fy_context())
        context_lines = []
        if businesses:
            context_lines.append(
                "**Business Units:** "
                + ", ".join(b for b in businesses)
            )

            logging.info(f"Businesses context: {context_lines}")
            logging.info("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        available_tables = {
    "cash-flow": "The cash-flow table provides comprehensive cash flow analysis including: cash from operating activities (profit from operations, working capital changes, receivables, payables, inventory), cash from investing activities (fixed assets purchased/sold, investments purchased/sold, acquisition of companies, investment in subsidiaries), cash from financing activities (proceeds from borrowings/shares, repayment of borrowings, dividends paid, interest paid/received), and net cash flow calculations.",
    
    "shareholding": "The shareholding table provides information about the ownership structure of the company, including data like: promoter shareholding, institutional shareholding, non-institutional shareholding, and details about shares held by promoters, government, institutions, and non-institutions.",
    
    "balance-sheet": "The balance-sheet table presents a comprehensive snapshot of the company's financial position including: assets (fixed assets like building, plant machinery, land, vehicles, equipment, furniture, intangible assets, investments, inventories, cash equivalents, trade receivables, loans & advances), liabilities (borrowings - long term/short term, trade payables, lease liabilities, advance from customers, other liabilities), and equity (equity capital, reserves, non-controlling interest). Also includes accumulated depreciation, gross block, CWIP, and total assets/liabilities.",
    
    "profit-loss": "The profit-loss table provides detailed income statement analysis including: revenue metrics (sales, sales growth %), cost structure (raw material cost, material cost %, employee cost %, manufacturing cost %, other cost %), profitability metrics (operating profit, OPM %, net profit, profit before tax, profit excluding exceptional items), other financial data (depreciation, interest, other income, exceptional items, tax %, minority share), and per-share metrics (EPS, dividend payout %, profit for PE/EPS calculations).",
    
    "quarters": "The quarters table breaks down the company's financial performance by quarters, containing key P&L metrics on a quarterly basis including: sales and YOY sales growth %, profitability metrics (operating profit, OPM %, net profit, profit before tax, profit excluding exceptional items), YOY profit growth %, cost ratios (material cost %, employee cost %), other income, expenses, depreciation, interest, exceptional items, tax %, minority share, and EPS calculations.",
    
    "ratios": "The ratios table contains key financial ratios and market metrics including: efficiency ratios (cash conversion cycle, debtor days, inventory days, days payable, working capital days), profitability ratios (ROCE %) and market valuation metrics (current price, stock P/E, market cap, book value, dividend yield, face value, high/low price ranges, ROE), providing insights into operational efficiency, profitability, and market valuation.",

}
        
        system_prompt = f"""You are a financial query analyzer. Your task is to extract and structure information from user queries about Indian companies.

**CONTEXT:**
**CURRENT DATE:** {self.fy_manager.current_date} 
**CURRENT FY CONTEXT:** {self.fy_manager.get_fy_context()}
**QUERY TO ANALYZE:** "{query}"

**POTENTIAL COMPANIES IN THIS QUERY:**
{context_lines}

**AVAILABLE TABLES:**
{json.dumps(available_tables, indent=2)}

**ANALYSIS TASKS:**

1. **COMPANY IDENTIFICATION:**
   - Extract company names from the query
   - Match them against the potential companies list
   - Set company_status: true if found, false if not found
   - Use exact matches from the potential companies list

2. **TIME PERIOD NORMALIZATION** 
   - Annual periods → "Mar/Apr/Dec/Sep YYYY" format with period_type="Annual"
   - Quarter periods → "Mar/Apr/Dec/Sep YYYY" format with period_type="Quarterly"
   - No time mentioned → default to current FY end: "{self.fy_manager.current_fy_end}" with period_type="Yearly"
   - If year or period not mentioned and stated consider last FY or last quarter respectively, then always prefered completed Financial year or Quarter.
   - Always Consider completed Financial year
   
   **Period Type Classification:**
   - "Annual":   yearly data, or default
   - "Quarterly": Q1/Q2/Q3/Q4  mentions or quarterly data

3. **DATA TYPE DETECTION:**
   - "Standalone": Query mentions for standalone 
   - "Consolidated": Query mentions consolidated
   - If Data type not mentioned then by default set "Consolidated"

4. **METRICS EXTRACTION:**
   - Extract financial terms: revenue, sales, profit, margin, EBITDA, etc.
   - If compound metrics mentioned (e.g., "Net Profit / Revenue"), split into separate metrics
   - Return meaningful metric names
   - Apply same metrics to all periods unless specified otherwise

5. **SUGGEST TABLE FOR EACH METRIC:**
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
      "period": "Mar 2024",
      "period_type": "Quarterly or Annual",
      "metrics": "revenue",
      "data_type": "Consolidated or Standalone",
      "table_name": "profit-loss/balance-sheet/cash-flow/shareholding-pattern/quarter/ratios",
      "company_available_status": true
    }}
  ]
}}"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze this query: '{query}'"}
        ]

    def validate_query(self, query: str, businesses: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any], float]:
        start_time = time.time()
        
        messages = self._build_prompt(query, businesses,)
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