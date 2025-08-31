import time
import re
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont


def get_comprehensive_element_data(page, url: str = None) -> Dict[str, Any]:
    """
    Get interactive elements directly using Playwright - simplified approach.
    
    Args:
        page: Playwright page object
        url: Current page URL for context-specific filtering
        
    Returns:
        Dict containing interactive elements and targeting data
    """
    print("🔍 Collecting interactive elements...")
    
    # Get all interactive elements directly using Playwright
    ax_elements = get_all_interactive_elements(page)
    print(f"    Found {len(ax_elements)} interactive elements")
    
    # Create targeting data
    targeting_data = create_comprehensive_targeting_data(ax_elements, url)
    
    return {
        "interactive_elements": ax_elements,
        "targeting_data": targeting_data,
        "element_count": len(ax_elements),
        "collection_timestamp": time.time()
    }


def create_simplified_element_summary(targeting_data: list) -> list:
    """
    Create simplified element data with just annotation_id, role, and name.
    This is what gets sent to GPT and saved in axtree files.
    
    Args:
        targeting_data: Full targeting data from comprehensive element collection
        
    Returns:
        List of simplified element objects
    """
    elements_data = []
    for elem in targeting_data:
        annotation_id = elem.get('annotation_id', '?')
        role = elem.get('element_info', {}).get('role', 'unknown')
        name = elem.get('element_info', {}).get('name', 'unnamed')
        elements_data.append({
            "annotation_id": str(annotation_id),
            "role": role,
            "name": name
        })
    return elements_data


