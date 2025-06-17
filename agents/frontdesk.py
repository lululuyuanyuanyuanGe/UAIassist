import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, create_assistant_with_files, filter_out_system_messages, detect_and_process_file_paths, upload_file_to_LLM
import uuid
import json
import os
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re

load_dotenv()

# 用于处理用户上传文件
from openai import OpenAI
client = OpenAI(
    api_key = os.environ.get("OPENAI_API_KEY")
)

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

@tool
def upload_file_to_LLM_tool(file_paths: list, provider: str = "openai", purpose: str = "assistants", vector_store_id: str = None):
    """
    通用文件上传工具，将用户提供的文件上传给大模型
    
    Args:
        file_paths: 文件路径列表
        provider: 模型提供商 ("openai", "azure", "anthropic", "local")
        purpose: 文件用途 ("assistants", "fine-tune", "user_data")
        vector_store_id: 可选的向量存储ID，用于OpenAI助手
    
    Returns:
        dict: 包含上传结果的字典，包括file_ids
    """
    # 执行文件上传
    result = upload_file_to_LLM(file_paths, provider, purpose, vector_store_id)
    
    # 提取成功上传的文件ID
    uploaded_file_ids = [file["file_id"] for file in result.get("uploaded_files", [])]
    
    print(f"📁 上传成功的文件ID: {uploaded_file_ids}")
    
    # 返回结果，包含file_ids用于后续状态更新
    result["file_ids"] = uploaded_file_ids
    return result

# 定义前台接待员状态
class FrontdeskState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    table_structure: dict
    table_info: dict
    additional_requirements: dict
    gather_complete: bool
    has_template: bool
    complete_confirm: bool
    uploaded_files: list  # 用户提供的文件路径
    uploaded_files_id: list
    previous_node: str  # Track the previous node before file upload
    failed_uploads: list  # Track files that failed to upload

class CustomFileUploadNode:
    """自定义文件上传节点，处理工具调用和状态更新"""
    
    def __init__(self, tools):
        self.tools = tools
        self.tool_node = ToolNode(tools)
    
    def __call__(self, state: FrontdeskState):
        # 执行工具调用 - 使用正确的invoke方法
        result = self.tool_node.invoke(state)
        
        # 检查工具执行结果，更新uploaded_files_id和failed_uploads
        if "messages" in result:
            for message in result["messages"]:
                if hasattr(message, 'content') and isinstance(message.content, str):
                    try:
                        # 尝试解析工具返回的结果
                        import json
                        if message.content.startswith('{') and ('"file_ids"' in message.content or '"failed_files"' in message.content):
                            tool_result = json.loads(message.content)
                            
                            # 更新成功上传的文件ID
                            if "file_ids" in tool_result:
                                current_file_ids = state.get("uploaded_files_id", [])
                                new_file_ids = tool_result["file_ids"]
                                updated_file_ids = list(set(current_file_ids + new_file_ids))  # 去重
                                result["uploaded_files_id"] = updated_file_ids
                                print(f"📁 状态更新 - 新增文件ID: {new_file_ids}")
                                print(f"📁 状态更新 - 总文件ID: {updated_file_ids}")
                            
                            # 更新失败上传的文件
                            if "failed_files" in tool_result and tool_result["failed_files"]:
                                current_failed = state.get("failed_uploads", [])
                                failed_paths = [f.get("file", "") for f in tool_result["failed_files"]]
                                updated_failed = list(set(current_failed + failed_paths))  # 去重
                                result["failed_uploads"] = updated_failed
                                print(f"📁 状态更新 - 失败文件: {failed_paths}")
                                print(f"📁 状态更新 - 总失败文件: {updated_failed}")
                            
                            break
                    except (json.JSONDecodeError, AttributeError):
                        continue
        
        return result

