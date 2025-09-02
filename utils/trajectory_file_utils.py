import json
import os
import html
import time
from datetime import datetime
from typing import Dict, Any, List, Optional


def create_episode_directory(base_dir: str, eps_name: str) -> Dict[str, str]:
    """Create directory structure for an episode."""
    eps_dir = os.path.join(base_dir, eps_name)
    dirs = {
        'root': eps_dir,
        'axtree': os.path.join(eps_dir, 'axtree'),
        'images': os.path.join(eps_dir, 'images'),
        'annotated_images': os.path.join(eps_dir, 'annotated_images'),
        'user_message': os.path.join(eps_dir, 'user_message'),
        'targeting_data': os.path.join(eps_dir, 'targeting_data'),
        'gpt_summaries': os.path.join(eps_dir, 'gpt_summaries')
    }
    for dir_path in dirs.values():
        os.makedirs(dir_path, exist_ok=True)
    return dirs


def create_trajectory_file(dirs: Dict[str, str]) -> None:
    """Create an empty trajectory.json file with initial structure."""
    trajectory_path = os.path.join(dirs['root'], 'trajectory.json')
    with open(trajectory_path, 'w', encoding='utf-8') as f:
        json.dump({}, f, indent=2, ensure_ascii=False)


def create_error_log_file(dirs: Dict[str, str]) -> None:
    """Create an empty error_log.json file with initial structure."""
    error_log_path = os.path.join(dirs['root'], 'error_log.json')
    with open(error_log_path, 'w', encoding='utf-8') as f:
        json.dump({"playwright_errors": []}, f, indent=2, ensure_ascii=False)


def update_playwright_error_log(dirs: Dict[str, str], step_idx: int, description: str, attempted_code: str, 
                               error_message: str, successful_code: str = None, thought: str = None, 
                               current_goal: str = None, all_failed_attempts: list = None) -> None:
    """Update error_log.json with Playwright execution error information and solution."""
    error_log_path = os.path.join(dirs['root'], 'error_log.json')
    
    try:
        with open(error_log_path, 'r', encoding='utf-8') as f:
            error_log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        error_log = {"playwright_errors": []}
    
    # Check if we already have an error entry for this step
    existing_error = None
    for error in error_log["playwright_errors"]:
        if error.get("step_index") == step_idx:
            existing_error = error
            break
    
    if existing_error:
        # Update existing error entry
        if all_failed_attempts:
            # This is a successful solution - update with solution and all attempts
            existing_error["successful_playwright_code"] = successful_code
            existing_error["attempted_codes"] = all_failed_attempts
            existing_error["final_error_message"] = error_message
        else:
            # This is another failed attempt - add to attempted_codes
            if "attempted_codes" not in existing_error:
                existing_error["attempted_codes"] = []
            
            attempt_entry = {
                "attempt_number": len(existing_error["attempted_codes"]) + 1,
                "code": attempted_code,
                "error_message": error_message,
                "thought": thought,
                "description": description
            }
            existing_error["attempted_codes"].append(attempt_entry)
    else:
        # Create new error entry
        error_entry = {
            "step_index": step_idx,
            "timestamp": datetime.now().isoformat(),
            "current_goal": current_goal,
            "attempted_codes": []
        }
        
        # Add constant fields to main body if they don't change
        if description:
            error_entry["description"] = description
        if thought:
            error_entry["thought"] = thought
        
        # Add first attempt
        attempt_entry = {
            "attempt_number": 1,
            "code": attempted_code,
            "error_message": error_message
        }
        
        # Add varying fields to attempt entry
        if description and "description" not in error_entry:
            attempt_entry["description"] = description
        if thought and "thought" not in error_entry:
            attempt_entry["thought"] = thought
            
        error_entry["attempted_codes"].append(attempt_entry)
        
        # If this is immediately successful, add the solution
        if successful_code:
            error_entry["successful_playwright_code"] = successful_code
        
        error_log["playwright_errors"].append(error_entry)
    
    with open(error_log_path, 'w', encoding='utf-8') as f:
        json.dump(error_log, f, indent=2, ensure_ascii=False)


