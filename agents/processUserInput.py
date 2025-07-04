import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content, extract_filename
from utilities.modelRelated import invoke_model

import uuid
import json
import os
from pathlib import Path
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
    uploaded_template_files_path: list[str]
    supplement_files_path: dict[str, list[str]]
    irrelevant_files_path: list[str]
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
            contexnt: 可选补充内容，解释为甚恶魔你需要一下信息
        """
        prompt = f"{question}\n{context}"
        user_response = interrupt({"prompt": prompt})

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
        graph.add_node("clarification_tool_node", ToolNode(self.tools))
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



    def create_initial_state(self, previous_AI_messages: list[BaseMessage] = None) -> ProcessUserInputState:
        """This function initializes the state of the process user input agent"""
        return {
            "process_user_input_messages": [],
            "user_input": "",
            "upload_files_path": [],
            "new_upload_files_path": [],
            "new_upload_files_processed_path": [],
            "uploaded_template_files_path": [],
            "supplement_files_path": {"表格": [], "文档": []},
            "irrelevant_files_path": [],
            "all_files_irrelevant": False,
            "text_input_validation": None,
            "previous_AI_messages": previous_AI_messages,
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
            data = {"表格": {}, "文档": {}}
        
        print("🔍 正在检查文件是否已存在...")
        for file in detected_files:
            file_name = Path(file).name
            if file_name in data["表格"] or file_name in data["文档"]:
                detected_files.remove(file)
                print(f"⚠️ 文件 {file} 已存在")
        
        if not detected_files:
            print("⚠️ 没有新文件需要上传")
            print("✅ _file_upload 执行完成")
            print("=" * 50)
            return {
                "new_upload_files_path": [],
                "new_upload_files_processed_path": []
            }
        
        print(f"🔄 正在处理 {len(detected_files)} 个新文件...")
        
        # Process the files using the correct session_id
        result = retrieve_file_content(detected_files, "files")
        
        print(f"✅ 文件上传完成: {result}")
        print("✅ _file_upload 执行完成")
        print("=" * 50)
        
        # Update state with new files
        # Safely handle the case where upload_files_path might not exist in state
        existing_files = state.get("upload_files_path", [])
        return {
            "new_upload_files_path": detected_files,
            "upload_files_path": existing_files + detected_files,
            "new_upload_files_processed_path": result
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

                请严格按照以下JSON格式回复，只返回这一个文件的分类结果（不要添加任何其他文字）：
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
                # Ensure the structure exists
                if "表格" not in data:
                    data["表格"] = {}
                if "文档" not in data:
                    data["文档"] = {}
        except FileNotFoundError:
            print("📝 data.json不存在，创建新的数据结构")
            data = {"表格": {}, "文档": {}}
        except json.JSONDecodeError as e:
            print(f"⚠️ data.json格式错误: {e}")
            print("📝 备份原文件并创建新的数据结构")
            # Backup the corrupted file
            backup_path = data_json_path.with_suffix('.json.backup')
            if data_json_path.exists():
                data_json_path.rename(backup_path)
                print(f"📦 原文件已备份到: {backup_path}")
            data = {"表格": {}, "文档": {}}
        
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
                
                # Create result data
                result_data = {
                    "file_key": source_path.name,
                    "new_entry": {
                        "summary": analysis_response,
                        "file_path": str(table_file),
                        "timestamp": datetime.now().isoformat(),
                        "file_size": source_path.stat().st_size
                    },
                    "analysis_response": analysis_response
                }
                
                print(f"✅ 表格文件已分析: {source_path.name}")
                return table_file, "table", result_data
                
            except Exception as e:
                print(f"❌ 处理表格文件出错 {table_file}: {e}")
                return table_file, "table", {
                    "file_key": Path(table_file).name,
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
                
                system_prompt = """你是一位专业的文档分析专家，具备法律与政策解读能力。你的任务是阅读用户提供的 HTML 格式文件，并从中提取出最重要的 1-2 条关键信息进行总结，无需提取全部内容。

请遵循以下要求：

1. 忽略所有 HTML 标签（如 <p>、<div>、<table> 等），只关注文本内容；

