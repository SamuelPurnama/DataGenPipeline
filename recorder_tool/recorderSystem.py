#!/usr/bin/env python3
"""
Enhanced Interaction Logger
Captures clicks, keyboard input, and form filling with Playwright-style selectors
"""

import asyncio
import json
import time
import uuid
import signal
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont
import os
from urllib.parse import urlparse


class EnhancedInteractionLogger:
    """Enhanced interaction logger with Playwright selectors and screenshots"""
    
    def __init__(self, output_dir: str = "../data/interaction_logs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate UUID for this session
        self.session_id = str(uuid.uuid4())
        self.session_name = f"session_{self.session_id}"
        
        # Create session directory with UUID
        self.session_dir = self.output_dir / self.session_name
        self.session_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        self.images_dir = self.session_dir / "images"
        self.images_dir.mkdir(exist_ok=True)
        
        self.axtree_dir = self.session_dir / "axtree"
        self.axtree_dir.mkdir(exist_ok=True)
        
        self.user_message_dir = self.session_dir / "user_message"
        self.user_message_dir.mkdir(exist_ok=True)
        
        self.interactions = []
        self.start_time = None
        self.step_counter = 0
        
        # Store trajectory data in the new format
        self.trajectory_data = {}
        
        # Store current axtree data
        self.current_axtree_data = None
        
        # Flag to track if we're shutting down
        self.shutting_down = False
        
        # Deduplication tracking
        self.last_interaction = None
        self.last_interaction_time = 0
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        print(f"\n⏹️ Received signal {signum}, shutting down gracefully...")
        self.shutting_down = True
    
    async def start_logging(self, url: str = "https://mail.google.com/"):
        """Start logging interactions"""
        self.start_time = time.time()
        
        # Create browser sessions directory
        sessions_dir = Path("../recorder_sessions")
    sessions_dir.mkdir(exist_ok=True)
        
        async with async_playwright() as p:
            # Launch browser with persistent context
            user_data_dir = sessions_dir / "recorder_chrome_session"
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=False,  # Keep browser visible
                args=[
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--window-size=1920,1080'  # Set window size for consistent screenshots
                ]
            )
            
            # Get the first page from the persistent context
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Set a realistic user agent to avoid detection
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            # Add script to hide automation and ensure persistence
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                // Store interaction logs in localStorage for persistence across navigation
                if (!window.interactionLogs) {
                    window.interactionLogs = JSON.parse(localStorage.getItem('interactionLogs') || '[]');
                }
                
                // Save logs to localStorage periodically
                setInterval(() => {
                    if (window.interactionLogs && window.interactionLogs.length > 0) {
                        localStorage.setItem('interactionLogs', JSON.stringify(window.interactionLogs));
                    }
                }, 1000);
                
                // Restore logs on page load
                window.addEventListener('load', () => {
                    const savedLogs = localStorage.getItem('interactionLogs');
                    if (savedLogs) {
                        window.interactionLogs = JSON.parse(savedLogs);
                    }
                });
                
                // Auto-reinject logging code on every page load
                function reinjectLogging() {
                    // Check if logging is already set up
                    if (window.loggingInitialized) {
                        console.log('Logging already initialized');
                        return;
                    }
                    
                    window.loggingInitialized = true;
                    console.log('Auto-reinjecting logging code...');
                    
                    // This will be replaced by the main logging code
                    // The main code will be injected after this init script
                }
                
                // Run on load and also periodically check
                window.addEventListener('load', reinjectLogging);
                setInterval(reinjectLogging, 5000); // Check every 5 seconds
            """)
            
            # Also add a more aggressive injection that runs on every page
            await page.add_init_script("""
                // This script runs on every page load
                console.log('Page loaded, setting up logging...');
                
                // Wait a bit for the page to be ready
                setTimeout(() => {
                    if (!window.loggingInitialized) {
                        console.log('Logging not initialized, triggering re-injection...');
                        // Signal to Python that we need re-injection
                        window.postMessage({type: 'NEED_REINJECTION'}, '*');
                    }
                }, 2000);
            """)
            
            # Listen to console messages from our JavaScript
            page.on("console", lambda msg: asyncio.create_task(self._on_console(msg, page)))
            
            # Listen for postMessage events from JavaScript
            async def handle_post_message(event):
                if event.get('type') == 'NEED_REINJECTION':
                    print("🔄 JavaScript requested re-injection...")
                    await re_inject_logging()
            
            page.on("page", lambda page: page.on("console", lambda msg: asyncio.create_task(handle_post_message(msg))))
            
            # Navigate to the page
            await page.goto(url)
            
            # Re-inject logging code on navigation
            re_injection_in_progress = False
            last_re_injection_time = 0
            
            async def re_inject_logging():
                try:
                    # Wait a bit for the page to load
                    await asyncio.sleep(2)
                    
                    # Check if page is still valid
                    if page.is_closed():
                        return
                    
                    # Re-inject the main logging code
                    await page.evaluate("""
                        // Check if logging is already set up
                        if (window.loggingInitialized) {
                            console.log('Logging already initialized');
                        } else {
                            window.loggingInitialized = true;
                            console.log('Logging initialized');
                        }
                    """)
                    
                    # Clean up existing listeners first
                    await page.evaluate("""
                        if (window.loggingCleanup) {
                            window.loggingCleanup();
                        }
                    """)
                    
                    # Actually re-inject the full logging JavaScript
                    await self._inject_full_logging_code(page)
                    
                    print("🔄 Re-injecting logging after navigation...")
                    
                except Exception as e:
                    print(f"⚠️ Error re-injecting logging: {e}")
            
            # Track current URL to detect actual navigation
            current_url = url
            
            def url_base_domain(url):
                parsed = urlparse(url)
                return (parsed.scheme, parsed.netloc)
            
            # Listen for navigation events - only re-inject when base domain actually changes
            async def handle_navigation(frame):
                nonlocal current_url
                try:
                    new_url = frame.url
                    if url_base_domain(new_url) != url_base_domain(current_url):
                        print(f"🌐 URL changed: {current_url} → {new_url}")
                        current_url = new_url
                        await re_inject_logging()
                except Exception as e:
                    print(f"⚠️ Error handling navigation: {e}")
            
            page.on("framenavigated", lambda frame: asyncio.create_task(handle_navigation(frame)))
            

            
            # Inject JavaScript to capture all interactions
            await self._inject_full_logging_code(page)
            
            # Add cleanup function to remove duplicate listeners
            await page.evaluate("""
                // Cleanup function to remove existing listeners
                if (window.loggingCleanup) {
                    window.loggingCleanup();
                }
                
                window.loggingCleanup = function() {
                    console.log('Cleaning up existing listeners...');
                    
                    // Remove click listeners
                    if (window.clickListener) {
                        document.removeEventListener('click', window.clickListener);
                    }
                    if (window.clickTypingListener) {
                        document.removeEventListener('click', window.clickTypingListener);
                    }
                    
                    // Remove keydown listeners  
                    if (window.keydownListener) {
                        document.removeEventListener('keydown', window.keydownListener);
                    }
                    if (window.debugKeydownListener) {
                        document.removeEventListener('keydown', window.debugKeydownListener);
                    }
                    if (window.typingKeydownListener) {
                        document.removeEventListener('keydown', window.typingKeydownListener);
                    }
                    
                    // Remove input listeners
                    if (window.inputListener) {
                        document.removeEventListener('input', window.inputListener);
                    }
                    
                    // Remove submit listeners
                    if (window.submitListener) {
                        document.removeEventListener('submit', window.submitListener);
                    }
                    
                    // Remove scroll listeners
                    if (window.scrollListener) {
                        document.removeEventListener('scroll', window.scrollListener);
                    }
                    if (window.elementScrollListener) {
                        // Remove from all elements that might have it
                        const allElements = document.querySelectorAll('*');
                        allElements.forEach(element => {
                            element.removeEventListener('scroll', window.elementScrollListener);
                        });
                    }
                    
                    // Remove hover listeners
                    if (window.hoverListener) {
                        document.removeEventListener('pointermove', window.hoverListener);
                    }
                    
                    // Remove popstate listeners
                    if (window.popstateListener) {
                        window.removeEventListener('popstate', window.popstateListener);
                    }
                    
                    // Remove beforeunload listeners
                    if (window.beforeunloadListener) {
                        window.removeEventListener('beforeunload', window.beforeunloadListener);
                    }
                    
                    // Remove load listeners
                    if (window.loadListener) {
                        window.removeEventListener('load', window.loadListener);
                    }
                    
                    console.log('Cleanup completed');
                };
            """)
            
            print(f"🎯 Started logging interactions on {url}")
            print(f"📁 Logs will be saved to: {self.session_dir / f'{self.session_id}_interactions.json'}")
            print(f"📸 Screenshots will be saved to: {self.images_dir}")
            print(f"🌲 Accessibility tree will be saved to: {self.axtree_dir}")
            print(f" User messages will be saved to: {self.user_message_dir}")
            print("💡 Interact with the page (click, type, fill forms). Press Ctrl+C to stop logging.")
            
            try:
                # Keep the browser open
                while not self.shutting_down:
                    await asyncio.sleep(0.1)
            except KeyboardInterrupt:
                print("\n⏹️  Stopping interaction logger...")
            finally:
                await self._save_logs()
                try:
                    await context.close()
                except:
                    pass
    
    async def _inject_full_logging_code(self, page):
        """Inject the complete logging JavaScript code"""
        await page.evaluate("""
            // Clean up existing listeners first
            if (window.loggingCleanup) {
                window.loggingCleanup();
            }

            window.loggingCleanup = function() {
                // Remove click listeners
                if (window.clickListener) {
                    document.removeEventListener('click', window.clickListener);
                }
                if (window.clickTypingListener) {
                    document.removeEventListener('click', window.clickTypingListener);
                }
                // Remove keydown listeners  
                if (window.keydownListener) {
                    document.removeEventListener('keydown', window.keydownListener);
                }
                if (window.debugKeydownListener) {
                    document.removeEventListener('keydown', window.debugKeydownListener);
                }
                if (window.typingKeydownListener) {
                    document.removeEventListener('keydown', window.typingKeydownListener);
                }
                // Remove input listeners
                if (window.inputListener) {
                    document.removeEventListener('input', window.inputListener);
                }
                // Remove submit listeners
                if (window.submitListener) {
                    document.removeEventListener('submit', window.submitListener);
                }
                // Remove scroll listeners
                if (window.scrollListener) {
                    document.removeEventListener('scroll', window.scrollListener);
                }
                if (window.elementScrollListener) {
                    const allElements = document.querySelectorAll('*');
                    allElements.forEach(element => {
                        element.removeEventListener('scroll', window.elementScrollListener);
                    });
                }
                // Remove hover listeners
                if (window.hoverListener) {
                    document.removeEventListener('pointermove', window.hoverListener);
                }
                // Remove popstate listeners
                if (window.popstateListener) {
                    window.removeEventListener('popstate', window.popstateListener);
                }
                // Remove beforeunload listeners
                if (window.beforeunloadListener) {
                    window.removeEventListener('beforeunload', window.beforeunloadListener);
                }
                // Remove load listeners
                if (window.loadListener) {
                    window.removeEventListener('load', window.loadListener);
                }
                // Reset all listener variables to undefined
                window.clickListener = undefined;
                window.clickTypingListener = undefined;
                window.keydownListener = undefined;
                window.debugKeydownListener = undefined;
                window.typingKeydownListener = undefined;
                window.inputListener = undefined;
                window.submitListener = undefined;
                window.scrollListener = undefined;
                window.elementScrollListener = undefined;
                window.hoverListener = undefined;
                window.popstateListener = undefined;
                window.beforeunloadListener = undefined;
                window.loadListener = undefined;
                window.loggingInitialized = false;
                console.log('Cleanup completed');
            };

            window.interactionLogs = [];
            window.lastInteractionElement = null;

            // --- Suppress navigation logging for 300ms after a click ---
            let lastClickTime = 0;
            let clickSuppressWindow = 300; // ms

            // Function to capture essential element properties
            function getEssentialElementProperties(element) {
                const rect = element.getBoundingClientRect();
                return {
                    tagName: element.tagName,
                    elementId: element.id || '',
                    elementClass: element.className || '',
                    elementText: element.textContent ? element.textContent.substring(0, 100) : '',
                    inputType: element.type || '',
                    value: element.value || '',
                    placeholder: element.placeholder || '',
                    required: element.required || false,
                    disabled: element.disabled || false,
                    ariaLabel: element.getAttribute('aria-label') || '',
                    role: element.getAttribute('role') || '',
                    dataTestid: element.getAttribute('data-testid') || '',
                    isVisible: rect.width > 0 && rect.height > 0,
                    isEnabled: !element.disabled,
                    isFocused: document.activeElement === element,
                    bbox: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    },
                    form: element.form ? element.form.id || '' : '',
                    name: element.name || '',
                    validationState: element.validity ? element.validity.valid ? 'valid' : 'invalid' : 'unknown',
                    errorMessage: element.validationMessage || ''
                };
            }
            
            // Function to get accessibility tree
            function getAccessibilityTree() {
                const tree = [];
                
                function traverseElement(element, depth = 0) {
                    const node = {
                        tagName: element.tagName,
                        role: element.getAttribute('role') || getDefaultRole(element),
                        name: element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || '',
                        id: element.id || '',
                        className: element.className || '',
                        value: element.value || '',
                        placeholder: element.getAttribute('placeholder') || '',
                        type: element.getAttribute('type') || '',
                        href: element.getAttribute('href') || '',
                        src: element.getAttribute('src') || '',
                        alt: element.getAttribute('alt') || '',
                        title: element.getAttribute('title') || '',
                        'data-testid': element.getAttribute('data-testid') || '',
                        depth: depth,
                        children: []
                    };
                    
                    for (let child of element.children) {
                        node.children.push(traverseElement(child, depth + 1));
                    }
                    
                    return node;
                }
                
                function getDefaultRole(element) {
                    if (element.tagName === 'BUTTON') return 'button';
                    if (element.tagName === 'A') return 'link';
                    if (element.tagName === 'INPUT') {
                        const type = element.type || 'text';
                        if (type === 'checkbox') return 'checkbox';
                        if (type === 'radio') return 'radio';
                        if (type === 'submit' || type === 'button') return 'button';
                        return 'textbox';
                    }
                    if (element.tagName === 'SELECT') return 'combobox';
                    if (element.tagName === 'TEXTAREA') return 'textbox';
                    if (element.tagName === 'FORM') return 'form';
                    return '';
                }
                
                return traverseElement(document.body);
            }
            
            // Function to get filtered accessibility tree (for Gmail)
            function getFilteredAccessibilityTree() {
                const tree = [];
                
                // Gmail inbox filtering function
                function shouldSkipElement(element) {
                    // ONLY skip Gmail inbox email rows (TR elements with zA class)
                    if (element.tagName === 'TR' && element.className && element.className.includes('zA')) {
                        return true;
                    }
                    
                    return false;
                }
                
                function traverseElement(element, depth = 0) {
                    // Skip Gmail inbox elements
                    if (shouldSkipElement(element)) {
                        return null;
                    }
                    
                    const node = {
                        tagName: element.tagName,
                        role: element.getAttribute('role') || getDefaultRole(element),
                        name: element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || '',
                        id: element.id || '',
                        className: element.className || '',
                        value: element.value || '',
                        placeholder: element.getAttribute('placeholder') || '',
                        type: element.getAttribute('type') || '',
                        href: element.getAttribute('href') || '',
                        src: element.getAttribute('src') || '',
                        alt: element.getAttribute('alt') || '',
                        title: element.getAttribute('title') || '',
                        'data-testid': element.getAttribute('data-testid') || '',
                        depth: depth,
                        children: []
                    };
                    
                    for (let child of element.children) {
                        const childNode = traverseElement(child, depth + 1);
                        if (childNode) {
                            node.children.push(childNode);
                        }
                    }
                    
                    return node;
                }
                
                function getDefaultRole(element) {
                    if (element.tagName === 'BUTTON') return 'button';
                    if (element.tagName === 'A') return 'link';
                    if (element.tagName === 'INPUT') {
                        const type = element.type || 'text';
                        if (type === 'checkbox') return 'checkbox';
                        if (type === 'radio') return 'radio';
                        if (type === 'submit' || type === 'button') return 'button';
                        return 'textbox';
                    }
                    if (element.tagName === 'SELECT') return 'combobox';
                    if (element.tagName === 'TEXTAREA') return 'textbox';
                    if (element.tagName === 'FORM') return 'form';
                    return '';
                }
                
                return traverseElement(document.body);
            }
            
            // Function to detect if current page is Gmail
            function isGmailPage() {
                const url = window.location.href;
                const hostname = window.location.hostname;
                
                // Check if it's Gmail
                return hostname.includes('gmail.com') || 
                       hostname.includes('mail.google.com') || 
                       url.includes('gmail.com') || 
                       url.includes('mail.google.com');
            }
            
            // Function to get appropriate accessibility tree based on current page
            function getAppropriateAccessibilityTree() {
                if (isGmailPage()) {
                    return getFilteredAccessibilityTree();
                } else {
                    return getAccessibilityTree();
                }
            }
            
            // Track clicks
            window.clickListener = function(e) {
                lastClickTime = Date.now(); // Set lastClickTime for navigation suppression
                const element = e.target;
                const selectors = generateSelectors(element);
                const essentialProperties = getEssentialElementProperties(element);
                const clickData = {
                    type: 'click',
                    timestamp: new Date().toISOString(),
                    x: e.clientX,
                    y: e.clientY,
                    element: element.tagName,
                    elementId: element.id || '',
                    elementClass: element.className || '',
                    elementText: element.textContent ? element.textContent.substring(0, 50) : '',
                    url: window.location.href,
                    pageTitle: document.title,
                    selectors: selectors,
                    bbox: essentialProperties.bbox,
                    essentialProperties: essentialProperties
                };
                window.interactionLogs.push(clickData);
                window.lastInteractionElement = element;
                console.log('INTERACTION_LOG:', JSON.stringify(clickData));
                // Also log accessibility tree (smart detection)
                const axtree = getAppropriateAccessibilityTree();
                console.log('AXTREE_LOG:', JSON.stringify(axtree));
            };
            document.addEventListener('click', window.clickListener);
            
            let currentlyHovered = null;
            let lastTypedElement = null;
            let typingTimeout = null;
            let lastTypingLogged = null; // Track last logged typing to prevent duplicates

            // Function to log typing completion
            function logTypingComplete(element) {
                // Prevent duplicate logging of the same typing
                const typingKey = element.id + ':' + element.value;
                if (lastTypingLogged === typingKey) {
                    return; // Already logged this typing
                }
                
                const selectors = generateSelectors(element);
                const essentialProperties = getEssentialElementProperties(element);
                
                const typingData = {
                    type: 'typing_complete',
                    timestamp: new Date().toISOString(),
                    value: element.value || '',
                    element: element.tagName,
                    elementId: element.id || '',
                    elementClass: element.className || '',
                    url: window.location.href,
                    pageTitle: document.title,
                    selectors: selectors,
                    bbox: essentialProperties.bbox,
                    essentialProperties: essentialProperties
                };
                window.interactionLogs.push(typingData);
                window.lastInteractionElement = element;
                lastTypingLogged = typingKey; // Mark as logged
                console.log('INTERACTION_LOG:', JSON.stringify(typingData));
                
                // Also log accessibility tree (smart detection)
                const axtree = getAppropriateAccessibilityTree();
                console.log('AXTREE_LOG:', JSON.stringify(axtree));
            }

            window.typingKeydownListener = function(e) {
                const element = e.target;
                
                // If we're typing in a different element, log the previous typing immediately
                if (lastTypedElement && lastTypedElement !== element && lastTypedElement.value) {
                    logTypingComplete(lastTypedElement);
                    if (typingTimeout) {
                        clearTimeout(typingTimeout);
                    }
                }
                
                // Clear previous timeout
                if (typingTimeout) {
                    clearTimeout(typingTimeout);
                }
                
                // Set new timeout to log when typing stops
                typingTimeout = setTimeout(function() {
                    if (lastTypedElement && lastTypedElement.value) {
                        logTypingComplete(lastTypedElement);
                    }
                }, 1000); // Wait 1 second after last keystroke
                
                lastTypedElement = element;
                
                // Also log Enter key immediately
                if (e.key === 'Enter') {
                    const selectors = generateSelectors(element);
                    const rect = element.getBoundingClientRect();
                    
                    const enterData = {
                        type: 'enter_pressed',
                        timestamp: new Date().toISOString(),
                        value: element.value || '',
                        element: element.tagName,
                        elementId: element.id || '',
                        elementClass: element.className || '',
                        url: window.location.href,
                        pageTitle: document.title,
                        selectors: selectors,
                        bbox: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        }
                    };
                    window.interactionLogs.push(enterData);
                    window.lastInteractionElement = element;
                    console.log('INTERACTION_LOG:', JSON.stringify(enterData));
                    
                    // Also log accessibility tree (smart detection)
                    const axtree = getAppropriateAccessibilityTree();
                    console.log('AXTREE_LOG:', JSON.stringify(axtree));
                    
                    // Clear timeout since Enter was pressed
                    if (typingTimeout) {
                        clearTimeout(typingTimeout);
                    }
                }
            };
            document.addEventListener('keydown', window.typingKeydownListener);
            
            // Global keyboard listener for all keyboard inputs
            window.keydownListener = function(e) {
                // Skip if it's a form element (already handled above)
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT' || e.target.contentEditable === 'true') {
                    return;
                }
                
                // Log all other keyboard inputs
                const keyboardData = {
                    type: 'keyboard_input',
                    timestamp: new Date().toISOString(),
                    key: e.key,
                    code: e.code,
                    keyCode: e.keyCode,
                    ctrlKey: e.ctrlKey,
                    altKey: e.altKey,
                    shiftKey: e.shiftKey,
                    metaKey: e.metaKey,
                    element: e.target.tagName,
                    elementId: e.target.id || '',
                    elementClass: e.target.className || '',
                    elementText: e.target.textContent ? e.target.textContent.substring(0, 50) : '',
                    url: window.location.href,
                    pageTitle: document.title,
                    selectors: generateSelectors(e.target),
                    bbox: {
                        x: e.target.getBoundingClientRect().x,
                        y: e.target.getBoundingClientRect().y,
                        width: e.target.getBoundingClientRect().width,
                        height: e.target.getBoundingClientRect().height
                    }
                };
                window.interactionLogs.push(keyboardData);
                console.log('INTERACTION_LOG:', JSON.stringify(keyboardData));
                
                // Also log accessibility tree (smart detection)
                const axtree = getAppropriateAccessibilityTree();
                console.log('AXTREE_LOG:', JSON.stringify(axtree));
            };
            document.addEventListener('keydown', window.keydownListener);
            
            // Also add a global keyboard listener that captures ALL keys (for testing)
            window.debugKeydownListener = function(e) {
                // Log every single keypress for debugging
                console.log('DEBUG: Key pressed:', e.key, 'on element:', e.target.tagName, e.target.className);
            };
            document.addEventListener('keydown', window.debugKeydownListener);
            
            // Also log typing when clicking elsewhere
            window.clickTypingListener = function(e) {
                if (lastTypedElement && lastTypedElement !== e.target && lastTypedElement.value) {
                    logTypingComplete(lastTypedElement);
                    if (typingTimeout) {
                        clearTimeout(typingTimeout);
                    }
                }
            };
            document.addEventListener('click', window.clickTypingListener);
            
            // Track input changes (only for non-keyboard events like paste, drag&drop, etc.)
            window.inputListener = function(e) {
                // Skip if this is from keyboard (we handle that in keydown)
                if (e.inputType && e.inputType.startsWith('insertText')) {
                    return;
                }
                
                const element = e.target;
                const selectors = generateSelectors(element);
                const rect = element.getBoundingClientRect();
                
                const inputData = {
                    type: 'input',
                    timestamp: new Date().toISOString(),
                    value: element.value ? element.value.substring(0, 100) : '',
                    element: element.tagName,
                    elementId: element.id || '',
                    elementClass: element.className || '',
                    elementText: element.textContent ? element.textContent.substring(0, 50) : '',
                    url: window.location.href,
                    pageTitle: document.title,
                    selectors: selectors,
                    bbox: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }
                };
                window.interactionLogs.push(inputData);
                window.lastInteractionElement = element;
                console.log('INTERACTION_LOG:', JSON.stringify(inputData));
                
                // Also log accessibility tree (smart detection)
                const axtree = getAppropriateAccessibilityTree();
                console.log('AXTREE_LOG:', JSON.stringify(axtree));
            };
            document.addEventListener('input', window.inputListener);
            
            // Track form submissions
            window.submitListener = function(e) {
                const element = e.target;
                const selectors = generateSelectors(element);
                const rect = element.getBoundingClientRect();
                
                const submitData = {
                    type: 'form_submit',
                    timestamp: new Date().toISOString(),
                    formId: element.id || '',
                    formAction: element.action || '',
                    url: window.location.href,
                    pageTitle: document.title,
                    selectors: selectors,
                    bbox: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }
                };
                window.interactionLogs.push(submitData);
                window.lastInteractionElement = element;
                console.log('INTERACTION_LOG:', JSON.stringify(submitData));
                
                // Also log accessibility tree (smart detection)
                const axtree = getAppropriateAccessibilityTree();
                console.log('AXTREE_LOG:', JSON.stringify(axtree));
            };
            document.addEventListener('submit', window.submitListener);
            
            // Track navigation events (DISABLED: do not log navigation events to Python)
            let lastUrl = window.location.href;
            let lastTitle = document.title;
            const observer = new MutationObserver(function(mutations) {
                const currentUrl = window.location.href;
                const currentTitle = document.title;
                const now = Date.now();
                if (now - lastClickTime < clickSuppressWindow) {
                    // Suppress navigation logging if within 300ms of a click
                    return;
                }
                if (currentUrl !== lastUrl || currentTitle !== lastTitle) {
                    // Navigation detected, but do NOT log or push navigation events
                    lastUrl = currentUrl;
                    lastTitle = currentTitle;
                }
            });
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
            
            // Detect page unload (when JavaScript will be killed)
            window.addEventListener('beforeunload', function(e) {
                const unloadData = {
                    type: 'page_unload',
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    pageTitle: document.title
                };
                window.interactionLogs.push(unloadData);
                console.log('INTERACTION_LOG:', JSON.stringify(unloadData));
            });
            
            // Log when recorder starts on a new page
            const pageLoadData = {
                type: 'page_load',
                timestamp: new Date().toISOString(),
                url: window.location.href,
                pageTitle: document.title
            };
            window.interactionLogs.push(pageLoadData);
            console.log('INTERACTION_LOG:', JSON.stringify(pageLoadData));
            
            // Track scroll events with navigation persistence
            let scrollTimeout = null;
            let elementScrollTimeout = null;
            let lastScrollPosition = { x: 0, y: 0 };
            
            function resetScrollTracking() {
                // Reset scroll position when page changes
                lastScrollPosition = { 
                    x: window.pageXOffset || document.documentElement.scrollLeft || 0,
                    y: window.pageYOffset || document.documentElement.scrollTop || 0
                };
            }
            
            // Reset scroll tracking on page load
            window.addEventListener('load', resetScrollTracking);
            
            // Reset scroll tracking on navigation
            window.addEventListener('popstate', resetScrollTracking);
            
            window.scrollListener = function(e) {
                // Clear previous scroll timeout
                if (scrollTimeout) {
                    clearTimeout(scrollTimeout);
                }
                
                // Set a small delay to avoid logging every tiny scroll
                scrollTimeout = setTimeout(function() {
                    const currentScrollX = window.pageXOffset || document.documentElement.scrollLeft;
                    const currentScrollY = window.pageYOffset || document.documentElement.scrollTop;
                    
                    // Only log if scroll position changed significantly
                    const scrollDeltaX = Math.abs(currentScrollX - lastScrollPosition.x);
                    const scrollDeltaY = Math.abs(currentScrollY - lastScrollPosition.y);
                    
                    if (scrollDeltaX > 10 || scrollDeltaY > 10) {
                        const scrollData = {
                            type: 'scroll',
                            timestamp: new Date().toISOString(),
                            scrollX: currentScrollX,
                            scrollY: currentScrollY,
                            deltaX: scrollDeltaX,
                            deltaY: scrollDeltaY,
                            url: window.location.href,
                            pageTitle: document.title,
                            selectors: {
                                css: 'locator("body")'
                            },
                            bbox: {
                                x: 0,
                                y: 0,
                                width: window.innerWidth,
                                height: window.innerHeight
                            }
                        };
                        window.interactionLogs.push(scrollData);
                        console.log('INTERACTION_LOG:', JSON.stringify(scrollData));
                        
                        // Also log accessibility tree (smart detection)
                        const axtree = getAppropriateAccessibilityTree();
                        console.log('AXTREE_LOG:', JSON.stringify(axtree));
                        
                        lastScrollPosition = { x: currentScrollX, y: currentScrollY };
                    }
                }, 150); // 150ms delay to avoid spam
            };
            document.addEventListener('scroll', window.scrollListener);
            
            // Track element-specific scrolling (textboxes, divs, etc.)
            window.elementScrollListener = function(e) {
                const element = e.target;
                
                // Skip if it's the document/window scroll (handled by scrollListener)
                if (element === document || element === document.documentElement || element === document.body) {
                    return;
                }
                
                // Clear previous element scroll timeout
                if (elementScrollTimeout) {
                    clearTimeout(elementScrollTimeout);
                }
                
                // Set a small delay to avoid logging every tiny scroll
                elementScrollTimeout = setTimeout(function() {
                    const rect = element.getBoundingClientRect();
                    const scrollTop = element.scrollTop || 0;
                    const scrollLeft = element.scrollLeft || 0;
                    
                    const scrollData = {
                        type: 'element_scroll',
                        timestamp: new Date().toISOString(),
                        element: element.tagName,
                        elementId: element.id || '',
                        elementClass: element.className || '',
                        elementText: element.textContent ? element.textContent.substring(0, 50) : '',
                        scrollTop: scrollTop,
                        scrollLeft: scrollLeft,
                        url: window.location.href,
                        pageTitle: document.title,
                        selectors: generateSelectors(element),
                        bbox: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        }
                    };
                    window.interactionLogs.push(scrollData);
                    console.log('INTERACTION_LOG:', JSON.stringify(scrollData));
                    
                    // Also log accessibility tree (smart detection)
                    const axtree = getAppropriateAccessibilityTree();
                    console.log('AXTREE_LOG:', JSON.stringify(axtree));
                }, 150); // 150ms delay to avoid spam
            };
            
            // Add scroll listener to all elements that can scroll
            function addScrollListenersToElements() {
                const scrollableElements = document.querySelectorAll('textarea, input[type="text"], input[type="email"], input[type="password"], div[style*="overflow"], div[class*="scroll"], .scrollable, [data-scrollable]');
                scrollableElements.forEach(element => {
                    element.addEventListener('scroll', window.elementScrollListener);
                });
            }
            
            // Initialize scroll listeners
            addScrollListenersToElements();
            
            // Also listen for dynamically added elements
            const scrollObserver = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) { // Element node
                            if (node.matches && (node.matches('textarea, input[type="text"], input[type="email"], input[type="password"], div[style*="overflow"], div[class*="scroll"], .scrollable, [data-scrollable]') || 
                                node.querySelector && node.querySelector('textarea, input[type="text"], input[type="email"], input[type="password"], div[style*="overflow"], div[class*="scroll"], .scrollable, [data-scrollable]'))) {
                                addScrollListenersToElements();
                            }
                        }
                    });
                });
            });
            
            scrollObserver.observe(document.body, { childList: true, subtree: true });
            
            // Track hover events
            let hoverStartTime = null;
            
            window.hoverListener = function(e) {
                const element = e.target;
                
                // Skip if hovering over the same element (no spam)
                if (currentlyHovered === element) {
                    return;
                }
                
                // Only log hover for clearly clickable elements
                const isHoverable = element.tagName === 'BUTTON' ||
                                   element.tagName === 'A' ||
                                   element.getAttribute('role') === 'button' ||
                                   element.getAttribute('role') === 'link' ||
                                   element.getAttribute('role') === 'menuitem';
                
                if (isHoverable && element.tagName !== 'BODY' && element.tagName !== 'HTML') {
                    currentlyHovered = element;
                    hoverStartTime = Date.now();
                    
                    const hoverData = {
                        type: 'hover',
                        timestamp: new Date().toISOString(),
                        element: element.tagName,
                        elementId: element.id || '',
                        elementClass: element.className || '',
                        elementText: element.textContent ? element.textContent.substring(0, 50) : '',
                        url: window.location.href,
                        pageTitle: document.title,
                        selectors: generateSelectors(element),
                        bbox: element.getBoundingClientRect()
                    };
                    window.interactionLogs.push(hoverData);
                    console.log('INTERACTION_LOG:', JSON.stringify(hoverData));
                    
                    // Also log accessibility tree (smart detection)
                    const axtree = getAppropriateAccessibilityTree();
                    console.log('AXTREE_LOG:', JSON.stringify(axtree));
                } else {
                    currentlyHovered = null;
                    hoverStartTime = null;
                }
            };
            // document.addEventListener('pointermove', window.hoverListener); // <--- COMMENTED OUT HOVER EVENT LISTENER
            
            // Generate Playwright-style selectors
            function generateSelectors(element) {
                const selectors = {};
                
                // Role-based selector (preferred)
                function getRoleWithName(element) {
                    let role = '';
                    let name = '';
                    
                    if (element.getAttribute('role')) {
                        role = element.getAttribute('role');
                    } else if (element.tagName === 'BUTTON') {
                        role = 'button';
                    } else if (element.tagName === 'A') {
                        role = 'link';
                    } else if (element.tagName === 'INPUT') {
                        const type = element.type || 'text';
                        if (type === 'checkbox') {
                            role = 'checkbox';
                        } else if (type === 'radio') {
                            role = 'radio';
                        } else if (type === 'submit' || type === 'button') {
                            role = 'button';
                        } else {
                            role = 'textbox';
                        }
                    } else if (element.tagName === 'SELECT') {
                        role = 'combobox';
                    } else if (element.tagName === 'TEXTAREA') {
                        role = 'textbox';
                    } else if (element.tagName === 'FORM') {
                        role = 'form';
                    }
                    
                    // Get the name from various sources
                    if (element.getAttribute('aria-label')) {
                        name = element.getAttribute('aria-label');
                    } else if (element.getAttribute('title')) {
                        name = element.getAttribute('title');
                    } else if (element.textContent && element.textContent.trim()) {
                        name = element.textContent.trim().substring(0, 50);
                    } else if (element.getAttribute('placeholder')) {
                        name = element.getAttribute('placeholder');
                    } else if (element.getAttribute('value')) {
                        name = element.getAttribute('value');
                    }
                    
                    if (role && name) {
                        return `getByRole('${role}', { name: '${name.replace(/'/g, "\\'")}' })`;
                    } else if (role) {
                        return `getByRole('${role}')`;
                    }
                    return null;
                }
                
                const roleSelector = getRoleWithName(element);
                if (roleSelector) {
                    selectors.role = roleSelector;
                }
                
                // Text-based selector
                if (element.textContent && element.textContent.trim()) {
                    const text = element.textContent.trim().substring(0, 30);
                    selectors.text = `getByText('${text}')`;
                }
                
                // Label-based selector
                if (element.getAttribute('aria-label')) {
                    selectors.label = `getByLabel('${element.getAttribute('aria-label')}')`;
                }
                
                // ID-based selector
                if (element.id) {
                    selectors.id = `getById('${element.id}')`;
                }
                
                // Test ID selector
                if (element.getAttribute('data-testid')) {
                    selectors.testId = `getByTestId('${element.getAttribute('data-testid')}')`;
                }
                
                // Placeholder selector
                if (element.getAttribute('placeholder')) {
                    selectors.placeholder = `getByPlaceholder('${element.getAttribute('placeholder')}')`;
                }
                
                // CSS selector
                if (element.id) {
                    selectors.css = `locator('#${element.id}')`;
                } else if (element.className) {
                    const classes = element.className.split(' ').filter(c => c.trim());
                    if (classes.length > 0) {
                        selectors.css = `locator('${element.tagName.toLowerCase()}.${classes.join('.')}')`;
                    }
                }
                
                return selectors;
            }
            
            console.log('Enhanced interaction logger initialized');
        """)
    
    async def _on_console(self, msg, page):
        """Handle console messages from JavaScript"""
        try:
            # Stop processing if we're shutting down
            if self.shutting_down:
                return
                
            if msg.text.startswith('INTERACTION_LOG:'):
                print("🔵 PYTHON RECEIVED:", msg.text)

                # Extract the JSON data from the console message
                json_str = msg.text.replace('INTERACTION_LOG:', '').strip()
                interaction_data = json.loads(json_str)
                
                # Skip page_load interactions (don't include in trajectory)
                if interaction_data['type'] == 'page_load':
                    return
                
                # DEDUPLICATION LOGIC TEMPORARILY DISABLED - capturing all interactions
                current_time = time.time()
                interaction_key = f"{interaction_data['type']}_{interaction_data.get('url', '')}_{interaction_data.get('element', '')}"
                
                if (self.last_interaction == interaction_key and 
                    current_time - self.last_interaction_time < 0.5):
                    return  # Skip duplicate interaction
                
                self.last_interaction = interaction_key
                self.last_interaction_time = current_time
                
                self.interactions.append(interaction_data)
                
                
                # Increment step counter FIRST, before taking screenshot
                self.step_counter += 1
                
                # Take screenshot with annotation (now using the correct step number)
                screenshot_path = await self._take_screenshot_fast(page, interaction_data)
                
                # Save axtree data
                axtree_path = await self._save_axtree()
                
                # Create user message (placeholder for now)
                user_message_path = await self._save_user_message(interaction_data)
                
                # Check if all files were created successfully
                if not (screenshot_path and axtree_path and user_message_path):
                    print(f"⚠️ File creation failed for step {self.step_counter}")
                    # Decrement step counter if files failed to create
                    self.step_counter -= 1
                    return
                
                # Create trajectory step in the new format
                step_number = str(self.step_counter)
                self.trajectory_data[step_number] = {
                    "screenshot": screenshot_path,
                    "axtree": axtree_path,
                    "user_message": user_message_path,
                    "other_obs": {
                        "page_index": 0,
                        "url": interaction_data.get('url', ''),
                        "open_pages_titles": [interaction_data.get('pageTitle', '')],
                        "open_pages_urls": [interaction_data.get('url', '')]
                    },
                    "action": self._create_action_data(interaction_data),
                    "coordinates": {
                        "x": interaction_data.get('x'),
                        "y": interaction_data.get('y')
                    },
                    "error": None,
                    "action_timestamp": time.time()
                }
                
                # Save trajectory data incrementally for live updates
                await self._save_trajectory_incrementally()
                
                # Print real-time feedback with Playwright selectors and URL
                url = interaction_data.get('url', 'Unknown URL')
                print(f"🌐 URL: {url}")
                
                if interaction_data['type'] == 'click':
                    selector = self._get_best_selector(interaction_data['selectors'])
                    print(f"🖱️  Click at ({interaction_data['x']}, {interaction_data['y']}) on {interaction_data['element']}")
                    print(f"   Playwright: page.{selector}")
                    
                elif interaction_data['type'] == 'typing_complete':
                    selector = self._get_best_selector(interaction_data['selectors'])
                    print(f"⌨️  Typed: '{interaction_data['value']}'")
                    print(f"   Playwright: page.{selector}.fill('{interaction_data['value']}')")
                    
                elif interaction_data['type'] == 'enter_pressed':
                    selector = self._get_best_selector(interaction_data['selectors'])
                    print(f"⌨️  Enter pressed with: '{interaction_data['value']}'")
                    print(f"   Playwright: page.{selector}.fill('{interaction_data['value']}')")
                    print(f"   Playwright: page.{selector}.press('Enter')")
                    
                elif interaction_data['type'] == 'input':
                    selector = self._get_best_selector(interaction_data['selectors'])
                    print(f"📝 Input: '{interaction_data['value'][:30]}...'")
                    print(f"   Playwright: page.{selector}.fill('{interaction_data['value']}')")
                    
                elif interaction_data['type'] == 'form_submit':
                    selector = self._get_best_selector(interaction_data['selectors'])
                    print(f"📋 Form submitted")
                    print(f"   Playwright: page.{selector}.submit()")
                    
                elif interaction_data['type'] == 'hover':
                    selector = self._get_best_selector(interaction_data['selectors'])
                    print(f"🖱️  Hover on {interaction_data['element']}")
                    print(f"   Playwright: page.{selector}.hover()")
                    
                elif interaction_data['type'] == 'scroll':
                    print(f"📜 Scroll to ({interaction_data['scrollX']}, {interaction_data['scrollY']})")
                    print(f"   Playwright: page.evaluate('window.scrollTo({interaction_data['scrollX']}, {interaction_data['scrollY']})')")
                    
                elif interaction_data['type'] == 'element_scroll':
                    selector = self._get_best_selector(interaction_data['selectors'])
                    print(f"📜 Element scroll on {interaction_data['element']} to ({interaction_data['scrollLeft']}, {interaction_data['scrollTop']})")
                    print(f"   Playwright: page.{selector}.evaluate('el => el.scrollTo({interaction_data['scrollLeft']}, {interaction_data['scrollTop']})')")
                    
                elif interaction_data['type'] == 'keyboard_input':
                    key_info = interaction_data['key']
                    modifiers = []
                    if interaction_data.get('ctrlKey'): modifiers.append('Ctrl')
                    if interaction_data.get('altKey'): modifiers.append('Alt')
                    if interaction_data.get('shiftKey'): modifiers.append('Shift')
                    if interaction_data.get('metaKey'): modifiers.append('Meta')
                    
                    modifier_str = '+' + '+'.join(modifiers) if modifiers else ''
                    print(f"⌨️  Keyboard: {key_info}{modifier_str} on {interaction_data['element']}")
                    print(f"   Playwright: page.keyboard.press('{key_info}')")
                    
                elif interaction_data['type'] == 'navigation':
                    print(f"🔄 Navigation: {interaction_data.get('previousUrl', 'Unknown')} → {interaction_data.get('currentUrl', 'Unknown')}")
                    
                elif interaction_data['type'] == 'page_load':
                    print(f"📄 Page loaded: {interaction_data.get('url', 'Unknown')}")
                    
                elif interaction_data['type'] == 'page_unload':
                    print(f"📄 Page unloading: {interaction_data.get('url', 'Unknown')}")
                    
                print()  # Add blank line for readability
                    
            elif msg.text.startswith('AXTREE_LOG:'):
                # Extract the JSON data from the console message
                json_str = msg.text.replace('AXTREE_LOG:', '').strip()
                axtree_data = json.loads(json_str)
                
                # Store axtree data for current step
                self.current_axtree_data = axtree_data
                
        except Exception as e:
            print(f"⚠️ Error processing console message: {e}")
    
    async def _take_screenshot_fast(self, page, interaction_data):
        """Take a screenshot quickly without annotation"""
        try:
            # Take screenshot with proper naming
            screenshot_path = self.images_dir / f"screenshot_{self.step_counter:03d}.png"
            
            # Take screenshot quickly without annotation
            await page.screenshot(
                path=str(screenshot_path),
                full_page=False,  # Only capture viewport, not full page
                type='png'  # Use PNG for faster encoding
            )
            
            # Add screenshot path to interaction data (relative path starting with ./images/)
            interaction_data['screenshot'] = f"./images/screenshot_{self.step_counter:03d}.png"
            
            print(f"📸 Screenshot saved: {screenshot_path.name}")
            
            # Minimal delay for faster processing
            await asyncio.sleep(0.01)
            
            return str(screenshot_path)
            
        except Exception as e:
            print(f"⚠️ Error taking screenshot: {e}")
            return None
    
    async def _save_axtree(self):
        """Save accessibility tree data"""
        try:
            axtree_path = self.axtree_dir / f"axtree_{self.step_counter:03d}.txt"
            with open(axtree_path, 'w') as f:
                json.dump(self.current_axtree_data, f, indent=2)
            print(f"🌲 Axtree saved: {axtree_path.name}")
            return str(axtree_path)
        except Exception as e:
            print(f"⚠️ Error saving axtree: {e}")
            return None
    
    async def _save_user_message(self, interaction_data):
        """Save user message data"""
        try:
            user_message_path = self.user_message_dir / f"user_message_{self.step_counter:03d}.txt"
            with open(user_message_path, 'w') as f:
                f.write(f"Interaction: {interaction_data['type']}\n")
                f.write(f"Value: {interaction_data.get('value', 'N/A')}\n")
                f.write(f"Element: {interaction_data.get('element', 'N/A')}\n")
                f.write(f"URL: {interaction_data.get('url', 'N/A')}\n")
                f.write(f"Page Title: {interaction_data.get('pageTitle', 'N/A')}\n")
                f.write(f"Selectors: {json.dumps(interaction_data.get('selectors', {}), indent=2)}\n")
                f.write(f"Bbox: {json.dumps(interaction_data.get('bbox', {}), indent=2)}\n")
            print(f"💬 User message saved: {user_message_path.name}")
            return str(user_message_path)
        except Exception as e:
            print(f"⚠️ Error saving user message: {e}")
            return None
    
    async def _annotate_screenshot(self, screenshot_path, bbox, interaction_data):
        """Annotate screenshot with bounding box, click coordinates, and interaction info"""
        try:
            # Check if file exists and is readable
            if not screenshot_path.exists():
                print(f"⚠️ Screenshot file not found: {screenshot_path}")
                return
                
            # Open the screenshot with error handling
            try:
                img = Image.open(screenshot_path)
            except Exception as e:
                print(f"⚠️ Error opening screenshot: {e}")
                return
                
            draw = ImageDraw.Draw(img)
            
            # Get bounding box coordinates
            x, y, width, height = bbox['x'], bbox['y'], bbox['width'], bbox['height']
            
            # Draw bounding box rectangle
            box_color = self._get_interaction_color(interaction_data['type'])
            line_width = 3
            draw.rectangle([x, y, x + width, y + height], outline=box_color, width=line_width)
            
            # Draw click coordinates if it's a click event
            if interaction_data['type'] == 'click' and 'x' in interaction_data and 'y' in interaction_data:
                click_x, click_y = interaction_data['x'], interaction_data['y']
                
                # Draw click point (red circle)
                circle_radius = 8
                circle_color = '#ff0000'  # Red
                draw.ellipse([click_x - circle_radius, click_y - circle_radius, 
                             click_x + circle_radius, click_y + circle_radius], 
                            fill=circle_color, outline='white', width=2)
                
                # Draw crosshair lines
                line_color = '#ff0000'
                line_length = 15
                # Horizontal line
                draw.line([click_x - line_length, click_y, click_x + line_length, click_y], 
                         fill=line_color, width=2)
                # Vertical line
                draw.line([click_x, click_y - line_length, click_x, click_y + line_length], 
                         fill=line_color, width=2)
            
            # Draw interaction type label
            label = f"{interaction_data['type'].upper()}"
            if interaction_data['type'] == 'typing_complete' and 'value' in interaction_data:
                label += f": {interaction_data['value'][:20]}..."
            elif interaction_data['type'] == 'click':
                label += f" at ({interaction_data['x']}, {interaction_data['y']})"
            
            # Try to use a font, fallback to default if not available
            try:
                font = ImageFont.truetype("arial.ttf", 16)
            except:
                font = ImageFont.load_default()
            
            # Draw label background
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            # Position label above the bounding box
            label_x = max(0, x)
            label_y = max(0, y - text_height - 5)
            
            # Draw label background
            draw.rectangle([label_x, label_y, label_x + text_width + 10, label_y + text_height + 5], 
                         fill=box_color)
            
            # Draw label text
            draw.text((label_x + 5, label_y + 2), label, fill="white", font=font)
            
            # Save annotated image
            img.save(screenshot_path)
            
        except Exception as e:
            print(f"⚠️ Error annotating screenshot: {e}")
    
    def _get_interaction_color(self, interaction_type):
        """Get color for different interaction types"""
        colors = {
            'click': '#ff0000',        # Red
            'hover': '#00ff00',        # Green
            'typing_complete': '#0000ff',  # Blue
            'enter_pressed': '#ff00ff',    # Magenta
            'input': '#ffff00',        # Yellow
            'form_submit': '#00ffff',  # Cyan
            'scroll': '#ff8800'        # Orange
        }
        return colors.get(interaction_type, '#888888')  # Gray default
    
    def _get_best_selector(self, selectors, element_properties=None):
        """Get the best available selector using enhanced element properties"""
        if not element_properties:
            element_properties = {}
        
        # Priority order for robust selectors:
        # 1. data-testid (most reliable for testing)
        # 2. aria-label (good for accessibility)
        # 3. role + text (semantic + descriptive)
        # 4. id (unique identifier)
        # 5. placeholder (for input fields)
        # 6. text content (for buttons/links)
        # 7. CSS selector (fallback)
        
        # Check data-testid first
        if element_properties.get('data_testid'):
            return f"getByTestId('{element_properties['data_testid']}')"
        
        # Check aria-label
        if element_properties.get('aria_label'):
            return f"getByLabel('{element_properties['aria_label']}')"
        
        # Check role + text combination
        if element_properties.get('role') and element_properties.get('text_content'):
            text = element_properties['text_content'].strip()
            if text and len(text) < 50:  # Avoid very long text
                return f"getByRole('{element_properties['role']}', {{ name: '{text}' }})"
        
        # Check id
        if element_properties.get('element_id'):
            return f"locator('#{element_properties['element_id']}')"
        
        # Check placeholder for input fields
        if element_properties.get('input_type') and element_properties.get('placeholder'):
            return f"getByPlaceholder('{element_properties['placeholder']}')"
        
        # Check text content for buttons/links
        if element_properties.get('text_content'):
            text = element_properties['text_content'].strip()
            if text and len(text) < 50:
                return f"getByText('{text}')"
        
        # Fallback to original selector logic
        if selectors.get('testId'):
            return selectors['testId']
        elif selectors.get('role'):
            return selectors['role']
        elif selectors.get('text'):
            return selectors['text']
        elif selectors.get('placeholder'):
            return selectors['placeholder']
        elif selectors.get('id'):
            return selectors['id']
        elif selectors.get('css'):
            return selectors['css']
        else:
            return "locator('element')"  # final fallback
    
    def _create_action_data(self, interaction_data):
        """Create action data in the format expected by trajectory.json"""
        action_type = interaction_data['type']
        element_properties = interaction_data.get('essentialProperties', {})
        selector = self._get_best_selector(interaction_data.get('selectors', {}), element_properties)

        if action_type == 'click':
            wait_condition = ""
            if element_properties.get('is_visible') is False:
                wait_condition = f"\nawait page.waitForSelector('{selector}', {{ state: 'visible' }})"
            playwright_code = f"{wait_condition}\nawait page.{selector}.click()"
            action_str = playwright_code.strip()
            element_text = element_properties.get('text_content', '').strip()
            element_id = element_properties.get('element_id', '')
            aria_label = element_properties.get('aria_label', '')
            placeholder = element_properties.get('placeholder', '')
            tag_name = element_properties.get('tag_name', '').lower()
            interaction_text = interaction_data.get('elementText', '').strip()
            if not element_text and interaction_text:
                element_text = interaction_text
            # Improved: Handle getByText and getByRole selectors for description
            if selector.startswith("locator('") and selector.endswith("')"):
                selector_str = selector[9:-2]
                if tag_name and tag_name != 'element':
                    action_description = f"Click {tag_name} with selector '{selector_str}'"
                else:
                    action_description = f"Click element with selector '{selector_str}'"
            elif selector.startswith("getByText('") and selector.endswith("')"):
                text_val = selector[11:-2]
                action_description = f"Click the '{text_val}' button"
            elif selector.startswith("getByRole('"):
                # Try to extract role and name
                try:
                    role_part = selector[10:].split("'", 1)[0]
                    name_part = ''
                    if '{ name:' in selector:
                        name_start = selector.index("{ name:") + 8
                        name_end = selector.index("'", name_start + 1)
                        name_part = selector[name_start:name_end]
                    if name_part:
                        action_description = f"Click the '{name_part}' {role_part}"
                    else:
                        action_description = f"Click the {role_part}"
                except Exception:
                    action_description = f"Click the {tag_name or 'element'} element"
            elif element_text and len(element_text) < 50:
                action_description = f"Click the '{element_text}' {tag_name or 'button'}"
            elif aria_label:
                action_description = f"Click the {tag_name or 'button'} labeled '{aria_label}'"
            elif element_id:
                action_description = f"Click the {tag_name or 'button'} with ID '{element_id}'"
            elif placeholder:
                action_description = f"Click the {tag_name or 'input'} with placeholder '{placeholder}'"
            else:
                action_description = f"Click the {tag_name or 'element'} element"
        elif action_type == 'typing_complete':
            value = element_properties.get('value', interaction_data.get('value', ''))
            wait_condition = ""
            if element_properties.get('is_visible') is False:
                wait_condition = f"\nawait page.waitForSelector('{selector}', {{ state: 'visible' }})"
            playwright_code = f"{wait_condition}\nawait page.{selector}.clear()\nawait page.{selector}.fill('{value}')"
            action_str = playwright_code.strip()
            element_text = element_properties.get('text_content', '').strip()
            placeholder = element_properties.get('placeholder', '')
            aria_label = element_properties.get('aria_label', '')
            element_id = element_properties.get('element_id', '')
            input_type = element_properties.get('input_type', '')
            interaction_text = interaction_data.get('elementText', '').strip()
            if not element_text and interaction_text:
                element_text = interaction_text
            if element_text and len(element_text) < 50:
                action_description = f"Enter '{value}' in the '{element_text}' {input_type or 'text'} field"
            elif placeholder:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field with placeholder '{placeholder}'"
            elif aria_label:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field labeled '{aria_label}'"
            elif element_id:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field with ID '{element_id}'"
            else:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field"
        elif action_type == 'enter_pressed':
            value = element_properties.get('value', interaction_data.get('value', ''))
            wait_condition = ""
            if element_properties.get('is_visible') is False:
                wait_condition = f"\nawait page.waitForSelector('{selector}', {{ state: 'visible' }})"
            playwright_code = f"{wait_condition}\nawait page.{selector}.clear()\nawait page.{selector}.fill('{value}')\nawait page.{selector}.press('Enter')"
            action_str = playwright_code.strip()
            element_text = element_properties.get('text_content', '').strip()
            placeholder = element_properties.get('placeholder', '')
            aria_label = element_properties.get('aria_label', '')
            element_id = element_properties.get('element_id', '')
            input_type = element_properties.get('input_type', '')
            interaction_text = interaction_data.get('elementText', '').strip()
            if not element_text and interaction_text:
                element_text = interaction_text
            if element_text and len(element_text) < 50:
                action_description = f"Enter '{value}' in the '{element_text}' {input_type or 'text'} field and press Enter"
            elif placeholder:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field with placeholder '{placeholder}' and press Enter"
            elif aria_label:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field labeled '{aria_label}' and press Enter"
            elif element_id:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field with ID '{element_id}' and press Enter"
            else:
                action_description = f"Enter '{value}' in the {input_type or 'text'} field and press Enter"
        elif action_type == 'input':
            value = element_properties.get('value', interaction_data.get('value', ''))
            wait_condition = ""
            if element_properties.get('is_visible') is False:
                wait_condition = f"\nawait page.waitForSelector('{selector}', {{ state: 'visible' }})"
            playwright_code = f"{wait_condition}\nawait page.{selector}.fill('{value}')"
            action_str = playwright_code.strip()
            element_text = element_properties.get('text_content', '').strip()
            placeholder = element_properties.get('placeholder', '')
            aria_label = element_properties.get('aria_label', '')
            element_id = element_properties.get('element_id', '')
            input_type = element_properties.get('input_type', '')
            interaction_text = interaction_data.get('elementText', '').strip()
            if not element_text and interaction_text:
                element_text = interaction_text
            if element_text and len(element_text) < 50:
                action_description = f"Type '{value}' in the '{element_text}' {input_type or 'text'} field"
            elif placeholder:
                action_description = f"Type '{value}' in the {input_type or 'text'} field with placeholder '{placeholder}'"
            elif aria_label:
                action_description = f"Type '{value}' in the {input_type or 'text'} field labeled '{aria_label}'"
            elif element_id:
                action_description = f"Type '{value}' in the {input_type or 'text'} field with ID '{element_id}'"
            else:
                action_description = f"Type '{value}' in the {input_type or 'text'} field"
        elif action_type == 'form_submit':
            wait_condition = ""
            if element_properties.get('is_visible') is False:
                wait_condition = f"\nawait page.waitForSelector('{selector}', {{ state: 'visible' }})"
            playwright_code = f"{wait_condition}\nawait page.{selector}.submit()"
            action_str = playwright_code.strip()
            element_text = element_properties.get('text_content', '').strip()
            aria_label = element_properties.get('aria_label', '')
            element_id = element_properties.get('element_id', '')
            interaction_text = interaction_data.get('elementText', '').strip()
            if not element_text and interaction_text:
                element_text = interaction_text
            if element_text and len(element_text) < 50:
                action_description = f"Submit the form by clicking the '{element_text}' button"
            elif aria_label:
                action_description = f"Submit the form by clicking the button labeled '{aria_label}'"
            elif element_id:
                action_description = f"Submit the form by clicking the button with ID '{element_id}'"
            else:
                action_description = f"Submit the form"
        elif action_type == 'hover':
            wait_condition = ""
            if element_properties.get('is_visible') is False:
                wait_condition = f"\nawait page.waitForSelector('{selector}', {{ state: 'visible' }})"
            playwright_code = f"{wait_condition}\nawait page.{selector}.hover()"
            action_str = playwright_code.strip()
            element_text = element_properties.get('text_content', '').strip()
            aria_label = element_properties.get('aria_label', '')
            element_id = element_properties.get('element_id', '')
            tag_name = element_properties.get('tag_name', '').lower()
            interaction_text = interaction_data.get('elementText', '').strip()
            if not element_text and interaction_text:
                element_text = interaction_text
            if element_text and len(element_text) < 50:
                action_description = f"Hover over the '{element_text}' {tag_name or 'element'}"
            elif aria_label:
                action_description = f"Hover over the {tag_name or 'element'} labeled '{aria_label}'"
            elif element_id:
                action_description = f"Hover over the {tag_name or 'element'} with ID '{element_id}'"
            else:
                action_description = f"Hover over the {tag_name or 'element'} element"
        elif action_type == 'scroll':
            scroll_x = interaction_data.get('scrollX', 0)
            scroll_y = interaction_data.get('scrollY', 0)
            playwright_code = f"await page.evaluate('window.scrollTo({scroll_x}, {scroll_y})')"
            action_str = playwright_code.strip()
            action_description = f"Scroll to position ({scroll_x}, {scroll_y})"
        elif action_type == 'element_scroll':
            scroll_left = interaction_data.get('scrollLeft', 0)
            scroll_top = interaction_data.get('scrollTop', 0)
            playwright_code = f"await page.{selector}.evaluate('el => el.scrollTo({scroll_left}, {scroll_top})')"
            action_str = playwright_code.strip()
            action_description = f"Scroll element {element_properties.get('tag_name', 'element')} to position ({scroll_left}, {scroll_top})"
        elif action_type == 'keyboard_input':
            key_info = interaction_data.get('key', '')
            modifiers = []
            if interaction_data.get('ctrlKey'): modifiers.append('Ctrl')
            if interaction_data.get('altKey'): modifiers.append('Alt')
            if interaction_data.get('shiftKey'): modifiers.append('Shift')
            if interaction_data.get('metaKey'): modifiers.append('Meta')
            modifier_str = '+' + '+'.join(modifiers) if modifiers else ''
            playwright_code = f"await page.keyboard.press('{key_info}')"
            action_str = playwright_code.strip()
            action_description = f"Press keyboard key {key_info}{modifier_str}"
        else:
            playwright_code = f"// {action_type} action"
            action_str = playwright_code.strip()
            action_description = f"Perform {action_type} action"

        # Create enhanced thought description using element properties
        def create_enhanced_thought(action_type, element_properties, value=""):
            """Create a more descriptive thought based on element properties with better fallbacks"""
            # Get element properties with better fallbacks
            element_text = element_properties.get('text_content', '').strip()
            aria_label = element_properties.get('aria_label', '').strip()
            placeholder = element_properties.get('placeholder', '').strip()
            element_id = element_properties.get('element_id', '').strip()
            tag_name = element_properties.get('tag_name', '').lower().strip()
            input_type = element_properties.get('input_type', '').strip()
            
            # Also check interaction_data for fallbacks
            interaction_text = interaction_data.get('elementText', '').strip()
            interaction_id = interaction_data.get('elementId', '').strip()
            interaction_class = interaction_data.get('elementClass', '').strip()
            
            # Use interaction data as fallback if element properties are empty
            if not element_text and interaction_text:
                element_text = interaction_text
            if not element_id and interaction_id:
                element_id = interaction_id
            
            # Determine the best descriptive element name
            element_name = ""
            if element_text and len(element_text) < 50:  # Avoid very long text
                element_name = f"'{element_text}'"
            elif aria_label and len(aria_label) < 50:
                element_name = f"labeled '{aria_label}'"
            elif element_id:
                element_name = f"with ID '{element_id}'"
            elif placeholder and len(placeholder) < 50:
                element_name = f"with placeholder '{placeholder}'"
            elif interaction_class:
                element_name = f"with class '{interaction_class.split()[0]}'"  # Use first class
            elif tag_name:
                element_name = f"{tag_name}"
            else:
                element_name = "element"
            
            # Create action-specific thoughts with better context
            if action_type == 'click':
                if element_name.startswith("'"):
                    return f"I need to click the {element_name} {tag_name or 'button'} to proceed with the task."
                elif element_name.startswith("labeled"):
                    return f"I need to click the {tag_name or 'button'} {element_name} to continue."
                elif element_name.startswith("with ID"):
                    return f"I need to click the {tag_name or 'button'} {element_name} to proceed."
                elif element_name.startswith("with placeholder"):
                    return f"I need to click the {tag_name or 'input'} {element_name} to continue."
                elif element_name.startswith("with class"):
                    return f"I need to click the {element_name} to proceed with the task."
                else:
                    return f"I need to click the {element_name} to proceed with the task."
                    
            elif action_type in ['typing_complete', 'enter_pressed', 'input']:
                # For input actions, focus on the field type and purpose
                field_type = input_type if input_type else "text"
                field_purpose = ""
                
                if placeholder:
                    field_purpose = f" with placeholder '{placeholder}'"
                elif aria_label:
                    field_purpose = f" labeled '{aria_label}'"
                elif element_id:
                    field_purpose = f" with ID '{element_id}'"
                elif interaction_class:
                    field_purpose = f" with class '{interaction_class.split()[0]}'"
                
                if value:
                    return f"I need to enter '{value}' in the {field_type} field{field_purpose} to provide the required information."
                else:
                    return f"I need to interact with the {field_type} field{field_purpose} to complete the form."
                    
            elif action_type == 'hover':
                if element_name.startswith("'"):
                    return f"I need to hover over the {element_name} {tag_name or 'element'} to see additional options or information."
                elif element_name.startswith("labeled"):
                    return f"I need to hover over the {tag_name or 'element'} {element_name} to reveal more details."
                elif element_name.startswith("with ID"):
                    return f"I need to hover over the {tag_name or 'element'} {element_name} to access additional functionality."
                else:
                    return f"I need to hover over the {element_name} to see more options."
                    
            elif action_type in ['scroll', 'element_scroll']:
                return f"I need to scroll to navigate through the content and find the relevant information."
                
            elif action_type == 'form_submit':
                if element_name.startswith("'"):
                    return f"I need to submit the form by clicking the {element_name} button to complete the process."
                elif element_name.startswith("labeled"):
                    return f"I need to submit the form by clicking the button {element_name} to finalize the action."
                elif element_name.startswith("with ID"):
                    return f"I need to submit the form by clicking the button {element_name} to complete the submission."
                else:
                    return f"I need to submit the form to complete the current task."
                    
            else:
                return f"I need to perform the {action_type} action to continue with the task."
        
        # Create action output structure with enhanced thoughts
        if action_type == 'click':
            action_output = {
                "thought": create_enhanced_thought('click', element_properties),
                "action": {
                    "bid": element_properties.get('element_id', ''),
                    "button": "left",
                    "click_type": "single",
                    "bbox": [
                        element_properties.get('bounding_box', {}).get('x', 0),
                        element_properties.get('bounding_box', {}).get('y', 0),
                        element_properties.get('bounding_box', {}).get('width', 0),
                        element_properties.get('bounding_box', {}).get('height', 0)
                    ] if element_properties.get('bounding_box') else None,
                    "class": element_properties.get('element_class', ''),
                    "id": element_properties.get('element_id', ''),
                    "type": element_properties.get('tag_name', ''),
                    "ariaLabel": element_properties.get('aria_label', ''),
                    "role": element_properties.get('role', ''),
                    "value": element_properties.get('value', ''),
                    "node_properties": {
                        "role": element_properties.get('role', ''),
                        "value": element_properties.get('text_content', '')
                    }
                },
                "action_name": "click"
            }
        elif action_type in ['typing_complete', 'enter_pressed', 'input']:
            value = element_properties.get('value', interaction_data.get('value', ''))
            action_output = {
                "thought": create_enhanced_thought(action_type, element_properties, value),
                "action": {
                    "text": value
                },
                "action_name": "keyboard_type"
            }
        elif action_type == 'hover':
            action_output = {
                "thought": create_enhanced_thought('hover', element_properties),
                "action": {
                    "text": element_properties.get('value', '')
                },
                "action_name": "hover"
            }
        elif action_type in ['scroll', 'element_scroll']:
            action_output = {
                "thought": create_enhanced_thought('scroll', element_properties),
                "action": {
                    "text": element_properties.get('value', '')
                },
                "action_name": "scroll"
            }
        elif action_type == 'form_submit':
            action_output = {
                "thought": create_enhanced_thought('form_submit', element_properties),
                "action": {
                    "text": element_properties.get('value', '')
                },
                "action_name": "form_submit"
            }
        else:
            action_output = {
                "thought": create_enhanced_thought(action_type, element_properties),
                "action": {
                    "text": element_properties.get('value', '')
                },
                "action_name": action_type
            }
        
        # Capture essential element properties for LLM context
        # Use essentialProperties from JavaScript if available, otherwise fallback to basic data
        essential_props = interaction_data.get("essentialProperties", {})
        
        element_properties = {
            # Core identification
            "tag_name": essential_props.get("tagName", interaction_data.get("element", "")).upper(),
            "element_id": essential_props.get("elementId", interaction_data.get("elementId", "")),
            "element_class": essential_props.get("elementClass", interaction_data.get("elementClass", "")),
            "text_content": essential_props.get("elementText", interaction_data.get("elementText", "")),
            
            # Input properties (for form elements)
            "input_type": essential_props.get("inputType", interaction_data.get("inputType", "")),
            "value": essential_props.get("value", interaction_data.get("value", "")),
            "placeholder": essential_props.get("placeholder", interaction_data.get("placeholder", "")),
            "required": essential_props.get("required", interaction_data.get("required", False)),
            "disabled": essential_props.get("disabled", interaction_data.get("disabled", False)),
            
            # Accessibility (for robust targeting)
            "aria_label": essential_props.get("ariaLabel", interaction_data.get("ariaLabel", "")),
            "role": essential_props.get("role", interaction_data.get("role", "")),
            "data_testid": essential_props.get("dataTestid", interaction_data.get("dataTestid", "")),
            
            # Visual state (for wait conditions)
            "is_visible": essential_props.get("isVisible", True),
            "is_enabled": essential_props.get("isEnabled", not interaction_data.get("disabled", False)),
            "is_focused": essential_props.get("isFocused", False),
            
            # Bounding box (for coordinates)
            "bounding_box": essential_props.get("bbox", interaction_data.get("bbox")) if essential_props.get("bbox") else None,
            
            # Form context (for form interactions)
            "form_id": essential_props.get("form", interaction_data.get("form", "")),
            "name": essential_props.get("name", interaction_data.get("name", "")),
            
            # Validation (for error handling)
            "validation_state": essential_props.get("validationState", "valid"),
            "error_message": essential_props.get("errorMessage", interaction_data.get("errorMessage", ""))
            }
        
        return {
            "action_str": action_str,
            "playwright_code": playwright_code,
            "action_description": action_description,
            "action_output": action_output
        }
    
    async def _save_trajectory_incrementally(self):
        """Save trajectory data incrementally for live updates"""
        try:
            trajectory_json = self.session_dir / "trajectory.json"
            with open(trajectory_json, 'w') as f:
                json.dump(self.trajectory_data, f, indent=2)
            print(f"📝 Live trajectory update: {len(self.trajectory_data)} steps")
        except Exception as e:
            print(f"⚠️ Error saving trajectory incrementally: {e}")
    
    def _generate_notes_html(self, notes, is_general=False):
        """Generate HTML for displaying notes"""
        if not notes:
            return ""
        
        # Generate unique ID for this notes section
        import random
        section_id = f"notes_{random.randint(1000, 9999)}"
        
        note_count_text = "(General)" if is_general else f"({len(notes)} note{'s' if len(notes) != 1 else ''})"
        
        notes_html = f"""
                <div class="notes-section">
                    <h4 onclick="toggleNotes('{section_id}')">
                        📝 Notes {note_count_text}
                        <span class="expand-icon" id="icon_{section_id}">▼</span>
                    </h4>
                    <div class="notes-container" id="{section_id}">
