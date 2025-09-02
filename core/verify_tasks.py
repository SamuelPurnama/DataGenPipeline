import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import base64
from typing import Dict, List
from openai import OpenAI
from config import RESULTS_DIR
from PIL import Image
from io import BytesIO

# OpenAI configuration
import os
import dotenv
dotenv.load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Maximum number of trajectories to verify (set to None for all)
MAX_TRAJECTORIES = 1000

def log_token_usage(resp):
    """Prints a detailed breakdown of token usage from OpenAI response."""
    if hasattr(resp, "usage"):
        input_tokens = getattr(resp.usage, "prompt_tokens", None)
        output_tokens = getattr(resp.usage, "completion_tokens", None)
        total_tokens = getattr(resp.usage, "total_tokens", None)
        print("\n📊 Token Usage Report:")
        print(f"📝 Input (Prompt) tokens: {input_tokens}")
        print(f"💬 Output (Completion) tokens: {output_tokens}")
        print(f"🔢 Total tokens charged: {total_tokens}")
        return total_tokens
    else:
        print("⚠️ Token usage info not available from API response.")
        return 0

def load_trajectory(trajectory_path: str) -> Dict:
    """Load trajectory.json file."""
    with open(trajectory_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_metadata(metadata_path: str) -> Dict:
    """Load metadata.json file."""
    with open(metadata_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def process_image(image_path: str) -> str:
    """Process and encode image for GPT."""
    with Image.open(image_path) as img:
        if img.width > 512:
            aspect_ratio = img.height / img.width
            new_height = int(512 * aspect_ratio)
            img = img.resize((512, new_height), Image.LANCZOS)
        
        buffer = BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

def verify_task_completion(
    task: str,
    last_step_screenshot: str,
    final_screenshot: str,
    executed_codes: List[str]
) -> Dict:
    """Use GPT to verify if the task was completed successfully."""
    try:
        # Process and encode the screenshots
        last_step_image = process_image(last_step_screenshot)
        final_image = process_image(final_screenshot)
            
        # Prepare the messages for GPT
        response = client.chat.completions.create(
            model="gpt-4.1",  # Use vision model
            messages=[
                {
                    "role": "system",
                    "content": """You are a task verification assistant to evaluate the quality of synthetic web trajectory data created by an agent. Your job is to analyze the given screenshots and executed actions to determine if the given task was completed successfully. 
                    You should consider:
                    1. The two screenshots, one from before executing the last step and one for the final state of the page.
                    2. If the sequence of actions taken make sense and there are no unimportant extra steps
                    3. If the end result and the steps taken reflects the task.
                    
                    You MUST respond with a valid JSON object containing exactly these fields:
                    - status: integer (1-4) where:
                      1 = Perfect execution: output is correct and steps are efficient
                      2 = Inefficient steps: output is correct but has extra/unnecessary steps (e.g. clicking the same button twice) (for this category, the error is only on the repeated steps, not on the final result)
                      3 = Wrong output, good steps: final result is wrong but the approach/steps were good
                      4 = Complete failure: both output and steps are wrong
                    - analysis: string explaining the status (required for status 2,3,4)

                    Example responses (you must return EXACTLY one of these formats):
                    {"status": 1}
                    {"status": 2, "analysis": "Task completed correctly but had unnecessary steps 2-3 before finding the right approach in step 4"}
                    {"status": 3, "analysis": "The meeting was created at the wrong time (2:00 PM instead of 3:00 PM) but the steps to create it were correct"}
                    {"status": 4, "analysis": "Failed to create the meeting - wrong approach and wrong time"}

                    IMPORTANT: 
                    - Your entire response must be a single valid JSON object. Do not include any other text or explanation outside the JSON.
                    - Be flexible for details that are not explicitly stated in the task, as the agent was given flexibility to assume details if not given.
                    - Ex: If the task doesn't specify the specific hours, only that the event was for the full day tomorrow, it's ok if the task was assigned to a particular time as long as the date is right.
                    """
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""Task: {task}

                    Executed actions:
                {json.dumps(executed_codes, indent=2)}

Please analyze if the task was completed successfully."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{last_step_image}"
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{final_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.7,
            max_tokens=500
        )

        # Log token usage
        tokens_used = log_token_usage(response)

        # Parse the response as JSON
        try:
            result = json.loads(response.choices[0].message.content)
            return {
                "status": result.get("status", 0),
                "analysis": result.get("analysis", "") if result.get("status", 0) in [2, 3, 4] else "",
                "tokens_used": tokens_used
            }
        except json.JSONDecodeError:
            print("Error: GPT response was not valid JSON")
            return {
                "status": 0,
                "analysis": "Error: Invalid response format from GPT",
                "tokens_used": tokens_used
            }
            
    except Exception as e:
        print(f"Error verifying task completion: {str(e)}")
        return {
            "status": 0,
            "analysis": f"Error during verification: {str(e)}",
            "tokens_used": 0
        }

def verify_all_trajectories():
    """Main function to verify all trajectories in the results directory."""
    results = []
    total_tokens = 0
    
    # Get all calendar directoriesx
    calendar_dirs = [d for d in os.listdir(RESULTS_DIR) if os.path.isdir(os.path.join(RESULTS_DIR, d))]
    
    # Limit number of trajectories if MAX_TRAJECTORIES is set
    if MAX_TRAJECTORIES is not None:
        calendar_dirs = calendar_dirs[:MAX_TRAJECTORIES]
        print(f"\n🔍 Verifying {len(calendar_dirs)} trajectories (limited by MAX_TRAJECTORIES={MAX_TRAJECTORIES})")
    
    # Iterate through calendar directories
    for calendar_dir in calendar_dirs:
        dir_path = os.path.join(RESULTS_DIR, calendar_dir)
        trajectory_path = os.path.join(dir_path, 'trajectory.json')
        metadata_path = os.path.join(dir_path, 'metadata.json')
        
        if not (os.path.exists(trajectory_path) and os.path.exists(metadata_path)):
            continue
            
        print(f"\nVerifying trajectory in {calendar_dir}...")
        
        try:
            # Load trajectory and metadata
            trajectory = load_trajectory(trajectory_path)
            metadata = load_metadata(metadata_path)
            
            # Check if trajectory has any steps
            if not trajectory:
                print(f"   ⚠️ Trajectory is empty - no steps recorded")
                results.append({
                    'trajectory': calendar_dir,
                    'task': metadata['task']['instruction']['high_level'],
                    'verification': {
                        'status': 0,
                        'analysis': 'Trajectory is empty - no steps recorded',
                        'tokens_used': 0
                    }
                })
                continue
            
            # Get the last step number
            try:
                last_step_num = max(int(step) for step in trajectory.keys())
            except ValueError:
                print(f"   ⚠️ No valid step numbers found in trajectory")
                results.append({
                    'trajectory': calendar_dir,
                    'task': metadata['task']['instruction']['high_level'],
                    'verification': {
                        'status': 0,
                        'analysis': 'No valid step numbers found in trajectory',
                        'tokens_used': 0
                    }
                })
                continue
            
            # Get the last step screenshot
            last_step_screenshot = os.path.join(dir_path, 'images', f'screenshot_{last_step_num:03d}.png')
            
            # Get the final screenshot
            final_screenshot = os.path.join(dir_path, 'images', f'screenshot_{last_step_num + 1:03d}.png')
            
            # Check if screenshot files exist
            if not os.path.exists(last_step_screenshot):
                print(f"   ⚠️ Last step screenshot not found: {last_step_screenshot}")
                results.append({
                    'trajectory': calendar_dir,
                    'task': metadata['task']['instruction']['high_level'],
                    'verification': {
                        'status': 0,
                        'analysis': f'Last step screenshot not found: screenshot_{last_step_num:03d}.png',
                        'tokens_used': 0
                    }
                })
                continue
                
            if not os.path.exists(final_screenshot):
                print(f"   ⚠️ Final screenshot not found: {final_screenshot}")
                results.append({
                    'trajectory': calendar_dir,
                    'task': metadata['task']['instruction']['high_level'],
                    'verification': {
                        'status': 0,
                        'analysis': f'Final screenshot not found: screenshot_{last_step_num + 1:03d}.png',
                        'tokens_used': 0
                    }
                })
                continue
            
            # Get all executed codes
            executed_codes = [step['action']['playwright_code'] for step in trajectory.values()]
            
            # Verify task completion
            verification = verify_task_completion(
                metadata['task']['instruction']['low_level'],
                last_step_screenshot,
                final_screenshot,
                executed_codes
            )
            
            # Add to total tokens
            total_tokens += verification.get('tokens_used', 0)
            print(f"📊 Current total tokens: {total_tokens}")
            
            results.append({
                'trajectory': calendar_dir,
                'task': metadata['task']['instruction']['high_level'],
                'verification': verification
            })
                
        except Exception as e:
            print(f"Error processing trajectory {calendar_dir}: {str(e)}")
            continue
    
    # Save overall results
    results_data = {
        'results': results,
        'total_tokens': total_tokens
    }
    with open(os.path.join(RESULTS_DIR, 'verification_results.json'), 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Final total tokens used: {total_tokens}")
    return results

def create_status_folders():
    """Create folders for different verification statuses."""
    status_folders = {
        0: os.path.join(RESULTS_DIR, 'status_0_error'),
        1: os.path.join(RESULTS_DIR, 'status_1_perfect'),
        2: os.path.join(RESULTS_DIR, 'status_2_inefficient'),
        3: os.path.join(RESULTS_DIR, 'status_3_wrong_output'),
        4: os.path.join(RESULTS_DIR, 'status_4_complete_failure')
    }
    
    for status, folder_path in status_folders.items():
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"📁 Created folder: {folder_path}")
        else:
            print(f"📁 Folder already exists: {folder_path}")
    
    return status_folders

def move_trajectory_to_status_folder(trajectory_name: str, status: int, status_folders: Dict):
    """Move a trajectory folder to the appropriate status folder."""
    source_path = os.path.join(RESULTS_DIR, trajectory_name)
    target_folder = status_folders.get(status)
    
    if not target_folder:
        print(f"⚠️ No target folder defined for status {status}")
        return False
    
    target_path = os.path.join(target_folder, trajectory_name)
    
    if not os.path.exists(source_path):
        print(f"❌ Source trajectory not found: {source_path}")
        return False
    
    if os.path.exists(target_path):
        print(f"⚠️ Target already exists, skipping: {target_path}")
        return False
    
    try:
        import shutil
        shutil.move(source_path, target_path)
        print(f"✅ Moved {trajectory_name} to status {status} folder")
        return True
    except Exception as e:
        print(f"❌ Error moving {trajectory_name}: {str(e)}")
        return False

def organize_trajectories():
    """Organize trajectories based on verification status."""
    print("🔍 Loading verification results...")
    verification_path = os.path.join(RESULTS_DIR, 'verification_results.json')
    if not os.path.exists(verification_path):
        print("❌ verification_results.json not found!")
        return
    
    with open(verification_path, 'r', encoding='utf-8') as f:
        verification_data = json.load(f)
    
    print("📁 Creating status folders...")
    status_folders = create_status_folders()
    
    # Statistics
    stats = {
        1: 0,  # Perfect execution
        2: 0,  # Inefficient steps
        3: 0,  # Wrong output, good steps
        4: 0,  # Complete failure
        0: 0   # Error
    }
    
    moved_count = 0
    
    print("\n📊 Organizing trajectories...")
    for result in verification_data.get('results', []):
        trajectory_name = result['trajectory']
        status = result['verification']['status']
        task = result['task']
        
        # Update statistics
        stats[status] = stats.get(status, 0) + 1
        
        print(f"\n📋 Trajectory: {trajectory_name}")
        print(f"   Task: {task}")
        print(f"   Status: {status}")
        
        if status in [0, 1, 2, 3, 4]:
            if status in [0, 2, 3, 4]:
                print(f"   Analysis: {result['verification']['analysis']}")
            if move_trajectory_to_status_folder(trajectory_name, status, status_folders):
                moved_count += 1
        else:
            print(f"   Status {status} - keeping in original location")
    
    # Print summary
    print(f"\n📊 Organization Summary:")
    print(f"🚫 Status 0 (Error): {stats[0]} trajectories")
    print(f"✅ Status 1 (Perfect): {stats[1]} trajectories")
    print(f"⚠️ Status 2 (Inefficient): {stats[2]} trajectories")
    print(f"❌ Status 3 (Wrong Output): {stats[3]} trajectories")
    print(f"💥 Status 4 (Complete Failure): {stats[4]} trajectories")
    print(f"📦 Total moved: {moved_count} trajectories")
    
    # Save organization report
    organization_report = {
        'organization_stats': stats,
        'moved_trajectories': moved_count,
        'status_folders': {
            'status_0_error': status_folders[0],
            'status_1_perfect': status_folders[1],
            'status_2_inefficient': status_folders[2],
            'status_3_wrong_output': status_folders[3],
            'status_4_complete_failure': status_folders[4]
        }
    }
    
    report_path = os.path.join(RESULTS_DIR, 'organization_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(organization_report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 Organization report saved to: {report_path}")

def verify_and_organize():
    """Main function to verify all trajectories and then organize them."""
    print("🔍 Starting verification process...")
    results = verify_all_trajectories()
    
    print("\n📁 Starting organization process...")
    organize_trajectories()
    
    return results

if __name__ == "__main__":
    verify_and_organize() 