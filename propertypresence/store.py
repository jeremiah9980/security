"""SQLite persistence for device state, presence events and poll history."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .models import Device, PresenceEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    mac          TEXT PRIMARY KEY,
    label        TEXT,
    person       TEXT,
    known        INTEGER DEFAULT 0,
    online       INTEGER DEFAULT 0,
    ip           TEXT,
    rssi         INTEGER,
    gateway      TEXT,
    manufacturer TEXT,
    first_seen   INTEGER,
    last_seen    INTEGER,
    online_since INTEGER,
    missed_polls INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS presence_events (
    id       INTEGER PRIMARY KEY,
    ts       INTEGER NOT NULL,
    type     TEXT NOT NULL,
    mac      TEXT,
    label    TEXT,
    person   TEXT,
    source   TEXT,
    severity TEXT,
    title    TEXT
);

CREATE TABLE IF NOT EXISTS poll_history (
    id            INTEGER PRIMARY KEY,
    ts            INTEGER NOT NULL,
    collectors    TEXT,
    devices_seen  INTEGER,
    online_count  INTEGER,
    people_home   INTEGER,
    duration_ms   INTEGER,
    ok            INTEGER
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON presence_events(ts);
"""


class Store:
    def __init__(self, db_path: str):
        os.makedirs(Path(db_path).parent or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    # ── devices ──────────────────────────────────────────────────────────
    def load_devices(self) -> dict[str, Device]:
        out: dict[str, Device] = {}
        for r in self.conn.execute("SELECT * FROM devices"):
            out[r["mac"]] = Device(
                mac=r["mac"], label=r["label"], person=r["person"],
                known=bool(r["known"]), online=bool(r["online"]),
                ip=r["ip"], rssi=r["rssi"], gateway=r["gateway"],
                manufacturer=r["manufacturer"], first_seen=r["first_seen"],
                last_seen=r["last_seen"], online_since=r["online_since"],
                missed_polls=r["missed_polls"] or 0,
            )
        return out

    def upsert_device(self, d: Device) -> None:
        self.conn.execute(
            """INSERT INTO devices
               (mac,label,person,known,online,ip,rssi,gateway,manufacturer,
                first_seen,last_seen,online_since,missed_polls)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(mac) DO UPDATE SET
                 label=excluded.label, person=excluded.person,
                 known=excluded.known, online=excluded.online, ip=excluded.ip,
                 rssi=excluded.rssi, gateway=excluded.gateway,
                 manufacturer=excluded.manufacturer, last_seen=excluded.last_seen,
                 online_since=excluded.online_since, missed_polls=excluded.missed_polls""",
            (d.mac, d.label, d.person, int(d.known), int(d.online), d.ip, d.rssi,
             d.gateway, d.manufacturer, d.first_seen, d.last_seen, d.online_since,
             d.missed_polls),
        )

    def known_macs(self) -> set[str]:
        return {r["mac"] for r in self.conn.execute("SELECT mac FROM devices")}

    # ── events / polls ───────────────────────────────────────────────────
    def record_event(self, ev: PresenceEvent) -> None:
        self.conn.execute(
            """INSERT INTO presence_events
               (ts,type,mac,label,person,source,severity,title)
               VALUES (?,?,?,?,?,?,?,?)""",
            (ev.ts, ev.type, ev.mac, ev.label, ev.person, ev.source, ev.severity, ev.title),
        )

    def record_poll(self, ts, collectors, devices_seen, online_count,
                    people_home, duration_ms, ok) -> None:
        self.conn.execute(
            """INSERT INTO poll_history
               (ts,collectors,devices_seen,online_count,people_home,duration_ms,ok)
               VALUES (?,?,?,?,?,?,?)""",
            (ts, ",".join(collectors), devices_seen, online_count, people_home,
             duration_ms, int(ok)),
        )

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
