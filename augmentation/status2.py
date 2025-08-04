import sys
import os
import json
import base64
from typing import Dict, List, Tuple
from openai import OpenAI
from PIL import Image
from io import BytesIO

# Ensure parent directory is in sys.path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RESULTS_DIR

# OpenAI configuration
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

STATUS2_DIR = os.path.join(RESULTS_DIR, "status_2_inefficient")
MAX_OPTIMIZE = 1  # Set to None for no limit

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

def identify_redundant_steps(
    steps: List[Dict],
    screenshots: List[str],
    original_instruction: str
) -> Dict:
    """Step 1: Use LLM to identify which steps are redundant and should be removed."""
    # Prepare steps as readable text
    steps_text = "\n".join([
        f"Step {i+1}: {step['action']['playwright_code']}" for i, step in enumerate(steps)
    ])
    
    # Encode all screenshots with labels
    screenshot_content = []
    step_numbers = sorted([int(k) for k in {step.split('_')[1].split('.')[0] for step in screenshots if os.path.exists(step)}])
    for i, screenshot_path in enumerate(screenshots):
        if os.path.exists(screenshot_path):
            # Extract step number from filename
            step_num = int(screenshot_path.split('screenshot_')[1].split('.')[0])
            img_b64 = process_image(screenshot_path)
            screenshot_content.extend([
                {
                    "type": "text",
                    "text": f"Screenshot for Step {step_num}:"
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                }
            ])
    
    system_prompt = (
        "You are an augmentation assistant. "
        "You will be given a web automation trajectory consisting of a list of steps taken and two screenshots: "
        "one screenshot taken before the last step, and one showing the final output. You are also given the original 3-level instructions for the task."
        "CONTEXT: This trajectory was flagged as having inefficient execution - it achieved the correct result but with extra/unnecessary steps. "
        "There may be repeated or redundant steps in the sequence that don't contribute to the final goal.\n\n"
        "Your task is to identify redundant step numbers that can be safely removed without affecting the final outcome. "
        "Look for:\n"
        "- Steps that repeat the same action unnecessarily\n"
        "- Steps that cancel or undo previous actions\n"
        "- Actions that don't contribute to achieving the stated goal\n\n"
        "IMPORTANT: The steps you identify will be DELETED from the trajectory data to fix and optimize it.\n\n"
        "Your response MUST be a single valid JSON object with these fields: "
        "'steps_to_remove' (array of step numbers to remove, 1-indexed), "
        "'duplicates_with' (array showing which steps the redundant steps duplicates with). "
        "Do NOT include ```json markers or any other text outside the JSON.\n\n"
        "Example: If steps 1 and 2 are repeated in steps 3 and 4, return: "
        '{"steps_to_remove": [1, 2], "duplicates_with": [3, 4]}'
        "Note: Always delete the EARLIER steps that get repeated later, keep the later ones."
    )
    
    user_content = [
        {
            "type": "text",
            "text": (
                f"Task instruction: {original_instruction}\n\n"
                f"Executed steps:\n{steps_text}\n\n"
                "Identify the redundant step numbers that should be removed:"
            )
        }
    ] + screenshot_content
    
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=0.3,
        max_tokens=200
    )
    
    try:
        # Remove triple backticks and optional 'json' prefix
        raw_content = response.choices[0].message.content
        if not raw_content or raw_content.strip() == "":
            print(f"Empty response from LLM")
            return {"steps_to_remove": [], "duplicates_with": []}
        
        import re
        cleaned = re.sub(r"^```json\s*|^```|```$", "", raw_content.strip(), flags=re.MULTILINE).strip()
        
        if not cleaned:
            print(f"No content after cleaning: '{raw_content}'")
            return {"steps_to_remove": [], "duplicates_with": []}
        
        result = json.loads(cleaned)
        if isinstance(result, dict) and "steps_to_remove" in result:
            return result
        else:
            return {"steps_to_remove": [], "duplicates_with": []}
    except json.JSONDecodeError as e:
        print(f"JSON parsing error in identify_redundant_steps: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        print(f"Cleaned content: '{cleaned}'")
        return {"error": f"JSON decode error: {str(e)}", "raw_response": response.choices[0].message.content}
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        return {"error": str(e), "raw_response": response.choices[0].message.content}

def verify_step_deletion(
    steps: List[Dict],
    steps_to_remove: List[int],
    duplicates_with: List[int],
    traj_path: str,
    original_instruction: str
) -> Dict:
    """Step 2: Verify if it's safe to delete the identified redundant steps."""
    # Prepare steps as readable text
    steps_text = "\n".join([
        f"Step {i+1}: {step['action']['playwright_code']}" for i, step in enumerate(steps)
    ])
    
    # Collect images for steps to delete and their duplicates
    screenshot_content = []
    images_dir = os.path.join(traj_path, "images")
    
    # Add images for steps to remove and their duplicates with labels
    all_steps_to_show = set(steps_to_remove + duplicates_with)
    for step_num in sorted(all_steps_to_show):
        screenshot_path = os.path.join(images_dir, f"screenshot_{step_num:03d}.png")
        if os.path.exists(screenshot_path):
            img_b64 = process_image(screenshot_path)
            # Determine if this step is being removed or if it's the duplicate
            if step_num in steps_to_remove:
                label = f"Screenshot for Step {step_num} (PROPOSED FOR DELETION):"
            else:
                label = f"Screenshot for Step {step_num} (DUPLICATE TARGET):"
            
            screenshot_content.extend([
                {
                    "type": "text",
                    "text": label
                },
                {
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                }
            ])
    
    # Create duplication pairs text
    duplication_info = ""
    if len(steps_to_remove) == len(duplicates_with):
        pairs = []
        for i, (remove_step, duplicate_step) in enumerate(zip(steps_to_remove, duplicates_with)):
            pairs.append(f"Step {remove_step} duplicates Step {duplicate_step}")
        duplication_info = "Identified duplications:\n" + "\n".join(pairs)
    
    system_prompt = (
        "You are a verification assistant. You have been given a list of steps that were identified as redundant and should be deleted. "
        "Your job is to verify if it is safe to delete these steps without affecting the final outcome.\n\n"
        "You will see:\n"
        "1. The full list of steps in the trajectory\n"
        "2. Which steps are marked for deletion and what they duplicate\n"
        "3. Screenshots showing the state at each relevant step\n\n"
        "CONTEXT: These steps were flagged as redundant duplicates. Verify if removing them would break the trajectory or if they are indeed safe to remove.\n\n"
        "Your response MUST be a single valid JSON object with these fields:\n"
        "'safe_to_delete' (boolean: true if safe to delete all identified steps, false if any should be kept),\n"
        "'verified_steps_to_remove' (array of step numbers that are confirmed safe to remove),\n"
        "'reason' (brief explanation of your decision)\n\n"
        "Do NOT include ```json markers or any other text outside the JSON."
    )
    
    user_content = [
        {
            "type": "text",
            "text": (
                f"Task instruction: {original_instruction}\n\n"
                f"Full trajectory steps:\n{steps_text}\n\n"
                f"Steps proposed for deletion: {steps_to_remove}\n"
                f"{duplication_info}\n\n"
                "Please verify if these steps are safe to delete:"
            )
        }
    ] + screenshot_content
    
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=0.1,
        max_tokens=300
    )
    
    try:
        # Remove triple backticks and optional 'json' prefix
        raw_content = response.choices[0].message.content
        if not raw_content or raw_content.strip() == "":
            print(f"Empty response from LLM")
            return {"error": "Empty response", "raw_response": raw_content}
        
        import re
        cleaned = re.sub(r"^```json\s*|^```|```$", "", raw_content.strip(), flags=re.MULTILINE).strip()
        
        if not cleaned:
            print(f"No content after cleaning: '{raw_content}'")
            return {"error": "No content after cleaning", "raw_response": raw_content}
        
        result = json.loads(cleaned)
        return result
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        print(f"Cleaned content: '{cleaned}'")
        return {"error": f"JSON decode error: {str(e)}", "raw_response": response.choices[0].message.content}
    except Exception as e:
        print(f"Error parsing verification response: {e}")
        return {"error": str(e), "raw_response": response.choices[0].message.content}

