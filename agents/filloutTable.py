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
from utilities.modelRelated import invoke_model

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

load_dotenv()

class FilloutTableState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    data_file_path: list[str]
    supplement_files_path: list[str]
    template_file: str
    rules: str
    combined_data: str
    file_process_code: str
    final_table: str
    error_message: str
    execution_successful: bool
    retry: int



class FilloutTableAgent:
    def __init__(self, model_name: str = "gpt-4o"):
        self.llm = model_creation(model_name)
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("combine_data", self._combine_data)
        graph.add_node("generate_code", self._generate_file_process_code_from_LLM)
        graph.add_node("execute_code", self._execute_code_from_LLM)
        
        # Define the workflow
        graph.add_edge(START, "combine_data")
        graph.add_edge("combine_data", "generate_code")
        graph.add_edge("generate_code", "execute_code")
        graph.add_conditional_edges("execute_code", self._route_after_execute_code, {"generate_code": "generate_code", "END": END})
        
        # Compile the graph
        return graph.compile()

    
    def create_initialize_state(self, template_file: str = None, rules: str = None, data_file_path: list[str] = None, supplement_files_path: list[str] = None) -> FilloutTableState:
        """This node will initialize the state of the graph"""
        return {
            "messages": [],
            "data_file_path": data_file_path,
            "supplement_files_path": supplement_files_path,
            "template_file": template_file,
            "rules": rules,
            "combined_data": "",
            "file_process_code": "",
            "final_table": "",
            "error_message": "",
            "execution_successful": True,
            "retry": 0
        }

    def _combine_data(self, state: FilloutTableState) -> FilloutTableState:
        """This node will combined all the required files into a single text file.
        and that is ready to feed to the model"""
        file_content = []
        
        # Combine data files
        for file in state["data_file_path"]:
            content = file + "\n" + read_txt_file(file)
            file_content.append(f"=== Data File: {Path(file).name} ===\n{content}\n")
        
        # Combine supplement files
        # for file in state["supplement_files_path"]:
        #     content = file + "\n" + read_txt_file(file)
        #     file_content.append(f"=== Supplement File: {Path(file).name} ===\n{content}\n")
        
        # Add template file
        if state["template_file"]:
            content = state["template_file"] + "\n" + read_txt_file(state["template_file"])
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

        error_block = f"\n【上一次执行错误】\n{state['error_message']}" if state["error_message"] else ""
        code_block  = f"\n【上一次生成的代码】\n{state['file_process_code']}" if state["file_process_code"] else ""
        system_prompt = f"""
你是一位专业的 Python 表格处理工程师，擅长使用 BeautifulSoup 和 pandas 操作 HTML 表格，并将结构化数据自动填写到模板表格中。

【你的任务】
用户会上传以下文件：
1. 一个 HTML 格式的模板文件（通常是 Excel 导出的空表格）；
2. 一个或多个 HTML 格式的数据文件（例如党员名册）；
3. 补充说明文档（可选，可能包括字段含义、计算规则等）。

你需要根据这些输入，生成一个完整可运行的 Python 脚本，请仔细思考，一步一步的思考，并完成以下任务：

1. 使用 BeautifulSoup 对所有 HTML 文件进行 DOM 解析；
2. 从数据文件中逐行提取 `<tr>` 和 `<td>` 内容，构造中间结构（例如 DataFrame），**严禁使用 `pandas.read_html()` 自动解析整个表格**；
3. **不能通过字段名访问字段值**，必须使用列索引或说明中提供的映射顺序；
4. 如果需要填写的字段内容需要计算（如“党龄”、“补贴”），必须根据说明编写 Python 函数实现；
5. **模板表格中的原始数据行不能直接修改或重用，必须使用 `copy.deepcopy()` 备份模板行结构，并根据数据数量循环克隆并插入**；
6. 不依赖模板中原有数据行数，必须覆盖全部数据；
7. 最终生成的新 HTML 文件，其结构和格式必须与原模板保持一致，仅替换 `<td>` 中的文本内容，你也可以用代码完全重新生成填入数据的文件，但是需要保证文件的结构和格式与原模板保持一致
8. 模板内已有的空白行需要删除，而不是保留
9. 输出路径为：`D:\\asianInfo\\ExcelAssist\\agents\\output\\老党员补贴_结果.html`

【关键技术规范】
- 使用 `BeautifulSoup` 解析 HTML；
- 使用 `copy.deepcopy()` 克隆模板 `<tr>` 行；
- 使用 `DataFrame` 临时管理提取后的数据行；
- 使用 `.insert()` 将新行插入 `<table>` 末尾；
- 每行 `<td>` 内容需用 `.string = str(...)` 逐个赋值；
- 输出时用 `f.write(str(soup))` 写入完整 HTML。

【调试机制】
- 如果你生成的代码运行出错，系统会返回错误信息和之前的代码；
- 你需要根据错误分析并修复代码，重新输出一个完整、可执行的 Python 脚本。

【输出要求】
- 仅输出纯 Python 脚本代码；
- 不得输出 markdown、注释、解释性文字；
- 代码应为完整可执行脚本，可直接传入 `exec()` 执行；
- 输出路径为：`D:\\asianInfo\\ExcelAssist\\agents\\output\\老党员补贴_结果.html`

【当前输入】
以下是用户上传的文件和说明：
{state["combined_data"]}

{code_block}{error_block}

请生成符合要求的完整 Python 脚本，或在原基础上修复错误并补充完善。
"""







        print("🤖 正在生成表格填写代码...")
        response = self.llm.invoke([SystemMessage(content=system_prompt)])
        print("✅ 代码生成完成")
        
        # Extract code from response if it's wrapped in markdown
        code_content = response.content.strip()
        if code_content.startswith('```python'):
            code_content = code_content[9:]  # Remove ```python
        elif code_content.startswith('```'):
            code_content = code_content[3:]  # Remove ```
            
        if code_content.endswith('```'):
            code_content = code_content[:-3]  # Remove ```
            
        # Clean up the code - remove any potential trailing characters
        code_content = code_content.strip()
        
        state["retry"] = state.get("retry", 0) + 1
        if state["retry"] > 3: 
            print("❌ 已重试 3 次仍失败，终止。")
            return "END"
        
        return {
            "file_process_code": code_content,
            "messages": [response],
            "execution_successful": False     # code not yet run
        }
    

    
    def _execute_code_from_LLM(self, state: FilloutTableState) -> FilloutTableState:
        """We will run the code from the model, and get the result. use exec() to execute the code in memroy"""
        code = state["file_process_code"]
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        print("🚀 正在执行生成的代码...")
        
        # Print the code for debugging
        print("📝 生成的代码:")
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            print(f"{i:2d}: {line}")
        print("-" * 50)
        
        # Prepare execution environment
        global_vars = {
            "pd": pd, 
            "BeautifulSoup": BeautifulSoup,
            "Path": Path,
            "json": json,
            "re": re,
            "datetime": datetime
        }
        
        try:
            # Directly execute the code
            with contextlib.redirect_stdout(output_buffer):
                with contextlib.redirect_stderr(error_buffer):
                    exec(code, global_vars)
            
            output = output_buffer.getvalue()
            errors = error_buffer.getvalue()
            
            if errors:
                print(f"⚠️ 执行过程中有警告: {errors}")
            
            # Check if the output contains error messages from the generated code
            error_patterns = [
                "An error occurred:",
                "Error:",
                "Exception:",
                "Traceback",
                "NameError:",
                "KeyError:",
                "AttributeError:",
                "TypeError:",
                "ValueError:"
            ]
            
            has_error_in_output = any(pattern in output for pattern in error_patterns)
            
            if has_error_in_output:
                print("❌ 代码执行过程中发生错误")
                print("错误输出:")
                print(output)
                
                return {
                    "final_table": output,

                    "execution_successful": False,
                    "error_message": f"Generated code internal error: {output}"
                }
            else:
                print("✅ 代码执行成功")
                
                return {
                    "final_table": output,
                    "execution_successful": True,
                    "error_message": ""
                }
            
        except SyntaxError as e:
            # Handle syntax errors with detailed information
            import traceback
            full_traceback = traceback.format_exc()
            error_msg = f"语法错误: {str(e)} (第{e.lineno}行, 第{e.offset}列)"
            
            # Print detailed syntax error information
            print(f"❌ {error_msg}")
            if e.lineno and e.lineno <= len(lines):
                print(f"问题代码: {lines[e.lineno-1]}")
            print("完整错误信息:")
            print(full_traceback)
            
            return {
                "final_table": f"执行失败: {error_msg}",
                "execution_error": error_msg,
                "execution_successful": False,
                "error_message": full_traceback
            }
            
        except Exception as e:
            # Handle runtime errors with full traceback
            import traceback
            full_traceback = traceback.format_exc()
            error_msg = f"代码执行错误: {str(e)}"
            
            # Print the complete error message
            print(f"❌ {error_msg}")
            print("完整错误信息:")
            print(full_traceback)
            
            return {
                "final_table": f"执行失败: {error_msg}",
                "execution_error": error_msg,
                "execution_successful": False,
                "error_message": full_traceback
            }


    def _route_after_execute_code(self, state: FilloutTableState) -> str:
        """This node will route back to the generate_code node, and ask the model to fix the error if error occurs"""
        if state["execution_successful"]:
            return "END"
        else:
            print("🔄 代码执行失败，返回重新生成代码...")
            return "generate_code"
    


    def run_fillout_table_agent(self, user_input: str, session_id: str = "1") -> None:
        """This function will run the fillout table agent"""
        initial_state = self.create_initialize_state(template_file = r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\老党员补贴.txt", 
                                                        rules = """党员补助列需要你智能计算，规则如下，党龄需要根据党员名册中的转正时间计算，（1）党龄40—49年的，补助标准为：100元/月；
（2）党龄50—54年的，补助标准为：120元/月；
（3）党龄55年及以上的，补助标准为：150元/月。
以上补助从党员党龄达到相关年限的次月起按月发放。补助标准根据市里政策作相应调整。
2.党组织关系在区、年满80周岁、党龄满55年的老党员：
（1）年龄80—89周岁且党龄满55年的，补助标准为500元/年；
（2）年龄90—99周岁且党龄满55年的，补助标准为1000元/年；
（3）年龄100周岁及以上的，补助标准为3000元/年。
以上补助年龄、党龄计算时间截至所在年份的12月31日。""", data_file_path = [r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\燕云村2024年度党员名册.txt"], 
                                                        supplement_files_path = [r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_files\[正文稿]关于印发《重庆市巴南区党内关怀办法（修订）》的通__知.txt"])
        config = {"configurable": {"thread_id":session_id}}
        current_state = initial_state

        try:
            for chunk in self.graph.stream(current_state, config = config, stream_mode = "updates"):
                for node_name, node_output in chunk.items():
                    print(f"\n📍 Node: {node_name}")
                    print("-" * 30)

                    if isinstance(node_output, dict):
                        if "messages" in node_output and node_output["messages"]:
                            latest_message = node_output["messages"][-1]
                            if hasattr(latest_message, 'content') and not isinstance(latest_message, HumanMessage):
                                print(f"💬 智能体回复: {latest_message.content}")

                        for key, value in node_output.items():
                            if key != "messages" and value:
                                # Show only first 500 characters for long outputs
                                if len(str(value)) > 500:
                                    print(f"📊 {key}: {str(value)[:500]}...")
                                else:
                                    print(f"📊 {key}: {value}")
                    print("-" * 30)

        except Exception as e:
            print(f"❌ 处理用户输入时出错: {e}")
    
agent = FilloutTableAgent()
agent_graph = agent._build_graph()

if __name__ == "__main__":
    fillout_table_agent = FilloutTableAgent()
    fillout_table_agent.run_fillout_table_agent(user_input = "请根据模板和数据文件，填写表格。", session_id = "1")




