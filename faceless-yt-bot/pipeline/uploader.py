"""
uploader.py
Uploads a video to YouTube using the YouTube Data API v3 (OAuth2).
Free quota: 10,000 units/day — one video upload costs ~1,600 units (~6 uploads/day).
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE = "youtube"
YOUTUBE_API_VERSION = "v3"
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_RETRIES = 5
CHUNK_SIZE = 256 * 1024  # 256 KB


def _get_authenticated_service(credentials_file: str):
    """
    Build and return an authenticated YouTube service object.
    On first run this will open a browser to authorize.
    The token is saved back to *credentials_file* for reuse.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Required packages not installed. Run:\n"
            "  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        ) from exc

    creds = None
    token_file = credentials_file.replace(".json", "_token.json")

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, [YOUTUBE_UPLOAD_SCOPE])

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"OAuth2 client secret file not found: {credentials_file}\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, [YOUTUBE_UPLOAD_SCOPE]
            )
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build(YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION, credentials=creds)


def upload_video(
    video_path: str,
    thumbnail_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str,
    credentials_file: str,
    language: str = "en",
    playlist_id: Optional[str] = None,
) -> str:
    """
    Upload a video to YouTube.

    Args:
        video_path:        Path to the MP4 file.
        thumbnail_path:    Path to the thumbnail JPEG.
        title:             Video title (max 100 chars).
        description:       Video description.
        tags:              List of tags (each max 500 chars; total max 500 chars).
        category_id:       YouTube category ID string (e.g., "28" for Tech).
        credentials_file:  Path to the OAuth2 client_secret JSON.
        language:          Default audio language.
        playlist_id:       Optional YouTube playlist ID to add the video to.

    Returns:
        The YouTube video ID of the uploaded video.
    """
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    youtube = _get_authenticated_service(credentials_file)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags[:500],
            "categoryId": category_id,
            "defaultAudioLanguage": language,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=CHUNK_SIZE, resumable=True)
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    video_id = _resumable_upload(request)
    logger.info("Video uploaded successfully. ID: %s", video_id)

    # Set thumbnail
    if os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path),
            ).execute()
            logger.info("Thumbnail set for video %s", video_id)
        except Exception as e:
            logger.warning("Failed to set thumbnail: %s", e)

    # Add to playlist
    if playlist_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
            logger.info("Added video %s to playlist %s", video_id, playlist_id)
        except Exception as e:
            logger.warning("Failed to add to playlist: %s", e)

    return video_id


def _resumable_upload(request) -> str:
    """Execute a resumable upload with exponential back-off on transient errors."""
    from googleapiclient.errors import HttpError

    response = None
    error = None
    retry = 0

    while response is None:
        try:
            logger.info("Uploading video chunk…")
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info("Upload progress: %d%%", pct)
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = f"Retriable HTTP error {e.resp.status}: {e.content}"
            else:
                raise
        except Exception as e:
            error = f"Transient error: {e}"

        if error:
            retry += 1
            if retry > MAX_RETRIES:
                raise RuntimeError(f"Upload failed after {MAX_RETRIES} retries. Last error: {error}")
            wait = 2 ** retry
            logger.warning("%s — retrying in %d seconds…", error, wait)
            time.sleep(wait)
            error = None

    return response["id"]
