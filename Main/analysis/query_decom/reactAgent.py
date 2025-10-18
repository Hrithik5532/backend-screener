"""
Financial Query Analysis Agent using LangGraph ReAct
Uses decomposer tool and retrieval tool
"""

from asyncio.log import logger
import os
import json
from typing import List, Dict, Any, Optional
from langchain.tools import StructuredTool
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import asyncio
import logging
# Import your existing modules
from Main.analysis.core.retrievel_processor import financial_data_retriever_tool_async
from Main.analysis.query_decom.LLMDecom import QueryValidator
from Main.analysis.data.Retrive_data import get_all_companies,get_financial_data

load_dotenv()


# ============================================================================
# TOOL 1: Query Decomposer Tool
# ============================================================================

class QueryDecomposerInput(BaseModel):
    """Input schema for query decomposition"""
    query: str = Field(description="The user's financial query to decompose")

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


async def decompose_query_async(
    query: str,
) -> str:
    """
    Decompose a complex financial query into structured sub-queries.
    
    This tool analyzes the user's query and breaks it down into:
    - Company names mentioned
    - Time periods (quarters, months, years)
    - Financial metrics (revenue, EBITDA, profit, etc.)
    - Data types (actual, projected, year-over-year)
    
    Returns a JSON string with all decomposed information needed for retrieval.

    """
    validator = QueryValidator()    
    available_companies = await get_all_companies()
    print("Initializing agent...")
    print(f"Loaded {len(available_companies)} companies")

    print("Validating query...")
    llm_result, usage, duration = validator.validate_query(query, available_companies)
    # Format the result for the agent
    result = {
        "success": True,
        "original_query": query,
        "understanding": llm_result.get("understanding", ""),
        "decomposed_queries": llm_result.get("companies_data", []),
      
    }

    print(f"Validation complete: {result}")
    return json.dumps(result, indent=2)


def decompose_query_sync(query: str) -> str:
    """Sync wrapper for LangChain"""
    return asyncio.run(decompose_query_async(query))


# Create the decomposer tool
query_decomposer_tool = StructuredTool.from_function(
    coroutine=decompose_query_async,
    name="decompose_financial_query",
    description="""Decompose a user's financial query into structured sub-queries.
    
    Use this tool FIRST when you receive a user query about financial data.
    It will break down the query into:
    - Identified companies
    - Time periods (FY, quarters, months)
    - Metrics to retrieve (revenue, EBITDA, profit, etc.)
    - Table names to query
    
    The output will guide you on what data to retrieve using the retrieve_financial_metrics tool.""",
    args_schema=QueryDecomposerInput,
    return_direct=False
)




async def retrieve_financial_data_async(
    company: str,
    table_name: str,
    metric: str,
    period: str,
    data_type: str,
    significance: str
) -> str:
    """
    Retrieve financial data from database using coordinates.
    
    This tool fetches specific financial metrics for a company from the database.
    Use this after decomposing the user's query to get the actual data values.
    
    Args:
        company: Company name (exact match from decomposition)
        table_name: Financial table (e.g., 'qbr_data' for quarterly, 'mbr_data' for monthly)
        metric: Metric to retrieve for company (e.g., 'EBITDA', 'Revenue')
        period: Time periods (e.g., 'Q1 2024', 'March 2024')
        data_type: Type of data - 'ftm', 'ytd', or 'qtd'
        significance: Data significance - 'actual', 'ly', 'p_b', or 'dev'
    
    Returns:
        JSON string with retrieved financial data
    """
    try:
        print(f"Retrieving data for {company}: {metric} from {table_name}")
        
        # Build coordinate for get_financial_data
        coord = {
            "company": company,
            "table_name": table_name,
            "metrics": metric,
            "columns": period,  # periods mapped to columns
            "data_type": data_type,
            "significance": significance
        }
        
        # Call the existing function
        result = await get_financial_data(coord)
        
        print(f"Data retrieval result: {result}")
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
        
        return json.dumps(response, indent=2)
        
    except Exception as e:
        print(f"Error retrieving financial data: {str(e)}")
        error_response = {
            "success": False,
            "error": str(e),
            "company": company,
            "data": []
        }
        return json.dumps(error_response, indent=2)



financial_data_tool_async = StructuredTool.from_function(
    coroutine=retrieve_financial_data_async,
    name="get_financial_data",
    description="""Retrieve financial data from database using specific coordinates.

Use this tool to fetch actual financial values after decomposing the user's query.

Parameters should come from the decomposition tool output:
- company: Exact company name from decomposition
- table_name: Table name from decomposition (qbr_data, mbr_data)
- metric: Metric names (EBITDA, Revenue, etc.)
- period: Time periods (Q1 2024, March 2024, etc.)
- data_type: ftm, ytd, or qtd (default: ftm)
- significance: actual, ly, p_b, or dev (default: actual)

Returns structured financial data with values organized by metric and period.""",
    args_schema=FinancialDataInput,
    return_direct=False
)