def update_trajectory(dirs: Dict[str, str], step_idx: int, screenshot: str, axtree: str, action_code: str, 
                     action_description: str, page, user_message_file: str = None, llm_output=None, 
                     targeting_data_file: str = None, element_summary: str = None, annotation_id: str = None) -> None:
    """Update trajectory.json with a new step."""
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
        print(f"⚠️  Error getting page info in update_trajectory: {e}")
        current_url = "Error getting URL"
        page_title = "Error getting title"
        open_pages_titles = []
        open_pages_urls = []
    
    # Load targeting data and find element by annotation ID if available
    element_data = None
    if targeting_data_file and annotation_id and os.path.exists(targeting_data_file):
        try:
            with open(targeting_data_file, 'r', encoding='utf-8') as f:
                targeting_data = json.load(f)
            
            # Find element by annotation_id
            element_data = next((elem for elem in targeting_data if str(elem.get('annotation_id', '')) == str(annotation_id)), None)
        except Exception as e:
            print(f"⚠️ Error loading targeting data: {e}")
    
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
        
        # Use targeting data if available, otherwise fall back to page evaluation
        if element_data:
            # Get role and name directly from targeting data
            role = element_data.get('element_info', {}).get('role', '')
            name = element_data.get('element_info', {}).get('name', '')
            
            # Get button name from targeting data
            button_name = name or element_data.get('element_info', {}).get('id', '')
            
            if button_name:
                thought = f'I need to click the "{button_name}" button.'
            else:
                thought = 'I need to click a button.'
            
            bbox = element_data.get('bounding_box', {})
            action_output = {
                "thought": thought,
                "action": {
                    "bid": "",
                    "button": "left",
                    "click_type": "single",
                    "bbox": [
                        bbox.get('x', 0),
                        bbox.get('y', 0),
                        bbox.get('width', 0),
                        bbox.get('height', 0)
                    ],
                    "class": element_data.get('element_info', {}).get('class_name', ''),
                    "id": element_data.get('element_info', {}).get('id', ''),
                    "type": element_data.get('element_info', {}).get('tag_name', ''),
                    "ariaLabel": element_data.get('element_info', {}).get('name', ''),
                    "role": element_data.get('element_info', {}).get('role', ''),
                    "value": element_data.get('element_info', {}).get('value', ''),
                    "node_properties": {
                        "role": role,
                        "value": name
                    }
                },
                "action_name": "click",
                "annotation_id": annotation_id
            }
        else:
            # Fallback to page evaluation if no targeting data available
            try:
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
            except Exception as e:
                print(f"⚠️  Error evaluating page in update_trajectory (click): {e}")
                element_info = None
            if element_info:
                # Get role and name directly from page evaluation
                role = element_info.get('role', '')
                name = element_info.get('value', '')
                
                # Get button name from page evaluation
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
                    "action_name": "click",
                    "annotation_id": annotation_id
                }
    elif ".fill(" in action_code:
        action_type = "type"
        parts = action_code.split(".fill(")
        locator_code = parts[0]
        text = parts[1].split(")")[0].strip('"\'')
        # Get the last focused input element
        try:
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
        except Exception as e:
            print(f"⚠️  Error evaluating page in update_trajectory (fill): {e}")
            element_info = None
        if element_info:
            action_output = {
                "thought": thought,
                "action": {
                    "text": text
                },
                "action_name": "keyboard_type"
            }
    elif ".click()" in action_code and ".type(" in action_code:
        # Handle combined click + type (common in fallback scenarios)
        action_type = "type"
        parts = action_code.split(".click()")
        locator_code = parts[0]
        
        # Extract text to type
        text = action_code.split(".type(")[1].split(")")[0].strip('"\'')
        
        # Use targeting data if available, otherwise fall back to page evaluation
        if element_data:
            bbox = element_data.get('bounding_box', {})
            action_output = {
                "thought": f'I need to click and type "{text}" into the input field.',
                "action": {
                    "bid": "",
                    "button": "left",
                    "click_type": "single",
                    "bbox": [
                        bbox.get('x', 0),
                        bbox.get('y', 0),
                        bbox.get('width', 0),
                        bbox.get('height', 0)
                    ],
                    "class": element_data.get('element_info', {}).get('class_name', ''),
                    "id": element_data.get('element_info', {}).get('id', ''),
                    "type": element_data.get('element_info', {}).get('tag_name', ''),
                    "ariaLabel": element_data.get('element_info', {}).get('name', ''),
                    "role": element_data.get('element_info', {}).get('role', ''),
                    "value": element_data.get('element_info', {}).get('value', ''),
                    "text": text,
                    "node_properties": {
                        "role": element_data.get('element_info', {}).get('role', ''),
                        "value": text
                    }
                },
                "action_name": "type",
                "annotation_id": annotation_id
            }
        else:
            # Fallback to page evaluation if no targeting data available
            try:
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
            except Exception as e:
                print(f"⚠️  Error evaluating page in update_trajectory (fill): {e}")
                element_info = None
            if element_info:
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
                        "text": text,
                        "node_properties": {
                            "role": element_info.get('role', ''),
                            "value": text
                        }
                    },
                    "action_name": "type",
                    "annotation_id": annotation_id
                }
    elif "page.mouse.click(" in action_code:
        action_type = "click"
        
        # Extract coordinates from the mouse click
        import re
        coords_match = re.search(r'page\.mouse\.click\((\d+),\s*(\d+)\)', action_code)
        if coords_match:
            x, y = int(coords_match.group(1)), int(coords_match.group(2))
            
            # Use targeting data if available, otherwise fall back to page evaluation
            if element_data:
                # Get role and name directly from targeting data
                role = element_data.get('element_info', {}).get('role', '')
                name = element_data.get('element_info', {}).get('name', '')
                
                # Get button name from targeting data
                button_name = name or element_data.get('element_info', {}).get('id', '')
                
                if button_name:
                    thought = f'I need to click the "{button_name}" button.'
                else:
                    thought = 'I need to click a button.'
                
                bbox = element_data.get('bounding_box', {})
                action_output = {
                    "thought": thought,
                    "action": {
                        "bid": "",
                        "button": "left",
                        "click_type": "single",
                        "bbox": [
                            bbox.get('x', 0),
                            bbox.get('y', 0),
                            bbox.get('width', 0),
                            bbox.get('height', 0)
                        ],
                        "class": element_data.get('element_info', {}).get('class_name', ''),
                        "id": element_data.get('element_info', {}).get('id', ''),
                        "type": element_data.get('element_info', {}).get('tag_name', ''),
                        "ariaLabel": element_data.get('element_info', {}).get('name', ''),
                        "role": element_data.get('element_info', {}).get('role', ''),
                        "value": element_data.get('element_info', {}).get('value', ''),
                        "coordinates": [x, y],
                        "node_properties": {
                            "role": role,
                            "value": name
                        }
                    },
                    "action_name": "click",
                    "annotation_id": annotation_id
                }
            else:
                # Fallback to page evaluation if no targeting data available
                try:
                    element_info = page.evaluate("""() => {
                        const elementAtPoint = document.elementFromPoint(arguments[0], arguments[1]);
                        if (!elementAtPoint) return null;
                        const rect = elementAtPoint.getBoundingClientRect();
                        return {
                            bbox: {
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            },
                            class: elementAtPoint.className,
                            id: elementAtPoint.id,
                            type: elementAtPoint.tagName.toLowerCase(),
                            ariaLabel: elementAtPoint.getAttribute('aria-label'),
                            role: elementAtPoint.getAttribute('role'),
                            value: elementAtPoint.value
                        };
                    }""", x, y)
                except Exception as e:
                    print(f"⚠️  Error evaluating page in update_trajectory (mouse click): {e}")
                    element_info = None
                
                if element_info:
                    # Get role and name directly from page evaluation
                    role = element_info.get('role', '')
                    name = element_info.get('value', '')
                    
                    # Get button name from page evaluation
                    button_name = name or element_info.get('ariaLabel') or element_info.get('id', '')
                    
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
                            "coordinates": [x, y],
                            "node_properties": {
                                "role": role,
                                "value": name
                            }
                        },
                        "action_name": "click",
                        "annotation_id": annotation_id
                    }
    elif ".dblclick()" in action_code:
        action_type = "dblclick"
        locator_code = action_code.split(".dblclick()")[0]
        try:
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
        except Exception as e:
            print(f"⚠️  Error evaluating page in update_trajectory (dblclick): {e}")
            element_info = None
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
        try:
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
        except Exception as e:
            print(f"⚠️  Error evaluating page in update_trajectory (paste): {e}")
            element_info = None
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
        try:
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
        except Exception as e:
            print(f"⚠️  Error evaluating page in update_trajectory (keyboard.press): {e}")
            element_info = None
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
        "targeting_data": os.path.join('targeting_data', os.path.basename(targeting_data_file)) if targeting_data_file else None,
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
        "phase": 1  # Hardcoded for now, could be made configurable
    }


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
    # Safety check for page object
    try:
        page_title = page.title() if hasattr(page, 'title') else "Unknown"
        page_url = page.url if hasattr(page, 'url') else "Unknown"
        user_message_content.append(f"Current Page: {page_title} ({page_url})\n")
    except Exception as e:
        print(f"⚠️  Error getting page info: {e}")
        user_message_content.append("Current Page: Unknown (Error getting page info)\n")
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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    <div class="container">
        <h1>{metadata['eps_name']} ({metadata['task'].get('task_type','')})</h1>
        <p><strong>GPT Summaries:</strong> <a href="gpt_summaries/">View all GPT summary files</a></p>
        <h2>Instructions</h2>
        <table class="instruction-table">
            <tr><th>level</th><th>instruction</th></tr>
            <tr><td><em>high_level</em></td><td>{html.escape(instructions.get('high_level',''))}</td></tr>
            <tr><td><em>mid_level</em></td><td>{html.escape(instructions.get('mid_level',''))}</td></tr>
            <tr><td><em>low_level</em></td><td>{html.escape(instructions.get('low_level',''))}</td></tr>
            <tr><td><em>steps</em></td><td><ul class="steps-list">{''.join(f'<li>{html.escape(str(s))}</li>' for s in steps)}</ul></td></tr>
        </table>
        <h2>Trajectory Steps</h2>
