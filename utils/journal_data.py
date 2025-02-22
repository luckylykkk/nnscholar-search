import os
import json
import logging

logger = logging.getLogger(__name__)

def load_journal_data(base_dir: str) -> dict:
    """加载期刊相关数据"""
    try:
        data_dir = os.path.join(base_dir, 'data', 'journal_metrics')
        jcr_file = os.path.join(data_dir, 'jcr_cas_ifqb.json')
        
        if not os.path.exists(jcr_file):
            logger.error(f"期刊数据文件不存在: {jcr_file}")
            return {}
            
        logger.info(f"开始加载期刊数据文件: {jcr_file}")
        with open(jcr_file, 'r', encoding='utf-8') as f:
            journal_list = json.load(f)
            
        # 转换为以ISSN为键的字典
        journal_data = {}
        for journal in journal_list:
            issn = journal.get('issn', '').strip()
            eissn = journal.get('eissn', '').strip()
            
            if not (issn or eissn):
                continue
                
            journal_info = {
                'title': journal.get('journal', ''),
                'if': journal.get('IF', 'N/A'),
                'jcr_quartile': journal.get('Q', 'N/A'),
                'cas_quartile': journal.get('B', 'N/A')  # 确保这里的值是 'B1', 'B2' 等格式
            }
            
            if issn:
                journal_data[issn] = journal_info
            if eissn:
                journal_data[eissn] = journal_info
                
        # 添加日志以验证数据格式
        if len(journal_data) % 1000 == 0:  # 每1000条记录记录一次示例
            logger.info(f"期刊数据示例: {journal_info}")
        
        logger.info(f"成功加载 {len(journal_data)} 条期刊数据")
        return journal_data
        
    except Exception as e:
        logger.error(f"加载期刊数据失败: {str(e)}")
        return {} 