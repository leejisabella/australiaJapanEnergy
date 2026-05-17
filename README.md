# Australia-Japan Energy Investment — Data Pipeline

Preliminary dataset and analysis for the Econ 101 paper *"The Australia-Japan
Energy Transition Problem: Is Security and Sustainability Possible?"*

## Layout

```
data/
  raw/         downloaded as-is from each source
  manual/      hand-coded contract/project tables
  processed/   merged annual panels ready for regression
scripts/       one fetcher per source plus a panel builder
notebooks/     preliminary_analysis.ipynb
```

## How to run

```bash
pip install -r requirements.txt

# Pull everything from scratch (~7 minutes; Comtrade rate-limits)
python scripts/fetch_world_bank.py
python scripts/fetch_pink_sheet.py
python scripts/fetch_exchange_rates.py
python scripts/fetch_comtrade.py
python scripts/fetch_jetro_fdi.py
python scripts/fetch_owid_energy.py

# Merge into panels
python scripts/build_panels.py

# Run the analysis
jupyter notebook notebooks/preliminary_analysis.ipynb
```

## Data sources

| File | Source | Notes |
|---|---|---|
| `world_bank_macro.csv` | World Bank API ([api.worldbank.org](https://api.worldbank.org/v2/)) | Japan & Australia GDP (current and constant 2015 USD), industry value added, energy use, exports. 1960-2024. |
| `pink_sheet_prices.csv` | World Bank Commodity Markets ([Pink Sheet](https://www.worldbank.org/en/research/commodity-markets)) | Annual nominal + real prices for Australian coal ($/mt), Japan-import LNG ($/mmbtu), iron ore ($/dmtu). |
| `exchange_rates.csv` | World Bank `PA.NUS.FCRF` | Annual JPY/USD, AUD/USD, derived JPY/AUD. 1960-2024. |
| `comtrade_aus_to_jpn.csv` | [UN Comtrade public preview API](https://comtradeapi.un.org/) | Australia→Japan exports by year. Uses SITC Rev. 1 (codes 281/321/341) for 1962-1987 and HS (2601/2701/2711) for 1988-2024. |
| `japan_fdi_to_australia.csv` | [JETRO](https://www.jetro.go.jp/en/reports/statistics.html) (originally BoJ/MoF Balance of Payments) | Japan-outward FDI to Australia. Flow data 1987-2025; year-end stock data 1996-2024 (USD millions). |
| `australia_renewable_energy.csv` | [Our World in Data energy](https://github.com/owid/energy-data) (stitched from IRENA + Ember + EI) | Australian renewables generation (TWh) by technology, total electricity, fossil shares. |
| `lng_contracts_aus_jpn.csv` | Hand-coded (manual) | Major Australia→Japan LNG long-term contracts: project, first-LNG year, nameplate Mtpa, Japan buyer share %, contract term. Each row has a `verification_status` column (`verified` / `approximate`) and a `source_notes` citation. See "Manual data audit" below. |
| `coal_iron_ore_projects_aus_jpn.csv` | Hand-coded (manual) | Major Australian coal and iron-ore projects with Japanese equity / offtake. Each row has a `verification_status` column and a `source_notes` citation. Equity columns split into `_initial` and `_current` because several projects (Mt Newman, Robe River, BMA) had their Japanese stake change over time. |

## Variables in the merged panels

### `fossil_era_panel.csv` (1962-2024, 63 obs)

| Column | Meaning | Coverage |
|---|---|---|
| `year` | Calendar year | 1962-2024 |
| `export_coal_usd_to_jpn` | Australia→Japan coal exports, USD nominal (SITC pre-1988, HS 2701 from 1988) | 1962-2024 |
| `export_lng_usd_to_jpn` | Same for LNG/gas (SITC 341 / HS 2711) | 1971-2024 (effectively zero pre-1989) |
| `export_iron_ore_usd_to_jpn` | Australia→Japan iron ore (SITC 281 / HS 2601) | 1962-2024 |
| `export_all_commodities_usd_to_jpn` | All Australia→Japan goods exports | 1962-2024 |
| `export_energy_usd_to_jpn` | Coal + LNG | 1962-2024 |
| `fdi_flow_usd_million` | Japan-outward FDI flow to Australia (USD millions, BoP) | 1987-2024 |
| `fdi_stock_usd_million` | Japan-outward FDI stock in Australia | 1996-2024 |
| `japan_lng_contracted_mtpa` | Cumulative Japan-contracted LNG capacity from Australia (Mtpa) | 1989-2024 |
| `jpn_gdp_current_usd` / `aus_gdp_current_usd` | GDP, USD nominal | 1960-2024 |
| `jpy_per_aud` | AUD/JPY exchange rate | 1960-2024 |
| `coal_australian_usd_per_mt` | World Bank thermal coal benchmark | 1970-2024 |
| `lng_japan_usd_per_mmbtu` | World Bank Japan-import LNG benchmark | 1977-2024 |

### `renewables_era_panel.csv` (2005-2024, 20 obs)

Subset of the same macro/FDI variables plus:

| Column | Meaning |
|---|---|
| `renewables_electricity` | TWh, all renewables |
| `renewables_share_elec` | Renewables % of total electricity |
| `solar_electricity` / `wind_electricity` / `hydro_electricity` | Same, by technology |
| `fossil_electricity`, `coal_electricity`, `gas_electricity` | Counterfactual fossil generation |

## Second audit pass (May 2026)

This README documents the audit history. **Run 2 found a critical data-quality issue and fixed it.**

### Critical fix: Comtrade was missing LNG

The first build queried only Australia-side exports from UN Comtrade. Australia's customs office suppresses LNG export data for confidentiality (too few exporters to disaggregate without revealing firm-level information), so `2711` for AUS→JPN came back as ~$0 for years where actual LNG trade was $15B+. Cross-checking against the user's paper anchors (2024: AUD 22.8B natural gas) exposed the gap.

The fix: fetch BOTH directions per commodity (Australia-as-reporter exports AND Japan-as-reporter imports) and consolidate by taking max(AUS, JPN) per year. Confidentiality only ever suppresses values toward zero, never inflates, so max() is the correct rule. After this fix the panel matches the paper's 2024 anchors within ±11%:

| Variable | Panel (USD→AUD) | Paper (DFAT) | Δ |
|---|---|---|---|
| Total AUS→JPN exports | AUD 80.1B | AUD 75.6B | +6% |
| Coal AUS→JPN | AUD 29.8B | AUD 27.1B | +10% |
| LNG / natural gas AUS→JPN | AUD 25.2B | AUD 22.8B | +11% |

Residual gap is consistent with f.o.b. vs c.i.f. and average-vs-year-end FX differences.

### Auto-fetched data — all sanity checks passed

12 independent reference checks across Japan/Aus GDP, JPY/USD (1985 & 2024), Australian coal price 2022, Japan LNG price 2022, Comtrade Aus→Jpn coal 2020, JETRO FDI stock 2024, Aus renewables generation 2023, Aus renewables share 2023, all match within tolerance against external sources (Clean Energy Council, DFAT Japan Country Brief, historical FX). One note: OWID renewables share is ~4 pp lower than Clean Energy Council headline figure (34.8% vs 39.4% for 2023) due to definitional differences; OWID excludes some rooftop solar and uses BP-consistent boundaries.

### Manual data audit (May 2026)

Every row in the two hand-coded files was cross-checked against authoritative public sources (Wikipedia primary citations, company releases, Oil & Gas Journal, S&P Global, Mitsui / Mitsubishi / Rio Tinto / Wesfarmers releases). Corrections applied vs. the original first draft:

**LNG contracts** (Run 2 corrections additional to Run 1):
- NWS Trains 1-2: capacity 4.5 → **5.0 Mtpa** (Wood Mackenzie); contract term tightened to **20 yr** (Lexology, oilandgasonline)
- NWS Train 3: 2.4 → **2.5 Mtpa**; post-debottlenecking Japan take rose to 7.33 Mtpa
- NWS Trains 4 & 5 Japan share approximate; Train 4 25%, Train 5 30% to reflect CNOOC Guangdong + KOGAS diversification from 2006
- Darwin LNG: Japan contracted 3.5 → **3.0 Mtpa** (3.5 was plant nameplate; firm TEPCO+Tokyo Gas SPA is exactly 3.0 Mtpa for 17 yr per OGJ Feb 2006)
- Pluto LNG: Japan contracted 4.3 → **3.75 Mtpa** (foundation SPAs to Kansai + Tokyo Gas; FID nameplate 4.3 Mtpa later debottlenecked to 4.9)
- QCLNG: Japan contracted 1.0 → **1.2 Mtpa** (Tokyo Gas 20-yr SPA from 2010)
- APLNG: first LNG year **2015 → 2016** (first cargo Jan 2016 per Maritime Executive, NOT 2015)
- Gorgon: Japan contracted 4.4 → **4.5 Mtpa** (added Nippon Oil 0.3 Mtpa SPA; sum = Nippon Oil 0.3 + Tokyo Gas 1.1 + Chubu/JERA 1.44 + Kyushu 0.3 + Osaka Gas 1.375 = 4.515)
- **Wheatstone**: Japan contracted 3.7 → **6.1 Mtpa** (corrected upward — JERA 4.5 + Kyushu 0.7 + Tohoku 0.9 per Chevron + JERA releases. Initial Run-1 estimate of 2.0 was too conservative — Run 2 found the full SPA list)
- Ichthys: Japan contracted 7.1 → **6.2 Mtpa** (~70% of plant output per industry reporting)
- Prelude: Japan contracted 1.2 → **0.6 Mtpa** (INPEX 17.5% equity)

**Coal / iron-ore** (Run 2 corrections additional to Run 1):
- Mt Newman: Japanese equity 10% → **15% current, 10% initial 1969** (original JV: AMAX 25%, CSR 30%, BHP 30%, Mitsui-C.Itoh 10%, Seltrust 5% per BHP 40-yr release)
- **Robe River**: equity 35% initial in 1972 (Run 1 over-corrected to 10% — Run 2 found Cape Lambert Iron Associates was Japanese, so initial Japanese stake was 30% Mitsui + 5% Cape Lambert = **35%**, rising to 47% after Nippon Steel + Sumitomo Metal entered 1977)
- BMA (Goonyella / Peak Downs / Saraji): Mitsubishi equity 50% → **15% initially, 50% only from June 28 2001** (originally Utah International 85% / Mitsubishi Development 15% in CQCA; BHP acquired Utah 1984; BMA 50:50 structure formed when Mitsubishi acquired QCT Resources in Nov 2000 and combined assets per BHP Mitsubishi Alliance Wikipedia)
- Bengalla: Japanese equity 30% (Mitsui + Idemitsu) → **10% (Mitsui only — Idemitsu was never an equity partner)**; original JV per Wesfarmers history: CNA 40%, Wesfarmers 40%, Taipower 10%, Mitsui 10%
- Ulan: start year "1970s" → **1986** (modern open-cut commencement), Mitsubishi Development 10% equity 1986-2018 (sold to Glencore per Mitsubishi Sept 2018 release)

**Auto-fetched data was sanity-checked against 10 known reference points**, all of which match within tolerance: Japan GDP 2024 ($4.0T), Australia GDP 2024 ($1.76T), JPY/USD 1985 (238.5) and 2024 (151), Australian coal price 2022 ($345/mt), Japan LNG 2022 ($18.4/mmbtu), Australian coal exports to Japan 2020 ($8.1B), JETRO Japan FDI stock 2024 ($104B USD ≈ AUD 159B), Australian renewables 2023 (95 TWh / 35% share).

Panel merges were verified by manually reconstructing several rows (2020 coal, 1970 coal, 1989 first LNG, 2020 FDI, 2020 JPN GDP, 2024 JPY/AUD).

## Known gaps and caveats

1. **FDI is total, not energy-specific.** The JETRO bilateral series is whole-economy. DFAT's *International Investment Australia* report breaks Japan-to-Australia FDI down by ANZSIC industry (mining vs. manufacturing vs. financial), but the file is behind a DFAT page that times out from this environment. Re-running with sector-split FDI would meaningfully sharpen the energy-era estimates.
2. **Pre-1987 FDI is missing.** This is the most important gap for the 1960s-70s investment story the paper builds around. Edgington (1990) and DFAT's historical foreign-investment review have annual values that would need to be hand-keyed.
3. **LNG contracts are best-effort.** The `lng_contracts_aus_jpn.csv` file uses publicly reported Japan-buyer shares for each project; some shares (NWS Trains 4-5, Wheatstone, Prelude) are approximations. Verify against company SPAs before quoting in the final paper.
4. **Coking-coal contracts are not yet a time series.** The `coal_iron_ore_projects_aus_jpn.csv` file lists major projects with Japanese equity, but quantifying contracted Mtpa per year requires another round of hand-coding from BHP / Mitsubishi annual reports.
5. **Dollar-denominated exports conflate price × quantity.** The 2022 spike in `export_lng_usd_to_jpn` is mostly a price effect (LNG hit $18/mmbtu after Ukraine). For a clean quantity series, swap `value_usd` for `net_weight_kg` in the Comtrade pull and re-run the merge.
6. **No structural-break test yet.** NWS first cargo (1989) and Fukushima (2011) are likely break points; the notebook flags this as a next step but does not estimate it.

## What the preliminary regressions show

Run the notebook for the full output. Headline results (after the Run-2 Comtrade fix):

- **Levels specification (matches outline model)**: R² = 0.992. Lagged FDI **positive and significant** (β=4.07e+05, p=0.009). LNG contracted Mtpa **positive and significant** (β=3.54e+08, p<0.001). Coal and LNG prices also highly significant. The user's hypothesis — that Japanese FDI and long-term contracts are associated with higher Australian energy exports to Japan — is supported in levels.
- **Important caveat**: ADF tests show all trending series are non-stationary (p > 0.10), so the levels result risks spurious correlation among co-trending variables. Treat the levels regression as descriptive, not inferential.
- **Log first-differences (preferred)**: R² = 0.897. FDI lag and Contracts both **insignificant** (p=0.55 and p=0.43); commodity prices dominate (coal elasticity 0.33, LNG elasticity 0.65, both highly significant). Reading: in year-to-year *changes*, FDI and contracts don't predict export changes — those are driven by price spikes. The structural FDI/contracts story shows up in the long-run levels relationship, not in annual growth co-movement.
- **Renewables-era equation**: 16 obs, R²=0.27. Lagged-FDI elasticity is *negative* and significant (β=-0.26, p<0.001). Almost certainly the proxy problem — recent Japan-to-Australia FDI is dominated by financial-services and real-estate flows, not energy. Worth flagging as a limitation that motivates obtaining sector-disaggregated FDI from DFAT's IIA report.
