#!/usr/bin/env python3
"""
Test script to debug the processUserInput agent execution
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.processUserInput import ProcessUserInputAgent
from langchain_core.messages import HumanMessage, AIMessage

def test_process_user_input_debug():
    """Test the ProcessUserInputAgent with a simple file upload scenario"""
    
    print("🔄 创建 ProcessUserInputAgent 实例...")
    agent = ProcessUserInputAgent()
    
    print("🔄 创建初始状态...")
    initial_state = agent.create_initial_state()
    
    print("🔄 测试文件上传场景...")
    # Simulate a file upload scenario similar to your log
    test_input = "d:\\asianInfo\\数据\\新槐村\\9.15接龙镇附件4：脱贫人口小额贷款贴息申报汇总表.xlsx"
    
    # Update the state with test input
    test_state = initial_state.copy()
    test_state["process_user_input_messages"] = [HumanMessage(content=test_input)]
    test_state["user_input"] = test_input
    
    print(f"📝 测试输入: {test_input}")
    
    try:
        print("🔄 开始执行图...")
        config = {"configurable": {"thread_id": "test_debug"}}
        
        # Use stream to see step-by-step execution
        step_count = 0
        for chunk in agent.graph.stream(test_state, config=config, stream_mode="updates"):
            step_count += 1
            print(f"\n📍 步骤 {step_count}: {chunk}")
            
            # Safety check to prevent infinite loops
            if step_count > 10:
                print("⚠️ 执行步骤过多，可能存在循环，停止测试")
                break
        
        print("✅ 图执行完成")
        
    except Exception as e:
        print(f"❌ 图执行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_process_user_input_debug() 