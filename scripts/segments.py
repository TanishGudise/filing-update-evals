"""Segment revenue for architecture A (segment-driven revenue), from each filing's XBRL instance:
SEC's company facts carry no dimensional facts. Offline except the downloads, which go through
scripts/fetch.py (SEC only).

  python -I scripts/segments.py urls [TICKER ...]     the SEC files still to download
  python -I scripts/segments.py extract [TICKER ...]  data/segments/<ticker>.json and the screen,
                                                      data/segments/screen.md

Filings, per filer: the task's 10-Q (a first quarter) and the previous fiscal year's first three
10-Qs and its 10-K. Together they hold every period the task and its worked example (the previous
year's third-quarter update) need: the quarters as reported and as comparatives, and the annual
figures for the fourth quarters and the growth drivers.

Segment revenue is the filer's consolidated revenue concept with one segment member on
StatementBusinessSegmentsAxis (and, at most, OperatingSegmentsMember on ConsolidationItemsAxis).
Reconciling rows (corporate and other, intersegment eliminations) are the same concept with only
a ConsolidationItemsAxis member; the first set of them in RECONCILING that makes the segments add
up is kept. The screen keeps a filer only if its segment tagging is clean:
  - at least two rows, and the same members in every period and filing;
  - in every period, the segments sum exactly to the consolidated revenue the task data uses;
  - every filing that reports a (period, segment) figure reports the same one (no recast).
"""

from __future__ import annotations

from filing_update_evals.netguard import install

install()  # offline: loopback only, even when run with python -I

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "raw"
OUT = REPO / "data" / "segments"
TICKERS = (
    "GIS",
    "MLKN",
    "SJM",
    "LZB",
    "MDT",
    "MEI",
    "KFY",
    "CALM",
    "TSCO",
    "FAST",
    "GNTX",
    "ROL",
    "ROST",
    "HD",
    "WSM",
    "BBY",
)
"""The seven first-quarter filers (the main set's three and the replication's four), Cal-Maine
(qualified in the replication screen, not run), and the main set's second-quarter filers."""

SEGMENT_AXIS = "StatementBusinessSegmentsAxis"
AXES = (SEGMENT_AXIS, "StatementGeographicalAxis", "ProductOrServiceAxis")
"""Revenue breakdowns, in order of preference: the segment note, then the revenue
disaggregation note's geography and product lines."""
RECONCILING = (
    (),
    ("CorporateNonSegmentMember",),
    ("IntersegmentEliminationMember",),
    ("CorporateNonSegmentMember", "IntersegmentEliminationMember"),
    ("CorporateReconcilingItemsAndEliminationsMember",),
    ("SegmentReconcilingItemsMember",),
)
ITEMS_AXIS = "ConsolidationItemsAxis"
NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
    "link": "http://www.xbrl.org/2003/linkbase",
    "xlink": "http://www.w3.org/1999/xlink",
}


def filer(ticker: str) -> dict:
    return json.loads((REPO / "data" / "filers" / f"{ticker}.json").read_text())


def submissions(cik: int) -> dict:
    return json.loads((RAW / "data.sec.gov" / "submissions" / f"CIK{cik:010d}.json").read_text())


def filings(d: dict) -> dict[str, dict]:
    """name -> {accession, form, filed, report, document} for the five filings."""
    recent = submissions(int(d["cik"]))["filings"]["recent"]
    rows = [{k: recent[k][i] for k in recent} for i in range(len(recent["form"]))]
    wanted = {
        "task": ("10-Q", d["target"]["period_end"]),
        **{f"fy_q{j}": ("10-Q", d["periods"][f"FYQ{j}"][1]) for j in range(1, int(d["quarter"]))},
        "fy1_q1": ("10-Q", d["periods"]["FY-1Q1"][1]),
        "fy1_q2": ("10-Q", d["periods"]["FY-1Q2"][1]),
        "fy1_q3": ("10-Q", d["periods"]["FY-1Q3"][1]),
        "fy1_k": ("10-K", d["periods"]["FY-1"][1]),
    }
    out = {}
    for name, (form, end) in wanted.items():
        match = [r for r in rows if r["form"] == form and r["reportDate"] == end]
        if not match:
            raise LookupError(f"{d['ticker']}: no {form} for the period ended {end}")
        r = min(match, key=lambda r: r["filingDate"])  # the original, not an amendment
        out[name] = {
            "accession": r["accessionNumber"],
            "form": form,
            "filed": r["filingDate"],
            "report": r["reportDate"],
            "document": r["primaryDocument"],
        }
    return out


