#!/usr/bin/env python3
"""Compare NetBox with the planned data (csv/*.csv). Read-only: changes nothing.

    export NETBOX_URL=...  NETBOX_TOKEN='nbt_<key>.<secret>'
    python3 verify_netbox.py            # summary, first 10 differences per check
    python3 verify_netbox.py --all      # every difference

Reports, per check, what is MISSING from NetBox, what is EXTRA (in NetBox, not in the
plan) and what DIFFERS (same object, different values). Exit code 1 if anything is off.
Extra top-level objects can be removed with cleanup_netbox.py; extra interfaces, cables
and power ports on planned devices are only reported here.
"""

import argparse
import csv
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def rows(name):
    with open(os.path.join(HERE, "csv", name)) as f:
        return list(csv.DictReader(f))


def nested(o, *path):
    for p in path:
        o = (o or {}).get(p) if isinstance(o, dict) else None
    return o


def val(x):
    """choice fields come back as {'value': ..., 'label': ...}"""
    return x.get("value") if isinstance(x, dict) else x


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("NETBOX_URL"))
    ap.add_argument("--token", default=os.environ.get("NETBOX_TOKEN"))
    ap.add_argument("--all", action="store_true", help="print every difference")
    a = ap.parse_args()
    if not a.url or not a.token:
        sys.exit("set NETBOX_URL and NETBOX_TOKEN (or pass --url/--token)")
    root = a.url.rstrip("/")
    scheme = "Bearer" if a.token.startswith("nbt_") and "." in a.token else "Token"
    s = requests.Session()
    s.headers.update({"Authorization": f"{scheme} {a.token}", "Accept": "application/json"})

    def fetch(path, **params):
        out, url, p = [], root + path, {"limit": 1000, **params}
        while url:
            r = s.get(url, params=p)
            r.raise_for_status()
            d = r.json()
            out += d["results"]
            url, p = d.get("next"), None
        return out

    problems = 0
    cap = None if a.all else 10

    def report(title, planned, actual, differs=()):
        """planned/actual: sets of keys. differs: list of strings."""
        nonlocal problems
        missing, extra = sorted(map(str, planned - actual)), sorted(map(str, actual - planned))
        bad = len(missing) + len(extra) + len(differs)
        problems += bad
        print(f"{'OK  ' if not bad else 'FAIL'} {title}: planned {len(planned)}, in NetBox {len(actual)}")
        for label, items in (("MISSING", missing), ("EXTRA", extra), ("DIFFERS", list(differs))):
            for x in items[:cap]:
                print(f"       {label}: {x}")
            if cap and len(items) > cap:
                print(f"       {label}: ... and {len(items) - cap} more")

    # --- device types, sites, locations, racks -------------------------------------
    types = {r["slug"]: r for r in rows("02_device_types.csv")}
    nb_types = {t["slug"]: t for t in fetch("/api/dcim/device-types/")}
    diffs = [f"{k}: model {nb_types[k]['model']!r} != {v['model']!r}" for k, v in types.items()
             if k in nb_types and nb_types[k]["model"] != v["model"]]
    diffs += [f"{k}: u_height {nb_types[k]['u_height']} != {v['u_height']}" for k, v in types.items()
              if k in nb_types and num(nb_types[k]["u_height"]) != num(v["u_height"])]
    report("device types", set(types), set(nb_types), diffs)
    model_slug = {v["model"]: k for k, v in types.items()}

    sites = {r["name"]: r for r in rows("04_sites.csv")}
    nb_sites = {x["name"]: x for x in fetch("/api/dcim/sites/")}
    diffs = [f"{k}: slug {nb_sites[k]['slug']!r} != {v['slug']!r}" for k, v in sites.items()
             if k in nb_sites and nb_sites[k]["slug"] != v["slug"]]
    diffs += [f"{k}: lat/long {nb_sites[k].get('latitude')}/{nb_sites[k].get('longitude')} "
              f"!= {v['latitude']}/{v['longitude']}" for k, v in sites.items()
              if k in nb_sites and (num(nb_sites[k].get("latitude")) != num(v["latitude"])
                                    or num(nb_sites[k].get("longitude")) != num(v["longitude"]))]
    report("sites", set(sites), set(nb_sites), diffs)

    locs = {r["slug"]: r for r in rows("05_locations.csv")}
    nb_locs = {x["slug"]: x for x in fetch("/api/dcim/locations/")}
    diffs = [f"{k}: site {nested(nb_locs[k], 'site', 'name')!r} != {v['site']!r}"
             for k, v in locs.items()
             if k in nb_locs and nested(nb_locs[k], "site", "name") != v["site"]]
    report("locations", set(locs), set(nb_locs), diffs)

    racks = {r["name"]: r for r in rows("06_racks.csv")}
    nb_racks = {x["name"]: x for x in fetch("/api/dcim/racks/")}
    diffs = []
    for k, v in racks.items():
        x = nb_racks.get(k)
        if not x:
            continue
        if nested(x, "location", "name") != v["location"]:
            diffs.append(f"{k}: location {nested(x, 'location', 'name')!r} != {v['location']!r}")
        if num(x.get("u_height")) != num(v["u_height"]):
            diffs.append(f"{k}: u_height {x.get('u_height')} != {v['u_height']}")
    report("racks", set(racks), set(nb_racks), diffs)

    # --- devices (incl. PDUs) ---------------------------------------------------------
    devs = {r["name"]: r for r in rows("07_devices.csv")}
    nb_devs = {x["name"]: x for x in fetch("/api/dcim/devices/")}
    pdus = {r["name"]: r for r in rows("23_pdus.csv")}
    diffs = []
    for k, v in devs.items():
        x = nb_devs.get(k)
        if not x:
            continue
        checks = [("device type", nested(x, "device_type", "slug"), model_slug.get(v["device_type"])),
                  ("role", nested(x, "role", "name"), v["role"]),
                  ("site", nested(x, "site", "name"), v["site"]),
                  ("rack", nested(x, "rack", "name"), v["rack"]),
                  ("position", num(x.get("position")), num(v["position"])),
                  ("face", val(x.get("face")), v["face"]),
                  ("status", val(x.get("status")), v["status"])]
        diffs += [f"{k}: {f} {have!r} != {want!r}" for f, have, want in checks if have != want]
    for k, v in pdus.items():
        x = nb_devs.get(k)
        if x and nested(x, "rack", "name") != v["rack"]:
            diffs.append(f"{k}: rack {nested(x, 'rack', 'name')!r} != {v['rack']!r}")
    report("devices + PDUs", set(devs) | set(pdus), set(nb_devs), diffs)

    # --- interfaces per device -----------------------------------------------------------
    planned_if = {(r["device"], r["name"]) for r in rows("10_interfaces.csv")}
    nb_if = {(nested(i, "device", "name"), i["name"]) for i in fetch("/api/dcim/interfaces/")
             if nested(i, "device", "name") in devs}
    report("interfaces on planned devices", planned_if, nb_if)

    # --- VLANs, prefixes, IPs -----------------------------------------------------------
    vlans = {int(r["vid"]): r for r in rows("08_vlans.csv")}
    nb_vlans = {v["vid"]: v for v in fetch("/api/ipam/vlans/")}
    diffs = [f"VLAN {k}: name {nb_vlans[k]['name']!r} != {v['name']!r}" for k, v in vlans.items()
             if k in nb_vlans and nb_vlans[k]["name"] != v["name"]]
    report("VLANs", set(vlans), set(nb_vlans), diffs)

    pfx = {r["prefix"]: r for r in rows("09_prefixes.csv")}
    nb_pfx = {x["prefix"]: x for x in fetch("/api/ipam/prefixes/")}
    diffs = []
    for k, v in pfx.items():
        x = nb_pfx.get(k)
        if not x:
            continue
        if val(x.get("status")) != v["status"]:
            diffs.append(f"{k}: status {val(x.get('status'))!r} != {v['status']!r}")
        if str(nested(x, "vlan", "vid") or "") != v["vlan"]:
            diffs.append(f"{k}: vlan {nested(x, 'vlan', 'vid')!r} != {v['vlan']!r}")
    report("prefixes", set(pfx), set(nb_pfx), diffs)

    ips = {r["address"]: r for r in rows("11_ip_addresses.csv")}
    ips.update({r["address"]: r for r in rows("20_wan_ip_addresses.csv")})
    nb_ips = {x["address"]: x for x in fetch("/api/ipam/ip-addresses/")}
    diffs = []
    for k, v in ips.items():
        x = nb_ips.get(k)
        if not x:
            continue
        ao = x.get("assigned_object") or {}
        have = (nested(ao, "device", "name") or "", ao.get("name") or "")
        want = (v.get("device", ""), v.get("interface", ""))
        if have != want:
            diffs.append(f"{k}: assigned to {have} != {want}")
        if val(x.get("status")) != v["status"]:
            diffs.append(f"{k}: status {val(x.get('status'))!r} != {v['status']!r}")
    report("IP addresses", set(ips), set(nb_ips), diffs)

    # --- circuits, ASNs, providers ---------------------------------------------------------
    circ = {r["cid"]: r for r in rows("17_circuits.csv")}
    nb_circ = {x["cid"]: x for x in fetch("/api/circuits/circuits/")}
    diffs = [f"{k}: status {val(nb_circ[k].get('status'))!r} != {v['status']!r}"
             for k, v in circ.items() if k in nb_circ and val(nb_circ[k].get("status")) != v["status"]]
    report("circuits", set(circ), set(nb_circ), diffs)
    report("ASNs", {int(r["asn"]) for r in rows("16_asns.csv")},
           {x["asn"] for x in fetch("/api/ipam/asns/")})
    report("providers", {r["slug"] for r in rows("13_providers.csv")},
           {x["slug"] for x in fetch("/api/circuits/providers/")})

    # --- power: panels, feeds, ports, outlets ------------------------------------------------
    report("power panels", {r["name"] for r in rows("21_power_panels.csv")},
           {x["name"] for x in fetch("/api/dcim/power-panels/")})
    feeds = {r["name"]: r for r in rows("22_power_feeds.csv")}
    nb_feeds = {x["name"]: x for x in fetch("/api/dcim/power-feeds/")}
    diffs = []
    for k, v in feeds.items():
        x = nb_feeds.get(k)
        if not x:
            continue
        for f, have, want in (("voltage", x.get("voltage"), int(v["voltage"])),
                              ("amperage", x.get("amperage"), int(v["amperage"])),
                              ("phase", val(x.get("phase")), v["phase"]),
                              ("rack", nested(x, "rack", "name"), v["rack"]),
                              ("panel", nested(x, "power_panel", "name"), v["panel"])):
            if have != want:
                diffs.append(f"{k}: {f} {have!r} != {want!r}")
    report("power feeds", set(feeds), set(nb_feeds), diffs)

    pports = {(r["device"], r["name"]): r for r in rows("24_power_ports.csv")}
    nb_pp = {}
    for p in fetch("/api/dcim/power-ports/"):
        d = nested(p, "device", "name")
        if d in devs:
            nb_pp[(d, p["name"])] = p
    diffs = []
    for k, v in pports.items():
        x = nb_pp.get(k)
        if x and (x.get("maximum_draw") != int(v["maximum_draw"])
                  or x.get("allocated_draw") != int(v["allocated_draw"])):
            diffs.append(f"{k}: draw {x.get('maximum_draw')}/{x.get('allocated_draw')} "
                         f"!= {v['maximum_draw']}/{v['allocated_draw']}")
    report("PSU power ports on devices", set(pports), set(nb_pp), diffs)

    want_out = {(p["name"], f"C13-{n}") for p in pdus.values() for n in range(1, int(p["c13_outlets"]) + 1)}
    want_out |= {(p["name"], f"C19-{n}") for p in pdus.values() for n in range(1, int(p["c19_outlets"]) + 1)}
    have_out = {(nested(o, "device", "name"), o["name"]) for o in fetch("/api/dcim/power-outlets/")
                if nested(o, "device", "name") in pdus}
    report("PDU outlets", want_out, have_out)

    # --- cables (data, WAN, power) --------------------------------------------------------------
    def end(t):
        o = t.get("object") or {}
        typ = t.get("object_type", "")
        if typ == "circuits.circuittermination":
            return ("circuit", nested(o, "circuit", "cid") or "?")
        if typ == "dcim.powerfeed":
            return ("feed", o.get("name"))
        return (nested(o, "device", "name"), o.get("name"))

    planned = set()
    for r in rows("12_cables.csv"):
        planned.add(frozenset([(r["side_a_device"], r["side_a_name"]), (r["side_b_device"], r["side_b_name"])]))
    for r in rows("19_wan_cables.csv"):
        planned.add(frozenset([("circuit", r["cid"]), (r["device"], r["interface"])]))
    for r in rows("25_power_cables.csv"):
        planned.add(frozenset([(r["device"], r["port"]), (r["pdu"], r["outlet"])]))
    for r in rows("23_pdus.csv"):
        planned.add(frozenset([(r["name"], "Input"), ("feed", r["feed"])]))
    actual = set()
    for c in fetch("/api/dcim/cables/"):
        ends = [end(t) for t in (c.get("a_terminations") or []) + (c.get("b_terminations") or [])]
        if len(ends) == 2:
            actual.add(frozenset(ends))
        else:
            actual.add(frozenset([("cable", c["id"])]))
    report("cables (data + WAN + power)", planned, actual)

    print(f"\n{'all checks passed' if not problems else str(problems) + ' difference(s) found'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
