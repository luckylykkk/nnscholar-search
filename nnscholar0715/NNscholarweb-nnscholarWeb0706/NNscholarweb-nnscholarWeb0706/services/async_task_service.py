#!/usr/bin/env python3
"""
异步任务处理服务

提供学术分析功能的异步处理能力，避免用户长时间等待
"""

import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 等待处理
    RUNNING = "running"      # 正在处理
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    EXPIRED = "expired"      # 已过期


class AsyncTask:
    """异步任务类"""
    
    def __init__(self, task_id: str, task_type: str, task_data: Dict[str, Any]):
        self.task_id = task_id
        self.task_type = task_type
        self.task_data = task_data
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = "任务已创建"
        self.result = None
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.last_updated = datetime.now()
    
    def start(self):
        """开始任务"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()
        self.last_updated = datetime.now()
        self.message = "任务正在处理中..."
        logger.info(f"Task {self.task_id} started")
    
    def update_progress(self, progress: int, message: str = None):
        """更新任务进度"""
        self.progress = min(100, max(0, progress))
        if message:
            self.message = message
        self.last_updated = datetime.now()
        logger.debug(f"Task {self.task_id} progress: {progress}% - {message}")
    
    def complete(self, result: Any):
        """完成任务"""
        self.status = TaskStatus.COMPLETED
        self.progress = 100
        self.result = result
        self.completed_at = datetime.now()
        self.last_updated = datetime.now()
        self.message = "任务已完成"
        logger.info(f"Task {self.task_id} completed successfully")
    
    def fail(self, error: str):
        """任务失败"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
        self.last_updated = datetime.now()
        self.message = f"任务失败: {error}"
        logger.error(f"Task {self.task_id} failed: {error}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type,
            'task_data': self.task_data,  # 包含原始任务数据，包括session_id
            'status': self.status.value,
            'progress': self.progress,
            'message': self.message,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_updated': self.last_updated.isoformat()
        }


class AsyncTaskService:
    """异步任务服务"""
    
    def __init__(self):
        self.tasks: Dict[str, AsyncTask] = {}
        self.task_handlers: Dict[str, Callable] = {}
        self.cleanup_interval = 3600  # 1小时清理一次过期任务
        self.task_expire_time = 7200  # 任务2小时后过期
        self._start_cleanup_thread()
    
    def register_handler(self, task_type: str, handler: Callable):
        """注册任务处理器"""
        self.task_handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")
    
    def create_task(self, task_type: str, task_data: Dict[str, Any]) -> str:
        """创建异步任务"""
        task_id = str(uuid.uuid4())
        task = AsyncTask(task_id, task_type, task_data)
        self.tasks[task_id] = task
        
        # 启动任务处理线程
        thread = threading.Thread(target=self._process_task, args=(task,))
        thread.daemon = True
        thread.start()
        
        logger.info(f"Created async task {task_id} of type {task_type}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[AsyncTask]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        task = self.get_task(task_id)
        if task:
            return task.to_dict()
        return None
    
    def _process_task(self, task: AsyncTask):
        """处理任务"""
        try:
            task.start()
            
            # 获取任务处理器
            handler = self.task_handlers.get(task.task_type)
            if not handler:
                task.fail(f"No handler found for task type: {task.task_type}")
                return
            
            # 执行任务
            result = handler(task)
            task.complete(result)
            
        except Exception as e:
            logger.exception(f"Error processing task {task.task_id}")
            task.fail(str(e))
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup():
            while True:
                try:
                    self._cleanup_expired_tasks()
                    time.sleep(self.cleanup_interval)
                except Exception as e:
                    logger.error(f"Error in cleanup thread: {e}")
                    time.sleep(60)  # 出错后等待1分钟再试
        
        thread = threading.Thread(target=cleanup)
        thread.daemon = True
        thread.start()
        logger.info("Cleanup thread started")
    
    def _cleanup_expired_tasks(self):
        """清理过期任务"""
        current_time = datetime.now()
        expired_tasks = []
        
        for task_id, task in self.tasks.items():
            # 计算任务年龄
            task_age = (current_time - task.created_at).total_seconds()
            
            if task_age > self.task_expire_time:
                expired_tasks.append(task_id)
                task.status = TaskStatus.EXPIRED
        
        # 删除过期任务
        for task_id in expired_tasks:
            del self.tasks[task_id]
            logger.info(f"Cleaned up expired task: {task_id}")
        
        if expired_tasks:
            logger.info(f"Cleaned up {len(expired_tasks)} expired tasks")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        status_counts = {}
        for task in self.tasks.values():
            status = task.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            'total_tasks': len(self.tasks),
            'status_distribution': status_counts,
            'task_types': list(self.task_handlers.keys()),
            'cleanup_interval': self.cleanup_interval,
            'task_expire_time': self.task_expire_time
        }


# 全局任务服务实例
async_task_service = AsyncTaskService()


def get_async_task_service() -> AsyncTaskService:
    """获取异步任务服务实例"""
    return async_task_service