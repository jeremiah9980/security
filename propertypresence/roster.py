"""Roster matching: map observed devices to the owner's known devices.

The roster is the consent boundary of this project. Presence for a *person*
is only ever derived from devices the owner deliberately registered here.
Everything else is an anonymous "unknown device" — surfaced as a generic
security signal, never resolved to an identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def _norm_mac(mac: str) -> str:
    return (mac or "").strip().lower().replace("-", ":")


@dataclass
class RosterEntry:
    label: str
    person: Optional[str]
    macs: frozenset
    names: frozenset  # lower-cased substrings to match device names on
    notify: bool = True

    def matches(self, mac: str, name: Optional[str]) -> bool:
        if mac and _norm_mac(mac) in self.macs:
            return True
        if name:
            n = name.strip().lower()
            return any(want and want in n for want in self.names)
        return False


class Roster:
    def __init__(self, entries: list[RosterEntry]):
        self._entries = entries
        # fast path: exact MAC -> entry
        self._by_mac: dict[str, RosterEntry] = {}
        for e in entries:
            for m in e.macs:
                self._by_mac[m] = e

    @classmethod
    def from_config(cls, roster_cfg: list[dict]) -> "Roster":
        entries: list[RosterEntry] = []
        for raw in roster_cfg or []:
            match = raw.get("match", {}) or {}
            entries.append(
                RosterEntry(
                    label=raw.get("name") or raw.get("label") or "device",
                    person=raw.get("person"),
                    macs=frozenset(_norm_mac(m) for m in (match.get("macs") or []) if m),
                    names=frozenset((s or "").strip().lower() for s in (match.get("names") or []) if s),
                    notify=bool(raw.get("notify", True)),
                )
            )
        return cls(entries)

    def resolve(self, mac: str, name: Optional[str]) -> Optional[RosterEntry]:
        m = _norm_mac(mac)
        if m in self._by_mac:
            return self._by_mac[m]
        for e in self._entries:
            if e.matches(m, name):
                return e
        return None

    @property
    def people(self) -> list[str]:
        seen, out = set(), []
        for e in self._entries:
            if e.person and e.person not in seen:
                seen.add(e.person)
                out.append(e.person)
        return out
