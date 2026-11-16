#!/usr/bin/env python3
"""Generate the deliberately MESSY handover spreadsheets for the NetBox demo.

Reads the canonical topology from rcc_model.py and layers representation
noise (inconsistent spellings, mixed formats, whitespace, dup rows) plus a
handful of planted DISCREPANCIES on top of it. Those discrepancies live
here, not in the model - the model itself is internally consistent.

Output: ~/Blackwood_RCC_NetBox_Demo/
  RCC_Equipment_Inventory.xlsx
  rack_layouts.xlsx
  RCC_IP_and_Networks.xlsx
  cabling_and_connections.xlsx

Clean NetBox-import CSVs are produced separately by gen_netbox_import.py.
"""

import os
import random
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from rcc_model import (D, SURPLUS, RACKS, PLACE, IPPLAN, ib_hosts,
                       RACK_IB_LEAF, eth_rows, ib_rows, con_rows, pwr_rows,
                       CIRCUITS, PROVIDERS, LOCAL_ASN, ANNOUNCED, FEEDS, PDUS, POWER_PANELS)

random.seed(1975)  # deterministic output

OUT = os.environ.get("RCC_OUT") or os.path.expanduser("~/Blackwood_RCC_NetBox_Demo")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------------------
# PLANTED DISCREPANCIES that only exist in the messy handover
# ---------------------------------------------------------------------------
# Ghost node: appears only in the cabling schedule, never in the inventory.
eth_rows = list(eth_rows) + [
    ["wr-cn-013", "iDRAC", "wr-mgmt-sw02", "Et40", "CAT6", "green", "3m",
     "TODO confirm - is this node installed?"],
]
wan_rnd = random.Random(77)
_short = {p["slug"]: p["short"] for p in PROVIDERS}
for _c in CIRCUITS:
    if _c["device"]:
        eth_rows.append([_c["device"], _c["port"], f"{_short[_c['provider']]} demarc",
                         _c["xconn"], "SMF LC/LC", "yellow", "3m",
                         wan_rnd.choice([f"circuit {_c['cid']}", f"{_short[_c['provider']]} uplink",
                                         f"WAN handoff ({_c['cid']})"])])
ib_rows = list(ib_rows) + [
    ["wr-cn-013", "ib0", "wr-ib-leaf02", "Port33", "HDR200 DAC", "1.5m", "TODO"],
]

def bare(ipval):
    """strip the /prefix so messy sheets look hand-entered, not exported."""
    return ipval.split("/")[0] if ipval else ""

# ---------------------------------------------------------------------------
# MESSY EXPORT HELPERS
# ---------------------------------------------------------------------------
MFR_VARIANTS = {
    "Dell": ["Dell", "DELL", "Dell Inc.", "Dell EMC"],
    "Arista": ["Arista", "Arista Networks", "arista"],
    "NVIDIA": ["NVIDIA", "Mellanox", "nVidia / Mellanox", "NVIDIA Networking"],
    "Palo Alto Networks": ["Palo Alto Networks", "PaloAlto", "Palo Alto"],
    "Cisco": ["Cisco", "Cisco Systems"],
    "Hitachi": ["Hitachi", "Hitachi Data Systems / BlueArc"],
    "Supermicro": ["Supermicro", "SuperMicro", "SMC"],
    "Lambda": ["Lambda", "Lambda Labs"],
}
def mfr_msg(canon, rnd):
    return rnd.choice(MFR_VARIANTS.get(canon, [canon]))

def u_msg(u_start, u_height, rnd):
    if u_height == 1:
        return rnd.choice([f"U{u_start}", str(u_start), f"{u_start}"])
    top = u_start + u_height - 1
    return rnd.choice([f"U{u_start}", f"{u_start}-{top}", f"U{u_start}-U{top}", str(u_start)])

def date_msg(base_year, rnd):
    import datetime
    m = rnd.randint(1, 12); dd = rnd.randint(1, 28)
    fmt = rnd.choice(["%m/%d/%Y", "%Y-%m-%d", "%d-%b-%y", "%b %Y", "%m/%d/%y"])
    return datetime.date(base_year, m, dd).strftime(fmt)

HDR_FILL = PatternFill("solid", fgColor="D9E1F2")
HDR_FONT = Font(bold=True)

def style_header(ws, ncol):
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
    ws.freeze_panes = "A2"

def autosize(ws):
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 48)

