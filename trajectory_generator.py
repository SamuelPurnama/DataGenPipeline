from playwright.sync_api import sync_playwright
from dataclasses import dataclass
from openai import OpenAI
import json
import base64
import os
from datetime import datetime
from dotenv import load_dotenv
import json
from openai import OpenAI
from PIL import Image
from io import BytesIO
import requests
import re

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
chrome_profile_path = os.getenv("CHROME_PROFILE_PATH")
chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")

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

def clean_json_response(raw_content):
    raw_content = raw_content.strip()
    # Remove triple backticks and optional language tag (e.g., ```json)
    raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
    raw_content = re.sub(r"\s*```$", "", raw_content)
    return raw_content


@dataclass
class TaskStep:
    action: str
    target: dict
    value: str = None

task_summarizer = []

def is_calendar_event(node):
    """
    Detect calendar events and tasks based on known structure:
    - role is 'button'
    - name contains 'calendar:' and time info like 'am', 'pm', or 'all day'
    """
    name = node.get("name", "").lower()
    return (
        node.get("role") == "button" and
        "calendar:" in name and
        ("am" in name or "pm" in name or "all day" in name)
    )

def prune_ax_tree(node):
    """
    Recursively prune the accessibility tree to:
    - Keep only relevant roles and properties
    - Remove event/task buttons from calendar gridcells
    """

    # Roles we care about
    actionable_roles = {
        "button", "link", "textbox", "checkbox", "radio",
        "combobox", "tab", "switch", "menuitem", "listitem", "option"
    }

    # Properties to keep
    keep_attrs = {"role", "name", "checked", "pressed", "expanded", "haspopup", "children"}

    # Base case: no children
    if "children" not in node:
        return {k: v for k, v in node.items() if k in keep_attrs} if node.get("role") in actionable_roles else None

    # Recursively prune children
    pruned_children = []
    for child in node["children"]:
        if is_calendar_event(child):
            continue  # ❌ Remove scheduled calendar events/tasks
        pruned = prune_ax_tree(child)
        if pruned:
            pruned_children.append(pruned)

    # Keep this node if it's actionable or has valid children
    if node.get("role") in actionable_roles or pruned_children:
        pruned_node = {k: v for k, v in node.items() if k in keep_attrs and k != "children"}
        if pruned_children:
            pruned_node["children"] = pruned_children
        return pruned_node

    return None

def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        encoded_string = base64.b64encode(img_file.read()).decode("utf-8")
    return encoded_string

