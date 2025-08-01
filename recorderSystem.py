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
    
    def __init__(self, output_dir: str = "interaction_logs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
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
        sessions_dir = Path("recorder_sessions")
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
            
            window.interactionLogs = [];
            window.lastInteractionElement = null;
            
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
                const element = e.target;
                const selectors = generateSelectors(element);
                
                // Get bounding box
                const rect = element.getBoundingClientRect();
                
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
                    bbox: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }
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
                const rect = element.getBoundingClientRect();
                
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
                    bbox: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }
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
            
            // Track navigation events
            let lastUrl = window.location.href;
            let lastTitle = document.title;
            
            // Monitor for URL changes
            const observer = new MutationObserver(function(mutations) {
                const currentUrl = window.location.href;
                const currentTitle = document.title;
                
                if (currentUrl !== lastUrl || currentTitle !== lastTitle) {
                    const navigationData = {
                        type: 'navigation',
                        timestamp: new Date().toISOString(),
                        previousUrl: lastUrl,
                        currentUrl: currentUrl,
                        previousTitle: lastTitle,
                        currentTitle: currentTitle,
                        url: currentUrl,
                        pageTitle: currentTitle,
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
                    window.interactionLogs.push(navigationData);
                    console.log('INTERACTION_LOG:', JSON.stringify(navigationData));
                    
                    // Also log accessibility tree (smart detection)
                    const axtree = getAppropriateAccessibilityTree();
                    console.log('AXTREE_LOG:', JSON.stringify(axtree));
                    
                    lastUrl = currentUrl;
                    lastTitle = currentTitle;
                }
            });
            
            // Start observing
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
            
            // Also listen for popstate events (back/forward navigation)
            window.addEventListener('popstate', function(e) {
                const currentUrl = window.location.href;
                const currentTitle = document.title;
                
                const navigationData = {
                    type: 'navigation',
                    timestamp: new Date().toISOString(),
                    navigationType: 'popstate',
                    currentUrl: currentUrl,
                    currentTitle: currentTitle,
                    url: currentUrl,
                    pageTitle: currentTitle,
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
                window.interactionLogs.push(navigationData);
                console.log('INTERACTION_LOG:', JSON.stringify(navigationData));
                
                // Also log accessibility tree (smart detection)
                const axtree = getAppropriateAccessibilityTree();
                console.log('AXTREE_LOG:', JSON.stringify(axtree));
                
                lastUrl = currentUrl;
                lastTitle = currentTitle;
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
                # Extract the JSON data from the console message
                json_str = msg.text.replace('INTERACTION_LOG:', '').strip()
                interaction_data = json.loads(json_str)
                
                # Skip page_load interactions (don't include in trajectory)
                if interaction_data['type'] == 'page_load':
                    return
                
                # Deduplication: Skip duplicate interactions within 500ms
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
            
            # Add screenshot path to interaction data
            interaction_data['screenshot'] = str(screenshot_path)
            
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
    
    def _get_best_selector(self, selectors):
        """Get the best available selector"""
        # Priority order: testId > role > text > placeholder > id > css
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
            return "locator('element')"  # fallback
    
    def _create_action_data(self, interaction_data):
        """Create action data in the format expected by trajectory.json"""
        action_type = interaction_data['type']
        selector = self._get_best_selector(interaction_data.get('selectors', {}))
        
        # Create action string based on type
        if action_type == 'click':
            action_str = f"click(bid='{interaction_data.get('elementId', '')}', button='left')"
            playwright_code = f"page.{selector}.click()"
            action_description = f"Click the {interaction_data.get('elementText', interaction_data.get('element', ''))} element"
            
        elif action_type == 'typing_complete':
            action_str = f"keyboard_type(text='{interaction_data.get('value', '')}')"
            playwright_code = f"page.{selector}.fill('{interaction_data.get('value', '')}')"
            action_description = f"Fill in the {interaction_data.get('elementText', 'input field')} with '{interaction_data.get('value', '')}'"
            
        elif action_type == 'enter_pressed':
            action_str = f"keyboard_type(text='{interaction_data.get('value', '')}')"
            playwright_code = f"page.{selector}.fill('{interaction_data.get('value', '')}'); page.{selector}.press('Enter')"
            action_description = f"Fill in the {interaction_data.get('elementText', 'input field')} with '{interaction_data.get('value', '')}' and press Enter"
            
        elif action_type == 'input':
            action_str = f"keyboard_type(text='{interaction_data.get('value', '')}')"
            playwright_code = f"page.{selector}.fill('{interaction_data.get('value', '')}')"
            action_description = f"Fill in the {interaction_data.get('elementText', 'input field')} with '{interaction_data.get('value', '')}'"
            
        elif action_type == 'form_submit':
            action_str = f"click(bid='{interaction_data.get('elementId', '')}', button='left')"
            playwright_code = f"page.{selector}.submit()"
            action_description = f"Submit the form"
            
        elif action_type == 'hover':
            action_str = f"hover(bid='{interaction_data.get('elementId', '')}')"
            playwright_code = f"page.{selector}.hover()"
            action_description = f"Hover over the {interaction_data.get('elementText', interaction_data.get('element', ''))} element"
            
        elif action_type == 'scroll':
            action_str = f"scroll(x={interaction_data.get('scrollX', 0)}, y={interaction_data.get('scrollY', 0)})"
            playwright_code = f"page.evaluate('window.scrollTo({interaction_data.get('scrollX', 0)}, {interaction_data.get('scrollY', 0)})')"
            action_description = f"Scroll to position ({interaction_data.get('scrollX', 0)}, {interaction_data.get('scrollY', 0)})"
            
        elif action_type == 'element_scroll':
            action_str = f"scroll_element(bid='{interaction_data.get('elementId', '')}', x={interaction_data.get('scrollLeft', 0)}, y={interaction_data.get('scrollTop', 0)})"
            playwright_code = f"page.{selector}.evaluate('el => el.scrollTo({interaction_data.get('scrollLeft', 0)}, {interaction_data.get('scrollTop', 0)})')"
            action_description = f"Scroll element {interaction_data.get('element', '')} to position ({interaction_data.get('scrollLeft', 0)}, {interaction_data.get('scrollTop', 0)})"
            
        elif action_type == 'keyboard_input':
            key_info = interaction_data.get('key', '')
            modifiers = []
            if interaction_data.get('ctrlKey'): modifiers.append('Ctrl')
            if interaction_data.get('altKey'): modifiers.append('Alt')
            if interaction_data.get('shiftKey'): modifiers.append('Shift')
            if interaction_data.get('metaKey'): modifiers.append('Meta')
            
            modifier_str = '+' + '+'.join(modifiers) if modifiers else ''
            action_str = f"keyboard_press(key='{key_info}{modifier_str}')"
            playwright_code = f"page.keyboard.press('{key_info}')"
            action_description = f"Press keyboard key {key_info}{modifier_str}"
            
        else:
            action_str = f"action(type='{action_type}')"
            playwright_code = f"// {action_type} action"
            action_description = f"Perform {action_type} action"
        
        # Create action output structure
        if action_type == 'click':
            action_output = {
                "thought": f"I need to {action_description.lower()}.",
                "action": {
                    "bid": interaction_data.get('elementId', ''),
                    "button": "left",
                    "click_type": "single",
                    "bbox": [
                        interaction_data.get('bbox', {}).get('x', 0),
                        interaction_data.get('bbox', {}).get('y', 0),
                        interaction_data.get('bbox', {}).get('width', 0),
                        interaction_data.get('bbox', {}).get('height', 0)
                    ] if interaction_data.get('bbox') else None,
                    "class": interaction_data.get('elementClass', ''),
                    "id": interaction_data.get('elementId', ''),
                    "type": interaction_data.get('element', ''),
                    "ariaLabel": None,
                    "role": None,
                    "value": interaction_data.get('value', ''),
                    "node_properties": {
                        "role": interaction_data.get('selectors', {}).get('role', '').replace("getByRole('", "").replace("')", "").split("', {")[0] if interaction_data.get('selectors', {}).get('role') else None,
                        "value": interaction_data.get('elementText', '')
                    }
                },
                "action_name": "click"
            }
        elif action_type in ['typing_complete', 'enter_pressed', 'input']:
            # For typing actions, only include the text field
            action_output = {
                "thought": f"I need to {action_description.lower()}.",
                "action": {
                    "text": interaction_data.get('value', '')
                },
                "action_name": "keyboard_type"
            }
        elif action_type == 'hover':
            # For hover actions
            action_output = {
                "thought": f"I need to {action_description.lower()}.",
                "action": {
                    "text": interaction_data.get('value', '')
                },
                "action_name": "hover"
            }
        elif action_type in ['scroll', 'element_scroll']:
            # For scroll actions
            action_output = {
                "thought": f"I need to {action_description.lower()}.",
                "action": {
                    "text": interaction_data.get('value', '')
                },
                "action_name": "scroll"
            }
        else:
            # For other actions
            action_output = {
                "thought": f"I need to {action_description.lower()}.",
                "action": {
                    "text": interaction_data.get('value', '')
                },
                "action_name": action_type
            }
        
        return {
            "action_str": action_str,
            "playwright_code": playwright_code,
            "action_description": action_description,
            "action_output": action_output
        }
    
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
        
        # Save codeSummary.json with array of Playwright codes
        code_summary_json = self.session_dir / "codeSummary.json"
        playwright_codes = []
        for step_data in self.trajectory_data.values():
            playwright_code = step_data.get('action', {}).get('playwright_code', '')
            if playwright_code:
                playwright_codes.append(playwright_code)
        
        with open(code_summary_json, 'w') as f:
            json.dump(playwright_codes, f, indent=2)
        
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
        print(f"💻 Saved codeSummary.json with {len(playwright_codes)} Playwright commands")
        
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
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 Trajectory Report</h1>
        <p><strong>Session ID:</strong> {self.session_id}</p>
        <p><strong>Total Steps:</strong> {len(trajectory_data)}</p>
        <p><strong>Generated:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="controls">
        <button class="button" onclick="expandAll()">Expand All</button>
        <button class="button" onclick="collapseAll()">Collapse All</button>
        <button class="button" onclick="showImages()">Show Images</button>
        <button class="button" onclick="hideImages()">Hide Images</button>
    </div>
"""
            
            # Add each step
            for step_num, step_data in trajectory_data.items():
                screenshot_path = step_data.get('screenshot', '')
                axtree_path = step_data.get('axtree', '')
                user_message_path = step_data.get('user_message', '')
                action_data = step_data.get('action', {})
                other_obs = step_data.get('other_obs', {})
                
                # Get action info
                action_name = action_data.get('action_output', {}).get('action_name', 'unknown')
                action_str = action_data.get('action_str', '')
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
                
                html_content += f"""
    <div class="step">
        <div class="step-header">
            Step {step_num} - {action_name.upper()}
        </div>
        
        <div class="content-row">
            <div class="image-section">
                <h4>📸 Screenshot</h4>
                {f'<img src="/api/screenshot/{self.session_name}/{step_num.zfill(3)}" alt="Screenshot {step_num}" class="screenshot">' if screenshot_exists else '<p style="color: #999;">Screenshot not available</p>'}
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
                        {f'<option value="{axtree_path}">axtree_{step_num.zfill(3)}.txt</option>' if axtree_exists else ''}
                    </select>
                    <div id="axtree-{step_num}" class="json-viewer" style="display: none;"></div>
                </div>
                
                <div class="data-box">
                    <h4>📋 User Message</h4>
                    <select class="dropdown" onchange="showUserMessage('{step_num}', this.value)">
                        <option value="">Select user message file...</option>
                        {f'<option value="{user_message_path}">user_message_{step_num.zfill(3)}.txt</option>' if user_message_path else ''}
                    </select>
                    <div id="usermessage-{step_num}" class="json-viewer" style="display: none;"></div>
                </div>
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
    parser.add_argument("--output-dir", default="interaction_logs",
                       help="Directory to save interaction logs")
    
    args = parser.parse_args()
    
    logger = EnhancedInteractionLogger(output_dir=args.output_dir)
    await logger.start_logging(url=args.url)


if __name__ == "__main__":
    asyncio.run(main()) 