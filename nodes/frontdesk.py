from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, create_assistant_with_files, filter_out_system_messages, detect_and_process_file_paths
import uuid
import json
import os
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
def upload_file_to_LLM():
    """用于将用户输入的文件上传给大模型"""
    pass

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
    uploaded_files: list  # Add support for tracking uploaded files
    previous_node: str  # Track the previous node before file upload

class FrontDeskAgent:
    """
    基于LangGraph的AI代理系统，用于判断用户是否给出了表格生成模板，并帮助用户汇总表格生成模板
    支持多模态输入（文档、图片等）
    """

    def __init__(self, model_name: str = "gpt-4o", checkpoint_path: str = "checkpoints.db"):
        self.model_name = model_name
        self.llm = ChatOpenAI(model=model_name, temperature=0.1)
        self.tools = [upload_file_to_LLM]
        self.llm_with_tool = self.llm.bind_tools(self.tools)
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建生成表格的LangGraph状态图"""

        workflow = StateGraph(FrontdeskState)

        # 创建工具节点
        file_upload_node = ToolNode(self.tools)

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
                "has_file_upload": "file_upload_tool",
                "no_template": "gather_requirements"
            }
        )

        # 当模板提供时和用户确认
        workflow.add_conditional_edges(
            "confirm_template",
            self._route_after_template_confirm,
            {
                "complete_confirm": "store_information",
                "incomplete_confirm": "collect_template_supplement"
            }
        )

        # collect_template_supplement时用户可能上传文件
        workflow.add_conditional_edges(
            "collect_template_supplement",
            self._route_after_collect_template_supplement,
            {
                "continue_confirm": "confirm_template",
                "upload_file": "file_upload_tool"
            }
        )

        # collect_input时用户可能上传文件
        workflow.add_conditional_edges(
            "collect_input",
            self._route_after_collect_input,
            {
                "continue_gather": "gather_requirements",
                "upload_file": "file_upload_tool"
            }
        )
        
        # 当模板未提供时
        workflow.add_conditional_edges(
            "gather_requirements",
            self._route_after_gather_requirements,
            {
                "complete": "store_information",
                "continue": "collect_input"
            }
        )

        # 文件上传工具处理完后的路由
        workflow.add_conditional_edges(
            "file_upload_tool",
            self._route_after_file_upload,
            {
                "check_template": "check_template",
                "confirm_template": "confirm_template", 
                "gather_requirements": "gather_requirements",
                "collect_template_supplement": "collect_template_supplement",
                "collect_input": "collect_input"
            }
        )

        workflow.add_edge("store_information", END)
        
        return workflow.compile(checkpointer = self.memory)

    def _check_template_node(self, state: FrontdeskState) -> FrontdeskState:
        """检查用户是否提供了表格生成模板 - 支持多模态输入"""

        system_prompt = """
        你是一个专业的表格模板识别专家，负责准确判断用户是否已经提供了完整的表格生成模板。
        你需要分析用户的文本描述以及他们上传的任何文件（包括图片、文档等）。

        **判断标准：**
        用户提供了表格模板当且仅当满足以下任一条件：

        1. **结构化描述**：用户清晰、详细地描述了表格的完整结构，包括：
           - 明确的表头名称和层级关系
           - 每个字段的具体含义和数据类型
           - 表格的整体布局和组织方式
           
        2. **文件模板**：用户提供了包含表格结构的文件，如：
           - Excel文件(.xlsx, .xls) - 包含具体的表头和数据结构
           - CSV模板文件 - 有明确的列名和格式
           - PDF文档中的表格样式 - 显示完整的表格布局
           - 图片中的表格截图 - 能清晰看到表头和结构
           
        3. **具体示例**：用户给出了表格的具体示例，包含：
           - 完整的表头结构
           - 示例数据行
           - 格式要求和规范

        **特别注意文件类型：**
        - 如果用户上传了Excel文件(.xlsx, .xls)，请仔细分析其中的表头结构和数据格式
        - 如果用户上传了图片文件，分析图片中是否包含表格结构
        - 如果用户上传了文档文件，考虑其可能包含的表格模板信息

        **不符合条件的情况：**
        - 仅描述表格用途或目的
        - 只提到需要哪些信息类别，但未具体化表头
        - 模糊的需求描述
        - 询问如何制作表格
        - 上传的文件与表格设计无关

        **输出要求：**
        - 如果用户提供了符合上述标准的完整表格模板，请回答 [YES]
        - 如果用户未提供完整模板或描述不够具体，请回答 [NO]
        - 如果有任何不确定的地方，倾向于回答 [NO]

        **分析过程：**
        请仔细分析用户输入和上传的文件，考虑是否包含足够的结构化信息来直接生成表格。
        如果用户上传了Excel文件，请使用pandas等工具分析文件结构，查看表头、数据类型、行数等信息。

        **注意事项**
        如果你认为用户当前的信息不够完整，或者你需要一些补充也要回答 [NO]
        """
        
        # 获取用户输入消息
        user_message = state["messages"][-1] if state["messages"] else HumanMessage(content="")
        file_paths = state.get("uploaded_files", [])

        # 检查是否上传了文件
        if file_paths:
            print(f"🔍 正在使用Assistants API分析 {len(file_paths)} 个文件...")
            try:
                # 使用新的Assistants API方法
                result = create_assistant_with_files(
                    client=client,
                    file_paths=file_paths,
                    user_input=user_message.content,
                    system_prompt=system_prompt
                )
                
                response_content = result["response"]
                print("✅ Assistants API文件分析完成")
                
                # 将分析结果转换为LangChain消息格式
                analysis_message = AIMessage(content=response_content)
                state["messages"].append(analysis_message)
                
            except Exception as e:
                print(f"❌ Assistants API分析失败: {e}")
                print("🔄 回退到文本分析模式")
                # 回退到文本分析
                messages = [SystemMessage(content=system_prompt), user_message]
                response = self.llm.invoke(messages)
                response_content = response.content
        else:
            # 构建正确的消息列表
            messages = [SystemMessage(content=system_prompt), user_message]
            response = self.llm.invoke(messages)
            response_content = response.content

        has_template = "[YES]" in response_content.upper()
        
        return {
            "has_template": has_template,
            "messages": [AIMessage(content=response_content)]
        }

    def _route_after_template_check(self, state: FrontdeskState) -> str:
        """用户提供外部文件时返回工具节点路由，没有外部文件则正常判断"""
        if state.get("uploaded_files"):
            # Set previous node before going to file upload
            state["previous_node"] = "check_template"
            return "has_file_upload"
        return "has_template" if state["has_template"] else "no_template"
    
    def _route_after_collect_template_supplement(self, state: FrontdeskState) -> str:
        """模板补充收集后的路由决策 - 检测用户是否提供了新文件"""
        # 检测最新用户消息中是否包含文件路径
        if state.get("messages"):
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                # 检测并处理用户输入中的文件路径
                detected_files = detect_and_process_file_paths(latest_message.content)
                if detected_files:
                    # 更新状态中的上传文件列表
                    current_files = state.get("uploaded_files", [])
                    state["uploaded_files"] = current_files + detected_files
                    # Set previous node before going to file upload
                    state["previous_node"] = "collect_template_supplement"
                    return "upload_file"
        
        return "continue_confirm"

    def _route_after_collect_input(self, state: FrontdeskState) -> str:
        """用户输入收集后的路由决策 - 检测用户是否提供了新文件"""
        # 检测最新用户消息中是否包含文件路径
        if state.get("messages"):
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                # 检测并处理用户输入中的文件路径
                detected_files = detect_and_process_file_paths(latest_message.content)
                if detected_files:
                    # 更新状态中的上传文件列表
                    current_files = state.get("uploaded_files", [])
                    state["uploaded_files"] = current_files + detected_files
                    # Set previous node before going to file upload
                    state["previous_node"] = "collect_input"
                    return "upload_file"
        
        return "continue_gather"

    def _confirm_template_node(self, state: FrontdeskState) -> FrontdeskState:
        """和用户确认模板细节"""

        # If complete_confirm is already True, don't override it
        if state.get("complete_confirm", False):
            return {
                "messages": state["messages"],
                "complete_confirm": True
            }

        system_prompt = """你是一个专业的表格模板审核专家，你的任务是主动与用户确认和完善表格模板的详细信息。

        **你需要按顺序确认以下信息：**
        1. **表格的用途和目标**：确认表格的具体用途，用来做什么？解决什么问题？
        2. **需要收集的具体信息类型**：确认所有数据字段，是否有遗漏的重要字段？
        3. **表格结构设计**：确认是否需要多级表头？如何分组？层级关系是否合理？
        4. **特殊要求**：确认格式、验证规则、特殊功能等

        **检查重点：**
        - **表头完整性**：检查表头是否清晰明确，是否有歧义或模糊的表述
        - **数据类型明确性**：确认每个字段的数据类型是否明确（文本、数字、日期等）
        - **必填字段标识**：确认哪些字段是必填的，哪些是可选的
        - **数据格式规范**：检查是否需要特定的数据格式要求
        - **表格结构逻辑**：验证表格的层级结构是否合理
        - **业务逻辑一致性**：确保表格设计符合实际业务需求

        **对话策略：**
        - 主动询问，不要被动等待
        - 一次确认1-2个具体问题，避免让用户感到困扰
        - 如果发现任何不确定或不完整的地方，请具体指出并询问用户
        - 根据用户回答给出建议和选项
        - 如果用户回答模糊，追问具体细节
        - 当确认所有信息都清晰完整时，主动总结并标记 [COMPLETE]

        **判断完成标准：**
        当你确认了表格用途、所有字段详情、结构组织方式、特殊要求后，应该主动总结信息并在回复末尾加上 [COMPLETE] 标记。

        **示例确认格式：**
        "好的，我已经仔细审核了您的表格模板，现在让我总结确认的信息：
        - 表格用途：[用途说明]
        - 主要字段：[字段列表]
        - 结构设计：[描述表头组织]
        - 特殊要求：[要求说明]
        所有信息都已确认清楚，现在可以开始生成表格了。[COMPLETE]"

        **示例补充询问格式：**
        "我注意到您的模板中有几个地方需要进一步确认：
        1. [具体问题1]
        2. [具体问题2]
        请您提供更多细节，以便我为您生成更准确的表格。"

        当模板确认完成后请在回复结尾加入[COMPLETE]
        """

        messages = state["messages"].copy()

        # 确保系统提示词在最前面
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages

        response = self.llm.invoke(messages)
        complete_confirm = "[COMPLETE]" in response.content.upper()

        return{
            "complete_confirm": complete_confirm,
            "messages": [response]
        }
    
    # confirm template node's conditional check
    def _route_after_template_confirm(self, state: FrontdeskState) -> str:
        """根据是否完成格式校验路由到相应节点"""
        return "complete_confirm" if state["complete_confirm"] else "incomplete_confirm"
    
    def _gather_user_template_supplement(self, state: FrontdeskState) -> FrontdeskState:
        """收集用户补充信息，来确认模板"""
        user_response = interrupt("请为模板提供补充信息: ")
        return {
            "messages": [HumanMessage(content=user_response)]
        }

    def _gather_requirements_node(self, state: FrontdeskState) -> FrontdeskState:
        """和用户对话确定生成表格的内容，要求等 - 支持多模态输入分析"""

        # If gather_complete is already True, don't override it
        if state.get("gather_complete", False):
            return {
                "messages": state["messages"],
                "gather_complete": True
            }

        system_prompt_text = """你是一个资深的excel表格设计专家，你的任务是主动引导用户完成表格设计。
        你可以分析用户上传的文件（包括图片、文档、Excel文件等）来更好地理解他们的需求。

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

        **判断完成标准：**
        当你明确了表格用途、主要字段、结构组织方式后，应该主动总结信息并在回复末尾加上 [COMPLETE] 标记。

        **示例完成总结格式：**
        "好的，根据我们的讨论和您提供的文件，我已经收集到足够的信息来设计这个表格：
        - 用途：[总结用途]
        - 主要字段：[列出字段]
        - 结构：[描述表头组织]
        现在我可以为您生成详细的表格结构了。[COMPLETE]"
        """

        messages = state["messages"].copy()

        # 确保系统提示词在最前面
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt_text)] + messages

        response = self.llm.invoke(messages)
        gather_complete = "[COMPLETE]" in response.content

        return {
            "messages": [response],
            "gather_complete": gather_complete    
        }

    def _route_after_gather_requirements(self, state: FrontdeskState) -> str:
        """根据需求收集完成状态路由到下一个节点"""
        return "complete" if state["gather_complete"] else "continue"

    def _gather_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """用户和agent对话确认信息，或提供额外信息用于智能体收集表格信息"""
        user_response = interrupt("请输入您的回复: ")
        return {
            "messages": [HumanMessage(content=user_response)]
        }

    
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
        filtered_messages = filter_out_system_messages(state["messages"])
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
            "previous_node": "check_template"  # 初始状态下，如果有文件上传，应该回到check_template
        }
    
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

    def _route_after_file_upload(self, state: FrontdeskState) -> str:
        """文件上传工具处理完成后的路由决策 - 返回到之前的节点"""
        # 返回到文件上传前的节点
        previous_node = state.get("previous_node", "check_template")
        
        print(f"📁 文件上传完成，返回到节点: {previous_node}")
        
        # 根据之前的节点返回相应的路由值
        node_routing_map = {
            "check_template": "check_template",
            "collect_template_supplement": "collect_template_supplement", 
            "collect_input": "collect_input",
            "confirm_template": "confirm_template",
            "gather_requirements": "gather_requirements"
        }
        
        return node_routing_map.get(previous_node, "check_template")

if __name__ == "__main__":

    #创建智能体
    frontdeskagent = FrontDeskAgent()

    save_graph_visualization(frontdeskagent.graph)

    # user_input = input("🤖 你好我是一个智能填表助手，请告诉我你想填什么表格: \n")
    # frontdeskagent.run_front_desk_agent(user_input)