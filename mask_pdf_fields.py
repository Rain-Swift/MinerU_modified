#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF字段遮挡脚本
根据字符级JSON文件，在PDF中遮挡指定的字符串区域
"""

import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import fitz  # PyMuPDF
from loguru import logger


class PDFMasker:
    """PDF字段遮挡器"""
    
    def __init__(self, pdf_path: str, json_path: str):
        """
        初始化PDF遮挡器
        
        Args:
            pdf_path: PDF文件路径
            json_path: 字符级JSON文件路径
        """
        self.pdf_path = Path(pdf_path)
        self.json_path = Path(json_path)
        
        # 验证文件存在
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        if not self.json_path.exists():
            raise FileNotFoundError(f"JSON文件不存在: {json_path}")
        
        # 加载PDF文档
        self.doc = fitz.open(str(self.pdf_path))
        
        # 加载字符级JSON数据
        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.char_data = json.load(f)
        
        logger.info(f"成功加载PDF: {self.pdf_path}")
        logger.info(f"成功加载字符数据: {len(self.char_data)} 个字符")
    
    def find_string_positions(self, target_string: str) -> List[Dict]:
        """
        在字符级数据中查找目标字符串的位置
        
        Args:
            target_string: 要查找的字符串
            
        Returns:
            包含字符位置信息的列表
        """
        positions = []
        char_keys = list(self.char_data.keys())
        
        # 遍历所有可能的起始位置
        for i in range(len(char_keys)):
            # 尝试从当前位置开始匹配
            matched_chars = []
            target_index = 0
            
            for j in range(i, len(char_keys)):
                if target_index >= len(target_string):
                    break
                
                char_key = char_keys[j]
                char_info = self.char_data[char_key]
                
                # 获取字符（处理带下标的字符）
                char = char_key.split('_')[0]  # 移除下标后缀
                
                if char == target_string[target_index]:
                    matched_chars.append({
                        'char_key': char_key,
                        'char': char,
                        'char_info': char_info
                    })
                    target_index += 1
                else:
                    # 匹配失败，重置
                    break
            
            # 如果完全匹配，添加到结果中
            if target_index == len(target_string):
                positions.append(matched_chars)
        
        return positions
    
    def get_bbox_for_string(self, target_string: str) -> List[Tuple[int, List[float]]]:
        """
        获取字符串在PDF中的边界框位置
        
        Args:
            target_string: 目标字符串
            
        Returns:
            [(page_index, bbox), ...] 列表
        """
        positions = self.find_string_positions(target_string)
        
        if not positions:
            logger.warning(f"未找到字符串: '{target_string}'")
            return []
        
        bbox_list = []
        for pos in positions:
            if not pos:
                continue
            
            # 获取第一个和最后一个字符的信息
            first_char = pos[0]
            last_char = pos[-1]
            
            first_info = first_char['char_info']
            last_info = last_char['char_info']
            
            page_index = first_info['page_index']
            first_bbox = first_info['bbox']
            last_bbox = last_info['bbox']
            
            # 计算整个字符串的边界框
            # bbox格式: [x0, y0, x1, y1]
            string_bbox = [
                min(first_bbox[0], last_bbox[0]),  # x0
                min(first_bbox[1], last_bbox[1]),  # y0
                max(first_bbox[2], last_bbox[2]),  # x1
                max(first_bbox[3], last_bbox[3])   # y1
            ]
            
            bbox_list.append((page_index, string_bbox))
        
        return bbox_list
    
    def mask_string(self, target_string: str, mask_color: Tuple[float, float, float] = (0, 0, 0)) -> int:
        """
        遮挡PDF中的指定字符串
        
        Args:
            target_string: 要遮挡的字符串
            mask_color: 遮挡颜色 (R, G, B)，默认为黑色
            
        Returns:
            遮挡的字符串数量
        """
        bbox_list = self.get_bbox_for_string(target_string)
        
        if not bbox_list:
            return 0
        
        masked_count = 0
        for page_index, bbox in bbox_list:
            page = self.doc[page_index]
            
            # 创建遮挡矩形
            rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
            
            # 绘制遮挡矩形
            page.draw_rect(rect, color=mask_color, fill=mask_color)
            
            masked_count += 1
            logger.info(f"遮挡字符串 '{target_string}' 在页面 {page_index}: {bbox}")
        
        return masked_count
    
    def mask_multiple_strings(self, strings: List[str], mask_color: Tuple[float, float, float] = (0, 0, 0)) -> Dict[str, int]:
        """
        遮挡多个字符串
        
        Args:
            strings: 要遮挡的字符串列表
            mask_color: 遮挡颜色
            
        Returns:
            {字符串: 遮挡数量} 字典
        """
        results = {}
        
        for string in strings:
            count = self.mask_string(string, mask_color)
            results[string] = count
            logger.info(f"字符串 '{string}': 遮挡了 {count} 处")
        
        return results
    
    def save_masked_pdf(self, output_path: str):
        """
        保存遮挡后的PDF
        
        Args:
            output_path: 输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.doc.save(str(output_path))
        logger.info(f"遮挡后的PDF已保存到: {output_path}")
    
    def close(self):
        """关闭PDF文档"""
        if self.doc:
            self.doc.close()


