import os
import html
import cv2
import numpy as np
from loguru import logger
from rapid_table import RapidTable, RapidTableInput

from mineru.utils.enum_class import ModelPath
from mineru.utils.models_download_utils import auto_download_and_get_model_root_path


def escape_html(input_string):
    """Escape HTML Entities."""
    return html.escape(input_string)


class RapidTableModel(object):
    def __init__(self, ocr_engine):
        slanet_plus_model_path = os.path.join(auto_download_and_get_model_root_path(ModelPath.slanet_plus), ModelPath.slanet_plus)
        input_args = RapidTableInput(model_type='slanet_plus', model_path=slanet_plus_model_path)
        self.table_model = RapidTable(input_args)
        self.ocr_engine = ocr_engine


    def predict(self, image):
        bgr_image = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

        # First check the overall image aspect ratio (height/width)
        img_height, img_width = bgr_image.shape[:2]
        logger.info(f"======= 表格尺寸 =======")
        logger.info(f"height:{img_height} width:{img_width}")

        img_aspect_ratio = img_height / img_width if img_width > 0 else 1.0
        img_is_portrait = img_aspect_ratio > 1.2

        if img_is_portrait:

            det_res = self.ocr_engine.ocr(bgr_image, rec=False)[0]
            # Check if table is rotated by analyzing text box aspect ratios
            is_rotated = False
            if det_res:
                vertical_count = 0

                for box_ocr_res in det_res:
                    p1, p2, p3, p4 = box_ocr_res

                    # Calculate width and height
                    width = p3[0] - p1[0]
                    height = p3[1] - p1[1]

                    aspect_ratio = width / height if height > 0 else 1.0

                    # Count vertical vs horizontal text boxes
                    if aspect_ratio < 0.8:  # Taller than wide - vertical text
                        vertical_count += 1
                    # elif aspect_ratio > 1.2:  # Wider than tall - horizontal text
                    #     horizontal_count += 1

                # If we have more vertical text boxes than horizontal ones,
                # and vertical ones are significant, table might be rotated
                if vertical_count >= len(det_res) * 0.3:
                    is_rotated = True

                # logger.debug(f"Text orientation analysis: vertical={vertical_count}, det_res={len(det_res)}, rotated={is_rotated}")

            # Rotate image if necessary
            if is_rotated:
                # logger.debug("Table appears to be in portrait orientation, rotating 90 degrees clockwise")
                image = cv2.rotate(np.asarray(image), cv2.ROTATE_90_CLOCKWISE)
                bgr_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        # Continue with OCR on potentially rotated image
        ocr_result = self.ocr_engine.ocr(bgr_image)[0]
        
        # 调试信息：输出OCR原始结果
        logger.info(f"======= 表格OCR原始结果 =======")
        logger.info(f"OCR结果数量: {len(ocr_result) if ocr_result else 0}")
        if ocr_result and len(ocr_result) > 0:
            for i, item in enumerate(ocr_result[:min(10, len(ocr_result))]):  # 只显示前10个
                if len(item) >= 2:
                    bbox = item[0]
                    text = item[1][0] if isinstance(item[1], tuple) else "无文本"
                    confidence = item[1][1] if isinstance(item[1], tuple) else 0
                    logger.info(f"文本[{i}]: '{text}' (置信度: {confidence:.3f})")
                    logger.info(f"坐标[{i}]: {bbox}")
            
            if len(ocr_result) > 10:
                logger.info(f"...还有 {len(ocr_result) - 10} 个OCR结果未显示...")
        
        # 处理OCR结果
        if ocr_result:
            ocr_result = [[item[0], escape_html(item[1][0]), item[1][1]] for item in ocr_result if
                      len(item) == 2 and isinstance(item[1], tuple)]
            
            for i, item in enumerate(ocr_result[:min(10, len(ocr_result))]):  # 只显示前10个
                bbox, text, confidence = item

        else:
            ocr_result = None


        if ocr_result:
            
            table_results = self.table_model(np.asarray(image), ocr_result)
            html_code = table_results.pred_html
            
            
            # 获取表格单元格边界框
            table_cell_bboxes = table_results.cell_bboxes
            
            # 如果存在表格单元格边界框，将坐标从模型输出转换回原始图像坐标
            if table_cell_bboxes is not None and len(table_cell_bboxes) > 0:
                original_h, original_w = np.asarray(image).shape[:2]
                
                # 判断是否进行了旋转
                is_image_rotated = is_rotated if 'is_rotated' in locals() else False
                
                # 将每个单元格的坐标转换回原始坐标
                for i in range(len(table_cell_bboxes)):
                    cell_bbox = table_cell_bboxes[i]

                    
                    
                    # 处理旋转图像的坐标转换
                    if is_image_rotated:
                        rotated_bbox = []
                        for j in range(0, 8, 2):
                            x = cell_bbox[j]
                            y = cell_bbox[j+1]
                            # 顺时针旋转90度的逆变换
                            temp_x, temp_y = y, original_w - x
                            rotated_bbox.extend([temp_x, temp_y])
                        table_cell_bboxes[i] = np.array(rotated_bbox)
            
            # 确保logic_points也是Python原生类型
            if hasattr(table_results.logic_points, 'tolist'):
                logic_points = table_results.logic_points.tolist()
            else:
                logic_points = table_results.logic_points
            elapse = float(table_results.elapse) if hasattr(table_results.elapse, 'item') else table_results.elapse
            
            # 计算图像可能的缩放比例，与RapidTable内部的adapt_slanet_plus方法一致
            original_h, original_w = np.asarray(image).shape[:2]
            
            # 判断是否进行了旋转
            is_image_rotated = is_rotated if 'is_rotated' in locals() else False
            
            # 提取文本和对应的边界框信息
            text_with_bbox = []
            for item in ocr_result:
                bbox = item[0]  # 文本框坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text = item[1]  # HTML转义后的文本
                confidence = item[2]  # 文本识别置信度
                
                # 将bbox坐标从模型输出的缩放坐标转换回原始图像坐标
                adjusted_bbox = []
                for point in bbox:
                    x, y = float(point[0]), float(point[1])
                    
                    # 处理旋转图像的坐标转换
                    if is_image_rotated:
                        # 顺时针旋转90度的逆变换
                        temp_x, temp_y = y, original_w - x
                        x, y = temp_x, temp_y
                    
                    adjusted_bbox.append([x, y])
                
                # 转换为[x_min, y_min, x_max, y_max]格式的边界框
                x_coords = [float(point[0]) for point in adjusted_bbox]
                y_coords = [float(point[1]) for point in adjusted_bbox]
                x_min, y_min = min(x_coords), min(y_coords)
                x_max, y_max = max(x_coords), max(y_coords)
                
                # 确保所有数值都是Python原生类型，而非NumPy类型
                polygon = [[float(point[0]), float(point[1])] for point in adjusted_bbox]
                confidence_value = float(confidence)
                
                text_with_bbox.append({
                    'text': html.unescape(text),  # 转回原始文本
                    'bbox': [float(x_min), float(y_min), float(x_max), float(y_max)],
                    'polygon': polygon,
                    'confidence': confidence_value,
                    'ocr_hw': (img_height, img_width)
                })
            
            return html_code, table_cell_bboxes, logic_points, elapse, text_with_bbox
        else:
            return None, None, None, None, None
