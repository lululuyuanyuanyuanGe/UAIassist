from utilities.file_process import *
from utilities.message_process import *
import json
from pathlib import Path
from datetime import datetime
from langchain_core.messages import SystemMessage
from utilities.modelRelated import model_creation
from langchain_openai import ChatOpenAI

def _process_supplement(file_path: list[str], model: ChatOpenAI):
        """This node will process the supplement files, it will analyze the supplement files and summarize the content of the files as well as stored the summary in data.json"""
        
        # Load existing data.json
        data_json_path = Path("agents/data.json")
        try:
            with open(data_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"表格": {}, "文档": {}}
        
        table_files = file_path
        document_files = file_path
        
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
                                
                analysis_response = model.invoke([SystemMessage(content=system_prompt)])
                
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
                                
                analysis_response = model.invoke([SystemMessage(content=system_prompt)])

                # Update state with analysis response
                # state["process_user_input_messages"].append(analysis_response)
                
                # Store in data.json
                data["文档"][source_path.name] = {
                    "summary": analysis_response.content,
                    "file_path": str(document_file),
                    "timestamp": datetime.now().isoformat(),
                    "file_size": source_path.stat().st_size
                }
                
                print(f"✅ 文档文件已分析: {source_path.name}")
                print(f"分析结果: {analysis_response.content}")
                
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
        
        return 


user_input_files = input("请输入用户输入的文件路径: ")
result = detect_and_process_file_paths(user_input_files)
print(result)

file_path = retrieve_file_content(result, "1")
print(file_path)

for file in file_path:
    analysis_content = Path(file).read_text(encoding='utf-8')

    model = ChatOpenAI(model="gpt-4o", temperature=0.0)
        
    _process_supplement([file], model)