"""Vector database abstraction layer using Qdrant."""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    Range,
    SearchRequest,
    ScoredPoint,
    UpdateStatus,
)
from qdrant_client.http import models
import uuid
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings
from ..models.schemas import ArgumentSegment, ArgumentBundle

logger = structlog.get_logger()


class VectorDB:
    """Qdrant vector database interface."""
    
    def __init__(self):
        """Initialize Qdrant client."""
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
        self.collection_name = settings.qdrant_collection_name
        self.vector_size = settings.qdrant_vector_size
        self._ensure_collection()
    
    def _ensure_collection(self) -> None:
        """Ensure collection exists with proper configuration."""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE,
                    ),
                    hnsw_config=models.HnswConfigDiff(
                        m=32,
                        ef_construct=256,
                        full_scan_threshold=10000,
                    ),
                    optimizers_config=models.OptimizersConfigDiff(
                        default_segment_number=6,
                        indexing_threshold=20000,
                    ),
                    quantization_config=models.ScalarQuantization(
                        scalar=models.ScalarQuantizationConfig(
                            type=models.ScalarType.INT8,
                            always_ram=True,
                        ),
                    ),
                )
                logger.info(f"Collection {self.collection_name} created successfully")
            else:
                logger.info(f"Collection {self.collection_name} already exists")
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def upsert_segments(
        self,
        segments: List[ArgumentSegment],
        embeddings: List[List[float]],
        metadata: Dict[str, Any],
    ) -> bool:
        """Upsert argument segments to vector database.
        
        Args:
            segments: List of argument segments
            embeddings: Corresponding embeddings
            metadata: Additional metadata for all segments
            
        Returns:
            Success status
        """
        try:
            points = []
            for segment, embedding in zip(segments, embeddings):
                point_id = str(uuid.uuid4())
                
                payload = {
                    "segment_id": segment.segment_id,
                    "argument_id": segment.argument_id,
                    "text": segment.text,
                    "role": segment.role,
                    "seq": segment.seq,
                    "citations": segment.citations,
                    "tenant": metadata.get("tenant", "default"),
                }
                
                # Add lawyer info
                if "lawyer" in metadata:
                    payload["lawyer"] = metadata["lawyer"]
                
                # Add case info
                if "case" in metadata:
                    payload["case"] = metadata["case"]
                
                # Add issue info
                if "issue" in metadata:
                    payload["issue"] = metadata["issue"]
                
                # Add other metadata
                for key in ["stage", "disposition", "filed_year", "signature_hash", "src"]:
                    if key in metadata:
                        payload[key] = metadata[key]
                
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload,
                    )
                )
            
            # Batch upsert
            operation_info = self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            
            logger.info(f"Upserted {len(points)} segments to vector database")
            return operation_info.status == UpdateStatus.COMPLETED
            
        except Exception as e:
            logger.error(f"Error upserting segments: {e}")
            raise
    
    def search_similar(
        self,
        query_embedding: List[float],
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        score_threshold: Optional[float] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Search for similar segments with filters.
        
        Args:
            query_embedding: Query vector
            filters: Filter conditions
            limit: Maximum results
            score_threshold: Minimum similarity score
            
        Returns:
            List of (payload, score) tuples
        """
        try:
            # Build filter conditions
            must_conditions = []
            should_conditions = []
            
            if filters:
                # Must conditions (required)
                for key in ["tenant", "lawyer.id", "case.jurisdiction", "issue.id"]:
                    if key in filters:
                        if key == "issue.id" and isinstance(filters[key], list):
                            # Handle expanded issue IDs
                            must_conditions.append(
                                FieldCondition(
                                    key=key,
                                    match=MatchAny(any=filters[key]),
                                )
                            )
                        else:
                            must_conditions.append(
                                FieldCondition(
                                    key=key,
                                    match=MatchValue(value=filters[key]),
                                )
                            )
                
                # Range conditions
                if "filed_year" in filters:
                    if isinstance(filters["filed_year"], dict):
                        must_conditions.append(
                            FieldCondition(
                                key="filed_year",
                                range=Range(**filters["filed_year"]),
                            )
                        )
                    else:
                        must_conditions.append(
                            FieldCondition(
                                key="filed_year",
                                range=Range(gte=filters["filed_year"]),
                            )
                        )
                
                # Should conditions (optional boosts)
                for key in ["case.judge_id", "stage", "disposition"]:
                    if key in filters:
                        should_conditions.append(
                            FieldCondition(
                                key=key,
                                match=MatchValue(value=filters[key]),
                            )
                        )
            
            # Construct filter
            search_filter = None
            if must_conditions or should_conditions:
                filter_dict = {}
                if must_conditions:
                    filter_dict["must"] = must_conditions
                if should_conditions:
                    filter_dict["should"] = should_conditions
                search_filter = Filter(**filter_dict)
            
            # Perform search
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            
            # Extract results
            results = []
            for point in search_result:
                results.append((point.payload, point.score))
            
            logger.info(f"Found {len(results)} similar segments")
            return results
            
        except Exception as e:
            logger.error(f"Error searching segments: {e}")
            raise
    
    def get_by_ids(self, segment_ids: List[str]) -> List[Dict[str, Any]]:
        """Retrieve segments by IDs.
        
        Args:
            segment_ids: List of segment IDs
            
        Returns:
            List of segment payloads
        """
        try:
            # Search by segment_id in payload
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="segment_id",
                        match=MatchAny(any=segment_ids),
                    )
                ]
            )
            
            # Scroll through all matching points
            points = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=filter_condition,
                limit=len(segment_ids),
                with_payload=True,
                with_vectors=False,
            )[0]
            
            results = [point.payload for point in points]
            logger.info(f"Retrieved {len(results)} segments by IDs")
            return results
            
        except Exception as e:
            logger.error(f"Error retrieving segments by IDs: {e}")
            raise
    
    def delete_by_filter(self, filters: Dict[str, Any]) -> bool:
        """Delete segments matching filters.
        
        Args:
            filters: Filter conditions
            
        Returns:
            Success status
        """
        try:
            conditions = []
            for key, value in filters.items():
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )
            
            if conditions:
                filter_obj = Filter(must=conditions)
                
                result = self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=models.FilterSelector(
                        filter=filter_obj,
                    ),
                    wait=True,
                )
                
                logger.info(f"Deleted segments with filters: {filters}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting segments: {e}")
            raise
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics and info.
        
        Returns:
            Collection information
        """
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": info.name,
                "vector_size": info.config.params.vectors.size,
                "points_count": info.points_count,
                "segments_count": info.segments_count,
                "status": info.status,
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            raise
    
    def create_snapshot(self, snapshot_name: Optional[str] = None) -> str:
        """Create collection snapshot for backup.
        
        Args:
            snapshot_name: Optional snapshot name
            
        Returns:
            Snapshot name
        """
        try:
            result = self.client.create_snapshot(
                collection_name=self.collection_name,
                wait=True,
            )
            logger.info(f"Created snapshot: {result}")
            return result.name
        except Exception as e:
            logger.error(f"Error creating snapshot: {e}")
            raise