"""Mapping XBRL company facts to model lines, on a synthetic filer with calendar quarters."""

from __future__ import annotations

import datetime as dt

from filing_update_evals.xbrl import CompanyFacts, find_calendar, map_lines

D = dt.date
TARGET = "0000000001-26-000020"

# (key, start, end, accession, form, filed) for every period the synthetic filings report.
PERIODS = {
    "FY-2": (D(2024, 1, 1), D(2024, 12, 31)),
    "FY-1Q1": (D(2025, 1, 1), D(2025, 3, 31)),
    "FY-1Q2": (D(2025, 4, 1), D(2025, 6, 30)),
    "FY-1Q3": (D(2025, 7, 1), D(2025, 9, 30)),
    "FY-1Q2YTD": (D(2025, 1, 1), D(2025, 6, 30)),
    "FY-1Q3YTD": (D(2025, 1, 1), D(2025, 9, 30)),
    "FY-1": (D(2025, 1, 1), D(2025, 12, 31)),
    "FYQ1": (D(2026, 1, 1), D(2026, 3, 31)),
    "FYQ2": (D(2026, 4, 1), D(2026, 6, 30)),
    "FYQ2YTD": (D(2026, 1, 1), D(2026, 6, 30)),
    "FY-1END": (None, D(2025, 12, 31)),
    "FYQ1END": (None, D(2026, 3, 31)),
    "FYQ2END": (None, D(2026, 6, 30)),
}
FILING = {  # which filing first reports each period
    "FY-1Q1": ("0000000001-25-000005", "10-Q", D(2025, 4, 30)),
    "FY-1Q2": ("0000000001-25-000010", "10-Q", D(2025, 7, 30)),
    "FY-1Q2YTD": ("0000000001-25-000010", "10-Q", D(2025, 7, 30)),
    "FY-1Q3": ("0000000001-25-000015", "10-Q", D(2025, 10, 30)),
    "FY-1Q3YTD": ("0000000001-25-000015", "10-Q", D(2025, 10, 30)),
    "FY-2": ("0000000001-26-000002", "10-K", D(2026, 2, 15)),
    "FY-1": ("0000000001-26-000002", "10-K", D(2026, 2, 15)),
    "FY-1END": ("0000000001-26-000002", "10-K", D(2026, 2, 15)),
    "FYQ1": ("0000000001-26-000010", "10-Q", D(2026, 4, 30)),
    "FYQ1END": ("0000000001-26-000010", "10-Q", D(2026, 4, 30)),
    "FYQ2": (TARGET, "10-Q", D(2026, 7, 30)),
    "FYQ2YTD": (TARGET, "10-Q", D(2026, 7, 30)),
    "FYQ2END": (TARGET, "10-Q", D(2026, 7, 30)),
}
DURATION = ["FY-2", "FY-1Q1", "FY-1Q2", "FY-1Q3", "FY-1Q3YTD", "FY-1", "FYQ1", "FYQ2", "FYQ2YTD"]
YTD = ["FY-1Q1", "FY-1Q2YTD", "FY-1Q3YTD", "FY-1", "FYQ1", "FYQ2YTD"]
INSTANT = ["FY-1END", "FYQ1END", "FYQ2END"]

BASE = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": (DURATION, 1000),
    "CostOfGoodsAndServicesSold": (DURATION, 600),
    "SellingGeneralAndAdministrativeExpense": (DURATION, 200),
    "OperatingIncomeLoss": (DURATION, 200),
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": (
        DURATION,
        190,
    ),
    "IncomeTaxExpenseBenefit": (DURATION, 40),
    "NetIncomeLoss": (DURATION, 150),
    "DepreciationDepletionAndAmortization": (YTD, 30),
    "NetCashProvidedByUsedInOperatingActivities": (YTD, 180),
    "PaymentsToAcquirePropertyPlantAndEquipment": (YTD, 50),
    "NetCashProvidedByUsedInInvestingActivities": (YTD, -50),
    "NetCashProvidedByUsedInFinancingActivities": (YTD, -100),
    "CashAndCashEquivalentsAtCarryingValue": (INSTANT, 300),
    "AccountsReceivableNetCurrent": (INSTANT, 150),
    "AssetsCurrent": (INSTANT, 600),
    "Assets": (INSTANT, 2000),
    "LiabilitiesCurrent": (INSTANT, 400),
    "LongTermDebtNoncurrent": (INSTANT, 500),
    "StockholdersEquity": (INSTANT, 1000),
    "LiabilitiesAndStockholdersEquity": (INSTANT, 2000),
}


