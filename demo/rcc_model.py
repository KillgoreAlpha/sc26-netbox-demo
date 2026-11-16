#!/usr/bin/env python3
"""Canonical topology for the Blackwood University RCC NetBox demo.

This module is the single source of truth. It contains NO randomness and
writes NO files - it just builds the data structures that both exporters
consume:

  gen_demo.py            -> the deliberately messy handover spreadsheets
  gen_netbox_import.py   -> clean NetBox 4.x bulk-import CSVs

The messy exporter layers representation noise and a handful of planted
DISCREPANCIES on top of this model. Those discrepancies live in
gen_demo.py, not here - here everything is internally consistent, which
is exactly the "after" state a NetBox migration converges on.

Exports: D, SURPLUS, RACKS, PLACE, IPPLAN, SUBNETS, VLANS,
         ib_hosts, compute, eth_rows, ib_rows, con_rows, pwr_rows,
         RACK_MGMT_SW, RACK_IB_LEAF, POWER_W, POWER_PANELS, PDUS, FEEDS
"""

# ---------------------------------------------------------------------------
# 1. DEVICES  (role, canonical manufacturer, model, U height)
# ---------------------------------------------------------------------------
D = {}

def dev(name, site, role, mfr, model, u, status="Active", pi="", fund="", notes=""):
    D[name] = dict(name=name, site=site, role=role, mfr=mfr, model=model,
                   u_height=u, status=status, pi=pi, fund=fund, notes=notes)

# --- MDC : Marston Data Center (main campus) ---
dev("mdc-border-fw01", "MDC", "Firewall", "Palo Alto Networks", "PA-3260", 2, notes="HA pair active")
dev("mdc-border-fw02", "MDC", "Firewall", "Palo Alto Networks", "PA-3260", 2, notes="HA pair standby")
dev("mdc-core-sw01",   "MDC", "Core Switch", "Arista", "DCS-7050SX3-48YC8-F", 1)
dev("mdc-core-sw02",   "MDC", "Core Switch", "Arista", "DCS-7050SX3-48YC8-F", 1)
dev("mdc-oob-sw01",    "MDC", "OOB/Console Switch", "Cisco", "Catalyst 2960-48TT-L", 1)
dev("mdc-dns01", "MDC", "DNS/DHCP", "Dell", "PowerEdge R640", 1)
dev("mdc-dns02", "MDC", "DNS/DHCP", "Dell", "PowerEdge R640", 1)
dev("mdc-vmhost-01", "MDC", "VM Hypervisor", "Dell", "PowerEdge R740", 2)
dev("mdc-vmhost-02", "MDC", "VM Hypervisor", "Dell", "PowerEdge R740", 2)
# canonical resolution of a planted discrepancy: PSU failed, VMs migrated off,
# box not yet pulled from the rack -> decommissioning, still racked.
dev("mdc-vmhost-03", "MDC", "VM Hypervisor", "Dell", "PowerEdge R740", 2,
    status="Decommissioning", notes="PSU failure Aug 2024, VMs migrated, awaiting removal (RCC-4471)")
dev("mdc-vmhost-04", "MDC", "VM Hypervisor", "Dell", "PowerEdge R740", 2)
dev("mdc-vmstor01", "MDC", "SAN/Disk Array", "Dell", "PowerVault ME4024", 2)
dev("mdc-backup01", "MDC", "Backup Server", "Dell", "PowerEdge R740xd", 2)
dev("hpcstor2", "MDC", "Legacy NAS", "Hitachi", "HNAS 4060", 3,
    notes="old research NAS, decom planned FY25. aka bluearc-head-a")
dev("mdc-globus-dtn-legacy", "MDC", "Data Transfer Node", "Supermicro", "SuperServer 6018R-MT", 1,
    notes="replaced by wr-dtn-01, keep till migration done")

# --- WRDC : West Ridge Data Center (HPC cluster) ---
dev("wr-core-sw01", "WRDC", "Core Switch", "Arista", "DCS-7280SR3-48YC8-F", 1)
dev("wr-core-sw02", "WRDC", "Core Switch", "Arista", "DCS-7280SR3-48YC8-F", 1)
for i in range(1, 5):
    dev(f"wr-mgmt-sw0{i}", "WRDC", "Mgmt Switch", "Dell", "PowerSwitch N2048", 1)
