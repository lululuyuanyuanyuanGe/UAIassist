from bs4 import BeautifulSoup
import copy
import os

input_path = r'D:\asianInfo\ExcelAssist\conversations\files\user_uploaded_files\template\老党员补贴.txt'
output_path = r'D:\asianInfo\ExcelAssist\conversations\1\output\template.html'
num_rows_to_generate = 100

os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(input_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

# 确保HTML文档有基本结构
if not soup.find('html'):
    html_tag = soup.new_tag('html')
    soup.append(html_tag)

if not soup.find('head'):
    head_tag = soup.new_tag('head')
    soup.html.insert(0, head_tag)

if not soup.find('body'):
    body_tag = soup.new_tag('body')
    soup.html.append(body_tag)

table = soup.find('table')
if not table:
    raise ValueError("未找到表格元素")

all_rows = table.find_all('tr')

data_row_template = None
for row in all_rows:
    cells = row.find_all('td')
    if cells and cells[0].text.strip().isdigit():
        data_row_template = copy.deepcopy(row)
        break

if not data_row_template:
    raise ValueError("未找到有效的模板数据行")

footer_row = None
for row in reversed(all_rows):
    if '审核人' in row.text or '制表人' in row.text:
        footer_row = row
        break

if footer_row:
    footer_row.extract()

for row in all_rows:
    cells = row.find_all('td')
    if cells and cells[0].text.strip().isdigit():
        row.extract()

for i in range(1, num_rows_to_generate + 1):
    new_row = copy.deepcopy(data_row_template)
    cells = new_row.find_all('td')
    cells[0].string = str(i)
    for j in range(1, len(cells)):
        cells[j].string = ''
    table.append(new_row)

if footer_row:
    table.append(footer_row)

style_tag = soup.new_tag('style')
style_tag.string = """
table {
    border-collapse: collapse;
    width: 100%;
    font-family: 'Microsoft YaHei', 'Arial', sans-serif;
    font-size: 14px;
    margin-top: 20px;
    color: #333;
}
th, td {
    border: 1px solid #444;
    padding: 8px 10px;
    text-align: center;
    vertical-align: middle;
}
td[colspan] {
    font-weight: bold;
    background-color: #e6f0ff;
    text-align: left;
    padding: 10px;
}
tr:nth-child(even) td {
    background-color: #f9f9f9;
}
tr:nth-child(odd) td {
    background-color: #ffffff;
}
th {
    background-color: #dce6f1;
    font-weight: bold;
}
"""

# 确保head标签存在
if not soup.head:
    head_tag = soup.new_tag('head')
    soup.html.insert(0, head_tag)

soup.head.append(style_tag)

# 确保文档结构完整
if not soup.find('title'):
    title_tag = soup.new_tag('title')
    title_tag.string = "老党员补贴表格"
    soup.head.insert(0, title_tag)

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(str(soup.prettify()))