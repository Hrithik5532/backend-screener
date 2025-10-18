import os
import time
import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from openai import AzureOpenAI

# Import the usage tracking system
from .monitoring.llm_usage_tracker import llm_usage_tracker, LLMType
from .monitoring.error_handling import extract_and_parse_json
logger = logging.getLogger(__name__)





# class TableFilterResponse(BaseModel):
#     """Response model for table filtering"""
#     id: str = Field(description="Unique identifier for the retrieval request")
#     company_slug: str = Field(description="The same name of the company SLUG provided by the user input.")
#     metric_name: str = Field(description="the same metric name requested by the user")
#     table_name: str = Field(description="The table name from which the metric data is to be retrieved")
#     reasoning: str = Field(description="A brief explanation of why this table was selected based on the metric name")
#     confidence_score: str = Field(description="A confidence score between 0 and 1 indicating the certainty of the table selection")

# class TableFilter:
#     """Table filter class using CrewAI LLM"""
    
#     def __init__(self):
#         self.client = AzureOpenAI(
#             api_key=os.environ.get('AZURE_API_KEY'),
#             api_version="2024-04-01-preview",  # adjust to your Azure deployment
#             azure_endpoint=os.environ.get('AZURE_API_BASE')
#         )
#         self.model = "gpt-4.1"

#     def filter_tables(self, input_structure):
#         """Convert create_table_filter_agent + create_table_filter_task to direct LLM call"""
        
#         output_structure =[ {
#             "metric_name": "the same metric name requested by the user",
#             "table_name": "The table name from which the metric data is to be retrieved",
#             "reasoning": "A brief explanation of why this table was selected based on the metric name",
#             'period_type': "The period type for which data is to be retrieved (mentioned in query json)",
#         },

#         ]
       
#         available_tables = {
    
#             'mbr_data' : 'mbr_data table consist important metrices like ocf, fcff and ebitda of companies having monthly results.',
#             'qbr_data' : 'qbr_data table consist important metrices  like ocf, fcff and ebitda of companies having quarterly results.',
            
# }

#         filter_prompt = [
#             {
#                 "role": "system",
#                 "content": f"""
#                     Hey GPT, You are a Finance Data Analyst, whose task is to extract table name from the json provided to you if it is related, otherwise you can give empty string as table name, based on the metric name provided by the user.
#                     Meaning of :
#                         `mbr` : Monthly Business Report, 
#                         `qbr` : Quarterly Business Report.

#                     Below are the Guidelines which you have to follow, before picking any table name from the table information JSON provided to you:
#                     1. Understand the metric name provided by the user.
#                     2. Analyze the available tables and their descriptions.
#                     3. Select the most relevant table based on the metric name.
#                     4. Provide a clear explanation of your reasoning.
#                     5. If you think, no table is related to the metric name, then give None as table name. But do not assume by yourself.
#                     Now you have to follow below guidelines to return your response in below format:
#                     Guideline 1: You must return your response in this provided JSON format only, do not delete any key of JSON not even of nested JSON.
#                     Guideline 2: If you are choosing table name `profit-loss` but if the period type is quarterly then suggest table name `quarters` not profit-loss
#                     Guideline 3: First analyse given user metric, and then think what other required parameters or finance terms you might need to calculate that provided user metrics. 
#                     Then start considering table name, Just do not directly assume table name based on the metric provided by user.

#                     Output structure is: 
#                     `{output_structure}`

#                     Now below are the user inputs and available table explanation for which you have to fetch above JSON format response:
#                     Input JSON is:
#                     `{input_structure}`

#                     Table information JSON is:
#                     `{available_tables}`

#                     """
#             }
#         ]

      
#         start_time = time.time()
#         usage_dict = {}

#         try:
#             # --- LLM Call ---
#             raw_response = self.client.chat.completions.create(
#                 model=self.model,
#                 messages=filter_prompt,
#                 temperature=0,
#             )
#             duration_ms = (time.time() - start_time) * 1000

#             # --- Usage tracking ---
#             if raw_response.usage:
#                 usage_dict = {
#                     "input_tokens": raw_response.usage.prompt_tokens,
#                     "output_tokens": raw_response.usage.completion_tokens,
#                     "total_tokens": raw_response.usage.total_tokens,
#                 }

#             # --- Extract and clean text ---
#             output_text = (raw_response.choices[0].message.content or "").strip()
#             if not output_text:
#                 raise ValueError("Empty response from Azure OpenAI")

