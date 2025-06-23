 1: import pandas as pd
 2: from bs4 import BeautifulSoup
 3: import copy
 4:
 5: def fuzzy_match(columns, keyword):
 6:     return [col for col in columns if keyword in col][0]
 7:
 8: def calculate_party_age(row, current_year):
 9:     try:
10:         return current_year - int(str(row['入党时间'])[:4])
11:     except:
12:         return 0
13:
14: def determine_subsidy(row):
15:     try:
16:         party_age = row['党龄']
17:         age = row['年龄']
18:         if party_age >= 40:
19:             if 40 <= party_age <= 49:
20:                 return 100
21:             elif 50 <= party_age <= 54:
22:                 return 120
23:             elif party_age >= 55:
24:                 return 150
25:         if age >= 80 and party_age >= 55:
26:             if 80 <= age <= 89:
27:                 return 500
28:             elif 90 <= age <= 99:
29:                 return 1000
30:             elif age >= 100:
31:                 return 3000
32:         return 0
33:     except:
34:         return 0
35:
36: def main():
37:     try:
38:         # Load template
39:         with open("D:\\asianInfo\\ExcelAssist\\conversations\\1\\user_uploaded_files\\老党员补贴.txt", 'r', encoding='utf-8') as file:
40:             template_html = file.read()
41:         soup = BeautifulSoup(template_html, 'html.parser')
42:
43:         # Load data files
44:         df_list = pd.read_html("D:\\asianInfo\\ExcelAssist\\conversations\\1\\user_uploaded_files\\燕云村2024年度党员名册.txt")
45:         df = df_list[0]
46:
47:         # Parse relevant columns
48:         df['党龄'] = df.apply(lambda row: calculate_party_age(row, 2024), axis=1)
49:         df['补贴标准'] = df.apply(determine_subsidy, axis=1)
50:
51:         # Find the template row (4th row is used as the style template)
52:         table = soup.find('table')
53:         template_row = table.find_all('tr')[4]
54:
55:         # Remove existing data rows in the template
56:         for row in table.find_all('tr')[3:-1]:
57:             row.extract()
58:
59:         # Insert new rows with data
60:         for idx, row in df.iterrows():
61:             new_row = copy.deepcopy(template_row)
62:             cells = new_row.find_all('td')
63:             cells[0].string = str(row['序号'])
64:             cells[1].string = row[fuzzy_match(df.columns, "姓名")]
65:             cells[2].string = row[fuzzy_match(df.columns, "性别")]
66:             cells[3].string = row[fuzzy_match(df.columns, "民族")]
67:             cells[4].string = row[fuzzy_match(df.columns, "身份证号")]
68:             cells[5].string = row[fuzzy_match(df.columns, "出生日期")]
69:             cells[6].string = row[fuzzy_match(df.columns, "所属支部")]
70:             cells[7].string = row[fuzzy_match(df.columns, "转正时间")]
71:             cells[8].string = str(row['党龄'])
72:             cells[9].string = str(row['补贴标准'])
73:             cells[10].string = ""  # Remark column can be updated if needed
74:             table.insert(-1, new_row)
75:
76:         # Save the modified HTML
77:         with open("D:\\asianInfo\\ExcelAssist\\agents\\output\\老党员补贴_结果.html", 'w', encoding='utf-8') as file:
78:             file.write(str(soup))
79:
80:     except Exception as e:
81:         print(f"An error occurred: {e}")
82:
83: main()