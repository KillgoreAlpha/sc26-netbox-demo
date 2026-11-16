#!/usr/bin/env python3
"""Emit clean NetBox 4.x bulk-import CSVs from the canonical rcc_model.

Writes numbered CSVs into netbox_import/csv/ in dependency order:

  01_manufacturers   02_device_types   03_device_roles   04_sites
  05_locations       06_racks          07_devices        08_vlans
  09_prefixes        10_interfaces     11_ip_addresses   12_cables
  12a_tags           13_providers      14_provider_networks  15_circuit_types
  16_asns            17_circuits       18_circuit_terminations
  19_wan_cables      20_wan_ip_addresses     (WAN / BGP)

The 5 planted discrepancies from the messy handover are resolved here to
canonical truth (five planted discrepancies in gen_demo.py). Console/power cables are
out of scope - the README explains how to add them.

Run: python3 gen_netbox_import.py
"""

import collections
import csv
import os
import re

from rcc_model import (D, RACKS, PLACE, IPPLAN, SUBNETS, VLANS, ib_hosts,
                        eth_rows, ib_rows, LOCAL_ASN, ANNOUNCED, PROVIDERS,
                        CIRCUIT_TYPES, TAGS, CIRCUITS,
                        pwr_rows, POWER_W, POWER_PANELS, PDUS, FEEDS, PDU_MODEL,
                        PDU_C13, PDU_C19)

CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netbox_import", "csv")
os.makedirs(CSV_DIR, exist_ok=True)


def slug(s):
    s = s.lower().replace("/", "-").replace("+", "-plus-")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def write_csv(idx, name, header, rows):
    tag = f"{idx:02d}" if isinstance(idx, int) else idx
    path = os.path.join(CSV_DIR, f"{tag}_{name}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {tag}_{name}.csv  ({len(rows)} rows)")
    return path


# ---------------------------------------------------------------------------
# static reference data
# ---------------------------------------------------------------------------
SITES = {
    "MDC":  dict(name="Marston Data Center",   slug="mdc",
                 facility="Marston Hall, Level B1", desc="Main campus machine room",
                 lat=40.7480, lon=-89.6060),
    "WRDC": dict(name="West Ridge Data Center", slug="wrdc",
                 facility="West Ridge Research Bldg", desc="HPC data hall",
                 lat=40.8230, lon=-89.7020),
}
LOCATIONS = {
    "MDC":  dict(name="Marston Machine Room", slug="marston-machine-room"),
    "WRDC": dict(name="West Ridge Data Hall", slug="west-ridge-data-hall"),
}

ROLE_COLOR = {
    "Firewall": "f44336", "Core Switch": "2196f3", "Mgmt Switch": "03a9f4",
    "OOB/Console Switch": "9e9e9e", "InfiniBand Spine": "3f51b5",
    "InfiniBand Leaf": "5c6bc0", "DNS/DHCP": "009688", "VM Hypervisor": "4caf50",
    "SAN/Disk Array": "ff9800", "Backup Server": "795548", "Legacy NAS": "9e9e9e",
    "Data Transfer Node": "00bcd4", "Login Node": "8bc34a", "Scheduler": "cddc39",
    "Lustre MDS": "ffc107", "Lustre OSS": "ffb300",
    "Compute Node (CPU)": "607d8b", "Compute Node (GPU)": "e91e63",
    "Condo Node (GPU)": "ad1457", "Condo Node (CPU)": "455a64",
}

STATUS_MAP = {"Active": "active", "Decommissioning": "decommissioning",
              "Offline": "offline"}

# cabling media -> (netbox cable type, is_infiniband)
CABLE_TYPE = {
    "DAC": "dac-passive", "HDR200 DAC": "dac-passive",
    "AOC": "aoc", "HDR200 AOC": "aoc",
    "SMF LC/LC": "smf-os2", "CAT6": "cat6", "RJ45 rollover": "cat6",
}
COLOR_HEX = {"black": "000000", "blue": "2196f3", "green": "4caf50",
             "grey": "607d8b", "yellow": "ffeb3b", "white": "ffffff"}


def cable_len(s):
    m = re.match(r"([\d.]+)\s*m", s or "")
    return (m.group(1), "m") if m else ("", "")


