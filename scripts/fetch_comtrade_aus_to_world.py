"""Fetch annual Australia -> WORLD trade data from UN Comtrade public API.

Pulls Australia as reporter, partner=World (code 0), flow=Export.

This is the world-total counterpart to fetch_comtrade.py (which pulls
Australia <-> Japan bilateral). Used by the new Aus->World regression
that compares the bilateral relationship against the global one.

Confidentiality check: a manual test (May 2026) confirmed that Australia
DOES report LNG exports at the world-aggregate level. The firm-level
confidentiality suppression that zeroes out Aus->Japan LNG does NOT
apply when the partner is "World" (the aggregate cannot reveal
firm-level destinations). Verified against external anchors:
  2018 LNG: $32B  (DFAT/EI: ~AUD 43B = ~USD 31B)
  2022 LNG: $63B  (LNG price spike; DFAT: ~AUD 90B = ~USD 62B)
  2024 iron ore: $82B (DFAT: ~AUD 116B = ~USD 77B)

Output: data/raw/comtrade_aus_to_world.csv with columns
  year, classification, hs_or_sitc_code, commodity,
  qty, net_weight_kg, value_usd
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
WORLD = 0

HS_TARGETS = [
    ("2701", "coal"),
    ("2704", "coke_semi_coke"),
    ("2711", "natural_gas_lng_gaseous"),
    ("271111", "lng_liquefied"),
    ("2601", "iron_ore"),
    ("TOTAL", "all_commodities"),
]
SITC_TARGETS = [
    ("321", "coal_coke_briquettes"),
    ("341", "gas_natural_manufactured"),
    ("281", "iron_ore_concentrates"),
    ("TOTAL", "all_commodities"),
]

HS_START, HS_END = 1988, 2024
SITC_START, SITC_END = 1962, 1987

BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/{cls}"
SLEEP = 0.7


def fetch(cls: str, code: str, year: int) -> dict | None:
    url = BASE.format(cls=cls)
    params = {
        "reporterCode": AUS,
        "period": year,
        "cmdCode": code,
        "flowCode": "X",
        "partnerCode": WORLD,
        "partner2Code": 0,
        "motCode": 0,
        "customsCode": "C00",
    }
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=60)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            print(f"  network err {type(e).__name__} {cls}/{code}/{year}  (attempt {attempt+1})")
            time.sleep(3 + attempt * 2)
            continue
        if r.status_code == 429:
            time.sleep(2 + attempt * 2)
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} for {cls}/{code}/{year}")
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


def harvest(classification: str, targets: list, years: range) -> pd.DataFrame:
    rows = []
    for year in years:
        for code, name in targets:
            rec = fetch(classification, code, year)
            time.sleep(SLEEP)
            if rec is None:
                continue
            rows.append(
                {
                    "year": year,
                    "classification": classification,
                    "hs_or_sitc_code": code,
                    "commodity": name,
                    "qty": rec.get("qty"),
                    "qty_unit_code": rec.get("qtyUnitCode"),
                    "net_weight_kg": rec.get("netWgt"),
                    "value_usd": rec.get("primaryValue"),
                }
            )
        print(f"  {classification} {year}: {len(rows)} rows so far")
    return pd.DataFrame(rows)


def main() -> None:
    print("Pulling HS (1988+) Aus->World ...")
    hs = harvest("HS", HS_TARGETS, range(HS_START, HS_END + 1))
    print(f"  -> {len(hs)} HS rows")

    print("Pulling SITC Rev. 1 (1962-1987) Aus->World ...")
    sitc = harvest("S1", SITC_TARGETS, range(SITC_START, SITC_END + 1))
    print(f"  -> {len(sitc)} SITC rows")

    out = pd.concat([hs, sitc], ignore_index=True)
    out = out.sort_values(["classification", "commodity", "year"]).reset_index(drop=True)
    out_path = RAW_DIR / "comtrade_aus_to_world.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows)")


if __name__ == "__main__":
    sys.exit(main())
