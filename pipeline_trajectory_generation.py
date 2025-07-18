import json
from playwright.sync_api import sync_playwright, TimeoutError
import json
import os
import uuid
import shutil
import time
from typing import Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import html
import re

from generate_trajectory import chat_ai_playwright_code
from config import RESULTS_DIR, ACCOUNTS
from google_auth import ensure_google_login

# ========== CONFIGURABLE PARAMETERS ==========
PHASE = 1
MAX_RETRIES = 7
MAX_STEPS = 25  # Maximum number of steps before failing
ACTION_TIMEOUT = 20000  # 30 seconds timeout for actions
# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0

# Directory to store all browser sessions
BROWSER_SESSIONS_DIR = "browser_sessions"
os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)

def create_episode_directory(base_dir: str, eps_name: str) -> Dict[str, str]:
    """Create directory structure for an episode."""
    eps_dir = os.path.join(base_dir, eps_name)
    dirs = {
        'root': eps_dir,
        'axtree': os.path.join(eps_dir, 'axtree'),
        'images': os.path.join(eps_dir, 'images'),
        'user_message': os.path.join(eps_dir, 'user_message')
    }
    for dir_path in dirs.values():
        os.makedirs(dir_path, exist_ok=True)
    return dirs

def create_trajectory_file(dirs: Dict[str, str]) -> None:
    """Create an empty trajectory.json file with initial structure."""
    trajectory_path = os.path.join(dirs['root'], 'trajectory.json')
    with open(trajectory_path, 'w', encoding='utf-8') as f:
        json.dump({}, f, indent=2, ensure_ascii=False)

def get_element_properties(page, locator_code):
    """Get detailed properties of an element using Playwright locator."""
    try:
        # Handle different locator types
        if "get_by_role" in locator_code:
            # Extract role and name from get_by_role('role', name='name')
            role = locator_code.split("get_by_role('")[1].split("'")[0]
            name = locator_code.split("name='")[1].split("'")[0] if "name='" in locator_code else None
            element = page.get_by_role(role, name=name)
        elif "get_by_label" in locator_code:
            label = locator_code.split("get_by_label('")[1].split("'")[0]
            element = page.get_by_label(label)
        elif "get_by_placeholder" in locator_code:
            placeholder = locator_code.split("get_by_placeholder('")[1].split("'")[0]
            element = page.get_by_placeholder(placeholder)
        elif "get_by_text" in locator_code:
            text = locator_code.split("get_by_text('")[1].split("'")[0]
            element = page.get_by_text(text)
        else:
            # Fallback to locator
            element = page.locator(locator_code)

        if element:
            bbox = element.bounding_box()
            return {
                "bbox": bbox,
                "class": element.get_attribute("class"),
                "id": element.get_attribute("id"),
                "type": element.evaluate("el => el.tagName.toLowerCase()"),
                "ariaLabel": element.get_attribute("aria-label"),
                "role": element.get_attribute("role"),
                "value": element.get_attribute("value"),
                "timestamp": int(time.time() * 1000)
            }
    except Exception as e:
        print(f"⚠️ Error getting element properties: {e}")
        print(f"Locator code: {locator_code}")
    return None