def optimize_trajectory(trajectory: Dict, steps_to_remove: List[int]) -> Dict:
    """Remove inefficient steps while keeping original file references."""
    if not steps_to_remove:
        return trajectory
    
    # Use the new function that preserves file references
    return update_trajectory_references(trajectory, steps_to_remove)

def update_trajectory_references(trajectory: Dict, steps_to_remove: List[int]) -> Dict:
    """Update trajectory.json to reference the correct axtree and image files without physically moving files."""
    if not steps_to_remove:
        return trajectory
    
    # Get the original step numbers that weren't removed
    original_steps = sorted([int(k) for k in trajectory.keys()])
    remaining_original_steps = [step for step in original_steps if step not in steps_to_remove]
    
    # Create mapping from new step numbers to original step numbers (for file references)
    new_trajectory = {}
    for new_step_idx, original_step_num in enumerate(remaining_original_steps, 1):
        # Get the step data
        step_data = trajectory[str(original_step_num)]
        
        # Update the file references to point to the original file numbers
        # The files keep their original names, but the trajectory references them correctly
        new_trajectory[str(new_step_idx)] = step_data
    
    return new_trajectory

def main():
    print(f"🚀 Starting Status 2 Trajectory Optimization")
    print(f"📂 Looking for trajectories in: {STATUS2_DIR}")
    print(f"⚙️  Processing limit: {MAX_OPTIMIZE if MAX_OPTIMIZE is not None else 'No limit'}")
    
    if not os.path.exists(STATUS2_DIR):
        print(f"❌ No status_2_inefficient directory found at {STATUS2_DIR}")
        return
    
    # Count total trajectories first
    total_trajectories = len([d for d in os.listdir(STATUS2_DIR) if os.path.isdir(os.path.join(STATUS2_DIR, d))])
    print(f"📊 Found {total_trajectories} trajectory directories to process")
    
    count = 0
    optimized_count = 0
    skipped_count = 0
    error_count = 0
    
    for traj_dir in os.listdir(STATUS2_DIR):
        if MAX_OPTIMIZE is not None and count >= MAX_OPTIMIZE:
            print(f"\n🔔 Reached optimization limit of {MAX_OPTIMIZE}.")
            break
            
        traj_path = os.path.join(STATUS2_DIR, traj_dir)
        if not os.path.isdir(traj_path):
            continue
            
        print(f"\n{'='*60}")
        print(f"🔍 Processing [{count+1}/{min(MAX_OPTIMIZE or total_trajectories, total_trajectories)}]: {traj_dir}")
        print(f"📁 Path: {traj_path}")
        
        try:
            # Load trajectory and metadata
            traj_json = os.path.join(traj_path, "trajectory.json")
            meta_json = os.path.join(traj_path, "metadata.json")
            
            print(f"📄 Checking for required files...")
            print(f"   trajectory.json: {'✅' if os.path.exists(traj_json) else '❌'}")
            print(f"   metadata.json: {'✅' if os.path.exists(meta_json) else '❌'}")
            
            if not (os.path.exists(traj_json) and os.path.exists(meta_json)):
                print("⏭️  Skipping: missing trajectory.json or metadata.json")
                skipped_count += 1
                continue
                
            print(f"📖 Loading trajectory and metadata files...")
            with open(traj_json, "r", encoding="utf-8") as f:
                trajectory = json.load(f)
            with open(meta_json, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            steps = list(trajectory.values())
            if not steps:
                print("⏭️  Skipping: no steps found in trajectory")
                skipped_count += 1
                continue
                
            print(f"📊 Trajectory contains {len(steps)} steps")
            
            # Collect all screenshot paths
            print(f"🖼️  Collecting screenshot paths...")
            screenshots = []
            images_dir = os.path.join(traj_path, "images")
            step_numbers = sorted([int(k) for k in trajectory.keys()])
            
            for step_num in step_numbers:
                screenshot_path = os.path.join(images_dir, f"screenshot_{step_num:03d}.png")
                screenshots.append(screenshot_path)
            
            # Add final screenshot
            max_step = max(step_numbers)
            final_screenshot = os.path.join(images_dir, f"screenshot_{max_step + 1:03d}.png")
            screenshots.append(final_screenshot)
            
            # Check screenshot availability
            available_screenshots = sum(1 for s in screenshots if os.path.exists(s))
            print(f"   Found {available_screenshots}/{len(screenshots)} screenshot files")
            
            original_instruction = metadata['task']['instruction'].get('low_level', '')
            print(f"📝 Task instruction: {original_instruction[:100]}{'...' if len(original_instruction) > 100 else ''}")
            
            # Step 1: Identify redundant steps
            print(f"\n🔍 STEP 1: Identifying redundant steps...")
            result = identify_redundant_steps(steps, screenshots, original_instruction)
            
            if "error" in result:
                print(f"❌ Step 1 failed with error: {result['error']}")
                if "raw_response" in result:
                    print(f"📝 LLM raw response: {result['raw_response'][:200]}...")
                error_count += 1
            elif "steps_to_remove" in result and result["steps_to_remove"]:
                steps_to_remove = result["steps_to_remove"]
                duplicates_with = result.get("duplicates_with", [])
                
                print(f"✅ Step 1 completed - Identified {len(steps_to_remove)} redundant steps: {steps_to_remove}")
                if duplicates_with:
                    print(f"🔗 Duplication analysis:")
                    for i, (remove_step, duplicate_step) in enumerate(zip(steps_to_remove, duplicates_with)):
                        print(f"     • Step {remove_step} duplicates Step {duplicate_step}")
                
                # Step 2: Verify deletion safety
                print(f"\n🔍 STEP 2: Verifying safety of deletion...")
                verification = verify_step_deletion(steps, steps_to_remove, duplicates_with, traj_path, original_instruction)
                
                # Check if verification had an error
                if "error" in verification:
                    print(f"❌ Step 2 failed with error: {verification['error']}")
                    if "raw_response" in verification:
                        print(f"📝 LLM raw response: {verification['raw_response'][:200]}...")
                    print("🚫 No changes made due to verification error")
                    error_count += 1
                elif "verified_steps_to_remove" in verification:
                    final_steps_to_remove = verification["verified_steps_to_remove"]
                    is_safe = verification.get("safe_to_delete", False)
                    reason = verification.get("reason", "No reason provided")
                    
                    print(f"✅ Step 2 completed")
                    print(f"🛡️  Safety assessment: {'SAFE' if is_safe else 'UNSAFE'}")
                    print(f"💭 Reasoning: {reason}")
                    print(f"🎯 Final steps approved for removal: {final_steps_to_remove if final_steps_to_remove else 'None'}")
                    
                    if final_steps_to_remove:
                        print(f"\n🔧 STEP 3: Applying optimizations...")
                        
                        # Save backup of original trajectory
                        backup_path = os.path.join(traj_path, "trajectory.original.json")
                        if not os.path.exists(backup_path):
                            print(f"💾 Creating backup: trajectory.original.json")
                            with open(backup_path, "w", encoding="utf-8") as f:
                                json.dump(trajectory, f, indent=2, ensure_ascii=False)
                        else:
                            print(f"📁 Backup already exists: trajectory.original.json")
                        
                        # Optimize trajectory
                        print(f"⚡ Optimizing trajectory structure...")
                        optimized_trajectory = optimize_trajectory(trajectory, final_steps_to_remove)
                        
                        # Save optimized trajectory
                        print(f"💾 Saving optimized trajectory.json...")
                        with open(traj_json, "w", encoding="utf-8") as f:
                            json.dump(optimized_trajectory, f, indent=2, ensure_ascii=False)
                        
                        # Save optimization report
                        optimization_report = {
                            "original_steps": len(trajectory),
                            "optimized_steps": len(optimized_trajectory),
                            "step1_identified": steps_to_remove,
                            "step1_duplicates_with": duplicates_with,
                            "step2_verification": {
                                "safe_to_delete": is_safe,
                                "reason": reason,
                                "verified_steps_to_remove": final_steps_to_remove
                            },
                            "final_removed_steps": final_steps_to_remove
                        }
                        
                        print(f"📊 Saving optimization report...")
                        with open(os.path.join(traj_path, "optimization_report.json"), "w", encoding="utf-8") as f:
                            json.dump(optimization_report, f, indent=2, ensure_ascii=False)
                        
                        print(f"🎉 OPTIMIZATION SUCCESSFUL!")
                        print(f"   📈 Steps: {len(trajectory)} → {len(optimized_trajectory)} (removed {len(trajectory) - len(optimized_trajectory)})")
                        print(f"   🗑️  Deleted steps: {final_steps_to_remove}")
                        optimized_count += 1
                    else:
                        print("🚫 Verification rejected all proposed deletions - no changes made")
                        skipped_count += 1
                else:
                    print("❌ Verification failed - no changes made")
                    error_count += 1
                    
            else:
                print("✅ No redundant steps found, trajectory already optimal")
                skipped_count += 1
                
            count += 1
            
        except Exception as e:
            print(f"💥 ERROR processing {traj_dir}: {e}")
            print(f"   📍 Error details: {type(e).__name__}")
            error_count += 1
            continue
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"🏁 OPTIMIZATION COMPLETE - SUMMARY")
    print(f"{'='*60}")
    print(f"📊 Total processed: {count}")
    print(f"✅ Successfully optimized: {optimized_count}")
    print(f"⏭️  Skipped (no changes needed): {skipped_count}")
    print(f"❌ Errors encountered: {error_count}")
    
    if optimized_count > 0:
        print(f"\n🎉 {optimized_count} trajectories were successfully optimized!")
    if error_count > 0:
        print(f"\n⚠️  {error_count} trajectories had errors and were not processed")
    if skipped_count > 0:
        print(f"\n🔍 {skipped_count} trajectories were already optimal or verification rejected changes")

if __name__ == "__main__":
    main() 