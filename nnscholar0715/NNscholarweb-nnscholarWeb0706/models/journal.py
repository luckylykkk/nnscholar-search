"""Journal and metrics models."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json
import os

@dataclass
class JournalMetrics:
    """Journal metrics information."""
    journal_name: str
    impact_factor: Optional[float] = None
    five_year_impact_factor: Optional[float] = None
    jcr_quartile: Optional[str] = None
    jcr_category: Optional[str] = None
    cas_quartile: Optional[str] = None
    cas_category: Optional[str] = None
    issn: Optional[str] = None
    eissn: Optional[str] = None
    
    def __post_init__(self):
        """Post-initialization processing."""
        # Normalize journal name
        self.journal_name = self.journal_name.strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'journal_name': self.journal_name,
            'impact_factor': self.impact_factor,
            'five_year_impact_factor': self.five_year_impact_factor,
            'jcr_quartile': self.jcr_quartile,
            'jcr_category': self.jcr_category,
            'cas_quartile': self.cas_quartile,
            'cas_category': self.cas_category,
            'issn': self.issn,
            'eissn': self.eissn
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JournalMetrics':
        """Create from dictionary."""
        return cls(
            journal_name=data.get('journal_name', ''),
            impact_factor=data.get('impact_factor'),
            five_year_impact_factor=data.get('five_year_impact_factor'),
            jcr_quartile=data.get('jcr_quartile'),
            jcr_category=data.get('jcr_category'),
            cas_quartile=data.get('cas_quartile'),
            cas_category=data.get('cas_category'),
            issn=data.get('issn'),
            eissn=data.get('eissn')
        )

@dataclass
class Journal:
    """Journal information with metrics."""
    name: str
    abbr_name: Optional[str] = None
    publisher: Optional[str] = None
    subject_areas: List[str] = field(default_factory=list)
    metrics: Optional[JournalMetrics] = None
    
    def __post_init__(self):
        """Post-initialization processing."""
        self.name = self.name.strip()
        if self.abbr_name:
            self.abbr_name = self.abbr_name.strip()
    
    def get_impact_factor(self) -> Optional[float]:
        """Get impact factor."""
        return self.metrics.impact_factor if self.metrics else None
    
    def get_quartile_info(self) -> Dict[str, Optional[str]]:
        """Get quartile information."""
        if not self.metrics:
            return {'jcr': None, 'cas': None}
        
        return {
            'jcr': self.metrics.jcr_quartile,
            'cas': self.metrics.cas_quartile
        }
    
    def is_high_impact(self, threshold: float = 5.0) -> bool:
        """Check if journal is high impact."""
        if_value = self.get_impact_factor()
        return if_value is not None and if_value >= threshold
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'abbr_name': self.abbr_name,
            'publisher': self.publisher,
            'subject_areas': self.subject_areas,
            'metrics': self.metrics.to_dict() if self.metrics else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Journal':
        """Create from dictionary."""
        metrics = None
        if data.get('metrics'):
            metrics = JournalMetrics.from_dict(data['metrics'])
        
        return cls(
            name=data.get('name', ''),
            abbr_name=data.get('abbr_name'),
            publisher=data.get('publisher'),
            subject_areas=data.get('subject_areas', []),
            metrics=metrics
        )

class JournalDatabase:
    """Journal database manager."""
    
    def __init__(self):
        self.journals: Dict[str, Journal] = {}
        self.name_mapping: Dict[str, str] = {}  # Maps variations to canonical names
        self._load_data()
    
    def _load_data(self):
        """Load journal data from files."""
        try:
            # Load 5-year impact factor data
            five_year_file = 'data/journal_metrics/5year.json'
            if os.path.exists(five_year_file):
                with open(five_year_file, 'r', encoding='utf-8') as f:
                    five_year_data = json.load(f)
                    self._process_five_year_data(five_year_data)
            
            # Load JCR and CAS data
            jcr_cas_file = 'data/journal_metrics/jcr_cas_ifqb.json'
            if os.path.exists(jcr_cas_file):
                with open(jcr_cas_file, 'r', encoding='utf-8') as f:
                    jcr_cas_data = json.load(f)
                    self._process_jcr_cas_data(jcr_cas_data)
                    
        except Exception as e:
            # Use logger if available, otherwise fallback to print
            try:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error loading journal data: {e}")
            except:
                pass  # Silently skip if logging is not available
    
    def _process_five_year_data(self, data: Dict[str, Any]):
        """Process 5-year impact factor data."""
        for journal_name, info in data.items():
            try:
                if journal_name not in self.journals:
                    self.journals[journal_name] = Journal(name=journal_name)
                
                if not self.journals[journal_name].metrics:
                    self.journals[journal_name].metrics = JournalMetrics(journal_name=journal_name)
                
                # Handle the actual data structure from 5year.json
                if isinstance(info, dict):
                    # Extract meta information
                    meta = info.get('meta', {})
                    if meta:
                        self.journals[journal_name].metrics.issn = meta.get('issn')
                        self.journals[journal_name].metrics.eissn = meta.get('eissn')
                    
                    # Extract latest year impact factor
                    data_by_year = info.get('dataByYear', [])
                    if data_by_year and isinstance(data_by_year, list):
                        # Get the most recent year's data
                        latest_data = data_by_year[-1]
                        if isinstance(latest_data, dict):
                            jif = latest_data.get('jif')
                            if jif:
                                try:
                                    self.journals[journal_name].metrics.impact_factor = float(jif)
                                except (ValueError, TypeError):
                                    pass
                            
                            # Set quartile info
                            self.journals[journal_name].metrics.jcr_quartile = latest_data.get('quartile')
                            
                            # Handle categories
                            categories = latest_data.get('category', [])
                            if categories and isinstance(categories, list):
                                category_names = [cat.get('category', '') for cat in categories if isinstance(cat, dict)]
                                if category_names:
                                    self.journals[journal_name].metrics.jcr_category = category_names[0]
                    
                    # Add name variations (journal name itself)
                    self._add_name_mapping(journal_name, [])
                    
            except Exception as e:
                # Skip problematic entries
                continue
    
    def _process_jcr_cas_data(self, data):
        """Process JCR and CAS data."""
        # Handle both dict and list formats
        if isinstance(data, list):
            # Array format: [{"journal": "name", "IF": "value", ...}, ...]
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                journal_name = entry.get('journal', '')
                if not journal_name:
                    continue
                self._process_single_journal_entry(journal_name, entry)
        elif isinstance(data, dict):
            # Dict format: {"journal_name": {"impact_factor": ..., ...}, ...}
            for journal_name, info in data.items():
                self._process_single_journal_entry(journal_name, info)
    
    def _process_single_journal_entry(self, journal_name: str, info: Dict[str, Any]):
        """Process a single journal entry."""
        try:
            if journal_name not in self.journals:
                self.journals[journal_name] = Journal(name=journal_name)
            
            if not self.journals[journal_name].metrics:
                self.journals[journal_name].metrics = JournalMetrics(journal_name=journal_name)
            
            metrics = self.journals[journal_name].metrics
            
            # Handle different possible data structures
            if isinstance(info, dict):
                # Array format from jcr_cas_ifqb.json: {"journal": "name", "IF": "value", "Q": "Q1", ...}
                if 'IF' in info and 'Q' in info:
                    try:
                        metrics.impact_factor = float(info.get('IF', 0))
                    except (ValueError, TypeError):
                        pass
                    metrics.jcr_quartile = info.get('Q')
                    metrics.cas_quartile = info.get('B')  # B field maps to CAS quartile
                    metrics.issn = info.get('issn')
                    metrics.eissn = info.get('eissn')
                    # Add journal abbreviation as variation
                    jabb = info.get('jabb', '')
                    if jabb:
                        self._add_name_mapping(journal_name, [jabb])
                    else:
                        self._add_name_mapping(journal_name, [])
                
                # Standard format
                elif 'impact_factor' in info:
                    metrics.impact_factor = info.get('impact_factor')
                    metrics.jcr_quartile = info.get('jcr_quartile')
                    metrics.jcr_category = info.get('jcr_category')
                    metrics.cas_quartile = info.get('cas_quartile')
                    metrics.cas_category = info.get('cas_category')
                    metrics.issn = info.get('issn')
                    metrics.eissn = info.get('eissn')
                    
                    self._add_name_mapping(journal_name, info.get('variations', []))
                
                # If it's the same format as 5year.json, extract accordingly
                elif 'meta' in info or 'dataByYear' in info:
                    # Already processed in _process_five_year_data
                    pass
                    
        except Exception as e:
            # Skip problematic entries
            pass
    
    def _add_name_mapping(self, canonical_name: str, variations: List[str]):
        """Add name variations to mapping."""
        # Add canonical name
        self.name_mapping[canonical_name.lower()] = canonical_name
        
        # Add variations
        for variation in variations:
            self.name_mapping[variation.lower()] = canonical_name
    
    def find_journal(self, journal_name: str) -> Optional[Journal]:
        """Find journal by name (with fuzzy matching)."""
        if not journal_name:
            return None
        
        # Direct match
        if journal_name in self.journals:
            return self.journals[journal_name]
        
        # Try name mapping
        canonical_name = self.name_mapping.get(journal_name.lower())
        if canonical_name:
            return self.journals.get(canonical_name)
        
        # Fuzzy search
        journal_lower = journal_name.lower()
        for mapped_name, canonical_name in self.name_mapping.items():
            if journal_lower in mapped_name or mapped_name in journal_lower:
                return self.journals.get(canonical_name)
        
        return None
    
    def get_journal_metrics(self, journal_name: str) -> Optional[JournalMetrics]:
        """Get journal metrics by name."""
        journal = self.find_journal(journal_name)
        return journal.metrics if journal else None
    
    def search_journals(self, query: str, limit: int = 10) -> List[Journal]:
        """Search journals by query."""
        if not query:
            return []
        
        query_lower = query.lower()
        matches = []
        
        for journal in self.journals.values():
            if query_lower in journal.name.lower():
                matches.append(journal)
            elif journal.abbr_name and query_lower in journal.abbr_name.lower():
                matches.append(journal)
        
        # Sort by name length (shorter names first, likely more relevant)
        matches.sort(key=lambda j: len(j.name))
        
        return matches[:limit]
    
    def get_high_impact_journals(self, threshold: float = 5.0) -> List[Journal]:
        """Get high impact journals."""
        return [j for j in self.journals.values() if j.is_high_impact(threshold)]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        total_journals = len(self.journals)
        with_metrics = sum(1 for j in self.journals.values() if j.metrics)
        with_if = sum(1 for j in self.journals.values() if j.get_impact_factor())
        
        return {
            'total_journals': total_journals,
            'with_metrics': with_metrics,
            'with_impact_factor': with_if,
            'name_mappings': len(self.name_mapping)
        }
    
    def test_extract_keywords(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Test keyword extraction from papers.
        
        Args:
            papers: List of paper objects with keywords and titles
            
        Returns:
            Test results with different extraction methods
        """
        try:
            from collections import Counter
            import re
            
            # Extract keywords from keyword fields
            from_keywords = []
            for paper in papers:
                keywords = paper.get('keywords', [])
                if keywords:
                    from_keywords.extend([kw.strip().lower() for kw in keywords])
            
            # Extract keywords from titles using simple text processing
            from_titles = []
            for paper in papers:
                title = paper.get('title', '')
                if title:
                    # Simple word extraction (remove common words)
                    words = re.findall(r'\b[a-zA-Z]{3,}\b', title.lower())
                    # Filter out common words
                    stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 
                                'any', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 
                                'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 
                                'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did',
                                'its', 'let', 'put', 'say', 'she', 'too', 'use'}
                    filtered_words = [word for word in words if word not in stop_words]
                    from_titles.extend(filtered_words)
            
            # Count frequencies
            keywords_counter = Counter(from_keywords)
            titles_counter = Counter(from_titles)
            
            # Get top keywords
            top_from_keywords = [{'text': kw, 'value': count} 
                               for kw, count in keywords_counter.most_common(30)]
            top_from_titles = [{'text': word, 'value': count} 
                             for word, count in titles_counter.most_common(30)]
            
            # Find overlap
            keyword_set = set(from_keywords)
            title_set = set(from_titles)
            overlap = keyword_set.intersection(title_set)
            
            return {
                'from_keywords': top_from_keywords,
                'from_titles': top_from_titles,
                'overlap': list(overlap),
                'total_papers': len(papers),
                'papers_with_keywords': sum(1 for p in papers if p.get('keywords')),
                'unique_keywords': len(keywords_counter),
                'unique_title_words': len(titles_counter)
            }
            
        except Exception as e:
            logger.error(f"Error in keyword extraction test: {e}")
            return {
                'error': str(e),
                'from_keywords': [],
                'from_titles': [],
                'overlap': []
            }
    
    def extract_keywords_from_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract keywords from papers for word cloud.
        
        Args:
            papers: List of paper objects
            
        Returns:
            List of keyword objects with text and value
        """
        try:
            from collections import Counter
            
            all_keywords = []
            for paper in papers:
                keywords = paper.get('keywords', [])
                if keywords:
                    all_keywords.extend([kw.strip().lower() for kw in keywords])
            
            # Count and format for word cloud
            counter = Counter(all_keywords)
            
            return [{'text': keyword, 'value': count} 
                   for keyword, count in counter.most_common(50)]
            
        except Exception as e:
            logger.error(f"Error extracting keywords: {e}")
            return []

# Global journal database instance
journal_db = JournalDatabase()