#!/usr/bin/env python3
"""
Launch script for the Terminal Chat Interface
"""

import sys
import os

# Add the utilities directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'utilities'))

from web_interface import launch_interface

if __name__ == "__main__":
    print("🚀 Starting Terminal Chat Interface...")
    print("   • Type /cmd <command> to execute terminal commands")
    print("   • Upload files using the file picker")
    print("   • Type /help for more commands")
    print("   • Access the interface at: http://localhost:7860")
    print("   • Press Ctrl+C to stop the server")
    print()
    
    try:
        launch_interface(share=False, port=7860)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error starting interface: {e}")
        sys.exit(1) 