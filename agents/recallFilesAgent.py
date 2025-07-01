import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content
from utilities.modelRelated import invoke_model

import uuid
import json
import os
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re

from langgraph.graph import StateGraph, END, START
from langgraph.constants import Send
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

class RecallFilesState(TypedDict):
    messages: list[BaseMessage]
    related_files: list[str]
    headers_mapping: dict[str, str]
    template_structure: str
    headers_mapping_: dict[any, any]

class RecallFilesAgent:
    def __init__(self):
        self.graph = self._build_graph()


    def _build_graph(self):
        pass

    def _create_initial_state(self, session_id: str = "1") -> RecallFilesState:
        pass

    

    def _recall_relative_files(self, state: RecallFilesState) -> RecallFilesState:
        """根据要生成的表格模板，从向量库中召回相关文件"""
        with open('data.json', 'r') as f:
            file_content = f.read()
        
        system_promt = f"""
        你是一个专业的文件分析专家，你的任务是根据用户提供的表格模板，里面的表头，总结，文件名等 从向量库中召回相关文件
        相关的文件可能是带有数据的表格，或者其他补充文件用于辅助填表，你需要根据向量库里面文件总结，表头内容等判断
        模板表格内容:
        {state["template_structure"]}
        文件库内容:
        {file_content}
        返回严格为一个数组，包含所有相关文件的全名，不要有任何其他内容
        """

        response = invoke_model(system_promt, model_name = "Qwen/Qwen3-32b", messages = AIMessage(content = system_promt))
        state["related_files"] = response
        return {
            "messages": [AIMessage(content = response)]
        }
    

    def _determine_the_mapping_of_headers(self, state: RecallFilesState) -> RecallFilesState:
        """确认模板表头和数据文件表头的映射关系"""
        state
