"""
GraphRAG Client Implementation

This module provides the GraphRAG-specific implementation of the knowledge base client.
Uses Graphiti for trajectory search and context retrieval.
"""

import os
import logging
from pathlib import Path
import sys
import os
# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.knowledge_base_client import KnowledgeBaseClient

logger = logging.getLogger(__name__)


class GraphRAGClient(KnowledgeBaseClient):
    """GraphRAG-specific implementation of the knowledge base client using Graphiti."""
    
    def __init__(self):
        self.available = False
        self.graphiti = None
        self._initialize_graphiti()
    
    def _initialize_graphiti(self):
        """Initialize Graphiti connection and configuration."""
        try:
            from graphiti_core.graphiti import Graphiti
            from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
            from graphiti_core.driver.neo4j_driver import Neo4jDriver
            
            # Configuration
            self.uri = os.getenv("NEO4J_URI")
            self.user = os.getenv("NEO4J_USERNAME")
            self.password = os.getenv("NEO4J_PASSWORD")
            # Search across both trajectory groups
            self.group_ids = ["web_trajectories", "web_interaction_logs"]
            self.api_key = os.getenv("OPENAI_API_KEY")
            
            if not all([self.uri, self.user, self.password, self.api_key]):
                logger.warning("⚠️ Missing Graphiti configuration. Some environment variables are not set.")
                return
            
            # Initialize components
            embedder_config = OpenAIEmbedderConfig(
                api_key=self.api_key,
                embedding_model="text-embedding-3-small"
            )
            embedder = OpenAIEmbedder(config=embedder_config)
            neo4j_driver = Neo4jDriver(
                uri=self.uri,
                user=self.user,
                password=self.password
            )
            
            self.graphiti = Graphiti(
                graph_driver=neo4j_driver,
                embedder=embedder
            )
            
            self.available = True
            logger.info("✅ GraphRAG client (Graphiti) initialized successfully")
            
        except ImportError:
            logger.warning("⚠️ Graphiti not available. Install graphiti-core to use trajectory context.")
        except Exception as e:
            logger.error(f"❌ Error initializing GraphRAG client: {e}")
    
    async def is_available(self) -> bool:
        """Check if GraphRAG is available and configured."""
        return self.available and self.graphiti is not None
    
    async def search_trajectories(self, query: str, max_results: int = 3, max_context_length: int = 3000) -> str:
        """Multi-layer search for relevant trajectories using GraphRAG (Graphiti)."""
        if not await self.is_available():
            print("❌ GraphRAG client not available")
            return ""
        
        try:
            print(f"🔍 Starting multi-layer search for query: '{query}'")
            
            # Layer 1: Direct Trajectory Search
            print("📊 Layer 1: Performing direct trajectory search...")
            direct_results = await self._layer1_direct_search(query, 5)
            print(f"✅ Layer 1 found {len(direct_results)} direct matches:")
            for i, result in enumerate(direct_results, 1):
                goal = result.get('goal', 'Unknown')
                print(f"   {i}. {goal}")
            
            # Layer 2: Task Type Search
            print("📊 Layer 2: Performing task type search...")
            task_type_results = await self._layer2_task_type_search(query, 5)
            print(f"✅ Layer 2 found {len(task_type_results)} task type matches:")
            for i, result in enumerate(task_type_results, 1):
                goal = result.get('goal', 'Unknown')
                print(f"   {i}. {goal}")
            
            # Combine and rank results
            print("📊 Combining and ranking results...")
            combined_results = self._combine_and_rank_results(direct_results, task_type_results, max_results)
            print(f"✅ Combined results: {len(combined_results)} total trajectories")
            
            if not combined_results:
                print("ℹ️ No relevant past trajectories found")
                return ""
            
            # Format context
            print("📊 Formatting context...")
            context = self._format_enhanced_context(combined_results, max_context_length)
            
            print(f"✅ Multi-layer search completed successfully")
            return context
            
        except Exception as e:
            print(f"❌ Error in multi-layer search: {e}")
            return ""
    
    async def _layer1_direct_search(self, query: str, max_results: int) -> list:
        """Layer 1: Direct trajectory search using semantic similarity."""
        try:
            # Use Graphiti's search with enhanced configuration
            results = await self.graphiti.search_(
                query=query,
                group_ids=self.group_ids,  # Search across both groups
                config=self._get_enhanced_search_config()
            )
            
            # Filter for trajectory nodes and track their group
            trajectory_nodes = []
            for node in results.nodes:
                if getattr(node, "labels", None) and "Trajectory" in node.labels:
                    # Determine which group this node belongs to
                    group_id = getattr(node, "group_id", "unknown")
                    trajectory_nodes.append((node, group_id))
            
            # Extract trajectory data
            direct_results = []
            for node, group_id in trajectory_nodes[:max_results]:
                trajectory_data = self._extract_trajectory_data(node)
                if trajectory_data:
                    trajectory_data["search_layer"] = "direct"
                    trajectory_data["relevance_score"] = getattr(node, "score", 0.5)
                    trajectory_data["group_id"] = group_id  # Track which group it came from
                    direct_results.append(trajectory_data)
            
            return direct_results
            
        except Exception as e:
            logger.error(f"❌ Error in Layer 1 search: {e}")
            return []
    
    async def _layer2_task_type_search(self, query: str, max_results: int) -> list:
        """Layer 2: Task type search using LLM-derived task type."""
        try:
            # Step 1: Use LLM to derive task type from query
            task_type = await self._derive_task_type_with_llm(query)
            if not task_type:
                logger.info("ℹ️ Could not derive task type from LLM, skipping Layer 2 search")
                return []
            
            logger.info(f"🔍 LLM derived task type: {task_type}")
            
            # Step 2: Search for trajectories with this task type
            task_results = await self._find_trajectories_by_task_type(task_type, max_results)
            
            # Step 3: Format results
            hierarchy_results = []
            for trajectory in task_results:
                trajectory["search_layer"] = "task_type"
                trajectory["derived_task_type"] = task_type
                trajectory["relevance_score"] = 0.8  # High relevance for task type matches
                hierarchy_results.append(trajectory)
            
            logger.info(f"🔍 Found {len(hierarchy_results)} trajectories with task type: {task_type}")
            return hierarchy_results
            
        except Exception as e:
            logger.error(f"❌ Error in Layer 2 search: {e}")
            return []
    
    async def _derive_task_type_with_llm(self, query: str) -> str:
        """Use LLM to derive task type from query."""
        try:
            # Import LLM client
            from graphiti_core.llm_client.openai_client import OpenAIClient
            
            # Initialize LLM client
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("❌ OpenAI API key not found")
                return None
            
            from graphiti_core.llm_client.config import LLMConfig
            llm_config = LLMConfig(api_key=api_key)
            llm_client = OpenAIClient(config=llm_config)
            
            # Create prompt for task type derivation
            prompt = f"""
            Analyze this web task query and derive a concise task type.

            Query: "{query}"

            Examples:
            - "Add a recurring event every Monday in June for a weekly check-in on campaign progress at 10 AM" → "Add Recurring Event"
            - "Delete the task 'Review latest research papers on medical ethics' on June" → "Delete Task"
            - "Share the calendar with a colleague named Alex" → "Share Calendar"
            - "Schedule a team meeting for next week" → "Schedule Meeting"
            
            Return only the task type as a JSON string, nothing else. Keep it concise (around 2-4 words).
            Format: {{"task_type": "your task type here"}}
            """
            
            # Get response from LLM
            from graphiti_core.prompts.models import Message
            
            messages = [Message(role="user", content=prompt)]
            response = await llm_client.generate_response(
                messages=messages,
                max_tokens=50
            )
            
            # Extract task type from response (based on ingest_string.py pattern)
            if isinstance(response, dict) and "content" in response:
                content = response["content"].strip()
                # Try to parse as JSON first
                try:
                    import json
                    json_response = json.loads(content)
                    task_type = json_response.get("task_type", content)
                except json.JSONDecodeError:
                    # Fallback to direct content
                    task_type = content
            else:
                # Fallback for different response formats
                task_type = str(response).strip()
            
            # Clean up the response (remove quotes, extra text, etc.)
            task_type = task_type.replace('"', '').replace("'", "").strip()
            
            # If response is too long, take first few words
            if len(task_type.split()) > 4:
                task_type = " ".join(task_type.split()[:4])
            
            logger.info(f"🔍 LLM derived task type: '{task_type}' from query: '{query}'")
            return task_type
            
        except Exception as e:
            logger.error(f"❌ Error deriving task type with LLM: {e}")
            return None
    
    async def _find_trajectories_by_task_type(self, task_type: str, max_results: int) -> list:
        """Find trajectories that use a specific task type."""
        try:
            # Search for trajectories with this task type
            results = await self.graphiti.search_(
                query=task_type,
                group_ids=self.group_ids,  # Search across both groups
                config=self._get_enhanced_search_config()
            )
            
            # Filter for trajectory nodes and track their group
            trajectory_nodes = []
            for node in results.nodes:
                if getattr(node, "labels", None) and "Trajectory" in node.labels:
                    # Determine which group this node belongs to
                    group_id = getattr(node, "group_id", "unknown")
                    trajectory_nodes.append((node, group_id))
            
            # Extract trajectory data
            trajectories = []
            for node, group_id in trajectory_nodes[:max_results]:
                trajectory_data = self._extract_trajectory_data(node)
                if trajectory_data:
                    trajectory_data["group_id"] = group_id  # Track which group it came from
                    trajectories.append(trajectory_data)
            
            return trajectories
            
        except Exception as e:
            logger.error(f"❌ Error finding trajectories by task type: {e}")
            return []
    
    def _combine_and_rank_results(self, direct_results: list, task_type_results: list, max_results: int) -> list:
        """Combine and rank results from both search layers."""
        try:
            # Combine all results
            all_results = direct_results + task_type_results
            
            # Remove duplicates based on trajectory goal
            seen_goals = set()
            unique_results = []
            
            for result in all_results:
                goal = result.get("goal", "")
                if goal and goal not in seen_goals:
                    seen_goals.add(goal)
                    unique_results.append(result)
            
            # Sort by relevance score
            unique_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            
            return unique_results[:max_results]
            
        except Exception as e:
            logger.error(f"❌ Error combining and ranking results: {e}")
            return direct_results[:max_results] + task_type_results[:max_results]
    
    def _extract_trajectory_data(self, node) -> dict:
        """Extract trajectory data from a Graphiti node."""
        try:
            # Extract basic fields
            goal = getattr(node, "name", "")
            steps = getattr(node, "steps", None)
            codes = getattr(node, "code_executed", None)
            
            # Check attributes dict if not found as top-level
            if steps is None and hasattr(node, "attributes"):
                steps = node.attributes.get("steps")
            if codes is None and hasattr(node, "attributes"):
                codes = node.attributes.get("code_executed")
            
            # Extract additional metadata
            metadata = {}
            if hasattr(node, "attributes"):
                metadata = node.attributes.get("metadata", {})
            
            return {
                "goal": goal,
                "steps": steps or [],
                "codes": codes or [],
                "metadata": metadata,
                "node_uuid": getattr(node, "uuid", "")
            }
            
        except Exception as e:
            logger.error(f"❌ Error extracting trajectory data: {e}")
            return None
    
    def _format_enhanced_context(self, results: list, max_context_length: int) -> str:
        """Format search results into enhanced context."""
        try:
            context_parts = ["Previous trajectories and solution steps that worked:"]
            
            # Combine all results and number them sequentially
            all_results = []
            for result in results:
                all_results.append(result)
            
            # Format all results in a simple numbered list
            for i, result in enumerate(all_results, 1):
                goal = result.get('goal', 'Unknown goal')
                steps = result.get('steps', [])
                codes = result.get('codes', [])
                group_id = result.get("group_id", "unknown")
                
                context_parts.append(f"{i}. Instruction: {goal}")
                context_parts.append(f"Steps: {steps}")
                
                # Include codes for web_trajectories group, skip for interaction logs
                if group_id != "web_interaction_logs" and codes:
                    context_parts.append(f"Codes: {codes}")
                
                context_parts.append("")
            
            context_parts.append("You can use these as reference to determine your next step.")
            full_context = "\n".join(context_parts)
            
            # Truncate if too long
            if len(full_context) > max_context_length:
                logger.warning(f"⚠️ Context length ({len(full_context)}) exceeds limit ({max_context_length}). Truncating...")
                full_context = full_context[:max_context_length] + "\n... [CONTEXT TRUNCATED]"
            
            return full_context
            
        except Exception as e:
            logger.error(f"❌ Error formatting enhanced context: {e}")
            return "=== ERROR FORMATTING CONTEXT ==="
    
    def _get_enhanced_search_config(self):
        """Get enhanced search configuration for Graphiti."""
        try:
            from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
            return NODE_HYBRID_SEARCH_RRF
        except ImportError:
            # Fallback to default search if enhanced config not available
            logger.warning("⚠️ Enhanced search config not available, using default")
            return None
    
    async def add_trajectory(self, trajectory_data: dict) -> bool:
        """Add a trajectory to the GraphRAG knowledge base using Graphiti."""
        if not await self.is_available():
            logger.error("❌ GraphRAG client not available")
            return False
        
        try:
            from graphiti_core import Graphiti
            from graphiti_core.nodes import EpisodeType
            from datetime import datetime, timezone
            from graphRAG.trajectory_entity_types import WEB_TRAJECTORY_ENTITY_TYPES
            
            # Check if trajectory_data contains a path to trajectory folder
            trajectory_path = trajectory_data.get('trajectory_path')
            if trajectory_path:
                # Use the TrajectoryParser from ingest_trajectory.py
                from graphRAG.ingest_trajectory import TrajectoryParser
                
                trajectory_folder = Path(trajectory_path)
                if not trajectory_folder.exists():
                    logger.error(f"❌ Trajectory folder does not exist: {trajectory_path}")
                    return False
                
                # Create parser and combined episode text with error data
                parser = TrajectoryParser()
                episode_text = parser.create_combined_episode_text(trajectory_folder)
                
                # Check if error log exists
                error_log_path = trajectory_folder / "error_log.json"
                has_errors = error_log_path.exists()
                
                # ==================== COMPREHENSIVE LOGGING ====================
                print(f"\n🔍 === DEBUGGING ENTITY EXTRACTION ===")
                print(f"📝 Episode text being sent to LLM:")
                print("=" * 80)
                print(episode_text)
                print("=" * 80)
                print(f"📏 Episode text length: {len(episode_text)} characters")
                print(f"🏷️  Entity types provided: {list(WEB_TRAJECTORY_ENTITY_TYPES.keys())}")
                
                # Add to Graphiti using the new split extraction method
                print(f"\n🚀 Calling graphiti.add_episode_split()...")
                result = await self.graphiti.add_episode_split(
                    name=f"Trajectory: {trajectory_folder.name}",
                    episode_body=episode_text,
                    source=EpisodeType.text,
                    source_description=f"Web trajectory from {trajectory_folder.name}",
                    reference_time=datetime.now(timezone.utc),
                    group_id=self.group_ids[0],  # Use first group for adding trajectories
                    entity_types=WEB_TRAJECTORY_ENTITY_TYPES,  # Now includes Error entity
                    mode="split"  # Use split mode for better accuracy
                )
                
                print(f"✅ add_episode_split() completed")
                print(f"📊 Raw results: {len(result.nodes)} nodes, {len(result.edges)} edges")
                
                # Log detailed entity information
                print(f"\n📋 DETAILED NODE ANALYSIS:")
                entity_names = {}
                for i, node in enumerate(result.nodes):
                    node_name = node.name
                    if node_name in entity_names:
                        entity_names[node_name] += 1
                    else:
                        entity_names[node_name] = 1
                    
                    print(f"  [{i+1}] Name: '{node_name}'")
                    print(f"      Labels: {node.labels}")
                    print(f"      Attributes: {list(node.attributes.keys()) if node.attributes else 'None'}")
                    print(f"      UUID: {node.uuid}")
                    print()
                
                # Check for duplicates
                print(f"🔄 DUPLICATE ANALYSIS:")
                duplicates_found = False
                for name, count in entity_names.items():
                    if count > 1:
                        print(f"  ⚠️  '{name}' appears {count} times")
                        duplicates_found = True
                
                if not duplicates_found:
                    print(f"  ✅ No duplicate entity names found")
                
                print(f"🔗 EDGES ANALYSIS:")
                for i, edge in enumerate(result.edges):
                    print(f"  [{i+1}] {edge.fact}")
                
                print(f"🏁 === END DEBUGGING ===\n")
                
                # Summary (detailed analysis already shown above)
                print(f"✅ SUMMARY: Created {len(result.nodes)} nodes and {len(result.edges)} edges for {trajectory_folder.name}")
                
                logger.info(f"✅ Successfully added trajectory to GraphRAG: {trajectory_folder.name}")
                logger.info(f"📊 Created {len(result.nodes)} nodes and {len(result.edges)} edges")
                return True
                
            else:
                # Fallback to simple EntityNode creation for backward compatibility
                from graphiti_core.nodes import EntityNode
                
                # Extract trajectory information
                goal = trajectory_data.get('goal', '')
                steps = trajectory_data.get('steps', [])
                codes = trajectory_data.get('codes', [])
                metadata = trajectory_data.get('metadata', {})
                
                # Create trajectory node
                trajectory_node = EntityNode(
                    name=goal,
                    group_id=self.group_id,
                    labels=['Trajectory'],
                    summary=f"Trajectory with {len(steps)} steps",
                    attributes={
                        'steps': steps,
                        'code_executed': codes,
                        'metadata': metadata,
                        'created_at': datetime.now(timezone.utc).isoformat()
                    }
                )
                
                # Save the trajectory node
                await trajectory_node.save(self.graphiti.driver)
                
                logger.info(f"✅ Successfully added trajectory to GraphRAG: {goal}")
                return True
            
        except Exception as e:
            logger.error(f"❌ Error adding trajectory to GraphRAG: {e}")
            return False 