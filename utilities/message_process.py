from typing import TypedDict, Annotated, List
import re
import os
from pathlib import Path

from openai import OpenAI
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage

def build_BaseMessage_type(messages:list[dict], file_paths : list[str] = None) -> list[BaseMessage]:
    """"将消息队列转换成LangChain的消息模板"""
    langchain_messages = []
    for msg in messages:
        if msg["role"] == "system":
            langchain_messages.append(SystemMessage(content = msg["content"]))
        elif msg["role"] == "user":
            # 判断是否为复杂输入(包含文件)
            if isinstance(msg["content"], list):
                # 将用户文本输入存储在 contenxt_text
                contexnt_text = next((item["text"] for item in msg["content"] if item["type"] == "text"), "")
                file_refs = [item["file_id"] for item in msg["content"] if item["type"] == "input_file"]
                user_input = F"{contexnt_text} + input files list: {' '.join(file_refs)}"
                human_msg = HumanMessage(
                    content= user_input,
                    additional_kargs = {
                        "filer_ids": file_refs,
                        "multimodal_content": msg["content"]
                    }
                )
                langchain_messages.append(human_msg)
        else:
            langchain_messages.append(HumanMessage(content=msg["content"]))

    return langchain_messages

def create_assistant_with_files(client: OpenAI, file_paths: list[str], user_input: str, system_prompt: str) -> dict:
    """
    使用OpenAI Assistants API正确处理Excel文件上传和分析
    """
    print(f"📤 正在上传 {len(file_paths)} 个文件到OpenAI...")
    
    # 1. 上传文件到OpenAI (目的为assistants)
    file_ids = []
    for file_path in file_paths:
        try:
            with open(file_path, 'rb') as file:
                file_response = client.files.create(
                    file=file,
                    purpose="assistants"  # 关键：必须设置为assistants
                )
                file_ids.append(file_response.id)
                print(f"✅ 文件上传成功: {file_path} -> {file_response.id}")
        except Exception as e:
            print(f"❌ 文件上传失败 {file_path}: {e}")
            continue
    # 这个函数只有在用户上传文件后才会被唤醒，因此file_paths一定不为空
    if not file_ids:
        raise Exception("没有文件成功上传")
    
    # 2. 创建Assistant，启用code_interpreter工具
    assistant = client.beta.assistants.create(
        name="Excel File Analyzer",
        instructions=system_prompt,
        model="gpt-4o",  # 使用支持文件的模型
        tools=[{"type": "code_interpreter"}],  # 关键：启用code_interpreter
        tool_resources={
            "code_interpreter": {
                "file_ids": file_ids  # 关键：将文件附加到code_interpreter
            }
        }
    )
    print(f"✅ Assistant创建成功: {assistant.id}")
    
    # 3. 创建Thread
    thread = client.beta.threads.create()
    print(f"✅ Thread创建成功: {thread.id}")
    
    # 4. 添加用户消息
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_input
    )
    
    # 5. 运行Assistant
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant.id,
        timeout=60  # 60秒超时
    )
    
    # 6. 获取响应
    if run.status == 'completed':
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        # 获取最新的助手回复
        for message in messages.data:
            if message.role == "assistant":
                response_content = ""
                for content_item in message.content:
                    if hasattr(content_item, 'text'):
                        response_content += content_item.text.value
                
                print("✅ Assistant分析完成")
                return {
                    "assistant_id": assistant.id,
                    "thread_id": thread.id,
                    "response": response_content,
                    "file_ids": file_ids
                }
    else:
        raise Exception(f"Assistant运行失败，状态: {run.status}")

def filter_out_system_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """辅助函数过滤消息队列中的系统提示词消息"""
    return [message for message in messages if not isinstance(message, SystemMessage)]


def detect_and_process_file_paths(user_input: str) -> list:
    """检测用户输入中的文件路径并验证文件是否存在"""
    file_paths = []
    
    # 改进的文件路径检测模式，支持中文字符
    # Windows路径模式 (C:\path\file.ext 或 D:\path\file.ext) - 支持中文字符
    windows_pattern = r'[A-Za-z]:[\\\\/](?:[^\\\\/\s\n\r]+[\\\\/])*[^\\\\/\s\n\r]+\.\w+'
    # 相对路径模式 (./path/file.ext 或 ../path/file.ext) - 支持中文字符
    relative_pattern = r'\.{1,2}[\\\\/](?:[^\\\\/\s\n\r]+[\\\\/])*[^\\\\/\s\n\r]+\.\w+'
    # 简单文件名模式 (filename.ext) - 支持中文字符
    filename_pattern = r'\b[a-zA-Z0-9_\u4e00-\u9fff\-\(\)（）]+\.[a-zA-Z0-9]+\b'
    
    patterns = [windows_pattern, relative_pattern, filename_pattern]
    
    for pattern in patterns:
        matches = re.findall(pattern, user_input)
        for match in matches:
            # 验证文件是否存在
            if os.path.exists(match):
                file_paths.append(match)
                print(f"✅ 检测到文件: {match}")
            else:
                print(f"⚠️ 文件路径无效或文件不存在: {match}")
    
    return file_paths

