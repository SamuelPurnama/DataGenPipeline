import sys
import os
import json
import base64
from typing import Dict, List
from openai import OpenAI
from PIL import Image
from io import BytesIO

# Load environment variables from .env file
import dotenv
dotenv.load_dotenv()

# Ensure parent directory is in sys.path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RESULTS_DIR

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
STATUS3_DIR = os.path.join(RESULTS_DIR, "status_3_wrong_output")

MAX_AUGMENT = None # Set to None for no limit

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

def augment_instructions(
    steps: List[Dict],
    last_img_path: str,
    final_img_path: str,
    original_high: str,
    original_mid: str,
    original_low: str,
) -> Dict:
    """Feed steps and images to LLM, ask it to rewrite all instruction levels and goal."""
    steps_text = "\n".join([
        f"Step {i+1}: {step['action']['playwright_code']}" for i, step in enumerate(steps)
    ])
    last_img_b64 = process_image(last_img_path)
    final_img_b64 = process_image(final_img_path)
    system_prompt = (
        "You are an augmentation assistant. You will be given a web automation trajectory consisting of a list of steps take and two screenshots: "
        "one screenshot taken before the last step, and one showing the final output. You are also given the original 3-level instructions for the task."
        "There may be a mismatch between the provided instructions and what was actually done in the steps and output.\n\n"
        "Your first task is to analyze the steps and screenshots and determine if the instructions accurately describe what was actually done. "
        "If the instructions do not match the actions and output, rewrite them so that they accurately reflect the observed behavior and result.\n\n"
        "IMPORTANT: Your response MUST be a single valid JSON object, and MUST NOT be wrapped in triple backticks, code blocks, or any markdown formatting. "
        "Do NOT include ```json or any other code block markers. "
        "Do NOT include any explanation or text outside the JSON object.\n\n"
        "Please provide your output as a valid JSON object with exactly these fields: "
        "'high_level' (a user-friendly instruction for the overall task that was actually completed), "
        "'mid_level' (a concise summary of the main goal achieved), "
        "'low_level' (a detailed step-by-step instruction that would lead to the same actions and result), "
        "Example:\n"
        "  high_level: \"Add my music workshop to my calendar on June 10th at 3 PM\"\n"
        "  mid_level: \"Create an event titled 'Music Workshop' on June 10th at 3 PM.\"\n"
        "  low_level: \"Click the create button and an create an event titled 'Music Workshop' on June 10th, 2025 from 3 PM to 4 PM..\"\n\n"
        "and 'explanation' (provide a structured explanation with this exact format):\n"
        "  CHANGED: [What specific instruction was changed] → [What it was changed to]\n"
        "  WHY: [Brief reason why the change was necessary based on the observed actions/output]\n\n"
        "If the original instructions already match the actions and output, you may return them unchanged, but always include an explanation.\n\n"
        "Do not include any other text outside the JSON."
    )
    user_content = [
        {
            "type": "text",
            "text": (
                f"Original high_level: {original_high}\n"
                f"Original mid_level: {original_mid}\n"
                f"Original low_level: {original_low}\n"
                f"\nExecuted steps:\n{steps_text}\n\n"
                "Please rewrite the goal and all instruction levels to match what was actually done."
            )
        },
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{last_img_b64}"}},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{final_img_b64}"}},
    ]
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=0.7,
        max_tokens=1000
    )
    try:
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        return {"error": str(e), "raw_response": response.choices[0].message.content}

