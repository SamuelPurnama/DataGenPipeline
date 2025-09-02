import json
from playwright.sync_api import sync_playwright, TimeoutError
import os
import sys
import uuid
import shutil
import time
from typing import Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import html
import re
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.new_generate_trajectory import chat_ai_playwright_code
from config import RESULTS_DIR, ACCOUNTS, BROWSER_SESSIONS_DIR
from utils.google_auth import ensure_google_login
from utils.trajectory_file_utils import (
    create_episode_directory, create_trajectory_file, create_error_log_file,
    update_playwright_error_log, update_trajectory, create_metadata,
    write_user_message, generate_trajectory_html
)
from utils.element_utils import (
    get_comprehensive_element_data, create_simplified_element_summary,
    try_alternative_selectors, annotate_screenshot_with_bounding_boxes,
    get_all_open_tabs, check_for_new_tabs, switch_to_new_tab
)

# Load environment variables from .env file
load_dotenv()

# Knowledge base client for trajectory context
from utils.knowledge_base_client import get_trajectory_context


# ========== CONFIGURABLE PARAMETERS ==========
PHASE = 1
MAX_RETRIES = 2
MAX_STEPS = 40  # Maximum number of steps before failing
ACTION_TIMEOUT = 10000  # 10 seconds timeout for actions
# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0

# Knowledge base configuration
MAX_CONTEXT_LENGTH = int(os.getenv("MAX_CONTEXT_LENGTH", "3000"))  # Maximum context length in characters
KNOWLEDGE_BASE_TYPE = os.getenv("KNOWLEDGE_BASE_TYPE", "graphrag")  # Type of knowledge base to use

# Directory to store all browser sessions
os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)


def fetch_trajectory_nodes(
    instruction: str,
    max_results: int = 3,
    max_context_length: int = 3000
) -> str:
    """
    Fetch relevant past trajectory nodes from vector database and extract steps/codes for LLM context.
    Uses modular vector database client that supports multiple database types.
    """
    return get_trajectory_context(
        query=instruction,
        max_results=max_results,
        max_context_length=max_context_length,
        kb_type=KNOWLEDGE_BASE_TYPE
    )
    
