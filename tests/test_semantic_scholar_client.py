import pytest
from utils.semantic_scholar_client import SemanticScholarClient
import logging
import time
from unittest.mock import patch, Mock
import requests

logger = logging.getLogger(__name__)

@pytest.fixture
def client():
    return SemanticScholarClient()

def test_search_papers_basic(client):
    """测试基本搜索功能"""
    with patch('requests.Session.request') as mock_request:
        # 模拟成功响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [{
                'paperId': '123',
                'title': 'Test Paper',
                'year': 2023,
                'citationCount': 10,
                'authors': [{'authorId': '1', 'name': 'Test Author'}]
            }]
        }
        mock_request.return_value = mock_response
        
        papers = client.search_papers(
            query="machine learning",
            limit=5,
            fields=["paperId", "title", "year", "citationCount", "authors"]
        )
        
        assert isinstance(papers, list)
        if papers:
            paper = papers[0]
            required_fields = {
                'paperId': str,
                'title': str,
                'year': (int, type(None)),
                'citationCount': (int, type(None)),
                'authors': list
            }
            
            for field, expected_type in required_fields.items():
                assert field in paper, f"Missing field: {field}"
                if not isinstance(expected_type, tuple):
                    assert isinstance(paper[field], expected_type)
                else:
                    assert isinstance(paper[field], expected_type)

def test_search_papers_with_filters(client):
    """测试带过滤条件的搜索"""
    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [{
                'paperId': '123',
                'title': 'Test Paper',
                'year': 2023,
                'citationCount': 150,
                'fieldsOfStudy': ['Computer Science'],
                'authors': []
            }]
        }
        mock_request.return_value = mock_response
        
        papers = client.search_papers(
            query="deep learning",
            year_range=(2020, 2024),
            min_citation_count=100,
            fields_of_study=["Computer Science"],
            limit=5
        )
        
        if papers:
            for paper in papers:
                assert paper['year'] >= 2020
                assert paper['year'] <= 2024
                assert paper['citationCount'] >= 100
                assert "Computer Science" in paper.get('fieldsOfStudy', [])

def test_get_paper_details(client):
    """测试获取论文详情"""
    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'paperId': '123',
            'title': 'Test Paper',
            'abstract': 'Test abstract',
            'year': 2023,
            'authors': []
        }
        mock_request.return_value = mock_response
        
        paper = client.get_paper_details('123')
        
        assert paper['paperId'] == '123'
        assert 'title' in paper
        assert 'abstract' in paper
        assert 'year' in paper
        assert 'authors' in paper

@patch('utils.semantic_scholar_client.time.sleep')  # 修改mock路径
def test_rate_limiting(mock_sleep, client):
    """测试速率限制"""
    with patch('requests.Session.request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}
        mock_request.return_value = mock_response
        
        # 重置last_request_time以确保触发限制
        client.last_request_time = 0
        
        for i in range(3):
            client.search_papers("test", limit=1)
            # 验证是否调用了sleep
            assert mock_sleep.called
            # 验证sleep时间是否合理
            sleep_time = mock_sleep.call_args[0][0]
            assert sleep_time >= 0.1  # 最小等待时间
            assert sleep_time <= client.request_interval
            # 重置mock以检查下一次调用
            mock_sleep.reset_mock()

def test_retry_on_429(client):
    """测试429错误重试"""
    with patch('requests.Session.request') as mock_request:
        # 创建模拟响应
        error_response = Mock()
        error_response.status_code = 429
        error_response.headers = {'Retry-After': '1'}
        error_response.raise_for_status.side_effect = requests.exceptions.HTTPError("429 Client Error")
        
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {'data': [{'paperId': '123', 'title': 'Test'}]}
        
        # 设置mock按顺序返回不同的响应
        mock_request.side_effect = [error_response, success_response]
        
        result = client.search_papers("test", limit=1)
        assert len(result) > 0
        assert mock_request.call_count == 2  # 确认重试了一次

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pytest.main([__file__, '-v']) 