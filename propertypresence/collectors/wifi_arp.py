"""LAN presence via ARP sweep of the property's own subnet.

Two backends, tried in order:
  1. scapy ARP sweep (fast, needs root/CAP_NET_RAW)
  2. the system ARP/neighbour table (`ip neigh` / `arp -a`) — no privileges,
     reflects devices the host has recently talked to.

Only devices on the LAN you operate are ever seen here.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
import subprocess

from ..models import Observation

log = logging.getLogger("propertypresence.collectors.wifi")

_MAC_RE = re.compile(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})")
_IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")


def _default_subnet() -> str | None:
    """Best-effort /24 for the host's primary interface."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return str(ipaddress.ip_network(ip + "/24", strict=False))
    except Exception:
        return None


class WifiArpCollector:
    name = "wifi"

    def __init__(self, cfg: dict):
        subnet = (cfg or {}).get("subnet", "auto")
        self.subnet = _default_subnet() if subnet in (None, "", "auto") else subnet

    def collect(self) -> list[Observation]:
        obs = self._scapy_scan()
        if obs is None:
            obs = self._neighbour_table()
        log.info("wifi: %d device(s) on %s", len(obs), self.subnet)
        return obs

    # ── backend 1: active scapy ARP sweep ────────────────────────────────
    def _scapy_scan(self) -> list[Observation] | None:
        if not self.subnet:
            return None
        try:
            from scapy.all import ARP, Ether, srp  # type: ignore
        except Exception:
            return None
        try:
            ans = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=self.subnet),
                      timeout=2, verbose=0)[0]
        except PermissionError:
            log.warning("wifi: scapy needs root/CAP_NET_RAW; falling back to arp table")
            return None
        except Exception as ex:
            log.warning("wifi: scapy scan failed (%s); falling back to arp table", ex)
            return None
        return [Observation(mac=r.hwsrc, ip=r.psrc, source=self.name) for _, r in ans]

    # ── backend 2: passive neighbour table ───────────────────────────────
    def _neighbour_table(self) -> list[Observation]:
        for cmd in (["ip", "neigh"], ["arp", "-a"]):
            try:
                out = subprocess.check_output(cmd, text=True, timeout=5)
            except (FileNotFoundError, subprocess.SubprocessError):
                continue
            found: list[Observation] = []
            for line in out.splitlines():
                mac = _MAC_RE.search(line)
                ip = _IP_RE.search(line)
                if mac and "REACHABLE" not in line.upper() and "FAILED" in line.upper():
                    continue
                if mac:
                    found.append(Observation(mac=mac.group(1),
                                             ip=ip.group(1) if ip else None,
                                             source=self.name))
            if found:
                return found
        return []