2. 从文件中提取你认为最重要的一到两项核心政策信息（例如补贴金额、适用对象、审批流程等），或者其他你觉得重要的信息，避免包含次要或重复内容；

3. 对提取的信息进行结构化总结，语言正式、逻辑清晰、简洁明了；

4. 输出格式为严格的 JSON：
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

                # Create result data
                result_data = {
                    "file_key": source_path.name,
                    "new_entry": {
                        "summary": analysis_response,
                        "file_path": str(document_file),
                        "timestamp": datetime.now().isoformat(),
                        "file_size": source_path.stat().st_size
                    },
                    "analysis_response": analysis_response
                }
                
                print(f"✅ 文档文件已分析: {source_path.name}")
                return document_file, "document", result_data
                
            except Exception as e:
                print(f"❌ 处理文档文件出错 {document_file}: {e}")
                return document_file, "document", {
                    "file_key": Path(document_file).name,
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
        
        max_workers = min(total_files, 4)  # Limit to 4 concurrent requests for supplement processing
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
                    
                    # Update data.json structure
                    file_key = result_data["file_key"]
                    new_entry = result_data["new_entry"]
                    
                    if processed_file_type == "table":
                        if file_key in data["表格"]:
                            print(f"⚠️ 表格文件 {file_key} 已存在，将更新其内容")
                            # Preserve any additional fields that might exist
                            existing_entry = data["表格"][file_key]
                            for key, value in existing_entry.items():
                                if key not in new_entry:
                                    new_entry[key] = value
                        else:
                            print(f"📝 添加新的表格文件: {file_key}")
                        data["表格"][file_key] = new_entry
                    else:  # document
                        if file_key in data["文档"]:
                            print(f"⚠️ 文档文件 {file_key} 已存在，将更新其内容")
                            # Preserve any additional fields that might exist
                            existing_entry = data["文档"][file_key]
                            for key, value in existing_entry.items():
                                if key not in new_entry:
                                    new_entry[key] = value
                        else:
                            print(f"📝 添加新的文档文件: {file_key}")
                        data["文档"][file_key] = new_entry
                    
                except Exception as e:
                    print(f"❌ 并行处理文件任务失败 {file_path}: {e}")
                    # Create fallback entry
                    fallback_response = f"文件处理失败: {str(e)}"
                    new_messages.append(AIMessage(content=fallback_response))
        
        print(f"🎉 并行文件处理完成，共处理 {total_files} 个文件")
        
        # Save updated data.json with atomic write
        try:
            # Write to a temporary file first to prevent corruption
            temp_path = data_json_path.with_suffix('.json.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            # Atomic rename to replace the original file
            temp_path.replace(data_json_path)
            print(f"✅ 已更新 data.json，表格文件 {len(data['表格'])} 个，文档文件 {len(data['文档'])} 个")
            
            # Log the files that were processed in this batch
            if table_files:
                print(f"📊 本批次处理的表格文件: {[Path(f).name for f in table_files]}")
            if document_files:
                print(f"📄 本批次处理的文档文件: {[Path(f).name for f in document_files]}")
                
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
        """This node will process the irrelevant files, it will delete the irrelevant files from the conversations folder"""
        
        print("\n🔍 开始执行: _process_irrelevant")
        print("=" * 50)
        
        irrelevant_files = state["irrelevant_files_path"]
        print(f"🗑️ 需要删除的无关文件数量: {len(irrelevant_files)}")
        
        deleted_files = []
        failed_deletes = []
        
        for file_path in irrelevant_files:
            try:
                file_to_delete = Path(file_path)
                print(f"🗑️ 正在删除: {file_to_delete.name}")
                
                if file_to_delete.exists():
                    os.remove(file_to_delete)
                    deleted_files.append(file_to_delete.name)
                    print(f"✅ 已删除无关文件: {file_to_delete.name}")
                else:
                    print(f"⚠️ 文件不存在，跳过删除: {file_path}")
                    
            except Exception as e:
                failed_deletes.append(Path(file_path).name)
                print(f"❌ 删除文件时出错 {file_path}: {e}")

        print(f"📊 删除结果: 成功 {len(deleted_files)} 个，失败 {len(failed_deletes)} 个")
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
            question = f"检测到多个模板文件，请选择要使用的模板：\n" + \
                      "\n".join([f"{i+1}. {name}" for i, name in enumerate(template_names)]) + \
                      "\n请输入序号（如：1）："
            
            try:
                print("🤝 正在请求用户确认模板选择...")
                user_choice = self.request_user_clarification(question, "系统需要确定使用哪个模板文件进行后续处理")
                
                # Parse user choice
                try:
                    choice_index = int(user_choice.strip()) - 1
                    if 0 <= choice_index < len(template_files):
                        selected_template = template_files[choice_index]
                        # Remove non-selected templates
                        rejected_templates = [f for i, f in enumerate(template_files) if i != choice_index]
                        
                        # Delete rejected template files
                        for rejected_file in rejected_templates:
                            try:
                                Path(rejected_file).unlink()
                                print(f"🗑️ 已删除未选中的模板: {Path(rejected_file).name}")
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
            
            analysis_response = invoke_model(model_name="Qwen/Qwen3-32B", messages=[SystemMessage(content=system_prompt)])
            
            # Extract the classification from the response
            if "[Complex]" in analysis_response:
                template_type = "[Complex]"
            elif "[Simple]" in analysis_response:
                template_type = "[Simple]"
            else:
                template_type = "[Simple]"  # Default fallback
                
            print(f"📥 模板分析结果: {template_type}")
            print("✅ _process_template 执行完成")
            print("=" * 50)

            return {"template_complexity": template_type,
                    "uploaded_template_files_path": [template_file]
                    }

        except Exception as e:
            print(f"❌ 模板分析LLM调用出错: {e}")
            # Default to Simple if analysis fails
            template_type = "[Simple]"
            print("⚠️ 模板分析失败，默认为简单模板")
            print("✅ _process_template 执行完成")
            print("=" * 50)
            
            return {
                "template_complexity": template_type,
                "uploaded_template_files_path": [template_file]
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
        if state.get("previous_AI_messages") and len(state["previous_AI_messages"]) > 0:
            latest_ai_msg = state["previous_AI_messages"][-1]
            if hasattr(latest_ai_msg, 'content'):
                previous_ai_content = latest_ai_msg.content
        
        system_prompt = f"""你是一个输入验证专家，需要判断用户的文本输入是否与表格生成、Excel处理相关，并且是否包含有意义的内容，你的判断需要根据上下文，
        我会提供上一个AI的回复，以及用户输入，你需要根据上下文，判断用户输入是否与表格生成、Excel处理相关，并且是否包含有意义的内容。
        
        上一个AI的回复: {previous_ai_content}
        用户输入: {user_input}

        验证标准：
        1. **有效输入 [Valid]**:
           - 明确提到需要生成表格、填写表格、Excel相关操作
           - 包含具体的表格要求、数据描述、字段信息
           - 询问表格模板、表格格式相关问题
           - 提供了表格相关的数据或信息

        2. **无效输入 [Invalid]**:
           - 完全与表格/Excel无关的内容
           - 垃圾文本、随机字符、无意义内容
           - 空白或只有标点符号
           - 明显的测试输入或无关问题

        请仔细分析用户输入，然后只回复以下选项之一：
        [Valid] - 如果输入与表格相关且有意义
        [Invalid] - 如果输入无关或无意义"""
        
        try:
            print("📤 正在调用LLM进行文本输入验证...")
            # Get LLM validation
            validation_response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
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
        根据历史对话总结这轮用户信息收集过程中，用户都提供了哪些有价值的信息，包括文件上传，文本输入，模板上传等
        历史对话: {process_user_input_messages_content}，
        请只返回JSON格式，无其他文字：
        {{
            "summary": "用户本轮提供的信息总结，输入了什么信息，提供了哪些文件等"
        }}"""

        try:
            print("📤 正在调用LLM生成总结...")
            response = invoke_model(model_name="Qwen/Qwen3-32B", messages=[SystemMessage(content=system_prompt)])
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