# ---------------------------------------------------------------------------
# FILE 1: RCC_Equipment_Inventory.xlsx
# ---------------------------------------------------------------------------
wb = Workbook()
wb.remove(wb.active)
rnd = random.Random(11)

INV_COLS = ["Property Tag", "Hostname", "Manufacturer", "Model", "Serial No.",
            "Function / Role", "Rack", "U", "Status", "PI / Owner",
            "Fund or Grant #", "Purchase Date", "Warranty End", "Notes"]

def tag(rnd):
    return rnd.choice([f"PC{rnd.randint(200000,299999)}", f"PC {rnd.randint(200000,299999)}",
                       "", "MISSING", f"pc{rnd.randint(200000,299999)}"])

def serial(mfr, rnd):
    if rnd.random() < 0.12:
        return ""
    pre = {"Dell": "", "Arista": "JPE", "NVIDIA": "MT", "Cisco": "FDO"}.get(mfr, "")
    body = "".join(rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(7))
    return f"{pre}{body}"

def inv_row(name, rnd):
    d = D[name]
    rk, us = PLACE[name]
    dispname = name + ("  " if rnd.random() < 0.15 else "")   # trailing whitespace
    py = rnd.choice([2018, 2019, 2020, 2021, 2021, 2022])
    status = d["status"]
    if name == "mdc-vmhost-03":
        status = "Active"   # PLANTED: ops sheet never updated after decommissioning
    return [
        tag(rnd), dispname, mfr_msg(d["mfr"], rnd), d["model"], serial(d["mfr"], rnd),
        d["role"], rk if rnd.random() > 0.05 else rk.replace("-", ""),
        u_msg(us, d["u_height"], rnd),
        status, d["pi"], d["fund"],
        date_msg(py, rnd), date_msg(py + rnd.randint(3, 5), rnd) if rnd.random() > 0.1 else "expired",
        d["notes"],
    ]

for site, sheet in [("MDC", "Marston DC"), ("WRDC", "West Ridge DC")]:
    ws = wb.create_sheet(sheet)
    ws.append(INV_COLS)
    names = [n for n in D if D[n]["site"] == site and n in PLACE]
    for n in names:
        row = inv_row(n, rnd)
        if n == "wr-gpu-004":
            # PLANTED: box moved H3 -> H4 in a maint window, inventory never updated
            row[6] = "WRDC-H3"
            row[7] = "U30-33"
            row[13] = "reinstalled after RMA - verify rack w/ facilities"
        ws.append(row)
    # planted duplicate rows
    if site == "WRDC":
        ws.append(inv_row("wr-cn-006", rnd))
    if site == "MDC":
        ws.append(inv_row("mdc-dns02", rnd))
    style_header(ws, len(INV_COLS))
    autosize(ws)

# Decommissioned / Surplus
ws = wb.create_sheet("Decommissioned-Surplus")
ws.append(["Hostname", "Manufacturer", "Model", "Function / Role", "Status", "Location", "Notes"])
for s in SURPLUS:
    ws.append([s["name"], s["mfr"], s["model"], s["role"], s["status"],
               rnd.choice(["MDC cage 3", "West Ridge loading dock", "Surplus warehouse", "MDC-B1"]),
               s["notes"]])
# planted conflict: vmhost-03 also here, but "Active" in the Marston DC tab
ws.append(["mdc-vmhost-03", "Dell", "PowerEdge R740", "VM Hypervisor", "Decommissioned 08/2024",
           "MDC-A2", "PSU failure, migrated VMs off, NOT yet removed from rack"])
style_header(ws, 7)
autosize(ws)

# ReadMe
ws = wb.create_sheet("ReadMe")
for row in [
    ["Blackwood University - Research Computing & Cyberinfrastructure (RCC)"],
    ["Data center equipment inventory - LAST FULL AUDIT: Spring 2023"],
    [""],
    ["Maintained by: RCC Operations (and whoever the current student worker is)"],
    ["Questions: rcc-ops@blackwood.edu  /  x7-4400"],
    [""],
    ["NOTES / KNOWN ISSUES:"],
    [" - U positions in older rows may be approximate. Trust rack_layouts.xlsx from Facilities."],
    [" - Some Property Control tags never got recorded when gear was grant-purchased direct."],
    [" - Condo (lab-owned) nodes are in here for tracking but billed separately - see chargeback sheet."],
    [" - 'expired' in Warranty End = we checked and it lapsed, exact date unknown."],
    [" - Serial numbers pulled from a mix of iDRAC, packing slips, and label photos. Some are wrong."],
]:
    ws.append(row)
