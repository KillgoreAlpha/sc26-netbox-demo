#!/usr/bin/env python3
"""Idempotent loader for the Blackwood RCC demo data.

Pushes the CSVs in ./csv/ into a NetBox 4.x instance via the REST API,
in dependency order. Safe to re-run: every object is matched on a natural
key and created only if missing (existing objects are left untouched).

    pip install pynetbox
    export NETBOX_URL=https://netbox.example.edu
    export NETBOX_TOKEN=0123456789abcdef...
    python3 load_netbox.py                 # load / top up
    python3 load_netbox.py --wipe          # remove every demo object
    python3 load_netbox.py --dry-run       # print what would happen

Only objects named in the CSVs are ever touched, so this is safe to point
at a NetBox that already has other data - but use a demo instance anyway.
"""

import argparse
import csv
import os
import sys

CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv")


def rows(name):
    with open(os.path.join(CSV_DIR, name)) as f:
        return list(csv.DictReader(f))


def b(v):
    return str(v).strip().lower() in ("1", "true", "yes")


def i(v):
    return int(v) if str(v).strip() else None


class Loader:
    def __init__(self, nb, dry):
        self.nb, self.dry = nb, dry
        self.cache = {}
        self.created = self.skipped = 0

    def _key(self, ep, **lk):
        return (ep, tuple(sorted(lk.items())))

    def goc(self, ep_path, lookup, defaults):
        """get-or-create; returns the record (or a fake in dry-run)."""
        ep = self._ep(ep_path)
        ck = self._key(ep_path, **lookup)
        if ck in self.cache:
            return self.cache[ck]
        # dry-run placeholders have negative ids; they can't exist in NetBox
        fake_ref = any(isinstance(v, int) and v < 0 for v in lookup.values())
        existing = None if fake_ref else ep.get(**lookup)
        if existing:
            print(f"  = {ep_path}: {lookup}")
            self.skipped += 1
            self.cache[ck] = existing
            return existing
        # *_id keys are filter names; the create payload wants the plain field
        payload = {**{(k[:-3] if k.endswith("_id") else k): v for k, v in lookup.items()}, **defaults}
        if self.dry:
            print(f"  + {ep_path}: {payload}")
            self.created += 1
            rec = _Fake(payload)
        else:
            print(f"  + {ep_path}: {payload}")
            rec = ep.create(payload)
            self.created += 1
        self.cache[ck] = rec
        return rec

    def _ep(self, path):
        obj = self.nb
        for part in path.split("."):
            obj = getattr(obj, part)
        return obj

    # -- resolvers (cached) ------------------------------------------------
    def site(self, name):
        return self.goc("dcim.sites", {"name": name},
                        {"slug": _slug(name), "status": "active"})

    def location(self, site_name, name):
        return self.goc("dcim.locations", {"name": name},
                        {"slug": _slug(name), "site": self.site(site_name).id,
                         "status": "active"})

    def role(self, name):
        return self.goc("dcim.device_roles", {"name": name},
                        {"slug": _slug(name), "color": "9e9e9e"})

    def mfr(self, name):
        return self.goc("dcim.manufacturers", {"name": name}, {"slug": _slug(name)})

    def dtype(self, model):
        return self.cache[("dt", model)]

    def device(self, name):
        return self.goc("dcim.devices", {"name": name}, {})

    def interface(self, dev_name, if_name):
        ck = ("if", dev_name, if_name)
        if ck not in self.cache:
            try:
                self.cache[ck] = self.nb.dcim.interfaces.get(
                    device=dev_name, name=if_name)
            except Exception:
                # dry-run: the device was never created, so NetBox rejects the filter
                if not self.dry:
                    raise
                self.cache[ck] = None
        return self.cache[ck]

    def vlan(self, vid):
        return self.cache.get(("vlan", int(vid)))


class _Fake:
    _n = 0
    def __init__(self, d):
        _Fake._n += 1
        self.id = -_Fake._n
        self.__dict__.update({k: v for k, v in d.items() if not hasattr(self, k)})
    def __getattr__(self, k):
        return None


