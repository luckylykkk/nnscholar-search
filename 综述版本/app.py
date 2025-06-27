from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for
import requests
import json
import os
from dotenv import load_dotenv
import nltk
from nltk.tokenize import sent_tokenize
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime
import traceback
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO, StringIO
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
import shutil
from pathlib import Path
import threading
import copy
from flask_socketio import SocketIO, emit
import asyncio
from flask_socketio import join_room, leave_room
import math
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from flask_cors import CORS
# 导入paper_insights模块
import paper_insights
from docx.oxml.ns import qn
from docx.shared import RGBColor, Pt
from docx.oxml import OxmlElement
from word_utils import set_run_font, is_chinese_text, add_paragraph_with_mixed_fonts
import uuid
import re
from collections import Counter

# 确保必要的目录存在
for directory in ['logs', 'exports', 'static/images']:
    os.makedirs(directory, exist_ok=True)

# 确保NLTK数据包已下载
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
    nltk.data.find('corpora/wordnet')
except LookupError:
    print("正在下载NLTK数据包...")
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
    print("NLTK数据包下载完成")

# 创建应用实例
app = Flask(__name__, template_folder='templates')
# 配置Socket.IO以支持更高并发
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e8,  # 100MB
    manage_session=True,  # 启用Socket.IO的会话管理
    logger=True,  # 启用详细日志
    engineio_logger=True  # 启用Engine.IO日志
)

# 用户会话管理
active_users = {}  # 存储活跃用户的会话信息
user_stats_lock = threading.Lock()  # 用于保护用户统计数据的锁
user_messages = {}  # 存储每个用户的消息历史

# 性能监控相关变量
performance_stats = {
    'response_times': [],
    'error_count': 0,
    'request_count': 0,
    'avg_response_time': 0.0
}
performance_stats_lock = threading.Lock()

# 用户统计相关变量
user_stats = {
    'total_visits': 0,
    'concurrent_users': 0,
    'peak_concurrent_users': 0,
    'visit_times': [],
    'hourly_stats': {str(i): 0 for i in range(24)}
}

# 线程池执行器
executor = ThreadPoolExecutor(
    max_workers=50,
    thread_name_prefix='NNScholar'
)

@socketio.on('connect')
def handle_connect():
    """处理用户连接"""
    try:
        # 从查询参数中获取会话ID
        session_id = request.args.get('sessionId')
        if not session_id:
            logger.warning("连接请求没有会话ID")
            return False
            
        # 将客户端加入对应的房间
        join_room(session_id)
        
        # 初始化用户会话
        with user_stats_lock:
            active_users[session_id] = {
                'connect_time': datetime.now(),
                'last_active': datetime.now(),
                'request_count': 0,
                'last_request_time': None
            }
            
        logger.info(f"用户连接成功 {session_id}")
        
        # 发送连接成功消息
        emit('search_progress', {
            'stage': 'connect',
            'message': '连接成功',
            'percentage': 0
        }, room=session_id)
        
        return True
        
    except Exception as e:
        logger.error(f"处理连接时出错: {str(e)}\n{traceback.format_exc()}")
        return False

@socketio.on('disconnect')
def handle_disconnect():
    """处理用户断开连接"""
    try:
        session_id = request.args.get('sessionId')
        if session_id:
            # 将客户端从房间中移除
            leave_room(session_id)
            
            with user_stats_lock:
                if session_id in active_users:
                    del active_users[session_id]
                    user_stats['concurrent_users'] = len(active_users)
            logger.info(f"用户断开 {session_id}, 当前在线人数: {user_stats['concurrent_users']}")
    except Exception as e:
        logger.error(f"处理断开连接时出错: {str(e)}\n{traceback.format_exc()}")

def update_user_stats(session_id, action='connect'):
    """更新用户统计信息"""
    try:
        with user_stats_lock:
            current_time = datetime.now()
            
            if action == 'connect':
                # 检查会话是否已存在
                if session_id not in active_users:
                    active_users[session_id] = {
                        'connect_time': current_time,
                        'last_active': current_time,
                        'request_count': 0,
                        'last_request_time': None,
                        'messages': []
                    }
                else:
                    # 更新现有会话
                    active_users[session_id]['last_active'] = current_time
                    
                # 更新统计信息
                user_stats['concurrent_users'] = len(active_users)
                if user_stats['concurrent_users'] > user_stats['peak_concurrent_users']:
                    user_stats['peak_concurrent_users'] = user_stats['concurrent_users']
                    
            elif action == 'disconnect':
                if session_id in active_users:
                    del active_users[session_id]
                    user_stats['concurrent_users'] = len(active_users)
                    
    except Exception as e:
        logger.error(f"更新用户统计时出错: {str(e)}")

def monitor_system_performance():
    """监控系统性能"""
    while True:
        try:
            with performance_stats_lock:
                if performance_stats['response_times']:
                    avg_response_time = sum(performance_stats['response_times']) / len(performance_stats['response_times'])
                    performance_stats['avg_response_time'] = avg_response_time
                    logger.info(f"平均响应时间: {avg_response_time:.2f}秒")
                    
                    if len(performance_stats['response_times']) > 1000:
                        performance_stats['response_times'] = performance_stats['response_times'][-1000:]
                
                if performance_stats['request_count'] > 0:
                    error_rate = (performance_stats['error_count'] / performance_stats['request_count']) * 100
                    logger.info(f"错误率: {error_rate:.2f}%")
                
                logger.info(f"当前在线用户: {user_stats['concurrent_users']}")
                logger.info(f"历史峰值: {user_stats['peak_concurrent_users']}")
                
                performance_stats['error_count'] = 0
                performance_stats['request_count'] = 0
        except Exception as e:
            logger.error(f"性能监控出错: {str(e)}")
        time.sleep(300)

@app.before_request
def before_request():
    """请求预处理"""
    try:
        request.start_time = time.time()
        session_id = request.headers.get('sid')
        if session_id:
            with user_stats_lock:
                if session_id in active_users:
                    active_users[session_id]['last_active'] = datetime.now()
    except Exception as e:
        logger.error(f"请求预处理时出错: {str(e)}")

@app.after_request
def after_request(response):
    """请求后处理"""
    try:
        with performance_stats_lock:
            if hasattr(request, 'start_time'):
                response_time = time.time() - request.start_time
                performance_stats['response_times'].append(response_time)
            
            performance_stats['request_count'] += 1
            if response.status_code >= 400:
                performance_stats['error_count'] += 1
    except Exception as e:
        logger.error(f"请求后处理时出错: {str(e)}")
    return response

def get_hourly_visits():
    """获取最近24小时的每小时访问量"""
    try:
        current_time = datetime.now()
        hourly_stats = [0] * 24
        
        for hour in range(24):
            hour_str = str(hour)
            if hour_str in user_stats['hourly_stats']:
                hour_index = (hour - current_time.hour) % 24
                hourly_stats[hour_index] = user_stats['hourly_stats'][hour_str]
        
        return hourly_stats
    except Exception as e:
        logger.error(f"获取小时访问量时出错: {str(e)}")
        return [0] * 24

def get_user_messages(session_id: str) -> List[Dict]:
    """
    获取用户的消息历史
    
    Args:
        session_id (str): 用户会话ID
        
    Returns:
        List[Dict]: 用户的消息历史列表
    """
    with user_stats_lock:
        return user_messages.get(session_id, [])

def handle_connect(session_id: str):
    """
    处理用户连接
    
    Args:
        session_id (str): 用户会话ID
    """
    with user_stats_lock:
        current_time = datetime.now()
        
        # 初始化或更新用户会话
        active_users[session_id] = {
            'connect_time': current_time,
            'last_active': current_time,
            'request_count': 0,
            'last_request_time': None,
            'messages': []
        }
        
        # 初始化用户消息列表
        if session_id not in user_messages:
            user_messages[session_id] = []
            
        # 更新用户统计信息
        user_stats['total_visits'] += 1
        user_stats['visit_times'].append(current_time)
        current_hour = str(current_time.hour)
        user_stats['hourly_stats'][current_hour] = user_stats['hourly_stats'].get(current_hour, 0) + 1
        user_stats['concurrent_users'] = len(active_users)
        
        # 更新峰值
        if user_stats['concurrent_users'] > user_stats['peak_concurrent_users']:
            user_stats['peak_concurrent_users'] = user_stats['concurrent_users']
            logger.info(f"新的并发峰值: {user_stats['peak_concurrent_users']}")

def handle_disconnect(session_id: str):
    """
    处理用户断开连接
    
    Args:
        session_id (str): 用户会话ID
    """
    with user_stats_lock:
        if session_id in active_users:
            del active_users[session_id]
        if session_id in user_messages:
            del user_messages[session_id]

