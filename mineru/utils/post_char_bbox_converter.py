#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后置字符级bbox转换器
在markdown生成后，将行级bbox转换为字符级bbox，并计算markdown索引
"""
import re
import json
from typing import List, Dict, Tuple, Optional
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
    
    def normalize_text_for_matching(self, text: str) -> str:
        """
        标准化文本用于匹配，移除多余的空白字符和特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            标准化后的文本
        """
        # 将多个空白字符替换为单个空格，并去除首尾空白
        normalized = re.sub(r'\s+', ' ', text.strip())
        
        # 移除或替换特殊字符，提高匹配成功率
        # 保留中文、英文、数字和基本标点
        normalized = re.sub(r'[^\w\u4e00-\u9fff\s，。！？；：""''（）【】]', '', normalized)
        
        return normalized
    
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
        
        # 标准化文本用于匹配
        normalized_text = self.normalize_text_for_matching(line_text)
        
        # 策略1: 直接匹配
        found_index = md_str.find(normalized_text, search_start)
        if found_index != -1:
            end_index = found_index + len(normalized_text)
            return found_index, end_index
        
        # 策略2: 尝试在markdown格式中查找（如标题）
        # 查找可能的markdown格式：如 "# 文本" 或 "## 文本"
        markdown_patterns = [
            f"# {normalized_text}",
            f"## {normalized_text}",
            f"### {normalized_text}",
            f"#### {normalized_text}",
            f"**{normalized_text}**",
            f"*{normalized_text}*",
            f"`{normalized_text}`"
        ]
        
        for pattern in markdown_patterns:
            found_index = md_str.find(pattern, search_start)
            if found_index != -1:
                # 找到markdown格式，返回文本部分的位置
                text_start = found_index + len(pattern) - len(normalized_text)
                text_end = text_start + len(normalized_text)
                return text_start, text_end
        
        # 策略3: 移除markdown格式字符后匹配
        clean_text = self._remove_markdown_formatting(normalized_text)
        if clean_text != normalized_text:
            found_index = md_str.find(clean_text, search_start)
            if found_index != -1:
                end_index = found_index + len(clean_text)
                return found_index, end_index
        
        # 策略4: 表格格式匹配
        # 检查是否是表格行（包含多个用空格分隔的词语）
        if ' ' in normalized_text and len(normalized_text.split()) >= 2:
            # 尝试匹配markdown表格格式
            words = normalized_text.split()
            
            # 策略4a: 匹配表格行格式 "| word1 | word2 | word3 |"
            table_pattern = '| ' + ' | '.join(words) + ' |'
            found_index = md_str.find(table_pattern, search_start)
            if found_index != -1:
                # 找到表格行，返回文本部分的位置（跳过markdown格式）
                text_start = found_index + 2  # 跳过 "| "
                text_end = text_start + len(normalized_text)
                return text_start, text_end
            
            # 策略4b: 匹配表格行格式 "word1 | word2 | word3"
            table_pattern2 = ' | '.join(words)
            found_index = md_str.find(table_pattern2, search_start)
            if found_index != -1:
                text_start = found_index
                text_end = text_start + len(normalized_text)
                return text_start, text_end
            
            # 策略4c: 匹配表格行格式 "| word1 | word2 | word3 |" (完整格式)
            table_pattern3 = '| ' + ' | '.join(words) + ' |'
            found_index = md_str.find(table_pattern3, search_start)
            if found_index != -1:
                # 找到完整表格行，返回文本部分的位置
                text_start = found_index + 2  # 跳过 "| "
                text_end = text_start + len(normalized_text)
                return text_start, text_end
            
            # 策略4d: 模糊匹配表格行（处理markdown中的额外空格）
            # 在markdown中查找包含所有词语的行
            for line in md_str[search_start:].split('\n'):
                if all(word in line for word in words):
                    # 找到包含所有词语的行
                    line_start = md_str.find(line, search_start)
                    if line_start != -1:
                        # 在行中查找文本的位置
                        text_in_line = ' '.join(words)
                        text_start_in_line = line.find(text_in_line)
                        if text_start_in_line != -1:
                            text_start = line_start + text_start_in_line
                            text_end = text_start + len(normalized_text)
                            return text_start, text_end
                        else:
                            # 如果直接查找失败，尝试查找第一个词语的位置
                            first_word = words[0]
                            first_word_pos = line.find(first_word)
                            if first_word_pos != -1:
                                text_start = line_start + first_word_pos
                                text_end = text_start + len(normalized_text)
                                return text_start, text_end
        
        # 策略5: HTML表格匹配
        # 检查markdown中是否包含HTML表格
        html_table_pattern = r'<html><body><table>.*?</table></body></html>'
        html_tables = re.findall(html_table_pattern, md_str[search_start:], re.DOTALL)
        
        for html_table in html_tables:
            # 从HTML中提取纯文本
            html_text = self._extract_text_from_html_table(html_table)
            if normalized_text in html_text:
                # 在HTML中找到文本，计算在markdown中的位置
                html_start = md_str.find(html_table, search_start)
                text_start_in_html = html_text.find(normalized_text)
                if html_start != -1 and text_start_in_html != -1:
                    # 简化处理：假设文本在HTML的开始位置
                    text_start = html_start + text_start_in_html
                    text_end = text_start + len(normalized_text)
                    return text_start, text_end
        
        # 策略6: 模糊匹配（处理可能的字符差异）
        # 移除所有空白字符后匹配
        clean_normalized = re.sub(r'\s+', '', normalized_text)
        clean_md = re.sub(r'\s+', '', md_str[search_start:])
        if clean_normalized in clean_md:
            # 找到模糊匹配，需要计算在原始字符串中的位置
            fuzzy_index = clean_md.find(clean_normalized)
            if fuzzy_index != -1:
                # 计算在原始markdown中的位置（简化处理）
                original_index = search_start + fuzzy_index
                end_index = original_index + len(normalized_text)
                
                # 验证匹配质量
                if end_index <= len(md_str):
                    matched_text = md_str[original_index:end_index]
                    # 如果匹配的文本长度差异太大，可能是错误匹配
                    if abs(len(matched_text) - len(normalized_text)) <= max(5, len(normalized_text) * 0.3):
                        return original_index, end_index
        
        # 策略7: 更宽松的模糊匹配（移除更多特殊字符）
        # 只保留中文、英文、数字进行匹配
        ultra_clean_normalized = re.sub(r'[^\w\u4e00-\u9fff]', '', normalized_text)
        ultra_clean_md = re.sub(r'[^\w\u4e00-\u9fff]', '', md_str[search_start:])
        if ultra_clean_normalized and ultra_clean_normalized in ultra_clean_md:
            # 找到超宽松匹配，但需要验证匹配质量
            fuzzy_index = ultra_clean_md.find(ultra_clean_normalized)
            if fuzzy_index != -1:
                # 计算在原始markdown中的位置（简化处理）
                original_index = search_start + fuzzy_index
                end_index = original_index + len(normalized_text)
                
                # 验证匹配质量：检查匹配的文本是否合理
                if end_index <= len(md_str):
                    matched_text = md_str[original_index:end_index]
                    # 如果匹配的文本长度差异太大，可能是错误匹配
                    if abs(len(matched_text) - len(normalized_text)) <= max(5, len(normalized_text) * 0.3):
                        return original_index, end_index
        
        return -1, -1
    
    def _remove_markdown_formatting(self, text: str) -> str:
        """
        移除markdown格式化字符，保留纯文本内容
        
        Args:
            text: 包含markdown格式的文本
        
        Returns:
            移除格式化字符后的纯文本
        """
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
    
    def _extract_text_from_html_table(self, html_table: str) -> str:
        """
        从HTML表格中提取纯文本内容
        
        Args:
            html_table: HTML表格字符串
        
        Returns:
            提取的纯文本内容
        """
        # 移除HTML标签，保留文本内容
        text = re.sub(r'<[^>]+>', '', html_table)
        
        # 清理多余的空白字符
        text = re.sub(r'\s+', ' ', text.strip())
        
        return text
    
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
