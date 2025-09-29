import json
from playwright.sync_api import sync_playwright, TimeoutError
import os
import sys
import uuid
import time
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from urllib.parse import urlparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.ocr_generate_trajectory import chat_ai_playwright_code_ocr
from config import RESULTS_DIR, ACCOUNTS, BROWSER_SESSIONS_DIR, TOTAL_PERSONAS, PHASE1_INSTRUCTIONS_PER_PERSONA, PHASE2_INSTRUCTIONS_PER_PERSONA
from utils.google_auth import ensure_google_login
from utils.trajectory_file_utils import (
    create_episode_directory, create_trajectory_file, create_error_log_file,
    update_playwright_error_log, update_trajectory, create_metadata,
    write_user_message, generate_trajectory_html, get_site_name_from_url
)
from utils.progress_tracker import ProgressTracker
from utils.element_utils import (
    get_all_open_tabs, check_for_new_tabs, switch_to_new_tab
)

# Knowledge base client for trajectory context
from utils.knowledge_base_client import get_trajectory_context

# Validation utilities (disabled for OCR approach)
# from utils.confidence_validation import process_confidence_validation
# from utils.post_action_validation import process_post_action_validation

# OCR utilities
from paddleocr import PaddleOCR

# Image processing utilities
from PIL import Image, ImageDraw, ImageFont

# Load environment variables from .env file
load_dotenv()

# Initialize OCR instance
ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False)


def execute_ocr_action(page, gpt_resp, elements_data):
    """
    Execute action using OCR coordinates instead of generated code.
    """
    if not gpt_resp or not elements_data:
        raise Exception("Missing GPT response or elements data")
    
    selected_element_id = gpt_resp.get("selected_annotation_id") or gpt_resp.get("selected_element_id")
    action_type = gpt_resp.get("action_type", "click")
    
    # Handle wait actions (no element ID needed)
    if action_type == "wait":
        print(f"🎯 Executing wait action")
        page.wait_for_timeout(2000)  # Wait for 2 seconds by default
        print(f"✅ Waited for 2 seconds")
        return
    
    if selected_element_id is None:
        raise Exception("No selected_annotation_id or selected_element_id in GPT response")
    
    # Find the element in OCR data
    target_element = None
    print(f"🔍 Looking for element ID: {selected_element_id} (type: {type(selected_element_id)})")
    print(f"🔍 Available elements: {[elem.get('annotation_id') for elem in elements_data.get('elements', [])]}")
    
    for element in elements_data.get("elements", []):
        element_id = element.get("annotation_id")
        print(f"🔍 Comparing {selected_element_id} (type: {type(selected_element_id)}) with {element_id} (type: {type(element_id)})")
        # Handle both string and integer comparisons
        if (element_id == selected_element_id or 
            str(element_id) == str(selected_element_id) or
            int(element_id) == int(selected_element_id)):
            target_element = element
            break
    
    if not target_element:
        raise Exception(f"Element ID {selected_element_id} not found in OCR data")
    
    # Get click coordinates
    click_coords = target_element.get("click_coordinates", {})
    click_x = click_coords.get("x")
    click_y = click_coords.get("y")
    
    if click_x is None or click_y is None:
        raise Exception(f"No click coordinates found for element ID {selected_element_id}")
    
    print(f"🎯 Executing {action_type} at coordinates ({click_x}, {click_y})")
    
    # Perform the action
    if action_type == "click":
        page.mouse.click(click_x, click_y)
        print(f"✅ Clicked at ({click_x}, {click_y})")
        
    elif action_type == "fill":
        # Type directly without clicking first
        page.keyboard.type("TEXT_TO_FILL")
        print(f"✅ Filled 'TEXT_TO_FILL'")
        
    else:
        raise Exception(f"Unknown action_type: {action_type}")


