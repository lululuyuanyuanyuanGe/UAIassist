from __future__ import annotations
from bs4 import BeautifulSoup
from pathlib import Path
import re
import os
import json
from pathlib import Path
import subprocess
import chardet
from typing import Union, List, Dict
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from utilities.modelRelated import invoke_model

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

def detect_and_process_file_paths(user_input: str) -> list:
    """检测用户输入中的文件路径并验证文件是否存在，返回结果为用户上传的文件路径组成的数列"""
    file_paths = []
    processed_paths = set()  # Track already processed paths to avoid duplicates
    
    # 改进的文件路径检测模式，支持中文字符
    # Windows路径模式 (C:\path\file.ext 或 D:\path\file.ext) - 支持中文字符
    windows_pattern = r'[A-Za-z]:[\\\\/](?:[^\\\\/\s\n\r]+[\\\\/])*[^\\\\/\s\n\r]+\.\w+'
    # 相对路径模式 (./path/file.ext 或 ../path/file.ext) - 支持中文字符
    relative_pattern = r'\.{1,2}[\\\\/](?:[^\\\\/\s\n\r]+[\\\\/])*[^\\\\/\s\n\r]+\.\w+'
    # 简单文件名模式 (filename.ext) - 支持中文字符
    filename_pattern = r'\b[a-zA-Z0-9_\u4e00-\u9fff\-\(\)（）]+\.[a-zA-Z0-9]+\b'
    
    patterns = [windows_pattern, relative_pattern, filename_pattern]
    
    # Run the absolute path pattern first
    for match in re.findall(patterns[0], user_input):
        if match in processed_paths:
            continue
        processed_paths.add(match)
        _log_existence(match, file_paths)

    # Run the relative path pattern
    for match in re.findall(patterns[1], user_input):
        if match in processed_paths:
            continue
        processed_paths.add(match)
        _log_existence(match, file_paths)
        
    # Run the filename pattern if we didn't find any files
    if not file_paths:
        for match in re.findall(patterns[2], user_input):
            if match in processed_paths:
                continue
            processed_paths.add(match)
            _log_existence(match, file_paths)

    return file_paths


# -- 小工具函数 ------------------------------------------------------------
def _log_existence(path: str, container: list):
    if os.path.exists(path):
        container.append(path)
        print(f"✅ 检测到文件: {path}")
    else:
        print(f"⚠️ 文件路径无效或文件不存在: {path}")


