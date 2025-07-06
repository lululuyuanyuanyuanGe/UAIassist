import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, TypedDict, Annotated
from utilities.file_process import fetch_related_files_content, extract_file_from_recall
from utilities.modelRelated import invoke_model, invoke_model_with_tools

import json
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
    related_files_str: str
    related_files: list[str]
    headers_mapping: dict[str, str]
    template_structure: str
    headers_mapping_: dict[any, any]
    file_content: str

class RecallFilesAgent:
    def __init__(self):
        self.graph = self._build_graph()

    tools = [request_user_clarification]

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
        # 只读取相关村的文件
        with open(r'agents\data.json', 'r', encoding = 'utf-8') as f:
            file_content = f.read()
        for key, value in json.loads(file_content).items():
            if key in template_structure:
                file_content = value
        print("模板结构: \n" + template_structure)
        print("数据库文件内容: \n" + file_content)

        return {
            "messages": [],
            "related_files": [],
            "headers_mapping": {},
            "template_structure": template_structure,
            "headers_mapping_": {},
            "file_content": file_content
        }
    

    def _recall_relative_files(self, state: RecallFilesState) -> RecallFilesState:
        """根据要生成的表格模板，从向量库中召回相关文件"""
        print("\n🔍 开始执行: _recall_relative_files")
        print("=" * 50)
        
        previous_AI_summary = ""
        for message in state["messages"]:
            previous_AI_summary += message.content

        print("=========历史对话记录==========")
        print(previous_AI_summary)
        print("=========历史对话记录==========")
        
        system_prompt = f"""
你是一位专业的文件分析专家，擅长从文件摘要中筛选出最适合用于填写模板表格的数据文件和辅助参考文件。

【你的任务】
根据我提供的表格模板结构、任务背景和文件摘要信息，从中挑选出可能用于填写模板的相关文件。请特别注意，**每一次文件召回后必须调用工具 `request_user_clarification` 与用户确认选择是否合适**，不得直接返回文件列表或跳过确认。

【执行标准】
1. 分析模板的结构字段，判断填写所需的数据和可能的计算或解释依据；
2. 从文件摘要中初步筛选 3~5 个高度相关的文件，可能包括：
   - 含有原始数据字段的 Excel 或 CSV 文件；
   - 含有字段说明、政策依据、计算规则的 Word 或 PDF 文件；
3. 无论是否已有历史召回记录或用户反馈，**本轮都必须调用工具与用户确认筛选结果**；
4. 如果用户反馈不满意，应根据其意见重新筛选并再次确认；
5. 一旦用户确认，后续节点将使用该确认结果继续流程；
6. 最终文件列表请以**严格的 JSON 数组格式**输出，内容示例如下：
   ["基础信息表.xlsx", "补贴政策说明.docx"]

【格式要求】
- 仅输出 JSON 数组格式；
- 不允许出现多余文字或 markdown 包裹（如 ```json）；
- 不允许自行与用户对话，必须使用 `request_user_clarification` 工具发起确认；
- 所有返回值仅包含文件名，不含路径或摘要内容；

【输入上下文】
表格模板结构：
{state["template_structure"]}

文件摘要列表：
{state["file_content"]}

用户历史行为摘要：
{previous_AI_summary}
"""

        response = invoke_model_with_tools(model_name = "deepseek-ai/DeepSeek-V3", 
                                           messages = [SystemMessage(content = system_prompt)], 
                                           tools=self.tools,
                                           temperature = 0.3)

        # Extract response content properly
        if isinstance(response, str):
            response_content = response
            AI_message = AIMessage(content=response)
            print(f"📥 LLM响应(字符串): {response_content}")
        else:
            response_content = response.content if hasattr(response, 'content') else str(response)
            AI_message = response
            print(f"📥 LLM响应(对象): {response_content}")
        
        # Always print the response content for debugging
        print("💬 智能体回复内容:")
        print(response_content)
        
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



    def _determine_the_mapping_of_headers(self, state: RecallFilesState) -> RecallFilesState:
        """确认模板表头和数据文件表头的映射关系"""
        print("\n🔍 开始执行: _determine_the_mapping_of_headers")
        print("=" * 50)
        
        # Extract related files from response
        related_files = extract_file_from_recall(state["related_files_str"])
        print(f"📋 需要处理的相关文件: {related_files}")
        
        # 获取所有相关文件的内容
        print("📖 正在读取相关文件内容...")
        files_content = fetch_related_files_content(related_files)
        
        # 构建用于分析表头映射的提示
        files_content_str = ""
        for filename, content in files_content.items():
            if content:  # 只包含成功读取的文件
                files_content_str += f"\n\n=== {filename} ===\n{content[:1000]}..."  # 限制内容长度避免过长
        
        print(f"📝 构建了 {len(files_content)} 个文件的内容摘要")
        
        system_prompt = f"""
        你是一位专业的表格分析专家，任务是分析模板表格与多个数据文件之间的表头映射关系。

### 输入信息如下：

- **模板表格结构**：
  ```json
  {state["template_structure"]}
  ```

- **相关数据文件内容**：
  ```text
  {files_content_str}
  ```

---

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
   - `推理规则: ...`（表示该字段通过逻辑推导得出）


---
请返回最终的模板表格结构，确保准确反映字段来源与生成逻辑，格式与上面一致，便于后续程序解析和处理。
        """
        
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
            "related_files": related_files
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
            
            print("\n🎉 RecallFilesAgent 执行完成！")
            print("=" * 60)
            print("📊 最终结果:")
            print(f"- 召回文件数量: {len(final_state.get('related_files', []))}")
            print(f"- 相关文件: {final_state.get('related_files', [])}")
            print(f"- 表头映射已生成: {'是' if final_state.get('headers_mapping') else '否'}")
            
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


