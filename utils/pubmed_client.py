"""
PubMed API客户端
"""
import aiohttp
import logging
import time
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from .paper_source_interface import PaperSourceInterface

logger = logging.getLogger(__name__)

class PubMedClient(PaperSourceInterface):
    """
    PubMed API客户端类
    """
    def __init__(self, api_key: Optional[str] = None):
        """初始化客户端"""
        
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/xml"
        }
        self.request_interval = 3  # 每次请求间隔3秒
        self.last_request_time = 0
        
    def _wait_for_rate_limit(self):
        """实现请求速率限制"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.request_interval:
            sleep_time = self.request_interval - elapsed
            logger.debug(f"等待 {sleep_time:.2f} 秒以遵守速率限制")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

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
            # 构建搜索参数
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": min(filters.get("papers_limit", 100), 100),
                "retmode": "xml"
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            # 添加年份过滤
            if "year_range" in filters:
                start_year, end_year = filters["year_range"]
                if start_year and end_year:
                    params["term"] += f" AND {start_year}:{end_year}[dp]"
            
            logger.info(f"开始搜索PubMed论文: {query}")
            logger.info(f"查询参数: {params}")
            
            # 先获取文章ID列表
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/esearch.fcgi",
                    params=params,
                    headers=self.headers,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        content = await response.text()
                        id_list = self._parse_search_response(content)
                        
                        if not id_list:
                            logger.warning("未找到匹配的文章")
                            return []
                            
                        # 获取文章详情
                        return await self._fetch_papers_details(id_list)
                    else:
                        error_text = await response.text()
                        logger.error(f"PubMed API搜索请求失败: HTTP {response.status}, {error_text}")
                        return []
                        
        except Exception as e:
            logger.error(f"搜索PubMed论文时出错: {str(e)}")
            return []

    def _parse_search_response(self, content: str) -> List[str]:
        """解析搜索响应,提取文章ID列表"""
        try:
            soup = BeautifulSoup(content, 'xml')
            id_list = []
            
            for id_elem in soup.find_all('Id'):
                id_list.append(id_elem.text)
                
            return id_list
            
        except Exception as e:
            logger.error(f"解析PubMed搜索响应时出错: {str(e)}")
            return []

    async def _fetch_papers_details(self, id_list: List[str]) -> List[Dict[str, Any]]:
        """获取文章详细信息"""
        try:
            params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml"
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/efetch.fcgi",
                    params=params,
                    headers=self.headers,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        content = await response.text()
                        return self._parse_papers_details(content)
                    else:
                        error_text = await response.text()
                        logger.error(f"获取PubMed文章详情失败: HTTP {response.status}, {error_text}")
                        return []
                        
        except Exception as e:
            logger.error(f"获取PubMed文章详情时出错: {str(e)}")
            return []

    def _parse_papers_details(self, content: str) -> List[Dict[str, Any]]:
        """解析文章详细信息"""
        try:
            soup = BeautifulSoup(content, 'xml')
            papers = []
            
            for article in soup.find_all('PubmedArticle'):
                try:
                    # 提取基本信息
                    paper = {
                        'id': article.find('PMID').text if article.find('PMID') else None,
                        'title': article.find('ArticleTitle').text if article.find('ArticleTitle') else 'No title available',
                        'abstract': article.find('Abstract').text if article.find('Abstract') else 'No abstract available',
                        'url': None,
                        'pdf_url': None,
                        'authors': [],
                        'journal_info': {
                            'title': None,
                            'impact_factor': 'N/A',
                            'jcr_quartile': 'N/A',
                            'cas_quartile': 'N/A'
                        }
                    }
                    
                    # 设置URL
                    if paper['id']:
                        paper['url'] = f"https://pubmed.ncbi.nlm.nih.gov/{paper['id']}/"
                    
                    # 提取作者信息
                    author_list = article.find('AuthorList')
                    if author_list:
                        for author in author_list.find_all('Author'):
                            last_name = author.find('LastName')
                            fore_name = author.find('ForeName')
                            if last_name and fore_name:
                                author_info = {
                                    'name': f"{last_name.text} {fore_name.text}",
                                    'affiliation': None
                                }
                                paper['authors'].append(author_info)
                    
                    # 提取期刊信息
                    journal = article.find('Journal')
                    if journal:
                        journal_title = journal.find('Title')
                        if journal_title:
                            paper['journal_info']['title'] = journal_title.text
                    
                    # 提取发布年份
                    pub_date = article.find('PubDate')
                    if pub_date:
                        year = pub_date.find('Year')
                        if year:
                            paper['year'] = int(year.text)
                    
                    papers.append(paper)
                    
                except Exception as e:
                    logger.error(f"解析单篇文章时出错: {str(e)}")
                    continue
            
            return papers
            
        except Exception as e:
            logger.error(f"解析PubMed文章详情时出错: {str(e)}")
            return []

    async def get_paper_details(self, paper_id: str) -> Dict[str, Any]:
        """获取论文详细信息"""
        try:
            papers = await self._fetch_papers_details([paper_id])
            return papers[0] if papers else {}
            
        except Exception as e:
            logger.error(f"获取PubMed论文详情时出错: {str(e)}")
            return {}

    async def get_paper_citations(self, paper_id: str) -> List[Dict[str, Any]]:
        """获取论文引用信息"""
        # PubMed API不提供引用信息
        return []

    async def get_paper_references(self, paper_id: str) -> List[Dict[str, Any]]:
        """获取论文参考文献"""
        # PubMed API不提供参考文献信息
        return []

    def get_source_name(self) -> str:
        """获取数据源名称"""
        return "pubmed" 