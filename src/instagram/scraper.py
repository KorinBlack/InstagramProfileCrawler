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

from .auth import InstagramAuth, SessionManager


@dataclass
class MediaItem:
    """Represents a single media item (post or story)."""
    id: str
    type: str  # 'post' or 'story'
    url: str
    thumbnail_url: str
    caption: str = ""
    timestamp: str = ""
    likes: int = 0
    comments: int = 0
    location: str = ""
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'type': self.type,
            'url': self.url,
            'thumbnail_url': self.thumbnail_url,
            'caption': self.caption,
            'timestamp': self.timestamp,
            'likes': self.likes,
            'comments': self.comments,
            'location': self.location,
            'tags': self.tags
        }


@dataclass
class Post:
    """Represents an Instagram post."""
    id: str
    shortcode: str
    media_type: str  # 'image', 'video', 'carousel'
    thumbnail_url: str
    display_url: str
    caption: str
    likes: int
    comments: int
    timestamp: str
    location: str = ""
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'shortcode': self.shortcode,
            'media_type': self.media_type,
            'thumbnail_url': self.thumbnail_url,
            'display_url': self.display_url,
            'caption': self.caption,
            'likes': self.likes,
            'comments': self.comments,
            'timestamp': self.timestamp,
            'location': self.location,
            'tags': self.tags
        }


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


@dataclass
class ProfileData:
    """Complete profile data structure."""
    username: str
    full_name: str
    followers: int
    posts_count: int
    is_verified: bool
    bio: str
    profile_pic_url: str
    posts: List[Post] = field(default_factory=list)
    stories: List[Story] = field(default_factory=list)
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'username': self.username,
            'full_name': self.full_name,
            'followers': self.followers,
            'posts_count': self.posts_count,
            'is_verified': self.is_verified,
            'bio': self.bio,
            'profile_pic_url': self.profile_pic_url,
            'posts': [p.to_dict() for p in self.posts],
            'stories': [s.to_dict() for s in self.stories],
            'timestamp': self.timestamp
        }


class InstagramScraper:
    """Core scraper for Instagram data."""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.rate_limit_delay = 1  # seconds between requests
    
    def scrape_profile(self, username: str, max_posts: int = 100) -> Optional[ProfileData]:
        """
        Scrape complete profile data.
        
        Args:
            username: Instagram username
            max_posts: Maximum posts to scrape
            
        Returns:
            ProfileData object or None if failed
        """
        print(f"\n🔍 Scraping profile: @{username}")
        
        # Get basic profile info
        profile_info = self.session_manager.scrape_profile(username)
        if not profile_info:
            return None
        
        profile_data = ProfileData(
            username=username,
            full_name=profile_info.get('full_name', ''),
            followers=profile_info.get('followers', 0),
            posts_count=profile_info.get('posts_count', 0),
            is_verified=profile_info.get('is_verified', False),
            bio=profile_info.get('bio', ''),
            profile_pic_url=profile_info.get('profile_pic_url', ''),
            timestamp=datetime.now().isoformat()
        )
        
        # Scrape posts
        print(f"📸 Scraping posts (max: {max_posts})...")
        posts = self._scrape_posts(username, max_posts)
        profile_data.posts = posts
        
        # Scrape stories
        print(f"⭐ Scraping stories...")
        stories = self._scrape_stories(username)
        profile_data.stories = stories
        
        print(f"✓ Profile scraped successfully!")
        print(f"  Posts: {len(posts)}")
        print(f"  Stories: {len(stories)}")
        
        return profile_data
    
    def _scrape_posts(self, username: str, max_posts: int) -> List[Post]:
        """Scrape posts from profile."""
        posts = []
        
        try:
            context = self.session_manager.auth.get_context()
            if not context:
                return posts
            
            page = context.new_page()
            page.goto(f"https://www.instagram.com/{username}/", wait_until="networkidle")
            
            # Extract posts from grid (simplified - real implementation needs GraphQL API)
            post_elements = page.locator('article._ap3x1d')
            
            for i, post in enumerate(post_elements.all()):
                if len(posts) >= max_posts:
                    break
                
                # Rate limiting
                if i > 0:
                    import time
                    time.sleep(self.rate_limit_delay)
                
                try:
                    post_data = self._extract_post(post, username)
                    if post_data:
                        posts.append(post_data)
                except Exception as e:
                    print(f"⚠ Failed to extract post {i}: {e}")
                    continue
            
            page.close()
            
        except Exception as e:
            print(f"✗ Failed to scrape posts: {e}")
        
        return posts
    
    def _extract_post(self, element, username: str) -> Optional[Post]:
        """Extract data from a single post element."""
        try:
            shortcode = element.get_attribute('data-x') or element.get_attribute('data-shortcode') or ""
            if not shortcode:
                return None
            
            # Get media type
            media_type = self._get_media_type(element)
            
            # Get thumbnail URL
            thumbnail_url = element.locator('img').get_attribute('src') or ""
            
            # Get caption
            caption = element.locator('div._17xg7g').inner_text().strip()
            
            # Get likes
            likes_text = element.locator('div._1107b9').inner_text()
            likes = self._extract_number(likes_text)
            
            # Get timestamp
            timestamp = element.locator('time').get_attribute('datetime') or ""
            
            # Get location
            location = element.locator('div._1107b9 div._1107b9').inner_text().strip()
            
            # Get tags
            tags = self._extract_tags(element)
            
            return Post(
                id=f"{username}_{shortcode}",
                shortcode=shortcode,
                media_type=media_type,
                thumbnail_url=thumbnail_url,
                display_url=thumbnail_url,  # Would need to extract from __typename
                caption=caption,
                likes=likes,
                comments=0,  # Would need separate API call
                timestamp=timestamp,
                location=location,
                tags=tags
            )
            
        except Exception as e:
            print(f"⚠ Error extracting post: {e}")
            return None
    
    def _get_media_type(self, element) -> str:
        """Determine media type from post element."""
        try:
            if element.locator('div._1107b9 div._1107b9 div._1107b9'):  # Carousel
                return 'carousel'
            elif element.locator('video'):  # Video
                return 'video'
            else:
                return 'image'
        except:
            return 'image'
    
    def _extract_number(self, text: str) -> int:
        """Extract number from text (handles "999+", "1.2M", etc.)."""
        try:
            text = text.strip().replace(',', '')
            if '+' in text:
                return 999999  # Return max for "999+"
            
            # Handle millions/billions
            if 'M' in text:
                return int(float(text.replace('M', '')) * 1_000_000)
            elif 'B' in text:
                return int(float(text.replace('B', '')) * 1_000_000_000)
            
            return int(float(text))
        except:
            return 0
    
    def _extract_tags(self, element) -> List[str]:
        """Extract hashtags from post."""
        try:
            text = element.inner_text().lower()
            tags = re.findall(r'#\w+', text)
            return [tag[1:] for tag in tags]  # Remove '#'
        except:
            return []
    
    def _scrape_stories(self, username: str) -> List[Story]:
        """Scrape story highlights."""
        stories = []
        
        try:
            context = self.session_manager.auth.get_context()
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
