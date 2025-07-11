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
            "village_name": village_name
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
        system_prompt = """你是一个智能路由分析专家，负责分析用户反馈并决定下一步操作。

请仔细分析用户的输入内容，判断用户的意图和需求：

**路由规则：**
1. 如果用户表示满意、同意、确认或给出了明确的肯定回复（如"好的"、"可以"、"满意"、"没问题"等），返回：END

2. 如果用户提出了具体的需求、修改建议、新的要求，或者表达了不满意，返回：design_excel_template

3. 如果用户询问问题、要求解释或需要更多信息，返回：design_excel_template

**分析要点：**
- 关注用户的情感倾向（满意/不满意）
- 识别是否有具体的修改要求
- 判断用户是否需要进一步的设计工作

**重要提醒：**
- 只返回路由节点名称，不要添加任何解释或其他内容
- 返回值必须是：END 或 design_excel_template
- 当有疑问时，倾向于选择 design_excel_template 继续设计流程
"""

        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", 
                               messages=[SystemMessage(content=system_prompt), HumanMessage(content=state["user_feedback"])])
        print("大模型返回的路由节点是：", response)
        return response.strip()

    def _design_excel_template(self, state: DesignExcelState) -> DesignExcelState:
        """根据用户需求，设计模版"""
        print("\n💬 开始执行: _design_excel_template")
        print("=" * 50)
        
        with open("agents/data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            related_files = data.get(state["village_name"], {"表格": {}, "文档": {}})

        system_prompt = f"""你是一个专业的Excel表格设计专家，专门为村级行政管理设计高质量的数据表格模板。

## 🎯 任务目标
根据用户需求和现有数据资源，设计一个结构化、实用的Excel表格模板，确保每个字段都有明确的数据来源或计算依据。

## 📊 可用数据资源
以下是{state["village_name"]}的知识库资源：

### 📋 现有表格数据：
{json.dumps(related_files.get("表格", {}), ensure_ascii=False, indent=2)}

### 📄 政策文档资料：
{json.dumps(related_files.get("文档", {}), ensure_ascii=False, indent=2)}

## 🔍 设计原则
1. **数据可追溯性**：每个表头字段必须有明确的数据来源
   - 直接来源：现有表格中的字段
   - 推导来源：根据政策文档和现有数据可计算得出
   - 手工录入：需要村民或管理员填写的新信息

2. **结构合理性**：
   - 采用多级表头结构，逻辑清晰
   - 相关字段分组归类
   - 字段命名规范统一

3. **实用性导向**：
   - 符合村级行政管理实际需求
   - 便于数据录入和维护
   - 支持后续统计分析

## 🎨 用户反馈处理
用户反馈："{state["user_feedback"]}"

请根据用户反馈调整设计方案，如果是首次设计，请基于用户需求创建合适的模板。

## 📝 输出要求
严格按照以下JSON格式输出：

```json
{{
  "表格结构": {{
    "主要分类1": {{
      "子分类A": ["字段1", "字段2", "字段3"],
      "子分类B": ["字段4", "字段5"]
    }},
    "主要分类2": {{
      "子分类C": ["字段6", "字段7"]
    }}
  }},
  "表格总结": "详细说明该表格的用途、适用场景、主要功能和预期效果（100-200字）",
  "额外信息": {{
    "填表单位": "{state["village_name"]}",
    "填表时间": "填表日期占位符",
    "制表人": "制表人姓名占位符",
    "审核人": "审核人姓名占位符"
  }},
  "数据来源说明": {{
    "字段1": "来源：现有表格XXX",
    "字段2": "来源：根据政策文档XXX计算",
    "字段3": "来源：需要手工录入"
  }}
}}
```

## ⚠️ 注意事项
- 确保所有字段都有明确的数据来源
- 表格结构要符合Excel操作习惯
- 考虑数据录入的便利性和准确性
- 如果现有资源不足，请在"数据来源说明"中明确标注
"""

        print("📤 正在调用LLM进行表格结构设计...")
        user_input = state["user_feedback"]
        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", 
                               messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
        
        print("返回结果：", response)
        
        print("✅ _design_excel_template 执行完成")
        print("=" * 50)
        
        return {"template_structure": str(response),
                "next_node": "generate_html_template"}
    
    def _generate_html_template(self, state: DesignExcelState) -> DesignExcelState:
        """根据模板生成html模版"""
        print("\n🔍 开始执行: _generate_html_template")
        print("=" * 50)
        
        system_prompt = f"""你是一个专业的HTML表格生成专家，擅长将JSON格式的表格结构转换为美观、实用的HTML表格模板。

## 📋 任务要求
根据提供的JSON表格结构，生成一个完整的HTML表格模板，用于村级行政管理的数据录入和展示。

## 🎨 设计规范

### 1. 表格结构要求
- 使用标准的`<table>`标签
- 合理设置`<colgroup>`，列数与最底层字段总数匹配
- 使用`colspan`和`rowspan`实现多级表头
- 保持表格结构清晰、对齐美观

### 2. 表头层次设计
- **第一行**：表格标题（全表合并）
- **第二行**：额外信息行（填表单位、时间、制表人等）
- **第三行及以后**：多级表头结构
- **最后几行**：数据录入区域（至少3-5行示例）

### 3. 样式要求
- 添加基本的CSS样式，确保表格美观
- 表头使用深色背景，数据区域使用浅色背景
- 设置合适的边框、间距和字体
- 确保表格在不同设备上显示良好

### 4. 内容填充
- 表头使用实际的字段名称
- 数据区域使用占位符（如"请输入..."）
- 额外信息区域使用带占位符的实际标签

## 🔧 HTML结构示例
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>表格模板</title>
    <style>
        /* 在这里添加CSS样式 */
    </style>
</head>
<body>
    <table>
        <colgroup>
            <!-- 根据实际列数设置 -->
        </colgroup>
        <thead>
            <!-- 表头结构 -->
        </thead>
        <tbody>
            <!-- 数据录入区域 -->
        </tbody>
        <tfoot>
            <!-- 签名区域 -->
        </tfoot>
    </table>
</body>
</html>
```

## 📊 输入的JSON结构
{state["template_structure"]}

## 🎯 输出要求
- 生成完整的HTML文档，包含CSS样式
- 确保表格结构与JSON描述完全匹配
- 提供美观的视觉效果和良好的用户体验
- 代码结构清晰，便于后续修改

请直接输出完整的HTML代码，不要添加任何解释或说明文字。
"""

        print("📤 正在调用LLM进行HTML模板生成...")
        response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", 
                               messages=[SystemMessage(content=system_prompt)])
        
        print("返回结果：", response)
        
        # 保存HTML模板到文件
        html_filename = f"{state['village_name']}_表格模板_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        html_path = Path("完整案列") / html_filename
        
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(response)
            print(f"✅ HTML模板已保存到: {html_path}")
        except Exception as e:
            print(f"❌ 保存HTML模板失败: {e}")
        
        print("✅ _generate_html_template 执行完成")
        print("=" * 50)
        
        return {"template_path": str(html_path)}
    
    def run_design_excel_agent(self, session_id: str, village_name: str) -> DesignExcelState:
        """Run the design excel agent"""
        config = {"configurable": {"thread_id": session_id}}
        state = self._create_initial_state(session_id, village_name)
        final_state = self.graph.invoke(state, config=config)
        return final_state
    

if __name__ == "__main__":
    designExcelAgent = DesignExcelAgent()
    designExcelAgent.run_design_excel_agent(session_id="1", village_name="燕云村")