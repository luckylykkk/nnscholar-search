#!/usr/bin/env python3
"""
更新期刊数据脚本
从2024JCR完整版.xlsx文件中提取期刊信息，更新jcr_cas_ifqb.json文件
"""

import pandas as pd
import json
import os
import logging
from typing import Dict, List, Any

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_excel_data(excel_path: str) -> pd.DataFrame:
    """加载Excel文件数据"""
    try:
        logger.info(f"正在加载Excel文件: {excel_path}")
        df = pd.read_excel(excel_path)
        logger.info(f"成功加载 {len(df)} 条记录")
        logger.info(f"列名: {list(df.columns)}")
        return df
    except Exception as e:
        logger.error(f"加载Excel文件失败: {e}")
        raise

def process_journal_data(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """处理期刊数据，转换为标准格式"""
    processed_data = []
    
    for index, row in df.iterrows():
        try:
            # 提取基本信息
            journal_name = str(row.get('Journal Name', '')).strip()
            abbreviated_name = str(row.get('Abbreviated Journal', '')).strip()
            publisher = str(row.get('Publisher', '')).strip()
            issn = str(row.get('ISSN', '')).strip()
            eissn = str(row.get('eISSN', '')).strip()
            
            # 提取影响因子
            jif_2024 = row.get('JIF 2024', '')
            impact_factor = 'N/A'
            if pd.notna(jif_2024) and jif_2024 != '':
                try:
                    impact_factor = float(jif_2024)
                except (ValueError, TypeError):
                    impact_factor = 'N/A'
            
            # 提取JCR分区
            jif_quartile = str(row.get('JIF Quartile', 'N/A')).strip()
            
            # 提取排名信息用于计算CAS分区
            jif_rank = str(row.get('JIF Rank', '')).strip()
            cas_quartile = 'N/A'
            
            # 根据JIF Rank计算CAS分区（简化处理）
            if jif_rank and '/' in jif_rank:
                try:
                    rank_parts = jif_rank.split('/')
                    current_rank = int(rank_parts[0])
                    total_journals = int(rank_parts[1])
                    
                    # 计算分区
                    percentage = current_rank / total_journals
                    if percentage <= 0.05:  # 前5%
                        cas_quartile = '1'
                    elif percentage <= 0.20:  # 前20%
                        cas_quartile = '2'
                    elif percentage <= 0.50:  # 前50%
                        cas_quartile = '3'
                    else:  # 其他
                        cas_quartile = '4'
                except (ValueError, IndexError):
                    cas_quartile = 'N/A'
            
            # 清理ISSN格式
            if issn and issn != 'nan':
                issn = issn.replace('-', '').replace(' ', '')
                if len(issn) == 8:
                    issn = f"{issn[:4]}-{issn[4:]}"
            else:
                issn = ''
                
            if eissn and eissn != 'nan':
                eissn = eissn.replace('-', '').replace(' ', '')
                if len(eissn) == 8:
                    eissn = f"{eissn[:4]}-{eissn[4:]}"
            else:
                eissn = ''
            
            # 构建期刊数据
            journal_data = {
                'journal': journal_name,
                'jabb': abbreviated_name,
                'publisher': publisher,
                'issn': issn,
                'eissn': eissn,
                'IF': impact_factor,
                'Q': jif_quartile,
                'B': cas_quartile,
                'rank': jif_rank
            }
            
            processed_data.append(journal_data)
            
            if (index + 1) % 1000 == 0:
                logger.info(f"已处理 {index + 1} 条记录")
                
        except Exception as e:
            logger.warning(f"处理第 {index + 1} 行数据时出错: {e}")
            continue
    
    logger.info(f"成功处理 {len(processed_data)} 条期刊数据")
    return processed_data

def save_journal_data(data: List[Dict[str, Any]], output_path: str):
    """保存期刊数据到JSON文件"""
    try:
        logger.info(f"正在保存数据到: {output_path}")
        
        # 确保目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"成功保存 {len(data)} 条记录到 {output_path}")
        
    except Exception as e:
        logger.error(f"保存数据失败: {e}")
        raise

def create_backup(original_path: str):
    """创建原文件备份"""
    if os.path.exists(original_path):
        backup_path = original_path + '.backup'
        try:
            import shutil
            shutil.copy2(original_path, backup_path)
            logger.info(f"已创建备份文件: {backup_path}")
        except Exception as e:
            logger.warning(f"创建备份失败: {e}")

def main():
    """主函数"""
    # 文件路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base_dir, 'data', 'journal_metrics', '2024JCR完整版.xlsx')
    output_path = os.path.join(base_dir, 'data', 'journal_metrics', 'jcr_cas_ifqb.json')
    
    try:
        # 检查Excel文件是否存在
        if not os.path.exists(excel_path):
            logger.error(f"Excel文件不存在: {excel_path}")
            return
        
        # 创建原文件备份
        create_backup(output_path)
        
        # 加载Excel数据
        df = load_excel_data(excel_path)
        
        # 处理数据
        processed_data = process_journal_data(df)
        
        # 保存数据
        save_journal_data(processed_data, output_path)
        
        # 显示统计信息
        logger.info("=" * 50)
        logger.info("数据更新完成！")
        logger.info(f"总计处理期刊数量: {len(processed_data)}")
        
        # 统计有影响因子的期刊数量
        with_if = sum(1 for item in processed_data if item['IF'] != 'N/A')
        logger.info(f"有影响因子的期刊: {with_if}")
        
        # 统计各分区期刊数量
        q1_count = sum(1 for item in processed_data if item['Q'] == 'Q1')
        q2_count = sum(1 for item in processed_data if item['Q'] == 'Q2')
        q3_count = sum(1 for item in processed_data if item['Q'] == 'Q3')
        q4_count = sum(1 for item in processed_data if item['Q'] == 'Q4')
        
        logger.info(f"JCR分区统计: Q1={q1_count}, Q2={q2_count}, Q3={q3_count}, Q4={q4_count}")
        
        # 统计CAS分区
        cas1_count = sum(1 for item in processed_data if item['B'] == '1')
        cas2_count = sum(1 for item in processed_data if item['B'] == '2')
        cas3_count = sum(1 for item in processed_data if item['B'] == '3')
        cas4_count = sum(1 for item in processed_data if item['B'] == '4')
        
        logger.info(f"CAS分区统计: 1区={cas1_count}, 2区={cas2_count}, 3区={cas3_count}, 4区={cas4_count}")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"更新期刊数据失败: {e}")
        raise

if __name__ == "__main__":
    main()