dev("wr-ib-spine01", "WRDC", "InfiniBand Spine", "NVIDIA", "QM8700", 1)
dev("wr-ib-spine02", "WRDC", "InfiniBand Spine", "NVIDIA", "QM8700", 1)
for i in range(1, 5):
    dev(f"wr-ib-leaf0{i}", "WRDC", "InfiniBand Leaf", "NVIDIA", "QM8700", 1)
dev("wr-login-01", "WRDC", "Login Node", "Dell", "PowerEdge R650", 1)
dev("wr-login-02", "WRDC", "Login Node", "Dell", "PowerEdge R650", 1)
dev("wr-slurm-01", "WRDC", "Scheduler", "Dell", "PowerEdge R640", 1, notes="Slurm controller (primary)")
dev("wr-slurm-02", "WRDC", "Scheduler", "Dell", "PowerEdge R640", 1, notes="Slurm controller (backup)")
dev("wr-lustre-mds01", "WRDC", "Lustre MDS", "Dell", "PowerEdge R740", 2)
dev("wr-lustre-mds02", "WRDC", "Lustre MDS", "Dell", "PowerEdge R740", 2)
for i in range(1, 5):
    dev(f"wr-lustre-oss0{i}", "WRDC", "Lustre OSS", "Dell", "PowerEdge R740xd", 2)
for i in range(1, 13):
    dev(f"wr-cn-{i:03d}", "WRDC", "Compute Node (CPU)", "Dell", "PowerEdge C6420", 1,
        fund="NSF-OAC-1929001", notes="general partition")
for i in range(1, 5):
    dev(f"wr-gpu-{i:03d}", "WRDC", "Compute Node (GPU)", "Dell", "PowerEdge XE8640", 4,
        fund="NSF-MRI-2018551")
dev("wr-dtn-01", "WRDC", "Data Transfer Node", "Dell", "PowerEdge R650", 1, notes="Globus DTN, Science DMZ")
# condo / lab-owned nodes (chargeback model)
dev("chem-gpu-01", "WRDC", "Condo Node (GPU)", "Supermicro", "GPU SuperServer SYS-422GA-NRT", 4,
    pi="Dr. Rekha Alvarez", fund="Chem Dept startup 6620-114", notes="lab-owned, condo model")
dev("dr-patel-node01", "WRDC", "Condo Node (CPU)", "Dell", "PowerEdge R6525", 1,
    pi="Dr. Amit Patel", fund="NIH R01-GM140xxx", notes="lab-owned, condo model")
dev("dr-patel-node02", "WRDC", "Condo Node (CPU)", "Dell", "PowerEdge R6525", 1,
    pi="Dr. Amit Patel", fund="NIH R01-GM140xxx", notes="lab-owned, condo model")

# decommissioned / surplus (not racked, not imported into NetBox as active)
SURPLUS = [
    dict(name="oldnfs", mfr="Whitebox / Silicon Mechanics", model="Storform R518", role="Legacy NFS",
         status="Surplus", notes="powered off 2022, awaiting Property Control pickup"),
    dict(name="mdc-vmhost-legacy1", mfr="Dell", model="PowerEdge R720", role="VM Hypervisor",
         status="Surplus", notes="out of warranty, drives wiped"),
    dict(name="hpc-sched-old", mfr="IBM", model="System x3550 M4", role="Scheduler",
         status="Surplus", notes="old Moab/Torque head node"),
    dict(name="wr-cn-old-0xx (x8)", mfr="Dell", model="PowerEdge C6320", role="Compute Node (CPU)",
         status="Surplus", notes="8 nodes, Sandy Bridge, donated to CS teaching lab"),
]

# ---------------------------------------------------------------------------
# 2. RACKS  (source of truth for U positions)
#    items: list of (u_top, item, kind)  kind in {"device", "filler"}
# ---------------------------------------------------------------------------
RACKS = {}

def rack(name, site, height, items):
    RACKS[name] = dict(site=site, height=height, items=items)

rack("MDC-A1", "MDC", 42, [
    (42, "mdc-border-fw01", "device"),
    (40, "mdc-border-fw02", "device"),
    (39, "PDU feed / cable mgmt", "filler"),
    (38, "mdc-core-sw01", "device"),
    (37, "mdc-core-sw02", "device"),
    (36, "mdc-oob-sw01", "device"),
    (35, "BLANK", "filler"),
    (34, "mdc-dns01", "device"),
    (33, "mdc-dns02", "device"),
    (32, "BLANK", "filler"),
    (2,  "RESERVED - network expansion", "filler"),
])
rack("MDC-A2", "MDC", 42, [
    (42, "mdc-vmhost-01", "device"),
    (40, "mdc-vmhost-02", "device"),
    (38, "mdc-vmhost-03", "device"),
    (36, "mdc-vmhost-04", "device"),
    (34, "mdc-vmstor01", "device"),
    (32, "mdc-backup01", "device"),
    (30, "BLANK", "filler"),
    (24, "hpcstor2", "device"),
    (18, "RESERVED", "filler"),
])
rack("MDC-B1", "MDC", 42, [
    (42, "mdc-globus-dtn-legacy", "device"),
    (41, "BLANK - rack mostly empty, tagged for surplus staging", "filler"),
])

