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


# Define the state for dataCollector
class dataCollectorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    validation_pass: bool
    related_files = list[Path]

class DataCollectorAgent:
    """This agent will collect the data to fill out the form from the data base"""

    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.llm = ChatOpenAI(model=model_name, temperature=0.1)
        self.tools = []
        self.llm_with_tool = self.llm.bind_tools(self.tools)
        self.memory = MemorySaver()
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(dataCollectorState)

        workflow.add_node("select_file", self._select_related_file_from_DB)
        workflow.add_node("validate_file_selection", self._validate_selected_file)

        workflow.add_conditional_edges(
            "validate",
            self._validate_selected_file,
            {
                True: "",
                False: ""
            }
        )
        

    def _select_related_file_from_DB(self, state: dataCollectorState) -> dataCollectorState:
        # For now the DB will just simply be a JSON file that contains the all the file name and
        # tags for description, later we will vectorize them as we get the entire data
        """
        Load the files from data.json and let LLM decide which files contain related data
        """
        with open('data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Here we should also add the state from the frontdesk agent that has the information about the table
        system_prompt = """你是一个填表助手，请根据需求从data.json{data}中召回可能存有相关数据的文件，
        你的返回内容必须是一个数列，包含所有文件的地址"""
        system_message = SystemMessage(content=system_prompt)
        response = self.llm.invoke(system_message)
        return {
            "messages": [system_message, response]
        }
    
    def _validate_selected_file(self, state: dataCollectorState) -> dataCollectorState:
        """This function will check the selected files to make sure the selection is correct"""
        with open('data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        system_prompt = """你是一个验证专家，你需要检查上一个专家是否选择了正确的文件{data}, 如果你认为文件选择正确，请在回复结尾处加入
        ["YES"]"""
        system_message = SystemMessage(content=system_prompt)
        response = self.llm.invoke([state["messages"][-1], system_message])
        state["messages"] = state["messages"] + response
        validation_pass = "[YES]" in response.content.upper()
        return validation_pass
    
    def _retrieve_files_content(self, state: dataCollectorState) -> dataCollectorState:
        """This node will retrieve the content of the related files"""



