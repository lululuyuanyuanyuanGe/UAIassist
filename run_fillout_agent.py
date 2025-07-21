import sys
import os
sys.path.append(str(os.path.dirname(os.path.abspath(__file__))))

# Set console encoding for Windows
if sys.platform == 'win32':
    import subprocess
    subprocess.run(['chcp', '65001'], shell=True, capture_output=True)

from agents.filloutTable import FilloutTableAgent

if __name__ == "__main__":
    fillout_table_agent = FilloutTableAgent()
    fillout_table_agent.run_fillout_table_agent(
        session_id="1",
        template_file=r"conversations\1\user_uploaded_files\template\七田村_表格模板_20250721_161945.txt",
        data_file_path=['城保名册.xls', '农保名册.xls'],
        headers_mapping={
            "表格标题": "七田村低保补贴汇总表",
            "表格结构": {
                "基本信息": [
                    "城保名册.xls/农保名册.xls: 序号",
                    "城保名册.xls/农保名册.xls: 户主姓名",
                    "城保名册.xls/农保名册.xls: 身份证号码",
                    "城保名册.xls/农保名册.xls: 低保证号",
                    "推理规则: 居民类型(城保/农保) - 根据文件名自动判断，城保名册.xls对应'城保'，农保名册.xls对应'农保'"
                ],
                "保障情况": {
                    "保障人数": [
                        "城保名册.xls/农保名册.xls: 保障人数.分解.重点保障人数",
                        "城保名册.xls/农保名册.xls: 保障人数.分解.残疾人数"
                    ],
                    "领取金额": [
                        "城保名册.xls/农保名册.xls: 领取金额.分解.家庭补差",
                        "城保名册.xls/农保名册.xls: 领取金额.分解.重点救助60元",
                        "城保名册.xls/农保名册.xls: 领取金额.分解.重点救助100元",
                        "城保名册.xls/农保名册.xls: 领取金额.分解.残疾人救助"
                    ]
                },
                "领取信息": [
                    "城保名册.xls/农保名册.xls: 领款人签字(章)",
                    "城保名册.xls/农保名册.xls: 领款时间"
                ]
            }
        }
    )