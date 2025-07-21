import sys
from pathlib import Path
import io
import contextlib

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated

from utils.file_process import (read_txt_file, 
                                process_excel_files_for_integration,
                                process_excel_files_for_merge)
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

load_dotenv()

class FilloutTableState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    data_file_path: list[str]
    supplement_files_summary: str
    template_file: str
    fill_CSV_2_template_code: str
    combined_data: str
    filled_row: str
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
    modify_after_first_fillout: bool
    village_name: str
    strategy_for_data_combination: str

class FilloutTableAgent:
    def __init__(self):
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("determine_strategy_for_data_combination", self._determine_strategy_for_data_combination)
        graph.add_node("combine_data_for_multitable_integration", self._combine_data_for_multitable_integration)
        graph.add_node("combine_data_for_multitable_merge", self._combine_data_for_multitable_merge)
        graph.add_node("generate_CSV_based_on_combined_data", self._generate_CSV_based_on_combined_data)
        graph.add_node("transform_data_to_html", self._transform_data_to_html_code_based)  # Use code-based function
        graph.add_node("extract_empty_row_html", self._extract_empty_row_html_code_based)
        graph.add_node("extract_headers_html", self._extract_headers_html_code_based)
        graph.add_node("extract_footer_html", self._extract_footer_html_code_based)
        graph.add_node("combine_html_tables", self._combine_html_tables)
        graph.add_node("shield_for_transform_data_to_html", self._shield_for_transform_data_to_html)
        
        # Define the workflow
        graph.add_edge(START, "determine_strategy_for_data_combination")
        graph.add_conditional_edges("determine_strategy_for_data_combination", self._route_after_determine_strategy_for_data_combination)
        graph.add_conditional_edges("combine_data_for_multitable_integration", self._route_after_chunking_data)
        graph.add_conditional_edges("combine_data_for_multitable_merge", self._route_after_chunking_data)
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
                                 supplement_files_summary: str = "",
                                 modify_after_first_fillout: bool = False,
                                 village_name: str = "") -> FilloutTableState:
        """This node will initialize the state of the graph"""
        return {
            "messages": [],
            "session_id": session_id,
            "data_file_path": data_file_path, # excel files(xls) that has raw data
            "template_file": template_file, # txt file of template file in html format
            "fill_CSV_2_template_code": "",
            "combined_data": "",
            "filled_row": "",
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
            "combined_html": "",
            "modify_after_first_fillout": False,
            "village_name": village_name,
            "strategy_for_data_combination": ""
        }
    def _determine_strategy_for_data_combination(self, state: FilloutTableState) -> FilloutTableState:
        """根据我们要填写的表格来决定数据整合的策略"""
        system_prompt = """你是一个专业的数据整合策略分析专家。

【任务】
分析给定的表格结构映射，确定数据整合策略。

【策略类型】
有且仅有两种策略：

1. **多表整合** - 特征：
   - 存在一个主要数据源（通常是最大的表格或包含最多核心信息的表格）
   - 其他表格作为补充数据源，用于填充缺失字段
   - 各字段的数据来源相对独立，不存在跨表格的字段合并
   - 示例：表格结构中字段来源格式为"表格A:字段X"、"表格B:字段Y"等

2. **多表合并** - 特征：
   - 多个表格地位相等，需要将它们的数据行合并到一张表
   - 同一字段可能来自多个表格的相同字段
   - 字段来源格式包含"/"分隔符，如"表格A:字段X/表格B:字段X"
   - 最终表格的行数等于所有源表格的行数之和

【分析步骤】
1. 检查字段来源格式：是否包含"/"分隔符
2. 判断数据源关系：是主从关系还是平等合并关系
3. 确定最终策略

【输出要求】
仅输出以下两个选项之一，不得包含任何其他内容：
- 多表整合
- 多表合并

【示例】
输入："表头1": ["表格1:字段A"]，"表头2": ["表格2:字段B"] → 输出：多表整合
输入："表头1": ["表格1:字段A/表格2:字段A"] → 输出：多表合并
        """
        table_structure = state["headers_mapping"]
        response = invoke_model(model_name = "deepseek-ai/DeepSeek-V3", 
                                messages = [SystemMessage(content = system_prompt), HumanMessage(content = table_structure)])
        return {
            "strategy_for_data_combination": response
        }

    def _route_after_determine_strategy_for_data_combination(self, state: FilloutTableState) -> str:
        if state["strategy_for_data_combination"] == "多表整合":
            return "combine_data_for_multitable_integration"
        elif state["strategy_for_data_combination"] == "多表合并":
            return "combine_data_for_multitable_merge"
        else:
            return "combine_data_for_multitable_integration"  # default fallback
    
    def _combine_data_for_multitable_integration(self, state: FilloutTableState) -> FilloutTableState:
        """将多个表格整合"""
        # return
        print("\n🔄 开始执行: _combine_data_split_into_chunks")
        print("=" * 50)
        if not state["modify_after_first_fillout"]:
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
                chunked_result = process_excel_files_for_integration(excel_file_paths=excel_file_paths, 
                                                                session_id=state["session_id"],
                                                                chunk_nums=15, largest_file=None,  # Let function auto-detect
                                                                data_json_path="agents/data.json",
                                                                village_name=state["village_name"])
                
                # Extract chunks and row count from the result
                chunked_data = chunked_result["combined_chunks"]
                largest_file_row_count = chunked_result["largest_file_row_count"]
                
                
                for chunk in chunked_data:
                    print(f"==================🔍 数据块 ==================:")
                    print(chunk)

                print(f"✅ 成功生成 {len(chunked_data)} 个数据块")
                print(f"📊 最大文件行数: {largest_file_row_count}")
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
        else:
            return state
    
    def _combine_data_for_multitable_merge(self, state: FilloutTableState) -> FilloutTableState:
        """将多个表格合并起来 - 所有data_file_path中的文件都作为核心数据进行合并"""
        print("\n🔄 开始执行: _combine_data_for_multitable_merge")
        print("=" * 50)
        if not state["modify_after_first_fillout"]:
            try:
                # Get Excel file paths from state
                excel_file_paths = []
                print(f"📋 开始处理 {len(state["data_file_path"])} 个数据文件（全部作为核心数据）")
                
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
                    print("✅ _combine_data_for_multitable_merge 执行完成(错误)")
                    print("=" * 50)
                    return {"combined_data_array": []}
                
                print(f"📊 准备处理 {len(excel_file_paths)} 个Excel文件进行合并（全部作为核心数据）")
                
                # For multitable merge, we treat all files as core data and combine them together
                # Rather than chunking based on one largest file, we merge all files row by row
                combined_data_result = process_excel_files_for_merge(
                    excel_file_paths=excel_file_paths,
                    session_id=state["session_id"],
                    village_name=state["village_name"],
                    chunk_nums=15
                )
                
                # Extract chunks and row count from the result
                chunked_data = combined_data_result["combined_chunks"]
                total_row_count = combined_data_result["total_row_count"]
                
                for chunk in chunked_data:
                    print(f"==================🔍 合并数据块 ==================:")
                    print(chunk)

                print(f"✅ 成功生成 {len(chunked_data)} 个合并数据块")
                print(f"📊 总行数: {total_row_count}")
                print("✅ _combine_data_for_multitable_merge 执行完成")
                print("=" * 50)
                
                return {
                    "combined_data_array": chunked_data,
                    "largest_file_row_num": total_row_count
                }
                
            except Exception as e:
                print(f"❌ _combine_data_for_multitable_merge 执行失败: {e}")
                import traceback
                print(f"错误详情: {traceback.format_exc()}")
                print("✅ _combine_data_for_multitable_merge 执行完成(错误)")
                print("=" * 50)
                return {
                    "combined_data_array": []
                }
        else:
            return state
    
    
    def _route_after_chunking_data(self, state: FilloutTableState) -> str:
        """并行执行模板代码的生成和CSV数据的合成"""
        print("\n🔀 开始执行: _route_after_combine_data_split_into_chunks")
        print("=" * 50)
        if not state["modify_after_first_fillout"]:
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
        if not state["modify_after_first_fillout"]:
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

