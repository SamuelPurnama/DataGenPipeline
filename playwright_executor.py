#!/usr/bin/env python3
"""
Playwright Code Executor
Reads codeSummary.json and executes each Playwright command in a persistent browser session
"""

import asyncio
import json
import time
import sys
from pathlib import Path
from playwright.async_api import async_playwright
import argparse


class PlaywrightExecutor:
    """Executes Playwright commands from codeSummary.json"""
    
    def __init__(self, session_dir: str, browser_sessions_dir: str = "browser_sessions"):
        self.session_dir = Path(session_dir)
        self.browser_sessions_dir = Path(browser_sessions_dir)
        self.browser_sessions_dir.mkdir(exist_ok=True)
        
        # Load codeSummary.json
        self.code_summary_path = self.session_dir / "codeSummary.json"
        if not self.code_summary_path.exists():
            raise FileNotFoundError(f"codeSummary.json not found in {self.session_dir}")
        
        with open(self.code_summary_path, 'r') as f:
            self.playwright_codes = json.load(f)
        
        print(f"📋 Loaded {len(self.playwright_codes)} Playwright commands from {self.code_summary_path}")
    
    async def execute_commands(self, delay: float = 1.0, headless: bool = False):
        """Execute all Playwright commands with a delay between each"""
        async with async_playwright() as p:
            # Launch browser with persistent context
            user_data_dir = self.browser_sessions_dir
            print(f"🔍 Using browser session directory: {user_data_dir}")
            print(f"🔍 Directory exists: {user_data_dir.exists()}")
            
            # Check what's already in the session directory
            if user_data_dir.exists():
                session_files = list(user_data_dir.glob("*"))
                print(f"🔍 Session directory contains {len(session_files)} files/folders")
                for item in session_files[:5]:  # Show first 5 items
                    print(f"   - {item.name}")
                if len(session_files) > 5:
                    print(f"   ... and {len(session_files) - 5} more")
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless,
                args=[
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--window-size=1920,1080'
                ]
            )
            
            # Get the first page from the persistent context
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Set a realistic user agent
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            print(f"🚀 Starting execution of {len(self.playwright_codes)} commands...")
            print(f"⏱️  Delay between commands: {delay} seconds")
            print(f"🌐 Browser session: {user_data_dir}")
            
            # Navigate to Google Calendar
            print("🌐 Navigating to Google Calendar...")
            await page.goto('https://calendar.google.com')
            await page.wait_for_load_state('networkidle')
            print("✅ Google Calendar loaded")
            
            # Check if user is logged in
            try:
                # Look for elements that indicate logged in state
                logged_in_indicators = [
                    'button[aria-label="Create"]',
                    '[data-testid="create-button"]',
                    'button:has-text("Create")'
                ]
                
                is_logged_in = False
                for selector in logged_in_indicators:
                    try:
                        await page.wait_for_selector(selector, timeout=3000)
                        is_logged_in = True
                        break
                    except:
                        continue
                
                if is_logged_in:
                    print("✅ Already logged in to Google Calendar")
                else:
                    print("⚠️  Not logged in - please log in manually")
                    print("💡 After logging in, future runs will remember your session")
            except Exception as e:
                print(f"⚠️  Could not determine login status: {e}")
            
            # Execute each command
            for i, code in enumerate(self.playwright_codes, 1):
                try:
                    print(f"\n[{i}/{len(self.playwright_codes)}] Executing: {code}")
                    
                    # Parse and execute the command
                    await self._execute_single_command(page, code)
                    
                    print(f"✅ Success: {code}")
                    
                    # Wait between commands
                    if i < len(self.playwright_codes):  # Don't wait after the last command
                        print(f"⏳ Waiting {delay} seconds...")
                        await asyncio.sleep(delay)
                        
                except Exception as e:
                    print(f"❌ Error executing command {i}: {code}")
                    print(f"   Error: {e}")
                    
                    # Ask user if they want to continue
                    response = input("Continue with next command? (y/n): ").lower().strip()
                    if response != 'y':
                        print("🛑 Execution stopped by user")
                        break
            
            print(f"\n🎉 Execution completed! {len(self.playwright_codes)} commands processed.")
            
            # Verify session was saved
            print(f"💾 Session data saved to: {user_data_dir}")
            if user_data_dir.exists():
                session_files = list(user_data_dir.glob("*"))
                print(f"💾 Session directory now contains {len(session_files)} files/folders")
            
            # Keep browser open for inspection
            if not headless:
                print("🔍 Browser will remain open for inspection. Close it manually when done.")
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print("\n⏹️  Closing browser...")
            else:
                await context.close()
    
    async def _execute_single_command(self, page, code: str):
        """Execute a single Playwright command using exec()"""
        try:
            # Skip comment lines
            if code.strip().startswith('//'):
                print(f"⏭️  Skipping comment: {code}")
                return
            
            # Convert camelCase methods to underscore format for Playwright
            code = code.replace('getByRole', 'get_by_role')
            code = code.replace('getByText', 'get_by_text')
            code = code.replace('getByLabel', 'get_by_label')
            code = code.replace('getByPlaceholder', 'get_by_placeholder')
            code = code.replace('getByTestId', 'get_by_test_id')
            
            # Convert JavaScript object syntax to Python dictionary syntax
            import re
            # Replace { name: 'value' } with { 'name': 'value' }
            code = re.sub(r'\{ (\w+): ', r"{ '\1': ", code)
            
            # Convert dictionary to keyword arguments for Playwright methods
            # Replace .get_by_role('selector', { 'name': 'value' }) with .get_by_role('selector', name='value')
            code = re.sub(r'\.get_by_role\(([^,]+),\s*\{\s*\'(\w+)\':\s*([^}]+)\s*\}\)', r'.get_by_role(\1, \2=\3)', code)
            code = re.sub(r'\.get_by_text\(([^,]+),\s*\{\s*\'(\w+)\':\s*([^}]+)\s*\}\)', r'.get_by_text(\1, \2=\3)', code)
            code = re.sub(r'\.get_by_label\(([^,]+),\s*\{\s*\'(\w+)\':\s*([^}]+)\s*\}\)', r'.get_by_label(\1, \2=\3)', code)
            code = re.sub(r'\.get_by_placeholder\(([^,]+),\s*\{\s*\'(\w+)\':\s*([^}]+)\s*\}\)', r'.get_by_placeholder(\1, \2=\3)', code)
            code = re.sub(r'\.get_by_test_id\(([^,]+),\s*\{\s*\'(\w+)\':\s*([^}]+)\s*\}\)', r'.get_by_test_id(\1, \2=\3)', code)
            
            # Create a local namespace with 'page' available
            local_vars = {'page': page}
            
            # Execute the command and await the result
            result = eval(code, {}, local_vars)
            if result and hasattr(result, '__await__'):
                await result
            
        except Exception as e:
            print(f"❌ Failed to execute command: {code}")
            print(f"   Error: {e}")
            raise e
    
    async def _execute_get_by_role(self, page, code: str):
        """Execute getByRole command"""
        # Extract role and name from getByRole('role', { name: 'name' })
        import re
        
        # Match getByRole('role') or getByRole('role', { name: 'name' })
        role_match = re.match(r"getByRole\('([^']+)'(?:,\s*\{\s*name:\s*'([^']+)'\s*\})?\)", code)
        if role_match:
            role = role_match.group(1)
            name = role_match.group(2) if role_match.group(2) else None
            
            # Get the locator
            if name:
                locator = page.get_by_role(role, name=name)
            else:
                locator = page.get_by_role(role)
            
            # Check if command ends with .click()
            if code.endswith('.click()'):
                await locator.click()
            elif code.endswith('.fill('):
                # Extract fill value
                fill_match = re.search(r"\.fill\('([^']+)'\)", code)
                if fill_match:
                    value = fill_match.group(1)
                    await locator.fill(value)
            elif code.endswith('.press('):
                # Extract press key
                press_match = re.search(r"\.press\('([^']+)'\)", code)
                if press_match:
                    key = press_match.group(1)
                    await locator.press(key)
            elif code.endswith('.hover()'):
                await locator.hover()
            elif code.endswith('.submit()'):
                await locator.submit()
            else:
                # Just click by default
                await locator.click()
    
    async def _execute_get_by_text(self, page, code: str):
        """Execute getByText command"""
        import re
        
        text_match = re.match(r"getByText\('([^']+)'\)", code)
        if text_match:
            text = text_match.group(1)
            locator = page.get_by_text(text)
            
            if code.endswith('.click()'):
                await locator.click()
            else:
                await locator.click()
    
    async def _execute_get_by_label(self, page, code: str):
        """Execute getByLabel command"""
        import re
        
        label_match = re.match(r"getByLabel\('([^']+)'\)", code)
        if label_match:
            label = label_match.group(1)
            locator = page.get_by_label(label)
            
            if code.endswith('.fill('):
                fill_match = re.search(r"\.fill\('([^']+)'\)", code)
                if fill_match:
                    value = fill_match.group(1)
                    await locator.fill(value)
            else:
                await locator.click()
    
    async def _execute_get_by_placeholder(self, page, code: str):
        """Execute getByPlaceholder command"""
        import re
        
        placeholder_match = re.match(r"getByPlaceholder\('([^']+)'\)", code)
        if placeholder_match:
            placeholder = placeholder_match.group(1)
            locator = page.get_by_placeholder(placeholder)
            
            if code.endswith('.fill('):
                fill_match = re.search(r"\.fill\('([^']+)'\)", code)
                if fill_match:
                    value = fill_match.group(1)
                    await locator.fill(value)
            else:
                await locator.click()
    
    async def _execute_get_by_test_id(self, page, code: str):
        """Execute getByTestId command"""
        import re
        
        test_id_match = re.match(r"getByTestId\('([^']+)'\)", code)
        if test_id_match:
            test_id = test_id_match.group(1)
            locator = page.get_by_test_id(test_id)
            
            if code.endswith('.click()'):
                await locator.click()
            elif code.endswith('.fill('):
                fill_match = re.search(r"\.fill\('([^']+)'\)", code)
                if fill_match:
                    value = fill_match.group(1)
                    await locator.fill(value)
            else:
                await locator.click()
    
    async def _execute_locator(self, page, code: str):
        """Execute locator command"""
        import re
        
        locator_match = re.match(r"locator\('([^']+)'\)", code)
        if locator_match:
            selector = locator_match.group(1)
            locator = page.locator(selector)
            
            if code.endswith('.click()'):
                await locator.click()
            elif code.endswith('.fill('):
                fill_match = re.search(r"\.fill\('([^']+)'\)", code)
                if fill_match:
                    value = fill_match.group(1)
                    await locator.fill(value)
            elif code.endswith('.submit()'):
                await locator.submit()
            elif code.endswith('.evaluate('):
                # Handle evaluate commands
                evaluate_match = re.search(r"\.evaluate\('([^']+)'\)", code)
                if evaluate_match:
                    script = evaluate_match.group(1)
                    await locator.evaluate(script)
            else:
                await locator.click()
    
    async def _execute_keyboard_press(self, page, code: str):
        """Execute keyboard.press command"""
        import re
        
        press_match = re.match(r"keyboard\.press\('([^']+)'\)", code)
        if press_match:
            key = press_match.group(1)
            await page.keyboard.press(key)
    
    async def _execute_evaluate(self, page, code: str):
        """Execute evaluate command"""
        import re
        
        evaluate_match = re.match(r"evaluate\('([^']+)'\)", code)
        if evaluate_match:
            script = evaluate_match.group(1)
            await page.evaluate(script)
    
    async def _execute_generic_command(self, page, code: str):
        """Execute generic command by trying to evaluate it"""
        try:
            # Try to execute as JavaScript
            await page.evaluate(f"console.log('Executing: {code}')")
            print(f"⚠️  Generic command execution not implemented for: {code}")
        except Exception as e:
            print(f"❌ Failed to execute generic command: {code}")
            raise e


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Execute Playwright commands from codeSummary.json")
    parser.add_argument("session_dir", help="Path to session directory containing codeSummary.json")
    parser.add_argument("--delay", type=float, default=1.0, 
                       help="Delay between commands in seconds (default: 1.0)")
    parser.add_argument("--headless", action="store_true",
                       help="Run browser in headless mode")
    parser.add_argument("--browser-sessions-dir", default="browser_sessions",
                       help="Directory for browser sessions (default: browser_sessions)")
    
    args = parser.parse_args()
    
    try:
        executor = PlaywrightExecutor(args.session_dir, args.browser_sessions_dir)
        await executor.execute_commands(delay=args.delay, headless=args.headless)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 