def generate_trajectory_loop(user_data_dir, chrome_path, phase, start_idx, end_idx, email: Optional[str] = None, password: Optional[str] = None, search_context: bool = False):
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
            
            # Set up monitoring for this browser session

            
            for idx, item in enumerate(all_instructions[start_idx:end_idx], start=start_idx):
                persona = item['persona']
                url = item['url']
                orig = item['original_instruction']
                aug = item['augmented_instruction']
                eps_name = f"calendar_{uuid.uuid4()}"
                dirs = create_episode_directory(RESULTS_DIR, eps_name)
                create_trajectory_file(dirs)  # Create empty trajectory.json
                create_error_log_file(dirs)   # Create empty error_log.json

                print(f"\n🔄 Instruction {idx + 1}/{total}")
                print(f"👤 {persona}")
                print(f"🌐 {url}")
                print(f"📝 Orig: {orig}")
                print(f"🔄 Aug: {aug}")
                print(f"UUID: {eps_name}")

                # Fetch relevant past trajectories for context (if enabled)
                trajectory_context = ""
                if search_context:
                    print("🔍 Fetching relevant past trajectories...")
                    trajectory_context = fetch_trajectory_nodes(aug, max_results=3, max_context_length=MAX_CONTEXT_LENGTH)
                    if trajectory_context:
                        print("✅ Found relevant past trajectories")
                        print("📄 Full trajectory context:")
                        print("=" * 50)
                        print(trajectory_context)
                        print("=" * 50)
                    else:
                        print("ℹ️ No relevant past trajectories found")

                # Navigate to URL for this instruction
                page.goto(url)
                
                # Handle login using the new module
                ensure_google_login(page, email, password, url)

                execution_history = []
                task_summarizer = []
                current_goal = aug
                should_continue = True
                start_time = time.time()
                total_tokens = 0  # Initialize token counter
                
                # Track initial URL for reference
                initial_url = page.url
                print(f"📍 Starting URL: {initial_url}")
                
                # Initialize tab tracking
                initial_tabs = get_all_open_tabs(browser)
                previous_tab_count = len(initial_tabs)
                previous_tab_urls = {tab['url'] for tab in initial_tabs}
                print(f"📑 Initial tabs: {previous_tab_count}")

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
                    annotated_screenshot = os.path.join(dirs['annotated_images'], f"annotated_screenshot_{step_idx+1:03d}.png")
                    axtree_file = os.path.join(dirs['axtree'], f"axtree_{step_idx+1:03d}.txt")
                    targeting_data_file = os.path.join(dirs['targeting_data'], f"targeting_data_{step_idx+1:03d}.json")
                    try:
                        page.screenshot(path=screenshot)
                        
                        # Get comprehensive element data instead of just accessibility tree
                        print(f"🔍 Collecting comprehensive element data for step {step_idx+1}...")
                        comprehensive_data = get_comprehensive_element_data(page, url)
                        
                        # Create simplified element data for axtree file and GPT
                        elements_data = create_simplified_element_summary(comprehensive_data['targeting_data'])
                        
                        # Use simplified data as the "tree"
                        tree = elements_data
                        
                        # Save simplified element data to axtree file (just annotation_id, role, name)
                        with open(axtree_file, 'w', encoding='utf-8') as f:
                            json.dump(elements_data, f, indent=2, ensure_ascii=False)
                        
                        # Save only the targeting data (not the entire comprehensive_data)
                        with open(targeting_data_file, 'w', encoding='utf-8') as f:
                            json.dump(comprehensive_data['targeting_data'], f, indent=2, ensure_ascii=False)
                        
                        # Create annotated screenshot with bounding boxes
                        print(f"🎨 Creating annotated screenshot with bounding boxes...")
                        annotated_path = annotate_screenshot_with_bounding_boxes(
                            screenshot, 
                            comprehensive_data['targeting_data'], 
                            annotated_screenshot
                        )
                        
                        print(f"✅ Saved comprehensive data: {len(comprehensive_data['interactive_elements'])} interactive elements, {len(comprehensive_data['targeting_data'])} targeting strategies")
                        
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

                    # Use the targeting data as the tree (no filtering needed)
                    filtered_tree = tree
                    

                    # Prepare context with past trajectories
                    enhanced_context = ""
                    if trajectory_context:
                        enhanced_context = f"\n\n{trajectory_context}\n\n"
                    
                    # Create structured JSON element summary for GPT
                    element_summary = ""
                    if comprehensive_data and 'targeting_data' in comprehensive_data:
                        # Use the function to create simplified element data
                        elements_data = create_simplified_element_summary(comprehensive_data['targeting_data'])
                        
                        # Convert to JSON string
                        element_summary = f"\n\nAvailable Interactive Elements:\n{json.dumps(elements_data, indent=2)}\n\n"
                    
                    # Save the minimal summary that gets sent to GPT for debugging
                    gpt_summary_file = os.path.join(dirs['gpt_summaries'], f'gpt_summary_step_{step_idx}.txt')
                    with open(gpt_summary_file, 'w', encoding='utf-8') as f:
                        f.write(f"Step: {step_idx}\n")
                        f.write(f"Current Goal: {current_goal}\n")
                        f.write(f"URL: {url}\n")
                        f.write(f"Task Goal: {aug}\n")
                        f.write(f"Trajectory Context: {enhanced_context}\n")
                        f.write(f"Element Summary Sent to GPT:\n{element_summary}")
                    print(f"📝 Saved GPT summary for debugging: {gpt_summary_file}")
                    
                    gpt_resp = chat_ai_playwright_code(
                        previous_steps=execution_history,
                        taskGoal=aug,
                        taskPlan=current_goal,
                        image_path=screenshot,  # Pass only the clean screenshot
                        failed_codes=[],
                        is_deletion_task=is_del,
                        url=url,
                        trajectory_context=enhanced_context,
                        targeting_data=element_summary
                    )

                    # Print GPT response
                    print(f"\n🤖 GPT Response:")
                    print(f"Description: {gpt_resp.get('description', 'No description') if gpt_resp else 'No response'}")
                    print(f"Code: {gpt_resp.get('code', 'No code') if gpt_resp else 'No response'}")
                    if gpt_resp and 'selected_annotation_id' in gpt_resp:
                        print(f"Selected Element ID: {gpt_resp['selected_annotation_id']}")
                    if gpt_resp and 'thought' in gpt_resp:
                        print(f"Thought: {gpt_resp['thought']}")
                    print(f"Full Response: {json.dumps(gpt_resp, indent=2) if gpt_resp else 'No response'}")

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
                    failed_attempts_details = []  # Track detailed info about each failed attempt
                    retry = 0
                    description = gpt_resp["description"] if gpt_resp else ""
                    code = gpt_resp.get("code", "") if gpt_resp else ""
                    success = False

                    while retry < MAX_RETRIES and not success:
                        try:
                            print(f"🤖 {description}")
                            print(f"🔄 Code: {code}")
                            print(f"🔄 Failed Codes: {failed_codes}")
                            
                            # Execute the Playwright code directly
                            if "page." in code:
                                # Execute Playwright code directly (sync version)
                                exec(code)
                            else:
                                # For non-Playwright code, execute normally
                                exec(code)
                            
                            # ALWAYS record the successful step first (regardless of new tabs)
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
                                llm_output=gpt_resp,
                                targeting_data_file=targeting_data_file,
                                annotation_id=gpt_resp.get('selected_annotation_id') if gpt_resp else None
                            )
                            
                            # Simple tab switching: after successful execution, check for new tabs
                            print("🔍 Checking for new tabs after successful action execution...")
                            print(f"   Previous tab count: {previous_tab_count}")
                            print(f"   Previous tab URLs: {list(previous_tab_urls)[:3]}...")  # Show first 3 URLs
                            
                            has_new_tabs, new_tabs, current_tab_count = check_for_new_tabs(
                                browser, previous_tab_count, previous_tab_urls
                            )
                            
                            if has_new_tabs:
                                print(f"🆕 New tabs detected! Switching to new tab and restarting loop...")
                                print(f"   New tabs: {[tab['domain'] for tab in new_tabs]}")
                                print(f"   Current tab count: {current_tab_count}")
                                
                                # Wait a few seconds for the new tab to stabilize
                                print("⏳ Waiting 8 seconds for new tab to stabilize...")
                                time.sleep(8)
                                
                                # Switch to the new tab
                                success, new_page = switch_to_new_tab(new_tabs, page)
                                
                                if success:
                                    # Update our page reference and tracking variables
                                    page = new_page
                                    previous_tab_count = current_tab_count
                                    previous_tab_urls = {tab['url'] for tab in get_all_open_tabs(browser)}
                                    
                                    # Update the URL variable so GPT gets the correct context
                                    url = page.url
                                    print(f"🌐 Updated URL context to: {url}")
                                    
                                    print(f"🚀 Successfully switched to new tab: {page.url}")
                                    print("🔄 Restarting loop to take screenshot and collect elements on new tab...")
                                    
                                    # Mark as successful to exit retry loop
                                    success = True
                                    break
                                else:
                                    print("⚠️  Failed to switch to new tab, continuing with current page")
                                    # Update tracking even if switch failed
                                    previous_tab_count = current_tab_count
                                    previous_tab_urls = {tab['url'] for tab in get_all_open_tabs(browser)}
                            else:
                                print("✅ No new tabs detected, continuing with current page")
                                # Only record the step if we didn't switch to a new tab
                                # Log successful solution with all failed attempts history
                                if retry > 0:
                                    update_playwright_error_log(
                                        dirs=dirs,
                                        step_idx=step_idx,
                                        description=description,
                                        attempted_code="",  # Not needed for successful solution
                                        error_message="Previous attempts failed",
                                        successful_code=code,
                                        thought=gpt_resp.get('thought', '') if gpt_resp else '',
                                        current_goal=current_goal,
                                        all_failed_attempts=failed_attempts_details
                                    )
                                success = True
                        except Exception as e:
                            print(f"⚠️ Attempt {retry + 1} failed: {e}")
                            

                            
                            # Try alternative selectors from targeting data if this is a Playwright error
                            if "page." in code and retry == 0:
                                print("🔄 Trying alternative Playwright selectors...")
                                success, failed_alternatives, successful_fallback_code = try_alternative_selectors(
                                    page, code, comprehensive_data, gpt_resp
                                )
                                
                                if success:
                                    print("✅ Alternative selector succeeded!")
                                    print(f"🔄 Fallback code that worked: {successful_fallback_code}")
                                    # Use the successful fallback code instead of the original GPT code
                                    working_code = successful_fallback_code
                                    

                                    
                                    # Simple tab switching: after successful alternative execution, check for new tabs
                                    print("🔍 Checking for new tabs after successful alternative action execution...")
                                    print(f"   Previous tab count: {previous_tab_count}")
                                    print(f"   Previous tab URLs: {list(previous_tab_urls)[:3]}...")  # Show first 3 URLs
                                    
                                    has_new_tabs, new_tabs, current_tab_count = check_for_new_tabs(
                                        browser, previous_tab_count, previous_tab_urls
                                    )
                                    
                                    if has_new_tabs:
                                        print(f"🆕 New tabs detected! Switching to new tab and restarting loop...")
                                        print(f"   New tabs: {[tab['domain'] for tab in new_tabs]}")
                                        print(f"   Current tab count: {current_tab_count}")
                                        
                                        # Wait a few seconds for the new tab to stabilize
                                        print("⏳ Waiting 5 seconds for new tab to stabilize...")
                                        time.sleep(5)
                                        
                                        # Switch to the new tab
                                        success, new_page = switch_to_new_tab(new_tabs, page)
                                        
                                        if success:
                                            # Update our page reference and tracking variables
                                            page = new_page
                                            previous_tab_count = current_tab_count
                                            previous_tab_urls = {tab['url'] for tab in get_all_open_tabs(browser)}
                                            
                                            # Update the URL variable so GPT gets the correct context
                                            url = page.url
                                            print(f"🌐 Updated URL context to: {url}")
                                            
                                            print(f"🚀 Successfully switched to new tab: {page.url}")
                                            print("🔄 Restarting loop to take screenshot and collect elements on new tab...")
                                            
                                            # Mark as successful to exit retry loop
                                            success = True
                                            break
                                        else:
                                            print("⚠️  Failed to switch to new tab, continuing with current page")
                                            # Update tracking even if switch failed
                                            previous_tab_count = current_tab_count
                                            previous_tab_urls = {tab['url'] for tab in get_all_open_tabs(browser)}
                                    else:
                                        # Only record the step if we didn't switch to a new tab
                                        execution_history.append({'step': description, 'code': working_code, 'note': 'fallback_selector_used'})
                                        task_summarizer.append({'step': description, 'code': working_code, 'axtree': tree})
                                        # Save axtree to file after successful alternative execution
                                        with open(axtree_file, 'w', encoding='utf-8') as f:
                                            json.dump(tree, f, indent=2, ensure_ascii=False)
                                        # Update trajectory.json with the successful alternative step
                                        update_trajectory(
                                            dirs=dirs,
                                            step_idx=step_idx,
                                            screenshot=screenshot,
                                            axtree=axtree_file,
                                            action_code=working_code,
                                            action_description=description,
                                            page=page,
                                            user_message_file=os.path.join(dirs['user_message'], f"user_message_{step_idx+1:03d}.txt"),
                                            llm_output=gpt_resp,
                                            targeting_data_file=targeting_data_file,
                                            annotation_id=gpt_resp.get('selected_annotation_id') if gpt_resp else None
                                        )
                                        success = True
                                        break
                                else:
                                    # Add all failed alternatives to failed_codes so GPT knows not to try them
                                    print(f"📝 Adding {len(failed_alternatives)} failed alternatives to failed_codes")
                                    for alt_code in failed_alternatives:
                                        if alt_code not in failed_codes:
                                            failed_codes.append(alt_code)
                            
                            retry += 1
                            if code not in failed_codes:
                                failed_codes.append(code)
                            
                            # Track detailed info about this failed attempt
                            failed_attempt_details = {
                                "attempt_number": retry,
                                "code": code,
                                "error_message": str(e),
                                "thought": gpt_resp.get('thought', '') if gpt_resp else '',
                                "description": description
                            }
                            failed_attempts_details.append(failed_attempt_details)
                            
                            # Log the individual Playwright execution error
                            update_playwright_error_log(
                                dirs=dirs,
                                step_idx=step_idx,
                                description=description,
                                attempted_code=code,
                                error_message=str(e),
                                thought=gpt_resp.get('thought', '') if gpt_resp else '',
                                current_goal=current_goal
                            )
                            
                            if retry < MAX_RETRIES:
                                print("🔄 Retrying GPT for new code...")
                                page.screenshot(path=screenshot)
                                
                                # Get comprehensive element data for retry
                                print(f"🔍 Collecting comprehensive element data for retry {retry + 1}...")
                                comprehensive_data = get_comprehensive_element_data(page, url)
                                
                                # Create simplified element data for axtree file and GPT
                                elements_data = create_simplified_element_summary(comprehensive_data['targeting_data'])
                                
                                # Use simplified data as the "tree"
                                tree = elements_data
                                
                                # Save simplified element data to axtree file for retry
                                with open(axtree_file, 'w', encoding='utf-8') as f:
                                    json.dump(elements_data, f, indent=2, ensure_ascii=False)
                                
                                # Save the comprehensive targeting data
                                with open(targeting_data_file, 'w', encoding='utf-8') as f:
                                    json.dump(comprehensive_data, f, indent=2, ensure_ascii=False)
                                
                                # Create annotated screenshot for retry
                                print(f"🎨 Creating annotated screenshot for retry {retry + 1}...")
                                annotated_path = annotate_screenshot_with_bounding_boxes(
                                    screenshot, 
                                    comprehensive_data['targeting_data'], 
                                    annotated_screenshot
                                )
                                
                                error_log = str(e)
                                print(f"📝 Error log: {error_log}")
                                
                                # Use the targeting data as the tree (no filtering needed)
                                filtered_tree = tree
                                
                                # Prepare context with past trajectories for retry
                                enhanced_context = ""
                                if trajectory_context:
                                    enhanced_context = f"\n\n{trajectory_context}\n\n"
                                
                                # Create minimal element summary for GPT retry (just annotation ID, role, name)
                                element_summary = ""
                                if comprehensive_data and 'targeting_data' in comprehensive_data:
                                    element_summary = "\n\nAvailable Interactive Elements:\n"
                                    for elem in comprehensive_data['targeting_data']:
                                        annotation_id = elem.get('annotation_id', '?')
                                        role = elem.get('element_info', {}).get('role', 'unknown')
                                        name = elem.get('element_info', {}).get('name', 'unnamed')
                                        element_summary += f"  {annotation_id}. {role}: {name}\n"
                                    element_summary += "\n"
                                
                                gpt_resp = chat_ai_playwright_code(
                                        previous_steps=execution_history,
                                        taskGoal=aug,
                                        taskPlan=current_goal,
                                        image_path=screenshot,  # Pass only the clean screenshot
                                        failed_codes=failed_codes,
                                        is_deletion_task=is_del,
                                        url=url,
                                        error_log=error_log,
                                        trajectory_context=enhanced_context,
                                        targeting_data=element_summary
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
                                code = gpt_resp.get("code", "") if gpt_resp else ""
                            else:
                                print(f"❌ All {MAX_RETRIES} retries failed.")
                                # Log final Playwright failure
                                update_playwright_error_log(
                                    dirs=dirs,
                                    step_idx=step_idx,
                                    description=description,
                                    attempted_code=code,
                                    error_message=f"All {MAX_RETRIES} retries failed",
                                    thought=gpt_resp.get('thought', '') if gpt_resp else '',
                                    current_goal=current_goal
                                )
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

def run_for_account(account, chrome_path, phase, search_context: bool = True):
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
        password=account["password"],
        search_context=search_context
    )

def main():
    chrome_exec = os.getenv("CHROME_EXECUTABLE_PATH")
    phase = PHASE
    
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        futures = [
            executor.submit(run_for_account, account, chrome_exec, phase, search_context=True)
            for account in ACCOUNTS
        ]
        for future in futures:
            future.result()  # Wait for all to finish



if __name__ == "__main__":
    main() 