def update_trajectory(dirs: Dict[str, str], step_idx: int, screenshot: str, axtree: str, action_code: str, action_description: str, page, user_message_file: str = None, llm_output=None) -> None:
    """Update trajectory.json with a new step."""
    trajectory_path = os.path.join(dirs['root'], 'trajectory.json')
    try:
        with open(trajectory_path, 'r', encoding='utf-8') as f:
            trajectory = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        trajectory = {}
    
    # Get current page information
    current_url = page.url
    page_title = page.title()
    open_pages = page.context.pages
    open_pages_titles = [p.title() for p in open_pages]
    open_pages_urls = [p.url for p in open_pages]
    
    # Extract action type and locator from the code
    action_type = None
    locator_code = None
    action_output = None
    
    # Get thought from LLM output, fallback to derived thought if not available
    thought = llm_output.get('thought', '') if llm_output else ''
    
    # Parse the action code to determine type and get element properties
    if "page.goto" in action_code:
        action_type = "goto"
        url = action_code.split("page.goto(")[1].split(")")[0].strip('"\'')
        action_output = {
            "thought": thought,
            "action": {
                "url": url
            },
            "action_name": "goto"
        }
    elif ".click()" in action_code:
        action_type = "click"
        locator_code = action_code.split(".click()")[0]
        element_info = page.evaluate("""() => {
            const lastClicked = document.activeElement;
            if (!lastClicked) return null;
            const rect = lastClicked.getBoundingClientRect();
            return {
                bbox: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                },
                class: lastClicked.className,
                id: lastClicked.id,
                type: lastClicked.tagName.toLowerCase(),
                ariaLabel: lastClicked.getAttribute('aria-label'),
                role: lastClicked.getAttribute('role'),
                value: lastClicked.value
            };
        }""")
        if element_info:
            # Extract role and name from Playwright code if possible
            role, name = extract_role_and_name_from_code(action_code)
            if not role:
                role = element_info.get('role', '')
            if not name:
                name = element_info.get('value', '')
            # Try to get a meaningful name for the button from Playwright code first
            button_name = extract_button_name_from_code(action_code)
            if not button_name:
                button_name = name or element_info.get('ariaLabel') or element_info.get('id') or ''
            if button_name:
                thought = f'I need to click the "{button_name}" button.'
            else:
                thought = 'I need to click a button.'
            action_output = {
                "thought": thought,
                "action": {
                    "bid": "",
                    "button": "left",
                    "click_type": "single",
                    "bbox": [
                        element_info['bbox']['x'],
                        element_info['bbox']['y'],
                        element_info['bbox']['width'],
                        element_info['bbox']['height']
                    ],
                    "class": element_info.get('class', ''),
                    "id": element_info.get('id', ''),
                    "type": element_info.get('type', ''),
                    "ariaLabel": element_info.get('ariaLabel', ''),
                    "role": element_info.get('role', ''),
                    "value": element_info.get('value', ''),
                    "node_properties": {
                        "role": role,
                        "value": name
                    }
                },
                "action_name": "click"
            }
    elif ".fill(" in action_code:
        action_type = "type"
        parts = action_code.split(".fill(")
        locator_code = parts[0]
        text = parts[1].split(")")[0].strip('"\'')
        # Get the last focused input element
        element_info = page.evaluate("""() => {
            const lastFocused = document.activeElement;
            if (!lastFocused) return null;
            const rect = lastFocused.getBoundingClientRect();
            return {
                bbox: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                },
                class: lastFocused.className,
                id: lastFocused.id,
                type: lastFocused.tagName.toLowerCase(),
                ariaLabel: lastFocused.getAttribute('aria-label'),
                role: lastFocused.getAttribute('role'),
                value: lastFocused.value
            };
        }""")
        if element_info:
            action_output = {
                "thought": thought,
                "action": {
                    "text": text
                },
                "action_name": "keyboard_type"
            }
    elif ".dblclick()" in action_code:
        action_type = "dblclick"
        locator_code = action_code.split(".dblclick()")[0]
        element_info = page.evaluate("""() => {
            const lastClicked = document.activeElement;
            if (!lastClicked) return null;
            const rect = lastClicked.getBoundingClientRect();
            return {
                bbox: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                },
                class: lastClicked.className,
                id: lastClicked.id,
                type: lastClicked.tagName.toLowerCase(),
                ariaLabel: lastClicked.getAttribute('aria-label'),
                role: lastClicked.getAttribute('role'),
                value: lastClicked.value
            };
        }""")
        if element_info:
            action_output = {
                "thought": thought,
                "action": {
                    "bid": "",
                    "button": "left",
                    "click_type": "double",
                    "bbox": [
                        element_info['bbox']['x'],
                        element_info['bbox']['y'],
                        element_info['bbox']['width'],
                        element_info['bbox']['height']
                    ],
                    "node_properties": {
                        "role": element_info.get('role', ''),
                        "value": element_info.get('value', '')
                    }
                },
                "action_name": "dblclick"
            }
    elif "page.scroll" in action_code:
        action_type = "scroll"
        action_output = {
            "thought": thought,
            "action": {},
            "action_name": "scroll"
        }
    elif ".paste(" in action_code:
        action_type = "paste"
        locator_code = action_code.split(".paste(")[0]
        element_info = page.evaluate("""() => {
            const lastFocused = document.activeElement;
            if (!lastFocused) return null;
            const rect = lastFocused.getBoundingClientRect();
            return {
                bbox: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                },
                class: lastFocused.className,
                id: lastFocused.id,
                type: lastFocused.tagName.toLowerCase(),
                ariaLabel: lastFocused.getAttribute('aria-label'),
                role: lastFocused.getAttribute('role'),
                value: lastFocused.value
            };
        }""")
        if element_info:
            action_output = {
                "thought": thought,
                "action": {
                    "bid": "",
                    "bbox": [
                        element_info['bbox']['x'],
                        element_info['bbox']['y'],
                        element_info['bbox']['width'],
                        element_info['bbox']['height']
                    ],
                    "node_properties": {
                        "role": element_info.get('role', ''),
                        "value": element_info.get('value', '')
                    }
                },
                "action_name": "paste"
            }
    elif "page.keyboard.press" in action_code:
        action_type = "keypress"
        key = action_code.split("page.keyboard.press(")[1].split(")")[0].strip('"\'')
        element_info = page.evaluate("""() => {
            const lastFocused = document.activeElement;
            if (!lastFocused) return null;
            const rect = lastFocused.getBoundingClientRect();
            return {
                bbox: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                },
                class: lastFocused.className,
                id: lastFocused.id,
                type: lastFocused.tagName.toLowerCase(),
                ariaLabel: lastFocused.getAttribute('aria-label'),
                role: lastFocused.getAttribute('role'),
                value: lastFocused.value
            };
        }""")
        if element_info:
            action_output = {
                "thought": thought,
                "action": {
                    "key": key,
                    "bid": "",
                    "bbox": [
                        element_info['bbox']['x'],
                        element_info['bbox']['y'],
                        element_info['bbox']['width'],
                        element_info['bbox']['height']
                    ],
                    "node_properties": {
                        "role": element_info.get('role', ''),
                        "value": element_info.get('value', '')
                    }
                },
                "action_name": "keypress"
            }
    
    # Generate high-level action_str for the step
    action_str = None
    if "page.goto" in action_code:
        url = action_code.split("page.goto(")[1].split(")")[0].strip('"\'')
        action_str = f"goto(url='{url}')"
    elif ".click()" in action_code:
        bid = ""
        button = "left"
        if action_output and "action" in action_output:
            bid = action_output["action"].get("bid", "")
            button = action_output["action"].get("button", "left")
        if bid or button:
            action_str = f"click(bid='{bid}', button='{button}')"
        else:
            action_str = "click(...)"
    elif ".fill(" in action_code:
        text = action_code.split(".fill(")[1].split(")")[0].strip('"\'')
        action_str = f"keyboard_type(text='{text}')"
    elif ".dblclick()" in action_code:
        action_str = "dblclick(...)"
    elif "page.scroll" in action_code:
        action_str = "scroll(...)"
    elif ".paste(" in action_code:
        action_str = "paste(...)"
    elif "page.keyboard.press" in action_code:
        key = action_code.split("page.keyboard.press(")[1].split(")")[0].strip('"\'')
        action_str = f"keyboard_press(key='{key}')"
    else:
        action_str = action_code
    
    # Add new step
    trajectory[str(step_idx + 1)] = {
        "screenshot": os.path.basename(screenshot),
        "axtree": os.path.basename(axtree),
        "user_message": os.path.join('user_message', os.path.basename(user_message_file)) if user_message_file else None,
        "other_obs": {
            "page_index": 0,
            "url": current_url,
            "open_pages_titles": open_pages_titles,
            "open_pages_urls": open_pages_urls
        },
        "action": {
            "action_str": action_str,
            "playwright_code": action_code,
            "action_description": action_description,
            "action_output": action_output
        },
        "error": None,
        "action_timestamp": time.time()
    }
    
    with open(trajectory_path, 'w', encoding='utf-8') as f:
        json.dump(trajectory, f, indent=2, ensure_ascii=False)