rack("WRDC-H1", "WRDC", 48, [
    (48, "wr-core-sw01", "device"),
    (47, "wr-core-sw02", "device"),
    (46, "wr-mgmt-sw01", "device"),
    (45, "wr-ib-spine01", "device"),
    (44, "wr-ib-spine02", "device"),
    (43, "wr-ib-leaf01", "device"),
    (42, "BLANK", "filler"),
    (41, "wr-login-01", "device"),
    (40, "wr-login-02", "device"),
    (39, "wr-slurm-01", "device"),
    (38, "wr-slurm-02", "device"),
    (37, "wr-lustre-mds01", "device"),
    (35, "wr-lustre-mds02", "device"),
    (33, "wr-lustre-oss01", "device"),
    (31, "wr-lustre-oss02", "device"),
    (29, "wr-dtn-01", "device"),
    (12, "RESERVED - Phase 2", "filler"),
])
rack("WRDC-H2", "WRDC", 48, [
    (48, "wr-mgmt-sw02", "device"),
    (47, "wr-ib-leaf02", "device"),
    (46, "wr-cn-001", "device"),
    (45, "wr-cn-002", "device"),
    (44, "wr-cn-003", "device"),
    (43, "wr-cn-004", "device"),
    (42, "wr-cn-005", "device"),
    (41, "wr-cn-006", "device"),
    (40, "wr-cn-007", "device"),
    (39, "wr-cn-008", "device"),
    (38, "wr-cn-009", "device"),
    (37, "wr-cn-010", "device"),
    (36, "wr-cn-011", "device"),
    (35, "wr-cn-012", "device"),
    (34, "BLANK", "filler"),
    (20, "wr-lustre-oss03", "device"),
    (18, "wr-lustre-oss04", "device"),
    (10, "RESERVED - Phase 2", "filler"),
])
rack("WRDC-H3", "WRDC", 48, [
    (48, "wr-mgmt-sw03", "device"),
    (47, "wr-ib-leaf03", "device"),
    (46, "BLANK", "filler"),
    (45, "wr-gpu-001", "device"),
    (41, "wr-gpu-002", "device"),
    (37, "wr-gpu-003", "device"),
    (33, "RESERVED - Phase 2 GPU expansion", "filler"),
    (9,  "chem-gpu-01", "device"),
])
rack("WRDC-H4", "WRDC", 48, [
    (48, "wr-mgmt-sw04", "device"),
    (47, "wr-ib-leaf04", "device"),
    (46, "dr-patel-node01", "device"),
    (45, "dr-patel-node02", "device"),
    (44, "BLANK", "filler"),
    (40, "wr-gpu-004", "device"),   # canonical home after the Aug relocation from H3
    (36, "RESERVED - condo expansion", "filler"),
])

# canonical rack + bottom-U for every placed device
PLACE = {}
for _rk, _meta in RACKS.items():
    for (_u_top, _item, _kind) in _meta["items"]:
        if _kind == "device" and _item in D:
            PLACE[_item] = (_rk, _u_top - D[_item]["u_height"] + 1)

_missing = [n for n in D if n not in PLACE]
assert not _missing, f"devices not placed in any rack: {_missing}"
for n, (rk, us) in PLACE.items():
    top = us + D[n]["u_height"] - 1
    assert 1 <= us <= top <= RACKS[rk]["height"], f"{n} does not fit in {rk}"

