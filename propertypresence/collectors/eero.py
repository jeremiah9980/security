"""eero cloud presence.

Talks to the unofficial eero cloud API (api-user.e2ro.com) for YOUR OWN eero
account and returns the connected-device list. This mirrors the client in the
sibling `eero` repo; a one-time login stores a session token that is
auto-refreshed on 401.

    python -m propertypresence.main --config config/config.yaml --eero-login
"""
from __future__ import annotations

import logging
import os
import re
import time

import requests

from ..models import Observation

log = logging.getLogger("propertypresence.collectors.eero")

API = "https://api-user.e2ro.com/2.2"


class EeroCloud:
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.session_file = self.cfg.get("session_file", "./data/eero_session.cookie")
        self.network_name = (self.cfg.get("network_name") or "").strip().lower()

    # ── session ──────────────────────────────────────────────────────────
    def _token(self):
        try:
            return open(self.session_file).read().strip() or None
        except OSError:
            return None

    def _save(self, token: str):
        os.makedirs(os.path.dirname(self.session_file) or ".", exist_ok=True)
        with open(self.session_file, "w") as f:
            f.write(token)

    def _req(self, method, path, retry=True, **kw):
        tok = self._token()
        if not tok:
            raise RuntimeError("eero: not logged in — run --eero-login")
        r = requests.request(method, API + path, cookies={"s": tok}, timeout=15, **kw)
        if r.status_code in (401, 403) and retry:
            self._refresh()
            return self._req(method, path, retry=False, **kw)
        r.raise_for_status()
        return (r.json() or {}).get("data", {})

    def _refresh(self):
        r = requests.post(API + "/login/refresh", cookies={"s": self._token() or ""}, timeout=15)
        r.raise_for_status()
        new = ((r.json() or {}).get("data") or {}).get("user_token")
        if not new:
            raise RuntimeError("eero: session refresh failed — re-run --eero-login")
        self._save(new)

    # ── one-time login ───────────────────────────────────────────────────
    def start_login(self, ident: str):
        r = requests.post(API + "/login", json={"login": ident}, timeout=15)
        r.raise_for_status()
        self._save(r.json()["data"]["user_token"])

    def verify(self, code: str):
        r = requests.post(API + "/login/verify", json={"code": str(code).strip()},
                          cookies={"s": self._token() or ""}, timeout=15)
        r.raise_for_status()

    def install_token(self, token: str):
        self._save(token.strip())

    # ── data ─────────────────────────────────────────────────────────────
    def devices(self) -> list[dict]:
        acct = self._req("GET", "/account")
        nets = ((acct.get("networks") or {}).get("data")) or []
        if self.network_name:
            matched = [n for n in nets if (n.get("name") or "").strip().lower() == self.network_name]
            nets = matched or nets
        out = []
        for net in nets:
            url = net.get("url") or ""
            path = url[len("/2.2"):] if url.startswith("/2.2") else url
            if not path:
                continue
            for d in self._req("GET", f"{path}/devices") or []:
                out.append(d)
        return out


def _rssi(c):
    v = (c.get("connectivity") or {}).get("signal") or c.get("rssi")
    if isinstance(v, str):
        m = re.search(r"-?\d+", v)
        return int(m.group()) if m else None
    return v


class EeroCollector:
    name = "eero"

    def __init__(self, cfg: dict):
        self.cloud = EeroCloud(cfg)
        self.retries = int((cfg or {}).get("api_retries", 3))

    def collect(self) -> list[Observation]:
        delay = 1
        for attempt in range(self.retries):
            try:
                raw = self.cloud.devices()
                break
            except Exception as ex:
                if attempt == self.retries - 1:
                    log.warning("eero: fetch failed (%s)", ex)
                    return []
                time.sleep(delay)
                delay *= 2
        obs: list[Observation] = []
        for c in raw:
            if not (c.get("connected") or c.get("online")):
                continue
            src = c.get("source") or {}
            obs.append(Observation(
                mac=(c.get("mac") or c.get("mac_address") or ""),
                name=c.get("nickname") or c.get("hostname") or c.get("name"),
                ip=c.get("ip") or (c.get("ips") or [None])[0],
                rssi=_rssi(c),
                gateway=c.get("gateway") or src.get("location") or src.get("display_name"),
                manufacturer=c.get("manufacturer"),
                source=self.name,
            ))
        log.info("eero: %d connected device(s)", len(obs))
        return obs
