# NetBox import set — Blackwood University RCC demo

Clean, internally consistent version of the same fictional estate described by
the four messy handover spreadsheets one directory up. Target: **NetBox 4.x**
(tested against the 4.1 / 4.2 import forms).

The five planted discrepancies from the messy sheets are **resolved to
canonical truth** here — see `gen_demo.py`:

| # | Messy sheets | This import set |
|---|---|---|
| 1 | `wr-gpu-004` in rack H3 *and* H4 | H4, position 37 |
| 2 | `mdc-vmhost-03` Active *and* Decommissioned | status `decommissioning`, still racked |
| 3 | `10.20.0.0/24` "old lab net", reclaim? | omitted entirely |
| 4 | ghost node `wr-cn-013` in cabling | omitted (cluster stops at `wr-cn-012`) |
| 5 | VLAN 60 / `10.72.3.0/24` overlapping VLAN 50 | only VLAN 50 + `10.72.2.0/23` |

Everything else (57 devices, 7 racks, ~290 interfaces, ~130 IPs, ~118 cables)
is one coherent topology.

---

## Contents

```
csv/
  01_manufacturers.csv    08_vlans.csv
  02_device_types.csv     09_prefixes.csv
  05a_rack_types.csv      (rack types, NetBox 4.3+; loaded before 06_racks)
  12a_tags .. 20_wan_ip_addresses.csv   WAN / BGP (see below)
  21_power_panels .. 25_power_cables.csv   power (see below)
  26_bgp_sessions.csv     eBGP sessions; needs the netbox-bgp plugin, skipped without it
  03_device_roles.csv     10_interfaces.csv
  04_sites.csv            11_ip_addresses.csv
  05_locations.csv        12_cables.csv
  06_racks.csv
  07_devices.csv
load_netbox.py            # pushes the CSVs via the REST API, idempotently
floorplans.py             # creates the two Visual Explorer floor plans (see below)
ndx_import.py             # aligns device types with the NDX catalog and imports them
verify_netbox.py          # read-only: compares NetBox with the CSVs
cleanup_netbox.py         # deletes objects that are not in the planned data
```

The numeric prefixes are the **import order** — each file depends only on
files before it.

---

## Option A — web UI bulk import

For each file, in order:

1. Go to the matching list view and click **Import** (e.g. *Devices → Import*).
2. Paste the CSV or upload the file.
3. Submit.

List views, in order:

| File | Import at |
|---|---|
| 01 | Organization → Manufacturers |
| 02 | Devices → Device Types |
| 03 | Organization → Device Roles |
| 04 | Organization → Sites |
| 05 | Organization → Locations |
| 06 | Devices → Racks |
| 07 | Devices → Devices |
| 08 | IPAM → VLANs |
| 09 | IPAM → Prefixes |
| 10 | Devices → Interfaces |
| 11 | IPAM → IP Addresses |
| 12 | Connections → Cables |

## Option B — API loader

```bash
pip install pynetbox
export NETBOX_URL=https://netbox.your-demo.edu
export NETBOX_TOKEN=<a token with write scope>

python3 load_netbox.py --dry-run     # show what it would create
python3 load_netbox.py               # create everything missing
python3 load_netbox.py --wipe        # remove every demo object again
```

The loader matches every object on a natural key (slug / name / vid / prefix)
and only creates what's missing, so it's safe to run repeatedly and safe to
stop and resume. `--wipe` deletes only the objects named in the CSVs
(device types, manufacturers and roles are left in place — they're harmless
and usually shared). Point it at a throwaway NetBox instance regardless.

---

## Regenerating

```bash
cd ..
python3 gen_netbox_import.py
```

Reads `../rcc_model.py` (the single source of truth shared with the messy-sheet
generator) and rewrites `csv/`. Deterministic. The script self-validates:
device-type coverage, rack fit, every cable endpoint has an interface, no
interface terminates two cables, every IP falls inside a prefix, every
prefix-referenced VLAN exists.

---

## Version notes

- **NetBox 3.7 / late 3.x:** rename the `role` column to `device_role` in
  `07_devices.csv`. Everything else is unchanged.
- **Cables (`12_cables.csv`):** `side_a_type` / `side_b_type` are given as
  `dcim.interface`. If your build's import form rejects that, use the bare
  `interface`.
- **Interface VLANs:** not populated. Access/trunk assignment per interface
  is left out to keep the set readable; add a `mode` + `untagged_vlan` /
  `tagged_vlans` column to `10_interfaces.csv` if you want it (NetBox ≥ 4.4
  supports VLAN assignment on interface bulk import).
