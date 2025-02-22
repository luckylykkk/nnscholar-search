import os
import sys
import unittest
from dotenv import load_dotenv
import logging
import json
from pprint import pformat

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.semantic_scholar_client import SemanticScholarClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestSemanticScholarAPIFormat(unittest.TestCase):
    """测试 Semantic Scholar API 返回格式"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        load_dotenv()
        cls.client = SemanticScholarClient(use_api_key=False)
    
    def setUp(self):
        """每个测试用例前的设置"""
        time.sleep(1)  # 请求限制

    def test_venue_format(self):
        """测试 venue 字段的返回格式"""
        # 使用一个简单的查询获取一些论文
        result = self.client.search_papers(
            query="machine learning",
            fields=['paperId', 'title', 'venue'],
            limit=5
        )
        
        logger.info("API 返回的原始数据结构:")
        logger.info(pformat(result))
        
        if 'data' in result and result['data']:
            papers = result['data']
            logger.info("\n=== Venue 字段分析 ===")
            for i, paper in enumerate(papers, 1):
                logger.info(f"\n论文 {i}:")
                logger.info(f"标题: {paper.get('title', 'N/A')}")
                venue = paper.get('venue')
                logger.info(f"Venue 类型: {type(venue)}")
                logger.info(f"Venue 值: {venue}")
                if isinstance(venue, dict):
                    logger.info("Venue 字典的键:")
                    logger.info(pformat(venue.keys()))
        else:
            logger.warning("未找到任何论文数据")

    def test_full_paper_format(self):
        """测试完整的论文数据格式"""
        # 获取一篇论文的所有字段
        result = self.client.search_papers(
            query="deep learning",
            fields=[
                'paperId',
                'title',
                'abstract',
                'year',
                'citationCount',
                'influentialCitationCount',
                'isOpenAccess',
                'authors',
                'url',
                'venue',
                'publicationTypes',
                'publicationDate',
                'externalIds',
                'fieldsOfStudy'
            ],
            limit=1
        )
        
        logger.info("\n=== 完整论文数据结构 ===")
        logger.info(pformat(result))
        
        if 'data' in result and result['data']:
            paper = result['data'][0]
            logger.info("\n字段类型分析:")
            for field, value in paper.items():
                logger.info(f"{field}:")
                logger.info(f"  类型: {type(value)}")
                logger.info(f"  值: {value}")
                if isinstance(value, (dict, list)):
                    logger.info(f"  详细结构: {pformat(value)}")

    def test_error_response_format(self):
        """测试错误响应的格式"""
        # 使用无效的字段名触发错误
        result = self.client.search_papers(
            query="test",
            fields=['invalid_field'],
            limit=1
        )
        
        logger.info("\n=== 错误响应格式 ===")
        logger.info(pformat(result))

if __name__ == '__main__':
    unittest.main(verbosity=2) 