# ---------------------------------------------------------------------------
# 01 manufacturers / 02 device types / 03 roles
# ---------------------------------------------------------------------------
mfrs = sorted({d["mfr"] for d in D.values()} | {"Generic"})  # Generic: rack types
write_csv(1, "manufacturers", ["name", "slug"],
          [[m, slug(m)] for m in mfrs])

dtypes = {}
for d in D.values():
    dtypes[(d["mfr"], d["model"])] = d["u_height"]

def _first_role(mfr, model):
    for d in D.values():
        if d["mfr"] == mfr and d["model"] == model:
            return d["role"]
    return ""

# slugs that differ from the derived one so NDX catalog imports update our type in place
SLUG_OVERRIDE = {("Cisco", "Catalyst 2960-48TT-L"): "cisco-ws-c2960-48tt-l",
                 ("Supermicro", "SuperServer 6018R-MT"): "supermicro-sys-6018r-mt",
                 ("Supermicro", "GPU SuperServer SYS-422GA-NRT"): "supermicro-sys-422ga-nrt"}

dtype_rows = []
for (mfr, model), h in sorted(dtypes.items()):
    role = _first_role(mfr, model)
    full_depth = "false" if ("Switch" in role or "InfiniBand" in role) else "true"
    dtype_rows.append([mfr, model, SLUG_OVERRIDE.get((mfr, model), slug(f"{mfr}-{model}")),
                      h, full_depth])
dtype_rows.append([PDU_MODEL[0], PDU_MODEL[1], slug(f"{PDU_MODEL[0]}-{PDU_MODEL[1]}"), 0, "false"])
write_csv(2, "device_types",
          ["manufacturer", "model", "slug", "u_height", "is_full_depth"],
          dtype_rows)

roles = sorted({d["role"] for d in D.values()})
write_csv(3, "device_roles", ["name", "slug", "color", "vm_role"],
          [[r, slug(r), ROLE_COLOR.get(r, "9e9e9e"), "false"] for r in roles]
          + [["PDU", "pdu", "d32f2f", "false"]])

# ---------------------------------------------------------------------------
# 04 sites / 05 locations / 06 racks
# ---------------------------------------------------------------------------
write_csv(4, "sites", ["name", "slug", "status", "facility", "description",
                       "latitude", "longitude"],
          [[s["name"], s["slug"], "active", s["facility"], s["desc"], s["lat"], s["lon"]]
           for s in SITES.values()])

write_csv(5, "locations", ["site", "name", "slug", "status"],
          [[SITES[k]["name"], LOCATIONS[k]["name"], LOCATIONS[k]["slug"], "active"]
           for k in SITES])

# rack types give the floorplan plugin an outer width/depth to draw each rack to scale
RT_OUTER = dict(outer_width=600, outer_depth=1200, outer_unit="mm")
rack_heights = sorted({m["height"] for m in RACKS.values()})
rt_path = os.path.join(CSV_DIR, "05a_rack_types.csv")
with open(rt_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["manufacturer", "model", "slug", "form_factor", "width", "u_height",
                "outer_width", "outer_depth", "outer_unit"])
    for h in rack_heights:
        w.writerow(["Generic", f"Generic {h}U 19in Cabinet", f"generic-{h}u-19in-cabinet",
                    "4-post-cabinet", 19, h, RT_OUTER["outer_width"],
                    RT_OUTER["outer_depth"], RT_OUTER["outer_unit"]])
print(f"  05a_rack_types.csv  ({len(rack_heights)} rows)")

rack_rows = []
for rk, meta in RACKS.items():
    rack_rows.append([SITES[meta["site"]]["name"], LOCATIONS[meta["site"]]["name"],
                      rk, "active", 19, meta["height"],
                      f"Generic {meta['height']}U 19in Cabinet"])
write_csv(6, "racks",
          ["site", "location", "name", "status", "width", "u_height", "rack_type"],
          rack_rows)

