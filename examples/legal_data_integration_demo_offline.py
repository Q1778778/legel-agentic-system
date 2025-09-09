#!/usr/bin/env python3
"""
Legal Data Integration System Demo - Offline Mode

This script demonstrates the complete workflow of the legal data integration system
without requiring external database connections. It uses mock data and in-memory
storage for demonstration purposes.

Features demonstrated:
1. API data retrieval from multiple sources (using mock data when API keys unavailable)
2. Data processing and standardization
3. Mock GraphRAG indexing (in-memory)
4. Real-time search and retrieval
5. Performance monitoring
6. Error handling and resilience

Usage:
    python examples/legal_data_integration_demo_offline.py
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class MockGraphDB:
    """Mock Neo4j graph database for demo purposes."""
    
    def __init__(self):
        """Initialize mock database."""
        self.nodes = []
        self.relationships = []
        self.connected = False
        
    def close(self):
        """Mock close method."""
        pass
        
    async def create_case_node(self, case_data: Dict[str, Any]) -> str:
        """Mock create case node."""
        node_id = f"case_{len(self.nodes)}"
        self.nodes.append({
            "id": node_id,
            "type": "Case",
            "data": case_data
        })
        return node_id
    
    async def create_relationships(self, relationships: List[Dict[str, Any]]) -> List[str]:
        """Mock create relationships."""
        rel_ids = []
        for rel in relationships:
            rel_id = f"rel_{len(self.relationships)}"
            self.relationships.append({
                "id": rel_id,
                **rel
            })
            rel_ids.append(rel_id)
        return rel_ids


class MockVectorDB:
    """Mock vector database for demo purposes."""
    
    def __init__(self):
        """Initialize mock vector database."""
        self.vectors = []
        
    def close(self):
        """Mock close method."""
        pass
        
    async def upsert_vectors(self, vectors: List[Dict[str, Any]]) -> List[str]:
        """Mock upsert vectors."""
        vector_ids = []
        for vector in vectors:
            vector_id = f"vector_{len(self.vectors)}"
            self.vectors.append({
                "id": vector_id,
                **vector
            })
            vector_ids.append(vector_id)
        return vector_ids
    
    async def search_similar(self, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """Mock similarity search."""
        # Return mock similar documents
        return [
            {
                "id": f"doc_{i}",
                "title": f"Mock Legal Document {i}",
                "similarity_score": 0.9 - (i * 0.1),
                "content_type": "case_law" if i % 2 == 0 else "statute"
            }
            for i in range(min(limit, 3))
        ]


class MockEmbeddingService:
    """Mock embedding service for demo purposes."""
    
    async def get_embedding(self, text: str) -> List[float]:
        """Mock get embedding."""
        # Return a mock 384-dimensional vector
        return [0.1] * 384
    
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Mock get embeddings for multiple texts."""
        return [[0.1] * 384 for _ in texts]


# Import required classes with error handling
try:
    from src.services.legal_data_apis import LegalDataAPIClient, DataSource
except ImportError:
    logger.warning("Could not import legal_data_apis, using mock implementation")
    
    class MockLegalDataAPIClient:
        """Mock API client for demo purposes."""
        
        async def search_cases(self, query: str, sources: List[Any], limit: int = 10):
            """Mock search cases."""
            from src.models.schemas import Case, DataSource as DS
            
            # Generate mock cases
            mock_cases = []
            for i in range(min(limit, 3)):
                case = Case(
                    case_id=f"mock_case_{i}",
                    caption=f"Mock Legal Case {i}: {query.title()} Matter",
                    court=f"Mock Superior Court {i}",
                    filing_date=datetime.now(),
                    source=DS.COURTLISTENER,
                    content=f"This is a mock legal case about {query}. It demonstrates the system's ability to process legal documents even without API access.",
                    citation=f"Mock {i+2024} WL {1000+i}",
                    jurisdiction="Mock State"
                )
                mock_cases.append(case)
            
            return mock_cases
    
    LegalDataAPIClient = MockLegalDataAPIClient
    
    class DataSource:
        COURTLISTENER = "courtlistener"
        CAP = "cap"

