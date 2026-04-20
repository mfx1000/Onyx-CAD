"""
Scheduler for automated content generation.
Can be run as a separate process or via Railway's scheduler.
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.seo_generator import generate_and_publish_post, bulk_generate_posts, get_content_stats
from core import content


DAILY_POST_COUNT = int(os.environ.get("DAILY_POST_COUNT", "2"))


async def run_daily_generation():
    """Generate and publish new content."""
    print(f"[{datetime.now()}] Starting daily content generation...")
    
    stats = get_content_stats()
    print(f"Current stats: {stats}")
    
    results = await bulk_generate_posts(count=DAILY_POST_COUNT)
    
    final_stats = get_content_stats()
    print(f"[{datetime.now()}] Generation complete. Final stats: {final_stats}")
    
    for r in results:
        if r.get("success"):
            print(f"  - Published: {r.get('title')}")
        else:
            print(f"  - Failed: {r.get('error')}")
    
    return results


async def generate_single_post():
    """Generate just one post."""
    result = await generate_and_publish_post()
    print(f"Result: {result}")
    return result


def main():
    """CLI entry point."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    
    if mode == "daily":
        asyncio.run(run_daily_generation())
    elif mode == "single":
        asyncio.run(generate_single_post())
    elif mode == "stats":
        stats = get_content_stats()
        print(json.dumps(stats, indent=2))
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python -m core.scheduler [daily|single|stats]")


if __name__ == "__main__":
    import json
    main()
