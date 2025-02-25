from flask import Flask, request, jsonify, render_template
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
from langchain_community.retrievers.pubmed import PubMedRetriever
from langchain_community.document_loaders.pubmed import PubMedLoader
import sys
import urllib.parse
from typing import List, Dict, Optional, Union
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from nltk.corpus import wordnet
import codecs
from journal_analyzer import JournalAnalyzer
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

# 加载环境变量
load_dotenv()

# 创建应用实例
app = Flask(__name__, template_folder='templates')

# 创建必要的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
EXPORTS_DIR = os.path.join(BASE_DIR, 'exports')
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, f'app_{datetime.now().strftime("%Y%m%d")}.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)  # 确保输出到标准输出
    ]
)
logger = logging.getLogger(__name__)

# 设置标准输出编码
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# 检查.env文件
env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_path):
    logger.info(f"找到.env文件: {env_path}")
    with open(env_path, 'r', encoding='utf-8') as f:
        env_content = f.read()
        logger.info(f"环境文件内容预览 (前100字符): {env_content[:100]}...")
else:
    logger.error(f"未找到.env文件: {env_path}")

# 加载环境变量
load_dotenv(env_path, verbose=True, override=True)

def get_api_config() -> Dict[str, str]:
    """
    获取API配置并验证
    
    Returns:
        Dict[str, str]: 包含API配置的字典
    
    Raises:
        ValueError: 当缺少必要的环境变量时
    """
    # 直接从环境变量中读取并打印所有相关变量
    env_vars = {
        'DEEPSEEK_API_KEY': os.getenv('DEEPSEEK_API_KEY'),
        'DEEPSEEK_MODEL': os.getenv('DEEPSEEK_MODEL'),
        'DEEPSEEK_API_URL': os.getenv('DEEPSEEK_API_URL'),
        'PUBMED_API_KEY': os.getenv('PUBMED_API_KEY'),
        'PUBMED_EMAIL': os.getenv('PUBMED_EMAIL'),
        'TOOL_NAME': os.getenv('TOOL_NAME'),
        'PUBMED_API_URL': os.getenv('PUBMED_API_URL'),
    }
    
    logger.info("环境变量读取结果:")
    for key, value in env_vars.items():
        if 'API_KEY' in key and value:
            logger.info(f"{key}: {value[:4]}...{value[-4:]}")
        else:
            logger.info(f"{key}: {value}")
    
    config = {
        'deepseek_key': env_vars['DEEPSEEK_API_KEY'],
        'deepseek_model': env_vars['DEEPSEEK_MODEL'] or 'deepseek-chat',
        'deepseek_url': env_vars['DEEPSEEK_API_URL'] or 'https://api.deepseek.com/v1/chat/completions',
        'pubmed_key': env_vars['PUBMED_API_KEY'],
        'pubmed_email': env_vars['PUBMED_EMAIL'],
        'tool_name': env_vars['TOOL_NAME'] or 'nnscholar_pubmed',
        'pubmed_url': env_vars['PUBMED_API_URL'] or 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    }
    
    # 验证必要的API密钥
    missing_keys = []
    if not config['deepseek_key']:
        missing_keys.append('DEEPSEEK_API_KEY')
    if not config['pubmed_key']:
        missing_keys.append('PUBMED_API_KEY')
    if not config['pubmed_email']:
        missing_keys.append('PUBMED_EMAIL')
        
    if missing_keys:
        raise ValueError(f"缺少必要的环境变量: {', '.join(missing_keys)}")
        
    return config

# 初始化API配置
try:
    API_CONFIG = get_api_config()
    DEEPSEEK_API_KEY = API_CONFIG['deepseek_key']
    DEEPSEEK_MODEL = API_CONFIG['deepseek_model']
    DEEPSEEK_API_URL = API_CONFIG['deepseek_url']
    PUBMED_API_KEY = API_CONFIG['pubmed_key']
    PUBMED_EMAIL = API_CONFIG['pubmed_email']
    TOOL_NAME = API_CONFIG['tool_name']
    PUBMED_BASE_URL = API_CONFIG['pubmed_url']
except Exception as e:
    logger.critical(f"API配置初始化失败: {str(e)}")
    raise

# 加载PubMed专家提示词模板
PROMPT_PATH = os.path.join(BASE_DIR, 'templates', 'pubmed_expert_prompt.md')
with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
    EXPERT_PROMPT = f.read()

# 加载期刊数据
def load_journal_data():
    """加载期刊相关数据"""
    data_dir = os.path.join(BASE_DIR, 'data', 'journal_metrics')
    journal_data = {}
    if_trend_data = {}
    
    try:
        # 加载JCR和中科院分区数据
        jcr_file = os.path.join(data_dir, 'jcr_cas_ifqb.json')
        if not os.path.exists(jcr_file):
            logger.error(f"期刊数据文件不存在: {jcr_file}")
            return {}, {}
            
        logger.info(f"开始加载期刊数据文件: {jcr_file}")
        with open(jcr_file, 'r', encoding='utf-8') as f:
            try:
                journal_list = json.load(f)
                logger.info(f"成功加载期刊数据，包含 {len(journal_list)} 条记录")
                
                # 记录一些原始数据示例
                if len(journal_list) > 0:
                    sample_raw = journal_list[:3]
                    logger.info(f"原始数据示例: {json.dumps(sample_raw, ensure_ascii=False)}")
                
                for journal in journal_list:
                    # 处理ISSN和eISSN
                    issn = journal.get('issn', '').strip()
                    eissn = journal.get('eissn', '').strip()
                    
                    # 标准化ISSN格式（移除连字符）
                    issn = issn.replace('-', '') if issn else None
                    eissn = eissn.replace('-', '') if eissn else None
                    
                    # 使用所有可能的ISSN作为键
                    issns = [i for i in [issn, eissn] if i]
                    
                    if issns:
                        # 处理影响因子，确保是数值类型
                        impact_factor = journal.get('IF', 'N/A')
                        try:
                            if impact_factor != 'N/A':
                                impact_factor = float(impact_factor)
                        except (ValueError, TypeError):
                            impact_factor = 'N/A'
                            logger.warning(f"无效的影响因子值: {journal.get('IF')} for {journal.get('journal')}")
                        
                        journal_info = {
                            'title': journal.get('journal', ''),
                            'if': impact_factor,
                            'jcr_quartile': journal.get('Q', 'N/A'),
                            'cas_quartile': journal.get('B', 'N/A')
                        }
                        
                        # 为每个ISSN都存储期刊信息
                        for issn_key in issns:
                            journal_data[issn_key] = journal_info
                
                logger.info(f"成功加载 {len(journal_data)} 条期刊数据")
                # 记录一些转换后的数据示例
                if journal_data:
                    sample_converted = {k: journal_data[k] for k in list(journal_data.keys())[:3]}
                    logger.info(f"转换后的数据示例: {json.dumps(sample_converted, ensure_ascii=False)}")
            except json.JSONDecodeError as e:
                logger.error(f"期刊数据文件格式错误: {str(e)}")
                return {}, {}
        
        # 加载五年影响因子趋势数据
        trend_file = os.path.join(data_dir, '5year.json')
        if os.path.exists(trend_file):
            logger.info(f"开始加载影响因子趋势数据: {trend_file}")
            with open(trend_file, 'r', encoding='utf-8') as f:
                try:
                    if_trend_data = json.load(f)
                    if not isinstance(if_trend_data, dict):
                        logger.error("影响因子趋势数据格式错误：应为字典类型")
                        if_trend_data = {}
                    else:
                        logger.info(f"成功加载影响因子趋势数据，包含 {len(if_trend_data)} 条记录")
                except json.JSONDecodeError as e:
                    logger.error(f"影响因子趋势数据文件格式错误: {str(e)}")
                    if_trend_data = {}
        else:
            logger.warning(f"影响因子趋势数据文件不存在: {trend_file}")
        
        return journal_data, if_trend_data
        
    except Exception as e:
        logger.error(f"加载期刊数据失败: {str(e)}\n{traceback.format_exc()}")
        return {}, {}

