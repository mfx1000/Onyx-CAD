"""
Keyword research module — informational and educational keywords for CAD/manufacturing.

These keywords target people actively searching for solutions to real problems.
Each keyword represents a genuine need/question the reader has.
"""
import random
from typing import Generator


# INFORMATIVE KEYWORDS - Topics where helpful content educates the reader
# These represent real questions engineers have that deserve thorough answers

CONVERSION_KEYWORDS = [
    # How to share/communicate with manufacturers
    "how to share STEP file with manufacturer without CAD license",
    "how to send CAD files to factory without SolidWorks",
    "how to communicate tolerances to supplier",
    "share STEP with contract manufacturer",
    "CAD handoff to factory",
    "share CAD file with supplier without email",
    "how to markup STEP file for machining",
    "how to annotate 3D model for CNC",
    "send CAD to supplier without CAD software",
    "collaborate with manufacturer without CAD license",
    
    # Browser-based viewing
    "browser based CAD viewer free no installation",
    "view STEP file in browser without software",
    "free CAD viewer no install online",
    "cloud CAD viewer annotation",
    "browser CAD viewer for iPad",
    "view 3D CAD files in browser",
    "no software CAD viewer online",
    "web based CAD viewer free",
    
    # Free tools
    "best free CAD viewer browser",
    "STEP file viewer online free",
    "free 3D CAD viewer no download",
    "free STEP viewer no signup",
    "no CAD license viewer free",
    "view STEP file without SolidWorks free",
    
    # Annotation / markup
    "how to annotate STEP file in browser",
    "annotate STEP file for manufacturing",
    "markup CAD file for manufacturer",
    "how to add tolerance to STEP file",
    "annotate CAD file online",
    "add notes to 3D model",
    "markup CAD file for production",
    "tolerance specification on CAD",
    
    # File sharing / collaboration
    "how to share 3D model with customer no CAD",
    "share 3D model manufacturer online",
    "STEP file collaboration online",
    "CAD file sharing without license",
    "share CAD file with client no software",
    "collaborate on CAD without software",
    
    # Specific problems
    "how to specify tolerance without 2D drawing",
    "communicate GD&T without CAD",
    "send parts to manufacturer without drawings",
    "supplier needs CAD file help",
    "factory can't open my CAD file",
    "no CAD license for supplier",
    
    # Industry-specific
    "CNC machining CAD annotation",
    "sheet metal fabrication CAD markup",
    "injection molding CAD annotations",
    "prototype manufacturing CAD",
    "hardware startup CAD workflow",
    "contract manufacturer CAD handoff",
    
    # Educational topics (not product-specific)
    "understanding STEP files and their limitations",
    "what is GD&T and why it matters",
    "how tolerances affect manufacturing cost",
    "why 2D drawings cause manufacturing errors",
    "communicating design intent to manufacturers",
    "common CAD to manufacturing mistakes",
    "best practices for CAD handoff",
]


# Additional educational keywords for variety
USER_INTENT_KEYWORDS = [
    "how do i share a STEP file with my manufacturer",
    "view STEP file without SolidWorks",
    "best free CAD viewer no installation",
    "annotate STEP file online",
    "send CAD file to supplier",
    "share 3D model without CAD software",
    "browser based CAD viewer",
    "free online CAD viewer",
    "how to add tolerance to 3D model",
    "annotate CAD file for manufacturing",
    "STEP file viewer no download",
    "view CAD files in browser",
    "share CAD with contract manufacturer",
    "no CAD license needed viewer",
    "free STEP viewer browser",
    "what is a STEP file used for",
    "how do i annotate a 3D model",
    "sending CAD files to manufacturers",
]


def get_all_keywords() -> list[str]:
    """Get all keywords combined."""
    all_kw = []
    all_kw.extend(CONVERSION_KEYWORDS)
    all_kw.extend(USER_INTENT_KEYWORDS)
    return list(set(all_kw))


def get_keyword_queue() -> Generator[tuple[str, str], None, None]:
    """Generator that yields keywords in shuffled order."""
    all_keywords = []
    
    for kw in CONVERSION_KEYWORDS:
        all_keywords.append((kw, "informational"))
    
    for kw in USER_INTENT_KEYWORDS:
        all_keywords.append((kw, "educational"))
    
    random.shuffle(all_keywords)
    
    for kw, category in all_keywords:
        yield kw, category


def get_next_keyword() -> tuple[str, str]:
    """Get the next keyword to target for content."""
    gen = get_keyword_queue()
    try:
        return next(gen)
    except StopIteration:
        random.shuffle(CONVERSION_KEYWORDS)
        random.shuffle(USER_INTENT_KEYWORDS)
        return get_next_keyword()