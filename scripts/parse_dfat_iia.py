"""Parse DFAT International Investment Australia (IIA) workbooks for Japan series.

Source: ABS 5352.0 supplementary tables, downloaded as
  data/raw/dfat_data/5352001_2025.xlsx  Table 1 - transactions/flows
  data/raw/dfat_data/5352002_2025.xlsx  Table 2 - levels/stocks
  data/raw/dfat_data/5352003_2025.xlsx  Table 3 - income debits

Each workbook is country × investment-type × year (2001-2025). We extract just
the Japan block from each and produce a single long-format CSV.

This gives us:
- Total Japan->Australia FDI (transactions), 2001-2025, official Australia side
- Total Japan->Australia FDI position (stock), 2001-2025
- Investment income paid to Japanese investors, 2001-2025
- Plus the breakdown into direct vs portfolio vs other, equity vs debt

Note: this is by *investment type* (direct/portfolio/equity/debt), NOT by
industry. DFAT does not publish Japan x ANZSIC industry at this granularity.

Output:
- data/raw/dfat_data/japan_fdi_panel.csv  (year, table, investment_type, value_aud_million)
- data/raw/dfat_data/japan_fdi_wide.csv   (year, plus one column per series)
"""
from __future__ import annotations

from pathlib import Path
import sys
import re
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "dfat_data"

FILES = [
    ("5352001_2025.xlsx", "Table1", "transactions"),
    ("5352002_2025.xlsx", "Table2", "levels"),
    ("5352003_2025.xlsx", "Table3", "income"),
]


PLACEBO_COUNTRIES = [
    "Japan",
    "United States of America",
    "United Kingdom",
    "China (excludes SARs and Taiwan)",
    "Hong Kong (SAR of China)",
    "Germany",
    "Singapore",
    "Korea, Republic of (South)",
    "Canada",
    "Netherlands",
    "ASEAN",
]


def parse_country_block(df: pd.DataFrame, country: str, table_kind: str,
                          year_cols: dict[int, int]) -> pd.DataFrame:
    rows_at = df.index[df[0].astype(str).str.strip().eq(country)].tolist()
    if not rows_at:
        return pd.DataFrame()
    start = rows_at[0]
    end = len(df)
    for j in range(start + 1, len(df)):
        cell = df.iloc[j, 0]
        if isinstance(cell, str) and cell.strip() and cell.strip() != country:
            end = j
            break
    rows = []
    for r in range(start, end):
        invtype = df.iloc[r, 1]
        if pd.isna(invtype) or not str(invtype).strip():
            continue
        invtype = str(invtype).strip()
        for c, y in year_cols.items():
            v = df.iloc[r, c]
            if isinstance(v, str):
                if v.strip() in ("-", "np", "..", "n.p.", "nan"):
                    continue
                try:
                    v = float(v.replace(",", ""))
                except ValueError:
                    continue
            if pd.isna(v):
                continue
            rows.append({
                "country": country,
                "year": y,
                "table": table_kind,
                "investment_type": invtype,
                "value_aud_million": float(v),
            })
    return pd.DataFrame(rows)


def parse_japan_block(xlsx_path: Path, sheet: str, table_kind: str) -> pd.DataFrame:
    """Parse Japan block (kept for backward compatibility) — wraps multi-country parser."""
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
    year_row = df.iloc[6].tolist()
    year_cols = {}
    for c, v in enumerate(year_row):
        try:
            y = int(v)
            if 1990 <= y <= 2030:
                year_cols[c] = y
        except (TypeError, ValueError):
            continue
    block = parse_country_block(df, "Japan", table_kind, year_cols)
    if not block.empty:
        return block.drop(columns="country")
    return pd.DataFrame()