# 全局变量
try:
    JOURNAL_DATA, IF_TREND_DATA = load_journal_data()
except Exception as e:
    logger.error(f"加载期刊数据失败: {str(e)}")
    JOURNAL_DATA, IF_TREND_DATA = {}, {}

def get_journal_metrics(issn):
    """获取期刊指标数据"""
    try:
        if not issn:
            logger.warning("ISSN为空")
            return None
            
        logger.info(f"开始获取期刊指标，ISSN: {issn}")
        
        if not isinstance(JOURNAL_DATA, dict):
            logger.error(f"期刊数据格式错误: {type(JOURNAL_DATA)}")
            return None
            
        if len(JOURNAL_DATA) == 0:
            logger.warning("期刊数据为空，请检查数据文件是否正确加载")
            return None
            
        # 标准化ISSN格式（移除连字符）
        issn = issn.replace('-', '')
        
        # 尝试直接获取
        journal_info = JOURNAL_DATA.get(issn)
        
        if not journal_info:
            # 尝试其他格式的ISSN
            issn_with_hyphen = f"{issn[:4]}-{issn[4:]}"
            journal_info = JOURNAL_DATA.get(issn_with_hyphen)
        
        if not journal_info:
            logger.warning(f"未找到ISSN对应的期刊信息: {issn}")
            return None
            
        logger.info(f"获取到的原始期刊信息: {json.dumps(journal_info, ensure_ascii=False)}")
        
        # 处理影响因子的显示格式
        impact_factor = journal_info.get('if', 'N/A')
        if isinstance(impact_factor, (int, float)):
            impact_factor = f"{impact_factor:.3f}"  # 格式化为三位小数
        
        metrics = {
            'title': journal_info.get('title', ''),
            'impact_factor': impact_factor,
            'jcr_quartile': journal_info.get('jcr_quartile', 'N/A'),
            'cas_quartile': journal_info.get('cas_quartile', 'N/A')
        }
        
        logger.info(f"处理后的期刊指标: {json.dumps(metrics, ensure_ascii=False)}")
        return metrics
        
    except Exception as e:
        logger.error(f"获取期刊指标时发生错误: {str(e)}\n{traceback.format_exc()}")
        return None

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
        if ('year_start' in filters and filters['year_start'] and 
            'year_end' in filters and filters['year_end']):
            year_start = int(filters['year_start'])
            year_end = int(filters['year_end'])
            logger.debug(f"应用年份筛选，范围: {year_start}-{year_end}")
            for paper in papers:
                pub_year = paper.get('pub_year')
                try:
                    pub_year = int(pub_year) if pub_year else None
                    if pub_year and year_start <= pub_year <= year_end:
                        year_filtered.append(paper)
                except (ValueError, TypeError) as e:
                    logger.warning(f"年份格式错误: {pub_year}, 错误信息: {str(e)}")
        else:
            year_filtered = papers.copy()
        stats['year_filtered'] = len(year_filtered)
        logger.info(f"1. 年份筛选 ({filters.get('year_start', '无')} - {filters.get('year_end', '无')}): {len(papers)} -> {len(year_filtered)}")
        
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
                        cas_q = cas_q[1:]
                    if cas_q in cas_filters:
                        cas_filtered.append(paper)
        else:
            cas_filtered = jcr_filtered.copy()
        stats['cas_filtered'] = len(cas_filtered)
        logger.info(f"4. CAS分区筛选 ({filters.get('cas_quartile', '无限制')}): {len(jcr_filtered)} -> {len(cas_filtered)}")
        
        # 5. 计算综合得分并排序
        # 单句模式下，相关性权重为0.7，影响因子权重为0.3
        for paper in cas_filtered:
            relevance = float(paper.get('relevance', 0))
            journal_info = paper.get('journal_info', {})
            impact_factor = journal_info.get('impact_factor', 'N/A')
            
            try:
                if impact_factor != 'N/A':
                    if isinstance(impact_factor, str):
                        impact_factor = float(impact_factor.replace(',', ''))
                    # 将影响因子归一化到0-100的范围（假设最高影响因子为50）
                    if_score = min(100, (float(impact_factor) / 50) * 100)
                else:
                    if_score = 0
            except (ValueError, TypeError):
                if_score = 0
            
            # 计算综合得分
            paper['composite_score'] = (relevance * 0.7) + (if_score * 0.3)
            logger.debug(f"文献 {paper.get('pmid')} 的综合得分: {paper['composite_score']:.1f} (相关性: {relevance:.1f}, IF得分: {if_score:.1f})")
        
        # 按综合得分排序
        filtered_papers = sorted(
            cas_filtered,
            key=lambda x: x.get('composite_score', 0),
            reverse=True
        )
        
        # 限制返回数量
        try:
            papers_limit = int(filters.get('papers_limit', 10))  # 确保转换为整数
        except (ValueError, TypeError) as e:
            logger.warning(f"无效的papers_limit值，使用默认值10。错误: {str(e)}")
            papers_limit = 10
        papers = filtered_papers[:papers_limit]
        
        stats['final'] = len(papers)
        
        # 输出详细的筛选统计信息
        logger.info("\n筛选过程统计:")
        logger.info(f"初始文献数量: {stats['total']}")
        logger.info(f"1. 年份筛选后: {stats['year_filtered']} 篇")
        logger.info(f"2. 影响因子筛选后: {stats['if_filtered']} 篇")
        logger.info(f"3. JCR分区筛选后: {stats['jcr_filtered']} 篇")
        logger.info(f"4. CAS分区筛选后: {stats['cas_filtered']} 篇")
        logger.info(f"5. 最终结果: {stats['final']} 篇")
        
        return papers, stats
        
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

