"""Architecture B: a cash flow statement derived from the balance sheet. Not a re-layout of the
base model (model.py): the cash flow logic differs.

The base model types each 10-Q's year-to-date cash flows (operating, capex, investing,
financing) and takes the quarter as a difference; an "exchange rate and other" line ties the
statement to the balance sheet's cash. Here no cash flow figure is typed. In every column, the
statement is built from the change in each balance sheet line between two balance sheet dates:
  working capital    the change in receivables, inventory, other current assets, payables and
                     other current liabilities
  operating          net income + D&A + working capital + the change in other non-current
                     liabilities less other non-current assets
  capex              -(change in PP&E + D&A)
  other investing    -(change in goodwill and intangibles)
  financing          change in debt + (change in equity - net income) + change in
                     non-controlling interests
These add up to the change in cash exactly (a check line shows 0), so there is no plug line.
In estimate columns cash is the balance sheet's plug (liabilities and equity less every other
asset), PP&E grows by capex (revenue x the capex input) less D&A, and equity by net income less
payouts. D&A is the one cash flow statement figure the model reads, typed year to date below the
statement, as the base model does.

An update types the new quarter's income statement, balance sheet and year-to-date D&A; the cash
flow statement is the same formulas before and after, and a figure typed into it breaks the
derivation. The statement covers the current year's quarters, the current year and the forecast
years (the prior year has no balance sheet before it in the model).
"""

from __future__ import annotations

from filing_update_evals import model as M
from filing_update_evals import styles as S

STYLE = "B"
CF_LINES = (
    "net_income",
    "da",
    "chg_receivables",
    "chg_inventory",
    "chg_other_current_assets",
    "chg_payables",
    "chg_other_current_liabilities",
    "wc_other",
    "chg_other_noncurrent",
    "cfo",
    "capex",
    "other_investing",
    "cfi",
    "chg_debt",
    "chg_equity",
    "cff",
    "net_change",
    "begin_cash",
    "end_cash",
    "check_cash",
    "fcf",
)
CF_COLUMNS = (*M.C, "CY", *M.F)
FLOWS = tuple(line for line in CF_LINES if line not in ("begin_cash", "end_cash", "check_cash"))
CF_LABELS = {
    "net_income": "Net income attributable to the company",
    "da": "Depreciation and amortization",
    "chg_receivables": "(Increase) decrease in accounts receivable",
    "chg_inventory": "(Increase) decrease in inventories",
    "chg_other_current_assets": "(Increase) decrease in other current assets",
    "chg_payables": "Increase (decrease) in accounts payable",
    "chg_other_current_liabilities": "Increase (decrease) in other current liabilities",
    "wc_other": "Change in working capital",
    "chg_other_noncurrent": "Change in other non-current liabilities, net of other non-current assets",
    "cfo": "Cash from operating activities",
    "capex": "Capital expenditures (change in PP&E plus D&A)",
    "other_investing": "Acquisitions and other investing (change in goodwill and intangibles)",
    "cfi": "Cash from investing activities",
    "chg_debt": "Change in debt",
    "chg_equity": "Change in equity other than net income, incl. non-controlling interests",
    "cff": "Cash from financing activities",
    "net_change": "Net change in cash",
    "begin_cash": "Cash, beginning of period",
    "end_cash": "Cash, end of period",
    "check_cash": "Check: end of period cash less balance sheet cash",
    "fcf": "Free cash flow (operating cash flow + capital expenditures)",
}
DROPPED_INPUTS = ("other_investing_q", "fx_other_q")
"""Base inputs for cash flow lines this architecture derives instead."""


def _change(line: str, col: str, prev: str, sign: str = "") -> str:
    """The change in a balance sheet line, as a formula fragment."""
    if sign == "-":
        return f"{{bs.{line}@{prev}}}-{{bs.{line}@{col}}}"
    return f"{{bs.{line}@{col}}}-{{bs.{line}@{prev}}}"


