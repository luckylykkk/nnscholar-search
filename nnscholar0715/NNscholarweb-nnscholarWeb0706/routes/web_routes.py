"""Web routes for serving HTML pages."""

from flask import Blueprint, render_template, request, session, jsonify, send_file, abort, flash, redirect, url_for
import os
import logging
from datetime import datetime

from config.settings import config
from models.session import session_manager
from services.export_service import export_service
from utils.session_cache import get_papers_cache

logger = logging.getLogger(__name__)

# Create blueprint
web_bp = Blueprint('web', __name__)


@web_bp.route('/')
def index():
    """Main page - professional search interface."""
    try:
        logger.info("Serving main page")
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error serving main page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/chat')
def chat():
    """Chat interface page."""
    try:
        logger.info("Serving chat page")
        return render_template('chat.html')
    except Exception as e:
        logger.error(f"Error serving chat page: {e}")
        return f"Error loading chat page: {str(e)}", 500


@web_bp.route('/admin')
def admin():
    """Admin dashboard page."""
    try:
        logger.info("Serving admin page")
        
        # Get system statistics
        session_stats = session_manager.get_statistics()
        export_stats = export_service.get_export_statistics()
        
        # Add system info
        system_info = {
            'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'config_info': config.get_env_info(),
            'session_stats': session_stats,
            'export_stats': export_stats
        }
        
        return render_template('admin.html', system_info=system_info)
    except Exception as e:
        logger.error(f"Error serving admin page: {e}")
        return f"Error loading admin page: {str(e)}", 500


