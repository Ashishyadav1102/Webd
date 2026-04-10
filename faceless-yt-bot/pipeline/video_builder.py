"""
video_builder.py
Assembles the final YouTube video from:
  - Stock footage (Pexels API) or AI-generated images (HuggingFace)
  - Voiceover MP3
  - Background music
  - Auto-generated captions / subtitles
  - Intro / outro bumpers (optional)

Requires: moviepy, Pillow, requests, ffmpeg (system dependency)
"""

import os
import logging
import textwrap
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stock footage helpers (Pexels)
# ---------------------------------------------------------------------------

PEXELS_API_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"


def _pexels_headers() -> dict:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise EnvironmentError("PEXELS_API_KEY environment variable is not set.")
    return {"Authorization": api_key}


def fetch_pexels_videos(query: str, output_dir: str, max_clips: int = 5) -> list[str]:
    """Download up to *max_clips* stock video clips from Pexels for the given query."""
    import requests

    os.makedirs(output_dir, exist_ok=True)
    params = {"query": query, "per_page": max_clips, "orientation": "landscape"}
    resp = requests.get(PEXELS_API_URL, headers=_pexels_headers(), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    paths = []
    for i, video in enumerate(data.get("videos", [])[:max_clips]):
        # Pick the HD file or fall back to the first available
        files = video.get("video_files", [])
        hd = next(
            (f for f in files if f.get("quality") == "hd" and f.get("width", 0) >= 1280),
            files[0] if files else None,
        )
        if not hd:
            continue
        url = hd["link"]
        ext = url.split("?")[0].rsplit(".", 1)[-1] or "mp4"
        dest = str(Path(output_dir) / f"clip_{i}.{ext}")
        logger.info("Downloading Pexels clip %d: %s", i + 1, url[:80])
        urllib.request.urlretrieve(url, dest)
        paths.append(dest)
    return paths


def fetch_pexels_images(query: str, output_dir: str, max_images: int = 8) -> list[str]:
    """Download static images from Pexels (fallback when videos aren't available)."""
    import requests

    os.makedirs(output_dir, exist_ok=True)
    params = {"query": query, "per_page": max_images, "orientation": "landscape"}
    resp = requests.get(PEXELS_PHOTO_URL, headers=_pexels_headers(), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    paths = []
    for i, photo in enumerate(data.get("photos", [])[:max_images]):
        url = photo["src"].get("large2x") or photo["src"]["original"]
        dest = str(Path(output_dir) / f"img_{i}.jpg")
        logger.info("Downloading Pexels image %d", i + 1)
        urllib.request.urlretrieve(url, dest)
        paths.append(dest)
    return paths


# ---------------------------------------------------------------------------
# HuggingFace image generation (free inference API)
# ---------------------------------------------------------------------------

def generate_hf_images(prompts: list[str], output_dir: str) -> list[str]:
    """Generate images via HuggingFace Inference API (free tier)."""
    import requests

    api_key = os.environ.get("HF_API_KEY")
    if not api_key:
        raise EnvironmentError("HF_API_KEY environment variable is not set.")

    os.makedirs(output_dir, exist_ok=True)
    model = "stabilityai/stable-diffusion-2-1"
    headers = {"Authorization": f"Bearer {api_key}"}
    paths = []
    for i, prompt in enumerate(prompts):
        url = f"https://api-inference.huggingface.co/models/{model}"
        resp = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=60)
        resp.raise_for_status()
        dest = str(Path(output_dir) / f"ai_img_{i}.jpg")
        with open(dest, "wb") as f:
            f.write(resp.content)
        logger.info("Generated HF image %d for prompt: %s", i + 1, prompt[:60])
        paths.append(dest)
    return paths


# ---------------------------------------------------------------------------
# Caption / subtitle overlay helpers
# ---------------------------------------------------------------------------

def _make_caption_clip(text: str, duration: float, video_w: int, video_h: int):
    """Return a TextClip with a semi-transparent background for captions."""
    from moviepy.editor import TextClip, CompositeVideoClip, ColorClip

    wrapped = textwrap.fill(text, width=50)
    txt = TextClip(
        wrapped,
        fontsize=36,
        color="white",
        font="DejaVu-Sans-Bold",
        stroke_color="black",
        stroke_width=1.5,
        method="caption",
        size=(int(video_w * 0.9), None),
    ).set_duration(duration)

    # Semi-transparent black bar behind captions
    bar_h = txt.size[1] + 20
    bar = ColorClip(size=(video_w, bar_h), color=(0, 0, 0)).set_opacity(0.55).set_duration(duration)
    bar = bar.set_position(("center", video_h - bar_h - 30))
    txt = txt.set_position(("center", video_h - bar_h - 20))
    return [bar, txt]


# ---------------------------------------------------------------------------
# Core video assembly
# ---------------------------------------------------------------------------

def build_video(
    audio_path: str,
    visual_keywords: list[str],
    script: dict,
    visuals_config: dict,
    music_config: dict,
    output_dir: str,
    assets_dir: str,
    filename: str = "final_video.mp4",
) -> str:
    """
    Assemble the final video.

    Args:
        audio_path:       Path to the voiceover MP3.
        visual_keywords:  List of search keywords per script segment.
        script:           Parsed script dict (from script_generator).
        visuals_config:   Dict: source, style, search_keywords.
        music_config:     Dict: folder, volume.
        output_dir:       Where to write the final MP4.
        assets_dir:       Root assets folder (for intro/outro/music).
        filename:         Output filename.

    Returns:
        Path to the final MP4.
    """
    from moviepy.editor import (
        VideoFileClip,
        ImageClip,
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        concatenate_videoclips,
        afx,
    )

    os.makedirs(output_dir, exist_ok=True)
    clips_dir = str(Path(output_dir) / "clips")
    os.makedirs(clips_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load voiceover and determine total duration
    # ------------------------------------------------------------------
    voiceover = AudioFileClip(audio_path)
    total_duration = voiceover.duration
    logger.info("Voiceover duration: %.1f seconds", total_duration)

    # ------------------------------------------------------------------
    # 2. Gather visual assets
    # ------------------------------------------------------------------
    source = visuals_config.get("source", "pexels")
    style = visuals_config.get("style", "stock_footage")
    fallback_keywords = visuals_config.get("search_keywords", ["nature"])

    # Build a combined list: per-segment keywords + fallback
    all_keywords = [kw for kw in visual_keywords if kw] + fallback_keywords

    raw_clips = []

    if source == "pexels" and style == "stock_footage":
        for kw in all_keywords[:3]:
            paths = fetch_pexels_videos(kw, clips_dir, max_clips=3)
            raw_clips.extend(paths)
            if len(raw_clips) >= 6:
                break
        # If no video clips found, fall back to images
        if not raw_clips:
            logger.warning("No Pexels videos found, falling back to images.")
            for kw in all_keywords[:2]:
                paths = fetch_pexels_images(kw, clips_dir, max_images=6)
                raw_clips.extend(paths)
                if len(raw_clips) >= 6:
                    break

    elif source == "huggingface" or style == "ai_images":
        prompts = [f"cinematic {kw}, 4K, high quality" for kw in all_keywords[:6]]
        raw_clips = generate_hf_images(prompts, clips_dir)

    if not raw_clips:
        raise RuntimeError("No visual assets could be obtained. Check API keys and quotas.")

    # ------------------------------------------------------------------
    # 3. Build visual timeline to match audio duration
    # ------------------------------------------------------------------
    TARGET_W, TARGET_H = 1920, 1080
    video_clips = []
    total_built = 0.0
    clip_duration = total_duration / max(len(raw_clips), 1)
    clip_duration = max(3.0, min(clip_duration, 15.0))  # clamp 3–15 s per clip

    for path in raw_clips:
        if total_built >= total_duration:
            break
        remaining = total_duration - total_built
        seg_dur = min(clip_duration, remaining)

        ext = Path(path).suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp"):
            clip = (
                ImageClip(path)
                .set_duration(seg_dur)
                .resize(height=TARGET_H)
                .crop(x_center=TARGET_W / 2, y_center=TARGET_H / 2, width=TARGET_W, height=TARGET_H)
            )
        else:
            raw = VideoFileClip(path).without_audio()
            if raw.duration < seg_dur:
                raw = raw.loop(duration=seg_dur)
            clip = (
                raw.subclip(0, seg_dur)
                .resize(height=TARGET_H)
                .crop(x_center=raw.size[0] / 2, y_center=TARGET_H / 2, width=min(raw.size[0], TARGET_W), height=TARGET_H)
            )
        video_clips.append(clip)
        total_built += seg_dur

    # If we still need more footage, loop the last clip
    while total_built < total_duration - 0.5:
        remaining = total_duration - total_built
        seg_dur = min(clip_duration, remaining)
        last = video_clips[-1]
        ext_clip = last.subclip(0, min(seg_dur, last.duration))
        video_clips.append(ext_clip)
        total_built += ext_clip.duration

    base_video = concatenate_videoclips(video_clips, method="compose")

    # ------------------------------------------------------------------
    # 4. Add captions from script segments
    # ------------------------------------------------------------------
    caption_overlays = []
    time_cursor = 0.0
    narration_parts = []
    if script.get("hook"):
        narration_parts.append(script["hook"])
    for seg in script.get("segments", []):
        narration_parts.append(seg["narration"])
    if script.get("cta"):
        narration_parts.append(script["cta"])

    words_per_second = 2.5  # average spoken speed
    for part in narration_parts:
        word_count = len(part.split())
        duration = word_count / words_per_second
        duration = min(duration, total_duration - time_cursor)
        if duration <= 0:
            break
        # Show first 100 chars of each part as caption
        caption_text = part[:100].rsplit(" ", 1)[0]
        overlays = _make_caption_clip(caption_text, duration, TARGET_W, TARGET_H)
        for ov in overlays:
            caption_overlays.append(ov.set_start(time_cursor))
        time_cursor += duration

    final_video = CompositeVideoClip([base_video] + caption_overlays)

    # ------------------------------------------------------------------
    # 5. Mix audio: voiceover + background music
    # ------------------------------------------------------------------
    music_folder = Path(assets_dir) / music_config.get("folder", "assets/music").replace("assets/", "")
    music_volume = float(music_config.get("volume", 0.08))

    music_files = list(music_folder.glob("*.mp3")) + list(music_folder.glob("*.wav"))
    if music_files:
        bg_music_path = str(music_files[0])
        bg_audio = AudioFileClip(bg_music_path)
        if bg_audio.duration < total_duration:
            bg_audio = afx.audio_loop(bg_audio, duration=total_duration)
        else:
            bg_audio = bg_audio.subclip(0, total_duration)
        bg_audio = bg_audio.volumex(music_volume)
        mixed_audio = CompositeAudioClip([voiceover, bg_audio])
    else:
        logger.warning("No background music files found in %s. Using voiceover only.", music_folder)
        mixed_audio = voiceover

    final_video = final_video.set_audio(mixed_audio)

    # ------------------------------------------------------------------
    # 6. Optionally prepend intro / append outro
    # ------------------------------------------------------------------
    intro_path = Path(assets_dir) / "intro.mp4"
    outro_path = Path(assets_dir) / "outro.mp4"
    all_parts = []
    if intro_path.exists():
        intro = VideoFileClip(str(intro_path)).resize((TARGET_W, TARGET_H))
        all_parts.append(intro)
    all_parts.append(final_video)
    if outro_path.exists():
        outro = VideoFileClip(str(outro_path)).resize((TARGET_W, TARGET_H))
        all_parts.append(outro)

    if len(all_parts) > 1:
        final_video = concatenate_videoclips(all_parts, method="compose")

    # ------------------------------------------------------------------
    # 7. Export
    # ------------------------------------------------------------------
    output_path = str(Path(output_dir) / filename)
    logger.info("Rendering video to %s …", output_path)
    final_video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )
    logger.info("Video saved: %s", output_path)
    return output_path
