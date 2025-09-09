"""Vector database abstraction layer using Weaviate."""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import weaviate
import weaviate.classes as wvc
from weaviate.classes.query import Filter
import uuid
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings
from ..models.schemas import ArgumentSegment, ArgumentBundle

logger = structlog.get_logger()


class VectorDB:
    """Weaviate vector database interface."""
    
    def __init__(self):
        """Initialize Weaviate client."""
        self.client = weaviate.connect_to_local(
            host=settings.weaviate_host,
            port=settings.weaviate_port,
            skip_init_checks=True,  # Skip gRPC health check for local development
        )
        self.class_name = settings.weaviate_class_name
        self.vector_size = settings.weaviate_vector_size
        self._ensure_collection()
    
    def _ensure_collection(self) -> None:
        """Ensure collection exists with proper legal document schema."""
        try:
            if not self.client.collections.exists(self.class_name):
                logger.info(f"Creating collection: {self.class_name}")
                self.client.collections.create(
                    name=self.class_name,
                    vectorizer_config=wvc.config.Configure.Vectorizer.none(),  # Using external embeddings
                    properties=[
                        wvc.config.Property(
                            name="segmentId",
                            data_type=wvc.config.DataType.TEXT,
                            description="Unique segment identifier"
                        ),
                        wvc.config.Property(
                            name="argumentId", 
                            data_type=wvc.config.DataType.TEXT,
                            description="Argument identifier"
                        ),
                        wvc.config.Property(
                            name="text",
                            data_type=wvc.config.DataType.TEXT,
                            description="Legal argument text content"
                        ),
                        wvc.config.Property(
                            name="role",
                            data_type=wvc.config.DataType.TEXT,
                            description="Role in legal argument"
                        ),
                        wvc.config.Property(
                            name="seq",
                            data_type=wvc.config.DataType.INT,
                            description="Sequence number in argument"
                        ),
                        wvc.config.Property(
                            name="citations",
                            data_type=wvc.config.DataType.TEXT_ARRAY,
                            description="Legal citations referenced"
                        ),
                        wvc.config.Property(
                            name="tenant",
                            data_type=wvc.config.DataType.TEXT,
                            description="Multi-tenant identifier"
                        ),
                        wvc.config.Property(
                            name="lawyerId",
                            data_type=wvc.config.DataType.TEXT,
                            description="Lawyer identifier"
                        ),
                        wvc.config.Property(
                            name="lawyer",
                            data_type=wvc.config.DataType.OBJECT,
                            description="Lawyer information"
                        ),
                        wvc.config.Property(
                            name="caseId",
                            data_type=wvc.config.DataType.TEXT,
                            description="Case identifier"
                        ),
                        wvc.config.Property(
                            name="case",
                            data_type=wvc.config.DataType.OBJECT,
                            description="Case information"
                        ),
                        wvc.config.Property(
                            name="caseJurisdiction",
                            data_type=wvc.config.DataType.TEXT,
                            description="Legal jurisdiction"
                        ),
                        wvc.config.Property(
                            name="issueId",
                            data_type=wvc.config.DataType.TEXT,
                            description="Issue identifier"
                        ),
                        wvc.config.Property(
                            name="issue",
                            data_type=wvc.config.DataType.OBJECT,
                            description="Issue information"
                        ),
                        wvc.config.Property(
                            name="stage",
                            data_type=wvc.config.DataType.TEXT,
                            description="Case stage"
                        ),
                        wvc.config.Property(
                            name="disposition",
                            data_type=wvc.config.DataType.TEXT,
                            description="Case disposition"
                        ),
                        wvc.config.Property(
                            name="filedYear",
                            data_type=wvc.config.DataType.INT,
                            description="Year case was filed"
                        ),
                        wvc.config.Property(
                            name="signatureHash",
                            data_type=wvc.config.DataType.TEXT,
                            description="Content signature hash"
                        ),
                        wvc.config.Property(
                            name="src",
                            data_type=wvc.config.DataType.TEXT,
                            description="Source information"
                        )
                    ]
                )
                logger.info(f"Collection {self.class_name} created successfully")
            else:
                logger.info(f"Collection {self.class_name} already exists")
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
        """Upsert argument segments to Weaviate.
        
        Args:
            segments: List of argument segments
            embeddings: Corresponding embeddings
            metadata: Additional metadata for all segments
            
        Returns:
            Success status
        """
        try:
            collection = self.client.collections.get(self.class_name)
            
            objects = []
            for segment, embedding in zip(segments, embeddings):
                # Build properties object
                properties = {
                    "segmentId": segment.segment_id,
                    "argumentId": segment.argument_id,
                    "text": segment.text,
                    "role": segment.role,
                    "seq": segment.seq,
                    "citations": segment.citations,
                    "tenant": metadata.get("tenant", "default"),
                }
                
                # Add lawyer info
                if "lawyer" in metadata:
                    properties["lawyer"] = metadata["lawyer"]
                    properties["lawyerId"] = metadata["lawyer"].get("id", "")
                
                # Add case info
                if "case" in metadata:
                    properties["case"] = metadata["case"]
                    properties["caseId"] = metadata["case"].get("id", "")
                    properties["caseJurisdiction"] = metadata["case"].get("jurisdiction", "")
                
                # Add issue info
                if "issue" in metadata:
                    properties["issue"] = metadata["issue"]
                    properties["issueId"] = metadata["issue"].get("id", "")
                
                # Add other metadata
                for key, prop_name in [
                    ("stage", "stage"),
                    ("disposition", "disposition"),
                    ("filed_year", "filedYear"),
                    ("signature_hash", "signatureHash"),
                    ("src", "src")
                ]:
                    if key in metadata:
                        properties[prop_name] = metadata[key]
                
                # Create data object
                obj = wvc.data.DataObject(
                    properties=properties,
                    vector=embedding
                )
                objects.append(obj)
            
            # Batch insert with error handling
            result = collection.data.insert_many(objects)
            
            # Check for errors
            failed_objects = []
            if hasattr(result, 'errors') and result.errors:
                for uuid, error in result.errors.items():
                    logger.warning(f"Failed to insert object {uuid}: {error}")
                    failed_objects.append(uuid)
            
            success_count = len(objects) - len(failed_objects)
            logger.info(f"Upserted {success_count}/{len(objects)} segments to Weaviate")
            
            return len(failed_objects) == 0
            
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
        """Search for similar segments with hybrid search capabilities.
        
        Args:
            query_embedding: Query vector
            filters: Filter conditions
            limit: Maximum results
            score_threshold: Minimum similarity score
            
        Returns:
            List of (payload, score) tuples
        """
        try:
            collection = self.client.collections.get(self.class_name)
            
            # Build Weaviate filters
            where_filter = None
            if filters:
                conditions = []
                
                # Must conditions (required)
                filter_mappings = {
                    "tenant": "tenant",
                    "lawyer.id": "lawyerId", 
                    "case.jurisdiction": "caseJurisdiction",
                    "issue.id": "issueId",
                    "case.judge_id": "case.judgeId",
                    "stage": "stage",
                    "disposition": "disposition"
                }
                
                for filter_key, prop_name in filter_mappings.items():
                    if filter_key in filters:
                        value = filters[filter_key]
                        if filter_key == "issue.id" and isinstance(value, list):
                            # Handle expanded issue IDs with OR condition
                            issue_conditions = []
                            for issue_id in value:
                                issue_conditions.append(
                                    Filter.by_property(prop_name).equal(issue_id)
                                )
                            if issue_conditions:
                                # Combine with OR
                                issue_filter = issue_conditions[0]
                                for cond in issue_conditions[1:]:
                                    issue_filter = issue_filter | cond
                                conditions.append(issue_filter)
                        else:
                            conditions.append(Filter.by_property(prop_name).equal(value))
                
                # Range conditions for filed year
                if "filed_year" in filters:
                    filed_year = filters["filed_year"]
                    if isinstance(filed_year, dict):
                        if "gte" in filed_year:
                            conditions.append(
                                Filter.by_property("filedYear").greater_or_equal(filed_year["gte"])
                            )
                        if "lte" in filed_year:
                            conditions.append(
                                Filter.by_property("filedYear").less_or_equal(filed_year["lte"])
                            )
                        if "gt" in filed_year:
                            conditions.append(
                                Filter.by_property("filedYear").greater_than(filed_year["gt"])
                            )
                        if "lt" in filed_year:
                            conditions.append(
                                Filter.by_property("filedYear").less_than(filed_year["lt"])
                            )
                    else:
                        conditions.append(
                            Filter.by_property("filedYear").greater_or_equal(filed_year)
                        )
                
                # Combine all conditions with AND
                if conditions:
                    where_filter = conditions[0]
                    for condition in conditions[1:]:
                        where_filter = where_filter & condition
            
            # Perform vector search
            response = collection.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                where=where_filter,
                return_metadata=wvc.query.MetadataQuery(score=True, distance=True)
            )
            
            # Extract results and convert to expected format
            results = []
            for obj in response.objects:
                # Convert properties back to original format
                payload = dict(obj.properties)
                
                # Convert back to original field names for compatibility
                if "segmentId" in payload:
                    payload["segment_id"] = payload.pop("segmentId")
                if "argumentId" in payload:
                    payload["argument_id"] = payload.pop("argumentId")
                if "lawyerId" in payload:
                    payload.pop("lawyerId", None)  # Keep only full lawyer object
                if "caseId" in payload:
                    payload.pop("caseId", None)  # Keep only full case object
                if "caseJurisdiction" in payload:
                    payload.pop("caseJurisdiction", None)  # Will be in case object
                if "issueId" in payload:
                    payload.pop("issueId", None)  # Keep only full issue object
                if "filedYear" in payload:
                    payload["filed_year"] = payload.pop("filedYear")
                if "signatureHash" in payload:
                    payload["signature_hash"] = payload.pop("signatureHash")
                
                # Calculate similarity score (Weaviate returns distance, convert to similarity)
                distance = obj.metadata.distance if obj.metadata and obj.metadata.distance else 0.0
                score = 1.0 - distance  # Convert distance to similarity
                
                # Apply score threshold
                if score_threshold and score < score_threshold:
                    continue
                    
                results.append((payload, score))
            
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
            collection = self.client.collections.get(self.class_name)
            
            # Create filter for segment IDs
            if not segment_ids:
                return []
            
            # Build OR filter for multiple segment IDs
            filters = []
            for segment_id in segment_ids:
                filters.append(Filter.by_property("segmentId").equal(segment_id))
            
            # Combine with OR
            where_filter = filters[0]
            for f in filters[1:]:
                where_filter = where_filter | f
            
            # Query with filter
            response = collection.query.fetch_objects(
                where=where_filter,
                limit=len(segment_ids)
            )
            
            # Convert results
            results = []
            for obj in response.objects:
                payload = dict(obj.properties)
                
                # Convert field names back for compatibility
                if "segmentId" in payload:
                    payload["segment_id"] = payload.pop("segmentId")
                if "argumentId" in payload:
                    payload["argument_id"] = payload.pop("argumentId")
                if "filedYear" in payload:
                    payload["filed_year"] = payload.pop("filedYear")
                if "signatureHash" in payload:
                    payload["signature_hash"] = payload.pop("signatureHash")
                
                results.append(payload)
            
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
            collection = self.client.collections.get(self.class_name)
            
            # Build filter conditions
            conditions = []
            for key, value in filters.items():
                # Map to Weaviate property names
                prop_name = key
                if key == "segment_id":
                    prop_name = "segmentId"
                elif key == "argument_id":
                    prop_name = "argumentId"
                elif key == "filed_year":
                    prop_name = "filedYear"
                elif key == "signature_hash":
                    prop_name = "signatureHash"
                
                conditions.append(Filter.by_property(prop_name).equal(value))
            
            if conditions:
                # Combine conditions with AND
                where_filter = conditions[0]
                for condition in conditions[1:]:
                    where_filter = where_filter & condition
                
                # Delete objects matching filter
                result = collection.data.delete_many(where=where_filter)
                
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
            collection = self.client.collections.get(self.class_name)
            
            # Get collection configuration
            config = collection.config.get()
            
            # Get collection stats (approximate)
            agg_result = collection.aggregate.over_all(
                total_count=True
            )
            
            return {
                "name": self.class_name,
                "vector_size": self.vector_size,
                "points_count": agg_result.total_count if agg_result else 0,
                "status": "ready",
                "vectorizer": config.vectorizer_config.vectorizer if config.vectorizer_config else "none",
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
            # Weaviate doesn't have the same snapshot concept as Qdrant
            # This would typically be handled at the cluster level
            # For now, return a simulated snapshot name
            import datetime
            snapshot_name = snapshot_name or f"weaviate_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Weaviate snapshot concept differs from Qdrant - use cluster-level backups")
            logger.info(f"Simulated snapshot name: {snapshot_name}")
            return snapshot_name
        except Exception as e:
            logger.error(f"Error creating snapshot: {e}")
            raise
    
    def close(self):
        """Close the Weaviate client connection."""
        try:
            self.client.close()
            logger.info("Weaviate client connection closed")
        except Exception as e:
            logger.error(f"Error closing Weaviate client: {e}")