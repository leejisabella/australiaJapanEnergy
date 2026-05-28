"""Build a panel for the Aus->World energy-EXPORT-QUANTITY regression.

This is the quantity counterpart to build_world_exports_panel.py. The DV
is physical export volume (tonnes) converted to energy-equivalent units
(MMBtu) so coal and LNG can be summed sensibly. The motivation is that
the dollar-value DV is contaminated by price: the 2022 LNG spike, for
example, is mostly a price effect, not a quantity effect.

Data sources for the quantity series, in priority order:

  1. Comtrade kg (already pulled by fetch_comtrade.py and
     fetch_comtrade_aus_to_world.py). Coverage:
       - Aus->Japan: COMPLETE for coal and LNG (JPN-reporter mirror).
       - Aus->World: COMPLETE for coal/iron ore. LNG has a 10-year
         hole 1990-1999, a 2012 gap, and a 2020 anomaly (Comtrade
         reports 45 Mt vs industry ~78 Mt).

  2. OWID gas_production - gas_consumption (data/raw/owid_energy_full.csv).
     OWID synthesizes from Energy Institute, Ember, IEA. Used to fill
     the Comtrade LNG-world gaps. The series is Australia's net gas
     exports in TWh; converted to Mt LNG using the standard industry
     factor 1 Mt LNG = 14.44 TWh (HHV: 52 GJ/t / 3600 GJ/GWh / 1000).

Energy-equivalent aggregation. We convert both coal and LNG tonnes to
MMBtu (chosen because the LNG price control is denominated in $/MMBtu):

  Coal:  26 GJ/t = 24.64 MMBtu/t  (ABS / DISR Australian thermal
         coal classification; HHV; varies by grade)
  LNG:   52 GJ/t = 49.28 MMBtu/t  (industry standard for Australian
         LNG; HHV)

Cross-validation: in years where both Comtrade kg and OWID-derived are
available, they agree within ~10% for 2000-2004 and 2021-2024. The
2005-2014 window shows OWID running 20-90% below Comtrade, which we
flag as a known discrepancy. Within the regression sample (1992-2024
after the Delta-log year-1 drop and the 3-year FDI lag), only the
1992-1999 LNG-world values rely entirely on OWID.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"
OUT = REPO_ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# Energy-equivalent conversion factors
GJ_PER_MMBTU = 1.055056
COAL_GJ_PER_T = 26.0   # ABS / DISR Australian thermal coal
LNG_GJ_PER_T = 52.0    # Industry standard for Aus LNG (HHV)
COAL_MMBTU_PER_T = COAL_GJ_PER_T / GJ_PER_MMBTU
LNG_MMBTU_PER_T = LNG_GJ_PER_T / GJ_PER_MMBTU
TWH_PER_MT_LNG = LNG_GJ_PER_T * 1e6 / 3600 / 1000  # = 14.44 TWh/Mt


def load_comtrade_bilateral_kg() -> pd.DataFrame:
    """Aus->Japan kg series. For LNG use the JPN-reporter mirror; for
    coal/iron ore use AUS-reporter (matching the bilateral USD panel)."""
    df = pd.read_csv(RAW / "comtrade_aus_to_jpn.csv")

    out_rows = []
    for year in sorted(df.year.unique()):
        sub = df[df.year == year]
        rec = {"year": year}
        # Coal: prefer AUS-reporter (matches DFAT). Use 2701 or SITC 321.
        coal = sub[
            ((sub.classification == "HS") & (sub.commodity == "coal"))
            | ((sub.classification == "S1") & (sub.commodity == "coal_coke_briquettes"))
        ]
        aus_coal = coal[coal.reporter == "AUS"]["net_weight_kg"].dropna()
        jpn_coal = coal[coal.reporter == "JPN"]["net_weight_kg"].dropna()
        if len(aus_coal):
            rec["export_coal_kg_to_jpn"] = float(aus_coal.iloc[0])
        elif len(jpn_coal):
            rec["export_coal_kg_to_jpn"] = float(jpn_coal.iloc[0])
        # LNG: JPN-reporter is essentially the only reliable side. Use
        # HS 2711 (broader) to match the USD panel.
        lng = sub[
            ((sub.classification == "HS") & (sub.commodity == "natural_gas_lng_gaseous"))
            | ((sub.classification == "S1") & (sub.commodity == "gas_natural_manufactured"))
        ]
        jpn_lng = lng[lng.reporter == "JPN"]["net_weight_kg"].dropna()
        aus_lng = lng[lng.reporter == "AUS"]["net_weight_kg"].dropna()
        # Use the larger of the two (same logic as the USD consolidation).
        candidates = list(jpn_lng) + list(aus_lng)
        candidates = [c for c in candidates if c == c]  # drop NaN
        if candidates:
            rec["export_lng_kg_to_jpn"] = float(max(candidates))
        out_rows.append(rec)
    return pd.DataFrame(out_rows)


def load_comtrade_world_kg() -> pd.DataFrame:
    """Aus->World kg series. AUS-reporter only (partner=World)."""
    df = pd.read_csv(RAW / "comtrade_aus_to_world.csv")
    code_map = {
        ("S1", "coal_coke_briquettes"): "coal",
        ("HS", "coal"): "coal",
        ("HS", "natural_gas_lng_gaseous"): "lng",
        ("S1", "gas_natural_manufactured"): "lng",
    }
    df["series"] = df.set_index(["classification", "commodity"]).index.map(code_map)
    df = df.dropna(subset=["series"]).copy()
    df["pref"] = df["classification"].map({"HS": 0, "S1": 1})
    df = df.sort_values(["year", "series", "pref"]).drop_duplicates(["year", "series"], keep="first")

    out = df.pivot_table(
        index="year", columns="series", values="net_weight_kg", aggfunc="first"
    ).reset_index()
    out = out.rename(
        columns={c: f"export_{c}_kg_to_world_comtrade" for c in out.columns if c != "year"}
    )
    return out


def load_owid_lng_world_kg() -> pd.DataFrame:
    """OWID-derived Aus->World LNG quantity series.

    Computed as gas_production - gas_consumption (TWh) converted to
    Mt LNG using the HHV factor 14.44 TWh/Mt.

    Cross-validation against Comtrade in overlap years:
      2000-2004: ratios 0.86-1.06 (agree)
      2005-2014: ratios 1.30-1.94 (OWID lower; possible coalbed
                 methane / statistical reconciliation differences)
      2015-2019: ratios 1.09-1.33 (close)
      2020:      ratio 0.63 (Comtrade anomalous; OWID 71.6 Mt matches
                 EI industry ~78 Mt)
      2021-2024: ratios 1.04-1.09 (agree)
    """
    owid = pd.read_csv(RAW / "owid_energy_full.csv")
    aus = owid[owid.country == "Australia"].copy()
    aus["net_gas_export_twh"] = aus["gas_production"] - aus["gas_consumption"]
    aus["lng_owid_mt"] = aus["net_gas_export_twh"] / TWH_PER_MT_LNG
    # Floor at zero (1985-1988 should be zero — NWS first cargo Aug 1989)
    aus.loc[aus["lng_owid_mt"] < 0, "lng_owid_mt"] = 0.0
    aus["export_lng_kg_to_world_owid"] = aus["lng_owid_mt"] * 1e9
    return aus[["year", "export_lng_kg_to_world_owid"]].copy()


def build_quantity_panel() -> pd.DataFrame:
    # Start with the existing USD-based world panel (has all controls
    # plus the bilateral and world USD DVs and Chinese GDP).
    base = pd.read_csv(OUT / "world_exports_panel.csv")

    # Add the kg series
    bil = load_comtrade_bilateral_kg()
    world_ct = load_comtrade_world_kg()
    world_owid = load_owid_lng_world_kg()

    df = base.merge(bil, on="year", how="left")
    df = df.merge(world_ct, on="year", how="left")
    df = df.merge(world_owid, on="year", how="left")

    # Construct the Aus->World LNG kg series: prefer Comtrade where
    # available AND not anomalous (2020); fall back to OWID otherwise.
    # The 2020 anomaly is detected by comparing the per-tonne implied
    # value: Comtrade reports $387/t for 2020 which is reasonable but
    # the kg is suspiciously low.
    df["export_lng_kg_to_world"] = df["export_lng_kg_to_world_comtrade"]
    # Manual substitution: 2020 anomaly
    df.loc[df.year == 2020, "export_lng_kg_to_world"] = df.loc[
        df.year == 2020, "export_lng_kg_to_world_owid"
    ].values
    # Fill remaining Comtrade gaps with OWID
    mask_missing = df["export_lng_kg_to_world"].isna() & df["export_lng_kg_to_world_owid"].notna()
    df.loc[mask_missing, "export_lng_kg_to_world"] = df.loc[
        mask_missing, "export_lng_kg_to_world_owid"
    ]

    # Track which source was used (for documentation in the notebook)
    df["lng_world_source"] = "missing"
    df.loc[df["export_lng_kg_to_world_comtrade"].notna()
           & (df.year != 2020), "lng_world_source"] = "comtrade"
    df.loc[df.year == 2020, "lng_world_source"] = "owid_2020_anomaly"
    df.loc[(df["lng_world_source"] == "missing")
           & df["export_lng_kg_to_world_owid"].notna(),
           "lng_world_source"] = "owid_comtrade_missing"

    # Coal world: Comtrade for available years; for the single 2019
    # gap, linearly interpolate from 2018 and 2020 (both reliable
    # Comtrade observations: 386.1 Mt and 370.8 Mt respectively).
    df["export_coal_kg_to_world"] = df["export_coal_kg_to_world_comtrade"]
    df["coal_world_source"] = "missing"
    df.loc[df["export_coal_kg_to_world_comtrade"].notna(), "coal_world_source"] = "comtrade"
    df = df.sort_values("year").reset_index(drop=True)
    coal_w = df["export_coal_kg_to_world"]
    # Find single-year gaps (NaN between two non-NaN years) and interpolate
    for i in range(1, len(df) - 1):
        if pd.isna(coal_w.iloc[i]) and pd.notna(coal_w.iloc[i - 1]) and pd.notna(coal_w.iloc[i + 1]):
            v = (coal_w.iloc[i - 1] + coal_w.iloc[i + 1]) / 2.0
            df.loc[df.index[i], "export_coal_kg_to_world"] = v
            df.loc[df.index[i], "coal_world_source"] = "interpolated_neighbor"

    # Floor world quantity at bilateral quantity (same logic as the USD
    # panel - world cannot be less than what we know went to Japan).
    # Only meaningful where both are non-NaN.
    df["export_lng_kg_to_world_raw"] = df["export_lng_kg_to_world"].copy()
    df["export_coal_kg_to_world_raw"] = df["export_coal_kg_to_world"].copy()
    have_lng_world = df["export_lng_kg_to_world"].notna() & df["export_lng_kg_to_jpn"].notna()
    have_coal_world = df["export_coal_kg_to_world"].notna() & df["export_coal_kg_to_jpn"].notna()
    df.loc[have_lng_world, "export_lng_kg_to_world"] = df.loc[have_lng_world, [
        "export_lng_kg_to_world", "export_lng_kg_to_jpn"
    ]].max(axis=1)
    df.loc[have_coal_world, "export_coal_kg_to_world"] = df.loc[have_coal_world, [
        "export_coal_kg_to_world", "export_coal_kg_to_jpn"
    ]].max(axis=1)

    # Ex-Japan = world - bilateral (>=0 by construction after floor)
    df["export_coal_kg_to_exjpn"] = (
        df["export_coal_kg_to_world"] - df["export_coal_kg_to_jpn"]
    )
    df["export_lng_kg_to_exjpn"] = (
        df["export_lng_kg_to_world"] - df["export_lng_kg_to_jpn"]
    )

    # Energy-equivalent aggregation: kg -> MMBtu
    for dest in ["jpn", "world", "exjpn"]:
        coal = df[f"export_coal_kg_to_{dest}"]
        lng = df[f"export_lng_kg_to_{dest}"]
        df[f"export_coal_mmbtu_to_{dest}"] = (coal / 1000) * COAL_MMBTU_PER_T
        df[f"export_lng_mmbtu_to_{dest}"] = (lng / 1000) * LNG_MMBTU_PER_T
        df[f"export_energy_mmbtu_to_{dest}"] = (
            df[f"export_coal_mmbtu_to_{dest}"].fillna(0)
            + df[f"export_lng_mmbtu_to_{dest}"].fillna(0)
        )
        df.loc[
            df[[f"export_coal_mmbtu_to_{dest}",
                f"export_lng_mmbtu_to_{dest}"]].isna().all(axis=1),
            f"export_energy_mmbtu_to_{dest}"
        ] = np.nan

    return df


def main() -> None:
    df = build_quantity_panel()
    out_path = OUT / "world_exports_quantity_panel.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  shape={df.shape}")

    print("\n--- Source mix for Aus->World LNG kg series ---")
    print(df["lng_world_source"].value_counts())

    print("\n--- Recent rows (Mt and PJ for readability) ---")
    show_cols = ["year",
                 "export_energy_mmbtu_to_jpn",
                 "export_energy_mmbtu_to_world",
                 "export_energy_mmbtu_to_exjpn",
                 "export_coal_kg_to_world",
                 "export_lng_kg_to_world",
                 "lng_world_source"]
    show = df[df.year.between(2018, 2024)][show_cols].copy()
    show["energy_jpn_PJ"] = show["export_energy_mmbtu_to_jpn"] * GJ_PER_MMBTU / 1e6
    show["energy_world_PJ"] = show["export_energy_mmbtu_to_world"] * GJ_PER_MMBTU / 1e6
    show["energy_exjpn_PJ"] = show["export_energy_mmbtu_to_exjpn"] * GJ_PER_MMBTU / 1e6
    show["coal_world_Mt"] = show["export_coal_kg_to_world"] / 1e9
    show["lng_world_Mt"] = show["export_lng_kg_to_world"] / 1e9
    print(show[["year", "energy_jpn_PJ", "energy_world_PJ", "energy_exjpn_PJ",
                "coal_world_Mt", "lng_world_Mt", "lng_world_source"]].round(1).to_string(index=False))

    print("\n--- Cross-validation against external anchors ---")
    y2022 = df[df.year == 2022].iloc[0]
    y2024 = df[df.year == 2024].iloc[0]
    print(f"  2022 Aus->World coal:  {y2022['export_coal_kg_to_world']/1e9:.1f} Mt  "
          f"(DISR Aus Petroleum Stats: ~338 Mt)")
    print(f"  2022 Aus->World LNG:   {y2022['export_lng_kg_to_world']/1e9:.1f} Mt  "
          f"(EI Stats Review: ~80 Mt)")
    print(f"  2024 Aus->World coal:  {y2024['export_coal_kg_to_world']/1e9:.1f} Mt  "
          f"(DISR: ~362 Mt)")
    print(f"  2024 Aus->World LNG:   {y2024['export_lng_kg_to_world']/1e9:.1f} Mt  "
          f"(EI: ~81 Mt)")
    print(f"  2022 Aus->Japan LNG:   {y2022['export_lng_kg_to_jpn']/1e9:.1f} Mt  "
          f"(Japan total LNG ~72 Mt x Aus share ~45% = ~32 Mt)")
    print(f"  2024 Aus->Japan LNG:   {y2024['export_lng_kg_to_jpn']/1e9:.1f} Mt  "
          f"(Japan total LNG ~66 Mt x Aus share ~40% = ~26 Mt)")

    # Final regression-sample coverage check
    KEYS = ["export_energy_mmbtu_to_jpn", "export_energy_mmbtu_to_world",
            "export_energy_mmbtu_to_exjpn", "fdi_flow_usd_million",
            "japan_lng_contracted_mtpa", "jpn_gdp_current_usd",
            "chn_gdp_current_usd", "lng_japan_usd_per_mmbtu",
            "coal_australian_usd_per_mt", "jpy_per_aud"]
    print("\nRegression-sample completeness (all key vars non-null, 1990-2024):")
    sub = df[(df.year >= 1990) & (df.year <= 2024)].dropna(subset=KEYS)
    print(f"  Rows: {len(sub)}  Years: {int(sub.year.min())}-{int(sub.year.max())}")


if __name__ == "__main__":
    sys.exit(main())
