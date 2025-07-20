#!/usr/bin/env python3
"""
Complete Trajectory Data Parser and Graphiti Ingestion

This script parses web trajectory data from the results folder and ingests it
into Graphiti using custom entity types for comprehensive knowledge graph construction.

Usage:
  python ingest_trajectory.py preview          # Preview trajectories without ingesting
  python ingest_trajectory.py sample 3         # Ingest 3 sample trajectories
  python ingest_trajectory.py all              # Ingest all trajectories
"""

import json
import os
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from dotenv import load_dotenv

# Import our custom entity types
from trajectory_entity_types import WEB_TRAJECTORY_ENTITY_TYPES

# Load environment variables
load_dotenv()


# ==================== CUSTOM ENTITY TYPES ====================
# Entity types are now imported from trajectory_entity_types.py
ENTITY_TYPES = WEB_TRAJECTORY_ENTITY_TYPES


class TrajectoryParser:
    """Parser for extracting and processing web trajectory data"""
    
    def __init__(self, results_path: str = "results"):
        self.results_path = Path(results_path)
    
    def parse_trajectory_json(self, trajectory_path: Path) -> Tuple[List[str], List[str], str]:
        """Parse trajectory.json to extract steps and code"""
        steps = []
        code_executed = []
        platform_url = ""
        
        try:
            with open(trajectory_path, 'r', encoding='utf-8') as f:
                trajectory_data = json.load(f)
            
            # Sort by step number
            sorted_steps = sorted(trajectory_data.items(), key=lambda x: int(x[0]))
            
            for step_num, step_data in sorted_steps:
                if isinstance(step_data, dict):
                    # Extract step description
                    action_desc = step_data.get('action', {}).get('action_description', '')
                    if action_desc:
                        steps.append(f"Step {step_num}: {action_desc}")
                    
                    # Extract playwright code
                    playwright_code = step_data.get('action', {}).get('playwright_code', '')
                    if playwright_code:
                        code_executed.append(playwright_code)
                    
                    # Extract platform URL from first step
                    if step_num == "1" and not platform_url:
                        other_obs = step_data.get('other_obs', {})
                        platform_url = other_obs.get('url', '')
                        
        except Exception as e:
            print(f"Error parsing trajectory.json: {e}")
            
        return steps, code_executed, platform_url
    
    def parse_metadata_json(self, metadata_path: Path) -> Dict[str, Any]:
        """Parse metadata.json to extract trajectory metadata"""
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return metadata
        except Exception as e:
            print(f"Error parsing metadata.json: {e}")
            return {}
    
    def create_trajectory_episode_text(self, trajectory_folder: Path) -> str:
        """Create structured episode text from trajectory data"""
        
        # Parse trajectory and metadata files
        trajectory_json_path = trajectory_folder / "trajectory.json"
        metadata_json_path = trajectory_folder / "metadata.json"
        
        metadata = self.parse_metadata_json(metadata_json_path)
        steps, code_executed, platform_url = self.parse_trajectory_json(trajectory_json_path)
        
        # Extract key information from metadata
        goal = metadata.get('goal', 'Unknown Goal')
        task_type = metadata.get('task', {}).get('task_type', 'unknown')
        instructions = metadata.get('task', {}).get('instruction', {})
        start_url = metadata.get('start_url', platform_url)
        success = metadata.get('success', False)
        total_steps = metadata.get('total_steps', len(steps))
        runtime_sec = metadata.get('runtime_sec', 0)
        gpt_output = metadata.get('gpt_output', '')
        
        # Format task type
        task_type_formatted = task_type.replace('_', ' ').title()
        
        # Create structured episode text
        episode_text = f"""
Web Trajectory Analysis Data:

GOAL: {goal}

PLATFORM_URL: {start_url or platform_url}

TASK_TYPE: {task_type_formatted}

DETAILED_STEPS:
{chr(10).join(steps) if steps else 'No detailed steps available'}

CODE_EXECUTED:
{chr(10).join([f"- {code}" for code in code_executed]) if code_executed else 'No code executed'}

EXECUTION_RESULTS:
- Success Status: {'Completed successfully' if success else 'Failed or incomplete'}
- Total Steps: {total_steps}
- Runtime: {runtime_sec:.1f} seconds
- Final Output: {gpt_output or 'No output recorded'}

TRAJECTORY_ID: {trajectory_folder.name}
"""
        
        return episode_text.strip()
    
    def discover_trajectories(self) -> List[Path]:
        """Discover all trajectory folders directly in results directory"""
        trajectory_folders = []
        
        if not self.results_path.exists():
            print(f"Results path does not exist: {self.results_path}")
            return []
        
        print(f"Scanning results directory: {self.results_path}")
        
        # Iterate through items in results folder
        for item in self.results_path.iterdir():
            if not item.is_dir() or item.name.startswith('.'):
                continue
                
            # Check if it's a trajectory folder directly in results
            if item.name.startswith('calendar_'):
                metadata_file = item / "metadata.json"
                trajectory_file = item / "trajectory.json"
                
                if metadata_file.exists() and trajectory_file.exists():
                    trajectory_folders.append(item)
                    print(f"  Found trajectory: {item.name}")
                else:
                    print(f"  Skipping {item.name} (missing required files)")
            else:
                # Skip status folders and other non-trajectory items
                print(f"  Skipping non-trajectory item: {item.name}")
        
        return trajectory_folders
    
    def preview_trajectory(self, trajectory_folder: Path):
        """Preview what would be extracted from a trajectory"""
        print(f"\n📋 Preview for: {trajectory_folder.name}")
        print("=" * 60)
        
        episode_text = self.create_trajectory_episode_text(trajectory_folder)
        print(episode_text)
    
    async def ingest_trajectories(self, limit: Optional[int] = None):
        """Ingest all discovered trajectories into Graphiti"""
        
        # Initialize Graphiti
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USERNAME")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        
        if not all([neo4j_uri, neo4j_user, neo4j_password]):
            print("\n❌ Missing Neo4j environment variables!")
            print("Please create a .env file in the pipeline_2 directory with:")
            print("NEO4J_URI=your-neo4j-uri")
            print("NEO4J_USER=neo4j") 
            print("NEO4J_PASSWORD=your-password")
            raise ValueError("Missing required Neo4j environment variables")
        
        print("Initializing Graphiti...")
        graphiti = Graphiti(neo4j_uri, neo4j_user, neo4j_password)
        await graphiti.build_indices_and_constraints()
        
        try:
            # Discover trajectories
            trajectory_folders = self.discover_trajectories()
            
            if not trajectory_folders:
                print("No trajectory folders found!")
                return
            
            # Apply limit if specified
            if limit:
                trajectory_folders = trajectory_folders[:limit]
                print(f"Limited to first {limit} trajectories")
            
            print(f"\nProcessing {len(trajectory_folders)} trajectories...")
            
            # Process each trajectory
            for i, trajectory_folder in enumerate(trajectory_folders, 1):
                try:
                    print(f"\n[{i}/{len(trajectory_folders)}] Processing: {trajectory_folder.name}")
                    
                    # Log source data being processed
                    metadata_file = trajectory_folder / "metadata.json"
                    if metadata_file.exists():
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        print(f"📄 Source metadata:")
                        print(f"   Goal: {metadata.get('goal', 'Unknown')}")
                        print(f"   Task type: {metadata.get('task', {}).get('task_type', 'Unknown')}")
                        print(f"   Success: {metadata.get('success', 'Unknown')}")
                        print(f"   Total steps: {metadata.get('total_steps', 'Unknown')}")
                    
                    # Create episode text
                    episode_text = self.create_trajectory_episode_text(trajectory_folder)
                    
                    # ==================== COMPREHENSIVE LOGGING ====================
                    print(f"\n🔍 === DEBUGGING ENTITY EXTRACTION ===")
                    print(f"📝 Episode text being sent to LLM:")
                    print("=" * 80)
                    print(episode_text)
                    print("=" * 80)
                    print(f"📏 Episode text length: {len(episode_text)} characters")
                    print(f"🏷️  Entity types provided: {list(ENTITY_TYPES.keys())}")
                    
                    # Add to Graphiti with custom entity types
                    print(f"\n🚀 Calling graphiti.add_episode()...")
                    result = await graphiti.add_episode(
                        name=f"Trajectory: {trajectory_folder.name}",
                        episode_body=episode_text,
                        source=EpisodeType.text,
                        source_description=f"Web trajectory from results folder ({trajectory_folder.parent.name})",
                        reference_time=datetime.now(timezone.utc),
                        group_id="web_trajectories",
                        entity_types=ENTITY_TYPES  # Use our custom entity types
                    )
                    
                    print(f"✅ add_episode() completed")
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
                    
                except Exception as e:
                    print(f"  ❌ Error processing {trajectory_folder.name}: {e}")
                    continue
            
            print(f"\n🎉 Successfully processed {len(trajectory_folders)} trajectories!")
                
        finally:
            await graphiti.close()


