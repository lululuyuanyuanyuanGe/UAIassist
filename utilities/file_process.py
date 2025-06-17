from __future__ import annotations
from bs4 import BeautifulSoup
from pathlib import Path
import re
import os
from pathlib import Path
import subprocess
import chardet


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

def retrieve_file_content(file_paths: list[str], session_id: str) -> list[str]:
    """This function will retrieve the content of the file and store them in the conversation folder
    and with the subfolder be the session_id, then it should be stored inside another subfolder named
    user_uploaded_files, it shuld be able to handle various different files types, but the strategy are
    very similar, if the file type is a spreadsheet, then use the conver_excel2html function and store the result
    in the corresponding txt file, the name should be the same as the file name which is revealed in the
    file path, secondly if the file will contain plain text, then simply copy the text and stored in the corresponding
    txt file, finally if the file is an image then simply just store it as the image file in the right place"""
    
    import shutil
    import mimetypes
    from pathlib import Path
    
    # Create the conversation folder structure
    project_root = Path.cwd().parent
    conversation_dir = project_root / "conversations" / session_id / "user_uploaded_files"
    conversation_dir.mkdir(parents=True, exist_ok=True)
    
    processed_files = []
    
    # Define file type categories
    spreadsheet_extensions = {'.xlsx', '.xls', '.xlsm', '.ods', '.csv'}
    text_extensions = {'.txt', '.md', '.json', '.xml', '.html', '.htm', '.py', '.js', '.css', '.sql', '.log'}
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg'}
    
    for file_path in file_paths:
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                print(f"❌ File not found: {file_path}")
                continue
                
            file_extension = source_path.suffix.lower()
            file_stem = source_path.stem
            
            print(f"🔄 Processing file: {source_path.name}")
            
            # Handle spreadsheet files
            if file_extension in spreadsheet_extensions:
                try:
                    # Use convert_excel2html function to convert spreadsheet
                    html_output_path = convert_excel2html(source_path, conversation_dir)
                    
                    # Read the HTML content and save as txt file
                    html_content = html_output_path.read_text(encoding='utf-8')
                    txt_file_path = conversation_dir / f"{file_stem}.txt"
                    txt_file_path.write_text(html_content, encoding='utf-8')
                    
                    processed_files.append(str(txt_file_path))
                    print(f"✅ Spreadsheet converted and saved: {txt_file_path}")
                    
                except Exception as e:
                    print(f"❌ Error processing spreadsheet {file_path}: {e}")
                    # Fallback: copy original file
                    destination = conversation_dir / source_path.name
                    shutil.copy2(source_path, destination)
                    processed_files.append(str(destination))
                    
            # Handle plain text files
            elif file_extension in text_extensions:
                try:
                    # Read text content (with encoding detection)
                    text_content = _read_text_auto(source_path)
                    
                    # Save as txt file with same stem name
                    txt_file_path = conversation_dir / f"{file_stem}.txt"
                    txt_file_path.write_text(text_content, encoding='utf-8')
                    
                    processed_files.append(str(txt_file_path))
                    print(f"✅ Text file processed and saved: {txt_file_path}")
                    
                except Exception as e:
                    print(f"❌ Error processing text file {file_path}: {e}")
                    # Fallback: copy original file
                    destination = conversation_dir / source_path.name
                    shutil.copy2(source_path, destination)
                    processed_files.append(str(destination))
                    
            # Handle image files
            elif file_extension in image_extensions:
                try:
                    # Simply copy image file to destination
                    destination = conversation_dir / source_path.name
                    shutil.copy2(source_path, destination)
                    
                    processed_files.append(str(destination))
                    print(f"✅ Image file copied: {destination}")
                    
                except Exception as e:
                    print(f"❌ Error copying image file {file_path}: {e}")
                    
            # Handle other file types
            else:
                # Try to detect if it's a text file by MIME type
                mime_type, _ = mimetypes.guess_type(str(source_path))
                
                if mime_type and mime_type.startswith('text/'):
                    try:
                        # Treat as text file
                        text_content = _read_text_auto(source_path)
                        txt_file_path = conversation_dir / f"{file_stem}.txt"
                        txt_file_path.write_text(text_content, encoding='utf-8')
                        
                        processed_files.append(str(txt_file_path))
                        print(f"✅ Unknown text file processed: {txt_file_path}")
                        
                    except Exception as e:
                        print(f"❌ Error processing unknown text file {file_path}: {e}")
                        # Fallback: copy original file
                        destination = conversation_dir / source_path.name
                        shutil.copy2(source_path, destination)
                        processed_files.append(str(destination))
                else:
                    # For binary files or unknown types, just copy them
                    try:
                        destination = conversation_dir / source_path.name
                        shutil.copy2(source_path, destination)
                        
                        processed_files.append(str(destination))
                        print(f"✅ Binary/unknown file copied: {destination}")
                        
                    except Exception as e:
                        print(f"❌ Error copying file {file_path}: {e}")
                        
        except Exception as e:
            print(f"❌ Unexpected error processing {file_path}: {e}")
            continue
    
    print(f"🎉 Successfully processed {len(processed_files)} out of {len(file_paths)} files")
    return processed_files

def convert_excel2html(input_path: str | Path, output_dir: str | Path) -> Path:
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


