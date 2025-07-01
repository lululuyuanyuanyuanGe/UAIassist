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
        file_paths = [r"D:\asianInfo\数据\郭坡村\2024低保公示格式（统一格式）.xlsx"]
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

    def _LLM_node_1(self, state: TestPromptState) -> TestPromptState:
        pass

    def _LLM_node_2(self, state: TestPromptState) -> TestPromptState:
        pass

    def _LLM_summary(self, state: TestPromptState) -> TestPromptState:
        pass

    def _LLM_node_3(self, state: TestPromptState) -> TestPromptState:
        """调用大模型"""
        prompt = """你是一位专业的文档分析专家。请阅读用户上传的 HTML 格式的 Excel 文件，并完成以下任务：

1. 提取表格的多级表头结构；
   - 使用嵌套的 key-value 形式表示层级关系；
   - 每一级表头应以对象形式展示其子级字段或子表头；
   - 不需要额外字段（如 null、isParent 等），仅保留结构清晰的层级映射；

2. 提供一个对该表格内容的简要总结；
   - 内容应包括表格用途、主要信息类别、适用范围等；
   - 语言简洁，不超过 150 字；

输出格式如下：
{
  "表格结构": {
    "顶层表头名称": {
      "二级表头名称": [
        "字段1",
        "字段2",
        ...
      ],
      ...
    },
    ...
  },
  "表格总结": "该表格的主要用途及内容说明..."
}

请忽略所有 HTML 样式标签，只关注表格结构和语义信息。"""

        message = [SystemMessage(content=prompt)] + state["messages"]
        

        model_response = invoke_model(model_name="Tongyi-Zhiwen/QwenLong-L1-32B", messages=message)
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