def upload_file_to_LLM(file_paths: list, provider: str = "openai", purpose: str = "assistants", vector_store_id: str = None):
    """
    通用文件上传工具，支持多个模型提供商
    """
    results = {
        "provider": provider,
        "uploaded_files": [],
        "failed_files": [],
        "vector_store_files": [],
        "total_files": len(file_paths)
    }
    
    if provider.lower() == "openai":
        return _upload_to_openai(file_paths, purpose, vector_store_id, results)
    # elif provider.lower() == "azure":
    #     return _upload_to_azure(file_paths, purpose, vector_store_id, results)
    # elif provider.lower() == "anthropic":
    #     return _upload_to_anthropic(file_paths, purpose, results)
    # elif provider.lower() == "local":
    #     return _upload_to_local(file_paths, purpose, results)
    else:
        results["error"] = f"Unsupported provider: {provider}"
        return results


def _upload_to_openai(file_paths: list, purpose: str, vector_store_id: str, results: dict):
    """OpenAI 文件上传实现"""
    from openai import OpenAI
    import os
    
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        for file_path in file_paths:
            try:
                file_path = Path(file_path)
                if not file_path.exists():
                    results["failed_files"].append({
                        "file": str(file_path),
                        "error": "File not found"
                    })
                    continue
                
                print(f"📁 正在上传文件: {file_path.name}")
                
                # 上传文件到OpenAI
                with open(file_path, 'rb') as file:
                    file_response = client.files.create(
                        file=file,
                        purpose=purpose
                    )
                
                uploaded_file_info = {
                    "file_id": file_response.id,
                    "filename": file_response.filename,
                    "purpose": file_response.purpose,
                    "size": file_response.bytes,
                    "created_at": file_response.created_at
                }
                
                results["uploaded_files"].append(uploaded_file_info)
                print(f"✅ 文件上传成功: {file_response.filename} (ID: {file_response.id})")
                
                # 如果提供了vector_store_id，将文件添加到向量存储
                if vector_store_id:
                    try:
                        vector_file_response = client.beta.vector_stores.files.create(
                            vector_store_id=vector_store_id,
                            file_id=file_response.id
                        )
                        
                        results["vector_store_files"].append({
                            "vector_store_id": vector_store_id,
                            "file_id": file_response.id,
                            "status": vector_file_response.status
                        })
                        print(f"✅ 文件已添加到向量存储: {vector_store_id}")
                        
                    except Exception as vs_error:
                        print(f"⚠️ 向量存储添加失败: {vs_error}")
                        results["failed_files"].append({
                            "file": str(file_path),
                            "error": f"Vector store upload failed: {vs_error}"
                        })
                
            except Exception as file_error:
                print(f"❌ 文件上传失败 {file_path.name}: {file_error}")
                results["failed_files"].append({
                    "file": str(file_path),
                    "error": str(file_error)
                })
        
        results["success"] = True
        results["message"] = f"OpenAI上传完成: {len(results['uploaded_files'])}个成功, {len(results['failed_files'])}个失败"
        
    except Exception as e:
        results["success"] = False
        results["error"] = f"OpenAI API错误: {str(e)}"
    
    return results

# 目前只用到了OpenAI的模型

# def _upload_to_azure(file_paths: list, purpose: str, vector_store_id: str, results: dict):
#     """Azure OpenAI 文件上传实现"""
#     try:
#         from openai import AzureOpenAI
#         import os
        
#         client = AzureOpenAI(
#             api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
#             api_version=os.environ.get("OPENAI_API_VERSION", "2024-02-15-preview"),
#             azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
#         )
        
#         for file_path in file_paths:
#             try:
#                 file_path = Path(file_path)
#                 if not file_path.exists():
#                     results["failed_files"].append({
#                         "file": str(file_path),
#                         "error": "File not found"
#                     })
#                     continue
                
