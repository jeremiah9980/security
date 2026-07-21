# security

Local presence and network scanning tool for property monitoring.

## Presence agent

`presence_agent.py` runs on a local machine and continuously scans:
- local network neighbors (ARP/IP neighbor table)
- nearby Bluetooth devices
- system presence (logged-in users and active interfaces)

Each scan produces a JSON snapshot containing detected devices and inferred onsite people.

### Run

```bash
python presence_agent.py --interval 30
```

### Optional identity mapping

You can map known devices to people using a JSON file:

```json
{
  "mac_to_person": {
    "aa:bb:cc:dd:ee:ff": "owner"
  },
  "name_to_person": {
    "Alice Phone": "alice"
  }
}
```

Then run:

```bash
python presence_agent.py --identity-map /path/to/identity-map.json
```

### Write JSONL output

```bash
python presence_agent.py --output ./presence.jsonl
```
