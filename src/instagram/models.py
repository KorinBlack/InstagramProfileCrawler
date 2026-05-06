"""
Data models for Instagram entities.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


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
