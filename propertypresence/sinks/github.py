"""GitHub status sink — commits presence snapshots to a repo via the REST
contents API so the current state (and a rolling history) live in Git.

Writes two files on each change:
  - status_path  (e.g. status/presence.json)  — latest snapshot, overwritten
  - history_path (e.g. status/history.jsonl)  — one appended line per event

PRIVACY: presence data is location data. Point this at a PRIVATE repo. MACs
are SHA-256-hashed by default (`redact_macs: true`) so raw hardware addresses
never land in Git history. The token comes from the GITHUB_TOKEN env var.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time

import requests

from ..config import github_token
from ..models import PresenceEvent

log = logging.getLogger("propertypresence.sinks.github")

API = "https://api.github.com"


def _hash_mac(mac: str) -> str:
    return "sha256:" + hashlib.sha256((mac or "").encode()).hexdigest()[:16]


class GithubSink:
    name = "github"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.repo = self.cfg.get("repo", "")  # "owner/name"
        self.branch = self.cfg.get("branch", "main")
        self.status_path = self.cfg.get("status_path", "status/presence.json")
        self.history_path = self.cfg.get("history_path", "status/history.jsonl")
        self.redact = self.cfg.get("redact_macs", True)
        if not self.repo:
            log.warning("github: no repo configured; sink disabled")

    def _redact(self, obj: dict) -> dict:
        if self.redact and obj.get("mac"):
            obj = dict(obj)
            obj["mac"] = _hash_mac(obj["mac"])
        return obj

    # ── REST helpers ─────────────────────────────────────────────────────
    def _headers(self):
        return {"Authorization": f"Bearer {github_token()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def _get_sha(self, path: str):
        url = f"{API}/repos/{self.repo}/contents/{path}"
        try:
            r = requests.get(url, headers=self._headers(),
                             params={"ref": self.branch}, timeout=10)
            if r.status_code == 200:
                return r.json().get("sha"), r.json().get("content", "")
        except Exception as ex:
            log.warning("github: get %s failed (%s)", path, ex)
        return None, None

    def _put(self, path: str, content_bytes: bytes, message: str, sha=None) -> bool:
        if not (self.repo and github_token()):
            return False
        url = f"{API}/repos/{self.repo}/contents/{path}"
        payload = {
            "message": message,
            "branch": self.branch,
            "content": base64.b64encode(content_bytes).decode(),
        }
        if sha:
            payload["sha"] = sha
        for attempt in range(3):
            try:
                r = requests.put(url, headers=self._headers(), json=payload, timeout=15)
                if r.ok:
                    return True
                if r.status_code == 409 and attempt < 2:  # sha race; refetch
                    sha, _ = self._get_sha(path)
                    payload["sha"] = sha
                    continue
                log.warning("github: put %s failed status=%s %s", path, r.status_code, r.text[:200])
                return False
            except Exception as ex:
                if attempt == 2:
                    log.warning("github: put %s error %s", path, ex)
                    return False
                time.sleep(2 ** attempt)
        return False

    # ── sink API ─────────────────────────────────────────────────────────
    def emit_event(self, ev: PresenceEvent) -> None:
        if not (self.repo and github_token()):
            return
        line = json.dumps(self._redact(ev.as_dict()), default=str)
        sha, content_b64 = self._get_sha(self.history_path)
        existing = b""
        if content_b64:
            try:
                existing = base64.b64decode(content_b64)
            except Exception:
                existing = b""
        new = existing + line.encode() + b"\n"
        self._put(self.history_path, new, f"presence: {ev.type} {ev.label or ev.mac}", sha)

    def emit_snapshot(self, snapshot: dict) -> None:
        if not (self.repo and github_token()):
            return
        snap = dict(snapshot)
        snap["devices"] = [self._redact(d) for d in snapshot.get("devices", [])]
        sha, _ = self._get_sha(self.status_path)
        body = json.dumps(snap, indent=2, default=str).encode()
        self._put(self.status_path, body,
                  f"presence snapshot: {snapshot.get('online_count', 0)} online, "
                  f"{len(snapshot.get('home_names', []))} home", sha)
