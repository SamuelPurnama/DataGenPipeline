from playwright.sync_api import sync_playwright, TimeoutError
import json
import os
import uuid
import shutil
import time
from typing import Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor

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
        'images': os.path.join(eps_dir, 'images')
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

def update_trajectory(dirs: Dict[str, str], step_idx: int, screenshot: str, axtree: str, action_code: str, action_description: str, page) -> None:
    """Update trajectory.json with a new step."""
    trajectory_path = os.path.join(dirs['root'], 'trajectory.json')
    try:
        with open(trajectory_path, 'r', encoding='utf-8') as f:
            trajectory = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        trajectory = {}
    
    # Extract action type and locator from the code
    action_type = None
    locator_code = None
    action_output = None
    
    # Parse the action code to determine type and get element properties
    if "page.goto" in action_code:
        action_type = "goto"
        url = action_code.split("page.goto(")[1].split(")")[0].strip('"\'')
        action_output = {"url": url, "timestamp": int(time.time() * 1000)}
    elif ".click()" in action_code:
        action_type = "click"
        locator_code = action_code.split(".click()")[0]
        # Get the last clicked element
        action_output = page.evaluate("""() => {
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
                value: lastClicked.value,
                timestamp: Date.now()
            };
        }""")
    elif ".fill(" in action_code:
        action_type = "type"
        parts = action_code.split(".fill(")
        locator_code = parts[0]
        text = parts[1].split(")")[0].strip('"\'')
        # Get the last focused input element
        action_output = page.evaluate("""() => {
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
                value: lastFocused.value,
                text: lastFocused.value,
                timestamp: Date.now()
            };
        }""")
    elif ".dblclick()" in action_code:
        action_type = "dblclick"
        locator_code = action_code.split(".dblclick()")[0]
        # Get the last double-clicked element
        action_output = page.evaluate("""() => {
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
                value: lastClicked.value,
                timestamp: Date.now()
            };
        }""")
    elif "page.scroll" in action_code:
        action_type = "scroll"
        action_output = {"timestamp": int(time.time() * 1000)}
    elif ".paste(" in action_code:
        action_type = "paste"
        locator_code = action_code.split(".paste(")[0]
        # Get the last focused element
        action_output = page.evaluate("""() => {
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
                value: lastFocused.value,
                timestamp: Date.now()
            };
        }""")
    elif "page.keyboard.press" in action_code:
        action_type = "keypress"
        key = action_code.split("page.keyboard.press(")[1].split(")")[0].strip('"\'')
        # Get the last focused element
        action_output = page.evaluate("""() => {
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
                value: lastFocused.value,
                key: arguments[0],
                timestamp: Date.now()
            };
        }""", key)
    
    # Add new step
    trajectory[str(step_idx + 1)] = {
        "screenshot": os.path.basename(screenshot),
        "axtree": os.path.basename(axtree),
        "action": {
            "action_code": action_code,
            "action_description": action_description,
            "action_type": action_type,
            "action_output": action_output
        }
    }
    
    with open(trajectory_path, 'w', encoding='utf-8') as f:
        json.dump(trajectory, f, indent=2, ensure_ascii=False)

