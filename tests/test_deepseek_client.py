import pytest
from utils.deepseek_client import DeepSeekClient

import os
from dotenv import load_dotenv

@pytest.fixture
def client():
    """创建DeepSeek客户端实例"""
    load_dotenv()
    return DeepSeekClient()

def test_chat_completion(client):
    """测试聊天完成功能"""
    messages = [
        {
            "role": "user",
            "content": "你好，请简单介绍下你自己。"
        }
    ]
    
    response = client.chat_completion(messages)
    assert "choices" in response
    assert len(response["choices"]) > 0
    assert "message" in response["choices"][0]
    assert "content" in response["choices"][0]["message"]

def test_analyze_text(client):
    """测试文本分析功能"""
    text = "这是一段测试文本，用于测试文本分析功能。"
    result = client.analyze_text(text)
    assert isinstance(result, str)
    assert len(result) > 0 