import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))



from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
from utilities.visualize_graph import save_graph_visualization
from utilities.message_process import build_BaseMessage_type, create_assistant_with_files, filter_out_system_messages, detect_and_process_file_paths, upload_file_to_LLM
import uuid
import json
import os
from pathlib import Path
# Create an interactive chatbox using gradio
import gradio as gr
from dotenv import load_dotenv
import re
from agents.frontdesk import FrontdeskState
load_dotenv()


def _process_html(file_path: Path, state: FrontdeskState) -> FrontdeskState:
    """This is the node that let LLM process the cleaned Html and add short description in each cell"""

    
