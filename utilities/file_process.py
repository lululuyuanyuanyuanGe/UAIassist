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
    


def retrieve_file_content(file_paths: list[str], session_id: str) -> list[str]:
    """This function will retrieve the content of the file and store them in the conversation folder
    and with the subfolder be the session_id, then it should be stored inside another subfolder named
    user_uploaded_files, it shuld be able to handle various different files types, but the strategy are
    very similar, if the file type is a spreadsheet, then use the conver_excel2html function and store the result
    in the corresponding txt file, the name should be the same as the file name which is revealed in the
    file path, secondly if the file will contain plain text, then simply copy the text and stored in the corresponding
    txt file, finally if the file is an image then simply just store it as the image file in the right place"""
    
    import shutil
    from pathlib import Path
    
    # Create the conversation folder structure
    project_root = Path.cwd()  # Use current directory instead of parent
    conversation_dir = project_root / "conversations" / session_id / "user_uploaded_files"
    conversation_dir.mkdir(parents=True, exist_ok=True)
    
    processed_files = []
    
    for file_path in file_paths:
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                print(f"❌ File not found: {file_path}")
                continue
                
            print(f"🔄 Processing file: {source_path.name}")
            
            # Use the new efficient processing function
            processed_content = process_file_to_text(source_path)
            
            if processed_content is not None:
                # Write the processed content to final destination file
                txt_file_path = conversation_dir / f"{source_path.stem}.txt"
                txt_file_path.write_text(processed_content, encoding='utf-8')
                processed_files.append(str(txt_file_path))
                print(f"✅ File processed and saved: {txt_file_path}")
            else:
                # Fallback: copy original file if processing failed
                destination = conversation_dir / source_path.name
                shutil.copy2(source_path, destination)
                processed_files.append(str(destination))
                print(f"⚠️ File copied as-is (processing failed): {destination}")
                
        except Exception as e:
            print(f"❌ Unexpected error processing {file_path}: {e}")
            continue
    
    print(f"🎉 Successfully processed {len(processed_files)} out of {len(file_paths)} files")
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
    """Process document file in memory using LibreOffice"""
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


def fetch_related_files_content(related_files: List[str], base_path: str = "D:/asianInfo/ExcelAssist/conversations/files/user_uploaded_files") -> Dict[str, str]:
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
    """Simple Excel to CSV conversion using pandas"""
    # Read Excel file
    df = pd.read_excel(excel_file, sheet_name=sheet_name)
    
    # Convert to CSV
    df.to_csv(csv_file, index=False, encoding='utf-8')


