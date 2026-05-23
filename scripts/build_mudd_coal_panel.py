"""Extract Black Coal and Iron Ore annual production by Australian state from
the Mudd (2023) dataset on Australian mine production 1799-2021.

Source: Mudd, G. (2023). "A Comprehensive dataset for Australian mine production
1799 to 2021." Scientific Data. doi:10.25439/rmt.22724081
Download: https://research-repository.rmit.edu.au/articles/dataset/22724081

The Mudd dataset has annual production by state/territory for major commodities.
**Granularity caveat**: this is STATE-level, not MINE-level. It's useful for
coarser DiD designs (QLD vs NSW around BMA 2001 event) but does NOT support a
project-level event study.

Emits:
  data/processed/mudd_coal_iron_state_panel.csv

Columns: year, state, commodity, production_tonnes
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw" / "mudd"
OUT = REPO_ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# Columns 39-45 are Black Coal (QLD, NSW, VIC, TAS, SA, WA, Australia total)
# Columns 77-84 are Iron Ore (QLD, NSW, VIC, TAS, SA, WA, NT, Australia total)
BLACK_COAL_COLS = {39: "QLD", 40: "NSW", 41: "VIC", 42: "TAS",
                   43: "SA", 44: "WA", 45: "Australia"}
IRON_ORE_COLS = {77: "QLD", 78: "NSW", 79: "VIC", 80: "TAS",
                 81: "SA", 82: "WA", 83: "NT", 84: "Australia"}
YEAR_COL = 0
DATA_START_ROW = 10  # Year 1799 is row 10


def extract_series(df: pd.DataFrame, col_map: dict, commodity: str) -> pd.DataFrame:
    rows = []
    for row_idx in range(DATA_START_ROW, len(df)):
        year_raw = df.iloc[row_idx, YEAR_COL]
        try:
            year = int(float(str(year_raw).replace(",", "")))
        except (ValueError, TypeError):
            continue
        if year < 1799 or year > 2030:
            continue
        for col_idx, state in col_map.items():
            val = df.iloc[row_idx, col_idx]
            if pd.isna(val):
                continue
            try:
                tonnes = float(str(val).replace(",", ""))
            except (ValueError, TypeError):
                continue
            rows.append({"year": year, "state": state,
                         "commodity": commodity, "production_tonnes": tonnes})
    return pd.DataFrame(rows)


def main() -> None:
    src = RAW / "Tab04-Annual-Data.csv"
    if not src.exists():
        print(f"ERROR: {src} not found. Download from RMIT figshare 22724081 first.")
        return
    ann = pd.read_csv(src, header=None)

    coal = extract_series(ann, BLACK_COAL_COLS, "black_coal")
    iron = extract_series(ann, IRON_ORE_COLS, "iron_ore")
    panel = pd.concat([coal, iron], ignore_index=True)
    panel = panel.sort_values(["commodity", "state", "year"]).reset_index(drop=True)

    out_path = OUT / "mudd_coal_iron_state_panel.csv"
    panel.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  shape={panel.shape}")

    print("\nQLD black coal 1995-2010 (covers BMA 2001 event):")
    qld = panel[(panel.state == "QLD") & (panel.commodity == "black_coal")
                & panel.year.between(1995, 2010)]
    print(qld.to_string(index=False))

    print("\nWA iron ore 1969-1980 (covers Mt Newman/Robe River entries):")
    wa_fe = panel[(panel.state == "WA") & (panel.commodity == "iron_ore")
                  & panel.year.between(1969, 1980)]
    print(wa_fe.to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
