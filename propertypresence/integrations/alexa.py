"""Alexa integration — spoken announcements on presence events.

Alexa has no simple public "announce" API, so this supports the two paths
that actually work for a personal setup, selected by `mode` in config:

  mode: "notify_me"  — Amazon's "Notify Me" skill. Set ALEXA_NOTIFYME_TOKEN;
                       posts a notification that Alexa reads on request.
  mode: "webhook"    — a generic webhook (e.g. a local Home Assistant / Node-RED
                       flow that calls alexa_media notify.alexa_media). Set
                       ALEXA_WEBHOOK_URL.

Either way this is fire-and-forget and degrades to a logged no-op if not
configured. It acts on YOUR OWN Alexa account/devices only.
"""
from __future__ import annotations

import logging
import os

import requests

from ..models import ARRIVED, LEFT, NEW_DEVICE, PresenceEvent

log = logging.getLogger("propertypresence.integrations.alexa")

NOTIFY_ME_URL = "https://api.notifymyecho.com/v1/NotifyMe"


class AlexaIntegration:
    name = "alexa"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self.mode = self.cfg.get("mode", "notify_me")
        self.announce_on = set(self.cfg.get("announce_on", [ARRIVED, LEFT, NEW_DEVICE]))

    def on_event(self, ev: PresenceEvent) -> None:
        if ev.type not in self.announce_on:
            return
        message = self._phrase(ev)
        try:
            if self.mode == "notify_me":
                self._notify_me(message)
            elif self.mode == "webhook":
                self._webhook(message)
        except Exception as ex:
            log.warning("alexa: announce failed (%s)", ex)

    @staticmethod
    def _phrase(ev: PresenceEvent) -> str:
        if ev.type == ARRIVED:
            return f"{ev.person or ev.label} just arrived home."
        if ev.type == LEFT:
            return f"{ev.person or ev.label} just left."
        if ev.type == NEW_DEVICE:
            return "Heads up: an unknown device just joined the network."
        return ev.title

    def _notify_me(self, message: str) -> None:
        token = os.environ.get("ALEXA_NOTIFYME_TOKEN", "").strip()
        if not token:
            log.warning("alexa: ALEXA_NOTIFYME_TOKEN not set")
            return
        requests.post(NOTIFY_ME_URL, json={"notification": message, "accessCode": token}, timeout=8)

    def _webhook(self, message: str) -> None:
        url = os.environ.get("ALEXA_WEBHOOK_URL", "").strip()
        if not url:
            log.warning("alexa: ALEXA_WEBHOOK_URL not set")
            return
        requests.post(url, json={"message": message}, timeout=8)
