"""Fetch annual Australia -> APAC partner trade data from UN Comtrade.

Pulls Australia as reporter, partner = each of (CHN, KOR, THA, MYS, SGP, VNM)
for coal (HS 2701) and natural gas / LNG (HS 2711) from 1988-2024. Japan is
already covered by fetch_comtrade.py.

Used to build an "Aus -> APAC" aggregate (Japan + the six above) for the
energy-export comparison plot.

Output: data/raw/comtrade_aus_to_apac.csv with columns
  year, partner_iso, classification, hs_or_sitc_code, commodity, value_usd
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

AUS = 36
PARTNERS = [
    ("CHN", 156),
    ("KOR", 410),
    ("THA", 764),
    ("MYS", 458),
    ("SGP", 702),
    ("VNM", 704),
]

HS_TARGETS = [
    ("2701", "coal"),
    ("2711", "natural_gas_lng_gaseous"),
]

HS_START, HS_END = 1988, 2024

BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
SLEEP = 0.7


def fetch(code: str, year: int, partner: int) -> dict | None:
    params = {
        "reporterCode": AUS,
        "period": year,
        "cmdCode": code,
        "flowCode": "X",
        "partnerCode": partner,
        "partner2Code": 0,
        "motCode": 0,
        "customsCode": "C00",
    }
    for attempt in range(5):
        try:
            r = requests.get(BASE, params=params, timeout=60)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            print(f"  network err {type(e).__name__} {code}/{year}/{partner}  (attempt {attempt+1})")
            time.sleep(3 + attempt * 2)
            continue
        if r.status_code == 429:
            time.sleep(2 + attempt * 2)
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} for {code}/{year}/{partner}")
            return None
        try:
            payload = r.json()
        except ValueError:
            return None
        if "statusCode" in payload:
            time.sleep(2 + attempt * 2)
            continue
        data = payload.get("data") or []
        return data[0] if data else None
    return None


def main() -> None:
    rows = []
    total = (HS_END - HS_START + 1) * len(HS_TARGETS) * len(PARTNERS)
    done = 0
    print(f"Pulling {total} cells: 6 partners x 2 commodities x {HS_END-HS_START+1} years ...")
    for iso, pcode in PARTNERS:
        for year in range(HS_START, HS_END + 1):
            for code, name in HS_TARGETS:
                rec = fetch(code, year, pcode)
                time.sleep(SLEEP)
                done += 1
                if rec is None:
                    continue
                rows.append({
                    "year": year,
                    "partner_iso": iso,
                    "classification": "HS",
                    "hs_or_sitc_code": code,
                    "commodity": name,
                    "value_usd": rec.get("primaryValue"),
                    "net_weight_kg": rec.get("netWgt"),
                })
            if year % 5 == 0:
                print(f"  {iso} {year}: {done}/{total} done, {len(rows)} rows")

    out = pd.DataFrame(rows)
    out = out.sort_values(["partner_iso", "commodity", "year"]).reset_index(drop=True)
    out_path = RAW_DIR / "comtrade_aus_to_apac.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows)")


if __name__ == "__main__":
    sys.exit(main())
