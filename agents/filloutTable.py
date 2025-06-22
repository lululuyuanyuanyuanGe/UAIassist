import sys
from pathlib import Path
import io
import contextlib

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, filter_out_system_messages
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content, read_txt_file
from utilities.modelRelated import model_creation, detect_provider

import uuid
import json
import os
import pandas as pd
from bs4 import BeautifulSoup
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


class FilloutTableState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    data_file_path: list[str]
    supplement_files_path: list[str]
    template_file: str
    rules: str
    combined_data: str
    file_process_code: str
    final_table: str



class FilloutTableAgent:
    def __init__(self, model_name: str = "gpt-4o"):
        self.llm = model_creation(model_name)
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("initialize_state", self.initialize_state)
        graph.add_node("combine_data", self._combine_data)
        graph.add_node("generate_code", self._generate_file_process_code_from_LLM)
        graph.add_node("execute_code", self._execute_code_from_LLM)
        
        # Define the workflow
        graph.add_edge(START, "initialize_state")
        graph.add_edge("initialize_state", "combine_data")
        graph.add_edge("combine_data", "generate_code")
        graph.add_edge("generate_code", "execute_code")
        graph.add_edge("execute_code", END)
        
        # Compile the graph
        return graph.compile()

    
    def initialize_state(self, state: FilloutTableState) -> FilloutTableState:
        """This node will initialize the state of the graph"""
        return {
            "messages": [],
            "data_file_path": [],
            "supplement_files_path": [],
            "template_file": "",
            "rules": "",
            "combined_data": "",
            "file_process_code": "",
            "final_table": "",
        }

    def _combine_data(self, state: FilloutTableState) -> FilloutTableState:
        """This node will combined all the required files into a single text file.
        and that is ready to feed to the model"""
        file_content = []
        
        # Combine data files
        for file in state["data_file_path"]:
            content = read_txt_file(file)
            file_content.append(f"=== Data File: {Path(file).name} ===\n{content}\n")
        
        # Combine supplement files
        for file in state["supplement_files_path"]:
            content = read_txt_file(file)
            file_content.append(f"=== Supplement File: {Path(file).name} ===\n{content}\n")
        
        # Add template file
        if state["template_file"]:
            content = read_txt_file(state["template_file"])
            file_content.append(f"=== Template File: {Path(state['template_file']).name} ===\n{content}\n")

        # Add rules
        if state["rules"]:
            file_content.append(f"=== Rules ===\n{state['rules']}\n")
        
        combined_data = "\n".join(file_content)
        print(f"📋 Combined data from {len(file_content)} sources")
        
        return {
            "combined_data": combined_data
        }
        

    

    def _generate_file_process_code_from_LLM(self, state: FilloutTableState) -> FilloutTableState:
        """We will feed the combined data to the model, and ask it to generate the code to that is used to fill out the table for 
        our new template table"""

        system_prompt = f"""你是一个专业的表格填写代码生成专家。请根据提供的模板、数据文件、补充文件和规则，生成Python代码来填写表格。

        任务要求：
        1. 分析提供的模板表格结构
        2. 根据数据文件和补充文件中的信息填写表格
        3. 遵循所有给定的规则和要求
        4. 生成的代码应该能够直接执行，并输出填写完成的HTML表格

        代码要求：
        - 使用pandas和BeautifulSoup库
        - 代码应该是完整的，可以直接执行
        - 最后将结果表格输出为HTML格式并打印出来
        - 在代码中包含注释说明主要步骤

        提供的数据：
        {state["combined_data"]}

        请生成Python代码（只返回代码，不要其他解释）：
        """

        print("🤖 正在生成表格填写代码...")
        response = self.llm.invoke([SystemMessage(content=system_prompt)])
        print("✅ 代码生成完成")
        
        # Extract code from response if it's wrapped in markdown
        code_content = response.content.strip()
        if code_content.startswith('```python'):
            code_content = code_content[9:]  # Remove ```python
        if code_content.endswith('```'):
            code_content = code_content[:-3]  # Remove ```
        
        return {
            "file_process_code": code_content,
            "messages": [response]
        }
    

    
    def _execute_code_from_LLM(self, state: FilloutTableState) -> FilloutTableState:
        """We will run the code from the model, and get the result. use exec() to execute the code in memroy"""
        code = state["file_process_code"]
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        print("🚀 正在执行生成的代码...")
        
        # Prepare execution environment
        global_vars = {
            "pd": pd, 
            "BeautifulSoup": BeautifulSoup,
            "Path": Path,
            "json": json,
            "re": re
        }
        local_vars = {}
        
        try:
            with contextlib.redirect_stdout(output_buffer):
                with contextlib.redirect_stderr(error_buffer):
                    exec(code, global_vars, local_vars)
            
            output = output_buffer.getvalue()
            errors = error_buffer.getvalue()
            
            if errors:
                print(f"⚠️ 执行过程中有警告: {errors}")
            
            print("✅ 代码执行成功")
            
            return {
                "final_table": output,
                "result_vars": local_vars,
                "execution_successful": True
            }
            
        except Exception as e:
            error_msg = f"代码执行错误: {str(e)}"
            print(f"❌ {error_msg}")
            
            return {
                "final_table": f"执行失败: {error_msg}",
                "execution_error": error_msg,
                "execution_successful": False
            }

    def run_fillout_table_agent(self, 
                                   data_file_paths: List[str] = None,
                                   supplement_file_paths: List[str] = None,
                                   template_file_path: str = None,
                                   rules: str = None) -> FilloutTableState:
        """
        Run the fillout table agent with the provided inputs.
        
        Args:
            data_file_paths: List of paths to data files
            supplement_file_paths: List of paths to supplement files
            template_file_path: Path to the template file
            rules: Rules for filling out the table
            
        Returns:
            FilloutTableState: The final state with the filled table
        """
        print("🚀 启动表格填写代理...")
        
        # Create initial state
        initial_state = {
            "messages": [],
            "data_file_path": data_file_paths or [],
            "supplement_files_path": supplement_file_paths or [],
            "template_file": template_file_path or "",
            "rules": rules or "",
            "combined_data": "",
            "file_process_code": "",
            "final_table": "",
        }
        
        print(f"📁 数据文件: {len(initial_state['data_file_path'])} 个")
        print(f"📋 补充文件: {len(initial_state['supplement_files_path'])} 个")
        print(f"📄 模板文件: {'有' if template_file_path else '无'}")
        print(f"📝 规则: {'有' if rules else '无'}")
        
        try:
            # Run the graph
            result = self.graph.invoke(initial_state)
            
            # Print results
            if result.get("execution_successful", False):
                print("🎉 表格填写完成！")
                print("\n" + "="*50)
                print("📊 生成的表格:")
                print("="*50)
                print(result["final_table"])
                print("="*50)
            else:
                print("❌ 表格填写失败")
                if "execution_error" in result:
                    print(f"错误: {result['execution_error']}")
            
            return result
            
        except Exception as e:
            print(f"❌ 执行过程中发生错误: {e}")
            return {
                "messages": [],
                "data_file_path": initial_state["data_file_path"],
                "supplement_files_path": initial_state["supplement_files_path"],
                "template_file": initial_state["template_file"],
                "rules": initial_state["rules"],
                "combined_data": "",
                "file_process_code": "",
                "final_table": f"执行失败: {str(e)}",
                "execution_successful": False,
                "execution_error": str(e)
            }
    
    def create_fillout_table_agent_interface(self) -> gr.Interface:
        """Create a Gradio interface for the fillout table agent"""
        
        def run_agent_interface(data_files, supplement_files, template_file, rules):
            """Interface function for Gradio"""
            try:
                # Process uploaded files
                data_file_paths = [f.name for f in data_files] if data_files else []
                supplement_file_paths = [f.name for f in supplement_files] if supplement_files else []
                template_file_path = template_file.name if template_file else None
                
                # Run the agent
                result = self.run_fillout_table_agent(
                    data_file_paths=data_file_paths,
                    supplement_file_paths=supplement_file_paths,
                    template_file_path=template_file_path,
                    rules=rules
                )
                
                # Return results
                success = result.get("execution_successful", False)
                table_output = result.get("final_table", "")
                code_output = result.get("file_process_code", "")
                
                status = "✅ 成功" if success else "❌ 失败"
                
                return status, table_output, code_output
                
            except Exception as e:
                return f"❌ 错误: {str(e)}", "", ""
        
        # Create the interface
        interface = gr.Interface(
            fn=run_agent_interface,
            inputs=[
                gr.File(label="数据文件", file_count="multiple", file_types=[".txt", ".html"]),
                gr.File(label="补充文件", file_count="multiple", file_types=[".txt", ".html"]),
                gr.File(label="模板文件", file_types=[".txt", ".html"]),
                gr.Textbox(label="填写规则", lines=5, placeholder="请输入表格填写的规则和要求...")
            ],
            outputs=[
                gr.Textbox(label="执行状态"),
                gr.HTML(label="生成的表格"),
                gr.Code(label="生成的代码", language="python")
            ],
            title="📊 智能表格填写代理",
            description="上传数据文件、补充文件和模板文件，设置填写规则，自动生成填写完成的表格。",
            theme=gr.themes.Soft()
        )
        
        return interface
        