def build(data: dict, last: int) -> M.Logical:
    m = M.build(data, last)
    for key in list(m.cells):
        section, line, _ = key
        if (
            section == "cf"
            or (section == "ytd" and line != "da")
            or (section == "inp" and line in DROPPED_INPUTS)
        ):
            del m.cells[key]
    noncash = (
        "receivables",
        "inventory",
        "other_current_assets",
        "ppe",
        "goodwill",
        "intangibles",
        "other_noncurrent_assets",
    )
    for col in M.BS_COLUMNS:
        if M.is_actual(col, last):
            continue
        prev = M.prev_quarter(col)
        m.set(
            "bs",
            "ppe",
            col,
            M.Formula(f"{{ppe@{prev}}}+{{is.revenue@{col}}}*{{inp.capex_pct}}-{{is.da@{col}}}"),
        )
        m.set("bs", "equity", col, M.Formula(f"{{equity@{prev}}}+{{is.net_income@{col}}}*(1-{{inp.payout}})"))
        m.set(
            "bs",
            "cash",
            col,
            M.Formula(
                f"{{total_liabilities_equity@{col}}}-(" + "+".join(f"{{{x}@{col}}}" for x in noncash) + ")"
            ),
        )
    for col in CF_COLUMNS:
        if col == "CY":
            for line in FLOWS:
                if line not in ("net_income", "da"):
                    m.set("cf", line, col, M.Formula(f"SUM({{{line}@C1:C4}})"))
            m.set("cf", "net_income", col, M.Formula(f"{{is.net_income@{col}}}"))
            m.set("cf", "da", col, M.Formula(f"{{is.da@{col}}}"))
            m.set("cf", "begin_cash", col, M.Formula("{bs.cash@PY}"))
            m.set("cf", "end_cash", col, M.Formula("{begin_cash@CY}+{net_change@CY}"))
            m.set("cf", "check_cash", col, M.Formula("{end_cash@CY}-{bs.cash@C4}"))
            continue
        prev = M.prev_quarter(col)
        f = {
            "net_income": f"{{is.net_income@{col}}}",
            "da": f"{{is.da@{col}}}",
            "chg_receivables": _change("receivables", col, prev, "-"),
            "chg_inventory": _change("inventory", col, prev, "-"),
            "chg_other_current_assets": _change("other_current_assets", col, prev, "-"),
            "chg_payables": _change("payables", col, prev),
            "chg_other_current_liabilities": _change("other_current_liabilities", col, prev),
            "wc_other": "+".join(
                f"{{{x}@{col}}}"
                for x in (
                    "chg_receivables",
                    "chg_inventory",
                    "chg_other_current_assets",
                    "chg_payables",
                    "chg_other_current_liabilities",
                )
            ),
            "chg_other_noncurrent": f"{_change('other_noncurrent_liabilities', col, prev)}-("
            f"{_change('other_noncurrent_assets', col, prev)})",
            "cfo": f"{{net_income@{col}}}+{{da@{col}}}+{{wc_other@{col}}}+{{chg_other_noncurrent@{col}}}",
            "capex": f"-({_change('ppe', col, prev)}+{{da@{col}}})",
            "other_investing": f"-({_change('goodwill', col, prev)}+{_change('intangibles', col, prev)})",
            "cfi": f"{{capex@{col}}}+{{other_investing@{col}}}",
            "chg_debt": "+".join(
                _change(x, col, prev) for x in ("short_term_debt", "current_ltd", "long_term_debt")
            ),
            "chg_equity": f"{_change('equity', col, prev)}-{{net_income@{col}}}+{_change('nci', col, prev)}+"
            f"{_change('redeemable_nci', col, prev)}",
            "cff": f"{{chg_debt@{col}}}+{{chg_equity@{col}}}",
            "net_change": f"{{cfo@{col}}}+{{cfi@{col}}}+{{cff@{col}}}",
            "begin_cash": f"{{bs.cash@{prev}}}",
            "end_cash": f"{{begin_cash@{col}}}+{{net_change@{col}}}",
            "check_cash": f"{{end_cash@{col}}}-{{bs.cash@{col}}}",
            "fcf": f"{{cfo@{col}}}+{{capex@{col}}}",
        }
        for line, template in f.items():
            m.set("cf", line, col, M.Formula(template))
    return m


def layout(data: dict) -> S.Layout:
    lay = S.Layout(
        STYLE, ("Inputs", "IS", "BS", "CF", "DCF", S.SCRATCH), 1e6, 1e6, "$ in millions", "millions"
    )
    labels = S._labels("S1", data)
    labels["cf"] = dict(CF_LABELS) | {"net_income": labels["is"]["net_income"]}
    labels["cf"]["da"] = labels["is"]["da"].removeprefix("Memo: ").replace(" (cash flow statement)", "")
    labels["cf"]["da"] = labels["cf"]["da"][0].upper() + labels["cf"]["da"][1:]
    fiscal = S._fiscal_labels(data, short=False)
    last_ref = "Inputs!$C$4"
    name = data["name"]
    lay.static[("Inputs", "A1")] = f"{name}: model inputs"
    lay.static[("Inputs", "A2")] = "$ in millions unless noted; rates as decimals"
    for col in M.F:
        lay.static[("Inputs", f"{S.GRID[col]}3")] = fiscal[col]
    row = 4
    for item in S.INPUT_ORDER:
        if item in DROPPED_INPUTS:
            continue
        if item is None:
            row += 1
            continue
        lay.static[("Inputs", f"A{row}")] = S._input_label(item, data, lay)
        if item == "growth":
            for col in M.F:
                lay.place[("inp", item, col)] = ("Inputs", f"{S.GRID[col]}{row}")
        else:
            lay.place[("inp", item, "V")] = ("Inputs", f"C{row}")
        row += 1
    titles = {
        "IS": "income statement",
        "BS": "balance sheet",
        "CF": "cash flow statement",
        "DCF": "unlevered DCF and valuation",
    }
    for sheet, title in titles.items():
        lay.static[(sheet, "A1")] = f"{name}: {title}"
        lay.static[(sheet, "A2")] = "$ in millions"
    grid = S.GRID
    is_cols = {c: grid[c] for c in M.COLUMNS}
    bs_cols = {c: grid[c] for c in M.BS_COLUMNS}
    cf_cols = {c: grid[c] for c in CF_COLUMNS}
    for sheet, cols in (("IS", is_cols), ("BS", bs_cols), ("CF", cf_cols)):
        S._headers(lay, sheet, 3, cols, fiscal, None, last_ref)
    S._section(lay, "IS", 6, "is", M.IS_LINES, is_cols, labels)
    S._section(lay, "BS", 6, "bs", M.BS_LINES, bs_cols, labels)
    row = S._section(lay, "CF", 6, "cf", CF_LINES, cf_cols, labels) + 1
    lay.static[("CF", f"A{row}")] = "As reported in each filing (year to date)"
    ytd_cols = {c: grid[c] for c in (*M.P[:3], "PY", *M.C)}
    S._section(lay, "CF", row + 1, "ytd", ("da",), ytd_cols, labels)
    q_cols = {c: grid[c] for c in (*M.C, *M.F)}
    S._headers(lay, "DCF", 3, q_cols, fiscal, None, last_ref)
    row = S._section(lay, "DCF", 6, "val", M.VAL_Q_LINES, q_cols, labels)
    row = (
        S._section(lay, "DCF", row, "val", ("period", "discount", "pv"), {c: grid[c] for c in M.F}, labels)
        + 1
    )
    S._val_scalars(lay, "DCF", row, labels)
    return lay