def create_metadata(persona: str, url: str, orig_instruction: str, aug_instruction: str, 
                   final_instruction: Optional[str], steps: list, success: bool, total_steps: int,
                   runtime: float, total_tokens: int, page, eps_name: str) -> Dict[str, Any]:
    """Create metadata dictionary."""
    # Get viewport size
    viewport = page.viewport_size
    viewport_str = f"{viewport['width']}x{viewport['height']}" if viewport else "unknown"
    
    # Get browser context info
    context = page.context
    cookies_enabled = context.cookies() is not None
    
    return {
        "goal": orig_instruction,
        "eps_name": eps_name,
        "task": {
            "task_type": "calendar",
            "steps": steps,
            "instruction": {
                "high_level": orig_instruction,
                "mid_level": aug_instruction,
                "low_level": final_instruction if final_instruction else aug_instruction
            }
        },
        "start_url": url,
        "browser_context": {
            "os": os.uname().sysname.lower(),  # Get OS name
            "viewport": viewport_str,
            "cookies_enabled": cookies_enabled
        },
        "success": success,
        "total_steps": total_steps,
        "runtime_sec": runtime,
        "total_tokens": total_tokens,
        "phase": PHASE
    }

def is_already_logged_in(page, timeout: int = 5000) -> bool:
    """
    Check if the user is already logged into Google.
    
    Args:
        page: Playwright page object
        timeout: Timeout in milliseconds for the check
        
    Returns:
        bool: True if already logged in, False otherwise
    """
    try:
        # Check for Google Account button or profile picture
        return page.locator('[aria-label*="Google Account"]').count() > 0 or \
               page.locator('img[alt*="Google Account"]').count() > 0
    except Exception:
        return False

