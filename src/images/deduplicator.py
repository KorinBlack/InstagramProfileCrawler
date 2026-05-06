"""
Image deduplication using hash-based comparison.
"""

import hashlib
from typing import Dict, Set, Optional
from pathlib import Path
from PIL import Image
import os


class ImageDeduplicator:
    """
    Deduplicates images using multiple hashing strategies.
    
    Supports:
    - Content-based hashing (image data)
    - Perceptual hashing (similar images)
    - Metadata hashing (EXIF data)
    """
    
    def __init__(self, hash_size: int = 16):
        """
        Initialize deduplicator.
        
        Args:
            hash_size: Size of hash to use for filenames
        """
        self.hash_size = hash_size
    
    def compute_hash(self, image_path: str, hash_type: str = "content") -> Optional[str]:
        """
        Compute hash of image.
        
        Args:
            image_path: Path to image
            hash_type: Type of hash to compute
            
        Returns:
            Hash string or None if failed
        """
        try:
            if hash_type == "content":
                return self._compute_content_hash(image_path)
            elif hash_type == "perceptual":
                return self._compute_perceptual_hash(image_path)
            elif hash_type == "metadata":
                return self._compute_metadata_hash(image_path)
            else:
                return self._compute_content_hash(image_path)
        except Exception as e:
            print(f"⚠ Failed to compute hash: {e}")
            return None
    
    def _compute_content_hash(self, image_path: str) -> str:
        """Compute hash based on image content."""
        try:
            with open(image_path, 'rb') as f:
                # Read in chunks for memory efficiency
                hash_md5 = hashlib.md5()
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_md5.update(chunk)
                return hash_md5.hexdigest()[:self.hash_size]
        except Exception as e:
            print(f"⚠ Error computing content hash: {e}")
            return ""
    
    def _compute_perceptual_hash(self, image_path: str) -> str:
        """Compute perceptual hash (average hash)."""
        try:
            with Image.open(image_path) as img:
                # Resize to small size for faster computation
                img = img.resize((8, 8), Image.LANCZOS)
                
                # Convert to grayscale
                gray = img.convert('L')
                
                # Get pixel data
                pixels = list(gray.getdata())
                
                # Compute average
                average = sum(pixels) / len(pixels)
                
                # Create hash
                bits = ''.join(['1' if p > average else '0' for p in pixels])
                
                # Convert to hex
                hex_hash = hex(int(bits, 2))[2:].zfill(self.hash_size)
                return hex_hash
        except Exception as e:
            print(f"⚠ Error computing perceptual hash: {e}")
            return ""
    
    def _compute_metadata_hash(self, image_path: str) -> str:
        """Compute hash based on EXIF metadata."""
        try:
            with Image.open(image_path) as img:
                exif_data = img.getexif()
                
                if not exif_data:
                    return ""
                
                # Extract key metadata
                metadata = {}
                
                # Common tags
                tags = [
                    0x010f,  # Make
                    0x0110,  # Model
                    0x8298,  # DateTimeOriginal
                    0x9201,  # ExposureTime
                    0x9202,  # FNumber
                    0x9203,  # ISOSpeedRatings
                    0xa002,  # ExposureProgram
                    0xa20e,  # LensInfo
                ]
                
                for tag_id in tags:
                    if tag_id in exif_data:
                        metadata[str(tag_id)] = exif_data[tag_id]
                
                # Create hash from metadata
                if metadata:
                    metadata_str = str(sorted(metadata.items()))
                    return hashlib.md5(metadata_str.encode()).hexdigest()[:self.hash_size]
                return ""
        except Exception as e:
            print(f"⚠ Error computing metadata hash: {e}")
            return ""
    
    def find_duplicates(self, directory: str, 
                       hash_type: str = "content",
                       similarity_threshold: int = 10) -> Dict[str, list]:
        """
        Find duplicate images in directory.
        
        Args:
            directory: Directory to scan
            hash_type: Type of hash to use
            similarity_threshold: Number of matching bits for perceptual hash
            
        Returns:
            Dictionary mapping hash to list of duplicate files
        """
        directory = Path(directory)
        hashes: Dict[str, list] = {}
        
        # Get all image files
        image_extensions = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}
        image_files = [f for f in directory.iterdir() 
                      if f.is_file() and f.suffix.lower() in image_extensions]
        
        print(f"Scanning {len(image_files)} images...")
        
        for image_file in image_files:
            hash_value = self.compute_hash(str(image_file), hash_type)
            
            if hash_value and hash_value not in hashes:
                hashes[hash_value] = []
            
            if hash_value and hash_value in hashes:
                hashes[hash_value].append(str(image_file))
        
        # Filter duplicates (groups with more than one file)
        duplicates = {h: files for h, files in hashes.items() if len(files) > 1}
        
        print(f"Found {len(duplicates)} duplicate groups")
        
        return duplicates
    
    def is_duplicate(self, image_path: str, known_hashes: Set[str]) -> bool:
        """
        Check if image is duplicate of known images.
        
        Args:
            image_path: Path to check
            known_hashes: Set of known hash values
            
        Returns:
            True if duplicate, False otherwise
        """
        if not known_hashes:
            return False
        
        hash_value = self.compute_hash(image_path, "content")
        return hash_value in known_hashes
    
    def get_unique_images(self, directory: str) -> list:
        """
        Get list of unique images in directory.
        
        Args:
            directory: Directory to scan
            
        Returns:
            List of unique image paths
        """
        all_hashes = self.find_duplicates(directory)
        duplicate_hashes = set(all_hashes.keys())
        
        # Get all files
        image_extensions = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}
        all_files = [f for f in Path(directory).iterdir() 
                    if f.is_file() and f.suffix.lower() in image_extensions]
        
        # Filter out duplicates
        unique_files = [f for f in all_files 
                       if not any(
                           self.compute_hash(str(f), "content") in duplicate_hashes
                           for _ in range(1)  # Compute once
                       )]
        
        return unique_files