def create_metadata(persona: str, url: str, orig_instruction: str, aug_instruction: str, 
                   final_instruction: Optional[str], steps: list, success: bool, total_steps: int,
                   runtime: float, total_tokens: int, page) -> Dict[str, Any]:
    """Create metadata dictionary."""
    # Get viewport size
    viewport = page.viewport_size
    viewport_str = f"{viewport['width']}x{viewport['height']}" if viewport else "unknown"
    
    # Get browser context info
    context = page.context
    cookies_enabled = context.cookies() is not None
    
    return {
        "eps_name": f"calendar_{uuid.uuid4()}",
        "start_url": url,
        "phase": PHASE,
        "browser_context": {
            "os": os.uname().sysname.lower(),  # Get OS name
            "viewport": viewport_str,
            "cookies_enabled": cookies_enabled
        },
        "task": {
            "task_type": "calendar",  # or determine from instruction
            "persona": persona,
            "instruction": {
                "level1": orig_instruction,
                "level2": aug_instruction,
                "level3": final_instruction if final_instruction else aug_instruction  # Fallback to aug_instruction if final_instruction is None
            },
            "steps": steps
        },
        "success": success,
        "total_steps": total_steps,
        "runtime_sec": runtime,
        "total_tokens": total_tokens
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

                page = browser.new_page()
                page.set_default_timeout(ACTION_TIMEOUT)
                page.goto(url)
                
                # Handle login using the new module
                ensure_google_login(page, email, password, url)

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
                            False, step_idx, runtime, total_tokens, page
                        )
                        with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, indent=2, ensure_ascii=False)
                        # Generate HTML after metadata is created
                        generate_trajectory_html(dirs, metadata)
                        should_continue = False
                        break

                    screenshot = os.path.join(dirs['images'], f"{step_idx:04d}.png")
                    axtree_file = os.path.join(dirs['axtree'], f"{step_idx:04d}.json")
                    page.screenshot(path=screenshot)
                    tree = page.accessibility.snapshot()
                    with open(axtree_file, 'w', encoding='utf-8') as f:
                        json.dump(tree, f, indent=2, ensure_ascii=False)
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

                    # Update total tokens from GPT response
                    if gpt_resp and "total_tokens" in gpt_resp:
                        total_tokens += gpt_resp["total_tokens"]
                        print(f"📊 Current total tokens: {total_tokens}")

                    if "summary_instruction" in gpt_resp:
                        runtime = time.time() - start_time
                        metadata = create_metadata(
                            persona, url, orig, aug, gpt_resp['summary_instruction'],
                            [step['step'] for step in task_summarizer],
                            True, step_idx, runtime, total_tokens, page
                        )
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
                    description = gpt_resp["description"]
                    code = gpt_resp["code"]
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
                            with open(os.path.join(dirs['axtree'], f"{step_idx:04d}.json"), 'w', encoding='utf-8') as f:
                                json.dump(tree, f, indent=2, ensure_ascii=False)
                            # Update trajectory.json with the successful step
                            update_trajectory(
                                dirs=dirs,
                                step_idx=step_idx,
                                screenshot=screenshot,
                                axtree=os.path.join(dirs['axtree'], f"{step_idx:04d}.json"),
                                action_code=code,
                                action_description=description,
                                page=page
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

                                if "summary_instruction" in gpt_resp:
                                    runtime = time.time() - start_time
                                    metadata = create_metadata(
                                        persona, url, orig, aug, gpt_resp['summary_instruction'],
                                        [step['step'] for step in task_summarizer],
                                        True, step_idx, runtime, total_tokens, page
                                    )
                                    with open(os.path.join(dirs['root'], 'metadata.json'), 'w', encoding='utf-8') as f:
                                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                                    # Generate HTML after metadata is created
                                    generate_trajectory_html(dirs, metadata)
                                    print("✅ Task completed on retry, metadata saved.")
                                    should_continue = False
                                    break
                                if "updated_goal" in gpt_resp:
                                    current_goal = gpt_resp["updated_goal"]
                                description = gpt_resp["description"]
                                code = gpt_resp["code"]
                            else:
                                print(f"❌ All {MAX_RETRIES} retries failed.")
                                runtime = time.time() - start_time
                                metadata = create_metadata(
                                    persona, url, orig, aug, None,  # Pass None for final_instruction
                                    [step['step'] for step in task_summarizer],
                                    False, step_idx, runtime, total_tokens, page
                                )
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

                page.close()
                if MODE == 1:
                    input("🔚 Press Enter to continue...")
        finally:
            input("🔚 Press Enter to close browser...")
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

    # Start building HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visualization of Trajectory</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1, h2 {{
            color: #333;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }}
        .metadata {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .metadata-item {{
            margin: 10px 0;
        }}
        .metadata-label {{
            font-weight: bold;
            color: #555;
        }}
        .step {{
            border: 1px solid #ddd;
            margin: 20px 0;
            padding: 15px;
            border-radius: 5px;
            background-color: white;
        }}
        .step-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .step-number {{
            font-size: 1.2em;
            font-weight: bold;
            color: #2196F3;
        }}
        .step-content {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .screenshot {{
            max-width: 100%;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        .action-details {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
        }}
        .element-properties {{
            margin-top: 10px;
            padding: 10px;
            background-color: #fff;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        .property {{
            margin: 5px 0;
        }}
        .property-label {{
            font-weight: bold;
            color: #555;
        }}
        .bbox {{
            background-color: #e3f2fd;
            padding: 5px;
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Visualization of Trajectory</h1>
        
        <div class="metadata">
            <h2>Metadata</h2>
            <div class="metadata-item">
                <span class="metadata-label">Episode Name:</span> {metadata['eps_name']}
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Start URL:</span> {metadata['start_url']}
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Phase:</span> {metadata['phase']}
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Browser Context:</span>
                <ul>
                    <li>OS: {metadata['browser_context']['os']}</li>
                    <li>Viewport: {metadata['browser_context']['viewport']}</li>
                    <li>Cookies Enabled: {metadata['browser_context']['cookies_enabled']}</li>
                </ul>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Task:</span>
                <ul>
                    <li>Type: {metadata['task']['task_type']}</li>
                    <li>Persona: {metadata['task']['persona']}</li>
                    <li>Instructions:
                        <ul>
                            <li>Level 1: {metadata['task']['instruction']['level1']}</li>
                            <li>Level 2: {metadata['task']['instruction']['level2']}</li>
                            <li>Level 3: {metadata['task']['instruction']['level3']}</li>
                        </ul>
                    </li>
                </ul>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Execution:</span>
                <ul>
                    <li>Success: {metadata['success']}</li>
                    <li>Total Steps: {metadata['total_steps']}</li>
                    <li>Runtime: {metadata['runtime_sec']:.2f} seconds</li>
                    <li>Total Tokens: {metadata['total_tokens']}</li>
                </ul>
            </div>
        </div>

        <h2>Trajectory Steps</h2>
"""

    # Add each step to the HTML
    for step_num, step_data in trajectory.items():
        screenshot_path = os.path.join('images', step_data['screenshot'])
        action = step_data['action']
        action_output = action.get('action_output', {})
        
        html_content += f"""
        <div class="step">
            <div class="step-header">
                <span class="step-number">Step {step_num}</span>
                <span class="action-type">{action['action_type'].upper()}</span>
            </div>
            <div class="step-content">
                <div>
                    <img src="{screenshot_path}" alt="Step {step_num} Screenshot" class="screenshot">
                </div>
                <div class="action-details">
                    <div class="property">
                        <span class="property-label">Action Code:</span><br>
                        <code>{action['action_code']}</code>
                    </div>
                    <div class="property">
                        <span class="property-label">Description:</span><br>
                        {action['action_description']}
                    </div>
                    <div class="element-properties">
                        <h3>Element Properties</h3>
"""
        
        if action_output:
            if 'bbox' in action_output:
                html_content += f"""
                        <div class="property">
                            <span class="property-label">Bounding Box:</span>
                            <div class="bbox">
                                x: {action_output['bbox']['x']}, 
                                y: {action_output['bbox']['y']}, 
                                width: {action_output['bbox']['width']}, 
                                height: {action_output['bbox']['height']}
                            </div>
                        </div>"""
            
            for prop in ['class', 'id', 'type', 'ariaLabel', 'role', 'value']:
                if prop in action_output and action_output[prop]:
                    html_content += f"""
                        <div class="property">
                            <span class="property-label">{prop}:</span> {action_output[prop]}
                        </div>"""
            
            if 'text' in action_output:
                html_content += f"""
                        <div class="property">
                            <span class="property-label">Text:</span> {action_output['text']}
                        </div>"""
            
            if 'key' in action_output:
                html_content += f"""
                        <div class="property">
                            <span class="property-label">Key Pressed:</span> {action_output['key']}
                        </div>"""
            
            if 'timestamp' in action_output:
                html_content += f"""
                        <div class="property">
                            <span class="property-label">Timestamp:</span> {action_output['timestamp']}
                        </div>"""

        html_content += """
                    </div>
                </div>
            </div>
        </div>"""

    # Close HTML
    html_content += """
    </div>
</body>
</html>"""

    # Write HTML file
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


if __name__ == "__main__":
    main()