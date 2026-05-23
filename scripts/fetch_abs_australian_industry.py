"""Fetch ABS Australian Industry (8155.0) by ANZSIC subdivision.

Source: ABS 8155.0 via SDMX (dataflow ID AUSTRALIAN_INDUSTRY).

Pulls four measures for energy-relevant subdivisions and the all-mining division:
- INDUSTRY (Industry Value Added)
- PURCHASES (Purchases of goods & materials, incl. capitalised purchases — closest
            capex-like measure available at sub-division granularity)
- EXPTOTAL (Total expenses)
- INCSALGDSSERV (Sales and service income)

Subdivisions:
- 06 Coal Mining             — energy (fossil)
- 07 Oil and Gas Extraction  — energy (fossil)
- 08 Metal Ore Mining        — placebo for China-demand channel (iron ore, gold)
- B  Mining (division total) — comparison with all-mining capex from CAPEX (5625.0)

Output: data/raw/abs_australian_industry_by_sector.csv  (year, sector, measure, value_aud_million)
        data/raw/abs_australian_industry_wide.csv       (year, plus column per sector/measure)
        data/raw/abs_energy_sector_aggregate.csv        (year, energy_iva, energy_purchases, ...)

Coverage: 2007 to ~2024.
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

SECTORS = {
    "coal_mining": "06",
    "oil_gas_extraction": "07",
    "metal_ore_mining": "08",
    "non_metallic_mineral": "09",
    "exploration_support": "10",
    "mining_division_total": "B",
}

MEASURES = {
    "iva": "INDUSTRY",
    "purchases": "PURCHASES",
    "total_expenses": "EXPTOTAL",
    "sales_income": "INCSALGDSSERV",
    "ebitda": "EBITDA",
    "opbt": "OPBT",
}


def fetch_series(measure: str, industry: str) -> pd.DataFrame:
    url = f"https://data.api.abs.gov.au/rest/data/AUSTRALIAN_INDUSTRY/{measure}.{industry}.1.AUS.A"
    r = requests.get(url, headers={"Accept": "application/vnd.sdmx.data+csv"}, timeout=60)
    if r.status_code != 200:
        return pd.DataFrame()
    df = pd.read_csv(StringIO(r.text))
    if "TIME_PERIOD" not in df.columns:
        return pd.DataFrame()
    df = df[["TIME_PERIOD", "OBS_VALUE"]].copy()
    df["year"] = df.TIME_PERIOD.astype(int)
    return df[["year", "OBS_VALUE"]].rename(columns={"OBS_VALUE": "value_aud_million"})


def main() -> None:
    long_rows = []
    for sector_name, ind_code in SECTORS.items():
        for measure_name, measure_code in MEASURES.items():
            df = fetch_series(measure_code, ind_code)
            if df.empty:
                continue
            df["sector"] = sector_name
            df["measure"] = measure_name
            long_rows.append(df)
            print(f"  {sector_name:25s} {measure_name:14s} n={len(df)}, "
                  f"{df.year.min()}-{df.year.max()}")
    long = pd.concat(long_rows, ignore_index=True)
    long = long[["year", "sector", "measure", "value_aud_million"]]
    long.to_csv(RAW_DIR / "abs_australian_industry_by_sector.csv", index=False)

    # Wide pivot
    wide = long.pivot_table(index="year", columns=["sector", "measure"],
                              values="value_aud_million")
    wide.columns = [f"{s}_{m}" for s, m in wide.columns]
    wide = wide.reset_index().sort_values("year")
    wide.to_csv(RAW_DIR / "abs_australian_industry_wide.csv", index=False)

    # Energy-sector aggregate (coal + oil & gas)
    agg = pd.DataFrame({"year": wide["year"]})
    for m in MEASURES.keys():
        coal = wide.get(f"coal_mining_{m}", 0)
        gas = wide.get(f"oil_gas_extraction_{m}", 0)
        metal = wide.get(f"metal_ore_mining_{m}", 0)
        total = wide.get(f"mining_division_total_{m}", 0)
        agg[f"energy_{m}_aud_million"] = coal.fillna(0) + gas.fillna(0)
        agg[f"metal_ore_{m}_aud_million"] = metal.fillna(0)
        agg[f"mining_total_{m}_aud_million"] = total.fillna(0)
        agg[f"energy_share_of_mining_{m}"] = (
            (coal.fillna(0) + gas.fillna(0)) / total.replace(0, pd.NA)
        )
    agg.to_csv(RAW_DIR / "abs_energy_sector_aggregate.csv", index=False)

    print("\nEnergy-sector aggregate (coal + oil & gas, AUD millions):")
    cols = ["year", "energy_iva_aud_million", "energy_purchases_aud_million",
            "energy_sales_income_aud_million", "energy_share_of_mining_purchases"]
    print(agg[cols].tail(10).round(2).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