# ---------------------------------------------------------------------------
# 3. IP ADDRESSING  (one coherent scheme)
# ---------------------------------------------------------------------------
# 10.64.0.0/24    MDC server mgmt/prod              VLAN 20
# 10.64.10.0/24   MDC IPMI / iDRAC                  VLAN 10
# 10.72.1.0/24    WRDC HPC infra (login/sched/fs)   VLAN 40
# 10.72.2.0/23    WRDC compute (cn + gpu + condo)   VLAN 50
# 10.72.20.0/24   WRDC IPMI / BMC                   VLAN 99
# 172.16.0.0/22   InfiniBand IPoIB fabric           (not routed)
# 192.0.2.0/24    Science DMZ (TEST-NET-1)          VLAN 200
#
# Prefix length carried per plane so the CSV exporter can emit real CIDRs.
PLANE_PREFIX = {"mgmt_mdc": 24, "mgmt_wr_infra": 24, "mgmt_compute": 23,
                "bmc_mdc": 24, "bmc_wr": 24, "ib": 22, "public": 24}

SUBNETS = [
    # (prefix, vlan_vid, status, description)
    ("10.64.0.0/24",   20,  "active",   "MDC server mgmt / prod"),
    ("10.64.10.0/24",  10,  "active",   "MDC IPMI / iDRAC (isolated)"),
    ("10.72.1.0/24",   40,  "active",   "WRDC HPC infra - login, scheduler, filesystem"),
    ("10.72.2.0/23",   50,  "active",   "WRDC compute - CPU + GPU + condo nodes"),
    ("10.72.20.0/24",  99,  "active",   "WRDC IPMI / BMC"),
    ("172.16.0.0/22",  None, "active",  "InfiniBand IPoIB fabric (not routed)"),
    ("192.0.2.0/24",   200, "active",   "Science DMZ - Globus DTN, login public, perfSONAR"),
]

VLANS = [
    # (vid, name, status)
    (10,  "mdc-ipmi",     "active"),
    (20,  "mdc-srv",      "active"),
    (40,  "wr-infra",     "active"),
    (50,  "wr-compute",   "active"),
    (99,  "wr-bmc",       "active"),
    (200, "science-dmz",  "active"),
]

IPPLAN = {}   # name -> dict(mgmt, bmc, ib, public), each value "a.b.c.d/len"

def _setip(name, **kw):
    IPPLAN.setdefault(name, {}).update(kw)

def _addr(base_net, host, plen):
    a, b, c, _ = base_net.split(".")
    return f"{a}.{b}.{c}.{host}/{plen}"

_mdc_infra = ["mdc-border-fw01", "mdc-border-fw02", "mdc-core-sw01", "mdc-core-sw02",
              "mdc-oob-sw01", "mdc-dns01", "mdc-dns02", "mdc-vmhost-01", "mdc-vmhost-02",
              "mdc-vmhost-03", "mdc-vmhost-04", "mdc-vmstor01", "mdc-backup01", "hpcstor2",
              "mdc-globus-dtn-legacy"]
for _idx, _n in enumerate(_mdc_infra, start=10):
    _setip(_n, mgmt=_addr("10.64.0.0", _idx, 24))
    if D[_n]["mfr"] in ("Dell", "Supermicro"):
        _setip(_n, bmc=_addr("10.64.10.0", _idx, 24))
_setip("mdc-border-fw01", public="192.0.2.2/24")
_setip("mdc-border-fw02", public="192.0.2.3/24")
_setip("mdc-globus-dtn-legacy", public="192.0.2.20/24")

_wr_infra = ["wr-core-sw01", "wr-core-sw02", "wr-mgmt-sw01", "wr-mgmt-sw02", "wr-mgmt-sw03",
             "wr-mgmt-sw04", "wr-ib-spine01", "wr-ib-spine02", "wr-ib-leaf01", "wr-ib-leaf02",
             "wr-ib-leaf03", "wr-ib-leaf04", "wr-login-01", "wr-login-02", "wr-slurm-01",
             "wr-slurm-02", "wr-lustre-mds01", "wr-lustre-mds02", "wr-lustre-oss01",
             "wr-lustre-oss02", "wr-lustre-oss03", "wr-lustre-oss04", "wr-dtn-01"]
for _idx, _n in enumerate(_wr_infra, start=10):
    _setip(_n, mgmt=_addr("10.72.1.0", _idx, 24))
    if D[_n]["mfr"] == "Dell":
        _setip(_n, bmc=_addr("10.72.20.0", _idx, 24))
_setip("wr-login-01", public="192.0.2.30/24")
_setip("wr-login-02", public="192.0.2.31/24")
_setip("wr-dtn-01", public="192.0.2.40/24")

compute = [f"wr-cn-{i:03d}" for i in range(1, 13)] + [f"wr-gpu-{i:03d}" for i in range(1, 5)] \
          + ["chem-gpu-01", "dr-patel-node01", "dr-patel-node02"]
