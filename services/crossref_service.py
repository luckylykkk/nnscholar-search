"""
Crossref API服务 - 用于验证文献真实性
"""

import requests
import logging
import time
import threading
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

logger = logging.getLogger(__name__)


class CrossrefService:
    """Crossref API服务类"""

    def __init__(self):
        self.base_url = "https://api.crossref.org"
        self.pubmed_base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NNScholar/1.0 (mailto:support@nnscholar.com)'
        })
        
    def search_work(self, title: str, author: str = None, year: str = None) -> Optional[Dict[str, Any]]:
        """搜索单篇文献"""
        try:
            # 构建查询参数
            query_parts = []
            if title:
                # 清理标题，移除特殊字符
                clean_title = re.sub(r'[^\w\s]', ' ', title).strip()
                query_parts.append(f'title:"{clean_title}"')

            if author:
                # 提取第一作者姓氏
                author_parts = author.split(',')[0].strip()
                if author_parts:
                    query_parts.append(f'author:"{author_parts}"')

            if year:
                query_parts.append(f'published:{year}')

            if not query_parts:
                return None

            query = ' AND '.join(query_parts)

            # 发送请求
            url = f"{self.base_url}/works"
            params = {
                'query': query,
                'rows': 5,  # 限制返回结果数量
                'select': 'DOI,title,author,published-print,published-online,container-title,is-referenced-by-count'
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            items = data.get('message', {}).get('items', [])

            if items:
                # 返回最匹配的结果
                best_match = items[0]
                return self._format_work_data(best_match)

            return None

        except Exception as e:
            logger.error(f"Crossref搜索失败: {str(e)}")
            return None

    def search_by_title(self, title: str) -> List[Dict[str, Any]]:
        """通过标题搜索文献，返回多个结果"""
        try:
            if not title:
                return []

            # 清理标题，移除特殊字符和引号
            clean_title = re.sub(r'[^\w\s]', ' ', title).strip()
            # 移除多余的空格
            clean_title = ' '.join(clean_title.split())

            # 发送请求
            url = f"{self.base_url}/works"
            params = {
                'query.title': clean_title,
                'rows': 3,  # 返回前3个最匹配的结果
                'select': 'DOI,title,author,published-print,published-online,container-title,is-referenced-by-count'
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            items = data.get('message', {}).get('items', [])

            results = []
            for item in items:
                formatted_data = self._format_work_data(item)
                if formatted_data:
                    results.append(formatted_data)

            return results

        except Exception as e:
            logger.error(f"Crossref标题搜索失败: {str(e)}")
            return []
    
    def verify_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """通过DOI验证文献"""
        try:
            if not doi:
                return None
            
            # 清理DOI
            clean_doi = doi.strip().replace('https://doi.org/', '').replace('http://dx.doi.org/', '')
            
            url = f"{self.base_url}/works/{clean_doi}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            work = data.get('message', {})
            
            return self._format_work_data(work)
            
        except Exception as e:
            logger.error(f"DOI验证失败 {doi}: {str(e)}")
            return None

    def verify_pmid(self, pmid: str) -> Optional[Dict[str, Any]]:
        """通过PMID验证文献"""
        try:
            if not pmid:
                return None

            # 清理PMID
            clean_pmid = pmid.strip()

            # 使用PubMed API获取文献信息
            url = f"{self.pubmed_base_url}/esummary.fcgi"
            params = {
                'db': 'pubmed',
                'id': clean_pmid,
                'retmode': 'json',
                'tool': 'NNScholar',
                'email': 'contact@nnscholar.com'
            }

            # 添加重试机制，参考PubMed服务的实现
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(url, params=params, timeout=15)
                    response.raise_for_status()
                    break  # 成功，跳出重试循环
                except (requests.exceptions.ConnectionError, requests.exceptions.SSLError) as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                        logger.warning(f"PMID {clean_pmid} 连接失败 (尝试 {attempt + 1}/{max_retries})，{wait_time}秒后重试: {e}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"PMID {clean_pmid} 连接失败，已重试 {max_retries} 次: {e}")
                        return None
                except requests.exceptions.Timeout as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"PMID {clean_pmid} 请求超时 (尝试 {attempt + 1}/{max_retries})，{wait_time}秒后重试: {e}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"PMID {clean_pmid} 请求超时，已重试 {max_retries} 次: {e}")
                        return None

            data = response.json()

            # 检查是否有结果
            if 'result' not in data or clean_pmid not in data['result']:
                logger.warning(f"PMID {clean_pmid} 未找到结果")
                return None

            article_data = data['result'][clean_pmid]

            # 检查是否有错误
            if 'error' in article_data:
                logger.warning(f"PMID {clean_pmid} 有错误: {article_data.get('error')}")
                return None

            return self._format_pubmed_data(article_data, clean_pmid)

        except Exception as e:
            logger.error(f"PMID验证失败 {pmid}: {str(e)}")
            return None

    def _format_pubmed_data(self, article_data: Dict[str, Any], pmid: str) -> Dict[str, Any]:
        """格式化PubMed数据"""
        try:
            # 提取标题
            title = article_data.get('title', '')

            # 提取作者
            authors = []
            if 'authors' in article_data:
                for author in article_data['authors'][:3]:  # 只取前3个作者
                    name = author.get('name', '')
                    if name:
                        authors.append(name)

            # 提取期刊
            journal = article_data.get('fulljournalname', '') or article_data.get('source', '')

            # 提取发表年份
            year = ""
            if 'pubdate' in article_data:
                pubdate = article_data['pubdate']
                # 提取年份（通常在日期字符串的开头）
                import re
                year_match = re.search(r'(\d{4})', pubdate)
                if year_match:
                    year = year_match.group(1)

            # 提取DOI（如果有）
            doi = ""
            if 'elocationid' in article_data:
                elocationid = article_data['elocationid']
                if elocationid.startswith('doi:'):
                    doi = elocationid[4:]  # 移除'doi:'前缀

            return {
                'title': title,
                'authors': authors,
                'journal': journal,
                'year': year,
                'pmid': pmid,
                'doi': doi,
                'citation_count': 0,  # PubMed API不直接提供引用次数
                'verified': True
            }

        except Exception as e:
            logger.error(f"格式化PubMed数据失败: {str(e)}")
            return None
    
    def _format_work_data(self, work: Dict[str, Any]) -> Dict[str, Any]:
        """格式化文献数据"""
        try:
            # 提取标题
            title = ""
            if 'title' in work and work['title']:
                title = work['title'][0] if isinstance(work['title'], list) else str(work['title'])
            
            # 提取作者
            authors = []
            if 'author' in work:
                for author in work['author'][:3]:  # 只取前3个作者
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if family:
                        authors.append(f"{family}, {given}".strip(', '))
            
            # 提取期刊
            journal = ""
            if 'container-title' in work and work['container-title']:
                journal = work['container-title'][0] if isinstance(work['container-title'], list) else str(work['container-title'])
            
            # 提取发表年份
            year = ""
            pub_date = work.get('published-print') or work.get('published-online')
            if pub_date and 'date-parts' in pub_date:
                date_parts = pub_date['date-parts'][0]
                if date_parts:
                    year = str(date_parts[0])
            
            # 提取DOI
            doi = work.get('DOI', '')
            
            # 提取引用次数
            citation_count = work.get('is-referenced-by-count', 0)
            
            return {
                'title': title,
                'authors': authors,
                'journal': journal,
                'year': year,
                'doi': doi,
                'citation_count': citation_count,
                'verified': True
            }
            
        except Exception as e:
            logger.error(f"格式化文献数据失败: {str(e)}")
            return None
    
    def batch_verify_references(self, references: List[Dict[str, Any]], max_workers: int = 5) -> List[Dict[str, Any]]:
        """批量验证参考文献"""
        verified_references = []
        
        def verify_single_reference(ref_data):
            """验证单个参考文献"""
            try:
                title = ref_data.get('title', '')
                author = ref_data.get('author', '')
                year = ref_data.get('year', '')
                doi = ref_data.get('doi', '')
                
                # 首先尝试DOI验证
                if doi:
                    verified = self.verify_doi(doi)
                    if verified:
                        # 合并原始数据和验证数据
                        result = {**ref_data, **verified}
                        return result
                
                # 如果DOI验证失败，尝试标题+作者搜索
                if title:
                    verified = self.search_work(title, author, year)
                    if verified:
                        # 检查标题相似度
                        if self._calculate_title_similarity(title, verified['title']) > 0.7:
                            result = {**ref_data, **verified}
                            return result
                
                # 验证失败
                return {**ref_data, 'verified': False, 'error': '无法验证文献真实性'}
                
            except Exception as e:
                logger.error(f"验证参考文献失败: {str(e)}")
                return {**ref_data, 'verified': False, 'error': str(e)}
        
        # 使用线程池并行验证
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ref = {executor.submit(verify_single_reference, ref): ref for ref in references}
            
            for future in as_completed(future_to_ref):
                try:
                    result = future.result(timeout=30)
                    verified_references.append(result)
                except Exception as e:
                    ref = future_to_ref[future]
                    logger.error(f"验证超时或失败: {str(e)}")
                    verified_references.append({**ref, 'verified': False, 'error': '验证超时'})
        
        return verified_references
    
    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """计算标题相似度"""
        try:
            # 简单的词汇重叠相似度计算
            words1 = set(title1.lower().split())
            words2 = set(title2.lower().split())
            
            if not words1 or not words2:
                return 0.0
            
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            
            return len(intersection) / len(union) if union else 0.0
            
        except Exception:
            return 0.0


# 全局服务实例
crossref_service = CrossrefService()
