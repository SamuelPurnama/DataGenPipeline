"""
Modular Knowledge Base Client

This module provides a clean abstraction layer for knowledge base operations.
Designed to be easily extended for different knowledge base types (GraphRAG, Pinecone, etc.).
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class KnowledgeBaseClient(ABC):
    """Abstract base class for knowledge base clients."""
    
    @abstractmethod
    async def search_trajectories(self, query: str, max_results: int = 3, max_context_length: int = 3000) -> str:
        """Search for relevant trajectories based on a query."""
        pass
    
    @abstractmethod
    async def add_trajectory(self, trajectory_data: dict) -> bool:
        """Add a trajectory to the knowledge base."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the knowledge base is available and configured."""
        pass


class KnowledgeBaseManager:
    """Manager class for handling knowledge base operations in a sync context."""
    
    def __init__(self, client: KnowledgeBaseClient):
        self.client = client
    
    def search_trajectories_sync(self, query: str, max_results: int = 3, max_context_length: int = 3000) -> str:
        """Synchronous wrapper for trajectory search."""
        try:
            # Run the async search in a new event loop
            return asyncio.run(self.client.search_trajectories(query, max_results, max_context_length))
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                # If we're already in an event loop, use a different approach
                logger.warning("⚠️ Already in event loop, using thread-based execution")
                return self._search_in_thread(query, max_results, max_context_length)
            else:
                logger.error(f"❌ Error in trajectory search: {e}")
                return ""
        except Exception as e:
            logger.error(f"❌ Unexpected error in trajectory search: {e}")
            return ""
    
    def add_trajectory_sync(self, trajectory_data: dict) -> bool:
        """Synchronous wrapper for adding trajectories."""
        try:
            # Run the async add in a new event loop
            return asyncio.run(self.client.add_trajectory(trajectory_data))
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                # If we're already in an event loop, use a different approach
                logger.warning("⚠️ Already in event loop, using thread-based execution")
                return self._add_in_thread(trajectory_data)
            else:
                logger.error(f"❌ Error in trajectory addition: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Unexpected error in trajectory addition: {e}")
            return False
    
    def _add_in_thread(self, trajectory_data: dict) -> bool:
        """Add trajectory in a separate thread to avoid event loop conflicts."""
        import concurrent.futures
        
        def _run_async_add():
            async def _add():
                return await self.client.add_trajectory(trajectory_data)
            return asyncio.run(_add())
        
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_async_add)
                return future.result(timeout=30)  # 30 second timeout
        except Exception as e:
            logger.error(f"❌ Error in thread-based trajectory addition: {e}")
            return False
    
    def _search_in_thread(self, query: str, max_results: int, max_context_length: int) -> str:
        """Search trajectories in a separate thread to avoid event loop conflicts."""
        import concurrent.futures
        
        def _run_async_search():
            async def _search():
                return await self.client.search_trajectories(query, max_results, max_context_length)
            return asyncio.run(_search())
        
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_async_search)
                return future.result(timeout=30)  # 30 second timeout
        except Exception as e:
            logger.error(f"❌ Error in thread-based search: {e}")
            return ""
    
    def is_available(self) -> bool:
        """Check if the knowledge base is available."""
        try:
            return asyncio.run(self.client.is_available())
        except Exception:
            return False


# High-level convenience functions for pipeline usage
def get_trajectory_context(query: str, max_results: int = 3, max_context_length: int = 3000, kb_type: str = "graphrag") -> str:
    """Get trajectory context from the specified knowledge base."""
    try:
        # Dynamically import and create the appropriate client
        if kb_type.lower() == "graphrag":
            from graphRAG.graphrag_client import GraphRAGClient
            client = GraphRAGClient()
        else:
            raise ValueError(f"Unsupported knowledge base type: {kb_type}")
        
        manager = KnowledgeBaseManager(client)
        return manager.search_trajectories_sync(query, max_results, max_context_length)
    except Exception as e:
        logger.error(f"❌ Error getting trajectory context: {e}")
        return ""

def add_trajectory_to_kb(trajectory_data: dict, kb_type: str = "graphrag") -> bool:
    """Add a trajectory to the specified knowledge base."""
    try:
        # Dynamically import and create the appropriate client
        if kb_type.lower() == "graphrag":
            from graphRAG.graphrag_client import GraphRAGClient
            client = GraphRAGClient()
        else:
            raise ValueError(f"Unsupported knowledge base type: {kb_type}")
        
        manager = KnowledgeBaseManager(client)
        return manager.add_trajectory_sync(trajectory_data)
    except Exception as e:
        logger.error(f"❌ Error adding trajectory to knowledge base: {e}")
        return False 