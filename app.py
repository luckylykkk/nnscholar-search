"""NNScholar - 智能学术文献检索与分析平台

重构版主应用文件 - 精简版Flask应用入口
"""

from flask import Flask, request, jsonify, render_template, session
from flask_socketio import SocketIO
import os
import logging
from datetime import datetime

# Import configuration
from config import Config, APIConfig
from config.settings import config
from config.api_config import api_config

# Import models
from models.session import session_manager
from models.journal import journal_db

# Import routes
from routes.web_routes import web_bp
from routes.api_routes import api_bp
from routes.export_routes import export_bp
from routes.websocket_routes import register_websocket_handlers


def create_app():
    """Application factory pattern."""
    
    # Initialize Flask app
    app = Flask(__name__)
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['DEBUG'] = config.DEBUG
    
    # Initialize SocketIO with configuration matching original version
    try:
        socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            async_mode='threading',
            ping_timeout=60,
            ping_interval=25,
            max_http_buffer_size=1e8,  # 100MB
            manage_session=True,  # 启用Socket.IO的会话管理
            logger=config.DEBUG,  # 启用详细日志
            engineio_logger=config.DEBUG  # 启用Engine.IO日志
        )
        import logging
        logger = logging.getLogger(__name__)
        logger.info("SocketIO initialized with full configuration")
    except Exception as e:
        # Fallback for compatibility issues
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize SocketIO with full config: {e}")
        
        try:
            # Try with basic threading mode
            socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
            logger.info("SocketIO initialized with threading backend")
        except Exception as e2:
            logger.error(f"Failed to initialize SocketIO: {e2}")
            # Last resort: minimal configuration
            socketio = SocketIO(app, cors_allowed_origins="*")
            logger.warning("SocketIO initialized with minimal configuration")
    
    # Setup logging
    setup_logging()
    
    # Validate configuration
    validate_configuration()
    
    # Register blueprints
    register_blueprints(app)
    
    # Register WebSocket handlers
    register_websocket_handlers(socketio, session_manager)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Initialize services
    initialize_services()
    
    # 将socketio实例附加到app，以便在API路由中使用
    app.socketio = socketio
    
    return app, socketio


def setup_logging():
    """Setup application logging."""
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO if not config.DEBUG else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(config.LOGS_DIR, 'app.log')),
            logging.StreamHandler()
        ]
    )
    
    # Set library log levels
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    app_logger = logging.getLogger(__name__)
    app_logger.info("Logging initialized")


def validate_configuration():
    """Validate application configuration."""
    # Validate basic config
    config.validate()
    
    # Validate API keys
    api_status = api_config.validate_api_keys()
    
    logger = logging.getLogger(__name__)
    logger.info(f"Configuration validation: {config.get_env_info()}")
    logger.info(f"API keys status: {api_status}")
    
    # Warn about missing API keys
    if not api_status['deepseek']:
        logger.warning("DeepSeek API key not configured")
    if not api_status['embedding']:
        logger.warning("Embedding API key not configured")
    if not api_status['pubmed_email']:
        logger.warning("PubMed email not configured")


def register_blueprints(app):
    """Register Flask blueprints."""
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(export_bp)  # 注册新的导出路由


def register_error_handlers(app):
    """Register application error handlers."""
    
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger = logging.getLogger(__name__)
        logger.error(f"Internal server error: {str(error)}")
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        logger = logging.getLogger(__name__)
        logger.error(f"Unhandled exception: {str(error)}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500


def initialize_services():
    """Initialize application services."""
    logger = logging.getLogger(__name__)
    
    # Initialize journal database
    try:
        stats = journal_db.get_statistics()
        logger.info(f"Journal database initialized: {stats}")
    except Exception as e:
        logger.error(f"Failed to initialize journal database: {e}")
    
    # Initialize session manager
    try:
        # Cleanup any inactive sessions on startup
        session_manager.cleanup_inactive_sessions()
        logger.info("Session manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize session manager: {e}")
    
    # Initialize async task service
    try:
        from services.academic_analysis_handlers import register_academic_analysis_handlers
        register_academic_analysis_handlers()
        logger.info("Async task service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize async task service: {e}")


def cleanup_on_shutdown():
    """Cleanup function called on application shutdown."""
    logger = logging.getLogger(__name__)
    logger.info("Application shutting down...")
    
    # Cleanup sessions
    try:
        session_manager.cleanup_inactive_sessions(timeout_minutes=0)  # Remove all sessions
        logger.info("Sessions cleaned up")
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")


# Create application instance
app, socketio = create_app()

# Register shutdown handler
import atexit
atexit.register(cleanup_on_shutdown)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.info(f"Starting NNScholar application on {config.HOST}:{config.PORT}")
    logger.info(f"Debug mode: {config.DEBUG}")
    
    try:
        socketio.run(
            app,
            host=config.HOST,
            port=config.PORT,
            debug=config.DEBUG,
            allow_unsafe_werkzeug=True
        )
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise