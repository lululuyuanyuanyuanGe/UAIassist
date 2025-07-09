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
    filled_row: str
    error_message: str
    error_message_summary: str
    template_completion_code_execution_successful: bool
    CSV2Teplate_template_completion_code_execution_successful: bool
    retry: int
    combined_data_array: list[str]
    headers_mapping: str
    CSV_data: list[str]
    largest_file_row_num: int
    empty_row_html: str
    headers_html: str
    footer_html: str
    combined_html: str



class FilloutTableAgent:
    def __init__(self):
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("combine_data_split_into_chunks", self._combine_data_split_into_chunks)
        graph.add_node("generate_CSV_based_on_combined_data", self._generate_CSV_based_on_combined_data)
        graph.add_node("transform_data_to_html", self._transform_data_to_html)
        graph.add_node("extract_empty_row_html", self._extract_empty_row_html)
        graph.add_node("extract_headers_html", self._extract_headers_html)
        graph.add_node("extract_footer_html", self._extract_footer_html)
        graph.add_node("combine_html_tables", self._combine_html_tables)
        
        # Define the workflow
        graph.add_edge(START, "combine_data_split_into_chunks")
        graph.add_conditional_edges("combine_data_split_into_chunks", self._route_after_combine_data_split_into_chunks)
        graph.add_edge("extract_empty_row_html", "transform_data_to_html")
        graph.add_edge("extract_headers_html", "transform_data_to_html")
        graph.add_edge("extract_footer_html", "transform_data_to_html")
        graph.add_edge("transform_data_to_html", "combine_html_tables")
        graph.add_edge("combine_html_tables", END)
        

        
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
            "filled_row": "",
            "error_message": "",
            "error_message_summary": "",
            "template_completion_code_execution_successful": False,
            "CSV2Teplate_template_completion_code_execution_successful": False,
            "retry": 0,
            "combined_data_array": [],
            "headers_mapping": headers_mapping,
            "CSV_data": [],
            "largest_file_row_num": 66,
            "supplement_files_summary": supplement_files_summary,
            "empty_row_html": "",
            "headers_html": "",
            "footer_html": "",
            "combined_html": ""
            
        }
    
    def _combine_data_split_into_chunks(self, state: FilloutTableState) -> FilloutTableState:
        """整合所有需要用到的数据，并生将其分批，用于分批生成表格"""
        # return
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
                                                             chunk_nums=15, largest_file=None,  # Let function auto-detect
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
        sends.append(Send("extract_empty_row_html", state))
        sends.append(Send("extract_headers_html", state))
        sends.append(Send("extract_footer_html", state)) 
        print("✅ 创建了4个并行任务:")
        print("   - generate_CSV_based_on_combined_data")
        print("   - extract_empty_row_html")
        print("   - extract_headers_html")
        print("   - extract_footer_html")
    
        
        print("✅ _route_after_combine_data_split_into_chunks 执行完成")
        print("=" * 50)
        
        return sends
    
    def _generate_CSV_based_on_combined_data(self, state: FilloutTableState) -> FilloutTableState:
        """根据整合的数据，映射关系，模板生成新的数据"""
        return state
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
        with ThreadPoolExecutor(max_workers=15) as executor:  # Limit to 5 concurrent requests
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
    
    def _extract_empty_row_html(self, state: FilloutTableState) -> FilloutTableState:
        """提取模板表格中的空行html代码"""
        template_file_content = read_txt_file(state["template_file"])
        system_prompt = """你是一个专业的HTML表格模板分析专家。

【任务目标】
从Excel表格的HTML模板中提取出表示空白数据行的HTML代码。

【提取规则】
1. 识别模板中用于填写数据的空白行（通常包含<br/>或空白内容）,只需要识别出一个
2. 清理掉任何已填入的示例数据，只保留空白行结构
3. 保持原始HTML标签结构和属性不变
4. 忽略表头、标题行、结尾行等非数据行

【输出要求】
- 仅输出纯HTML代码，不要包裹在```html```中
- 不要输出任何解释、注释或其他文本
- 确保输出的HTML代码格式正确且可直接使用
- 如果有多个空白行只需要输出一个

【示例】
输入HTML模板包含：
<tr>
<td>1</td>
<td>张三</td>
<td>男</td>
<td>25</td>
</tr>
<tr>
<td>2</td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
</tr>

应该输出：
<tr>
<td></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
</tr>
有时输入的html模板中没有空白行，你需要根据表头来构建空白行，规则非常简单，只需要把表头中的每个字段都填充为<br/>即可
        """
        response = invoke_model(
            model_name="deepseek-ai/DeepSeek-V3",
            messages=[SystemMessage(content=system_prompt), HumanMessage(content=template_file_content)]
        )
        return {"empty_row_html": response}
        

    def _extract_headers_html(self, state: FilloutTableState) -> FilloutTableState:
        """提取出html模板表格的表头html代码"""
        system_prompt = """你是一个专业的HTML表格模板分析专家。

【任务目标】
从Excel表格的HTML模板中提取出表头部分的HTML代码（从开始到第一个空白数据行之前的所有内容）。

【提取规则】
1. 包含HTML文档的开始标签（<html><body><table>）
2. 包含所有列组定义（<colgroup>）
3. 包含表格标题行（通常使用colspan的标题）
4. 包含表格列头行（定义各列名称）
5. 停止在第一个空白数据行之前
6. 保持原始HTML标签结构和属性不变

【输出要求】
- 仅输出纯HTML代码，不要包裹在```html```中
- 不要输出任何解释、注释或其他文本
- 确保输出的HTML代码格式正确且可直接使用

【示例】
输入HTML模板包含：
<html><body><table>
<colgroup></colgroup>
<colgroup></colgroup>
<colgroup></colgroup>
<tr>
<td colspan="3">员工信息表</td>
</tr>
<tr>
<td>姓名</td>
<td>年龄</td>
<td>部门</td>
</tr>
<tr>
<td><br/></td>
<td><br/></td>
<td><br/></td>
</tr>
<tr>
<td colspan="3">制表人：XXX</td>
</tr>
</table></body></html>

应该输出：
<html><body><table>
<colgroup></colgroup>
<colgroup></colgroup>
<colgroup></colgroup>
<tr>
<td colspan="3">员工信息表</td>
</tr>
<tr>
<td>姓名</td>
<td>年龄</td>
<td>部门</td>
</tr>
        """
        template_file_content = read_txt_file(state["template_file"])
        response = invoke_model(
            model_name="deepseek-ai/DeepSeek-V3",
            messages=[SystemMessage(content=system_prompt), HumanMessage(content=template_file_content)]
        )
        return {"headers_html": response}
    
    def _extract_footer_html(self, state: FilloutTableState) -> FilloutTableState:
        """提取出html模板表格的结尾html代码"""
        system_prompt = """你是一个专业的HTML表格模板分析专家。

【任务目标】
从Excel表格的HTML模板中提取出页脚部分的HTML代码（从最后一个数据行之后到HTML文档结束的所有内容）。

【提取规则】
1. 识别最后一个数据行（空白行）的位置
2. 提取该行之后的所有内容
3. 通常包含签名行、统计行、审核信息等
4. 包含HTML文档的结束标签（</table></body></html>）
5. 保持原始HTML标签结构和属性不变

【输出要求】
- 仅输出纯HTML代码，不要包裹在```html```中
- 不要输出任何解释、注释或其他文本
- 确保输出的HTML代码格式正确且可直接使用

【示例】
输入HTML模板包含：
<html><body><table>
<colgroup></colgroup>
<colgroup></colgroup>
<colgroup></colgroup>
<tr>
<td colspan="3">员工信息表</td>
</tr>
<tr>
<td>姓名</td>
<td>年龄</td>
<td>部门</td>
</tr>
<tr>
<td><br/></td>
<td><br/></td>
<td><br/></td>
</tr>
<tr>
<td colspan="3">制表人：XXX审核人：YYY</td>
</tr>
</table></body></html>

应该输出：
<tr>
<td colspan="3">制表人：XXX审核人：YYY</td>
</tr>
</table></body></html>
        """
        template_file_content = read_txt_file(state["template_file"])
        response = invoke_model(
            model_name="deepseek-ai/DeepSeek-V3",
            messages=[SystemMessage(content=system_prompt), HumanMessage(content=template_file_content)]
        )
        return {"footer_html": response}
    
    
    def _transform_data_to_html(self, state: FilloutTableState) -> FilloutTableState:
        """将数据转换为html代码"""
        print("\n🔄 开始执行: _transform_data_to_html")
        print("=" * 50)
        print("摘取到的表头：", state["headers_html"])
        print("摘取到的表尾：", state["footer_html"])
        print("摘取到的空白行：", state["empty_row_html"])
        return state
        system_prompt = """你是一个html表格数据处理专家，现在我会给你提供代填数据，和html模板，你需要把数据填入html模板中，
        返回结果为严格符合html代码规范的代码，不要输出任何其他内容。不要将结果包裹在```html```中
        举个例子：
        代填数据：
        1,张三,男,汉族,123456,1990-01-01,无
        html模板：
<tr>
<td>1</td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
<td><br/></td>
</tr>
你需要返回的结果
<tr>
<td>1</td>
<td>张三</td>
<td>男</td>
<td>汉族</td>
<td>123456</td>
<td>1990-01-01</td>
<td>无</td>
</tr>
        """
        
        try:
            # Read CSV data
            csv_file_path = f"conversations/{state['session_id']}/CSV_files/synthesized_table_with_only_data.csv"
            print(f"📄 读取CSV文件: {csv_file_path}")
            
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                csv_data = file.read().strip().split('\n')
            
            print(f"📊 CSV数据行数: {len(csv_data)}")
            
            # Split into specified number of chunks for parallel processing
            num_chunks = 15  # Number of parallel tasks to create
            total_rows = len(csv_data)
            
            # Calculate chunk size based on total rows and desired number of chunks
            chunk_size = max(1, total_rows // num_chunks)
            actual_num_chunks = min(num_chunks, total_rows)  # Don't create more chunks than rows
            
            chunks = [csv_data[i:i + chunk_size] for i in range(0, total_rows, chunk_size)]
            print(f"📦 分割为 {len(chunks)} 个数据块，总共 {total_rows} 行")
            print(f"🚀 将创建 {len(chunks)} 个并行LLM调用任务，每块约 {chunk_size} 行")
            
            # Get empty row HTML template from state
            empty_row_html = state.get("empty_row_html", "")
            if not empty_row_html:
                print("⚠️ 未找到空行HTML模板")
                return {"filled_row": ""}
            
            def process_single_chunk(chunk_data):
                """处理单个chunk的函数"""
                chunk, index = chunk_data
                try:
                    # Join chunk data with newlines
                    chunk_csv = '\n'.join(chunk)
                    
                    user_input = f"""
                    代填数据：
                    {chunk_csv}
                    html模板：
                    {empty_row_html}
                    """
                    
                    print(f"🤖 Processing chunk {index + 1}/{len(chunks)}...")
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
            chunks_with_indices = [(chunk, i) for i, chunk in enumerate(chunks)]
            
            if not chunks_with_indices:
                print("⚠️ 没有数据块需要处理")
                return {"filled_row": ""}
            
            print(f"🚀 开始并发处理 {len(chunks_with_indices)} 个数据块...")
            
            # Use ThreadPoolExecutor for concurrent processing
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            results = {}
            with ThreadPoolExecutor(max_workers=15) as executor:
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
            
            # Sort results by index and combine into single HTML string
            sorted_results = [results[i] for i in sorted(results.keys())]
            combined_html = '\n'.join(sorted_results)
            
            print(f"🎉 成功并发处理 {len(sorted_results)} 个数据块")
            print(f"📄 合并后HTML长度: {len(combined_html)} 字符")
            
            print("✅ _transform_data_to_html 执行完成")
            print("=" * 50)
            
            return {"filled_row": combined_html}
            
        except Exception as e:
            print(f"❌ _transform_data_to_html 执行失败: {e}")
            import traceback
            print(f"错误详情: {traceback.format_exc()}")
            return {"filled_row": ""}
    
    def _combine_html_tables(self, state: FilloutTableState) -> FilloutTableState:
        """将表头，数据，表尾html整合在一起"""
        combined_html = state["headers_html"] + state["filled_row"] + state["footer_html"]
        with open(r"D:\asianInfo\ExcelAssist\conversations\1\Output\filled_table.html", "w", encoding="utf-8") as file:
            file.write(combined_html)
        return {"combined_html": combined_html}
    
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
                if "filled_row" in final_state and final_state["filled_row"]:
                    print(f"📊 最终结果已生成")
                    if len(str(final_state["filled_row"])) > 500:
                        print(f"📄 内容长度: {len(str(final_state['filled_row']))} 字符")
                    else:
                        print(f"📄 内容: {final_state['filled_row']}")
                        
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
                                                template_file = r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\template\燕云村残疾人补贴申领登记.txt",
                                                data_file_path = [r"D:\asianInfo\ExcelAssist\files\table_files\original\燕云村残疾人名单.xlsx"],
                                                headers_mapping={
  "表格结构": {
    "燕云村残疾人补贴申领登记": {
      "序号": ["燕云村残疾人名单.txt: 序号"],
      "姓名": ["燕云村残疾人名单.txt: 姓名"],
      "残疾类别": ["燕云村残疾人名单.txt: 残疾类别"],
      "监护人姓名": ["燕云村残疾人名单.txt: 监护人姓名"],
      "残疾证号": ["燕云村残疾人名单.txt: 残疾证号"],
      "地址": ["燕云村残疾人名单.txt: 地址"],
      "联系电话": ["燕云村残疾人名单.txt: 联系电话"],
      "补贴金额": [
        "推理规则: 根据重庆市残疾人补贴.txt中的补贴标准计算",
        "1. 困难残疾人生活补贴: 每人每月90元（适用于低保家庭中的各类残疾人）",
        "2. 重度残疾人护理补贴: 一级每人每月100元，二级每人每月90元",
        "3. 具体计算逻辑:",
        "   - 首先需要确认残疾人是否为低保家庭（当前数据中无此信息，需补充）",
        "   - 若为低保家庭，则享受困难残疾人生活补贴90元",
        "   - 若残疾类别为'精神'或'智力'且残疾证号第二位为'1'（一级）则额外享受100元护理补贴",
        "   - 若残疾类别为'精神'或'智力'且残疾证号第二位为'2'（二级）则额外享受90元护理补贴",
        "   - 其他情况仅享受基础补贴（若有）"
      ],
      "备注": ["燕云村残疾人名单.txt: 备注"]
    }
  },
  "表格总结": "该表格用于记录燕云村残疾人补贴申领信息，大部分字段可直接从'燕云村残疾人名单.txt'中获取。补贴金额字段需要根据重庆市残疾人补贴政策进行计算，当前缺少低保家庭信息，需要补充该信息才能准确计算补贴金额。"
})