def chat_ai_accessibility_tree_text_only(accessibility_tree=None, previous_steps=None, taskGoal=None):
    """Analyze accessibility tree only (no screenshot) to predict next Playwright action."""

    if accessibility_tree is not None and previous_steps is not None:
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an assistant that analyzes a web page's accessibility tree to help complete a user's task.
                                    Your responsibilities:
                                    1. Check if the task goal has already been completed (i.e., not just filled out, but fully finalized by clicking save/submit). If so, return: null
                                    2. If not, predict the next step the user should take to make progress.
                                    3. Identify the correct UI element based on the accessibility tree to perform the next predicted step on.
                                    4. Return:
                                        - A human-friendly explanation of the next suggested step
                                        - A structured object with the role, name, and action to perform on the matched element

                                    You will receive:
                                    - Task goal – the user's intended outcome (e.g., "create a calendar event for May 1st at 10PM")
                                    - Previous steps – a list of actions the user has already taken. It's okay if the previous steps array is empty.
                                    - Accessibility tree – a list of role-name objects describing all visible and interactive elements on the page

                                    Your response must follow this output format:
                                    {
                                    "explanation": "<concise description of the next step>",
                                    "action": {
                                        "role": "<role of the matched element>",
                                        "name": "<name of the matched element>",
                                        "action": "<click, fill, or other interaction>",
                                        "value": "<only required if action is 'fill', 'type', or 'select'; omit otherwise>",
                                        "iframe": "<only required if the matched element is inside an iframe; omit otherwise>"
                                    }
                                    }
                                    If no further action is needed, return:
                                    null
                                    """
                    },
                    {
                        "role": "user",
                        "content": f"Task goal: {taskGoal}\nPrevious steps: {json.dumps(previous_steps, indent=2)}\n\nAccessibility tree: {json.dumps(accessibility_tree, indent=2)}"
                    }
                ]
            )
            log_token_usage(response) 
            raw_content = clean_json_response(response.choices[0].message.content)
            try:
                result = json.loads(raw_content)
                if result is None:
                    print("✅ Task goal appears to be complete. No further action needed.")
                    return None
                return result
            except json.JSONDecodeError:
                print("\nError: AI response was not valid JSON")
                print("Raw response:", raw_content)
        except Exception as e:
            print(f"❌ Error in GPT call: {str(e)}")
    else:
        print("⚠️ Error: Missing accessibility tree or previous steps")

def chat_ai_accessibility_tree(accessibility_tree=None, previous_steps=None, taskGoal=None, image_path=None):
    """Analyze accessibility tree and screenshot (from path) to predict next Playwright action."""

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
                        "content": """You are an assistant that analyzes a web page's accessibility tree and the screenshot of the current page to help complete a user's task.

                        Your responsibilities:
                        1. Check if the task goal has already been completed (i.e., not just filled out, but fully finalized by CLICKING SAVE/SUBMIT). If so, return: null
                        2. If not, predict the next step the user should take to make progress.
                        3. Identify the correct UI element based on the accessibility tree and a screenshot of the current page to perform the next predicted step to get closer to the end goal.
                        4. Return:
                            - A human-friendly explanation of the next suggested step
                            - A structured object with the role, name, and action to perform on the matched element

                        You will receive:
                        - Task goal – the user's intended outcome (e.g., "create a calendar event for May 1st at 10PM")
                        - Previous steps – a list of actions the user has already taken. It's okay if the previous steps array is empty.
                        - Accessibility tree – a list of role-name objects describing all visible and interactive elements on the page
                        - Screenshot of the current page`

                        Your response must follow this output format:
                        {
                        "explanation": "<concise description of the next step>",
                        "action": {
                            "role": "<role of the matched element>",
                            "name": "<name of the matched element>",
                            "action": "<click, fill, or other interaction>",
                            "value": "<only required if action is 'fill', 'type', or 'select'; omit otherwise>",
                        }
                        }

                        If no further action is needed, return:
                        null
                        """
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Task goal: {taskGoal}\nPrevious steps: {json.dumps(previous_steps, indent=2)}\n\nAccessibility tree: {json.dumps(accessibility_tree, indent=2)}"
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
            raw_content = clean_json_response(response.choices[0].message.content)
            print("Raw_content:", raw_content)

            try:
                result = json.loads(raw_content)
                if result is None:
                    print("✅ Task goal appears to be complete. No further action needed.")
                    return None
                return result
            except json.JSONDecodeError:
                print("\nError: AI response was not valid JSON")
                print("Raw response:", raw_content)
        except Exception as e:
            print(f"❌ Error in GPT call: {str(e)}")
    else:
        print("⚠️ Error: Missing accessibility tree, previous steps, or image path")


def generate_trajectory(task_goal, url):
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=chrome_profile_path,
            executable_path=chrome_executable_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        print(task_goal)

        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(url)
        task_summarizer = []
        try:
            page.wait_for_selector('[aria-label*="Google Account"]', timeout=300000)
            print("✅ Logged in successfully!")

            while True:
                # Take screenshot
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"./screenshots/step_{timestamp}.png"
                page.screenshot(path=screenshot_path)

                # Get accessibility tree
                tree = page.accessibility.snapshot()
                print("Tree:", tree)
                result = chat_ai_accessibility_tree(
                    accessibility_tree= tree,
                    previous_steps=task_summarizer,
                    taskGoal=task_goal,
                    image_path=screenshot_path
                )

                if result is None:
                    print("Task completed!")
                    break

                print(f"🤖 Step: {result['explanation']}")
                task_summarizer.append(result['action'])
                role = result['action']['role']
                name = result['action']['name']
                action = result['action']['action']
                if action == "click":
                    page.get_by_role(role, name=name).click()
                elif action == "fill":
                    value = result['action']['value']
                    page.get_by_role(role, name=name).fill(value)
                elif action == "check":
                    page.get_by_role(role, name=name).check()
                elif action == "uncheck":
                    page.get_by_role(role, name=name).uncheck()
                elif action == "hover":
                    page.get_by_role(role, name=name).hover()
                elif action == "dblclick":
                    page.get_by_role(role, name=name).dblclick()
                elif action == "press":
                    # Expecting action object to include a key like {"key": "Enter"}
                    key = result['action'].get("key", "Enter")
                    page.get_by_role(role, name=name).press(key)
                elif action == "select":
                    # Expecting action object to include a value like {"value": "May"}
                    value = result['action'].get("value", "")
                    page.get_by_role(role, name=name).select_option(value)
                elif action == "type":
                    value = result['action'].get("value", "")
                    page.get_by_role(role, name=name).type(value)
                else:
                    print(f"⚠️ Unknown action: {action}")

                page.wait_for_timeout(1000)  # short delay between steps

        except Exception as e:
            print(f"❌ Error: {str(e)}")
        finally:
            input("🔚 Press Enter to close browser...")
            browser.close()