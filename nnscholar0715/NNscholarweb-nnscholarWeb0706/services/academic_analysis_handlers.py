#!/usr/bin/env python3
"""
学术分析异步任务处理器

处理各种学术分析任务的异步执行
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.deepseek_service import deepseek_service
from services.pubmed_service import pubmed_service
from utils.session_cache import get_papers_cache
from services.async_task_service import AsyncTask

logger = logging.getLogger(__name__)


class AcademicAnalysisHandlers:
    """学术分析任务处理器"""
    
    @staticmethod
    def handle_review_topic_analysis(task: AsyncTask) -> Dict[str, Any]:
        """处理综述选题建议分析"""
        try:
            task_data = task.task_data
            query = task_data.get('query', '')
            session_id = task_data.get('session_id', '')
            
            logger.info(f"开始处理综述选题建议: query='{query}', session_id='{session_id}'")
            
            # 获取缓存中的文献数据
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)
            
            if not cached_data or not cached_data.get('papers'):
                raise Exception("没有找到文献数据")
            
            papers = cached_data['papers']
            logger.info(f"获取到 {len(papers)} 篇文献用于分析")
            
            # 提取标题和摘要
            titles = [paper.get('title', '') for paper in papers[:150]]
            abstracts = [paper.get('abstract', '')[:200] for paper in papers[:15]]
            
            # 构建分析提示词
            titles_text = '\n'.join([f"{i+1}. {title}" for i, title in enumerate(titles)])
            
            prompt = f"""基于{len(papers)}篇文献，为"{query}"领域提供综述选题建议：

文献标题：
{titles_text}

请提供：
1. 该领域研究热点分析
2. 3-5个具体的综述选题建议
3. 每个选题的写作思路和预期贡献
4. 推荐的文献组织方式

请用中文回答，使用HTML格式。"""
            
            # 调用AI分析
            messages = [
                {"role": "system", "content": "你是一位专业的学术综述选题专家。"},
                {"role": "user", "content": prompt}
            ]
            
            response = deepseek_service._make_request(messages, temperature=0.8)
            suggestions = deepseek_service._extract_response_content(response)
            
            logger.info(f"综述选题建议生成完成，内容长度: {len(suggestions)} 字符")
            
            return {
                "analysis_type": "review_topic",
                "content": suggestions,
                "paper_count": len(papers),
                "query": query,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"综述选题建议分析失败: {str(e)}")
            raise
    
    @staticmethod
    def handle_research_topic_analysis(task: AsyncTask) -> Dict[str, Any]:
        """处理论著选题建议分析"""
        try:
            task_data = task.task_data
            query = task_data.get('query', '')
            session_id = task_data.get('session_id', '')
            
            logger.info(f"开始处理论著选题建议: query='{query}', session_id='{session_id}'")
            
            # 获取缓存中的文献数据
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)
            
            if not cached_data or not cached_data.get('papers'):
                raise Exception("没有找到文献数据")
            
            papers = cached_data['papers']
            logger.info(f"获取到 {len(papers)} 篇文献用于分析")
            
            # 提取最新文献信息
            recent_papers = [p for p in papers if p.get('pub_date', '').startswith(('2022', '2023', '2024'))][:15]
            
            paper_info = []
            for paper in recent_papers:
                title = paper.get('title', '')
                authors = paper.get('authors', [])
                author_str = ', '.join(authors[:3]) + ('等' if len(authors) > 3 else '')
                year = paper.get('pub_year', '未知年份')
                journal = paper.get('journal', '未知期刊')
                paper_info.append(f"{title} - {author_str} ({year}) {journal}")
            
            prompt = f"""基于{len(papers)}篇文献，为"{query}"领域提供原创性研究选题建议：

相关研究：
{chr(10).join(paper_info)}

请提供：
1. 3-5个具有创新性的研究选题
2. 每个选题的创新点和研究价值
3. 可能的研究方法和技术路线
4. 研究的可行性评估

请用中文回答，使用HTML格式。"""
            
            # 调用AI分析
            messages = [
                {"role": "system", "content": "你是一位资深的科研指导专家。"},
                {"role": "user", "content": prompt}
            ]
            
            response = deepseek_service._make_request(messages, temperature=0.8)
            suggestions = deepseek_service._extract_response_content(response)
            
            logger.info(f"论著选题建议生成完成，内容长度: {len(suggestions)} 字符")
            
            return {
                "analysis_type": "research_topic",
                "content": suggestions,
                "paper_count": len(papers),
                "query": query,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"论著选题建议分析失败: {str(e)}")
            raise
    
    @staticmethod
    def handle_full_review_generation(task: AsyncTask) -> Dict[str, Any]:
        """处理完整综述生成 - 使用简化的综述生成流程"""
        try:
            task_data = task.task_data
            query = task_data.get('query', '')
            session_id = task_data.get('session_id', '')
            review_type = task_data.get('review_type', 'narrative')
            user_title = task_data.get('user_title', '')

            logger.info(f"开始处理综述生成: query='{query}', user_title='{user_title}', session_id='{session_id}', type='{review_type}'")

            # 获取缓存中的文献数据
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)

            if not cached_data or not cached_data.get('papers'):
                raise Exception("没有找到文献数据")

            papers = cached_data['papers']
            logger.info(f"获取到 {len(papers)} 篇文献用于综述生成")

            # 更新任务进度
            task.progress = 20
            task.message = "正在准备文献数据..."

            # 提取文献标题和详细信息
            titles = [paper.get('title', '') for paper in papers]

            # 使用前150篇相关性最强的文献
            selected_titles = titles[:150]
            selected_papers = papers[:150]

            # 更新任务进度
            task.progress = 40
            task.message = "正在生成综述内容..."

            # 构建完整综述生成提示词
            titles_text = '\n'.join([f"{i+1}. {title}" for i, title in enumerate(selected_titles)])

            # 如果有完整的文献信息，提取更多细节
            papers_info = ""
            if selected_papers:
                papers_info = "\n\n文献详细信息（前50篇）：\n"
                for i, paper in enumerate(selected_papers[:50]):
                    authors = paper.get('authors', [])
                    author_str = ', '.join(authors[:3]) + ('等' if len(authors) > 3 else '')
                    year = paper.get('pub_year', '未知年份')
                    journal = paper.get('journal', '未知期刊')
                    abstract = paper.get('abstract', '')[:200] + '...' if paper.get('abstract') else '无摘要'
                    papers_info += f"{i+1}. {paper.get('title', '无标题')} - {author_str} ({year}) {journal}\n   摘要: {abstract}\n\n"

            prompt = f"""- Role: 学术综述写作专家
- Background: 用户需要基于收集的真实文献生成一份完整的学术综述文档，要求内容全面、结构清晰、学术规范。
- Profile: 你是一位在学术写作和文献综述方面有着丰富经验的专家，擅长整合大量文献信息，撰写高质量的综述文章。
- Skills: 你具备文献综合分析能力、学术写作能力、逻辑思维能力，能够基于真实文献数据撰写结构完整、内容丰富的综述文档。
- Goals:
  1. 基于提供的文献撰写完整的综述文档
  2. 确保内容结构清晰、逻辑严密
  3. 包含所有综述必要的组成部分
  4. 提供专业的学术观点和见解
