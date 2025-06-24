import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, filter_out_system_messages
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content
from utilities.modelRelated import model_creation, detect_provider

import uuid
import json
import os
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re

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


class FrontdeskState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    messages_s: Annotated[list[BaseMessage], add_messages]
    table_structure: str
    previous_node: str # Track the previous node
    session_id: str
    


class FrontdeskAgent:
    """
    用于处理用户上传的模板，若未提供模板，和用户沟通确定表格结构
    """



    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.llm_c = model_creation(model_name=model_name, temperature=2) # complex logic use user selected model
        self.llm_s = model_creation(model_name="gpt-3.5-turbo", temperature=2) # simple logic use 3-5turbo
        self.graph = self._build_graph()



    def _build_graph(self):
        """This function will build the graph of the frontdesk agent"""

        graph = StateGraph(FrontdeskState)

        graph.add_node("entry", self._entry_node)
        graph.add_node("collect_user_input", self._collect_user_input)
        graph.add_node("route_after_collect_user_input", self._route_after_collect_user_input)

        graph.add_edge(START, "entry")
        graph.add_edge("entry", "collect_user_input")
        # Add the missing nodes first
        graph.add_node("complex_template_handle", self._complex_template_analysis)
        graph.add_node("simple_template_handle", self._simple_template_analysis)
        graph.add_node("confirm_template", self._analyze_template)
        graph.add_node("confirm_table_structure", self._check_template)
        
        graph.add_conditional_edges(
            "collect_user_input",
            self._route_after_collect_user_input,
            {"complex_template_handle": "complex_template_handle",
             "simple_template_handle": "simple_template_handle",
             "confirm_template": "confirm_template",
             "confirm_table_structure": "confirm_table_structure",
             }
        )
        
        # Add edges to END for the terminal nodes
        graph.add_edge("complex_template_handle", END)
        graph.add_edge("simple_template_handle", END)
        graph.add_edge("confirm_template", END)
        graph.add_edge("confirm_table_structure", END)

        # Compile the graph to make it executable with stream() method
        # You can add checkpointer if needed: graph.compile(checkpointer=MemorySaver())
        return graph.compile()



    def _create_initial_state(self, session_id: str = "1") -> FrontdeskState:
        """This function will create the initial state of the frontdesk agent"""
        return {
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
            "previous_node": "entry"
        }

    def _collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """This node will collect user's input by calling the process user input agent,
        it should return a summary message that contains the next node to route to"""
        
        print(f"🔄 开始收集用户输入，当前会话ID: {state.get('session_id', 'unknown')}")
        
        # Create an instance of the ProcessUserInputAgent
        process_user_input_agent = ProcessUserInputAgent()
        
        # Create initial state for the agent
        current_state = process_user_input_agent.create_initial_state(previous_AI_messages = state["messages"])
        
        config = {"configurable": {"thread_id": state["session_id"]}}
        
        max_interrupt_count = 5
        interrupt_count = 0
        
        print(f"🔄 开始处理用户输入，最大中断次数: {max_interrupt_count}")
        
        while interrupt_count < max_interrupt_count:
            has_interrupt = False
            final_chunk = None

            try:
                print(f"🔄 开始流式处理，当前中断次数: {interrupt_count}")
                
                for chunk in process_user_input_agent.graph.stream(current_state, config = config, stream_mode = "updates"):
                    final_chunk = chunk
                    print(f"📦 收到chunk: {list(chunk.keys())}")

                    # check if there is an interrupt
                    if "__interrupt__" in chunk:
                        has_interrupt = True
                        interrupt_count += 1
                        interrupt_value = chunk['__interrupt__'][0].value
                        print(f"\n💬 智能体: {interrupt_value}")

                        user_response = input("👤 请输入您的回复: ")

                        # Resume the agnet with command and prepare for next iteration
                        current_state = Command(resume = user_response)
                        print(f"🔄 用户响应已设置，准备下一轮处理")
                        break

                if not has_interrupt:
                    print(f"✅ 处理完成，没有中断")
                    # No more interrupts, processing is complete
                    break
                    
            except Exception as e:
                print(f"❌ 处理用户输入时出错: {type(e).__name__}: {e}")
                import traceback
                print(f"❌ 详细错误信息: {traceback.format_exc()}")
                
                # Return error message
                return {
                    "messages": [AIMessage(content=f"处理用户输入时出错: {e}")],
                    "previous_node": "collect_user_input"
                }
        
        # Handle case where max interrupts reached
        if interrupt_count >= max_interrupt_count:
            print(f"⚠️ 达到最大中断次数 ({max_interrupt_count})")
            return {
                "messages": [AIMessage(content="已达到最大交互次数，请重新开始")],
                "previous_node": "collect_user_input"
            }
        
        # Extract the final result
        try:
            print(f"🔄 提取最终结果，final_chunk类型: {type(final_chunk)}")
            
            if final_chunk and "summary_user_input" in final_chunk:
                summary_data = final_chunk["summary_user_input"]
                
                # Handle both cases: summary_message field or direct content
                if "summary_message" in summary_data:
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
                
                return {
                    "messages": [result_message],
                    "previous_node": "collect_user_input"
                }
            else:
                print(f"⚠️ 未找到总结信息，final_chunk: {final_chunk}")
                return {
                    "messages": [AIMessage(content="未能获取有效的处理结果")],
                    "previous_node": "collect_user_input"
                }
                
        except Exception as e:
            print(f"❌ 提取结果时出错: {type(e).__name__}: {e}")
            return {
                "messages": [AIMessage(content=f"提取结果时出错: {e}")],
                "previous_node": "collect_user_input"
            }



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
    



                    

            

    def _check_template(self, state: FrontdeskState) -> FrontdeskState:
        """This node will check if the user has provided a template"""
        system_prompt = """你是一个智能填表助手智能体，你需要根据用户的输入来决定下一步的行动，如果用户提供了模板，
        请返回[YES]，否则返回[NO]，另外用户可能上传文件"""
        # user turbo at here
        response = self.llm_s.invoke([SystemMessage(content=system_prompt)] + state["messages"][-1])
        return {"messages": response}
    


    def _route_after_check_template(self, state: FrontdeskState) -> str:
        """This node will route the agent to the next node based on the user's input"""
        if state["messages"][-1].content == "[YES]":
            return "template_provided"
        else:
            return "no_template_provided"
        


    def _analyze_template(self, state: FrontdeskState) -> FrontdeskState:
        """This node will analyze the template to determine if it a complex template
        (both row, column headers) or a simple template (only column headers)"""
        system_prompt = """你需要根据html代码判断这个模板是复杂模板还是简单模板，判断规则为：
        1. 如果html代码中包含row和column headers，则返回[YES]
        2. 如果html代码中只包含column headers，则返回[NO]
        3. 如果html代码中既包含row headers又包含column headers，则返回[YES]
        4. 如果html代码中既包含row headers又包含column headers，则返回[YES]
        5. 如果html代码中既包含row headers又包含column headers，则返回[YES]
        """
        # use 3-5turbo at here
    


    def _complex_template_analysis(self, state: FrontdeskState) -> FrontdeskState:
        """This node will be use to analyze the complex table template, we will skip for now"""
        pass

    def _simple_template_analysis(self, state: FrontdeskState) -> FrontdeskState:
        """This node will be use to analyze the simple table template, we"""
        pass

    
    def run_frontdesk_agent(self, session_id: str = "1") -> None:
        """This function will run the frontdesk agent"""
        initial_state = self._create_initial_state(session_id)
        config = {"configurable": {"thread_id": session_id}}
        current_state = initial_state

        while True:
            try:
                has_interrupt = False
                for chunk in self.graph.stream(current_state, config = config, stream_mode = "updates"):
                    for node_name, node_output in chunk.items():
                        print(f"\n📍 Node: {node_name}")
                        print("-" * 30)

                        # check if there is an interrupt
                        if "__interrupt__" in chunk:
                            has_interrupt = True
                            interrupt_value = chunk['__interrupt__'][0].value
                            print(f"\n💬 智能体: {interrupt_value}")
                            user_response = input("👤 请输入您的回复: ")

                            # set the next input
                            current_state = Command(resume=user_response)
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
                
                if not has_interrupt:
                    break

            
            except Exception as e:
                print(f"❌ 处理用户输入时出错: {e}")
                break

            





if __name__ == "__main__":
    frontdesk_agent = FrontdeskAgent()
    frontdesk_agent.run_frontdesk_agent()