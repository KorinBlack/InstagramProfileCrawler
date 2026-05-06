"""
Statistics tracking for the application.
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict


@dataclass
class DownloadStats:
    """Statistics for downloads."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    total_bytes: int = 0
    total_duration_ms: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100
    
    @property
    def avg_size_bytes(self) -> int:
        if self.total == 0:
            return 0
        return self.total_bytes // self.total
    
    @property
    def avg_duration_ms(self) -> int:
        if self.total == 0:
            return 0
        return self.total_duration_ms // self.total


@dataclass
class ProcessingStats:
    """Statistics for image processing."""
    total: int = 0
    optimized: int = 0
    filtered: int = 0
    duplicates: int = 0
    failed: int = 0
    
    @property
    def optimization_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.optimized / self.total) * 100
    
    @property
    def filter_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.filtered / self.total) * 100


@dataclass
class CaptionStats:
    """Statistics for caption generation."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    total_tokens: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100


@dataclass
class OverallStats:
    """Overall statistics for a complete run."""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    download_stats: DownloadStats = field(default_factory=DownloadStats)
    processing_stats: ProcessingStats = field(default_factory=ProcessingStats)
    caption_stats: CaptionStats = field(default_factory=CaptionStats)
    
    # Additional metrics
    profiles_processed: int = 0
    total_images: int = 0
    unique_images: int = 0
    
    @property
    def duration(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0
    
    @property
    def images_per_second(self) -> float:
        if self.duration == 0:
            return 0
        return self.unique_images / self.duration
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'duration_seconds': self.duration,
            'images_per_second': self.images_per_second,
            'profiles_processed': self.profiles_processed,
            'total_images': self.total_images,
            'unique_images': self.unique_images,
            'download_stats': {
                'total': self.download_stats.total,
                'successful': self.download_stats.successful,
                'failed': self.download_stats.failed,
                'success_rate': f"{self.download_stats.success_rate:.1f}%"
            },
            'processing_stats': {
                'total': self.processing_stats.total,
                'optimized': self.processing_stats.optimized,
                'filtered': self.processing_stats.filtered,
                'duplicates': self.processing_stats.duplicates,
                'optimization_rate': f"{self.processing_stats.optimization_rate:.1f}%"
            },
            'caption_stats': {
                'total': self.caption_stats.total,
                'successful': self.caption_stats.successful,
                'failed': self.caption_stats.failed,
                'success_rate': f"{self.caption_stats.success_rate:.1f}%"
            }
        }


class StatisticsTracker:
    """Tracks statistics throughout the application run."""
    
    def __init__(self):
        self.stats = OverallStats()
        self._start_time = time.time()
    
    def record_download(self, success: bool, size_bytes: int = 0, duration_ms: int = 0):
        """Record a download."""
        self.stats.download_stats.total += 1
        if success:
            self.stats.download_stats.successful += 1
            self.stats.download_stats.total_bytes += size_bytes
            self.stats.download_stats.total_duration_ms += duration_ms
        else:
            self.stats.download_stats.failed += 1
    
    def record_processing(self, success: bool, optimized: bool = False, 
                         is_duplicate: bool = False, filtered: bool = False):
        """Record processing result."""
        self.stats.processing_stats.total += 1
        if optimized:
            self.stats.processing_stats.optimized += 1
        if is_duplicate:
            self.stats.processing_stats.duplicates += 1
        if filtered:
            self.stats.processing_stats.filtered += 1
        if not success:
            self.stats.processing_stats.failed += 1
    
    def record_caption(self, success: bool, tokens: int = 0):
        """Record caption generation."""
        self.stats.caption_stats.total += 1
        if success:
            self.stats.caption_stats.successful += 1
            self.stats.caption_stats.total_tokens += tokens
        else:
            self.stats.caption_stats.failed += 1
    
    def record_profile(self):
        """Record a processed profile."""
        self.stats.profiles_processed += 1
    
    def record_image(self, total: int, unique: int = 0):
        """Record image processing."""
        self.stats.total_images += total
        self.stats.unique_images += unique
    
    def finalize(self):
        """Finalize statistics."""
        self.stats.end_time = datetime.now()
    
    def get_summary(self) -> str:
        """Get formatted summary."""
        self.finalize()
        
        lines = [
            f"📊 Overall Statistics",
            f"{'=' * 40}",
            f"Duration: {self.stats.duration:.2f}s",
            f"Images/sec: {self.stats.images_per_second:.2f}",
            f"Profiles: {self.stats.profiles_processed}",
            f"Total Images: {self.stats.total_images}",
            f"Unique Images: {self.stats.unique_images}",
            "",
            f"📥 Downloads",
            f"  Total: {self.stats.download_stats.total}",
            f"  Success: {self.stats.download_stats.successful} ({self.stats.download_stats.success_rate:.1f}%)",
            f"  Failed: {self.stats.download_stats.failed}",
            "",
            f"🖼️ Processing",
            f"  Total: {self.stats.processing_stats.total}",
            f"  Optimized: {self.stats.processing_stats.optimized}",
            f"  Filtered: {self.stats.processing_stats.filtered}",
            f"  Duplicates: {self.stats.processing_stats.duplicates}",
            "",
            f"📝 Captions",
            f"  Total: {self.stats.caption_stats.total}",
            f"  Success: {self.stats.caption_stats.successful} ({self.stats.caption_stats.success_rate:.1f}%)",
            f"  Failed: {self.stats.caption_stats.failed}",
        ]
        
        return "\n".join(lines)
