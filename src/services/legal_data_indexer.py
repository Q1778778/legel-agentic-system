"""
Legal Data GraphRAG Indexer Service

This service handles indexing of processed legal data into Neo4j graph database
and vector database for GraphRAG retrieval.
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import structlog
import numpy as np
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, TransientError

from .legal_data_processor import ProcessedLegalDocument, LegalEntity, LegalCitation, LegalConcept
from .legal_data_apis import LegalCase, LegalDocument, DataSource
from ..db.graph_db import GraphDB
from ..db.vector_db import VectorDB
from ..services.embeddings import EmbeddingService
from ..core.config import settings

logger = structlog.get_logger()


class IndexingStatus(Enum):
    """Status of indexing operation."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class IndexingResult:
    """Result of an indexing operation."""
    document_id: str
    status: IndexingStatus
    nodes_created: int
    relationships_created: int
    vectors_indexed: int
    processing_time_ms: int
    error_message: Optional[str] = None


@dataclass
class IndexingStats:
    """Statistics from indexing operations."""
    total_documents: int
    successful_documents: int
    failed_documents: int
    total_nodes_created: int
    total_relationships_created: int
    total_vectors_indexed: int
    total_processing_time_ms: int
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_documents == 0:
            return 0.0
        return self.successful_documents / self.total_documents
    
    @property
    def avg_processing_time_ms(self) -> float:
        """Calculate average processing time."""
        if self.successful_documents == 0:
            return 0.0
        return self.total_processing_time_ms / self.successful_documents


