"""
SEO Content Generator — uses LLM via OpenRouter for high-quality blog posts.
Targets conversion-focused keywords for CAD/manufacturing niche.
"""
import json
import time
import random
from core import content
from core.llm_client import generate_with_minimax
from core.keyword_researcher import get_next_keyword, get_all_keywords
from core.seo_prompts import generate_short_post_prompt


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


async def generate_content_for_keyword(keyword: str) -> dict:
    """Generate SEO content for a target keyword using LLM."""
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
        
        print(f"Generated: {data.get('title')}")
        return data
        
    except json.JSONDecodeError as e:
        print(f"JSON parse error for '{keyword}': {e}")
        return None
    except Exception as e:
        print(f"Error generating content for '{keyword}': {e}")
        return None


async def generate_and_publish_post(keyword: str = None) -> dict:
    """Generate content and publish to blog."""
    if not keyword:
        keyword, _ = get_next_keyword()
    
    print(f"Processing keyword: {keyword}")
    
    data = await generate_content_for_keyword(keyword)
    
    if not data:
        return {"success": False, "error": "Failed to generate content"}
    
    slug = data.get("slug", generate_slug(data.get("title", keyword)))
    
    existing = content.get_post_by_slug(slug)
    if existing:
        print(f"Post with slug '{slug}' already exists, trying new keyword...")
        keyword2, _ = get_next_keyword()
        return await generate_and_publish_post(keyword2)
    
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
        result = await generate_and_publish_post()
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
        "keywords_available": len(get_all_keywords()),
    }