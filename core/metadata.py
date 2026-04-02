
import base64
import json
import re

# ── Metadata markers ─────────────────────────────────────────────────────────
_SVFM_TAG       = "SVFM"                    # tag inside DESCRIPTIVE_REPRESENTATION_ITEM
_SVFM_PROP_NAME = "StepViewerFaceMetadata"  # PROPERTY_DEFINITION name
_SVFM_DESC_PFX  = "[SVFM:"                  # prefix in PRODUCT description
_SVFM_DESC_SFX  = "]"

# Comment fallback
_META_START = "/* __STEPVIEWER_META_START__ "
_META_END   = " __STEPVIEWER_META_END__ */"
_META_COMMENT_RE = re.compile(
    r"/\* __STEPVIEWER_META_START__ (.*?) __STEPVIEWER_META_END__ \*/",
    re.DOTALL,
)

# Entity extraction regex — matches either tag name (across line breaks)
_SVFM_ENTITY_RE = re.compile(
    r"DESCRIPTIVE_REPRESENTATION_ITEM\s*\(\s*'(?:" + _SVFM_TAG + r"|" + _SVFM_PROP_NAME + r")'\s*,\s*'([^']*)'\s*\)",
    re.DOTALL,
)

# PRODUCT description extraction regex
_SVFM_DESC_RE = re.compile(r"\[SVFM:([A-Za-z0-9+/=]+)\]")


def _decode_b64_meta(b64_str: str) -> dict:
    """Decode a base64 metadata payload, return {} on failure."""
    try:
        return json.loads(base64.b64decode(b64_str).decode("utf-8"))
    except Exception:
        return {}


def extract_meta_from_step(filepath: str) -> dict:
    """
    Extract embedded face metadata from a STEP file.

    Three strategies tried in priority order — the first one that yields
    data wins.  This gives us resilience across different CAD tools:

      1. DESCRIPTIVE_REPRESENTATION_ITEM('SVFM', '<b64>')
         Real STEP entity — survives tools that preserve product properties.

      2. PRODUCT description field  [SVFM:<b64>]
         The description is the most universally preserved text in STEP.
         SolidWorks maps it to "Description" custom property, Fusion 360
         keeps it as the component description.  Survives almost everything.

      3. Comment block  /* __STEPVIEWER_META_START__ ... */
         Fastest for our-tool-to-our-tool, but stripped by any re-export.
    """
    try:
        with open(filepath, "r", errors="replace") as f:
            text = f.read()

        # Strategy 1: STEP entity
        m = _SVFM_ENTITY_RE.search(text)
        if m:
            result = _decode_b64_meta(m.group(1))
            if result:
                return result

        # Strategy 2: PRODUCT description field
        m = _SVFM_DESC_RE.search(text)
        if m:
            result = _decode_b64_meta(m.group(1))
            if result:
                return result

        # Strategy 3: Comment block
        m = _META_COMMENT_RE.search(text)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

    except Exception:
        pass
    return {}


