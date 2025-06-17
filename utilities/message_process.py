from __future__ import annotations
from bs4 import BeautifulSoup, Tag
from pathlib import Path

from typing import TypedDict, Annotated, List
import re
import os
from pathlib import Path
import subprocess
import chardet

from openai import OpenAI
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage


def build_BaseMessage_type(messages:list[dict], file_paths : list[str] = None) -> list[BaseMessage]:
    """"将消息队列转换成LangChain的消息模板"""
    langchain_messages = []
    for msg in messages:
        if msg["role"] == "system":
            langchain_messages.append(SystemMessage(content = msg["content"]))
        elif msg["role"] == "user":
            # 判断是否为复杂输入(包含文件)
            if isinstance(msg["content"], list):
                # 将用户文本输入存储在 contenxt_text
                contexnt_text = next((item["text"] for item in msg["content"] if item["type"] == "text"), "")
                file_refs = [item["file_id"] for item in msg["content"] if item["type"] == "input_file"]
                user_input = F"{contexnt_text} + input files list: {' '.join(file_refs)}"
                human_msg = HumanMessage(
                    content= user_input,
                    additional_kargs = {
                        "filer_ids": file_refs,
                        "multimodal_content": msg["content"]
                    }
                )
                langchain_messages.append(human_msg)
        else:
            langchain_messages.append(HumanMessage(content=msg["content"]))

    return langchain_messages

def filter_out_system_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """辅助函数过滤消息队列中的系统提示词消息"""
    return [message for message in messages if not isinstance(message, SystemMessage)]

def detect_and_process_file_paths(user_input: str) -> list:
    """检测用户输入中的文件路径并验证文件是否存在，返回结果为用户上传的文件路径组成的数列"""
    file_paths = []
    
    # 改进的文件路径检测模式，支持中文字符
    # Windows路径模式 (C:\path\file.ext 或 D:\path\file.ext) - 支持中文字符
    windows_pattern = r'[A-Za-z]:[\\\\/](?:[^\\\\/\s\n\r]+[\\\\/])*[^\\\\/\s\n\r]+\.\w+'
    # 相对路径模式 (./path/file.ext 或 ../path/file.ext) - 支持中文字符
    relative_pattern = r'\.{1,2}[\\\\/](?:[^\\\\/\s\n\r]+[\\\\/])*[^\\\\/\s\n\r]+\.\w+'
    # 简单文件名模式 (filename.ext) - 支持中文字符
    filename_pattern = r'\b[a-zA-Z0-9_\u4e00-\u9fff\-\(\)（）]+\.[a-zA-Z0-9]+\b'
    
    patterns = [windows_pattern, relative_pattern, filename_pattern]
    
    for pattern in patterns:
        matches = re.findall(pattern, user_input)
        for match in matches:
            # 验证文件是否存在
            if os.path.exists(match):
                file_paths.append(match)
                print(f"✅ 检测到文件: {match}")
            else:
                print(f"⚠️ 文件路径无效或文件不存在: {match}")
    
    return file_paths

def upload_file_to_LLM(file_paths: list, provider: str = "openai", purpose: str = "assistants", vector_store_id: str = None):
    """
    通用文件上传工具，支持多个模型提供商
    """
    results = {
        "provider": provider,
        "uploaded_files": [],
        "failed_files": [],
        "vector_store_files": [],
        "total_files": len(file_paths)
    }
    
    if provider.lower() == "openai":
        return _upload_to_openai(file_paths, purpose, vector_store_id, results)
    # elif provider.lower() == "azure":
    #     return _upload_to_azure(file_paths, purpose, vector_store_id, results)
    # elif provider.lower() == "anthropic":
    #     return _upload_to_anthropic(file_paths, purpose, results)
    # elif provider.lower() == "local":
    #     return _upload_to_local(file_paths, purpose, results)
    else:
        results["error"] = f"Unsupported provider: {provider}"
        return results


