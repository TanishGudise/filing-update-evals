"""The logical model: a three-statement model plus an unlevered DCF, written once for every
filer and every workbook style.

Columns (logical): P1-P4 and PY are the prior fiscal year's quarters and full year; C1-C4 and CY
the current fiscal year's; F1-F4 four forecast years. `last` is the last reported quarter of the
current year: quarters up to it are actuals, later ones are estimates. The task workbook is the
model with `last = k - 1`; the reference answer is the model with `last = k`, built from the same
filings plus the new 10-Q. Everything that differs between the two is the update.

Actual columns hold the filing's numbers, typed, and the filing's own totals: the "other" lines
are formulas (e.g. other current assets = total current assets - the mapped lines), so actual
columns tie exactly to the filing, rounding included. Estimate columns are driver formulas, and
the balance sheet balances in every one of them. Fourth quarters are never reported: P4 is the
full year minus the first three quarters. Cash flows in a 10-Q are year to date; the quarters
are differences of the typed year-to-date figures.

Cells hold a number (a typed actual or input, in dollars or as a ratio), text, or a formula
template with placeholders that each style turns into cell references:
  {line@col}           same section       {is.revenue@C2}     another section
  {is.revenue@C1:C4}   a range            {inp.wacc}          an input
"""

from __future__ import annotations

from dataclasses import dataclass, field

P = ("P1", "P2", "P3", "P4")
C = ("C1", "C2", "C3", "C4")
F = ("F1", "F2", "F3", "F4")
COLUMNS = (*P, "PY", *C, "CY", *F)
BS_COLUMNS = ("PY", *C, *F)
CF_COLUMNS = ("PY", *C, "CY", *F)
QUARTER_DAYS = 91.25
YEAR_DAYS = 365

IS_LINES = (
    "revenue",
    "cogs",
    "gross_profit",
    "sga",
    "other_opex",
    "operating_income",
    "interest_expense",
    "other_nonop",
    "pretax_income",
    "income_tax",
    "other_after_tax",
    "net_income",
    "da",
    "ebitda",
)
IS_TYPED = (
    "revenue",
    "cogs",
    "sga",
    "operating_income",
    "interest_expense",
    "pretax_income",
    "income_tax",
    "net_income",
)
BS_LINES = (
    "cash",
    "receivables",
    "inventory",
    "other_current_assets",
    "current_assets",
    "ppe",
    "goodwill",
    "intangibles",
    "other_noncurrent_assets",
    "total_assets",
    "payables",
    "short_term_debt",
    "current_ltd",
    "other_current_liabilities",
    "current_liabilities",
    "long_term_debt",
    "other_noncurrent_liabilities",
    "total_liabilities",
    "redeemable_nci",
    "equity",
    "nci",
    "total_equity",
    "total_liabilities_equity",
    "check",
)
BS_TYPED = (
    "cash",
    "receivables",
    "inventory",
    "current_assets",
    "ppe",
    "goodwill",
    "intangibles",
    "total_assets",
    "payables",
    "short_term_debt",
    "current_ltd",
    "current_liabilities",
    "long_term_debt",
    "redeemable_nci",
    "equity",
    "nci",
    "total_liabilities_equity",
)
CF_LINES = (
    "net_income",
    "da",
    "wc_other",
    "cfo",
    "capex",
    "other_investing",
    "cfi",
    "cff",
    "fx_other",
    "net_change",
    "begin_cash",
    "end_cash",
    "fcf",
)
YTD_LINES = ("cfo", "capex", "cfi", "cff", "da")
VAL_Q_LINES = ("quarter", "ebit", "tax_on_ebit", "nopat", "da", "capex", "wc", "ufcf")
VAL_LINES = (
    "ltm_revenue",
    "ltm_ebitda",
    "stub_years",
    "stub_ufcf",
    "stub_discount",
    "pv_stub",
    "period",
    "discount",
    "pv",
    "terminal_value",
    "pv_terminal",
    "enterprise_value",
    "cash",
    "short_term_debt",
    "current_ltd",
    "long_term_debt",
    "net_debt",
    "nci",
    "equity_value",
    "shares",
    "per_share",
    "ev_ltm_ebitda",
)
INPUTS = (
    "last_q",
    "shares",
    "growth_fy",
    "growth",  # per forecast year (F1-F4)
    "gross_margin",
    "sga_pct",
    "other_opex_pct",
    "da_pct",
    "capex_pct",
    "tax_rate",
    "dso",
    "dio",
    "dpo",
    "payout",
    "interest",
    "other_nonop_q",
    "other_after_tax_q",
    "other_investing_q",
    "fx_other_q",
    "wacc",
    "terminal_growth",
)
PLUG_INPUTS = ("q4_gross_margin",)
"""Analyst overrides that only the plug-carrying style has. They are hardcodes an update must
leave alone."""

