#!/usr/bin/env python3
"""
Interaction Log Data Parser and Graphiti Ingestion

This script parses web interaction log data from the interaction_logs folder and ingests it
into Graphiti using custom entity types for comprehensive knowledge graph construction.

Usage:
  python ingest_interaction_logs.py preview          # Preview interaction logs without ingesting
  python ingest_interaction_logs.py sample 3         # Ingest 3 sample interaction logs
  python ingest_interaction_logs.py all              # Ingest all interaction logs
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


class InteractionLogParser:
    """Parser for extracting and processing web interaction log data"""
    
    def __init__(self, interaction_logs_path: str = "data/interaction_logs"):
        self.interaction_logs_path = Path(interaction_logs_path)
    
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
    
    def parse_step_summary_json(self, step_summary_path: Path) -> Tuple[List[str], List[str], str, str]:
        """Parse stepSummary.json to extract steps, code, goal, and URL"""
        steps = []
        code_executed = []
        goal = ""
        url = ""
        
        try:
            with open(step_summary_path, 'r', encoding='utf-8') as f:
                step_summary_data = json.load(f)
            
            # Extract goal
            goal = step_summary_data.get('goal', '')
            
            # Extract URL
            url = step_summary_data.get('url', '')
            
            # Extract steps (renamed from action_descriptions)
            steps = step_summary_data.get('steps', [])
            
            # Extract playwright codes
            code_executed = step_summary_data.get('playwright_codes', [])
            
            # Format steps with step numbers
            formatted_steps = []
            for i, step in enumerate(steps, 1):
                formatted_steps.append(f"Step {i}: {step}")
            
            # Format playwright codes
            formatted_codes = []
            for i, code in enumerate(code_executed, 1):
                if code.strip() and code != "// navigation action":
                    formatted_codes.append(f"Step {i}: {code}")
                        
        except Exception as e:
            print(f"Error parsing stepSummary.json: {e}")
            
        return formatted_steps, formatted_codes, goal, url
    
    def parse_metadata_json(self, metadata_path: Path) -> Dict[str, Any]:
        """Parse metadata.json to extract interaction log metadata"""
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return metadata
        except Exception as e:
            print(f"Error parsing metadata.json: {e}")
            return {}
    
    def create_interaction_log_episode_text(self, session_folder: Path) -> str:
        """Create structured episode text from interaction log data"""
        
        # Parse trajectory and metadata files
        trajectory_json_path = session_folder / "trajectory.json"
        step_summary_json_path = session_folder / "stepSummary.json"
        metadata_json_path = session_folder / "metadata.json"
        
        metadata = self.parse_metadata_json(metadata_json_path)
        
        # Try to parse stepSummary.json first (preferred format)
        if step_summary_json_path.exists():
            steps, code_executed, goal, platform_url = self.parse_step_summary_json(step_summary_json_path)
        else:
            # Fallback to trajectory.json parsing
            steps, code_executed, platform_url = self.parse_trajectory_json(trajectory_json_path)
            goal = ""
        
        # Extract key information from metadata
        session_id = metadata.get('session_id', 'Unknown Session')
        session_name = metadata.get('session_name', session_folder.name)
        start_time = metadata.get('start_time', 'Unknown')
        end_time = metadata.get('end_time', 'Unknown')
        duration_seconds = metadata.get('duration_seconds', 0)
        total_interactions = metadata.get('total_interactions', len(steps))
        interaction_types = metadata.get('interaction_types', {})
        screenshots_count = metadata.get('screenshots_count', 0)
        
        # Create structured episode text
        episode_text = f"""
Web Interaction Log Analysis Data:

USER_GOAL:
{goal if goal else 'No specific goal recorded'}

SESSION_INFO:
- Session ID: {session_id}
- Session Name: {session_name}
- Start Time: {start_time}
- End Time: {end_time}
- Duration: {duration_seconds:.1f} seconds
- Total Interactions: {total_interactions}
- Screenshots Taken: {screenshots_count}

INTERACTION_TYPES:
{chr(10).join([f"- {action_type}: {count} interactions" for action_type, count in interaction_types.items()]) if interaction_types else 'No interaction types recorded'}

PLATFORM_URL: {platform_url}

DETAILED_STEPS:
{chr(10).join(steps) if steps else 'No detailed steps available'}

CODE_EXECUTED:
{chr(10).join([f"- {code}" for code in code_executed]) if code_executed else 'No code executed'}

EXECUTION_RESULTS:
- Total Steps: {total_interactions}
- Runtime: {duration_seconds:.1f} seconds
- Interaction Types: {', '.join(interaction_types.keys()) if interaction_types else 'None recorded'}
- Session Duration: {duration_seconds:.1f} seconds
- Interaction Count: {total_interactions}

WEB_ELEMENTS_INTERACTED:
{chr(10).join([f"- {step}" for step in steps[:5]]) if steps else 'No elements recorded'}

