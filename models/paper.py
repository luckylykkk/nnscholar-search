"""Paper and document models."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class Paper:
    """Basic paper information model."""
    pmid: str
    title: str
    authors: List[str] = field(default_factory=list)
    journal: str = ""
    pub_date: str = ""
    pub_year: Optional[int] = None
    abstract: str = ""
    doi: Optional[str] = None
    url: Optional[str] = None
    
    def __post_init__(self):
        """Post-initialization processing."""
        if self.url is None and self.pmid:
            self.url = f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'pmid': self.pmid,
            'title': self.title,
            'authors': self.authors,
            'journal': self.journal,
            'pub_date': self.pub_date,
            'pub_year': self.pub_year,
            'abstract': self.abstract,
            'doi': self.doi,
            'url': self.url
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Paper':
        """Create from dictionary."""
        return cls(
            pmid=data.get('pmid', ''),
            title=data.get('title', ''),
            authors=data.get('authors', []),
            journal=data.get('journal', ''),
            pub_date=data.get('pub_date', ''),
            pub_year=data.get('pub_year'),
            abstract=data.get('abstract', ''),
            doi=data.get('doi'),
            url=data.get('url')
        )

@dataclass
class PaperDetail(Paper):
    """Detailed paper information with analysis data."""
    keywords: List[str] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    publication_types: List[str] = field(default_factory=list)
    
    # Journal metrics
    impact_factor: Optional[float] = None
    jcr_quartile: Optional[str] = None
    cas_quartile: Optional[str] = None
    
    # Journal information
    journal_info: Optional[Dict[str, Any]] = None
    
    # Analysis results
    relevance_score: Optional[float] = None
    relevance_reason: Optional[str] = None
    
    # Processing metadata
    processed_at: Optional[datetime] = None
    processing_time: Optional[float] = None
    
    def __post_init__(self):
        """Post-initialization processing."""
        super().__post_init__()
        if self.processed_at is None:
            self.processed_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        base_dict = super().to_dict()
        base_dict.update({
            'keywords': self.keywords,
            'mesh_terms': self.mesh_terms,
            'publication_types': self.publication_types,
            'impact_factor': self.impact_factor,
            'jcr_quartile': self.jcr_quartile,
            'cas_quartile': self.cas_quartile,
            'journal_info': self.journal_info,
            'relevance_score': self.relevance_score,
            'relevance_reason': self.relevance_reason,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'processing_time': self.processing_time
        })
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PaperDetail':
        """Create from dictionary."""
        processed_at = None
        if data.get('processed_at'):
            processed_at = datetime.fromisoformat(data['processed_at'])
        
        return cls(
            pmid=data.get('pmid', ''),
            title=data.get('title', ''),
            authors=data.get('authors', []),
            journal=data.get('journal', ''),
            pub_date=data.get('pub_date', ''),
            pub_year=data.get('pub_year'),
            abstract=data.get('abstract', ''),
            doi=data.get('doi'),
            url=data.get('url'),
            keywords=data.get('keywords', []),
            mesh_terms=data.get('mesh_terms', []),
            publication_types=data.get('publication_types', []),
            impact_factor=data.get('impact_factor'),
            jcr_quartile=data.get('jcr_quartile'),
            cas_quartile=data.get('cas_quartile'),
            journal_info=data.get('journal_info'),
            relevance_score=data.get('relevance_score'),
            relevance_reason=data.get('relevance_reason'),
            processed_at=processed_at,
            processing_time=data.get('processing_time')
        )

@dataclass
class SearchResult:
    """Search result container."""
    papers: List[PaperDetail] = field(default_factory=list)
    total_count: int = 0
    search_query: str = ""
    search_time: Optional[float] = None
    filters_applied: Dict[str, Any] = field(default_factory=dict)
    
    def add_paper(self, paper: PaperDetail):
        """Add paper to results."""
        self.papers.append(paper)
        self.total_count += 1
    
    def get_papers_by_relevance(self, min_score: float = 0.5) -> List[PaperDetail]:
        """Get papers filtered by relevance score."""
        return [
            paper for paper in self.papers 
            if paper.relevance_score is not None and paper.relevance_score >= min_score
        ]
    
    def get_papers_by_journal(self, journal_name: str) -> List[PaperDetail]:
        """Get papers from specific journal."""
        return [
            paper for paper in self.papers 
            if journal_name.lower() in paper.journal.lower()
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'papers': [paper.to_dict() for paper in self.papers],
            'total_count': self.total_count,
            'search_query': self.search_query,
            'search_time': self.search_time,
            'filters_applied': self.filters_applied
        }