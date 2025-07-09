import os
import copy
from bs4 import BeautifulSoup

# 参数
template_path = r'D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\template\老党员补贴.txt'
output_path = r'D:\asianInfo\ExcelAssist\conversations\1\output\expanded_template.html'
target_row_count = 66

try:
    with open(template_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    table = soup.find('table')
    all_rows = table.find_all('tr')

    # 找出表头（列名）所在的那一行
    header_index = None
    for i, row in enumerate(all_rows):
        if all(cell.text.strip() in ["序号", "姓名", "性别", "民族", "身份证号码", "出生时间", "所在党支部", "成为正式党员时间", "党龄（年）", "生活补贴标准（元／月）", "备注"]
               for cell in row.find_all('td')):
            header_index = i
            break

    if header_index is None:
        raise ValueError("未找到表头行")

    # 数据行模板通常是表头下一行
    data_row_template = all_rows[header_index + 1]

    # 识别表尾行（含“审核人”、“制表人”等字段）
    footer_index = None
    for i in reversed(range(len(all_rows))):
        row = all_rows[i]
        if "审核人" in row.text or "制表人" in row.text:
            footer_index = i
            break

    if footer_index is None:
        raise ValueError("未找到表尾（审核人）行")

    # 找出现有数据行数量（紧跟表头的连续行）
    data_rows = []
    for i in range(header_index + 1, footer_index):
        row = all_rows[i]
        if row.find_all('td'):
            data_rows.append(row)

    existing_count = len(data_rows)
    to_add = target_row_count - existing_count

    for i in range(to_add):
        new_row = copy.deepcopy(data_row_template)
        tds = new_row.find_all('td')
        if tds:
            tds[0].string = str(existing_count + i + 1)
            for td in tds[1:]:
                td.clear()
                br = soup.new_tag("br")
                td.append(br)
        # 插入在表尾前面
        table.insert(footer_index, new_row)
        footer_index += 1  # 保持插入点始终在尾部行之前

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))

except Exception as e:
    print(f"发生错误: {e}")