INTERACTION_LOG_ID: {session_folder.name}
"""
        
        return episode_text.strip()
    
    def discover_interaction_logs(self) -> List[Path]:
        """Discover all interaction log session folders"""
        session_folders = []
        
        if not self.interaction_logs_path.exists():
            print(f"Interaction logs path does not exist: {self.interaction_logs_path}")
            return []
        
        print(f"Scanning interaction logs directory: {self.interaction_logs_path}")
        
        # Iterate through items in interaction_logs folder
        for item in self.interaction_logs_path.iterdir():
            if not item.is_dir() or item.name.startswith('.'):
                continue
                
            # Check if it's a session folder (starts with 'session_')
            if item.name.startswith('session_'):
                metadata_file = item / "metadata.json"
                trajectory_file = item / "trajectory.json"
                step_summary_file = item / "stepSummary.json"
                
                # Check for required files (either trajectory.json or stepSummary.json)
                if (metadata_file.exists() and 
                    (trajectory_file.exists() or step_summary_file.exists())):
                    session_folders.append(item)
                    print(f"  Found interaction log: {item.name}")
                else:
                    print(f"  Skipping {item.name} (missing required files)")
            else:
                # Skip non-session items
                print(f"  Skipping non-session item: {item.name}")
        
        return session_folders
    
    def preview_interaction_log(self, session_folder: Path):
        """Preview what would be extracted from an interaction log"""
        print(f"\n📋 Preview for: {session_folder.name}")
        print("=" * 60)
        
        episode_text = self.create_interaction_log_episode_text(session_folder)
        print(episode_text)
    
    async def ingest_interaction_logs(self, limit: Optional[int] = None):
        """Ingest all discovered interaction logs into Graphiti"""
        
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
            # Discover interaction logs
            session_folders = self.discover_interaction_logs()
            
            if not session_folders:
                print("No interaction log folders found!")
                return
            
            # Apply limit if specified
            if limit:
                session_folders = session_folders[:limit]
                print(f"Limited to first {limit} interaction logs")
            
            print(f"\nProcessing {len(session_folders)} interaction logs...")
            
            # Process each interaction log
            for i, session_folder in enumerate(session_folders, 1):
                try:
                    print(f"\n[{i}/{len(session_folders)}] Processing: {session_folder.name}")
                    
                    # Log source data being processed
                    metadata_file = session_folder / "metadata.json"
                    if metadata_file.exists():
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        print(f"📄 Source metadata:")
                        print(f"   Session ID: {metadata.get('session_id', 'Unknown')}")
                        print(f"   Duration: {metadata.get('duration_seconds', 'Unknown')} seconds")
                        print(f"   Total interactions: {metadata.get('total_interactions', 'Unknown')}")
                        print(f"   Interaction types: {metadata.get('interaction_types', {})}")
                    
                    # Create episode text
                    episode_text = self.create_interaction_log_episode_text(session_folder)
                    
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
                        name=f"Interaction Log: {session_folder.name}",
                        episode_body=episode_text,
                        source=EpisodeType.text,
                        source_description=f"Web interaction log from recorder system ({session_folder.parent.name})",
                        reference_time=datetime.now(timezone.utc),
                        group_id="web_interaction_logs",
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
                    print(f"✅ SUMMARY: Created {len(result.nodes)} nodes and {len(result.edges)} edges for {session_folder.name}")
                    
                except Exception as e:
                    print(f"  ❌ Error processing {session_folder.name}: {e}")
                    continue
            
            print(f"\n🎉 Successfully processed {len(session_folders)} interaction logs!")
                
        finally:
            await graphiti.close()


# ==================== COMMAND LINE FUNCTIONS ====================

async def preview_interaction_logs():
    """Preview interaction log data without ingesting"""
    parser = InteractionLogParser("data/interaction_logs")
    
    print("👀 Previewing interaction log data...")
    
    sessions = parser.discover_interaction_logs()
    
    if not sessions:
        print("❌ No interaction logs found!")
        return
    
    print(f"📁 Found {len(sessions)} interaction logs")
    
    # Preview first 3 interaction logs
    for i, session in enumerate(sessions[:3], 1):
        print(f"\n{'='*60}")
        print(f"Preview {i}/{min(3, len(sessions))}: {session.name}")
        print('='*60)
        parser.preview_interaction_log(session)
    
    if len(sessions) > 3:
        print(f"\n... and {len(sessions) - 3} more interaction logs")


async def ingest_sample_interaction_logs(count: int = 5):
    """Ingest a sample of interaction logs for testing"""
    parser = InteractionLogParser("data/interaction_logs")
    
    print(f"🧪 Starting sample interaction log ingestion ({count} logs)...")
    
    # Ingest limited number of interaction logs
    await parser.ingest_interaction_logs(limit=count)
    
    print("✅ Sample interaction log ingestion completed!")


async def ingest_all_interaction_logs():
    """Ingest all interaction logs automatically"""
    parser = InteractionLogParser()
    
    print("🚀 Starting automated interaction log ingestion...")
    
    # Discover interaction logs
    sessions = parser.discover_interaction_logs()
    print(f"📁 Found {len(sessions)} interaction logs to process")
    
    if not sessions:
        print("❌ No interaction logs found!")
        return
    
    # Ingest all interaction logs
    await parser.ingest_interaction_logs(limit=None)
    
    print("✅ Interaction log ingestion completed!")


# ==================== MAIN EXECUTION ====================

def main():
    """Main function with command-line interface"""
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "preview":
            asyncio.run(preview_interaction_logs())
        elif mode == "sample":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            asyncio.run(ingest_sample_interaction_logs(count))
        elif mode == "all":
            asyncio.run(ingest_all_interaction_logs())
        else:
            print("❌ Invalid mode. Use: preview, sample, or all")
            print_usage()
    else:
        print_usage()


def print_usage():
    """Print usage instructions"""
    print("🎯 Interaction Log Data Parser and Graphiti Ingestion")
    print()
    print("Usage:")
    print("  python ingest_interaction_logs.py preview          # Preview interaction logs without ingesting")
    print("  python ingest_interaction_logs.py sample 3         # Ingest 3 sample interaction logs")
    print("  python ingest_interaction_logs.py all              # Ingest all interaction logs")
    print()
    print("Examples:")
    print("  python ingest_interaction_logs.py preview")
    print("  python ingest_interaction_logs.py sample 5")
    print("  python ingest_interaction_logs.py all")


if __name__ == "__main__":
    main() 