- **Console & power cabling:** out of scope. The messy `cabling_and_connections.xlsx`
  has the Console/Serial and Power tabs; modelling them in NetBox needs
  console-server-port and power-outlet components on synthetic PDU / terminal
  server devices. Add PDUs as devices (role "PDU"), give them `power-outlets`,
  give each server `power-ports`, then extend `12_cables.csv` with
  `dcim.powerport` ↔ `dcim.poweroutlet` rows.
- **`192.0.2.0/24`** is TEST-NET-1 (RFC 5737) standing in for the public
  Science-DMZ range — safe to import anywhere.

---

## Floor plans (NetBox Visual Explorer, Cloud Premium)

Racks reference a rack type (`05a_rack_types.csv`, 600 x 1200 mm outer), so
Visual Explorer draws them to scale. After `load_netbox.py`:

```bash
python3 floorplans.py --dry-run
python3 floorplans.py   # floor plan + layer per location, then places each rack
```

The script uses the physical-geometry API (`/api/plugins/physical-geometry/`),
which NetBox describes as under active development. Everything is in cm. Sizes
and rack positions are at the top of `floorplans.py`. If racks land off, nudge
them in Visual Explorer's edit mode and click **Save**. Without the script: pick
the site in Visual Explorer, **Create Floorplan**, switch to edit mode, drag the
racks from the unplaced panel, **Save**. Needs NetBox 4.3+ for rack types.
Racks that already exist are skipped by the loader, so they will not gain a
rack type on re-run.

---

## WAN and BGP

Fictional: Blackwood is AS64500 (RFC 5398 documentation range), announcing the
Science DMZ `192.0.2.0/24` from both sites. Providers: WRRN (AS64501, R&E and
Internet2), Cascade Fiber (AS64502, transit), Lakeshore (AS64503, backup transit).
Five circuits (one planned), each terminating on a border firewall or core
switch. `load_netbox.py` creates, in order: tags (`12a`), providers (`13`),
provider networks (`14`), circuit types (`15`), ASNs (`16`), circuits (`17`),
terminations (`18`), circuit-to-interface cables (`19`), and the /31 peering IPs (`20`).

Core NetBox has no BGP session object, so each peering is the /31 IP pair on the
handoff, tagged `bgp-peer`, with custom fields `bgp_peer_asn` and `bgp_local_asn`
(created by the loader). Filter IP Addresses by tag `bgp-peer` for the BGP table.
Sites get latitude/longitude for map views. Needs NetBox 4.2+ for circuit terminations.
The messy sheets carry the same data on new `WAN circuits` and `BGP peers` tabs
(RCC_IP_and_Networks.xlsx), plus WAN rows in Subnets and the cabling Ethernet tab.

## Power

`21_power_panels` .. `25_power_cables.csv`, loaded by `load_netbox.py` (`load_power`):

- 4 power panels (A and B side per site) and 14 power feeds, one A and one B per rack.
  Default feed is 208 V single-phase 30 A; `WRDC-H3` (the GPU rack) is 208 V 3-phase 60 A.
- 14 rack PDUs (0U, role `PDU`, type `Generic Rack PDU 0U 24xC13 6xC19`) with an `Input`
  power port and 30 outlets, each outlet linked to the input so feed utilization rolls up.
- 114 PSU power ports (`PSU1`/`PSU2` on every device) with `maximum_draw` (PSU rating)
  and `allocated_draw` (half the typical load). Per-model watts are in `POWER_W` in `rcc_model.py`.
- 114 PSU-to-outlet cables plus 14 PDU-to-feed cables (red = A side, blue = B side).
  GPU nodes use C19 outlets, everything else C13.

In NetBox, open a feed (Connectivity > Power Feeds) to see its utilization, or a rack for
its power panel. Full load on one `WRDC-H3` feed (18.4 kW) exceeds the 80% continuous rating
(17.3 kW), which is the "what if the A side drops" talking point. The Power tab in
`cabling_and_connections.xlsx` carries the same PSU-to-outlet map with the planted mess.

## BGP sessions

`26_bgp_sessions.csv` holds one eBGP session per live circuit (4), loaded by `load_bgp()` into the
netbox-bgp plugin (`/api/plugins/bgp/session/`): device, site, the local and remote /31 addresses
and the local and remote ASNs. It runs after the WAN section and skips with a message if the
plugin API is unreachable. The `bgp-peer` IP tags and custom fields stay as they were.

## Checking NetBox against the plan

`verify_netbox.py` is read-only. It compares NetBox with the CSVs (device types, sites, racks,
devices, interfaces, VLANs, prefixes, IPs, circuits, ASNs, power, and every cable) and prints
what is missing, extra or different. `cleanup_netbox.py` removes extra top-level objects.
`ndx_import.py` aligns the device types with the NDX catalog (`--status` shows the components).
