import sys
from pathlib import Path
import json

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from typing import Dict, List, Optional, Any, TypedDict, Annotated, Union
from datetime import datetime

from utils.modelRelated import invoke_model
from utils.clean_response import clean_json_response
from utils.html_generator import generate_header_html
from utils.file_process import extract_summary_for_each_file

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
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agents.processUserInput import ProcessUserInputAgent

load_dotenv()




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

        graph.add_edge(START, "design_excel_template")
        graph.add_edge("design_excel_template", "collect_user_requirement")
        graph.add_conditional_edges("collect_user_requirement", self._route_after_collect_user_requirement)
        graph.add_edge("generate_html_template", END)
        return graph
    
    def _create_initial_state(self, session_id: str, village_name: str, user_feedback: str = "") -> DesignExcelState:
        """This function initializes the state of the design excel agent"""
        return {
            "messages": [],
            "template_structure": "",
            "user_feedback": "",
            "session_id": session_id,
            "template_path": "",
            "village_name": village_name,
            "user_feedback": user_feedback,
            "next_node": "collect_user_requirement"
        }

    def _design_excel_template(self, state: DesignExcelState) -> DesignExcelState:
        """根据用户需求，设计模版"""
        print("\n💬 开始执行: _design_excel_template")
        print("=" * 50)
        
        with open("agents/data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            related_files = data.get(state["village_name"], {"表格": {}, "文档": {}})
            related_files = extract_summary_for_each_file(related_files)

        system_prompt = f"""你是一个专业的Excel表格设计专家，专门为村级行政管理设计高质量的数据表格模板。

## 任务目标
根据用户需求和现有数据资源，设计一个结构化、实用的Excel表格模板，确保每个字段都有明确的数据来源或计算依据。

## 可用数据资源
以下是{state["village_name"]}的知识库资源：

{related_files}

## 🔍 设计原则
1. **数据可追溯性**：每个表头字段必须有明确的数据来源
   - 直接来源：现有表格中的字段，请将表格名称包含在内
   - 推导来源：根据政策文档和现有数据可计算得出
   - 手工录入：需要村民或管理员填写的新信息
   - 注意所有数据来源必须有明确的数据来源，必须严格参考现有表格或者政策文档来设计

2. **结构合理性**：
   - 相关字段分组归类
   - 字段命名规范统一
   - 支持复杂计算和子字段分解

3. **实用性导向**：
   - 符合村级行政管理实际需求
   - 便于数据录入和维护
   - 支持后续统计分析

## 用户反馈或改进意见
用户反馈："{state["user_feedback"]}"
## 上一次设计的表格结构
{state["template_structure"]}

请根据用户反馈调整设计方案，如果是首次设计，请基于用户需求创建合适的模板。

## 📝 输出要求
严格按照以下JSON格式输出，支持混合的表格结构：

**标准格式**：
{{
  "表格标题": "根据用户需求和表格用途设计的具体标题",
  "表格结构": {{
    "简单字段": [],
    "复杂字段": {{
      "值": [],
      "分解": {{
        "子字段1": [],
        "子字段2": []
      }},
      "规则": "子字段1 + 子字段2"
    }}
  }}
}}

**字段结构规则**：

**1. 简单字段（最底层字段，直接包含数据）**：
- 格式：`"字段名": []`
- 用于：直接存储数据值的字段，如"序号"、"姓名"、"身份证号"等
- 不需要"值"、"分解"、"规则"结构

**2. 复杂字段（包含子字段的父字段）**：
- 格式：使用"值"、"分解"、"规则"结构
- **"值"**：该父字段本身的数据值处理方式：
  - 如果用户明确需要父字段显示汇总值，应包含计算方法或数据来源
  - 如果父字段仅作为分组标题，则保持空数组[]
  - 根据用户需求和表格实际用途智能判断
- **"分解"**：该字段的子字段组成部分
- **"规则"**：子字段之间的计算关系（如"子字段1 + 子字段2"，无规则则为空字符串""）

**设计示例**：
{{
  "表格标题": "七田村2024年低保补贴汇总表",
  "表格结构": {{
    "序号": [],
    "户主姓名": [],
    "身份证号码": [],
    "低保证号": [],
    "基本信息": {{
      "值": [],
      "分解": {{
        "姓名": [],
        "性别": []
      }},
      "规则": ""
    }},
    "保障人数": {{
      "值": ["推理规则: 重点保障人数 + 残疾人数的汇总"],
      "分解": {{
        "重点保障人数": [],
        "残疾人数": []
      }},
      "规则": "重点保障人数 + 残疾人数"
    }},
    "领取金额": {{
      "值": ["推理规则: 家庭补差 + 重点救助60元 + 重点救助100元 + 残疾人救助的总计"],
      "分解": {{
        "家庭补差": [],
        "重点救助60元": [],
        "重点救助100元": [],
        "残疾人救助": []
      }},
      "规则": "家庭补差 + 重点救助60元 + 重点救助100元 + 残疾人救助"
    }},
    "领款人签字": [],
    "领款时间": []
  }}
}}

**表格标题要求**：
- 根据用户提问和表格用途设计具体、明确的标题
- 标题应体现表格的主要功能和使用场景
- 格式示例："XX村XX年度XX登记表"、"XX村XX补贴申领表"等

## "值"字段智能填充规则
根据用户需求和表格用途，智能决定复杂字段的"值"部分：

1. **需要填充"值"的情况**：
   - 用户明确提到需要显示总计/汇总/合计数值
   - 表格用途需要显示父字段的计算结果
   - 监管或报表要求显示汇总数据
   - 示例："值": ["推理规则: 根据分解中所有子字段求和"]

2. **保持"值"为空的情况**：
   - 父字段仅用于分组组织，无实际数值意义
   - 用户未明确要求显示父字段数值
   - 表格设计中父字段作为分类标题使用
   - 示例："值": []

3. **"值"字段内容格式**：
   - 数据来源："值": ["来源文件名: 字段名"]
   - 计算规则："值": ["推理规则: 具体计算方法或公式"]
   - 手工录入："值": ["推理规则: 需要手工填入汇总数值"]

## ⚠️ 注意事项
- **关键原则**：只有包含子字段的复杂字段才使用"值"、"分解"、"规则"结构
- **简单字段**：直接使用 `"字段名": []` 格式，不使用复杂结构
- **复杂字段**：必须包含"值"、"分解"、"规则"三个属性
- **子字段**：在"分解"中的子字段使用简单的 `"子字段名": []` 格式
- **智能"值"处理**：根据用户需求和表格用途，智能决定"值"字段是否需要填充计算方法
  - 用户有明确汇总需求时，"值"应包含计算方法或数据来源
  - 仅作为分组标题时，"值"保持空数组[]
- 确保所有字段都有明确的数据来源
- 表格结构要符合Excel操作习惯和CSV数据重构需求
- **数据来源仅用于内部设计参考**：不要将数据来源作为表头字段或在表格中显示

## 输出要求
- 不需要做出额外的任何解释，直接输出JSON格即可
"""
        
  #       """,
  # "数据来源说明": {{
  #   "字段1": "来源：现有表格XXX",
  #   "字段2": "来源：根据政策文档XXX计算",
  #   "字段3": "来源：需要手工录入"
  # }}
  
  # ,
  # "表格总结": "详细说明该表格的用途、适用场景、主要功能和预期效果（100-200字）",
  # "额外信息": {{
  #   "填表单位": "{state["village_name"]}",
  #   "填表时间": "填表日期占位符",
  #   "制表人": "制表人姓名占位符",
  #   "审核人": "审核人姓名占位符"
  # }}
  
  # """
        
        print("📤 正在调用LLM进行表格结构设计...")
        print("提示词：", system_prompt)
        user_input = state["user_feedback"]
        print("用户输入：", user_input)
        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", 
                               messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
        
        # Clean the response to handle markdown code blocks
        cleaned_response = clean_json_response(response)

        print("cleaned_response：", cleaned_response)
        
        print("✅ _design_excel_template 执行完成")
        print("=" * 50)
        
        return {"template_structure": str(cleaned_response),
                "next_node": "generate_html_template"}
    

    def _collect_user_requirement(self, state: DesignExcelState) -> DesignExcelState:
        """询问用户模版需求，或改进意见"""
        print("\n🔍 开始执行: _collect_user_requirement")
        print("=" * 50)
        template_stucture = state["template_structure"]
        previous_AI_messages = AIMessage(content=template_stucture + "\n" + "请根据以上内容，给出您的反馈")
        processUserInputAgent = ProcessUserInputAgent()
        processUserInputAgent_final_state = processUserInputAgent.run_process_user_input_agent(session_id=state["session_id"], 
                                                                                               previous_AI_messages=previous_AI_messages, current_node="design_excel_template")
        
        print("processUserInputAgent_final_state：", processUserInputAgent_final_state)
        
        # Parse the JSON string to get the actual dictionary
        try:
            summary_data = json.loads(processUserInputAgent_final_state[0])
            user_feedback = summary_data["summary"]
            next_node = summary_data["next_node"]
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"❌ 解析processUserInputAgent返回数据时出错: {e}")
            user_feedback = "用户反馈解析失败"
            next_node = "design_excel_template"

        print("✅ _collect_user_requirement 执行完成")
        print("=" * 50)
        return {"user_feedback": user_feedback, "next_node": next_node}
    
    def _route_after_collect_user_requirement(self, state: DesignExcelState) -> str:
        """根据用户反馈，决定下一步操作"""
        next_node = state["next_node"]
        return next_node

    
    def _generate_html_template(self, state: DesignExcelState) -> DesignExcelState:
        """根据模板生成html模版（使用代码生成，替代LLM）"""
        print("\n🔍 开始执行: _generate_html_template（代码生成模式）")
        print("=" * 50)
        
        try:
            # Parse the template structure JSON
            template_structure = state["template_structure"]
            print(f"📊 正在解析模板结构: {template_structure}")
            
            # Generate HTML using code instead of LLM
            print("🔧 正在使用代码生成HTML...")
            cleaned_response = generate_header_html(template_structure)
            print(f"✅ HTML代码生成成功，长度: {len(cleaned_response)} 字符")
            print(f"🔍 生成的HTML预览: {cleaned_response[:200]}...")
            
        except Exception as e:
            print(f"❌ HTML生成失败: {e}")
            # Fallback HTML
            cleaned_response = f"<html><body><table><tr><td><b>{state['village_name']}表格模板</b></td></tr></table></body></html>"
        
        # 保存HTML模板到文件
        html_filename = f"{state['village_name']}_表格模板_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        html_path = Path(f"conversations/{state['session_id']}/user_uploaded_files/template/") / html_filename
        
        try:
            # Ensure directory exists
            html_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(cleaned_response)
            print(f"✅ HTML模板已保存到: {html_path}")
        except Exception as e:
            print(f"❌ 保存HTML模板失败: {e}")
        
        print("✅ _generate_html_template 执行完成")
        print("=" * 50)
        
        return {"template_path": str(html_path)}
    
    def run_design_excel_agent(self, session_id: str, village_name: str, user_feedback: str = "") -> DesignExcelState:
        """Run the design excel agent"""
        config = {"configurable": {"thread_id": session_id}}
        state = self._create_initial_state(session_id, village_name, user_feedback)
        final_state = self.graph.invoke(state, config=config)
        return final_state
    

if __name__ == "__main__":
    # Original agent test
    designExcelAgent = DesignExcelAgent()
    designExcelAgent.run_design_excel_agent(session_id="1", village_name="燕云村")