#!/usr/bin/env python3
"""
Excel表格生成智能助手 - Gradio界面启动器
"""

import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utilities.chatbox import launch_chatbot

def main():
    """
    启动Excel表格生成智能助手的Gradio界面
    """
    print("🚀 启动Excel表格生成智能助手...")
    print("📋 功能特点:")
    print("  • 智能对话式表格设计")
    print("  • 多级表头结构生成")
    print("  • 文件上传支持")
    print("  • 实时对话历史")
    print("  • JSON格式输出")
    print("\n🌐 界面将在浏览器中自动打开...")
    print("📍 默认地址: http://localhost:7860")
    print("\n💡 使用提示:")
    print("  1. 告诉我您想创建什么样的表格")
    print("  2. 回答我的问题来完善需求")
    print("  3. 可以上传参考文件")
    print("  4. 我会生成完整的表格结构JSON文件")
    print("\n" + "="*50)
    
    try:
        # Launch the chatbot with default settings
        launch_chatbot(
            share=False,      # Set to True to create a public link
            server_port=7860  # Change port if needed
        )
    except KeyboardInterrupt:
        print("\n👋 感谢使用！再见！")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        print("请检查依赖是否正确安装：")
        print("  pip install gradio langchain langgraph langchain-openai")

if __name__ == "__main__":
    main() 