import pandas as pd

df_list = pd.read_html(r"D:\asianInfo\ExcelAssist\conversations\1\user_uploaded_files\test.html")
df = df_list[0]
print(df)