def _scale(key: str) -> float:
    if key in ("FY-2", "FY-1"):
        return 4.0
    if key.endswith("Q2YTD"):
        return 2.0
    if key.endswith("Q3YTD"):
        return 3.0
    return 1.0


def facts(overrides=None, extra=()):
    """Company facts in data.sec.gov's shape. overrides: concept -> (keys, value) or None."""
    spec = dict(BASE) | (overrides or {})
    us_gaap = {}
    for concept, entry in spec.items():
        if entry is None:
            continue
        keys, value = entry
        rows = []
        for key in keys:
            start, end = PERIODS[key]
            accn, form, filed = FILING[key]
            row = {
                "end": end.isoformat(),
                "val": value * _scale(key),
                "accn": accn,
                "form": form,
                "filed": filed.isoformat(),
            }
            if start:
                row["start"] = start.isoformat()
            rows.append(row)
        us_gaap[concept] = {"units": {"USD": rows}}
    for concept, row in extra:
        us_gaap.setdefault(concept, {"units": {"USD": []}})["units"]["USD"].append(row)
    shares = {
        "units": {
            "shares": [
                {"end": "2026-07-20", "val": 100, "accn": TARGET, "form": "10-Q", "filed": "2026-07-30"}
            ]
        }
    }
    return CompanyFacts(
        {
            "cik": 1,
            "entityName": "Synthetic",
            "facts": {"us-gaap": us_gaap, "dei": {"EntityCommonStockSharesOutstanding": shares}},
        }
    )


def mapped(cf):
    cal = find_calendar(cf, TARGET, D(2026, 6, 30))
    return cal, *map_lines(cf, cal, D(2026, 7, 30))


def test_calendar_and_clean_mapping():
    cal, lines, problems, notes = mapped(facts())
    assert cal.k == 2 and cal.fy_start == D(2026, 1, 1) and cal.prev_quarter_ends[-1] == D(2025, 12, 31)
    assert not problems and not notes
    assert lines["revenue"].values["FYQ2"] == 1000 and lines["revenue"].values["FY-1Q3YTD"] == 3000
    assert lines["inventory"].concept == "" and set(lines["inventory"].values.values()) == {0.0}


def test_taxonomy_rename_is_stitched():
    old = [k for k in DURATION if k.startswith(("FY-1", "FY-2"))]
    new = [k for k in DURATION if k.startswith("FYQ")]
    _, lines, problems, notes = mapped(
        facts({"InterestExpense": (old, 10), "InterestExpenseNonoperating": (new, 12)})
    )
    assert not problems and not notes
    assert lines["interest_expense"].concept == "InterestExpense | InterestExpenseNonoperating"
    assert lines["interest_expense"].values["FY-1Q1"] == 10 and lines["interest_expense"].values["FYQ2"] == 12


def test_net_interest_retag_is_stitched_only_where_the_tags_agree():
    old = [k for k in DURATION if k.startswith(("FY-1", "FY-2"))]
    new = [k for k in DURATION if k.startswith("FYQ") or k == "FY-1Q1"]
    # Both tag FY-1Q1 (the new filing's comparative column) with the same value: stitched.
    _, lines, problems, notes = mapped(
        facts({"InterestExpense": (old, 10), "InterestIncomeExpenseNonoperatingNet": (new, -10)})
    )
    assert not problems and not notes
    assert lines["interest_expense"].concept == "-InterestIncomeExpenseNonoperatingNet | InterestExpense"
    _, same, _, _ = mapped(facts({"InterestExpense": (DURATION, 10)}))
    assert lines["interest_expense"].values == same["interest_expense"].values
    # They disagree on FY-1Q1: not the same line, so it is folded.
    _, lines, _, notes = mapped(
        facts({"InterestExpense": (old, 10), "InterestIncomeExpenseNonoperatingNet": (new, -12)})
    )
    assert lines["interest_expense"].folded and any("interest_expense folded" in n for n in notes)
    # They never tag the same period: nothing shows they are the same line, so it is folded.
    only_new = [k for k in DURATION if k.startswith("FYQ")]
    _, lines, _, notes = mapped(
        facts({"InterestExpense": (old, 10), "InterestIncomeExpenseNonoperatingNet": (only_new, -25)})
    )
    assert lines["interest_expense"].folded and any("interest_expense folded" in n for n in notes)