def _upload_to_openai(file_paths: list, purpose: str, vector_store_id: str, results: dict):
    """OpenAI 文件上传实现"""
    from openai import OpenAI
    import os
    
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        for file_path in file_paths:
            try:
                file_path = Path(file_path)
                if not file_path.exists():
                    results["failed_files"].append({
                        "file": str(file_path),
                        "error": "File not found"
                    })
                    continue
                
                print(f"📁 正在上传文件: {file_path.name}")
                
                # 上传文件到OpenAI
                with open(file_path, 'rb') as file:
                    file_response = client.files.create(
                        file=file,
                        purpose=purpose
                    )
                
                uploaded_file_info = {
                    "file_id": file_response.id,
                    "filename": file_response.filename,
                    "purpose": file_response.purpose,
                    "size": file_response.bytes,
                    "created_at": file_response.created_at
                }
                
                results["uploaded_files"].append(uploaded_file_info)
                print(f"✅ 文件上传成功: {file_response.filename} (ID: {file_response.id})")
                
                # 如果提供了vector_store_id，将文件添加到向量存储
                if vector_store_id:
                    try:
                        vector_file_response = client.beta.vector_stores.files.create(
                            vector_store_id=vector_store_id,
                            file_id=file_response.id
                        )
                        
                        results["vector_store_files"].append({
                            "vector_store_id": vector_store_id,
                            "file_id": file_response.id,
                            "status": vector_file_response.status
                        })
                        print(f"✅ 文件已添加到向量存储: {vector_store_id}")
                        
                    except Exception as vs_error:
                        print(f"⚠️ 向量存储添加失败: {vs_error}")
                        results["failed_files"].append({
                            "file": str(file_path),
                            "error": f"Vector store upload failed: {vs_error}"
                        })
                
            except Exception as file_error:
                print(f"❌ 文件上传失败 {file_path.name}: {file_error}")
                results["failed_files"].append({
                    "file": str(file_path),
                    "error": str(file_error)
                })
        
        results["success"] = True
        results["message"] = f"OpenAI上传完成: {len(results['uploaded_files'])}个成功, {len(results['failed_files'])}个失败"
        
    except Exception as e:
        results["success"] = False
        results["error"] = f"OpenAI API错误: {str(e)}"
    
    return results

# 目前只用到了OpenAI的模型

# def _upload_to_azure(file_paths: list, purpose: str, vector_store_id: str, results: dict):
#     """Azure OpenAI 文件上传实现"""
#     try:
#         from openai import AzureOpenAI
#         import os
        
#         client = AzureOpenAI(
#             api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
#             api_version=os.environ.get("OPENAI_API_VERSION", "2024-02-15-preview"),
#             azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
#         )
        
#         for file_path in file_paths:
#             try:
#                 file_path = Path(file_path)
#                 if not file_path.exists():
#                     results["failed_files"].append({
#                         "file": str(file_path),
#                         "error": "File not found"
#                     })
#                     continue
                
#                 print(f"📁 正在上传文件到Azure: {file_path.name}")
                
#                 with open(file_path, 'rb') as file:
#                     file_response = client.files.create(
#                         file=file,
#                         purpose=purpose
#                     )
                
#                 results["uploaded_files"].append({
#                     "file_id": file_response.id,
#                     "filename": file_response.filename,
#                     "purpose": file_response.purpose,
#                     "provider": "azure"
#                 })
#                 print(f"✅ Azure文件上传成功: {file_response.filename}")
                
#             except Exception as file_error:
#                 print(f"❌ Azure文件上传失败 {file_path.name}: {file_error}")
#                 results["failed_files"].append({
#                     "file": str(file_path),
#                     "error": str(file_error)
#                 })
        
#         results["success"] = True
#         results["message"] = f"Azure上传完成: {len(results['uploaded_files'])}个成功"
        
#     except ImportError:
#         results["success"] = False
#         results["error"] = "Azure OpenAI library not installed. Run: pip install openai[azure]"
#     except Exception as e:
#         results["success"] = False
#         results["error"] = f"Azure API错误: {str(e)}"
    
#     return results


# def _upload_to_anthropic(file_paths: list, purpose: str, results: dict):
#     """Anthropic Claude 文件上传实现"""
#     try:
#         import anthropic
#         import os
        
#         client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        
#         for file_path in file_paths:
#             try:
#                 file_path = Path(file_path)
#                 if not file_path.exists():
#                     results["failed_files"].append({
#                         "file": str(file_path),
#                         "error": "File not found"
#                     })
#                     continue
                
#                 print(f"📁 正在上传文件到Anthropic: {file_path.name}")
                
#                 # 注意：Anthropic的文件上传API可能不同，这里是示例
#                 # 实际实现需要根据Anthropic的具体API调整
#                 with open(file_path, 'rb') as file:
#                     file_content = file.read()
                
#                 results["uploaded_files"].append({
#                     "filename": file_path.name,
#                     "size": len(file_content),
#                     "provider": "anthropic",
#                     "note": "Anthropic files are typically handled differently"
#                 })
#                 print(f"✅ Anthropic文件处理完成: {file_path.name}")
                
#             except Exception as file_error:
#                 print(f"❌ Anthropic文件处理失败 {file_path.name}: {file_error}")
#                 results["failed_files"].append({
#                     "file": str(file_path),
#                     "error": str(file_error)
#                 })
        
#         results["success"] = True
#         results["message"] = f"Anthropic处理完成: {len(results['uploaded_files'])}个文件"
        
#     except ImportError:
#         results["success"] = False
#         results["error"] = "Anthropic library not installed. Run: pip install anthropic"
#     except Exception as e:
#         results["success"] = False
#         results["error"] = f"Anthropic API错误: {str(e)}"
    
#     return results


# def _upload_to_local(file_paths: list, purpose: str, results: dict):
#     """本地文件处理实现"""
#     import shutil
#     import os
#     from datetime import datetime
    
