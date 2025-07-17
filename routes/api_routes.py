"""API routes for REST endpoints."""

from flask import Blueprint, request, jsonify, session, send_file
from flask_socketio import emit
import logging
from datetime import datetime
from typing import Dict, Any, List
import os
import tempfile
import re
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

from config.settings import config
from models.session import session_manager
from models.journal import journal_db
from services.pubmed_service import pubmed_service
from services.deepseek_service import deepseek_service
from services.embedding_service import embedding_service
from services.export_service import export_service
from services.async_task_service import get_async_task_service
from utils.cache_utils import get_cache_stats, cleanup_global_cache
from utils.session_cache import get_papers_cache
from journal_analyzer import JournalAnalyzer

logger = logging.getLogger(__name__)


def emit_progress(stage: str, message: str, **kwargs):
    """安全地发送进度更新，如果Socket.IO可用的话"""
    try:
        progress_data = {
            'stage': stage,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        # 从Flask应用上下文获取socketio实例
        from flask import current_app
        if hasattr(current_app, 'socketio'):
            # 向所有连接的客户端发送进度更新
            current_app.socketio.emit('search_progress', progress_data, namespace='/')
            logger.info(f"Progress emitted: {stage} - {message}")
        else:
            logger.debug(f"SocketIO not available, progress: {stage} - {message}")
    except Exception as e:
        # 如果Socket.IO不可用，仅记录警告，不中断主流程
        logger.warning(f"Failed to emit progress: {e}")


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
            
        # 简单的关键词处理：添加到标题/摘要字段
        expanded_terms.append(f'"{keyword}"[Title/Abstract]')
    
    return " OR ".join(expanded_terms)


# Create blueprint
api_bp = Blueprint('api', __name__)


def get_current_session():
    """Get current user session."""
    session_id = session.get('session_id')
    if not session_id:
        return None
    return session_manager.get_session(session_id)


def handle_api_error(error: Exception, operation: str) -> Dict[str, Any]:
    """Handle API errors consistently."""
    error_msg = str(error)
    logger.error(f"{operation} failed: {error_msg}")
    
    return {
        'success': False,
        'error': error_msg,
        'operation': operation,
        'timestamp': datetime.now().isoformat()
    }


@api_bp.route('/search', methods=['POST'])
def search_papers():
    """Search for papers using PubMed - 兼容原版本API."""
    try:
        data = request.get_json() or {}
        
        # 兼容原版本参数: session_id, query, sentences, id_list, mode
        # 优先从header中获取sid，保持与分析API一致
        session_id = data.get('session_id', '') or request.headers.get('sid', '') or request.headers.get('session_id', '')
        query = data.get('query', '').strip()
        sentences = data.get('sentences', [])
        id_list = data.get('id_list', [])
        pmids = data.get('pmids', id_list)  # 新版本参数pmids对应原版本id_list
        mode = data.get('mode', 'single')  # 添加mode参数，默认为single模式
        
        # 详细的session调试日志
        logger.info(f"Search API - Data session_id: {data.get('session_id', 'None')}")
        logger.info(f"Search API - Header sid: {request.headers.get('sid', 'None')}")
        logger.info(f"Search API - Header session_id: {request.headers.get('session_id', 'None')}")
        logger.info(f"Search API - Final session_id: {session_id}")
        logger.info(f"Search API - Query: '{query}'")
        logger.info(f"Search API - Mode: '{mode}' (type: {type(mode)})")
        logger.info(f"Search API - Mode comparison: mode == 'paragraph' -> {mode == 'paragraph'}")
        
        # 如果提供了sentences，使用sentences重构query
        if sentences and isinstance(sentences, list):
            query = ' '.join(sentences) if not query else query
        
        if not query and not pmids:
            return jsonify({
                'success': False,
                'error': 'Query or pmids is required'
            }), 400
        
        # 根据模式处理搜索
        if mode == 'paragraph':
            # 段落模式处理
            from utils.text_processing import split_paragraph_to_sentences, process_paragraph_threaded
            
            emit_progress('paragraph_mode', "正在使用段落模式处理...", percentage=10)
            
            # 分解段落为句子
            sentences = split_paragraph_to_sentences(query)
            if not sentences:
                return jsonify({
                    'success': True,
                    'sentences': []
                })
            
            logger.info(f"段落模式：分解为 {len(sentences)} 个句子")
            
            # 使用线程池并行处理所有句子
            results = process_paragraph_threaded(session_id, sentences, data.get('filters', {}))
            
            # 发送完成消息
            emit_progress('paragraph_complete', f"段落处理完成，共处理 {len(results)} 个句子", percentage=100)
            
            return jsonify({
                'success': True,
                'sentences': results,
                'session_id': session_id,
                'mode': 'paragraph'
            })
            
        # single模式或strategy模式继续正常处理
        
        # 兼容多种前端发送的数据结构获取文章数量限制
        # 1. Index界面：{filters: {papers_limit: "10"}}
        # 2. Chat界面：{papers_limit: 500}
        # 3. 直接参数：{max_results: 100}
        filters = data.get('filters', {})
        papers_limit = None
        
        # 优先从filters中获取papers_limit (Index界面)
        if 'papers_limit' in filters:
            papers_limit = filters['papers_limit']
        # 其次从顶级参数获取papers_limit (Chat界面)
        elif 'papers_limit' in data:
            papers_limit = data['papers_limit']
        # 最后使用max_results或默认值
        else:
            papers_limit = data.get('max_results', 100)
        
        # 统一转换为整数
        if isinstance(papers_limit, str) and papers_limit.isdigit():
            papers_limit = int(papers_limit)
        elif not isinstance(papers_limit, int):
            papers_limit = 100
            
        max_results = min(papers_limit, config.MAX_SEARCH_RESULTS)
        search_mode = data.get('search_mode', 'comprehensive')
        
        logger.info(f"API search request: {query[:100]}... (max_results={max_results})")
        
        # 发送搜索开始信号
        emit_progress('search_started', 'Search started...', percentage=5, query=query[:100], max_results=max_results)
        
        # Generate optimized search strategy if requested
        use_ai_strategy = data.get('use_ai_strategy', True)
        
        # 策略模式跳过AI策略生成
        if mode == 'strategy':
            use_ai_strategy = False
            logger.info(f"策略模式：跳过AI策略生成，直接使用用户提供的策略")
        
        if use_ai_strategy:
            try:
                emit_progress('strategy_generation', 'Generating AI-optimized search strategy...', percentage=10)
                optimized_query = deepseek_service.generate_search_strategy(query, search_mode)
                if optimized_query:
                    query = optimized_query
                    emit_progress('strategy_generated', 'AI strategy generated', percentage=20, optimized_query=query[:100])
                    logger.info(f"Using AI-optimized query: {query[:100]}...")
            except Exception as e:
                emit_progress('strategy_fallback', 'Using original query (AI strategy failed)', percentage=15)
                logger.warning(f"AI strategy generation failed, using original query: {e}")
        
        # 在搜索前应用年份过滤器
        final_query = query
        if filters and 'year_start' in filters and 'year_end' in filters:
            year_start = filters.get('year_start')
            year_end = filters.get('year_end')
            if year_start and year_end:
                year_filter = f' AND ("{year_start}"[Date - Publication] : "{year_end}"[Date - Publication])'
                final_query = f"({query}){year_filter}"
                logger.info(f"应用年份过滤器: {year_start}-{year_end}")

        # Search papers
        emit_progress('pubmed_search', 'Searching PubMed database...', percentage=30)
        pmids, total_count = pubmed_service.search_papers(final_query, max_results)
        
        if not pmids:
            emit_progress('search_completed', 'No papers found', percentage=100, total_count=0)
            return jsonify({
                'success': True,
                'papers': [],
                'total_count': 0,
                'query': query,
                'message': 'No papers found'
            })
        
        # Fetch paper details
        emit_progress('fetching_details', f'Found {len(pmids)} papers, fetching details...', 
                      percentage=40, found_count=len(pmids), total_count=total_count)
        
        # 创建进度回调函数，将批次进度映射到40-70%
        def progress_callback(stage, message, **kwargs):
            if 'completed_batches' in kwargs and 'total_batches' in kwargs:
                batch_progress = (kwargs['completed_batches'] / kwargs['total_batches']) * 30
                percentage = 40 + batch_progress
                emit_progress(stage, message, percentage=min(70, percentage), **kwargs)
            else:
                emit_progress(stage, message, **kwargs)
        
        papers = pubmed_service.fetch_paper_details_batch(pmids, progress_callback=progress_callback)
        
        # Calculate relevance scores if requested
        include_relevance = data.get('include_relevance', True)
        if include_relevance and papers:
            try:
                emit_progress('calculating_relevance', 'Calculating relevance scores...', percentage=75)
                # Prepare texts for relevance calculation
                paper_texts = []
                for paper in papers:
                    text = f"{paper.title} {paper.abstract}"
                    paper_texts.append(text)
                
                # Calculate relevance scores
                original_query = data.get('original_query', query)
                relevance_scores = embedding_service.calculate_relevance_scores(
                    original_query, paper_texts
                )
                
                # Add scores to papers
                for i, paper in enumerate(papers):
                    if i < len(relevance_scores):
                        paper.relevance_score = relevance_scores[i]
                
                # Sort by relevance
                papers.sort(key=lambda p: p.relevance_score or 0, reverse=True)
                
            except Exception as e:
                logger.warning(f"Relevance calculation failed: {e}")
        
        # Convert to dict format and preserve relevance_score
        paper_dicts = []
        for paper in papers:
            paper_dict = paper.to_dict()
            # 保留相关度分数
            if hasattr(paper, 'relevance_score'):
                paper_dict['relevance_score'] = paper.relevance_score
            paper_dicts.append(paper_dict)
        
        # Add journal metrics
        emit_progress('adding_metrics', 'Adding journal metrics...', percentage=85)
        for paper_dict in paper_dicts:
            journal_name = paper_dict.get('journal', '')
            if journal_name:
                metrics = journal_db.get_journal_metrics(journal_name)
                if metrics:
                    paper_dict['impact_factor'] = metrics.impact_factor
                    paper_dict['jcr_quartile'] = metrics.jcr_quartile
                    paper_dict['cas_quartile'] = metrics.cas_quartile
        
        # Store results in session
        user_session = get_current_session()
        if not user_session:
            # 如果没有现有session，创建一个新的
            user_session = session_manager.create_session()
            session['session_id'] = user_session.session_id
        
        if user_session:
            user_session.add_search_result(query, paper_dicts)
        
        # 确定最终使用的session_id：优先使用前端传来的session_id
        final_session_id = session_id or (user_session.session_id if user_session else None)
        logger.info(f"Search API - Frontend session_id: {session_id}")
        logger.info(f"Search API - Backend session_id: {user_session.session_id if user_session else None}")
        logger.info(f"Search API - Final session_id for cache: {final_session_id}")
        
        # 同时存储到兼容缓存（支持原版本API）
        if final_session_id:
            cache = get_papers_cache()
            # 存储初始数据和筛选后数据（暂时相同）
            cache.store_papers(final_session_id, paper_dicts, query, original_papers=paper_dicts)
        
        result = {
            'success': True,
            'data': paper_dicts,
            'original_papers': paper_dicts,
            'search_strategy': query,
            'total_count': total_count,
            'filtered_count': len(paper_dicts),
            'has_cached_data': bool(final_session_id),
            'session_id': final_session_id,
            'sentences': sentences,
            'mode': mode,  # 添加mode信息
            'export_files': {
                'initial_excel': 'ready',
                'filtered_excel': 'ready',
                'initial_word': 'ready', 
                'filtered_word': 'ready'
            } if session_id and paper_dicts else None
        }
        
        # 发送搜索完成信号
        emit_progress('search_completed', 'Search completed successfully', percentage=100,
                      papers_count=len(paper_dicts), total_count=total_count)
        
        logger.info(f"Search completed: {len(paper_dicts)} papers returned")
        
        return jsonify(result)
        
    except Exception as e:
        # 发送错误进度更新
        emit_progress('search_error', f'Search failed: {str(e)}', percentage=0, error=True)
        logger.error(f"Search error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/generate_strategy', methods=['POST'])
def generate_strategy():
    """生成检索策略 - 兼容原版本API"""
    try:
        data = request.get_json() or {}
        
        # 兼容原版本参数: session_id, query, sentences
        session_id = data.get('session_id', '') or request.headers.get('session_id', '')
        query = data.get('query', '').strip() or data.get('topic', '').strip()
        sentences = data.get('sentences', [])
        mode = data.get('mode', 'single')
        filters = data.get('filters', {})
        search_mode = data.get('search_mode', 'comprehensive')
        
        # 如果提供了sentences，使用sentences重构query
        if sentences and isinstance(sentences, list):
            query = ' '.join(sentences) if not query else query
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请输入检索内容'
            }), 400
        
        logger.info(f"Generating search strategy for: {query}, mode: {mode}")
        
        if mode == 'paragraph':
            # 段落模式：分句并为每个句子生成检索策略
            from utils.text_processing import split_paragraph_to_sentences
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
                    # 生成检索策略
                    search_strategy = deepseek_service.generate_search_strategy(sentence, search_mode)
                    
                    # 策略生成阶段不添加年份限制，保持策略纯净
                    # 年份过滤器将在执行阶段通过pubmed_service自动处理
                    
                    results.append({
                        'text': sentence,
                        'search_strategy': search_strategy
                    })
                    
                except Exception as e:
                    logger.error(f"处理句子时出错: {str(e)}")
                    continue
            
            return jsonify({
                'success': True,
                'sentences': results
            })
            
        else:
            # 单句模式：生成单个检索策略
            try:
                search_strategy = deepseek_service.generate_search_strategy(query, search_mode)
                
                # 策略生成阶段不添加年份限制，保持策略纯净
                # 年份过滤器将在执行阶段通过pubmed_service自动处理
                
                return jsonify({
                    'success': True,
                    'search_strategy': search_strategy,
                    'sentences': [{'text': query, 'search_strategy': search_strategy}]
                })
                
            except Exception as e:
                logger.error(f"生成检索策略时出错: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
                
    except Exception as e:
        logger.error(f"生成检索策略时出错: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/analyze_research_status', methods=['POST'])
def analyze_research_status():
    """分析研究现状API端点 - 兼容原版本"""
    try:
        data = request.get_json() or {}
        # 兼容原版本：data参数可选
        
        # 兼容原版本参数: query, titles, paper_count
        # 同时支持新版本参数: papers, topic
        query = data.get('query', '').strip() or data.get('topic', '').strip()
        titles = data.get('titles', [])
        paper_count = data.get('paper_count', 0)
        papers = data.get('papers', [])
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请提供研究方向'
            }), 400

        # 如果没有提供titles但有papers，从papers中提取titles
        if not titles and papers:
            titles = [paper.get('title', '') for paper in papers]
            paper_count = len(papers)
        
        # 如果没有提供titles，从缓存中获取（原版本兼容）
        if not titles:
            session_id = request.headers.get('sid') or session.get('session_id')
            logger.info(f"研究现状分析 - 会话ID: {session_id}")
            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    titles = [paper.get('title', '') for paper in cached_data['papers']]
                    if not query:
                        query = cached_data['query']  # 使用缓存中的查询词
                    paper_count = len(cached_data['papers'])
                    logger.info(f"研究现状分析 - 从缓存获取到 {len(titles)} 篇文献")
                else:
                    logger.warning(f"研究现状分析 - 会话ID {session_id} 不在缓存中")

        if not titles:
            return jsonify({
                'success': False,
                'error': '没有文献标题用于分析，请先进行文献检索'
            }), 400

        # 构建分析提示词 - 使用相关性最强的150篇文献
        selected_titles = titles[:150]  # 取前150篇相关性最强的文献
        titles_text = '\n'.join([f"{i+1}. {title}" for i, title in enumerate(selected_titles)])

        prompt = f"""- Role: 学术研究前沿分析师
- Background: 用户已经收集了特定研究领域的文献资料，需要对这些文献进行深入分析，以生成一份能够反映该领域前沿发展的调研报告。
- Profile: 你是一位在学术研究领域有着丰富经验的前沿分析师，擅长从大量文献中提取关键信息，识别研究趋势和创新点。
- Skills: 你具备文献综述能力、数据分析能力、趋势预测能力以及报告撰写能力。
- Goals:
  1. 对文献进行全面梳理，提取关键研究内容和成果。
  2. 分析该领域的研究趋势，识别当前的研究热点和未来的发展方向。
  3. 挖掘文献中的潜在问题和未解决的挑战，为后续研究提供参考。
  4. 撰写一份结构清晰、内容详实的前沿发展调研报告。
- Constrains: 报告应基于文献内容，确保信息的准确性和客观性。在分析时，请自然地说"文献显示"、"研究表明"、"相关文献"等。
- OutputFormat: 请用中文回答，使用HTML格式，包含适当的标题和段落标签。

现在请对"{query}"领域进行专业的前沿发展分析。以下是{len(selected_titles)}篇高相关性文献：

{titles_text}

请严格按照上述要求进行分析，自然地引用文献内容，确保内容专业、准确、具有前瞻性。"""

        try:
            # 调用AI分析
            from services.deepseek_service import DeepSeekService
            deepseek_service = DeepSeekService()
            analysis = deepseek_service.analyze_text(prompt)

            return jsonify({
                'success': True,
                'suggestion': analysis,  # 注意这里改为'suggestion'字段名以兼容前端
                'analyzed_papers': len(selected_titles),
                'total_papers': paper_count or len(titles)
            })

        except Exception as e:
            logger.error(f"AI分析失败: {str(e)}")
            # 提供备用分析
            fallback_analysis = f"""
            <h3>📊 {query} - 前沿发展分析</h3>

            <h4>🔬 研究现状</h4>
            <p>"{query}"领域当前呈现出多元化发展态势。从{len(selected_titles)}篇高相关性文献可以看出，该领域研究深度和广度都在不断扩展。</p>

            <h4>📈 研究趋势</h4>
            <p>该领域正朝着精准化、个性化和智能化方向发展。跨学科融合趋势明显，新兴技术的应用日益广泛。</p>

            <h4>⚠️ 面临的挑战</h4>
            <p>当前该领域面临研究方法标准化、数据质量和可重复性等挑战。</p>

            <h4>🚀 未来发展方向</h4>
            <p>未来该领域有望在技术创新、临床转化和产业应用方面取得重大突破。</p>

            <p><em>💡 注：由于AI分析服务暂时不可用，以上为专业基础分析。</em></p>
            """

            return jsonify({
                'success': True,
                'suggestion': fallback_analysis,  # 改为'suggestion'字段名以兼容前端
                'analyzed_papers': len(selected_titles),
                'total_papers': paper_count or len(titles)
            })
        
    except Exception as e:
        logger.error(f"分析研究现状时出错: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/review_topic_suggestion', methods=['POST'])
def review_topic_suggestion_deprecated():
    """基于真实文献的综述选题建议API端点 - 完全复制原版本实现"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        titles = data.get('titles', [])
        papers = data.get('papers', [])

        if not query:
            return jsonify({
                'success': False,
                'error': '请提供研究方向'
            }), 400

        # 如果没有提供titles和papers，从缓存中获取
        if not titles and not papers:
            session_id = request.headers.get('sid') or session.get('session_id')
            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    papers = cached_data.get('papers', [])
                    titles = [paper.get('title', '') for paper in papers]
                    query = cached_data.get('query', query)  # 使用缓存中的查询词

        # 如果有papers但没有titles，从papers中提取
        if papers and not titles:
            titles = [paper.get('title', '') for paper in papers]

        if not titles and not papers:
            return jsonify({
                'success': False,
                'error': '没有文献数据用于分析，请先进行文献检索'
            }), 400

        # 使用前150篇相关性最强的文献
        selected_titles = titles[:150] if titles else []
        selected_papers = papers[:150] if papers else []

        # 构建综述选题分析提示词
        titles_text = '\n'.join([f"{i+1}. {title}" for i, title in enumerate(selected_titles)])

        # 如果有完整的文献信息，提取更多细节
        papers_info = ""
        if selected_papers:
            papers_info = "\n\n文献详细信息（前20篇）：\n"
            for i, paper in enumerate(selected_papers[:20]):
                authors = paper.get('authors', [])
                author_str = ', '.join(authors[:3]) + ('等' if len(authors) > 3 else '')
                year = paper.get('year', '未知年份')
                journal = paper.get('journal', '未知期刊')
                papers_info += f"{i+1}. {paper.get('title', '无标题')} - {author_str} ({year}) {journal}\n"

        prompt = f"""- Role: 学术综述选题专家
- Background: 用户已经收集了特定研究领域的文献资料，需要基于这些真实文献提供具体的综述选题建议。
- Profile: 你是一位在学术写作和文献综述方面有着丰富经验的专家，擅长从大量文献中识别研究热点、发现研究空白、提出有价值的综述选题。
- Skills: 你具备文献分析能力、选题策划能力、学术写作指导能力，能够基于真实文献数据提供具体可行的综述选题建议。
- Goals:
  1. 基于提供的文献分析该领域的研究热点和发展趋势
  2. 识别适合综述的具体角度和切入点
  3. 提供3-5个具体的综述选题建议
  4. 为每个选题提供详细的写作思路和文献支撑
- Constrains: 选题建议必须基于提供的真实文献，确保可行性和学术价值。避免过于宽泛或过于狭窄的选题。
- OutputFormat: 请用中文回答，使用HTML格式，包含适当的标题和段落标签。

现在请基于"{query}"领域的{len(selected_titles)}篇文献，提供具体的综述选题建议：

文献标题列表：
{titles_text}
{papers_info}

请提供：
1. 该领域研究热点分析
2. 3-5个具体的综述选题建议
3. 每个选题的写作思路和预期贡献
4. 推荐的文献组织方式

确保选题具有学术价值、可操作性和创新性。"""

        try:
            # 调用AI分析
            logger.info(f"开始调用DeepSeek API生成综述选题建议，论文数量: {len(selected_titles)}")
            suggestion_result = deepseek_service._make_request([
                {"role": "system", "content": "你是一位专业的学术综述选题专家。"},
                {"role": "user", "content": prompt}
            ])
            
            suggestion = deepseek_service._extract_response_content(suggestion_result)
            logger.info(f"AI返回的建议内容长度: {len(suggestion)} 字符")
            
            # 检查返回内容是否有效
            if suggestion and len(suggestion.strip()) > 10:  # 至少10个字符的有效内容
                logger.info("AI生成的建议内容有效，存储到session并返回")
                
                # 存储到session中供新页面使用 - DEPRECATED: 使用异步API替代
                # session['review_topic_result'] = {
                #     'content': suggestion,
                #     'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                #     'paper_count': len(selected_titles),
                #     'search_query': query,
                #     'loading': False,
                #     'error': None
                # }
                
                return jsonify({
                    'success': True,
                    'suggestion': suggestion,
                    'analyzed_papers': len(selected_titles),
                    'total_papers': len(titles) if titles else len(papers),
                    'redirect_url': '/analysis/review_topic'
                })
            else:
                logger.warning(f"AI返回的建议内容无效或过短: '{suggestion}', 使用备用建议")
                # 内容无效，使用备用建议

        except Exception as e:
            logger.error(f"AI选题建议生成失败: {str(e)}")
            # 提供备用建议
            fallback_suggestion = f"""
            <h3>📝 {query} - 综述选题建议</h3>

            <h4>🔥 研究热点分析</h4>
            <p>基于{len(selected_titles)}篇文献分析，该领域当前的研究热点集中在技术创新、临床应用和方法学改进等方面。</p>

            <h4>📋 推荐综述选题</h4>
            <ol>
                <li><strong>{query}技术发展与临床应用综述</strong>
                    <p>梳理该领域的技术演进历程，总结当前主流技术的优缺点，分析临床应用现状和前景。</p>
                </li>
                <li><strong>{query}相关方法学比较与评价</strong>
                    <p>系统比较不同研究方法的适用性、准确性和局限性，为研究者选择合适方法提供参考。</p>
                </li>
                <li><strong>{query}领域的挑战与未来发展方向</strong>
                    <p>分析当前面临的主要技术和临床挑战，预测未来发展趋势和研究重点。</p>
                </li>
            </ol>

            <h4>💡 写作建议</h4>
            <p>建议采用系统性综述的方法，按照技术发展时间线或应用领域进行文献组织，确保综述的逻辑性和完整性。</p>

            <p><em>💡 注：由于AI分析服务暂时不可用，以上为基于文献数量和研究领域的基础建议。</em></p>
            """
            
            # 存储备用建议到session - DEPRECATED: 使用异步API替代
            # session['review_topic_result'] = {
            #     'content': fallback_suggestion,
            #     'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            #     'paper_count': len(selected_titles),
            #     'search_query': query,
            #     'loading': False,
            #     'error': None
            # }

            return jsonify({
                'success': True,
                'suggestion': fallback_suggestion,
                'analyzed_papers': len(selected_titles),
                'total_papers': len(titles) if titles else len(papers),
                'redirect_url': '/analysis/review_topic'
            })
        
    except Exception as e:
        logger.error(f"综述选题建议生成出错: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/research_topic_suggestion', methods=['POST'])
def research_topic_suggestion():
    """Suggest original research topics - 兼容原版本API."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        papers = data.get('papers', [])
        topic = data.get('topic', '').strip() or data.get('query', '').strip()
        
        # 如果没有提供papers，从缓存中获取（兼容前端调用）
        if not papers:
            session_id = request.headers.get('sid') or session.get('session_id')
            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    papers = cached_data.get('papers', [])
                    if not topic:
                        topic = cached_data.get('query', topic)
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        if not topic:
            return jsonify({'success': False, 'error': 'Topic is required'}), 400
        
        logger.info(f"Generating research topic suggestions for {len(papers)} papers")
        
        try:
            result = deepseek_service.suggest_research_topics(papers, topic)
            # 处理字典返回值
            if isinstance(result, dict):
                if 'error' in result:
                    suggestions = f"分析出现错误: {result['error']}"
                else:
                    suggestions = result.get('research_suggestions', '')
            else:
                suggestions = str(result) if result else ''
        except AttributeError:
            # 如果方法不存在，提供备用建议
            suggestions = f"""
            <h3>🔬 {topic} - 论著选题建议</h3>
            
            <h4>🎯 基于{len(papers)}篇文献的选题建议</h4>
            <ol>
                <li><strong>基于现有研究的改进性研究</strong>
                    <p>分析当前研究的局限性，提出新的研究方法或技术改进方案。</p>
                </li>
                <li><strong>多中心验证性研究</strong>
                    <p>对已有的单中心研究结果进行多中心验证，扩大样本量和代表性。</p>
                </li>
                <li><strong>机制探索性研究</strong>
                    <p>深入研究{topic}相关的分子机制、信号通路或病理过程。</p>
                </li>
                <li><strong>临床转化研究</strong>
                    <p>将基础研究成果转化为临床应用，开展临床试验或效果评估。</p>
                </li>
            </ol>
            
            <h4>💡 选题建议</h4>
            <p>建议从当前研究的空白点出发，结合临床需求和技术可行性，选择具有创新性和实用性的研究方向。</p>
            
            <p><em>💡 注：基于文献分析的基础建议，建议结合具体研究条件进行选题。</em></p>
            """
        
        if not suggestions:
            suggestions = f"基于{len(papers)}篇文献的分析，建议从当前研究的空白点和局限性出发，提出创新性的研究选题。"
        
        # 存储到session中供新页面使用 - DEPRECATED: 使用异步API替代
        # session['research_topic_result'] = {
        #     'content': suggestions,
        #     'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        #     'paper_count': len(papers),
        #     'search_query': topic,
        #     'loading': False,
        #     'error': None
        # }
        
        return jsonify({
            'success': True,
            'suggestions': suggestions,
            'redirect_url': '/analysis/research_topic'
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'research_topic_suggestion')), 500


@api_bp.route('/generate_full_review', methods=['POST'])
def generate_full_review():
    """Generate complete literature review - 兼容原版本API."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        papers = data.get('papers', [])
        topic = data.get('topic', '').strip() or data.get('query', '').strip()
        review_type = data.get('review_type', 'narrative')
        language = data.get('language', 'chinese')  # 支持语言选择
        
        # 如果没有提供papers，从缓存中获取（兼容前端调用）
        if not papers:
            session_id = request.headers.get('sid') or session.get('session_id')
            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    papers = cached_data.get('papers', [])
                    if not topic:
                        topic = cached_data.get('query', topic)
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        if not topic:
            return jsonify({'success': False, 'error': 'Topic is required'}), 400
        
        logger.info(f"Generating {review_type} review for {len(papers)} papers in {language}")

        # 使用高级综述服务
        from services.advanced_review_service import AdvancedReviewService
        from services.deepseek_service import DeepSeekService

        deepseek = DeepSeekService()
        review_service = AdvancedReviewService(deepseek)

        try:
            result = review_service.generate_comprehensive_review(
                papers=papers,
                topic=topic,
                user_title=topic,
                language=language
            )

            if result.get('success'):
                review = result.get('content', '')
                if not review:
                    review = "综述生成完成，但内容为空。"
            else:
                review = f"综述生成失败: {result.get('error', '未知错误')}"

        except Exception as e:
            logger.error(f"Advanced review service failed: {str(e)}")
            # 提供备用综述
            if language == 'english':
                review = f"""
                <h1>{topic} - Literature Review</h1>

                <h2>Abstract</h2>
                <p>This review provides a comprehensive analysis of the current research status, development trends, and future directions in the field of {topic}, based on {len(papers)} relevant literature.</p>

                <h2>Introduction</h2>
                <p>{topic} is a hot research field with emerging studies. Through systematic analysis of relevant literature, we can better understand the development trajectory and research focus of this field.</p>

                <h2>Current Research Status</h2>
                <p>Based on the analysis of {len(papers)} papers, current research in the {topic} field mainly focuses on the following aspects:</p>
                <ul>
                    <li>Basic theoretical research</li>
                    <li>Technical method innovation</li>
                    <li>Clinical application validation</li>
                    <li>Effect evaluation and optimization</li>
                </ul>

                <h2>Development Trends</h2>
                <p>The field is developing towards precision, personalization, and intelligence, with obvious interdisciplinary integration trends.</p>

                <h2>Conclusions and Prospects</h2>
                <p>Based on current literature analysis, the {topic} field has made significant progress in theoretical research, technological innovation, and clinical applications, with broad development prospects in the future.</p>

                <p><em>Note: This review is based on basic analysis of {len(papers)} papers. It is recommended to conduct in-depth analysis based on specific research needs.</em></p>
                """
            else:
                review = f"""
                <h1>{topic} - 文献综述</h1>

                <h2>摘要</h2>
                <p>本综述基于{len(papers)}篇相关文献，对{topic}领域的研究现状、发展趋势和未来方向进行了全面分析。</p>

                <h2>引言</h2>
                <p>{topic}是当前研究的热点领域，相关研究不断涌现。通过系统分析相关文献，可以更好地了解该领域的发展脉络和研究重点。</p>

                <h2>研究现状</h2>
                <p>基于{len(papers)}篇文献的分析，当前{topic}领域的研究主要集中在以下几个方面：</p>
                <ul>
                    <li>基础理论研究</li>
                    <li>技术方法创新</li>
                    <li>临床应用验证</li>
                    <li>效果评估与优化</li>
                </ul>

                <h2>发展趋势</h2>
                <p>该领域正朝着精准化、个性化和智能化方向发展，跨学科融合趋势明显。</p>

                <h2>结论与展望</h2>
                <p>基于当前文献分析，{topic}领域在理论研究、技术创新和临床应用方面都取得了显著进展，未来仍有广阔的发展空间。</p>

                <p><em>注：本综述基于{len(papers)}篇文献的基础分析，建议结合具体研究需求进行深入分析。</em></p>
                """
        
        if not review:
            review = f"基于{len(papers)}篇文献的{topic}综述，涵盖研究现状、发展趋势和未来方向。"
        
        # 存储到session中供新页面使用 - DEPRECATED: 使用异步API替代
        # session['full_review_result'] = {
        #     'content': review,
        #     'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        #     'paper_count': len(papers),
        #     'search_query': topic,
        #     'loading': False,
        #     'error': None
        # }
        
        return jsonify({
            'success': True,
            'review': review,
            'redirect_url': '/analysis/full_review'
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'generate_full_review')), 500


@api_bp.route('/search_paper', methods=['POST'])
def search_paper():
    """搜索单篇文献 - 用于文献追踪功能"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        query = data.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400

        logger.info(f"Searching paper for tracking: {query}")

        # 判断输入类型
        paper_info = None

        # 检查是否为PMID (纯数字)
        if query.isdigit():
            logger.info(f"Searching by PMID: {query}")
            try:
                papers = pubmed_service.fetch_paper_details([query])
                if papers:
                    paper_info = papers[0]
            except Exception as e:
                logger.error(f"PMID search failed: {e}")

        # 检查是否为DOI
        elif query.startswith('10.') and '/' in query:
            logger.info(f"Searching by DOI: {query}")
            try:
                # 使用DOI搜索
                pmids, _ = pubmed_service.search_papers(f'"{query}"[DOI]', max_results=1)
                if pmids:
                    papers = pubmed_service.fetch_paper_details(pmids)
                    if papers:
                        paper_info = papers[0]
            except Exception as e:
                logger.error(f"DOI search failed: {e}")

        # 按标题搜索
        if not paper_info:
            logger.info(f"Searching by title: {query}")
            try:
                pmids, _ = pubmed_service.search_papers(f'"{query}"[Title]', max_results=5)
                if pmids:
                    papers = pubmed_service.fetch_paper_details(pmids)
                    if papers:
                        # 选择最相关的文献（第一个）
                        paper_info = papers[0]
            except Exception as e:
                logger.error(f"Title search failed: {e}")

        # 如果还是没找到，尝试一般搜索
        if not paper_info:
            logger.info(f"Fallback general search: {query}")
            try:
                pmids, _ = pubmed_service.search_papers(query, max_results=1)
                if pmids:
                    papers = pubmed_service.fetch_paper_details(pmids)
                    if papers:
                        paper_info = papers[0]
            except Exception as e:
                logger.error(f"General search failed: {e}")

        if paper_info:
            return jsonify({
                'success': True,
                'paper': paper_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Paper not found'
            })

    except Exception as e:
        logger.error(f"Error in search_paper: {str(e)}")
        return jsonify(handle_api_error(e, 'search_paper')), 500


@api_bp.route('/recommend_representative_papers', methods=['POST'])
def recommend_representative_papers():
    """Recommend representative papers - 兼容原版本API."""
    try:
        data = request.get_json() or {}
        
        # 原版本参数: papers
        # 新版本参数: papers, data
        papers = data.get('papers', [])
        criteria = data.get('criteria', 'impact_and_novelty')
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        logger.info(f"Recommending representative papers from {len(papers)} papers")
        
        recommendations = deepseek_service.recommend_representative_papers(papers, criteria)
        
        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'structured_papers': papers  # 修正：返回papers数组而不是recommendations字符串
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/precise_literature_search', methods=['POST'])
def precise_literature_search():
    """Precisely filter papers based on requirements - 兼容原版本API."""
    try:
        data = request.get_json() or {}
        
        # 兼容原版本参数: top_papers, search_requirement, papers
        top_papers = data.get('top_papers', [])
        search_requirement = data.get('search_requirement', '').strip()
        papers = data.get('papers', top_papers)  # 新版本用papers，原版本用top_papers
        requirements = data.get('requirements', search_requirement).strip()  # 新版本用requirements，原版本用search_requirement
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        if not requirements:
            return jsonify({'success': False, 'error': 'Requirements are required'}), 400
        
        logger.info(f"Precise filtering of {len(papers)} papers with requirements: {requirements[:50]}...")
        
        filtered_results = deepseek_service.precise_literature_search(papers, requirements)
        
        return jsonify({
            'success': True,
            'analysis': filtered_results,
            'structured_papers': papers,  # 修正：返回原始papers数组而不是字符串
            'filtered_results': filtered_results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# @api_bp.route('/export/excel', methods=['POST'])  # 移动到export_routes.py
def export_excel():
    """导出Excel文件API端点 - 兼容原版本"""
    try:
        data = request.get_json() or {}
        # 兼容原版本：data参数可选
        
        # 兼容原版本参数: query (从缓存获取数据)
        # 同时支持新版本参数: papers, filename
        query = data.get('query', '').strip()
        papers = data.get('papers', [])
        filename = data.get('filename')
        include_metrics = data.get('include_metrics', True)
        
        # 获取会话ID（原版本兼容）
        session_id = data.get('session_id', '') or request.headers.get('session_id', '') or request.headers.get('sid', '') or session.get('session_id')
        
        # 如果没有直接提供papers，尝试从缓存获取（原版本行为）
        if not papers and session_id:
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)
            if cached_data:
                # 根据data_type决定使用初始数据还是筛选后数据
                data_type = data.get('data_type', 'filtered')
                if data_type == 'initial' and 'original_papers' in cached_data:
                    papers = cached_data['original_papers']
                else:
                    papers = cached_data['papers']  # 默认使用筛选后的数据
                if not query:
                    query = cached_data['query']
            else:
                return jsonify({'error': '文献数据不存在，请重新检索'}), 404
        
        if not papers:
            return jsonify({'error': '无效的会话ID或缺少文献数据'}), 400
        
        logger.info(f"Exporting {len(papers)} papers to Excel")
        
        # 尝试使用导出服务
        try:
            file_path, generated_filename = export_service.export_to_excel(
                papers, filename, include_metrics
            )
            
            # 兼容原版本返回格式 - 直接返回文件而不是JSON
            from flask import send_file
            from io import BytesIO
            import os
            
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                
                excel_buffer = BytesIO(file_content)
                excel_buffer.seek(0)
                
                return send_file(
                    excel_buffer,
                    as_attachment=True,
                    download_name=generated_filename or 'export.xlsx',
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                
        except Exception as export_error:
            logger.error(f"Export service failed: {export_error}")
            
            # 备用导出方法：生成简单的Excel文件
            try:
                import pandas as pd
                from io import BytesIO
                from datetime import datetime
                import re
                
                # 准备数据
                data_for_excel = []
                for paper in papers:
                    journal_info = paper.get('journal_info', {})
                    paper_data = {
                        '标题': paper.get('title', ''),
                        '摘要': paper.get('abstract', ''),
                        '作者': ', '.join(paper.get('authors', [])),
                        '发表年份': paper.get('pub_year', ''),
                        '期刊名称': journal_info.get('title', '') or paper.get('journal', ''),
                        '影响因子': journal_info.get('impact_factor', 'N/A'),
                        'JCR分区': journal_info.get('jcr_quartile', 'N/A'),
                        'CAS分区': journal_info.get('cas_quartile', 'N/A'),
                        '关键词': ', '.join(paper.get('keywords', [])),
                        'DOI': paper.get('doi', ''),
                        'PMID': paper.get('pmid', ''),
                        '相关度': f"{paper.get('relevance', 0):.1f}%" if paper.get('relevance') else 'N/A'
                    }
                    data_for_excel.append(paper_data)
                
                # 创建DataFrame
                df = pd.DataFrame(data_for_excel)
                
                # 生成文件名
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_query = re.sub(r'[^\w\u4e00-\u9fff]', '_', query) if query else 'papers'
                if len(safe_query) > 50:
                    safe_query = safe_query[:50]
                generated_filename = f'papers_{safe_query}_{timestamp}.xlsx'
                
                # 创建BytesIO对象
                excel_buffer = BytesIO()
                df.to_excel(excel_buffer, index=False, engine='openpyxl')
                excel_buffer.seek(0)
                
                return send_file(
                    excel_buffer,
                    as_attachment=True,
                    download_name=generated_filename,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                
            except Exception as fallback_error:
                logger.error(f"Fallback export failed: {fallback_error}")
                return jsonify({'error': '生成Excel文件失败'}), 500
        
    except Exception as e:
        logger.error(f"导出Excel文件时发生错误: {str(e)}")
        return jsonify({'error': str(e)}), 500


# @api_bp.route('/export/word', methods=['POST'])  # 移动到export_routes.py
def export_word():
    """Export papers to Word format - 兼容原版本API."""
    try:
        data = request.get_json() or {}
        
        # 兼容原版本参数: session_id
        session_id = data.get('session_id', '') or request.headers.get('session_id', '') or request.headers.get('sid', '') or session.get('session_id')
        
        # 新版本参数: papers, filename, data
        papers = data.get('papers', [])
        title = data.get('title', 'Literature Review')
        filename = data.get('filename')
        include_abstracts = data.get('include_abstracts', True)
        
        # 如果没有直接提供 papers，尝试从缓存获取（原版本行为）
        if not papers and session_id:
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)
            if cached_data:
                # 根据data_type决定使用初始数据还是筛选后数据
                data_type = data.get('data_type', 'filtered')
                if data_type == 'initial' and 'original_papers' in cached_data:
                    papers = cached_data['original_papers']
                else:
                    papers = cached_data['papers']  # 默认使用筛选后的数据
        
        if not papers:
            return jsonify({'error': '没有文献数据用于导出，请先进行文献检索'}), 400
        
        logger.info(f"Exporting {len(papers)} papers to Word")
        
        file_path, filename = export_service.export_to_word(
            papers, title, filename, include_abstracts
        )
        
        # Update session export count
        user_session = get_current_session()
        if user_session:
            user_session.total_exports += 1
        
        return jsonify({
            'success': True,
            'filename': filename,
            'file_path': file_path,
            'paper_count': len(papers),
            'download_url': f'/download/{session.get("session_id", "unknown")}/word'
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'export_word')), 500


@api_bp.route('/analyze-journal', methods=['POST'])
def analyze_journal():
    """期刊分析API端点 - 完全复制原版本实现"""
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
        try:
            articles = analyzer.fetch_journal_articles(base_query)
        except Exception as e:
            logger.error(f"期刊分析数据获取失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'数据获取失败: {str(e)}'
            }), 500
        
        if not articles:
            return jsonify({
                'success': False,
                'error': '未找到相关文章，请尝试调整检索条件'
            }), 200  # 改为200，因为这是正常的查询结果
            
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
        logger.info(f"趋势数据: {len(trend_data.get('topics', []))} 年")
        logger.info(f"热点作者: {len(hot_authors)} 位")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"期刊分析失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'分析失败: {str(e)}'
        }), 500


