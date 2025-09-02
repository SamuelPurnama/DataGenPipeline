import random
import os
import sys
import json
import re
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasets import load_dataset
from tqdm import tqdm
from utils.generate_instruction import generate_instructions
from utils.prompt_augmentation import generate_augmented_instructions
from utils.element_utils import get_comprehensive_element_data, annotate_screenshot_with_bounding_boxes
from playwright.sync_api import sync_playwright
from utils.google_auth import ensure_google_login


def discover_navigable_elements(page):
    """
    Discover all elements that have dropdowns, options, or can lead somewhere else.
    This function identifies elements that can expand, navigate, or show additional content.
    """
    navigable_elements = {
        'dropdowns': [],
        'navigation_links': [],
        'expandable_elements': [],
        'modal_triggers': [],
        'tab_elements': [],
        'accordion_elements': []
    }
    
    try:
        # 1. Find all interactive elements
        all_elements = page.query_selector_all('button, a, [role="button"], [tabindex], [onclick], [data-toggle], [aria-haspopup]')
        
        for element in all_elements:
            if not element.is_visible():
                continue
                
            # Get bounding box while we still have the ElementHandle
            try:
                bbox = element.bounding_box()
                bbox_data = bbox if bbox else None
            except Exception as e:
                bbox_data = None
                print(f"⚠️ Could not get bounding box: {e}")
            
            element_info = {
                'text': element.inner_text().strip(),
                'tag': element.evaluate('el => el.tagName.toLowerCase()'),
                'id': element.get_attribute('id'),
                'class': element.get_attribute('class'),
                'href': element.get_attribute('href'),
                'role': element.get_attribute('role'),
                'aria_haspopup': element.get_attribute('aria-haspopup'),
                'aria_expanded': element.get_attribute('aria-expanded'),
                'data_toggle': element.get_attribute('data-toggle'),
                'data_target': element.get_attribute('data-target'),
                'onclick': element.get_attribute('onclick'),
                'bbox': bbox_data,
                'selector_info': {
                    'type': 'playwright_element',
                    'description': f"Playwright element: {element.evaluate('el => el.tagName.toLowerCase()')} with text '{element.inner_text().strip()[:50]}...'"
                }
            }
            
            # 2. Check for dropdown indicators
            is_dropdown = False
            dropdown_reason = None
            
            if element_info['aria_haspopup'] == 'true':
                is_dropdown = True
                dropdown_reason = 'aria-haspopup="true"'
            elif element_info['data_toggle'] and 'dropdown' in element_info['data_toggle']:
                is_dropdown = True
                dropdown_reason = f'data-toggle="{element_info["data_toggle"]}"'
            elif element_info['class'] and any(dropdown_class in element_info['class'] for dropdown_class in ['dropdown', 'menu', 'popup']):
                is_dropdown = True
                dropdown_reason = f'class contains dropdown/menu/popup'
            
            if is_dropdown:
                navigable_elements['dropdowns'].append({
                    **element_info,
                    'type': 'dropdown',
                    'reason': dropdown_reason
                })
            
            # 3. Check for navigation links
            if element_info['tag'] == 'a' and element_info['href']:
                if element_info['href'].startswith('http') or element_info['href'].startswith('/'):
                    navigable_elements['navigation_links'].append({
                        **element_info,
                        'type': 'navigation_link',
                        'destination': element_info['href']
                    })
            
            # 4. Check for expandable elements
            if element_info['aria_expanded'] is not None:
                navigable_elements['expandable_elements'].append({
                    **element_info,
                    'type': 'expandable',
                    'current_state': element_info['aria_expanded']
                })
            
            # 5. Check for modal triggers
            if element_info['data_target'] and 'modal' in element_info['data_target']:
                navigable_elements['modal_triggers'].append({
                    **element_info,
                    'type': 'modal_trigger',
                    'modal_target': element_info['data_target']
                })
            
            # 6. Check for tab elements
            if element_info['data_toggle'] and 'tab' in element_info['data_toggle']:
                navigable_elements['tab_elements'].append({
                    **element_info,
                    'type': 'tab',
                    'tab_function': element_info['data_toggle']
                })
            
            # 7. Check for accordion elements
            if element_info['data_toggle'] and 'collapse' in element_info['data_toggle']:
                navigable_elements['accordion_elements'].append({
                    **element_info,
                    'type': 'accordion',
                    'collapse_function': element_info['data_toggle']
                })
        
        # 8. Find elements with specific patterns that suggest navigation
        pattern_elements = page.query_selector_all('[class*="nav"], [class*="menu"], [class*="tab"], [class*="accordion"]')
        
        for element in pattern_elements:
            if not element.is_visible():
                continue
                
            class_name = element.get_attribute('class') or ''
            text = element.inner_text().strip()
            
            if text and any(pattern in class_name.lower() for pattern in ['nav', 'menu', 'tab', 'accordion']):
                # Check if we already found this element
                already_found = any(
                    elem['selector'] == element 
                    for category in navigable_elements.values() 
                    for elem in category
                )
                
                if not already_found:
                    navigable_elements['expandable_elements'].append({
                        'text': text,
                        'tag': element.tag_name,
                        'class': class_name,
                        'type': 'pattern_based_navigation',
                        'pattern': next(pattern for pattern in ['nav', 'menu', 'tab', 'accordion'] if pattern in class_name.lower()),
                        'selector': element
                    })
        
        print(f"🔍 Discovered navigable elements:")
        print(f"   📋 Dropdowns: {len(navigable_elements['dropdowns'])}")
        print(f"   🔗 Navigation links: {len(navigable_elements['navigation_links'])}")
        print(f"   📂 Expandable elements: {len(navigable_elements['expandable_elements'])}")
        print(f"   🪟 Modal triggers: {len(navigable_elements['modal_triggers'])}")
        print(f"   📑 Tab elements: {len(navigable_elements['tab_elements'])}")
        print(f"   🗂️ Accordion elements: {len(navigable_elements['accordion_elements'])}")
        
        return navigable_elements
        
    except Exception as e:
        print(f"❌ Error discovering navigable elements: {e}")
        return navigable_elements