def call_deepseek_api(prompt):
    """调用DeepSeek API进行文本处理"""
    # 记录API密钥前三位用于调试
    if DEEPSEEK_API_KEY:
        logger.info(f"DeepSeek API密钥前三位: {DEEPSEEK_API_KEY[:3]}...")
    else:
        logger.error("DeepSeek API密钥未设置")
        
    headers = {
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'model': DEEPSEEK_MODEL,
        'messages': [
            {'role': 'system', 'content': EXPERT_PROMPT},
            {'role': 'user', 'content': prompt}
        ]
    }
    
    try:
        logger.info(f"调用DeepSeek API，模型: {DEEPSEEK_MODEL}, URL: {DEEPSEEK_API_URL}")
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=data
        )
        
        # 检查HTTP状态码
        response.raise_for_status()
        
        # 解析JSON响应
        response_data = response.json()
        
        # 记录完整响应用于调试
        logger.debug(f"DeepSeek API响应: {response_data}")
        
        # 验证响应格式
        if 'choices' not in response_data:
            error_msg = response_data.get('error', {}).get('message', '未知错误')
            logger.error(f"DeepSeek API返回格式错误: {error_msg}")
            raise ValueError(f"DeepSeek API错误: {error_msg}")
            
        return response_data['choices'][0]['message']['content']
        
    except requests.exceptions.RequestException as e:
        logger.error(f"调用DeepSeek API时发生网络错误: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"处理DeepSeek API响应时发生错误: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"调用DeepSeek API时发生未预期的错误: {str(e)}")
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
            if pub_date:
                # 尝试从Year标签提取
                year_elem = pub_date.find('year')
                if year_elem and year_elem.text:
                    try:
                        pub_year = int(year_elem.text)
                        logger.info(f"成功提取发表年份: {pub_year}")
                    except ValueError:
                        logger.warning(f"无效的年份格式: {year_elem.text}")
                else:
                    # 尝试从MedlineDate中提取
                    medline_date = pub_date.find('medlinedate')
                    if medline_date and medline_date.text:
                        try:
                            # 提取第一个四位数字作为年份
                            year_match = re.search(r'\b\d{4}\b', medline_date.text)
                            if year_match:
                                pub_year = int(year_match.group())
                                logger.info(f"从MedlineDate提取到年份: {pub_year}")
                        except ValueError:
                            logger.warning(f"无法从MedlineDate提取年份: {medline_date.text}")
            
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
                    metrics = get_journal_metrics(issn)
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
                'pub_year': pub_year,  # 确保年份被正确存储
                'pmid': article.find('pmid').text if article.find('pmid') else '',
                'url': f'https://pubmed.ncbi.nlm.nih.gov/{article.find("pmid").text}/' if article.find('pmid') else '#',
                'journal_info': journal_info,
                'journal_issn': journal_info.get('issn', '')
            }
            
            logger.info(f"文章数据构建完成: PMID={article_data['pmid']}, 年份={article_data['pub_year']}")
            articles.append(article_data)
            
        except Exception as e:
            logger.error(f"解析第 {i} 篇文章时发生错误: {str(e)}\n{traceback.format_exc()}")
            continue
    
    logger.info(f"完成XML解析，成功解析 {len(articles)}/{article_count} 篇文章")
    return articles

# 初始化全局变量
model = None

def preprocess_text(text):
    """文本预处理函数
    
    Args:
        text (str): 输入文本
        
    Returns:
        str: 预处理后的文本
    """
    if not text:
        return ""
        
    # 转换为小写
    text = text.lower()
    
    # 移除标点符号
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # 移除多余空格
    text = re.sub(r'\s+', ' ', text)
    
    # 移除数字
    text = re.sub(r'\d+', '', text)
    
    return text.strip()

