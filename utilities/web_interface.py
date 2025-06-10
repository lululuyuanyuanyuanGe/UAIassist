import gradio as gr
import subprocess
import threading
import queue
import time
import os
from datetime import datetime
from typing import List, Tuple, Optional
import json

class TerminalInterface:
    def __init__(self):
        self.output_queue = queue.Queue()
        self.process = None
        self.chat_history = []
        self.uploaded_files = []
        
    def execute_command(self, command: str) -> str:
        """Execute a terminal command and capture output"""
        try:
            # Execute command and capture output
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"
            if result.returncode != 0:
                output += f"Return code: {result.returncode}\n"
                
            return output if output else "Command executed successfully (no output)"
            
        except subprocess.TimeoutExpired:
            return "❌ Command timed out after 30 seconds"
        except Exception as e:
            return f"❌ Error executing command: {str(e)}"
    
    def process_message(self, message: str, files: List, history: List) -> Tuple[List, str, List]:
        """Process user message and files"""
        if not message.strip() and not files:
            return history, "", []
        
        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Handle file uploads
        file_info = ""
        if files:
            file_info = "\n📎 Uploaded files:\n"
            for file in files:
                if file:
                    filename = os.path.basename(file.name)
                    file_size = os.path.getsize(file.name) if os.path.exists(file.name) else 0
                    file_info += f"  • {filename} ({file_size} bytes)\n"
                    
                    # Store file info
                    self.uploaded_files.append({
                        'name': filename,
                        'path': file.name,
                        'timestamp': timestamp,
                        'size': file_size
                    })
        
        # Add user message to history
        user_content = f"[{timestamp}] {message}"
        if file_info:
            user_content += file_info
            
        history.append({"role": "user", "content": user_content})
        
        # Store in chat history
        self.chat_history.append({
            'timestamp': timestamp,
            'type': 'user',
            'content': message,
            'files': [f['name'] for f in self.uploaded_files[-len(files):]] if files else []
        })
        
        # Process as terminal command or regular message
        if message.startswith('/cmd '):
            # Terminal command
            command = message[5:]  # Remove '/cmd ' prefix
            bot_response = f"🖥️ Executing: {command}\n\n"
            command_output = self.execute_command(command)
            bot_response += command_output
        elif message.startswith('/'):
            # Special commands
            if message == '/help':
                bot_response = """📋 Available commands:
• /cmd <command> - Execute terminal command
• /files - List uploaded files  
• /clear - Clear chat history
• /help - Show this help"""
            elif message == '/files':
                if self.uploaded_files:
                    bot_response = "📁 Uploaded files:\n"
                    for file in self.uploaded_files:
                        bot_response += f"  • {file['name']} ({file['size']} bytes) - {file['timestamp']}\n"
                else:
                    bot_response = "📁 No files uploaded yet"
            elif message == '/clear':
                self.chat_history = []
                return [], "", []
            else:
                bot_response = f"❓ Unknown command: {message}\nType /help for available commands"
        else:
            # Regular message
            bot_response = f"💬 Message received: {message}"
            if file_info:
                bot_response += f"\n{file_info}"
        
        # Add bot response to history
        bot_content = f"[{timestamp}] {bot_response}"
        history.append({"role": "assistant", "content": bot_content})
        
        # Store in chat history
        self.chat_history.append({
            'timestamp': timestamp,
            'type': 'assistant', 
            'content': bot_response
        })
        
        return history, "", []
    
    def clear_chat(self):
        """Clear chat history"""
        self.chat_history = []
        self.uploaded_files = []
        return [], "", []
    
    def get_chat_history_display(self):
        """Get formatted chat history for display"""
        if not self.chat_history:
            return "No chat history yet"
        
        history_text = "📜 Chat History\n" + "="*50 + "\n\n"
        for entry in self.chat_history:
            icon = "👤" if entry['type'] == 'user' else "🤖"
            history_text += f"{icon} [{entry['timestamp']}]\n"
            history_text += f"{entry['content']}\n\n"
            if entry.get('files'):
                history_text += f"📎 Files: {', '.join(entry['files'])}\n\n"
        
        return history_text

def create_interface():
    """Create the Gradio interface"""
    terminal = TerminalInterface()
    
    with gr.Blocks(title="Terminal Chat Interface", theme=gr.themes.Soft()) as interface:
        gr.Markdown("# 🖥️ Terminal Chat Interface")
        gr.Markdown("Send messages, execute commands with `/cmd <command>`, and upload files")
        
        with gr.Tab("💬 Chat"):
            with gr.Row():
                with gr.Column(scale=4):
                    chatbot = gr.Chatbot(
                        label="Chat",
                        height=400,
                        show_label=False,
                        bubble_full_width=False
                    )
                    
                    with gr.Row():
                        message_input = gr.Textbox(
                            placeholder="Type your message or /cmd <command>...",
                            show_label=False,
                            scale=4
                        )
                        send_btn = gr.Button("Send", scale=1, variant="primary")
                    
                    file_upload = gr.File(
                        label="Upload Files",
                        file_count="multiple",
                        file_types=None
                    )
                    
                    with gr.Row():
                        clear_btn = gr.Button("Clear Chat", variant="secondary")
                        help_btn = gr.Button("Help", variant="secondary")
                
                with gr.Column(scale=1):
                    gr.Markdown("### 💡 Quick Tips")
                    gr.Markdown("""
                    • Type `/cmd <command>` to execute terminal commands
                    • Upload files using the file picker
                    • Type `/help` for more commands
                    • Type `/files` to see uploaded files
                    • Type `/clear` to clear history
                    """)
        
        with gr.Tab("📜 History"):
            history_display = gr.Textbox(
                label="Chat History",
                lines=20,
                interactive=False,
                value=terminal.get_chat_history_display()
            )
            refresh_history_btn = gr.Button("Refresh History", variant="secondary")
        
        # Event handlers
        def submit_message(message, files, history):
            return terminal.process_message(message, files, history)
        
        def clear_chat():
            return terminal.clear_chat()
        
        def show_help(history):
            help_msg = """📋 Available commands:
• /cmd <command> - Execute terminal command
• /files - List uploaded files  
• /clear - Clear chat history
• /help - Show this help"""
            timestamp = datetime.now().strftime("%H:%M:%S")
            history.append({"role": "assistant", "content": f"[{timestamp}] {help_msg}"})
            return history, ""
        
        def refresh_history():
            return terminal.get_chat_history_display()
        
        # Connect events
        send_btn.click(
            submit_message,
            inputs=[message_input, file_upload, chatbot],
            outputs=[chatbot, message_input, file_upload]
        )
        
        message_input.submit(
            submit_message,
            inputs=[message_input, file_upload, chatbot],
            outputs=[chatbot, message_input, file_upload]
        )
        
        clear_btn.click(
            clear_chat,
            outputs=[chatbot, message_input, file_upload]
        )
        
        help_btn.click(
            show_help,
            inputs=[chatbot],
            outputs=[chatbot, message_input]
        )
        
        refresh_history_btn.click(
            refresh_history,
            outputs=[history_display]
        )
    
    return interface

def launch_interface(share=False, port=7860):
    """Launch the web interface"""
    interface = create_interface()
    interface.launch(
        share=share,
        server_port=port,
        server_name="0.0.0.0"
    )

if __name__ == "__main__":
    launch_interface()
