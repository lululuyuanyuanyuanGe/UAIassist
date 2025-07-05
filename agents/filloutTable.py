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
    data_file_path: list[str]
    supplement_files_path: list[str]
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

    
    def create_initialize_state(self, template_file: str = None,
                                 data_file_path: list[str] = None, supplement_files_path: list[str] = None,
                                 headers_mapping: dict[str, str] = None) -> FilloutTableState:
        """This node will initialize the state of the graph"""
        return {
            "messages": [],
            "data_file_path": data_file_path, # excel files(xls) that has raw data
            "supplement_files_path": supplement_files_path,
            "template_file": template_file, # txt file of template file in html format
            "supplement_files_summary": "党龄需要根据党员名册中的转正时间计算，（1）党龄40—49年的，补助标准为：100元/月；（2）党龄50—54年的，补助标准为：120元/月；（3）党龄55年及以上的，补助标准为：150元/月。以上补助从党员党龄达到相关年限的次月起按月发放。补助标准根据市里政策作相应调整。2.党组织关系在区、年满80周岁、党龄满55年的老党员：（1）年龄80—89周岁且党龄满55年的，补助标准为500元/年；（2）年龄90—99周岁且党龄满55年的，补助标准为1000元/年；（3）年龄100周岁及以上的，补助标准为3000元/年。以上补助年龄、党龄计算时间截至所在年份的12月31日。",
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
            "CSV_data": []
        }
    
    def _combine_data_split_into_chunks(self, state: FilloutTableState) -> FilloutTableState:
        """整合所有需要用到的数据，并生将其分批，用于分批生成表格"""
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
            chunked_data = process_excel_files_with_chunking(excel_file_paths, supplement_content)
            print(f"✅ 成功生成 {len(chunked_data)} 个数据块")
            for chunk in chunked_data:
                print(f"==================🔍 数据块 ==================:")
                print(chunk)
            print("✅ _combine_data_split_into_chunks 执行完成")
            print("=" * 50)
            
            return {
                "combined_data_array": chunked_data
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
        print("\n🔄 开始执行: _generate_CSV_based_on_combined_data")
        print("=" * 50)
        
        system_prompt = f"""
你是一位专业的结构化数据填报专家，任务是根据提供的数据集和模板表头映射，生成符合结构的纯 CSV 格式数据。

请严格遵循以下规范执行：

【任务目标】
1. 分析数据集与模板字段映射（字段对应、计算逻辑、推理要求等）；
2. 对所有字段执行必要的数据转换、计算或推理操作；
3. 生成符合模板结构要求的纯数据行，每一行代表一条完整记录；
4. 输出结果必须严格为纯粹的 CSV 格式，不包含任何表头、注释或解释性文字。

【输出格式】
- 每一行是一条数据记录；
- 所有列顺序必须严格按照模板定义；
- 使用英文逗号 `,` 分隔字段；
- 每行以换行符结尾；
- **禁止输出表头（字段名）**；
- 输出结果应可直接导入 Excel，无需额外处理。

【字段处理要求】
- 日期格式：`yyyy-mm-dd`）；
- 清除无效或占位时间格式，如 `00.00.00.00`，直接替换为空；
- 对于像“备注”等可能没有明确来源字段的列，可根据上下文推理填写补充内容；
- 计算字段（如“党龄”、“补贴标准”）必须提供实际计算结果，不能省略；
- 若某字段无数据但允许为空，请保持空值（两个逗号之间留空）。

【禁止事项】
- ❌ 禁止输出任何解释、总结、注释或标签；
- ❌ 禁止输出非结构化内容；
- ❌ 禁止跳过映射或计算逻辑；
- ❌ 禁止输出表头或无关内容；

请立即开始数据处理，并**只返回纯 CSV 格式的数据记录**，每一行为一条记录，**不包含字段名**。
"""


        
        print("📋 系统提示准备完成")
        
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
                    messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)],
                    temperature=0.8
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
        with ThreadPoolExecutor(max_workers=5) as executor:  # Limit to 5 concurrent requests
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
            saved_file_path = save_csv_to_output(sorted_results, "generated_table")
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
        
        system_prompt = f"""
你是一位专业的 HTML 表格处理与数据填充专家，擅长使用 Python 将结构化数据写入 HTML 模板中，生成格式标准、美观可用的表格文件。

【任务目标】
请根据用户提供的 HTML 表格模板文件和数据源 CSV 文件，生成一段**完整、可执行**的 Python 脚本，实现以下功能：

1. **数据填充**
   - 使用 CSV 文件中的每一行数据填充 HTML 表格；
   - 仅替换模板中的“数据行”部分（即有序号的行）；
   - 清除原始模板中的示例数据行，使用 CSV 中的数据逐行追加；
   - 字段顺序应严格按照 HTML 模板的列顺序排列；
   - 第一列“序号”需自动从 1 开始递增，其他字段来自 CSV 数据。

2. **结构保持**
   - 保留 HTML 模板中原有的结构，包括：
     - `<colgroup>` 列宽设定；
     - `<thead>` 表头；
     - 标题行（如合并单元格的表名）；
     - 表尾备注（如含“审核人”、“制表人”的行）；
   - 不得破坏 HTML 原有结构；
   - 最终生成的 HTML 文件必须结构完整，浏览器可正常打开查看。

3. **技术要求**
   - 使用 `pandas` 读取 CSV 数据；
   - 使用 `BeautifulSoup` 解析和修改 HTML 内容；
   - 使用 `soup.new_tag()` 或 `copy.deepcopy()` 插入 `<tr>` 行；
   - 所有字段以 `<td>` 标签形式添加；
   - 文件读写使用 UTF-8 编码；
   - 输入 HTML 路径：`D:\\asianInfo\\ExcelAssist\\agents\\input\\老党员补贴.txt`；
   - 输入 CSV 路径：`D:\\path\\to\\processed_filled.csv`（可自定义）；
   - 输出 HTML 路径：`D:\\asianInfo\\ExcelAssist\\agents\\output\\老党员补贴_最终含李静.html`。

4. **输出要求**
   - 你必须**只输出完整、可直接运行的 Python 脚本**；
   - 不得输出 Markdown 格式、代码块标记（如```）、解释性文字或其他说明内容；
   - 所有依赖（如 `pandas`, `bs4`）必须在脚本中导入；
   - 结果 HTML 文件必须是结构闭合、浏览器可渲染的标准 HTML 表格。

【示例代码结构（请据此生成完整脚本）】

from bs4 import BeautifulSoup
import pandas as pd

# 路径设置
input_html_path = "D:/asianInfo/ExcelAssist/agents/input/老党员补贴.txt"
output_html_path = "D:/asianInfo/ExcelAssist/agents/output/老党员补贴_最终含李静.html"
csv_path = "D:/path/to/processed_filled.csv"  # 请将此路径替换为实际 CSV 文件路径

# 读取 HTML 模板
with open(input_html_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

# 读取 CSV 数据
df = pd.read_csv(csv_path)

# 获取表格并分析行结构
table = soup.find('table')
all_rows = table.find_all('tr')

# 查找数据行模板
template_row = None
for row in all_rows:
    cells = row.find_all('td')
    if cells and cells[0].text.strip().isdigit():
        template_row = row
        break

# 删除原始数据行
for row in all_rows:
    cells = row.find_all('td')
    if cells and cells[0].text.strip().isdigit():
        row.extract()

# 插入新的数据行
for i, (_, record) in enumerate(df.iterrows(), start=1):
    new_row = soup.new_tag("tr")
    # 序号
    td_serial = soup.new_tag("td")
    td_serial.string = str(i)
    new_row.append(td_serial)
    # 其他字段
    for value in record.values:
        td = soup.new_tag("td")
        td.string = str(value) if pd.notna(value) else ""
        new_row.append(td)
    table.append(new_row)

# 输出 HTML 文件
with open(output_html_path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
"""

        template = state["final_table"]
        CSV_data = state["CSV_data"]
        
        print(f"📄 模板表格内容长度: {len(template)} 字符")
        print(f"📊 CSV数据块数量: {len(CSV_data)}")
        
        user_input = f"需要填的模板表格:\n{template}\n需要填的CSV数据:\n{CSV_data}"
        print(f"📝 用户输入总长度: {len(user_input)} 字符")
        
        print("🤖 正在调用LLM生成CSV填充代码...")
        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
        
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
                "D:\\asianInfo\\ExcelAssist\\agents\\output\\老党员补贴_结果.html",
                "agents\\output\\老党员补贴_结果.html",
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
        
        system_prompt = f"""你的任务是根据CSV填充代码的报错信息和上一次的代码，总结出错误的原因，并反馈给代码生成智能体，让其根据报错重新生成代码。

你需要特别关注以下几个方面：
1. CSV数据格式是否正确
2. 模板表格结构解析是否正确
3. 数据填充逻辑是否有问题
4. 文件路径和读写权限是否正确
5. 数据类型转换是否正确

你不需要生成改进的代码，你只需要总结出错误的原因，并反馈给代码生成智能体，让其根据报错重新生成代码。
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
        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=input_2_LLM)])
        
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


        file_path = state["template_file"]
        template_file_content = read_txt_file(file_path)
        number_of_rows = "需要生成100行数据行"
        base_input = f"HTML模板地址: {file_path}\n HTML模板内容:\n{template_file_content}\n \n需求:\n{number_of_rows}"

        print(f"📄 读取模板文件: {file_path}")
        print(f"📊 模板内容长度: {len(template_file_content)} 字符")
        print(f"📝 基础输入长度: {len(base_input)} 字符")

        # Fix: Check if execution was NOT successful to use error recovery
        if not state["template_completion_code_execution_successful"]:
            previous_code = state["template_file_completion_code"]
            error_message = state.get("error_message_summary", state.get("error_message", ""))
            error_input = f"上一次生成的代码:\n{previous_code}\n\n错误信息:\n{error_message}\n\n请根据错误信息修复代码。"
            full_input = f"{base_input}\n\n{error_input}"
            print("🤖 正在基于错误信息重新生成Python代码...")
            print(f"📊 包含错误信息的输入长度: {len(full_input)} 字符")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=full_input)])
        else:
            print("🤖 正在生成Python代码...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=base_input)])

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
            print("✅ _execute_template_completion_code_from_LLM 执行完成")
            print("=" * 50)
            return {
                "template_completion_code_execution_successful": True,
                "error_message": "",
                "final_table": html_content
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



    # def _convert_html_to_excel(self, state: FilloutTableState) -> FilloutTableState:
    #     """把通过代码构建的html表格通过libreoffice转换为excel表格"""
    #     try:
    #         import subprocess
    #         import tempfile
    #         import os
            
    #         # Get the HTML content from state
    #         html_content = state.get("styled_html_table", state.get("final_table", ""))
            
    #         if not html_content:
    #             print("❌ 没有找到HTML表格内容")
    #             return {"error_message": "没有找到HTML表格内容"}
            
    #         # If final_table is a file path, read the content
    #         if isinstance(html_content, str) and Path(html_content).exists():
    #             html_content = read_txt_file(html_content)
            
    #         # Create temporary HTML file
    #         with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
    #             temp_html.write(html_content)
    #             temp_html_path = temp_html.name
            
    #         # Output paths
    #         output_dir = Path("agents/output")
    #         output_dir.mkdir(exist_ok=True)
            
    #         html_output_path = output_dir / "老党员补贴_结果.html"
    #         excel_output_path = output_dir / "老党员补贴_结果.xlsx"
            
    #         # Save the final HTML file
    #         try:
    #             with open(html_output_path, 'w', encoding='utf-8') as f:
    #                 f.write(html_content)
    #             print(f"✅ HTML文件已保存: {html_output_path}")
    #         except Exception as e:
    #             print(f"❌ 保存HTML文件失败: {e}")
            
    #         # Convert to Excel using LibreOffice
    #         try:
    #             # Use the specified LibreOffice path
    #             libreoffice_path = r"D:\LibreOffice\program\soffice.exe"
                
    #             # Check if LibreOffice exists
    #             if not os.path.exists(libreoffice_path):
    #                 print(f"❌ 未找到LibreOffice: {libreoffice_path}")
    #                 return {"error_message": f"LibreOffice not found at {libreoffice_path}"}
                
    #             # Convert HTML to Excel using LibreOffice
    #             cmd = [
    #                 libreoffice_path,
    #                 '--headless',
    #                 '--convert-to', 'xlsx',
    #                 '--outdir', str(output_dir),
    #                 temp_html_path
    #             ]
                
    #             print(f"🔄 正在转换HTML到Excel...")
    #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
    #             if result.returncode == 0:
    #                 print(f"✅ Excel文件已生成: {excel_output_path}")
    #             else:
    #                 print(f"❌ LibreOffice转换失败: {result.stderr}")
    #                 return {"error_message": f"LibreOffice conversion failed: {result.stderr}"}
                    
    #         except subprocess.TimeoutExpired:
    #             print("❌ LibreOffice转换超时")
    #             return {"error_message": "LibreOffice conversion timeout"}
    #         except Exception as e:
    #             print(f"❌ Excel转换失败: {e}")
    #             return {"error_message": f"Excel conversion failed: {str(e)}"}
            
    #         # Clean up temporary file
    #         try:
    #             os.unlink(temp_html_path)
    #         except Exception as e:
    #             print(f"⚠️ 清理临时文件失败: {e}")
            
    #         return {
    #             "final_table": str(html_output_path),
    #             "messages": [AIMessage(content=f"表格填写完成！\n- HTML文件: {html_output_path}\n- Excel文件: {excel_output_path}")]
    #         }
            
    #     except Exception as e:
    #         print(f"❌ 转换过程中发生错误: {e}")
    #         return {"error_message": f"转换失败: {str(e)}"}

    def run_fillout_table_agent(self, session_id: str = "1") -> None:
        """This function will run the fillout table agent using invoke method with manual debug printing"""
        print("\n🚀 启动 FilloutTableAgent")
        print("=" * 60)
        
        initial_state = self.create_initialize_state(
            template_file = r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_files\老党员补贴.txt",
            data_file_path = [r"D:\asianInfo\ExcelAssist\燕云村case\燕云村2024年度党员名册.xlsx"],
            supplement_files_path = [r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_files\[正文稿]关于印发《重庆市巴南区党内关怀办法（修订）》的通__知.txt"],
            headers_mapping={
    "表格结构": {
        "重庆市巴南区享受生活补贴老党员登记表": {
            "基本信息": [
                {
                    "序号": "燕云村2024年度党员名册.txt: 序号"
                },
                {
                    "姓名": "燕云村2024年度党员名册.txt: 姓名"
                },
                {
                    "性别": "燕云村2024年度党员名册.txt: 性别"
                },
                {
                    "民族": "燕云村2024年度党员名册.txt: 民族"
                },
                {
                    "身份证号码": "燕云村2024年度党员名册.txt: 公民身份证号"
                },
                {
                    "出生时间": "燕云村2024年度党员名册.txt: 出生日期"
                },
                {
                    "所在党支部": "燕云村2024年度党员名册.txt: 所属支部"
                },
                {
                    "成为正式党员时间": "燕云村2024年度党员名册.txt: 转正时间"
                },
                {
                    "党龄（年）": "推理规则: 当前年份(2024) - 转正时间的年份"
                },
                {
                    "生活补贴标准（元／月）": "推理规则: 根据《重庆市巴南区党内关怀办法（修订）》中关于老党员敬老补助的规定，需结合党龄和年龄综合确定。例如：党龄满50年且年龄80岁以上补贴500元/月，党龄满40年补贴300元/月等（需补充具体政策条款）"
                },
                {
                    "备注": "推理规则: 手动填写或根据其他特殊情况补充说明"
                }
            ]
        }
        }
    })
        config = {"configurable": {"thread_id": session_id}}
        
        print(f"📋 初始状态创建完成，会话ID: {session_id}")
        print(f"📄 模板文件: {initial_state['template_file']}")
        print(f"📊 数据文件数量: {len(initial_state['data_file_path'])}")
        print(f"📚 补充文件数量: {len(initial_state['supplement_files_path'])}")
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
    fillout_table_agent.run_fillout_table_agent(session_id = "1")