def generate_action_code_from_ocr(gpt_resp, elements_data):
    """
    Generate a readable action code string from OCR response for logging purposes.
    """
    if not gpt_resp or not elements_data:
        return "No action data"
    
    selected_element_id = gpt_resp.get("selected_annotation_id") or gpt_resp.get("selected_element_id")
    action_type = gpt_resp.get("action_type", "click")
    
    # Handle wait actions (no element needed)
    if action_type == "wait":
        return f"page.wait_for_timeout(2000)  # Wait for page to load"
    
    # Find the element in OCR data
    target_element = None
    for element in elements_data.get("elements", []):
        element_id = element.get("annotation_id")
        # Handle both string and integer comparisons
        if (element_id == selected_element_id or 
            str(element_id) == str(selected_element_id) or
            int(element_id) == int(selected_element_id)):
            target_element = element
            break
    
    if not target_element:
        return f"Element ID {selected_element_id} not found"
    
    # Get click coordinates
    click_coords = target_element.get("click_coordinates", {})
    click_x = click_coords.get("x")
    click_y = click_coords.get("y")
    
    if action_type == "click":
        return f"page.mouse.click({click_x}, {click_y})  # Click on '{target_element.get('text', '')}'"
    elif action_type == "fill":
        return f"page.keyboard.type('TEXT_TO_FILL')  # Fill '{target_element.get('text', '')}' with 'TEXT_TO_FILL'"
    else:
        return f"Unknown action: {action_type}"


def update_trajectory_ocr(dirs: Dict[str, str], step_idx: int, screenshot: str, elements_data_file: str, 
                         action_code: str, action_description: str, page, user_message_file: str = None, 
                         llm_output=None, annotation_id: str = None) -> None:
    """Update trajectory.json with a new step using OCR-based elements."""
    trajectory_path = os.path.join(dirs['root'], 'trajectory.json')
    try:
        with open(trajectory_path, 'r', encoding='utf-8') as f:
            trajectory = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        trajectory = {}
    
    # Get current page information with safety checks
    try:
        current_url = page.url if hasattr(page, 'url') else "Unknown"
        page_title = page.title() if hasattr(page, 'title') else "Unknown"
        open_pages = page.context.pages if hasattr(page, 'context') else []
        open_pages_titles = [p.title() for p in open_pages] if open_pages else []
        open_pages_urls = [p.url for p in open_pages] if open_pages else []
    except Exception as e:
        print(f"⚠️  Error getting page info in update_trajectory_ocr: {e}")
        current_url = "Error getting URL"
        page_title = "Error getting title"
        open_pages_titles = []
        open_pages_urls = []
    
    # Load elements data and find element by annotation ID if available
    element_data = None
    if elements_data_file and annotation_id and os.path.exists(elements_data_file):
        try:
            with open(elements_data_file, 'r', encoding='utf-8') as f:
                elements_data = json.load(f)
            
            # Find element by annotation_id
            element_data = next((elem for elem in elements_data.get('elements', []) 
                               if str(elem.get('annotation_id', '')) == str(annotation_id)), None)
        except Exception as e:
            print(f"⚠️ Error loading elements data: {e}")
    
    # Extract action type from the code
    action_type = "unknown"
    if "page.mouse.click" in action_code:
        action_type = "click"
    elif "page.keyboard.type" in action_code:
        action_type = "fill"
    elif "page.wait_for_timeout" in action_code:
        action_type = "wait"
    
    # Get thought from LLM output
    thought = llm_output.get('thought', '') if llm_output else ''
    
    # Create step data
    step_data = {
        "step": step_idx + 1,
        "action": {
            "type": action_type,
            "description": action_description,
            "code": action_code,
            "thought": thought
        },
        "page": {
            "url": current_url,
            "title": page_title,
            "open_pages": {
                "titles": open_pages_titles,
                "urls": open_pages_urls
            }
        },
        "screenshot": screenshot,
        "elements_data_file": elements_data_file,
        "timestamp": datetime.now().isoformat()
    }
    
    # Add element data if found
    if element_data:
        step_data["element"] = {
            "annotation_id": element_data.get("annotation_id"),
            "text": element_data.get("text"),
            "confidence": element_data.get("confidence"),
            "bounding_box": element_data.get("bounding_box"),
            "click_coordinates": element_data.get("click_coordinates")
        }
    
    # Add LLM output if available
    if llm_output:
        step_data["llm_output"] = llm_output
    
    # Add user message if available
    if user_message_file and os.path.exists(user_message_file):
        try:
            with open(user_message_file, 'r', encoding='utf-8') as f:
                step_data["user_message"] = f.read()
        except Exception as e:
            print(f"⚠️ Error reading user message: {e}")
    
    # Initialize steps array if not exists
    if "steps" not in trajectory:
        trajectory["steps"] = []
    
    # Add the new step
    trajectory["steps"].append(step_data)
    
    # Save updated trajectory
    try:
        with open(trajectory_path, 'w', encoding='utf-8') as f:
            json.dump(trajectory, f, indent=2, ensure_ascii=False)
        print(f"✅ Updated trajectory.json with step {step_idx + 1}")
    except Exception as e:
        print(f"❌ Error saving trajectory: {e}")


