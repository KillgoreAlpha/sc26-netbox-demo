#!/usr/bin/env python3
"""Align our device types with the NDX catalog and import the matches.

Dry run by default. For each row of csv/02_device_types.csv:
  - if the type exists in NetBox under a different slug, plan a slug rename
    to the CSV slug (so the NDX import updates it in place, no duplicate);
  - if the catalog has that exact slug, plan an NDX import for it.
Types the catalog does not have are left alone.

    python3 ndx_import.py                          # show the plan, change nothing
    python3 ndx_import.py --go --only dell-poweredge-r740xd   # try ONE type first
    python3 ndx_import.py --go                     # rename + import everything planned
    python3 ndx_import.py --repoint                # show devices still on an old type
    python3 ndx_import.py --repoint --go           # move them to the CSV's type
"""

import argparse
import csv
import os
import re
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def repoint(s, root, go):
    """Existing devices keep the type they were created with; point them at the CSV's type."""
    slug_of = {r["model"]: r["slug"] for r in csv.DictReader(open(os.path.join(HERE, "csv", "02_device_types.csv")))}
    types = {}
    r = s.get(root + "/api/dcim/device-types/", params={"limit": 1000})
    r.raise_for_status()
    for t in r.json()["results"]:
        types[t["slug"]] = t["id"]
    todo = []
    for row in csv.DictReader(open(os.path.join(HERE, "csv", "07_devices.csv"))):
        want = slug_of[row["device_type"]]
        r = s.get(root + "/api/dcim/devices/", params={"name": row["name"]})
        r.raise_for_status()
        res = r.json()["results"]
        if not res:
            continue
        dev = res[0]
        if dev["device_type"]["slug"] == want:
            continue
        if want not in types:
            print(f"  ! {row['name']}: type {want} is not in NetBox yet (run load_netbox.py or the NDX import first)")
            continue
        todo.append((dev["id"], row["name"], dev["device_type"]["slug"], want))
    for _id, name, old, new in todo:
        print(f"  {name}: {old} -> {new}")
        if go:
            r = s.patch(f"{root}/api/dcim/devices/{_id}/", json={"device_type": types[new]})
            print(f"    {r.status_code}" + ("" if r.ok else f" {r.text[:300]}"))
    if not todo:
        print("  every device is already on its CSV type")
    elif not go:
        print("\ndry run: nothing changed. Add --go to apply.")
    keep = set(slug_of.values())
    used = {t for t in keep}
    print("\ndevice types in NetBox that no longer appear in the CSV (candidates to delete once empty):")
    for slug in sorted(types):
        if slug not in used:
            print(f"  {slug}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("NETBOX_URL"))
    ap.add_argument("--token", default=os.environ.get("NETBOX_TOKEN"))
    ap.add_argument("--go", action="store_true", help="actually rename and import")
    ap.add_argument("--only", help="limit to one slug")
    ap.add_argument("--repoint", action="store_true",
                    help="move existing devices onto the device type named in 07_devices.csv")
    a = ap.parse_args()
    if not a.url or not a.token:
        sys.exit("set NETBOX_URL and NETBOX_TOKEN (or pass --url/--token)")
    root = a.url.rstrip("/")
    scheme = "Bearer" if a.token.startswith("nbt_") and "." in a.token else "Token"
    s = requests.Session()
    s.headers.update({"Authorization": f"{scheme} {a.token}", "Accept": "application/json"})

    def get(path, **params):
        r = s.get(root + path, params=params)
        r.raise_for_status()
        return r.json().get("results", [])

    if a.repoint:
        return repoint(s, root, a.go)

    renames, imports, skipped = [], [], []
    for row in csv.DictReader(open(os.path.join(HERE, "csv", "02_device_types.csv"))):
        model, slug, mfr = row["model"], row["slug"], row["manufacturer"]
        if a.only and slug != a.only:
            continue
        # existing NetBox type (match on manufacturer + model)
        have = [t for t in get("/api/dcim/device-types/", model=model)
                if (t.get("manufacturer") or {}).get("name") == mfr]
        # catalog: is our slug there?
        cat = []
        for q in (re.sub(r"\s*\(.*?\)", "", model).strip(), slug, model.split()[-1]):
            cat = [c for c in get("/api/plugins/ndx/catalog/", q=q, limit=200)
                   if c.get("type") == "device-type" and c["slug"] == slug]
            if cat:
                break
        if not cat:
            skipped.append(f"{mfr} {model}")
            continue
        if have and have[0]["slug"] != slug:
            renames.append((have[0]["id"], have[0]["slug"], slug, f"{mfr} {model}"))
        imports.append((slug, f"{mfr} {model}"))

    print("slug renames in NetBox:")
    for _id, old, new, name in renames:
        print(f"  {name}: {old} -> {new}")
    if not renames:
        print("  none")
    print("NDX imports:")
    for slug, name in imports:
        print(f"  {name} [{slug}]")
    print("left alone (not in catalog under our slug):")
    for n in skipped:
        print(f"  {n}")

    if not a.go:
        print("\ndry run: nothing changed. Add --go to apply.")
        return
    for _id, old, new, name in renames:
        r = s.patch(f"{root}/api/dcim/device-types/{_id}/", json={"slug": new})
        print(f"rename {name}: {r.status_code}" + ("" if r.ok else f" {r.text[:300]}"))
    if imports:
        # assumption: ndx_ids are catalog slugs; a 400 below names the problem if not
        r = s.post(root + "/api/plugins/ndx/import/", json={"ndx_ids": [i[0] for i in imports]})
        print(f"import: {r.status_code} {r.text[:800]}")


if __name__ == "__main__":
    main()
