"""
thumbnail_maker.py
Generates a YouTube thumbnail (1280x720) using Pillow.
No external API needed — pure local image generation.
"""

import logging
import os
import textwrap
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

THUMB_W, THUMB_H = 1280, 720


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i: i + 2], 16) for i in (0, 2, 4))


def _get_font(size: int):
    """Try to load a bold font; fall back to Pillow default."""
    from PIL import ImageFont

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def create_thumbnail(
    title: str,
    thumbnail_config: dict,
    output_dir: str,
    background_image_path: Optional[str] = None,
    channel_logo_path: Optional[str] = None,
    filename: str = "thumbnail.jpg",
) -> str:
    """
    Generate a YouTube thumbnail image.

    Args:
        title:                 Video title text to overlay.
        thumbnail_config:      Dict: bg_color, text_color, accent_color, font_size.
        output_dir:            Directory to save the thumbnail.
        background_image_path: Optional path to a background photo.
        channel_logo_path:     Optional path to a channel logo PNG.
        filename:              Output filename.

    Returns:
        Path to the generated thumbnail JPEG.
    """
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

    os.makedirs(output_dir, exist_ok=True)
    output_path = str(Path(output_dir) / filename)

    bg_color = _hex_to_rgb(thumbnail_config.get("bg_color", "#1a1a2e"))
    text_color = _hex_to_rgb(thumbnail_config.get("text_color", "#ffffff"))
    accent_color = _hex_to_rgb(thumbnail_config.get("accent_color", "#e94560"))
    font_size = int(thumbnail_config.get("font_size", 60))

    # ------------------------------------------------------------------
    # 1. Background
    # ------------------------------------------------------------------
    if background_image_path and os.path.exists(background_image_path):
        bg = Image.open(background_image_path).convert("RGB")
        bg = bg.resize((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
        # Darken so text is readable
        bg = ImageEnhance.Brightness(bg).enhance(0.45)
        # Slight blur
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
    else:
        # Gradient background
        bg = Image.new("RGB", (THUMB_W, THUMB_H), bg_color)
        draw_bg = ImageDraw.Draw(bg)
        # Simple gradient: lighter top, darker bottom
        for y in range(THUMB_H):
            factor = y / THUMB_H
            r = int(bg_color[0] * (1 - factor * 0.4))
            g = int(bg_color[1] * (1 - factor * 0.4))
            b = int(bg_color[2] * (1 - factor * 0.4))
            draw_bg.line([(0, y), (THUMB_W, y)], fill=(r, g, b))

    draw = ImageDraw.Draw(bg)

    # ------------------------------------------------------------------
    # 2. Accent bar on the left edge
    # ------------------------------------------------------------------
    draw.rectangle([(0, 0), (12, THUMB_H)], fill=accent_color)

    # ------------------------------------------------------------------
    # 3. Title text (word-wrapped)
    # ------------------------------------------------------------------
    font_title = _get_font(font_size)
    font_small = _get_font(max(28, font_size - 24))

    # Wrap title to ~20 chars per line
    wrapped_lines = textwrap.wrap(title, width=22)[:4]  # max 4 lines

    # Calculate total text block height
    line_h = font_size + 12
    block_h = len(wrapped_lines) * line_h
    start_y = (THUMB_H - block_h) // 2 - 20

    for i, line in enumerate(wrapped_lines):
        y = start_y + i * line_h
        x = 50
        # Shadow
        draw.text((x + 3, y + 3), line, font=font_title, fill=(0, 0, 0))
        draw.text((x, y), line, font=font_title, fill=text_color)

    # ------------------------------------------------------------------
    # 4. Accent underline below title
    # ------------------------------------------------------------------
    underline_y = start_y + block_h + 10
    draw.rectangle(
        [(50, underline_y), (min(500, THUMB_W - 50), underline_y + 5)],
        fill=accent_color,
    )

    # ------------------------------------------------------------------
    # 5. Channel logo (top-right corner)
    # ------------------------------------------------------------------
    if channel_logo_path and os.path.exists(channel_logo_path):
        try:
            logo = Image.open(channel_logo_path).convert("RGBA")
            logo_size = 100
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            bg.paste(logo, (THUMB_W - logo_size - 20, 20), mask=logo)
        except Exception as e:
            logger.warning("Could not overlay channel logo: %s", e)

    # ------------------------------------------------------------------
    # 6. Save
    # ------------------------------------------------------------------
    bg.save(output_path, "JPEG", quality=95)
    logger.info("Thumbnail saved: %s", output_path)
    return output_path
