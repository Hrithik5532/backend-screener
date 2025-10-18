import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain.tools import StructuredTool
from langchain_core.messages import HumanMessage
from langchain_core.messages.ai import AIMessageChunk
from langchain_core.messages.tool import ToolMessage
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from Main.agents.tools.decom_tool import DecomposeQuery
from Main.agents.tools.retrieval_tool import retrieve_metrics
from Main.agents.tools.sql_tool import get_financial_data_tool
from .tools.stockprice import get_indian_stock_info
from Main.agents.prompt import  construct_db_chat_prompt
from psycopg_pool import AsyncConnectionPool
from urllib.parse import quote_plus

load_dotenv()

model_name = os.getenv("DOC_CHAT_OPENAI_MODEL", "gpt-4.1")

model = AzureChatOpenAI(
    model=model_name,
    max_retries=5,
    temperature=0,
    stream_options={"include_usage": True},
)

# Add your database URI from environment or settings
password = 'sky@#!123'
encoded_password = quote_plus(password)

DB_URI = f'postgresql://screeneradmin:{encoded_password}@52.22.136.221:5432/screenerdb'

async def db_agents_chat_stream_2(
    user: str,
    query: str,
    businesses: Optional[List[str]] = None,
    timeout_: int = 55,
):
    id_ = str(uuid.uuid4())
    full_response = ""
    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
    }

    try:
        logging.info("Agent insider function")
    
        query_decomposer = DecomposeQuery(businesses)
        query_decomposer_tool = query_decomposer.create_tool()

        tools = [
            get_indian_stock_info,
            query_decomposer_tool,
            retrieve_metrics,
            get_financial_data_tool,
        ]

        # Option 1: WITHOUT AsyncConnectionPool (simpler, recommended)
        langgraph_agent_executor = create_react_agent(
            model,
            tools,
            prompt=construct_db_chat_prompt(businesses=businesses),
        )
        
        config = {
            "configurable": {
                "user_name": user,
            }
        }
        
        try:
            query_id_prompt = f"""
                Only Provide the response based on the information provided else reply with:
                Example :
                Mention the question and say no information found
                
                No information should be provided out of the mentioned data.
                """

            async for msg, metadata in langgraph_agent_executor.astream(
                {
                    "messages": [
                        ("system", query_id_prompt),
                        ("human", query),
                    ]
                },
                config,
                stream_mode="messages",
            ):
                token_usage_data = getattr(msg, "usage_metadata", {})
                
                if msg.content:
                    content = getattr(msg, "content", "")
                    additional_kwargs = getattr(msg, "additional_kwargs", "")
                    response_metadata = getattr(msg, "response_metadata", "")
                    id_val = getattr(msg, "id", "")
                    tool_call_id = getattr(msg, "tool_call_id", "")

                    if (
                        content
                        and not additional_kwargs
                        and not response_metadata
                        and id_val
                        and not tool_call_id
                    ):
                        full_response += msg.content
                        yield msg.content
                        
        except Exception as e:
            logging.error(f"Error in streaming: {str(e)}")
            yield ''

        # Option 2: WITH AsyncConnectionPool (if you need checkpointer)
        # Uncomment this if you need the connection pool and add DB_URI
        """
        if not DB_URI:
            raise ValueError("DATABASE_URL not configured in environment")
            
        async with AsyncConnectionPool(
            conninfo=DB_URI,  # IMPORTANT: Add this line
            max_size=5,
            kwargs=connection_kwargs,
        ) as pool:
            # from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            # checkpointer = AsyncPostgresSaver(pool)

            langgraph_agent_executor = create_react_agent(
                model,
                tools,
                prompt=construct_db_chat_prompt(businesses=businesses),
                # checkpointer=checkpointer  # Uncomment if using checkpointer
            )
            
            config = {
                "configurable": {
                    "user_name": user,
                }
            }
            
            try:
                query_id_prompt = f'''
                    Only Provide the response based on the information provided else reply with:
                    Example :
                    Mention the question and say no information found
                    
                    No information should be provided out of the mentioned data.
                    '''

                async for msg, metadata in langgraph_agent_executor.astream(
                    {
                        "messages": [
                            ("system", query_id_prompt),
                            ("human", query),
                        ]
                    },
                    config,
                    stream_mode="messages",
                ):
                    if msg.content:
                        content = getattr(msg, "content", "")
                        additional_kwargs = getattr(msg, "additional_kwargs", "")
                        response_metadata = getattr(msg, "response_metadata", "")
                        id_val = getattr(msg, "id", "")
                        tool_call_id = getattr(msg, "tool_call_id", "")

                        if (
                            content
                            and not additional_kwargs
                            and not response_metadata
                            and id_val
                            and not tool_call_id
                        ):
                            full_response += msg.content
                            yield msg.content
            except Exception as e:
                logging.error(f"Error in streaming: {str(e)}")
                yield ''
        """

    except Exception as error_:
        logging.error(f"Got error in db_agents_chat_stream_2: {str(error_)}")
        generic_response = (
            "\n\nIt seems something went wrong on my end, and I encountered "
            "an internal server error. I apologize for the inconvenience. \n\nLet me try to resolve "
            "this issue for you. Could you please provide more details or clarify your request? "
            "Alternatively, you can try rephrasing it, and I'll do my best to assist you!"
        )
        yield generic_response