# ============================================================================
# Agent Setup
# ============================================================================

class FinancialReActAgent:
    """ReAct Agent for Financial Queries"""
    
    def __init__(self):
        """
        Initialize the ReAct agent with tools
        
        Args:
            available_companies: List[str] = Field(
                description="List of available company names in the database"
            )
        """
        # self.available_companies = available_companies
        
        # Initialize LLM
        self.llm = AzureChatOpenAI(
            api_key=os.environ.get('AZURE_API_KEY'),
            api_version="2024-04-01-preview",
            azure_endpoint=os.environ.get('AZURE_API_BASE'),
            deployment_name="gpt-4.1",
            temperature=0,
            streaming=True
        )
        
        # Create tools list
        self.tools = [
            query_decomposer_tool,
            financial_data_retriever_tool_async,
            financial_data_tool_async
        ]
        
        # Create ReAct agent with system prompt
        system_prompt = """You are a financial data analysis assistant specializing in Indian company financial data.

# AVAILABLE TOOLS

1. **decompose_financial_query**: Breaks down user queries into structured components
2. **retrieve_financial_metrics**: Fetches financial data from database

# WORKFLOW (FOLLOW STRICTLY)

## STEP 1: DECOMPOSE THE QUERY
- **Action**: Call `decompose_financial_query` with the user's original query
- **Purpose**: Get structured information about companies, metrics, time periods, and tables
- **Do this**: ONLY ONCE per user query
- **Output**: You'll receive a JSON with `decomposed_queries` array

## STEP 2: EXTRACT RETRIEVAL PARAMETERS
From the decomposition output, for EACH item in `decomposed_queries`, extract:
- `company`: Use EXACT company name (e.g., "AB Capital" not "abcapital")
- `table_name`: Use exact table name (e.g., "qbr_data", "mbr_data")
- `metric` : Use EXACT metric name (e.g., "EBITDA", "Revenue")
- `period`: Use EXACT time period (e.g., "Q1 2024", "March 2024")
- `data_type`: Use provided value or default to "ftm"
- `significance`: Use provided value or default to "actual"


## STEP 3: RETRIEVE DATA
For EACH item in decomposed_queries:
- Call `retrieve_financial_metrics` with extracted parameters
- Use EXACT VALUES from decomposition (no modifications)
- If multiple companies, make separate calls

## STEP 4: FETCH DATA
- Call `get_financial_data` for each item in `retrieve_financial_metrics` with:
  - `company`
  - `table_name` 
  - `valid_metric_name` (with valid_metric_name from retrieve_financial_metrics for company)
  - `period` 
  - `data_type` (default "ftm")
  - `significance` (default "actual")   

## STEP 5: SYNTHESIZE ANSWER
- Combine all retrieved data
- Present in clear, readable format
- Include company name, metric, period, and values
- If data missing, explain what couldn't be found

# CRITICAL RULES

❌ **DON'T:**
- Modify company names from decomposition output
- Call decompose_financial_query multiple times
- Skip retrieval calls
- Make assumptions about data availability

✅ **DO:**
- Use exact parameter values from decomposition
- Make one retrieval call per company-metric-table combination
- Handle errors gracefully
- Provide clear, formatted answers

# EXAMPLE EXECUTION

**User Query:**
"What is the EBITDA of AB Capital for Q1 2024?"

**Step 1 - Decompose:**
```
Call: decompose_financial_query(query="What is the EBITDA of AB Capital for Q1 2024?")

Result: {
  "success": true,
  "understanding": "User wants EBITDA for AB Capital in Q1 2024",
  "decomposed_queries": [
    {
      "company": "AB Capital",
      "period": "Q1 2024",
      "period_type": "qbr",
      "metrics": "EBITDA",
      "data_type": "qtd",
      "significance": "actual",
      "table_name": "qbr_data",
      "company_available_status": true
    }
  ]
}
```



**Step 2 - Retrieve:**
```
Call: retrieve_financial_metrics(
  table_name="qbr_data",
  company="AB Capital",
  metric="EBITDA",
  data_type="qtd",
  significance="actual",
  period="Q1 2024"
)

Result: {
                "table_name": "qbr_data",
                "company": "AB Capital",
                "metric": "EBITDA",
                "data_type": "qtd",
                "significance": "actual",
                "valid_metric_name": "ebitda",
                "period": "Q1 2024",
                "retrieval_status": True,
                "reasoning": "The user requested 'EBITDA', which is present as an exact match in the available metrics list ('ebitda'). No calculation or interpretation is required. This is a direct, case-insensitive match, so retrieval is possible with maximum confidence.",
    }

```

**Step 3 - Fetch Data:**
```
Call: get_financial_data(
  company="AB Capital",
  table_name="qbr_data",
  metric="ebitda",
  period="Q1 2024",
  data_type="qtd",
  significance="actual"
)
```
get_financial_data returns JSON with actual data values, use that in final answer.

**Step 4 - Answer:**
"The EBITDA of AB Capital for Q1 2024 is ₹XXXX."

# MULTI-COMPANY EXAMPLE

**User Query:**
"Compare EBITDA and Revenue of TCS and Infosys for Q1 2024"

**Execution:**
1. Decompose once → Get 4 items (2 companies × 2 metrics)
2. Make 4 retrieval calls:
   - retrieve(table="qbr_data", company="TCS", metric="EBITDA", period="Q1 2024", data_type="qtd", significance="actual")
   - retrieve(table="qbr_data", company="TCS", metric="Revenue", period="Q1 2024", data_type="qtd", significance="actual")
   - retrieve(table="qbr_data", company="Infosys", metric="EBITDA", period="Q1 2024", data_type="qtd", significance="actual")
   - retrieve(table="qbr_data", company="Infosys", metric="Revenue", period="Q1 2024", data_type="qtd", significance="actual")
3. Present comparison table

# ERROR HANDLING

**If decomposition fails:**
- Inform user the query couldn't be understood
- Ask for clarification

**If retrieval fails:**
- Check if company name is correct
- Verify table exists
- Explain what data is missing

**If no data found:**
- Report which specific metric/period is unavailable
- Suggest alternatives if possible

# OUTPUT FORMAT

Present data clearly:
- Use tables for multiple values
- Include units (Crores, Lakhs, etc.)
- Show time periods clearly
- Format numbers with commas (e.g., 1,250.5)

Remember: Your goal is to provide accurate financial data with zero hallucination. Always retrieve data before answering."""

        self.agent = create_react_agent(
            self.llm,
            self.tools,
            prompt=system_prompt
        )
    
    async def run(self, query: str) -> Dict[str, Any]:
        """
        Run the agent on a query
        
        Args:
            query: User's financial query
            
        Returns:
            Dictionary with results
        """
        # Prepare the input with available companies context
        enhanced_query = f"""{query}"""        
        # Run the agent
        result = await self.agent.ainvoke({
            "messages": [HumanMessage(content=enhanced_query)]
        })
        
        # Extract the final answer
        messages = result.get("messages", [])
        final_message = messages[-1] if messages else None
        
        return {
            "query": query,
            "final_answer": final_message.content if final_message else "No answer generated",
            "messages": messages,
            "tool_calls_made": sum(1 for msg in messages if hasattr(msg, 'tool_calls'))
        }
    
    async def stream(self, query: str):
        """
        Stream the agent's response
        
        Args:
            query: User's financial query
            
        Yields:
            Agent events and messages
        """
        enhanced_query = f"""{query}"""
        
        async for event in self.agent.astream_events(
            {"messages": [HumanMessage(content=enhanced_query)]},
            version="v1"
        ):
            yield event


