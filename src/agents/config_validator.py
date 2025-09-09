"""Configuration validator for OpenAI API and agent initialization."""

import os
import structlog
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

logger = structlog.get_logger()


class ConfigValidator:
    """Validates and provides configuration for agent initialization."""
    
    @staticmethod
    def get_openai_api_key() -> Optional[str]:
        """Get OpenAI API key from environment with validation.
        
        Returns:
            API key if found and valid, None otherwise
        """
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            logger.warning("OPENAI_API_KEY not found in environment variables")
            return None
        
        if api_key.startswith("sk-"):
            logger.info("Valid OpenAI API key format detected")
            return api_key
        else:
            logger.warning("Invalid OpenAI API key format (should start with 'sk-')")
            return None
    
    @staticmethod
    async def validate_openai_connection(api_key: Optional[str] = None) -> bool:
        """Validate OpenAI API connection.
        
        Args:
            api_key: Optional API key to test
            
        Returns:
            True if connection is valid
        """
        if not api_key:
            api_key = ConfigValidator.get_openai_api_key()
        
        if not api_key:
            logger.error("No API key available for validation")
            return False
        
        try:
            client = AsyncOpenAI(api_key=api_key)
            # Try a simple API call to validate
            models = await client.models.list()
            logger.info(f"Successfully connected to OpenAI API, {len(models.data)} models available")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI API: {e}")
            return False
    
    @staticmethod
    def get_model_config() -> Dict[str, Any]:
        """Get model configuration with fallbacks.
        
        Returns:
            Model configuration dictionary
        """
        return {
            "default_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2000")),
            "enable_mock": os.getenv("ENABLE_MOCK_AGENTS", "true").lower() == "true"
        }
    
    @staticmethod
    def validate_environment() -> Dict[str, bool]:
        """Validate all required environment variables.
        
        Returns:
            Dictionary of validation results
        """
        validations = {
            "openai_api_key": ConfigValidator.get_openai_api_key() is not None,
            "neo4j_configured": bool(os.getenv("NEO4J_URI")),
            "qdrant_configured": bool(os.getenv("QDRANT_HOST")),
            "redis_configured": bool(os.getenv("REDIS_URL")),
        }
        
        # Log validation results
        for key, valid in validations.items():
            if valid:
                logger.info(f"✓ {key} is configured")
            else:
                logger.warning(f"✗ {key} is not configured")
        
        return validations
    
    @staticmethod
    def get_agent_config(agent_type: str = "base") -> Dict[str, Any]:
        """Get configuration for a specific agent type.
        
        Args:
            agent_type: Type of agent (base, prosecutor, defender, feedback)
            
        Returns:
            Agent configuration dictionary
        """
        model_config = ConfigValidator.get_model_config()
        api_key = ConfigValidator.get_openai_api_key()
        
        # Base configuration
        config = {
            "api_key": api_key,
            "model": model_config["default_model"],
            "temperature": model_config["temperature"],
            "max_tokens": model_config["max_tokens"],
            "enable_mock": model_config["enable_mock"] or not api_key
        }
        
        # Agent-specific overrides
        if agent_type == "prosecutor":
            config.update({
                "temperature": 0.8,  # More assertive
                "name": "Lead Prosecutor",
                "role": "prosecutor"
            })
        elif agent_type == "defender":
            config.update({
                "temperature": 0.7,  # Balanced
                "name": "Defense Attorney",
                "role": "defender"
            })
        elif agent_type == "feedback":
            config.update({
                "temperature": 0.5,  # More analytical
                "name": "Legal Expert",
                "role": "feedback"
            })
        elif agent_type == "lawyer":
            config.update({
                "temperature": 0.6,  # Professional
                "name": "Legal Analyst",
                "role": "lawyer"
            })
        
        return config