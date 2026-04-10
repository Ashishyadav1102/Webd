"""
main.py
Orchestrates the full pipeline for one channel:
  1. Ensure topic queue is stocked
  2. Pick next topic
  3. Generate script
  4. Generate voiceover (TTS)
  5. Build video
  6. Create thumbnail
  7. Upload to YouTube

Usage:
    python main.py --channel channels/channel1_config.yaml
    python main.py --channel channels/channel1_config.yaml --dry-run
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

# Ensure pipeline modules are importable when running from project root
sys.path.insert(0, str(Path(__file__).parent / "pipeline"))

from topic_generator import ensure_topics, get_next_topic
from script_generator import generate_script, generate_description, get_full_narration
from tts import text_to_speech
from video_builder import build_video
from thumbnail_maker import create_thumbnail
from uploader import upload_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

BASE_DIR = Path(__file__).parent
OUTPUT_BASE = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_pipeline(config_path: str, dry_run: bool = False) -> None:
    """Execute the full content pipeline for one channel config."""
    config = load_config(config_path)

    channel_cfg = config["channel"]
    llm_cfg = config["llm"]
    tts_cfg = config["tts"]
    visuals_cfg = config["visuals"]
    music_cfg = config["music"]
    thumb_cfg = config["thumbnail"]
    yt_cfg = config["youtube"]

    niche = channel_cfg["niche"]
    channel_name = channel_cfg["name"]

    logger.info("=" * 60)
    logger.info("Channel : %s", channel_name)
    logger.info("Niche   : %s", niche)
    logger.info("Dry-run : %s", dry_run)
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Step 1 — Ensure the topic queue is populated
    # ------------------------------------------------------------------
    logger.info("[1/7] Checking topic queue…")
    ensure_topics(niche, llm_cfg, min_count=5)

    # ------------------------------------------------------------------
    # Step 2 — Pick the next topic
    # ------------------------------------------------------------------
    logger.info("[2/7] Fetching next topic…")
    topic = get_next_topic(niche)
    if not topic:
        logger.error("No topics available and generation failed. Aborting.")
        return
    logger.info("Topic: %s", topic)

    # Create a per-video output directory based on sanitised topic name
    safe_topic = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic)[:50].strip()
    out_dir = OUTPUT_BASE / channel_name.replace(" ", "_") / safe_topic
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory: %s", out_dir)

    # ------------------------------------------------------------------
    # Step 3 — Generate script
    # ------------------------------------------------------------------
    logger.info("[3/7] Generating script…")
    script = generate_script(topic, niche, llm_cfg)
    description = generate_description(script, niche, llm_cfg)
    logger.info("Title: %s", script["title"])

    # Save script for review
    script_path = out_dir / "script.txt"
    script_path.write_text(script["raw"], encoding="utf-8")
    desc_path = out_dir / "description.txt"
    desc_path.write_text(description, encoding="utf-8")

    if dry_run:
        logger.info("[DRY-RUN] Skipping TTS, video build and upload.")
        logger.info("Script saved to: %s", script_path)
        return

    # ------------------------------------------------------------------
    # Step 4 — Text-to-Speech
    # ------------------------------------------------------------------
    logger.info("[4/7] Generating voiceover…")
    narration = get_full_narration(script)
    audio_path = text_to_speech(narration, tts_cfg, str(out_dir), filename="voiceover.mp3")

    # ------------------------------------------------------------------
    # Step 5 — Build video
    # ------------------------------------------------------------------
    logger.info("[5/7] Building video…")
    visual_keywords = script.get("visual_keywords", [])
    video_path = build_video(
        audio_path=audio_path,
        visual_keywords=visual_keywords,
        script=script,
        visuals_config=visuals_cfg,
        music_config=music_cfg,
        output_dir=str(out_dir),
        assets_dir=str(ASSETS_DIR),
        filename="final_video.mp4",
    )

    # ------------------------------------------------------------------
    # Step 6 — Thumbnail
    # ------------------------------------------------------------------
    logger.info("[6/7] Creating thumbnail…")
    # Use the first downloaded clip image as background if available
    clips_dir = out_dir / "clips"
    bg_images = list(clips_dir.glob("img_0.*")) + list(clips_dir.glob("clip_0.*"))
    bg_image_path = str(bg_images[0]) if bg_images else None

    logo_path = str(ASSETS_DIR / "logo.png") if (ASSETS_DIR / "logo.png").exists() else None

    thumbnail_path = create_thumbnail(
        title=script["title"],
        thumbnail_config=thumb_cfg,
        output_dir=str(out_dir),
        background_image_path=bg_image_path,
        channel_logo_path=logo_path,
        filename="thumbnail.jpg",
    )

    # ------------------------------------------------------------------
    # Step 7 — Upload to YouTube
    # ------------------------------------------------------------------
    logger.info("[7/7] Uploading to YouTube…")
    credentials_file = str(BASE_DIR / yt_cfg["credentials_file"])
    playlist_id = yt_cfg.get("playlist_id") or None

    title = script["title"]
    tags = script.get("tags", []) + channel_cfg.get("tags", [])
    category_id = channel_cfg.get("category_id", "22")

    video_id = upload_video(
        video_path=video_path,
        thumbnail_path=thumbnail_path,
        title=title,
        description=description,
        tags=list(dict.fromkeys(tags)),  # deduplicate preserving order
        category_id=category_id,
        credentials_file=credentials_file,
        language=channel_cfg.get("language", "en"),
        playlist_id=playlist_id,
    )

    logger.info("✅ Done! Video published: https://www.youtube.com/watch?v=%s", video_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated Faceless YouTube Channel Bot"
    )
    parser.add_argument(
        "--channel",
        required=True,
        help="Path to channel config YAML (e.g. channels/channel1_config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate script only; skip TTS, video build, and upload.",
    )
    args = parser.parse_args()

    config_path = str(BASE_DIR / args.channel) if not os.path.isabs(args.channel) else args.channel
    if not os.path.exists(config_path):
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    run_pipeline(config_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
