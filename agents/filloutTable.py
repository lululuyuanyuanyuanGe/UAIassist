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
from utilities.file_process import (read_txt_file, 
                                    process_excel_files_with_chunking)
from utilities.modelRelated import invoke_model
from utilities.html_generator import (
    extract_empty_row_html_code_based,
    extract_headers_html_code_based,
    extract_footer_html_code_based,
    transform_data_to_html_code_based,
    combine_html_parts
)
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
import csv

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
    largest_file_row_num: int
    combined_html: str
    # Use lambda reducers for concurrent updates
    empty_row_html: Annotated[str, lambda old, new: new if new else old]
    headers_html: Annotated[str, lambda old, new: new if new else old]
    footer_html: Annotated[str, lambda old, new: new if new else old]
    CSV_data: Annotated[list[str], lambda old, new: new if new else old]



class FilloutTableAgent:
    def __init__(self):
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("combine_data_split_into_chunks", self._combine_data_split_into_chunks)
        graph.add_node("generate_CSV_based_on_combined_data", self._generate_CSV_based_on_combined_data)
        graph.add_node("transform_data_to_html", self._transform_data_to_html_code_based)  # Use code-based function
        graph.add_node("extract_empty_row_html", self._extract_empty_row_html_code_based)
        graph.add_node("extract_headers_html", self._extract_headers_html_code_based)
        graph.add_node("extract_footer_html", self._extract_footer_html_code_based)
        graph.add_node("combine_html_tables", self._combine_html_tables)
        graph.add_node("shield_for_transform_data_to_html", self._shield_for_transform_data_to_html)
        
        # Define the workflow
        graph.add_edge(START, "combine_data_split_into_chunks")
        graph.add_conditional_edges("combine_data_split_into_chunks", self._route_after_combine_data_split_into_chunks)
        graph.add_edge("extract_empty_row_html", "shield_for_transform_data_to_html")
        graph.add_edge("extract_headers_html", "shield_for_transform_data_to_html")
        graph.add_edge("extract_footer_html", "shield_for_transform_data_to_html")
        graph.add_edge("generate_CSV_based_on_combined_data", "shield_for_transform_data_to_html")
        graph.add_edge("shield_for_transform_data_to_html", "transform_data_to_html")
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
            print(f"📋 开始处理 {len(state["data_file_path"])} 个数据文件")
            
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
        # return state
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
        
        # Dynamically adjust max_workers based on actual data size
        max_workers = min(15, len(chunks_with_indices))  # Use fewer workers if we have less data
        print(f"🚀 开始并发处理 {len(chunks_with_indices)} 个数据块...")
        print(f"👥 使用 {max_workers} 个并发工作者")
        
        # Use ThreadPoolExecutor for concurrent processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
        # print(f"🔍 生成的CSV数据: {sorted_results}")
        return {
            "CSV_data": sorted_results
        }
    
    def _extract_empty_row_html_code_based(self, state: FilloutTableState) -> FilloutTableState:
        """提取模板表格中的空行html代码 - 基于代码的高效实现"""
        try:
            empty_row_html = extract_empty_row_html_code_based(state["template_file"])
            return {"empty_row_html": empty_row_html}
        except Exception as e:
            print(f"❌ _extract_empty_row_html_code_based 执行失败: {e}")
            return {"empty_row_html": ""}

    def _extract_headers_html_code_based(self, state: FilloutTableState) -> FilloutTableState:
        """提取出html模板表格的表头html代码 - 基于代码的高效实现"""
        try:
            headers_html = extract_headers_html_code_based(state["template_file"])
            return {"headers_html": headers_html}
        except Exception as e:
            print(f"❌ _extract_headers_html_code_based 执行失败: {e}")
            return {"headers_html": ""}

    def _extract_footer_html_code_based(self, state: FilloutTableState) -> FilloutTableState:
        """提取出html模板表格的结尾html代码 - 基于代码的高效实现"""
        try:
            footer_html = extract_footer_html_code_based(state["template_file"])
            return {"footer_html": footer_html}
        except Exception as e:
            print(f"❌ _extract_footer_html_code_based 执行失败: {e}")
            return {"footer_html": ""}

    def _transform_data_to_html_code_based(self, state: FilloutTableState) -> FilloutTableState:
        """将数据转换为html代码 - 基于代码的高效实现"""
        try:
            # Read CSV data file path
            csv_file_path = f"conversations/{state['session_id']}/CSV_files/synthesized_table_with_only_data.csv"
            
            # Get empty row HTML template from state
            empty_row_html = state.get("empty_row_html", "")
            if not empty_row_html:
                print("⚠️ 未找到空行HTML模板")
                return {"filled_row": ""}
            
            # Use the utility function to transform data
            filled_row_html = transform_data_to_html_code_based(
                csv_file_path=csv_file_path,
                empty_row_html=empty_row_html,
                session_id=state["session_id"]
            )
            
            return {"filled_row": filled_row_html}
            
        except Exception as e:
            print(f"❌ _transform_data_to_html_code_based 执行失败: {e}")
            import traceback
            print(f"错误详情: {traceback.format_exc()}")
            return {"filled_row": ""}
    
    def _combine_html_tables(self, state: FilloutTableState) -> FilloutTableState:
        """将表头，数据，表尾html整合在一起，并添加全局美化样式"""
        try:
            # 获取各部分HTML
            headers_html = state.get("headers_html", "")
            data_html = state.get("filled_row", "")
            footer_html = state.get("footer_html", "")
            
            # Use the utility function to combine HTML parts
            combined_html = combine_html_parts(
                headers_html=headers_html,
                data_html=data_html,
                footer_html=footer_html
            )
            
            # 保存到文件
            output_path = f"conversations/{state['session_id']}/output/combined_html.html"
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as file:
                file.write(combined_html)
            
            print(f"✅ 美化表格已保存到: {output_path}")
            
            return {"combined_html": combined_html}
        except Exception as e:
            print(f"❌ _combine_html_tables 执行失败: {e}")
            import traceback
            print(f"错误详情: {traceback.format_exc()}")
            return {"combined_html": ""}
    
    def _shield_for_transform_data_to_html(self, state: FilloutTableState) -> FilloutTableState:
        """Shield node for transform_data_to_html"""
        print("\n🔄 开始执行: _shield_for_transform_data_to_html")
        print("=" * 50)
        
        try:
            # Ensure all required components are available
            if not state["CSV_data"] or not state["empty_row_html"] or not state["headers_html"] or not state["footer_html"]:
                print("❌ 缺少必要组件，无法转换为HTML")
                return state
            
            print("✅ _shield_for_transform_data_to_html 执行完成")
            print("=" * 50)
            return state
        
        except Exception as e:
            print(f"❌ _shield_for_transform_data_to_html 执行失败: {e}")
            import traceback
            print(f"错误详情: {traceback.format_exc()}")
            return state
    
    def run_fillout_table_agent(self, session_id: str,
                                template_file: str,
                                data_file_path: list[str],
                                headers_mapping: dict[str, str]
                                ) -> None:
        """This function will run the fillout table agent using invoke method with manual debug printing"""
        print("\n🚀 启动 FilloutTableAgent")
        print("=" * 60)
        print("模板文件：", template_file)
        
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
                                                template_file = r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\template\种植险投保清单模版.txt",
                                                data_file_path = [r"D:\asianInfo\ExcelAssist\files\table_files\original\2024年农作物登记.xlsx",
                                                                  r"D:\asianInfo\ExcelAssist\files\table_files\original\种植户银行卡号登记.xlsx"],
                                                headers_mapping={
  "表格结构": {
    "序号": ["2024年农作物登记.txt: 序号"],
    "姓名": ["2024年农作物登记.txt: 姓名"],
    "身份证号码": ["2024年农作物登记.txt: 身份证号码"],
    "电话号码": ["2024年农作物登记.txt: 电话号码"],
    "玉米（亩）": ["2024年农作物登记.txt: 玉米（亩）"],
    "水稻（亩）": ["2024年农作物登记.txt: 水稻（亩）"],
    "开户银行": ["种植户银行卡号登记.txt: 开户银行"],
    "银行账号": ["种植户银行卡号登记.txt: 银行账号"],
    "是否脱贫户": ["种植户银行卡号登记.txt: 是否脱贫户"],
    "备注": ["推理规则: 根据玉米水稻种植保险相关说明.txt中的保险金额和赔偿计算规则，可以在此字段备注保险金额或赔偿相关信息。例如：玉米每亩保险金额为800元，水稻每亩保险金额为1000元；赔偿金额=每亩保险金额×损失面积×损失程度，累计赔偿不超过总保险金额。"]       
  },
  "表格总结": "该表格为燕云村2024年农作物保险投保清单，用于记录农户投保信息，包括个人基本信息、投保作物面积、银行账户信息及脱贫户标识等，适用于村级农作物保险投保管理。所有字段均来自2024年农作物登记.txt和种植户银行卡号登记.txt两个数据文件，备注字段根据玉米水稻种植保险相关说明.txt中的保险金额和赔偿计算规则进行推理填写。"
})