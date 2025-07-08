import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, TypedDict, Annotated
from utilities.file_process import fetch_related_files_content, extract_file_from_recall
from utilities.modelRelated import invoke_model, invoke_model_with_tools

import json
import tempfile
import hashlib
import time
# Create an interactive chatbox using gradio
import re

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool

from agents.processUserInput import ProcessUserInputAgent

# Define tool as standalone function (not class method)
@tool
def request_user_clarification(question: str) -> str:
    """
    这个函数用于向用户请求澄清，例如询问用户召回的文件正确不正确，是否需要重新召回，
    或者补充召回，也可询问用户影射关系是否正确，或者有些映射实在无法结局时可向用户询问

    参数：question: 你的问题
    返回：用户回答
    """
    try:
        print("request_user_clarification 被调用=========================================\n", question)
        process_user_input_agent = ProcessUserInputAgent()
        response = process_user_input_agent.run_process_user_input_agent(previous_AI_messages=AIMessage(content=question))
        
        # Extract the summary message from response
        summary_message = response[0]
        print("request_user_clarification 调用模型的输入: \n" + summary_message)
        summary_message = json.loads(summary_message)
        print("request_user_clarification 调用模型的输入类型: \n" + str(type(summary_message)))
        summary_message = summary_message["summary"]
        print("request_user_clarification 调用模型的输出: \n" + summary_message)
        return summary_message

    except Exception as e:
        print(f"❌ 用户澄清请求失败: {e}")
        return f"无法获取用户回复: {str(e)}"


class RecallFilesState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    chat_history: list[str]
    related_files_str: str
    related_files: list[str]
    classified_files: dict[str, list[str]]
    headers_mapping: dict[str, str]
    template_structure: str
    headers_mapping_: dict[any, any]
    file_content: str # 把文件摘要里面的相关村子的文件全部提取出来，并按照表格，模板进行分类
    document_files_content: str # 把文件摘要里面的相关村子的文件全部提取出来，并按照表格，模板进行分类