def _slug(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------------------------------------------------------------------------
def load(nb, dry):
    L = Loader(nb, dry)

    for r in rows("01_manufacturers.csv"):
        rec = L.goc("dcim.manufacturers", {"slug": r["slug"]}, {"name": r["name"]})
        L.cache[L._key("dcim.manufacturers", name=r["name"])] = rec

    for r in rows("02_device_types.csv"):
        rec = L.goc("dcim.device_types", {"slug": r["slug"]},
                    {"model": r["model"], "manufacturer": L.mfr(r["manufacturer"]).id,
                     "u_height": float(r["u_height"]),
                     "is_full_depth": b(r["is_full_depth"])})
        L.cache[("dt", r["model"])] = rec

    for r in rows("03_device_roles.csv"):
        rec = L.goc("dcim.device_roles", {"slug": r["slug"]},
                    {"name": r["name"], "color": r["color"], "vm_role": b(r["vm_role"])})
        L.cache[L._key("dcim.device_roles", name=r["name"])] = rec

    for r in rows("04_sites.csv"):
        rec = L.goc("dcim.sites", {"slug": r["slug"]},
                    {"name": r["name"], "status": r["status"],
                     "facility": r["facility"], "description": r["description"],
                     "latitude": float(r["latitude"]), "longitude": float(r["longitude"])})
        L.cache[L._key("dcim.sites", name=r["name"])] = rec
        # sites created by an earlier run have no coordinates yet (the WAN map needs them)
        if not dry and getattr(rec, "latitude", None) is None:
            rec.update({"latitude": float(r["latitude"]), "longitude": float(r["longitude"])})

    for r in rows("05_locations.csv"):
        rec = L.goc("dcim.locations", {"slug": r["slug"]},
                    {"name": r["name"], "site": L.site(r["site"]).id, "status": r["status"]})
        L.cache[L._key("dcim.locations", name=r["name"])] = rec

    # rack types (NetBox 4.3+) carry the outer dimensions the floorplan plugin draws to scale
    for r in rows("05a_rack_types.csv"):
        rec = L.goc("dcim.rack_types", {"slug": r["slug"]},
                    {"model": r["model"], "manufacturer": L.mfr(r["manufacturer"]).id,
                     "form_factor": r["form_factor"], "width": int(r["width"]),
                     "u_height": int(r["u_height"]),
                     "outer_width": int(r["outer_width"]),
                     "outer_depth": int(r["outer_depth"]),
                     "outer_unit": r["outer_unit"]})
        L.cache[("rt", r["model"])] = rec

    for r in rows("06_racks.csv"):
        sid = L.site(r["site"]).id
        d = {"location": L.location(r["site"], r["location"]).id, "status": r["status"]}
        if r.get("rack_type"):
            # width / u_height come from the rack type
            d["rack_type"] = L.cache[("rt", r["rack_type"])].id
        else:
            d.update(width=int(r["width"]), u_height=int(r["u_height"]))
        L.goc("dcim.racks", {"name": r["name"], "site_id": sid}, d)

    for r in rows("07_devices.csv"):
        L.goc("dcim.devices", {"name": r["name"]},
              {"device_type": L.dtype(r["device_type"]).id,
               "role": L.role(r["role"]).id,
               "site": L.site(r["site"]).id,
               "location": L.location(r["site"], r["location"]).id,
               "rack": L.goc("dcim.racks", {"name": r["rack"],
                                            "site_id": L.site(r["site"]).id}, {}).id,
               "position": float(r["position"]), "face": r["face"],
               "status": r["status"], "description": r["description"]})

    for r in rows("08_vlans.csv"):
        rec = L.goc("ipam.vlans", {"vid": int(r["vid"])},
                    {"name": r["name"], "status": r["status"]})
        L.cache[("vlan", int(r["vid"]))] = rec

    for r in rows("09_prefixes.csv"):
        d = {"status": r["status"], "description": r["description"]}
        if r["vlan"]:
            d["vlan"] = L.vlan(r["vlan"]).id
        L.goc("ipam.prefixes", {"prefix": r["prefix"]}, d)

    for r in rows("10_interfaces.csv"):
        L.goc("dcim.interfaces",
              {"device_id": L.device(r["device"]).id, "name": r["name"]},
              {"type": r["type"], "enabled": b(r["enabled"]),
               "mgmt_only": b(r["mgmt_only"])})

    for r in rows("11_ip_addresses.csv"):
        iface = L.interface(r["device"], r["interface"])
        rec = L.goc("ipam.ip_addresses", {"address": r["address"]},
                    {"status": r["status"], "dns_name": r["dns_name"],
                     "description": r["description"],
                     "assigned_object_type": "dcim.interface",
                     "assigned_object_id": iface.id if iface else None})
        if b(r["is_primary"]) and not dry and iface:
            dev = L.device(r["device"])
            if not getattr(dev, "primary_ip4", None):
                dev.update({"primary_ip4": rec.id})

    made = skipped = 0
    for r in rows("12_cables.csv"):
        a = L.interface(r["side_a_device"], r["side_a_name"])
        z = L.interface(r["side_b_device"], r["side_b_name"])
        if not dry and (a is None or z is None):
            print(f"  ! cable {r['side_a_device']}:{r['side_a_name']} - missing endpoint")
            continue
        if not dry and getattr(a, "cable", None):
            print(f"  = cable {r['side_a_device']}:{r['side_a_name']} <-> "
                  f"{r['side_b_device']}:{r['side_b_name']}")
            skipped += 1
            continue
        payload = {"a_terminations": [{"object_type": "dcim.interface",
                                       "object_id": a.id if a else None}],
                   "b_terminations": [{"object_type": "dcim.interface",
                                       "object_id": z.id if z else None}],
                   "type": r["type"] or None, "status": r["status"],
                   "label": r["label"], "color": r["color"]}
        if r["length"]:
            payload["length"] = float(r["length"])
            payload["length_unit"] = r["length_unit"]
        print(f"  + cable {r['side_a_device']}:{r['side_a_name']} <-> "
              f"{r['side_b_device']}:{r['side_b_name']}")
        if not dry:
            nb.dcim.cables.create(payload)
        made += 1

    made += load_wan(L, nb, dry)
    made += load_power(L, nb, dry)
    load_bgp(L, nb, dry)

    print(f"\ndone. objects created: {L.created + made}, "
          f"already present: {L.skipped + skipped}")


CUSTOM_FIELDS = [("bgp_peer_asn", "BGP peer ASN"), ("bgp_local_asn", "BGP local ASN")]


def load_wan(L, nb, dry):
    """Providers, circuits, ASNs, circuit cabling and BGP peering IPs (core NetBox only).

    BGP sessions are not a core object, so each peering is recorded as the /31
    IP pair on the handoff, tagged bgp-peer and carrying the two ASNs as custom
    fields. Returns the number of cables created.
    """
    for r in rows("12a_tags.csv"):
        L.goc("extras.tags", {"slug": r["slug"]}, {"name": r["name"], "color": r["color"]})
    for name, label in CUSTOM_FIELDS:
        L.goc("extras.custom_fields", {"name": name},
              {"object_types": ["ipam.ipaddress"], "type": "integer",
               "label": label, "filter_logic": "loose"})

    rir = L.goc("ipam.rirs", {"slug": "rfc5398"},
                {"name": "Documentation (RFC 5398)", "is_private": True})
    asn = {}
    for r in rows("16_asns.csv"):
        asn[int(r["asn"])] = L.goc("ipam.asns", {"asn": int(r["asn"])},
                                   {"rir": rir.id, "description": r["description"]})
        for sname in filter(None, r["sites"].split(";")):
            site = L.site(sname)
            have = [a.id for a in (getattr(site, "asns", None) or [])]
            if not dry and asn[int(r["asn"])].id not in have:
                site.update({"asns": have + [asn[int(r["asn"])].id]})

    prov = {}
    for r in rows("13_providers.csv"):
        prov[r["name"]] = L.goc("circuits.providers", {"slug": r["slug"]},
                                {"name": r["name"], "description": r["description"],
                                 "asns": [asn[int(r["asn"])].id]})
    net = {}
    for r in rows("14_provider_networks.csv"):
        net[r["name"]] = L.goc("circuits.provider_networks", {"name": r["name"]},
                               {"provider": prov[r["provider"]].id})
    ctype = {}
    for r in rows("15_circuit_types.csv"):
        ctype[r["name"]] = L.goc("circuits.circuit_types", {"slug": r["slug"]},
                                 {"name": r["name"], "color": r["color"]})

    circ = {}
    for r in rows("17_circuits.csv"):
        d = {"provider": prov[r["provider"]].id, "type": ctype[r["type"]].id,
             "status": r["status"], "commit_rate": int(r["commit_rate_kbps"]),
             "description": r["description"],
             "tags": [{"slug": t} for t in r["tags"].split(";") if t]}
        if r["install_date"]:
            d["install_date"] = r["install_date"]
        circ[r["cid"]] = L.goc("circuits.circuits", {"cid": r["cid"]}, d)

    term = {}
    for r in rows("18_circuit_terminations.csv"):
        target = (L.site(r["termination"]) if r["termination_type"] == "dcim.site"
                  else net[r["termination"]])
        d = {"termination_type": r["termination_type"], "termination_id": target.id,
             "port_speed": int(r["port_speed_kbps"]), "description": r["description"]}
        if r["xconnect_id"]:
            d["xconnect_id"] = r["xconnect_id"]
        term[(r["cid"], r["term_side"])] = L.goc(
            "circuits.circuit_terminations",
            {"circuit_id": circ[r["cid"]].id, "term_side": r["term_side"]}, d)

    made = 0
    for r in rows("19_wan_cables.csv"):
        t = term[(r["cid"], r["term_side"])]
        iface = L.interface(r["device"], r["interface"])
        if not dry and iface is None:
            print(f"  ! {r['cid']}: {r['device']}:{r['interface']} not found")
            continue
        if not dry and (getattr(t, "cable", None) or getattr(iface, "cable", None)):
            print(f"  = cable {r['cid']} <-> {r['device']}:{r['interface']}")
            continue
        payload = {"a_terminations": [{"object_type": "circuits.circuittermination",
                                       "object_id": t.id}],
                   "b_terminations": [{"object_type": "dcim.interface",
                                       "object_id": iface.id if iface else None}],
                   "type": r["type"], "status": r["status"], "label": r["label"],
                   "color": r["color"], "length": float(r["length"]),
                   "length_unit": r["length_unit"]}
        print(f"  + cable {r['cid']} <-> {r['device']}:{r['interface']}")
        if not dry:
            nb.dcim.cables.create(payload)
        made += 1

    for r in rows("20_wan_ip_addresses.csv"):
        d = {"status": r["status"], "description": r["description"],
             "tags": [{"slug": t} for t in r["tags"].split(";") if t],
             "custom_fields": {"bgp_peer_asn": int(r["bgp_peer_asn"]),
                               "bgp_local_asn": int(r["bgp_local_asn"])}}
        if r["device"]:
            iface = L.interface(r["device"], r["interface"])
            if iface is not None:
                d["assigned_object_type"] = "dcim.interface"
                d["assigned_object_id"] = iface.id
            elif not dry:
                print(f"  ! {r['address']}: {r['device']}:{r['interface']} not found")
        L.goc("ipam.ip_addresses", {"address": r["address"]}, d)
    return made


def load_power(L, nb, dry):
    """Power panels, per-rack A/B feeds, rack PDUs, PSU ports and the power cables.

    Chain per PSU: device PSU -> PDU outlet; PDU input -> power feed. The outlets
    are linked to the PDU input, so NetBox can roll draw up to each feed's
    utilization. Returns the number of cables created.
    """
    for r in rows("21_power_panels.csv"):
        L.goc("dcim.power_panels", {"name": r["name"], "site_id": L.site(r["site"]).id},
              {"location": L.location(r["site"], r["location"]).id,
               "description": r["description"]})
    for r in rows("22_power_feeds.csv"):
        panel = L.goc("dcim.power_panels", {"name": r["panel"], "site_id": L.site(r["site"]).id}, {})
        rack = L.goc("dcim.racks", {"name": r["rack"], "site_id": L.site(r["site"]).id}, {})
        L.goc("dcim.power_feeds", {"name": r["name"], "power_panel_id": panel.id},
              {"rack": rack.id, "status": r["status"], "type": r["type"],
               "supply": r["supply"], "phase": r["phase"], "voltage": int(r["voltage"]),
               "amperage": int(r["amperage"]), "max_utilization": int(r["max_utilization"])})

    pdu_in = {}
    for r in rows("23_pdus.csv"):
        sid = L.site(r["site"]).id
        pdu = L.goc("dcim.devices", {"name": r["name"]},
                    {"device_type": L.dtype(r["model"]).id, "role": L.role(r["role"]).id,
                     "site": sid, "location": L.location(r["site"], r["location"]).id,
                     "rack": L.goc("dcim.racks", {"name": r["rack"], "site_id": sid}, {}).id,
                     "status": "active"})
        inlet = L.goc("dcim.power_ports", {"device_id": pdu.id, "name": "Input"},
                      {"type": r["inlet_type"]})
        pdu_in[r["name"]] = (pdu, inlet)
        # outlets in one bulk POST per PDU, skipping any that already exist
        have = set() if dry or pdu.id < 0 else {o.name for o in
                                               nb.dcim.power_outlets.filter(device_id=pdu.id)}
        want = ([(f"C13-{n}", "iec-60320-c13") for n in range(1, int(r["c13_outlets"]) + 1)]
                + [(f"C19-{n}", "iec-60320-c19") for n in range(1, int(r["c19_outlets"]) + 1)])
        new = [{"device": pdu.id, "name": n, "type": t, "power_port": inlet.id}
               for n, t in want if n not in have]
        if len(want) - len(new):
            print(f"  = {r['name']}: {len(want) - len(new)} power outlets")
        if new:
            print(f"  + {r['name']}: {len(new)} power outlets")
            if not dry:
                nb.dcim.power_outlets.create(new)
        L.created += len(new)

    for r in rows("24_power_ports.csv"):
        L.goc("dcim.power_ports", {"device_id": L.device(r["device"]).id, "name": r["name"]},
              {"type": r["type"], "maximum_draw": int(r["maximum_draw"]),
               "allocated_draw": int(r["allocated_draw"])})

    made = 0
    if dry:
        n = len(rows("25_power_cables.csv")) + len(pdu_in)
        print(f"  + {n} power cables (PSU -> outlet, PDU input -> feed)")
        return n

    ports = {(p.device.name, p.name): p for p in nb.dcim.power_ports.all()}
    outlets = {(o.device.name, o.name): o for o in nb.dcim.power_outlets.all()}

    def cable(a_type, a, z_type, z, **extra):
        if getattr(a, "cable", None) or getattr(z, "cable", None):
            print(f"  = power cable {extra.get('label', '')}")
            return 0
        print(f"  + power cable {extra.get('label', '')}")
        nb.dcim.cables.create({"a_terminations": [{"object_type": a_type, "object_id": a.id}],
                               "b_terminations": [{"object_type": z_type, "object_id": z.id}],
                               "type": "power", "status": "connected", **extra})
        return 1

    for r in rows("25_power_cables.csv"):
        psu, outlet = ports.get((r["device"], r["port"])), outlets.get((r["pdu"], r["outlet"]))
        if psu is None or outlet is None:
            print(f"  ! power cable {r['device']}:{r['port']} -> {r['pdu']}:{r['outlet']} - missing end")
            continue
        made += cable("dcim.powerport", psu, "dcim.poweroutlet", outlet,
                      label=r["label"], color=r["color"])
    for r in rows("23_pdus.csv"):
        feed = nb.dcim.power_feeds.get(name=r["feed"])
        inlet = ports.get((r["name"], "Input"))
        if feed is None or inlet is None:
            print(f"  ! {r['name']} input -> {r['feed']} - missing end")
            continue
        made += cable("dcim.powerport", inlet, "dcim.powerfeed", feed, label=f"{r['name']} feed")
    return made


def load_bgp(L, nb, dry):
    """eBGP sessions for the netbox-bgp plugin (/api/plugins/bgp/session/).

    Needs the plugin and the WAN IPs and ASNs from load_wan, which runs first.
    Skips with a message if the plugin's API is missing.
    """
    if not dry:
        try:
            nb.plugins.bgp.session.count()
        except Exception as e:
            print(f"  ! BGP plugin API not reachable, skipping sessions: {e}")
            return
    for r in rows("26_bgp_sessions.csv"):
        d = {"status": r["status"], "description": r["description"],
             "site": L.site(r["site"]).id, "device": L.device(r["device"]).id}
        ips = {}
        for k in ("local_address", "remote_address"):
            ip = L.goc("ipam.ip_addresses", {"address": r[k]}, {})
            ips[k] = ip.id
        asns = {k: L.goc("ipam.asns", {"asn": int(r[k])}, {}).id
                for k in ("local_asn", "remote_asn")}
        d.update(local_address=ips["local_address"], remote_address=ips["remote_address"],
                 local_as=asns["local_asn"], remote_as=asns["remote_asn"])
        L.goc("plugins.bgp.session", {"name": r["name"]}, d)


def wipe(nb, dry):
    names = {r["name"] for r in rows("07_devices.csv")}
    racks = {r["name"] for r in rows("06_racks.csv")}
    prefixes = {r["prefix"] for r in rows("09_prefixes.csv")}
    vids = {int(r["vid"]) for r in rows("08_vlans.csv")}
    loc_slugs = {r["slug"] for r in rows("05_locations.csv")}
    site_slugs = {r["slug"] for r in rows("04_sites.csv")}

    def kill(qs, label):
        n = 0
        for obj in qs:
            print(f"  - {label}: {obj}")
            if not dry:
                obj.delete()
            n += 1
        print(f"  {label}: {n} removed")

    names |= {r["name"] for r in rows("23_pdus.csv")}
    # devices (cascades interfaces, cable terminations, IP assignments)
    for name in names:
        d = nb.dcim.devices.get(name=name)
        if d:
            kill([d], f"device {name}")
    kill([ip for ip in nb.ipam.ip_addresses.all()
          if getattr(ip, "assigned_object", None) is None
          and str(ip).split("/")[0].startswith(("10.64.", "10.72.", "172.16.", "192.0.2.",
                                                "198.51.100.", "203.0.113."))],
         "orphan demo IP")
    try:
        for r in rows("26_bgp_sessions.csv"):
            kill(nb.plugins.bgp.session.filter(name=r["name"]), f"bgp session {r['name']}")
    except Exception as e:
        print(f"  (bgp sessions skipped: {e})")
    for r in rows("22_power_feeds.csv"):
        kill(nb.dcim.power_feeds.filter(name=r["name"]), f"power feed {r['name']}")
    for r in rows("21_power_panels.csv"):
        kill(nb.dcim.power_panels.filter(name=r["name"]), f"power panel {r['name']}")
    for r in rows("17_circuits.csv"):
        kill(nb.circuits.circuits.filter(cid=r["cid"]), f"circuit {r['cid']}")
    for r in rows("13_providers.csv"):
        kill(nb.circuits.providers.filter(slug=r["slug"]), f"provider {r['slug']}")
    for r in rows("16_asns.csv"):
        kill(nb.ipam.asns.filter(asn=int(r["asn"])), f"asn {r['asn']}")
    for p in prefixes:
        kill(nb.ipam.prefixes.filter(prefix=p), f"prefix {p}")
    for vid in vids:
        kill(nb.ipam.vlans.filter(vid=vid), f"vlan {vid}")
    for r in racks:
        kill(nb.dcim.racks.filter(name=r), f"rack {r}")
    for s in loc_slugs:
        kill(nb.dcim.locations.filter(slug=s), f"location {s}")
    for s in site_slugs:
        kill(nb.dcim.sites.filter(slug=s), f"site {s}")
    print("\n(device types, manufacturers and roles are left in place - "
          "they are harmless and often shared)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("NETBOX_URL"))
    ap.add_argument("--token", default=os.environ.get("NETBOX_TOKEN"))
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.url or not a.token:
        sys.exit("set NETBOX_URL and NETBOX_TOKEN (or pass --url/--token)")

    import pynetbox
    nb = pynetbox.api(a.url, token=a.token)
    nb.http_session.headers["User-Agent"] = "blackwood-rcc-demo-loader"

    if a.wipe:
        wipe(nb, a.dry_run)
    else:
        load(nb, a.dry_run)


if __name__ == "__main__":
    main()
