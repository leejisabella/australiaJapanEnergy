"""Fetch APAC-as-reporter LNG imports from Australia (mirror data).

Aus-reported bilateral LNG suffers from firm-level confidentiality
suppression - the same issue that motivates using JPN-import mirror in
fetch_comtrade.py. The CHN/KOR/etc. import mirrors give the true flow.

Pulls each APAC partner as reporter, partner=AUS, flow=M, HS 2711 only.
Coal (HS 2701) is not suppressed in AUS-as-reporter so we keep that.

Output: data/raw/comtrade_apac_lng_mirror.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"

AUS = 36
REPORTERS = [
    ("CHN", 156),
    ("KOR", 410),
    ("THA", 764),
    ("MYS", 458),
    ("SGP", 702),
    ("VNM", 704),
]

HS_START, HS_END = 1988, 2024
BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
SLEEP = 0.7


def fetch(reporter: int, year: int) -> dict | None:
    params = {
        "reporterCode": reporter,
        "period": year,
        "cmdCode": "2711",
        "flowCode": "M",
        "partnerCode": AUS,
        "partner2Code": 0,
        "motCode": 0,
        "customsCode": "C00",
    }
    for attempt in range(5):
        try:
            r = requests.get(BASE, params=params, timeout=60)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            print(f"  network err {type(e).__name__} {reporter}/{year} (attempt {attempt+1})")
            time.sleep(3 + attempt * 2)
            continue
        if r.status_code == 429:
            time.sleep(2 + attempt * 2)
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} for {reporter}/{year}")
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
    total = (HS_END - HS_START + 1) * len(REPORTERS)
    done = 0
    print(f"Pulling {total} LNG mirror cells (6 reporters x {HS_END-HS_START+1} years) ...")
    for iso, code in REPORTERS:
        for year in range(HS_START, HS_END + 1):
            rec = fetch(code, year)
            time.sleep(SLEEP)
            done += 1
            if rec is None:
                continue
            rows.append({
                "year": year,
                "reporter_iso": iso,
                "value_usd": rec.get("primaryValue"),
                "net_weight_kg": rec.get("netWgt"),
            })
            if year % 5 == 0:
                print(f"  {iso} {year}: {done}/{total} done, {len(rows)} rows")

    out = pd.DataFrame(rows).sort_values(["reporter_iso", "year"]).reset_index(drop=True)
    out_path = RAW_DIR / "comtrade_apac_lng_mirror.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows)")


if __name__ == "__main__":
    sys.exit(main())
