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

from langgraph.graph import StateGraph, END, START, Send
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool


load_dotenv()

class ProcessUserInputState(TypedDict):
    process_user_input_messages: Annotated[list[BaseMessage], add_messages]
    user_input: str
    upload_files_path: list[str]
    new_upload_files_path: list[str] # Track the new uploaded files
    upload_files_processed_path: list[str]
    new_upload_files_processed_path: list[str]
    uploaded_template_files_path: list[str]
    supplement_files_path: dict[str, list[str]]
    irrelevant_files_path: list[str]
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


    def _build_graph(self) -> StateGraph:
        """This function will build the graph for the process user input agent"""
        graph = StateGraph(ProcessUserInputState)
        graph.add_node("collect_user_input", self._collect_user_input)
        graph.add_node("file_upload", self._file_upload)
        graph.add_node("analyze_file", self._analyze_file)
        graph.add_node("analyze_uploaded_files", self._analyze_uploaded_files)
        graph.add_node("process_supplement", self._process_supplement)

        graph.add_edge(START, "collect_user_input")
        graph.add_conditional_edges(
            "collect_user_input", 
            self._route_after_collect_user_input,
            {
                "file_upload": "file_upload",
                "valid_input": "",
                "invalid_input": "collect_user_input"
            }
            )

    

    clarification_tool_node = ToolNode(tools)



    def _collect_user_input(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This is the node where we get user's input"""
        user_input = interrupt("用户：")
        return {"user_input": user_input}



    def _route_after_collect_user_input(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node act as a safety check node, it will analyze the user's input and determine if it's a valid input,
        based on the LLM's previous response, at the same time it will route the agent to the correct node"""
        # We should let LLM decide the route
        
        user_upload_files = detect_and_process_file_paths(state["process_user_input_messages"][-1])
        # Filter out the new uploaded files
        new_upload_files = [item for item in user_upload_files if item not in state["upload_files_path"]]
        if new_upload_files:
            state["new_upload_files_path"] = new_upload_files
            state["upload_files_path"].extend(new_upload_files)
            return "file_upload"
        
        # User didn't upload new files
        elif not user_upload_files:
            system_prompt = """你需要判断用户的输入是否为有效输入，判断标准为"""
            LLM_response_and_user_input = [state["process_user_input_messages"][-2], state["process_user_input_messages"][-1]]
            LLM_decision = self.llm_s.invoke([SystemMessage(content=system_prompt)] + LLM_response_and_user_input)
            # If it is a valid input we conitnue the normal execution flow, otherwise we will keep leting user 
            # input messages until it is a valid input
            if LLM_decision.content == "[YES]":
                return "valid_input"
            else:
                print(f"❌ Invalid input: {state['process_user_input_messages'][-1].content}")
                return "invalid_input"
    


    def _uploaded_files(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will upload user's file to our system"""
        # For now we simply store the file content 
        result = retrieve_file_content(state["new_upload_files_path"], state["session_id"])
        state["new_upload_files_processed_path"] = result
        state["upload_files_processed_path"].extend(result)
        print(f"✅ File uploaded: {state['upload_files_processed_path']}")
        return "analyze_file"
    


    def _analyze_uploaded_files(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will analyze the user's uploaded files, it need to classify the file into template
        supplement, or irrelevant"""
        
        import json
        import os
        from pathlib import Path
        
        # Initialize classification results
        classification_results = {
            "template": [],
            "supplement": {"表格": [], "文档": []},
            "irrelevant": []
        }
        
        # Process files in batch for efficiency
        files_content = []
        for file_path in state["new_upload_files_processed_path"]:
            try:
                source_path = Path(file_path)
                if not source_path.exists():
                    print(f"❌ 文件不存在: {file_path}")
                    continue
                
                # Read file content for analysis
                file_content = source_path.read_text(encoding='utf-8')
                # Truncate content for analysis (to avoid token limits)
                analysis_content = file_content[:2000] if len(file_content) > 2000 else file_content
                
                files_content.append({
                    "file_path": file_path,
                    "file_name": source_path.name,
                    "content": analysis_content
                })
                
            except Exception as e:
                print(f"❌ 读取文件出错 {file_path}: {e}")
                continue
        
        if not files_content:
            return {
                "uploaded_template_files_path": [],
                "supplement_files_path": {"表格": [], "文档": []},
                "irrelevant_files_path": [],
                "process_user_input_messages": [SystemMessage(content="没有找到可处理的文件")]
            }
        
        # Create analysis prompt in Chinese
        files_info = "\n\n".join([
            f"文件名: {item['file_name']}\n文件路径: {item['file_path']}\n文件内容:\n{item['content']}"
            for item in files_content
        ])
        
        system_prompt = f"""你是一个表格生成智能体，需要分析用户上传的文件内容并进行分类。共有四种类型：

        1. **模板类型 (template)**: 空白表格模板，只有表头没有具体数据
        2. **补充表格 (supplement-表格)**: 已填写的完整表格，用于补充数据库
        3. **补充文档 (supplement-文档)**: 包含重要信息的文本文件，如法律条文、政策信息等
        4. **无关文件 (irrelevant)**: 与表格填写无关的文件

        注意：所有文件已转换为txt格式，表格以HTML代码形式呈现，请根据内容而非文件名或后缀判断。

        用户输入: {state.get("user_input", "")}

        文件信息:
        {files_info}

        请严格按照以下JSON格式回复（不要添加任何其他文字）：
        {{
            "template": ["文件路径1", "文件路径2"],
            "supplement": {{"表格": ["文件路径1"], "文档": ["文件路径2"]}},
            "irrelevant": ["文件路径1"]
        }}"""
        
        try:
            # Get LLM analysis
            analysis_response = self.llm_c_with_tools.invoke([SystemMessage(content=system_prompt)])
            
            # Handle tool calls if LLM needs clarification
            if hasattr(analysis_response, 'tool_calls') and analysis_response.tool_calls:
                # Add the analysis response to process messages for tool handling
                return {
                    "process_user_input_messages": [analysis_response]
                }
            
            # Parse JSON response
            try:
                # Extract JSON from response
                response_content = analysis_response.content.strip()
                # Remove markdown code blocks if present
                if response_content.startswith('```'):
                    response_content = response_content.split('\n', 1)[1]
                    response_content = response_content.rsplit('\n', 1)[0]
                
                classification_results = json.loads(response_content)
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析错误: {e}")
                print(f"LLM响应: {analysis_response.content}")
                # Fallback: keep all files as irrelevant for safety
                classification_results = {
                    "template": [],
                    "supplement": {"表格": [], "文档": []},
                    "irrelevant": [item['file_path'] for item in files_content]
                }
            
            # Update state with classification results
            uploaded_template_files = classification_results.get("template", [])
            supplement_files = classification_results.get("supplement", {"表格": [], "文档": []})
            irrelevant_files = classification_results.get("irrelevant", [])
            
            # Create analysis summary message
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
                "process_user_input_messages": [SystemMessage(content=analysis_summary)]
            }
            
        except Exception as e:
            print(f"❌ 分析文件时出错: {e}")
            # Fallback: keep all files as irrelevant for safety
            return {
                "uploaded_template_files_path": [],
                "supplement_files_path": {"表格": [], "文档": []},
                "irrelevant_files_path": [item['file_path'] for item in files_content],
                "process_user_input_messages": [SystemMessage(content=f"文件分析出错: {e}")]
            }
                
    def _route_after_analyze_uploaded_files(self, state: ProcessUserInputState):
        if state.get("user_clarification_request"):
            return [Send("request_user_clarification", state)]
        
        sends = []
        if state.get("template_files"):
            sends.append(Send("_process_template", state))
        if state.get("supplement_files"):
            sends.append(Send("_process_supplement", state))
        if state.get("irrelevant_files"):
            sends.append(Send("_process_irrelevant", state))
        
        return sends
    
    def _process_supplement(self, state: ProcessUserInputState) -> ProcessUserInputState:
        """This node will process the supplement files, it will analyze the supplement files and summarize the content of the files"""
        
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
        
        # Clean up state lists - remove deleted files from all relevant lists ！！！！！！！ Might not be needed
        for file_path in state["irrelevant_files_path"]:
            # Remove from processed files lists
            if file_path in state.get("upload_files_processed_path", []):
                state["upload_files_processed_path"].remove(file_path)
            if file_path in state.get("new_upload_files_processed_path", []):
                state["new_upload_files_processed_path"].remove(file_path)
        
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