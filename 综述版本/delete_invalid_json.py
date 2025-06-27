#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
删除无效的JSON文件
"""

import os
import glob
import json
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def is_valid_json(file_path):
    """检查文件是否包含有效的JSON"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        return True
    except Exception:
        return False

def main():
    """主函数"""
    # 查找所有batch_response_*.json文件
    json_files = glob.glob('batch_response_*.json')
    
    for file_path in json_files:
        if not is_valid_json(file_path):
            logger.info(f"发现无效的JSON文件: {file_path}")
            
            # 尝试将无效的JSON文件重命名为.txt
            txt_path = file_path.replace('.json', '.txt')
            try:
                # 如果已存在同名的.txt文件，先删除
                if os.path.exists(txt_path):
                    os.remove(txt_path)
                
                # 读取原始内容
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 保存为.txt文件
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # 删除原始的.json文件
                os.remove(file_path)
                logger.info(f"已将无效的JSON文件转换为文本文件: {txt_path}")
            except Exception as e:
                logger.error(f"处理文件时出错: {str(e)}")
        else:
            logger.info(f"文件包含有效的JSON: {file_path}")

if __name__ == "__main__":
    main() 