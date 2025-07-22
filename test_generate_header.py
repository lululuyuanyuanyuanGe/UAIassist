#!/usr/bin/env python3
"""
Test script for the modified generate_header_html function
"""

import sys
import json
import os
from pathlib import Path

# Set console encoding for Windows
if sys.platform == 'win32':
    import subprocess
    subprocess.run(['chcp', '65001'], shell=True, capture_output=True)

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from utils.html_generator import generate_header_html

def test_simple_structure():
    """Test with simple fields only"""
    print("🧪 测试简单表格结构...")
    
    test_data = {
        "表格标题": "燕云村党员信息表",
        "表格结构": {
            "序号": [],
            "姓名": [],
            "身份证号": [],
            "电话": []
        }
    }
    
    html_result = generate_header_html(test_data)
    print(f"✅ 简单结构测试完成，HTML长度: {len(html_result)}")
    print("生成的HTML:", html_result[:200], "...")
    return html_result

def test_complex_structure():
    """Test with complex nested fields"""
    print("\n🧪 测试复杂表格结构...")
    
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
    print(f"✅ 复杂结构测试完成，HTML长度: {len(html_result)}")
    print("生成的HTML:", html_result[:500], "...")
    return html_result

def test_mixed_structure():
    """Test with mixed simple and complex fields"""
    print("\n🧪 测试混合表格结构...")
    
    test_data = {
        "表格标题": "燕云村综合信息统计表",
        "表格结构": {
            "序号": [],
            "基本信息": {
                "值": [],
                "分解": {
                    "姓名": [],
                    "性别": [],
                    "年龄": []
                },
                "规则": ""
            },
            "联系方式": [],
            "补贴情况": {
                "值": [],
                "分解": {
                    "低保补贴": [],
                    "残疾人补贴": []
                },
                "规则": "低保补贴 + 残疾人补贴"
            },
            "备注": []
        }
    }
    
    html_result = generate_header_html(test_data)
    print(f"✅ 混合结构测试完成，HTML长度: {len(html_result)}")
    print("生成的HTML:", html_result[:500], "...")
    return html_result

def save_test_results():
    """Save test results to HTML files"""
    print("\n💾 保存测试结果...")
    
    results = {
        "simple": test_simple_structure(),
        "complex": test_complex_structure(), 
        "mixed": test_mixed_structure()
    }
    
    for test_name, html_content in results.items():
        output_path = f"test_output_{test_name}.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"📝 {test_name}测试结果已保存到: {output_path}")

if __name__ == "__main__":
    print("🚀 开始测试 generate_header_html 函数...")
    print("=" * 60)
    
    try:
        save_test_results()
        print("\n✅ 所有测试完成！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        print(f"错误详情: {traceback.format_exc()}")