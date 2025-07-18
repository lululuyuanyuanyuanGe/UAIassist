from langchain_core.messages import SystemMessage, HumanMessage
from utils.modelRelated import invoke_model


system_prompt = f"""
你是一位专业的输入验证专家，任务是判断用户的文本输入是否与**表格生成或 Excel 处理相关**，并且是否在当前对话上下文中具有实际意义。

你将获得以下两部分信息：
- 上一轮 AI 的回复（用于判断上下文是否连贯）
- 当前用户的输入内容

请根据以下标准进行判断：

【有效输入 [Valid]】满足以下任一条件即可视为有效：
- 明确提到生成表格、填写表格、Excel 处理、数据整理等相关操作
- 提出关于表格字段、数据格式、模板结构等方面的需求或提问
- 提供表格相关的数据内容、字段说明或规则
- 对上一轮 AI 的回复作出有意义的延续或回应（即使未直接提到表格）
- 即使存在错别字、语病、拼写错误，只要语义清晰合理，也视为有效

【无效输入 [Invalid]】符合以下任一情况即视为无效：
- 内容与表格/Excel 完全无关（如闲聊、情绪表达、与上下文跳脱）
- 明显为测试文本、随机字符或系统调试输入（如 "123"、"测试一下"、"哈啊啊啊" 等）
- 仅包含空白、表情符号、标点符号等无实际内容

【输出要求】
请你根据上述标准，**仅输出以下两种结果之一**（不添加任何其他内容）：
- [Valid]
- [Invalid]


"""



print("📤 正在调用LLM进行文本输入验证...")
# Get LLM validation
user_input = "用户输入：" + "帮我生成一个城镇农村居民低保发放汇总表"
print("analyze_text_input时调用模型的输入: \n" + user_input)              
validation_response = invoke_model(model_name="Pro/deepseek-ai/DeepSeek-V3", messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_input)])
# validation_response = self.llm_s.invoke([SystemMessage(content=system_prompt)])