"""
Image downloader - Downloads images from URLs with proper handling.
"""

import os
import hashlib
from typing import Dict, Any, List, Optional, Generator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from io import BytesIO
from PIL import Image
import io


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    path: str = ""
    error: str = ""
    size_bytes: int = 0
    duration_ms: int = 0


class DownloadManager:
    """Manages image downloads with retry logic and rate limiting."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create session with retry logic."""
        session = requests.Session()
        
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=10,
            pool_maxsize=10
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def download_image(self, url: str, output_dir: str) -> DownloadResult:
        """
        Download an image from URL.
        
        Args:
            url: Image URL
            output_dir: Directory to save image
            
        Returns:
            DownloadResult with success status and path
        """
        start_time = datetime.now()
        output_path = Path(output_dir)
        
        try:
            # Get image data
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Generate filename
            filename = self._generate_filename(url)
            image_path = output_path / filename
            
            # Save image
            with open(image_path, 'wb') as f:
                f.write(response.content)
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            return DownloadResult(
                success=True,
                path=str(image_path),
                size_bytes=len(response.content),
                duration_ms=int(duration)
            )
            
        except requests.RequestException as e:
            return DownloadResult(
                success=False,
                error=str(e)
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                error=str(e)
            )
    
    def _generate_filename(self, url: str) -> str:
        """Generate unique filename from URL."""
        # Use URL hash as base
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        
        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return f"{url_hash}_{timestamp}.jpg"


class ImageDownloader:
    """Handles downloading and processing images from Instagram."""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.downloader = DownloadManager()
    
    def download_image(self, url: str, media_id: str, caption: str = "") -> DownloadResult:
        """
        Download and process a single image.
        
        Args:
            url: Image URL
            media_id: Unique media identifier
            caption: Optional caption for metadata
            
        Returns:
            DownloadResult with status
        """
        # Generate output filename
        safe_id = media_id.replace("/", "_").replace(":", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_id}_{timestamp}.jpg"
        
        output_path = self.output_dir / filename
        
        # Download image
        result = self.downloader.download_image(url, str(output_path.parent))
        
        if result.success:
            # Add metadata to filename
            metadata = f"_{caption[:50]}" if caption else ""
            final_path = output_path.parent / f"{safe_id}_{timestamp}{metadata}.jpg"
            
            # Move file if downloaded elsewhere
            if result.path != str(final_path):
                import shutil
                shutil.move(result.path, str(final_path))
                result.path = str(final_path)
        
        return result
    
    def download_images_batch(self, media_urls: List[str], 
                             max_concurrent: int = 3) -> Generator[DownloadResult, None, None]:
        """
        Download multiple images in batches.
        
        Args:
            media_urls: List of media URLs
            max_concurrent: Maximum concurrent downloads
            
        Yields:
            DownloadResult for each image
        """
        for media_url in media_urls:            
            if media_url:
                result = self.download_image(media_url, "", "")
                yield result
    
    def download_from_media_item(self, media_item) -> DownloadResult:
        """
        Download image from MediaItem object.
        
        Args:
            media_item: MediaItem object
            
        Returns:
            DownloadResult
        """
        url = media_item.url
        media_id = media_item.id
        caption = media_item.caption
        
        return self.download_image(url, media_id, caption)
    
    def validate_image(self, image_path: str) -> bool:
        """
        Validate that an image file is valid and readable.
        
        Args:
            image_path: Path to image file
            
        Returns:
            True if valid, False otherwise
        """
        try:
            with Image.open(image_path) as img:
                # Verify it's a proper image
                img.verify()
            
            # Open again to fully validate
            with Image.open(image_path) as img:
                # Check dimensions (LoRA optimal: 512x512 to 1024x1024)
                width, height = img.size
                min_dim = min(width, height)
                
                if min_dim < 256:
                    print(f"⚠ Image too small: {image_path} ({width}x{height})")
                    return False
                
                return True
                
        except Exception as e:
            print(f"⚠ Invalid image: {image_path} - {e}")
            return False