def handle_google_login(page, email: str, password: str, timeout: int = 30000) -> bool:
    """
    Handle Google login process automatically.
    
    Args:
        page: Playwright page object
        email: Google account email
        password: Google account password
        timeout: Timeout in milliseconds for each step
        
    Returns:
        bool: True if login was successful, False otherwise
    """
    try:
        # If the "Sign in" button is present (landing page), click it
        if page.locator('text=Sign in').count() > 0:
            print("🔵 'Sign in' button detected on landing page. Clicking it...")
            page.click('text=Sign in')
            page.wait_for_timeout(1000)  # Wait for the login page to load

        # First check if already logged in
        if is_already_logged_in(page):
            print("✅ Already logged in to Google")
            return True

        # Handle 'Choose an account' screen if present
        if page.locator('text=Choose an account').count() > 0:
            print("🔄 'Choose an account' screen detected. Always clicking 'Use another account'.")
            page.click('text=Use another account')
            # Wait a moment for the next screen to load
            page.wait_for_timeout(1000)

        # Wait for the email input field
        page.wait_for_selector('input[type="email"]', timeout=timeout)
        page.fill('input[type="email"]', email)
        page.click('button:has-text("Next")')
        
        # Wait for password input
        page.wait_for_selector('input[type="password"]', timeout=timeout)
        page.fill('input[type="password"]', password)
        page.click('button:has-text("Next")')
        
        # Wait for either successful login or error
        try:
            # Wait for successful login indicators
            page.wait_for_selector('[aria-label*="Google Account"]', timeout=timeout)
            return True
        except TimeoutError:
            # Check for error messages
            error_selectors = [
                'text="Wrong password"',
                'text="Couldn\'t find your Google Account"',
                'text="This account doesn\'t exist"'
            ]
            for selector in error_selectors:
                if page.locator(selector).count() > 0:
                    print(f"❌ Login failed: {page.locator(selector).text_content()}")
                    return False
            
            # If no specific error found but login didn't complete
            print("❌ Login failed: Unknown error")
            return False
            
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return False

def write_user_message(user_message_file: str, goal: str, execution_history: list, page, tree, failed_codes: list = None):
    """Write a user message file with goal, previous actions, current page, ax tree, and error codes."""
    user_message_content = []
    user_message_content.append(f"Goal: {goal}\n")
    user_message_content.append("Previous Actions:")
    if execution_history:
        for i, act in enumerate(execution_history, 1):
            user_message_content.append(f"  {i}. {act['step']} | Code: {act['code']}")
    else:
        user_message_content.append("  None")
    user_message_content.append("")
    user_message_content.append(f"Current Page: {page.title()} ({page.url})\n")
    user_message_content.append("AX Tree:")
    user_message_content.append(json.dumps(tree, indent=2, ensure_ascii=False))
    user_message_content.append("")
    user_message_content.append("Error Codes:")
    if failed_codes:
        for err in failed_codes:
            user_message_content.append(f"  {err}")
    else:
        user_message_content.append("  None")
    with open(user_message_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(user_message_content))

