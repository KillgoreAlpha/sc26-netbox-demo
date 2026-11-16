#!/usr/bin/env python3
"""Remove every object the demo added to NetBox (the objects named in csv/*.csv).

DESTRUCTIVE. The opposite of cleanup_netbox.py: that script deletes what is NOT in the plan,
this one deletes what IS. Only objects named in the CSVs (plus the two floor plans) are touched.
Nothing is deleted unless you pass BOTH --go and --confirm N, where N is the exact object
count the dry run printed.

    python3 teardown_netbox.py                         # dry run: list what would go
    python3 teardown_netbox.py --include shared        # also device types, manufacturers, roles,
                                                       # tags, custom fields, circuit types, RIR
    python3 teardown_netbox.py --only devices,racks    # limit the classes
    python3 teardown_netbox.py --go --confirm 412      # delete (412 = count from the dry run)

Classes, in deletion order: bgp-sessions, devices (incl. PDUs; their cables, interfaces and power
ports go with them), power-feeds, power-panels, circuits, provider-networks, providers, asns,
ip-addresses, prefixes, vlans, floorplans (with their layers and shapes), racks, rack-types,
locations, sites.
--include shared adds: device-types (incl. the NDX-imported ones), manufacturers, device-roles,
circuit-types, rirs, tags, custom-fields. Those can be shared with other data, so they are opt-in
and NetBox refuses to delete any that something else still uses (reported, not fatal).
Plugin classes (bgp-sessions, floorplans) are skipped quietly if the plugin API is missing.
Rerun after a failure; already-deleted objects are simply not listed again.
"""

import argparse
import csv
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
GEOM = "/api/plugins/physical-geometry"
FLOORPLAN_NAMES = {"Marston Machine Room", "West Ridge Data Hall"}  # see floorplans.py
CUSTOM_FIELDS = {"bgp_peer_asn", "bgp_local_asn"}                    # see load_netbox.py
RIR_SLUG = "rfc5398"


def col(file, key):
    with open(os.path.join(HERE, "csv", file)) as f:
        return {r[key] for r in csv.DictReader(f) if r[key]}


def ref(v):
    return v.get("id") if isinstance(v, dict) else v


# class -> (api path, identity field, planned set, plugin?)
def classes():
    return {
        "bgp-sessions":      ("/api/plugins/bgp/session/", "name", col("26_bgp_sessions.csv", "name"), True),
        "virtual-machines":  ("/api/virtualization/virtual-machines/", "name", col("28_virtual_machines.csv", "name"), False),
        "clusters":          ("/api/virtualization/clusters/", "name", col("27_clusters.csv", "name"), False),
        "devices":           ("/api/dcim/devices/", "name", col("07_devices.csv", "name") | col("23_pdus.csv", "name"), False),
        "power-feeds":       ("/api/dcim/power-feeds/", "name", col("22_power_feeds.csv", "name"), False),
        "power-panels":      ("/api/dcim/power-panels/", "name", col("21_power_panels.csv", "name"), False),
        "circuits":          ("/api/circuits/circuits/", "cid", col("17_circuits.csv", "cid"), False),
        "provider-networks": ("/api/circuits/provider-networks/", "name", col("14_provider_networks.csv", "name"), False),
        "providers":         ("/api/circuits/providers/", "slug", col("13_providers.csv", "slug"), False),
        "asns":              ("/api/ipam/asns/", "asn", {int(x) for x in col("16_asns.csv", "asn")}, False),
        "ip-addresses":      ("/api/ipam/ip-addresses/", "address",
                              col("11_ip_addresses.csv", "address") | col("20_wan_ip_addresses.csv", "address")
                              | col("29_vm_interfaces.csv", "address"), False),
        "prefixes":          ("/api/ipam/prefixes/", "prefix", col("09_prefixes.csv", "prefix"), False),
        "vlans":             ("/api/ipam/vlans/", "vid", {int(x) for x in col("08_vlans.csv", "vid")}, False),
        "floorplans":        (GEOM + "/floorplans/", "name", FLOORPLAN_NAMES, True),
        "racks":             ("/api/dcim/racks/", "name", col("06_racks.csv", "name"), False),
        "rack-types":        ("/api/dcim/rack-types/", "slug", col("05a_rack_types.csv", "slug"), False),
        "locations":         ("/api/dcim/locations/", "slug", col("05_locations.csv", "slug"), False),
        "sites":             ("/api/dcim/sites/", "slug", col("04_sites.csv", "slug"), False),
        # --include shared
        "device-types":      ("/api/dcim/device-types/", "slug", col("02_device_types.csv", "slug"), False),
        "manufacturers":     ("/api/dcim/manufacturers/", "slug", col("01_manufacturers.csv", "slug"), False),
        "device-roles":      ("/api/dcim/device-roles/", "slug", col("03_device_roles.csv", "slug"), False),
        "circuit-types":     ("/api/circuits/circuit-types/", "slug", col("15_circuit_types.csv", "slug"), False),
        "rirs":              ("/api/ipam/rirs/", "slug", {RIR_SLUG}, False),
        "tags":              ("/api/extras/tags/", "slug", col("12a_tags.csv", "slug"), False),
        "custom-fields":     ("/api/extras/custom-fields/", "name", CUSTOM_FIELDS, False),
    }