#             # --- Parse JSON with robust error handling ---
#             try:
#                 response_data = extract_and_parse_json(output_text, input_structure)
#             except Exception as json_error:
#                 logger.error(f"JSON parsing failed even with robust handling: {json_error}")
#                 logger.error(f"Raw LLM output: {output_text}")
                
#                 # Create fallback response
#                 response_data = []
#                 for item in input_structure:
#                     if isinstance(item, str):
#                         metric_name = item
#                     elif isinstance(item, dict):
#                         metric_name = item.get('metric_name', 'unknown')
#                     else:
#                         metric_name = 'unknown'
                    
#                     response_data.append({
#                         "metric_name": metric_name,
#                         "table_name": "None",
#                         "reasoning": f"Critical JSON parsing failure: {str(json_error)}",
#                         "confidence_score": "0.0"
#                     })

#             # Ensure response_data is always a list
#             if not isinstance(response_data, list):
#                 response_data = [response_data]

#             # --- Record successful usage ---
#             if llm_usage_tracker.current_session and response_data:
#                 llm_usage_tracker.record_llm_usage(
#                     llm_type=LLMType.TABLE_FILTERING,
#                     usage_data=usage_dict,
#                     duration_ms=duration_ms,
#                     company_slug='multiple',
#                     metric_name='multiple',
#                     model_name=self.model,
#                     success=True,
#                     additional_info={},
#                 )
            
#             logger.info(f"Table filtering successful: {response_data}, usage: {usage_dict}, duration_ms: {duration_ms}")
#             return response_data, usage_dict, duration_ms

#         except Exception as e:
#             logger.error(f"Error in filter_tables: {str(e)}")
#             duration_ms = (time.time() - start_time) * 1000

#             # --- Record failed usage ---
#             if llm_usage_tracker.current_session:
#                 llm_usage_tracker.record_llm_usage(
#                     llm_type=LLMType.TABLE_FILTERING,
#                     usage_data=usage_dict,
#                     duration_ms=duration_ms,
#                     company_slug='multiple',
#                     metric_name='multiple',
#                     model_name=self.model,
#                     success=False,  # Fixed: should be False for errors
#                     additional_info={'error': str(e)},
#                 )

#             # --- Fallback response ---
#             error_response = []
#             for item in input_structure:
#                 if isinstance(item, str):
#                     metric_name = item
#                 elif isinstance(item, dict):
#                     metric_name = item.get('metric_name', 'unknown')
#                 else:
#                     metric_name = 'unknown'
                
#                 error_response.append({
#                     "metric_name": metric_name,
#                     "table_name": "None",
#                     "reasoning": f"Error during table filtering: {str(e)}",
#                     "confidence_score": "0.0"
#                 })
            
#             return error_response, usage_dict, duration_ms



class FormulaGenerationResult(BaseModel):
    company_slug: str
    query_understanding: str
    formula: str
    formula_explanation: str
    required_parameters: List[str]
    reasoning: str
    confidence_score: float = Field(ge=0.0, le=1.0)

