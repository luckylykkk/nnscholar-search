import requests
from typing import List, Dict, Any, Optional
import logging
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import re
from fuzzywuzzy import fuzz
from .paper_source_interface import PaperSourceInterface
import aiohttp
import json
import asyncio

logger = logging.getLogger(__name__)

class SemanticScholarClient(PaperSourceInterface):
    """
    Semantic Scholar API客户端类
    """
    def __init__(self, api_key: Optional[str] = None, journal_data: Dict = None):
        """初始化客户端"""
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["x-api-key"] = api_key
        self.request_interval = 3  # 每次请求间隔3秒
        self.last_request_time = 0
        self.journal_data = journal_data or {}  # 存储期刊数据
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 最多重试3次
            backoff_factor=1,  # 重试间隔
            status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
        )
        
        # 创建会话并应用重试策略
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _wait_for_rate_limit(self):
        """实现请求速率限制"""
        current_time = time.time()

        # 总是至少等待一个最小间隔
        sleep_time = 10
        logger.debug(f"等待 {sleep_time:.2f} 秒以遵守速率限制")
        time.sleep(sleep_time)
        self.last_request_time = time.sleep()

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """发送API请求"""
        url = f"{self.base_url}/{endpoint}"
        time.sleep(10)
        response = None
        max_retries = 3  # 最大重试次数
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 添加参数验证
                if 'params' in kwargs:
                    params = kwargs['params']
                    # 移除值为 None 的参数
                    params = {k: v for k, v in params.items() if v is not None}
                    # 确保所有值都是字符串
                    params = {k: str(v) if not isinstance(v, (list, tuple)) else v 
                             for k, v in params.items()}
                    kwargs['params'] = params
                
                logger.debug(f"发送请求: {method} {url}")
                logger.debug(f"请求参数: {kwargs}")
                
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    **kwargs
                )
                
                # 记录响应状态
                logger.debug(f"响应状态码: {response.status_code}")
                
                if response.status_code == 429:
                    retry_count += 1
                    wait_time = 30  # 等待30秒
                    logger.warning(f"触发请求限制(429)，等待{wait_time}秒后进行第{retry_count}次重试")
                    time.sleep(wait_time)
                    continue
                
                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        logger.error(f"API错误响应: {error_data}")
                    except:
                        logger.error(f"API错误响应: {response.text}")
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if response:
                    try:
                        error_data = response.json()
                        if 'error' in error_data:
                            error_msg = error_data['error']
                    except:
                        pass
                
                if response and response.status_code == 429:
                    if retry_count < max_retries - 1:  # 如果还有重试机会，继续循环
                        continue
                    error_msg = "API 请求过于频繁，请稍后再试"
                elif response and response.status_code == 400:
                    error_msg = f"搜索请求无效: {error_msg}"
                elif response and response.status_code == 403:
                    error_msg = "API 访问受限，请检查 API 密钥"
                elif response and response.status_code >= 500:
                    error_msg = "Semantic Scholar 服务器错误，请稍后再试"
            
                logger.error(f"API请求失败: {error_msg}")
                if retry_count >= max_retries - 1:  # 如果已经重试到最大次数
                    raise Exception(error_msg)
                retry_count += 1
                wait_time = 30  # 等待30秒
                logger.warning(f"请求失败，等待{wait_time}秒后进行第{retry_count}次重试")
                time.sleep(wait_time)

    def search_papers(
        self,
        query: str,
        fields: List[str] = None,
        limit: int = 100,
        offset: int = 0,
        year_range: Optional[tuple] = None,
        venue: Optional[str] = None,
        fields_of_study: Optional[List[str]] = None,
        min_citation_count: Optional[int] = None,
        publication_types: Optional[List[str]] = None,
        open_access_only: bool = False
    ) -> List[Dict]:
        """
        搜索论文

        Args:
            query: 搜索查询文本
            fields: 要返回的字段列表
            limit: 返回结果数量限制
            year_range: 发表年份范围,如(2020, 2023)
            venue: 期刊/会议名称
            fields_of_study: 学科领域
            min_citation_count: 最小引用数
            publication_types: 文献类型
            open_access_only: 是否只返回开放获取论文

        Returns:
            论文列表
        """
        if not fields:
            fields = [
                "paperId",
                "title",
                "abstract",
                "year",
                "citationCount",
                "authors",
                "fieldsOfStudy",
                "publicationTypes",
                "url",
                "venue",
                "publicationVenue",
                "openAccessPdf"
            ]

        try:
            query = query.strip()
            logger.info(f"开始搜索论文: {query}")
            
            params = {
                "query": query,
                "fields": ",".join(fields),
                "limit": min(limit, 100),
                "offset": offset
            }
            
            if year_range:
                start_year, end_year = year_range
                params["year"] = str(start_year)
            
            if min_citation_count is not None:
                params["minCitationCount"] = min_citation_count
            
            if fields_of_study:
                params["fieldsOfStudy"] = fields_of_study
            
            if publication_types:
                params["publicationTypes"] = publication_types
            
            if open_access_only:
                params["isOpenAccess"] = "true"
            
            logger.info(f"搜索参数: {params}")
            
            response = self._make_request('GET', 'paper/search', params=params)
            papers = response.get('data', [])
            
            if year_range:
                start_year, end_year = year_range
                papers = [
                    paper for paper in papers
                    if paper.get('year') and start_year <= paper['year'] <= end_year
                ]
            
            logger.info(f"找到 {len(papers)} 篇论文")
            if papers:
                logger.info("论文详情:")
                for i, paper in enumerate(papers[:5], 1):  # 只记录前5篇
                    try:
                        logger.info(f"\n论文 {i}:")
                        logger.info(f"- ID: {paper.get('paperId', 'Unknown')}")
                        logger.info(f"- 标题: {paper.get('title', 'Unknown')}")
                        logger.info(f"- 年份: {paper.get('year', 'Unknown')}")
                        logger.info(f"- 引用数: {paper.get('citationCount', 0)}")
                        logger.info(f"- 领域: {paper.get('fieldsOfStudy', [])}")
                        
                        # 安全处理作者名字
                        authors = paper.get('authors', [])
                        author_names = []
                        for author in authors:
                            if isinstance(author, dict):
                                name = author.get('name', '')
                                if name:
                                    # 移除或替换可能导致编码问题的字符
                                    name = name.encode('ascii', 'ignore').decode()
                                    author_names.append(name)
                        
                        logger.info(f"- 作者: {author_names}")
                        
                        abstract = paper.get('abstract', '')
                        if abstract:
                            # 截取摘要并确保编码安全
                            safe_abstract = abstract[:200].encode('ascii', 'ignore').decode()
                            logger.info(f"- 摘要: {safe_abstract}...")
                    except Exception as e:
                        logger.warning(f"处理论文详情时出错: {str(e)}")
                        continue
            
            # 在处理论文数据时添加调试信息
            processed_papers = []
            for paper in papers:
                try:
                    # 获取 PDF 信息
                    pdf_info = paper.get('openAccessPdf')
                    pdf_url = None
                    if pdf_info and isinstance(pdf_info, dict):
                        pdf_url = pdf_info.get('url')
                        if pdf_url:
                            logger.info(f"找到PDF链接: {pdf_url}")
                            logger.info(f"PDF状态: {pdf_info.get('status')}")
                    
                    # 获取期刊/会议名称
                    venue_name = (paper.get('venue') or 
                                 (paper.get('publicationVenue', {}) or {}).get('name') or 
                                 'Unknown')
                    
                    # 获取期刊指标信息
                    journal_metrics = self.get_journal_metrics(venue_name)
                    
                    # 处理作者信息
                    authors = []
                    for author in paper.get('authors', []):
                        if isinstance(author, dict) and author.get('name'):
                            authors.append({
                                'name': author['name'].encode('ascii', 'ignore').decode()
                            })
                    
                    processed_paper = {
                        'id': paper.get('paperId', ''),  # 添加论文ID
                        'title': paper.get('title', ''),
                        'url': f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}",
                        'abstract': paper.get('abstract', ''),
                        'year': paper.get('year'),
                        'citationCount': paper.get('citationCount', 0),
                        'authors': authors,
                        'pdf_url': pdf_url,  # 直接在顶层添加 PDF URL
                        'journal_info': {
                            'title': venue_name,
                            'impact_factor': journal_metrics.get('impact_factor', 'N/A'),
                            'jcr_quartile': journal_metrics.get('jcr_quartile', 'N/A'),
                            'cas_quartile': journal_metrics.get('cas_quartile', 'N/A')
                        }
                    }
                    
                    # 记录最终的论文信息
                    logger.info(f"处理后的论文信息:")
                    logger.info(f"- 标题: {processed_paper['title']}")
                    logger.info(f"- PDF URL: {processed_paper['pdf_url']}")
                    
                    processed_papers.append(processed_paper)
                    
                except Exception as e:
                    logger.error(f"处理论文数据时出错: {str(e)}\n论文数据: {paper}")
                    continue
            
            return processed_papers
            
        except Exception as e:
            logger.error(f"搜索论文失败: {str(e)}")
            raise Exception(f"Semantic Scholar API 搜索失败: {str(e)}")

    def get_journal_metrics(self, journal_name: str) -> Dict:
        """获取期刊指标信息"""
        try:
            if not journal_name or not self.journal_data:
                return self._get_default_metrics()
            
            # 标准化期刊名称
            def normalize_journal_name(name: str) -> str:
                if not name:
                    return ''
                # 转换为小写
                name = name.lower()
                # 移除特殊字符
                name = re.sub(r'[^\w\s]', '', name)
                # 移除多余空格
                name = ' '.join(name.split())
                return name
            
            journal_name = normalize_journal_name(journal_name)
            
            # 跳过一些常见的非期刊来源
            skip_sources = {
                'arxiv',
                'unknown',
                'conference',
                'symposium',
                'proceedings',
                'dissertation'
            }
            
            if any(source in journal_name for source in skip_sources):
                logger.info(f"跳过非期刊来源: {journal_name}")
                return self._get_default_metrics()
            
            # 尝试在期刊数据中查找匹配的记录
            best_match = None
            best_ratio = 0
            
            for issn, journal_info in self.journal_data.items():
                db_journal_name = normalize_journal_name(journal_info['title'])
                # 使用模糊匹配
                ratio = fuzz.ratio(journal_name, db_journal_name)
                if ratio > 85 and ratio > best_ratio:  # 设置较高的匹配阈值
                    best_match = journal_info
                    best_ratio = ratio
            
            if best_match:
                # 获取分区信息
                cas_quartile = best_match.get('cas_quartile', 'N/A')
                # 如果是数字格式，转换为B格式
                if cas_quartile.isdigit():
                    cas_quartile = f"B{cas_quartile}"
                
                metrics = {
                    'impact_factor': best_match.get('if', 'N/A'),
                    'jcr_quartile': best_match.get('jcr_quartile', 'N/A'),
                    'cas_quartile': cas_quartile
                }
                logger.info(f"找到期刊指标 (匹配度: {best_ratio}%): {metrics} (期刊: {journal_name})")
                return metrics
            
            logger.info(f"未找到匹配的期刊指标: {journal_name}")
            return self._get_default_metrics()
        
        except Exception as e:
            logger.error(f"获取期刊指标失败: {str(e)}")
            return self._get_default_metrics()
        
    def _get_default_metrics(self) -> Dict:
        """返回默认的期刊指标"""
        return {
            'impact_factor': 'N/A',
            'jcr_quartile': 'N/A',
            'cas_quartile': 'N/A'
        }

    def get_paper_details(self, paper_id: str, fields: List[str] = None) -> Dict:
        """
        获取论文详细信息

        Args:
            paper_id: 论文ID
            fields: 要返回的字段列表

        Returns:
            论文详细信息
        """
        if not fields:
            fields = [
                "paperId",
                "title",
                "abstract",
                "year",
                "citationCount",
                "authors",
                "fieldsOfStudy",
                "publicationTypes"
            ]

        return self._make_request('GET', f'paper/{paper_id}', params={'fields': ','.join(fields)})

    def get_paper_citations(
        self,
        paper_id: str,
        fields: List[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict:
        """获取引用该论文的文献"""
        if not fields:
            fields = ["paperId", "title", "year", "authors"]

        params = {
            "fields": ",".join(fields),
            "limit": min(limit, 1000),
            "offset": offset
        }

        try:
            response = requests.get(
                f"{self.base_url}/paper/{paper_id}/citations",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"获取论文引用时发生错误: {str(e)}")
            raise Exception(f"Semantic Scholar API调用失败: {str(e)}")

    def get_paper_references(
        self, 
        paper_id: str, 
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        获取该论文引用的文献

        Args:
            paper_id: 论文ID
            limit: 返回结果数量限制

        Returns:
            参考文献信息
        """
        try:
            endpoint = f"{self.base_url}/paper/{paper_id}/references"
            
            params = {
                'limit': min(limit, 100)
            }
            
            logger.info(f"获取论文参考文献: {paper_id}")
            
            time.sleep(self.request_interval)
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params
            )
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"获取论文参考文献失败: {str(e)}")
            return {"data": []}

    def get_source_name(self) -> str:
        return "semanticscholar"

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
            logger.info(f"开始搜索论文: {query}")
            logger.info(f"过滤条件: {filters}")
            
            # 构建查询参数
            params = {
                "query": query,
                "fields": "paperId,title,abstract,year,citationCount,authors,venue,publicationVenue,openAccessPdf",
                "limit": min(filters.get("limit", 100), 100)  # 限制最大返回数量
            }
            
            # 添加年份过滤
            if "year_range" in filters:
                start_year, end_year = filters["year_range"]
                if start_year and end_year:
                    params["year"] = f"{start_year}-{end_year}"
            
            # 添加引用次数过滤
            if "min_citation_count" in filters:
                params["minCitationCount"] = filters["min_citation_count"]
            
            max_retries = 3  # 最大重试次数
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{self.base_url}/paper/search",
                            params=params,
                            headers=self.headers,
                            timeout=30
                        ) as response:
                            if response.status == 429:
                                retry_count += 1
                                wait_time = 30  # 等待30秒
                                logger.warning(f"触发请求限制(429)，等待{wait_time}秒后进行第{retry_count}次重试")
                                await asyncio.sleep(wait_time)
                                continue
                                
                            if response.status == 200:
                                data = await response.json()
                                papers = data.get("data", [])
                                
                                # 处理每篇论文的数据
                                processed_papers = []
                                for paper in papers:
                                    try:
                                        # 获取期刊信息
                                        venue_name = (paper.get('venue') or 
                                                   (paper.get('publicationVenue', {}) or {}).get('name') or 
                                                   'Unknown')
                                        
                                        # 获取期刊指标
                                        journal_metrics = self.get_journal_metrics(venue_name)
                                        
                                        # 处理作者信息
                                        authors = []
                                        for author in paper.get('authors', []):
                                            if isinstance(author, dict) and author.get('name'):
                                                authors.append({
                                                    'name': author['name']
                                                })
                                        
                                        # 构建论文信息
                                        processed_paper = {
                                            'id': paper.get('paperId', ''),
                                            'title': paper.get('title', ''),
                                            'abstract': paper.get('abstract', ''),
                                            'year': paper.get('year'),
                                            'citationCount': paper.get('citationCount', 0),
                                            'authors': authors,
                                            'url': f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}",
                                            'pdf_url': (paper.get('openAccessPdf', {}) or {}).get('url'),
                                            'journal_info': {
                                                'title': venue_name,
                                                'impact_factor': journal_metrics.get('impact_factor', 'N/A'),
                                                'jcr_quartile': journal_metrics.get('jcr_quartile', 'N/A'),
                                                'cas_quartile': journal_metrics.get('cas_quartile', 'N/A')
                                            }
                                        }
                                        
                                        # 应用过滤条件
                                        if self._apply_filters(processed_paper, filters):
                                            processed_papers.append(processed_paper)
                                        
                                    except Exception as e:
                                        logger.error(f"处理论文数据时出错: {str(e)}")
                                        continue
                                        
                                logger.info(f"搜索完成，找到 {len(processed_papers)} 篇论文")
                                return processed_papers
                            else:
                                error_text = await response.text()
                                logger.error(f"API请求失败: HTTP {response.status}, {error_text}")
                                if retry_count >= max_retries - 1:  # 如果已经重试到最大次数
                                    return []
                                retry_count += 1
                                wait_time = 30  # 等待30秒
                                logger.warning(f"请求失败，等待{wait_time}秒后进行第{retry_count}次重试")
                                await asyncio.sleep(wait_time)
                                
                except Exception as e:
                    logger.error(f"请求出错: {str(e)}")
                    if retry_count >= max_retries - 1:  # 如果已经重试到最大次数
                        return []
                    retry_count += 1
                    wait_time = 30  # 等待30秒
                    logger.warning(f"请求出错，等待{wait_time}秒后进行第{retry_count}次重试")
                    await asyncio.sleep(wait_time)
                    
            return []  # 如果所有重试都失败了
                        
        except Exception as e:
            logger.error(f"搜索论文时出错: {str(e)}")
            return []

    async def get_paper_details(self, paper_id: str) -> Dict[str, Any]:
        """
        获取论文详细信息
        
        Args:
            paper_id: 论文ID
            
        Returns:
            Dict[str, Any]: 论文详细信息
        """
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/paper/{paper_id}") as response:
                if response.status == 200:
                    return await response.json()
                return {}

    async def get_paper_citations(self, paper_id: str) -> List[Dict[str, Any]]:
        """
        获取论文引用信息
        
        Args:
            paper_id: 论文ID
            
        Returns:
            List[Dict[str, Any]]: 引用论文列表
        """
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/paper/{paper_id}/citations") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("citations", [])
                return []

    async def get_paper_references(self, paper_id: str) -> List[Dict[str, Any]]:
        """
        获取论文参考文献
        
        Args:
            paper_id: 论文ID
            
        Returns:
            List[Dict[str, Any]]: 参考文献列表
        """
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/paper/{paper_id}/references") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("references", [])
                return []

    def _apply_filters(self, paper: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """
        应用过滤条件
        
        Args:
            paper: 论文数据
            filters: 过滤条件
            
        Returns:
            bool: 是否通过过滤
        """
        try:
            # 年份过滤
            if "year_range" in filters:
                start_year, end_year = filters["year_range"]
                if start_year and end_year:
                    paper_year = paper.get("year")
                    if not paper_year or not (start_year <= paper_year <= end_year):
                        return False
            
            # 引用次数过滤
            if "min_citation_count" in filters:
                min_cites = filters["min_citation_count"]
                if paper.get("citationCount", 0) < min_cites:
                    return False
            
            # JCR分区过滤
            if "jcr_quartile" in filters and filters["jcr_quartile"]:
                paper_quartile = paper["journal_info"]["jcr_quartile"]
                if paper_quartile not in filters["jcr_quartile"]:
                    return False
            
            # CAS分区过滤
            if "cas_quartile" in filters and filters["cas_quartile"]:
                paper_quartile = paper["journal_info"]["cas_quartile"]
                if paper_quartile not in filters["cas_quartile"]:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"应用过滤条件时出错: {str(e)}")
            return False

    def get_journal_metrics(self, journal_name: str) -> Dict[str, Any]:
        """
        获取期刊指标信息
        
        Args:
            journal_name: 期刊名称
            
        Returns:
            Dict[str, Any]: 期刊指标信息
        """
        try:
            if not journal_name or not self.journal_data:
                return self._get_default_metrics()
            
            # 在期刊数据中查找匹配的记录
            for journal_info in self.journal_data.values():
                if journal_info["title"].lower() == journal_name.lower():
                    return {
                        "impact_factor": journal_info.get("if", "N/A"),
                        "jcr_quartile": journal_info.get("jcr_quartile", "N/A"),
                        "cas_quartile": journal_info.get("cas_quartile", "N/A")
                    }
            
            return self._get_default_metrics()
            
        except Exception as e:
            logger.error(f"获取期刊指标时出错: {str(e)}")
            return self._get_default_metrics()
    
    def _get_default_metrics(self) -> Dict[str, Any]:
        """
        获取默认的期刊指标
        
        Returns:
            Dict[str, Any]: 默认的期刊指标
        """
        return {
            "impact_factor": "N/A",
            "jcr_quartile": "N/A",
            "cas_quartile": "N/A"
        } 