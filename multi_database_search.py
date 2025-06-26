"""
多数据库学术文献检索模块
支持多个免费开放的学术数据库API
"""

import requests
import json
import time
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple
import urllib.parse
import re

# 配置日志
logger = logging.getLogger(__name__)

class MultiDatabaseSearcher:
    """多数据库学术文献检索器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NNScholar/1.0 (mailto:support@nnscholar.com)',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        })
    
    def search_openalex(self, query: str, max_results: int = 600) -> Tuple[List[Dict], str, int, int]:
        """
        OpenAlex API搜索
        覆盖全学科领域，超过2.5亿篇学术文献
        """
        try:
            logger.info(f"开始OpenAlex搜索，查询: {query}, 最大结果数: {max_results}")
            
            # OpenAlex API端点
            base_url = "https://api.openalex.org/works"
            
            # 构建搜索参数
            params = {
                'search': query,
                'per-page': min(max_results, 200),  # OpenAlex单次最多200条
                'cursor': '*',  # 用于分页
                'select': 'id,title,display_name,publication_year,publication_date,type,open_access,authorships,concepts,abstract_inverted_index,biblio,primary_location,locations,best_oa_location,sustainable_development_goals,grants,referenced_works,related_works,ngrams_url,abstract_inverted_index,cited_by_count,counts_by_year,updated_date,created_date'
            }
            
            all_papers = []
            total_count = 0
            page_count = 0
            max_pages = (max_results + 199) // 200  # 计算需要的页数
            
            while len(all_papers) < max_results and page_count < max_pages:
                try:
                    response = self.session.get(base_url, params=params, timeout=30)
                    response.raise_for_status()
                    
                    data = response.json()
                    results = data.get('results', [])
                    
                    if page_count == 0:
                        total_count = data.get('meta', {}).get('count', 0)
                        logger.info(f"OpenAlex找到 {total_count} 篇相关文献")
                    
                    if not results:
                        break
                    
                    # 处理每篇文献
                    for work in results:
                        if len(all_papers) >= max_results:
                            break
                            
                        paper = self._parse_openalex_work(work)
                        if paper:
                            all_papers.append(paper)
                    
                    # 获取下一页的cursor
                    next_cursor = data.get('meta', {}).get('next_cursor')
                    if not next_cursor:
                        break
                    
                    params['cursor'] = next_cursor
                    page_count += 1
                    
                    # 避免请求过快
                    time.sleep(0.1)
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"OpenAlex请求失败: {e}")
                    break
            
            logger.info(f"OpenAlex搜索完成，获取 {len(all_papers)} 篇文献")
            return all_papers, query, total_count, len(all_papers)
            
        except Exception as e:
            logger.error(f"OpenAlex搜索出错: {e}")
            return [], query, 0, 0
    
    def search_arxiv(self, query: str, max_results: int = 600) -> Tuple[List[Dict], str, int, int]:
        """
        arXiv API搜索
        覆盖物理学、数学、计算机科学、生物学等预印本论文
        """
        try:
            logger.info(f"开始arXiv搜索，查询: {query}, 最大结果数: {max_results}")
            
            # arXiv API端点
            base_url = "http://export.arxiv.org/api/query"
            
            # 构建搜索参数
            params = {
                'search_query': f'all:{query}',
                'start': 0,
                'max_results': min(max_results, 2000),  # arXiv单次最多2000条
                'sortBy': 'relevance',
                'sortOrder': 'descending'
            }
            
            response = self.session.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            # 解析XML响应
            root = ET.fromstring(response.content)
            
            # 命名空间
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'opensearch': 'http://a9.com/-/spec/opensearch/1.1/',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            # 获取总数
            total_results = root.find('opensearch:totalResults', namespaces)
            total_count = int(total_results.text) if total_results is not None else 0
            
            # 解析文献条目
            entries = root.findall('atom:entry', namespaces)
            papers = []
            
            for entry in entries:
                paper = self._parse_arxiv_entry(entry, namespaces)
                if paper:
                    papers.append(paper)
            
            logger.info(f"arXiv搜索完成，找到 {total_count} 篇，获取 {len(papers)} 篇文献")
            return papers, query, total_count, len(papers)
            
        except Exception as e:
            logger.error(f"arXiv搜索出错: {e}")
            return [], query, 0, 0
    
    def search_semantic_scholar(self, query: str, max_results: int = 600) -> Tuple[List[Dict], str, int, int]:
        """
        Semantic Scholar API搜索
        AI驱动的学术搜索，覆盖计算机科学、生物医学等多领域
        """
        try:
            logger.info(f"开始Semantic Scholar搜索，查询: {query}, 最大结果数: {max_results}")
            
            # Semantic Scholar API端点
            base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
            
            # 构建搜索参数
            params = {
                'query': query,
                'limit': min(max_results, 100),  # Semantic Scholar单次最多100条
                'fields': 'paperId,title,abstract,year,authors,venue,publicationTypes,publicationDate,citationCount,influentialCitationCount,isOpenAccess,openAccessPdf,fieldsOfStudy,s2FieldsOfStudy,publicationVenue,externalIds'
            }
            
            all_papers = []
            total_count = 0
            offset = 0
            
            while len(all_papers) < max_results:
                try:
                    params['offset'] = offset
                    
                    response = self.session.get(base_url, params=params, timeout=30)
                    response.raise_for_status()
                    
                    data = response.json()
                    results = data.get('data', [])
                    
                    if offset == 0:
                        total_count = data.get('total', 0)
                        logger.info(f"Semantic Scholar找到 {total_count} 篇相关文献")
                    
                    if not results:
                        break
                    
                    # 处理每篇文献
                    for paper_data in results:
                        if len(all_papers) >= max_results:
                            break
                            
                        paper = self._parse_semantic_scholar_paper(paper_data)
                        if paper:
                            all_papers.append(paper)
                    
                    offset += len(results)
                    
                    # 避免请求过快
                    time.sleep(0.1)
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Semantic Scholar请求失败: {e}")
                    break
            
            logger.info(f"Semantic Scholar搜索完成，获取 {len(all_papers)} 篇文献")
            return all_papers, query, total_count, len(all_papers)
            
        except Exception as e:
            logger.error(f"Semantic Scholar搜索出错: {e}")
            return [], query, 0, 0
    
    def search_doaj(self, query: str, max_results: int = 600) -> Tuple[List[Dict], str, int, int]:
        """
        DOAJ API搜索
        开放获取期刊目录，覆盖所有学科的高质量同行评议内容
        """
        try:
            logger.info(f"开始DOAJ搜索，查询: {query}, 最大结果数: {max_results}")
            
            # DOAJ API端点
            base_url = "https://doaj.org/api/v2/search/articles"
            
            # 构建搜索参数
            params = {
                'q': query,
                'pageSize': min(max_results, 100),  # DOAJ单次最多100条
                'page': 1
            }
            
            all_papers = []
            total_count = 0
            page = 1
            
            while len(all_papers) < max_results:
                try:
                    params['page'] = page
                    
                    response = self.session.get(base_url, params=params, timeout=30)
                    response.raise_for_status()
                    
                    data = response.json()
                    results = data.get('results', [])
                    
                    if page == 1:
                        total_count = data.get('total', 0)
                        logger.info(f"DOAJ找到 {total_count} 篇相关文献")
                    
                    if not results:
                        break
                    
                    # 处理每篇文献
                    for article_data in results:
                        if len(all_papers) >= max_results:
                            break
                            
                        paper = self._parse_doaj_article(article_data)
                        if paper:
                            all_papers.append(paper)
                    
                    page += 1
                    
                    # 避免请求过快
                    time.sleep(0.1)
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"DOAJ请求失败: {e}")
                    break
            
            logger.info(f"DOAJ搜索完成，获取 {len(all_papers)} 篇文献")
            return all_papers, query, total_count, len(all_papers)

        except Exception as e:
            logger.error(f"DOAJ搜索出错: {e}")
            return [], query, 0, 0

    def search_crossref(self, query: str, max_results: int = 600) -> Tuple[List[Dict], str, int, int]:
        """
        Crossref API搜索
        权威的学术元数据和引用信息，覆盖全学科DOI注册的学术内容
        """
        try:
            logger.info(f"开始Crossref搜索，查询: {query}, 最大结果数: {max_results}")

            # Crossref API端点
            base_url = "https://api.crossref.org/works"

            # 构建搜索参数
            params = {
                'query': query,
                'rows': min(max_results, 1000),  # Crossref单次最多1000条
                'offset': 0,
                'sort': 'relevance',
                'order': 'desc'
            }

            all_papers = []
            total_count = 0
            offset = 0

            while len(all_papers) < max_results:
                try:
                    params['offset'] = offset

                    response = self.session.get(base_url, params=params, timeout=30)
                    response.raise_for_status()

                    data = response.json()
                    message = data.get('message', {})
                    results = message.get('items', [])

                    if offset == 0:
                        total_count = message.get('total-results', 0)
                        logger.info(f"Crossref找到 {total_count} 篇相关文献")

                    if not results:
                        break

                    # 处理每篇文献
                    for work_data in results:
                        if len(all_papers) >= max_results:
                            break

                        paper = self._parse_crossref_work(work_data)
                        if paper:
                            all_papers.append(paper)

                    offset += len(results)

                    # 避免请求过快
                    time.sleep(0.1)

                except requests.exceptions.RequestException as e:
                    logger.error(f"Crossref请求失败: {e}")
                    break

            logger.info(f"Crossref搜索完成，获取 {len(all_papers)} 篇文献")
            return all_papers, query, total_count, len(all_papers)

        except Exception as e:
            logger.error(f"Crossref搜索出错: {e}")
            return [], query, 0, 0

    def search_all_databases(self, query: str, max_results_per_db: int = 200) -> Dict[str, Tuple[List[Dict], str, int, int]]:
        """
        搜索所有数据库并返回结果
        """
        results = {}

        # 定义数据库搜索函数
        databases = {
            'openalex': self.search_openalex,
            'arxiv': self.search_arxiv,
            'semantic_scholar': self.search_semantic_scholar,
            'doaj': self.search_doaj,
            'crossref': self.search_crossref
        }

        for db_name, search_func in databases.items():
            try:
                logger.info(f"开始搜索数据库: {db_name}")
                result = search_func(query, max_results_per_db)
                results[db_name] = result
                logger.info(f"数据库 {db_name} 搜索完成，获取 {len(result[0])} 篇文献")
            except Exception as e:
                logger.error(f"搜索数据库 {db_name} 时出错: {e}")
                results[db_name] = ([], query, 0, 0)

        return results

    # 解析函数
    def _parse_openalex_work(self, work: Dict) -> Optional[Dict]:
        """解析OpenAlex工作数据"""
        try:
            # 提取基本信息
            title = work.get('display_name', work.get('title', ''))
            if not title:
                return None

            # 提取作者信息
            authors = []
            authorships = work.get('authorships', [])
            for authorship in authorships[:10]:  # 限制作者数量
                author = authorship.get('author', {})
                author_name = author.get('display_name', '')
                if author_name:
                    authors.append(author_name)

            # 提取期刊信息
            primary_location = work.get('primary_location', {})
            source = primary_location.get('source', {})
            journal = source.get('display_name', '')

            # 提取摘要（OpenAlex使用倒排索引）
            abstract = self._reconstruct_abstract_from_inverted_index(
                work.get('abstract_inverted_index', {})
            )

            # 提取年份
            pub_year = work.get('publication_year')

            # 提取DOI
            doi = None
            if work.get('doi'):
                doi = work.get('doi').replace('https://doi.org/', '')

            # 提取开放获取信息
            is_oa = work.get('open_access', {}).get('is_oa', False)
            oa_url = work.get('open_access', {}).get('oa_url', '')

            return {
                'title': title,
                'authors': authors,
                'abstract': abstract or '',
                'journal': journal,
                'pub_year': pub_year,
                'doi': doi,
                'url': f"https://openalex.org/{work.get('id', '').split('/')[-1]}" if work.get('id') else '',
                'database': 'OpenAlex',
                'is_open_access': is_oa,
                'open_access_url': oa_url,
                'citation_count': work.get('cited_by_count', 0),
                'type': work.get('type', ''),
                'concepts': [concept.get('display_name', '') for concept in work.get('concepts', [])[:5]]
            }

        except Exception as e:
            logger.error(f"解析OpenAlex工作数据时出错: {e}")
            return None

    def _parse_arxiv_entry(self, entry, namespaces: Dict) -> Optional[Dict]:
        """解析arXiv条目数据"""
        try:
            # 提取标题
            title_elem = entry.find('atom:title', namespaces)
            title = title_elem.text.strip() if title_elem is not None else ''
            if not title:
                return None

            # 提取作者
            authors = []
            author_elems = entry.findall('atom:author', namespaces)
            for author_elem in author_elems:
                name_elem = author_elem.find('atom:name', namespaces)
                if name_elem is not None:
                    authors.append(name_elem.text.strip())

            # 提取摘要
            summary_elem = entry.find('atom:summary', namespaces)
            abstract = summary_elem.text.strip() if summary_elem is not None else ''

            # 提取发布日期
            published_elem = entry.find('atom:published', namespaces)
            pub_date = published_elem.text if published_elem is not None else ''
            pub_year = None
            if pub_date:
                try:
                    pub_year = int(pub_date[:4])
                except:
                    pass

            # 提取arXiv ID和URL
            id_elem = entry.find('atom:id', namespaces)
            arxiv_url = id_elem.text if id_elem is not None else ''
            arxiv_id = arxiv_url.split('/')[-1] if arxiv_url else ''

            # 提取分类
            categories = []
            category_elems = entry.findall('atom:category', namespaces)
            for cat_elem in category_elems:
                term = cat_elem.get('term', '')
                if term:
                    categories.append(term)

            return {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'journal': 'arXiv',
                'pub_year': pub_year,
                'doi': None,
                'url': arxiv_url,
                'database': 'arXiv',
                'arxiv_id': arxiv_id,
                'categories': categories,
                'is_open_access': True,  # arXiv都是开放获取
                'type': 'preprint'
            }

        except Exception as e:
            logger.error(f"解析arXiv条目数据时出错: {e}")
            return None

    def _parse_semantic_scholar_paper(self, paper_data: Dict) -> Optional[Dict]:
        """解析Semantic Scholar论文数据"""
        try:
            title = paper_data.get('title', '')
            if not title:
                return None

            # 提取作者
            authors = []
            author_list = paper_data.get('authors', [])
            for author in author_list:
                author_name = author.get('name', '')
                if author_name:
                    authors.append(author_name)

            # 提取摘要
            abstract = paper_data.get('abstract', '') or ''

            # 提取期刊信息
            venue = paper_data.get('venue', '') or paper_data.get('publicationVenue', {}).get('name', '')

            # 提取年份
            pub_year = paper_data.get('year')

            # 提取DOI
            external_ids = paper_data.get('externalIds', {})
            doi = external_ids.get('DOI')

            # 提取开放获取信息
            is_oa = paper_data.get('isOpenAccess', False)
            oa_pdf = paper_data.get('openAccessPdf')
            oa_url = oa_pdf.get('url', '') if oa_pdf else ''

            # 提取研究领域
            fields = []
            s2_fields = paper_data.get('s2FieldsOfStudy', [])
            for field in s2_fields:
                field_name = field.get('category', '')
                if field_name:
                    fields.append(field_name)

            return {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'journal': venue,
                'pub_year': pub_year,
                'doi': doi,
                'url': f"https://www.semanticscholar.org/paper/{paper_data.get('paperId', '')}" if paper_data.get('paperId') else '',
                'database': 'Semantic Scholar',
                'is_open_access': is_oa,
                'open_access_url': oa_url,
                'citation_count': paper_data.get('citationCount', 0),
                'influential_citation_count': paper_data.get('influentialCitationCount', 0),
                'fields_of_study': fields,
                'publication_types': paper_data.get('publicationTypes', [])
            }

        except Exception as e:
            logger.error(f"解析Semantic Scholar论文数据时出错: {e}")
            return None

    def _parse_doaj_article(self, article_data: Dict) -> Optional[Dict]:
        """解析DOAJ文章数据"""
        try:
            bibjson = article_data.get('bibjson', {})

            title = bibjson.get('title', '')
            if not title:
                return None

            # 提取作者
            authors = []
            author_list = bibjson.get('author', [])
            for author in author_list:
                author_name = author.get('name', '')
                if author_name:
                    authors.append(author_name)

            # 提取摘要
            abstract = bibjson.get('abstract', '') or ''

            # 提取期刊信息
            journal_info = bibjson.get('journal', {})
            journal = journal_info.get('title', '')

            # 提取年份
            pub_year = None
            pub_date = bibjson.get('year')
            if pub_date:
                try:
                    pub_year = int(pub_date)
                except:
                    pass

            # 提取DOI
            identifiers = bibjson.get('identifier', [])
            doi = None
            for identifier in identifiers:
                if identifier.get('type') == 'doi':
                    doi = identifier.get('id')
                    break

            # 提取URL
            links = bibjson.get('link', [])
            url = ''
            for link in links:
                if link.get('type') == 'fulltext':
                    url = link.get('url', '')
                    break

            # 提取主题分类
            subjects = []
            subject_list = bibjson.get('subject', [])
            for subject in subject_list:
                subject_term = subject.get('term', '')
                if subject_term:
                    subjects.append(subject_term)

            return {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'journal': journal,
                'pub_year': pub_year,
                'doi': doi,
                'url': url,
                'database': 'DOAJ',
                'is_open_access': True,  # DOAJ都是开放获取
                'subjects': subjects,
                'language': bibjson.get('language', [])
            }

        except Exception as e:
            logger.error(f"解析DOAJ文章数据时出错: {e}")
            return None

    def _parse_crossref_work(self, work_data: Dict) -> Optional[Dict]:
        """解析Crossref工作数据"""
        try:
            # 提取标题
            title_list = work_data.get('title', [])
            title = title_list[0] if title_list else ''
            if not title:
                return None

            # 提取作者
            authors = []
            author_list = work_data.get('author', [])
            for author in author_list:
                given = author.get('given', '')
                family = author.get('family', '')
                if given and family:
                    authors.append(f"{given} {family}")
                elif family:
                    authors.append(family)

            # 提取摘要
            abstract = work_data.get('abstract', '') or ''

            # 提取期刊信息
            container_title = work_data.get('container-title', [])
            journal = container_title[0] if container_title else ''

            # 提取年份
            pub_year = None
            published = work_data.get('published-print') or work_data.get('published-online')
            if published and 'date-parts' in published:
                date_parts = published['date-parts'][0]
                if date_parts:
                    pub_year = date_parts[0]

            # 提取DOI
            doi = work_data.get('DOI')

            # 提取URL
            url = work_data.get('URL', '')
            if not url and doi:
                url = f"https://doi.org/{doi}"

            # 提取类型
            work_type = work_data.get('type', '')

            # 提取引用数（如果有）
            citation_count = work_data.get('is-referenced-by-count', 0)

            return {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'journal': journal,
                'pub_year': pub_year,
                'doi': doi,
                'url': url,
                'database': 'Crossref',
                'type': work_type,
                'citation_count': citation_count,
                'publisher': work_data.get('publisher', ''),
                'issn': work_data.get('ISSN', [])
            }

        except Exception as e:
            logger.error(f"解析Crossref工作数据时出错: {e}")
            return None

    def _reconstruct_abstract_from_inverted_index(self, inverted_index: Dict) -> str:
        """从OpenAlex的倒排索引重构摘要"""
        try:
            if not inverted_index:
                return ''

            # 创建位置到词的映射
            position_to_word = {}
            for word, positions in inverted_index.items():
                for pos in positions:
                    position_to_word[pos] = word

            # 按位置排序并重构文本
            sorted_positions = sorted(position_to_word.keys())
            words = [position_to_word[pos] for pos in sorted_positions]

            return ' '.join(words)

        except Exception as e:
            logger.error(f"重构摘要时出错: {e}")
            return ''


# 数据库配置
DATABASE_CONFIGS = {
    'openalex': {
        'name': 'OpenAlex',
        'description': '全学科领域，超过2.5亿篇学术文献',
        'coverage': '全学科',
        'api_limit': 200,
        'free': True
    },
    'arxiv': {
        'name': 'arXiv',
        'description': '物理学、数学、计算机科学、生物学等预印本论文',
        'coverage': '理工科预印本',
        'api_limit': 2000,
        'free': True
    },
    'semantic_scholar': {
        'name': 'Semantic Scholar',
        'description': 'AI驱动的学术搜索，覆盖计算机科学、生物医学等多领域',
        'coverage': '计算机科学、生物医学等',
        'api_limit': 100,
        'free': True
    },
    'doaj': {
        'name': 'DOAJ',
        'description': '开放获取期刊目录，覆盖所有学科的高质量同行评议内容',
        'coverage': '全学科开放获取',
        'api_limit': 100,
        'free': True
    },
    'crossref': {
        'name': 'Crossref',
        'description': '权威的学术元数据和引用信息，覆盖全学科DOI注册的学术内容',
        'coverage': '全学科元数据',
        'api_limit': 1000,
        'free': True
    }
}
