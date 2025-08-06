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
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
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
    
    def __init__(self, results_path: str = None):
        if results_path is None:
            from config import RESULTS_DIR
            results_path = RESULTS_DIR
        self.results_path = Path(results_path)
    
    def truncate_error_message(self, error_message: str) -> str:
        """Truncate error message at '\nCall log:\n' to prevent it from being too long."""
        if "\nCall log:\n" in error_message:
            return error_message.split("\nCall log:\n")[0]
        return error_message
    
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
        instructions = metadata.get('task', {}).get('instruction', {})
        start_url = metadata.get('start_url', platform_url)
        success = metadata.get('success', False)
        total_steps = metadata.get('total_steps', len(steps))
        runtime_sec = metadata.get('runtime_sec', 0)
        gpt_output = metadata.get('gpt_output', '')
        
        # Create structured episode text (task type will be extracted by Graphiti LLM)
        episode_text = f"""
Web Trajectory Analysis Data:

GOAL: {goal}

PLATFORM_URL: {start_url or platform_url}

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
    
    def process_error_log(self, error_log_path: Path) -> List[Dict]:
        """Extract error information from error_log.json file."""
        if not error_log_path.exists():
            return []
        
        try:
            with open(error_log_path, 'r', encoding='utf-8') as f:
                error_data = json.load(f)
            
            errors = []
            for error in error_data.get("playwright_errors", []):
                # Convert attempted_codes to proper format
                attempted_codes = []
                for attempt in error.get("attempted_codes", []):
                    # Truncate error message if it contains call log
                    error_message = self.truncate_error_message(attempt.get("error_message", ""))
                    attempted_codes.append({
                        "attempt_number": attempt.get("attempt_number"),
                        "code": attempt.get("code"),
                        "error_message": error_message,
                        "description": attempt.get("description")
                    })
                
                error_entity = {
                    "current_goal": error.get("current_goal"),
                    "description": error.get("description"),
                    "thought": error.get("thought"),
                    "successful_code": error.get("successful_playwright_code"),
                    "timestamp": error.get("timestamp"),
                    "step_index": error.get("step_index"),
                    "attempted_codes": attempted_codes
                }
                errors.append(error_entity)
            
            return errors
            
        except Exception as e:
            print(f"Error processing error log {error_log_path}: {e}")
            return []
    
    def create_error_episode_text(self, trajectory_folder: Path) -> str:
        """Create structured episode text from error log data."""
        error_log_path = trajectory_folder / "error_log.json"
        
        if not error_log_path.exists():
            return ""
        
        errors = self.process_error_log(error_log_path)
        
        if not errors:
            return ""
        
        # Create structured episode text for errors
        episode_text = f"""
Error Analysis Data from Trajectory: {trajectory_folder.name}

TOTAL_ERRORS: {len(errors)}

ERROR_DETAILS:
"""
        
        for i, error in enumerate(errors, 1):
            episode_text += f"""
ERROR_{i} (USE THE FIELDS BELOW TO DECLARE THE ERROR ENTITY):
- Step Index: {error.get('step_index', 'Unknown')}
- Current Goal: {error.get('current_goal', 'Unknown')}
- Description: {error.get('description', 'Unknown')}
- Thought: {error.get('thought', 'Unknown')}
- Timestamp: {error.get('timestamp', 'Unknown')}
- Successful Code: {error.get('successful_code', 'None')}
- Attempted Codes: {len(error.get('attempted_codes', []))} attempts

ATTEMPTED_CODES:
"""
            
            for attempt in error.get('attempted_codes', []):
                code = attempt.get('code', 'Unknown')
                error_message = attempt.get('error_message', 'Unknown')
                episode_text += f"""
  Attempt {attempt.get('attempt_number', 'Unknown')}:
  - {code} -> {error_message}
"""
        
        return episode_text.strip()
    
    def create_combined_episode_text(self, trajectory_folder: Path) -> str:
        """Create combined episode text with both trajectory and error data"""
        
        # Get trajectory episode text
        trajectory_text = self.create_trajectory_episode_text(trajectory_folder)
        
        # Get error episode text
        error_text = self.create_error_episode_text(trajectory_folder)
        
        # Combine them
        if error_text:
            combined_text = f"{trajectory_text}\n\n{'='*50}\n\n{error_text}"
        else:
            combined_text = trajectory_text
        
        return combined_text
    
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
        
        episode_text = self.create_combined_episode_text(trajectory_folder)
        print(episode_text)
    
    def ingest_trajectories(self, limit: Optional[int] = None):
        """Ingest all discovered trajectories using KnowledgeBaseClient"""
        
        # Import the high-level function
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.knowledge_base_client import add_trajectory_to_kb
        
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
            
            # Process each trajectory using KnowledgeBaseClient
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
                        print(f"   Goal: {metadata.get('goal', 'Unknown')}")
                        print(f"   Success: {metadata.get('success', 'Unknown')}")
                        print(f"   Total steps: {metadata.get('total_steps', 'Unknown')}")
                    
                    # Check if error log exists
                    error_log_path = trajectory_folder / "error_log.json"
                    has_errors = error_log_path.exists()
                    if has_errors:
                        print(f"🔴 Error log found: {error_log_path.name}")
                    
                    # Use KnowledgeBaseClient to add trajectory
                    trajectory_data = {
                        'trajectory_path': str(trajectory_folder)
                    }
                    
                    print(f"🚀 Calling KnowledgeBaseClient add_trajectory_to_kb()...")
                    success = add_trajectory_to_kb(trajectory_data, kb_type="graphrag")
                    
                    if success:
                        print(f"✅ Successfully processed {trajectory_folder.name}")
                    else:
                        print(f"❌ Failed to process {trajectory_folder.name}")
                    
                except Exception as e:
                    print(f"  ❌ Error processing {trajectory_folder.name}: {e}")
                    continue
            
            print(f"\n🎉 Successfully processed {len(trajectory_folders)} trajectories!")
                
        except Exception as e:
            print(f"❌ Error in trajectory ingestion: {e}")


# ==================== COMMAND LINE FUNCTIONS ====================

def preview_trajectories():
    """Preview trajectory data without ingesting"""
    parser = TrajectoryParser("data/results")
    
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


def ingest_sample_trajectories(count: int = 5):
    """Ingest a sample of trajectories for testing"""
    parser = TrajectoryParser("data/results")
    
    print(f"🧪 Starting sample trajectory ingestion ({count} trajectories)...")
    
    # Ingest limited number of trajectories
    parser.ingest_trajectories(limit=count)
    
    print("✅ Sample trajectory ingestion completed!")


def ingest_all_trajectories():
    """Ingest all trajectories automatically"""
    parser = TrajectoryParser()
    
    print("🚀 Starting automated trajectory ingestion...")
    
    # Discover trajectories
    trajectories = parser.discover_trajectories()
    print(f"📁 Found {len(trajectories)} trajectories to process")
    
    if not trajectories:
        print("❌ No trajectories found!")
        return
    
    # Ingest all trajectories
    parser.ingest_trajectories(limit=None)
    
    print("✅ Trajectory ingestion completed!")


# ==================== MAIN EXECUTION ====================

def main():
    """Main function with command-line interface"""
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "preview":
            preview_trajectories()
        elif mode == "sample":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            ingest_sample_trajectories(count)
        elif mode == "all":
            ingest_all_trajectories()
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