"""Slack Incoming Webhook sink — Block Kit cards on real state changes only.

The webhook URL comes from the SLACK_WEBHOOK_URL environment variable (or a
`webhook_urls` list in config); it is never committed. Delivery retries with
exponential backoff.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

from ..config import slack_webhook_url
from ..models import (ARRIVED, LEFT, NEW_DEVICE, OFFLINE, ONLINE, PresenceEvent)

log = logging.getLogger("propertypresence.sinks.slack")

STYLE = {
    ARRIVED:    {"emoji": ":large_green_circle:", "color": "#0ca30c"},
    LEFT:       {"emoji": ":red_circle:",         "color": "#d03b3b"},
    ONLINE:     {"emoji": ":large_blue_circle:",  "color": "#3987e5"},
    OFFLINE:    {"emoji": ":white_circle:",       "color": "#898781"},
    NEW_DEVICE: {"emoji": ":warning:",            "color": "#fab219"},
}


def _fmt_dur(seconds):
    if seconds is None:
        return "–"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def _fmt_time(ts):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


class SlackSink:
    name = "slack"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.notify_on_new_device = self.cfg.get("notify_on_new_device", True)

    def _urls(self) -> list[str]:
        urls = [u for u in (self.cfg.get("webhook_urls") or []) if u]
        env = slack_webhook_url()
        if env and env not in urls:
            urls.append(env)
        return urls

    def emit_event(self, ev: PresenceEvent) -> None:
        if ev.type == NEW_DEVICE and not self.notify_on_new_device:
            return
        body = self._blocks(ev)
        for url in self._urls():
            self._post(url, body)

    def emit_snapshot(self, snapshot: dict) -> None:
        # snapshots are not chatty by default; the daily summary is a separate call
        return

    def send_daily_summary(self, snapshot: dict) -> None:
        home = snapshot.get("home_names") or []
        lines = "\n".join(f"• {n}" for n in home) or "_Nobody home_"
        body = {
            "text": f"Daily summary — {len(home)} home",
            "attachments": [{"color": "#3987e5", "blocks": [
                {"type": "section", "text": {"type": "mrkdwn",
                    "text": f":house: *Daily Presence Summary — {snapshot.get('property')}*"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*Currently home:*\n{lines}"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Devices online:*\n{snapshot.get('online_count', 0)}"},
                    {"type": "mrkdwn", "text": f"*Known devices:*\n{snapshot.get('known_count', 0)}"},
                ]},
            ]}],
        }
        for url in self._urls():
            self._post(url, body)

    def _blocks(self, ev: PresenceEvent) -> dict:
        style = STYLE.get(ev.type, STYLE[ONLINE])
        fields = [
            {"type": "mrkdwn", "text": f"*Device:*\n{ev.label or 'Unknown'}"},
            {"type": "mrkdwn", "text": f"*MAC:*\n`{ev.mac or 'n/a'}`"},
        ]
        if ev.person:
            fields.append({"type": "mrkdwn", "text": f"*Person:*\n{ev.person}"})
        if ev.ip:
            fields.append({"type": "mrkdwn", "text": f"*IP:*\n`{ev.ip}`"})
        if ev.source:
            fields.append({"type": "mrkdwn", "text": f"*Seen by:*\n{ev.source}"})
        if ev.rssi is not None:
            fields.append({"type": "mrkdwn", "text": f"*RSSI:*\n{ev.rssi} dBm"})
        if ev.session_seconds is not None:
            fields.append({"type": "mrkdwn", "text": f"*Session:*\n{_fmt_dur(ev.session_seconds)}"})
        fields.append({"type": "mrkdwn", "text": f"*Time:*\n{_fmt_time(ev.ts)}"})
        headline = f"{style['emoji']} *{ev.type}* — {ev.title}"
        return {
            "text": f"[{ev.type}] {ev.title}",
            "attachments": [{"color": style["color"], "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": headline}},
                {"type": "section", "fields": fields[:10]},
            ]}],
        }

    @staticmethod
    def _post(url: str, body: dict, retries: int = 3) -> None:
        delay = 1
        for attempt in range(retries):
            try:
                r = requests.post(url, json=body, timeout=8)
                if r.ok:
                    return
                if r.status_code < 500:
                    log.warning("slack: delivery failed status=%s", r.status_code)
                    return
            except Exception as ex:
                if attempt == retries - 1:
                    log.warning("slack: delivery error %s", ex)
                    return
            time.sleep(delay)
            delay *= 2
