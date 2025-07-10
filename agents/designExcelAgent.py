import sys
from pathlib import Path
import json

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated, Union
from datetime import datetime

from utilities.modelRelated import invoke_model, invoke_model_with_tools

from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv


from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

# import other agents
from agents.processUserInput import ProcessUserInputAgent
from agents.recallFilesAgent import RecallFilesAgent
from agents.filloutTable import FilloutTableAgent


class DesignExcelState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next_node: str
    template_structure: str
    user_feedback: str
    session_id: str
    template_path: str
    village_name: str

class DesignExcelAgent:
    def __init__(self):
        self.memory = MemorySaver()
        self.graph = self._build_graph().compile(checkpointer=self.memory)


    def _build_graph(self) -> StateGraph:
        graph = StateGraph(DesignExcelState)
        graph.add_node("collect_user_requirement", self._collect_user_requirement)
        graph.add_node("design_excel_template", self._design_excel_template)
        graph.add_node("generate_html_template", self._generate_html_template)

        graph.add_edge(START, "collect_user_requirement")
        graph.add_conditional_edges("collect_user_requirement", self._route_after_collect_user_requirement)
        graph.add_edge("design_excel_template", "generate_html_template")
        graph.add_edge("generate_html_template", END)
        return graph
    

    def _create_initial_state(self, session_id: str, village_name: str) -> DesignExcelState:
        """This function initializes the state of the design excel agent"""
        return {
            "messages": [],
            "next_node": "collect_user_requirement",
            "template_structure": "",
            "user_feedback": "",
            "session_id": session_id,
            "template_path": "",
            "village_name": ""
        }

    def _collect_user_requirement(self, state: DesignExcelState) -> DesignExcelState:
        """询问用户模版需求，或改进意见"""
        print("\n🔍 开始执行: _collect_user_requirement")
        print("=" * 50)
        
        if not state["template_structure"]:
            print("大模型设计的模板")

        user_feedback = input("请输入您的反馈：")
        print("✅ _collect_user_requirement 执行完成")
        print("=" * 50)
        return {"user_feedback": user_feedback}

    def _route_after_collect_user_requirement(self, state: DesignExcelState) -> str:
        """根据用户需求，设计模版"""
        system_prompt = f"""你是一个文本分析专家，根据收集到的用户输入总结你来判断下一步的路由节点，
        如果用户给出了肯定的答复则返回
        END
        否则返回
        design_excel_template
        你的返回为纯文本，不要返回任何其他内容或解释
        """

        response = invoke_model(model_name="deepseek-ai/DeepSeek-R1", 
                                           messages=[SystemMessage(content=system_prompt)])
        print("大模型返回的路由节点是：", response)
        return response


    def _design_excel_template(self, state: DesignExcelState) -> DesignExcelState:
        """根据用户需求，设计模版"""
        print("\n💬 开始执行: _chat_with_user_to_determine_template")
        print("=" * 50)
        
        with open("agent/data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            related_files = data[state["village_name"]]

        system_prompt = f"""你是一个Excel表格设计专家，你需要跟根据用户的需求，并且参考我们知识库里已收录的信息，
        来设计一个符合用户需求的表格。知识库里收录了所有可以利用的表格或者文档，表格是用户上传给我们的带有原始数据的表格，并且我们
        已经整理出了表格结构，以及总结，同样的，文档是用户已经上传的用于辅助填写表格的文件，里面包含一些政策信息，这些信息加上
        已有数据可以让我们推理出新的数据。你的任务是根据这些已有数据，文档和用户需求设计出一个新的Excel模板表格。你一定要确保
        设计出来的表格中每个表头都能有确切的数据来源，或者能根据其他信息推理出来。另外我也会把用户的反馈信息或者设计要求提供给你
        你也需要参考这些信息来设计模板或者改进设计。


        知识库信息：
        {related_files}


        请严格遵守以下输出规则
1. 提取表格的多级表头结构：
   - 使用嵌套的 key-value 形式表示层级关系；
   - 每一级表头应以对象形式展示其子级字段或子表头；
   - 不需要额外字段（如 null、isParent 等），仅保留结构清晰的层级映射；

2. 提供一个对该表格内容的简要总结：
   - 内容应包括表格用途、主要信息类别、适用范围等；
   - 语言简洁，不超过 150 字；

输出格式如下：
{{
  "表格结构": {{
    "顶层表头名称": {{
      "二级表头名称": [
        "字段1",
        "字段2"
      ]
    }}
  }},
  "表格总结": "该表格的主要用途及内容说明...",
  "额外信息": "该表格额外信息，例如填表人，填表时间，填表单位等"
}}



"""
        print("system_prompt和用户交互确定表格结构:\n ", system_prompt)
        print("📤 正在调用LLM进行表格结构确定...")
        user_input = state["user_feedback"]
        response = invoke_model(model_name="deepseek-ai/DeepSeek-R1", 
                                           messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
        
        print("返回结果：", response)

        
        print("✅ _chat_with_user_to_determine_template 执行完成")
        print("=" * 50)
        
        return {"template_structure": str(response),
                "next_node": "design_excel_template"
                }
    

    def  _generate_html_template(self, state: DesignExcelState) -> DesignExcelState:
        """根据模板生成html模版"""
        print("\n🔍 开始执行: _generate_html_template")
        print("=" * 50)
        system_prompt = f"""
你是一个精通 Excel 模板表格的专家，擅长根据 JSON 格式的表格结构摘要自动生成对应的 HTML 模板。

当我提供如下摘要（JSON 格式）时：

{{
  "表格结构": {{
    "一级表头1": {{
      "二级表头A": ["字段A1", "字段A2"],
      "二级表头B": ["字段B1", "..."]
    }},
    "一级表头2": {{
      "二级表头C": ["字段C1", "..."]
    }},
    "..." : {{ "...": ["...", "..."] }}
  }},
  "额外信息": {{
    "填表单位": "单位名称占位",
    "填表时间": "YYYY-MM-DD 占位",
    "其他说明": "...占位"
  }}
}}

请生成一个通用的 HTML 表格模板，要求：
1. 使用 <table> 与若干 <colgroup>，列数与最底层字段总数一致；
2. 第一行使用 <td colspan="..."> 占位展示“表格标题”；
3. 第二行按 “额外信息” 中键值顺序，生成合并单元格占位展示；
4. 第三行将所有“字段”扁平展开，按 JSON 结构顺序输出表头占位符；
5. 最后一行可留给审签/制表人占位；
6. HTML 代码应保持简洁、结构清晰，仅使用占位符，不包含任何具体业务名称或数据。

仅输出 HTML 模板代码，不要包含多余的解释或示例数据。
"""

        print("system_prompt和用户交互确定表格结构:\n ", system_prompt)
        print("📤 正在调用LLM进行表格结构确定...")
        response = invoke_model(model_name="deepseek-ai/DeepSeek-R1", 
                                           messages=[SystemMessage(content=system_prompt)])
        
        print("返回结果：", response)
        return state
    
    def run_design_excel_agent(self, session_id: str, village_name: str) -> DesignExcelState:
        """Run the design excel agent"""
        state = self._create_initial_state(session_id, village_name)
        final_state = self.graph.invoke(state)
        return final_state
    

if __name__ == "__main__":
    designExcelAgent = DesignExcelAgent()
    designExcelAgent.run_design_excel_agent(session_id="1", village_name="燕云村")