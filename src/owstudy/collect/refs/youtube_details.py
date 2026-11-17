"""Video details from ObsSojourn's descriptions: match date and where each map starts.

ObsSojourn's descriptions look like:

    Heroes played: Tracer, Pharah, Echo
    ZETA Division vs Team Falcons | OWCS Korea Stage 1 Playoffs
    Match Date: April 25, 2026
    ...
    Timestamps:
    Lijiang Tower: 0:00
    Runasapi: 9:50

`videos details` reads each in-scope video's page information with yt-dlp (text only: no video
is downloaded), one video at a time with a pause between, and saves the fields below into a
dated snapshot `data/raw/reference/youtube_details/<date>/details.json`. Videos already in an
earlier snapshot are not asked again. The catalog uses the newest saved details per video.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from owstudy.collect import __version__
from owstudy.collect.errors import RetrievalBlocked
from owstudy.collect.io.manifest import snapshot_json
from owstudy.collect.refs.snapshot import REFERENCE_ROOT, list_snapshots, new_snapshot

SOURCE = "youtube_details"
DETAILS_FILE = "details.json"
DETAIL_FIELDS = ("id", "title", "description", "upload_date", "duration")
YDL_OPTIONS = {"skip_download": True, "quiet": True, "no_warnings": True}
PAUSE_S = 2.0  # between videos

MATCH_DATE = re.compile(r"^\s*match\s*date\s*:\s*(.+?)\s*$", re.I | re.M)
HEROES = re.compile(r"^\s*heroes\s*played\s*:\s*(.+?)\s*$", re.I | re.M)
STAMP = re.compile(r"^\s*(.+?)\s*[:\-–]\s*((?:\d+:)?\d{1,2}:\d{2})\s*$")


@dataclass(frozen=True)
class Description:
    match_date: dt.date | None = None
    maps: tuple[tuple[str, int], ...] = ()  # (map name as written, start in seconds)
    heroes: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)  # what couldn't be read


def _seconds(text: str) -> int:
    parts = [int(p) for p in text.split(":")]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def _parse_date(text: str) -> dt.date | None:
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip().rstrip("."))
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%Y-%m-%d", "%d %B %Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def parse_description(text: str | None) -> Description:
    """Match date, map timestamps and heroes from a description. Missing parts are empty."""
    text = text or ""
    notes = []
    m = MATCH_DATE.search(text)
    day = _parse_date(m.group(1)) if m else None
    if m and day is None:
        notes.append(f"match date not understood: {m.group(1)!r}")
    maps: list[tuple[str, int]] = []
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().lower().rstrip(":") == "timestamps"), None)
    if start is not None:
        for line in lines[start + 1:]:
            s = STAMP.match(line)
            if not s:
                if maps or line.strip():
                    break  # the list ends at the first line that isn't "Name: m:ss"
                continue
            maps.append((s.group(1).strip(), _seconds(s.group(2))))
    h = HEROES.search(text)
    heroes = tuple(x.strip() for x in h.group(1).split(",") if x.strip()) if h else ()
    return Description(day, tuple(maps), heroes, tuple(notes))


# --- fetching --------------------------------------------------------------------------------


def _default_ydl(options: dict[str, Any]):
    import yt_dlp

    return yt_dlp.YoutubeDL(options)


def load_details(root: str | Path = REFERENCE_ROOT) -> dict[str, dict]:
    """video_id -> saved details, the newest snapshot winning."""
    out: dict[str, dict] = {}
    for folder in list_snapshots(SOURCE, root):
        with open(folder / DETAILS_FILE, encoding="utf-8") as f:
            for entry in json.load(f)["videos"]:
                out[entry["id"]] = entry
    return out


def fetch_details(
    video_ids: Iterable[str],
    root: str | Path = REFERENCE_ROOT,
    date: str | dt.date | None = None,
    refresh: bool = False,
    ydl_factory: Callable[[dict[str, Any]], Any] = _default_ydl,
    sleep: Callable[[float], None] = time.sleep,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[Path | None, list[str]]:
    """Fetch details for videos not saved yet (all of them with `refresh`).

    Returns (new snapshot folder or None if nothing was fetched, video IDs that failed).
    Stops with RetrievalBlocked if YouTube refuses repeatedly (3 failures in a row).
    """
    have = set() if refresh else set(load_details(root))
    todo = sorted(set(video_ids) - have)
    got, failed, streak = [], [], 0
    with ydl_factory(dict(YDL_OPTIONS)) as ydl:
        for n, vid in enumerate(todo, start=1):
            if n > 1:
                sleep(PAUSE_S)
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                got.append({k: info.get(k) for k in DETAIL_FIELDS if info.get(k) is not None})
                streak = 0
            except Exception as e:  # removed or private video, network trouble
                failed.append(vid)
                streak += 1
                if streak >= 3 and not got:
                    raise RetrievalBlocked(f"YouTube refused 3 videos in a row ({e}); nothing was saved") from e
            if progress:
                progress(n, len(todo))
    if not got:
        return None, failed
    folder = new_snapshot(SOURCE, date or dt.date.today(), root=root)
    data = {"videos": sorted(got, key=lambda e: e["id"])}
    (folder / DETAILS_FILE).write_bytes((json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    snapshot_json(folder, SOURCE, folder.name, f"owstudy-collect {__version__} videos details",
                  description="ObsSojourn video descriptions (text only, no downloads)")  # fmt: skip
    return folder, failed