def base(d: dict, f: dict) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(d['cik'])}/{f['accession'].replace('-', '')}"


def instance_url(d: dict, f: dict) -> str:
    return f"{base(d, f)}/{f['document'].rsplit('.', 1)[0]}_htm.xml"


def labels_url(d: dict, f: dict) -> str:
    return f"{base(d, f)}/{f['document'].rsplit('.', 1)[0]}_lab.xml"


def local(url: str) -> Path:
    return RAW / url.split("https://", 1)[1]


def urls(tickers) -> list[str]:
    out = []
    for t in tickers:
        d = filer(t)
        fs = filings(d)
        wanted = [instance_url(d, f) for f in fs.values()] + [labels_url(d, fs["task"])]
        out += [u for u in wanted if not local(u).exists()]
    return out


def _local_name(qname: str) -> str:
    return qname.split(":", 1)[1] if ":" in qname else qname


def parse_instance(path: Path, concepts: set[str]) -> list[dict]:
    """Facts of the given concepts: value, period, and explicit dimensions (axis -> member)."""
    root = ET.parse(path).getroot()
    contexts = {}
    for ctx in root.findall("xbrli:context", NS):
        period = ctx.find("xbrli:period", NS)
        start = period.findtext("xbrli:startDate", None, NS)
        end = period.findtext("xbrli:endDate", None, NS) or period.findtext("xbrli:instant", None, NS)
        dims = {
            _local_name(m.get("dimension")): _local_name(m.text.strip())
            for m in ctx.findall(".//xbrldi:explicitMember", NS)
        }
        contexts[ctx.get("id")] = (start, end, dims)
    out = []
    for el in root:
        tag = el.tag.split("}", 1)[1] if "}" in el.tag else el.tag
        if tag not in concepts or el.get("contextRef") not in contexts or el.text is None:
            continue
        if el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
            continue
        start, end, dims = contexts[el.get("contextRef")]
        out.append({"concept": tag, "value": float(el.text), "start": start, "end": end, "dims": dims})
    return out


def member_labels(path: Path) -> dict[str, str]:
    """Member local name -> the filer's terse or standard label."""
    if not path.exists():
        return {}
    root = ET.parse(path).getroot()
    labels: dict[str, dict[str, str]] = {}
    for link in root.findall("link:labelLink", NS):
        locs = {
            loc.get(f"{{{NS['xlink']}}}label"): loc.get(f"{{{NS['xlink']}}}href").split("#", 1)[1]
            for loc in link.findall("link:loc", NS)
        }
        texts = {}
        for lab in link.findall("link:label", NS):
            role = lab.get(f"{{{NS['xlink']}}}role").rsplit("/", 1)[1]
            texts.setdefault(lab.get(f"{{{NS['xlink']}}}label"), {})[role] = (lab.text or "").strip()
        for arc in link.findall("link:labelArc", NS):
            concept = locs.get(arc.get(f"{{{NS['xlink']}}}from"), "")
            for role, text in texts.get(arc.get(f"{{{NS['xlink']}}}to"), {}).items():
                labels.setdefault(re.sub(r"^[a-z\-]+_", "", concept), {})[role] = text
    out = {}
    for name, by_role in labels.items():
        text = by_role.get("terseLabel") or by_role.get("label") or ""
        out[name] = re.sub(r"\s*\[Member\]$", "", text)
    return out


