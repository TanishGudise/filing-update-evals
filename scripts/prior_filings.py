"""Filer data for the firm-memory experiment's worked examples when the task is a first-quarter
update: there is no earlier 10-Q in the same fiscal year, so the example is the update for the
filer's most recent earlier 10-Q, the previous fiscal year's third quarter. (The same quarter a
year earlier would change the same cells with the same formulas as the task's answer.) Offline
except for the downloads, which go through scripts/fetch.py (SEC only).

  python -I scripts/prior_filings.py urls      print the SEC files still to download (the filing
                                               index first, then its statement pages)
  python -I scripts/prior_filings.py prepare   write data/prior/<ticker>.json with prepare()

Each filing is the latest 10-Q before the task's, found in the filer's SEC submissions file; its
"prior" filing (for the share count) is the periodic filing before it.
"""

from __future__ import annotations

from filing_update_evals.netguard import install

install()  # offline: loopback only, even when run with python -I

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/pages.py, scripts/prepare.py
from pages import base_url, local, reports_for
from prepare import prepare

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "raw"
TICKERS = ("GIS", "MLKN", "SJM")


def year_earlier(row: dict) -> dict:
    """The screen row for the latest 10-Q before the task's (the previous year's third quarter)."""
    target_end = dt.date.fromisoformat(row["target"]["period_end"])
    sub = json.loads((RAW / "data.sec.gov/submissions" / f"CIK{row['cik']:010d}.json").read_text())
    recent = sub["filings"]["recent"]
    filings = sorted(
        (recent["reportDate"][i], recent["form"][i], recent["accessionNumber"][i], recent["filingDate"][i])
        for i in range(len(recent["form"]))
        if recent["form"][i] in ("10-Q", "10-K")
    )
    target = max(f for f in filings if f[1] == "10-Q" and dt.date.fromisoformat(f[0]) < target_end)
    prior = max(f for f in filings if f[0] < target[0])
    return {
        "ticker": row["ticker"],
        "cik": row["cik"],
        "name": row["name"],
        "fiscal_year_end": row["fiscal_year_end"],
        "public": target[3],
        "target": {
            "accession": target[2],
            "filed": target[3],
            "period_end": target[0],
            "prior_accession": prior[2],
            "prior_form": prior[1],
        },
    }


def rows() -> list[dict]:
    screen = {r["ticker"]: r for r in json.loads((REPO / "data" / "screen.json").read_text())}
    return [year_earlier(screen[t]) for t in TICKERS]


def urls() -> int:
    for r in rows():
        summary = base_url(r) + "/FilingSummary.xml"
        if not local(summary).exists():
            print(summary)
            continue
        for file in reports_for(r).values():
            if not local(f"{base_url(r)}/{file}").exists():
                print(f"{base_url(r)}/{file}")
    return 0


def prepare_all() -> int:
    out = REPO / "data" / "prior"
    out.mkdir(parents=True, exist_ok=True)
    for r in rows():
        r["pages"] = reports_for(r)
        data = prepare(r)
        (out / f"{r['ticker']}.json").write_text(json.dumps(data, indent=1) + "\n")
        print(
            f"{r['ticker']}: Q{data['quarter']} FY{data['fy']} 10-Q {r['target']['accession']} -> {out.name}/"
        )
    return 0


if __name__ == "__main__":
    sys.exit({"urls": urls, "prepare": prepare_all}[sys.argv[1]]())
