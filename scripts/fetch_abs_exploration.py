"""Fetch ABS exploration expenditure — energy-sector and placebo series.

Source: ABS catalogue 8412.0 via the SDMX API.

Two dataflows:
- PET_EXP — Petroleum Exploration Expenditure (oil & gas), quarterly from 1974-Q3.
- MIN_EXP — Mineral Exploration Expenditure with breakdown by mineral sought.
            Coal (07) and iron ore (03) are extracted here; coal is part of the
            energy-sector series, iron ore serves as a China-demand placebo.

Output:
- data/raw/abs_petroleum_exploration.csv  (year, quarter, expenditure_aud_million)
- data/raw/abs_mineral_exploration_by_type.csv  (year, quarter, mineral, expenditure_aud_million)
- data/raw/abs_exploration_annual.csv  (year, petroleum, coal, iron_ore, all_minerals, total_energy)
"""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import sys
import requests
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# PET_EXP key: MEASURE.ONSHORE_OFFSHORE.EXPLORE_TYPE.LEASE_TYPE.TSEST.REGION.FREQ
# 1 = Expenditure; TOT = onshore+offshore total; TOT explore = drilling+other; 3 = total lease type;
# 10 = original (not seasonally adjusted); AUS = Australia; Q = quarterly.
PET_URL = "https://data.api.abs.gov.au/rest/data/PET_EXP/1.TOT.TOT.3.10.AUS.Q"

# MIN_EXP key: MEASURE.DEPOSIT_TYPE.MINERAL_TYPE.TSEST.REGION.FREQ
# 1 = Expenditure; 6 = Total deposits; 10 = Original; AUS; Q
MIN_URL_TEMPLATE = "https://data.api.abs.gov.au/rest/data/MIN_EXP/1.6.{mineral}.10.AUS.Q"

MINERALS = {
    "all_minerals": "TOT",
    "coal": "07",
    "iron_ore": "03",
    "gold": "02",
    "uranium": "06",
}


def fetch(url: str) -> pd.DataFrame:
    r = requests.get(
        url,
        headers={"Accept": "application/vnd.sdmx.data+csv"},
        params={"startPeriod": "1974-Q1"},
        timeout=120,
    )
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))


def to_quarterly(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df = df[["TIME_PERIOD", "OBS_VALUE"]].copy()
    df["year"] = df.TIME_PERIOD.str.slice(0, 4).astype(int)
    df["quarter"] = df.TIME_PERIOD.str.slice(-1).astype(int)
    df = df.rename(columns={"OBS_VALUE": name}).drop(columns="TIME_PERIOD")
    return df[["year", "quarter", name]].sort_values(["year", "quarter"]).reset_index(drop=True)


def main() -> None:
    # Petroleum (oil & gas exploration)
    print(f"Fetching PET_EXP from {PET_URL}")
    pet = fetch(PET_URL)
    print(f"  raw rows: {len(pet)}")
    pet_q = to_quarterly(pet, "petroleum_exp_aud_million")
    pet_q.to_csv(RAW_DIR / "abs_petroleum_exploration.csv", index=False)
    print(f"  wrote {RAW_DIR/'abs_petroleum_exploration.csv'}  "
          f"({len(pet_q)} rows, {pet_q.year.min()}-{pet_q.year.max()})")

    # Mineral exploration by type
    pieces = []
    for label, code in MINERALS.items():
        url = MIN_URL_TEMPLATE.format(mineral=code)
        print(f"Fetching MIN_EXP {label} ({code}) from {url}")
        df = fetch(url)
        df = df[["TIME_PERIOD", "OBS_VALUE"]].copy()
        df["mineral"] = label
        df["year"] = df.TIME_PERIOD.str.slice(0, 4).astype(int)
        df["quarter"] = df.TIME_PERIOD.str.slice(-1).astype(int)
        df = df.rename(columns={"OBS_VALUE": "expenditure_aud_million"})
        pieces.append(df[["year", "quarter", "mineral", "expenditure_aud_million"]])
        print(f"  {label}: {len(df)} rows")
    min_long = pd.concat(pieces, ignore_index=True).sort_values(
        ["year", "quarter", "mineral"]).reset_index(drop=True)
    min_long.to_csv(RAW_DIR / "abs_mineral_exploration_by_type.csv", index=False)

    # Annual combined panel (sum quarters in same year)
    # Combine petroleum + mineral; build energy series = coal + petroleum
    pet_ann = (pet_q.groupby("year")["petroleum_exp_aud_million"].sum()
               .reset_index())
    min_wide = (min_long.pivot_table(index=["year", "quarter"], columns="mineral",
                                       values="expenditure_aud_million")
                .reset_index())
    min_ann = (min_wide.groupby("year").sum(numeric_only=True).reset_index()
               .drop(columns="quarter"))
    annual = pet_ann.merge(min_ann, on="year", how="outer").sort_values("year")
    # Keep years with 4 quarters of petroleum exploration (the always-present series).
    # Per-mineral coverage starts later (1988 for coal/iron ore), so don't drop on that.
    pet_full = pet_q.groupby("year").size()
    full_pet = set(pet_full[pet_full == 4].index)
    annual = annual[annual.year.isin(full_pet)].reset_index(drop=True)
    annual["energy_exploration_aud_million"] = (
        annual["petroleum_exp_aud_million"].fillna(0) + annual["coal"].fillna(0)
    )
    annual.to_csv(RAW_DIR / "abs_exploration_annual.csv", index=False)
    print(f"\nWrote annual panel: {len(annual)} years, "
          f"{annual.year.min()}-{annual.year.max()}")
    print(annual.tail(8).round(0).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
