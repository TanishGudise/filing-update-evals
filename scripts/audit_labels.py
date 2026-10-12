"""Audit the generic row labels (S1 standard, S3 abbreviated) against each filer's own statement
labels. Offline. Writes outputs/labels.md and fails if a qualifier is unreviewed.

A filer label is flagged when it carries a qualifier that decides which reported figure belongs in
the row: something excluded or included, a narrower or combined line, gross against net interest,
or units. Each flag must be either carried into the generic labels (styles._qualify) or reviewed
below as making no difference to the figure (the statement has a single row it can come from).

Usage: scripts/guarded .venv/bin/python -I scripts/audit_labels.py
"""

from __future__ import annotations

from filing_update_evals.netguard import install

install()  # offline: loopback only, even when run with python -I

import json
import re
import sys
import tomllib
from pathlib import Path

from filing_update_evals import model as M
from filing_update_evals import styles as S

REPO = Path(__file__).resolve().parent.parent

QUALIFIER = re.compile(
    r"exclu|includ|and after-tax|and equity in|consolidated operations|amortizable|indefinite"
    r"|short-term borrowings and|interest income|thousand|million|per share",
    re.I,
)

AFTER_TAX = "One pre-tax line; {} income comes after tax, in the model's other after-tax items."
SIGN = 'Net interest income, held as a negative "Interest expense, net" by the sign convention.'
REVIEWED = {
    ("ROL", "cogs"): "One cost line; D&A is its own line, kept in the model's other operating expenses.",
    ("GIS", "pretax_income"): AFTER_TAX.format("joint-venture"),
    ("BBY", "pretax_income"): AFTER_TAX.format("affiliates'"),
    ("MKC", "pretax_income"): AFTER_TAX.format("unconsolidated operations'"),
    ("MKC", "capex"): "One capital expenditure line, which includes software.",
    ("ROST", "interest_expense"): SIGN,
    ("WSM", "interest_expense"): SIGN,
    ("HD", "long_term_debt"): 'Same meaning: "Long-term debt" sits next to its own current-portion row.',
}


def section(line: str) -> str | None:
    if line in M.IS_TYPED:
        return "is"
    if line in M.BS_TYPED:
        return "bs"
    if line in M.YTD_LINES:
        return "ytd"
    return None


def main() -> int:
    tickers = tomllib.loads((REPO / "data" / "filers.toml").read_text())["selected"]
    tickers += tomllib.loads((REPO / "data" / "hardset.toml").read_text())["tickers"]
    generic = S._labels("S1", {"labels": {}})
    out = [
        "# Row labels: filer vs generic",
        "",
        "Every typed row's label on the filer's statement next to the generic labels the S1 (standard) "
        "and S3 (abbreviated) workbooks use; S2 uses the filer's label. A flagged qualifier is either "
        "carried into the generic labels for that filer or reviewed as making no difference to the "
        "figure.",
        "",
        "| filer | row | filer's label | S1 label | S3 label | qualifier |",
        "|---|---|---|---|---|---|",
    ]
    unreviewed = []
    carried = reviewed = 0
    for ticker in tickers:
        data = json.loads((REPO / "data" / "filers" / f"{ticker}.json").read_text())
        s1, s3 = S._labels("S1", data), S._labels("S3", data)
        for line, label in data["labels"].items():
            sec = section(line)
            if not label or not sec:
                continue
            flagged = bool(QUALIFIER.search(label))
            net_gap = line == "interest_expense" and (
                bool(re.search(r"\bnet\b", label, re.I)) != bool(re.search(r"\bnet\b", s1[sec][line], re.I))
            )
            note = ""
            if s1[sec][line] != generic[sec][line]:
                note = "carried"
                carried += 1
            elif flagged or net_gap:
                if (ticker, line) in REVIEWED:
                    note = "reviewed: " + REVIEWED[(ticker, line)]
                    reviewed += 1
                else:
                    note = "UNREVIEWED"
                    unreviewed.append(f"{ticker} {line}: {label}")
            out.append(f"| {ticker} | {sec}.{line} | {label} | {s1[sec][line]} | {s3[sec][line]} | {note} |")
    out += [
        "",
        f"{carried} qualifiers carried into the generic labels, {reviewed} reviewed as making no "
        f"difference, {len(unreviewed)} unreviewed.",
    ]
    (REPO / "outputs" / "labels.md").write_text("\n".join(out) + "\n")
    print(out[-1])
    for item in unreviewed:
        print(f"  unreviewed: {item}")
    return 1 if unreviewed else 0


if __name__ == "__main__":
    sys.exit(main())