def inject_meta_into_step(step_bytes: bytes, meta: dict) -> bytes:
    """
    Inject face metadata into a STEP file using THREE strategies:

    1. PROPERTY_DEFINITION on PRODUCT_DEFINITION (not PRODUCT_DEFINITION_SHAPE!)
       This is how SolidWorks writes custom properties to STEP. When SW imports
       a file with PROPERTY_DEFINITION → PRODUCT_DEFINITION, it maps it to a
       custom property and re-exports it.  The entity chain:

         PROPERTY_DEFINITION('StepViewerFaceMetadata','',#PD)
         PROPERTY_DEFINITION_REPRESENTATION(→ REPRESENTATION)
         REPRESENTATION(→ DESCRIPTIVE_REPRESENTATION_ITEM)
         DESCRIPTIVE_REPRESENTATION_ITEM('SVFM','<base64>')

    2. PRODUCT description field — append [SVFM:<base64>] to the existing
       description.  This is the single most reliably preserved text field
       across ALL CAD tools (SolidWorks, Fusion 360, CATIA, NX, Creo).

    3. Comment block — fast fallback for our own tool.
    """
    if not meta:
        return step_bytes

    text = step_bytes.decode("utf-8", errors="replace")

    # Clean any existing meta (comment block, old description tag)
    text = _META_COMMENT_RE.sub("", text)

    # ── Encode payload ───────────────────────────────────────────────────
    payload_json = json.dumps(meta, separators=(",", ":"))
    payload_b64  = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")

    # ── Find STEP anchors ────────────────────────────────────────────────
    entity_ids = [int(x) for x in re.findall(r"#(\d+)\s*=", text)]
    max_id = max(entity_ids) if entity_ids else 0

    # PRODUCT_DEFINITION — the product-level entity that SolidWorks maps
    # to its internal product structure.  NOT PRODUCT_DEFINITION_SHAPE.
    # The regex uses \( to ensure we match exactly PRODUCT_DEFINITION and
    # not PRODUCT_DEFINITION_SHAPE or PRODUCT_DEFINITION_FORMATION.
    pd_match = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION\s*\(", text)

    # REPRESENTATION_CONTEXT
    ctx_match = re.search(
        r"#(\d+)\s*=\s*\(\s*GEOMETRIC_REPRESENTATION_CONTEXT", text
    )
    if not ctx_match:
        ctx_match = re.search(r"#(\d+)\s*=\s*REPRESENTATION_CONTEXT", text)

    # ── Strategy 1: PROPERTY_DEFINITION entities ─────────────────────────
    # Only use if payload is small enough effectively (prevent buffer overflow in readers)
    # 4KB limit is conservative safe zone for typical flex buffers (8KB-16KB)
    if len(payload_b64) < 4096:
        new_entities = ""
        if pd_match and ctx_match:
            pd_id  = pd_match.group(1)
            ctx_id = ctx_match.group(1)
            n = max_id + 1

            # Mirror the exact pattern SolidWorks uses for custom properties:
            new_entities = (
                f"#{n} = PROPERTY_DEFINITION('{_SVFM_PROP_NAME}','',#{pd_id});\n"
                f"#{n+1} = PROPERTY_DEFINITION_REPRESENTATION(#{n},#{n+2});\n"
                f"#{n+2} = REPRESENTATION('',(#{n+3}),#{ctx_id});\n"
                f"#{n+3} = DESCRIPTIVE_REPRESENTATION_ITEM('{_SVFM_PROP_NAME}',\n"
                f"  '{payload_b64}');\n"
            )

        # ── Strategy 2: Encode into PRODUCT description ──────────────────────
        # Also limit size here
        svfm_tag = f"{_SVFM_DESC_PFX}{payload_b64}{_SVFM_DESC_SFX}"

        # Remove any existing SVFM tag from product descriptions
        text = re.sub(r"\[SVFM:[A-Za-z0-9+/=]+\]", "", text)

        # Find PRODUCT entity — match the entity and its parameters
        product_re = re.compile(
            r"(#\d+\s*=\s*PRODUCT\s*\(\s*'[^']*'\s*,\s*')([^']*)('\s*,)",
            re.DOTALL,
        )
        m = product_re.search(text)
        if m:
            old_desc = m.group(2).strip()
            # Append our tag to existing description (preserve what's there)
            if old_desc:
                new_desc = f"{old_desc} {svfm_tag}"
            else:
                new_desc = svfm_tag
            text = text[:m.start(2)] + new_desc + text[m.end(2):]
    else:
        # Just clean up existing tags if we can't write new ones
        text = re.sub(r"\[SVFM:[A-Za-z0-9+/=]+\]", "", text)
        new_entities = ""

    # ── Strategy 3: Comment block ────────────────────────────────────────
    # Use indent=1 to break lines! This prevents "input buffer overflow" in flex scanners.
    # The regex in extract_meta matches DOTALL, so multiline JSON is fine.
    payload_multiline = json.dumps(meta, indent=1)
    comment = f"{_META_START}\n{payload_multiline}\n{_META_END}\n"

    # ── Inject entities + comment before ENDSEC; ─────────────────────────
    endsec_idx = text.rfind("ENDSEC;")
    if endsec_idx >= 0:
        text = text[:endsec_idx] + new_entities + comment + text[endsec_idx:]
    else:
        text += new_entities + comment

    return text.encode("utf-8")
