"""
分析结果缓存管理
用于跨session访问分析结果数据
"""

import threading
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class AnalysisCache:
    """分析结果缓存管理器"""
    
    def __init__(self):
        self.cache = {}  # {session_id: {analysis_type: result_data}}
        self.lock = threading.Lock()
        self.cleanup_interval = timedelta(hours=2)  # 2小时清理一次
        self.last_cleanup = datetime.now()
    
    def store_result(self, session_id: str, analysis_type: str, result_data: Dict[str, Any]) -> bool:
        """存储分析结果"""
        try:
            with self.lock:
                if session_id not in self.cache:
                    self.cache[session_id] = {}
                
                # 添加存储时间戳
                result_data = result_data.copy()
                result_data['stored_at'] = datetime.now().isoformat()
                
                self.cache[session_id][analysis_type] = result_data
                
                logger.info(f"Analysis cache STORE: {analysis_type} for session {session_id}, paper_count={result_data.get('paper_count', 0)}")
                
                self._cleanup_if_needed()
                return True
        except Exception as e:
            logger.error(f"Error storing analysis result for session {session_id}: {e}")
            return False
    
    def get_result(self, session_id: str, analysis_type: str) -> Optional[Dict[str, Any]]:
        """获取分析结果"""
        try:
            with self.lock:
                if session_id in self.cache and analysis_type in self.cache[session_id]:
                    result = self.cache[session_id][analysis_type]
                    logger.info(f"Analysis cache HIT: {analysis_type} for session {session_id}, paper_count={result.get('paper_count', 0)}")
                    return result
                else:
                    logger.warning(f"Analysis cache MISS: {analysis_type} for session {session_id}")
                    logger.info(f"Available cache: sessions={list(self.cache.keys())}")
                    if session_id in self.cache:
                        logger.info(f"Available analysis types for session {session_id}: {list(self.cache[session_id].keys())}")
                    return None
        except Exception as e:
            logger.error(f"Error retrieving analysis result for session {session_id}: {e}")
            return None
    
    def _cleanup_if_needed(self):
        """如果需要的话清理过期数据"""
        now = datetime.now()
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_expired_results()
            self.last_cleanup = now
    
    def _cleanup_expired_results(self):
        """清理过期的分析结果（超过24小时）"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            expired_sessions = []
            
            for session_id, analysis_results in self.cache.items():
                # 检查每个分析结果的存储时间
                expired_types = []
                for analysis_type, result_data in analysis_results.items():
                    stored_at_str = result_data.get('stored_at')
                    if stored_at_str:
                        stored_at = datetime.fromisoformat(stored_at_str)
                        if stored_at < cutoff_time:
                            expired_types.append(analysis_type)
                
                # 删除过期的分析类型
                for analysis_type in expired_types:
                    del analysis_results[analysis_type]
                
                # 如果session没有任何分析结果了，标记为过期
                if not analysis_results:
                    expired_sessions.append(session_id)
            
            # 删除过期的session
            for session_id in expired_sessions:
                del self.cache[session_id]
            
            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired analysis sessions")
                
        except Exception as e:
            logger.error(f"Error during analysis cache cleanup: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.lock:
            total_results = sum(len(results) for results in self.cache.values())
            return {
                'total_sessions': len(self.cache),
                'total_results': total_results,
                'last_cleanup': self.last_cleanup.isoformat(),
                'sessions': {
                    session_id: list(results.keys())
                    for session_id, results in self.cache.items()
                }
            }

# 全局分析结果缓存实例
analysis_cache = AnalysisCache()

def get_analysis_cache():
    """获取全局分析结果缓存实例"""
    return analysis_cache