def calculate_rule_based_relevance(sentence, paper):
    """基于规则的相关性计算"""
    try:
        # 文本预处理
        query = preprocess_text(sentence)
        title = preprocess_text(paper.get('title', ''))
        abstract = preprocess_text(paper.get('abstract', ''))
        
        logger.info(f"\n开始计算文献相关度:")
        logger.info(f"文献标题: {title}")
        logger.info(f"文献摘要: {abstract[:200]}...")
        
        # 从查询中提取关键词组
        key_phrases = [phrase.strip() for phrase in re.split(r'[与和及]', query) if phrase.strip()]
        logger.info(f"从查询中提取的关键词组: {key_phrases}")
        
        # 为每个关键词组定义可能的变体
        key_terms = {}
        for phrase in key_phrases:
            # 将中文关键词转换为对应的英文变体
            if any(term in phrase.lower() for term in ["慢性肾病", "ckd", "chronic kidney"]):
                key_terms["CKD"] = ["chronic kidney disease", "ckd", "chronic renal disease", "chronic kidney failure", "kidney disease"]
            elif any(term in phrase.lower() for term in ["斑块", "plaque", "高危斑块"]):
                key_terms["plaque"] = ["plaque", "atherosclerotic plaque", "coronary plaque", "high risk plaque", "vulnerable plaque", "high-risk plaque", "atherosclerosis"]
            elif any(term in phrase.lower() for term in ["冠脉", "冠状动脉", "coronary"]):
                key_terms["coronary"] = ["coronary", "coronary artery", "coronary arteries", "coronary vessel"]
            else:
                # 对于其他关键词,保留原词并添加一些常见变体
                base_term = phrase.lower()
                key_terms[base_term] = [base_term]
                # 添加词形变化
                if base_term.endswith('y'):
                    key_terms[base_term].append(base_term[:-1] + 'ies')
                elif not base_term.endswith('s'):
                    key_terms[base_term].append(base_term + 's')
        
        if not key_terms:
            logger.warning(f"未能提取到核心概念,原始查询: {query}")
            return 0.0
            
        logger.info("\n核心概念及其变体:")
        for concept, variations in key_terms.items():
            logger.info(f"- {concept}: {variations}")
        
        # 计算标题中关键词组的匹配情况
        title_matched_terms = set()
        title_matched_variations = {}  # 记录每个核心概念在标题中匹配到的变体
        
        logger.info("\n标题匹配分析:")
        # 记录每个概念在标题中的匹配情况
        for term_group, variations in key_terms.items():
            title_matched_variations[term_group] = []
            for variation in variations:
                if any(word.lower() == variation.lower() for word in title.split()) or \
                   re.search(r'\b' + re.escape(variation.lower()) + r'\b', title.lower()):
                    title_matched_terms.add(term_group)
                    title_matched_variations[term_group].append(variation)
                    logger.info(f"[MATCH] 概念 '{term_group}' 在标题中匹配到变体: '{variation}'")
                else:
                    logger.info(f"[NO MATCH] 概念 '{term_group}' 的变体 '{variation}' 未在标题中匹配")
        
        # 计算摘要中关键词组的匹配情况
        abstract_matched_terms = set()
        abstract_matched_variations = {}  # 记录每个核心概念在摘要中匹配到的变体
        
        logger.info("\n摘要匹配分析:")
        for term_group, variations in key_terms.items():
            abstract_matched_variations[term_group] = []
            for variation in variations:
                if variation.lower() in abstract.lower():
                    abstract_matched_terms.add(term_group)
                    abstract_matched_variations[term_group].append(variation)
                    logger.info(f"[MATCH] 概念 '{term_group}' 在摘要中匹配到变体: '{variation}'")
                else:
                    logger.info(f"[NO MATCH] 概念 '{term_group}' 的变体 '{variation}' 未在摘要中匹配")
        
        # 计算基础分数
        base_score = 0.0
        total_concepts = len(key_terms)
        title_match_count = len(title_matched_terms)
        
        # 标题匹配分数计算
        logger.info("\n分数计算详情:")
        if title_match_count > 0:
            # 为每个在标题中匹配到的核心概念加30分
            base_score = title_match_count * 30.0
            logger.info(f"标题匹配基础得分: {base_score:.1f} (每个概念30分 × {title_match_count}个概念)")
            for term in title_matched_terms:
                logger.info(f"- 概念 '{term}' 在标题中匹配 (得分: 30.0)")
                logger.info(f"  匹配到的变体: {', '.join(title_matched_variations[term])}")
        else:
            logger.info("标题中未匹配到任何核心概念，基础得分: 0.0")
        
        # 计算摘要中出现的额外概念
        extra_concepts_in_abstract = abstract_matched_terms - title_matched_terms
        extra_score = len(extra_concepts_in_abstract) * 10.0
        
        if extra_concepts_in_abstract:
            logger.info(f"\n摘要额外得分: {extra_score:.1f} (每个概念10分 × {len(extra_concepts_in_abstract)}个概念)")
            for term in extra_concepts_in_abstract:
                logger.info(f"- 概念 '{term}' 仅在摘要中匹配 (得分: 10.0)")
                logger.info(f"  匹配到的变体: {', '.join(abstract_matched_variations[term])}")
        else:
            logger.info("\n摘要中无额外匹配概念，额外得分: 0.0")
        
        # 计算最终分数
        final_score = base_score + extra_score
        
        # 确保分数不超过100
        final_score = min(100.0, final_score)
        
        logger.info(f"\n最终得分计算:")
        logger.info(f"- 标题匹配得分: {base_score:.1f}")
        logger.info(f"- 摘要额外得分: {extra_score:.1f}")
        logger.info(f"- 总分: {final_score:.1f}")
        
        return final_score
        
    except Exception as e:
        logger.error(f"基于规则的相关性计算时出错: {str(e)}")
        return 0.0

def calculate_relevance_improved(sentence, paper):
    """改进的相关性计算方法,暂时只使用规则based评分"""
    try:
        # 获取规则based的相关度分数
        rule_score = calculate_rule_based_relevance(sentence, paper)
        
        # 直接返回规则分数
        final_score = rule_score
        
        # 确保分数在0-100之间
        final_score = max(0.0, min(100.0, final_score))
        
        logger.info(f"相关度计算结果:")
        logger.info(f"- 规则分数: {final_score:.1f}")
        
        return round(final_score, 1)
        
    except Exception as e:
        logger.error(f"计算相关性时出错: {str(e)}")
        return 0.0

def search_pubmed(query, max_results=3000):
    """直接使用PubMed API搜索文献"""
    try:
        logger.info(f"开始PubMed搜索，检索策略: {query}, 最大结果数: {max_results}")
        
        # 如果输入的是完整的检索策略，直接使用
        if '[' in query and ']' in query:
            search_strategy = query
            logger.info(f"使用提供的完整检索策略: {search_strategy}")
        else:
            # 否则生成检索策略
            prompt = """作为PubMed搜索专家，请为以下研究内容生成优化的PubMed检索策略：

研究内容：{query}

要求：
1. 提取2-3个核心概念，每个概念扩展：
   - 首选缩写（如有）
   - 全称术语
   - 相近术语和同义词
   - 仅返回检索策略，不要其他解释

2. 结构要求：
   (
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract]) 
     AND 
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract])
   )

3. 强制规则：
   - 每个概念最多3个术语（缩写+全称+同义词）
   - 只使用Title/Abstract字段，不使用MeSH
   - 保持AND连接的逻辑组不超过3组
   - 使用精确匹配，所有术语都要加双引号"""

            try:
                logger.info("生成检索策略...")
                search_strategy = call_deepseek_api(prompt.format(query=query))
                logger.info(f"生成的检索策略: {search_strategy}")
            except Exception as e:
                logger.warning(f"DeepSeek API调用失败，使用基本搜索策略: {str(e)}")
                search_strategy = f'"{query}"[All Fields]'
                logger.info(f"使用基本搜索策略: {search_strategy}")

        # 构建PubMed搜索请求
        search_params = {
            'db': 'pubmed',
            'term': search_strategy,
            'retmax': str(max_results),
            'retmode': 'json',
            'api_key': PUBMED_API_KEY
        }
        
        # 发送搜索请求
        search_url = f"{PUBMED_BASE_URL}esearch.fcgi"
        response = requests.get(search_url, params=search_params)
        
        if response.status_code != 200:
            logger.error(f"PubMed搜索请求失败: HTTP {response.status_code}")
            return [], search_strategy, 0, 0
            
        search_result = response.json()
        total_count = int(search_result.get('esearchresult', {}).get('count', 0))
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
                total_count = int(search_result.get('esearchresult', {}).get('count', 0))
                id_list = search_result.get('esearchresult', {}).get('idlist', [])
        
        if not id_list:
            logger.warning("所有搜索策略均未找到文献")
            return [], search_strategy, 0, 0
            
        logger.info(f"找到 {len(id_list)} 篇文献")
        
        # 使用分批处理获取文献详情
        papers = fetch_paper_details(id_list)
        
        if not papers:
            logger.warning("未能获取任何文献详情")
            return [], search_strategy, total_count, 0
            
        logger.info(f"成功获取 {len(papers)} 篇文献的详细信息")
        return papers, search_strategy, total_count, len(papers)
        
    except Exception as e:
        logger.error(f"PubMed搜索过程中发生错误: {str(e)}\n{traceback.format_exc()}")
        return [], None, 0, 0

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

