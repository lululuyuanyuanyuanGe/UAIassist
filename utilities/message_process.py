from typing import TypedDict, Annotated, List
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