@api_bp.route('/messages', methods=['GET'])
def get_messages():
    """Get chat message history."""
    try:
        user_session = get_current_session()
        if not user_session:
            return jsonify({'success': False, 'error': 'No active session'}), 400
        
        # Get recent searches as "messages"
        recent_searches = user_session.get_recent_searches(10)
        
        messages = []
        for search in recent_searches:
            messages.append({
                'type': 'search',
                'query': search['query'],
                'timestamp': search['timestamp'],
                'result_count': search['count']
            })
        
        return jsonify({
            'success': True,
            'messages': messages,
            'session_id': user_session.session_id
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'get_messages')), 500


@api_bp.route('/session', methods=['DELETE'])
def clear_session():
    """Clear current session."""
    try:
        session_id = session.get('session_id')
        if session_id:
            session_manager.remove_session(session_id)
            session.clear()
        
        # Create new session
        new_session = session_manager.create_session()
        session['session_id'] = new_session.session_id
        
        logger.info(f"Session cleared, new session: {new_session.session_id}")
        
        return jsonify({
            'success': True,
            'message': 'Session cleared',
            'new_session_id': new_session.session_id
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'clear_session')), 500


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get application statistics."""
    try:
        # Get various statistics
        session_stats = session_manager.get_statistics()
        cache_stats = get_cache_stats()
        journal_stats = journal_db.get_statistics()
        export_stats = export_service.get_export_statistics()
        
        # Service status
        service_status = {
            'pubmed': pubmed_service.get_service_status(),
            'deepseek': deepseek_service.get_service_status(),
            'embedding': embedding_service.get_service_status()
        }
        
        stats = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'sessions': session_stats,
            'cache': cache_stats,
            'journals': journal_stats,
            'exports': export_stats,
            'services': service_status
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'get_stats')), 500


@api_bp.route('/cache/cleanup', methods=['POST'])
def cleanup_cache():
    """Clean up application cache."""
    try:
        # Only allow in debug mode or with admin privileges
        if not config.DEBUG:
            return jsonify({'success': False, 'error': 'Not authorized'}), 403
        
        cleaned_entries = cleanup_global_cache()
        
        logger.info(f"Cache cleanup completed: {cleaned_entries} entries removed")
        
        return jsonify({
            'success': True,
            'cleaned_entries': cleaned_entries,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'cleanup_cache')), 500


# Error handlers for API blueprint
@api_bp.errorhandler(400)
def bad_request(error):
    return jsonify({
        'success': False,
        'error': 'Bad request',
        'message': str(error),
        'timestamp': datetime.now().isoformat()
    }), 400


@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'timestamp': datetime.now().isoformat()
    }), 404


@api_bp.errorhandler(500)
def internal_server_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'timestamp': datetime.now().isoformat()
    }), 500


# Before request handler for API
@api_bp.before_request
def before_api_request():
    """Handle operations before each API request."""
    # Log API requests
    logger.debug(f"API Request: {request.method} {request.endpoint}")
    
    # Ensure JSON content type for POST requests
    if request.method == 'POST' and not request.is_json:
        logger.warning(f"Non-JSON POST request to {request.endpoint}")


# After request handler for API
@api_bp.after_request
def after_api_request(response):
    """Handle operations after each API request."""
    # Log response status
    if response.status_code >= 400:
        logger.warning(f"API Error Response: {response.status_code} for {request.endpoint}")
    
    # Add API-specific headers
    response.headers['Content-Type'] = 'application/json'
    
    return response


@api_bp.route('/suggest_further_search', methods=['POST'])
def suggest_further_search():
    """建议进一步检索功能"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': '请提供研究方向'}), 400
        
        logger.info(f"Building further search suggestions for: {query}")
        
        # 从缓存中获取文献数据（兼容前端调用）
        papers = data.get('papers', [])
        if not papers:
            session_id = request.headers.get('sid') or session.get('session_id')
            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    papers = cached_data.get('papers', [])
                    if not query:
                        query = cached_data.get('query', query)
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        # 分析当前检索结果的前50篇文献
        titles = [paper.get('title', '') for paper in papers[:50]]
        
        prompt = f"""
基于当前检索到的{len(papers)}篇文献（查询："{query}"），请分析并提供进一步精准检索的建议：

当前检索结果的代表性文献标题：
{chr(10).join([f"{i+1}. {title}" for i, title in enumerate(titles[:20])])}

请按以下格式提供建议：

## 🔍 进一步检索建议

### 📊 当前检索结果分析：
- 文献数量：{len(papers)}篇
- 主要研究方向：[分析主要研究方向]
- 覆盖范围：[评估覆盖的研究范围]

### 🎯 精准检索建议：

#### 1. 细化检索策略
- **更具体的关键词组合**：[建议具体的关键词]
- **时间范围调整**：[建议合适的时间范围]
- **研究类型筛选**：[建议关注的研究类型]

#### 2. 扩展检索方向
- **相关子领域**：[建议探索的相关领域]
- **交叉学科**：[建议的交叉研究方向]
- **新兴技术应用**：[相关的新技术或方法]

#### 3. 具体检索建议
- **PubMed检索式**：[提供具体的检索式]
- **筛选条件**：[建议的筛选条件]
- **期刊范围**：[建议关注的期刊类型]

### 💡 检索优化提示：
- 如何提高检索精准度
- 如何避免遗漏重要文献
- 如何平衡查全率和查准率
"""
        
        # 使用AI服务生成建议
        suggestions = deepseek_service.generate_search_suggestions(query, titles, len(papers))
        
        return jsonify({
            'success': True,
            'suggestions': suggestions,
            'query': query,
            'analyzed_papers': len(papers)
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'suggest_further_search')), 500


