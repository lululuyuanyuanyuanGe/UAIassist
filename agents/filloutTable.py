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
from utilities.file_process import (detect_and_process_file_paths, retrieve_file_content, read_txt_file, 
                                    process_excel_files_with_chunking, find_largest_file)
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
from langgraph.constants import Send
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
    session_id: str
    data_file_path: list[str]
    supplement_files_summary: str
    template_file: str
    template_file_completion_code: str
    fill_CSV_2_template_code: str
    combined_data: str
    final_table: str
    error_message: str
    error_message_summary: str
    template_completion_code_execution_successful: bool
    CSV2Teplate_template_completion_code_execution_successful: bool
    retry: int
    combined_data_array: list[str]
    headers_mapping: str
    CSV_data: list[str]
    largest_file_row_num: int



class FilloutTableAgent:
    def __init__(self):
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("combine_data_split_into_chunks", self._combine_data_split_into_chunks)
        graph.add_node("generate_CSV_based_on_combined_data", self._generate_CSV_based_on_combined_data)
        graph.add_node("generate_html_table_completion_code", self._generate_html_table_completion_code)
        graph.add_node("execute_template_completion_code_from_LLM", self._execute_template_completion_code_from_LLM)
        graph.add_node("summary_error_message_template_completion_code", self._summary_error_message_template_completion_code)
        graph.add_node("generate_code_fill_CSV_2_template", self._generate_code_fill_CSV_2_template)
        graph.add_node("execute_fill_CSV_2_template_code", self._execute_fill_CSV_2_template_code)
        graph.add_node("summary_error_message_CSV2Template", self._summary_error_message_CSV2Template)
        
        # Define the workflow
        graph.add_edge(START, "combine_data_split_into_chunks")
        graph.add_conditional_edges("combine_data_split_into_chunks", self._route_after_combine_data_split_into_chunks)

        graph.add_edge("generate_html_table_completion_code", "execute_template_completion_code_from_LLM")
        graph.add_conditional_edges("execute_template_completion_code_from_LLM", self._route_after_execute_template_completion_code_from_LLM)
        graph.add_edge("summary_error_message_template_completion_code", "generate_html_table_completion_code")

        graph.add_edge("generate_CSV_based_on_combined_data", "generate_code_fill_CSV_2_template")
        graph.add_edge("generate_code_fill_CSV_2_template", "execute_fill_CSV_2_template_code")
        graph.add_conditional_edges("execute_fill_CSV_2_template_code", self._route_after_execute_fill_CSV_2_template_code)
        graph.add_edge("summary_error_message_CSV2Template", "generate_code_fill_CSV_2_template")
        graph.add_edge("summary_error_message_template_completion_code", "generate_html_table_completion_code")
        
        graph.add_edge("execute_fill_CSV_2_template_code", END)
        
        # Compile the graph
        return graph.compile()

    
    def create_initialize_state(self, session_id: str,
                                 template_file: str = None,
                                 data_file_path: list[str] = None,
                                 headers_mapping: dict[str, str] = None,
                                 supplement_files_summary: str = "") -> FilloutTableState:
        """This node will initialize the state of the graph"""
        return {
            "messages": [],
            "session_id": session_id,
            "data_file_path": data_file_path, # excel files(xls) that has raw data
            "template_file": template_file, # txt file of template file in html format
            "template_file_completion_code": "",
            "fill_CSV_2_template_code": "",
            "combined_data": "",
            "final_table": "",
            "error_message": "",
            "error_message_summary": "",
            "template_completion_code_execution_successful": False,
            "CSV2Teplate_template_completion_code_execution_successful": False,
            "retry": 0,
            "combined_data_array": [],
            "headers_mapping": headers_mapping,
            "CSV_data": [],
            "largest_file_row_num": 66,
            "supplement_files_summary": supplement_files_summary
        }
    
    def _combine_data_split_into_chunks(self, state: FilloutTableState) -> FilloutTableState:
        """整合所有需要用到的数据，并生将其分批，用于分批生成表格"""
        return
        print("\n🔄 开始执行: _combine_data_split_into_chunks")
        print("=" * 50)
        
        try:
            # Get Excel file paths from state
            excel_file_paths = []
            print(f"📋 开始处理 {len(state['data_file_path'])} 个数据文件")
            
            # Convert data files to Excel paths if they're not already
            for file_path in state["data_file_path"]:
                print(f"📄 检查文件: {file_path}")
                if file_path.endswith('.txt'):
                    # Try to find corresponding Excel file
                    excel_path = file_path.replace('.txt', '.xlsx')
                    if Path(excel_path).exists():
                        excel_file_paths.append(excel_path)
                        print(f"✅ 找到对应的Excel文件: {excel_path}")
                    else:
                        # Try .xls extension
                        excel_path = file_path.replace('.txt', '.xls')
                        if Path(excel_path).exists():
                            excel_file_paths.append(excel_path)
                            print(f"✅ 找到对应的Excel文件: {excel_path}")
                        else:
                            print(f"⚠️ 未找到对应的Excel文件: {file_path}")
                elif file_path.endswith(('.xlsx', '.xls', '.xlsm')):
                    excel_file_paths.append(file_path)
                    print(f"✅ 直接使用Excel文件: {file_path}")
            
            if not excel_file_paths:
                print("❌ 没有找到可用的Excel文件")
                print("✅ _combine_data_split_into_chunks 执行完成(错误)")
                print("=" * 50)
                return {"combined_data_array": []}
            
            print(f"📊 准备处理 {len(excel_file_paths)} 个Excel文件进行分块")
            
            # Use the helper function to process and chunk files
            # Convert word_file_list to string for supplement content
            supplement_content = ""
            if state["supplement_files_summary"]:
                supplement_content = "=== 补充文件内容 ===\n" + state["supplement_files_summary"]
                print(f"📚 补充内容长度: {len(supplement_content)} 字符")
            
            print("🔄 正在调用process_excel_files_with_chunking函数...")
            print("state['headers_mapping']的类型: ", type(state["headers_mapping"]))
            chunked_result = process_excel_files_with_chunking(excel_file_paths=excel_file_paths, 
                                                             session_id=state["session_id"],
                                                             chunk_nums=35, largest_file=None,  # Let function auto-detect
                                                             data_json_path="agents/data.json")
            
            # Extract chunks and row count from the result
            chunked_data = chunked_result["combined_chunks"]
            largest_file_row_count = chunked_result["largest_file_row_count"]
            
            print(f"✅ 成功生成 {len(chunked_data)} 个数据块")
            print(f"📊 最大文件行数: {largest_file_row_count}")
            for chunk in chunked_data:
                print(f"==================🔍 数据块 ==================:")
                print(chunk)
            print("✅ _combine_data_split_into_chunks 执行完成")
            print("=" * 50)
            
            return {
                "combined_data_array": chunked_data,
                "largest_file_row_num": largest_file_row_count
            }
            
        except Exception as e:
            print(f"❌ _combine_data_split_into_chunks 执行失败: {e}")
            import traceback
            print(f"错误详情: {traceback.format_exc()}")
            print("✅ _combine_data_split_into_chunks 执行完成(错误)")
            print("=" * 50)
            return {
                "combined_data_array": []
            }

    def _route_after_combine_data_split_into_chunks(self, state: FilloutTableState) -> str:
        """并行执行模板代码的生成和CSV数据的合成"""
        print("\n🔀 开始执行: _route_after_combine_data_split_into_chunks")
        print("=" * 50)
        
        print("🔄 创建并行任务...")
        sends = []
        sends.append(Send("generate_CSV_based_on_combined_data", state))
        sends.append(Send("generate_html_table_completion_code", state))
        print("✅ 创建了2个并行任务:")
        print("   - generate_CSV_based_on_combined_data")
        print("   - generate_html_table_completion_code")
        
        print("✅ _route_after_combine_data_split_into_chunks 执行完成")
        print("=" * 50)
        
        return sends
    
    def _generate_CSV_based_on_combined_data(self, state: FilloutTableState) -> FilloutTableState:
        """根据整合的数据，映射关系，模板生成新的数据"""
        return
        print("\n🔄 开始执行: _generate_CSV_based_on_combined_data")
        print("=" * 50)
        
