#测试图片识别api
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from utils.modelRelated import invoke_model
import base64

with open(r"D:\asianInfo\ExcelAssist\agents\test\1城保名册.png", "rb") as image_file:
    image_data = image_file.read()
    base64_image = base64.b64encode(image_data).decode("utf-8")


human_message = HumanMessage(content=[
    {
        "type": "text",
        "text": "请识别图片中的文字"
    },
    {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{base64_image}"
        }
    }
])

# system_message = SystemMessage(content="""
# 你是一位专业的表格结构分析专家，擅长从复杂 Excel 表格或 HTML 表格中提取完整的多级表头结构，并识别**分类汇总关系**。

# 请根据用户提供的表头图片，完成以下任务：

# 【分析流程 - 请按步骤深度思考】

# 🔍 **第一步：图片观察与理解**
# - 仔细观察表头图片，识别所有可见的表头文字内容
# - 理解表格的用途和业务场景（如：人员统计、资金发放、物资登记等）
# - 识别表头的行数和列数结构

# 🔍 **第二步：表头关系分析**
# - 分析每个表头单元格的合并情况和跨列/跨行关系
# - 识别哪些是主标题（通常跨越多列）、哪些是分类表头、哪些是具体字段
# - 理解表头的层级关系：上级分类 → 下级分类 → 具体字段

# 🔍 **第三步：逻辑结构推理**
# - 基于业务逻辑，推理各个表头之间的从属关系
# - 识别哪些字段属于同一信息类别（如：基本信息、金额信息、统计信息等）
# - **重点分析汇总关系**：
#   - 仔细观察哪些字段在逻辑上是其他字段的数值汇总
#   - 特别注意那些看起来像分类标题但实际上有具体数值的字段
#   - 例如："保障人数"如果有具体数值，很可能是"重点保障人数"+"残疾人数"的汇总
#   - 例如："总金额"通常是各项明细金额的汇总
#   - 识别这种汇总关系的关键：观察字段名称的语义和在表格中的位置关系

# 🔍 **第四步：结构验证与组织**
# - 验证推理的层级结构是否符合图片中的实际表头布局
# - 确保每个表头都有明确的层级位置和从属关系
# - **验证汇总关系**：
#   - 对于识别出的汇总字段，检查其是否应该用 "字段名": "子字段1 + 子字段2 + ..." 格式
#   - 确保汇总字段不会被错误地当作分类标题处理
#   - 例如："保障人数"应该表示为 "保障人数": "重点保障人数 + 残疾人数"，而不是作为分类包含子字段
# - 组织成完整的嵌套JSON结构

# 【任务目标】

# 1. 提取完整的表头层级结构：
#    - 包含表格主标题、分类表头、字段表头，逐层提取；
#    - 使用嵌套的 key-value 结构，表达表头的层级关系；
#    - 每一级表头都应清晰反映其子级字段或子分类。

# 2. 识别分类汇总关系：
#    - 如果某个表头字段是其他字段的**数值汇总**（例如：该字段是总和，其他字段是各项明细），请在结构中体现这种汇总逻辑；
#    - **关键识别原则**：
#      - 观察字段名称：包含"总"、"合计"、"小计"等词汇通常是汇总字段
#      - 语义分析：如"保障人数"在逻辑上应该是各类保障人数的汇总
#      - 位置关系：汇总字段通常在其组成字段的左侧或上方
#    - 用以下格式表达：
#      "汇总字段": "组成字段1 + 组成字段2 + ..."
#    - 组成字段列出为 []（表示该字段用于填入数据）。

# 【输出格式】

# **严格JSON格式要求：**
# - 输出必须是完整、有效的JSON格式，可以直接被JSON解析器解析
# - 根键名必须为 {file_name}（不能更改）
# - 结构必须使用标准JSON语法：双引号、正确的逗号和括号
# - 不能有任何非JSON内容（如解释性文字、markdown标记等）

# **层级关系表达：**
# - 分类标题用对象（{}）表示，包含其子字段
# - 具体数据字段用空数组（[]）表示
# - 汇总字段用字符串表示计算公式："字段1 + 字段2 + ..."

# **标准输出结构：**
# ```json
# {
#   "{file_name}": {
#     "表格结构": {
#       "主分类1": {
#         "子分类1": {
#           "具体字段1": [],
#           "具体字段2": [],
#           "汇总字段": "具体字段1 + 具体字段2"
#         },
#         "子分类2": {
#           "具体字段3": [],
#           "具体字段4": []
#         }
#       },
#       "主分类2": [
#         "具体字段5",
#         "具体字段6"
#       ]
#     },
#     "表格总结": "不超过150字的表格用途和核心信息描述"
#   }
# }
# ```

# 【特别注意】

