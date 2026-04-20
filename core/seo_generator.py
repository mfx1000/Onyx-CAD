"""
SEO Content Generator — uses LLM via OpenRouter for high-quality blog posts.
Targets conversion-focused keywords for CAD/manufacturing niche.
"""
import json
import time
import re
from datetime import datetime
from core import content
from core.llm_client import call_llm, generate_with_minimax
from core.seo_prompts import generate_seo_prompt
from core.keyword_researcher import (
    get_next_keyword,
    get_all_keywords,
)


CONVERSION_KEYWORDS = [
    "how to share STEP file with manufacturer without CAD license",
    "how to annotate STEP file in browser",
    "how to send CAD files to factory without SolidWorks",
    "browser based CAD viewer free no installation",
    "how to communicate tolerances to supplier",
    "STEP file viewer with annotations online",
    "how to add tolerance to STEP file",
    "CAD file sharing without license",
    "how to share 3D model with customer no CAD",
    "annotate STEP file for manufacturing",
    "free STEP file viewer browser",
    "how to markup CAD file for manufacturer",
    "share CAD file with supplier without email",
    "browser CAD viewer for iPad",
    "how to specify tolerance without 2D drawing",
    "STEP file collaboration online",
    "no CAD license viewer",
    "3D model annotation browser",
    "manufacturer CAD viewer free",
    "how to annotate 3D model for CNC",
    "share STEP with contract manufacturer",
    "CAD handoff to factory",
    "how to markup STEP file for machining",
    "free CAD viewer no install",
    "cloud CAD viewer annotation",
]

USER_INTENT_KEYWORDS = [
    "best free CAD viewer browser",
    "STEP file viewer online free",
    "how to view STEP file without SolidWorks",
    "free 3D CAD viewer no download",
    "annotate CAD file online",
    "share 3D model manufacturer",
    "tolerance specification CAD",
    "GD&T on STEP file",
    "add notes to 3D model",
    "markup CAD file for production",
]


def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title."""
    slug = title.lower()
    replacements = {
        " ": "-",
        "?": "",
        "!": "",
        ".": "",
        ",": "",
        "'": "",
        '"': "",
        "--": "-",
    }
    for old, new in replacements.items():
        slug = slug.replace(old, new)
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    slug = "-".join(filter(None, slug.split("-")))
    return slug[:80]


async def generate_content_for_keyword(keyword: str, category: str = "user_intent") -> dict:
    """
    Generate SEO content for a target keyword using LLM.
    Returns shorter, focused posts (800-1200 words).
    """
    from core.seo_prompts import generate_short_post_prompt
    
    print(f"Generating content for: {keyword}")
    
    prompt = generate_short_post_prompt(keyword)
    
    response = generate_with_minimax(prompt)
    
    if not response:
        print(f"LLM generation failed for '{keyword}'")
        return None
    
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        
        if json_start == -1 or json_end == 0:
            print(f"No JSON found for '{keyword}'")
            return None
        
        json_str = response[json_start:json_end]
        data = json.loads(json_str)
        
        if not data.get("title"):
            print(f"No title in response for '{keyword}'")
            return None
        
        if not data.get("slug"):
            data["slug"] = generate_slug(data.get("title", keyword))
        
        data["_keyword"] = keyword
        data["_category"] = category
        
        print(f"Generated: {data.get('title')}")
        return data
        
    except json.JSONDecodeError as e:
        print(f"JSON parse error for '{keyword}': {e}")
        return None
    except Exception as e:
        print(f"Error generating content for '{keyword}': {e}")
        return None


async def generate_and_publish_post(keyword: str = None, category: str = None) -> dict:
    """Generate content and publish to blog."""
    if not keyword or not category:
        keyword, category = get_next_keyword()
    
    print(f"Processing keyword: {keyword}")
    
    data = await generate_content_for_keyword(keyword, category)
    
    if not data:
        return {"success": False, "error": "Failed to generate content"}
    
    slug = data.get("slug", generate_slug(data.get("title", keyword)))
    
    existing = content.get_post_by_slug(slug)
    if existing:
        print(f"Post with slug '{slug}' already exists, trying new keyword...")
        keyword2, cat2 = get_next_keyword()
        return await generate_and_publish_post(keyword2, cat2)
    
    post_id = content.create_post(
        title=data.get("title", ""),
        slug=slug,
        content=data.get("content", ""),
        meta_description=data.get("meta_description", "")[:160],
        status="draft",
    )
    
    content.publish_post(post_id)
    
    print(f"Published: {data.get('title')}")
    
    return {
        "success": True,
        "post_id": post_id,
        "title": data.get("title"),
        "slug": slug,
        "keyword": keyword,
    }


async def bulk_generate_posts(count: int = 5) -> list[dict]:
    """Generate multiple posts in batch."""
    results = []
    
    for i in range(count):
        keyword, category = get_next_keyword()
        result = await generate_and_publish_post(keyword, category)
        results.append(result)
        
        if i < count - 1:
            time.sleep(2)
    
    return results


def get_content_stats() -> dict:
    """Get statistics about generated content."""
    from core import content
    
    all_posts = content.list_posts(limit=1000, status=None)
    published = [p for p in all_posts if p.get("status") == "published"]
    drafts = [p for p in all_posts if p.get("status") == "draft"]
    
    return {
        "total_posts": len(all_posts),
        "published": len(published),
        "drafts": len(drafts),
    }