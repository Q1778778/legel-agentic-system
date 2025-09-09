# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Storage module for conversation history.
Provides a unified interface for storing and retrieving conversation history,
similar to how retriever.py handles vector database operations.
"""

import os
import sys
import json
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod

from core.config import CONFIG
from core.embedding import get_embedding
from core.schemas import ConversationEntry
from misc.logger.logging_config_helper import get_configured_logger
    
logger = get_configured_logger("storage")

class StorageProvider(ABC):
    """Abstract base class for storage providers."""
    
    @abstractmethod
    async def add_conversation(self, user_id: str, site: str, message_id: Optional[str], 
                             user_prompt: str, response: str, conversation_id: str,
                             embedding: Optional[List[float]] = None,
                             summary: Optional[str] = None, main_topics: Optional[List[str]] = None,
                             participants: Optional[List[Dict[str, Any]]] = None) -> ConversationEntry:
        """
        Add a conversation to storage.
        
        Args:
            user_id: User ID (if logged in) or anonymous ID
            site: Site context for the conversation
            message_id: Message ID for grouping. If None, create a new message_id
            user_prompt: The user's question/prompt
            response: The assistant's response
            conversation_id: The conversation ID (required, from frontend)
            embedding: Optional pre-computed embedding vector
            summary: Optional LLM-generated summary
            main_topics: Optional list of main topics
            participants: Optional list of participants
            
        Returns:
            ConversationEntry: The created conversation entry with generated conversation_id
        """
        pass
    
    @abstractmethod
    async def get_conversation_by_id(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieve all conversations with the given conversation_id.
        
        Args:
            conversation_id: The conversation ID to retrieve
            limit: Optional limit to return only the N most recent exchanges
            
        Returns:
            List of conversation entries
        """
        pass
    
    @abstractmethod
    async def get_recent_conversations(self, user_id: str, site: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve the N most recent conversations for a user and site, grouped by thread.
        
        Args:
            user_id: User ID to retrieve conversations for
            site: Site to filter by
            limit: Maximum number of conversations to retrieve
            
        Returns:
            List of thread objects, each containing:
            {
                "id": message_id,
                "site": site,
                "conversations": [
                    {
                        "id": conversation_id,
                        "user_prompt": prompt,
                        "response": response,
                        "time": timestamp
                    },
                    ...
                ]  # sorted by date, oldest first
            }
        """
        pass
    
    @abstractmethod
    async def delete_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> bool:
        """
        Delete a specific conversation.
        
        Args:
            conversation_id: ID of the conversation to delete
            user_id: Optional user ID for access control
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        pass

    @abstractmethod
    async def search_conversations(self, query: str, user_id: Optional[str] = None, 
                                 site: Optional[str] = None, limit: int = 10) -> List[ConversationEntry]:
        """
        Search conversations using a query string.

        Args:
            query: The search query string
            user_id: Optional user ID to filter results
            site: Optional site to filter results
            limit: Maximum number of results to return

        Returns:
            List[ConversationEntry]: The search results
        """
        pass

# Global storage client instance
_storage_client = None
_storage_lock = asyncio.Lock()

async def get_storage_client() -> StorageProvider:
    """
    Get or create the storage client instance.
    
    Returns:
        StorageProvider: The storage provider instance
    """
    global _storage_client
    
    if _storage_client is not None:
        return _storage_client
    
    async with _storage_lock:
        # Double-check after acquiring lock
        if _storage_client is not None:
            return _storage_client
        
        # Get storage configuration from CONFIG
        storage_config = CONFIG.conversation_storage
        storage_type = storage_config.type
        
        logger.info(f"Initializing storage client with type: {storage_type}")
        
        if storage_type == 'qdrant':
            from storage_providers.qdrant_storage import QdrantStorageProvider
            _storage_client = QdrantStorageProvider(storage_config)
        elif storage_type == 'azure_ai_search':
            from storage_providers.azure_search_storage import AzureSearchStorageProvider
            _storage_client = AzureSearchStorageProvider(storage_config)
        elif storage_type == 'azure_cosmos':
            from storage_providers.cosmos_storage import CosmosStorageProvider
            _storage_client = CosmosStorageProvider(storage_config)
        elif storage_type == 'postgres':
            from storage_providers.postgres_storage import PostgresStorageProvider
            _storage_client = PostgresStorageProvider(storage_config)
        else:
            # Default to Qdrant for now
            from storage_providers.qdrant_storage import QdrantStorageProvider
            logger.warning(f"Unknown storage type '{storage_type}', defaulting to Qdrant")
            _storage_client = QdrantStorageProvider(storage_config)
        
        # Initialize the storage provider
        await _storage_client.initialize()
        
        logger.info(f"Storage client initialized successfully")
        return _storage_client

async def add_conversation(user_id: str, site: str, message_id: Optional[str], 
                         user_prompt: str, response: str, conversation_id: str,
                         embedding: Optional[List[float]] = None,
                         summary: Optional[str] = None, main_topics: Optional[List[str]] = None,
                         participants: Optional[List[Dict[str, Any]]] = None) -> ConversationEntry:
    """
    Add a conversation to storage.
    
    Args:
        user_id: User ID (can be anonymous ID)
        site: Site context
        message_id: Message ID for grouping. If None, create a new message_id
        user_prompt: User's question
        response: Assistant's response
        conversation_id: The conversation ID (required, from frontend)
        embedding: Optional pre-computed embedding vector
        summary: Optional LLM-generated summary
        main_topics: Optional list of main topics
        participants: Optional list of participants
        
    Returns:
        ConversationEntry: The stored conversation entry
    """
    client = await get_storage_client()
    return await client.add_conversation(user_id, site, message_id, user_prompt, response, 
                                        conversation_id, embedding, summary, main_topics, participants)

async def get_conversation_by_id(conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get all conversations with the given conversation_id.
    
    Args:
        conversation_id: The conversation ID to retrieve
        limit: Optional limit to return only the N most recent exchanges
        
    Returns:
        List of conversation entries
    """
    client = await get_storage_client()
    return await client.get_conversation_by_id(conversation_id, limit)

async def get_recent_conversations(user_id: str, site: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get recent conversations for a user and site, grouped by thread.
    
    Args:
        user_id: User ID
        site: Site to filter by
        limit: Maximum number of conversations to return
        
    Returns:
        List of thread objects with conversations
    """
    client = await get_storage_client()
    return await client.get_recent_conversations(user_id, site, limit)

async def delete_conversation(conversation_id: str, user_id: Optional[str] = None) -> bool:
    """
    Delete a specific conversation.
    
    Args:
        conversation_id: Conversation ID to delete
        user_id: Optional user ID for access control
        
    Returns:
        bool: Success status
    """
    client = await get_storage_client()
    return await client.delete_conversation(conversation_id, user_id)

# Convenience function for migration from localStorage
async def migrate_from_localstorage(user_id: str, conversations_data: List[Dict[str, Any]]) -> int:
    """
    Migrate conversations from browser localStorage to server storage.
    
    Args:
        user_id: User ID to assign to migrated conversations
        conversations_data: List of conversation data from localStorage
        
    Returns:
        int: Number of conversations migrated
    """
    migrated_count = 0
    
    for conv_data in conversations_data:
        try:
            # Handle converted format from client
            message_id = conv_data.get('message_id', conv_data.get('thread_id', str(uuid.uuid4())))
            site = conv_data.get('site', 'all')
            user_prompt = conv_data.get('user_prompt', '')
            response = conv_data.get('response', '')
            
            if user_prompt and response:
                await add_conversation(
                    user_id=user_id,
                    site=site,
                    message_id=message_id,
                    user_prompt=user_prompt,
                    response=response
                )
                migrated_count += 1
                        
        except Exception as e:
            logger.error(f"Error migrating conversation: {e}")
            continue
    
    return migrated_count