ws["A1"].font = Font(bold=True, size=13)
autosize(ws)

wb.move_sheet("ReadMe", offset=-(len(wb.sheetnames) - 1))
wb.save(os.path.join(OUT, "RCC_Equipment_Inventory.xlsx"))

# ---------------------------------------------------------------------------
# FILE 2: rack_layouts.xlsx   (Facilities - one tab per rack, U-top -> U1)
# ---------------------------------------------------------------------------
wb = Workbook(); wb.remove(wb.active)
rnd = random.Random(22)

NAME_DRIFT = {   # facilities uses short/older names
    "wr-login-01": "login01", "wr-login-02": "login02",
    "wr-slurm-01": "slurm-ctl", "wr-slurm-02": "slurm-ctl-bak",
    "mdc-core-sw01": "core-sw-01", "mdc-core-sw02": "core-sw-02",
    "wr-ib-spine01": "IB-spine-A", "wr-ib-spine02": "IB-spine-B",
    "hpcstor2": "bluearc-head-a",
}

def occ_map(rk):
    """expand rack items into per-U occupancy for display."""
    meta = RACKS[rk]
    h = meta["height"]
    slots = {u: None for u in range(1, h + 1)}
    for (u_top, name, kind) in meta["items"]:
        if kind == "device":
            hh = D[name]["u_height"]
            label = NAME_DRIFT.get(name, name)
            for u in range(u_top - hh + 1, u_top + 1):
                slots[u] = ("DEVICE", label, name)
        else:
            slots[u_top] = ("FILLER", name, None)
    return slots, h

for rk, meta in RACKS.items():
    ws = wb.create_sheet(rk)
    ws.append([f"Rack {rk}", f"Site: {meta['site']}", f"{meta['height']}U",
               "PDU: 2x APC AP8853 (A/B feed, 208V 30A)"])
    ws.append(["U", "Equipment", "Type", "Notes"])
    slots, h = occ_map(rk)
    for u in range(h, 0, -1):
        s = slots[u]
        if s is None:
            if rnd.random() < 0.85:
                continue  # blank U's usually just omitted by facilities
            ws.append([f"U{u}", "", "blank", ""])
        elif s[0] == "FILLER":
            txt = s[1]
            if txt == "BLANK":
                ws.append([f"U{u}", "-- blanking panel --", "panel", ""])
            elif txt.startswith("RESERVED"):
                ws.append([f"U{u}", txt, "reserved", "do not populate"])
            else:
                ws.append([f"U{u}", txt, "infra", ""])
        else:
            _, label, canon = s
            note = ""
            if canon == "wr-gpu-004":
                note = "relocated from H3 during Aug maint window"
            if canon and D[canon]["role"].startswith("Condo"):
                note = f"LAB-OWNED ({D[canon]['pi']})"
            ws.append([f"U{u}", label, "device", note])
    ws.append([])
    ws.append(["Elevation last verified:", date_msg(2024, rnd), "by",
               rnd.choice(["J. Okafor (Facilities)", "DC Manager", "M. Tran"])])
    style_header(ws, 4)
    for c in range(1, 5):
        ws.cell(row=2, column=c).font = Font(bold=True)
        ws.cell(row=2, column=c).fill = HDR_FILL
    ws.cell(row=1, column=1).font = Font(bold=True, size=12)
    autosize(ws)

wb.save(os.path.join(OUT, "rack_layouts.xlsx"))

# ---------------------------------------------------------------------------
# FILE 3: RCC_IP_and_Networks.xlsx   (Network engineer)
# ---------------------------------------------------------------------------
wb = Workbook(); wb.remove(wb.active)
rnd = random.Random(33)

