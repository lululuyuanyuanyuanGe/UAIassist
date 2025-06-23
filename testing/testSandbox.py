from bs4 import BeautifulSoup

with open(r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\老党员补贴.txt", "r", encoding="utf-8") as f:
    template_html = f.read()
with open(r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\燕云村2024年度党员名册.txt", "r", encoding="utf-8") as f:
    member_html = f.read()

template_soup = BeautifulSoup(template_html, "html.parser")
member_soup = BeautifulSoup(member_html, "html.parser")



from datetime import datetime
import pandas as pd

member_rows = member_soup.find_all("tr")[2:]
members = []
for row in member_rows:
    cells = row.find_all("td")
    if len(cells) >= 13:
        name = cells[1].text.strip()
        gender = cells[2].text.strip()
        ethnic = cells[3].text.strip()
        birthday = cells[6].text.strip()
        pid = cells[8].text.strip()
        party_join_date = cells[9].text.strip()
        party_branch = cells[11].text.strip()

        if party_join_date.isdigit():
            party_date = datetime.strptime(party_join_date, "%Y%m%d")
            party_years = datetime(2024, 12, 31).year - party_date.year
        else:
            party_years = ""

        if isinstance(party_years, int):
            if party_years >= 55:
                subsidy = 150
            elif party_years >= 50:
                subsidy = 120
            elif party_years >= 40:
                subsidy = 100
            else:
                subsidy = ""
        else:
            subsidy = ""

        members.append([
            name, gender, ethnic, pid, birthday,
            party_branch, party_join_date,
            party_years, subsidy, ""
        ])

df = pd.DataFrame(members, columns=[
    "name", "gender", "ethnicity", "id_number", "birth_date",
    "party_branch", "join_date", "party_age", "subsidy", "remarks"
])



filled_soup = BeautifulSoup(template_html, "html.parser")
table_rows = filled_soup.find_all("tr")
data_rows = table_rows[3:-1]  # Skip header/footer

for i, (row, data) in enumerate(zip(data_rows, df.itertuples(index=False)), start=1):
    cells = row.find_all("td")
    if len(cells) == 11:
        cells[0].string = str(i)
        cells[1].string = str(data.name)
        cells[2].string = str(data.gender)
        cells[3].string = str(data.ethnicity)
        cells[4].string = str(data.id_number)
        cells[5].string = str(data.birth_date)
        cells[6].string = str(data.party_branch)
        cells[7].string = str(data.join_date)
        cells[8].string = str(data.party_age)
        cells[9].string = str(data.subsidy)
        cells[10].string = str(data.remarks)



with open(r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\结果.txt", "w", encoding="utf-8") as f:
    f.write(str(filled_soup))




from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
import copy

# 读取两个 HTML 文件（模板 和 名册）
with open("老党员补贴.txt", "r", encoding="utf-8") as f:
    template_html = f.read()
with open("燕云村2024年度党员名册.txt", "r", encoding="utf-8") as f:
    member_html = f.read()

# 解析 HTML
template_soup = BeautifulSoup(template_html, "html.parser")
member_soup = BeautifulSoup(member_html, "html.parser")

# 提取党员信息并计算补贴金额
member_rows = member_soup.find_all("tr")[2:]
members = []
for row in member_rows:
    cells = row.find_all("td")
    if len(cells) >= 13:
        name = cells[1].text.strip()
        gender = cells[2].text.strip()
        ethnic = cells[3].text.strip()
        birthday = cells[6].text.strip()
        pid = cells[8].text.strip()
        party_join_date = cells[9].text.strip()
        party_branch = cells[11].text.strip()

        # 计算党龄
        if party_join_date.isdigit():
            party_date = datetime.strptime(party_join_date, "%Y%m%d")
            party_years = datetime(2024, 12, 31).year - party_date.year
        else:
            party_years = ""

        # 根据党龄判断补贴金额
        if isinstance(party_years, int):
            if party_years >= 55:
                subsidy = 150
            elif party_years >= 50:
                subsidy = 120
            elif party_years >= 40:
                subsidy = 100
            else:
                subsidy = ""
        else:
            subsidy = ""

        members.append([
            name, gender, ethnic, pid, birthday,
            party_branch, party_join_date,
            party_years, subsidy, ""
        ])

# 放入 DataFrame
df = pd.DataFrame(members, columns=[
    "name", "gender", "ethnicity", "id_number", "birth_date",
    "party_branch", "join_date", "party_age", "subsidy", "remarks"
])

# 处理模板行与表格扩展
table = template_soup.find("table")
template_row_backup = copy.deepcopy(table.find_all("tr")[3])  # 备份模板行

# 删除原始的10个数据行（保留标题和最后一行）
for _ in range(10):
    row = table.find_all("tr")[3]
    if row:
        row.decompose()

# 插入新的66行
for i, row_data in enumerate(df.itertuples(index=False), start=1):
    new_row = copy.deepcopy(template_row_backup)
    cells = new_row.find_all("td")
    cells[0].string = str(i)
    cells[1].string = str(row_data.name)
    cells[2].string = str(row_data.gender)
    cells[3].string = str(row_data.ethnicity)
    cells[4].string = str(row_data.id_number)
    cells[5].string = str(row_data.birth_date)
    cells[6].string = str(row_data.party_branch)
    cells[7].string = str(row_data.join_date)
    cells[8].string = str(row_data.party_age)
    cells[9].string = str(row_data.subsidy)
    cells[10].string = str(row_data.remarks)
    table.insert(-1, new_row)

# 保存最终 HTML
with open("老党员补贴_66人_已填.html", "w", encoding="utf-8") as f:
    f.write(str(template_soup))
