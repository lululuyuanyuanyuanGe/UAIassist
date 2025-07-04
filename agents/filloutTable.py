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
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content, read_txt_file, process_excel_files_with_chunking
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
    supplement_files_summary: str
    template_file: str
    template_file_completion_code: str
    rules: str
    combined_data: str
    final_table: str
    styled_html_table: str
    error_message: str
    error_message_summary: str
    execution_successful: bool
    retry: int
    combined_data_array: list[str]
    headers_mapping: str



class FilloutTableAgent:
    def __init__(self):
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("combine_data_split_into_chunks", self._combine_data_split_into_chunks)
        graph.add_node("generate_html_table_completion_code", self._generate_html_table_completion_code)
        graph.add_node("execute_template_completion_code_from_LLM", self._execute_template_completion_code_from_LLM)
        graph.add_node("summary_error_message", self._summary_error_message)
        graph.add_node("validate_html_table", self._validate_html_table)
        graph.add_node("style_html_table", self._style_html_table)
        graph.add_node("convert_html_to_excel", self._convert_html_to_excel)
        
        # Define the workflow
        graph.add_edge(START, "combine_data_split_into_chunks")
        graph.add_edge("combine_data_split_into_chunks", "generate_html_table_completion_code")
        graph.add_edge("generate_html_table_completion_code", "execute_template_completion_code_from_LLM")
        
        # Fix: Use add_conditional_edges instead of add_edge for routing
        graph.add_conditional_edges(
            "execute_template_completion_code_from_LLM", 
            self._route_after_execute_code,
            {
                "END": END,
                "summary_error_message": "summary_error_message"
            }
        )
        
        graph.add_edge("summary_error_message", "generate_html_table_completion_code")
        # graph.add_edge("validate_html_table", "style_html_table")
        # graph.add_edge("style_html_table", "convert_html_to_excel")
        # graph.add_edge("convert_html_to_excel", END)

        
        # Compile the graph
        return graph.compile()

    
    def create_initialize_state(self, template_file: str = None, rules: str = None, data_file_path: list[str] = None, supplement_files_path: list[str] = None) -> FilloutTableState:
        """This node will initialize the state of the graph"""
        return {
            "messages": [],
            "data_file_path": data_file_path,
            "supplement_files_path": supplement_files_path,
            "template_file": template_file,
            "supplement_files_summary": "",
            "template_file_completion_code": "",
            "rules": rules,
            "combined_data": "",
            "final_table": "",
            "styled_html_table": "",
            "error_message": "",
            "error_message_summary": "",
            "execution_successful": True,
            "retry": 0,
            "combined_data_array": [],
            "headers_mapping": ""
        }
    
    def _combine_data_split_into_chunks(self, state: FilloutTableState) -> FilloutTableState:
        """整合所有需要用到的数据，并生将其分批，用于分批生成表格"""
        try:
            # Get Excel file paths from state
            excel_file_paths = []
            
            # Convert data files to Excel paths if they're not already
            for file_path in state["data_file_path"]:
                if file_path.endswith('.txt'):
                    # Try to find corresponding Excel file
                    excel_path = file_path.replace('.txt', '.xlsx')
                    if Path(excel_path).exists():
                        excel_file_paths.append(excel_path)
                    else:
                        # Try .xls extension
                        excel_path = file_path.replace('.txt', '.xls')
                        if Path(excel_path).exists():
                            excel_file_paths.append(excel_path)
                elif file_path.endswith(('.xlsx', '.xls', '.xlsm')):
                    excel_file_paths.append(file_path)
            
            if not excel_file_paths:
                print("⚠️ No Excel files found for chunking")
                return []
            
            print(f"📊 Processing {len(excel_file_paths)} Excel files for chunking")
            
            # Use the helper function to process and chunk files
            # Convert word_file_list to string for supplement content
            supplement_content = ""
            if state["supplement_files_summary"]:
                supplement_content = "补充文件内容\n" + state["supplement_files_summary"]
            
            chunked_data = process_excel_files_with_chunking(excel_file_paths, supplement_content)

            return {
                "combined_data_array": chunked_data
            }
            
        except Exception as e:
            print(f"❌ Error in _combine_data_split_into_chunks: {e}")
            return {
                "combined_data_array": []
            }

    
    def _generate_CSV_based_on_combined_data(self, state: FilloutTableState) -> FilloutTableState:
        """根据整合的数据，映射关系，模板生成新的数据"""
        system_prompt = f"""
你是一位精通表格数据解析与填报的专家助手。用户将提供一个包含多个 CSV 格式的 Excel 数据文件的数据集合。

这些文件存在以下特点与辅助信息：
1. 由于 CSV 格式无法完整表达复杂的表头结构，系统将提供一份由字典构成的表头结构说明，以帮助你准确理解每个文件的表格布局；
2. 同时还会提供一份"字段映射关系表"，明确指出模板表格中的每一列数据应如何从原始数据文件中提取，包括：
   - 直接对应某一列；
   - 由多列组合计算得到；
   - 或需依据补充规则进行逻辑推理或条件判断得出。

你的任务是根据提供的数据集、表头结构说明与字段映射规则，自动生成用于填写模板表格的数据内容。

最终输出格式要求：
- 输出为严格遵循 CSV 格式的纯文本；
- 每一行代表模板表格中的一条记录；
- 不包含多余信息或注释，仅保留数据本身。

请确保你完整解析每个字段规则，正确处理计算与推理逻辑，生成结构准确、内容完整的表格数据。
"""
        
        def process_single_chunk(chunk_data):
            """处理单个chunk的函数"""
            chunk, index = chunk_data
            try:
                user_input = f"""
{chunk}

{state["headers_mapping"]}
"""
                print(f"🤖 Processing chunk {index + 1}/{len(state['combined_data_array'])}...")
                response = invoke_model(
                    model_name="deepseek-ai/DeepSeek-V3", 
                    messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)]
                )
                print(f"✅ Completed chunk {index + 1}")
                return (index, response)
            except Exception as e:
                print(f"❌ Error processing chunk {index + 1}: {e}")
                return (index, f"Error processing chunk {index + 1}: {e}")
        
        # Prepare chunk data with indices
        chunks_with_indices = [(chunk, i) for i, chunk in enumerate(state["combined_data_array"])]
        
        if not chunks_with_indices:
            print("⚠️ No chunks to process")
            return {"combined_data_array": []}
        
        print(f"🚀 Starting concurrent processing of {len(chunks_with_indices)} chunks...")
        
        # Use ThreadPoolExecutor for concurrent processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:  # Limit to 3 concurrent requests
            # Submit all tasks
            future_to_index = {executor.submit(process_single_chunk, chunk_data): chunk_data[1] 
                              for chunk_data in chunks_with_indices}
            
            # Collect results as they complete
            for future in as_completed(future_to_index):
                try:
                    index, response = future.result()
                    results[index] = response
                except Exception as e:
                    index = future_to_index[future]
                    print(f"❌ Exception in chunk {index + 1}: {e}")
                    results[index] = f"Exception in chunk {index + 1}: {e}"
        
        # Sort results by index to maintain order
        sorted_results = [results[i] for i in sorted(results.keys())]
        
        print(f"🎉 Successfully processed {len(sorted_results)} chunks concurrently")
        
        return {
            "combined_data_array": sorted_results
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

        system_prompt = f"""你是一位专业的 HTML 表格处理和样式优化专家，擅长通过 Python 代码实现表格的动态扩展和美化。

【核心任务】
根据用户提供的 HTML 表格模板，生成一段完整可执行的 Python 代码，实现以下功能：

1. **表格数据行扩展**：
   - 你需要识别出表格中哪些是"数据行"，这些行通常满足：
     - 包含"序号"列；
     - 且"序号"单元格中是连续的数字（如 1、2、3…）；
   - 使用这些数据行中第一个有效的 `<tr>` 作为模板进行扩展；
   - 自动忽略或删除非数据行，如包含"审核人"、"制表人"字段的表尾行，或空白行。

2. **样式美化**：
   - 使用内嵌 `<style>` 标签添加 CSS 样式；
   - 样式包括：边框、对齐方式、字体、表头背景、隔行换色等；
   - 美化后表格应简洁、清晰、正式。

3. **结构保持**：
   - 保留表格原有的 `<colgroup>` 区块；
   - 保留表头 `<tr>`；
   - 非数据部分结构不应被破坏。

【技术要求】
- 使用 BeautifulSoup 解析 HTML；
- 使用 copy.deepcopy() 或 soup.new_tag() 方法复制模板行；
- 遍历 <tr> 判断数据行；
- 使用标准 Python 文件读写操作；
- 插入数据行时保证序号递增，并清空其余单元格内容；
- 最终 HTML 结构必须符合标准并可直接在浏览器打开。

【输出要求】
- 仅输出完整、可直接执行的 Python 代码（不要添加 markdown 格式或解释性文字）；
- Python 脚本需从 D:\\asianInfo\\ExcelAssist\\agents\\input\\老党员补贴.txt 读取 HTML 模板；
- 结果输出为 D:\\asianInfo\\ExcelAssist\\agents\\output\\老党员补贴_结果.html；
- 编码为 UTF-8，路径必须可写。

【错误修复机制】
如遇到执行错误，请重点检查并修复以下问题：
- 是否错误地复制了非数据行；
- 是否误删或误保留了尾部备注行；
- 是否遗漏 HTML 的结构闭合或 CSS 插入；
- 是否缺失必要依赖（如 copy, BeautifulSoup）；
- 文件路径是否正确、可读写。

【参考示例】
以下是符合要求的 Python 参考模板：

from bs4 import BeautifulSoup
import copy

input_path = ""
output_path = ""
num_rows_to_generate = 100

with open(input_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

table = soup.find('table')
all_rows = table.find_all('tr')

data_row_template = None
for row in all_rows:
    cells = row.find_all('td')
    if len(cells) == 11 and cells[0].text.strip().isdigit():
        data_row_template = copy.deepcopy(row)
        break

footer_row = None
# 具体表格具体分析
for row in reversed(all_rows):
    if '审核人' in row.text or '制表人' in row.text:
        footer_row = row
        break

if footer_row:
    footer_row.extract()

for row in all_rows:
    cells = row.find_all('td')
    if len(cells) == 11 and cells[0].text.strip().isdigit():
        row.extract()

for i in range(1, num_rows_to_generate + 1):
    new_row = copy.deepcopy(data_row_template)
    cells = new_row.find_all('td')
    cells[0].string = str(i)
    for j in range(1, len(cells)):
        cells[j].string = ''
    table.append(new_row)

if footer_row:
    table.append(footer_row)

style_tag = soup.new_tag('style')
style_tag.string = \"\"\"
table {{
    border-collapse: collapse;
    width: 100%;
    font-family: 'Arial', sans-serif;
    font-size: 14px;
}}
td {{
    border: 1px solid #333;
    padding: 6px;
    text-align: center;
}}
td[colspan="11"] {{
    font-weight: bold;
    background-color: #f2f2f2;
}}
tr:nth-child(even) {{
    background-color: #f9f9f9;
}}
\"\"\"
soup.html.insert(0, style_tag)

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
"""


        file_path = r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\燕云村残疾人补贴申领登记.txt"
        template_file_content = read_txt_file(file_path)
        number_of_rows = "需要生成100行数据行"
        base_input = f"HTML模板地址: {file_path}\n HTML模板内容:\n{template_file_content}\n \n需求:\n{number_of_rows}"

        # Fix: Check if execution was NOT successful to use error recovery
        if not state["execution_successful"]:
            previous_code = state["template_file_completion_code"]
            error_message = state.get("error_message_summary", state.get("error_message", ""))
            error_input = f"上一次生成的代码:\n{previous_code}\n\n错误信息:\n{error_message}\n\n请根据错误信息修复代码。"
            full_input = f"{base_input}\n\n{error_input}"
            print("🤖 正在基于错误信息重新生成Python代码...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=full_input)])
        else:
            print("🤖 正在生成Python代码...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=base_input)])

        print("✅ Python代码生成完成")
        
        # Extract Python code if wrapped in markdown
        code_content = response.strip()
        if code_content.startswith('```python'):
            code_content = code_content[9:]
        elif code_content.startswith('```'):
            code_content = code_content[3:]
        if code_content.endswith('```'):
            code_content = code_content[:-3]
        code_content = code_content.strip()
        
        return {
            "template_file_completion_code": code_content,
        }
    


    def _execute_template_completion_code_from_LLM(self, state: FilloutTableState) -> FilloutTableState:
        """执行从LLM生成的Python代码"""
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
                    "execution_successful": False,
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
                    "execution_successful": False,
                    "error_message": f"代码执行输出包含错误: {output}",
                    "final_table": ""
                }
            
            # Try to find generated HTML file
            output_paths = [
                "D:\\asianInfo\\ExcelAssist\\agents\\output\\老党员补贴_结果.html",
                "agents\\output\\老党员补贴_结果.html",
                "老党员补贴_结果.html"
            ]
            
            html_content = ""
            for path in output_paths:
                if Path(path).exists():
                    try:
                        html_content = read_txt_file(path)
                        print(f"✅ 找到生成的HTML文件: {path}")
                        break
                    except Exception as e:
                        print(f"⚠️ 读取文件失败 {path}: {e}")
            
            # If no file found, use output content
            if not html_content and output:
                html_content = output
                print("✅ 使用代码输出作为HTML内容")
            elif not html_content:
                print("⚠️ 未找到生成的HTML内容，但代码执行成功")
                html_content = "<html><body><p>代码执行成功，但未生成HTML内容</p></body></html>"
            
            print("✅ 代码执行成功")
            return {
                "execution_successful": True,
                "error_message": "",
                "final_table": html_content
            }
            
        except SyntaxError as e:
            error_msg = f"语法错误 (第{e.lineno}行): {str(e)}"
            print(f"❌ {error_msg}")
            if e.lineno and e.lineno <= len(lines):
                print(f"问题代码: {lines[e.lineno-1]}")
            
            return {
                "execution_successful": False,
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
            
            return {
                "execution_successful": False,
                "error_message": full_traceback,
                "final_table": ""
            }

    def _route_after_execute_code(self, state: FilloutTableState) -> str:
        """This node will route back to the generate_code node, and ask the model to fix the error if error occurs"""
        if state["execution_successful"]:
            return END
        else:
            print("🔄 代码执行失败，返回重新生成代码...")
            return "summary_error_message"
        

    def _summary_error_message(self, state: FilloutTableState) -> FilloutTableState:
        """这个节点用于整理总结代码执行中的错误，并返回给智能体重新生成"""
        system_prompt = f"""你的任务是根据报错信息和上一次的代码，总结出错误的原因，并反馈给代码生成智能体，让其根据报错重新生成代码
        你不需要生成改进的代码，你只需要总结出错误的原因，并反馈给代码生成智能体，让其根据报错重新生成代码。
        """

        previous_code = "上一次的代码:\n" + state["template_file_completion_code"]
        error_message = "报错信息:\n" + state["error_message"]
        input_2_LLM = previous_code + "\n\n" + error_message

        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=input_2_LLM)])
        return {
            "error_message_summary": response
        }


    def _validate_html_table(self, state: FilloutTableState) -> FilloutTableState:
        """这个节点用于验证模型生成的html表格是否符合要求，并提出修改意见"""
        try:
            # Get the final table content
            final_table = state.get("final_table", "")
            
            if not final_table:
                print("❌ 没有找到最终表格内容")
                return {"error_message": "没有找到最终表格内容"}
            
            # If final_table is a file path, read the content
            if isinstance(final_table, str) and Path(final_table).exists():
                html_table_content = read_txt_file(final_table)
            else:
                html_table_content = final_table
            
            # Clean up the HTML content before validation
            html_table_content = self._clean_html_content(html_table_content)
            
            # Truncate content if too long to prevent token limit issues
            if len(html_table_content) > 8000:
                html_table_content = html_table_content[:8000] + "...[内容已截断]"
                print(f"⚠️ 验证内容过长，已截断至8000字符")
            
            system_prompt = f"""
            你需要根据用户提供的模板表格，数据表格和文档来判断模型生成的html表格是否符合要求，并提出修改意见，
            所有文件都是由html构建的，你需要根据html的结构和内容来判断模型生成的html表格是否符合要求，表头结构是否符合模板表头，
            数据是否正确，是否完整，数据计算是否正确

            下面是当前生成的html表格
            {html_table_content}

            下面是用户提供的模板，数据表格和文档
            {state["combined_data"][:5000]}

            如果需要修改请直接返回修改后的html表格，否则返回[No]
            """
            
            print("🔍 正在验证生成的HTML表格...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
            
            if response.strip() == "[No]":
                print("✅ 表格验证通过，无需修改")
                # Return current state unchanged - this is crucial!
                return {}
            else:
                print("🔄 表格验证发现问题，已修改")
                # Clean the modified HTML table as well
                cleaned_response = self._clean_html_content(response)
                return {"final_table": cleaned_response}
                
        except Exception as e:
            print(f"❌ 验证过程中发生错误: {e}")
            return {"error_message": f"验证失败: {str(e)}"}



    def _style_html_table(self, state: FilloutTableState) -> FilloutTableState:
        """这个节点用于把通过代码构建的html表格进行样式调整，使其符合用户的需求"""
        try:
            # Get the final table content
            final_table = state.get("final_table", "")
            
            if not final_table:
                print("❌ 没有找到HTML表格内容")
                return {"error_message": "没有找到HTML表格内容"}
            
            # If final_table is a file path, read the content
            if isinstance(final_table, str) and Path(final_table).exists():
                html_content = read_txt_file(final_table)
            else:
                html_content = final_table
            
            # Clean up the HTML content before styling
            html_content = self._clean_html_content(html_content)
            
            # Truncate content if too long to prevent token limit issues
            if len(html_content) > 8000:
                html_content = html_content[:8000] + "...[内容已截断]"
                print(f"⚠️ 样式调整内容过长，已截断至8000字符")
            
            system_prompt = f"""你是一位擅长美化 HTML 表格的专业样式设计专家。接下来我将提供一份由 Excel 转换而来的 HTML 表格文件。  
            你的任务是：  
            1. 对表格的整体样式进行美化，使其更加美观、清晰、专业；  
            2. 所有样式需直接以 CSS 的形式嵌入到 HTML 文件中（可使用 `<style>` 标签），避免依赖外部样式文件；  
            3. 保持原始表格结构和内容不变，仅对其外观进行优化调整；  
            4. 输出结果请直接返回完整的 HTML 文件代码（包括样式和表格内容）。

            以下是当前的 HTML 表格文件内容：
            {html_content}
            """
            
            print("🎨 正在美化HTML表格样式...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
            
            print("✅ 表格样式美化完成")
            # Clean the styled HTML as well
            cleaned_response = self._clean_html_content(response)
            return {"styled_html_table": cleaned_response}
            
        except Exception as e:
            print(f"❌ 样式调整过程中发生错误: {e}")
            return {"error_message": f"样式调整失败: {str(e)}"}

    def _convert_html_to_excel(self, state: FilloutTableState) -> FilloutTableState:
        """把通过代码构建的html表格通过libreoffice转换为excel表格"""
        try:
            import subprocess
            import tempfile
            import os
            
            # Get the HTML content from state
            html_content = state.get("styled_html_table", state.get("final_table", ""))
            
            if not html_content:
                print("❌ 没有找到HTML表格内容")
                return {"error_message": "没有找到HTML表格内容"}
            
            # If final_table is a file path, read the content
            if isinstance(html_content, str) and Path(html_content).exists():
                html_content = read_txt_file(html_content)
            
            # Create temporary HTML file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                temp_html.write(html_content)
                temp_html_path = temp_html.name
            
            # Output paths
            output_dir = Path("agents/output")
            output_dir.mkdir(exist_ok=True)
            
            html_output_path = output_dir / "老党员补贴_结果.html"
            excel_output_path = output_dir / "老党员补贴_结果.xlsx"
            
            # Save the final HTML file
            try:
                with open(html_output_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"✅ HTML文件已保存: {html_output_path}")
            except Exception as e:
                print(f"❌ 保存HTML文件失败: {e}")
            
            # Convert to Excel using LibreOffice
            try:
                # Use the specified LibreOffice path
                libreoffice_path = r"D:\LibreOffice\program\soffice.exe"
                
                # Check if LibreOffice exists
                if not os.path.exists(libreoffice_path):
                    print(f"❌ 未找到LibreOffice: {libreoffice_path}")
                    return {"error_message": f"LibreOffice not found at {libreoffice_path}"}
                
                # Convert HTML to Excel using LibreOffice
                cmd = [
                    libreoffice_path,
                    '--headless',
                    '--convert-to', 'xlsx',
                    '--outdir', str(output_dir),
                    temp_html_path
                ]
                
                print(f"🔄 正在转换HTML到Excel...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print(f"✅ Excel文件已生成: {excel_output_path}")
                else:
                    print(f"❌ LibreOffice转换失败: {result.stderr}")
                    return {"error_message": f"LibreOffice conversion failed: {result.stderr}"}
                    
            except subprocess.TimeoutExpired:
                print("❌ LibreOffice转换超时")
                return {"error_message": "LibreOffice conversion timeout"}
            except Exception as e:
                print(f"❌ Excel转换失败: {e}")
                return {"error_message": f"Excel conversion failed: {str(e)}"}
            
            # Clean up temporary file
            try:
                os.unlink(temp_html_path)
            except Exception as e:
                print(f"⚠️ 清理临时文件失败: {e}")
            
            return {
                "final_table": str(html_output_path),
                "messages": [AIMessage(content=f"表格填写完成！\n- HTML文件: {html_output_path}\n- Excel文件: {excel_output_path}")]
            }
            
        except Exception as e:
            print(f"❌ 转换过程中发生错误: {e}")
            return {"error_message": f"转换失败: {str(e)}"}

    def run_fillout_table_agent(self, session_id: str = "1") -> None:
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
    


if __name__ == "__main__":
    # fillout_table_agent = FilloutTableAgent()
    # fillout_table_agent.run_fillout_table_agent( session_id = "1")
    # file_content = retrieve_file_content(session_id= "1", file_paths = [r"D:\asianInfo\ExcelAssist\燕云村测试样例\燕云村残疾人补贴\待填表\燕云村残疾人补贴申领登记.xlsx"])

    file_list = [r"D:\asianInfo\数据\新槐村\7.2接龙镇附件4.xlsx", r"D:\asianInfo\数据\新槐村\10.24接龙镇附件4：脱贫人口小额贷款贴息发放明细表.xlsx", r"D:\asianInfo\数据\新槐村\12.3附件4：脱贫人口小额贷款贴息申报汇总表.xlsx"]
    fillout_table_agent = FilloutTableAgent()
    combined_data = fillout_table_agent._combine_data_split_into_chunks(file_list)
    print(combined_data)