"""
会话缓存管理 - 兼容原版本API
临时缓存实现，用于API兼容性
"""

import threading
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class SessionCache:
    """会话缓存管理器"""
    
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()
        self.cleanup_interval = timedelta(hours=2)  # 2小时清理一次
        self.last_cleanup = datetime.now()
    
    def store_papers(self, session_id: str, papers: list, query: str = "", original_papers: list = None) -> bool:
        """存储文献数据到缓存"""
        try:
            with self.lock:
                # 如果已存在数据，保留分析结果
                existing_data = self.cache.get(session_id, {})
                analysis_results = existing_data.get('analysis_results', {})
                
                self.cache[session_id] = {
                    'papers': papers,
                    'original_papers': original_papers or papers,  # 如果没有原始数据，使用当前数据
                    'query': query,
                    'timestamp': datetime.now(),
                    'access_count': 0,
                    'analysis_results': analysis_results  # 保留已有的分析结果
                }
                logger.info(f"Cache STORE: Stored {len(papers)} papers for session {session_id} with query '{query}'")
                if original_papers:
                    logger.info(f"Cache STORE: Also stored {len(original_papers)} original papers for session {session_id}")
                
                # 验证存储的数据
                if papers:
                    sample_paper = papers[0]
                    logger.info(f"Sample stored paper: {list(sample_paper.keys()) if isinstance(sample_paper, dict) else type(sample_paper)}")
                
                logger.info(f"Cache now has {len(self.cache)} sessions: {list(self.cache.keys())}")
                self._cleanup_if_needed()
                return True
        except Exception as e:
            logger.error(f"Error storing papers for session {session_id}: {e}")
            return False
    
    def get_papers(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从缓存获取文献数据"""
        try:
            with self.lock:
                logger.info(f"Cache lookup for session: {session_id}")
                logger.info(f"Available cache keys: {list(self.cache.keys())}")
                
                if session_id in self.cache:
                    data = self.cache[session_id]
                    data['access_count'] += 1
                    data['last_access'] = datetime.now()
                    papers_count = len(data['papers'])
                    logger.info(f"Cache HIT: Retrieved {papers_count} papers for session {session_id}")
                    
                    # 验证论文数据结构
                    if papers_count > 0:
                        sample_paper = data['papers'][0]
                        logger.info(f"Sample paper structure: {list(sample_paper.keys()) if isinstance(sample_paper, dict) else type(sample_paper)}")
                    
                    return {
                        'papers': data['papers'],
                        'query': data['query']
                    }
                else:
                    logger.warning(f"Cache MISS: No data found for session {session_id}")
                    logger.info(f"Cache has {len(self.cache)} sessions total")
                    return None
        except Exception as e:
            logger.error(f"Error retrieving papers for session {session_id}: {e}")
            return None
    
    def get_titles(self, session_id: str) -> list:
        """从缓存获取文献标题列表"""
        data = self.get_papers(session_id)
        if data and data['papers']:
            return [paper.get('title', '') for paper in data['papers']]
        return []
    
    def session_exists(self, session_id: str) -> bool:
        """检查会话是否存在"""
        with self.lock:
            return session_id in self.cache
    
    def remove_session(self, session_id: str) -> bool:
        """移除会话数据"""
        try:
            with self.lock:
                if session_id in self.cache:
                    del self.cache[session_id]
                    logger.debug(f"Removed session {session_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error removing session {session_id}: {e}")
            return False
    
    def _cleanup_if_needed(self):
        """清理过期的会话数据"""
        now = datetime.now()
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_expired_sessions()
            self.last_cleanup = now
    
    def _cleanup_expired_sessions(self):
        """清理过期的会话（超过24小时）"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            expired_sessions = []
            
            for session_id, data in self.cache.items():
                if data['timestamp'] < cutoff_time:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del self.cache[session_id]
                logger.debug(f"Cleaned up expired session {session_id}")
                
            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
                
        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")
    
    def store_analysis_result(self, session_id: str, analysis_type: str, result_data: Dict[str, Any]) -> bool:
        """存储分析结果到缓存"""
        try:
            with self.lock:
                if session_id not in self.cache:
                    # 如果session不存在，创建基本结构
                    self.cache[session_id] = {
                        'papers': [],
                        'query': '',
                        'timestamp': datetime.now(),
                        'access_count': 0,
                        'analysis_results': {}
                    }
                
                if 'analysis_results' not in self.cache[session_id]:
                    self.cache[session_id]['analysis_results'] = {}
                
                self.cache[session_id]['analysis_results'][analysis_type] = result_data
                logger.info(f"Cache STORE: Stored {analysis_type} result for session {session_id}: paper_count={result_data.get('paper_count', 0)}")
                return True
        except Exception as e:
            logger.error(f"Error storing analysis result for session {session_id}: {e}")
            return False
    
    def get_analysis_result(self, session_id: str, analysis_type: str) -> Optional[Dict[str, Any]]:
        """获取分析结果"""
        try:
            with self.lock:
                if session_id in self.cache and 'analysis_results' in self.cache[session_id]:
                    result = self.cache[session_id]['analysis_results'].get(analysis_type)
                    if result:
                        logger.info(f"Cache HIT: Retrieved {analysis_type} result for session {session_id}: paper_count={result.get('paper_count', 0)}")
                        return result
                    else:
                        logger.warning(f"Cache MISS: No {analysis_type} result for session {session_id}")
                else:
                    logger.warning(f"Cache MISS: No analysis results for session {session_id}")
                return None
        except Exception as e:
            logger.error(f"Error retrieving analysis result for session {session_id}: {e}")
            return None

    def get_all_sessions(self) -> list:
        """获取所有会话的列表，按时间倒序排列"""
        try:
            with self.lock:
                sessions = []
                for session_id, data in self.cache.items():
                    # 只返回有文献数据的会话
                    if data.get('papers') and len(data['papers']) > 0:
                        sessions.append({
                            'session_id': session_id,
                            'query': data.get('query', '未知查询'),
                            'paper_count': len(data['papers']),
                            'timestamp': data['timestamp'].isoformat(),
                            'last_access': data.get('last_access', data['timestamp']).isoformat(),
                            'access_count': data.get('access_count', 0)
                        })

                # 按时间倒序排列（最新的在前）
                sessions.sort(key=lambda x: x['timestamp'], reverse=True)
                return sessions
        except Exception as e:
            logger.error(f"Error getting all sessions: {e}")
            return []

    def remove_session(self, session_id: str) -> bool:
        """删除指定会话"""
        try:
            with self.lock:
                if session_id in self.cache:
                    del self.cache[session_id]
                    logger.info(f"Session {session_id} removed from cache")
                    return True
                else:
                    logger.warning(f"Session {session_id} not found in cache")
                    return False
        except Exception as e:
            logger.error(f"Error removing session {session_id}: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.lock:
            total_papers = sum(len(data['papers']) for data in self.cache.values())
            return {
                'total_sessions': len(self.cache),
                'total_papers': total_papers,
                'last_cleanup': self.last_cleanup.isoformat(),
                'sessions': {
                    session_id: {
                        'paper_count': len(data['papers']),
                        'timestamp': data['timestamp'].isoformat(),
                        'access_count': data['access_count']
                    }
                    for session_id, data in self.cache.items()
                }
            }

# 全局缓存实例
papers_cache = SessionCache()

def get_papers_cache():
    """获取全局缓存实例"""
    return papers_cache