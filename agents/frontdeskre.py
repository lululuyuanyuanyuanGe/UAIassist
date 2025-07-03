import sys
from pathlib import Path
import json

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated, Union
from datetime import datetime

from utilities.modelRelated import invoke_model, invoke_model_with_tools
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content


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

load_dotenv()

def append_strings(left: list[str], right: Union[list[str], str]) -> list[str]:
    """Custom reducer to append strings to a list"""
    if isinstance(right, list):
        return left + right
    else:
        return left + [right]
    

@tool
def _collect_user_input(session_id: str, previous_AI_messages: Union[BaseMessage, List[Dict[str, Any]]]) -> list[str]:
    """这是一个用来收集用户输入的工具，你需要调用这个工具来收集用户输入
    参数：
        session_id: 当前会话ID
        previous_AI_messages: 之前的AI消息
    返回：
        str: 总结后的用户输入信息
    """

    print(f"🔄 开始收集用户输入，当前会话ID: {session_id}")
    
    # Create an instance of the ProcessUserInputAgent
    process_user_input_agent = ProcessUserInputAgent()
    print("testtest111111")
    
    # Handle both BaseMessage (manual calls) and List[Dict] (LLM calls)
    if isinstance(previous_AI_messages, list):
        # LLM tool call - convert dictionaries to BaseMessage
        converted_messages = []
        for msg_dict in previous_AI_messages:
            if isinstance(msg_dict, dict):
                if msg_dict.get('type') == 'ai':
                    converted_messages.append(AIMessage(content=msg_dict.get('content', '')))
                else:
                    converted_messages.append(HumanMessage(content=msg_dict.get('content', '')))
        last_message = converted_messages[-1] if converted_messages else AIMessage(content="")
    else:
        # Manual call - use BaseMessage directly (your intentional design)
        last_message = previous_AI_messages
    
    summary_messages = process_user_input_agent.run_process_user_input_agent(session_id = session_id, previous_AI_messages = last_message)

    print("testtest")
    
    # Extract the final result
    try:
        print(f"🔄 提取最终结果，summary_message类型: {type(summary_messages)}")
        return summary_messages
            
    except Exception as e:
        print(f"❌ 提取结果时出错: {type(e).__name__}: {e}")
        return f"提取结果时出错: {e}"
    

class FrontdeskState(TypedDict):
    chat_history: Annotated[list[str], append_strings]
    messages: Annotated[list[BaseMessage], add_messages]
    table_structure: str
    previous_node: str # Track the previous node
    session_id: str
    template_file_path: str
    table_summary: str


