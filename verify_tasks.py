import os
import json
import base64
from typing import Dict, List
from openai import OpenAI
from config import RESULTS_DIR
from PIL import Image
from io import BytesIO

# OpenAI configuration
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Maximum number of trajectories to verify (set to None for all)
MAX_TRAJECTORIES = 20

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
            model="gpt-4o",  # Use vision model
            messages=[
                {
                    "role": "system",
                    "content": """You are a task verification assistant. Your job is to analyze screenshots and executed actions to determine if the given task was completed successfully. 
                    Consider:
                    1. The the screenshots
                    2. If the sequence of actions taken make sense and there are no unimportant extra steps
                    3. Whether the task requirements were met
                    
                    You MUST respond with a valid JSON object containing exactly these fields:
                    - status: integer (1-4) where:
                      1 = Perfect execution: output is correct and steps are efficient
                      2 = Correct but inefficient: output is correct but has extra/unnecessary steps
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
                    - Do not be too strict with the success judgment, be flexible for details that are not explicitly stated in the task.
                    - Ex: If the task doesn't specify the specific hours, only that the event was for the full day tomorrow, it's ok if the task was assigned to a particular time as long as the date is right.
                    - Be flexible about the type of action (task/reminder/event) as long as the core task is completed correctly.
                    - NEVER assume or verify details that are not explicitly mentioned in the task:
                      * If day of week is not specified, don't check or mention it - the day of week doesn't matter as long as the date is correct
                      * If year is not specified, don't check or mention it
                      * If time is not specified, don't check or mention it
                      * If location is not specified, don't check or mention it
                      * If attendees are not specified, don't check or mention them
                    - For dates: ONLY verify the month and day if specified. The day of week and year should be ignored unless explicitly required."""
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
    
    # Get all calendar directories
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
            
            # Get the last step number
            last_step_num = max(int(step) for step in trajectory.keys())
            
            # Get the last step screenshot
            last_step_screenshot = os.path.join(dir_path, 'images', f'screenshot_{last_step_num:03d}.png')
            
            # Get the final screenshot
            final_screenshot = os.path.join(dir_path, 'images', f'screenshot_{last_step_num + 1:03d}.png')
            
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

if __name__ == "__main__":
    verify_all_trajectories() 