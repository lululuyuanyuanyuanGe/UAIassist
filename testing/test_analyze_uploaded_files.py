from utilities.file_process import *
from utilities.message_process import *

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from pathlib import Path

user_input_files = input("请输入用户输入的文件路径: ")
result = detect_and_process_file_paths(user_input_files)
print(result)

file_path = convert_excel2html(result[0], "test_excel")
print(file_path)

# file_path = retrieve_file_content(result, "1")
# print(file_path)

# for file in file_path:
#     analysis_content = Path(file).read_text(encoding='utf-8')

#     model = ChatOpenAI(model="gpt-4o", temperature=0.0)



#     system_prompt = f"""你是一个表格生成智能体，需要分析用户上传的文件内容并进行分类。共有四种类型：

#                     1. **模板类型 (template)**: 空白表格模板，只有表头没有具体数据
#                     2. **补充表格 (supplement-表格)**: 已填写的完整表格，用于补充数据库
#                     3. **补充文档 (supplement-文档)**: 包含重要信息的文本文件，如法律条文、政策信息等
#                     4. **无关文件 (irrelevant)**: 与表格填写无关的文件

#                     注意：所有文件已转换为txt格式，表格以HTML代码形式呈现，请根据内容而非文件名或后缀判断。

#                     当前分析文件:
#                     文件名: {Path(file).name}
#                     文件路径: {file}
#                     文件内容:
#                     {analysis_content}

#                     请严格按照以下JSON格式回复，只返回这一个文件的分类结果（不要添加任何其他文字）：
#                     {{
#                         "classification": "template" | "supplement-表格" | "supplement-文档" | "irrelevant"
#                     }}"""

#     response = model.invoke([SystemMessage(content=system_prompt)])
#     print(response.content)