def generate_trajectory_loop(user_data_dir, chrome_path, phase, start_idx, end_idx, email: Optional[str] = None, password: Optional[str] = None):
    phase_file = os.path.join(RESULTS_DIR, f"instructions_phase{phase}.json")
    try:
        with open(phase_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading {phase_file}: {e}")
        return

    all_instructions = []
    for persona_data in data:
        persona = persona_data['persona']
        url = persona_data['url']
        original_instructions = persona_data['instructions']
        augmented = persona_data['augmented_instructions']
        for orig, aug in zip(original_instructions, augmented):
            all_instructions.append({
                'persona': persona,
                'url': url,
                'original_instruction': orig,
                'augmented_instruction': aug
            })

    total = len(all_instructions)
    if start_idx >= total or end_idx <= start_idx or end_idx > total:
        print(f"❌ Invalid range: total={total}, requested={start_idx}-{end_idx}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=chrome_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        try:
            # Create page once at the start
            page = browser.new_page()
            page.set_default_timeout(ACTION_TIMEOUT)
            
            for idx, item in enumerate(all_instructions[start_idx:end_idx], start=start_idx):
                persona = item['persona']
                url = item['url']
                orig = item['original_instruction']
                aug = item['augmented_instruction']
                eps_name = f"calendar_{uuid.uuid4()}"
                dirs = create_episode_directory(RESULTS_DIR, eps_name)
                create_trajectory_file(dirs)  # Create empty trajectory.json

                print(f"\n🔄 Instruction {idx + 1}/{total}")
                print(f"👤 {persona}")
                print(f"🌐 {url}")
                print(f"📝 Orig: {orig}")
                print(f"🔄 Aug: {aug}")
                print(f"UUID: {eps_name}")

                # Navigate to URL for this instruction
                page.goto(url)
                
                # Handle login using the new module
                # ensure_google_login(page, email, password, url)

                execution_history = []
                task_summarizer = []
                current_goal = aug
                should_continue = True
                start_time = time.time()
                total_tokens = 0  # Initialize token counter

                while should_continue:
                    step_idx = len(task_summarizer)

                    if step_idx >= MAX_STEPS:
                        print(f"❌ Maximum number of steps ({MAX_STEPS}) exceeded.")
                        runtime = time.time() - start_time
                        metadata = create_metadata(
                            persona, url, orig, aug, None,  # Pass None for final_instruction
                            [step['step'] for step in task_summarizer],
                            False, step_idx, runtime, total_tokens, page, eps_name
                        )
                        if gpt_resp and "output" in gpt_resp:
                            metadata["gpt_output"] = gpt_resp["output"]
                        with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, indent=2, ensure_ascii=False)
                        # Generate HTML after metadata is created
                        generate_trajectory_html(dirs, metadata)
                        should_continue = False
                        break

                    screenshot = os.path.join(dirs['images'], f"screenshot_{step_idx+1:03d}.png")
                    axtree_file = os.path.join(dirs['axtree'], f"axtree_{step_idx+1:03d}.txt")
                    try:
                        page.screenshot(path=screenshot)
                        tree = page.accessibility.snapshot()
                        with open(axtree_file, 'w', encoding='utf-8') as f:
                            json.dump(tree, f, indent=2, ensure_ascii=False)
                    except Exception as e:
                        if "TargetClosedError" in str(e):
                            print("❌ Page was closed unexpectedly. Attempting to recover...")
                            # Try to create a new page
                            try:
                                page = browser.new_page()
                                page.set_default_timeout(ACTION_TIMEOUT)
                                page.goto(url)
                                # Handle login again
                                ensure_google_login(page, email, password, url)
                                # Retry the screenshot and tree capture
                                page.screenshot(path=screenshot)
                                tree = page.accessibility.snapshot()
                                with open(axtree_file, 'w', encoding='utf-8') as f:
                                    json.dump(tree, f, indent=2, ensure_ascii=False)
                            except Exception as recovery_error:
                                print(f"❌ Recovery failed: {str(recovery_error)}")
                                runtime = time.time() - start_time
                                metadata = create_metadata(
                                    persona, url, orig, aug, None,
                                    [step['step'] for step in task_summarizer],
                                    False, step_idx, runtime, total_tokens, page, eps_name
                                )
                                # Add GPT response output to metadata if available
                                if gpt_resp and "output" in gpt_resp:
                                    metadata["gpt_output"] = gpt_resp["output"]
                                with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                                generate_trajectory_html(dirs, metadata)
                                should_continue = False
                                break
                        else:
                            print(f"❌ Error capturing page state: {str(e)}")
                            runtime = time.time() - start_time
                            metadata = create_metadata(
                                persona, url, orig, aug, None,
                                [step['step'] for step in task_summarizer],
                                False, step_idx, runtime, total_tokens, page, eps_name
                            )
                            # Add GPT response output to metadata if available
                            if gpt_resp and "output" in gpt_resp:
                                metadata["gpt_output"] = gpt_resp["output"]
                            with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                                json.dump(metadata, f, indent=2, ensure_ascii=False)
                            generate_trajectory_html(dirs, metadata)
                            should_continue = False
                            break
                    is_del = 'delete' in current_goal.lower()

                    gpt_resp = chat_ai_playwright_code(
                        accessibility_tree=tree,
                        previous_steps=execution_history,
                        taskGoal=aug,
                        taskPlan=current_goal,
                        image_path=screenshot,
                        failed_codes=[],
                        is_deletion_task=is_del,
                        url=url
                    )

                    # Handle case where GPT response is None
                    if gpt_resp is None:
                        print("❌ GPT returned no response")
                        runtime = time.time() - start_time
                        metadata = create_metadata(
                            persona, url, orig, aug, None,  # Pass None for final_instruction
                            [step['step'] for step in task_summarizer],
                            False, step_idx, runtime, total_tokens, page, eps_name
                        )
                        if gpt_resp and "output" in gpt_resp:
                            metadata["gpt_output"] = gpt_resp["output"]
                        with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, indent=2, ensure_ascii=False)
                        # Generate HTML after metadata is created
                        generate_trajectory_html(dirs, metadata)
                        should_continue = False
                        break

                    # Update total tokens from GPT response
                    if "total_tokens" in gpt_resp:
                        total_tokens += gpt_resp["total_tokens"]
                        print(f"📊 Current total tokens: {total_tokens}")

                    if "summary_instruction" in gpt_resp:
                        runtime = time.time() - start_time
                        metadata = create_metadata(
                            persona, url, orig, aug, gpt_resp['summary_instruction'],
                            [step['step'] for step in task_summarizer],
                            True, step_idx, runtime, total_tokens, page, eps_name
                        )
                        if gpt_resp and "output" in gpt_resp:
                            metadata["gpt_output"] = gpt_resp["output"]
                        with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, indent=2, ensure_ascii=False)
                        # Generate HTML after metadata is created
                        generate_trajectory_html(dirs, metadata)
                        print("✅ Task completed, metadata saved.")
                        break

                    if "updated_goal" in gpt_resp:
                        current_goal = gpt_resp["updated_goal"]

                    failed_codes = []
                    retry = 0
                    description = gpt_resp["description"] if gpt_resp else ""
                    code = gpt_resp["code"] if gpt_resp else ""
                    success = False

                    while retry < MAX_RETRIES and not success:
                        try:
                            print(f"🤖 {description}")
                            print(f"🔄 Code: {code}")
                            print(f"🔄 Failed Codes: {failed_codes}")
                            exec(code)
                            # Only save files and document steps if the execution was successful
                            execution_history.append({'step': description, 'code': code})
                            task_summarizer.append({'step': description, 'code': code, 'axtree': tree})
                            # Save axtree to file only after successful execution
                            with open(axtree_file, 'w', encoding='utf-8') as f:
                                json.dump(tree, f, indent=2, ensure_ascii=False)
                            # Update trajectory.json with the successful step
                            update_trajectory(
                                dirs=dirs,
                                step_idx=step_idx,
                                screenshot=screenshot,
                                axtree=axtree_file,
                                action_code=code,
                                action_description=description,
                                page=page,
                                user_message_file=os.path.join(dirs['user_message'], f"user_message_{step_idx+1:03d}.txt"),
                                llm_output=gpt_resp
                            )
                            success = True
                        except Exception as e:
                            retry += 1
                            if code not in failed_codes:
                                failed_codes.append(code)
                            print(f"⚠️ Attempt {retry} failed: {e}")
                            if retry < MAX_RETRIES:
                                print("🔄 Retrying GPT for new code...")
                                page.screenshot(path=screenshot)
                                tree = page.accessibility.snapshot()
                                with open(axtree_file, 'w', encoding='utf-8') as f:
                                    json.dump(tree, f, indent=2, ensure_ascii=False)
                                error_log = str(e)
                                print(f"📝 Error log: {error_log}")
                                gpt_resp = chat_ai_playwright_code(
                                        accessibility_tree=tree,
                                    previous_steps=execution_history,
                                    taskGoal=aug,
                                    taskPlan=current_goal,
                                    image_path=screenshot,
                                    failed_codes=failed_codes,
                                    is_deletion_task=is_del,
                                    url=url,
                                    error_log=error_log
                                )
                                # Update total tokens from retry response
                                if gpt_resp and "total_tokens" in gpt_resp:
                                    total_tokens += gpt_resp["total_tokens"]
                                    print(f"📊 Current total tokens: {total_tokens}")

                                if gpt_resp and "summary_instruction" in gpt_resp:
                                    runtime = time.time() - start_time
                                    metadata = create_metadata(
                                        persona, url, orig, aug, gpt_resp['summary_instruction'],
                                        [step['step'] for step in task_summarizer],
                                        True, step_idx, runtime, total_tokens, page, eps_name
                                    )
                                    if gpt_resp and "output" in gpt_resp:
                                        metadata["gpt_output"] = gpt_resp["output"]
                                    with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                                    # Generate HTML after metadata is created
                                    generate_trajectory_html(dirs, metadata)
                                    print("✅ Task completed on retry, metadata saved.")
                                    should_continue = False
                                    break
                                if gpt_resp and "updated_goal" in gpt_resp:
                                    current_goal = gpt_resp["updated_goal"]
                                description = gpt_resp["description"] if gpt_resp else ""
                                code = gpt_resp["code"] if gpt_resp else ""
                            else:
                                print(f"❌ All {MAX_RETRIES} retries failed.")
                                runtime = time.time() - start_time
                                metadata = create_metadata(
                                    persona, url, orig, aug, None,  # Pass None for final_instruction
                                    [step['step'] for step in task_summarizer],
                                    False, step_idx, runtime, total_tokens, page, eps_name
                                )
                                if gpt_resp and "output" in gpt_resp:
                                    metadata["gpt_output"] = gpt_resp["output"]
                                with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                                # Generate HTML after metadata is created
                                generate_trajectory_html(dirs, metadata)
                                should_continue = False
                                break
                                        
                    if success:
                        page.wait_for_timeout(2000)
                    else:
                        # If the step failed, remove both screenshot and axtree files
                        if os.path.exists(screenshot):
                            os.remove(screenshot)
                        if os.path.exists(axtree_file):
                            os.remove(axtree_file)
                            break

                    # Prepare user message content
                    user_message_file = os.path.join(dirs['user_message'], f"user_message_{step_idx+1:03d}.txt")
                    write_user_message(
                        user_message_file=user_message_file,
                        goal=current_goal,
                        execution_history=execution_history,
                        page=page,
                        tree=tree,
                        failed_codes=failed_codes if 'failed_codes' in locals() else None
                    )

                # Don't close the page here, just continue to next instruction
                
        finally:
            # Close page and browser at the very end
            if MODE == 1:
                    input("🔚 Press Enter to continue...")
            page.close()
            browser.close()