ORDER = ["bgp-sessions", "virtual-machines", "clusters", "devices", "power-feeds", "power-panels", "circuits", "provider-networks",
         "providers", "asns", "ip-addresses", "prefixes", "vlans", "floorplans", "racks",
         "rack-types", "locations", "sites"]
SHARED = ["device-types", "manufacturers", "device-roles", "circuit-types", "rirs", "tags",
          "custom-fields"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("NETBOX_URL"))
    ap.add_argument("--token", default=os.environ.get("NETBOX_TOKEN"))
    ap.add_argument("--only", help="comma list of classes")
    ap.add_argument("--include", help="'shared' (device types, manufacturers, roles, tags, ...)")
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
        if a.include != "shared":
            sys.exit(f"--include only supports 'shared', not {a.include!r}")
        order += SHARED
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

    found = {}
    for cls in order:
        path, key, planned, plugin = spec[cls]
        try:
            objs = fetch(path)
        except requests.HTTPError as e:
            if plugin and e.response is not None and e.response.status_code == 404:
                found[cls] = None  # plugin not installed
                continue
            raise
        found[cls] = [o for o in objs if o.get(key) in planned]

    total = sum(len(v) for v in found.values() if v)
    print(f"instance: {root}\n")
    for cls in order:
        key = spec[cls][1]
        items = found[cls]
        if items is None:
            print(f"{cls}: plugin API not available, skipped")
            continue
        print(f"{cls}: {len(items)} to delete")
        for o in items[:25]:
            print(f"    {o.get(key)}")
        if len(items) > 25:
            print(f"    ... and {len(items) - 25} more")
    print(f"\ntotal to delete: {total}")

    if not a.go:
        print("dry run: nothing deleted.")
        if total:
            print(f"to delete: python3 teardown_netbox.py --go --confirm {total}"
                  + (f" --only {a.only}" if a.only else "")
                  + (f" --include {a.include}" if a.include else ""))
        return
    if a.confirm != total:
        sys.exit(f"refusing: --confirm must equal the total ({total}); got {a.confirm}")

    def delete(path, obj_id):
        return s.delete(f"{root}{path}{obj_id}/")

    failed = 0
    for cls in order:
        path, key, _, _ = spec[cls]
        for o in found[cls] or []:
            if cls == "floorplans":  # layers and shapes first, in case they do not cascade
                for sub in ("shapes", "layers"):
                    for x in fetch(f"{GEOM}/{sub}/"):
                        if ref(x.get("floorplan")) == o["id"]:
                            delete(f"{GEOM}/{sub}/", x["id"])
            r = delete(path, o["id"])
            if r.ok:
                print(f"  deleted {cls}: {o.get(key)}")
            else:
                failed += 1
                why = "still in use" if r.status_code == 409 else f"{r.status_code} {r.text[:200]}"
                print(f"  ! {cls} {o.get(key)}: {why}")
    print(f"\ndone. deleted {total - failed}, failed {failed}")
    if failed:
        print("failures are usually objects still referenced by something else; fix and re-run.")


if __name__ == "__main__":
    main()
