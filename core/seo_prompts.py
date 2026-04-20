"""
Master SEO Prompt System for OnyxCAD Content Generation.

This module creates optimized prompts that guide the LLM to produce 
high-quality, SEO-optimized blog posts for CAD/manufacturing keywords.
"""

import json
from core.keyword_researcher import get_all_keywords, get_cluster_keywords, KEYWORD_CLUSTERS

# The primary keyword(s) to target
TARGET_KEYWORD = "{keyword}"

# Full keyword list for context
ALL_KEYWORDS = get_all_keywords()

# Cluster context for related topics
ANNOTATION_CLUSTER = KEYWORD_CLUSTERS.get("step_annotation", [])
TOLERANCE_CLUSTER = KEYWORD_CLUSTERS.get("tolerance_spec", [])
MANUFACTURING_CLUSTER = KEYWORD_CLUSTERS.get("manufacturer_handoff", [])
VIEWER_CLUSTER = KEYWORD_CLUSTERS.get("browser_viewer", [])

CONTEXT_ABOUT_ONYXCAD = """
ABOUT ONYXCAD:
- Browser-based STEP file annotation tool
- Annotate faces with tolerances, threads, colors, notes
- Share via link - no CAD license needed to view
- Metadata bakes into STEP file for downstream use
- Tolerance heat map visualization
- Free plan: 3 projects, no share links
- Pro ($29/mo): 10 projects + shareable links
- Growth ($79/mo): 50 projects + priority processing

KEY USE CASES:
- Manufacturing engineers sending parts to contract manufacturers
- Hardware startups iterating with suppliers
- Design engineers communicating with factories
- Anyone needing to specify tolerances without 2D drawings

UNIQUE VALUE PROPOSITION:
"Like PDFs for CAD" - turn STEP files into traveling sources of truth
by layering metadata onto face IDs.
"""

MASTER_SYSTEM_PROMPT = f"""You are an expert SEO content writer specializing in CAD, manufacturing, and engineering software. Your content ranks on Google because it's comprehensive, actionable, and genuinely helpful.

CONTEXT:
{CONTEXT_ABOUT_ONYXCAD}

YOUR TASK:
Write a high-quality, SEO-optimized blog post targeting the keyword: {TARGET_KEYWORD}

REQUIREMENTS:
1. TITLE: Compelling, includes keyword naturally, 40-60 chars
2. META DESCRIPTION: 150-160 chars, includes keyword + value proposition  
3. slug: URL-friendly, kebab-case, includes keyword
4. KEYWORDS: List of 5-8 related keywords including primary
5. CONTENT: 1500-2000 words, well-structured with h2/h3 headings

CONTENT STRUCTURE:
- Opening hook (problem statement)
- H2: "Understanding [keyword]" - context and why it matters
- H2: "How to [achieve goal]" - step-by-step guide
- H2: "Real-world example" - practical case study
- H2: "Best practices" - expert tips
- H2: "Why OnyxCAD helps" - natural product mention
- Closing CTA - encouraging action

SEO GUIDELINES:
- Include keyword in first 100 words
- Use keyword in at least one H2 heading
- Include keyword naturally 3-5 times throughout
- Add related keywords in subheadings naturally
- Link to relevant internal pages where contextually appropriate
- Use semantic HTML (h2, h3, p, ul, ol, li, blockquote)
- Include schema markup (article, FAQ, or HowTo)
- Add image alt text descriptions if mentioning images

QUALITY STANDARDS:
- Write in conversational but professional tone
- Include specific, actionable steps
- Add real-world examples engineering context
- Cite best practices from manufacturing
- Avoid fluff - every paragraph adds value
- End with clear call-to-action

OUTPUT FORMAT:
Return ONLY valid JSON (no markdown code blocks):
{{
    "title": "...",
    "slug": "...",
    "meta_description": "...",
    "keywords": ["primary", "related1", "related2", ...],
    "content": "complete HTML content with h2/h3 headings"
}}

Do NOT include any explanation or additional text. Just the JSON."""


def generate_seo_prompt(
    keyword: str,
    include_related: bool = True,
    custom_intro: str = None,
) -> str:
    """Generate the full SEO prompt for a keyword."""
    
    prompt = MASTER_SYSTEM_PROMPT.replace("{keyword}", keyword)
    
    if include_related:
        related_context = f"""
RELATED KEYWORDS TO NATURALLY INCORPORATE:
{json.dumps(ANNOTATION_CLUSTER[:5])}
{json.dumps(TOLERANCE_CLUSTER[:5])}
{json.dumps(MANUFACTURING_CLUSTER[:5])}
{json.dumps(VIEWER_CLUSTER[:5])}
"""
        prompt = prompt.replace(
            "RELATED KEYWORDS TO NATURALLY INCURPORATE:",
            related_context
        )
    
    if custom_intro:
        prompt = prompt.replace(
            "YOUR TASK:",
            f"{custom_intro}\n\nYOUR TASK:"
        )
    
    return prompt


def generate_comparison_prompt(keyword: str, vs: str) -> str:
    """Generate prompt for comparison content."""
    return f"""Write a comparison blog post: {keyword} vs {vs}

Compare the approaches, use cases, pros/cons.
Target: {keyword}

Context:
{TARGET_KEYWORD}

OnyxCAD is a browser-based annotation tool for STEP files.

Output as JSON:
{{
    "title": "...",
    "slug": "...",
    "meta_description": "...",
    "keywords": [...],
    "content": "full HTML content"
}}
"""


def generate_howto_prompt(keyword: str) -> str:
    """Generate prompt for how-to guide content."""
    return f"""Write a comprehensive how-to guide for: {keyword}

Target audience: Manufacturing engineers, hardware startups, design engineers

Context:
- Problem: Engineers struggle to communicate specifications to manufacturers
- Solution: Browser-based tools like OnyxCAD for annotation
- Keyword: {keyword}

Structure needed:
1. What is {keyword} (intro)
2. Why it matters
3. Step-by-step instructions
4. Best practices
5. Common mistakes to avoid
6. Tools and resources
7. CTA

Output as JSON with HTML content."""


def generate_case_study_prompt(industry: str = "CNC machining") -> str:
    """Generate prompt for industry case study."""
    return f"""Write a case study about using CAD annotation for {industry} manufacturing.

Include:
- Industry challenges
- How annotation solves them
- Specific tolerances and specs
- Results/better outcomes

OnyxCAD context needed.
Output as JSON."""


def get_seo_guidelines() -> dict:
    """Get SEO guidelines for content quality."""
    return {
        "min_word_count": 1500,
        "max_word_count": 2000,
        "keyword_density": {
            "primary": "3-5 times",
            "related": "2-3 times each",
        },
        "structure": {
            "required_headings": ["H2", "H3"],
            "min_paragraphs": 8,
            "max_paragraphs": 15,
        },
        "meta": {
            "title_length": {"min": 40, "max": 60},
            "description_length": {"min": 150, "max": 160},
        },
        "technical": {
            "schema_types": ["Article", "FAQPage", "HowTo"],
            "opengraph": True,
            "canonical": True,
            "og_image": True,
        },
    }