def run_for_account(account, chrome_path, phase):
    user_data_dir = os.path.join(BROWSER_SESSIONS_DIR, account["user_data_dir"])
    # Only create the directory if it doesn't exist
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir, exist_ok=True)
    generate_trajectory_loop(
        user_data_dir=user_data_dir,
        chrome_path=chrome_path,
        phase=phase,
        start_idx=account["start_idx"],
        end_idx=account["end_idx"],
        email=account["email"],
        password=account["password"]
    )

def main():
    chrome_exec = os.getenv("CHROME_EXECUTABLE_PATH")
    phase = PHASE
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        futures = [
            executor.submit(run_for_account, account, chrome_exec, phase)
            for account in ACCOUNTS
        ]
        for future in futures:
            future.result()  # Wait for all to finish

def generate_trajectory_html(dirs: Dict[str, str], metadata: Dict[str, Any]) -> None:
    """Generate an HTML visualization of the trajectory."""
    trajectory_path = os.path.join(dirs['root'], 'trajectory.json')
    html_path = os.path.join(dirs['root'], 'trajectory.html')
    
    try:
        with open(trajectory_path, 'r', encoding='utf-8') as f:
            trajectory = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("❌ Error loading trajectory.json")
        return

    # Instruction Table
    instructions = metadata['task']['instruction']
    steps = metadata['task']['steps']
    html_content = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Visualization of Trajectory</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1, h2 {{ color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        .step {{ border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; background-color: white; }}
        .step-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .step-number {{ font-size: 1.2em; font-weight: bold; color: #2196F3; }}
        .step-content {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .screenshot {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }}
        .collapsible {{ background-color: #eee; color: #444; cursor: pointer; padding: 10px; width: 100%; border: none; text-align: left; outline: none; font-size: 1em; margin-top: 5px; }}
        .active, .collapsible:hover {{ background-color: #ccc; }}
        .content {{ padding: 0 18px; display: none; overflow: auto; background-color: #f9f9f9; border-radius: 0 0 5px 5px; }}
        pre {{ white-space: pre-wrap; word-break: break-word; }}
        table.instruction-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        table.instruction-table th, table.instruction-table td {{ border: 1px solid #ddd; padding: 8px; }}
        table.instruction-table th {{ background: #f0f0f0; text-align: left; }}
        .steps-list {{ margin: 0; padding-left: 20px; }}
        .steps-list li {{ margin-bottom: 4px; }}
        .step-details-label {{ font-weight: bold; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class=\"container\">
        <h1>{metadata['eps_name']} ({metadata['task'].get('task_type','')})</h1>
        <h2>Instructions</h2>
        <table class=\"instruction-table\">
            <tr><th>level</th><th>instruction</th></tr>
            <tr><td><em>high_level</em></td><td>{html.escape(instructions.get('high_level',''))}</td></tr>
            <tr><td><em>mid_level</em></td><td>{html.escape(instructions.get('mid_level',''))}</td></tr>
            <tr><td><em>low_level</em></td><td>{html.escape(instructions.get('low_level',''))}</td></tr>
            <tr><td><em>steps</em></td><td><ul class=\"steps-list\">{''.join(f'<li>{html.escape(str(s))}</li>' for s in steps)}</ul></td></tr>
        </table>
        <h2>Trajectory Steps</h2>
"""

    for step_num, step_data in trajectory.items():
        screenshot_path = os.path.join('images', step_data['screenshot'])
        user_message_path = step_data.get('user_message')
        user_message_content = ""
        if user_message_path:
            user_message_full_path = os.path.join(dirs['root'], user_message_path)
            try:
                with open(user_message_full_path, 'r', encoding='utf-8') as umf:
                    user_message_content = html.escape(umf.read())
            except Exception:
                user_message_content = "[Could not load user message]"
        else:
            user_message_content = "[No user message]"
        action = step_data['action']
        action_output = action.get('action_output', {})
        thought = html.escape(action_output.get('thought', ''))
        action_str = html.escape(action.get('action_str', ''))
        action_description = html.escape(action.get('action_description', ''))
        # System message: use a field if available, else placeholder
        system_message = step_data.get('system_message', 'System message for this step (placeholder)')
        # Element output: pretty print action_output['action'] if available
        element_output = ''
        if 'action' in action_output:
            element_output = json.dumps(action_output['action'], indent=2, ensure_ascii=False)
            element_output = html.escape(element_output)
        else:
            element_output = '[No element output]'
        # LLM output: show Playwright code for this step
        playwright_code = action.get('playwright_code', '')
        llm_output_str = html.escape(playwright_code) if playwright_code else 'No Playwright code for this step.'

        html_content += f"""
        <div class=\"step\">
            <div class=\"step-header\">
                <span class=\"step-number\">Step {step_num}</span>
            </div>
            <div class=\"step-content\">
                <div>
                    <img src=\"{screenshot_path}\" alt=\"Step {step_num} Screenshot\" class=\"screenshot\">
                </div>
                <div>
                    <div class=\"step-details-label\">Thought</div>
                    <div>{thought}</div>
                    <div class=\"step-details-label\">Action</div>
                    <div>{action_str}</div>
                    <div class=\"step-details-label\">Action Description</div>
                    <div>{action_description}</div>
                    <button class=\"collapsible\">System Message</button>
                    <div class=\"content\"><pre>{system_message}</pre></div>
                    <button class=\"collapsible\">User Message</button>
                    <div class=\"content\"><pre>{user_message_content}</pre></div>
                    <button class=\"collapsible\">Element Output</button>
                    <div class=\"content\"><pre>{element_output}</pre></div>
                    <button class=\"collapsible\">LLM Output</button>
                    <div class=\"content\"><pre>{llm_output_str}</pre></div>
                </div>
            </div>
        </div>
        """

    html_content += """
    </div>
    <script>
    document.addEventListener('DOMContentLoaded', function() {
      var coll = document.getElementsByClassName('collapsible');
      for (var i = 0; i < coll.length; i++) {
        coll[i].addEventListener('click', function() {
          this.classList.toggle('active');
          var content = this.nextElementSibling;
          if (content.style.display === 'block') {
            content.style.display = 'none';
          } else {
            content.style.display = 'block';
          }
        });
      }
    });
    </script>
</body>
</html>"""

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

def extract_button_name_from_code(action_code):
    match = re.search(r"name=['\"]([^'\"]+)['\"]", action_code)
    if match:
        return match.group(1)
    return None

def extract_role_and_name_from_code(action_code):
    role_match = re.search(r"get_by_role\(['\"]([^'\"]+)['\"]", action_code)
    name_match = re.search(r"name=['\"]([^'\"]+)['\"]", action_code)
    role = role_match.group(1) if role_match else None
    name = name_match.group(1) if name_match else None
    return role, name

if __name__ == "__main__":
    main()