@api_bp.route('/analyze_research_frontiers', methods=['POST'])
def analyze_research_frontiers():
    """分析前沿研究方向"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': '请提供研究方向'}), 400
        
        logger.info(f"Analyzing research frontiers for: {query}")
        
        # 从缓存中获取文献数据（兼容前端调用）
        papers = data.get('papers', [])
        if not papers:
            session_id = request.headers.get('sid') or session.get('session_id')
            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    papers = cached_data.get('papers', [])
                    if not query:
                        query = cached_data.get('query', query)
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        # 分析最新的文献（按年份排序）
        recent_papers = sorted(papers, key=lambda x: x.get('pub_date', '')[:4] if x.get('pub_date') else '0', reverse=True)[:30]
        
        # 使用AI服务分析前沿趋势
        analysis = deepseek_service.analyze_research_frontiers(query, recent_papers)
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'query': query,
            'analyzed_papers': len(recent_papers)
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'analyze_research_frontiers')), 500


@api_bp.route('/identify_research_gaps', methods=['POST'])
def identify_research_gaps():
    """识别研究空白与机会"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': '请提供研究方向'}), 400
        
        logger.info(f"Identifying research gaps for: {query}")
        
        # 从缓存中获取文献数据（兼容前端调用）
        papers = data.get('papers', [])
        if not papers:
            session_id = request.headers.get('sid') or session.get('session_id')
            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    papers = cached_data.get('papers', [])
                    if not query:
                        query = cached_data.get('query', query)
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        # 使用AI服务识别研究空白
        gaps_analysis = deepseek_service.identify_research_gaps(query, papers)
        
        return jsonify({
            'success': True,
            'analysis': gaps_analysis,
            'query': query,
            'analyzed_papers': len(papers)
        })
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'identify_research_gaps')), 500


