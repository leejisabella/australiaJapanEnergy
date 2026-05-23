"""Assemble the project-year panel for Analysis 2 (project-level cross-section
+ event study DiD around BMA 2001 Mitsubishi equity transition).

Scope: coal + iron-ore projects only. LNG is analyzed at the country level in
Analysis 3 via data/processed/japan_lng_supplier_panel.csv.

Reads:
  data/manual/coal_iron_ore_projects_aus_jpn.csv  (project metadata)
  data/manual/japanese_equity_transitions.csv      (step-function equity changes)
  data/manual/coking_coal_spa_cohorts.csv          (JSM SPA participation)
  data/manual/project_production_annual.csv        (hand-coded annual mtpa, japan-share)
  data/processed/fossil_era_panel.csv              (prices, FX for merge)

Emits:
  data/processed/project_year_panel.csv

Long format, one row per (project, year). Years 1969-2010 by default; rows
exist for years >= project.first_export_year.

HAND-CODING REQUIRED to complete the panel:
  1. project_production_annual.csv — annual Mtpa for each (project, year) from
     ABARES *Resources & Energy Quarterly* (1995+), *Joint Coal Board Annual
     Reports* (NLA Trove, 1971-90), *Australian Mineral Industry Annual Review*
     (BMR, 1969-90), and company annual reports (BHP, Rio Tinto, BMA joint
     annual statements).

  2. For the BMA event study you also need rows for control mines: German
     Creek, Oaky Creek, Curragh, Moranbah North. These do not appear in
     coal_iron_ore_projects_aus_jpn.csv because they have no Japanese equity;
     add them to coal_iron_ore_projects_aus_jpn.csv with japanese_equity_pct=0
     and to project_production_annual.csv with annual Mtpa.

  3. Japan-share-of-output is only observable from ~2005+ for most projects
     (Wood Mackenzie is paywalled; METI port data doesn't link to mine). Leave
     blank where unknown — the cross-section regression in Analysis 2 will use
     only the observed sub-sample.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
MAN = REPO_ROOT / "data" / "manual"
PROC = REPO_ROOT / "data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)

PANEL_YEARS = range(1969, 2011)  # inclusive endpoints 1969-2010


def load_projects() -> pd.DataFrame:
    """Coal + iron-ore project metadata. LNG is handled in Analysis 3."""
    coal = pd.read_csv(MAN / "coal_iron_ore_projects_aus_jpn.csv")
    coal = coal.rename(columns={
        "first_export_year": "first_year",
        "japanese_equity_pct_initial": "equity_initial",
        "japanese_equity_pct_current": "equity_current",
        "approx_initial_mtpa": "nameplate_mtpa",
    })
    cols = ["project", "commodity", "first_year", "equity_initial",
            "equity_current", "nameplate_mtpa"]
    return coal[cols]


def load_transitions() -> pd.DataFrame:
    df = pd.read_csv(MAN / "japanese_equity_transitions.csv")
    return df[["project", "transition_year", "japanese_equity_pct_before",
               "japanese_equity_pct_after"]]


def equity_step(row, transitions: pd.DataFrame) -> float:
    """Step-function for Japanese equity pct in (project, year)."""
    t = transitions[transitions.project == row["project"]]
    if t.empty:
        # No documented transition — use 'initial' value pre-2010, 'current' from 2010+
        return row["equity_initial"] if row["year"] < 2010 else row["equity_current"]
    # Apply transitions in order
    eq = row["equity_initial"]
    for _, tr in t.sort_values("transition_year").iterrows():
        if row["year"] >= tr["transition_year"]:
            eq = tr["japanese_equity_pct_after"]
    return eq


def build_skeleton(projects: pd.DataFrame, years: range) -> pd.DataFrame:
    rows = []
    for _, p in projects.iterrows():
        for y in years:
            if y < p["first_year"]:
                continue
            rows.append({
                "project": p["project"],
                "commodity": p["commodity"],
                "year": y,
                "first_export_year": p["first_year"],
                "years_since_first_export": y - p["first_year"],
                "equity_initial": p["equity_initial"],
                "equity_current": p["equity_current"],
                "nameplate_mtpa": p["nameplate_mtpa"],
            })
    return pd.DataFrame(rows)


def attach_production_and_share(panel: pd.DataFrame) -> pd.DataFrame:
    prod = pd.read_csv(MAN / "project_production_annual.csv")
    keep = ["project", "year", "mtpa_production", "japan_share_of_output_pct"]
    return panel.merge(prod[keep], on=["project", "year"], how="left")


def attach_spa_status(panel: pd.DataFrame) -> pd.DataFrame:
    cohorts = pd.read_csv(MAN / "coking_coal_spa_cohorts.csv")
    # An SPA is "in force" from first_jsm_spa_year onward (the JSM Annual
    # Benchmark regime persisted continuously through 2010 for all listed mines).
    out = panel.merge(
        cohorts[["project", "first_jsm_spa_year", "has_spa_through_2010"]],
        on="project", how="left"
    )
    out["has_japanese_spa"] = (
        (out["first_jsm_spa_year"].notna())
        & (out["year"] >= out["first_jsm_spa_year"])
        & (out["has_spa_through_2010"] == 1)
    ).astype(int)
    out["spa_age_years"] = np.where(
        out["has_japanese_spa"] == 1,
        out["year"] - out["first_jsm_spa_year"],
        np.nan
    )
    return out


def attach_prices(panel: pd.DataFrame) -> pd.DataFrame:
    macro = pd.read_csv(PROC / "fossil_era_panel.csv")
    keep_cols = [c for c in
                 ["year", "coal_australian_usd_per_mt",
                  "iron_ore_cfr_spot_usd_per_dmtu",
                  "lng_japan_usd_per_mmbtu", "jpy_per_aud"]
                 if c in macro.columns]
    return panel.merge(macro[keep_cols], on="year", how="left")


def main() -> None:
    projects = load_projects()
    transitions = load_transitions()
    print(f"Loaded {len(projects)} projects, {len(transitions)} equity transitions.")

    panel = build_skeleton(projects, PANEL_YEARS)
    panel["japanese_equity_pct"] = panel.apply(
        equity_step, axis=1, transitions=transitions)
    panel["japanese_equity_change_flag"] = panel.apply(
        lambda r: int(((transitions.project == r["project"])
                       & (transitions.transition_year == r["year"])).any()),
        axis=1)

    panel = attach_production_and_share(panel)
    panel = attach_spa_status(panel)
    panel = attach_prices(panel)

    panel = panel.sort_values(["project", "year"]).reset_index(drop=True)
    out_path = PROC / "project_year_panel.csv"
    panel.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  shape={panel.shape}")

    print("\nSample (BMA mines around 2001 transition):")
    bma = panel[panel.project.str.contains("BMA", na=False)
                & panel.year.between(1999, 2003)]
    print(bma[["project", "year", "japanese_equity_pct",
               "japanese_equity_change_flag", "mtpa_production",
               "has_japanese_spa"]].to_string(index=False))

    print("\nSample (Robe River around 1977 transition):")
    rob = panel[(panel.project == "Robe River") & panel.year.between(1975, 1979)]
    print(rob[["project", "year", "japanese_equity_pct",
               "japanese_equity_change_flag", "has_japanese_spa"]].to_string(index=False))

    print("\nCoverage summary — non-null mtpa_production by project:")
    cov = panel.groupby("project")["mtpa_production"].apply(
        lambda s: f"{s.notna().sum()}/{len(s)} years")
    print(cov.to_string())


if __name__ == "__main__":
    sys.exit(main())
