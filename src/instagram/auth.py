"""
Instagram authentication and session management.
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import playwright
from playwright.sync_api import sync_playwright, BrowserContext, Browser
from playwright.sync_api import Cookie
from dotenv import load_dotenv


@dataclass
class SessionConfig:
    """Configuration for Instagram session."""
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    headless: bool = True
    timeout: int = 30000


class InstagramAuth:
    """Handles Instagram authentication and session management."""
    
    def __init__(self, session_id: str = None, config: Optional[SessionConfig] = None):
        # Load environment variables if session_id not provided
        if session_id is None:
            load_dotenv()
            session_id = os.getenv('INSTAGRAM_SESSION_ID', '')
        
        self.session_id = session_id
        self.config = config or SessionConfig()
        self.context: Optional[BrowserContext] = None
        self.browser: Optional[Browser] = None
    
    def login(self) -> bool:
        """
        Login to Instagram using session ID.
        
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            with sync_playwright() as p:
                # Launch browser
                self.browser = p.chromium.launch(
                    headless=self.config.headless,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                    ]
                )
                
                # Create context
                self.context = self.browser.new_context(
                    user_agent=self.config.user_agent,
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York'
                )
                
                page = self.context.new_page()
                
                # Navigate to Instagram
                page.goto("https://www.instagram.com", wait_until="networkidle")
                
                # Set session cookie from environment variable
                # Format: name%3Avalue%3Apath%3Adomain%3Asecure%3AhttpOnly%3ApathIsSameSite
                if self.session_id:
                    page.context.add_cookies([
                        {
                            'name': 'sessionid',
                            'value': self.session_id,
                            'domain': '.instagram.com',
                            'path': '/',
                            'secure': True,
                            'httpOnly': True,
                            'sameSite': 'Lax'
                        }
                    ])
                
                # Reload page to apply cookie
                page.reload()
                
                # Check if logged in (simple heuristic)
                is_logged_in = "logged_in_user" in page.url or "story" in page.url
                
                if is_logged_in:
                    print("✓ Successfully logged in with session cookie")
                    return True
                
                print("⚠ Session cookie may not be valid or expired")
                print("Please verify the session cookie and try again")
                return False
                
        except Exception as e:
            print(f"✗ Login failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.browser:
                self.browser.close()
    
    def get_context(self) -> BrowserContext:
        """Get browser context."""
        if not self.context:
            raise Exception("Context not initialized")
        return self.context


class SessionManager:
    """Manages Instagram session lifecycle."""
    
    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self.auth: Optional[InstagramAuth] = None
    
    def initialize(self) -> bool:
        """Initialize session manager."""
        if not self.session_id:
            print("⚠ No session ID provided")
            return False
        
        self.auth = InstagramAuth(self.session_id)
        return self.auth.login()
    
    def scrape_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Scrape data from Instagram profile.
        
        Args:
            username: Instagram username
            
        Returns:
            Dict containing profile data or None if failed
        """
        if not self.auth or not self.auth.context:
            print("✗ Session not initialized")
            return None
        
        try:
            context = self.auth.get_context()
            page = context.new_page()
            
            # Navigate to profile
            page.goto(f"https://www.instagram.com/{username}/", wait_until="networkidle")
            
            # Extract profile data
            profile_data = {
                'username': username,
                'full_name': self._extract_full_name(page),
                'followers': self._extract_followers(page),
                'posts_count': self._extract_posts_count(page),
                'is_verified': self._extract_verified(page),
                'bio': self._extract_bio(page),
                'profile_pic_url': self._extract_profile_pic(page),
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"✓ Profile scraped: {profile_data['username']}")
            return profile_data
            
        except Exception as e:
            print(f"✗ Failed to scrape profile: {e}")
            return None
    
    def _extract_full_name(self, page) -> str:
        """Extract full name from profile page."""
        try:
            return page.locator('div[role="main"] h2').inner_text().strip()
        except:
            return ""
    
    def _extract_followers(self, page) -> int:
        """Extract followers count."""
        try:
            text = page.locator('div[role="main"] div div').inner_text()
            if 'Followers' in text:
                return int(text.split()[0])
        except:
            pass
        return 0
    
    def _extract_posts_count(self, page) -> int:
        """Extract posts count."""
        try:
            text = page.locator('div[role="main"] div div').inner_text()
            if 'Posts' in text:
                return int(text.split()[0])
        except:
            pass
        return 0
    
    def _extract_verified(self, page) -> bool:
        """Check if profile is verified."""
        try:
            return 'verified' in page.locator('div[role="main"]').inner_text().lower()
        except:
            return False
    
    def _extract_bio(self, page) -> str:
        """Extract bio from profile."""
        try:
            return page.locator('div[role="main"] div div').inner_text().strip()
        except:
            return ""
    
    def _extract_profile_pic(self, page) -> str:
        """Extract profile picture URL."""
        try:
            return page.locator('div[role="main"] img').get_attribute('src')
        except:
            return ""