@api_bp.route('/deepseek_analysis', methods=['POST'])
def deepseek_analysis():
    """Handle DeepSeek analysis requests for expert consultations."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        prompt = data.get('prompt')
        expert_type = data.get('expert_type', '专家')

        if not prompt:
            return jsonify({'success': False, 'error': 'Prompt is required'}), 400

        logger.info(f"开始{expert_type}分析")

        # 调用DeepSeek API进行分析
        messages = [
            {"role": "system", "content": f"你是一位专业的{expert_type}，具有丰富的专业知识和实践经验。请提供详细、专业、实用的建议。"},
            {"role": "user", "content": prompt}
        ]

        response = deepseek_service._make_request(messages, temperature=0.3, max_tokens=4000)
        analysis_result = deepseek_service._extract_response_content(response)

        if not analysis_result:
            return jsonify({'success': False, 'error': 'AI分析返回空结果'}), 500

        logger.info(f"{expert_type}分析完成")

        return jsonify({
            'success': True,
            'analysis': analysis_result,
            'expert_type': expert_type,
            'generated_at': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"DeepSeek分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/test-keywords', methods=['POST'])
def test_keywords():
    """测试关键词提取功能"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': '请提供检索词'}), 400
        
        logger.info(f"Testing keyword extraction for: {query}")
        
        # 首先尝试从PubMed搜索获取文章
        pmids, total_count = pubmed_service.search_papers(query, 50)
        
        if not pmids:
            return jsonify({
                'success': False,
                'error': '未找到相关文章'
            }), 404
        
        # 获取文章详情
        papers = pubmed_service.fetch_paper_details_batch(pmids)
        
        if not papers:
            return jsonify({
                'success': False,
                'error': '未能获取文章详情'
            }), 404
        
        # 测试关键词提取
        from models.journal import journal_db
        test_results = journal_db.test_extract_keywords(papers)
        
        # 生成词云数据（仅使用关键词）
        wordcloud_data = journal_db.extract_keywords_from_papers(papers)[:50]  # 限制50个关键词
        
        # 准备返回数据
        response_data = {
            'success': True,
            'test_results': test_results,
            'wordcloud_data': wordcloud_data,
            'total_articles': len(papers),
            'query': query
        }
        
        logger.info(f"Keyword extraction test completed: {len(papers)} articles analyzed")
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify(handle_api_error(e, 'test_keywords')), 500


# =============================================================================
# 历史会话管理API
# =============================================================================

@api_bp.route('/sessions', methods=['GET'])
def get_sessions():
    """获取所有历史会话列表"""
    try:
        cache = get_papers_cache()
        sessions = cache.get_all_sessions()

        return jsonify({
            'success': True,
            'sessions': sessions,
            'total': len(sessions)
        })

    except Exception as e:
        logger.exception("Failed to get sessions")
        return jsonify(handle_api_error(e, 'get_sessions')), 500


@api_bp.route('/sessions/<session_id>', methods=['GET'])
def get_session_details(session_id):
    """获取指定会话的详细信息"""
    try:
        cache = get_papers_cache()
        session_data = cache.get_papers(session_id)

        if not session_data:
            return jsonify({
                'success': False,
                'error': '会话不存在或已过期'
            }), 404

        return jsonify({
            'success': True,
            'session_id': session_id,
            'data': session_data
        })

    except Exception as e:
        logger.exception(f"Failed to get session details for {session_id}")
        return jsonify(handle_api_error(e, 'get_session_details')), 500


@api_bp.route('/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除指定会话"""
    try:
        cache = get_papers_cache()
        success = cache.remove_session(session_id)

        if success:
            return jsonify({
                'success': True,
                'message': '会话已删除'
            })
        else:
            return jsonify({
                'success': False,
                'error': '会话不存在'
            }), 404

    except Exception as e:
        logger.exception(f"Failed to delete session {session_id}")
        return jsonify(handle_api_error(e, 'delete_session')), 500


@api_bp.route('/sessions/<session_id>/restore', methods=['POST'])
def restore_session(session_id):
    """恢复指定会话到当前会话"""
    try:
        cache = get_papers_cache()
        session_data = cache.get_papers(session_id)

        if not session_data:
            return jsonify({
                'success': False,
                'error': '会话不存在或已过期'
            }), 404

        # 将会话数据设置为当前会话
        session['session_id'] = session_id

        return jsonify({
            'success': True,
            'message': '会话已恢复',
            'session_id': session_id,
            'data': session_data
        })

    except Exception as e:
        logger.exception(f"Failed to restore session {session_id}")
        return jsonify(handle_api_error(e, 'restore_session')), 500


# =============================================================================
# 异步任务相关API
# =============================================================================

@api_bp.route('/async/review_topic_suggestion', methods=['POST'])
def start_review_topic_analysis():
    """启动综述选题建议异步任务"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query', '').strip()
        session_id = request.headers.get('sid') or session.get('session_id')
        
        # 详细的session调试日志
        logger.info(f"Review topic async API - Headers sid: {request.headers.get('sid')}")
        logger.info(f"Review topic async API - Flask session id: {session.get('session_id')}")
        logger.info(f"Review topic async API - Final session_id: {session_id}")
        logger.info(f"Review topic async API - Query: '{query}'")
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID is required'}), 400
        
        # 验证是否有文献数据
        cache = get_papers_cache()
        logger.info(f"Review topic async API - Checking cache for session: {session_id}")
        cached_data = cache.get_papers(session_id)
        logger.info(f"Review topic async API - Cache check result: cached_data={cached_data is not None}")
        
        if cached_data:
            papers_count = len(cached_data.get('papers', []))
            logger.info(f"Review topic async API - Found {papers_count} papers in cache")
        else:
            logger.warning(f"Review topic async API - No papers found in cache for session: {session_id}")
            
        if not cached_data or not cached_data.get('papers'):
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        # 创建异步任务
        task_service = get_async_task_service()
        task_data = {
            'query': query,
            'session_id': session_id
        }
        
        task_id = task_service.create_task('review_topic_analysis', task_data)
        
        logger.info(f"Started review topic analysis task: {task_id}")
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '综述选题建议分析任务已启动',
            'status_url': f'/api/async/task/{task_id}/status',
            'estimated_time': '30-60秒'
        })
        
    except Exception as e:
        logger.exception("Failed to start review topic analysis")
        return jsonify(handle_api_error(e, 'start_review_topic_analysis')), 500


@api_bp.route('/async/research_topic_suggestion', methods=['POST'])
def start_research_topic_analysis():
    """启动论著选题建议异步任务"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        query = data.get('query', '').strip()
        session_id = request.headers.get('sid') or session.get('session_id')
        
        # 详细的session调试日志
        logger.info(f"Research topic async API - Headers sid: {request.headers.get('sid')}")
        logger.info(f"Research topic async API - Flask session id: {session.get('session_id')}")
        logger.info(f"Research topic async API - Final session_id: {session_id}")
        logger.info(f"Research topic async API - Query: '{query}'")
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID is required'}), 400
        
        # 验证是否有文献数据
        cache = get_papers_cache()
        logger.info(f"Research topic async API - Checking cache for session: {session_id}")
        cached_data = cache.get_papers(session_id)
        logger.info(f"Research topic async API - Cache check result: cached_data={cached_data is not None}")
        
        if cached_data:
            papers_count = len(cached_data.get('papers', []))
            logger.info(f"Research topic async API - Found {papers_count} papers in cache")
        else:
            logger.warning(f"Research topic async API - No papers found in cache for session: {session_id}")
            
        if not cached_data or not cached_data.get('papers'):
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        # 创建异步任务
        task_service = get_async_task_service()
        task_data = {
            'query': query,
            'session_id': session_id
        }
        
        task_id = task_service.create_task('research_topic_analysis', task_data)
        
        logger.info(f"Started research topic analysis task: {task_id}")
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '论著选题建议分析任务已启动',
            'status_url': f'/api/async/task/{task_id}/status',
            'estimated_time': '30-60秒'
        })
        
    except Exception as e:
        logger.exception("Failed to start research topic analysis")
        return jsonify(handle_api_error(e, 'start_research_topic_analysis')), 500


@api_bp.route('/async/generate_full_review', methods=['POST'])
def start_full_review_generation():
    """启动完整综述生成异步任务"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        query = data.get('query', '').strip()
        user_title = data.get('user_title', '').strip()  # 用户自定义题目
        session_id = request.headers.get('sid') or session.get('session_id')
        review_type = data.get('review_type', 'narrative')

        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400

        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID is required'}), 400

        # 验证是否有文献数据
        cache = get_papers_cache()
        cached_data = cache.get_papers(session_id)
        if not cached_data or not cached_data.get('papers'):
            return jsonify({'success': False, 'error': 'Papers are required'}), 400

        # 创建异步任务
        task_service = get_async_task_service()
        task_data = {
            'query': query,
            'user_title': user_title,
            'session_id': session_id,
            'review_type': review_type
        }

        task_id = task_service.create_task('full_review_generation', task_data)

        logger.info(f"Started advanced full review generation task: {task_id}")

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '高级综述生成任务已启动',
            'status_url': f'/api/async/task/{task_id}/status',
            'estimated_time': '120-300秒'
        })

    except Exception as e:
        logger.exception("Failed to start full review generation")
        return jsonify(handle_api_error(e, 'start_full_review_generation')), 500


@api_bp.route('/export/review_word', methods=['POST'])
def export_review_to_word():
    """导出综述为Word文档"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        review_data = data.get('review_data')
        if not review_data:
            return jsonify({'success': False, 'error': 'Review data is required'}), 400

        # 导入Word导出服务
        from services.word_export_service import word_export_service

        # 导出Word文档
        filepath = word_export_service.export_review_to_word(review_data)

        # 读取文件内容
        with open(filepath, 'rb') as f:
            file_content = f.read()

        # 删除临时文件
        import os
        os.remove(filepath)

        # 返回文件
        from flask import make_response
        response = make_response(file_content)
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        response.headers['Content-Disposition'] = f'attachment; filename="{review_data.get("title", "综述")}.docx"'

        return response

    except Exception as e:
        logger.exception("Failed to export review to Word")
        return jsonify(handle_api_error(e, 'export_review_to_word')), 500