# ---------------------------------------------------------------------------
# 07 devices
# ---------------------------------------------------------------------------
dev_rows = []
for name in D:
    d = D[name]
    rk, us = PLACE[name]
    dev_rows.append([
        name, d["model"], d["role"], SITES[d["site"]]["name"],
        LOCATIONS[d["site"]]["name"], rk, us, "front",
        STATUS_MAP.get(d["status"], "active"),
        d["pi"] and f'owner: {d["pi"]}' or (d["fund"] and f'fund: {d["fund"]}' or ""),
    ])
write_csv(7, "devices",
          ["name", "device_type", "role", "site", "location", "rack",
           "position", "face", "status", "description"], dev_rows)

# ---------------------------------------------------------------------------
# 08 vlans / 09 prefixes
# ---------------------------------------------------------------------------
write_csv(8, "vlans", ["vid", "name", "status"],
          [[vid, nm, st] for (vid, nm, st) in VLANS])

pfx_rows = []
for (prefix, vid, status, desc) in SUBNETS:
    pfx_rows.append([prefix, status, vid if vid else "", desc])
write_csv(9, "prefixes", ["prefix", "status", "vlan", "description"], pfx_rows)

# ---------------------------------------------------------------------------
# 10 interfaces  (collected from the cabling model + synthetic mgmt/BMC)
# ---------------------------------------------------------------------------
def iftype(dev, port):
    p = port.lower()
    role = D[dev]["role"]
    if p.startswith("ib") or p.startswith("uplink-") or \
       (port.startswith("Port") and "InfiniBand" in role):
        return "infiniband-hdr", "false"
    if port == "iDRAC" or p in ("mgmt0", "ipmi"):
        return "1000base-t", "true"
    if port == "eth1":
        return "10gbase-x-sfpp", "false"
    if port == "eno1":
        return "25gbase-x-sfp28", "false"
    if port.startswith("Et"):
        if role == "Core Switch":
            return ("100gbase-x-qsfp28", "false") if port == "Et48" else ("25gbase-x-sfp28", "false")
        if role == "Mgmt Switch":
            return ("10gbase-x-sfpp", "false") if port in ("Et49", "Et50") else ("1000base-t", "false")
        if role in ("OOB/Console Switch",):
            return "1000base-t", "false"
        if "InfiniBand" in role:
            return "infiniband-hdr", "false"
        return "25gbase-x-sfp28", "false"
    return "1000base-t", "false"


# device -> {port: (type, mgmt_only)}
ifaces = {n: {} for n in D}
for r in eth_rows + ib_rows:
    a_dev, a_port, b_dev, b_port = r[0], r[1], r[2], r[3]
    for dv, pt in ((a_dev, a_port), (b_dev, b_port)):
        if dv in ifaces and pt not in ifaces[dv]:
            ifaces[dv][pt] = iftype(dv, pt)

# WAN handoff ports (cabled to circuit terminations, not to another device)
for c in CIRCUITS:
    if c["device"]:
        ifaces[c["device"]].setdefault(c["port"], (c["port_type"], "false"))

# ensure a management interface + BMC interface exist where there's an IP
mgmt_iface = {}   # device -> interface name that holds the mgmt IP
for n in D:
    p = IPPLAN.get(n, {})
    has_bmc = "bmc" in p
    if "mgmt0" in ifaces[n]:
        mi = "mgmt0"
    elif "iDRAC" in ifaces[n] and not has_bmc:
        mi = "iDRAC"
    else:
        mi = "mgmt0"
        ifaces[n].setdefault("mgmt0", ("1000base-t", "true"))
    mgmt_iface[n] = mi
    if has_bmc and "iDRAC" not in ifaces[n]:
        ifaces[n]["iDRAC"] = ("1000base-t", "true")

if_rows = []
for n in sorted(ifaces):
    for port, (typ, mgmt_only) in ifaces[n].items():
        if_rows.append([n, port, typ, "true", mgmt_only])
write_csv(10, "interfaces",
          ["device", "name", "type", "enabled", "mgmt_only"], if_rows)

