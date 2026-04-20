"""
SEO Content Generator — uses LLM via OpenRouter for high-quality blog posts.
Targets long-tail keywords for CAD/manufacturing niche.
"""
import os
import json
import time
import re
import random
from datetime import datetime
from core import content
from core.llm_client import call_llm, generate_with_minimax
from core.seo_prompts import generate_seo_prompt, get_seo_guidelines
from core.keyword_researcher import (
    get_next_keyword,
    get_all_keywords,
)


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


async def generate_content_for_keyword(keyword: str, category: str = "expanded") -> dict:
    """
    Generate SEO content for a target keyword using LLM.
    Returns dict with title, slug, content, meta_description, keywords.
    """
    print(f"Generating LLM content for: {keyword}")
    
    prompt = generate_seo_prompt(keyword)
    
    response = generate_with_minimax(prompt)
    
    if not response:
        print(f"LLM generation failed for '{keyword}', falling back to template")
        return None
    
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        
        if json_start == -1 or json_end == 0:
            print(f"No JSON found in LLM response for '{keyword}'")
            return None
        
        json_str = response[json_start:json_end]
        data = json.loads(json_str)
        
        if not data.get("title"):
            print(f"No title in LLM response for '{keyword}'")
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
    
    print(f"Processing keyword: {keyword} (category: {category})")
    
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
        keywords=data.get("keywords", [keyword]),
        status="draft",
    )
    
    content.publish_post(post_id)
    
    print(f"Published: {data.get('title')} (ID: {post_id})")
    
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
        "total_views": sum(p.get("views", 0) for p in published),
    }