@api_bp.route('/literature_tracking/generate_network', methods=['POST'])
def generate_literature_network():
    """生成文献网络图谱"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        seed_paper_id = data.get('seed_paper_id')
        session_id = request.headers.get('sid') or session.get('session_id')

        if not seed_paper_id:
            return jsonify({'success': False, 'error': 'Seed paper ID is required'}), 400

        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID is required'}), 400

        # 获取缓存中的文献数据
        cache = get_papers_cache()
        cached_data = cache.get_papers(session_id)

        if not cached_data or not cached_data.get('papers'):
            # 如果没有缓存数据，创建一个包含种子文献的临时数据集
            logger.warning(f"No cached papers found for session {session_id}, creating temporary dataset with seed paper")

            # 尝试通过种子文献ID获取文献信息
            try:
                from services.pubmed_service import pubmed_service

                # 如果seed_paper_id是PMID
                if seed_paper_id.isdigit():
                    papers = pubmed_service.fetch_paper_details([seed_paper_id])
                else:
                    # 如果是标题，搜索获取
                    pmids = pubmed_service.search_papers(f'"{seed_paper_id}"[Title]', max_results=1)
                    if pmids:
                        papers = pubmed_service.fetch_paper_details(pmids)
                    else:
                        return jsonify({'success': False, 'error': 'Could not find the seed paper'}), 404

                if not papers:
                    return jsonify({'success': False, 'error': 'Could not retrieve seed paper details'}), 404

            except Exception as e:
                logger.error(f"Error retrieving seed paper: {e}")
                # 如果网络请求失败，创建一个模拟的种子文献用于演示
                logger.info("Creating demo seed paper due to network issues")
                papers = [{
                    'pmid': seed_paper_id if seed_paper_id.isdigit() else '12345678',
                    'title': seed_paper_id if not seed_paper_id.isdigit() else 'Demo Paper Title',
                    'authors': ['Demo Author'],
                    'journal': 'Demo Journal',
                    'year': '2023',
                    'abstract': 'This is a demo paper created due to network connectivity issues.',
                    'impact_factor': '5.0',
                    'jcr_quartile': 'Q1'
                }]
        else:
            papers = cached_data['papers']

        # 找到种子文献
        seed_paper = None
        for paper in papers:
            if str(paper.get('pmid', '')) == str(seed_paper_id) or \
               paper.get('title', '').strip().lower() == seed_paper_id.lower():
                seed_paper = paper
                break

        if not seed_paper:
            return jsonify({'success': False, 'error': 'Seed paper not found'}), 404

        # 生成文献网络图
        from services.literature_tracking_service import literature_tracking_service

        result = literature_tracking_service.generate_citation_network(seed_paper, papers)

        if result['success']:
            logger.info(f"Literature network generated successfully for paper: {seed_paper.get('title', '')}")
            return jsonify(result)
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.exception("Failed to generate literature network")
        return jsonify(handle_api_error(e, 'generate_literature_network')), 500


@api_bp.route('/literature_tracking/get_citations', methods=['POST'])
def get_literature_citations():
    """获取文献的真实引用关系"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        paper_info = data.get('paper')
        if not paper_info:
            return jsonify({'success': False, 'error': 'No paper information provided'}), 400

        logger.info(f"获取文献引用关系: {paper_info.get('title', '')}")

        # 使用文献追踪服务获取真实引用数据
        from services.literature_tracking_service import literature_tracking_service
        citation_data = literature_tracking_service.get_real_citations(paper_info)

        result = {
            'success': True,
            'paper': paper_info,
            'references': citation_data.get('references', []),
            'citations': citation_data.get('citations', []),
            'statistics': {
                'reference_count': len(citation_data.get('references', [])),
                'citation_count': len(citation_data.get('citations', []))
            }
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"获取文献引用关系失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/literature_tracking/prior_works/<paper_id>', methods=['GET'])
def get_prior_works(paper_id):
    """获取祖先文献"""
    try:
        session_id = request.headers.get('sid') or session.get('session_id')

        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID is required'}), 400

        # 获取缓存中的文献数据
        cache = get_papers_cache()
        cached_data = cache.get_papers(session_id)

        if not cached_data or not cached_data.get('papers'):
            return jsonify({'success': False, 'error': 'No papers found in session'}), 400

        papers = cached_data['papers']

        # 找到目标文献
        target_paper = None
        for paper in papers:
            if str(paper.get('pmid', '')) == str(paper_id) or \
               paper.get('title', '').strip().lower() == paper_id.lower():
                target_paper = paper
                break

        if not target_paper:
            return jsonify({'success': False, 'error': 'Paper not found'}), 404

        # 分析祖先文献
        from services.literature_tracking_service import literature_tracking_service

        papers_index = literature_tracking_service._build_papers_index(papers)
        prior_works = literature_tracking_service._analyze_prior_works(target_paper, papers_index)

        return jsonify({
            'success': True,
            'paper': target_paper,
            'prior_works': prior_works,
            'count': len(prior_works)
        })

    except Exception as e:
        logger.exception("Failed to get prior works")
        return jsonify(handle_api_error(e, 'get_prior_works')), 500


@api_bp.route('/literature_tracking/derivative_works/<paper_id>', methods=['GET'])
def get_derivative_works(paper_id):
    """获取后代文献"""
    try:
        session_id = request.headers.get('sid') or session.get('session_id')

        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID is required'}), 400

        # 获取缓存中的文献数据
        cache = get_papers_cache()
        cached_data = cache.get_papers(session_id)

        if not cached_data or not cached_data.get('papers'):
            return jsonify({'success': False, 'error': 'No papers found in session'}), 400

        papers = cached_data['papers']

        # 找到目标文献
        target_paper = None
        for paper in papers:
            if str(paper.get('pmid', '')) == str(paper_id) or \
               paper.get('title', '').strip().lower() == paper_id.lower():
                target_paper = paper
                break

        if not target_paper:
            return jsonify({'success': False, 'error': 'Paper not found'}), 404

        # 分析后代文献
        from services.literature_tracking_service import literature_tracking_service

        papers_index = literature_tracking_service._build_papers_index(papers)
        derivative_works = literature_tracking_service._analyze_derivative_works(target_paper, papers_index)

        return jsonify({
            'success': True,
            'paper': target_paper,
            'derivative_works': derivative_works,
            'count': len(derivative_works)
        })

    except Exception as e:
        logger.exception("Failed to get derivative works")
        return jsonify(handle_api_error(e, 'get_derivative_works')), 500


@api_bp.route('/async/task/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    """获取异步任务状态"""
    try:
        task_service = get_async_task_service()
        task_status = task_service.get_task_status(task_id)
        
        if not task_status:
            return jsonify({
                'success': False,
                'error': 'Task not found',
                'task_id': task_id
            }), 404
        
        # 如果任务已完成，将结果存储到分析缓存中
        if task_status['status'] == 'completed' and task_status['result']:
            result = task_status['result']
            analysis_type = result.get('analysis_type')
            
            if analysis_type and 'task_data' in task_status:
                # 从task_data获取session_id
                task_session_id = task_status['task_data'].get('session_id', '')
                if task_session_id:
                    # 存储到分析缓存中，可以跨session访问
                    from utils.analysis_cache import get_analysis_cache
                    cache = get_analysis_cache()
                    cache.store_result(task_session_id, analysis_type, result)
                    logger.info(f"Stored {analysis_type} result in analysis cache for session {task_session_id}: paper_count={result.get('paper_count')}")
                
                # 同时存储到Flask session中（向后兼容），但只存储关键信息
                session_key = f'{analysis_type}_result'
                # 对于reference_matching，只存储必要的数据以避免session过大
                if analysis_type == 'reference_matching':
                    # 只存储简化的数据
                    simplified_result = {
                        'analysis_type': result.get('analysis_type'),
                        'valid_count': result.get('valid_count', 0),
                        'invalid_count': result.get('invalid_count', 0),
                        'total_count': result.get('total_count', 0),
                        'generated_at': result.get('generated_at'),
                        'has_data': True  # 标记有数据，前端可以从cache获取完整数据
                    }
                    session[session_key] = simplified_result
                else:
                    session[session_key] = result
                session.permanent = True
                session.modified = True
                logger.info(f"Also stored {analysis_type} result in Flask session: paper_count={result.get('paper_count')}")
        
        return jsonify({
            'success': True,
            'task': task_status
        })
        
    except Exception as e:
        logger.exception(f"Failed to get task status for {task_id}")
        return jsonify(handle_api_error(e, 'get_task_status')), 500


@api_bp.route('/async/task/<task_id>/result', methods=['GET'])
def get_task_result(task_id):
    """获取异步任务结果"""
    try:
        task_service = get_async_task_service()
        task_status = task_service.get_task_status(task_id)
        
        if not task_status:
            return jsonify({
                'success': False,
                'error': 'Task not found',
                'task_id': task_id
            }), 404
        
        if task_status['status'] != 'completed':
            return jsonify({
                'success': False,
                'error': 'Task not completed yet',
                'status': task_status['status'],
                'progress': task_status['progress'],
                'message': task_status['message']
            }), 202
        
        result = task_status['result']
        if not result:
            return jsonify({
                'success': False,
                'error': 'No result available'
            }), 404
        
        # 存储结果到分析缓存并返回重定向URL
        analysis_type = result.get('analysis_type')
        if analysis_type:
            # 从task_status获取session_id
            task_session_id = ''
            if task_status and isinstance(task_status, dict) and 'task_data' in task_status:
                task_session_id = task_status['task_data'].get('session_id', '')
                
                if task_session_id:
                    # 存储到session缓存中
                    from utils.session_cache import get_papers_cache
                    cache = get_papers_cache()
                    cache.store_analysis_result(task_session_id, analysis_type, result)
                    logger.info(f"Stored {analysis_type} result in session cache via result API: session={task_session_id}, paper_count={result.get('paper_count')}")
            
            # 同时存储到Flask session中（向后兼容），但只存储关键信息
            session_key = f'{analysis_type}_result'
            # 对于reference_matching，只存储必要的数据以避免session过大
            if analysis_type == 'reference_matching':
                # 只存储简化的数据
                simplified_result = {
                    'analysis_type': result.get('analysis_type'),
                    'valid_count': result.get('valid_count', 0),
                    'invalid_count': result.get('invalid_count', 0),
                    'total_count': result.get('total_count', 0),
                    'generated_at': result.get('generated_at'),
                    'has_data': True  # 标记有数据，前端可以从cache获取完整数据
                }
                session[session_key] = simplified_result
            else:
                session[session_key] = result
            session.permanent = True
            session.modified = True
            logger.info(f"Also stored {analysis_type} result in Flask session via result API: paper_count={result.get('paper_count')}")
            
            # 在重定向URL中包含session ID
            current_session_id = task_session_id or session.get('session_id', '')
            redirect_url = f'/analysis/{analysis_type}'
            if current_session_id:
                redirect_url += f'?sid={current_session_id}'
                logger.info(f"Result API - Redirect URL with session ID: '{redirect_url}'")
            else:
                logger.warning(f"Result API - No session_id found, redirect URL: '{redirect_url}'")
            
            return jsonify({
                'success': True,
                'result': result,
                'redirect_url': redirect_url
            })
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        logger.exception(f"Failed to get task result for {task_id}")
        return jsonify(handle_api_error(e, 'get_task_result')), 500


@api_bp.route('/async/tasks/stats', methods=['GET'])
def get_async_tasks_stats():
    """获取异步任务统计信息"""
    try:
        task_service = get_async_task_service()
        stats = task_service.get_statistics()
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        logger.exception("Failed to get async tasks stats")
        return jsonify(handle_api_error(e, 'get_async_tasks_stats')), 500


@api_bp.route('/journal_selection', methods=['POST'])
def journal_selection():
    """AI投稿选刊功能API端点"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请提供论文信息'
            }), 400

        title = data.get('title', '').strip()
        abstract = data.get('abstract', '').strip()
        keywords = data.get('keywords', '').strip()
        field = data.get('field', '').strip()

        if not title or not abstract:
            return jsonify({
                'success': False,
                'error': '论文标题和摘要不能为空'
            }), 400

        logger.info(f"Starting journal selection analysis for title: {title[:50]}...")

        # 构建分析提示词
        analysis_prompt = f"""
作为顶级学术期刊编辑和投稿专家，请基于以下论文信息推荐最合适的期刊：

论文标题：{title}

论文摘要：{abstract}

关键词：{keywords if keywords else '未提供'}

研究领域：{field if field else '未指定'}

请为这篇论文推荐5个最合适的期刊，并按照以下JSON格式返回：

```json
[
    {{
        "name": "期刊全名",
        "publisher": "出版社",
        "impact_factor": "影响因子数值",
        "jcr_quartile": "JCR分区(Q1/Q2/Q3/Q4)",
        "cas_zone": "中科院分区(1区/2区/3区/4区)",
        "match_score": 匹配度百分比(80-95),
        "difficulty": "投稿难度(容易/中等/困难)",
        "reason": "推荐理由(100-150字)",
        "submission_tips": "投稿建议(100-150字)"
    }}
]
```

推荐要求：
1. 期刊必须与研究内容高度相关
2. 涵盖不同影响因子层次(高、中、低)
3. 考虑投稿成功率和发表周期
4. 提供具体的投稿建议
5. 确保期刊信息准确可靠

请只返回JSON格式的结果，不要包含其他文字。
"""

        # 调用DeepSeek API进行分析
        try:
            response = deepseek_service.chat_with_deepseek(analysis_prompt)

            if not response:
                raise Exception("AI分析服务返回空结果")

            # 解析JSON响应
            import json
            import re

            # 提取JSON部分
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 如果没有代码块，尝试直接解析
                json_str = response.strip()

            try:
                recommendations = json.loads(json_str)

                # 验证数据格式
                if not isinstance(recommendations, list):
                    raise ValueError("返回结果不是列表格式")

                # 确保每个推荐都有必要的字段
                for i, rec in enumerate(recommendations):
                    if not isinstance(rec, dict):
                        continue

                    # 设置默认值
                    rec.setdefault('name', f'期刊 {i+1}')
                    rec.setdefault('publisher', '未知出版社')
                    rec.setdefault('impact_factor', 'N/A')
                    rec.setdefault('jcr_quartile', 'N/A')
                    rec.setdefault('cas_zone', 'N/A')
                    rec.setdefault('match_score', 85)
                    rec.setdefault('difficulty', '中等')
                    rec.setdefault('reason', '该期刊与您的研究内容相关，具有良好的学术声誉。')
                    rec.setdefault('submission_tips', '建议仔细阅读期刊投稿指南，确保格式符合要求。')

                logger.info(f"Successfully analyzed journal recommendations: {len(recommendations)} journals")

                return jsonify({
                    'success': True,
                    'recommendations': recommendations
                })

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Raw response: {response}")

                # 如果JSON解析失败，返回一个默认的推荐
                default_recommendations = [
                    {
                        "name": "相关领域期刊推荐",
                        "publisher": "学术出版社",
                        "impact_factor": "待查询",
                        "jcr_quartile": "待确认",
                        "cas_zone": "待确认",
                        "match_score": 80,
                        "difficulty": "中等",
                        "reason": "基于您的研究内容，建议查询相关领域的专业期刊。",
                        "submission_tips": "建议进一步细化研究领域，以获得更精准的期刊推荐。"
                    }
                ]

                return jsonify({
                    'success': True,
                    'recommendations': default_recommendations,
                    'note': 'AI分析结果格式异常，已提供基础推荐'
                })

        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            return jsonify({
                'success': False,
                'error': f'AI分析服务暂时不可用: {str(e)}'
            }), 500

    except Exception as e:
        logger.error(f"Journal selection analysis failed: {e}")
        return jsonify(handle_api_error(e, 'journal_selection')), 500


@api_bp.route('/paper_translation', methods=['POST'])
def paper_translation():
    """论文翻译功能API端点"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请提供翻译内容'
            }), 400

        direction = data.get('direction', '').strip()
        translation_type = data.get('type', '').strip()
        content = data.get('content', '').strip()
        options = data.get('options', {})

        if not direction or not translation_type or not content:
            return jsonify({
                'success': False,
                'error': '翻译方向、类型和内容不能为空'
            }), 400

        logger.info(f"Starting paper translation: {direction}, type: {translation_type}")

        # 构建翻译提示词
        direction_text = "中文翻译成英文" if direction == 'zh-to-en' else "英文翻译成中文"
        type_text = {
            'title': '标题',
            'abstract': '摘要',
            'paragraph': '段落',
            'full-text': '全文'
        }.get(translation_type, translation_type)

        # 根据选项构建特殊要求
        special_requirements = []
        if options.get('preserve_terms'):
            special_requirements.append("保持专业术语的准确性")
        if options.get('academic_style'):
            special_requirements.append("使用学术写作风格")
        if options.get('format_preservation'):
            special_requirements.append("保持原文格式")

        requirements_text = "、".join(special_requirements) if special_requirements else "无特殊要求"

        translation_prompt = f"""
作为专业的学术翻译专家，请将以下{type_text}从{direction_text}。

翻译要求：
1. 保持学术论文的专业性和准确性
2. 确保专业术语翻译正确
3. 保持原文的逻辑结构和表达方式
4. 特殊要求：{requirements_text}

待翻译内容：
{content}

请直接提供翻译结果，不要包含任何解释或说明文字。
"""

        # 调用DeepSeek API进行翻译
        try:
            translation = deepseek_service.chat_with_deepseek(translation_prompt)

            if not translation:
                raise Exception("翻译服务返回空结果")

            # 清理翻译结果，移除可能的前缀说明
            translation = translation.strip()

            # 移除常见的前缀
            prefixes_to_remove = [
                "翻译结果：", "Translation:", "译文：", "结果：",
                "以下是翻译：", "翻译如下：", "Here is the translation:",
                "The translation is:"
            ]

            for prefix in prefixes_to_remove:
                if translation.startswith(prefix):
                    translation = translation[len(prefix):].strip()
                    break

            logger.info(f"Successfully completed paper translation: {len(translation)} characters")

            return jsonify({
                'success': True,
                'translation': translation,
                'direction': direction,
                'type': translation_type
            })

        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            return jsonify({
                'success': False,
                'error': f'翻译服务暂时不可用: {str(e)}'
            }), 500

    except Exception as e:
        logger.error(f"Paper translation failed: {e}")
        return jsonify(handle_api_error(e, 'paper_translation')), 500


