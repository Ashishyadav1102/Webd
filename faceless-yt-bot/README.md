# Automated Faceless YouTube Channel Bot 🎬

A fully automated pipeline that generates niche-specific scripts, converts them to voiceover and video, and uploads to YouTube — **100% free tools**.

---

## Features

| Feature | Tool Used |
|---|---|
| Script & topic generation | Groq API (Llama 3, free) or Google Gemini (free) |
| Text-to-speech | Microsoft Edge TTS (free, no key) |
| Stock footage | Pexels API (free) |
| AI images (optional) | HuggingFace Inference API (free tier) |
| Video assembly | MoviePy + FFmpeg |
| Thumbnail | Pillow (local, no API) |
| YouTube upload | YouTube Data API v3 (free quota) |
| Scheduling | Python `schedule` library or cron |
| Topic queue | SQLite (local) |

---

## Project Structure

```
faceless-yt-bot/
├── channels/
│   ├── channel1_config.yaml       # Motivation niche
│   ├── channel2_config.yaml       # Tech Facts niche
│   ├── channel1_oauth.json        # ← you provide (Google OAuth2 client secret)
│   └── channel2_oauth.json        # ← you provide
├── templates/
│   ├── script_prompt.txt
│   └── description_prompt.txt
├── assets/
│   ├── intro.mp4                  # optional
│   ├── outro.mp4                  # optional
│   ├── logo.png                   # optional channel logo for thumbnails
│   └── music/                     # add royalty-free .mp3 files here
├── pipeline/
│   ├── llm_client.py
│   ├── topic_generator.py
│   ├── script_generator.py
│   ├── tts.py
│   ├── video_builder.py
│   ├── thumbnail_maker.py
│   └── uploader.py
├── output/                        # auto-created, holds generated videos
├── main.py                        # single-channel pipeline runner
├── scheduler.py                   # multi-channel daily scheduler
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

> **System requirement:** FFmpeg must be installed.
> - macOS: `brew install ffmpeg`
> - Ubuntu/Debian: `sudo apt install ffmpeg`
> - Windows: Download from https://ffmpeg.org/download.html and add to PATH

### 2. Set Environment Variables

Create a `.env` file (or export in your shell):

```bash
# At least one LLM provider is required
GROQ_API_KEY=your_groq_api_key_here          # https://console.groq.com
GEMINI_API_KEY=your_gemini_api_key_here      # https://aistudio.google.com

# Required for stock footage
PEXELS_API_KEY=your_pexels_api_key_here      # https://www.pexels.com/api/

# Optional: HuggingFace image generation
HF_API_KEY=your_huggingface_token_here       # https://huggingface.co/settings/tokens
```

Load them before running:
```bash
export $(cat .env | xargs)
```

### 3. Set Up YouTube OAuth2 Credentials

For **each** channel:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project → Enable **YouTube Data API v3**
3. Create **OAuth 2.0 Client ID** (Desktop app type)
4. Download the JSON and save as `channels/channel1_oauth.json`
5. On first run, a browser window will open to authorise. The token is saved automatically for future runs.

### 4. Add Background Music (Optional)

Place royalty-free `.mp3` files in `assets/music/`. Good free sources:
- [YouTube Audio Library](https://studio.youtube.com/channel/music)
- [Free Music Archive](https://freemusicarchive.org/)
- [Pixabay Music](https://pixabay.com/music/)

### 5. Run a Single Channel

```bash
# Full pipeline (generates script → TTS → video → upload)
python main.py --channel channels/channel1_config.yaml

# Dry-run: generate script only, no video/upload
python main.py --channel channels/channel1_config.yaml --dry-run
```

### 6. Run All Channels on a Schedule

```bash
# Run all due channels once (great for cron jobs)
python scheduler.py --once

# Run continuously, triggering at 09:00 every day
python scheduler.py --time 09:00
```

**Cron example** (runs at 9 AM daily):
```cron
0 9 * * * cd /path/to/faceless-yt-bot && /usr/bin/python3 scheduler.py --once >> logs/scheduler.log 2>&1
```

---

## Adding a New Channel

1. Copy `channels/channel1_config.yaml` to e.g. `channels/channel3_config.yaml`
2. Edit the niche, voice, colors, and tags
3. Download a new OAuth2 credential JSON for the new YouTube channel
4. The scheduler will automatically pick it up

---

## Configuration Reference

| Key | Description |
|---|---|
| `channel.niche` | Niche keyword (used in LLM prompts) |
| `channel.upload_frequency_days` | How often to upload (1 = daily) |
| `llm.provider` | `groq` or `gemini` |
| `llm.model` | LLM model name (e.g. `llama3-8b-8192`) |
| `tts.voice` | Edge-TTS voice name (run `edge-tts --list-voices`) |
| `visuals.source` | `pexels` or `huggingface` |
| `visuals.style` | `stock_footage` or `ai_images` |
| `music.volume` | Background music volume 0.0–1.0 (0.08 = 8%) |
| `thumbnail.bg_color` | Hex background color for thumbnail |
| `youtube.credentials_file` | Path to OAuth2 client secret JSON |

---

## YouTube API Quota

- **Free quota:** 10,000 units/day per Google Cloud project
- **One upload:** ~1,600 units → ~6 uploads/day per project
- **Workaround:** Create multiple Google Cloud projects (one per 6 channels)

---

## Free Tier Limits Summary

| Service | Free Limit |
|---|---|
| Groq API | ~14,400 req/day (varies by model) |
| Google Gemini | 15 req/min, 1M tokens/day |
| Pexels API | 200 req/hour, 20,000/month |
| HuggingFace Inference | Rate-limited, no hard daily cap |
| YouTube Data API | 10,000 units/day per project |
| Edge-TTS | Unlimited (uses Microsoft's free endpoint) |
