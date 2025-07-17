"""Text processing utilities."""

import re
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from typing import List, Dict, Any, Optional
import hashlib
import logging

logger = logging.getLogger(__name__)

# Initialize NLTK components
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
    nltk.data.find('corpora/wordnet')
    # Global instances
    lemmatizer = WordNetLemmatizer()
    stop_words = set(stopwords.words('english'))
except LookupError:
    logger.warning("NLTK data not available, using fallback text processing")
    # Fallback instances
    lemmatizer = None
    stop_words = set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'])


def preprocess_text(text: str, max_length: int = 10000) -> str:
    """Preprocess text for analysis.
    
    Args:
        text: Input text to process
        max_length: Maximum text length to process
    
    Returns:
        Cleaned and preprocessed text
    """
    if not text:
        return ""
    
    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length]
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove special characters but keep basic punctuation
    text = re.sub(r'[^\w\s.,;:!?()-]', ' ', text)
    
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text


def split_paragraph_to_sentences(paragraph: str, max_sentences: int = 20) -> List[str]:
    """Split paragraph into sentences.
    
    Args:
        paragraph: Input paragraph
        max_sentences: Maximum number of sentences to return
    
    Returns:
        List of sentences
    """
    if not paragraph:
        return []
    
    try:
        # Preprocess text
        clean_text = preprocess_text(paragraph)
        
        # Split into sentences
        sentences = sent_tokenize(clean_text)
        
        # Filter out very short sentences
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        
        # Limit number of sentences
        return sentences[:max_sentences]
        
    except Exception as e:
        logger.error(f"Error splitting paragraph: {e}")
        return [paragraph]  # Return original as fallback


def extract_keywords(text: str, max_keywords: int = 20) -> List[str]:
    """Extract keywords from text using TF-IDF.
    
    Args:
        text: Input text
        max_keywords: Maximum number of keywords
    
    Returns:
        List of keywords
    """
    if not text:
        return []
    
    try:
        # Preprocess
        clean_text = preprocess_text(text)
        
        # Tokenize and filter
        words = word_tokenize(clean_text.lower())
        if lemmatizer:
            words = [lemmatizer.lemmatize(word) for word in words
                    if word.isalpha() and word not in stop_words and len(word) > 2]
        else:
            words = [word for word in words
                    if word.isalpha() and word not in stop_words and len(word) > 2]
        
        if not words:
            return []
        
        # Use TF-IDF for keyword extraction
        vectorizer = TfidfVectorizer(
            max_features=max_keywords,
            ngram_range=(1, 2),
            stop_words='english'
        )
        
        try:
            tfidf_matrix = vectorizer.fit_transform([' '.join(words)])
            feature_names = vectorizer.get_feature_names_out()
            scores = tfidf_matrix.toarray()[0]
            
            # Get top keywords
            keyword_scores = list(zip(feature_names, scores))
            keyword_scores.sort(key=lambda x: x[1], reverse=True)
            
            return [kw for kw, score in keyword_scores if score > 0]
            
        except ValueError:
            # Fallback: return most frequent words
            from collections import Counter
            word_freq = Counter(words)
            return [word for word, freq in word_freq.most_common(max_keywords)]
            
    except Exception as e:
        logger.error(f"Error extracting keywords: {e}")
        return []


def create_text_features(texts: List[str], max_features: int = 1000) -> np.ndarray:
    """Create TF-IDF features from texts.
    
    Args:
        texts: List of input texts
        max_features: Maximum number of features
    
    Returns:
        TF-IDF feature matrix
    """
    if not texts:
        return np.array([])
    
    try:
        # Preprocess all texts
        clean_texts = [preprocess_text(text) for text in texts]
        clean_texts = [text for text in clean_texts if text]  # Remove empty
        
        if not clean_texts:
            return np.array([])
        
        # Create TF-IDF features
        vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=(1, 2),
            stop_words='english',
            min_df=1,
            max_df=0.95
        )
        
        tfidf_matrix = vectorizer.fit_transform(clean_texts)
        return tfidf_matrix.toarray()
        
    except Exception as e:
        logger.error(f"Error creating text features: {e}")
        return np.array([])