#                 print(f"📁 正在上传文件到Azure: {file_path.name}")
                
#                 with open(file_path, 'rb') as file:
#                     file_response = client.files.create(
#                         file=file,
#                         purpose=purpose
#                     )
                
#                 results["uploaded_files"].append({
#                     "file_id": file_response.id,
#                     "filename": file_response.filename,
#                     "purpose": file_response.purpose,
#                     "provider": "azure"
#                 })
#                 print(f"✅ Azure文件上传成功: {file_response.filename}")
                
#             except Exception as file_error:
#                 print(f"❌ Azure文件上传失败 {file_path.name}: {file_error}")
#                 results["failed_files"].append({
#                     "file": str(file_path),
#                     "error": str(file_error)
#                 })
        
#         results["success"] = True
#         results["message"] = f"Azure上传完成: {len(results['uploaded_files'])}个成功"
        
#     except ImportError:
#         results["success"] = False
#         results["error"] = "Azure OpenAI library not installed. Run: pip install openai[azure]"
#     except Exception as e:
#         results["success"] = False
#         results["error"] = f"Azure API错误: {str(e)}"
    
#     return results


# def _upload_to_anthropic(file_paths: list, purpose: str, results: dict):
#     """Anthropic Claude 文件上传实现"""
#     try:
#         import anthropic
#         import os
        
#         client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        
#         for file_path in file_paths:
#             try:
#                 file_path = Path(file_path)
#                 if not file_path.exists():
#                     results["failed_files"].append({
#                         "file": str(file_path),
#                         "error": "File not found"
#                     })
#                     continue
                
#                 print(f"📁 正在上传文件到Anthropic: {file_path.name}")
                
#                 # 注意：Anthropic的文件上传API可能不同，这里是示例
#                 # 实际实现需要根据Anthropic的具体API调整
#                 with open(file_path, 'rb') as file:
#                     file_content = file.read()
                
#                 results["uploaded_files"].append({
#                     "filename": file_path.name,
#                     "size": len(file_content),
#                     "provider": "anthropic",
#                     "note": "Anthropic files are typically handled differently"
#                 })
#                 print(f"✅ Anthropic文件处理完成: {file_path.name}")
                
#             except Exception as file_error:
#                 print(f"❌ Anthropic文件处理失败 {file_path.name}: {file_error}")
#                 results["failed_files"].append({
#                     "file": str(file_path),
#                     "error": str(file_error)
#                 })
        
#         results["success"] = True
#         results["message"] = f"Anthropic处理完成: {len(results['uploaded_files'])}个文件"
        
#     except ImportError:
#         results["success"] = False
#         results["error"] = "Anthropic library not installed. Run: pip install anthropic"
#     except Exception as e:
#         results["success"] = False
#         results["error"] = f"Anthropic API错误: {str(e)}"
    
#     return results


# def _upload_to_local(file_paths: list, purpose: str, results: dict):
#     """本地文件处理实现"""
#     import shutil
#     import os
#     from datetime import datetime
    
#     try:
#         # 创建本地存储目录
#         local_storage = Path("uploaded_files")
#         local_storage.mkdir(exist_ok=True)
        
#         for file_path in file_paths:
#             try:
#                 file_path = Path(file_path)
#                 if not file_path.exists():
#                     results["failed_files"].append({
#                         "file": str(file_path),
#                         "error": "File not found"
#                     })
#                     continue
                
#                 print(f"📁 正在处理本地文件: {file_path.name}")
                
#                 # 复制文件到本地存储
#                 destination = local_storage / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_path.name}"
#                 shutil.copy2(file_path, destination)
                
#                 results["uploaded_files"].append({
#                     "original_path": str(file_path),
#                     "stored_path": str(destination),
#                     "filename": file_path.name,
#                     "size": file_path.stat().st_size,
#                     "provider": "local"
#                 })
#                 print(f"✅ 本地文件存储成功: {destination}")
                
#             except Exception as file_error:
#                 print(f"❌ 本地文件处理失败 {file_path.name}: {file_error}")
#                 results["failed_files"].append({
#                     "file": str(file_path),
#                     "error": str(file_error)
#                 })
        
#         results["success"] = True
#         results["message"] = f"本地存储完成: {len(results['uploaded_files'])}个文件"
        
#     except Exception as e:
#         results["success"] = False
#         results["error"] = f"本地存储错误: {str(e)}"
    
#     return results