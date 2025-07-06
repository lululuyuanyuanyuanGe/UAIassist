#!/usr/bin/env python3
"""
Test script to verify HTML to Excel conversion functionality
"""

import sys
from pathlib import Path
import json

# Add root project directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from utilities.file_process import convert_html_to_excel

def test_html_to_excel_conversion():
    """Test the HTML to Excel conversion with actual files"""
    print("🧪 Testing HTML to Excel conversion...")
    
    # Load data.json to understand the structure
    try:
        with open('agents/data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print("📊 Data structure from data.json:")
        print(f"Available locations: {list(data.keys())}")
        
        # Check 燕云村 structure
        yangyun_data = data.get("燕云村", {})
        table_files = yangyun_data.get("表格", {})
        
        print(f"\n📋 Table files in 燕云村:")
        for file_name, file_info in table_files.items():
            print(f"  - {file_name}")
            if isinstance(file_info, dict):
                print(f"    file_path: {file_info.get('file_path', 'N/A')}")
                print(f"    file_size: {file_info.get('file_size', 'N/A')}")
            else:
                print(f"    info: {file_info}")
    
    except Exception as e:
        print(f"❌ Error loading data.json: {e}")
        return
    
    # Test with HTML files in output directory
    output_dir = Path("agents/output")
    if output_dir.exists():
        html_files = list(output_dir.glob("*.html"))
        print(f"\n📁 Found {len(html_files)} HTML files in output directory:")
        
        for html_file in html_files:
            print(f"  - {html_file.name}")
        
        # Test conversion with the first HTML file
        if html_files:
            test_file = html_files[0]
            print(f"\n🔄 Testing conversion with: {test_file}")
            
            try:
                excel_file = convert_html_to_excel(str(test_file), "agents/output")
                print(f"✅ Conversion successful! Created: {excel_file}")
                
                # Verify the Excel file was created
                if Path(excel_file).exists():
                    print(f"✅ Excel file verified: {Path(excel_file).stat().st_size} bytes")
                else:
                    print(f"❌ Excel file not found: {excel_file}")
                    
            except Exception as e:
                print(f"❌ Conversion failed: {e}")
        else:
            print("⚠️ No HTML files found for testing")
    else:
        print("⚠️ Output directory not found")

def test_data_structure_access():
    """Test accessing the data structure like in the actual code"""
    print("\n🔍 Testing data structure access...")
    
    try:
        with open('agents/data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Simulate the code in recallFilesAgent.py
        files_under_location = data["燕云村"]
        table_files = files_under_location["表格"]
        
        print(f"📊 Table files structure:")
        for file_name, file_info in table_files.items():
            print(f"\n  File: {file_name}")
            print(f"  Type: {type(file_info)}")
            
            if isinstance(file_info, dict):
                print(f"  Keys: {list(file_info.keys())}")
                file_path = file_info.get("file_path", "N/A")
                print(f"  File path: {file_path}")
                
                # Check if the file exists
                if file_path != "N/A":
                    exists = Path(file_path).exists()
                    print(f"  File exists: {exists}")
                    
                    if exists:
                        file_size = Path(file_path).stat().st_size
                        print(f"  Actual file size: {file_size} bytes")
            else:
                print(f"  Content: {file_info}")
                
    except Exception as e:
        print(f"❌ Error testing data structure: {e}")

if __name__ == "__main__":
    print("🚀 Starting HTML to Excel conversion tests...")
    print("=" * 60)
    
    test_data_structure_access()
    test_html_to_excel_conversion()
    
    print("\n" + "=" * 60)
    print("✅ Test completed!") 