import json
import csv
import os
from bs4 import BeautifulSoup
from pathlib import Path

# Add root project directory to sys.path if needed
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from utilities.file_process import read_txt_file


def generate_header_html(json_data: dict) -> str:
    """
    Generate HTML table structure from JSON data.
    
    Args:
        json_data: Dictionary containing 表格标题 and 表格结构
        
    Returns:
        str: HTML table code
    """
    try:
        # Parse JSON if it's a string
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data
        
        table_title = data.get("表格标题", "表格")
        table_structure = data.get("表格结构", {})
        
        # Count total columns
        total_columns = 0
        is_multilevel = False
        
        # Check if structure is multilevel (nested dict) or single level (list)
        for key, value in table_structure.items():
            if isinstance(value, dict):
                is_multilevel = True
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, list):
                        total_columns += len(subvalue)
            elif isinstance(value, list):
                total_columns += len(value)
        
        # Generate colgroup
        colgroup_html = "\n".join([f"<colgroup></colgroup>" for _ in range(total_columns)])
        
        # Generate HTML
        html_lines = [
            "<html><body><table>",
            colgroup_html,
            # Title row
            f'<tr>\n<td colspan="{total_columns}"><b>{table_title}</b></td>\n</tr>'
        ]
        
        if is_multilevel:
            # Generate multilevel structure
            # Second row: main categories
            main_categories_row = ["<tr>"]
            # Third row: subcategories  
            sub_categories_row = ["<tr>"]
            # Fourth row: fields
            fields_row = ["<tr>"]
            
            for main_cat, sub_cats in table_structure.items():
                if isinstance(sub_cats, dict):
                    # Count total fields under this main category
                    main_cat_span = sum(len(fields) for fields in sub_cats.values() if isinstance(fields, list))
                    main_categories_row.append(f'<td colspan="{main_cat_span}"><b>{main_cat}</b></td>')
                    
                    # Add subcategories and fields
                    for sub_cat, fields in sub_cats.items():
                        if isinstance(fields, list):
                            sub_categories_row.append(f'<td colspan="{len(fields)}"><b>{sub_cat}</b></td>')
                            for field in fields:
                                fields_row.append(f'<td><b>{field}</b></td>')
            
            main_categories_row.append("</tr>")
            sub_categories_row.append("</tr>")
            fields_row.append("</tr>")
            
            html_lines.extend([
                "\n".join(main_categories_row),
                "\n".join(sub_categories_row), 
                "\n".join(fields_row)
            ])
        
        else:
            # Generate single level structure
            # Second row: categories
            categories_row = ["<tr>"]
            # Third row: fields
            fields_row = ["<tr>"]
            
            for category, fields in table_structure.items():
                if isinstance(fields, list):
                    categories_row.append(f'<td colspan="{len(fields)}"><b>{category}</b></td>')
                    for field in fields:
                        fields_row.append(f'<td><b>{field}</b></td>')
            
            categories_row.append("</tr>")
            fields_row.append("</tr>")
            
            html_lines.extend([
                "\n".join(categories_row),
                "\n".join(fields_row)
            ])
        
        html_lines.append("</table></body></html>")
        
        return "\n".join(html_lines)
        
    except Exception as e:
        print(f"❌ HTML生成错误: {e}")
        # Fallback simple structure
        return f"<html><body><table><tr><td><b>表格生成错误</b></td></tr></table></body></html>"


