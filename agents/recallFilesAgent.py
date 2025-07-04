import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, TypedDict, Annotated
from utilities.file_process import fetch_related_files_content
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
        
        # Extract the response content if it's a message object
        if hasattr(response, 'content'):
            return response.content
        elif isinstance(response, str):
            return response
        else:
            return str(response)
            
    except Exception as e:
        print(f"❌ 用户澄清请求失败: {e}")
        return f"无法获取用户回复: {str(e)}"




class RecallFilesState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    related_files: list[str]
    headers_mapping: dict[str, str]
    template_structure: str
    headers_mapping_: dict[any, any]

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

    def _create_initial_state(self) -> RecallFilesState:
        return {
            "messages": [],
            "related_files": [],
            "headers_mapping": {},
            "template_structure": "",
            "headers_mapping_": {}
        }
    

    def _recall_relative_files(self, state: RecallFilesState) -> RecallFilesState:
        """根据要生成的表格模板，从向量库中召回相关文件"""
        print("\n🔍 开始执行: _recall_relative_files")
        print("=" * 50)
        
        with open(r'agents\data.json', 'r', encoding = 'utf-8') as f:
            file_content = f.read()
        
        system_prompt = f"""
你是一位专业的文件分析专家，擅长根据表格模板内容，从用户提供的文件摘要中识别与其高度相关的参考文件。

【任务背景】
用户提供了一个表格模板，其内容包括表头结构、摘要信息、文件名等；
同时还提供了一份文件摘要列表，其中每条记录包含一个文件的完整文件名及其简要说明。

你的任务是：
1. 根据模板表格的结构和内容（特别是表头结构和摘要信息）；
2. 从提供的文件摘要中筛选出所有可能用于填写该模板的相关文件；
3. 返回这些相关文件的完整文件名组成的数组。

【重要要求】
- **如果是第一次召回相关文件，必须调用工具向用户确认这些文件是否合适**，确认后才可继续后续流程；
- 如果不是第一次（用户已确认），则可直接返回最终文件列表；
- 当和用户确认后，请确保返回结果严格为一个字符串数组，内容为文件的完整文件名，不包含其他文字、标点或注释。例如：
  ["2024年党员数据.xlsx", "补贴规则说明.docx"]

【文件摘要列表】：
{file_content}
"""


        if state["messages"]:
            previous_AI_summary = state["messages"][-1].content
        else:
            previous_AI_summary = ""

        print("📤 正在调用LLM进行文件召回...")

        user_input = "表格模板内容：" + state["template_structure"] + "\n文件摘要列表："

        response = invoke_model_with_tools(model_name = "Pro/deepseek-ai/DeepSeek-V3", messages = [SystemMessage(content = system_prompt), HumanMessage(content = user_input), HumanMessage(content = previous_AI_summary)], tools=self.tools)

        # 创建AIMessage时需要保留tool_calls信息
        # if hasattr(response, 'tool_calls') and response.tool_calls:
        #     # 如果有工具调用，创建包含tool_calls的AIMessage
        #     ai_message = AIMessage(content=response.content or "", tool_calls=response.tool_calls)
        #     print("🔧 检测到工具调用")
        #     return {
        #         "messages": [ai_message],
        #         "related_files": ""
        #     
        # else:
        # 如果没有工具调用，只包含内容
        AI_message = AIMessage(content=response) if isinstance(response, str) else response
        response = response if isinstance(response, str) else response.content
        related_files = self._extract_file_from_recall(response)
        print("✅ _recall_relative_files 执行完成")
        print("=" * 50)
        return {
            "messages": [AI_message],
            "related_files": related_files
        }

    def _extract_file_from_recall(self, response: str) -> str:
        # Parse the response to extract the file list
        try:
            # Try to parse as JSON array
            related_files = json.loads(response.content if hasattr(response, 'content') else response)
            if not isinstance(related_files, list):
                # If not a list, try to extract from string
                # Look for patterns like ["file1", "file2"] or ['file1', 'file2']
                match = re.search(r'\[.*?\]', response)
                if match:
                    related_files = json.loads(match.group())
                else:
                    # Fallback: split by lines and filter
                    related_files = [line.strip().strip('"\'') for line in response.split('\n') if line.strip() and not line.strip().startswith('#')]
        except:
            # Fallback parsing if JSON fails
            related_files = [line.strip().strip('"\'') for line in response.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        print(f"📁 解析出的相关文件: {related_files}")
        return related_files

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
        
        # 读取文件内容，只读取表头即可
        related_files = state["related_files"]
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
            "headers_mapping": response
        }
    
    def run_recall_files_agent(self, template_structure: str, session_id: str = "1") -> Dict:
        """运行召回文件代理，使用invoke方法而不是stream"""
        print("\n🚀 开始运行 RecallFilesAgent")
        print("=" * 60)

        config = {"configurable": {"thread_id": session_id}}
        initial_state = self._create_initial_state()
        
        # Set the template structure if provided
        if template_structure:
            initial_state["template_structure"] = template_structure
            print(f"📋 已设置模板结构: {len(template_structure)} 字符")
        elif hasattr(self, 'template_structure'):
            initial_state["template_structure"] = self.template_structure
            print(f"📋 使用预设模板结构: {len(self.template_structure)} 字符")
        else:
            print("⚠️ Warning: No template structure provided")
            
        print("🔄 正在执行图形工作流...")
        
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
            "基本信息": ["姓名", "性别", "年龄", "身份证号"],
            "联系方式": ["电话", "地址"],
            "补贴信息": ["补贴类型", "补贴金额", "申请日期"]
        },
        "表格总结": "这是一个老党员补贴申报表格，用于记录党员基本信息和补贴申请详情"
    }
    """
    
    agent.run_recall_files_agent(template_structure=sample_template_structure)