AMOUNT = "usd"
RATIO = "ratio"
SHARES = "shares"
COUNT = "count"


@dataclass(frozen=True)
class Formula:
    template: str


@dataclass
class Cell:
    content: float | str | Formula
    unit: str = AMOUNT
    source: dict | None = None
    """For a typed number from a filing: concept, accession, period (key, start, end) and sign
    (-1 where the model types the negative of the tagged value, e.g. capex as an outflow)."""


@dataclass
class Logical:
    cells: dict[tuple[str, str, str], Cell] = field(default_factory=dict)
    """(section, line, column) -> cell. Scalars use column "V"."""
    last: int = 0
    plugs: bool = False

    def set(
        self, section: str, line: str, col: str, content, unit: str = AMOUNT, source: dict | None = None
    ) -> None:
        self.cells[(section, line, col)] = Cell(content, unit, source)


def is_actual(col: str, last: int) -> bool:
    if col in (*P[:3], "PY"):
        return True
    if col in C:
        return int(col[1]) <= last
    return False


def prev_quarter(col: str) -> str:
    """The column whose balance sheet a column's flows start from."""
    if col == "C1":
        return "PY"
    if col in C:
        return f"C{int(col[1]) - 1}"
    if col == "F1":
        return "C4"
    if col in F:
        return f"F{int(col[1]) - 1}"
    raise ValueError(col)


def days(col: str) -> float:
    return QUARTER_DAYS if col in C else YEAR_DAYS


# Period keys used by data/filers/<T>.json (scripts/prepare.py)
IS_KEY = {
    "P1": "FY-1Q1",
    "P2": "FY-1Q2",
    "P3": "FY-1Q3",
    "PY": "FY-1",
    **{f"C{j}": f"FYQ{j}" for j in range(1, 5)},
}
YTD_KEY = {
    "P1": "FY-1Q1",
    "P2": "FY-1Q2YTD",
    "P3": "FY-1Q3YTD",
    "PY": "FY-1",
    **{f"C{j}": f"FYQ{j}YTD" for j in range(1, 5)},
}
BS_KEY = {"PY": "FY-1END", **{f"C{j}": f"FYQ{j}END" for j in range(1, 5)}}


