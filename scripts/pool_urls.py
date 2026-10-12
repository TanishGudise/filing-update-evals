"""Resolve the candidate pool (data/pool.toml) to CIKs and print the SEC URLs the screen needs:
each filer's filing list (submissions) and its XBRL company facts. Offline; reads the
downloaded ticker map. Writes data/pool_ciks.json.

Usage: scripts/guarded .venv/bin/python -I scripts/pool_urls.py > raw-urls.txt
"""

import json
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    tickers = tomllib.loads((REPO / "data" / "pool.toml").read_text())["tickers"]
    table = json.loads((REPO / "raw" / "www.sec.gov" / "files" / "company_tickers.json").read_text())
    by_ticker = {row["ticker"].upper(): row for row in table.values()}
    out, missing = {}, []
    for ticker in tickers:
        row = by_ticker.get(ticker.upper())
        if row is None:
            missing.append(ticker)
            continue
        out[ticker] = {"cik": int(row["cik_str"]), "name": row["title"]}
    (REPO / "data" / "pool_ciks.json").write_text(json.dumps(out, indent=1) + "\n")
    for info in out.values():
        cik10 = f"{info['cik']:010d}"
        print(f"https://data.sec.gov/submissions/CIK{cik10}.json")
        print(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json")
    if missing:
        print("missing tickers: " + ", ".join(missing), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