#     try:
#         # 创建本地存储目录
#         local_storage = Path("uploaded_files")
#         local_storage.mkdir(exist_ok=True)
        
#         for file_path in file_paths:
#             try:
#                 file_path = Path(file_path)
#                 if not file_path.exists():
#                     results["failed_files"].append({
#                         "file": str(file_path),
#                         "error": "File not found"
#                     })
#                     continue
                
#                 print(f"📁 正在处理本地文件: {file_path.name}")
                
#                 # 复制文件到本地存储
#                 destination = local_storage / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_path.name}"
#                 shutil.copy2(file_path, destination)
                
#                 results["uploaded_files"].append({
#                     "original_path": str(file_path),
#                     "stored_path": str(destination),
#                     "filename": file_path.name,
#                     "size": file_path.stat().st_size,
#                     "provider": "local"
#                 })
#                 print(f"✅ 本地文件存储成功: {destination}")
                
#             except Exception as file_error:
#                 print(f"❌ 本地文件处理失败 {file_path.name}: {file_error}")
#                 results["failed_files"].append({
#                     "file": str(file_path),
#                     "error": str(file_error)
#                 })
        
#         results["success"] = True
#         results["message"] = f"本地存储完成: {len(results['uploaded_files'])}个文件"
        
#     except Exception as e:
#         results["success"] = False
#         results["error"] = f"本地存储错误: {str(e)}"
    
#     return results

def convert_excel_2_html(input_path: str | Path, output_dir: str | Path) -> Path:
    """
    Convert an Excel workbook to a minimal HTML file that contains only the
    table structure.  Returns the *cleaned* HTML path.

    Notes
    -----
    • LibreOffice writes `<workbook-stem>.html` into *output_dir*.  
    • Because *output_dir* is reserved exclusively for these exports, we can
      compute that file name directly instead of searching for it.
    """
    input_path  = Path(input_path).expanduser().resolve()
    output_dir  = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1️⃣  LibreOffice export --------------------------------------------------
    soffice = r"D:\LibreOffice\program\soffice.exe"      # adjust if necessary
    subprocess.run(
        [soffice, "--headless", "--convert-to", "html", str(input_path),
         "--outdir", str(output_dir)],
        check=True
    )

    # 2️⃣  The raw export path we expect LibreOffice to create
    raw_html_path = output_dir / f"{input_path.stem}.html"
    if not raw_html_path.exists():
        raise FileNotFoundError(f"LibreOffice did not create {raw_html_path}")

    # 3️⃣  Clean & return the tidy file
    return _clean_html(raw_html_path, output_dir)


# ──────────────────────── private helpers ─────────────────────── #
def _read_text_auto(path: Path) -> str:
    """Best-effort text loader with encoding detection."""
    data = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    if chardet:
        enc = chardet.detect(data).get("encoding")
        if enc:
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                pass
    return data.decode("utf-8", errors="replace")


def _clean_html(raw_html_path: Path, out_dir: Path) -> Path:
    """
    Strip Excel/Sheets boiler-plate—*including the massive inline CSS*—and keep
    only genuine table markup.

    • Preserves:  <table>, <thead>, <tbody>, <tfoot>, <tr>, <td>, <th>,
                 <col>, <colgroup>
    • Keeps attributes:  rowspan/colspan everywhere, plus span on <colgroup>.
    """
    KEEP          = {"table", "thead", "tbody", "tfoot", "tr", "td",
                     "th", "col", "colgroup"}
    ATTR_ALWAYS   = {"rowspan", "colspan"}
    ATTR_EXTRA    = {"colgroup": {"span"}}

    html = _read_text_auto(raw_html_path)

    # drop DOCTYPE / XML prologs
    html = re.sub(r'<!DOCTYPE[^>]*?>',           '', html, flags=re.I | re.S)
    html = re.sub(r'<\?xml[^>]*?\?>',            '', html, flags=re.I)
    html = re.sub(r'<\?mso-application[^>]*?\?>','', html, flags=re.I)

    soup = BeautifulSoup(html, "html.parser")

    # remove <style>, <meta>, <link>
    for t in soup.find_all(["style", "meta", "link"]):
        t.decompose()

    # prune unwanted tags / attributes
    for t in soup.find_all(True):
        if t.name not in KEEP:
            t.unwrap()
            continue
        allowed = ATTR_ALWAYS | ATTR_EXTRA.get(t.name, set())
        t.attrs = {k: v for k, v in t.attrs.items() if k in allowed}

    # build minimal shell
    shell = BeautifulSoup("<html><body></body></html>", "html.parser")
    for tbl in soup.find_all("table"):
        shell.body.append(tbl)

    out_file = out_dir / f"{raw_html_path.stem}_clean.html"
    out_file.write_text(shell.prettify(), encoding="utf-8")
    return out_file


