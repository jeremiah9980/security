"""Collectors turn a live signal (LAN, Bluetooth, eero cloud) into a list of
Observation records. Each collector is independent and degrades gracefully:
a collector that fails (missing tool, no creds, network error) returns [] and
logs a warning rather than taking down the poll.
"""
from __future__ import annotations

import logging
from typing import Protocol

from ..models import Observation

log = logging.getLogger("propertypresence.collectors")


class Collector(Protocol):
    name: str

    def collect(self) -> list[Observation]:
        ...


def build_collectors(cfg: dict) -> list["Collector"]:
    """Instantiate the enabled collectors from config."""
    out: list[Collector] = []
    c = cfg.get("collectors", {})
    if c.get("wifi", {}).get("enabled"):
        from .wifi_arp import WifiArpCollector
        out.append(WifiArpCollector(c["wifi"]))
    if c.get("bluetooth", {}).get("enabled"):
        from .bluetooth import BluetoothCollector
        out.append(BluetoothCollector(c["bluetooth"]))
    if c.get("eero", {}).get("enabled"):
        from .eero import EeroCollector
        out.append(EeroCollector(c["eero"]))
    return out
