"""A polite web client: one request per host per minimum interval, gzip, a descriptive
User-Agent with a contact, and an on-disk cache so the same request is never sent twice.

Liquipedia asks for at most 1 request per 2 s; OWTV for 1 per 5 s (contracts/reference-sources.md).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from owstudy.collect import __version__
from owstudy.collect.errors import RetrievalBlocked

BLOCKING_STATUS = {403, 429}


@dataclass(frozen=True)
class CachedResponse:
    url: str
    status: int
    content: bytes
    from_cache: bool

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content)


def build_user_agent(contact: str) -> str:
    if not contact or contact.startswith("<"):
        raise RetrievalBlocked(
            "no contact for the User-Agent: set user_agent_contact in configs/collect/local.yaml"
        )
    return f"owstudy-collect/{__version__} (research data collection; contact: {contact})"


def cache_key(url: str, params: Mapping[str, Any] | None) -> str:
    blob = json.dumps({"url": url, "params": sorted((params or {}).items())}, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class HttpClient:
    """GET with per-host spacing and caching. Raises RetrievalBlocked on 403/429 or no network.

    `session`, `clock` and `sleep` can be swapped out in tests.
    """

    def __init__(
        self,
        host_min_interval_s: Mapping[str, float],
        cache_dir: str | Path,
        user_agent_contact: str,
        session: Any = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = 30.0,
    ):
        self.host_min_interval_s = dict(host_min_interval_s)
        self.cache_dir = Path(cache_dir)
        self.user_agent = build_user_agent(user_agent_contact)
        if session is None:
            import requests

            session = requests.Session()
        self.session = session
        self.clock = clock
        self.sleep = sleep
        self.timeout_s = timeout_s
        self._last: dict[str, float] = {}

    def _interval(self, host: str) -> float:
        for pattern, interval in self.host_min_interval_s.items():
            if host == pattern or host.endswith("." + pattern):
                return interval
        raise RetrievalBlocked(f"no rate limit configured for {host}; refusing to contact it")

    def _wait_turn(self, host: str) -> None:
        interval = self._interval(host)
        last = self._last.get(host)
        if last is not None:
            remaining = interval - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.cache_dir / f"{key}.body", self.cache_dir / f"{key}.json"

    def get(self, url: str, params: Mapping[str, Any] | None = None, use_cache: bool = True) -> CachedResponse:
        key = cache_key(url, params)
        body_path, meta_path = self._paths(key)
        if use_cache and body_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return CachedResponse(meta["url"], meta["status"], body_path.read_bytes(), True)

        host = urlsplit(url).hostname or ""
        self._wait_turn(host)
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip"}
        try:
            resp = self.session.get(url, params=dict(params or {}), headers=headers, timeout=self.timeout_s)
        except Exception as e:  # network down, DNS, timeout
            raise RetrievalBlocked(f"couldn't reach {host}: {e}") from e

        if resp.status_code in BLOCKING_STATUS:
            raise RetrievalBlocked(f"{host} answered {resp.status_code}; stopping (rate limit or access refused)")
        if resp.status_code >= 400:
            raise RetrievalBlocked(f"{host} answered {resp.status_code} for {url}")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(resp.content)
        meta_path.write_text(
            json.dumps({"url": url, "params": dict(params or {}), "status": resp.status_code}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return CachedResponse(url, resp.status_code, resp.content, False)
