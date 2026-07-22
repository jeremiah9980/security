"""Configuration loading: YAML file + environment overrides.

Secrets (Slack webhook, GitHub token, eero session) never live in the YAML —
they come from the environment / .env so config can be committed safely.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

try:  # optional; .env is convenient but not required
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*_a, **_k):  # type: ignore
        return False


DEFAULTS: dict[str, Any] = {
    "property_name": "Home",
    "poll_interval_seconds": 60,
    # A device must miss this many consecutive polls before LEFT/OFFLINE fires.
    # Two misses suppresses false departures from a single dropped scan.
    "offline_confirmation_polls": 2,
    "database": "./data/presence.db",
    "web": {"enabled": True, "host": "0.0.0.0", "port": 8093},
    "collectors": {
        "wifi": {"enabled": True, "subnet": "auto"},
        "bluetooth": {"enabled": False, "scan_seconds": 8},
        "eero": {"enabled": False, "network_name": "", "session_file": "./data/eero_session.cookie"},
    },
    "sinks": {
        "slack": {"enabled": True, "notify_on_new_device": True},
        "github": {"enabled": False, "repo": "", "branch": "main",
                   "status_path": "status/presence.json",
                   "history_path": "status/history.jsonl",
                   "redact_macs": True},
        "log": {"enabled": True},
    },
    "integrations": {
        "ring": {"enabled": False, "poll_seconds": 30},
        "alexa": {"enabled": False},
        "cameras": {"enabled": False, "feeds": []},
    },
    # Roster of YOUR OWN known devices. Entries with `person:` emit
    # ARRIVED/LEFT and count toward "people home"; others emit ONLINE/OFFLINE.
    "roster": [],
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | os.PathLike | None) -> dict:
    load_dotenv()
    cfg = dict(DEFAULTS)
    if path:
        p = Path(path)
        if p.exists():
            cfg = _deep_merge(cfg, yaml.safe_load(p.read_text()) or {})
    return cfg


# ── secret accessors (env only) ──────────────────────────────────────────
def slack_webhook_url() -> str:
    return os.environ.get("SLACK_WEBHOOK_URL", "").strip()


def github_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip()


def eero_login_ident() -> str:
    return os.environ.get("EERO_LOGIN", "").strip()


def ring_token_file() -> str:
    return os.environ.get(
        "RING_TOKEN_FILE", str(Path.home() / ".propertypresence_ring_token.json")
    )
