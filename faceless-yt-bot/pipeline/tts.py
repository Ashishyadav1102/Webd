"""
tts.py
Converts a narration script to an MP3 audio file using Microsoft Edge TTS (free).
Edge-TTS runs entirely offline/via Microsoft's free endpoint — no API key needed.
"""

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _sanitize_ssml_text(text: str) -> str:
    """Remove characters that can break TTS engines."""
    # Replace smart quotes with regular quotes
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Replace em-dash with comma+space for natural pause
    text = text.replace("\u2014", ", ").replace("\u2013", " - ")
    # Strip markdown formatting
    import re
    text = re.sub(r"[*_#`]", "", text)
    return text.strip()


async def _generate_audio(text: str, voice: str, rate: str, volume: str, output_path: str) -> None:
    try:
        import edge_tts  # pip install edge-tts
    except ImportError as exc:
        raise ImportError(
            "edge-tts package not installed. Run: pip install edge-tts"
        ) from exc

    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    await communicate.save(output_path)


def text_to_speech(
    narration: str,
    tts_config: dict,
    output_dir: str,
    filename: str = "voiceover.mp3",
) -> str:
    """
    Convert *narration* text to speech and save as an MP3 file.

    Args:
        narration:   Full narration text.
        tts_config:  Dict with keys: voice, rate, volume.
        output_dir:  Directory where the MP3 will be saved.
        filename:    Output filename (default: voiceover.mp3).

    Returns:
        Absolute path to the generated MP3 file.
    """
    voice = tts_config.get("voice", "en-US-GuyNeural")
    rate = tts_config.get("rate", "+0%")
    volume = tts_config.get("volume", "+0%")

    os.makedirs(output_dir, exist_ok=True)
    output_path = str(Path(output_dir) / filename)

    clean_text = _sanitize_ssml_text(narration)
    if not clean_text:
        raise ValueError("Narration text is empty after sanitization.")

    logger.info("Generating TTS audio | voice=%s | output=%s", voice, output_path)
    asyncio.run(_generate_audio(clean_text, voice, rate, volume, output_path))

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"TTS output file was not created or is empty: {output_path}")

    size_kb = os.path.getsize(output_path) // 1024
    logger.info("TTS complete. File: %s (%d KB)", output_path, size_kb)
    return output_path


def list_available_voices() -> list[dict]:
    """Return a list of available Edge-TTS voices (for reference/setup)."""
    try:
        import edge_tts
    except ImportError as exc:
        raise ImportError("edge-tts package not installed. Run: pip install edge-tts") from exc

    async def _list():
        return await edge_tts.list_voices()

    voices = asyncio.run(_list())
    return [
        {"name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]}
        for v in voices
    ]
