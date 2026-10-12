"""Read a filing's rendered statements: FilingSummary.xml and the R pages SEC's XBRL viewer
generates from the filing (R1.htm cover, R2.htm ...). These pages show each statement exactly as
the filer presents it (its own line labels, order, columns and units), so they are what a task's
filing excerpt is made from, and what the screen checks the mapped XBRL facts against.

Both files are downloaded data: XML with a DTD or entity declaration is refused, and the HTML is
read with the standard library's tolerant parser, text only.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser

_DTD = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)

KINDS = {
    "balance": re.compile(r"BALANCE SHEET|FINANCIAL POSITION|FINANCIAL CONDITION", re.I),
    "cash": re.compile(r"CASH FLOW", re.I),
    "income": re.compile(r"OPERATIONS|INCOME|EARNINGS", re.I),
}


@dataclass
class Report:
    file: str
    short_name: str
    category: str
    kind: str  # cover | income | balance | cash | other


def statement_reports(summary_xml: bytes) -> list[Report]:
    if _DTD.search(summary_xml):
        raise ValueError("FilingSummary.xml declares a DTD or entity")
    root = ET.fromstring(summary_xml)
    out = []
    for report in root.iter("Report"):
        file = (report.findtext("HtmlFileName") or "").strip()
        name = (report.findtext("ShortName") or "").strip()
        category = (report.findtext("MenuCategory") or "").strip()
        if not file:
            continue
        kind = "other"
        if category == "Cover":
            kind = "cover"
        elif category == "Statements" and "parenthetical" not in name.lower():
            if KINDS["balance"].search(name):
                kind = "balance"
            elif KINDS["cash"].search(name):
                kind = "cash"
            elif KINDS["income"].search(name) and not re.search(
                r"^\W*(CONSOLIDATED\W+)?(CONDENSED\W+)?(STATEMENTS?\W+OF\W+)?COMPREHENSIVE", name, re.I
            ):
                kind = "income"
        out.append(Report(file, name, category, kind))
    return out


@dataclass
class Table:
    title: str = ""
    unit: str = ""
    header_rows: list[list[str]] = field(default_factory=list)
    rows: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def scale(self) -> int:
        """Dollar scale from the title cell: "$ in Thousands" -> 1000, "$ in Millions" -> 10**6."""
        text = self.unit.lower()
        if "$ in millions" in text:
            return 1_000_000
        if "$ in thousands" in text:
            return 1_000
        if "$ in billions" in text:
            return 1_000_000_000
        return 1

    def numbers(self) -> list[float]:
        out = []
        for _, cells in self.rows:
            for cell in cells:
                value = parse_number(cell)
                if value is not None:
                    out.append(value)
        return out


_NUM = re.compile(r"^\(?-?\$?\s*\(?\s*[\d,]*\.?\d+\s*\)?$")


def parse_number(text: str) -> float | None:
    t = text.replace("\xa0", " ").strip()
    if not t or not _NUM.match(t):
        return None
    negative = "(" in t or t.startswith("-")
    digits = re.sub(r"[^\d.]", "", t)
    if not digits or digits == ".":
        return None
    value = float(digits)
    return -value if negative else value


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table = Table()
        self._in_cell = False
        self._cell_is_header = False
        self._cell: list[str] = []
        self._row: list[tuple[str, bool]] = []
        self._depth = 0
        self._skip = 0
        self._tables = 0  # only the first table is the statement; later ones are SEC's definitions

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._tables += 1
        if self._depth != 1 or self._tables != 1:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell, self._cell_is_header, self._cell = True, tag == "th", []
        elif tag == "br" and self._in_cell:
            self._cell.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "table":
            self._depth -= 1
            return
        if self._depth != 1 or self._tables != 1:
            return
        if tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            self._row.append(("".join(self._cell).strip(), self._cell_is_header))
        elif tag == "tr":
            self._finish_row()

    def handle_data(self, data):
        if self._in_cell and not self._skip:
            self._cell.append(data)

    def _finish_row(self) -> None:
        row = self._row
        if not row:
            return
        if all(is_header for _, is_header in row):
            texts = [text for text, _ in row]
            if not self.table.title and texts:
                first = texts[0].split("\n")
                self.table.title = first[0].strip()
                self.table.unit = " ".join(x.strip() for x in first[1:] if x.strip())
                texts = texts[1:]
            self.table.header_rows.append([" ".join(t.split()) for t in texts])
        else:
            label = " ".join(row[0][0].split())
            self.table.rows.append((label, [" ".join(text.split()) for text, _ in row[1:]]))


def parse_rpage(html: bytes) -> Table:
    parser = _Parser()
    parser.feed(html.decode("utf-8", errors="replace"))
    parser.close()
    return parser.table


def to_markdown(table: Table, heading: str, keep: tuple[str, ...] | None = None) -> str:
    """A rendered statement as a markdown table: its title and units, header rows and every row
    (or, with `keep`, only rows whose label contains one of those words)."""
    lines = [f"### {heading}", "", f"{table.title}" + (f" ({table.unit})" if table.unit else ""), ""]
    width = max([len(cells) for _, cells in table.rows] + [len(h) for h in table.header_rows] + [1])
    headers = [h + [""] * (width - len(h)) for h in table.header_rows] or [[""] * width]
    if len(headers) > 1 and len(headers[0]) < width:
        headers[0] = headers[0] + [""] * (width - len(headers[0]))
    top = headers[0]
    lines.append("| | " + " | ".join(top) + " |")
    lines.append("|---" * (width + 1) + "|")
    for extra in headers[1:]:
        lines.append("| | " + " | ".join(extra) + " |")
    for label, cells in table.rows:
        if keep is not None and not any(word.lower() in label.lower() for word in keep):
            continue
        cells = cells + [""] * (width - len(cells))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