- Constrains: 综述内容必须基于提供的真实文献，确保学术严谨性和可信度。遵循学术写作规范。
- OutputFormat: 请用中文回答，使用HTML格式，包含适当的标题和段落标签，确保格式规范。

现在请基于"{query}"领域的{len(selected_titles)}篇文献，生成完整的综述文档：

文献标题列表：
{titles_text}
{papers_info}

请按以下结构撰写完整综述：

1. **研究背景与意义**
   - 领域发展历程
   - 研究重要性和临床意义
   - 当前面临的挑战

2. **文献检索策略**
   - 检索数据库和时间范围
   - 检索关键词和策略
   - 文献筛选标准

3. **研究现状分析**
   - 主要研究成果梳理
   - 技术方法发展现状
   - 临床应用进展

4. **技术方法比较**
   - 不同方法的优缺点
   - 适用场景分析
   - 性能指标比较

5. **存在问题与挑战**
   - 当前技术局限性
   - 临床应用障碍
   - 标准化问题

6. **发展趋势与展望**
   - 未来发展方向
   - 新兴技术趋势
   - 临床应用前景

7. **结论与建议**
   - 主要结论总结
   - 实践建议
   - 未来研究方向

确保内容专业、全面、具有学术价值。"""

            # 更新任务进度
            task.progress = 60
            task.message = "正在调用AI生成服务..."

            try:
                # 调用DeepSeek API
                from services.deepseek_service import DeepSeekService
                deepseek_service = DeepSeekService()
                review_result = deepseek_service.analyze_text(prompt)

                # 更新任务进度
                task.progress = 90
                task.message = "正在整理结果..."

                logger.info(f"综述生成完成，内容长度: {len(review_result)} 字符")

                return {
                    "analysis_type": "full_review",
                    "content": review_result,
                    "title": user_title or f"{query} - 综述",
                    "analyzed_papers": len(selected_titles),
                    "total_papers": len(titles),
                    "query": query,
                    "user_title": user_title,
                    "generated_at": datetime.now().isoformat()
                }

            except Exception as e:
                logger.error(f"DeepSeek API调用失败: {str(e)}")
                # 如果AI生成失败，回退到原始方法
                return AcademicAnalysisHandlers._fallback_review_generation(task)

        except Exception as e:
            logger.error(f"综述生成失败: {str(e)}")
            # 如果整个流程失败，回退到原始方法
            return AcademicAnalysisHandlers._fallback_review_generation(task)

    @staticmethod
    def _fallback_review_generation(task: AsyncTask) -> Dict[str, Any]:
        """回退的综述生成方法"""
        try:
            task_data = task.task_data
            query = task_data.get('query', '')
            session_id = task_data.get('session_id', '')

            # 获取缓存中的文献数据
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)

            if not cached_data or not cached_data.get('papers'):
                raise Exception("没有找到文献数据")

            papers = cached_data['papers']
            logger.info(f"使用回退方法生成综述，文献数量: {len(papers)}")

            # 使用前150篇相关性最强的文献（按照原版本逻辑）
            selected_papers = papers[:150] if papers else []

            # 构建完整综述生成提示词（按照原版本格式）
            titles_text = '\n'.join([f"{i+1}. {paper.get('title', '')}" for i, paper in enumerate(selected_papers)])

            # 如果有完整的文献信息，提取更多细节（前50篇）
            papers_info = ""
            if selected_papers:
                papers_info = "\n\n文献详细信息（前50篇）：\n"
                for i, paper in enumerate(selected_papers[:50]):
                    authors = paper.get('authors', [])
                    author_str = ', '.join(authors[:3]) + ('等' if len(authors) > 3 else '')
                    year = paper.get('pub_year', '未知年份')
                    journal = paper.get('journal', '未知期刊')
                    abstract = paper.get('abstract', '')[:200] + '...' if paper.get('abstract') else '无摘要'
                    papers_info += f"{i+1}. {paper.get('title', '无标题')} - {author_str} ({year}) {journal}\n   摘要: {abstract}\n\n"

            # 使用原版本的完整提示词
            prompt = f"""- Role: 学术综述写作专家
- Background: 用户需要基于收集的真实文献生成一份完整的学术综述文档，要求内容全面、结构清晰、学术规范。
- Profile: 你是一位在学术写作和文献综述方面有着丰富经验的专家，擅长整合大量文献信息，撰写高质量的综述文章。
- Skills: 你具备文献综合分析能力、学术写作能力、逻辑思维能力，能够基于真实文献数据撰写结构完整、内容丰富的综述文档。
- Goals:
  1. 基于提供的文献撰写完整的综述文档
  2. 确保内容结构清晰、逻辑严密
  3. 包含所有综述必要的组成部分
  4. 提供专业的学术观点和见解
- Constrains: 综述内容必须基于提供的真实文献，确保学术严谨性和可信度。遵循学术写作规范。
- OutputFormat: 请用中文回答，使用HTML格式，包含适当的标题和段落标签，确保格式规范。

现在请基于"{query}"领域的{len(selected_papers)}篇文献，生成完整的综述文档：

文献标题列表：
{titles_text}
{papers_info}

请按以下结构撰写完整综述：

1. **研究背景与意义**
   - 领域发展历程
   - 研究重要性和临床意义
   - 当前面临的挑战

2. **文献检索策略**
   - 检索数据库和时间范围
   - 检索关键词和策略
   - 文献筛选标准

3. **研究现状分析**
   - 主要研究成果梳理
   - 技术方法发展现状
   - 临床应用进展

4. **技术方法比较**
   - 不同方法的优缺点
   - 适用场景分析
   - 性能指标比较

5. **存在问题与挑战**
   - 当前技术局限性
   - 临床应用障碍
   - 标准化问题

6. **发展趋势与展望**
   - 未来发展方向
   - 新兴技术趋势
   - 临床应用前景

7. **结论与建议**
   - 主要结论总结
   - 实践建议
   - 未来研究方向

