"""Architecture A: revenue built from its parts. Not a re-layout of the base model (model.py): the
revenue logic differs.

The base model types consolidated revenue in actual columns and grows it with one rate. Here
revenue is built from the rows of the 10-Q's revenue breakdown (its segment note where the
tagging is clean, otherwise its geographic split; scripts/segments.py): each row is typed in
actual columns and grown at its own rate in estimates, and consolidated revenue is their sum in
every column. An update types the new quarter's rows from the breakdown note; revenue stays a
formula. Everything else is the base model.

The sheets are the statements layout (S1) plus a `Revenue` sheet: one row per segment (and
reconciling items, such as eliminations, where the filer tags them), the total, and a block of
growth drivers (the current year's rate against the same quarter a year earlier, and one per
forecast year).
"""

from __future__ import annotations

import json
from pathlib import Path

from filing_update_evals import model as M
from filing_update_evals import styles as S

STYLE = "A"
SHEET = "Revenue"
REPO = Path(__file__).resolve().parent.parent
RECONCILING_LABELS = {
    "items:CorporateNonSegmentMember": "Corporate and other",
    "items:IntersegmentEliminationMember": "Intersegment eliminations",
    "items:CorporateReconcilingItemsAndEliminationsMember": "Corporate, reconciling items and eliminations",
    "items:SegmentReconcilingItemsMember": "Reconciling items",
}


def load_breakdown(ticker: str) -> dict:
    return json.loads((REPO / "data" / "segments" / f"{ticker}.json").read_text())


def with_breakdown(data: dict, breakdown: dict, which: str = "task") -> dict:
    """The filer data with its revenue breakdown attached, by the data's own period keys.
    which: "task" for the task's data; "example" for the year-earlier data of a first-quarter
    task's worked example."""
    prefix = f"{which}:"
    values = {tag[len(prefix) :]: row for tag, row in breakdown["values"].items() if tag.startswith(prefix)}
    return data | {
        "breakdown": {
            "axis": breakdown["axis"],
            "members": breakdown["members"],
            "labels": {m: RECONCILING_LABELS.get(m, label) for m, label in breakdown["labels"].items()},
            "values": values,
            "filings": breakdown["filings"],
            "sources": breakdown["sources"],
            "page": breakdown["page"],
            "concept": data["lines"]["revenue"]["concept"],
        }
    }


def rows(data: dict) -> list[str]:
    return [f"r{i}" for i in range(1, len(data["breakdown"]["members"]) + 1)]


def growth_drivers(data: dict) -> dict[str, dict[str, float]]:
    """Per row: the current year's growth (the prior year against the year before, where the
    filings give that year by row; else the consolidated rate) and one rate per forecast year,
    fading like the base model's."""
    b = data["breakdown"]
    fallback = M.drivers(data)["growth_fy"]
    out = {}
    for name, member in zip(rows(data), b["members"], strict=True):
        last = b["values"]["FY-1"][member]
        before = b["values"].get("FY-2", {}).get(member)
        g = round(last / before - 1, 3) if before and last and (last > 0) == (before > 0) else fallback
        out[name] = {"CY": g} | {col: round(max(g * (1 - 0.15 * i), 0.02), 3) for i, col in enumerate(M.F)}
    return out


def _source(data: dict, member: str, key: str) -> dict:
    b = data["breakdown"]
    start, end = data["periods"][key]
    names = b["sources"].get(f"{start}..{end}|{member}", [])
    filings = sorted((b["filings"][n] for n in names), key=lambda f: f["filed"])
    as_of = data["target"]["filed"]
    usable = [f for f in filings if f["filed"] <= as_of] or filings
    return {
        "concept": b["concept"],
        "accession": usable[-1]["accession"] if usable else "",
        "period": key,
        "start": start,
        "end": end,
        "sign": 1,
        "axis": b["axis"],
        "member": member,
    }