def get_all_interactive_elements(page) -> list:
    """Get all interactive elements directly using Playwright - simple and fast"""
    elements = []
    
    # List of interactive roles to look for
    interactive_roles = [
        'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox',
        'listbox', 'menuitem', 'tab', 'slider', 'spinbutton', 'searchbox',
        'switch', 'menubar', 'toolbar', 'tree', 'grid', 'table',
        'option', 'menuitemcheckbox', 'menuitemradio', 'listitem',
        'group', 'region', 'dialog', 'alertdialog', 'tooltip'
    ]

    # Get elements by each role
    for role in interactive_roles:
        try:
            role_elements = page.get_by_role(role).all()
            for element in role_elements:
                try:
                    bbox = element.bounding_box()
                    # Filter out elements with negative coordinates or very small dimensions
                    if bbox and bbox['width'] > 8 and bbox['height'] > 8 and bbox['x'] >= 0 and bbox['y'] >= 0:
                        # Check if element is truly visible and not transparent/covered
                        try:
                            if not element.is_visible():
                                continue
                            
                            # Additional check: ensure element has actual visual presence and is in viewport
                            is_visually_visible = element.evaluate('''
                                (el) => {
                                    const style = window.getComputedStyle(el);
                                    const rect = el.getBoundingClientRect();
                                    const viewport = {
                                        width: window.innerWidth,
                                        height: window.innerHeight
                                    };
                                    
                                    // Check if element has no dimensions
                                    if (rect.width === 0 || rect.height === 0) return false;
                                    
                                    // Check if element is transparent
                                    if (parseFloat(style.opacity) === 0) return false;
                                    
                                    // Check if element is hidden by CSS
                                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                                    
                                    // Check if element is hidden by CSS animations or transitions
                                    if (style.animationName !== 'none' && style.animationPlayState === 'paused') return false;
                                    if (style.transitionDuration !== '0s' && style.transitionProperty !== 'none') {
                                        // If element is in transition, check if it's actually visible
                                        if (parseFloat(style.opacity) < 0.1) return false;
                                    }
                                    
                                    // Check if element is positioned off-screen or partially hidden
                                    if (rect.right < 0 || rect.bottom < 0 || rect.left > viewport.width || rect.top > viewport.height) return false;
                                    
                                    // Check if element is completely outside the viewport (more strict)
                                    if (rect.left >= viewport.width || rect.top >= viewport.height) return false;
                                    
                                    // Check if element is too small to be meaningful (less than 8x8 pixels)
                                    if (rect.width < 8 || rect.height < 8) return false;
                                    
                                    // Check if element is covered by another element (z-index issues)
                                    const elementAtPoint = document.elementFromPoint(
                                        rect.left + rect.width / 2,
                                        rect.top + rect.height / 2
                                    );
                                    if (!elementAtPoint || !el.contains(elementAtPoint)) return false;
                                    
                                    // Additional check: ensure element is not clipped by overflow
                                    const parent = el.parentElement;
                                    if (parent) {
                                        const parentStyle = window.getComputedStyle(parent);
                                        if (parentStyle.overflow === 'hidden' || parentStyle.overflow === 'scroll') {
                                            const parentRect = parent.getBoundingClientRect();
                                            if (rect.left < parentRect.left || rect.top < parentRect.top || 
                                                rect.right > parentRect.right || rect.bottom > parentRect.bottom) {
                                                return false;
                                            }
                                        }
                                    }
                                    
                                    // Check if element has no meaningful content (text, images, or interactive properties)
                                    const hasText = el.textContent && el.textContent.trim().length > 0;
                                    const hasImage = el.querySelector('img') || el.tagName === 'IMG';
                                    const hasInteractiveAttr = el.getAttribute('onclick') || el.getAttribute('href') || el.getAttribute('role') || el.tagName === 'BUTTON' || el.tagName === 'INPUT' || el.tagName === 'A';
                                    const hasBackground = style.backgroundImage !== 'none' || style.backgroundColor !== 'rgba(0, 0, 0, 0)';
                                    
                                    // Element must have at least one of these to be considered visible
                                    if (!hasText && !hasImage && !hasInteractiveAttr && !hasBackground) return false;
                                    
                                    // Final check: ensure element is actually in the current scroll viewport
                                    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                                    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
                                    const viewportTop = scrollTop;
                                    const viewportBottom = scrollTop + viewport.height;
                                    const viewportLeft = scrollLeft;
                                    const viewportRight = scrollLeft + viewport.width;
                                    
                                    if (rect.top > viewportBottom || rect.bottom < viewportTop || 
                                        rect.left > viewportRight || rect.right < viewportLeft) {
                                        return false;
                                    }
                                    
                                    // Check if element is actually clickable/interactive in current state
                                    const isClickable = el.offsetParent !== null && 
                                                       !el.disabled && 
                                                       el.style.pointerEvents !== 'none' &&
                                                       el.style.userSelect !== 'none';
                                    
                                    if (!isClickable) return false;
                                    
                                    return true;
                                }
                            ''')
                            
                            if not is_visually_visible:
                                continue
                        except:
                            continue
                        # Get element properties
                        name = element.get_attribute('aria-label') or \
                               element.text_content() or \
                               element.get_attribute('title') or \
                               element.get_attribute('placeholder') or \
                               element.get_attribute('value') or ''
                        
                        tag_name = element.evaluate('el => el.tagName.toLowerCase()')
                        element_id = element.get_attribute('id') or ''
                        class_name = element.get_attribute('class') or ''
                        href = element.get_attribute('href') or ''
                        element_type = element.get_attribute('type') or ''
                        disabled = element.evaluate('el => el.disabled') or False
                        checked = element.evaluate('el => el.checked')
                        selected = element.evaluate('el => el.selected')
                        
                        # Create clean Playwright selector without action (action will be determined by GPT's action_type)
                        playwright_selector = None
                        if element_id:
                            playwright_selector = f"page.locator('#{element_id}')"
                        elif name.strip():
                            playwright_selector = f'page.get_by_text("{name.strip()}")'
                        else:
                            playwright_selector = f'page.get_by_role("{role}")'
                        
                        element_data = {
                            'name': name.strip() if name else '',
                            'role': role,
                            'value': element.get_attribute('value') or '',
                            'x': int(bbox['x']),
                            'y': int(bbox['y']),
                            'width': int(bbox['width']),
                            'height': int(bbox['height']),
                            'tagName': tag_name,
                            'type': element_type,
                            'id': element_id,
                            'className': class_name,
                            'href': href,
                            'disabled': disabled,
                            'checked': checked,
                            'selected': selected,
                            'source': 'playwright_direct',
                            'hasBoundingBox': True,
                            'playwright_selector': playwright_selector
                        }
                        elements.append(element_data)
                except:
                    continue
        except:
            continue
    
    return elements