"""
        
        for note in notes:
            timestamp = note.get('timestamp', '')
            note_text = note.get('note', '')
            
            # Format timestamp
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                formatted_time = timestamp
            
            # Escape HTML characters in note text
            import html
            escaped_note = html.escape(note_text)
            
            note_class = "general-note" if is_general or not note.get('step_id') else ""
            
            notes_html += f"""
                        <div class="note-item {note_class}">
                            <div class="note-timestamp">{formatted_time}</div>
                            <div class="note-text">{escaped_note}</div>
                        </div>
"""
        
        notes_html += """
                    </div>
                </div>
"""
        return notes_html
    
    async def _save_logs(self):
        """Save all logged interactions to a JSON file"""
        if not self.trajectory_data:
            print("⚠️  No interactions to save")
            return
        
        # Calculate session duration
        duration = time.time() - self.start_time if self.start_time else 0
        
        # Save trajectory.json in the new format
        trajectory_json = self.session_dir / "trajectory.json"
        with open(trajectory_json, 'w') as f:
            json.dump(self.trajectory_data, f, indent=2)
        
        # Save stepSummary.json with both Playwright codes and steps
        step_summary_json = self.session_dir / "stepSummary.json"
        playwright_codes = []
        steps = []
        
        for step_data in self.trajectory_data.values():
            action_data = step_data.get('action', {})
            playwright_code = action_data.get('playwright_code', '')
            action_description = action_data.get('action_description', '')
            
            if playwright_code:
                playwright_codes.append(playwright_code)
            if action_description:
                steps.append(action_description)
        
        # Extract URL from the first step if available
        url = ""
        if self.trajectory_data:
            first_step = next(iter(self.trajectory_data.values()))
            url = first_step.get('other_obs', {}).get('url', '')
        
        # Create the new JSON structure
        step_summary = {
            "goal": "",
            "url": url,
            "playwright_codes": playwright_codes,
            "steps": steps,
            "total_steps": len(playwright_codes),
            "session_info": {
                "session_id": self.session_id,
                "session_name": self.session_name,
                "start_time": datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
                "end_time": datetime.now().isoformat(),
                "duration_seconds": duration
            }
        }
        
        with open(step_summary_json, 'w') as f:
            json.dump(step_summary, f, indent=2)
        
        # Save metadata.json
        metadata_json = self.session_dir / "metadata.json"
        metadata = {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            "end_time": datetime.now().isoformat(),
            "duration_seconds": duration,
            "total_interactions": len(self.trajectory_data),
            "interaction_types": {},
            "screenshots_count": self.step_counter
        }
        
        # Count interaction types
        for step_data in self.trajectory_data.values():
            action_type = step_data.get('action', {}).get('action_output', {}).get('action_name', 'unknown')
            metadata["interaction_types"][action_type] = metadata["interaction_types"].get(action_type, 0) + 1
        
        with open(metadata_json, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"💾 Saved trajectory to: {self.session_dir}")
        print(f"💻 Saved stepSummary.json with {len(playwright_codes)} Playwright commands and {len(steps)} steps")
        
        # Generate HTML report
        await self._generate_html_report()
        
        print(f"📊 Session duration: {duration:.2f} seconds")
        print(f"📈 Interaction types: {metadata['interaction_types']}")
        print(f"📸 Screenshots taken: {self.step_counter}")
        
        # Print Playwright commands
        if playwright_codes:
            print("\n🎭 Generated Playwright commands:")
            for i, cmd in enumerate(playwright_codes[:10], 1):
                print(f"   {i}. {cmd}")
            if len(playwright_codes) > 10:
                print(f"   ... and {len(playwright_codes) - 10} more commands")
    
    async def _generate_html_report(self):
        """Generate an HTML report showing trajectory data with images side by side"""
        try:
            html_path = self.session_dir / "trajectory_report.html"
            
            # Read trajectory data
            trajectory_file = self.session_dir / "trajectory.json"
            if not trajectory_file.exists():
                print("⚠️ No trajectory.json found - cannot generate HTML report")
                return
                
            with open(trajectory_file, 'r') as f:
                trajectory_data = json.load(f)
            
            # Read notes data if available
            notes_file = self.session_dir / "notes.json"
            notes_data = []
            if notes_file.exists():
                with open(notes_file, 'r') as f:
                    notes_data = json.load(f)
                print(f"📝 Found {len(notes_data)} notes for HTML report")
            
            # Generate HTML content
            html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trajectory Report - Session {self.session_id}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #333;
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .step {{
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 20px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .step-header {{
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 15px;
            font-weight: bold;
            color: #333;
        }}
        .content-row {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}
        .image-section {{
            flex: 1;
            min-width: 300px;
        }}
        .data-section {{
            flex: 1;
            min-width: 300px;
        }}
        .screenshot {{
            max-width: 100%;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        .data-box {{
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin-bottom: 10px;
        }}
        .data-box h4 {{
            margin-top: 0;
            color: #333;
        }}
        .dropdown {{
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 10px;
        }}
        .json-viewer {{
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 10px;
            max-height: 200px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
        }}
        .action-info {{
            background-color: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 10px;
            margin-bottom: 10px;
        }}
        .url-info {{
            background-color: #fff3e0;
            border-left: 4px solid #ff9800;
            padding: 10px;
            margin-bottom: 10px;
        }}
        .controls {{
            background-color: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #ddd;
        }}
        .button {{
            background-color: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            margin-right: 10px;
        }}
        .button:hover {{
            background-color: #0056b3;
        }}
        .notes-section {{
            background-color: #f8f9fa;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin-top: 15px;
            border-radius: 6px;
        }}
        .notes-section h4 {{
            margin-top: 0;
            color: #28a745;
            font-size: 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .notes-section h4:hover {{
            color: #1e7e34;
        }}
        .notes-container {{
            max-height: 200px;
            overflow-y: auto;
            transition: max-height 0.3s ease;
            scrollbar-width: thin;
            scrollbar-color: #28a745 #f8f9fa;
        }}
        .notes-container::-webkit-scrollbar {{
            width: 6px;
        }}
        .notes-container::-webkit-scrollbar-track {{
            background: #f8f9fa;
            border-radius: 3px;
        }}
        .notes-container::-webkit-scrollbar-thumb {{
            background: #28a745;
            border-radius: 3px;
        }}
        .notes-container::-webkit-scrollbar-thumb:hover {{
            background: #1e7e34;
        }}
        .notes-container.collapsed {{
            max-height: 0;
            overflow: hidden;
        }}
        .expand-icon {{
            font-size: 12px;
            transition: transform 0.3s ease;
        }}
        .expand-icon.expanded {{
            transform: rotate(180deg);
        }}
        .note-item {{
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
            border-left: 3px solid #28a745;
        }}
        .note-item:last-child {{
            margin-bottom: 0;
        }}
        .note-timestamp {{
            font-size: 12px;
            color: #6c757d;
            margin-bottom: 5px;
            font-weight: 500;
        }}
        .note-text {{
            font-size: 14px;
            color: #333;
            line-height: 1.4;
            margin-bottom: 5px;
        }}
        .note-step-info {{
            background: #e7f3ff;
            color: #0366d6;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            display: inline-block;
            margin-top: 5px;
        }}
        .general-note {{
            border-left-color: #17a2b8;
        }}
        .general-note .note-step-info {{
            background: #d1ecf1;
            color: #0c5460;
        }}
        .no-notes {{
            color: #6c757d;
            font-style: italic;
            text-align: center;
            padding: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 Trajectory Report</h1>
        <p><strong>Session ID:</strong> {self.session_id}</p>
        <p><strong>Total Steps:</strong> {len(trajectory_data)}</p>
        <p><strong>Total Notes:</strong> {len(notes_data)}</p>
        <p><strong>Generated:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="controls">
        <button class="button" onclick="expandAll()">Expand All</button>
        <button class="button" onclick="collapseAll()">Collapse All</button>
        <button class="button" onclick="showImages()">Show Images</button>
        <button class="button" onclick="hideImages()">Hide Images</button>
        <button class="button" onclick="showNotes()">Show Notes</button>
        <button class="button" onclick="hideNotes()">Hide Notes</button>
    </div>
"""
            
            # Helper function to filter notes for a specific step
            def get_step_notes(step_id):
                """Get notes that are attached to a specific step"""
                step_notes = []
                for note in notes_data:
                    if note.get('step_id') == step_id:
                        step_notes.append(note)
                return step_notes
            
            def get_general_notes():
                """Get notes that are not attached to any specific step"""
                general_notes = []
                for note in notes_data:
                    if not note.get('step_id'):
                        general_notes.append(note)
                return general_notes
            
            # Add each step
            for step_num, step_data in trajectory_data.items():
                screenshot_path = step_data.get('screenshot', '')
                axtree_path = step_data.get('axtree', '')
                user_message_path = step_data.get('user_message', '')
                action_data = step_data.get('action', {})
                other_obs = step_data.get('other_obs', {})
                
                # Get action info
                action_name = action_data.get('action_output', {}).get('action_name', 'unknown')
                action_str = action_data.get('action_description', '')
                playwright_code = action_data.get('playwright_code', '')
                thought = action_data.get('thought', '')
                
                # Get action details for display
                action_details = action_data.get('action_output', {}).get('action', {})
                bbox = action_details.get('bbox', [])
                
                # Get coordinates
                coordinates = step_data.get('coordinates', {})
                coord_x = coordinates.get('x')
                coord_y = coordinates.get('y')
                
                # Get URL info
                url = other_obs.get('url', '')
                page_titles = other_obs.get('open_pages_titles', [])
                
                # Check if files exist
                screenshot_exists = Path(screenshot_path).exists() if screenshot_path else False
                axtree_exists = Path(axtree_path).exists() if axtree_path else False

                # Fix relative paths for axtree and user message
                axtree_rel_path = f"./axtree/axtree_{step_num.zfill(3)}.txt" if axtree_exists else ''
                user_message_rel_path = f"./user_message/user_message_{step_num.zfill(3)}.txt" if user_message_path else ''

                html_content += f"""
    <div class="step">
        <div class="step-header">
            Step {step_num} - {action_name.upper()}
        </div>
        <div class="content-row">
            <div class="image-section">
                <h4>📸 Screenshot</h4>
                {f'<img src="./images/screenshot_{step_num.zfill(3)}.png" alt="Screenshot {step_num}" class="screenshot">' if screenshot_exists else '<p style="color: #999;">Screenshot not available</p>'}
            </div>
            <div class="data-section">
                <div class="action-info">
                    <h4>🎯 Action Details</h4>
                    <p><strong>Type:</strong> {action_name}</p>
                    <p><strong>Action:</strong> {action_str}</p>
                    <p><strong>Playwright:</strong> {playwright_code}</p>
                    {f'<p><strong>Thought:</strong> {thought}</p>' if thought else ''}
                    {f'<p><strong>Element ID:</strong> {action_details.get("id", "N/A")}</p>' if action_details.get("id") else ''}
                    {f'<p><strong>Element Class:</strong> {action_details.get("class", "N/A")}</p>' if action_details.get("class") else ''}
                    {f'<p><strong>Element Type:</strong> {action_details.get("type", "N/A")}</p>' if action_details.get("type") else ''}
                    {f'<p><strong>Coordinates:</strong> ({coord_x}, {coord_y})</p>' if coord_x is not None and coord_y is not None else ''}
                    {f'<p><strong>Bounding Box:</strong> x={bbox[0] if len(bbox) > 0 else "N/A"}, y={bbox[1] if len(bbox) > 1 else "N/A"}, width={bbox[2] if len(bbox) > 2 else "N/A"}, height={bbox[3] if len(bbox) > 3 else "N/A"}</p>' if bbox else ''}
                    {f'<p><strong>Role:</strong> {action_details.get("node_properties", {}).get("role", "N/A")}</p>' if action_details.get("node_properties", {}).get("role") else ''}
                    {f'<p><strong>Value:</strong> {action_details.get("node_properties", {}).get("value", "N/A")}</p>' if action_details.get("node_properties", {}).get("value") else ''}
                </div>
                <div class="url-info">
                    <h4>🌐 Page Info</h4>
                    <p><strong>URL:</strong> {url}</p>
                    <p><strong>Titles:</strong> {', '.join(page_titles)}</p>
                </div>
                <div class="data-box">
                    <h4>📄 Axtree Data</h4>
                    <select class="dropdown" onchange="showAxtree('{step_num}', this.value)">
                        <option value="">Select axtree file...</option>
                        {f'<option value="{axtree_rel_path}">axtree_{step_num.zfill(3)}.txt</option>' if axtree_exists else ''}
                    </select>
                    <div id="axtree-{step_num}" class="json-viewer" style="display: none;"></div>
                </div>
                <div class="data-box">
                    <h4>📋 User Message</h4>
                    <select class="dropdown" onchange="showUserMessage('{step_num}', this.value)">
                        <option value="">Select user message file...</option>
                        {f'<option value="{user_message_rel_path}">user_message_{step_num.zfill(3)}.txt</option>' if user_message_path else ''}
                    </select>
                    <div id="usermessage-{step_num}" class="json-viewer" style="display: none;"></div>
                </div>
                {self._generate_notes_html(get_step_notes(step_num))}
            </div>
        </div>
    </div>
"""
            
            # Add general notes section at the end
            general_notes = get_general_notes()
            if general_notes:
                html_content += f"""
    <div class="step">
        <div class="step-header">
            📝 General Notes (Not Attached to Specific Steps)
        </div>
        <div class="content-row">
            <div class="data-section" style="width: 100%;">
                {self._generate_notes_html(general_notes, is_general=True)}
            </div>
        </div>
    </div>
"""
            
            # Add JavaScript for interactivity
            html_content += """
    <script>
        function showAxtree(stepNum, filePath) {
            const viewer = document.getElementById(`axtree-${stepNum}`);
            if (filePath) {
                fetch(filePath)
                    .then(response => response.text())
                    .then(data => {
                        viewer.textContent = data;
                        viewer.style.display = 'block';
                    })
                    .catch(error => {
                        viewer.textContent = 'Error loading file: ' + error;
                        viewer.style.display = 'block';
                    });
            } else {
                viewer.style.display = 'none';
            }
        }
        
        function showUserMessage(stepNum, filePath) {
            const viewer = document.getElementById(`usermessage-${stepNum}`);
            if (filePath) {
                fetch(filePath)
                    .then(response => response.text())
                    .then(data => {
                        viewer.textContent = data;
                        viewer.style.display = 'block';
                    })
                    .catch(error => {
                        viewer.textContent = 'Error loading file: ' + error;
                        viewer.style.display = 'block';
                    });
            } else {
                viewer.style.display = 'none';
            }
        }
        
        function expandAll() {
            const viewers = document.querySelectorAll('.json-viewer');
            viewers.forEach(viewer => {
                if (viewer.textContent.trim()) {
                    viewer.style.display = 'block';
                }
            });
        }
        
        function collapseAll() {
            const viewers = document.querySelectorAll('.json-viewer');
            viewers.forEach(viewer => {
                viewer.style.display = 'none';
            });
        }
        
        function showImages() {
            const images = document.querySelectorAll('.screenshot');
            images.forEach(img => {
                img.style.display = 'block';
            });
        }
        
        function hideImages() {
            const images = document.querySelectorAll('.screenshot');
            images.forEach(img => {
                img.style.display = 'none';
            });
        }
        
        function showNotes() {
            const notes = document.querySelectorAll('.notes-section');
            notes.forEach(note => {
                note.style.display = 'block';
            });
        }
        
        function hideNotes() {
            const notes = document.querySelectorAll('.notes-section');
            notes.forEach(note => {
                note.style.display = 'none';
            });
        }
        
        function toggleNotes(sectionId) {
            const container = document.getElementById(sectionId);
            const icon = document.getElementById(`icon_${sectionId}`);
            
            if (container.classList.contains('collapsed')) {
                container.classList.remove('collapsed');
                icon.textContent = '▼';
                icon.classList.add('expanded');
            } else {
                container.classList.add('collapsed');
                icon.textContent = '▶';
                icon.classList.remove('expanded');
            }
        }
    </script>
</body>
</html>
"""
            
            # Write the HTML file
            with open(html_path, 'w') as f:
                f.write(html_content)
            
            print(f"📄 HTML report generated: {html_path}")
            
        except Exception as e:
            print(f"⚠️ Error generating HTML report: {e}")


async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced interaction logger")
    parser.add_argument("--url", default="https://mail.google.com/", 
                       help="URL to start logging on")
    parser.add_argument("--output-dir", default="../data/interaction_logs",
                       help="Directory to save interaction logs")
    
    args = parser.parse_args()
    
    logger = EnhancedInteractionLogger(output_dir=args.output_dir)
    await logger.start_logging(url=args.url)


if __name__ == "__main__":
    asyncio.run(main()) 