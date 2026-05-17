"""Fetch annual Australia <-> Japan trade data from UN Comtrade public API.

The public preview endpoint requires no API key but is rate-limited; we
sleep between requests.  We pull each commodity TWO ways:

  - Australia as reporter, exports to Japan (flowCode=X)
  - Japan as reporter, imports from Australia (flowCode=M, the mirror)

This matters because Australia's customs data omits LNG to Japan
(confidentiality at the firm level when there are few exporters), so
the Australia-side query returns ~$0 for LNG even when actual trade
is ~$15B+/year.  The Japan-import mirror has full LNG values.

Classifications used:
  HS 1988+:  2701 (coal), 2704 (coke), 2711 (gas), 271111 (LNG only),
             2601 (iron ore), TOTAL (all commodities)
  SITC Rev. 1 1962-1987: 321 (coal+coke), 341 (gas), 281 (iron ore), TOTAL

Output: data/raw/comtrade_aus_to_jpn.csv with columns
  year, classification, hs_or_sitc_code, commodity, flow,
  reporter_iso, partner_iso, qty, net_weight_kg, value_usd
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
JPN = 392

# Two queries per (year, commodity): forward and mirror.
# (reporter, partner, flow) tuples.
DIRECTIONS = [
    ("AUS", AUS, JPN, "X"),  # Aus exports to Japan
    ("JPN", JPN, AUS, "M"),  # Japan imports from Aus  (mirror)
]

# (classification, code, friendly name)
# HS codes valid from 1988; SITC Rev. 1 covers 1962+
HS_TARGETS = [
    ("2701", "coal"),
    ("2704", "coke_semi_coke"),
    ("2711", "natural_gas_lng_gaseous"),  # parent for 271111 LNG + 271121 gas
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
SLEEP = 0.7  # seconds between requests to stay under rate limits


def fetch(cls: str, code: str, year: int, reporter: int, partner: int, flow: str) -> dict | None:
    url = BASE.format(cls=cls)
    params = {
        "reporterCode": reporter,
        "period": year,
        "cmdCode": code,
        "flowCode": flow,
        "partnerCode": partner,
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
        if "statusCode" in payload:  # rate-limit JSON body
            time.sleep(2 + attempt * 2)
            continue
        data = payload.get("data") or []
        return data[0] if data else None
    return None


def harvest(classification: str, targets: list, years: range) -> pd.DataFrame:
    rows = []
    for year in years:
        for code, name in targets:
            for label, reporter, partner, flow in DIRECTIONS:
                rec = fetch(classification, code, year, reporter, partner, flow)
                time.sleep(SLEEP)
                if rec is None:
                    continue
                rows.append(
                    {
                        "year": year,
                        "classification": classification,
                        "hs_or_sitc_code": code,
                        "commodity": name,
                        "reporter": label,
                        "flow": flow,
                        "qty": rec.get("qty"),
                        "qty_unit_code": rec.get("qtyUnitCode"),
                        "net_weight_kg": rec.get("netWgt"),
                        "value_usd": rec.get("primaryValue"),
                    }
                )
        print(f"  {classification} {year}: {len(rows)} rows so far")
    return pd.DataFrame(rows)


def main() -> None:
    print("Pulling HS (1988+) ...")
    hs = harvest("HS", HS_TARGETS, range(HS_START, HS_END + 1))
    print(f"  -> {len(hs)} HS rows")

    print("Pulling SITC Rev. 1 (1962-1987) ...")
    sitc = harvest("S1", SITC_TARGETS, range(SITC_START, SITC_END + 1))
    print(f"  -> {len(sitc)} SITC rows")

    out = pd.concat([hs, sitc], ignore_index=True)
    out = out.sort_values(["classification", "commodity", "year"]).reset_index(drop=True)
    out_path = RAW_DIR / "comtrade_aus_to_jpn.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(out)} rows)")


if __name__ == "__main__":
    sys.exit(main())
