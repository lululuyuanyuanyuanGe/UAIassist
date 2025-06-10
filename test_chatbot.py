#!/usr/bin/env python3
"""
Test script for the Excel表格生成智能助手 chatbot
"""

import os
import sys
from utilities.chatbox import ChatbotInterface

def test_chatbot():
    """
    Test the chatbot functionality
    """
    print("🧪 测试Excel表格生成智能助手...")
    
    try:
        # Initialize chatbot
        chatbot = ChatbotInterface()
        print("✅ 智能体初始化成功")
        
        # Test conversation
        test_messages = [
            "我想创建一个员工信息管理表格",
            "用来管理公司员工的基本信息和工作情况",
            "需要包括姓名、工号、部门、职位、入职日期、联系电话等基本信息",
            "还需要薪资、绩效评级等字段",
            "是的，需要多级表头分组",
            "这样就够了"
        ]
        
        chat_history = []
        
        for i, message in enumerate(test_messages):
            print(f"\n👤 用户消息 {i+1}: {message}")
            
            # Process message
            chat_history, _, _ = chatbot.process_chat(message, [], chat_history)
            
            if chat_history:
                bot_response = chat_history[-1][1]
                print(f"🤖 智能体回复: {bot_response[:100]}...")
                
                # Check if conversation is complete
                if "表格信息收集完成" in bot_response or "COMPLETE" in bot_response:
                    print("🎉 对话完成！")
                    break
        
        print("\n📊 测试完成")
        print("🚀 要启动完整界面，请运行: python launch_chatbot.py")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_chatbot() 