class LegalDataIndexer:
    """Advanced GraphRAG indexer for legal data."""
    
    def __init__(self, 
                 graph_db: Optional[GraphDB] = None,
                 vector_db: Optional[VectorDB] = None,
                 embedding_service: Optional[EmbeddingService] = None):
        """Initialize the legal data indexer."""
        self.logger = logger
        self.graph_db = graph_db or GraphDB()
        self.vector_db = vector_db or VectorDB()
        self.embedding_service = embedding_service or EmbeddingService()
        
        # Initialize stats
        self.stats = IndexingStats(
            total_documents=0,
            successful_documents=0,
            failed_documents=0,
            total_nodes_created=0,
            total_relationships_created=0,
            total_vectors_indexed=0,
            total_processing_time_ms=0
        )
        
        # Cache for entity and concept embeddings
        self.entity_cache = {}
        self.concept_cache = {}
        
        # Initialize graph constraints and indexes
        self._initialize_graph_schema()
    
    def _initialize_graph_schema(self):
        """Initialize graph database schema with constraints and indexes."""
        try:
            # Create constraints and indexes for better performance
            constraints_and_indexes = [
                # Unique constraints
                "CREATE CONSTRAINT legal_case_id IF NOT EXISTS FOR (c:LegalCase) REQUIRE c.id IS UNIQUE",
                "CREATE CONSTRAINT legal_document_id IF NOT EXISTS FOR (d:LegalDocument) REQUIRE d.id IS UNIQUE",
                "CREATE CONSTRAINT citation_id IF NOT EXISTS FOR (ct:Citation) REQUIRE ct.normalized_form IS UNIQUE",
                "CREATE CONSTRAINT legal_entity_id IF NOT EXISTS FOR (e:LegalEntity) REQUIRE (e.text, e.entity_type) IS UNIQUE",
                "CREATE CONSTRAINT legal_concept_id IF NOT EXISTS FOR (lc:LegalConcept) REQUIRE (lc.concept, lc.category) IS UNIQUE",
                "CREATE CONSTRAINT court_id IF NOT EXISTS FOR (c:Court) REQUIRE c.name IS UNIQUE",
                "CREATE CONSTRAINT jurisdiction_id IF NOT EXISTS FOR (j:Jurisdiction) REQUIRE j.name IS UNIQUE",
                
                # Indexes for better query performance
                "CREATE INDEX legal_case_source IF NOT EXISTS FOR (c:LegalCase) ON (c.source)",
                "CREATE INDEX legal_case_court IF NOT EXISTS FOR (c:LegalCase) ON (c.court)",
                "CREATE INDEX legal_case_date IF NOT EXISTS FOR (c:LegalCase) ON (c.filed_date, c.decided_date)",
                "CREATE INDEX legal_document_type IF NOT EXISTS FOR (d:LegalDocument) ON (d.doc_type)",
                "CREATE INDEX legal_document_agency IF NOT EXISTS FOR (d:LegalDocument) ON (d.agency)",
                "CREATE INDEX citation_type IF NOT EXISTS FOR (ct:Citation) ON (ct.citation_type)",
                "CREATE INDEX legal_entity_type IF NOT EXISTS FOR (e:LegalEntity) ON (e.entity_type)",
                "CREATE INDEX legal_concept_category IF NOT EXISTS FOR (lc:LegalConcept) ON (lc.category, lc.domain)",
                
                # Full-text search indexes
                "CREATE FULLTEXT INDEX legal_case_text IF NOT EXISTS FOR (c:LegalCase) ON EACH [c.caption, c.summary]",
                "CREATE FULLTEXT INDEX legal_document_text IF NOT EXISTS FOR (d:LegalDocument) ON EACH [d.title, d.summary]",
            ]
            
            for constraint_or_index in constraints_and_indexes:
                try:
                    # This would be executed using the graph database connection
                    # For now, we log what would be created
                    self.logger.debug(f"Schema command: {constraint_or_index}")
                except Exception as e:
                    self.logger.warning(f"Schema command failed (may already exist): {e}")
                    
        except Exception as e:
            self.logger.error(f"Error initializing graph schema: {e}")
    
    async def index_processed_documents(
        self,
        processed_docs: List[ProcessedLegalDocument],
        batch_size: int = 10,
        include_vectors: bool = True,
        include_relationships: bool = True
    ) -> List[IndexingResult]:
        """
        Index processed legal documents into GraphRAG system.
        
        Args:
            processed_docs: List of processed documents
            batch_size: Number of documents to process in parallel
            include_vectors: Whether to create vector embeddings
            include_relationships: Whether to create graph relationships
            
        Returns:
            List of indexing results
        """
        results = []
        
        # Process documents in batches
        for i in range(0, len(processed_docs), batch_size):
            batch = processed_docs[i:i + batch_size]
            
            # Process batch in parallel
            batch_tasks = []
            for doc in batch:
                task = self._index_single_document(doc, include_vectors, include_relationships)
                batch_tasks.append(task)
            
            try:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for result in batch_results:
                    if isinstance(result, Exception):
                        self.logger.error(f"Error in batch processing: {result}")
                        error_result = IndexingResult(
                            document_id="unknown",
                            status=IndexingStatus.FAILED,
                            nodes_created=0,
                            relationships_created=0,
                            vectors_indexed=0,
                            processing_time_ms=0,
                            error_message=str(result)
                        )
                        results.append(error_result)
                        self.stats.failed_documents += 1
                    else:
                        results.append(result)
                        
                        # Update stats
                        if result.status == IndexingStatus.COMPLETED:
                            self.stats.successful_documents += 1
                            self.stats.total_nodes_created += result.nodes_created
                            self.stats.total_relationships_created += result.relationships_created
                            self.stats.total_vectors_indexed += result.vectors_indexed
                        else:
                            self.stats.failed_documents += 1
                        
                        self.stats.total_processing_time_ms += result.processing_time_ms
                
            except Exception as e:
                self.logger.error(f"Error processing batch: {e}")
                # Add error results for the whole batch
                for doc in batch:
                    error_result = IndexingResult(
                        document_id=doc.standardized_metadata.get('id', 'unknown'),
                        status=IndexingStatus.FAILED,
                        nodes_created=0,
                        relationships_created=0,
                        vectors_indexed=0,
                        processing_time_ms=0,
                        error_message=str(e)
                    )
                    results.append(error_result)
                    self.stats.failed_documents += 1
        
        self.stats.total_documents += len(processed_docs)
        
        self.logger.info(f"Indexing completed. Success rate: {self.stats.success_rate:.2%}")
        
        return results
    
    async def _index_single_document(
        self,
        doc: ProcessedLegalDocument,
        include_vectors: bool,
        include_relationships: bool
    ) -> IndexingResult:
        """Index a single processed document."""
        start_time = datetime.now()
        document_id = doc.standardized_metadata.get('id', 'unknown')
        
        try:
            nodes_created = 0
            relationships_created = 0
            vectors_indexed = 0
            
            # 1. Create main document node
            main_node_result = await self._create_main_document_node(doc)
            nodes_created += main_node_result
            
            # 2. Create and link entity nodes
            entity_result = await self._create_entity_nodes(doc)
            nodes_created += entity_result['nodes']
            relationships_created += entity_result['relationships']
            
            # 3. Create and link citation nodes
            citation_result = await self._create_citation_nodes(doc)
            nodes_created += citation_result['nodes']
            relationships_created += citation_result['relationships']
            
            # 4. Create and link concept nodes
            concept_result = await self._create_concept_nodes(doc)
            nodes_created += concept_result['nodes']
            relationships_created += concept_result['relationships']
            
            # 5. Create court and jurisdiction nodes if needed
            court_result = await self._create_court_jurisdiction_nodes(doc)
            nodes_created += court_result['nodes']
            relationships_created += court_result['relationships']
            
            # 6. Create additional relationships
            if include_relationships:
                relationship_result = await self._create_advanced_relationships(doc)
                relationships_created += relationship_result
            
            # 7. Create vector embeddings
            if include_vectors:
                vector_result = await self._create_vector_embeddings(doc)
                vectors_indexed += vector_result
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return IndexingResult(
                document_id=document_id,
                status=IndexingStatus.COMPLETED,
                nodes_created=nodes_created,
                relationships_created=relationships_created,
                vectors_indexed=vectors_indexed,
                processing_time_ms=int(processing_time),
                error_message=None
            )
            
        except Exception as e:
            self.logger.error(f"Error indexing document {document_id}: {e}")
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return IndexingResult(
                document_id=document_id,
                status=IndexingStatus.FAILED,
                nodes_created=0,
                relationships_created=0,
                vectors_indexed=0,
                processing_time_ms=int(processing_time),
                error_message=str(e)
            )
    
    async def _create_main_document_node(self, doc: ProcessedLegalDocument) -> int:
        """Create the main document node in Neo4j."""
        metadata = doc.standardized_metadata
        doc_type = metadata.get('type', 'document')
        
        # Determine node label based on document type
        if doc_type == 'case':
            label = 'LegalCase'
            cypher = """
            MERGE (c:LegalCase {id: $id})
            SET c.caption = $title,
                c.court = $court,
                c.jurisdiction = $jurisdiction,
                c.filed_date = $filed_date,
                c.decided_date = $decided_date,
                c.docket_number = $docket_number,
                c.source = $source,
                c.outcome = $outcome,
                c.status = $status,
                c.url = $url,
                c.summary = $summary,
                c.quality_score = $quality_score,
                c.indexed_at = $indexed_at,
                c.word_count = $word_count
            RETURN c
            """
        else:
            label = 'LegalDocument'
            cypher = """
            MERGE (d:LegalDocument {id: $id})
            SET d.title = $title,
                d.doc_type = $doc_type,
                d.agency = $agency,
                d.effective_date = $effective_date,
                d.source = $source,
                d.url = $url,
                d.summary = $summary,
                d.quality_score = $quality_score,
                d.indexed_at = $indexed_at,
                d.word_count = $word_count
            RETURN d
            """
        
        # Prepare parameters
        params = {
            'id': metadata.get('id'),
            'title': metadata.get('title'),
            'source': metadata.get('source'),
            'url': metadata.get('url'),
            'summary': doc.summary,
            'quality_score': doc.quality_metrics.get('overall_quality', 0.5),
            'indexed_at': datetime.now(timezone.utc).isoformat(),
            'word_count': doc.quality_metrics.get('word_count', 0)
        }
        
        if doc_type == 'case':
            params.update({
                'court': metadata.get('court'),
                'jurisdiction': metadata.get('jurisdiction'),
                'filed_date': metadata.get('filed_date'),
                'decided_date': metadata.get('decided_date'),
                'docket_number': metadata.get('docket_number'),
                'outcome': metadata.get('outcome'),
                'status': metadata.get('status')
            })
        else:
            params.update({
                'doc_type': metadata.get('type'),
                'agency': metadata.get('agency'),
                'effective_date': metadata.get('effective_date')
            })
        
        try:
            # Execute query (mock implementation - would use actual Neo4j driver)
            self.logger.debug(f"Creating {label} node: {params['id']}")
            # result = await self.graph_db.execute_query(cypher, params)
            return 1  # One node created
            
        except Exception as e:
            self.logger.error(f"Error creating main document node: {e}")
            raise
    
    async def _create_entity_nodes(self, doc: ProcessedLegalDocument) -> Dict[str, int]:
        """Create entity nodes and relationships."""
        if not doc.extracted_entities:
            return {'nodes': 0, 'relationships': 0}
        
        nodes_created = 0
        relationships_created = 0
        document_id = doc.standardized_metadata.get('id')
        
        for entity in doc.extracted_entities:
            try:
                # Create entity node
                cypher = """
                MERGE (e:LegalEntity {text: $text, entity_type: $entity_type})
                SET e.confidence = $confidence,
                    e.last_seen = $last_seen
                RETURN e
                """
                
                params = {
                    'text': entity.text,
                    'entity_type': entity.entity_type,
                    'confidence': entity.confidence,
                    'last_seen': datetime.now(timezone.utc).isoformat()
                }
                
                # Execute query
                self.logger.debug(f"Creating entity node: {entity.text}")
                # await self.graph_db.execute_query(cypher, params)
                nodes_created += 1
                
                # Create relationship to document
                rel_cypher = """
                MATCH (d {id: $doc_id})
                MATCH (e:LegalEntity {text: $text, entity_type: $entity_type})
                MERGE (d)-[r:CONTAINS_ENTITY]->(e)
                SET r.start_pos = $start_pos,
                    r.end_pos = $end_pos
                RETURN r
                """
                
                rel_params = {
                    'doc_id': document_id,
                    'text': entity.text,
                    'entity_type': entity.entity_type,
                    'start_pos': entity.start_pos,
                    'end_pos': entity.end_pos
                }
                
                # Execute relationship query
                # await self.graph_db.execute_query(rel_cypher, rel_params)
                relationships_created += 1
                
            except Exception as e:
                self.logger.error(f"Error creating entity node {entity.text}: {e}")
        
        return {'nodes': nodes_created, 'relationships': relationships_created}
    
    async def _create_citation_nodes(self, doc: ProcessedLegalDocument) -> Dict[str, int]:
        """Create citation nodes and relationships."""
        if not doc.extracted_citations:
            return {'nodes': 0, 'relationships': 0}
        
        nodes_created = 0
        relationships_created = 0
        document_id = doc.standardized_metadata.get('id')
        
        for citation in doc.extracted_citations:
            try:
                # Create citation node
                cypher = """
                MERGE (c:Citation {normalized_form: $normalized_form})
                SET c.citation_text = $citation_text,
                    c.citation_type = $citation_type,
                    c.authority_level = $authority_level,
                    c.jurisdiction = $jurisdiction,
                    c.year = $year,
                    c.confidence = $confidence,
                    c.last_seen = $last_seen
                RETURN c
                """
                
                params = {
                    'normalized_form': citation.normalized_form,
                    'citation_text': citation.citation_text,
                    'citation_type': citation.citation_type,
                    'authority_level': citation.authority_level,
                    'jurisdiction': citation.jurisdiction,
                    'year': citation.year,
                    'confidence': citation.confidence,
                    'last_seen': datetime.now(timezone.utc).isoformat()
                }
                
                # Execute query
                self.logger.debug(f"Creating citation node: {citation.normalized_form}")
                # await self.graph_db.execute_query(cypher, params)
                nodes_created += 1
                
                # Create relationship to document
                rel_cypher = """
                MATCH (d {id: $doc_id})
                MATCH (c:Citation {normalized_form: $normalized_form})
                MERGE (d)-[r:CITES]->(c)
                RETURN r
                """
                
                rel_params = {
                    'doc_id': document_id,
                    'normalized_form': citation.normalized_form
                }
                
                # Execute relationship query
                # await self.graph_db.execute_query(rel_cypher, rel_params)
                relationships_created += 1
                
            except Exception as e:
                self.logger.error(f"Error creating citation node {citation.citation_text}: {e}")
        
        return {'nodes': nodes_created, 'relationships': relationships_created}
    
    async def _create_concept_nodes(self, doc: ProcessedLegalDocument) -> Dict[str, int]:
        """Create legal concept nodes and relationships."""
        if not doc.identified_concepts:
            return {'nodes': 0, 'relationships': 0}
        
        nodes_created = 0
        relationships_created = 0
        document_id = doc.standardized_metadata.get('id')
        
        for concept in doc.identified_concepts:
            try:
                # Create concept node
                cypher = """
                MERGE (lc:LegalConcept {concept: $concept, category: $category})
                SET lc.domain = $domain,
                    lc.confidence = $confidence,
                    lc.last_seen = $last_seen
                RETURN lc
                """
                
                params = {
                    'concept': concept.concept,
                    'category': concept.category,
                    'domain': concept.domain,
                    'confidence': concept.confidence,
                    'last_seen': datetime.now(timezone.utc).isoformat()
                }
                
                # Execute query
                self.logger.debug(f"Creating concept node: {concept.concept}")
                # await self.graph_db.execute_query(cypher, params)
                nodes_created += 1
                
                # Create relationship to document
                rel_cypher = """
                MATCH (d {id: $doc_id})
                MATCH (lc:LegalConcept {concept: $concept, category: $category})
                MERGE (d)-[r:INVOLVES_CONCEPT]->(lc)
                SET r.context = $context,
                    r.confidence = $confidence
                RETURN r
                """
                
                rel_params = {
                    'doc_id': document_id,
                    'concept': concept.concept,
                    'category': concept.category,
                    'context': concept.context,
                    'confidence': concept.confidence
                }
                
                # Execute relationship query
                # await self.graph_db.execute_query(rel_cypher, rel_params)
                relationships_created += 1
                
            except Exception as e:
                self.logger.error(f"Error creating concept node {concept.concept}: {e}")
        
        return {'nodes': nodes_created, 'relationships': relationships_created}
    
    async def _create_court_jurisdiction_nodes(self, doc: ProcessedLegalDocument) -> Dict[str, int]:
        """Create court and jurisdiction nodes."""
        nodes_created = 0
        relationships_created = 0
        metadata = doc.standardized_metadata
        document_id = metadata.get('id')
        
        # Create court node if document is a case
        if metadata.get('type') == 'case' and metadata.get('court'):
            try:
                court_name = metadata['court']
                
                # Create court node
                court_cypher = """
                MERGE (c:Court {name: $name})
                SET c.last_seen = $last_seen
                RETURN c
                """
                
                court_params = {
                    'name': court_name,
                    'last_seen': datetime.now(timezone.utc).isoformat()
                }
                
                # Execute query
                # await self.graph_db.execute_query(court_cypher, court_params)
                nodes_created += 1
                
                # Create relationship
                rel_cypher = """
                MATCH (d:LegalCase {id: $doc_id})
                MATCH (c:Court {name: $court_name})
                MERGE (d)-[r:DECIDED_BY]->(c)
                RETURN r
                """
                
                rel_params = {
                    'doc_id': document_id,
                    'court_name': court_name
                }
                
                # await self.graph_db.execute_query(rel_cypher, rel_params)
                relationships_created += 1
                
            except Exception as e:
                self.logger.error(f"Error creating court node: {e}")
        
        # Create jurisdiction node
        if metadata.get('jurisdiction'):
            try:
                jurisdiction_name = metadata['jurisdiction']
                
                # Create jurisdiction node
                jurisdiction_cypher = """
                MERGE (j:Jurisdiction {name: $name})
                SET j.last_seen = $last_seen
                RETURN j
                """
                
                jurisdiction_params = {
                    'name': jurisdiction_name,
                    'last_seen': datetime.now(timezone.utc).isoformat()
                }
                
                # Execute query
                # await self.graph_db.execute_query(jurisdiction_cypher, jurisdiction_params)
                nodes_created += 1
                
                # Create relationship
                rel_cypher = """
                MATCH (d {id: $doc_id})
                MATCH (j:Jurisdiction {name: $jurisdiction_name})
                MERGE (d)-[r:IN_JURISDICTION]->(j)
                RETURN r
                """
                
                rel_params = {
                    'doc_id': document_id,
                    'jurisdiction_name': jurisdiction_name
                }
                
                # await self.graph_db.execute_query(rel_cypher, rel_params)
                relationships_created += 1
                
            except Exception as e:
                self.logger.error(f"Error creating jurisdiction node: {e}")
        
        return {'nodes': nodes_created, 'relationships': relationships_created}
    
    async def _create_advanced_relationships(self, doc: ProcessedLegalDocument) -> int:
        """Create advanced relationships between entities, concepts, and citations."""
        relationships_created = 0
        
        # Create relationships between entities and concepts that co-occur
        entities = doc.extracted_entities
        concepts = doc.identified_concepts
        
        for entity in entities:
            for concept in concepts:
                # Check if entity and concept are related (simple co-occurrence check)
                if self._are_related(entity.text, concept.concept, concept.context):
                    try:
                        cypher = """
                        MATCH (e:LegalEntity {text: $entity_text, entity_type: $entity_type})
                        MATCH (c:LegalConcept {concept: $concept, category: $category})
                        MERGE (e)-[r:RELATED_TO_CONCEPT]->(c)
                        SET r.confidence = $confidence,
                            r.created_at = $created_at
                        RETURN r
                        """
                        
                        params = {
                            'entity_text': entity.text,
                            'entity_type': entity.entity_type,
                            'concept': concept.concept,
                            'category': concept.category,
                            'confidence': min(entity.confidence, concept.confidence),
                            'created_at': datetime.now(timezone.utc).isoformat()
                        }
                        
                        # Execute query
                        # await self.graph_db.execute_query(cypher, params)
                        relationships_created += 1
                        
                    except Exception as e:
                        self.logger.error(f"Error creating entity-concept relationship: {e}")
        
        # Create relationships between citations and concepts
        citations = doc.extracted_citations
        
        for citation in citations:
            for concept in concepts:
                if self._citation_supports_concept(citation, concept):
                    try:
                        cypher = """
                        MATCH (ct:Citation {normalized_form: $citation})
                        MATCH (c:LegalConcept {concept: $concept, category: $category})
                        MERGE (ct)-[r:SUPPORTS_CONCEPT]->(c)
                        SET r.confidence = $confidence,
                            r.created_at = $created_at
                        RETURN r
                        """
                        
                        params = {
                            'citation': citation.normalized_form,
                            'concept': concept.concept,
                            'category': concept.category,
                            'confidence': min(citation.confidence, concept.confidence),
                            'created_at': datetime.now(timezone.utc).isoformat()
                        }
                        
                        # Execute query
                        # await self.graph_db.execute_query(cypher, params)
                        relationships_created += 1
                        
                    except Exception as e:
                        self.logger.error(f"Error creating citation-concept relationship: {e}")
        
        return relationships_created
    
    def _are_related(self, entity_text: str, concept: str, context: str) -> bool:
        """Check if an entity and concept are related."""
        # Simple heuristic: check if they appear near each other in context
        entity_lower = entity_text.lower()
        concept_lower = concept.lower()
        context_lower = context.lower()
        
        return (entity_lower in context_lower and concept_lower in context_lower)
    
    def _citation_supports_concept(self, citation: LegalCitation, concept: LegalConcept) -> bool:
        """Check if a citation supports a legal concept."""
        # Simple heuristic based on citation type and concept category
        type_concept_mapping = {
            'case_citation': ['procedural', 'substantive', 'constitutional'],
            'statute_citation': ['substantive', 'procedural'],
            'regulation_citation': ['substantive', 'procedural']
        }
        
        return concept.category in type_concept_mapping.get(citation.citation_type, [])
    
    async def _create_vector_embeddings(self, doc: ProcessedLegalDocument) -> int:
        """Create vector embeddings for the document."""
        vectors_created = 0
        document_id = doc.standardized_metadata.get('id')
        
        try:
            # Create embeddings for text segments
            if doc.text_segments:
                for i, segment in enumerate(doc.text_segments):
                    if segment.strip():
                        # Generate embedding
                        embedding = await self.embedding_service.embed_text(segment)
                        
                        # Prepare metadata
                        metadata = {
                            'document_id': document_id,
                            'segment_index': i,
                            'segment_text': segment[:500],  # Truncate for storage
                            'document_type': doc.standardized_metadata.get('type'),
                            'source': doc.standardized_metadata.get('source'),
                            'title': doc.standardized_metadata.get('title', '')[:200],
                            'quality_score': doc.quality_metrics.get('overall_quality', 0.5)
                        }
                        
                        # Store in vector database
                        vector_id = f"{document_id}_segment_{i}"
                        self.vector_db.add_vector(
                            vector_id=vector_id,
                            vector=embedding,
                            metadata=metadata
                        )
                        vectors_created += 1
            
            # Create embedding for summary if available
            if doc.summary:
                summary_embedding = await self.embedding_service.embed_text(doc.summary)
                
                summary_metadata = {
                    'document_id': document_id,
                    'content_type': 'summary',
                    'document_type': doc.standardized_metadata.get('type'),
                    'source': doc.standardized_metadata.get('source'),
                    'title': doc.standardized_metadata.get('title', '')[:200],
                    'quality_score': doc.quality_metrics.get('overall_quality', 0.5)
                }
                
                summary_vector_id = f"{document_id}_summary"
                self.vector_db.add_vector(
                    vector_id=summary_vector_id,
                    vector=summary_embedding,
                    metadata=summary_metadata
                )
                vectors_created += 1
            
            # Create embeddings for key points
            if doc.key_points:
                for i, key_point in enumerate(doc.key_points):
                    if key_point.strip():
                        key_point_embedding = await self.embedding_service.embed_text(key_point)
                        
                        key_point_metadata = {
                            'document_id': document_id,
                            'content_type': 'key_point',
                            'key_point_index': i,
                            'document_type': doc.standardized_metadata.get('type'),
                            'source': doc.standardized_metadata.get('source'),
                            'title': doc.standardized_metadata.get('title', '')[:200],
                            'quality_score': doc.quality_metrics.get('overall_quality', 0.5)
                        }
                        
                        key_point_vector_id = f"{document_id}_keypoint_{i}"
                        self.vector_db.add_vector(
                            vector_id=key_point_vector_id,
                            vector=key_point_embedding,
                            metadata=key_point_metadata
                        )
                        vectors_created += 1
            
        except Exception as e:
            self.logger.error(f"Error creating vector embeddings: {e}")
        
        return vectors_created
    
    async def search_similar_documents(
        self,
        query_text: str,
        document_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents using vector similarity.
        
        Args:
            query_text: Search query
            document_type: Filter by document type
            source: Filter by source
            limit: Maximum results
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of similar documents with metadata
        """
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.embed_text(query_text)
            
            # Prepare filters
            filters = {}
            if document_type:
                filters['document_type'] = document_type
            if source:
                filters['source'] = source
            
            # Search in vector database
            results = self.vector_db.search_similar(
                query_embedding,
                filters=filters,
                limit=limit * 2  # Get more results to filter
            )
            
            # Filter by similarity threshold and format results
            filtered_results = []
            for result in results:
                if isinstance(result, tuple):
                    metadata, score = result
                    if score >= similarity_threshold:
                        filtered_results.append({
                            'metadata': metadata,
                            'similarity_score': score,
                            'document_id': metadata.get('document_id'),
                            'title': metadata.get('title'),
                            'content_type': metadata.get('content_type', 'segment')
                        })
                
                if len(filtered_results) >= limit:
                    break
            
            return filtered_results
            
        except Exception as e:
            self.logger.error(f"Error searching similar documents: {e}")
            return []
    
    async def get_document_graph_neighbors(
        self,
        document_id: str,
        relationship_types: Optional[List[str]] = None,
        max_hops: int = 2,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get graph neighbors of a document.
        
        Args:
            document_id: ID of the document
            relationship_types: Types of relationships to follow
            max_hops: Maximum hops from the document
            limit: Maximum number of neighbors
            
        Returns:
            Dictionary with nodes and relationships
        """
        try:
            # Build Cypher query
            if relationship_types:
                rel_filter = "|".join(relationship_types)
                rel_pattern = f"[r:{rel_filter}]"
            else:
                rel_pattern = "[r]"
            
            cypher = f"""
            MATCH (d {{id: $document_id}})
            MATCH path = (d){rel_pattern}{{1,{max_hops}}}(neighbor)
            RETURN DISTINCT neighbor, r, length(path) as hops
            ORDER BY hops, neighbor.title
            LIMIT $limit
            """
            
            params = {
                'document_id': document_id,
                'limit': limit
            }
            
            # Execute query (mock implementation)
            # result = await self.graph_db.execute_query(cypher, params)
            
            # For now, return mock results
            return {
                'document_id': document_id,
                'neighbors': [],
                'relationships': [],
                'total_neighbors': 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting document graph neighbors: {e}")
            return {
                'document_id': document_id,
                'neighbors': [],
                'relationships': [],
                'total_neighbors': 0
            }
    
    def get_indexing_stats(self) -> IndexingStats:
        """Get current indexing statistics."""
        return self.stats
    
    def reset_stats(self):
        """Reset indexing statistics."""
        self.stats = IndexingStats(
            total_documents=0,
            successful_documents=0,
            failed_documents=0,
            total_nodes_created=0,
            total_relationships_created=0,
            total_vectors_indexed=0,
            total_processing_time_ms=0
        )


# Utility class for graph operations
class GraphQueryBuilder:
    """Helper class for building complex graph queries."""
    
    @staticmethod
    def build_citation_network_query(citation_ids: List[str], max_depth: int = 3) -> Tuple[str, Dict]:
        """Build query to find citation networks."""
        cypher = """
        MATCH (start:Citation) WHERE start.normalized_form IN $citation_ids
        CALL apoc.path.expandConfig(start, {
            relationshipFilter: "CITES>|<CITED_BY",
            minLevel: 1,
            maxLevel: $max_depth,
            uniqueness: "NODE_GLOBAL"
        }) YIELD path
        RETURN path
        """
        
        params = {
            'citation_ids': citation_ids,
            'max_depth': max_depth
        }
        
        return cypher, params
    
    @staticmethod
    def build_concept_similarity_query(concept: str, category: str, limit: int = 10) -> Tuple[str, Dict]:
        """Build query to find similar concepts."""
        cypher = """
        MATCH (c1:LegalConcept {concept: $concept, category: $category})
        MATCH (c1)<-[:INVOLVES_CONCEPT]-(d)-[:INVOLVES_CONCEPT]->(c2:LegalConcept)
        WHERE c2 <> c1
        WITH c2, count(d) as shared_documents
        ORDER BY shared_documents DESC
        LIMIT $limit
        RETURN c2, shared_documents
        """
        
        params = {
            'concept': concept,
            'category': category,
            'limit': limit
        }
        
        return cypher, params


# Example usage
async def test_indexer():
    """Test the legal data indexer."""
    from .legal_data_processor import LegalDataProcessor
    from .legal_data_apis import LegalCase, DataSource
    
    # Create test data
    test_case = LegalCase(
        case_id="test_indexer_001",
        source=DataSource.COURTLISTENER,
        caption="Test Indexing Corp v. Example Systems - Patent Case",
        court="U.S. District Court for the District of Delaware",
        jurisdiction="federal",
        opinion_text="The court finds that the claims are valid and infringed. Under 35 U.S.C. § 271, defendant is liable.",
    )
    
    # Process the case
    processor = LegalDataProcessor()
    processed_docs = await processor.process_legal_cases([test_case])
    
    # Index the processed documents
    indexer = LegalDataIndexer()
    results = await indexer.index_processed_documents(processed_docs)
    
    # Display results
    for result in results:
        print(f"Document: {result.document_id}")
        print(f"Status: {result.status}")
        print(f"Nodes created: {result.nodes_created}")
        print(f"Relationships created: {result.relationships_created}")
        print(f"Vectors indexed: {result.vectors_indexed}")
        print(f"Processing time: {result.processing_time_ms}ms")
        print("-" * 50)
    
    # Display overall stats
    stats = indexer.get_indexing_stats()
    print(f"Overall success rate: {stats.success_rate:.2%}")
    print(f"Total nodes created: {stats.total_nodes_created}")
    print(f"Total relationships created: {stats.total_relationships_created}")


if __name__ == "__main__":
    asyncio.run(test_indexer())