ws = wb.create_sheet("Subnets")
ws.append(["Name", "Network", "Mask / CIDR", "VLAN", "Gateway", "Site", "Purpose", "Notes"])
subnets = [
    ["MDC server mgmt", "10.64.0.0", "/24", "20", "10.64.0.1", "MDC", "hypervisors, DNS, core mgmt", ""],
    ["MDC IPMI", "10.64.10.0", "255.255.255.0", "10", "10.64.10.1", "MDC", "iDRAC / BMC", "isolated, no route off-campus"],
    ["WRDC HPC infra", "10.72.1.0", "/24", "40", "10.72.1.1", "WRDC", "login, scheduler, filesystem", ""],
    ["WRDC compute", "10.72.2.0", "/23", "50", "10.72.2.1", "WRDC", "cn + gpu + condo nodes", "recorded as two /24s in old docs"],
    ["WRDC compute (gpu)", "10.72.3.0", "/24", "60", "10.72.2.1", "WRDC", "gpu partition", "same L2 as 10.72.2.0, do not re-gateway"],
    ["WRDC IPMI/BMC", "10.72.20.0", "/24", "99", "10.72.20.1", "WRDC", "BMC for all WRDC nodes", ""],
    ["InfiniBand IPoIB", "172.16.0.0", "/22", "", "n/a", "WRDC", "IPoIB fabric addressing", "not routed"],
    ["Science DMZ", "192.0.2.0", "/24", "200", "192.0.2.1", "both", "Globus DTN, login public, perfSONAR", "friction-free path to Internet2"],
    ["Marston old lab net", "10.20.0.0", "/24", "?", "10.20.0.1", "MDC", "legacy Bio HPC lab", "DECOM? still see ARP. reclaim for WRDC BMC expansion"],
]
subnets += [
    ["WRRN MDC link", "198.51.100.0", "/31", "", "n/a", "MDC", "BGP peering to WRRN (R&E)", "ptp, provider is .0"],
    ["Cascade MDC link", "203.0.113.0", "255.255.255.254", "", "n/a", "MDC", "BGP peering to Cascade (transit)", ""],
    ["WRRN WRDC link", "198.51.100.2", "/31", "", "n/a", "WRDC", "BGP peering to WRRN 100G", "provider .2, us .3"],
    ["Lakeshore WRDC link", "203.0.113.2", "/31", "", "n/a", "WRDC", "BGP peering to Lakeshore (backup)", "ptp"],
]
for r in subnets:
    ws.append(r)
style_header(ws, 8); autosize(ws)

ws = wb.create_sheet("Host assignments")
ws.append(["Hostname", "Mgmt IP", "BMC / IPMI IP", "InfiniBand IP", "Public / DMZ IP", "DNS name", "Notes"])
def dns_for(n):
    if n in ("wr-login-01", "wr-login-02"):
        return f"{n.replace('wr-','').replace('-0','0')}.hpc.blackwood.edu"
    if n == "wr-dtn-01":
        return "dtn.hpc.blackwood.edu"
    if n.startswith("mdc-dns"):
        return f"{n}.rcc.blackwood.edu"
    return f"{n}.rcc.blackwood.edu" if rnd.random() > 0.25 else ""
allnames = [n for n in D if n in PLACE]
for n in allnames:
    p = IPPLAN.get(n, {})
    ws.append([n, bare(p.get("mgmt", "")), bare(p.get("bmc", "")), bare(p.get("ib", "")),
               bare(p.get("public", "")), dns_for(n),
               "" if rnd.random() > 0.15 else rnd.choice(["ping ok", "no response - check", "?", "DHCP reservation"])])
# a couple of messy freeform rows
ws.append(["wr-cn-005 (spare NIC)", "10.72.2.5 /24", "", "", "", "", "second 10G port, not in DNS"])
ws.append(["old bluearc", "10.20.0.15", "", "", "", "bluearc-head-a", "still pingable?? see Subnets tab note"])
style_header(ws, 7); autosize(ws)

ws = wb.create_sheet("VLANs")
ws.append(["VLAN ID", "Name", "Site", "Subnet(s)", "Notes"])
for r in [
    [10, "mdc-ipmi", "MDC", "10.64.10.0/24", ""],
    [20, "mdc-srv", "MDC", "10.64.0.0/24", ""],
    [40, "wr-infra", "WRDC", "10.72.1.0/24", ""],
    [50, "wr-compute", "WRDC", "10.72.2.0/23", "gpu shares this"],
    [60, "wr-gpu", "WRDC", "(see compute)", "legacy - being merged into 50"],
    [99, "wr-bmc", "WRDC", "10.72.20.0/24", ""],
    [200, "science-dmz", "both", "192.0.2.0/24", "ACL bypass path"],
    [250, "ib-mgmt", "WRDC", "10.72.1.0/24", "UFM appliance mgmt - shares infra subnet"],
]:
    ws.append(r)
style_header(ws, 5); autosize(ws)