def fetch_paper_details(id_list):
    """分批获取文献详细信息"""
    try:
        if not id_list:
            return []
            
        # 将ID列表分成较小的批次，每批300个ID
        batch_size = 300
        all_papers = []
        total_batches = (len(id_list) + batch_size - 1) // batch_size
        
        logger.info(f"开始获取文献详情，共 {len(id_list)} 篇文献，分 {total_batches} 批处理")
        
        for i in range(0, len(id_list), batch_size):
            batch_ids = id_list[i:i+batch_size]
            current_batch = i // batch_size + 1
            logger.info(f"正在处理第 {current_batch}/{total_batches} 批文献 ({len(batch_ids)} 篇)")
            
            # 构建请求参数
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(batch_ids),
                'retmode': 'xml',
                'api_key': PUBMED_API_KEY
            }
            
            # 发送请求获取详情
            fetch_url = f"{PUBMED_BASE_URL}efetch.fcgi"
            response = requests.get(fetch_url, params=fetch_params)
            
            if response.status_code == 200:
                # 解析XML响应
                papers = parse_pubmed_xml(response.content)
                all_papers.extend(papers)
                logger.info(f"✓ 第 {current_batch}/{total_batches} 批完成，成功获取 {len(papers)} 篇文献")
                logger.info(f"当前进度: {len(all_papers)}/{len(id_list)} 篇 ({(len(all_papers)/len(id_list)*100):.1f}%)")
            else:
                logger.error(f"✗ 第 {current_batch}/{total_batches} 批失败: HTTP {response.status_code}")
            
            # 添加短暂延时，避免请求过于频繁
            if current_batch < total_batches:  # 最后一批不需要延时
                time.sleep(0.5)
        
        logger.info(f"文献获取完成，共处理 {len(all_papers)}/{len(id_list)} 篇文献")
        return all_papers
        
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
                try:
                    pub_year = int(year_elem.text)
                    logger.info(f"成功提取发表年份: {pub_year}")
                except ValueError:
                    logger.warning(f"无效的年份格式: {year_elem.text}")
            else:
                # 尝试从MedlineDate中提取
                medline_date = pub_date.find('MedlineDate')
                if medline_date and medline_date.text:
                    try:
                        # 提取第一个四位数字作为年份
                        year_match = re.search(r'\b\d{4}\b', medline_date.text)
                        if year_match:
                            pub_year = int(year_match.group())
                            logger.info(f"从MedlineDate提取到年份: {pub_year}")
                    except ValueError:
                        logger.warning(f"无法从MedlineDate提取年份: {medline_date.text}")
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
        journal_metrics = get_journal_metrics(issn)
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
        all_papers, search_strategy, total_count, filtered_count = search_pubmed(sentence)
        
        # 为所有文献计算相关性得分并排序
        for paper in all_papers:
            paper['relevance'] = calculate_relevance_improved(sentence, paper)
        all_papers.sort(key=lambda x: x['relevance'], reverse=True)
        
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
            search_prompt = f"""作为PubMed搜索专家，请为以下研究内容生成优化的PubMed检索策略：

研究内容：{short_sent}

要求：
1. 提取2-3个核心概念，每个概念扩展：
   - 首选缩写（如有）
   - 全称术语
   - 相近术语和同义词
   - 仅返回检索策略，不要其他解释

2. 结构要求：
   (
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract]) 
     AND 
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract])
   )

3. 强制规则：
   - 每个概念最多3个术语（缩写+全称+同义词）
   - 只使用Title/Abstract字段，不使用MeSH
   - 保持AND连接的逻辑组不超过3组
   - 使用精确匹配，所有术语都要加双引号"""

            search_strategy = call_deepseek_api(search_prompt)
            
            # 解析检索策略并搜索文献
            papers = search_pubmed(short_sent)
            
            # 计算相关性并排序
            for paper in papers:
                paper['relevance'] = calculate_relevance_improved(short_sent, paper)
            papers.sort(key=lambda x: x['relevance'], reverse=True)
            
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

