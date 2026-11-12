"""
Image optimizer - Processes images for optimal LoRA training.
"""

import os
from typing import List
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageFilter
import numpy as np


@dataclass
class OptimizationResult:
    """Result of image optimization."""
    success: bool
    path: str = ""
    original_size: int = 0
    optimized_size: int = 0
    reduction: float = 0.0
    dimensions: tuple = (0, 0)
    error: str = ""


class ImageOptimizer:
    """
    Optimizes images for LoRA training.
    
    LoRA training benefits from:
    - Consistent dimensions (512x512 to 1024x1024 recommended)
    - High quality but not excessive resolution
    - Proper color space (RGB)
    - Minimal compression artifacts
    """
    
    def __init__(self, 
                 target_size: int = 1024,
                 max_size_mb: float = 5.0,
                 quality: int = 95):
        """
        Initialize optimizer.
        
        Args:
            target_size: Target dimension (square recommended)
            max_size_mb: Maximum file size in MB
            quality: JPEG quality (0-100)
        """
        self.target_size = target_size
        self.max_size_mb = max_size_mb * 1024 * 1024
        self.quality = quality
    
    def optimize_image(self, image_path: str, 
                      output_dir: str = None) -> OptimizationResult:
        """
        Optimize a single image for LoRA training.
        
        Args:
            image_path: Path to input image
            output_dir: Directory to save optimized image
            
        Returns:
            OptimizationResult with details
        """
        if output_dir:
            output_path = Path(output_dir)
        else:
            output_path = Path(image_path).parent
        
        try:
            # Load image
            with Image.open(image_path) as img:
                original_size = img.size
                original_size_bytes = self._get_file_size(image_path)
                
                # Convert to RGB if necessary
                if img.mode not in ('RGB', 'LA'):
                    img = img.convert('RGB')
                
                # Optimize dimensions
                optimized_img = self._optimize_dimensions(img, original_size)
                
                # Apply enhancements
                enhanced_img = self._apply_enhancements(optimized_img)
                
                # Resize to target if too large
                final_img = self._resize_if_needed(enhanced_img, original_size)
                
                # Save optimized image
                output_file = output_path / Path(image_path).name
                self._save_image(final_img, output_file)
                
                optimized_size = self._get_file_size(str(output_file))
                reduction = ((original_size_bytes - optimized_size) / original_size_bytes) * 100
                
                return OptimizationResult(
                    success=True,
                    path=str(output_file),
                    original_size=original_size_bytes,
                    optimized_size=optimized_size,
                    reduction=reduction,
                    dimensions=final_img.size
                )
                
        except Exception as e:
            return OptimizationResult(
                success=False,
                error=str(e)
            )
    
    def optimize_batch(self, image_paths: List[str], 
                      output_dir: str = None) -> List[OptimizationResult]:
        """
        Optimize multiple images.
        
        Args:
            image_paths: List of input image paths
            output_dir: Directory to save optimized images
            
        Returns:
            List of OptimizationResult objects
        """
        results = []
        
        for i, path in enumerate(image_paths):
            print(f"Optimizing {i+1}/{len(image_paths)}: {Path(path).name}")
            result = self.optimize_image(path, output_dir)
            results.append(result)
            
            if result.success:
                print(f"  ✓ {result.dimensions[0]}x{result.dimensions[1]}, "
                      f"saved {result.reduction:.1f}%")
        
        return results
    
    def _optimize_dimensions(self, img: Image.Image, 
                            original_size: tuple) -> Image.Image:
        """
        Optimize image dimensions for LoRA training.
        
        LoRA works best with:
        - Square images (512x512, 768x768, 1024x1024)
        - Or consistent aspect ratio
        """
        width, height = img.size
        
        # If image is already good size, return as is
        if 512 <= min(width, height) <= 1024:
            return img
        
        # Resize to target size maintaining aspect ratio
        if max(width, height) > self.target_size:
            ratio = self.target_size / max(width, height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
        
        # Crop to square if needed (center crop)
        if width != height:
            # Calculate crop box
            crop_box = self._calculate_crop_box(img.size, self.target_size)
            img = img.crop(crop_box)
        
        return img
    
    def _calculate_crop_box(self, size: tuple, target_size: int) -> tuple:
        """Calculate crop box for center crop to square."""
        width, height = size
        
        if width == height:
            return (0, 0, width, height)
        
        # Determine which side to crop
        if width > height:
            # Crop from width
            crop_width = height
            crop_left = (width - crop_width) // 2
            return (crop_left, 0, crop_left + crop_width, height)
        else:
            # Crop from height
            crop_height = width
            crop_top = (height - crop_height) // 2
            return (0, crop_top, width, crop_top + crop_height)
    
    def _apply_enhancements(self, img: Image.Image) -> Image.Image:
        """
        Apply enhancements to improve image quality for training.
        
        Enhancements:
        - Smart cropping (remove borders)
        - Color correction
        - Noise reduction
        """
        # Skip enhancements for very small images
        if min(img.size) < 512:
            return img
        
        # Apply smart cropping to remove borders
        img = self._smart_crop(img)
        
        # Apply slight sharpening
        img = img.filter(ImageFilter.SHARPEN)
        
        return img
    
    def _smart_crop(self, img: Image.Image) -> Image.Image:
        """
        Smart crop to remove borders and improve composition.
        
        Uses edge detection to find the most interesting area.
        """
        if min(img.size) < 512:
            return img
        
        # Convert to grayscale
        gray = img.convert('L')
        
        # Apply blur to smooth out noise
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=2))
        
        # Find edges
        edges = blurred.filter(ImageFilter.FIND_EDGES)
        
        # Calculate bounding box of non-zero pixels
        pixels = np.array(edges)
        coords = np.argwhere(pixels > 0)
        
        if len(coords) == 0:
            return img
        
        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)
        
        # Add padding
        padding = 20
        y_min = max(0, y_min - padding)
        x_min = max(0, x_min - padding)
        y_max = min(img.height, y_max + padding)
        x_max = min(img.width, x_max + padding)
        
        # Crop
        cropped = img.crop((x_min, y_min, x_max, y_max))
        
        return cropped
    
    def _resize_if_needed(self, img: Image.Image, 
                         original_size: tuple) -> Image.Image:
        """
        Resize image if it exceeds maximum recommended size.
        
        LoRA training is more efficient with smaller images.
        """
        width, height = img.size
        
        # If image is already within target size, return as is
        if max(width, height) <= self.target_size:
            return img
        
        # Resize down
        ratio = self.target_size / max(width, height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        
        return img.resize((new_width, new_height), Image.LANCZOS)
    
    def _save_image(self, img: Image.Image, output_path: Path):
        """Save image with optimal settings."""
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Determine format
        if output_path.suffix.lower() == '.png':
            img.save(output_path, 'PNG', quality=self.quality)
        else:
            # JPEG with optimal settings
            img.save(output_path, 'JPEG', 
                    quality=self.quality,
                    optimize=True,
                    progressive=True)
    
    def _get_file_size(self, path: str) -> int:
        """Get file size in bytes."""
        try:
            return os.path.getsize(path)
        except:
            return 0