def emit_to_user(session_id: str, event: str, data: Dict):
    """
    向指定用户发送消息
    
    Args:
        session_id (str): 用户会话ID
        event (str): 事件名称
        data (Dict): 要发送的数据
    """
    try:
        # 检查会话是否存在
        if session_id not in active_users:
            logger.warning(f"尝试向不存在的会话 {session_id} 发送消息")
            return
            
        # 发送消息
        try:
            logger.info(f"发送消息到用户 {session_id}: {event}")
            socketio.emit(event, data, room=session_id)
        except Exception as e:
            logger.error(f"发送消息到用户 {session_id} 失败: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"处理消息发送时出错: {str(e)}")
        raise

def update_search_progress(session_id: str, stage: str, message: str, percentage: float = 0, **extra_data):
    """
    更新搜索进度
    
    Args:
        session_id (str): 用户会话ID
        stage (str): 当前阶段
        message (str): 进度消息
        percentage (float): 进度百分比
        **extra_data: 额外的数据字段
    """
    try:
        if not session_id:
            logger.error("无效的会话ID")
            return
            
        # 确保百分比在0-100之间
        percentage = min(100, max(0, percentage))
        
        # 构建进度数据
        progress_data = {
            'stage': stage,
            'message': message,
            'percentage': percentage,
            'timestamp': datetime.now().isoformat()
        }
        
        # 添加额外的数据字段
        progress_data.update(extra_data)
        
        # 记录日志
        logger.info(f"发送进度更新 [会话: {session_id}] - 阶段: {stage}, 消息: {message}, 进度: {percentage}%")
        
        try:
            # 发送进度更新
            socketio.emit('search_progress', progress_data, room=session_id)
        except Exception as e:
            logger.error(f"发送进度更新失败: {str(e)}")
            # 尝试发送错误消息
            try:
                socketio.emit('search_error', {'error': f"进度更新失败: {str(e)}"}, room=session_id)
            except:
                pass
                
    except Exception as e:
        logger.error(f"更新搜索进度时出错: {str(e)}\n{traceback.format_exc()}")
        try:
            socketio.emit('search_error', {'error': str(e)}, room=session_id)
        except:
            pass

def update_fetch_progress(session_id: str, stage: str, message: str, percentage: float, 
                         current: int = None, total: int = None, batch_info: Dict = None):
    """
    更新文献获取进度
    
    Args:
        session_id (str): 用户会话ID
        stage (str): 当前阶段
        message (str): 进度消息
        percentage (float): 进度百分比
        current (int, optional): 当前处理数量
        total (int, optional): 总数量
        batch_info (Dict, optional): 批次信息
    """
    try:
        progress_data = {
            'stage': stage,
            'message': message,
            'percentage': percentage
        }
        
        if current is not None:
            progress_data['current'] = current
            
        if total is not None:
            progress_data['total'] = total
            
        if batch_info:
            progress_data['batch_info'] = batch_info
            
        emit_to_user(session_id, 'fetch_progress', progress_data)
        
    except Exception as e:
        logger.error(f"更新文献获取进度时出错: {str(e)}")
        raise

# 创建必要的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
EXPORTS_DIR = os.path.join(BASE_DIR, 'exports')
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

# 设置最大缓存时间（24小时，以秒为单位）
MAX_CACHE_TIME = 86400

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

def get_api_config(log_info=False) -> Dict[str, str]:
    """
    获取API配置并验证
    
    Args:
        log_info (bool): 是否记录环境变量信息，默认为False
    
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
        'EMBEDDING_API_KEY': os.getenv('EMBEDDING_API_KEY', os.getenv('DEEPSEEK_API_KEY')),  # 默认使用DeepSeek API密钥
        'EMBEDDING_API_URL': os.getenv('EMBEDDING_API_URL', 'https://api.siliconflow.cn/v1/embeddings'),  # 使用SiliconFlow嵌入API端点
        'EMBEDDING_MODEL': os.getenv('EMBEDDING_MODEL', 'BAAI/bge-large-zh-v1.5'),  # 使用SiliconFlow支持的模型
    }
    
    if log_info:
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
        'pubmed_url': env_vars['PUBMED_API_URL'] or 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
        'embedding_api_key': env_vars['EMBEDDING_API_KEY'],
        'embedding_api_url': env_vars['EMBEDDING_API_URL'],
        'embedding_model': env_vars['EMBEDDING_MODEL'],
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
    # 仅在应用启动时记录环境变量信息
    API_CONFIG = get_api_config(log_info=True)
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

def calculate_authority_score(papers, paper):
    """计算文献的权威分数，考虑影响因子和相关度"""
    try:
        logger.info("开始计算权威分数")
        
        # 获取当前文献的影响因子
        journal_info = paper.get('journal_info', {})
        current_if = float(journal_info.get('impact_factor', 0)) if journal_info.get('impact_factor') else 0
        
        # 查找最大影响因子
        max_if = 0
        for p in papers:
            p_journal_info = p.get('journal_info', {})
            p_if = p_journal_info.get('impact_factor')
            if p_if and isinstance(p_if, (int, float, str)):
                try:
                    p_if_value = float(p_if)
                    if p_if_value > max_if:
                        max_if = p_if_value
                except (ValueError, TypeError):
                    continue
        
        # 确保最大影响因子不为0，避免除以0错误
        if max_if == 0:
            max_if = 10.0  # 使用一个合理的默认值
            logger.warning(f"未找到有效的最大影响因子，使用默认值 {max_if}")
        
        # 计算影响因子分数 (0-100)
        if_score = (current_if / max_if) * 100
        
        # 获取相关度分数 (0-100)
        # 优先使用 relevance_score 字段
        relevance_score = None
        if 'relevance_score' in paper and paper['relevance_score'] is not None:
            relevance_score = paper['relevance_score']
            logger.info(f"使用 relevance_score: {relevance_score}")
        elif 'relevance' in paper and paper['relevance'] is not None:
            relevance_score = paper['relevance']
            logger.info(f"使用 relevance: {relevance_score}")
        else:
            relevance_score = 0
            logger.warning("未找到相关度数据，使用默认值0")
        
        # 将相关度和字符串格式的数值转换为浮点数
        try:
            relevance_score = float(relevance_score)
        except (ValueError, TypeError):
            relevance_score = 0
            logger.warning("无法将相关度转换为数值，使用默认值0")
        
        # 记录调试信息
        logger.info(f"文献相关度得分: {relevance_score}, 影响因子得分: {if_score}")
        
        # 权重因子
        if_weight = 0.6  # 影响因子权重
        relevance_weight = 0.4  # 相关度权重
        
        # 计算各部分贡献分数
        if_contribution = if_score * if_weight
        relevance_contribution = relevance_score * relevance_weight
        
        # 计算最终权威分数
        final_score = if_contribution + relevance_contribution
        
        # 保留一位小数
        if_score = round(if_score, 1)
        relevance_score = round(relevance_score, 1)
        if_contribution = round(if_contribution, 1)
        relevance_contribution = round(relevance_contribution, 1)
        final_score = round(final_score, 1)
        
        # 创建计算信息字典，用于前端显示计算过程
        calculation_info = {
            'current_if': current_if,
            'max_if': max_if,
            'if_score': if_score,
            'relevance_score': relevance_score,
            'if_weight': if_weight,
            'relevance_weight': relevance_weight,
            'if_contribution': if_contribution,
            'relevance_contribution': relevance_contribution,
            'final_score': final_score
        }
        
        logger.info(f"权威分数计算完成: {final_score}")
        logger.info(f"计算信息: {calculation_info}")
        
        return final_score, calculation_info
        
    except Exception as e:
        logger.error(f"计算权威分数时出错: {str(e)}\n{traceback.format_exc()}")
        return 0, {'error': str(e)}

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
        
        # 5. 根据排序模式进行排序
        sort_mode = filters.get('sort_mode', 'relevance')  # 默认使用相关度优先
        if sort_mode == 'authority':
            # 权威文献优先模式
            logger.info("使用权威文献优先模式排序")
            # 计算每篇文献的权威分数
            for paper in cas_filtered:
                score, calculation_info = calculate_authority_score(cas_filtered, paper)
                paper['authority_score'] = score
                paper['authority_calculation'] = calculation_info  # 添加计算过程信息
            # 按权威分数排序
            filtered_papers = sorted(
                cas_filtered,
                key=lambda x: float(x.get('authority_score', 0)),
                reverse=True
            )
        else:
            # 相关度优先模式（默认）
            logger.info("使用相关度优先模式排序")
            # 确保每篇文献都有正确的相关度分数
            query = filters.get('original_query', '')  # 获取原始查询
            if query:
                logger.info(f"使用原始查询'{query}'计算相关度分数")
                # 批量计算所有文献的相关度
                try:
                    batch_scores = calculate_batch_embedding_relevance(query, cas_filtered)
                    logger.info(f"成功计算批量相关度分数，共{len(batch_scores)}个分数")
                    # 更新每篇文献的相关度分数
                    for i, paper in enumerate(cas_filtered):
                        if i < len(batch_scores):
                            paper['relevance_score'] = batch_scores[i]
                            logger.info(f"文献{i+1}的相关度分数: {batch_scores[i]}")
                        else:
                            paper['relevance_score'] = 0.0
                            logger.warning(f"文献{i+1}未获得相关度分数，设为0")
                except Exception as e:
                    logger.error(f"计算相关度分数时出错: {str(e)}")
                    # 如果计算失败，使用已有的相关度分数
                    logger.info("使用已有的相关度分数进行排序")
            else:
                logger.warning("未提供原始查询，无法计算新的相关度分数")
            
            # 按相关度排序
            filtered_papers = sorted(
                cas_filtered,
                key=lambda x: float(x.get('relevance_score', 0.0)),  # 使用relevance_score而不是relevance
                reverse=True
            )
            logger.info(f"按相关度排序完成，共{len(filtered_papers)}篇文献")
            # 记录排序后的前几篇文献的相关度分数
            for i, paper in enumerate(filtered_papers[:5]):
                logger.info(f"排序后第{i+1}篇文献的相关度分数: {paper.get('relevance_score', 0.0)}")
        
        # 限制返回数量
        try:
            papers_limit = int(filters.get('papers_limit', 10))
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
        logger.info(f"排序模式: {sort_mode}")
        
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
            # logger.info(f"文章标题: {title[:100]}...")
            
            # 提取发表年份
            pub_date = article.find('pubdate')
            pub_year = None
            if pub_date:
                # 尝试从Year标签提取
                year_elem = pub_date.find('year')
                if year_elem and year_elem.text:
                    try:
                        pub_year = int(year_elem.text)
                        # logger.info(f"成功提取发表年份: {pub_year}")
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
                                # logger.info(f"从MedlineDate提取到年份: {pub_year}")
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
                    # logger.info(f"找到ISSN: {issn}")
                else:
                    issn = None
                    logger.warning("未找到ISSN")
                journal_info['issn'] = issn
                
                # 提取期刊标题
                journal_title = journal.find('title')
                journal_info['title'] = journal_title.text if journal_title else ''
                # logger.info(f"期刊标题: {journal_info['title']}")
                
                # 获取期刊指标
                if issn:
                    # logger.info(f"开始获取期刊 {issn} 的指标信息")
                    metrics = get_journal_metrics(issn)
                    if metrics:
                        # logger.info(f"成功获取期刊指标: {metrics}")
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
            
            # 提取关键词
            keywords = []
            
            # 记录XML结构信息，帮助调试
            article_id = article.find('pmid').text if article.find('pmid') else 'unknown'
            logger.info(f"分析文章 {article_id} 的关键词结构")
            
            # 首先尝试提取<keywordlist owner="NOTNLM">标签下的关键词
            medline_citation = article.find('medlinecitation')
            if medline_citation:
                keyword_list = medline_citation.find('keywordlist', {'owner': 'NOTNLM'})
                if keyword_list:
                    keywords = [k.text.strip() for k in keyword_list.find_all('keyword')]
                    logger.info(f"从NOTNLM关键词列表中提取了 {len(keywords)} 个关键词")
                    if keywords:
                        logger.info(f"关键词示例: {keywords[:3]}")
            
            # 如果没有找到关键词，尝试其他可能的位置
            if not keywords:
                # 尝试查找任何keywordlist标签
                keyword_list = article.find('keywordlist') or article.find('KeywordList')
                if keyword_list:
                    keyword_elements = keyword_list.find_all('keyword') or keyword_list.find_all('Keyword')
                    keywords = [k.text.strip() for k in keyword_elements]
                    logger.info(f"成功提取 {len(keywords)} 个关键词，标签名: {keyword_list.name}")
                    if keywords:
                        logger.info(f"关键词示例: {keywords[:3]}")
                else:
                    # 尝试从MeSH中提取
                    mesh_list = article.find('meshheadinglist') or article.find('MeshHeadingList')
                    if not mesh_list and medline_citation:
                        mesh_list = medline_citation.find('meshheadinglist') or medline_citation.find('MeshHeadingList')
                    
                    if mesh_list:
                        mesh_terms = []
                        mesh_elements = mesh_list.find_all('meshheading') or mesh_list.find_all('MeshHeading')
                        for mesh in mesh_elements:
                            descriptor = mesh.find('descriptorname') or mesh.find('DescriptorName')
                            if descriptor:
                                mesh_terms.append(descriptor.text.strip())
                        if mesh_terms:
                            keywords = mesh_terms
                            logger.info(f"从MeSH中提取了 {len(keywords)} 个关键词")
                            if keywords:
                                logger.info(f"MeSH关键词示例: {keywords[:3]}")
                        else:
                            logger.info("MeSH列表为空")
                    else:
                        logger.info("未找到关键词列表或MeSH列表")
            
            article_data['keywords'] = keywords
            
            # 提取DOI
            article_id_list = article.find('articleidlist')
            if article_id_list:
                for article_id in article_id_list.find_all('articleid'):
                    if article_id.get('idtype') == 'doi':
                        article_data['doi'] = article_id.text
                        logger.info(f"成功提取DOI: {article_id.text}")
                        break
                if 'doi' not in article_data:
                    article_data['doi'] = ''
                    logger.warning(f"文献 {article_data['pmid']} 未找到DOI信息")
            else:
                article_data['doi'] = ''
                logger.warning(f"文献 {article_data['pmid']} 缺少ArticleIdList")
            
            logger.info(f"文章数据构建完成: PMID={article_data['pmid']}, 年份={article_data['pub_year']}, 关键词数量={len(keywords)}")
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
    """改进的相关性计算方法，优先使用embedding模型，失败时使用规则based评分"""
    try:
        # 首先尝试使用embedding模型计算相关度
        embedding_score = calculate_embedding_relevance(sentence, paper)
        
        # 如果embedding模型返回有效分数，直接使用
        if embedding_score > 0:
            logger.info(f"使用embedding模型计算相关度: {embedding_score:.1f}")
            return round(embedding_score, 1)
            
        # 如果embedding模型失败，使用规则based评分
        rule_score = calculate_rule_based_relevance(sentence, paper)
        logger.info(f"embedding模型失败，使用规则based评分: {rule_score:.1f}")
        
        # 确保分数在0-100之间
        final_score = max(0.0, min(100.0, rule_score))
        
        return round(final_score, 1)
        
    except Exception as e:
        logger.error(f"计算相关性时出错: {str(e)}")
        return 0.0

def calculate_embedding_relevance(query, paper):
    """
    使用嵌入模型计算查询与文献的相关度
    
    Args:
        query (str): 用户查询
        paper (dict): 文献信息
        
    Returns:
        float: 相关度分数 (0-100)
    """
    try:
        # 提取文献信息
        title = paper.get('title', '')
        abstract = paper.get('abstract', '')
        keywords = paper.get('keywords', [])
        keywords_str = ', '.join(keywords) if keywords else ''
        
        # 构建文献文本
        paper_text = f"标题: {title}\n摘要: {abstract}\n关键词: {keywords_str}"
        
        # 获取API配置
        api_url = os.getenv('EMBEDDING_API_URL', 'https://api.siliconflow.cn/v1/embeddings')
        api_key = os.getenv('EMBEDDING_API_KEY', os.getenv('DEEPSEEK_API_KEY'))
        model = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
        
        # 记录API调用（简化日志）
        # logger.info(f"调用嵌入模型API计算相关度: {api_url}")
        
        # 准备请求头和数据
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # 准备请求数据
        data = {
            "model": model,
            "input": [query, paper_text]
        }
        
        # 发送请求
        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()
        
        # 解析响应
        result = response.json()
        
        if 'data' in result and len(result['data']) >= 2:
            # 获取嵌入向量
            query_embedding = result['data'][0]['embedding']
            paper_embedding = result['data'][1]['embedding']
            
            # 计算余弦相似度
            similarity = cosine_similarity(query_embedding, paper_embedding)
            
            # 将相似度转换为0-100的分数
            relevance_score = round(similarity * 100, 1)
            
            # 记录结果
            # logger.info(f"嵌入模型相关度计算结果: {relevance_score}")
            
            return relevance_score
        else:
            logger.error(f"嵌入API响应格式错误: {result}")
            return 0.0
            
    except Exception as e:
        logger.error(f"计算嵌入相关度时出错: {str(e)}")
        return 0.0

def cosine_similarity(vec1, vec2):
    """
    计算两个向量的余弦相似度
    
    Args:
        vec1 (list): 第一个向量
        vec2 (list): 第二个向量
    
    Returns:
        float: 余弦相似度 (0-1)
    """
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    
    if magnitude1 * magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)

def search_pubmed(query, max_results=1000):
    """直接使用PubMed API搜索文献"""
    try:
        logger.info(f"开始PubMed搜索，检索策略: {query}, 最大结果数: {max_results}")
        
        session_id = request.headers.get('sid')
        if not session_id:
            raise ValueError("无效的会话ID")
            
        # 发送搜索开始信息
        update_search_progress(session_id, 'search_start', "开始PubMed搜索...", 0)
        
        # 使用提供的检索策略
        search_strategy = query

        # 构建PubMed搜索请求
        search_params = {
            'db': 'pubmed',
            'term': search_strategy,
            'retmax': str(max_results),
            'retmode': 'json',
            'api_key': PUBMED_API_KEY
        }
        
        # 发送正在搜索的信息
        update_search_progress(session_id, 'searching', "正在PubMed中搜索文献...", 60)
        
        # 发送搜索请求
        search_url = f"{PUBMED_BASE_URL}esearch.fcgi"
        response = requests.get(search_url, params=search_params)
        
        if response.status_code != 200:
            logger.error(f"PubMed搜索请求失败: HTTP {response.status_code}")
            
            # 发送搜索失败信息
            update_search_progress(session_id, 'search_failed', f"PubMed搜索请求失败: HTTP {response.status_code}", 100)
            
            return [], search_strategy, 0, 0
            
        search_result = response.json()
        total_count = int(search_result.get('esearchresult', {}).get('count', 0))
        id_list = search_result.get('esearchresult', {}).get('idlist', [])
        
        # 发送搜索结果信息
        update_search_progress(session_id, 'search_complete', f"找到 {total_count} 篇文献", total_count, result_count=len(id_list))
        
        return id_list, search_strategy, total_count, len(id_list)
    except Exception as e:
        logger.error(f"PubMed搜索出错: {str(e)}\n{traceback.format_exc()}")
        
        # 发送错误信息
        if session_id:
            update_search_progress(session_id, 'error', f"搜索出错: {str(e)}", 100)
            
        return [], "", 0, 0

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
            
        session_id = request.headers.get('sid')
        if not session_id:
            raise ValueError("无效的会话ID")
            
        # 将ID列表分成较小的批次，每批300个ID
        batch_size = 300
        all_papers = []
        total_batches = (len(id_list) + batch_size - 1) // batch_size
        
        logger.info(f"开始获取文献详情，共 {len(id_list)} 篇文献，分 {total_batches} 批处理")
        
        # 发送初始进度信息
        update_fetch_progress(session_id, 'fetch_start', f"开始获取文献详情，共 {len(id_list)} 篇文献，将分 {total_batches} 批处理", 0, total=len(id_list))
        
        for i in range(0, len(id_list), batch_size):
            batch_ids = id_list[i:i+batch_size]
            current_batch = i // batch_size + 1
            logger.info(f"正在处理第 {current_batch}/{total_batches} 批文献 ({len(batch_ids)} 篇)")
            
            # 发送批次开始处理的消息
            update_fetch_progress(session_id, 'batch_start', f"正在处理第 {current_batch}/{total_batches} 批文献 ({len(batch_ids)} 篇)", 
                                (current_batch - 1) / total_batches * 100,
                                total=total_batches, 
                                batch_info={'current_batch': current_batch, 'total_batches': total_batches, 'batch_size': len(batch_ids)})
            
            # 构建请求参数
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(batch_ids),
                'retmode': 'xml',
                'api_key': PUBMED_API_KEY
            }
            
            # 添加重试机制
            max_retries = 3
            retry_delay = 1  # 初始延迟1秒
            success = False
            
            for retry in range(max_retries):
                try:
            # 发送请求获取详情
                    fetch_url = f"{PUBMED_BASE_URL}efetch.fcgi"
                    response = requests.get(fetch_url, params=fetch_params, timeout=30)  # 添加超时设置
            
                    if response.status_code == 200:
                        # 解析XML响应
                        papers = parse_pubmed_xml(response.content)
                        all_papers.extend(papers)
                        logger.info(f"✓ 第 {current_batch}/{total_batches} 批完成，成功获取 {len(papers)} 篇文献")
                        
                        # 计算当前进度
                        current_count = len(all_papers)
                        percentage = round((current_count / len(id_list)) * 100, 1)
                        logger.info(f"当前进度: {current_count}/{len(id_list)} 篇 ({percentage}%)")
                        
                        # 发送批次完成的进度更新
                        update_fetch_progress(session_id, 'batch_complete', 
                                        f"第 {current_batch}/{total_batches} 批处理完成，已获取 {current_count}/{len(id_list)} 篇文献 ({percentage}%)", 
                                        percentage,
                                        current=current_count, 
                                        total=len(id_list), 
                                        batch_info={'current_batch': current_batch, 
                                                    'total_batches': total_batches, 
                                                    'batch_size': len(batch_ids), 
                                                    'batch_success': len(papers)})
                        success = True
                        break
                    else:
                                logger.warning(f"第 {retry + 1} 次尝试失败: HTTP {response.status_code}")
                                if retry < max_retries - 1:
                                    time.sleep(retry_delay)
                                    retry_delay *= 2  # 指数退避
                
                except (requests.exceptions.RequestException, requests.exceptions.ChunkedEncodingError) as e:
                    logger.warning(f"第 {retry + 1} 次尝试出错: {str(e)}")
                    if retry < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
            
            if not success:
                logger.error(f"✗ 第 {current_batch}/{total_batches} 批失败，已重试 {max_retries} 次")
                # 发送批次失败的消息
                update_fetch_progress(session_id, 'batch_error', 
                                   f"第 {current_batch}/{total_batches} 批处理失败，已重试 {max_retries} 次", 
                                   (current_batch / total_batches) * 100,
                                   batch_info={'current_batch': current_batch, 
                                             'total_batches': total_batches, 
                                             'error': f"获取失败，已重试 {max_retries} 次"})
            
            # 添加短暂延时，避免请求过于频繁
            if current_batch < total_batches:  # 最后一批不需要延时
                time.sleep(0.5)
        
        logger.info(f"文献获取完成，共处理 {len(all_papers)}/{len(id_list)} 篇文献")
        
        # 发送完成信息
        final_percentage = round((len(all_papers) / len(id_list)) * 100, 1)
        update_fetch_progress(session_id, 'fetch_complete', 
                            f"文献获取完成，共获取 {len(all_papers)}/{len(id_list)} 篇文献", 
                            final_percentage,
                            current=len(all_papers), 
                            total=len(id_list))
        
        return all_papers
        
    except Exception as e:
        logger.error(f"获取文献详情过程中发生错误: {str(e)}\n{traceback.format_exc()}")
        # 发送错误信息
        if session_id:
            update_fetch_progress(session_id, 'error', 
                                f"获取文献详情失败: {str(e)}", 
                                100,  # 错误时显示100%
                                error=str(e))
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
            # logger.info(f"成功将年份转换为整数: {pub_year}")
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
            
        # 提取DOI
        article_id_list = article.find('ArticleIdList')
        if article_id_list:
            for article_id in article_id_list.find_all('ArticleId'):
                if article_id.get('IdType') == 'doi':
                    paper_info['doi'] = article_id.text
                    logger.info(f"成功提取DOI: {article_id.text}")
                    break
            if 'doi' not in paper_info:
                paper_info['doi'] = ''
                logger.warning(f"文献 {pmid} 未找到DOI信息")
        else:
            paper_info['doi'] = ''
            logger.warning(f"文献 {pmid} 缺少ArticleIdList")
            
        return paper_info
            
    except Exception as e:
        logger.error(f"解析文献信息时出错: {str(e)}\n{traceback.format_exc()}")
        return None

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

async def process_sentence_async(session_id: str, sentence: dict, filters: dict = None) -> dict:
    """异步处理单个句子的检索
    
    Args:
        session_id (str): 用户会话ID
        sentence (dict): 包含文本和检索策略的句子字典
        filters (dict, optional): 筛选条件
        
    Returns:
        dict: 检索结果
    """
    try:
        # 执行检索
        id_list, search_strategy, total_count, filtered_count = search_pubmed(sentence['search_strategy'])
        
        # 获取文献详情
        papers = fetch_paper_details(id_list)
        
        # 计算相关度得分
        for i, paper in enumerate(papers):
            relevance = calculate_relevance_improved(sentence['text'], paper)
            paper['relevance_score'] = relevance
            paper['relevance'] = relevance  # 保持兼容性
            if i < 5:  # 只记录前5篇的日志
                logger.info(f"文献{i+1}的相关度分数: {relevance}")
        
        # 应用筛选条件
        if filters:
            # 使用句子的文本作为原始查询
            filters_copy = filters.copy()
            filters_copy['original_query'] = sentence['text']
            filtered_papers, stats = filter_papers_by_metrics(papers, filters_copy)
        else:
            filtered_papers = papers
            stats = {
                'total': len(papers),
                'filtered': len(papers)
            }
        
        return {
            'text': sentence['text'],
            'search_strategy': sentence['search_strategy'],
            'data': filtered_papers,  # 使用data字段保持一致性
            'total_count': total_count,
            'filtered_count': len(filtered_papers)
        }
        
    except Exception as e:
        logger.error(f"处理句子时出错: {str(e)}\n{traceback.format_exc()}")
        return None

async def process_paragraph_async(session_id: str, sentences: List[dict], filters: dict = None) -> List[dict]:
    """异步处理段落中的所有句子
    
    Args:
        session_id (str): 用户会话ID
        sentences (List[dict]): 句子列表
        filters (dict, optional): 筛选条件
        
    Returns:
        List[dict]: 检索结果列表
    """
    try:
        # 创建任务列表
        tasks = [
            process_sentence_async(session_id, sentence, filters)
            for sentence in sentences
        ]
        
        # 并发执行所有任务
        results = await asyncio.gather(*tasks)
        
        # 过滤掉失败的结果
        return [r for r in results if r is not None]
        
    except Exception as e:
        logger.error(f"处理段落时出错: {str(e)}\n{traceback.format_exc()}")
        return []

def process_paragraph_threaded(session_id: str, sentences: List[dict], filters: dict = None) -> List[dict]:
    """使用线程池处理段落中的所有句子
    
    Args:
        session_id (str): 用户会话ID
        sentences (List[dict]): 句子列表
        filters (dict, optional): 筛选条件
        
    Returns:
        List[dict]: 检索结果列表
    """
    try:
        results = []
        with ThreadPoolExecutor(max_workers=len(sentences)) as executor:
            # 提交所有任务
            future_to_sentence = {
                executor.submit(
                    lambda s: asyncio.run(process_sentence_async(session_id, s, filters)),
                    sentence
                ): sentence
                for sentence in sentences
            }
            
            # 收集结果
            for future in as_completed(future_to_sentence):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"处理句子时出错: {str(e)}")
                    continue
                    
        return results
        
    except Exception as e:
        logger.error(f"处理段落时出错: {str(e)}\n{traceback.format_exc()}")
        return []

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

# 用于存储内存中的导出文件
memory_exports = {}

def export_papers(papers, query, file_suffix=''):
    """
    导出文献信息到Excel和Word文件
    
    Args:
        papers: 文献列表
        query: 检索词
        file_suffix: 文件名后缀
        
    Returns:
        tuple: (excel_path, word_path, titles_path) 导出文件的路径或文件ID
    """
    try:
        session_id = request.headers.get('sid')
        if not session_id:
            raise ValueError("无效的会话ID")
        
        # 发送开始导出的消息
        update_search_progress(session_id, 'export_progress', "开始导出文件...", 10)
        
        # 导出Excel
        update_search_progress(session_id, 'export_progress', "正在导出Excel文件...", 25)
        excel_path = export_papers_to_excel(papers, query, file_suffix)
        
        # 发送Excel导出完成的消息
        update_search_progress(session_id, 'export_progress', "Excel文件导出完成", 40)
        
        # 导出Word
        update_search_progress(session_id, 'export_progress', "正在导出Word文件...", 55)
        word_path = export_papers_to_word(papers, query, file_suffix)
        
        # 发送Word导出完成的消息
        update_search_progress(session_id, 'export_progress', "Word文件导出完成", 70)
        
        # 导出标题文档
        update_search_progress(session_id, 'export_progress', "正在导出标题文档...", 85)
        titles_path = export_titles_to_word(papers, query, file_suffix)
        
        # 发送标题文档导出完成的消息
        update_search_progress(session_id, 'export_progress', "标题文档导出完成", 95)
        
        # 发送导出完成的消息
        update_search_progress(session_id, 'export_progress', "文献导出完成", 100, 
                             files={'excel': excel_path, 'word': word_path, 'titles': titles_path})
        
        return excel_path, word_path, titles_path
        
    except Exception as e:
        logger.error(f'导出文件失败：{str(e)}\n{traceback.format_exc()}')
        
        # 发送错误信息
        if session_id:
            update_search_progress(session_id, 'export_progress', f"导出文件失败: {str(e)}", 100)
            
        return None, None, None

def export_papers_to_excel(papers, query, file_suffix='', export_type='standard'):
    """
    将论文导出为Excel文件
    
    Args:
        papers (list): 论文列表，应该已经包含相关度分数和权威分数（如果使用权威文献优先模式）
        query (str): 查询字符串
        file_suffix (str, optional): 文件名后缀. Defaults to ''.
        export_type (str, optional): 导出类型，'standard'为标准导出，'pro'为专业版导出(包含摘要和创新点). Defaults to 'standard'.
        
    Returns:
        str: 导出文件的路径
    """
    try:
        # 获取session_id
        session_id = request.args.get('sessionId', 'unknown')
        update_search_progress(session_id, 'excel_export_progress', "正在准备导出Excel...", 10)
        
        # 创建导出目录
        export_dir = os.path.join(app.root_path, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"nnscholar_export_{timestamp}{file_suffix}.xlsx"
        filepath = os.path.join(export_dir, filename)
        
        # 更新进度
        update_search_progress(session_id, 'excel_export_progress', "正在处理文献数据...", 20)
        
        # 检查文献是否已有相关度分数
        has_scores = all('relevance_score' in paper for paper in papers)
        if not has_scores:
            logger.warning("文献缺少相关度分数，这不应该发生，因为应该在导出前已经计算过相关度")
        
        # 批量生成文献摘要和创新点分析（仅在Pro版本中）
        paper_insights_results = {}
        if export_type == 'pro':
            paper_insights_results = generate_batch_paper_insights(papers, query)
        
        # 准备数据
        data = []
        total_papers = len(papers)
        
        for i, paper in enumerate(papers):
            # 更新进度
            progress_percentage = 70 + (i / total_papers) * 20
            if i % 5 == 0:  # 每处理5篇文献更新一次进度
                update_search_progress(
                    session_id, 
                    'excel_export_progress', 
                    f"正在处理文献数据 ({i+1}/{total_papers})...", 
                    progress_percentage
                )
            
            # 获取期刊信息
            journal_info = paper.get('journal_info', {})
            
            # 提取作者信息
            authors = paper.get('authors', [])
            authors_str = ', '.join(authors) if authors else ''
            
            # 提取关键词信息
            keywords = paper.get('keywords', [])
            keywords_str = ', '.join(keywords) if keywords else ''
            
            # 获取相关度分数和权威分数
            relevance_score = paper.get('relevance_score', 0.0)
            authority_score = paper.get('authority_score', 0.0)
            
            # 获取摘要和创新点分析（仅在Pro版本中）
            summary = "未生成"
            innovation = "未生成"
            if export_type == 'pro':
                paper_id = paper.get('pmid', '')
                if not paper_id:
                    paper_id = str(hash(paper.get('title', '')))
                if paper_id in paper_insights_results:
                    summary, innovation = paper_insights_results[paper_id]
                    logger.info(f"使用生成的摘要和创新点 (ID: {paper_id}), 摘要长度: {len(summary)}, 创新点长度: {len(innovation)}")
                else:
                    logger.warning(f"未找到文献的摘要和创新点 (ID: {paper_id})")
            
            # 构建基本数据行
            paper_data = {
                'PMID': paper.get('pmid', ''),
                'DOI': paper.get('doi', ''),
                '标题': paper.get('title', ''),
                '作者': authors_str,
                '期刊': journal_info.get('title', ''),
                '发表年份': paper.get('pub_year', ''),
                '影响因子': journal_info.get('impact_factor', ''),
                'JCR分区': journal_info.get('jcr_quartile', ''),
                'CAS分区': journal_info.get('cas_quartile', ''),
                '相关度': relevance_score,
                '权威分数': authority_score,
                '关键词': keywords_str,
                '摘要': paper.get('abstract', '')
            }
            
            # 如果是Pro版本，添加摘要和创新点分析列
            if export_type == 'pro':
                logger.info(f"添加摘要和创新点分析列 (ID: {paper.get('pmid', '')})")
                paper_data['总结摘要'] = summary
                paper_data['创新点分析'] = innovation
            
            # 添加数据行
            data.append(paper_data)
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 按相关度降序排序
        # df = df.sort_values(by='相关度', ascending=False)
        
        # 发送格式化Excel的消息
        update_search_progress(session_id, 'excel_export_progress', "正在格式化Excel表格...", 85)
        
        # 创建内存中的Excel文件
        excel_buffer = BytesIO()
        
        # 使用ExcelWriter以便应用格式
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='文献列表')
            
            # 获取工作簿和工作表
            workbook = writer.book
            worksheet = writer.sheets['文献列表']
            
            # 设置列宽
            for idx, col in enumerate(df.columns):
                column_width = 15  # 默认宽度
                if col == '标题':
                    column_width = 40
                elif col == '摘要':
                    column_width = 50
                elif col == '作者' or col == '关键词':
                    column_width = 30
                
                # 设置列宽
                worksheet.column_dimensions[get_column_letter(idx + 1)].width = column_width
            
            # 为相关度和权威分数列添加条件格式
            from openpyxl.formatting.rule import ColorScaleRule
            
            # 相关度列
            relevance_col = df.columns.get_loc('相关度') + 1
            relevance_col_letter = get_column_letter(relevance_col)
            
            # 权威分数列
            authority_col = df.columns.get_loc('权威分数') + 1
            authority_col_letter = get_column_letter(authority_col)
            
            # 添加颜色渐变
            color_scale_rule = ColorScaleRule(
                start_type='num', start_value=0, start_color='FFFFFF',
                mid_type='num', mid_value=50, mid_color='FFEB84',
                end_type='num', end_value=100, end_color='63BE7B'
            )
            
            # 应用条件格式到相关度列和权威分数列
            worksheet.conditional_formatting.add(
                f"{relevance_col_letter}2:{relevance_col_letter}{len(df) + 1}",
                color_scale_rule
            )
            worksheet.conditional_formatting.add(
                f"{authority_col_letter}2:{authority_col_letter}{len(df) + 1}",
                color_scale_rule
            )
        
        # 重置缓冲区位置
        excel_buffer.seek(0)
        
        # 生成唯一的文件ID
        file_id = f"{session_id}_{filename}"
        
        # 存储到内存中
        memory_exports[file_id] = {
            'data': excel_buffer,
            'filename': filename,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'timestamp': datetime.now()
        }
        
        # 发送导出完成的消息
        update_search_progress(session_id, 'excel_export_progress', "Excel文件导出完成", 100)
        
        return file_id
        
    except Exception as e:
        logger.error(f"导出Excel文件时发生错误: {str(e)}")
        logger.error(traceback.format_exc())
        if session_id:
            update_search_progress(session_id, 'excel_export_progress', 
                                f"导出Excel文件失败: {str(e)}", 100)
        return None

def export_papers_to_word(papers, query, file_suffix=''):
    """
    将论文信息导出为Word文档
    
    Args:
        papers (list): 论文列表，应该已经包含相关度分数和权威分数（如果使用权威文献优先模式）
        query (str): 查询字符串
        file_suffix (str, optional): 文件名后缀. Defaults to ''.
        
    Returns:
        str: 导出文件的路径
    """
    try:
        # 获取session_id
        session_id = request.args.get('sessionId', 'unknown')
        update_search_progress(session_id, 'word_export_progress', "正在准备导出Word...", 10)
        
        # 创建导出目录
        export_dir = os.path.join(app.root_path, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"nnscholar_export_{timestamp}{file_suffix}.docx"
        filepath = os.path.join(export_dir, filename)
        
        # 检查文献是否已有相关度分数
        has_scores = all('relevance_score' in paper for paper in papers)
        if not has_scores:
            logger.warning("文献缺少相关度分数，这不应该发生，因为应该在导出前已经计算过相关度")
        
        # 按相关度降序排序文献
        papers_with_relevance = sorted(papers, key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        update_search_progress(session_id, 'word_export_progress', "正在生成Word文档...", 40)
        
        # 创建Word文档
        doc = Document()
        
        # 添加标题
        title = doc.add_heading('文献检索报告', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 添加检索信息
        doc.add_heading('检索策略', level=1)
        doc.add_paragraph(f'检索词：\n{query}')
        doc.add_paragraph(f'检索时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        doc.add_paragraph(f'检索到的文献数量：{len(papers)}')
        
        # 添加文献列表
        doc.add_heading('文献列表', level=1)
        for i, paper in enumerate(papers, 1):
            # 获取期刊信息
            journal_info = paper.get('journal_info', {})
            
            # 添加文献标题和相关度
            p = doc.add_paragraph()
            p.add_run(f'{i}. ').bold = True
            title_run = p.add_run(paper.get('title', 'N/A'))
            title_run.bold = True
            
            # 添加相关度和权威分数信息
            relevance_score = paper.get('relevance_score', 0)
            authority_score = paper.get('authority_score', 0)
            
            relevance_run = p.add_run(f' [相关度: {relevance_score:.1f}]')
            relevance_run.bold = True
            if relevance_score >= 70:
                relevance_run.font.color.rgb = RGBColor(0, 128, 0)  # 绿色
            elif relevance_score >= 40:
                relevance_run.font.color.rgb = RGBColor(255, 165, 0)  # 橙色
            else:
                relevance_run.font.color.rgb = RGBColor(128, 128, 128)  # 灰色
            
            authority_run = p.add_run(f' [权威分数: {authority_score:.1f}]')
            authority_run.bold = True
            if authority_score >= 70:
                authority_run.font.color.rgb = RGBColor(0, 0, 255)  # 蓝色
            elif authority_score >= 40:
                authority_run.font.color.rgb = RGBColor(128, 0, 128)  # 紫色
            else:
                authority_run.font.color.rgb = RGBColor(128, 128, 128)  # 灰色
            
            # 添加作者信息
            authors_str = ', '.join(paper.get('authors', [])) if paper.get('authors') else 'N/A'
            doc.add_paragraph(f'作者：{authors_str}')
            
            # 添加期刊信息
            doc.add_paragraph(f'期刊：{journal_info.get("title", "N/A")}')
            doc.add_paragraph(f'发表时间：{paper.get("pub_year", "N/A")}')
            
            # 添加影响因子和分区信息
            doc.add_paragraph(f'影响因子：{journal_info.get("impact_factor", "N/A")}')
            doc.add_paragraph(f'JCR分区：{journal_info.get("jcr_quartile", "N/A")}')
            doc.add_paragraph(f'CAS分区：{journal_info.get("cas_quartile", "N/A")}')
            
            # 添加关键词信息
            keywords_str = ', '.join(paper.get('keywords', [])) if paper.get('keywords') else 'N/A'
            doc.add_paragraph(f'关键词：{keywords_str}')
            
            # 添加DOI和PMID
            doc.add_paragraph(f'DOI：{paper.get("doi", "N/A")}')
            doc.add_paragraph(f'PMID：{paper.get("pmid", "N/A")}')
            
            # 添加摘要
            if paper.get('abstract'):
                doc.add_paragraph('摘要：').add_run(paper['abstract']).italic = True
            
            # 添加分隔线
            if i < len(papers_with_relevance):
                doc.add_paragraph('_' * 50)
        
        # 保存到内存
        word_buffer = BytesIO()
        doc.save(word_buffer)
        word_buffer.seek(0)
        
        # 生成唯一的文件ID
        file_id = f"{session_id}_{filename}"
        
        # 存储到内存中
        memory_exports[file_id] = {
            'data': word_buffer,
            'filename': filename,
            'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'timestamp': datetime.now()
        }
        
        # 发送导出完成的消息
        update_search_progress(session_id, 'word_export_progress', "Word文件导出完成", 100)
        
        return file_id
        
    except Exception as e:
        logger.error(f"导出Word文件时发生错误: {str(e)}")
        logger.error(traceback.format_exc())
        if session_id:
            update_search_progress(session_id, 'word_export_progress', 
                                f"导出Word文件失败: {str(e)}", 100)
        return None

@app.route('/')
def index():
    """主页，获取并存储用户ID"""
    # 从URL参数获取用户ID
    user_id = request.args.get('userId')
    logger.info(f"主页访问 - URL中的userId参数: {user_id}")
    
    return render_template('index.html', user_id=user_id)

@app.route('/api/search', methods=['POST'])
def search():
    """处理搜索请求"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        mode = data.get('mode', 'single')
        filters = data.get('filters', {})
        
        # 在过滤器中添加原始查询，用于后续计算相关度
        filters['original_query'] = query
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请输入检索内容'
            }), 400
            
        # 获取当前用户的会话ID
        session_id = request.headers.get('Session-Id') or request.headers.get('sid')
        if not session_id:
            logger.warning("未提供会话ID，将使用临时ID")
            session_id = f"temp_{uuid.uuid4().hex[:8]}"
            
        # 更新用户活跃状态
        handle_connect(session_id)
        
        # 发送开始搜索的进度信息
        update_search_progress(session_id, 'start', "开始处理搜索请求...", 0)
        
        # 根据模式处理搜索
        if mode == 'paragraph':
            # 段落模式处理
            update_search_progress(session_id, 'paragraph_mode', "正在使用段落模式处理...", 10)
            
            # 分解段落为句子
            sentences = split_paragraph_to_sentences(query)
            if not sentences:
                return jsonify({
                    'success': True,
                    'sentences': []
                })
            
            # 使用线程池并行处理所有句子
            results = process_paragraph_threaded(session_id, sentences, filters)
            
            # 发送完成消息
            update_search_progress(session_id, 'complete', f"段落处理完成，共处理 {len(results)} 个句子", 100)
            
            return jsonify({
                'success': True,
                'sentences': results
            })
            
        elif mode == 'strategy':
            # 直接使用提供的检索策略
            search_strategy = query
            logger.info(f"使用提供的检索策略: {search_strategy}")
            
            update_search_progress(session_id, 'executing_strategy', "正在执行检索策略...", 30)
        else:
            # 生成检索策略
            update_search_progress(session_id, 'generating_strategy', "正在生成检索策略...", 20)
            
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
                search_strategy = call_deepseek_api(prompt.format(query=query))
                logger.info(f"生成的检索策略: {search_strategy}")
                
                update_search_progress(session_id, 'strategy_generated', "检索策略生成完成", 40, search_strategy=search_strategy)
            except Exception as e:
                logger.warning(f"DeepSeek API调用失败，使用基本搜索策略: {str(e)}")
                search_strategy = f'"{query}"[All Fields]'
                logger.info(f"使用基本搜索策略: {search_strategy}")
                
                update_search_progress(session_id, 'strategy_fallback', "检索策略生成失败，使用基本策略", 40, search_strategy=search_strategy)
        
        # 执行搜索
        id_list, _, total_count, result_count = search_pubmed(search_strategy)
        
        # 获取文献详情
        update_search_progress(session_id, 'fetching_details', "正在获取文献详情...", 60)
        
        papers = fetch_paper_details(id_list)
        
        # 计算相关性得分
        update_search_progress(session_id, 'calculating_relevance', "正在计算相关性得分...", 80)
        
        # 使用批量计算相关度的方法，确保每篇文献都有 relevance_score
        try:
            batch_scores = calculate_batch_embedding_relevance(query, papers)
            logger.info(f"成功计算批量相关度分数，共{len(batch_scores)}个分数")
            # 更新每篇文献的相关度分数
            for i, paper in enumerate(papers):
                if i < len(batch_scores):
                    paper['relevance_score'] = batch_scores[i]
                    logger.info(f"文献{i+1}的相关度分数: {batch_scores[i]}")
                else:
                    # 如果没有批量计算结果，使用单独计算
                    relevance = calculate_relevance_improved(query, paper)
                    paper['relevance_score'] = relevance
                    logger.info(f"文献{i+1}的相关度分数(单独计算): {relevance}")
        except Exception as e:
            logger.error(f"批量计算相关度分数时出错: {str(e)}")
            # 如果批量计算失败，使用单独计算
            for i, paper in enumerate(papers):
                relevance = calculate_relevance_improved(query, paper)
                paper['relevance_score'] = relevance
                if i < 5:  # 只记录前5篇文献的日志
                    logger.info(f"文献{i+1}的相关度分数(单独计算): {relevance}")
        
        # 应用筛选条件 - 确保传递原始查询
        filtered_papers, stats = filter_papers_by_metrics(papers, filters)
        
        # 导出文件
        update_search_progress(session_id, 'exporting', "正在生成导出文件...", 90)
        
                # 导出初始结果和筛选后的结果
        initial_excel, initial_word, initial_titles = export_papers(papers, query, 'initial')
        filtered_excel, filtered_word, filtered_titles = export_papers(filtered_papers, query, 'filtered')
        
        # 发送完成消息
        update_search_progress(session_id, 'complete', f"搜索完成，找到 {len(filtered_papers)} 篇相关文献", 100)
            
        return jsonify({
            'success': True,
            'data': filtered_papers,
            'original_papers': papers,
            'search_strategy': search_strategy,
            'total_count': total_count,
            'filtered_count': len(filtered_papers),
            'export_path': filtered_excel,
            'report_path': filtered_word,
            'text_path': filtered_titles,
            'export_files': {
                'initial_excel': initial_excel,
                'initial_word': initial_word,
                'filtered_excel': filtered_excel,
                'filtered_word': filtered_word,
                'filtered_titles': filtered_titles
            }
        })
        
    except Exception as e:
        logger.error(f"搜索请求处理出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/search-sentence', methods=['POST'])
def search_sentence():
    """处理段落模式下单个句子的检索请求，并确保正确调用计费功能"""
    try:
        data = request.get_json()
        strategy = data.get('strategy', '').strip()
        filters = data.get('filters', {})
        
        if not strategy:
            return jsonify({
                'success': False,
                'error': '请提供检索策略'
            }), 400
            
        # 获取当前用户的会话ID和用户ID
        session_id = request.headers.get('sid')
        user_id = request.headers.get('userId')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': '无效的会话ID'
            }), 400
            
        # 验证用户ID和积分（已禁用积分检查）
        if user_id:
            # 调用Token API检查并减少用户的credit（已禁用，始终返回成功）
            token_result = reduce_tokens(
                user_id=user_id,
                amount=1000,  
                service_id="nnscholar",
                reason="search_sentence"
            )
            
            # 记录禁用积分检查的日志
            logger.info(f"积分检查已禁用 - 用户ID: {user_id}, 调用函数: search_sentence")
        
        # 更新用户活跃状态
        handle_connect(session_id)
        
        # 发送开始搜索的进度信息
        update_search_progress(session_id, 'executing_strategy', f"正在执行句子检索策略...", 30)
        
        # 执行搜索
        id_list, _, total_count, result_count = search_pubmed(strategy)
        
        # 获取文献详情
        update_search_progress(session_id, 'fetching_details', "正在获取文献详情...", 60)
        
        papers = fetch_paper_details(id_list)
        
        # 计算相关性得分
        update_search_progress(session_id, 'calculating_relevance', "正在计算相关性得分...", 80)
        
        # 批量计算相关度得分
        try:
            batch_scores = calculate_batch_embedding_relevance(strategy, papers)
            logger.info(f"成功计算批量相关度分数，共{len(batch_scores)}个分数")
            # 更新每篇文献的相关度分数
            for i, paper in enumerate(papers):
                if i < len(batch_scores):
                    paper['relevance_score'] = batch_scores[i]
                    logger.info(f"文献{i+1}的相关度分数: {batch_scores[i]}")
                else:
                    # 如果没有批量计算结果，使用单独计算
                    relevance = calculate_relevance_improved(strategy, paper)
                    paper['relevance_score'] = relevance
                    logger.info(f"文献{i+1}的相关度分数(单独计算): {relevance}")
        except Exception as e:
            logger.error(f"批量计算相关度分数时出错: {str(e)}")
            # 如果批量计算失败，使用单独计算
            for i, paper in enumerate(papers):
                relevance = calculate_relevance_improved(strategy, paper)
                paper['relevance_score'] = relevance
                # 同时设置relevance字段以保持兼容性
                paper['relevance'] = relevance
                if i < 5:  # 只记录前5篇文献的日志
                    logger.info(f"文献{i+1}的相关度分数(单独计算): {relevance}")
        
        # 应用筛选条件 - 确保传递原始查询
        filters['original_query'] = strategy  # 添加原始查询到过滤条件
        filtered_papers, stats = filter_papers_by_metrics(papers, filters)
        
        # 导出文件
        update_search_progress(session_id, 'exporting', "正在生成导出文件...", 90)
        
        # 导出初始结果和筛选后的结果 - 使用策略作为查询内容
        initial_excel, initial_word, initial_titles = export_papers(papers, strategy, 'sentence_initial')
        filtered_excel, filtered_word, filtered_titles = export_papers(filtered_papers, strategy, 'sentence_filtered')
        
        # 发送完成消息
        update_search_progress(session_id, 'complete', f"句子检索完成，找到 {len(filtered_papers)} 篇相关文献", 100)
            
        return jsonify({
            'success': True,
            'data': filtered_papers,
            'original_papers': papers,
            'search_strategy': strategy,
            'total_count': total_count,
            'filtered_count': len(filtered_papers),
            'export_path': filtered_excel,
            'report_path': filtered_word,
            'text_path': filtered_titles,
            'export_files': {
                'initial_excel': initial_excel,
                'initial_word': initial_word,
                'initial_titles': initial_titles,
                'filtered_excel': filtered_excel,
                'filtered_word': filtered_word,
                'filtered_titles': filtered_titles
            }
        })
        
    except Exception as e:
        logger.error(f"句子检索请求处理出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """获取用户消息历史"""
    try:
        session_id = request.headers.get('sid')
        if not session_id:
            return jsonify({
                'success': False,
                'error': '无效的会话ID'
            }), 400
            
        with user_stats_lock:
            messages = get_user_messages(session_id)
            return jsonify({
            'success': True,
            'messages': messages
        })
        
    except Exception as e:
        logger.error(f"获取消息历史出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500

@app.route('/api/session', methods=['DELETE'])
def clear_session():
    """清除用户会话"""
    try:
        session_id = request.headers.get('sid')
        if not session_id:
            return jsonify({
                'success': False,
                'error': '无效的会话ID'
            }), 400
        
        handle_disconnect(session_id)
        return jsonify({
            'success': True,
            'message': '会话已清除'
        })
    
    except Exception as e:
        logger.error(f"清除会话出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误'
        }), 500

@app.route('/api/stats')
def get_stats():
    """获取用户统计信息"""
    try:
        with user_stats_lock, performance_stats_lock:
            current_stats = {
                'total_visits': user_stats['total_visits'],
                'concurrent_users': user_stats['concurrent_users'],
                'peak_concurrent_users': user_stats['peak_concurrent_users'],
                'hourly_visits': get_hourly_visits(),
                'performance': {
                    'avg_response_time': performance_stats['avg_response_time'],
                    'error_rate': (performance_stats['error_count'] / performance_stats['request_count'] * 100) if performance_stats['request_count'] > 0 else 0
                }
            }
        return jsonify(current_stats)
    except Exception as e:
        logger.error(f"获取统计信息时出错: {str(e)}")
        return jsonify({
            'error': '获取统计信息失败'
        }), 500

@app.route('/admin')
def admin():
    """后台管理页面"""
    return render_template('admin.html')

# 启动所有后台线程
def start_background_tasks():
    """启动所有后台任务"""
    try:
        # 启动用户清理线程
        cleaning_thread = threading.Thread(target=clean_inactive_users, daemon=True)
        cleaning_thread.start()
        
        # 启动性能监控线程
        monitor_thread = threading.Thread(target=monitor_system_performance, daemon=True)
        monitor_thread.start()
        
        # 启动导出文件清理线程
        exports_cleaning_thread = threading.Thread(target=clean_exports_directory, daemon=True)
        exports_cleaning_thread.start()
        
        logger.info("所有后台任务已启动")
    except Exception as e:
        logger.error(f"启动后台任务时出错: {str(e)}")

def clean_inactive_users():
    """
    清理不活跃用户的后台任务
    
    每隔一定时间检查并清理超过MAX_CACHE_TIME（24小时）未活跃的用户会话
    """
    logger.info("启动用户清理线程")
    while True:
        try:
            current_time = datetime.now()
            inactive_users = []
            
            # 使用锁保护对用户数据的访问
            with user_stats_lock:
                # 检查所有用户
                for session_id, user_data in active_users.items():
                    last_active = user_data['last_active']
                    # 计算不活跃时间（秒）
                    inactive_time = (current_time - last_active).total_seconds()
                    
                    # 如果超过最大缓存时间，加入待清理列表
                    if inactive_time > MAX_CACHE_TIME:
                        inactive_users.append(session_id)
                
                # 清理不活跃用户
                for session_id in inactive_users:
                    logger.info(f"清理不活跃用户: {session_id}")
                    handle_disconnect(session_id)
                
                if inactive_users:
                    logger.info(f"已清理 {len(inactive_users)} 个不活跃用户")
                else:
                    logger.debug("没有需要清理的不活跃用户")
            
            # 每小时检查一次
            time.sleep(3600)
            
        except Exception as e:
            logger.error(f"清理不活跃用户时出错: {str(e)}\n{traceback.format_exc()}")
            # 发生错误时等待一段时间后继续
            time.sleep(300)

def clean_exports_directory():
    """
    清理导出目录中的旧文件
    
    每隔一定时间检查并清理超过MAX_CACHE_TIME（24小时）的导出文件
    """
    logger.info("启动导出文件清理线程")
    while True:
        try:
            current_time = datetime.now()
            files_removed = 0
            
            # 遍历导出目录中的所有文件
            for file_path in Path(EXPORTS_DIR).glob('*.*'):
                try:
                    # 获取文件的修改时间
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    # 计算文件存在时间（秒）
                    file_age = (current_time - file_mtime).total_seconds()
                    
                    # 如果文件超过最大缓存时间，删除它
                    if file_age > MAX_CACHE_TIME:
                        file_path.unlink()
                        files_removed += 1
                        logger.debug(f"已删除过期文件: {file_path}")
                except Exception as e:
                    logger.warning(f"删除文件 {file_path} 时出错: {str(e)}")
            
            if files_removed > 0:
                logger.info(f"已清理 {files_removed} 个过期导出文件")
            else:
                logger.debug("没有需要清理的过期导出文件")
            
            # 每6小时检查一次
            time.sleep(21600)
            
        except Exception as e:
            logger.error(f"清理导出文件时出错: {str(e)}\n{traceback.format_exc()}")
            # 发生错误时等待一段时间后继续
            time.sleep(300)

@app.route('/api/generate_strategy', methods=['POST'])
def generate_strategy():
    """生成检索策略"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        mode = data.get('mode', 'single')
        filters = data.get('filters', {})
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请输入检索内容'
            }), 400
            
        # 从请求头获取用户ID
        user_id = request.headers.get('userId')
        
        # 详细记录请求信息
        logger.info(f"生成检索策略 - 请求体: {data}")
        logger.info(f"生成检索策略 - 请求头: {dict(request.headers)}")
        logger.info(f"生成检索策略 - 用户ID: {user_id}")
        
        if not user_id:
            # 如果没有用户ID，返回需要登录的响应
            logger.warning("生成检索策略 - 未提供userId，需要登录")
            return jsonify({
                'success': False,
                'error': 'login_required',
                'redirect_url': 'https://www.nnscholar.com/auth/signin'
            }), 401
            
        # 获取当前用户的会话ID
        session_id = request.headers.get('sid')
        if not session_id:
            return jsonify({
                'success': False,
                'error': '无效的会话ID'
            }), 400
            
        # 更新用户活跃状态
        handle_connect(session_id)
        
        # 调用Token API检查并减少用户的credit（已禁用，始终返回成功）
        token_result = reduce_tokens(
            user_id=user_id,
            amount=2000,
            service_id="nnscholar",
            reason="generate_search_strategy"
        )
        
        # 记录禁用积分检查的日志
        logger.info(f"积分检查已禁用 - 用户ID: {user_id}")
        logger.info(f"生成检索策略 - 请求头中的userId: {user_id}")
        logger.info(f"生成检索策略 - Token API响应: {token_result}")
        
        # 积分检查已禁用，跳过所有检查步骤
        
        # 发送开始生成的进度信息
        update_search_progress(session_id, 'strategy_progress', "开始生成检索策略...", 0)
        
        if mode == 'paragraph':
            # 段落模式：分句并为每个句子生成检索策略
            sentences = split_paragraph_to_sentences(query)
            if not sentences:
                return jsonify({
                    'success': True,
                    'sentences': []
                })
            
            # 为每个句子生成检索策略
            results = []
            for i, sentence in enumerate(sentences, 1):
                try:
                    # 更新进度
                    progress = (i / len(sentences)) * 100
                    update_search_progress(session_id, 'strategy_progress', 
                                        f"正在为第 {i}/{len(sentences)} 个句子生成检索策略", progress)
                    
                    # 生成检索策略
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
                    logger.info(f"为句子生成的检索策略: {search_strategy}")
                    
                    # 构建年份限制
                    year_filter = ""
                    if filters and 'year_start' in filters and 'year_end' in filters:
                        year_start = filters.get('year_start')
                        year_end = filters.get('year_end')
                        if year_start and year_end:
                            year_filter = f' AND ("{year_start}"[Date - Publication] : "{year_end}"[Date - Publication])'
                    
                    # 添加年份限制
                    if year_filter:
                        search_strategy = f"({search_strategy}){year_filter}"
                    
                    results.append({
                        'text': sentence,
                        'search_strategy': search_strategy
                    })
                    
                    # 添加日志
                    logger.info(f"第 {i} 个句子的检索策略生成完成")
                    
                except Exception as e:
                    logger.error(f"处理句子时出错: {str(e)}")
                    continue
            
            # 发送完成消息
            update_search_progress(session_id, 'strategy_complete', 
                                f"检索策略生成完成，共处理 {len(results)} 个句子", 100)
            
            return jsonify({
                'success': True,
                'sentences': results
            })
            
        else:
            # 单句模式：生成单个检索策略
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

            try:
                search_strategy = call_deepseek_api(prompt)
                logger.info(f"生成的检索策略: {search_strategy}")
                
                # 构建年份限制
                year_filter = ""
                if filters and 'year_start' in filters and 'year_end' in filters:
                    year_start = filters.get('year_start')
                    year_end = filters.get('year_end')
                    if year_start and year_end:
                        year_filter = f' AND ("{year_start}"[Date - Publication] : "{year_end}"[Date - Publication])'
                
                # 添加年份限制
                if year_filter:
                    search_strategy = f"({search_strategy}){year_filter}"
                
                update_search_progress(session_id, 'strategy_complete', "检索策略生成完成", 100)
                
                return jsonify({
                    'success': True,
                    'search_strategy': search_strategy
                })
                
            except Exception as e:
                logger.error(f"生成检索策略时出错: {str(e)}")
                update_search_progress(session_id, 'strategy_error', f"生成检索策略失败: {str(e)}", 100)
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
                
    except Exception as e:
        logger.error(f"生成检索策略时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/test-keywords', methods=['POST'])
def test_keywords():
    """测试关键词提取功能"""
    try:
        data = request.json
        query = data.get('query', '')
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请提供检索词'
            }), 400
            
        # 初始化分析器
        analyzer = JournalAnalyzer()
        
        # 获取文章数据
        articles = analyzer.fetch_journal_articles(query)
        
        if not articles:
            return jsonify({
                'success': False,
                'error': '未找到相关文章'
            }), 404
            
        # 测试关键词提取
        test_results = analyzer.test_extract_keywords(articles)
        
        # 生成词云数据（仅使用关键词）
        wordcloud_data = analyzer.extract_keywords(articles)[:50]  # 限制50个关键词
        
        # 准备返回数据
        response_data = {
            'success': True,
            'test_results': test_results,
            'wordcloud_data': wordcloud_data,
            'total_articles': len(articles)
        }
        
        logger.info(f"测试完成，数据预览:")
        logger.info(f"从关键词字段提取: {len(test_results['from_keywords'])} 个关键词")
        logger.info(f"从标题中提取: {len(test_results['from_titles'])} 个关键词")
        logger.info(f"重叠关键词: {len(test_results['overlap'])} 个")
        logger.info(f"词云数据: {len(wordcloud_data)} 个关键词")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"关键词提取测试失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'测试失败: {str(e)}'
        }), 500