def create_comprehensive_targeting_data(elements: list, url: str = None) -> list:
    """Create comprehensive targeting data for elements with multiple strategies"""
    targeting_data = []
    
    for i, element in enumerate(elements):
        # Create multiple targeting strategies for each element
        element_data = {
            "annotation_id": i,
            "element_info": {
                "name": clean_text_for_selector(element.get('name', '')),
                "name_raw": element.get('name', ''),  # Keep raw version too
                "role": element.get('role', ''),
                "value": element.get('value', ''),
                "tag_name": element.get('tagName', ''),
                "type": element.get('type', ''),
                "id": element.get('id', ''),
                "class_name": element.get('className', ''),
                "href": element.get('href', ''),
                "disabled": element.get('disabled', False),
                "checked": element.get('checked'),
                "selected": element.get('selected')
            },
            "bounding_box": {
                "x": element.get('x', 0),
                "y": element.get('y', 0),
                "width": element.get('width', 0),
                "height": element.get('height', 0),
                "center_x": element.get('x', 0) + element.get('width', 0) // 2,
                "center_y": element.get('y', 0) + element.get('height', 0) // 2
            },
            "playwright_selectors": generate_playwright_selectors(element),
            "interaction_suggestions": suggest_interactions(element)
        }
        
        targeting_data.append(element_data)
    
    return targeting_data


def clean_text_for_selector(text: str) -> str:
    """Clean text for use in selectors - conservative cleaning"""
    if not text:
        return ""
    
    # Only remove leading/trailing whitespace and normalize newlines
    # Keep internal spacing as-is to preserve legitimate spaces
    cleaned = text.strip()
    
    # Replace newlines and tabs with single spaces, but preserve regular spaces
    cleaned = cleaned.replace('\n', ' ').replace('\t', ' ').replace('\r', ' ')
    
    # Only collapse multiple spaces if there are 3+ consecutive spaces
    # This preserves intentional double spaces but removes excessive whitespace
    cleaned = re.sub(r' {3,}', ' ', cleaned)
    
    # Escape single quotes for selector strings
    cleaned = cleaned.replace("'", "\\'")
    
    # Truncate if too long
    if len(cleaned) > 50:
        cleaned = cleaned[:47] + "..."
    
    return cleaned


