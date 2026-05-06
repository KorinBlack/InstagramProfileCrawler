"""
Visual AI integration using Ollama for image filtering and captioning.
"""

import os
from typing import Dict, Any, List, Optional, Generator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import base64
from PIL import Image
import io

try:
    from ollama import chat, generate
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


@dataclass
class VisualAIResult:
    """Result from Visual AI processing."""
    success: bool
    filtered: bool = False
    caption: str = ""
    negative_caption: str = ""
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    error: str = ""
    processing_time_ms: int = 0


class VisualAI:
    """
    Visual AI integration for image filtering and analysis.
    
    Uses Ollama with vision-capable models like:
    - llava
    - babyllama
    - mistral (with vision)
    """
    
    def __init__(self, 
                 route: str = "http://localhost:11434/api/generate",
                 model: str = "llava"):
        """
        Initialize Visual AI.
        
        Args:
            route: Ollama API endpoint
            model: Model name to use
        """
        self.route = route
        self.model = model
        self.available = OLLAMA_AVAILABLE
    
    def check_availability(self) -> bool:
        """Check if Ollama is running and model is available."""
        if not self.available:
            return False
        
        try:
            # Test connection
            generate(
                model=self.model,
                prompt="ping",
                stream=False
            )
            return True
        except Exception as e:
            print(f"⚠ Ollama unavailable: {e}")
            return False
    
    def filter_image(self, image_path: str) -> VisualAIResult:
        """
        Analyze image and determine if it should be kept.
        
        Args:
            image_path: Path to image
            
        Returns:
            VisualAIResult with filtering decision
        """
        if not self.available:
            return VisualAIResult(
                success=False,
                error="Ollama not available"
            )
        
        try:
            # Encode image
            with Image.open(image_path) as img:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=90)
                img_byte_arr.seek(0)
                base64_image = base64.b64encode(img_byte_arr.read()).decode('utf-8')
            
            # Analyze image
            prompt = f"""
            Analyze this image and determine if it's suitable for LoRA training.
            Return ONLY a JSON object with:
            {{
                "keep": true/false,
                "reason": "brief explanation",
                "confidence": 0.0-1.0
            }}
            
            Consider filtering out:
            - Watermarks or logos
            - Low quality / blurry images
            - Screenshots
            - Text-heavy images
            - Duplicate-looking images
            - Inappropriate content
            """
            
            response = generate(
                model=self.model,
                prompt=prompt,
                images=[base64_image],
                stream=False
            )
            
            # Parse response
            try:
                response_text = response.get('response', '').strip()
                if not response_text:
                    raise ValueError("Empty response")
                
                # Extract JSON from response
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start == -1 or json_end == 0:
                    raise ValueError("No JSON in response")
                
                json_data = json.loads(response_text[json_start:json_end])
                
                keep = json_data.get('keep', False)
                confidence = json_data.get('confidence', 0.0)
                
                return VisualAIResult(
                    success=True,
                    filtered=not keep,
                    confidence=confidence,
                    tags=self._extract_tags(response_text)
                )
                
            except Exception as e:
                print(f"⚠ Failed to parse response: {e}")
                return VisualAIResult(
                    success=False,
                    error=f"Failed to parse response: {e}"
                )
                
        except Exception as e:
            print(f"⚠ Failed to filter image: {e}")
            return VisualAIResult(
                success=False,
                error=str(e)
            )
    
    def generate_caption(self, image_path: str, 
                        include_negative: bool = True) -> VisualAIResult:
        """
        Generate caption for image using Visual AI.
        
        Args:
            image_path: Path to image
            include_negative: Whether to generate negative prompt
            
        Returns:
            VisualAIResult with captions
        """
        if not self.available:
            return VisualAIResult(
                success=False,
                error="Ollama not available"
            )
        
        try:
            # Encode image
            with Image.open(image_path) as img:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=90)
                img_byte_arr.seek(0)
                base64_image = base64.b64encode(img_byte_arr.read()).decode('utf-8')
            
            # Generate main caption
            prompt = f"""
            Generate a detailed caption for this image suitable for LoRA training.
            
            Requirements:
            - 1-2 sentences describing the main subject and composition
            - Include key visual elements, colors, lighting
            - Natural language, not tags
            - Max 100 words
            
            Return ONLY the caption text, nothing else.
            """
            
            response = generate(
                model=self.model,
                prompt=prompt,
                images=[base64_image],
                stream=False
            )
            
            caption = response.get('response', '').strip()
            
            # Generate negative caption
            negative_caption = ""
            if include_negative:
                prompt = f"""
                Generate a negative prompt for this image to help the LoRA model
                learn what to avoid.
                
                Requirements:
                - List common artifacts, styles, or elements to avoid
                - Comma-separated keywords
                - Max 50 words
                
                Return ONLY the negative prompt, nothing else.
                """
                
                response = generate(
                    model=self.model,
                    prompt=prompt,
                    images=[base64_image],
                    stream=False
                )
                
                negative_caption = response.get('response', '').strip()
            
            # Extract tags
            tags = self._extract_tags(caption)
            
            return VisualAIResult(
                success=True,
                caption=caption,
                negative_caption=negative_caption,
                tags=tags,
                confidence=0.85  # Default confidence
            )
                
        except Exception as e:
            print(f"⚠ Failed to generate caption: {e}")
            return VisualAIResult(
                success=False,
                error=str(e)
            )
    
    def generate_caption_pairs(self, image_path: str,
                              output_dir: str) -> Generator[Dict[str, Any], None, None]:
        """
        Generate caption pairs for LoRA training and save to file.
        
        Args:
            image_path: Path to image
            output_dir: Directory to save caption files
            
        Yields:
            Dictionary with caption data
        """
        if not self.available:
            return
        
        try:
            # Get captions
            result = self.generate_caption(image_path, include_negative=True)
            
            if not result.success:
                print(f"⚠ Failed to generate captions for {Path(image_path).name}")
                return
            
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            image_name = Path(image_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create caption data
            caption_data = {
                'image': image_name,
                'prompt': result.caption,
                'negative_prompt': result.negative_caption,
                'confidence': result.confidence,
                'tags': result.tags,
                'timestamp': datetime.now().isoformat()
            }
            
            # Save as JSON
            json_file = output_path / f"{image_name}_{timestamp}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(caption_data, f, indent=2, ensure_ascii=False)
            
            print(f"✓ Saved captions to {json_file.name}")
            
            yield {
                'image': image_name,
                'json_file': str(json_file),
                'prompt': result.caption,
                'negative_prompt': result.negative_caption
            }
            
        except Exception as e:
            print(f"⚠ Failed to save caption pairs: {e}")
    
    def _extract_tags(self, text: str) -> List[str]:
        """Extract potential tags from text."""
        if not text:
            return []
        
        # Simple tag extraction based on common patterns
        words = text.lower().split()
        common_nouns = [
            'person', 'people', 'portrait', 'landscape', 'nature',
            'building', 'architecture', 'food', 'animal', 'pet',
            'car', 'vehicle', 'fashion', 'clothing', 'technology',
            'product', 'object', 'scene', 'environment'
        ]
        
        tags = []
        for word in words:
            if len(word) > 4 and word not in ['the', 'and', 'or', 'but', 'is', 'are']:
                # Check if it might be a tag
                if any(noun in word for noun in common_nouns):
                    tags.append(word)
        
        return list(set(tags))[:10]  # Limit to 10 tags


class CaptionGenerator:
    """
    Batch caption generator for multiple images.
    """
    
    def __init__(self, visual_ai: VisualAI, batch_size: int = 3):
        """
        Initialize caption generator.
        
        Args:
            visual_ai: VisualAI instance
            batch_size: Number of images to process at once
        """
        self.visual_ai = visual_ai
        self.batch_size = batch_size
    
    def generate_all(self, image_paths: List[str],
                    output_dir: str) -> List[Dict[str, Any]]:
        """
        Generate captions for all images.
        
        Args:
            image_paths: List of image paths
            output_dir: Directory to save caption files
            
        Returns:
            List of caption results
        """
        results = []
        
        for i in range(0, len(image_paths), self.batch_size):
            batch = image_paths[i:i + self.batch_size]
            
            print(f"\n📝 Generating captions for batch {i//self.batch_size + 1}...")
            
            for result in self.visual_ai.generate_caption_pairs(
                batch[0],  # Process first image as representative
                output_dir
            ):
                results.append(result)
        
        return results
