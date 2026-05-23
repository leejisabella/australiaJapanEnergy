"""Assemble the country-year panel for Analysis 3 (staggered DiD across
LNG supplier cohorts).

Reads:
  data/raw/comtrade_japan_lng_by_supplier.csv  (from fetch_japan_lng_by_country.py)
  data/manual/lng_supplier_spa_cohorts.csv

Emits:
  data/processed/japan_lng_supplier_panel.csv

Long format, one row per (country, year), 1970-2010. Columns:
  country, iso3, year, value_usd, net_weight_kg, value_share_of_japan_total,
  weight_share_of_japan_total, treatment_cohort, first_cargo_year,
  treated_t, event_time, post

For LNG-strict (HS 271111) data only exists 1996+; for 1988-1995 we use HS 2711
(natural gas total — dominated by LNG for Japan); for 1970-1987 we use SITC 341.
The choice rule per (year, country): use the most LNG-specific code available
that returns nonzero data, then propagate via World-total denominator.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"
MAN = REPO_ROOT / "data" / "manual"
OUT = REPO_ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


# Priority ordering for collapsing multiple HS/SITC codes to one LNG-value-per-year.
# Higher = preferred. We pick the highest-priority nonzero observation per row.
CODE_PRIORITY = {
    "lng_liquefied": 3,           # HS 271111 (1996+) — purest LNG
    "natural_gas_lng_gaseous": 2, # HS 2711 (1988+) — includes pipeline gas (Japan has none, so ≈ LNG)
    "gas_natural_manufactured": 1, # SITC 341 (pre-1988) — gas, manufactured or natural
}


def load_supplier_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW / "comtrade_japan_lng_by_supplier.csv")
    df["priority"] = df["commodity"].map(CODE_PRIORITY).fillna(0)
    return df


def collapse_to_best_code(df: pd.DataFrame) -> pd.DataFrame:
    """For each (partner_iso, year), choose the highest-priority commodity row
    with nonzero value_usd. Falls back to lower-priority codes if higher is
    missing or zero."""
    df = df.sort_values(["partner_iso", "year", "priority"], ascending=[True, True, False])
    rows = []
    for (iso, m49, year), grp in df.groupby(["partner_iso", "partner_m49", "year"]):
        nonzero = grp[grp["value_usd"].fillna(0) > 0]
        chosen = nonzero.iloc[0] if len(nonzero) else grp.iloc[0]
        rows.append({
            "partner_iso": iso, "partner_m49": m49, "year": year,
            "value_usd": chosen["value_usd"],
            "net_weight_kg": chosen["net_weight_kg"],
            "commodity": chosen["commodity"],
            "classification": chosen["classification"],
            "hs_or_sitc_code": chosen["hs_or_sitc_code"],
        })
    return pd.DataFrame(rows)


def compute_shares(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot out WLD as the Japan-total denominator, compute supplier shares."""
    wld = df[df["partner_iso"] == "WLD"][["year", "value_usd", "net_weight_kg"]].rename(
        columns={"value_usd": "japan_total_value_usd",
                 "net_weight_kg": "japan_total_net_weight_kg"})
    suppliers = df[df["partner_iso"] != "WLD"].copy()
    out = suppliers.merge(wld, on="year", how="left")
    out["value_share_of_japan_total"] = out["value_usd"] / out["japan_total_value_usd"]
    out["weight_share_of_japan_total"] = out["net_weight_kg"] / out["japan_total_net_weight_kg"]
    return out


def attach_treatment(df: pd.DataFrame) -> pd.DataFrame:
    cohorts = pd.read_csv(MAN / "lng_supplier_spa_cohorts.csv")
    cohorts = cohorts.rename(columns={"iso3": "partner_iso"})
    keep = ["partner_iso", "country", "first_spa_signed_year", "first_cargo_year", "treatment_cohort"]
    out = df.merge(cohorts[keep], on="partner_iso", how="left")
    # Countries not in the cohort file (e.g., USA, RUS) get NaN — useful as
    # never-treated / late-treated controls.
    out["treated_t"] = ((out["first_cargo_year"].notna())
                        & (out["year"] >= out["first_cargo_year"])).astype(int)
    out["event_time"] = out["year"] - out["first_cargo_year"]
    out["post"] = (out["event_time"] >= 0).astype(int)
    out.loc[out["first_cargo_year"].isna(), ["event_time", "post"]] = np.nan
    return out


def main() -> None:
    raw = load_supplier_raw()
    print(f"Loaded {len(raw)} raw rows from Comtrade supplier fetch.")
    best = collapse_to_best_code(raw)
    print(f"Collapsed to {len(best)} (partner, year) rows.")
    shared = compute_shares(best)
    final = attach_treatment(shared)

    final = final[(final.year >= 1970) & (final.year <= 2010)].copy()
    final = final.sort_values(["partner_iso", "year"]).reset_index(drop=True)

    out_path = OUT / "japan_lng_supplier_panel.csv"
    final.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  shape={final.shape}")
    print("\nSample (Australia, 1985-1995):")
    print(final[(final.partner_iso == "AUS") & (final.year.between(1985, 1995))]
          [["year", "value_usd", "value_share_of_japan_total", "treated_t", "event_time"]]
          .to_string(index=False))
    print("\nSample (Brunei, 1972-1985 — first-mover):")
    print(final[(final.partner_iso == "BRN") & (final.year.between(1972, 1985))]
          [["year", "value_usd", "value_share_of_japan_total", "treated_t", "event_time"]]
          .to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