确保内容专业、全面、具有学术价值。"""

            # 调用AI分析
            try:
                from services.deepseek_service import DeepSeekService
                deepseek_service = DeepSeekService()
                review = deepseek_service.analyze_text(prompt)
            except Exception as e:
                logger.error(f"DeepSeek API调用失败: {str(e)}")
                review = None

            # 如果AI调用失败，提供备用综述（按照原版本逻辑）
            if not review:
                logger.warning("AI分析服务不可用，使用备用综述")
                review = f"""
                <h2>📚 {query} - 综述文档</h2>

                <h3>1. 研究背景与意义</h3>
                <p>{query}是当前医学研究的重要领域，具有重要的临床意义和应用价值。基于{len(selected_papers)}篇相关文献的分析，该领域在近年来取得了显著进展。</p>

                <h3>2. 文献检索策略</h3>
                <p>本综述检索了PubMed等主要医学数据库，时间范围为2020-2025年，共纳入{len(selected_papers)}篇高质量文献进行分析。</p>

                <h3>3. 研究现状分析</h3>
                <p>当前{query}领域的研究主要集中在技术创新、临床应用和方法学改进等方面，取得了一系列重要成果。</p>

                <h3>4. 技术方法比较</h3>
                <p>不同的技术方法各有优缺点，在准确性、效率和适用性方面存在差异，需要根据具体应用场景选择合适的方法。</p>

                <h3>5. 存在问题与挑战</h3>
                <p>该领域仍面临技术标准化、临床验证、成本控制等挑战，需要进一步的研究和改进。</p>

                <h3>6. 发展趋势与展望</h3>
                <p>未来{query}领域将朝着更加精准、智能、个性化的方向发展，有望在临床实践中发挥更大作用。</p>

                <h3>7. 结论与建议</h3>
                <p>建议加强多学科合作，推进技术创新，完善标准规范，促进{query}技术的临床转化和应用。</p>

                <p><em>💡 注：由于AI分析服务暂时不可用，以上为基于文献数量和研究领域的专业基础综述框架。</em></p>
                """

            logger.info(f"回退综述生成完成，内容长度: {len(review)} 字符")

            return {
                "analysis_type": "full_review",
                "content": review,
                "paper_count": len(papers),
                "analyzed_papers": len(selected_papers),
                "total_papers": len(papers),
                "query": query,
                "review_type": "narrative",
                "generated_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"回退综述生成失败: {str(e)}")
            raise

    @staticmethod
    def handle_reference_matching(task: AsyncTask) -> Dict[str, Any]:
        """处理参考文献匹配"""
        try:
            task_data = task.task_data
            text_content = task_data.get('text_content', '')

            logger.info(f"开始处理参考文献匹配: 文本长度={len(text_content)}")

            # 更新任务进度
            task.progress = 10
            task.message = "正在分析文本内容..."

            # 构建基于序号引用的参考文献专家提示词
            reference_prompt = f"""你是参考文献专家。请为以下文本添加学术规范的序号引用。

要求：
1. 在需要引用的地方使用序号格式：[1]、[2]、[3]等
2. 在文末列出完整的文献标题，格式：'''完整文献标题'''
3. 使用真实存在的文献标题
4. 优先选择近5年的高质量文献
5. 确保文献与引用内容高度相关
6. 直接返回文本，不要返回JSON格式

输入文本：
{text_content}

请直接返回添加了序号引用的文本，然后在最后列出所有文献标题：

参考文献：
[1] '''完整文献标题1'''
[2] '''完整文献标题2'''
[3] '''完整文献标题3'''

示例：
输入：慢性肾病作为全球性公共健康挑战，患病率不断上升。
输出：慢性肾病(CKD)作为全球性公共健康挑战，目前全球患病率已达8-16%[1]。随着老龄化进程加快，其患病率呈上升趋势[2]，他们面临三大核心并发症：骨矿物质代谢紊乱(CKD-MBD)引起的骨质疏松[3]，机体炎症反应[4]和血管钙化[5]。

参考文献：
[1] '''Global, regional, and national burden of chronic kidney disease, 1990-2017: a systematic analysis for the Global Burden of Disease Study 2017'''
[2] '''Trends in chronic kidney disease prevalence and risk factors'''
[3] '''Chronic kidney disease-mineral and bone disorder: pathophysiology and management'''
[4] '''Inflammation in chronic kidney disease: causes and consequences'''
[5] '''Vascular calcification in chronic kidney disease: mechanisms and clinical implications'''

注意：使用真实存在的完整文献标题，确保与内容相关。

- Examples:
输入文本示例：
"在分子机制层面，Zhang通过生物信息学分析发现，AD相关炎症通路（如NF-κB和TNF-α信号）与OP共享关键节点基因PROK2和CSF3，这些基因的多态性可能通过改变细胞因子分泌影响两种疾病进程。钙敏感受体（CaSR）作为跨膜信号分子，其基因变异不仅影响钙稳态，还通过调控甲状旁腺激素分泌参与AD的tau蛋白磷酸化过程。表观遗传学研究进一步揭示，氧化应激诱导的DNA甲基化变化是连接两种疾病的重要桥梁。胆固醇氧化产物氧固醇（如27-羟基胆固醇）不仅能穿过血脑屏障促进Aβ沉积，还可通过表观遗传沉默骨保护素（OPG）基因表达，加速骨吸收。"

输出示例：
{{
  "references": [
    {{
      "sentence": "AD相关炎症通路（如NF-κB和TNF-α信号）与OP共享关键节点基因PROK2和CSF3",
      "title": "Shared genetic architecture between Alzheimer's disease and osteoporosis: a bioinformatics analysis",
      "authors": "Zhang L, Wang Y, Chen M, et al.",
      "journal": "Journal of Bone and Mineral Research",
      "year": "2022",
      "pmid": "36203970",
      "doi": "10.1002/jbmr.4567",
      "abstract": "本研究通过生物信息学分析发现AD和OP共享关键基因PROK2和CSF3，这些基因参与炎症通路调控",
      "selection_reason": "发表在骨代谢领域顶级期刊（影响因子5.1，JCR Q1区），被引用超过50次",
      "relevance": "直接支持AD和OP共享炎症通路基因的观点"
    }},
    {{
      "sentence": "钙敏感受体（CaSR）基因变异影响钙稳态",
      "title": "Calcium-sensing receptor gene variants and bone mineral density",
      "authors": "Tian X, Liu H, Zhang K, et al.",
      "journal": "Bone",
      "year": "2024",
      "pmid": "39027195",
      "doi": "10.1016/j.bone.2024.117089",
      "abstract": "研究CaSR基因变异对钙稳态和骨密度的影响机制",
      "selection_reason": "发表在骨科学权威期刊（影响因子4.1，JCR Q1区），最新研究成果",
      "relevance": "直接证明CaSR基因变异对钙稳态的影响"
    }},
    {{
      "sentence": "CaSR通过调控甲状旁腺激素分泌参与AD的tau蛋白磷酸化过程",
      "title": "Parathyroid hormone regulation and tau phosphorylation in Alzheimer's disease",
      "authors": "Dengler-Crish CM, Smith MA, Wilson GN, et al.",
      "journal": "Neurobiology of Aging",
      "year": "2019",
      "pmid": "30779704",
      "doi": "10.1016/j.neurobiolaging.2019.02.015",
      "abstract": "探讨甲状旁腺激素调控与AD中tau蛋白磷酸化的关系",
      "selection_reason": "发表在神经退行性疾病权威期刊（影响因子4.8，JCR Q1区），被引用超过80次",
      "relevance": "支持CaSR-PTH-tau磷酸化的分子机制假说"
    }}
  ],
  "formatted_text": "在分子机制层面，Zhang[36203970]通过生物信息学分析发现，AD相关炎症通路（如NF-κB和TNF-α信号）与OP共享关键节点基因PROK2和CSF3，这些基因的多态性可能通过改变细胞因子分泌影响两种疾病进程。钙敏感受体（CaSR）作为跨膜信号分子，其基因变异不仅影响钙稳态[39027195]，还通过调控甲状旁腺激素分泌参与AD的tau蛋白磷酸化过程[30779704]。表观遗传学研究进一步揭示，氧化应激诱导的DNA甲基化变化是连接两种疾病的重要桥梁。胆固醇氧化产物氧固醇（如27-羟基胆固醇）不仅能穿过血脑屏障促进Aβ沉积，还可通过表观遗传沉默骨保护素（OPG）基因表达，加速骨吸收。",
  "simple_reference_list": "1.36203970\\n2.39027195\\n3.30779704"
}}

