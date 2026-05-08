"""
CLI module - Command-line interface for the application.
"""

import argparse
import sys
import os
from typing import List, Optional
from pathlib import Path

from .instagram.auth import SessionManager
from .instagram.scraper import InstagramScraper
from .images.downloader import ImageDownloader
from .images.optimizer import ImageOptimizer
from .images.deduplicator import ImageDeduplicator
from .filtering.visual_ai import VisualAI, CaptionGenerator
from .config.env import EnvConfig
from .utils.logger import Logger
from .utils.stats import StatisticsTracker


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="InstagramProfileCrawler - Create datasets from Instagram profiles",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Positional arguments
    parser.add_argument(
        "username",
        nargs="?",
        help="Instagram username to scrape"
    )
    
    # Profile options
    parser.add_argument(
        "--max-posts",
        type=int,
        default=100,
        help="Maximum number of posts to scrape"
    )
    
    # Output options
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="./dataset",
        help="Output directory for downloaded images"
    )
    
    # Processing options
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Optimize images for LoRA training"
    )
    
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Remove duplicate images"
    )
    
    # Visual AI options
    parser.add_argument(
        "--generate-captions",
        action="store_true",
        help="Generate captions using Visual AI"
    )
    
    parser.add_argument(
        "--caption-format",
        type=str,
        choices=["text", "json", "pairs"],
        default="json",
        help="Format for caption output"
    )
    
    # Filtering options
    parser.add_argument(
        "--filter",
        action="store_true",
        help="Filter images using Visual AI"
    )
    
    # Batch options
    parser.add_argument(
        "--batch",
        type=str,
        help="Batch file with list of usernames (one per line)"
    )
    
    # Verbose options
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output"
    )
    
    return parser


def process_profile(username: str,
                   max_posts: int,
                   output_dir: str,
                   optimize: bool,
                   deduplicate: bool,
                   generate_captions: bool,
                   caption_format: str,
                   filter_images: bool) -> dict:
    """
    Process a single Instagram profile.
    
    Args:
        username: Instagram username
        max_posts: Maximum posts to scrape
        output_dir: Output directory
        optimize: Whether to optimize images
        deduplicate: Whether to remove duplicates
        generate_captions: Whether to generate captions
        caption_format: Format for captions
        filter_images: Whether to filter images
        
    Returns:
        Dictionary with processing results
    """
    logger = Logger("InstagramProfileCrawler")
    stats = StatisticsTracker()
    
    logger.print_header(f"Scraping Profile", f"@{username}")
    
    config = EnvConfig()
    
    # Initialize components
    session_manager = SessionManager()
    scraper = InstagramScraper(session_manager)
    downloader = ImageDownloader(output_dir)
    optimizer = ImageOptimizer() if optimize else None
    deduplicator = ImageDeduplicator() if deduplicate else None
    
    use_ollama = config.visual_ai_type == 'ollama'
    visual_ai = VisualAI(
        host=config.visual_ai_ollama_host if use_ollama else config.visual_ai_llama_host,
        model=config.visual_ai_ollama_model if use_ollama else config.visual_ai_llama_model,
        use_ollama=use_ollama
    ) if filter_images or generate_captions else None
    
    try:
        # Step 1: Scrape profile
        profile_data = scraper.scrape_profile(username, max_posts)
        if not profile_data:
            return {"success": False, "error": "Failed to scrape profile"}
        
        stats.record_profile()
        # Collect all media items
        media_items = []
        for post in profile_data['posts']:
            media_items.append({
                'id': post['id'],
                'type': 'post',
                'caption': post['caption']
            })
        
        for story in profile_data['stories']:
            for item in story:
                media_items.append({
                    'id': item.get("id"),
                    'type': 'story',
                    'caption': item.get("caption")
                })
        
        stats.record_image(len(profile_data['image_urls']))
        
        if not media_items:
            return {"success": False, "error": "No media items found"}
        
        # Step 2: Download images
        logger.info(f"Downloading {len(profile_data['image_urls'])} images...")
        
        for result in downloader.download_images_batch(profile_data['image_urls']):
            if result.success:
                stats.record_download(True, result.size_bytes, result.duration_ms)
            else:
                stats.record_download(False, 0, 0)
        
        # Step 3: Deduplicate
        if deduplicate:
            logger.info("Deduplicating images...")
            duplicates = deduplicator.find_duplicates(output_dir)
            stats.record_processing(len(duplicates), is_duplicate=True)
        
        # Step 4: Optimize images
        if optimize:
            logger.info("Optimizing images...")
            image_files = list(Path(output_dir).glob("*.jpg")) + list(Path(output_dir).glob("*.jpeg"))
            if image_files:
                results = optimizer.optimize_batch([str(f) for f in image_files], output_dir)
                for result in results:
                    if result.success:
                        stats.record_processing(True, optimized=True)
                    else:
                        stats.record_processing(False)
        
        # Step 5: Filter images
        if filter_images and visual_ai:
            logger.info("Filtering images...")
            config = EnvConfig()
            image_files = list(Path(output_dir).glob("*.jpg")) + list(Path(output_dir).glob("*.jpeg"))
            
            for image_path in image_files:
                result = visual_ai.filter_image(str(image_path), config.filtering_prompt)
                if result.success and result.filtered:
                    stats.record_processing(True, filtered=True)
                    try:
                        os.remove(image_path)
                    except Exception as e:
                        logger.error(f"Error deleting file {image_path}: {e}")
                    logger.info(f"  Filtered: {Path(image_path).name}")
        
        # Step 6: Generate captions
        if generate_captions and visual_ai:
            logger.info("Generating captions...")
            image_files = list(Path(output_dir).glob("*.jpg")) + list(Path(output_dir).glob("*.jpeg"))
            
            if caption_format == "pairs":
                caption_generator = CaptionGenerator(visual_ai, batch_size=1)
                caption_results = caption_generator.generate_all([str(f) for f in image_files], output_dir)
                for _ in caption_results:
                    stats.record_caption(True)
            else:
                # Simple caption generation
                for image_path in image_files:
                    result = visual_ai.generate_caption(str(image_path))
                    if result.success:
                        stats.record_caption(True)
                    else:
                        stats.record_caption(False)
        
        # Finalize stats
        stats.finalize()
        
        # Return results
        return {
            "success": True,
            "username": username,
            "posts": len(profile_data['posts']),
            "stories": len(profile_data['stories']),
            "images": len(profile_data['image_urls']),
            "stats": stats.get_summary()
        }
        
    except Exception as e:
        logger.error(f"Failed to process profile: {e}")
        return {"success": False, "error": str(e)}



