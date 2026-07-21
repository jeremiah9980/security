#!/usr/bin/env python3
"""Local presence and network scanning agent for properties."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


CommandRunner = Callable[[list[str]], str]


@dataclass(frozen=True)
class IdentityMap:
    mac_to_person: dict[str, str]
    name_to_person: dict[str, str]


class PresenceScanner:
    def __init__(self, command_runner: CommandRunner | None = None, identity_map: IdentityMap | None = None) -> None:
        self.command_runner = command_runner or self._run_command
        self.identity_map = identity_map or IdentityMap(mac_to_person={}, name_to_person={})

    def _run_command(self, command: list[str]) -> str:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)
        except (FileNotFoundError, subprocess.SubprocessError):
            return ""
        return result.stdout.strip()

    def _read_first_available(self, commands: list[list[str]]) -> str:
        for command in commands:
            output = self.command_runner(command)
            if output:
                return output
        return ""

    def scan_network_devices(self) -> list[dict[str, str]]:
        output = self._read_first_available([["ip", "neigh"], ["arp", "-an"]])
        devices: list[dict[str, str]] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("?") and "(" in line and ")" in line and " at " in line:
                ip = line.split("(", 1)[1].split(")", 1)[0]
                mac = line.split(" at ", 1)[1].split()[0]
                state = line.split()[-1]
            else:
                parts = line.split()
                if len(parts) < 5 or "lladdr" not in parts:
                    continue
                ip = parts[0]
                mac = parts[parts.index("lladdr") + 1]
                state = parts[-1]
            devices.append({"ip": ip, "mac": mac.lower(), "state": state})
        return devices

    def scan_bluetooth_devices(self) -> list[dict[str, str]]:
        output = self._read_first_available([["bluetoothctl", "devices"], ["hcitool", "scan"]])
        devices: list[dict[str, str]] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("Device "):
                parts = line.split(maxsplit=2)
                if len(parts) < 2:
                    continue
                mac = parts[1].lower()
                name = parts[2] if len(parts) == 3 else mac
            else:
                parts = line.split(maxsplit=1)
                if len(parts) < 2 or ":" not in parts[0]:
                    continue
                mac = parts[0].lower()
                name = parts[1]
            devices.append({"mac": mac, "name": name})
        return devices

    def scan_system_presence(self) -> dict[str, object]:
        users_output = self._read_first_available([["who"]])
        users = sorted({line.split()[0] for line in users_output.splitlines() if line.split()})

        interfaces_output = self._read_first_available([["ip", "-o", "link", "show", "up"]])
        interfaces: list[str] = []
        for line in interfaces_output.splitlines():
            parts = line.split(":", maxsplit=2)
            if len(parts) >= 2:
                interfaces.append(parts[1].strip())

        return {
            "hostname": socket.gethostname(),
            "logged_in_users": users,
            "active_interfaces": sorted(set(interfaces)),
        }

    def scan_once(self) -> dict[str, object]:
        network_devices = self.scan_network_devices()
        bluetooth_devices = self.scan_bluetooth_devices()
        system_presence = self.scan_system_presence()

        people = set(system_presence["logged_in_users"])
        for device in network_devices:
            person = self.identity_map.mac_to_person.get(device["mac"])
            if person:
                people.add(person)
        for device in bluetooth_devices:
            person = self.identity_map.mac_to_person.get(device["mac"])
            if person:
                people.add(person)
            mapped_from_name = self.identity_map.name_to_person.get(device["name"])
            if mapped_from_name:
                people.add(mapped_from_name)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_devices": network_devices,
            "bluetooth_devices": bluetooth_devices,
            "system_presence": system_presence,
            "onsite_people": sorted(people),
        }


def load_identity_map(path: Path | None) -> IdentityMap:
    if path is None:
        return IdentityMap(mac_to_person={}, name_to_person={})

    payload = json.loads(path.read_text(encoding="utf-8"))
    return IdentityMap(
        mac_to_person={k.lower(): v for k, v in payload.get("mac_to_person", {}).items()},
        name_to_person=payload.get("name_to_person", {}),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuously scan local network/Bluetooth/system presence.")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between scans (default: 30)")
    parser.add_argument("--iterations", type=int, default=0, help="Number of scans before exit (0 = run forever)")
    parser.add_argument("--identity-map", type=Path, help="Optional JSON file mapping devices to people")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSONL output file. If omitted, writes JSON snapshots to stdout.",
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.interval <= 0:
        raise ValueError("--interval must be greater than 0")
    if args.iterations < 0:
        raise ValueError("--iterations must be 0 or greater")

    scanner = PresenceScanner(identity_map=load_identity_map(args.identity_map))
    scan_count = 0

    while True:
        snapshot = scanner.scan_once()
        line = json.dumps(snapshot, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("a", encoding="utf-8") as output_file:
                output_file.write(line + "\n")
        else:
            print(line)

        scan_count += 1
        if args.iterations and scan_count >= args.iterations:
            return 0
        time.sleep(args.interval)


def main() -> int:
    try:
        return run(sys.argv[1:])
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
