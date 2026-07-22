"""Bluetooth presence via `bluetoothctl` discovery.

Bluetooth is opt-in and, for presence purposes, only meaningful for devices
in your roster (a phone/watch/tag you registered). Discoverable-but-unknown
devices are reported like any other unknown device — as an anonymous signal,
not an identity. See docs/PRIVACY.md before enabling this in a shared space.
"""
from __future__ import annotations

import logging
import re
import subprocess
import time

from ..models import Observation

log = logging.getLogger("propertypresence.collectors.bluetooth")

_MAC_RE = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")


class BluetoothCollector:
    name = "bluetooth"

    def __init__(self, cfg: dict):
        self.scan_seconds = int((cfg or {}).get("scan_seconds", 8))

    def collect(self) -> list[Observation]:
        rows = self._scan()
        log.info("bluetooth: %d device(s)", len(rows))
        return [Observation(mac=mac, name=name, source=self.name) for mac, name in rows]

    def _scan(self) -> list[tuple[str, str]]:
        try:
            subprocess.run(["bluetoothctl", "power", "on"], capture_output=True, timeout=5)
            subprocess.run(["bluetoothctl", "scan", "on"], capture_output=True, timeout=2)
            time.sleep(self.scan_seconds)
            out = subprocess.check_output(["bluetoothctl", "devices"], text=True, timeout=5)
            subprocess.run(["bluetoothctl", "scan", "off"], capture_output=True, timeout=2)
        except (subprocess.SubprocessError, FileNotFoundError) as ex:
            log.warning("bluetooth: bluetoothctl unavailable (%s)", ex)
            return []
        rows: list[tuple[str, str]] = []
        for line in out.splitlines():
            m = _MAC_RE.search(line)
            if m:
                mac = m.group(1)
                name = line.split(mac, 1)[-1].strip() or "unknown"
                rows.append((mac, name))
        return rows
