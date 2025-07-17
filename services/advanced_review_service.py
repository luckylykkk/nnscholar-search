#!/usr/bin/env python3
"""
高级综述生成服务

按照学术标准流程生成高质量文献综述：
1. 文献相关度分析和筛选
2. 综述大纲生成
3. 分段内容填充
4. 整合和格式化
5. Word文档导出
"""

import logging
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime
import json

from services.deepseek_service import DeepSeekService
from services.embedding_service import EmbeddingService
from utils.text_processing import preprocess_text

logger = logging.getLogger(__name__)


class AdvancedReviewService:
    """高级综述生成服务"""

    def __init__(self, deepseek_service=None):
        self.deepseek = deepseek_service or DeepSeekService()
        self.embedding = EmbeddingService()
    
    def generate_comprehensive_review(self, papers: List[Dict[str, Any]],
                                    topic: str, user_title: str = None,
                                    language: str = 'chinese',
                                    progress_callback=None) -> Dict[str, Any]:
        """
        生成完整的学术综述
        
        Args:
            papers: 检索到的文献列表
            topic: 研究主题
            user_title: 用户指定的综述题目
            
        Returns:
            包含完整综述内容的字典
        """
        try:
            logger.info(f"开始生成高级综述: topic='{topic}', user_title='{user_title}', papers={len(papers)}")
            
            # 步骤1: 文献相关度分析和筛选
            if progress_callback:
                progress_callback(10, "正在分析文献相关度...")
            logger.info("步骤1: 进行文献相关度分析...")
            relevant_papers = self._analyze_relevance_and_filter(papers, user_title or topic)
            logger.info(f"筛选出 {len(relevant_papers)} 篇最相关文献")

            # 步骤2: 生成综述大纲
            if progress_callback:
                progress_callback(30, "正在生成综述大纲...")
            logger.info("步骤2: 生成综述大纲...")
            outline = self._generate_review_outline(relevant_papers, user_title or topic, language, progress_callback)
            logger.info("综述大纲生成完成")

            # 显示生成的大纲
            if progress_callback and outline:
                outline_text = self._format_outline_for_display(outline)
                progress_callback(40, f"大纲生成完成！\n\n{outline_text}")

            # 步骤3: 分段内容填充
            if progress_callback:
                progress_callback(50, "正在填充各章节内容...")
            logger.info("步骤3: 进行分段内容填充...")
            sections = self._fill_section_content(outline, relevant_papers, user_title or topic, language, progress_callback)
            logger.info(f"完成 {len(sections)} 个章节的内容填充")

            # 步骤4: 整合和格式化
            if progress_callback:
                progress_callback(90, "正在整合和格式化...")
            logger.info("步骤4: 整合和格式化...")
            final_review = self._integrate_and_format(sections, relevant_papers, user_title or topic, language)
            logger.info("综述整合和格式化完成")

            if progress_callback:
                progress_callback(100, "综述生成完成！")
            
            return {
                "success": True,
                "title": user_title or f"{topic} - 文献综述",
                "content": final_review["content"],
                "references": final_review["references"],
                "paper_count": len(relevant_papers),
                "total_papers": len(papers),
                "outline": outline,
                "generated_at": datetime.now().isoformat(),
                "word_count": len(final_review["content"]),
                "reference_count": len(final_review["references"])
            }
            
        except Exception as e:
            logger.error(f"高级综述生成失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "paper_count": len(papers) if papers else 0
            }

    def _format_outline_for_display(self, outline: Dict[str, Any]) -> str:
        """
        格式化大纲用于显示

        Args:
            outline: 大纲数据

        Returns:
            格式化的大纲文本
        """
        if not outline or 'sections' not in outline:
            return "大纲生成失败"

        formatted_text = f"📋 **{outline.get('title', '综述大纲')}**\n\n"

        for section in outline.get('sections', []):
            section_title = section.get('section_title', '')
            section_number = section.get('section_number', '')
            formatted_text += f"**{section_number}. {section_title}**\n"

            for subsection in section.get('subsections', []):
                subsection_title = subsection.get('subsection_title', '')
                subsection_number = subsection.get('subsection_number', '')
                formatted_text += f"  {subsection_number} {subsection_title}\n"

            formatted_text += "\n"

        return formatted_text

    def _format_outline_for_display(self, outline: Dict[str, Any]) -> str:
        """
        格式化大纲用于显示

        Args:
            outline: 大纲数据

        Returns:
            格式化的大纲文本
        """
        if not outline or 'sections' not in outline:
            return "大纲生成失败"

        formatted_text = f"📋 **{outline.get('title', '综述大纲')}**\n\n"

        for section in outline.get('sections', []):
            section_title = section.get('section_title', '')
            section_number = section.get('section_number', '')
            formatted_text += f"**{section_number}. {section_title}**\n"

            for subsection in section.get('subsections', []):
                subsection_title = subsection.get('subsection_title', '')
                subsection_number = subsection.get('subsection_number', '')
                formatted_text += f"  {subsection_number} {subsection_title}\n"

            formatted_text += "\n"

        return formatted_text
    
    def _analyze_relevance_and_filter(self, papers: List[Dict[str, Any]], 
                                    title: str) -> List[Dict[str, Any]]:
        """
        分析文献相关度并筛选最相关的100篇
        
        Args:
            papers: 原始文献列表
            title: 综述题目
            
        Returns:
            按相关度排序的前100篇文献
        """
        try:
            if len(papers) <= 100:
                return papers
            
            # 使用嵌入模型计算相关度
            title_embedding = self.embedding.get_embeddings_batch([title])[0]
            
            scored_papers = []
            for paper in papers:
                # 构建文献文本用于相关度计算
                paper_text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
                if paper_text.strip():
                    try:
                        paper_embedding = self.embedding.get_embeddings_batch([paper_text])[0]
                        # 计算余弦相似度
                        similarity = self._cosine_similarity(title_embedding, paper_embedding)
                        paper_copy = paper.copy()
                        paper_copy['relevance_score'] = similarity
                        scored_papers.append(paper_copy)
                    except Exception as e:
                        logger.warning(f"计算文献相关度失败: {e}")
                        paper_copy = paper.copy()
                        paper_copy['relevance_score'] = 0.0
                        scored_papers.append(paper_copy)
            
            # 按相关度排序并取前100篇
            scored_papers.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            return scored_papers[:100]
            
        except Exception as e:
            logger.error(f"文献相关度分析失败: {e}")
            # 如果失败，返回前100篇
            return papers[:100]
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        try:
            import numpy as np
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
        except Exception:
            return 0.0
    
    def _generate_review_outline(self, papers: List[Dict[str, Any]], title: str, language: str = 'chinese', progress_callback=None) -> Dict[str, Any]:
        """
        生成综述大纲
        
        Args:
            papers: 筛选后的文献列表
            title: 综述题目
            
        Returns:
            综述大纲结构
        """
        try:
            # 准备文献摘要信息
            paper_summaries = []
            for i, paper in enumerate(papers[:30]):  # 使用前30篇最相关的文献
                summary = f"{i+1}. {paper.get('title', '')}"
                if paper.get('abstract'):
                    summary += f"\n摘要: {paper.get('abstract', '')[:200]}..."
                paper_summaries.append(summary)
            
            # 构建大纲生成提示词
            if language == 'english':
                outline_prompt = f"""As a senior academic review expert, please generate a detailed review outline for "{title}" based on the following literature.

Literature Information:
{chr(10).join(paper_summaries)}

Please generate a well-structured and logically clear review outline with the following requirements:
1. The outline should contain 6-8 main sections
2. Each section should have 2-4 subsections
3. Section titles should accurately reflect the content focus
4. Clear logical hierarchy from background to current status to prospects
5. Conform to standard academic review structure

Please return the outline in JSON format as follows:
{{
  "title": "Review Title",
  "sections": [
    {{
      "section_number": "1",
      "section_title": "Introduction",
      "subsections": [
        {{"subsection_number": "1.1", "subsection_title": "Research Background"}},
        {{"subsection_number": "1.2", "subsection_title": "Research Significance"}}
      ]
    }}
  ]
}}"""
            else:
                outline_prompt = f"""作为资深的学术综述专家，请基于以下文献为"{title}"生成详细的综述大纲。

文献信息：
{chr(10).join(paper_summaries)}

请生成一个结构严谨、逻辑清晰的综述大纲，包含以下要求：
1. 大纲应包含6-8个主要章节
2. 每个章节应有2-4个子章节
3. 章节标题要准确反映内容重点
4. 逻辑层次清晰，从背景到现状到展望
5. 符合学术综述的标准结构

请以JSON格式返回大纲，格式如下：
{{
  "title": "综述标题",
  "sections": [
    {{
      "section_number": "1",
      "section_title": "引言",
      "subsections": [
        {{"subsection_number": "1.1", "subsection_title": "研究背景"}},
        {{"subsection_number": "1.2", "subsection_title": "研究意义"}}
      ]
    }}
  ]
}}"""

            # 调用AI生成大纲
            outline_text = self.deepseek.analyze_text(outline_prompt)
            
            # 尝试解析JSON
            try:
                outline = json.loads(outline_text)
                return outline
            except json.JSONDecodeError:
                # 如果JSON解析失败，使用默认大纲
                logger.warning("大纲JSON解析失败，使用默认大纲")
                return self._get_default_outline(title)
                
        except Exception as e:
            logger.error(f"生成综述大纲失败: {e}")
            return self._get_default_outline(title)
    
    def _get_default_outline(self, title: str) -> Dict[str, Any]:
        """获取默认综述大纲"""
        return {
            "title": title,
            "sections": [
                {
                    "section_number": "1",
                    "section_title": "引言",
                    "subsections": [
                        {"subsection_number": "1.1", "subsection_title": "研究背景"},
                        {"subsection_number": "1.2", "subsection_title": "研究意义"},
                        {"subsection_number": "1.3", "subsection_title": "综述目的"}
                    ]
                },
                {
                    "section_number": "2", 
                    "section_title": "研究现状",
                    "subsections": [
                        {"subsection_number": "2.1", "subsection_title": "理论基础"},
                        {"subsection_number": "2.2", "subsection_title": "技术发展"},
                        {"subsection_number": "2.3", "subsection_title": "应用进展"}
                    ]
                },
                {
                    "section_number": "3",
                    "section_title": "方法与技术",
                    "subsections": [
                        {"subsection_number": "3.1", "subsection_title": "主要方法"},
                        {"subsection_number": "3.2", "subsection_title": "技术比较"},
                        {"subsection_number": "3.3", "subsection_title": "性能评估"}
                    ]
                },
                {
                    "section_number": "4",
                    "section_title": "挑战与问题",
                    "subsections": [
                        {"subsection_number": "4.1", "subsection_title": "技术挑战"},
                        {"subsection_number": "4.2", "subsection_title": "应用障碍"},
                        {"subsection_number": "4.3", "subsection_title": "标准化问题"}
                    ]
                },
                {
                    "section_number": "5",
                    "section_title": "发展趋势与展望",
                    "subsections": [
                        {"subsection_number": "5.1", "subsection_title": "技术趋势"},
                        {"subsection_number": "5.2", "subsection_title": "应用前景"},
                        {"subsection_number": "5.3", "subsection_title": "研究方向"}
                    ]
                },
                {
                    "section_number": "6",
                    "section_title": "结论",
                    "subsections": [
                        {"subsection_number": "6.1", "subsection_title": "主要结论"},
                        {"subsection_number": "6.2", "subsection_title": "研究建议"}
                    ]
                }
            ]
        }


    def _fill_section_content(self, outline: Dict[str, Any],
                            papers: List[Dict[str, Any]], title: str,
                            language: str = 'chinese', progress_callback=None) -> List[Dict[str, Any]]:
        """
        高级分段内容填充模块

        实现智能的章节内容生成，包括：
        1. 文献相关度分析和筛选
        2. 子章节内容生成
        3. 引用格式化
        4. 内容质量控制

        Args:
            outline: 综述大纲
            papers: 文献列表
            title: 综述题目
            language: 语言选择
            progress_callback: 进度回调函数

        Returns:
            包含内容的章节列表
        """
        sections_with_content = []

        try:
            total_sections = len(outline.get('sections', []))
            logger.info(f"开始分段内容填充，共{total_sections}个章节")

            # 预处理：构建文献索引和嵌入向量
            papers_index = self._build_papers_index_for_sections(papers)

            for i, section in enumerate(outline.get('sections', [])):
                if progress_callback:
                    progress = 50 + int((i / total_sections) * 35)  # 50-85%的进度
                    progress_callback(progress, f"正在生成第{i+1}/{total_sections}个章节: {section.get('section_title', '')}")

                logger.info(f"生成章节 {i+1}/{total_sections}: {section.get('section_title', '')}")

                # 生成章节内容
                section_content = self._generate_enhanced_section_content(
                    section, papers, papers_index, title, language
                )

                # 验证内容质量
                if self._validate_section_content(section_content):
                    sections_with_content.append(section_content)
                    logger.info(f"章节 {section.get('section_title', '')} 内容生成成功")
                else:
                    logger.warning(f"章节 {section.get('section_title', '')} 内容质量不达标，使用备用内容")
                    # 生成备用内容
                    fallback_content = self._generate_fallback_section_content(section, language)
                    sections_with_content.append(fallback_content)

        except Exception as e:
            logger.error(f"分段内容填充失败: {e}")
            # 生成基础章节结构作为备用
            for section in outline.get('sections', []):
                fallback_content = self._generate_fallback_section_content(section, language)
                sections_with_content.append(fallback_content)

        logger.info(f"分段内容填充完成，生成了{len(sections_with_content)}个章节")
        return sections_with_content

    def _generate_section_content(self, section: Dict[str, Any],
                                papers: List[Dict[str, Any]], title: str,
                                language: str = 'chinese') -> Dict[str, Any]:
        """
        生成单个章节的内容

        Args:
            section: 章节信息
            papers: 文献列表
            title: 综述题目

        Returns:
            包含内容的章节
        """
        try:
            section_title = section.get('section_title', '')
            section_number = section.get('section_number', '')

            # 为该章节筛选最相关的文献
            relevant_papers = self._find_relevant_papers_for_section(
                section_title, papers, max_papers=20
            )

            # 准备文献信息
            paper_info = []
            for paper in relevant_papers:
                info = f"PMID: {paper.get('pmid', 'N/A')}\n"
                info += f"标题: {paper.get('title', '')}\n"
                if paper.get('abstract'):
                    info += f"摘要: {paper.get('abstract', '')[:300]}...\n"
                info += f"期刊: {paper.get('journal', '')} ({paper.get('pub_year', '')})\n"
                paper_info.append(info)

            # 构建内容生成提示词
            if language == 'english':
                content_prompt = f"""As an academic review expert, please write detailed content for Section {section_number} "{section_title}" of the review "{title}".

Relevant Literature:
{chr(10).join(['---'] + paper_info)}

Section Subsections:
{chr(10).join([f"{sub.get('subsection_number', '')} {sub.get('subsection_title', '')}" for sub in section.get('subsections', [])])}

Requirements:
1. Content should be substantial and academic, 800-1200 words
2. Strictly based on provided literature, no fabricated content
3. Use [PMID:specific_PMID_number] format when citing literature
4. Organize content according to subsection structure
5. Accurate language and clear logic
6. Use HTML format with appropriate heading tags

Please generate the complete content for this section:"""
            else:
                content_prompt = f"""作为学术综述专家，请为综述"{title}"的第{section_number}章节"{section_title}"撰写详细内容。

相关文献：
{chr(10).join(['---'] + paper_info)}

章节子标题：
{chr(10).join([f"{sub.get('subsection_number', '')} {sub.get('subsection_title', '')}" for sub in section.get('subsections', [])])}

要求：
1. 内容要充实、学术性强，字数800-1200字
2. 严格基于提供的文献撰写，不得编造内容
3. 在文中引用文献时使用[PMID:具体PMID号]格式
4. 按照子章节结构组织内容
5. 语言准确、逻辑清晰
6. 使用HTML格式，包含适当的标题标签

请生成该章节的完整内容："""

            # 调用AI生成内容
            content = self.deepseek.analyze_text(content_prompt)

            # 返回包含内容的章节
            section_with_content = section.copy()
            section_with_content['content'] = content
            section_with_content['relevant_papers'] = relevant_papers

            return section_with_content

        except Exception as e:
            logger.error(f"生成章节内容失败: {e}")
            # 返回基础章节结构
            section_with_content = section.copy()
            section_with_content['content'] = f"<h3>{section.get('section_title', '')}</h3><p>该章节内容生成失败，请重试。</p>"
            section_with_content['relevant_papers'] = []
            return section_with_content

    def _find_relevant_papers_for_section(self, section_title: str,
                                        papers: List[Dict[str, Any]],
                                        max_papers: int = 20) -> List[Dict[str, Any]]:
        """
        为特定章节找到最相关的文献

        Args:
            section_title: 章节标题
            papers: 文献列表
            max_papers: 最大文献数量

        Returns:
            相关文献列表
        """
        try:
            # 使用嵌入模型计算相关度
            section_embedding = self.embedding.get_embeddings_batch([section_title])[0]

            scored_papers = []
            for paper in papers:
                paper_text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
                if paper_text.strip():
                    try:
                        paper_embedding = self.embedding.get_embeddings_batch([paper_text])[0]
                        similarity = self._cosine_similarity(section_embedding, paper_embedding)
                        paper_copy = paper.copy()
                        paper_copy['section_relevance'] = similarity
                        scored_papers.append(paper_copy)
                    except Exception:
                        paper_copy = paper.copy()
                        paper_copy['section_relevance'] = 0.0
                        scored_papers.append(paper_copy)

            # 按相关度排序并返回前N篇
            scored_papers.sort(key=lambda x: x.get('section_relevance', 0), reverse=True)
            return scored_papers[:max_papers]

        except Exception as e:
            logger.error(f"章节文献筛选失败: {e}")
            return papers[:max_papers]

    def _integrate_and_format(self, sections: List[Dict[str, Any]],
                            papers: List[Dict[str, Any]], title: str,
                            language: str = 'chinese') -> Dict[str, Any]:
        """
        高级综述整合和格式化模块

        实现完整的综述整合功能：
        1. 章节内容整合
        2. 引用格式统一化（PMID -> [1][2]格式）
        3. 参考文献列表生成
        4. 内容质量检查和优化
        5. 学术格式规范化

        Args:
            sections: 包含内容的章节列表
            papers: 文献列表
            title: 综述题目
            language: 语言选择

        Returns:
            格式化后的完整综述
        """
        try:
            logger.info(f"开始综述整合和格式化，共{len(sections)}个章节")

            # 1. 生成综述摘要
            abstract = self._generate_review_abstract(sections, title, language)

            # 2. 收集所有引用的PMID并去重
            all_pmids = []
            pmid_usage_count = {}

            # 3. 构建完整内容结构
            full_content = f"<h1>{title}</h1>\n\n"

            # 添加摘要
            if language == 'english':
                full_content += "<h2>Abstract</h2>\n"
                full_content += f"<p>{abstract}</p>\n\n"
            else:
                full_content += "<h2>摘要</h2>\n"
                full_content += f"<p>{abstract}</p>\n\n"

            # 4. 整合各章节内容
            for i, section in enumerate(sections):
                content = section.get('content', '')

                # 提取并统计PMID引用
                import re
                pmid_matches = re.findall(r'\[PMID:(\d+)\]', content)
                for pmid in pmid_matches:
                    if pmid not in all_pmids:
                        all_pmids.append(pmid)
                    pmid_usage_count[pmid] = pmid_usage_count.get(pmid, 0) + 1

                # 添加章节分隔
                if i > 0:
                    full_content += "\n<hr>\n\n"

                full_content += content + "\n\n"

            # 5. 将PMID引用替换为数字引用（按使用频率排序）
            sorted_pmids = sorted(all_pmids, key=lambda x: pmid_usage_count.get(x, 0), reverse=True)
            pmid_to_number = {pmid: i+1 for i, pmid in enumerate(sorted_pmids)}

            for pmid, number in pmid_to_number.items():
                full_content = full_content.replace(f'[PMID:{pmid}]', f'[{number}]')

            # 6. 生成高质量参考文献列表
            references = self._generate_enhanced_references(sorted_pmids, papers, language)

            # 7. 添加参考文献部分
            if language == 'english':
                full_content += "<h2>References</h2>\n<ol>\n"
            else:
                full_content += "<h2>参考文献</h2>\n<ol>\n"
            for ref in references:
                full_content += f"<li>{ref}</li>\n"
            full_content += "</ol>\n"

            # 8. 添加综述统计信息
            stats = self._calculate_review_statistics(full_content, references, sections)

            # 9. 格式化和美化
            formatted_content = self._apply_academic_formatting(full_content, language)

            logger.info(f"综述整合完成：{stats['word_count']}字，{len(references)}个参考文献")

            return {
                "content": formatted_content,
                "abstract": abstract,
                "references": references,
                "pmid_mapping": pmid_to_number,
                "statistics": stats,
                "sections_count": len(sections),
                "citation_count": len(sorted_pmids)
            }

        except Exception as e:
            logger.error(f"综述整合和格式化失败: {e}")
            # 返回基础内容
            basic_content = f"<h1>{title}</h1>\n<p>综述内容整合失败，请重试。</p>"
            return {
                "content": basic_content,
                "references": [],
                "pmid_mapping": {}
            }

    def _generate_references(self, pmids: List[str],
                           papers: List[Dict[str, Any]]) -> List[str]:
        """
        生成APA格式的参考文献列表

        Args:
            pmids: PMID列表
            papers: 文献列表

        Returns:
            APA格式的参考文献列表
        """
        references = []
        pmid_to_paper = {str(paper.get('pmid', '')): paper for paper in papers}

        for pmid in pmids:
            paper = pmid_to_paper.get(pmid)
            if paper:
                ref = self._format_apa_reference(paper)
                references.append(ref)
            else:
                references.append(f"PMID: {pmid} (文献信息不可用)")

        return references

    def _format_apa_reference(self, paper: Dict[str, Any]) -> str:
        """
        将文献格式化为APA格式

        Args:
            paper: 文献信息

        Returns:
            APA格式的参考文献
        """
        try:
            authors = paper.get('authors', [])
            title = paper.get('title', '')
            journal = paper.get('journal', '')
            year = paper.get('pub_year', '')
            doi = paper.get('doi', '')
            pmid = paper.get('pmid', '')

            # 处理作者
            if authors:
                if len(authors) == 1:
                    author_str = authors[0]
                elif len(authors) <= 6:
                    author_str = ', '.join(authors[:-1]) + ', & ' + authors[-1]
                else:
                    author_str = ', '.join(authors[:6]) + ', ... ' + authors[-1]
            else:
                author_str = "作者未知"

            # 构建APA格式引用
            reference = f"{author_str} ({year}). {title}. <em>{journal}</em>."

            if doi:
                reference += f" https://doi.org/{doi}"
            elif pmid:
                reference += f" PMID: {pmid}"

            return reference

        except Exception as e:
            logger.error(f"格式化参考文献失败: {e}")
            return f"PMID: {paper.get('pmid', 'N/A')} - 格式化失败"

    def _build_papers_index_for_sections(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        为分段内容填充构建文献索引

        Args:
            papers: 文献列表

        Returns:
            文献索引字典
        """
        try:
            papers_index = {
                'by_pmid': {},
                'by_title': {},
                'keywords': {}
            }

            for paper in papers:
                pmid = str(paper.get('pmid', ''))
                title = paper.get('title', '').lower()

                if pmid:
                    papers_index['by_pmid'][pmid] = paper
                if title:
                    papers_index['by_title'][title] = paper

                # 提取关键词
                keywords = self._extract_paper_keywords(paper)
                papers_index['keywords'][pmid] = keywords

            logger.info(f"构建文献索引完成，索引了{len(papers)}篇文献")
            return papers_index

        except Exception as e:
            logger.error(f"构建文献索引失败: {e}")
            return {'by_pmid': {}, 'by_title': {}, 'keywords': {}}

    def _extract_paper_keywords(self, paper: Dict[str, Any]) -> List[str]:
        """
        从文献中提取关键词

        Args:
            paper: 文献信息

        Returns:
            关键词列表
        """
        keywords = []

        # 从标题提取
        title = paper.get('title', '')
        if title:
            # 简单的关键词提取
            import re
            words = re.findall(r'\b[A-Za-z]{3,}\b', title.lower())
            keywords.extend(words[:5])  # 取前5个词

        # 从摘要提取
        abstract = paper.get('abstract', '')
        if abstract:
            words = re.findall(r'\b[A-Za-z]{4,}\b', abstract.lower())
            keywords.extend(words[:10])  # 取前10个词

        return list(set(keywords))  # 去重

    def _generate_enhanced_section_content(self, section: Dict[str, Any],
                                         papers: List[Dict[str, Any]],
                                         papers_index: Dict[str, Any],
                                         title: str, language: str) -> Dict[str, Any]:
        """
        生成增强的章节内容

        Args:
            section: 章节信息
            papers: 文献列表
            papers_index: 文献索引
            title: 综述题目
            language: 语言

        Returns:
            包含内容的章节
        """
        try:
            section_title = section.get('section_title', '')

            # 智能筛选相关文献
            relevant_papers = self._find_relevant_papers_for_section(
                section_title, papers, max_papers=15
            )

            # 生成子章节内容
            subsections_content = []
            for subsection in section.get('subsections', []):
                subsection_content = self._generate_subsection_content(
                    subsection, relevant_papers, title, language
                )
                subsections_content.append(subsection_content)

            # 整合章节内容
            full_content = self._integrate_section_content(
                section, subsections_content, relevant_papers, language
            )

            # 返回完整章节
            section_with_content = section.copy()
            section_with_content['content'] = full_content
            section_with_content['relevant_papers'] = relevant_papers
            section_with_content['subsections_content'] = subsections_content

            return section_with_content

        except Exception as e:
            logger.error(f"生成增强章节内容失败: {e}")
            return self._generate_fallback_section_content(section, language)

    def _generate_subsection_content(self, subsection: Dict[str, Any],
                                   papers: List[Dict[str, Any]],
                                   title: str, language: str) -> str:
        """
        生成子章节内容

        Args:
            subsection: 子章节信息
            papers: 相关文献
            title: 综述题目
            language: 语言

        Returns:
            子章节内容
        """
        try:
            subsection_title = subsection.get('subsection_title', '')
            subsection_number = subsection.get('subsection_number', '')

            # 为子章节筛选最相关的文献
            relevant_papers = papers[:5]  # 取前5篇最相关的

            # 准备文献信息
            paper_info = []
            for paper in relevant_papers:
                info = f"PMID: {paper.get('pmid', 'N/A')}\n"
                info += f"标题: {paper.get('title', '')}\n"
                if paper.get('abstract'):
                    info += f"摘要: {paper.get('abstract', '')[:200]}...\n"
                paper_info.append(info)

            # 构建提示词
            if language == 'english':
                prompt = f"""Write detailed content for subsection {subsection_number} "{subsection_title}" based on the following literature:

{chr(10).join(paper_info)}

Requirements:
1. 300-500 words
2. Use [PMID:number] format for citations
3. Academic writing style
4. Focus on the specific subsection topic

Content:"""
            else:
                prompt = f"""基于以下文献为子章节{subsection_number}"{subsection_title}"撰写详细内容：

{chr(10).join(paper_info)}

要求：
1. 300-500字
2. 使用[PMID:编号]格式引用
3. 学术写作风格
4. 聚焦子章节主题

内容："""

            # 调用AI生成内容
            content = self.deepseek.analyze_text(prompt)
            return content or f"<h4>{subsection_title}</h4><p>该子章节内容生成失败。</p>"

        except Exception as e:
            logger.error(f"生成子章节内容失败: {e}")
            return f"<h4>{subsection.get('subsection_title', '')}</h4><p>该子章节内容生成失败。</p>"

    def _integrate_section_content(self, section: Dict[str, Any],
                                 subsections_content: List[str],
                                 papers: List[Dict[str, Any]],
                                 language: str) -> str:
        """
        整合章节内容

        Args:
            section: 章节信息
            subsections_content: 子章节内容列表
            papers: 相关文献
            language: 语言

        Returns:
            完整的章节内容
        """
        try:
            section_title = section.get('section_title', '')
            section_number = section.get('section_number', '')

            # 构建章节头部
            content = f"<h2>{section_number} {section_title}</h2>\n\n"

            # 添加章节介绍
            if language == 'english':
                intro = f"<p>This section provides a comprehensive overview of {section_title.lower()}.</p>\n\n"
            else:
                intro = f"<p>本章节对{section_title}进行全面综述。</p>\n\n"
            content += intro

            # 整合子章节内容
            for subsection_content in subsections_content:
                content += subsection_content + "\n\n"

            # 添加章节小结
            if language == 'english':
                summary = f"<p>In summary, the research in {section_title.lower()} demonstrates significant progress and ongoing challenges that warrant further investigation.</p>\n"
            else:
                summary = f"<p>综上所述，{section_title}领域的研究取得了显著进展，但仍存在需要进一步探索的挑战。</p>\n"
            content += summary

            return content

        except Exception as e:
            logger.error(f"整合章节内容失败: {e}")
            return f"<h2>{section.get('section_title', '')}</h2><p>章节内容整合失败。</p>"

    def _validate_section_content(self, section_content: Dict[str, Any]) -> bool:
        """
        验证章节内容质量

        Args:
            section_content: 章节内容

        Returns:
            是否通过验证
        """
        try:
            content = section_content.get('content', '')

            # 基本验证
            if not content or len(content) < 100:
                return False

            # 检查是否包含HTML标签
            if '<h' not in content:
                return False

            # 检查是否包含引用
            if '[PMID:' not in content:
                logger.warning("章节内容缺少文献引用")

            # 检查字数
            import re
            text_content = re.sub(r'<[^>]+>', '', content)
            if len(text_content) < 200:
                return False

            return True

        except Exception as e:
            logger.error(f"验证章节内容失败: {e}")
            return False

    def _generate_fallback_section_content(self, section: Dict[str, Any],
                                         language: str) -> Dict[str, Any]:
        """
        生成备用章节内容

        Args:
            section: 章节信息
            language: 语言

        Returns:
            备用章节内容
        """
        try:
            section_title = section.get('section_title', '')
            section_number = section.get('section_number', '')

            if language == 'english':
                content = f"""<h2>{section_number} {section_title}</h2>
<p>This section discusses {section_title.lower()}. Due to technical limitations, detailed content generation was not successful. Please refer to the relevant literature for comprehensive information on this topic.</p>

<h3>Key Points</h3>
<ul>
<li>Current research status in {section_title.lower()}</li>
<li>Main methodological approaches</li>
<li>Future research directions</li>
</ul>

<p>Further analysis of this topic requires additional literature review and expert consultation.</p>"""
            else:
                content = f"""<h2>{section_number} {section_title}</h2>
<p>本章节讨论{section_title}。由于技术限制，详细内容生成未能成功。请参考相关文献获取该主题的全面信息。</p>

<h3>要点</h3>
<ul>
<li>{section_title}的研究现状</li>
<li>主要方法学途径</li>
<li>未来研究方向</li>
</ul>

<p>该主题的进一步分析需要额外的文献综述和专家咨询。</p>"""

            section_with_content = section.copy()
            section_with_content['content'] = content
            section_with_content['relevant_papers'] = []
            section_with_content['is_fallback'] = True

            return section_with_content

        except Exception as e:
            logger.error(f"生成备用章节内容失败: {e}")
            return {
                'section_title': section.get('section_title', ''),
                'section_number': section.get('section_number', ''),
                'content': f"<h2>{section.get('section_title', '')}</h2><p>内容生成失败。</p>",
                'relevant_papers': [],
                'is_fallback': True
            }

    def _generate_review_abstract(self, sections: List[Dict[str, Any]],
                                title: str, language: str) -> str:
        """
        生成综述摘要

        Args:
            sections: 章节列表
            title: 综述题目
            language: 语言

        Returns:
            综述摘要
        """
        try:
            # 提取各章节的关键信息
            section_summaries = []
            for section in sections[:5]:  # 只使用前5个章节
                section_title = section.get('section_title', '')
                if section_title:
                    section_summaries.append(section_title)

            sections_text = ', '.join(section_summaries)

            if language == 'english':
                prompt = f"""Write a comprehensive abstract for the review titled "{title}". The review covers the following main sections: {sections_text}.

Requirements:
1. 200-300 words
2. Include background, objectives, main findings, and conclusions
3. Academic writing style
4. No citations in abstract

Abstract:"""
            else:
                prompt = f"""为题为"{title}"的综述撰写全面的摘要。该综述涵盖以下主要章节：{sections_text}。

要求：
1. 200-300字
2. 包含背景、目标、主要发现和结论
3. 学术写作风格
4. 摘要中不包含引用

摘要："""

            abstract = self.deepseek.analyze_text(prompt)
            return abstract or "本综述对相关领域进行了全面分析。"

        except Exception as e:
            logger.error(f"生成综述摘要失败: {e}")
            if language == 'english':
                return "This review provides a comprehensive analysis of the relevant field."
            else:
                return "本综述对相关领域进行了全面分析。"

    def _generate_enhanced_references(self, pmids: List[str],
                                    papers: List[Dict[str, Any]],
                                    language: str) -> List[str]:
        """
        生成增强的参考文献列表

        Args:
            pmids: PMID列表（按重要性排序）
            papers: 文献列表
            language: 语言

        Returns:
            格式化的参考文献列表
        """
        references = []
        pmid_to_paper = {str(paper.get('pmid', '')): paper for paper in papers}

        for pmid in pmids:
            paper = pmid_to_paper.get(pmid)
            if paper:
                ref = self._format_enhanced_reference(paper, language)
                references.append(ref)
            else:
                if language == 'english':
                    references.append(f"PMID: {pmid} (Reference information unavailable)")
                else:
                    references.append(f"PMID: {pmid} (参考文献信息不可用)")

        return references

    def _format_enhanced_reference(self, paper: Dict[str, Any], language: str) -> str:
        """
        格式化增强的参考文献

        Args:
            paper: 文献信息
            language: 语言

        Returns:
            格式化的参考文献
        """
        try:
            title = paper.get('title', 'No title')
            authors = paper.get('authors', 'Unknown authors')
            journal = paper.get('journal', 'Unknown journal')
            year = paper.get('pub_year', 'Unknown year')
            pmid = paper.get('pmid', 'N/A')
            doi = paper.get('doi', '')

            # 处理作者列表
            if isinstance(authors, list):
                if len(authors) > 3:
                    authors_str = f"{authors[0]} et al."
                else:
                    authors_str = ', '.join(authors)
            else:
                authors_str = str(authors)

            # 构建基本引用
            reference = f"{authors_str} ({year}). {title}. {journal}."

            # 添加DOI（如果有）
            if doi:
                reference += f" DOI: {doi}."

            # 添加PMID
            reference += f" PMID: {pmid}."

            return reference

        except Exception as e:
            logger.error(f"格式化增强参考文献失败: {e}")
            return f"PMID: {paper.get('pmid', 'N/A')} - 格式化失败"

    def _calculate_review_statistics(self, content: str, references: List[str],
                                   sections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        计算综述统计信息

        Args:
            content: 综述内容
            references: 参考文献列表
            sections: 章节列表

        Returns:
            统计信息字典
        """
        try:
            import re

            # 计算字数（去除HTML标签）
            text_content = re.sub(r'<[^>]+>', '', content)
            word_count = len(text_content)

            # 计算引用数量
            citation_matches = re.findall(r'\[\d+\]', content)
            citation_count = len(set(citation_matches))

            # 计算章节数量
            section_count = len(sections)

            # 计算图表数量（如果有）
            figure_count = len(re.findall(r'<img|<figure', content, re.IGNORECASE))
            table_count = len(re.findall(r'<table', content, re.IGNORECASE))

            return {
                'word_count': word_count,
                'reference_count': len(references),
                'citation_count': citation_count,
                'section_count': section_count,
                'figure_count': figure_count,
                'table_count': table_count,
                'generated_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"计算综述统计信息失败: {e}")
            return {
                'word_count': 0,
                'reference_count': len(references),
                'citation_count': 0,
                'section_count': len(sections),
                'figure_count': 0,
                'table_count': 0,
                'generated_at': datetime.now().isoformat()
            }

    def _apply_academic_formatting(self, content: str, language: str) -> str:
        """
        应用学术格式化

        Args:
            content: 原始内容
            language: 语言

        Returns:
            格式化后的内容
        """
        try:
            # 添加CSS样式
            formatted_content = f"""
<style>
body {{
    font-family: 'Times New Roman', serif;
    line-height: 1.6;
    margin: 40px;
    color: #333;
}}
h1 {{
    text-align: center;
    color: #2c3e50;
    border-bottom: 3px solid #3498db;
    padding-bottom: 10px;
}}
h2 {{
    color: #34495e;
    margin-top: 30px;
    border-left: 4px solid #3498db;
    padding-left: 15px;
}}
h3 {{
    color: #7f8c8d;
    margin-top: 20px;
}}
p {{
    text-align: justify;
    margin: 15px 0;
}}
ol, ul {{
    margin: 15px 0;
    padding-left: 30px;
}}
hr {{
    border: none;
    border-top: 1px solid #bdc3c7;
    margin: 30px 0;
}}
.abstract {{
    background: #f8f9fa;
    padding: 20px;
    border-left: 4px solid #3498db;
    margin: 20px 0;
}}
</style>

{content}
"""

            return formatted_content

        except Exception as e:
            logger.error(f"应用学术格式化失败: {e}")
            return content


# 全局服务实例
from services.deepseek_service import DeepSeekService
advanced_review_service = AdvancedReviewService(DeepSeekService())