def parse_multi_country(xlsx_path: Path, sheet: str, table_kind: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
    year_row = df.iloc[6].tolist()
    year_cols = {}
    for c, v in enumerate(year_row):
        try:
            y = int(v)
            if 1990 <= y <= 2030:
                year_cols[c] = y
        except (TypeError, ValueError):
            continue
    pieces = []
    for c in PLACEBO_COUNTRIES:
        block = parse_country_block(df, c, table_kind, year_cols)
        if not block.empty:
            pieces.append(block)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def short_name(invtype: str) -> str:
    s = invtype.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def main() -> None:
    # Japan-only long panel (kept for backward compatibility with downstream code)
    pieces = []
    for fname, sheet, kind in FILES:
        path = RAW / fname
        print(f"Parsing {path.name} (Japan)…")
        block = parse_japan_block(path, sheet, kind)
        print(f"  Japan rows: {len(block)}, "
              f"years {block.year.min()}-{block.year.max()}, "
              f"types: {block.investment_type.nunique()}")
        pieces.append(block)

    long = pd.concat(pieces, ignore_index=True)
    long_path = RAW / "japan_fdi_panel.csv"
    long.to_csv(long_path, index=False)
    print(f"Wrote {long_path}  ({len(long)} rows)")

    # Multi-country long panel for placebo tests
    multi_pieces = []
    for fname, sheet, kind in FILES:
        path = RAW / fname
        print(f"Parsing {path.name} (all placebo countries)…")
        block = parse_multi_country(path, sheet, kind)
        if not block.empty:
            print(f"  rows: {len(block)}, countries: {block.country.nunique()}")
            multi_pieces.append(block)
    multi_long = pd.concat(multi_pieces, ignore_index=True)
    multi_path = RAW / "placebo_fdi_panel.csv"
    multi_long.to_csv(multi_path, index=False)
    print(f"Wrote {multi_path}  ({len(multi_long)} rows)")

    # Wide pivot for direct-stock and direct-flow comparison across countries
    placebo_wide_rows = []
    for c in multi_long.country.unique():
        sub = multi_long[multi_long.country == c]
        # Direct investment in Australia, levels (stock) — preferred for placebo
        stock = sub[(sub.table == "levels") &
                      (sub.investment_type == "Direct investment in Australia")]
        flow = sub[(sub.table == "transactions") &
                      (sub.investment_type == "Direct investment in Australia")]
        country_slug = (c.lower()
                          .replace(" ", "_")
                          .replace(",", "")
                          .replace("(", "")
                          .replace(")", "")
                          .replace("'", ""))
        for y, v in zip(stock.year, stock.value_aud_million):
            placebo_wide_rows.append(
                {"year": y, "country": country_slug, "kind": "stock", "value": v})
        for y, v in zip(flow.year, flow.value_aud_million):
            placebo_wide_rows.append(
                {"year": y, "country": country_slug, "kind": "flow", "value": v})
    pwide = pd.DataFrame(placebo_wide_rows)
    pwide["col"] = pwide.apply(
        lambda r: f"{r['country']}_direct_{r['kind']}_aud_million", axis=1)
    pwide = pwide.pivot_table(index="year", columns="col", values="value").reset_index()
    placebo_path = RAW / "placebo_fdi_direct_wide.csv"
    pwide.to_csv(placebo_path, index=False)
    print(f"Wrote {placebo_path}  shape={pwide.shape}")

    # Wide format for the most-used series only
    wide = long.copy()
    wide["col"] = wide.apply(
        lambda r: f"jpn_{r.table}_{short_name(r.investment_type)}", axis=1)
    wide = wide.pivot_table(index="year", columns="col",
                              values="value_aud_million", aggfunc="first").reset_index()
    wide_path = RAW / "japan_fdi_wide.csv"
    wide.to_csv(wide_path, index=False)
    print(f"Wrote {wide_path}  shape={wide.shape}")

    # Sanity check: print headline series
    key_cols = [c for c in wide.columns if
                  c.startswith("jpn_transactions_foreign_investment_in_australia") or
                  c.startswith("jpn_transactions_direct_investment_in_australia") or
                  c.startswith("jpn_levels_direct_investment_in_australia") or
                  c.startswith("jpn_levels_foreign_investment_in_australia") or
                  c == "year"]
    key_cols = [c for c in key_cols if "equity" not in c and "other_capital" not in c
                and "securities" not in c]
    print("\nKey Japan FDI series (AUD millions):")
    print(wide[key_cols].tail(12).round(0).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