"""

    for step_num, step_data in trajectory.items():
        screenshot_path = os.path.join('images', step_data['screenshot'])
        user_message_path = step_data.get('user_message')
        targeting_data_path = step_data.get('targeting_data')
        
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
        # Fix: check if action_output is a dict before calling .get()
        thought = html.escape(action_output.get('thought', '')) if isinstance(action_output, dict) else ''
        action_str = html.escape(action.get('action_str', ''))
        action_description = html.escape(action.get('action_description', ''))
        # System message: use a field if available, else placeholder
        system_message = step_data.get('system_message', 'System message for this step (placeholder)')
        # Element output: pretty print action_output['action'] if available
        element_output = ''
        if isinstance(action_output, dict) and 'action' in action_output:
            element_output = json.dumps(action_output['action'], indent=2, ensure_ascii=False)
            element_output = html.escape(element_output)
        else:
            element_output = '[No element output]'
        # LLM output: show Playwright code for this step
        playwright_code = action.get('playwright_code', '')
        llm_output_str = html.escape(playwright_code) if playwright_code else 'No Playwright code for this step.'

        # Get annotated screenshot path if available
        annotated_screenshot_path = None
        if step_data.get('targeting_data'):
            # Try to find corresponding annotated screenshot
            step_num_int = int(step_num)
            annotated_filename = f"annotated_screenshot_{step_num_int:03d}.png"
            annotated_screenshot_path = os.path.join('annotated_images', annotated_filename)
        
        # Load targeting data and find selected element information
        selected_element_info = ""
        annotation_id = action_output.get('annotation_id') if isinstance(action_output, dict) else None
        
        if targeting_data_path and annotation_id:
            try:
                targeting_data_full_path = os.path.join(dirs['root'], targeting_data_path)
                if os.path.exists(targeting_data_full_path):
                    with open(targeting_data_full_path, 'r', encoding='utf-8') as f:
                        targeting_data = json.load(f)
                    
                    # Find the selected element by annotation ID
                    selected_element = None
                    for element in targeting_data:
                        if str(element.get('annotation_id', '')) == str(annotation_id):
                            selected_element = element
                            break
                    
                    if selected_element:
                        element_info = selected_element.get('element_info', {})
                        bounding_box = selected_element.get('bounding_box', {})
                        
                        selected_element_info = f"""
                        <div class="step-details-label">Selected Element (ID: {annotation_id})</div>
                        <div>
                            <strong>Name:</strong> {html.escape(element_info.get('name', 'N/A'))}<br>
                            <strong>Role:</strong> {html.escape(element_info.get('role', 'N/A'))}<br>
                            <strong>Type:</strong> {html.escape(element_info.get('tag_name', 'N/A'))}<br>
                            <strong>Bounding Box:</strong> x={bounding_box.get('x', 0)}, y={bounding_box.get('y', 0)}, width={bounding_box.get('width', 0)}, height={bounding_box.get('height', 0)}<br>
                            <strong>Center:</strong> ({bounding_box.get('center_x', 0)}, {bounding_box.get('center_y', 0)})
                        </div>
                        """
            except Exception as e:
                selected_element_info = f"<div class='step-details-label'>Selected Element Info</div><div>Error loading targeting data: {str(e)}</div>"
        
        html_content += f"""
        <div class="step">
            <div class="step-header">
                <span class="step-number">Step {step_num}</span>
            </div>
            <div class="step-content">
                <div>
                    <img src="{screenshot_path}" alt="Step {step_num} Screenshot" class="screenshot">
                    {f'<br><br><strong>Annotated Version:</strong><br><img src="{annotated_screenshot_path}" alt="Step {step_num} Annotated Screenshot" class="screenshot">' if annotated_screenshot_path else ''}
                </div>
                <div>
                    <div class="step-details-label">Thought</div>
                    <div>{thought}</div>
                    <div class="step-details-label">Action Code</div>
                    <div><pre>{llm_output_str}</pre></div>
                    <div class="step-details-label">Action Description</div>
                    <div>{action_description}</div>
                    {selected_element_info}
                    <button class="collapsible">System Message</button>
                    <div class="content"><pre>{system_message}</pre></div>
                    <button class="collapsible">User Message</button>
                    <div class="content"><pre>{user_message_content}</pre></div>
                    <button class="collapsible">Element Output</button>
                    <div class="content"><pre>{element_output}</pre></div>
                    <button class="collapsible">LLM Output</button>
                    <div class="content"><pre>{llm_output_str}</pre></div>
                </div>
            </div>
        </div>
        """

    # Add final image section
    if trajectory:
        # Get the last step number to find the final screenshot
        last_step_num = max(int(step_num) for step_num in trajectory.keys())
        final_screenshot_path = os.path.join('images', f'screenshot_{last_step_num:03d}.png')
        final_annotated_path = os.path.join('annotated_images', f'annotated_screenshot_{last_step_num:03d}.png')
        
        # Check if final annotated screenshot exists
        final_annotated_exists = os.path.exists(os.path.join(dirs['root'], final_annotated_path))
        
        html_content += f"""
        <h2>Final Result</h2>
        <div class="step">
            <div class="step-header">
                <span class="step-number">Final State</span>
            </div>
            <div class="step-content">
                <div>
                    <img src="{final_screenshot_path}" alt="Final Screenshot" class="screenshot">
                    {f'<br><br><strong>Annotated Final State:</strong><br><img src="{final_annotated_path}" alt="Final Annotated Screenshot" class="screenshot">' if final_annotated_exists else ''}
                </div>
                <div>
                    <div class="step-details-label">Task Status</div>
                    <div>{'✅ Completed Successfully' if metadata.get('success', False) else '❌ Failed or Incomplete'}</div>
                    <div class="step-details-label">Total Steps</div>
                    <div>{metadata.get('total_steps', 0)}</div>
                    <div class="step-details-label">Runtime</div>
                    <div>{metadata.get('runtime_sec', 0):.2f} seconds</div>
                    <div class="step-details-label">Total Tokens Used</div>
                    <div>{metadata.get('total_tokens', 0)}</div>
                    {f'<div class="step-details-label">GPT Output</div><div>{html.escape(metadata.get("gpt_output", ""))}</div>' if metadata.get("gpt_output") else ''}
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

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
