"""Fetch World Bank Pink Sheet annual commodity prices (nominal & real).

Pulls the Excel file directly from the World Bank and extracts the three
commodities most relevant to Australia-Japan energy trade:
  - Coal, Australian ($/mt)
  - Liquefied natural gas, Japan ($/mmbtu)
  - Iron ore, cfr spot ($/dmtu)

Output:
  data/raw/pink_sheet_prices.csv  (year, commodity, nominal_usd, real_2010_usd)
"""
from __future__ import annotations

import sys
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "18675f1d1639c7a34d463f59263ba0a2-0050012025/related/"
    "CMO-Historical-Data-Annual.xlsx"
)
LOCAL_XLSX = RAW_DIR / "pink_sheet.xlsx"

# Column index -> friendly name (from Pink Sheet row 6)
COMMODITIES = {
    1: "crude_oil_avg_usd_per_bbl",
    2: "crude_oil_brent_usd_per_bbl",
    5: "coal_australian_usd_per_mt",
    9: "lng_japan_usd_per_mmbtu",
    61: "iron_ore_cfr_spot_usd_per_dmtu",
}


def download() -> None:
    print(f"Downloading {URL}")
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    LOCAL_XLSX.write_bytes(r.content)
    print(f"  saved {LOCAL_XLSX} ({len(r.content):,} bytes)")


def extract(sheet: str, price_type: str) -> pd.DataFrame:
    raw = pd.read_excel(LOCAL_XLSX, sheet_name=sheet, header=None)
    # Year column is 0; first data row is 7
    rows = []
    for i in range(7, len(raw)):
        year_val = raw.iat[i, 0]
        if pd.isna(year_val):
            continue
        try:
            year = int(year_val)
        except (TypeError, ValueError):
            continue
        for col_idx, name in COMMODITIES.items():
            val = raw.iat[i, col_idx]
            rows.append({"year": year, "commodity": name, price_type: val})
    return pd.DataFrame(rows)


def main() -> None:
    if not LOCAL_XLSX.exists():
        download()
    nominal = extract("Annual Prices (Nominal)", "price_nominal_usd")
    real = extract("Annual Prices (Real)", "price_real_2010_usd")
    merged = nominal.merge(real, on=["year", "commodity"], how="outer")
    # Pink Sheet uses ".." for missing — coerce to NaN/numeric.
    for col in ("price_nominal_usd", "price_real_2010_usd"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged.sort_values(["commodity", "year"]).reset_index(drop=True)
    out = RAW_DIR / "pink_sheet_prices.csv"
    merged.to_csv(out, index=False)
    print(f"Wrote {out} ({len(merged)} rows)")
    summary = merged.groupby("commodity")["price_nominal_usd"].agg(["count", "min", "max"])
    print(summary)


if __name__ == "__main__":
    sys.exit(main())
