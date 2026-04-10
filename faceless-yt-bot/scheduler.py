"""
scheduler.py
Runs the pipeline for every channel on its configured schedule.
Reads all YAML files from the channels/ directory and uploads videos
according to each channel's upload_frequency_days setting.

Usage:
    python scheduler.py                # runs continuously
    python scheduler.py --once        # run all channels once immediately then exit
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path

import yaml
import schedule

BASE_DIR = Path(__file__).parent
CHANNELS_DIR = BASE_DIR / "channels"
STATE_FILE = BASE_DIR / "scheduler_state.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

# Ensure pipeline is importable
sys.path.insert(0, str(BASE_DIR / "pipeline"))


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        yaml.dump(state, f)


def _is_due(channel_name: str, frequency_days: int, state: dict) -> bool:
    """Return True if this channel is due for a new upload today."""
    last_str = state.get(channel_name, {}).get("last_upload")
    if not last_str:
        return True
    last_date = date.fromisoformat(last_str)
    delta = (date.today() - last_date).days
    return delta >= frequency_days


def run_channel(config_path: str) -> None:
    """Import and run the main pipeline for the given channel config."""
    from main import run_pipeline

    try:
        run_pipeline(str(config_path))
    except Exception as e:
        logger.exception("Pipeline failed for %s: %s", config_path, e)


def run_all_due_channels(state: dict) -> None:
    """Iterate over all channel configs and run whichever are due today."""
    config_files = sorted(CHANNELS_DIR.glob("*_config.yaml"))
    if not config_files:
        logger.warning("No channel config files found in %s", CHANNELS_DIR)
        return

    for cfg_path in config_files:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        channel_name = cfg["channel"]["name"]
        frequency = int(cfg["channel"].get("upload_frequency_days", 1))

        if not _is_due(channel_name, frequency, state):
            logger.info(
                "Channel '%s' is not due yet (every %d day(s)). Skipping.",
                channel_name,
                frequency,
            )
            continue

        logger.info("Running pipeline for channel: %s", channel_name)
        run_channel(cfg_path)

        # Update last-upload date
        if channel_name not in state:
            state[channel_name] = {}
        state[channel_name]["last_upload"] = date.today().isoformat()
        save_state(state)
        logger.info("State saved for channel: %s", channel_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Faceless YouTube Channel Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run all due channels once and exit (useful for cron jobs).",
    )
    parser.add_argument(
        "--time",
        default="09:00",
        help="Daily run time in HH:MM format (default: 09:00). Used in continuous mode.",
    )
    args = parser.parse_args()

    state = load_state()

    if args.once:
        logger.info("Running in --once mode.")
        run_all_due_channels(state)
        return

    # Continuous scheduling mode
    logger.info("Scheduling daily runs at %s (server local time).", args.time)
    schedule.every().day.at(args.time).do(run_all_due_channels, state=state)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")


if __name__ == "__main__":
    main()