def expand_keywords(keywords):
    """提取基本关键词"""
    # 提取括号中的缩写
    abbreviations = re.findall(r'\(([A-Z]+)\)', keywords)
    
    # 提取主要医学术语
    key_terms = []
    medical_terms = [
        'Coronary computed tomography angiography',
        'CCTA',
        'atherosclerotic plaque',
        'coronary'
    ]
    
    for term in medical_terms:
        if term.lower() in keywords.lower():
            key_terms.append(term)
    
    # 合并缩写和关键词，限制数量
    all_terms = key_terms + abbreviations
    return list(set(all_terms))[:3]  # 最多返回3个关键词

def reduce_tokens(user_id, amount=2000, service_id="nnscholar", reason=None):
    """
    减少用户的token数量（已禁用积分检查，始终返回成功）
    
    参数:
        user_id (str): 用户ID
        amount (int): 要减少的token数量，默认为1
        service_id (str): 服务ID，默认为"nnscholar"
        reason (str, optional): 使用原因，可选
    
    返回:
        dict: 包含操作结果的响应
    """
    # 记录函数调用，但不实际检查积分
    logger.info(f"积分检查已禁用 - 用户ID: {user_id}, 请求数量: {amount}")
    
    # 始终返回成功响应
    return {
        "success": True, 
        "data": {
            "totalRemaining": 999999,  # 假设用户有大量积分
            "amountReduced": amount
        },
        "message": "积分检查已禁用，返回默认成功响应"
    }

