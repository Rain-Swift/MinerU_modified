#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据bbox映射信息遮挡PDF中的指定字段 - API接口

主要功能:
1. get_fields_bbox_list() - 从mapping文件中搜索指定字段列表，返回对应的bbox列表
2. mask_pdf_fields() - 在PDF中遮挡指定字段列表
3. list_available_fields() - 列出映射文件中所有可用的字段

"""
import json
from typing import List, Tuple, Dict, Any
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
from pathlib import Path


def load_bbox_mapping(mapping_file: str) -> Dict[str, Any]:
    """
    加载bbox映射文件
    
    Args:
        mapping_file: mapping JSON文件路径
    
    Returns:
        字典格式的映射数据
    """
    with open(mapping_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_char_width_ratio(char: str) -> float:
    """
    获取字符的相对宽度比例
    
    Args:
        char: 单个字符
    
    Returns:
        字符宽度比例（以中文字符为1.0基准）
    """
    import unicodedata
    
    # 中文字符（CJK统一表意文字）
    if '\u4e00' <= char <= '\u9fff':
        return 1.0
    # 中文标点符号
    elif '\u3000' <= char <= '\u303f' or '\uff00' <= char <= '\uffef':
        return 0.65
    # 全角字符
    elif unicodedata.east_asian_width(char) in ('F', 'W'):
        return 1.0
    # 数字
    elif char.isdigit():
        return 0.5
    # 英文字母
    elif char.isalpha() and ord(char) < 128:  # ASCII字母
        return 0.6
    # 常见半角标点符号
    elif char in '.,!?;:()[]{}"\'-_/\\@#$%^&*+=<>|`~':
        return 0.5
    # 空格
    elif char.isspace():
        return 0.5
    # 其他字符，根据East Asian Width属性判断
    elif unicodedata.east_asian_width(char) in ('Na', 'H'):
        return 0.5  # 窄字符和半角字符
    else:
        return 0.8  # 未知字符，给一个中等宽度


def calculate_text_width_ratios(text: str) -> List[float]:
    """
    计算文本中每个字符的累积宽度比例
    
    Args:
        text: 文本字符串
    
    Returns:
        每个字符位置的累积宽度比例列表
    """
    if not text:
        return []
    
    char_widths = [get_char_width_ratio(char) for char in text]
    total_width = sum(char_widths)
    
    # 计算累积宽度比例
    cumulative_ratios = [0.0]  # 起始位置
    cumulative_width = 0.0
    
    for width in char_widths:
        cumulative_width += width
        cumulative_ratios.append(cumulative_width / total_width if total_width > 0 else 0)
    
    return cumulative_ratios


def calculate_substring_bbox(full_text: str, substring: str, full_bbox: List[float]) -> List[float]:
    """
    计算子字符串在完整bbox中的位置，考虑中文和英文字符的宽度差异
    
    Args:
        full_text: 完整文本
        substring: 子字符串
        full_bbox: 完整文本的bbox [x0, y0, x1, y1]
    
    Returns:
        子字符串的bbox [x0, y0, x1, y1]
    """
    if len(full_bbox) < 4:
        return full_bbox
    
    # 找到子字符串在完整文本中的位置
    start_idx = full_text.lower().find(substring.lower())
    if start_idx == -1:
        return full_bbox
    
    end_idx = start_idx + len(substring)
    
    # 计算每个字符位置的累积宽度比例
    cumulative_ratios = calculate_text_width_ratios(full_text)
    
    if len(cumulative_ratios) <= end_idx:
        # 如果计算出错，回退到简单的线性计算
        text_len = len(full_text)
        start_ratio = start_idx / text_len if text_len > 0 else 0
        end_ratio = end_idx / text_len if text_len > 0 else 1
    else:
        # 使用基于字符宽度的精确计算
        start_ratio = cumulative_ratios[start_idx]
        end_ratio = cumulative_ratios[end_idx]
    
    x0, y0, x1, y1 = full_bbox[:4]
    width = x1 - x0
    
    # 计算子字符串的精确bbox
    sub_x0 = x0 + width * start_ratio
    sub_x1 = x0 + width * end_ratio
    
    return [sub_x0, y0, sub_x1, y1]


def find_cross_segment_matches(mapping_data: Dict[str, Any], field_name: str) -> List[Tuple[List[float], int, str]]:
    """
    查找跨段匹配
    
    Args:
        mapping_data: 映射数据
        field_name: 要查找的字段名
    
    Returns:
        匹配的bbox列表，每个匹配的段都有独立的bbox
    """
    matches = []
    field_lower = field_name.lower()
    
    # 按页面分组
    pages_data = {}
    for key, value in mapping_data.items():
        page_index = value.get('page_index', 0)
        if page_index not in pages_data:
            pages_data[page_index] = []
        pages_data[page_index].append((key, value))
    
    # 在每个页面内查找跨段匹配
    for page_index, page_items in pages_data.items():
        # 为了避免匹配到无关内容，我们采用更保守的策略：
        # 1. 寻找包含字段名任意连续子串的文本段
        # 2. 确保这些子串能够完整覆盖目标字段
        
        # 生成字段名的所有可能的连续子串（至少2个字符）
        field_substrings = []
        for i in range(len(field_name)):
            for j in range(i + 2, len(field_name) + 1):  # 至少2个字符
                substring = field_name[i:j]
                field_substrings.append(substring)
        
        # 对每个子串，在映射数据中查找匹配
        matched_segments = {}  # {substring: [(bbox, original_key), ...]}
        
        for substring in field_substrings:
            substring_lower = substring.lower()
            for key, value in page_items:
                key_lower = key.lower()
                if substring_lower in key_lower:
                    bbox = value.get('bbox', [])
                    if bbox:
                        # 计算子字符串的精确bbox
                        precise_bbox = calculate_substring_bbox(key, substring, bbox)
                        if substring not in matched_segments:
                            matched_segments[substring] = []
                        matched_segments[substring].append((precise_bbox, key))
        
        # 尝试找到能够覆盖整个字段名的最小子串集合
        covered_positions = set()
        selected_matches = []
        
        # 按子串长度降序排序，优先选择较长的匹配
        sorted_substrings = sorted(matched_segments.keys(), key=len, reverse=True)
        
        for substring in sorted_substrings:
            start_pos = field_lower.find(substring.lower())
            if start_pos != -1:
                end_pos = start_pos + len(substring)
                substring_positions = set(range(start_pos, end_pos))
                
                # 如果这个子串覆盖了新的位置，则选择它
                if not substring_positions.issubset(covered_positions):
                    covered_positions.update(substring_positions)
                    # 选择第一个匹配的bbox（可以优化为选择最佳的）
                    if matched_segments[substring]:
                        bbox, original_key = matched_segments[substring][0]
                        selected_matches.append((bbox, page_index, f"跨段匹配: {original_key} -> {substring}"))
        
        # 只有当覆盖了整个字段名时，才添加匹配结果
        if len(covered_positions) == len(field_name):
            matches.extend(selected_matches)
    
    return matches


def merge_bboxes(bboxes: List[List[float]]) -> List[float]:
    """
    合并多个bbox为一个包围盒
    
    Args:
        bboxes: bbox列表
    
    Returns:
        合并后的bbox [x0, y0, x1, y1]
    """
    if not bboxes:
        return []
    
    valid_bboxes = [bbox for bbox in bboxes if len(bbox) >= 4]
    if not valid_bboxes:
        return []
    
    x0_min = min(bbox[0] for bbox in valid_bboxes)
    y0_min = min(bbox[1] for bbox in valid_bboxes)
    x1_max = max(bbox[2] for bbox in valid_bboxes)
    y1_max = max(bbox[3] for bbox in valid_bboxes)
    
    return [x0_min, y0_min, x1_max, y1_max]


def find_fields_bbox(mapping_data: Dict[str, Any], field_list: List[str], fuzzy_match: bool = False) -> List[Tuple[List[float], int, str]]:
    """
    查找指定字段列表的bbox信息，支持精确子字符串匹配和跨段匹配
    
    Args:
        mapping_data: 映射数据
        field_list: 要查找的字段名列表
        fuzzy_match: 是否使用模糊匹配
    
    Returns:
        匹配字段的bbox、页号和字段名列表 [(bbox, page_index, field_name), ...]
    """
    matches = []
    
    for field_name in field_list:
        field_matches = []
        
        # 1. 精确匹配
        for key, value in mapping_data.items():
            if key == field_name:
                bbox = value.get('bbox', [])
                page_index = value.get('page_index', 0)
                if bbox:
                    field_matches.append((bbox, page_index, f"精确匹配: {key}"))
        
        # 2. 子字符串匹配 - 计算精确的子bbox
        if not field_matches or fuzzy_match:
            for key, value in mapping_data.items():
                if field_name.lower() in key.lower() and key != field_name:
                    bbox = value.get('bbox', [])
                    page_index = value.get('page_index', 0)
                    if bbox:
                        # 计算子字符串的精确bbox
                        precise_bbox = calculate_substring_bbox(key, field_name, bbox)
                        field_matches.append((precise_bbox, page_index, f"子串匹配: {key} -> {field_name}"))
        
        # 3. 跨段匹配
        if not field_matches or fuzzy_match:
            cross_matches = find_cross_segment_matches(mapping_data, field_name)
            field_matches.extend(cross_matches)
        
        # 4. 如果启用模糊匹配，添加所有包含该字段的条目
        if fuzzy_match:
            for key, value in mapping_data.items():
                if field_name.lower() in key.lower():
                    bbox = value.get('bbox', [])
                    page_index = value.get('page_index', 0)
                    if bbox:
                        # 检查是否已经添加过
                        already_added = any(match[2].endswith(key) for match in field_matches)
                        if not already_added:
                            precise_bbox = calculate_substring_bbox(key, field_name, bbox)
                            field_matches.append((precise_bbox, page_index, f"模糊匹配: {key} -> {field_name}"))
        
        matches.extend(field_matches)
    
    return matches


def mask_pdf_fields(pdf_path: str, field_list: List[str], mapping_file: str, output_path: str, 
                   mask_color: Tuple[float, float, float] = (0, 0, 0), 
                   fuzzy_match: bool = False) -> bool:
    """
    在PDF中遮挡指定字段列表
    
    Args:
        pdf_path: 原始PDF文件路径
        field_list: 要遮挡的字段名列表
        mapping_file: bbox映射文件路径
        output_path: 输出PDF文件路径
        mask_color: 遮挡颜色，RGB格式 (0-1范围)
        fuzzy_match: 是否使用模糊匹配
    
    Returns:
        是否成功遮挡
    """
    if fitz is None:
        raise ImportError("缺少PyMuPDF库，请安装: pip install PyMuPDF")
    
    try:
        # 加载映射数据
        mapping_data = load_bbox_mapping(mapping_file)
        
        # 使用增强的查找逻辑
        matches = find_fields_bbox(mapping_data, field_list, fuzzy_match)
        
        if not matches:
            print(f"警告: 未找到字段 {field_list} 的bbox信息")
            return False
        
        # 打开PDF文档
        doc = fitz.open(pdf_path)
        
        masked_count = 0
        
        # 对每个匹配的bbox进行遮挡
        for bbox, page_index, match_info in matches:
            if page_index >= len(doc):
                print(f"警告: 页面索引 {page_index} 超出文档范围")
                continue
            
            page = doc[page_index]
            
            # 转换bbox格式：[x0, y0, x1, y1]
            if len(bbox) >= 4:
                x0, y0, x1, y1 = bbox[:4]
                
                # 计算左右边界扩展10%
                width = x1 - x0
                expand_width = width * 0.15  # 10%扩展
                
                # 扩展左右边界
                expanded_x0 = x0 - expand_width
                expanded_x1 = x1 + expand_width
                
                # 确保扩展后的坐标不超出页面边界
                page_rect = page.rect
                expanded_x0 = max(expanded_x0, page_rect.x0)
                expanded_x1 = min(expanded_x1, page_rect.x1)
                
                rect = fitz.Rect(expanded_x0, y0, expanded_x1, y1)
                
                # 添加遮挡矩形
                page.draw_rect(rect, color=mask_color, fill=mask_color)
                masked_count += 1
                print(f"已遮挡页面 {page_index} - {match_info}: 原始bbox {bbox} -> 扩展bbox [{expanded_x0:.2f}, {y0}, {expanded_x1:.2f}, {y1}]")
        
        # 保存修改后的PDF
        doc.save(output_path)
        doc.close()
        
        print(f"成功遮挡了 {masked_count} 个区域")
        print(f"输出文件已保存到: {output_path}")
        return True
        
    except Exception as e:
        print(f"遮挡过程中出现错误: {str(e)}")
        return False


def list_available_fields(mapping_file: str, search_term: str = None):
    """
    列出映射文件中所有可用的字段
    
    Args:
        mapping_file: 映射文件路径
        search_term: 搜索关键词，如果提供则只显示包含该关键词的字段
    """
    try:
        mapping_data = load_bbox_mapping(mapping_file)
        
        print(f"\n=== 可用字段列表 ===")
        print(f"共找到 {len(mapping_data)} 个字段")
        
        if search_term:
            print(f"搜索关键词: '{search_term}'")
            filtered_fields = [key for key in mapping_data.keys() 
                             if search_term.lower() in key.lower()]
        else:
            filtered_fields = list(mapping_data.keys())
        
        if not filtered_fields:
            print("没有找到匹配的字段")
            return
        
        print(f"\n匹配的字段 ({len(filtered_fields)} 个):")
        for i, field in enumerate(filtered_fields, 1):
            page_index = mapping_data[field].get('page_index', 0)
            bbox = mapping_data[field].get('bbox', [])
            print(f"{i:3d}. 页面{page_index} | '{field}' | bbox: {bbox}")
            
    except Exception as e:
        print(f"读取映射文件时出现错误: {str(e)}")


def get_fields_bbox_list(mapping_file: str, field_list: List[str], fuzzy_match: bool = False) -> List[Tuple[List[float], int, str]]:
    """
    从mapping文件中搜索指定字段列表，返回对应的bbox列表
    支持精确子字符串匹配和跨段匹配
    
    Args:
        mapping_file: bbox映射文件路径
        field_list: 要查找的字段名列表
        fuzzy_match: 是否使用模糊匹配
    
    Returns:
        匹配字段的bbox、页号和匹配信息列表 [(bbox, page_index, match_info), ...]
    """
    try:
        # 加载映射数据
        mapping_data = load_bbox_mapping(mapping_file)
        
        # 使用增强的查找逻辑
        matches = find_fields_bbox(mapping_data, field_list, fuzzy_match)
        
        return matches
        
    except Exception as e:
        print(f"读取映射文件时出现错误: {str(e)}")
        return []


def parse_color(color_str: str) -> Tuple[float, float, float]:
    """
    解析颜色字符串为RGB元组
    
    Args:
        color_str: 颜色字符串，支持预定义颜色名或RGB格式
    
    Returns:
        RGB颜色元组 (0-1范围)
    """
    color_map = {
        "black": (0, 0, 0),
        "white": (1, 1, 1),
        "red": (1, 0, 0),
        "blue": (0, 0, 1),
        "green": (0, 1, 0),
        "yellow": (1, 1, 0),
    }
    
    if color_str in color_map:
        return color_map[color_str]
    else:
        # 尝试解析RGB格式
        try:
            rgb_values = [int(x.strip()) for x in color_str.split(',')]
            if len(rgb_values) == 3 and all(0 <= x <= 255 for x in rgb_values):
                return tuple(x / 255.0 for x in rgb_values)
            else:
                raise ValueError("RGB值必须在0-255范围内")
        except:
            raise ValueError(f"无效的颜色格式 '{color_str}'。支持的颜色: black, white, red, blue, green, yellow 或RGB格式: '255,0,0'")


# 示例使用方法
if __name__ == "__main__":
    # 示例：测试增强的bbox搜索功能
    mapping_file = "/home/czr/MinerU_2/mineru_out/广州五舟公司销售合同/auto/广州五舟公司销售合同_middle.json"
    
    # 测试字符宽度计算
    test_text = "WZ-NY-DZ-OEM-20231008002"
    print(f"测试文本: {test_text}")
    ratios = calculate_text_width_ratios(test_text)
    print(f"字符宽度比例: {ratios}")
    
    # 测试子字符串bbox计算
    test_bbox = [100, 200, 300, 220]  # 示例bbox
    substring = "深圳云创"
    result_bbox = calculate_substring_bbox(test_text, substring, test_bbox)
    print(f"'{substring}' 在 '{test_text}' 中的bbox: {result_bbox}")
    
    # 测试不同类型的匹配
    test_cases = [
        ["号码"],  # 子字符串匹配，应该能在"发票号码"中找到"号码"
        ["名称"],  # 子字符串匹配，应该能在"名称：深圳云创数安科技有限公司"中找到"名称"
        ["深圳"],  # 子字符串匹配
    ]
    
    try:
        for field_list in test_cases:
            print(f"\n=== 测试字段: {field_list} ===")
            
            # 测试精确匹配
            bbox_list = get_fields_bbox_list(mapping_file, field_list, fuzzy_match=False)
            print(f"精确匹配结果 ({len(bbox_list)} 个):")
            for bbox, page_index, match_info in bbox_list:
                print(f"  {match_info}")
                print(f"    页面: {page_index}, bbox: {bbox}")
            
            # 测试模糊匹配
            bbox_list_fuzzy = get_fields_bbox_list(mapping_file, field_list, fuzzy_match=True)
            print(f"模糊匹配结果 ({len(bbox_list_fuzzy)} 个):")
            for bbox, page_index, match_info in bbox_list_fuzzy:
                print(f"  {match_info}")
                print(f"    页面: {page_index}, bbox: {bbox}")
        
        # 示例：遮挡PDF字段
        print("\n=== PDF遮挡示例 ===")
        success = mask_pdf_fields(
            pdf_path="/home/czr/MinerU_2/mineru_in/广州五舟公司销售合同.pdf",
            field_list=["广州五舟信息技术有限公司"],
            mapping_file=mapping_file,
            output_path="/home/czr/MinerU_2/mineru_out/masked_output.pdf",
            mask_color=(0, 0, 0),  # 黑色
            fuzzy_match=True
        )
        print(f"遮挡结果: {success}")
        
    except Exception as e:
        print(f"运行示例时出错: {e}")