@web_bp.route('/analysis/<analysis_type>')
def academic_analysis(analysis_type):
    """Academic analysis result page.
    
    Args:
        analysis_type: Type of analysis (review_topic, research_topic, full_review)
    """
    try:
        logger.info(f"Serving analysis page for type: {analysis_type}")
        
        # Validate analysis type
        valid_types = ['review_topic', 'research_topic', 'full_review']
        if analysis_type not in valid_types:
            logger.warning(f"Invalid analysis type: {analysis_type}")
            abort(404, "Invalid analysis type")
        
        # Get session data - 优先使用URL参数中的session ID，然后是Flask session
        url_session_id = request.args.get('sid', '')
        flask_session_id = session.get('session_id', '')
        session_id = url_session_id or flask_session_id
        
        logger.info(f"Web route {analysis_type} - URL session_id: {url_session_id}")
        logger.info(f"Web route {analysis_type} - Flask session_id: {flask_session_id}")
        logger.info(f"Web route {analysis_type} - Final session_id: {session_id}")
        logger.info(f"Web route {analysis_type} - Session keys: {list(session.keys())}")
        
        # 如果使用URL参数的session ID，需要更新Flask session以确保数据一致性
        if url_session_id and url_session_id != flask_session_id:
            logger.info(f"Web route {analysis_type} - Updating Flask session from URL parameter")
            session['session_id'] = url_session_id
        
        # 尝试获取user session，但不强制要求存在
        user_session = None
        if session_id:
            user_session = session_manager.get_session(session_id)
            if not user_session:
                logger.warning(f"Session not found in session_manager: {session_id}")
        else:
            logger.warning("No session ID found for analysis page")
        
        # Get analysis data from session
        session_key = f'{analysis_type}_result'
        analysis_data = session.get(session_key, {})
        
        logger.info(f"Web route {analysis_type} - Looking for session key: {session_key}")
        logger.info(f"Web route {analysis_type} - Session data: {analysis_data}")
        
        # Check all session data for debugging
        all_session_data = {k: v for k, v in session.items() if '_result' in k}
        logger.info(f"Web route {analysis_type} - All analysis results in session: {list(all_session_data.keys())}")
        
        # 如果没有数据，但有URL参数中的session_id，尝试从缓存获取完整分析结果
        if not analysis_data and url_session_id:
            logger.warning(f"Web route {analysis_type} - No data in current session, trying to reconstruct from cache")
            try:
                from utils.session_cache import get_papers_cache
                papers_cache = get_papers_cache()
                
                # 首先尝试获取完整的分析结果
                cached_analysis = papers_cache.get_analysis_result(url_session_id, analysis_type)
                if cached_analysis:
                    logger.info(f"Web route {analysis_type} - Found complete analysis result in cache: paper_count={cached_analysis.get('paper_count')}")
                    analysis_data = cached_analysis
                else:
                    # 如果没有完整分析结果，尝试从papers缓存获取基本信息
                    cached_papers = papers_cache.get_papers(url_session_id)
                    
                    if cached_papers and cached_papers.get('papers'):
                        # 创建基本的分析数据结构
                        paper_count = len(cached_papers['papers'])
                        query = cached_papers.get('query', '')
                        
                        analysis_data = {
                            'content': f'<h3>基于URL参数恢复的{analysis_type}分析</h3><p>检测到来自新窗口的访问，正在恢复分析数据...</p><p>基于{paper_count}篇文献的分析结果应该正常显示。如果看到此消息，说明session数据传递有问题。</p>',
                            'paper_count': paper_count,
                            'search_query': query,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'loading': False,
                            'error': None,
                            'analysis_type': analysis_type
                        }
                        
                        logger.info(f"Web route {analysis_type} - Reconstructed basic analysis data: paper_count={paper_count}")
                    else:
                        logger.warning(f"Web route {analysis_type} - No papers found in cache for session {url_session_id}")
            except Exception as e:
                logger.error(f"Web route {analysis_type} - Error reconstructing data: {e}")
        
        # Clean up old session data that might have incorrect format
        if analysis_data and not isinstance(analysis_data.get('content'), str):
            logger.warning(f"Found malformed session data for {analysis_type}, clearing...")
            session.pop(f'{analysis_type}_result', None)
            analysis_data = {}
        
        # Prepare template data with proper field mapping
        template_data = {
            'analysis_type': analysis_type,
            'analysis_result': analysis_data.get('content', '暂无分析结果'),
            'analysis_time': analysis_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            'paper_count': analysis_data.get('paper_count', 0),
            'search_query': analysis_data.get('search_query', ''),
            'query': analysis_data.get('search_query', ''),  # 添加query变量以兼容模板
            'title': analysis_data.get('title', ''),
            'generated_at': analysis_data.get('generated_at', ''),
            'word_count': analysis_data.get('word_count', 0),
            'reference_count': analysis_data.get('reference_count', 0),
            'error': analysis_data.get('error'),
            'loading': analysis_data.get('loading', False)
        }
        
        # Debug logging for troubleshooting
        logger.info(f"Analysis data for {analysis_type}: paper_count={template_data['paper_count']}, has_content={bool(template_data['analysis_result'])}")
        if not template_data['analysis_result'] or template_data['analysis_result'] == '暂无分析结果':
            logger.warning(f"No valid analysis result found for {analysis_type}. Session data: {analysis_data}")
        
        return render_template('academic_analysis.html', **template_data)
        
    except Exception as e:
        logger.error(f"Error serving analysis page: {e}")
        return f"Error loading analysis page: {str(e)}", 500


@web_bp.route('/literature_tracking')
def literature_tracking():
    """文献追踪页面"""
    try:
        # 获取URL参数
        seed_paper_id = request.args.get('seed_paper_id', '')
        session_id = request.args.get('session_id', '') or session.get('session_id')

        # 优先使用URL参数中的session_id
        if session_id:
            # 验证session_id是否在缓存中存在
            cache = get_papers_cache()
            if cache.session_exists(session_id):
                logger.info(f"Using existing session_id from URL: {session_id}")
                session['session_id'] = session_id
            else:
                logger.warning(f"Session {session_id} not found in cache, creating new session")
                session_id = None

        # 如果没有有效的session_id，创建一个新的
        if not session_id:
            # 生成session_xxx格式的会话ID
            import random
            session_id = 'session_' + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=9))
            session['session_id'] = session_id
            logger.info(f"Created new session_id: {session_id}")

        seed_paper = None

        # 如果有种子文献ID，尝试获取文献信息
        if seed_paper_id and session_id:
            cache = get_papers_cache()
            cached_data = cache.get_papers(session_id)

            if cached_data and cached_data.get('papers'):
                papers = cached_data['papers']
                for paper in papers:
                    if str(paper.get('pmid', '')) == str(seed_paper_id) or \
                       paper.get('title', '').strip().lower() == seed_paper_id.lower():
                        seed_paper = paper
                        break

        return render_template('literature_tracking.html',
                             seed_paper=seed_paper,
                             session_id=session_id)

    except Exception as e:
        logger.exception("Literature tracking page error")
        flash('页面加载失败', 'error')
        return redirect(url_for('web.index'))


