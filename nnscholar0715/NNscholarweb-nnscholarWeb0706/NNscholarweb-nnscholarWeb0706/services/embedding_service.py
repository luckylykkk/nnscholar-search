"""Embedding service for semantic similarity calculations."""

import requests
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import logging
import time
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

from config.api_config import api_config
from utils.cache_utils import cache_result, RateLimiter
from utils.text_processing import preprocess_text, get_text_hash

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating and managing text embeddings."""
    
    def __init__(self):
        self.api_url = api_config.EMBEDDING_API_URL
        self.api_key = api_config.EMBEDDING_API_KEY
        self.model = api_config.EMBEDDING_MODEL
        self.dimension = api_config.EMBEDDING_DIMENSION
        
        self.rate_limiter = RateLimiter(
            max_requests=api_config.EMBEDDING_RPM,
            window_seconds=60
        )
        
        # Fallback TF-IDF vectorizer
        self.tfidf_vectorizer = None
        
        if not self.api_key:
            logger.warning("Embedding API key not configured, will use TF-IDF fallback")
    
    @cache_result(ttl=3600)  # Cache embeddings for 1 hour
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for a single text.
        
        Args:
            text: Input text
        
        Returns:
            Embedding vector or None if failed
        """
        if not text or not text.strip():
            return None
        
        # Try API first if available
        if self.api_key:
            try:
                return self._get_api_embedding(text)
            except Exception as e:
                logger.warning(f"API embedding failed, falling back to TF-IDF: {e}")
        
        # Fallback to TF-IDF
        return self._get_tfidf_embedding(text)
    
    def get_embeddings_batch(self, texts: List[str], 
                           batch_size: int = None) -> List[Optional[List[float]]]:
        """Get embeddings for multiple texts.
        
        Args:
            texts: List of input texts
            batch_size: Size of each batch for API calls (defaults to config value)
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Use configured batch size if not specified
        if batch_size is None:
            batch_size = api_config.EMBEDDING_BATCH_SIZE
        
        embeddings = []
        
        if self.api_key:
            # Process in batches for API
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    batch_embeddings = self._get_api_embeddings_batch(batch)
                    embeddings.extend(batch_embeddings)
                except Exception as e:
                    logger.warning(f"Batch API embedding failed: {e}")
                    # Fallback to individual TF-IDF
                    for text in batch:
                        embeddings.append(self._get_tfidf_embedding(text))
        else:
            # Use TF-IDF for all
            embeddings = self._get_tfidf_embeddings_batch(texts)
        
        return embeddings
    
    def _get_api_embedding(self, text: str) -> List[float]:
        """Get embedding from API.
        
        Args:
            text: Input text
        
        Returns:
            Embedding vector
        """
        # Rate limiting
        if not self.rate_limiter.is_allowed('embedding'):
            logger.warning("Rate limit exceeded for embedding API")
            time.sleep(1)
        
        # Preprocess text
        clean_text = preprocess_text(text)
        if not clean_text:
            raise ValueError("Empty text after preprocessing")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': self.model,
            'input': clean_text
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=api_config.REQUEST_TIMEOUT
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'data' in result and len(result['data']) > 0:
                embedding = result['data'][0]['embedding']
                logger.debug(f"Got API embedding with dimension {len(embedding)}")
                return embedding
            else:
                raise ValueError("Invalid API response format")
                
        except requests.RequestException as e:
            logger.error(f"Embedding API request failed: {e}")
            raise Exception(f"Embedding API error: {str(e)}")
    
    def _get_api_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts from API.
        
        Args:
            texts: List of input texts
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Rate limiting
        if not self.rate_limiter.is_allowed('embedding_batch'):
            logger.warning("Rate limit exceeded for embedding API")
            time.sleep(1)
        
        # Preprocess texts
        clean_texts = [preprocess_text(text) for text in texts]
        clean_texts = [text for text in clean_texts if text]  # Remove empty
        
        if not clean_texts:
            return [None] * len(texts)
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': self.model,
            'input': clean_texts
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=api_config.REQUEST_TIMEOUT * 2  # Longer timeout for batch
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'data' in result:
                embeddings = [item['embedding'] for item in result['data']]
                logger.debug(f"Got {len(embeddings)} API embeddings")
                return embeddings
            else:
                raise ValueError("Invalid API response format")
                
        except requests.RequestException as e:
            logger.error(f"Batch embedding API request failed: {e}")
            raise Exception(f"Batch embedding API error: {str(e)}")
    
    def _get_tfidf_embedding(self, text: str) -> List[float]:
        """Get TF-IDF based embedding for single text.
        
        Args:
            text: Input text
        
        Returns:
            TF-IDF vector as embedding
        """
        try:
            clean_text = preprocess_text(text)
            if not clean_text:
                return [0.0] * 384  # Return zero vector with standard dimension
            
            # Use a simple TF-IDF approach for single text
            if self.tfidf_vectorizer is None:
                self.tfidf_vectorizer = TfidfVectorizer(
                    max_features=384,  # Fixed dimension
                    ngram_range=(1, 2),
                    stop_words='english'
                )
                # Initialize with dummy data
                self.tfidf_vectorizer.fit([clean_text, "dummy text for initialization"])
            
            vector = self.tfidf_vectorizer.transform([clean_text])
            embedding = vector.toarray()[0].tolist()
            
            logger.debug(f"Generated TF-IDF embedding with dimension {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"TF-IDF embedding generation failed: {e}")
            return [0.0] * 384  # Return zero vector
    
    def _get_tfidf_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get TF-IDF based embeddings for multiple texts.
        
        Args:
            texts: List of input texts
        
        Returns:
            List of TF-IDF vectors
        """
        try:
            clean_texts = [preprocess_text(text) for text in texts]
            clean_texts = [text if text else "empty" for text in clean_texts]  # Handle empty texts
            
            # Create TF-IDF vectorizer
            vectorizer = TfidfVectorizer(
                max_features=384,  # Fixed dimension
                ngram_range=(1, 2),
                stop_words='english',
                min_df=1
            )
            
            # Fit and transform
            tfidf_matrix = vectorizer.fit_transform(clean_texts)
            embeddings = tfidf_matrix.toarray().tolist()
            
            logger.debug(f"Generated {len(embeddings)} TF-IDF embeddings")
            return embeddings
            
        except Exception as e:
            logger.error(f"Batch TF-IDF embedding generation failed: {e}")
            # Return zero vectors
            return [[0.0] * 384 for _ in texts]
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts.
        
        Args:
            text1: First text
            text2: Second text
        
        Returns:
            Similarity score (0-1)
        """
        try:
            # Get embeddings
            emb1 = self.get_embedding(text1)
            emb2 = self.get_embedding(text2)
            
            if emb1 is None or emb2 is None:
                return 0.0
            
            # Calculate cosine similarity
            similarity = cosine_similarity([emb1], [emb2])[0][0]
            
            # Ensure result is between 0 and 1
            return max(0.0, min(1.0, similarity))
            
        except Exception as e:
            logger.error(f"Similarity calculation failed: {e}")
            return 0.0
    
    def calculate_relevance_scores(self, query: str, documents: List[str]) -> List[float]:
        """Calculate relevance scores for documents against query.
        
        Args:
            query: Search query
            documents: List of document texts
        
        Returns:
            List of relevance scores
        """
        try:
            if not documents:
                return []
            
            # Get query embedding
            query_embedding = self.get_embedding(query)
            if query_embedding is None:
                return [0.0] * len(documents)
            
            # Get document embeddings
            doc_embeddings = self.get_embeddings_batch(documents)
            
            # Calculate similarities
            scores = []
            for doc_emb in doc_embeddings:
                if doc_emb is None:
                    scores.append(0.0)
                else:
                    try:
                        similarity = cosine_similarity([query_embedding], [doc_emb])[0][0]
                        scores.append(max(0.0, min(1.0, similarity)))
                    except Exception:
                        scores.append(0.0)
            
            logger.debug(f"Calculated relevance scores for {len(documents)} documents")
            return scores
            
        except Exception as e:
            logger.error(f"Relevance score calculation failed: {e}")
            return [0.0] * len(documents)
    
    def find_similar_papers(self, query_paper: Dict[str, Any], 
                          candidate_papers: List[Dict[str, Any]], 
                          top_k: int = 10) -> List[Tuple[int, float]]:
        """Find papers similar to query paper.
        
        Args:
            query_paper: Query paper information
            candidate_papers: List of candidate papers
            top_k: Number of top similar papers to return
        
        Returns:
            List of (paper_index, similarity_score) tuples
        """
        try:
            if not candidate_papers:
                return []
            
            # Prepare query text
            query_text = self._prepare_paper_text(query_paper)
            
            # Prepare candidate texts
            candidate_texts = [self._prepare_paper_text(paper) for paper in candidate_papers]
            
            # Calculate relevance scores
            scores = self.calculate_relevance_scores(query_text, candidate_texts)
            
            # Create (index, score) pairs and sort
            paper_scores = [(i, score) for i, score in enumerate(scores)]
            paper_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Return top k
            return paper_scores[:top_k]
            
        except Exception as e:
            logger.error(f"Similar paper search failed: {e}")
            return []
    
    def _prepare_paper_text(self, paper: Dict[str, Any]) -> str:
        """Prepare paper text for embedding.
        
        Args:
            paper: Paper information
        
        Returns:
            Combined text for embedding
        """
        text_parts = []
        
        # Title (highest weight)
        title = paper.get('title', '')
        if title:
            text_parts.append(title + " " + title)  # Duplicate for emphasis
        
        # Abstract
        abstract = paper.get('abstract', '')
        if abstract:
            text_parts.append(abstract)
        
        # Keywords
        keywords = paper.get('keywords', [])
        if keywords:
            keyword_text = ' '.join(keywords)
            text_parts.append(keyword_text)
        
        # MeSH terms
        mesh_terms = paper.get('mesh_terms', [])
        if mesh_terms:
            mesh_text = ' '.join(mesh_terms)
            text_parts.append(mesh_text)
        
        return ' '.join(text_parts)
    
    def cluster_papers(self, papers: List[Dict[str, Any]], 
                      n_clusters: int = 5) -> Dict[str, Any]:
        """Cluster papers based on semantic similarity.
        
        Args:
            papers: List of paper information
            n_clusters: Number of clusters
        
        Returns:
            Clustering results
        """
        try:
            if len(papers) < n_clusters:
                logger.warning(f"Not enough papers ({len(papers)}) for {n_clusters} clusters")
                n_clusters = max(1, len(papers) // 2)
            
            # Prepare texts
            paper_texts = [self._prepare_paper_text(paper) for paper in papers]
            
            # Get embeddings
            embeddings = self.get_embeddings_batch(paper_texts)
            
            # Filter out None embeddings
            valid_embeddings = []
            valid_indices = []
            for i, emb in enumerate(embeddings):
                if emb is not None:
                    valid_embeddings.append(emb)
                    valid_indices.append(i)
            
            if len(valid_embeddings) < n_clusters:
                return {"error": "Not enough valid embeddings for clustering"}
            
            # Perform clustering
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(valid_embeddings)
            
            # Organize results
            clusters = {}
            for i, label in enumerate(cluster_labels):
                paper_idx = valid_indices[i]
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append({
                    'paper_index': paper_idx,
                    'title': papers[paper_idx].get('title', ''),
                    'journal': papers[paper_idx].get('journal', '')
                })
            
            return {
                'n_clusters': n_clusters,
                'clusters': clusters,
                'total_papers': len(papers),
                'clustered_papers': len(valid_indices)
            }
            
        except Exception as e:
            logger.error(f"Paper clustering failed: {e}")
            return {"error": f"Clustering failed: {str(e)}"}
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get service status and statistics.
        
        Returns:
            Service status information
        """
        return {
            "service": "Embedding",
            "api_url": self.api_url,
            "model": self.model,
            "dimension": self.dimension,
            "api_key_configured": bool(self.api_key),
            "rate_limit_remaining": self.rate_limiter.get_remaining('embedding'),
            "fallback_available": True,  # TF-IDF always available
            "tfidf_vectorizer_initialized": self.tfidf_vectorizer is not None
        }


# Global service instance
embedding_service = EmbeddingService()