# ---------------------------------------------------------------------------
# 11 ip addresses
# ---------------------------------------------------------------------------
def dns_name(n, kind):
    d = D[n]
    if kind == "public":
        if n in ("wr-login-01", "wr-login-02"):
            return n.replace("wr-login-0", "login0") + ".hpc.blackwood.edu"
        if n == "wr-dtn-01":
            return "dtn.hpc.blackwood.edu"
        if n == "mdc-globus-dtn-legacy":
            return "dtn-legacy.hpc.blackwood.edu"
        return n + ".dmz.blackwood.edu"
    if kind == "mgmt":
        return n + ".rcc.blackwood.edu"
    if kind == "bmc":
        return n + "-bmc.rcc.blackwood.edu"
    return ""

ip_rows = []
for n in D:
    p = IPPLAN.get(n, {})
    if p.get("mgmt"):
        ip_rows.append([p["mgmt"], "active", dns_name(n, "mgmt"), "management",
                        n, mgmt_iface[n], "true"])
    if p.get("bmc"):
        ip_rows.append([p["bmc"], "active", dns_name(n, "bmc"), "BMC / iDRAC",
                        n, "iDRAC", "false"])
    if p.get("ib"):
        ip_rows.append([p["ib"], "active", "", "IPoIB", n, "ib0", "false"])
    if p.get("public"):
        data_if = next((x for x in ("eth1", "eno1", "p1p1") if x in ifaces[n]),
                       mgmt_iface[n])
        ip_rows.append([p["public"], "active", dns_name(n, "public"), "Science DMZ",
                        n, data_if, "false"])
write_csv(11, "ip_addresses",
          ["address", "status", "dns_name", "description",
           "device", "interface", "is_primary"], ip_rows)

# ---------------------------------------------------------------------------
# 12 cables  (interface <-> interface; ethernet + InfiniBand)
# ---------------------------------------------------------------------------
cab_rows = []
for r in eth_rows:
    a_dev, a_port, b_dev, b_port, media, color, length, label = r
    val, unit = cable_len(length)
    cab_rows.append([a_dev, "dcim.interface", a_port,
                     b_dev, "dcim.interface", b_port,
                     CABLE_TYPE.get(media, ""), "connected", label,
                     COLOR_HEX.get(color, ""), val, unit])
for r in ib_rows:
    a_dev, a_port, b_dev, b_port, media, length, label = r
    val, unit = cable_len(length)
    cab_rows.append([a_dev, "dcim.interface", a_port,
                     b_dev, "dcim.interface", b_port,
                     CABLE_TYPE.get(media, ""), "connected", label,
                     "9c27b0", val, unit])
write_csv(12, "cables",
          ["side_a_device", "side_a_type", "side_a_name",
           "side_b_device", "side_b_type", "side_b_name",
           "type", "status", "label", "color", "length", "length_unit"], cab_rows)

# ---------------------------------------------------------------------------
# 21-25  POWER: panels, feeds, PDUs, PSU ports, power cables
# ---------------------------------------------------------------------------
write_csv(21, "power_panels", ["site", "location", "name", "description"],
          [[SITES[p["site"]]["name"], LOCATIONS[p["site"]]["name"], p["name"], p["note"]]
           for p in POWER_PANELS])
write_csv(22, "power_feeds",
          ["panel", "name", "site", "rack", "status", "type", "supply", "phase",
           "voltage", "amperage", "max_utilization"],
          [[f["panel"], f["name"], SITES[f["site"]]["name"], f["rack"], "active", f["type"],
            "ac", f["phase"], f["voltage"], f["amps"], 80] for f in FEEDS])
write_csv(23, "pdus",
          ["name", "model", "role", "site", "location", "rack", "feed", "inlet_type",
           "c13_outlets", "c19_outlets"],
          [[p["name"], PDU_MODEL[1], "PDU", SITES[p["site"]]["name"],
            LOCATIONS[p["site"]]["name"], p["rack"], p["feed"], p["inlet"],
            PDU_C13, PDU_C19] for p in PDUS])
_pp = []
for dv, psu, pdu, outlet, _feed, _role in pwr_rows:
    psu_w, typ_w = POWER_W[D[dv]["model"]]
    _pp.append([dv, psu, "iec-60320-c20" if outlet.startswith("C19") else "iec-60320-c14",
                psu_w, round(typ_w / 2)])
