import os
import json
import shutil
from typing import List, Dict
from config import RESULTS_DIR

def delete_failed_trajectories() -> Dict[str, List[str]]:
    """
    Delete all failed trajectory directories from the results folder.
    Returns a dictionary with lists of deleted directories by phase.
    """
    deleted = {
        'phase1': [],
        'phase2': []
    }
    
    print(f"🔍 Searching for failed trajectories in: {RESULTS_DIR}")
    
    # Check if directory exists
    if not os.path.exists(RESULTS_DIR):
        print(f"❌ Results directory not found: {RESULTS_DIR}")
        return deleted

    # Get all calendar directories
    calendar_dirs = [d for d in os.listdir(RESULTS_DIR) 
                    if os.path.isdir(os.path.join(RESULTS_DIR, d)) 
                    and d.startswith('calendar_')]
    
    print(f"📁 Found {len(calendar_dirs)} calendar directories")
    
    for calendar_dir in calendar_dirs:
        dir_path = os.path.join(RESULTS_DIR, calendar_dir)
        metadata_path = os.path.join(dir_path, 'metadata.json')
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Check if task failed
                if not metadata.get('success', False):
                    phase = metadata.get('phase', 0)
                    phase_key = f'phase{phase}'
                    
                    # Delete the directory
                    shutil.rmtree(dir_path)
                    deleted[phase_key].append(calendar_dir)
                    print(f"🗑️ Deleted failed trajectory: {calendar_dir} (Phase {phase})")
                    
            except Exception as e:
                print(f"⚠️ Error processing {calendar_dir}: {str(e)}")
    
    # Print summary
    total_deleted = sum(len(dirs) for dirs in deleted.values())
    print(f"\n📊 Summary of deleted trajectories:")
    print(f"Total deleted: {total_deleted}")
    
    for phase, dirs in deleted.items():
        if dirs:
            print(f"\n{phase.upper()}:")
            print(f"Deleted {len(dirs)} directories:")
            for d in dirs:
                print(f"  - {d}")
    
    return deleted

if __name__ == "__main__":
    # Ask for confirmation before proceeding
    print("⚠️ This script will delete all failed trajectory directories.")
    print("This action cannot be undone!")
    response = input("Do you want to continue? (yes/no): ")
    
    if response.lower() == 'yes':
        delete_failed_trajectories()
    else:
        print("Operation cancelled.") 