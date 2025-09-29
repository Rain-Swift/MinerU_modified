#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取OCR结果中的文本和边界框信息
"""
import json
import sys
from typing import List, Tuple, Dict, Any


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


def extract_all_text_bbox(json_file_path: str) -> List[Tuple[str, List[float], int]]:
    """
    从OCR结果JSON文件中提取所有文本和bbox信息
    
    Args:
        json_file_path: JSON文件路径
    
    Returns:
        List of tuples (text, bbox, page_index)
    """
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_text_bbox = []
    
    # 遍历pdf_info中的每个页面
    for page_info in data.get('pdf_info', []):
        # 获取页面索引，如果没有则使用0作为默认值
        page_index = page_info.get('page_idx', 0)
        if page_index == 0:
            page_info.get('page_num', 0)
        
        if 'preproc_blocks' in page_info:
            page_results = extract_text_bbox_from_preproc_blocks(page_info['preproc_blocks'], page_index)
            all_text_bbox.extend(page_results)
    
    return all_text_bbox


def save_text_bbox_mapping(text_bbox_list: List[Tuple[str, List[float], int]], output_file: str):
    """
    保存文本和bbox映射到文件
    
    Args:
        text_bbox_list: 文本、bbox和页号的列表
        output_file: 输出文件路径
    """
    # 创建映射字典
    text_bbox_mapping = {}
    for i, (text, bbox, page_index) in enumerate(text_bbox_list):
        # 如果有重复的文本，添加索引以区分
        key = text
        counter = 1
        while key in text_bbox_mapping:
            key = f"{text}_{counter}"
            counter += 1
        text_bbox_mapping[key] = {
            "bbox": bbox,
            "page_index": page_index
        }
    
    # 保存为JSON文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(text_bbox_mapping, f, ensure_ascii=False, indent=2)
    
    print(f"文本-bbox映射已保存到: {output_file}")
    print(f"共提取到 {len(text_bbox_mapping)} 个文本-bbox对")


def print_text_bbox_summary(text_bbox_list: List[Tuple[str, List[float], int]]):
    """打印文本和bbox的摘要信息"""
    print(f"\n=== 提取结果摘要 ===")
    print(f"总共提取到 {len(text_bbox_list)} 个文本-bbox对")
    
    print(f"\n前10个示例:")
    for i, (text, bbox, page_index) in enumerate(text_bbox_list[:10]):
        text_type = "表格" if any(keyword in text for keyword in ['名称：', '统一社会信用代码', '项目名称', '单价', '数量', '金额', '税率', '税额']) else "普通"
        print(f"{i+1:2d}. 页面{page_index} | {text_type} | 文本: '{text}' | bbox: {bbox}")
    
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

def main():
    if len(sys.argv) not in [2, 3]:
        print("用法: python extract_text_bbox.py <input_json_file> [--analyze]")
        print("示例: python extract_text_bbox.py /path/to/ocr_result.json")
        print("      python extract_text_bbox.py /path/to/ocr_result.json --analyze  # 显示坐标转换分析")
        sys.exit(1)
    
    input_file = sys.argv[1]
    analyze_mode = len(sys.argv) == 3 and sys.argv[2] == '--analyze'
    
    try:
        if analyze_mode:
            # 坐标转换分析模式
            print("=== 坐标转换分析模式 ===")
            analyze_coordinate_transformation(input_file, debug=True)
            return
        
        # 提取所有文本和bbox
        text_bbox_list = extract_all_text_bbox(input_file)
        
        # 打印摘要
        print_text_bbox_summary(text_bbox_list)
        
        # 保存映射文件
        output_file = input_file.replace('.json', '_text_bbox_mapping.json')
        save_text_bbox_mapping(text_bbox_list, output_file)
        
        # 也可以保存为简单的文本格式
        txt_output_file = input_file.replace('.json', '_text_bbox.txt')
        with open(txt_output_file, 'w', encoding='utf-8') as f:
            f.write("文本\tbbox\t页号\n")
            f.write("-" * 80 + "\n")
            for text, bbox, page_index in text_bbox_list:
                f.write(f"{text}\t{bbox}\t{page_index}\n")
        
        print(f"文本列表已保存到: {txt_output_file}")
        
    except FileNotFoundError:
        print(f"错误: 找不到文件 {input_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"错误: 文件 {input_file} 不是有效的JSON格式")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