try:
    from src.services.legal_data_processor import LegalDataProcessor
except ImportError:
    logger.warning("Could not import legal_data_processor, using mock implementation")
    
    class MockLegalDataProcessor:
        """Mock data processor for demo purposes."""
        
        def __init__(self):
            self.stats = {
                "documents_processed": 0,
                "entities_extracted": 0,
                "citations_found": 0,
                "legal_concepts_identified": 0,
                "processing_time_ms": 0
            }
        
        async def process_legal_cases(self, cases, **kwargs):
            """Mock process legal cases."""
            from dataclasses import dataclass
            from typing import List, Dict, Any
            
            @dataclass
            class MockEntity:
                text: str
                label: str
                start: int
                end: int
            
            @dataclass  
            class MockCitation:
                citation_text: str
                case_name: str = ""
                citation_type: str = "case"
            
            @dataclass
            class MockConcept:
                concept: str
                confidence: float
            
            @dataclass
            class MockProcessedDoc:
                document_id: str
                standardized_metadata: Dict[str, Any]
                extracted_entities: List[MockEntity] 
                extracted_citations: List[MockCitation]
                identified_concepts: List[MockConcept]
                quality_metrics: Dict[str, float]
            
            processed_docs = []
            for i, case in enumerate(cases):
                # Mock processing results
                processed_doc = MockProcessedDoc(
                    document_id=case.case_id,
                    standardized_metadata={
                        "title": case.caption,
                        "court": case.court,
                        "filing_date": case.filing_date.isoformat() if case.filing_date else None,
                        "jurisdiction": getattr(case, 'jurisdiction', 'Unknown')
                    },
                    extracted_entities=[
                        MockEntity(text="Patent", label="LEGAL_CONCEPT", start=0, end=6),
                        MockEntity(text="Infringement", label="LEGAL_CONCEPT", start=7, end=19),
                        MockEntity(text="Software", label="TECHNOLOGY", start=20, end=28)
                    ],
                    extracted_citations=[
                        MockCitation(citation_text=f"Example v. Case {i}", case_name=f"Example v. Case {i}"),
                        MockCitation(citation_text="35 U.S.C. § 101", citation_type="statute")
                    ],
                    identified_concepts=[
                        MockConcept(concept="Patent Law", confidence=0.95),
                        MockConcept(concept="Intellectual Property", confidence=0.88),
                        MockConcept(concept="Software Patents", confidence=0.82)
                    ],
                    quality_metrics={"overall_quality": 0.85 + (i * 0.05)}
                )
                processed_docs.append(processed_doc)
            
            # Update stats
            self.stats["documents_processed"] = len(processed_docs)
            self.stats["entities_extracted"] = len(processed_docs) * 3
            self.stats["citations_found"] = len(processed_docs) * 2
            self.stats["legal_concepts_identified"] = len(processed_docs) * 3
            self.stats["processing_time_ms"] = 1500
            
            return processed_docs
        
        def get_processing_stats(self):
            """Get mock processing statistics."""
            from dataclasses import dataclass
            
            @dataclass
            class ProcessingStats:
                documents_processed: int
                entities_extracted: int
                citations_found: int
                legal_concepts_identified: int
                processing_time_ms: int
            
            return ProcessingStats(**self.stats)
    
    LegalDataProcessor = MockLegalDataProcessor

try:
    from src.services.legal_data_indexer import LegalDataIndexer
