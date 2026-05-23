"""Parse BoJ outward FDI Excel files into a Japan->Australia by industry panel.

Source: BoJ Balance of Payments data, https://www.boj.or.jp/en/statistics/br/bop_06/bpdata/
Files: dif{YY}cy.xlsx (calendar-year flows) and dip{YYYY}.xlsx (year-end position/stock).
Sheet 3 in each file is "Direct Investment Abroad (by Country and Industry)".

Unit: 100 million yen (億円) — converted to millions of USD using annual avg JPY/USD.

Industries kept:
- Mining (鉱業)            — resource extraction; closest sector match
- Petroleum (石油)         — refining/chemicals; often suppressed for Australia
- Manufacturing total
- Non-manufacturing total
- Total                    — all-sector

Output:
- data/raw/boj/japan_fdi_to_australia_by_industry.csv
    (year, series_type, industry, value_oku_yen, value_usd_million)
"""
from __future__ import annotations

from pathlib import Path
import sys
import glob
import re
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "boj"
OUT_PATH = RAW_DIR / "japan_fdi_to_australia_by_industry.csv"

# English-name -> Japanese name mapping for the industry rows in Sheet 3 col 2
INDUSTRY_LABELS = {
    "manufacturing_total": "製造業",          # 製造業 （計）
    "food":                "食料品",
    "textile":             "繊維",
    "lumber_pulp":         "木材",
    "chemicals_pharma":    "化学",
    "petroleum":           "石油",            # refining, not extraction
    "rubber_leather":      "ゴム",
    "glass_ceramics":      "ガラス",
    "iron_metals":         "鉄",
    "general_machinery":   "一般機械",
    "electric_machinery":  "電気機械",
    "transport_equipment": "輸送機械",
    "precision_machinery": "精密機械",
    "nonmanufacturing_total": "非製造業",
    "farming_forestry":    "農",
    "fishery":             "漁",
    "mining":              "鉱業",            # resource extraction (coal + oil & gas + metals)
    "construction":        "建設",
    "transportation":      "運輸",
    "communications":      "通信",
    "wholesale_retail":    "卸売",
    "finance_insurance":   "金融",
    "real_estate":         "不動産",
    "services":            "サ",              # サ-ビス業
    "total":               "合計",
}

# Annual avg JPY per USD (used to convert 100M yen -> million USD).
# Source: BoJ/OANDA composite (rounded).
JPY_PER_USD = {
    2014: 105.94, 2015: 121.04, 2016: 108.79, 2017: 112.10,
    2018: 110.42, 2019: 109.01, 2020: 106.78, 2021: 109.84,
    2022: 131.50, 2023: 140.49, 2024: 151.46,
}


def find_australia_column(df: pd.DataFrame) -> int:
    """Find the column whose row-10 header is 'Australia'."""
    # English headers can be on row 10 or sometimes row 11/12 depending on year
    for header_row in (10, 11, 12):
        if header_row >= len(df):
            continue
        for c in df.columns:
            v = df.iloc[header_row, c]
            if isinstance(v, str) and v.strip() == "Australia":
                return c
    raise ValueError("Australia column not found")


def parse_file(path: Path, series_type: str) -> list[dict]:
    # Find sheet whose row 10 contains "Australia"
    xl = pd.ExcelFile(path)
    df = None
    for sheet in xl.sheet_names:
        try:
            cand = pd.read_excel(xl, sheet_name=sheet, header=None)
        except Exception:
            continue
        if cand.shape[1] < 30 or cand.shape[0] < 30:
            continue  # too small to hold country breakdown
        for header_row in (8, 9, 10, 11, 12):
            if header_row >= len(cand):
                continue
            row_vals = cand.iloc[header_row].astype(str).tolist()
            if any("Australia" in v for v in row_vals):
                df = cand
                break
        if df is not None:
            break
    if df is None:
        return []
    try:
        au_col = find_australia_column(df)
    except ValueError:
        return []

    # Year from filename
    m = re.search(r"(\d{2,4})", path.stem)
    if not m:
        return []
    yy = int(m.group(1))
    year = 2000 + yy if yy < 100 else yy

    rows = []
    # Walk through rows 13..78 looking for Japanese industry labels in col 2 (or 1)
    for i in range(13, len(df)):
        label_col2 = df.iloc[i, 2] if pd.notna(df.iloc[i, 2]) else ""
        label_col1 = df.iloc[i, 1] if pd.notna(df.iloc[i, 1]) else ""
        label = str(label_col2) if label_col2 else str(label_col1)
        if not label.strip():
            continue
        # Match against known industry tokens, checking longer (more specific)
        # tokens first so "非製造業" matches "nonmanufacturing_total", not the
        # substring "製造業" for "manufacturing_total".
        for ind_en, ind_jp_token in sorted(
            INDUSTRY_LABELS.items(), key=lambda kv: -len(kv[1])
        ):
            if ind_jp_token in label:
                val = df.iloc[i, au_col]
                # Filter to numeric only ("X" = suppressed, "." = no data)
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    v = None
                rows.append({
                    "year": year,
                    "series_type": series_type,
                    "industry": ind_en,
                    "value_oku_yen": v,
                })
                break
    return rows


def main() -> None:
    flows = sorted(glob.glob(str(RAW_DIR / "dif*cy.xlsx")))
    stocks = sorted(glob.glob(str(RAW_DIR / "dip*.xlsx")))
    print(f"Found {len(flows)} flow files, {len(stocks)} stock files")

    rows = []
    for p in flows:
        rows.extend(parse_file(Path(p), "flow"))
    for p in stocks:
        rows.extend(parse_file(Path(p), "stock"))

    out = pd.DataFrame(rows)
    if out.empty:
        print("WARNING: no rows parsed")
        return

    # USD conversion: 100M yen / (JPY per USD) = M USD
    out["value_usd_million"] = out.apply(
        lambda r: (r["value_oku_yen"] * 100 / JPY_PER_USD[r["year"]])
        if pd.notna(r["value_oku_yen"]) and r["year"] in JPY_PER_USD else None,
        axis=1,
    )
    out = out.sort_values(["series_type", "year", "industry"]).reset_index(drop=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH}  ({len(out)} rows, "
          f"{out.year.min()}-{out.year.max()})")

    # Quick summary
    key_rows = out[out.industry.isin(["mining", "total", "manufacturing_total"]) &
                    (out.series_type == "flow")]
    pivot = key_rows.pivot_table(index="year", columns="industry",
                                   values="value_usd_million")
    print("\nJapan FDI flows to Australia (USD millions), by industry:")
    print(pivot.round(0).to_string())


if __name__ == "__main__":
    sys.exit(main())