#         system_prompt = f"""
# 你是一名专业且严谨的结构化数据填报专家，具备逻辑推理和计算能力。你的任务是根据原始数据和模板映射规则，将数据准确转换为目标 CSV 格式，输出结构化、干净的数据行。

# 【输入内容】
# 1. 模板表头映射（JSON 格式）：描述目标表格每一列的来源、计算逻辑或推理规则；
# 2. 原始数据集：包括表头结构的 JSON 和 CSV 数据块，其中每条数据行前一行标注了字段名称，用于辅助字段匹配。

# 【任务流程】
# 1. 请你逐字段分析模板表头映射，明确该字段的来源或推理逻辑；
# 2. 若字段来自原始数据，请先定位来源字段并校验其格式；
# 3. 若字段需推理（如日期格式转换、年龄计算、逻辑判断等），请先在脑中逐步推导，确保思路清晰；
# 4. 若字段需计算，请先明确所需公式并逐步计算出结果；
# 5. 在完成所有字段推理后，再将结果按照字段顺序合并为一行 CSV 数据；
# 6. 在每次输出前，请先**在脑中逐项验证字段是否合理、格式是否规范**。

# 💡 请你像一位人类专家一样，**一步一步思考再做决定**，不要跳过任何逻辑过程。

# 【输出要求】
# - 仅输出纯净的 CSV 数据行，不包含表头、注释或任何多余内容；
# - 使用英文逗号分隔字段；
# - 每行数据字段顺序必须与模板表头映射完全一致；
# - 严禁遗漏字段、重复字段、多输出空值或空行；
# - 输出中不得出现 Markdown 包裹（如 ```）或额外说明文字。

