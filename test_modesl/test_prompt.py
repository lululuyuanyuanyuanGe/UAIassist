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
    file_path: list[str]





class TestPromptGraph():
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.graph = self._build_graph().compile()

    def _build_graph(self):
        graph = StateGraph(TestPromptState)

        graph.add_node("LLM_node_1", self._LLM_node_1)
        graph.add_node("LLM_node_2", self._LLM_node_2)
        graph.add_node("LLM_node_3", self._LLM_node_3)
        graph.add_node("LLM_summary", self._LLM_summary)

        graph.add_node("process_file_input", self._process_file_input)
        graph.add_conditional_edges("process_file_input", self._route_after_file_input)
        graph.add_edge("LLM_node_1", "LLM_summary")
        graph.add_edge("LLM_node_2", "LLM_summary")
        graph.add_edge("LLM_node_3", "LLM_summary")
        graph.add_edge("LLM_summary", END)

        graph.add_edge(START, "process_file_input")


        return graph

    def _process_file_input(self, state: TestPromptState) -> TestPromptState:
        """处理用户输入文件"""
        file_paths = [r"D:\asianInfo\ExcelAssist\燕云村case\[正文稿]关于印发《重庆市巴南区党内关怀办法（修订）》的通__知.doc"]
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
        prompt = """你作为一个文档分析专家，你现在需要仔细阅读文件，并根据文件内容，总结出关键信息，比如政策条例，规则等，详细说明，文档是用html格式写的，因此你需要忽略掉html标签的干扰，
        输出内容为json格式，key为文件名，value为文内容的总结。
        """

        message = [SystemMessage(content=prompt)] + state["messages"]
        

        model_response = invoke_model(model_name="Tongyi-Zhiwen/QwenLong-L1-32B", messages=message)
        state["messages"].append(AIMessage(content=model_response))
        print(model_response)
        return {
            "message" : AIMessage(content=model_response)
        }


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