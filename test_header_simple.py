#!/usr/bin/env python3

import sys
import json
from pathlib import Path

# Set console encoding for Windows
if sys.platform == 'win32':
    import subprocess
    subprocess.run(['chcp', '65001'], shell=True, capture_output=True)

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from utils.html_generator import generate_header_html

def test_complex_structure():
    """Test with complex nested fields"""
    print("Testing complex table structure...")
    
    test_data = {
        "表格标题": "七田村2024年低保补贴汇总表",
        "表格结构": {
            "序号": [],
            "户主姓名": [],
            "身份证号码": [],
            "低保证号": [],
            "保障人数": {
                "值": [],
                "分解": {
                    "重点保障人数": [],
                    "残疾人数": []
                },
                "规则": "重点保障人数 + 残疾人数"
            },
            "领取金额": {
                "值": [],
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
    
    html_result = generate_header_html(test_data)
    print(f"Complex structure test completed, HTML length: {len(html_result)}")
    
    # Save result to file
    with open('test_output_complex.html', 'w', encoding='utf-8') as f:
        f.write(html_result)
    print("HTML saved to test_output_complex.html")
    
    return html_result

if __name__ == "__main__":
    print("Starting generate_header_html function test...")
    print("=" * 50)
    
    try:
        test_complex_structure()
        print("Test completed successfully!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")