# 模板表头映射：
# {state["headers_mapping"]}
# """ 
        system_prompt = f"""
你是一名专业且严谨的结构化数据填报专家，具备逻辑推理和计算能力。

让我们一步一步来解决这个数据转换问题。

【任务目标】
根据原始数据和模板映射规则，将数据准确转换为目标 CSV 格式。

【输入内容】
1. 模板表头映射（JSON 格式）：描述目标表格每一列的来源、计算逻辑或推理规则；
2. 原始数据集：包括表头结构的 JSON 和 CSV 数据块。

【推理步骤】
请严格按照以下步骤进行推理，并展示每一步的思考过程：

步骤1：理解映射规则
- 逐一分析每个目标字段的定义
- 明确数据来源和转换规则

步骤2：定位原始数据
- 在原始数据中找到对应字段
- 验证数据格式和完整性

步骤3：执行转换逻辑
- 对于计算字段：明确公式并逐步计算
- 对于推理字段：展示逻辑判断过程
- 对于格式转换：说明转换规则

步骤4：质量检查
- 验证每个字段的合理性
- 检查格式规范性
- 确认字段顺序正确

【输出格式】
请按照以下格式输出：

=== 推理过程 ===
[展示你的完整思考过程，包括每个字段的分析、定位、转换和验证]

=== 最终答案 ===
[仅输出纯净的 CSV 数据行，使用英文逗号分隔]

【质量要求】
- 推理过程必须详细展示每个步骤的思考
- 最终答案仅包含CSV数据，不含任何其他内容
- 字段顺序必须与模板表头映射完全一致
- 严禁遗漏字段、重复字段或输出空值

模板表头映射：
{state["headers_mapping"]}
"""










        
        print("📋 系统提示准备完成")
        print("系统提示词：", system_prompt)
        
        def process_single_chunk(chunk_data):
            """处理单个chunk的函数"""
            chunk, index = chunk_data
            try:
                user_input = f"""
                数据级：
                {chunk}
                """             
                print("用户输入提示词", system_prompt)
                print(f"🤖 Processing chunk {index + 1}/{len(state['combined_data_array'])}...")
                response = invoke_model(
                    model_name="deepseek-ai/DeepSeek-V3", 
                    messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)],
                    temperature=0.2
                )
                print(f"✅ Completed chunk {index + 1}")
                return (index, response)
            except Exception as e:
                print(f"❌ Error processing chunk {index + 1}: {e}")
                return (index, f"Error processing chunk {index + 1}: {e}")
        
        # Prepare chunk data with indices
        chunks_with_indices = [(chunk, i) for i, chunk in enumerate(state["combined_data_array"])]
        
        if not chunks_with_indices:
            print("⚠️ 没有数据块需要处理")
            print("✅ _generate_CSV_based_on_combined_data 执行完成(无数据)")
            print("=" * 50)
            return {"CSV_data": []}
        
        print(f"🚀 开始并发处理 {len(chunks_with_indices)} 个数据块...")
        
        # Use ThreadPoolExecutor for concurrent processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = {}
        with ThreadPoolExecutor(max_workers=35) as executor:  # Limit to 5 concurrent requests
            # Submit all tasks
            future_to_index = {executor.submit(process_single_chunk, chunk_data): chunk_data[1] 
                              for chunk_data in chunks_with_indices}
            print(f"✅ 已提交 {len(future_to_index)} 个并发任务")
            
            # Collect results as they complete
            completed_count = 0
            for future in as_completed(future_to_index):
                try:
                    index, response = future.result()
                    results[index] = response
                    completed_count += 1
                    print(f"✅ 完成第 {completed_count}/{len(chunks_with_indices)} 个任务")
                except Exception as e:
                    index = future_to_index[future]
                    print(f"❌ 第 {index + 1} 个数据块处理异常: {e}")
                    results[index] = f"数据块 {index + 1} 处理异常: {e}"
        
        # Sort results by index to maintain order
        sorted_results = [results[i] for i in sorted(results.keys())]
        
        print(f"🎉 成功并发处理 {len(sorted_results)} 个数据块")
        
        # Save CSV data to output folder using helper function
        try:
            from utilities.file_process import save_csv_to_output
            saved_file_path = save_csv_to_output(sorted_results, state["session_id"])
            print(f"✅ CSV数据已保存到输出文件夹: {saved_file_path}")
        except Exception as e:
            print(f"❌ 保存CSV文件时发生错误: {e}")
            print("⚠️ 数据仍保存在内存中，可继续处理")
        
        print("✅ _generate_CSV_based_on_combined_data 执行完成")
        print("=" * 50)
        print(f"🔍 生成的CSV数据: {sorted_results}")
        return {
            "CSV_data": sorted_results
        }
    
    

    def _generate_code_fill_CSV_2_template(self, state: FilloutTableState) -> FilloutTableState:
        """这个节点会把生成出的CSV数据填到模板表格中"""
        print("\n🔄 开始执行: _generate_code_fill_CSV_2_template")
        print("=" * 50)
        #获得模板文件HTML代码
        file_path = state["template_file"]
        template_file_content = read_txt_file(file_path)

        system_prompt = f"""
你是一名精通 HTML 表格结构处理和 Python 脚本编写的工程师，擅长将结构化数据填充到复杂的 HTML 表格模板中。

【任务目标】
请编写一段完整的 Python 脚本，实现在 HTML 表格模板中自动填充 CSV 数据行，生成结果 HTML 文件。

【任务背景】
我将为你提供：
1. 一个 HTML 表格模板（作为结构示例）；
2. 一个 CSV 数据片段（作为字段示例）；
3. 实际的数据文件路径（CSV）与 HTML 模板路径；
4. CSV 数据总行数（实际数据量）。

【任务要求】
1. 请先解析 HTML 模板结构，定位出**需要插入数据的代表性数据行**（通常是带有空单元格或序号占位的 `<tr>`）；
2. 利用该数据行作为**插入模板**，将实际 CSV 数据源中的所有行逐行插入；
3. 若模板中某个单元格已存在有效数据，请跳过对应 CSV 字段填充，保持原样；
4. 请确保**每一行 CSV 数据都被完整填入表格中**，不得遗漏；
5. 插入后的 HTML 表格结构必须完整且可被浏览器正常渲染。

【输出要求】
- 请输出一段**完整、可直接执行的 Python 脚本**；
- 使用 `pandas` 读取 CSV，`BeautifulSoup` 操作 HTML；
- 请确保脚本中路径参数清晰、注释简明、逻辑稳健；
- 不要输出除代码之外的任何说明、解释或 Markdown 包裹。
- 严禁将输出包裹在```python里，直接给出代码，不要附加多余解释或示例。

💡 请先**思考 HTML 结构与数据对齐逻辑**，再生成代码。

HTML模板内容：
{template_file_content}
"""







        # 上一轮代码的错误信息:
        previous_code_error_message = state["error_message_summary"]

        
        #获得CSV数据示例(前3行)
        csv_path = f"D:\\asianInfo\\ExcelAssist\\conversations\\{state['session_id']}\\CSV_files\\synthesized_table_with_only_data.csv"
        CSV_data = pd.read_csv(csv_path, nrows=3)
        CSV_data = CSV_data.to_string(index=False)

        user_input = f"""
                        上一轮生成的代码:\n{state["fill_CSV_2_template_code"]}\n
                        上一轮代码的错误信息:\n{previous_code_error_message}\n
                         需要填的模板表格(路径：D:\\asianInfo\\ExcelAssist\\conversations\\{state["session_id"]}\\output\\expanded_template.html):
                         需要填入的CSV数据例子(路径：D:\\asianInfo\\ExcelAssist\\conversations\\{state["session_id"]}\\CSV_files\\synthesized_table_with_only_data.csv):\n{CSV_data}"""
        print(f"📝 用户输入总长度: {len(user_input)} 字符")
        print(f"📝 用户输入: {user_input}")
        print("🤖 正在调用LLM生成CSV填充代码...")
        response = invoke_model(model_name="gpt-4o",
                                messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)],
                                temperature=0.2
                                )
        
        print("✅ CSV填充代码生成完成")
        print("✅ _generate_code_fill_CSV_2_template 执行完成")
        print("=" * 50)
        
        return {
            "fill_CSV_2_template_code": response
        }
        
    def _execute_fill_CSV_2_template_code(self, state: FilloutTableState) -> FilloutTableState:
        """执行填CSV到模板表格的代码"""
        print("\n🔄 开始执行: _execute_fill_CSV_2_template_code")
        print("=" * 50)
        
        code = state["fill_CSV_2_template_code"]
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        print("🚀 正在执行CSV填充代码...")
        
        # Print the code for debugging (first 10 lines)
        print("📝 生成的CSV填充代码片段:")
        lines = code.split('\n')
        for i, line in enumerate(lines[:10], 1):
            print(f"{i:2d}: {line}")
        if len(lines) > 10:
            print(f"... (共 {len(lines)} 行代码)")
        print("-" * 50)
        
        # Prepare execution environment with all necessary imports
        global_vars = {
            "pd": pd, 
            "BeautifulSoup": BeautifulSoup,
            "Path": Path,
            "json": json,
            "re": re,
            "datetime": datetime,
            "copy": __import__('copy'),
            "os": __import__('os'),
            "sys": __import__('sys'),
            "csv": __import__('csv'),
        }
        
        try:
            # Execute the code
            with contextlib.redirect_stdout(output_buffer):
                with contextlib.redirect_stderr(error_buffer):
                    exec(code, global_vars)
            
            output = output_buffer.getvalue()
            errors = error_buffer.getvalue()
            
            # Check for execution errors
            if errors:
                print(f"❌ CSV填充代码执行失败:")
                print(errors)
                return {
                    "CSV2Teplate_template_completion_code_execution_successful": False,
                    "error_message": f"CSV填充代码执行错误: {errors}",
                    "final_table": ""
                }
            
            # Check if output contains error indicators
            error_indicators = [
                "error", "Error", "ERROR", "exception", "Exception", 
                "traceback", "Traceback", "failed", "Failed"
            ]
            
            if any(indicator in output.lower() for indicator in error_indicators):
                print(f"❌ CSV填充代码执行包含错误信息:")
                print(output)
                return {
                    "CSV2Teplate_template_completion_code_execution_successful": False,
                    "error_message": f"CSV填充代码执行输出包含错误: {output}",
                    "final_table": ""
                }
            
            # Try to find generated HTML file
            output_paths = [
                f"D:\\asianInfo\\ExcelAssist\\conversations\\{state['session_id']}\\output\\老党员补贴_结果.html",
                f"conversations\\{state['session_id']}\\output\\老党员补贴_结果.html",
                "老党员补贴_结果.html"
            ]
            
            html_content = ""
            for path in output_paths:
                if Path(path).exists():
                    try:
                        html_content = read_txt_file(path)
                        print(f"✅ 找到填充后的HTML文件: {path}")
                        break
                    except Exception as e:
                        print(f"⚠️ 读取文件失败 {path}: {e}")
            
            # If no file found, use output content
            if not html_content and output:
                html_content = output
                print("✅ 使用代码输出作为HTML内容")
            elif not html_content:
                print("⚠️ 未找到填充后的HTML内容，但代码执行成功")
                html_content = "<html><body><p>CSV填充代码执行成功，但未生成HTML内容</p></body></html>"
            
            print("✅ CSV填充代码执行成功")
            print("✅ _execute_fill_CSV_2_template_code 执行完成")
            print("=" * 50)
            return {
                "CSV2Teplate_template_completion_code_execution_successful": True,
                "error_message": "",
                "final_table": html_content
            }
            
        except SyntaxError as e:
            error_msg = f"CSV填充代码语法错误 (第{e.lineno}行): {str(e)}"
            print(f"❌ {error_msg}")
            if e.lineno and e.lineno <= len(lines):
                print(f"问题代码: {lines[e.lineno-1]}")
            
            print("✅ _execute_fill_CSV_2_template_code 执行完成(语法错误)")
            print("=" * 50)
            return {
                "CSV2Teplate_template_completion_code_execution_successful": False,
                "error_message": error_msg,
                "final_table": ""
            }
            
        except Exception as e:
            import traceback
            full_traceback = traceback.format_exc()
            error_msg = f"CSV填充代码运行时错误: {str(e)}"
            
            print(f"❌ {error_msg}")
            print("完整错误信息:")
            print(full_traceback)
            print("✅ _execute_fill_CSV_2_template_code 执行完成(运行时错误)")
            print("=" * 50)
            
            return {
                "CSV2Teplate_template_completion_code_execution_successful": False,
                "error_message": full_traceback,
                "final_table": ""
            }

    def _route_after_execute_fill_CSV_2_template_code(self, state: FilloutTableState) -> str:
        """根据执行结果路由到错误总结，或者执行成功"""
        print("\n🔀 开始执行: _route_after_execute_fill_CSV_2_template_code")
        print("=" * 50)
        
        if state["CSV2Teplate_template_completion_code_execution_successful"]:
            print("✅ CSV填充代码执行成功，继续后续流程")
            print("🔄 路由到: validate_html_table")
            print("✅ _route_after_execute_fill_CSV_2_template_code 执行完成")
            print("=" * 50)
            return "validate_html_table"
        else:
            print("🔄 CSV填充代码执行失败，返回重新生成代码...")
            print("🔄 路由到: summary_error_message_CSV2Template")
            print("✅ _route_after_execute_fill_CSV_2_template_code 执行完成")
            print("=" * 50)
            return "summary_error_message_CSV2Template"

    def _summary_error_message_CSV2Template(self, state: FilloutTableState) -> FilloutTableState:
        """总结CSV填充代码的报错信息"""
        print("\n🔄 开始执行: _summary_error_message_CSV2Template")
        print("=" * 50)
        
        system_prompt = f"""
你是一名专业的代码错误分析专家。你的任务是：

1. 阅读提供的 CSV 填充脚本的报错信息和上一次生成的代码。
2. 简要提炼并定位错误根因，指出问题所在。
3. 将错误原因反馈给代码生成智能体，帮助其基于这些信息重新生成修正版代码。

【注意】
- 总结须简明扼要，避免冗长。
- 只聚焦于错误原因，不提供修复后的代码。
"""


        previous_code = "上一次的CSV填充代码:\n" + state["fill_CSV_2_template_code"]
        error_message = "报错信息:\n" + state["error_message"]
        csv_data_preview = f"CSV数据预览:\n{str(state['CSV_data'])[:500]}..." if state.get("CSV_data") else ""
        
        input_2_LLM = previous_code + "\n\n" + error_message + "\n\n" + csv_data_preview

        print("📝 准备错误总结内容...")
        print(f"📊 代码长度: {len(previous_code)} 字符")
        print(f"❌ 错误信息长度: {len(error_message)} 字符")
        if csv_data_preview:
            print(f"📋 CSV数据预览长度: {len(csv_data_preview)} 字符")
        
        print("🤖 正在调用LLM总结CSV填充错误信息...")
        response = invoke_model(model_name="gpt-4o", messages=[SystemMessage(content=system_prompt), HumanMessage(content=input_2_LLM)])
        
        print("✅ CSV填充错误信息总结完成")
        print("✅ _summary_error_message_CSV2Template 执行完成")
        print("=" * 50)
        
        return {
            "error_message_summary": response
        }
    

    def _clean_html_content(self, html_content: str) -> str:
        """清理HTML内容中的过多空白字符和非断行空格"""
        try:
            import re
            
            # 替换4个以上连续的&nbsp;为最多3个
            html_content = re.sub(r'(&nbsp;){4,}', r'&nbsp;&nbsp;&nbsp;', html_content)
            
            # 替换过多的空白字符
            html_content = re.sub(r'\s{4,}', ' ', html_content)
            
            # 移除多余的换行符
            html_content = re.sub(r'\n\s*\n', '\n', html_content)
            
            print(f"✅ HTML内容已清理，长度: {len(html_content)} 字符")
            
            return html_content
            
        except Exception as e:
            print(f"⚠️ HTML清理失败: {e}")
            return html_content


    def _generate_html_table_completion_code(self, state: FilloutTableState) -> FilloutTableState:
        """生成完整的模板表格，生成python代码，但无需执行"""
        print("\n🔄 开始执行: _generate_html_table_completion_code")
        print("=" * 50)
        file_path = state["template_file"]
        template_file_content = read_txt_file(file_path)
        system_prompt = f"""
你是一名精通 HTML 表格处理和 Python 脚本编写的工程师。

【任务目标】
根据提供的HTML模板表格，智能识别数据行结构并扩展到指定行数，生成完整可执行的Python代码。并将转换结果保存在
D:\\asianInfo\\ExcelAssist\\conversations\\{state['session_id']}\\output\\expanded_template.html

【输入参数】
- HTML模板表格路径：{file_path}
- HTML模板表格内容：{template_file_content}
- 目标行数：{state['largest_file_row_num']}

【处理要求】
1. 自动识别表格结构：区分表头、数据行、表尾和其他内容
2. 分析数据行模式：提取现有数据行的完整结构（标签、属性、样式、内容）
3. 智能扩展：根据现有数据行结构生成新的空白行至目标数量
4. 保持完整性：确保扩展后保持原有格式、样式和非数据行内容不变

【数据行识别规则】
- 数据行通常位于表头之后、表尾之前
- 包含多个td标签的tr元素
- 可能包含空白内容或<br/>标签
- 需要保持原有的单元格数量和结构

【技术规范】
- 使用BeautifulSoup解析和修改HTML结构
- 实现智能数据行识别算法
- 确保新生成的行与原数据行结构完全一致
- 添加异常处理和边界条件检查
- 保持HTML文档的完整性和有效性

【扩展策略】
- 定位现有数据行的精确位置
- 复制数据行的完整结构信息
- 计算需要增加的行数（目标行数-现有行数）
- 在合适位置插入新生成的数据行
- 验证扩展后的表格结构正确性

【输出要求】
输出完整可执行的Python代码，满足以下条件：
- 代码可直接运行，无需修改
- 不包含代码块标记（```pyhon等
- 不包含任何解释文字或注释
- 包含必要的导入语句和异常处理
- 代码结构清晰，逻辑完整
- 不要把模板表格的内容在你的代码里输出，直接读取模板表格的内容

【示例数据行结构】
参考格式：
<tr>
<td></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
</tr>

请根据实际模板表格内容，生成相应的Python扩展代码。
"""






        print(f"📄 读取模板文件: {file_path}")
        print(f"📊 模板内容长度: {len(template_file_content)} 字符")

        # Fix: Check if execution was NOT successful to use error recovery
        if not state["template_completion_code_execution_successful"]:
            previous_code = state["template_file_completion_code"]
            print("模板填充上一次生成的代码", previous_code)
            error_message = state.get("error_message_summary", state.get("error_message", ""))
            error_input = f"上一次生成的代码:\n{previous_code}\n\n错误信息:\n{error_message}\n\n请根据错误信息修复代码。"
            full_input = f"\n{error_input}"
            print("🤖 正在基于错误信息重新生成Python代码...")
            print(f"📊 包含错误信息的输入长度: {len(full_input)} 字符")
            print("用户输入内容:", full_input)
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", 
                                    messages=[SystemMessage(content=system_prompt), HumanMessage(content=full_input)],
                                    temperature=0.3)
        else:
            print("🤖 正在生成Python代码...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", 
                                    messages=[SystemMessage(content=system_prompt)],
                                    temperature=0.3)

        print("✅ Python代码生成完成")
        
        # Extract Python code if wrapped in markdown
        code_content = response.strip()
        if code_content.startswith('```python'):
            code_content = code_content[9:]
            print("🔧 移除了Python标记")
        elif code_content.startswith('```'):
            code_content = code_content[3:]
            print("🔧 移除了通用代码标记")
        if code_content.endswith('```'):
            code_content = code_content[:-3]
            print("🔧 移除了结束标记")
        code_content = code_content.strip()
        
        print(f"📝 提取的代码长度: {len(code_content)} 字符")
        print("✅ _generate_html_table_completion_code 执行完成")
        print("=" * 50)
        
        return {
            "template_file_completion_code": code_content,
        }
    


    def _execute_template_completion_code_from_LLM(self, state: FilloutTableState) -> FilloutTableState:
        """执行从LLM生成的Python代码"""
        print("\n🔄 开始执行: _execute_template_completion_code_from_LLM")
        print("=" * 50)
        
        code = state["template_file_completion_code"]
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        print("🚀 正在执行生成的代码...")
        
        # Print the code for debugging (first 10 lines)
        print("📝 生成的代码片段:")
        lines = code.split('\n')
        for i, line in enumerate(lines[:10], 1):
            print(f"{i:2d}: {line}")
        if len(lines) > 10:
            print(f"... (共 {len(lines)} 行代码)")
        print("-" * 50)
        
        # Prepare execution environment with all necessary imports
        global_vars = {
            "pd": pd, 
            "BeautifulSoup": BeautifulSoup,
            "Path": Path,
            "json": json,
            "re": re,
            "datetime": datetime,
            "copy": __import__('copy'),
            "os": __import__('os'),
            "sys": __import__('sys'),
        }
        
        try:
            # Execute the code
            with contextlib.redirect_stdout(output_buffer):
                with contextlib.redirect_stderr(error_buffer):
                    exec(code, global_vars)
            
            output = output_buffer.getvalue()
            errors = error_buffer.getvalue()
            
            # Check for execution errors
            if errors:
                print(f"❌ 代码执行失败:")
                print(errors)
                return {
                    "template_completion_code_execution_successful": False,
                    "error_message": f"代码执行错误: {errors}",
                    "final_table": ""
                }
            
            # Check if output contains error indicators
            error_indicators = [
                "error", "Error", "ERROR", "exception", "Exception", 
                "traceback", "Traceback", "failed", "Failed"
            ]
            
            if any(indicator in output.lower() for indicator in error_indicators):
                print(f"❌ 代码执行包含错误信息:")
                print(output)
                return {
                    "template_completion_code_execution_successful": False,
                    "error_message": f"代码执行输出包含错误: {output}",
                    "final_table": ""
                }
            
            # # Try to find generated HTML file
            # output_paths = [
            #     f"D:\\asianInfo\\ExcelAssist\\conversations\\{state['session_id']}\\output\\老党员补贴_结果.html",
            #     f"conversations\\{state['session_id']}\\output\\老党员补贴_结果.html",
            #     "老党员补贴_结果.html"
            # ]
            
            # html_content = ""
            # for path in output_paths:
            #     if Path(path).exists():
            #         try:
            #             html_content = read_txt_file(path)
            #             print(f"✅ 找到生成的HTML文件: {path}")
            #             break
            #         except Exception as e:
            #             print(f"⚠️ 读取文件失败 {path}: {e}")
            
            # # If no file found, use output content
            # if not html_content and output:
            #     html_content = output
            #     print("✅ 使用代码输出作为HTML内容")
            # elif not html_content:
            #     print("⚠️ 未找到生成的HTML内容，但代码执行成功")
            #     html_content = "<html><body><p>代码执行成功，但未生成HTML内容</p></body></html>"
            
            print("✅ 代码执行成功")
            print("✅ _execute_template_completion_code_from_LLM 执行完成")
            print("=" * 50)
            return {
                "template_completion_code_execution_successful": True,
                "error_message": ""
            }
            
        except SyntaxError as e:
            error_msg = f"语法错误 (第{e.lineno}行): {str(e)}"
            print(f"❌ {error_msg}")
            if e.lineno and e.lineno <= len(lines):
                print(f"问题代码: {lines[e.lineno-1]}")
            
            print("✅ _execute_template_completion_code_from_LLM 执行完成(语法错误)")
            print("=" * 50)
            return {
                "template_completion_code_execution_successful": False,
                "error_message": error_msg,
                "final_table": ""
            }
            
        except Exception as e:
            import traceback
            full_traceback = traceback.format_exc()
            error_msg = f"运行时错误: {str(e)}"
            
            print(f"❌ {error_msg}")
            print("完整错误信息:")
            print(full_traceback)
            print("✅ _execute_template_completion_code_from_LLM 执行完成(运行时错误)")
            print("=" * 50)
            
            return {
                "template_completion_code_execution_successful": False,
                "error_message": full_traceback,
                "final_table": ""
            }

    def _route_after_execute_template_completion_code_from_LLM(self, state: FilloutTableState) -> str:
        """This node will route back to the generate_code node, and ask the model to fix the error if error occurs"""
        print("\n🔀 开始执行: _route_after_execute_template_completion_code_from_LLM")
        print("=" * 50)
        
        if state["template_completion_code_execution_successful"]:
            print("✅ 模板代码执行成功，继续下一步")
            print("🔄 路由到: execute_fill_CSV_2_template_code")
            print("✅ _route_after_execute_template_completion_code_from_LLM 执行完成")
            print("=" * 50)
            return "execute_fill_CSV_2_template_code"
        else:
            print("🔄 代码执行失败，返回重新生成代码...")
            print("🔄 路由到: summary_error_message_template_completion_code")
            print("✅ _route_after_execute_template_completion_code_from_LLM 执行完成")
            print("=" * 50)
            return "summary_error_message_template_completion_code"
        

    def _summary_error_message_template_completion_code(self, state: FilloutTableState) -> FilloutTableState:
        """这个节点用于整理总结代码执行中的错误，并返回给智能体重新生成"""
        print("\n🔄 开始执行: _summary_error_message_template_completion_code")
        print("=" * 50)
        
        system_prompt = f"""你的任务是根据报错信息和上一次的代码，总结出错误的原因，并反馈给代码生成智能体，让其根据报错重新生成代码
        你不需要生成改进的代码，你只需要总结出错误的原因，并反馈给代码生成智能体，让其根据报错重新生成代码。
        """

        previous_code = "上一次的代码:\n" + state["template_file_completion_code"]
        error_message = "报错信息:\n" + state["error_message"]
        input_2_LLM = previous_code + "\n\n" + error_message

        print("📝 准备模板代码错误总结内容...")
        print(f"📊 代码长度: {len(previous_code)} 字符")
        print(f"❌ 错误信息长度: {len(error_message)} 字符")
        
        print("🤖 正在调用LLM总结模板代码错误信息...")
        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=input_2_LLM)])
        
        print("✅ 模板代码错误信息总结完成")
        print("✅ _summary_error_message_template_completion_code 执行完成")
        print("=" * 50)
        
        return {
            "error_message_summary": response
        }

    

    def run_fillout_table_agent(self, session_id: str,
                                template_file: str,
                                data_file_path: list[str],
                                headers_mapping: dict[str, str]
                                ) -> None:
        """This function will run the fillout table agent using invoke method with manual debug printing"""
        print("\n🚀 启动 FilloutTableAgent")
        print("=" * 60)
        
        initial_state = self.create_initialize_state(
            session_id = session_id,
            template_file = template_file,
            data_file_path = data_file_path,
            headers_mapping=headers_mapping
        )

        config = {"configurable": {"thread_id": session_id}}
        
        print(f"📋 初始状态创建完成，会话ID: {session_id}")
        print(f"📄 模板文件: {initial_state['template_file']}")
        print(f"📊 数据文件数量: {len(initial_state['data_file_path'])}")

        print("-" * 60)

        while True:
            try:
                print(f"\n🔄 执行状态图，当前会话ID: {session_id}")
                print("-" * 50)
                
                final_state = self.graph.invoke(initial_state, config=config)
                
                if "__interrupt__" in final_state:
                    interrupt_value = final_state["__interrupt__"][0].value
                    print(f"💬 智能体: {interrupt_value}")
                    user_response = input("👤 请输入您的回复: ")
                    initial_state = Command(resume=user_response)
                    continue
                
                print("\n✅ FilloutTableAgent执行完毕")
                print("=" * 60)
                
                # Print final results
                if "final_table" in final_state and final_state["final_table"]:
                    print(f"📊 最终结果已生成")
                    if len(str(final_state["final_table"])) > 500:
                        print(f"📄 内容长度: {len(str(final_state['final_table']))} 字符")
                    else:
                        print(f"📄 内容: {final_state['final_table']}")
                        
                if "messages" in final_state and final_state["messages"]:
                    latest_message = final_state["messages"][-1]
                    if hasattr(latest_message, 'content'):
                        print(f"💬 最终消息: {latest_message.content}")
                        
                break
                
            except Exception as e:
                print(f"❌ 执行过程中发生错误: {e}")
                print(f"错误类型: {type(e).__name__}")
                import traceback
                print(f"错误详情: {traceback.format_exc()}")
                print("-" * 50)
                break
    


