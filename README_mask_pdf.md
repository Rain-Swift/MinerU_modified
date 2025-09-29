# PDF字段遮挡工具

这个工具可以根据字符级JSON文件，在PDF中遮挡指定的字符串区域。

## 功能特点

- 支持基于字符级bbox精确定位文本
- 支持遮挡多个字符串
- 支持自定义遮挡颜色
- 支持详细日志输出
- 自动处理字符下标（如 "张_1", "张_2"）

## 安装依赖

```bash
pip install PyMuPDF loguru
```

## 使用方法

### 基本用法

```bash
python mask_pdf_fields.py <PDF文件> <JSON文件> <字符串1> <字符串2> ... -o <输出文件>
```

### 参数说明

- `pdf_path`: 原始PDF文件路径
- `json_path`: 字符级JSON文件路径（由MinerU生成）
- `strings`: 要遮挡的字符串列表（可多个）
- `-o, --output`: 输出PDF文件路径（必需）
- `--color`: 遮挡颜色 RGB值 (0-1)，默认黑色 [0, 0, 0]
- `--verbose, -v`: 详细输出模式

### 使用示例

#### 1. 遮挡敏感数据（黑色遮挡）

```bash
python mask_pdf_fields.py \
    mineru_in/敏感数据.pdf \
    mineru_out/敏感数据/auto/敏感数据_middle.json \
    "张三" "李娜" "王磊" \
    -o masked_sensitive_data.pdf
```

#### 2. 遮挡合同信息（红色遮挡）

```bash
python mask_pdf_fields.py \
    mineru_in/广州五舟公司销售合同.pdf \
    mineru_out/广州五舟公司销售合同/auto/广州五舟公司销售合同_middle.json \
    "白云" "谢高辉" "黄允犬" \
    -o 合同_masked.pdf \
    --color 1 0 0
```

#### 3. 详细输出模式

```bash
python mask_pdf_fields.py \
    mineru_in/敏感数据.pdf \
    mineru_out/敏感数据/auto/敏感数据_middle.json \
    "张三" "李娜" \
    -o masked_output.pdf \
    --verbose
```

## 输出示例

```
✓ '张三': 1 处
✓ '李娜': 1 处
✓ '王磊': 1 处
总共遮挡了 3 处字符串
```

## 工作原理

1. **加载数据**: 读取PDF文件和字符级JSON文件
2. **字符串匹配**: 在字符级数据中查找目标字符串的所有出现位置
3. **bbox计算**: 根据字符位置计算字符串的边界框
4. **遮挡绘制**: 在PDF对应位置绘制遮挡矩形
5. **保存结果**: 输出遮挡后的PDF文件

## 注意事项

- 确保PDF文件和JSON文件路径正确
- 字符串匹配区分大小写
- 遮挡颜色使用RGB值，范围0-1
- 如果字符串未找到，会显示"未找到"提示

## 错误处理

- 文件不存在时会给出明确错误信息
- 字符串未找到时会记录警告但不中断处理
- 处理过程中的异常会被捕获并记录

## 技术细节

- 使用PyMuPDF进行PDF操作
- 支持多页面PDF处理
- 自动处理字符下标后缀（如 "张_1", "张_2"）
- 精确计算字符串边界框
