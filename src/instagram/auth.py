"""
Instagram authentication and session management.
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import playwright
from playwright.sync_api import sync_playwright, BrowserContext, Browser


@dataclass
class SessionConfig:
    """Configuration for Instagram session."""
    session_id: str = ""
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    headless: bool = True
    timeout: int = 30000


class InstagramAuth:
    """Handles Instagram authentication and session management."""
    
    def __init__(self, config: Optional[SessionConfig] = None):
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
                
                # Inject script to handle session cookie
                page.evaluate("""
                    () => {
                        // Handle any session-based redirects
                        window.location.reload();
                    }
                """)
                
                # Check if logged in (simple heuristic)
                is_logged_in = "logged_in_user" in page.url or "story" in page.url
                
                if is_logged_in:
                    print("✓ Already logged in")
                    return True
                
                print("⚠ Session ID not found or expired")
                print("Please obtain a valid session ID from Instagram")
                return False
                
        except Exception as e:
            print(f"✗ Login failed: {e}")
            return False
    
    def get_context(self) -> Optional[BrowserContext]:
        """Get the browser context."""
        return self.context
    
    def close(self):
        """Close browser and context."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()


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
        
        self.auth = InstagramAuth()
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
        """Extract bio text."""
        try:
            return page.locator('div[role="main"] div div').inner_text().strip()
        except:
            return ""
    
    def _extract_profile_pic(self, page) -> str:
        """Extract profile picture URL."""
        try:
            return page.locator('div[role="main"] img').get_attribute('src') or ""
        except:
            return ""
