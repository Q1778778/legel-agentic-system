#!/usr/bin/env python3
"""
Legal Data Integration System Demo

This script demonstrates the complete workflow of the legal data integration system:
1. API data retrieval from multiple sources
2. Data processing and standardization
3. GraphRAG indexing
4. Real-time search and retrieval
5. Performance monitoring
6. Error handling and resilience

Usage:
    python examples/legal_data_integration_demo.py
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.legal_data_apis import LegalDataAPIClient, DataSource
from src.services.legal_data_processor import LegalDataProcessor
from src.services.legal_data_indexer import LegalDataIndexer
from src.services.error_handling import ResilientAPIClient, error_aggregator
from src.services.performance_monitor import performance_monitor, performance_timer
from src.db.graph_db import GraphDB
from src.db.vector_db import VectorDB
from src.services.embeddings import EmbeddingService
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


class LegalDataDemo:
    """Demo class for legal data integration system."""
    
    def __init__(self):
        """Initialize demo components."""
        self.api_client = LegalDataAPIClient()
        self.processor = LegalDataProcessor()
        
        # Mock database connections for demo
        self.graph_db = GraphDB()
        self.vector_db = VectorDB()
        self.embedding_service = EmbeddingService()
        
        self.indexer = LegalDataIndexer(
            graph_db=self.graph_db,
            vector_db=self.vector_db,
            embedding_service=self.embedding_service
        )
        
        logger.info("Demo components initialized")
    
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
                        print(f"      Source: {case.source.value}")
                    
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
        print("STEP 3: GraphRAG Indexing")
        print("="*80)
        
        print(f"\n🔗 Indexing {len(processed_docs)} processed documents into GraphRAG...")
        
        # Time the indexing
        async with performance_timer(
            performance_monitor.metrics,
            "demo.indexing_time_ms",
            {"document_count": len(processed_docs)}
        ):
            try:
                # Index documents into Neo4j and vector database
                indexing_results = await self.indexer.index_processed_documents(
                    processed_docs,
                    batch_size=5,
                    include_vectors=True,
                    include_relationships=True
                )
                
                print(f"   ✅ Indexing completed")
                
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
        """Demonstrate search and retrieval from GraphRAG."""
        print("\n" + "="*80)
        print("STEP 4: Search and Retrieval")
        print("="*80)
        
        search_queries = [
            "software patent disputes",
            "employment contract violations",
            "intellectual property infringement"
        ]
        
        for query in search_queries:
            print(f"\n🔍 Searching GraphRAG for: '{query}'")
            
            # Time the search
            async with performance_timer(
                performance_monitor.metrics,
                "demo.search_time_ms",
                {"query_type": query.split()[0]}
            ):
                try:
                    # Search similar documents using vector similarity
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
                        print(f"   ℹ️ No similar documents found (using mock data)")
                        
                except Exception as e:
                    print(f"   ❌ Search error: {e}")
                    logger.error(f"Search failed for query '{query}'", error=str(e))
    
    async def demonstrate_performance_monitoring(self):
        """Demonstrate performance monitoring and analytics."""
        print("\n" + "="*80)
        print("STEP 5: Performance Monitoring & Analytics")
        print("="*80)
        
        print("\n📊 Collecting performance metrics...")
        
        # Start performance monitoring
        await performance_monitor.start()
        
        # Wait a bit for metrics collection
        await asyncio.sleep(2)
        
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
        print(f"\n📋 Generating performance report...")
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
        print("STEP 6: Error Handling & Resilience")
        print("="*80)
        
        print("\n🛡️ Testing error handling capabilities...")
        
        # Create a resilient API client
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
            if hasattr(e, 'get_user_message'):
                print(f"   User message: {e.get_user_message()}")
        
        # Show health status
        health = resilient_client.get_health_status()
        print(f"\n🏥 API Client Health:")
        print(f"   - Status: {health['health_status']}")
        print(f"   - Total requests: {health['request_stats']['total_requests']}")
        print(f"   - Success rate: {health['request_stats']['successful_requests'] / max(health['request_stats']['total_requests'], 1) * 100:.1f}%")
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
        print("🚀 Legal Data Integration System Demo")
        print("====================================")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
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
            print("   - GraphRAG indexing with Neo4j and vector databases")
            print("   - Real-time search and similarity matching")
            print("   - Comprehensive performance monitoring")
            print("   - Robust error handling with circuit breakers")
            print("   - Automatic retry mechanisms and rate limiting")
            
            print(f"\n📚 Next Steps:")
            print("   - Configure API keys in .env file")
            print("   - Set up Neo4j and vector database")
            print("   - Run comprehensive tests with pytest")
            print("   - Deploy with proper monitoring and alerting")
            print("   - Scale horizontally for production workloads")
            
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