from bs4 import BeautifulSoup
import copy

template_path = r'D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\template\老党员补贴.txt'
output_path = r'D:\asianInfo\ExcelAssist\conversations\1\output\expanded_template.html'
target_row_count = 66

with open(template_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

table = soup.find('table')
all_rows = table.find_all('tr')

# 步骤 1：找到表头行（包含“序号”字段的那一行）
header_index = None
for i, row in enumerate(all_rows):
    texts = [td.get_text(strip=True) for td in row.find_all('td')]
    if texts[:3] == ['序号', '姓名', '性别']:
        header_index = i
        break
if header_index is None:
    raise Exception("找不到表头行")

# 步骤 2：找到“审核人 / 制表人”尾行
footer_index = None
for i in reversed(range(len(all_rows))):
    if '审核人' in all_rows[i].get_text() or '制表人' in all_rows[i].get_text():
        footer_index = i
        break
if footer_index is None:
    raise Exception("找不到表尾（审核人）行")

# 步骤 3：清除原有数据行（表头和审核人之间的所有 tr）
for i in range(footer_index - 1, header_index, -1):
    all_rows[i].decompose()

# 步骤 4：找到用于复制的新行模板（表头下第一个 tr）
template_row = copy.deepcopy(all_rows[header_index + 1])

# 步骤 5：插入 target_row_count 行
for i in range(target_row_count):
    new_row = copy.deepcopy(template_row)
    tds = new_row.find_all('td')
    if tds:
        tds[0].string = str(i + 1)
        for td in tds[1:]:
            td.clear()
            td.append(soup.new_tag('br'))
    # 插入到表尾前一行
    all_rows[footer_index].insert_before(new_row)

# 步骤 6：保存文件
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(str(soup))
