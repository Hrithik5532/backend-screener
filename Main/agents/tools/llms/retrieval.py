import os
import time
import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from openai import AzureOpenAI


# logger = logging.getLogger(__name__)





class RetrievalParameter(BaseModel):
    """Individual retrieval parameter"""
    table_type: str = Field(description="the exact name of the table from which data needs to be retrieved")
    company_slug: str = Field(description="The name of the company SLUG provided by the user input.")
    data_type: str = Field(description="the data type provided by the user input, it can be consolidated or standalone. consider consoliodated if not found")
    metrics: List[str] = Field(description="Exact metric names to be retreived from the meta data of table, if you think multiple metrices required, then do not give any metric, Fill it with None.")
    columns: List[str] = Field(description="Based on the user input time period demand you have to give me the list of periods to be retrieved, do not assume or approximate any column names or time periods, if not found in column key of table structure still give the exact period mentioned in user input")

class RetrievalResponse(BaseModel):
    """Response model for data retrieval"""
    company_slug: str = Field(description="The name of the company SLUG provided by the user input.")
    retrieval_status: bool = Field(description="Boolean True or False, True if you are able to extract the parameters for retrieval, else False.")
    retrieval_parameters: List[RetrievalParameter] = Field(description="List of retrieval parameters")
    reasoning: str = Field(description="The reasoning, why did you choose the above parameters, explain in detail your understanding of the user query and how you mapped it to the table structure to extract the parameters for retrieval. If you are not able to extract any parameters for retrieval, explain why.")
    confidence_score: str = Field(description="Confidence score in the range of 0 to 1, how confident you are about the extracted parameters for retrieval, if you are not able to extract any parameters for retrieval give confidence score as 0.")