def drivers(data: dict) -> dict[str, float]:
    """Forecast drivers, set from the prior fiscal year the way an analyst would normalize it,
    and rounded like typed inputs. Margins and expense ratios are the median of the year's four
    quarters, so one quarter with a large charge doesn't set them; the tax rate is the year's
    effective rate held to 15-30% (24% if pre-tax income wasn't positive); the payout ratio is
    capped at 100% (50% if net income wasn't positive). They are inputs: an update never changes
    them."""
    import statistics

    v = {line: body["values"] for line, body in data["lines"].items()}
    quarters = ("FY-1Q1", "FY-1Q2", "FY-1Q3", "Q4")

    def q(line: str, key: str) -> float:
        if key != "Q4":
            return v[line][key]
        return v[line]["FY-1"] - v[line]["FY-1Q1"] - v[line]["FY-1Q2"] - v[line]["FY-1Q3"]

    def median_ratio(fn) -> float:
        values = [fn(key) / q("revenue", key) for key in quarters if q("revenue", key)]
        return round(statistics.median(values), 4) if values else 0.0

    rev = v["revenue"]["FY-1"]
    cogs = v["cogs"]["FY-1"]
    pretax, tax, ni = v["pretax_income"]["FY-1"], v["income_tax"]["FY-1"], v["net_income"]["FY-1"]
    prior = v["revenue"]["FY-2"]
    out = {
        "growth_fy": round(rev / prior - 1, 3) if prior else 0.0,
        "gross_margin": median_ratio(lambda k: q("revenue", k) - q("cogs", k)),
        "sga_pct": median_ratio(lambda k: q("sga", k)),
        "other_opex_pct": median_ratio(
            lambda k: q("revenue", k) - q("cogs", k) - q("sga", k) - q("operating_income", k)
        ),
        "da_pct": round(v["da"]["FY-1"] / rev, 4),
        "capex_pct": round(v["capex"]["FY-1"] / rev, 4),
        "tax_rate": round(min(0.30, max(0.15, tax / pretax)), 3) if pretax > 0 else 0.24,
        "dso": round(v["receivables"]["FY-1END"] / rev * YEAR_DAYS, 1),
        "dio": round(v["inventory"]["FY-1END"] / cogs * YEAR_DAYS, 1) if cogs else 0.0,
        "dpo": round(v["payables"]["FY-1END"] / cogs * YEAR_DAYS, 1) if cogs else 0.0,
        "payout": round(min(1.0, max(0.0, -v["cff"]["FY-1"] / ni)), 2) if ni > 0 else 0.5,
        "interest": float(v["interest_expense"]["FY-1"]),
        "wacc": 0.09,
        "terminal_growth": 0.025,
    }
    return out


