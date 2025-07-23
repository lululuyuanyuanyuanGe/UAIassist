#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

# Safe print function that handles encoding issues
def safe_print(*args, **kwargs):
    """Print function that handles Unicode encoding issues on Windows"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Convert all args to ASCII-safe versions
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                # Replace problematic characters with safe alternatives
                safe_arg = arg.encode('ascii', errors='replace').decode('ascii')
                safe_args.append(safe_arg)
            else:
                safe_args.append(str(arg))
        print(*safe_args, **kwargs)

from utils.html_generator import generate_header_html

def debug_html_structure():
    """Debug the HTML structure generation with a simple example"""
    
    # Simple test structure with one parent field that has a value
    test_structure = {
        "表格标题": "测试表格",
        "表格结构": {
            "序号": [],
            "姓名": [],
            "领取金额": {
                "值": ["推理规则: 家庭补差 + 重点救助的总计"],
                "分解": {
                    "家庭补差": [],
                    "重点救助": []
                },
                "规则": "家庭补差 + 重点救助"
            },
            "备注": []
        }
    }
    
    safe_print("=== Debugging HTML Structure Generation ===")
    safe_print(f"Test structure: {test_structure}")
    safe_print("")
    
    try:
        # Generate HTML
        html_result = generate_header_html(test_structure)
        
        safe_print("=== Generated HTML ===")
        safe_print(html_result)
        safe_print("")
        
        # Save debug result
        output_path = Path("debug_html_output.html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_result)
        
        safe_print(f"Debug output saved to: {output_path}")
        
        # Analysis
        safe_print("=== Analysis ===")
        safe_print("Expected structure:")
        safe_print("Level 1: 序号 | 姓名 | 领取金额 (colspan=3) | 备注")
        safe_print("Level 2: 序号 | 姓名 | 领取金额(value) | 家庭补差 | 重点救助 | 备注")
        safe_print("")
        safe_print("The '领取金额' parent should have its own data cell PLUS the child cells")
        
        return True
        
    except Exception as e:
        safe_print(f"HTML Generation Failed: {e}")
        import traceback
        safe_print(f"Error Details:\n{traceback.format_exc()}")
        return False

if __name__ == "__main__":
    debug_html_structure()