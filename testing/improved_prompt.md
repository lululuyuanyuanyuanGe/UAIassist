# Improved Prompt for Table Header Extraction

## Original Prompt Issues:
- Vague task description
- Unclear handling of nested structures 
- No examples provided
- Missing edge case guidance
- Ambiguous output format requirements

## Improved Prompt:

```
# Role & Context
你是一位专业的表格结构解析专家，擅长将复杂的 JSON 层次结构转换为标准的 Markdown 表格格式。

# Task Description
将提供的 JSON 数据转换为 Markdown 表格头部，保持原有的层次结构和合并关系。

# Input Format
JSON 数据结构说明：
- 键名：表头字段名
- 值类型：
  - 字符串：叶子节点，表示最终列标题
  - 对象：父节点，包含子级表头结构
  - 数组：同级并列的表头项

# Output Requirements

## Format Specifications:
1. **仅输出 Markdown 表格头部**（不包含数据行）
2. **使用标准 Markdown 表格语法**
3. **保持层次结构**：多级表头需要正确显示层级关系
4. **处理合并单元格**：使用适当的列跨度表示法

## Structure Rules:
- 第一行：顶级表头（如果存在多级结构）
- 后续行：按层级依次展开子表头
- 最后一行：分隔符行（|---|---|---|）

## Example Input & Output:

### Input:
```json
{
  "基本信息": {
    "姓名": "",
    "年龄": "",
    "性别": ""
  },
  "联系方式": {
    "电话": "",
    "邮箱": ""
  },
  "备注": ""
}
```

### Expected Output:
```markdown
| 基本信息 | | | 联系方式 | | 备注 |
|----------|----------|----------|----------|----------|------|
| 姓名 | 年龄 | 性别 | 电话 | 邮箱 | 备注 |
|------|------|------|------|------|------|
```

# Processing Instructions

## Step-by-Step Process:
1. **解析 JSON 结构**：识别层级关系和嵌套深度
2. **计算列跨度**：确定每个父节点需要跨越的列数
3. **构建表头矩阵**：创建多行表头结构
4. **生成 Markdown**：转换为标准格式

## Edge Cases Handling:
- **空值处理**：跳过空键或null值
- **不规则结构**：自动对齐缺失的层级
- **单层结构**：直接输出为单行表头
- **深度嵌套**：支持任意层级深度

# Output Constraints
- **仅输出结果**：不包含解释、注释或额外说明
- **格式严格**：严格遵循 Markdown 表格语法
- **编码规范**：使用 UTF-8 编码，保持中文字符正确显示

# Quality Criteria
✅ 层次结构完整保留
✅ 合并单元格正确表示
✅ Markdown 语法标准
✅ 列对齐规整
✅ 无多余空白或格式错误

请根据以上要求处理提供的 JSON 数据。
```

## Key Improvements Made:

### 1. **Clearer Structure**
- Added role definition and context
- Separated input/output specifications
- Used clear headings and bullet points

### 2. **Concrete Examples**
- Provided specific input JSON example
- Showed expected output format
- Demonstrated multi-level header handling

### 3. **Detailed Requirements**
- Specified exact Markdown syntax requirements
- Added step-by-step processing instructions
- Included edge case handling guidelines

### 4. **Quality Assurance**
- Added quality criteria checklist
- Specified encoding and formatting requirements
- Included validation points

### 5. **Better Formatting**
- Used consistent formatting throughout
- Added visual separators and emphasis
- Made instructions scannable with clear hierarchy

### 6. **Practical Guidance**
- Added processing steps for complex cases
- Provided specific handling for edge cases
- Included format validation criteria

This improved prompt is more likely to produce consistent, high-quality results because it:
- Removes ambiguity through concrete examples
- Provides clear processing steps
- Specifies exact output format requirements
- Includes quality validation criteria
- Handles edge cases explicitly 