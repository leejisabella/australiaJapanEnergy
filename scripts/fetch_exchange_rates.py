"""Fetch annual official exchange rates from the World Bank.

Indicator: PA.NUS.FCRF -- Official exchange rate (LCU per US$, period average).
We pull JPY/USD and AUD/USD and derive AUD/JPY.

Output: data/raw/exchange_rates.csv  (year, jpy_per_usd, aud_per_usd, jpy_per_aud)
"""
from __future__ import annotations

import sys
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

START_YEAR, END_YEAR = 1960, 2024
INDICATOR = "PA.NUS.FCRF"


def fetch(country_iso3: str) -> pd.DataFrame:
    url = (
        f"https://api.worldbank.org/v2/country/{country_iso3}/indicator/{INDICATOR}"
        f"?format=json&date={START_YEAR}:{END_YEAR}&per_page=500"
    )
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    payload = r.json()
    rows = [
        {"year": int(rec["date"]), "value": rec["value"]}
        for rec in (payload[1] or [])
    ]
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def main() -> None:
    jpy = fetch("JPN").rename(columns={"value": "jpy_per_usd"})
    aud = fetch("AUS").rename(columns={"value": "aud_per_usd"})
    df = jpy.merge(aud, on="year", how="outer")
    df["jpy_per_aud"] = df["jpy_per_usd"] / df["aud_per_usd"]
    out = RAW_DIR / "exchange_rates.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {out} ({len(df)} rows)")
    print(df.head(3))
    print(df.tail(3))


if __name__ == "__main__":
    sys.exit(main())
