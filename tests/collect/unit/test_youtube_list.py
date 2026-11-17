"""T029: listing the channel's videos into a snapshot, with a stand-in for yt-dlp (no network)."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from owstudy.collect.errors import RetrievalBlocked
from owstudy.collect.refs.youtube_list import YDL_OPTIONS, list_channel, load_videos, upload_day


class FakeYDL:
    seen_options: dict = {}

    def __init__(self, options, info=None, error=None):
        FakeYDL.seen_options = options
        self.info, self.error = info, error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        assert download is False
        if self.error:
            raise self.error
        return self.info


INFO = {"channel_id": "UC123", "entries": [
    {"id": "b2", "title": "[ B ] x | A vs B | OWCS Korea Stage 1", "duration": 100, "timestamp": 1777204800,
     "view_count": 5, "url": "https://youtu.be/b2"},
    {"id": "a1", "title": "[ A ] y | A vs B | OWCS Korea Stage 1", "duration": None, "upload_date": "20260426"},
    None,
]}  # fmt: skip


def test_lists_into_a_new_snapshot(tmp_path):
    folder = list_channel(root=tmp_path, date="2026-11-20", ydl_factory=lambda o: FakeYDL(o, INFO))
    assert folder == tmp_path / "youtube" / "2026-11-20"
    assert FakeYDL.seen_options == YDL_OPTIONS and YDL_OPTIONS["skip_download"]
    entries = load_videos(folder)
    assert [e["id"] for e in entries] == ["a1", "b2"]  # sorted, empty entries dropped
    assert entries[1] == {"id": "b2", "title": INFO["entries"][0]["title"], "duration": 100, "timestamp": 1777204800}
    meta = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    assert meta["source"] == "youtube" and meta["files"][0]["path"] == "obssojourn_videos.json"


def test_network_error_writes_nothing(tmp_path):
    with pytest.raises(RetrievalBlocked, match="offline"):
        list_channel(root=tmp_path, date="2026-11-20", ydl_factory=lambda o: FakeYDL(o, error=OSError("offline")))
    assert not (tmp_path / "youtube").exists()


def test_upload_day():
    assert upload_day({"timestamp": 1777204800}) == dt.date(2026, 4, 26)
    assert upload_day({"upload_date": "20260426"}) == dt.date(2026, 4, 26)
    assert upload_day({}) is None
