import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
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
from langgraph.types import Command, Interrupt, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool

# import other agents
from agents.processUserInput import ProcessUserInputAgent

load_dotenv()


@tool
def _collect_user_input(session_id: str, previous_AI_messages: BaseMessage) -> str:
    """这是一个用来收集用户输入的工具，你需要调用这个工具来收集用户输入，
    参数：
        state: 当前FrontdeskAgengt的状态，包含当前的messages，session_id，previous_node
    返回：
        FrontdeskState: 包含当前的messages，session_id，previous_node, 以及process_user_input_agent的返回结果等
    """

    print(f"🔄 开始收集用户输入，当前会话ID: {session_id}")
    
    # Create an instance of the ProcessUserInputAgent
    process_user_input_agent = ProcessUserInputAgent()
    
    final_chunk = process_user_input_agent.run_process_user_input_agent(session_id = session_id, previous_AI_messages = previous_AI_messages)
    
    # Extract the final result
    try:
        print(f"🔄 提取最终结果，final_chunk类型: {type(final_chunk)}")
        
        if final_chunk and "summary_user_input" in final_chunk:
            summary_data = final_chunk["summary_user_input"]
            
            # Handle both cases: summary_message field or direct content
            if "summary_message" in summary_data:
                print("summary_message in summary_data")
                summary_content = summary_data["summary_message"]
            elif "process_user_input_messages" in summary_data and summary_data["process_user_input_messages"]:
                # Extract from the last message
                last_msg = summary_data["process_user_input_messages"][-1]
                if hasattr(last_msg, 'content'):
                    summary_content = last_msg.content
                else:
                    summary_content = str(last_msg)
            else:
                summary_content = str(summary_data)
            
            print(f"✅ 成功提取总结信息: {str(summary_content)[:100]}...")
            
            # Create the message with the summary content  
            # Content should always be a JSON string now
            if isinstance(summary_content, str):
                # Content is already a JSON string, use it directly
                result_message = AIMessage(content=summary_content)
            else:
                # Convert to JSON string if it's not already
                import json
                result_message = AIMessage(content=json.dumps(summary_content, ensure_ascii=False))
                
            result_message.name = "summary_message"
            
            return Command(
                update = {
                    "messages": [result_message],
                    "chat_history": summary_content,
                }   
            )
        else:
            print(f"⚠️ 未找到总结信息，final_chunk: {final_chunk}")
            return Command(
                update = {
                    "messages": [AIMessage(content="未能获取有效的处理结果")],
                    "chat_history": "未能获取有效的处理结果",
                }
            )
            
    except Exception as e:
        print(f"❌ 提取结果时出错: {type(e).__name__}: {e}")
        return Command(
            update = {
                "messages": [AIMessage(content=f"提取结果时出错: {e}")],
                "chat_history": f"提取结果时出错: {e}",
            }
        )
    

