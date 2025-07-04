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

def combine_data_split_into_chunks(excel_file_list: list[str], word_file_list: list[str]) -> list[str]:
    """整合所有需要用到的数据，并生将其分批，用于分批生成表格"""
    try:
        # Get Excel file paths from state
        excel_file_paths = []
        
        # Convert data files to Excel paths if they're not already
        for file_path in excel_file_list:
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
        if word_file_list:
            supplement_content = "补充文件内容\n" + "补充内容。。。。。。。"
        
        chunked_data = process_excel_files_with_chunking(excel_file_paths, supplement_content)

        return chunked_data
        
    except Exception as e:
        print(f"❌ Error in _combine_data_split_into_chunks: {e}")
        return []

word_list = ["这个是补充内容"]
file_list = [r"D:\asianInfo\数据\新槐村\7.2接龙镇附件4.xlsx", r"D:\asianInfo\数据\新槐村\10.24接龙镇附件4：脱贫人口小额贷款贴息发放明细表.xlsx", r"D:\asianInfo\数据\新槐村\12.3附件4：脱贫人口小额贷款贴息申报汇总表.xlsx"]
result = combine_data_split_into_chunks(file_list, word_list)
for chunk in result:
    print(chunk)
    print("-"*100)