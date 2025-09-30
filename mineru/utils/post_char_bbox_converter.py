#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后置字符级bbox转换器
在markdown生成后，将行级bbox转换为字符级bbox，并计算markdown索引
"""
import re
import json
from typing import List, Dict, Tuple
from loguru import logger


class PostCharBboxConverter:
    """后置字符级bbox转换器"""
    
    def __init__(self):
        self.char_width_ratios = self._init_char_width_ratios()
    
    def _init_char_width_ratios(self) -> Dict[str, float]:
        """初始化字符宽度比例映射"""
        return {
            # 中文字符
            'chinese': 1.0,
            # 英文字母和数字
            'ascii_alpha_num': 0.5,
            # 常见标点符号
            'punctuation': 0.5,
            # 空格
            'space': 0.5,
            # 全角字符
            'fullwidth': 1.0,
            # 其他字符
            'other': 0.8
        }
    
    def get_char_width_ratio(self, char: str) -> float:
        """
        获取字符的相对宽度比例
        
        Args:
            char: 单个字符
        
        Returns:
            字符宽度比例（以中文字符为1.0基准）
        """
        import unicodedata
        
        # 中文字符
        if '\u4e00' <= char <= '\u9fff':
            return self.char_width_ratios['chinese']
        # 中文标点符号
        elif '\u3000' <= char <= '\u303f' or '\uff00' <= char <= '\uffef':
            return self.char_width_ratios['fullwidth']
        # 全角字符
        elif unicodedata.east_asian_width(char) in ('F', 'W'):
            return self.char_width_ratios['fullwidth']
        # 数字
        elif char.isdigit():
            return self.char_width_ratios['ascii_alpha_num']
        # 英文字母
        elif char.isalpha() and ord(char) < 128:  # ASCII字母
            return self.char_width_ratios['ascii_alpha_num']
        # 常见半角标点符号
        elif char in '.,!?;:()[]{}"\'-_/\\@#$%^&*+=<>|`~':
            return self.char_width_ratios['punctuation']
        # 空格
        elif char.isspace():
            return self.char_width_ratios['space']
        # 其他字符，根据East Asian Width属性判断
        elif unicodedata.east_asian_width(char) in ('Na', 'H'):
            return self.char_width_ratios['ascii_alpha_num']  # 窄字符和半角字符
        else:
            return self.char_width_ratios['other']  # 未知字符，给一个中等宽度
    
    def calculate_text_width_ratios(self, text: str) -> List[float]:
        """
        计算文本中每个字符的累积宽度比例
        
        Args:
            text: 文本字符串
        
        Returns:
            每个字符位置的累积宽度比例列表
        """
        if not text:
            return []
        
        char_widths = [self.get_char_width_ratio(char) for char in text]
        total_width = sum(char_widths)
        
        # 计算累积宽度比例
        cumulative_ratios = [0.0]  # 起始位置
        cumulative_width = 0.0
        
        for width in char_widths:
            cumulative_width += width
            cumulative_ratios.append(cumulative_width / total_width if total_width > 0 else 0)
        
        return cumulative_ratios
    
    def calculate_char_bboxes(self, text: str, line_bbox: List[float]) -> List[List[float]]:
        """
        根据行级bbox计算每个字符的bbox
        
        Args:
            text: 文本内容
            line_bbox: 行级bbox [x0, y0, x1, y1]
        
        Returns:
            每个字符的bbox列表
        """
        if not text or len(line_bbox) < 4:
            return []
        
        # 计算每个字符位置的累积宽度比例
        cumulative_ratios = self.calculate_text_width_ratios(text)
        
        if len(cumulative_ratios) <= 1:
            return []
        
        x0, y0, x1, y1 = line_bbox[:4]
        width = x1 - x0
        
        char_bboxes = []
        for i in range(len(text)):
            if i + 1 < len(cumulative_ratios):
                # 计算字符的起始和结束位置
                char_start_x = x0 + width * cumulative_ratios[i]
                char_end_x = x0 + width * cumulative_ratios[i + 1]
                
                # 计算字符宽度并向左右各延伸50%
                char_width = char_end_x - char_start_x
                extension = char_width * 0.5
                
                # 应用延伸，但确保不超出原始边界
                extended_start_x = max(x0, char_start_x - extension)
                extended_end_x = min(x1, char_end_x + extension)
                
                char_bbox = [
                    extended_start_x,
                    y0,
                    extended_end_x,
                    y1
                ]
                char_bboxes.append(char_bbox)
        
        return char_bboxes
    
    
    
    def find_line_in_markdown(self, line_text: str, md_str: str, search_start: int = 0) -> Tuple[int, int]:
        """
        在markdown中查找行的位置
        
        Args:
            line_text: 行文本
            md_str: markdown文本
            search_start: 搜索起始位置
        
        Returns:
            (start_index, end_index) 行在markdown中的位置范围
        """
        if not line_text.strip():
            return -1, -1
        
        # 主策略：仅用原始行文本在 markdown 中直接查找（不做任何转换）
        found_index = md_str.find(line_text, search_start)
        if found_index != -1:
            end_index = found_index + len(line_text)
            return found_index, end_index

        # 备用策略：从右开始缩短前缀，直到匹配成功
        # 命中后返回 [命中起点, 命中起点 + 原始整行长度)
        min_sub_len = 5
        text_len = len(line_text)
        for cut in range(text_len - 1, min_sub_len - 1, -1):
            prefix = line_text[:cut]
            if not prefix.strip():
                continue
            pos = md_str.find(prefix, search_start)
            if pos != -1:
                return pos, pos + text_len

        return -1, -1
    
    
    
    def convert_line_to_chars(self, line_text: str, line_bbox: List[float], 
                             md_start_index: int, page_index: int) -> List[Dict]:
        """
        将行级文本转换为字符级数据
        
        Args:
            line_text: 行文本
            line_bbox: 行级bbox
            md_start_index: 行在markdown中的起始位置
            page_index: 页面索引
        
        Returns:
            字符级数据列表
        """
        if not line_text.strip():
            return []
        
        # 计算字符级bbox
        char_bboxes = self.calculate_char_bboxes(line_text, line_bbox)
        
        if not char_bboxes or len(char_bboxes) != len(line_text):
            return []
        
        char_data = []
        for i, char in enumerate(line_text):
            char_data.append({
                'char': char,
                'bbox': char_bboxes[i],
                'page_index': page_index,
                'md_index': md_start_index + i
            })
        
        return char_data
    
    
    
    def extract_lines_from_middle_json(self, middle_json: Dict) -> List[Dict]:
        """
        从middle.json中提取行级数据
        
        Args:
            middle_json: middle.json数据
        
        Returns:
            行级数据列表，每个元素包含 {text, bbox, page_index}
        """
        lines_data = []
        
        for page_info in middle_json.get('pdf_info', []):
            page_index = page_info.get('page_idx', 0)
            
            # 处理preproc_blocks
            for block in page_info.get('preproc_blocks', []):
                # 处理普通文本块
                if 'lines' in block:
                    for line in block['lines']:
                        if 'spans' in line:
                            for span in line['spans']:
                                if span.get('type') in ['text', 'title'] and 'content' in span:
                                    content = span['content']
                                    if content and isinstance(content, str) and content.strip():
                                        # 为每个span单独创建行级数据，而不是合并
                                        if 'bbox' in span and len(span['bbox']) >= 4:
                                            lines_data.append({
                                                'text': content,
                                                'bbox': span['bbox'],
                                                'page_index': page_index
                                            })
                
                # 处理表格块中的子块
                if 'blocks' in block:
                    for sub_block in block['blocks']:
                        if 'lines' in sub_block:
                            for line in sub_block['lines']:
                                if 'spans' in line:
                                    line_text = ''
                                    line_bbox = None
                                    
                                    for span in line['spans']:
                                        # 处理普通文本
                                        if span.get('type') in ['text', 'title'] and 'content' in span:
                                            content = span['content']
                                            if content and isinstance(content, str) and content.strip():
                                                # 为每个span单独创建行级数据，而不是合并
                                                if 'bbox' in span and len(span['bbox']) >= 4:
                                                    lines_data.append({
                                                        'text': content,
                                                        'bbox': span['bbox'],
                                                        'page_index': page_index
                                                    })
                                        
                                        # 处理表格文本
                                        elif span.get('type') == 'table' and 'table_texts' in span:
                                            table_texts = span['table_texts']
                                            if table_texts:
                                                # 将表格文本按行组织
                                                table_lines = {}
                                                for text_item in table_texts:
                                                    text = text_item.get('text', '')
                                                    bbox = text_item.get('bbox', [])
                                                    if text.strip() and len(bbox) >= 4:
                                                        # 使用y坐标作为行标识（简化处理）
                                                        y_coord = int(bbox[1])
                                                        if y_coord not in table_lines:
                                                            table_lines[y_coord] = []
                                                        table_lines[y_coord].append({
                                                            'text': text,
                                                            'bbox': bbox
                                                        })
                                                
                                                # 为每个表格行创建数据
                                                for y_coord in sorted(table_lines.keys()):
                                                    row_items = table_lines[y_coord]
                                                    row_text = ' '.join([item['text'] for item in row_items])
                                                    # 使用第一个文本的bbox作为行bbox
                                                    row_bbox = row_items[0]['bbox']
                                                    
                                                    lines_data.append({
                                                        'text': row_text,
                                                        'bbox': row_bbox,
                                                        'page_index': page_index,
                                                        'is_table': True
                                                    })
            
            # 处理discarded_blocks
            for block in page_info.get('discarded_blocks', []):
                if 'lines' in block:
                    for line in block['lines']:
                        if 'spans' in line:
                            for span in line['spans']:
                                if span.get('type') in ['text', 'title'] and 'content' in span:
                                    content = span['content']
                                    if content and isinstance(content, str) and content.strip():
                                        # 为每个span单独创建行级数据，而不是合并
                                        if 'bbox' in span and len(span['bbox']) >= 4:
                                            lines_data.append({
                                                'text': content,
                                                'bbox': span['bbox'],
                                                'page_index': page_index
                                            })
        
        return lines_data
    
    def convert_to_char_level(self, middle_json: Dict, md_str: str) -> Dict[str, Dict]:
        """
        将middle.json转换为字符级bbox映射
        
        Args:
            middle_json: middle.json数据
            md_str: markdown文本
        
        Returns:
            字符级bbox映射字典
        """
        # 提取行级数据
        lines_data = self.extract_lines_from_middle_json(middle_json)
        
        char_mapping = {}
        md_search_start = 0
        successful_matches = 0
        failed_matches = 0
        
        logger.info(f"开始转换 {len(lines_data)} 行数据为字符级bbox")
        
        for i, line_data in enumerate(lines_data):
            line_text = line_data['text']
            line_bbox = line_data['bbox']
            page_index = line_data['page_index']
            
            # 在markdown中查找行的位置
            md_start, md_end = self.find_line_in_markdown(line_text, md_str, md_search_start)
            
            if md_start != -1:
                # 转换为字符级数据
                char_data = self.convert_line_to_chars(line_text, line_bbox, md_start, page_index)
                
                # 添加到映射中
                for char_info in char_data:
                    char = char_info['char']
                    key = char
                    counter = 1
                    while key in char_mapping:
                        key = f"{char}_{counter}"
                        counter += 1
                    
                    char_mapping[key] = {
                        'bbox': char_info['bbox'],
                        'page_index': char_info['page_index'],
                        'md_index': char_info['md_index']
                    }
                
                # 更新搜索起始位置
                md_search_start = md_end
                successful_matches += 1
                
                if i < 5:  # 只记录前5行的详细信息
                    logger.debug(f"行 {i+1} 匹配成功: '{line_text[:30]}...' -> {md_start}-{md_end}, 生成 {len(char_data)} 个字符")
            else:
                failed_matches += 1
                logger.warning(f"行 {i+1} 未在markdown中找到: '{line_text[:50]}...' (搜索起始位置: {md_search_start})")
                
                # 尝试全局搜索（不限制搜索起始位置）
                global_start, global_end = self.find_line_in_markdown(line_text, md_str, 0)
                if global_start != -1:
                    logger.info(f"行 {i+1} 在全局搜索中找到: {global_start}-{global_end}")
                    # 使用全局匹配的结果
                    char_data = self.convert_line_to_chars(line_text, line_bbox, global_start, page_index)
                    
                    for char_info in char_data:
                        char = char_info['char']
                        key = char
                        counter = 1
                        while key in char_mapping:
                            key = f"{char}_{counter}"
                            counter += 1
                        
                        char_mapping[key] = {
                            'bbox': char_info['bbox'],
                            'page_index': char_info['page_index'],
                            'md_index': char_info['md_index']
                        }
                    
                    successful_matches += 1
                    failed_matches -= 1
        
        logger.info(f"转换完成: 成功匹配 {successful_matches} 行，失败 {failed_matches} 行，共生成 {len(char_mapping)} 个字符级bbox")
        return char_mapping


def convert_middle_json_to_char_level(middle_json: Dict, md_str: str) -> str:
    """
    将middle.json转换为字符级bbox映射的JSON字符串
    
    Args:
        middle_json: middle.json数据
        md_str: markdown文本
    
    Returns:
        字符级bbox映射的JSON字符串
    """
    converter = PostCharBboxConverter()
    char_mapping = converter.convert_to_char_level(middle_json, md_str)
    return json.dumps(char_mapping, ensure_ascii=False, indent=2)