class FrontDeskAgent:
    """
    基于LangGraph的AI代理系统，用于判断用户是否给出了表格生成模板，并帮助用户汇总表格生成模板
    支持多模态输入（文档、图片等）
    """

    def __init__(self, model_name: str = "gpt-4o", checkpoint_path: str = "checkpoints.db"):
        self.model_name = model_name
        self.llm = ChatOpenAI(model=model_name, temperature=2)
        self.tools = [upload_file_to_LLM_tool]
        self.llm_with_tool = self.llm.bind_tools(self.tools)
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _filter_messages_for_llm(self, messages):
        """过滤消息，确保正确的对话序列，避免OpenAI API错误"""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
        
        filtered = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            
            # 检查消息类型
            if isinstance(msg, (HumanMessage, SystemMessage)):
                filtered.append(msg)
                i += 1
            elif isinstance(msg, AIMessage):
                # 如果AI消息有tool_calls，检查后续是否有对应的tool消息
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    # 查找对应的tool消息
                    tool_call_ids = [tc.get('id') for tc in msg.tool_calls if tc.get('id')]
                    j = i + 1
                    found_tool_responses = []
                    
                    # 收集所有对应的tool消息
                    while j < len(messages) and isinstance(messages[j], ToolMessage):
                        if messages[j].tool_call_id in tool_call_ids:
                            found_tool_responses.append(messages[j])
                        j += 1
                    
                    # 如果找到了完整的tool响应，跳过这个AI消息和tool消息序列
                    # 因为我们不想在LLM调用中包含tool相关的消息
                    if len(found_tool_responses) == len(tool_call_ids):
                        i = j  # 跳过整个tool调用序列
                        continue
                    else:
                        # 如果tool响应不完整，也跳过这个AI消息，避免API错误
                        i += 1
                        continue
                else:
                    # 普通AI消息，直接添加
                    filtered.append(msg)
                    i += 1
            else:
                # 其他类型消息（如ToolMessage）跳过
                i += 1
        
        return filtered

    def _build_graph(self) -> StateGraph:
        """构建生成表格的LangGraph状态图"""

        workflow = StateGraph(FrontdeskState)

        # 创建自定义工具节点
        file_upload_node = CustomFileUploadNode(self.tools)

        # 添加节点
        workflow.add_node("check_template", self._check_template_node)
        workflow.add_node("confirm_template", self._confirm_template_node)
        workflow.add_node("gather_requirements", self._gather_requirements_node)
        workflow.add_node("store_information", self._store_information_node)
        workflow.add_node("collect_input", self._gather_user_input)
        workflow.add_node("collect_template_supplement", self._gather_user_template_supplement)
        workflow.add_node("file_upload_tool", file_upload_node)

        # 入口节点
        workflow.set_entry_point("check_template")

        # 连接节点
        # 检测节点判断用户提供了文件需要上传
        workflow.add_conditional_edges(
            "check_template",
            self._route_after_template_check,
            {
                "has_template": "confirm_template",
                "file_upload": "file_upload_tool",
                "no_template": "gather_requirements"
            }
        )

        # 当模板提供时和用户确认
        workflow.add_conditional_edges(
            "confirm_template",
            self._route_after_template_confirm,
            {
                "complete_confirm": "store_information",
                "incomplete_confirm": "collect_template_supplement",
                "upload_file": "file_upload_tool"
            }
        )

        # collect_template_supplement直接返回确认模板
        workflow.add_edge("collect_template_supplement", "confirm_template")
        
        # collect_input直接返回需求收集  
        workflow.add_edge("collect_input", "gather_requirements")

        # 当模板未提供时
        workflow.add_conditional_edges(
            "gather_requirements",
            self._route_after_gather_requirements,
            {
                "complete": "store_information",
                "continue": "collect_input",
                "upload_file": "file_upload_tool"
            }
        )

        # 文件上传工具处理完后返回到LLM处理节点
        workflow.add_conditional_edges(
            "file_upload_tool",
            self._route_after_file_upload,
            {
                "check_template": "check_template",
                "confirm_template": "confirm_template", 
                "gather_requirements": "gather_requirements"
            }
        )

        workflow.add_edge("store_information", END)
        
        return workflow.compile(checkpointer = self.memory)

    def _check_template_node(self, state: FrontdeskState) -> FrontdeskState:
        """检查用户是否提供了表格生成模板 - 支持多模态输入和智能工具调用"""

        # 获取已上传文件信息和失败文件信息
        uploaded_files_info = ""
        if state.get("uploaded_files_id"):
            uploaded_files_info = f"\n**已上传的文件：**\n已成功上传 {len(state['uploaded_files_id'])} 个文件到系统中，文件ID: {state['uploaded_files_id']}\n"
        
        failed_files_info = ""
        if state.get("failed_uploads"):
            failed_files_info = f"\n**上传失败的文件：**\n以下文件上传失败，请不要重复尝试: {state['failed_uploads']}\n"

        system_prompt = f"""
        你是一个专业的表格模板识别专家，负责准确判断用户是否已经提供了完整的表格生成模板。
        你需要分析用户的文本描述以及他们上传的任何文件（包括图片、文档等）。
        {uploaded_files_info}{failed_files_info}
        **工具使用指南：**
        如果用户输入中包含NEW文件路径（尚未上传且未失败的文件），请使用 upload_file_to_LLM_tool 工具。
        
        文件路径识别规则：
        - Windows路径：d:\\folder\\file.xlsx, C:\\Users\\file.csv
        - Unix路径：/home/user/file.xlsx, ./data/file.csv
        - 相对路径：../data/file.xlsx, data/file.csv
        
        工具参数：
        - file_paths: 提取的文件路径列表，例如 ["d:\\data\\file.xlsx"]
        - provider: "openai"
        - purpose: "assistants"

        **重要：** 
        - 如果文件已经上传（如上面显示的已上传文件），请不要重复上传！
        - 如果文件上传失败（如上面显示的失败文件），请不要重复尝试！

        **判断标准：**
        用户提供了表格模板当且仅当满足以下任一条件：

        1. **结构化描述**：用户清晰、详细地描述了表格的完整结构
        2. **文件模板**：用户提供了包含表格结构的文件（包括已上传的文件）
        3. **具体示例**：用户给出了表格的具体示例

        **输出要求：**
        - 如果用户提供了完整表格模板，回答 [YES]
        - 如果用户未提供完整模板，回答 [NO]
        - 如果需要分析NEW文件，请先调用工具上传文件，然后基于分析结果判断

        **注意事项**
        如果信息不够完整，回答 [NO]
        """
        
        # 过滤消息，移除工具消息
        filtered_messages = self._filter_messages_for_llm(state["messages"])

        # 使用带工具的LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        messages = [SystemMessage(content=system_prompt)] + filtered_messages
        response = llm_with_tools.invoke(messages)

        has_template = "[YES]" in response.content.upper()
        
        return {
            "has_template": has_template,
            "messages": [response]
        }

    def _route_after_template_check(self, state: FrontdeskState) -> str:
        """根据LLM是否调用工具来决定路由"""
        if state.get("messages"):
            latest_message = state["messages"][-1]
            if hasattr(latest_message, 'tool_calls') and latest_message.tool_calls:
                # Set previous node before going to file upload
                state["previous_node"] = "check_template"
                return "file_upload"
        return "has_template" if state["has_template"] else "no_template"

    def _confirm_template_node(self, state: FrontdeskState) -> FrontdeskState:
        """和用户确认模板细节 - 支持智能工具调用"""

        # If complete_confirm is already True, don't override it
        if state.get("complete_confirm", False):
            return {
                "messages": state["messages"],
                "complete_confirm": True
            }

        # 获取已上传文件信息
        uploaded_files_info = ""
        if state.get("uploaded_files_id"):
            uploaded_files_info = f"\n**已上传的文件：**\n已成功上传 {len(state['uploaded_files_id'])} 个文件到系统中，文件ID: {state['uploaded_files_id']}\n"

        system_prompt = f"""你是一个专业的表格模板审核专家，你的任务是主动与用户确认和完善表格模板的详细信息。
        {uploaded_files_info}
        **工具使用指南：**
        如果用户在对话中提到了NEW文件路径、文件名，或者说要上传新文件来补充模板信息，请使用 upload_file_to_LLM_tool 工具。
        工具参数说明：
        - file_paths: 从用户输入中提取的文件路径列表
        - provider: 使用 "openai"
        - purpose: 使用 "assistants"
        
        **重要：** 如果文件已经上传（如上面显示的已上传文件），请不要重复上传！

        **你需要按顺序确认以下信息：**
        1. **表格的用途和目标**：确认表格的具体用途，用来做什么？解决什么问题？
        2. **需要收集的具体信息类型**：确认所有数据字段，是否有遗漏的重要字段？
        3. **表格结构设计**：确认是否需要多级表头？如何分组？层级关系是否合理？
        4. **特殊要求**：确认格式、验证规则、特殊功能等

        **对话策略：**
        - 主动询问，不要被动等待
        - 一次确认1-2个具体问题，避免让用户感到困扰
        - 如果发现任何不确定或不完整的地方，请具体指出并询问用户
        - 根据用户回答给出建议和选项
        - 如果用户回答模糊，追问具体细节
        - 当确认所有信息都清晰完整时，主动总结并标记 [COMPLETE]
        - 如果用户提供新文件来补充信息，请先调用工具上传分析

        **判断完成标准：**
        当你确认了表格用途、所有字段详情、结构组织方式、特殊要求后，应该主动总结信息并在回复末尾加上 [COMPLETE] 标记。

        当模板确认完成后请在回复结尾加入[COMPLETE]
        """

        # 过滤消息，移除工具消息
        filtered_messages = self._filter_messages_for_llm(state["messages"])

        # 确保系统提示词在最前面
        if not filtered_messages or not isinstance(filtered_messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + filtered_messages
        else:
            messages = [SystemMessage(content=system_prompt)] + filtered_messages[1:]

        # 使用带工具的LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        response = llm_with_tools.invoke(messages)
        complete_confirm = "[COMPLETE]" in response.content.upper()

        return{
            "complete_confirm": complete_confirm,
            "messages": [response]
        }
    
    def _route_after_template_confirm(self, state: FrontdeskState) -> str:
        """根据LLM是否调用工具来决定路由"""
        if state.get("messages"):
            latest_message = state["messages"][-1]
            if hasattr(latest_message, 'tool_calls') and latest_message.tool_calls:
                # Set previous node before going to file upload
                state["previous_node"] = "confirm_template"
                return "upload_file"
        
        return "complete_confirm" if state["complete_confirm"] else "incomplete_confirm"
    
    def _gather_user_template_supplement(self, state: FrontdeskState) -> FrontdeskState:
        """收集用户补充信息，来确认模板"""
        user_response = interrupt("请为模板提供补充信息: ")
        return {
            "messages": [HumanMessage(content=user_response)]
        }

    def _gather_requirements_node(self, state: FrontdeskState) -> FrontdeskState:
        """和用户对话确定生成表格的内容，要求等 - 支持多模态输入分析和智能工具调用"""

        # If gather_complete is already True, don't override it
        if state.get("gather_complete", False):
            return {
                "messages": state["messages"],
                "gather_complete": True
            }

        # 获取已上传文件信息
        uploaded_files_info = ""
        if state.get("uploaded_files_id"):
            uploaded_files_info = f"\n**已上传的文件：**\n已成功上传 {len(state['uploaded_files_id'])} 个文件到系统中，文件ID: {state['uploaded_files_id']}\n"

        system_prompt_text = f"""你是一个资深的excel表格设计专家，你的任务是主动引导用户完成表格设计。
        你可以分析用户上传的文件（包括图片、文档、Excel文件等）来更好地理解他们的需求。
        {uploaded_files_info}
        **工具使用指南：**
        如果用户在对话中提到了NEW文件路径、文件名，或者说要上传新文件来帮助设计表格，请使用 upload_file_to_LLM_tool 工具。
        工具参数说明：
        - file_paths: 从用户输入中提取的文件路径列表
        - provider: 使用 "openai"
        - purpose: 使用 "assistants"
        
        **重要：** 如果文件已经上传（如上面显示的已上传文件），请不要重复上传！

        **你需要按顺序收集以下信息：**
        1. 表格的用途和目标（用来做什么？解决什么问题？）
        2. 需要收集的具体信息类型（哪些数据字段？），可以发散思维适当追问用户补充额外数据
        3. 表格结构设计（是否需要多级表头？如何分组？）
        4. 特殊要求（格式、验证规则、特殊功能等）

        **多模态分析能力：**
        - 如果用户上传了图片，尝试分析图片中的表格结构或相关信息
        - 如果用户上传了文档，考虑文档中可能包含的表格需求或模板
        - 如果用户上传了Excel/CSV文件，分析其结构作为参考

        **对话策略：**
        - 主动询问，不要被动等待
        - 一次问1或2个具体问题
        - 根据用户回答和上传的文件给出建议和选项
        - 如果用户回答模糊，追问具体细节
        - 如果用户上传了相关文件，主动提及并询问是否基于文件内容设计
        - 当收集到足够信息设计完整表格时，主动总结并标记 [COMPLETE]
        - 如果用户提供文件，请先调用工具上传分析，然后基于分析结果继续对话

        **判断完成标准：**
        当你明确了表格用途、主要字段、结构组织方式后，应该主动总结信息并在回复末尾加上 [COMPLETE] 标记。

        **示例完成总结格式：**
        "好的，根据我们的讨论和您提供的文件，我已经收集到足够的信息来设计这个表格：
        - 用途：[总结用途]
        - 主要字段：[列出字段]
        - 结构：[描述表头组织]
        现在我可以为您生成详细的表格结构了。[COMPLETE]"
        """

        # 过滤消息，移除工具消息
        filtered_messages = self._filter_messages_for_llm(state["messages"])

        # 确保系统提示词在最前面
        if not filtered_messages or not isinstance(filtered_messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt_text)] + filtered_messages
        else:
            messages = [SystemMessage(content=system_prompt_text)] + filtered_messages[1:]

        # 使用带工具的LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        response = llm_with_tools.invoke(messages)
        gather_complete = "[COMPLETE]" in response.content

        return {
            "messages": [response],
            "gather_complete": gather_complete    
        }

    def _route_after_gather_requirements(self, state: FrontdeskState) -> str:
        """根据LLM是否调用工具来决定路由"""
        if state.get("messages"):
            latest_message = state["messages"][-1]
            if hasattr(latest_message, 'tool_calls') and latest_message.tool_calls:
                # Set previous node before going to file upload
                state["previous_node"] = "gather_requirements"
                return "upload_file"
        
        return "complete" if state["gather_complete"] else "continue"

    def _gather_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """用户和agent对话确认信息，或提供额外信息用于智能体收集表格信息"""
        user_response = interrupt("请输入您的回复: ")
        return {
            "messages": [HumanMessage(content=user_response)]
        }


    def _process_html(file_path: Path, state: FrontdeskState) -> FrontdeskState:
        """This is the node that let LLM process the cleaned Html and add short description in each cell"""
        system_promtp = """"""

        

    

    
    def _store_information_node(self, state: FrontdeskState) -> FrontdeskState:
        """将收集到的信息结构化储存"""

        # Check if we have enough conversation context
        conversation_length = len([msg for msg in state["messages"] if isinstance(msg, (HumanMessage, AIMessage))])
        
        if conversation_length < 2:
            # 没有收集到足够信息，根据用户初始输入创立基础表格
            initial_input = state["messages"][0].content if state["messages"] else "未知需求"
            
            basic_template = {
                "table_info": {
                    "purpose": f"基于用户输入创建的表格：{initial_input}",
                    "description": "用户提供的基本需求，需要进一步完善",
                    "data_sources": ["用户输入"],
                    "target_users": ["用户"],
                    "frequency": "待确定"
                },
                "table_structure": {
                    "has_multi_level": False,
                    "multi_level_headers": [
                        {
                            "name": "待定字段1",
                            "description": "需要进一步确定的表头",
                            "data_type": "text",
                            "required": True,
                            "example": "示例数据"
                        }
                    ]
                },
                "additional_requirements": {
                    "formatting": ["待确定"],
                    "validation_rules": ["待确定"],
                    "special_features": ["待确定"]
                }
            }
            
            print("⚠️ 对话信息不足，生成基础模板")
            return {
                **state,
                "table_info": basic_template["table_info"],
                "table_structure": basic_template["table_structure"],
                "additional_requirements": basic_template["additional_requirements"],
                "gather_complete": True
            }

        system_prompt ="""你是一个专业的表格结构分析专家。请根据对话历史记录，或用户提供的表格模板，
        提取并结构化表格相关信息。

        **重要提醒：**
        如果对话信息不足，请基于现有信息生成一个合理的基础结构，不要拒绝生成。

        **任务要求：**
        1. 仔细分析对话内容，提取表格的用途、内容、数据需求和结构信息
        2. 输出必须是有效的JSON格式
        3. 严格按照以下数据结构输出

        **表格结构说明：**
        - 对于多级表头，使用嵌套的数组和字典结构
        - 标题表头（有子级的）只包含 name 和 children 字段
        - 数据表头（叶子节点）包含 name, description, data_type, required, example 字段
        - 支持任意层级的嵌套结构

        **输出格式：**
        请直接输出JSON内容，不要使用markdown代码块包装，不要添加任何解释文字：
        {
        "table_info": {
            "purpose": "表格的具体用途和目标",
            "description": "表格内容的详细描述",
            "data_sources": ["数据来源1", "数据来源2"],
            "target_users": ["目标用户群体"],
            "frequency": "使用频率（如：每日/每周/每月）"
        },
        "table_structure": {
            "has_multi_level": true,
            "multi_level_headers": [
            {
                "name": "第一级标题表头名称",
                "children": [
                {
                    "name": "第二级标题表头名称",
                    "children": [
                    {
                        "name": "数据字段名称",
                        "description": "数据字段说明",
                        "data_type": "数据类型（text/number/date/boolean）",
                        "required": true,
                        "example": "示例数据"
                    }
                    ]
                },
                {
                    "name": "直接数据字段名称",
                    "description": "数据字段说明",
                    "data_type": "数据类型（text/number/date/boolean）",
                    "required": false,
                    "example": "示例数据"
                }
                ]
            }
            ]
        },
        "additional_requirements": {
            "formatting": ["格式要求"],
            "validation_rules": ["数据验证规则"],
            "special_features": ["特殊功能需求"]
        }
        }

        **结构示例说明：**
        - 如果表头是标题性质（有子表头），只需要 "name" 和 "children"
        - 如果表头是数据字段（叶子节点），需要完整的字段信息
        - children 是一个数组，可以包含更多的标题表头或数据字段
        - 支持2级、3级或更多级的嵌套结构
        """
        print("正在生成表格模板......")
        system_message = SystemMessage(content=system_prompt)
        filtered_messages = self._filter_messages_for_llm(state["messages"])
        messages = [system_message] + filtered_messages
        response = self.llm.invoke(messages)

        try:
            # Clean the response content to handle markdown-wrapped JSON
            response_content = response.content.strip()
            
            # 移除markdown输出
            if response_content.startswith('```json'):
                response_content = response_content[7:]  # Remove ```json
            if response_content.startswith('```'):
                response_content = response_content[3:]   # Remove ```
            if response_content.endswith('```'):
                response_content = response_content[:-3]  # Remove trailing ```
            
            response_content = response_content.strip()
            
            # Parse the JSON response
            structured_output = json.loads(response_content)
            
            # Extract components
            table_info = structured_output["table_info"]
            table_structure = structured_output["table_structure"]
            additional_requirements = structured_output["additional_requirements"]

            # 创建完整的数据
            complete_data = {
                "session_id": state.get("session_id", "unknown"),
                "timestamp": datetime.now().isoformat(),
                "table_info": table_info,
                "table_structure": table_structure,
                "additional_requirements": additional_requirements,
                "conversation_messages": [
                    {
                        "type": msg.__class__.__name__,
                        "content": msg.content
                    } for msg in state["messages"] if hasattr(msg, 'content')
                ]
            }

            print("✅ JSON解析成功，表格模板生成完成")

            # 创建文件夹用于存储生成的表格模板
            output_dir = "table_template"
            os.makedirs(output_dir, exist_ok=True)

            # 生成文件名称
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = state.get("session_id", "default")
            filename = f"table_template_{session_id}_{timestamp}.json"

            # 将表格模板储存到这个JSON文件
            file_path = os.path.join(output_dir, filename)
            with open(file_path, 'w', encoding = 'utf-8') as f:
                json.dump(complete_data, f, ensure_ascii=False, indent=2)
            print(f"✅ 表格模板已保存到: {filename}")
        
            # Return updated state
            return {
                **state,
                "table_info": table_info,
                "table_structure": table_structure,
                "additional_requirements": additional_requirements,
                "gather_complete": True
            }
        
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析失败: {e}")
            print(f"原始响应: {response.content}")
            print(f"清理后响应: {response_content if 'response_content' in locals() else 'N/A'}")
            
            # Fallback: create a basic template from the conversation
            print("🔄 使用对话内容生成基础模板")
            fallback_template = {
                "table_info": {
                    "purpose": "根据对话内容生成的表格",
                    "description": "基于用户需求的基础表格结构",
                    "data_sources": ["用户对话"],
                    "target_users": ["用户"],
                    "frequency": "待确定"
                },
                "table_structure": {
                    "has_multi_level": False,
                    "multi_level_headers": [
                        {
                            "name": "基础字段",
                            "description": "根据对话推断的字段",
                            "data_type": "text",
                            "required": True,
                            "example": "示例"
                        }
                    ]
                },
                "additional_requirements": {
                    "formatting": ["标准格式"],
                    "validation_rules": ["基本验证"],
                    "special_features": ["无特殊要求"]
                }
            }
            
            return {
                **state,
                "table_info": fallback_template["table_info"],
                "table_structure": fallback_template["table_structure"],
                "additional_requirements": fallback_template["additional_requirements"],
                "gather_complete": True
            }
        except KeyError as e:
            print(f"❌ JSON结构错误: {e}")
            print(f"可用键: {list(structured_output.keys()) if 'structured_output' in locals() else 'N/A'}")
            
            return {
                **state,
                "gather_complete": False
            }

    def _create_initial_state(self, user_input: str, session_id: str = "default") -> FrontdeskState:
        """创建Langgraph最初状态 - 支持多模态输入和自动文件路径检测"""
        
        # 检测并处理用户输入中的文件路径
        detected_files = detect_and_process_file_paths(user_input)
        
        return {
            "messages": [HumanMessage(content=user_input)],
            "session_id": session_id,
            "table_structure": {},
            "table_info": {},
            "additional_requirements": {},
            "gather_complete": False,
            "has_template": False,
            "complete_confirm": False,
            "uploaded_files": detected_files,  # 使用检测到的文件路径
            "uploaded_files_id": [],  # 初始化为空列表
            "failed_uploads": [],  # 初始化失败上传列表
            "previous_node": "check_template"  # 初始状态下，如果有文件上传，应该回到check_template
        }
    
    def _route_after_file_upload(self, state: FrontdeskState) -> str:
        """文件上传工具处理完成后的路由决策 - 返回到LLM处理节点"""
        previous_node = state.get("previous_node", "check_template")
        
        print(f"📁 文件上传完成，来自节点: {previous_node}")
        
        # 文件上传后返回到LLM处理节点，让LLM分析文件内容
        if previous_node == "confirm_template":
            print("📍 从confirm_template上传文件完成，返回confirm_template处理")
            return "confirm_template"
        elif previous_node == "gather_requirements":
            print("📍 从gather_requirements上传文件完成，返回gather_requirements处理")
            return "gather_requirements"
        else:
            # 其他情况（如check_template等）正常返回原节点
            print(f"📍 返回到原节点: {previous_node}")
            return previous_node
    
    def run_front_desk_agent(self, user_input: str, session_id = "1") -> None: # session_id默认为1
        """执行前台智能体"""
        initial_state = self._create_initial_state(user_input, session_id)
        config = {"configurable": {"thread_id": session_id}}

        print(f"🤖 正在处理用户输入: {user_input}")
        print("=" * 50)

        current_input = initial_state
        
        while True:
            try:
                has_interrupt = False
                for chunk in self.graph.stream(current_input, config = config, stream_mode = "updates"):
                    for node_name, node_output in chunk.items():
                        print(f"\n📍 Node: {node_name}")
                        print("-" * 30)
                        
                        # 检查是否有interrupt
                        if '__interrupt__' in chunk:
                            has_interrupt = True
                            interrupt_value = chunk['__interrupt__'][0].value
                            print(f"\n💬 智能体: {interrupt_value}")
                            user_response = input("👤 请输入您的回复: ")
                            
                            # 设置下一次循环的输入
                            current_input = Command(resume=user_response)
                            break
                        
                        if isinstance(node_output, dict):
                            if "messages" in node_output and node_output["messages"]:
                                latest_message = node_output["messages"][-1]
                                if hasattr(latest_message, 'content') and not isinstance(latest_message, HumanMessage):
                                    print(f"💬 智能体回复: {latest_message.content}")
                            
                            for key, value in node_output.items():
                                if key != "messages" and value:
                                    print(f"📊 {key}: {value}")
                        print("-" * 30)
                
                # 如果没有interrupt，说明流程完成
                if not has_interrupt:
                    break
                    
            except Exception as e:
                print(f"❌ 执行错误: {e}")
                raise e
        
        print("\n✅ 表格模板生成完成！")

if __name__ == "__main__":

    #创建智能体
    frontdeskagent = FrontDeskAgent()

    save_graph_visualization(frontdeskagent.graph)

    # user_input = input("🤖 你好我是一个智能填表助手，请告诉我你想填什么表格: \n")
    # frontdeskagent.run_front_desk_agent(user_input)