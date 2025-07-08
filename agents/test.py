import pandas as pd
from bs4 import BeautifulSoup

def fill_html_table(template_path, csv_path, output_path):
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')

        df = pd.read_csv(csv_path)
        
        table = soup.find('table')
        if not table:
            raise ValueError("No table found in HTML template")

        data_rows = []
        for tr in table.find_all('tr'):
            if any('序号' in td.get_text() for td in tr.find_all('td')):
                continue
            if any('审核人' in td.get_text() or '制表人' in td.get_text() for td in tr.find_all('td')):
                continue
            if tr.find_all('td'):
                data_rows.append(tr)

        max_rows = min(len(data_rows), len(df))

        for i in range(max_rows):
            tds = data_rows[i].find_all('td')
            csv_row = df.iloc[i]

            td_index = 0
            for j, value in enumerate(csv_row):
                if td_index >= len(tds):
                    break
                if '序号' in tds[td_index].get_text():
                    td_index += 1
                    if td_index >= len(tds):
                        break
                tds[td_index].string = str(value)
                td_index += 1

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))

    except Exception as e:
        raise Exception(f"Error processing files: {str(e)}")