def main():
    if not os.path.exists(STATUS3_DIR):
        print(f"No status_3_wrong_output directory found at {STATUS3_DIR}")
        return
    count = 0
    for traj_dir in os.listdir(STATUS3_DIR):
        if MAX_AUGMENT is not None and count >= MAX_AUGMENT:
            print(f"\n🔔 Reached augmentation limit of {MAX_AUGMENT}.")
            break
        traj_path = os.path.join(STATUS3_DIR, traj_dir)
        if not os.path.isdir(traj_path):
            continue
        print(f"\n🔍 Augmenting: {traj_dir}")
        try:
            traj_json = os.path.join(traj_path, "trajectory.json")
            meta_json = os.path.join(traj_path, "metadata.json")
            if not (os.path.exists(traj_json) and os.path.exists(meta_json)):
                print("  Skipping: missing trajectory.json or metadata.json")
                continue
            with open(traj_json, "r", encoding="utf-8") as f:
                trajectory = json.load(f)
            with open(meta_json, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            steps = list(trajectory.values())
            if not steps:
                print("  Skipping: no steps found")
                continue
            last_step_num = max(int(k) for k in trajectory.keys())
            last_img_path = os.path.join(traj_path, "images", f"screenshot_{last_step_num:03d}.png")
            final_img_path = os.path.join(traj_path, "images", f"screenshot_{last_step_num+1:03d}.png")
            if not (os.path.exists(last_img_path) and os.path.exists(final_img_path)):
                print("  Skipping: missing screenshots")
                continue
            instr = metadata['task']['instruction']
            original_high = instr.get('high_level', '')
            original_mid = instr.get('mid_level', '')
            original_low = instr.get('low_level', '')
            # Augment
            result = augment_instructions(
                steps, last_img_path, final_img_path,
                original_high, original_mid, original_low
            )
            print(f"  📝 Explanation: {result.get('explanation', 'No explanation provided')}")
            # Update metadata fields
            if all(k in result for k in ("high_level", "mid_level", "low_level")):
                # Save backup of original metadata only if we are about to change it
                backup_path = os.path.join(traj_path, "metadata.original.json")
                if not os.path.exists(backup_path):
                    with open(backup_path, "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                metadata["goal"] = result["mid_level"]
                metadata["task"]["instruction"]["high_level"] = result["high_level"]
                metadata["task"]["instruction"]["mid_level"] = result["mid_level"]
                metadata["task"]["instruction"]["low_level"] = result["low_level"]
                
                # Update HTML file
                html_path = os.path.join(traj_path, "trajectory.html")
                if os.path.exists(html_path):
                    try:
                        with open(html_path, "r", encoding="utf-8") as f:
                            html_content = f.read()
                        
                        # Create backup of original HTML
                        html_backup_path = os.path.join(traj_path, "trajectory.original.html")
                        if not os.path.exists(html_backup_path):
                            with open(html_backup_path, "w", encoding="utf-8") as f:
                                f.write(html_content)
                        
                        # Update the instruction table in HTML
                        import re
                        
                        # Replace high_level instruction
                        html_content = re.sub(
                            r'<tr><td><em>high_level</em></td><td>.*?</td></tr>',
                            f'<tr><td><em>high_level</em></td><td>{result["high_level"]}</td></tr>',
                            html_content,
                            flags=re.DOTALL
                        )
                        
                        # Replace mid_level instruction
                        html_content = re.sub(
                            r'<tr><td><em>mid_level</em></td><td>.*?</td></tr>',
                            f'<tr><td><em>mid_level</em></td><td>{result["mid_level"]}</td></tr>',
                            html_content,
                            flags=re.DOTALL
                        )
                        
                        # Replace low_level instruction
                        html_content = re.sub(
                            r'<tr><td><em>low_level</em></td><td>.*?</td></tr>',
                            f'<tr><td><em>low_level</em></td><td>{result["low_level"]}</td></tr>',
                            html_content,
                            flags=re.DOTALL
                        )
                        
                        # Save updated HTML
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        
                        print(f"  ✅ Updated metadata.json, trajectory.html and saved explanation.")
                    except Exception as e:
                        print(f"  ⚠️ Error updating HTML file: {e}")
                        print(f"  ✅ Updated metadata.json and saved explanation.")
                else:
                    print(f"  ✅ Updated metadata.json and saved explanation. (HTML file not found)")
                
                # Save explanation for traceability
                with open(os.path.join(traj_path, "augmentation_explanation.txt"), "w", encoding="utf-8") as f:
                    f.write(result.get("explanation", ""))
                # Save updated metadata
                with open(meta_json, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            else:
                print(f"  ⚠️ LLM response missing required fields. Saving raw result.")
                with open(os.path.join(traj_path, "augmentation_error.json"), "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            count += 1
        except Exception as e:
            print(f"  ❌ Error processing {traj_dir}: {e}")

if __name__ == "__main__":
    main() 