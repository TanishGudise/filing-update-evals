"""Render a workbook (formulas) plus its recalculated values as the text a model reads."""

from __future__ import annotations

from openpyxl.workbook.workbook import Workbook


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).upper()
    if isinstance(value, int | float):
        if float(value).is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def render(formulas: Workbook, values: dict[str, dict[str, object]], skip: tuple[str, ...] = ()) -> str:
    """One line per non-empty row: `row | A: label | C: 812 | F: =E5*(1+$C$9) -> 860.72`."""
    out = []
    for name in formulas.sheetnames:
        if name in skip:
            continue
        ws, vs = formulas[name], values.get(name, {})
        out.append(f"### Sheet `{name}`\n")
        for row in ws.iter_rows():
            parts = []
            for cell in row:
                if cell.value is None:
                    continue
                col = cell.column_letter
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    parts.append(f"{col}: {cell.value} -> {format_value(vs.get(cell.coordinate))}")
                elif isinstance(cell.value, str):
                    parts.append(f'{col}: "{cell.value}"')
                else:
                    parts.append(f"{col}: {format_value(cell.value)}")
            if parts:
                out.append(f"{row[0].row} | " + " | ".join(parts))
        if ws.max_row == 1 and ws["A1"].value is None:
            out.append("(empty)")
        out.append("")
    return "\n".join(out)
