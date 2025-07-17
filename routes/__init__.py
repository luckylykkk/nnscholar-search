"""Route handlers for NNScholar application."""

from .api_routes import api_bp
from .web_routes import web_bp
from .websocket_routes import register_websocket_handlers

__all__ = ['api_bp', 'web_bp', 'register_websocket_handlers']