def build(data: dict, last: int, plugs: bool = False) -> Logical:
    """The model as of `last` reported quarters of the current fiscal year."""
    m = Logical(last=last, plugs=plugs)
    v = {line: body["values"] for line, body in data["lines"].items()}
    src = {line: body for line, body in data["lines"].items()}

    def typed(
        section: str, line: str, col: str, key: str, value: float, unit: str = AMOUNT, sign: int = 1
    ) -> None:
        body = src[line]
        start, end = data["periods"][key]
        source = {
            "concept": body["by_period"].get(key, body["concept"]) or "",
            "accession": body["sources"].get(key, ""),
            "period": key,
            "start": start,
            "end": end,
            "sign": sign,
        }
        m.set(section, line, col, float(value), unit, source)

    # Inputs ------------------------------------------------------------------------------
    d = drivers(data)
    m.set("inp", "last_q", "V", float(last), COUNT)
    shares = data["shares"]["current" if last == data["quarter"] else "prior"]
    m.set(
        "inp",
        "shares",
        "V",
        float(shares["value"]),
        SHARES,
        {
            "concept": "dei:EntityCommonStockSharesOutstanding",
            "accession": shares["accession"],
            "period": "cover",
            "start": None,
            "end": shares["as_of"],
            "sign": 1,
            **({"classes": shares["classes"]} if "classes" in shares else {}),
        },
    )
    for name in (
        "growth_fy",
        "gross_margin",
        "sga_pct",
        "other_opex_pct",
        "da_pct",
        "capex_pct",
        "tax_rate",
        "payout",
        "wacc",
        "terminal_growth",
    ):
        m.set("inp", name, "V", d[name], RATIO)
    for name in ("dso", "dio", "dpo"):
        m.set("inp", name, "V", d[name], COUNT)
    m.set("inp", "interest", "V", d["interest"])
    for name in ("other_nonop_q", "other_after_tax_q", "other_investing_q", "fx_other_q"):
        m.set("inp", name, "V", 0.0)
    for i, col in enumerate(F):
        m.set("inp", "growth", col, round(max(d["growth_fy"] * (1 - 0.15 * i), 0.02), 3), RATIO)
    if plugs:
        m.set("inp", "q4_gross_margin", "V", round(d["gross_margin"] + 0.005, 4), RATIO)

    # Year-to-date block (cash flow statement as reported) -----------------------------------
    for col in (*P[:3], "PY", *C):
        if col in C and int(col[1]) > last:
            continue
        key = YTD_KEY[col]
        typed("ytd", "da", col, key, v["da"][key])
        if col in ("PY", *C):
            typed("ytd", "cfo", col, key, v["cfo"][key])
            typed(
                "ytd", "capex", col, key, -v["capex"][key], sign=-1
            )  # an outflow, as the statement shows it
            typed("ytd", "cfi", col, key, v["cfi"][key])
            typed("ytd", "cff", col, key, v["cff"][key])

    def ytd_quarter(line: str, col: str) -> Formula:
        """A quarter's cash flow from the year-to-date figures."""
        if col in ("P1", "C1", "PY"):
            return Formula(f"{{ytd.{line}@{col}}}")
        if col == "P4":
            return Formula(f"{{ytd.{line}@PY}}-{{ytd.{line}@P3}}")
        prev = f"{col[0]}{int(col[1]) - 1}"
        return Formula(f"{{ytd.{line}@{col}}}-{{ytd.{line}@{prev}}}")

    # Income statement ------------------------------------------------------------------------
    for col in COLUMNS:
        actual = is_actual(col, last)
        if actual:
            for line in IS_TYPED:
                typed("is", line, col, IS_KEY[col], v[line][IS_KEY[col]])
        elif col == "P4":
            for line in IS_TYPED:
                m.set("is", line, col, Formula(f"{{{line}@PY}}-{{{line}@P1}}-{{{line}@P2}}-{{{line}@P3}}"))
        elif col == "CY":
            for line in IS_TYPED:
                m.set("is", line, col, Formula(f"SUM({{{line}@C1:C4}})"))
        else:  # estimate quarter or forecast year
            if col in C:
                m.set("is", "revenue", col, Formula(f"{{revenue@P{col[1]}}}*(1+{{inp.growth_fy}})"))
            else:
                prev = "CY" if col == "F1" else f"F{int(col[1]) - 1}"
                m.set("is", "revenue", col, Formula(f"{{revenue@{prev}}}*(1+{{inp.growth@{col}}})"))
            margin = "{inp.q4_gross_margin}" if plugs and col == "C4" else "{inp.gross_margin}"
            m.set("is", "cogs", col, Formula(f"{{revenue@{col}}}*(1-{margin})"))
            m.set("is", "sga", col, Formula(f"{{revenue@{col}}}*{{inp.sga_pct}}"))
            m.set(
                "is",
                "operating_income",
                col,
                Formula(f"{{gross_profit@{col}}}-{{sga@{col}}}-{{other_opex@{col}}}"),
            )
            per = "/4" if col in C else ""
            times = "" if col in C else "*4"
            m.set("is", "interest_expense", col, Formula(f"{{inp.interest}}{per}"))
            m.set(
                "is",
                "pretax_income",
                col,
                Formula(f"{{operating_income@{col}}}-{{interest_expense@{col}}}+{{other_nonop@{col}}}"),
            )
            m.set("is", "income_tax", col, Formula(f"{{pretax_income@{col}}}*{{inp.tax_rate}}"))
            m.set(
                "is",
                "net_income",
                col,
                Formula(f"{{pretax_income@{col}}}-{{income_tax@{col}}}+{{other_after_tax@{col}}}"),
            )
            m.set("is", "other_nonop", col, Formula(f"{{inp.other_nonop_q}}{times}"))
            m.set("is", "other_after_tax", col, Formula(f"{{inp.other_after_tax_q}}{times}"))
            m.set("is", "other_opex", col, Formula(f"{{revenue@{col}}}*{{inp.other_opex_pct}}"))
        m.set("is", "gross_profit", col, Formula(f"{{revenue@{col}}}-{{cogs@{col}}}"))
        if actual or col in ("P4", "CY"):
            m.set(
                "is",
                "other_opex",
                col,
                Formula(f"{{gross_profit@{col}}}-{{sga@{col}}}-{{operating_income@{col}}}"),
            )
            m.set(
                "is",
                "other_nonop",
                col,
                Formula(f"{{pretax_income@{col}}}-{{operating_income@{col}}}+{{interest_expense@{col}}}"),
            )
            m.set(
                "is",
                "other_after_tax",
                col,
                Formula(f"{{net_income@{col}}}-({{pretax_income@{col}}}-{{income_tax@{col}}})"),
            )
        if actual or col == "P4":
            m.set("is", "da", col, ytd_quarter("da", col))
        elif col == "CY":
            m.set("is", "da", col, Formula("SUM({da@C1:C4})"))
        else:
            m.set("is", "da", col, Formula(f"{{revenue@{col}}}*{{inp.da_pct}}"))
        m.set("is", "ebitda", col, Formula(f"{{operating_income@{col}}}+{{da@{col}}}"))

    # Balance sheet ---------------------------------------------------------------------------
    for col in BS_COLUMNS:
        if is_actual(col, last):
            for line in BS_TYPED:
                typed("bs", line, col, BS_KEY[col], v[line][BS_KEY[col]])
            m.set(
                "bs",
                "other_current_assets",
                col,
                Formula(f"{{current_assets@{col}}}-{{cash@{col}}}-{{receivables@{col}}}-{{inventory@{col}}}"),
            )
            m.set(
                "bs",
                "other_noncurrent_assets",
                col,
                Formula(
                    f"{{total_assets@{col}}}-{{current_assets@{col}}}-{{ppe@{col}}}-{{goodwill@{col}}}-{{intangibles@{col}}}"
                ),
            )
            m.set(
                "bs",
                "other_current_liabilities",
                col,
                Formula(
                    f"{{current_liabilities@{col}}}-{{payables@{col}}}-{{short_term_debt@{col}}}-{{current_ltd@{col}}}"
                ),
            )
            m.set(
                "bs",
                "other_noncurrent_liabilities",
                col,
                Formula(
                    f"{{total_liabilities_equity@{col}}}-{{current_liabilities@{col}}}-{{long_term_debt@{col}}}-{{redeemable_nci@{col}}}-{{equity@{col}}}-{{nci@{col}}}"
                ),
            )
        else:
            prev = prev_quarter(col)
            dd = days(col)
            m.set("bs", "cash", col, Formula(f"{{cf.end_cash@{col}}}"))
            m.set("bs", "receivables", col, Formula(f"{{is.revenue@{col}}}*{{inp.dso}}/{dd:g}"))
            m.set("bs", "inventory", col, Formula(f"{{is.cogs@{col}}}*{{inp.dio}}/{dd:g}"))
            m.set("bs", "payables", col, Formula(f"{{is.cogs@{col}}}*{{inp.dpo}}/{dd:g}"))
            for line in (
                "other_current_assets",
                "goodwill",
                "intangibles",
                "other_noncurrent_assets",
                "short_term_debt",
                "current_ltd",
                "other_current_liabilities",
                "long_term_debt",
                "other_noncurrent_liabilities",
                "redeemable_nci",
                "nci",
            ):
                m.set("bs", line, col, Formula(f"{{{line}@{prev}}}"))
            m.set(
                "bs",
                "current_assets",
                col,
                Formula(
                    f"{{cash@{col}}}+{{receivables@{col}}}+{{inventory@{col}}}+{{other_current_assets@{col}}}"
                ),
            )
            m.set("bs", "ppe", col, Formula(f"{{ppe@{prev}}}-{{cf.capex@{col}}}-{{is.da@{col}}}"))
            m.set(
                "bs",
                "total_assets",
                col,
                Formula(
                    f"{{current_assets@{col}}}+{{ppe@{col}}}+{{goodwill@{col}}}+{{intangibles@{col}}}+{{other_noncurrent_assets@{col}}}"
                ),
            )
            m.set(
                "bs",
                "current_liabilities",
                col,
                Formula(
                    f"{{payables@{col}}}+{{short_term_debt@{col}}}+{{current_ltd@{col}}}+{{other_current_liabilities@{col}}}"
                ),
            )
            m.set("bs", "equity", col, Formula(f"{{equity@{prev}}}+{{is.net_income@{col}}}+{{cf.cff@{col}}}"))
            m.set(
                "bs",
                "total_liabilities_equity",
                col,
                Formula(
                    f"{{current_liabilities@{col}}}+{{long_term_debt@{col}}}+{{other_noncurrent_liabilities@{col}}}+{{redeemable_nci@{col}}}+{{equity@{col}}}+{{nci@{col}}}"
                ),
            )
        m.set(
            "bs",
            "total_liabilities",
            col,
            Formula(
                f"{{total_liabilities_equity@{col}}}-{{redeemable_nci@{col}}}-{{equity@{col}}}-{{nci@{col}}}"
            ),
        )
        m.set("bs", "total_equity", col, Formula(f"{{equity@{col}}}+{{nci@{col}}}"))
        m.set("bs", "check", col, Formula(f"{{total_assets@{col}}}-{{total_liabilities_equity@{col}}}"))

    # Cash flow statement ---------------------------------------------------------------------
    for col in CF_COLUMNS:
        m.set("cf", "net_income", col, Formula(f"{{is.net_income@{col}}}"))
        m.set("cf", "da", col, Formula(f"{{is.da@{col}}}"))
        if col == "CY":
            for line in (
                "wc_other",
                "cfo",
                "capex",
                "other_investing",
                "cfi",
                "cff",
                "fx_other",
                "net_change",
            ):
                m.set("cf", line, col, Formula(f"SUM({{{line}@C1:C4}})"))
            m.set("cf", "begin_cash", col, Formula("{bs.cash@PY}"))
            m.set("cf", "end_cash", col, Formula("{begin_cash@CY}+{net_change@CY}"))
        elif is_actual(col, last):
            for line in ("cfo", "capex", "cfi", "cff"):
                m.set("cf", line, col, ytd_quarter(line, col))
            m.set("cf", "wc_other", col, Formula(f"{{cfo@{col}}}-{{net_income@{col}}}-{{da@{col}}}"))
            m.set("cf", "other_investing", col, Formula(f"{{cfi@{col}}}-{{capex@{col}}}"))
            if col != "PY":
                prev = prev_quarter(col)
                m.set(
                    "cf",
                    "fx_other",
                    col,
                    Formula(
                        f"{{bs.cash@{col}}}-{{bs.cash@{prev}}}-{{cfo@{col}}}-{{cfi@{col}}}-{{cff@{col}}}"
                    ),
                )
        else:
            prev = prev_quarter(col)
            m.set(
                "cf",
                "wc_other",
                col,
                Formula(
                    f"{{bs.receivables@{prev}}}-{{bs.receivables@{col}}}+{{bs.inventory@{prev}}}-{{bs.inventory@{col}}}+{{bs.payables@{col}}}-{{bs.payables@{prev}}}"
                ),
            )
            m.set("cf", "cfo", col, Formula(f"{{net_income@{col}}}+{{da@{col}}}+{{wc_other@{col}}}"))
            m.set("cf", "capex", col, Formula(f"-{{is.revenue@{col}}}*{{inp.capex_pct}}"))
            times = "" if col in C else "*4"
            m.set("cf", "other_investing", col, Formula(f"{{inp.other_investing_q}}{times}"))
            m.set("cf", "cfi", col, Formula(f"{{capex@{col}}}+{{other_investing@{col}}}"))
            m.set("cf", "cff", col, Formula(f"-{{is.net_income@{col}}}*{{inp.payout}}"))
            m.set("cf", "fx_other", col, Formula(f"{{inp.fx_other_q}}{times}"))
        if col not in ("PY", "CY"):
            prev = prev_quarter(col)
            m.set(
                "cf",
                "net_change",
                col,
                Formula(f"{{cfo@{col}}}+{{cfi@{col}}}+{{cff@{col}}}+{{fx_other@{col}}}"),
            )
            m.set("cf", "begin_cash", col, Formula(f"{{bs.cash@{prev}}}"))
            m.set("cf", "end_cash", col, Formula(f"{{begin_cash@{col}}}+{{net_change@{col}}}"))
        m.set("cf", "fcf", col, Formula(f"{{cfo@{col}}}+{{capex@{col}}}"))

    if plugs:
        # An analyst's hardcoded estimate in a forecast year: a round number, not a formula.
        plug = round(0.001 * v["revenue"]["FY-1"], -5) or 100_000.0
        m.set("is", "other_nonop", "F1", float(plug))

    # Valuation -------------------------------------------------------------------------------
    for i, col in enumerate(C, start=1):
        m.set("val", "quarter", col, float(i), COUNT)
    for col in (*C, *F):
        m.set("val", "ebit", col, Formula(f"{{is.operating_income@{col}}}"))
        m.set("val", "tax_on_ebit", col, Formula(f"-{{ebit@{col}}}*{{inp.tax_rate}}"))
        m.set("val", "nopat", col, Formula(f"{{ebit@{col}}}+{{tax_on_ebit@{col}}}"))
        m.set("val", "da", col, Formula(f"{{is.da@{col}}}"))
        m.set("val", "capex", col, Formula(f"{{cf.capex@{col}}}"))
        m.set("val", "wc", col, Formula(f"{{cf.wc_other@{col}}}"))
        m.set("val", "ufcf", col, Formula(f"{{nopat@{col}}}+{{da@{col}}}+{{capex@{col}}}+{{wc@{col}}}"))
    for col in F:
        m.set("val", "period", col, Formula(f"{{stub_years@V}}+{col[1]}"))
        m.set("val", "discount", col, Formula(f"1/(1+{{inp.wacc}})^{{period@{col}}}"))
        m.set("val", "pv", col, Formula(f"{{ufcf@{col}}}*{{discount@{col}}}"))

    def trailing(line: str) -> Formula:
        if last == 0:
            return Formula(f"SUM({{is.{line}@P1:P4}})")
        prior = f"SUM({{is.{line}@P{last + 1}:P4}})+" if last < 4 else ""
        return Formula(f"{prior}SUM({{is.{line}@C1:C{last}}})")

    at = f"C{last}" if last else "PY"  # the latest reported balance sheet
    scalars = {
        "ltm_revenue": trailing("revenue"),
        "ltm_ebitda": trailing("ebitda"),
        "stub_years": Formula("(4-{inp.last_q})/4"),
        "stub_ufcf": Formula("SUMPRODUCT(({quarter@C1:C4}>{inp.last_q})*{ufcf@C1:C4})"),
        "stub_discount": Formula("1/(1+{inp.wacc})^{stub_years@V}"),
        "pv_stub": Formula("{stub_ufcf@V}*{stub_discount@V}"),
        "terminal_value": Formula("{ufcf@F4}*(1+{inp.terminal_growth})/({inp.wacc}-{inp.terminal_growth})"),
        "pv_terminal": Formula("{terminal_value@V}*{discount@F4}"),
        "enterprise_value": Formula("{pv_stub@V}+SUM({pv@F1:F4})+{pv_terminal@V}"),
        "cash": Formula(f"{{bs.cash@{at}}}"),
        "short_term_debt": Formula(f"{{bs.short_term_debt@{at}}}"),
        "current_ltd": Formula(f"{{bs.current_ltd@{at}}}"),
        "long_term_debt": Formula(f"{{bs.long_term_debt@{at}}}"),
        "net_debt": Formula("{short_term_debt@V}+{current_ltd@V}+{long_term_debt@V}-{cash@V}"),
        "nci": Formula(f"{{bs.nci@{at}}}+{{bs.redeemable_nci@{at}}}"),
        "equity_value": Formula("{enterprise_value@V}-{net_debt@V}-{nci@V}"),
        "shares": Formula("{inp.shares}"),
        "per_share": Formula("{equity_value@V}/{shares@V}"),
        "ev_ltm_ebitda": Formula("{enterprise_value@V}/{ltm_ebitda@V}"),
    }
    for line, formula in scalars.items():
        m.set("val", line, "V", formula, SHARES if line == "shares" else AMOUNT)
    return m