# 添加文件下载路由
@app.route('/exports/<path:filename>')
def download_file(filename):
    """
    处理文件下载请求
    
    Args:
        filename: 文件名
        
    Returns:
        Response: 文件下载响应
    """
    try:
        logger.info(f"请求下载文件: {filename}")
        
        # 检查是否是内存中的文件
        for file_id, file_info in memory_exports.items():
            if file_info['filename'] == filename:
                logger.info(f"在内存中找到文件: {filename}")
                # 从内存中获取文件
                file_data = file_info['data']
                file_data.seek(0)  # 确保从头开始读取
                
                # 返回文件流
                return send_file(
                    file_data,
                    mimetype=file_info['mimetype'],
                    as_attachment=True,
                    download_name=filename
                )
        
        # 如果内存中没有找到，尝试从磁盘读取（兼容旧版本）
        logger.warning(f"内存中未找到文件: {filename}，尝试从磁盘读取")
        disk_path = os.path.join(EXPORTS_DIR, filename)
        if os.path.exists(disk_path):
            logger.info(f"在磁盘上找到文件: {disk_path}")
            return send_file(
                disk_path,
                as_attachment=True,
                download_name=filename
            )
        
        logger.error(f"文件不存在: {filename}")
        return jsonify({"error": f"文件不存在: {filename}"}), 404
    
    except Exception as e:
        logger.error(f"下载文件时发生错误: {str(e)}")
        return jsonify({"error": f"下载文件失败: {str(e)}"}), 500

@app.route('/api/download/<path:file_id>', methods=['GET'])
def api_download(file_id):
    """
    通过API下载文件
    
    Args:
        file_id: 文件ID
        
    Returns:
        Response: 文件下载响应
    """
    try:
        logger.info(f"API请求下载文件ID: {file_id}")
        
        # 检查是否是内存中的文件
        if file_id in memory_exports:
            logger.info(f"在内存中找到文件ID: {file_id}")
            file_info = memory_exports[file_id]
            
            # 确保文件数据是BytesIO对象
            if isinstance(file_info['data'], BytesIO):
                file_data = file_info['data']
            else:
                logger.error(f"文件数据格式错误: {type(file_info['data'])}")
                return jsonify({"error": "文件数据格式错误"}), 500
            
            file_data.seek(0)  # 确保从头开始读取
            
            # 返回文件流
            return send_file(
                file_data,
                mimetype=file_info['mimetype'],
                as_attachment=True,
                download_name=file_info['filename']
            )
        
        logger.error(f"文件ID不存在: {file_id}")
        return jsonify({"error": f"文件ID不存在: {file_id}"}), 404
    
    except Exception as e:
        logger.error(f"API下载文件时发生错误: {str(e)}")
        return jsonify({"error": f"下载文件失败: {str(e)}"}), 500

# 定期清理内存中的导出文件
def clean_memory_exports():
    """定期清理内存中的导出文件，删除超过24小时的文件"""
    while True:
        try:
            current_time = datetime.now()
            files_to_remove = []
            
            # 查找过期的文件
            for file_id, file_info in memory_exports.items():
                file_age = (current_time - file_info['timestamp']).total_seconds()
                if file_age > MAX_CACHE_TIME:
                    files_to_remove.append(file_id)
            
            # 删除过期的文件
            for file_id in files_to_remove:
                del memory_exports[file_id]
                logger.info(f"已从内存中删除过期文件: {file_id}")
            
            # 每小时检查一次
            time.sleep(3600)
        
        except Exception as e:
            logger.error(f"清理内存导出文件时发生错误: {str(e)}")
            time.sleep(3600)  # 出错后等待一小时再试

# 启动内存清理线程
memory_exports_cleaning_thread = threading.Thread(target=clean_memory_exports, daemon=True)
memory_exports_cleaning_thread.start()

