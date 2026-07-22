import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import presence_agent


class PresenceAgentTests(unittest.TestCase):
    def test_scan_network_devices_parses_ip_neigh(self):
        scanner = presence_agent.PresenceScanner(command_runner=lambda _: "192.168.1.5 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE")

        devices = scanner.scan_network_devices()

        self.assertEqual(devices, [{"ip": "192.168.1.5", "mac": "aa:bb:cc:dd:ee:ff", "state": "REACHABLE"}])

    def test_scan_bluetooth_devices_parses_bluetoothctl(self):
        scanner = presence_agent.PresenceScanner(command_runner=lambda _: "Device 11:22:33:44:55:66 Alice Phone")

        devices = scanner.scan_bluetooth_devices()

        self.assertEqual(devices, [{"mac": "11:22:33:44:55:66", "name": "Alice Phone"}])

    def test_scan_once_merges_people_from_mappings(self):
        responses = {
            ("ip", "neigh"): "192.168.1.8 dev wlan0 lladdr aa:aa:aa:aa:aa:aa REACHABLE",
            ("bluetoothctl", "devices"): "Device bb:bb:bb:bb:bb:bb Guest Tag",
            ("who",): "operator pts/0 2026-07-21 12:00",
            ("ip", "-o", "link", "show", "up"): "1: lo: <LOOPBACK,UP> mtu 65536\n2: wlan0: <BROADCAST,UP> mtu 1500",
        }

        def runner(command):
            return responses.get(tuple(command), "")

        scanner = presence_agent.PresenceScanner(
            command_runner=runner,
            identity_map=presence_agent.IdentityMap(
                mac_to_person={"aa:aa:aa:aa:aa:aa": "owner"},
                name_to_person={"Guest Tag": "guest"},
            ),
        )

        snapshot = scanner.scan_once()

        self.assertEqual(snapshot["onsite_people"], ["guest", "operator", "owner"])

    def test_run_writes_jsonl_output(self):
        fake_snapshot = {
            "timestamp": "2026-07-21T00:00:00+00:00",
            "network_devices": [],
            "bluetooth_devices": [],
            "system_presence": {"hostname": "host", "logged_in_users": [], "active_interfaces": []},
            "onsite_people": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "presence.jsonl"

            with patch("presence_agent.PresenceScanner") as scanner_class:
                scanner_class.return_value.scan_once.return_value = fake_snapshot
                result = presence_agent.run(["--iterations", "1", "--interval", "1", "--output", str(output_path)])

            self.assertEqual(result, 0)
            data = output_path.read_text(encoding="utf-8").strip()
            self.assertEqual(json.loads(data), fake_snapshot)


if __name__ == "__main__":
    unittest.main()
