from __future__ import annotations
from bs4 import BeautifulSoup
from pathlib import Path
import re
import os
from pathlib import Path
import subprocess
import chardet
from typing import Union

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