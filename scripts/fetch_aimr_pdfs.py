"""Fetch Geoscience Australia AIMR (Australia's Identified Mineral Resources)
PDFs for 2001-2010. These are narrative documents that mention mine names with
Mtpa capacity figures. Useful for cross-validating capacity claims, but NOT for
clean annual mine-level production tables.

URL patterns (verified by search 2026-05):
  - AIMR 2001 = ga.gov.au/pdf/RR0019.pdf
  - AIMR 2002 = ga.gov.au/pdf/RR0112.pdf
  - AIMR 2006 = ga.gov.au/bigobj/GA8870.pdf
  - AIMR 2008 = ga.gov.au/bigobj/GA12116.pdf
  - AIMR 2009 = ga.gov.au/bigobj/GA16013.pdf

For unverified years (2003-2005, 2007, 2010+) the GA numbering does not follow
a predictable pattern — they must be found manually from
https://www.ga.gov.au/scientific-topics/minerals/aimr

Output: data/raw/aimr/AIMR_<year>.pdf
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "raw" / "aimr"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Verified direct URLs (others will need manual lookup; see geonetwork catalog)
AIMR_URLS = {
    2001: "https://www.ga.gov.au/pdf/RR0019.pdf",
    2002: "https://www.ga.gov.au/pdf/RR0112.pdf",
    2006: "https://www.ga.gov.au/bigobj/GA8870.pdf",
    2008: "https://www.ga.gov.au/bigobj/GA12116.pdf",
    2009: "https://www.ga.gov.au/bigobj/GA16013.pdf",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def fetch_one(year: int, url: str) -> Path | None:
    out = OUT_DIR / f"AIMR_{year}.pdf"
    if out.exists() and out.stat().st_size > 100_000:
        print(f"  {year}: cached ({out.stat().st_size:,} bytes)")
        return out
    print(f"  {year}: downloading from {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=120)
    except requests.RequestException as e:
        print(f"    failed: {e}")
        return None
    if r.status_code != 200 or len(r.content) < 50_000:
        print(f"    HTTP {r.status_code}, {len(r.content)} bytes — skipping")
        return None
    out.write_bytes(r.content)
    print(f"    saved {len(r.content):,} bytes -> {out}")
    return out


def main() -> None:
    for year, url in sorted(AIMR_URLS.items()):
        fetch_one(year, url)
        time.sleep(1)
    print(f"\nDone. {len(list(OUT_DIR.glob('*.pdf')))} PDFs in {OUT_DIR}.")
    print("\nMANUAL HAND-CODING NOTE:")
    print("AIMR PDFs contain narrative text with mine names and Mtpa figures,")
    print("but NOT clean annual production tables. Use the BHP, Rio Tinto, BMA")
    print("Annual Reports for project-level production: search 'project_production_annual.csv'.")


if __name__ == "__main__":
    sys.exit(main())