@api_bp.route('/paper_polish', methods=['POST'])
def paper_polish():
    """论文润色功能API端点"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请提供润色内容'
            }), 400

        polish_type = data.get('type', '').strip()
        academic_field = data.get('field', '').strip()
        content = data.get('content', '').strip()
        focus_areas = data.get('focus_areas', {})

        if not polish_type or not content:
            return jsonify({
                'success': False,
                'error': '润色类型和内容不能为空'
            }), 400

        logger.info(f"Starting paper polish: type: {polish_type}, field: {academic_field}")

        # 构建润色提示词
        type_text = {
            'title': '标题',
            'abstract': '摘要',
            'introduction': '引言',
            'methods': '方法部分',
            'results': '结果部分',
            'discussion': '讨论部分',
            'conclusion': '结论',
            'paragraph': '段落',
            'full-paper': '全文'
        }.get(polish_type, polish_type)

        field_text = academic_field if academic_field else "通用学术"

        # 根据选择的重点构建润色要求
        focus_requirements = []
        if focus_areas.get('grammar_check'):
            focus_requirements.append("语法检查和纠正")
        if focus_areas.get('vocabulary_improvement'):
            focus_requirements.append("词汇提升和替换")
        if focus_areas.get('sentence_structure'):
            focus_requirements.append("句式结构优化")
        if focus_areas.get('academic_tone'):
            focus_requirements.append("学术语调调整")
        if focus_areas.get('logical_flow'):
            focus_requirements.append("逻辑流畅性改进")
        if focus_areas.get('clarity_improvement'):
            focus_requirements.append("表达清晰度提升")

        focus_text = "、".join(focus_requirements) if focus_requirements else "全面润色"

        polish_prompt = f"""
作为专业的学术英文编辑，请对以下{field_text}领域的{type_text}进行专业润色。

润色重点：{focus_text}

润色要求：
1. 保持原文的学术内容和核心观点不变
2. 改善语法、用词、句式结构
3. 提升表达的清晰度和专业性
4. 确保符合学术写作规范
5. 保持适当的学术语调

待润色内容：
{content}

请按照以下格式返回结果：

润色后文本：
[在这里提供润色后的完整文本]

主要改进：
[简要列出主要的改进点，包括语法修正、词汇替换、句式优化等]
"""

        # 调用DeepSeek API进行润色
        try:
            response = deepseek_service.chat_with_deepseek(polish_prompt)

            if not response:
                raise Exception("润色服务返回空结果")

            # 解析响应，分离润色后文本和改进说明
            polished_text = ""
            improvements = ""

            # 尝试解析结构化响应
            if "润色后文本：" in response and "主要改进：" in response:
                parts = response.split("主要改进：")
                if len(parts) >= 2:
                    polished_part = parts[0].replace("润色后文本：", "").strip()
                    improvements_part = parts[1].strip()

                    polished_text = polished_part
                    improvements = improvements_part
                else:
                    polished_text = response.strip()
            else:
                # 如果没有结构化格式，直接使用整个响应作为润色结果
                polished_text = response.strip()

            # 清理可能的前缀
            prefixes_to_remove = [
                "润色后文本：", "润色结果：", "Polished text:", "Result:",
                "以下是润色后的文本：", "润色后的内容如下："
            ]

            for prefix in prefixes_to_remove:
                if polished_text.startswith(prefix):
                    polished_text = polished_text[len(prefix):].strip()
                    break

            logger.info(f"Successfully completed paper polish: {len(polished_text)} characters")

            return jsonify({
                'success': True,
                'polished_text': polished_text,
                'improvements': improvements if improvements else None,
                'type': polish_type
            })

        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            return jsonify({
                'success': False,
                'error': f'润色服务暂时不可用: {str(e)}'
            }), 500

    except Exception as e:
        logger.error(f"Paper polish failed: {e}")
        return jsonify(handle_api_error(e, 'paper_polish')), 500


@api_bp.route('/ai_topic_selection', methods=['POST'])
def ai_topic_selection():
    """AI选题功能API端点"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请提供选题信息'
            }), 400

        domain = data.get('domain', '').strip()
        keywords = data.get('keywords', '').strip()
        background = data.get('background', '').strip()
        goal = data.get('goal', '').strip()
        preferences = data.get('preferences', {})

        if not domain:
            return jsonify({
                'success': False,
                'error': '研究领域不能为空'
            }), 400

        logger.info(f"Starting AI topic selection: domain: {domain}")

        # 构建选题提示词
        domain_text = {
            'medicine': '医学',
            'biology': '生物学',
            'chemistry': '化学',
            'physics': '物理学',
            'engineering': '工程学',
            'computer-science': '计算机科学',
            'materials': '材料科学',
            'environmental': '环境科学',
            'neuroscience': '神经科学',
            'biotechnology': '生物技术'
        }.get(domain, domain)

        goal_text = {
            'basic-research': '基础研究',
            'applied-research': '应用研究',
            'clinical-research': '临床研究',
            'technology-development': '技术开发',
            'review-analysis': '综述分析',
            'interdisciplinary': '跨学科研究'
        }.get(goal, goal) if goal else "不限"

        # 根据偏好构建要求
        preference_requirements = []
        if preferences.get('innovative'):
            preference_requirements.append("具有高创新性")
        if preferences.get('feasible'):
            preference_requirements.append("具有较高可行性")
        if preferences.get('hot'):
            preference_requirements.append("属于研究热点")
        if preferences.get('emerging'):
            preference_requirements.append("属于新兴方向")
        if preferences.get('practical'):
            preference_requirements.append("具有实用价值")
        if preferences.get('funding_friendly'):
            preference_requirements.append("容易获得资助")

        preference_text = "、".join(preference_requirements) if preference_requirements else "无特殊偏好"

        topic_prompt = f"""
作为资深的学术研究专家和科研导师，请基于以下信息为研究者推荐5个创新的研究选题。

研究领域：{domain_text}
关键词：{keywords if keywords else '未提供'}
研究背景：{background if background else '未提供'}
研究目标：{goal_text}
选题偏好：{preference_text}

请为每个选题提供以下信息，并按照JSON格式返回：

```json
[
    {{
        "title": "研究选题标题",
        "category": "具体研究分类",
        "description": "详细的研究描述(150-200字)",
        "innovation_score": 创新性评分(70-95),
        "feasibility_score": 可行性评分(70-95),
        "impact_score": 影响力评分(70-95),
        "difficulty": "研究难度(容易/中等/困难)",
        "research_methods": "建议的研究方法",
        "expected_outcomes": "预期研究成果",
        "challenges": "可能面临的挑战"
    }}
]
```

选题要求：
1. 确保选题具有学术价值和创新性
2. 考虑当前技术条件和研究环境的可行性
3. 关注该领域的前沿发展和未来趋势
4. 提供具体可操作的研究方向
5. 评估研究的潜在影响和应用价值

请只返回JSON格式的结果，不要包含其他文字。
"""

        # 调用DeepSeek API进行分析
        try:
            response = deepseek_service.chat_with_deepseek(topic_prompt)

            if not response:
                raise Exception("AI选题服务返回空结果")

            # 解析JSON响应
            import json
            import re

            # 提取JSON部分
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 如果没有代码块，尝试直接解析
                json_str = response.strip()

            try:
                topics = json.loads(json_str)

                # 验证数据格式
                if not isinstance(topics, list):
                    raise ValueError("返回结果不是列表格式")

                # 确保每个选题都有必要的字段
                for i, topic in enumerate(topics):
                    if not isinstance(topic, dict):
                        continue

                    # 设置默认值
                    topic.setdefault('title', f'研究选题 {i+1}')
                    topic.setdefault('category', '学术研究')
                    topic.setdefault('description', '这是一个有潜力的研究方向，值得深入探索。')
                    topic.setdefault('innovation_score', 85)
                    topic.setdefault('feasibility_score', 80)
                    topic.setdefault('impact_score', 75)
                    topic.setdefault('difficulty', '中等')
                    topic.setdefault('research_methods', '建议采用多种研究方法相结合的方式。')
                    topic.setdefault('expected_outcomes', '预期将产生有价值的研究成果。')
                    topic.setdefault('challenges', '需要克服一些技术和资源方面的挑战。')

                logger.info(f"Successfully generated topic suggestions: {len(topics)} topics")

                return jsonify({
                    'success': True,
                    'topics': topics
                })

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Raw response: {response}")

                # 如果JSON解析失败，返回一个默认的选题
                default_topics = [
                    {
                        "title": f"{domain_text}领域创新研究方向",
                        "category": "前沿研究",
                        "description": "基于当前技术发展趋势，这是一个具有潜力的研究方向，建议进一步调研相关文献。",
                        "innovation_score": 80,
                        "feasibility_score": 75,
                        "impact_score": 70,
                        "difficulty": "中等",
                        "research_methods": "建议采用文献调研、实验验证等方法。",
                        "expected_outcomes": "预期将产生有学术价值的研究成果。",
                        "challenges": "需要进一步明确具体研究方向和技术路线。"
                    }
                ]

                return jsonify({
                    'success': True,
                    'topics': default_topics,
                    'note': 'AI分析结果格式异常，已提供基础建议'
                })

        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            return jsonify({
                'success': False,
                'error': f'AI选题服务暂时不可用: {str(e)}'
            }), 500

    except Exception as e:
        logger.error(f"AI topic selection failed: {e}")
        return jsonify(handle_api_error(e, 'ai_topic_selection')), 500


@api_bp.route('/store_paragraph_results', methods=['POST'])
def store_paragraph_results():
    """存储段落模式的合并结果供学术分析功能使用"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        session_id = data.get('session_id')
        papers = data.get('papers', [])
        query = data.get('query', '')
        
        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID is required'}), 400
        
        if not papers:
            return jsonify({'success': False, 'error': 'Papers are required'}), 400
        
        # 存储到缓存中供学术分析功能使用
        cache = get_papers_cache()
        cache.store_papers(session_id, papers, query)
        
        logger.info(f"存储段落模式结果到缓存: session_id={session_id}, papers_count={len(papers)}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully stored {len(papers)} papers for session {session_id}'
        })
        
    except Exception as e:
        logger.exception("Failed to store paragraph results")
        return jsonify(handle_api_error(e, 'store_paragraph_results')), 500


@api_bp.route('/export_cover_letter', methods=['POST'])
def export_cover_letter():
    """导出Cover Letter为Word文档"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        cover_letter_content = data.get('content', '')
        journal_name = data.get('journal', 'Journal')
        paper_title = data.get('title', 'Research Paper')

        if not cover_letter_content:
            return jsonify({'success': False, 'error': 'Cover letter content is required'}), 400

        # 创建Word文档
        doc = Document()

        # 设置文档样式
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        # 清理和格式化内容
        content = clean_cover_letter_content(cover_letter_content)

        # 添加内容到文档
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                doc.add_paragraph()
                continue

            # 检查是否是标题行
            if line.startswith('**') and line.endswith('**'):
                # 标题格式
                title_text = line.replace('**', '')
                p = doc.add_paragraph()
                run = p.add_run(title_text)
                run.bold = True
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            elif line.startswith('[') and line.endswith(']'):
                # 占位符格式
                p = doc.add_paragraph()
                run = p.add_run(line)
                run.italic = True
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            else:
                # 普通文本
                doc.add_paragraph(line)

        # 生成文件名
        safe_journal = re.sub(r'[^\w\s-]', '', journal_name).strip()
        safe_title = re.sub(r'[^\w\s-]', '', paper_title)[:50].strip()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Cover_Letter_{safe_journal}_{timestamp}.docx"

        # 创建临时文件
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, filename)
        doc.save(temp_path)

        logger.info(f"Generated cover letter Word document: {filename}")

        # 返回文件
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        logger.exception("Failed to export cover letter")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/generate_review_outline', methods=['POST'])
def generate_review_outline():
    """基于文献标题生成综述大纲"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        query = data.get('query', '').strip()
        titles = data.get('titles', [])
        user_title = data.get('user_title', '').strip()

        if not query:
            return jsonify({'success': False, 'error': '请提供研究主题'}), 400

        # 如果没有提供titles，从缓存中获取
        if not titles:
            session_id = request.headers.get('sid') or session.get('session_id')
            logger.info(f"综述大纲生成 - 会话ID: {session_id}")

            if session_id:
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)

                if cached_data and cached_data.get('papers'):
                    papers = cached_data['papers']
                    titles = [paper.get('title', '') for paper in papers]
                    logger.info(f"综述大纲生成 - 从缓存获取到 {len(titles)} 篇文献标题")
                else:
                    logger.warning(f"综述大纲生成 - 会话ID {session_id} 不在缓存中")

        if not titles:
            return jsonify({
                'success': False,
                'error': '没有文献标题用于生成大纲，请先进行文献检索'
            }), 400

        # 使用前100篇文献标题
        selected_titles = titles[:100]
        titles_text = '\n'.join([f"{i+1}. {title}" for i, title in enumerate(selected_titles)])

        # 构建大纲生成提示词
        outline_prompt = f"""你是一位资深的学术综述专家，擅长设计结构严谨的综述大纲。