for _idx, _n in enumerate(compute, start=1):
    _setip(_n, mgmt=f"10.72.2.{_idx}/23")
    _setip(_n, bmc=f"10.72.20.{100 + _idx}/24")

ib_hosts = ["wr-login-01", "wr-login-02", "wr-lustre-mds01", "wr-lustre-mds02",
            "wr-lustre-oss01", "wr-lustre-oss02", "wr-lustre-oss03", "wr-lustre-oss04",
            "wr-dtn-01"] + compute
for _idx, _n in enumerate(ib_hosts, start=10):
    _setip(_n, ib=f"172.16.0.{_idx}/22" if _idx < 254 else f"172.16.1.{_idx - 244}/22")

# ---------------------------------------------------------------------------
# 4. CABLING  (derived from topology rules; unique port per switch side)
# ---------------------------------------------------------------------------
eth_rows, ib_rows, con_rows, pwr_rows = [], [], [], []

RACK_MGMT_SW = {"WRDC-H1": "wr-mgmt-sw01", "WRDC-H2": "wr-mgmt-sw02",
                "WRDC-H3": "wr-mgmt-sw03", "WRDC-H4": "wr-mgmt-sw04"}
RACK_IB_LEAF = {"WRDC-H1": "wr-ib-leaf01", "WRDC-H2": "wr-ib-leaf02",
                "WRDC-H3": "wr-ib-leaf03", "WRDC-H4": "wr-ib-leaf04"}


# (psu_watts, typical_total_watts) per model. Each box is dual-PSU, so every
# PSU is allocated half of the typical load and rated at psu_watts.
POWER_W = {
    "PA-3260": (450, 330), "DCS-7050SX3-48YC8-F": (460, 200),
    "DCS-7280SR3-48YC8-F": (750, 260), "Catalyst 2960-48TT-L": (150, 60),
    "PowerSwitch N2048": (200, 70), "QM8700": (550, 290),
    "PowerEdge R640": (750, 300), "PowerEdge R650": (800, 350),
    "PowerEdge R6525": (1100, 450), "PowerEdge R740": (1100, 400),
    "PowerEdge R740xd": (1100, 450), "PowerEdge C6420": (1100, 400),
    "PowerEdge XE8640": (2800, 5200), "PowerVault ME4024": (580, 300),
    "HNAS 4060": (1000, 800), "SuperServer 6018R-MT": (750, 300),
    "GPU SuperServer SYS-422GA-NRT": (2200, 2400),
}
HIGH_DRAW_W = 1500   # PSUs above this plug into C19 outlets (C20 inlets), the rest C13/C14

def _psu_conn(model):
    return "C19-" if POWER_W[model][0] > HIGH_DRAW_W else "C13-"

def _port_alloc():
    counts = {}
    def nxt(key, prefix):
        counts[key] = counts.get(key, 0) + 1
        return f"{prefix}{counts[key]}"
    return nxt

_port = _port_alloc()

