"""
MCP Initializer
Production-ready initialization and lifecycle management for MCP services.
"""

import asyncio
from typing import Optional
import structlog
from contextlib import asynccontextmanager

from .mcp_sdk_bridge import get_mcp_bridge, MCPSDKBridge
from .mcp_session_manager import get_session_manager, configure_session_manager
from .mcp_config_loader import get_mcp_config_loader

logger = structlog.get_logger(__name__)


class MCPInitializer:
    """Manages MCP service initialization and lifecycle."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize MCP initializer.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config_loader = get_mcp_config_loader(config_path)
        self.bridge: Optional[MCPSDKBridge] = None
        self.session_manager = None
        self.initialized = False
        
    async def initialize(self):
        """Initialize all MCP services."""
        try:
            logger.info("Starting MCP service initialization")
            
            # Load configuration
            config = self.config_loader.load()
            
            # Validate configuration
            if not self.config_loader.validate():
                raise ValueError("Configuration validation failed")
                
            # Initialize session manager
            session_config = self.config_loader.get_session_config()
            self.session_manager = configure_session_manager(**session_config)
            await self.session_manager.initialize()
            logger.info("Session manager initialized")
            
            # Initialize MCP bridge
            self.bridge = get_mcp_bridge()
            server_configs = self.config_loader.get_server_configs()
            await self.bridge.initialize(server_configs)
            logger.info("MCP bridge initialized")
            
            self.initialized = True
            logger.info("MCP services initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP services: {e}")
            await self.shutdown()
            raise
            
    async def shutdown(self):
        """Shutdown all MCP services."""
        logger.info("Shutting down MCP services")
        
        try:
            # Shutdown bridge
            if self.bridge:
                await self.bridge.shutdown()
                logger.info("MCP bridge shut down")
                
            # Shutdown session manager
            if self.session_manager:
                await self.session_manager.shutdown()
                logger.info("Session manager shut down")
                
            self.initialized = False
            logger.info("MCP services shut down successfully")
            
        except Exception as e:
            logger.error(f"Error during MCP shutdown: {e}")
            
    async def health_check(self) -> dict:
        """Perform health check on MCP services."""
        health_status = {
            "initialized": self.initialized,
            "bridge": None,
            "session_manager": None,
            "servers": {}
        }
        
        try:
            if self.bridge:
                bridge_status = self.bridge.get_status()
                health_status["bridge"] = bridge_status
                health_status["servers"] = bridge_status.get("servers", {})
                
            if self.session_manager:
                health_status["session_manager"] = self.session_manager.get_status()
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_status["error"] = str(e)
            
        return health_status
        
    def is_initialized(self) -> bool:
        """Check if MCP services are initialized."""
        return self.initialized
        
    async def reload_config(self):
        """Reload configuration and restart services if needed."""
        logger.info("Reloading MCP configuration")
        
        try:
            # Reload configuration
            self.config_loader.reload()
            
            # Restart services with new configuration
            await self.shutdown()
            await self.initialize()
            
            logger.info("MCP configuration reloaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            raise
            
    @asynccontextmanager
    async def lifespan(self):
        """Context manager for MCP service lifecycle."""
        try:
            await self.initialize()
            yield self
        finally:
            await self.shutdown()


# Singleton instance
_initializer: Optional[MCPInitializer] = None


def get_mcp_initializer(config_path: Optional[str] = None) -> MCPInitializer:
    """Get singleton MCP initializer instance."""
    global _initializer
    if _initializer is None or config_path:
        _initializer = MCPInitializer(config_path)
    return _initializer


async def initialize_mcp_services(config_path: Optional[str] = None):
    """Initialize all MCP services."""
    initializer = get_mcp_initializer(config_path)
    await initializer.initialize()
    return initializer


async def shutdown_mcp_services():
    """Shutdown all MCP services."""
    initializer = get_mcp_initializer()
    if initializer:
        await initializer.shutdown()