class FrontdeskState(TypedDict):
    chat_history: Annotated[list[str], add_messages]
    messages: Annotated[list[BaseMessage], add_messages]
    table_structure: str
    previous_node: str # Track the previous node
    session_id: str
    template_structure: str
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
        graph.add_node("force_collect_user_input", self._force_collect_user_input)
        graph.add_node("complex_template_handle", self._complex_template_analysis)
        graph.add_node("simple_template_handle", self._simple_template_analysis)
        graph.add_node("chat_with_user_to_determine_template", self._chat_with_user_to_determine_template)

        graph.add_edge(START, "entry")
        graph.add_edge("entry", "force_collect_user_input")
        graph.add_conditional_edges("force_collect_user_input", self._route_after_collect_user_input)
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
    

    def _force_collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """直接调用工具收集用户输入"""
        session_id = state["session_id"]
        previous_AI_messages = state["messages"][-1]
         # ✅ Use .invoke() method with proper input format
        tool_input = {
        "session_id": session_id,
        "previous_AI_messages": previous_AI_messages
        }
        command_result = _collect_user_input.invoke(tool_input)

        return command_result.update

    def _route_after_collect_user_input(self, state: FrontdeskState) -> str:
        """This node will route the agent to the next node based on the summary message from the ProcessUserInputAgent"""

        try:
            # Check if the last message has the expected structure
            last_message = state["messages"][-1]
            if hasattr(last_message, 'content') and isinstance(last_message.content, str):
                # Content is a JSON string - parse it
                import json
                try:
                    content_dict = json.loads(last_message.content)
                    next_node = content_dict.get("next_node", "previous_node")
                    print(f"✅ 成功解析JSON: {content_dict}")
                except json.JSONDecodeError:
                    print(f"⚠️ 无法解析JSON内容: {last_message.content}")
                    next_node = "previous_node"
            else:
                print(f"⚠️ 消息格式不正确，期望字符串，得到: {type(last_message.content)}")
                next_node = "previous_node"
            
            print(f"🔄 路由决定: {next_node}")
            
            if next_node == "complex_template":
                return "complex_template_handle"
            elif next_node == "simple_template":
                return "simple_template_handle"
            else:
                return state.get("previous_node", "entry")  # Fallback to previous node
                
        except Exception as e:
            print(f"❌ 路由决定时出错: {e}")
            import traceback
            print(f"❌ 详细错误: {traceback.format_exc()}")
            return state.get("previous_node", "entry")  # Safe fallback
            


    def _complex_template_analysis(self, state: FrontdeskState) -> FrontdeskState:
        """This node will be use to analyze the complex table template, we will skip for now"""
        pass

    def _chat_with_user_to_determine_template(self, state: FrontdeskState) -> FrontdeskState:
        """This node will chat with the user to determine the template, when the template is not provided"""
        system_prompt = """你是一个智能excel表格生成助手，现在你需要和用户进行对话，来确认用户想要生成的表格结构
        内容，表格可能涉及到复杂的多级表头，因此你需要弄清楚所有的结构层级，不断询问用户，知道你搞清楚全部需求，并返回
        以下格式：
        1. 提取表格的多级表头结构；
   - 使用嵌套的 key-value 形式表示层级关系；
   - 每一级表头应以对象形式展示其子级字段或子表头；
   - 不需要额外字段（如 null、isParent 等），仅保留结构清晰的层级映射；

2. 提供一个对该表格内容的简要总结；
   - 内容应包括表格用途、主要信息类别、适用范围等；
   - 语言简洁，不超过 150 字；

输出格式如下：
{
  "表格结构": {
    "顶层表头名称": {
      "二级表头名称": [
        "字段1",
        "字段2",
        ...
      ],
      ...
    },
    ...
  },
  "表格总结": "该表格的主要用途及内容说明..."
}

        请忽略所有 HTML 样式标签，只关注表格结构和语义信息。

        你也可以调用工具来收集用户输入，来帮助你分析表格结构，有任何不确定的地方一定要询问用户，直到你完全明确表格结构为止
        """

        response = invoke_model_with_tools(model_name="Qwen/Qwen3-8B", messages=[SystemMessage(content=system_prompt)] + state["messages"], tools=self.tools)
        
        # 创建AIMessage时需要保留tool_calls信息
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # 如果有工具调用，创建包含tool_calls的AIMessage
            ai_message = AIMessage(content=response.content or "", tool_calls=response.tool_calls)
        else:
            # 如果没有工具调用，只包含内容
            ai_message = AIMessage(content=str(response.content) if hasattr(response, 'content') else str(response))
        
        return {"table_structure": str(response),
                "previous_node": "complex_template_handle",
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
        prompt = """你是一位专业的文档分析专家。请阅读用户上传的 HTML 格式的 Excel 文件，并完成以下任务：
        你也可以调用工具来收集用户输入，来帮助你分析表格结构，有任何不确定的地方一定要询问用户，直到你完全明确表格结构为止
1. 提取表格的多级表头结构；
   - 使用嵌套的 key-value 形式表示层级关系；
   - 每一级表头应以对象形式展示其子级字段或子表头；
   - 不需要额外字段（如 null、isParent 等），仅保留结构清晰的层级映射；

2. 提供一个对该表格内容的简要总结；
   - 内容应包括表格用途、主要信息类别、适用范围等；
   - 语言简洁，不超过 150 字；

输出格式如下：
{
  "表格结构": {
    "顶层表头名称": {
      "二级表头名称": [
        "字段1",
        "字段2",
        ...
      ],
      ...
    },
    ...
  },
  "表格总结": "该表格的主要用途及内容说明..."
}

请忽略所有 HTML 样式标签，只关注表格结构和语义信息。"""

        response = invoke_model_with_tools(model_name="Qwen/Qwen3-8B", messages=[SystemMessage(content=prompt)] + state["messages"], tools=[self._collect_user_input])
        
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