class RecallFilesAgent:
    def __init__(self):
        self.tools = [request_user_clarification]  # Reference the standalone function
        self.graph = self._build_graph()
        self.location: str # 村子名字
        self.files_under_location: str # 村子下的文件
        self.related_files_classified: dict

    def _build_graph(self):
        graph = StateGraph(RecallFilesState)
        graph.add_node("recall_relative_files", self._recall_relative_files)
        graph.add_node("determine_the_mapping_of_headers", self._determine_the_mapping_of_headers)
        graph.add_node("request_user_clarification", ToolNode(self.tools))

        graph.add_edge(START, "recall_relative_files")
        graph.add_conditional_edges("recall_relative_files", self._route_after_recall_relative_files)
        graph.add_edge("request_user_clarification", "recall_relative_files")
        graph.add_edge("determine_the_mapping_of_headers", END)
        return graph.compile(checkpointer = MemorySaver())

    def _create_initial_state(self, template_structure: str) -> RecallFilesState:

        def extract_summary_for_each_file(file_content: dict) -> str:
            """提取文件内容的摘要信息"""
            summary = ""
            
            # 提取表格summary
            if "表格" in file_content and file_content["表格"]:
                summary += "表格: \n"
                tables = file_content["表格"]
                for table_name in tables:
                    if isinstance(tables[table_name], dict) and "summary" in tables[table_name]:
                        summary += f"  {tables[table_name]['summary']}\n"
                    else:
                        summary += f"  {table_name}: [无摘要信息]\n"
            
            # 提取文档summary
            if "文档" in file_content and file_content["文档"]:
                summary += "\n文档: \n"
                documents = file_content["文档"]
                for doc_name in documents:
                    if isinstance(documents[doc_name], dict) and "summary" in documents[doc_name]:
                        summary += f"  {documents[doc_name]['summary']}\n"
                    else:
                        summary += f"  {doc_name}: [无摘要信息]\n"
            
            return summary
        
        # 只读取相关村的文件
        with open(r'agents\data.json', 'r', encoding = 'utf-8') as f:
            file_content = f.read()
        #     print(template_structure)
        # for key, value in json.loads(file_content).items():
        #     print("key: \n", key)
        #     if key in template_structure:
        #         file_content = value
        #         self.location = key
        file_content = json.loads(file_content)
        self.location = "燕云村"
        self.files_under_location = file_content["燕云村"]
        file_content = extract_summary_for_each_file(self.files_under_location)
        print("===========================")
        print(self.files_under_location)
        

        return {
            "messages": [],
            "chat_history": [],
            "related_files": [],
            "classified_files": {"表格": [], "文档": []},  # Add default classified files
            "headers_mapping": {},
            "template_structure": template_structure,
            "headers_mapping_": {},
            "file_content": file_content,
            "document_files_content": ""
        }
    

    def _recall_relative_files(self, state: RecallFilesState) -> RecallFilesState:
        """根据要生成的表格模板，从向量库中召回相关文件"""
        print("\n🔍 开始执行: _recall_relative_files")
        print("=" * 50)
        if state["messages"]:   
            previous_AI_message = state["messages"][-1]
            previous_AI_message_content = previous_AI_message.content
            state["chat_history"].append(previous_AI_message_content)
        chat_history = "\n".join(state["chat_history"])

        print("=========历史对话记录==========")
        print(chat_history)
        print("=========历史对话记录==========")
        
        system_prompt = f"""
你是一位专业的文件分析专家，擅长从文件摘要中筛选出最适合用于填写模板表格的数据文件和辅助参考文件。

【你的任务】
根据我提供的表格模板结构、任务背景和文件摘要信息，从中挑选出可能用于填写模板的相关文件，表格或者文档文件。

【执行流程】
你必须严格按照以下流程执行：

1. **分析阶段**：
   - 分析模板的结构字段，判断填写所需的数据和可能的计算或解释依据
   - 从文件摘要中初步筛选 3~5 个高度相关的文件，可能包括：
     * 含有原始数据字段的 Excel 或 CSV 文件
     * 含有字段说明、政策依据、计算规则的 Word 或 PDF 文件

2. **确认阶段**：
   - **必须调用工具 `request_user_clarification` 与用户确认筛选结果**
   - 在工具调用中，向用户展示你筛选的文件列表，并询问是否合适
   - 等待用户反馈后，根据用户意见调整文件选择，如果用户给出了正面的回答，则直接返回文件列表，不要重复调用工具

3. **输出阶段**：
   - 只有在用户确认后，才能输出最终的文件列表
   - 输出格式必须是严格的 JSON 数组，例如：["基础信息表.xlsx", "补贴政策说明.docx"]，不要包裹在```json中，直接返回json格式即可
   - 不要返回任何其他内容，不要返回任何其他内容，不要返回任何其他内容

【重要说明】
- 根据历史对话记录，判断是否需要调用工具，当得到用户确认后，不需要再调用工具
- 不允许跳过用户确认直接返回文件列表，但也不要重复调用工具
- 不允许自行与用户对话，必须使用 `request_user_clarification` 工具
- 文件名不含路径或摘要内容，仅包含文件名

【严格遵守】
- 不要返回任何其他内容，不要返回任何其他内容，不要返回任何其他内容
- 返回的必须是文件数组，且必须与文件摘要中的文件名一致，不要将序列号包含在内

表格模板结构：
{state["template_structure"]}

文件摘要列表：
{state["file_content"]}

历史对话记录：
{chat_history}

请开始执行第一步：分析模板结构并初步筛选文件，然后调用工具与用户确认。
"""
        print("Garbage fed to our poor LLM: \n", system_prompt)
        response = invoke_model_with_tools(model_name = "gpt-4o", 
                                           messages = [SystemMessage(content = system_prompt)], 
                                           tools=self.tools,
                                           temperature = 0.2)
        response_content = ""
        print("Garbage returned from our LLM: \n", response)
        # invoke_maodel_with_tools永远不会返回str
        if hasattr(response, 'tool_calls') and response.tool_calls:
            question = response.tool_calls[0]['args']['question']
            print("问题：")
            print(question)
            state["chat_history"].append(question)
            AI_message = response

        else:
            response_content = response.content
            AI_message = AIMessage(content=response_content)
        
        
        
        # Check for tool calls
        has_tool_calls = hasattr(response, 'tool_calls') and response.tool_calls
        if has_tool_calls:
            print("🔧 检测到工具调用")
        else:
            print("ℹ️ 无工具调用")
        
        print("✅ _recall_relative_files 执行完成")
        print("=" * 50)
        return {
            "messages": [AI_message],
            "related_files_str": response_content
        }


    def _route_after_recall_relative_files(self, state: RecallFilesState) -> str:
        """This node will route the agent to the next node based on the user's input"""
        print("\n🔀 开始执行: _route_after_recall_relative_files")
        print("=" * 50)

        latest_message = state["messages"][-1]
        if hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
            print("🔧 检测到工具调用，路由到 request_user_clarification")
            print("✅ _route_after_recall_relative_files 执行完成")
            print("=" * 50)
            return "request_user_clarification"
        else:
            print("✅ 无工具调用，路由到 determine_the_mapping_of_headers")
            print("✅ _route_after_recall_relative_files 执行完成")
            print("=" * 50)
            return "determine_the_mapping_of_headers"

    def _classify_files_by_type(self, file_list: list[str], file_content:str ) -> dict[str, list[str]]:
        """Classify the files as 表格 or 文档"""

        classified_files = {
            "表格": [],
            "文档": []
        }

        for file in file_list:
            if file in file_content["文档"]:
                classified_files["文档"].append(file)
            elif file in file_content["表格"]:
                classified_files["表格"].append(file)
        print("Classified files: \n", classified_files)
        return classified_files
        

    def _determine_the_mapping_of_headers(self, state: RecallFilesState) -> RecallFilesState:
        """确认模板表头和数据文件表头的映射关系"""
        print("\n🔍 开始执行: _determine_the_mapping_of_headers")
        print("=" * 50)
        
        
        # Extract related files from response
        related_files = extract_file_from_recall(state["related_files_str"])
        print(f"📋 需要处理的相关文件: {related_files}")
        classified_files = self._classify_files_by_type(related_files, self.files_under_location)
        print("dEBUGBUGBBUBUGB", classified_files)
        
        # 获取所有相关文件的内容
        print("📖 正在读取相关文件内容...")
        files_content = fetch_related_files_content(classified_files)

        # 获取文档内容：
        print("classified_files有什么: \n", classified_files)
        document_files_content = ""
        for file in classified_files["文档"]:
            document_files_content += self.files_under_location["文档"][file]["summary"] + "\n"
            print("document_files_content: \n", document_files_content)
        
        # 构建用于分析表头映射的提示
        table_files_content_str = ""
        for filename, content in files_content.items():
            if content:  # 只包含成功读取的文件
                table_files_content_str += f"\n\n=== {filename} ===\n{content[:1000]}..."  # 限制内容长度避免过长

        files_content_str = table_files_content_str + "\n\n" + document_files_content
        print(f"📝 构建了 {len(files_content)} 个文件的内容摘要")

        
        system_prompt = f"""
        你是一位专业的表格分析专家，任务是分析模板表格与多个数据文件之间的表头映射关系。

### 输入信息如下：

- **模板表格结构**：
  {state["template_structure"]}

- **相关数据文件内容**：
  {files_content_str}

### 任务要求：

请逐一对比模板表格中的每一个表头，分析其在数据文件中对应的来源字段。你需要完成以下几项工作：

1. **建立表头映射关系**：  
   在模板表格中注明每个表头对应的数据来源——包括来源文件名和具体表头名称。

2. **处理缺失映射的字段**：  
   对于模板中找不到直接对应字段的表头，请尝试基于已有数据进行推理或推导。例如：
   - 利用已有字段进行计算（如"总计"可通过加总其他字段获得）；
   - 根据政策文件、说明文档等补充信息进行判断；
   - 你需要把详细完整的表格填写规则写出来，例如具体补贴数字等，不要遗漏
   - 若涉及特定筛选条件（如"仅男性"、"特定年龄段"、"某地区"等），请根据用户需求进行逻辑筛选并填写。

3. **输出格式要求**：  
   返回结果应保持与原模板表格结构一致，但每个表头需扩展为以下形式之一：
   - `来源文件名: 数据字段名`（表示该字段来自数据文件）
   - `推理规则: ...`告诉模型该字段需要通过什么逻辑推导出来，必须把详细的规则，或者计算公式写出来，不要遗漏
   - 不要将返回结果包裹在```json中，直接返回json格式即可


---
请返回最终的模板表格结构，确保准确反映字段来源与生成逻辑，格式与上面一致，便于后续程序解析和处理。
        """
        print("确认表头映射提示词：\n", system_prompt)
        print("📤 正在调用LLM进行表头映射分析...")
        response = invoke_model(model_name="Pro/deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
        print("📥 LLM映射分析完成")
        print("💬 智能体回复:")
        print(response)
        print("✅ _determine_the_mapping_of_headers 执行完成")
        print("=" * 50)
        
        return {
            "messages": [AIMessage(content=response)],
            "headers_mapping": response,
            "related_files": related_files,
            "classified_files": classified_files,  # Store classified files in state
            "document_files_content": document_files_content
        }
    
    def run_recall_files_agent(self, template_structure: str, session_id: str = "1") -> Dict:
        """运行召回文件代理，使用invoke方法而不是stream"""
        print("\n🚀 开始运行 RecallFilesAgent")
        print("=" * 60)

        config = {"configurable": {"thread_id": session_id}}
        initial_state = self._create_initial_state(template_structure)
        
        try:
            # Use invoke instead of stream
            final_state = self.graph.invoke(initial_state, config=config)

            # 提取对应的原始xls文件
            def extract_original_xls_file(files_under_location: dict[str, dict[str, str]], related_files: list[str]) -> list[str]:
                """Extract the original xls table file from the related files"""
                table_file = files_under_location["表格"]
                extract_original_xls_file = []
                for file in related_files:
                    if file in table_file:
                        extract_original_xls_file.append(table_file[file]["original_file_path"])
                return extract_original_xls_file
                    
            
            original_xls_files = extract_original_xls_file(self.files_under_location, final_state.get('related_files', []))
            print("original_xls_files有这些: \n", original_xls_files)
            
            print("\n🎉 RecallFilesAgent 执行完成！")
            print("=" * 60)
            print("📊 最终结果:")
            print(f"- 召回文件数量: {len(final_state.get('related_files', []))}")
            print(f"- 相关文件: {final_state.get('related_files', [])}")
            print(f"- 表头映射已生成: {'是' if final_state.get('headers_mapping') else '否'}")
            print(f"- 转换的Excel文件数量: {len(original_xls_files)}")
            print(f"- 转换的Excel文件: {original_xls_files}")
            
            # Add converted Excel files to the final state
            final_state["original_xls_files"] = original_xls_files
            
            return final_state
            
        except Exception as e:
            print(f"❌ 执行过程中发生错误: {e}")
            return initial_state


if __name__ == "__main__":
    agent = RecallFilesAgent()
    
    # Example template structure for testing
    sample_template_structure = """
    {
        "表格结构": {
        "重庆市巴南区享受生活补贴老党员登记表": {
            "基本信息": [
                "序号",
                "姓名",
                "性别",
                "民族",
                "身份证号码",
                "出生时间",
                "所在党支部",
                "成为正式党员时间",
                "党龄（年）",
                "生活补贴标准（元／月）",
                "备注"
            ]
        }
            },
    "表格总结": "该表格用于重庆市巴南区燕云村党委登记享受生活补贴的老党员信息，包含党员个人身份信息、党龄、补贴标准等核心字段，适用于基层党组织对老党员补贴发放的统计管理。" 
    }
    """
    
    agent.run_recall_files_agent(template_structure=sample_template_structure)