def breakdown_facts(facts: list[dict], axis: str) -> list[dict]:
    """Facts with one member on the axis and, at most, OperatingSegmentsMember on the items axis;
    and reconciling facts, with only an items-axis member (named "items:<member>")."""
    out = []
    for f in facts:
        dims = dict(f["dims"])
        member = dims.pop(axis, None)
        if member is None:
            if set(dims) == {ITEMS_AXIS} and dims[ITEMS_AXIS] != "OperatingSegmentsMember":
                out.append({**f, "member": f"items:{dims[ITEMS_AXIS]}"})
            continue
        if dims and dims != {ITEMS_AXIS: "OperatingSegmentsMember"}:
            continue
        out.append({**f, "member": member})
    return out


def screen(axis: str, d: dict, prior: dict, facts: dict[str, list[dict]]) -> dict:
    """One axis: its members, their figures in every period the task and the example read, and
    the problems that disqualify it."""
    problems: list[str] = []
    values: dict[tuple[str, str, str], dict[str, float]] = {}
    for name, rows in facts.items():
        for x in breakdown_facts(rows, axis):
            values.setdefault((x["start"], x["end"], x["member"]), {})[name] = x["value"]

    # The periods the task (d) and the example (prior) read, by their dates. The example's FY-2
    # (two years before the task) only sets its growth drivers, which an update never changes.
    needed = {}
    for data, prefix in ((d, "task"), (prior, "example")):
        for key in ("FY-1Q1", "FY-1Q2", "FY-1Q3", "FY-1", "FY-2", "FYQ1", "FYQ2", "FYQ3"):
            if key in data["periods"]:
                needed[f"{prefix}:{key}"] = tuple(data["periods"][key])
    core = [tag for tag in needed if tag != "example:FY-2"]
    member_sets = {
        tuple(sorted({m for (s, e, m) in values if (s, e) == needed[tag] and not m.startswith("items:")}))
        for tag in core
    }
    if len(member_sets) != 1 or not next(iter(member_sets)):
        problems.append(f"members differ between periods: {sorted(member_sets)[:3]}")
    elif len(next(iter(member_sets))) < 2:
        problems.append("a single row: nothing to build revenue from")
    components = list(next(iter(member_sets))) if member_sets else []

    def value(period: tuple[str, str], member: str) -> float | None:
        v = values.get((*period, member))
        return next(iter(v.values())) if v else None

    def consolidated(tag: str) -> float | None:
        data = d if tag.startswith("task") else prior
        return data["lines"]["revenue"]["values"].get(tag.split(":", 1)[1])

    def adds_up(members: list[str]) -> bool:
        for tag in core:
            row = [value(needed[tag], m) for m in members]
            if None in row or consolidated(tag) is None or abs(sum(row) - consolidated(tag)) > 0.5:
                return False
        return True

    reconciling = next(
        (list(extra) for extra in RECONCILING if adds_up(components + [f"items:{m}" for m in extra])), []
    )
    members = components + [f"items:{m}" for m in reconciling]
    recast = sorted(
        f"{m} {s}..{e}: {sorted(set(v.values()))}"
        for (s, e, m), v in values.items()
        if m in members and len(set(v.values())) > 1
    )
    if recast:
        problems.append(f"recast between filings: {recast[:2]}")
    table: dict[str, dict[str, float]] = {}
    for tag, period in needed.items():
        row = {m: value(period, m) for m in members}
        if any(x is None for x in row.values()):
            if tag != "example:FY-2":
                problems.append(f"{tag}: a figure is missing")
            continue
        table[tag] = row
        total = sum(row.values())
        if tag != "example:FY-2" and (consolidated(tag) is None or abs(total - consolidated(tag)) > 0.5):
            problems.append(f"{tag}: the rows sum to {total:,.0f}, revenue is {consolidated(tag)}")
    sources = {f"{s}..{e}|{m}": sorted(v) for (s, e, m), v in values.items() if m in members}
    return {
        "axis": axis,
        "qualified": not problems,
        "problems": problems,
        "members": members,
        "reconciling": [f"items:{m}" for m in reconciling],
        "values": table,
        "sources": sources,
    }