def test_other_concept_mixes_are_folded_not_stitched():
    old = [k for k in DURATION if k.startswith(("FY-1", "FY-2"))]
    new = [k for k in DURATION if k.startswith("FYQ")]
    _, lines, problems, notes = mapped(
        facts({"InterestExpense": (old, 10), "InterestIncomeExpenseNet": (new, -12)})
    )
    assert not problems
    assert lines["interest_expense"].concept == "" and any("interest_expense folded" in n for n in notes)
    # Folded: 0 in every period, but what each period reports is kept (for accepted readings).
    folded = lines["interest_expense"]
    assert folded.folded and set(folded.values.values()) == {0.0}
    assert folded.reported["FYQ2"] == ["-InterestIncomeExpenseNet", 12.0, TARGET]
    assert folded.reported["FY-1Q1"][:2] == ["InterestExpense", 10.0]
    assert not lines["revenue"].folded and not lines["revenue"].reported


def test_net_interest_is_sign_flipped():
    _, lines, _, _ = mapped(facts({"InterestIncomeExpenseNonoperatingNet": (DURATION, -10)}))
    assert lines["interest_expense"].values["FYQ2"] == 10


def test_restated_required_line_fails_but_proxy_statements_are_ignored():
    start, end = PERIODS["FY-1Q2"]
    restated = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "val": 999,
        "accn": TARGET,
        "form": "10-Q",
        "filed": "2026-07-30",
    }
    proxy = dict(restated, form="DEF 14A", accn="0000000001-26-000007", filed="2026-04-01")
    _, _, problems, _ = mapped(facts(extra=[("NetIncomeLoss", proxy)]))
    assert not problems
    _, _, problems, _ = mapped(facts(extra=[("NetIncomeLoss", restated)]))
    assert any("net_income" in p and "restated" in p for p in problems)


def test_untagged_balance_is_zero_only_with_evidence():
    # The Q1 10-Q tags inventory in its comparative column (prior year end) but not at its own
    # quarter end: the line is on that balance sheet, blank this quarter, so it is 0.
    comparative = {
        "end": "2025-12-31",
        "val": 80,
        "accn": "0000000001-26-000010",
        "form": "10-Q",
        "filed": "2026-04-30",
    }
    _, lines, problems, notes = mapped(
        facts({"InventoryNet": (["FY-1END", "FYQ2END"], 80)}, extra=[("InventoryNet", comparative)])
    )
    assert not problems and not notes
    assert lines["inventory"].values == {"FY-1END": 80, "FYQ1END": 0.0, "FYQ2END": 80}
    # Without that evidence the filer may have re-tagged the line: it is folded, not zeroed.
    _, lines, problems, notes = mapped(facts({"InventoryNet": (["FY-1END", "FYQ2END"], 80)}))
    assert not problems and lines["inventory"].concept == "" and any("inventory folded" in n for n in notes)


def test_missing_flows_are_never_zero():
    _, _, problems, _ = mapped(facts({"NetIncomeLoss": ([k for k in DURATION if k != "FY-1Q2"], 150)}))
    assert any(p.startswith("net_income") for p in problems)


def test_debt_lines_are_never_folded():
    _, _, problems, _ = mapped(facts({"LongTermDebtNoncurrent": (["FY-1END", "FYQ2END"], 500)}))
    assert any(p.startswith("long_term_debt") for p in problems)


def test_debt_current_absorbs_short_term_borrowings():
    _, lines, _, notes = mapped(facts({"DebtCurrent": (INSTANT, 70), "ShortTermBorrowings": (INSTANT, 20)}))
    assert lines["current_ltd"].concept == "DebtCurrent"
    assert set(lines["short_term_debt"].values.values()) == {0.0}
    assert any("short_term_debt dropped" in n for n in notes)


def test_long_term_debt_current_is_not_debt_current():
    # "LongTermDebtCurrent" contains the text "DebtCurrent" but is only the current portion of
    # long-term debt: short-term borrowings stay their own line.
    _, lines, _, notes = mapped(
        facts({"LongTermDebtCurrent": (INSTANT, 70), "ShortTermBorrowings": (INSTANT, 20)})
    )
    assert lines["current_ltd"].concept == "LongTermDebtCurrent"
    assert set(lines["short_term_debt"].values.values()) == {20}
    assert not notes
