"""
CSV文件领域验证器
提供CSV文件的领域验证和文件分类功能
"""
import pandas as pd
import os
import logging
import traceback

logger = logging.getLogger(__name__)

class CSVValidator:
    def __init__(self):
        """初始化验证器"""
        pass
        
    def prompt_construct(self, record, domain):
        """构建用于验证的prompt"""
        try:
            prompt = f"""
            请根据以下信息判断论文是否属于{domain}领域:
            标题: {record['标题']}
            作者: {record['作者']}
            摘要: {record['摘要']}
            发表年份: {record['发表年份']}
            期刊名称: {record['期刊名称']}
            结果只需要返回True或False
            """
            return prompt.strip()
        except Exception as e:
            logger.error(f"构建prompt时出错: {str(e)}")
            raise

    def run_LLM(self, prompt):
        """运行LLM模型进行验证"""
        try:
            from utils.deepseek_client import DeepSeekClient
            client = DeepSeekClient()
            result = client.analyze_text(prompt)
            logger.debug(f"LLM响应: {result}")
            return result.lower().strip() == 'true'
        except Exception as e:
            logger.error(f"运行LLM时出错: {str(e)}")
            raise

    def read_csv_iterator(self, csv_path):
        """CSV文件迭代器"""
        try:
            logger.info(f"开始读取CSV文件: {csv_path}")
            df = pd.read_csv(csv_path)
            logger.info(f"成功读取CSV文件，共 {len(df)} 行")
            
            for idx, row in df.iterrows():
                try:
                    record = {
                        '标题': row.get('标题', ''),
                        '作者': row.get('作者', ''),
                        '摘要': row.get('摘要', ''),
                        '发表年份': row.get('发表年份', ''),
                        '期刊名称': row.get('期刊名称', ''),
                        '影响因子': row.get('影响因子', 'N/A'),
                        'JCR分区': row.get('JCR分区', 'N/A'),
                        'CAS分区': row.get('CAS分区', 'N/A'),
                        'DOI': row.get('DOI', ''),
                        'PMID': row.get('PMID', ''),
                        '引用次数': row.get('引用次数', 0),
                        'PDF链接': row.get('PDF链接', '')
                    }
                    yield record, row.to_dict()
                except Exception as e:
                    logger.error(f"处理第 {idx} 行时出错: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"读取CSV文件时出错: {str(e)}\n{traceback.format_exc()}")
            raise

    def validate_csv(self, csv_path, domain):
        """验证CSV文件并生成结果文件"""
        try:
            logger.info(f"开始验证CSV文件: {csv_path}, 目标领域: {domain}")
            
            # 获取文件名和目录
            dir_path = os.path.dirname(csv_path)
            file_name = os.path.splitext(os.path.basename(csv_path))[0]
            
            # 创建两个列表来存储结果
            valid_records = []
            invalid_records = []
            
            # 处理每条记录
            total_count = 0
            for record, full_record in self.read_csv_iterator(csv_path):
                try:
                    total_count += 1
                    logger.info(f"正在处理第 {total_count} 条记录")
                    
                    prompt = self.prompt_construct(record, domain)
                    is_valid = self.run_LLM(prompt)
                    
                    if is_valid:
                        valid_records.append(full_record)
                        logger.debug(f"记录符合领域要求: {record['标题']}")
                    else:
                        invalid_records.append(full_record)
                        logger.debug(f"记录不符合领域要求: {record['标题']}")
                        
                except Exception as e:
                    logger.error(f"处理记录时出错: {str(e)}")
                    continue
            
            # 创建输出文件路径
            valid_file_path = os.path.join(dir_path, f"{file_name}_校验.csv")
            invalid_file_path = os.path.join(dir_path, f"{file_name}_exclude.csv")
            
            # 保存结果
            if valid_records:
                pd.DataFrame(valid_records).to_csv(valid_file_path, index=False)
                logger.info(f"已保存符合条件的记录: {valid_file_path}")
                
            if invalid_records:
                pd.DataFrame(invalid_records).to_csv(invalid_file_path, index=False)
                logger.info(f"已保存不符合条件的记录: {invalid_file_path}")
            
            results = {
                'valid_file': valid_file_path if valid_records else None,
                'invalid_file': invalid_file_path if invalid_records else None,
                'valid_count': len(valid_records),
                'invalid_count': len(invalid_records),
                'total_count': total_count
            }
            
            logger.info(f"验证完成: {results}")
            return results
            
        except Exception as e:
            logger.error(f"验证CSV文件时出错: {str(e)}\n{traceback.format_exc()}")
            raise 

    def validate_single_record(self, record, domain):
        """验证单条记录"""
        try:
            prompt = self.prompt_construct(record, domain)
            is_valid = self.run_LLM(prompt)
            return is_valid
        except Exception as e:
            logger.error(f"验证单条记录时出错: {str(e)}")
            raise 