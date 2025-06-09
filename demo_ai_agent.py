#!/usr/bin/env python3
"""
Demo script for the LangGraph-based AI Prompt Requirement Agent
Shows how the AI handles conversation flow and decision-making
"""

import os
import sys
sys.path.append('nodes')

def setup_demo():
    """Setup demo environment"""
    print("🚀 LangGraph AI Agent Demo")
    print("=" * 50)
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  For full functionality, set your OPENAI_API_KEY environment variable")
        print("   Get one from: https://platform.openai.com/account/api-keys")
        print()
        print("📝 For demo purposes, you can:")
        print("   1. Set the key: export OPENAI_API_KEY=your_key_here")
        print("   2. Or modify the agent to use a different model")
        print()
        
        proceed = input("Continue with demo anyway? (y/n): ").lower()
        if proceed != 'y':
            print("👋 Demo cancelled. Set up your API key and try again!")
            return False
    
    return True

def demonstrate_agent_capabilities():
    """Demonstrate the AI agent capabilities"""
    print("\n🎯 This AI agent demonstrates:")
    print("• 🧠 LLM-driven conversation flow")
    print("• 🔧 Tool usage for structured actions")
    print("• 💾 State persistence with interruptions")
    print("• 🔄 Human-in-the-loop workflow")
    print("• 🎨 Dynamic prompt template generation")
    print()
    
    example_conversation = """
Example AI-Human Conversation:
🤖 AI: "Hi! I'm here to help you create a custom prompt template. 
        What kind of task would you like your prompt to handle?"

👤 Human: "I need a prompt for writing blog posts"

🤖 AI: "Great! Blog post writing. Let me gather more details.
        [Uses save_requirement_info tool]
        Who is your target audience for these blog posts?"

👤 Human: "Tech professionals and developers"

🤖 AI: "Perfect! Tech professionals and developers.
        [Uses save_requirement_info tool]
        What writing style would you prefer - technical and detailed, 
        or more accessible and engaging?"

... (AI continues intelligently based on responses)

🤖 AI: "I have enough information now. Let me generate your template.
        [Uses generate_prompt_template tool]
        Here's your customized prompt template..."
"""
    
    print(example_conversation)
    print()

def main():
    """Main demo function"""
    if not setup_demo():
        return
    
    demonstrate_agent_capabilities()
    
    print("🎮 Ready to try the AI agent?")
    print("Choose your option:")
    print("1. Run the interactive AI agent")
    print("2. View the agent architecture")
    print("3. Exit demo")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        try:
            from frontdesk import PromptRequirementAgent
            print("\n🤖 Starting AI Agent...")
            agent = PromptRequirementAgent()
            agent.run_interactive_session()
        except ImportError as e:
            print(f"❌ Import error: {e}")
            print("💡 Make sure you have installed: pip install langgraph langchain-openai")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    elif choice == "2":
        print("\n🏗️  AI Agent Architecture:")
        print("""
        ┌─────────────────┐
        │   START         │
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │ gather_info_node│  ← AI decides what to ask
        │    (AI LLM)     │  ← Uses conversation context
        └────────┬────────┘  ← Calls tools when needed
                 │
        ┌────────▼────────┐
        │   tool_node     │  ← save_requirement_info
        │  (Function      │  ← check_completeness  
        │   Calling)      │  ← generate_template
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │human_in_loop_   │  ← Interruption point
        │     node        │  ← Waits for human input
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │generate_prompt_ │  ← Final AI generation
        │     node        │  ← Creates custom template
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │      END        │
        └─────────────────┘
        
        🔑 Key Features:
        • AI-driven decision making at each step
        • Tools for structured actions
        • Persistent state across interruptions
        • Natural conversation flow
        """)
    
    else:
        print("👋 Thanks for trying the AI agent demo!")

if __name__ == "__main__":
    main() 