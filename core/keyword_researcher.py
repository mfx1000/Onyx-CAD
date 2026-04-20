"""
Keyword research module — uses free web search to find long-tail keywords.
No paid tools required.
"""
import json
import os
import random
from typing import Generator

TARGET_KEYWORDS = [
    "STEP file annotation",
    "annotate STEP file browser",
    "browser based CAD viewer",
    "STEP file tolerance annotation",
    "GD&T on STEP file",
    "share STEP file with manufacturer",
    "CAD file sharing without license",
    "STEP file metadata",
    "3D model annotation browser",
    "manufacturing handoff CAD",
    "CAD to factory communication",
    "no CAD license viewer",
    "STEP file collaboration",
    "cloud CAD viewer",
    "STEP file viewer with annotations",
]

EXPANDED_KEYWORDS = [
    "how to annotate STEP file in browser",
    "add tolerance to STEP file without CAD software",
    "share STEP file with supplier without SolidWorks",
    "browser based 3D CAD viewer free",
    "STEP file viewer no installation",
    "annotate 3D model for manufacturing",
    "add GD&T to STEP file online",
    "manufacturing annotation tool CAD",
    "send CAD files to factory without CAD license",
    "cloud based CAD viewer with annotation",
    "free STEP file viewer with tolerance",
    "3D PDF alternative for CAD",
    "STEP file markup online",
    "CAD collaboration without software",
    "engineering annotation tool browser",
    "view STEP file on iPad tablet",
    "share 3D model with customer no CAD",
    "add notes to 3D model for manufacturing",
    "annotate STEP file for supplier",
    "visual tolerance map CAD",
    "color code faces STEP file",
    "thread specification on 3D model",
    "markup CAD file for manufacture",
    "inspect STEP file online free",
    "no CAD viewer for suppliers",
]

INDUSTRY_SPECIFIC = [
    "cnc machining tolerance annotation",
    "sheet metal fabrication CAD markup",
    "3D printing model annotation",
    "injection molding CAD annotations",
    "aerospace GD&T STEP file",
    "automotive CAD markup for supplier",
    "medical device CAD annotation",
    "electronics enclosure CAD handoff",
    "robotics CAD file collaboration",
    "consumer product manufacturing CAD",
    "architecture manufacturing CAD",
    "marine CAD parts annotation",
]


def get_keyword_queue() -> Generator[str, None, None]:
    """
    Generator that yields keywords in priority order.
    Mix of core, expanded, and industry-specific keywords.
    """
    all_keywords = []
    
    for kw in EXPANDED_KEYWORDS:
        all_keywords.append((kw, "expanded"))
    
    for kw in INDUSTRY_SPECIFIC:
        all_keywords.append((kw, "industry"))
    
    for kw in TARGET_KEYWORDS:
        all_keywords.append((kw, "core"))
    
    random.shuffle(all_keywords)
    
    for kw, category in all_keywords:
        yield kw, category


def get_next_keyword() -> tuple[str, str]:
    """Get the next keyword to target for content."""
    gen = get_keyword_queue()
    return next(gen)


KEYWORD_CLUSTERS = {
    "step_annotation": [
        "how to annotate STEP file in browser",
        "annotate STEP file online free",
        "STEP file markup tool",
        "add notes to STEP file",
        "color faces in STEP viewer",
    ],
    "tolerance_spec": [
        "add tolerance to STEP file",
        "GD&T on STEP file browser",
        "tolerance annotation CAD online",
        "specify tolerance without CAD",
        "tolerance heat map 3D model",
    ],
    "manufacturer_handoff": [
        "share STEP file with manufacturer",
        "send CAD to factory without license",
        "CAD handoff to supplier",
        "collaborate on CAD without software",
        "manufacturing communication 3D model",
    ],
    "browser_viewer": [
        "browser based CAD viewer",
        "view STEP file online no install",
        "free STEP viewer browser",
        "no CAD software viewer",
        "cloud CAD viewer free",
    ],
    "thread_spec": [
        "annotate threads on 3D model",
        "specify thread in browser CAD",
        "add thread callout to STEP",
        "thread specification CAD markup",
    ],
}


def get_cluster_keywords(cluster_name: str) -> list[str]:
    """Get all keywords in a specific cluster."""
    return KEYWORD_CLUSTERS.get(cluster_name, [])


def get_all_keywords() -> list[str]:
    """Get all keywords combined."""
    all_kw = []
    all_kw.extend(TARGET_KEYWORDS)
    all_kw.extend(EXPANDED_KEYWORDS)
    all_kw.extend(INDUSTRY_SPECIFIC)
    return list(set(all_kw))
