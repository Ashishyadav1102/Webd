"""
script_generator.py
Generates a structured YouTube video script and description using a free LLM.
"""

import os
import re
import logging
from pathlib import Path
from llm_client import get_llm_client

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Tone per niche — extend as needed
NICHE_TONES: dict[str, str] = {
    "motivation": "energetic, uplifting, and inspiring",
    "finance tips": "authoritative, clear, and practical",
    "tech facts": "curious, enthusiastic, and informative",
    "history": "storytelling, dramatic, and educational",
    "health": "calm, trustworthy, and empowering",
}

DEFAULT_TONE = "engaging, informative, and conversational"


def _load_template(filename: str) -> str:
    path = TEMPLATES_DIR / filename
    return path.read_text(encoding="utf-8")


def _parse_script(raw: str) -> dict:
    """
    Parse the LLM's raw script text into a structured dictionary.
    Returns keys: title, tags, hook, segments (list of dicts), cta, visual_keywords
    """
    result = {
        "title": "",
        "tags": [],
        "hook": "",
        "segments": [],
        "cta": "",
        "visual_keywords": [],
        "raw": raw,
    }

    # Extract title
    title_match = re.search(r"##\s*TITLE\s*\n(.+)", raw)
    if title_match:
        result["title"] = title_match.group(1).strip()

    # Extract tags
    tags_match = re.search(r"##\s*TAGS\s*\n(.+)", raw)
    if tags_match:
        result["tags"] = [t.strip() for t in tags_match.group(1).split(",") if t.strip()]

    # Extract hook
    hook_match = re.search(r"##\s*HOOK[^\n]*\n([\s\S]+?)(?=##\s*SEGMENT)", raw)
    if hook_match:
        result["hook"] = hook_match.group(1).strip()

    # Extract segments
    segment_pattern = re.compile(
        r"##\s*SEGMENT\s*\d+\s*[—\-]+\s*(.+)\n([\s\S]+?)(?=##\s*SEGMENT|##\s*CALL|$)",
        re.IGNORECASE,
    )
    for m in segment_pattern.finditer(raw):
        seg_title = m.group(1).strip()
        seg_body = m.group(2).strip()
        # Extract VISUAL_KEYWORD line if present
        vis_match = re.search(r"VISUAL_KEYWORD:\s*(.+)", seg_body)
        visual_kw = vis_match.group(1).strip() if vis_match else ""
        # Remove VISUAL_KEYWORD line from narration
        narration = re.sub(r"VISUAL_KEYWORD:.+", "", seg_body).strip()
        result["segments"].append(
            {"title": seg_title, "narration": narration, "visual_keyword": visual_kw}
        )
        if visual_kw:
            result["visual_keywords"].append(visual_kw)

    # Extract CTA
    cta_match = re.search(r"##\s*CALL TO ACTION[^\n]*\n([\s\S]+?)$", raw)
    if cta_match:
        result["cta"] = cta_match.group(1).strip()

    return result


def generate_script(topic: str, niche: str, llm_config: dict) -> dict:
    """Generate a full video script for *topic* in *niche*."""
    tone = NICHE_TONES.get(niche.lower(), DEFAULT_TONE)
    template = _load_template("script_prompt.txt")
    prompt = template.format(
        niche=niche,
        topic=topic,
        tone=tone,
        segment1_title="Background / Context",
        segment2_title="Key Insights",
        segment3_title="Practical Takeaways",
    )

    client = get_llm_client(llm_config)
    logger.info("Generating script for topic: %s", topic)
    raw_script = client.complete(prompt)
    script = _parse_script(raw_script)

    if not script["title"]:
        # Fallback: use topic as title
        script["title"] = topic

    logger.info("Script generated. Title: %s | Segments: %d", script["title"], len(script["segments"]))
    return script


def generate_description(script: dict, niche: str, llm_config: dict) -> str:
    """Generate an SEO-optimised YouTube description for the video."""
    template = _load_template("description_prompt.txt")
    summary = " ".join(
        seg["narration"][:150] for seg in script.get("segments", [])
    )
    primary_keyword = niche
    prompt = template.format(
        title=script["title"],
        niche=niche,
        summary=summary,
        primary_keyword=primary_keyword,
    )

    client = get_llm_client(llm_config)
    logger.info("Generating description for: %s", script["title"])
    description = client.complete(prompt)
    return description


def get_full_narration(script: dict) -> str:
    """Concatenate all spoken parts of the script into a single narration string."""
    parts = []
    if script.get("hook"):
        parts.append(script["hook"])
    for seg in script.get("segments", []):
        parts.append(seg["narration"])
    if script.get("cta"):
        parts.append(script["cta"])
    return "\n\n".join(parts)