def mask_pdf_fields(pdf_path: str, json_path: str, strings: List[str], 
                   output_path: str, mask_color: Tuple[float, float, float] = (0, 0, 0),
                   verbose: bool = False) -> Dict[str, int]:
    """
    遮挡PDF中的指定字符串字段
    
    Args:
        pdf_path: PDF文件路径
        json_path: 字符级JSON文件路径
        strings: 要遮挡的字符串列表
        output_path: 输出PDF文件路径
        mask_color: 遮挡颜色 RGB (0-1)，默认为黑色
        verbose: 是否显示详细日志
        
    Returns:
        {字符串: 遮挡数量} 字典
        
    Example:
        # 遮挡单个字符串
        results = mask_pdf_fields(
            pdf_path="input.pdf",
            json_path="char_data.json", 
            strings=["张三"],
            output_path="masked.pdf"
        )
        
        # 遮挡多个字符串
        results = mask_pdf_fields(
            pdf_path="input.pdf",
            json_path="char_data.json",
            strings=["张三", "李四", "王五"],
            output_path="masked.pdf",
            mask_color=(1, 1, 1)  # 白色遮挡
        )
    """
    # 设置日志级别
    if verbose:
        logger.remove()
        logger.add(lambda msg: print(msg, end=""), level="DEBUG")
    
    try:
        # 创建PDF遮挡器
        masker = PDFMasker(pdf_path, json_path)
        
        # 遮挡字符串
        results = masker.mask_multiple_strings(strings, mask_color)
        
        # 保存结果
        masker.save_masked_pdf(output_path)
        
        # 输出统计信息
        total_masked = sum(results.values())
        logger.info(f"总共遮挡了 {total_masked} 处字符串")
        
        for string, count in results.items():
            if count > 0:
                logger.info(f"✓ '{string}': {count} 处")
            else:
                logger.warning(f"✗ '{string}': 未找到")
        
        masker.close()
        return results
        
    except Exception as e:
        logger.error(f"处理过程中发生错误: {e}")
        raise


# 使用示例
if __name__ == "__main__":
    # 示例1: 遮挡单个字符串
    results = mask_pdf_fields(
        pdf_path="/home/czr/MinerU_2/mineru_in/1.pdf",
        json_path="/home/czr/MinerU_2/mineru_out/1/auto/1_middle.json", 
        strings=["310@10119960223@24@1", "zhangy^ing5602@&163.c-0m"],
        output_path="masked.pdf"
    )
    
    # 示例2: 遮挡多个字符串
    # results = mask_pdf_fields(
    #     pdf_path="input.pdf",
    #     json_path="char_data.json",
    #     strings=["张三", "李四", "王五"],
    #     output_path="masked.pdf",
    #     mask_color=(1, 1, 1),  # 白色遮挡
    #     verbose=True
    # )