for _n, _d in D.items():
    _rk = PLACE[_n][0]

    # --- ethernet: mgmt + data ---
    if _d["role"] == "Firewall":
        eth_rows.append([_n, "eth1", "mdc-core-sw01", _port("mdc-core-sw01", "Et"),
                         "DAC", "black", "1m", f"{_n} <-> core"])
    elif _d["role"] == "Core Switch":
        peer = {"mdc-core-sw01": "mdc-core-sw02", "wr-core-sw01": "wr-core-sw02"}.get(_n)
        if peer:
            eth_rows.append([_n, "Et49", peer, "Et49", "DAC", "blue", "0.5m", "MLAG peer-link"])
            eth_rows.append([_n, "Et50", peer, "Et50", "DAC", "blue", "0.5m", "MLAG peer-link"])
        if _n == "wr-core-sw01":
            eth_rows.append([_n, "Et48", "mdc-core-sw01", _port("mdc-core-sw01", "Et"),
                             "SMF LC/LC", "yellow", "500m", "campus DWDM to Marston"])
    elif _d["site"] == "WRDC" and _rk in RACK_MGMT_SW:
        sw = RACK_MGMT_SW[_rk]
        if _n != sw:
            eth_rows.append([_n, "iDRAC" if _d["mfr"] == "Dell" else "mgmt0",
                             sw, _port(sw, "Et"), "CAT6", "green", "3m", "OOB mgmt"])
        else:
            # the rack's mgmt switch itself uplinks to the HPC core
            eth_rows.append([_n, "Et49", "wr-core-sw01", _port("wr-core-sw01", "Et"),
                             "DAC", "blue", "2m", "mgmt switch uplink"])
        if _d["role"] in ("Login Node", "Data Transfer Node", "Lustre OSS", "Lustre MDS", "Scheduler"):
            media = "AOC" if _d["role"] == "Data Transfer Node" else "DAC"
            eth_rows.append([_n, "eno1", "wr-core-sw01", _port("wr-core-sw01", "Et"),
                             media, "black", "3m", "25G data"])
    elif _d["site"] == "MDC":
        eth_rows.append([_n, "eno1", "mdc-core-sw01", _port("mdc-core-sw01", "Et"),
                         "CAT6" if _d["u_height"] < 2 else "DAC", "grey", "2m", "data"])
        if _d["mfr"] == "Dell":
            eth_rows.append([_n, "iDRAC", "mdc-oob-sw01", _port("mdc-oob-sw01", "Et"),
                             "CAT6", "green", "2m", "iDRAC"])

    # --- infiniband ---
    if _n in ib_hosts and _rk in RACK_IB_LEAF:
        leaf = RACK_IB_LEAF[_rk]
        hca_ports = 2 if "gpu" in _n else 1
        for k in range(hca_ports):
            ib_rows.append([_n, f"ib{k}", leaf, _port(leaf, "Port"),
                            "HDR200 DAC", "1.5m", f"{_n} HCA{k}"])
    if _d["role"] == "InfiniBand Leaf":
        for sp in ("wr-ib-spine01", "wr-ib-spine02"):
            ib_rows.append([_n, _port(_n, "uplink-"), sp, _port(sp, "Port"),
                            "HDR200 AOC", "10m", "leaf-spine uplink"])

    # --- console / serial (components only; cables out of scope for import) ---
    if _d["role"] in ("Firewall", "Core Switch", "OOB/Console Switch", "Mgmt Switch",
                      "Scheduler", "InfiniBand Spine", "InfiniBand Leaf", "DNS/DHCP", "Login Node"):
        con_rows.append([_n, "console", "mdc-oob-sw01", _port("mdc-oob-sw01-con", "async"),
                         "RJ45 rollover", "1.8m", ""])

    # --- power (dual feed) ---
    _pc = _psu_conn(_d["model"])
    pwr_rows.append([_n, "PSU1", f"{_rk}-PDU-A", _port(f"{_rk}-A", _pc), "A feed", _d["role"]])
    pwr_rows.append([_n, "PSU2", f"{_rk}-PDU-B", _port(f"{_rk}-B", _pc), "B feed", _d["role"]])


# ---------------------------------------------------------------------------
# 4. WAN / BGP  (fictional; ASNs from RFC 5398 documentation range, IPs from
#    TEST-NET-2/3, the announced prefix is the existing Science DMZ TEST-NET-1)
# ---------------------------------------------------------------------------
LOCAL_ASN = 64500          # Blackwood University, announced from both sites
ANNOUNCED = "192.0.2.0/24" # Science DMZ

PROVIDERS = [
    dict(name="Western Regional Research Network", short="WRRN", slug="wrrn", asn=64501,
         desc="Regional R&E network: Internet2 and research peering"),
    dict(name="Cascade Fiber Networks", short="CFN", slug="cascade-fiber-networks", asn=64502,
         desc="Commodity Internet transit"),
    dict(name="Lakeshore Telecom", short="LTN", slug="lakeshore-telecom", asn=64503,
         desc="Commodity Internet transit (West Ridge backup)"),
]

CIRCUIT_TYPES = [("R&E Network", "r-and-e-network", "3f51b5"),
                 ("Internet Transit", "internet-transit", "ff9800")]

TAGS = [("wan", "WAN", "9c27b0"), ("bgp-peer", "BGP peer", "2196f3"),
        ("r-and-e", "R&E", "3f51b5"), ("transit", "Transit", "ff9800"),
        ("backup", "Backup", "9e9e9e")]

