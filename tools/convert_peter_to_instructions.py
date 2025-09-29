#!/usr/bin/env python3
"""
Convert peter_tasks.json to instructions_phase1.json format
"""

import json
import os
from typing import Dict, List, Any

def convert_peter_task_to_instruction_format(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single peter task to the instructions phase 1 format
    """
    # Extract the instruction text from the high_level field
    instruction_text = task.get("instruction", {}).get("high_level", "")
    
    # Determine the URL based on task type
    url = ""
    if task.get("task_type", "").startswith("united"):
        url = "https://www.united.com"
    elif task.get("task_type", "").startswith("expedia"):
        url = "https://expedia.com"
    elif task.get("task_type", "").startswith("bestwestern"):
        url = "https://bestwestern.com"
    else:
        # Default fallback - try to extract from steps if available
        steps = task.get("steps", [])
        for step in steps:
            if "navigate to" in step.lower() and "http" in step:
                # Extract URL from step like "Navigate to 'https://www.united.com'"
                url = step.split("'")[1] if "'" in step else ""
                break
    
    return {
        "persona": "",
        "url": url,
        "instructions": [instruction_text],
        "augmented_instructions": [instruction_text]
    }

def convert_peter_tasks_to_instructions(input_file: str, output_file: str):
    """
    Convert peter_tasks.json to instructions_phase1.json format
    """
    print(f"Reading peter tasks from: {input_file}")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        peter_tasks = json.load(f)
    
    print(f"Found {len(peter_tasks)} peter tasks")
    
    # Convert each task
    converted_instructions = []
    for i, task in enumerate(peter_tasks):
        try:
            converted_task = convert_peter_task_to_instruction_format(task)
            converted_instructions.append(converted_task)
            
            if (i + 1) % 100 == 0:
                print(f"Converted {i + 1} tasks...")
                
        except Exception as e:
            print(f"Error converting task {i}: {e}")
            continue
    
    print(f"Successfully converted {len(converted_instructions)} tasks")
    
    # Write the converted instructions
    print(f"Writing converted instructions to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(converted_instructions, f, indent=2, ensure_ascii=False)
    
    print("Conversion completed successfully!")

def main():
    # Define file paths
    input_file = "/Users/jovewinston/Documents/DataGenPipeline Complete/DataGenPipeline/peter_tasks.json"
    output_file = "/Users/jovewinston/Documents/DataGenPipeline Complete/DataGenPipeline/data/results/peter_tasks_converted_to_instructions_phase1.json"
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Run conversion
    convert_peter_tasks_to_instructions(input_file, output_file)

if __name__ == "__main__":
    main()
