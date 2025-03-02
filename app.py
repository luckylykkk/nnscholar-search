from flask import Flask, request, jsonify, render_template, send_from_directory
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
import shutil
from pathlib import Path
import threading
import copy
from flask_socketio import SocketIO, emit
import asyncio
from flask_socketio import join_room, leave_room

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

def search_pubmed(query, max_results=600):
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
            
        # logger.info(f"开始处理文献 PMID: {pmid}")
            
        # 提取标题
        title_element = article.find('ArticleTitle')
        title = title_element.text if title_element else None
        if not title:
            logger.warning(f"文献 {pmid} 缺少标题，跳过")
            return None
            
        # logger.info(f"文献标题: {title[:100]}...")
            
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
        
        # 应用筛选条件
        if filters:
            filtered_papers, stats = filter_papers_by_metrics(papers, filters)
        else:
            filtered_papers = papers
            stats = {
                'total': len(papers),
                'filtered': len(papers)
            }
        
        return {
            'text': sentence['text'],
            'papers': filtered_papers,
            'search_strategy': sentence['search_strategy'],
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
                    lambda s: process_sentence_async(session_id, s, filters),
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
        session_id = request.headers.get('sid')
        if not session_id:
            raise ValueError("无效的会话ID")
            
        # 发送导出开始的消息
        update_search_progress(session_id, 'export_progress', "开始导出文献...", 0)
        
        # 如果是段落模式，合并所有子句的文献
        mode = request.args.get('mode', 'single')
        if mode == 'paragraph':
            # 获取所有子句
            sentences = []
            all_papers = []
            
            # 合并所有子句的文献，并记录每个文献对应的句子
            for sentence_result in papers:
                sentence_text = sentence_result.get('text', '')
                sentence_papers = sentence_result.get('papers', [])
                sentences.append(sentence_text)
                
                # 为每篇文献添加对应的句子信息
                for paper in sentence_papers:
                    paper['source_sentence'] = sentence_text
                    all_papers.append(paper)
            
            # 使用合并后的文献列表
            papers = all_papers
            # 更新查询文本为所有句子的组合
            query = "\n".join(sentences)
        
        # 导出Excel
        update_search_progress(session_id, 'export_progress', "正在导出Excel文件...", 30)
        excel_path = export_papers_to_excel(papers, query, file_suffix)
        
        # 发送Excel导出完成的消息
        update_search_progress(session_id, 'export_progress', "Excel文件导出完成", 60)
        
        # 导出Word
        update_search_progress(session_id, 'export_progress', "正在导出Word文件...", 70)
        word_path = export_papers_to_word(papers, query, file_suffix)
        
        # 发送Word导出完成的消息
        update_search_progress(session_id, 'export_progress', "Word文件导出完成", 90)
        
        # 发送导出完成的消息
        update_search_progress(session_id, 'export_progress', "文献导出完成", 100, 
                             files={'excel': excel_path, 'word': word_path})
        
        return excel_path, word_path
        
    except Exception as e:
        logger.error(f'导出文件失败：{str(e)}\n{traceback.format_exc()}')
        
        # 发送错误信息
        if session_id:
            update_search_progress(session_id, 'export_progress', f"导出文件失败: {str(e)}", 100)
            
        return None, None

def export_papers_to_excel(papers, query, file_suffix=''):
    """将文献信息导出为Excel表格"""
    try:
        session_id = request.headers.get('sid')
        if not session_id:
            raise ValueError("无效的会话ID")
            
        # 发送开始导出Excel的消息
        update_search_progress(session_id, 'excel_export_progress', "正在准备数据...", 10)
        
        # 准备数据
        data = []
        for i, paper in enumerate(papers):
            journal_info = paper.get('journal_info', {})
            paper_data = {
                '标题': paper.get('title', ''),
                '摘要': paper.get('abstract', ''),
                '作者': ', '.join(paper.get('authors', [])),
                '发表年份': paper.get('pub_year', ''),
                '期刊名称': journal_info.get('title', ''),
                '影响因子': journal_info.get('impact_factor', 'N/A'),
                'JCR分区': journal_info.get('jcr_quartile', 'N/A'),
                'CAS分区': journal_info.get('cas_quartile', 'N/A'),
                '关键词': ', '.join(paper.get('keywords', [])),
                'DOI': paper.get('doi', ''),
                'PMID': paper.get('pmid', ''),
                '相关度': f"{paper.get('relevance', 0):.1f}%"
            }
            
            # 如果是段落模式，添加来源句子
            if 'source_sentence' in paper:
                paper_data['来源句子'] = paper['source_sentence']
            
            data.append(paper_data)
            
            # 每处理10篇文献发送一次进度更新
            if (i + 1) % 10 == 0:
                progress = min(10 + int((i + 1) / len(papers) * 40), 50)
                update_search_progress(session_id, 'excel_export_progress', 
                                    f"正在处理数据 ({i + 1}/{len(papers)})...", progress)
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_query = re.sub(r'[^\w\u4e00-\u9fff]', '_', query)
        if len(safe_query) > 50:
            safe_query = safe_query[:50]
        filename = f'papers_{safe_query}_{file_suffix}_{timestamp}.xlsx'
        filepath = os.path.join(EXPORTS_DIR, filename)
        
        # 导出到Excel
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        # 发送导出完成的消息
        update_search_progress(session_id, 'excel_export_progress', "Excel文件导出完成", 100)
        
        return filepath
        
    except Exception as e:
        logger.error(f"导出Excel文件时发生错误: {str(e)}")
        if session_id:
            update_search_progress(session_id, 'excel_export_progress', 
                                f"导出Excel文件失败: {str(e)}", 100)
        return None

def export_papers_to_word(papers, query, file_suffix=''):
    """将论文信息导出为Word文档"""
    try:
        session_id = request.headers.get('sid')
        if not session_id:
            raise ValueError("无效的会话ID")
            
        # 发送开始导出Word的消息
        update_search_progress(session_id, 'word_export_progress', "正在创建Word文档...", 10)
        
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
        
        # 如果是段落模式，添加句子分析部分
        if any('source_sentence' in paper for paper in papers):
            doc.add_heading('句子分析', level=1)
            # 使用字典来收集每个句子的相关文献
            sentence_papers = {}
            for paper in papers:
                if 'source_sentence' in paper:
                    if paper['source_sentence'] not in sentence_papers:
                        sentence_papers[paper['source_sentence']] = []
                    sentence_papers[paper['source_sentence']].append(paper)
            
            # 按句子顺序显示分析
            for i, (sentence, related_papers) in enumerate(sentence_papers.items(), 1):
                # 添加句子标题
                doc.add_heading(f'句子 {i}', level=2)
                
                # 添加原句
                p = doc.add_paragraph()
                p.add_run('原句：').bold = True
                p.add_run(sentence)
                
                # 添加相关文献数量
                doc.add_paragraph(f'相关文献数量：{len(related_papers)}篇')
                
                # 添加该句子的文献列表
                if related_papers:
                    doc.add_heading(f'相关文献列表：', level=3)
                    for j, paper in enumerate(related_papers, 1):
                        # 获取期刊信息
                        journal_info = paper.get('journal_info', {})
                        
                        # 添加文献标题
                        p = doc.add_paragraph()
                        p.add_run(f'{j}. ').bold = True
                        title_run = p.add_run(paper.get('title', 'N/A'))
                        title_run.bold = True
                        
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
                        if j < len(related_papers):
                            doc.add_paragraph('_' * 50)
                
                # 在句子之间添加分隔线
                if i < len(sentence_papers):
                    doc.add_paragraph('=' * 50)
        
        # 如果不是段落模式，直接显示文献列表
        else:
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
                if i < len(papers):
                    doc.add_paragraph('_' * 50)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_query = re.sub(r'[^\w\u4e00-\u9fff]', '_', query[:50])  # 限制查询长度为50个字符
        filename = f'papers_{safe_query}_{file_suffix}_{timestamp}.docx'
        filepath = os.path.join(EXPORTS_DIR, filename)
        
        # 保存文档
        doc.save(filepath)
        
        # 发送导出完成的消息
        update_search_progress(session_id, 'word_export_progress', "Word文档导出完成", 100)
        
        return filepath
        
    except Exception as e:
        logger.error(f"导出Word文档时发生错误: {str(e)}")
        if session_id:
            update_search_progress(session_id, 'word_export_progress', 
                                f"导出Word文档失败: {str(e)}", 100)
        return None

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
        filters = data.get('filters', {})
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请输入检索内容'
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
        
        for paper in papers:
            paper['relevance'] = calculate_relevance_improved(query, paper)
        
        # 应用筛选条件
        filtered_papers, stats = filter_papers_by_metrics(papers, filters)
        
        # 导出文件
        update_search_progress(session_id, 'exporting', "正在生成导出文件...", 90)
        
        # 导出初始结果和筛选后的结果
        initial_excel, initial_word = export_papers(papers, query, 'initial')
        filtered_excel, filtered_word = export_papers(filtered_papers, query, 'filtered')
        
        # 发送完成消息
        update_search_progress(session_id, 'complete', f"搜索完成，找到 {len(filtered_papers)} 篇相关文献", 100)
            
        return jsonify({
            'success': True,
            'data': filtered_papers,
            'original_papers': papers,
            'search_strategy': search_strategy,
            'total_count': total_count,
            'filtered_count': len(filtered_papers),
            'export_files': {
                'initial_excel': initial_excel,
                'initial_word': initial_word,
                'filtered_excel': filtered_excel,
                'filtered_word': filtered_word
            }
        })
        
    except Exception as e:
        logger.error(f"搜索请求处理出错: {str(e)}\n{traceback.format_exc()}")
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
            
        # 获取当前用户的会话ID
        session_id = request.headers.get('sid')
        if not session_id:
            return jsonify({
                'success': False,
                'error': '无效的会话ID'
            }), 400
            
        # 更新用户活跃状态
        handle_connect(session_id)
        
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

@app.route('/exports/<path:filename>')
def download_file(filename):
    """处理文件下载请求"""
    try:
        # 安全检查：确保文件名不包含目录遍历
        if '..' in filename or filename.startswith('/'):
            return jsonify({
                'success': False,
                'error': '无效的文件名'
            }), 400
            
        # 清理文件名，只保留文件名部分
        clean_filename = os.path.basename(filename)
        logger.info(f"正在处理文件下载请求: {clean_filename}")
        
        # 检查文件是否存在
        file_path = os.path.join(EXPORTS_DIR, clean_filename)
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404
            
        # 从导出目录发送文件
        return send_from_directory(
            EXPORTS_DIR, 
            clean_filename, 
            as_attachment=True,
            download_name=clean_filename
        )
        
    except Exception as e:
        logger.error(f"文件下载失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': '文件下载失败'
        }), 500