让我们一步一步来解决这个数据转换和合成问题。

【任务目标】
根据多个数据源，以核心数据源为主要依据，结合参考数据源进行补充验证，将数据准确转换为目标 CSV 格式。

【数据源说明】
1. 核心数据源：标记为"=== 核心数据源：xxx ==="的数据，主要作用是确定要生成的数据行数和提供数据切分的基础结构
2. 参考数据源：标记为"=== 参考数据源：xxx ==="的数据，提供用于填充目标表头字段的具体信息
3. 补充信息和上下文：标记为"=== 补充信息和上下文 ==="的内容，用于理解业务背景和填充规则

【核心工作原则】
⭐ 严格按照表头映射：生成的每个字段必须严格对应模板表头映射中的定义和要求
⭐ 核心数据源决定行数：根据核心数据源中的数据条目数量来确定需要生成的CSV行数
⭐ 全数据源信息填充：从所有可用数据源中获取信息来填充表头映射要求的字段内容
⭐ 保持逻辑一致性：确保生成的数据在业务逻辑上合理且字段间相互协调

【输入内容】
1. 模板表头映射（JSON 格式）：描述目标表格每一列的来源、计算逻辑或推理规则
2. 核心数据源：主要用于合成的数据集
3. 参考数据源：用于补充验证的数据集
4. 补充信息：业务背景和填充规则

