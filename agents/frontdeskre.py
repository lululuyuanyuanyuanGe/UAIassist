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


load_dotenv()


class FrontdeskState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    messages_s: Annotated[list[BaseMessage], add_messages]
    table_structure: str
    upload_files_path: list[str]
    new_upload_files_path: list[str] # Track the new uploaded files
    upload_files_processed_path: list[str]
    new_upload_files_processed_path: list[str]
    upload_template: str # This variable will hold the actual content of the template
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



    def _build_graph(self) -> StateGraph:
        """This function will build the graph of the frontdesk agent"""

        graph = StateGraph(FrontdeskState)

        graph.add_node("entry", self._entry_node)
        graph.add_node("collect_user_input", self._collect_user_input)
        graph.add_node("route_after_collect_user_input", self._route_after_collect_user_input)
        graph.add_node("file_upload", self._file_upload)

        graph.add_edge(START, "entry")
        graph.add_edge("entry", "collect_user_input")
        graph.add_edge("collect_user_input", "route_after_collect_user_input")
        graph.add_edge("route_after_collect_user_input", "file_upload")
        graph.add_edge("file_upload", END)
        return graph



    def _entry_node(self, state: FrontdeskState) -> FrontdeskState:
        """This is the starting node of our frontdesk agent"""
        # Enrich this later, it should include a short description of the agent's ability and how to use it
        print("你好，我是一个表格处理助手！")
        # Here we will add a human in the loop to get user's response



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







    def _collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """This is the node where we get user's input"""
        user_input = interrupt("用户：")
        return {"messages": user_input}



    def _route_after_collect_user_input(self, state: FrontdeskState) -> FrontdeskState:
        """This node act as a safety check node, it will analyze the user's input and determine if it's a valid input,
        based on the LLM's previous response, at the same time it will route the agent to the correct node"""
        # We should let LLM decide the route
        
        user_upload_files = detect_and_process_file_paths(state["messages"][-1])
        # Filter out the new uploaded files
        new_upload_files = [item for item in user_upload_files if item not in state["upload_files_path"]]
        if new_upload_files:
            state["new_upload_files_path"] = new_upload_files
            state["upload_files_path"].extend(new_upload_files)
            return "file_upload"
        
        # User didn't upload new files
        elif not user_upload_files:
            system_prompt = """你需要判断用户的输入是否为有效输入，判断标准为"""
            LLM_response_and_user_input = [state["messages"][-2], state["messages"][-1]]
            LLM_decision = self.llm_s.invoke([SystemMessage(content=system_prompt)] + LLM_response_and_user_input)
            # If it is a valid input we conitnue the normal execution flow, otherwise we will keep leting user 
            # input messages until it is a valid input
            if LLM_decision.content == "[YES]":
                return "valid_input"
            else:
                print(f"❌ Invalid input: {state['messages'][-1].content}")
                return "invalid_input"
    


    def _uploaded_files(self, state: FrontdeskState) -> FrontdeskState:
        """This node will upload user's file to our system"""
        # For now we simply store the file content 
        result = retrieve_file_content(state["new_upload_files_path"], state["session_id"])
        state["new_upload_files_processed_path"] = result
        state["upload_files_processed_path"].extend(result)
        print(f"✅ File uploaded: {state['upload_files_processed_path']}")
        return "check_template"
    


    def _analyze_uploaded_files_related_to_agent_task(self, state: FrontdeskState) -> FrontdeskState:
        """This node will analyze the uploaded files to determine if it's a valid file that is related
        to our agent's task in general, if it does we will keep the file, also we will summarize the file's content
        and store it as json format in the data.json file, basically it will append to the data.json file,
        it should contains the file;s name as the key, the value should be the description of the file's content
        and important information in the file, if it is not a related file we will remove delete this file from 
        our system."""
        
        import json
        import os
        from pathlib import Path
        
        # Load existing data.json or create empty dict
        data_json_path = Path("agents/data.json")
        try:
            if data_json_path.exists() and data_json_path.stat().st_size > 0:
                with open(data_json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            else:
                existing_data = {}
        except (json.JSONDecodeError, FileNotFoundError):
            existing_data = {}
            print("⚠️ 创建新的 data.json 文件")
        
        relevant_files = []
        irrelevant_files = []
        
        # Process each newly uploaded file
        for file_path in state.get("new_upload_files_processed_path", []):
            try:
                source_path = Path(file_path)
                if not source_path.exists():
                    print(f"❌ 文件不存在: {file_path}")
                    continue
                
                # Read file content for analysis
                file_content = source_path.read_text(encoding='utf-8')
                
                # Truncate content for analysis (to avoid token limits)
                analysis_content = file_content[:2000] if len(file_content) > 2000 else file_content
                
                # Create analysis prompt
                system_prompt = f"""你是一个智能文件分析助手。你需要分析用户上传的文件，判断它是否与表格生成、数据填写、模板处理等任务相关。
                与任务相关的文件将会被存储起来，判断标准如下
                
                表格文件已经全部转换为html代码，你需要根据内容判断这个文件是否包含具体的数据，如果包含具体数据意味着这是一个
                用户对数据库的补充，因此这个文件是相关的，如果只有表格结构没有具体数据，则意味着这个文件是表格的模板。如果用户
                上传的是纯文本文件，你需要判断这个文本文件和表格填写是否有关，有些文本可能包含填写的规则，或者法律条文，政策信息
                这些都会辅助我们以后对表格的填写，因此这个文件是相关的。
                
                文件名: {source_path.name}
                文件路径: {file_path}
                文件内容预览:
                {analysis_content}
                
                请按以下格式回复：
                相关性: [YES/NO]
                是否为模板: [YES/NO]
                摘要: [文件内容的简要描述，重点描述其中的重要信息、数据结构、表格结构等，列出所有表头]
                重要信息: [提取文件中的关键信息，法律条文，政策信息，表格填写规则]
                """
                
                # Get LLM analysis
                analysis_response = self.llm_c.invoke([SystemMessage(content=system_prompt)])
                analysis_text = analysis_response.content
                
                # Parse LLM response
                is_relevant = False
                summary = ""
                important_info = ""
                
                if "[YES]" in analysis_text.upper() or "相关性: YES" in analysis_text:
                    is_relevant = True
                
                # Extract summary and important info
                lines = analysis_text.split('\n')
                for line in lines:
                    if line.startswith('摘要:') or '摘要：' in line:
                        summary = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    elif line.startswith('重要信息:') or '重要信息：' in line:
                        important_info = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                
                # If no structured response, use the entire analysis as summary
                if not summary:
                    summary = analysis_text.strip()
                
                if is_relevant:
                    # Keep the file and add to data.json
                    file_info = {
                        "description": summary,
                        "important_info": important_info,
                        "file_path": str(file_path),
                        "file_type": source_path.suffix.lower(),
                        "file_size": source_path.stat().st_size,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    existing_data[source_path.name] = file_info
                    relevant_files.append(file_path)
                    print(f"✅ 相关文件已保留: {source_path.name}")
                    print(f"   摘要: {summary[:100]}...")
                    
                else:
                    # Mark for deletion
                    irrelevant_files.append(file_path)
                    print(f"❌ 不相关文件将被删除: {source_path.name}")
                    print(f"   原因: {summary[:100]}...")
                    
            except Exception as e:
                print(f"❌ 分析文件时出错 {file_path}: {e}")
                # On error, keep the file to be safe
                relevant_files.append(file_path)
        
        # Delete irrelevant files
        for file_path in irrelevant_files:
            try:
                file_to_delete = Path(file_path)
                if file_to_delete.exists():
                    os.remove(file_to_delete)
                    print(f"🗑️ 已删除不相关文件: {file_to_delete.name}")
                
                # Also remove from state lists
                if file_path in state.get("upload_files_processed_path", []):
                    state["upload_files_processed_path"].remove(file_path)
                if file_path in state.get("new_upload_files_processed_path", []):
                    state["new_upload_files_processed_path"].remove(file_path)
                    
            except Exception as e:
                print(f"❌ 删除文件时出错 {file_path}: {e}")
        
        # Save updated data.json
        try:
            with open(data_json_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            print(f"✅ 已更新 data.json，包含 {len(existing_data)} 个文件记录")
        except Exception as e:
            print(f"❌ 保存 data.json 时出错: {e}")
        
        # Update state to only include relevant files
        state["new_upload_files_processed_path"] = [f for f in state.get("new_upload_files_processed_path", []) if f in relevant_files]
        
        # Add analysis summary to messages
        analysis_summary = f"""
📋 文件分析完成:
✅ 相关文件: {len(relevant_files)} 个
❌ 不相关文件: {len(irrelevant_files)} 个 (已删除)
📝 数据库记录: {len(existing_data)} 个文件

相关文件列表:
{chr(10).join([f"• {Path(f).name}" for f in relevant_files])}
"""
        
        return {
            "messages": [SystemMessage(content=analysis_summary)]
        }



def _analyze_uploaded_files_related_to

# after we analyze the how related the uploaded files to our system, we will determine if it is related to the
# question the LLM just asked, if that it is related, we will store the content of the file in the state
# and pass it for the LLM to analyze