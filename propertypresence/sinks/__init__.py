"""Sinks receive presence events + snapshots and publish them somewhere
(Slack, GitHub, stdout). Like collectors, a sink that fails logs and moves on
rather than breaking the poll loop.
"""
from __future__ import annotations

import logging
from typing import Protocol

from ..models import Device, PresenceEvent

log = logging.getLogger("propertypresence.sinks")


class Sink(Protocol):
    name: str

    def emit_event(self, ev: PresenceEvent) -> None:
        ...

    def emit_snapshot(self, snapshot: dict) -> None:
        ...


def build_sinks(cfg: dict) -> list["Sink"]:
    out: list[Sink] = []
    s = cfg.get("sinks", {})
    if s.get("log", {}).get("enabled", True):
        from .logsink import LogSink
        out.append(LogSink(s.get("log", {})))
    if s.get("slack", {}).get("enabled"):
        from .slack import SlackSink
        out.append(SlackSink(s["slack"]))
    if s.get("github", {}).get("enabled"):
        from .github import GithubSink
        out.append(GithubSink(s["github"]))
    return out
