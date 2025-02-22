import requests
from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# 搜索专家提示词模板
SEARCH_EXPERT_PROMPT = """作为学术文献检索专家，请为以下研究内容生成检索策略：

研究内容：{query}

要求：
1. 提取2-3个最核心的英文关键词或短语
2. 关键词应该简洁精确
3. 优先使用领域内通用的专业术语
4. 关键词之间用空格分隔
5. 不要使用AND、OR等布尔运算符

请按以下格式提供：

1. 核心关键词：
- [列出2-3个最重要的英文关键词，每个关键词一行]
- [列出2-3个最重要的中文关键词，每个关键词一行]
2. 检索策略：
[将关键词组合成一个搜索短语]"""

class DeepSeekClient:
    """
    DeepSeek API客户端类
    """
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化DeepSeek客户端
        从环境变量加载API密钥
        """
        base_url = os.getenv('BASE_URL')
        load_dotenv()
        self.api_key = api_key or os.getenv('DEEPSEEK_API_KEY')
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url
        )

    def generate_search_strategy(self, query: str) -> str:
        """
        生成检索策略
        
        Args:
            query: 搜索查询文本
            
        Returns:
            str: 生成的检索策略
        """
        try:
            # 使用搜索专家提示词模板
            prompt = SEARCH_EXPERT_PROMPT.format(query=query)
            model = os.getenv('MODEL')
            # 发送请求
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            # 提取生成的文本
            return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"生成检索策略时出错: {str(e)}")
            raise

    def analyze_text(self, prompt: str) -> str:
        """
        调用DeepSeek API分析文本
        
        Args:
            prompt: 输入提示文本
            
        Returns:
            str: 生成的文本内容
        """
        try:
            # 发送请求
            response = self.client.chat.completions.create(
                model="Pro/deepseek-ai/DeepSeek-R1",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=16000
            )
            
            # 提取生成的文本
            return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"调用DeepSeek API时出错: {str(e)}")
            raise 