class FinancialAnalysisLLM:
    """Direct LLM-based financial analysis with proper error handling"""
    
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.environ.get('AZURE_API_KEY'),
            api_version="2024-04-01-preview",
            azure_endpoint=os.environ.get('AZURE_API_BASE')
        )
        self.model = "gpt-4.1"


    async def generate_formula(self, 
                        query: str, 
                      ) -> FormulaGenerationResult:
        """Generate mathematical formula and identify required parameters for calculation"""
        
        knowledge_base = {
                            "overview": [
                                {
                                    "table_type": "balance-sheet",
                                    "metrics": [
                                        "Accumulated Depreciation",
                                        "Advance from Customers",
                                        "Borrowings",
                                        "Building",
                                        "CWIP",
                                        "Cash Equivalents",
                                        "Equipments",
                                        "Equity Capital",
                                        "Fixed Assets",
                                        "Furniture n fittings",
                                        "Gross Block",
                                        "Intangible Assets",
                                        "Inventories",
                                        "Investments",
                                        "Land",
                                        "Lease Liabilities",
                                        "Loans n Advances",
                                        "Long term Borrowings",
                                        "Non controlling int",
                                        "Other Assets",
                                        "Other Borrowings",
                                        "Other Liabilities",
                                        "Other asset items",
                                        "Other fixed assets",
                                        "Other liability items",
                                        "Plant Machinery",
                                        "Prov for Doubtful",
                                        "Railway sidings",
                                        "Receivables over 6m",
                                        "Receivables under 6m",
                                        "Reserves",
                                        "Ships Vessels",
                                        "Short term Borrowings",
                                        "Total Assets",
                                        "Total Liabilities",
                                        "Trade Payables",
                                        "Trade receivables",
                                        "Vehicles"
                                    ]
                                },
                                {
                                    "table_type": "cash-flow",
                                    "metrics": [
                                        "Acquisition of companies",
                                        "Cash from Financing Activity",
                                        "Cash from Investing Activity",
                                        "Cash from Operating Activity",
                                        "Direct taxes",
                                        "Dividends paid",
                                        "Dividends received",
                                        "Financial liabilities",
                                        "Fixed assets purchased",
                                        "Fixed assets sold",
                                        "Interest paid fin",
                                        "Interest received",
                                        "Inventory",
                                        "Invest in subsidiaries",
                                        "Investment in group cos",
                                        "Investments purchased",
                                        "Investments sold",
                                        "Loans Advances",
                                        "Net Cash Flow",
                                        "Other WC items",
                                        "Other financing items",
                                        "Other investing items",
                                        "Other operating items",
                                        "Payables",
                                        "Proceeds from borrowings",
                                        "Proceeds from shares",
                                        "Profit from operations",
                                        "Receivables",
                                        "Redemp n Canc of Shares",
                                        "Repayment of borrowings",
                                        "Working capital changes"
                                    ]
                                },
                                {
                                    "table_type": "profit-loss",
                                    "metrics": [
                                        "Change in inventory",
                                        "Depreciation",
                                        "Dividend Payout %",
                                        "EPS in Rs",
                                        "Employee Cost %",
                                        "Exceptional items",
                                        "Exceptional items AT",
                                        "Expenses",
                                        "Interest",
                                        "Manufacturing Cost %",
                                        "Material Cost %",
                                        "Minority share",
                                        "Net Profit",
                                        "OPM %",
                                        "Operating Profit",
                                        "Other Cost %",
                                        "Other Income",
                                        "Other income normal",
                                        "Profit before tax",
                                        "Profit excl Excep",
                                        "Profit for EPS",
                                        "Profit for PE",
                                        "Raw material cost",
                                        "Sales",
                                        "Sales Growth %",
                                        "Tax %"
                                    ]
                                },
                                {
                                    "table_type": "quarters",
                                    "metrics": [
                                        "Depreciation",
                                        "EPS in Rs",
                                        "Employee Cost %",
                                        "Exceptional items",
                                        "Exceptional items AT",
                                        "Expenses",
                                        "Interest",
                                        "Material Cost %",
                                        "Minority share",
                                        "Net Profit",
                                        "OPM %",
                                        "Operating Profit",
                                        "Other Income",
                                        "Other income normal",
                                        "Profit before tax",
                                        "Profit excl Excep",
                                        "Profit for EPS",
                                        "Profit for PE",
                                        "Sales",
                                        "Tax %",
                                        "YOY Profit Growth %",
                                        "YOY Sales Growth %"
                                    ]
                                },
                                {
                                    "table_type": "ratios",
                                    "metrics": [
                                        "Cash Conversion Cycle",
                                        "Days Payable",
                                        "Debtor Days",
                                        "Inventory Days",
                                        "ROCE %",
                                        "Working Capital Days",
                                        "Book Value",
                                        "Current Price",
                                        "Dividend Yield",
                                        "Face Value",
                                        "High / Low",
                                        "Market Cap",
                                        "ROCE",
                                        "ROE",
                                        "Stock P/E"
                                    ]
                                }
                            ]
                        }
                                
        output_structure = [{
                    "metric_name": "metric name for which formula is generated",
                    "formula": "complete mathematical formula to fulfill for metric 1 if multiple metrics found in user query",
                    "required_parameters": ["list of all available metrics used in the formulas to calculate the requested user metrics"],
                    "reasoning": "explanation of approach of your overall selection",
                },
                {
                    "metric_name": "metric name for which formula is generated",
                    "formula": "complete mathematical formula to fulfill for metric 2 if multiple metrics found in user query",
                    "required_parameters": ["list of all available metrics used in the formulas to calculate the requested user metrics"],
                    "reasoning": "explanation of approach of your overall selection",
                }
                ]
        formula_generation_prompt = [
            {
                "role": "system",
                "content": f"""
You are a financial analyst, who has expertise in finance.
Your task is to provide me the formula based on the below availale information or metrices available in my dataset.

Below are the guidelines which you have to follow before generating formula:
guideline 1: First check the available metric names in the provided dataset strcuture, and then think which are the available metrics can help to calculate
given metric in user query, and then write correct formula for that.
guideline 2: Please reverify that you have used only the available metrics from the dataset.
guideline 3: give me the formulas upon analysis in katex format.
guideline 4: give me your output in provided JSON format.

some pre set rules, which you have to consider to give response:
1. Debt-to-Equity Ratio calculation needed Total Debt - consider Total Borrowings as a Total Debt.
2. EBITDA is might be calculated : [EBITDA = Operating Profit + Depreciation + Amortization.]
3. EBIT is might be calculayed. : [EBIT = (Operating Profit / Sales) * 100]


**OUTPUT FORMAT:**
Always return your output in List of JSON format only without deleting any keys:
`{output_structure}`


This is your user query which will contain user metric name:
`{query}`

this is the available dataset of metrics, prioritise writing formula based on this: 
`{knowledge_base}`


"""
            }
        ]
        
        try:
            start_time = time.time()

            # Call Azure OpenAI
            raw_response = self.client.chat.completions.create(
                model=self.model,
                messages=formula_generation_prompt,
                temperature=0,
                max_tokens=20000,
                response_format={"type": "json_object"}
            )

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
                logger.error(f"Invalid JSON from LLM: {output_text}")
                raise ValueError(f"JSON parsing failed: {str(je)}")

            logger.info(f"Formula generation successful : {response_data}, usage: {usage_dict}, duration_ms: {duration_ms}")

            # Record successful usage
            if llm_usage_tracker.current_session:
                llm_usage_tracker.record_llm_usage(
                    llm_type=LLMType.FORMULA_GENERATION,
                    usage_data=usage_dict,
                    duration_ms=duration_ms,
                    company_slug='multiple',
                    metric_name=query,
                    model_name=self.model,
                    success=True,
                    additional_info={
                        'parameters_count': len(response_data.get('required_parameters', [])),
                        'confidence_score': response_data.get('confidence_score', 0.0)
                    }
                )

            # Return as dictionary for compatibility
            return response_data, usage_dict, duration_ms

        except Exception as e:
            logger.error(f"Formula generation failed for {query}: {e}")
            
            # Record failed usage
            if llm_usage_tracker.current_session:
                llm_usage_tracker.record_llm_usage(
                    llm_type=LLMType.FORMULA_GENERATION,
                    usage_data={},
                    duration_ms=0,
                    company_slug='multiple',
                    metric_name=query,
                    model_name=self.model,
                    success=False,
                    error_message=str(e)
                )

            # Return structured error response with all required fields
            error_response = [{
                "formula": "Unable to generate formula due to error",
                "formula_explanation": f"Error occurred: {str(e)}",
                "required_parameters": [],
                "reasoning": f"Technical error prevented formula generation: {str(e)}",
                "confidence_score": 0.0
            }]
            
            return error_response, {}, 0

   


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
            api_key=os.environ.get('AZURE_API_KEY'),
            api_version="2025-01-01-preview",
            azure_endpoint=os.environ.get('AZURE_API_BASE')
        )
        self.model = "gpt-4.1"

    async def RetrievalLLM(self, metrics, company_slug, table_structures):
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
  "retrieval_parameters": [
    {{
      "metric_name": "Original metric name from user query",
      "company": "The same name of the company provided by the user input.",
      "metrics": "Exact metric name from available data OR null if cannot retrieve directly",
      "retrieval_status": true/false,
      "confidence_score": 0.0-1.0,
      "reasoning": "Detailed explanation of mapping decision"
    }}
  ]
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
                logger.error(f"Invalid JSON from LLM: {output_text}")
                raise ValueError(f"JSON parsing failed: {str(je)}")
            if llm_usage_tracker.current_session:
                llm_usage_tracker.record_llm_usage(
                    llm_type=LLMType.DATA_RETRIEVAL,
                    usage_data=usage_dict,
                    duration_ms=duration_ms,
                    company_slug='multiple',
                    metric_name='multiple',
                    model_name=self.model,
                    success=True,
                    additional_info={
                        
                    }
                )
            return response_data
            
        except Exception as e:
            logger.error(f"Error in RetrievelLLM: {str(e)}")
            
            # Record failed usage
            if llm_usage_tracker.current_session:
                llm_usage_tracker.record_llm_usage(
                    llm_type=LLMType.DATA_RETRIEVAL,
                    usage_data={},
                    duration_ms=0,
                    company_slug='multiple',
                    metric_name='multiple',
                    model_name=self.model,
                    success=False,
                    error_message=str(e)
                )

            # Fallback response
            error_response = {
                "company_slug": 'multiple',
                "retrieval_status": False,
                "retrieval_parameters": [],
                "reasoning": f"Error occurred during data retrieval: {str(e)}",
                "confidence_score": "0.0"
            }
            
            return error_response, {}, 0 


