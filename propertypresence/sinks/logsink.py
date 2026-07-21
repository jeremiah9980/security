"""Structured stdout sink — always useful, no external dependencies."""
from __future__ import annotations

import json
import logging

from ..models import PresenceEvent

log = logging.getLogger("propertypresence.sinks.log")


class LogSink:
    name = "log"

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}

    def emit_event(self, ev: PresenceEvent) -> None:
        log.info("EVENT %s", json.dumps(ev.as_dict(), default=str))

    def emit_snapshot(self, snapshot: dict) -> None:
        log.info("SNAPSHOT people_home=%s online=%s",
                 snapshot.get("people_home"), snapshot.get("online_count"))
