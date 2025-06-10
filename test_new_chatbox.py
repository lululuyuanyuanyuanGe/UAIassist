#!/usr/bin/env python3
"""
Test script for the new chatbox interface with improved file handling and UI
"""

import sys
import os

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all imports work correctly"""
    try:
        from utilities.chatbox import create_chatbot_interface, launch_chatbot
        from nodes.frontdesk import FrontDeskAgent
        print("✅ All imports successful!")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_agent_creation():
    """Test that the agent can be created"""
    try:
        from nodes.frontdesk import FrontDeskAgent
        agent = FrontDeskAgent()
        print("✅ FrontDeskAgent created successfully!")
        return True
    except Exception as e:
        print(f"❌ Agent creation error: {e}")
        return False

def test_interface_creation():
    """Test that the interface can be created"""
    try:
        from utilities.chatbox import create_chatbot_interface
        interface = create_chatbot_interface()
        print("✅ Chatbot interface created successfully!")
        return True
    except Exception as e:
        print(f"❌ Interface creation error: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Testing New Chatbox Features")
    print("=" * 50)
    
    # Run tests
    tests = [
        ("Import Test", test_imports),
        ("Agent Creation Test", test_agent_creation),
        ("Interface Creation Test", test_interface_creation)
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name} failed")
    
    print(f"\n📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("\n🎉 All tests passed! Ready to launch the chatbot.")
        
        # Ask user if they want to launch
        response = input("\n🚀 Would you like to launch the chatbot interface? (y/n): ").lower().strip()
        
        if response in ['y', 'yes']:
            print("\n🌟 Launching ChatGPT-style chatbot interface...")
            print("Features:")
            print("• 🎨 Modern ChatGPT/Claude-style UI")
            print("• 📁 Multi-file upload support")  
            print("• 🖼️ Image file support (.png, .jpg, .jpeg, .gif, .bmp, .webp)")
            print("• 📄 Document support (.txt, .md, .csv, .json, .pdf, .xlsx, .xls)")
            print("• 🤖 Multimodal AI processing")
            print("• 💬 Improved conversation flow")
            
            try:
                from utilities.chatbox import launch_chatbot
                launch_chatbot(share=False, server_port=7860)
            except KeyboardInterrupt:
                print("\n👋 Chatbot stopped by user")
            except Exception as e:
                print(f"\n❌ Error launching chatbot: {e}")
        else:
            print("\n👋 Test completed. You can manually launch with: python utilities/chatbox.py")
    else:
        print(f"\n❌ {len(tests) - passed} test(s) failed. Please check the errors above.")

if __name__ == "__main__":
    main() 