"""
论文分析器模块
提供论文内容分析和总结功能

@author: Renegade12138
@date: 2025
"""

import logging
from datetime import datetime
from utils.deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)

class PaperAnalyzer:
    """论文分析器类"""
    
    def __init__(self):
        """初始化分析器"""
        self.llm_client = DeepSeekClient()
        
    def prompt_construct(self, content):
        """
        根据论文内容构造分析提示
        
        Args:
            content: 论文内容文本
            
        Returns:
            str: 构造的提示文本
        """
        prompt = f"""
        # Role
        你是一名论文研究助手，专注于论文阅读、总结并提出改进建议

        # Goal
        - 你的目标是全面阅读和理解论文，总结论文的结构和内容，列出技术要点和论文中提到的方法的具体实现过程，以及最终的实现效果，并对该论文点评和提出改进方案。
        - 你的输出格式为markdown格式，并包含以下内容：  
          - 论文的结构和内容总结  
          - 技术要点和论文中提到的方法的具体实现过程，如果有公式，使用latex，如果需要图表示意，使用mermaid  
          - 最终的实现效果  
          - 对论文的点评和改进方案  
        - 提出改进建议时，要深度考虑改进可行性，并给出理论依据，提出完整可行的改进方案。如果有必要，使用公式和流程图辅助说明。  
        - 输出结果以raw markdown 呈现  

        # 论文内容:  
        {content}
        """
        return prompt
        
    def process_llm_response(self, response):
        """
        处理LLM返回的内容，确保正确的markdown格式
        
        Args:
            response: LLM返回的原始响应
            
        Returns:
            str: 处理后的markdown内容
        """
        try:
            # 如果响应被包裹在markdown代码块中，移除它
            if response.startswith('```markdown\n'):
                response = response[len('```markdown\n'):]
            if response.endswith('\n```'):
                response = response[:-4]
                
            # 添加标题和时间戳
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            header = f"""# 论文阅读总结

> 生成时间：{current_time}

"""
            response = header + response.strip()
            
            return response
            
        except Exception as e:
            logger.error(f"处理LLM响应时出错: {str(e)}")
            return response  # 如果处理出错，返回原始响应
            
    def analyze_paper(self, content):
        """
        分析论文内容
        
        Args:
            content: 论文内容文本
            
        Returns:
            str: 分析结果（markdown格式）
        """
        try:
            # 构建prompt
            prompt = self.prompt_construct(content)
            
            # 调用LLM分析
            response = self.llm_client.analyze_text(prompt)
            
            if not response:
                raise Exception("LLM分析失败")
                
            # 处理响应
            result = self.process_llm_response(response)
            
            return result
            
        except Exception as e:
            logger.error(f"论文分析失败: {str(e)}")
            raise 