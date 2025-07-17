"""期刊信息服务模块，用于获取期刊影响因子、JCR分区、CAS分区等指标"""

import json
import os
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class JournalMetrics:
    """期刊指标数据类"""
    title: str = ""
    impact_factor: str = "N/A"
    jcr_quartile: str = "N/A"
    cas_quartile: str = "N/A"
    issn: str = ""
    eissn: str = ""


class JournalService:
    """期刊信息服务类"""
    
    def __init__(self):
        self.journal_data: Dict[str, Dict[str, Any]] = {}
        self.trend_data: Dict[str, Any] = {}
        self._load_journal_data()
    
    def _load_journal_data(self):
        """加载期刊数据文件"""
        try:
            # 加载主要期刊数据
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'journal_metrics')
            journal_file = os.path.join(data_dir, 'jcr_cas_ifqb.json')
            
            if os.path.exists(journal_file):
                logger.info(f"开始加载期刊数据: {journal_file}")
                with open(journal_file, 'r', encoding='utf-8') as f:
                    journals = json.load(f)
                    
                    if not isinstance(journals, list):
                        logger.error("期刊数据格式错误：应为列表类型")
                        return
                    
                    # 转换数据格式，按ISSN建立索引
                    for journal in journals:
                        if not isinstance(journal, dict):
                            continue
                        
                        # 提取ISSN列表
                        issns = []
                        if journal.get('issn'):
                            issns.append(journal['issn'])
                        if journal.get('eissn'):
                            issns.append(journal['eissn'])
                        
                        # 处理影响因子
                        impact_factor = journal.get('IF', 'N/A')
                        if impact_factor != 'N/A':
                            try:
                                impact_factor = float(impact_factor)
                            except (ValueError, TypeError):
                                impact_factor = 'N/A'
                                logger.warning(f"无效的影响因子值: {journal.get('IF')} for {journal.get('journal')}")
                        
                        # 处理分区信息
                        jcr_quartile = journal.get('Q', 'N/A')
                        cas_quartile = journal.get('B', 'N/A')
                        
                        # 处理CAS分区格式（B1 -> 1）
                        if cas_quartile and cas_quartile != 'N/A' and isinstance(cas_quartile, str):
                            if cas_quartile.startswith('B'):
                                cas_quartile = cas_quartile[1:]
                        
                        journal_info = {
                            'title': journal.get('journal', ''),
                            'impact_factor': impact_factor,
                            'jcr_quartile': jcr_quartile,
                            'cas_quartile': cas_quartile,
                            'issn': journal.get('issn', ''),
                            'eissn': journal.get('eissn', '')
                        }
                        
                        # 为每个ISSN都存储期刊信息
                        for issn_key in issns:
                            if issn_key:
                                # 存储带连字符和不带连字符的版本
                                self.journal_data[issn_key] = journal_info
                                # 如果ISSN有连字符，也存储无连字符版本
                                if '-' in issn_key:
                                    self.journal_data[issn_key.replace('-', '')] = journal_info
                                # 如果ISSN无连字符，也存储有连字符版本
                                elif len(issn_key) == 8:
                                    formatted_issn = f"{issn_key[:4]}-{issn_key[4:]}"
                                    self.journal_data[formatted_issn] = journal_info
                
                logger.info(f"成功加载 {len(self.journal_data)} 条期刊数据")
                
                # 记录一些转换后的数据示例
                if self.journal_data:
                    sample_converted = {k: self.journal_data[k] for k in list(self.journal_data.keys())[:3]}
                    logger.info(f"转换后的数据示例: {json.dumps(sample_converted, ensure_ascii=False)}")
                    
            else:
                logger.warning(f"期刊数据文件不存在: {journal_file}")
            
            # 加载五年影响因子趋势数据
            trend_file = os.path.join(data_dir, '5year.json')
            if os.path.exists(trend_file):
                logger.info(f"开始加载影响因子趋势数据: {trend_file}")
                with open(trend_file, 'r', encoding='utf-8') as f:
                    self.trend_data = json.load(f)
                    if not isinstance(self.trend_data, dict):
                        logger.error("影响因子趋势数据格式错误：应为字典类型")
                        self.trend_data = {}
                    else:
                        logger.info(f"成功加载影响因子趋势数据: {len(self.trend_data)} 条记录")
            else:
                logger.warning(f"影响因子趋势数据文件不存在: {trend_file}")
                
        except json.JSONDecodeError as e:
            logger.error(f"期刊数据文件格式错误: {str(e)}")
        except Exception as e:
            logger.error(f"加载期刊数据时发生错误: {str(e)}")
    
    def get_journal_metrics(self, issn: str) -> Optional[JournalMetrics]:
        """根据ISSN获取期刊指标
        
        Args:
            issn: 期刊的ISSN号
            
        Returns:
            JournalMetrics对象或None
        """
        if not issn:
            return None
            
        try:
            # 标准化ISSN格式（移除连字符）
            issn_clean = issn.replace('-', '')
            
            # 尝试直接获取
            journal_info = self.journal_data.get(issn_clean)
            
            if not journal_info:
                # 尝试其他格式的ISSN
                issn_with_hyphen = f"{issn_clean[:4]}-{issn_clean[4:]}"
                journal_info = self.journal_data.get(issn_with_hyphen)
            
            if not journal_info:
                # 尝试原始格式
                journal_info = self.journal_data.get(issn)
            
            if not journal_info:
                logger.warning(f"未找到ISSN对应的期刊信息: {issn}")
                return None
                
            logger.info(f"获取到的原始期刊信息: {json.dumps(journal_info, ensure_ascii=False)}")
            
            # 处理影响因子的显示格式
            impact_factor = journal_info.get('impact_factor', 'N/A')
            if isinstance(impact_factor, (int, float)) and impact_factor != 'N/A':
                impact_factor = f"{impact_factor:.3f}"  # 格式化为三位小数
            
            metrics = JournalMetrics(
                title=journal_info.get('title', ''),
                impact_factor=str(impact_factor),
                jcr_quartile=journal_info.get('jcr_quartile', 'N/A'),
                cas_quartile=journal_info.get('cas_quartile', 'N/A'),
                issn=journal_info.get('issn', ''),
                eissn=journal_info.get('eissn', '')
            )
            
            logger.info(f"处理后的期刊指标: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"获取期刊指标时发生错误: {str(e)}")
            return None
    
    def get_journal_metrics_by_name(self, journal_name: str) -> Optional[JournalMetrics]:
        """根据期刊名称获取期刊指标（模糊匹配）
        
        Args:
            journal_name: 期刊名称
            
        Returns:
            JournalMetrics对象或None
        """
        if not journal_name:
            return None
            
        try:
            journal_name_lower = journal_name.lower().strip()
            
            # 遍历所有期刊数据进行模糊匹配
            for issn, journal_info in self.journal_data.items():
                journal_title = journal_info.get('title', '').lower().strip()
                
                # 精确匹配或包含匹配
                if journal_title == journal_name_lower or journal_name_lower in journal_title:
                    logger.info(f"找到匹配的期刊: {journal_info.get('title')} (通过名称: {journal_name})")
                    
                    impact_factor = journal_info.get('impact_factor', 'N/A')
                    if isinstance(impact_factor, (int, float)) and impact_factor != 'N/A':
                        impact_factor = f"{impact_factor:.3f}"
                    
                    return JournalMetrics(
                        title=journal_info.get('title', ''),
                        impact_factor=str(impact_factor),
                        jcr_quartile=journal_info.get('jcr_quartile', 'N/A'),
                        cas_quartile=journal_info.get('cas_quartile', 'N/A'),
                        issn=journal_info.get('issn', ''),
                        eissn=journal_info.get('eissn', '')
                    )
            
            logger.warning(f"未找到匹配的期刊: {journal_name}")
            return None
            
        except Exception as e:
            logger.error(f"通过期刊名称获取指标时发生错误: {str(e)}")
            return None
    
    def get_if_trend(self, issn: str) -> Optional[Dict[str, Any]]:
        """获取期刊近五年影响因子趋势
        
        Args:
            issn: 期刊的ISSN号
            
        Returns:
            趋势数据字典或None
        """
        if not issn or issn not in self.trend_data:
            return None
        return self.trend_data[issn]
    
    def search_journals(self, keyword: str, limit: int = 10) -> list:
        """搜索期刊
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            期刊列表
        """
        results = []
        keyword_lower = keyword.lower().strip()
        
        try:
            for issn, journal_info in self.journal_data.items():
                if len(results) >= limit:
                    break
                    
                journal_title = journal_info.get('title', '').lower()
                if keyword_lower in journal_title:
                    impact_factor = journal_info.get('impact_factor', 'N/A')
                    if isinstance(impact_factor, (int, float)) and impact_factor != 'N/A':
                        impact_factor = f"{impact_factor:.3f}"
                    
                    results.append({
                        'title': journal_info.get('title', ''),
                        'issn': journal_info.get('issn', ''),
                        'eissn': journal_info.get('eissn', ''),
                        'impact_factor': str(impact_factor),
                        'jcr_quartile': journal_info.get('jcr_quartile', 'N/A'),
                        'cas_quartile': journal_info.get('cas_quartile', 'N/A')
                    })
        except Exception as e:
            logger.error(f"搜索期刊时发生错误: {str(e)}")
        
        return results
    
    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态
        
        Returns:
            服务状态信息
        """
        return {
            'service': 'Journal',
            'journals_loaded': len(self.journal_data),
            'trend_data_loaded': len(self.trend_data),
            'status': 'active' if self.journal_data else 'no_data'
        }


# 全局期刊服务实例
journal_service = JournalService()