def try_alternative_selectors(page, original_code: str, comprehensive_data: dict, gpt_resp: dict) -> tuple[bool, list, str]:
    """
    Try alternative Playwright selectors when the primary one fails.
    Simple approach: loop through selectors array (skip first) and try exec() one by one.
    Returns: (success, failed_alternatives, successful_selector_code)
    """
    failed_alternatives = []
    
    try:
        # Get the selected annotation ID from GPT response
        selected_id = gpt_resp.get('selected_annotation_id')
        if not selected_id:
            print("⚠️ No selected_annotation_id found, can't try alternative selectors")
            return False, failed_alternatives, ""
        
        # Find the element data for this annotation ID
        target_element = None
        for element in comprehensive_data.get('targeting_data', []):
            if str(element.get('annotation_id', '')) == str(selected_id):
                target_element = element
                break
        
        if not target_element:
            print(f"⚠️ Element with annotation ID {selected_id} not found in targeting data")
            return False, failed_alternatives, ""
        
        # Get alternative selectors
        alternative_selectors = target_element.get('playwright_selectors', [])
        if len(alternative_selectors) == 0:
            print("⚠️ No alternative selectors available")
            return False, failed_alternatives, ""
        
        print(f"🎯 Trying alternative selectors for element {selected_id}")
        
        # Try each alternative selector starting from index 0
        for i, selector_data in enumerate(alternative_selectors):
            selector_code = selector_data.get('selector', '')
            selector_type = selector_data.get('type', 'unknown')
            
            if not selector_code:
                continue
            
            # Construct the action based on the action type from GPT's response
            # Check if the selector already includes an action (like coordinates or mouse actions)
            action_type = gpt_resp.get('action_type', 'click')  # Default to click if not specified
            
            # Check if selector already includes an action
            if 'page.mouse.click' in selector_code or 'page.keyboard.' in selector_code:
                # Selector already includes the action, use as-is
                if action_type == 'fill':
                    text_to_fill = gpt_resp.get('text_to_fill', 'TEXT_TO_FILL')
                    action_code = f"{selector_code}; page.keyboard.type('{text_to_fill}')"
                else:
                    action_code = selector_code
            else:
                # Selector is clean, add the appropriate action
                if action_type == 'click':
                    action_code = f"{selector_code}.click()"
                elif action_type == 'fill':
                    # For fill actions, use the text_to_fill from GPT's response if available
                    text_to_fill = gpt_resp.get('text_to_fill', 'TEXT_TO_FILL')
                    action_code = f"{selector_code}.fill('{text_to_fill}')"
                elif action_type == 'select':
                    action_code = f"{selector_code}.select_option('OPTION_TO_SELECT')"
                elif action_type == 'navigate':
                    action_code = f"{selector_code}.click()"  # Navigate usually involves clicking
                elif action_type == 'wait':
                    action_code = f"{selector_code}.wait_for()"  # Wait for element to be visible
                else:
                    # Default to click for unknown action types
                    action_code = f"{selector_code}.click()"
            
            print(f"  🔄 Trying alternative {i}: {selector_type} - {action_code}")
            
            try:
                # Execute the alternative selector with the constructed action
                exec(action_code)
                print(f"  ✅ Alternative selector succeeded: {selector_type}")
                return True, failed_alternatives, action_code
                
            except Exception as alt_e:
                print(f"  ❌ Alternative {i} failed: {alt_e}")
                failed_alternatives.append(action_code)
                continue
        
        print("❌ All alternative selectors failed")
        return False, failed_alternatives, ""
        
    except Exception as e:
        print(f"⚠️ Error trying alternative selectors: {e}")
        return False, failed_alternatives, ""


def generate_colors(count):
    """Generate distinct colors for bounding boxes"""
    colors = []
    for i in range(count):
        # Generate bright colors that are easily distinguishable
        hue = (i * 137.508) % 360  # Golden angle for good distribution
        saturation = 70 + (i % 3) * 10  # 70, 80, 90
        lightness = 50 + (i % 2) * 20   # 50, 70
        
        # Convert HSL to RGB
        c = (1 - abs(2 * lightness/100 - 1)) * saturation/100
        x = c * (1 - abs((hue / 60) % 2 - 1))
        m = lightness/100 - c/2
        
        if 0 <= hue < 60:
            r, g, b = c, x, 0
        elif 60 <= hue < 120:
            r, g, b = x, c, 0
        elif 120 <= hue < 180:
            r, g, b = 0, c, x
        elif 180 <= hue < 240:
            r, g, b = 0, x, c
        elif 240 <= hue < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        
        r = int((r + m) * 255)
        g = int((g + m) * 255)
        b = int((b + m) * 255)
        
        colors.append((r, g, b))
    
    return colors