def export_papers_to_excel(papers, query, file_suffix=''):
    """
    将文献信息导出为Excel表格
    :param papers: 文献列表
    :param query: 搜索关键词
    :param file_suffix: 文件名后缀（用于区分初始结果和筛选结果）
    :return: 导出文件的路径
    """
    try:
        # 为每篇文献计算相关度分数
        for paper in papers:
            if 'relevance' not in paper:
                paper['relevance'] = calculate_relevance_improved(query, paper)

        # 准备数据
        data = []
        for paper in papers:
            journal_info = paper.get('journal_info', {})
            paper_data = {
                '标题': paper.get('title', ''),
                '摘要': paper.get('abstract', ''),
                '作者': ', '.join(paper.get('authors', [])),
                '发表年份': paper.get('pub_year', ''),
                '期刊名称': paper.get('journal', {}).get('title', ''),
                '影响因子': journal_info.get('impact_factor', 'N/A'),
                'JCR分区': journal_info.get('jcr_quartile', 'N/A'),
                'CAS分区': journal_info.get('cas_quartile', 'N/A'),
                'DOI': paper.get('doi', ''),
                'PMID': paper.get('pmid', ''),
                '相关度': f"{paper.get('relevance', 0):.1f}%"
            }
            data.append(paper_data)
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"papers_{query.replace(' ', '_')}_{file_suffix}_{timestamp}.xlsx"
        filepath = os.path.join(EXPORTS_DIR, filename)
        
        # 导出到Excel
        df.to_excel(filepath, index=False, engine='openpyxl')
        logger.info(f"成功导出文献信息到: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"导出Excel文件时发生错误: {str(e)}")
        return None

def export_papers_to_word(papers, query, file_suffix=''):
    """
    将论文信息导出为Word文档
    
    Args:
        papers (list): 论文信息列表
        query (str): 搜索查询
        file_suffix (str): 文件名后缀
    
    Returns:
        str: 导出文件的路径
    """
    try:
        # 创建Word文档
        doc = Document()
        
        # 添加标题
        title = doc.add_heading('文献检索报告', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 添加检索信息
        doc.add_paragraph(f'检索词：{query}')
        doc.add_paragraph(f'检索时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        doc.add_paragraph(f'检索到的文献数量：{len(papers)}')
        
        # 添加文献列表
        doc.add_heading('文献列表', level=1)
        
        for i, paper in enumerate(papers, 1):
            # 获取期刊信息
            journal_info = paper.get('journal_info', {})
            
            # 添加文献标题
            p = doc.add_paragraph()
            p.add_run(f'{i}. ').bold = True
            title_run = p.add_run(paper.get('title', 'N/A'))
            title_run.bold = True
            
            # 添加作者信息
            authors_str = ', '.join(paper.get('authors', [])) if paper.get('authors') else 'N/A'
            doc.add_paragraph(f'作者：{authors_str}')
            
            # 添加期刊信息
            doc.add_paragraph(f'期刊：{journal_info.get("title", "N/A")}')
            doc.add_paragraph(f'发表时间：{paper.get("pub_date", "N/A")}')
            
            # 添加影响因子和分区信息
            doc.add_paragraph(f'影响因子：{journal_info.get("impact_factor", "N/A")}')
            doc.add_paragraph(f'JCR分区：{journal_info.get("jcr_quartile", "N/A")}')
            doc.add_paragraph(f'CAS分区：{journal_info.get("cas_quartile", "N/A")}')
            
            # 添加DOI和PMID
            doc.add_paragraph(f'DOI：{paper.get("doi", "N/A")}')
            doc.add_paragraph(f'PMID：{paper.get("pmid", "N/A")}')
            
            # 添加相关度信息
            relevance = paper.get('relevance', 0)
            if isinstance(relevance, (int, float)):
                doc.add_paragraph(f'相关度：{relevance:.1f}%')
            else:
                doc.add_paragraph(f'相关度：{relevance}')
            
            # 添加摘要
            if paper.get('abstract'):
                doc.add_paragraph('摘要：').bold = True
                doc.add_paragraph(paper.get('abstract'))
            
            # 添加分隔线
            if i < len(papers):
                doc.add_paragraph('_' * 50)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'papers_{query}{file_suffix}_{timestamp}.docx'
        filepath = os.path.join(EXPORTS_DIR, filename)
        
        # 保存文档
        doc.save(filepath)
        logger.info(f'成功导出Word文档：{filepath}')
        
        return filepath
        
    except Exception as e:
        logger.error(f'导出Word文档失败：{str(e)}\n{traceback.format_exc()}')
        return None

def export_papers(papers, query, file_suffix=''):
    """
    将论文信息同时导出为Excel和Word格式
    
    Args:
        papers (list): 论文信息列表
        query (str): 搜索查询
        file_suffix (str): 文件名后缀
    
    Returns:
        tuple: (excel_path, word_path) 导出文件的路径
    """
    try:
        # 导出Excel
        excel_path = export_papers_to_excel(papers, query, file_suffix)
        
        # 导出Word
        word_path = export_papers_to_word(papers, query, file_suffix)
        
        return excel_path, word_path
        
    except Exception as e:
        logger.error(f'导出文件失败：{str(e)}\n{traceback.format_exc()}')
        return None, None

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search():
    """处理搜索请求"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        mode = data.get('mode', 'single')
        generate_only = data.get('generate_only', True)
        execute_search = data.get('execute_search', False)
        filters = data.get('filters', {})
        papers_per_sentence = int(data.get('papers_per_sentence', 10))
        year_start = data.get('year_start')
        year_end = data.get('year_end')
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请输入检索内容'
            }), 400
            
        if mode == 'paragraph':
            # 段落模式处理
            sentences = split_paragraph_to_sentences(query)
            if not sentences:
                return jsonify({
                    'success': True,
                    'sentences': []
                })
            
            # 处理每个句子
            results = []
            for sentence in sentences:
                papers, search_strategy = analyze_sentence(sentence, papers_per_sentence, year_start, year_end)
                if papers:
                    results.append({
                        'text': sentence,
                        'papers': papers,
                        'search_strategy': search_strategy
                    })
            
            return jsonify({
                'success': True,
                'sentences': results
            })
        else:
            # 单句模式处理
            if generate_only:
                # 生成检索策略
                prompt = f"""作为PubMed搜索专家，请为以下研究内容生成优化的PubMed检索策略：

研究内容：{query}

要求：
1. 提取2-3个核心概念，每个概念扩展：
   - 首选缩写（如有）
   - 全称术语
   - 相近术语和同义词
   - 仅返回检索策略，不要其他解释

2. 结构要求：
   (
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract]) 
     AND 
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract])
   )

