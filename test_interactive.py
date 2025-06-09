from nodes.frontdesk import FrontDeskAgent

def simulate_conversation():
    """Simulate an interactive conversation with predefined responses"""
    
    agent = FrontDeskAgent()
    
    # Simulated conversation
    responses = [
        "我想创建一个羊村村民信息表格",
        "用来管理村民的基本信息和统计",
        "需要包括姓名、年龄、性别、职业、特长、爱好等信息",
        "是的，需要多级表头，分为基本信息和个人特色两大类",
        "基本信息包括姓名、年龄、性别、职业；个人特色包括特长、爱好、梦想",
        "这样就够了，可以生成表格了"
    ]
    
    # Start conversation
    print("🚀 开始模拟对话...")
    print("=" * 60)
    
    # Initialize with first input
    user_input = responses[0]
    print(f"👤 用户: {user_input}")
    
    # Create initial state and config
    initial_state = agent._create_initial_state(user_input, "test_session")
    config = {"configurable": {"thread_id": "test_session"}}
    
    response_index = 1
    
    try:
        for chunk in agent.graph.stream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                print(f"\n📍 节点: {node_name}")
                print("-" * 40)
                
                if isinstance(node_output, dict):
                    if "messages" in node_output and node_output["messages"]:
                        latest_message = node_output["messages"][-1]
                        if hasattr(latest_message, 'content'):
                            print(f"🤖 智能体: {latest_message.content}")
                    
                    # Check if it's asking for user input
                    if node_name == "collect_input" and response_index < len(responses):
                        print(f"👤 用户: {responses[response_index]}")
                        response_index += 1
                    
                    # Show other state info
                    for key, value in node_output.items():
                        if key != "messages" and value and key in ["gather_complete", "has_template", "table_info"]:
                            print(f"📊 {key}: {value}")
                
                print("-" * 40)
    
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    simulate_conversation() 