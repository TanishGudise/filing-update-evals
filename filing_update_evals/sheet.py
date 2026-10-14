"""Reading a worksheet's cells without walking its declared dimension."""

from __future__ import annotations


def stored_cells(ws) -> list:
    """The cells a sheet stores, in row then column order. `iter_rows()` walks every row up to the
    sheet's declared dimension, which a formatted last row can put at row 1,048,576 (one such sheet
    with 132 cells took 20 s per pass); this reads only what the file holds."""
    return sorted(ws._cells.values(), key=lambda c: (c.row, c.column))
