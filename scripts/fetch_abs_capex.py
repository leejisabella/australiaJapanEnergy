"""Fetch Australian private new capital expenditure (mining sector) from ABS.

Source: ABS catalogue 5625.0 via the SDMX API (data.api.abs.gov.au).
Series key: M1.CUR.TOT.P01.20.AUS.Q
  - M1   = Actual Expenditure
  - CUR  = Current prices (nominal AUD millions)
  - TOT  = All asset types (buildings & structures + plant & equipment)
  - P01  = Mining (ANZSIC division B, aggregated)
  - 20   = Seasonally adjusted
  - AUS  = Australia (all states)
  - Q    = Quarterly

Output: data/raw/abs_mining_capex.csv  (year, quarter, capex_aud_million)
        data/raw/abs_mining_capex_annual.csv  (year, capex_aud_million)

Coverage: ~1987-Q3 onward (quarterly).
"""
from __future__ import annotations

import sys
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://data.api.abs.gov.au/rest/data/CAPEX/M1.CUR.TOT.P01.20.AUS.Q"


def main() -> None:
    print(f"Fetching {URL}")
    r = requests.get(
        URL,
        headers={"Accept": "application/vnd.sdmx.data+csv"},
        params={"startPeriod": "1987-Q1"},
        timeout=120,
    )
    r.raise_for_status()
    df = pd.read_csv(pd.io.common.StringIO(r.text))
    print(f"  {len(df)} rows fetched")

    df = df[["TIME_PERIOD", "OBS_VALUE", "UNIT_MEASURE", "UNIT_MULT"]].copy()
    df.columns = ["period", "value", "unit", "multiplier"]
    # ABS returns AUD millions (UNIT=AUD, MULT=6 means base*10^6)
    df["capex_aud_million"] = df["value"].astype(float)
    df["year"] = df["period"].str.slice(0, 4).astype(int)
    df["quarter"] = df["period"].str.slice(-1).astype(int)
    df = df.sort_values(["year", "quarter"]).reset_index(drop=True)

    quarterly = df[["year", "quarter", "capex_aud_million"]]
    quarterly_path = RAW_DIR / "abs_mining_capex.csv"
    quarterly.to_csv(quarterly_path, index=False)
    print(f"  wrote {quarterly_path} ({len(quarterly)} quarterly rows, "
          f"{quarterly.year.min()}-Q{quarterly[quarterly.year==quarterly.year.min()].quarter.min()} → "
          f"{quarterly.year.max()}-Q{quarterly[quarterly.year==quarterly.year.max()].quarter.max()})")

    # Annual aggregation - only keep years with all 4 quarters present
    counts = quarterly.groupby("year")["quarter"].count()
    full_years = counts[counts == 4].index
    annual = (quarterly[quarterly.year.isin(full_years)]
              .groupby("year")["capex_aud_million"]
              .sum()
              .reset_index())
    annual_path = RAW_DIR / "abs_mining_capex_annual.csv"
    annual.to_csv(annual_path, index=False)
    print(f"  wrote {annual_path} ({len(annual)} annual rows, "
          f"{annual.year.min()} → {annual.year.max()})")
    print("\nAnnual mining capex (AUD billions):")
    for _, row in annual.tail(10).iterrows():
        print(f"  {int(row.year)}: A${row.capex_aud_million/1000:>6.1f}B")


if __name__ == "__main__":
    sys.exit(main())
