"""Parse FIRB Annual Report PDFs to extract Japan-by-sector approval values.

Each year's report uses a slightly different layout/encoding for the
country-by-industry-sector table. We handle each PDF individually and
output a single tidy CSV.

Output: data/raw/firb/japan_firb_approvals_by_sector.csv
  Columns: fy, n_approvals, agri_aud_m, finance_aud_m, manufacturing_elec_gas_aud_m,
           mineral_exp_dev_aud_m, real_estate_aud_m, services_aud_m, total_aud_m,
           source_pdf, table_ref
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
import pdfplumber
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
FIRB_DIR = REPO / "data" / "raw" / "firb"


def revstr(s: str) -> str:
    return s[::-1]


def num(s: str) -> float | None:
    if not s or s in ("-", ""):
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ----------------------------------------------------------------------------
# Per-PDF extractors
# ----------------------------------------------------------------------------

def parse_2019_20() -> dict:
    """2019-20: table is in normal orientation, Japan row found via text scan."""
    pdf_path = FIRB_DIR / "firb_2019-20.pdf"
    with pdfplumber.open(pdf_path) as p:
        for pg in p.pages:
            text = pg.extract_text() or ""
            if "Table 3.17" in text and "JAPAN" in text:
                # Find JAPAN row
                for line in text.split("\n"):
                    if line.startswith("JAPAN"):
                        # JAPAN 129 197.8 1,334.0 17,487.9 226.7 1,059.9 1,774.9 22,081.1
                        toks = line.split()
                        return {
                            "fy": "2019-20",
                            "n_approvals": int(toks[1]),
                            "agri_aud_m": num(toks[2]),
                            "finance_aud_m": num(toks[3]),
                            "manufacturing_elec_gas_aud_m": num(toks[4]),
                            "mineral_exp_dev_aud_m": num(toks[5]),
                            "real_estate_aud_m": num(toks[6]),
                            "services_aud_m": num(toks[7]),
                            "total_aud_m": num(toks[8]),
                            "source_pdf": pdf_path.name,
                            "table_ref": "Table 3.17",
                        }
    raise RuntimeError("Could not find JAPAN row in 2019-20 PDF")


def parse_2018_19() -> dict:
    """2018-19: table is transposed AND each cell is character-reversed.

    Approach: pull the Japan column by index from each data row. Country
    header row tells us Japan sits at column index 8.
    """
    pdf_path = FIRB_DIR / "firb_2018-19.pdf"
    with pdfplumber.open(pdf_path) as p:
        pg = p.pages[47]
        tables = pg.extract_tables()
    t = tables[0]
    # Find the country header row and Japan column index
    jp_col = None
    for row in t:
        if any(cell and "NAPAJ" in str(cell) for cell in row):
            for j, cell in enumerate(row):
                if cell and "NAPAJ" in str(cell):
                    jp_col = j
                    break
            break
    if jp_col is None:
        raise RuntimeError("Japan column not found in 2018-19")

    # Each sector has a label-row then a data row containing '$m' marker.
    # Walk through, tracking pending label.
    label_keys = [
        ("total_aud_m",                       "latoT"),
        ("services_aud_m",                    "secivreS"),
        ("real_estate_aud_m",                 "laeR"),
        ("mineral_exp_dev_aud_m",             "lareniM"),
        ("manufacturing_elec_gas_aud_m",      ",gnirutcafunaM"),
        ("finance_aud_m",                     "ecnaniF"),
        ("agri_aud_m",                        ",erutlucirgA"),
        ("n_approvals",                       "fo slavorppa"),  # 'Number of approvals'
    ]
    result = {"fy": "2018-19", "source_pdf": pdf_path.name, "table_ref": "Table 3.14"}
    pending_field = None
    for row in t:
        row_text = " ".join(str(c) for c in row if c)
        is_data_row = any(c and ("$m" in str(c) or "m$" in str(c)) for c in row)
        if is_data_row:
            if pending_field:
                cell = row[jp_col] if jp_col < len(row) else None
                if cell:
                    val_rev = revstr(str(cell))
                    if pending_field == "n_approvals":
                        try:
                            result[pending_field] = int(val_rev.replace(",", ""))
                        except ValueError:
                            result[pending_field] = None
                    else:
                        result[pending_field] = num(val_rev)
                pending_field = None
            continue
        # Label row: pick the most-specific matching label
        for field, key in label_keys:
            if key in row_text:
                pending_field = field
                break

    # The Number-of-approvals row doesn't have a $m marker — handle separately
    for i, row in enumerate(t):
        row_text = " ".join(str(c) for c in row if c)
        if "fo slavorppa" in row_text or "rebmuN" in row_text:
            # Look for the next row with numeric data at jp_col
            for nxt in t[i+1:i+4]:
                if nxt and jp_col < len(nxt):
                    cell = nxt[jp_col]
                    if cell:
                        rev = revstr(str(cell)).replace(",", "")
                        if rev.isdigit():
                            result["n_approvals"] = int(rev)
                            break
            break
    return result


def parse_2020_21() -> dict:
    """2020-21: country×sector table in mostly-normal orientation."""
    pdf_path = FIRB_DIR / "firb_2020-21.pdf"
    with pdfplumber.open(pdf_path) as p:
        for pi, pg in enumerate(p.pages):
            text = pg.extract_text() or ""
            if "Japan" in text and "Singapore" in text and "Real" in text:
                tables = pg.extract_tables()
                for ti, t in enumerate(tables):
                    # Find a row whose first non-empty cell starts with a country rank+name (e.g., "2 Japan")
                    for row in t:
                        joined = " ".join(str(c) for c in row if c)
                        if "Japan" in joined and any(
                            (c and re.match(r"^\d", str(c).strip())) for c in row
                        ):
                            # Find tokens — country may be combined with rank
                            # Try to extract a "Japan" data row by re-splitting the joined text
                            line = joined
                            # Pattern: <rank> Japan <approvals> <agri> <finance> <manu> <mineral> <re> <services> <total>
                            m = re.match(
                                r"\s*\d+\s+Japan\s+(\d+(?:,\d+)?)\s+([\d,.\-]+)\s+([\d,.\-]+)\s+([\d,.\-]+)\s+([\d,.\-]+)\s+([\d,.\-]+)\s+([\d,.\-]+)\s+([\d,.\-]+)",
                                line,
                            )
                            if m:
                                vals = m.groups()
                                return {
                                    "fy": "2020-21",
                                    "n_approvals": int(vals[0].replace(",", "")),
                                    "agri_aud_m": num(vals[1]),
                                    "finance_aud_m": num(vals[2]),
                                    "manufacturing_elec_gas_aud_m": num(vals[3]),
                                    "mineral_exp_dev_aud_m": num(vals[4]),
                                    "real_estate_aud_m": num(vals[5]),
                                    "services_aud_m": num(vals[6]),
                                    "total_aud_m": num(vals[7]),
                                    "source_pdf": pdf_path.name,
                                    "table_ref": "Table 3.17",
                                }
    raise RuntimeError("Could not parse 2020-21 PDF")


def parse_2017_18() -> dict:
    """2017-18: cleanly readable Japan row in Chapter 3, Table 3.14."""
    pdf_path = FIRB_DIR / "firb_2017-18_05-chap3.pdf"
    with pdfplumber.open(pdf_path) as p:
        for pg in p.pages:
            text = pg.extract_text() or ""
            if "Table 3.14" in text and "Japan" in text:
                for line in text.split("\n"):
                    if line.startswith("Japan"):
                        toks = line.split()
                        # 'Japan 136 192.6 26.1 109.8 525.8 2 ,205.5 1 ,635.2 4,695.1'
                        # Some thousand-separators got split — re-join
                        rejoined = re.sub(r"(\d+) ,(\d{3})", r"\1,\2", line)
                        toks = rejoined.split()
                        return {
                            "fy": "2017-18",
                            "n_approvals": int(toks[1]),
                            "agri_aud_m": num(toks[2]),
                            "finance_aud_m": num(toks[3]),
                            "manufacturing_elec_gas_aud_m": num(toks[4]),
                            "mineral_exp_dev_aud_m": num(toks[5]),
                            "real_estate_aud_m": num(toks[6]),
                            "services_aud_m": num(toks[7]),
                            "total_aud_m": num(toks[8]),
                            "source_pdf": pdf_path.name,
                            "table_ref": "Table 3.14",
                        }
    raise RuntimeError("2017-18 Japan row not found")


def parse_2016_17() -> dict:
    """2016-17: Table 4.13, clean text. Note: includes Tourism column."""
    pdf_path = FIRB_DIR / "firb_2016-17.pdf"
    with pdfplumber.open(pdf_path) as p:
        for pg in p.pages:
            text = pg.extract_text() or ""
            if "Table 4.13" in text and "Japan" in text:
                for line in text.split("\n"):
                    if line.startswith("Japan"):
                        rejoined = re.sub(r"(\d+) ,(\d{3})", r"\1,\2", line)
                        toks = rejoined.split()
                        # 'Japan 113 12.2 0.0 1,150.3 109.5 3,199.6 937.5 0.0 5,409.1'
                        # Approvals, agri, finance, manu/elec/gas, mineral, RE, services, tourism, total
                        return {
                            "fy": "2016-17",
                            "n_approvals": int(toks[1]),
                            "agri_aud_m": num(toks[2]),
                            "finance_aud_m": num(toks[3]),
                            "manufacturing_elec_gas_aud_m": num(toks[4]),
                            "mineral_exp_dev_aud_m": num(toks[5]),
                            "real_estate_aud_m": num(toks[6]),
                            "services_aud_m": num(toks[7]),
                            # toks[8] is tourism (0.0 for Japan), we skip
                            "total_aud_m": num(toks[9]),
                            "source_pdf": pdf_path.name,
                            "table_ref": "Table 4.13",
                        }
    raise RuntimeError("2016-17 Japan row not found")


def parse_2014_15() -> dict:
    """2014-15: hand-coded — PDF parsing yields split numbers that are hard
    to reassemble programmatically. Values from Table 2.12 page 35 of the
    2014-15 chapter 2 PDF, cross-checked against the row total.
    Original row: '4 Japan 152 - 17 135 766 774 6,965 - 8,658'
    Columns: rank, country, approvals, agri, finance, manu, mineral, RE,
             services, tourism, total.
    NOTE: this year uses 'Manufacturing' (not manu+elec+gas) and has a
    separate 'Tourism' column.
    """
    return {
        "fy": "2014-15",
        "n_approvals": 152,
        "agri_aud_m": 0.0,                       # '-'
        "finance_aud_m": 17.0,
        "manufacturing_elec_gas_aud_m": 135.0,   # 'Manufacturing' only this year
        "mineral_exp_dev_aud_m": 766.0,
        "real_estate_aud_m": 774.0,
        "services_aud_m": 6965.0,
        "total_aud_m": 8658.0,                   # tourism = 0 for Japan
        "source_pdf": "firb_2014-15_chap2.pdf",
        "table_ref": "Table 2.12 (hand-coded)",
    }


def main() -> None:
    rows = []
    for parser in (parse_2014_15, parse_2016_17, parse_2017_18,
                   parse_2018_19, parse_2019_20, parse_2020_21):
        try:
            rows.append(parser())
            print(f"OK: {parser.__name__}")
        except Exception as e:
            print(f"FAIL {parser.__name__}: {type(e).__name__}: {e}")

    df = pd.DataFrame(rows)
    cols = [
        "fy", "n_approvals",
        "agri_aud_m", "finance_aud_m", "manufacturing_elec_gas_aud_m",
        "mineral_exp_dev_aud_m", "real_estate_aud_m", "services_aud_m",
        "total_aud_m", "source_pdf", "table_ref",
    ]
    df = df[cols].sort_values("fy").reset_index(drop=True)
    out = FIRB_DIR / "japan_firb_approvals_by_sector.csv"
    df.to_csv(out, index=False)
    print(f"\nWrote {out}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
