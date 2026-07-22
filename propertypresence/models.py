"""Core data types shared across collectors, engine, sinks and integrations."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional


def now_ts() -> int:
    return int(time.time())


@dataclass
class Observation:
    """A single sighting of a device by one collector during one scan."""

    mac: str
    source: str  # "wifi" | "bluetooth" | "eero" | ...
    ts: int = field(default_factory=now_ts)
    name: Optional[str] = None
    ip: Optional[str] = None
    rssi: Optional[int] = None
    gateway: Optional[str] = None
    manufacturer: Optional[str] = None

    def __post_init__(self) -> None:
        # MACs are the join key across every collector; normalise aggressively.
        self.mac = (self.mac or "").strip().lower().replace("-", ":")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Device:
    """Roster-resolved device with current presence state."""

    mac: str
    label: str  # roster name, or the raw device name for unknown devices
    person: Optional[str] = None  # set only for roster "person" devices
    known: bool = False  # True if matched a roster entry
    online: bool = False
    sources: tuple = ()  # collectors that saw it this poll
    ip: Optional[str] = None
    rssi: Optional[int] = None
    gateway: Optional[str] = None
    manufacturer: Optional[str] = None
    first_seen: Optional[int] = None
    last_seen: Optional[int] = None
    online_since: Optional[int] = None
    missed_polls: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


# Event / alert types the engine can emit.
ARRIVED = "ARRIVED"
LEFT = "LEFT"
ONLINE = "ONLINE"
OFFLINE = "OFFLINE"
NEW_DEVICE = "NEW_DEVICE"  # never-before-seen device -> security warning


@dataclass
class PresenceEvent:
    type: str
    mac: str
    title: str
    ts: int = field(default_factory=now_ts)
    label: Optional[str] = None
    person: Optional[str] = None
    ip: Optional[str] = None
    rssi: Optional[int] = None
    gateway: Optional[str] = None
    source: Optional[str] = None
    severity: str = "info"  # "info" | "warning" | "critical"
    session_seconds: Optional[int] = None

    def as_dict(self) -> dict:
        return asdict(self)