def annotate_screenshot_with_bounding_boxes(screenshot_path: str, targeting_data: list, annotated_path: str) -> str:
    """
    Annotate screenshot with bounding boxes and annotation IDs for interactive elements.
    
    Args:
        screenshot_path: Path to the original screenshot
        targeting_data: List of element data with bounding boxes and annotation IDs
        annotated_path: Path to save the annotated image
        
    Returns:
        Path to the annotated image
    """
    try:
        # Open the screenshot
        img = Image.open(screenshot_path)
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, fallback to default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)  # macOS
            except:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)  # Linux
                except:
                    font = ImageFont.load_default()
        
        # Generate colors for each element
        colors = generate_colors(len(targeting_data))
        
        # Draw bounding boxes and labels
        for i, element in enumerate(targeting_data):
            bbox = element.get('bounding_box', {})
            annotation_id = element.get('annotation_id', '?')
            
            x = bbox.get('x', 0)
            y = bbox.get('y', 0)
            width = bbox.get('width', 0)
            height = bbox.get('height', 0)
            
            # Skip elements with invalid dimensions
            if width <= 0 or height <= 0:
                continue
            
            color = colors[i]
            
            # Draw bounding box
            draw.rectangle([x, y, x + width, y + height], outline=color, width=2)
            
            # Create label text (just the annotation ID)
            label = f"{annotation_id}"
            
            # Draw label background
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            label_x = max(0, min(x, img.width - text_width - 4))
            label_y = max(0, y - text_height - 4)
            
            draw.rectangle(
                [label_x, label_y, label_x + text_width + 4, label_y + text_height + 4],
                fill=color,
                outline=color
            )
            
            # Draw label text (white for better visibility)
            draw.text(
                (label_x + 2, label_y + 2),
                label,
                fill='white',
                font=font
            )
        
        # Save the annotated image
        img.save(annotated_path)
        print(f"✅ Annotated screenshot saved to: {annotated_path}")
        
        return annotated_path
        
    except ImportError:
        print("⚠️ PIL not available, skipping image annotation")
        return screenshot_path
    except Exception as e:
        print(f"⚠️ Error annotating screenshot: {e}")
        return screenshot_path


def generate_playwright_selectors(element: dict) -> list:
    """Generate multiple Playwright selector strategies for an element"""
    selectors = []
    
    # Strategy 1: By ID (highest priority - most reliable)
    if element.get('id'):
        selectors.append({
            "type": "id",
            "selector": f"page.locator('#{element['id']}')",
            "priority": "high"
        })
    
    # Strategy 2: By coordinates (mouse click) - second priority
    selectors.append({
        "type": "coordinates",
        "selector": f"page.mouse.click({element.get('x', 0) + element.get('width', 0)//2}, {element.get('y', 0) + element.get('height', 0)//2})",
        "priority": "high"
    })
    
    # Strategy 3: By role and name
    if element.get('role') and element.get('name'):
        selectors.append({
            "type": "role_name",
            "selector": f"page.get_by_role('{element['role']}', name='{element['name']}')",
            "priority": "high"
        })
    
    # Strategy 4: By label
    if element.get('name'):
        selectors.append({
            "type": "label",
            "selector": f"page.get_by_label('{element['name']}')",
            "priority": "high"
        })
    
    # Strategy 5: By text content
    if element.get('name'):
        selectors.append({
            "type": "text",
            "selector": f"page.get_by_text('{element['name']}')",
            "priority": "medium"
        })
    
    # Strategy 6: By CSS class combination
    css_parts = []
    if element.get('tagName'):
        css_parts.append(element['tagName'])
    if element.get('id'):
        css_parts.append(f"#{element['id']}")
    if element.get('className'):
        # Split class names and add them
        classes = element['className'].split()
        for cls in classes[:3]:  # Limit to first 3 classes
            if cls.strip():
                css_parts.append(f".{cls.strip()}")
    
    if css_parts:
        selectors.append({
            "type": "css_combined",
            "selector": f"page.locator('{''.join(css_parts)}')",
            "priority": "medium"
        })
    
    return selectors


