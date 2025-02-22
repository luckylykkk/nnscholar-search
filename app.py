from flask import Flask, request, jsonify, render_template, Response, stream_with_context, send_from_directory
import requests
import json
import os
from dotenv import load_dotenv
import nltk
from nltk.tokenize import sent_tokenize
from concurrent.futures import ThreadPoolExecutor
import time
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime
import traceback
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from typing import List, Dict, Any, Optional
from utils.deepseek_client import DeepSeekClient
from utils.semantic_scholar_client import SemanticScholarClient
from utils.csv_validator import CSVValidator
import csv
import aiohttp
import asyncio
from pathlib import Path
import sys
import concurrent.futures
from utils.paper_source_manager import PaperSourceManager
from functools import wraps
from utils.pubmed_client import PubMedClient
from utils.arxiv_client import ArxivClient
from asgiref.wsgi import WsgiToAsgi
from utils.journal_data import load_journal_data
from werkzeug.utils import secure_filename
from utils.paper_analyzer import PaperAnalyzer

# 加载环境变量
load_dotenv()

# 创建必要的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(LOGS_DIR, f'app_{datetime.now().strftime("%Y%m%d")}.log'),
            encoding='utf-8'
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 配置
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
SEMANTIC_SCHOLAR_API_KEY = os.getenv('SEMANTIC_SCHOLAR_API_KEY')

# 加载提示词模板
PROMPT_PATH = os.path.join(BASE_DIR, 'templates', 'search_expert_prompt.md')
try:
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        EXPERT_PROMPT = f.read()
except Exception as e:
    logger.error(f"加载提示词模板失败: {str(e)}")
    EXPERT_PROMPT = ""

# 初始化 DeepSeek 客户端
deepseek_client = DeepSeekClient(api_key=DEEPSEEK_API_KEY)

# 加载期刊数据
JOURNAL_DATA = load_journal_data(BASE_DIR)

# 创建应用实例
app = Flask(__name__, template_folder='templates')
asgi_app = WsgiToAsgi(app)  # 将 WSGI 应用转换为 ASGI 应用

# 初始化数据源管理器
paper_source_manager = PaperSourceManager()

# 初始化并注册数据源
try:
    # 初始化 Semantic Scholar 数据源
    semantic_scholar_client = SemanticScholarClient(
        api_key=SEMANTIC_SCHOLAR_API_KEY,
        journal_data=JOURNAL_DATA
    )
    paper_source_manager.register_source(semantic_scholar_client)
    logger.info("成功初始化并注册 Semantic Scholar 数据源")
    
    # 初始化 PubMed 数据源
    pubmed_client = PubMedClient(api_key=os.getenv('PUBMED_API_KEY'))
    paper_source_manager.register_source(pubmed_client)
    logger.info("成功初始化并注册 PubMed 数据源")
    
    # 初始化 arXiv 数据源
    arxiv_client = ArxivClient()
    paper_source_manager.register_source(arxiv_client)
    logger.info("成功初始化并注册 arXiv 数据源")
    
except Exception as e:
    logger.error(f"初始化数据源失败: {str(e)}")
    raise

# 配置 CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# 错误处理
@app.errorhandler(Exception)
def handle_error(error):
    logger.error(f"服务器错误: {str(error)}")
    return jsonify({
        "status": "error",
        "message": "服务器内部错误，请稍后重试"
    }), 500

def get_journal_metrics(journal_name: str) -> Dict:
    """获取期刊指标信息"""
    try:
        if not journal_name or not JOURNAL_DATA:
            return {
                'impact_factor': 'N/A',
                'jcr_quartile': 'N/A',
                'cas_quartile': 'N/A'
            }
            
        # 在期刊数据中查找匹配的记录
        for journal_info in JOURNAL_DATA.values():
            if journal_info['title'].lower() == journal_name.lower():
                return {
                    'impact_factor': journal_info.get('if', 'N/A'),
                    'jcr_quartile': journal_info.get('jcr_quartile', 'N/A'),
                    'cas_quartile': journal_info.get('cas_quartile', 'N/A')
                }
                
        return {
            'impact_factor': 'N/A',
            'jcr_quartile': 'N/A',
            'cas_quartile': 'N/A'
        }
        
    except Exception as e:
        logger.error(f"获取期刊指标失败: {str(e)}")
        return {
            'impact_factor': 'N/A',
            'jcr_quartile': 'N/A',
            'cas_quartile': 'N/A'
        }

def get_if_trend(issn):
    """获取期刊近五年影响因子趋势"""
    if not issn or issn not in IF_TREND_DATA:
        return None
    
    trend_data = IF_TREND_DATA[issn]
    years = list(trend_data.keys())[-5:]
    ifs = [trend_data[year] for year in years]
    
    # 生成趋势图
    plt.figure(figsize=(8, 4))
    plt.plot(years, ifs, marker='o')
    plt.title('Impact Factor Trend (5 Years)')
    plt.xlabel('Year')
    plt.ylabel('Impact Factor')
    plt.grid(True)
    
    # 转换为base64图片
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    image_png = buffer.getvalue()
    buffer.close()
    plt.close()
    
    return base64.b64encode(image_png).decode()

