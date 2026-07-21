"""Integrations are optional add-ons that either enrich presence (Ring motion
correlated with arrivals) or act on it (Alexa announcements). Each is isolated
behind a small interface so the core agent runs with none of them installed.
"""
from __future__ import annotations

import logging

log = logging.getLogger("propertypresence.integrations")


def build_integrations(cfg: dict):
    """Return (enrichers, actors).

    enrichers: objects with .collect() -> list[Observation] merged into a poll
    actors:    objects with .on_event(event) called for each presence event
    """
    enrichers, actors = [], []
    i = cfg.get("integrations", {})
    if i.get("ring", {}).get("enabled"):
        from .ring import RingIntegration
        ring = RingIntegration(i["ring"])
        actors.append(ring)
    if i.get("alexa", {}).get("enabled"):
        from .alexa import AlexaIntegration
        actors.append(AlexaIntegration(i["alexa"]))
    if i.get("cameras", {}).get("enabled"):
        from .cameras import CameraRegistry
        actors.append(CameraRegistry(i["cameras"]))
    return enrichers, actors