def suggest_interactions(element: dict) -> list:
    """Suggest appropriate Playwright interactions for an element"""
    suggestions = []
    
    role = element.get('role', '').lower()
    tag = element.get('tagName', '').lower()
    element_type = element.get('type', '').lower()
    
    # Click interactions
    if role in ['button', 'link', 'tab', 'menuitem'] or tag in ['button', 'a']:
        suggestions.append("click()")
        if role == 'link' or tag == 'a':
            suggestions.append("click(button='middle')")  # Middle click for links
    
    # Form interactions
    elif role == 'textbox' or tag == 'input':
        if element_type in ['text', 'email', 'password', 'search']:
            suggestions.append("fill('text')")
            suggestions.append("type('text')")
            suggestions.append("clear()")
        elif element_type in ['checkbox', 'radio']:
            suggestions.append("check()")
            suggestions.append("uncheck()")
            if element_type == 'radio':
                suggestions.append("set_checked(true)")
    
    # Select interactions
    elif role == 'combobox' or tag == 'select':
        suggestions.append("select_option('value')")
        suggestions.append("select_option(label='label')")
    
    # Hover interactions
    if role in ['button', 'link', 'menuitem'] or tag in ['button', 'a']:
        suggestions.append("hover()")
    
    # Focus interactions
    if role in ['textbox', 'combobox', 'button'] or tag in ['input', 'select', 'button']:
        suggestions.append("focus()")
    
    return suggestions


def get_all_open_tabs(browser) -> list:
    """Get information about all currently open tabs, excluding about:blank"""
    tabs = []
    try:
        for page in browser.pages:
            try:
                # Skip about:blank tabs
                if page.url == "about:blank":
                    continue
                    
                try:
                    tab_info = {
                        'url': page.url,
                        'title': page.title(),
                        'domain': 'google.com' if 'google.com' in page.url.lower() else 'external',
                        'page': page
                    }
                    tabs.append(tab_info)
                except Exception as e:
                    print(f"⚠️  Error getting tab info: {e}")
                    # Skip this tab if we can't get its info
                    continue
            except Exception as e:
                print(f"⚠️  Error accessing tab: {e}")
                continue
    except Exception as e:
        print(f"⚠️  Error accessing browser pages: {e}")
        return []
    
    return tabs


def check_for_new_tabs(browser, previous_tab_count: int, previous_tab_urls: set) -> tuple[bool, list, int]:
    """
    Check if new tabs were opened and return info about them.
    
    Args:
        browser: Browser context
        previous_tab_count: Number of tabs from previous step
        previous_tab_urls: Set of tab URLs from previous step
        
    Returns:
        tuple: (has_new_tabs, new_tabs, current_tab_count)
    """
    current_tabs = get_all_open_tabs(browser)
    current_tab_count = len(current_tabs)
    current_tab_urls = {tab['url'] for tab in current_tabs}
    
    # Check if we have new tabs
    if current_tab_count > previous_tab_count:
        # Find new tabs (URLs that weren't in previous step)
        new_tab_urls = current_tab_urls - previous_tab_urls
        new_tabs = [tab for tab in current_tabs if tab['url'] in new_tab_urls]
        
        print(f"🆕 New tabs detected! Previous: {previous_tab_count}, Current: {current_tab_count}")
        print(f"   New tabs: {[tab['domain'] for tab in new_tabs]}")
        
        return True, new_tabs, current_tab_count
    else:
        return False, [], current_tab_count


def switch_to_new_tab(new_tabs: list, current_page) -> tuple[bool, object]:
    """
    Switch to the first new tab and return success status and new page object.
    
    Args:
        new_tabs: List of new tab info dictionaries
        current_page: Current page object
        
    Returns:
        tuple: (success, new_page_object)
    """
    if not new_tabs:
        return False, current_page
    
    try:
        # Get the first new tab
        new_tab = new_tabs[0]
        new_page = new_tab['page']
        
        print(f"🔄 Switching to new tab: {new_tab['title']} ({new_tab['domain']})")
        
        # Wait for the new tab to be ready
        print("⏳ Waiting for new tab to stabilize...")
        new_page.wait_for_timeout(3000)  # 3 second delay
        
        # Bring the new tab to front
        new_page.bring_to_front()
        
        # Wait a bit more after bringing to front
        new_page.wait_for_timeout(2000)  # 2 second additional delay
        
        # Verify the tab is accessible
        try:
            new_page.wait_for_selector('body', timeout=5000)
            print(f"✅ Successfully switched to: {new_tab['domain']}")
            return True, new_page
        except Exception as e:
            print(f"⚠️  New tab not ready: {e}")
            return False, current_page
            
    except Exception as e:
        print(f"❌ Error switching to new tab: {e}")
        return False, current_page