请基于以下{len(selected_titles)}篇文献标题，为主题"{query}"生成一个详细的综述大纲。

文献标题列表：
{titles_text}

请按照以下要求生成大纲：

1. **大纲结构要求**：
   - 采用层次化结构（一级标题、二级标题、三级标题）
   - 逻辑清晰，层次分明
   - 涵盖该领域的主要研究方向和热点

2. **内容要求**：
   - 引言部分：研究背景、意义、目的
   - 主体部分：按主题或方法分类组织
   - 结论部分：总结与展望
   - 每个章节都要有简要的内容说明

3. **输出格式**：
   - 使用HTML格式
   - 一级标题用<h2>，二级标题用<h3>，三级标题用<h4>
   - 内容说明用<p>标签
   - 重要概念用<strong>标签加粗

4. **专业要求**：
   - 体现该领域的研究脉络和发展趋势
   - 突出关键技术和方法
   - 考虑理论与应用的平衡

请生成一个完整、专业的综述大纲："""

        try:
            # 调用DeepSeek服务生成大纲
            from services.deepseek_service import DeepSeekService
            deepseek_service = DeepSeekService()
            outline_content = deepseek_service.analyze_text(outline_prompt)

            return jsonify({
                'success': True,
                'outline': outline_content,
                'analyzed_titles': len(selected_titles),
                'total_titles': len(titles),
                'query': query,
                'user_title': user_title
            })

        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {str(e)}")
            # 提供备用大纲
            fallback_outline = f"""
            <h2>📋 {query} - 综述大纲</h2>

            <h3>1. 引言</h3>
            <p><strong>1.1 研究背景</strong> - 介绍{query}领域的发展历程和重要性</p>
            <p><strong>1.2 研究现状</strong> - 分析当前研究的主要进展和成果</p>
            <p><strong>1.3 研究意义</strong> - 阐述本综述的目的和价值</p>

            <h3>2. 理论基础与概念框架</h3>
            <p><strong>2.1 核心概念定义</strong> - 明确关键术语和概念</p>
            <p><strong>2.2 理论基础</strong> - 梳理相关理论框架</p>
            <p><strong>2.3 研究方法</strong> - 总结主要研究方法和技术</p>

            <h3>3. 研究现状分析</h3>
            <p><strong>3.1 技术发展</strong> - 分析技术演进和创新</p>
            <p><strong>3.2 应用领域</strong> - 总结主要应用场景</p>
            <p><strong>3.3 研究热点</strong> - 识别当前研究热点和趋势</p>

            <h3>4. 关键技术与方法</h3>
            <p><strong>4.1 主要技术路线</strong> - 梳理技术发展路径</p>
            <p><strong>4.2 方法比较</strong> - 对比不同方法的优缺点</p>
            <p><strong>4.3 性能评估</strong> - 分析评估指标和标准</p>

            <h3>5. 挑战与问题</h3>
            <p><strong>5.1 技术挑战</strong> - 识别技术瓶颈和难点</p>
            <p><strong>5.2 应用障碍</strong> - 分析实际应用中的问题</p>
            <p><strong>5.3 标准化需求</strong> - 探讨标准化的必要性</p>

            <h3>6. 发展趋势与展望</h3>
            <p><strong>6.1 技术趋势</strong> - 预测未来技术发展方向</p>
            <p><strong>6.2 应用前景</strong> - 展望应用发展前景</p>
            <p><strong>6.3 研究建议</strong> - 提出未来研究方向建议</p>

            <h3>7. 结论</h3>
            <p><strong>7.1 主要发现</strong> - 总结综述的主要发现</p>
            <p><strong>7.2 贡献与意义</strong> - 阐述综述的贡献</p>
            <p><strong>7.3 局限性</strong> - 说明研究局限性</p>

            <p><em>💡 注：由于AI分析服务暂时不可用，以上为专业基础大纲模板。</em></p>
            """

            return jsonify({
                'success': True,
                'outline': fallback_outline,
                'analyzed_titles': len(selected_titles),
                'total_titles': len(titles),
                'query': query,
                'user_title': user_title
            })

    except Exception as e:
        logger.exception("Failed to generate review outline")
        return jsonify(handle_api_error(e, 'generate_review_outline')), 500


def parse_precise_search_results(analysis_text, original_papers):
    """将精确查找结果解析为结构化数据"""
    try:
        logger.info(f"开始解析精确查找结果，原始文献数量: {len(original_papers)}")

        # 使用换行符分割文本进行解析
        import re
        lines = analysis_text.split('\n')
        found_papers = []

        current_paper = None
        current_section = None
        content_buffer = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测文献标题行（数字开头的标题）
            if re.match(r'^\d+\.\s*\*\*.*\*\*', line):
                # 保存上一篇文献
                if current_paper:
                    if current_section == 'selection_reason' and content_buffer:
                        current_paper['selection_reason'] = ' '.join(content_buffer).strip()
                    found_papers.append(current_paper)

                # 开始新文献
                title_match = re.search(r'\d+\.\s*\*\*(.*?)\*\*', line)
                if title_match:
                    title = title_match.group(1).strip()
                    current_paper = {
                        'title': title,
                        'chinese_title': '',
                        'authors': '',
                        'abstract': '',
                        'selection_reason': '',
                        'sufficiency_score': ''
                    }
                    current_section = None
                    content_buffer = []
                    logger.info(f"找到文献: {title}")

            # 检测中文标题（方括号格式）
            elif line.startswith('[') and line.endswith(']') and current_paper:
                current_paper['chinese_title'] = line[1:-1]  # 去掉方括号
                logger.info(f"找到中文标题: {current_paper['chinese_title']}")

            # 检测各个部分
            elif line.startswith('**作者：**') or line.startswith('**作者信息**'):
                current_section = 'authors'
                content_buffer = []
            elif line.startswith('**发表年份：**') or line.startswith('**期刊信息**'):
                if current_section == 'authors' and content_buffer:
                    current_paper['authors'] = ' '.join(content_buffer).strip()
                current_section = 'journal'
                content_buffer = []
            elif line.startswith('**符合条件充分性：**') or line.startswith('**充分性评分：**'):
                # 解析充分性评分
                import re
                score_match = re.search(r'(\d+)%', line)
                if score_match:
                    current_paper['sufficiency_score'] = score_match.group(1)
                current_section = None
                content_buffer = []
            elif line.startswith('**中文摘要总结**') or line.startswith('**摘要**'):
                current_section = 'abstract'
                content_buffer = []
            elif line.startswith('**符合筛选的理由**') or line.startswith('**筛选理由**'):
                if current_section == 'abstract' and content_buffer:
                    current_paper['abstract'] = ' '.join(content_buffer).strip()
                current_section = 'selection_reason'
                content_buffer = []
            elif line.startswith('---'):
                if current_section == 'selection_reason' and content_buffer:
                    current_paper['selection_reason'] = ' '.join(content_buffer).strip()
                current_section = None
                content_buffer = []
            elif current_section and not line.startswith('**'):
                content_buffer.append(line)

        # 处理最后一篇文献
        if current_paper:
            if current_section == 'selection_reason' and content_buffer:
                current_paper['selection_reason'] = ' '.join(content_buffer).strip()
            elif current_section == 'abstract' and content_buffer:
                current_paper['abstract'] = ' '.join(content_buffer).strip()
            found_papers.append(current_paper)

        logger.info(f"解析出 {len(found_papers)} 篇精确查找文献")

        # 匹配原始文献数据
        structured_papers = []
        for i, found_paper in enumerate(found_papers):
            title = found_paper.get('title', '').strip()
            logger.info(f"正在匹配第 {i+1} 篇文献: {title}")

            if title:
                # 在原始文献中查找匹配的文献
                best_match = None
                best_score = 0

                for orig_paper in original_papers:
                    orig_title = orig_paper.get('title', '').strip()

                    # 计算标题相似度
                    title_lower = title.lower()
                    orig_title_lower = orig_title.lower()

                    # 完全匹配
                    if title_lower == orig_title_lower:
                        best_match = orig_paper
                        best_score = 100
                        break

                    # 包含匹配
                    if title_lower in orig_title_lower or orig_title_lower in title_lower:
                        score = max(len(title_lower), len(orig_title_lower)) / min(len(title_lower), len(orig_title_lower))
                        if score > best_score:
                            best_match = orig_paper
                            best_score = score

                    # 关键词匹配
                    title_words = set(title_lower.split())
                    orig_words = set(orig_title_lower.split())
                    common_words = title_words.intersection(orig_words)
                    if len(common_words) >= 3:  # 至少3个共同词
                        score = len(common_words) / max(len(title_words), len(orig_words))
                        if score > best_score:
                            best_match = orig_paper
                            best_score = score

                if best_match:
                    logger.info(f"找到匹配文献，相似度: {best_score}")
                    structured_paper = {
                        'title': best_match.get('title', ''),
                        'chinese_title': found_paper.get('chinese_title', ''),
                        'authors': best_match.get('authors', []),
                        'abstract': found_paper.get('abstract', best_match.get('abstract', '')),  # 优先使用AI生成的中文摘要
                        'journal': best_match.get('journal', ''),
                        'pub_year': best_match.get('pub_year', ''),
                        'url': best_match.get('url', ''),
                        'journal_info': best_match.get('journal_info', {}),
                        'impact_factor': best_match.get('impact_factor', ''),
                        'jcr_quartile': best_match.get('jcr_quartile', ''),
                        'cas_quartile': best_match.get('cas_quartile', ''),
                        'relevance': best_match.get('relevance', ''),
                        'selection_reason': found_paper.get('selection_reason', ''),
                        'sufficiency_score': found_paper.get('sufficiency_score', '')
                    }
                    structured_papers.append(structured_paper)
                else:
                    logger.warning(f"未找到匹配的原始文献: {title}")

        logger.info(f"成功匹配 {len(structured_papers)} 篇文献")
        return structured_papers

    except Exception as e:
        logger.error(f"解析精确查找结果时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


@api_bp.route('/reference_matching', methods=['POST'])
def reference_matching():
    """匹配参考文献功能"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        text_content = data.get('text_content', '').strip()

        if not text_content:
            return jsonify({'success': False, 'error': '请提供需要匹配参考文献的文本内容'}), 400

        # 创建异步任务
        task_data = {
            'text_content': text_content
        }

        async_task_service = get_async_task_service()
        task_id = async_task_service.create_task(
            task_type='reference_matching',
            task_data=task_data
        )

        logger.info(f"Created reference matching task {task_id}")

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '参考文献匹配任务已启动'
        })

    except Exception as e:
        logger.exception("Failed to start reference matching")
        return jsonify(handle_api_error(e, 'reference_matching')), 500


def clean_cover_letter_content(content):
    """清理和格式化Cover Letter内容"""
    try:
        # 移除HTML标签
        content = re.sub(r'<[^>]+>', '', content)

        # 处理换行符
        content = content.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')

        # 处理粗体标记
        content = re.sub(r'<strong>(.*?)</strong>', r'**\1**', content)
        content = re.sub(r'<b>(.*?)</b>', r'**\1**', content)

        # 处理斜体标记
        content = re.sub(r'<em>(.*?)</em>', r'*\1*', content)
        content = re.sub(r'<i>(.*?)</i>', r'*\1*', content)

        # 清理多余的空行
        lines = content.split('\n')
        cleaned_lines = []
        prev_empty = False

        for line in lines:
            line = line.strip()
            if not line:
                if not prev_empty:
                    cleaned_lines.append('')
                prev_empty = True
            else:
                cleaned_lines.append(line)
                prev_empty = False

        return '\n'.join(cleaned_lines)

    except Exception as e:
        logger.error(f"Error cleaning cover letter content: {e}")
        return content
