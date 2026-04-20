"""
SEO Prompts for OnyxCAD Content Generation.
Focused on conversion and user intent.
"""

MASTER_SHORT_PROMPT = """You are a technical writer for OnyxCAD, a browser-based tool that lets engineers annotate STEP files with tolerances, threads, colors, and notes—then share via link. No CAD license required.

Write a SHORT, focused blog post (800-1000 words MAX) targeting: {keyword}

REQUIREMENTS:
- Title: Catchy, 40-55 chars, includes keyword
- Meta: 140-155 chars, value-focused
- slug: URL-friendly (kebab-case)
- Content: 800-1000 words, 4-5 sections max

STRUCTURE:
- H2: Problem or question (1 paragraph)
- H2: Solution (step-by-step, 3-4 steps max)
- H2: Why this matters (1 paragraph)  
- CTA: Try OnyxCAD free

STYLE:
- Conversational, directly helpful
- No fluff or padding
- Specific steps, not abstractions
- End with clear CTA to try OnyxCAD

OUTPUT ONLY JSON:
{{
    "title": "...",
    "slug": "...",
    "meta_description": "...",
    "content": "..."
}}
"""


def generate_short_post_prompt(keyword: str) -> str:
    """Generate prompt for short, focused post."""
    return MASTER_SHORT_PROMPT.replace("{keyword}", keyword)


def generate_seo_prompt(keyword: str) -> str:
    """Legacy prompt - use generate_short_post_prompt instead."""
    return generate_short_post_prompt(keyword)