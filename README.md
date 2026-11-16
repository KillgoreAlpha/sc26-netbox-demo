# SC26 NetBox demo: Death by a Thousand Spreadsheets

Slides and demo data for the SC26 talk "Death by a Thousand Spreadsheets: Consolidating
Infrastructure Data with NetBox" (Neuvys Technologies).

The demo follows a fictional university research computing group, Blackwood RCC, with two
data centers, 57 racked devices, 20 virtual machines and a handoff spread across four messy spreadsheets. The
repo holds the deliberately messy spreadsheets, the clean NetBox import data, and scripts that
load it into a NetBox 4.x instance.

## Layout

| Path | What it is |
|---|---|
| `slides/NetBox Demo (Neuvys template).pptx` | The presentation, with speaker notes |
| `demo/rcc_model.py` | Single source of truth: racks, devices, IPs, WAN, power |
| `demo/gen_demo.py` | Generates the messy spreadsheets (`RCC_*.xlsx`, `cabling_and_connections.xlsx`, `rack_layouts.xlsx`) |
| `demo/gen_netbox_import.py` | Generates the clean CSVs in `demo/netbox_import/csv/` |
| `demo/netbox_import/` | Loader, floor plan, NDX, verify, cleanup and teardown scripts. See its `README.md` |

## Quick start

```
pip install pynetbox requests
export NETBOX_URL=https://your-instance.example.com
export NETBOX_TOKEN='nbt_<key>.<secret>'      # or a v1 token
cd demo/netbox_import
python3 load_netbox.py --dry-run
python3 load_netbox.py
```

Use a throwaway NetBox instance. `cleanup_netbox.py` and `load_netbox.py --wipe` delete objects.
All names, ASNs (RFC 5398 range) and IP addresses (documentation ranges and private space) are
fictional. Never commit a NetBox token.

To regenerate the data after editing `rcc_model.py`: `python3 demo/gen_netbox_import.py`, and
`RCC_OUT=. python3 demo/gen_demo.py` for the spreadsheets.
