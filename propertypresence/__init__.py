"""PropertyPresence — a local presence & network intelligence agent.

Runs on an always-on machine at a property (Raspberry Pi, mini-PC, NUC),
merges several presence signals (LAN scan, Bluetooth, the eero cloud API),
resolves them against a *roster of your own known devices*, and publishes
arrival/departure changes to Slack and GitHub.

Design principle: presence is derived from devices YOU register in the
roster (household members, your own hardware) and accounts YOU own. It is
not a tool for identifying or tracking non-consenting third parties. See
docs/PRIVACY.md.
"""

__version__ = "0.1.0"
