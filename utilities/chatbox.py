import gradio as gr
import time
import json
import os
from typing import List, Tuple, Optional
import uuid
from datetime import datetime

# Import the FrontDeskAgent
from agents.frontdesk import FrontDeskAgent

class ChatbotInterface:
    def __init__(self):
        self.agent = FrontDeskAgent()
        self.session_id = str(uuid.uuid4())
        self.conversation_state = None
        self.config = {"configurable": {"thread_id": self.session_id}}
        
    def process_chat(self, message: str, files: List, chat_history: List) -> Tuple[List, str, List]:
        """
        处理用户输入和文件上传 - 改为支持多模态输入
        """
        try:
            # Process uploaded files for multimodal input
            multimodal_content = []
            
            # Add text message
            if message.strip():
                multimodal_content.append({
                    "type": "text",
                    "text": message
                })
            
            # Add files for multimodal processing
            if files:
                file_descriptions = []
                for file in files:
                    if file and hasattr(file, 'name'):
                        file_ext = os.path.splitext(file.name)[1].lower()
                        filename = os.path.basename(file.name)
                        
                        # Support images and documents
                        if file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                            multimodal_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": file.name  # In real implementation, this would be converted to base64 or URL
                                }
                            })
                            file_descriptions.append(f"📷 图片: {filename}")
                        elif file_ext in ['.txt', '.md', '.csv', '.json', '.xlsx', '.xls', '.pdf']:
                            multimodal_content.append({
                                "type": "document",
                                "document": {
                                    "path": file.name,
                                    "type": file_ext[1:]  # Remove the dot
                                }
                            })
                            file_descriptions.append(f"📄 文档: {filename}")
                        else:
                            file_descriptions.append(f"📎 文件: {filename} (类型: {file_ext})")
                
                # Add file summary to message
                if file_descriptions:
                    file_summary = "\n".join(file_descriptions)
                    if message.strip():
                        display_message = f"{message}\n\n附件:\n{file_summary}"
                    else:
                        display_message = f"上传了文件:\n{file_summary}"
                else:
                    display_message = message
            else:
                display_message = message
            
            # If this is the first message, initialize the conversation
            if not self.conversation_state:
                self.conversation_state = self.agent._create_initial_state(message, self.session_id)
                chat_history.append({"role": "user", "content": display_message})
                
                # Process through the agent
                bot_response = self._run_agent_step(message, files)
                chat_history.append({"role": "assistant", "content": bot_response})
                
                return chat_history, "", []
            
            # Continue existing conversation
            chat_history.append({"role": "user", "content": display_message})
            
            # Process the user input through the agent  
            bot_response = self._run_agent_step(message, files)
            chat_history.append({"role": "assistant", "content": bot_response})
            
            return chat_history, "", []
            
        except Exception as e:
            error_msg = f"❌ 处理出错: {str(e)}"
            chat_history.append({"role": "user", "content": display_message if 'display_message' in locals() else message})
            chat_history.append({"role": "assistant", "content": error_msg})
            return chat_history, "", []
    
    def _run_agent_step(self, user_message: str, files: List = None) -> str:
        """
        运行智能体并获取响应 - 支持多模态输入
        """
        try:
            # Create a human message for the current input
            from langchain_core.messages import HumanMessage
            
            # For multimodal support, we would structure the message content differently
            # For now, we'll still use text but indicate file presence
            message_content = user_message
            if files:
                file_info = []
                for file in files:
                    if file and hasattr(file, 'name'):
                        file_ext = os.path.splitext(file.name)[1].lower()
                        filename = os.path.basename(file.name)
                        
                        if file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                            file_info.append(f"[图片文件: {filename}]")
                        else:
                            file_info.append(f"[文件: {filename}]")
                
                if file_info:
                    message_content = f"{user_message}\n\n用户上传了以下文件: {', '.join(file_info)}\n请根据文件内容和用户需求进行分析和响应。"
            
            # For continuing conversations, just add the user message and re-run from gather_requirements
            if self.conversation_state and self.conversation_state.get("messages"):
                # Add user message to state
                self.conversation_state["messages"].append(HumanMessage(content=message_content))
                
                # If gather_complete was True, reset it to continue conversation
                if self.conversation_state.get("gather_complete"):
                    self.conversation_state["gather_complete"] = False
            
            # Stream through the agent graph
            responses = []
            last_state = None
            
            for chunk in self.agent.graph.stream(self.conversation_state, config=self.config, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        if "messages" in node_output and node_output["messages"]:
                            latest_message = node_output["messages"][-1]
                            if hasattr(latest_message, 'content') and not isinstance(latest_message, HumanMessage):
                                responses.append(latest_message.content)
                        
                        # Update our conversation state
                        self.conversation_state.update(node_output)
                        last_state = node_output
                        
                        # Check if conversation is complete
                        if node_output.get("gather_complete"):
                            responses.append("\n🎉 **表格信息收集完成！**")
                            
                            if node_output.get("table_info"):
                                info = node_output.get("table_info", {})
                                responses.append(f"\n📋 **生成的表格信息：**")
                                responses.append(f"• **用途**: {info.get('purpose', '未指定')}")
                                responses.append(f"• **描述**: {info.get('description', '未指定')}")
                            
                            if node_output.get("table_structure"):
                                structure = node_output.get("table_structure", {})
                                if structure.get("multi_level_headers"):
                                    responses.append("\n📊 **表格结构已生成并保存到文件！**")
                                    
                                    # Show structure preview
                                    headers = structure.get("multi_level_headers", [])
                                    if headers:
                                        responses.append("\n🏗️ **表头结构预览：**")
                                        for header in headers[:3]:  # Show first 3 headers
                                            if isinstance(header, dict):
                                                responses.append(f"• {header.get('name', '未命名字段')}")
                                        if len(headers) > 3:
                                            responses.append(f"• ... 等共{len(headers)}个字段")
            
            # Return the response or a default message
            if responses:
                return "\n".join(responses)
            else:
                return "🤔 我正在思考中，请稍等..."
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"❌ 处理出错: {str(e)}"
    
    def reset_conversation(self):
        """
        重置对话
        """
        self.session_id = str(uuid.uuid4())
        self.conversation_state = None
        self.config = {"configurable": {"thread_id": self.session_id}}
        return [], "", []


def create_chatbot_interface():
    """
    创建ChatGPT/Claude风格的聊天界面
    """
    chatbot_interface = ChatbotInterface()
    
    # ChatGPT/Claude style CSS
    custom_css = """
    .gradio-container {
        max-width: 900px !important;
        margin: 0 auto !important;
        background: #f7f7f8 !important;
    }
    
    .main-container {
        background: white !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 16px rgba(0,0,0,0.1) !important;
        margin: 20px !important;
        overflow: hidden !important;
    }
    
    .chat-container {
        background: white !important;
        min-height: 600px !important;
        max-height: 70vh !important;
        overflow-y: auto !important;
    }
    
    .message-wrap {
        padding: 20px !important;
        border-bottom: 1px solid #f0f0f0 !important;
    }
    
    .user-message {
        background: #f7f7f8 !important;
        padding: 12px 16px !important;
        border-radius: 12px !important;
        margin: 8px 0 !important;
        max-width: 80% !important;
        margin-left: auto !important;
        border: 1px solid #e5e5e7 !important;
    }
    
    .bot-message {
        background: white !important;
        padding: 12px 16px !important;
        border-radius: 12px !important;
        margin: 8px 0 !important;
        max-width: 85% !important;
        border: 1px solid #e5e5e7 !important;
        line-height: 1.6 !important;
    }
    
    .input-container {
        background: white !important;
        border-top: 1px solid #e5e5e7 !important;
        padding: 16px 20px !important;
    }
    
    .input-row {
        display: flex !important;
        gap: 12px !important;
        align-items: flex-end !important;
    }
    
    .message-input {
        flex: 1 !important;
        border: 1px solid #e5e5e7 !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        font-size: 14px !important;
        resize: none !important;
        min-height: 20px !important;
        max-height: 120px !important;
    }
    
    .send-button {
        background: #2d7ee6 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 12px 20px !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        min-width: 80px !important;
    }
    
    .send-button:hover {
        background: #1e6fdd !important;
    }
    
    .attachment-area {
        margin-top: 8px !important;
        padding: 8px !important;
        background: #f8f9fa !important;
        border-radius: 8px !important;
        border: 1px dashed #dee2e6 !important;
    }
    
    .header-area {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        padding: 24px 20px !important;
        text-align: center !important;
    }
    
    .controls-area {
        background: #f8f9fa !important;
        padding: 12px 20px !important;
        border-top: 1px solid #e5e5e7 !important;
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
    }
    
    .control-button {
        background: #6c757d !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 8px 16px !important;
        font-size: 12px !important;
        cursor: pointer !important;
    }
    
    .session-info {
        font-size: 12px !important;
        color: #6c757d !important;
    }
    """
    
    with gr.Blocks(css=custom_css, title="💬 Excel表格生成助手") as ExcelAgent:
        with gr.Column(elem_classes=["main-container"]):
            # Header
            with gr.Row(elem_classes=["header-area"]):
                gr.Markdown("""
                # 💬 Excel表格生成智能助手
                
                **我可以帮您设计和创建专业的Excel表格**
                
                支持文档分析 • 图片识别 • 智能对话 • 结构设计
                """)
            
            # Chat Area
            with gr.Column(elem_classes=["chat-container"]):
                chatbot = gr.Chatbot(
                    value=[],
                    show_label=False,
                    container=False,
                    height=500,
                    elem_classes=["message-wrap"],
                    avatar_images=("https://cdn-icons-png.flaticon.com/512/147/147144.png", 
                                 "https://cdn-icons-png.flaticon.com/512/4712/4712035.png"),
                    bubble_full_width=False,
                    show_copy_button=True,
                    type="messages"
                )
            
            # Input Area
            with gr.Column(elem_classes=["input-container"]):
                with gr.Row(elem_classes=["input-row"]):
                    with gr.Column(scale=10):
                        msg = gr.Textbox(
                            placeholder="💭 描述您想要创建的表格，或上传参考文件...",
                            show_label=False,
                            lines=2,
                            max_lines=6,
                            elem_classes=["message-input"]
                        )
                        
                        # File upload area
                        files = gr.File(
                            label="📎 上传文件",
                            file_count="multiple",
                            file_types=[".txt", ".md", ".csv", ".json", ".xlsx", ".xls", ".pdf", 
                                       ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"],
                            show_label=False,
                            container=False,
                            elem_classes=["attachment-area"]
                        )
                        
                        gr.Markdown("""
                        **支持格式**: 📄 文档 (.txt, .md, .csv, .json, .pdf) • 📊 表格 (.xlsx, .xls) • 🖼️ 图片 (.png, .jpg, .jpeg, .gif, .bmp, .webp)
                        """, elem_id="file-info")
                    
                    with gr.Column(scale=1, min_width=80):
                        send_btn = gr.Button(
                            "发送",
                            variant="primary",
                            elem_classes=["send-button"]
                        )
            
            # Controls Area
            with gr.Row(elem_classes=["controls-area"]):
                with gr.Column(scale=1):
                    gr.Markdown(f"**会话**: `{chatbot_interface.session_id[:8]}...`", elem_classes=["session-info"])
                
                with gr.Column(scale=1):
                    with gr.Row():
                        clear_btn = gr.Button("清空", size="sm", elem_classes=["control-button"])
                        reset_btn = gr.Button("重新开始", size="sm", elem_classes=["control-button"])
        
        # Event handlers with improved UX
        def submit_message(message, files, history):
            if message.strip() or files:
                return chatbot_interface.process_chat(message, files, history)
            return history, "", files
        
        def clear_chat():
            return []
        
        def reset_all():
            chatbot_interface.reset_conversation()
            return [], "", []
        
        # Auto-submit on Enter (single line)
        msg.submit(submit_message, [msg, files, chatbot], [chatbot, msg, files])
        send_btn.click(submit_message, [msg, files, chatbot], [chatbot, msg, files])
        clear_btn.click(clear_chat, outputs=[chatbot])
        reset_btn.click(reset_all, outputs=[chatbot, msg, files])
        
        # Auto-focus and welcome message
        def welcome_message():
            return [{"role": "assistant", "content": "👋 您好！我是Excel表格生成智能助手。\n\n我可以帮您：\n• 🎯 分析表格需求\n• 📋 设计表格结构  \n• 🏗️ 创建多级表头\n• 📄 处理参考文件\n\n请告诉我您想创建什么样的表格，或者上传相关文件让我分析。"}]
        
        ExcelAgent.load(welcome_message, outputs=[chatbot])
    
    return ExcelAgent

def launch_chatbot(share=False, server_port=7860):
    """
    启动聊天机器人界面
    """
    ExcelAgent = create_chatbot_interface()
    ExcelAgent.launch(
        share=share,
        server_port=server_port,
        server_name="0.0.0.0",
        show_error=True,
        favicon_path=None,
        inbrowser=True
    )

if __name__ == "__main__":
    launch_chatbot(share=False, server_port=7860)