@app.route('/api/export', methods=['POST'])
def api_export():
    """处理导出请求"""
    try:
        data = request.get_json()
        export_format = data.get('format', 'excel')
        papers = data.get('papers', [])
        all_papers = data.get('all_papers', papers)  # 获取初始表格中的所有文献
        query = data.get('query', '')
        
        if not papers:
            return jsonify({
                'success': False,
                'error': '没有可导出的文献'
            }), 400
            
        # 确定导出类型
        is_pro_version = (export_format == 'excel_pro')
        export_type = 'pro' if is_pro_version else 'standard'
        
        # 记录导出请求
        logger.info(f"收到导出请求: 格式={export_format}, 选择文献数量={len(papers)}, 初始表格文献数量={len(all_papers)}, 查询={query}, 类型={export_type}")
        
        if is_pro_version:
            logger.info("用户选择了Pro版本导出，将生成文献摘要和创新点分析")
            # 记录一些文献信息，帮助调试
            for i, paper in enumerate(papers[:3]):  # 只记录前3篇文献
                paper_id = paper.get('pmid', '')
                title = paper.get('title', '')
                logger.info(f"文献样本 {i+1}: ID={paper_id}, 标题={title[:50]}...")
        
        # 预先计算所有文献的相关度（使用初始表格中的所有文献）
        # 相关度分析默认进行，无论导出类型如何
        try:
            logger.info(f"开始预计算初始表格中所有{len(all_papers)}篇文献的相关度")
            start_time = time.time()
            all_relevance_scores = {}
            
            # 批量计算所有文献的相关度
            batch_scores = calculate_batch_embedding_relevance(query, all_papers)
            
            # 更新分数字典
            for i, paper in enumerate(all_papers):
                paper_id = paper.get('pmid', str(i))
                if i < len(batch_scores):
                    all_relevance_scores[paper_id] = batch_scores[i]
            
            elapsed = time.time() - start_time
            logger.info(f"预计算相关度完成，耗时: {elapsed:.2f}秒")
            
            # 将相关度分数添加到每篇文献中
            for paper in papers:
                paper_id = paper.get('pmid', '')
                if paper_id in all_relevance_scores:
                    paper['relevance_score'] = all_relevance_scores[paper_id]
        except Exception as e:
            logger.error(f"预计算相关度失败: {str(e)}")
        
        # 根据导出格式调用相应的导出函数
        if export_format == 'excel':
            # 标准Excel导出，不生成摘要和创新点
            file_path = export_papers_to_excel(papers, query, export_type='standard')
        elif export_format == 'excel_pro':
            # Pro版Excel导出，生成摘要和创新点
            file_path = export_papers_to_excel(papers, query, export_type='pro', file_suffix='_pro')
        elif export_format == 'word':
            # Word导出，不生成摘要和创新点
            file_path = export_papers_to_word(papers, query)
        else:
            return jsonify({
                'success': False,
                'error': f'不支持的导出格式: {export_format}'
            }), 400
            
        if not file_path:
            return jsonify({
                'success': False,
                'error': '导出失败'
            }), 500
            
        # 获取文件名
        file_name = os.path.basename(file_path)
        
        # 返回下载链接
        return jsonify({
            'success': True,
            'file_id': file_name,
            'download_url': f'/api/download/{file_name}'
        })
    
    except Exception as e:
        logger.error(f"处理导出请求时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def calculate_combined_relevance(query, paper, use_batch=False, papers=None, batch_size=10):
    """
    综合计算文献与查询的相关度，优先使用嵌入模型，如果不可用则回退到规则相关度
    
    Args:
        query (str): 用户查询
        paper (dict): 文献信息
        use_batch (bool): 是否使用批量计算
        papers (list): 文献列表，用于批量计算
        batch_size (int): 每批处理的文献数量
    
    Returns:
        float 或 dict: 单篇文献的相关度分数或多篇文献的相关度分数字典
    """
    try:
        # 获取API配置
        api_config = get_api_config(log_info=False)
        embedding_api_key = api_config.get('embedding_api_key')
        
        # 批量计算模式
        if use_batch and papers:
            # 如果配置了嵌入模型API，则使用批量嵌入模型计算相关度
            if embedding_api_key:
                try:
                    return calculate_batch_embedding_relevance(query, papers, batch_size)
                except Exception as e:
                    logger.error(f"批量嵌入模型相关度计算失败: {str(e)}")
                    logger.info("回退到单篇规则相关度计算")
            
            # 如果没有配置嵌入模型API或批量计算失败，则使用规则相关度计算
            return {paper.get('pmid', i): calculate_relevance_improved(query, paper) 
                   for i, paper in enumerate(papers)}
        
        # 单篇计算模式
        else:
            # 如果配置了嵌入模型API，则使用嵌入模型计算相关度
            if embedding_api_key:
                try:
                    return calculate_embedding_relevance(query, paper)
                except Exception as e:
                    logger.error(f"嵌入模型相关度计算失败: {str(e)}")
                    logger.info("回退到规则相关度计算")
            
            # 如果没有配置嵌入模型API或计算失败，则使用规则相关度计算
            return calculate_relevance_improved(query, paper)
        
    except Exception as e:
        logger.error(f"计算综合相关度时出错: {str(e)}")
        if use_batch and papers:
            return {paper.get('pmid', i): 0.0 for i, paper in enumerate(papers)}
        return 0.0

def calculate_batch_embedding_relevance(query, papers, batch_size=15):
    """
    批量计算多篇文献与查询的嵌入相关度，使用多线程加速处理
    
    Args:
        query (str): 用户查询
        papers (list): 文献列表
        batch_size (int): 每批处理的文献数量
        
    Returns:
        list: 相关度分数列表
    """
    # 获取API配置（只获取一次）
    api_url = os.getenv('EMBEDDING_API_URL', 'https://api.siliconflow.cn/v1/embeddings')
    api_key = os.getenv('EMBEDDING_API_KEY', os.getenv('DEEPSEEK_API_KEY'))
    model = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
    
    # 记录API配置（只记录一次）
    logger.info(f"批量计算嵌入相关度 - API: {api_url}, 模型: {model}, 文献数: {len(papers)}")
    
    # 准备请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 准备所有文献的文本
    paper_texts = []
    for paper in papers:
        title = paper.get('title', '')
        abstract = paper.get('abstract', '')
        keywords = paper.get('keywords', [])
        keywords_str = ', '.join(keywords) if keywords else ''
        
        paper_text = f"标题: {title}\n摘要: {abstract}\n关键词: {keywords_str}"
        paper_texts.append(paper_text)
    
    def process_batch(batch_start):
        """处理单个批次的文献"""
        batch_texts = paper_texts[batch_start:batch_start + batch_size]
        batch_scores = []
        
        try:
            # 准备批量请求数据
            inputs = [query] + batch_texts
            data = {
                "model": model,
                "input": inputs
            }
            
            # 记录批次信息
            logger.info(f"处理批次 {batch_start//batch_size + 1}/{(len(papers)-1)//batch_size + 1}, 文献数: {len(batch_texts)}")
            
            # 发送请求
            response = requests.post(api_url, headers=headers, json=data)
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            
            if 'data' in result and len(result['data']) >= len(inputs):
                # 获取查询的嵌入向量
                query_embedding = result['data'][0]['embedding']
                
                # 计算每篇文献的相关度
                for j in range(1, len(result['data'])):
                    paper_embedding = result['data'][j]['embedding']
                    similarity = cosine_similarity(query_embedding, paper_embedding)
                    relevance_score = round(similarity * 100, 1)
                    batch_scores.append(relevance_score)
                    logger.info(f"批次 {batch_start//batch_size + 1} 文献 {j} 相关度: {relevance_score}")
                
                # 记录批次结果
                logger.info(f"批次 {batch_start//batch_size + 1} 相关度计算完成，分数范围: {min(batch_scores) if batch_scores else 0}-{max(batch_scores) if batch_scores else 0}")
            else:
                logger.error(f"嵌入API批量响应格式错误: {result}")
                # 填充零分数
                batch_scores.extend([0.0] * len(batch_texts))
                
        except Exception as e:
            logger.error(f"处理批次 {batch_start//batch_size + 1} 时出错: {str(e)}")
            # 填充零分数
            batch_scores.extend([0.0] * len(batch_texts))
            
        return batch_start, batch_scores
    
    try:
        # 使用线程池并发处理批次
        all_scores = [0.0] * len(papers)  # 预分配结果列表
        with ThreadPoolExecutor(max_workers=5) as executor:  # 最多5个并发线程
            # 提交所有批次的任务
            future_to_batch = {
                executor.submit(process_batch, i): i 
                for i in range(0, len(papers), batch_size)
            }
            
            # 收集结果
            for future in as_completed(future_to_batch):
                batch_start, batch_scores = future.result()
                # 将批次结果放入正确的位置
                for i, score in enumerate(batch_scores):
                    if batch_start + i < len(all_scores):
                        all_scores[batch_start + i] = score
        
        # 记录所有分数
        logger.info("所有文献的相关度分数:")
        for i, score in enumerate(all_scores):
            logger.info(f"文献 {i+1}: {score}")
        
        return all_scores
        
    except Exception as e:
        logger.error(f"批量计算嵌入相关度时出错: {str(e)}")
        # 如果整个批处理过程失败，返回所有零分数
        return [0.0] * len(papers)

def test_embedding_api():
    """
    测试嵌入模型API是否可用
    
    Returns:
        tuple: (是否可用, 错误信息)
    """
    try:
        # 获取API配置
        api_config = get_api_config(log_info=False)
        embedding_api_key = api_config.get('embedding_api_key')
        embedding_api_url = api_config.get('embedding_api_url')
        embedding_model = api_config.get('embedding_model')
        
        if not embedding_api_key or not embedding_api_url:
            return False, "嵌入模型API配置不完整"
        
        # 准备API请求头
        headers = {
            'Authorization': f'Bearer {embedding_api_key}',
            'Content-Type': 'application/json'
        }
        
        # 准备测试数据
        data = {
            'model': embedding_model,
            'input': ["这是一个测试"],
            'encoding_format': 'float'  # 指定返回浮点数格式的嵌入向量
        }
        
        logger.info(f"测试嵌入模型API: {embedding_api_url}")
        logger.info(f"使用模型: {embedding_model}")
        logger.info(f"请求数据: {data}")
        
        # 记录请求头（不包含完整API密钥）
        masked_key = f"{embedding_api_key[:4]}...{embedding_api_key[-4:]}"
        logger.info(f"请求头: Content-Type={headers['Content-Type']}, Authorization=Bearer {masked_key}")
        
        # 发送测试请求
        try:
            start_time = time.time()
            response = requests.post(
                embedding_api_url,
                headers=headers,
                json=data,
                timeout=30
            )
            request_time = time.time() - start_time
            logger.info(f"API请求耗时: {request_time:.2f}秒")
        except Exception as e:
            logger.error(f"发送API请求时出错: {str(e)}")
            return False, f"发送API请求时出错: {str(e)}"
        
        # 记录响应状态
        logger.info(f"API测试响应状态码: {response.status_code}")
        
        # 如果响应不成功，记录响应内容
        if response.status_code != 200:
            logger.error(f"API测试响应内容: {response.text}")
            return False, f"API返回错误: HTTP {response.status_code} - {response.text}"
        
        # 解析JSON响应
        response_data = response.json()
        
        # 验证响应格式
        if 'data' not in response_data or not response_data['data']:
            return False, f"API响应格式错误: {response_data}"
        
        # 验证嵌入向量
        embedding = response_data['data'][0].get('embedding')
        if not embedding or not isinstance(embedding, list):
            return False, f"API返回的嵌入向量格式错误: {response_data['data'][0]}"
        
        logger.info(f"嵌入模型API测试成功，向量维度: {len(embedding)}")
        return True, None
        
    except Exception as e:
        error_msg = f"测试嵌入模型API时出错: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False, error_msg

def generate_paper_insights(paper, query):
    """
    使用DeepSeek API生成文献的总结摘要和创新点分析
    
    Args:
        paper (dict): 文献信息字典
        query (str): 用户查询
        
    Returns:
        tuple: (总结摘要, 创新点分析)
    """
    try:
        # 构建提示词
        title = paper.get('title', '')
        authors = ', '.join(paper.get('authors', []))
        year = paper.get('pub_year', '')
        keywords = ', '.join(paper.get('keywords', []))
        abstract = paper.get('abstract', '')
        paper_id = paper.get('pmid', '')
        
        logger.info(f"开始为文献生成摘要和创新点 (ID: {paper_id})")
        
        prompt = f"""
        请分析以下学术文献，并用中文提供简明的总结摘要和创新点分析：
        
        标题: {title}
        作者: {authors}
        发表年份: {year}
        关键词: {keywords}
        摘要: {abstract}
        用户查询: {query}
        
        请以JSON格式返回以下内容:
        {{
            "summary": "对文章内容的简明总结，100字以内，必须使用中文",
            "innovation": "文章的主要创新点和贡献，100字以内，必须使用中文"
        }}
        """
        
        logger.info(f"生成的提示词长度: {len(prompt)}")
        
        # 调用DeepSeek API
        logger.info("开始调用DeepSeek API")
        response = call_deepseek_api(prompt)
        logger.info("DeepSeek API调用完成")
        
        # 解析响应
        if response and 'choices' in response:
            content = response['choices'][0]['message']['content']
            logger.info(f"API响应内容前100字符: {content[:100]}...")
            
            # 预处理内容，移除可能的代码块标记
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            
            # 尝试解析JSON
            try:
                logger.info("尝试解析JSON响应")
                result = json.loads(content)
                summary = result.get('summary', '未能生成摘要')
                innovation = result.get('innovation', '未能生成创新点分析')
                
                # 限制字数
                if len(summary) > 100:
                    summary = summary[:97] + '...'
                if len(innovation) > 100:
                    innovation = innovation[:97] + '...'
                
                logger.info(f"成功解析JSON，摘要长度: {len(summary)}, 创新点长度: {len(innovation)}")
                
                # 确保内容为中文
                if not any('\u4e00' <= char <= '\u9fff' for char in summary):
                    logger.warning("摘要不包含中文字符，可能需要翻译")
                    summary = f"摘要(需翻译): {summary}"
                
                if not any('\u4e00' <= char <= '\u9fff' for char in innovation):
                    logger.warning("创新点不包含中文字符，可能需要翻译")
                    innovation = f"创新点(需翻译): {innovation}"
                
                return summary, innovation
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {str(e)}")
                
                # 如果JSON解析失败，使用正则表达式提取信息
                summary_pattern = r'"summary"\s*:\s*"([^"]+)"'
                innovation_pattern = r'"innovation"\s*:\s*"([^"]+)"'
                
                summary_match = re.search(summary_pattern, content)
                innovation_match = re.search(innovation_pattern, content)
                
                if summary_match or innovation_match:
                    summary = summary_match.group(1) if summary_match else '未能解析摘要'
                    innovation = innovation_match.group(1) if innovation_match else '未能解析创新点分析'
                    
                    # 限制字数
                    if len(summary) > 100:
                        summary = summary[:97] + '...'
                    if len(innovation) > 100:
                        innovation = innovation[:97] + '...'
                    
                    logger.info(f"使用正则表达式提取，摘要长度: {len(summary)}, 创新点长度: {len(innovation)}")
                    
                    return summary, innovation
                else:
                    # 如果正则表达式也失败，尝试直接提取内容
                    logger.info("正则表达式提取失败，尝试直接提取内容")
                    
                    # 查找"summary"和"innovation"关键词
                    summary_pos = content.find("summary")
                    innovation_pos = content.find("innovation")
                    
                    if summary_pos > 0 and innovation_pos > 0:
                        # 提取两个关键词之间的内容作为摘要
                        summary_start = content.find(":", summary_pos) + 1
                        summary_end = innovation_pos
                        if summary_start > 0 and summary_end > summary_start:
                            summary = content[summary_start:summary_end].strip().strip('",:')
                        
                        # 提取innovation后面的内容作为创新点
                        innovation_start = content.find(":", innovation_pos) + 1
                        if innovation_start > 0:
                            innovation = content[innovation_start:].strip().strip('",:}')
                        
                        # 限制字数
                        if len(summary) > 100:
                            summary = summary[:97] + '...'
                        if len(innovation) > 100:
                            innovation = innovation[:97] + '...'
                        
                        logger.info(f"直接提取内容，摘要长度: {len(summary)}, 创新点长度: {len(innovation)}")
                        return summary, innovation
        
        logger.warning("API响应无效或为空")
        return '未能生成摘要', '未能生成创新点分析'
    except Exception as e:
        logger.error(f"生成文献洞察时出错: {str(e)}")
        return '生成过程出错', '生成过程出错'

def generate_batch_paper_insights(papers, query, batch_size=5):
    """
    批量生成多篇文献的总结摘要和创新点分析
    
    Args:
        papers (list): 文献列表
        query (str): 用户查询
        batch_size (int): 每批处理的文献数量
        
    Returns:
        dict: 文献ID到(总结摘要,创新点分析)的映射
    """
    results = {}
    
    # 筛选相关度高的文献
    relevant_papers = []
    logger.info(f"开始筛选相关度高的文献，总文献数: {len(papers)}")
    
    for paper in papers:
        paper_id = paper.get('pmid', '')
        if not paper_id:
            paper_id = str(hash(paper.get('title', '')))  # 使用标题哈希作为备用ID
            logger.warning(f"文献没有PMID，使用标题哈希作为ID: {paper_id}")
        
        # 检查是否已有相关度分数
        if 'relevance_score' in paper:
            relevance_score = paper['relevance_score']
            logger.info(f"使用预计算的相关度分数: {relevance_score} (ID: {paper_id})")
        else:
            # 计算相关度
            try:
                relevance_score = calculate_embedding_relevance(query, paper)
                logger.info(f"计算得到的相关度分数: {relevance_score} (ID: {paper_id})")
            except Exception as e:
                logger.error(f"计算文献相关度时出错: {str(e)}")
                relevance_score = 0.0
        
        # 设置相关度阈值为50
        if relevance_score >= 30:  # 调整为50
            paper['relevance_score'] = relevance_score
            relevant_papers.append(paper)
            logger.info(f"文献相关度 {relevance_score} >= 50，添加到处理列表 (ID: {paper_id})")
        else:
            logger.info(f"文献相关度 {relevance_score} < 50，不处理 (ID: {paper_id})")
    
    # 按相关度排序
    relevant_papers.sort(key=lambda p: p.get('relevance_score', 0), reverse=True)
    logger.info(f"按相关度排序后，待处理文献数: {len(relevant_papers)}")
    
    # 限制处理数量，最多处理前15篇最相关的文献
    relevant_papers = relevant_papers[:15]
    logger.info(f"限制处理数量后，实际处理文献数: {len(relevant_papers)}")
    
    # 如果没有相关文献，返回空结果
    if not relevant_papers:
        logger.warning("没有找到相关度足够高的文献，跳过生成摘要和创新点分析")
        return results
    
    # 分批处理
    for i in range(0, len(relevant_papers), batch_size):
        batch = relevant_papers[i:i+batch_size]
        logger.info(f"处理批次 {i//batch_size + 1}/{(len(relevant_papers)-1)//batch_size + 1}，文献数: {len(batch)}")
        
        # 构建批量提示词
        prompt = "请分析以下多篇学术文献，并用中文提供每篇文献的简明总结摘要和创新点分析。\n\n"
        
        # 记录批次中的文献ID，用于后续匹配
        batch_paper_ids = []
        
        for idx, paper in enumerate(batch):
            title = paper.get('title', '')
            authors = ', '.join(paper.get('authors', []))
            year = paper.get('pub_year', '')
            keywords = ', '.join(paper.get('keywords', []))
            abstract = paper.get('abstract', '')
            paper_id = paper.get('pmid', '')
            if not paper_id:
                paper_id = str(hash(title))
            
            batch_paper_ids.append(paper_id)
            
            prompt += f"""
            文献{idx+1} ID:{paper_id}
            标题: {title}
            作者: {authors}
            发表年份: {year}
            关键词: {keywords}
            摘要: {abstract}
            
            """
        
        prompt += f"""
        用户查询: {query}
        
        请以JSON格式返回分析结果，每篇文献包含总结摘要和创新点分析：
        {{
            "papers": [
                {{
                    "id": "文献ID",
                    "summary": "对文章内容的简明总结，100字以内，必须使用中文",
                    "innovation": "文章的主要创新点和贡献，100字以内，必须使用中文"
                }},
                ...
            ]
        }}
        """
        
        logger.info(f"生成的提示词长度: {len(prompt)}")
        
        try:
            # 调用DeepSeek API
            logger.info("开始调用DeepSeek API")
            response = call_deepseek_api(prompt)
            logger.info("DeepSeek API调用完成")
            
            # 记录API响应
            if response:
                logger.info(f"API响应状态: 成功")
                if 'choices' in response:
                    content = response['choices'][0]['message']['content']
                    logger.info(f"API响应内容前200字符: {content[:200]}...")
                    
                    # 保存完整响应到文件，便于调试
                    try:
                        with open(f"batch_response_{i}.json", "w", encoding="utf-8") as f:
                            f.write(content)
                        logger.info(f"已保存完整响应到文件: batch_response_{i}.json")
                    except Exception as e:
                        logger.error(f"保存响应文件失败: {str(e)}")
                else:
                    logger.warning(f"API响应中没有choices字段: {response.keys()}")
            else:
                logger.error("API响应为空")
            
            # 解析响应
            if response and 'choices' in response:
                content = response['choices'][0]['message']['content']
                
                # 预处理内容，移除可能的代码块标记
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                
                # 尝试解析JSON
                try:
                    logger.info("尝试解析JSON响应")
                    result = json.loads(content)
                    papers_results = result.get('papers', [])
                    logger.info(f"成功解析JSON，获取到{len(papers_results)}篇文献的结果")
                    
                    for paper_result in papers_results:
                        paper_id = paper_result.get('id')
                        if paper_id:
                            summary = paper_result.get('summary', '未能生成摘要')
                            innovation = paper_result.get('innovation', '未能生成创新点分析')
                            
                            # 限制字数
                            if len(summary) > 100:
                                summary = summary[:97] + '...'
                            if len(innovation) > 100:
                                innovation = innovation[:97] + '...'
                                
                            logger.info(f"添加文献结果 ID: {paper_id}, 摘要长度: {len(summary)}, 创新点长度: {len(innovation)}")
                            results[paper_id] = (summary, innovation)
                        else:
                            logger.warning(f"解析的结果中缺少id字段: {paper_result}")
                            
                            # 尝试通过索引匹配
                            idx = papers_results.index(paper_result)
                            if idx < len(batch_paper_ids):
                                paper_id = batch_paper_ids[idx]
                                summary = paper_result.get('summary', '未能生成摘要')
                                innovation = paper_result.get('innovation', '未能生成创新点分析')
                                
                                # 限制字数
                                if len(summary) > 100:
                                    summary = summary[:97] + '...'
                                if len(innovation) > 100:
                                    innovation = innovation[:97] + '...'
                                    
                                logger.info(f"通过索引匹配添加文献结果 ID: {paper_id}")
                                results[paper_id] = (summary, innovation)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {str(e)}")
                    logger.info("尝试使用正则表达式提取信息")
                    
                    # 如果JSON解析失败，尝试使用正则表达式提取
                    for idx, paper in enumerate(batch):
                        paper_id = paper.get('pmid', '')
                        if not paper_id:
                            paper_id = str(hash(paper.get('title', '')))
                        
                        # 尝试多种模式匹配
                        patterns = [
                            f'ID:{paper_id}',
                            f'"id"\\s*:\\s*"{paper_id}"',
                            f'"id"\\s*:\\s*{paper_id}',
                            f'文献{idx+1}'
                        ]
                        
                        matched = False
                        for pattern in patterns:
                            if re.search(pattern, content, re.IGNORECASE):
                                matched = True
                                # 查找摘要和创新点
                                summary_pattern = r'"summary"\s*:\s*"([^"]+)"'
                                innovation_pattern = r'"innovation"\s*:\s*"([^"]+)"'
                                
                                summary_match = re.search(summary_pattern, content)
                                innovation_match = re.search(innovation_pattern, content)
                                
                                summary = summary_match.group(1) if summary_match else '未能解析摘要'
                                innovation = innovation_match.group(1) if innovation_match else '未能解析创新点分析'
                                
                                # 限制字数
                                if len(summary) > 100:
                                    summary = summary[:97] + '...'
                                if len(innovation) > 100:
                                    innovation = innovation[:97] + '...'
                                
                                logger.info(f"使用正则表达式提取 ID: {paper_id}, 摘要长度: {len(summary)}, 创新点长度: {len(innovation)}")
                                results[paper_id] = (summary, innovation)
                                break
                        
                        if not matched:
                            logger.warning(f"未找到与ID:{paper_id}匹配的内容")
                            # 尝试为每篇文献单独生成
                            try:
                                logger.info(f"尝试为ID:{paper_id}单独生成内容")
                                summary, innovation = generate_paper_insights(paper, query)
                                results[paper_id] = (summary, innovation)
                            except Exception as e:
                                logger.error(f"单独生成内容失败: {str(e)}")
                                results[paper_id] = ('生成过程出错', '生成过程出错')
        except Exception as e:
            logger.error(f"批量生成文献洞察时出错: {str(e)}")
            # 出错时尝试单独处理
            for paper in batch:
                paper_id = paper.get('pmid', '')
                if not paper_id:
                    paper_id = str(hash(paper.get('title', '')))
                
                try:
                    logger.info(f"尝试为ID:{paper_id}单独生成内容")
                    summary, innovation = generate_paper_insights(paper, query)
                    results[paper_id] = (summary, innovation)
                except Exception as e:
                    logger.error(f"单独生成内容失败: {str(e)}")
                    results[paper_id] = ('生成过程出错', '生成过程出错')
    
    logger.info(f"批量生成完成，共生成{len(results)}篇文献的摘要和创新点分析")
    return results

@app.route('/api/export-paragraph', methods=['POST'])
def export_paragraph():
    """导出段落模式的所有句子检索结果为一个完整的文档"""
    try:
        data = request.get_json()
        sentences_results = data.get('sentences_results', [])
        query = data.get('query', '')
        format_type = data.get('format', 'word')
        
        if not sentences_results:
            return jsonify({
                'success': False,
                'error': '没有可导出的句子检索结果'
            }), 400
            
        # 获取当前用户的会话ID
        session_id = request.headers.get('sid')
        if not session_id:
            return jsonify({
                'success': False,
                'error': '无效的会话ID'
            }), 400
            
        # 更新用户活跃状态
        handle_connect(session_id)
        
        try:
            # 发送开始导出的进度信息
            update_search_progress(session_id, 'paragraph_export', "开始导出段落分析结果...", 10)
            
            # 创建导出目录
            export_dir = os.path.join(app.root_path, 'exports')
            os.makedirs(export_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if format_type == 'excel':
                # 导出为Excel
                filename = f"nnscholar_paragraph_export_{timestamp}.xlsx"
                
                # 创建Excel工作簿
                wb = Workbook()
                ws = wb.active
                ws.title = "段落检索结果"
                
                # 添加标题行
                ws.append(["句子序号", "句子内容", "相关文献数量", "文献标题", "作者", "期刊", "年份", "影响因子", "JCR分区", "CAS分区", "相关度", "摘要"])
                
                # 填充数据
                for idx, sentence_result in enumerate(sentences_results, 1):
                    sentence_text = sentence_result.get('text', '')
                    papers = sentence_result.get('papers', [])
                    
                    if not papers:
                        # 如果没有相关文献，也添加句子信息
                        ws.append([idx, sentence_text, 0, "", "", "", "", "", "", "", "", ""])
                        continue
                    
                    # 为每篇相关文献添加一行
                    for i, paper in enumerate(papers):
                        journal_info = paper.get('journal_info', {})
                        authors = paper.get('authors', [])
                        authors_str = ", ".join(authors) if authors else "N/A"
                        
                        if i == 0:
                            # 第一篇文献带句子信息
                            ws.append([
                                idx, 
                                sentence_text, 
                                len(papers),
                                paper.get('title', ''),
                                authors_str,
                                journal_info.get('title', ''),
                                paper.get('pub_year', ''),
                                journal_info.get('impact_factor', ''),
                                journal_info.get('jcr_quartile', ''),
                                journal_info.get('cas_quartile', ''),
                                paper.get('relevance', ''),
                                paper.get('abstract', '')
                            ])
                        else:
                            # 后续文献不重复句子信息
                            ws.append([
                                "", 
                                "", 
                                "",
                                paper.get('title', ''),
                                authors_str,
                                journal_info.get('title', ''),
                                paper.get('pub_year', ''),
                                journal_info.get('impact_factor', ''),
                                journal_info.get('jcr_quartile', ''),
                                journal_info.get('cas_quartile', ''),
                                paper.get('relevance', ''),
                                paper.get('abstract', '')
                            ])
                
                # 调整列宽
                for col in ws.columns:
                    max_length = 0
                    column = col[0].column_letter
                    for cell in col:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    adjusted_width = (max_length + 2) * 1.2
                    # 对于摘要列，限制最大宽度为100
                    if column == get_column_letter(12):  # 摘要列
                        ws.column_dimensions[column].width = 100
                    else:
                        ws.column_dimensions[column].width = min(adjusted_width, 50)
                
                # 保存到内存
                excel_buffer = BytesIO()
                wb.save(excel_buffer)
                excel_buffer.seek(0)
                
                file_id = f"paragraph_{timestamp}_{format_type}"
                memory_exports[file_id] = {
                    'data': excel_buffer,
                    'filename': filename,
                    'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'timestamp': datetime.now()
                }
                
                update_search_progress(session_id, 'paragraph_export', "Excel导出完成", 100)
                
            elif format_type == 'word':
                # 导出为Word
                filename = f"nnscholar_paragraph_export_{timestamp}.docx"
                
                # 创建Word文档
                doc = Document()
                
                # 设置默认字体
                style = doc.styles['Normal']
                style.font.name = 'Times New Roman'
                style.font.size = Pt(10.5)
                
                # 添加标题
                title = add_paragraph_with_mixed_fonts(doc, '段落检索分析报告', is_bold=True, alignment=WD_ALIGN_PARAGRAPH.CENTER)
                title.style = doc.styles['Title']
                
                # 添加生成信息
                add_paragraph_with_mixed_fonts(doc, f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
                add_paragraph_with_mixed_fonts(doc, f'原始段落: {query}')
                add_paragraph_with_mixed_fonts(doc, f'句子数量: {len(sentences_results)}')
                
                # 添加分割线
                doc.add_paragraph().add_run('_' * 50)
                
                # 为每个句子创建一个部分
                for idx, sentence_result in enumerate(sentences_results, 1):
                    sentence_text = sentence_result.get('text', '')
                    papers = sentence_result.get('papers', [])
                    
                    # 添加句子标题
                    add_paragraph_with_mixed_fonts(doc, f'句子 {idx}', is_bold=True)
                    
                    # 添加原句
                    p = doc.add_paragraph()
                    run = p.add_run('原句：')
                    run.bold = True
                    set_run_font(run, True)  # 中文标签使用宋体
                    run = p.add_run(sentence_text)
                    set_run_font(run, is_chinese_text(sentence_text))
                    
                    # 添加文献数量
                    add_paragraph_with_mixed_fonts(doc, f'相关文献数量：{len(papers)}篇')
                    
                    if not papers:
                        p = doc.add_paragraph()
                        run = p.add_run('未找到相关文献')
                        run.italic = True
                        set_run_font(run, True)
                        doc.add_paragraph().add_run('_' * 30)
                        continue
                    
                    # 添加文献列表
                    add_paragraph_with_mixed_fonts(doc, '相关文献列表：', is_bold=True)
                    
                    for i, paper in enumerate(papers, 1):
                        journal_info = paper.get('journal_info', {})
                        authors = paper.get('authors', [])
                        authors_str = ", ".join(authors) if authors else "N/A"
                        
                        # 添加标题
                        p = doc.add_paragraph(style='List Number')
                        run = p.add_run(paper.get('title', ''))
                        run.bold = True
                        set_run_font(run, False)  # 文献标题通常是英文
                        
                        # 添加作者信息
                        p = doc.add_paragraph()
                        run = p.add_run('作者：')
                        run.bold = True
                        set_run_font(run, True)
                        run = p.add_run(authors_str)
                        set_run_font(run, False)
                        
                        # 添加期刊信息
                        p = doc.add_paragraph()
                        run = p.add_run('期刊：')
                        run.bold = True
                        set_run_font(run, True)
                        journal_text = f"{journal_info.get('title', '')} ({paper.get('pub_year', '')})"
                        run = p.add_run(journal_text)
                        set_run_font(run, False)
                        
                        # 添加影响因子和分区
                        p = doc.add_paragraph()
                        run = p.add_run('指标：')
                        run.bold = True
                        set_run_font(run, True)
                        metrics_text = f"IF: {journal_info.get('impact_factor', 'N/A')}, JCR: {journal_info.get('jcr_quartile', 'N/A')}, CAS: {journal_info.get('cas_quartile', 'N/A')}"
                        run = p.add_run(metrics_text)
                        set_run_font(run, False)
                        
                        # 添加相关度
                        p = doc.add_paragraph()
                        run = p.add_run('相关度：')
                        run.bold = True
                        set_run_font(run, True)
                        run = p.add_run(f"{paper.get('relevance', 'N/A')}%")
                        set_run_font(run, False)
                        
                        # 添加摘要
                        if paper.get('abstract'):
                            p = doc.add_paragraph()
                            run = p.add_run('摘要：')
                            run.bold = True
                            set_run_font(run, True)
                            run = p.add_run(paper.get('abstract', ''))
                            run.italic = True
                            set_run_font(run, False)
                        
                        # 添加分隔线
                        if i < len(papers):
                            doc.add_paragraph().add_run('- ' * 15)
                    
                    # 句子间分隔线
                    doc.add_paragraph().add_run('_' * 30)
                
                # 保存到内存
                word_buffer = BytesIO()
                doc.save(word_buffer)
                word_buffer.seek(0)
                
                file_id = f"paragraph_{timestamp}_{format_type}"
                memory_exports[file_id] = {
                    'data': word_buffer,
                    'filename': filename,
                    'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'timestamp': datetime.now()
                }
                
                update_search_progress(session_id, 'paragraph_export', "Word导出完成", 100)
            
            else:
                return jsonify({
                    'success': False,
                    'error': '不支持的导出格式'
                }), 400
            
            # 返回导出结果
            return jsonify({
                'success': True,
                'file_id': file_id,
                'download_url': f"/api/download/{file_id}",
                'message': f"段落分析结果已导出为{format_type.upper()}文件"
            })
            
        except Exception as e:
            logger.error(f"导出段落分析结果失败: {str(e)}\n{traceback.format_exc()}")
            update_search_progress(session_id, 'paragraph_export_error', f"导出失败: {str(e)}", 100)
            
            return jsonify({
                'success': False,
                'error': f"导出失败: {str(e)}"
            }), 500
            
    except Exception as e:
        logger.error(f"导出段落分析请求处理出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/export-sentence/<int:sentence_index>/<format_type>', methods=['GET'])
def export_sentence(sentence_index, format_type):
    try:
        # 从会话中获取句子检索结果
        sentence_results = session.get('sentence_results', [])
        if not sentence_results or sentence_index >= len(sentence_results):
            return jsonify({'error': '未找到对应的检索结果'}), 404
            
        result = sentence_results[sentence_index]
        if not result.get('success'):
            return jsonify({'error': '检索结果无效'}), 400
            
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'sentence_{sentence_index + 1}_{timestamp}'
        
        if format_type == 'excel':
            # 创建Excel文件
            wb = Workbook()
            ws = wb.active
            ws.title = f"句子{sentence_index + 1}检索结果"
            
            # 添加表头
            headers = ['标题', '作者', '期刊', '发表年份', '影响因子', 'JCR分区', 'CAS分区', '相关度']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
                cell.alignment = Alignment(horizontal='center')
            
            # 添加数据
            for row, paper in enumerate(result['data'], 2):
                journal_info = paper.get('journal_info', {})
                ws.cell(row=row, column=1, value=paper.get('title', ''))
                ws.cell(row=row, column=2, value=', '.join(paper.get('authors', [])))
                ws.cell(row=row, column=3, value=journal_info.get('title', ''))
                ws.cell(row=row, column=4, value=paper.get('pub_year', ''))
                ws.cell(row=row, column=5, value=journal_info.get('impact_factor', ''))
                ws.cell(row=row, column=6, value=journal_info.get('jcr_quartile', ''))
                ws.cell(row=row, column=7, value=journal_info.get('cas_quartile', ''))
                ws.cell(row=row, column=8, value=f"{paper.get('relevance', '')}%")
            
            # 调整列宽
            for col in range(1, len(headers) + 1):
                ws.column_dimensions[get_column_letter(col)].width = 15
            
            # 保存文件
            filepath = os.path.join('exports', f'{filename}.xlsx')
            wb.save(filepath)
            return send_file(filepath, as_attachment=True)
            
        elif format_type == 'word':
            # 创建Word文档
            doc = Document()
            
            # 添加标题
            title = doc.add_heading(f'句子 {sentence_index + 1} 检索结果', 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # 添加元数据
            meta = doc.add_paragraph()
            meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            meta.add_run(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            meta.add_run(f'检索到文献：{result.get("filtered_count", 0)} 篇\n')
            
            # 添加文献列表
            for paper in result['data']:
                journal_info = paper.get('journal_info', {})
                
                # 添加标题
                title = doc.add_paragraph()
                title.add_run(paper.get('title', '')).bold = True
                
                # 添加作者信息
                authors = doc.add_paragraph()
                authors.add_run('作者：').bold = True
                authors.add_run(', '.join(paper.get('authors', [])))
                
                # 添加期刊信息
                journal = doc.add_paragraph()
                journal.add_run('期刊：').bold = True
                journal.add_run(journal_info.get('title', ''))
                
                # 添加其他信息
                info = doc.add_paragraph()
                info.add_run(f"发表年份：{paper.get('pub_year', '')}\n")
                info.add_run(f"影响因子：{journal_info.get('impact_factor', '')}\n")
                info.add_run(f"JCR分区：{journal_info.get('jcr_quartile', '')}\n")
                info.add_run(f"CAS分区：{journal_info.get('cas_quartile', '')}\n")
                info.add_run(f"相关度：{paper.get('relevance', '')}%")
                
                # 添加分隔线
                doc.add_paragraph('_' * 50)
            
            # 保存文件
            filepath = os.path.join('exports', f'{filename}.docx')
            doc.save(filepath)
            return send_file(filepath, as_attachment=True)
            
        else:
            return jsonify({'error': '不支持的导出格式'}), 400
            
    except Exception as e:
        print(f"导出句子 {sentence_index + 1} 失败: {str(e)}")
        return jsonify({'error': f'导出失败: {str(e)}'}), 500

def set_run_font(run, is_chinese=False):
    """设置run的字体
    
    Args:
        run: docx run对象
        is_chinese (bool): 是否是中文文本
    """
    font = run.font
    if is_chinese:
        # 中文使用宋体
        font.name = '宋体'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    else:
        # 英文使用Times New Roman
        font.name = 'Times New Roman'
    font.size = Pt(10.5)  # 设置字号为五号

def is_chinese_text(text):
    """判断文本是否包含中文字符
    
    Args:
        text (str): 要判断的文本
        
    Returns:
        bool: 是否包含中文字符
    """
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def add_paragraph_with_mixed_fonts(doc, text, is_bold=False, alignment=None):
    """添加包含中英文的段落，自动设置不同字体
    
    Args:
        doc: docx文档对象
        text (str): 要添加的文本
        is_bold (bool): 是否加粗
        alignment: 对齐方式
    
    Returns:
        paragraph: 添加的段落对象
    """
    p = doc.add_paragraph()
    if alignment:
        p.alignment = alignment
    
    # 分割文本为中文和英文部分
    current_text = ""
    current_is_chinese = None
    
    for char in text:
        is_char_chinese = '\u4e00' <= char <= '\u9fff'
        
        # 如果字符类型改变，或者是最后一个字符
        if current_is_chinese is not None and is_char_chinese != current_is_chinese:
            # 添加当前积累的文本
            run = p.add_run(current_text)
            run.bold = is_bold
            set_run_font(run, current_is_chinese)
            current_text = ""
        
        current_text += char
        current_is_chinese = is_char_chinese
    
    # 添加最后一部分文本
    if current_text:
        run = p.add_run(current_text)
        run.bold = is_bold
        set_run_font(run, current_is_chinese)
    
    return p

def export_titles_to_word(papers, query, file_suffix=''):
    """
    将论文标题导出为Word文档
    
    Args:
        papers (list): 论文列表
        query (str): 查询字符串
        file_suffix (str, optional): 文件名后缀. Defaults to ''.
        
    Returns:
        str: 导出文件的ID
    """
    try:
        # 获取session_id
        session_id = request.args.get('sessionId', 'unknown')
        update_search_progress(session_id, 'titles_export_progress', "正在准备导出文献标题...", 10)
        
        # 创建导出目录
        export_dir = os.path.join(app.root_path, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"nnscholar_titles_{timestamp}{file_suffix}.docx"
        filepath = os.path.join(export_dir, filename)
        
        # 按相关度降序排序文献
        papers_with_relevance = sorted(papers, key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        update_search_progress(session_id, 'titles_export_progress', "正在生成标题文档...", 40)
        
        # 创建Word文档
        doc = Document()
        
        # 添加标题
        title = doc.add_heading('文献标题列表', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 添加检索信息
        doc.add_heading('检索策略', level=1)
        doc.add_paragraph(f'检索词：\n{query}')
        doc.add_paragraph(f'检索时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        doc.add_paragraph(f'检索到的文献数量：{len(papers)}')
        
        # 添加文献标题列表
        doc.add_heading('文献标题', level=1)
        
        # 添加每篇文献的标题
        for i, paper in enumerate(papers_with_relevance, 1):
            # 添加文献标题
            p = doc.add_paragraph(style='List Number')
            title_run = p.add_run(paper.get('title', 'N/A'))
            
            # 根据是否是中文设置字体
            is_chinese = is_chinese_text(paper.get('title', ''))
            set_run_font(title_run, is_chinese)
            
            # 添加相关度信息
            relevance_score = paper.get('relevance_score', 0)
            relevance_run = p.add_run(f' [相关度: {relevance_score:.1f}]')
            if relevance_score >= 70:
                relevance_run.font.color.rgb = RGBColor(0, 128, 0)  # 绿色
            elif relevance_score >= 40:
                relevance_run.font.color.rgb = RGBColor(255, 165, 0)  # 橙色
            else:
                relevance_run.font.color.rgb = RGBColor(128, 128, 128)  # 灰色
        
        # 保存到内存
        word_buffer = BytesIO()
        doc.save(word_buffer)
        word_buffer.seek(0)
        
        # 生成唯一的文件ID
        file_id = f"{session_id}_{filename}"
        
        # 存储到内存中
        memory_exports[file_id] = {
            'data': word_buffer,
            'filename': filename,
            'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'timestamp': datetime.now()
        }
        
        # 发送导出完成的消息
        update_search_progress(session_id, 'titles_export_progress', "标题文档导出完成", 100)
        
        return file_id
        
    except Exception as e:
        logger.error(f"导出标题文档时发生错误: {str(e)}")
        logger.error(traceback.format_exc())
        if session_id:
            update_search_progress(session_id, 'titles_export_progress', 
                                f"导出标题文档失败: {str(e)}", 100)
        return None

@app.route('/api/generate-topic', methods=['POST'])
def generate_topic():
    """基于文献标题生成综述或论著选题"""
    try:
        logger.info("收到生成选题请求")
        session_id = request.headers.get('sid', 'unknown')
        logger.info(f"请求会话ID: {session_id}")
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            logger.error("请求数据为空")
            return jsonify({
                'success': False,
                'error': '请求数据为空'
            }), 400
            
        # 提取参数
        topic_type = data.get('type', 'review')  # 选题类型：review(综述选题)、research(论著选题)、outline(综述大纲)
        titles = data.get('titles', [])
        
        if not titles:
            logger.error("未提供文献标题")
            return jsonify({
                'success': False,
                'error': '请提供文献标题'
            }), 400
            
        logger.info(f"选题类型: {topic_type}, 标题数量: {len(titles)}")
        logger.info(f"前3个标题示例: {titles[:3]}")
        
        # 根据选题类型选择不同的提示词模板
        if topic_type == 'review':
            prompt_title = "基于真实文献的综述选题"
            logger.info("使用综述选题提示词模板")
            system_prompt = """- Role: 学术综述选题专家
- Background: 用户提供了一批文献标题，需要从中提取关键信息，生成3-5个高质量的综述选题建议。
- Profile: 你是一位在学术研究领域经验丰富的专家，擅长分析文献标题，识别研究热点和趋势，并提出有价值的综述方向。
- Skills: 文献分析、主题提取、趋势识别、综述规划
- Goals: 根据用户提供的文献标题，生成3-5个高质量的综述选题建议，每个建议包括选题标题、研究背景、研究意义和可行性分析。
- Constrains: 选题必须基于用户提供的文献，具有学术价值和可行性，符合学术规范。
- OutputFormat: 有序列表，每个选题包括标题、背景、意义和可行性四个部分。
- Workflow:
  1. 分析用户提供的文献标题，识别关键主题和研究方向。
  2. 根据主题相关性和研究热度，提出3-5个综述选题。
  3. 对每个选题进行详细说明，包括研究背景、研究意义和可行性分析。"""
        elif topic_type == 'research':
            prompt_title = "基于真实文献的论著选题"
            logger.info("使用论著选题提示词模板")
            system_prompt = """- Role: 学术论著选题专家
- Background: 用户提供了一批文献标题，需要从中提取关键信息，生成3-5个高质量的原创性论著选题建议。
- Profile: 你是一位在学术研究领域经验丰富的专家，擅长分析文献标题，识别研究空白和机会，并提出有创新价值的研究方向。
- Skills: 文献分析、研究空白识别、创新思维、实验设计思路
- Goals: 根据用户提供的文献标题，生成3-5个高质量的论著选题建议，每个建议包括选题标题、研究背景、研究意义、创新点和可行性评估。
- Constrains: 选题必须基于用户提供的文献，具有创新性和可行性，符合学术规范，可以进行实际操作。
- OutputFormat: 有序列表，每个选题包括标题、背景、意义、创新点和可行性五个部分。
- Workflow:
  1. 分析用户提供的文献标题，识别研究热点和潜在空白。
  2. 根据研究空白和创新机会，提出3-5个论著选题。
  3. 对每个选题进行详细说明，包括研究背景、研究意义、创新点和可行性评估。
  4. 特别强调研究的可行性和实际操作性评估。"""
        else:  # outline
            prompt_title = "基于真实文献的综述生成"
            logger.info("使用综述大纲提示词模板")
            system_prompt = """- Role: 学术论文写作专家和研究综述架构师
- Background: 用户需要根据一个综述题目和上百篇相关论文的标题，生成一个清晰且逻辑性强的大纲，该大纲需分为摘要、前言、研究进展和结论四个主要部分，其中研究进展部分需要提供二级标题示例，以系统展示某领域的研究现状和进展。
- Profile: 你是一位在医学综述撰写和医学研究逻辑架构方面具有丰富经验的专家，具备深厚的医学背景和文献整理能力，能够从大量论文标题中提炼关键信息，构建出科学合理的综述大纲。
- Skills: 你具备文献综述能力、信息提取能力、逻辑结构设计能力以及学术写作能力。能够从论文标题中快速识别主题、方法和结论，并将这些信息整合到一个连贯的大纲中。
- Goals: 根据用户提供的综述题目和上百篇相关论文的标题，生成一个包含摘要、前言、研究进展和结论的清晰大纲。确保大纲能够全面覆盖相关研究领域，并且逻辑连贯。
- Constrains: 大纲必须基于用户提供的综述题目和论文标题，不能引入无关的内容。每个部分的内容需要简洁明了，重点突出，避免冗余。
- OutputFormat: 文字形式的大纲，分为四个部分：摘要、前言、研究进展和结论。每个部分需要有简短的描述和关键点的罗列。
- Workflow:
  1. 从综述题目和论文标题中提取关键主题和研究方向。
 2. 构建大纲的基本框架，包括摘要、前言、研究进展和结论四个部分。
  3. 在研究进展部分，根据论文标题和研究内容，设计详细的二级标题，并提供简要描述。
  4. 对大纲进行逻辑优化和内容补充，确保其完整性和科学性，并确保最终只输出markdown格式大纲，不需要任何额外的说明。此外研究进展中的二级标题最好囊括重点。
  5. 构建结论部分，总结研究的主要发现和未来研究方向- 示例: 题目：软骨肉瘤的影像组学进展 1. 摘要 - 简述软骨肉瘤影像组学的研究现状和主要进展，强调其在临床诊断和治疗中的应用价值。 2. 前言 - 软骨肉瘤的发病率和临床意义 - 传统影像学诊断的局限性 - 影像组学在软骨肉瘤诊疗中的应用价值 - 影像组学概念及工作流程 3. 研究进展：影像组学在软骨肉瘤中的应用 - 3.1 影像组学和软骨肉瘤分级 - MRI影像组学在软骨肉瘤分级中的应用 - CT影像组学在软骨肉瘤分级中的价值 - 特征提取与模型构建在分级中的作用 - 3.2 影像组学和软骨肉瘤复发 - 复发风险评估的影像组学方法 - 多参数MRI影像组学模型的应用 - 临床影像组学列线图在复发预测中的作用 - 3.3 影像组学鉴别软骨肉瘤和其他骨肿瘤 - 与内生软骨瘤的鉴别诊断 - 与非典型软骨瘤的影像组学鉴别 - 与脊索瘤的影像组学鉴别 4. 结论与面临的挑战 - 总结影像组学在软骨肉瘤研究中的主要成果 - 面临的挑战与未来发展方向
    """
        
        # 将标题列表格式化为文本
        titles_text = "\n".join([f"{i+1}. {title}" for i, title in enumerate(titles)])
        logger.info(f"格式化后的标题文本长度: {len(titles_text)}")
        
        # 构建用户提示词
        if topic_type == 'outline':
            # 检查是否提供了自定义题目
            custom_title = data.get('custom_title')
            
            if custom_title:
                logger.info(f"使用用户提供的自定义题目: {custom_title}")
                user_prompt = f'我需要撰写一篇关于"{custom_title}"的综述论文。以下是我搜索到的{len(titles)}篇相关文献的标题，请帮我生成一个清晰且逻辑性强的综述大纲：\n\n{titles_text}'
            else:
                # 从标题中提取可能的综述题目
                possible_topics = extract_possible_topics(titles)
                suggested_topic = possible_topics[0] if possible_topics else "综述题目"
                
                user_prompt = f'我需要撰写一篇关于"{suggested_topic}"的综述论文。以下是我搜索到的{len(titles)}篇相关文献的标题，请帮我生成一个清晰且逻辑性强的综述大纲：\n\n{titles_text}'
        else:
            user_prompt = f"以下是我搜索到的{len(titles)}篇文献标题，请帮我分析并提供{prompt_title}：\n\n{titles_text}"
        
        logger.info(f"用户提示词长度: {len(user_prompt)}")
        
        # 调用DeepSeek API
        logger.info("开始调用DeepSeek API")
        response = call_deepseek_api_with_system_prompt(system_prompt, user_prompt)
        
        if not response:
            logger.error("DeepSeek API返回为空")
            return jsonify({
                'success': False,
                'error': 'AI生成失败，请稍后重试'
            }), 500
        
        logger.info(f"DeepSeek API返回成功，内容长度: {len(response)}")
        
        return jsonify({
            'success': True,
            'type': topic_type,
            'title': prompt_title,
            'content': response
        })
        
    except Exception as e:
        logger.error(f"生成选题时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def extract_possible_topics(titles, top_n=3):
    """从文献标题中提取可能的综述题目"""
    try:
        # 简单方法：找出最常见的关键词组合
        all_text = ' '.join(titles)
        # 移除常见的无意义词
        stop_words = ['a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'of', 'about']
        words = [word.lower() for word in re.findall(r'\b\w+\b', all_text) if word.lower() not in stop_words]
        
        # 计算词频
        word_counts = Counter(words)
        most_common = word_counts.most_common(10)
        
        # 从最常见的词中构建可能的主题
        topics = []
        if most_common:
            # 使用前三个最常见的词构建一个主题
            top_words = [word for word, _ in most_common[:min(3, len(most_common))]]
            topics.append(' '.join(top_words).title())
            
            # 使用前两个最常见的词构建另一个主题
            if len(most_common) >= 2:
                top_two = [word for word, _ in most_common[:2]]
                topics.append(' '.join(top_two).title())
            
            # 单独使用最常见的词
            topics.append(most_common[0][0].title())
        
        return topics[:top_n]
    except Exception as e:
        logger.error(f"提取可能的综述题目时出错: {str(e)}")
        return ["综述研究"]

def call_deepseek_api_with_system_prompt(system_prompt, user_prompt):
    """调用DeepSeek API，支持系统提示词"""
    try:
        logger.info("准备调用DeepSeek API")
        
        # 获取API配置
        api_config = get_api_config(log_info=False)
        api_key = api_config.get('deepseek_key')  # 修正键名，应该是deepseek_key而不是deepseek_api_key
        api_url = os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions')
        
        logger.info(f"DeepSeek API URL: {api_url}")
        logger.info(f"API密钥状态: {'已配置' if api_key else '未配置'}")
        
        if not api_key:
            logger.error("未配置DeepSeek API密钥，无法调用API")
            return None
            
        # 构建请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        logger.info(f"请求参数: model={data['model']}, temperature={data['temperature']}, max_tokens={data['max_tokens']}")
        logger.info(f"系统提示词长度: {len(system_prompt)}")
        logger.info(f"用户提示词长度: {len(user_prompt)}")
        
        # 发送请求
        logger.info(f"正在发送请求到DeepSeek API...")
        start_time = time.time()
        
        try:
            response = requests.post(api_url, headers=headers, json=data, timeout=60)
            elapsed_time = time.time() - start_time
            logger.info(f"API请求耗时: {elapsed_time:.2f}秒")
            
            logger.info(f"API响应状态码: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"DeepSeek API调用失败: {response.status_code}")
                logger.error(f"错误详情: {response.text[:500]}...")  # 只记录前500个字符
                return None
                
            # 解析响应
            result = response.json()
            logger.info("成功解析API响应为JSON")
            
            if 'choices' not in result or len(result['choices']) == 0:
                logger.error(f"API响应缺少choices字段: {str(result)[:200]}...")
                return None
                
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            if not content:
                logger.error(f"DeepSeek API返回内容为空: {str(result)[:200]}...")
                return None
                
            logger.info(f"成功获取API返回内容，长度: {len(content)}")
            return content
            
        except requests.exceptions.Timeout:
            logger.error("DeepSeek API请求超时")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("DeepSeek API连接错误")
            return None
        except Exception as e:
            logger.error(f"发送API请求时发生未知错误: {str(e)}")
            return None
        
    except Exception as e:
        logger.error(f"调用DeepSeek API时出错: {str(e)}")
        return None

@app.route('/api/outline-section-review', methods=['POST'])
def generate_outline_section_review():
    """
    根据综述大纲中的二级标题进行检索，并生成该部分的综述内容
    """
    try:
        session_id = request.headers.get('sid', 'unknown')
        logger.info(f"收到二级标题综述生成请求 [session: {session_id}]")
        
        data = request.get_json()
        if not data:
            logger.error("请求数据为空")
            return jsonify({
                'success': False,
                'error': '请求数据为空'
            }), 400
            
        # 提取必要参数
        section_title = data.get('section_title')
        year_start = data.get('year_start', 2020)
        year_end = data.get('year_end', 2025)
        max_results = data.get('max_results', 50)
        
        if not section_title:
            logger.error("未提供二级标题")
            return jsonify({
                'success': False,
                'error': '请提供二级标题'
            }), 400
            
        logger.info(f"二级标题: {section_title}, 年份范围: {year_start}-{year_end}, 最大结果数: {max_results}")
        
        # 构建检索策略
        search_strategy = f'"{section_title}"[Title/Abstract] AND ("{year_start}"[Date - Publication] : "{year_end}"[Date - Publication])'
        logger.info(f"生成的检索策略: {search_strategy}")
        
        # 执行PubMed检索
        update_search_progress(session_id, 'searching', f"正在检索与'{section_title}'相关的文献...", 20)
        id_list, _, total_count, result_count = search_pubmed(search_strategy)
        
        if not id_list:
            logger.warning(f"未找到与'{section_title}'相关的文献")
            return jsonify({
                'success': False,
                'error': f"未找到与'{section_title}'相关的文献"
            }), 404
            
        logger.info(f"找到{len(id_list)}篇相关文献，限制为前{max_results}篇")
        id_list = id_list[:min(len(id_list), max_results)]
        
        # 获取文献详情
        update_search_progress(session_id, 'fetching_details', f"正在获取'{section_title}'相关文献的详情...", 40)
        papers = fetch_paper_details(id_list)
        
        if not papers:
            logger.warning(f"获取文献详情失败")
            return jsonify({
                'success': False,
                'error': '获取文献详情失败'
            }), 500
            
        logger.info(f"成功获取{len(papers)}篇文献的详情")
        
        # 计算相关性得分
        update_search_progress(session_id, 'calculating_relevance', "正在计算相关性得分...", 60)
        
        # 使用批量计算相关度的方法，确保每篇文献都有 relevance_score
        try:
            # 设置较大的批次大小以加快处理速度
            batch_size = 50  # 增加批次大小
            total_papers = len(papers)
            
            # 使用具有进度更新的批量计算
            api_url = os.getenv('EMBEDDING_API_URL', 'https://api.siliconflow.cn/v1/embeddings')
            api_key = os.getenv('EMBEDDING_API_KEY', os.getenv('DEEPSEEK_API_KEY'))
            model = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
            
            # 记录API配置
            logger.info(f"批量计算嵌入相关度 - API: {api_url}, 模型: {model}, 文献数: {total_papers}, 批次大小: {batch_size}")
            
            # 准备请求头
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # 准备所有文献的文本
            paper_texts = []
            for paper in papers:
                title = paper.get('title', '')
                abstract = paper.get('abstract', '')
                keywords = paper.get('keywords', [])
                keywords_str = ', '.join(keywords) if keywords else ''
                
                paper_text = f"标题: {title}\n摘要: {abstract}\n关键词: {keywords_str}"
                paper_texts.append(paper_text)
            
            # 初始化批次分数列表
            all_scores = [0.0] * total_papers
            
            # 处理每个批次
            for batch_start in range(0, total_papers, batch_size):
                batch_end = min(batch_start + batch_size, total_papers)
                current_batch_size = batch_end - batch_start
                
                # 更新进度
                progress_percentage = 60 + (batch_start / total_papers) * 20  # 从60%到80%的进度区间
                update_search_progress(
                    session_id, 
                    'processing', 
                    f"已分析 {batch_start}/{total_papers} 篇文献...", 
                    progress_percentage
                )
                
                # 获取当前批次的文本
                batch_texts = paper_texts[batch_start:batch_end]
                
                try:
                    # 准备批量请求数据
                    inputs = [section_title] + batch_texts
                    data = {
                        "model": model,
                        "input": inputs
                    }
                    
                    # 发送请求
                    response = requests.post(api_url, headers=headers, json=data)
                    response.raise_for_status()
                    
                    # 解析响应
                    result = response.json()
                    
                    if 'data' in result and len(result['data']) >= len(inputs):
                        # 获取查询的嵌入向量
                        query_embedding = result['data'][0]['embedding']
                        
                        # 计算每篇文献的相关度
                        for j in range(1, len(result['data'])):
                            paper_embedding = result['data'][j]['embedding']
                            similarity = cosine_similarity(query_embedding, paper_embedding)
                            relevance_score = round(similarity * 100, 1)
                            
                            # 保存到结果列表
                            idx = batch_start + j - 1
                            if idx < total_papers:
                                all_scores[idx] = relevance_score
                                
                        logger.info(f"批次 {batch_start//batch_size + 1}/{(total_papers-1)//batch_size + 1} 相关度计算完成")
                    else:
                        logger.error(f"嵌入API批量响应格式错误: {result}")
                        # 填充零分数
                        for j in range(current_batch_size):
                            idx = batch_start + j
                            if idx < total_papers:
                                all_scores[idx] = 0.0
                
                except Exception as e:
                    logger.error(f"处理批次 {batch_start//batch_size + 1} 时出错: {str(e)}")
                    # 填充零分数
                    for j in range(current_batch_size):
                        idx = batch_start + j
                        if idx < total_papers:
                            all_scores[idx] = 0.0
            
            # 最终进度更新
            update_search_progress(session_id, 'processing', f"已分析 {total_papers}/{total_papers} 篇文献...", 80)
            
            # 更新每篇文献的相关度分数
            for i, paper in enumerate(papers):
                if i < len(all_scores):
                    paper['relevance_score'] = all_scores[i]
                    logger.info(f"文献{i+1}的相关度分数: {all_scores[i]}")
                else:
                    # 如果没有批量计算结果，使用单独计算
                    relevance = calculate_relevance_improved(section_title, paper)
                    paper['relevance_score'] = relevance
                    logger.info(f"文献{i+1}的相关度分数(单独计算): {relevance}")
            
            logger.info(f"成功计算批量相关度分数，共{len(all_scores)}个分数")
            
        except Exception as e:
            logger.error(f"批量计算相关度分数时出错: {str(e)}")
            # 如果批量计算失败，使用单独计算
            for i, paper in enumerate(papers):
                relevance = calculate_relevance_improved(section_title, paper)
                paper['relevance_score'] = relevance
                if i < 5:  # 只记录前5篇文献的日志
                    logger.info(f"文献{i+1}的相关度分数(单独计算): {relevance}")
                    
                # 每处理10篇文献更新一次进度
                if i % 10 == 0:
                    progress_percentage = 60 + (i / len(papers)) * 20
                    update_search_progress(
                        session_id, 
                        'processing', 
                        f"已分析 {i}/{len(papers)} 篇文献...", 
                        progress_percentage
                    )
                    
        # 根据相关度分数对文献进行排序
        papers.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        # 限制使用的文献数量，只使用相关度最高的文献
        max_papers_to_use = min(len(papers), max_results)
        logger.info(f"按相关度排序后，将使用前{max_papers_to_use}篇文献生成综述")
        papers_to_use = papers[:max_papers_to_use]
        
        # 提取文献标题和摘要
        titles_abstracts = []
        for i, paper in enumerate(papers_to_use):
            title = paper.get('title', '')
            abstract = paper.get('abstract', '')
            authors = paper.get('authors', [])
            first_author = authors[0] if authors else "Unknown"
            year = paper.get('pub_year', '')
            pmid = paper.get('pmid', f"{i+1}")
            
            titles_abstracts.append({
                'index': i + 1,
                'title': title,
                'abstract': abstract,
                'first_author': first_author,
                'year': year,
                'pmid': pmid
            })
            
        # 构建提示词
        system_prompt = """- Role: 学术文献综述撰写专家 
- Background: 用户需要基于特定领域的文献撰写综述初稿，文献已提供且每篇有明确PMID，要求在文中以第一作者名[具体PMID]的形式引用文献，并附参考文献目录。 
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长对大量文献进行梳理、分析和总结，能够精准把握文献的核心观点和研究进展，熟悉学术写作规范和引用格式。 
- Skills: 文献分析、归纳总结、逻辑组织、学术写作规范、引用格式掌握 
- Goals: 撰写一份条理清晰、内容全面的综述初稿，准确引用文献，附带规范的参考文献目录。 
- Constrains: 严格按照学术写作规范，确保引用准确无误。在文中必须使用第一作者名[具体PMID]的格式，例如：Zhang[12345]表明...，不要用序号代替PMID。在参考文献目录中，必须包含每篇文献的PMID，格式示例：1. Zhang W [PMID: 12345]。
- OutputFormat: 文本格式，包含综述正文和参考文献目录 
- Workflow:
1. 仔细阅读每篇文献，提取关键信息，包括研究目的、方法、结果和结论。 
2. 按照研究主题或方法对文献进行分类，梳理出研究脉络和进展。 
3. 撰写综述正文，将文献内容进行整合和总结，以第一作者名[具体PMID]的形式在文中引用。 
4. 编写参考文献目录，确保包含每篇文献的PMID信息。"""
        
        # 构建用户提示词
        user_prompt = f"请根据以下{len(titles_abstracts)}篇关于\"{section_title}\"的文献，撰写一篇综述初稿。每篇文献都有明确的PMID，请在综述中以第一作者名[具体PMID]的形式引用文献，写参考文献目录，并确保包含每篇文献的PMID信息\n\n"
        
        # 添加文献信息
        for item in titles_abstracts:
            user_prompt += f"【{item['index']}】\n标题：{item['title']}\nPMID：{item['pmid']}\n作者：{item['first_author']} et al., {item['year']}\n摘要：{item['abstract']}\n\n"
        
        # 调用DeepSeek API
        update_search_progress(session_id, 'generating', f"正在生成'{section_title}'的综述内容...", 70)
        logger.info(f"开始调用DeepSeek API生成综述内容，使用按相关度排序后的前{len(titles_abstracts)}篇文献")
        
        response = call_deepseek_api_with_system_prompt(system_prompt, user_prompt)
        
        if not response:
            logger.error("DeepSeek API返回为空")
            return jsonify({
                'success': False,
                'error': 'AI生成失败，请稍后重试'
            }), 500
            
        logger.info(f"DeepSeek API返回成功，内容长度: {len(response)}")
        
        # 更新进度
        update_search_progress(session_id, 'completed', f"'{section_title}'的综述内容生成完成，批次大小已提高到50篇/批", 100)
        
        return jsonify({
            'success': True,
            'section_title': section_title,
            'content': response,
            'papers_count': len(papers),
            'year_range': f"{year_start}-{year_end}"
        })
        
    except Exception as e:
        logger.error(f"生成二级标题综述时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/generate-outline-section', methods=['POST'])
def generate_outline_section():
    """
    根据大纲部分内容生成完整内容（不进行PubMed检索）
    用于生成前言、摘要和结论等部分
    """
    try:
        session_id = request.headers.get('sid', 'unknown')
        logger.info(f"收到大纲部分生成请求 [session: {session_id}]")
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            logger.error("请求数据为空")
            return jsonify({
                'success': False,
                'error': '请求数据为空'
            }), 400
            
        # 提取必要参数
        section_type = data.get('section_type', '')  # 部分类型：前言、摘要、结论
        outline_content = data.get('outline_content', '')  # 大纲内容
        
        if not section_type or not outline_content:
            logger.error("未提供部分类型或大纲内容")
            return jsonify({
                'success': False,
                'error': '请提供部分类型和大纲内容'
            }), 400
            
        logger.info(f"部分类型: {section_type}, 大纲内容长度: {len(outline_content)}")
        
        # 根据部分类型选择不同的系统提示词
        if section_type == "前言":
            system_prompt = """- Role: 学术论文前言撰写专家
- Background: 用户需要基于一个综述大纲的前言部分，扩写为完整的前言内容。前言应当包括研究背景、研究意义、研究现状和研究目的等内容。
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长撰写高质量的论文前言，能够清晰地阐述研究背景和意义，并恰当引用相关文献。
- Skills: 学术写作、文献引用、逻辑组织、背景分析
- Goals: 将用户提供的前言大纲扩写为完整、专业的前言内容，包含至少10篇真实文献的引用，并确保内容的逻辑性和学术性。
- Constrains: 必须使用真实文献作为引用，引用格式为第一作者名[PMID]，写参考文献目录，按照出现的文献PMID顺序列出文献信息。
- OutputFormat: 文本格式，包含前言正文和参考文献列表。
- Workflow:
  1. 分析用户提供的前言大纲，理解研究主题和方向。
  2. 扩写研究背景，说明研究领域的重要性。
  3. 阐述研究现状，引用相关文献支持论点。
  4. 说明研究的目的和意义。
  5. 提供完整的参考文献列表。"""
        elif section_type == "摘要":
            system_prompt = """- Role: 学术论文摘要撰写专家
- Background: 用户需要基于一个综述大纲的摘要部分，撰写完整的摘要内容。摘要应当简明扼要地概括研究的背景、目的、方法、结果和结论。
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长撰写高质量的论文摘要，能够在有限的篇幅内准确传达研究的核心内容。
- Skills: 信息提炼、简明表达、学术写作
- Goals: 将用户提供的摘要大纲扩写为完整、专业的摘要内容，确保内容的准确性和简洁性。
- Constrains: 摘要应控制在300-400字以内，不包含引用，语言简洁明了。
- OutputFormat: 文本格式，一段完整的摘要。
- Workflow:
  1. 分析用户提供的摘要大纲，理解研究的核心内容。
  2. 简要说明研究背景和目的。
  3. 概述研究方法或综述的范围。
  4. 总结主要发现或结论。
  5. 指出研究的意义或应用价值。"""
        elif section_type == "结论":
            system_prompt = """- Role: 学术论文结论撰写专家
- Background: 用户需要基于一个综述大纲的结论部分，撰写完整的结论内容。结论应当总结研究的主要发现，指出研究的意义和局限性，并提出未来研究方向。
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长撰写高质量的论文结论，能够准确总结研究成果并提出有价值的展望。
- Skills: 总结分析、学术写作、批判性思维
- Goals: 将用户提供的结论大纲扩写为完整、专业的结论内容，包含研究总结、意义分析和未来展望。
- Constrains: 结论应当客观、准确，可以引用关键文献支持论点，但不应引入新的研究内容。
- OutputFormat: 文本格式，包含结论正文和必要的引用。
- Workflow:
  1. 分析用户提供的结论大纲，理解研究的主要发现。
  2. 总结研究的核心内容和主要贡献。
  3. 分析研究的意义和价值。
  4. 指出研究的局限性。
  5. 提出未来研究方向和建议。"""
        elif section_type == "研究进展":
            system_prompt = """- Role: 学术综述研究进展撰写专家
- Background: 用户需要基于综述大纲的研究进展部分，包括其中的二级标题，扩写为完整的研究进展内容。研究进展应当全面分析该领域的现有研究，包括方法、结果和意义等。
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长撰写高质量的研究进展部分，能够系统地分析和总结某领域的研究现状。
- Skills: 文献综述、分析总结、逻辑组织、学术写作
- Goals: 将用户提供的研究进展大纲扩写为完整、专业的研究进展内容，包含各二级标题的详细论述，并引用至少15篇真实文献支持论点。
- Constrains: 必须使用真实文献作为引用，引用格式为第一作者名[PMID]，写参考文献目录，按照出现的文献PMID顺序列出文献信息。
- OutputFormat: 文本格式，包含研究进展正文和参考文献列表，正文需保持原有的标题层级结构。
- Workflow:
  1. 分析用户提供的研究进展大纲，理解各二级标题的主题和逻辑关系。
  2. 扩写每个二级标题下的内容，系统地阐述该方面的研究现状。
  3. 引用相关文献支持论点，确保内容的学术性和可信度。
  4. 在各部分之间建立逻辑连贯性，形成完整的研究进展论述。
  5. 提供完整的参考文献列表。示例：在人工智能领域，张三[1]提出了深度学习算法的基本框架，为后续研究奠定了基础。李四[2]在此基础上，对算法进行了优化，提高了模型的准确性和效率。王五[3]则从应用角度出发，探讨了深度学习在图像识别中的实际效果。
  """
        else:
            system_prompt = """- Role: 学术论文内容撰写专家
- Background: 用户需要基于一个综述大纲的特定部分，扩写为完整的内容。
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长将大纲扩写为详细、专业的学术内容。
- Skills: 学术写作、内容扩展、逻辑组织
- Goals: 将用户提供的大纲扩写为完整、专业的学术内容，确保内容的逻辑性和学术性。
- Constrains: 内容应当客观、准确，可以适当引用文献支持论点。
- OutputFormat: 文本格式，包含正文和必要的引用。
- Workflow:
  1. 分析用户提供的大纲，理解内容的核心要点。
  2. 按照逻辑顺序扩展每个要点。
  3. 确保内容之间的连贯性和一致性。
  4. 适当引用文献支持论点。"""
        
        # 构建用户提示词
        if section_type == "前言":
            user_prompt = f"请将以下综述论文的前言大纲扩写为完整的前言内容，至少需要引用10篇真实文献，引用格式为第一作者名[PMID]，写参考文献目录，按照出现的文献PMID顺序列出文献信息：\n\n{outline_content}"
        elif section_type == "摘要":
            user_prompt = f"请将以下综述论文的摘要大纲扩写为完整的摘要内容，控制在300-400字以内：\n\n{outline_content}"
        elif section_type == "结论":
            user_prompt = f"请将以下综述论文的结论大纲扩写为完整的结论内容，包括研究总结、意义分析和未来展望：\n\n{outline_content}"
        elif section_type == "研究进展":
            user_prompt = f"请将以下综述论文的研究进展部分大纲扩写为完整内容，保留原有的标题层级结构，并至少引用15篇真实文献支持论点，引用格式为第一作者名[PMID]，写参考文献目录，按照出现的文献PMID顺序列出完整的参考文献列表：\n\n{outline_content}"
        else:
            user_prompt = f"请将以下综述论文的{section_type}部分大纲扩写为完整内容：\n\n{outline_content}"
        
        # 调用DeepSeek API
        update_search_progress(session_id, 'generating', f"正在生成{section_type}内容...", 50)
        logger.info(f"开始调用DeepSeek API生成{section_type}内容")
        
        response = call_deepseek_api_with_system_prompt(system_prompt, user_prompt)
        
        if not response:
            logger.error("DeepSeek API返回为空")
            return jsonify({
                'success': False,
                'error': 'AI生成失败，请稍后重试'
            }), 500
            
        logger.info(f"DeepSeek API返回成功，内容长度: {len(response)}")
        
        # 更新进度
        update_search_progress(session_id, 'completed', f"{section_type}内容生成完成", 100)
        
        return jsonify({
            'success': True,
            'section_type': section_type,
            'content': response
        })
        
    except Exception as e:
        logger.error(f"生成{data.get('section_type', '未知部分')}内容时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/generate-research-subsection-content', methods=['POST'])
def generate_research_subsection_content():
    """
    根据研究进展的次级标题内容，分析检索结果中的相关文献，
    筛选出相关性最高的文献，结合次级标题内容生成详细的综述内容
    """
    try:
        session_id = request.headers.get('sid', 'unknown')
        logger.info(f"收到研究进展次级标题生成请求 [session: {session_id}]")
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            logger.error("请求数据为空")
            return jsonify({
                'success': False,
                'error': '请求数据为空'
            }), 400
        
        # 提取必要参数
        subsection_title = data.get('subsection_title', '')  # 次级标题
        subsection_content = data.get('subsection_content', '')  # 次级标题下的内容
        search_papers = data.get('search_papers', [])  # 检索到的文献列表
        related_papers_count = data.get('related_papers_count', 30)  # 要筛选的相关文献数量
        
        if not subsection_title or not subsection_content:
            logger.error("未提供次级标题或内容")
            return jsonify({
                'success': False,
                'error': '请提供次级标题和内容'
            }), 400
        
        if not search_papers:
            logger.error("未提供检索文献")
            return jsonify({
                'success': False,
                'error': '请提供检索文献列表'
            }), 400
        
        logger.info(f"次级标题: {subsection_title}, 内容长度: {len(subsection_content)}, 检索文献数量: {len(search_papers)}")
        
        # 1. 构建查询文本，包含次级标题和内容
        query_text = f"{subsection_title} {subsection_content}"
        
        # 2. 计算每篇文献与查询的相关性
        papers_with_relevance = []
        
        update_search_progress(session_id, 'processing', f"正在分析文献与次级标题\"{subsection_title}\"的相关性...", 20)
        
        for idx, paper in enumerate(search_papers):
            try:
                # 计算相关性分数
                relevance_score = calculate_combined_relevance(query_text, paper)
                
                # 添加到列表
                papers_with_relevance.append({
                    'paper': paper,
                    'relevance': relevance_score
                })
                
                # 更新进度
                if idx % 10 == 0:
                    percentage = min(20 + (idx / len(search_papers) * 30), 50)
                    update_search_progress(session_id, 'processing', f"已分析 {idx}/{len(search_papers)} 篇文献...", percentage)
            
            except Exception as e:
                logger.error(f"计算文献相关性时出错: {str(e)}")
                # 继续处理其他文献
                continue
        
        # 3. 按相关性排序并选择前N篇
        papers_with_relevance.sort(key=lambda x: x['relevance'], reverse=True)
        top_related_papers = papers_with_relevance[:related_papers_count]
        
        logger.info(f"筛选出 {len(top_related_papers)} 篇相关性最高的文献")
        
        # 4. 提取相关文献的信息
        related_papers_info = []
        for idx, paper_data in enumerate(top_related_papers):
            paper = paper_data['paper']
            paper_info = {
                'title': paper.get('title', '无标题'),
                'authors': paper.get('authors', []),
                'journal': paper.get('journal', '未知期刊'),
                'year': paper.get('year', '未知年份'),
                'abstract': paper.get('abstract', '无摘要'),
                'pmid': paper.get('pmid', f"{idx+1}"),
                'relevance': paper_data['relevance']
            }
            related_papers_info.append(paper_info)
            
            # 更新进度
            percentage = min(50 + (idx / len(top_related_papers) * 20), 70)
            update_search_progress(session_id, 'processing', f"正在整理相关文献信息...", percentage)
        
        # 5. 构建提示词
        system_prompt = """- Role: 学术综述研究进展撰写专家
- Background: 用户提供了一个研究进展的次级标题及其内容，以及与该主题最相关的若干篇文献信息，需要你根据这些文献生成该次级标题下的详细综述内容。
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长撰写高质量的研究进展部分，能够系统地分析和总结某一特定领域的研究现状。
- Skills: 文献综述、分析总结、逻辑组织、学术写作
- Goals: 根据提供的次级标题、内容概要和相关文献，生成详细、专业的研究进展内容，引用提供的真实文献支持论点。
- Constrains: 必须使用提供的真实文献作为引用，引用格式为第一作者名[PMID]，写参考文献目录，按照出现的文献PMID顺序列出完整的参考文献列表
- OutputFormat: 文本格式，包含研究进展正文和参考文献列表。
- Workflow:
  1. 分析提供的次级标题和内容概要，理解研究主题。
  2. 系统性整理相关文献，形成逻辑连贯的叙述。
  3. 详细论述该次级标题下的研究现状、方法、结果和意义。
  4. 引用相关文献支持论点，确保内容的学术性和可信度。
  5. 提供完整的参考文献列表。"""
        
        # 格式化文献信息
        formatted_papers = ""
        for idx, paper in enumerate(related_papers_info):
            # 处理作者信息 - 支持不同的数据格式
            if paper['authors']:
                if isinstance(paper['authors'], list):
                    # 检查第一个作者的类型
                    if paper['authors'] and isinstance(paper['authors'][0], dict):
                        # 如果是字典类型，使用get方法获取名称
                        authors_text = "、".join([a.get('name', '未知作者') for a in paper['authors'][:3]])
                    else:
                        # 如果是字符串类型，直接连接
                        authors_text = "、".join([str(a) for a in paper['authors'][:3]])
                    
                    if len(paper['authors']) > 3:
                        authors_text += "等"
                else:
                    # 如果authors不是列表，直接使用
                    authors_text = str(paper['authors'])
            else:
                authors_text = '未知作者'
            
            formatted_papers += f"[{idx+1}] 标题: {paper['title']}\n"
            formatted_papers += f"    PMID: {paper['pmid']}\n"
            formatted_papers += f"    作者: {authors_text}\n"
            formatted_papers += f"    期刊: {paper['journal']}\n"
            formatted_papers += f"    年份: {paper['year']}\n"
            formatted_papers += f"    摘要: {paper['abstract'][:200]}...\n\n"
        
        user_prompt = f"""请根据以下次级标题和内容，结合提供的相关文献信息，生成该次级标题下的详细综述内容：

## 次级标题和内容：
{subsection_title}
{subsection_content}

## 相关文献信息（按相关性排序，共{len(related_papers_info)}篇）：
{formatted_papers}

请生成详细、学术性强的综述内容，必须引用上述相关文献，引用格式为第一作者名[具体PMID]，例如"Zhang[12345]表明..."，不要用序号代替PMID。
在参考文献目录中，必须按照引用顺序列出完整的参考文献信息，并确保包含具体PMID，格式示例：1. Zhang W [PMID: 12345]
内容应该深入分析该领域的研究现状、方法、结果和意义，并建立逻辑连贯的叙述。
"""
        
        # 6. 调用DeepSeek API生成内容
        update_search_progress(session_id, 'generating', f"正在生成\"{subsection_title}\"的详细内容...", 75)
        logger.info(f"开始调用DeepSeek API生成次级标题内容")
        
        response = call_deepseek_api_with_system_prompt(system_prompt, user_prompt)
        
        if not response:
            logger.error("DeepSeek API返回为空")
            return jsonify({
                'success': False,
                'error': 'AI生成失败，请稍后重试'
            }), 500
        
        logger.info(f"DeepSeek API返回成功，内容长度: {len(response)}")
        
        # 7. 更新进度并返回结果
        update_search_progress(session_id, 'completed', f"次级标题\"{subsection_title}\"内容生成完成", 100)
        
        return jsonify({
            'success': True,
            'subsection_title': subsection_title,
            'content': response,
            'related_papers_count': len(related_papers_info)
        })
        
    except Exception as e:
        logger.error(f"生成研究进展次级标题内容时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/merge-review-sections', methods=['POST'])
def merge_review_sections():
    """
    合并综述的各个部分（摘要、前言、研究进展、结论），生成一个完整的综述文档
    """
    try:
        session_id = request.headers.get('sid', 'unknown')
        logger.info(f"收到合并综述部分请求 [session: {session_id}]")
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            logger.error("请求数据为空")
            return jsonify({
                'success': False,
                'error': '请求数据为空'
            }), 400
            
        # 提取各个部分的内容
        abstract = data.get('abstract', '')
        introduction = data.get('introduction', '')
        progress_sections = data.get('progress_sections', [])
        conclusion = data.get('conclusion', '')
        title = data.get('title', '综述论文')
        
        # 检查必要的部分是否存在
        if not abstract or not introduction or not progress_sections or not conclusion:
            logger.error("缺少必要的综述部分")
            return jsonify({
                'success': False,
                'error': '请提供摘要、前言、研究进展和结论部分'
            }), 400
            
        logger.info(f"综述标题: {title}")
        logger.info(f"摘要长度: {len(abstract)}, 前言长度: {len(introduction)}, 研究进展部分数量: {len(progress_sections)}, 结论长度: {len(conclusion)}")
        
        # 构建完整的综述内容
        full_review = f"# {title}\n\n"
        
        # 添加摘要
        full_review += "## 摘要\n\n"
        full_review += abstract + "\n\n"
        
        # 添加前言
        full_review += "## 前言\n\n"
        full_review += introduction + "\n\n"
        
        # 添加研究进展部分
        full_review += "## 研究进展\n\n"
        for section in progress_sections:
            section_title = section.get('title', '')
            section_content = section.get('content', '')
            if section_title and section_content:
                full_review += f"### {section_title}\n\n"
                full_review += section_content + "\n\n"
        
        # 添加结论
        full_review += "## 结论与展望\n\n"
        full_review += conclusion
        
        # 生成Word文档
        doc = Document()
        
        # 设置标题样式
        doc.add_heading(title, level=0)
        
        # 添加摘要
        doc.add_heading('摘要', level=1)
        add_paragraph_with_mixed_fonts(doc, abstract)
        
        # 添加前言
        doc.add_heading('前言', level=1)
        add_paragraph_with_mixed_fonts(doc, introduction)
        
        # 添加研究进展
        doc.add_heading('研究进展', level=1)
        for section in progress_sections:
            section_title = section.get('title', '')
            section_content = section.get('content', '')
            if section_title and section_content:
                doc.add_heading(section_title, level=2)
                add_paragraph_with_mixed_fonts(doc, section_content)
        
        # 添加结论
        doc.add_heading('结论与展望', level=1)
        add_paragraph_with_mixed_fonts(doc, conclusion)
        
        # 保存文档
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        export_dir = os.path.join(app.root_path, 'exports')
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
            
        file_name = f"综述_{timestamp}.docx"
        file_path = os.path.join(export_dir, file_name)
        doc.save(file_path)
        
        download_url = f"/exports/{file_name}"
        
        logger.info(f"综述文档已生成，保存路径: {file_path}")
        
        return jsonify({
            'success': True,
            'word_download_url': download_url
        })
        
    except Exception as e:
        logger.error(f"合并综述部分时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/generate-research-subsection', methods=['POST'])
def generate_research_subsection():
    """
    根据研究进展的次级标题内容，分析检索结果中的相关文献，
    筛选出相关性最高的文献，结合次级标题内容生成详细的综述内容
    """
    try:
        session_id = request.headers.get('sid', 'unknown')
        logger.info(f"收到研究进展次级标题生成请求 [session: {session_id}]")
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            logger.error("请求数据为空")
            return jsonify({
                'success': False,
                'error': '请求数据为空'
            }), 400
        
        # 提取必要参数
        subsection_title = data.get('subsection_title', '')  # 次级标题
        subsection_content = data.get('subsection_content', '')  # 次级标题下的内容
        search_papers = data.get('search_papers', [])  # 检索到的文献列表
        related_papers_count = data.get('related_papers_count', 30)  # 要筛选的相关文献数量
        
        if not subsection_title or not subsection_content:
            logger.error("未提供次级标题或内容")
            return jsonify({
                'success': False,
                'error': '请提供次级标题和内容'
            }), 400
        
        if not search_papers:
            logger.error("未提供检索文献")
            return jsonify({
                'success': False,
                'error': '请提供检索文献列表'
            }), 400
        
        logger.info(f"次级标题: {subsection_title}, 内容长度: {len(subsection_content)}, 检索文献数量: {len(search_papers)}")
        
        # 1. 构建查询文本，包含次级标题和内容
        query_text = f"{subsection_title} {subsection_content}"
        
        # 2. 计算每篇文献与查询的相关性
        papers_with_relevance = []
        
        update_search_progress(session_id, 'processing', f"正在分析文献与次级标题\"{subsection_title}\"的相关性...", 20)
        
        for idx, paper in enumerate(search_papers):
            try:
                # 计算相关性分数
                relevance_score = calculate_combined_relevance(query_text, paper)
                
                # 添加到列表
                papers_with_relevance.append({
                    'paper': paper,
                    'relevance': relevance_score
                })
                
                # 更新进度
                if idx % 10 == 0:
                    percentage = min(20 + (idx / len(search_papers) * 30), 50)
                    update_search_progress(session_id, 'processing', f"已分析 {idx}/{len(search_papers)} 篇文献...", percentage)
            
            except Exception as e:
                logger.error(f"计算文献相关性时出错: {str(e)}")
                # 继续处理其他文献
                continue
        
        # 3. 按相关性排序并选择前N篇
        papers_with_relevance.sort(key=lambda x: x['relevance'], reverse=True)
        top_related_papers = papers_with_relevance[:related_papers_count]
        
        logger.info(f"筛选出 {len(top_related_papers)} 篇相关性最高的文献")
        
        # 4. 提取相关文献的信息
        related_papers_info = []
        for idx, paper_data in enumerate(top_related_papers):
            paper = paper_data['paper']
            paper_info = {
                'title': paper.get('title', '无标题'),
                'authors': paper.get('authors', []),
                'journal': paper.get('journal', '未知期刊'),
                'year': paper.get('year', '未知年份'),
                'abstract': paper.get('abstract', '无摘要'),
                'pmid': paper.get('pmid', f"{idx+1}"),
                'relevance': paper_data['relevance']
            }
            related_papers_info.append(paper_info)
            
            # 更新进度
            percentage = min(50 + (idx / len(top_related_papers) * 20), 70)
            update_search_progress(session_id, 'processing', f"正在整理相关文献信息...", percentage)
        
        # 5. 构建提示词
        system_prompt = """- Role: 学术综述研究进展撰写专家
- Background: 用户提供了一个研究进展的次级标题及其内容，以及与该主题最相关的若干篇文献信息，需要你根据这些文献生成该次级标题下的详细综述内容。
- Profile: 你是一位在学术写作领域经验丰富的专家，擅长撰写高质量的研究进展部分，能够系统地分析和总结某一特定领域的研究现状。
- Skills: 文献综述、分析总结、逻辑组织、学术写作
- Goals: 根据提供的次级标题、内容概要和相关文献，生成详细、专业的研究进展内容，引用提供的真实文献支持论点。
- Constrains: 必须使用提供的真实文献作为引用，引用格式为第一作者名[具体PMID]，例如：Zhang[12345]表明... 不要使用序号代替PMID。写参考文献目录时，必须包含PMID信息，例如：1. Zhang W [PMID: 12345]。
- OutputFormat: 文本格式，包含研究进展正文和参考文献列表。
- Workflow:
  1. 分析提供的次级标题和内容概要，理解研究主题。
  2. 系统性整理相关文献，形成逻辑连贯的叙述。
  3. 详细论述该次级标题下的研究现状、方法、结果和意义。
  4. 在文中引用相关文献时，使用第一作者名[具体PMID]的格式。
  5. 提供完整的参考文献列表，确保包含每篇文献的PMID。"""
        
                # 格式化文献信息
        formatted_papers = ""
        for idx, paper in enumerate(related_papers_info):
            # 处理作者信息 - 支持不同的数据格式
            if paper['authors']:
                if isinstance(paper['authors'], list):
                    # 检查第一个作者的类型
                    if paper['authors'] and isinstance(paper['authors'][0], dict):
                        # 如果是字典类型，使用get方法获取名称
                        authors_text = "、".join([a.get('name', '未知作者') for a in paper['authors'][:3]])
                    else:
                        # 如果是字符串类型，直接连接
                        authors_text = "、".join([str(a) for a in paper['authors'][:3]])
                    
                    if len(paper['authors']) > 3:
                        authors_text += "等"
                else:
                    # 如果authors不是列表，直接使用
                    authors_text = str(paper['authors'])
            else:
                authors_text = '未知作者'
            
            # 获取PMID，确保在展示和引用时使用真实PMID或索引
            actual_pmid = paper.get('pmid')
            if not actual_pmid:
                actual_pmid = f"{idx+1}"
                logger.warning(f"文献没有PMID，使用索引号代替: {actual_pmid}")
                
            formatted_papers += f"[{idx+1}] 标题: {paper['title']}\n"
            formatted_papers += f"    PMID: {actual_pmid}\n"
            formatted_papers += f"    作者: {authors_text}\n"
            formatted_papers += f"    期刊: {paper['journal']}\n"
            formatted_papers += f"    年份: {paper['year']}\n"
            formatted_papers += f"    摘要: {paper['abstract'][:200]}...\n\n"
        
        user_prompt = f"""请根据以下次级标题和内容，结合提供的相关文献信息，生成该次级标题下的详细综述内容：

## 次级标题和内容：
{subsection_title}
{subsection_content}

## 相关文献信息（按相关性排序，共{len(related_papers_info)}篇）：
{formatted_papers}

请生成详细、学术性强的综述内容，必须引用上述相关文献，引用格式为第一作者名[具体PMID]，例如"Zhang[12345]表明..."，不要用序号代替PMID。
在参考文献目录中，必须按照引用顺序列出完整的参考文献信息，并确保包含具体PMID，格式示例：1. Zhang W [PMID: 12345]
内容应该深入分析该领域的研究现状、方法、结果和意义，并建立逻辑连贯的叙述。
"""
        
        # 6. 调用DeepSeek API生成内容
        update_search_progress(session_id, 'generating', f"正在生成\"{subsection_title}\"的详细内容...", 75)
        logger.info(f"开始调用DeepSeek API生成次级标题内容")
        
        response = call_deepseek_api_with_system_prompt(system_prompt, user_prompt)
        
        if not response:
            logger.error("DeepSeek API返回为空")
            return jsonify({
                'success': False,
                'error': 'AI生成失败，请稍后重试'
            }), 500
        
        logger.info(f"DeepSeek API返回成功，内容长度: {len(response)}")
        
        # 7. 更新进度并返回结果
        update_search_progress(session_id, 'completed', f"次级标题\"{subsection_title}\"内容生成完成", 100)
        
        return jsonify({
            'success': True,
            'subsection_title': subsection_title,
            'content': response,
            'related_papers_count': len(related_papers_info)
        })
        
    except Exception as e:
        logger.error(f"生成研究进展次级标题内容时出错: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("logs/app.log"),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger("NNScholar")
    logger.info("应用启动中...")
    
    # 启动后台任务
    start_background_tasks()
    
    # 启动应用
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)