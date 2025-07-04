import sys
from pathlib import Path
import json

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated, Union
from datetime import datetime

from utilities.modelRelated import invoke_model, invoke_model_with_tools
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content, read_txt_file


from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv


from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

# import other agents
from agents.processUserInput import ProcessUserInputAgent


# def extract_table_headers_by_LLM(html_content):
#     system_prompt = f"""你将接收到一个由 HTML 表达的 Excel 表格源码。请从中提取完整的多级表头结构，并以 Markdown 表格格式输出。

# 要求：
# - 表头可能包含多级嵌套结构，你必须完整保留所有表头层级；
# - 各级标题之间的列合并、对应关系必须准确呈现；
# - 不要只返回最底层表头；
# - 返回结果仅包含表头，不包含数据；
# - 输出为标准 Markdown 表格格式，用多行表示层级结构。
# - 输出不需要包含任何解释，不要加入```markdown```标签
# """




#     response = invoke_model(model_name="Tongyi-Zhiwen/QwenLong-L1-32B", messages=[SystemMessage(content=system_prompt), HumanMessage(content=html_content)])
#     return response


def extract_table_headers_by_LLM(json_content):
    system_prompt = f"""
# Role & Context
你是一位专业的表格结构解析专家，擅长将复杂的 JSON 层次结构转换为标准的 Markdown 表格格式。

# Task Description
将提供的 JSON 数据转换为 Markdown 表格头部，保持原有的层次结构和合并关系。

# Input Format
JSON 数据结构说明：
- 键名：表头字段名
- 值类型：对象表示父节点，字符串表示叶子节点

# Output Requirements
1. **仅输出 Markdown 表格头部**（不包含数据行）
2. **使用标准 Markdown 表格语法**
3. **保持层次结构**：多级表头需要正确显示层级关系
4. **处理合并单元格**：父节点需要跨越其所有子节点列数

# Example
Input:
```json
{{"基本信息": {{"姓名": "", "年龄": ""}}, "联系方式": {{"电话": "", "邮箱": ""}}, "备注": ""}}
```

Output:
```markdown
|   基本信息  |  联系方式   | 备注 |
|---------------------------------
| 姓名 | 年龄 | 电话 | 邮箱 | 备注 |
|------|------|------|------|------|
```

# Processing Steps
1. 解析 JSON 结构识别层级关系
2. 计算每个父节点需要跨越的列数
3. 构建多行表头结构
4. 生成标准 Markdown 格式

# Output Constraints
- 仅输出结果，无解释或注释
- 严格遵循 Markdown 表格语法
- 保持 UTF-8 编码正确显示中文
- 不要添加多余的"|"符号，另外每一个表头需要对于子表头居中

请根据以上要求处理提供的 JSON 数据。
"""





    response = invoke_model(model_name="Tongyi-Zhiwen/QwenLong-L1-32B", messages=[SystemMessage(content=system_prompt), HumanMessage(content=json_content)])
    return response

with open(r"D:\asianInfo\ExcelAssist\agents\data.json", "r", encoding="utf-8") as f:
    json_content = json.load(f)  # 注意这里用的是 json.load，不是 json.loads
table = json_content["表格"]["农保名册.txt"]["summary"]
print("模型生成的md格式：")
response = extract_table_headers_by_LLM(table)
print(response)


def build_header_matrix(data):
    """Builds a matrix of header cells with alignment based on nested dict"""
    matrix = []

    def get_leaf_count(node):
        if not isinstance(node, dict) or not node:
            return 1
        return sum(get_leaf_count(child) for child in node.values())

    def fill_matrix(node, depth, matrix):
        if len(matrix) <= depth:
            matrix.append([])
        for key, child in node.items():
            span = get_leaf_count(child)
            matrix[depth].append((key, span))
            if isinstance(child, dict) and child:
                fill_matrix(child, depth + 1, matrix)

    # Assume the top-level has one main entry
    top_label = list(data.keys())[0]
    root = data[top_label]

    # First row: full-span header
    matrix.append([(top_label, get_leaf_count(root))])
    fill_matrix(root, 1, matrix)

    return matrix


def matrix_to_markdown(matrix):
    """Converts the header matrix to aligned markdown string"""
    output = []
    for row in matrix:
        line = []
        for text, span in row:
            line.append(f"{text}")
            for _ in range(span - 1):
                line.append("")  # empty cells to simulate colspan
        output.append("| " + " | ".join(line) + " |")
    return "\n".join(output)