# ============================================================================
# Example Usage
# ============================================================================

async def main():
    """Example usage of the Financial ReAct Agent"""
    
  
    
    # Initialize agent
    agent = FinancialReActAgent()
    
    # Test queries
    test_queries = [
        "What is the EBITDA of abcapital for Q1 2024?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*80}")
        print(f"Query: {query}")
        print('='*80)
        
        result = await agent.run(query)
        
        print(f"\n{result['final_answer']}")
        print(f"\nTool calls made: {result['tool_calls_made']}")


async def demo_streaming():
    """Demo streaming responses"""
    
    agent = FinancialReActAgent()
    
    query = "What is the EBITDA of abcapital and abml for April 2024?"
    
    print(f"Query: {query}\n")
    print("Streaming response:")
    print("-" * 80)
    
    async for event in agent.stream(query):
        kind = event.get("event")
        
        if kind == "on_chat_model_stream":
            content = event.get("data", {}).get("chunk", {}).content
            if content:
                print(content, end="", flush=True)
        
        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            print(f"\n\n🔧 Using tool: {tool_name}")
        
        elif kind == "on_tool_end":
            print(f"\n✓ Tool completed")


if __name__ == "__main__":
    import asyncio
    
    # Run basic demo
    asyncio.run(demo_streaming())
    
