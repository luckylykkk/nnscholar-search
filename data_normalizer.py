"""
多数据库文献数据规范化模块
将不同数据库返回的格式统一为标准格式，适配现有的PubMed逻辑
"""

import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class LiteratureDataNormalizer:
    """文献数据规范化器"""
    
    def __init__(self):
        # 标准字段映射
        self.standard_fields = {
            'title': str,
            'authors': list,
            'abstract': str,
            'journal': str,
            'pub_year': int,
            'doi': str,
            'url': str,
            'database': str,
            'pmid': str,  # PubMed ID (如果有)
            'journal_info': dict,
            'impact_factor': float,
            'jcr_quartile': str,
            'cas_quartile': str,
            'relevance': float,
            'is_open_access': bool,
            'open_access_url': str,
            'citation_count': int,
            'type': str,
            'language': str,
            'keywords': list,
            'mesh_terms': list,
            'publication_date': str
        }
    
    def normalize_papers(self, papers: List[Dict], database: str) -> List[Dict]:
        """
        规范化文献列表
        """
        normalized_papers = []
        
        for paper in papers:
            try:
                normalized_paper = self.normalize_single_paper(paper, database)
                if normalized_paper:
                    normalized_papers.append(normalized_paper)
            except Exception as e:
                logger.error(f"规范化文献时出错: {e}")
                continue
        
        logger.info(f"成功规范化 {len(normalized_papers)} 篇文献 (来源: {database})")
        return normalized_papers
    
    def normalize_single_paper(self, paper: Dict, database: str) -> Optional[Dict]:
        """
        规范化单篇文献数据为标准格式
        """
        try:
            # 创建标准格式的文献对象
            normalized = {
                'title': self._normalize_title(paper.get('title', '')),
                'authors': self._normalize_authors(paper.get('authors', [])),
                'abstract': self._normalize_abstract(paper.get('abstract', '')),
                'journal': self._normalize_journal(paper.get('journal', '')),
                'pub_year': self._normalize_year(paper.get('pub_year')),
                'doi': self._normalize_doi(paper.get('doi', '')),
                'url': self._normalize_url(paper.get('url', '')),
                'database': database,
                'pmid': paper.get('pmid', ''),  # 大多数非PubMed数据库没有PMID
                'journal_info': self._create_journal_info(paper),
                'impact_factor': self._extract_impact_factor(paper),
                'jcr_quartile': self._extract_jcr_quartile(paper),
                'cas_quartile': self._extract_cas_quartile(paper),
                'relevance': paper.get('relevance', 0.0),
                'is_open_access': paper.get('is_open_access', False),
                'open_access_url': paper.get('open_access_url', ''),
                'citation_count': paper.get('citation_count', 0),
                'type': self._normalize_type(paper.get('type', '')),
                'language': self._normalize_language(paper.get('language', '')),
                'keywords': self._extract_keywords(paper),
                'mesh_terms': paper.get('mesh_terms', []),  # 主要来自PubMed
                'publication_date': self._normalize_publication_date(paper)
            }
            
            # 验证必要字段
            if not normalized['title']:
                logger.warning(f"文献缺少标题，跳过: {paper}")
                return None
            
            # 添加数据库特定的额外信息
            normalized.update(self._add_database_specific_fields(paper, database))
            
            return normalized
            
        except Exception as e:
            logger.error(f"规范化单篇文献时出错: {e}")
            return None
    
    def _normalize_title(self, title: Any) -> str:
        """规范化标题"""
        if not title:
            return ''
        
        title_str = str(title).strip()
        # 移除多余的空白字符
        title_str = re.sub(r'\s+', ' ', title_str)
        # 移除末尾的句号
        title_str = title_str.rstrip('.')
        
        return title_str
    
    def _normalize_authors(self, authors: Any) -> List[str]:
        """规范化作者列表"""
        if not authors:
            return []
        
        if isinstance(authors, str):
            # 如果是字符串，尝试分割
            authors = [a.strip() for a in authors.split(',') if a.strip()]
        elif isinstance(authors, list):
            authors = [str(a).strip() for a in authors if str(a).strip()]
        else:
            return []
        
        # 限制作者数量，避免过长
        return authors[:20]
    
    def _normalize_abstract(self, abstract: Any) -> str:
        """规范化摘要"""
        if not abstract:
            return ''
        
        abstract_str = str(abstract).strip()
        # 移除多余的空白字符
        abstract_str = re.sub(r'\s+', ' ', abstract_str)
        # 限制摘要长度
        if len(abstract_str) > 5000:
            abstract_str = abstract_str[:5000] + '...'
        
        return abstract_str
    
    def _normalize_journal(self, journal: Any) -> str:
        """规范化期刊名称"""
        if not journal:
            return ''
        
        journal_str = str(journal).strip()
        # 移除多余的空白字符
        journal_str = re.sub(r'\s+', ' ', journal_str)
        
        return journal_str
    
    def _normalize_year(self, year: Any) -> Optional[int]:
        """规范化发表年份"""
        if not year:
            return None
        
        try:
            if isinstance(year, int):
                return year if 1900 <= year <= datetime.now().year + 2 else None
            elif isinstance(year, str):
                # 尝试从字符串中提取年份
                year_match = re.search(r'(\d{4})', year)
                if year_match:
                    year_int = int(year_match.group(1))
                    return year_int if 1900 <= year_int <= datetime.now().year + 2 else None
        except:
            pass
        
        return None
    
    def _normalize_doi(self, doi: Any) -> str:
        """规范化DOI"""
        if not doi:
            return ''
        
        doi_str = str(doi).strip()
        # 移除DOI前缀
        doi_str = re.sub(r'^(https?://)?(dx\.)?doi\.org/', '', doi_str)
        doi_str = re.sub(r'^doi:', '', doi_str, flags=re.IGNORECASE)
        
        return doi_str
    
    def _normalize_url(self, url: Any) -> str:
        """规范化URL"""
        if not url:
            return ''
        
        url_str = str(url).strip()
        # 验证URL格式
        if not url_str.startswith(('http://', 'https://')):
            return ''
        
        return url_str
    
    def _create_journal_info(self, paper: Dict) -> Dict:
        """创建期刊信息对象"""
        journal_info = {
            'title': paper.get('journal', ''),
            'impact_factor': self._extract_impact_factor(paper),
            'jcr_quartile': self._extract_jcr_quartile(paper),
            'cas_quartile': self._extract_cas_quartile(paper),
            'issn': paper.get('issn', []),
            'publisher': paper.get('publisher', '')
        }
        
        return journal_info
    
    def _extract_impact_factor(self, paper: Dict) -> Optional[float]:
        """提取影响因子"""
        # 大多数开放数据库不提供影响因子信息
        # 这里可以集成外部影响因子数据库
        if 'impact_factor' in paper:
            try:
                return float(paper['impact_factor'])
            except:
                pass
        return None
    
    def _extract_jcr_quartile(self, paper: Dict) -> str:
        """提取JCR分区"""
        # 大多数开放数据库不提供JCR分区信息
        return paper.get('jcr_quartile', '')
    
    def _extract_cas_quartile(self, paper: Dict) -> str:
        """提取中科院分区"""
        # 大多数开放数据库不提供中科院分区信息
        return paper.get('cas_quartile', '')
    
    def _normalize_type(self, doc_type: Any) -> str:
        """规范化文档类型"""
        if not doc_type:
            return ''
        
        type_str = str(doc_type).lower()
        
        # 标准化文档类型
        type_mapping = {
            'journal-article': 'Journal Article',
            'article': 'Journal Article',
            'review': 'Review',
            'review-article': 'Review',
            'preprint': 'Preprint',
            'conference-paper': 'Conference Paper',
            'book-chapter': 'Book Chapter',
            'book': 'Book',
            'thesis': 'Thesis',
            'dissertation': 'Dissertation'
        }
        
        for key, value in type_mapping.items():
            if key in type_str:
                return value
        
        return doc_type.title() if doc_type else ''
    
    def _normalize_language(self, language: Any) -> str:
        """规范化语言"""
        if not language:
            return 'en'  # 默认英语
        
        if isinstance(language, list):
            language = language[0] if language else 'en'
        
        lang_str = str(language).lower()
        
        # 语言代码映射
        lang_mapping = {
            'english': 'en',
            'chinese': 'zh',
            'spanish': 'es',
            'french': 'fr',
            'german': 'de',
            'japanese': 'ja',
            'korean': 'ko',
            'russian': 'ru'
        }
        
        return lang_mapping.get(lang_str, lang_str[:2])
    
    def _extract_keywords(self, paper: Dict) -> List[str]:
        """提取关键词"""
        keywords = []
        
        # 从不同字段提取关键词
        keyword_fields = ['keywords', 'concepts', 'subjects', 'categories', 'fields_of_study']
        
        for field in keyword_fields:
            if field in paper and paper[field]:
                field_keywords = paper[field]
                if isinstance(field_keywords, list):
                    keywords.extend([str(k).strip() for k in field_keywords if str(k).strip()])
                elif isinstance(field_keywords, str):
                    keywords.extend([k.strip() for k in field_keywords.split(',') if k.strip()])
        
        # 去重并限制数量
        keywords = list(set(keywords))[:10]
        
        return keywords
    
    def _normalize_publication_date(self, paper: Dict) -> str:
        """规范化发表日期"""
        # 尝试从不同字段获取日期
        date_fields = ['publication_date', 'pub_date', 'published', 'date']
        
        for field in date_fields:
            if field in paper and paper[field]:
                date_str = str(paper[field])
                # 尝试标准化日期格式
                try:
                    # 简单的日期格式处理
                    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                        return date_str[:10]  # YYYY-MM-DD
                    elif re.match(r'\d{4}', date_str):
                        return date_str[:4] + '-01-01'  # 只有年份
                except:
                    pass
        
        # 如果有年份，使用年份
        if paper.get('pub_year'):
            return f"{paper['pub_year']}-01-01"
        
        return ''
    
    def _add_database_specific_fields(self, paper: Dict, database: str) -> Dict:
        """添加数据库特定的字段"""
        specific_fields = {}
        
        if database == 'OpenAlex':
            specific_fields.update({
                'openalex_id': paper.get('id', ''),
                'concepts': paper.get('concepts', []),
                'sustainable_development_goals': paper.get('sustainable_development_goals', [])
            })
        elif database == 'arXiv':
            specific_fields.update({
                'arxiv_id': paper.get('arxiv_id', ''),
                'categories': paper.get('categories', [])
            })
        elif database == 'Semantic Scholar':
            specific_fields.update({
                'semantic_scholar_id': paper.get('paperId', ''),
                'influential_citation_count': paper.get('influential_citation_count', 0),
                'fields_of_study': paper.get('fields_of_study', []),
                'publication_types': paper.get('publication_types', [])
            })
        elif database == 'DOAJ':
            specific_fields.update({
                'subjects': paper.get('subjects', [])
            })
        elif database == 'Crossref':
            specific_fields.update({
                'crossref_type': paper.get('type', ''),
                'publisher': paper.get('publisher', ''),
                'issn': paper.get('issn', [])
            })
        
        return specific_fields
    
    def merge_duplicate_papers(self, papers: List[Dict]) -> List[Dict]:
        """
        合并重复的文献（基于DOI或标题相似性）
        """
        unique_papers = []
        seen_dois = set()
        seen_titles = set()
        
        for paper in papers:
            # 检查DOI重复
            doi = paper.get('doi', '')
            if doi and doi in seen_dois:
                continue
            
            # 检查标题重复（简单的字符串匹配）
            title = paper.get('title', '').lower().strip()
            if title and title in seen_titles:
                continue
            
            unique_papers.append(paper)
            
            if doi:
                seen_dois.add(doi)
            if title:
                seen_titles.add(title)
        
        logger.info(f"去重后保留 {len(unique_papers)} 篇文献（原始: {len(papers)} 篇）")
        return unique_papers