def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two texts using TF-IDF.
    
    Args:
        text1: First text
        text2: Second text
    
    Returns:
        Similarity score (0-1)
    """
    try:
        if not text1 or not text2:
            return 0.0
        
        # Create features
        features = create_text_features([text1, text2])
        
        if features.shape[0] < 2:
            return 0.0
        
        # Calculate cosine similarity
        from sklearn.metrics.pairwise import cosine_similarity
        similarity = cosine_similarity([features[0]], [features[1]])[0][0]
        
        return max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
        
    except Exception as e:
        logger.error(f"Error calculating text similarity: {e}")
        return 0.0


def get_text_hash(text: str) -> str:
    """Generate hash for text (useful for caching).
    
    Args:
        text: Input text
    
    Returns:
        MD5 hash of text
    """
    if not text:
        return ""
    
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def clean_journal_name(journal_name: str) -> str:
    """Clean and normalize journal name.
    
    Args:
        journal_name: Raw journal name
    
    Returns:
        Cleaned journal name
    """
    if not journal_name:
        return ""
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', journal_name.strip())
    
    # Remove common prefixes/suffixes
    name = re.sub(r'^(the\s+)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(journal|magazine|review)$', '', name, flags=re.IGNORECASE)
    
    return name.strip()


def extract_author_names(author_string: str) -> List[str]:
    """Extract individual author names from author string.
    
    Args:
        author_string: Raw author string
    
    Returns:
        List of individual author names
    """
    if not author_string:
        return []
    
    # Split by common separators
    authors = re.split(r'[,;]|\sand\s', author_string)
    
    # Clean each author name
    cleaned_authors = []
    for author in authors:
        author = author.strip()
        if author and len(author) > 2:
            # Remove common suffixes
            author = re.sub(r'\s+(jr|sr|phd|md|dr)\.?$', '', author, flags=re.IGNORECASE)
            cleaned_authors.append(author.strip())
    
    return cleaned_authors


def format_citation(title: str, authors: List[str], journal: str, year: str, 
                   pmid: str = None, doi: str = None) -> str:
    """Format citation in standard format.
    
    Args:
        title: Paper title
        authors: List of authors
        journal: Journal name
        year: Publication year
        pmid: PubMed ID (optional)
        doi: DOI (optional)
    
    Returns:
        Formatted citation string
    """
    try:
        citation_parts = []
        
        # Authors
        if authors:
            if len(authors) <= 3:
                author_string = ', '.join(authors)
            else:
                author_string = f"{authors[0]} et al."
            citation_parts.append(author_string)
        
        # Title
        if title:
            citation_parts.append(f"\"{title}\"")
        
        # Journal and year
        if journal:
            journal_part = journal
            if year:
                journal_part += f" ({year})"
            citation_parts.append(journal_part)
        
        # Identifiers
        identifiers = []
        if pmid:
            identifiers.append(f"PMID: {pmid}")
        if doi:
            identifiers.append(f"DOI: {doi}")
        
        if identifiers:
            citation_parts.append("; ".join(identifiers))
        
        return ". ".join(citation_parts) + "."
        
    except Exception as e:
        logger.error(f"Error formatting citation: {e}")
        return f"{title} - {journal} ({year})" if all([title, journal, year]) else ""


def split_paragraph_to_sentences(paragraph: str) -> List[str]:
    """使用 NLTK 将段落分解为句子 - 兼容原版本API"""
    try:
        # 检查是否包含中文字符
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in paragraph)
        
        if has_chinese:
            # 对于中文文本，使用标点符号分句
            sentences = []
            current_sentence = ""
            # 中文分句标点符号
            end_marks = {'。', '！', '？', '；', '.', '!', '?', ';'}
            
            for char in paragraph:
                current_sentence += char
                if char in end_marks:
                    sentence = current_sentence.strip()
                    if sentence:
                        # 确保句子以标点符号结尾
                        if not any(sentence.endswith(mark) for mark in end_marks):
                            sentence += '。'
                        sentences.append(sentence)
                    current_sentence = ""
            
            # 处理最后一个可能没有结束标点的句子
            if current_sentence.strip():
                sentence = current_sentence.strip()
                # 确保最后一个句子也以标点符号结尾
                if not any(sentence.endswith(mark) for mark in end_marks):
                    sentence += '。'
                sentences.append(sentence)
        else:
            # 对于英文文本，使用NLTK的分句功能
            try:
                sentences = nltk.sent_tokenize(paragraph)
            except LookupError:
                # 如果NLTK数据未下载，使用简单的分句规则
                sentences = [s.strip() for s in re.split('[.!?]+', paragraph) if s.strip()]
        
        # 过滤空句子并去重
        return list(dict.fromkeys(s for s in sentences if s.strip()))
        
    except Exception as e:
        logger.error(f"分句过程中出现错误: {str(e)}")
        # 发生错误时使用最简单的分句方式
        sentences = [s.strip() for s in re.split('[.。!！?？;；]+', paragraph) if s.strip()]
        # 确保每个句子都以标点符号结尾
        return [s if any(s.endswith(mark) for mark in {'。', '！', '？', '；', '.', '!', '?', ';'}) else s + '。' for s in sentences]


def process_sentence_sync(session_id: str, sentence: str, filters: dict = None) -> dict:
    """同步处理单个句子的检索
    
    Args:
        session_id (str): 用户会话ID
        sentence (str): 句子文本
        filters (dict, optional): 筛选条件
        
    Returns:
        dict: 检索结果
    """
    try:
        from services.pubmed_service import pubmed_service
        from services.deepseek_service import deepseek_service
        from models.journal import journal_db
        
        logger.info(f"开始处理句子: {sentence[:50]}...")
        
        # 生成检索策略
        try:
            search_strategy = deepseek_service.generate_search_strategy(sentence, 'comprehensive')
            if not search_strategy:
                # 使用基本策略作为后备
                search_strategy = f'({sentence}[Title/Abstract] OR {sentence}[All Fields])'
        except Exception as e:
            logger.warning(f"AI策略生成失败，使用基本策略: {e}")
            search_strategy = f'({sentence}[Title/Abstract] OR {sentence}[All Fields])'
        
        # 执行检索
        pmids, total_count = pubmed_service.search_papers(search_strategy, max_results=50)
        
        if not pmids:
            return {
                'sentence': sentence,
                'search_strategy': search_strategy,
                'papers': [],
                'total_count': 0,
                'filtered_count': 0
            }
        
        # 获取文献详情
        papers = pubmed_service.fetch_paper_details_batch(pmids)
        
        # 转换为dict格式并添加期刊指标
        paper_dicts = []
        for paper in papers:
            if paper:
                paper_dict = paper.to_dict()
                
                # 添加期刊指标
                journal_name = paper_dict.get('journal', '')
                if journal_name:
                    metrics = journal_db.get_journal_metrics(journal_name)
                    if metrics:
                        paper_dict['impact_factor'] = metrics.impact_factor
                        paper_dict['jcr_quartile'] = metrics.jcr_quartile
                        paper_dict['cas_quartile'] = metrics.cas_quartile
                
                paper_dicts.append(paper_dict)
        
        logger.info(f"句子处理完成: {sentence[:50]}... -> {len(paper_dicts)}篇文献")
        
        return {
            'sentence': sentence,
            'search_strategy': search_strategy,
            'papers': paper_dicts,
            'total_count': total_count,
            'filtered_count': len(paper_dicts)
        }
        
    except Exception as e:
        logger.error(f"处理句子出错: {str(e)}")
        return {
            'sentence': sentence,
            'search_strategy': sentence,
            'papers': [],
            'total_count': 0,
            'filtered_count': 0,
            'error': str(e)
        }


def process_paragraph_threaded(session_id: str, sentences: List[str], filters: dict = None) -> List[dict]:
    """使用线程池处理段落中的所有句子
    
    Args:
        session_id (str): 用户会话ID
        sentences (List[str]): 句子列表
        filters (dict, optional): 筛选条件
        
    Returns:
        List[dict]: 检索结果列表
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    try:
        results = []
        max_workers = min(len(sentences), 5)  # 限制并发数避免过载
        
        logger.info(f"开始并行处理 {len(sentences)} 个句子，使用 {max_workers} 个线程")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_sentence = {
                executor.submit(process_sentence_sync, session_id, sentence, filters): sentence
                for sentence in sentences
            }
            
            # 收集结果
            for i, future in enumerate(as_completed(future_to_sentence)):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        logger.info(f"完成句子处理 {i+1}/{len(sentences)}")
                except Exception as e:
                    sentence = future_to_sentence[future]
                    logger.error(f"处理句子时出错: {sentence[:50]}... -> {str(e)}")
                    continue
        
        logger.info(f"段落处理完成，共处理 {len(results)} 个句子")
        return results
        
    except Exception as e:
        logger.error(f"处理段落时出错: {str(e)}")
        return []