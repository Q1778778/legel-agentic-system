#!/usr/bin/env python3
"""Standalone runner for MCP Lawyer Server."""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_lawyer_server.server import MCPLawyerServer
import structlog

# Configure logging for standalone mode
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
        structlog.dev.ConsoleRenderer()  # Use console renderer for standalone
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def main():
    """Main entry point for standalone server."""
    logger.info("Starting MCP Lawyer Server in standalone mode")
    
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not set, some features may not work")
    
    # Get config path
    config_path = os.getenv("MCP_CONFIG_PATH", "config.yaml")
    
    # Create server
    server = MCPLawyerServer(config_path)
    
    try:
        logger.info("MCP Lawyer Server ready for connections")
        logger.info("Connect using MCP client via stdio transport")
        await server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        await server.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    # Run the server
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutdown complete")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)