#!/usr/bin/env python3
"""
Test script to verify HTML generation for the new table structure format.
"""

import sys
from pathlib import Path
import json

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from utils.html_generator import generate_header_html

def test_table_structure():
    """Test the table structure provided by the user"""
    
    test_structure = {
        "表格标题": "七田村低保补贴汇总表(城保+农保)",
        "表格结构": {
            "序号": [],
            "户主姓名": [],
            "低保证号": [],
            "身份证号码": [],
            "居民类型": [],
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
            "领款人签字(章)": [],
            "领款时间": []
        }
    }
    
    print("测试表格结构HTML生成")
    print("=" * 60)
    print("输入结构:", json.dumps(test_structure, ensure_ascii=False, indent=2))
    print("=" * 60)
    
    result_html = generate_header_html(test_structure)
    
    print("生成的HTML:")
    print("-" * 40)
    print(result_html)
    print("-" * 40)
    
    # Save the result to a file for inspection
    output_file = Path("test_output.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(result_html)
    
    print("HTML已保存到:", output_file)
    print("请检查HTML文件确认表格结构是否正确")

if __name__ == "__main__":
    test_table_structure()