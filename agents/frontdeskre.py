import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, filter_out_system_messages
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content
from utilities.modelRelated import model_creation, detect_provider

import uuid
import json
import os
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool


load_dotenv()


class FrontdeskState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    upload_files_path: list[str]
    upload_files_processed: list[str]
    upload_template: str
    session_id: str
    
class FrontdeskAgent:
    """
    用于处理用户上传的模板，若未提供模板，和用户沟通确定表格结构
    """



    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.llm = model_creation(model_name=model_name, temperature=2)



    def _build_graph(self) -> StateGraph:
        """This function will build the graph of the frontdesk agent"""

        graph = StateGraph(FrontdeskState)

        graph.add_node("entry", self._entry_node)
        graph.add_node("collect_user_input", self._collect_user_input)
        graph.add_node("route_after_collect_user_input", self._route_after_collect_user_input)
        graph.add_node("file_upload", self._file_upload)

        graph.add_edge(START, "entry")
        graph.add_edge("entry", "collect_user_input")
        graph.add_edge("collect_user_input", "route_after_collect_user_input")
        graph.add_edge("route_after_collect_user_input", "file_upload")
        graph.add_edge("file_upload", END)
        return graph



    def _entry_node(self, state: FrontdeskState) -> FrontdeskState:
        """This is the starting node of our frontdesk agent"""
        # Enrich this later, it should include a short description of the agent's ability and how to use it
        print("你好，我是一个表格处理助手！")
        # Here we will add a human in the loop to get user's response
        system_prompt = ""



    def _collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """This is the node where we get user's input"""
        user_input = interrupt("用户：")
        return {"messages": user_input}
    


    def _route_after_collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """This node determines the route after we collect the user's input"""
        # We should let LLM decide the route
        
        user_upload_files = detect_and_process_file_paths(state["messages"][-1])
        # Filter out the new uploaded files
        new_upload_files = [item for item in user_upload_files if item not in state["upload_files_path"]]
        if new_upload_files:
            state["upload_files_path"] = user_upload_files
            return "file_upload"
        
        # User didn't upload new files
        elif not user_upload_files:
            return "no_file_upload"
    
        # User upload repeated files:
        else:
            state["messages"].append(HumanMessage(content=f"文件重复上传：{user_upload_files}"))
            return "previous_node"
    


    def _file_upload(self, state: FrontdeskState) -> FrontdeskState:
        """This node will upload user's file to LLM"""
        result = retrieve_file_content(state["upload_files_path"], state["session_id"])
        state["upload_files_processed"] = result
        print(f"✅ File uploaded: {state['upload_files_processed']}")
        return "check_template"
    


