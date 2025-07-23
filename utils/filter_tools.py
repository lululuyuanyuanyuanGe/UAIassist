import sys
from pathlib import Path
import json

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated, Union

from utils.modelRelated import invoke_model, invoke_model_with_tools

from pathlib import Path
# Create an interactive chatbox using gradio
from dotenv import load_dotenv


from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

# import other agents
from agents.processUserInput import ProcessUserInputAgent
from agents.recallFilesAgent import RecallFilesAgent
from agents.filloutTable import FilloutTableAgent
from agents.designExcelAgent import DesignExcelAgent


def 