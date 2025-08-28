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

# Load environment variables from .env file
load_dotenv()

# Knowledge base client for trajectory context
from utils.knowledge_base_client import get_trajectory_context

def filter_accessibility_tree(tree: Dict[str, Any], url: str = None) -> Dict[str, Any]:
    """
    Filter out inbox-like elements and other verbose content from accessibility tree.
    This reduces token usage and focuses on actionable UI elements.
    
    Args:
        tree: The accessibility tree to filter
        url: The current page URL to determine site-specific filtering
    """
    if not tree or not isinstance(tree, dict):
        return tree
    
    def should_keep_element(element: Dict[str, Any]) -> bool:
        """Determine if an element should be kept in the filtered tree."""
        if not isinstance(element, dict):
            return True
        
        # Get element properties
        tagName = element.get('tagName', '').upper()
        className = element.get('className', '').lower()
        name = element.get('name', '').lower()
        role = element.get('role', '').lower()
        description = element.get('description', '').lower()
        
        # ===== GMAIL INBOX SPECIFIC FILTERING =====
        # Only apply Gmail-specific filtering if we're on a Gmail URL
        if url and ('mail.google.com' in url or 'gmail.com' in url):
            # ALWAYS keep the root element and its direct children
            if role == "WebArea" or element.get('focused') is True:
                return True
            
            # Keep all navigation and action elements
            if role in ['button', 'link', 'textbox', 'combobox', 'heading', 'tab', 'toolbar']:
                return True
            
            # Keep elements with important names
            important_names = ['compose', 'search', 'inbox', 'sent', 'drafts', 'settings', 'support']
            if any(important in name for important in important_names):
                return True
            
            # Filter out only the most obvious inbox email rows
            if tagName == "TR" and role == "row" and len(name) > 100:
                # This is likely an email row with long content
                return False
            
            # Filter out very long text content (likely email bodies)
            if len(name) > 200:
                return False
            
            # Keep everything else
            return True
        
        # ===== GENERAL INBOX FILTERING =====
        # Filter out inbox-like elements
        inbox_keywords = [
            'inbox', 'email', 'message', 'mail', 'notification', 'alert',
            'unread', 'read', 'sent', 'draft', 'spam', 'trash',
            'conversation', 'thread', 'reply', 'forward', 'archive',
            'mark as read', 'mark as unread', 'delete message',
            'compose', 'new message', 'send', 'attach', 'cc', 'bcc'
        ]
        
        # Check if element contains inbox-related keywords
        for keyword in inbox_keywords:
            if keyword in name or keyword in description:
                return False
        
        # Filter out verbose content areas that are not actionable
        if role in ['article', 'main', 'contentinfo'] and not element.get('children'):
            # Keep only if it has actionable children
            return True
        
        # Filter out very long text content (likely email bodies, articles, etc.)
        if len(name) > 200:  # Very long text content
            return False
        
        # Keep navigation, buttons, inputs, and other actionable elements
        actionable_roles = [
            'button', 'link', 'textbox', 'combobox', 'checkbox', 'radio',
            'tab', 'menuitem', 'option', 'searchbox', 'spinbutton',
            'slider', 'switch', 'treeitem', 'gridcell', 'cell',
            'heading', 'listitem', 'menubar', 'toolbar', 'navigation'
        ]
        
        if role in actionable_roles:
            return True
        
        # Keep elements with specific attributes that make them interactive
        if element.get('focused') or element.get('pressed') or element.get('checked'):
            return True
        
        # Keep elements that are likely to be part of the main interface
        if 'aria-' in str(element) or 'data-' in str(element):
            return True
        
        # Filter out generic containers with no actionable content
        if role in ['generic', 'group', 'region'] and not element.get('children'):
            return False
        
        return True
    
    def filter_element(element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Recursively filter an element and its children."""
        if not should_keep_element(element):
            return None
        
        # Create a copy of the element
        filtered_element = element.copy()
        
        # Recursively filter children
        if 'children' in filtered_element and filtered_element['children']:
            filtered_children = []
            for child in filtered_element['children']:
                filtered_child = filter_element(child)
                if filtered_child is not None:
                    filtered_children.append(filtered_child)
            filtered_element['children'] = filtered_children
        
        return filtered_element
    
    # Apply filtering to the root element
    filtered_result = filter_element(tree)
    
    # Debug: Log filtering results
    if filtered_result is None:
        print("⚠️ Warning: filter_element returned None for root element")
        # Return original tree if filtering removed everything
        return tree
    elif isinstance(filtered_result, dict) and not filtered_result.get('children'):
        print("⚠️ Warning: Root element has no children after filtering")
        # Return original tree if filtering removed all children
        return tree
    
    return filtered_result

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
        "accessibility_tree": {},  # Empty for compatibility
        "interactive_elements": ax_elements,
        "targeting_data": targeting_data,
        "element_count": len(ax_elements),
        "collection_timestamp": time.time()
    }







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
                    # if bbox and bbox['width'] > 2 and bbox['height'] > 2 and bbox['x'] >= 0 and bbox['y'] >= 0:
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
    import re
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
        from PIL import Image, ImageDraw, ImageFont
        import os
        
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
            
            # # Draw click coordinate marker (center point of the element)
            # click_x = x + width // 2
            # click_y = y + height // 2
            
            # # Draw a small circle at the click coordinates
            # circle_radius = 3
            # draw.ellipse(
            #     [click_x - circle_radius, click_y - circle_radius, 
            #      click_x + circle_radius, click_y + circle_radius],
            #     fill='yellow',
            #     outline='black',
            #     width=1
            # )
            

        
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

# ========== CONFIGURABLE PARAMETERS ==========
PHASE = 1
MAX_RETRIES = 2
MAX_STEPS = 25  # Maximum number of steps before failing
ACTION_TIMEOUT = 10000  # 10 seconds timeout for actions
# Execution Modes:
# 0 - Automatic Mode: Processes all instructions without manual intervention
# 1 - Interactive Mode: Requires Enter press after each instruction for manual review
MODE = 0

# Knowledge base configuration
MAX_CONTEXT_LENGTH = int(os.getenv("MAX_CONTEXT_LENGTH", "2000"))  # Maximum context length in characters
KNOWLEDGE_BASE_TYPE = os.getenv("KNOWLEDGE_BASE_TYPE", "graphrag")  # Type of knowledge base to use

# Directory to store all browser sessions
os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)

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

def update_trajectory(dirs: Dict[str, str], step_idx: int, screenshot: str, axtree: str, action_code: str, action_description: str, page, user_message_file: str = None, llm_output=None, targeting_data_file: str = None, element_summary: str = None, annotation_id: str = None) -> None:
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
                    "thought": f'I need to click and type "{text}" into the input field.',
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
                        
                        # Extract the accessibility tree for backward compatibility
                        tree = comprehensive_data["accessibility_tree"]
                        
                        # Save the accessibility tree
                        with open(axtree_file, 'w', encoding='utf-8') as f:
                            json.dump(tree, f, indent=2, ensure_ascii=False)
                        
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

                    # Filter the accessibility tree for Gmail to remove inbox elements
                    if url and ('mail.google.com' in url or 'gmail.com' in url):
                        filtered_tree = filter_accessibility_tree(tree, url)
                        # If filtering fails, use original tree
                        if filtered_tree is None or (isinstance(filtered_tree, dict) and not filtered_tree.get('children')):
                            # print("⚠️ Warning: Filtering failed, using original tree")
                            filtered_tree = tree
                    else:
                        # For non-Gmail sites, use original tree
                        filtered_tree = tree
                    

                    # Prepare context with past trajectories
                    enhanced_context = ""
                    if trajectory_context:
                        enhanced_context = f"\n\n{trajectory_context}\n\n"
                    
                    # Create structured JSON element summary for GPT
                    element_summary = ""
                    if comprehensive_data and 'targeting_data' in comprehensive_data:
                        # Create structured data for GPT
                        elements_data = []
                        for elem in comprehensive_data['targeting_data']:
                            annotation_id = elem.get('annotation_id', '?')
                            role = elem.get('element_info', {}).get('role', 'unknown')
                            name = elem.get('element_info', {}).get('name', 'unnamed')
                            elements_data.append({
                                "annotation_id": str(annotation_id),
                                "role": role,
                                "name": name
                            })
                        
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
                                tree = comprehensive_data["accessibility_tree"]
                                
                                # Save the accessibility tree
                                with open(axtree_file, 'w', encoding='utf-8') as f:
                                    json.dump(tree, f, indent=2, ensure_ascii=False)
                                
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
                                
                                # Filter the accessibility tree for Gmail to remove inbox elements
                                if url and ('mail.google.com' in url or 'gmail.com' in url):
                                    filtered_tree = filter_accessibility_tree(tree, url)
                                    # If filtering fails, use original tree
                                    if filtered_tree is None or (isinstance(filtered_tree, dict) and not filtered_tree.get('children')):
                                        # print("⚠️ Warning: Filtering failed, using original tree")
                                        filtered_tree = tree
                                else:
                                    # For non-Gmail sites, use original tree
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
            executor.submit(run_for_account, account, chrome_exec, phase, search_context=False)
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

if __name__ == "__main__":
    main() 