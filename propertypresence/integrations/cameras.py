"""Generic camera-feed registry.

A thin, vendor-neutral registry of camera feeds (RTSP URLs, Ring cameras,
or an eventual NextGenSecurity/Kinesis bridge). It doesn't stream media
itself — it records which feed covers which zone and exposes the reference
so a presence event can be linked to the right camera for later review.

This is the seam the NextGenSecurity Alexa/Kinesis pipeline and Ring feeds
plug into. Streaming/clip-export intentionally lives in that cloud stack, not
in this edge agent.
"""
from __future__ import annotations

import logging

from ..models import PresenceEvent

log = logging.getLogger("propertypresence.integrations.cameras")


class CameraRegistry:
    name = "cameras"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        # feeds: [{name, zone, kind: rtsp|ring|kinesis, url}]
        self.feeds = self.cfg.get("feeds", []) or []

    def feeds_for_zone(self, zone: str) -> list[dict]:
        return [f for f in self.feeds if f.get("zone") == zone]

    def all_feeds(self) -> list[dict]:
        return list(self.feeds)

    def on_event(self, ev: PresenceEvent) -> None:
        # Link the event to any feed covering the property's entry zones.
        if not self.feeds:
            return
        refs = [f.get("name") for f in self.feeds if f.get("zone") in ("entry", "any", None)]
        if refs:
            log.info("cameras: event %s -> feeds %s (open these to review)", ev.type, refs)
