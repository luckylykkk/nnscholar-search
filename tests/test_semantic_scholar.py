import os
import sys
import unittest
from dotenv import load_dotenv
import logging

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.semantic_scholar_client import SemanticScholarClient

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestSemanticScholarClient(unittest.TestCase):
    """测试 Semantic Scholar API 客户端"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        load_dotenv()
        cls.client = SemanticScholarClient()
        
    def test_basic_search(self):
        """测试基本搜索功能"""
        query = "machine learning"
        result = self.client.search_papers(query=query, limit=5)
        
        # 检查返回结果
        self.assertIn('data', result)
        papers = result['data']
        self.assertIsInstance(papers, list)
        if papers:  # 如果找到文章
            logger.info(f"成功检索到 {len(papers)} 篇文献")
            # 检查第一篇文章的结构
            paper = papers[0]
            self.assertIn('title', paper)
            self.assertIn('year', paper)
            logger.info(f"示例文章: {paper['title']}")
        else:
            logger.warning("未找到任何文章")

    def test_chinese_search(self):
        """测试中文搜索"""
        query = "机器学习"
        result = self.client.search_papers(query=query, limit=5)
        
        self.assertIn('data', result)
        papers = result['data']
        if papers:
            logger.info(f"中文搜索成功检索到 {len(papers)} 篇文献")
            logger.info(f"第一篇文章标题: {papers[0]['title']}")

    def test_complex_search(self):
        """测试复杂查询"""
        query = "Complex Event Processing AND Distributed Systems"
        result = self.client.search_papers(query=query, limit=5)
        
        self.assertIn('data', result)
        papers = result['data']
        if papers:
            logger.info(f"复杂查询成功检索到 {len(papers)} 篇文献")
            for paper in papers:
                logger.info(f"标题: {paper['title']}")
                logger.info(f"年份: {paper.get('year', 'N/A')}")
                logger.info(f"引用数: {paper.get('citation_count', 'N/A')}")
                logger.info("---")

    def test_field_selection(self):
        """测试字段选择"""
        fields = ['paperId', 'title', 'year', 'citationCount']
        result = self.client.search_papers(
            query="artificial intelligence",
            limit=3,
            fields=fields
        )
        
        self.assertIn('data', result)
        papers = result['data']
        if papers:
            paper = papers[0]
            logger.info("返回字段测试:")
            for field in ['title', 'year']:
                self.assertIn(field, paper)
                logger.info(f"{field}: {paper[field]}")

    def test_error_handling(self):
        """测试错误处理"""
        # 测试空查询
        result = self.client.search_papers(query="")
        self.assertIn('data', result)
        self.assertEqual(len(result['data']), 0)
        
        # 测试无效的字段名
        result = self.client.search_papers(
            query="test",
            fields=['invalid_field']
        )
        self.assertIn('data', result)

    def test_rate_limiting(self):
        """测试请求限制"""
        # 连续发送几个请求测试限速
        queries = ["python", "java", "javascript"]
        for query in queries:
            result = self.client.search_papers(query=query, limit=1)
            self.assertIn('data', result)
            logger.info(f"查询 '{query}' 成功")

if __name__ == '__main__':
    unittest.main(verbosity=2) 