# one row per circuit; device/port is our handoff, local_ip/peer_ip the /31 BGP link
CIRCUITS = [
    dict(cid="WRRN-MDC-10G-0417", provider="wrrn", ctype="R&E Network", status="active",
         kbps=10_000_000, site="MDC", install="2022-03-14", device="mdc-border-fw01",
         port="eth2", port_type="10gbase-x-sfpp", local_ip="198.51.100.1/31",
         peer_ip="198.51.100.0/31", xconn="MMR-04-17", tags=["wan", "r-and-e", "bgp-peer"],
         notes="Primary R&E uplink, Internet2 via WRRN"),
    dict(cid="CFN-MDC-10G-0392", provider="cascade-fiber-networks", ctype="Internet Transit",
         status="active", kbps=10_000_000, site="MDC", install="2021-09-30",
         device="mdc-border-fw02", port="eth2", port_type="10gbase-x-sfpp",
         local_ip="203.0.113.1/31", peer_ip="203.0.113.0/31", xconn="MMR-04-22",
         tags=["wan", "transit", "bgp-peer"], notes="Commodity Internet transit"),
    dict(cid="WRRN-WRDC-100G-0733", provider="wrrn", ctype="R&E Network", status="active",
         kbps=100_000_000, site="WRDC", install="2023-06-02", device="wr-core-sw01",
         port="Et51", port_type="100gbase-x-qsfp28", local_ip="198.51.100.3/31",
         peer_ip="198.51.100.2/31", xconn="WRDH-A-11", tags=["wan", "r-and-e", "bgp-peer"],
         notes="HPC R&E uplink, Science DMZ path"),
    dict(cid="LTN-WRDC-10G-1180", provider="lakeshore-telecom", ctype="Internet Transit",
         status="active", kbps=10_000_000, site="WRDC", install="2023-06-20",
         device="wr-core-sw02", port="Et16", port_type="25gbase-x-sfp28",
         local_ip="203.0.113.3/31", peer_ip="203.0.113.2/31", xconn="WRDH-A-14",
         tags=["wan", "transit", "backup", "bgp-peer"], notes="Backup transit, 5G CIR"),
    dict(cid="WRRN-WRDC-100G-0734", provider="wrrn", ctype="R&E Network", status="planned",
         kbps=100_000_000, site="WRDC", install="", device=None, port=None, port_type=None,
         local_ip=None, peer_ip=None, xconn="", tags=["wan", "r-and-e"],
         notes="Second diverse 100G R&E path, install FY26"),
]

def _net31(ip):
    a, b, c, d = ip.split("/")[0].split(".")
    return f"{a}.{b}.{c}.{int(d) & ~1}/31"

for _c in CIRCUITS:
    if _c["local_ip"]:
        _short = next(p["short"] for p in PROVIDERS if p["slug"] == _c["provider"])
        SUBNETS.append((_net31(_c["local_ip"]), None, "active",
                        f"WAN link {_c['cid']} ({_short} BGP peering)"))


# ---------------------------------------------------------------------------
# 5. POWER  (panels, per-rack A/B feeds, rack PDUs). Draw lives in POWER_W.
#    Default feed is 208 V single-phase 30 A; the GPU rack (WRDC-H3) gets 208 V 3-phase 60 A.
#    Panels are fictional; the A and B sides come from different panels.
# ---------------------------------------------------------------------------
POWER_PANELS = [
    dict(name="MDC-PNL-A", site="MDC", note="Marston B1 UPS-A distribution"),
    dict(name="MDC-PNL-B", site="MDC", note="Marston B1 UPS-B distribution"),
    dict(name="WRDC-PNL-A", site="WRDC", note="West Ridge hall panel A (generator-backed)"),
    dict(name="WRDC-PNL-B", site="WRDC", note="West Ridge hall panel B (generator-backed)"),
]
FEED_SPEC = {"WRDC-H3": dict(phase="three-phase", amps=60, conn="iec-60309-3p-e-6h")}
DEFAULT_FEED = dict(phase="single-phase", amps=30, conn="nema-l6-30p")
PDU_MODEL = ("Generic", "Rack PDU 0U 24xC13 6xC19")
PDU_C13, PDU_C19 = 24, 6

PDUS, FEEDS = [], []
for _rk, _meta in RACKS.items():
    _spec = {**DEFAULT_FEED, **FEED_SPEC.get(_rk, {})}
    for _side in "AB":
        FEEDS.append(dict(name=f"{_rk}-FEED-{_side}", panel=f"{_meta['site']}-PNL-{_side}",
                          rack=_rk, site=_meta["site"], side=_side, voltage=208,
                          amps=_spec["amps"], phase=_spec["phase"],
                          type="primary" if _side == "A" else "redundant"))
        PDUS.append(dict(name=f"{_rk}-PDU-{_side}", rack=_rk, site=_meta["site"], side=_side,
                         feed=f"{_rk}-FEED-{_side}", inlet=_spec["conn"]))