def filter_papers_by_metrics(papers, filters):
    """根据期刊指标筛选文献"""
    try:
        logger.info(f"开始筛选文献，筛选条件: {filters}")
        logger.info(f"待筛选文献数量: {len(papers)}")
        
        # 初始化统计信息
        stats = {
            'total': len(papers),
            'year_filtered': 0,
            'if_filtered': 0,
            'jcr_filtered': 0,
            'cas_filtered': 0,
            'final': 0
        }
        
        # 1. 年份筛选
        year_filtered = []
        if 'year_range' in filters and filters['year_range']:
            year_range = filters['year_range']
            logger.debug(f"应用年份筛选，范围: {year_range}")
            for paper in papers:
                pub_year = paper.get('pub_year')
                try:
                    pub_year = int(pub_year) if pub_year else None
                    logger.debug(f"文献 {paper.get('pmid')} 发表年份: {pub_year}")
                    if pub_year and year_range[0] <= pub_year <= year_range[1]:
                        year_filtered.append(paper)
                        logger.debug(f"文献 {paper.get('pmid')} 通过年份筛选")
                    else:
                        logger.debug(f"文献 {paper.get('pmid')} 未通过年份筛选: {pub_year} not in {year_range}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"年份格式错误: {pub_year}, 错误信息: {str(e)}")
        else:
            year_filtered = papers.copy()
            logger.debug("未设置年份筛选条件，保留所有文献")
        stats['year_filtered'] = len(year_filtered)
        logger.info(f"1. 年份筛选 ({filters.get('year_range', '无限制')}): {len(papers)} -> {len(year_filtered)}")
        
        # 如果年份筛选后没有文献，记录所有文献的年份信息以便调试
        if len(year_filtered) == 0:
            logger.warning("年份筛选后没有文献，记录所有文献的年份信息：")
            for paper in papers:
                pmid = paper.get('pmid', 'Unknown')
                pub_year = paper.get('pub_year')
                title = paper.get('title', '')[:100]
                logger.warning(f"PMID: {pmid}, 年份: {pub_year}, 标题: {title}")
        
        # 2. 影响因子筛选
        if_filtered = []
        if 'min_if' in filters and filters['min_if']:
            min_if = float(filters['min_if'])
            for paper in year_filtered:
                journal_info = paper.get('journal_info', {})
                impact_factor = journal_info.get('impact_factor', 'N/A')
                try:
                    if impact_factor != 'N/A':
                        if isinstance(impact_factor, str):
                            impact_factor = float(impact_factor.replace(',', ''))
                        if float(impact_factor) >= min_if:
                            if_filtered.append(paper)
                            logger.debug(f"文献 {paper.get('pmid')} 通过影响因子筛选: {impact_factor} >= {min_if}")
                        else:
                            logger.debug(f"文献 {paper.get('pmid')} 未通过影响因子筛选: {impact_factor} < {min_if}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"影响因子格式错误: {impact_factor}, 错误信息: {str(e)}")
        else:
            if_filtered = year_filtered.copy()
        stats['if_filtered'] = len(if_filtered)
        logger.info(f"2. 影响因子筛选 (>= {filters.get('min_if', '无限制')}): {len(year_filtered)} -> {len(if_filtered)}")
        
        # 3. JCR分区筛选
        jcr_filtered = []
        if 'jcr_quartile' in filters and filters['jcr_quartile']:
            for paper in if_filtered:
                journal_info = paper.get('journal_info', {})
                jcr_q = journal_info.get('jcr_quartile', 'N/A')
                if jcr_q != 'N/A' and jcr_q in filters['jcr_quartile']:
                    jcr_filtered.append(paper)
                    logger.debug(f"文献 {paper.get('pmid')} 通过JCR分区筛选: {jcr_q} in {filters['jcr_quartile']}")
                else:
                    logger.debug(f"文献 {paper.get('pmid')} 未通过JCR分区筛选: {jcr_q} not in {filters['jcr_quartile']}")
        else:
            jcr_filtered = if_filtered.copy()
        stats['jcr_filtered'] = len(jcr_filtered)
        logger.info(f"3. JCR分区筛选 ({filters.get('jcr_quartile', '无限制')}): {len(if_filtered)} -> {len(jcr_filtered)}")
        
        # 4. CAS分区筛选
        cas_filtered = []
        if 'cas_quartile' in filters and filters['cas_quartile']:
            cas_filters = [str(q) for q in filters['cas_quartile']]
            for paper in jcr_filtered:
                journal_info = paper.get('journal_info', {})
                cas_q = journal_info.get('cas_quartile', 'N/A')
                if cas_q != 'N/A':
                    if isinstance(cas_q, str) and cas_q.startswith('B'):
                        cas_q = cas_q[1:]  # 移除'B'前缀
                    if cas_q in cas_filters:
                        cas_filtered.append(paper)
                        logger.debug(f"文献 {paper.get('pmid')} 通过CAS分区筛选: {cas_q} in {cas_filters}")
                    else:
                        logger.debug(f"文献 {paper.get('pmid')} 未通过CAS分区筛选: {cas_q} not in {cas_filters}")
        else:
            cas_filtered = jcr_filtered.copy()
        stats['cas_filtered'] = len(cas_filtered)
        logger.info(f"4. CAS分区筛选 ({filters.get('cas_quartile', '无限制')}): {len(jcr_filtered)} -> {len(cas_filtered)}")
        
        # 按影响因子排序
        filtered_papers = sorted(
            cas_filtered,
            key=lambda x: float(x.get('journal_info', {}).get('impact_factor', '0').replace(',', ''))
            if isinstance(x.get('journal_info', {}).get('impact_factor'), str)
            else float(x.get('journal_info', {}).get('impact_factor', '0')),
            reverse=True
        )
        
        # 限制每句话的文献数量
        if 'papers_limit' in filters and filters['papers_limit']:
            try:
                limit = int(filters['papers_limit'])
                filtered_papers = filtered_papers[:limit]
                logger.info(f"5. 应用数量限制 ({limit}): {len(cas_filtered)} -> {len(filtered_papers)}")
            except ValueError as e:
                logger.error(f"转换papers_limit时出错: {str(e)}")
        
        stats['final'] = len(filtered_papers)
        
        # 输出详细的筛选统计信息
        logger.info("\n筛选过程统计:")
        logger.info(f"初始文献数量: {stats['total']}")
        logger.info(f"1. 年份筛选后: {stats['year_filtered']} 篇")
        logger.info(f"2. 影响因子筛选后: {stats['if_filtered']} 篇")
        logger.info(f"3. JCR分区筛选后: {stats['jcr_filtered']} 篇")
        logger.info(f"4. CAS分区筛选后: {stats['cas_filtered']} 篇")
        logger.info(f"5. 最终结果: {stats['final']} 篇")
        
        return filtered_papers, stats
        
    except Exception as e:
        logger.error(f"筛选文献时发生错误: {str(e)}\n{traceback.format_exc()}")
        raise

def handle_api_error(func):
    """API错误处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            logger.error(f"API请求错误: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': '外部API请求失败，请稍后重试'
            }), 503
        except Exception as e:
            logger.error(f"未预期的错误: {str(e)}\n{traceback.format_exc()}")
            return jsonify({
                'status': 'error',
                'message': '服务器内部错误'
            }), 500
    wrapper.__name__ = func.__name__  # 保留原函数名
    return wrapper

def call_deepseek_api(prompt: str) -> str:
    """
    调用DeepSeek API进行文本生成

    Args:
        prompt: 输入提示文本

    Returns:
        生成的文本内容
    """
    try:
        return deepseek_client.analyze_text(prompt)
    except Exception as e:
        logging.error(f"DeepSeek API调用失败: {str(e)}")
        raise

def parse_pubmed_xml(xml_content):
    """解析PubMed XML响应"""
    logger.info("开始解析PubMed XML响应")
    soup = BeautifulSoup(xml_content, 'lxml')
    articles = []
    article_count = len(soup.find_all('pubmedarticle'))
    logger.info(f"找到 {article_count} 篇文章记录")
    
    for i, article in enumerate(soup.find_all('pubmedarticle'), 1):
        try:
            logger.info(f"开始解析第 {i}/{article_count} 篇文章")
            
            # 提取文章标题
            title = article.find('articletitle')
            title = title.text if title else 'No title available'
            logger.info(f"文章标题: {title[:100]}...")
            
            # 提取发表年份
            pub_date = article.find('pubdate')
            pub_year = None
            if pub_date and pub_date.find('year'):
                pub_year = pub_date.find('year').text
                logger.info(f"发表年份: {pub_year}")
            
            # 提取期刊信息
            journal = article.find('journal')
            journal_info = {}
            if journal:
                # 提取ISSN
                issn_elem = journal.find('issn')
                if issn_elem:
                    issn = issn_elem.text
                    logger.info(f"找到ISSN: {issn}")
                else:
                    issn = None
                    logger.warning("未找到ISSN")
                journal_info['issn'] = issn
                
                # 提取期刊标题
                journal_title = journal.find('title')
                journal_info['title'] = journal_title.text if journal_title else ''
                logger.info(f"期刊标题: {journal_info['title']}")
                
                # 获取期刊指标
                if issn:
                    logger.info(f"开始获取期刊 {issn} 的指标信息")
                    metrics = get_journal_metrics(journal_info['title'])
                    if metrics:
                        logger.info(f"成功获取期刊指标: {metrics}")
                        journal_info.update(metrics)
                    else:
                        logger.warning(f"未能获取期刊 {issn} 的指标信息")
                
            # 构建文章数据
            article_data = {
                'title': title,
                'abstract': article.find('abstract').text if article.find('abstract') else 'No abstract available',
                'authors': [f"{author.find('lastname').text} {author.find('forename').text}" 
                          for author in article.find('authorlist').find_all('author') 
                          if author.find('lastname') and author.find('forename')] if article.find('authorlist') else [],
                'pub_date': (lambda d: f"{d.find('year').text if d.find('year') else ''} {d.find('month').text if d.find('month') else ''}".strip())(article.find('pubdate')) if article.find('pubdate') else 'Date not available',
                'pub_year': pub_year,  # 添加发表年份字段
                'pmid': article.find('pmid').text if article.find('pmid') else '',
                'url': f'https://pubmed.ncbi.nlm.nih.gov/{article.find("pmid").text}/' if article.find('pmid') else '#',
                'journal_info': journal_info,
                'journal_issn': journal_info.get('issn', '')
            }
            
            logger.info(f"文章数据构建完成，期刊信息: {journal_info}")
            articles.append(article_data)
            
        except Exception as e:
            logger.error(f"解析第 {i} 篇文章时发生错误: {str(e)}\n{traceback.format_exc()}")
            continue
    
    logger.info(f"完成XML解析，成功解析 {len(articles)}/{article_count} 篇文章")
    return articles

def calculate_relevance(sentence, paper):
    """计算文献与句子的相关性得分"""
    try:
        # 提取关键词
        keywords = re.findall(r'\w+', sentence.lower())
        
        # 安全获取标题和摘要
        title = paper.get('title', '') or ''
        abstract = paper.get('abstract', '') or ''
        
        # 合并标题和摘要文本
        text = f"{title} {abstract}".lower()
        
        # 计算匹配的关键词数量
        matches = sum(1 for keyword in keywords if keyword in text)
        
        # 计算相关性得分
        relevance = min(100, int((matches / len(keywords)) * 100)) if keywords else 0
        
        return relevance
    except Exception as e:
        logger.error(f"计算相关性得分时出错: {str(e)}")
        return 0  # 出错时返回0分

def search_pubmed(query: str, papers_limit: int = 10) -> List[Dict]:
    """
    搜索PubMed文献

    Args:
        query: 搜索查询文本
        papers_limit: 每句话返回的最大文献数量

    Returns:
        文献列表
    """
    try:
        logger.info(f"开始PubMed搜索，原始文本: {query}")
        logger.info("调用DeepSeek生成检索策略...")
        
        # 从模板文件加载提示词
        with open('templates/pubmed_expert_prompt.md', 'r', encoding='utf-8') as f:
            prompt = f.read()
        
        # 使用新的客户端调用方式
        search_strategy = call_deepseek_api(prompt.format(query=query))
        
        # 构建搜索请求
        search_params = {
            'db': 'pubmed',
            'term': search_strategy,
            'retmax': '100',
            'retmode': 'json',
            'api_key': PUBMED_API_KEY
        }
        
        # 发送搜索请求
        search_url = f"{PUBMED_BASE_URL}esearch.fcgi"
        response = requests.get(search_url, params=search_params)
        
        if response.status_code != 200:
            logger.error(f"PubMed搜索请求失败: HTTP {response.status_code}")
            return []
            
        search_result = response.json()
        id_list = search_result.get('esearchresult', {}).get('idlist', [])
        
        if not id_list:
            logger.warning("未找到文献，尝试更宽泛的搜索策略")
            # 使用更宽泛的搜索策略
            broader_strategy = search_strategy.replace('[Title/Abstract]', '[All Fields]').replace('[Mesh]', '[All Fields]')
            logger.info(f"更宽泛的检索策略: {broader_strategy}")
            
            search_params['term'] = broader_strategy
            response = requests.get(search_url, params=search_params)
            
            if response.status_code == 200:
                search_result = response.json()
                id_list = search_result.get('esearchresult', {}).get('idlist', [])
        
        if not id_list:
            # 如果仍然没有结果，使用最基本的关键词搜索
            basic_terms = extract_basic_terms(query)
            basic_query = ' AND '.join(f'"{term}"[All Fields]' for term in basic_terms)
            logger.info(f"使用基本关键词搜索: {basic_query}")
            
            search_params['term'] = basic_query
            response = requests.get(search_url, params=search_params)
            
            if response.status_code == 200:
                search_result = response.json()
                id_list = search_result.get('esearchresult', {}).get('idlist', [])
        
        if not id_list:
            logger.warning("所有搜索策略均未找到文献")
            return []
            
        logger.info(f"找到 {len(id_list)} 篇文献")
        return fetch_paper_details(id_list)
        
    except Exception as e:
        logger.error(f"PubMed搜索过程中发生错误: {str(e)}\n{traceback.format_exc()}")
        return []

def extract_basic_terms(text):
    """提取基本关键词"""
    # 提取括号中的缩写
    abbreviations = re.findall(r'\(([A-Z]+)\)', text)
    
    # 提取主要医学术语
    key_terms = []
    medical_terms = [
        'Coronary computed tomography angiography',
        'CCTA',
        'atherosclerotic plaque',
        'coronary'
    ]
    
    for term in medical_terms:
        if term.lower() in text.lower():
            key_terms.append(term)
    
    # 合并缩写和关键词，限制数量
    all_terms = key_terms + abbreviations
    return list(set(all_terms))[:3]  # 最多返回3个关键词

async def fetch_paper_details(id_list):
    """获取文献详细信息"""
    try:
        if not id_list:
            return []
            
        # 构建请求参数
        fetch_params = {
            'db': 'pubmed',
            'id': ','.join(id_list),
            'retmode': 'xml',
            'api_key': PUBMED_API_KEY
        }
        
        # 发送请求获取详情
        logger.info(f"获取文献详情，ID列表: {id_list}")
        fetch_url = f"{PUBMED_BASE_URL}efetch.fcgi"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url, params=fetch_params) as response:
                if response.status != 200:
                    logger.error(f"获取文献详情失败: HTTP {response.status}")
                    return []
                    
                content = await response.text()
                
                # 解析XML响应
                try:
                    soup = BeautifulSoup(content, 'xml')
                    articles = soup.find_all('PubmedArticle')
                    logger.info(f"解析到 {len(articles)} 篇文献")
                    
                    papers = []
                    for article in articles:
                        try:
                            # 提取文献信息
                            paper = extract_paper_info(article)
                            if paper:
                                papers.append(paper)
                        except Exception as e:
                            logger.error(f"解析单篇文献时出错: {str(e)}\n{traceback.format_exc()}")
                            continue
                    
                    logger.info(f"成功解析 {len(papers)} 篇文献的详细信息")
                    return papers
                    
                except Exception as e:
                    logger.error(f"解析XML响应时出错: {str(e)}\n{traceback.format_exc()}")
                    return []
                    
    except Exception as e:
        logger.error(f"获取文献详情过程中发生错误: {str(e)}\n{traceback.format_exc()}")
        return []

def extract_paper_info(article):
    """从XML中提取文献信息"""
    try:
        # 提取基本信息
        pmid = article.find('PMID').text if article.find('PMID') else None
        if not pmid:
            logger.warning("文献缺少PMID，跳过")
            return None
            
        logger.info(f"开始处理文献 PMID: {pmid}")
            
        # 提取标题
        title_element = article.find('ArticleTitle')
        title = title_element.text if title_element else None
        if not title:
            logger.warning(f"文献 {pmid} 缺少标题，跳过")
            return None
            
        logger.info(f"文献标题: {title[:100]}...")
            
        # 提取期刊信息
        journal_element = article.find('Journal')
        if not journal_element:
            logger.warning(f"文献 {pmid} 缺少期刊信息，跳过")
            return None
            
        # 提取期刊标题 - 优先使用Title，如果没有则使用ISOAbbreviation
        journal_title = None
        journal_full = journal_element.find('Title')
        journal_iso = journal_element.find('ISOAbbreviation')
        
        logger.info(f"期刊信息提取详情:")
        logger.info(f"- 完整标题: {journal_full.text if journal_full else 'N/A'}")
        logger.info(f"- ISO缩写: {journal_iso.text if journal_iso else 'N/A'}")
        
        if journal_full and journal_full.text:
            journal_title = journal_full.text
            logger.info(f"使用完整期刊标题: {journal_title}")
        elif journal_iso and journal_iso.text:
            journal_title = journal_iso.text
            logger.info(f"使用期刊ISO缩写: {journal_title}")
            
        if not journal_title:
            logger.warning(f"文献 {pmid} 缺少期刊标题")
            return None
            
        issn = journal_element.find('ISSN').text if journal_element.find('ISSN') else None
        
        logger.info(f"期刊信息 - 标题: {journal_title}, ISSN: {issn}")
        
        if not issn:
            logger.warning(f"文献 {pmid} 缺少ISSN，跳过")
            return None
            
        # 提取发表年份
        pub_year = None
        pub_date = article.find('PubDate')
        
        logger.info(f"开始提取发表年份，PubDate标签内容: {pub_date}")
        
        if pub_date:
            # 尝试从Year标签提取
            year_elem = pub_date.find('Year')
            if year_elem and year_elem.text:
                pub_year = year_elem.text
                logger.info(f"从Year标签提取的年份: {pub_year}")
            else:
                # 如果没有Year标签，尝试从MedlineDate中提取
                medline_date = pub_date.find('MedlineDate')
                if medline_date and medline_date.text:
                    logger.info(f"找到MedlineDate: {medline_date.text}")
                    try:
                        # MedlineDate可能的格式: "2020 Dec-2021 Jan"
                        pub_year = medline_date.text.split()[0]  # 取第一个年份
                        logger.info(f"从MedlineDate提取的年份: {pub_year}")
                    except (IndexError, ValueError):
                        logger.warning(f"无法从MedlineDate解析年份: {medline_date.text}")
                else:
                    logger.warning("未找到Year标签或MedlineDate标签")
        else:
            logger.warning(f"文献 {pmid} 缺少PubDate标签")
        
        if not pub_year:
            logger.warning(f"文献 {pmid} 未能提取到发表年份")
            return None
            
        try:
            pub_year = int(pub_year)
            logger.info(f"成功将年份转换为整数: {pub_year}")
        except ValueError:
            logger.warning(f"文献 {pmid} 的发表年份格式无效: {pub_year}")
            return None
            
        # 获取期刊指标
        journal_metrics = get_journal_metrics(journal_title)
        if not journal_metrics:
            logger.warning(f"未找到期刊 {journal_title} (ISSN: {issn}) 的指标信息")
            # 如果没有找到期刊指标，仍然保留期刊基本信息
            journal_metrics = {
                'title': journal_title,
                'issn': issn,
                'impact_factor': 'N/A',
                'jcr_quartile': 'N/A',
                'cas_quartile': 'N/A'
            }
            logger.info("使用默认期刊指标信息")
        else:
            # 确保期刊标题使用从PubMed获取的标题
            journal_metrics['title'] = journal_title
            logger.info(f"获取到期刊指标:")
            logger.info(f"- 期刊标题: {journal_metrics['title']}")
            logger.info(f"- 影响因子: {journal_metrics['impact_factor']}")
            logger.info(f"- JCR分区: {journal_metrics['jcr_quartile']}")
            logger.info(f"- CAS分区: {journal_metrics['cas_quartile']}")
            
        # 构建文献信息
        paper_info = {
            'pmid': pmid,
            'title': title,
            'journal_info': journal_metrics,
            'pub_year': pub_year
        }
        
        logger.info(f"文献 {pmid} 的完整信息:")
        logger.info(f"- 标题: {title}")
        logger.info(f"- 发表年份: {pub_year}")
        logger.info(f"- 期刊标题: {journal_metrics['title']}")
        logger.info(f"- ISSN: {issn}")
        logger.info(f"- 影响因子: {journal_metrics['impact_factor']}")
        logger.info(f"- JCR分区: {journal_metrics['jcr_quartile']}")
        logger.info(f"- CAS分区: {journal_metrics['cas_quartile']}")
        
        # 提取摘要
        abstract_element = article.find('Abstract')
        if abstract_element:
            abstract_text = ' '.join(text.text for text in abstract_element.find_all('AbstractText'))
            paper_info['abstract'] = abstract_text
            logger.info(f"成功提取摘要，长度: {len(abstract_text)}")
        else:
            paper_info['abstract'] = 'No abstract available'
            logger.warning("未找到摘要信息")
            
        # 提取作者信息
        author_list = article.find('AuthorList')
        if author_list:
            authors = []
            for author in author_list.find_all('Author'):
                last_name = author.find('LastName')
                fore_name = author.find('ForeName')
                if last_name and fore_name:
                    authors.append(f"{last_name.text} {fore_name.text}")
            paper_info['authors'] = authors
            logger.info(f"成功提取作者信息，作者数量: {len(authors)}")
            if authors:
                logger.info(f"第一作者: {authors[0]}")
                if len(authors) > 1:
                    logger.info(f"通讯作者: {authors[-1]}")
        else:
            paper_info['authors'] = []
            logger.warning("未找到作者信息")
            
        return paper_info
            
    except Exception as e:
        logger.error(f"解析文献信息时出错: {str(e)}\n{traceback.format_exc()}")
        return None

def process_sentence(sentence, filters=None):
    """处理单个句子，分解为短句并添加相关文献序号"""
    logger.info(f"开始处理长句: {sentence[:100]}...")
    try:
        # 首先获取长句的所有相关文献
        logger.info("获取长句的所有相关文献...")
        all_papers = search_pubmed(sentence)
        
        # 为所有文献计算相关性得分并排序
        # for paper in all_papers:
        #     paper['relevance'] = calculate_relevance(sentence, paper)
        # all_papers.sort(key=lambda x: x['relevance'], reverse=True)
        
        # 创建文献ID到序号的映射
        paper_index_map = {paper['pmid']: idx for idx, paper in enumerate(all_papers, 1)}
        logger.info(f"长句共检索到 {len(all_papers)} 篇文献")

        # 使用文本分析专家提示词分解长句
        split_prompt = f"""作为语言逻辑分析专家和文本优化顾问，请将以下长句分解为多个独立短句：

长句：{sentence}

要求：
1. 每个短句必须结构完整，包含明确的主语、谓语和宾语
2. 避免使用代词（如"它"、"这"、"那"）指代前文内容
3. 保持原句的核心信息和逻辑关系
4. 确保每个短句都能独立表达完整的意思
5. 按序号列出短句"""

        logger.info("调用DeepSeek分解长句...")
        split_response = call_deepseek_api(split_prompt)
        logger.info(f"分解结果: {split_response}")

        # 解析短句列表
        short_sentences = []
        for line in split_response.split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                sentence = re.sub(r'^\d+\.\s*', '', line).strip()
                if not sentence.endswith('。'):
                    sentence += '。'
                if sentence:
                    short_sentences.append(sentence)

        logger.info(f"共分解出 {len(short_sentences)} 个短句")

        # 处理每个短句
        results = []
        for idx, short_sent in enumerate(short_sentences, 1):
            logger.info(f"处理第 {idx} 个短句: {short_sent}")

            # 生成检索策略
            search_prompt = f"""作为PubMed搜索专家，请为以下医学短句生成检索策略：

医学短句：{short_sent}

请按以下格式提供：

1. 核心医学概念：
- [列出2-3个最重要的医学概念，每个概念一行]

2. MeSH主题词：
- [列出对应的MeSH术语，每个术语一行]

3. 检索策略：
主策略：[使用MeSH Terms的精确检索策略]
补充策略：[使用Title/Abstract的扩展检索策略]"""

            search_strategy = call_deepseek_api(search_prompt)
            
            # 解析检索策略并搜索文献
            papers = search_pubmed(short_sent)
            
            # 计算相关性并排序
            # for paper in papers:
            #     paper['relevance'] = calculate_relevance(short_sent, paper)
            # papers.sort(key=lambda x: x['relevance'], reverse=True)
            
            # 获取文献在原始长句文献列表中的序号
            paper_indices = []
            for paper in papers[:10]:  # 只取相关性最高的前10篇
                if paper['pmid'] in paper_index_map:
                    paper_indices.append(paper_index_map[paper['pmid']])
            
            # 格式化文献序号列表
            indices_str = ', '.join(str(i) for i in sorted(paper_indices))
            
            # 构建带有文献序号的短句
            annotated_sentence = f"{short_sent} [相关文献序号：{indices_str}]"
            
            results.append({
                'short_sentence': short_sent,
                'annotated_sentence': annotated_sentence,
                'paper_indices': paper_indices,
                'papers': papers
            })

        final_result = {
            'original_sentence': sentence,
            'all_papers': all_papers,
            'short_sentences': results
        }

        # 生成格式化输出
        formatted_output = [
            "原始长句：",
            sentence,
            "\n相关文献列表：",
        ]
        
        # 添加排序后的文献列表
        for idx, paper in enumerate(all_papers, 1):
            formatted_output.append(f"{idx}. {paper.get('title', 'No title')} (PMID: {paper['pmid']})")
        
        formatted_output.append("\n分解后的短句及其相关文献：")
        for result in results:
            formatted_output.append(result['annotated_sentence'])

        final_result['formatted_output'] = '\n'.join(formatted_output)
        logger.info("长句处理完成")
        return final_result

    except Exception as e:
        logger.error(f"处理长句时发生错误: {str(e)}\n{traceback.format_exc()}")
        return {
            'original_sentence': sentence,
            'all_papers': [],
            'short_sentences': [],
            'formatted_output': f"处理过程中发生错误: {str(e)}"
        }

def generate_broader_query(query):
    """生成更宽泛的搜索策略"""
    try:
        # 移除一些限制性标签
        broader = query.replace('[Title/Abstract]', '[All Fields]')
        broader = broader.replace('[Mesh]', '[All Fields]')
        
        # 如果包含多个AND条件，只保留部分
        terms = broader.split(' AND ')
        if len(terms) > 2:
            # 保留最重要的2-3个术语
            terms = terms[:3]
            broader = ' AND '.join(terms)
        
        logger.info(f"原始查询: {query}")
        logger.info(f"更宽泛的查询: {broader}")
        return broader
        
    except Exception as e:
        logger.error(f"生成更宽泛查询时出错: {str(e)}")
        return query  # 出错时返回原始查询

async def generate_search_strategy(text: str) -> str:
    """使用DeepSeek生成检索策略"""
    try:
        logger.info(f"开始为文本生成检索策略: {text}")
        prompt = EXPERT_PROMPT.format(query=text)
        logger.info(f"使用提示词:\n{prompt}")
        
        response = call_deepseek_api(prompt)
        logger.info(f"DeepSeek原始响应:\n{response}")
        
        # 解析响应获取检索策略
        strategy = ""
        lines = response.split('\n')
        
        # 记录解析过程
        logger.info("开始解析检索策略:")
        for i, line in enumerate(lines):
            logger.debug(f"处理第{i+1}行: {line}")
            if line.startswith('2. 检索'):
                if i + 1 < len(lines):
                    strategy = lines[i + 1].strip()
                    # 移除可能的引号
                    strategy = strategy.replace('"', '').replace("'", '')
                    logger.info(f"找到检索策略: {strategy}")
                break
        
        if not strategy:
            # 尝试直接从关键词部分构建检索策略
            keywords = []
            for line in lines:
                if line.strip().startswith('- '):
                    keyword = line.strip()[2:].strip()  # 移除'- '前缀
                    if keyword:
                        keywords.append(keyword)
            
            if keywords:
                search_query = ' '.join(keywords)
                logger.info(f"从关键词构建检索策略: {search_query}")
            else:
                logger.warning("未能从DeepSeek响应中提取检索策略，将使用原始查询")
                search_query = text
            
            logger.info(f"提取的检索策略: {search_query}")
            query = search_query  # 使用生成的英文检索策略替换原始查询
            
        logger.info(f"最终生成的检索策略: {strategy}")
        return strategy
        
    except Exception as e:
        logger.error(f"生成检索策略失败: {str(e)}")
        return text

@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')

def async_route(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapped

@app.route('/api/search', methods=['POST'])
async def search():
    """搜索论文接口"""
    try:
        # 获取请求数据
        data = request.get_json()
        query = data.get('query', '')
        filters = data.get('filters', {})
        
        if not query:
            return jsonify({
                'status': 'error',
                'message': '请输入搜索内容'
            })
            
        # 记录选择的数据源
        selected_sources = filters.get('sources', [])
        logger.info(f"用户选择的数据源: {selected_sources}")
        
        if not selected_sources:
            return jsonify({
                'status': 'error',
                'message': '请至少选择一个数据源'
            })
            
        # 使用DeepSeek生成检索策略
        try:
            strategy = deepseek_client.generate_search_strategy(query)
            logger.info(f"生成的检索策略: {strategy}")
            
            # 提取关键词
            keywords = extract_keywords_from_strategy(strategy)
            if not keywords:
                logger.warning("未能从检索策略中提取到关键词,将使用原始查询")
                keywords = [query]
            
            logger.info(f"提取的关键词: {keywords}")
            
        except Exception as e:
            logger.error(f"生成检索策略时出错: {str(e)}")
            keywords = [query]
            
        # 搜索论文
        all_papers = []
        seen_paper_ids = set()
        
        # 对每个关键词分别搜索
        for keyword in keywords:
            try:
                # 从每个选择的数据源搜索
                for source_name in selected_sources:
                    if source_name not in paper_source_manager.sources:
                        logger.warning(f"未知的数据源: {source_name}")
                        continue
                        
                    source = paper_source_manager.sources[source_name]
                    try:
                        papers = await source.search_papers(keyword, filters)
                        logger.info(f"从 {source_name} 获取到 {len(papers)} 篇论文")
                        
                        # 去重并添加到结果列表
                        for paper in papers:
                            paper_id = paper.get("id")
                            if paper_id and paper_id not in seen_paper_ids:
                                seen_paper_ids.add(paper_id)
                                paper["source"] = source_name  # 添加来源标记
                                # 计算相关度分数
                                # paper['relevance_score'] = calculate_relevance(paper, keywords)
                                all_papers.append(paper)
                                
                    except Exception as e:
                        logger.error(f"从 {source_name} 搜索论文时出错: {str(e)}")
                        
            except Exception as e:
                logger.error(f"搜索关键词 '{keyword}' 时出错: {str(e)}")
                
        # 按相关度分数排序
        all_papers.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return jsonify({
            'status': 'success',
            'data': {
                'papers': all_papers,
                'total': len(all_papers)
            }
        })
        
    except Exception as e:
        logger.error(f"搜索接口出错: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'搜索失败: {str(e)}'
        })

@app.route('/api/paper/<paper_id>', methods=['GET'])
@async_route
async def get_paper_details(paper_id):
    """
    获取论文详情接口
    """
    try:
        source_name = request.args.get('source')  # 可选参数，指定数据源
        
        if source_name:
            source = paper_source_manager.get_source(source_name)
            if not source:
                return jsonify({
                    "status": "error",
                    "message": f"未找到数据源: {source_name}"
                }), 404
                
            details = await source.get_paper_details(paper_id)
            results = {source_name: details}
        else:
            # 从所有数据源获取详情
            results = await paper_source_manager.get_paper_details_all_sources(paper_id)
            
        return jsonify({
            "status": "success",
            "data": results
        })
        
    except Exception as e:
        logger.error(f"获取论文详情失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/sources', methods=['GET'])
def get_available_sources():
    """
    获取可用数据源列表
    """
    sources = paper_source_manager.get_all_sources()
    return jsonify({
        "status": "success",
        "data": sources
    })

def split_sentences(text):
    """将文本分割成句子"""
    try:
        sentences = []
        
        # 处理英文句子
        # 1. 先将句号+空格的模式替换为特殊标记，避免被括号内的句号干扰
        text = re.sub(r'\.\s+([A-Z])', r'SENT_BREAK\1', text)
        
        # 2. 按特殊标记分割
        temp_sentences = text.split('SENT_BREAK')
        
        # 3. 处理每个分割后的句子
        for sent in temp_sentences:
            sent = sent.strip()
            if sent:
                # 如果句子末尾没有标点，添加句号
                if not sent[-1] in '.!?。！？':
                    sent += '.'
                sentences.append(sent)
        
        # 如果没有找到句子，将整个文本作为一个句子
        if not sentences and text.strip():
            sentences = [text.strip()]
        
        logger.info(f"文本分句结果: {len(sentences)} 句")
        for i, s in enumerate(sentences, 1):
            logger.debug(f"第 {i} 句: {s}")
        
        return sentences
        
    except Exception as e:
        logger.error(f"文本分句时出错: {str(e)}\n{traceback.format_exc()}")
        return [text.strip()] if text.strip() else []

def filter_papers(papers: List[Dict], filters: Dict) -> List[Dict]:
    """根据条件筛选论文"""
    try:
        filtered = papers.copy()
        logger.info(f"开始筛选，初始论文数: {len(filtered)}")
        
        # 年份筛选
        if 'year_range' in filters and filters['year_range']:
            start_year, end_year = filters['year_range']
            before_count = len(filtered)
            filtered = [
                paper for paper in filtered 
                if paper.get('year') and start_year <= paper['year'] <= end_year
            ]
            logger.info(f"年份筛选 ({start_year}-{end_year}): {before_count} -> {len(filtered)}")
        
        # 引用数筛选
        if 'min_citation_count' in filters and filters['min_citation_count'] > 0:
            min_cites = filters['min_citation_count']
            before_count = len(filtered)
            filtered = [
                paper for paper in filtered 
                if paper.get('citationCount', 0) >= min_cites
            ]
            logger.info(f"引用数筛选 (>={min_cites}): {before_count} -> {len(filtered)}")
        
        # 学科领域筛选（可选）
        if 'fields_of_study' in filters and filters['fields_of_study']:
            fields = set(filters['fields_of_study'])
            before_count = len(filtered)
            # 只有当论文有学科领域信息时才进行筛选
            filtered = [
                paper for paper in filtered 
                if not paper.get('fieldsOfStudy') or  # 如果论文没有学科信息，保留
                any(field in fields for field in paper.get('fieldsOfStudy', []))
            ]
            logger.info(f"学科领域筛选 ({fields}): {before_count} -> {len(filtered)}")
        
        # JCR分区筛选
        if 'jcr_quartile' in filters and filters['jcr_quartile']:
            allowed_quartiles = set(filters['jcr_quartile'])
            before_count = len(filtered)
            filtered = [
                paper for paper in filtered
                if paper.get('journal_info', {}).get('jcr_quartile') in allowed_quartiles
            ]
            logger.info(f"JCR分区筛选 ({allowed_quartiles}): {before_count} -> {len(filtered)}")
        
        # 中科院分区筛选
        if 'cas_quartile' in filters and filters['cas_quartile']:
            allowed_quartiles = set(filters['cas_quartile'])
            cas_mapping = {'1': 'B1', '2': 'B2', '3': 'B3', '4': 'B4', 'N/A': 'N/A'}
            mapped_quartiles = {cas_mapping.get(q, q) for q in allowed_quartiles}
            
            before_count = len(filtered)
            filtered = [
                paper for paper in filtered
                if paper.get('journal_info', {}).get('cas_quartile') in mapped_quartiles
            ]
            logger.info(f"中科院分区筛选 (原始: {allowed_quartiles}, 映射后: {mapped_quartiles}): {before_count} -> {len(filtered)}")
        
        logger.info(f"筛选完成，最终论文数: {len(filtered)}")
        return filtered
        
    except Exception as e:
        logger.error(f"论文筛选失败: {str(e)}")
        return papers  # 出错时返回原始论文列表

def download_pdf(paper, pdf_dir, download_status, i):
    """使用线程池下载单个PDF文件"""
    if not paper['PDF链接']:
        logger.info(f"论文无PDF链接可用: {paper['标题']}")
        return None
        
    safe_title = "".join(x for x in paper['标题'][:50] if x.isalnum() or x in (' ', '_'))
    filename = f"{i+1}_{safe_title}.pdf"
    pdf_path = pdf_dir / filename
    
    # 检查是否已经成功下载
    if filename in download_status and download_status[filename]['status'] == 'success':
        logger.info(f"跳过已下载: {filename}")
        return {'filename': filename, 'status': 'skipped'}
    
    try:
        logger.info(f"尝试下载PDF: {paper['PDF链接']}")
        response = requests.get(paper['PDF链接'], timeout=30)
        if response.status_code == 200 and response.headers.get('content-type', '').lower().startswith('application/pdf'):
            pdf_path.write_bytes(response.content)
            download_status[filename] = {
                'status': 'success',
                'timestamp': datetime.now().isoformat()
            }
            logger.info(f"成功下载PDF: {filename}")
            return {'filename': filename, 'status': 'success'}
        else:
            download_status[filename] = {
                'status': 'failed',
                'error': f'HTTP {response.status_code} 或非PDF响应',
                'timestamp': datetime.now().isoformat()
            }
            logger.warning(f"下载PDF失败 {paper['PDF链接']}: HTTP {response.status_code}")
            return {'filename': filename, 'status': 'failed', 'error': f'HTTP {response.status_code}'}
    except Exception as e:
        download_status[filename] = {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
        logger.error(f"下载PDF失败 {paper['PDF链接']}: {str(e)}")
        return {'filename': filename, 'status': 'failed', 'error': str(e)}

@app.route('/api/export', methods=['POST'])
def export_results():
    def generate():
        try:
            data = request.json
            results = data.get('results', [])
            search_text = data.get('search_text', '').strip()
            
            # 添加调试日志
            logger.info(f"开始导出，结果数量: {len(results)}")
            logger.info(f"搜索文本: {search_text}")
            
            # 创建导出目录
            export_dir = Path('exports')
            export_dir.mkdir(exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_search_text = "".join(x for x in search_text if x.isalnum() or x in (' ', '_'))[:30]
            base_name = f"{safe_search_text}_{timestamp}"
            
            # 创建PDF保存目录
            pdf_dir = export_dir / f"{base_name}_pdfs"
            pdf_dir.mkdir(exist_ok=True)
            
            yield 'data: ' + json.dumps({
                'progress': 10,
                'status': '正在准备数据...'
            }) + '\n\n'
            
            # 准备CSV数据
            csv_data = []
            total_papers = 0
            
            # 添加调试日志
            logger.info("开始处理论文数据")
            
            for result in results:
                papers = result.get('papers', [])
                total_papers += len(papers)
                for paper in papers:
                    try:
                        row = {
                            '标题': paper.get('title', ''),
                            '摘要': paper.get('abstract', ''),
                            '作者': ', '.join(a.get('name', '') for a in paper.get('authors', [])),
                            '发表年份': paper.get('year', ''),
                            '期刊名称': paper.get('journal_info', {}).get('title', ''),
                            '影响因子': paper.get('journal_info', {}).get('impact_factor', 'N/A'),
                            'JCR分区': paper.get('journal_info', {}).get('jcr_quartile', 'N/A'),
                            'CAS分区': paper.get('journal_info', {}).get('cas_quartile', 'N/A'),
                            'DOI': paper.get('doi', ''),
                            'PMID': paper.get('pmid', ''),
                            '引用次数': paper.get('citationCount', 0),
                            'PDF链接': paper.get('pdf_url', '')
                        }
                        csv_data.append(row)
                        logger.info(f"添加论文: {row['标题']}")
                        if row['PDF链接']:
                            logger.info(f"包含PDF链接: {row['PDF链接']}")
                    except Exception as e:
                        logger.error(f"处理论文数据时出错: {str(e)}")
            
            logger.info(f"共处理 {len(csv_data)} 篇论文")
            
            # 保存CSV文件
            csv_path = export_dir / f"{base_name}.csv"
            df = pd.DataFrame(csv_data)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            
            # 创建下载记录文件
            download_record = pdf_dir / 'download_record.json'
            download_status = {}
            
            if download_record.exists():
                with open(download_record, 'r', encoding='utf-8') as f:
                    download_status = json.load(f)
            
            # 使用线程池下载PDF文件
            total_pdfs = sum(1 for paper in csv_data if paper['PDF链接'])
            downloaded = 0
            
            # 创建线程池
            with ThreadPoolExecutor(max_workers=5) as executor:
                # 提交下载任务
                future_to_paper = {
                    executor.submit(download_pdf, paper, pdf_dir, download_status, i): paper
                    for i, paper in enumerate(csv_data)
                    if paper['PDF链接']
                }
                
                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_paper):
                    result = future.result()
                    if result and result['status'] in ['success', 'skipped']:
                        downloaded += 1
                        
                    progress = int(20 + (downloaded / total_pdfs * 80))
                    yield 'data: ' + json.dumps({
                        'progress': progress,
                        'status': f'正在下载PDF文件 ({downloaded}/{total_pdfs})',
                        'details': f'已完成: {result["filename"] if result else "unknown"}'
                    }) + '\n\n'
                    
                    # 保存下载记录
                    with open(download_record, 'w', encoding='utf-8') as f:
                        json.dump(download_status, f, ensure_ascii=False, indent=2)
            
            # 生成失败下载报告
            failed_downloads = [
                f"{name}: {info['error']}"
                for name, info in download_status.items()
                if info['status'] == 'failed'
            ]
            
            if failed_downloads:
                report_path = pdf_dir / 'failed_downloads.txt'
                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(failed_downloads))
            
            # 使用 yield 替代 return
            yield json.dumps({
                'progress': 100,
                'status': '导出完成',
                'complete': True,
                'message': (
                    f'导出成功！\n'
                    f'CSV文件保存在: {csv_path}\n'
                    f'PDF文件保存在: {pdf_dir}\n'
                    f'成功下载: {sum(1 for info in download_status.values() if info["status"] == "success")}\n'
                    f'失败下载: {len(failed_downloads)}'
                )
            })
            
        except Exception as e:
            logger.error(f"导出失败: {str(e)}")
            yield 'data: ' + json.dumps({
                'error': f'导出失败: {str(e)}'
            }) + '\n\n'
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/retry-downloads', methods=['POST'])
def retry_downloads():
    try:
        data = request.json
        export_dir = data.get('export_dir')
        
        if not export_dir or not os.path.exists(export_dir):
            return jsonify({'error': '导出目录不存在'}), 400
        
        pdf_dir = Path(export_dir)
        record_file = pdf_dir / 'download_record.json'
        
        if not record_file.exists():
            return jsonify({'error': '下载记录不存在'}), 404
        
        with open(record_file, 'r', encoding='utf-8') as f:
            download_status = json.load(f)
        
        # 筛选出失败的下载
        failed_downloads = {
            name: info
            for name, info in download_status.items()
            if info['status'] == 'failed'
        }
        
        if not failed_downloads:
            return jsonify({'message': '没有需要重新下载的文件'})
        
        # 读取原始CSV文件以获取下载链接
        csv_file = list(pdf_dir.parent.glob('*.csv'))[0]
        df = pd.read_csv(csv_file)
        
        # 重新下载失败的文件
        for filename in failed_downloads:
            # 从文件名中提取索引
            index = int(filename.split('_')[0]) - 1
            if index < len(df):
                pdf_url = df.iloc[index]['PDF链接']
                if pdf_url:
                    try:
                        response = requests.get(pdf_url, timeout=30)
                        if response.status_code == 200:
                            (pdf_dir / filename).write_bytes(response.content)
                            download_status[filename]['status'] = 'success'
                            download_status[filename]['timestamp'] = datetime.now().isoformat()
                            logger.info(f"重新下载成功: {filename}")
                        else:
                            download_status[filename]['error'] = f'HTTP {response.status_code}'
                            download_status[filename]['timestamp'] = datetime.now().isoformat()
                    except Exception as e:
                        download_status[filename]['error'] = str(e)
                        download_status[filename]['timestamp'] = datetime.now().isoformat()
        
        # 更新下载记录
        with open(record_file, 'w', encoding='utf-8') as f:
            json.dump(download_status, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'status': 'success',
            'message': f'重新下载完成，请查看下载记录获取详细信息'
        })
        
    except Exception as e:
        logger.error(f"重新下载失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': f'重新下载失败: {str(e)}'
        }), 500

def extract_keywords_from_strategy(strategy: str) -> List[str]:
    """
    从检索策略中提取关键词
    
    Args:
        strategy: 检索策略文本
        
    Returns:
        List[str]: 关键词列表
    """
    try:
        keywords = []
        lines = strategy.split('\n')
        
        
        for line in lines:
            line = line.strip()
            

                
                
            # 检查是否离开关键词部分
            if line.startswith('2. 检索'):
                break
                
            # 提取关键词
            if line.startswith('-'):
                keyword = line[1:].strip()  # 移除'-'前缀
                if not keyword:
                    continue
                    
                # 判断是否为英文关键词
                
                keywords.append(keyword)
        
        logger.info(f"提取到的英文关键词: {keywords}")
        return keywords
        
    except Exception as e:
        logger.error(f"提取关键词时出错: {str(e)}")
        return []

@app.route('/validate')
def validate_page():
    """论文领域验证页面"""
    return render_template('validate.html')

@app.route('/api/validate', methods=['GET', 'POST'])
def validate_papers():
    if request.method == 'POST':
        # 处理文件上传
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': '没有上传文件'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': '没有选择文件'})
            
        if not file.filename.endswith('.csv'):
            return jsonify({'status': 'error', 'message': '请上传CSV文件'})
            
        # 保存上传的文件
        filename = secure_filename(file.filename)
        file_path = os.path.join('exports', filename)
        file.save(file_path)
        
        return jsonify({'status': 'success', 'message': '文件上传成功'})
    
    # GET请求处理验证过程
    domain = request.args.get('domain')
    filename = request.args.get('filename')
    start_row = int(request.args.get('start_row', 0))
    thread_count = int(request.args.get('thread_count', 5))  # 获取线程数量参数
    
    if not domain or not filename:
        return jsonify({'status': 'error', 'message': '缺少必要参数'})
    
    csv_file = os.path.join('exports', filename)
    if not os.path.exists(csv_file):
        return jsonify({'status': 'error', 'message': '文件不存在'})
    
    def generate():
        try:
            logger.info("开始验证过程")
            validator = CSVValidator()
            
            # 读取CSV文件获取总行数
            df = pd.read_csv(csv_file)
            total_rows = len(df)
            
            # 创建线程池
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                # 获取所有记录
                records = []
                futures = []
                current_row = start_row
                
                for record, full_record in validator.read_csv_iterator(csv_file):
                    if current_row < start_row:
                        current_row += 1
                        continue
                        
                    # 提交验证任务到线程池
                    future = executor.submit(validator.validate_single_record, record, domain)
                    futures.append((future, record, full_record, current_row))
                    current_row += 1
                
                valid_records = []
                invalid_records = []
                
                # 处理每个任务的结果
                for future, record, full_record, row_num in futures:
                    try:
                        is_valid = future.result()
                        
                        # 计算进度
                        progress = int((row_num - start_row + 1) / (total_rows - start_row) * 100)
                        
                        # 发送进度信息
                        result = {
                            'status': 'processing',
                            'progress': progress,
                            'current': {
                                'title': record['标题'],
                                'is_valid': is_valid,
                                'result': '符合领域' if is_valid else '不符合领域',
                                'row': row_num
                            }
                        }
                        
                        yield 'data: ' + json.dumps(result, ensure_ascii=False) + '\n\n'
                        
                        if is_valid:
                            valid_records.append(full_record)
                        else:
                            invalid_records.append(full_record)
                            
                    except Exception as e:
                        logger.error(f"处理记录时出错: {str(e)}")
                        continue
            
            # 保存结果文件
            if valid_records or invalid_records:
                dir_path = os.path.dirname(csv_file)
                file_name = os.path.splitext(os.path.basename(csv_file))[0]
                
                valid_file_path = None
                invalid_file_path = None
                
                if valid_records:
                    valid_file_path = os.path.join(dir_path, f"{file_name}_校验.csv")
                    pd.DataFrame(valid_records).to_csv(valid_file_path, index=False)
                    
                if invalid_records:
                    invalid_file_path = os.path.join(dir_path, f"{file_name}_exclude.csv")
                    pd.DataFrame(invalid_records).to_csv(invalid_file_path, index=False)
                
                # 发送完成消息
                final_result = {
                    'status': 'complete',
                    'results': {
                        'valid_file': valid_file_path,
                        'invalid_file': invalid_file_path,
                        'valid_count': len(valid_records),
                        'invalid_count': len(invalid_records),
                        'total_count': total_rows
                    }
                }
                yield 'data: ' + json.dumps(final_result, ensure_ascii=False) + '\n\n'
                
        except Exception as e:
            logger.error(f"验证过程出错: {str(e)}")
            error_result = {
                'status': 'error',
                'message': f'验证过程出错: {str(e)}'
            }
            yield 'data: ' + json.dumps(error_result, ensure_ascii=False) + '\n\n'
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/list-exports')
def list_exports():
    """获取exports目录下的CSV文件列表"""
    try:
        exports_dir = os.path.join(BASE_DIR, 'exports')
        if not os.path.exists(exports_dir):
            return jsonify({'files': []})
            
        files = [f for f in os.listdir(exports_dir) if f.endswith('.csv')]
        return jsonify({'files': files})
        
    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/download/<path:filename>')
def download_file(filename):
    """下载文件路由"""
    try:
        # 获取exports目录的绝对路径
        exports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports')
        
        # 确保文件名不包含目录遍历
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(exports_dir, safe_filename)
        
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return jsonify({
                'status': 'error',
                'message': '文件不存在'
            }), 404
            
        # 发送文件
        return send_from_directory(
            directory=exports_dir,
            path=safe_filename,
            as_attachment=True
        )
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': '文件下载失败'
        }), 500

@app.route('/reader')
def reader_page():
    """论文阅读与总结页面"""
    return render_template('paper_reader.html')

# 初始化论文分析器
paper_analyzer = PaperAnalyzer()

@app.route('/api/analyze_status')
def analyze_status():
    """处理论文分析状态的SSE连接"""
    def generate():
        try:
            filename = request.args.get('filename')
            if not filename:
                yield 'data: ' + json.dumps({
                    'error': '缺少文件名参数'
                }) + '\n\n'
                return
                
            file_path = os.path.join('exports', filename)
            if not os.path.exists(file_path):
                yield 'data: ' + json.dumps({
                    'error': '文件不存在'
                }) + '\n\n'
                return
                
            # 读取文件内容
            yield 'data: ' + json.dumps({
                'progress': 10,
                'message': '正在读取文件内容...'
            }) + '\n\n'
            
            content = None
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if not content:
                yield 'data: ' + json.dumps({
                    'error': '文件内容为空'
                }) + '\n\n'
                return
                
            # 分析论文
            yield 'data: ' + json.dumps({
                'progress': 30,
                'message': '正在分析论文内容...'
            }) + '\n\n'
            
            try:
                result = paper_analyzer.analyze_paper(content)
                # 发送预览内容
                yield 'data: ' + json.dumps({
                    'progress': 60,
                    'message': '正在生成预览...',
                    'preview': result
                }) + '\n\n'
            except Exception as e:
                yield 'data: ' + json.dumps({
                    'error': f'论文分析失败: {str(e)}'
                }) + '\n\n'
                return
                
            # 生成结果文件
            yield 'data: ' + json.dumps({
                'progress': 80,
                'message': '正在生成分析报告...'
            }) + '\n\n'
            
            base_name = os.path.splitext(filename)[0]
            result_filename = f"{base_name}_阅读总结.md"
            result_path = os.path.join('exports', result_filename)
            
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write(result)
                
            # 完成
            yield 'data: ' + json.dumps({
                'progress': 100,
                'message': '分析完成！',
                'complete': True,
                'result_file': result_filename
            }) + '\n\n'
            
        except Exception as e:
            logger.error(f"论文分析过程出错: {str(e)}")
            yield 'data: ' + json.dumps({
                'error': f'分析过程出错: {str(e)}'
            }) + '\n\n'
            
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/analyze_paper', methods=['POST'])
def analyze_paper():
    """处理论文文件上传和分析请求"""
    try:
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': '没有上传文件'})
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': '没有选择文件'})
            
        if not file.filename.endswith('.md'):
            return jsonify({'status': 'error', 'message': '请上传Markdown格式的文件'})
            
        # 保存上传的文件
        filename = secure_filename(file.filename)
        file_path = os.path.join('exports', filename)
        file.save(file_path)
        
        return jsonify({
            'status': 'success',
            'message': '文件上传成功',
            'filename': filename
        })
        
    except Exception as e:
        logger.error(f"处理文件上传失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'文件处理失败: {str(e)}'
        })

if __name__ == '__main__':
    try:
        # 下载NLTK数据
        print("正在下载NLTK数据...")
        nltk.download('punkt', quiet=True)
        print("NLTK数据下载完成")
        
        # 检查必要的配置
        if not DEEPSEEK_API_KEY:
            raise ValueError("未设置DEEPSEEK_API_KEY")
        
        print("正在启动应用服务器...")
        # 启动应用
        import uvicorn
        uvicorn.run(asgi_app, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"启动失败: {str(e)}")
        logger.error(f"启动失败: {str(e)}\n{traceback.format_exc()}")
        raise 