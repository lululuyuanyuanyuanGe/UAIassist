import sys
from pathlib import Path
import io
import contextlib

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utils.visualize_graph import save_graph_visualization
from utils.message_process import build_BaseMessage_type, filter_out_system_messages
from utils.file_process import (read_txt_file, 
                                    process_excel_files_with_chunking)
from utils.modelRelated import invoke_model
from utils.html_generator import (
    extract_empty_row_html_code_based,
    extract_headers_html_code_based,
    extract_footer_html_code_based,
    transform_data_to_html_code_based,
    combine_html_parts
)

import os
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv


from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.constants import Send
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool


# import other agents
from agents.processUserInput import ProcessUserInputAgent
from agents.filloutTable import FilloutTableAgent


class FillterGeneratedTableState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    table_structure: str
    user_requirement: str
    village_name: str
    session_id: str
    route_decision: str



class FillterGeneratedTableAgent:
    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(FillterGeneratedTableState)
        graph.add_node("collect_user_requirement", self._collect_user_requirement)
        graph.add_node("modify_template", self._modify_template)
        graph.add_node("generate_code_to_filter_csv_data", self._generate_code_to_filter_csv_data)
        graph.add_node("execute_code_to_filter_csv_data", self._execute_code_to_filter_csv_data)
        graph.add_node("summary_error_message", self._summary_error_message)
        
        graph.add_edge(START, "collect_user_requirement")
        graph.add_conditional_edges("collect_user_requirement", self._route_after_collect_user_requirement)
        graph.add_edge("modify_template")

    def _create_initial_state(self, session_id: str, template_file: str, data_file_path: list[str], headers_mapping: dict[str, str]) -> FillterGeneratedTableState:
        pass

    def _collect_user_requirement(self, state: FillterGeneratedTableState) -> FillterGeneratedTableState:
        """这个节点用于收集用户的需求"""
        ai_message = AIMessage(content="你对表格生成结果满意吗？要做修改吗？")
        process_user_input_agent = ProcessUserInputAgent()
        final_state = process_user_input_agent.run_process_user_input_agent(session_id=state["session_id"], 
                                                              previous_AI_messages=[ai_message], 
                                                              current_node="modify_generated_table", 
                                                              village_name=state["village_name"])
        return {"route_decision": final_state["next_node"]}
    
    def _route_after_collect_user_requirement(self, state: FillterGeneratedTableState) -> str:
        """这个节点用于路由到下一个节点"""
        sends = []
        if state["route_decision"] == "reconstruct_table_structure":
        sends = []
        sends.append(Send("modify_template", state))
        sends.append(Send("generate_code_to_filter_csv_data", state))
        return sends

    

    def _modify_template(self, state: FillterGeneratedTableState) -> FillterGeneratedTableState:
        """这个节点用于修改模板"""
        pass

    def _generate_code_to_filter_csv_data(self, state: FillterGeneratedTableState) -> FillterGeneratedTableState:
        """这个节点用于生成代码在synthesized_table.csv中过滤数据"""
        system_prompt = f"""
        你是一个经验丰富的数据分析师，现在需要你根据用户的需求，生成代码在synthesized_table.csv中过滤数据。
        用户的需求是：{state["user_requirement"]}
        """
        response = invoke_model(model="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=state["user_requirement"])])

    def _execute_code_to_filter_csv_data(self, state: FillterGeneratedTableState) -> FillterGeneratedTableState:
        """这个节点用于执行代码在synthesized_table.csv中过滤数据"""
        pass

    def _route_after_execute_code_to_filter_csv_data(self, state: FillterGeneratedTableState) -> str:

        pass
    
    def _summary_error_message(self, state: FillterGeneratedTableState) -> FillterGeneratedTableState:
        pass


    def  _fillout_new_table(self, state: FillterGeneratedTableState) -> FillterGeneratedTableState:
        fillout_table_agent = FilloutTableAgent()
        fillout_table_agent.run_fillout_table_agent(state["session_id"], state["template_file"], 
                                                    state["data_file_path"], state["headers_mapping"],
                                                    modify_after_first_fillout=True)
        return state


    
    

