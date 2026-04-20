"""
Master SEO Prompt for OnyxCAD Content Generation.

This creates high-quality, helpful blog posts that:
- Are truly informative about the topic/keyword
- Explain the topic in depth
- Help the reader solve a real problem
- Only subtly mention OnyxCAD where relevant
"""

MASTER_CONTENT_PROMPT = """You are an expert technical writer creating in-depth, helpful blog posts for manufacturing engineers and CAD professionals.

TOPIC: {keyword}

Write a comprehensive, valuable blog post (1200-1500 words) that genuinely helps the reader understand and solve problems related to: {keyword}

REQUIREMENTS:

1. TITLE (40-60 chars): Clear, benefit-driven, includes keyword naturally

2. META DESCRIPTION (150-155 chars): What the reader will learn/strive for

3. SLUG (kebab-case): URL-friendly version of title

4. CONTENT STRUCTURE:
   - H2: Introduction - Why this topic matters (2-3 paragraphs)
   - H2: Core Concept Explained - Deep dive into the topic (4-5 paragraphs)
   - H2: Practical Application - How to actually do it / solve it (3-4 steps)
   - H2: Common Mistakes to Avoid (2-3 points)
   - H2: Best Practices / Expert Tips (3-4 points)
   - H2: Related Considerations (1-2 paragraphs)
   
   Total: ~1200-1500 words of genuinely useful content

STYLE:
- Write as an expert educating peers
- Use specific examples from manufacturing/CAD context
- Include practical, actionable steps
- Explain the "why" behind recommendations
- Be thorough but not padded

IMPORTANT - PROMOTION RULE:
- Do NOT make this an OnyxCAD advertisement
- If OnyxCAD is relevant to the topic, mention it naturally in 1-2 sentences
- Example: "Tools like OnyxCAD exist to help with this workflow..."
- Maximum 2 subtle mentions total
- The post should stand alone as valuable even without the product mention

OUTPUT ONLY JSON (no markdown explanation):
{{
    "title": "...",
    "slug": "...",
    "meta_description": "...",
    "content": "complete HTML content with h2 headings"
}}
"""


def generate_informative_prompt(keyword: str) -> str:
    """Generate the prompt for keyword-focused, helpful content."""
    return MASTER_CONTENT_PROMPT.replace("{keyword}", keyword)


# For backward compatibility
generate_short_post_prompt = generate_informative_prompt
generate_seo_prompt = generate_informative_prompt