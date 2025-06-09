from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
import uuid
import json

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# 定义前台接待员状态
class FrontdeskState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    table_structure: dict
    table_info: dict
    additonal_requirements: dict
    gather_complete: bool
    has_template: bool
    user_input: str

class FrontDeskAgent:
    """
    基于LangGraph的AI代理系统，用于判断用户是否给出了表格生成模板，并帮助用户汇总表格生成模板
    """

    def __init__(self, model_name: str = "gpt-4o", checkpoint_path: str = "checkpoints.db"):
        self.model_name = model_name
        self.llm = ChatOpenAI(model=model_name, temperature=0.1)
        self.memory = MemorySaver()
        self.tools = []
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建生成表格的LangGraph状态图"""

        workflow = StateGraph(FrontdeskState)

        # 添加节点
        workflow.add_node("check_template", self._check_template_node)
        workflow.add_node("gather_requirements", self._gather_requirements_node)
        workflow.add_node("collect_input", self._gather_user_input)
        workflow.add_node("store_information", self._store_information_node)

        # 入口节点
        workflow.set_entry_point("check_template")

        # 连接节点
        workflow.add_conditional_edges(
            "check_template",
            self._route_after_template_check,
            {
                "has_template": "store_information",
                "no_template": "gather_requirements"
            }
        )

        workflow.add_conditional_edges(
            "gather_requirements",
            self._route_after_requirements,
            {
                "complete": "store_information",
                "continue": "collect_input"
            }
        )

        workflow.add_edge("collect_input", "gather_requirements")
        workflow.add_edge("store_information", END)
        
        return workflow.compile(checkpointer = self.memory)
        
    def _check_template_node(self, state: FrontdeskState) -> FrontdeskState:
        """检查用户是否提供了表格生成模板"""

        system_prompt = """
        你作为一个表格生成智能体，第一步你需要判断用户是否提供了表格的模板，
        判断规则如下：
        1.用户清晰的描述出了表格的结构，每一级表头标题
        2.用户提供了表格各式的文件，可能是excel文件，pdf等里面清晰的定义了表格结构
        如果用户提供了表格模板则回答[YES]，反之回答[NO]，如果你有任何不清楚的地方也需要回答[NO]
        """
        system_message = SystemMessage(content=system_prompt)

        latest_message = [system_message] + [state["messages"][-1]] if state["messages"] else [system_message]

        response = self.llm.invoke(latest_message)

        has_template = "[YES]" in response.content.upper()

        return {
            "has_template": has_template,
            "messages": [AIMessage(content = f"是否提供模板：{"是" if has_template else "否"}")]
        }

    def _route_after_template_check(self, state: FrontdeskState) -> str:
        """根据模板检查结果路由到下一个节点"""
        return "has_template" if state["has_template"] else "no_template"

    def _gather_requirements_node(self, state: FrontdeskState) -> FrontdeskState:
        """和用户对话确定生成表格的内容，要求等"""

        # If gather_complete is already True, don't override it
        if state.get("gather_complete", False):
            return {
                "messages": state["messages"],
                "gather_complete": True
            }

        system_prompt_text = """你作为一个资深的excel表格设计专家，现在需要通过和用户对话的方式了解用户需求，并通过发散四维
         一步一步帮用户设计出excel表格，你需要弄清楚以下问题

         -这个表格是用来干什么的
         -需要收集哪些信息
         -表格都涉及到哪些表头，是否存在多级表头
         -需要用到哪些数据

         请一次只问1-2个问题，让对话自然进行

        你也可以给出用户一些建议并询问用户是否采纳。
        当你认为信息收集完整时，请在回复最后加上 [COMPLETE] 标记，并总结表格信息。
        """

        messages = state["messages"]

        # 判断是否已提供系统提示词
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content = system_prompt_text)] + messages

        # Add the current user input if available
        if state.get("user_input"):
            messages.append(HumanMessage(content = state["user_input"]))

        response = self.llm.invoke(messages)

        gather_complete = "[COMPLETE]" in response.content

        return {
            "messages": [response],
            "gather_complete": gather_complete    
        }

    def _route_after_requirements(self, state: FrontdeskState) -> str:
        """根据需求收集完成状态路由到下一个节点"""
        return "complete" if state["gather_complete"] else "continue"

    def _gather_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """用户和agent对话确认信息，或提供额外信息用于智能体收集表格信息"""

        try:
            user_input = input("用户：")
            return {
                "user_input": user_input
            }
        except EOFError:
            # Handle non-interactive environments
            print("⚠️  非交互式环境，无法获取用户输入")
            return {
                "user_input": "",
                "gather_complete": True  # Force completion to avoid infinite loop
            }
    
    def _route_after_gather(self, state: FrontdeskState) -> str:
        """根据"gather_complete"的值返回下一个节点"""

        gather_complete = state["gather_complete"]

        if gather_complete:
            return "ready"

        return "collect_input"
    
    def _store_information_node(self, state: FrontdeskState) -> FrontdeskState:
        """将收集到的信息结构化储存"""

        system_prompt ="""你是一个专业的表格结构分析专家。请根据对话历史记录，或用户提供的表格模板，
        提取并结构化表格相关信息。

        **任务要求：**
        1. 仔细分析对话内容，提取表格的用途、内容、数据需求和结构信息
        2. 输出必须是有效的JSON格式
        3. 严格按照以下数据结构输出

        **输出格式：**
        ```json
        {
        "table_info": {
            "purpose": "表格的具体用途和目标",
            "description": "表格内容的详细描述",
            "data_sources": ["数据来源1", "数据来源2"],
            "target_users": ["目标用户群体"],
            "frequency": "使用频率（如：每日/每周/每月）"
        },
        "table_structure": {
            "has_multi_level": false,
            "headers": [
            {
                "name": "表头名称",
                "description": "表头说明",
                "data_type": "数据类型（text/number/date/boolean）",
                "required": true,
                "example": "示例数据"
            }
            ],
            "multi_level_headers": {
            "level_1": [
                {
                "name": "一级表头名称",
                "description": "一级表头说明",
                "children": [
                    {
                    "name": "二级表头名称",
                    "description": "二级表头说明",
                    "data_type": "数据类型",
                    "required": true,
                    "example": "示例数据"
                    }
                ]
                }
            ]
            }
        },
        "additional_requirements": {
            "formatting": ["格式要求"],
            "validation_rules": ["数据验证规则"],
            "special_features": ["特殊功能需求"]
        }
        }
        """

        system_message = SystemMessage(content=system_prompt)
        messages = [system_message] + state["messages"]
        response = self.llm.invoke(messages)

        try:
            # Parse the JSON response
            structured_output = json.loads(response.content)
            
            # Extract components
            table_info = structured_output["table_info"]
            table_structure = structured_output["table_structure"]
            additional_requirements = structured_output["additional_requirements"]
            
            # Return updated state
            return {
                **state,
                "table_info": table_info,
                "table_structure": table_structure,
                "additional_requirements": additional_requirements,
                "gather_complete": True
            }
        
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Raw response: {response.content}")
            
            # Return state with error indication
            return {
                **state,
                "gather_complete": False
            }
        except KeyError as e:
            print(f"Missing key in JSON response: {e}")
            print(f"Available keys: {list(structured_output.keys()) if 'structured_output' in locals() else 'N/A'}")
            
            return {
                **state,
                "gather_complete": False
            }

    def _create_initial_state(self, user_input: str, session_id: str = "default") -> FrontdeskState:
        """创建Langgraph最初状态"""
        return {
            "messages": [HumanMessage(content=user_input)],
            "session_id": session_id,
            "table_structure": {},
            "table_info": {},
            "gather_complete": False,
            "has_template": False,
            "user_input": user_input,
            "additonal_requirements": {}
        }
    
    def run_front_desk_agent(self, user_input: str, session_id = "1") -> None: # session_id默认为1
        """执行前台智能体"""
        initial_state = self._create_initial_state(user_input, session_id)
        config = {"configurable": {"thread_id": session_id}}

        print(f"🤖 Processing user input: {user_input}")
        print("=" * 50)

        for chunk in self.graph.stream(initial_state, config=config, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    print(f"\n📍 Node: {node_name}")
                    print("-" * 30)
                    
                    if isinstance(node_output, dict):
                        if "messages" in node_output and node_output["messages"]:
                            latest_message = node_output["messages"][-1]
                            if hasattr(latest_message, 'content'):
                                print(f"💬 Response: {latest_message.content}")
                        
                        for key, value in node_output.items():
                            if key != "messages" and value:
                                print(f"📊 {key}: {value}")
                    
                    print("-" * 30)

                
if __name__ == "__main__":

    #创建智能体
    frontdeskagent = FrontDeskAgent()

    user_input = input("请输入你想生成的表格：")
    frontdeskagent.run_front_desk_agent(user_input)




        






        
