#!/usr/bin/env python3
"""Delete NetBox objects that are NOT in the planned data (csv/*.csv).

DESTRUCTIVE. Point it only at a throwaway demo instance. It compares what is in
NetBox with the CSVs and removes the extras. Nothing is deleted unless you pass
BOTH --go and --confirm N, where N is the exact object count the dry run printed.

    python3 cleanup_netbox.py                       # dry run: list what would go
    python3 cleanup_netbox.py --only devices,racks  # limit the object classes
    python3 cleanup_netbox.py --include device-types  # also unused, unplanned device types
    python3 cleanup_netbox.py --go --confirm 12     # delete (12 = count from the dry run)

Classes (deleted in this order): devices (incl. PDUs), bgp-sessions, power-feeds, power-panels, circuits, provider-networks, providers,
asns, ip-addresses, prefixes, vlans, racks, locations, sites.
Opt-in with --include: device-types (only those with no devices).
Never touched: manufacturers, device roles, tags, custom fields, cables (they go
with the devices they connect), floor plans, anything else.
"""

import argparse
import csv
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def col(file, key):
    with open(os.path.join(HERE, "csv", file)) as f:
        return {r[key] for r in csv.DictReader(f) if r[key]}


# class -> (api path, identity field(s), planned set, how to print an object)
def classes():
    return {
        "devices":           ("/api/dcim/devices/", "name",
                              col("07_devices.csv", "name") | col("23_pdus.csv", "name")),
        "bgp-sessions":      ("/api/plugins/bgp/session/", "name", col("26_bgp_sessions.csv", "name")),
        "power-feeds":       ("/api/dcim/power-feeds/", "name", col("22_power_feeds.csv", "name")),
        "power-panels":      ("/api/dcim/power-panels/", "name", col("21_power_panels.csv", "name")),
        "circuits":          ("/api/circuits/circuits/", "cid", col("17_circuits.csv", "cid")),
        "provider-networks": ("/api/circuits/provider-networks/", "name", col("14_provider_networks.csv", "name")),
        "providers":         ("/api/circuits/providers/", "slug", col("13_providers.csv", "slug")),
        "asns":              ("/api/ipam/asns/", "asn", {int(x) for x in col("16_asns.csv", "asn")}),
        "ip-addresses":      ("/api/ipam/ip-addresses/", "address",
                              col("11_ip_addresses.csv", "address") | col("20_wan_ip_addresses.csv", "address")),
        "prefixes":          ("/api/ipam/prefixes/", "prefix", col("09_prefixes.csv", "prefix")),
        "vlans":             ("/api/ipam/vlans/", "vid", {int(x) for x in col("08_vlans.csv", "vid")}),
        "racks":             ("/api/dcim/racks/", "name", col("06_racks.csv", "name")),
        "locations":         ("/api/dcim/locations/", "slug", col("05_locations.csv", "slug")),
        "sites":             ("/api/dcim/sites/", "slug", col("04_sites.csv", "slug")),
        "device-types":      ("/api/dcim/device-types/", "slug", col("02_device_types.csv", "slug")),
    }


ORDER = ["devices", "bgp-sessions", "power-feeds", "power-panels", "circuits", "provider-networks", "providers", "asns",
         "ip-addresses", "prefixes", "vlans", "racks", "locations", "sites"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("NETBOX_URL"))
    ap.add_argument("--token", default=os.environ.get("NETBOX_TOKEN"))
    ap.add_argument("--only", help="comma list of classes to check")
    ap.add_argument("--include", help="opt-in classes, e.g. device-types")
    ap.add_argument("--go", action="store_true", help="actually delete")
    ap.add_argument("--confirm", type=int, help="exact number of objects to delete")
    a = ap.parse_args()
    if not a.url or not a.token:
        sys.exit("set NETBOX_URL and NETBOX_TOKEN (or pass --url/--token)")
    root = a.url.rstrip("/")
    scheme = "Bearer" if a.token.startswith("nbt_") and "." in a.token else "Token"
    s = requests.Session()
    s.headers.update({"Authorization": f"{scheme} {a.token}", "Accept": "application/json"})

    spec = classes()
    order = list(ORDER)
    if a.include:
        for c in a.include.split(","):
            if c != "device-types":
                sys.exit(f"--include only supports device-types, not {c!r}")
            order.append(c)
    if a.only:
        want = a.only.split(",")
        bad = [c for c in want if c not in order]
        if bad:
            sys.exit(f"unknown class(es): {', '.join(bad)}. choose from {', '.join(order)}")
        order = [c for c in order if c in want]

    def fetch(path):
        out, url, params = [], root + path, {"limit": 500}
        while url:
            r = s.get(url, params=params)
            r.raise_for_status()
            d = r.json()
            out += d["results"]
            url, params = d.get("next"), None
        return out

    extras = {}
    for cls in order:
        path, key, planned = spec[cls]
        try:
            objs = fetch(path)
        except requests.HTTPError as e:
            if cls == "bgp-sessions" and e.response is not None and e.response.status_code == 404:
                objs = []  # plugin not installed
            else:
                raise
        if cls == "device-types":
            objs = [o for o in objs if not o.get("device_count")]  # never delete a type in use
        extras[cls] = [o for o in objs if o.get(key) not in planned]

    total = sum(len(v) for v in extras.values())
    print(f"instance: {root}\n")
    for cls in order:
        key = spec[cls][1]
        items = extras[cls]
        print(f"{cls}: {len(items)} not in the planned data")
        for o in items[:25]:
            print(f"    {o.get(key)}")
        if len(items) > 25:
            print(f"    ... and {len(items) - 25} more")
    print(f"\ntotal to delete: {total}")

    if not a.go:
        print("dry run: nothing deleted.")
        if total:
            print(f"to delete: python3 cleanup_netbox.py --go --confirm {total}"
                  + (f" --only {a.only}" if a.only else "")
                  + (f" --include {a.include}" if a.include else ""))
        return
    if a.confirm != total:
        sys.exit(f"refusing: --confirm must equal the total ({total}); got {a.confirm}")

    failed = 0
    for cls in order:
        path, key, _ = spec[cls]
        for o in extras[cls]:
            r = s.delete(f"{root}{path}{o['id']}/")
            if r.ok:
                print(f"  deleted {cls[:-1] if cls.endswith('s') else cls}: {o.get(key)}")
            else:
                failed += 1
                print(f"  ! {cls} {o.get(key)}: {r.status_code} {r.text[:200]}")
    print(f"\ndone. deleted {total - failed}, failed {failed}")
    if failed:
        print("failures are usually objects still referenced by something else; re-run to retry.")


if __name__ == "__main__":
    main()