# ========== CONFIGURABLE PARAMETERS ==========
# These parameters are set by the end_to_end_pipeline.py file
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
SEARCH_CONTEXT = False  # Whether to search for relevant past trajectories for context

# Directory to store all browser sessions
os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)


def generate_episode_name(url: str) -> str:
    """Generate a meaningful episode name based on URL and UUID."""
    site_name = get_site_name_from_url(url)
    return f"{site_name}_{uuid.uuid4()}"


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

def annotate_screenshot_with_ocr_boxes(screenshot_path: str, elements_data: dict, output_path: str) -> str:
    """
    Create an annotated screenshot with OCR bounding boxes.
    """
    try:
        # Load the screenshot
        image = Image.open(screenshot_path)
        draw = ImageDraw.Draw(image)
        
        # Try to use a default font, fallback to basic if not available
        try:
            font = ImageFont.load_default()
        except:
            font = None
        
        # Draw bounding boxes for each OCR element
        for element in elements_data.get('elements', []):
            bbox = element.get('bounding_box', {})
            text = element.get('text', '')
            annotation_id = element.get('annotation_id', '?')
            
            if bbox:
                x1, y1, x2, y2 = bbox['x1'], bbox['y1'], bbox['x2'], bbox['y2']
                
                # Draw bounding box
                draw.rectangle([x1, y1, x2, y2], outline='red', width=2)
                
                # Draw annotation ID and text
                label = f"{annotation_id}: {text}"
                if font:
                    draw.text((x1, y1 - 20), label, fill='red', font=font)
                else:
                    draw.text((x1, y1 - 20), label, fill='red')
        
        # Save the annotated image
        image.save(output_path)
        print(f"✅ Created annotated screenshot with OCR bounding boxes: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"❌ Error creating annotated screenshot: {e}")
        return screenshot_path


def get_ocr_element_data(screenshot_path: str) -> dict:
    """
    Get element data using OCR instead of comprehensive element detection.
    Returns organized JSON structure with text elements and bounding boxes.
    """
    try:
        print(f"🔍 Running OCR on screenshot: {screenshot_path}")
        result = ocr.predict(input=screenshot_path)
        
        # Process results and create organized JSON structure
        for res in result:
            # Create organized JSON structure
            organized_data = {
                "image_path": screenshot_path,
                "elements": []
            }
            
            # Access the data from the result object
            result_data = res.res if hasattr(res, 'res') else res
            
            # Combine text and bounding boxes into individual objects
            texts = result_data['rec_texts']
            boxes = result_data['rec_boxes'] 
            scores = result_data['rec_scores']
            
            for i, (text, box, score) in enumerate(zip(texts, boxes, scores)):
                x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
                
                # Calculate click coordinates (center of bounding box)
                click_x = (x1 + x2) // 2
                click_y = (y1 + y2) // 2
                
                text_element = {
                    "annotation_id": i,
                    "text": text,
                    "confidence": float(score),
                    "bounding_box": {
                        "x1": x1,
                        "y1": y1, 
                        "x2": x2,
                        "y2": y2
                    },
                    "click_coordinates": {
                        "x": click_x,
                        "y": click_y
                    }
                }
                organized_data["elements"].append(text_element)
            
            print(f"✅ OCR detected {len(organized_data['elements'])} text elements")
            return organized_data
            
    except Exception as e:
        print(f"❌ OCR failed: {e}")
        return {"image_path": screenshot_path, "elements": []}
    
def generate_trajectory_loop(user_data_dir, chrome_path, phase, start_idx, end_idx, email: Optional[str] = None, password: Optional[str] = None, progress_tracker=None):
        
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
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-fullscreen"
            ]
        )
        try:
            # Create page once at the start
            page = browser.new_page()
            page.set_default_timeout(ACTION_TIMEOUT)
            
            # Set mobile viewport for mobile view detection (optional)
            # Uncomment the line below to enable mobile viewport
            # page.set_viewport_size({"width": 375, "height": 667})  # iPhone SE size
            
            # Set up monitoring for this browser session

            
            for idx, item in enumerate(all_instructions[start_idx:end_idx], start=start_idx):
                persona = item['persona']
                url = item['url']
                orig = item['original_instruction']
                aug = item['augmented_instruction']
                eps_name = generate_episode_name(url)
                dirs = create_episode_directory(RESULTS_DIR, eps_name)
                create_trajectory_file(dirs)  # Create empty trajectory.json
                create_error_log_file(dirs)   # Create empty error_log.json

                print(f"\n🔄 Instruction {idx + 1}/{total}")
                print(f"👤 {persona}")
                print(f"🌐 {url}")
                print(f"📝 Orig: {orig}")
                print(f"🔄 Aug: {aug}")
                print(f"UUID: {eps_name}")
                
                # Start tracking this instruction
                if progress_tracker:
                    progress_tracker.start_instruction(email, idx, aug, eps_name)

                # Fetch relevant past trajectories for context (if enabled)
                trajectory_context = ""
                if SEARCH_CONTEXT:
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
                    
                    # Update progress tracker with current step
                    if progress_tracker:
                        progress_tracker.update_step(email, step_idx)
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
                        
                        # Mark instruction as failed in progress tracker
                        if progress_tracker:
                            progress_tracker.complete_instruction(email, idx, aug, eps_name, success=False, error_message=f"Maximum steps ({MAX_STEPS}) exceeded")
                        should_continue = False
                        break

                    screenshot = os.path.join(dirs['images'], f"screenshot_{step_idx+1:03d}.png")
                    annotated_screenshot = os.path.join(dirs['annotated_images'], f"annotated_screenshot_{step_idx+1:03d}.png")
                    axtree_file = os.path.join(dirs['axtree'], f"axtree_{step_idx+1:03d}.txt")
                    elements_data_file = os.path.join(dirs['targeting_data'], f"elements_data_{step_idx+1:03d}.json")
                    try:
                        page.screenshot(path=screenshot)
                        
                        # Get OCR-based element data instead of comprehensive element detection
                        print(f"🔍 Running OCR for step {step_idx+1}...")
                        elements_data = get_ocr_element_data(screenshot)
                        
                        # Use elements data as the "tree" for GPT
                        tree = elements_data
                        
                        # Save elements data to axtree file
                        with open(axtree_file, 'w', encoding='utf-8') as f:
                            json.dump(elements_data, f, indent=2, ensure_ascii=False)
                        
                        # Save elements data to targeting data file
                        with open(elements_data_file, 'w', encoding='utf-8') as f:
                            json.dump(elements_data, f, indent=2, ensure_ascii=False)
                        
                        # Create annotated screenshot with OCR bounding boxes
                        print(f"🎨 Creating annotated screenshot with OCR bounding boxes...")
                        annotated_path = annotate_screenshot_with_ocr_boxes(
                            screenshot, 
                            elements_data, 
                            annotated_screenshot
                        )
                        
                        print(f"✅ OCR detected {len(elements_data['elements'])} text elements")
                        
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
                    
                    # OCR data is passed directly to the GPT function
                    
                    # Save the minimal summary that gets sent to GPT for debugging
                    gpt_summary_file = os.path.join(dirs['gpt_summaries'], f'gpt_summary_step_{step_idx}.txt')
                    with open(gpt_summary_file, 'w', encoding='utf-8') as f:
                        f.write(f"Step: {step_idx}\n")
                        f.write(f"Current Goal: {current_goal}\n")
                        f.write(f"URL: {url}\n")
                        f.write(f"Task Goal: {aug}\n")
                        f.write(f"Trajectory Context: {enhanced_context}\n")
                        f.write(f"Elements Data Sent to GPT:\n{json.dumps(elements_data, indent=2) if elements_data else 'No elements data'}")
                    print(f"📝 Saved GPT summary for debugging: {gpt_summary_file}")
                    
                    gpt_resp = chat_ai_playwright_code_ocr(
                        previous_steps=execution_history,
                        taskGoal=aug,
                        taskPlan=current_goal,
                        image_path=screenshot,  # Pass only the clean screenshot
                        elements_data=elements_data,
                        failed_codes=[],
                        is_deletion_task=is_del,
                        url=url,
                        trajectory_context=enhanced_context,
                        session_dir=dirs['root']
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

                    # Confidence validation disabled for OCR approach

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
                        
                        # Mark instruction as completed in progress tracker
                        if progress_tracker:
                            progress_tracker.complete_instruction(email, idx, aug, eps_name, success=True)
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
                            print(f"🎯 Action: {gpt_resp.get('action_type', 'click')}")
                            print(f"🔄 Failed Codes: {failed_codes}")
                            
                            # Execute action using OCR coordinates
                            execute_ocr_action(page, gpt_resp, elements_data)
                            
                            # Post-action validation disabled for OCR approach
                            
                            # ALWAYS record the successful step first (regardless of new tabs)
                            execution_history.append({
                                'step': description, 
                                'code': code
                            })
                            task_summarizer.append({
                                'step': description, 
                                'code': code, 
                                'axtree': tree
                            })
                            # Save axtree to file only after successful execution
                            with open(axtree_file, 'w', encoding='utf-8') as f:
                                json.dump(tree, f, indent=2, ensure_ascii=False)
                            # Update trajectory.json with the successful step
                            action_code = generate_action_code_from_ocr(gpt_resp, elements_data)
                            update_trajectory_ocr(
                                dirs=dirs,
                                step_idx=step_idx,
                                screenshot=screenshot,
                                elements_data_file=elements_data_file,
                                action_code=action_code,
                                action_description=description,
                                page=page,
                                user_message_file=os.path.join(dirs['user_message'], f"user_message_{step_idx+1:03d}.txt"),
                                llm_output=gpt_resp,
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
                                
                                # Get OCR element data for retry
                                print(f"🔍 Running OCR for retry {retry + 1}...")
                                elements_data = get_ocr_element_data(screenshot)
                                
                                # Use elements data as the "tree"
                                tree = elements_data
                                
                                # Save elements data to axtree file for retry
                                with open(axtree_file, 'w', encoding='utf-8') as f:
                                    json.dump(elements_data, f, indent=2, ensure_ascii=False)
                                
                                # Save the elements data
                                with open(elements_data_file, 'w', encoding='utf-8') as f:
                                    json.dump(elements_data, f, indent=2, ensure_ascii=False)
                                
                                # Skip annotated screenshot for retry (OCR doesn't need it)
                                print(f"✅ OCR retry completed with {len(elements_data['elements'])} text elements")
                                
                                error_log = str(e)
                                print(f"📝 Error log: {error_log}")
                                
                                # Use the targeting data as the tree (no filtering needed)
                                filtered_tree = tree
                                
                                # Prepare context with past trajectories for retry
                                enhanced_context = ""
                                if trajectory_context:
                                    enhanced_context = f"\n\n{trajectory_context}\n\n"
                                
                                # OCR data is passed directly to the GPT function
                                
                                gpt_resp = chat_ai_playwright_code_ocr(
                                        previous_steps=execution_history,
                                        taskGoal=aug,
                                        taskPlan=current_goal,
                                        image_path=screenshot,  # Pass only the clean screenshot
                                        elements_data=elements_data,
                                        failed_codes=failed_codes,
                                        is_deletion_task=is_del,
                                        url=url,
                                        error_log=error_log,
                                        trajectory_context=enhanced_context,
                                        session_dir=dirs['root']
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
                                
                                # Mark instruction as failed in progress tracker
                                if progress_tracker:
                                    progress_tracker.complete_instruction(email, idx, aug, eps_name, success=False, error_message=f"All {MAX_RETRIES} retries failed")
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

def run_for_account(account, chrome_path, phase, progress_tracker):
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
        progress_tracker=progress_tracker
    )

def main():
    chrome_exec = os.getenv("CHROME_EXECUTABLE_PATH")
    
    # Initialize progress tracker
    progress_tracker = ProgressTracker(RESULTS_DIR)
    
    # Calculate total instructions for progress tracking
    instructions_per_persona = PHASE2_INSTRUCTIONS_PER_PERSONA if PHASE == 2 else PHASE1_INSTRUCTIONS_PER_PERSONA
    total_instructions = TOTAL_PERSONAS * instructions_per_persona
    
    # Setup progress tracking for all accounts
    progress_tracker.setup_accounts(ACCOUNTS, total_instructions)
    print("📊 Progress tracking initialized!")
    
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        futures = [
            executor.submit(run_for_account, account, chrome_exec, PHASE, progress_tracker)
            for account in ACCOUNTS
        ]
        for future in futures:
            future.result()  # Wait for all to finish
    
    # Print final progress summary
    progress_tracker.print_progress_summary()



if __name__ == "__main__":
    main() 