def convert_2_markdown(file_path: str) -> str:
    """将Excel文件转换为Markdown格式并保存为.md文件"""

    # 读取Excel文件
    df = pd.read_excel(file_path)
    markdown_content = df.to_markdown(index=False)

    # 构造新的Markdown文件名
    original_name = Path(file_path).stem  # 不带扩展名
    markdown_file_name = f"{original_name}.md"

    # 目标保存目录
    markdown_folder = Path(r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_md")
    markdown_folder.mkdir(parents=True, exist_ok=True)  # 如果不存在就创建

    # 完整路径
    markdown_file_path = markdown_folder / markdown_file_name

    # 写入文件
    with open(markdown_file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return str(markdown_file_path)  # 返回保存路径以便后续使用
    


def save_original_file(source_path: Path, original_files_dir: Path) -> str:
    """
    Save the original file to the original_file subfolder.
    
    Args:
        source_path: Path to the source file
        original_files_dir: Path to the original_file directory
        
    Returns:
        str: Path to the saved original file, empty string if failed
    """
    import shutil
    
    try:
        if not source_path.exists():
            print(f"❌ Source file not found: {source_path}")
            return ""
            
        print(f"📁 正在保存原始文件: {source_path.name}")
        
        # Create target path for original file
        original_file_path = original_files_dir / source_path.name
        
        # Handle duplicate original files by updating content
        if original_file_path.exists():
            print(f"⚠️ 原始文件已存在，正在更新: {source_path.name}")
            try:
                # Try to remove existing file
                original_file_path.unlink()
                print(f"🗑️ 已删除旧的原始文件: {source_path.name}")
            except Exception as e:
                print(f"❌ 删除旧原始文件失败: {e}")
                # Check for permission errors
                if "WinError 5" in str(e) or "Access is denied" in str(e) or "Permission denied" in str(e):
                    print(f"💡 文件 '{source_path.name}' 可能被其他应用程序锁定")
                    print(f"📝 请关闭相关应用程序后重试，或使用不同的文件名")
                    return ""
                else:
                    print(f"⚠️ 其他错误: {e}")
                    return ""
        
        # Copy the original file to the original_file subfolder
        try:
            shutil.copy2(source_path, original_file_path)
            print(f"💾 原始文件已保存: {original_file_path}")
            return str(original_file_path)
        except Exception as e:
            print(f"❌ 保存原始文件失败: {e}")
            # Check for permission errors
            if "WinError 5" in str(e) or "Access is denied" in str(e) or "Permission denied" in str(e):
                print(f"💡 目标文件 '{original_file_path}' 可能被其他应用程序锁定")
                print(f"📝 请关闭相关应用程序后重试")
            else:
                print(f"⚠️ 其他错误: {e}")
            return ""
            
    except Exception as e:
        print(f"❌ 保存原始文件时发生意外错误: {e}")
        return ""

def convert_document_to_txt(file_path: str) -> str:
    """Convert document to txt file"""
    soffice = r"D:\LibreOffice\program\soffice.exe"
    subprocess.run(
        [soffice, "--headless", "--convert-to", "txt:Text (encoded):UTF8", file_path, "--outdir", "D:\asianInfo\ExcelAssist\agents\output"], check=True)
    return file_path

def retrieve_file_content(file_paths: list[str], session_id: str, output_dir: str = None) -> list[str]:
    """Process files and store them as .txt files in the staging area: conversations/session_id/user_uploaded_files
    This function only handles file processing, not original file saving.
    
    Args:
        file_paths: List of file paths to process
        session_id: Session identifier for folder structure
        output_dir: Optional output directory override
        
    Returns:
        list[str]: List of processed .txt file paths in staging area
    """
    
    from pathlib import Path
    
    if output_dir:
        staging_dir = Path(output_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)
    else:
        # Create the staging area: conversations/session_id/user_uploaded_files
        project_root = Path.cwd()
        staging_dir = project_root / "conversations" / session_id / "user_uploaded_files"
        staging_dir.mkdir(parents=True, exist_ok=True)
        output_dir = project_root / "conversations" / session_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
    
    processed_files = []
    
    for file_path in file_paths:
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                print(f"❌ File not found: {file_path}")
                continue
                
            print(f"🔄 Processing file: {source_path.name}")
            
            # Process the file content
            processed_content = process_file_to_text(source_path)
            
            if processed_content is not None:
                # Save processed content as .txt file in staging area
                txt_file_path = staging_dir / f"{source_path.stem}.txt"
                
                if txt_file_path.exists():
                    print(f"⚠️ 处理文件已存在，正在更新内容: {txt_file_path.name}")
                
                txt_file_path.write_text(processed_content, encoding='utf-8')
                processed_files.append(str(txt_file_path))
                print(f"✅ 文件处理并保存到暂存区: {txt_file_path}")
            else:
                print(f"❌ 文件内容处理失败: {source_path.name}")
                
        except Exception as e:
            print(f"❌ 处理文件时发生意外错误 {file_path}: {e}")
            continue
    
    print(f"🎉 成功处理 {len(processed_files)} 个文件到暂存区")
    
    return processed_files


def process_file_to_text(file_path: str | Path) -> str | None:
    """
    Efficiently process a file to readable text content in memory.
    
    This function does: 1 read → process in memory → return text
    Instead of: read → write temp file → read temp file → write final file
    
    Returns:
        str: The processed text content, or None if processing failed
    """
    source_path = Path(file_path)
    file_extension = source_path.suffix.lower()
    
    # Define file type categories
    spreadsheet_extensions = {'.xlsx', '.xls', '.xlsm', '.ods', '.csv'}
    text_extensions = {'.txt', '.md', '.json', '.xml', '.html', '.htm', '.py', '.js', '.css', '.sql', '.log'}
    document_extensions = {'.docx', '.doc', '.pptx', '.ppt'}
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg'}
    
    try:
        # Handle spreadsheet files
        if file_extension in spreadsheet_extensions:
            return _process_spreadsheet_in_memory(source_path)
        
        # Handle document files (DOCX, DOC, etc.)
        elif file_extension in document_extensions:
            return _process_document_in_memory(source_path)
        
        # Handle plain text files
        elif file_extension in text_extensions:
            return _read_text_auto(source_path)
        
        # Handle image files - return metadata since we can't convert to text
        elif file_extension in image_extensions:
            return f"Image file: {source_path.name}\nFile size: {source_path.stat().st_size} bytes\nFormat: {file_extension}"
        
        # Handle other file types
        else:
            # Try to detect if it's a text file by MIME type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(source_path))
            
            if mime_type and mime_type.startswith('text/'):
                return _read_text_auto(source_path)
            else:
                # For binary files, return metadata
                return f"Binary file: {source_path.name}\nFile size: {source_path.stat().st_size} bytes\nType: {mime_type or 'unknown'}"
                
    except Exception as e:
        print(f"❌ Error processing file {file_path}: {e}")
        return None


def _process_spreadsheet_in_memory(source_path: Path) -> str:
    """Process spreadsheet file in memory using LibreOffice"""
    import tempfile
    
    # Create a temporary directory for LibreOffice processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        
        # LibreOffice export to temp directory
        soffice = r"D:\LibreOffice\program\soffice.exe"
        subprocess.run(
            [soffice, "--headless", "--convert-to", "html", str(source_path),
             "--outdir", str(temp_dir_path)],
            check=True
        )
        
        # Read the generated HTML file
        raw_html_path = temp_dir_path / f"{source_path.stem}.html"
        if not raw_html_path.exists():
            raise FileNotFoundError(f"LibreOffice did not create {raw_html_path}")
        
        # Clean HTML in memory and return the result
        return _clean_html_in_memory(raw_html_path)


def _process_document_in_memory(source_path: Path) -> str:
    """Process document file in memory using LibreOffice to convert to txt"""
    import tempfile
    
    # Create a temporary directory for LibreOffice processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        
        # LibreOffice export to temp directory as txt
        soffice = r"D:\LibreOffice\program\soffice.exe"
        subprocess.run(
            [soffice, "--headless", "--convert-to", "txt:Text (encoded):UTF8", str(source_path),
             "--outdir", str(temp_dir_path)],
            check=True
        )
        
        # Read the generated TXT file
        raw_txt_path = temp_dir_path / f"{source_path.stem}.txt"
        if not raw_txt_path.exists():
            raise FileNotFoundError(f"LibreOffice did not create {raw_txt_path}")
        
        # Read and return the txt content directly
        return _read_text_auto(raw_txt_path)


def _clean_html_in_memory(raw_html_path: Path) -> str:
    """
    Clean HTML file in memory and return the clean HTML string.
    This function preserves both table structures and text content while
    removing unnecessary decorative HTML elements.
    """
    # Tags to keep for table structure
    TABLE_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "col", "colgroup"}
    
    # Tags to keep for text content and basic formatting
    TEXT_TAGS = {"p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6", 
                 "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", 
                 "blockquote", "pre", "code", "a"}
    
    # All tags we want to preserve
    KEEP = TABLE_TAGS | TEXT_TAGS
    
    # Attributes to always keep
    ATTR_ALWAYS = {"rowspan", "colspan"}
    
    # Additional attributes for specific tags
    ATTR_EXTRA = {
        "colgroup": {"span"},
        "a": {"href"},  # Keep links
    }

    html = _read_text_auto(raw_html_path)

    # Drop DOCTYPE / XML prologs
    html = re.sub(r'<!DOCTYPE[^>]*?>',           '', html, flags=re.I | re.S)
    html = re.sub(r'<\?xml[^>]*?\?>',            '', html, flags=re.I)
    html = re.sub(r'<\?mso-application[^>]*?\?>','', html, flags=re.I)

    soup = BeautifulSoup(html, "html.parser")

    # Remove styling and metadata tags
    for t in soup.find_all(["style", "meta", "link", "script", "noscript"]):
        t.decompose()

    # Clean up attributes and unwrap unwanted tags
    for t in soup.find_all(True):
        if t.name not in KEEP:
            # Unwrap tags we don't want to keep, but preserve their content
            t.unwrap()
            continue
        
        # For kept tags, clean up attributes
        allowed = ATTR_ALWAYS | ATTR_EXTRA.get(t.name, set())
        
        # Remove style attributes and other formatting attributes
        attrs_to_remove = []
        for attr_name in t.attrs.keys():
            if attr_name not in allowed:
                # Remove ALL styling and metadata attributes
                attrs_to_remove.append(attr_name)
        
        for attr in attrs_to_remove:
            del t.attrs[attr]

    # Build a clean document structure
    shell = BeautifulSoup("<html><body></body></html>", "html.parser")
    
    # Add all content from the body, preserving both text and tables
    if soup.body:
        for element in soup.body.children:
            if element.name or (hasattr(element, 'strip') and element.strip()):
                # Add both tag elements and non-empty text nodes
                shell.body.append(element)
    else:
        # If no body tag, add all content
        for element in soup.children:
            if element.name or (hasattr(element, 'strip') and element.strip()):
                shell.body.append(element)

    # Return HTML with preserved formatting (keep newlines for bs4 processing)
    return str(shell)


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


def read_txt_file(file_path: Union[Path, str]) -> str:
    """Read the content of a txt file"""
    try:
        path = Path(file_path).expanduser().resolve()
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


def read_processed_files_content(file_paths: list[str], separator: str = "\n\n--- File Separator ---\n\n") -> str:
    """
    Read the content of files returned by retrieve_file_content function and return as a combined string.
    
    Args:
        file_paths: List of file paths returned by retrieve_file_content
        separator: String to separate content from different files (optional)
    
    Returns:
        str: Combined content of all files as a single string
    """
    if not file_paths:
        return ""
    
    combined_content = []
    
    for file_path in file_paths:
        try:
            path = Path(file_path)
            if path.exists():
                content = _read_text_auto(path)
                # Add file header for clarity
                file_header = f"=== Content from: {path.name} ==="
                combined_content.append(f"{file_header}\n{content}")
                print(f"✅ Read content from: {path.name}")
            else:
                error_msg = f"File not found: {file_path}"
                combined_content.append(f"❌ {error_msg}")
                print(f"⚠️ {error_msg}")
        except Exception as e:
            error_msg = f"Error reading {file_path}: {e}"
            combined_content.append(f"❌ {error_msg}")
            print(f"❌ {error_msg}")
    
    return separator.join(combined_content)


def extract_filename(file_path: str) -> str:
    """
    Extract filename from a file path or URL.
    
    Handles various path formats:
    - Windows: d:\folder\file.txt
    - Linux/Mac: /folder/file.txt  
    - HTTP URLs: https://example.com/folder/file.txt
    
    Args:
        file_path: File path or URL string
        
    Returns:
        str: The filename with extension
        
    Examples:
        >>> extract_filename(r"d:\asianInfo\ExcelAssist\燕云村case\正文稿关于印发通知.doc")
        '正文稿关于印发通知.doc'
        >>> extract_filename("/home/user/document.pdf")
        'document.pdf'
        >>> extract_filename("https://example.com/files/image.jpg")
        'image.jpg'
    """
    if not file_path:
        return ""
    
    # Replace backslashes with forward slashes for consistency
    normalized_path = file_path.replace('\\', '/')
    
    # Split by forward slash and take the last part
    filename = normalized_path.split('/')[-1]
    
    # Handle edge cases where path ends with slash
    if not filename:
        # If the path ends with a slash, try the second-to-last part
        parts = [part for part in normalized_path.split('/') if part]
        filename = parts[-1] if parts else file_path
    
    return filename


def fetch_related_files_content(related_files: dict[str], base_path: str = r"D:\asianInfo\ExcelAssist\files") -> dict[str, str]:
    """
    Wrapper function that receives a dictionary of classified related files, and invoke fetch_related_files_content
    to fetch the actual content
    """
    print("related_files:  aaaaaaaaaa", related_files)
    table_files = related_files["表格"]
    base_path = r"D:\asianInfo\ExcelAssist\files\table_files\html_content"
    table_files_content = fetch_files_content(table_files, base_path)

    # document_files = related_files["文档"]
    # base_path = r"D:\asianInfo\ExcelAssist\files\document_files\txt_content"
    # document_files_content = fetch_files_content(document_files, base_path)

    file_content = table_files_content

    return file_content



    

def fetch_files_content(related_files: List[str], base_path: str = r"D:\asianInfo\ExcelAssist\files") -> Dict[str, str]:
        """
        Fetch the content of related files from the specified directory
        
        Args:
            related_files: List of filenames to fetch
            base_path: Base directory path where files are stored
            
        Returns:
            Dictionary mapping filename to file content
        """
        files_content = {}
        base_directory = Path(base_path)
        
        for filename in related_files:
            # Handle both .txt and non-.txt filenames
            txt_filename = filename if filename.endswith('.txt') else f"{filename}.txt"
            file_path = base_directory / txt_filename
            
            try:
                if file_path.exists():
                    content = file_path.read_text(encoding='utf-8')
                    files_content[filename] = content
                    print(f"✅ 成功读取文件: {filename}")
                else:
                    print(f"⚠️  文件不存在: {file_path}")
                    files_content[filename] = ""
            except Exception as e:
                print(f"❌ 读取文件 {filename} 时出错: {e}")
                files_content[filename] = ""
        
        return files_content


def excel_to_csv(excel_file, csv_file, sheet_name="Sheet1"):
    """Enhanced Excel to CSV conversion with proper date handling"""
    import re
    
    try:
        # Read Excel file
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        print(f"📊 Processing {len(df.columns)} columns for date cleaning...")
        
        # Process each column to handle dates properly
        for col in df.columns:
            print(f"🔍 Processing column '{col}' with dtype: {df[col].dtype}")
            
            # Check if column contains datetime-like data
            if df[col].dtype == 'datetime64[ns]' or any(isinstance(x, pd.Timestamp) for x in df[col].dropna()):
                print(f"📅 Found datetime column: {col}")
                # Convert datetime columns to clean date format
                df[col] = df[col].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) and hasattr(x, 'strftime') else x)
            
            else:
                # Apply aggressive date cleaning to ALL columns (not just object columns)
                df[col] = df[col].apply(lambda x: clean_date_string(x) if pd.notna(x) else x)
        
        # Convert to CSV
        df.to_csv(csv_file, index=False, encoding='utf-8')
        print(f"✅ Successfully converted {excel_file} to {csv_file}")
        
        # Read back and verify cleaning worked
        with open(csv_file, 'r', encoding='utf-8') as f:
            sample_content = f.read()[:500]
            if " 00:00:00" in sample_content:
                print(f"⚠️ Warning: Still found '00:00:00' in output, applying post-processing...")
                # Apply additional cleaning to the entire CSV content
                with open(csv_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Clean up the content with regex
                content = re.sub(r' 00:00:00', '', content)
                content = re.sub(r'\.00\.00\.00', '', content)
                content = re.sub(r'\.0+(?=,|$)', '', content)
                
                # Write back the cleaned content
                with open(csv_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ Applied post-processing date cleanup")
        
    except Exception as e:
        print(f"❌ Error converting Excel to CSV: {e}")
        # Fallback to simple conversion with post-processing
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            df.to_csv(csv_file, index=False, encoding='utf-8')
            
            # Apply post-processing cleanup
            with open(csv_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            content = re.sub(r' 00:00:00', '', content)
            content = re.sub(r'\.00\.00\.00', '', content)
            
            with open(csv_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Fallback conversion with post-processing completed")
            
        except Exception as fallback_error:
            print(f"❌ Fallback conversion also failed: {fallback_error}")


def clean_date_string(value):
    """Clean up date strings and remove malformed time portions"""
    if not isinstance(value, str):
        return value
    
    # Remove malformed time formats like "00.00.00.00"
    if ".00.00.00" in str(value):
        value = str(value).replace(".00.00.00", "")
    
    # Remove "00:00:00" time portions from date strings
    if " 00:00:00" in str(value):
        value = str(value).replace(" 00:00:00", "")
    
    # Handle other common malformed patterns
    value = re.sub(r'\.00\.00\.00$', '', str(value))  # Remove trailing .00.00.00
    value = re.sub(r' 00:00:00\.0+$', '', str(value))  # Remove trailing 00:00:00.000...
    value = re.sub(r'\.0+$', '', str(value))  # Remove trailing .000...
    
    # Try to parse and reformat date strings
    try:
        # Common date patterns to try
        date_patterns = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y%m%d'
        ]
        
        for pattern in date_patterns:
            try:
                parsed_date = datetime.strptime(str(value), pattern)
                return parsed_date.strftime('%Y-%m-%d')  # Return clean date format
            except ValueError:
                continue
    except:
        pass
    
    return value  # Return original if no date pattern matched

def read_relative_files_from_data_json(data_json_path: str = "agents/data.json", headers_mapping: str = None) -> str:
    """
    Read the relative files from data.json file
    """
    with open(data_json_path, 'r', encoding='utf-8') as f:
        data_json = json.load(f)
        for key, value in data_json.items():
            if key in headers_mapping:
                return value
    return None
def find_largest_file(excel_file_paths: list[str]) -> str:
    """
    Find the largest file in the list of Excel file paths
    return a dictionary with the file path and the number of rows
    """
    file_row_counts = {}
    for file_path in excel_file_paths:
        try:
            df = pd.read_excel(file_path)
            # Count actual data rows (excluding header)
            data_rows = len(df.dropna(how='all'))  # Remove completely empty rows
            file_row_counts[file_path] = data_rows
            print(f"📊 {Path(file_path).name}: {data_rows} data rows")
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            file_row_counts[file_path] = 0
    
    # Find file with most rows
    largest_file = max(file_row_counts, key=file_row_counts.get)
    largest_row_count = file_row_counts[largest_file]
    print(f"🎯 Largest file: {Path(largest_file).name} with {largest_row_count} rows")
    return {largest_file: largest_row_count}

def detect_csv_format(csv_lines: list[str]) -> tuple[bool, int]:
    """
    Detect if CSV has repeated headers before each data row.
    
    Returns:
        tuple: (is_repeated_header_format, data_record_count)
    """
    if len(csv_lines) >= 4:  # Need at least 4 lines to detect pattern
        first_line = csv_lines[0].strip()
        third_line = csv_lines[2].strip()
        
        # If first and third lines are identical, it's likely repeated headers
        if first_line == third_line and first_line.count(',') > 0:
            # Each data record consists of header + data line
            data_rows = len(csv_lines) // 2
            print(f"🔍 Detected repeated header format: {len(csv_lines)} lines = {data_rows} data records")
            return True, data_rows
        else:
            # Normal CSV format with single header
            data_rows = len(csv_lines) - 1 if csv_lines else 0  # Subtract 1 for header
            print(f"🔍 Standard CSV format: {len(csv_lines)} lines = {data_rows} data records")
            return False, data_rows
    else:
        # Too few lines, use standard counting
        data_rows = len(csv_lines) - 1 if csv_lines else 0  # Subtract 1 for header
        return False, data_rows

def extract_structure_info_for_file(file_path: str, table_structure_info: dict) -> str:
    """
    Extract structure information for a specific file.
    
    Returns:
        str: Formatted structure information
    """
    file_name = Path(file_path).stem + ".txt"
    structure_info = ""
    
    if file_name in table_structure_info:
        file_structure = table_structure_info[file_name]
        
        try:
            summary_content = file_structure.get("summary", "")
            if summary_content:
                summary_content = summary_content.strip()
                
                if summary_content.startswith('{') and summary_content.endswith('}'):
                    parsed_summary = json.loads(summary_content)
                    
                    if file_name in parsed_summary:
                        file_data = parsed_summary[file_name]
                        
                        # Extract 表格结构 (detailed column structure)
                        table_structure = file_data.get("表格结构", {})
                        if table_structure:
                            structure_info += "=== 表格结构 ===\n"
                            structure_info += json.dumps(table_structure, ensure_ascii=False, indent=2) + "\n\n"
                        
                        # Extract 表格总结 (summary)
                        table_summary = file_data.get("表格总结", "")
                        if table_summary:
                            structure_info += "=== 表格总结 ===\n"
                            structure_info += table_summary + "\n\n"
                else:
                    structure_info += "=== 文件分析 ===\n"
                    structure_info += summary_content + "\n\n"
                        
        except json.JSONDecodeError:
            structure_info += "=== 文件分析 ===\n"
            structure_info += file_structure.get("summary", "") + "\n\n"
        
        # Also include the full summary if available and different from structured data
        if "summary" in file_structure and not structure_info:
            structure_info += "=== 完整分析 ===\n"
            structure_info += file_structure["summary"] + "\n\n"
    
    return structure_info

def parse_header_data_pairs(csv_lines: list[str], is_repeated_header: bool) -> list[tuple[str, str]]:
    """
    Parse CSV lines into header+data pairs.
    
    Args:
        csv_lines: List of CSV lines
        is_repeated_header: Whether the CSV has repeated headers
        
    Returns:
        list: List of (header, data) tuples
    """
    pairs = []
    
    if is_repeated_header:
        # Group every 2 lines as header+data pairs
        for i in range(0, len(csv_lines), 2):
            if i + 1 < len(csv_lines):
                header = csv_lines[i].strip()
                data = csv_lines[i + 1].strip()
                if header and data:  # Only add if both header and data exist
                    pairs.append((header, data))
    else:
        # Standard CSV: first line is header, rest are data
        if csv_lines:
            header = csv_lines[0].strip()
            for data_line in csv_lines[1:]:
                data = data_line.strip()
                if data:
                    pairs.append((header, data))
    
    return pairs

def create_chunks_from_pairs(pairs: list[tuple[str, str]], chunk_nums: int) -> list[list[tuple[str, str]]]:
    """
    Split header+data pairs into chunks, keeping pairs intact.
    
    Args:
        pairs: List of (header, data) tuples
        chunk_nums: Desired number of chunks
        
    Returns:
        list: List of chunks, each containing pairs
    """
    if not pairs:
        return []
    
    total_pairs = len(pairs)
    actual_chunk_nums = min(chunk_nums, total_pairs)
    
    if actual_chunk_nums == 0:
        return []
    
    base_chunk_size = total_pairs // actual_chunk_nums
    remainder = total_pairs % actual_chunk_nums
    
    print(f"📏 Dividing {total_pairs} data pairs into {actual_chunk_nums} chunks (requested: {chunk_nums})")
    print(f"   Base chunk size: {base_chunk_size} pairs, Extra pairs to distribute: {remainder}")
    
    chunks = []
    current_idx = 0
    
    for chunk_index in range(actual_chunk_nums):
        # First 'remainder' chunks get one extra pair
        if chunk_index < remainder:
            chunk_size = base_chunk_size + 1
        else:
            chunk_size = base_chunk_size
        
        start_idx = current_idx
        end_idx = current_idx + chunk_size
        
        chunk_pairs = pairs[start_idx:end_idx]
        chunks.append(chunk_pairs)
        current_idx = end_idx
        
        print(f"✅ Created chunk {chunk_index + 1}/{actual_chunk_nums} with {len(chunk_pairs)} data pairs")
    
    return chunks

def combine_chunk_content(chunk_pairs: list[tuple[str, str]], largest_structure_info: str, 
                         largest_filename: str, other_files_content: list[str], 
                         supplement_files_summary: str) -> str:
    """
    Combine chunk content with structure info and other files.
    
    Returns:
        str: Combined content for the chunk
    """
    chunk_combined = []
    
    # 1. Add other files' complete content (already includes structure)
    for other_content in other_files_content:
        if other_content.strip():
            chunk_combined.append(other_content)
    
    # 2. Add largest file structure + data chunk
    if chunk_pairs:
        largest_file_chunk_content = ""
        
        # Add structure information if available
        if largest_structure_info.strip():
            largest_file_chunk_content += largest_structure_info.strip() + "\n\n"
        
        # Add data header and reconstruct the header+data format
        largest_file_chunk_content += f"=== {largest_filename} 的表格数据 ===\n"
        
        # Reconstruct the alternating header+data format
        for header, data in chunk_pairs:
            largest_file_chunk_content += f"{header}\n{data}\n"
        
        chunk_combined.append(largest_file_chunk_content.rstrip())  # Remove trailing newline
    
    # 3. Add supplement information last
    if supplement_files_summary:
        if supplement_files_summary.strip().startswith("=== 补充文件内容 ==="):
            chunk_combined.append(supplement_files_summary)
        else:
            chunk_combined.append(f"=== 补充文件内容 ===\n{supplement_files_summary}")
    
    return "\n\n".join(chunk_combined)

def find_largest_file(csv_files: list[str], row_counts: list[int], largest_file: str = None) -> str:
    """
    Find the file with the most data rows.
    
    Returns:
        str: Path to the largest file
    """
    if largest_file is None:
        max_rows_idx = row_counts.index(max(row_counts))
        largest_file = csv_files[max_rows_idx]
        print(f"📊 Largest file: {Path(largest_file).name} with {row_counts[max_rows_idx]} rows")
    else:
        # Validate the specified largest file exists in our CSV files
        if largest_file not in csv_files:
            print(f"⚠️ Specified largest file not found in CSV files, using automatic selection")
            max_rows_idx = row_counts.index(max(row_counts))
            largest_file = csv_files[max_rows_idx]
    
    return largest_file

def process_excel_files_with_chunking(excel_file_paths: list[str], supplement_files_summary: str = "", 
                                      session_id: str = "1", chunk_nums: int = 5, largest_file: str = None,
                                      data_json_path: str = "agents/data.json") -> dict:
    """
    Process Excel files by reading their corresponding pre-generated CSV files,
    finding the one with most rows, chunking the largest file, and combining everything.
    
    Args:
        excel_file_paths: List of Excel file paths (used to find corresponding CSV files)
        supplement_files_summary: String containing supplement file content (not a list)
        session_id: Session identifier for folder structure
        chunk_nums: Number of chunks to create (default 5)
        largest_file: Optional pre-specified largest file path
        data_json_path: Path to data.json file containing structure information
        
    Returns:
        dict: {
            "combined_chunks": List of strings, each containing combined content of one chunk with other files
            "largest_file_row_count": int, number of data rows in the largest file
        }
    """
    print(f"🔄 Processing {len(excel_file_paths)} Excel files...")
    if supplement_files_summary:
        print(f"📄 Also processing supplement files content")
    
    # Map Excel file paths to corresponding CSV files in CSV_files directory
    csv_files = []
    row_counts = []
    csv_base_dir = Path("files/table_files/CSV_files")
    
    if not csv_base_dir.exists():
        print(f"❌ CSV files directory not found: {csv_base_dir}")
        return {"combined_chunks": [], "largest_file_row_count": 0}
    
    # Step 1: Find corresponding CSV files and count rows
    file_contents = {}  # {original_excel_path: csv_content}
    
    for excel_path in excel_file_paths:
        excel_filename = Path(excel_path).stem  # Get filename without extension
        csv_file_path = csv_base_dir / f"{excel_filename}.csv"
        
        if csv_file_path.exists():
            try:
                # Read CSV content
                with open(csv_file_path, 'r', encoding='utf-8') as f:
                    csv_content = f.read()
                
                # Count data rows using helper function
                csv_lines = csv_content.strip().split('\n')
                is_repeated_header, data_rows = detect_csv_format(csv_lines)
                
                csv_files.append(excel_path)  # Keep original Excel path as key
                row_counts.append(data_rows)
                
                # Store content with proper headers
                combined_content = f"=== {Path(excel_path).name} 的表格数据 ===\n{csv_content}"
                file_contents[excel_path] = combined_content
                
                print(f"✅ Found CSV for {Path(excel_path).name}: {data_rows} data rows")
                
            except Exception as e:
                print(f"❌ Error reading CSV for {Path(excel_path).name}: {e}")
                file_contents[excel_path] = f"Error reading CSV file: {e}"
                csv_files.append(excel_path)
                row_counts.append(0)
        else:
            print(f"⚠️ No corresponding CSV found for {Path(excel_path).name}, skipping...")
    
    if not csv_files:
        print("❌ No CSV files found for processing")
        return {"combined_chunks": [], "largest_file_row_count": 0}
    
    # Step 2: Load structure information from data.json
    table_structure_info = {}
    if Path(data_json_path).exists():
        try:
            with open(data_json_path, 'r', encoding='utf-8') as f:
                data_content = json.load(f)
                # Get table structure info from all locations
                for location_key, location_data in data_content.items():
                    if isinstance(location_data, dict) and "表格" in location_data:
                        table_structure_info.update(location_data["表格"])
                print(f"📋 Loaded structure info for {len(table_structure_info)} tables")
        except Exception as e:
            print(f"⚠️ Failed to load structure info: {e}")
    
    # Step 3: Add structure information to file contents
    for excel_path in list(file_contents.keys()):
        structure_info = extract_structure_info_for_file(excel_path, table_structure_info)
        
        # Update file content to include structure information
        if structure_info:
            original_content = file_contents[excel_path]
            filename = Path(excel_path).name
            new_content = f"=== {filename} 的表格结构 ===\n{structure_info}=== {filename} 的表格数据 ===\n"
            # Extract the CSV data part
            csv_data = original_content.split(f"=== {filename} 的表格数据 ===\n", 1)[1] if f"=== {filename} 的表格数据 ===" in original_content else original_content
            file_contents[excel_path] = new_content + csv_data
            print(f"✅ Added structure info for {filename}")
    
    # Step 4: Find the largest file by row count
    largest_file = find_largest_file(csv_files, row_counts, largest_file)
    
    # Step 5: Handle the largest file - divide into chunks while preserving header+data pairs
    largest_file_content = file_contents[largest_file]
    other_files_content = [content for path, content in file_contents.items() if path != largest_file]
    
    # Extract data from the largest file content
    largest_file_lines = largest_file_content.split('\n')
    largest_filename = Path(largest_file).name
    data_header_pattern = f"=== {largest_filename} 的表格数据 ==="
    
    # Find where the actual CSV data starts and extract structure info
    data_section_start = -1
    for i, line in enumerate(largest_file_lines):
        if line.strip() == data_header_pattern:
            data_section_start = i
            break
    
    if data_section_start == -1:
        print(f"⚠️ Could not find data section separator '{data_header_pattern}', using full content")
        largest_structure_info = ""
        largest_data_lines = largest_file_lines
    else:
        # Structure is everything before the data header
        largest_structure_info = '\n'.join(largest_file_lines[:data_section_start])
        # Data is everything after the data header (excluding the header itself)
        largest_data_lines = largest_file_lines[data_section_start + 1:]
    
    # Remove empty lines at the beginning and end of data
    while largest_data_lines and not largest_data_lines[0].strip():
        largest_data_lines.pop(0)
    while largest_data_lines and not largest_data_lines[-1].strip():
        largest_data_lines.pop()
    
    # Detect format and parse into header+data pairs
    is_repeated_header, _ = detect_csv_format(largest_data_lines)
    header_data_pairs = parse_header_data_pairs(largest_data_lines, is_repeated_header)
    
    if not header_data_pairs:
        print("⚠️ No valid header+data pairs found")
        return {"combined_chunks": [], "largest_file_row_count": 0}
    
    # Create chunks from pairs (preserving header+data integrity)
    pair_chunks = create_chunks_from_pairs(header_data_pairs, chunk_nums)
    
    if not pair_chunks:
        print("⚠️ No chunks created")
        return {"combined_chunks": [], "largest_file_row_count": 0}
    
    # Step 6: Combine chunks with other content
    combined_chunks = []
    for chunk_index, chunk_pairs in enumerate(pair_chunks):
        combined_content = combine_chunk_content(
            chunk_pairs, largest_structure_info, largest_filename, 
            other_files_content, supplement_files_summary
        )
        combined_chunks.append(combined_content)
    
    print(f"🎉 Successfully created {len(combined_chunks)} combined chunks")
    
    # Return both chunks and largest file row count
    largest_file_row_count = row_counts[csv_files.index(largest_file)] if largest_file in csv_files else 0
    
    return {
        "combined_chunks": combined_chunks,
        "largest_file_row_count": largest_file_row_count
    }



def extract_file_from_recall(response: str) -> list:
    """返回文件名数组"""

    # Parse the response to extract the file list
    print(f"🔍 开始解析响应内容: {response[:200]}...")
    
    try:
        # Try to parse as JSON array first
        related_files = json.loads(response)
        if isinstance(related_files, list):
            print(f"✅ 成功解析JSON数组: {related_files}")
            return related_files
    except:
        print("❌ JSON解析失败，尝试其他方法")
        pass
    
    try:
        # Look for patterns like ["file1", "file2"] or ['file1', 'file2']
        match = re.search(r'\[.*?\]', response)
        if match:
            related_files = json.loads(match.group())
            print(f"✅ 正则匹配成功: {related_files}")
            return related_files
    except:
        print("❌ 正则表达式匹配失败")
        pass
    
    # Check if response contains file names with .txt, .xlsx, .docx extensions
    file_pattern = r'["""]([^"""]*?\.(txt|xlsx|docx|csv|pdf))["""]'
    file_matches = re.findall(file_pattern, response)
    if file_matches:
        related_files = [match[0] for match in file_matches]
        print(f"✅ 文件名模式匹配成功: {related_files}")
        return related_files
    
    # Final fallback: split by lines and filter
    related_files = [line.strip().strip('"\'') for line in response.split('\n') 
                    if line.strip() and not line.strip().startswith('#') and 
                    any(ext in line.lower() for ext in ['.txt', '.xlsx', '.docx', '.csv', '.pdf'])]
    
    print(f"📁 解析出的相关文件: {related_files}")
    return related_files

def _clean_csv_data(csv_data: str) -> str:
    """
    Clean up the CSV data by removing the thinking part and only keeping the actual data
    under the "===最终答案===" section
    
    Args:
        csv_data: Raw CSV data string containing both reasoning and final answer
        
    Returns:
        str: Cleaned CSV data with only the actual data rows
    """
    csv_data_lines = csv_data.split('\n')
    
    # Find the start of the final answer section
    final_answer_started = False
    cleaned_lines = []
    
    for line in csv_data_lines:
        line = line.strip()
        
        # Check if we've reached the final answer section
        if "=== 最终答案 ===" in line:
            final_answer_started = True
            continue
        
        # If we encounter a new reasoning section, stop collecting
        if final_answer_started and "=== 推理过程 ===" in line:
            final_answer_started = False
            continue
        
        # If we're in the final answer section, collect the data lines
        if final_answer_started:
            # Skip empty lines and lines that look like section headers
            if line and not line.startswith("==="):
                cleaned_lines.append(line)
    
    # Join the cleaned lines
    return '\n'.join(cleaned_lines)

def save_csv_to_output(csv_data_list: list[str], session_id: str = "1") -> str:
    """
    Save CSV data to session-specific CSV_files folder
    
    Args:
        csv_data_list: List of CSV strings from concurrent processing
        session_id: Session identifier for folder structure
    
    Returns:
        str: Full path to the saved CSV file
    """
    import os
    from datetime import datetime
    from pathlib import Path
    
    # Create output directory
    output_dir = Path(f"D:\\asianInfo\\ExcelAssist\\conversations\\{session_id}\\CSV_files")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    actual_filename_with_thinking = "synthesized_table_with_thinking"
    actual_filename_with_only_data = "synthesized_table_with_only_data"
    filename_with_thinking = f"{actual_filename_with_thinking}.csv"
    filename_with_only_data = f"{actual_filename_with_only_data}.csv"
    filepath_with_thinking = output_dir / filename_with_thinking
    filepath_with_only_data = output_dir / filename_with_only_data
    
    # Combine all CSV data and clean up
    combined_csv = '\n'.join(csv_data_list)
    
    # Remove unnecessary newlines and clean up the CSV content
    lines = combined_csv.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line:  # Only keep non-empty lines
            cleaned_lines.append(line)
    
    # Join with single newlines
    final_csv = '\n'.join(cleaned_lines)

    # Write to file with thinking process
    with open(filepath_with_thinking, 'w', encoding='utf-8', newline='') as f:
        f.write(final_csv)
    
    # Write to file with only cleaned data (using helper function)
    with open(filepath_with_only_data, 'w', encoding='utf-8', newline='') as f:
        cleaned_data = _clean_csv_data(final_csv)
        f.write(cleaned_data)
            
    print(f"💾 CSV数据已保存到: {filepath_with_thinking}")
    print(f"📄 CSV数据已保存到: {filepath_with_only_data}")
    print(f"📊 清理后包含 {len(cleaned_lines)} 行数据")
    return str(filepath_with_thinking), str(filepath_with_only_data)



def get_available_locations(data: dict) -> list[str]:
        """
        从data.json中获取可用的村/镇位置列表
        
        Args:
            data: data.json的数据结构
            
        Returns:
            list[str]: 可用的位置列表
        """
        locations = []
        for key in data.keys():
            if isinstance(data[key], dict) and "表格" in data[key] and "文档" in data[key]:
                locations.append(key)
        return locations

def determine_location_from_content(file_content: str, file_name: str, user_input: str, available_locations: list[str]) -> str:
    """
    根据文件内容、文件名和用户输入确定文件所属的村/镇
    
    Args:
        file_content: 文件内容
        file_name: 文件名
        user_input: 用户输入
        available_locations: 可用的位置列表（从data.json读取）
        
    Returns:
        location: 确定的位置，如果无法确定则返回第一个可用位置
    """
    if not available_locations:
        print("⚠️ 没有可用的位置，创建默认位置")
        return "默认位置"
    
    # 首先检查文件名中是否包含位置信息
    for location in available_locations:
        if location in file_name:
            print(f"📍 从文件名确定位置: {location}")
            return location
    
    # 检查文件内容中是否包含位置信息
    content_to_check = file_content[:1000]  # 只检查前1000个字符
    for location in available_locations:
        if location in content_to_check:
            print(f"📍 从文件内容确定位置: {location}")
            return location
    
    # 检查用户输入中是否包含位置信息
    for location in available_locations:
        if location in user_input:
            print(f"📍 从用户输入确定位置: {location}")
            return location
    
    # 如果无法确定，使用LLM进行智能分析
    try:
        analysis_prompt = f"""
        请分析以下信息，判断文件属于哪个村/镇：
        
        可选位置：{', '.join(available_locations)}
        
        文件名：{file_name}
        用户输入：{user_input}
        文件内容片段：{content_to_check}
        
        请只回复确定的位置名称，如果无法确定，请回复"{available_locations[0]}"。
        """
        
        analysis_result = invoke_model(model_name="Qwen/Qwen3-32B", 
                                        messages=[SystemMessage(content=analysis_prompt)])
        
        for location in available_locations:
            if location in analysis_result:
                print(f"📍 通过LLM分析确定位置: {location}")
                return location
                
    except Exception as e:
        print(f"❌ LLM位置分析失败: {e}")
    
    # 默认返回第一个可用位置
    default_location = available_locations[0]
    print(f"📍 使用默认位置: {default_location}")
    return default_location

def ensure_location_structure(data: dict, location: str) -> dict:
    """
    确保指定位置的数据结构存在
    
    Args:
        data: 当前的数据结构
        location: 需要确保存在的位置
        
    Returns:
        dict: 更新后的数据结构
    """
    if location not in data:
        data[location] = {"表格": {}, "文档": {}}
        print(f"📝 创建新位置结构: {location}")
    elif not isinstance(data[location], dict):
        data[location] = {"表格": {}, "文档": {}}
        print(f"📝 修复位置结构: {location}")
    else:
        if "表格" not in data[location]:
            data[location]["表格"] = {}
        if "文档" not in data[location]:
            data[location]["文档"] = {}
    
    return data

def check_file_exists_in_data(data: dict, file_name: str) -> bool:
    """
    检查文件是否已存在于data.json中
    
    Args:
        data: data.json的数据结构
        file_name: 文件名
        
    Returns:
        bool: 文件是否存在
    """
    for location in data.keys():
        if isinstance(data[location], dict):
            if file_name in data[location].get("表格", {}) or file_name in data[location].get("文档", {}):
                return True
    return False



def move_template_file_safely(source_file: str, dest_dir_name: str = "template_files") -> str:
        """
        Safely move a template file to the destination directory, handling existing files.
        
        This function ensures robust file handling by:
        - Creating the destination directory if it doesn't exist
        - Generating unique filenames when target files already exist (adds _1, _2, etc.)
        - Gracefully handling move errors and maintaining original path as fallback
        - Providing detailed logging of the process
        
        Args:
            source_file: Path to the source file to be moved
            dest_dir_name: Name of the destination directory under conversations/files/user_uploaded_files/
            
        Returns:
            str: Path to the final file location (new path if moved successfully, original path if failed)
        """
        try:
            dest_dir = Path(f"conversations/files/user_uploaded_files/{dest_dir_name}")
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            source_file_path = Path(source_file)
            target_file_path = dest_dir / source_file_path.name
            
            # Handle existing file case by deleting old file
            if target_file_path.exists():
                print(f"⚠️ 目标文件已存在: {target_file_path.name}")
                try:
                    target_file_path.unlink()  # Delete the existing file
                    print(f"🗑️ 已删除旧文件: {target_file_path.name}")
                except Exception as delete_error:
                    print(f"❌ 删除旧文件失败: {delete_error}")
                    # If we can't delete the old file, we can't proceed
                    return source_file
            
            # Move the file
            source_file_path.rename(target_file_path)
            print(f"✅ 模板文件已移动到: {target_file_path}")
            return str(target_file_path)
            
        except Exception as move_error:
            print(f"❌ 移动模板文件失败: {move_error}")
            print(f"⚠️ 保持原始文件路径: {source_file}")
            return source_file


def move_template_files_safely(processed_template_file: str, original_files_list: list[str], dest_dir_name: str = "template_files") -> dict[str, str]:
    """
    Safely move both processed and original template files to the template_files directory.
    
    This function handles moving both the processed template file (.txt) and its corresponding
    original file to the template_files folder, with proper error handling and logging.
    
    Args:
        processed_template_file: Path to the processed template file (.txt)
        original_files_list: List of original file paths to search for the corresponding original file
        dest_dir_name: Name of the destination directory under conversations/files/user_uploaded_files/
        
    Returns:
        dict: {
            "processed_template_path": str,  # Path to moved processed template file
            "original_template_path": str    # Path to moved original template file (or empty if not found)
        }
    """
    import shutil
    
    try:
        # Create destination directories
        dest_dir = Path(f"conversations/files/user_uploaded_files/{dest_dir_name}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Create original_file subdirectory within template_files
        original_dest_dir = dest_dir / "original_file"
        original_dest_dir.mkdir(parents=True, exist_ok=True)
        
        processed_template_path = Path(processed_template_file)
        result = {
            "processed_template_path": "",
            "original_template_path": ""
        }
        
        print(f"📁 正在移动模板文件: {processed_template_path.name}")
        
        # Move the processed template file
        processed_target_path = dest_dir / processed_template_path.name
        
        # Handle existing processed file
        if processed_target_path.exists():
            print(f"⚠️ 处理模板文件已存在: {processed_target_path.name}")
            try:
                processed_target_path.unlink()
                print(f"🗑️ 已删除旧的处理模板文件: {processed_target_path.name}")
            except Exception as delete_error:
                print(f"❌ 删除旧的处理模板文件失败: {delete_error}")
                result["processed_template_path"] = processed_template_file
                return result
        
        # Move processed template file
        try:
            shutil.move(str(processed_template_path), str(processed_target_path))
            result["processed_template_path"] = str(processed_target_path)
            print(f"✅ 处理模板文件已移动到: {processed_target_path}")
        except Exception as move_error:
            print(f"❌ 移动处理模板文件失败: {move_error}")
            result["processed_template_path"] = processed_template_file
            return result
        
        # Find and move the corresponding original file
        template_file_stem = processed_template_path.stem
        original_file_found = False
        
        print(f"🔍 正在寻找对应的原始模板文件: {template_file_stem}")
        
        for original_file in original_files_list:
            original_file_path = Path(original_file)
            if original_file_path.stem == template_file_stem:
                print(f"📋 找到对应的原始文件: {original_file_path.name}")
                
                # Move the original file to the original_file subdirectory
                original_target_path = original_dest_dir / original_file_path.name
                
                # Handle existing original file
                if original_target_path.exists():
                    print(f"⚠️ 原始模板文件已存在: {original_target_path.name}")
                    try:
                        original_target_path.unlink()
                        print(f"🗑️ 已删除旧的原始模板文件: {original_target_path.name}")
                    except Exception as delete_error:
                        print(f"❌ 删除旧的原始模板文件失败: {delete_error}")
                        # Continue with moving even if deletion failed
                
                # Move original file
                try:
                    shutil.move(str(original_file_path), str(original_target_path))
                    result["original_template_path"] = str(original_target_path)
                    print(f"✅ 原始模板文件已移动到: {original_target_path}")
                    original_file_found = True
                    break
                except Exception as move_error:
                    print(f"❌ 移动原始模板文件失败: {move_error}")
                    # Continue searching for other matching files
        
        if not original_file_found:
            print(f"⚠️ 未找到对应的原始模板文件: {template_file_stem}")
            result["original_template_path"] = ""
        
        return result
        
    except Exception as e:
        print(f"❌ 移动模板文件过程中出错: {e}")
        return {
            "processed_template_path": processed_template_file,
            "original_template_path": ""
        }

def convert_html_to_excel(html_file_path: str, output_dir: str = None) -> str:
    """
    Convert HTML file to Excel format using session-specific output directory
    
    Args:
        html_file_path: Path to the HTML file to convert
        output_dir: Output directory path (should be session-specific)
    
    Returns:
        str: Path to the converted Excel file
    """
    # Function implementation placeholder
    pass

def move_template_files_to_final_destination(processed_file_path: str, original_file_path: str, session_id: str) -> dict[str, str]:
    """Move template files from staging area to final destination.
    
    Destination: conversations/session_id/user_uploaded_files/template/
    
    Args:
        processed_file_path: Path to processed template file in staging area
        original_file_path: Path to original template file in staging area
        session_id: Session identifier
        
    Returns:
        dict: {
            "processed_template_path": str,  # Final path of processed template
            "original_template_path": str    # Final path of original template
        }
    """
    import shutil
    from pathlib import Path
    
    try:
        # Create destination directory
        project_root = Path.cwd()
        dest_dir = project_root / "conversations" / session_id / "user_uploaded_files" / "template"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        result = {
            "processed_template_path": "",
            "original_template_path": ""
        }
        
        # Move processed template file
        if processed_file_path and Path(processed_file_path).exists():
            processed_source = Path(processed_file_path)
            processed_target = dest_dir / processed_source.name
            
            # Handle existing file
            if processed_target.exists():
                print(f"⚠️ 模板文件已存在，正在更新: {processed_target.name}")
                processed_target.unlink()
            
            shutil.move(str(processed_source), str(processed_target))
            result["processed_template_path"] = str(processed_target)
            print(f"✅ 模板文件已移动到: {processed_target}")
        
        # Move original template file
        if original_file_path and Path(original_file_path).exists():
            original_source = Path(original_file_path)
            original_target = dest_dir / original_source.name
            
            # Handle existing file
            if original_target.exists():
                print(f"⚠️ 原始模板文件已存在，正在更新: {original_target.name}")
                original_target.unlink()
            
            shutil.move(str(original_source), str(original_target))
            result["original_template_path"] = str(original_target)
            print(f"✅ 原始模板文件已移动到: {original_target}")
        
        return result
        
    except Exception as e:
        print(f"❌ 移动模板文件时出错: {e}")
        return {
            "processed_template_path": processed_file_path,
            "original_template_path": original_file_path
        }



def move_supplement_files_to_final_destination(processed_file_path: str, original_file_path: str, file_type: str) -> dict[str, str]:
    """Move supplement files from staging area to final destination with simple override strategy.
    
    Destinations:
    - Table files: conversations/files/table_files/html_content/ and conversations/files/table_files/original/
    - Document files: conversations/files/document_files/txt_content/ and conversations/files/document_files/original/
    
    Args:
        processed_file_path: Path to processed supplement file in staging area
        original_file_path: Path to original supplement file in staging area
        file_type: Either "table" or "document"
        
    Returns:
        dict: {
            "processed_supplement_path": str,  # Final path of processed supplement
            "original_supplement_path": str    # Final path of original supplement
        }
    """
    import shutil
    import stat
    from pathlib import Path
    
    def remove_readonly_and_delete(target_path: Path):
        """Remove read-only attribute and delete file"""
        try:
            if target_path.exists():
                # Remove read-only attribute
                target_path.chmod(stat.S_IWRITE | stat.S_IREAD)
                target_path.unlink()
                print(f"🗑️ 已删除只读文件: {target_path.name}")
        except Exception as e:
            print(f"⚠️ 删除文件时出错: {e}")
            raise
    
    try:
        # Determine destination based on file type
        project_root = Path.cwd()
        
        if file_type == "table":
            processed_content_dir = project_root / "files" / "table_files" / "html_content"
            original_dir = project_root / "files" / "table_files" / "original"
        elif file_type == "document":
            processed_content_dir = project_root / "files" / "document_files" / "txt_content"
            original_dir = project_root / "files" / "document_files" / "original"
        else:
            print(f"❌ 无效的文件类型: {file_type}")
            return {
                "processed_supplement_path": processed_file_path,
                "original_supplement_path": original_file_path
            }
        
        # Create destination directories
        processed_content_dir.mkdir(parents=True, exist_ok=True)
        original_dir.mkdir(parents=True, exist_ok=True)
        
        result = {
            "processed_supplement_path": "",
            "original_supplement_path": ""
        }
        
        # Move processed supplement file
        if processed_file_path and Path(processed_file_path).exists():
            processed_source = Path(processed_file_path)
            processed_target = processed_content_dir / processed_source.name
            
            # Handle existing file with read-only attribute
            if processed_target.exists():
                print(f"⚠️ 补充文件已存在，正在覆盖: {processed_target.name}")
                remove_readonly_and_delete(processed_target)
            
            shutil.move(str(processed_source), str(processed_target))
            result["processed_supplement_path"] = str(processed_target)
            print(f"✅ 补充文件已移动到: {processed_target}")
        
        # Move original supplement file
        if original_file_path and Path(original_file_path).exists():
            original_source = Path(original_file_path)
            original_target = original_dir / original_source.name
            
            # Handle existing file with read-only attribute
            if original_target.exists():
                print(f"⚠️ 原始补充文件已存在，正在覆盖: {original_target.name}")
                remove_readonly_and_delete(original_target)
            
            shutil.move(str(original_source), str(original_target))
            result["original_supplement_path"] = str(original_target)
            print(f"✅ 原始补充文件已移动到: {original_target}")
        
        return result
        
    except Exception as e:
        print(f"❌ 移动补充文件时出错: {e}")
        return {
            "processed_supplement_path": processed_file_path,
            "original_supplement_path": original_file_path
        }


def delete_files_from_staging_area(file_paths: list[str]) -> dict[str, list[str]]:
    """Delete irrelevant files from staging area.
    
    Args:
        file_paths: List of file paths to delete
        
    Returns:
        dict: {
            "deleted_files": list[str],  # Successfully deleted files
            "failed_deletes": list[str]  # Files that failed to delete
        }
    """
    from pathlib import Path
    
    deleted_files = []
    failed_deletes = []
    
    for file_path in file_paths:
        try:
            file_to_delete = Path(file_path)
            if file_to_delete.exists():
                file_to_delete.unlink()
                deleted_files.append(str(file_to_delete))
                print(f"🗑️ 已删除无关文件: {file_to_delete.name}")
            else:
                print(f"⚠️ 文件不存在，跳过删除: {file_path}")
        except Exception as e:
            failed_deletes.append(file_path)
            print(f"❌ 删除文件失败 {file_path}: {e}")
    
    print(f"📊 删除结果: 成功 {len(deleted_files)} 个，失败 {len(failed_deletes)} 个")
    
    return {
        "deleted_files": deleted_files,
        "failed_deletes": failed_deletes
    }




def reconstruct_csv_with_headers(analysis_response: str, original_filename: str, original_excel_file_path: str = None) -> str:
    """
    Reconstruct CSV file with headers using the analyzed table structure.
    
    Args:
        table_file_path: Path to the processed table file (.txt with HTML content)
        analysis_response: JSON response from LLM containing table structure
        original_filename: Original filename for the output CSV
        original_excel_file_path: Path to the original Excel file for CSV conversion
        
    Returns:
        str: Path to the reconstructed CSV file
    """
    try:
        # Create output directory
        project_root = Path.cwd()
        csv_output_dir = project_root / "files" / "table_files" / "CSV_files"
        csv_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Parse the analysis response to extract table structure
        try:
            if analysis_response.startswith('{') and analysis_response.endswith('}'):
                structure_data = json.loads(analysis_response)
            else:
                # Try to find JSON within the response
                import re
                json_match = re.search(r'\{.*\}', analysis_response, re.DOTALL)
                if json_match:
                    structure_data = json.loads(json_match.group())
                else:
                    raise ValueError("No valid JSON found in analysis response")
        except json.JSONDecodeError as e:
            print(f"❌ 解析表格结构JSON失败: {e}")
            return ""
        
        # Extract the table structure from the first key (should be filename)
        table_key = list(structure_data.keys())[0]
        table_structure = structure_data[table_key].get("表格结构", {})
        
        # Determine the Excel file path to use
        if original_excel_file_path and Path(original_excel_file_path).exists():
            excel_file_path = Path(original_excel_file_path)
        else:
            print("❌ 未提供原始Excel文件路径或文件不存在")
            return ""
        
        # Convert the original Excel file to CSV using helper function
        temp_csv_path = csv_output_dir / f"temp_{excel_file_path.stem}.csv"
        
        # Import the helper function
        from utilities.file_process import excel_to_csv
        
        try:
            # Use the existing helper function to convert Excel to CSV
            excel_to_csv(str(excel_file_path), str(temp_csv_path))
            print(f"📊 Excel文件已转换为CSV: {temp_csv_path}")
        except Exception as e:
            print(f"❌ Excel转CSV失败: {e}")
            return ""
        
        # Read the CSV data (skip header row)
        try:
            with open(temp_csv_path, 'r', encoding='utf-8') as f:
                csv_lines = f.readlines()
            
            # Skip the header row and get data rows
            print(f"这是我们CSV_lines的内容：\n{csv_lines}")
            data_rows = [line.strip() for line in csv_lines[2:] if line.strip()]
            print(f"这是我们CSV的内容strip 表头：\n{data_rows}")
            
            if not data_rows:
                print("❌ CSV文件中未找到数据行")
                return ""
            
            # Clean up temporary CSV file
            temp_csv_path.unlink()
            
        except Exception as e:
            print(f"❌ 读取CSV文件失败: {e}")
            return ""
        
        print(f"📊 提取到 {len(data_rows)} 行数据")
        
        # Dynamically adjust chunking based on data size
        max_chunks = 15  # Maximum number of chunks we want to create
        total_rows = len(data_rows)
        
        if total_rows <= max_chunks:
            # If we have fewer rows than max chunks, create one chunk per row
            chunks = [[row] for row in data_rows]
            print(f"📦 数据行数({total_rows})小于等于最大分块数({max_chunks})，创建 {len(chunks)} 个单行分块")
        else:
            # If we have more rows than max chunks, distribute evenly
            chunk_size = max(1, total_rows // max_chunks)
            chunks = [data_rows[i:i + chunk_size] for i in range(0, total_rows, chunk_size)]
            print(f"📦 数据行数({total_rows})大于最大分块数({max_chunks})，创建 {len(chunks)} 个分块，每块约 {chunk_size} 行")
        
        print(f"📏 数据分为 {len(chunks)} 个块进行处理")
        
        # Process chunks with multi-threading
        def process_chunk(chunk_data: list, chunk_index: int) -> tuple[int, str]:
            """Process a single chunk with LLM"""
            try:
                # Validate chunk data - skip if empty or invalid
                valid_data = [row for row in chunk_data if row.strip() and ',' in row]
                if not valid_data:
                    print(f"⚠️ 跳过块 {chunk_index + 1} - 无有效数据")
                    return chunk_index, ""
                
                print(f"🔍 块 {chunk_index + 1} 包含有效数据: {len(valid_data)} 行")
                
                system_prompt = f"""
你是一位专业的表格结构分析与数据重构专家。

【任务说明】
我将依次提供以下两部分内容：
1. 表格的**结构化表头信息**，已经按照层级关系整理好；
2. 一组对应该表头的**CSV数据行**；

【你的目标】
请根据提供的表头结构，为每一行 CSV 数据补上一行其对应的表头信息，从而生成一个新的 CSV 文件，满足如下要求：

【输出要求】
- 每一行数据的**上一行必须是该行对应的完整表头**；
- 表头应严格按照原始结构中的**最底层字段顺序**排列；
- 表头与数据的列数、顺序完全一致；
- 输出结果为纯净的 CSV 格式（英文逗号分隔，每行以换行符结尾）；
- 不要添加任何额外注释或解释性文本；

【输入示例】
表头结构格式如下：
{{
    "{{file_name}}": {{
        "表格结构": {{
            "顶层表头名称": {{
                "二级表头名称": [
                    "字段1",
                    "字段2",
                    ...
                ],
                "更多子表头": [
                    "字段A",
                    "字段B"
                ]
            }}
        }},
        "表格总结": "该表格的主要用途及内容说明..."
    }}
}}

CSV数据示例如下：
csv数据1，csv数据2，csv数据3，...，csv数据10

【输出示例】
字段1,字段2,字段3,...,字段10  
数据1,数据2,数据3,...,数据10  
字段1,字段2,字段3,...,字段10  
数据11,数据12,数据13,...,数据20  
（如此类推）

请注意：
- 只需要处理"最底层字段"，无需在输出中包含中间层级表头；
- 每一组字段必须严格对应一组数据，不要出现数据行与表头行不匹配的情况
- 对于数据块中的表头行（判断标准为字段和表头结构完全一致），不要做任何处理，跳过这一行，处理下一行
- 如果数据块里面只有表头行（判断标准为字段和表头结构完全一致），没有任何实际数据，直输出空值，不要输出任何其他的内容
- 只有当数据块包含有效的CSV数据行时，才输出对应的表头+数据格式
- 生成的表头行应保持一致性，始终与原始字段顺序匹配。
"""
                
                # Prepare input for this chunk using validated data
                chunk_input = f"""
=== 表格结构 ===
{json.dumps(structure_data, ensure_ascii=False, indent=2)}

=== CSV数据 ===
{chr(10).join(valid_data)}
"""
                
                print(f"📤 处理块 {chunk_index + 1} (原始: {len(chunk_data)} 行, 有效: {len(valid_data)} 行)")
                print(f"🔍 重构CSV输入数据块内容\n: {chunk_input}") 
                # Call LLM
                response = invoke_model(
                    model_name="Pro/deepseek-ai/DeepSeek-V3",
                    messages=[SystemMessage(content=system_prompt), HumanMessage(content=chunk_input)],
                    temperature=0.2
                )
                
                print(f"📥 块 {chunk_index + 1} 处理完成")
                return chunk_index, response
                
            except Exception as e:
                print(f"❌ 处理块 {chunk_index + 1} 失败: {e}")
                return chunk_index, ""
        
        # Process all chunks in parallel
        chunk_results = {}
        max_workers = min(len(chunks), 15)  # Dynamically adjust workers based on actual chunk count
        print(f"👥 使用 {max_workers} 个并发工作者处理 {len(chunks)} 个数据块")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {
                executor.submit(process_chunk, chunk, i): i 
                for i, chunk in enumerate(chunks)
            }
            
            for future in as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                try:
                    idx, result = future.result()
                    chunk_results[idx] = result
                except Exception as e:
                    print(f"❌ 块 {chunk_index} 处理出错: {e}")
                    chunk_results[chunk_index] = ""
        
        # Combine results in order, filtering out empty results
        combined_csv = []
        for i in range(len(chunks)):
            if i in chunk_results and chunk_results[i] and chunk_results[i].strip():
                combined_csv.append(chunk_results[i])
                print(f"✅ 添加块 {i + 1} 的结果到最终CSV")
        
        # Join all chunks
        final_csv_content = '\n'.join(combined_csv)
        
        # Save to CSV file
        csv_filename = Path(original_filename).stem + ".csv"
        csv_output_path = csv_output_dir / csv_filename
        print("这是我们CSV的内容：\n", final_csv_content)
        with open(csv_output_path, 'w', encoding='utf-8', newline='') as f:
            f.write(final_csv_content)
        
        print(f"💾 重构的CSV文件已保存: {csv_output_path}")
        return str(csv_output_path)
        
    except Exception as e:
        print(f"❌ CSV重构过程出错: {e}")
        return ""
    

def extract_summary_for_each_file(file_content: dict) -> str:
            """提取文件内容的摘要信息"""
            summary = ""
            
            # 提取表格summary
            if "表格" in file_content and file_content["表格"]:
                summary += "表格: \n"
                tables = file_content["表格"]
                for table_name in tables:
                    if isinstance(tables[table_name], dict) and "summary" in tables[table_name]:
                        summary += f"  {tables[table_name]['summary']}\n"
                    else:
                        summary += f"  {table_name}: [无摘要信息]\n"
            
            # 提取文档summary
            if "文档" in file_content and file_content["文档"]:
                summary += "\n文档: \n"
                documents = file_content["文档"]
                for doc_name in documents:
                    if isinstance(documents[doc_name], dict) and "summary" in documents[doc_name]:
                        summary += f"  {documents[doc_name]['summary']}\n"
                    else:
                        summary += f"  {doc_name}: [无摘要信息]\n"
            
            return summary