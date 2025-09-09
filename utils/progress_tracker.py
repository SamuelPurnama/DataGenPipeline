"""
Progress tracking utility for trajectory generation pipeline.
Tracks progress of each account and instruction execution in real-time.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from threading import Lock

class ProgressTracker:
    def __init__(self, results_dir: str):
        self.results_dir = results_dir
        self.progress_file = os.path.join(results_dir, "progress_tracking.json")
        self.lock = Lock()  # Thread-safe updates
        
        # Initialize progress tracking
        self.initialize_progress()
    
    def initialize_progress(self):
        """Initialize the progress tracking file."""
        pipeline_run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        initial_progress = {
            "pipeline_run_id": pipeline_run_id,
            "start_time": datetime.now().isoformat() + "Z",
            "total_instructions": 0,
            "accounts": {},
            "overall_progress": {
                "total_completed": 0,
                "total_failed": 0,
                "total_in_progress": 0,
                "total_remaining": 0,
                "overall_completion_percentage": 0.0
            },
            "last_updated": datetime.now().isoformat() + "Z"
        }
        
        with self.lock:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(initial_progress, f, indent=2, ensure_ascii=False)
    
    def setup_accounts(self, accounts: List[Dict], total_instructions: int):
        """Setup account tracking structure."""
        with self.lock:
            # Read current progress
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            
            # Update total instructions
            progress["total_instructions"] = total_instructions
            
            # Setup each account
            for i, account in enumerate(accounts):
                email = account["email"]
                progress["accounts"][email] = {
                    "account_index": i,
                    "start_idx": account["start_idx"],
                    "end_idx": account["end_idx"],
                    "total_assigned": account["end_idx"] - account["start_idx"],
                    "completed_count": 0,
                    "completed_instructions": [],
                    "failed_instructions": [],
                    "in_progress_instruction": None,
                    "progress_summary": {
                        "completed": 0,
                        "failed": 0,
                        "in_progress": 0,
                        "remaining": account["end_idx"] - account["start_idx"],
                        "completion_percentage": 0.0
                    }
                }
            
            # Update overall progress
            progress["overall_progress"]["total_remaining"] = total_instructions
            progress["last_updated"] = datetime.now().isoformat() + "Z"
            
            # Write back
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress, f, indent=2, ensure_ascii=False)
    
    def start_instruction(self, account_email: str, instruction_index: int, augmented_instruction: str, episode_name: str):
        """Mark an instruction as in progress."""
        with self.lock:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            
            if account_email in progress["accounts"]:
                progress["accounts"][account_email]["in_progress_instruction"] = {
                    "instruction_index": instruction_index,
                    "augmented_instruction": augmented_instruction,
                    "start_time": datetime.now().isoformat() + "Z",
                    "current_step": 0,
                    "episode_name": episode_name
                }
                
                # Update progress summary
                progress["accounts"][account_email]["progress_summary"]["in_progress"] = 1
                progress["accounts"][account_email]["progress_summary"]["remaining"] -= 1
                
                # Update overall progress
                progress["overall_progress"]["total_in_progress"] += 1
                progress["overall_progress"]["total_remaining"] -= 1
                
                progress["last_updated"] = datetime.now().isoformat() + "Z"
                
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(progress, f, indent=2, ensure_ascii=False)
    
    def complete_instruction(self, account_email: str, instruction_index: int, augmented_instruction: str, 
                           episode_name: str, success: bool = True, error_message: str = None):
        """Mark an instruction as completed or failed."""
        with self.lock:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            
            if account_email in progress["accounts"]:
                account = progress["accounts"][account_email]
                
                # Remove from in_progress
                if account["in_progress_instruction"]:
                    account["in_progress_instruction"] = None
                    account["progress_summary"]["in_progress"] = 0
                    progress["overall_progress"]["total_in_progress"] -= 1
                
                # Add to completed or failed
                instruction_data = {
                    "instruction_index": instruction_index,
                    "augmented_instruction": augmented_instruction,
                    "episode_name": episode_name
                }
                
                if success:
                    instruction_data["completion_time"] = datetime.now().isoformat() + "Z"
                    instruction_data["success"] = True
                    account["completed_instructions"].append(instruction_data)
                    account["completed_count"] += 1
                    account["progress_summary"]["completed"] += 1
                    progress["overall_progress"]["total_completed"] += 1
                else:
                    instruction_data["failure_time"] = datetime.now().isoformat() + "Z"
                    instruction_data["error_message"] = error_message or "Unknown error"
                    account["failed_instructions"].append(instruction_data)
                    account["progress_summary"]["failed"] += 1
                    progress["overall_progress"]["total_failed"] += 1
                
                # Update completion percentage
                total_assigned = account["total_assigned"]
                completed = account["progress_summary"]["completed"]
                account["progress_summary"]["completion_percentage"] = (completed / total_assigned) * 100
                
                # Update overall completion percentage
                total_instructions = progress["total_instructions"]
                total_completed = progress["overall_progress"]["total_completed"]
                progress["overall_progress"]["overall_completion_percentage"] = (total_completed / total_instructions) * 100
                
                progress["last_updated"] = datetime.now().isoformat() + "Z"
                
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(progress, f, indent=2, ensure_ascii=False)
    
    def update_step(self, account_email: str, current_step: int):
        """Update the current step for an in-progress instruction."""
        with self.lock:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            
            if (account_email in progress["accounts"] and 
                progress["accounts"][account_email]["in_progress_instruction"]):
                
                progress["accounts"][account_email]["in_progress_instruction"]["current_step"] = current_step
                progress["last_updated"] = datetime.now().isoformat() + "Z"
                
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(progress, f, indent=2, ensure_ascii=False)
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of current progress."""
        with self.lock:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    def print_progress_summary(self):
        """Print a formatted progress summary."""
        progress = self.get_progress_summary()
        
        print("\n" + "="*60)
        print("📊 PROGRESS TRACKING SUMMARY")
        print("="*60)
        print(f"🆔 Pipeline Run ID: {progress['pipeline_run_id']}")
        print(f"📈 Overall Progress: {progress['overall_progress']['overall_completion_percentage']:.1f}%")
        print(f"✅ Completed: {progress['overall_progress']['total_completed']}")
        print(f"❌ Failed: {progress['overall_progress']['total_failed']}")
        print(f"🔄 In Progress: {progress['overall_progress']['total_in_progress']}")
        print(f"⏳ Remaining: {progress['overall_progress']['total_remaining']}")
        
        print("\n👤 Account Progress:")
        for email, account in progress["accounts"].items():
            print(f"   📧 {email}:")
            print(f"      ✅ Completed: {account['completed_count']}/{account['total_assigned']} ({account['progress_summary']['completion_percentage']:.1f}%)")
            print(f"      ❌ Failed: {account['progress_summary']['failed']}")
            print(f"      🔄 In Progress: {account['progress_summary']['in_progress']}")
            if account["in_progress_instruction"]:
                current_step = account["in_progress_instruction"]["current_step"]
                print(f"      📝 Current: Step {current_step}")
        
        print(f"\n🕒 Last Updated: {progress['last_updated']}")
        print("="*60)
