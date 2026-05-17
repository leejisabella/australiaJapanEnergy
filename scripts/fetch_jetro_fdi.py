"""Parse JETRO Japan-outward-FDI files for Japan -> Australia values.

Two files downloaded from JETRO (Japan External Trade Organization):
  - country1_e_25cy.xlsx : annual FLOW (balance-of-payments, net), 1983+, USD millions
  - 24fdistock01_en.xls  : year-end STOCK, 1996-2024, USD millions

Both are sourced by JETRO from BoJ / Ministry of Finance BoP statistics.

Output: data/raw/japan_fdi_to_australia.csv
  year, fdi_flow_usd_million, fdi_stock_usd_million
"""
from __future__ import annotations

import sys
from pathlib import Path
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

FLOW_URL = "https://www.jetro.go.jp/ext_images/en/reports/statistics/data/country1_e_25cy.xlsx"
STOCK_URL = "https://www.jetro.go.jp/ext_images/en/reports/statistics/data/24fdistock01_en.xls"

FLOW_PATH = RAW_DIR / "jetro_country_flow_annual.xlsx"
STOCK_PATH = RAW_DIR / "jetro_country_stock.xls"


def download(url: str, path: Path) -> None:
    if path.exists():
        return
    print(f"Downloading {url}")
    r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    path.write_bytes(r.content)


def parse_flow() -> pd.DataFrame:
    df = pd.read_excel(FLOW_PATH, sheet_name="Historical(Outward)", header=None)
    # Years are in row 3, starting at column 2. Australia values are row 27, starting col 2.
    years = []
    for v in df.iloc[3, 2:].tolist():
        if isinstance(v, str):
            v = v.rstrip("r")
        try:
            years.append(int(float(v)))
        except (TypeError, ValueError):
            years.append(None)
    values = df.iloc[27, 2:].tolist()
    rows = []
    for yr, val in zip(years, values):
        if yr is None:
            continue
        try:
            val_float = float(val)
        except (TypeError, ValueError):
            val_float = None
        rows.append({"year": yr, "fdi_flow_usd_million": val_float})
    return pd.DataFrame(rows)


def parse_stock() -> pd.DataFrame:
    df = pd.read_excel(STOCK_PATH, sheet_name="Total Outward FDI", header=None)
    # Years live in row 3 as "end of 96" through "end of 24". Australia row = 26, starts col 3.
    years = []
    for v in df.iloc[3, 3:].tolist():
        if not isinstance(v, str):
            years.append(None)
            continue
        token = v.strip().lower().replace("end of", "").strip()
        try:
            yy = int(token)
        except ValueError:
            years.append(None)
            continue
        years.append(1900 + yy if yy >= 90 else 2000 + yy)
    values = df.iloc[26, 3:].tolist()
    rows = []
    for yr, val in zip(years, values):
        if yr is None:
            continue
        try:
            val_float = float(val)
        except (TypeError, ValueError):
            val_float = None
        rows.append({"year": yr, "fdi_stock_usd_million": val_float})
    return pd.DataFrame(rows)


def main() -> None:
    download(FLOW_URL, FLOW_PATH)
    download(STOCK_URL, STOCK_PATH)
    flow = parse_flow()
    stock = parse_stock()
    merged = flow.merge(stock, on="year", how="outer").sort_values("year").reset_index(drop=True)
    out = RAW_DIR / "japan_fdi_to_australia.csv"
    merged.to_csv(out, index=False)
    print(f"Wrote {out} ({len(merged)} rows)")
    print(merged.to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
