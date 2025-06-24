import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))=



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


# import other agents
from agents.processUserInput import ProcessUserInputAgent

load_dotenv()


class FrontdeskState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    messages_s: Annotated[list[BaseMessage], add_messages]
    table_structure: str
    previous_node: str # Track the previous node
    session_id: str
    


class FrontdeskAgent:
    """
    用于处理用户上传的模板，若未提供模板，和用户沟通确定表格结构
    """



    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.llm_c = model_creation(model_name=model_name, temperature=2) # complex logic use user selected model
        self.llm_s = model_creation(model_name="gpt-3.5-turbo", temperature=2) # simple logic use 3-5turbo



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

    def _collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """This node will use the ProcessUserInputAgent to collect user's input"""
        process_user_input_agent = ProcessUserInputAgent()
        
        process_user_input_agent.run_process_user_input_agent(state["messages"][-1].content)
        return {"messages": process_user_input_agent.state["messages"]}

    def _check_template(self, state: FrontdeskState) -> FrontdeskState:
        """This node will check if the user has provided a template"""
        system_prompt = """你是一个智能填表助手智能体，你需要根据用户的输入来决定下一步的行动，如果用户提供了模板，
        请返回[YES]，否则返回[NO]，另外用户可能上传文件"""
        # user turbo at here
        response = self.llm_s.invoke([SystemMessage(content=system_prompt)] + state["messages"][-1])
        return {"messages": response}
    


    def _route_after_check_template(self, state: FrontdeskState) -> str:
        """This node will route the agent to the next node based on the user's input"""
        if state["messages"][-1].content == "[YES]":
            return "template_provided"
        else:
            return "no_template_provided"
        


    def _analyze_template(self, state: FrontdeskState) -> FrontdeskState:
        """This node will analyze the template to determine if it a complex template
        (both row, column headers) or a simple template (only column headers)"""
        system_prompt = """你需要根据html代码判断这个模板是复杂模板还是简单模板，判断规则为：
        1. 如果html代码中包含row和column headers，则返回[YES]
        2. 如果html代码中只包含column headers，则返回[NO]
        3. 如果html代码中既包含row headers又包含column headers，则返回[YES]
        4. 如果html代码中既包含row headers又包含column headers，则返回[YES]
        5. 如果html代码中既包含row headers又包含column headers，则返回[YES]
        """
        # use 3-5turbo at here
    


    def _complex_template_analysis(self, state: FrontdeskState) -> FrontdeskState:
        """This node will be use to analyze the complex table template, we will skip for now"""
        pass

    def _simple_template_analysis(self, state: FrontdeskState) -> FrontdeskState:
        """This node will be use to analyze the simple table template, we"""
        pass







def _analyze_uploaded_files_related_to

# after we analyze the how related the uploaded files to our system, we will determine if it is related to the
# question the LLM just asked, if that it is related, we will store the content of the file in the state
# and pass it for the LLM to analyze