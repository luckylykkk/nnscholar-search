"""PubMed API service for literature search."""

import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from bs4 import BeautifulSoup
import re

from config.api_config import api_config
from models.paper import Paper, PaperDetail
from utils.text_processing import preprocess_text, extract_keywords
from utils.cache_utils import cache_result, RateLimiter
from services.journal_service import journal_service

logger = logging.getLogger(__name__)


class PubMedService:
    """Service for interacting with PubMed API."""
    
    def __init__(self):
        self.base_url = api_config.PUBMED_API_URL
        self.rate_limiter = RateLimiter(
            max_requests=api_config.PUBMED_RPS * 60,  # Convert to requests per minute
            window_seconds=60
        )
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'User-Agent': 'NNScholar/1.0 (https://github.com/nnscholar)',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
    
    def search_papers(self, query: str, max_results: int = 100, 
                     retstart: int = 0, sort: str = 'relevance') -> Tuple[List[str], int]:
        """Search PubMed for papers and return PMIDs.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            retstart: Starting position for results
            sort: Sort order ('relevance', 'date', 'author')
        
        Returns:
            Tuple of (list of PMIDs, total count)
        """
        try:
            # Rate limiting
            if not self.rate_limiter.is_allowed('search'):
                logger.warning("Rate limit exceeded for PubMed search")
                raise Exception("Rate limit exceeded")
            
            # Prepare search parameters
            search_url = f"{self.base_url}/esearch.fcgi"
            
            params = {
                'db': 'pubmed',
                'term': query,
                'retmax': min(max_results, api_config.PUBMED_MAX_RESULTS),
                'retstart': retstart,
                'retmode': 'xml',
                'sort': sort,
                'tool': 'NNScholar',
                'email': api_config.PUBMED_EMAIL or 'contact@nnscholar.com'
            }
            
            if api_config.PUBMED_API_KEY:
                params['api_key'] = api_config.PUBMED_API_KEY
            
            logger.info(f"Searching PubMed: {query[:100]}... (max_results={max_results})")
            
            # Make request with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(
                        search_url, 
                        params=params, 
                        timeout=api_config.REQUEST_TIMEOUT
                    )
                    response.raise_for_status()
                    break  # Success, break out of retry loop
                except requests.exceptions.ConnectionError as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                        logger.warning(f"PubMed connection failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"PubMed connection failed after {max_retries} attempts: {e}")
                        raise
                except requests.exceptions.Timeout as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"PubMed request timeout (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"PubMed request timeout after {max_retries} attempts: {e}")
                        raise
            
            # Parse XML response
            root = ET.fromstring(response.content)
            
            # Extract PMIDs
            pmids = []
            id_list = root.find('.//IdList')
            if id_list is not None:
                for id_elem in id_list.findall('Id'):
                    pmids.append(id_elem.text)
            
            # Get total count
            count_elem = root.find('.//Count')
            total_count = int(count_elem.text) if count_elem is not None else 0
            
            logger.info(f"Found {len(pmids)} PMIDs (total: {total_count})")
            
            return pmids, total_count
            
        except requests.RequestException as e:
            logger.error(f"PubMed search request failed: {e}")
            raise Exception(f"PubMed search failed: {str(e)}")
        except ET.ParseError as e:
            logger.error(f"Failed to parse PubMed response: {e}")
            raise Exception(f"Invalid response from PubMed: {str(e)}")
        except Exception as e:
            logger.error(f"PubMed search error: {e}")
            raise
    
    @cache_result(ttl=3600)  # Cache for 1 hour
    def fetch_paper_details(self, pmids: List[str]) -> List[PaperDetail]:
        """Fetch detailed information for papers by PMID.
        
        Args:
            pmids: List of PubMed IDs
        
        Returns:
            List of PaperDetail objects
        """
        if not pmids:
            return []
        
        try:
            # Rate limiting
            if not self.rate_limiter.is_allowed('fetch'):
                logger.warning("Rate limit exceeded for PubMed fetch")
                time.sleep(1)
            
            # Prepare fetch parameters
            fetch_url = f"{self.base_url}/efetch.fcgi"
            
            params = {
                'db': 'pubmed',
                'id': ','.join(pmids),
                'rettype': 'abstract',
                'retmode': 'xml',
                'tool': 'NNScholar',
                'email': api_config.PUBMED_EMAIL or 'contact@nnscholar.com'
            }
            
            if api_config.PUBMED_API_KEY:
                params['api_key'] = api_config.PUBMED_API_KEY
            
            logger.info(f"Fetching details for {len(pmids)} papers")
            
            # Make request with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(
                        fetch_url, 
                        params=params, 
                        timeout=api_config.REQUEST_TIMEOUT
                    )
                    response.raise_for_status()
                    break  # Success, break out of retry loop
                except requests.exceptions.ConnectionError as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                        logger.warning(f"PubMed fetch connection failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"PubMed fetch connection failed after {max_retries} attempts: {e}")
                        raise
                except requests.exceptions.Timeout as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"PubMed fetch timeout (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"PubMed fetch timeout after {max_retries} attempts: {e}")
                        raise
            
            # Parse XML response
            papers = self._parse_pubmed_xml(response.content)
            
            logger.info(f"Successfully parsed {len(papers)} papers")
            
            return papers
            
        except requests.RequestException as e:
            logger.error(f"PubMed fetch request failed: {e}")
            raise Exception(f"Failed to fetch paper details: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching paper details: {e}")
            raise
    
    def fetch_paper_details_batch(self, pmids: List[str], 
                                 batch_size: int = 200, 
                                 max_workers: int = 3,
                                 progress_callback=None) -> List[PaperDetail]:
        """Fetch paper details in batches with parallel processing.
        
        Args:
            pmids: List of PubMed IDs
            batch_size: Size of each batch
            max_workers: Maximum number of concurrent workers
            progress_callback: Optional callback function for progress updates
        
        Returns:
            List of PaperDetail objects
        """
        if not pmids:
            return []
        
        # Split into batches
        batches = [pmids[i:i + batch_size] for i in range(0, len(pmids), batch_size)]
        
        all_papers = []
        completed_batches = 0
        total_batches = len(batches)
        
        # Process batches
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batches
            future_to_batch = {
                executor.submit(self.fetch_paper_details, batch): batch 
                for batch in batches
            }
            
            # Collect results
            for future in as_completed(future_to_batch):
                batch = future_to_batch[future]
                try:
                    papers = future.result()
                    all_papers.extend(papers)
                    completed_batches += 1
                    
                    logger.debug(f"Completed batch {completed_batches}/{total_batches} with {len(papers)} papers")
                    
                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(
                            stage='fetching_details_progress',
                            message=f'Fetching details... ({completed_batches}/{total_batches} batches completed)',
                            completed_batches=completed_batches,
                            total_batches=total_batches,
                            papers_fetched=len(all_papers)
                        )
                        
                except Exception as e:
                    logger.error(f"Batch processing failed: {e}")
                    # Continue with other batches
        
        return all_papers
    
    def _parse_pubmed_xml(self, xml_content: bytes) -> List[PaperDetail]:
        """Parse PubMed XML response into PaperDetail objects.
        
        Args:
            xml_content: Raw XML content from PubMed
        
        Returns:
            List of PaperDetail objects
        """
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            
            for article in root.findall('.//PubmedArticle'):
                try:
                    paper = self._parse_single_article(article)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    logger.warning(f"Failed to parse article: {e}")
                    continue
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse XML: {e}")
            raise
        
        return papers
    
    def _parse_single_article(self, article_elem) -> Optional[PaperDetail]:
        """Parse a single PubMed article element.
        
        Args:
            article_elem: XML element for the article
        
        Returns:
            PaperDetail object or None if parsing fails
        """
        try:
            # Extract PMID
            pmid_elem = article_elem.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else ''
            
            if not pmid:
                return None
            
            # Extract basic information
            article = article_elem.find('.//Article')
            if article is None:
                return None
            
            # Title
            title_elem = article.find('.//ArticleTitle')
            title = self._extract_text(title_elem) if title_elem is not None else ''
            
            # Abstract
            abstract_parts = []
            abstract_elem = article.find('.//Abstract')
            if abstract_elem is not None:
                for text_elem in abstract_elem.findall('.//AbstractText'):
                    text = self._extract_text(text_elem)
                    if text:
                        # Add label if present
                        label = text_elem.get('Label')
                        if label:
                            abstract_parts.append(f"{label}: {text}")
                        else:
                            abstract_parts.append(text)
            
            abstract = ' '.join(abstract_parts)
            
            # Authors
            authors = []
            author_list = article.find('.//AuthorList')
            if author_list is not None:
                for author in author_list.findall('.//Author'):
                    last_name = self._get_element_text(author, './/LastName')
                    first_name = self._get_element_text(author, './/ForeName')
                    
                    if last_name:
                        if first_name:
                            authors.append(f"{last_name}, {first_name}")
                        else:
                            authors.append(last_name)
            
            # Journal - 提取期刊标题和ISSN
            journal_elem = article.find('.//Journal/Title')
            if journal_elem is None:
                journal_elem = article.find('.//Journal/ISOAbbreviation')
            journal = self._extract_text(journal_elem) if journal_elem is not None else ''
            
            # 提取ISSN
            issn = ''
            journal_container = article.find('.//Journal')
            if journal_container is not None:
                issn_elem = journal_container.find('.//ISSN')
                if issn_elem is not None:
                    issn = self._extract_text(issn_elem)
                    logger.debug(f"找到ISSN: {issn} for journal: {journal}")
            
            # 获取期刊指标
            journal_info = {}
            if issn:
                logger.debug(f"开始获取期刊 {issn} 的指标信息")
                metrics = journal_service.get_journal_metrics(issn)
                if metrics:
                    logger.debug(f"成功获取期刊指标: {metrics}")
                    journal_info = {
                        'title': metrics.title or journal,  # 如果数据库中有期刊名，优先使用
                        'impact_factor': metrics.impact_factor,
                        'jcr_quartile': metrics.jcr_quartile,
                        'cas_quartile': metrics.cas_quartile,
                        'issn': metrics.issn or issn,
                        'eissn': metrics.eissn
                    }
                else:
                    logger.warning(f"未能获取期刊 {issn} 的指标信息，尝试通过期刊名称匹配")
                    # 如果通过ISSN找不到，尝试通过期刊名称查找
                    if journal:
                        metrics = journal_service.get_journal_metrics_by_name(journal)
                        if metrics:
                            logger.debug(f"通过期刊名称找到指标: {metrics}")
                            journal_info = {
                                'title': metrics.title,
                                'impact_factor': metrics.impact_factor,
                                'jcr_quartile': metrics.jcr_quartile,
                                'cas_quartile': metrics.cas_quartile,
                                'issn': metrics.issn,
                                'eissn': metrics.eissn
                            }
            elif journal:
                # 如果没有ISSN，尝试通过期刊名称查找
                logger.debug(f"无ISSN，尝试通过期刊名称获取指标: {journal}")
                metrics = journal_service.get_journal_metrics_by_name(journal)
                if metrics:
                    logger.debug(f"通过期刊名称找到指标: {metrics}")
                    journal_info = {
                        'title': metrics.title,
                        'impact_factor': metrics.impact_factor,
                        'jcr_quartile': metrics.jcr_quartile,
                        'cas_quartile': metrics.cas_quartile,
                        'issn': metrics.issn,
                        'eissn': metrics.eissn
                    }
            
            # 如果没有找到期刊指标，使用默认值
            if not journal_info:
                journal_info = {
                    'title': journal,
                    'impact_factor': 'N/A',
                    'jcr_quartile': 'N/A',
                    'cas_quartile': 'N/A',
                    'issn': issn,
                    'eissn': ''
                }
            
            # Publication date and year
            pub_date = self._extract_publication_date(article)
            pub_year = self._extract_publication_year(article)
            
            # DOI
            doi = ''
            for id_elem in article.findall('.//ArticleId'):
                if id_elem.get('IdType') == 'doi':
                    doi = id_elem.text
                    break
            
            # Keywords - 按照原版本的多层后备机制
            keywords = []
            
            # 首先尝试提取NOTNLM owner的关键词
            medline_citation = article_elem.find('.//MedlineCitation')
            if medline_citation is not None:
                keyword_list = medline_citation.find('.//KeywordList[@Owner="NOTNLM"]')
                if keyword_list is not None:
                    for keyword in keyword_list.findall('.//Keyword'):
                        kw_text = self._extract_text(keyword)
                        if kw_text:
                            keywords.append(kw_text.strip())
            
            # 如果没有找到NOTNLM关键词，尝试其他KeywordList
            if not keywords:
                keyword_list = article_elem.find('.//KeywordList')
                if keyword_list is not None:
                    for keyword in keyword_list.findall('.//Keyword'):
                        kw_text = self._extract_text(keyword)
                        if kw_text:
                            keywords.append(kw_text.strip())
            
            # MeSH terms
            mesh_terms = []
            mesh_list = article_elem.find('.//MeshHeadingList')
            if mesh_list is not None:
                for mesh_heading in mesh_list.findall('.//MeshHeading'):
                    descriptor = mesh_heading.find('.//DescriptorName')
                    if descriptor is not None:
                        mesh_terms.append(self._extract_text(descriptor))
            
            # 如果没有关键词，使用MeSH术语作为后备（按照原版本逻辑）
            if not keywords and mesh_terms:
                keywords = mesh_terms.copy()
            
            # Publication types - 原版本中实际没有提取此字段，保持一致
            pub_types = []
            
            # Create PaperDetail object
            paper = PaperDetail(
                pmid=pmid,
                title=title,
                authors=authors,
                journal=journal_info.get('title', journal),  # 使用期刊数据库中的标准名称
                pub_date=pub_date,
                pub_year=pub_year,
                abstract=abstract,
                doi=doi,
                keywords=keywords,
                mesh_terms=mesh_terms,
                publication_types=pub_types,
                journal_info=journal_info  # 添加期刊信息
            )
            
            return paper
            
        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            return None
    
    def _extract_text(self, element) -> str:
        """Extract text from XML element, handling HTML entities.
        
        Args:
            element: XML element
        
        Returns:
            Cleaned text
        """
        if element is None:
            return ''
        
        # Get all text content
        text = ''.join(element.itertext())
        
        # Clean up
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        
        return text
    
    def _get_element_text(self, parent, xpath: str) -> str:
        """Get text from child element.
        
        Args:
            parent: Parent XML element
            xpath: XPath to child element
        
        Returns:
            Text content or empty string
        """
        elem = parent.find(xpath)
        return self._extract_text(elem) if elem is not None else ''
    
    def _extract_publication_date(self, article) -> str:
        """Extract publication date from article.
        
        Args:
            article: Article XML element
        
        Returns:
            Publication date string
        """
        # Try different date fields
        date_paths = [
            './/Journal/JournalIssue/PubDate',
            './/ArticleDate',
            './/PubDate'
        ]
        
        for path in date_paths:
            date_elem = article.find(path)
            if date_elem is not None:
                year = self._get_element_text(date_elem, './/Year')
                month = self._get_element_text(date_elem, './/Month')
                day = self._get_element_text(date_elem, './/Day')
                
                if year:
                    date_parts = [year]
                    if month:
                        date_parts.append(month)
                    if day:
                        date_parts.append(day)
                    return '-'.join(date_parts)
        
        return ''
    
    def _extract_publication_year(self, article) -> Optional[int]:
        """Extract publication year from article.
        
        Args:
            article: XML article element
        
        Returns:
            Publication year as integer or None
        """
        import re
        
        # Try different date fields
        date_paths = [
            './/Journal/JournalIssue/PubDate',
            './/ArticleDate',
            './/PubDate'
        ]
        
        for path in date_paths:
            date_elem = article.find(path)
            if date_elem is not None:
                # First try to get Year element directly
                year = self._get_element_text(date_elem, './/Year')
                if year:
                    try:
                        return int(year)
                    except ValueError:
                        continue
                
                # Try to extract from MedlineDate
                medline_date = self._get_element_text(date_elem, './/MedlineDate')
                if medline_date:
                    try:
                        # Extract first 4-digit number as year
                        year_match = re.search(r'\b\d{4}\b', medline_date)
                        if year_match:
                            return int(year_match.group())
                    except ValueError:
                        continue
        
        return None
    
    def generate_search_strategy(self, topic: str, filters: Dict[str, Any] = None) -> str:
        """Generate optimized PubMed search strategy.
        
        Args:
            topic: Research topic
            filters: Additional filters (date range, journal, etc.)
        
        Returns:
            Optimized search query string
        """
        try:
            # Clean and prepare topic
            clean_topic = preprocess_text(topic)
            
            # Extract key terms
            keywords = extract_keywords(clean_topic, max_keywords=10)
            
            # Build search components
            search_parts = []
            
            # Main topic
            if len(keywords) > 0:
                # Use most important keywords
                main_terms = keywords[:5]
                search_parts.append(f"({' OR '.join(main_terms)})")
            else:
                # Fallback to simple topic
                search_parts.append(f'"{clean_topic}"')
            
            # Add filters if provided
            if filters:
                # Date range
                if filters.get('start_year') or filters.get('end_year'):
                    start_year = filters.get('start_year', '1900')
                    end_year = filters.get('end_year', '2024')
                    search_parts.append(f'("{start_year}"[Date - Publication] : "{end_year}"[Date - Publication])')
                
                # Journal
                if filters.get('journal'):
                    journal = filters['journal']
                    search_parts.append(f'("{journal}"[Journal])')
                
                # Publication type
                if filters.get('publication_types'):
                    pub_types = filters['publication_types']
                    if isinstance(pub_types, list):
                        type_query = ' OR '.join([f'"{pt}"[Publication Type]' for pt in pub_types])
                        search_parts.append(f'({type_query})')
                
                # Language
                if filters.get('languages'):
                    languages = filters['languages']
                    if isinstance(languages, list):
                        lang_query = ' OR '.join([f'"{lang}"[Language]' for lang in languages])
                        search_parts.append(f'({lang_query})')
            
            # Combine with AND
            final_query = ' AND '.join(search_parts)
            
            logger.info(f"Generated search strategy: {final_query}")
            
            return final_query
            
        except Exception as e:
            logger.error(f"Error generating search strategy: {e}")
            return topic  # Fallback to simple topic
    
    def validate_query(self, query: str) -> Tuple[bool, str]:
        """Validate PubMed search query.
        
        Args:
            query: Search query to validate
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Query cannot be empty"
        
        # Check length
        if len(query) > 5000:
            return False, "Query is too long (max 5000 characters)"
        
        # Check for balanced parentheses
        if query.count('(') != query.count(')'):
            return False, "Unbalanced parentheses in query"
        
        # Check for balanced quotes
        if query.count('"') % 2 != 0:
            return False, "Unbalanced quotes in query"
        
        return True, ""
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get service status and statistics.
        
        Returns:
            Service status information
        """
        return {
            'service': 'PubMed',
            'base_url': self.base_url,
            'rate_limit_remaining': self.rate_limiter.get_remaining('search'),
            'api_key_configured': bool(api_config.PUBMED_API_KEY),
            'email_configured': bool(api_config.PUBMED_EMAIL)
        }


# Global service instance
pubmed_service = PubMedService()