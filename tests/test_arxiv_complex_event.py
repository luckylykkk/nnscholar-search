"""
测试 arXiv 复杂事件处理相关搜索
"""
import pytest
import asyncio
from utils.arxiv_client import ArxivClient
import logging
from urllib.parse import unquote

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture
def arxiv_client():
    """创建 ArxivClient 实例"""
    return ArxivClient()

@pytest.mark.asyncio
async def test_search_complex_event_processing(arxiv_client):
    """测试复杂事件处理相关搜索"""
    # 测试用例1：使用引号包围的精确短语，不限年份
    query = '"event processing"'
    filters = {
        "papers_limit": 10
    }
    
    papers = await arxiv_client.search_papers(query, filters)
    logger.info(f"精确短语搜索结果数量: {len(papers)}")
    
    # 记录实际发送的查询
    logger.info(f"实际查询URL解码后: {unquote(arxiv_client._build_search_query(query, filters))}")
    
    # 测试用例2：使用 OR 连接的关键词
    query = "event OR processing"
    papers = await arxiv_client.search_papers(query, filters)
    logger.info(f"OR连接搜索结果数量: {len(papers)}")
    logger.info(f"实际查询URL解码后: {unquote(arxiv_client._build_search_query(query, filters))}")
    
    # 测试用例3：使用类别限定
    query = 'cat:cs.* AND event'  # 所有计算机科学类别
    papers = await arxiv_client.search_papers(query, filters)
    logger.info(f"类别限定搜索结果数量: {len(papers)}")
    logger.info(f"实际查询URL解码后: {unquote(arxiv_client._build_search_query(query, filters))}")
    
    # 测试用例4：使用标题限定
    query = 'ti:event'
    papers = await arxiv_client.search_papers(query, filters)
    logger.info(f"标题限定搜索结果数量: {len(papers)}")
    logger.info(f"实际查询URL解码后: {unquote(arxiv_client._build_search_query(query, filters))}")
    
    # 至少有一个查询应该返回结果
    assert any(len(p) > 0 for p in [papers]), "所有查询都没有返回结果"
    
    # 如果有结果，验证返回的论文
    if papers:
        paper = papers[0]
        logger.info(f"示例论文标题: {paper['title']}")
        logger.info(f"示例论文分类: {paper.get('primary_category', 'N/A')}")
        logger.info(f"示例论文作者: {[a['name'] for a in paper['authors']]}")
        logger.info(f"示例论文年份: {paper.get('year', 'N/A')}")

@pytest.mark.asyncio
async def test_search_with_different_date_ranges(arxiv_client):
    """测试不同日期范围的搜索"""
    query = 'event'
    
    # 测试最近5年
    filters = {
        "papers_limit": 5,
        "year_range": [2019, 2024]
    }
    papers_recent = await arxiv_client.search_papers(query, filters)
    logger.info(f"最近5年的结果数量: {len(papers_recent)}")
    
    # 测试2010-2015年
    filters = {
        "papers_limit": 5,
        "year_range": [2010, 2015]
    }
    papers_old = await arxiv_client.search_papers(query, filters)
    logger.info(f"2010-2015年的结果数量: {len(papers_old)}")
    
    # 记录一些结果详情
    if papers_recent:
        paper = papers_recent[0]
        logger.info(f"最新论文标题: {paper['title']}")
        logger.info(f"发表年份: {paper.get('year')}")
        logger.info(f"作者: {[a['name'] for a in paper['authors']]}")
        logger.info(f"分类: {paper.get('primary_category', 'N/A')}")

@pytest.mark.asyncio
async def test_search_with_category_combinations(arxiv_client):
    """测试不同类别组合的搜索"""
    base_filters = {
        "papers_limit": 5
    }
    
    # 测试不同的类别组合
    categories = [
        'cs.*',  # 所有计算机科学类别
        'physics.*',  # 所有物理学类别
        'math.*',  # 所有数学类别
    ]
    
    for category in categories:
        query = f'cat:{category} AND event'
        papers = await arxiv_client.search_papers(query, base_filters)
        logger.info(f"类别 {category} 的结果数量: {len(papers)}")
        
        if papers:
            logger.info(f"示例论文标题: {papers[0]['title']}")

@pytest.mark.asyncio
async def test_search_error_cases(arxiv_client):
    """测试错误情况处理"""
    filters = {"papers_limit": 5}
    
    # 测试无效的查询语法
    query = "cat:invalid AND title:test"
    papers = await arxiv_client.search_papers(query, filters)
    assert isinstance(papers, list), "应该返回空列表而不是抛出异常"
    
    # 测试特殊字符
    query = "event processing & analysis"
    papers = await arxiv_client.search_papers(query, filters)
    assert isinstance(papers, list), "应该正确处理特殊字符"
    
    # 测试超长查询
    query = "event " * 50
    papers = await arxiv_client.search_papers(query, filters)
    assert isinstance(papers, list), "应该正确处理超长查询" 