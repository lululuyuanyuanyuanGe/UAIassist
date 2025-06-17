import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, create_assistant_with_files, filter_out_system_messages, detect_and_process_file_paths, upload_file_to_LLM
import uuid
import json
import os
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re

load_dotenv()

# 用于处理用户上传文件
from openai import OpenAI
client = OpenAI(
    api_key = os.environ.get("OPENAI_API_KEY")
)

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


# 定义前台接待员状态
class FrontdeskState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    table_structure: dict
    table_info: dict
    additional_requirements: dict
    gather_complete: bool
    has_template: bool
    complete_confirm: bool
    uploaded_files: list  # 用户提供的文件路径
    uploaded_files_id: list
    previous_node: str  # Track the previous node before file upload
    failed_uploads: list  # Track files that failed to upload
