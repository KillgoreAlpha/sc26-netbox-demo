#!/usr/bin/env python3
"""Write the whole NDX catalog to ndx_catalog.txt (read-only).

    export NETBOX_URL=...  NETBOX_TOKEN='nbt_<key>.<secret>'
    python3 ndx_dump.py
One line per entry: type | manufacturer | model | slug | u_height | source
"""
import os
import sys

import requests

url = os.environ.get("NETBOX_URL", "").rstrip("/")
tok = os.environ.get("NETBOX_TOKEN", "")
if not url or not tok:
    sys.exit("set NETBOX_URL and NETBOX_TOKEN")
scheme = "Bearer" if tok.startswith("nbt_") and "." in tok else "Token"
h = {"Authorization": f"{scheme} {tok}", "Accept": "application/json"}

out, nxt = [], url + "/api/plugins/ndx/catalog/?limit=500"
while nxt:
    r = requests.get(nxt, headers=h)
    r.raise_for_status()
    d = r.json()
    out += d["results"]
    nxt = d.get("next")
    print(f"  fetched {len(out)} of {d.get('count')}", end="\r")

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ndx_catalog.txt")
with open(path, "w") as f:
    for x in sorted(out, key=lambda x: (x.get("type") or "", x.get("manufacturer") or "", x.get("model") or "")):
        f.write(" | ".join(str(x.get(k) if x.get(k) is not None else "") for k in
                           ("type", "manufacturer", "model", "slug", "u_height", "source")) + "\n")
print(f"\nwrote {len(out)} entries to {path}")
