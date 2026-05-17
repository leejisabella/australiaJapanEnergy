"""Fetch macroeconomic indicators from the World Bank API.

No API key required. Pulls Japan and Australia GDP plus a small set of
controls that will be useful for the regression.

Output: data/raw/world_bank_macro.csv (long format: country, year, indicator, value)
"""
from __future__ import annotations

import sys
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

INDICATORS = {
    "NY.GDP.MKTP.CD": "gdp_current_usd",
    "NY.GDP.MKTP.KD": "gdp_constant_2015_usd",
    "NV.IND.TOTL.CD": "industry_value_added_current_usd",
    "EG.USE.PCAP.KG.OE": "energy_use_per_capita_kgoe",
    "EG.IMP.CONS.ZS": "energy_imports_pct_use",
    "NE.EXP.GNFS.CD": "exports_goods_services_current_usd",
}

COUNTRIES = ["JPN", "AUS"]
START_YEAR, END_YEAR = 1960, 2024


def fetch_indicator(country: str, indicator: str) -> pd.DataFrame:
    url = (
        f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
        f"?format=json&date={START_YEAR}:{END_YEAR}&per_page=500"
    )
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if len(payload) < 2 or payload[1] is None:
        return pd.DataFrame(columns=["country", "year", "indicator_code", "value"])
    rows = [
        {
            "country": country,
            "year": int(rec["date"]),
            "indicator_code": indicator,
            "value": rec["value"],
        }
        for rec in payload[1]
    ]
    return pd.DataFrame(rows)


def main() -> None:
    frames = []
    for country in COUNTRIES:
        for code in INDICATORS:
            df = fetch_indicator(country, code)
            print(f"  {country} {code}: {len(df)} rows, {df['value'].notna().sum()} non-null")
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["indicator_name"] = out["indicator_code"].map(INDICATORS)
    out = out[["country", "year", "indicator_code", "indicator_name", "value"]]
    out = out.sort_values(["country", "indicator_code", "year"]).reset_index(drop=True)
    out_path = OUT_DIR / "world_bank_macro.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows)")


if __name__ == "__main__":
    sys.exit(main())
