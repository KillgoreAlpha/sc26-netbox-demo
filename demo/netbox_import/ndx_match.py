#!/usr/bin/env python3
"""Compare our 17 device types with the NetBox Data Exchange (NDX) catalog.

Read-only. For each row of csv/02_device_types.csv it searches the NDX catalog
on your NetBox and reports whether the catalog has the same slug (an NDX
import will update our type in place), the same model under a different slug
(add a SLUG_OVERRIDE in gen_netbox_import.py), or no match.

    export NETBOX_URL=...  NETBOX_TOKEN='nbt_<key>.<secret>'
    python3 ndx_match.py                 # compare
    python3 ndx_match.py --probe-import  # also POST an EMPTY body to /import/ to
                                         # learn its required fields (rejected, changes nothing)
"""

import argparse
import csv
import os
import re
import sys

import requests

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv", "02_device_types.csv")


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("NETBOX_URL"))
    ap.add_argument("--token", default=os.environ.get("NETBOX_TOKEN"))
    ap.add_argument("--probe-import", action="store_true")
    a = ap.parse_args()
    if not a.url or not a.token:
        sys.exit("set NETBOX_URL and NETBOX_TOKEN (or pass --url/--token)")
    base = a.url.rstrip("/") + "/api/plugins/ndx"
    scheme = "Bearer" if a.token.startswith("nbt_") and "." in a.token else "Token"
    s = requests.Session()
    s.headers.update({"Authorization": f"{scheme} {a.token}", "Accept": "application/json"})

    def search(q):
        r = s.get(base + "/catalog/", params={"q": q, "limit": 50})
        r.raise_for_status()
        return [x for x in r.json().get("results", []) if x.get("type") == "device-type"]

    suggest = []
    for row in csv.DictReader(open(CSV)):
        model, slug, mfr = row["model"], row["slug"], row["manufacturer"]
        # try the full model, then the model without a "(...)" suffix, then the first word
        queries = [model, re.sub(r"\s*\(.*?\)", "", model).strip(), model.split()[0]]
        hits = []
        for q in dict.fromkeys(queries):
            hits = search(q)
            if hits:
                break
        by_slug = next((h for h in hits if h["slug"] == slug), None)
        by_model = next((h for h in hits if norm(h["model"]) == norm(model)
                         or norm(h["model"]) == norm(re.sub(r"\s*\(.*?\)", "", model))), None)
        if by_slug:
            print(f"  = {mfr} {model}: same slug in catalog ({slug})")
        elif by_model:
            print(f"  ~ {mfr} {model}: catalog slug is {by_model['slug']!r}, ours is {slug!r}")
            suggest.append(((row["manufacturer"], model), by_model["slug"]))
        else:
            near = ", ".join(f"{h['model']} [{h['slug']}]" for h in hits[:3]) or "nothing"
            print(f"  ? {mfr} {model}: no match. nearest: {near}")

    if suggest:
        print("\nAdd to SLUG_OVERRIDE in gen_netbox_import.py:")
        for (m, mo), sl in suggest:
            print(f'    ("{m}", "{mo}"): "{sl}",')

    if a.probe_import:
        r = s.post(base + "/import/", json={})
        print(f"\nPOST {{}} to /import/ -> {r.status_code}: {r.text[:800]}")


if __name__ == "__main__":
    main()
