"""
LangGraph-based Financial Response Agent
"""

from typing import TypedDict, Annotated
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
import os
from dotenv import load_dotenv

load_dotenv()

# Azure LLM Configuration
model = AzureChatOpenAI(
    azure_deployment=os.environ.get("AZURE_LLM_MODEL_NAME", "gpt-4o"),
    api_version="2024-02-15-preview",
    temperature=0,
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    api_key=os.environ.get("AZURE_OPENAI_API_KEY")
)

# System prompt for financial accuracy
FINANCIAL_ACCURACY_PROMPT = """You are an Ultra-Precise Financial Data Response Specialist.

CRITICAL RULES:
1. NEVER mix data between companies
2. ALWAYS verify each number comes from the correct company
3. ALWAYS cite sources: [Company → Table → Metric → Period → Type]
4. For calculations: show complete audit trail with source verification
5. Maintain strict data segregation between companies

RESPONSE STRUCTURE:
1. Direct Answer with Source Verification
2. Data Presentation with Individual Attribution
3. Calculation Transparency (if applicable)
4. Insights with Indian Financial Context

VERIFICATION CHECKLIST (Complete before responding):
□ Each company's data belongs to that company only
□ No number swapping between companies
□ Table sources correctly identified
□ Time periods aligned
□ Calculations verified (same company, same period)
□ Currency formatting consistent (₹Cr/₹L)

When presenting data:
- Use tables for comparisons with source verification column
- Show calculation steps: Component 1 + Component 2 = Result
- Include source trail for each data point
- Apply Indian market context and FY terminology

NEVER:
❌ Mix Company A's data with Company B's data
❌ Use data without source attribution
❌ Make assumptions or estimates
❌ Modify provided numbers"""


class FinancialState(TypedDict):
    """State for financial analysis"""
    query: str
    fetch_result: list
    calculation_required: str
    errors: list
    response: str


def create_financial_agent():
    """Create LangGraph agent for financial responses"""
    
    # No tools needed - agent works with provided data only
    tools = []
    
    # Create system message
    system_message = SystemMessage(content=FINANCIAL_ACCURACY_PROMPT)
    
    # Create agent with checkpointer
    checkpointer = MemorySaver()
    
    agent_executor = create_react_agent(
        model,
        tools,
        prompt=system_message,
        # checkpointer=checkpointer
    )
    
    return agent_executor


def format_input_for_agent(response_input: dict) -> str:
    """Format input data for the agent"""
    
    input_text = f"""USER QUERY: {response_input.get('crew_input', '')}

FETCHED DATA:
{response_input.get('fetch_result', [])}

CALCULATION REQUIRED: {response_input.get('calculation_required', 'None')}

ERRORS: {response_input.get('errors', [])}

FAILED QUERIES: {response_input.get('failed_queries', [])}

NOT AVAILABLE QUERIES: {response_input.get('not_available_queries', [])}

Provide an accurate, conversational response with complete source verification for all data points."""
    
    return input_text


def generate_financial_response(response_input: dict) -> str:
    """Generate financial response using LangGraph agent"""
    
    agent = create_financial_agent()
    formatted_input = format_input_for_agent(response_input)
    config = {"configurable": {"thread_id": "financial_analysis_thread"}}
    
    result = agent.invoke(
        {"messages": [HumanMessage(content=formatted_input)]},
        config=config
    )
    
    return result["messages"][-1].content


def generate_financial_response_sync(response_input: dict) -> str:
    """Synchronous version of response generation"""
    
    agent = create_financial_agent()
    formatted_input = format_input_for_agent(response_input)
    config = {"configurable": {"thread_id": "financial_analysis_thread"}}
    
    result = agent.invoke(
        {"messages": [HumanMessage(content=formatted_input)]},
        config=config
    )
    
    return result["messages"][-1].content


# Usage example
if __name__ == "__main__":
    import asyncio
    
    # Example data
    test_query = "What is the revenue of TCS?"
    test_fetch_result = [
        {
            "company": "tcs",
            "table_name": "profit-loss",
            "data_type": "consolidated",
            "data": {
                "Net Sales": {
                    "Mar 2025": {
                        "value": "245678",
                        "numeric_value": 245678.0,
                        "significance": "Cr",
                        "data_type": "consolidated"
                    }
                }
            }
        }
    ]
    
    # Run async
    async def test():
        response = await generate_financial_response(
            test_query,
            test_fetch_result
        )
        print(response)
    
    asyncio.run(test())