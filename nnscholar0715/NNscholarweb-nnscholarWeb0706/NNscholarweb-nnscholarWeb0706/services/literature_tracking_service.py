#!/usr/bin/env python3
"""
文献追踪服务

模仿Connected Papers实现文献网络图谱功能：
1. 基于种子文献生成引用网络图
2. 分析Prior Works（祖先文献）
3. 分析Derivative Works（后代文献）
4. 计算文献相关度和影响力
5. 生成可视化图谱数据
"""

import logging
import math
from typing import List, Dict, Any, Set, Tuple
from datetime import datetime
from collections import defaultdict, Counter
import json
import requests
import time

logger = logging.getLogger(__name__)


class LiteratureTrackingService:
    """文献追踪服务"""
    
    def __init__(self):
        self.max_nodes = 50  # 最大节点数量
        self.max_depth = 2   # 最大搜索深度
        self.semantic_scholar_base_url = "https://api.semanticscholar.org/graph/v1/paper"
        self.opencitations_base_url = "https://opencitations.net/index/api/v1"
    
    def generate_citation_network(self, seed_paper: Dict[str, Any], 
                                all_papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成以种子文献为中心的引用网络图
        
        Args:
            seed_paper: 种子文献
            all_papers: 所有可用文献
            
        Returns:
            包含节点和边的网络图数据
        """
        try:
            logger.info(f"开始生成文献网络图，种子文献: {seed_paper.get('title', '')}")

            # 如果只有种子文献，生成演示网络
            if len(all_papers) <= 1:
                logger.info("Only seed paper available, generating demo network")
                return self._generate_demo_network(seed_paper)

            # 构建文献索引
            papers_index = self._build_papers_index(all_papers)

            # 分析引用关系
            citation_graph = self._analyze_citation_relationships(seed_paper, papers_index)

            # 计算相关度分数
            relatedness_scores = self._calculate_relatedness_scores(citation_graph, seed_paper)

            # 选择最相关的文献节点
            selected_papers = self._select_relevant_papers(citation_graph, relatedness_scores)

            # 生成网络图数据
            network_data = self._generate_network_data(selected_papers, citation_graph, seed_paper)

            # 分析Prior和Derivative Works
            prior_works = self._analyze_prior_works(seed_paper, papers_index)
            derivative_works = self._analyze_derivative_works(seed_paper, papers_index)

            logger.info(f"网络图生成完成: {len(network_data['nodes'])} 个节点, {len(network_data['edges'])} 条边")

            return {
                "success": True,
                "seed_paper": seed_paper,
                "network": network_data,
                "prior_works": prior_works,
                "derivative_works": derivative_works,
                "statistics": {
                    "total_nodes": len(network_data['nodes']),
                    "total_edges": len(network_data['edges']),
                    "prior_count": len(prior_works),
                    "derivative_count": len(derivative_works)
                }
            }
            
        except Exception as e:
            logger.error(f"生成文献网络图失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_demo_network(self, seed_paper: Dict[str, Any]) -> Dict[str, Any]:
        """生成演示网络图（当只有种子文献时）"""
        try:
            # 创建种子节点
            seed_node = {
                "id": seed_paper.get('pmid', 'seed'),
                "title": seed_paper.get('title', 'Seed Paper'),
                "authors": seed_paper.get('authors', ['Unknown Author']),
                "year": seed_paper.get('year', '2023'),
                "journal": seed_paper.get('journal', 'Unknown Journal'),
                "impact_factor": seed_paper.get('impact_factor', '0.0'),
                "jcr_quartile": seed_paper.get('jcr_quartile', 'Q4'),
                "type": "seed",
                "size": 20,
                "color": "#ff9500"
            }

            # 创建一些演示相关文献节点
            demo_papers = [
                {
                    "id": "demo_1",
                    "title": "相关研究 1: 基础理论研究",
                    "authors": ["研究者 A", "研究者 B"],
                    "year": "2022",
                    "journal": "顶级期刊 A",
                    "impact_factor": "8.5",
                    "jcr_quartile": "Q1",
                    "type": "prior",
                    "size": 15,
                    "color": "#ff6b6b"
                },
                {
                    "id": "demo_2",
                    "title": "相关研究 2: 方法学改进",
                    "authors": ["研究者 C", "研究者 D"],
                    "year": "2021",
                    "journal": "权威期刊 B",
                    "impact_factor": "6.2",
                    "jcr_quartile": "Q1",
                    "type": "prior",
                    "size": 12,
                    "color": "#ff6b6b"
                },
                {
                    "id": "demo_3",
                    "title": "后续研究 1: 应用拓展",
                    "authors": ["研究者 E", "研究者 F"],
                    "year": "2024",
                    "journal": "新兴期刊 C",
                    "impact_factor": "4.1",
                    "jcr_quartile": "Q2",
                    "type": "derivative",
                    "size": 10,
                    "color": "#4ecdc4"
                }
            ]

            # 创建边（引用关系）
            edges = [
                {
                    "source": "demo_1",
                    "target": seed_node["id"],
                    "type": "citation",
                    "weight": 1
                },
                {
                    "source": "demo_2",
                    "target": seed_node["id"],
                    "type": "citation",
                    "weight": 1
                },
                {
                    "source": seed_node["id"],
                    "target": "demo_3",
                    "type": "citation",
                    "weight": 1
                }
            ]

            network_data = {
                "nodes": [seed_node] + demo_papers,
                "edges": edges
            }

            # 创建Prior和Derivative Works
            prior_works = demo_papers[:2]  # 前两个作为Prior Works
            derivative_works = demo_papers[2:]  # 后面的作为Derivative Works

            logger.info("演示网络图生成完成")

            return {
                "success": True,
                "seed_paper": seed_paper,
                "network": network_data,
                "prior_works": prior_works,
                "derivative_works": derivative_works,
                "statistics": {
                    "total_nodes": len(network_data['nodes']),
                    "total_edges": len(network_data['edges']),
                    "prior_count": len(prior_works),
                    "derivative_count": len(derivative_works)
                },
                "is_demo": True
            }

        except Exception as e:
            logger.error(f"生成演示网络图失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_papers_index(self, papers: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """构建文献索引"""
        index = {}
        for paper in papers:
            # 使用PMID作为主键，标题作为备用键
            pmid = paper.get('pmid')
            title = paper.get('title', '').strip().lower()
            
            if pmid:
                index[str(pmid)] = paper
            if title:
                index[title] = paper
                
        return index
    
    def _analyze_citation_relationships(self, seed_paper: Dict[str, Any], 
                                      papers_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """分析引用关系"""
        citation_graph = {
            'papers': {},
            'citations': defaultdict(set),  # paper_id -> set of cited paper_ids
            'cited_by': defaultdict(set)    # paper_id -> set of citing paper_ids
        }
        
        seed_id = str(seed_paper.get('pmid', seed_paper.get('title', '').strip().lower()))
        citation_graph['papers'][seed_id] = seed_paper
        
        # 模拟引用关系分析（在实际应用中，这里需要真实的引用数据）
        # 由于我们的数据可能没有完整的引用关系，我们基于相似度和时间来模拟
        seed_year = self._extract_year(seed_paper.get('pub_year'))
        seed_keywords = self._extract_keywords(seed_paper)
        
        for paper_id, paper in papers_index.items():
            if paper_id == seed_id:
                continue
                
            paper_year = self._extract_year(paper.get('pub_year'))
            paper_keywords = self._extract_keywords(paper)
            
            # 计算相似度
            similarity = self._calculate_keyword_similarity(seed_keywords, paper_keywords)
            
            if similarity > 0.3:  # 相似度阈值
                citation_graph['papers'][paper_id] = paper
                
                # 基于时间关系模拟引用
                if paper_year and seed_year:
                    if paper_year < seed_year:
                        # 较早的文献可能被种子文献引用
                        citation_graph['citations'][seed_id].add(paper_id)
                        citation_graph['cited_by'][paper_id].add(seed_id)
                    elif paper_year > seed_year:
                        # 较晚的文献可能引用种子文献
                        citation_graph['citations'][paper_id].add(seed_id)
                        citation_graph['cited_by'][seed_id].add(paper_id)
        
        return citation_graph
    
    def _calculate_relatedness_scores(self, citation_graph: Dict[str, Any], 
                                    seed_paper: Dict[str, Any]) -> Dict[str, float]:
        """计算相关度分数"""
        scores = {}
        seed_id = str(seed_paper.get('pmid', seed_paper.get('title', '').strip().lower()))
        
        for paper_id, paper in citation_graph['papers'].items():
            if paper_id == seed_id:
                scores[paper_id] = 1.0  # 种子文献相关度最高
                continue
            
            # 共引强度（被同一文献引用的次数）
            co_citation_score = len(citation_graph['cited_by'][paper_id] & 
                                  citation_graph['cited_by'][seed_id])
            
            # 共参数量（引用相同文献的数量）
            co_reference_score = len(citation_graph['citations'][paper_id] & 
                                   citation_graph['citations'][seed_id])
            
            # 直接引用关系
            direct_citation_score = 0
            if paper_id in citation_graph['citations'][seed_id] or \
               seed_id in citation_graph['citations'][paper_id]:
                direct_citation_score = 1
            
            # 综合相关度分数
            relatedness = (co_citation_score * 0.4 + 
                         co_reference_score * 0.4 + 
                         direct_citation_score * 0.2)
            
            # 加入时间衰减因子
            paper_year = self._extract_year(paper.get('pub_year'))
            seed_year = self._extract_year(seed_paper.get('pub_year'))
            if paper_year and seed_year:
                year_diff = abs(paper_year - seed_year)
                time_decay = math.exp(-year_diff / 10)  # 10年半衰期
                relatedness *= time_decay
            
            scores[paper_id] = relatedness
        
        return scores
    
    def _select_relevant_papers(self, citation_graph: Dict[str, Any], 
                              relatedness_scores: Dict[str, float]) -> List[Dict[str, Any]]:
        """选择最相关的文献"""
        # 按相关度排序
        sorted_papers = sorted(
            citation_graph['papers'].items(),
            key=lambda x: relatedness_scores.get(x[0], 0),
            reverse=True
        )
        
        # 选择前N篇最相关的文献
        selected = []
        for paper_id, paper in sorted_papers[:self.max_nodes]:
            paper_copy = paper.copy()
            paper_copy['relatedness_score'] = relatedness_scores.get(paper_id, 0)
            paper_copy['node_id'] = paper_id
            selected.append(paper_copy)
        
        return selected
    
    def _generate_network_data(self, selected_papers: List[Dict[str, Any]], 
                             citation_graph: Dict[str, Any], 
                             seed_paper: Dict[str, Any]) -> Dict[str, Any]:
        """生成网络图数据"""
        nodes = []
        edges = []
        
        # 创建节点ID映射
        paper_ids = {paper['node_id'] for paper in selected_papers}
        seed_id = str(seed_paper.get('pmid', seed_paper.get('title', '').strip().lower()))
        
        # 生成节点
        for paper in selected_papers:
            node_id = paper['node_id']
            
            # 计算节点大小（基于被引用次数）
            citation_count = len(citation_graph['cited_by'].get(node_id, set()))
            node_size = max(10, min(50, 10 + citation_count * 2))
            
            # 计算节点颜色（基于发表年份）
            year = self._extract_year(paper.get('pub_year'))
            color_intensity = self._calculate_color_intensity(year)
            
            node = {
                "id": node_id,
                "label": paper.get('title', '')[:50] + "...",
                "title": paper.get('title', ''),
                "authors": paper.get('authors', []),
                "journal": paper.get('journal', ''),
                "year": paper.get('pub_year', ''),
                "pmid": paper.get('pmid', ''),
                "abstract": paper.get('abstract', ''),
                "size": node_size,
                "color": color_intensity,
                "is_seed": node_id == seed_id,
                "relatedness_score": paper.get('relatedness_score', 0),
                "citation_count": citation_count
            }
            nodes.append(node)
        
        # 生成边
        for paper_id in paper_ids:
            # 引用关系
            for cited_id in citation_graph['citations'].get(paper_id, set()):
                if cited_id in paper_ids:
                    edge = {
                        "source": paper_id,
                        "target": cited_id,
                        "type": "citation",
                        "weight": 1
                    }
                    edges.append(edge)
        
        return {
            "nodes": nodes,
            "edges": edges
        }
    
    def _analyze_prior_works(self, seed_paper: Dict[str, Any],
                           papers_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """分析祖先文献（Prior Works）"""
        prior_works = []

        try:
            # 首先尝试获取真实的引用数据
            citation_data = self.get_real_citations(seed_paper)
            real_references = citation_data.get('references', [])

            if real_references:
                logger.info(f"使用真实引用数据，找到 {len(real_references)} 个引用文献")
                # 使用真实的引用数据
                for ref in real_references[:20]:  # 限制数量
                    ref['similarity_score'] = 1.0  # 真实引用关系给最高分
                    ref['is_real_citation'] = True
                    prior_works.append(ref)
            else:
                # 如果没有真实数据，回退到基于相似度的方法
                logger.info("未找到真实引用数据，使用相似度分析")
                seed_year = self._extract_year(seed_paper.get('pub_year'))
                seed_keywords = self._extract_keywords(seed_paper)

                for paper_id, paper in papers_index.items():
                    paper_year = self._extract_year(paper.get('pub_year'))

                    # 只考虑更早发表的文献
                    if paper_year and seed_year and paper_year < seed_year:
                        paper_keywords = self._extract_keywords(paper)
                        similarity = self._calculate_keyword_similarity(seed_keywords, paper_keywords)

                        if similarity > 0.4:  # 较高的相似度阈值
                            paper_copy = paper.copy()
                            paper_copy['similarity_score'] = similarity
                            paper_copy['is_real_citation'] = False
                            prior_works.append(paper_copy)

                # 按相似度排序，返回前20篇
                prior_works.sort(key=lambda x: x['similarity_score'], reverse=True)
                prior_works = prior_works[:20]

        except Exception as e:
            logger.error(f"分析祖先文献失败: {e}")

        return prior_works
    
    def _analyze_derivative_works(self, seed_paper: Dict[str, Any],
                                papers_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """分析后代文献（Derivative Works）"""
        derivative_works = []

        try:
            # 首先尝试获取真实的引用数据
            citation_data = self.get_real_citations(seed_paper)
            real_citations = citation_data.get('citations', [])

            if real_citations:
                logger.info(f"使用真实被引用数据，找到 {len(real_citations)} 个引用该文献的文献")
                # 使用真实的被引用数据
                for cit in real_citations[:20]:  # 限制数量
                    cit['similarity_score'] = 1.0  # 真实引用关系给最高分
                    cit['is_real_citation'] = True
                    derivative_works.append(cit)
            else:
                # 如果没有真实数据，回退到基于相似度的方法
                logger.info("未找到真实被引用数据，使用相似度分析")
                seed_year = self._extract_year(seed_paper.get('pub_year'))
                seed_keywords = self._extract_keywords(seed_paper)

                for paper_id, paper in papers_index.items():
                    paper_year = self._extract_year(paper.get('pub_year'))

                    # 只考虑更晚发表的文献
                    if paper_year and seed_year and paper_year > seed_year:
                        paper_keywords = self._extract_keywords(paper)
                        similarity = self._calculate_keyword_similarity(seed_keywords, paper_keywords)

                        if similarity > 0.4:  # 较高的相似度阈值
                            paper_copy = paper.copy()
                            paper_copy['similarity_score'] = similarity
                            paper_copy['is_real_citation'] = False
                            derivative_works.append(paper_copy)

                # 按相似度排序，返回前20篇
                derivative_works.sort(key=lambda x: x['similarity_score'], reverse=True)
                derivative_works = derivative_works[:20]

        except Exception as e:
            logger.error(f"分析后代文献失败: {e}")

        return derivative_works
    
    def _extract_year(self, pub_year: Any) -> int:
        """提取发表年份"""
        try:
            if isinstance(pub_year, int):
                return pub_year
            elif isinstance(pub_year, str):
                # 提取年份数字
                import re
                year_match = re.search(r'\d{4}', pub_year)
                if year_match:
                    return int(year_match.group())
            return None
        except:
            return None
    
    def _extract_keywords(self, paper: Dict[str, Any]) -> Set[str]:
        """提取文献关键词"""
        keywords = set()
        
        # 从标题提取
        title = paper.get('title', '').lower()
        if title:
            # 简单的关键词提取（实际应用中可以使用更复杂的NLP技术）
            words = title.split()
            keywords.update([word.strip('.,!?;:()[]{}') for word in words if len(word) > 3])
        
        # 从摘要提取（如果有）
        abstract = paper.get('abstract', '').lower()
        if abstract:
            words = abstract.split()[:50]  # 只取前50个词
            keywords.update([word.strip('.,!?;:()[]{}') for word in words if len(word) > 4])
        
        return keywords
    
    def _calculate_keyword_similarity(self, keywords1: Set[str], keywords2: Set[str]) -> float:
        """计算关键词相似度"""
        if not keywords1 or not keywords2:
            return 0.0
        
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_color_intensity(self, year: int) -> str:
        """计算节点颜色强度（基于年份）"""
        if not year:
            return "#888888"
        
        current_year = datetime.now().year
        age = current_year - year
        
        if age <= 2:
            return "#FF6B6B"  # 最新文献 - 红色
        elif age <= 5:
            return "#4ECDC4"  # 较新文献 - 青色
        elif age <= 10:
            return "#45B7D1"  # 中等年龄 - 蓝色
        else:
            return "#96CEB4"  # 较老文献 - 绿色


    def get_real_citations(self, paper: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取真实的引用关系数据

        Args:
            paper: 文献信息

        Returns:
            包含references（引用的文献）和citations（被引用的文献）的字典
        """
        result = {
            'references': [],  # 该文献引用的其他文献（祖先文献）
            'citations': []    # 引用该文献的其他文献（后代文献）
        }

        try:
            # 尝试通过多种方式获取引用数据
            pmid = paper.get('pmid')
            doi = paper.get('doi')
            title = paper.get('title', '')

            # 1. 尝试Semantic Scholar API
            if pmid or doi or title:
                semantic_data = self._get_semantic_scholar_citations(pmid, doi, title)
                if semantic_data:
                    result['references'].extend(semantic_data.get('references', []))
                    result['citations'].extend(semantic_data.get('citations', []))

            # 2. 如果Semantic Scholar没有数据，尝试OpenCitations
            if not result['references'] and not result['citations'] and doi:
                opencitations_data = self._get_opencitations_data(doi)
                if opencitations_data:
                    result['references'].extend(opencitations_data.get('references', []))
                    result['citations'].extend(opencitations_data.get('citations', []))

            logger.info(f"获取到引用数据: {len(result['references'])} 个引用, {len(result['citations'])} 个被引用")

        except Exception as e:
            logger.error(f"获取引用关系失败: {e}")

        return result

    def _get_semantic_scholar_citations(self, pmid: str = None, doi: str = None, title: str = None) -> Dict[str, List[Dict[str, Any]]]:
        """通过Semantic Scholar API获取引用数据"""
        try:
            # 构建查询参数
            paper_id = None
            if pmid:
                paper_id = f"PMID:{pmid}"
            elif doi:
                paper_id = f"DOI:{doi}"
            elif title:
                # 通过标题搜索
                search_url = f"{self.semantic_scholar_base_url}/search"
                search_params = {
                    'query': title,
                    'limit': 1,
                    'fields': 'paperId,title,authors,year,journal,citationCount,referenceCount'
                }

                response = requests.get(search_url, params=search_params, timeout=10)
                if response.status_code == 200:
                    search_data = response.json()
                    if search_data.get('data') and len(search_data['data']) > 0:
                        paper_id = search_data['data'][0]['paperId']

            if not paper_id:
                return {}

            # 获取引用和被引用数据
            result = {'references': [], 'citations': []}

            # 获取该文献引用的其他文献（references）
            ref_url = f"{self.semantic_scholar_base_url}/{paper_id}/references"
            ref_params = {
                'fields': 'paperId,title,authors,year,journal,citationCount',
                'limit': 50
            }

            time.sleep(0.1)  # 避免请求过快
            ref_response = requests.get(ref_url, params=ref_params, timeout=10)
            if ref_response.status_code == 200:
                ref_data = ref_response.json()
                for ref in ref_data.get('data', []):
                    if ref.get('citedPaper'):
                        cited_paper = ref['citedPaper']
                        result['references'].append({
                            'id': cited_paper.get('paperId'),
                            'title': cited_paper.get('title', ''),
                            'authors': [author.get('name', '') for author in cited_paper.get('authors', [])],
                            'year': str(cited_paper.get('year', '')),
                            'journal': cited_paper.get('journal', {}).get('name', ''),
                            'citation_count': cited_paper.get('citationCount', 0)
                        })

            # 获取引用该文献的其他文献（citations）
            cit_url = f"{self.semantic_scholar_base_url}/{paper_id}/citations"
            cit_params = {
                'fields': 'paperId,title,authors,year,journal,citationCount',
                'limit': 50
            }

            time.sleep(0.1)  # 避免请求过快
            cit_response = requests.get(cit_url, params=cit_params, timeout=10)
            if cit_response.status_code == 200:
                cit_data = cit_response.json()
                for cit in cit_data.get('data', []):
                    if cit.get('citingPaper'):
                        citing_paper = cit['citingPaper']
                        result['citations'].append({
                            'id': citing_paper.get('paperId'),
                            'title': citing_paper.get('title', ''),
                            'authors': [author.get('name', '') for author in citing_paper.get('authors', [])],
                            'year': str(citing_paper.get('year', '')),
                            'journal': citing_paper.get('journal', {}).get('name', ''),
                            'citation_count': citing_paper.get('citationCount', 0)
                        })

            return result

        except Exception as e:
            logger.error(f"Semantic Scholar API请求失败: {e}")
            return {}

# 全局服务实例
literature_tracking_service = LiteratureTrackingService()