ws = wb.create_sheet("IPMI-BMC")
ws.append(["Hostname", "BMC IP", "MAC (if known)", "Default creds changed?", "Notes"])
for n in allnames:
    p = IPPLAN.get(n, {})
    if p.get("bmc"):
        mac = "%02X:%02X:%02X:%02X:%02X:%02X" % tuple(rnd.randint(0, 255) for _ in range(6)) if rnd.random() > 0.4 else ""
        ws.append([n, bare(p["bmc"]), mac, rnd.choice(["yes", "yes", "yes", "NO - fix!", "unknown"]), ""])
style_header(ws, 5); autosize(ws)

ws = wb.create_sheet("InfiniBand")
ws.append(["Hostname", "IPoIB address", "HCA", "GUID (partial)", "Leaf switch", "Notes"])
for n in ib_hosts:
    if n not in PLACE:
        continue
    p = IPPLAN.get(n, {})
    rk = PLACE[n][0]
    leaf = RACK_IB_LEAF.get(rk, "?")
    guid = "0x" + "".join(rnd.choice("0123456789abcdef") for _ in range(8))
    ws.append([n, bare(p.get("ib", "")), rnd.choice(["ConnectX-6", "ConnectX-6", "ConnectX-5"]),
               guid, leaf, ""])
style_header(ws, 6); autosize(ws)

# --- WAN circuits + BGP peers (hand-kept by the network engineer) ---
PROV_VARIANTS = {"wrrn": ["WRRN", "Western Regional Research Network", "W.R.R.N."],
                 "cascade-fiber-networks": ["Cascade Fiber", "Cascade Fiber Networks, Inc.", "CFN"],
                 "lakeshore-telecom": ["Lakeshore Telecom", "Lakeshore Tel.", "LTN"]}
SITE_VARIANTS = {"MDC": ["MDC", "Marston", "Marston DC"], "WRDC": ["WRDC", "West Ridge", "WR"]}
BW_VARIANTS = {10_000_000: ["10G", "10 Gbps", "10000M"], 100_000_000: ["100G", "100 Gbps", "100GE"]}
ASN_OF = {p["slug"]: p["asn"] for p in PROVIDERS}

def asn_msg(n, r):
    return r.choice([f"AS{n}", str(n), f"ASN {n}", f"AS {n}"])

def cid_msg(cid, r, canonical):
    return cid if canonical else r.choice([cid.replace("-", " "), cid.lower(), cid])

ws = wb.create_sheet("WAN circuits")
ws.append(["Circuit ID", "Provider", "Service", "Bandwidth", "Site", "Handoff", "In service", "Notes"])
for i, c in enumerate(CIRCUITS):
    service = "R&E" if "r-and-e" in c["tags"] else "Internet transit"
    if c["install"]:
        import datetime
        y, m, d_ = (int(x) for x in c["install"].split("-"))
        inservice = datetime.date(y, m, d_).strftime(wan_rnd.choice(["%m/%d/%Y", "%Y-%m-%d", "%d-%b-%y", "%b %Y"]))
    else:
        inservice = "FY26 (?)"
    ws.append([cid_msg(c["cid"], wan_rnd, i == 0), wan_rnd.choice(PROV_VARIANTS[c["provider"]]),
               service, wan_rnd.choice(BW_VARIANTS[c["kbps"]]),
               wan_rnd.choice(SITE_VARIANTS[c["site"]]),
               f"{c['device']} {c['port']}" if c["device"] else "TBD", inservice,
               c["notes"] + (" - PLANNED, not cabled" if c["status"] == "planned" else "")])
ws.append(["CFN-MDC-1G-0188", "Cascade Fiber", "Internet", "1G", "Marston", "mdc-border-fw02 eth0",
           "09/2018", "DISCONNECTED 2021 - cancel? still on invoice"])
ws.append(["Internet2", "via WRRN", "R&E", "", "both", "n/a", "", "peering is through WRRN, not a separate circuit"])
style_header(ws, 8); autosize(ws)

ws = wb.create_sheet("BGP peers")
ws.append(["Peer", "Peer ASN", "Peer IP", "Our IP", "Our device", "Our ASN", "Type", "We announce", "Notes"])
bgp_notes = {"wrrn": ["md5 key in KeePass", "gets Internet2 routes"], "cascade-fiber-networks": ["prefer over backup, local-pref 200"],
             "lakeshore-telecom": ["backup only, prepend x2 outbound"]}