class DataRetriever:
    """Data retrieval class using CrewAI LLM"""
    
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.environ.get('AZURE_OPENAI_API_KEY'),
            api_version="2024-04-01-preview",
            azure_endpoint=os.environ.get('AZURE_OPENAI_ENDPOINT')
        )
        self.model = "gpt-4.1"

    def RetrievalLLM(self, metrics, company_slug, table_structures):
        """
        Retrieve relevant data from filtered tables using LLM analysis
        
        Args:
            metrics (str): User's original query
            table_structures (dict): Structure information for tables
        
        Returns:
            dict: Structured response with retrieved data and analysis
        """
    
                
        
        
        retrieval_prompt = [
    {
        "role": "system", 
        "content": f"""You are a senior financial data analyst with deep expertise in financial metrics and accounting standards. Your task is to intelligently map user-requested financial metrics to available data metrics using financial knowledge and semantic understanding.

## 🎯 CORE OBJECTIVE
Map each user-requested metric to the most appropriate available metric, or determine if it cannot be retrieved directly.

## 🧠 ANALYSIS METHODOLOGY

### Step 1: Metric Identification
- Parse the user's metric list completely
- Identify each unique financial metric requested
- Understand the financial context and intent

### Step 2: Intelligent Mapping Strategy
For each requested metric, apply this decision tree:

**DIRECT MATCH (confidence: 0.9-1.0)**
- Exact name match or perfect synonym
- Examples: "Revenue" → "Sales", "EBITDA" → "EBITDA", "Net Income" → "Profit After Tax"

**SEMANTIC MATCH (confidence: 0.7-0.9)**
- Strong financial relationship with single available metric
- Examples: "Gross Profit" when only "Gross Margin" available, "Interest Expense" → "Interest"

**NO DIRECT RETRIEVAL (retrieval_status: false, metrics: null)**
- **Calculated Metrics**: Requires computation from multiple metrics
  - Examples: "Current Ratio", "Debt-to-Equity Ratio", "ROE", "Asset Turnover"
- **Multiple Metrics Needed**: Single request needs 2+ available metrics
  - Examples: "Total Income" when requires "Sales" + "Other Income"
- **Not Available**: No reasonable equivalent exists in available metrics
- **Ambiguous**: Multiple possible interpretations without clear context

### Step 3: Financial Expertise Rules

**PROFIT HIERARCHY** (be specific about context):
- "Profit" (generic) → Use "Net Income" if available, else retrieval_status: false
- "Operating Profit" → "EBIT" or "Operating Income"
- "Gross Profit" → Direct match or calculate from Revenue-COGS

**REVENUE SYNONYMS**:
- Sales, Revenue, Turnover, Income (from operations) → all equivalent

**BALANCE SHEET ITEMS**:
- Assets, Liabilities, Equity → must match specific types
- Working Capital components → Current Assets, Current Liabilities

**RATIOS & CALCULATED METRICS**:
- ANY ratio (Current Ratio, Quick Ratio, etc.) → retrieval_status: false
- ANY percentage-based metric requiring calculation → retrieval_status: false
- ANY per-share metric → retrieval_status: false

### Step 4: Confidence Scoring
- **1.0**: Exact match
- **0.9-0.95**: Perfect financial synonym
- **0.8-0.9**: Strong semantic relationship, same financial concept
- **0.7-0.8**: Reasonable approximation but not perfect
- **<0.7**: Set retrieval_status: false

## 📋 OUTPUT REQUIREMENTS

**MANDATORY JSON STRUCTURE:**
```json
{{
  "retrieval_parameter": 
    {{
      "metric_name": "Original metric name from user query",
      "company": "The same name of the company provided by the user input.",
      "valid_metric_name": "Exact metric name from available data OR null if cannot retrieve directly",
      "retrieval_status": true/false,
      "confidence_score": 0.0-1.0,
      "reasoning": "Detailed explanation of mapping decision"
    }}
  
}}
```

## 🔍 DECISION EXAMPLES

**✅ RETRIEVABLE:**
- User: "Revenue" → Available: "Sales" → metrics: "Sales", retrieval_status: true, confidence: 0.95
- User: "EBITDA" → Available: "EBITDA" → metrics: "EBITDA", retrieval_status: true, confidence: 1.0

**❌ NOT RETRIEVABLE:**
- User: "Current Ratio" → Needs Current Assets + Current Liabilities → metrics: null, retrieval_status: false
- User: "Total Income" → Needs "Sales" + "Other Income" → metrics: null, retrieval_status: false
- User: "ROE" → Needs Net Income + Shareholders Equity → metrics: null, retrieval_status: false

## 📊 INPUT DATA

**USER REQUESTED METRICS:** `{metrics}`

**AVAILABLE METRICS:** `{table_structures}`

**COMPANY:** `{company_slug}`

## ⚡ ANALYSIS INSTRUCTIONS

1. **Process each user metric individually**
2. **Check for exact matches first**
3. **Apply financial synonyms and semantic understanding**
4. **If multiple metrics needed or calculation required → retrieval_status: false**
5. **Provide clear reasoning for each decision**
6. **Ensure confidence scores reflect mapping certainty**
7. **Return valid JSON only**

**CRITICAL RULES:**
- ONE user metric = ONE retrieval parameter
- If you need 2+ available metrics for 1 user metric → retrieval_status: false
- If calculation/formula needed → retrieval_status: false  
- If no reasonable match → retrieval_status: false
- Always explain your reasoning clearly

Begin analysis now and return the JSON response."""
    }
]

        
        try:
            start_time = time.time()
            # logger.info("ANythi8ng !!!!!!!!!!!!!")
            # Call Azure OpenAI
            # clie
            raw_response = self.client.chat.completions.create(
                model=self.model,
                messages=retrieval_prompt,
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            # logger.info(f"raw_response : {raw_response}")

            duration_ms = (time.time() - start_time) * 1000

            # Extract usage
            usage_dict = {}
            if raw_response.usage:
                usage_dict = {
                    'input_tokens': raw_response.usage.prompt_tokens,
                    'output_tokens': raw_response.usage.completion_tokens,
                    'total_tokens': raw_response.usage.total_tokens
                }

            # Get response text
            output_text = raw_response.choices[0].message.content
            
            if not output_text or output_text.strip() == "":
                raise ValueError("Empty response from Azure OpenAI")
            
            # Clean response
            output_text = output_text.strip()
            if output_text.startswith("```json"):
                output_text = output_text[7:]
            if output_text.endswith("```"):
                output_text = output_text[:-3]
            output_text = output_text.strip()

            # Parse JSON
            try:
                response_data = json.loads(output_text)
            except json.JSONDecodeError as je:
                logging.error(f"Invalid JSON from LLM: {output_text}")
                raise ValueError(f"JSON parsing failed: {str(je)}")
            response_data['token_usage'] = usage_dict
            response_data['processing_time_seconds'] = duration_ms
            return response_data
            
        except Exception as e:
            logging.error(f"Error in RetrievalLLM: {str(e)}")
            
            
            # Fallback response
            error_response = {
                "company_slug": 'multiple',
                "retrieval_status": False,
                "retrieval_parameters": [],
                "reasoning": f"Error occurred during data retrieval: {str(e)}",
                "confidence_score": "0.0"
            }
            
            return error_response, {}, 0 

