import pandas as pd

def excel_to_markdown(file_path, sheet_name="Sheet1"):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df.to_markdown(index=False)

# Usage
markdown_content = excel_to_markdown(r"D:\asianInfo\数据\数据集\农业\以此为准5.集体林权流转授权委托协议签字表(2)(1)(1).xlsx1.xlsx")
with open(r'D:\asianInfo\ExcelAssist\testing\output.md', 'w', encoding='utf-8') as f:
    f.write(markdown_content)



def excel_to_csv(excel_file, csv_file, sheet_name="Sheet1"):
    # Read Excel file
    df = pd.read_excel(excel_file, sheet_name=sheet_name)
    
    # Convert to CSV
    df.to_csv(csv_file, index=False, encoding='utf-8')
    
# Usage
excel_to_csv(r"D:\asianInfo\数据\数据集\农业\以此为准5.集体林权流转授权委托协议签字表(2)(1)(1).xlsx1.xlsx", r'D:\asianInfo\ExcelAssist\testing\output.csv')