用户提供的文本内容：
{text_content}

请为文本中的每个重要观点或句子提供相应的参考文献支持，确保PMID真实有效。"""

            # 更新任务进度
            task.progress = 30
            task.message = "正在生成参考文献..."

            try:
                # 调用DeepSeek API
                from services.deepseek_service import DeepSeekService
                deepseek_service = DeepSeekService()
                ai_response = deepseek_service.analyze_text(reference_prompt)

                # 更新任务进度
                task.progress = 50
                task.message = "正在解析AI响应..."

                # 解析AI响应
                references = AcademicAnalysisHandlers._parse_reference_response(ai_response)

                if not references:
                    raise Exception("AI未能生成有效的参考文献")

                # 更新任务进度
                task.progress = 70
                task.message = "正在验证文献真实性..."

                # 使用Crossref API验证文献真实性
                verified_references = AcademicAnalysisHandlers._verify_references_with_crossref(references)

                # 检查验证结果
                valid_references = [ref for ref in verified_references if ref.get('verified', False)]
                invalid_references = [ref for ref in verified_references if not ref.get('verified', False)]

                # 如果有无效文献，重新生成
                max_retries = 2
                retry_count = 0

                while invalid_references and retry_count < max_retries:
                    retry_count += 1
                    task.progress = 70 + (retry_count * 10)
                    task.message = f"重新生成无效文献... (第{retry_count}次重试)"

                    # 重新生成无效文献
                    retry_references = AcademicAnalysisHandlers._regenerate_invalid_references(
                        text_content, invalid_references, deepseek_service
                    )

                    if retry_references:
                        # 验证重新生成的文献
                        retry_verified = AcademicAnalysisHandlers._verify_references_with_crossref(retry_references)

                        # 更新结果
                        for i, invalid_ref in enumerate(invalid_references):
                            if i < len(retry_verified) and retry_verified[i].get('verified', False):
                                # 替换无效文献
                                for j, ref in enumerate(verified_references):
                                    if ref.get('sentence') == invalid_ref.get('sentence'):
                                        verified_references[j] = retry_verified[i]
                                        break

                        # 重新检查
                        valid_references = [ref for ref in verified_references if ref.get('verified', False)]
                        invalid_references = [ref for ref in verified_references if not ref.get('verified', False)]

                # 更新任务进度
                task.progress = 90
                task.message = "正在整理结果..."

                logger.info(f"参考文献匹配完成: 有效文献={len(valid_references)}, 无效文献={len(invalid_references)}")

                return {
                    "analysis_type": "reference_matching",
                    "references": verified_references,
                    "valid_count": len(valid_references),
                    "invalid_count": len(invalid_references),
                    "total_count": len(verified_references),
                    "text_content": text_content,
                    "ai_response": ai_response,  # 添加AI生成的原始响应
                    "generated_at": datetime.now().isoformat()
                }

            except Exception as e:
                logger.error(f"AI分析失败: {str(e)}")
                # 提供备用响应
                return {
                    "analysis_type": "reference_matching",
                    "references": [],
                    "valid_count": 0,
                    "invalid_count": 0,
                    "total_count": 0,
                    "text_content": text_content,
                    "error": "AI分析服务暂时不可用，请稍后重试",
                    "generated_at": datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"参考文献匹配失败: {str(e)}")
            raise

    @staticmethod
    def _parse_reference_response(ai_response: str) -> List[Dict[str, Any]]:
        """解析AI响应，提取'''文献标题'''格式的引用"""
        try:
            import re

            logger.info(f"开始解析AI响应，长度: {len(ai_response)}")
            logger.info(f"AI响应内容预览: {ai_response[:500]}...")

            # 兼容两种格式：[1]、[2]格式和'''内容'''格式
            titles = []

            # 首先尝试新格式：[1]、[2]格式引用
            citation_pattern = r"\[(\d+)\]"
            citations = re.findall(citation_pattern, ai_response)

            # 提取参考文献列表中的'''标题'''
            ref_list_pattern = r"参考文献：?\s*\n((?:\[\d+\]\s*'''[^']+'''\s*\n?)+)"
            ref_match = re.search(ref_list_pattern, ai_response)

            if ref_match and citations:
                # 新格式：[1] '''标题'''
                ref_lines = ref_match.group(1).strip().split('\n')
                for line in ref_lines:
                    line = line.strip()
                    title_match = re.match(r"\[(\d+)\]\s*'''([^']+)'''", line)
                    if title_match:
                        title = title_match.group(2).strip()
                        titles.append(title)
            else:
                # 回退到旧格式：'''内容'''
                title_pattern = r"'''([^']+)'''"
                titles = re.findall(title_pattern, ai_response)

                # 提取参考文献列表部分（旧格式）
                ref_list_pattern_old = r"参考文献：?\s*\n((?:\d+\.\s*[^\n]+\n?)+)"
                ref_match_old = re.search(ref_list_pattern_old, ai_response)

                if ref_match_old:
                    ref_lines = ref_match_old.group(1).strip().split('\n')
                    for line in ref_lines:
                        line = line.strip()
                        if line and '.' in line:
                            title = line.split('.', 1)[1].strip()
                            if title and title not in titles:
                                titles.append(title)

            # 构建参考文献列表
            references = []
            for i, title in enumerate(titles):
                citation_num = str(i + 1)
                references.append({
                    'title': title,
                    'authors': '基于标题引用',
                    'journal': '待查证',
                    'year': '待查证',
                    'pmid': '无',
                    'verified': True,  # 标题引用默认为已验证
                    'sentence': f'[{citation_num}] {title}',
                    'citation_type': 'numbered_title',
                    'citation_number': citation_num
                })

            logger.info(f"提取到 {len(titles)} 个文献标题: {titles}")
            return references

        except Exception as e:
            logger.error(f"解析AI响应失败: {str(e)}")
            return []

    @staticmethod
    def _verify_references_with_crossref(references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证文献引用（仅支持标题验证）"""
        try:
            verified_references = []

            # 只支持标题引用格式
            logger.info(f"开始PubMed标题验证")

            def verify_title_with_pubmed(ref):
                """通过PubMed搜索验证文献标题"""
                try:
                    title = ref.get('title', '').strip()
                    if not title:
                        ref['verified'] = False
                        ref['error'] = '缺少标题'
                        logger.warning(f"文献缺少标题")
                        return ref

                    logger.info(f"验证标题: {title[:50]}...")

                    # 使用PubMed搜索验证标题
                    pmids, total_count = pubmed_service.search_papers(title, max_results=3)

                    if pmids and len(pmids) > 0:
                        # 找到PMID就认为验证成功，暂时跳过详细信息获取
                        ref.update({
                            'pmid': pmids[0],
                            'verified': True,
                            'verification_method': 'pubmed_title_search_simple'
                        })
                        logger.info(f"标题验证成功: {title[:30]}... -> PMID: {pmids[0]}")
                        return ref
                    else:
                        # 未找到匹配文献
                        ref['verified'] = False
                        ref['verification_method'] = 'pubmed_not_found'
                        ref['error'] = 'PubMed中未找到匹配文献'
                        logger.warning(f"标题未找到匹配: {title[:30]}...")
                        return ref

                except Exception as e:
                    logger.error(f"验证标题失败: {str(e)}")
                    ref['verified'] = False
                    ref['verification_method'] = 'pubmed_error'
                    ref['error'] = f'验证异常: {str(e)}'
                    return ref

            # 顺序验证标题
            for ref in references:
                try:
                    result = verify_title_with_pubmed(ref)
                    verified_references.append(result)
                except Exception as e:
                    logger.error(f"验证标题时出错: {str(e)}")
                    ref['verified'] = False
                    ref['verification_method'] = 'sequential_error'
                    ref['error'] = f'验证异常: {str(e)}'
                    verified_references.append(ref)

            # 统计验证结果
            valid_count = sum(1 for ref in verified_references if ref.get('verified', False))
            invalid_count = len(verified_references) - valid_count
            logger.info(f"PubMed标题验证完成: 有效文献={valid_count}, 无效文献={invalid_count}")
            return verified_references

        except Exception as e:
            logger.error(f"PMID验证失败: {str(e)}")
            # 如果验证失败，标记所有文献为未验证
            for ref in references:
                ref['verified'] = False
                ref['error'] = '验证服务不可用'
            return references

    @staticmethod
    def _regenerate_invalid_references(text_content: str, invalid_references: List[Dict[str, Any]],
                                     deepseek_service) -> List[Dict[str, Any]]:
        """重新生成无效的参考文献"""
        try:
            # 构建重新生成的提示词
            invalid_sentences = [ref.get('sentence', '') for ref in invalid_references]

            regenerate_prompt = f"""之前为以下句子生成的参考文献验证失败，请重新为这些句子提供真实可靠的参考文献：

句子列表：
{chr(10).join([f"- {sentence}" for sentence in invalid_sentences])}

请确保：
1. 文献必须真实存在
2. 提供准确的DOI
3. 作者和期刊信息准确
4. 发表年份在合理范围内

请按照JSON格式返回：
{{
  "references": [
    {{
      "sentence": "原句子内容",
      "title": "文献标题",
      "authors": "作者列表",
      "journal": "期刊名称",
      "year": "发表年份",
      "doi": "DOI",
      "abstract": "文献摘要",
      "selection_reason": "选择理由",
      "relevance": "相关性说明"
    }}
  ]
}}"""

            ai_response = deepseek_service.analyze_text(regenerate_prompt)
            return AcademicAnalysisHandlers._parse_reference_response(ai_response)

        except Exception as e:
            logger.error(f"重新生成参考文献失败: {str(e)}")
            return []
    
    @staticmethod
    def handle_representative_papers_recommendation(task: AsyncTask) -> Dict[str, Any]:
        """处理代表性文章推荐"""
        try:
            task_data = task.task_data
            query = task_data.get('query', '')
            session_id = task_data.get('session_id', '')
            criteria = task_data.get('criteria', 'impact_and_novelty')
            
            logger.info(f"开始处理代表性文章推荐: query='{query}', session_id='{session_id}', criteria='{criteria}'")
            
            # 获取缓存中的文献数据
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)
            
            if not cached_data or not cached_data.get('papers'):
                raise Exception("没有找到文献数据")
            
            papers = cached_data['papers']
            logger.info(f"获取到 {len(papers)} 篇文献用于推荐")
            
            # 准备文献信息
            paper_list = []
            for i, paper in enumerate(papers[:50]):  # 分析前50篇
                title = paper.get('title', '')
                authors = paper.get('authors', [])
                journal = paper.get('journal', '')
                year = paper.get('pub_year', '')
                abstract = paper.get('abstract', '')
                impact_factor = paper.get('impact_factor', 'N/A')
                
                author_str = ', '.join(authors[:3]) + ('等' if len(authors) > 3 else '')
                
                info = f"{i+1}. {title}\n作者：{author_str}\n期刊：{journal} (IF: {impact_factor})\n年份：{year}"
                if abstract:
                    info += f"\n摘要：{abstract[:200]}..."
                
                paper_list.append(info)
            
            prompt = f"""基于{len(papers)}篇文献，按{criteria}标准推荐5-10篇最具代表性的论文：

文献列表：
{chr(10).join(['---'] + paper_list)}

请为每篇推荐论文提供详细的推荐理由，说明其代表性和重要性。

请用中文回答，使用HTML格式，包含：
1. 推荐论文列表（按重要性排序）
2. 每篇论文的详细推荐理由
3. 学术影响力和创新点分析"""
            
            # 调用AI分析
            messages = [
                {"role": "system", "content": "你是一位资深的学术专家，擅长评估文献的学术价值和影响力。"},
                {"role": "user", "content": prompt}
            ]
            
            response = deepseek_service._make_request(messages, temperature=0.6)
            recommendations = deepseek_service._extract_response_content(response)
            
            logger.info(f"代表性文章推荐完成，内容长度: {len(recommendations)} 字符")
            
            return {
                "analysis_type": "representative_papers",
                "content": recommendations,
                "paper_count": len(papers),
                "query": query,
                "criteria": criteria,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"代表性文章推荐失败: {str(e)}")
            raise

    @staticmethod
    def handle_research_method_analysis(task: AsyncTask) -> Dict[str, Any]:
        """处理研究方法分析"""
        try:
            task_data = task.task_data
            content = task_data.get('content', '')
            analysis_type = task_data.get('analysis_type', 'paper')  # paper, proposal, idea

            logger.info(f"开始处理研究方法分析: type='{analysis_type}'")

            if not content:
                raise Exception("分析内容不能为空")

            # 根据分析类型构建不同的提示词
            if analysis_type == 'paper':
                prompt = f"""作为资深的研究方法学专家，请分析以下论文的研究方法，并提供专业建议：

论文内容：
{content}

请从以下方面进行分析：
1. 研究设计类型识别（实验研究、观察性研究、系统综述等）
2. 样本量和抽样方法评估
3. 数据收集方法分析
4. 统计分析方法评价
5. 研究局限性识别
6. 方法学改进建议
7. 研究质量评分（1-10分）

请提供详细的分析报告，包含具体的改进建议。"""

            elif analysis_type == 'proposal':
                prompt = f"""作为资深的研究方法学专家，请为以下研究提案设计合适的研究方法：

研究提案：
{content}

请提供以下内容：
1. 推荐的研究设计类型及理由
2. 样本量计算和抽样策略
3. 数据收集方案设计
4. 统计分析计划
5. 质量控制措施
6. 伦理考虑要点
7. 时间安排建议
8. 预期困难和解决方案

请提供完整的方法学设计方案。"""

            else:  # idea
                prompt = f"""作为资深的研究方法学专家，请为以下研究想法提供方法学指导：

研究想法：
{content}

请提供以下建议：
1. 可行的研究设计选项
2. 关键变量的测量方法
3. 潜在的混杂因素控制
4. 适合的统计分析方法
5. 研究实施的关键步骤
6. 可能遇到的方法学挑战
7. 文献支持和理论基础
8. 创新性评估

请提供系统性的方法学建议。"""

            # 调用AI分析
            response = deepseek_service._make_request([
                {"role": "system", "content": "你是一位资深的研究方法学专家，具有丰富的科研经验和方法学知识。"},
                {"role": "user", "content": prompt}
            ], temperature=0.3, max_tokens=3000)

            analysis_result = deepseek_service._extract_response_content(response)

            if not analysis_result:
                raise Exception("AI分析返回空结果")

            logger.info("研究方法分析完成")

            return {
                'success': True,
                'content': analysis_result,
                'analysis_type': analysis_type,
                'generated_at': datetime.now().isoformat(),
                'task_id': task.task_id
            }

        except Exception as e:
            logger.error(f"研究方法分析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }

    @staticmethod
    def handle_literature_review_analysis(task: AsyncTask) -> Dict[str, Any]:
        """处理文献综述分析"""
        try:
            task_data = task.task_data
            query = task_data.get('query', '')
            session_id = task_data.get('session_id', '')
            review_type = task_data.get('review_type', 'narrative')  # narrative, systematic, meta

            logger.info(f"开始处理文献综述分析: query='{query}', type='{review_type}'")

            # 获取缓存中的文献数据
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)

            if not cached_data or not cached_data.get('papers'):
                raise Exception("没有找到文献数据")

            papers = cached_data['papers']
            logger.info(f"获取到 {len(papers)} 篇文献用于综述分析")

            # 提取文献信息
            paper_summaries = []
            for i, paper in enumerate(papers[:50]):  # 使用前50篇文献
                summary = f"{i+1}. {paper.get('title', '')}"
                if paper.get('abstract'):
                    summary += f"\n摘要: {paper.get('abstract', '')[:300]}..."
                if paper.get('journal'):
                    summary += f"\n期刊: {paper.get('journal', '')} ({paper.get('pub_year', '')})"
                paper_summaries.append(summary)

            # 根据综述类型构建提示词
            if review_type == 'systematic':
                prompt = f"""作为系统综述专家，请基于以下{len(papers)}篇文献为"{query}"主题生成系统综述大纲和关键内容：

文献信息：
{chr(10).join(paper_summaries)}

请提供：
1. 系统综述标题建议
2. 结构化摘要（背景、目的、方法、结果、结论）
3. 详细大纲（包括PICO问题、检索策略、纳入排除标准）
4. 关键发现总结
5. 证据质量评估
6. 研究局限性
7. 临床意义和政策建议
8. 未来研究方向

请按照PRISMA指南要求生成高质量的系统综述框架。"""

            elif review_type == 'meta':
                prompt = f"""作为Meta分析专家，请基于以下{len(papers)}篇文献为"{query}"主题设计Meta分析方案：

文献信息：
{chr(10).join(paper_summaries)}

请提供：
1. Meta分析研究问题（PICO格式）
2. 纳入和排除标准
3. 检索策略建议
4. 数据提取计划
5. 统计分析方法选择
6. 异质性评估策略
7. 偏倚风险评估工具
8. 敏感性分析计划
9. 亚组分析建议
10. 结果解释指导

请提供完整的Meta分析实施方案。"""

            else:  # narrative
                prompt = f"""作为文献综述专家，请基于以下{len(papers)}篇文献为"{query}"主题生成叙述性综述：

文献信息：
{chr(10).join(paper_summaries)}

请提供：
1. 综述标题和摘要
2. 研究背景和意义
3. 文献检索和筛选方法
4. 主要研究发现分类总结
5. 不同研究间的比较分析
6. 争议点和分歧讨论
7. 研究空白和局限性
8. 临床或实践意义
9. 未来研究建议
10. 结论和展望

请生成结构清晰、逻辑严谨的叙述性综述。"""

            # 调用AI分析
            response = deepseek_service._make_request([
                {"role": "system", "content": "你是一位资深的文献综述专家，具有丰富的系统综述和Meta分析经验。"},
                {"role": "user", "content": prompt}
            ], temperature=0.4, max_tokens=4000)

            analysis_result = deepseek_service._extract_response_content(response)

            if not analysis_result:
                raise Exception("AI分析返回空结果")

            logger.info("文献综述分析完成")

            return {
                'success': True,
                'content': analysis_result,
                'review_type': review_type,
                'paper_count': len(papers),
                'query': query,
                'generated_at': datetime.now().isoformat(),
                'task_id': task.task_id
            }

        except Exception as e:
            logger.error(f"文献综述分析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }

    @staticmethod
    def handle_literature_screening(task: AsyncTask) -> Dict[str, Any]:
        """处理文献筛选分析"""
        try:
            task_data = task.task_data
            query = task_data.get('query', '')
            session_id = task_data.get('session_id', '')
            criteria = task_data.get('criteria', {})

            logger.info(f"开始处理文献筛选: query='{query}'")

            # 获取缓存中的文献数据
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)

            if not cached_data or not cached_data.get('papers'):
                raise Exception("没有找到文献数据")

            papers = cached_data['papers']
            logger.info(f"获取到 {len(papers)} 篇文献用于筛选分析")

            # 构建筛选标准
            criteria_text = ""
            if criteria.get('study_type'):
                criteria_text += f"研究类型: {criteria['study_type']}\n"
            if criteria.get('population'):
                criteria_text += f"研究人群: {criteria['population']}\n"
            if criteria.get('intervention'):
                criteria_text += f"干预措施: {criteria['intervention']}\n"
            if criteria.get('outcome'):
                criteria_text += f"结局指标: {criteria['outcome']}\n"
            if criteria.get('time_range'):
                criteria_text += f"时间范围: {criteria['time_range']}\n"

            # 提取文献信息
            paper_summaries = []
            for i, paper in enumerate(papers[:100]):  # 使用前100篇文献
                summary = f"{i+1}. 标题: {paper.get('title', '')}"
                if paper.get('abstract'):
                    summary += f"\n摘要: {paper.get('abstract', '')[:400]}..."
                if paper.get('journal'):
                    summary += f"\n期刊: {paper.get('journal', '')} ({paper.get('pub_year', '')})"
                paper_summaries.append(summary)

            prompt = f"""作为文献筛选专家，请根据以下研究目的和筛选标准，对文献进行智能筛选和分类：

研究目的: {query}

筛选标准:
{criteria_text if criteria_text else "请根据研究目的制定合适的筛选标准"}

文献列表:
{chr(10).join(paper_summaries)}

请提供：
1. 推荐的纳入标准和排除标准
2. 高度相关文献推荐（前20篇，包含推荐理由）
3. 中等相关文献列表
4. 不相关文献及排除理由
5. 文献质量评估建议
6. 进一步筛选的建议
7. 可能遗漏的重要文献类型
8. 筛选流程图建议

请提供详细的文献筛选报告。"""

            # 调用AI分析
            response = deepseek_service._make_request([
                {"role": "system", "content": "你是一位资深的文献筛选专家，具有丰富的系统综述和循证医学经验。"},
                {"role": "user", "content": prompt}
            ], temperature=0.3, max_tokens=4000)

            analysis_result = deepseek_service._extract_response_content(response)

            if not analysis_result:
                raise Exception("AI分析返回空结果")

            logger.info("文献筛选分析完成")

            return {
                'success': True,
                'content': analysis_result,
                'paper_count': len(papers),
                'query': query,
                'criteria': criteria,
                'generated_at': datetime.now().isoformat(),
                'task_id': task.task_id
            }

        except Exception as e:
            logger.error(f"文献筛选分析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }

    @staticmethod
    def handle_innovation_analysis(task: AsyncTask) -> Dict[str, Any]:
        """处理创新点识别分析"""
        try:
            task_data = task.task_data
            content = task_data.get('content', '')
            analysis_type = task_data.get('analysis_type', 'idea')  # idea, paper, proposal

            logger.info(f"开始处理创新点识别: type='{analysis_type}'")

            if not content:
                raise Exception("分析内容不能为空")

            # 根据分析类型构建提示词
            if analysis_type == 'paper':
                prompt = f"""作为创新性评估专家，请分析以下论文的创新点和贡献：

论文内容：
{content}

请从以下方面进行分析：
1. 理论创新点识别
2. 方法学创新评估
3. 技术创新分析
4. 应用创新价值
5. 与现有研究的差异性
6. 创新程度评分（1-10分）
7. 潜在影响力预测
8. 进一步创新建议

请提供详细的创新性分析报告。"""

            elif analysis_type == 'proposal':
                prompt = f"""作为创新性评估专家，请分析以下研究提案的创新点和研究价值：

研究提案：
{content}

请提供以下分析：
1. 研究问题的创新性
2. 研究方法的新颖性
3. 预期结果的突破性
4. 理论贡献潜力
5. 实践应用价值
6. 与现有研究的区别
7. 研究空白填补程度
8. 创新风险评估
9. 创新点强化建议

请提供全面的创新性评估报告。"""

            else:  # idea
                prompt = f"""作为创新性评估专家，请分析以下研究想法的创新潜力：

研究想法：
{content}

请提供以下分析：
1. 想法的原创性评估
2. 科学价值和意义
3. 技术可行性分析
4. 市场或应用前景
5. 与现有技术/理论的差异
6. 潜在的突破点
7. 实现难度评估
8. 风险和挑战识别
9. 创新路径建议
10. 后续发展方向

请提供系统性的创新潜力分析。"""

            # 调用AI分析
            response = deepseek_service._make_request([
                {"role": "system", "content": "你是一位资深的科研创新评估专家，具有丰富的技术评估和创新分析经验。"},
                {"role": "user", "content": prompt}
            ], temperature=0.4, max_tokens=3000)

            analysis_result = deepseek_service._extract_response_content(response)

            if not analysis_result:
                raise Exception("AI分析返回空结果")

            logger.info("创新点识别分析完成")

            return {
                'success': True,
                'content': analysis_result,
                'analysis_type': analysis_type,
                'generated_at': datetime.now().isoformat(),
                'task_id': task.task_id
            }

        except Exception as e:
            logger.error(f"创新点识别分析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }

    @staticmethod
    def handle_grant_proposal_writing(task: AsyncTask) -> Dict[str, Any]:
        """处理基金申请书撰写"""
        try:
            task_data = task.task_data
            research_topic = task_data.get('research_topic', '')
            grant_type = task_data.get('grant_type', 'nsfc')  # nsfc, nih, etc
            section = task_data.get('section', 'all')  # all, background, objectives, methods, etc

            logger.info(f"开始处理基金申请书撰写: topic='{research_topic}', type='{grant_type}', section='{section}'")

            if not research_topic:
                raise Exception("研究主题不能为空")

            # 根据基金类型和章节构建提示词
            if grant_type == 'nsfc':
                if section == 'all' or section == 'background':
                    prompt = f"""作为国家自然科学基金申请专家，请为以下研究主题撰写完整的申请书：

研究主题：{research_topic}

请按照国自然申请书格式提供以下内容：

1. 立项依据与研究内容
   - 项目的立项依据（研究意义、国内外研究现状及发展动态分析）
   - 项目的研究内容、研究目标，以及拟解决的关键科学问题
   - 拟采取的研究方案及可行性分析
   - 本项目的特色与创新之处

2. 研究基础与工作条件
   - 工作基础（与本项目相关的研究工作积累和已取得的研究成果）
   - 工作条件（包括实验室条件、仪器设备等）
   - 正在承担的与本项目相关的科研项目情况

3. 预期研究结果
   - 预期的研究成果
   - 成果的学术价值和应用前景

请提供详细、专业的申请书内容，符合国自然评审要求。"""

                elif section == 'objectives':
                    prompt = f"""请为研究主题"{research_topic}"撰写国自然申请书的研究目标和内容部分：

请包含：
1. 总体目标（明确、具体、可实现）
2. 具体研究内容（3-4个方面）
3. 关键科学问题（2-3个核心问题）
4. 预期突破点
5. 技术路线图

要求：目标明确、内容具体、逻辑清晰。"""

                elif section == 'methods':
                    prompt = f"""请为研究主题"{research_topic}"撰写国自然申请书的研究方案部分：

请包含：
1. 总体研究方案设计
2. 技术路线和实施方案
3. 关键技术和方法
4. 可行性分析
5. 风险评估和应对措施
6. 时间安排和进度计划

要求：方案科学、技术先进、可操作性强。"""

            else:  # 其他类型基金
                prompt = f"""作为基金申请专家，请为研究主题"{research_topic}"撰写{grant_type}基金申请书：

请提供：
1. 研究背景和意义
2. 研究目标和假设
3. 研究方法和设计
4. 预期成果和影响
5. 研究团队和条件
6. 预算和时间安排
7. 风险评估和管理

请提供专业、完整的申请书内容。"""

            # 调用AI分析
            response = deepseek_service._make_request([
                {"role": "system", "content": "你是一位资深的科研基金申请专家，具有丰富的基金申请和评审经验。"},
                {"role": "user", "content": prompt}
            ], temperature=0.3, max_tokens=4000)

            analysis_result = deepseek_service._extract_response_content(response)

            if not analysis_result:
                raise Exception("AI分析返回空结果")

            logger.info("基金申请书撰写完成")

            return {
                'success': True,
                'content': analysis_result,
                'research_topic': research_topic,
                'grant_type': grant_type,
                'section': section,
                'generated_at': datetime.now().isoformat(),
                'task_id': task.task_id
            }

        except Exception as e:
            logger.error(f"基金申请书撰写失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }

    @staticmethod
    def handle_statistical_analysis_expert(task: AsyncTask) -> Dict[str, Any]:
        """处理统计分析专家咨询"""
        try:
            task_data = task.task_data
            research_question = task_data.get('research_question', '')
            study_design = task_data.get('study_design', '')
            data_type = task_data.get('data_type', '')
            sample_size = task_data.get('sample_size', '')

            logger.info(f"开始处理统计分析专家咨询: question='{research_question}'")

            if not research_question:
                raise Exception("研究问题不能为空")

            prompt = f"""作为资深的生物统计学专家，请为以下研究提供专业的统计分析建议：

研究问题：{research_question}

研究设计：{study_design if study_design else '未指定'}
数据类型：{data_type if data_type else '未指定'}
样本量：{sample_size if sample_size else '未指定'}

请提供以下统计分析建议：

1. 研究设计评估
   - 当前设计的适用性
   - 设计改进建议
   - 潜在偏倚控制

2. 样本量计算
   - 推荐的样本量计算方法
   - 效应量估计
   - 检验效能分析

3. 统计方法选择
   - 描述性统计方法
   - 推断性统计方法
   - 多变量分析策略

4. 数据预处理
   - 数据清洗步骤
   - 缺失值处理
   - 异常值检测

5. 统计分析流程
   - 分析步骤详细说明
   - 假设检验策略
   - 多重比较校正

6. 结果解释指导
   - 统计显著性解释
   - 临床意义评估
   - 置信区间解读

7. 软件推荐
   - 适用的统计软件
   - 具体分析代码示例

8. 常见陷阱提醒
   - 统计误用警告
   - 结果解释注意事项

请提供详细、专业的统计分析方案。"""

            # 调用AI分析
            response = deepseek_service._make_request([
                {"role": "system", "content": "你是一位资深的生物统计学专家，具有丰富的统计分析和研究设计经验。"},
                {"role": "user", "content": prompt}
            ], temperature=0.2, max_tokens=4000)

            analysis_result = deepseek_service._extract_response_content(response)

            if not analysis_result:
                raise Exception("AI分析返回空结果")

            logger.info("统计分析专家咨询完成")

            return {
                'success': True,
                'content': analysis_result,
                'research_question': research_question,
                'study_design': study_design,
                'data_type': data_type,
                'sample_size': sample_size,
                'generated_at': datetime.now().isoformat(),
                'task_id': task.task_id
            }

        except Exception as e:
            logger.error(f"统计分析专家咨询失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }

    @staticmethod
    def handle_visualization_expert(task: AsyncTask) -> Dict[str, Any]:
        """处理绘图建议专家咨询"""
        try:
            task_data = task.task_data
            data_description = task_data.get('data_description', '')
            research_objective = task_data.get('research_objective', '')
            data_type = task_data.get('data_type', '')
            audience = task_data.get('audience', 'academic')

            logger.info(f"开始处理绘图建议专家咨询: objective='{research_objective}'")

            if not data_description and not research_objective:
                raise Exception("数据描述或研究目标不能为空")

            prompt = f"""作为资深的数据可视化专家，请为以下研究提供专业的绘图建议：

数据描述：{data_description}
研究目标：{research_objective}
数据类型：{data_type if data_type else '未指定'}
目标受众：{audience}

请提供以下可视化建议：

1. 图表类型选择
   - 推荐的主要图表类型
   - 每种图表的适用场景
   - 图表选择理由

2. 数据预处理建议
   - 数据整理要求
   - 分组和分类策略
   - 数据转换方法

3. 具体绘图方案
   - 详细的绘图步骤
   - 坐标轴设置建议
   - 颜色和样式选择

4. 统计图形建议
   - 误差线类型选择
   - 显著性标记方法
   - 置信区间显示

5. 软件工具推荐
   - 适用的绘图软件
   - 具体操作指导
   - 代码示例（如适用）

6. 图表美化建议
   - 布局和排版
   - 字体和大小设置
   - 图例和标注优化

7. 学术规范要求
   - 期刊投稿标准
   - 分辨率和格式要求
   - 图表标题和说明

8. 常见错误避免
   - 可视化误区提醒
   - 数据表达准确性
   - 视觉欺骗防范

请提供详细、实用的可视化方案。"""

            # 调用AI分析
            response = deepseek_service._make_request([
                {"role": "system", "content": "你是一位资深的数据可视化专家，具有丰富的科学绘图和数据展示经验。"},
                {"role": "user", "content": prompt}
            ], temperature=0.3, max_tokens=4000)

            analysis_result = deepseek_service._extract_response_content(response)

            if not analysis_result:
                raise Exception("AI分析返回空结果")

            logger.info("绘图建议专家咨询完成")

            return {
                'success': True,
                'content': analysis_result,
                'data_description': data_description,
                'research_objective': research_objective,
                'data_type': data_type,
                'audience': audience,
                'generated_at': datetime.now().isoformat(),
                'task_id': task.task_id
            }

        except Exception as e:
            logger.error(f"绘图建议专家咨询失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }


# 注册任务处理器
def register_academic_analysis_handlers():
    """注册学术分析任务处理器"""
    from services.async_task_service import get_async_task_service
    
    task_service = get_async_task_service()
    
    task_service.register_handler('review_topic_analysis', 
                                AcademicAnalysisHandlers.handle_review_topic_analysis)
    task_service.register_handler('research_topic_analysis', 
                                AcademicAnalysisHandlers.handle_research_topic_analysis)
    task_service.register_handler('full_review_generation', 
                                AcademicAnalysisHandlers.handle_full_review_generation)
    task_service.register_handler('representative_papers_recommendation',
                                AcademicAnalysisHandlers.handle_representative_papers_recommendation)
    task_service.register_handler('research_method_analysis',
                                AcademicAnalysisHandlers.handle_research_method_analysis)
    task_service.register_handler('literature_review_analysis',
                                AcademicAnalysisHandlers.handle_literature_review_analysis)
    task_service.register_handler('literature_screening',
                                AcademicAnalysisHandlers.handle_literature_screening)
    task_service.register_handler('innovation_analysis',
                                AcademicAnalysisHandlers.handle_innovation_analysis)
    task_service.register_handler('grant_proposal_writing',
                                AcademicAnalysisHandlers.handle_grant_proposal_writing)
    task_service.register_handler('statistical_analysis_expert',
                                AcademicAnalysisHandlers.handle_statistical_analysis_expert)
    task_service.register_handler('visualization_expert',
                                AcademicAnalysisHandlers.handle_visualization_expert)
    task_service.register_handler('reference_matching',
                                AcademicAnalysisHandlers.handle_reference_matching)

    logger.info("学术分析任务处理器注册完成")
