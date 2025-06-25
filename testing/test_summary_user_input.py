from utilities.file_process import *
from utilities.message_process import *
import json
from pathlib import Path
from datetime import datetime
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, BaseMessage
from utilities.modelRelated import model_creation
from langchain_openai import ChatOpenAI

# Example 1: Chat history with simple template
simple_template_messages = [
    HumanMessage(content="你好，我需要处理一个表格"),
    AIMessage(content="您好！我是表格处理助手。请告诉我您需要处理什么样的表格，或者您可以上传表格模板。"),
    HumanMessage(content="我有一个员工信息表，包含姓名、年龄、部门、职位这几列"),
    AIMessage(content="明白了，这是一个简单的员工信息表。您提到的表格包含以下列：\n- 姓名\n- 年龄\n- 部门\n- 职位\n\n这是一个简单模板，只有列标题。您需要我帮您做什么处理吗？"),
    HumanMessage(content="对的，就是这样的简单表格，我需要填充一些数据")
]

# Example 2: Chat history with complex template  
complex_template_messages = [
    HumanMessage(content="我需要处理一个复杂的财务报表"),
    AIMessage(content="好的，请描述一下您的财务报表结构，或者上传模板文件。"),
    HumanMessage(content="这个表格比较复杂，有行标题和列标题。列标题是各个月份：1月、2月、3月等，行标题是不同的费用类型：办公费、差旅费、设备费等。"),
    AIMessage(content="我理解了，这是一个二维交叉表格：\n- 列标题：月份（1月、2月、3月...）\n- 行标题：费用类型（办公费、差旅费、设备费...）\n\n这是一个复杂模板，包含行标题和列标题的交叉结构。"),
    HumanMessage(content="是的，每个交叉点需要填入对应月份的费用金额"),
    AIMessage(content="明白了，这是一个典型的复杂表格模板，需要在行列交叉处填入数据。")
]

# Example 3: Chat history with general inquiry (no template)
general_inquiry_messages = [
    HumanMessage(content="你好"),
    AIMessage(content="您好！我是表格处理助手，可以帮您处理各种表格相关的任务。"),
    HumanMessage(content="我想了解一下你都能做什么"),
    AIMessage(content="我可以帮您：\n1. 分析表格结构\n2. 填充表格数据\n3. 处理简单和复杂模板\n4. 数据格式转换\n\n您有什么具体需求吗？"),
    HumanMessage(content="我先了解一下，稍后再具体使用")
]

# Example 4: Chat history with file upload scenario
file_upload_messages = [
    HumanMessage(content="我要上传一个Excel文件"),
    AIMessage(content="好的，请上传您的Excel文件，我会帮您分析表格结构。"),
    HumanMessage(content="文件路径：/path/to/student_grades.xlsx"),
    AIMessage(content="我收到了您上传的文件。正在分析表格结构..."),
    HumanMessage(content="这个表格包含学生姓名、各科成绩、总分等信息，结构比较简单"),
    AIMessage(content="根据您的描述，这是一个学生成绩表，属于简单模板类型，只有列标题没有复杂的行列交叉结构。")
]

def test_summary_user_input():
    """Test function that actually invokes LLM and allows human evaluation"""
    
    # Initialize the LLM
    llm = model_creation(model_name="gpt-4o", temperature=0.2)
    
    def _summary_user_input_real(process_user_input_messages: list[BaseMessage]) -> AIMessage:
        """Real implementation that calls LLM"""
        
        # Extract content from messages
        process_user_input_messages_content = [item.content for item in process_user_input_messages]
        process_user_input_messages_content = "\n".join(f"{item.type#}: {item.content}" for item in process_user_input_messages)
        
        system_prompt = f"""你的任务是负责总结用户在这一轮都提供了哪些信息，你需要根据整个对话记录，总结用户都提供了哪些信息，并且根据这些信息，决定下一步的流程

规则如下：
- 如果出现了复杂模板（同时包含行标题和列标题的交叉表格），返回"complex_template"
- 如果出现了简单模板（只有列标题的普通表格），返回"simple_template"  
- 其余情况请返回"previous_node"

你的回复需要包含对这一轮的总结，和节点路由信息，严格按照以下JSON格式返回：

历史对话: {process_user_input_messages_content}

请返回：
{{
    "summary": "总结用户在这一轮都提供了哪些信息",
    "next_node": "complex_template/simple_template/previous_node"
}}
"""
        
        try:
            messages = [SystemMessage(content=system_prompt)]
            print(f"🔄 正在调用LLM进行总结...")
            
            response = llm.invoke(messages)
            print(f"✅ LLM调用成功")
            
            return response
            
        except Exception as e:
            print(f"❌ LLM调用失败: {type(e).__name__}: {e}")
            
            # Fallback response when LLM fails
            fallback_response = AIMessage(content="""
            {
                "summary": "由于网络连接问题，无法完成智能分析。用户本轮提供了输入信息。",
                "next_node": "previous_node"
            }
            """)
            
            return fallback_response

    # Test scenarios with human evaluation
    test_scenarios = [
        ("简单模板场景", simple_template_messages),
        ("复杂模板场景", complex_template_messages), 
        ("一般询问场景", general_inquiry_messages),
        ("文件上传场景", file_upload_messages)
    ]
    
    print("=" * 50)
    print("开始LLM总结功能测试 - 需要人工评估")
    print("=" * 50)
    
    for scenario_name, messages in test_scenarios:
        print(f"\n{'='*20} {scenario_name} {'='*20}")
        
        # Show input messages
        print("\n📝 输入的对话历史:")
        for i, msg in enumerate(messages, 1):
            msg_type = "用户" if isinstance(msg, HumanMessage) else "AI助手"
            print(f"  {i}. [{msg_type}]: {msg.content}")
        
        # Get LLM response
        print(f"\n🤖 调用LLM分析...")
        result = _summary_user_input_real(messages)
        
        print(f"\n📋 LLM分析结果:")
        print("-" * 40)
        print(result.content)
        print("-" * 40)
        
        # Human evaluation
        print(f"\n👤 请评估LLM的回复质量:")
        print("1. 总结是否准确？")
        print("2. 路由决策是否正确？")
        print("3. JSON格式是否正确？")
        
        while True:
            evaluation = input("\n请输入评估 (excellent/good/fair/poor) 或 's' 跳过: ").lower().strip()
            if evaluation in ['excellent', 'good', 'fair', 'poor', 's']:
                break
            print("请输入有效的评估: excellent, good, fair, poor, 或 s")
        
        if evaluation != 's':
            print(f"✅ 人工评估: {evaluation}")
            
            if evaluation in ['fair', 'poor']:
                feedback = input("请提供改进建议: ")
                print(f"📝 改进建议: {feedback}")
        
        print("\n" + "="*60)
    
    print("\n🎉 测试完成！感谢您的评估。")

if __name__ == "__main__":
    test_summary_user_input()