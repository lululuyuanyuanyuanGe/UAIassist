from typing import Dict, List, Optional, Any, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
import os



def invoke_model(model_name : str, messages : List[BaseMessage]) -> str:
    """调用大模型"""
    llm = ChatOpenAI(
        model = model_name,
        api_key=os.getenv("SILICONFLOW_API_KEY"), 
        base_url="https://api.siliconflow.cn/v1",
        streaming=True,
        temperature=0.2  # 启用流式
    )

    full_response = ""

    for chunk in llm.stream(messages):
        chunk_content = chunk.content
        print(chunk_content, end="", flush=True)
        full_response += chunk_content
    
    return full_response

def invoke_model_with_tools(model_name : str, messages : List[BaseMessage], tools : List[dict]) -> Any:
    """调用大模型并使用工具"""
    llm = ChatOpenAI(
        model = model_name,
        api_key=os.getenv("SILICONFLOW_API_KEY"), 
        base_url="https://api.siliconflow.cn/v1",
        streaming=True,
        temperature=0.2
    )
    
    # 绑定工具到模型
    llm_with_tools = llm.bind_tools(tools)
    
    # 首先尝试非流式调用以检查是否有工具调用
    response = llm_with_tools.invoke(messages)
    
    # 如果有工具调用，直接返回完整响应
    if hasattr(response, 'tool_calls') and response.tool_calls:
        # 打印文本内容（如果有）
        if response.content:
            print(response.content, end="", flush=True)
        return response
    
    # 如果没有工具调用，使用流式输出文本内容
    if response.content:
        print(response.content, end="", flush=True)
    
    # 返回完整响应以便调用者处理
    return response