"""Assemble an *energy-only* crowding-analysis panel.

Replaces the all-mining DV and total-Japan FDI from the original crowding notebook
with sector-specific series:

DV options (Australian energy capex / output):
  - energy_exploration_aud_million        ABS 8412.0, coal+petroleum, 1975-2024 (long)
  - energy_purchases_aud_million          ABS 8155.0, coal+oil&gas, 2007-2024 (short)
  - energy_iva_aud_million                ABS 8155.0, coal+oil&gas value added
  - mining_capex_aud_million              ABS 5625.0, all mining (legacy comparison)

IV options (Japanese FDI):
  - jpn_fdi_mining_usd_million            BoJ Sheet 3 "Mining" -> Australia, 2014-2024
  - jpn_fdi_total_usd_million             BoJ Sheet 3 total -> Australia, 2014-2024
  - jpn_fdi_jetro_total_usd_million       JETRO/BoP, 1987-2024 (legacy, all sectors)

Counterfactual / placebo:
  - metal_ore_purchases_aud_million       iron ore + gold + base metals 2007-2024
  - iron_ore_exploration_aud_million      MIN_EXP iron ore, 1988-2024

Project-finance channel:
  - jbic_australia_press.csv              hand-extracted JBIC loan amounts by year

Output: data/processed/energy_crowding_panel.csv
"""
from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw"
PROC = REPO / "data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)


