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
from urllib.parse import quote_plus
from json import dumps, decoder, loads


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

        
        
    def _preflight_config(self, playwright: sync_playwright):
        """Perform preflight config for every browser instance."""
        try:
            browser = playwright.chromium.launch(
                    headless=self.config.headless,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                    ]
                )
            context = browser.new_context(
                    user_agent=self.config.user_agent,
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York'
                )
            context.add_cookies([
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
                
            return context, browser
        
        except Exception as e:
            print(f"✗ Context creation failed: {e}")
            import traceback
            traceback.print_exc()
        
    def _preflight_config_proxyed(self, playwright: sync_playwright):
        """Perform preflight config for every browser instance."""
        proxy_config = {
            "server": "http://127.0.0.1:8081"
        }
        try:
            browser = playwright.chromium.launch(
                    proxy={"server": "per-context"},
                    headless=self.config.headless,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                    ]
                )
            context = browser.new_context(
                    proxy=proxy_config,
                    user_agent=self.config.user_agent,
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York',
                    ignore_https_errors=True
                )
            context.add_cookies([
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
                
            return context, browser
                
        except Exception as e:
            print(f"✗ Context creation failed: {e}")
            import traceback
            traceback.print_exc()
        
    
    def session_check(self, playwright: sync_playwright) -> bool:
        """
        Check if the session is valid.
        
        Returns:
            bool: True if session is valid, False otherwise
        """
        try:
            context, browser = self._preflight_config(playwright)
            page = context.new_page()
            page.goto("https://www.instagram.com/", wait_until="networkidle")
            
            # Check if logged in by looking for profile icon
            if not page.locator('input[name="email"]').is_visible():
                browser.close()
                print("✓ Session is valid, logged in successfully")
                return True
            else:
                browser.close()
                print("✗ Session invalid: Session ID may be invalid or expired")
                return False
                
        except Exception as e:
            print(f"✗ Session check error: {e}")
            import traceback
            traceback.print_exc()
            return False
        

    def close(self):        
        """Close browser and context."""
        if self.browser:
            self.browser.close()
    



class SessionManager:
    """Manages Instagram session lifecycle."""
    
    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self.auth: Optional[InstagramAuth] = None
        self.auth = InstagramAuth(session_id=self.session_id)
        with sync_playwright() as playwright:
            if not self.auth.session_check(playwright):
                raise Exception("Failed to initialize Instagram session")

    
    def scrape_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Scrape data from Instagram profile.
        
        Args:
            username: Instagram username
            
        Returns:
            Dict containing profile data or None if failed
        """
        
        try:
            with sync_playwright() as playwright:
                if not self.auth.session_check(playwright):
                    raise Exception("Failed to initialize Instagram session")
                context, browser = self.auth._preflight_config_proxyed(playwright)

                userid_req = context.request.get(
                            f'https://i.instagram.com/api/v1/users/web_profile_info/?username={username}',
                            headers = {"User-Agent": "iphone_ua", "x-ig-app-id": "936619743392459"}
                        )
                user_data = userid_req.json().get("data", {}).get('user', {})

                if not user_data:
                    print(f"✗ Failed to get user data for {username}")
                    browser.close()
                    return None



                browser.close()
            print(f"✓ Profile scraped: {user_data.get('username', '')}")
            return user_data
            
        except Exception as e:
            print(f"✗ Failed to scrape profile: {e}")
            import traceback
            traceback.print_exc()
            return None

