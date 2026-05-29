"""Build a panel for the Aus->World energy-exports regression.

This is the world-total counterpart to fossil_era_panel.csv. Same
columns as the bilateral panel, but with three NEW dependent-variable
groups added:

  export_coal_usd_to_world      Australia->World, AUS-reported
  export_lng_usd_to_world       Australia->World, AUS-reported (HS 2711)
  export_energy_usd_to_world    sum of the two above
  export_coal_usd_to_exjpn      world minus consolidated bilateral
  export_lng_usd_to_exjpn       world minus consolidated bilateral
  export_energy_usd_to_exjpn    sum of the two above

The bilateral panel uses max(AUS-reported, JPN-reported) per commodity
because Australia's customs office suppresses LNG bilateral data. The
world-aggregate AUS report is NOT suppressed (verified manually -
2024 AUS-reported world LNG = USD 46B, matching DFAT's AUD 64B).

So the ex-Japan calculation is:
    world - bilateral_consolidated
both numerators internally consistent: the AUS-world series includes
the actual (un-suppressed) Japan-bound LNG even though the AUS->JPN
disaggregation is censored, and we subtract the true (mirror-derived)
Japan-bound amount.

Adds Chinese GDP as a new control, because no Aus->World regression
should be run without controlling for the post-2001 China shock.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"
OUT = REPO_ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def load_world_trade() -> pd.DataFrame:
    """Australia-as-reporter, partner=World, Comtrade.

    No mirror is feasible at the world level (would require summing
    every importing country). Confidentiality check confirms LNG is
    not suppressed at the world aggregate.
    """
    df = pd.read_csv(RAW / "comtrade_aus_to_world.csv")
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

    # If both HS and SITC are present for a year (overlap years), prefer HS.
    # In practice they shouldn't overlap because HS_START=1988 and
    # SITC_END=1987, but be defensive.
    df["pref"] = df["classification"].map({"HS": 0, "S1": 1})
    df = df.sort_values(["year", "series", "pref"])
    df = df.drop_duplicates(["year", "series"], keep="first")

    out = df.pivot_table(
        index="year", columns="series", values="value_usd", aggfunc="first"
    ).reset_index()
    out = out.rename(
        columns={c: f"export_{c}_usd_to_world" for c in out.columns if c != "year"}
    )
    return out


def load_apac_trade() -> pd.DataFrame:
    """Australia-as-reporter, partner = each of (CHN, KOR, THA, MYS, SGP, VNM).

    Used to build an Aus->APAC aggregate (Japan + six above). Coal HS 2701
    is reliable AUS-reported. For LNG (HS 2711) AUS suppresses bilateral
    values via firm-level confidentiality, so we substitute partner-import
    mirror data (data/raw/comtrade_apac_lng_mirror.csv) when it is larger,
    same logic as JPN-import mirror in fetch_comtrade.py.
    """
    path = RAW / "comtrade_aus_to_apac.csv"
    if not path.exists():
        return pd.DataFrame(columns=["year"])
    df = pd.read_csv(path)
    commodity_map = {
        "coal": "coal",
        "natural_gas_lng_gaseous": "lng",
    }
    df["series"] = df["commodity"].map(commodity_map)
    df = df.dropna(subset=["series"])

    # Substitute LNG mirror data per-(year, partner) where it is larger.
    mirror_path = RAW / "comtrade_apac_lng_mirror.csv"
    if mirror_path.exists():
        mirror = pd.read_csv(mirror_path)[["year", "reporter_iso", "value_usd"]]
        mirror = mirror.rename(
            columns={"reporter_iso": "partner_iso", "value_usd": "value_mirror"}
        )
        lng_mask = df["series"] == "lng"
        lng = df.loc[lng_mask].merge(
            mirror, on=["year", "partner_iso"], how="left"
        )
        lng["value_usd"] = lng[["value_usd", "value_mirror"]].max(axis=1)
        df = pd.concat([df.loc[~lng_mask], lng.drop(columns="value_mirror")],
                       ignore_index=True)

    # Sum across the six APAC partners per (year, series).
    agg = (
        df.groupby(["year", "series"])["value_usd"]
        .sum(min_count=1)
        .reset_index()
    )
    out = agg.pivot(index="year", columns="series", values="value_usd").reset_index()
    out = out.rename(
        columns={
            "coal": "export_coal_usd_to_apac_others",
            "lng": "export_lng_usd_to_apac_others",
        }
    )
    return out


def load_china_gdp() -> pd.DataFrame:
    """Add Chinese GDP. The post-2001 China demand shock is the single
    most important control for any Aus->World energy regression - it
    drives both Australian energy exports and (via global commodity
    cycles) Japanese FDI in Australia.
    """
    df = pd.read_csv(RAW / "world_bank_macro.csv")
    chn = df[(df.country == "CHN") & (df.indicator_name == "gdp_current_usd")]
    return chn[["year", "value"]].rename(columns={"value": "chn_gdp_current_usd"})


def build_world_panel() -> pd.DataFrame:
    # Start from the existing fossil panel (has bilateral Aus->Japan and
    # all the controls already wired up).
    fossil = pd.read_csv(OUT / "fossil_era_panel.csv")

    # Add the world DV columns
    world = load_world_trade()
    df = fossil.merge(world, on="year", how="left")

    # Add Chinese GDP control
    chn = load_china_gdp()
    df = df.merge(chn, on="year", how="left")

    # Add APAC (CHN+KOR+THA+MYS+SGP+VNM) aggregate columns
    apac_others = load_apac_trade()
    if not apac_others.empty:
        df = df.merge(apac_others, on="year", how="left")
    else:
        df["export_coal_usd_to_apac_others"] = np.nan
        df["export_lng_usd_to_apac_others"] = np.nan

    # Floor the world value at the consolidated bilateral. Reasoning:
    # the world total can never be less than what we know went to
    # Japan. In years where AUS-reported world < JPN-reported imports
    # from AUS (mostly pre-2005 LNG and pre-1975 coal, due to
    # Comtrade reporter asymmetry + early-NWS confidentiality), we
    # substitute the bilateral as the floor. This sets ex-Japan to
    # zero in those years, which is approximately correct -
    # Australian LNG was almost entirely Japan-bound before Korea
    # and China started buying meaningfully in the mid-2000s.
    df["export_coal_usd_to_world_raw"] = df["export_coal_usd_to_world"]
    df["export_lng_usd_to_world_raw"] = df["export_lng_usd_to_world"]
    df["export_coal_usd_to_world"] = df[
        ["export_coal_usd_to_world", "export_coal_usd_to_jpn"]
    ].max(axis=1)
    df["export_lng_usd_to_world"] = df[
        ["export_lng_usd_to_world", "export_lng_usd_to_jpn"]
    ].max(axis=1)

    # Construct ex-Japan as World minus consolidated bilateral. After
    # the flooring step, this is always >= 0.
    df["export_coal_usd_to_exjpn"] = (
        df["export_coal_usd_to_world"] - df["export_coal_usd_to_jpn"]
    )
    df["export_lng_usd_to_exjpn"] = (
        df["export_lng_usd_to_world"] - df["export_lng_usd_to_jpn"]
    )
    df["export_energy_usd_to_world"] = (
        df["export_coal_usd_to_world"].fillna(0)
        + df["export_lng_usd_to_world"].fillna(0)
    )
    df["export_energy_usd_to_exjpn"] = (
        df["export_coal_usd_to_exjpn"].fillna(0)
        + df["export_lng_usd_to_exjpn"].fillna(0)
    )

    # APAC aggregate = Japan + 6 others (CHN+KOR+THA+MYS+SGP+VNM).
    # Japan uses the consolidated bilateral (max of AUS-export and JPN-import
    # mirror) so LNG isn't censored. The other six use AUS-as-reporter only.
    df["export_coal_usd_to_apac"] = (
        df["export_coal_usd_to_jpn"].fillna(0)
        + df["export_coal_usd_to_apac_others"].fillna(0)
    )
    df["export_lng_usd_to_apac"] = (
        df["export_lng_usd_to_jpn"].fillna(0)
        + df["export_lng_usd_to_apac_others"].fillna(0)
    )
    df["export_energy_usd_to_apac"] = (
        df["export_coal_usd_to_apac"] + df["export_lng_usd_to_apac"]
    )
    # NaN out APAC totals in years where neither Japan nor APAC-others has data
    no_apac = (
        df[["export_coal_usd_to_jpn", "export_coal_usd_to_apac_others",
            "export_lng_usd_to_jpn",  "export_lng_usd_to_apac_others"]].isna().all(axis=1)
    )
    df.loc[no_apac, "export_energy_usd_to_apac"] = np.nan
    df.loc[no_apac, "export_coal_usd_to_apac"] = np.nan
    df.loc[no_apac, "export_lng_usd_to_apac"] = np.nan

    # Drop synthesized energy totals in years where all components are missing.
    df.loc[
        df[["export_coal_usd_to_world", "export_lng_usd_to_world"]].isna().all(axis=1),
        "export_energy_usd_to_world",
    ] = np.nan
    df.loc[
        df[["export_coal_usd_to_exjpn", "export_lng_usd_to_exjpn"]].isna().all(axis=1),
        "export_energy_usd_to_exjpn",
    ] = np.nan

    # After flooring, ex-Japan is non-negative by construction. Report
    # how many years required the floor as a diagnostic.
    n_coal_floored = (
        (df["export_coal_usd_to_world_raw"] < df["export_coal_usd_to_jpn"])
        & df["export_coal_usd_to_world_raw"].notna()
    ).sum()
    n_lng_floored = (
        (df["export_lng_usd_to_world_raw"] < df["export_lng_usd_to_jpn"])
        & df["export_lng_usd_to_world_raw"].notna()
    ).sum()
    print(
        f"Floored AUS-world to bilateral in {n_coal_floored} coal years "
        f"and {n_lng_floored} LNG years (reporter asymmetry + early-NWS "
        f"confidentiality)."
    )

    return df


def main() -> None:
    df = build_world_panel()
    out_path = OUT / "world_exports_panel.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  shape={df.shape}")

    cols = [
        "year",
        "export_energy_usd_to_jpn",
        "export_energy_usd_to_world",
        "export_energy_usd_to_exjpn",
        "export_coal_usd_to_world",
        "export_lng_usd_to_world",
    ]
    print("\nRecent rows (USD billions):")
    show = df[df.year.between(2018, 2024)][cols].copy()
    for c in cols:
        if c != "year":
            show[c] = show[c] / 1e9
    print(show.round(2).to_string(index=False))

    print("\n--- Sanity checks ---")
    y2024 = df[df.year == 2024].iloc[0]
    print(f"  2024 Aus->World coal:    USD {y2024['export_coal_usd_to_world']/1e9:.1f}B  "
          f"(DFAT ~AUD 73B = USD ~48B)")
    print(f"  2024 Aus->World LNG:     USD {y2024['export_lng_usd_to_world']/1e9:.1f}B  "
          f"(DFAT ~AUD 64B = USD ~42B)")
    print(f"  2024 Aus->Japan energy:  USD {y2024['export_energy_usd_to_jpn']/1e9:.1f}B")
    print(f"  2024 Aus->World energy:  USD {y2024['export_energy_usd_to_world']/1e9:.1f}B")
    print(f"  2024 Aus->ex-Jpn energy: USD {y2024['export_energy_usd_to_exjpn']/1e9:.1f}B")

    jpn_share = y2024["export_energy_usd_to_jpn"] / y2024["export_energy_usd_to_world"]
    print(f"  2024 Japan share of Aus energy exports: {jpn_share:.1%}")


if __name__ == "__main__":
    sys.exit(main())
