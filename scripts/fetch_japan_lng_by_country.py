"""Fetch annual Japan-as-reporter LNG imports from each major supplier country.

Used to construct a country-year panel for Analysis 3 (staggered DiD across
LNG supplier cohorts). We query Japan-as-reporter (M flow) for HS 271111 and
HS 2711, and also pull Japan's TOTAL LNG imports so the country share can be
computed.

Mirrors the rate-limited pattern of fetch_comtrade.py.

Output: data/raw/comtrade_japan_lng_by_supplier.csv with columns
  year, classification, hs_code, commodity, partner_iso, partner_m49,
  qty, qty_unit_code, net_weight_kg, value_usd
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

JPN = 392

# Partner countries (M49 codes) — major LNG suppliers to Japan, 1970-2010.
# WORLD (code 0) gives Japan's total LNG imports for share denominator.
SUPPLIERS = [
    ("BRN", 96),    # Brunei (first cargo 1972)
    ("IDN", 360),   # Indonesia (1977)
    ("ARE", 784),   # United Arab Emirates (1977)
    ("MYS", 458),   # Malaysia (1983)
    ("AUS", 36),    # Australia (1989)
    ("QAT", 634),   # Qatar (1997)
    ("OMN", 512),   # Oman (2000)
    ("RUS", 643),   # Russia (Sakhalin, 2009) — useful as a late-treatment
    ("USA", 840),   # USA (2017) — never treated within sample, useful control
    ("WLD", 0),     # World total — denominator for share variable
]

# HS 271111 = LNG specifically (1996+); HS 2711 = all natural gas (1988+).
# For pre-1988 coverage we fall back to SITC Rev. 1 code 341 (gas, manufactured
# or natural). Comtrade SITC pre-1988 coverage of LNG is patchy but Indonesia
# and Brunei should be present from 1977 / 1972.
HS_TARGETS = [
    ("2711", "natural_gas_lng_gaseous"),
    ("271111", "lng_liquefied"),
]
SITC_TARGETS = [
    ("341", "gas_natural_manufactured"),
]

HS_START, HS_END = 1988, 2010
SITC_START, SITC_END = 1970, 1987

BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/{cls}"
SLEEP = 0.7  # seconds between requests


def fetch(cls: str, code: str, year: int, partner: int) -> dict | None:
    """One request: Japan-as-reporter, importing `code` from `partner` in `year`."""
    url = BASE.format(cls=cls)
    params = {
        "reporterCode": JPN,
        "period": year,
        "cmdCode": code,
        "flowCode": "M",
        "partnerCode": partner,
        "partner2Code": 0,
        "motCode": 0,
        "customsCode": "C00",
    }
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=60)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            print(f"  network err {type(e).__name__} {cls}/{code}/{year}/{partner}  (attempt {attempt+1})")
            time.sleep(3 + attempt * 2)
            continue
        if r.status_code == 429:
            time.sleep(2 + attempt * 2)
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} for {cls}/{code}/{year}/{partner}")
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
            for iso, m49 in SUPPLIERS:
                rec = fetch(classification, code, year, m49)
                time.sleep(SLEEP)
                if rec is None:
                    continue
                rows.append(
                    {
                        "year": year,
                        "classification": classification,
                        "hs_or_sitc_code": code,
                        "commodity": name,
                        "partner_iso": iso,
                        "partner_m49": m49,
                        "qty": rec.get("qty"),
                        "qty_unit_code": rec.get("qtyUnitCode"),
                        "net_weight_kg": rec.get("netWgt"),
                        "value_usd": rec.get("primaryValue"),
                    }
                )
        print(f"  {classification} {year}: {len(rows)} rows so far")
    return pd.DataFrame(rows)


def main() -> None:
    print("Pulling HS (1988-2010) — LNG by supplier ...")
    hs = harvest("HS", HS_TARGETS, range(HS_START, HS_END + 1))
    print(f"  -> {len(hs)} HS rows")

    print("Pulling SITC Rev. 1 (1970-1987) ...")
    sitc = harvest("S1", SITC_TARGETS, range(SITC_START, SITC_END + 1))
    print(f"  -> {len(sitc)} SITC rows")

    out = pd.concat([hs, sitc], ignore_index=True)
    out = out.sort_values(["classification", "commodity", "partner_iso", "year"]).reset_index(drop=True)
    out_path = RAW_DIR / "comtrade_japan_lng_by_supplier.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows)")


if __name__ == "__main__":
    sys.exit(main())