for c in CIRCUITS:
    if not c["device"]:
        continue
    peer_ip = c["peer_ip"].split("/")[0]
    our_ip = c["local_ip"].split("/")[0]
    ws.append([wan_rnd.choice(PROV_VARIANTS[c["provider"]]), asn_msg(ASN_OF[c["provider"]], wan_rnd),
               wan_rnd.choice([peer_ip, peer_ip + "/31"]), wan_rnd.choice([our_ip, our_ip + "/31"]),
               c["device"], asn_msg(LOCAL_ASN, wan_rnd),
               "R&E" if "r-and-e" in c["tags"] else ("transit (backup)" if "backup" in c["tags"] else "transit"),
               wan_rnd.choice([ANNOUNCED, ANNOUNCED.replace("/", " /")]),
               wan_rnd.choice(bgp_notes[c["provider"]])])
ws.append(["Cascade Fiber (old 1G)", "AS64502", "203.0.113.250", "", "mdc-border-fw02", "AS64500",
           "transit", ANNOUNCED, "DOWN since 2021, remove?"])
style_header(ws, 9); autosize(ws)

wb.save(os.path.join(OUT, "RCC_IP_and_Networks.xlsx"))

# ---------------------------------------------------------------------------
# FILE 4: cabling_and_connections.xlsx
# ---------------------------------------------------------------------------
wb = Workbook(); wb.remove(wb.active)

ws = wb.create_sheet("Ethernet")
ws.append(["A-end device", "A-end port", "B-end device", "B-end port", "Media", "Cable color", "Length", "Label / Notes"])
for r in eth_rows:
    ws.append(r)
style_header(ws, 8); autosize(ws)

ws = wb.create_sheet("InfiniBand")
ws.append(["A-end device", "A-end port", "B-end device", "B-end port", "Media", "Length", "Label / Notes"])
for r in ib_rows:
    ws.append(r)
style_header(ws, 7); autosize(ws)

ws = wb.create_sheet("Console-Serial")
ws.append(["Device", "Device port", "Console server", "Console port", "Cable", "Length", "Notes"])
for r in con_rows:
    ws.append(r)
style_header(ws, 7); autosize(ws)

ws = wb.create_sheet("Power")
ws.append(["Device", "PSU", "PDU", "Outlet", "Feed", "Role (ref)"])
for r in pwr_rows:
    ws.append(r)
ws.append(["wr-gpu-004", "PSU1", "WRDC-H4-PDU-A", "C19-3", "A feed", "moved - update PDU load calc!"])
ws.append(["wr-gpu-004", "PSU2", "WRDC-H4-PDU-B", "C19-3", "B feed", "moved - update PDU load calc!"])
style_header(ws, 6); autosize(ws)

ws = wb.create_sheet("ReadMe")
for row in [
    ["Structured cabling + connection schedule"],
    ["Compiled by NorthPoint Cabling Inc. for RCC, updated by RCC network eng ad hoc"],
    [""],
    ["Ethernet ports on Arista shown as EtN (interface index, not physical label)."],
    ["'DAC' = direct-attach copper, 'AOC' = active optical, 'MPO' = 12f trunk to patch panel."],
    ["Rows marked TODO were not verified on the last walk-through."],
    ["Power: every device is dual-corded to the A and B PDU in its rack unless noted."],
]:
    ws.append(row)
ws["A1"].font = Font(bold=True, size=12); autosize(ws)
wb.move_sheet("ReadMe", offset=-(len(wb.sheetnames) - 1))
wb.save(os.path.join(OUT, "cabling_and_connections.xlsx"))

racked = [n for n in D if n in PLACE]

# ---------------------------------------------------------------------------
# VERIFICATION
# ---------------------------------------------------------------------------
print("Output dir:", OUT)
for fn in sorted(os.listdir(OUT)):
    if fn.endswith((".xlsx", ".md")):
        print("  ", fn, f"({os.path.getsize(os.path.join(OUT, fn))} bytes)")
print()
print("Racked devices:", len(racked),
      "| MDC", sum(1 for n in racked if D[n]['site'] == 'MDC'),
      "| WRDC", sum(1 for n in racked if D[n]['site'] == 'WRDC'))
print("Ethernet cable rows:", len(eth_rows))
print("InfiniBand cable rows:", len(ib_rows))
print("Console rows:", len(con_rows))
print("Power rows:", len(pwr_rows))
print("Surplus entries:", len(SURPLUS))
for n in ib_hosts:
    if n in PLACE and not IPPLAN.get(n, {}).get("ib"):
        print("WARN: ib host without IB ip:", n)
print("\nOK")