【详细推理要求】
🔍 对于每一行数据，你必须进行逐行逐列的深度推理：

第一层推理：逐行数据处理
- 识别当前处理的数据行
- 确定该行数据的完整性和有效性
- 明确该行数据在核心数据源中的位置和上下文

第二层推理：逐列字段推理
对于每个目标字段，进行以下链式推理：
1. 字段定义理解：表头映射中这个字段要求什么类型的数据？
2. 数据源搜索：在所有数据源中查找能满足该字段要求的信息
3. 数据匹配验证：找到的数据是否符合表头映射中的字段定义？
4. 数据优先级选择：如果多个数据源都有相关信息，如何选择最合适的？
5. 数据转换处理：需要进行什么格式转换或计算以匹配表头要求？
6. 合理性验证：最终确定的数据是否逻辑合理且符合表头映射？

【推理步骤】
请严格按照以下步骤进行推理，并展示每一步的思考过程：

步骤1：数据源全面分析
- 识别核心数据源的条目数量，确定需要生成的CSV行数
- 识别参考数据源和补充信息的内容和结构
- 理解各数据源中可用于填充表头字段的信息
- 预估数据处理的复杂度和潜在问题

步骤2：映射规则深度解析
- 逐一分析每个目标字段的定义和要求
- 明确每个字段需要什么类型的数据和格式
- 确定哪些字段可以从哪些数据源获取信息
- 识别需要计算、推理或格式转换的字段

步骤3：逐行数据处理（Chain of Thought）
对于每一行数据，进行以下详细推理：

【数据行 X 的处理】
→ 行数据识别：当前处理的是第X行，对应核心数据源中的第X个条目
→ 逐列字段推理：
  ├── 字段1：[字段名称]
  │   ├── 定义理解：表头映射中该字段要求什么类型的数据？
  │   ├── 数据源搜索：在所有数据源中查找相关信息 [搜索结果]
  │   ├── 数据验证：找到的数据是否符合表头映射要求？
  │   ├── 优先级选择：（如有多个来源）选择最合适的数据源
  │   ├── 转换处理：需要进行 [具体转换] 以匹配表头要求
  │   └── 最终确定：该字段的值为 [最终值]
  ├── 字段2：[字段名称]
  │   ├── 定义理解：表头映射中该字段要求什么类型的数据？
  │   ├── 数据源搜索：在所有数据源中查找相关信息 [搜索结果]
  │   └── ... （重复上述过程）
  └── 字段N：[字段名称]
      └── ... （重复上述过程）
→ 行数据完整性检查：该行是否包含所有表头映射要求的字段？
→ 行数据一致性验证：各字段间是否逻辑一致且符合业务规则？

步骤4：数据质量全面验证
- 验证每个字段的合理性和准确性
- 检查与核心数据源的一致性
- 确认字段顺序和格式正确
- 进行跨行数据的一致性检查

【输出格式】
请按照以下格式输出：

  === 推理过程 ===
  [详细展示你的完整思考过程，必须包括：
  - 数据源全面分析（核心数据源行数确定，各数据源可用信息）
  - 映射规则深度解析（每个表头字段的具体要求）
  - 逐行逐列的Chain of Thought推理过程
  - 每个字段的6步详细推理链（严格按照表头映射要求）
  - 数据质量验证结果]