@web_bp.route('/test-export')
def test_export():
    """Test export page for debugging."""
    try:
        # Only available in debug mode
        if not config.DEBUG:
            abort(404)
        
        logger.info("Serving test export page")
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Export Test</title>
            <meta charset="utf-8">
        </head>
        <body>
            <h1>Export Test Page</h1>
            <p>This page is only available in debug mode.</p>
            <p>Use this page to test export functionality.</p>
            
            <h2>Test Data</h2>
            <pre id="test-data">{
    "papers": [
        {
            "pmid": "12345678",
            "title": "Test Paper Title",
            "authors": ["Author One", "Author Two"],
            "journal": "Test Journal",
            "pub_date": "2023-01-01",
            "abstract": "This is a test abstract for the test paper.",
            "doi": "10.1000/test.doi",
            "keywords": ["test", "example", "demo"]
        }
    ]
}</pre>
            
            <h2>Export Actions</h2>
            <button onclick="testExcelExport()">Test Excel Export</button>
            <button onclick="testWordExport()">Test Word Export</button>
            
            <div id="result"></div>
            
            <script>
            function testExcelExport() {
                const data = JSON.parse(document.getElementById('test-data').textContent);
                
                fetch('/api/export/excel', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                })
                .then(response => response.json())
                .then(data => {
                    document.getElementById('result').innerHTML = 
                        '<h3>Excel Export Result:</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
                })
                .catch(error => {
                    document.getElementById('result').innerHTML = 
                        '<h3>Error:</h3><p>' + error + '</p>';
                });
            }
            
            function testWordExport() {
                const data = JSON.parse(document.getElementById('test-data').textContent);
                
                fetch('/api/export/word', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                })
                .then(response => response.json())
                .then(data => {
                    document.getElementById('result').innerHTML = 
                        '<h3>Word Export Result:</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
                })
                .catch(error => {
                    document.getElementById('result').innerHTML = 
                        '<h3>Error:</h3><p>' + error + '</p>';
                });
            }
            </script>
        </body>
        </html>
        """
    except Exception as e:
        logger.error(f"Error serving test export page: {e}")
        return f"Error: {str(e)}", 500


@web_bp.route('/download/<session_id>/<file_type>')
def download_file(session_id, file_type):
    """Download exported files.
    
    Args:
        session_id: User session ID
        file_type: File type ('excel' or 'word')
    """
    try:
        # Validate session
        user_session = session_manager.get_session(session_id)
        if not user_session:
            logger.warning(f"Invalid session for download: {session_id}")
            abort(404, "Session not found")
        
        # Validate file type
        if file_type not in ['excel', 'word']:
            logger.warning(f"Invalid file type: {file_type}")
            abort(400, "Invalid file type")
        
        # Get file extension
        extension = '.xlsx' if file_type == 'excel' else '.docx'
        
        # Look for the file in exports directory
        export_dir = config.EXPORTS_DIR
        
        # Find files that match the session and type
        import glob
        pattern = os.path.join(export_dir, f"*{session_id}*{extension}")
        matching_files = glob.glob(pattern)
        
        if not matching_files:
            # Try alternative patterns
            pattern = os.path.join(export_dir, f"*{extension}")
            all_files = glob.glob(pattern)
            
            # Get the most recent file (fallback)
            if all_files:
                matching_files = [max(all_files, key=os.path.getctime)]
        
        if not matching_files:
            logger.warning(f"No {file_type} file found for session {session_id}")
            abort(404, f"No {file_type} file found")
        
        # Use the most recent matching file
        file_path = matching_files[0]
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            abort(404, "File not found")
        
        # Generate download filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_name = f"nnscholar_export_{timestamp}{extension}"
        
        logger.info(f"Serving download: {file_path} as {download_name}")
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_type == 'excel' 
                     else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        abort(500, f"Download failed: {str(e)}")


@web_bp.route('/health')
def health_check():
    """Health check endpoint."""
    try:
        # Basic health information
        health_info = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '2.0.0',
            'services': {
                'session_manager': session_manager.get_active_sessions_count(),
                'export_service': 'available'
            }
        }
        
        return jsonify(health_info)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@web_bp.route('/status')
def status():
    """Detailed status information."""
    try:
        # Import services for status
        from services.pubmed_service import pubmed_service
        from services.deepseek_service import deepseek_service
        from services.embedding_service import embedding_service
        
        status_info = {
            'application': {
                'name': 'NNScholar',
                'version': '2.0.0',
                'mode': 'debug' if config.DEBUG else 'production',
                'timestamp': datetime.now().isoformat()
            },
            'configuration': config.get_env_info(),
            'services': {
                'pubmed': pubmed_service.get_service_status(),
                'deepseek': deepseek_service.get_service_status(),
                'embedding': embedding_service.get_service_status(),
                'export': export_service.get_export_statistics()
            },
            'sessions': session_manager.get_statistics()
        }
        
        return jsonify(status_info)
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@web_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    logger.warning(f"404 error: {request.url}")
    
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    return render_template('404.html'), 404


@web_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"500 error: {error}")
    
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    
    return render_template('500.html'), 500


# Context processor to inject common variables
@web_bp.app_context_processor
def inject_common_vars():
    """Inject common template variables."""
    return {
        'app_name': 'NNScholar',
        'app_version': '2.0.0',
        'current_year': datetime.now().year,
        'debug_mode': config.DEBUG
    }


# Before request handler
@web_bp.before_request
def before_request():
    """Handle operations before each request."""
    # Log request (in debug mode)
    if config.DEBUG:
        logger.debug(f"Request: {request.method} {request.path}")
    
    # Initialize session if needed
    if 'session_id' not in session:
        user_session = session_manager.create_session()
        session['session_id'] = user_session.session_id
        logger.debug(f"Created new session: {user_session.session_id}")
    else:
        # Update existing session activity
        user_session = session_manager.get_session(session['session_id'])
        if user_session:
            user_session.update_activity()
        else:
            # Session expired, create new one
            user_session = session_manager.create_session()
            session['session_id'] = user_session.session_id
            logger.debug(f"Session expired, created new: {user_session.session_id}")


# After request handler
@web_bp.after_request
def after_request(response):
    """Handle operations after each request."""
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # CORS headers for API endpoints
    if request.path.startswith('/api/'):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    
    return response


# 深度分析功能页面路由
@web_bp.route('/analysis/statistical-analysis')
def statistical_analysis():
    """统计分析专家页面."""
    try:
        logger.info("Serving statistical analysis page")
        return render_template('analysis/statistical_analysis.html')
    except Exception as e:
        logger.error(f"Error serving statistical analysis page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/visualization-expert')
def visualization_expert():
    """绘图建议专家页面."""
    try:
        logger.info("Serving visualization expert page")
        return render_template('analysis/visualization_expert.html')
    except Exception as e:
        logger.error(f"Error serving visualization expert page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/journal-selection')
def journal_selection():
    """AI投稿选刊页面."""
    try:
        logger.info("Serving journal selection page")
        return render_template('analysis/journal_selection.html')
    except Exception as e:
        logger.error(f"Error serving journal selection page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/cover-letter')
def cover_letter():
    """Cover Letter页面."""
    try:
        logger.info("Serving cover letter page")
        return render_template('analysis/cover_letter.html')
    except Exception as e:
        logger.error(f"Error serving cover letter page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/grant-evaluation')
def grant_evaluation():
    """基金立项评估页面."""
    try:
        logger.info("Serving grant evaluation page")
        return render_template('analysis/grant_evaluation.html')
    except Exception as e:
        logger.error(f"Error serving grant evaluation page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/deep-statistical-analysis')
def deep_statistical_analysis():
    """深度统计分析页面."""
    try:
        logger.info("Serving deep statistical analysis page")
        return render_template('analysis/deep_statistical_analysis.html')
    except Exception as e:
        logger.error(f"Error serving deep statistical analysis page: {e}")
        return f"Error loading page: {str(e)}", 500




@web_bp.route('/analysis/paper-translation')
def paper_translation():
    """论文翻译页面."""
    try:
        logger.info("Serving paper translation page")
        return render_template('analysis/paper_translation.html')
    except Exception as e:
        logger.error(f"Error serving paper translation page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/paper-polish')
def paper_polish():
    """论文润色页面."""
    try:
        logger.info("Serving paper polish page")
        return render_template('analysis/paper_polish.html')
    except Exception as e:
        logger.error(f"Error serving paper polish page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/ai-topic-selection')
def ai_topic_selection():
    """AI选题页面."""
    try:
        logger.info("Serving AI topic selection page")
        return render_template('analysis/ai_topic_selection.html')
    except Exception as e:
        logger.error(f"Error serving AI topic selection page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/innovation-analysis')
def innovation_analysis():
    """创新点分析页面."""
    try:
        logger.info("Serving innovation analysis page")
        return render_template('analysis/innovation_analysis.html')
    except Exception as e:
        logger.error(f"Error serving innovation analysis page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/reviewer-response')
def reviewer_response():
    """审稿回复页面."""
    try:
        logger.info("Serving reviewer response page")
        return render_template('analysis/reviewer_response.html')
    except Exception as e:
        logger.error(f"Error serving reviewer response page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/reference-matching')
def reference_matching():
    """参考文献匹配页面."""
    try:
        logger.info("Serving reference matching page")
        return render_template('analysis/reference_matching.html')
    except Exception as e:
        logger.error(f"Error serving reference matching page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/research-methodology')
def research_methodology():
    """研究方法设计页面."""
    try:
        logger.info("Serving research methodology page")
        return render_template('analysis/research_methodology.html')
    except Exception as e:
        logger.error(f"Error serving research methodology page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/literature-screening')
def literature_screening():
    """文献筛查页面."""
    try:
        logger.info("Serving literature screening page")
        return render_template('analysis/literature_screening.html')
    except Exception as e:
        logger.error(f"Error serving literature screening page: {e}")
        return f"Error loading page: {str(e)}", 500





@web_bp.route('/analysis/innovation-discovery')
def innovation_discovery():
    """创新点挖掘页面."""
    try:
        logger.info("Serving innovation discovery page")
        return render_template('analysis/innovation_discovery.html')
    except Exception as e:
        logger.error(f"Error serving innovation discovery page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/review-outline')
def review_outline():
    """综述大纲页面."""
    try:
        logger.info("Serving review outline page")
        return render_template('analysis/review_outline.html')
    except Exception as e:
        logger.error(f"Error serving review outline page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/review-draft')
def review_draft():
    """综述初稿页面."""
    try:
        logger.info("Serving review draft page")
        return render_template('analysis/review_draft.html')
    except Exception as e:
        logger.error(f"Error serving review draft page: {e}")
        return f"Error loading page: {str(e)}", 500


@web_bp.route('/analysis/research-gap-analysis')
def research_gap_analysis():
    """研究空白分析页面."""
    try:
        logger.info("Serving research gap analysis page")
        return render_template('analysis/research_gap_analysis.html')
    except Exception as e:
        logger.error(f"Error serving research gap analysis page: {e}")
        return f"Error loading page: {str(e)}", 500