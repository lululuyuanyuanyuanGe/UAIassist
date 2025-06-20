import sys
from pathlib import Path
import time

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content
from utilities.modelRelated import model_creation

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


class SendState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

class SendAgent:
    def __init__(self, model_name: str = "gpt-4o"):
        self.model = model_creation(model_name, temperature=0.0)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(SendState)
        graph.add_node("node_A", self._node_A)
        graph.add_node("node_B", self._node_B)
        graph.add_node("node_C", self._node_C)
        graph.add_node("node_D", self._node_D)
        graph.add_node("node_E", self._node_E)
        graph.add_node("node_F", self._node_F)

        graph.add_edge(START, "node_A")
        graph.add_conditional_edges("node_A", self._route_after_node_A)
        graph.add_edge("node_B", "node_F")
        graph.add_edge("node_C", "node_F")
        graph.add_edge("node_D", "node_F")
        graph.add_edge("node_E", "node_F")
        graph.add_edge("node_F", END)
        return graph.compile()
    
    def create_initial_state(self) -> SendState:
        return {
            "messages": ""
        }
    
    def run_send_agent(self):
        self.graph.invoke(self.create_initial_state())

    def _node_A(self, state: SendState):
        """Init state"""
        print("node_A")

    def _node_B(self, state: SendState):
        """Parallel state"""
        time.sleep(8)
        print("node_B")

    def _node_C(self, state: SendState):
        """Parallel state"""
        time.sleep(6)
        print("node_C")

    def _node_D(self, state: SendState):
        """Parallel state"""
        time.sleep(4)
        print("node_D")
    
    def _node_E(self, state: SendState):
        """Parallel state"""
        time.sleep(2)
        print("node_E")

    def _node_F(self, state: SendState):
        """End State"""
        print("node_F")

    def _route_after_node_A(self, state: SendState):

        sends = []
        sends.append(Send("node_B", state))
        sends.append(Send("node_C", state))
        sends.append(Send("node_D", state))
        sends.append(Send("node_E", state))
        return sends


send_agent = SendAgent()
send_agent.run_send_agent()