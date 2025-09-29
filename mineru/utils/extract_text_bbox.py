#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取OCR结果中的文本和边界框信息
"""
import json
import os
from typing import List, Tuple, Dict


def extract_from_middle_json(middle_json_data) -> List[Tuple[str, List[float], int]]:
    """
    从middle.json格式的数据中提取字符级的文本和bbox信息
    
    Args:
        middle_json_data: middle.json数据，字典格式，键为字符（可能带序号后缀），值包含bbox和page_index
    
    Returns:
        List of tuples (character, bbox, page_index)，按原始字符顺序排列
    """
    import re
    
    if isinstance(middle_json_data, str):
        try:
            data = json.loads(middle_json_data)
        except json.JSONDecodeError:
            return []
    else:
        data = middle_json_data
    
    # 提取所有字符条目，并按序号排序
    char_entries = []
    
    for key, value in data.items():
        if isinstance(value, dict) and 'bbox' in value and 'page_index' in value:
            # 解析字符和序号
            match = re.match(r'^(.+?)(?:_(\d+))?$', key)
            if match:
                char = match.group(1)
                seq_num = int(match.group(2)) if match.group(2) else 0
                
                char_entries.append({
                    'char': char,
                    'bbox': value['bbox'],
                    'page_index': value['page_index'],
                    'seq_num': seq_num,
                    'original_key': key
                })
    
    # 按页面索引和序号排序，确保字符顺序正确
    char_entries.sort(key=lambda x: (x['page_index'], x['seq_num']))
    
    # 转换为元组列表
    result = []
    for entry in char_entries:
        result.append((entry['char'], entry['bbox'], entry['page_index']))
    
    return result


def remove_markdown_formatting(text: str) -> str:
    """
    移除markdown格式化字符，保留纯文本内容
    
    Args:
        text: 包含markdown格式的文本
    
    Returns:
        移除格式化字符后的纯文本
    """
    import re
    
    # 移除markdown格式化字符的正则表达式
    # 标题标记 #
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    
    # 粗体和斜体标记 **text** *text*
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
    
    # 链接 [text](url) 
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # 图片 ![alt](url)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    
    # 代码块标记 ```
    text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
    
    # 行内代码 `code`
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # 列表标记 - * +
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    
    # 有序列表标记 1. 2.
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # 引用标记 >
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # 水平线 --- ***
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
    
    # 表格分隔符 |
    text = re.sub(r'\|', '', text)
    
    # 移除多余的空白字符
    text = re.sub(r'\s+', ' ', text.strip())
    
    return text


def normalize_text_for_matching(text: str) -> str:
    """
    标准化文本用于匹配，移除多余的空白字符
    
    Args:
        text: 原始文本
        
    Returns:
        标准化后的文本
    """
    import re
    # 将多个空白字符替换为单个空格，并去除首尾空白
    return re.sub(r'\s+', ' ', text.strip())


def build_char_position_mapping(md_str: str) -> Tuple[str, Dict[int, int], Dict[int, int]]:
    """
    构建原始markdown和清理版本之间的精确字符位置映射
    
    Args:
        md_str: 原始markdown文本
        
    Returns:
        (clean_md_str, original_to_clean_map, clean_to_original_map)
    """
    import re
    
    # 先创建字符级的映射记录
    clean_chars = []
    original_to_clean_map = {}
    clean_to_original_map = {}
    
    # 逐字符处理，记录哪些字符被保留
    clean_idx = 0
    i = 0
    
    while i < len(md_str):
        char = md_str[i]
        keep_char = True
        
        # 检查各种markdown格式并跳过
        if char == '#' and (i == 0 or md_str[i-1] == '\n'):
            # 跳过标题标记到第一个空格
            while i < len(md_str) and md_str[i] in '#':
                i += 1
            # 跳过标题后的空格
            while i < len(md_str) and md_str[i] == ' ':
                i += 1
            continue
            
        elif char == '*':
            # 跳过粗体/斜体标记
            if i + 1 < len(md_str) and md_str[i + 1] == '*':
                i += 2  # 跳过**
                continue
            else:
                i += 1  # 跳过单个*
                continue
                
        elif char == '[':
            # 跳过链接的[text]部分，但保留text
            bracket_start = i
            i += 1
            link_text = ""
            while i < len(md_str) and md_str[i] != ']':
                link_text += md_str[i]
                i += 1
            if i < len(md_str):  # 跳过]
                i += 1
            # 跳过(url)部分
            if i < len(md_str) and md_str[i] == '(':
                while i < len(md_str) and md_str[i] != ')':
                    i += 1
                if i < len(md_str):  # 跳过)
                    i += 1
            # 保留链接文本
            for link_char in link_text:
                clean_chars.append(link_char)
                original_to_clean_map[bracket_start] = clean_idx
                clean_to_original_map[clean_idx] = bracket_start
                clean_idx += 1
            continue
            
        elif char == '`':
            # 跳过代码标记，保留内容
            i += 1
            continue
            
        elif char == '|':
            # 跳过表格分隔符
            i += 1
            continue
            
        elif char in '-+' and (i == 0 or md_str[i-1] == '\n'):
            # 跳过列表标记
            i += 1
            # 跳过后续空格
            while i < len(md_str) and md_str[i] == ' ':
                i += 1
            continue
            
        # 如果字符被保留
        if keep_char:
            clean_chars.append(char)
            original_to_clean_map[i] = clean_idx
            clean_to_original_map[clean_idx] = i
            clean_idx += 1
            
        i += 1
    
    clean_md_str = ''.join(clean_chars)
    return clean_md_str, original_to_clean_map, clean_to_original_map


def calculate_md_indices_for_chars(char_bbox_list: List[Tuple[str, List[float], int]], md_str: str) -> List[Tuple[str, List[float], int, int]]:
    """
    为字符级数据计算markdown位置索引，处理格式化字符差异
    
    Args:
        char_bbox_list: 字符、bbox和页号的列表（字符级）
        md_str: markdown文档内容
    
    Returns:
        包含md_index的四元组列表 (character, bbox, page_index, md_index)
    """
    if not md_str:
        return [(char, bbox, page_index, -1) for char, bbox, page_index in char_bbox_list]
    
    # 构建精确的字符位置映射
    clean_md_str, original_to_clean_map, clean_to_original_map = build_char_position_mapping(md_str)
    
    print(f"原始markdown长度: {len(md_str)}")
    print(f"清理后长度: {len(clean_md_str)}")
    print(f"清理后前100字符: {repr(clean_md_str[:100])}")
    
    result_list = []
    clean_search_index = 0
    
    # 对每个字符进行匹配
    for i, (char, bbox, page_index) in enumerate(char_bbox_list):
        md_index = -1
        
        # 跳过空白字符
        if not char.strip():
            result_list.append((char, bbox, page_index, md_index))
            continue
        
        # 在清理后的文本中查找字符
        found_clean_index = clean_md_str.find(char, clean_search_index)
        
        if found_clean_index != -1:
            # 将清理后的索引映射回原始markdown索引
            if found_clean_index in clean_to_original_map:
                md_index = clean_to_original_map[found_clean_index]
            else:
                md_index = -1
            
            # 更新搜索起始位置（重要：确保下一次搜索从当前位置之后开始）
            clean_search_index = found_clean_index + 1
            
            if i < 10:  # 调试输出前10个字符
                print(f"字符 '{char}' 在清理文本索引 {found_clean_index} -> 原始索引 {md_index}")
        else:
            if i < 10:
                print(f"字符 '{char}' 未在清理文本中找到（搜索起始位置: {clean_search_index}）")
        
        result_list.append((char, bbox, page_index, md_index))
    
    return result_list


def calculate_md_indices(text_bbox_list: List[Tuple[str, List[float], int]], md_str: str) -> List[Tuple[str, List[float], int, int]]:
    """
    计算每个文本片段在markdown文档中的位置索引（兼容原有接口）
    
    Args:
        text_bbox_list: 文本、bbox和页号的列表，按markdown阅读顺序排列
        md_str: markdown文档内容
    
    Returns:
        包含md_index的四元组列表 (text, bbox, page_index, md_index)
    """
    if not md_str:
        # 如果没有markdown内容，md_index设为-1
        return [(text, bbox, page_index, -1) for text, bbox, page_index in text_bbox_list]
    
    # 检查是否为字符级数据（大多数条目长度为1）
    char_level_ratio = sum(1 for text, _, _ in text_bbox_list if len(text) == 1) / len(text_bbox_list)
    
    if char_level_ratio > 0.8:  # 如果80%以上是单字符，使用字符级匹配
        return calculate_md_indices_for_chars(text_bbox_list, md_str)
    
    # 构建markdown清理版本和位置映射
    clean_md_str, original_to_clean_map, clean_to_original_map = build_char_position_mapping(md_str)
    
    result_list = []
    md_search_start = 0  # 在原始markdown中的搜索起始位置
    clean_search_start = 0  # 在清理后markdown中的搜索起始位置
    
    for text, bbox, page_index in text_bbox_list:
        md_index = -1
        
        if not text.strip():
            result_list.append((text, bbox, page_index, md_index))
            continue
        
        # 标准化文本用于匹配
        normalized_text = normalize_text_for_matching(text)
        
        # 策略1: 在原始markdown中按顺序搜索
        found_index = md_str.find(normalized_text, md_search_start)
        if found_index != -1:
            md_index = found_index
            md_search_start = found_index + len(normalized_text)
        else:
            # 策略2: 在清理后的markdown中搜索，然后映射回原始位置
            found_clean_index = clean_md_str.find(normalized_text, clean_search_start)
            if found_clean_index != -1:
                # 将清理后的位置映射回原始位置
                if found_clean_index in clean_to_original_map:
                    md_index = clean_to_original_map[found_clean_index]
                    # 更新搜索位置：找到的位置 + 文本长度
                    clean_search_start = found_clean_index + len(normalized_text)
                    # 同时更新原始markdown的搜索位置
                    md_search_start = md_index + len(normalized_text)
                else:
                    # 如果映射失败，尝试在原始markdown中查找
                    md_index = md_str.find(normalized_text, 0)
                    if md_index != -1:
                        md_search_start = md_index + len(normalized_text)
            else:
                # 策略3: 尝试部分匹配（处理格式化字符干扰）
                # 移除文本中的markdown格式字符后再次尝试
                clean_text = remove_markdown_formatting(text)
                if clean_text != text:
                    found_clean_index = clean_md_str.find(clean_text, clean_search_start)
                    if found_clean_index != -1:
                        if found_clean_index in clean_to_original_map:
                            md_index = clean_to_original_map[found_clean_index]
                            clean_search_start = found_clean_index + len(clean_text)
                            md_search_start = md_index + len(clean_text)
        
        result_list.append((text, bbox, page_index, md_index))
    
    return result_list


def extract_text_bbox_from_spans(spans: List[Dict], page_index: int, table_bbox: List[float] = None) -> List[Tuple[str, List[float], int]]:
    """从spans中提取文本和bbox
    
    Args:
        spans: span列表
        page_index: 页面索引
        table_bbox: 表格的全局bbox坐标，用于转换表格内文本的相对坐标为绝对坐标
    """
    results = []
    for span in spans:
        if 'content' in span and span['content'].strip():
            content = span['content'].strip()
            bbox = span.get('bbox', [])
            if bbox:
                results.append((content, bbox, page_index))
        
        # 处理table_cell_bboxes（表格单元格）
        if 'table_cell_bboxes' in span:
            # 获取表格OCR时的宽高信息
            
            for cell in span['table_cell_bboxes']:
                if 'text' in cell and cell['text'].strip():
                    text = cell['text'].strip()
                    bbox = cell.get('bbox', [])
                    ocr_hw = cell.get('ocr_hw')
                    if bbox and len(bbox) >= 4:
                        # 使用专门的转换函数处理表格内文字坐标
                        if table_bbox and len(table_bbox) >= 4:
                            global_bbox = convert_table_cell_bbox_to_global(bbox, table_bbox, ocr_hw)
                            results.append((text, global_bbox, page_index))
                        else:
                            # 没有表格bbox信息，使用原始坐标
                            results.append((text, bbox, page_index))
    
    return results


def extract_text_bbox_from_lines(lines: List[Dict], page_index: int, table_bbox: List[float] = None) -> List[Tuple[str, List[float], int]]:
    """从lines中提取文本和bbox"""
    results = []
    for line in lines:
        if 'spans' in line:
            results.extend(extract_text_bbox_from_spans(line['spans'], page_index, table_bbox))
    return results


def extract_text_bbox_from_blocks(blocks: List[Dict], page_index: int, table_bbox: List[float] = None) -> List[Tuple[str, List[float], int]]:
    """从blocks中提取文本和bbox"""
    results = []
    for block in blocks:
        if 'lines' in block:
            results.extend(extract_text_bbox_from_lines(block['lines'], page_index, table_bbox))
    return results


def extract_text_bbox_from_preproc_blocks(preproc_blocks: List[Dict], page_index: int) -> List[Tuple[str, List[float], int]]:
    """从preproc_blocks中提取文本和bbox"""
    results = []
    for block in preproc_blocks:
        # 检查是否是表格块
        is_table = block.get('type') == 'table'
        table_bbox = block.get('bbox', []) if is_table else None
        
        # 处理普通文本块
        if 'lines' in block:
            results.extend(extract_text_bbox_from_lines(block['lines'], page_index, table_bbox))
        
        # 处理表格块中的子块
        if 'blocks' in block:
            for sub_block in block['blocks']:
                # 对于表格内的子块，传递表格的bbox信息
                if 'lines' in sub_block:
                    results.extend(extract_text_bbox_from_lines(sub_block['lines'], page_index, table_bbox))
    
    return results


def is_middle_json_format(json_data) -> bool:
    """
    判断输入数据是否为middle.json格式（字符级映射）
    
    Args:
        json_data: JSON数据
        
    Returns:
        bool: True如果是middle.json格式
    """
    if not isinstance(json_data, dict):
        return False
    
    # 检查是否有典型的middle.json结构：字符键 + bbox/page_index值
    sample_keys = list(json_data.keys())[:10]  # 检查前10个键
    
    middle_json_indicators = 0
    for key in sample_keys:
        value = json_data.get(key)
        if (isinstance(value, dict) and 
            'bbox' in value and 
            'page_index' in value and 
            len(key) <= 3):  # 字符键通常很短
            middle_json_indicators += 1
    
    # 如果超过一半的样本符合middle.json格式，认为是middle.json
    return middle_json_indicators / len(sample_keys) > 0.5


def extract_all_text_bbox_with_md(json_data, md_str: str = None) -> List[Tuple[str, List[float], int, int]]:
    """
    从JSON文件中提取所有文本和bbox信息，并计算markdown位置索引
    自动识别数据格式（OCR结果格式 vs middle.json格式）
    
    Args:
        json_data: JSON数据，可以是字典对象或JSON字符串
        md_str: markdown文档内容，用于计算md_index
    
    Returns:
        List of tuples (text, bbox, page_index, md_index)
    """
    if isinstance(json_data, str):
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError:
            return []
    else:
        data = json_data
    
    # 判断数据格式并使用相应的提取方法
    if is_middle_json_format(data):
        # middle.json格式：直接提取字符级数据
        text_bbox_list = extract_from_middle_json(data)
    else:
        # 传统OCR结果格式：使用原有的提取方法
        text_bbox_list = extract_all_text_bbox(data)
    
    # 计算markdown位置索引
    return calculate_md_indices(text_bbox_list, md_str or "")


def extract_all_text_bbox(json_data) -> List[Tuple[str, List[float], int]]:
    """
    从OCR结果JSON文件中提取所有文本和bbox信息
    
    Args:
        json_data: JSON数据，可以是字典对象或JSON字符串
    
    Returns:
        List of tuples (text, bbox, page_index)
    """
    # 如果输入是字符串，先解析为字典
    if isinstance(json_data, str):
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            print(f"错误: JSON解析失败 - {str(e)}")
            return []
    elif isinstance(json_data, dict):
        data = json_data
    else:
        print(f"错误: 不支持的数据类型 {type(json_data)}")
        return []
    
    all_text_bbox = []
    
    # 遍历pdf_info中的每个页面
    for page_info in data.get('pdf_info', []):
        # 获取页面索引，如果没有则使用0作为默认值
        page_index = page_info.get('page_idx', 0)
        if page_index == 0:
            page_index = page_info.get('page_num', 0)
        
        if 'preproc_blocks' in page_info:
            page_results = extract_text_bbox_from_preproc_blocks(page_info['preproc_blocks'], page_index)
            all_text_bbox.extend(page_results)
    
    return all_text_bbox


def save_text_bbox_mapping(text_bbox_list: List[Tuple[str, List[float], int, int]]):
    """
    保存文本和bbox映射到文件
    
    Args:
        text_bbox_list: 文本、bbox、页号和md_index的列表
        output_file: 输出文件路径
    """
    # 创建映射字典
    text_bbox_mapping = {}
    for i, (text, bbox, page_index, md_index) in enumerate(text_bbox_list):
        # 如果有重复的文本，添加索引以区分
        key = text
        counter = 1
        while key in text_bbox_mapping:
            key = f"{text}_{counter}"
            counter += 1
        text_bbox_mapping[key] = {
            "bbox": bbox,
            "page_index": page_index,
            "md_index": md_index
        }
    
    # 保存为JSON文件

    return json.dumps(text_bbox_mapping, ensure_ascii=False, indent=2)


def print_text_bbox_summary(text_bbox_list: List[Tuple[str, List[float], int, int]]):
    """打印文本和bbox的摘要信息"""
    print(f"\n=== 提取结果摘要 ===")
    print(f"总共提取到 {len(text_bbox_list)} 个文本-bbox对")
    
    print(f"\n前10个示例:")
    for i, (text, bbox, page_index, md_index) in enumerate(text_bbox_list[:10]):
        text_type = "表格" if any(keyword in text for keyword in ['名称：', '统一社会信用代码', '项目名称', '单价', '数量', '金额', '税率', '税额']) else "普通"
        md_pos = f"MD:{md_index}" if md_index >= 0 else "MD:未找到"
        print(f"{i+1:2d}. 页面{page_index} | {text_type} | {md_pos} | 文本: '{text}' | bbox: {bbox}")
    
    if len(text_bbox_list) > 10:
        print(f"... 还有 {len(text_bbox_list) - 10} 个")


def convert_table_cell_bbox_to_global(cell_bbox, table_bbox, ocr_hw=None, debug=True):
    """
    表格内文字坐标转换：全局坐标 = 缩放后的相对坐标 + 表格左上角坐标
    
    根据crop_img函数的实现：
    1. 表格裁剪：table_img, _ = crop_img(table_res, pil_img)
       - 使用默认参数crop_paste_x=0, crop_paste_y=0
       - 从原图裁剪出表格区域：input_img[crop_ymin:crop_ymax, crop_xmin:crop_xmax]
       - 裁剪后图像的(0,0)对应原图的(crop_xmin, crop_ymin)
    
    2. 表格识别在裁剪后图像上进行，返回相对坐标
    
    3. 如果提供了ocr_hw(表示OCR时表格的宽高)，先根据比例缩放坐标
    
    4. 转换公式：
       global_x = (relative_x * table_width / ocr_width) + table_x1
       global_y = (relative_y * table_height / ocr_height) + table_y1
    
    Args:
        cell_bbox: 表格内文字的相对坐标 [x1, y1, x2, y2]
        table_bbox: 表格的全局坐标 [x1, y1, x2, y2]
        ocr_hw: OCR时表格的宽高 [height, width]，如果提供则进行缩放处理
        debug: 是否输出调试信息
    
    Returns:
        全局坐标 [x1, y1, x2, y2]
    """
    if not cell_bbox or len(cell_bbox) < 4:
        return cell_bbox
    
    if not table_bbox or len(table_bbox) < 4:
        # 没有表格bbox信息，直接返回原始坐标
        return cell_bbox
    
    # 表格在原图中的左上角位置和宽高
    table_x1, table_y1 = table_bbox[0], table_bbox[1]
    table_width = table_bbox[2] - table_bbox[0]
    table_height = table_bbox[3] - table_bbox[1]
    
    # 应用坐标转换
    if ocr_hw and len(ocr_hw) == 2:
        # 如果提供了OCR时的宽高，先进行缩放处理
        ocr_height, ocr_width = ocr_hw
        
        # 缩放系数
        scale_x = table_width / ocr_width
        scale_y = table_height / ocr_height
        
        # 缩放并转换坐标
        global_bbox = [
            cell_bbox[0] * scale_x + table_x1,
            cell_bbox[1] * scale_y + table_y1,
            cell_bbox[2] * scale_x + table_x1,
            cell_bbox[3] * scale_y + table_y1
        ]
        
        if debug:
            print(f"      表格bbox: {table_bbox}")
            print(f"      表格宽高: {table_width} x {table_height}")
            print(f"      OCR宽高: {ocr_width} x {ocr_height}")
            print(f"      缩放系数: x={scale_x:.4f}, y={scale_y:.4f}")
            print(f"      相对坐标: {cell_bbox}")
            print(f"      缩放后全局坐标: {global_bbox}")
    else:
        # 没有提供OCR宽高，使用原始转换公式
        global_bbox = [
            cell_bbox[0] + table_x1,
            cell_bbox[1] + table_y1,
            cell_bbox[2] + table_x1,
            cell_bbox[3] + table_y1
        ]
        
        if debug:
            print(f"      表格bbox: {table_bbox}")
            print(f"      表格左上角: ({table_x1}, {table_y1})")
            print(f"      相对坐标: {cell_bbox}")
            print(f"      全局坐标: {global_bbox}")
    
    return global_bbox


def analyze_coordinate_transformation(json_file_path: str, debug=False):
    """
    分析坐标转换，对比不同的转换方式
    """
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("=== 坐标转换分析 ===")
    
    for page_info in data.get('pdf_info', []):
        page_index = page_info.get('page_id', 0)
        
        for block in page_info.get('preproc_blocks', []):
            if block.get('type') == 'table':
                table_bbox = block.get('bbox', [])
                print(f"\n页面 {page_index}, 表格bbox: {table_bbox}")
                
                # 查找表格内的文字
                for sub_block in block.get('blocks', []):
                    for line in sub_block.get('lines', []):
                        for span in line.get('spans', []):
                            if 'table_cell_bboxes' in span:
                                print(f"  找到表格文字数据，共 {len(span['table_cell_bboxes'])} 个单元格")
                                
                                # 分析前几个单元格的坐标
                                for i, cell in enumerate(span['table_cell_bboxes'][:5]):
                                    if 'text' in cell and 'bbox' in cell:
                                        text = cell['text']
                                        cell_bbox = cell['bbox']
                                        print(f"    单元格{i+1}: '{text}'")
                                        print(f"      原始坐标: {cell_bbox}")
                                        
                                        global_bbox = convert_table_cell_bbox_to_global(
                                            cell_bbox, table_bbox, debug=True
                                        )
                                        print(f"      最终坐标: {global_bbox}")
                                        print()
                                
                                break  # 只处理第一个span中的表格数据

def extract(input_data, md_str: str):
    """
    提取文本和bbox信息
    
    Args:
        input_data: 可以是文件路径(str)、JSON字符串(str)或字典对象(dict)
    
    Returns:
        JSON格式的文本-bbox映射字符串
    """
    try:
        # 判断输入类型并相应处理
        if isinstance(input_data, str):
            # 检查是否是文件路径
            if input_data.endswith('.json') and os.path.exists(input_data):
                # 是文件路径，读取文件
                with open(input_data, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
            else:
                # 假设是JSON字符串
                try:
                    json_data = json.loads(input_data)
                except json.JSONDecodeError:
                    print(f"错误: 输入既不是有效的文件路径也不是有效的JSON字符串")
                    return None
        elif isinstance(input_data, dict):
            # 已经是字典对象
            json_data = input_data
        else:
            print(f"错误: 不支持的输入类型 {type(input_data)}")
            return None
        
        # 提取所有文本和bbox，并计算markdown位置索引
        text_bbox_with_md = extract_all_text_bbox_with_md(json_data, md_str)
        
        # 打印摘要
        print_text_bbox_summary(text_bbox_with_md)
        
        return save_text_bbox_mapping(text_bbox_with_md)
        
    except FileNotFoundError:
        print(f"错误: 找不到文件 {input_data}")
        return None
    except json.JSONDecodeError:
        print(f"错误: 文件或字符串不是有效的JSON格式")
        return None
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

