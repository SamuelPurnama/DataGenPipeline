import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont
import random

class GoogleCalendarBoundingBoxTest:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.data_dir = self.base_dir / "data"
        self.browser_sessions_dir = self.data_dir / "browser_sessions"
        self.boundingboxes_dir = self.data_dir / "boundingboxes"
        
        # Ensure directories exist
        self.browser_sessions_dir.mkdir(parents=True, exist_ok=True)
        self.boundingboxes_dir.mkdir(parents=True, exist_ok=True)
        
    def create_session_folder(self, timestamp):
        """Create organized session folder structure"""
        session_dir = self.boundingboxes_dir / f"session_{timestamp}"
        session_dir.mkdir(exist_ok=True)
        
        # Create subfolders
        (session_dir / "raw_data").mkdir(exist_ok=True)
        (session_dir / "annotated_elements").mkdir(exist_ok=True)
        (session_dir / "screenshots").mkdir(exist_ok=True)
        
        return session_dir
    
    def create_targeting_data(self, elements, timestamp):
        """Create comprehensive data for targeting elements with Playwright"""
        targeting_data = []
        
        for i, element in enumerate(elements):
            # Create multiple targeting strategies for each element
            element_data = {
                "annotation_id": i + 1,
                "element_info": {
                    "name": self.clean_text_for_selector(element.get('name', '')),
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
                "playwright_selectors": self.generate_playwright_selectors(element),
                "interaction_suggestions": self.suggest_interactions(element)
            }
            
            targeting_data.append(element_data)
        
        return targeting_data
    
    def clean_text_for_selector(self, text):
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
    
    def generate_playwright_selectors(self, element):
        """Generate multiple Playwright selector strategies for an element"""
        selectors = []
        
        # Clean the element name for use in selectors
        clean_name = self.clean_text_for_selector(element.get('name', ''))
        
        # Strategy 1: By role and name
        if element.get('role') and clean_name:
            selectors.append({
                "type": "role_and_name",
                "selector": f"page.get_by_role('{element['role']}', name='{clean_name}')",
                "priority": "high"
            })
        
        # Strategy 2: By aria-label
        if clean_name:
            selectors.append({
                "type": "aria_label",
                "selector": f"page.get_by_label('{clean_name}')",
                "priority": "high"
            })
        
        # Strategy 3: By text content
        if clean_name and element.get('tagName') in ['button', 'a']:
            selectors.append({
                "type": "text",
                "selector": f"page.get_by_text('{clean_name}')",
                "priority": "medium"
            })
        
        # Strategy 4: By CSS selector (ID)
        if element.get('id'):
            selectors.append({
                "type": "css_id",
                "selector": f"page.locator('#{element['id']}')",
                "priority": "high"
            })
        
        # Strategy 5: By CSS selector (combined)
        css_parts = []
        if element.get('tagName'):
            css_parts.append(element['tagName'])
        if element.get('className'):
            # Take first class for simplicity
            first_class = element['className'].split()[0] if element['className'] else ''
            if first_class:
                css_parts.append(f".{first_class}")
        
        if css_parts:
            selectors.append({
                "type": "css_combined",
                "selector": f"page.locator('{''.join(css_parts)}')",
                "priority": "medium"
            })
        
        # Strategy 6: By XPath (coordinates fallback)
        selectors.append({
            "type": "coordinates",
            "selector": f"page.mouse.click({element.get('x', 0) + element.get('width', 0)//2}, {element.get('y', 0) + element.get('height', 0)//2})",
            "priority": "low"
        })
        
        return selectors
    
    def suggest_interactions(self, element):
        """Suggest appropriate Playwright interactions for an element"""
        suggestions = []
        
        role = element.get('role', '').lower()
        tag = element.get('tagName', '').lower()
        element_type = element.get('type', '').lower()
        
        if role == 'button' or tag == 'button':
            suggestions.extend([
                "click()",
                "hover()",
                "focus()"
            ])
        elif role == 'link' or tag == 'a':
            suggestions.extend([
                "click()",
                "hover()"
            ])
        elif role == 'textbox' or tag == 'input':
            if element_type in ['text', 'email', 'password', 'search']:
                suggestions.extend([
                    "fill('your_text_here')",
                    "type('your_text_here')",
                    "clear()",
                    "focus()"
                ])
            elif element_type == 'checkbox':
                suggestions.extend([
                    "check()",
                    "uncheck()",
                    "set_checked(True)"
                ])
            elif element_type == 'radio':
                suggestions.extend([
                    "check()"
                ])
        elif role == 'combobox' or tag == 'select':
            suggestions.extend([
                "select_option('option_value')",
                "click()"
            ])
        elif role == 'tab':
            suggestions.extend([
                "click()",
                "focus()"
            ])
        elif role == 'menuitem':
            suggestions.extend([
                "click()",
                "hover()"
            ])
        
        # Add common interactions for all elements
        suggestions.extend([
            "bounding_box()",
            "screenshot()",
            "is_visible()",
            "is_enabled()"
        ])
        
        return list(set(suggestions))  # Remove duplicates
    
    async def _get_all_interactive_elements_playwright_native(self, page):
        """Get all interactive elements using Playwright's native methods - most reliable approach"""
        elements = []
        
        # Define roles we want to capture with Playwright's built-in methods
        interactive_roles = [
            'button', 'link', 'textbox', 'combobox', 'checkbox', 
            'radio', 'tab', 'menuitem', 'option', 'searchbox',
            'slider', 'spinbutton', 'switch', 'listbox'
        ]
        
        for role in interactive_roles:
            try:
                print(f"  Searching for {role} elements...")
                # Get all elements with this role using Playwright's built-in method
                role_elements = await page.get_by_role(role).all()
                
                for element in role_elements:
                    try:
                        # Get bounding box BEFORE any action using Playwright's method
                        bbox = await element.bounding_box()
                        
                        # Only include elements that are visible and have valid dimensions
                        if bbox and bbox['width'] > 0 and bbox['height'] > 0:
                            # Get element properties using Playwright's methods
                            name = await element.get_attribute('aria-label') or \
                                   await element.text_content() or \
                                   await element.get_attribute('title') or \
                                   await element.get_attribute('placeholder') or \
                                   await element.get_attribute('value') or ''
                            
                            # Get additional DOM properties
                            tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                            element_id = await element.get_attribute('id') or ''
                            class_name = await element.get_attribute('class') or ''
                            href = await element.get_attribute('href') or ''
                            element_type = await element.get_attribute('type') or ''
                            disabled = await element.evaluate('el => el.disabled') or False
                            checked = await element.evaluate('el => el.checked')
                            selected = await element.evaluate('el => el.selected')
                            
                            elements.append({
                                'name': name.strip()[:200],  # Limit length but be generous
                                'role': role,  # This comes directly from Playwright role
                                'value': await element.get_attribute('value') or '',
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
                                'source': 'playwright_native'  # Mark as native Playwright source
                            })
                            
                    except Exception as e:
                        # Skip elements that can't be processed (hidden, removed, etc.)
                        continue
                        
            except Exception as e:
                # Skip roles that don't exist or cause errors
                print(f"    No {role} elements found or error: {e}")
                continue
        
        print(f"  Playwright-native approach found {len(elements)} elements")
        return elements
    
    def is_already_logged_in(self, page, timeout: int = 5000) -> bool:
        """
        Check if the user is already logged into Google by looking for absence of login elements.
        
        Args:
            page: Playwright page object
            timeout: Timeout in milliseconds for the check
            
        Returns:
            bool: True if already logged in, False otherwise
        """
        try:
            # Check for absence of sign-in related text/buttons
            sign_in_indicators = [
                'text="Sign in"',
                'text="sign in"', 
                'text="Sign In"',
                'text="SIGN IN"',
                'input[type="email"]',
                'input[type="password"]',
                'text="Email"',
                'text="Password"',
                'text="Enter your email"',
                'text="Enter your password"',
                '[placeholder*="email"]',
                '[placeholder*="password"]',
                'button:has-text("Next")',
                'text="Use another account"',
                'text="Choose an account"'
            ]
            
            # If any sign-in indicators are present, we're not logged in
            for indicator in sign_in_indicators:
                try:
                    if page.locator(indicator).count() > 0:
                        print(f"🔍 Found login indicator: {indicator}")
                        return False
                except:
                    continue
            
            # Additional check: if URL contains login-related paths
            current_url = page.url
            if any(login_path in current_url for login_path in ['accounts.google.com', '/signin', '/login']):
                print(f"🔍 URL suggests login page: {current_url}")
                return False
            
            # If we're on calendar.google.com and no login indicators found, we're likely logged in
            if 'calendar.google.com' in current_url:
                print(f"✅ On Google Calendar and no login indicators found")
                return True
            
            return False
        except Exception as e:
            print(f"⚠️ Error checking login status: {e}")
            return False
        
    async def get_interactable_elements_from_axtree(self, page):
        """Get all elements using multiple approaches: Playwright native, accessibility tree, and DOM fallback"""
        try:
            # Step 1: Try Playwright-native approach first (most reliable)
            print("🎯 Getting elements using Playwright-native approach...")
            native_elements = await self._get_all_interactive_elements_playwright_native(page)
            print(f"✅ Found {len(native_elements)} elements using Playwright-native approach")
            
            # Step 2: Get the accessibility tree for additional elements (backup approach)
            print("🔍 Getting accessibility tree from Playwright...")
            ax_tree = await page.accessibility.snapshot()
            
            # Step 3: Extract all elements from the tree
            all_ax_elements = []
            if ax_tree:
                self._extract_all_elements_from_ax_tree(ax_tree, all_ax_elements)
            
            print(f"📋 Found {len(all_ax_elements)} total elements from accessibility tree")
            
            # Step 4: Get bounding boxes for accessibility tree elements using JavaScript (for comparison)
            js_elements_with_boxes = await self._get_bounding_boxes_for_ax_elements(page, all_ax_elements)
            
            print(f"🔧 Found {len(js_elements_with_boxes)} elements via JavaScript DOM matching")
            
            # Step 5: Combine native and accessibility tree elements with deduplication
            all_elements = native_elements.copy()
            
            # Add JavaScript elements that aren't already covered by native approach
            for js_elem in js_elements_with_boxes:
                # Check if we already have this element from native approach
                is_duplicate = False
                for native_elem in native_elements:
                    # Consider elements the same if they have similar position and name
                    if (abs(js_elem['x'] - native_elem['x']) < 5 and 
                        abs(js_elem['y'] - native_elem['y']) < 5 and
                        abs(js_elem['width'] - native_elem['width']) < 10 and
                        abs(js_elem['height'] - native_elem['height']) < 10):
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    all_elements.append(js_elem)
            
            print(f"🔀 Combined total: {len(all_elements)} unique elements from all approaches")
            elements_with_boxes = all_elements
            
            # If we didn't find many elements, add a fallback to find all interactive DOM elements
            if len(elements_with_boxes) < 10:
                print("Low element count, adding fallback DOM element detection...")
                fallback_elements = await self._get_all_interactive_dom_elements(page)
                print(f"Found {len(fallback_elements)} additional elements from DOM fallback")
                
                # Merge and deduplicate with priority: Playwright native > Accessibility tree > Fallback DOM
                all_elements_final = elements_with_boxes + fallback_elements
                # Smart deduplication: prioritize by source reliability
                unique_elements = []
                seen_positions = set()
                
                # First pass: Add all Playwright native elements (highest priority)
                for elem in all_elements_final:
                    if elem.get('source') == 'playwright_native':
                        pos = (elem['x'], elem['y'], elem['width'], elem['height'])
                        if pos not in seen_positions:
                            unique_elements.append(elem)
                            seen_positions.add(pos)
                
                # Second pass: Add accessibility tree elements not already covered
                for elem in all_elements_final:
                    if elem.get('source') == 'playwright_axtree':
                        pos = (elem['x'], elem['y'], elem['width'], elem['height'])
                        if pos not in seen_positions:
                            unique_elements.append(elem)
                            seen_positions.add(pos)
                
                # Third pass: Add fallback elements only if position not already covered
                for elem in all_elements_final:
                    if elem.get('source') == 'fallback_dom':
                        pos = (elem['x'], elem['y'], elem['width'], elem['height'])
                        if pos not in seen_positions:
                            unique_elements.append(elem)
                            seen_positions.add(pos)
                
                print(f"Total unique elements after deduplication: {len(unique_elements)}")
                return unique_elements
            
            return elements_with_boxes
            
        except Exception as e:
            print(f"Error getting accessibility tree: {e}")
            return []
    
    def _extract_all_elements_from_ax_tree(self, node, elements, depth=0):
        """Recursively extract ALL potentially interactive elements from accessibility tree nodes"""
        if not node or depth > 20:  # Prevent infinite recursion
            return
            
        # More permissive criteria for including elements
        should_include = False
        
        # Include if has a role (any role)
        if node.get('role'):
            should_include = True
            
        # Include if it's focusable
        if node.get('focusable'):
            should_include = True
            
        # Include if it has interactive properties
        if (node.get('clickable') or 
            node.get('checked') is not None or
            node.get('selected') is not None or
            node.get('expanded') is not None):
            should_include = True
            
        # Include if it has a name or value (could be interactive)
        if node.get('name') or node.get('value'):
            should_include = True
            
        if should_include:
            elements.append({
                'name': node.get('name', ''),
                'role': node.get('role', ''),
                'value': node.get('value', ''),
                'description': node.get('description', ''),
                'checked': node.get('checked'),
                'disabled': node.get('disabled', False),
                'expanded': node.get('expanded'),
                'focused': node.get('focused', False),
                'selected': node.get('selected'),
                'level': node.get('level'),
                'valuetext': node.get('valuetext', ''),
                'orientation': node.get('orientation', ''),
                'keyshortcuts': node.get('keyshortcuts', ''),
                'roledescription': node.get('roledescription', ''),
                'focusable': node.get('focusable', False),
                'clickable': node.get('clickable', False)
            })
        
        # Recursively process children
        children = node.get('children', [])
        for child in children:
            self._extract_all_elements_from_ax_tree(child, elements, depth + 1)
    
    async def _get_bounding_boxes_for_ax_elements(self, page, ax_elements):
        """Get bounding boxes for all accessibility elements using JavaScript"""
        
        # Convert None values and Python booleans for JavaScript compatibility
        clean_elements = []
        for element in ax_elements:
            clean_element = {}
            for key, value in element.items():
                if value is None:
                    clean_element[key] = ""
                elif isinstance(value, bool):
                    clean_element[key] = "true" if value else "false"
                else:
                    clean_element[key] = value
            clean_elements.append(clean_element)
        
        # Create a JavaScript function that processes all elements at once
        import json
        js_code = f"""
        () => {{
            const axElements = {json.dumps(clean_elements)};
            const elementsWithBoxes = [];
            
            for (let axElement of axElements) {{
                const name = axElement.name || '';
                const role = axElement.role || '';
                const value = axElement.value || '';
                
                // Try to find the DOM element
                let domElement = null;
                
                // Strategy 1: Find by exact role and name/text match
                if (role && name) {{
                    const roleSelector = `[role="${{role}}"]`;
                    const candidates = document.querySelectorAll(roleSelector);
                    
                    for (let candidate of candidates) {{
                        const candidateText = (
                            candidate.getAttribute('aria-label') || 
                            candidate.getAttribute('title') || 
                            candidate.textContent?.trim() || 
                            candidate.getAttribute('placeholder') || 
                            candidate.value || ''
                        );
                        
                        if (candidateText === name || 
                            (name.length > 3 && candidateText.includes(name)) ||
                            (candidateText.length > 3 && name.includes(candidateText))) {{
                            domElement = candidate;
                            break;
                        }}
                    }}
                }}
                
                // Strategy 2: Find by tag-based selectors if role search failed
                if (!domElement && name) {{
                    const tagSelectors = {{
                        'button': 'button, input[type="button"], input[type="submit"], input[type="reset"], [role="button"]',
                        'link': 'a[href], [role="link"]',
                        'textbox': 'input[type="text"], input:not([type]), textarea, [role="textbox"]',
                        'searchbox': 'input[type="search"], [role="searchbox"]',
                        'checkbox': 'input[type="checkbox"], [role="checkbox"]',
                        'radio': 'input[type="radio"], [role="radio"]',
                        'combobox': 'select, [role="combobox"]',
                        'option': 'option, [role="option"]',
                        'tab': '[role="tab"]',
                        'menuitem': '[role="menuitem"]',
                        'slider': 'input[type="range"], [role="slider"]',
                        'spinbutton': 'input[type="number"], [role="spinbutton"]'
                    }};
                    
                    const selector = tagSelectors[role];
                    if (selector) {{
                        const candidates = document.querySelectorAll(selector);
                        for (let candidate of candidates) {{
                            const candidateText = (
                                candidate.getAttribute('aria-label') || 
                                candidate.getAttribute('title') || 
                                candidate.textContent?.trim() || 
                                candidate.getAttribute('placeholder') || 
                                candidate.value || ''
                            );
                            
                            if (candidateText === name || 
                                (name.length > 3 && candidateText.includes(name)) ||
                                (candidateText.length > 3 && name.includes(candidateText))) {{
                                domElement = candidate;
                                break;
                            }}
                        }}
                    }}
                }}
                
                // Strategy 3: Broad search for any potentially interactive element with matching text
                if (!domElement && name && name.length > 2) {{
                    const interactiveSelectors = [
                        'button', 'a', 'input', 'select', 'textarea',
                        '[onclick]', '[onmousedown]', '[onkeydown]', '[tabindex]',
                        '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
                        '[role="checkbox"]', '[role="radio"]', '[role="option"]',
                        '[contenteditable="true"]', '[draggable="true"]'
                    ];
                    
                    const allInteractive = document.querySelectorAll(interactiveSelectors.join(', '));
                    for (let candidate of allInteractive) {{
                        const candidateText = (
                            candidate.getAttribute('aria-label') || 
                            candidate.getAttribute('title') || 
                            candidate.textContent?.trim() || 
                            candidate.getAttribute('placeholder') || 
                            candidate.value || 
                            candidate.getAttribute('alt') || ''
                        );
                        
                        if (candidateText === name || 
                            (name.length > 3 && candidateText.includes(name)) ||
                            (candidateText.length > 3 && name.includes(candidateText))) {{
                            domElement = candidate;
                            break;
                        }}
                    }}
                }}
                
                if (!domElement) {{
                    continue;
                }}
                
                const rect = domElement.getBoundingClientRect();
                const style = window.getComputedStyle(domElement);
                
                // Skip elements that are not visible or have zero size
                if (rect.width <= 2 || rect.height <= 2 || 
                    style.visibility === 'hidden' || 
                    style.display === 'none' ||
                    style.opacity === '0') {{
                    continue;
                }}
                
                // Only include elements that are within the viewport
                if (rect.bottom < 0 || rect.top > window.innerHeight || 
                    rect.right < 0 || rect.left > window.innerWidth) {{
                    continue;
                }}
                
                elementsWithBoxes.push({{
                    name: name,
                    role: role,  // This comes from Playwright accessibility tree
                    value: value,
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    tagName: domElement.tagName.toLowerCase(),
                    type: domElement.type || '',
                    href: domElement.href || '',
                    disabled: domElement.disabled || false,
                    checked: domElement.checked,
                    selected: domElement.selected,
                    id: domElement.id || '',
                    className: domElement.className || '',
                    source: 'playwright_axtree'  // Mark as accessibility tree source
                }});
            }}
            
            return elementsWithBoxes;
        }}
        """
        
        try:
            result = await page.evaluate(js_code)
            return result
        except Exception as e:
            print(f"Error getting bounding boxes: {e}")
            return []
    
    async def _get_all_interactive_dom_elements(self, page):
        """Fallback: Find only truly interactive DOM elements"""
        js_code = """
        () => {
            const elements = [];
            
            // More selective list - only truly clickable/interactable elements
            const interactiveSelectors = [
                'button',
                'a[href]',
                'input[type="button"]',
                'input[type="submit"]',
                'input[type="reset"]',
                'input[type="text"]',
                'input[type="email"]',
                'input[type="password"]',
                'input[type="search"]',
                'input[type="checkbox"]',
                'input[type="radio"]',
                'select',
                'textarea',
                '[role="button"]',
                '[role="link"]',
                '[role="tab"]',
                '[role="menuitem"]',
                '[role="checkbox"]',
                '[role="radio"]',
                '[role="textbox"]',
                '[role="searchbox"]',
                '[role="combobox"]'
            ];
            
            const allInteractive = document.querySelectorAll(interactiveSelectors.join(', '));
            
            for (let element of allInteractive) {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                
                // Skip elements that are not visible or have zero size
                if (rect.width <= 3 || rect.height <= 3 || 
                    style.visibility === 'hidden' || 
                    style.display === 'none' ||
                    style.opacity === '0') {
                    continue;
                }
                
                // Only include elements that are within the viewport
                if (rect.bottom < 0 || rect.top > window.innerHeight || 
                    rect.right < 0 || rect.left > window.innerWidth) {
                    continue;
                }
                
                // Additional filter: check if element is actually interactive
                const isActuallyInteractive = (
                    element.tagName === 'BUTTON' ||
                    element.tagName === 'A' ||
                    element.tagName === 'INPUT' ||
                    element.tagName === 'SELECT' ||
                    element.tagName === 'TEXTAREA' ||
                    element.getAttribute('role') === 'button' ||
                    element.getAttribute('role') === 'link' ||
                    element.getAttribute('role') === 'tab' ||
                    element.getAttribute('role') === 'menuitem' ||
                    element.hasAttribute('onclick') ||
                    (element.hasAttribute('tabindex') && element.getAttribute('tabindex') !== '-1')
                );
                
                if (!isActuallyInteractive) {
                    continue;
                }
                
                // Skip tiny elements that are likely decorative
                if (rect.width < 10 || rect.height < 10) {
                    continue;
                }
                
                const name = (
                    element.getAttribute('aria-label') || 
                    element.getAttribute('title') || 
                    element.textContent?.trim()?.substring(0, 50) || 
                    element.getAttribute('placeholder') || 
                    element.getAttribute('alt') || 
                    element.value || 
                    `${element.tagName.toLowerCase()}_element`
                );
                
                // Skip elements with empty or very short names unless they're form inputs
                if (name.length < 2 && !['input', 'select', 'textarea'].includes(element.tagName.toLowerCase())) {
                    continue;
                }
                
                elements.push({
                    name: name,
                    role: element.getAttribute('role') || element.tagName.toLowerCase(),
                    value: element.value || '',
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    tagName: element.tagName.toLowerCase(),
                    type: element.type || '',
                    href: element.href || '',
                    disabled: element.disabled || false,
                    checked: element.checked,
                    selected: element.selected,
                    id: element.id || '',
                    className: element.className || '',
                    source: 'fallback_dom'  // Mark as fallback source
                });
            }
            
            return elements;
        }
        """
        
        try:
            result = await page.evaluate(js_code)
            return result
        except Exception as e:
            print(f"Error getting DOM elements: {e}")
            return []

    
    async def get_accessibility_tree_cdp(self, page):
        """Get the accessibility tree using Chrome DevTools Protocol"""
        try:
            # Get the accessibility tree using CDP
            cdp = await page.context.new_cdp_session(page)
            await cdp.send('Accessibility.enable')
            
            # Get the full accessibility tree
            tree = await cdp.send('Accessibility.getFullAXTree')
            
            await cdp.detach()
            return tree
        except Exception as e:
            print(f"Error getting CDP accessibility tree: {e}")
            # Fallback: get basic accessibility info
            return await self.get_basic_accessibility_info(page)
    
    async def get_accessibility_tree_playwright(self, page):
        """Get the accessibility tree using Playwright's built-in snapshot"""
        try:
            # Get the accessibility tree using Playwright's method
            tree = await page.accessibility.snapshot()
            return tree
        except Exception as e:
            print(f"Error getting Playwright accessibility tree: {e}")
            return None
    
    async def get_accessibility_tree(self, page):
        """Legacy method - redirects to CDP version for backward compatibility"""
        return await self.get_accessibility_tree_cdp(page)
    
    async def get_basic_accessibility_info(self, page):
        """Fallback method to get basic accessibility information"""
        js_code = """
        () => {
            const getAccessibilityInfo = (element) => {
                return {
                    tagName: element.tagName,
                    role: element.getAttribute('role') || element.tagName.toLowerCase(),
                    name: element.getAttribute('aria-label') || 
                          element.getAttribute('aria-labelledby') || 
                          element.textContent?.trim()?.substring(0, 50) || '',
                    description: element.getAttribute('aria-describedby') || '',
                    value: element.value || element.getAttribute('aria-valuenow') || '',
                    checked: element.checked,
                    disabled: element.disabled,
                    hidden: element.hidden || element.getAttribute('aria-hidden') === 'true',
                    expanded: element.getAttribute('aria-expanded'),
                    selected: element.getAttribute('aria-selected'),
                    level: element.getAttribute('aria-level'),
                    setSize: element.getAttribute('aria-setsize'),
                    positionInSet: element.getAttribute('aria-posinset')
                };
            };
            
            const traverseElement = (element, depth = 0) => {
                if (depth > 10) return null; // Prevent infinite recursion
                
                const info = getAccessibilityInfo(element);
                const children = [];
                
                for (let child of element.children) {
                    const childInfo = traverseElement(child, depth + 1);
                    if (childInfo) children.push(childInfo);
                }
                
                return {
                    ...info,
                    children: children.length > 0 ? children : undefined
                };
            };
            
            return traverseElement(document.body);
        }
        """
        
        return await page.evaluate(js_code)
    
    def generate_colors(self, count):
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
    
    def annotate_screenshot(self, screenshot_path, elements):
        """Annotate screenshot with bounding boxes"""
        # Open the screenshot
        image = Image.open(screenshot_path)
        draw = ImageDraw.Draw(image)
        
        # Try to load a font
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 12)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 12)
            except:
                font = ImageFont.load_default()
        
        # Generate colors for each element
        colors = self.generate_colors(len(elements))
        
        # Draw bounding boxes and labels
        for i, element in enumerate(elements):
            x, y, width, height = element['x'], element['y'], element['width'], element['height']
            color = colors[i]
            
            # Draw bounding box
            draw.rectangle(
                [x, y, x + width, y + height],
                outline=color,
                width=2
            )
            
            # Create label text (just the index number)
            label = f"{i+1}"
            
            # Draw label background
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            label_x = max(0, min(x, image.width - text_width - 4))
            label_y = max(0, y - text_height - 4)
            
            draw.rectangle(
                [label_x, label_y, label_x + text_width + 4, label_y + text_height + 4],
                fill=color,
                outline=color
            )
            
            # Draw label text
            draw.text(
                (label_x + 2, label_y + 2),
                label,
                fill='white',
                font=font
            )
            
            # Draw click coordinate marker (center point of the element)
            click_x = x + width // 2
            click_y = y + height // 2
            
            # Draw a small circle at the click coordinates
            circle_radius = 3
            draw.ellipse(
                [click_x - circle_radius, click_y - circle_radius, 
                 click_x + circle_radius, click_y + circle_radius],
                fill='yellow',
                outline='black',
                width=1
            )
            
            # Add click coordinates text below the index number
            coords_text = f"({click_x},{click_y})"
            coords_bbox = draw.textbbox((0, 0), coords_text, font=font)
            coords_width = coords_bbox[2] - coords_bbox[0]
            coords_height = coords_bbox[3] - coords_bbox[1]
            
            # Position coordinates below the index number
            coords_x = label_x
            coords_y = label_y + text_height + 8
            
            # Draw coordinates background
            draw.rectangle(
                [coords_x, coords_y, coords_x + coords_width + 4, coords_y + coords_height + 4],
                fill='black',
                outline='white',
                width=1
            )
            
            # Draw coordinates text
            draw.text(
                (coords_x + 2, coords_y + 2),
                coords_text,
                fill='white',
                font=font
            )
        
        # Save annotated image
        annotated_path = screenshot_path.replace('.png', '_annotated.png')
        image.save(annotated_path)
        
        return annotated_path
    
    async def run(self):
        """Main execution function"""
        print("Starting Google Calendar bounding box test...")
        
        async with async_playwright() as p:
            # Launch browser with persistent context (dedicated folder for bounding box test)
            sessions_dir = Path("bounding_box_sessions")
            sessions_dir.mkdir(exist_ok=True)
            user_data_dir = sessions_dir / "bounding_box_chrome_session"
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=False,
                args=[
                    '--no-first-run',
                    '--no-default-browser-check', 
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--window-size=1920,1080'  # Set window size for consistent screenshots
                ]
            )
            
            try:
                # Get or create a page
                if len(browser.pages) > 0:
                    page = browser.pages[0]
                else:
                    page = await browser.new_page()
                
                print("Navigating to Google Calendar...")
                await page.goto('https://docs.google.com', timeout=60000, wait_until='networkidle')
                
                # Wait a bit for the page to fully load
                await page.wait_for_timeout(3000)
                
                # Check if we're actually logged in to Google Calendar
                print("Checking login status...")
                is_logged_in = self.is_already_logged_in(page)
                
                if not is_logged_in:
                    print("❌ Not logged in to Google Calendar!")
                    print("🔑 Please log in manually in the browser window that just opened.")
                    print("📋 Steps:")
                    print("   1. Click 'Sign in' if you see it")
                    print("   2. Enter your Google credentials")
                    print("   3. Complete any 2FA if required")
                    print("   4. Wait until you see the Google Calendar interface")
                    print("   5. Press Enter here to continue...")
                    print("")
                    print("⚠️  IMPORTANT: Keep this terminal window open! The browser will close if you close this.")
                    
                    # Wait for user to complete login
                    input("⏳ Press Enter after you've logged in to Google Calendar...")
                    
                    # Wait a moment for the page to stabilize after login
                    await page.wait_for_timeout(2000)
                    
                    # Verify login was successful
                    is_logged_in = self.is_already_logged_in(page)
                    if not is_logged_in:
                        print("❌ Still not logged in. Please check your login and try again.")
                        print("🔄 Keeping browser open for you to try again...")
                        input("⏳ Press Enter after you've successfully logged in...")
                        
                        # Check one more time
                        is_logged_in = self.is_already_logged_in(page)
                        if not is_logged_in:
                            print("❌ Login verification failed. Exiting...")
                            return
                
                print("✅ Successfully logged in to Google Calendar!")
                
                # Generate timestamp for session
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Create organized session folder
                session_dir = self.create_session_folder(timestamp)
                print(f"Created session folder: {session_dir}")
                
                print("Getting interactable elements from accessibility tree...")
                elements = await self.get_interactable_elements_from_axtree(page)
                print(f"Found {len(elements)} interactable elements")
                
                print("Taking screenshot...")
                original_screenshot = session_dir / "screenshots" / f"original_{timestamp}.png"
                await page.screenshot(path=str(original_screenshot), full_page=False)
                
                print("Getting raw accessibility trees (both CDP and Playwright)...")
                raw_axtree_cdp = await self.get_accessibility_tree_cdp(page)
                raw_axtree_playwright = await self.get_accessibility_tree_playwright(page)
                
                print("Annotating screenshot with bounding boxes...")
                annotated_screenshot = session_dir / "screenshots" / f"annotated_{timestamp}.png"
                self.annotate_screenshot(str(original_screenshot), elements)
                # Move annotated file to proper location
                annotated_source = str(original_screenshot).replace('.png', '_annotated.png')
                if os.path.exists(annotated_source):
                    os.rename(annotated_source, str(annotated_screenshot))
                
                print("Creating targeting data...")
                targeting_data = self.create_targeting_data(elements, timestamp)
                
                # Save raw accessibility tree from CDP (detailed format)
                raw_axtree_cdp_path = session_dir / "raw_data" / f"raw_accessibility_tree_cdp_{timestamp}.json"
                with open(raw_axtree_cdp_path, 'w', encoding='utf-8') as f:
                    json.dump(raw_axtree_cdp, f, indent=2, ensure_ascii=False)
                
                # Save raw accessibility tree from Playwright (clean format)
                raw_axtree_playwright_path = session_dir / "raw_data" / f"raw_accessibility_tree_playwright_{timestamp}.json"
                with open(raw_axtree_playwright_path, 'w', encoding='utf-8') as f:
                    json.dump(raw_axtree_playwright, f, indent=2, ensure_ascii=False)
                
                # Save annotated elements with targeting data
                targeting_data_path = session_dir / "annotated_elements" / f"targeting_data_{timestamp}.json"
                with open(targeting_data_path, 'w', encoding='utf-8') as f:
                    json.dump(targeting_data, f, indent=2, ensure_ascii=False)
                
                # Save raw elements data (what we found)
                raw_elements_path = session_dir / "raw_data" / f"raw_elements_{timestamp}.json"
                with open(raw_elements_path, 'w', encoding='utf-8') as f:
                    json.dump(elements, f, indent=2, ensure_ascii=False)
                
                # Create session summary with element statistics
                element_stats = {}
                for element in elements:
                    role = element.get('role', 'unknown')
                    if role in element_stats:
                        element_stats[role] += 1
                    else:
                        element_stats[role] = 1
                
                session_summary = {
                    'session_info': {
                        'timestamp': timestamp,
                        'url': 'https://calendar.google.com',
                        'total_elements_found': len(elements),
                        'session_folder': str(session_dir)
                    },
                    'files_generated': {
                        'raw_data': {
                            'raw_accessibility_tree_cdp': str(raw_axtree_cdp_path),
                            'raw_accessibility_tree_playwright': str(raw_axtree_playwright_path),
                            'raw_elements': str(raw_elements_path)
                        },
                        'screenshots': {
                            'original': str(original_screenshot),
                            'annotated': str(annotated_screenshot)
                        },
                        'annotated_elements': {
                            'targeting_data': str(targeting_data_path)
                        }
                    },
                    'element_statistics': {
                        'by_role': element_stats,
                        'total_count': len(elements),
                        'has_targeting_info': len([e for e in targeting_data if e['playwright_selectors']])
                    },
                    'usage_instructions': {
                        'targeting_elements': "Use targeting_data.json to find Playwright selectors for each annotated element",
                        'annotation_reference': "Numbers in annotated screenshot correspond to annotation_id in targeting_data.json",
                        'raw_data': "raw_data/ contains unprocessed accessibility tree and element data",
                        'selector_priority': "Use 'high' priority selectors first, then 'medium', then 'low'"
                    }
                }
                
                summary_path = session_dir / f"session_summary_{timestamp}.json"
                with open(summary_path, 'w', encoding='utf-8') as f:
                    json.dump(session_summary, f, indent=2, ensure_ascii=False)
                
                print(f"\n🎯 Session complete! Files saved in: {session_dir}")
                print(f"\n📁 Generated files:")
                print(f"   📊 Session summary: {summary_path.name}")
                print(f"   🖼️  Screenshots: {len(list((session_dir / 'screenshots').glob('*')))} files")
                print(f"   📋 Raw data: {len(list((session_dir / 'raw_data').glob('*')))} files") 
                print(f"   🎯 Targeting data: {len(list((session_dir / 'annotated_elements').glob('*')))} files")
                print(f"\n🔍 Found {len(elements)} interactable elements:")
                for role, count in element_stats.items():
                    print(f"   - {role}: {count}")
                print(f"\n📖 To target elements: Check annotation numbers in screenshot, then use targeting_data_{timestamp}.json")
                
            except Exception as e:
                print(f"Error during execution: {e}")
                raise
            
            finally:
                # Keep browser open for inspection
                print("\n🔓 Browser session will remain open for inspection...")
                print("📋 Close the browser manually when done.")
                print("💡 Tip: If browser closed unexpectedly, your session data is saved and you can re-run the script.")

async def main():
    test = GoogleCalendarBoundingBoxTest()
    await test.run()

if __name__ == "__main__":
    asyncio.run(main())
