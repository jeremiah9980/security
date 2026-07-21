# Privacy, consent & responsible use

PropertyPresence works with location and network data about people. That data
is sensitive, and in many places its collection is regulated. Read this before
you deploy — especially in an apartment or any shared building.

## The design boundary

**Presence is roster-scoped.** A person is only ever reported as home/away based
on devices *you deliberately register* in `config.yaml`. The engine never turns
an anonymous device into a named person. Devices that aren't in your roster are
counted only as an anonymous "unknown device" security signal — no name, no
profile, no tracking history beyond a MAC last-seen timestamp.

This is deliberate. The tool is built to answer *"is my family home / did an
unexpected device appear on my network?"* — not *"who is near my apartment?"*

## Use it for

- Your own dwelling and the devices you and your household own.
- Your own eero / Ring / Alexa accounts.
- Automations keyed to your household's presence (lights, notifications).

## Do not use it for

- Identifying, profiling, or tracking neighbours or other residents of a
  building, or anyone passing by.
- Scanning networks, or capturing Bluetooth/WiFi from devices, that you do not
  own or administer.
- Monitoring common areas, hallways, parking, or any space shared with people
  who haven't consented.
- Covert monitoring of housemates, guests, or family members without their
  knowledge where consent is expected or legally required.

## Signal-specific cautions

- **WiFi/ARP.** Only scan a subnet on a network you operate. In an apartment,
  that's *your own* router/eero LAN — not the building's shared network, where
  you'd see other tenants' devices.
- **Bluetooth.** `bluetoothctl` discovery picks up any discoverable device in
  range, which in a dense building includes neighbours. Keep it disabled unless
  you specifically need it for your own roster devices (a watch/tag), and know
  that the range extends past your walls.
- **Cameras (Ring / NextGenSecurity).** Point cameras only at your own property.
  Recording audio and pointing cameras at shared or public space carries extra
  legal weight in many jurisdictions.

## Data handling

- **Keep the GitHub status repo private.** Presence history is a log of when
  your home is empty. `redact_macs: true` (default) hashes MACs before they're
  committed, but the *pattern* of occupancy is still sensitive — don't publish
  it.
- Secrets (`SLACK_WEBHOOK_URL`, `GITHUB_TOKEN`, eero/Ring tokens) live in `.env`
  and token files, all gitignored. Never commit them.
- The local SQLite DB, session cookies, and camera snapshots are gitignored too.
- Prefer short retention. There's no reason to keep months of occupancy history
  for a presence automation.

## Your responsibility

Laws on recording, wiretapping, and processing personal/biometric data vary by
country, state, and even building lease terms. You are responsible for using
this in a way that's lawful and respectful of the people around you. When in
doubt, narrow the scope: fewer signals, your own devices only, shorter
retention.