class FrontdeskAgent:
    """
    用于处理用户上传的模板，若未提供模板，和用户沟通确定表格结构
    """



    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.tools = [_collect_user_input]
        self.graph = self._build_graph()




    def _build_graph(self):
        """This function will build the graph of the frontdesk agent"""

        graph = StateGraph(FrontdeskState)

        graph.add_node("entry", self._entry_node)
        graph.add_node("collect_user_input", ToolNode(self.tools))
        graph.add_node("initial_collect_user_input", self._initial_collect_user_input)
        graph.add_node("complex_template_handle", self._complex_template_analysis)
        graph.add_node("simple_template_handle", self._simple_template_analysis)
        graph.add_node("chat_with_user_to_determine_template", self._chat_with_user_to_determine_template)

        graph.add_edge(START, "entry")
        graph.add_edge("entry", "initial_collect_user_input")
        graph.add_conditional_edges("initial_collect_user_input", self._route_after_initial_collect_user_input)
        graph.add_conditional_edges("collect_user_input", self._route_after_collect_user_input)
        graph.add_conditional_edges("chat_with_user_to_determine_template", self._route_after_chat_with_user_to_determine_template)
        graph.add_conditional_edges("simple_template_handle", self._route_after_simple_template_analysis)

        
        # Compile the graph to make it executable with stream() method
        # You can add checkpointer if needed: graph.compile(checkpointer=MemorySaver())
        return graph.compile()



    def _create_initial_state(self, session_id: str = "1") -> FrontdeskState:
        """This function will create the initial state of the frontdesk agent"""
        return {
            "chat_history": [],
            "messages": [],
            "messages_s": [],
            "table_structure": "",
            "session_id": session_id,
            "previous_node": ""
        }


    def _entry_node(self, state: FrontdeskState) -> FrontdeskState:
        """This is the starting node of our frontdesk agent"""
        # Enrich this later, it should include a short description of the agent's ability and how to use it
        welcome_message = "你好，我是一个表格处理助手！"
        print(welcome_message)
        return {
            "messages": [AIMessage(content=welcome_message)],
            "previous_node": "chat_with_user_to_determine_template"
        }
    

    def _initial_collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """调用ProcessUserInputAgent来收集用户输入"""
        session_id = state["session_id"]
        previous_AI_messages = state["messages"][-1]
        processUserInputAgent = ProcessUserInputAgent()
        summary_message = processUserInputAgent.run_process_user_input_agent(session_id = session_id, previous_AI_messages = previous_AI_messages)
        print("原始返回信息：", summary_message)
        
        # Handle the case where summary_message might be None
        if summary_message is None or len(summary_message) < 2:
            error_msg = "用户输入处理失败，请重新输入"
            print(f"❌ {error_msg}")
            return {
                "messages": [AIMessage(content=error_msg)],
                "template_file_path": ""
            }
            
        print("返回信息joson dump：", json.dumps(summary_message[0]))
        
        return {
            "messages": [AIMessage(content=summary_message[0])],
            "template_file_path": summary_message[1]
        }
        
    def _route_after_initial_collect_user_input(self, state: FrontdeskState) -> str:
        """初始调用ProcessUserInputAgent后，根据返回信息决定下一步的流程"""
        print("state测试", state["messages"][-1].content)
        summary_message = json.loads(state["messages"][-1].content)
        print("summary_message测试: ", summary_message)
        next_node = summary_message.get("next_node", "previous_node")
        print(f"🔄 路由决定: {next_node}")
            
        if next_node == "complex_template":
            return "complex_template_handle"
        elif next_node == "simple_template":
            return "simple_template_handle"
        else:
            return state.get("previous_node", "entry")  # Fallback to previous node
        

    def _route_after_collect_user_input(self, state: FrontdeskState) -> str:
        """This node will route the agent to the next node based on the summary message from the ProcessUserInputAgent"""
        summary_message_str = state["messages"][-1].content
        summary_message_json = json.loads(summary_message_str)
        summary_message = json.loads(summary_message_json[0])
        state["template_file_path"] = summary_message_json[1]
        print("summary_message测试: ", summary_message)
        next_node = summary_message.get("next_node", "previous_node")
        print(f"🔄 路由决定: {next_node}")
            
        if next_node == "complex_template":
            return "complex_template_handle"
        elif next_node == "simple_template":
            return "simple_template_handle"
        else:
            return state.get("previous_node", "entry")  # Fallback to previous node
            


    def _complex_template_analysis(self, state: FrontdeskState) -> FrontdeskState:
        """This node will be use to analyze the complex table template, we will skip for now"""
        pass

    def _chat_with_user_to_determine_template(self, state: FrontdeskState) -> FrontdeskState:
        """This node will chat with the user to determine the template, when the template is not provided"""
        # Use chat_history instead of the confusing JSON blob in messages
        user_context = state["chat_history"][-1] if state.get("chat_history") else "用户需要确定表格结构"

        system_prompt = f"""你是一个智能 Excel 表格生成助手，现在你需要和用户进行对话，来确认用户想要生成的表格结构内容。
表格可能涉及到复杂的多级表头，因此你需要弄清楚所有的结构层级，不断询问用户，直到你搞清楚全部需求，并返回以下格式：

1. 提取表格的多级表头结构：
   - 使用嵌套的 key-value 形式表示层级关系；
   - 每一级表头应以对象形式展示其子级字段或子表头；
   - 不需要额外字段（如 null、isParent 等），仅保留结构清晰的层级映射；

2. 提供一个对该表格内容的简要总结：
   - 内容应包括表格用途、主要信息类别、适用范围等；
   - 语言简洁，不超过 150 字；

输出格式如下：
{{
  "表格结构": {{
    "顶层表头名称": {{
      "二级表头名称": [
        "字段1",
        "字段2"
      ]
    }}
  }},
  "表格总结": "该表格的主要用途及内容说明..."
}}

请忽略所有 HTML 样式标签，只关注表格结构和语义信息。

你也可以调用工具来收集用户输入，来帮助你分析表格结构，有任何不确定的地方一定要询问用户，直到你完全明确表格结构为止。

当前情况: {user_context}
"""

        response = invoke_model_with_tools(model_name="Qwen/Qwen3-32B", messages=[SystemMessage(content=system_prompt)], tools=self.tools)
        
        # 创建AIMessage时需要保留tool_calls信息
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # 如果有工具调用，创建包含tool_calls的AIMessage
            ai_message = AIMessage(content=response.content or "", tool_calls=response.tool_calls)
        else:
            # 如果没有工具调用，只包含内容
            ai_message = AIMessage(content=str(response.content) if hasattr(response, 'content') else str(response))
        
        return {"table_structure": str(response),
                "previous_node": "chat_with_user_to_determine_template",
                "messages": [ai_message]
                }
    
    def _route_after_chat_with_user_to_determine_template(self, state: FrontdeskState) -> str:
        """This node will route the agent to the next node based on the user's input"""
        latest_message = state["messages"][-1]
        if hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
            return "collect_user_input"
        else:
            return "END"

    def _simple_template_analysis(self, state: FrontdeskState) -> FrontdeskState:
        """处理用户上传的简单模板"""
        # Handle the case where template_file_path might be a list
        template_file_path_raw = state["template_file_path"]
        print(f"🔍 Debug - template_file_path_raw: {template_file_path_raw} (type: {type(template_file_path_raw)})")
        
        if isinstance(template_file_path_raw, list):
            if len(template_file_path_raw) > 0:
                template_file_path = Path(template_file_path_raw[0])  # Take the first file
                print(f"🔍 Debug - Using first file from list: {template_file_path}")
            else:
                raise ValueError("template_file_path list is empty")
        else:
            template_file_path = Path(template_file_path_raw)
            print(f"🔍 Debug - Using single file path: {template_file_path}")
        template_file_content = template_file_path.read_text(encoding="utf-8")

        prompt = f"""你是一位专业的文档分析专家。请阅读用户上传的 HTML 格式的 Excel 文件，并完成以下任务：
        你也可以调用工具来收集用户输入，来帮助你分析表格结构，有任何不确定的地方一定要询问用户，直到你完全明确表格结构为止
        你不要所有问题都问用户，自己根据html的结构来分析，如果分析不出来，再问用户
        1. 提取表格的多级表头结构；
        - 使用嵌套的 key-value 形式表示层级关系；
        - 每一级表头应以对象形式展示其子级字段或子表头；
        - 不需要额外字段（如 null、isParent 等），仅保留结构清晰的层级映射；

        2. 提供一个对该表格内容的简要总结；
        - 内容应包括表格用途、主要信息类别、适用范围等；
        - 语言简洁，不超过 150 字；

        输出格式如下：
        {{
        "表格结构": {{
            "顶层表头名称": {{
            "二级表头名称": [
                "字段1",
                "字段2",
                ...
            ]
            }}
        }},
        "表格总结": "该表格的主要用途及内容说明..."
        }}

        请忽略所有 HTML 样式标签，只关注表格结构和语义信息。

        下面是用户上传的模板表格内容:
        {template_file_content}
        """


        response = invoke_model_with_tools(model_name="Qwen/Qwen3-32B", messages=[SystemMessage(content=prompt)], tools=self.tools)
        if response.content:
            print(response.content)
        print(response)
        # 创建AIMessage时需要保留tool_calls信息
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # 如果有工具调用，创建包含tool_calls的AIMessage
            ai_message = AIMessage(content=response.content or "", tool_calls=response.tool_calls)
        else:
            # 如果没有工具调用，只包含内容
            ai_message = AIMessage(content=str(response.content) if hasattr(response, 'content') else str(response))
        
        return {"template_structure": str(response),
                "previous_node": "simple_template_handle",
                "messages": [ai_message]
                }
        
    def _route_after_simple_template_analysis(self, state: FrontdeskState) -> str:
        """This node will route the agent to the next node based on the user's input"""
        latest_message = state["messages"][-1]
        if hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
            return "collect_user_input"
        else:
            return "END"

    
    def run_frontdesk_agent(self, session_id: str = "1") -> None:
        """This function will run the frontdesk agent"""
        # initial_state = self._create_initial_state(session_id)
        # config = {"configurable": {"thread_id": session_id}}
        # current_state = initial_state

        # while True:
        #     try:
        #         has_interrupt = False
        #         for chunk in self.graph.stream(current_state, config = config, stream_mode = "updates"):
        #             for node_name, node_output in chunk.items():
        #                 print(f"\n📍 Node: {node_name}")
        #                 print("-" * 30)

        #                 # check if there is an interrupt
        #                 if "__interrupt__" in chunk:
        #                     has_interrupt = True
        #                     interrupt_value = chunk['__interrupt__'][0].value
        #                     print(f"\n💬 智能体: {interrupt_value}")
        #                     user_response = input("👤 请输入您的回复: ")

        #                     # set the next input
        #                     current_state = Command(resume=user_response)
        #                     break

        #                 if isinstance(node_output, dict):
        #                     if "messages" in node_output and node_output["messages"]:
        #                         latest_message = node_output["messages"][-1]
        #                         if hasattr(latest_message, 'content') and not isinstance(latest_message, HumanMessage):
        #                             print(f"💬 智能体回复: {latest_message.content}")

        #                     for key, value in node_output.items():
        #                         if key != "messages" and value:
        #                             print(f"📊 {key}: {value}")
        #                 print("-" * 30)
                
        #         if not has_interrupt:
        #             break

            
        #     except Exception as e:
        #         print(f"❌ 处理用户输入时出错: {e}")
        #         break

        for chunk in self.graph.stream(self._create_initial_state(session_id), stream_mode = "updates"):
            for node_name, node_output in chunk.items():
                print(f"\n📍 Node: {node_name}")
                print("-" * 30)
                if isinstance(node_output, dict):
                    if "messages" in node_output and node_output["messages"]:
                        latest_message = node_output["messages"][-1]
                        if hasattr(latest_message, 'content') and not isinstance(latest_message, HumanMessage):
                            print(f"💬 智能体回复: {latest_message.content}")
                    for key, value in node_output.items():
                        if key != "messages" and value:
                            print(f"📊 {key}: {value}")
                print("-" * 30)

            

frontdesk_agent = FrontdeskAgent()
graph = frontdesk_agent.graph



if __name__ == "__main__":
    frontdesk_agent = FrontdeskAgent()
    frontdesk_agent.run_frontdesk_agent()