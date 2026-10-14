"""A LibreOffice Python macro: open each workbook in Calc, apply an analyst's edits, save as xlsx.

Runs inside soffice (scripts/third_party.py starts it), not in this repo's Python: Calc does the
edits, so an inserted row or column, or a moved range, updates every formula that refers to it, as
it would in Excel. The jobs file (path in FUE_JOBS) is a list of {"src", "dst", "ops"}; the result
of each job is written to FUE_JOBS + ".log".

Operations, applied in order:
  {"op": "insert_cols", "sheet": S, "before": "K", "count": 1}
  {"op": "insert_rows", "sheet": S, "before": 12, "count": 1}
  {"op": "delete_rows", "sheet": S, "first": 12, "count": 1}
  {"op": "set", "sheet": S, "cell": "K4", "formula": "=J4*2"}   (or "value": 12.5, or "text": "Q1")
      a formula is in Calc's own syntax: another sheet's cell is $'Sheet name'.A1, not 'Sheet name'!A1,
      and a function's arguments are separated by ; (EOMONTH(E16;3)), not ,
  {"op": "clear", "sheet": S, "range": "K4:K9"}
  {"op": "move", "sheet": S, "range": "A20:H30", "to": "A40"}  (cut and paste: references follow)
  {"op": "copy", "sheet": S, "range": "J4:J9", "to": "K4"}     (copy and paste: relative references shift)
"""

import json
import os
from pathlib import Path

from com.sun.star.beans import PropertyValue


def _prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def _col(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _apply(doc, ops):
    for op in ops:
        sh = doc.Sheets.getByName(op["sheet"])
        kind = op["op"]
        if kind == "insert_cols":
            sh.Columns.insertByIndex(_col(op["before"]), op.get("count", 1))
        elif kind == "insert_rows":
            sh.Rows.insertByIndex(op["before"] - 1, op.get("count", 1))
        elif kind == "delete_rows":
            sh.Rows.removeByIndex(op["first"] - 1, op.get("count", 1))
        elif kind == "set":
            cell = sh.getCellRangeByName(op["cell"])
            if "formula" in op:
                cell.setFormula(op["formula"])
            elif "value" in op:
                cell.setValue(op["value"])
            else:
                cell.setString(op["text"])
        elif kind == "clear":
            sh.getCellRangeByName(op["range"]).clearContents(1 | 2 | 4 | 16)  # values, dates, text, formulas
        elif kind in ("move", "copy"):
            source = sh.getCellRangeByName(op["range"]).getRangeAddress()
            to = sh.getCellRangeByName(op["to"]).getCellAddress()
            (sh.moveRange if kind == "move" else sh.copyRange)(to, source)
        else:
            raise ValueError(f"unknown operation {kind!r}")


def run(*_args):
    jobs_path = Path(os.environ["FUE_JOBS"])
    desktop = XSCRIPTCONTEXT.getDesktop()  # noqa: F821 - provided by LibreOffice's script runtime
    log = []
    for job in json.loads(jobs_path.read_text()):
        try:
            doc = desktop.loadComponentFromURL(
                Path(job["src"]).as_uri(), "_blank", 0, (_prop("Hidden", True),)
            )
            _apply(doc, job["ops"])
            doc.calculateAll()
            doc.storeToURL(Path(job["dst"]).as_uri(), (_prop("FilterName", "Calc MS Excel 2007 XML"),))
            doc.close(True)
            log.append({"dst": job["dst"], "ok": True})
        except Exception as exc:  # report and go on to the next job
            log.append({"dst": job["dst"], "ok": False, "error": repr(exc)})
    Path(str(jobs_path) + ".log").write_text(json.dumps(log, indent=1))
    desktop.terminate()


g_exportedScripts = (run,)
