import pandas as pd
from bs4 import BeautifulSoup

def fill_html_table_no_header(html_path, csv_path, output_path):
    # 读取 HTML
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    table = soup.find('table')

    # 读取 CSV（无表头）
    df = pd.read_csv(csv_path, header=None, dtype=str).fillna("")

    # 找到表格中数据行（排除标题行、表尾等）
    data_rows = []
    for tr in table.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 2 and tds[0].text.strip().isdigit():
            data_rows.append(tr)

    for i, row_data in enumerate(df.itertuples(index=False)):
        if i >= len(data_rows):
            break

        tr = data_rows[i]
        tds = tr.find_all('td')

        # 第一列填入自动序号
        if not tds[0].text.strip():
            tds[0].string = str(i + 1)

        # 其余列按顺序填入 CSV 数据
        for j in range(1, min(len(tds), len(row_data) + 1)):
            if not tds[j].text.strip():
                tds[j].string = str(row_data[j - 1])

    # 输出到目标文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))

# 路径设置
html_path = r'D:\asianInfo\ExcelAssist\agents\output\老党员补贴_结果.html'
csv_path = r'D:\asianInfo\ExcelAssist\agents\output\synthesized_table.csv'
output_path = r'D:\asianInfo\ExcelAssist\agents\output\老党员补贴_结果_filled.html'

fill_html_table_no_header(html_path, csv_path, output_path)
