from utilities.modelRelated import model_creation

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage


llm = model_creation("gpt-4o")
message1 = SystemMessage(content="""你是一个输入验证专家，需要判断用户的文本输入是否与表格生成、Excel处理相关，并且是否包含有意义的内容，你的判断需要根据上下文，
        我会提供上一个AI的回复，以及用户输入，你需要根据上下文，判断用户输入是否与表格生成、Excel处理相关，并且是否包含有意义的内容。

        上一个AI的回复: None
        用户输入: 你好
        验证标准：
        1. **有效输入 [Valid]**:
           - 明确提到需要生成表格、填写表格、Excel相关操作
           - 包含具体的表格要求、数据描述、字段信息
           - 询问表格模板、表格格式相关问题
           - 提供了表格相关的数据或信息

        2. **无效输入 [Invalid]**:
           - 完全与表格/Excel无关的内容
           - 垃圾文本、随机字符、无意义内容
           - 空白或只有标点符号
           - 明显的测试输入或无关问题

        请仔细分析用户输入，然后只回复以下选项之一：
        [Valid] - 如果输入与表格相关且有意义
        [Invalid] - 如果输入无关或无意义""")
message2 = HumanMessage(content="用户输入： “表格为复杂表头，里面有100行，验证结果为[valid]”")

response = llm.invoke([message1])
print(response.content)