def discover_all_url_changes(page, base_url, max_depth=3):
    """
    Discover ALL possible ways URLs can change on a website.
    This includes href links, JavaScript navigation, form submissions, SPA navigation, etc.
    """
    url_changes = {
        'href_links': [],
        'javascript_navigation': [],
        'form_submissions': [],
        'programmatic_changes': [],
        'spa_navigation': [],
        'discovery_stats': {
            'total_elements_found': 0,
            'href_links_count': 0,
            'javascript_navigation_count': 0,
            'form_submissions_count': 0,
            'spa_navigation_count': 0
        }
    }
    
    try:
        print(f"🔍 Discovering URL change mechanisms on: {base_url}")
        
        # 1. Find all <a href> links
        href_links = page.query_selector_all('a[href]')
        for link in href_links:
            try:
                href = link.get_attribute('href')
                if href:
                    # Convert relative URLs to absolute
                    if href.startswith('/'):
                        full_url = base_url.rstrip('/') + href
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = base_url.rstrip('/') + '/' + href
                    
                    # Only include URLs from the same domain
                    if base_url in full_url:
                        bbox = link.bounding_box()
                        url_changes['href_links'].append({
                            'url': full_url,
                            'text': link.inner_text().strip(),
                            'element_type': 'a',
                            'href': href,
                            'id': link.get_attribute('id'),
                            'class': link.get_attribute('class'),
                            'role': link.get_attribute('role'),
                            'bounding_box': bbox,
                            'type': 'href_link',
                            'description': f"Link element that navigates to {full_url}"
                        })
            except Exception as e:
                print(f"⚠️ Error processing href link: {e}")
                continue
        
        # 2. Find elements with onclick that might change URL
        onclick_elements = page.query_selector_all('[onclick*="location"], [onclick*="window"], [onclick*="history"]')
        for element in onclick_elements:
            try:
                onclick = element.get_attribute('onclick')
                if onclick:
                    bbox = element.bounding_box()
                    url_changes['javascript_navigation'].append({
                        'element_type': element.evaluate('el => el.tagName.toLowerCase()'),
                        'text': element.inner_text().strip(),
                        'onclick': onclick,
                        'id': element.get_attribute('id'),
                        'class': element.get_attribute('class'),
                        'bounding_box': bbox,
                        'type': 'javascript_navigation',
                        'description': f"Element with onclick that may change URL: {onclick[:100]}..."
                    })
            except Exception as e:
                print(f"⚠️ Error processing onclick element: {e}")
                continue
        
        # 3. Find forms that might change URL
        forms = page.query_selector_all('form[action]')
        for form in forms:
            try:
                action = form.get_attribute('action')
                if action:
                    # Convert relative URLs to absolute
                    if action.startswith('/'):
                        full_action = base_url.rstrip('/') + action
                    elif action.startswith('http'):
                        full_action = action
                    else:
                        full_action = base_url.rstrip('/') + '/' + action
                    
                    if base_url in full_action:
                        bbox = form.bounding_box()
                        url_changes['form_submissions'].append({
                            'action': full_action,
                            'method': form.get_attribute('method', 'GET'),
                            'id': form.get_attribute('id'),
                            'class': form.get_attribute('class'),
                            'bounding_box': bbox,
                            'type': 'form_submission',
                            'description': f"Form that submits to {full_action} using {form.get_attribute('method', 'GET')} method"
                        })
            except Exception as e:
                print(f"⚠️ Error processing form: {e}")
                continue
        
        # 4. Look for SPA navigation patterns
        spa_elements = page.query_selector_all('[data-route], [data-page], [data-url], [data-navigation]')
        for element in spa_elements:
            try:
                bbox = element.bounding_box()
                url_changes['spa_navigation'].append({
                    'element_type': element.evaluate('el => el.tagName.toLowerCase()'),
                    'text': element.inner_text().strip(),
                    'data_route': element.get_attribute('data-route'),
                    'data_page': element.get_attribute('data-page'),
                    'data_url': element.get_attribute('data-url'),
                    'data_navigation': element.get_attribute('data-navigation'),
                    'id': element.get_attribute('id'),
                    'class': element.get_attribute('class'),
                    'bounding_box': bbox,
                    'type': 'spa_navigation',
                    'description': f"SPA navigation element with data attributes"
                })
            except Exception as e:
                print(f"⚠️ Error processing SPA element: {e}")
                continue
        
        # 5. Find elements with navigation-related classes
        nav_classes = page.query_selector_all('[class*="nav"], [class*="route"], [class*="page"], [class*="link"]')
        for element in nav_classes:
            try:
                class_name = element.get_attribute('class')
                if class_name and any(nav_word in class_name.lower() for nav_word in ['nav', 'route', 'page', 'link']):
                    # Check if we already found this element
                    already_found = any(
                        elem.get('bounding_box') == element.bounding_box() 
                        for category in url_changes.values() 
                        if isinstance(category, list)
                        for elem in category
                    )
                    
                    if not already_found:
                        bbox = element.bounding_box()
                        url_changes['spa_navigation'].append({
                            'element_type': element.evaluate('el => el.tagName.toLowerCase()'),
                            'text': element.inner_text().strip(),
                            'class': class_name,
                            'id': element.get_attribute('id'),
                            'bounding_box': bbox,
                            'type': 'spa_navigation',
                            'description': f"Element with navigation-related class: {class_name}"
                        })
            except Exception as e:
                print(f"⚠️ Error processing nav class element: {e}")
                continue
        
        # 6. Look for elements with navigation-related attributes
        nav_attrs = page.query_selector_all('[data-navigation], [data-route], [data-page], [data-href]')
        for element in nav_attrs:
            try:
                # Check if we already found this element
                already_found = any(
                    elem.get('bounding_box') == element.bounding_box() 
                    for category in url_changes.values() 
                    if isinstance(category, list)
                    for elem in category
                )
                
                if not already_found:
                    bbox = element.bounding_box()
                    url_changes['spa_navigation'].append({
                        'element_type': element.evaluate('el => el.tagName.toLowerCase()'),
                        'type': 'spa_navigation',
                        'description': f"Element with navigation-related data attributes"
                    })
            except Exception as e:
                print(f"⚠️ Error processing nav attr element: {e}")
                continue
        
        # Create a simple, clean navigation structure
        navigation_map = {
            'current_page': base_url,
            'navigation': []
        }
        
        # Process href links (direct navigation)
        for link in url_changes['href_links']:
            destination = link['url']
            navigation_map['navigation'].append({
                'element': link['text'] or 'Link',
                'destination': destination
            })
        
        # Process JavaScript navigation
        for element in url_changes['javascript_navigation']:
            onclick = element['onclick']
            potential_url = None
            
            # Look for URL patterns in onclick
            if 'location.href' in onclick:
                url_match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
                if url_match:
                    potential_url = url_match.group(1)
            elif 'window.location' in onclick:
                url_match = re.search(r"window\.location\s*=\s*['\"]([^'\"]+)['\"]", onclick)
                if url_match:
                    potential_url = url_match.group(1)
            
            if potential_url:
                # Convert to absolute URL
                if potential_url.startswith('/'):
                    full_url = base_url.rstrip('/') + potential_url
                elif potential_url.startswith('http'):
                    full_url = potential_url
                else:
                    full_url = base_url.rstrip('/') + '/' + potential_url
                
                if base_url in full_url:
                    navigation_map['navigation'].append({
                        'element': element['text'] or 'Button',
                        'destination': full_url
                    })
        
        # Process form submissions
        for form in url_changes['form_submissions']:
            destination = form['action']
            navigation_map['navigation'].append({
                'element': 'Form',
                'destination': destination
            })
        
        # Process SPA navigation
        for element in url_changes['spa_navigation']:
            route = element.get('data_route') or element.get('data_page') or element.get('data_url')
            if route:
                # Convert to full URL
                if route.startswith('/'):
                    full_url = base_url.rstrip('/') + route
                else:
                    full_url = base_url.rstrip('/') + '/' + route
                
                navigation_map['navigation'].append({
                    'element': element['text'] or 'SPA Element',
                    'destination': full_url
                })
        
        # Look for additional navigation patterns that might be missed
        print(f"🔍 Looking for additional navigation elements...")
        
        # Find buttons with navigation-related text
        navigation_keywords = [
            'go to', 'navigate', 'visit', 'open', 'view', 'see', 'browse', 'explore',
            'search', 'find', 'look up', 'check', 'access', 'enter', 'continue',
            'next', 'previous', 'back', 'forward', 'home', 'menu', 'settings',
            'profile', 'account', 'dashboard', 'calendar', 'mail', 'drive',
            'maps', 'news', 'shopping', 'travel', 'books', 'photos', 'videos'
        ]
        
        # Find all buttons and clickable elements
        all_buttons = page.query_selector_all('button, [role="button"], [tabindex], [onclick], [data-action], [data-navigation]')
        
        for button in all_buttons:
            try:
                if not button.is_visible():
                    continue
                    
                button_text = button.inner_text().strip().lower()
                button_class = button.get_attribute('class') or ''
                button_id = button.get_attribute('id') or ''
                
                # Check if button text suggests navigation
                is_navigation_button = False
                navigation_hint = None
                
                for keyword in navigation_keywords:
                    if keyword in button_text:
                        is_navigation_button = True
                        navigation_hint = f"Text contains '{keyword}'"
                        break
                
                # Check if button has navigation-related classes
                if not is_navigation_button:
                    nav_classes = ['nav', 'navigation', 'route', 'page', 'link', 'menu', 'tab']
                    for nav_class in nav_classes:
                        if nav_class in button_class.lower():
                            is_navigation_button = True
                            navigation_hint = f"Class contains '{nav_class}'"
                            break
                
                # Check if button has navigation-related ID
                if not is_navigation_button:
                    nav_ids = ['nav', 'navigation', 'route', 'page', 'link', 'menu', 'tab']
                    for nav_id in nav_ids:
                        if nav_id in button_id.lower():
                            is_navigation_button = True
                            navigation_hint = f"ID contains '{nav_id}'"
                            break
                
                # Check if button has data attributes suggesting navigation
                data_nav = button.get_attribute('data-navigation') or button.get_attribute('data-route') or button.get_attribute('data-page')
                if data_nav:
                    is_navigation_button = True
                    navigation_hint = f"Data attribute: {data_nav}"
                
                if is_navigation_button:
                    # Try to extract potential destination from various sources
                    potential_destination = None
                    
                    # Check onclick for URL patterns
                    onclick = button.get_attribute('onclick')
                    if onclick:
                        # Look for various URL patterns
                        url_patterns = [
                            r"location\.href\s*=\s*['\"]([^'\"]+)['\"]",
                            r"window\.location\s*=\s*['\"]([^'\"]+)['\"]",
                            r"window\.open\s*\(\s*['\"]([^'\"]+)['\"]",
                            r"navigate\s*\(\s*['\"]([^'\"]+)['\"]",
                            r"router\.push\s*\(\s*['\"]([^'\"]+)['\"]",
                            r"history\.pushState\s*\(\s*[^,]*,\s*['\"]([^'\"]+)['\"]"
                        ]
                        
                        for pattern in url_patterns:
                            match = re.search(pattern, onclick)
                            if match:
                                potential_destination = match.group(1)
                                break
                    
                    # Check for href-like attributes
                    if not potential_destination:
                        href_like = button.get_attribute('data-href') or button.get_attribute('data-url') or button.get_attribute('data-link')
                        if href_like:
                            potential_destination = href_like
                    
                    # If we found a destination, add it to navigation
                    if potential_destination:
                        # Convert to absolute URL
                        if potential_destination.startswith('/'):
                            full_url = base_url.rstrip('/') + potential_destination
                        elif potential_destination.startswith('http'):
                            full_url = potential_destination
                        else:
                            full_url = base_url.rstrip('/') + '/' + potential_destination
                        
                        if base_url in full_url:
                            navigation_map['navigation'].append({
                                'element': button.inner_text().strip() or 'Navigation Button',
                                'destination': full_url,
                                'hint': navigation_hint
                            })
                    else:
                        # Add as potential navigation without known destination
                        navigation_map['navigation'].append({
                            'element': button.inner_text().strip() or 'Navigation Button',
                            'destination': 'Unknown (likely navigation)',
                            'hint': navigation_hint
                        })
                        
            except Exception as e:
                print(f"⚠️ Error processing button: {e}")
                continue
        
        # Find elements with navigation-related ARIA labels
        aria_elements = page.query_selector_all('[aria-label], [aria-labelledby]')
        for element in aria_elements:
            try:
                if not element.is_visible():
                    continue
                    
                aria_label = element.get_attribute('aria-label') or ''
                if aria_label:
                    # Check if aria-label suggests navigation
                    for keyword in navigation_keywords:
                        if keyword in aria_label.lower():
                            # Check if we already have this element
                            element_text = element.inner_text().strip()
                            already_exists = any(
                                nav['element'] == element_text 
                                for nav in navigation_map['navigation']
                            )
                            
                            if not already_exists:
                                navigation_map['navigation'].append({
                                    'element': element_text or 'ARIA Navigation',
                                    'destination': 'Unknown (ARIA suggests navigation)',
                                    'hint': f"ARIA label: {aria_label}"
                                })
                            break
                            
            except Exception as e:
                continue
        
        print(f"✅ Navigation mapping complete:")
        print(f"   📍 Current page: {base_url}")
        print(f"   🔗 Total navigation elements: {len(navigation_map['navigation'])}")
        
        return navigation_map
        
    except Exception as e:
        print(f"❌ Error discovering URL changes: {e}")
        return url_changes


