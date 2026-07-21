# Architecture

PropertyPresence is a small, single-process agent built from four replaceable
part-types. Everything is plain synchronous Python; there is no framework and
no always-on server — it wakes on a timer, polls, publishes, and sleeps.

```
collectors ──▶ engine ──▶ store
                 │
                 ├──▶ sinks         (Slack, GitHub, log)
                 └──▶ integrations  (Ring, Alexa, cameras)
```

## Part-types

### Collectors (`propertypresence/collectors/`)
Turn a live signal into `Observation` records `(mac, source, name, ip, rssi, …)`.
Each is independent and fail-soft: a missing tool, absent credentials, or a
network error yields `[]` and a warning, never a crash.

- `wifi_arp` — scapy ARP sweep of the configured subnet, falling back to the
  system neighbour table (`ip neigh` / `arp -a`) when raw sockets aren't
  available.
- `bluetooth` — `bluetoothctl` discovery (opt-in).
- `eero` — the eero cloud API client (session token, auto-refresh on 401),
  mirroring the sibling `eero` repo so the two stay consistent.

`build_collectors(cfg)` instantiates only the enabled ones.

### Engine (`engine.py`)
Pure, dependency-free state machine. `evaluate(devices, observations)`:

1. Merges all observations for the poll to one record per MAC (strongest RSSI,
   first non-empty name/ip/gateway win).
2. Resolves each MAC/name against the **roster** → known device + optional
   person.
3. Emits transition events: `ARRIVED`/`ONLINE` on a device going present,
   `LEFT`/`OFFLINE` on going absent, `NEW_DEVICE` (severity `warning`) the first
   time an unregistered device appears.
4. **Debounces departures** with `offline_confirmation_polls` (default 2): a
   device must miss that many consecutive polls before it's declared gone.

Being pure makes it fully unit-testable (see `tests/test_engine.py`) with no
network or hardware.

### Sinks (`propertypresence/sinks/`)
Consume events and per-poll snapshots and publish them. `emit_event` fires on
transitions; `emit_snapshot` gets the whole current picture.

- `slack` — Block Kit cards on change, webhook URL from the environment, retry
  with backoff.
- `github` — commits `status/presence.json` (overwritten) and appends
  `status/history.jsonl` via the REST contents API; MACs hashed by default.
- `log` — structured stdout.

### Integrations (`propertypresence/integrations/`)
Optional add-ons. Two shapes: *enrichers* (contribute observations) and *actors*
(`on_event`) that react to presence.

- `ring` — camera snapshot on noteworthy events; recent motion history helper.
- `alexa` — spoken announcement via "Notify Me" or a webhook.
- `cameras` — vendor-neutral feed registry; the seam into the NextGenSecurity
  cloud streaming/clip pipeline.

## Orchestrator (`orchestrator.py`)
`Agent` wires the parts from config and owns the loop. One `poll_once()`:

```
gather observations (collectors + enrichers, each guarded)
  → engine.evaluate → (updated devices, events)
  → persist devices + events
  → dispatch each event to sinks + integration actors
  → emit snapshot to sinks
  → record poll diagnostics
```

Every fan-out is individually try/guarded so one broken sink or integration
can't stop the loop or the other sinks.

## Data model (`models.py`, `store.py`)
`Observation` (a sighting) → `Device` (roster-resolved current state) →
`PresenceEvent` (a transition). SQLite tables: `devices`, `presence_events`,
`poll_history`. MAC is the single join key and is normalised everywhere
(lower-case, colon-separated).

## Configuration (`config.py`)
YAML for structure (committed as `config.example.yaml`), environment/`.env` for
every secret. Deep-merged over built-in defaults so a short config still boots.

## Why this shape
- **Fail-soft everywhere** — a home agent runs unattended for months; a flaky
  camera or an expired eero session must degrade, not halt.
- **Roster-scoped by construction** — the identity boundary lives in one place
  (`roster.py`), which is also the privacy boundary.
- **Reuses proven pieces** — the eero client and Slack card format come straight
  from the existing `eero` repo, so behaviour matches the cloud platform.
