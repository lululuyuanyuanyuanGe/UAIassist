import pandas as pd
from bs4 import BeautifulSoup
import copy

csv_file_path = r'D:\asianInfo\ExcelAssist\conversations\1\CSV_files\synthesized_table_with_only_data.csv'
html_template_path = r'D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\template\老党员补贴.txt'
output_html_path = r'D:\asianInfo\ExcelAssist\conversations\1\output\filled_template.html'

try:
    df = pd.read_csv(csv_file_path)
    with open(html_template_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    table = soup.find('table')
    rows = table.find_all('tr')
    data_row_template = rows[3]
    existing_data_rows = rows[3:-2]
    num_existing_rows = len(existing_data_rows)
    num_csv_rows = len(df)

    if num_csv_rows > num_existing_rows:
        for i in range(num_csv_rows - num_existing_rows):
            new_row = copy.copy(data_row_template)
            new_row.find('td').string = str(num_existing_rows + i + 1)
            table.insert(-2, new_row)

    rows = table.find_all('tr')[3:-2]

    for i, row in enumerate(rows):
        if i < num_csv_rows:
            cells = row.find_all('td')
            csv_row = df.iloc[i]
            cells[0].string = str(i + 1)
            cells[1].string = csv_row['姓名']
            cells[2].string = csv_row['性别']
            cells[3].string = csv_row['民族']
            cells[4].string = csv_row['身份证号码']
            cells[5].string = csv_row['出生时间']
            cells[6].string = csv_row['所在党支部']
            cells[7].string = csv_row['成为正式党员时间']
            cells[8].string = str(csv_row['党龄（年）'])
            cells[9].string = str(csv_row['生活补贴标准（元／月）'])
            cells[10].string = csv_row.get('备注', '')

    with open(output_html_path, 'w', encoding='utf-8') as file:
        file.write(str(soup))

except Exception as e:
    print(f"An error occurred: {e}")