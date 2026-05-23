"""Scrape JBIC press releases for Japan-Australia project finance deals.

Source: https://www.jbic.go.jp/en/information/press/resources.html
The index page lists all JBIC press releases by year. We extract every Australia-
related release, then visit each one to extract: date, project name, loan amount,
JBIC share, co-lenders, and a one-line description.

This is the "debt-financing channel" data the paper's hypothesis turns on. Each
record is a Japanese-backed debt facility for an Australian energy/resource
project — the mechanism by which Japan's long-term offtake commitments
translate into actual project bankability.

Output:
- data/raw/jbic/jbic_australia_press.csv  (one row per press release)
- data/raw/jbic/jbic_australia_press_text/  (one .txt per release, for citation/audit)
"""
from __future__ import annotations

from pathlib import Path
import sys
import re
import time
import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "jbic"
TXT_DIR = RAW_DIR / "press_text"
RAW_DIR.mkdir(parents=True, exist_ok=True)
TXT_DIR.mkdir(parents=True, exist_ok=True)

INDEX_URL = "https://www.jbic.go.jp/en/information/press/resources.html"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}


def get_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def parse_index(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/press/press-" not in href:
            continue
        title = " ".join(a.get_text(separator=" ", strip=True).split())
        if "Australia" not in title:
            continue
        url = ("https://www.jbic.go.jp" + href) if href.startswith("/") else href
        items.append({"url": url, "title": title})
    return items


# Loan-amount patterns commonly used in JBIC releases. Two forms:
#   "USD 1.0 billion" / "approximately USD 1 billion" / "JPY 30 billion" / "AUD 200 m"
#   "5 billion U.S. dollars" / "1.0 billion U.S." / "30 billion Japanese yen"
AMOUNT_RE = re.compile(
    r"(approximately\s+)?(up to\s+)?"
    r"(USD|US\$|JPY|AUD|EUR)\s*"
    r"([0-9][0-9,]*\.?[0-9]*)\s*"
    r"(million|billion|m|bn|b)\b",
    re.IGNORECASE,
)
AMOUNT_TRAIL_RE = re.compile(
    r"(approximately\s+)?(up to\s+)?"
    r"([0-9][0-9,]*\.?[0-9]*)\s*"
    r"(million|billion)\s+"
    r"(U\.S\.\s*(?:dollars?)?|US\s*dollars?|Japanese\s+yen|Australian\s+dollars?|Yen)",
    re.IGNORECASE,
)

DATE_RE = re.compile(r"(January|February|March|April|May|June|July|August|"
                     r"September|October|November|December)\s+\d{1,2},\s+\d{4}")


def parse_release(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    # Get just the main body text (skip nav/footer)
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    # Date
    m = DATE_RE.search(text)
    date = m.group(0) if m else ""

    # First few loan amount mentions (prefixed-currency form: "USD 1.0 billion")
    amts = []
    for m in AMOUNT_RE.finditer(text[:4000]):
        sign = (m.group(1) or "").strip() + " " + (m.group(2) or "").strip()
        sign = sign.strip()
        currency = m.group(3).upper().replace("$", "D")
        amount = m.group(4).replace(",", "")
        unit = m.group(5).lower()
        amts.append(f"{sign + ' ' if sign else ''}{currency} {amount} {unit}".strip())
    # Trailing-currency form: "5 billion U.S. dollars"
    for m in AMOUNT_TRAIL_RE.finditer(text[:4000]):
        sign = (m.group(1) or "").strip() + " " + (m.group(2) or "").strip()
        sign = sign.strip()
        amount = m.group(3).replace(",", "")
        unit = m.group(4).lower()
        cur_raw = m.group(5).lower()
        if "yen" in cur_raw:
            currency = "JPY"
        elif "australian" in cur_raw:
            currency = "AUD"
        else:
            currency = "USD"
        amts.append(f"{sign + ' ' if sign else ''}{currency} {amount} {unit}".strip())
    amounts = " | ".join(amts[:8])

    # Headline = first <h1> or <h2>
    h = soup.find(["h1", "h2"])
    headline = h.get_text(" ", strip=True) if h else ""

    return {
        "date": date,
        "headline": headline,
        "loan_amounts_mentioned": amounts,
        "body_excerpt": text[:1500],
    }


def main() -> None:
    print(f"Fetching index from {INDEX_URL}")
    idx_html = get_html(INDEX_URL)
    items = parse_index(idx_html)
    print(f"Found {len(items)} Australia-related press releases\n")

    out_rows = []
    for i, item in enumerate(items, 1):
        slug = re.sub(r"[^\w.-]", "_", item["url"].rsplit("/", 1)[-1])
        txt_path = TXT_DIR / f"{slug}.txt"
        try:
            if txt_path.exists():
                html = txt_path.read_text()
            else:
                html = get_html(item["url"])
                txt_path.write_text(html)
                time.sleep(0.5)  # polite
        except Exception as e:
            print(f"  [{i}/{len(items)}] FAIL: {item['url']} -- {e}")
            continue
        parsed = parse_release(html)
        out_rows.append({
            "title": item["title"],
            "url": item["url"],
            "date": parsed["date"],
            "headline": parsed["headline"],
            "loan_amounts_mentioned": parsed["loan_amounts_mentioned"],
            "body_excerpt": parsed["body_excerpt"],
        })
        print(f"  [{i}/{len(items)}] {parsed['date']:20s}  {item['title'][:80]}")
        print(f"         amounts: {parsed['loan_amounts_mentioned']}")

    import pandas as pd
    df = pd.DataFrame(out_rows)
    out_path = RAW_DIR / "jbic_australia_press.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path} ({len(df)} rows)")


if __name__ == "__main__":
    sys.exit(main())
