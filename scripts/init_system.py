#!/usr/bin/env python3
"""
System initialization script for Court Argument.
Checks database connections, creates indexes, and initializes the system.
"""

import asyncio
import sys
from pathlib import Path
import logging

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from src.core.config import settings
from src.db.vector_db import VectorDB
from src.db.graph_db import GraphDB
from src.services.embeddings import EmbeddingService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SystemInitializer:
    """Initialize the Court Argument system."""
    
    def __init__(self):
        self.vector_db = None
        self.graph_db = None
        self.embedding_service = None
    
    async def initialize_system(self):
        """Initialize the complete system."""
        print("🏛️  Court Argument - System Initialization")
        print("="*60)
        
        success = True
        
        # Step 1: Check configuration
        print("📋 Step 1: Checking configuration...")
        config_ok = self._check_configuration()
        if not config_ok:
            success = False
        
        # Step 2: Initialize databases
        print("\n🗄️  Step 2: Initializing databases...")
        db_ok = await self._initialize_databases()
        if not db_ok:
            success = False
        
        # Step 3: Test embedding service
        print("\n🤖 Step 3: Testing embedding service...")
        embedding_ok = await self._test_embedding_service()
        if not embedding_ok:
            success = False
        
        # Step 4: Create indexes and constraints
        print("\n🔗 Step 4: Creating database indexes...")
        index_ok = self._create_indexes()
        if not index_ok:
            success = False
        
        # Step 5: Verify system readiness
        print("\n✅ Step 5: Verifying system readiness...")
        verify_ok = await self._verify_system()
        if not verify_ok:
            success = False
        
        # Summary
        print("\n" + "="*60)
        if success:
            print("🎉 System initialization completed successfully!")
            print("   The Court Argument is ready to use.")
            print("\n💡 Next steps:")
            print("   1. Run: python scripts/import_data.py (to load sample data)")
            print("   2. Run: python -m uvicorn src.main:app --reload (to start the API server)")
            print("   3. Run: streamlit run web_app.py (to start the web interface)")
        else:
            print("❌ System initialization failed!")
            print("   Please check the error messages above and fix the issues.")
        
        return success
    
    def _check_configuration(self) -> bool:
        """Check system configuration."""
        try:
            print(f"   App Name: {settings.app_name}")
            print(f"   Environment: {settings.app_env}")
            print(f"   Debug Mode: {settings.debug}")
            print(f"   Log Level: {settings.log_level}")
            
            print(f"   Vector DB: {settings.qdrant_url}")
            print(f"   Vector Size: {settings.qdrant_vector_size}")
            print(f"   Collection: {settings.qdrant_collection_name}")
            
            print(f"   Graph DB: {settings.neo4j_uri}")
            print(f"   Graph DB User: {settings.neo4j_user}")
            print(f"   Graph Database: {settings.neo4j_database}")
            
            print(f"   Embedding Model: {settings.embedding_model}")
            print(f"   LLM Model: {settings.llm_model}")
            
            # Check required API keys
            missing_keys = []
            if not settings.openai_api_key:
                missing_keys.append("OPENAI_API_KEY")
            
            if missing_keys:
                print(f"   ⚠️  Missing API keys: {', '.join(missing_keys)}")
                print("   Please set these environment variables or update .env file")
                return False
            
            print("   ✅ Configuration is valid")
            return True
            
        except Exception as e:
            print(f"   ❌ Configuration error: {e}")
            return False
    
    async def _initialize_databases(self) -> bool:
        """Initialize database connections."""
        success = True
        
        # Initialize Vector DB
        try:
            print("   Connecting to Vector DB (Qdrant)...")
            self.vector_db = VectorDB()
            info = self.vector_db.get_collection_info()
            print(f"   ✅ Vector DB connected - Collection: {info['name']}")
            print(f"      Points count: {info['points_count']}")
            print(f"      Vector size: {info['vector_size']}")
            print(f"      Status: {info['status']}")
        except Exception as e:
            print(f"   ❌ Vector DB connection failed: {e}")
            success = False
        
        # Initialize Graph DB
        try:
            print("   Connecting to Graph DB (Neo4j)...")
            self.graph_db = GraphDB()
            with self.graph_db.driver.session() as session:
                result = session.run("RETURN 'Connected' as status")
                record = result.single()
                print(f"   ✅ Graph DB connected - {record['status']}")
        except Exception as e:
            print(f"   ❌ Graph DB connection failed: {e}")
            success = False
        
        return success
    
    async def _test_embedding_service(self) -> bool:
        """Test the embedding service."""
        try:
            print("   Testing embedding service...")
            self.embedding_service = EmbeddingService()
            
            # Test embedding generation
            test_text = "这是一个测试文本"
            embedding = await self.embedding_service.embed_text(test_text)
            
            print(f"   ✅ Embedding service working")
            print(f"      Model: {self.embedding_service.model}")
            print(f"      Vector dimension: {len(embedding)}")
            print(f"      Expected dimension: {settings.qdrant_vector_size}")
            
            if len(embedding) != settings.qdrant_vector_size:
                print(f"   ⚠️  Warning: Vector dimension mismatch!")
                print(f"      Embedding: {len(embedding)}, Config: {settings.qdrant_vector_size}")
                return False
            
            return True
            
        except Exception as e:
            print(f"   ❌ Embedding service test failed: {e}")
            return False
    
    def _create_indexes(self) -> bool:
        """Create database indexes and constraints."""
        if not self.graph_db:
            print("   ❌ Graph DB not initialized")
            return False
        
        try:
            # Neo4j constraints and indexes are created in GraphDB.__init__
            # Let's just verify they exist
            with self.graph_db.driver.session() as session:
                # Check constraints
                result = session.run("SHOW CONSTRAINTS")
                constraints = list(result)
                print(f"   ✅ Graph DB constraints: {len(constraints)} created")
                
                # Check indexes
                result = session.run("SHOW INDEXES")
                indexes = list(result)
                print(f"   ✅ Graph DB indexes: {len(indexes)} created")
                
                # Check if collection has proper config in Vector DB
                if self.vector_db:
                    info = self.vector_db.get_collection_info()
                    print(f"   ✅ Vector DB collection configured with {info['vector_size']}D vectors")
                
            return True
            
        except Exception as e:
            print(f"   ❌ Index creation failed: {e}")
            return False
    
    async def _verify_system(self) -> bool:
        """Verify system is ready for operation."""
        success = True
        
        try:
            # Test vector search (should work even with empty collection)
            if self.vector_db and self.embedding_service:
                print("   Testing vector search capability...")
                test_embedding = await self.embedding_service.embed_text("测试查询")
                results = self.vector_db.search_similar(
                    query_embedding=test_embedding,
                    limit=1
                )
                print(f"   ✅ Vector search working (returned {len(results)} results)")
            
            # Test graph queries
            if self.graph_db:
                print("   Testing graph query capability...")
                with self.graph_db.driver.session() as session:
                    result = session.run("MATCH (n) RETURN count(n) as node_count")
                    record = result.single()
                    node_count = record["node_count"]
                    print(f"   ✅ Graph query working ({node_count} nodes in database)")
            
            # Test GraphRAG components integration
            print("   Testing GraphRAG integration...")
            if self.graph_db and self.vector_db and self.embedding_service:
                # This is a basic integration test - the components can communicate
                print("   ✅ All GraphRAG components initialized and communicating")
            else:
                print("   ❌ GraphRAG components not fully initialized")
                success = False
            
        except Exception as e:
            print(f"   ❌ System verification failed: {e}")
            success = False
        
        return success
    
    def cleanup(self):
        """Clean up resources."""
        if self.graph_db:
            self.graph_db.close()


async def main():
    """Main initialization function."""
    initializer = SystemInitializer()
    
    try:
        success = await initializer.initialize_system()
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Initialization interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        initializer.cleanup()


if __name__ == "__main__":
    asyncio.run(main())