def build(data: dict, last: int) -> M.Logical:
    m = M.build(data, last)
    b = data["breakdown"]
    names = rows(data)
    for key in [k for k in m.cells if k[0] == "inp" and k[1] in ("growth_fy", "growth")]:
        del m.cells[key]
    for name, g in growth_drivers(data).items():
        for col, rate in g.items():
            m.set("seginp", name, col, rate, M.RATIO)
    for name, member in zip(names, b["members"], strict=True):
        for col in M.COLUMNS:
            if M.is_actual(col, last):
                key = M.IS_KEY[col]
                m.set("seg", name, col, float(b["values"][key][member]), M.AMOUNT, _source(data, member, key))
            elif col == "P4":
                m.set("seg", name, col, M.Formula(f"{{{name}@PY}}-{{{name}@P1}}-{{{name}@P2}}-{{{name}@P3}}"))
            elif col == "CY":
                m.set("seg", name, col, M.Formula(f"SUM({{{name}@C1:C4}})"))
            elif col in M.C:
                m.set("seg", name, col, M.Formula(f"{{{name}@P{col[1]}}}*(1+{{seginp.{name}@CY}})"))
            else:
                prev = "CY" if col == "F1" else f"F{int(col[1]) - 1}"
                m.set("seg", name, col, M.Formula(f"{{{name}@{prev}}}*(1+{{seginp.{name}@{col}}})"))
    for col in M.COLUMNS:
        m.set("seg", "total", col, M.Formula("+".join(f"{{{name}@{col}}}" for name in names)))
        m.set("is", "revenue", col, M.Formula(f"{{seg.total@{col}}}"))
    return m


def layout(data: dict) -> S.Layout:
    lay = S.Layout(
        STYLE,
        ("Inputs", SHEET, "IS", "BS", "CF", "DCF", S.SCRATCH),
        1e6,
        1e6,
        "$ in millions",
        "millions",
    )
    labels = S._labels("S1", data)
    fiscal = S._fiscal_labels(data, short=False)
    last_ref = "Inputs!$C$4"
    name = data["name"]
    b = data["breakdown"]
    lay.static[("Inputs", "A1")] = f"{name}: model inputs"
    lay.static[("Inputs", "A2")] = "$ in millions unless noted; rates as decimals"
    row = 4
    for item in S.INPUT_ORDER:
        if item in ("growth_fy", "growth"):
            continue
        if item is None:
            row += 1
            continue
        lay.static[("Inputs", f"A{row}")] = S._input_label(item, data, lay)
        lay.place[("inp", item, "V")] = ("Inputs", f"C{row}")
        row += 1
    lay.static[("Inputs", f"A{row + 1}")] = (
        f"Revenue growth drivers by {_axis_name(b['axis'])}: see the {SHEET} sheet"
    )
    titles = {
        SHEET: f"revenue by {_axis_name(b['axis'])}",
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
    cf_cols = {c: grid[c] for c in M.CF_COLUMNS}
    for sheet, cols in ((SHEET, is_cols), ("IS", is_cols), ("BS", bs_cols), ("CF", cf_cols)):
        S._headers(lay, sheet, 3, cols, fiscal, None, last_ref)
    names = rows(data)
    seg_labels = {"seg": {n: b["labels"][m] for n, m in zip(names, b["members"], strict=True)}}
    seg_labels["seg"]["total"] = "Total revenue"
    row = S._section(lay, SHEET, 6, "seg", [*names, "total"], is_cols, seg_labels) + 1
    lay.static[(SHEET, f"A{row}")] = (
        f"Growth drivers: {fiscal['CY']} quarters vs. the same quarter of {fiscal['PY']} (column "
        f"{grid['CY']}), and each forecast year"
    )
    driver_cols = {c: grid[c] for c in ("CY", *M.F)}
    driver_labels = {
        "seginp": {n: f"Growth: {b['labels'][m]}" for n, m in zip(names, b["members"], strict=True)}
    }
    S._section(lay, SHEET, row + 1, "seginp", names, driver_cols, driver_labels)
    S._section(lay, "IS", 6, "is", M.IS_LINES, is_cols, labels)
    S._section(lay, "BS", 6, "bs", M.BS_LINES, bs_cols, labels)
    row = S._section(lay, "CF", 6, "cf", M.CF_LINES, cf_cols, labels) + 1
    lay.static[("CF", f"A{row}")] = "As reported in each filing (year to date)"
    ytd_cols = {c: grid[c] for c in (*M.P[:3], "PY", *M.C)}
    S._section(lay, "CF", row + 1, "ytd", M.YTD_LINES, ytd_cols, labels)
    q_cols = {c: grid[c] for c in (*M.C, *M.F)}
    S._headers(lay, "DCF", 3, q_cols, fiscal, None, last_ref)
    row = S._section(lay, "DCF", 6, "val", M.VAL_Q_LINES, q_cols, labels)
    row = (
        S._section(lay, "DCF", row, "val", ("period", "discount", "pv"), {c: grid[c] for c in M.F}, labels)
        + 1
    )
    S._val_scalars(lay, "DCF", row, labels)
    return lay


def _axis_name(axis: str) -> str:
    return {"StatementBusinessSegmentsAxis": "segment", "StatementGeographicalAxis": "region"}.get(
        axis, "product line"
    )
