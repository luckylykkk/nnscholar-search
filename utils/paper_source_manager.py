from typing import Dict, List, Any, Optional
from .paper_source_interface import PaperSourceInterface
import logging
from .arxiv_client import ArxivClient
from .pubmed_client import PubMedClient
from .semantic_scholar_client import SemanticScholarClient

logger = logging.getLogger(__name__)

class PaperSourceManager:
    """
    论文数据源管理器
    """
    
    def __init__(self):
        """初始化论文数据源管理器"""
        self.sources: Dict[str, PaperSourceInterface] = {}
        
    def register_source(self, source: PaperSourceInterface) -> None:
        """
        注册新的数据源
        
        Args:
            source: 实现了 PaperSourceInterface 的数据源实例
        """
        source_name = source.get_source_name()
        self.sources[source_name] = source
        logger.info(f"注册数据源: {source_name}")
        
    def get_source(self, source_name: str) -> Optional[PaperSourceInterface]:
        """
        获取指定名称的数据源
        
        Args:
            source_name: 数据源名称
            
        Returns:
            Optional[PaperSourceInterface]: 数据源实例或 None
        """
        return self.sources.get(source_name)
        
    def get_all_sources(self) -> List[str]:
        """
        获取所有已注册的数据源名称
        
        Returns:
            List[str]: 数据源名称列表
        """
        return list(self.sources.keys())
        
    async def search_papers_all_sources(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从所有数据源搜索论文"""
        all_papers = []
        seen_paper_ids = set()  # 用于去重
        
        # 获取选择的数据源
        selected_sources = filters.get("sources", ["pubmed", "semanticscholar"])
        logger.info(f"选择的数据源: {selected_sources}")
        
        # 从每个选择的数据源搜索
        for source_name in selected_sources:
            if source_name not in self.sources:
                logger.warning(f"未知的数据源: {source_name}")
                continue
                
            source = self.sources[source_name]
            try:
                papers = await source.search_papers(query, filters)
                logger.info(f"从 {source_name} 获取到 {len(papers)} 篇论文")
                
                # 去重并添加到结果列表
                for paper in papers:
                    paper_id = paper.get("id")
                    if paper_id and paper_id not in seen_paper_ids:
                        seen_paper_ids.add(paper_id)
                        paper["source"] = source_name  # 添加来源标记
                        all_papers.append(paper)
                        
            except Exception as e:
                logger.error(f"从 {source_name} 搜索论文时出错: {str(e)}")
                
        return all_papers
        
    def get_paper_details_all_sources(self, paper_id: str) -> Dict[str, Dict[str, Any]]:
        """
        从所有数据源获取论文详细信息
        
        Args:
            paper_id: 论文ID
            
        Returns:
            Dict[str, Dict[str, Any]]: 各数据源的论文详情
        """
        results = {}
        for source_name, source in self.sources.items():
            try:
                results[source_name] = source.get_paper_details(paper_id)
            except Exception as e:
                logger.error(f"数据源 {source_name} 获取论文详情失败: {str(e)}")
                results[source_name] = {}
                
        return results 