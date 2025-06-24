import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content
from utilities.modelRelated import model_creation

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
    session_id: str
    
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

    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.llm_c = model_creation(model_name=model_name, temperature=2) # complex logic use user selected model
        self.llm_c_with_tools = self.llm_c.bind_tools(self.tools)
        self.llm_s = model_creation(model_name="gpt-3.5-turbo", temperature=2) # simple logic use 3-5turbo
        self.llm_s_with_tools = self.llm_s.bind_tools(self.tools)
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



    def create_initial_state(self, user_input: str, session_id: str = "1") -> ProcessUserInputState:
        """This function initializes the state of the process user input agent"""
        return {
            "process_user_input_messages": [HumanMessage(content=user_input)],
            "user_input": user_input,
            "upload_files_path": [],
            "new_upload_files_path": [],
            "new_upload_files_processed_path": [],
            "uploaded_template_files_path": [],
            "supplement_files_path": {"表格": [], "文档": []},
            "irrelevant_files_path": [],
            "all_files_irrelevant": False,
            "text_input_validation": None,
            "previous_AI_messages": [AIMessage(content="请提供更多关于羊村人口普查的信息")],
            "session_id": session_id,
        }


    def _collect_user_input(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This is the node where we get user's input"""
        user_input = interrupt("用户：")
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
        
        # Re-detect files from user input since routing functions cannot modify state
        latest_message = state["process_user_input_messages"][-1]
        message_content = latest_message.content if hasattr(latest_message, 'content') else str(latest_message)
        
        detected_files = detect_and_process_file_paths(message_content)
        data_file = Path("agents/data.json")
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for file in detected_files:
            file_name = Path(file).name
            if file_name in data["表格"] or file_name in data["文档"]:
                detected_files.remove(file)
                print(f"⚠️ 文件 {file} 已存在")
        
        if not detected_files:
            print("⚠️ No new files to upload")
            return {
                "new_upload_files_path": [],
                "new_upload_files_processed_path": []
            }
        
        print(f"🔄 Processing {len(detected_files)} new files")
        
        # Process the files using the correct session_id
        result = retrieve_file_content(detected_files, "files")
        
        print(f"✅ File uploaded: {result}")
        
        # Update state with new files
        return {
            "new_upload_files_path": detected_files,
            "upload_files_path": state["upload_files_path"] + detected_files,
            "new_upload_files_processed_path": result
        }
    


    def _analyze_uploaded_files(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will analyze the user's uploaded files, it need to classify the file into template
        supplement, or irrelevant. If all files are irrelevant, it will flag for text analysis instead."""
        
        import json
        from pathlib import Path
        
        # Initialize classification results
        classification_results = {
            "template": [],
            "supplement": {"表格": [], "文档": []},
            "irrelevant": []
        }
        
        # Process files one by one for better accuracy
        processed_files = []
        for file_path in state["new_upload_files_processed_path"]:
            try:
                source_path = Path(file_path)
                if not source_path.exists():
                    print(f"❌ 文件不存在: {file_path}")
                    classification_results["irrelevant"].append(file_path)
                    continue
                
                # Read file content for analysis
                file_content = source_path.read_text(encoding='utf-8')
                # Truncate content for analysis (to avoid token limits)
                analysis_content = file_content[:2000] if len(file_content) > 2000 else file_content
                
                # Create individual analysis prompt for this file
                system_prompt = f"""你是一个表格生成智能体，需要分析用户上传的文件内容并进行分类。共有四种类型：

                1. **模板类型 (template)**: 空白表格模板，只有表头没有具体数据
                2. **补充表格 (supplement-表格)**: 已填写的完整表格，用于补充数据库
                3. **补充文档 (supplement-文档)**: 包含重要信息的文本文件，如法律条文、政策信息等
                4. **无关文件 (irrelevant)**: 与表格填写无关的文件

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
                analysis_response = self.llm_c_with_tools.invoke([SystemMessage(content=system_prompt)])
                
                # Handle tool calls if LLM needs clarification
                if hasattr(analysis_response, 'tool_calls') and analysis_response.tool_calls:
                    print(f"⚠️ LLM对文件 {source_path.name} 需要使用工具，跳过此文件")
                    classification_results["irrelevant"].append(file_path)
                    continue
                
                # Parse JSON response for this file
                try:
                    # Extract JSON from response
                    response_content = analysis_response.content.strip()
                    # Remove markdown code blocks if present
                    if response_content.startswith('```'):
                        response_content = response_content.split('\n', 1)[1]
                        response_content = response_content.rsplit('\n', 1)[0]
                    
                    file_classification = json.loads(response_content)
                    classification_type = file_classification.get("classification", "irrelevant")
                    
                    # Add to appropriate category
                    if classification_type == "template":
                        classification_results["template"].append(file_path)
                    elif classification_type == "supplement-表格":
                        classification_results["supplement"]["表格"].append(file_path)
                    elif classification_type == "supplement-文档":
                        classification_results["supplement"]["文档"].append(file_path)
                    else:  # irrelevant or unknown
                        classification_results["irrelevant"].append(file_path)
                    
                    processed_files.append(source_path.name)
                    print(f"✅ 文件 {source_path.name} 分类为: {classification_type}")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ 文件 {source_path.name} JSON解析错误: {e}")
                    print(f"LLM响应: {analysis_response.content}")
                    # Fallback: mark as irrelevant for safety
                    classification_results["irrelevant"].append(file_path)
                
            except Exception as e:
                print(f"❌ 处理文件出错 {file_path}: {e}")
                # Add to irrelevant on error
                classification_results["irrelevant"].append(file_path)
                continue
        
        if not processed_files and not classification_results["irrelevant"]:
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
        all_files_irrelevant = (
            len(uploaded_template_files) == 0 and 
            len(supplement_files.get("表格", [])) == 0 and 
            len(supplement_files.get("文档", [])) == 0 and
            len(irrelevant_files) == len(state["new_upload_files_processed_path"])
        )
        
        if all_files_irrelevant:
            # All files are irrelevant, flag for text analysis
            analysis_summary = f"""📋 文件分析完成 - 所有文件均与表格生成无关:
            ❌ 无关文件: {len(irrelevant_files)} 个
            
            文件列表: {[Path(f).name for f in irrelevant_files]}
            
            🔄 将转为分析用户文本输入内容"""
            
            return {
                "uploaded_template_files_path": [],
                "supplement_files_path": {"表格": [], "文档": []},
                "irrelevant_files_path": irrelevant_files,
                "all_files_irrelevant": True,  # Flag for routing
                "process_user_input_messages": [SystemMessage(content=analysis_summary)]
            }
        else:
            # Some files are relevant, proceed with normal flow
            analysis_summary = f"""📋 文件分析完成:
            ✅ 模板文件: {len(uploaded_template_files)} 个
            ✅ 补充表格: {len(supplement_files.get("表格", []))} 个  
            ✅ 补充文档: {len(supplement_files.get("文档", []))} 个
            ❌ 无关文件: {len(irrelevant_files)} 个

            分类详情:
            模板: {[Path(f).name for f in uploaded_template_files]}
            表格: {[Path(f).name for f in supplement_files.get("表格", [])]}
            文档: {[Path(f).name for f in supplement_files.get("文档", [])]}
            无关: {[Path(f).name for f in irrelevant_files]}"""
            
            return {
                "uploaded_template_files_path": uploaded_template_files,
                "supplement_files_path": supplement_files,
                "irrelevant_files_path": irrelevant_files,
                "all_files_irrelevant": False,  # Flag for routing
                "process_user_input_messages": [SystemMessage(content=analysis_summary)]
            }
                
    def _route_after_analyze_uploaded_files(self, state: ProcessUserInputState):
        """Route after analyzing uploaded files. Uses Send objects for all routing."""
        
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
        
        # Some files are relevant - process them in parallel, then continue to text analysis
        sends = []
        if state.get("uploaded_template_files_path"):
            sends.append(Send("process_template", state))
        if state.get("supplement_files_path", {}).get("表格") or state.get("supplement_files_path", {}).get("文档"):
            sends.append(Send("process_supplement", state))
        if state.get("irrelevant_files_path"):
            sends.append(Send("process_irrelevant", state))

        
        return sends if sends else [Send("analyze_text_input", state)]  # Fallback
    
    def _process_supplement(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will process the supplement files, it will analyze the supplement files and summarize the content of the files as well as stored the summary in data.json"""
        
        # Load existing data.json
        data_json_path = Path("agents/data.json")
        try:
            with open(data_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"表格": {}, "文档": {}}
        
        table_files = state["supplement_files_path"]["表格"]
        document_files = state["supplement_files_path"]["文档"]
        
        # Process table files
        for table_file in table_files:
            try:
                source_path = Path(table_file)
                file_content = source_path.read_text(encoding='utf-8')
                
                system_prompt = f"""你是一个表格分析专家，现在这个excel表格已经被转换成了HTML格式，你的任务是仔细阅读这个表格，分析表格的结构，并总结表格的内容，所有的表头、列名、数据都要总结出来。

                文件内容:
                {file_content}

                请按照以下格式输出结果：
                {{
                    "表格结构": "描述表格的整体结构",
                    "表头信息": ["列名1", "列名2", "列名3"],
                    "数据概要": "数据的总体描述和重要信息",
                    "行数统计": "总行数",
                    "关键字段": ["重要字段1", "重要字段2"]
                }}"""
                                
                analysis_response = self.llm_c.invoke([SystemMessage(content=system_prompt)])
                
                # Store in data.json
                data["表格"][source_path.name] = {
                    "summary": analysis_response.content,
                    "file_path": str(table_file),
                    "timestamp": datetime.now().isoformat(),
                    "file_size": source_path.stat().st_size
                }
                
                print(f"✅ 表格文件已分析: {source_path.name}")
                
            except Exception as e:
                print(f"❌ 处理表格文件出错 {table_file}: {e}")

        # Process document files
        for document_file in document_files:
            try:
                source_path = Path(document_file)
                file_content = source_path.read_text(encoding='utf-8')
                
                system_prompt = f"""你是一个文档分析专家，现在这个文档已经被转换成了txt格式，你的任务是仔细阅读这个文档，分析文档的内容，并总结文档的内容。文档可能包含重要的信息，例如法律条文、政策规定等，你不能遗漏这些信息。

                文件内容:
                {file_content}

                请按照以下格式输出结果：
                {{
                    "文档类型": "判断文档的类型（如政策文件、法律条文、说明文档等）",
                    "主要内容": "文档的核心内容概要",
                    "重要条款": ["重要条款1", "重要条款2"],
                    "关键信息": ["关键信息1", "关键信息2"],
                    "应用场景": "这些信息在表格填写中的用途"
                }}"""
                                
                analysis_response = self.llm_c.invoke([SystemMessage(content=system_prompt)])

                # Update state with analysis response
                state["process_user_input_messages"].append(analysis_response)
                
                # Store in data.json
                data["文档"][source_path.name] = {
                    "summary": analysis_response.content,
                    "file_path": str(document_file),
                    "timestamp": datetime.now().isoformat(),
                    "file_size": source_path.stat().st_size
                }
                
                print(f"✅ 文档文件已分析: {source_path.name}")
                
            except Exception as e:
                print(f"❌ 处理文档文件出错 {document_file}: {e}")
        
        # Save updated data.json
        try:
            with open(data_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"✅ 已更新 data.json，表格文件 {len(data['表格'])} 个，文档文件 {len(data['文档'])} 个")
        except Exception as e:
            print(f"❌ 保存 data.json 时出错: {e}")
        
        # Create summary message
        summary_message = f"""📊 补充文件处理完成:
        ✅ 表格文件: {len(table_files)} 个已分析并存储
        ✅ 文档文件: {len(document_files)} 个已分析并存储
        📝 数据库已更新，总计表格 {len(data['表格'])} 个，文档 {len(data['文档'])} 个"""
        
        return {
            "process_user_input_messages": [SystemMessage(content=summary_message)]
        }
        
        
    def _process_irrelevant(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will process the irrelevant files, it will delete the irrelevant files from the conversations folder"""
        
        deleted_files = []
        failed_deletes = []
        
        for file_path in state["irrelevant_files_path"]:
            try:
                file_to_delete = Path(file_path)
                if file_to_delete.exists():
                    os.remove(file_to_delete)
                    deleted_files.append(file_to_delete.name)
                    print(f"🗑️ 已删除无关文件: {file_to_delete.name}")
                else:
                    print(f"⚠️ 文件不存在，跳过删除: {file_path}")
                    
            except Exception as e:
                failed_deletes.append(Path(file_path).name)
                print(f"❌ 删除文件时出错 {file_path}: {e}")

        # Create summary message
        summary_message = f"""🗑️ 无关文件处理完成:
        ✅ 成功删除: {len(deleted_files)} 个文件
        ❌ 删除失败: {len(failed_deletes)} 个文件

        删除的文件: {', '.join(deleted_files) if deleted_files else '无'}
        失败的文件: {', '.join(failed_deletes) if failed_deletes else '无'}"""
        
        return {
            "process_user_input_messages": [SystemMessage(content=summary_message)]
        }
    

    
    def _process_template(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will process the template files, it will analyze the template files and determine if it's a valid template"""
        
        template_files = state["uploaded_template_files_path"]
        
        # If multiple templates, ask user to choose
        if len(template_files) > 1:
            template_names = [Path(f).name for f in template_files]
            question = f"检测到多个模板文件，请选择要使用的模板：\n" + \
                      "\n".join([f"{i+1}. {name}" for i, name in enumerate(template_names)]) + \
                      "\n请输入序号（如：1）："
            
            try:
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
        
        try:
            source_path = Path(template_file)
            template_content = source_path.read_text(encoding='utf-8')
            
            # Create prompt to determine if template is complex or simple
            system_prompt = f"""你是一个表格结构分析专家，需要判断这个表格模板是复杂模板还是简单模板。

            判断标准：
            - **复杂模板**: 表格同时包含行表头和列表头，即既有行标题又有列标题的二维表格结构
            - **简单模板**: 表格只包含列表头，每行是独立的数据记录

            模板内容（HTML格式）：
            {template_content}

            请仔细分析表格结构，然后只回复以下选项之一：
            [Complex] - 如果是复杂模板（包含行表头和列表头）
            [Simple] - 如果是简单模板（只包含列表头）"""
            
            analysis_response = self.llm_c.invoke([SystemMessage(content=system_prompt)])
            
            # Parse response
            response_content = analysis_response.content.strip()
            if "[Complex]" in response_content:
                template_type = "[Complex]"
            elif "[Simple]" in response_content:
                template_type = "[Simple]"
            else:
                # Default to Simple if unclear
                template_type = "[Simple]"
                print("⚠️ 无法确定模板类型，默认为简单模板")
            
            # Create analysis summary
            summary_message = f"""📋 模板分析完成:
            ✅ 选定模板: {Path(template_file).name}
            🔍 模板类型: {template_type}
            📁 模板路径: {template_file}

            {template_type}"""
            
            return {
                "uploaded_template_files_path": template_files,  # Only selected template
                "process_user_input_messages": [SystemMessage(content=summary_message)]
            }
            
        except Exception as e:
            print(f"❌ 分析模板时出错: {e}")
            return {
                "uploaded_template_files_path": template_files,
                "process_user_input_messages": [SystemMessage(content=f"模板分析出错: {e}\n默认为[Simple]")]
            }



    def _route_after_process_template(self, state: ProcessUserInputState) -> str:
        """It has two different routes, if it is [Complex] template we will go to complex template handle node, which for now is a placeholder.
        if it is [Simple] template we simply go to the template_provided node to keep the analysis"""

        latest_message = state["process_user_input_messages"][-1]
        if "[Complex]" in latest_message.content:
            return "complex_template_handle"
        else:
            return "template_provided"
        


    def _analyze_text_input(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node performs a safety check on user text input when all uploaded files are irrelevant.
        It validates if the user input contains meaningful table/Excel-related content.
        Returns [Valid] or [Invalid] based on the analysis."""
        
        user_input = state["user_input"]
        
        if not user_input or user_input.strip() == "":
            return {
                "text_input_validation": "[Invalid]",
                "process_user_input_messages": [SystemMessage(content="❌ 用户输入为空，验证失败")]
            }
        
        # Create validation prompt for text input safety check
        system_prompt = f"""你是一个输入验证专家，需要判断用户的文本输入是否与表格生成、Excel处理相关，并且是否包含有意义的内容，你的判断需要根据上下文，
        我会提供上一个AI的回复，以及用户输入，你需要根据上下文，判断用户输入是否与表格生成、Excel处理相关，并且是否包含有意义的内容。
        
        上一个AI的回复: {state["previous_AI_messages"]}
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
            # Get LLM validation
            validation_response = self.llm_s.invoke([SystemMessage(content=system_prompt)])
            
            # Parse response
            response_content = validation_response.content.strip()
            
            if "[Valid]" in response_content:
                validation_result = "[Valid]"
                status_message = "✅ 用户输入验证通过 - 内容与表格相关且有意义"
            elif "[Invalid]" in response_content:
                validation_result = "[Invalid]"
                status_message = "❌ 用户输入验证失败 - 内容与表格无关或无意义"
            else:
                # Default to Invalid for safety
                validation_result = "[Invalid]"
                status_message = "❌ 用户输入验证失败 - 无法确定输入有效性，默认为无效"
                print(f"⚠️ 无法解析验证结果，LLM响应: {response_content}")
            
            # Create validation summary
            summary_message = f"""🔍 文本输入安全检查完成:
            
            📄 **用户输入**: {user_input[:100]}{'...' if len(user_input) > 100 else ''}
            ✅ **验证结果**: {validation_result}
            📝 **状态**: {status_message}"""
            
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
        """Basically this nodes act as a summry nodes, that summarize what the new information has been provided by the user in this round of human in the lopp also it needs to 
        decide which node to route to next
        """
        process_user_input_messages_conent = [item.content for item in state["process_user_input_messages"]]
        system_prompt = f"""你的任务是负责总结用户在这一轮都提供了哪些信息，你需要根据整个对话记录，总结用户都提供了哪些信息，并且根据这些信息，决定下一步的流程
        规则如下，如何出现了复杂模板，返回"complex_template"，如果出现了简单模板，返回"simple_template"，其余情况请返回"previous_node" 
        你的回复需要包含对这一轮的总结，和节点路由信息，由json来表示

        历史对话:{process_user_input_messages_conent}
        {{
            "summary": "总结用户在这一轮都提供了哪些信息",
            "next_node": "节点路由信息"
        }}
        
        """
        
        try:
            # Try the LLM call with detailed error handling
            
            messages = [SystemMessage(content=system_prompt)]
            print(f"🔄 正在调用LLM进行总结，消息数量: {len(messages)}")
            
            response = self.llm_c.invoke(messages)
            print(f"✅ LLM调用成功")
            
            return {"process_user_input_messages": [response]}
            
        except Exception as e:
            print(f"❌ LLM调用失败: {type(e).__name__}: {e}")
            
            # Fallback response when LLM fails
            fallback_response = AIMessage(content="""
            {
                "summary": "由于网络连接问题，无法完成智能分析。用户本轮提供了输入信息。",
                "next_node": "previous_node"
            }
            """)
            
            return {"process_user_input_messages": [fallback_response]}
    

    def run_process_user_input_agent(self, user_input: str, session_id: str = "1") -> None:
        """This function runs the process user input agent"""
        initial_state = self.create_initial_state(user_input, session_id)
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
    agent = ProcessUserInputAgent()
    # save_graph_visualization(agent.graph, "process_user_input_graph.png")
    agent.run_process_user_input_agent("")