except ImportError:
    logger.warning("Could not import legal_data_indexer, using mock implementation")
    
    class MockLegalDataIndexer:
        """Mock data indexer for demo purposes."""
        
        def __init__(self, graph_db, vector_db, embedding_service):
            self.graph_db = graph_db
            self.vector_db = vector_db
            self.embedding_service = embedding_service
            self.stats = {
                "total_documents": 0,
                "success_rate": 1.0,
                "total_nodes_created": 0,
                "total_relationships_created": 0,
                "total_vectors_indexed": 0,
                "avg_processing_time_ms": 800
            }
        
        async def index_processed_documents(self, processed_docs, **kwargs):
            """Mock index processed documents."""
            from dataclasses import dataclass
            from enum import Enum
            
            class IndexingStatus(Enum):
                COMPLETED = "completed"
                FAILED = "failed"
                PENDING = "pending"
            
            @dataclass
            class IndexingResult:
                document_id: str
                status: IndexingStatus
                nodes_created: int
                relationships_created: int
                vectors_indexed: int
                processing_time_ms: int
            
            results = []
            for doc in processed_docs:
                # Mock successful indexing
                result = IndexingResult(
                    document_id=doc.document_id,
                    status=IndexingStatus.COMPLETED,
                    nodes_created=5,
                    relationships_created=8,
                    vectors_indexed=3,
                    processing_time_ms=750
                )
                results.append(result)
            
            # Update stats
            self.stats["total_documents"] = len(processed_docs)
            self.stats["total_nodes_created"] = len(processed_docs) * 5
            self.stats["total_relationships_created"] = len(processed_docs) * 8
            self.stats["total_vectors_indexed"] = len(processed_docs) * 3
            
            return results
        
        async def search_similar_documents(self, query_text: str, limit: int = 10, similarity_threshold: float = 0.7):
            """Mock search similar documents."""
            return await self.vector_db.search_similar([0.1] * 384, limit)
        
        def get_indexing_stats(self):
            """Get mock indexing statistics."""
            from dataclasses import dataclass
            
            @dataclass
            class IndexingStats:
                total_documents: int
                success_rate: float
                total_nodes_created: int
                total_relationships_created: int
                total_vectors_indexed: int
                avg_processing_time_ms: float
            
            return IndexingStats(**self.stats)
    
    LegalDataIndexer = MockLegalDataIndexer

# Mock performance monitoring
class MockPerformanceMonitor:
    """Mock performance monitor for demo purposes."""
    
    def __init__(self):
        self.metrics = {}
        self.api_monitor = self
        
    async def start(self):
        """Mock start monitoring."""
        pass
        
    async def stop(self):
        """Mock stop monitoring."""
        pass
        
    def record_api_request(self, **kwargs):
        """Mock record API request."""
        pass
        
    async def get_dashboard_data(self):
        """Mock get dashboard data."""
        return {
            "api_health": {
                "request_count": 15,
                "error_count": 0
            },
            "system_health": {
                "cpu": {"mean": 25.5},
                "memory": {"mean": 45.2}
            },
            "active_alerts": []
        }
        
    @property
    def reporter(self):
        """Mock reporter."""
        return self
        
    async def generate_report(self, hours: int = 1):
        """Mock generate report."""
        return {
            "performance_analysis": {
                "system_performance": {"status": "healthy"},
                "api_performance": {"status": "excellent"},
                "error_analysis": {"status": "no_issues"},
                "recommendations": [
                    "System is performing optimally",
                    "No bottlenecks detected",
                    "API response times are excellent"
                ]
            }
        }

class MockPerformanceTimer:
    """Mock performance timer context manager."""
    
    def __init__(self, metrics, name, tags=None):
        self.metrics = metrics
        self.name = name
        self.tags = tags or {}
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

# Mock error handling
class MockResilientAPIClient:
    """Mock resilient API client for demo purposes."""
    
    def __init__(self, name: str, base_url: str, **kwargs):
        self.name = name
        self.base_url = base_url
        self.request_count = 0
        self.success_count = 0
        
    async def make_request(self, method: str, endpoint: str, data=None):
        """Mock make request."""
        self.request_count += 1
        
        if "500" in endpoint:
            raise Exception("Mock HTTP 500 error for testing")
        
        self.success_count += 1
        return {
            "url": f"{self.base_url}{endpoint}",
            "method": method,
            "status": "success"
        }
        
    def get_health_status(self):
        """Mock get health status."""
        return {
            "health_status": "healthy",
            "request_stats": {
                "total_requests": self.request_count,
                "successful_requests": self.success_count
            },
            "avg_response_time_ms": 250.0
        }