3. 强制规则：
   - 每个概念最多3个术语（缩写+全称+同义词）
   - 只使用Title/Abstract字段，不使用MeSH
   - 保持AND连接的逻辑组不超过3组
   - 使用精确匹配，所有术语都要加双引号"""
                search_strategy = call_deepseek_api(prompt)
                
                if year_start and year_end:
                    search_strategy += f" AND (\"{year_start}\"[Date - Publication] : \"{year_end}\"[Date - Publication])"
                    
                return jsonify({
                    'success': True,
                    'search_strategy': search_strategy
                })
            
            elif execute_search:
                # 执行检索
                search_strategy = data.get('search_strategy', '')
                if not search_strategy:
                    return jsonify({
                        'success': False,
                        'error': '检索策略不能为空'
                    }), 400
                
                # 执行PubMed搜索
                papers, _, total_count, filtered_count = search_pubmed(search_strategy)
                
                # 应用筛选条件
                if filters:
                    papers, stats = filter_papers_by_metrics(papers, filters)
                    filtered_count = stats['final']
                
                return jsonify({
                    'success': True,
                    'data': papers,
                    'total_count': total_count,
                    'filtered_count': filtered_count,
                    'original_papers': papers  # 保存原始未筛选的文献，供导出时使用
                })
            
    except Exception as e:
        logger.error(f"搜索过程中出现错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def split_paragraph_to_sentences(paragraph):
    """使用 NLTK 将段落分解为句子"""
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
                        sentences.append(sentence)
                    current_sentence = ""
            
            # 处理最后一个可能没有结束标点的句子
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
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
        return [s.strip() for s in re.split('[.。!！?？;；]+', paragraph) if s.strip()]

def analyze_sentence(sentence, papers_per_sentence=10, year_start=None, year_end=None):
    """分析单个句子并返回相关文献
    
    Args:
        sentence (str): 要分析的句子
        papers_per_sentence (int): 每个句子返回的文献数量
        year_start (str): 起始年份
        year_end (str): 结束年份
        
    Returns:
        tuple: (papers, search_strategy) 相关文献列表和检索策略
    """
    try:
        # 首先生成检索策略
        prompt = f"""作为PubMed搜索专家，请为以下研究内容生成优化的PubMed检索策略：

研究内容：{sentence}

要求：
1. 提取2-3个核心概念，每个概念扩展：
   - 首选缩写（如有）
   - 全称术语
   - 相近术语和同义词
   - 仅返回检索策略，不要其他解释

2. 结构要求：
   (
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract]) 
     AND 
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract])
   )

3. 强制规则：
   - 每个概念最多3个术语（缩写+全称+同义词）
   - 只使用Title/Abstract字段，不使用MeSH
   - 保持AND连接的逻辑组不超过3组
   - 使用精确匹配，所有术语都要加双引号"""

        search_strategy = call_deepseek_api(prompt)
        logger.info(f"为句子生成检索策略: {search_strategy}")

        # 如果提供了年份范围，添加年份限制条件
        if year_start and year_end:
            search_strategy += f" AND (\"{year_start}\"[Date - Publication] : \"{year_end}\"[Date - Publication])"
            logger.info(f"添加年份限制条件: {search_strategy}")

        # 使用生成的检索策略搜索文献
        papers, _, _, _ = search_pubmed(search_strategy)
        if not papers:
            return [], search_strategy
        
        # 为每篇文献获取期刊指标信息
        for paper in papers:
            # 确保journal_info存在
            if 'journal_info' not in paper:
                issn = paper.get('journal_issn')
                if issn:
                    metrics = get_journal_metrics(issn)
                    if metrics:
                        paper['journal_info'] = metrics
                    else:
                        paper['journal_info'] = {
                            'title': paper.get('journal', {}).get('title', 'N/A'),
                            'impact_factor': 'N/A',
                            'jcr_quartile': 'N/A',
                            'cas_quartile': 'N/A'
                        }
        
        # 计算每篇文献的相关度和综合得分
        for paper in papers:
            # 计算相关度得分 (0-100)
            relevance_score = calculate_relevance_improved(sentence, paper)
            paper['relevance'] = relevance_score
            
            # 计算影响因子得分 (0-100)
            impact_factor = paper.get('journal_info', {}).get('impact_factor', 'N/A')
            if impact_factor != 'N/A':
                try:
                    if isinstance(impact_factor, str):
                        impact_factor = float(impact_factor.replace(',', ''))
                    # 将影响因子归一化到0-100的范围（假设最高影响因子为50）
                    if_score = min(100, (float(impact_factor) / 50) * 100)
                except (ValueError, TypeError):
                    if_score = 0
            else:
                if_score = 0
            
            # 在段落模式下，影响因子权重为0.7，相关度权重为0.3
            paper['composite_score'] = (if_score * 0.7) + (relevance_score * 0.3)
            logger.debug(f"文献 {paper.get('pmid')} 的综合得分: {paper['composite_score']:.1f} (相关度得分: {relevance_score:.1f}, 影响因子得分: {if_score:.1f})")
        
        # 按综合得分排序
        papers.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
        
        # 返回指定数量的文献和检索策略
        return papers[:papers_per_sentence], search_strategy
        
    except Exception as e:
        logger.error(f"分析句子时出现错误: {str(e)}")
        return [], None

def calculate_similarity(text1, text2):
    """计算两段文本的相似度（简单实现）"""
    try:
        # 将文本转换为小写并分词
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # 计算 Jaccard 相似度
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0
        
    except Exception as e:
        logger.error(f"计算相似度时出现错误: {str(e)}")
        return 0

@app.route('/api/metrics/<issn>')
def get_metrics(issn):
    """获取期刊指标API端点"""
    try:
        metrics = get_journal_metrics(issn)
        if not metrics:
            return jsonify({
                'success': False,
                'error': '未找到期刊指标数据'
            }), 404
            
        return jsonify({
            'success': True,
            'data': metrics
        })
        
    except Exception as e:
        logger.error(f"获取期刊指标出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'获取期刊指标出错: {str(e)}'
        }), 500

@app.route('/api/trend/<issn>')
def get_trend(issn):
    """获取期刊影响因子趋势API端点"""
    try:
        trend_data = get_if_trend(issn)
        if not trend_data:
            return jsonify({
                'success': False,
                'error': '未找到影响因子趋势数据'
            }), 404
            
        return jsonify({
            'success': True,
            'data': trend_data
        })
        
    except Exception as e:
        logger.error(f"获取影响因子趋势出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'获取影响因子趋势出错: {str(e)}'
        }), 500

def expand_keywords(keywords):
    """
    扩展关键词，只处理缩写和全称的转换
    
    Args:
        keywords (str): 用逗号分隔的关键词字符串
        
    Returns:
        str: 扩展后的PubMed检索策略
    """
    if not keywords:
        return ""
        
    # 分割关键词
    keyword_list = [k.strip() for k in keywords.split(',')]
    expanded_terms = []
    
    for keyword in keyword_list:
        if not keyword:
            continue
            
        # 调用DeepSeek API进行扩展
        prompt = f"""作为PubMed检索专家，请为以下关键词生成检索策略，只考虑缩写和全称的转换，不要添加额外相关概念：

关键词：{keyword}