# ==================== COMMAND LINE FUNCTIONS ====================

async def preview_trajectories():
    """Preview trajectory data without ingesting"""
    parser = TrajectoryParser("results")
    
    print("👀 Previewing trajectory data...")
    
    trajectories = parser.discover_trajectories()
    
    if not trajectories:
        print("❌ No trajectories found!")
        return
    
    print(f"📁 Found {len(trajectories)} trajectories")
    
    # Preview first 3 trajectories
    for i, trajectory in enumerate(trajectories[:3], 1):
        print(f"\n{'='*60}")
        print(f"Preview {i}/{min(3, len(trajectories))}: {trajectory.name}")
        print('='*60)
        parser.preview_trajectory(trajectory)
    
    if len(trajectories) > 3:
        print(f"\n... and {len(trajectories) - 3} more trajectories")


async def ingest_sample_trajectories(count: int = 5):
    """Ingest a sample of trajectories for testing"""
    parser = TrajectoryParser("results")
    
    print(f"🧪 Starting sample trajectory ingestion ({count} trajectories)...")
    
    # Ingest limited number of trajectories
    await parser.ingest_trajectories(limit=count)
    
    print("✅ Sample trajectory ingestion completed!")


async def ingest_all_trajectories():
    """Ingest all trajectories automatically"""
    parser = TrajectoryParser("results")
    
    print("🚀 Starting automated trajectory ingestion...")
    
    # Discover trajectories
    trajectories = parser.discover_trajectories()
    print(f"📁 Found {len(trajectories)} trajectories to process")
    
    if not trajectories:
        print("❌ No trajectories found!")
        return
    
    # Ingest all trajectories
    await parser.ingest_trajectories(limit=None)
    
    print("✅ Trajectory ingestion completed!")


# ==================== MAIN EXECUTION ====================

def main():
    """Main function with command-line interface"""
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "preview":
            asyncio.run(preview_trajectories())
        elif mode == "sample":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            asyncio.run(ingest_sample_trajectories(count))
        elif mode == "all":
            asyncio.run(ingest_all_trajectories())
        else:
            print("❌ Invalid mode. Use: preview, sample, or all")
            print_usage()
    else:
        print_usage()


def print_usage():
    """Print usage instructions"""
    print("🎯 Trajectory Data Parser and Graphiti Ingestion")
    print()
    print("Usage:")
    print("  python ingest_trajectory.py preview          # Preview trajectories without ingesting")
    print("  python ingest_trajectory.py sample 3         # Ingest 3 sample trajectories")
    print("  python ingest_trajectory.py all              # Ingest all trajectories")
    print()
    print("Examples:")
    print("  python ingest_trajectory.py preview")
    print("  python ingest_trajectory.py sample 5")
    print("  python ingest_trajectory.py all")


if __name__ == "__main__":
    main() 