class MockErrorAggregator:
    """Mock error aggregator for demo purposes."""
    
    def get_error_summary(self, hours: int = 1):
        """Mock get error summary."""
        return {
            "total_errors": 1,
            "by_category": {"http_error": 1},
            "by_severity": {"medium": 1}
        }

# Create mock instances
performance_monitor = MockPerformanceMonitor()
performance_timer = MockPerformanceTimer
ResilientAPIClient = MockResilientAPIClient
error_aggregator = MockErrorAggregator()


class LegalDataDemo:
    """Demo class for legal data integration system using mock components."""
    
    def __init__(self):
        """Initialize demo components with mock implementations."""
        self.api_client = LegalDataAPIClient()
        self.processor = LegalDataProcessor()
        
        # Mock database connections
        self.graph_db = MockGraphDB()
        self.vector_db = MockVectorDB()
        self.embedding_service = MockEmbeddingService()
        
        self.indexer = LegalDataIndexer(
            graph_db=self.graph_db,
            vector_db=self.vector_db,
            embedding_service=self.embedding_service
        )
        
        logger.info("Demo components initialized with mock implementations")
    
    async def demonstrate_api_retrieval(self):
        """Demonstrate legal data API retrieval."""
        print("\n" + "="*80)
        print("STEP 1: Legal Data API Retrieval")
        print("="*80)
        
        search_queries = [
            "patent infringement software",
            "contract breach liability", 
            "employment discrimination"
        ]
        
        all_cases = []
        
        for query in search_queries:
            print(f"\n📋 Searching for: '{query}'")
            
            # Time the API call
            async with performance_timer(
                performance_monitor.metrics,
                "demo.api_search_time_ms",
                {"query_type": query.split()[0]}
            ):
                try:
                    # Search across multiple sources
                    cases = await self.api_client.search_cases(
                        query=query,
                        sources=[DataSource.COURTLISTENER, DataSource.CAP],
                        limit=3
                    )
                    
                    print(f"   ✅ Found {len(cases)} cases")
                    for i, case in enumerate(cases, 1):
                        print(f"   {i}. {case.caption[:60]}...")
                        print(f"      Court: {case.court}")
                        print(f"      Source: {case.source}")
                    
                    all_cases.extend(cases)
                    
                    # Record metrics
                    performance_monitor.api_monitor.record_api_request(
                        api_name="legal_search",
                        endpoint="/search/cases",
                        status_code=200,
                        response_time_ms=500
                    )
                    
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    logger.error(f"API search failed for query '{query}'", error=str(e))
        
        print(f"\n📊 Total cases retrieved: {len(all_cases)}")
        return all_cases
    
    async def demonstrate_data_processing(self, cases):
        """Demonstrate data processing and standardization."""
        print("\n" + "="*80)
        print("STEP 2: Data Processing and Standardization")
        print("="*80)
        
        processed_docs = []
        
        print(f"\n🔄 Processing {len(cases)} legal cases...")
        
        # Time the processing
        async with performance_timer(
            performance_monitor.metrics,
            "demo.processing_time_ms",
            {"batch_size": len(cases)}
        ):
            try:
                # Process cases with NLP, citation extraction, and concept identification
                processed_docs = await self.processor.process_legal_cases(
                    cases,
                    include_nlp=True,
                    include_citations=True,
                    include_concepts=True
                )
                
                print(f"   ✅ Successfully processed {len(processed_docs)} documents")
                
                # Show processing results
                for i, doc in enumerate(processed_docs[:2], 1):  # Show first 2 for demo
                    print(f"\n   📄 Document {i}: {doc.standardized_metadata.get('title', 'Unknown')[:50]}...")
                    print(f"      Entities extracted: {len(doc.extracted_entities)}")
                    print(f"      Citations found: {len(doc.extracted_citations)}")
                    print(f"      Legal concepts: {len(doc.identified_concepts)}")
                    print(f"      Quality score: {doc.quality_metrics.get('overall_quality', 0):.2f}")
                    
                    # Show some extracted information
                    if doc.extracted_citations:
                        print(f"      Sample citations: {[c.citation_text for c in doc.extracted_citations[:2]]}")
                    
                    if doc.identified_concepts:
                        concepts = [c.concept for c in doc.identified_concepts[:3]]
                        print(f"      Key concepts: {concepts}")
                
            except Exception as e:
                print(f"   ❌ Processing error: {e}")
                logger.error("Data processing failed", error=str(e))
        
        # Show processing statistics
        stats = self.processor.get_processing_stats()
        print(f"\n📊 Processing Statistics:")
        print(f"   - Documents processed: {stats.documents_processed}")
        print(f"   - Entities extracted: {stats.entities_extracted}")
        print(f"   - Citations found: {stats.citations_found}")
        print(f"   - Legal concepts identified: {stats.legal_concepts_identified}")
        print(f"   - Total processing time: {stats.processing_time_ms}ms")
        
        return processed_docs
    
    async def demonstrate_graphrag_indexing(self, processed_docs):
        """Demonstrate GraphRAG indexing."""
        print("\n" + "="*80)
        print("STEP 3: GraphRAG Indexing (Mock Implementation)")
        print("="*80)
        
        print(f"\n🔗 Indexing {len(processed_docs)} processed documents into mock GraphRAG...")
        
        # Time the indexing
        async with performance_timer(
            performance_monitor.metrics,
            "demo.indexing_time_ms",
            {"document_count": len(processed_docs)}
        ):
            try:
                # Index documents into mock databases
                indexing_results = await self.indexer.index_processed_documents(
                    processed_docs,
                    batch_size=5,
                    include_vectors=True,
                    include_relationships=True
                )
                
                print(f"   ✅ Mock indexing completed")
                
                # Show indexing results
                successful = sum(1 for r in indexing_results if r.status.value == "completed")
                failed = sum(1 for r in indexing_results if r.status.value == "failed")
                
                print(f"\n📊 Indexing Results:")
                print(f"   - Successful: {successful}")
                print(f"   - Failed: {failed}")
                print(f"   - Success rate: {successful / len(indexing_results) * 100:.1f}%")
                
                # Show detailed results for first few documents
                for i, result in enumerate(indexing_results[:2], 1):
                    print(f"\n   📑 Document {i} ({result.document_id}):")
                    print(f"      Status: {result.status.value}")
                    print(f"      Nodes created: {result.nodes_created}")
                    print(f"      Relationships created: {result.relationships_created}")
                    print(f"      Vectors indexed: {result.vectors_indexed}")
                    print(f"      Processing time: {result.processing_time_ms}ms")
                
            except Exception as e:
                print(f"   ❌ Indexing error: {e}")
                logger.error("GraphRAG indexing failed", error=str(e))
        
        # Show indexing statistics
        stats = self.indexer.get_indexing_stats()
        print(f"\n📊 Overall Indexing Statistics:")
        print(f"   - Total documents: {stats.total_documents}")
        print(f"   - Success rate: {stats.success_rate:.1%}")
        print(f"   - Total nodes created: {stats.total_nodes_created}")
        print(f"   - Total relationships created: {stats.total_relationships_created}")
        print(f"   - Total vectors indexed: {stats.total_vectors_indexed}")
        print(f"   - Average processing time: {stats.avg_processing_time_ms:.1f}ms")
        
        return indexing_results
    
    async def demonstrate_search_and_retrieval(self):
        """Demonstrate search and retrieval from mock GraphRAG."""
        print("\n" + "="*80)
        print("STEP 4: Search and Retrieval (Mock Implementation)")
        print("="*80)
        
        search_queries = [
            "software patent disputes",
            "employment contract violations",
            "intellectual property infringement"
        ]
        
        for query in search_queries:
            print(f"\n🔍 Searching mock GraphRAG for: '{query}'")
            
            # Time the search
            async with performance_timer(
                performance_monitor.metrics,
                "demo.search_time_ms",
                {"query_type": query.split()[0]}
            ):
                try:
                    # Search similar documents using mock vector similarity
                    similar_docs = await self.indexer.search_similar_documents(
                        query_text=query,
                        limit=3,
                        similarity_threshold=0.7
                    )
                    
                    if similar_docs:
                        print(f"   ✅ Found {len(similar_docs)} similar documents:")
                        for i, doc in enumerate(similar_docs, 1):
                            print(f"   {i}. {doc['title'][:50]}...")
                            print(f"      Similarity: {doc['similarity_score']:.3f}")
                            print(f"      Type: {doc['content_type']}")
                    else:
                        print(f"   ℹ️ No similar documents found")
                        
                except Exception as e:
                    print(f"   ❌ Search error: {e}")
                    logger.error(f"Search failed for query '{query}'", error=str(e))
    
    async def demonstrate_performance_monitoring(self):
        """Demonstrate performance monitoring and analytics."""
        print("\n" + "="*80)
        print("STEP 5: Performance Monitoring & Analytics (Mock)")
        print("="*80)
        
        print("\n📊 Collecting mock performance metrics...")
        
        # Start performance monitoring
        await performance_monitor.start()
        
        # Wait a bit for mock metrics collection
        await asyncio.sleep(1)
        
        # Get dashboard data
        dashboard_data = await performance_monitor.get_dashboard_data()
        
        print(f"\n📈 Performance Dashboard:")
        print(f"   - Total API requests: {dashboard_data['api_health']['request_count']}")
        print(f"   - API errors: {dashboard_data['api_health']['error_count']}")
        print(f"   - Active alerts: {len(dashboard_data['active_alerts'])}")
        
        # Show system health
        if dashboard_data['system_health']['cpu']:
            cpu_usage = dashboard_data['system_health']['cpu']['mean']
            print(f"   - CPU usage: {cpu_usage:.1f}%")
        
        if dashboard_data['system_health']['memory']:
            memory_usage = dashboard_data['system_health']['memory']['mean']
            print(f"   - Memory usage: {memory_usage:.1f}%")
        
        # Show any active alerts
        if dashboard_data['active_alerts']:
            print(f"\n⚠️ Active Alerts:")
            for alert in dashboard_data['active_alerts'][:3]:
                print(f"   - {alert['severity'].upper()}: {alert['message']}")
        else:
            print(f"\n✅ No active alerts - system healthy")
        
        # Generate performance report
        print(f"\n📋 Generating mock performance report...")
        report = await performance_monitor.reporter.generate_report(hours=1)
        
        # Show report summary
        analysis = report['performance_analysis']
        print(f"   - System status: {analysis['system_performance']['status']}")
        print(f"   - API status: {analysis['api_performance']['status']}")
        print(f"   - Error analysis: {analysis['error_analysis']['status']}")
        
        if analysis['recommendations']:
            print(f"\n💡 Recommendations:")
            for rec in analysis['recommendations'][:3]:
                print(f"   - {rec}")
        
        # Stop monitoring
        await performance_monitor.stop()
    
    async def demonstrate_error_handling(self):
        """Demonstrate error handling and resilience."""
        print("\n" + "="*80)
        print("STEP 6: Error Handling & Resilience (Mock)")
        print("="*80)
        
        print("\n🛡️ Testing mock error handling capabilities...")
        
        # Create a mock resilient API client
        resilient_client = ResilientAPIClient(
            name="demo_api",
            base_url="https://httpbin.org",
            rate_limit_per_second=2.0
        )
        
        # Test successful request
        print("\n✅ Testing successful request:")
        try:
            result = await resilient_client.make_request("GET", "/get", {"test": "demo"})
            print(f"   Success: {result['url']}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test error handling
        print("\n❌ Testing error handling (simulated 500 error):")
        try:
            await resilient_client.make_request("GET", "/status/500")
        except Exception as e:
            print(f"   Handled error: {type(e).__name__}")
            print(f"   Error message: {str(e)}")
        
        # Show health status
        health = resilient_client.get_health_status()
        print(f"\n🏥 API Client Health:")
        print(f"   - Status: {health['health_status']}")
        print(f"   - Total requests: {health['request_stats']['total_requests']}")
        success_rate = health['request_stats']['successful_requests'] / max(health['request_stats']['total_requests'], 1) * 100
        print(f"   - Success rate: {success_rate:.1f}%")
        print(f"   - Avg response time: {health['avg_response_time_ms']:.1f}ms")
        
        # Show error aggregation
        error_summary = error_aggregator.get_error_summary(1)
        print(f"\n📊 Error Summary (last hour):")
        print(f"   - Total errors: {error_summary['total_errors']}")
        if error_summary['by_category']:
            print(f"   - By category: {error_summary['by_category']}")
        if error_summary['by_severity']:
            print(f"   - By severity: {error_summary['by_severity']}")
    
    async def run_complete_demo(self):
        """Run the complete demonstration."""
        print("🚀 Legal Data Integration System Demo (Offline Mode)")
        print("====================================================")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("\n🔧 This demo uses mock implementations to demonstrate system")
        print("   capabilities without requiring external dependencies.")
        
        try:
            # Step 1: API Data Retrieval
            cases = await self.demonstrate_api_retrieval()
            
            # Step 2: Data Processing
            processed_docs = await self.demonstrate_data_processing(cases)
            
            # Step 3: GraphRAG Indexing
            indexing_results = await self.demonstrate_graphrag_indexing(processed_docs)
            
            # Step 4: Search and Retrieval
            await self.demonstrate_search_and_retrieval()
            
            # Step 5: Performance Monitoring
            await self.demonstrate_performance_monitoring()
            
            # Step 6: Error Handling
            await self.demonstrate_error_handling()
            
            # Demo summary
            print("\n" + "="*80)
            print("DEMO COMPLETE - SUMMARY")
            print("="*80)
            print(f"✅ Successfully processed {len(cases)} legal cases")
            print(f"✅ Created {len(processed_docs)} processed documents")
            print(f"✅ Completed {len(indexing_results)} indexing operations")
            print("✅ Demonstrated search and retrieval capabilities")
            print("✅ Showed performance monitoring and analytics")
            print("✅ Tested error handling and resilience patterns")
            
            print(f"\n🎯 Key Features Demonstrated:")
            print("   - Multi-source legal data API integration")
            print("   - Advanced NLP processing and standardization")
            print("   - GraphRAG indexing with graph and vector databases")
            print("   - Real-time search and similarity matching")
            print("   - Comprehensive performance monitoring")
            print("   - Robust error handling with circuit breakers")
            print("   - Automatic retry mechanisms and rate limiting")
            
            print(f"\n📚 Next Steps for Production Setup:")
            print("   - Configure API keys in .env file")
            print("   - Set up Neo4j and vector database (Pinecone/Weaviate)")
            print("   - Install and configure spaCy models")
            print("   - Run comprehensive tests with pytest")
            print("   - Deploy with proper monitoring and alerting")
            print("   - Scale horizontally for production workloads")
            
            print(f"\n🎉 Note: This offline demo successfully demonstrated")
            print("   all system capabilities using mock implementations!")
            
        except Exception as e:
            print(f"\n❌ Demo failed: {e}")
            logger.error("Demo execution failed", error=str(e), exc_info=True)
            return False
        
        print(f"\n🏁 Demo completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return True


async def main():
    """Main demo function."""
    try:
        demo = LegalDataDemo()
        success = await demo.run_complete_demo()
        
        if success:
            print("\n✅ Demo completed successfully!")
            return 0
        else:
            print("\n❌ Demo failed!")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️ Demo interrupted by user")
        return 130
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        logger.error("Unexpected demo error", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    # Run the demo
    exit_code = asyncio.run(main())
    sys.exit(exit_code)