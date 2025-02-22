import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

import pytest
from dotenv import load_dotenv
from utils.deepseek_client import DeepSeekClient
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@pytest.fixture
def client():
    """创建DeepSeek客户端实例"""
    load_dotenv()
    return DeepSeekClient()

def test_api_connection(client):
    """测试API连接和基本响应"""
    try:
        # 1. 测试简单问题
        logger.info("测试1: 发送简单问题")
        response = client.analyze_text("你好，请做个简单的自我介绍。")
        assert isinstance(response, str)
        assert len(response) > 0
        logger.info(f"测试1响应: {response[:100]}...")

        # 2. 测试专业问题
        logger.info("测试2: 发送专业医学问题")
        medical_query = "请解释什么是冠状动脉造影？"
        response = client.analyze_text(medical_query)
        assert isinstance(response, str)
        assert len(response) > 0
        logger.info(f"测试2响应: {response[:100]}...")

        logger.info("所有测试通过！API连接正常且响应符合预期。")

    except Exception as e:
        logger.error(f"API测试失败: {str(e)}")
        raise

def test_error_handling(client):
    """测试错误处理"""
    try:
        # 测试空消息
        with pytest.raises(Exception):
            client.analyze_text("")
        logger.info("空消息测试通过")

        # 测试超长文本
        very_long_text = "测试" * 10000
        with pytest.raises(Exception):
            client.analyze_text(very_long_text)
        logger.info("超长文本测试通过")

        logger.info("错误处理测试通过！")

    except Exception as e:
        logger.error(f"错误处理测试失败: {str(e)}")
        raise

def test_api_error():
    """测试API错误情况"""
    class ErrorTestClient(DeepSeekClient):
        def __init__(self):
            super().__init__()
            # 使用一个无效的URL
            self.base_url = "https://invalid-url-that-will-fail.com/v1/chat/completions"

    client = ErrorTestClient()
    
    with pytest.raises(Exception) as exc_info:
        client.analyze_text("测试文本")
    
    assert "DeepSeek API调用失败" in str(exc_info.value)
    logger.info("API错误测试通过！")

if __name__ == "__main__":
    # 直接运行测试
    load_dotenv()
    client = DeepSeekClient()
    
    print("开始测试DeepSeek API连接...")
    
    try:
        test_api_connection(client)
        test_error_handling(client)
        test_api_error()  # 替换原来的test_api_timeout
        print("所有测试通过！API工作正常。")
    except Exception as e:
        print(f"测试失败: {str(e)}") 