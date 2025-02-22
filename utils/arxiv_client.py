"""
Arxiv API客户端
"""
import aiohttp
import logging
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from .paper_source_interface import PaperSourceInterface
import asyncio
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)

class ArxivClient(PaperSourceInterface):
    """
    Arxiv API客户端类
    """
    def __init__(self):
        """初始化客户端"""
        self.base_url = "http://export.arxiv.org/api/query"
        self.headers = {
            "Content-Type": "application/xml"
        }
        self.request_interval = 3  # 每次请求间隔3秒
        self.last_request_time = 0
        
    async def _wait_for_rate_limit(self):
        """实现请求速率限制"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.request_interval:
            sleep_time = self.request_interval - elapsed
            logger.debug(f"等待 {sleep_time:.2f} 秒以遵守速率限制")
            await asyncio.sleep(sleep_time)
        self.last_request_time = time.time()

    def _build_search_query(self, query: str, filters: Dict[str, Any]) -> str:
        """
        构建搜索查询字符串
        
        arXiv 查询语法：
        - 字段前缀：ti (标题), au (作者), abs (摘要), co (注释), jr (期刊), cat (类别), all (所有)
        - 精确短语：使用双引号，如 ti:"complex event processing"
        - 布尔运算：AND, OR, ANDNOT（必须大写）
        - 分组：使用括号，如 (ti:quantum AND au:smith)
        """
        # 预处理查询字符串
        query = query.strip()
        logger.debug(f"原始查询: {query}")
        
        # 如果查询已经包含高级语法,直接使用
        if any(prefix in query for prefix in ['ti:', 'abs:', 'au:', 'cat:', 'AND', 'OR', 'ANDNOT']):
            # 确保布尔运算符大写
            for op in ['AND', 'OR', 'ANDNOT']:
                query = query.replace(f' {op.lower()} ', f' {op} ')
            search_query = query
            logger.debug(f"使用高级语法查询: {search_query}")
        else:
            # 将查询拆分为单词
            terms = [term.strip() for term in query.split() if term.strip()]
            logger.debug(f"查询词: {terms}")
            
            # 构建简化的查询语法
            if len(terms) == 1:
                # 单个词直接搜索标题和摘要
                search_query = f'(ti:{terms[0]} OR abs:{terms[0]})'
            else:
                # 多个词构建精确短语搜索
                phrase = ' '.join(terms)
                search_query = f'(ti:"{phrase}" OR abs:"{phrase}")'
            
            logger.debug(f"构建的查询: {search_query}")
        
        # 添加年份过滤
        if "year_range" in filters:
            start_year, end_year = filters["year_range"]
            if start_year and end_year and start_year <= end_year:
                # 使用 submittedDate，格式：YYYYMMDDHHSS
                start_date = f"{start_year}01010000"
                end_date = f"{end_year}12312359"
                date_filter = f' AND submittedDate:[{start_date} TO {end_date}]'
                search_query = f"{search_query}{date_filter}"
                logger.debug(f"添加日期过滤后的查询: {search_query}")
        
        # URL 编码,保留特殊字符
        encoded_query = quote(search_query, safe=':"()[]+-')
        logger.debug(f"URL编码后的查询: {encoded_query}")
        return encoded_query

    async def search_papers(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        搜索论文
        
        Args:
            query: 搜索查询字符串
            filters: 过滤条件
            
        Returns:
            List[Dict[str, Any]]: 论文列表
        """
        try:
            if not query.strip():
                return []
                
            # 构建查询参数
            search_query = self._build_search_query(query, filters)
            params = {
                "search_query": search_query,
                "start": 0,
                "max_results": min(filters.get("papers_limit", 100), 100),
                "sortBy": "submittedDate",
                "sortOrder": "descending"
            }
            
            # 正确构建完整的URL
            query_string = urlencode(params)
            full_url = f"{self.base_url}?{query_string}"
            
            logger.info(f"开始搜索arxiv论文: {query}")
            logger.info(f"完整URL: {full_url}")
            logger.info(f"查询参数: {params}")
            
            # 等待速率限制
            await self._wait_for_rate_limit()
            
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            self.base_url,
                            params=params,
                            headers=self.headers,
                            timeout=30
                        ) as response:
                            content = await response.text()
                            logger.debug(f"API响应: {content[:500]}...")  # 记录响应内容的前500个字符
                            
                            if response.status == 200:
                                papers = self._parse_response(content)
                                logger.info(f"成功获取到 {len(papers)} 篇论文")
                                if papers:
                                    logger.info(f"第一篇论文标题: {papers[0]['title']}")
                                    logger.info(f"第一篇论文分类: {papers[0].get('primary_category', 'N/A')}")
                                    logger.info(f"第一篇论文年份: {papers[0].get('year', 'N/A')}")
                                return papers
                            elif response.status == 400:
                                logger.error(f"查询语法错误: {content}")
                                return []
                            elif response.status == 429:  # 速率限制
                                retry_count += 1
                                wait_time = 30
                                logger.warning(f"触发速率限制，等待{wait_time}秒后重试({retry_count}/{max_retries})")
                                await asyncio.sleep(wait_time)
                            else:
                                error_text = await response.text()
                                logger.error(f"Arxiv API请求失败: HTTP {response.status}, {error_text}")
                                return []
                                
                except aiohttp.ClientError as e:
                    logger.error(f"请求出错: {str(e)}")
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(5)
                    else:
                        return []
                        
        except Exception as e:
            logger.error(f"搜索arxiv论文时出错: {str(e)}")
            return []

    def _parse_response(self, content: str) -> List[Dict[str, Any]]:
        """解析API响应"""
        try:
            # 解析XML响应
            root = ET.fromstring(content)
            
            # 定义命名空间
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            papers = []
            for entry in root.findall('atom:entry', ns):
                try:
                    # 提取基本信息
                    paper = {
                        'id': entry.find('atom:id', ns).text.split('abs/')[-1],
                        'title': entry.find('atom:title', ns).text.strip(),
                        'abstract': entry.find('atom:summary', ns).text.strip(),
                        'url': entry.find('atom:id', ns).text,
                        'pdf_url': None,
                        'authors': [],
                        'journal_info': {
                            'title': 'arXiv',
                            'impact_factor': 'N/A',
                            'jcr_quartile': 'N/A',
                            'cas_quartile': 'N/A'
                        }
                    }
                    
                    # 提取PDF链接
                    for link in entry.findall('atom:link', ns):
                        if link.get('title') == 'pdf':
                            paper['pdf_url'] = link.get('href')
                            break
                    
                    # 提取作者信息
                    for author in entry.findall('atom:author', ns):
                        name = author.find('atom:name', ns).text
                        affiliation = author.find('arxiv:affiliation', ns)
                        author_info = {
                            'name': name,
                            'affiliation': affiliation.text if affiliation is not None else None
                        }
                        paper['authors'].append(author_info)
                    
                    # 提取发布日期
                    published = entry.find('atom:published', ns)
                    if published is not None:
                        paper['year'] = int(published.text[:4])
                    
                    # 提取分类信息
                    primary_category = entry.find('arxiv:primary_category', ns)
                    if primary_category is not None:
                        paper['primary_category'] = primary_category.get('term')
                    
                    papers.append(paper)
                    
                except Exception as e:
                    logger.error(f"解析论文条目时出错: {str(e)}")
                    continue
            
            return papers
            
        except Exception as e:
            logger.error(f"解析arxiv响应时出错: {str(e)}")
            return []

    async def get_paper_details(self, paper_id: str) -> Dict[str, Any]:
        """获取论文详细信息"""
        try:
            params = {
                "id_list": paper_id,
                "max_results": 1
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.base_url,
                    params=params,
                    headers=self.headers,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        content = await response.text()
                        papers = self._parse_response(content)
                        return papers[0] if papers else {}
                    return {}
                    
        except Exception as e:
            logger.error(f"获取arxiv论文详情时出错: {str(e)}")
            return {}

    async def get_paper_citations(self, paper_id: str) -> List[Dict[str, Any]]:
        """获取论文引用信息"""
        # Arxiv API不提供引用信息
        return []

    async def get_paper_references(self, paper_id: str) -> List[Dict[str, Any]]:
        """获取论文参考文献"""
        # Arxiv API不提供参考文献信息
        return []

    def get_source_name(self) -> str:
        """获取数据源名称"""
        return "arxiv" 