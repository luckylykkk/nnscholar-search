"""
测试单数据库选择功能
验证智能路由是否能正确选择最适合的单个数据库
"""

import logging
from intelligent_search_router import IntelligentSearchRouter

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_single_database_selection():
    """测试单数据库选择功能"""
    
    router = IntelligentSearchRouter()
    
    # 测试用例：不同领域的查询
    test_cases = [
        {
            'query': '糖尿病的药物治疗研究',
            'expected_db': 'pubmed',
            'description': '医学领域查询，应推荐PubMed'
        },
        {
            'query': '深度学习神经网络算法优化',
            'expected_db': 'arxiv',
            'description': '计算机科学理论，应推荐arXiv'
        },
        {
            'query': '机器学习在图像识别中的应用',
            'expected_db': 'semantic_scholar',
            'description': '计算机科学应用，应推荐Semantic Scholar'
        },
        {
            'query': '气候变化对社会经济的影响',
            'expected_db': 'openalex',
            'description': '跨学科研究，应推荐OpenAlex'
        },
        {
            'query': '开放科学政策研究',
            'expected_db': 'doaj',
            'description': '开放获取相关，应推荐DOAJ'
        },
        {
            'query': '量子计算理论基础',
            'expected_db': 'arxiv',
            'description': '物理学理论，应推荐arXiv'
        },
        {
            'query': '心血管疾病的临床诊断',
            'expected_db': 'pubmed',
            'description': '临床医学，应推荐PubMed'
        }
    ]
    
    print("=" * 80)
    print("单数据库选择功能测试")
    print("=" * 80)
    
    correct_predictions = 0
    total_tests = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        query = test_case['query']
        expected_db = test_case['expected_db']
        description = test_case['description']
        
        print(f"\n测试 {i}/{total_tests}: {description}")
        print(f"查询: {query}")
        print(f"期望数据库: {expected_db}")
        
        try:
            # 执行智能路由分析
            recommended_db, detected_field, analysis_info = router.analyze_query_and_select_database(query)
            
            print(f"推荐数据库: {recommended_db}")
            print(f"检测领域: {detected_field}")
            
            # 检查是否推荐正确
            if recommended_db == expected_db:
                print("✅ 推荐正确")
                correct_predictions += 1
            else:
                print("❌ 推荐错误")
            
            # 生成检索式
            try:
                search_strategy = router.convert_to_search_strategy(query, recommended_db, detected_field)
                print(f"检索策略: {search_strategy[:100]}..." if len(search_strategy) > 100 else f"检索策略: {search_strategy}")
            except Exception as e:
                print(f"检索策略生成失败: {e}")
            
            # 显示分析方法
            selection_method = analysis_info.get('selection_method', 'unknown')
            print(f"选择方法: {selection_method}")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
        
        print("-" * 60)
    
    # 显示总体结果
    accuracy = (correct_predictions / total_tests) * 100
    print(f"\n总体测试结果:")
    print(f"正确预测: {correct_predictions}/{total_tests}")
    print(f"准确率: {accuracy:.1f}%")
    
    if accuracy >= 80:
        print("🎉 测试通过！智能路由功能表现良好")
    elif accuracy >= 60:
        print("⚠️  测试部分通过，需要优化提示词")
    else:
        print("❌ 测试失败，需要重新设计路由逻辑")
    
    return accuracy

def test_database_specific_strategies():
    """测试不同数据库的检索策略生成"""

    router = IntelligentSearchRouter()

    print("\n" + "=" * 80)
    print("数据库特定检索策略测试")
    print("=" * 80)

    test_query = "糖尿病药物治疗"  # 使用医学相关查询更好地测试PubMed
    databases = ['pubmed', 'arxiv', 'semantic_scholar', 'openalex', 'doaj']

    print(f"测试查询: {test_query}")
    print("\n不同数据库的检索策略:")

    for db in databases:
        try:
            strategy = router.convert_to_search_strategy(test_query, db, '医学')
            print(f"\n{db.upper()}:")
            print(f"  策略: {strategy}")

            # 验证策略是否包含数据库特定的语法
            if db == 'pubmed':
                if '[Title/Abstract]' in strategy and '"' in strategy:
                    print("  ✅ 包含PubMed特定语法（使用app.py中的提示词）")
                elif '[MeSH]' in strategy:
                    print("  ✅ 包含PubMed MeSH语法")
                else:
                    print("  ⚠️  PubMed策略格式需要检查")
            elif db == 'arxiv' and ('cat:' in strategy or 'cs.' in strategy):
                print("  ✅ 包含arXiv特定语法")
            elif db == 'semantic_scholar' and ('"' in strategy and 'AND' in strategy):
                print("  ✅ 包含Semantic Scholar适用语法")
            else:
                print("  ℹ️  通用检索策略")

        except Exception as e:
            print(f"\n{db.upper()}: ❌ 策略生成失败 - {e}")

    # 专门测试PubMed检索式格式
    print(f"\n专门测试PubMed检索式格式:")
    try:
        pubmed_strategy = router.convert_to_search_strategy("冠心病介入治疗", 'pubmed', '医学')
        print(f"PubMed策略: {pubmed_strategy}")

        # 检查是否符合app.py中定义的格式要求
        if '[Title/Abstract]' in pubmed_strategy and '"' in pubmed_strategy:
            print("✅ 符合app.py中的PubMed检索式格式要求")
        else:
            print("❌ 不符合app.py中的PubMed检索式格式要求")

    except Exception as e:
        print(f"❌ PubMed专门测试失败: {e}")

def main():
    """主测试函数"""
    try:
        # 测试单数据库选择
        accuracy = test_single_database_selection()
        
        # 测试检索策略生成
        test_database_specific_strategies()
        
        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)
        
        return accuracy >= 70  # 70%以上准确率认为测试通过
        
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
