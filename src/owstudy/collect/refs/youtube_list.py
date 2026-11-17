"""Snapshot of the ObsSojourn channel's video list (task T029). No video is downloaded.

Uses yt-dlp's "flat playlist" mode, which reads the channel's list of uploads only. The result
goes into a new dated snapshot `data/raw/reference/youtube/<date>/obssojourn_videos.json` with
one entry per video, keeping yt-dlp's own field names (values as given, FR-004):
`id` (video_id), `title`, `duration` (duration_s), `timestamp` and `upload_date` when the
listing gives them.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from owstudy.collect import __version__
from owstudy.collect.errors import RetrievalBlocked
from owstudy.collect.io.manifest import snapshot_json
from owstudy.collect.refs.snapshot import REFERENCE_ROOT, new_snapshot

CHANNEL_URL = "https://www.youtube.com/@ObsSojourn/videos"
VIDEOS_FILE = "obssojourn_videos.json"
ENTRY_FIELDS = ("id", "title", "duration", "timestamp", "upload_date")

# Listing only: never download, never write anything but the info we keep.
YDL_OPTIONS = {"extract_flat": "in_playlist", "skip_download": True, "quiet": True, "no_warnings": True}


def _default_ydl(options: dict[str, Any]):
    import yt_dlp

    return yt_dlp.YoutubeDL(options)


def list_channel(
    channel_url: str = CHANNEL_URL,
    root: str | Path = REFERENCE_ROOT,
    date: str | dt.date | None = None,
    ydl_factory: Callable[[dict[str, Any]], Any] = _default_ydl,
) -> Path:
    """List the channel's videos into a new youtube snapshot. Returns the snapshot folder.

    Raises RetrievalBlocked if YouTube can't be reached (nothing is written then).
    """
    date = date or dt.date.today()
    try:
        with ydl_factory(dict(YDL_OPTIONS)) as ydl:
            info = ydl.extract_info(channel_url, download=False)
    except Exception as e:  # network down, channel moved, YouTube refused
        raise RetrievalBlocked(f"couldn't list {channel_url}: {e}") from e

    entries = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        entries.append({k: e.get(k) for k in ENTRY_FIELDS if e.get(k) is not None})
    entries.sort(key=lambda e: e["id"])

    folder = new_snapshot("youtube", date, root=root)
    data = {"channel_url": channel_url, "channel_id": info.get("channel_id") or info.get("id"),
            "entries": entries}  # fmt: skip
    (folder / VIDEOS_FILE).write_bytes((json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    snapshot_json(
        folder, "youtube", folder.name, f"owstudy-collect {__version__} videos list",
        description="ObsSojourn YouTube channel video list (flat playlist, no downloads)",
    )  # fmt: skip
    return folder


def load_videos(snapshot_folder: str | Path) -> list[dict]:
    """The entries of a youtube snapshot as given (yt-dlp field names)."""
    with open(Path(snapshot_folder) / VIDEOS_FILE, encoding="utf-8") as f:
        return json.load(f)["entries"]


def upload_day(entry: dict) -> dt.date | None:
    """Upload date of a listing entry: from `timestamp` (UTC), else `upload_date` (YYYYMMDD)."""
    ts = entry.get("timestamp")
    if ts:
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
    ud = entry.get("upload_date")
    if ud:
        try:
            return dt.datetime.strptime(str(ud), "%Y%m%d").date()
        except ValueError:
            return None
    return None
