#!/usr/bin/env python3
"""
OnyxCAD SEO Content Generator CLI

Usage:
    python generate_content.py single   # Generate and publish one post
    python generate_content.py daily   # Generate and publish DAILY_POST_COUNT posts (default: 2)
    python generate_content.py stats    # Show content statistics
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.seo_generator import (
    generate_and_publish_post,
    bulk_generate_posts,
    get_content_stats,
)
from core import content


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if mode == "single":
        print("Generating a single post...")
        result = await generate_and_publish_post()
        if result.get("success"):
            print(f"✓ Published: {result.get('title')}")
            print(f"  URL: https://onyxcad.com/blog/{result.get('slug')}")
        else:
            print(f"✗ Failed: {result.get('error')}")
            
    elif mode == "daily":
        print(f"[{datetime.now()}] Starting daily content generation...")
        count = int(os.environ.get("DAILY_POST_COUNT", "2"))
        results = await bulk_generate_posts(count=count)
        
        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n✓ Published {success_count}/{len(results)} posts")
        
        for r in results:
            if r.get("success"):
                print(f"  - {r.get('title')}")
            else:
                print(f"  ✗ {r.get('error')}")
                
    elif mode == "stats":
        stats = get_content_stats()
        print("Content Statistics:")
        print(f"  Total posts: {stats['total_posts']}")
        print(f"  Published:   {stats['published']}")
        print(f"  Drafts:      {stats['drafts']}")
        print(f"  Total views: {stats['total_views']}")
        
    elif mode == "list":
        posts = content.list_posts(limit=20, status="published")
        print(f"Published posts ({len(posts)}):")
        for p in posts:
            print(f"  - {p.get('title')}")
            print(f"    /blog/{p.get('slug')}")
            print(f"    Views: {p.get('views', 0)}")
            print()
            
    else:
        print(__doc__)
        print("\nExamples:")
        print("  python generate_content.py single   # Generate one post")
        print("  python generate_content.py daily    # Run daily batch")
        print("  python generate_content.py stats   # View statistics")
        print("  python generate_content.py list    # List published posts")


if __name__ == "__main__":
    asyncio.run(main())
