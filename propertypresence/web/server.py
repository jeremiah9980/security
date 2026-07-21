"""Stdlib HTTP server for the dashboard + read-only JSON API.

No framework: the agent must run for months on a Pi with minimal deps.
Each request opens its own short-lived SQLite connection, so the web thread
never contends with the poll loop's writes beyond SQLite's own locking.

Routes
  GET /                  main presence dashboard
  GET /integrations      integration-points status page
  GET /api/presence      people home + online devices + summary
  GET /api/devices       full device inventory
  GET /api/events        recent presence events   (?limit=, default 100)
  GET /api/polls         poll diagnostics         (?limit=, default 50)
  GET /api/integrations  status of every integration point
  GET /api/health        healthy/degraded + last poll age
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .status import integration_status

log = logging.getLogger("propertypresence.web")

STATIC_DIR = Path(__file__).parent / "static"
PAGES = {"/": "dashboard.html", "/integrations": "integrations.html"}


def _fmt_ago(seconds):
    if seconds is None:
        return "never"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h {seconds % 3600 // 60}m ago"
    return f"{seconds // 86400}d ago"


class Api:
    """Read-only queries over the agent's SQLite database."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.db_path = cfg.get("database", "./data/presence.db")
        self.started_at = int(time.time())

    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _devices(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM devices ORDER BY online DESC, last_seen DESC")]

    def presence(self):
        now = int(time.time())
        devices = self._devices()
        online = [d for d in devices if d["online"]]
        persons, seen = [], set()
        for d in devices:
            if not d["person"]:
                continue
            if d["person"] in seen:
                # a person may own several devices; home if ANY is online
                if d["online"]:
                    for p in persons:
                        if p["name"] == d["person"]:
                            p["home"] = True
                continue
            seen.add(d["person"])
            persons.append({
                "name": d["person"], "home": bool(d["online"]),
                "device": d["label"],
                "since": d["online_since"],
                "since_human": _fmt_ago(now - d["online_since"]) if d["online_since"] else None,
                "last_seen": d["last_seen"],
                "last_seen_human": _fmt_ago(now - d["last_seen"]) if d["last_seen"] else "never",
            })
        for d in devices:
            d["last_seen_human"] = _fmt_ago(now - d["last_seen"]) if d["last_seen"] else "never"
        return {
            "property": self.cfg.get("property_name", "Home"),
            "generated_at": now,
            "persons": persons,
            "people_home": sum(1 for p in persons if p["home"]),
            "online_count": len(online),
            "known_count": sum(1 for d in devices if d["known"]),
            "unknown_online": sum(1 for d in online if not d["known"]),
            "devices_online": online,
        }

    def devices(self):
        now = int(time.time())
        devices = self._devices()
        for d in devices:
            d["last_seen_human"] = _fmt_ago(now - d["last_seen"]) if d["last_seen"] else "never"
        return {"devices": devices, "total": len(devices)}

    def events(self, limit=100):
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM presence_events ORDER BY ts DESC LIMIT ?", (limit,))]
        now = int(time.time())
        for r in rows:
            r["ago"] = _fmt_ago(now - r["ts"])
        return {"events": rows}

    def polls(self, limit=50):
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM poll_history ORDER BY ts DESC LIMIT ?", (limit,))]
        return {"polls": rows}

    def integrations(self):
        points = integration_status(self.cfg)
        with self._conn() as c:
            last = c.execute(
                "SELECT ts, collectors FROM poll_history ORDER BY ts DESC LIMIT 1").fetchone()
        ran = (last["collectors"].split(",") if last and last["collectors"] else [])
        return {
            "points": points,
            "last_poll_collectors": ran,
            "last_poll_ts": last["ts"] if last else None,
            "summary": {
                "active": sum(1 for p in points if p["state"] == "active"),
                "needs_setup": sum(1 for p in points if p["state"] == "needs_setup"),
                "off": sum(1 for p in points if p["state"] == "off"),
            },
        }

    def health(self):
        now = int(time.time())
        with self._conn() as c:
            last = c.execute("SELECT ts, ok FROM poll_history ORDER BY ts DESC LIMIT 1").fetchone()
        interval = int(self.cfg.get("poll_interval_seconds", 60))
        age = (now - last["ts"]) if last else None
        healthy = last is not None and bool(last["ok"]) and age is not None and age < interval * 3
        return {
            "status": "healthy" if healthy else "degraded",
            "last_poll_age_seconds": age,
            "last_poll_human": _fmt_ago(age) if age is not None else "never",
            "poll_interval_seconds": interval,
            "uptime_seconds": now - self.started_at,
        }


class Handler(BaseHTTPRequestHandler):
    api: Api = None  # set by start_web

    def log_message(self, fmt, *args):  # route through our logger, quietly
        log.debug("%s %s", self.address_string(), fmt % args)

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str).encode(), "application/json")

    def do_GET(self):
        url = urlparse(self.path)
        path, q = url.path.rstrip("/") or "/", parse_qs(url.query)
        try:
            if path in PAGES:
                page = STATIC_DIR / PAGES[path]
                self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/presence":
                self._json(self.api.presence())
            elif path == "/api/devices":
                self._json(self.api.devices())
            elif path == "/api/events":
                self._json(self.api.events(int(q.get("limit", ["100"])[0])))
            elif path == "/api/polls":
                self._json(self.api.polls(int(q.get("limit", ["50"])[0])))
            elif path == "/api/integrations":
                self._json(self.api.integrations())
            elif path == "/api/health":
                self._json(self.api.health())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as ex:
            log.warning("web: %s failed: %s", path, ex)
            self._json({"error": str(ex)}, 500)


def start_web(cfg: dict) -> ThreadingHTTPServer | None:
    web = cfg.get("web", {})
    if not web.get("enabled", True):
        return None
    host, port = web.get("host", "0.0.0.0"), int(web.get("port", 8093))
    handler = type("BoundHandler", (Handler,), {"api": Api(cfg)})
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as ex:
        log.warning("web: could not bind %s:%s (%s) — dashboard disabled", host, port, ex)
        return None
    threading.Thread(target=server.serve_forever, name="web", daemon=True).start()
    log.info("dashboard: http://%s:%d  (integrations: /integrations)",
             "localhost" if host in ("0.0.0.0", "::") else host, port)
    return server
