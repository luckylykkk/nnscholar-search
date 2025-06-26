"""
演示集成模块
展示多数据库搜索和智能路由的功能
"""

import logging
from typing import Dict, List
from intelligent_search_router import IntelligentSearchRouter

logger = logging.getLogger(__name__)

class DemoIntegration:
    """演示集成类"""
    
    def __init__(self):
        self.router = IntelligentSearchRouter()
    
    def demo_intelligent_routing(self, user_queries: List[str]) -> Dict:
        """
        演示智能路由功能（单数据库选择）
        """
        results = {}

        for query in user_queries:
            try:
                # 分析查询并选择最佳数据库
                best_database, field, analysis = self.router.analyze_query_and_select_database(query)

                # 为推荐的数据库生成检索式
                search_strategy = self.router.convert_to_search_strategy(query, best_database, field)

                results[query] = {
                    'detected_field': field,
                    'recommended_database': best_database,
                    'search_strategy': search_strategy,
                    'analysis_info': analysis
                }

            except Exception as e:
                logger.error(f"处理查询 '{query}' 时出错: {e}")
                results[query] = {'error': str(e)}

        return results
    
    def demo_database_coverage(self) -> Dict:
        """
        演示数据库覆盖范围
        """
        from multi_database_search import DATABASE_CONFIGS
        
        coverage_info = {}
        
        for db_name, config in DATABASE_CONFIGS.items():
            coverage_info[db_name] = {
                'name': config['name'],
                'description': config['description'],
                'coverage': config['coverage'],
                'api_limit': config['api_limit'],
                'free': config['free']
            }
        
        return coverage_info
    
    def demo_search_strategies(self) -> Dict:
        """
        演示不同数据库的检索策略转换
        """
        test_queries = [
            "冠心病的药物治疗研究",
            "机器学习在医学影像诊断中的应用",
            "量子计算算法优化",
            "气候变化对生态系统的影响",
            "深度学习神经网络架构"
        ]
        
        databases = ['pubmed', 'arxiv', 'semantic_scholar', 'openalex', 'doaj']
        
        strategy_examples = {}
        
        for query in test_queries:
            strategy_examples[query] = {}

            # 智能推荐（单数据库）
            recommended_db, field, _ = self.router.analyze_query_and_select_database(query)
            strategy_examples[query]['recommended_database'] = recommended_db
            strategy_examples[query]['detected_field'] = field

            # 为每个数据库生成检索式（用于对比）
            for db in databases:
                try:
                    strategy = self.router.convert_to_search_strategy(query, db, field)
                    strategy_examples[query][db] = strategy
                except Exception as e:
                    strategy_examples[query][db] = f"Error: {e}"
        
        return strategy_examples


def run_demo():
    """运行演示"""
    demo = DemoIntegration()
    
    print("=" * 80)
    print("多数据库学术文献检索系统演示")
    print("=" * 80)
    
    # 1. 演示数据库覆盖范围
    print("\n1. 支持的数据库及其覆盖范围:")
    print("-" * 50)
    
    coverage = demo.demo_database_coverage()
    for db_name, info in coverage.items():
        print(f"\n{info['name']} ({db_name})")
        print(f"  描述: {info['description']}")
        print(f"  覆盖范围: {info['coverage']}")
        print(f"  API限制: {info['api_limit']} 条/次")
        print(f"  免费使用: {'是' if info['free'] else '否'}")
    
    # 2. 演示智能路由
    print("\n\n2. 智能数据库选择演示:")
    print("-" * 50)
    
    test_queries = [
        "糖尿病的药物治疗研究",
        "深度学习算法优化",
        "量子物理理论研究",
        "环境保护政策分析"
    ]
    
    routing_results = demo.demo_intelligent_routing(test_queries)
    
    for query, result in routing_results.items():
        if 'error' in result:
            print(f"\n查询: {query}")
            print(f"  错误: {result['error']}")
            continue
            
        print(f"\n查询: {query}")
        print(f"  检测领域: {result['detected_field']}")
        print(f"  推荐数据库: {result['recommended_database']}")

        strategy = result['search_strategy']
        print(f"  检索策略: {strategy[:100]}..." if len(strategy) > 100 else f"  检索策略: {strategy}")
    
    # 3. 演示检索策略转换
    print("\n\n3. 检索策略转换演示:")
    print("-" * 50)
    
    strategy_examples = demo.demo_search_strategies()
    
    for query, strategies in list(strategy_examples.items())[:2]:  # 只显示前2个例子
        print(f"\n查询: {query}")
        print(f"推荐数据库: {strategies.get('recommended_database', '未知')}")
        print(f"检测领域: {strategies.get('detected_field', '未知')}")

        print("不同数据库的检索策略对比:")
        recommended_db = strategies.get('recommended_database', '')
        for db in ['pubmed', 'arxiv', 'semantic_scholar']:
            if db in strategies:
                strategy = strategies[db]
                if len(strategy) > 80:
                    strategy = strategy[:80] + "..."
                marker = " ⭐ (推荐)" if db == recommended_db else ""
                print(f"  {db}: {strategy}{marker}")
    
    print("\n" + "=" * 80)
    print("演示完成")
    print("=" * 80)


if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    
    # 运行演示
    run_demo()
