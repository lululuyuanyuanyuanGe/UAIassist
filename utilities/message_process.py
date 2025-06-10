from typing import TypedDict, Annotated
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

def build_complex_message(system_prompt: str, file_paths: list[str], client: OpenAI, user_input: str) -> list[dict]:
    """将用户的文本输入和文件上传整合在一起"""
    # 用OpenAI内置函数将文件上传至其服务器
    file_ids =[]
    for file_path in file_paths:
        file_response = client.files.create(
            file = open(file_path, 'rb'),
            purpose = "user_data"
        )
        file_ids.append(file_response.id)
    
    # 创建文件，文本混合输入
    return [
        {
            "role": "system", "content": system_prompt
        },
        {
            "role": "user", "content": [
                {
                    "type": "text",
                    "text": user_input
                },
                *[
                    {
                        "type": "inptu_file",
                        "file_id": file_id
                    } for file_id in file_ids
                ]
            ]
        }
    ]