def process_batch(batch_file: str) -> dict:
    """
    Process a batch of usernames.
    
    Args:
        batch_file: Path to file with usernames
        
    Returns:
        Dictionary with batch results
    """
    logger = Logger("InstagramProfileCrawler")
    
    logger.print_header("Batch Processing")
    
    try:
        # Read usernames
        with open(batch_file, 'r') as f:
            usernames = [line.strip() for line in f if line.strip()]
        
        logger.info(f"Processing {len(usernames)} usernames...")
        
        results = []
        for i, username in enumerate(usernames, 1):
            logger.print_progress(i, len(usernames), f"Processing @{username}")
            
            result = process_profile(
                username=username,
                max_posts=100,
                output_dir="./dataset",
                optimize=True,
                deduplicate=True,
                generate_captions=True,
                caption_format="json",
                filter_images=False
            )
            
            results.append(result)
        
        # Print summary
        successful = sum(1 for r in results if r.get("success"))
        logger.print_table(
            [{"Status": r.get("success"), "Username": r.get("username"), "Images": r.get("images")} 
             for r in results],
            "Batch Results"
        )
        
        return {
            "total": len(usernames),
            "successful": successful,
            "failed": len(usernames) - successful,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        return {"success": False, "error": str(e)}


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle batch processing
    if args.batch:
        result = process_batch(args.batch)
        print(result)
        return
    
    # Handle single profile
    if not args.username:
        parser.print_help()
        return
    
    result = process_profile(
        username=args.username,
        max_posts=args.max_posts,
        output_dir=args.output,
        optimize=args.optimize,
        deduplicate=args.deduplicate,
        generate_captions=args.generate_captions,
        caption_format=args.caption_format,
        filter_images=args.filter
    )
    
    if result.get("success"):
        print(f"\n✓ Successfully processed @{result['username']}")
        print(f"  Posts: {result['posts']}")
        print(f"  Stories: {result['stories']}")
        print(f"  Images: {result['images']}")
        print(result["stats"])
    else:
        print(f"\n✗ Failed to process @{args.username}")
        print(f"  Error: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
