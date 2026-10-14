"""Write the firm-memory experiment's worked examples, experiments/prior/<task>.md, one per
generated task. Offline.

Usage: scripts/guarded .venv/bin/python -I scripts/prior_examples.py
"""

from __future__ import annotations

from filing_update_evals.netguard import install

install()  # offline: loopback only, even when run with python -I

import json
import sys
from pathlib import Path

from filing_update_evals.prior_update import EXAMPLES, load_year_earlier, prior_update, render
from filing_update_evals.tasks import load_specs

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    for spec in load_specs():
        if spec.group != "xbrl":
            continue
        data = json.loads((REPO / "data" / "filers" / f"{spec.filer}.json").read_text())
        update = prior_update(data, spec.style, load_year_earlier(spec.filer))
        text = render(update)
        (EXAMPLES / f"{spec.id}.md").write_text(text)
        print(
            f"{spec.id}: Q{update.quarter} FY{update.data['fy']}, {len(update.changed)} cells, "
            f"{len(text):,} characters"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
