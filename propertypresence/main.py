"""CLI entrypoint.

    python -m propertypresence.main --config config/config.yaml --run
    python -m propertypresence.main --config config/config.yaml --once
    python -m propertypresence.main --config config/config.yaml --eero-login
    python -m propertypresence.main --config config/config.yaml --ring-login
    python -m propertypresence.main --config config/config.yaml --test-slack
"""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from pathlib import Path

from .config import load_config, ring_token_file
from .orchestrator import Agent


def _setup_logging():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _eero_login(cfg: dict):
    from .collectors.eero import EeroCloud
    ecfg = cfg.get("collectors", {}).get("eero", {})
    cloud = EeroCloud(ecfg)
    session = os.environ.get("EERO_SESSION", "").strip()
    if session:
        cloud.install_token(session)
        print(f"eero session token installed to {cloud.session_file}")
        return
    ident = os.environ.get("EERO_LOGIN", "").strip() or input("eero email or phone: ").strip()
    cloud.start_login(ident)
    for _ in range(3):
        code = input("verification code (newest message only): ").strip()
        try:
            cloud.verify(code)
            print("eero login OK; session saved.")
            return
        except Exception as ex:
            print(f"  verify failed: {ex}")
    sys.exit("eero login failed after 3 attempts")


def _ring_login():
    try:
        from ring_doorbell import Auth, Ring
        from ring_doorbell.exceptions import Requires2FAError
    except ImportError:
        sys.exit("pip install ring_doorbell first")
    token_path = Path(ring_token_file())
    username = input("Ring account email: ").strip()
    password = getpass.getpass("Ring account password: ")
    auth = Auth("PropertyPresence/0.1", None,
                lambda t: token_path.write_text(json.dumps(t)))
    try:
        auth.fetch_token(username, password)
    except Requires2FAError:
        otp = input("2FA code: ").strip()
        auth.fetch_token(username, password, otp)
    ring = Ring(auth)
    ring.update_data()
    cams = ring.video_devices()
    print(f"Ring auth OK; token at {token_path}. Cameras: {[c.name for c in cams]}")


def _test_slack(cfg: dict):
    from .sinks.slack import SlackSink
    from .models import PresenceEvent, ONLINE
    sink = SlackSink(cfg.get("sinks", {}).get("slack", {}))
    sink.emit_event(PresenceEvent(type=ONLINE, mac="n/a", label="Self-test",
                                  title="PropertyPresence connected to Slack."))
    print("test Slack notification sent (check the channel).")


def main(argv=None):
    _setup_logging()
    ap = argparse.ArgumentParser(prog="propertypresence")
    ap.add_argument("--config", default="config/config.yaml")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", action="store_true", help="run the continuous agent loop")
    g.add_argument("--once", action="store_true", help="run a single poll and print the snapshot")
    g.add_argument("--eero-login", action="store_true")
    g.add_argument("--ring-login", action="store_true")
    g.add_argument("--test-slack", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    if args.eero_login:
        return _eero_login(cfg)
    if args.ring_login:
        return _ring_login()
    if args.test_slack:
        return _test_slack(cfg)

    agent = Agent(cfg)
    server = None
    try:
        if args.once:
            print(json.dumps(agent.poll_once(), indent=2, default=str))
        else:
            from .web import start_web
            server = start_web(cfg)
            agent.run()
    finally:
        if server:
            server.shutdown()
        agent.close()


if __name__ == "__main__":
    main()
