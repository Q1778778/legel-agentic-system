#!/usr/bin/env python3
"""Wait for databases to be available before starting the application."""

import time
import sys
import os
from typing import Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import settings
from src.db.graph_db import GraphDB
from src.db.vector_db import VectorDB
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def check_databases() -> Tuple[bool, bool]:
    """Check if databases are available.
    
    Returns:
        Tuple of (neo4j_available, qdrant_available)
    """
    neo4j_available = False
    qdrant_available = False
    
    # Check Neo4j
    try:
        logger.info("Checking Neo4j availability...")
        graph_db = GraphDB()
        if graph_db.is_available():
            logger.info("Neo4j is available")
            neo4j_available = True
        else:
            logger.warning("Neo4j is not available")
        graph_db.close()
    except Exception as e:
        logger.warning(f"Neo4j check failed: {e}")
    
    # Check Qdrant
    try:
        logger.info("Checking Qdrant availability...")
        vector_db = VectorDB()
        if vector_db.is_available():
            logger.info("Qdrant is available")
            qdrant_available = True
        else:
            logger.warning("Qdrant is not available")
    except Exception as e:
        logger.warning(f"Qdrant check failed: {e}")
    
    return neo4j_available, qdrant_available


def wait_for_databases(max_wait: int = 60, check_interval: int = 5) -> bool:
    """Wait for at least one database to become available.
    
    Args:
        max_wait: Maximum time to wait in seconds
        check_interval: Time between checks in seconds
    
    Returns:
        True if at least one database is available, False otherwise
    """
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        neo4j_ok, qdrant_ok = check_databases()
        
        if neo4j_ok and qdrant_ok:
            logger.info("All databases are available")
            return True
        elif neo4j_ok or qdrant_ok:
            if settings.db_graceful_degradation:
                logger.warning(
                    "Running in degraded mode",
                    neo4j=neo4j_ok,
                    qdrant=qdrant_ok
                )
                return True
            else:
                logger.info(
                    "Waiting for all databases...",
                    neo4j=neo4j_ok,
                    qdrant=qdrant_ok
                )
        else:
            logger.info("No databases available yet, waiting...")
        
        time.sleep(check_interval)
    
    # Check one more time
    neo4j_ok, qdrant_ok = check_databases()
    
    if settings.db_graceful_degradation and (neo4j_ok or qdrant_ok):
        logger.warning(
            "Starting in degraded mode after timeout",
            neo4j=neo4j_ok,
            qdrant=qdrant_ok
        )
        return True
    
    return False


def main():
    """Main entry point."""
    logger.info("Starting database availability check...")
    
    # Check if we should skip waiting (for development)
    if os.environ.get("SKIP_DB_WAIT", "").lower() == "true":
        logger.info("Skipping database wait (SKIP_DB_WAIT=true)")
        return 0
    
    # Wait for databases
    if wait_for_databases():
        logger.info("System ready to start")
        return 0
    else:
        if settings.db_graceful_degradation:
            logger.error("No databases available, but starting anyway (graceful degradation enabled)")
            return 0
        else:
            logger.error("Failed to connect to any database within timeout")
            return 1


if __name__ == "__main__":
    sys.exit(main())