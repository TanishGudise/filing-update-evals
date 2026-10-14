"""One entry point for every model: the base model (model.py) in its three layouts (S1-S3), and
the structurally different architectures (arch_a.py). The generator, the worked examples and the
checks build models through here."""

from __future__ import annotations

from filing_update_evals import arch_a
from filing_update_evals import model as M
from filing_update_evals import styles as S

ARCHITECTURES = {arch_a.STYLE: "segment-driven revenue"}


def prepare(data: dict, style: str, which: str = "task") -> dict:
    """The filer data with what the architecture needs beyond the statements. which: "task", or
    "example" for a first-quarter task's year-earlier data."""
    if style == arch_a.STYLE:
        return arch_a.with_breakdown(data, arch_a.load_breakdown(data["ticker"]), which)
    return data


def logical(data: dict, style: str, last: int) -> M.Logical:
    if style == arch_a.STYLE:
        return arch_a.build(data, last)
    return M.build(data, last, style == "S3")


def layout(style: str, data: dict) -> S.Layout:
    if style == arch_a.STYLE:
        return arch_a.layout(data)
    return S.layout(style, data)
