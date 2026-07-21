"""Roster matching tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from propertypresence.roster import Roster

R = Roster.from_config([
    {"name": "Jere iPhone", "person": "Jeremiah",
     "match": {"macs": ["AA:BB:CC:DD:EE:FF"], "names": ["jere iphone"]}},
    {"name": "TV", "match": {"names": ["samsung"]}},
])


def test_match_by_mac_case_insensitive():
    e = R.resolve("aa:bb:cc:dd:ee:ff", None)
    assert e and e.person == "Jeremiah"


def test_match_by_name_substring():
    e = R.resolve("00:00:00:00:00:01", "Samsung Frame TV")
    assert e and e.label == "TV" and e.person is None


def test_unknown_returns_none():
    assert R.resolve("de:ad:be:ef:00:01", "random") is None


def test_people_list_is_unique_and_ordered():
    assert R.people == ["Jeremiah"]