if __name__ == "__main__":
    # fillout_table_agent = FilloutTableAgent()
    # fillout_table_agent.run_fillout_table_agent( session_id = "1")
    # file_content = retrieve_file_content(session_id= "1", file_paths = [r"D:\asianInfo\ExcelAssist\燕云村测试样例\燕云村残疾人补贴\待填表\燕云村残疾人补贴申领登记.xlsx"])

    # file_list = [r"D:\asianInfo\数据\新槐村\7.2接龙镇附件4.xlsx", r"D:\asianInfo\数据\新槐村\10.24接龙镇附件4：脱贫人口小额贷款贴息发放明细表.xlsx", r"D:\asianInfo\数据\新槐村\12.3附件4：脱贫人口小额贷款贴息申报汇总表.xlsx"]
    # fillout_table_agent = FilloutTableAgent()
    # combined_data = fillout_table_agent._combine_data_split_into_chunks(file_list)
    # print(combined_data)
    fillout_table_agent = FilloutTableAgent()
    fillout_table_agent.run_fillout_table_agent(session_id = "1",
                                                template_file = r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\template\老党员补贴.txt",
                                                data_file_path = [r"D:\asianInfo\ExcelAssist\files\table_files\original\燕云村24年度党员名册.xlsx"],
                                                headers_mapping={
  "表格结构": {
    "重庆市巴南区享受生活补贴老党员登记表": {
      "填表单位：燕云村党委": [
        {
          "表头": "序号",
          "来源": "燕云村2024年度党员名册.txt: 序号"
        },
        {
          "表头": "姓名",
          "来源": "燕云村2024年度党员名册.txt: 姓名"
        },
        {
          "表头": "性别",
          "来源": "燕云村2024年度党员名册.txt: 性别"
        },
        {
          "表头": "民族",
          "来源": "燕云村2024年度党员名册.txt: 民族"
        },
        {
          "表头": "身份证号码",
          "来源": "燕云村2024年度党员名册.txt: 公民身份证号"
        },
        {
          "表头": "出生时间",
          "来源": "燕云村2024年度党员名册.txt: 出生日期",
          "转换规则": "将'19750610'格式转换为'1975年6月10日'"
        },
        {
          "表头": "所在党支部",
          "来源": "燕云村2024年度党员名册.txt: 所属支部"
        },
        {
          "表头": "成为正式党员时间",
          "来源": "燕云村2024年度党员名册.txt: 转正时间",
          "转换规则": "将'20130619'格式转换为'2013年6月19日'"
        },
        {
          "表头": "党龄（年）",
          "推理规则": "当前年份(2024) - 转正时间的年份(从'转正时间'字段提取)"
        },
        {
          "表头": "生活补贴标准（元／月）",
          "推理规则": "根据[正文稿]关于印发《重庆市巴南区党内关怀办法（修订）》的通__知.txt中的关怀标准计算：1.如果党龄≥55年且年龄≥80岁，按年龄分段：80-89岁500元/年(约42元/月)，90-99岁1000元/年(约83元/月)，100岁以上3000元/年(250元/月)；2.如果不符合年龄条件，仅按党龄：40-49年100元/月，50-54年120元/月，55年及以上150元/月。取两者中较高值"
        },
        {
          "表头": "备注",
          "推理规则": "如需特殊说明的情况，如临时救助等"
        }
      ]
    }
  },
  "表格总结": "该表格用于登记重庆市巴南区享受生活补贴的老党员信息，主要数据来源为'燕云村2024年度党员名册.txt'，部分字段需要根据党员名册中的数据进行计算或转换。生活补贴标准需结合党龄和年龄，按照《重庆市巴南区党内关怀办法（修订）》的规定进行计算。"
})