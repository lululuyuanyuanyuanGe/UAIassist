from openai import OpenAI
from typing import Dict, List, Optional, Any, TypedDict, Annotated
from dotenv import load_dotenv
import os

from utilities.file_process import retrieve_file_content, read_processed_files_content, _read_text_auto

from langgraph.graph import StateGraph, END, START
from langgraph.constants import Send
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()
 

def invoke_model(model_name : str, messages : List[BaseMessage]) -> str:
    """调用大模型"""
    llm = ChatOpenAI(
        model = model_name,
        api_key=os.getenv("SILICONFLOW_API_KEY"), 
        base_url="https://api.siliconflow.cn/v1",
        streaming=True,
        temperature=0.2  # 启用流式
    )

    full_response = ""

    for chunk in llm.stream(messages):
        chunk_content = chunk.content
        print(chunk_content, end="", flush=True)
        full_response += chunk_content
    
    return full_response


class TestPromptState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]





class TestPromptGraph():
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.graph = self._build_graph().compile()

    def _build_graph(self):
        graph = StateGraph(TestPromptState)


        graph.add_node("process_file_input", self._process_file_input)
        graph.add_node("LLM_node_3", self._LLM_node_3)

        graph.add_edge(START, "process_file_input")
        graph.add_edge("process_file_input", "LLM_node_3")

        graph.add_edge("LLM_node_3", END)


        return graph

    def _process_file_input(self, state: TestPromptState) -> TestPromptState:
        """处理用户输入文件"""
        file_paths = [r"D:\asianInfo\数据\七田村\七田村村信息简介.docx"]
        processed_content_paths = retrieve_file_content(file_paths, "1")

        # 读取文档信息
        processed_content = read_processed_files_content(processed_content_paths)
        state["messages"].append(HumanMessage(content=processed_content))

        return state
    
    def _route_after_file_input(self, state: TestPromptState) -> TestPromptState:
        sends = []
        sends.append(Send("LLM_node_1", state))
        sends.append(Send("LLM_node_2", state))
        sends.append(Send("LLM_node_3", state))
        return sends


    def _LLM_node_3(self, state: TestPromptState) -> TestPromptState:
        """调用大模型"""
        prompt = """你是一位专业的文档分析专家。请阅读提供的 HTML 格式政策类文件，并对其进行简要总结。

总结要求如下：

1. **忽略所有 HTML 标签**（如 <p>、<div>、<span>、<table> 等），仅关注文本内容；
2. 总结内容为文件的简介，包含了哪些信息，文件内容等
3. 总结语言应简洁明了、条理清晰、逻辑性强，避免冗长和具体数字；
4. 输出格式为严格的 JSON 格式：
   - 键（Key）为文件名；
   - 值（Value）为对该文件内容的简要总结；
5. 若提供多个文件，需分别处理并合并输出为一个 JSON 对象；
6. 保持输出语言与输入文档一致（若文档为中文，则输出中文）；

请根据上述要求，对提供的 HTML 文件内容进行分析并返回结果。"""

        message = [SystemMessage(content=prompt)] + state["messages"]
        

        model_response = invoke_model(model_name="Qwen/Qwen3-8B", messages=message)
        state["messages"].append(AIMessage(content=model_response))
        print(model_response)
        state["messages"] = []

    def run_test_prompt(self):
        """运行测试"""
        state = TestPromptState()
        test_prompt_graph = TestPromptGraph()
        test_prompt_graph.graph.invoke(state)


test_prompt_graph = TestPromptGraph()
graph = test_prompt_graph.graph



if __name__ == "__main__":
    test_prompt_graph = TestPromptGraph()
    test_prompt_graph.run_test_prompt()