from dataclasses import dataclass
from openai import OpenAI
import json
import base64
import os
from dotenv import load_dotenv
import json
from openai import OpenAI
from PIL import Image
from io import BytesIO
import requests

from prompts import (
    PLAYWRIGHT_CODE_SYSTEM_MSG_FAILED,
    PLAYWRIGHT_CODE_SYSTEM_MSG_CALENDAR,
    PLAYWRIGHT_CODE_SYSTEM_MSG_DELETION_CALENDAR,
    PLAYWRIGHT_CODE_SYSTEM_MSG_MAPS,
    PLAYWRIGHT_CODE_SYSTEM_MSG_FLIGHTS,
    PLAYWRIGHT_CODE_SYSTEM_MSG_SCHOLAR,
    PLAYWRIGHT_CODE_SYSTEM_MSG_DOCS,
)

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

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
    else:
        print("⚠️ Token usage info not available from API response.")

def resize_image_url(url: str, max_width=512) -> str:
    """Download image from URL, resize it, and return base64 string."""
    response = requests.get(url)
    img = Image.open(BytesIO(response.content))
    
    if img.width > max_width:
        aspect_ratio = img.height / img.width
        new_height = int(max_width * aspect_ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
    
    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def clean_code_response(raw_content):
    """Clean the raw response and return the parsed JSON object."""
    raw_content = raw_content.strip()
    
    # Handle null response
    if raw_content == "null":
        return None
        
    # Remove markdown code block if present
    if raw_content.startswith("```json"):
        raw_content = raw_content[len("```json"):].strip()
    elif raw_content.startswith("```"):
        raw_content = raw_content[len("```"):].strip()
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3].strip()
        
    try:
        # Parse and return the entire JSON response
        return json.loads(raw_content)
    except json.JSONDecodeError:
        print("Error: Response was not valid JSON")
        return None

client = OpenAI(api_key=api_key)

@dataclass
class TaskStep:
    action: str
    target: dict
    value: str = None

task_summarizer = []

def chat_ai_playwright_code(accessibility_tree=None, previous_steps=None, taskGoal=None, taskPlan=None, image_path=None, failed_codes=None, is_deletion_task=False, url=None, error_log=None):
    """Get Playwright code directly from GPT to execute the next step.
    
    Args:
        accessibility_tree: The accessibility tree of the current page
        previous_steps: List of previous steps taken
        taskGoal: The overall goal of the task (augmented instruction)
        taskPlan: The current specific goal/plan to execute
        image_path: Path to the screenshot of the current page
        failed_codes: List of previously failed code attempts
        is_deletion_task: Whether this is a deletion task
        url: The URL of the current page
        error_log: The error log for the current task
    """
    # Base system message
    if failed_codes and len(failed_codes) > 0:
            base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_FAILED
            print("\n🤖 Using FAILED ATTEMPT prompt")
    else:
        # Select prompt based on URL
        if url:
            if "calendar.google.com" in url:
                base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_DELETION_CALENDAR if is_deletion_task else PLAYWRIGHT_CODE_SYSTEM_MSG_CALENDAR
                print("\n🤖 Using CALENDAR prompt" + (" (deletion)" if is_deletion_task else ""))
            elif "maps.google.com" in url:
                base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_MAPS
                print("\n🤖 Using MAPS prompt")
            elif "flights.google.com" in url:
                base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_FLIGHTS
                print("\n🤖 Using FLIGHTS prompt")
            elif "scholar.google.com" in url:
                base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_SCHOLAR
                print("\n🤖 Using SCHOLAR prompt")
            elif "docs.google.com" in url:
                base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_DOCS
                print("\n🤖 Using DOCS prompt")
            else:
                # Default to calendar for backward compatibility
                base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_CALENDAR
                print("\n🤖 Using DEFAULT (CALENDAR) prompt")
        else:
            # Default to calendar for backward compatibility
            base_system_message = PLAYWRIGHT_CODE_SYSTEM_MSG_CALENDAR
            print("\n🤖 Using DEFAULT (CALENDAR) prompt")

    if accessibility_tree is not None and previous_steps is not None and image_path:
        try:
            # Resize and encode image
            with Image.open(image_path) as img:
                if img.width > 512:
                    aspect_ratio = img.height / img.width
                    new_height = int(512 * aspect_ratio)
                    img = img.resize((512, new_height), Image.LANCZOS)
                
                buffer = BytesIO()
                img.save(buffer, format="PNG", optimize=True)
                resized_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": base_system_message 
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Task goal: {taskGoal}\nCurrent plan: {taskPlan}\nPrevious steps: {json.dumps(previous_steps, indent=2)}\n\nAccessibility tree: {json.dumps(accessibility_tree, indent=2)}\n\nError log: {error_log if error_log else 'No errors'}"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{resized_image}"
                                }
                            }
                        ]
                    }
                ]
            )
            log_token_usage(response)
            gpt_response = clean_code_response(response.choices[0].message.content)
            print("GPT Response:", gpt_response)
            
            if gpt_response is None:
                print("✅ Task completed!")
                return None
            
            # Add token usage to the response
            if hasattr(response, "usage"):
                gpt_response["total_tokens"] = response.usage.total_tokens
                gpt_response["prompt_tokens"] = response.usage.prompt_tokens
                gpt_response["completion_tokens"] = response.usage.completion_tokens
                
            return gpt_response
            
        except Exception as e:
            print(f"❌ Error in GPT call: {str(e)}")
    else:
        print("⚠️ Error: Missing accessibility tree, previous steps, or image path")