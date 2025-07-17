"""WebSocket routes for real-time communication."""

from flask_socketio import emit, join_room, leave_room, disconnect
try:
    from flask_socketio import request
except ImportError:
    # Fallback: 使用flask的request（在某些版本中可能需要）
    try:
        from flask import request
    except ImportError:
        request = None
import logging
from datetime import datetime
from typing import Dict, Any
from functools import wraps

from config.settings import config
from models.session import SessionManager
from services.pubmed_service import pubmed_service
from services.deepseek_service import deepseek_service
from services.embedding_service import embedding_service
from services.advanced_review_service import AdvancedReviewService

logger = logging.getLogger(__name__)

def get_client_id():
    """获取客户端ID的辅助函数"""
    if request and hasattr(request, 'sid'):
        return request.sid
    else:
        import uuid
        return str(uuid.uuid4())[:8]

# Global variables for tracking connections
active_connections = {}
connection_stats = {
    'total_connections': 0,
    'current_connections': 0,
    'total_disconnections': 0
}


def authenticated(f):
    """Decorator to check if user has valid session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = args[0].get('session_id') if args else None
        if not session_id:
            emit('error', {'message': 'Session ID required'})
            return
        return f(*args, **kwargs)
    return decorated_function


def register_websocket_handlers(socketio, session_manager: SessionManager):
    """Register all WebSocket event handlers.
    
    Args:
        socketio: SocketIO instance
        session_manager: Session manager instance
    """
    
    @socketio.on('connect')
    def handle_connect(auth=None):
        """Handle client connection."""
        try:
            client_id = get_client_id()
            
            # Update connection stats
            connection_stats['total_connections'] += 1
            connection_stats['current_connections'] += 1
            
            # Store connection info
            active_connections[client_id] = {
                'connected_at': datetime.now(),
                'session_id': None,
                'last_activity': datetime.now()
            }
            
            logger.info(f"Client connected: {client_id}")
            
            # Send welcome message
            emit('connected', {
                'message': 'Connected to NNScholar',
                'client_id': client_id,
                'server_time': datetime.now().isoformat(),
                'version': '2.0.0'
            })
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            emit('error', {'message': 'Connection failed'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        try:
            client_id = get_client_id()
            
            # Update connection stats (ensure they don't go negative)
            if connection_stats['current_connections'] > 0:
                connection_stats['current_connections'] -= 1
            connection_stats['total_disconnections'] += 1
            
            # Clean up connection info
            if client_id in active_connections:
                connection_info = active_connections.pop(client_id)
                session_id = connection_info.get('session_id')
                
                # Update session if exists
                if session_id:
                    try:
                        user_session = session_manager.get_session(session_id)
                        if user_session:
                            user_session.socket_id = None
                    except Exception as session_error:
                        logger.warning(f"Session cleanup error during disconnect: {session_error}")
            
            logger.info(f"Client disconnected: {client_id}")
            
        except Exception as e:
            logger.error(f"Disconnection error: {e}")
            # Don't try to emit error response during disconnect as connection may be closed
    
    @socketio.on('join_session')
    def handle_join_session(data):
        """Associate client with user session."""
        try:
            client_id = get_client_id()
            session_id = data.get('session_id')
            
            if not session_id:
                emit('error', {'message': 'Session ID required'})
                return
            
            # Get or create session
            user_session = session_manager.get_session(session_id)
            if not user_session:
                user_session = session_manager.create_session(client_id)
                session_id = user_session.session_id
            else:
                user_session.socket_id = client_id
                user_session.update_activity()
            
            # Update connection info
            if client_id in active_connections:
                active_connections[client_id]['session_id'] = session_id
            
            # Join session room
            join_room(session_id)
            
            logger.info(f"Client {client_id} joined session {session_id}")
            
            emit('session_joined', {
                'session_id': session_id,
                'message': 'Joined session successfully'
            })
            
        except Exception as e:
            logger.error(f"Join session error: {e}")
            emit('error', {'message': 'Failed to join session'})
    
    @socketio.on('search_papers')
    @authenticated
    def handle_search_papers(data):
        """Handle real-time paper search."""
        try:
            client_id = get_client_id()
            session_id = data.get('session_id')
            query = data.get('query', '').strip()
            max_results = min(data.get('max_results', 100), config.MAX_SEARCH_RESULTS)
            
            if not query:
                emit('search_error', {'message': 'Query is required'})
                return
            
            logger.info(f"WebSocket search: {query[:50]}... (client: {client_id})")
            
            # Emit search started
            emit('search_started', {
                'query': query,
                'max_results': max_results,
                'timestamp': datetime.now().isoformat()
            })
            
            # Generate search strategy if requested
            use_ai_strategy = data.get('use_ai_strategy', True)
            if use_ai_strategy:
                try:
                    emit('search_progress', {
                        'stage': 'strategy_generation',
                        'message': 'Generating AI-optimized search strategy...'
                    })
                    
                    search_mode = data.get('search_mode', 'comprehensive')
                    optimized_query = deepseek_service.generate_search_strategy(query, search_mode)
                    
                    if optimized_query:
                        query = optimized_query
                        emit('search_progress', {
                            'stage': 'strategy_generated',
                            'message': 'AI strategy generated',
                            'optimized_query': query
                        })
                    
                except Exception as e:
                    logger.warning(f"AI strategy generation failed: {e}")
                    emit('search_progress', {
                        'stage': 'strategy_fallback',
                        'message': 'Using original query (AI strategy failed)'
                    })
            
            # Search papers
            emit('search_progress', {
                'stage': 'pubmed_search',
                'message': 'Searching PubMed database...'
            })
            
            pmids, total_count = pubmed_service.search_papers(query, max_results)
            
            if not pmids:
                emit('search_completed', {
                    'papers': [],
                    'total_count': 0,
                    'query': query,
                    'message': 'No papers found'
                })
                return
            
            emit('search_progress', {
                'stage': 'fetching_details',
                'message': f'Found {len(pmids)} papers, fetching details...',
                'found_count': len(pmids),
                'total_count': total_count
            })
            
            # Fetch paper details
            papers = pubmed_service.fetch_paper_details_batch(pmids)
            
            emit('search_progress', {
                'stage': 'calculating_relevance',
                'message': 'Calculating relevance scores...'
            })
            
            # Calculate relevance scores
            include_relevance = data.get('include_relevance', True)
            if include_relevance and papers:
                try:
                    paper_texts = [f"{paper.title} {paper.abstract}" for paper in papers]
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
            
            # Convert to dict format
            paper_dicts = [paper.to_dict() for paper in papers]
            
            # Add journal metrics
            emit('search_progress', {
                'stage': 'adding_metrics',
                'message': 'Adding journal metrics...'
            })
            
            from models.journal import journal_db
            for paper_dict in paper_dicts:
                journal_name = paper_dict.get('journal', '')
                if journal_name:
                    metrics = journal_db.get_journal_metrics(journal_name)
                    if metrics:
                        paper_dict['impact_factor'] = metrics.impact_factor
                        paper_dict['jcr_quartile'] = metrics.jcr_quartile
                        paper_dict['cas_quartile'] = metrics.cas_quartile
            
            # Store results in session
            user_session = session_manager.get_session(session_id)
            if user_session:
                user_session.add_search_result(query, paper_dicts)
            
            # Emit completion
            emit('search_completed', {
                'papers': paper_dicts,
                'total_count': total_count,
                'returned_count': len(paper_dicts),
                'query': query,
                'search_time': datetime.now().isoformat()
            })
            
            logger.info(f"WebSocket search completed: {len(paper_dicts)} papers")
            
        except Exception as e:
            logger.error(f"WebSocket search error: {e}")
            emit('search_error', {
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    @socketio.on('analyze_papers')
    @authenticated
    def handle_analyze_papers(data):
        """Handle real-time paper analysis."""
        try:
            analysis_type = data.get('analysis_type')
            papers = data.get('papers', [])
            topic = data.get('topic', '')
            
            if not papers:
                emit('analysis_error', {'message': 'Papers are required'})
                return
            
            if not analysis_type:
                emit('analysis_error', {'message': 'Analysis type is required'})
                return
            
            logger.info(f"WebSocket analysis: {analysis_type} for {len(papers)} papers")
            
            # Emit analysis started
            emit('analysis_started', {
                'analysis_type': analysis_type,
                'paper_count': len(papers),
                'timestamp': datetime.now().isoformat()
            })
            
            result = None
            
            if analysis_type == 'research_status':
                emit('analysis_progress', {'message': 'Analyzing research status...'})
                result = deepseek_service.analyze_research_status(papers, topic)
                
            elif analysis_type == 'review_suggestions':
                emit('analysis_progress', {'message': 'Generating review topic suggestions...'})
                result = deepseek_service.suggest_review_topics(papers, topic)
                
            elif analysis_type == 'research_suggestions':
                emit('analysis_progress', {'message': 'Generating research topic suggestions...'})
                result = deepseek_service.suggest_research_topics(papers, topic)
                
            elif analysis_type == 'full_review':
                emit('analysis_progress', {'message': 'Generating comprehensive review...'})
                review_type = data.get('review_type', 'narrative')
                result = deepseek_service.generate_full_review(papers, topic, review_type)
                
            elif analysis_type == 'representative_papers':
                emit('analysis_progress', {'message': 'Recommending representative papers...'})
                criteria = data.get('criteria', 'impact_and_novelty')
                result = deepseek_service.recommend_representative_papers(papers, criteria)
                
            else:
                emit('analysis_error', {'message': f'Unknown analysis type: {analysis_type}'})
                return
            
            # Store result in session
            session_id = data.get('session_id')
            if session_id:
                user_session = session_manager.get_session(session_id)
                if user_session:
                    user_session.add_analysis_result(analysis_type, result)
            
            # Emit completion
            emit('analysis_completed', {
                'analysis_type': analysis_type,
                'result': result,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"WebSocket analysis completed: {analysis_type}")
            
        except Exception as e:
            logger.error(f"WebSocket analysis error: {e}")
            emit('analysis_error', {
                'message': str(e),
                'analysis_type': data.get('analysis_type'),
                'timestamp': datetime.now().isoformat()
            })
    
    @socketio.on('export_papers')
    @authenticated
    def handle_export_papers(data):
        """Handle real-time paper export."""
        try:
            export_type = data.get('export_type')  # 'excel' or 'word'
            papers = data.get('papers', [])
            filename = data.get('filename')
            options = data.get('options', {})
            
            if not papers:
                emit('export_error', {'message': 'Papers are required'})
                return
            
            if export_type not in ['excel', 'word']:
                emit('export_error', {'message': 'Invalid export type'})
                return
            
            logger.info(f"WebSocket export: {export_type} for {len(papers)} papers")
            
            # Emit export started
            emit('export_started', {
                'export_type': export_type,
                'paper_count': len(papers),
                'timestamp': datetime.now().isoformat()
            })
            
            emit('export_progress', {'message': f'Generating {export_type} file...'})
            
            from services.export_service import export_service
            
            if export_type == 'excel':
                include_metrics = options.get('include_metrics', True)
                file_path, filename = export_service.export_to_excel(
                    papers, filename, include_metrics
                )
            else:  # word
                title = options.get('title', 'Literature Review')
                include_abstracts = options.get('include_abstracts', True)
                file_path, filename = export_service.export_to_word(
                    papers, title, filename, include_abstracts
                )
            
            # Update session export count
            session_id = data.get('session_id')
            if session_id:
                user_session = session_manager.get_session(session_id)
                if user_session:
                    user_session.total_exports += 1
            
            # Emit completion
            emit('export_completed', {
                'export_type': export_type,
                'filename': filename,
                'file_path': file_path,
                'paper_count': len(papers),
                'download_url': f'/download/{session_id}/{export_type}',
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"WebSocket export completed: {filename}")
            
        except Exception as e:
            logger.error(f"WebSocket export error: {e}")
            emit('export_error', {
                'message': str(e),
                'export_type': data.get('export_type'),
                'timestamp': datetime.now().isoformat()
            })
    
    @socketio.on('get_stats')
    def handle_get_stats(data):
        """Handle stats request."""
        try:
            # Get connection stats
            stats = {
                'connections': connection_stats.copy(),
                'active_sessions': session_manager.get_active_sessions_count(),
                'timestamp': datetime.now().isoformat()
            }
            
            emit('stats_update', stats)
            
        except Exception as e:
            logger.error(f"Stats request error: {e}")
            emit('error', {'message': 'Failed to get stats'})
    
    @socketio.on('ping')
    def handle_ping(data):
        """Handle ping for keepalive."""
        try:
            client_id = get_client_id()
            
            # Update activity
            if client_id in active_connections:
                active_connections[client_id]['last_activity'] = datetime.now()
            
            emit('pong', {
                'timestamp': datetime.now().isoformat(),
                'client_id': client_id
            })
            
        except Exception as e:
            logger.error(f"Ping error: {e}")
    
    # Periodic cleanup task
    def cleanup_inactive_connections():
        """Clean up inactive connections and sessions."""
        try:
            # Cleanup sessions
            session_manager.cleanup_inactive_sessions()
            
            # Cleanup old connections
            current_time = datetime.now()
            inactive_clients = []
            
            for client_id, conn_info in active_connections.items():
                last_activity = conn_info['last_activity']
                if (current_time - last_activity).total_seconds() > config.WEBSOCKET_TIMEOUT:
                    inactive_clients.append(client_id)
            
            for client_id in inactive_clients:
                active_connections.pop(client_id, None)
                connection_stats['current_connections'] -= 1
                logger.debug(f"Cleaned up inactive connection: {client_id}")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    # Schedule periodic cleanup (you'll need to call this externally)
    # This is just the function definition
    socketio.cleanup_inactive_connections = cleanup_inactive_connections

    # 注册综述生成处理器
    register_review_handlers(socketio)

    logger.info("WebSocket handlers registered successfully")


def get_connection_stats() -> Dict[str, Any]:
    """Get current connection statistics."""
    return {
        'connection_stats': connection_stats.copy(),
        'active_connections': len(active_connections),
        'connection_details': {
            client_id: {
                'connected_at': info['connected_at'].isoformat(),
                'session_id': info['session_id'],
                'last_activity': info['last_activity'].isoformat()
            }
            for client_id, info in active_connections.items()
        }
    }


def register_review_handlers(socketio):
    """注册综述生成相关的WebSocket事件处理器"""

    @socketio.on('generate_full_review_with_progress')
    def handle_generate_full_review_with_progress(data):
        """处理带进度更新的综述生成请求"""
        try:
            client_id = get_client_id()
            logger.info(f"Client {client_id} requesting full review generation with progress")

            # 获取参数
            papers = data.get('papers', [])
            topic = data.get('topic', '').strip() or data.get('query', '').strip()
            language = data.get('language', 'chinese')
            session_id = data.get('session_id')

            # 如果没有提供papers，从缓存中获取
            if not papers and session_id:
                from models.cache import get_papers_cache
                cache = get_papers_cache()
                cached_data = cache.get_papers(session_id)
                if cached_data:
                    papers = cached_data.get('papers', [])
                    if not topic:
                        topic = cached_data.get('query', topic)

            if not papers:
                emit('review_error', {'error': 'Papers are required'})
                return

            if not topic:
                emit('review_error', {'error': 'Topic is required'})
                return

            # 进度回调函数
            def progress_callback(progress, message):
                emit('review_progress', {
                    'progress': progress,
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })

            # 初始化服务
            review_service = AdvancedReviewService(deepseek_service)

            # 开始生成综述
            emit('review_started', {
                'message': '开始生成综述...',
                'paper_count': len(papers),
                'language': language
            })

            # 生成综述
            result = review_service.generate_comprehensive_review(
                papers=papers,
                topic=topic,
                user_title=topic,
                language=language,
                progress_callback=progress_callback
            )

            if result.get('success'):
                emit('review_completed', {
                    'content': result.get('content', ''),
                    'title': result.get('title', topic),
                    'paper_count': result.get('paper_count', len(papers)),
                    'word_count': result.get('word_count', 0),
                    'reference_count': result.get('reference_count', 0),
                    'generated_at': result.get('generated_at'),
                    'references': result.get('references', [])
                })
            else:
                emit('review_error', {
                    'error': result.get('error', '未知错误'),
                    'paper_count': len(papers)
                })

        except Exception as e:
            logger.error(f"Error in full review generation: {str(e)}")
            emit('review_error', {
                'error': f'生成过程中出现错误: {str(e)}'
            })