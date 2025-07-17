"""DeepSeek AI service for intelligent analysis."""

import requests
import json
from typing import List, Dict, Any, Optional, Union
import logging
import time
from datetime import datetime

from config.api_config import api_config
from utils.cache_utils import cache_result, RateLimiter
from utils.text_processing import preprocess_text

logger = logging.getLogger(__name__)


class DeepSeekService:
    """Service for interacting with DeepSeek AI API."""
    
    def __init__(self):
        self.api_url = api_config.DEEPSEEK_API_URL
        self.api_key = api_config.DEEPSEEK_API_KEY
        self.model = api_config.DEEPSEEK_MODEL
        self.rate_limiter = RateLimiter(
            max_requests=api_config.DEEPSEEK_RPM,
            window_seconds=60
        )
        
        if not self.api_key:
            logger.warning("DeepSeek API key not configured")
    
    def _make_request(self, messages: List[Dict[str, str]], 
                     temperature: float = None, 
                     max_tokens: int = None) -> Dict[str, Any]:
        """Make request to DeepSeek API.
        
        Args:
            messages: List of message objects
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        
        Returns:
            API response
        """
        if not self.api_key:
            raise Exception("DeepSeek API key not configured")
        
        # Rate limiting
        if not self.rate_limiter.is_allowed('deepseek'):
            logger.warning("Rate limit exceeded for DeepSeek API")
            raise Exception("Rate limit exceeded")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature or api_config.DEEPSEEK_TEMPERATURE,
            'max_tokens': max_tokens or api_config.DEEPSEEK_MAX_TOKENS
        }
        
        # 重试机制
        max_retries = 3
        retry_delay = 1  # 秒

        for attempt in range(max_retries):
            try:
                logger.debug(f"Making DeepSeek API request (attempt {attempt + 1}/{max_retries}): {len(messages)} messages")

                # 创建会话以复用连接
                session = requests.Session()
                session.headers.update(headers)

                response = session.post(
                    self.api_url,
                    json=payload,
                    timeout=api_config.DEEPSEEK_TIMEOUT,
                    verify=True  # 确保SSL验证
                )

                response.raise_for_status()

                result = response.json()

                # Log usage
                if 'usage' in result:
                    usage = result['usage']
                    logger.debug(f"DeepSeek API usage: {usage}")

                session.close()
                return result

            except requests.exceptions.SSLError as e:
                logger.warning(f"SSL error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))  # 递增延迟
                    continue
                else:
                    logger.error(f"SSL error after {max_retries} attempts: {e}")
                    raise Exception(f"DeepSeek API SSL error: {str(e)}")

            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Connection error after {max_retries} attempts: {e}")
                    raise Exception(f"DeepSeek API connection error: {str(e)}")

            except requests.exceptions.Timeout as e:
                logger.warning(f"Timeout error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Timeout error after {max_retries} attempts: {e}")
                    raise Exception(f"DeepSeek API timeout error: {str(e)}")

            except requests.RequestException as e:
                logger.warning(f"Request error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Request error after {max_retries} attempts: {e}")
                    raise Exception(f"DeepSeek API error: {str(e)}")

            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Unexpected error after {max_retries} attempts: {e}")
                    raise Exception(f"DeepSeek API unexpected error: {str(e)}")

            finally:
                # 确保会话被关闭
                try:
                    session.close()
                except:
                    pass
    
    def _extract_response_content(self, response: Dict[str, Any]) -> str:
        """Extract content from API response.
        
        Args:
            response: API response
        
        Returns:
            Response content
        """
        try:
            # 详细记录响应结构用于调试
            logger.info(f"DeepSeek API响应结构: {json.dumps(response, ensure_ascii=False, indent=2)[:1000]}...")
            
            if 'choices' in response and len(response['choices']) > 0:
                choice = response['choices'][0]
                logger.info(f"处理choice: {json.dumps(choice, ensure_ascii=False, indent=2)[:500]}...")
                
                if 'message' in choice and 'content' in choice['message']:
                    content = choice['message']['content'].strip()
                    logger.info(f"提取到内容长度: {len(content)} 字符")
                    logger.info(f"内容预览: {content[:200]}...")
                    
                    if content:
                        return content
                    else:
                        logger.warning("API返回的内容为空")
                        return ""
                else:
                    logger.warning(f"Choice中缺少message.content字段: {choice}")
            else:
                logger.warning(f"响应中缺少choices字段或choices为空: {response}")
            
            logger.warning("无法从DeepSeek API响应中提取有效内容")
            return ""
            
        except Exception as e:
            logger.error(f"提取响应内容时出错: {e}")
            logger.error(f"响应数据: {response}")
            return ""
    
    @cache_result(ttl=1800)  # Cache for 30 minutes
    def generate_search_strategy(self, topic: str, search_mode: str = 'comprehensive') -> str:
        """Generate optimized search strategy for given topic.
        
        Args:
            topic: Research topic
            search_mode: 'comprehensive', 'focused', or 'broad'
        
        Returns:
            Optimized search query
        """
        try:
            system_prompt = """你是一位专业的学术文献检索专家。请根据用户提供的研究主题，生成简洁有效的PubMed检索策略。

要求：
1. 使用3-8个最核心的关键词或MeSH词汇
2. 合理使用布尔逻辑操作符（AND, OR）
3. 考虑最重要的同义词（不超过5个）
4. 使用合适的字段限定符如[MeSH]、[Title/Abstract]
5. 保持策略简洁，避免过度复杂
6. 总长度不超过500字符

请直接返回一行检索策略，不需要额外解释。"""
            
            user_prompt = f"研究主题：{topic}\n检索模式：{search_mode}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self._make_request(messages, temperature=0.3)
            strategy = self._extract_response_content(response)
            
            if not strategy:
                logger.warning("Empty strategy from DeepSeek, using fallback")
                return f'("{topic}"[Title/Abstract])'
            
            # 检查URL长度限制，避免414 Request-URI Too Long错误
            max_strategy_length = 2000  # 为其他URL参数预留空间
            if len(strategy) > max_strategy_length:
                logger.warning(f"Generated strategy too long ({len(strategy)} chars), using fallback")
                # 尝试提取策略的主要部分
                main_terms = strategy.split(' OR ')[:10]  # 只取前10个术语
                if main_terms:
                    strategy = ' OR '.join(main_terms)
                    # 如果仍然太长，使用简单策略
                    if len(strategy) > max_strategy_length:
                        strategy = f'("{topic}"[Title/Abstract])'
                else:
                    strategy = f'("{topic}"[Title/Abstract])'
            
            logger.info(f"Generated search strategy for '{topic}': {strategy[:100]}...")
            
            return strategy
            
        except Exception as e:
            logger.error(f"Error generating search strategy: {e}")
            # Fallback to simple strategy
            return f'("{topic}"[Title/Abstract])'
    
    @cache_result(ttl=3600)  # Cache for 1 hour
    def analyze_research_status(self, papers: List[Dict[str, Any]], topic: str) -> Dict[str, Any]:
        """Analyze research status based on papers.
        
        Args:
            papers: List of paper information
            topic: Research topic
        
        Returns:
            Analysis results
        """
        try:
            if not papers:
                return {"error": "No papers provided for analysis"}
            
            # Prepare paper summaries
            paper_summaries = []
            for i, paper in enumerate(papers[:20]):  # Limit to first 20 papers
                title = paper.get('title', '')
                abstract = paper.get('abstract', '')
                year = paper.get('pub_date', '')
                journal = paper.get('journal', '')
                
                summary = f"{i+1}. {title} ({year}) - {journal}"
                if abstract:
                    summary += f"\n摘要：{abstract[:200]}..."
                
                paper_summaries.append(summary)
            
            system_prompt = """你是一位资深的学术研究分析专家。请基于提供的文献信息，对指定研究领域进行全面的现状分析。
            
请从以下几个方面进行分析：
1. 研究热点和发展趋势
2. 主要研究方法和技术路线
3. 重要发现和突破
4. 存在的问题和挑战
5. 未来发展方向

请以结构化的方式组织分析结果。"""
            
            user_prompt = f"""研究主题：{topic}
            
相关文献摘要：
{chr(10).join(paper_summaries)}
            
请对该研究领域进行深入分析。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self._make_request(messages, temperature=0.7)
            analysis = self._extract_response_content(response)
            
            return {
                "topic": topic,
                "analysis": analysis,
                "paper_count": len(papers),
                "analyzed_papers": len(paper_summaries),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing research status: {e}")
            return {"error": f"Analysis failed: {str(e)}"}
    
    def suggest_review_topics(self, papers: List[Dict[str, Any]], topic: str) -> Dict[str, Any]:
        """Suggest review paper topics based on literature.
        
        Args:
            papers: List of paper information
            topic: Research topic
        
        Returns:
            Topic suggestions
        """
        try:
            if not papers:
                return {"error": "No papers provided for analysis"}
            
            # Extract key information from papers
            titles = [p.get('title', '') for p in papers[:30]]
            abstracts = [p.get('abstract', '')[:200] for p in papers[:15]]  # Limit abstract length
            
            system_prompt = """你是一位经验丰富的学术编辑和综述写作专家。请基于提供的文献信息，为综述论文提供有价值的选题建议。
            
请提供：
1. 3-5个具体的综述选题建议
2. 每个选题的研究价值和意义
3. 选题的可行性分析
4. 建议的综述结构框架

选题应该具有学术价值、创新性和可操作性。"""
            
            content = f"""研究领域：{topic}
            
相关文献标题：
{chr(10).join(titles[:20])}
            
部分摘要：
{chr(10).join(abstracts[:10])}
            
请提供综述选题建议。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            response = self._make_request(messages, temperature=0.8)
            suggestions = self._extract_response_content(response)
            
            return {
                "topic": topic,
                "suggestions": suggestions,
                "based_on_papers": len(papers),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error suggesting review topics: {e}")
            return {"error": f"Topic suggestion failed: {str(e)}"}
    
    def suggest_research_topics(self, papers: List[Dict[str, Any]], topic: str) -> Dict[str, Any]:
        """Suggest original research topics based on literature gaps.
        
        Args:
            papers: List of paper information
            topic: Research topic
        
        Returns:
            Research topic suggestions
        """
        try:
            if not papers:
                return {"error": "No papers provided for analysis"}
            
            # Prepare literature summary
            recent_papers = [p for p in papers if p.get('pub_date', '').startswith(('2022', '2023', '2024'))][:15]
            
            paper_info = []
            for paper in recent_papers:
                title = paper.get('title', '')
                abstract = paper.get('abstract', '')[:150]
                methods = paper.get('keywords', [])
                
                info = f"标题：{title}"
                if abstract:
                    info += f"\n摘要片段：{abstract}"
                if methods:
                    info += f"\n关键词：{', '.join(methods[:5])}"
                
                paper_info.append(info)
            
            system_prompt = """你是一位资深的科研指导专家，擅长识别研究空白和机会。请基于当前文献，识别研究空白并提出原创性研究选题建议。
            
请提供：
1. 3-5个具有创新性的研究选题
2. 每个选题的创新点和研究价值
3. 可能的研究方法和技术路线
4. 预期的研究难点和解决方案
5. 研究的可行性评估

选题应该填补现有研究空白，具有重要的学术价值和实践意义。"""
            
            content = f"""研究领域：{topic}
            
近期相关研究：
{'---'.join(paper_info)}
            
请基于以上文献分析，提出原创性研究选题建议。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            response = self._make_request(messages, temperature=0.8)
            suggestions = self._extract_response_content(response)
            
            return {
                "topic": topic,
                "research_suggestions": suggestions,
                "based_on_recent_papers": len(recent_papers),
                "total_papers_analyzed": len(papers),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error suggesting research topics: {e}")
            return {"error": f"Research topic suggestion failed: {str(e)}"}
    
    def generate_full_review(self, papers: List[Dict[str, Any]], topic: str, 
                           review_type: str = 'narrative') -> Dict[str, Any]:
        """Generate a comprehensive literature review.
        
        Args:
            papers: List of paper information
            topic: Review topic
            review_type: 'narrative', 'systematic', or 'meta-analysis'
        
        Returns:
            Generated review
        """
        try:
            if not papers:
                return {"error": "No papers provided for review generation"}
            
            # Organize papers by themes/categories
            paper_summaries = []
            for i, paper in enumerate(papers[:25]):  # Limit to 25 papers for comprehensive analysis
                title = paper.get('title', '')
                authors = paper.get('authors', [])
                journal = paper.get('journal', '')
                year = paper.get('pub_date', '')[:4]  # Extract year
                abstract = paper.get('abstract', '')
                
                author_str = ', '.join(authors[:3]) + (' et al.' if len(authors) > 3 else '')
                
                summary = f"{i+1}. {title}\n作者：{author_str}\n期刊：{journal} ({year})"
                if abstract:
                    summary += f"\n摘要：{abstract[:300]}..."
                
                paper_summaries.append(summary)
            
            system_prompt = f"""你是一位顶级期刊的学术编辑，擅长撰写高质量的文献综述。请基于提供的文献信息，撰写一篇完整的{review_type}综述。
            
综述要求：
1. 结构清晰，逻辑严密
2. 全面覆盖主要研究方向
3. 客观分析研究现状和趋势
4. 识别研究空白和未来方向
5. 学术写作规范，语言准确

请按以下结构组织：
1. 引言（研究背景和意义）
2. 研究现状（分类讨论主要发现）
3. 研究方法和技术进展
4. 存在问题和挑战
5. 未来发展趋势
6. 结论

字数控制在3000-5000字。"""
            
            content = f"""综述主题：{topic}
            
相关文献：
{chr(10).join(['---'] + paper_summaries)}
            
请撰写完整的文献综述。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            response = self._make_request(messages, temperature=0.7, max_tokens=6000)
            review_content = self._extract_response_content(response)
            
            return {
                "topic": topic,
                "review_type": review_type,
                "content": review_content,
                "papers_included": len(paper_summaries),
                "total_papers": len(papers),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating full review: {e}")
            return {"error": f"Review generation failed: {str(e)}"}
    
    def recommend_representative_papers(self, papers: List[Dict[str, Any]], 
                                      criteria: str = 'impact_and_novelty') -> Dict[str, Any]:
        """Recommend representative papers based on criteria.
        
        Args:
            papers: List of paper information
            criteria: Selection criteria
        
        Returns:
            Recommended papers with reasoning
        """
        try:
            if not papers:
                return {"error": "No papers provided for recommendation"}
            
            # Prepare paper information
            paper_list = []
            for i, paper in enumerate(papers[:50]):  # Analyze up to 50 papers
                title = paper.get('title', '')
                authors = paper.get('authors', [])
                journal = paper.get('journal', '')
                year = paper.get('pub_date', '')[:4]
                abstract = paper.get('abstract', '')[:200]
                impact_factor = paper.get('impact_factor', 'N/A')
                
                paper_info = f"{i+1}. {title}\n期刊：{journal} (IF: {impact_factor})\n年份：{year}\n摘要：{abstract}"
                paper_list.append(paper_info)
            
            system_prompt = f"""你是一位资深的学术专家，擅长评估文献的学术价值和影响力。请基于{criteria}标准，从提供的文献中推荐5-10篇最具代表性的论文。
            
评估标准：
1. 学术影响力（期刊影响因子、引用潜力）
2. 创新性和原创性
3. 研究方法的科学性
4. 研究结果的重要性
5. 对领域发展的贡献

请为每篇推荐论文提供详细的推荐理由，说明其代表性和重要性。"""
            
            content = f"""文献列表：
{chr(10).join(['---'] + paper_list)}
            
请推荐最具代表性的论文并说明理由。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            response = self._make_request(messages, temperature=0.6)
            recommendations = self._extract_response_content(response)
            
            return {
                "criteria": criteria,
                "recommendations": recommendations,
                "total_papers_analyzed": len(papers),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error recommending papers: {e}")
            return {"error": f"Paper recommendation failed: {str(e)}"}
    
    def precise_literature_search(self, papers: List[Dict[str, Any]], 
                                 requirements: str) -> Dict[str, Any]:
        """Precisely filter papers based on specific requirements.
        
        Args:
            papers: List of paper information
            requirements: Specific filtering requirements
        
        Returns:
            Filtered papers with sufficiency scores
        """
        try:
            if not papers:
                return {"error": "No papers provided for filtering"}
            
            # Prepare paper information for analysis
            paper_data = []
            for i, paper in enumerate(papers):
                title = paper.get('title', '')
                abstract = paper.get('abstract', '')
                keywords = paper.get('keywords', [])
                
                paper_info = {
                    'index': i,
                    'title': title,
                    'abstract': abstract[:300],  # Limit abstract length
                    'keywords': ', '.join(keywords[:10]) if keywords else 'N/A'
                }
                paper_data.append(paper_info)
            
            # Process in batches to avoid token limits
            batch_size = 20
            all_results = []
            
            for i in range(0, len(paper_data), batch_size):
                batch = paper_data[i:i + batch_size]
                
                paper_text = []
                for p in batch:
                    text = f"论文{p['index']+1}：\n标题：{p['title']}\n摘要：{p['abstract']}\n关键词：{p['keywords']}"
                    paper_text.append(text)
                
                system_prompt = f"""你是一位严格的文献筛选专家。请根据用户的具体要求，对每篇论文进行严格评估。
                
评估要求：
1. 严格按照用户要求筛选
2. 为每篇符合要求的论文打分（50-100分）
3. 90-100分：高度符合要求
4. 70-89分：中度符合要求
5. 50-69分：基本符合要求
6. 低于50分：不符合要求（排除）

请以JSON格式返回结果：
{{
  "filtered_papers": [
    {{
      "paper_index": 论文序号,
      "score": 评分,
      "reason": "符合要求的具体理由"
    }}
  ]
}}
                
用户要求：{requirements}"""
                
                content = f"""请筛选以下论文：

{chr(10).join(['---'] + paper_text)}"""
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ]
                
                response = self._make_request(messages, temperature=0.3)
                result_text = self._extract_response_content(response)
                
                # Try to parse JSON response
                try:
                    import re
                    json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                    if json_match:
                        result_json = json.loads(json_match.group())
                        if 'filtered_papers' in result_json:
                            all_results.extend(result_json['filtered_papers'])
                except:
                    logger.warning(f"Failed to parse JSON response: {result_text[:200]}...")
            
            # Sort by score
            all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
            
            return {
                "requirements": requirements,
                "filtered_papers": all_results,
                "total_analyzed": len(papers),
                "filtered_count": len(all_results),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in precise literature search: {e}")
            return {"error": f"Precise search failed: {str(e)}"}
    
    def generate_search_suggestions(self, query: str, titles: List[str], 
                                   total_papers: int) -> str:
        """Generate further search suggestions based on current results.
        
        Args:
            query: Original search query
            titles: List of paper titles from current search
            total_papers: Total number of papers found
            
        Returns:
            Search suggestions as formatted text
        """
        try:
            system_prompt = """你是一位经验丰富的文献检索专家，擅长优化检索策略和提供检索建议。
            
请基于当前检索结果，分析检索覆盖范围，并提供进一步的精准检索建议，帮助用户发现更多相关和高质量的文献。

检索建议应包括：
1. 当前检索结果的分析评估
2. 更精准的关键词组合建议
3. 检索策略优化建议
4. 相关研究方向的扩展建议
5. 具体的检索式和筛选条件"""
            
            content = f"""原始检索查询：{query}
当前检索结果：{total_papers}篇文献

代表性文献标题（前20篇）：
{chr(10).join([f"{i+1}. {title}" for i, title in enumerate(titles[:20])])}

请提供详细的进一步检索建议。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            response = self._make_request(messages, temperature=0.7)
            return self._extract_response_content(response)
            
        except Exception as e:
            logger.error(f"Error generating search suggestions: {e}")
            return f"检索建议生成失败: {str(e)}"
    
    def analyze_research_frontiers(self, query: str, recent_papers: List[Dict[str, Any]]) -> str:
        """Analyze research frontiers and trends.
        
        Args:
            query: Research domain
            recent_papers: List of recent papers
            
        Returns:
            Research frontiers analysis as formatted text
        """
        try:
            # Prepare recent paper information
            paper_info = []
            for paper in recent_papers[:20]:  # Use top 20 recent papers
                title = paper.get('title', 'No title')
                year = paper.get('pub_date', '')[:4] if paper.get('pub_date') else 'Unknown'
                journal = paper.get('journal', 'Unknown journal')
                info = f"标题: {title}\n年份: {year}\n期刊: {journal}"
                paper_info.append(info)
            
            system_prompt = """你是一位学术前沿分析专家，擅长识别研究热点、新兴技术趋势和未来发展方向。
            
请基于最新的文献，分析该研究领域的前沿方向和发展趋势，包括：
1. 当前研究热点和趋势
2. 新兴技术和方法
3. 未来发展方向预测
4. 研究机会和挑战
5. 对研究者的建议

分析应具有前瞻性和指导性。"""
            
            content = f"""研究领域：{query}

最新文献（按发表时间排序）：
{chr(10).join(['---'] + paper_info)}

请分析该领域的前沿研究方向和发展趋势。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            response = self._make_request(messages, temperature=0.8)
            return self._extract_response_content(response)
            
        except Exception as e:
            logger.error(f"Error analyzing research frontiers: {e}")
            return f"前沿研究分析失败: {str(e)}"
    
    def identify_research_gaps(self, query: str, papers: List[Dict[str, Any]]) -> str:
        """Identify research gaps and opportunities.
        
        Args:
            query: Research domain
            papers: List of papers to analyze
            
        Returns:
            Research gaps analysis as formatted text
        """
        try:
            # Prepare paper information for analysis
            paper_info = []
            for paper in papers[:50]:  # Analyze top 50 papers
                title = paper.get('title', 'No title')
                abstract = paper.get('abstract', 'No abstract')
                year = paper.get('pub_date', '')[:4] if paper.get('pub_date') else 'Unknown'
                info = f"标题: {title}\n年份: {year}\n摘要: {abstract[:200]}..."
                paper_info.append(info)
            
            system_prompt = """你是一位研究空白识别专家，擅长从现有文献中发现研究不足和潜在机会。
            
请基于提供的文献，识别该研究领域的空白和机会，包括：
1. 现有研究的不足和局限性
2. 尚未充分探索的研究方向
3. 方法学上的改进空间
4. 跨学科研究机会
5. 实践应用中的待解决问题
6. 具体的研究建议和可行性分析

分析应具有创新性和可操作性。"""
            
            content = f"""研究领域：{query}

相关文献分析：
{chr(10).join(['---'] + paper_info[:10])}

请识别该领域的研究空白和机会。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ]
            
            response = self._make_request(messages, temperature=0.8)
            return self._extract_response_content(response)
            
        except Exception as e:
            logger.error(f"Error identifying research gaps: {e}")
            return f"研究空白识别失败: {str(e)}"

    def analyze_text(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """通用文本分析方法

        Args:
            prompt: 分析提示词
            temperature: 采样温度
            max_tokens: 最大token数

        Returns:
            分析结果文本
        """
        try:
            messages = [
                {"role": "system", "content": "你是一位专业的学术研究分析师，擅长深度分析和综合评估。"},
                {"role": "user", "content": prompt}
            ]

            response = self._make_request(messages, temperature=temperature, max_tokens=max_tokens)
            return self._extract_response_content(response)

        except Exception as e:
            logger.error(f"文本分析失败: {e}")
            raise e

    def get_service_status(self) -> Dict[str, Any]:
        """Get service status and statistics.
        
        Returns:
            Service status information
        """
        return {
            "service": "DeepSeek AI",
            "api_url": self.api_url,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "rate_limit_remaining": self.rate_limiter.get_remaining('deepseek'),
            "max_tokens": api_config.DEEPSEEK_MAX_TOKENS,
            "temperature": api_config.DEEPSEEK_TEMPERATURE
        }


# Global service instance
deepseek_service = DeepSeekService()