from utilities.file_process import *
from utilities.message_process import *

user_input_files = input("请输入用户输入的文件路径: ")
result = detect_and_process_file_paths(user_input_files)
print(result)

content = retrieve_file_content(result, "1")
print(content)





