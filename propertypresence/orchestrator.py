"""The agent loop: run every collector, fold observations through the engine,
persist state, and fan the resulting events out to sinks and integrations.
"""
from __future__ import annotations

import logging
import time

from .collectors import build_collectors
from .engine import PresenceEngine, people_home
from .integrations import build_integrations
from .models import Observation
from .roster import Roster
from .sinks import build_sinks
from .store import Store

log = logging.getLogger("propertypresence.orchestrator")


class Agent:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.roster = Roster.from_config(cfg.get("roster", []))
        self.engine = PresenceEngine(self.roster, cfg.get("offline_confirmation_polls", 2))
        self.store = Store(cfg.get("database", "./data/presence.db"))
        self.collectors = build_collectors(cfg)
        self.sinks = build_sinks(cfg)
        self.enrichers, self.actors = build_integrations(cfg)
        self.devices = self.store.load_devices()
        names = [c.name for c in self.collectors]
        log.info("agent ready: collectors=%s sinks=%s integrations=%s roster=%d people=%s",
                 names, [s.name for s in self.sinks],
                 [a.name for a in self.actors], len(cfg.get("roster", [])),
                 self.roster.people)

    def poll_once(self) -> dict:
        t0 = time.time()
        observations: list[Observation] = []
        used: list[str] = []
        for c in self.collectors + self.enrichers:
            try:
                found = c.collect()
                observations.extend(found)
                used.append(c.name)
            except Exception as ex:  # a broken collector must not stop the loop
                log.warning("collector %s failed: %s", getattr(c, "name", "?"), ex)

        self.devices, events = self.engine.evaluate(self.devices, observations)

        for d in self.devices.values():
            self.store.upsert_device(d)
        for ev in events:
            self.store.record_event(ev)
            self._dispatch(ev)

        snapshot = self.snapshot()
        for s in self.sinks:
            try:
                s.emit_snapshot(snapshot)
            except Exception as ex:
                log.warning("sink %s snapshot failed: %s", s.name, ex)

        dur_ms = int((time.time() - t0) * 1000)
        self.store.record_poll(int(time.time()), used, len(observations),
                               snapshot["online_count"], len(snapshot["home_names"]),
                               dur_ms, True)
        self.store.commit()
        log.info("poll done: %d obs, %d events, %d online, home=%s (%dms)",
                 len(observations), len(events), snapshot["online_count"],
                 snapshot["home_names"], dur_ms)
        return snapshot

    def _dispatch(self, ev) -> None:
        for s in self.sinks:
            try:
                s.emit_event(ev)
            except Exception as ex:
                log.warning("sink %s event failed: %s", s.name, ex)
        for a in self.actors:
            try:
                a.on_event(ev)
            except Exception as ex:
                log.warning("integration %s event failed: %s", a.name, ex)

    def snapshot(self) -> dict:
        online = [d for d in self.devices.values() if d.online]
        home = people_home(self.devices)
        return {
            "property": self.cfg.get("property_name", "Home"),
            "generated_at": int(time.time()),
            "online_count": len(online),
            "known_count": sum(1 for d in self.devices.values() if d.known),
            "people_home": len(home),
            "home_names": home,
            "devices": [d.as_dict() for d in online],
        }

    def run(self) -> None:
        interval = int(self.cfg.get("poll_interval_seconds", 60))
        log.info("starting agent loop, interval=%ds", interval)
        while True:
            try:
                self.poll_once()
            except Exception as ex:
                log.exception("poll loop error: %s", ex)
            time.sleep(interval)

    def close(self) -> None:
        self.store.close()
