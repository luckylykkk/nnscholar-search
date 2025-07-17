"""User session models."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

@dataclass
class UserSession:
    """User session information."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    socket_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    # User preferences
    search_preferences: Dict[str, Any] = field(default_factory=dict)
    export_preferences: Dict[str, Any] = field(default_factory=dict)
    
    # Session data
    current_query: Optional[str] = None
    search_results: List[Dict[str, Any]] = field(default_factory=list)
    analysis_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Cache
    cached_papers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cached_embeddings: Dict[str, List[float]] = field(default_factory=dict)
    
    # Statistics
    total_searches: int = 0
    total_exports: int = 0
    total_analyses: int = 0
    
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
    
    def add_search_result(self, query: str, results: List[Dict[str, Any]]):
        """Add search result to session."""
        self.current_query = query
        self.search_results.append({
            'query': query,
            'results': results,
            'timestamp': datetime.now().isoformat(),
            'count': len(results)
        })
        self.total_searches += 1
        self.update_activity()
    
    def add_analysis_result(self, analysis_type: str, result: Dict[str, Any]):
        """Add analysis result to session."""
        self.analysis_results.append({
            'type': analysis_type,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        self.total_analyses += 1
        self.update_activity()
    
    def cache_paper(self, pmid: str, paper_data: Dict[str, Any]):
        """Cache paper data."""
        self.cached_papers[pmid] = paper_data
        self.update_activity()
    
    def get_cached_paper(self, pmid: str) -> Optional[Dict[str, Any]]:
        """Get cached paper data."""
        return self.cached_papers.get(pmid)
    
    def cache_embedding(self, text_hash: str, embedding: List[float]):
        """Cache embedding result."""
        self.cached_embeddings[text_hash] = embedding
        self.update_activity()
    
    def get_cached_embedding(self, text_hash: str) -> Optional[List[float]]:
        """Get cached embedding."""
        return self.cached_embeddings.get(text_hash)
    
    def get_recent_searches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent search queries."""
        return self.search_results[-limit:] if self.search_results else []
    
    def clear_cache(self):
        """Clear session cache."""
        self.cached_papers.clear()
        self.cached_embeddings.clear()
        self.update_activity()
    
    def is_active(self, timeout_minutes: int = 30) -> bool:
        """Check if session is still active."""
        time_diff = datetime.now() - self.last_activity
        return time_diff.total_seconds() < (timeout_minutes * 60)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'session_id': self.session_id,
            'socket_id': self.socket_id,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'search_preferences': self.search_preferences,
            'export_preferences': self.export_preferences,
            'current_query': self.current_query,
            'total_searches': self.total_searches,
            'total_exports': self.total_exports,
            'total_analyses': self.total_analyses,
            'recent_searches': self.get_recent_searches(5)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserSession':
        """Create from dictionary."""
        session = cls(
            session_id=data.get('session_id', str(uuid.uuid4())),
            socket_id=data.get('socket_id'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            last_activity=datetime.fromisoformat(data['last_activity']) if data.get('last_activity') else datetime.now(),
            search_preferences=data.get('search_preferences', {}),
            export_preferences=data.get('export_preferences', {}),
            current_query=data.get('current_query'),
            total_searches=data.get('total_searches', 0),
            total_exports=data.get('total_exports', 0),
            total_analyses=data.get('total_analyses', 0)
        )
        return session

@dataclass
class SessionManager:
    """Manages user sessions."""
    sessions: Dict[str, UserSession] = field(default_factory=dict)
    socket_to_session: Dict[str, str] = field(default_factory=dict)
    
    def create_session(self, socket_id: Optional[str] = None) -> UserSession:
        """Create new user session."""
        session = UserSession(socket_id=socket_id)
        self.sessions[session.session_id] = session
        
        if socket_id:
            self.socket_to_session[socket_id] = session.session_id
        
        return session
    
    def get_session(self, session_id: str) -> Optional[UserSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    def get_session_by_socket(self, socket_id: str) -> Optional[UserSession]:
        """Get session by socket ID."""
        session_id = self.socket_to_session.get(socket_id)
        return self.sessions.get(session_id) if session_id else None
    
    def remove_session(self, session_id: str):
        """Remove session."""
        session = self.sessions.pop(session_id, None)
        if session and session.socket_id:
            self.socket_to_session.pop(session.socket_id, None)
    
    def cleanup_inactive_sessions(self, timeout_minutes: int = 30):
        """Remove inactive sessions."""
        inactive_sessions = [
            session_id for session_id, session in self.sessions.items()
            if not session.is_active(timeout_minutes)
        ]
        
        for session_id in inactive_sessions:
            self.remove_session(session_id)
    
    def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        return sum(1 for session in self.sessions.values() if session.is_active())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get session statistics."""
        active_sessions = [s for s in self.sessions.values() if s.is_active()]
        
        return {
            'total_sessions': len(self.sessions),
            'active_sessions': len(active_sessions),
            'total_searches': sum(s.total_searches for s in self.sessions.values()),
            'total_exports': sum(s.total_exports for s in self.sessions.values()),
            'total_analyses': sum(s.total_analyses for s in self.sessions.values())
        }

# Global session manager instance
session_manager = SessionManager()