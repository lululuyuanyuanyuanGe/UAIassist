import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.modelRelated import invoke_model
from utilities.file_process import (detect_and_process_file_paths, retrieve_file_content, save_original_file,
                                    extract_filename, determine_location_from_content, 
                                    ensure_location_structure, check_file_exists_in_data,
                                    get_available_locations, move_template_files_to_final_destination,
                                    move_supplement_files_to_final_destination, delete_files_from_staging_area)


import uuid
import json
import os
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re

from langgraph.graph import StateGraph, END, START
from langgraph.constants import Send
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

class ProcessUserInputState(TypedDict):
    process_user_input_messages: Annotated[list[BaseMessage], add_messages]
    user_input: str
    upload_files_path: list[str] # Store all uploaded files
    new_upload_files_path: list[str] # Track the new uploaded files in this round
    new_upload_files_processed_path: list[str] # Store the processed new uploaded files
    original_files_path: list[str] # Store the original files in original_file subfolder
    uploaded_template_files_path: list[str]
    supplement_files_path: dict[str, list[str]]
    irrelevant_files_path: list[str]
    irrelevant_original_files_path: list[str] # Track original files to be deleted with irrelevant files
    all_files_irrelevant: bool  # Flag to indicate all files are irrelevant
    text_input_validation: str  # Store validation result [Valid] or [Invalid]
    previous_AI_messages: list[BaseMessage]
    summary_message: str  # Add the missing field
    template_complexity: str

    
class ProcessUserInputAgent:

    @tool
    def request_user_clarification(question: str, context: str = "") -> str:
        """
        询问用户澄清，和用户确认，或者询问用户补充信息，当你不确定的时候请询问用户

        参数：
            question: 问题
            context: 可选补充内容，解释为甚恶魔你需要一下信息
        """
        print("\n" + "="*60)
        print("🤔 需要您的确认")
        print("="*60)
        print(f"📋 {question}")
        if context:
            print(f"💡 {context}")
        print("="*60)
        
        user_response = input("👤 请输入您的选择: ").strip()
        
        print(f"✅ 您的选择: {user_response}")
        print("="*60 + "\n")
        
        return user_response
    
    tools = [request_user_clarification]



    def __init__(self):
        self.memory = MemorySaver()
        self.graph = self._build_graph().compile(checkpointer=self.memory)


    def _build_graph(self) -> StateGraph:
        """This function will build the graph for the process user input agent"""
        graph = StateGraph(ProcessUserInputState)
        graph.add_node("collect_user_input", self._collect_user_input)
        graph.add_node("file_upload", self._file_upload)
        graph.add_node("analyze_uploaded_files", self._analyze_uploaded_files)
        graph.add_node("process_template", self._process_template)
        graph.add_node("process_supplement", self._process_supplement)
        graph.add_node("process_irrelevant", self._process_irrelevant)
        graph.add_node("analyze_text_input", self._analyze_text_input)
        graph.add_node("clarification_tool_node", ToolNode(self.tools, messages_key = "process_user_input_messages"))
        graph.add_node("summary_user_input", self._summary_user_input)
        
        graph.add_edge(START, "collect_user_input")

        graph.add_conditional_edges(
            "collect_user_input",
            self._route_after_collect_user_input,
            {
                "file_upload": "file_upload",
                "analyze_text_input": "analyze_text_input",
            }
        )

        graph.add_edge("file_upload", "analyze_uploaded_files")

        graph.add_conditional_edges(
            "analyze_uploaded_files",
            self._route_after_analyze_uploaded_files # Since we are using the send objects, we don't need to specify the edges
        )

        # After tool execution, re-analyze uploaded files with user input
        graph.add_edge("clarification_tool_node", "analyze_uploaded_files")

        graph.add_edge("process_template", "summary_user_input")
        graph.add_edge("process_supplement", "summary_user_input")
        graph.add_edge("process_irrelevant", "summary_user_input")

        graph.add_conditional_edges(
            "analyze_text_input",
            self._route_after_analyze_text_input,
            {
                "valid_text_input": "summary_user_input",
                "invalid_text_input": "collect_user_input",
            }
        )

        graph.add_edge("summary_user_input", END)
        return graph



    def create_initial_state(self, previous_AI_messages = None) -> ProcessUserInputState:
        """This function initializes the state of the process user input agent"""
        
        # Handle both single BaseMessage and list[BaseMessage] input
        processed_messages = None
        if previous_AI_messages is not None:
            if isinstance(previous_AI_messages, list):
                processed_messages = previous_AI_messages
                print(f"🔍 初始化: 接收到消息列表，包含 {len(previous_AI_messages)} 条消息")
            else:
                # It's a single message, convert to list
                processed_messages = [previous_AI_messages]
                print(f"🔍 初始化: 接收到单条消息，已转换为列表")
        else:
            print(f"🔍 初始化: 没有接收到previous_AI_messages")
        
        return {
            "process_user_input_messages": [],
            "user_input": "",
            "upload_files_path": [],
            "new_upload_files_path": [],
            "new_upload_files_processed_path": [],
            "original_files_path": [],
            "uploaded_template_files_path": [],
            "supplement_files_path": {"表格": [], "文档": []},
            "irrelevant_files_path": [],
            "irrelevant_original_files_path": [],
            "all_files_irrelevant": False,
            "text_input_validation": None,
            "previous_AI_messages": processed_messages,
            "summary_message": "",
            "template_complexity": ""
        }


    def _collect_user_input(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This is the node where we get user's input"""
        print("\n🔍 开始执行: _collect_user_input")
        print("=" * 50)
        print("⌨️ 等待用户输入...")
        
        user_input = interrupt("用户：")
        
        print(f"📥 接收到用户输入: {user_input[:100]}{'...' if len(user_input) > 100 else ''}")
        print("✅ _collect_user_input 执行完成")
        print("=" * 50)
        
        return {
            "process_user_input_messages": [HumanMessage(content=user_input)],
            "user_input": user_input
        }



    def _route_after_collect_user_input(self, state: ProcessUserInputState) -> str:
        """This node act as a safety check node, it will analyze the user's input and determine if it's a valid input,
        based on the LLM's previous response, at the same time it will route the agent to the correct node"""
        
        # Extract content from the message object
        latest_message = state["process_user_input_messages"][-1]
        message_content = latest_message.content if hasattr(latest_message, 'content') else str(latest_message)
        
        # Check if there are files in the user input
        user_upload_files = detect_and_process_file_paths(message_content)
        if user_upload_files:
            # Files detected - route to file_upload 
            # Note: We cannot modify state in routing functions, so file_upload node will re-detect files
            return "file_upload"
        
        # User didn't upload any new files, we will analyze the text input
        return "analyze_text_input"



    def _file_upload(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will upload user's file to our system"""
        print("\n🔍 开始执行: _file_upload")
        print("=" * 50)
        
        # Re-detect files from user input since routing functions cannot modify state
        latest_message = state["process_user_input_messages"][-1]
        message_content = latest_message.content if hasattr(latest_message, 'content') else str(latest_message)
        
        print("📁 正在检测用户输入中的文件路径...")
        detected_files = detect_and_process_file_paths(message_content)
        print(f"📋 检测到 {len(detected_files)} 个文件")
        
        # Load data.json with error handling
        data_file = Path("agents/data.json")
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"⚠️ data.json文件出错: {e}")
            # Initialize empty structure if file is missing or corrupted
            data = {}
        
        print("🔍 正在检查文件是否已存在...")
        files_to_remove = []
        for file in detected_files:
            file_name = Path(file).name
            if check_file_exists_in_data(data, file_name):
                files_to_remove.append(file)
                print(f"⚠️ 文件 {file} 已存在")
        
        # Remove existing files from detected_files
        for file in files_to_remove:
            detected_files.remove(file)
        
        if not detected_files:
            print("⚠️ 没有新文件需要上传")
            print("✅ _file_upload 执行完成")
            print("=" * 50)
            return {
                "new_upload_files_path": [],
                "new_upload_files_processed_path": []
            }
        
        print(f"🔄 正在处理 {len(detected_files)} 个新文件...")
        
        # Create staging area for original files
        project_root = Path.cwd()
        staging_dir = project_root / "conversations" / "files" / "user_uploaded_files"
        staging_dir.mkdir(parents=True, exist_ok=True)
        
        # Process the files to get .txt versions
        processed_files = retrieve_file_content(detected_files, "files")
        
        # Save original files separately
        original_files = []
        for file_path in detected_files:
            try:
                source_path = Path(file_path)
                original_file_saved_path = save_original_file(source_path, staging_dir)
                if original_file_saved_path:
                    original_files.append(original_file_saved_path)
                    print(f"💾 原始文件已保存: {Path(original_file_saved_path).name}")
                else:
                    print(f"⚠️ 原始文件保存失败: {source_path.name}")
            except Exception as e:
                print(f"❌ 保存原始文件时出错 {file_path}: {e}")
        
        print(f"✅ 文件处理完成: {len(processed_files)} 个处理文件, {len(original_files)} 个原始文件")
        print("✅ _file_upload 执行完成")
        print("=" * 50)
        
        # Update state with new files
        # Safely handle the case where upload_files_path might not exist in state
        existing_files = state.get("upload_files_path", [])
        existing_original_files = state.get("original_files_path", [])
        return {
            "new_upload_files_path": detected_files,
            "upload_files_path": existing_files + detected_files,
            "new_upload_files_processed_path": processed_files,
            "original_files_path": existing_original_files + original_files
        }
    


    def _analyze_uploaded_files(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will analyze the user's uploaded files, it need to classify the file into template
        supplement, or irrelevant. If all files are irrelevant, it will flag for text analysis instead."""
        
        print("\n🔍 开始执行: _analyze_uploaded_files")
        print("=" * 50)
        
        import json
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Initialize classification results
        classification_results = {
            "template": [],
            "supplement": {"表格": [], "文档": []},
            "irrelevant": []
        }
        
        # Process files one by one for better accuracy
        processed_files = []
        # Safely handle the case where new_upload_files_processed_path might not exist in state
        new_files_to_process = state.get("new_upload_files_processed_path", [])
        
        print(f"📁 需要分析的文件数量: {len(new_files_to_process)}")
        
        if not new_files_to_process:
            print("⚠️ 没有找到可处理的文件")
            print("✅ _analyze_uploaded_files 执行完成")
            print("=" * 50)
            return {
                "uploaded_template_files_path": [],
                "supplement_files_path": {"表格": [], "文档": []},
                "irrelevant_files_path": [],
                "all_files_irrelevant": True,  # Flag for routing to text analysis
                "process_user_input_messages": [SystemMessage(content="没有找到可处理的文件，将分析用户文本输入")]
            }
        
        def analyze_single_file(file_path: str) -> tuple[str, str, str]:
            """Analyze a single file and return (file_path, classification, file_name)"""
            try:
                source_path = Path(file_path)
                print(f"🔍 正在分析文件: {source_path.name}")
                
                if not source_path.exists():
                    print(f"❌ 文件不存在: {file_path}")
                    return file_path, "irrelevant", source_path.name
                
                # Read file content for analysis
                file_content = source_path.read_text(encoding='utf-8')
                # Truncate content for analysis (to avoid token limits)
                analysis_content = file_content[:5000] if len(file_content) > 2000 else file_content
                
                # Create individual analysis prompt for this file
                system_prompt = f"""你是一个表格生成智能体，需要分析用户上传的文件内容并进行分类。共有四种类型：

                1. **模板类型 (template)**: 空白表格模板，只有表头没有具体数据
                2. **补充表格 (supplement-表格)**: 已填写的完整表格，用于补充数据库
                3. **补充文档 (supplement-文档)**: 包含重要信息的文本文件，如法律条文、政策信息等
                4. **无关文件 (irrelevant)**: 与表格填写无关的文件

                仔细检查不要把补充文件错误划分为模板文件反之亦然，补充文件里面是有数据的，模板文件里面是空的，或者只有一两个例子数据
                注意：所有文件已转换为txt格式，表格以HTML代码形式呈现，请根据内容而非文件名或后缀判断。

                用户输入: {state.get("user_input", "")}

                当前分析文件:
                文件名: {source_path.name}
                文件路径: {file_path}
                文件内容:
                {analysis_content}

                请严格按照以下JSON格式回复，只返回这一个文件的分类结果（不要添加任何其他文字），不要将返回内容包裹在```json```中：
                {{
                    "classification": "template" | "supplement-表格" | "supplement-文档" | "irrelevant"
                }}"""
                
                # Get LLM analysis for this file
                print("📤 正在调用LLM进行文件分类...")
                analysis_response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])

                # Parse JSON response for this file
                try:
                    # Extract JSON from response
                    response_content = analysis_response.strip()
                    print(f"📥 LLM分类响应: {response_content}")
                    
                    # Remove markdown code blocks if present
                    if response_content.startswith('```'):
                        response_content = response_content.split('\n', 1)[1]
                        response_content = response_content.rsplit('\n', 1)[0]
                    
                    file_classification = json.loads(response_content)
                    classification_type = file_classification.get("classification", "irrelevant")
                    
                    print(f"✅ 文件 {source_path.name} 分类为: {classification_type}")
                    return file_path, classification_type, source_path.name
                    
                except json.JSONDecodeError as e:
                    print(f"❌ 文件 {source_path.name} JSON解析错误: {e}")
                    print(f"LLM响应: {analysis_response}")
                    # Fallback: mark as irrelevant for safety
                    return file_path, "irrelevant", source_path.name
                
            except Exception as e:
                print(f"❌ 处理文件出错 {file_path}: {e}")
                # Return irrelevant on error
                return file_path, "irrelevant", Path(file_path).name
        
        # Use ThreadPoolExecutor for parallel processing
        max_workers = min(len(new_files_to_process), 5)  # Limit to 5 concurrent requests
        print(f"🚀 开始并行处理文件，使用 {max_workers} 个工作线程")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all file analysis tasks
            future_to_file = {
                executor.submit(analyze_single_file, file_path): file_path 
                for file_path in new_files_to_process
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    file_path_result, classification_type, file_name = future.result()
                    
                    # Add to appropriate category
                    if classification_type == "template":
                        classification_results["template"].append(file_path_result)
                    elif classification_type == "supplement-表格":
                        classification_results["supplement"]["表格"].append(file_path_result)
                    elif classification_type == "supplement-文档":
                        classification_results["supplement"]["文档"].append(file_path_result)
                    else:  # irrelevant or unknown
                        classification_results["irrelevant"].append(file_path_result)
                    
                    processed_files.append(file_name)
                    
                except Exception as e:
                    print(f"❌ 并行处理文件任务失败 {file_path}: {e}")
                    # Add to irrelevant on error
                    classification_results["irrelevant"].append(file_path)
        
        print(f"🎉 并行文件分析完成:")
        print(f"  - 模板文件: {len(classification_results['template'])} 个")
        print(f"  - 补充表格: {len(classification_results['supplement']['表格'])} 个")
        print(f"  - 补充文档: {len(classification_results['supplement']['文档'])} 个")
        print(f"  - 无关文件: {len(classification_results['irrelevant'])} 个")
        print(f"  - 成功处理: {len(processed_files)} 个文件")
        
        if not processed_files and not classification_results["irrelevant"]:
            print("⚠️ 没有找到可处理的文件")
            print("✅ _analyze_uploaded_files 执行完成")
            print("=" * 50)
            return {
                "uploaded_template_files_path": [],
                "supplement_files_path": {"表格": [], "文档": []},
                "irrelevant_files_path": [],
                "all_files_irrelevant": True,  # Flag for routing to text analysis
                "process_user_input_messages": [SystemMessage(content="没有找到可处理的文件，将分析用户文本输入")]
            }
        
        # Update state with classification results
        uploaded_template_files = classification_results.get("template", [])
        supplement_files = classification_results.get("supplement", {"表格": [], "文档": []})
        irrelevant_files = classification_results.get("irrelevant", [])
        
        # Create mapping of processed files to original files to track irrelevant originals
        irrelevant_original_files = []
        if irrelevant_files:
            original_files = state.get("original_files_path", [])
            processed_files = state.get("new_upload_files_processed_path", [])
            
            print("🔍 正在映射无关文件对应的原始文件...")
            
            # Create mapping based on filename (stem)
            for irrelevant_file in irrelevant_files:
                irrelevant_file_stem = Path(irrelevant_file).stem
                # Find the corresponding original file
                for original_file in original_files:
                    original_file_stem = Path(original_file).stem
                    if irrelevant_file_stem == original_file_stem:
                        irrelevant_original_files.append(original_file)
                        print(f"📋 映射无关文件: {Path(irrelevant_file).name} -> {Path(original_file).name}")
                        break
        
        # Check if all files are irrelevant
        # Safely handle the case where new_upload_files_processed_path might not exist in state
        new_files_processed_count = len(state.get("new_upload_files_processed_path", []))
        all_files_irrelevant = (
            len(uploaded_template_files) == 0 and 
            len(supplement_files.get("表格", [])) == 0 and 
            len(supplement_files.get("文档", [])) == 0 and
            len(irrelevant_files) == new_files_processed_count
        )
        
        if all_files_irrelevant:
            print("⚠️ 所有文件都被分类为无关文件")
            print("✅ _analyze_uploaded_files 执行完成")
            print("=" * 50)
            return {
                "uploaded_template_files_path": [],
                "supplement_files_path": {"表格": [], "文档": []},
                "irrelevant_files_path": irrelevant_files,
                "irrelevant_original_files_path": irrelevant_original_files,
                "all_files_irrelevant": True,  # Flag for routing
            }
        else:
            # Some files are relevant, proceed with normal flow
            analysis_summary = f"""文件分析完成:
            模板文件: {len(uploaded_template_files)} 个
            补充表格: {len(supplement_files.get("表格", []))} 个  
            补充文档: {len(supplement_files.get("文档", []))} 个
            无关文件: {len(irrelevant_files)} 个"""
            
            print("✅ 文件分析完成，存在有效文件")
            print("✅ _analyze_uploaded_files 执行完成")
            print("=" * 50)
            
            return {
                "uploaded_template_files_path": uploaded_template_files,
                "supplement_files_path": supplement_files,
                "irrelevant_files_path": irrelevant_files,
                "irrelevant_original_files_path": irrelevant_original_files,
                "all_files_irrelevant": False,  # Flag for routing
                "process_user_input_messages": [SystemMessage(content=analysis_summary)]
            }
                
    def _route_after_analyze_uploaded_files(self, state: ProcessUserInputState):
        """Route after analyzing uploaded files. Uses Send objects for all routing."""
        print("Debug: route_after_analyze_uploaded_files")
        # Check if LLM request a tool call
        latest_message = state["process_user_input_messages"][-1]
        if hasattr(latest_message, 'tool_calls') and latest_message.tool_calls:
            return [Send("clarification_tool_node", state)]
        
        # Check if all files are irrelevant - route to text analysis
        if state.get("all_files_irrelevant", False):
            # First clean up irrelevant files, then analyze text
            sends = []
            if state.get("irrelevant_files_path"):
                sends.append(Send("process_irrelevant", state))
            sends.append(Send("analyze_text_input", state))
            return sends
        
        # Some files are relevant - process them in parallel
        sends = []
        if state.get("uploaded_template_files_path"):
            print("Debug: process_template")
            sends.append(Send("process_template", state))
        if state.get("supplement_files_path", {}).get("表格") or state.get("supplement_files_path", {}).get("文档"):
            print("Debug: process_supplement")
            sends.append(Send("process_supplement", state))
        if state.get("irrelevant_files_path"):
            print("Debug: process_irrelevant")
            sends.append(Send("process_irrelevant", state))

        # The parallel nodes will automatically converge, then continue to analyze_text_input
        return sends if sends else [Send("analyze_text_input", state)]  # Fallback
    
    def _process_supplement(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will process the supplement files, it will analyze the supplement files and summarize the content of the files as well as stored the summary in data.json"""
        print("\n🔍 开始执行: _process_supplement")
        print("=" * 50)
        print("Debug: Start to process_supplement")
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Load existing data.json with better error handling
        data_json_path = Path("agents/data.json")
        try:
            with open(data_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print("📝 data.json不存在，创建空的数据结构")
            data = {}
        except json.JSONDecodeError as e:
            print(f"⚠️ data.json格式错误: {e}")
            print("📝 备份原文件并创建新的数据结构")
            # Backup the corrupted file
            backup_path = data_json_path.with_suffix('.json.backup')
            if data_json_path.exists():
                data_json_path.rename(backup_path)
                print(f"📦 原文件已备份到: {backup_path}")
            data = {}
        
        # Get available locations from existing data
        available_locations = get_available_locations(data)
        
        table_files = state["supplement_files_path"]["表格"]
        document_files = state["supplement_files_path"]["文档"]
        
        print(f"📊 需要处理的表格文件: {len(table_files)} 个")
        print(f"📄 需要处理的文档文件: {len(document_files)} 个")
        
        # Collect new messages instead of directly modifying state
        new_messages = []
        
        def process_table_file(table_file: str) -> tuple[str, str, dict]:
            """Process a single table file and return (file_path, file_type, result_data)"""
            try:
                source_path = Path(table_file)
                print(f"🔍 正在处理表格文件: {source_path.name}")
                
                file_content = source_path.read_text(encoding='utf-8')
                file_content = file_content[:2000] if len(file_content) > 2000 else file_content
                file_name = extract_filename(table_file)
                
                # Determine location for this file
                location = determine_location_from_content(
                    file_content, 
                    file_name, 
                    state.get("user_input", ""),
                    available_locations
                )
                
                # Define the JSON template separately to avoid f-string nesting issues
                json_template = '''{{
  "{file_name}": {{
    "表格结构": {{
      "顶层表头名称": {{
        "二级表头名称": [
          "字段1",
          "字段2",
          "..."
        ],
        "更多子表头": [
          "字段A",
          "字段B"
        ]
      }}
    }},
    "表格总结": "该表格的主要用途及内容说明..."
  }}
}}'''.format(file_name=file_name)

                system_prompt = f"""你是一位专业的文档分析专家。请阅读用户上传的 HTML 格式的 Excel 文件，并完成以下任务：

1. 提取表格的多级表头结构；
   - 使用嵌套的 key-value 形式表示层级关系；
   - 每一级表头应以对象形式展示其子级字段或子表头；
   - 不需要额外字段（如 null、isParent 等），仅保留结构清晰的层级映射；

2. 提供一个对该表格内容的简要总结；
   - 内容应包括表格用途、主要信息类别、适用范围等；
   - 语言简洁，不超过 150 字；

输出要求:
返回内容不要包裹在```json中，直接返回json格式即可

输出格式如下：
{json_template}

请忽略所有 HTML 样式标签，只关注表格结构和语义信息。

文件内容:
{file_content}"""

                print("📤 正在调用LLM进行表格分析...")
                
                try:
                    analysis_response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
                    print("📥 表格分析响应接收成功")
                except Exception as llm_error:
                    print(f"❌ LLM调用失败: {llm_error}")
                    # Create fallback response  
                    analysis_response = f"表格文件分析失败: {str(llm_error)}，文件名: {source_path.name}"
                
                # Create result data with location information
                # Note: file_path will be updated after moving to final destination
                result_data = {
                    "file_key": source_path.name,
                    "location": location,
                    "new_entry": {
                        "summary": analysis_response,
                        "file_path": str(table_file),  # This will be updated after moving
                        "original_file_path": str(source_path),  # This will be updated after moving
                        "timestamp": datetime.now().isoformat(),
                        "file_size": source_path.stat().st_size
                    },
                    "analysis_response": analysis_response
                }
                
                print(f"✅ 表格文件已分析: {source_path.name} (位置: {location})")
                return table_file, "table", result_data
                
            except Exception as e:
                print(f"❌ 处理表格文件出错 {table_file}: {e}")
                default_location = available_locations[0] if available_locations else "默认位置"
                return table_file, "table", {
                    "file_key": Path(table_file).name,
                    "location": default_location,  # Default location on error
                    "new_entry": {
                        "summary": f"表格文件处理失败: {str(e)}",
                        "file_path": str(table_file),
                        "timestamp": datetime.now().isoformat(),
                        "file_size": 0
                    },
                    "analysis_response": f"表格文件处理失败: {str(e)}"
                }

        def process_document_file(document_file: str) -> tuple[str, str, dict]:
            """Process a single document file and return (file_path, file_type, result_data)"""
            try:
                source_path = Path(document_file)
                print(f"🔍 正在处理文档文件: {source_path.name}")
                
                file_content = source_path.read_text(encoding='utf-8')
                file_content = file_content[:2000] if len(file_content) > 2000 else file_content
                file_name = extract_filename(document_file)
                
                # For document files, ask user to select location(s)
                if len(available_locations) == 0:
                    # If no locations exist, create a default one
                    selected_locations = ["默认位置"]
                    print(f"📍 没有可用位置，为文档文件创建默认位置: {selected_locations}")
                elif len(available_locations) == 1:
                    # If only one location exists, use it
                    selected_locations = [available_locations[0]]
                    print(f"📍 只有一个可用位置，文档文件使用: {selected_locations}")
                else:
                    # Multiple locations exist, ask user to choose
                    try:
                        locations_list = "\n".join([f"  {i+1}. {loc}" for i, loc in enumerate(available_locations)])
                        question = f"""检测到文档文件: {source_path.name}

📍 可选的存储位置：
{locations_list}

请选择要将此文档文件添加到哪个位置：
  • 输入序号（如：1, 2, 3）选择单个位置
  • 输入 "all" 添加到所有位置  
  • 输入 "new [位置名]" 创建新位置（如：new 石龙村）"""
                        
                        user_choice = self.request_user_clarification.invoke(
                            input = {"question": question,
                                     "context" : "文档文件可以添加到多个位置，请选择合适的存储位置"
                                    }
                            )
                
                        print(f"👤 用户选择: {user_choice}")
                        
                        # Parse user choice
                        choice = user_choice.strip().lower()
                        selected_locations = []
                        
                        if choice == "all":
                            selected_locations = available_locations.copy()
                            print(f"📍 用户选择添加到所有位置: {selected_locations}")
                        elif choice.startswith("new "):
                            new_location = choice[4:].strip()
                            if new_location:
                                selected_locations = [new_location]
                                print(f"📍 用户创建新位置: {new_location}")
                            else:
                                selected_locations = ["默认位置"]
                                print(f"⚠️ 新位置名称无效，使用默认位置: {selected_locations[0]}")
                        else:
                            # Parse numbers
                            try:
                                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                                selected_locations = [available_locations[i] for i in indices if 0 <= i < len(available_locations)]
                                if not selected_locations:
                                    selected_locations = [available_locations[0]]
                                print(f"📍 用户选择的位置: {selected_locations}")
                            except (ValueError, IndexError):
                                selected_locations = [available_locations[0]]
                                print(f"⚠️ 输入格式错误，使用默认位置: {available_locations[0]}")
                        
                        # Handle multiple selected locations
                        if not selected_locations:
                            selected_locations = ["默认位置"]
                        
                    except Exception as e:
                        print(f"❌ 用户选择过程出错: {e}")
                        selected_locations = ["默认位置"]
                        print(f"📍 使用默认位置: {selected_locations}")
                
                system_prompt = """你是一位专业的文档分析专家，具备法律与政策解读能力。你的任务是阅读用户提供的 HTML 格式文件，并从中提取出最重要的 1-2 条关键信息进行总结，无需提取全部内容。

请遵循以下要求：

1. 忽略所有 HTML 标签（如 <p>、<div>、<table> 等），只关注文本内容；

2. 从文件中提取你认为最重要的一到两项核心政策信息（例如补贴金额、适用对象、审批流程等），或者其他你觉得重要的信息，避免包含次要或重复内容；

3. 对提取的信息进行结构化总结，语言正式、逻辑清晰、简洁明了；

4. 输出格式为严格的 JSON，但不要包裹在```json中，直接返回json格式即可：
   {{
     "{file_name}": "内容总结"
   }}

5. 若提供多个文件，需分别处理并合并输出为一个 JSON 对象；

6. 输出语言应与输入文档保持一致（若文档为中文，则输出中文）；

请根据上述要求，对提供的 HTML 文件内容进行分析并返回结果。

文件内容:
{file_content}
""".format(file_name=file_name, file_content=file_content)

                print("📤 正在调用LLM进行文档分析...")
                
                try:
                    analysis_response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
                    print("📥 文档分析响应接收成功")
                except Exception as llm_error:
                    print(f"❌ LLM调用失败: {llm_error}")
                    # Create fallback response
                    analysis_response = f"文档文件分析失败: {str(llm_error)}，文件名: {source_path.name}"

                # Create result data with multiple location information
                # Note: file_path will be updated after moving to final destination
                result_data = {
                    "file_key": source_path.name,
                    "selected_locations": selected_locations,  # Multiple locations
                    "new_entry": {
                        "summary": analysis_response,
                        "file_path": str(document_file),  # This will be updated after moving
                        "original_file_path": str(source_path),  # This will be updated after moving
                        "timestamp": datetime.now().isoformat(),
                        "file_size": source_path.stat().st_size
                    },
                    "analysis_response": analysis_response
                }
                
                print(f"✅ 文档文件已分析: {source_path.name} (位置: {selected_locations})")
                return document_file, "document", result_data
                
            except Exception as e:
                print(f"❌ 处理文档文件出错 {document_file}: {e}")
                default_locations = [available_locations[0]] if available_locations else ["默认位置"]
                return document_file, "document", {
                    "file_key": Path(document_file).name,
                    "selected_locations": default_locations,  # Default locations on error
                    "new_entry": {
                        "summary": f"文档文件处理失败: {str(e)}",
                        "file_path": str(document_file),
                        "timestamp": datetime.now().isoformat(),
                        "file_size": 0
                    },
                    "analysis_response": f"文档文件处理失败: {str(e)}"
                }

        # Use ThreadPoolExecutor for parallel processing
        all_files = [(file, "table") for file in table_files] + [(file, "document") for file in document_files]
        total_files = len(all_files)
        
        if total_files == 0:
            print("⚠️ 没有文件需要处理")
            print("✅ _process_supplement 执行完成")
            print("=" * 50)
            return {"process_user_input_messages": new_messages}
        
        max_workers = min(total_files, 5)  # Limit to 4 concurrent requests for supplement processing
        print(f"🚀 开始并行处理补充文件，使用 {max_workers} 个工作线程")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all file processing tasks
            future_to_file = {}
            for file_path, file_type in all_files:
                if file_type == "table":
                    future = executor.submit(process_table_file, file_path)
                else:  # document
                    future = executor.submit(process_document_file, file_path)
                future_to_file[future] = (file_path, file_type)
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_file):
                file_path, file_type = future_to_file[future]
                try:
                    processed_file_path, processed_file_type, result_data = future.result()
                    
                    # Add to new_messages
                    new_messages.append(AIMessage(content=result_data["analysis_response"]))
                    
                    # Update data.json structure with location-based storage
                    file_key = result_data["file_key"]
                    new_entry = result_data["new_entry"]
                    
                    if processed_file_type == "table":
                        # Table files have single location
                        location = result_data["location"]
                        # Ensure location structure exists in data
                        data = ensure_location_structure(data, location)
                        
                        if file_key in data[location]["表格"]:
                            print(f"⚠️ 表格文件 {file_key} 已存在于 {location}，将更新其内容")
                            # Preserve any additional fields that might exist
                            existing_entry = data[location]["表格"][file_key]
                            for key, value in existing_entry.items():
                                if key not in new_entry:
                                    new_entry[key] = value
                        else:
                            print(f"📝 添加新的表格文件: {file_key} 到 {location}")
                        data[location]["表格"][file_key] = new_entry
                    else:  # document - can have multiple locations
                        selected_locations = result_data["selected_locations"]
                        for location in selected_locations:
                            # Ensure location structure exists in data
                            data = ensure_location_structure(data, location)
                            
                            # Create a copy of new_entry for each location
                            entry_copy = new_entry.copy()
                            
                            if file_key in data[location]["文档"]:
                                print(f"⚠️ 文档文件 {file_key} 已存在于 {location}，将更新其内容")
                                # Preserve any additional fields that might exist
                                existing_entry = data[location]["文档"][file_key]
                                for key, value in existing_entry.items():
                                    if key not in entry_copy:
                                        entry_copy[key] = value
                            else:
                                print(f"📝 添加新的文档文件: {file_key} 到 {location}")
                            data[location]["文档"][file_key] = entry_copy
                    
                except Exception as e:
                    print(f"❌ 并行处理文件任务失败 {file_path}: {e}")
                    # Create fallback entry
                    fallback_response = f"文件处理失败: {str(e)}"
                    new_messages.append(AIMessage(content=fallback_response))
        
        print(f"🎉 并行文件处理完成，共处理 {total_files} 个文件")
        
        # Move supplement files to their final destinations and update data.json with new paths
        original_files = state.get("original_files_path", [])
        
        # Track moved files to update data.json paths
        moved_files_info = {}
        
        # Move table files to their final destination
        for table_file in table_files:
            # Find corresponding original file
            table_file_stem = Path(table_file).stem
            corresponding_original_file = ""
            
            for original_file in original_files:
                if Path(original_file).stem == table_file_stem:
                    corresponding_original_file = original_file
                    break
            
            try:
                move_result = move_supplement_files_to_final_destination(
                    table_file, corresponding_original_file, "table"
                )
                print(f"✅ 表格文件已移动到最终位置: {Path(table_file).name}")
                
                # Store moved file info for later data.json update
                moved_files_info[Path(table_file).name] = {
                    "new_processed_path": move_result["processed_supplement_path"],
                    "new_original_path": move_result["original_supplement_path"]
                }
            except Exception as e:
                print(f"❌ 移动表格文件失败 {table_file}: {e}")
        
        # Move document files to their final destination
        for document_file in document_files:
            # Find corresponding original file
            document_file_stem = Path(document_file).stem
            corresponding_original_file = ""
            
            for original_file in original_files:
                if Path(original_file).stem == document_file_stem:
                    corresponding_original_file = original_file
                    break
            
            try:
                move_result = move_supplement_files_to_final_destination(
                    document_file, corresponding_original_file, "document"
                )
                print(f"✅ 文档文件已移动到最终位置: {Path(document_file).name}")
                
                # Store moved file info for later data.json update
                moved_files_info[Path(document_file).name] = {
                    "new_processed_path": move_result["processed_supplement_path"],
                    "new_original_path": move_result["original_supplement_path"]
                }
            except Exception as e:
                print(f"❌ 移动文档文件失败 {document_file}: {e}")
        
        # Update data.json entries with new file paths
        for location in data.keys():
            if isinstance(data[location], dict):
                # Update table file paths
                for file_key in data[location].get("表格", {}):
                    if file_key in moved_files_info:
                        if moved_files_info[file_key]["new_processed_path"]:
                            data[location]["表格"][file_key]["file_path"] = moved_files_info[file_key]["new_processed_path"]
                        if moved_files_info[file_key]["new_original_path"]:
                            data[location]["表格"][file_key]["original_file_path"] = moved_files_info[file_key]["new_original_path"]
                
                # Update document file paths
                for file_key in data[location].get("文档", {}):
                    if file_key in moved_files_info:
                        if moved_files_info[file_key]["new_processed_path"]:
                            data[location]["文档"][file_key]["file_path"] = moved_files_info[file_key]["new_processed_path"]
                        if moved_files_info[file_key]["new_original_path"]:
                            data[location]["文档"][file_key]["original_file_path"] = moved_files_info[file_key]["new_original_path"]
        
        # Save updated data.json with atomic write
        try:
            # Write to a temporary file first to prevent corruption
            temp_path = data_json_path.with_suffix('.json.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            # Atomic rename to replace the original file
            temp_path.replace(data_json_path)
            
            # Count total files across all locations
            total_table_files = sum(len(data[location]["表格"]) for location in data.keys() if isinstance(data[location], dict))
            total_document_files = sum(len(data[location]["文档"]) for location in data.keys() if isinstance(data[location], dict))
            
            print(f"✅ 已更新 data.json，表格文件 {total_table_files} 个，文档文件 {total_document_files} 个")
            
            # Log the files that were processed in this batch
            if table_files:
                print(f"📊 本批次处理的表格文件: {[Path(f).name for f in table_files]}")
            if document_files:
                print(f"📄 本批次处理的文档文件: {[Path(f).name for f in document_files]}")
            
            # Log current distribution by location
            print("📍 当前数据分布:")
            for location in data.keys():
                if isinstance(data[location], dict):
                    table_count = len(data[location]["表格"])
                    doc_count = len(data[location]["文档"])
                    print(f"  {location}: 表格 {table_count} 个, 文档 {doc_count} 个")
                
        except Exception as e:
            print(f"❌ 保存 data.json 时出错: {e}")
            # Clean up temp file if it exists
            temp_path = data_json_path.with_suffix('.json.tmp')
            if temp_path.exists():
                try:
                    temp_path.unlink()
                    print("🗑️ 临时文件已清理")
                except Exception as cleanup_error:
                    print(f"⚠️ 清理临时文件失败: {cleanup_error}")
        
        print("✅ _process_supplement 执行完成")
        print("=" * 50)
        
        # Return the collected messages for proper state update
        return {"process_user_input_messages": new_messages}
        
        
    def _process_irrelevant(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will process the irrelevant files, it will delete the irrelevant files (both processed and original) from the staging area"""
        
        print("\n🔍 开始执行: _process_irrelevant")
        print("=" * 50)
        
        irrelevant_files = state["irrelevant_files_path"]
        irrelevant_original_files = state.get("irrelevant_original_files_path", [])
        
        print(f"🗑️ 需要删除的无关处理文件数量: {len(irrelevant_files)}")
        print(f"🗑️ 需要删除的无关原始文件数量: {len(irrelevant_original_files)}")
        
        # Combine all files to delete
        all_files_to_delete = irrelevant_files + irrelevant_original_files
        
        if all_files_to_delete:
            delete_result = delete_files_from_staging_area(all_files_to_delete)
            
            deleted_count = len(delete_result["deleted_files"])
            failed_count = len(delete_result["failed_deletes"])
            
            print(f"📊 删除结果: 成功 {deleted_count} 个，失败 {failed_count} 个 (总计 {len(all_files_to_delete)} 个文件)")
            
            if delete_result["failed_deletes"]:
                print("❌ 删除失败的文件:")
                for failed_file in delete_result["failed_deletes"]:
                    print(f"  - {failed_file}")
        else:
            print("⚠️ 没有无关文件需要删除")
        
        print("✅ _process_irrelevant 执行完成")
        print("=" * 50)
        
        return {}  # Return empty dict since this node doesn't need to update any state keys

    
    def _process_template(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will process the template files, it will analyze the template files and determine if it's a valid template"""
        
        print("\n🔍 开始执行: _process_template")
        print("=" * 50)
        
        template_files = state["uploaded_template_files_path"]
        print(f"📋 需要处理的模板文件数量: {len(template_files)}")
        
        # If multiple templates, ask user to choose
        if len(template_files) > 1:
            print("⚠️ 检测到多个模板文件，需要用户选择")
            template_names = [Path(f).name for f in template_files]
            template_list = "\n".join([f"  {i+1}. {name}" for i, name in enumerate(template_names)])
            question = f"""检测到多个模板文件，请选择要使用的模板：

📋 可用模板：
{template_list}

请输入序号（如：1）选择模板："""
            
            try:
                print("🤝 正在请求用户确认模板选择...")
                user_choice = self.request_user_clarification.invoke(
                    input = {"question": question,
                             "context": "系统需要确定使用哪个模板文件进行后续处理"}
                    )
                
                # Parse user choice
                try:
                    choice_index = int(user_choice.strip()) - 1
                    if 0 <= choice_index < len(template_files):
                        selected_template = template_files[choice_index]
                        # Remove non-selected templates
                        rejected_templates = [f for i, f in enumerate(template_files) if i != choice_index]
                        
                        # Delete rejected template files (both processed and original)
                        original_files = state.get("original_files_path", [])
                        for rejected_file in rejected_templates:
                            try:
                                # Delete processed template file
                                Path(rejected_file).unlink()
                                print(f"🗑️ 已删除未选中的处理模板: {Path(rejected_file).name}")
                                
                                # Find and delete corresponding original file
                                rejected_file_stem = Path(rejected_file).stem
                                for original_file in original_files:
                                    original_file_path = Path(original_file)
                                    if original_file_path.stem == rejected_file_stem:
                                        try:
                                            original_file_path.unlink()
                                            print(f"🗑️ 已删除未选中的原始模板: {original_file_path.name}")
                                            break
                                        except Exception as orig_error:
                                            print(f"❌ 删除原始模板文件出错: {orig_error}")
                                
                            except Exception as e:
                                print(f"❌ 删除模板文件出错: {e}")
                        
                        # Update state to only include selected template
                        template_files = [selected_template]
                        print(f"✅ 用户选择了模板: {Path(selected_template).name}")
                        
                    else:
                        print("❌ 无效的选择，使用第一个模板")
                        selected_template = template_files[0]
                        template_files = [selected_template]
                        
                except ValueError:
                    print("❌ 输入格式错误，使用第一个模板")
                    selected_template = template_files[0]
                    template_files = [selected_template]
                    
            except Exception as e:
                print(f"❌ 用户选择出错: {e}")
                selected_template = template_files[0]
                template_files = [selected_template]
        
        # Analyze the selected template for complexity
        template_file = template_files[0]
        print(f"🔍 正在分析模板复杂度: {Path(template_file).name}")
        
        try:
            source_path = Path(template_file)
            template_content = source_path.read_text(encoding='utf-8')
            
            # Create prompt to determine if template is complex or simple
            system_prompt = f"""你是一个表格结构分析专家，需要判断这个表格模板是复杂模板还是简单模板。

            判断标准：
            - **复杂模板**: 表格同时包含行表头和列表头，即既有行标题又有列标题的二维表格结构
            - **简单模板**: 表格只包含列表头或者只包含行表头，但是可以是多级表头，每行是独立的数据记录

            模板内容（HTML格式）：
            {template_content}

            请仔细分析表格结构，然后只回复以下选项之一：
            [Complex] - 如果是复杂模板（包含行表头和列表头）
            [Simple] - 如果是简单模板（只包含列表头）"""
            

            print("📤 正在调用LLM进行模板复杂度分析...")
            
            analysis_response = invoke_model(model_name="Pro/deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
            
            # Extract the classification from the response
            if "[Complex]" in analysis_response:
                template_type = "[Complex]"
            elif "[Simple]" in analysis_response:
                template_type = "[Simple]"
            else:
                template_type = "[Simple]"  # Default fallback
            
            # 将模板文件（包括原始文件）移动到最终位置
            # Find corresponding original file
            original_files = state.get("original_files_path", [])
            template_file_stem = Path(template_file).stem
            corresponding_original_file = ""
            
            for original_file in original_files:
                if Path(original_file).stem == template_file_stem:
                    corresponding_original_file = original_file
                    break
            
            # Move template files to final destination using session ID
            # Extract session ID from one of the file paths
            session_id = "files"  # Default session ID
            if template_file:
                # Extract session ID from the file path: conversations/session_id/user_uploaded_files/...
                template_path_parts = Path(template_file).parts
                if len(template_path_parts) >= 3 and template_path_parts[0] == "conversations":
                    session_id = template_path_parts[1]
            
            move_result = move_template_files_to_final_destination(
                template_file, corresponding_original_file, session_id
            )
            final_template_path = move_result["processed_template_path"]
            
            if move_result["original_template_path"]:
                print(f"📁 模板原始文件已移动到: {move_result['original_template_path']}")
            else:
                print("⚠️ 未找到对应的原始模板文件")

            print(f"📥 模板分析结果: {template_type}")
            print("✅ _process_template 执行完成")
            print("=" * 50)

            return {"template_complexity": template_type,
                    "uploaded_template_files_path": [final_template_path]
                    }

        except Exception as e:
            print(f"❌ 模板分析LLM调用出错: {e}")
            # Default to Simple if analysis fails
            template_type = "[Simple]"
            print("⚠️ 模板分析失败，默认为简单模板")
            
            # Still try to move the template file (including original) even if LLM analysis fails
            original_files = state.get("original_files_path", [])
            template_file_stem = Path(template_file).stem
            corresponding_original_file = ""
            
            for original_file in original_files:
                if Path(original_file).stem == template_file_stem:
                    corresponding_original_file = original_file
                    break
            
            # Extract session ID from file path
            session_id = "files"  # Default session ID
            if template_file:
                template_path_parts = Path(template_file).parts
                if len(template_path_parts) >= 3 and template_path_parts[0] == "conversations":
                    session_id = template_path_parts[1]
            
            move_result = move_template_files_to_final_destination(
                template_file, corresponding_original_file, session_id
            )
            final_template_path = move_result["processed_template_path"]
            
            if move_result["original_template_path"]:
                print(f"📁 模板原始文件已移动到: {move_result['original_template_path']}")
            else:
                print("⚠️ 未找到对应的原始模板文件")
            
            print("✅ _process_template 执行完成")
            print("=" * 50)
            
            return {
                "template_complexity": template_type,
                "uploaded_template_files_path": [final_template_path]
            }
        


    def _analyze_text_input(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node performs a safety check on user text input when all uploaded files are irrelevant.
        It validates if the user input contains meaningful table/Excel-related content.
        Returns [Valid] or [Invalid] based on the analysis."""
        
        print("\n🔍 开始执行: _analyze_text_input")
        print("=" * 50)
        
        user_input = state["user_input"]
        print(f"📝 正在分析用户文本输入: {user_input[:100]}{'...' if len(user_input) > 100 else ''}")
        
        if not user_input or user_input.strip() == "":
            print("❌ 用户输入为空")
            print("✅ _analyze_text_input 执行完成")
            print("=" * 50)
            return {
                "text_input_validation": "[Invalid]",
                "process_user_input_messages": [SystemMessage(content="❌ 用户输入为空，验证失败")]
            }
        
        # Create validation prompt for text input safety check
        # Get the previous AI message content safely
        previous_ai_content = ""
        try:
            if state.get("previous_AI_messages"):
                previous_ai_messages = state["previous_AI_messages"]
                print(f"🔍 previous_AI_messages 类型: {type(previous_ai_messages)}")
                
                # Handle both single message and list of messages
                if isinstance(previous_ai_messages, list):
                    if len(previous_ai_messages) > 0:
                        latest_message = previous_ai_messages[-1]
                        if hasattr(latest_message, 'content'):
                            previous_ai_content = latest_message.content
                        else:
                            previous_ai_content = str(latest_message)
                        print(f"📝 从消息列表提取内容，长度: {len(previous_ai_content)}")
                    else:
                        print("⚠️ 消息列表为空")
                else:
                    # It's a single message object
                    if hasattr(previous_ai_messages, 'content'):
                        previous_ai_content = previous_ai_messages.content
                    else:
                        previous_ai_content = str(previous_ai_messages)
                    print(f"📝 从单个消息提取内容，长度: {len(previous_ai_content)}")
            else:
                print("⚠️ 没有找到previous_AI_messages")
                
        except Exception as e:
            print(f"❌ 提取previous_AI_messages内容时出错: {e}")
            previous_ai_content = ""
            
        print(f"上一轮ai输入内容：=========================================\n{previous_ai_content}")
        system_prompt = f"""
你是一位专业的输入验证专家，任务是判断用户的文本输入是否与**表格生成或 Excel 处理相关**，并且是否在当前对话上下文中具有实际意义。

你将获得以下两部分信息：
- 上一轮 AI 的回复（用于判断上下文是否连贯）
- 当前用户的输入内容

请根据以下标准进行判断：

【有效输入 [Valid]】满足以下任一条件即可视为有效：
- 明确提到生成表格、填写表格、Excel 处理、数据整理等相关操作
- 提出关于表格字段、数据格式、模板结构等方面的需求或提问
- 提供表格相关的数据内容、字段说明或规则
- 对上一轮 AI 的回复作出有意义的延续或回应（即使未直接提到表格）
- 即使存在错别字、语病、拼写错误，只要语义清晰合理，也视为有效

【无效输入 [Invalid]】符合以下任一情况即视为无效：
- 内容与表格/Excel 完全无关（如闲聊、情绪表达、与上下文跳脱）
- 明显为测试文本、随机字符或系统调试输入（如 “123”、“测试一下”、“哈啊啊啊” 等）
- 仅包含空白、表情符号、标点符号等无实际内容

【输出要求】
请你根据上述标准，**仅输出以下两种结果之一**（不添加任何其他内容）：
- [Valid]
- [Invalid]

【上一轮 AI 的回复】
{previous_ai_content}
"""



        
        try:
            print("📤 正在调用LLM进行文本输入验证...")
            # Get LLM validation
            user_input = "用户输入：" + user_input
            print("analyze_text_input时调用模型的输入: \n" + user_input)              
            validation_response = invoke_model(model_name="Pro/deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
            # validation_response = self.llm_s.invoke([SystemMessage(content=system_prompt)])
            
            print(f"📥 验证响应: {validation_response}")
            
            if "[Valid]" in validation_response:
                validation_result = "[Valid]"
                status_message = "用户输入验证通过 - 内容与表格相关且有意义"
            elif "[Invalid]" in validation_response:
                validation_result = "[Invalid]"
                status_message = "用户输入验证失败 - 内容与表格无关或无意义"
            else:
                # Default to Invalid for safety
                validation_result = "[Invalid]"
                status_message = "用户输入验证失败 - 无法确定输入有效性，默认为无效"
                print(f"⚠️ 无法解析验证结果，LLM响应: {validation_response}")
            
            print(f"📊 验证结果: {validation_result}")
            print(f"📋 状态说明: {status_message}")
            
            # Create validation summary
            summary_message = f"""文本输入安全检查完成:
            
            **用户输入**: {user_input[:100]}{'...' if len(user_input) > 100 else ''}
            **验证结果**: {validation_result}
            **状态**: {status_message}"""
            
            print("✅ _analyze_text_input 执行完成")
            print("=" * 50)
            
            return {
                "text_input_validation": validation_result,
                "process_user_input_messages": [SystemMessage(content=summary_message)]
            }
                
        except Exception as e:
            print(f"❌ 验证文本输入时出错: {e}")
            
            # Default to Invalid for safety when there's an error
            error_message = f"""❌ 文本输入验证出错: {e}
            
            📄 **用户输入**: {user_input[:100]}{'...' if len(user_input) > 100 else ''}
            🔒 **安全措施**: 默认标记为无效输入"""
            
            print("✅ _analyze_text_input 执行完成 (出错)")
            print("=" * 50)
            
            return {
                "text_input_validation": "[Invalid]",
                "process_user_input_messages": [SystemMessage(content=error_message)]
            }



    def _route_after_analyze_text_input(self, state: ProcessUserInputState) -> str:
        """Route after text input validation based on [Valid] or [Invalid] result."""
        
        validation_result = state.get("text_input_validation", "[Invalid]")
        
        if validation_result == "[Valid]":
            # Text input is valid and table-related, proceed to summary
            return "valid_text_input"
        else:
            # Text input is invalid, route back to collect user input
            return "invalid_text_input"
        

    
    def _summary_user_input(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """Summary node that consolidates all information from this round and determines next routing."""
        
        print("\n🔍 开始执行: _summary_user_input")
        print("=" * 50)
        
        print(f"🔄 开始总结用户输入，当前消息数: {len(state.get('process_user_input_messages', []))}")
        
        # Extract content from all messages in this processing round
        process_user_input_messages_content =("\n").join([item.content for item in state["process_user_input_messages"]])
        print(f"📝 处理的消息内容长度: {len(process_user_input_messages_content)} 字符")
        
        # Determine route decision based on template complexity (with proper parsing)
        template_complexity = state.get("template_complexity", "")
        print(f"🔍 原始模板复杂度: {repr(template_complexity)}")
        template_complexity = template_complexity.strip()
        print(f"🔍 清理后模板复杂度: '{template_complexity}'")
        
        if "[Complex]" in template_complexity:
            route_decision = "complex_template"
        elif "[Simple]" in template_complexity:
            route_decision = "simple_template"
        else:
            route_decision = "previous_node"
        
        print(f"🎯 路由决定: {route_decision}")
        
        system_prompt = f"""
你是一位专业的用户输入分析专家，任务是根据当前轮次的历史对话内容，总结用户在信息收集过程中的所有有效输入。

【你的目标】
- 提取本轮对话中用户提供的所有有价值信息，包括但不限于：
  - 文件上传（如数据文件、模板文件等）；
  - 文本输入（如填写说明、政策信息、计算规则等）；
  - 对召回文件的判断（例如用户确认某些文件是否相关）；
- 注意：有时你被作为“确认节点”调用，任务是让用户判断文件是否相关，此时你需要总结的是“用户的判断结果”，而不是文件本身。
- 请基于上下文灵活判断哪些内容构成有价值的信息。
- 总结中请不要包含用户上传的无关信息内容，以及有效性验证
- 但是一定不要忽略曲解用户的意图

【输出格式】
仅返回以下 JSON 对象，不得包含任何额外解释或文本,不要包裹在```json中，直接返回json格式即可：
{{
  "summary": "对本轮用户提供的信息进行总结"
}}
"""


        try:
            user_input = "【历史对话】\n" + process_user_input_messages_content
            print("📤 正在调用LLM生成总结...")
            response = invoke_model(model_name="Pro/deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
            print(f"📥 LLM总结响应长度: {len(response)} 字符")
            
            # Clean the response to handle markdown code blocks and malformed JSON
            cleaned_response = response.strip()
            
            # Remove markdown code blocks if present
            if '```json' in cleaned_response:
                print("🔍 检测到markdown代码块，正在清理...")
                # Extract content between ```json and ```
                start_marker = '```json'
                end_marker = '```'
                start_index = cleaned_response.find(start_marker)
                if start_index != -1:
                    start_index += len(start_marker)
                    end_index = cleaned_response.find(end_marker, start_index)
                    if end_index != -1:
                        cleaned_response = cleaned_response[start_index:end_index].strip()
                    else:
                        # If no closing ```, take everything after ```json
                        cleaned_response = cleaned_response[start_index:].strip()
            elif '```' in cleaned_response:
                print("🔍 检测到通用代码块，正在清理...")
                # Handle generic ``` blocks
                parts = cleaned_response.split('```')
                if len(parts) >= 3:
                    # Take the middle part (index 1)
                    cleaned_response = parts[1].strip()
            
            # If there are multiple JSON objects, take the first valid one
            if '}{' in cleaned_response:
                print("⚠️ 检测到多个JSON对象，取第一个")
                cleaned_response = cleaned_response.split('}{')[0] + '}'
            
            print(f"🔍 清理后的响应: {cleaned_response}")
            
            response_json = json.loads(cleaned_response)
            response_json["next_node"] = route_decision
            final_response = json.dumps(response_json, ensure_ascii=False)
            
            print(f"✅ 总结生成成功")
            print(f"📊 最终响应: {final_response}")
            print("✅ _summary_user_input 执行完成")
            print("=" * 50)
            
            return {"summary_message": final_response}
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析错误: {e}")
            print(f"❌ 原始响应: {repr(response)}")
            # Fallback response
            fallback_response = {
                "summary": "用户本轮提供了文件信息，但解析过程中出现错误",
                "next_node": route_decision
            }
            final_fallback = json.dumps(fallback_response, ensure_ascii=False)
            print(f"🔄 使用备用响应: {final_fallback}")
            print("✅ _summary_user_input 执行完成 (备用)")
            print("=" * 50)
            return {"summary_message": final_fallback}



    def run_process_user_input_agent(self, session_id: str = "1", previous_AI_messages: BaseMessage = None) -> List:
        """This function runs the process user input agent using invoke method instead of streaming"""
        print("\n🚀 开始运行 ProcessUserInputAgent")
        print("=" * 60)
        
        initial_state = self.create_initial_state(previous_AI_messages)
        config = {"configurable": {"thread_id": session_id}}
        
        print(f"📋 会话ID: {session_id}")
        print(f"📝 初始状态已创建")
        print("🔄 正在执行用户输入处理工作流...")
        
        try:
            # Use invoke instead of stream for simpler execution
            while True:
                final_state = self.graph.invoke(initial_state, config=config)
                if "__interrupt__" in final_state:
                    interrupt_value = final_state["__interrupt__"][0].value
                    print(f"💬 智能体: {interrupt_value}")
                    user_response = input("👤 请输入您的回复: ")
                    initial_state = Command(resume=user_response)
                    continue

                print("🎉执行完毕")
                summary_message = final_state.get("summary_message", "")
                template_file = final_state.get("uploaded_template_files_path", [])
                return [summary_message, template_file]
            
        except Exception as e:
            print(f"❌ 执行过程中发生错误: {e}")
            # Return empty results on error
            error_summary = json.dumps({
                "summary": f"处理用户输入时发生错误: {str(e)}",
                "next_node": "previous_node"
            }, ensure_ascii=False)
            return [error_summary, []]



# Langgraph studio to export the compiled graph
agent = ProcessUserInputAgent()
graph = agent.graph


if __name__ == "__main__":
    agent = ProcessUserInputAgent()
    # save_graph_visualization(agent.graph, "process_user_input_graph.png")
    agent.run_process_user_input_agent("")