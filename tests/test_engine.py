"""Engine tests: arrival, debounced departure, unknown-device warning."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from propertypresence.engine import PresenceEngine, people_home
from propertypresence.models import (ARRIVED, LEFT, NEW_DEVICE, Observation)
from propertypresence.roster import Roster

ROSTER = Roster.from_config([
    {"name": "Jere iPhone", "person": "Jeremiah",
     "match": {"macs": ["aa:bb:cc:dd:ee:ff"]}, "notify": True},
])


def _obs(mac, source="wifi", name=None):
    return Observation(mac=mac, source=source, name=name)


def test_person_arrival_then_debounced_departure():
    eng = PresenceEngine(ROSTER, offline_confirmation_polls=2)
    devices = {}

    # poll 1: person device seen -> ARRIVED
    devices, events = eng.evaluate(devices, [_obs("AA:BB:CC:DD:EE:FF")])
    assert [e.type for e in events] == [ARRIVED]
    assert events[0].person == "Jeremiah"
    assert people_home(devices) == ["Jeremiah"]

    # poll 2: still seen -> no event
    devices, events = eng.evaluate(devices, [_obs("aa:bb:cc:dd:ee:ff")])
    assert events == []

    # poll 3: missing once -> no event yet (grace window)
    devices, events = eng.evaluate(devices, [])
    assert events == []
    assert people_home(devices) == ["Jeremiah"]  # still counted home

    # poll 4: missing twice -> LEFT fires
    devices, events = eng.evaluate(devices, [])
    assert [e.type for e in events] == [LEFT]
    assert events[0].person == "Jeremiah"
    assert events[0].session_seconds is not None
    assert people_home(devices) == []


def test_unknown_device_raises_warning_once():
    eng = PresenceEngine(ROSTER, offline_confirmation_polls=2)
    devices = {}
    devices, events = eng.evaluate(devices, [_obs("11:22:33:44:55:66", name="stranger")])
    assert [e.type for e in events] == [NEW_DEVICE]
    assert events[0].severity == "warning"
    assert events[0].person is None  # never resolved to an identity

    # seen again next poll -> not a new device, no duplicate warning
    devices, events = eng.evaluate(devices, [_obs("11:22:33:44:55:66")])
    assert events == []


def test_mac_normalisation_matches_roster():
    eng = PresenceEngine(ROSTER, offline_confirmation_polls=1)
    devices = {}
    # dashed + upper form should still match the roster entry
    devices, events = eng.evaluate(devices, [_obs("AA-BB-CC-DD-EE-FF")])
    assert events[0].type == ARRIVED
