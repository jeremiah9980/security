"""Ring camera integration.

Uses the `ring_doorbell` library against YOUR OWN Ring account to (a) pull
recent motion/ding events and (b) grab a snapshot when a presence event fires
at the property, so an arrival/unknown-device alert can carry camera context.

One-time auth (handles 2FA) stores a token file:
    python -m propertypresence.main --config config/config.yaml --ring-login

If `ring_doorbell` is not installed or no token exists, the integration
degrades to a no-op and logs a hint — the core agent keeps running.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import ring_token_file
from ..models import NEW_DEVICE, ARRIVED, PresenceEvent

log = logging.getLogger("propertypresence.integrations.ring")


class RingIntegration:
    name = "ring"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.snapshot_dir = Path(self.cfg.get("snapshot_dir", "./data/snapshots"))
        self.snapshot_on = set(self.cfg.get("snapshot_on", [NEW_DEVICE, ARRIVED]))
        self._ring = None

    def _get_ring(self):
        if self._ring is not None:
            return self._ring
        token_path = Path(ring_token_file())
        if not token_path.exists():
            log.warning("ring: no token at %s — run --ring-login", token_path)
            return None
        try:
            from ring_doorbell import Auth, Ring
        except ImportError:
            log.warning("ring: pip install ring_doorbell to enable camera context")
            return None
        try:
            token = json.loads(token_path.read_text())
            auth = Auth("PropertyPresence/0.1", token,
                        lambda t: token_path.write_text(json.dumps(t)))
            ring = Ring(auth)
            ring.update_data()
            self._ring = ring
            return ring
        except Exception as ex:
            log.warning("ring: auth/update failed (%s)", ex)
            return None

    def recent_events(self, limit: int = 10) -> list[dict]:
        ring = self._get_ring()
        if not ring:
            return []
        out = []
        try:
            for cam in ring.video_devices():
                for e in cam.history(limit=limit):
                    out.append({"device": cam.name, "kind": e.get("kind"),
                                "created_at": str(e.get("created_at"))})
        except Exception as ex:
            log.warning("ring: history failed (%s)", ex)
        return out

    def on_event(self, ev: PresenceEvent) -> None:
        """Grab a camera snapshot to accompany noteworthy presence events."""
        if ev.type not in self.snapshot_on:
            return
        ring = self._get_ring()
        if not ring:
            return
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        try:
            for cam in ring.video_devices():
                img = cam.get_snapshot()
                path = self.snapshot_dir / f"{cam.name}-{ev.ts}.jpg"
                path.write_bytes(img)
                log.info("ring: snapshot saved %s for event %s", path, ev.type)
        except Exception as ex:
            log.warning("ring: snapshot failed (%s)", ex)
