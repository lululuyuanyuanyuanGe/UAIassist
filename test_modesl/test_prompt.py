from openai import OpenAI
from typing import List, Dict, Any
from dotenv import load_dotenv
import os

from langgraph.graph import StateGraph, END, START
from langgraph.constants import Send
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()



def invoke_model(model_name : str, messages : List[BaseMessage]) -> str:
    """调用大模型"""
    llm = ChatOpenAI(
        model = model_name,
        api_key=os.getenv("SILICONFLOW_API_KEY"), 
        base_url="https://api.siliconflow.cn/v1",
        streaming=True  # 启用流式
    )

    full_response = ""

    for chunk in llm.stream(messages):
        chunk_content = chunk.content
        print(chunk_content, end="", flush=True)
        full_response += chunk_content
    
    return full_response


messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Tell me about artificial intelligence")
]

response = invoke_model(model_name="Qwen/Qwen2.5-72B-Instruct", messages=messages)