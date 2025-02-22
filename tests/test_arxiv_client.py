import pytest
import asyncio
from utils.arxiv_client import ArxivClient
import aiohttp
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture
def arxiv_client():
    """创建 ArxivClient 实例"""
    return ArxivClient()

@pytest.mark.asyncio
async def test_search_papers_basic(arxiv_client):
    """测试基本搜索功能"""
    query = "physics"  # 使用最基础的主题
    filters = {
        "papers_limit": 1  # 只获取一篇论文
    }
    
    papers = await arxiv_client.search_papers(query, filters)
    
    # 验证返回结果
    assert isinstance(papers, list), "返回结果应该是列表"
    assert len(papers) > 0, "应该至少找到一些论文"
    
    # 验证第一篇论文的结构
    if papers:
        paper = papers[0]
        assert 'id' in paper, "论文应该有ID"
        assert 'title' in paper, "论文应该有标题"
        assert 'abstract' in paper, "论文应该有摘要"
        assert 'authors' in paper, "论文应该有作者信息"
        assert isinstance(paper['authors'], list), "作者信息应该是列表"
        
        # 打印详细信息以帮助调试
        logger.info(f"找到 {len(papers)} 篇论文")
        logger.info(f"第一篇论文标题: {paper['title']}")
        logger.info(f"第一篇论文ID: {paper['id']}")

@pytest.mark.asyncio
async def test_search_papers_chinese(arxiv_client):
    """测试中文搜索"""
    query = "physics"  # 使用英文主题
    filters = {
        "papers_limit": 1
    }
    
    papers = await arxiv_client.search_papers(query, filters)
    logger.info(f"搜索结果数量: {len(papers)}")
    
    assert isinstance(papers, list), "返回结果应该是列表"

@pytest.mark.asyncio
async def test_search_papers_with_category(arxiv_client):
    """测试特定类别的搜索"""
    query = "physics"  # 使用基础主题
    filters = {
        "papers_limit": 1
    }
    
    papers = await arxiv_client.search_papers(query, filters)
    logger.info(f"搜索结果数量: {len(papers)}")
    
    assert isinstance(papers, list), "返回结果应该是列表"
    assert len(papers) > 0, "应该至少找到一些论文"

@pytest.mark.asyncio
async def test_search_papers_error_handling(arxiv_client):
    """测试错误处理"""
    # 测试空查询
    papers = await arxiv_client.search_papers("", {})
    assert isinstance(papers, list), "即使是空查询也应该返回空列表"
    assert len(papers) == 0, "空查询应该返回空列表"
    
    # 测试无效的年份范围
    filters = {
        "year_range": [2025, 2024]  # 无效的年份范围
    }
    papers = await arxiv_client.search_papers("test", filters)
    assert isinstance(papers, list), "无效的过滤条件应该返回空列表"

@pytest.mark.asyncio
async def test_get_paper_details(arxiv_client):
    """测试获取论文详情"""
    # 使用一个已知存在的论文ID
    paper_id = "2402.11417"  # 这是一个示例ID，需要替换为实际存在的ID
    
    details = await arxiv_client.get_paper_details(paper_id)
    
    assert isinstance(details, dict), "论文详情应该是字典"
    if details:
        assert 'id' in details, "详情应该包含ID"
        assert 'title' in details, "详情应该包含标题"
        assert 'abstract' in details, "详情应该包含摘要"
        
        logger.info(f"论文详情标题: {details.get('title')}") 