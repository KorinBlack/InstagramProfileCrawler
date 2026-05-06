"""
Example script demonstrating how to use InstagramProfileCrawler.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PIL import Image


def example_basic_usage():
    """Example: Basic profile scraping and downloading."""
    from src.utils.logger import Logger
    from src.instagram.auth import SessionManager
    from src.instagram.scraper import InstagramScraper
    from src.images.downloader import ImageDownloader
    
    logger = Logger("Example")
    logger.print_header("Basic Usage Example")
    
    # Initialize components
    session_manager = SessionManager()
    scraper = InstagramScraper(session_manager)
    downloader = ImageDownloader("./example_dataset")
    
    try:
        # Scrape profile (requires valid session ID)
        profile = scraper.scrape_profile("example_username", max_posts=10)
        
        if profile:
            print(f"\nProfile: @{profile.username}")
            print(f"  Posts: {len(profile.posts)}")
            print(f"  Stories: {len(profile.stories)}")
            
            # Download images
            media_items = []
            for post in profile.posts:
                media_items.append({
                    'id': post.id,
                    'url': post.thumbnail_url,
                    'caption': post.caption
                })
            
            print(f"\nDownloading {len(media_items)} images...")
            for result in downloader.download_images_batch(media_items):
                if result.success:
                    print(f"  ✓ Downloaded: {result.path}")
                else:
                    print(f"  ✗ Failed: {result.error}")
        
    finally:
        session_manager.auth.close()


def example_with_optimization():
    """Example: Full pipeline with optimization."""
    from src.utils.logger import Logger
    from src.instagram.auth import SessionManager
    from src.instagram.scraper import InstagramScraper
    from src.images.downloader import ImageDownloader
    from src.images.optimizer import ImageOptimizer
    from src.images.deduplicator import ImageDeduplicator
    
    logger = Logger("Example")
    logger.print_header("Optimization Example")
    
    # Initialize components
    session_manager = SessionManager()
    scraper = InstagramScraper(session_manager)
    downloader = ImageDownloader("./optimized_dataset")
    optimizer = ImageOptimizer(target_size=1024)
    deduplicator = ImageDeduplicator()
    
    try:
        # Scrape profile
        profile = scraper.scrape_profile("example_username", max_posts=20)
        
        if profile:
            # Collect media items
            media_items = []
            for post in profile.posts:
                media_items.append({
                    'id': post.id,
                    'url': post.thumbnail_url,
                    'caption': post.caption
                })
            
            # Download
            print(f"\nDownloading {len(media_items)} images...")
            for result in downloader.download_images_batch(media_items):
                if result.success:
                    print(f"  ✓ {result.path}")
            
            # Deduplicate
            print("\nDeduplicating...")
            duplicates = deduplicator.find_duplicates("./optimized_dataset")
            print(f"  Found {len(duplicates)} duplicate groups")
            
            # Optimize
            print("\nOptimizing images...")
            image_files = [f for f in Path("./optimized_dataset").iterdir() 
                         if f.is_file() and f.suffix.lower() == '.jpg']
            
            for image_file in image_files:
                result = optimizer.optimize_image(str(image_file), "./optimized_dataset")
                if result.success:
                    print(f"  ✓ {image_file.name} -> {result.dimensions}")
        
    finally:
        session_manager.auth.close()


def example_visual_ai():
    """Example: Using Visual AI for captioning."""
    from src.utils.logger import Logger
    from src.instagram.auth import SessionManager
    from src.instagram.scraper import InstagramScraper
    from src.images.downloader import ImageDownloader
    from src.filtering.visual_ai import VisualAI
    
    logger = Logger("Example")
    logger.print_header("Visual AI Example")
    
    # Initialize components
    session_manager = SessionManager()
    scraper = InstagramScraper(session_manager)
    downloader = ImageDownloader("./ai_dataset")
    visual_ai = VisualAI()
    
    try:
        # Scrape and download
        profile = scraper.scrape_profile("example_username", max_posts=5)
        
        if profile:
            media_items = []
            for post in profile.posts:
                media_items.append({
                    'id': post.id,
                    'url': post.thumbnail_url,
                    'caption': post.caption
                })
            
            for result in downloader.download_images_batch(media_items):
                if result.success:
                    print(f"  ✓ Downloaded: {result.path}")
            
            # Generate captions
            print("\nGenerating captions with Visual AI...")
            image_files = [f for f in Path("./ai_dataset").iterdir() 
                         if f.is_file() and f.suffix.lower() == '.jpg']
            
            if image_files:
                sample_image = image_files[0]
                result = visual_ai.generate_caption(str(sample_image))
                
                if result.success:
                    print(f"\nCaption for {sample_image.name}:")
                    print(f"  {result.caption}")
                    print(f"\nTags: {', '.join(result.tags)}")
        
    finally:
        session_manager.auth.close()


def example_with_env_config():
    """Example: Using environment configuration."""
    from src.utils.logger import Logger
    from src.config.env import EnvConfig
    
    logger = Logger("Example")
    logger.print_header("Environment Config Example")
    
    # Load environment config
    config = EnvConfig()
    
    print(f"Output directory: {config.output_dir}")
    print(f"Max images: {config.max_images}")
    print(f"Visual AI route: {config.visual_ai_route}")
    print(f"Generate captions: {config.generate_captions}")
    
    # Validate config
    errors = config.validate()
    if errors:
        print("\nConfiguration errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✓ Configuration is valid")


if __name__ == "__main__":
    # Run examples
    print("\n" + "="*60)
    print("InstagramProfileCrawler - Examples")
    print("="*60 + "\n")
    
    # Example 1: Basic usage
    print("\n" + "-"*60)
    print("1. Basic Usage")
    print("-"*60)
    example_basic_usage()
    
    # Example 2: With optimization
    print("\n" + "-"*60)
    print("2. Optimization Example")
    print("-"*60)
    example_with_optimization()
    
    # Example 3: Visual AI
    print("\n" + "-"*60)
    print("3. Visual AI Example")
    print("-"*60)
    example_visual_ai()
    
    # Example 4: Environment config
    print("\n" + "-"*60)
    print("4. Environment Config Example")
    print("-"*60)
    example_with_env_config()
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60)
