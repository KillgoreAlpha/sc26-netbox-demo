#!/usr/bin/env python3
"""Create the two floor plans and place the racks (NetBox Visual Explorer).

Uses the physical-geometry API that backs Visual Explorer Floorplans
(NetBox Cloud Premium). Run load_netbox.py first so the locations and racks exist.

    export NETBOX_URL=...  NETBOX_TOKEN='nbt_<key>.<secret>'
    python3 floorplans.py --dry-run
    python3 floorplans.py

Everything is in centimetres. Idempotent: an existing floor plan, layer or rack
shape is left alone. The geometry API is "under active development" per the
NetBox docs, so if a field is rejected, the error body is printed.
x, y are the rack's position in the room; open the plan afterwards and nudge
anything that landed off (the docs do not say whether x/y is the centre or a
corner). You can also skip the shapes and drag racks in edit mode instead.
"""

import argparse
import os
import sys

import requests

BASE = "/api/plugins/physical-geometry"
RACK_W, RACK_D = 60, 120  # cm, matches the 600 x 1200 mm rack types

# location slug -> floor plan name, room size (cm), rack positions (cm)
PLANS = {
    "marston-machine-room": dict(
        name="Marston Machine Room", width=1000, depth=800,
        racks={"MDC-A1": (200, 250), "MDC-A2": (270, 250), "MDC-B1": (200, 550)}),
    "west-ridge-data-hall": dict(
        name="West Ridge Data Hall", width=1400, depth=1000,
        racks={"WRDC-H1": (300, 400), "WRDC-H2": (370, 400),
               "WRDC-H3": (560, 400), "WRDC-H4": (630, 400)}),
}


def ref(v):
    """id from either a plain id or a nested {'id': ...} reference"""
    return v.get("id") if isinstance(v, dict) else v


class Api:
    def __init__(self, url, token, dry):
        self.url, self.dry = url.rstrip("/"), dry
        self.s = requests.Session()
        # v2 tokens (nbt_<key>.<secret>) use Bearer, v1 tokens use Token
        scheme = "Bearer" if token.startswith("nbt_") and "." in token else "Token"
        self.s.headers.update({"Authorization": f"{scheme} {token}",
                               "Accept": "application/json"})

    def get(self, path, **params):
        r = self.s.get(self.url + path, params={**params, "limit": 1000})
        self._check(r)
        return r.json().get("results", [])

    def delete(self, path):
        r = self.s.delete(self.url + path)
        self._check(r)

    def post(self, path, body):
        r = self.s.post(self.url + path, json=body)
        self._check(r)
        return r.json()

    @staticmethod
    def _check(r):
        if not r.ok:
            sys.exit(f"  ! {r.request.method} {r.url} -> {r.status_code}: {r.text[:500]}")


def status(api, repair):
    """List every floor plan with its shapes; optionally drop mismatched rack shapes."""
    fps = api.get(BASE + "/floorplans/")
    shapes = api.get(BASE + "/shapes/")
    racks = {r["id"]: r for r in api.get("/api/dcim/racks/")}
    print(f"{len(fps)} floor plan(s), {len(shapes)} shape(s)")
    for f in fps:
        fid, lid = f["id"], ref(f.get("location"))
        print(f"\nplan {fid}: {f.get('name')!r} (location id {lid})")
        for sh in list(shapes):
            if ref(sh.get("floorplan")) != fid:
                continue
            rk = racks.get(sh.get("object_id"))
            name = rk["name"] if rk else f"object {sh.get('object_id')}"
            rloc = ref(rk.get("location")) if rk else None
            bad = rk is not None and rloc != lid
            print(f"  shape {sh['id']}: {name} at ({sh.get('x')}, {sh.get('y')})"
                  + ("   <-- rack is in a different location" if bad else ""))
            if bad and repair:
                api.delete(f"{BASE}/shapes/{sh['id']}/")
                print("    deleted")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("NETBOX_URL"))
    ap.add_argument("--token", default=os.environ.get("NETBOX_TOKEN"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true",
                    help="read-only: list floor plans and the racks placed on each")
    ap.add_argument("--repair", action="store_true",
                    help="delete rack shapes sitting on a floor plan for a different location")
    a = ap.parse_args()
    if not a.url or not a.token:
        sys.exit("set NETBOX_URL and NETBOX_TOKEN (or pass --url/--token)")
    api = Api(a.url, a.token, a.dry_run)
    if a.status or a.repair:
        return status(api, a.repair)

    for slug, plan in PLANS.items():
        locs = api.get("/api/dcim/locations/", slug=slug)
        if not locs:
            print(f"  ! location {slug} not found - run load_netbox.py first")
            continue
        loc = locs[0]
        print(f"{plan['name']}")

        # filter client-side too: an ignored query param would return every plan
        fps = [f for f in api.get(BASE + "/floorplans/", location=loc["id"])
               if ref(f.get("location")) == loc["id"]]
        if fps:
            fp = fps[0]
            print("  = floor plan exists")
        else:
            body = {"name": plan["name"], "location": loc["id"], "base_unit": "cm",
                    "width": plan["width"], "depth": plan["depth"]}
            if api.dry:
                print(f"  + floor plan {body}")
                fp = {"id": 0}
            else:
                fp = api.post(BASE + "/floorplans/", body)
                print("  + floor plan created")

        layers = [] if not fp["id"] else [
            l for l in api.get(BASE + "/layers/", floorplan=fp["id"])
            if ref(l.get("floorplan")) == fp["id"]]
        if layers:
            layer = layers[0]
            print(f"  = layer '{layer['name']}' exists")
        else:
            body = {"floorplan": fp["id"], "name": "Racks"}
            if api.dry:
                print(f"  + layer {body}")
                layer = {"id": 0}
            else:
                layer = api.post(BASE + "/layers/", body)
                print("  + layer created")

        placed = set()
        if fp["id"]:
            placed = {s.get("object_id") for s in api.get(BASE + "/shapes/", floorplan=fp["id"])
                      if ref(s.get("floorplan")) == fp["id"]}
        for rname, (x, y) in plan["racks"].items():
            racks = api.get("/api/dcim/racks/", name=rname)
            if not racks:
                print(f"  ! rack {rname} not found")
                continue
            rid = racks[0]["id"]
            if rid in placed:
                print(f"  = {rname} already placed")
                continue
            body = {"floorplan": fp["id"], "layer": layer["id"], "type": "rack",
                    "object_type": "dcim.rack", "object_id": rid, "x": x, "y": y,
                    "width": RACK_W, "depth": RACK_D, "orientation": 0}
            if api.dry:
                print(f"  + {rname} at ({x}, {y})")
            else:
                api.post(BASE + "/shapes/", body)
                print(f"  + {rname} placed at ({x}, {y})")


if __name__ == "__main__":
    main()
