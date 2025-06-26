"""
集成多数据库搜索模块
将多个数据库的搜索结果整合，适配现有的PubMed逻辑
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
from multi_database_search import MultiDatabaseSearcher, DATABASE_CONFIGS
from data_normalizer import LiteratureDataNormalizer
import asyncio
import concurrent.futures
from functools import partial

logger = logging.getLogger(__name__)

class IntegratedSearchEngine:
    """集成搜索引擎"""
    
    def __init__(self):
        self.searcher = MultiDatabaseSearcher()
        self.normalizer = LiteratureDataNormalizer()
        
        # 数据库优先级配置
        self.database_priority = {
            'pubmed': 1,      # 医学领域优先PubMed
            'openalex': 2,    # 全学科综合数据库
            'semantic_scholar': 3,  # AI增强搜索
            'crossref': 4,    # 权威元数据
            'arxiv': 5,       # 预印本
            'doaj': 6         # 开放获取
        }
        
        # 领域特定的数据库推荐
        self.field_specific_databases = {
            'medicine': ['pubmed', 'openalex', 'semantic_scholar'],
            'biology': ['pubmed', 'openalex', 'arxiv', 'semantic_scholar'],
            'physics': ['arxiv', 'openalex', 'semantic_scholar'],
            'mathematics': ['arxiv', 'openalex', 'semantic_scholar'],
            'computer_science': ['arxiv', 'semantic_scholar', 'openalex'],
            'chemistry': ['openalex', 'semantic_scholar', 'crossref'],
            'engineering': ['openalex', 'semantic_scholar', 'crossref'],
            'social_sciences': ['openalex', 'crossref', 'doaj'],
            'humanities': ['openalex', 'crossref', 'doaj'],
            'general': ['openalex', 'semantic_scholar', 'crossref', 'arxiv', 'doaj']
        }
    
    def search_multiple_databases(self, query: str, max_results: int = 600, 
                                databases: Optional[List[str]] = None,
                                field: str = 'general') -> Tuple[List[Dict], str, int, int]:
        """
        搜索多个数据库并整合结果
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            databases: 指定要搜索的数据库列表，None表示自动选择
            field: 研究领域，用于自动选择合适的数据库
            
        Returns:
            (papers, search_strategy, total_count, filtered_count)
        """
        try:
            logger.info(f"开始集成搜索，查询: {query}, 领域: {field}, 最大结果数: {max_results}")
            
            # 自动选择数据库
            if databases is None:
                databases = self._select_databases_for_field(field)
            
            logger.info(f"选择的数据库: {databases}")
            
            # 计算每个数据库的结果数分配
            results_per_db = max(50, max_results // len(databases))
            
            all_papers = []
            total_count = 0
            search_strategy = query
            
            # 并行搜索多个数据库
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 提交搜索任务
                future_to_db = {}
                
                for db_name in databases:
                    if db_name == 'pubmed':
                        # PubMed使用现有的搜索函数
                        continue
                    
                    search_func = getattr(self.searcher, f'search_{db_name}', None)
                    if search_func:
                        future = executor.submit(search_func, query, results_per_db)
                        future_to_db[future] = db_name
                
                # 收集结果
                for future in concurrent.futures.as_completed(future_to_db):
                    db_name = future_to_db[future]
                    try:
                        papers, _, db_total, db_count = future.result(timeout=60)
                        
                        # 规范化数据
                        normalized_papers = self.normalizer.normalize_papers(papers, db_name)
                        all_papers.extend(normalized_papers)
                        total_count += db_total
                        
                        logger.info(f"数据库 {db_name} 搜索完成: {db_count} 篇文献")
                        
                    except Exception as e:
                        logger.error(f"数据库 {db_name} 搜索失败: {e}")
            
            # 如果包含PubMed，需要单独处理
            if 'pubmed' in databases:
                try:
                    # 这里需要调用现有的PubMed搜索函数
                    # pubmed_papers, _, pubmed_total, pubmed_count = search_pubmed(query, results_per_db)
                    # all_papers.extend(pubmed_papers)
                    # total_count += pubmed_total
                    logger.info("PubMed搜索需要在主应用中集成")
                except Exception as e:
                    logger.error(f"PubMed搜索失败: {e}")
            
            # 去重和排序
            unique_papers = self.normalizer.merge_duplicate_papers(all_papers)
            
            # 按相关度排序（如果有的话）
            unique_papers.sort(key=lambda x: x.get('relevance', 0), reverse=True)
            
            # 限制结果数量
            final_papers = unique_papers[:max_results]
            
            logger.info(f"集成搜索完成，总计找到 {total_count} 篇，去重后 {len(unique_papers)} 篇，最终返回 {len(final_papers)} 篇")
            
            return final_papers, search_strategy, total_count, len(final_papers)
            
        except Exception as e:
            logger.error(f"集成搜索出错: {e}")
            return [], query, 0, 0
    
    def _select_databases_for_field(self, field: str) -> List[str]:
        """根据研究领域选择合适的数据库"""
        
        # 关键词到领域的映射
        field_keywords = {
            'medicine': ['medical', 'clinical', 'patient', 'disease', 'treatment', 'therapy', 'drug', 'medicine', 'health'],
            'biology': ['biological', 'gene', 'protein', 'cell', 'molecular', 'organism', 'species', 'evolution'],
            'physics': ['physics', 'quantum', 'particle', 'energy', 'force', 'wave', 'matter'],
            'mathematics': ['mathematical', 'equation', 'theorem', 'proof', 'algorithm', 'statistics'],
            'computer_science': ['computer', 'software', 'algorithm', 'programming', 'artificial intelligence', 'machine learning', 'data'],
            'chemistry': ['chemical', 'molecule', 'reaction', 'compound', 'synthesis', 'catalyst'],
            'engineering': ['engineering', 'design', 'system', 'technology', 'manufacturing', 'construction'],
            'social_sciences': ['social', 'society', 'psychology', 'economics', 'politics', 'education'],
            'humanities': ['literature', 'history', 'philosophy', 'culture', 'language', 'art']
        }
        
        # 尝试从查询中推断领域
        query_lower = field.lower()
        detected_field = 'general'
        
        for field_name, keywords in field_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_field = field_name
                break
        
        # 返回该领域推荐的数据库
        return self.field_specific_databases.get(detected_field, self.field_specific_databases['general'])
    
    def get_database_info(self) -> Dict[str, Dict]:
        """获取所有支持的数据库信息"""
        return DATABASE_CONFIGS
    
    def search_single_database(self, database: str, query: str, max_results: int = 600) -> Tuple[List[Dict], str, int, int]:
        """搜索单个数据库"""
        try:
            search_func = getattr(self.searcher, f'search_{database}', None)
            if not search_func:
                logger.error(f"不支持的数据库: {database}")
                return [], query, 0, 0
            
            papers, search_strategy, total_count, result_count = search_func(query, max_results)
            
            # 规范化数据
            normalized_papers = self.normalizer.normalize_papers(papers, database)
            
            return normalized_papers, search_strategy, total_count, len(normalized_papers)
            
        except Exception as e:
            logger.error(f"搜索数据库 {database} 时出错: {e}")
            return [], query, 0, 0
    
    def get_recommended_databases(self, query: str) -> List[str]:
        """根据查询推荐合适的数据库"""
        field = self._detect_field_from_query(query)
        return self._select_databases_for_field(field)
    
    def _detect_field_from_query(self, query: str) -> str:
        """从查询中检测研究领域"""
        query_lower = query.lower()
        
        # 医学关键词
        medical_keywords = ['medical', 'clinical', 'patient', 'disease', 'treatment', 'therapy', 'drug', 'medicine', 'health', 'hospital', 'diagnosis', 'surgery', 'cancer', 'diabetes', 'cardiovascular']
        
        # 生物学关键词
        biology_keywords = ['biological', 'gene', 'protein', 'cell', 'molecular', 'organism', 'species', 'evolution', 'dna', 'rna', 'genome', 'bacteria', 'virus']
        
        # 物理学关键词
        physics_keywords = ['physics', 'quantum', 'particle', 'energy', 'force', 'wave', 'matter', 'electromagnetic', 'thermodynamics', 'mechanics']
        
        # 计算机科学关键词
        cs_keywords = ['computer', 'software', 'algorithm', 'programming', 'artificial intelligence', 'machine learning', 'data', 'neural network', 'deep learning']
        
        # 检测领域
        if any(keyword in query_lower for keyword in medical_keywords):
            return 'medicine'
        elif any(keyword in query_lower for keyword in biology_keywords):
            return 'biology'
        elif any(keyword in query_lower for keyword in physics_keywords):
            return 'physics'
        elif any(keyword in query_lower for keyword in cs_keywords):
            return 'computer_science'
        else:
            return 'general'
    
    def combine_with_pubmed(self, pubmed_papers: List[Dict], other_papers: List[Dict]) -> List[Dict]:
        """
        将PubMed结果与其他数据库结果合并
        """
        try:
            # 将PubMed论文标记为来源
            for paper in pubmed_papers:
                paper['database'] = 'PubMed'
            
            # 合并所有论文
            all_papers = pubmed_papers + other_papers
            
            # 去重
            unique_papers = self.normalizer.merge_duplicate_papers(all_papers)
            
            # 按数据库优先级和相关度排序
            def sort_key(paper):
                db_priority = self.database_priority.get(paper.get('database', '').lower(), 999)
                relevance = paper.get('relevance', 0)
                return (db_priority, -relevance)  # 优先级越小越好，相关度越大越好
            
            unique_papers.sort(key=sort_key)
            
            logger.info(f"合并PubMed和其他数据库结果: PubMed {len(pubmed_papers)} 篇, 其他 {len(other_papers)} 篇, 去重后 {len(unique_papers)} 篇")
            
            return unique_papers
            
        except Exception as e:
            logger.error(f"合并PubMed和其他数据库结果时出错: {e}")
            return pubmed_papers + other_papers


# 全局搜索引擎实例
integrated_search_engine = IntegratedSearchEngine()


def search_multiple_databases_api(query: str, max_results: int = 600, 
                                databases: Optional[List[str]] = None,
                                field: str = 'general') -> Tuple[List[Dict], str, int, int]:
    """
    API接口函数，用于在主应用中调用
    """
    return integrated_search_engine.search_multiple_databases(query, max_results, databases, field)


def get_database_recommendations(query: str) -> List[str]:
    """
    获取查询推荐的数据库
    """
    return integrated_search_engine.get_recommended_databases(query)


def get_supported_databases() -> Dict[str, Dict]:
    """
    获取所有支持的数据库信息
    """
    return integrated_search_engine.get_database_info()
