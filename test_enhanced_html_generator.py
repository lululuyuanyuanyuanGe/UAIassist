#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from pathlib import Path
import json

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

def test_enhanced_html_generator():
    """Test the enhanced HTML generator with parent value fields"""
    
    # Test structure similar to the screenshot - "领取金额" with its own value + children
    test_structure = {
        "表格标题": "七田村2024年低保补贴汇总表",
        "表格结构": {
            "序号": [],
            "户主姓名": [],
            "身份证号码": [],
            "低保证号": [],
            "保障人数": {
                "值": ["推理规则: 重点保障人数 + 残疾人数的汇总"],
                "分解": {
                    "重点保障人数": [],
                    "残疾人数": []
                },
                "规则": "重点保障人数 + 残疾人数"
            },
            "领取金额": {
                "值": ["推理规则: 家庭补差 + 重点救助60元 + 重点救助100元 + 残疾人救助的总计"],
                "分解": {
                    "家庭补差": [],
                    "重点救助60元": [],
                    "重点救助100元": [],
                    "残疾人救助": []
                },
                "规则": "家庭补差 + 重点救助60元 + 重点救助100元 + 残疾人救助"
            },
            "领款人签字": [],
            "领款时间": []
        }
    }
    
    safe_print("Testing Enhanced HTML Generator")
    safe_print("=" * 60)
    
    try:
        # Generate HTML
        html_result = generate_header_html(test_structure)
        
        safe_print("HTML Generation Successful!")
        safe_print(f"Generated HTML length: {len(html_result)} characters")
        
        # Save test result
        output_path = Path("test_enhanced_output.html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_result)
        
        safe_print(f"Test output saved to: {output_path}")
        
        # Print first 1000 characters for inspection
        safe_print("\nHTML Preview (first 1000 chars):")
        safe_print("-" * 50)
        safe_print(html_result[:1000])
        if len(html_result) > 1000:
            safe_print("... (truncated)")
        
        # Basic validation checks
        safe_print("\nValidation Checks:")
        checks = [
            ("Contains table tag", "<table>" in html_result),
            ("Contains title row", "七田村2024年低保补贴汇总表" in html_result),
            ("Contains领取金额 parent", "领取金额" in html_result),
            ("Contains家庭补差 child", "家庭补差" in html_result),
            ("Contains proper cell structure", "<td>" in html_result and "</td>" in html_result),
            ("Contains empty data row", "<br/>" in html_result),
        ]
        
        for check_name, check_result in checks:
            status = "PASS" if check_result else "FAIL"
            safe_print(f"   [{status}] {check_name}")
        
        all_passed = all(check[1] for check in checks)
        if all_passed:
            safe_print("\nAll validation checks passed!")
        else:
            safe_print("\nSome validation checks failed!")
        
        return all_passed
        
    except Exception as e:
        safe_print(f"HTML Generation Failed: {e}")
        import traceback
        safe_print(f"Error Details:\n{traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_enhanced_html_generator()
    if success:
        safe_print("\nTest completed successfully!")
    else:
        safe_print("\nTest failed!")
        sys.exit(1)