from playwright.sync_api import Page, TimeoutError
from typing import Optional

def is_already_logged_in(page: Page, timeout: int = 5000) -> bool:
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

def handle_google_login(page: Page, email: str, password: str, timeout: int = 30000) -> bool:
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

def ensure_google_login(page: Page, email: Optional[str] = None, password: Optional[str] = None, 
                       url: Optional[str] = None, timeout: int = 300000) -> bool:
    """
    Ensure that the user is logged into Google, handling the login process if needed.
    This is a convenience function that combines login checking and handling.
    
    Args:
        page: Playwright page object
        email: Google account email (optional)
        password: Google account password (optional)
        url: Current URL (optional, used to determine if Scholar-specific handling is needed)
        timeout: Timeout in milliseconds for waiting for login completion
        
    Returns:
        bool: True if login was successful or already logged in, False otherwise
    """
    if not email or not password or (url and 'scholar.google.com' in url):
        # For Scholar or when no credentials provided, just wait for appropriate element
        if url and 'scholar.google.com' in url:
            page.wait_for_selector('input[name="q"]', timeout=timeout)
        else:
            page.wait_for_selector('[aria-label*="Google Account"]', timeout=timeout)
        return True
    
    print("🔑 Checking login status...")
    if not handle_google_login(page, email, password):
        print("❌ Automatic login failed, please login manually")
        page.wait_for_selector('[aria-label*="Google Account"]', timeout=timeout)
    
    return True 