def extract(ticker: str) -> dict:
    d = filer(ticker)
    # The worked example: the previous fiscal year's third-quarter update for a first-quarter
    # task, the same year's previous quarter otherwise (the task's own data).
    prior = json.loads((REPO / "data" / "prior" / f"{ticker}.json").read_text()) if d["quarter"] == 1 else d
    fs = filings(d)
    revenue = d["lines"]["revenue"]
    concepts = {revenue["concept"], *revenue["by_period"].values()} - {"", None}
    missing = [name for name, f in fs.items() if not local(instance_url(d, f)).exists()]
    if missing:
        return {"ticker": ticker, "qualified": False, "problems": [f"not downloaded: {missing}"]}
    facts = {name: parse_instance(local(instance_url(d, f)), concepts) for name, f in fs.items()}
    tried = [screen(axis, d, prior, facts) for axis in AXES]
    chosen = next((r for r in tried if r["qualified"]), None)
    labels = member_labels(local(labels_url(d, fs["task"])))
    out = {
        "ticker": ticker,
        "qualified": chosen is not None,
        "problems": [f"{r['axis']}: {'; '.join(r['problems'][:2])}" for r in tried if not r["qualified"]],
        "concepts": sorted(concepts),
        "filings": fs,
    }
    if chosen is not None:
        out["page"] = breakdown_page(d, chosen)
        if out["page"] is None:
            out["qualified"] = False
            out["problems"].append("no page of the 10-Q shows every row's figure for the quarter")
        out |= {k: v for k, v in chosen.items() if k not in ("qualified", "problems")} | {
            "labels": {
                m: labels.get(m.removeprefix("items:"))
                or re.sub(r"(?<!^)(?=[A-Z])", " ", m.removeprefix("items:").removesuffix("Member"))
                for m in chosen["members"]
            },
        }
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("urls", "extract"):
        sys.exit(__doc__)
    tickers = [t.upper() for t in argv[1:]] or list(TICKERS)
    if argv[0] == "urls":
        print("\n".join(urls(tickers)))
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Revenue-breakdown screen (architecture A)",
        "",
        "Axes tried in order: business segments, geography, product or service. The first clean one is used.",
        "",
        "| ticker | axis | rows | axes that failed, and why |",
        "|---|---|---|---|",
    ]
    for t in tickers:
        r = extract(t)
        (OUT / f"{t}.json").write_text(json.dumps(r, indent=1) + "\n")
        axis = r.get("axis", "none").removesuffix("Axis") if r["qualified"] else "none"
        rows = ", ".join(r.get("labels", {}).values())
        why = " / ".join(p[:160] for p in r["problems"])
        lines.append(f"| {t} | {axis} | {rows} | {why} |")
    (OUT / "screen.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def note_candidates(d: dict) -> list[str]:
    """The task 10-Q's detail pages that could hold the revenue breakdown, by their names."""
    from filing_update_evals.rpages import statement_reports  # noqa: F401  (FilingSummary parsing lives there)

    base_url = d["target"]["url"]
    xml = local(f"{base_url}/FilingSummary.xml").read_text()
    reports = re.findall(
        r"<HtmlFileName>(R\d+\.htm)</HtmlFileName>.*?<ShortName>(.*?)</ShortName>", xml, re.S
    )
    return [
        f"{base_url}/{file}"
        for file, name in reports
        if re.search(r"segment|disaggreg|geograph", name, re.I)
        and "Details" in name
        and "Narrative" not in name
    ]


def breakdown_page(d: dict, breakdown: dict) -> str | None:
    """The candidate page whose table shows every row's figure for the new quarter."""
    from filing_update_evals.rpages import parse_rpage

    key = f"FYQ{d['quarter']}"
    figures = breakdown["values"][f"task:{key}"]
    for url in note_candidates(d):
        path = local(url)
        if not path.exists():
            continue
        table = parse_rpage(path.read_bytes())
        shown = {
            round(abs(float(re.sub(r"[^\d.]", "", c))) * table.scale, 0)
            for _, cells in table.rows
            for c in cells
            if re.search(r"\d", c)
        }
        if all(round(abs(v), 0) in shown for v in figures.values()):
            return url.rsplit("/", 1)[1]
    return None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
