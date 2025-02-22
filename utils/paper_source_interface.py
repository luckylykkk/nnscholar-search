from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class PaperSourceInterface(ABC):
    """
    论文数据源接口抽象类
    """
    
    @abstractmethod
    def search_papers(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        搜索论文的抽象方法
        
        Args:
            query: 搜索查询字符串
            filters: 过滤条件字典
            
        Returns:
            List[Dict[str, Any]]: 论文信息列表
        """
        pass
    
    @abstractmethod
    def get_paper_details(self, paper_id: str) -> Dict[str, Any]:
        """
        获取论文详细信息的抽象方法
        
        Args:
            paper_id: 论文ID
            
        Returns:
            Dict[str, Any]: 论文详细信息
        """
        pass
    
    @abstractmethod
    def get_paper_citations(self, paper_id: str) -> List[Dict[str, Any]]:
        """
        获取论文引用信息的抽象方法
        
        Args:
            paper_id: 论文ID
            
        Returns:
            List[Dict[str, Any]]: 引用论文列表
        """
        pass
    
    @abstractmethod
    def get_paper_references(self, paper_id: str) -> List[Dict[str, Any]]:
        """
        获取论文参考文献的抽象方法
        
        Args:
            paper_id: 论文ID
            
        Returns:
            List[Dict[str, Any]]: 参考文献列表
        """
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """
        获取数据源名称
        
        Returns:
            str: 数据源名称
        """
        pass 