# ---------------------------------------------------------------------------
# VIRTUALIZATION  (MDC only; WRDC is bare-metal HPC)
# ---------------------------------------------------------------------------
# One vSphere cluster on the three live hypervisors. mdc-vmhost-03 is
# decommissioning (VMs migrated off after the PSU failure), so it hosts none.
CLUSTER_TYPES = [("VMware vSphere", "vmware-vsphere")]
CLUSTERS = [dict(name="mdc-vsphere01", type="VMware vSphere", site="MDC",
                 description="Marston production vSphere cluster (vmhost-03 pending removal)")]
VM_ROLES = [("Infrastructure VM", "infrastructure-vm", "3f51b5"),
            ("Research Service VM", "research-service-vm", "009688"),
            ("Campus Service VM", "campus-service-vm", "ff9800")]

VMS = []   # dicts: name, host, role, vcpus, memory_mb, disk_gb, ip, dns, status, owner, notes

def vm(name, host, role, vcpus, mem_gb, disk_gb, owner, notes="", status="Active", dns=None):
    VMS.append(dict(name=name, host=host, role=role, vcpus=vcpus, memory_mb=mem_gb * 1024,
                    disk_gb=disk_gb, owner=owner, notes=notes, status=status,
                    dns=dns or f"{name}.rcc.blackwood.edu"))

vm("mdc-ldap01",      "mdc-vmhost-01", "Infrastructure VM", 2, 8,  60,  "RCC ops", "directory (primary)")
vm("mdc-ldap02",      "mdc-vmhost-02", "Infrastructure VM", 2, 8,  60,  "RCC ops", "directory (replica)")
vm("mdc-monitor01",   "mdc-vmhost-01", "Infrastructure VM", 4, 16, 500, "RCC ops", "Prometheus + Grafana")
vm("mdc-syslog01",    "mdc-vmhost-02", "Infrastructure VM", 4, 16, 1000, "RCC ops", "central syslog")
vm("mdc-ansible01",   "mdc-vmhost-04", "Infrastructure VM", 2, 8,  100, "RCC ops", "config management")
vm("mdc-netbox01",    "mdc-vmhost-04", "Infrastructure VM", 4, 16, 200, "RCC ops", "DCIM and IPAM")
vm("mdc-ntp01",       "mdc-vmhost-01", "Infrastructure VM", 1, 2,  20,  "Network engineering", "stratum 2")
vm("mdc-jump01",      "mdc-vmhost-02", "Infrastructure VM", 2, 4,  40,  "RCC ops", "admin bastion")
vm("mdc-gitlab01",    "mdc-vmhost-04", "Research Service VM", 8, 32, 800, "RCC ops", "campus GitLab for research groups")
vm("mdc-jupyterhub01","mdc-vmhost-01", "Research Service VM", 16, 64, 500, "RCC ops", "teaching JupyterHub")
vm("mdc-rstudio01",   "mdc-vmhost-02", "Research Service VM", 8, 64, 300, "RCC ops", "RStudio Server")
vm("mdc-redcap01",    "mdc-vmhost-04", "Research Service VM", 4, 16, 250, "Dr. Maria Okafor", "REDCap survey platform")
vm("mdc-omero01",     "mdc-vmhost-01", "Research Service VM", 8, 32, 2000, "Dr. Rekha Alvarez", "microscopy image store")
vm("mdc-galaxy01",    "mdc-vmhost-02", "Research Service VM", 8, 32, 1500, "Dr. Amit Patel", "bioinformatics workflows")
vm("mdc-web01",       "mdc-vmhost-04", "Campus Service VM", 4, 8,  100, "RCC ops", "rcc.blackwood.edu")
vm("mdc-wiki01",      "mdc-vmhost-01", "Campus Service VM", 2, 8,  80,  "RCC ops", "RCC docs wiki")
vm("mdc-tickets01",   "mdc-vmhost-02", "Campus Service VM", 4, 16, 150, "RCC ops", "helpdesk")
vm("mdc-license01",   "mdc-vmhost-04", "Campus Service VM", 2, 4,  40,  "RCC ops", "FlexLM license server")
vm("mdc-oldlab-web",  "mdc-vmhost-01", "Campus Service VM", 2, 4,  60,  "Dr. Amit Patel",
   "legacy lab site, owner asked to retire", status="Offline")
vm("mdc-test01",      "mdc-vmhost-02", "Infrastructure VM", 2, 4,  40,  "RCC ops", "staging", status="Staged")

for _i, _v in enumerate(VMS, start=101):
    _v["ip"] = f"10.64.0.{_i}/24"