# **JSON格式严格要求：**
# - **必须输出完整有效的JSON**：输出内容必须能够被JSON.parse()成功解析
# - **不能包含任何解释**：不要在JSON前后添加任何说明文字或markdown标记  
# - **语法必须正确**：使用双引号、正确的逗号分隔、正确的括号匹配
# - **直接输出JSON**：整个输出就是一个JSON对象，没有其他内容

# **表头分析要求：**
# - 忽略元数据：如"所属地区"、"制表单位"、"制表时间"等说明性文字，非数据字段不纳入表头
# - 表头结构只用于描述数据列，实际数据内容不需要输出
# - 保持层级结构清晰，完整保留多级表头信息
# - **关键**：必须基于图片中的实际表头布局来确定层级关系，不能仅凭字段名称猜测
# - 确保分析的结构与图片中显示的表头合并和排列完全一致
# - 如果图片中某些表头跨越多列或多行，必须在结构中准确体现这种层级关系

# **汇总关系识别重点：**
# - 不要将汇总字段误认为是分类标题
# - 如果一个字段在业务逻辑上是其他字段的数值汇总，必须使用 "字段名": "字段1 + 字段2 + ..." 格式
# - 典型例子：当看到"保障人数"、"重点保障人数"、"残疾人数"时，要识别出"保障人数"="重点保障人数"+"残疾人数"的汇总关系

# **最终输出要求：**
# 请直接输出一个完整的JSON对象，不要包含任何其他内容。确保输出的JSON可以被标准JSON解析器成功解析。

# """)

system_message = SystemMessage(content="""
你是一位专业的表格结构分析专家，擅长从复杂的 Excel 或 HTML 表格中提取完整的多级表头结构，并结合数据内容辅助理解字段含义、层级和分类汇总关系。

请根据用户提供的表格，完成以下任务：

【任务目标】

1. 提取完整的表头层级结构：
   - 从表格主标题开始，逐层提取所有分类表头、字段表头；
   - 结合实际数据，辅助判断字段的含义、分类、层级归属，确保结构理解准确；
   - 使用嵌套的 key-value 结构，表达表头的层级关系；
   - 每一级表头都应清晰反映其子级字段或子分类，避免遗漏或误分类。

2. 采用「值 / 分解」结构识别分类汇总关系：
   - 如果某个父级字段**自身有数据**，同时又包含多个子字段（如“保障人数”、“领取金额”），必须采用以下格式：

   {
     "字段名": {
       "值": [],          // 表示该字段自身的数据（即原表格中该字段的单元格数据）
       "分解": {           // 表示该字段下的子分类或子字段
         "子字段1": [],
         "子字段2": [],
         ...
       }
     }
   }

   - 如果父级字段只是分类（自身无数据），只输出 "分解"；
   - 如果某个字段既没有子分类，也没有子字段拆分，直接输出为：

   {
     "字段名": []
   }

3. 辅助判断字段含义：
   - 结合数据内容辅助判断字段用途，避免仅依赖表头文字表面拆分；
   - 识别重复字段、并列字段、合并单元格带来的结构层级；
   - 对于存在数据但表头描述模糊的情况，尽量根据数据判断其真实分类。

【输出格式要求】

- 严格输出为**标准 JSON 格式**，不能有 markdown、代码块标记或其他多余文字；
- 只输出表头结构，**不要输出表格总结、描述、用途说明或数据样例**；
- JSON 的根键名必须为 {file_name}（严格保留，不能更改）；
- 每一层级都以对象形式描述，遵循以下结构：

【输出示例】

{
  "{file_name}": {
    "表格结构": {
      "序号": [],
      "户主姓名": [],
      "低保证号": [],
      "身份证号码": [],
      "保障人数": {
        "值": [],
        "分解": {
          "重点保障人数": [],
          "残疾人数": []
        }
      },
      "领取金额": {
        "值": [],
        "分解": {
          "家庭补差": [],
          "重点救助60元": [],
          "重点救助100元": [],
          "残疾人救助": []
        }
      },
      "领款人签字(章)": [],
      "领款时间": []
    }
  }
}

【特别注意】

- 所有输出必须为严格的 JSON 结构；
- 不允许输出表格总结、描述、元数据或用途说明；
- 不允许有 markdown、代码块标记或多余的格式符号；
- 保持层级结构清晰，完整保留所有分类表头、子表头和字段表头；
- **父级字段有数据时，必须采用 "值 / 分解" 结构，确保数据与分类信息都保留**；
- 必须结合数据辅助判断字段含义，确保分类、层级和汇总逻辑准确。

""")

# Next add the prompt to generate the subtitle and the footer




message = [system_message, human_message]
response = invoke_model(model_name="Qwen/Qwen2.5-VL-72B-Instruct", messages=message)
print(response)