def main() -> None:
    # 1. ABS exploration (1975-2024)
    expl = pd.read_csv(RAW / "abs_exploration_annual.csv")
    expl = expl.rename(columns={
        "petroleum_exp_aud_million": "petroleum_exploration_aud_million",
        "coal": "coal_exploration_aud_million",
        "iron_ore": "iron_ore_exploration_aud_million",
        "gold": "gold_exploration_aud_million",
        "uranium": "uranium_exploration_aud_million",
        "all_minerals": "all_mineral_exploration_aud_million",
        "energy_exploration_aud_million": "energy_exploration_aud_million",
    })
    expl = expl[["year",
                   "petroleum_exploration_aud_million",
                   "coal_exploration_aud_million",
                   "iron_ore_exploration_aud_million",
                   "gold_exploration_aud_million",
                   "uranium_exploration_aud_million",
                   "all_mineral_exploration_aud_million",
                   "energy_exploration_aud_million"]]

    # 2. ABS 8155.0 energy-sector aggregate (2007-2024)
    sec = pd.read_csv(RAW / "abs_energy_sector_aggregate.csv")
    # Keep only the columns that matter for the crowding regression
    keep = ["year",
              "energy_iva_aud_million",
              "energy_purchases_aud_million",
              "energy_sales_income_aud_million",
              "metal_ore_iva_aud_million",
              "metal_ore_purchases_aud_million",
              "mining_total_iva_aud_million",
              "mining_total_purchases_aud_million"]
    sec = sec[[c for c in keep if c in sec.columns]]

    # 3. All-mining capex (1988-2024) — legacy DV for comparison
    capex = pd.read_csv(RAW / "abs_mining_capex_annual.csv")
    capex = capex.rename(columns={"capex_aud_million": "mining_capex_aud_million"})

    # 4. BoJ FDI by industry (2014-2024)
    boj = pd.read_csv(RAW / "boj" / "japan_fdi_to_australia_by_industry.csv")
    flow = boj[boj.series_type == "flow"]
    boj_wide = flow.pivot_table(index="year", columns="industry",
                                  values="value_usd_million").reset_index()
    boj_wide = boj_wide.rename(columns={
        "mining": "jpn_fdi_mining_usd_million",
        "manufacturing_total": "jpn_fdi_manufacturing_usd_million",
        "total": "jpn_fdi_total_usd_million",
        "communications": "jpn_fdi_communications_usd_million",
        "finance_insurance": "jpn_fdi_finance_usd_million",
        "real_estate": "jpn_fdi_real_estate_usd_million",
    })
    boj_wide = boj_wide[["year",
                            "jpn_fdi_mining_usd_million",
                            "jpn_fdi_manufacturing_usd_million",
                            "jpn_fdi_total_usd_million",
                            "jpn_fdi_communications_usd_million",
                            "jpn_fdi_finance_usd_million",
                            "jpn_fdi_real_estate_usd_million"]]

    # 5a. Legacy JETRO total FDI (1987-2024)
    jetro = pd.read_csv(RAW / "japan_fdi_to_australia.csv")
    jetro = jetro.rename(columns={"fdi_flow_usd_million": "jpn_fdi_jetro_total_usd_million"})
    jetro = jetro[["year", "jpn_fdi_jetro_total_usd_million"]]

    # 5b. DFAT IIA Japan FDI (Australia-side ABS data, 2001-2025)
    dfat = pd.read_csv(RAW / "dfat_data" / "japan_fdi_wide.csv")
    dfat_keep = {
        "year": "year",
        "jpn_transactions_direct_investment_in_australia":
            "jpn_dfat_direct_flow_aud_million",
        "jpn_transactions_foreign_investment_in_australia":
            "jpn_dfat_total_flow_aud_million",
        "jpn_levels_direct_investment_in_australia":
            "jpn_dfat_direct_stock_aud_million",
        "jpn_levels_foreign_investment_in_australia":
            "jpn_dfat_total_stock_aud_million",
        "jpn_levels_total_equity":
            "jpn_dfat_total_equity_stock_aud_million",
        "jpn_levels_total_debt":
            "jpn_dfat_total_debt_stock_aud_million",
        "jpn_income_investment_income":
            "jpn_dfat_investment_income_aud_million",
    }
    dfat = dfat[[c for c in dfat_keep if c in dfat.columns]].rename(columns=dfat_keep)

    # 5c. Coking coal exports Aus -> Jpn (1964-1982, hand-coded from manual file)
    coking = pd.read_csv(REPO / "data" / "manual" / "coking_coal_industry.csv")
    coking = coking.rename(columns={
        "Year": "year",
        "Value ($, Thousands)": "coking_coal_export_usd_thousand",
        "Tonnes (Thousands)": "coking_coal_export_kt",
    })
    coking["coking_coal_export_usd_million"] = (
        coking["coking_coal_export_usd_thousand"] / 1000)
    coking["coking_coal_export_kt"] = coking["coking_coal_export_kt"].astype(float)
    coking["coking_coal_export_mt"] = coking["coking_coal_export_kt"] / 1000
    coking = coking[["year",
                       "coking_coal_export_usd_million",
                       "coking_coal_export_mt"]]

    # 6. Macro controls already in repo
    wb = pd.read_csv(RAW / "world_bank_macro.csv")
    gdp = wb[wb.indicator_code == "NY.GDP.MKTP.CD"].pivot_table(
        index="year", columns="country", values="value").reset_index()
    gdp = gdp.rename(columns={"CHN": "gdp_chn_usd",
                                "AUS": "gdp_aus_usd",
                                "JPN": "gdp_jpn_usd"})
    gdp = gdp[["year", "gdp_chn_usd", "gdp_aus_usd", "gdp_jpn_usd"]]

    prices = pd.read_csv(RAW / "pink_sheet_prices.csv")
    pr = prices.pivot_table(index="year", columns="commodity",
                              values="price_nominal_usd").reset_index()

    fx = pd.read_csv(RAW / "exchange_rates.csv")
    fx_keep = fx[["year", "aud_per_usd"]]

    # 7. JBIC project-finance series (annual sum of USD loan commitments)
    jbic = pd.read_csv(RAW / "jbic" / "jbic_australia_press.csv")

    def jbic_year(date_str):
        if not isinstance(date_str, str) or not date_str:
            return None
        m = pd.to_datetime(date_str, errors="coerce")
        return m.year if pd.notna(m) else None

    jbic["year"] = jbic["date"].apply(jbic_year)
    # Pull the *first* USD amount mentioned per release as JBIC's share
    def first_usd(s):
        if not isinstance(s, str):
            return None
        for part in s.split("|"):
            part = part.strip()
            if "USD" in part:
                tokens = part.split()
                try:
                    i = tokens.index("USD")
                    amt = float(tokens[i + 1])
                    unit = tokens[i + 2].lower()
                    return amt * (1000 if "bil" in unit else 1)
                except (ValueError, IndexError):
                    continue
        return None

    jbic["jbic_loan_usd_million"] = jbic["loan_amounts_mentioned"].apply(first_usd)
    # Flag energy projects (LNG, gas, oil, coal) vs other (iron ore, lead, MOUs)
    energy_kw = ["LNG", "Gas", "Scarborough", "Ichthys", "Wheatstone", "Barossa",
                  "Queensland Curtis", "Browse", "Coal", "Coking"]
    jbic["is_energy"] = jbic["title"].apply(
        lambda t: any(k.lower() in t.lower() for k in energy_kw))
    jbic_ann = (jbic.dropna(subset=["year"])
                .groupby("year")
                .apply(lambda g: pd.Series({
                    "jbic_all_loans_usd_million":
                        g["jbic_loan_usd_million"].sum(skipna=True),
                    "jbic_energy_loans_usd_million":
                        g.loc[g["is_energy"], "jbic_loan_usd_million"].sum(skipna=True),
                    "jbic_n_releases": len(g),
                    "jbic_n_energy_releases": g["is_energy"].sum(),
                }), include_groups=False)
                .reset_index())
    jbic_ann["year"] = jbic_ann["year"].astype(int)

    # 8. Merge everything on year
    panel = (expl
             .merge(sec, on="year", how="outer")
             .merge(capex, on="year", how="outer")
             .merge(boj_wide, on="year", how="outer")
             .merge(jetro, on="year", how="outer")
             .merge(dfat, on="year", how="outer")
             .merge(coking, on="year", how="outer")
             .merge(gdp, on="year", how="outer")
             .merge(pr, on="year", how="outer")
             .merge(fx_keep, on="year", how="outer")
             .merge(jbic_ann, on="year", how="outer")
             .sort_values("year")
             .reset_index(drop=True))
    panel = panel[(panel.year >= 1962) & (panel.year <= 2025)]

    out = PROC / "energy_crowding_panel.csv"
    panel.to_csv(out, index=False)
    print(f"Wrote {out}  shape={panel.shape}, years {panel.year.min()}-{panel.year.max()}")

    # Quick sanity-check tables
    print("\nFossil-era foundation (1964-1985): coking coal exports vs petroleum exploration")
    pick_hist = ["year",
                   "coking_coal_export_mt",
                   "coking_coal_export_usd_million",
                   "petroleum_exploration_aud_million"]
    pick_hist = [c for c in pick_hist if c in panel.columns]
    print(panel[panel.year.between(1964, 1985)][pick_hist].round(1).to_string(index=False))

    print("\nRecent panel (2014-2025): all key series")
    pick = ["year",
              "energy_exploration_aud_million",
              "energy_purchases_aud_million",
              "mining_capex_aud_million",
              "jpn_fdi_mining_usd_million",
              "jpn_dfat_direct_flow_aud_million",
              "jpn_dfat_direct_stock_aud_million",
              "jpn_fdi_jetro_total_usd_million",
              "jbic_energy_loans_usd_million"]
    pick = [c for c in pick if c in panel.columns]
    print(panel[panel.year.isin(range(2014, 2025))][pick].round(0).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