def extract_empty_row_html_code_based(template_file_path: str) -> str:
    """
    Extract empty row HTML template from template file using code-based approach.
    
    Args:
        template_file_path: Path to HTML template file
        
    Returns:
        str: HTML code for empty row template
    """
    print("\n🔄 开始执行: extract_empty_row_html_code_based")
    print("=" * 50)
    
    try:
        template_file_content = read_txt_file(template_file_path)
        print(f"📄 读取模板文件: {template_file_path}")
        
        # Parse HTML content
        soup = BeautifulSoup(template_file_content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            print("❌ 未找到table元素")
            return ""
        
        # Find all rows
        rows = table.find_all('tr')
        print(f"📋 找到 {len(rows)} 行")
        
        # Look for empty row (contains <br/> or is mostly empty)
        empty_row = None
        for row in rows:
            cells = row.find_all('td')
            if cells and len(cells) > 1:  # Skip single-cell title rows
                # Check if this row has empty cells or <br/> tags
                empty_cell_count = 0
                for cell in cells:
                    if cell.find('br') or cell.get_text().strip() == '':
                        empty_cell_count += 1
                
                # If most cells are empty, this is likely our empty row template
                if empty_cell_count >= len(cells) - 1:  # Allow one cell to have content (like sequence number)
                    empty_row = row
                    break
        
        if empty_row:
            # Clean up the empty row - ensure all cells except first are empty
            cells = empty_row.find_all('td')
            for i, cell in enumerate(cells):
                if i == 0:
                    # First cell might have sequence number, make it empty
                    cell.clear()
                    cell.string = ""
                else:
                    # Other cells should be empty with <br/>
                    cell.clear()
                    cell.append(soup.new_tag('br'))
            
            empty_row_html = str(empty_row)
            print(f"✅ 找到空行模板: {empty_row_html}")
            print("✅ extract_empty_row_html_code_based 执行完成")
            print("=" * 50)
            return empty_row_html
        else:
            # If no empty row found, create one based on the table structure
            print("⚠️ 未找到空行，基于表头创建空行")
            header_row = None
            for row in rows:
                cells = row.find_all('td')
                if cells and len(cells) > 1 and not any(cell.get('colspan') for cell in cells):
                    header_row = row
                    break
            
            if header_row:
                # Create empty row based on header structure
                new_row = soup.new_tag('tr')
                header_cells = header_row.find_all('td')
                for i in range(len(header_cells)):
                    new_cell = soup.new_tag('td')
                    if i == 0:
                        new_cell.string = ""
                    else:
                        new_cell.append(soup.new_tag('br'))
                    new_row.append(new_cell)
                
                empty_row_html = str(new_row)
                print(f"✅ 创建空行模板: {empty_row_html}")
                print("✅ extract_empty_row_html_code_based 执行完成")
                print("=" * 50)
                return empty_row_html
            else:
                print("❌ 无法创建空行模板")
                return ""
    
    except Exception as e:
        print(f"❌ extract_empty_row_html_code_based 执行失败: {e}")
        import traceback
        print(f"错误详情: {traceback.format_exc()}")
        return ""


def extract_headers_html_code_based(template_file_path: str) -> str:
    """
    Extract headers HTML from template file using code-based approach.
    
    Args:
        template_file_path: Path to HTML template file
        
    Returns:
        str: HTML code for headers section
    """
    print("\n🔄 开始执行: extract_headers_html_code_based")
    print("=" * 50)
    
    try:
        template_file_content = read_txt_file(template_file_path)
        print(f"📄 读取模板文件: {template_file_path}")
        
        # Parse HTML content
        soup = BeautifulSoup(template_file_content, 'html.parser')
        
        # Find the table
        table = soup.find('table')
        if not table:
            print("❌ 未找到table元素")
            return ""
        
        # Get all rows
        rows = table.find_all('tr')
        print(f"📋 找到 {len(rows)} 行")
        
        # Find the first empty row (data row)
        first_empty_row_index = None
        for i, row in enumerate(rows):
            cells = row.find_all('td')
            if cells and len(cells) > 1:
                # Check if this row has empty cells or <br/> tags
                empty_cell_count = 0
                for cell in cells:
                    if cell.find('br') or cell.get_text().strip() == '':
                        empty_cell_count += 1
                
                # If most cells are empty, this is likely our first data row
                if empty_cell_count >= len(cells) - 1:
                    first_empty_row_index = i
                    break
        
        if first_empty_row_index is None:
            print("⚠️ 未找到空行，使用所有行作为表头")
            first_empty_row_index = len(rows)
        
        # Build header HTML
        header_parts = []
        header_parts.append("<html><body><table>")
        
        # Add colgroup if present
        colgroups = soup.find_all('colgroup')
        for colgroup in colgroups:
            header_parts.append(str(colgroup))
        
        # Add all rows before the first empty row
        for i in range(first_empty_row_index):
            header_parts.append(str(rows[i]))
        
        headers_html = '\n'.join(header_parts)
        print(f"✅ 提取表头HTML (包含 {first_empty_row_index} 行)")
        print("✅ extract_headers_html_code_based 执行完成")
        print("=" * 50)
        return headers_html
        
    except Exception as e:
        print(f"❌ extract_headers_html_code_based 执行失败: {e}")
        import traceback
        print(f"错误详情: {traceback.format_exc()}")
        return ""


def extract_footer_html_code_based(template_file_path: str) -> str:
    """
    Extract footer HTML from template file using code-based approach.
    
    Args:
        template_file_path: Path to HTML template file
        
    Returns:
        str: HTML code for footer section
    """
    print("\n🔄 开始执行: extract_footer_html_code_based")
    print("=" * 50)
    
    try:
        template_file_content = read_txt_file(template_file_path)
        print(f"📄 读取模板文件: {template_file_path}")
        
        # Parse HTML content
        soup = BeautifulSoup(template_file_content, 'html.parser')
        
        # Find the table
        table = soup.find('table')
        if not table:
            print("❌ 未找到table元素")
            return ""
        
        # Get all rows
        rows = table.find_all('tr')
        print(f"📋 找到 {len(rows)} 行")
        
        # Find the last empty row (data row)
        last_empty_row_index = None
        for i in range(len(rows) - 1, -1, -1):
            row = rows[i]
            cells = row.find_all('td')
            if cells and len(cells) > 1:
                # Check if this row has empty cells or <br/> tags
                empty_cell_count = 0
                for cell in cells:
                    if cell.find('br') or cell.get_text().strip() == '':
                        empty_cell_count += 1
                
                # If most cells are empty, this is likely our last data row
                if empty_cell_count >= len(cells) - 1:
                    last_empty_row_index = i
                    break
        
        if last_empty_row_index is None:
            print("⚠️ 未找到空行，无页脚")
            return "</table></body></html>"
        
        # Build footer HTML
        footer_parts = []
        
        # Add all rows after the last empty row
        for i in range(last_empty_row_index + 1, len(rows)):
            footer_parts.append(str(rows[i]))
        
        # Close the HTML structure
        footer_parts.append("</table></body></html>")
        
        footer_html = '\n'.join(footer_parts)
        print(f"✅ 提取页脚HTML (包含 {len(rows) - last_empty_row_index - 1} 行)")
        print("✅ extract_footer_html_code_based 执行完成")
        print("=" * 50)
        return footer_html
        
    except Exception as e:
        print(f"❌ extract_footer_html_code_based 执行失败: {e}")
        import traceback
        print(f"错误详情: {traceback.format_exc()}")
        return ""


def is_valid_csv_row(row_text: str) -> bool:
    """
    Check if a row contains valid CSV data.
    
    Args:
        row_text: The text row to check
        
    Returns:
        bool: True if row appears to be valid CSV data
    """
    if not row_text or not row_text.strip():
        return False
    
    # Skip obvious non-CSV content
    non_csv_indicators = [
        '===', '---', '***', '+++', '###',  # Separator lines
        '推理过程', '最终答案', '分析', '结论',  # Analysis text
        'Error', 'Exception', 'Traceback',  # Error messages
        '步骤', '过程', '思考', '判断',  # Process text
        '根据', '因为', '所以', '由于',  # Logic text
    ]
    
    for indicator in non_csv_indicators:
        if indicator in row_text:
            return False
    
    # Check if it looks like CSV (has commas and reasonable structure)
    try:
        # Try to parse as CSV
        csv_reader = csv.reader([row_text])
        fields = next(csv_reader)
        
        # Should have multiple fields
        if len(fields) < 2:
            return False
        
        # Fields shouldn't be too long (likely prose text)
        for field in fields:
            if len(field.strip()) > 200:  # Reasonable field length limit
                return False
        
        return True
        
    except:
        return False


def parse_csv_row_safely(row_text: str) -> list:
    """
    Safely parse a CSV row, handling various edge cases.
    
    Args:
        row_text: The CSV row text to parse
        
    Returns:
        list: List of field values, or empty list if parsing fails
    """
    try:
        # First try proper CSV parsing
        csv_reader = csv.reader([row_text])
        fields = next(csv_reader)
        
        # Strip whitespace from each field
        fields = [field.strip() for field in fields]
        
        return fields
        
    except:
        # Fallback to simple comma split
        try:
            fields = row_text.split(',')
            fields = [field.strip() for field in fields]
            return fields
        except:
            return []


def transform_data_to_html_code_based(csv_file_path: str, empty_row_html: str, session_id: str) -> str:
    """
    Transform CSV data to HTML using code-based approach with robust error handling.
    
    Args:
        csv_file_path: Path to CSV file
        empty_row_html: HTML template for empty row
        session_id: Session ID for logging
        
    Returns:
        str: Generated HTML rows
    """
    print("\n🔄 开始执行: transform_data_to_html_code_based")
    print("=" * 50)
    
    try:
        # Check if CSV file exists
        if not os.path.exists(csv_file_path):
            print(f"❌ CSV文件不存在: {csv_file_path}")
            return ""
        
        # Read CSV data
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            csv_lines = file.read().strip().split('\n')
        
        print(f"📊 读取到 {len(csv_lines)} 行原始数据")
        
        # Parse the empty row HTML template
        soup = BeautifulSoup(empty_row_html, 'html.parser')
        template_row = soup.find('tr')
        
        if not template_row:
            print("❌ 无法在模板中找到<tr>元素")
            return ""
        
        # Get all td elements in the template
        template_cells = template_row.find_all('td')
        expected_columns = len(template_cells)
        print(f"📋 模板列数: {expected_columns}")
        
        filled_rows = []
        valid_row_count = 0
        skipped_row_count = 0
        
        for row_index, csv_line in enumerate(csv_lines):
            # Skip empty lines
            if not csv_line.strip():
                skipped_row_count += 1
                continue
            
            # Check if row is valid CSV
            if not is_valid_csv_row(csv_line):
                print(f"⚠️ 跳过非CSV行 {row_index + 1}: {csv_line[:50]}...")
                skipped_row_count += 1
                continue
            
            # Parse CSV row safely
            row_data = parse_csv_row_safely(csv_line)
            if not row_data:
                print(f"⚠️ 无法解析行 {row_index + 1}: {csv_line[:50]}...")
                skipped_row_count += 1
                continue
            
            valid_row_count += 1
            
            # Create a new row based on the template
            new_row = BeautifulSoup(empty_row_html, 'html.parser').find('tr')
            cells = new_row.find_all('td')
            
            # Fill in the data
            for i, cell in enumerate(cells):
                if i < len(row_data):
                    # Replace <br/> or empty content with actual data
                    if cell.find('br'):
                        cell.clear()
                    cell.string = row_data[i] if row_data[i] else ''
                else:
                    # If we have fewer data fields than template columns, fill with empty
                    if cell.find('br'):
                        cell.clear()
                    cell.string = ''
            
            # No inline styles needed - CSS handles all styling
            filled_rows.append(str(new_row))
            
            # Progress indicator for large datasets
            if valid_row_count % 100 == 0:
                print(f"✅ 已处理 {valid_row_count} 行有效数据")
        
        combined_html = '\n'.join(filled_rows)
        
        print(f"🎉 处理完成:")
        print(f"   - 总行数: {len(csv_lines)}")
        print(f"   - 有效行数: {valid_row_count}")
        print(f"   - 跳过行数: {skipped_row_count}")
        print(f"   - 生成HTML长度: {len(combined_html)} 字符")
        
        # Save a sample to file for debugging
        if session_id:
            sample_output_path = f"conversations/{session_id}/output/sample_filled_rows.html"
            os.makedirs(os.path.dirname(sample_output_path), exist_ok=True)
            with open(sample_output_path, 'w', encoding='utf-8') as f:
                f.write(combined_html[:5000])  # Save first 5000 chars as sample
            print(f"📝 样本HTML已保存到: {sample_output_path}")
        
        print("✅ transform_data_to_html_code_based 执行完成")
        print("=" * 50)
        
        return combined_html
        
    except Exception as e:
        print(f"❌ transform_data_to_html_code_based 执行失败: {e}")
        import traceback
        print(f"错误详情: {traceback.format_exc()}")
        return ""


def combine_html_parts(headers_html: str, data_html: str, footer_html: str) -> str:
    """
    Combine HTML parts with enhanced modern styling.
    
    Args:
        headers_html: HTML for headers
        data_html: HTML for data rows
        footer_html: HTML for footer
        
    Returns:
        str: Complete HTML document
    """
    print("\n🔄 开始执行: combine_html_parts")
    print("=" * 50)
    
    try:
        # Create complete HTML document with professional formal styling
        complete_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>表格报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Microsoft YaHei', 'SimHei', Arial, sans-serif;
            background-color: #f8f9fa;
            padding: 30px 20px;
            color: #333;
            line-height: 1.6;
        }}
        
        .table-container {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            margin: 0 auto;
            width: 100%;
            max-width: none;
            padding: 25px;
            border: 1px solid #e0e0e0;
        }}
        
        .table-wrapper {{
            overflow-x: auto;
            overflow-y: hidden;
            width: 100%;
            border-radius: 4px;
        }}
        
        table {{
            width: 100%;
            min-width: 800px;
            border-collapse: collapse;
            margin: 0;
            background: white;
            font-size: 14px;
        }}
        
        /* 表头样式 - 主标题 */
        table tr:first-child td {{
            background-color: #2c3e50 !important;
            color: white !important;
            font-weight: 600;
            font-size: 16px;
            text-align: center;
            padding: 18px 15px;
            border: 1px solid #2c3e50;
            border-right: 2px solid #1a252f;
        }}
        
        table tr:first-child td:last-child {{
            border-right: 1px solid #2c3e50;
        }}
        
        /* 分类标题行 */
        table tr:nth-child(2) td {{
            background-color: #34495e !important;
            color: white !important;
            font-weight: 600;
            font-size: 14px;
            text-align: center;
            padding: 14px 12px;
            border: 1px solid #34495e;
            border-right: 2px solid #2c3e50;
        }}
        
        table tr:nth-child(2) td:last-child {{
            border-right: 1px solid #34495e;
        }}
        
        /* 字段标题行 */
        table tr:nth-child(3) td {{
            background-color: #ecf0f1 !important;
            color: #2c3e50 !important;
            font-weight: 600;
            font-size: 13px;
            text-align: center;
            padding: 12px 10px;
            border: 1px solid #bdc3c7;
            border-right: 2px solid #95a5a6;
        }}
        
        table tr:nth-child(3) td:last-child {{
            border-right: 1px solid #bdc3c7;
        }}
        
        /* 数据行基础样式 */
        table tr:not(:first-child):not(:nth-child(2)):not(:nth-child(3)):not(:last-child) {{
            background-color: white;
            transition: background-color 0.2s ease;
        }}
        
        /* 交替行颜色 */
        table tr:not(:first-child):not(:nth-child(2)):not(:nth-child(3)):not(:last-child):nth-child(even) {{
            background-color: #f8f9fa;
        }}
        
        /* 数据单元格样式 */
        table tr:not(:first-child):not(:nth-child(2)):not(:nth-child(3)) td {{
            padding: 12px 15px;
            border: 1px solid #dee2e6;
            text-align: center;
            font-size: 13px;
            color: #495057;
            font-weight: 400;
            vertical-align: middle;
        }}
        
        /* 第一列特殊样式 - 序号列 */
        table tr:not(:first-child):not(:nth-child(2)):not(:nth-child(3)) td:first-child {{
            background-color: #f1f3f4;
            font-weight: 500;
            color: #5f6368;
            border-right: 2px solid #dadce0;
        }}
        
        /* 数据行悬停效果 */
        table tr:not(:first-child):not(:nth-child(2)):not(:nth-child(3)):hover {{
            background-color: #e8f4f8 !important;
        }}
        
        table tr:not(:first-child):not(:nth-child(2)):not(:nth-child(3)):hover td {{
            color: #1a73e8;
        }}
        
        /* 页脚样式 */
        table tr:last-child td {{
            background-color: #f8f9fa !important;
            color: #495057 !important;
            font-weight: 500;
            padding: 15px 12px;
            font-size: 12px;
            border-top: 2px solid #dee2e6;
            text-align: center;
        }}
        
        /* 表格外边框 */
        table {{
            border: 2px solid #2c3e50;
        }}
        
        /* 水平滚动条样式 */
        .table-wrapper::-webkit-scrollbar {{
            height: 12px;
        }}
        
        .table-wrapper::-webkit-scrollbar-track {{
            background: #f1f1f1;
            border-radius: 6px;
        }}
        
        .table-wrapper::-webkit-scrollbar-thumb {{
            background: #c1c1c1;
            border-radius: 6px;
            border: 2px solid #f1f1f1;
        }}
        
        .table-wrapper::-webkit-scrollbar-thumb:hover {{
            background: #a8a8a8;
        }}
        
        .table-wrapper::-webkit-scrollbar-corner {{
            background: #f1f1f1;
        }}
        
        /* 响应式设计 */
        @media (max-width: 1200px) {{
            .table-container {{
                padding: 20px;
                margin: 15px;
            }}
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 15px 10px;
            }}
            
            .table-container {{
                padding: 15px;
                margin: 10px;
                border-radius: 6px;
            }}
            
            .table-wrapper {{
                border-radius: 4px;
            }}
            
            table {{
                min-width: 600px;
            }}
            
            table td {{
                padding: 8px 6px;
                font-size: 11px;
            }}
            
            table tr:first-child td {{
                font-size: 14px;
                padding: 15px 10px;
            }}
            
            table tr:nth-child(2) td {{
                font-size: 12px;
                padding: 12px 8px;
            }}
            
            table tr:nth-child(3) td {{
                font-size: 11px;
                padding: 10px 6px;
            }}
        }}
        
        @media (max-width: 480px) {{
            .table-container {{
                padding: 10px;
                margin: 5px;
            }}
            
            table {{
                min-width: 500px;
            }}
            
            table td {{
                padding: 6px 4px;
                font-size: 10px;
            }}
            
            table tr:first-child td {{
                font-size: 12px;
                padding: 12px 8px;
            }}
        }}
        
        /* 打印样式 */
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            
            .table-container {{
                box-shadow: none;
                border: 1px solid #000;
                background: white;
                padding: 0;
                width: 100%;
            }}
            
            .table-wrapper {{
                overflow: visible;
            }}
            
            table {{
                border: 1px solid #000;
                min-width: auto;
                width: 100%;
            }}
            
            table td {{
                border: 1px solid #000;
            }}
            
            table tr:hover {{
                background: white !important;
            }}
        }}
        
        /* 轻微的入场动画 */
        .table-container {{
            animation: fadeIn 0.3s ease-out;
        }}
        
        @keyframes fadeIn {{
            from {{
                opacity: 0;
                transform: translateY(10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
    </style>
</head>
<body>
    <div class="table-container">
        <div class="table-wrapper">
            {headers_html}
            {data_html}
            {footer_html}
        </div>
    </div>
</body>
</html>"""
        
        print(f"✅ 成功合并HTML文档 - 应用正式专业设计")
        print(f"📄 总长度: {len(complete_html)} 字符")
        print("✅ combine_html_parts 执行完成")
        print("=" * 50)
        
        return complete_html
        
    except Exception as e:
        print(f"❌ combine_html_parts 执行失败: {e}")
        import traceback
        print(f"错误详情: {traceback.format_exc()}")
        return ""
