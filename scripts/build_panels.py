"""Merge the raw datasets into two clean annual panels.

  data/processed/fossil_era_panel.csv      (1962-2024, fossil-fuel focus)
  data/processed/renewables_era_panel.csv  (2005-2024, renewable focus)

Both panels share several columns (Japan GDP, FX rate, etc.) but differ
in the dependent variable.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"
MAN = REPO_ROOT / "data" / "manual"
OUT = REPO_ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


# ---------- helpers ---------------------------------------------------------

def load_wb_macro() -> pd.DataFrame:
    df = pd.read_csv(RAW / "world_bank_macro.csv")
    wide = df.pivot_table(
        index="year",
        columns=["country", "indicator_name"],
        values="value",
        aggfunc="first",
    )
    wide.columns = [f"{c}_{i}".lower() for c, i in wide.columns]
    return wide.reset_index()


def load_prices() -> pd.DataFrame:
    df = pd.read_csv(RAW / "pink_sheet_prices.csv")
    return df.pivot_table(
        index="year", columns="commodity", values="price_nominal_usd", aggfunc="first"
    ).reset_index()


def load_fx() -> pd.DataFrame:
    return pd.read_csv(RAW / "exchange_rates.csv")


def load_trade() -> pd.DataFrame:
    """Build a single annual Australia->Japan trade panel from Comtrade.

    Comtrade has BOTH an Australia-exports view and a Japan-imports mirror.
    Australia's customs office suppresses LNG exports for confidentiality
    (too few exporters), so the Australia-side value is ~$0 even when
    actual trade is ~$15B+/year. We resolve this per commodity:

      - coal, iron_ore, all_commodities, coke: prefer Australia-exports
        (matches DFAT headline numbers), fall back to Japan-imports.
      - lng, gas: use Japan-imports (the only reliable side).
    """
    df = pd.read_csv(RAW / "comtrade_aus_to_jpn.csv")
    code_map = {
        ("S1", "coal_coke_briquettes"): "coal",
        ("HS", "coal"): "coal",
        ("S1", "iron_ore_concentrates"): "iron_ore",
        ("HS", "iron_ore"): "iron_ore",
        ("S1", "gas_natural_manufactured"): "lng",
        ("HS", "natural_gas_lng_gaseous"): "lng",
        ("HS", "lng_liquefied"): "lng_strict",
        ("S1", "all_commodities"): "all_commodities",
        ("HS", "all_commodities"): "all_commodities",
        ("HS", "coke_semi_coke"): "coke",
    }
    df["series"] = df.set_index(["classification", "commodity"]).index.map(code_map)
    df = df.dropna(subset=["series"]).copy()

    # Pick the larger of (Australia-reported export, Japan-reported import).
    # Confidentiality only ever suppresses values toward zero, never inflates,
    # so max() is the right consolidation rule.
    def choose(rows: pd.DataFrame) -> float:
        vals = rows["value_usd"].dropna()
        return float(vals.max()) if len(vals) else float("nan")

    rows = []
    for (year, series), grp in df.groupby(["year", "series"]):
        val = choose(grp)
        rows.append({"year": year, "series": series, "value_usd": val})
    flat = pd.DataFrame(rows)
    out = flat.pivot_table(index="year", columns="series", values="value_usd", aggfunc="first").reset_index()
    out = out.rename(columns={c: f"export_{c}_usd_to_jpn" for c in out.columns if c != "year"})
    return out


def load_fdi() -> pd.DataFrame:
    return pd.read_csv(RAW / "japan_fdi_to_australia.csv")


def load_renewables() -> pd.DataFrame:
    return pd.read_csv(RAW / "australia_renewable_energy.csv")


def build_lng_contracts_series(years: range) -> pd.DataFrame:
    """Convert hand-coded contract rows into a cumulative annual Mtpa series.

    A contract's Japan-contracted Mtpa is counted from its first_lng_year
    forward through the end of its assumed term length. If a term length
    is given as a range (e.g. "20-25"), the midpoint is used.
    """
    df = pd.read_csv(MAN / "lng_contracts_aus_jpn.csv")

    def parse_term(v) -> int:
        s = str(v)
        if "-" in s:
            lo, hi = s.split("-")
            return int((int(lo) + int(hi)) / 2)
        try:
            return int(float(s))
        except (TypeError, ValueError):
            return 20

    df["term_years_int"] = df["contract_term_years"].apply(parse_term)
    df["end_year"] = df["first_lng_year"] + df["term_years_int"]
    yrs = list(years)
    cum_mtpa = []
    for y in yrs:
        active = df[(df.first_lng_year <= y) & (df.end_year > y)]
        cum_mtpa.append(active["japan_contracted_mtpa"].sum())
    return pd.DataFrame({"year": yrs, "japan_lng_contracted_mtpa": cum_mtpa})


# ---------- assembly --------------------------------------------------------

def build_fossil_panel() -> pd.DataFrame:
    macro = load_wb_macro()
    prices = load_prices()
    fx = load_fx()
    trade = load_trade()
    fdi = load_fdi()
    contracts = build_lng_contracts_series(range(1962, 2025))

    df = macro.merge(prices, on="year", how="outer") \
              .merge(fx, on="year", how="outer") \
              .merge(trade, on="year", how="outer") \
              .merge(fdi, on="year", how="outer") \
              .merge(contracts, on="year", how="outer")
    df = df[(df.year >= 1962) & (df.year <= 2024)].sort_values("year").reset_index(drop=True)

    df["export_energy_usd_to_jpn"] = (
        df["export_coal_usd_to_jpn"].fillna(0) + df["export_lng_usd_to_jpn"].fillna(0)
    )
    # Only keep years where at least one trade column is present
    df.loc[df[["export_coal_usd_to_jpn", "export_lng_usd_to_jpn"]].isna().all(axis=1), "export_energy_usd_to_jpn"] = np.nan
    return df


def build_renewables_panel() -> pd.DataFrame:
    macro = load_wb_macro()
    fx = load_fx()
    fdi = load_fdi()
    ren = load_renewables()

    df = ren.merge(macro, on="year", how="left") \
            .merge(fx, on="year", how="left") \
            .merge(fdi, on="year", how="left")
    df = df[(df.year >= 2005) & (df.year <= 2024)].sort_values("year").reset_index(drop=True)
    return df


def main() -> None:
    fossil = build_fossil_panel()
    fossil_path = OUT / "fossil_era_panel.csv"
    fossil.to_csv(fossil_path, index=False)
    print(f"Wrote {fossil_path}  shape={fossil.shape}")
    print(fossil[["year", "export_energy_usd_to_jpn", "fdi_flow_usd_million",
                  "japan_lng_contracted_mtpa", "jpn_gdp_current_usd"]].tail(10).to_string(index=False))

    renew = build_renewables_panel()
    renew_path = OUT / "renewables_era_panel.csv"
    renew.to_csv(renew_path, index=False)
    print(f"\nWrote {renew_path}  shape={renew.shape}")
    print(renew[["year", "renewables_electricity", "renewables_share_elec",
                 "fdi_flow_usd_million", "fdi_stock_usd_million"]].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
