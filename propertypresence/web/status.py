"""Live status of every integration point, derived from config + environment.

Pure function over (config, filesystem, env) so it is unit-testable and the
/integrations page always reflects what the agent would actually do at the
next poll — not just what the YAML says.

States:
  active       enabled and everything it needs is present
  needs_setup  enabled but missing a credential/session/dependency
  off          disabled in config
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from ..config import github_token, ring_token_file, slack_webhook_url

ACTIVE, NEEDS_SETUP, OFF = "active", "needs_setup", "off"


def _point(group, key, name, state, detail, hint=None):
    return {"group": group, "key": key, "name": name, "state": state,
            "detail": detail, "hint": hint}


def integration_status(cfg: dict) -> list[dict]:
    out = []
    col = cfg.get("collectors", {})
    snk = cfg.get("sinks", {})
    itg = cfg.get("integrations", {})

    # ── collectors ───────────────────────────────────────────────────────
    wifi = col.get("wifi", {})
    if wifi.get("enabled"):
        subnet = wifi.get("subnet", "auto")
        out.append(_point("collectors", "wifi", "WiFi / ARP scan", ACTIVE,
                          f"subnet: {subnet}" + (" (derived from host)" if subnet in ("auto", "", None) else "")))
    else:
        out.append(_point("collectors", "wifi", "WiFi / ARP scan", OFF,
                          "disabled in config", "collectors.wifi.enabled: true"))

    bt = col.get("bluetooth", {})
    if bt.get("enabled"):
        out.append(_point("collectors", "bluetooth", "Bluetooth", ACTIVE,
                          f"bluetoothctl discovery, {bt.get('scan_seconds', 8)}s window"))
    else:
        out.append(_point("collectors", "bluetooth", "Bluetooth", OFF,
                          "disabled (opt-in — see docs/PRIVACY.md)",
                          "collectors.bluetooth.enabled: true"))

    eero = col.get("eero", {})
    if eero.get("enabled"):
        sess = Path(eero.get("session_file", "./data/eero_session.cookie"))
        if sess.exists() and sess.stat().st_size > 0:
            net = eero.get("network_name") or "all networks"
            out.append(_point("collectors", "eero", "eero cloud API", ACTIVE,
                              f"session on file · polling {net}"))
        else:
            out.append(_point("collectors", "eero", "eero cloud API", NEEDS_SETUP,
                              "no session token", "run: --eero-login"))
    else:
        out.append(_point("collectors", "eero", "eero cloud API", OFF,
                          "disabled in config", "collectors.eero.enabled: true"))

    # ── sinks ────────────────────────────────────────────────────────────
    slack = snk.get("slack", {})
    if slack.get("enabled"):
        urls = [u for u in (slack.get("webhook_urls") or []) if u]
        if slack_webhook_url() or urls:
            n = len(urls) + (1 if slack_webhook_url() else 0)
            out.append(_point("sinks", "slack", "Slack notifications", ACTIVE,
                              f"{n} webhook(s) · new-device alerts "
                              f"{'on' if slack.get('notify_on_new_device', True) else 'off'}"))
        else:
            out.append(_point("sinks", "slack", "Slack notifications", NEEDS_SETUP,
                              "no webhook configured", "set SLACK_WEBHOOK_URL in .env"))
    else:
        out.append(_point("sinks", "slack", "Slack notifications", OFF,
                          "disabled in config", "sinks.slack.enabled: true"))

    gh = snk.get("github", {})
    if gh.get("enabled"):
        if gh.get("repo") and github_token():
            out.append(_point("sinks", "github", "GitHub status repo", ACTIVE,
                              f"{gh['repo']}@{gh.get('branch', 'main')} · "
                              f"MACs {'hashed' if gh.get('redact_macs', True) else 'raw'}"))
        else:
            missing = "repo" if not gh.get("repo") else "GITHUB_TOKEN"
            out.append(_point("sinks", "github", "GitHub status repo", NEEDS_SETUP,
                              f"missing {missing}",
                              "set sinks.github.repo + GITHUB_TOKEN in .env"))
    else:
        out.append(_point("sinks", "github", "GitHub status repo", OFF,
                          "disabled in config", "sinks.github.enabled: true"))

    out.append(_point("sinks", "log", "Structured log",
                      ACTIVE if snk.get("log", {}).get("enabled", True) else OFF,
                      "stdout JSON events"))

    # ── integrations ─────────────────────────────────────────────────────
    ring = itg.get("ring", {})
    if ring.get("enabled"):
        has_lib = importlib.util.find_spec("ring_doorbell") is not None
        has_tok = Path(ring_token_file()).exists()
        if has_lib and has_tok:
            out.append(_point("integrations", "ring", "Ring cameras", ACTIVE,
                              f"snapshots on {', '.join(ring.get('snapshot_on', []) or ['ARRIVED', 'NEW_DEVICE'])}"))
        else:
            miss = "ring_doorbell not installed" if not has_lib else "no auth token"
            hint = "pip install ring_doorbell" if not has_lib else "run: --ring-login"
            out.append(_point("integrations", "ring", "Ring cameras", NEEDS_SETUP, miss, hint))
    else:
        out.append(_point("integrations", "ring", "Ring cameras", OFF,
                          "disabled in config", "integrations.ring.enabled: true"))

    alexa = itg.get("alexa", {})
    if alexa.get("enabled"):
        mode = alexa.get("mode", "notify_me")
        env = os.environ.get("ALEXA_NOTIFYME_TOKEN" if mode == "notify_me" else "ALEXA_WEBHOOK_URL", "").strip()
        if env:
            out.append(_point("integrations", "alexa", "Alexa announcements", ACTIVE,
                              f"mode: {mode} · on {', '.join(alexa.get('announce_on', []))}"))
        else:
            var = "ALEXA_NOTIFYME_TOKEN" if mode == "notify_me" else "ALEXA_WEBHOOK_URL"
            out.append(_point("integrations", "alexa", "Alexa announcements", NEEDS_SETUP,
                              f"mode {mode}, {var} not set", f"set {var} in .env"))
    else:
        out.append(_point("integrations", "alexa", "Alexa announcements", OFF,
                          "disabled in config", "integrations.alexa.enabled: true"))

    cams = itg.get("cameras", {})
    if cams.get("enabled"):
        feeds = [f for f in (cams.get("feeds") or []) if f.get("name")]
        if feeds:
            kinds = {}
            for f in feeds:
                kinds[f.get("kind", "rtsp")] = kinds.get(f.get("kind", "rtsp"), 0) + 1
            det = " · ".join(f"{v}× {k}" for k, v in sorted(kinds.items()))
            out.append(_point("integrations", "cameras", "Camera feed registry", ACTIVE,
                              f"{len(feeds)} feed(s): {det}"))
        else:
            out.append(_point("integrations", "cameras", "Camera feed registry", NEEDS_SETUP,
                              "no feeds registered", "add integrations.cameras.feeds entries"))
    else:
        out.append(_point("integrations", "cameras", "Camera feed registry", OFF,
                          "disabled in config", "integrations.cameras.enabled: true"))

    return out
