"""Presence state machine.

Takes the merged set of observations from every collector for one poll and
produces (a) the updated device table and (b) the list of state-change
events. Departures are debounced: a device must miss
`offline_confirmation_polls` consecutive polls before LEFT/OFFLINE fires,
which suppresses false departures from a single dropped scan.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .models import (ARRIVED, LEFT, NEW_DEVICE, OFFLINE, ONLINE, Device,
                     Observation, PresenceEvent, now_ts)
from .roster import Roster


class PresenceEngine:
    def __init__(self, roster: Roster, offline_confirmation_polls: int = 2):
        self.roster = roster
        self.offline_polls = max(1, int(offline_confirmation_polls))

    def _merge_observations(self, obs: Iterable[Observation]) -> dict[str, dict]:
        """Collapse many observations to one record per MAC (best signal wins)."""
        merged: dict[str, dict] = {}
        for o in obs:
            if not o.mac:
                continue
            m = merged.setdefault(o.mac, {"mac": o.mac, "sources": set(), "name": None,
                                          "ip": None, "rssi": None, "gateway": None,
                                          "manufacturer": None})
            m["sources"].add(o.source)
            for k in ("name", "ip", "gateway", "manufacturer"):
                if getattr(o, k) and not m[k]:
                    m[k] = getattr(o, k)
            if o.rssi is not None:
                # keep the strongest (closest to 0) RSSI seen
                m["rssi"] = o.rssi if m["rssi"] is None else max(m["rssi"], o.rssi)
        return merged

    def evaluate(self, devices: dict[str, Device],
                 observations: Iterable[Observation]) -> tuple[dict[str, Device], list[PresenceEvent]]:
        ts = now_ts()
        seen = self._merge_observations(observations)
        events: list[PresenceEvent] = []

        # 1) devices seen this poll -> online (+ arrival/new-device events)
        for mac, rec in seen.items():
            entry = self.roster.resolve(mac, rec["name"])
            dev = devices.get(mac)
            is_new = dev is None

            if dev is None:
                dev = Device(mac=mac, label=(entry.label if entry else (rec["name"] or "Unknown device")),
                             first_seen=ts)
                devices[mac] = dev

            dev.person = entry.person if entry else None
            dev.known = entry is not None
            dev.label = entry.label if entry else (rec["name"] or dev.label)
            dev.sources = tuple(sorted(rec["sources"]))
            dev.ip = rec["ip"] or dev.ip
            dev.rssi = rec["rssi"]
            dev.gateway = rec["gateway"] or dev.gateway
            dev.manufacturer = rec["manufacturer"] or dev.manufacturer
            dev.last_seen = ts
            dev.missed_polls = 0

            was_online = dev.online
            dev.online = True
            if not was_online:
                dev.online_since = ts

            notify = entry.notify if entry else True
            if is_new and not dev.known:
                events.append(PresenceEvent(
                    type=NEW_DEVICE, mac=mac, label=dev.label,
                    title=f"Unknown device joined {self._where(dev)}",
                    ip=dev.ip, rssi=dev.rssi, gateway=dev.gateway,
                    source=",".join(dev.sources), severity="warning"))
            elif not was_online and notify:
                if dev.person:
                    events.append(PresenceEvent(
                        type=ARRIVED, mac=mac, label=dev.label, person=dev.person,
                        title=f"{dev.person} arrived", ip=dev.ip, rssi=dev.rssi,
                        gateway=dev.gateway, source=",".join(dev.sources)))
                else:
                    events.append(PresenceEvent(
                        type=ONLINE, mac=mac, label=dev.label,
                        title=f"{dev.label} online", ip=dev.ip, rssi=dev.rssi,
                        gateway=dev.gateway, source=",".join(dev.sources)))

        # 2) devices NOT seen this poll -> maybe departed (debounced)
        for mac, dev in devices.items():
            if mac in seen or not dev.online:
                continue
            dev.missed_polls += 1
            if dev.missed_polls < self.offline_polls:
                continue  # still within grace window
            dev.online = False
            dev.sources = ()
            entry = self.roster.resolve(mac, dev.label)
            notify = entry.notify if entry else True
            session = ts - dev.online_since if dev.online_since else None
            if notify:
                if dev.person:
                    events.append(PresenceEvent(
                        type=LEFT, mac=mac, label=dev.label, person=dev.person,
                        title=f"{dev.person} left", session_seconds=session))
                else:
                    events.append(PresenceEvent(
                        type=OFFLINE, mac=mac, label=dev.label,
                        title=f"{dev.label} offline", session_seconds=session))
            dev.online_since = None

        return devices, events

    @staticmethod
    def _where(dev: Device) -> str:
        return "the network" if "wifi" in dev.sources or "eero" in dev.sources else "range"


def people_home(devices: dict[str, Device]) -> list[str]:
    home, seen = [], set()
    for d in devices.values():
        if d.online and d.person and d.person not in seen:
            seen.add(d.person)
            home.append(d.person)
    return home
