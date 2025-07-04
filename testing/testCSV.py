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
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content, read_txt_file, process_excel_files_with_chunking, clean_and_pretty_print_csv
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


def combine_data_split_into_chunks(file_path: list[str]) -> list[str]:
        """整合所有需要用到的数据，并生将其分批，用于分批生成表格"""
        try:
            # Get Excel file paths from state
            excel_file_paths = []
            
            # Convert data files to Excel paths if they're not already
            for file_path in file_path:
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

            supplement_content = "1. 重庆市巴南区党内关怀办法（修订）明确关怀对象为三类：党龄40年及以上的农村老党员和未享受城镇养老保险或离退休待遇的城镇老党员；年满80周岁且党龄55年及以上的老党员；以及因重大疾病、灾难、变故等导致家庭生活特别困难的党员。2. 敬老补助标准按党龄年限分档执行：党龄40-49年补助100元/月，50-54年补助120元/月，55年及以上补助150元/月，补助自符合条件次月起按月发放，标准随市级政策调整。"
            
            chunked_data = process_excel_files_with_chunking(excel_file_paths, supplement_content)

            return chunked_data
            
        except Exception as e:
            print(f"❌ Error in _combine_data_split_into_chunks: {e}")
            return []



def generate_CSV_based_on_combined_data(chunk_data: list[str]) -> str:
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
- 不需要生成任何解释，不要加入CSV标签
- 不要生成表头，只生成数据
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

"表格结构": {{
    "重庆市巴南区享受生活补贴老党员登记表": {{  
      "序号": [],
      "姓名": [],
      "性别": [],
      "民族": [],
      "身份证号码": [],
      "出生时间": [],
      "所在党支部": [],
      "成为正式党员时间": [],
      "党龄（年）": [],
      "生活补贴标准（元／月）": [],
      "备注": []
    }}
}}
"""
                print(f"🤖 Processing chunk {index + 1}...")
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
        chunks_with_indices = [(chunk, i) for i, chunk in enumerate(chunk_data)]
        
        if not chunks_with_indices:
            print("⚠️ No chunks to process")
            return []
        
        print(f"🚀 Starting concurrent processing of {len(chunks_with_indices)} chunks...")
        
        # Use ThreadPoolExecutor for concurrent processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:  # Limit to 3 concurrent requests
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
        
        return sorted_results




file_path = [r"D:\asianInfo\ExcelAssist\燕云村case\燕云村2024年度党员名册.xlsx"]
chunked_data = combine_data_split_into_chunks(file_path)

print("\n" + "="*80)
print("🚀 Starting CSV data generation with concurrent processing...")
print("="*80)

data = generate_CSV_based_on_combined_data(chunked_data)

print("\n" + "="*80)
print("📊 Pretty printing cleaned CSV data...")
print("="*80)

# Use the pretty print function to clean and display the data nicely
cleaned_df = clean_and_pretty_print_csv(data, output_file="testing/cleaned_党员补贴_output.csv")