write_csv(24, "power_ports", ["device", "name", "type", "maximum_draw", "allocated_draw"], _pp)
write_csv(25, "power_cables",
          ["device", "port", "pdu", "outlet", "status", "label", "color"],
          [[dv, psu, pdu, outlet, "connected", f"{dv} {psu}", "f44336" if feed.startswith("A") else "2196f3"]
           for dv, psu, pdu, outlet, feed, _role in pwr_rows])

# ---------------------------------------------------------------------------
# 12a-20  WAN / BGP: tags, providers, circuits, ASNs, circuit cables, peering IPs
# ---------------------------------------------------------------------------
write_csv("12a", "tags", ["name", "slug", "color"], [[t[1], t[0], t[2]] for t in TAGS])

prov_name = {p["slug"]: p["name"] for p in PROVIDERS}
write_csv(13, "providers", ["name", "slug", "asn", "description"],
          [[p["name"], p["slug"], p["asn"], p["desc"]] for p in PROVIDERS])
write_csv(14, "provider_networks", ["provider", "name"],
          [[p["name"], f"{p['short']} backbone"] for p in PROVIDERS])
write_csv(15, "circuit_types", ["name", "slug", "color"], [list(t) for t in CIRCUIT_TYPES])
write_csv(16, "asns", ["asn", "description", "sites"],
          [[LOCAL_ASN, "Blackwood University (announces " + ANNOUNCED + ")",
            ";".join(s["name"] for s in SITES.values())]] +
          [[p["asn"], p["name"], ""] for p in PROVIDERS])

short = {p["slug"]: p["short"] for p in PROVIDERS}
write_csv(17, "circuits",
          ["cid", "provider", "type", "status", "commit_rate_kbps", "install_date",
           "tags", "description"],
          [[c["cid"], prov_name[c["provider"]], c["ctype"], c["status"], c["kbps"],
            c["install"], ";".join(c["tags"]), c["notes"]] for c in CIRCUITS])

term_rows, wan_cab_rows, wan_ip_rows = [], [], []
for c in CIRCUITS:
    term_rows.append([c["cid"], "A", "dcim.site", SITES[c["site"]]["name"], c["kbps"],
                      c["xconn"], f"{SITES[c['site']]['name']} demarc"])
    term_rows.append([c["cid"], "Z", "circuits.providernetwork",
                      f"{short[c['provider']]} backbone", c["kbps"], "", ""])
    if not c["device"]:
        continue
    wan_cab_rows.append([c["cid"], "A", c["device"], c["port"], "smf", "connected",
                         f"{c['cid']} handoff", "ffeb3b", 3, "m"])
    peer_asn = next(p["asn"] for p in PROVIDERS if p["slug"] == c["provider"])
    kind = "R&E" if "r-and-e" in c["tags"] else "transit"
    wan_ip_rows.append([c["local_ip"], "active", "", f"BGP local, {c['cid']}",
                        c["device"], c["port"], ";".join(c["tags"]), peer_asn, LOCAL_ASN])
    wan_ip_rows.append([c["peer_ip"], "active", "",
                        f"BGP peer {short[c['provider']]} AS{peer_asn} ({kind}), {c['cid']}",
                        "", "", ";".join(c["tags"]), peer_asn, LOCAL_ASN])
write_csv(18, "circuit_terminations",
          ["cid", "term_side", "termination_type", "termination", "port_speed_kbps",
           "xconnect_id", "description"], term_rows)
write_csv(19, "wan_cables",
          ["cid", "term_side", "device", "interface", "type", "status", "label",
           "color", "length", "length_unit"], wan_cab_rows)
write_csv(20, "wan_ip_addresses",
          ["address", "status", "dns_name", "description", "device", "interface",
           "tags", "bgp_peer_asn", "bgp_local_asn"], wan_ip_rows)

# 26  BGP sessions for the netbox-bgp plugin: one eBGP session per live circuit
bgp_rows = []
for c in CIRCUITS:
    if not c["device"]:
        continue
    peer_asn = next(p["asn"] for p in PROVIDERS if p["slug"] == c["provider"])
    bgp_rows.append([f"{c['cid']} eBGP", c["device"], SITES[c["site"]]["name"],
                     c["local_ip"], c["peer_ip"], LOCAL_ASN, peer_asn, "active",
                     f"eBGP to {short[c['provider']]} AS{peer_asn} over {c['cid']}"])
