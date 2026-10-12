"""Write a logical model (model.py) into a workbook with a style's layout (styles.py)."""

from __future__ import annotations

import datetime as dt

from openpyxl import Workbook

from filing_update_evals import model as M
from filing_update_evals import styles as S

FIXED_TIME = dt.datetime(2026, 1, 1)


def physical(m: M.Logical, lay: S.Layout) -> dict[tuple[str, str], object]:
    """(sheet, coordinate) -> the content the workbook holds: labels, headers and every cell."""
    out: dict[tuple[str, str], object] = {key: value for key, value in lay.static.items() if value != ""}
    for (section, line, col), cell in m.cells.items():
        key = (section, line, col)
        if key not in lay.place:
            raise KeyError(f"{lay.style}: no place for {key}")
        sheet, coord = lay.place[key]
        if isinstance(cell.content, M.Formula):
            out[(sheet, coord)] = S.render(cell.content.template, section, lay, sheet)
        elif isinstance(cell.content, str):
            out[(sheet, coord)] = cell.content
        else:
            out[(sheet, coord)] = S.scale(cell, lay)
    return out


def to_workbook(cells: dict[tuple[str, str], object], sheets: tuple[str, ...]) -> Workbook:
    wb = Workbook()
    wb.properties.created = FIXED_TIME
    wb.properties.modified = FIXED_TIME
    wb.properties.creator = "filing-update-evals"
    for i, name in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet(name)
        ws.title = name
        ws.column_dimensions["A"].width = 52
        for col in range(2, 20):
            ws.column_dimensions[chr(ord("A") + col - 1)].width = 13
    for (sheet, coord), value in sorted(cells.items()):
        wb[sheet][coord] = value
    return wb


def sources(m: M.Logical, lay: S.Layout) -> dict[str, dict]:
    """`Sheet!A1` -> where each typed filing number comes from (see model.Cell.source)."""
    return {
        f"{lay.place[key][0]}!{lay.place[key][1]}": cell.source
        for key, cell in m.cells.items()
        if cell.source and key in lay.place
    }
