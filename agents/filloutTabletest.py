import sys
from pathlib import Path
import io
import contextlib

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, filter_out_system_messages
from utilities.file_process import detect_and_process_file_paths, retrieve_file_content, read_txt_file
from utilities.modelRelated import invoke_model

import uuid
import json
import os
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
# from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt, interrupt
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool


# import other agents
from agents.processUserInput import ProcessUserInputAgent

load_dotenv()

class FilloutTableState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    data_file_path: list[str]
    supplement_files_path: list[str]
    template_file: str
    rules: str
    combined_data: str
    final_table: str
    styled_html_table: str
    error_message: str
    execution_successful: bool
    retry: int



class FilloutTableAgent:
    def __init__(self):
        self.graph = self._build_graph()
        



    def _build_graph(self):
        """Build the LangGraph workflow for filling out tables"""
        graph = StateGraph(FilloutTableState)
        
        # Add nodes
        graph.add_node("combine_data", self._combine_data)
        graph.add_node("generate_html_table", self._generate_html_table)
        graph.add_node("validate_html_table", self._validate_html_table)
        graph.add_node("style_html_table", self._style_html_table)
        graph.add_node("convert_html_to_excel", self._convert_html_to_excel)
        
        # Define the workflow
        graph.add_edge(START, "combine_data")
        graph.add_edge("combine_data", "generate_html_table")
        graph.add_edge("generate_html_table", "validate_html_table")
        graph.add_edge("validate_html_table", "style_html_table")
        graph.add_edge("style_html_table", "convert_html_to_excel")
        graph.add_edge("convert_html_to_excel", END)

        
        # Compile the graph
        return graph.compile()

    
    def create_initialize_state(self, template_file: str = None, rules: str = None, data_file_path: list[str] = None, supplement_files_path: list[str] = None) -> FilloutTableState:
        """This node will initialize the state of the graph"""
        return {
            "messages": [],
            "data_file_path": data_file_path,
            "supplement_files_path": supplement_files_path,
            "template_file": template_file,
            "rules": rules,
            "combined_data": "",
            "final_table": "",
            "styled_html_table": "",
            "error_message": "",
            "execution_successful": True,
            "retry": 0,
        }

    def _combine_data(self, state: FilloutTableState) -> FilloutTableState:
        """This node will combined all the required files into a single text file.
        and that is ready to feed to the model"""
        file_content = []
        
        # Combine data files
        for file in state["data_file_path"]:
            content = file + "\n" + read_txt_file(file)
            file_content.append(f"=== Data File: {Path(file).name} ===\n{content}\n")
        
        # Combine supplement files
        if state.get("supplement_files_path"):
            for file in state["supplement_files_path"]:
                content = file + "\n" + read_txt_file(file)
                file_content.append(f"=== Supplement File: {Path(file).name} ===\n{content}\n")
        
        # Add template file
        if state["template_file"]:
            content = state["template_file"] + "\n" + read_txt_file(state["template_file"])
            file_content.append(f"=== Template File: {Path(state['template_file']).name} ===\n{content}\n")

        # Add rules
        if state["rules"]:
            file_content.append(f"=== Rules ===\n{state['rules']}\n")
        
        combined_data = "\n".join(file_content)
        print(f"📋 Combined data from {len(file_content)} sources")
        combined_data = self._clean_html_content(combined_data)
        return {
            "combined_data": combined_data
        }
        


    def _clean_html_content(self, html_content: str) -> str:
        """清理HTML内容中的过多空白字符和非断行空格"""
        try:
            import re
            
            # 替换4个以上连续的&nbsp;为最多3个
            html_content = re.sub(r'(&nbsp;){4,}', r'&nbsp;&nbsp;&nbsp;', html_content)
            
            # 替换过多的空白字符
            html_content = re.sub(r'\s{4,}', ' ', html_content)
            
            # 移除多余的换行符
            html_content = re.sub(r'\n\s*\n', '\n', html_content)
            
            print(f"✅ HTML内容已清理，长度: {len(html_content)} 字符")
            
            return html_content
            
        except Exception as e:
            print(f"⚠️ HTML清理失败: {e}")
            return html_content


    def _generate_html_table(self, state: FilloutTableState) -> FilloutTableState:
        """直接生成完整的HTML表格，无需代码执行"""

        system_prompt = f"""你是一位专业的智能表格填写专家，擅长分析结构化数据并自动生成完整的HTML表格。

【核心任务】
根据提供的数据文件、模板表格和补充规则，直接生成一个完整填写好的HTML表格。

【输入材料分析】
1. **模板表格**：包含表头结构和格式要求
2. **数据文件**：包含需要填入的原始数据
3. **补充规则**：包含计算公式、筛选条件、填写规范等

【处理要求】

**数据提取与映射：**
- 仔细分析模板表格的表头结构，识别每个字段的含义
- 从数据文件中提取对应的信息，建立字段映射关系
- 对于找不到直接对应的字段，根据补充规则进行推理计算

**计算逻辑处理：**
- 党龄计算：根据转正时间计算到2024年12月31日的年限
- 补贴金额：严格按照补充文件中的标准进行计算
- 年龄计算：根据身份证号或出生日期计算实际年龄
- 其他计算字段：根据规则文档进行相应计算

**数据完整性：**
- 确保所有数据行都被正确处理，不遗漏任何记录
- 对于缺失数据，根据上下文和规则进行合理填充
- 删除模板中的空白行，只保留有效数据

**HTML格式要求：**
- 保持与原模板完全一致的表格结构
- 保留原有的HTML标签、属性和样式
- 确保生成的HTML代码规范、完整、可解析

【输出格式】
请直接返回完整的HTML表格代码，包含：
1. 完整的HTML文档结构（如果原模板有）
2. 所有表头和数据行
3. 正确的HTML标签闭合
4. 与模板一致的格式和样式

【质量标准】
✓ 数据准确性：所有计算结果必须正确
✓ 完整性：不遗漏任何数据记录
✓ 格式一致性：与模板表格格式完全一致
✓ HTML规范性：生成的代码符合HTML标准

【注意事项】
- 严格按照补充文件中的计算规则执行
- 注意日期格式的统一处理
- 确保数值计算的精确性
- 保持表格的专业性和可读性

---

【数据文件和补充规则】
{state["combined_data"]}

【模板表格结构】
{state.get("template_file", "未提供模板文件")}

请基于以上材料，直接生成完整填写好的HTML表格："""

        print("🤖 正在生成HTML表格...")
        response = invoke_model(model_name="baidu/ERNIE-4.5-300B-A47B", messages=[SystemMessage(content=system_prompt)])
        print("✅ HTML表格生成完成")
        
        # 清理生成的HTML内容
        cleaned_response = self._clean_html_content(response)
        
        return {
            "final_table": cleaned_response,
            "messages": [AIMessage(content="HTML表格已生成完成")]
        }

    def _validate_html_table(self, state: FilloutTableState) -> FilloutTableState:
        """这个节点用于验证模型生成的html表格是否符合要求，并提出修改意见"""
        try:
            # Get the final table content
            final_table = state.get("final_table", "")
            
            if not final_table:
                print("❌ 没有找到最终表格内容")
                return {"error_message": "没有找到最终表格内容"}
            
            # If final_table is a file path, read the content
            if isinstance(final_table, str) and Path(final_table).exists():
                html_table_content = read_txt_file(final_table)
            else:
                html_table_content = final_table
            
            # Clean up the HTML content before validation
            html_table_content = self._clean_html_content(html_table_content)
            
            # Truncate content if too long to prevent token limit issues
            if len(html_table_content) > 8000:
                html_table_content = html_table_content[:8000] + "...[内容已截断]"
                print(f"⚠️ 验证内容过长，已截断至8000字符")
            
            system_prompt = f"""
            你需要根据用户提供的模板表格，数据表格和文档来判断模型生成的html表格是否符合要求，并提出修改意见，
            所有文件都是由html构建的，你需要根据html的结构和内容来判断模型生成的html表格是否符合要求，表头结构是否符合模板表头，
            数据是否正确，是否完整，数据计算是否正确

            下面是当前生成的html表格
            {html_table_content}

            下面是用户提供的模板，数据表格和文档
            {state["combined_data"][:5000]}

            如果需要修改请直接返回修改后的html表格，否则返回[No]
            """
            
            print("🔍 正在验证生成的HTML表格...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
            
            if response.strip() == "[No]":
                print("✅ 表格验证通过，无需修改")
                # Return current state unchanged - this is crucial!
                return {}
            else:
                print("🔄 表格验证发现问题，已修改")
                # Clean the modified HTML table as well
                cleaned_response = self._clean_html_content(response)
                return {"final_table": cleaned_response}
                
        except Exception as e:
            print(f"❌ 验证过程中发生错误: {e}")
            return {"error_message": f"验证失败: {str(e)}"}



    def _style_html_table(self, state: FilloutTableState) -> FilloutTableState:
        """这个节点用于把通过代码构建的html表格进行样式调整，使其符合用户的需求"""
        try:
            # Get the final table content
            final_table = state.get("final_table", "")
            
            if not final_table:
                print("❌ 没有找到HTML表格内容")
                return {"error_message": "没有找到HTML表格内容"}
            
            # If final_table is a file path, read the content
            if isinstance(final_table, str) and Path(final_table).exists():
                html_content = read_txt_file(final_table)
            else:
                html_content = final_table
            
            # Clean up the HTML content before styling
            html_content = self._clean_html_content(html_content)
            
            # Truncate content if too long to prevent token limit issues
            if len(html_content) > 8000:
                html_content = html_content[:8000] + "...[内容已截断]"
                print(f"⚠️ 样式调整内容过长，已截断至8000字符")
            
            system_prompt = f"""你是一位擅长美化 HTML 表格的专业样式设计专家。接下来我将提供一份由 Excel 转换而来的 HTML 表格文件。  
            你的任务是：  
            1. 对表格的整体样式进行美化，使其更加美观、清晰、专业；  
            2. 所有样式需直接以 CSS 的形式嵌入到 HTML 文件中（可使用 `<style>` 标签），避免依赖外部样式文件；  
            3. 保持原始表格结构和内容不变，仅对其外观进行优化调整；  
            4. 输出结果请直接返回完整的 HTML 文件代码（包括样式和表格内容）。

            以下是当前的 HTML 表格文件内容：
            {html_content}
            """
            
            print("🎨 正在美化HTML表格样式...")
            response = invoke_model(model_name="deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt)])
            
            print("✅ 表格样式美化完成")
            # Clean the styled HTML as well
            cleaned_response = self._clean_html_content(response)
            return {"styled_html_table": cleaned_response}
            
        except Exception as e:
            print(f"❌ 样式调整过程中发生错误: {e}")
            return {"error_message": f"样式调整失败: {str(e)}"}

    def _convert_html_to_excel(self, state: FilloutTableState) -> FilloutTableState:
        """把通过代码构建的html表格通过libreoffice转换为excel表格"""
        try:
            import subprocess
            import tempfile
            import os
            
            # Get the HTML content from state
            html_content = state.get("styled_html_table", state.get("final_table", ""))
            
            if not html_content:
                print("❌ 没有找到HTML表格内容")
                return {"error_message": "没有找到HTML表格内容"}
            
            # If final_table is a file path, read the content
            if isinstance(html_content, str) and Path(html_content).exists():
                html_content = read_txt_file(html_content)
            
            # Create temporary HTML file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                temp_html.write(html_content)
                temp_html_path = temp_html.name
            
            # Output paths
            output_dir = Path("agents/output")
            output_dir.mkdir(exist_ok=True)
            
            html_output_path = output_dir / "老党员补贴_结果.html"
            excel_output_path = output_dir / "老党员补贴_结果.xlsx"
            
            # Save the final HTML file
            try:
                with open(html_output_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"✅ HTML文件已保存: {html_output_path}")
            except Exception as e:
                print(f"❌ 保存HTML文件失败: {e}")
            
            # Convert to Excel using LibreOffice
            try:
                # Use the specified LibreOffice path
                libreoffice_path = r"D:\LibreOffice\program\soffice.exe"
                
                # Check if LibreOffice exists
                if not os.path.exists(libreoffice_path):
                    print(f"❌ 未找到LibreOffice: {libreoffice_path}")
                    return {"error_message": f"LibreOffice not found at {libreoffice_path}"}
                
                # Convert HTML to Excel using LibreOffice
                cmd = [
                    libreoffice_path,
                    '--headless',
                    '--convert-to', 'xlsx',
                    '--outdir', str(output_dir),
                    temp_html_path
                ]
                
                print(f"🔄 正在转换HTML到Excel...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print(f"✅ Excel文件已生成: {excel_output_path}")
                else:
                    print(f"❌ LibreOffice转换失败: {result.stderr}")
                    return {"error_message": f"LibreOffice conversion failed: {result.stderr}"}
                    
            except subprocess.TimeoutExpired:
                print("❌ LibreOffice转换超时")
                return {"error_message": "LibreOffice conversion timeout"}
            except Exception as e:
                print(f"❌ Excel转换失败: {e}")
                return {"error_message": f"Excel conversion failed: {str(e)}"}
            
            # Clean up temporary file
            try:
                os.unlink(temp_html_path)
            except Exception as e:
                print(f"⚠️ 清理临时文件失败: {e}")
            
            return {
                "final_table": str(html_output_path),
                "messages": [AIMessage(content=f"表格填写完成！\n- HTML文件: {html_output_path}\n- Excel文件: {excel_output_path}")]
            }
            
        except Exception as e:
            print(f"❌ 转换过程中发生错误: {e}")
            return {"error_message": f"转换失败: {str(e)}"}

    def run_fillout_table_agent(self, user_input: str, session_id: str = "1") -> None:
        """This function will run the fillout table agent"""
        initial_state = self.create_initialize_state(template_file = r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\老党员补贴.txt", 
                                                        rules = """党员补助列需要你智能计算，规则如下，党龄需要根据党员名册中的转正时间计算，（1）党龄40—49年的，补助标准为：100元/月；
（2）党龄50—54年的，补助标准为：120元/月；
（3）党龄55年及以上的，补助标准为：150元/月。
以上补助从党员党龄达到相关年限的次月起按月发放。补助标准根据市里政策作相应调整。
2.党组织关系在区、年满80周岁、党龄满55年的老党员：
（1）年龄80—89周岁且党龄满55年的，补助标准为500元/年；
（2）年龄90—99周岁且党龄满55年的，补助标准为1000元/年；
（3）年龄100周岁及以上的，补助标准为3000元/年。
以上补助年龄、党龄计算时间截至所在年份的12月31日。""", data_file_path = [r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\燕云村2024年度党员名册.txt"], 
                                                        supplement_files_path = [r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_files\[正文稿]关于印发《重庆市巴南区党内关怀办法（修订）》的通__知.txt"])
        config = {"configurable": {"thread_id":session_id}}
        current_state = initial_state

        try:
            for chunk in self.graph.stream(current_state, config = config, stream_mode = "updates"):
                for node_name, node_output in chunk.items():
                    print(f"\n📍 Node: {node_name}")
                    print("-" * 30)

                    if isinstance(node_output, dict):
                        if "messages" in node_output and node_output["messages"]:
                            latest_message = node_output["messages"][-1]
                            if hasattr(latest_message, 'content') and not isinstance(latest_message, HumanMessage):
                                print(f"💬 智能体回复: {latest_message.content}")

                        for key, value in node_output.items():
                            if key != "messages" and value:
                                # Show only first 500 characters for long outputs
                                if len(str(value)) > 500:
                                    print(f"📊 {key}: {str(value)[:500]}...")
                                else:
                                    print(f"📊 {key}: {value}")
                    print("-" * 30)

        except Exception as e:
            print(f"❌ 处理用户输入时出错: {e}")
    
agent = FilloutTableAgent()
agent_graph = agent._build_graph()

if __name__ == "__main__":
    fillout_table_agent = FilloutTableAgent()
    fillout_table_agent.run_fillout_table_agent(user_input = "请根据模板和数据文件，填写表格。", session_id = "1")




