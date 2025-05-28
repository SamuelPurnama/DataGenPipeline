from playwright.sync_api import sync_playwright, TimeoutError
import json
import os
import uuid
import shutil
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

from generate_trajectory import chat_ai_playwright_code
from config import RESULTS_DIR

# ========== CONFIGURABLE PARAMETERS ==========
PHASE = 1
MAX_RETRIES = 7
MAX_STEPS = 25  # Maximum number of steps before failing
ACTION_TIMEOUT = 30000  # 30 seconds timeout for actions
# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0

# Directory to store all browser sessions
BROWSER_SESSIONS_DIR = "browser_sessions"
os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)

# ========== ACCOUNTS CONFIGURATION ==========
# Fill in your Google accounts and unique user data directories here
ACCOUNTS = [
    {
        "email": "example1@gmail.com",
        "password": "password1",
        "user_data_dir": "example1",
        "start_idx": 0,
        "end_idx": 5
    },
    {
        "email": "example2@gmail.com",
        "password": "password2",
        "user_data_dir": "example2",
        "start_idx": 5,
        "end_idx": 10
    },
    # Add more accounts as needed
]
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
                run_uuid = str(uuid.uuid4())
                inst_dir = os.path.join(RESULTS_DIR, run_uuid)
                os.makedirs(inst_dir, exist_ok=True)

                print(f"\n🔄 Instruction {idx + 1}/{total}")
                print(f"👤 {persona}")
                print(f"🌐 {url}")
                print(f"📝 Orig: {orig}")
                print(f"🔄 Aug: {aug}")
                print(f"UUID: {run_uuid}")

                page = browser.new_page()
                page.set_default_timeout(ACTION_TIMEOUT)
                page.goto(url)
                
                # Handle login if credentials are provided
                if email and password and 'scholar.google.com' not in url:
                    print("🔑 Checking login status...")
                    if not handle_google_login(page, email, password):
                        print("❌ Automatic login failed, please login manually")
                        page.wait_for_selector('[aria-label*="Google Account"]', timeout=300000)
                else:
                    # Only wait for Google Account if it's not Scholar
                    if 'scholar.google.com' not in url:
                        page.wait_for_selector('[aria-label*="Google Account"]', timeout=300000)
                    else:
                        # For Scholar, just wait for the search box
                        page.wait_for_selector('input[name="q"]', timeout=300000)

                execution_history = []
                task_summarizer = []
                current_goal = aug
                should_continue = True

                while should_continue:
                    step_idx = len(task_summarizer)

                    if step_idx >= MAX_STEPS:
                        print(f"❌ Maximum number of steps ({MAX_STEPS}) exceeded. Creating failure summary.")
                        summary = {
                            "persona": persona,
                            "original_instruction": orig,
                            "augmented_instruction": aug,
                            "url": url,
                            "final_instruction": current_goal,
                            "task_steps": task_summarizer,
                            "success": False,
                            "failure_reason": f"Exceeded maximum steps ({MAX_STEPS})"
                        }
                        with open(os.path.join(inst_dir, "task_summarizer.json"), "w", encoding="utf-8") as f:
                            json.dump(summary, f, indent=2, ensure_ascii=False)
                        should_continue = False
                        break

                    screenshot = os.path.join(inst_dir, f"step_{step_idx}.png")
                    page.screenshot(path=screenshot)
                    tree = page.accessibility.snapshot()
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

                    if "summary_instruction" in gpt_resp:
                        summary = {
                            "persona": persona,
                            "original_instruction": orig,
                            "augmented_instruction": aug,
                            "final_instruction": gpt_resp['summary_instruction'],
                            "url": url,
                            "task_steps": task_summarizer,
                            "success": True
                        }
                        if "output" in gpt_resp:
                            summary["output"] = gpt_resp["output"]
                        with open(os.path.join(inst_dir, "task_summarizer.json"), "w", encoding="utf-8") as f:
                            json.dump(summary, f, indent=2, ensure_ascii=False)
                        print("✅ Task completed, summary saved.")
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
                            execution_history.append({'step': description, 'code': code})
                            task_summarizer.append({'step': description, 'code': code, 'axtree': tree})
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
                                if "summary_instruction" in gpt_resp:
                                    summary = {
                                        "persona": persona,
                                        "original_instruction": orig,
                                        "augmented_instruction": aug,
                                        "url": url,
                                        "final_instruction": gpt_resp['summary_instruction'],
                                        "task_steps": task_summarizer,
                                        "success": True
                                    }
                                    if "output" in gpt_resp:
                                        summary["output"] = gpt_resp["output"]
                                    with open(os.path.join(inst_dir, "task_summarizer.json"), "w", encoding="utf-8") as f:
                                        json.dump(summary, f, indent=2, ensure_ascii=False)
                                    print("✅ Task completed on retry, summary saved.")
                                    should_continue = False
                                    break
                                if "updated_goal" in gpt_resp:
                                    current_goal = gpt_resp["updated_goal"]
                                description = gpt_resp["description"]
                                code = gpt_resp["code"]
                            else:
                                print(f"❌ All {MAX_RETRIES} retries failed; creating failure summary.")
                                summary = {
                                    "persona": persona,
                                    "original_instruction": orig,
                                    "augmented_instruction": aug,
                                    "url": url,
                                    "final_instruction": current_goal,
                                    "task_steps": task_summarizer,
                                    "success": False
                                }
                                with open(os.path.join(inst_dir, "task_summarizer.json"), "w", encoding="utf-8") as f:
                                    json.dump(summary, f, indent=2, ensure_ascii=False)
                                should_continue = False
                                break

                    if success:
                        page.wait_for_timeout(2000)
                    else:
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

if __name__ == "__main__":
    main()