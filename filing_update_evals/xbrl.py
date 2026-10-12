"""Read SEC XBRL company facts and map them to the model's lines.

Ground truth for the generated tasks comes from the facts each filer tagged in its own filings
(data.sec.gov/api/xbrl/companyfacts). Every model line has an ordered list of candidate
concepts; a filer's line uses the first candidate that has a value for every period the model
needs. A line no candidate covers at all is absent (0); a line covered only for some periods
fails the screen, because the filer changed how it tags that line.

Periods: the target 10-Q's quarter is quarter k of fiscal year FY. The model needs the 3-month
income statement for every quarter of FY-1 and quarters 1..k of FY (Q4 of FY-1 is the full year
minus nine months), FY-1 and FY-2 full years, year-to-date cash flows for quarters 1..k of FY,
and balance sheets at the end of FY-1 and of quarters 1..k of FY.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

# line -> (period type, candidates, required). A candidate is a concept or a tuple summed; a
# leading "-" on a concept negates it.
LINES: dict[str, tuple[str, tuple[str | tuple[str, ...], ...], bool]] = {
    # income statement (3-month and annual durations)
    "revenue": (
        "duration",
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueGoodsNet",
        ),
        True,
    ),
    "cogs": (
        "duration",
        (
            "CostOfGoodsAndServicesSold",
            "CostOfRevenue",
            "CostOfGoodsSold",
            "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
            "CostOfServices",
        ),
        False,
    ),
    "sga": ("duration", ("SellingGeneralAndAdministrativeExpense",), False),
    "operating_income": ("duration", ("OperatingIncomeLoss",), True),
    "interest_expense": (
        "duration",
        (
            "InterestExpense",
            "InterestExpenseNonoperating",
            "InterestExpenseDebt",
            # "Interest expense, net" on the face of the statement is often tagged as net
            # interest income; a leading "-" flips the sign.
            "-InterestIncomeExpenseNonoperatingNet",
            "-InterestIncomeExpenseNet",
        ),
        False,
    ),
    "pretax_income": (
        "duration",
        (
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
        True,
    ),
    "income_tax": ("duration", ("IncomeTaxExpenseBenefit",), True),
    "net_income": ("duration", ("NetIncomeLoss",), True),
    # cash flow statement (year-to-date durations)
    "da": (
        "ytd",
        (
            "DepreciationDepletionAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
            "DepreciationAndAmortization",
            ("Depreciation", "AmortizationOfIntangibleAssets"),
        ),
        True,
    ),
    "cfo": (
        "ytd",
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        True,
    ),
    "capex": (
        "ytd",
        ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
        True,
    ),
    "cfi": (
        "ytd",
        (
            "NetCashProvidedByUsedInInvestingActivities",
            "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
        ),
        True,
    ),
    "cff": (
        "ytd",
        (
            "NetCashProvidedByUsedInFinancingActivities",
            "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
        ),
        True,
    ),
    # balance sheet (instants)
    "cash": (
        "instant",
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        True,
    ),
    "receivables": (
        "instant",
        (
            "AccountsReceivableNetCurrent",
            "ReceivablesNetCurrent",
            "AccountsNotesAndLoansReceivableNetCurrent",
        ),
        False,
    ),
    "inventory": ("instant", ("InventoryNet", "RetailRelatedInventoryMerchandise"), False),
    "current_assets": ("instant", ("AssetsCurrent",), True),
    "ppe": (
        "instant",
        (
            "PropertyPlantAndEquipmentNet",
            "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        ),
        False,
    ),
    "goodwill": ("instant", ("Goodwill",), False),
    "intangibles": (
        "instant",
        ("IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"),
        False,
    ),
    "total_assets": ("instant", ("Assets",), True),
    "payables": ("instant", ("AccountsPayableCurrent", "AccountsPayableTradeCurrent"), False),
    "short_term_debt": (
        "instant",
        (
            "ShortTermBorrowings",
            "CommercialPaper",
            "LinesOfCreditCurrent",
            "ShortTermBankLoansAndNotesPayable",
        ),
        False,
    ),
    "current_ltd": (
        "instant",
        ("LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent", "DebtCurrent"),
        False,
    ),
    "current_liabilities": ("instant", ("LiabilitiesCurrent",), True),
    "long_term_debt": (
        "instant",
        ("LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermLineOfCredit"),
        False,
    ),
    "equity": (
        "instant",
        ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        True,
    ),
    "redeemable_nci": (
        "instant",
        (
            "RedeemableNoncontrollingInterestEquityCarryingAmount",
            "RedeemableNoncontrollingInterestEquityFairValue",
            "RedeemableNoncontrollingInterestEquityCommonCarryingAmount",
        ),
        False,
    ),
    "nci": ("instant", ("MinorityInterest",), False),
    "total_liabilities_equity": ("instant", ("LiabilitiesAndStockholdersEquity",), True),
}


PERIODIC_FORMS = frozenset({"10-Q", "10-K", "10-Q/A", "10-K/A"})


@dataclass(frozen=True)
class Fact:
    concept: str
    start: dt.date | None
    end: dt.date
    val: float
    accn: str
    form: str
    filed: dt.date
    fp: str
    fy: int | None = None


def _d(text: str | None) -> dt.date | None:
    return dt.date.fromisoformat(text) if text else None


def days(start: dt.date, end: dt.date) -> int:
    return (end - start).days


def is_quarter(start: dt.date, end: dt.date) -> bool:
    return 80 <= days(start, end) <= 100


def is_year(start: dt.date, end: dt.date) -> bool:
    return 350 <= days(start, end) <= 380


class CompanyFacts:
    def __init__(self, data: dict):
        self.cik = int(data["cik"])
        self.name = data["entityName"]
        self.facts: dict[str, list[Fact]] = {}
        for taxonomy in ("us-gaap", "dei"):
            for concept, body in data["facts"].get(taxonomy, {}).items():
                units = body.get("units", {})
                rows = units.get("USD") or units.get("shares") or []
                self.facts[concept] = [
                    Fact(
                        concept,
                        _d(r.get("start")),
                        _d(r["end"]),
                        r["val"],
                        r["accn"],
                        r["form"],
                        _d(r["filed"]),
                        r.get("fp", ""),
                        r.get("fy"),
                    )
                    for r in rows
                ]

        ends: dict[str, dt.date] = {}
        for concept, rows in self.facts.items():
            if concept in ("EntityCommonStockSharesOutstanding", "EntityPublicFloat"):
                continue
            for f in rows:
                if f.form in PERIODIC_FORMS and (f.accn not in ends or f.end > ends[f.accn]):
                    ends[f.accn] = f.end
        self.period_end = ends
        """Accession -> the period end the filing reports (its latest balance sheet date)."""

    def home_filings(self, end: dt.date) -> list[str]:
        """The periodic filings whose own period ends on `end`."""
        return [accn for accn, e in self.period_end.items() if e == end]

    @classmethod
    def load(cls, path: Path) -> CompanyFacts:
        return cls(json.loads(path.read_text()))

    def reported(
        self, concept: str, start: dt.date | None, end: dt.date, up_to: dt.date | None = None
    ) -> list[Fact]:
        """Every 10-Q/10-K value for one period (start None = instant), filed on or before up_to.
        Other forms are ignored: proxy statements re-tag net income in their pay-versus-
        performance tables, sometimes with different rounding."""
        return [
            f
            for f in self.facts.get(concept, [])
            if f.end == end
            and f.start == start
            and f.form in PERIODIC_FORMS
            and (up_to is None or f.filed <= up_to)
        ]

    def in_filing(self, concept: str, accn: str) -> list[Fact]:
        return [f for f in self.facts.get(concept, []) if f.accn == accn]


@dataclass
class Period:
    key: str
    """e.g. "FY-1Q2" (3-month), "FY-1" (annual), "FYQ2YTD", "FY-1END" (instant), "FYQ2END"."""
    start: dt.date | None
    end: dt.date
    kind: str  # "quarter" | "year" | "ytd" | "instant"


@dataclass
class Calendar:
    """Fiscal periods around the target 10-Q."""

    fy_start: dt.date
    k: int
    quarter_ends: list[dt.date]  # FY quarter ends 1..k
    prev_start: dt.date
    prev_quarter_ends: list[dt.date]  # FY-1 quarter ends 1..4 (4 = FY-1 end)
    prev2_start: dt.date


@dataclass
class LineValue:
    concept: str
    """The concepts used, joined with " | " (a sum of concepts is joined with "+"); "" if absent."""
    values: dict[str, float] = field(default_factory=dict)  # period key -> value
    by_period: dict[str, str] = field(default_factory=dict)  # period key -> concept used
    sources: dict[str, str] = field(default_factory=dict)  # period key -> accession of the value


class ScreenError(Exception):
    pass


def find_calendar(cf: CompanyFacts, accn: str, period_end: dt.date) -> Calendar:
    """Work out FY start, quarter index and quarter-end dates from the revenue facts."""
    durations = []
    for concept in LINES["revenue"][1]:
        assert isinstance(concept, str)
        durations += [f for f in cf.in_filing(concept, accn) if f.start and f.end == period_end]
        if durations:
            break
    if not durations:
        raise ScreenError("no revenue facts for the target quarter")
    fy_start = min(f.start for f in durations if f.start)
    span = days(fy_start, period_end)
    k = round((span + 1) / 91.3)
    if not 1 <= k <= 3:
        raise ScreenError(f"target is not quarter 1-3 (span {span} days)")

    # FY-1: an annual duration ending the day before fy_start (52/53-week years end exactly then).
    annual = [
        f
        for concept in LINES["revenue"][1]
        if isinstance(concept, str)
        for f in cf.facts.get(concept, [])
        if f.start and is_year(f.start, f.end) and 0 < days(f.end, fy_start) <= 7
    ]
    if not annual:
        raise ScreenError("no prior fiscal-year revenue")
    prev_end = max(f.end for f in annual)
    prev_start = min(f.start for f in annual if f.end == prev_end and f.start)
    annual2 = [
        f
        for concept in LINES["revenue"][1]
        if isinstance(concept, str)
        for f in cf.facts.get(concept, [])
        if f.start and is_year(f.start, f.end) and 0 < days(f.end, prev_start) <= 7
    ]
    if not annual2:
        raise ScreenError("no fiscal-year revenue two years back")
    prev2_start = min(f.start for f in annual2 if f.start)

    def quarter_ends(start: dt.date, last_end: dt.date, count: int) -> list[dt.date]:
        ends = sorted(
            {
                f.end
                for concept in LINES["revenue"][1]
                if isinstance(concept, str)
                for f in cf.facts.get(concept, [])
                if f.start and is_quarter(f.start, f.end) and start <= f.start and f.end <= last_end
            }
        )
        return ends[:count]

    q_ends = quarter_ends(fy_start, period_end, k)
    p_ends = quarter_ends(prev_start, prev_end, 3) + [prev_end]
    if len(q_ends) != k or q_ends[-1] != period_end:
        raise ScreenError("can't find every quarter of the current fiscal year")
    if len(p_ends) != 4:
        raise ScreenError("can't find every quarter of the prior fiscal year")
    return Calendar(fy_start, k, q_ends, prev_start, p_ends, prev2_start)


def periods(cal: Calendar) -> list[Period]:
    """Every period any line needs. Keys: FY-1Q1..Q3 (3 months), FY-1 and FY-2 (years),
    FY-1Q2YTD / FY-1Q3YTD, FYQ1..FYQk (3 months), FYQ1YTD..FYQkYTD, FY-1END and FYQ1END..FYQkEND."""
    out: list[Period] = []
    starts = [cal.prev_start] + [e + dt.timedelta(days=1) for e in cal.prev_quarter_ends[:3]]
    for i in range(3):
        out.append(Period(f"FY-1Q{i + 1}", starts[i], cal.prev_quarter_ends[i], "quarter"))
    out.append(Period("FY-1", cal.prev_start, cal.prev_quarter_ends[3], "year"))
    out.append(Period("FY-2", cal.prev2_start, cal.prev_start - dt.timedelta(days=1), "year"))
    out.append(Period("FY-1Q2YTD", cal.prev_start, cal.prev_quarter_ends[1], "ytd"))
    out.append(Period("FY-1Q3YTD", cal.prev_start, cal.prev_quarter_ends[2], "ytd"))
    out.append(Period("FY-1END", None, cal.prev_quarter_ends[3], "instant"))
    q_starts = [cal.fy_start] + [e + dt.timedelta(days=1) for e in cal.quarter_ends[:-1]]
    for i, end in enumerate(cal.quarter_ends):
        out.append(Period(f"FYQ{i + 1}", q_starts[i], end, "quarter"))
        out.append(Period(f"FYQ{i + 1}YTD", cal.fy_start, end, "ytd"))
        out.append(Period(f"FYQ{i + 1}END", None, end, "instant"))
    return out


def needed(line: str, ps: list[Period]) -> list[Period]:
    kind = LINES[line][0]
    by_key = {p.key: p for p in ps}
    if kind == "instant":
        return [p for p in ps if p.kind == "instant"]
    if kind == "ytd":
        keys = [p.key for p in ps if p.key.startswith("FYQ") and p.key.endswith("YTD")] + ["FY-1"]
        if line == "da":  # D&A by quarter for EBITDA, in both years
            keys += ["FY-1Q1", "FY-1Q2YTD", "FY-1Q3YTD"]
        return [by_key[k] for k in keys]
    keys = ["FY-1Q1", "FY-1Q2", "FY-1Q3", "FY-1", "FY-1Q3YTD"]
    keys += [p.key for p in ps if p.kind == "quarter" and p.key.startswith("FYQ")]
    if line == "revenue":  # prior-year growth sets the forecast driver
        keys.append("FY-2")
    return [by_key[k] for k in keys]


def _value(
    cf: CompanyFacts, candidate: str | tuple[str, ...], p: Period, up_to: dt.date
) -> tuple[float | None, set]:
    parts = (candidate,) if isinstance(candidate, str) else candidate
    total, distinct = 0.0, set()
    for part in parts:
        sign, concept = (-1, part[1:]) if part.startswith("-") else (1, part)
        facts = cf.reported(concept, p.start, p.end, up_to)
        if not facts:
            # Q4 of FY-1 is never tagged as 3 months; it is derived later.
            return None, set()
        vals = {f.val for f in facts}
        distinct |= {(concept, v) for v in vals}
        total += sign * sorted(facts, key=lambda f: f.filed)[-1].val
        if len(vals) > 1:
            distinct.add(("recast", concept))
    return total, distinct


def _source(cf: CompanyFacts, name: str, p: Period, up_to: dt.date) -> str:
    """Accession number of the filing the value was read from (the latest one reporting it)."""
    accns = []
    for part in name.split("+"):
        facts = cf.reported(part.lstrip("-"), p.start, p.end, up_to)
        if facts:
            accns.append(sorted(facts, key=lambda f: f.filed)[-1].accn)
    return "+".join(dict.fromkeys(accns))


DEBT_LINES = ("short_term_debt", "current_ltd", "long_term_debt", "redeemable_nci", "nci")
"""Optional, but never folded: the equity bridge needs every debt and non-controlling-interest
line. A filer that tags none of them at all has a zero line; scripts/pages.py then checks the
balance sheet shows no such row with a number."""

RENAMES = (frozenset({"InterestExpense", "InterestExpenseNonoperating"}),)
"""Concepts a filer may switch between from one year to the next (a US GAAP taxonomy rename).
Any other mix of concepts within one line would change what the line means across periods."""


def _name(candidate: str | tuple[str, ...]) -> str:
    return candidate if isinstance(candidate, str) else "+".join(candidate)


def map_lines(
    cf: CompanyFacts, cal: Calendar, target_filed: dt.date, overrides: dict[str, list[str]] | None = None
) -> tuple[dict[str, LineValue], list[str], list[str]]:
    """Read each line's value for every period it needs. Returns (lines, problems, notes).

    A line uses the first candidate concept that has a value for every period, or else a pair of
    concepts related by a taxonomy rename (RENAMES), one per period. A value reported
    differently by two periodic filings is a restatement. An optional balance sheet line with
    no value on some dates is 0 on those dates (filers often leave a zero balance untagged). An
    optional line that is still incomplete, or restated, is folded into the model's derived
    "other" line instead of dropping the filer; a required line in that state fails it.

    `overrides` (the hand-built set only) replaces a line's candidates with concepts a person
    checked against the filer's statements; those may be stitched across periods."""
    ps = periods(cal)
    out: dict[str, LineValue] = {}
    problems: list[str] = []
    notes: list[str] = []
    for line, (kind, candidates, required) in LINES.items():
        groups = RENAMES
        if overrides and line in overrides:
            candidates = tuple(overrides[line])
            groups = (frozenset(candidates),)
        want = needed(line, ps)
        table: dict[str, dict[str, tuple[float, bool]]] = {}
        for candidate in candidates:
            row = {}
            for p in want:
                value, distinct = _value(cf, candidate, p, target_filed)
                if value is not None:
                    row[p.key] = (value, any(d[0] == "recast" for d in distinct))
            if row:
                table[_name(candidate)] = row

        chosen: dict[str, str] = {}
        for name, row in table.items():  # candidate order
            if len(row) == len(want):
                chosen = {p.key: name for p in want}
                break
        if not chosen:
            for group in groups:
                names = [n for n in table if n in group]
                stitched = {p.key: next((n for n in names if p.key in table[n]), None) for p in want}
                if names and all(stitched.values()):
                    chosen = {k: v for k, v in stitched.items() if v}
                    break
        if not chosen and kind == "instant" and table:
            # A balance the filer leaves untagged on some dates is 0 there only with evidence: the
            # filing for that date still tags the line on another date (its comparative column),
            # so the line is on that statement, just blank; or the line was 0 on every date it
            # was tagged. (scripts/pages.py also checks the target date shows no number.)
            # Otherwise the filer may have re-tagged the line, and that's no zero.
            name = max(table, key=lambda n: len(table[n]))
            by_key = {p.key: p for p in want}

            def blank_on_statement(key: str, name: str = name, by_key: dict = by_key) -> bool:
                p = by_key[key]
                homes = set(cf.home_filings(p.end))
                return any(
                    f.accn in homes and f.end != p.end and f.start is None
                    for f in cf.facts.get(name.lstrip("-"), [])
                )

            missing = [p.key for p in want if p.key not in table[name]]
            always_zero = all(value == 0 for value, _ in table[name].values())
            if always_zero or all(blank_on_statement(key) for key in missing):
                chosen = {p.key: name if p.key in table[name] else "(untagged: 0)" for p in want}

        if not chosen:
            if not table and not required:
                out[line] = LineValue("", {p.key: 0.0 for p in want})
                continue
            if required or line in DEBT_LINES:
                problems.append(
                    f"{line}: no concept covers every period" if table else f"{line}: no concept found"
                )
                continue
            notes.append(f"{line} folded into other (no single concept covers every period)")
            out[line] = LineValue("", {p.key: 0.0 for p in want})
            continue

        values = {k: (table[n][k][0] if n in table else 0.0) for k, n in chosen.items()}
        restated = any(table[n][k][1] for k, n in chosen.items() if n in table)
        if restated:
            if required or line in DEBT_LINES:
                problems.append(f"{line}: a value was restated between filings")
                continue
            notes.append(f"{line} folded into other (restated between filings)")
            out[line] = LineValue("", {p.key: 0.0 for p in want})
            continue
        by_key = {p.key: p for p in want}
        sources = {k: _source(cf, n, by_key[k], target_filed) for k, n in chosen.items() if n in table}
        out[line] = LineValue(" | ".join(sorted(set(chosen.values()))), values, chosen, sources)
    # DebtCurrent is all current debt: short-term borrowings are part of it, not a second line.
    if "DebtCurrent" in out.get("current_ltd", LineValue("")).by_period.values() and "short_term_debt" in out:
        if out["short_term_debt"].concept:
            notes.append("short_term_debt dropped: DebtCurrent already includes it")
        out["short_term_debt"] = LineValue("", {key: 0.0 for key in out["short_term_debt"].values})
    return out, problems, notes
