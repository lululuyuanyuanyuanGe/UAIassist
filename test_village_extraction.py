#!/usr/bin/env python3
"""
测试动态村庄数据提取功能
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

from agents.recallFilesAgent import RecallFilesAgent

def test_village_extraction():
    """测试村庄数据提取功能"""
    print("🧪 测试动态村庄数据提取功能")
    print("=" * 60)
    
    # 创建智能体实例
    agent = RecallFilesAgent()
    
    # 测试不同的模板结构
    test_templates = [
        {
            "name": "燕云村模板",
            "template": '''
            {
                "表格结构": {
                    "重庆市巴南区享受生活补贴老党员登记表": {
                        "基本信息": ["序号", "姓名", "性别", "民族", "身份证号码"]
                    }
                },
                "表格总结": "该表格用于重庆市巴南区燕云村党委登记享受生活补贴的老党员信息"
            }
            '''
        },
        {
            "name": "七田村模板",
            "template": '''
            {
                "表格结构": {
                    "七田村党员登记表": {
                        "基本信息": ["序号", "姓名", "党支部"]
                    }
                },
                "表格总结": "该表格用于七田村党员登记管理"
            }
            '''
        },
        {
            "name": "无明确村庄模板",
            "template": '''
            {
                "表格结构": {
                    "通用登记表": {
                        "基本信息": ["序号", "姓名", "地址"]
                    }
                },
                "表格总结": "该表格用于通用信息登记"
            }
            '''
        }
    ]
    
    for test_case in test_templates:
        print(f"\n📋 测试用例: {test_case['name']}")
        print("-" * 40)
        
        try:
            # 测试初始化状态
            initial_state = agent._create_initial_state(test_case['template'])
            
            print(f"✅ 初始化成功")
            print(f"📊 文件内容类型: {type(initial_state['file_content'])}")
            
            if isinstance(initial_state['file_content'], dict):
                print(f"📁 文件数量: {len(initial_state['file_content'])}")
                if initial_state['file_content']:
                    print(f"📋 文件列表: {list(initial_state['file_content'].keys())[:3]}...")
            else:
                print(f"📄 文件内容: {str(initial_state['file_content'])[:100]}...")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            print(f"错误类型: {type(e).__name__}")
    
    print("\n🎯 测试完成")

if __name__ == "__main__":
    test_village_extraction() 