=== 最终答案 ===
[仅输出纯净的 CSV 数据行，使用英文逗号分隔]

  【质量要求】
  ✅ 推理过程必须展示每一行每一列的详细思考链路
  ✅ 生成的CSV行数必须与核心数据源条目数量严格对应
  ✅ 每个字段的内容必须严格符合表头映射中的定义和要求
  ✅ 可以从所有数据源中获取信息，但必须服务于表头映射的要求
  ✅ 最终答案仅包含CSV数据，不含任何其他内容
  ✅ 字段顺序必须与模板表头映射完全一致
  ✅ 严禁遗漏字段、重复字段或输出空值
  ✅ 每个字段的推理过程都必须清晰可追溯且基于表头映射

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
                        temperature=0.2, silent_mode=True
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
                from utils.file_process import save_csv_to_output
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
        
        else:
            return state
    
        
    def _extract_empty_row_html_code_based(self, state: FilloutTableState) -> FilloutTableState:
        """提取模板表格中的空行html代码 - 基于代码的高效实现"""
        try:
            empty_row_html = extract_empty_row_html_code_based(state["template_file"])
            print("empty_row_html", empty_row_html)
            return {"empty_row_html": empty_row_html}
        except Exception as e:
            print(f"❌ _extract_empty_row_html_code_based 执行失败: {e}")
            return {"empty_row_html": ""}

    def _extract_headers_html_code_based(self, state: FilloutTableState) -> FilloutTableState:
        """提取出html模板表格的表头html代码 - 基于代码的高效实现"""
        try:
            headers_html = extract_headers_html_code_based(state["template_file"])
            print("headers_html", headers_html)
            return {"headers_html": headers_html}
        except Exception as e:
            print(f"❌ _extract_headers_html_code_based 执行失败: {e}")
            return {"headers_html": ""}

    def _extract_footer_html_code_based(self, state: FilloutTableState) -> FilloutTableState:
        """提取出html模板表格的结尾html代码 - 基于代码的高效实现"""
        try:
            footer_html = extract_footer_html_code_based(state["template_file"])
            print("footer_html", footer_html)
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
                session_id=state["session_id"],
                template_file_path=state["template_file"]
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
                                headers_mapping: dict[str, str],
                                modify_after_first_fillout: bool = False,
                                village_name: str = ""
                                ) -> None:
        """This function will run the fillout table agent using invoke method with manual debug printing"""
        print("\n🚀 启动 FilloutTableAgent")
        print("=" * 60)
        print("模板文件：", template_file)
        
        initial_state = self.create_initialize_state(
            session_id = session_id,
            template_file = template_file,
            data_file_path = data_file_path,
            headers_mapping=headers_mapping,
            modify_after_first_fillout=modify_after_first_fillout,
            village_name=village_name
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
                                                template_file = r"conversations\1\user_uploaded_files\template\七田村_表格模板_20250721_161945.txt",
                                                data_file_path = ['城保名册.xls', '农保名册.xls'],
                                                headers_mapping={
  "表格标题": "七田村低保补贴汇总表",
  "表格结构": {
    "基本信息": [
      "城保名册.xls/农保名册.xls: 序号",
      "城保名册.xls/农保名册.xls: 户主姓名",
      "城保名册.xls/农保名册.xls: 身份证号码",
      "城保名册.xls/农保名册.xls: 低保证号",
      "推理规则: 居民类型(城保/农保) - 根据文件名自动判断，城保名册.xls对应'城保'，农保名册.xls对应'农保'"
    ],
    "保障情况": {
      "保障人数": [
        "城保名册.xls/农保名册.xls: 保障人数.分解.重点保障人数",
        "城保名册.xls/农保名册.xls: 保障人数.分解.残疾人数"
      ],
      "领取金额": [
        "城保名册.xls/农保名册.xls: 领取金额.分解.家庭补差",
        "城保名册.xls/农保名册.xls: 领取金额.分解.重点救助60元",
        "城保名册.xls/农保名册.xls: 领取金额.分解.重点救助100元",
        "城保名册.xls/农保名册.xls: 领取金额.分解.残疾人救助"
      ]
    },
    "领取信息": [
      "城保名册.xls/农保名册.xls: 领款人签字(章)",
      "城保名册.xls/农保名册.xls: 领款时间"
    ]
  }
})