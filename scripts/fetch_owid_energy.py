"""Pull Our World in Data consolidated energy dataset and extract Australia.

OWID stitches together IRENA, Ember, EI Statistical Review, and BP.
We keep a focused subset most relevant to the renewables-era model.

Output: data/raw/australia_renewable_energy.csv
"""
from __future__ import annotations

import sys
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://github.com/owid/energy-data/raw/master/owid-energy-data.csv"
LOCAL = RAW_DIR / "owid_energy_full.csv"

KEEP_COLS = [
    "year",
    "electricity_generation",
    "renewables_electricity",
    "renewables_share_elec",
    "renewables_share_energy",
    "solar_electricity",
    "wind_electricity",
    "hydro_electricity",
    "biofuel_electricity",
    "fossil_electricity",
    "coal_electricity",
    "gas_electricity",
    "primary_energy_consumption",
    "energy_per_gdp",
    "greenhouse_gas_emissions",
]


def main() -> None:
    if not LOCAL.exists():
        print(f"Downloading {URL}")
        r = requests.get(URL, timeout=180)
        r.raise_for_status()
        LOCAL.write_bytes(r.content)
    df = pd.read_csv(LOCAL)
    aus = df[df["country"] == "Australia"].copy()
    keep = [c for c in KEEP_COLS if c in aus.columns]
    out = aus[keep].sort_values("year").reset_index(drop=True)
    out_path = RAW_DIR / "australia_renewable_energy.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows, {len(keep)} cols)")
    print("Non-null counts on renewables columns (year >= 1990):")
    sub = out[out.year >= 1990]
    print(sub[keep].notna().sum())


if __name__ == "__main__":
    sys.exit(main())