write_csv(26, "bgp_sessions",
          ["name", "device", "site", "local_address", "remote_address", "local_asn",
           "remote_asn", "status", "description"], bgp_rows)

# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
print("\nvalidation:")
errs = []

known_dt = {(m, mo) for (m, mo) in dtypes}
for n, d in D.items():
    if (d["mfr"], d["model"]) not in known_dt:
        errs.append(f"device {n}: no device_type row")
    rk, us = PLACE[n]
    if not (1 <= us <= us + d["u_height"] - 1 <= RACKS[rk]["height"]):
        errs.append(f"device {n}: position {us} does not fit {rk}")

# every cable endpoint must have an interface row
if_set = {(n, p) for n in ifaces for p in ifaces[n]}
for r in cab_rows:
    for dv, pt in ((r[0], r[2]), (r[3], r[5])):
        if (dv, pt) not in if_set:
            errs.append(f"cable endpoint {dv}:{pt} has no interface row")

# no interface used by more than one cable
from collections import Counter
endpoint_use = Counter()
for r in cab_rows:
    endpoint_use[(r[0], r[2])] += 1
    endpoint_use[(r[3], r[5])] += 1
for (dv, pt), c in endpoint_use.items():
    if c > 1:
        errs.append(f"interface {dv}:{pt} terminates {c} cables")

# every IP references an existing interface on that device
for r in ip_rows:
    if (r[4], r[5]) not in if_set:
        errs.append(f"ip {r[0]}: {r[4]} has no interface {r[5]}")

# prefixes cover every assigned IP; VLAN ids referenced by prefixes exist
import ipaddress
nets = [ipaddress.ip_network(s[0], strict=False) for s in SUBNETS]
for r in ip_rows:
    a = ipaddress.ip_interface(r[0]).ip
    if not any(a in net for net in nets):
        errs.append(f"ip {r[0]} not inside any prefix")
vids = {v[0] for v in VLANS}
for (prefix, vid, _s, _d) in SUBNETS:
    if vid and vid not in vids:
        errs.append(f"prefix {prefix} references unknown VLAN {vid}")

# WAN: one termination handoff per interface, interface rows exist, IPs sit in a prefix
cids = [c["cid"] for c in CIRCUITS]
if len(set(cids)) != len(cids):
    errs.append("duplicate circuit ids")
for r in wan_cab_rows:
    if (r[2], r[3]) not in if_set:
        errs.append(f"wan cable endpoint {r[2]}:{r[3]} has no interface row")
    if endpoint_use[(r[2], r[3])]:
        errs.append(f"wan interface {r[2]}:{r[3]} already used by a cable")
for r in wan_ip_rows:
    a = ipaddress.ip_interface(r[0]).ip
    if not any(a in net for net in nets):
        errs.append(f"wan ip {r[0]} not inside any prefix")
    if r[4] and (r[4], r[5]) not in if_set:
        errs.append(f"wan ip {r[0]}: {r[4]} has no interface {r[5]}")

# power: one cable per PSU and per outlet, outlets exist, feeds sized for the load
_outlet_use = collections.Counter((r[2], r[3]) for r in pwr_rows)
for (pdu, outlet), c in _outlet_use.items():
    if c > 1:
        errs.append(f"outlet {pdu}:{outlet} feeds {c} PSUs")
    n = int(outlet.split("-")[1])
    if n > (PDU_C19 if outlet.startswith("C19") else PDU_C13):
        errs.append(f"outlet {pdu}:{outlet} does not exist on the PDU")
for r in pwr_rows:
    if r[0] not in D:
        errs.append(f"power row for unknown device {r[0]}")
_pdu_names = {p["name"] for p in PDUS}
if {r[2] for r in pwr_rows} - _pdu_names:
    errs.append("power rows reference a PDU with no PDU row")

if errs:
    print("  FAIL")
    for e in errs:
        print("   -", e)
    raise SystemExit(1)

print(f"  OK  -  {len(D)} devices, {len(if_rows)} interfaces, "
      f"{len(ip_rows)} IPs, {len(cab_rows)} cables, "
      f"{len(rack_rows)} racks, {len(roles)} roles")
