#!/usr/bin/env python3
"""
Main entry point for InstagramProfileCrawler.
"""

import sys

# Force UTF-8 encoding for standard output to avoid UnicodeEncodeError on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from src.cli import main

if __name__ == "__main__":
    main()
