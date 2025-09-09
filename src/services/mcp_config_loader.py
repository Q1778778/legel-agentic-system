"""
MCP Configuration Loader
Utility for loading and managing MCP configuration from YAML files.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
from pydantic import BaseModel, Field, validator

from .mcp_sdk_bridge import MCPServerConfig, MCPServerType, StorageBackend

logger = structlog.get_logger(__name__)


class MCPConfig(BaseModel):
    """Complete MCP configuration model."""
    
    servers: Dict[str, Dict[str, Any]]
    session: Dict[str, Any]
    websocket: Dict[str, Any]
    bridge: Dict[str, Any]
    logging: Dict[str, Any]
    monitoring: Dict[str, Any]
    security: Dict[str, Any]
    features: Dict[str, Any]
    integration: Dict[str, Any]
    development: Dict[str, Any] = Field(default_factory=dict)
    production: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('servers')
    def validate_servers(cls, v):
        """Validate server configurations."""
        for server_name, server_config in v.items():
            if 'command' not in server_config:
                raise ValueError(f"Server {server_name} missing 'command'")
            if 'type' not in server_config:
                raise ValueError(f"Server {server_name} missing 'type'")
        return v


class MCPConfigLoader:
    """Loads and manages MCP configuration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration loader.
        
        Args:
            config_path: Path to configuration file. If None, uses default.
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            # Default configuration path
            self.config_path = Path(__file__).parent.parent.parent / "config" / "mcp_config.yaml"
            
        self.config: Optional[MCPConfig] = None
        self._env_vars: Dict[str, str] = {}
        
    def load(self) -> MCPConfig:
        """Load configuration from file."""
        try:
            if not self.config_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
                
            with open(self.config_path, 'r') as f:
                raw_config = yaml.safe_load(f)
                
            # Replace environment variables
            raw_config = self._replace_env_vars(raw_config)
            
            # Parse configuration
            self.config = MCPConfig(**raw_config)
            
            logger.info(f"Loaded MCP configuration from {self.config_path}")
            return self.config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
            
    def _replace_env_vars(self, config: Any) -> Any:
        """Recursively replace environment variables in configuration.
        
        Replaces ${VAR_NAME} with environment variable value.
        """
        if isinstance(config, dict):
            return {k: self._replace_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._replace_env_vars(item) for item in config]
        elif isinstance(config, str):
            # Check for environment variable pattern
            if config.startswith("${") and config.endswith("}"):
                var_name = config[2:-1]
                value = os.environ.get(var_name)
                if value is None:
                    logger.warning(f"Environment variable {var_name} not found")
                    return config
                return value
            return config
        else:
            return config
            
    def get_server_configs(self) -> List[MCPServerConfig]:
        """Get list of MCPServerConfig objects from configuration."""
        if not self.config:
            self.load()
            
        server_configs = []
        
        for server_name, server_data in self.config.servers.items():
            # Map configuration to MCPServerConfig
            config = MCPServerConfig(
                name=server_data.get("name", server_name),
                type=MCPServerType(server_data.get("type")),
                command=server_data.get("command", []),
                args=server_data.get("args", []),
                env=server_data.get("env", {}),
                working_dir=server_data.get("working_dir"),
                auto_restart=server_data.get("auto_restart", True),
                max_retries=server_data.get("max_retries", 5),
                retry_delay=server_data.get("retry_delay", 1.0),
                health_check_interval=server_data.get("health_check_interval", 30.0),
                timeout=server_data.get("timeout", 60.0)
            )
            server_configs.append(config)
            
        return server_configs
        
    def get_session_config(self) -> Dict[str, Any]:
        """Get session configuration."""
        if not self.config:
            self.load()
            
        return {
            "storage_backend": StorageBackend(self.config.session.get("storage_backend", "memory")),
            "redis_url": self.config.session.get("redis_url"),
            "session_timeout": self.config.session.get("session_timeout", 3600),
            "max_sessions_per_client": self.config.session.get("max_sessions_per_client", 10)
        }
        
    def get_websocket_config(self) -> Dict[str, Any]:
        """Get WebSocket configuration."""
        if not self.config:
            self.load()
            
        return self.config.websocket
        
    def get_feature_flags(self) -> Dict[str, Any]:
        """Get feature flags."""
        if not self.config:
            self.load()
            
        return self.config.features
        
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled."""
        if not self.config:
            self.load()
            
        return self.config.features.get(feature, False)
        
    def get_integration_config(self, service: str) -> Dict[str, Any]:
        """Get integration configuration for a specific service."""
        if not self.config:
            self.load()
            
        return self.config.integration.get(service, {})
        
    def reload(self):
        """Reload configuration from file."""
        self.config = None
        return self.load()
        
    def validate(self) -> bool:
        """Validate configuration."""
        try:
            if not self.config:
                self.load()
                
            # Check required fields
            if not self.config.servers:
                raise ValueError("No servers configured")
                
            # Validate server executables exist
            for server_config in self.get_server_configs():
                if server_config.command:
                    # Check if command is executable
                    cmd = server_config.command[0]
                    if not (cmd == "python" or Path(cmd).exists()):
                        logger.warning(f"Command '{cmd}' for server {server_config.name} may not exist")
                        
            logger.info("Configuration validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        if not self.config:
            self.load()
            
        return self.config.dict()


# Singleton instance
_config_loader: Optional[MCPConfigLoader] = None


def get_mcp_config_loader(config_path: Optional[str] = None) -> MCPConfigLoader:
    """Get singleton configuration loader instance."""
    global _config_loader
    if _config_loader is None or config_path:
        _config_loader = MCPConfigLoader(config_path)
    return _config_loader


def load_mcp_config(config_path: Optional[str] = None) -> MCPConfig:
    """Load MCP configuration."""
    loader = get_mcp_config_loader(config_path)
    return loader.load()