# ========== CONFIGURABLE PARAMETERS ==========
from config import (
    PHASE1_NUM_INSTRUCTIONS,
    PHASE2_NUM_INSTRUCTIONS,
    RESULTS_DIR,
    URL,
    ACCOUNTS,
    PERSONAS_PER_ACCOUNT,
    BROWSER_SESSIONS_DIR
)

chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")
PERSONAHUB_DATA_PATH = "persona.jsonl"  # Path to PersonaHub data file
SCREENSHOT_PATH = "screenshot.png"
PHASE = 1

# Directory to store all browser sessions
os.makedirs(BROWSER_SESSIONS_DIR, exist_ok=True)

def write_documentation(persona, url, instructions, augmented_instructions, results_dir=RESULTS_DIR, filename=f"instructions_phase{PHASE}.json"):
    import json

    # Ensure the results directory exists
    os.makedirs(results_dir, exist_ok=True)
    file_path = os.path.join(results_dir, filename)

    # Load existing data if file exists, else start with empty list
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    # Append new entry
    data.append({
        "persona": persona,
        "url": url,
        "instructions": instructions,
        "augmented_instructions": augmented_instructions
    })

    # Write back to file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_instructions_for_account(account, persona, num_instructions):
    """Generate instructions for a specific account and persona."""
    user_data_dir = os.path.join(BROWSER_SESSIONS_DIR, account["user_data_dir"])
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=chrome_executable_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.new_page()
        page.goto(URL)
        
        # Ensure we're logged in before proceeding
        ensure_google_login(page, account["email"], account["password"], URL)
            
        # Take screenshot
        screenshot_path = SCREENSHOT_PATH
        page.screenshot(path=screenshot_path)
        
        # Get comprehensive element data for phase 2
        comprehensive_data = None
        if PHASE == 2:
            print(f"🔍 Collecting comprehensive element data for {persona}...")
            comprehensive_data = get_comprehensive_element_data(page, URL)
            
            # Discover navigable elements (dropdowns, navigation, etc.)
            print(f"🧭 Discovering navigable elements for {persona}...")
            navigable_elements = discover_navigable_elements(page)
            
            # Save navigable elements to a separate JSON file
            navigable_elements_file = f"navigable_elements_{persona.replace(' ', '_')}.json"
            with open(navigable_elements_file, 'w', encoding='utf-8') as f:
                json.dump(navigable_elements, f, indent=2, ensure_ascii=False)
            print(f"📄 Saved navigable elements to: {navigable_elements_file}")
            
            # Discover all URL change mechanisms
            print(f"🔗 Discovering URL change mechanisms for {persona}...")
            url_changes = discover_all_url_changes(page, URL)
            
            # Save URL changes to a separate JSON file
            url_changes_file = f"url_changes_{persona.replace(' ', '_')}.json"
            with open(url_changes_file, 'w', encoding='utf-8') as f:
                json.dump(url_changes, f, indent=2, ensure_ascii=False)
            print(f"📄 Saved URL changes to: {url_changes_file}")
            
            # Add both to comprehensive data
            comprehensive_data['navigable_elements'] = navigable_elements
            comprehensive_data['url_changes'] = url_changes
            
            # Create annotated screenshot with navigable elements using existing utility
            print(f"🎨 Creating annotated screenshot with navigable elements...")
            
            # Convert navigable elements to targeting data format for the existing function
            navigable_targeting_data = []
            for category, elements in navigable_elements.items():
                for i, element in enumerate(elements):
                    try:
                        # Use the stored bounding box
                        bbox = element.get('bbox')
                        if bbox:
                            navigable_targeting_data.append({
                                'annotation_id': f"{category[:3].upper()}{i+1}",
                                'bounding_box': bbox,
                                'element_info': {
                                    'role': element.get('type', category),
                                    'name': element.get('text', ''),
                                    'tag_name': element.get('tag', ''),
                                    'class_name': element.get('class', ''),
                                    'id': element.get('id', '')
                                }
                            })
                    except Exception as e:
                        print(f"⚠️ Could not get bounding box for {category} element: {e}")
                        continue
            
            # Use existing function to create annotated screenshot
            annotated_screenshot = annotate_screenshot_with_bounding_boxes(
                screenshot_path, 
                navigable_targeting_data,
                f"navigable_elements_{persona.replace(' ', '_')}.png"
            )
            
            # Add annotated screenshot path to comprehensive data
            if annotated_screenshot:
                comprehensive_data['annotated_screenshot'] = annotated_screenshot
            
            # Save enhanced comprehensive element data to file
            comprehensive_file = f"comprehensive_elements_{persona.replace(' ', '_')}.json"
            with open(comprehensive_file, 'w', encoding='utf-8') as f:
                json.dump(comprehensive_data, f, indent=2, ensure_ascii=False)
            print(f"📄 Saved enhanced comprehensive element data to: {comprehensive_file}")
            
            # Extract targeting data for instruction generation
            axtree = comprehensive_data.get('targeting_data', [])
        else:
            axtree = None
            
        # Generate instructions and augment them
        instructions = generate_instructions(
            persona, PHASE, num_instructions=num_instructions, 
            screenshot_path=screenshot_path, axtree=axtree
        )

        print(f"Generated {len(instructions)} instructions for account {account['email']}")
            
        augmented_instructions = generate_augmented_instructions(
            instructions, screenshot_path=screenshot_path
        )

        browser.close()
        return instructions, augmented_instructions

