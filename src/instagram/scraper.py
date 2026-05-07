"""
Instagram scraper - Core scraping logic for posts and stories.
"""

import os
import hashlib
from typing import Dict, Any, List, Optional, Generator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import re

from playwright.sync_api import sync_playwright

from .auth import InstagramAuth, SessionManager

@dataclass
class Story:
    """Represents an Instagram story highlight."""
    id: str
    title: str
    media_count: int
    cover_media: str
    items: List[MediaItem] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'media_count': self.media_count,
            'cover_media': self.cover_media,
            'items': [item.to_dict() for item in self.items]
        }

class InstagramScraper:
    """Core scraper for Instagram data."""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.rate_limit_delay = 1  # seconds between requests
    
    def scrape_profile(self, username: str, max_posts: int = 100):
        """
        Scrape complete profile data.
        
        Args:
            username: Instagram username
            max_posts: Maximum posts to scrape
            
        Returns:
            ProfileData object or None if failed
        """
        print(f"\n🔍 Scraping profile: @{username}")

        profile_data = {}
                
        # Get basic profile info
        profile_info = self.session_manager.scrape_profile(username)
        if not profile_info:
            return None
        profile_data["profile_info"] = profile_info
        
        # Scrape posts
        print(f"📸 Scraping posts (max: {max_posts})...")
        image_urls = self._scrape_posts(username, max_posts)
        if not image_urls:
            print(f"✗ Failed to scrape posts  {username}")
        profile_data['image_urls'] = image_urls
        
        # Scrape stories
        print(f"⭐ Scraping stories...")
        stories = self._scrape_stories(username)
        profile_data['stories'] = stories
        
        print(f"✓ Profile scraped successfully!")
        print(f"  Posts: {len(image_urls)}")
        print(f"  Stories: {len(stories)}")
        
        return profile_data
    
    def _scrape_posts(self, username: str, max_posts: int):
        """Scrape posts from profile."""
        image_urls = []   
        try:
            with sync_playwright() as playwright:
                context, browser = self.session_manager.auth._preflight_config_proxyed(playwright)
                feed = context.request.get(
                            f'https://i.instagram.com/api/v1/feed/user/{username}/username/',
                            headers = {"User-Agent": "iphone_ua", "x-ig-app-id": "936619743392459"}
                        ).json()
                browser.close()
                if not feed:
                    print(f"✗ Failed to get feed data for {username}")
                    return None
            for element in feed.get('items', []):
                if element.get('media_type') == 1:  # Image
                    image_urls.append(self._extract_url(element))
                elif element.get('media_type') == 8:  # Carousel
                    for carousel_item in element.get('carousel_media', []):
                        image_urls.append(self._extract_url(carousel_item))
            return image_urls
                
                
        except Exception as e:
            print(f"✗ Failed to scrape posts: {e}")
            return image_urls
    
    def _extract_url(self, element) -> str:
        """Extract URL from a single element."""
        return element.get('image_versions2', {}).get('candidates', [{}])[0].get('url', '')
    

    def _scrape_stories(self, username: str) -> List[Story]:
        """Scrape story highlights."""
        stories = []
        
        try:
            with sync_playwright() as playwright:
                context, browser = self.session_manager.auth._preflight_config_proxyed(playwright)
                if not context:
                    return stories
                
                page = context.new_page()
                page.goto(f"https://www.instagram.com/{username}/highlight-reel/", wait_until="networkidle")
                
                story_elements = page.locator('div._1107b9 div._1107b9 div._1107b9')
                
                for story in story_elements.all():
                    try:
                        story_data = self._extract_story(story)
                        if story_data:
                            stories.append(story_data)
                    except Exception as e:
                        print(f"⚠ Failed to extract story: {e}")
                
                page.close()
                browser.close()
            
        except Exception as e:
            print(f"✗ Failed to scrape stories: {e}")
        
        return stories
    
    def _extract_story(self, element) -> Optional[Story]:
        """Extract data from a story highlight."""
        try:
            title = element.locator('div._1107b9 div._1107b9 div._1107b9 div._1107b9').inner_text().strip()
            if not title:
                return None
            
            cover_url = element.locator('img').get_attribute('src') or ""
            
            # Get media count
            media_count_text = element.locator('div._1107b9 div._1107b9 div._1107b9 div._1107b9').inner_text()
            media_count = self._extract_number(media_count_text)
            
            # Extract media items
            items = []
            media_items = element.locator('div._1107b9 div._1107b9 div._1107b9 div._1107b9 div._1107b9')
            
            for item in media_items.all():
                try:
                    media_url = item.locator('img').get_attribute('src') or ""
                    if media_url:
                        items.append(MediaItem(
                            id=f"{title}_{hashlib.md5(media_url.encode()).hexdigest()[:8]}",
                            type='story',
                            url=media_url,
                            thumbnail_url=media_url,
                            timestamp=datetime.now().isoformat()
                        ))
                except:
                    continue
            
            return Story(
                id=f"highlight_{hashlib.md5(title.encode()).hexdigest()[:8]}",
                title=title,
                media_count=media_count,
                cover_media=cover_url,
                items=items
            )
            
        except Exception as e:
            print(f"⚠ Error extracting story: {e}")
            return None
