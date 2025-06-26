"""
测试其他数据库的检索功能
验证各个数据库是否可以成功检索文献，以及返回数据的格式差异
"""

import logging
import json
import time
from typing import Dict, List, Any
from multi_database_search import MultiDatabaseSearcher
from data_normalizer import LiteratureDataNormalizer
from intelligent_search_router import IntelligentSearchRouter

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseRetrievalTester:
    """数据库检索测试器"""
    
    def __init__(self):
        self.searcher = MultiDatabaseSearcher()
        self.normalizer = LiteratureDataNormalizer()
        self.router = IntelligentSearchRouter()
        
        # 测试查询
        self.test_queries = {
            'medical': '糖尿病药物治疗',
            'computer_science': '深度学习算法',
            'physics': '量子计算',
            'general': '气候变化研究'
        }
        
        # 数据库列表
        self.databases = ['openalex', 'arxiv', 'semantic_scholar', 'doaj', 'crossref']
    
    def test_single_database(self, database: str, query: str, max_results: int = 10) -> Dict[str, Any]:
        """测试单个数据库的检索功能"""
        logger.info(f"测试数据库: {database}, 查询: {query}")
        
        result = {
            'database': database,
            'query': query,
            'success': False,
            'papers': [],
            'total_count': 0,
            'result_count': 0,
            'error': None,
            'response_time': 0,
            'data_format': {}
        }
        
        try:
            start_time = time.time()
            
            # 根据数据库选择对应的搜索函数
            if database == 'openalex':
                papers, search_strategy, total_count, result_count = self.searcher.search_openalex(query, max_results)
            elif database == 'arxiv':
                papers, search_strategy, total_count, result_count = self.searcher.search_arxiv(query, max_results)
            elif database == 'semantic_scholar':
                papers, search_strategy, total_count, result_count = self.searcher.search_semantic_scholar(query, max_results)
            elif database == 'doaj':
                papers, search_strategy, total_count, result_count = self.searcher.search_doaj(query, max_results)
            elif database == 'crossref':
                papers, search_strategy, total_count, result_count = self.searcher.search_crossref(query, max_results)
            else:
                raise ValueError(f"不支持的数据库: {database}")
            
            end_time = time.time()
            response_time = end_time - start_time
            
            result.update({
                'success': True,
                'papers': papers,
                'total_count': total_count,
                'result_count': result_count,
                'response_time': response_time,
                'search_strategy': search_strategy
            })
            
            # 分析数据格式
            if papers:
                sample_paper = papers[0]
                result['data_format'] = {
                    'fields': list(sample_paper.keys()),
                    'sample_title': sample_paper.get('title', ''),
                    'has_abstract': bool(sample_paper.get('abstract')),
                    'has_authors': bool(sample_paper.get('authors')),
                    'has_journal': bool(sample_paper.get('journal')),
                    'has_doi': bool(sample_paper.get('doi')),
                    'has_url': bool(sample_paper.get('url')),
                    'database_specific_fields': [k for k in sample_paper.keys() 
                                               if k not in ['title', 'authors', 'abstract', 'journal', 'pub_year', 'doi', 'url']]
                }
            
            logger.info(f"✅ {database} 检索成功: {result_count} 篇文献, 用时 {response_time:.2f}s")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ {database} 检索失败: {e}")
        
        return result
    
    def test_all_databases(self) -> Dict[str, Dict]:
        """测试所有数据库"""
        logger.info("开始测试所有数据库的检索功能")
        
        results = {}
        
        for query_type, query in self.test_queries.items():
            logger.info(f"\n测试查询类型: {query_type} - '{query}'")
            results[query_type] = {}
            
            for database in self.databases:
                result = self.test_single_database(database, query, max_results=5)
                results[query_type][database] = result
                
                # 添加延迟避免API限制
                time.sleep(1)
        
        return results
    
    def test_data_normalization(self) -> Dict[str, Any]:
        """测试数据规范化功能"""
        logger.info("测试数据规范化功能")
        
        normalization_results = {}
        
        # 测试每个数据库的数据规范化
        for database in self.databases:
            try:
                # 获取一些样本数据
                papers, _, _, _ = getattr(self.searcher, f'search_{database}')('machine learning', 3)
                
                if papers:
                    # 规范化数据
                    normalized_papers = self.normalizer.normalize_papers(papers, database)
                    
                    normalization_results[database] = {
                        'original_count': len(papers),
                        'normalized_count': len(normalized_papers),
                        'success': True,
                        'sample_normalized': normalized_papers[0] if normalized_papers else None
                    }
                    
                    logger.info(f"✅ {database} 数据规范化成功: {len(papers)} -> {len(normalized_papers)}")
                else:
                    normalization_results[database] = {
                        'success': False,
                        'error': '没有获取到原始数据'
                    }
                    
            except Exception as e:
                normalization_results[database] = {
                    'success': False,
                    'error': str(e)
                }
                logger.error(f"❌ {database} 数据规范化失败: {e}")
        
        return normalization_results
    
    def test_intelligent_routing(self) -> Dict[str, Any]:
        """测试智能路由功能"""
        logger.info("测试智能路由功能")
        
        routing_results = {}
        
        for query_type, query in self.test_queries.items():
            try:
                # 测试智能路由
                recommended_db, detected_field, analysis_info = self.router.analyze_query_and_select_database(query)
                
                # 生成检索策略
                search_strategy = self.router.convert_to_search_strategy(query, recommended_db, detected_field)
                
                routing_results[query_type] = {
                    'query': query,
                    'recommended_database': recommended_db,
                    'detected_field': detected_field,
                    'search_strategy': search_strategy,
                    'analysis_method': analysis_info.get('selection_method', 'unknown'),
                    'success': True
                }
                
                logger.info(f"✅ {query_type} 智能路由成功: {recommended_db}")
                
            except Exception as e:
                routing_results[query_type] = {
                    'query': query,
                    'success': False,
                    'error': str(e)
                }
                logger.error(f"❌ {query_type} 智能路由失败: {e}")
        
        return routing_results
    
    def generate_report(self, results: Dict) -> str:
        """生成测试报告"""
        report = []
        report.append("=" * 80)
        report.append("多数据库检索功能测试报告")
        report.append("=" * 80)
        
        # 数据库检索测试结果
        report.append("\n1. 数据库检索测试结果:")
        report.append("-" * 50)
        
        for query_type, db_results in results['database_tests'].items():
            report.append(f"\n查询类型: {query_type}")
            for database, result in db_results.items():
                if result['success']:
                    report.append(f"  ✅ {database}: {result['result_count']} 篇文献, {result['response_time']:.2f}s")
                else:
                    report.append(f"  ❌ {database}: {result['error']}")
        
        # 数据格式分析
        report.append("\n\n2. 数据格式分析:")
        report.append("-" * 50)
        
        for query_type, db_results in results['database_tests'].items():
            report.append(f"\n{query_type} 查询的数据格式:")
            for database, result in db_results.items():
                if result['success'] and result['data_format']:
                    format_info = result['data_format']
                    report.append(f"  {database}:")
                    report.append(f"    字段数: {len(format_info['fields'])}")
                    report.append(f"    特有字段: {format_info['database_specific_fields']}")
                    report.append(f"    有摘要: {format_info['has_abstract']}")
                    report.append(f"    有DOI: {format_info['has_doi']}")
        
        # 数据规范化测试结果
        if 'normalization_tests' in results:
            report.append("\n\n3. 数据规范化测试结果:")
            report.append("-" * 50)
            
            for database, result in results['normalization_tests'].items():
                if result['success']:
                    report.append(f"  ✅ {database}: {result['original_count']} -> {result['normalized_count']} 篇")
                else:
                    report.append(f"  ❌ {database}: {result['error']}")
        
        # 智能路由测试结果
        if 'routing_tests' in results:
            report.append("\n\n4. 智能路由测试结果:")
            report.append("-" * 50)
            
            for query_type, result in results['routing_tests'].items():
                if result['success']:
                    report.append(f"  ✅ {query_type}: 推荐 {result['recommended_database']}")
                    report.append(f"    检测领域: {result['detected_field']}")
                    report.append(f"    检索策略: {result['search_strategy'][:60]}...")
                else:
                    report.append(f"  ❌ {query_type}: {result['error']}")
        
        report.append("\n" + "=" * 80)
        report.append("测试完成")
        report.append("=" * 80)
        
        return "\n".join(report)

def main():
    """主测试函数"""
    tester = DatabaseRetrievalTester()
    
    print("开始多数据库检索功能测试...")
    
    # 执行所有测试
    all_results = {}
    
    # 1. 测试数据库检索
    all_results['database_tests'] = tester.test_all_databases()
    
    # 2. 测试数据规范化
    all_results['normalization_tests'] = tester.test_data_normalization()
    
    # 3. 测试智能路由
    all_results['routing_tests'] = tester.test_intelligent_routing()
    
    # 生成并显示报告
    report = tester.generate_report(all_results)
    print(report)
    
    # 保存详细结果到文件
    with open('database_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细测试结果已保存到: database_test_results.json")
    
    return all_results

if __name__ == "__main__":
    results = main()