def main():
    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    dataset = load_dataset("proj-persona/PersonaHub", data_files=PERSONAHUB_DATA_PATH)['train']
    shuffled = dataset.shuffle(seed=random.randint(0, 9999))  # Use a random seed each run
    
    # Calculate total personas needed
    total_personas = PERSONAS_PER_ACCOUNT * len(ACCOUNTS)
    personas = shuffled[:total_personas]['persona']
    num_instructions = PHASE2_NUM_INSTRUCTIONS if PHASE == 2 else PHASE1_NUM_INSTRUCTIONS

    print(f"Processing {total_personas} personas total ({PERSONAS_PER_ACCOUNT} per account)")

    if PHASE == 1:
        # Phase 1: Use first account only
        account = ACCOUNTS[0]
        for persona in tqdm(personas[:PERSONAS_PER_ACCOUNT], desc="Processing personas"):
            instructions, augmented_instructions = generate_instructions_for_account(
                account, persona, num_instructions
            )
            write_documentation(persona, URL, instructions, augmented_instructions)
    else:
        # Phase 2: Each account processes its assigned personas
        for i, account in enumerate(ACCOUNTS):
            start_idx = i * PERSONAS_PER_ACCOUNT
            end_idx = start_idx + PERSONAS_PER_ACCOUNT
            
            print(f"\nAccount {account['email']} processing personas {start_idx} to {end_idx-1}")
            
            # Process this account's assigned personas
            for persona in tqdm(personas[start_idx:end_idx], desc=f"Processing with account {i+1}"):
                try:
                    instructions, augmented = generate_instructions_for_account(
                        account, persona, num_instructions
                    )
                    print(f"Generated {len(instructions)} instructions for persona: {persona}")
                    write_documentation(persona, URL, instructions, augmented)
                except Exception as e:
                    print(f"Error processing persona {persona} with account {account['email']}: {e}")
                    # Write error state to maintain documentation
                    write_documentation(persona, URL, 
                                     [f"ERROR: {e}"] * num_instructions,
                                     [f"ERROR: {e}"] * num_instructions)

if __name__ == "__main__":
    main()