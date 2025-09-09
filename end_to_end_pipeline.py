#!/usr/bin/env python3
"""
DataGen Pipeline Runner

This script runs the complete DataGen pipeline with configurable steps:
1. Generate Instructions (pipeline_instruction.py)
2. Generate Trajectories (generate_trajectory.py) 
3. Verify Tasks (verify_tasks.py)

Configure which steps to run by modifying the settings below.
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# All configuration is now imported from config.py

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Import the main functions from all pipeline components
from core.pipeline_instruction import main as generate_instructions
from core.generate_trajectory import main as generate_trajectories
from core.verify_tasks import verify_and_organize

# Import all configuration from config.py
from config import (
    # Pipeline control settings
    ENABLE_INSTRUCTION_GENERATION, ENABLE_TRAJECTORY_GENERATION, ENABLE_TASK_VERIFICATION,
    SKIP_CONFIRMATION, VERBOSE_OUTPUT,
    # Trajectory generation parameters
    PHASE, MAX_RETRIES, MAX_STEPS, ACTION_TIMEOUT, MODE, MAX_CONTEXT_LENGTH, KNOWLEDGE_BASE_TYPE, SEARCH_CONTEXT,
    AUTO_TRAJECTORY_PROCESSING, MAX_INSTRUCTIONS_TO_PROCESS,
    # Instruction generation parameters
    PERSONAHUB_DATA_PATH, SCREENSHOT_PATH,
    # Project configuration
    ACCOUNTS, TOTAL_PERSONAS, PHASE1_INSTRUCTIONS_PER_PERSONA, PHASE2_INSTRUCTIONS_PER_PERSONA, URL,
    RESULTS_DIR, BROWSER_SESSIONS_DIR, AUTO_INDEXING, NUM_ACCOUNTS_TO_USE
)


def setup_environment():
    """Setup the environment and check for required configurations."""
    print("🔧 Setting up environment...")
    
    # Check for required environment variables
    required_env_vars = ["OPENAI_API_KEY", "CHROME_EXECUTABLE_PATH"]
    missing_vars = []
    
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file or environment.")
        return False
    
    # Ensure required directories exist
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)
    
    print("✅ Environment setup complete!")
    return True


def print_configuration():
    """Print current configuration settings."""
    print("\n📋 Current Configuration:")
    print(f"   🌐 Target URL: {URL}")
    print(f"   📊 Current Phase: {PHASE}")
    print(f"   👥 Number of accounts: {len(ACCOUNTS)}")
    print(f"   🎭 Personas total: {TOTAL_PERSONAS}")
    print(f"   📝 Phase 1 instructions per persona: {PHASE1_INSTRUCTIONS_PER_PERSONA}")
    print(f"   📝 Phase 2 instructions per persona: {PHASE2_INSTRUCTIONS_PER_PERSONA}")
    
    print("\n🎯 Trajectory Generation Settings:")
    print(f"   🔄 Max Retries: {MAX_RETRIES}")
    print(f"   📏 Max Steps: {MAX_STEPS}")
    print(f"   ⏱️ Action Timeout: {ACTION_TIMEOUT}ms")
    print(f"   🤖 Mode: {'Interactive' if MODE == 1 else 'Automatic'}")
    print(f"   📚 Max Context Length: {MAX_CONTEXT_LENGTH}")
    print(f"   🧠 Knowledge Base: {KNOWLEDGE_BASE_TYPE}")
    print(f"   🔍 Search Context: {'Enabled' if SEARCH_CONTEXT else 'Disabled'}")
    print(f"   📊 Auto Processing: {'All Instructions' if AUTO_TRAJECTORY_PROCESSING else f'Max {MAX_INSTRUCTIONS_TO_PROCESS} Instructions'}")
    
    print("\n👤 Active Accounts:")
    for i, account in enumerate(ACCOUNTS, 1):
        print(f"   {i}. {account['email']} (range: {account['start_idx']}-{account['end_idx']})")


def run_instruction_generation():
    """Run the instruction generation pipeline."""
    print("\n" + "="*60)
    print("📝 STEP 1: GENERATING INSTRUCTIONS")
    print("="*60)
    
    try:
        # Set the global variables in the pipeline_instruction module
        import core.pipeline_instruction as pi
        pi.PHASE = PHASE
        pi.PERSONAHUB_DATA_PATH = PERSONAHUB_DATA_PATH
        pi.SCREENSHOT_PATH = SCREENSHOT_PATH
        
        generate_instructions()
        print("\n✅ Instruction generation completed successfully!")
        return True
        
    except KeyboardInterrupt:
        print("\n⚠️ Instruction generation interrupted by user.")
        return False
        
    except Exception as e:
        print(f"\n❌ Error during instruction generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_trajectory_generation():
    """Run the trajectory generation pipeline."""
    print("\n" + "="*60)
    print("🎯 STEP 2: GENERATING TRAJECTORIES")
    print("="*60)
    
    try:
        # Set the global variables in the generate_trajectory module
        import core.generate_trajectory as gt
        gt.PHASE = PHASE
        gt.MAX_RETRIES = MAX_RETRIES
        gt.MAX_STEPS = MAX_STEPS
        gt.ACTION_TIMEOUT = ACTION_TIMEOUT
        gt.MODE = MODE
        gt.MAX_CONTEXT_LENGTH = MAX_CONTEXT_LENGTH
        gt.KNOWLEDGE_BASE_TYPE = KNOWLEDGE_BASE_TYPE
        gt.SEARCH_CONTEXT = SEARCH_CONTEXT
        
        generate_trajectories()
        print("\n✅ Trajectory generation completed successfully!")
        return True
        
    except KeyboardInterrupt:
        print("\n⚠️ Trajectory generation interrupted by user.")
        return False
        
    except Exception as e:
        print(f"\n❌ Error during trajectory generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_verify_tasks():
    """Run the task verification and organization pipeline."""
    print("\n" + "="*60)
    print("🔍 STEP 3: VERIFYING TASKS")
    print("="*60)
    
    try:
        results = verify_and_organize()
        print("\n✅ Task verification completed successfully!")
        return True
        
    except KeyboardInterrupt:
        print("\n⚠️ Task verification interrupted by user.")
        return False
        
    except Exception as e:
        print(f"\n❌ Error during task verification: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def show_pipeline_configuration():
    """Show which pipeline steps are enabled."""
    print("\n🔧 Pipeline Configuration:")
    print(f"   📝 Instruction Generation: {'✅ ENABLED' if ENABLE_INSTRUCTION_GENERATION else '❌ DISABLED'}")
    print(f"   🎯 Trajectory Generation: {'✅ ENABLED' if ENABLE_TRAJECTORY_GENERATION else '❌ DISABLED'}")
    print(f"   🔍 Task Verification: {'✅ ENABLED' if ENABLE_TASK_VERIFICATION else '❌ DISABLED'}")
    print(f"   ⚡ Skip Confirmation: {'✅ YES' if SKIP_CONFIRMATION else '❌ NO'}")
    print(f"   📊 Verbose Output: {'✅ YES' if VERBOSE_OUTPUT else '❌ NO'}")


def get_pipeline_description():
    """Get a description of what will be run based on enabled steps."""
    steps = []
    if ENABLE_INSTRUCTION_GENERATION:
        steps.append("instructions")
    if ENABLE_TRAJECTORY_GENERATION:
        steps.append("trajectories")
    if ENABLE_TASK_VERIFICATION:
        steps.append("verification")
    
    if not steps:
        return "nothing (all steps disabled)"
    elif len(steps) == 1:
        return steps[0]
    elif len(steps) == 2:
        return f"{steps[0]} and {steps[1]}"
    else:
        return f"{', '.join(steps[:-1])}, and {steps[-1]}"


def main():
    """Main function."""
    print("🚀 DataGen Pipeline Runner")
    print("=" * 50)
    
    # Show pipeline configuration
    show_pipeline_configuration()
    
    # Setup environment
    if not setup_environment():
        sys.exit(1)
    
    # Show project configuration
    print_configuration()
    
    # Check if any steps are enabled
    if not any([ENABLE_INSTRUCTION_GENERATION, ENABLE_TRAJECTORY_GENERATION, ENABLE_TASK_VERIFICATION]):
        print("\n❌ All pipeline steps are disabled! Please enable at least one step in the configuration.")
        sys.exit(1)
    
    # Confirm before running (unless skipped)
    if not SKIP_CONFIRMATION:
        pipeline_desc = get_pipeline_description()
        response = input(f"\n❓ Do you want to proceed with {pipeline_desc}? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("❌ Operation cancelled.")
            return
    
    # Run the pipeline steps
    print(f"\n🚀 Starting pipeline ({get_pipeline_description()})...")
    
    # Step 1: Generate instructions
    if ENABLE_INSTRUCTION_GENERATION:
        success = run_instruction_generation()
        if not success:
            print("\n❌ Pipeline failed at instruction generation step.")
            sys.exit(1)
    
    # Step 2: Generate trajectories
    if ENABLE_TRAJECTORY_GENERATION:
        success = run_trajectory_generation()
        if not success:
            print("\n❌ Pipeline failed at trajectory generation step.")
            sys.exit(1)
    
    # Step 3: Verify tasks
    if ENABLE_TASK_VERIFICATION:
        success = run_verify_tasks()
        if not success:
            print("\n❌ Pipeline failed at task verification step.")
            sys.exit(1)
    
    # Success!
    print("\n" + "="*60)
    print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
    print("="*60)
    print("📁 Check the 'data/results' directory for generated trajectories")
    print("📁 Check the 'data/browser_sessions' directory for browser data")
    if ENABLE_TASK_VERIFICATION:
        print("🔍 Check verification results and organized trajectories")


if __name__ == "__main__":
    main()
