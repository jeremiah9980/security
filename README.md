# PropertyPresence

A **local presence & network-intelligence agent** for a property you control
(apartment, house, small office). It runs on an always-on machine on-site
(Raspberry Pi, mini-PC, NUC), continuously watches several signals to work out
which of *your registered devices/people* are present, and publishes
arrival/departure changes to **Slack** and **GitHub**.

It's the edge companion to the sibling repos in this account:

| Repo | Role |
|------|------|
| **eero** / **eero_network_intelligence** | Cloud-side eero presence platform + dashboard (this agent reuses the same eero client + Slack card style) |
| **NextGenPresence** | Original WiFi/Bluetooth/Ring presence-tracking stack this generalises |
| **NextGenSecurity** | Alexa Echo Show + Kinesis camera streaming/recording pipeline (the `cameras` integration is the seam into it) |

## What it does

```
   ┌── collectors ──────────┐      ┌── engine ───────────┐     ┌── sinks ──────────┐
   │  wifi  (ARP / ip neigh)│      │ roster match        │     │  slack (webhook)  │
   │  bluetooth (bluetoothctl)─────▶│ arrival/departure   │────▶│  github (status)  │
   │  eero  (cloud API)     │      │ debounce (2 misses) │     │  log  (stdout)    │
   └────────────────────────┘      │ unknown-device warn │     └───────────────────┘
                                   └─────────┬───────────┘
                                             │  events
                             ┌── integrations┴──────────────┐
                             │ ring   (camera snapshot)      │
                             │ alexa  (spoken announcement)  │
                             │ cameras(feed registry → NGS)  │
                             └───────────────────────────────┘
```

- **Merges signals.** LAN scan, Bluetooth, and the eero cloud API each report
  which devices are present; the engine folds them into one view keyed by MAC.
- **Roster-based.** Presence for a *person* is derived only from devices you
  register in the roster. Everything else is an anonymous device — surfaced as a
  generic "unknown device" security warning, never resolved to an identity.
- **Debounced.** A device must miss two consecutive polls before it counts as
  *left*, which suppresses false departures from a single dropped scan.
- **Notifies on change only.** Slack Block Kit cards fire on real transitions
  (`ARRIVED` / `LEFT` / `ONLINE` / `OFFLINE` / unknown-device warning).
- **Posts to GitHub.** A private status repo gets `status/presence.json`
  (current snapshot) plus an appended `status/history.jsonl`. MACs are hashed by
  default so raw hardware addresses never enter Git history.
- **Extensible.** Ring snapshots, Alexa announcements, and a camera-feed
  registry are opt-in integrations that degrade to no-ops when not configured.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config/config.example.yaml config/config.yaml   # edit your roster
cp .env.example .env                               # add SLACK_WEBHOOK_URL
mkdir -p data

# one poll, print the snapshot
python -m propertypresence.main --config config/config.yaml --once
# continuous agent loop
python -m propertypresence.main --config config/config.yaml --run
```

`scripts/run.sh` does the venv/deps/config bootstrap for you.

### Find your devices' MACs

Run `--once` with the wifi collector on and `LOG_LEVEL=DEBUG`, or check your
eero app / router client list, then add each phone/watch to the `roster` in
`config.yaml`. MAC match is the most reliable; name substrings are a fallback.
(Note modern phones use per-network *randomised* MACs — register the address
your device shows on *your* network, and turn off "private/random address" for
that network if you want it stable.)

## Collectors

| Collector | Backend | Notes |
|-----------|---------|-------|
| `wifi` | scapy ARP sweep → falls back to `ip neigh` / `arp -a` | Active sweep needs root/`CAP_NET_RAW`; the fallback needs no privileges. Scans only the subnet you configure. |
| `bluetooth` | `bluetoothctl` discovery | Opt-in. Read `docs/PRIVACY.md` before enabling in a shared building. |
| `eero` | eero cloud API (`api-user.e2ro.com`) | Your own account; one-time login below. |

### eero login (one-time)

```bash
# interactive: sends a verification code to your eero account
python -m propertypresence.main --config config/config.yaml --eero-login
# or reuse a browser session captured from my.eero.com (Amazon-linked accounts):
EERO_SESSION='123456|abcdef...' python -m propertypresence.main \
    --config config/config.yaml --eero-login
```

## Sinks

- **Slack** — set `SLACK_WEBHOOK_URL`; verify with `--test-slack`.
- **GitHub** — set `GITHUB_TOKEN` (fine-grained PAT, contents read/write on a
  **private** repo) and `sinks.github.repo`. Keep `redact_macs: true`.
- **log** — structured stdout, always on.

## Integrations (add later)

- **Ring** — `--ring-login` once (handles 2FA), then the agent grabs a camera
  snapshot when an `ARRIVED` / `NEW_DEVICE` event fires. Requires
  `pip install ring_doorbell`.
- **Alexa** — spoken announcements via Amazon's "Notify Me" skill
  (`ALEXA_NOTIFYME_TOKEN`) or a generic webhook (`ALEXA_WEBHOOK_URL`, e.g. a
  Home Assistant `alexa_media` flow).
- **cameras** — a vendor-neutral feed registry (RTSP / Ring / Kinesis). It links
  presence events to the feed that covers an entry zone; live streaming and clip
  export are delegated to the **NextGenSecurity** cloud pipeline.

## Deploy

```bash
# Docker (host networking so it can see the LAN)
cd deploy && docker compose up --build -d

# systemd on a Pi
sudo cp -r . /opt/propertypresence && cd /opt/propertypresence
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo cp deploy/propertypresence.service /etc/systemd/system/
sudo systemctl enable --now propertypresence
```

## Tests

```bash
pip install pytest && pytest -q
```

## Privacy, consent & scope

This tool is for monitoring **your own home and the devices you register**.
Presence is intentionally roster-scoped: it is not designed to identify or
track other people, and it should not be used to surveil neighbours,
common areas, or anyone who hasn't consented. Read **[docs/PRIVACY.md](docs/PRIVACY.md)**
before enabling Bluetooth scanning or the GitHub sink — and keep any status
repo private.