def process_excel_files_with_chunking(excel_file_paths: list[str], supplement_files_summary: str = "", data_json_path: str = "agents/data.json") -> list[str]:
    """
    Process Excel files by finding the one with most rows, converting to CSV,
    adding detailed structure information, chunking the largest file, and combining everything.
    
    Args:
        excel_file_paths: List of Excel file paths
        supplement_files_summary: String containing supplement file content (not a list)
        data_json_path: Path to data.json file containing structure information
    
    Returns:
        List of 5 strings, each containing combined content of one chunk with other files
    """
    print(f"🔄 Processing {len(excel_file_paths)} Excel files...")
    if supplement_files_summary:
        print(f"📄 Also processing supplement files content")
    
    # Step 1: Count data rows in each Excel file to find the largest
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
    
    # Step 2: Load structure information from data.json
    try:
        with open(data_json_path, 'r', encoding='utf-8') as f:
            data_json = json.load(f)
        table_structure_info = data_json.get("表格", {})
        print(f"📋 Loaded structure info: {len(table_structure_info)} tables")
    except Exception as e:
        print(f"❌ Error loading data.json: {e}")
        table_structure_info = {}
    
    # Step 3: Convert all Excel files to CSV and add detailed structure info
    file_contents = {}  # {file_path: content}
    
    for file_path in excel_file_paths:
        try:
            # Create CSV file path
            csv_folder = Path(r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_csv")
            csv_folder.mkdir(parents=True, exist_ok=True)
            csv_file_path = csv_folder / f"{Path(file_path).stem}.csv"
            
            # Convert Excel to CSV using the simple function
            # ========函数当前存在问题，没有处理好日期，并且保留了一级表头
            excel_to_csv(file_path, str(csv_file_path))
            
            # Read CSV content
            with open(csv_file_path, 'r', encoding='utf-8') as f:
                csv_content = f.read()
            
            # Get detailed structure information from table section
            file_name = Path(file_path).stem + ".txt"
            structure_info = ""
            
            if file_name in table_structure_info:
                file_structure = table_structure_info[file_name]
                
                # Try to parse the JSON structure from the summary field
                try:
                    summary_content = file_structure.get("summary", "")
                    if summary_content:
                        # Clean up the summary content and try to parse as JSON
                        summary_content = summary_content.strip()
                        
                        # Sometimes the JSON is wrapped in text, try to extract it
                        if summary_content.startswith('{') and summary_content.endswith('}'):
                            parsed_summary = json.loads(summary_content)
                            
                            # Check if it's the expected format
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
                            # If not proper JSON format, use the raw summary
                            structure_info += "=== 文件分析 ===\n"
                            structure_info += summary_content + "\n\n"
                            
                except json.JSONDecodeError:
                    # If JSON parsing fails, use the raw summary
                    structure_info += "=== 文件分析 ===\n"
                    structure_info += file_structure.get("summary", "") + "\n\n"
                
                # Also include the full summary if available and different from structured data
                if "summary" in file_structure and not structure_info:
                    structure_info += "=== 完整分析 ===\n"
                    structure_info += file_structure["summary"] + "\n\n"
            
            # Combine structure + CSV content
            combined_content = f"=== {Path(file_path).name} 的表格结构 ===\n{structure_info}\n=== {Path(file_path).name} 的表格数据 ===\n{csv_content}"
            
            file_contents[file_path] = combined_content
            print(f"✅ Processed Excel: {Path(file_path).name}")
            
        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")
            file_contents[file_path] = f"Error processing file: {e}"
    
    # Step 4: Handle the largest file - divide into 5 chunks
    largest_file_content = file_contents[largest_file]
    other_files_content = [content for path, content in file_contents.items() if path != largest_file]
    
    # Split the largest file content into structure and data parts
    largest_file_lines = largest_file_content.split('\n')
    data_section_start = -1
    
    # Look for the correct pattern: "=== filename 的表格数据 ==="
    largest_filename = Path(largest_file).name
    data_header_pattern = f"=== {largest_filename} 的表格数据 ==="
    
    for i, line in enumerate(largest_file_lines):
        if line.strip() == data_header_pattern:
            data_section_start = i
            break
    
    if data_section_start == -1:
        print(f"⚠️ Could not find data section separator '{data_header_pattern}', using full content")
        largest_structure = ""
        largest_data_lines = largest_file_lines
    else:
        # Structure is everything before the data header
        largest_structure = '\n'.join(largest_file_lines[:data_section_start])
        # Data is everything after the data header (excluding the header itself)
        largest_data_lines = largest_file_lines[data_section_start + 1:]
    
    # Remove empty lines at the beginning of data
    while largest_data_lines and not largest_data_lines[0].strip():
        largest_data_lines.pop(0)
    
    # Calculate chunk size (equal number of rows)
    chunk_size = max(1, len(largest_data_lines) // 5)
    print(f"📏 Dividing {len(largest_data_lines)} data lines into chunks of ~{chunk_size} lines each")
    
    # Step 5: Separate structure and data from other files
    other_files_structure = []
    other_files_data = []
    
    for other_content in other_files_content:
        lines = other_content.split('\n')
        other_filename = None
        
        # Find the filename from the structure header
        for line in lines:
            if line.startswith("=== ") and " 的表格结构 ===" in line:
                other_filename = line.replace("=== ", "").replace(" 的表格结构 ===", "")
                break
        
        if other_filename:
            other_data_header = f"=== {other_filename} 的表格数据 ==="
            other_data_start = -1
            
            for i, line in enumerate(lines):
                if line.strip() == other_data_header:
                    other_data_start = i
                    break
            
            if other_data_start != -1:
                structure_part = '\n'.join(lines[:other_data_start])
                data_part = '\n'.join(lines[other_data_start:])
                other_files_structure.append(structure_part)
                other_files_data.append(data_part)
            else:
                # If no data section found, treat as structure only
                other_files_structure.append(other_content)
        else:
            # If no filename found, treat as structure
            other_files_structure.append(other_content)
    
    # Step 6: Create 5 chunks with proper order
    combined_chunks = []
    
    for chunk_index in range(5):
        start_idx = chunk_index * chunk_size
        if chunk_index == 4:  # Last chunk gets remaining lines
            end_idx = len(largest_data_lines)
        else:
            end_idx = start_idx + chunk_size
        
        chunk_data_lines = largest_data_lines[start_idx:end_idx]
        
        # Create chunk following the required order:
        # 1. All structure information first
        # 2. All data information second  
        # 3. Supplement information last
        
        chunk_combined = []
        
        # 1. Add all structure information first
        for structure_content in other_files_structure:
            if structure_content.strip():
                chunk_combined.append(structure_content)
        
        # Add largest file structure
        if largest_structure.strip():
            chunk_combined.append(largest_structure)
        
        # 2. Add all data information second
        for data_content in other_files_data:
            if data_content.strip():
                chunk_combined.append(data_content)
        
        # Add largest file data chunk
        if chunk_data_lines:
            chunk_combined.append(f"=== {largest_filename} 的表格数据 ===\n" + '\n'.join(chunk_data_lines))
        
        # 3. Add supplement information last
        if supplement_files_summary:
            # Check if supplement content already has header
            if supplement_files_summary.strip().startswith("=== 补充文件内容 ==="):
                chunk_combined.append(supplement_files_summary)
            else:
                chunk_combined.append(f"=== 补充文件内容 ===\n{supplement_files_summary}")
        
        # Join all parts with clean separators
        final_combined = "\n\n".join(chunk_combined)
        combined_chunks.append(final_combined)
        
        print(f"✅ Created chunk {chunk_index + 1}/5 with {len(chunk_data_lines)} data lines")
    
    print(f"🎉 Successfully created {len(combined_chunks)} combined chunks")
    return combined_chunks



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


def save_csv_to_output(csv_data_list: list[str], filename_prefix: str = "generated_table") -> str:
    """
    Save CSV data to agents/output folder
    
    Args:
        csv_data_list: List of CSV strings from concurrent processing
        filename_prefix: Prefix for the output filename
    
    Returns:
        str: Full path to the saved CSV file
    """
    import os
    from datetime import datetime
    from pathlib import Path
    
    # Create output directory
    current_dir = Path(__file__).parent
    output_dir = current_dir.parent / "agents" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    actual_filename = "synthesized_table"
    filename = f"{actual_filename}.csv"
    filepath = output_dir / filename
    
    # Combine all CSV data
    combined_csv = '\n'.join(csv_data_list)
    
    # Write to file
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        f.write(combined_csv)
    
    print(f"💾 CSV数据已保存到: {filepath}")
    return str(filepath)