@app.route('/api/analyze-journal', methods=['POST'])
def analyze_journal():
    """期刊分析API端点"""
    try:
        data = request.get_json()
        journal = data.get('journal')
        keywords = data.get('keywords', '').strip()  # 可选参数
        start_year = data.get('start_year')
        end_year = data.get('end_year')
        
        # 参数验证
        if not journal:
            return jsonify({
                'success': False,
                'error': '请输入期刊名称'
            }), 400
            
        if not all([start_year, end_year]):
            return jsonify({
                'success': False,
                'error': '请输入完整的时间范围'
            }), 400
            
        try:
            start_year = int(start_year)
            end_year = int(end_year)
            if start_year > end_year:
                return jsonify({
                    'success': False,
                    'error': '起始年份不能大于结束年份'
                }), 400
        except ValueError:
            return jsonify({
                'success': False,
                'error': '年份格式无效'
            }), 400
            
        # 创建分析器实例
        analyzer = JournalAnalyzer()
        
        # 构建基本检索策略
        base_query = f"{journal}[ta] AND ({start_year}[pdat]:{end_year}[pdat])"
        
        # 如果有关键词，扩展关键词并添加到检索策略
        if keywords:
            expanded_keywords = expand_keywords(keywords)
            if expanded_keywords:
                base_query = f"({base_query}) AND ({expanded_keywords})"
        
        # 获取文章数据
        articles = analyzer.fetch_journal_articles(base_query)
        
        if not articles:
            return jsonify({
                'success': False,
                'error': '未找到相关文章'
            }), 404
            
        # 分析热点主题
        hot_topics = analyzer.analyze_hot_topics(articles)
        
        # 生成热力图数据 - 转换为简单的[topic, count]格式
        heatmap_data = []
        for topic in hot_topics[:30]:  # 只取前30个主题
            heatmap_data.append([topic['topic'], topic['article_count']])
        
        # 生成词云数据
        wordcloud_data = analyzer.extract_keywords(articles)[:50]  # 限制50个关键词
        
        # 生成趋势数据
        trend_data = analyzer.analyze_trends(articles)
        
        # 分析热点作者
        hot_authors = analyzer.analyze_hot_authors(articles)
        
        # 准备返回数据
        response_data = {
            'success': True,
            'heatmap_data': heatmap_data,
            'wordcloud_data': wordcloud_data,
            'trend_data': trend_data,
            'hot_authors': hot_authors,
            'total_articles': len(articles)
        }
        
        logger.info(f"分析完成，数据预览:")
        logger.info(f"热力图数据: {len(heatmap_data)} 个主题")
        logger.info(f"词云数据: {len(wordcloud_data)} 个关键词")
        logger.info(f"趋势数据: {len(trend_data.get('topics', []))} 个主题, {len(trend_data.get('years', []))} 年")
        logger.info(f"热点作者: {len(hot_authors)} 位")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"期刊分析失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'分析失败: {str(e)}'
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

if __name__ == '__main__':
    try:
        # 检查NLTK数据
        nltk_data_path = os.path.join(os.path.expanduser('~'), 'nltk_data')
        
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
        
        # 启动性能监控线程
        monitor_thread = threading.Thread(target=monitor_system_performance, daemon=True)
        monitor_thread.start()
        
        logger.info("正在启动应用服务器...")
        # 使用socketio启动应用
        socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"启动失败: {str(e)}\n{traceback.format_exc()}")
        raise 