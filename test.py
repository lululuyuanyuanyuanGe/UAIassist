from utilities.file_process import detect_and_process_file_paths, retrieve_file_content

# 测试文件路径检测功能
file_path = input("输入文件地址")
result = detect_and_process_file_paths(file_path)
print(result)

# 测试文件内容读取功能
file_content = retrieve_file_content(result, "1")
print(file_content)