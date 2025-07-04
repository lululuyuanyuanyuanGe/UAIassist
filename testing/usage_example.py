"""
Simple Usage Example for Excel to Markdown Extractor

This example shows how to use the ExcelToMarkdownExtractor to convert
Excel tables (in HTML format) to Markdown while preserving header hierarchies.
"""

from excel_to_markdown_extractor import ExcelToMarkdownExtractor
from pathlib import Path

def simple_usage_example():
    """Simple example of how to use the extractor."""
    
    # Create an instance of the extractor
    extractor = ExcelToMarkdownExtractor()
    
    # Example 1: Extract from a single file
    print("Example 1: Single file extraction")
    print("-" * 40)
    
    input_file = r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_files\老党员补贴.txt"
    
    try:
        # Extract to markdown (will auto-generate output filename)
        result = extractor.extract_from_file(input_file)
        
        print("✅ Extraction successful!")
        print("Preview of markdown content:")
        print(result[:300] + "...")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*60 + "\n")
    
    # Example 2: Extract with custom output file
    print("Example 2: Custom output file")
    print("-" * 40)
    
    custom_output = "testing/custom_output.md"
    
    try:
        result = extractor.extract_from_file(input_file, custom_output)
        print(f"✅ Saved to {custom_output}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*60 + "\n")
    
    # Example 3: Batch processing
    print("Example 3: Batch processing")
    print("-" * 40)
    
    input_directory = r"D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_files"
    output_directory = "testing/batch_output"
    
    try:
        results = extractor.batch_extract(input_directory, output_directory)
        
        successful = sum(1 for result in results.values() if result == "Success")
        total = len(results)
        
        print(f"📊 Batch processing complete:")
        print(f"   Total files: {total}")
        print(f"   Successful: {successful}")
        print(f"   Failed: {total - successful}")
        
        # Show individual results
        for filename, status in list(results.items())[:5]:  # Show first 5
            print(f"   {filename}: {status}")
        
        if len(results) > 5:
            print(f"   ... and {len(results) - 5} more files")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def show_header_structure_analysis():
    """Demonstrate header structure analysis."""
    
    print("Header Structure Analysis Demo")
    print("=" * 50)
    
    # Sample HTML content with multi-level headers
    sample_html = """
    <html><body><table>
    <tr>
        <td colspan="4">员工信息表</td>
    </tr>
    <tr>
        <td>序号</td>
        <td colspan="2">基本信息</td>
        <td>备注</td>
    </tr>
    <tr>
        <td></td>
        <td>姓名</td>
        <td>年龄</td>
        <td></td>
    </tr>
    <tr>
        <td>1</td>
        <td>张三</td>
        <td>25</td>
        <td>优秀员工</td>
    </tr>
    <tr>
        <td>2</td>
        <td>李四</td>
        <td>30</td>
        <td>部门经理</td>
    </tr>
    </table></body></html>
    """
    
    extractor = ExcelToMarkdownExtractor()
    
    try:
        result = extractor.extract_table_to_markdown(sample_html)
        
        print("Input HTML:")
        print(sample_html)
        print("\nGenerated Markdown:")
        print(result)
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # Run the simple usage examples
    simple_usage_example()
    
    print("\n" + "="*80 + "\n")
    
    # Show header structure analysis
    show_header_structure_analysis() 