要求：
1. 只扩展缩写和全称的对应关系，例如：
   - "LLM" -> ("LLM"[Title/Abstract] OR "Large Language Model"[Title/Abstract])
   - "CT" -> ("CT"[Title/Abstract] OR "Computed Tomography"[Title/Abstract])
2. 不要添加其他相关概念或同义词
3. 使用Title/Abstract字段
4. 所有术语都要加双引号
5. 直接返回检索策略，不要其他解释"""

        try:
            expanded = call_deepseek_api(prompt)
            expanded_terms.append(expanded)
        except Exception as e:
            logger.warning(f"扩展关键词 {keyword} 时出错: {str(e)}")
            # 如果扩展失败，使用原始关键词
            expanded_terms.append(f'"{keyword}"[Title/Abstract]')
    
    # 将所有扩展后的词组用 AND 连接
    if expanded_terms:
        return " AND ".join(expanded_terms)
    return ""

@app.route('/api/analyze-journal', methods=['POST'])
def analyze_journal():
    """期刊分析API端点"""
    try:
        data = request.get_json()
        journal = data.get('journal')
        keywords = data.get('keywords', '').strip()  # 可选参数
        start_year = data.get('start_year')
        end_year = data.get('end_year')
        
        if not all([journal, start_year, end_year]):
            return jsonify({
                'success': False,
                'error': '缺少必要的参数'
            }), 400
            
        logger.info(f"开始分析期刊: {journal}, 时间范围: {start_year}-{end_year}")
        if keywords:
            logger.info(f"关键词方向: {keywords}")
        
        # 创建分析器实例
        analyzer = JournalAnalyzer()
        
        # 构建基本检索策略
        base_query = f"{journal}[ta] AND ({start_year}[pdat]:{end_year}[pdat])"
        
        # 如果有关键词，扩展关键词并添加到检索策略
        if keywords:
            expanded_keywords = expand_keywords(keywords)
            if expanded_keywords:
                base_query = f"({base_query}) AND ({expanded_keywords})"
            logger.info(f"最终检索策略: {base_query}")
        
        # 获取文章数据
        articles = analyzer.fetch_journal_articles(base_query)
        
        if not articles:
            return jsonify({
                'success': False,
                'error': '未找到相关文章'
            }), 404
            
        logger.info(f"获取到 {len(articles)} 篇文章")
        
        # 分析热点主题
        hot_topics = analyzer.analyze_hot_topics(articles)
        
        # 分析热点作者
        hot_authors = analyzer.analyze_hot_authors(articles)
        
        # 生成热力图
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        heatmap_file = os.path.join('static', 'images', f'heatmap_{journal}_{timestamp}.png')
        os.makedirs(os.path.dirname(heatmap_file), exist_ok=True)
        analyzer.generate_heatmap(hot_topics, heatmap_file)
        
        # 准备返回数据
        response_data = {
            'success': True,
            'heatmap_data': [[topic['topic'], topic['article_count']] for topic in hot_topics],  # 修改为二维数组格式
            'wordcloud_data': [[topic['topic'], topic['article_count']] for topic in hot_topics],  # 修改为二维数组格式
            'trend_data': {
                'years': list(range(int(start_year), int(end_year) + 1)),
                'topics': [topic['topic'] for topic in hot_topics[:5]],
                'frequencies': [[topic['article_count']] * len(range(int(start_year), int(end_year) + 1)) for topic in hot_topics[:5]]  # 修改为每年的频率
            },
            'hot_authors': hot_authors,
            'heatmap_url': f'/{heatmap_file}',
            'total_articles': len(articles)
        }
        
        logger.info("期刊分析完成")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"期刊分析失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'分析失败: {str(e)}'
        }), 500

@app.route('/api/export', methods=['POST'])
def export_files():
    """
    处理文件导出请求
    
    请求体格式：
    {
        "query": "查询词",
        "papers": [文献列表],
        "export_type": "导出类型(initial_word/filtered_word/initial_excel/filtered_excel)",
        "filters": {筛选条件}
    }
    
    返回格式：
    {
        "success": true/false,
        "file_name": "文件名",
        "error": "错误信息"
    }
    """
    try:
        # 获取请求数据
        data = request.get_json()
        
        # 验证数据有效性
        if not data or not data.get('query') or not data.get('papers'):
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        query = data.get('query')
        papers = data.get('papers')
        export_type = data.get('export_type', 'initial_word')
        filters = data.get('filters', {})
        
        # 确定导出类型和文件后缀
        is_initial = 'initial' in export_type
        is_word = 'word' in export_type
        export_suffix = 'initial' if is_initial else 'filtered'
        
        # 如果需要过滤，则应用筛选条件
        if not is_initial:
            if isinstance(filters, dict) and filters:
                papers, _ = filter_papers_by_metrics(papers, filters)
        
        # 根据类型导出文件
        file_name = ""
        if is_word:
            file_path = export_papers_to_word(papers, query, export_suffix)
            file_name = os.path.basename(file_path)
        else:
            file_path = export_papers_to_excel(papers, query, export_suffix)
            file_name = os.path.basename(file_path)
        
        # 如果是筛选后的导出，生成分析报告
        if not is_initial:
            from analyze_papers import analyze_papers
            analyze_papers(file_path)
        
        return jsonify({
            'success': True,
            'file_name': file_name
        })
    
    except Exception as e:
        logger.error(f"导出文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f"导出失败: {str(e)}"
        }), 500

if __name__ == '__main__':
    try:
        # 检查NLTK数据
        nltk_data_path = os.path.join(os.path.expanduser('~'), 'nltk_data')
        
        # 如果nltk_data目录已存在，说明之前已经下载过数据
        if os.path.exists(nltk_data_path):
            logger.info("NLTK数据目录已存在，跳过下载")
        else:
            logger.info("首次运行，开始下载NLTK数据...")
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('wordnet', quiet=True)
                logger.info("NLTK数据下载完成")
            except Exception as e:
                logger.error(f"NLTK数据下载失败: {str(e)}")
                logger.warning("将使用基础分词功能")
        
        # 检查必要的配置
        if not DEEPSEEK_API_KEY:
            raise ValueError("未设置DEEPSEEK_API_KEY")
        if not PUBMED_API_KEY:
            raise ValueError("未设置PUBMED_API_KEY")
        
        logger.info("正在启动应用服务器...")
        # 启动应用
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"启动失败: {str(e)}\n{traceback.format_exc()}")
        raise 