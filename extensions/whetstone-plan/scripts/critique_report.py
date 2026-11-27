#!/usr/bin/env python3
"""Find the critique report this run wrote.

    critique_report.py mark <spec folder> <baseline>   # before the critique step: record the reports already on disk
    critique_report.py find <spec folder> <baseline>   # after it: print {"path": ...} for the one report that is new

A re-scoped spec folder keeps earlier runs' reports, and report names are not guaranteed to sort by
run, so the newest name is not evidence of this run's report. The baseline is a file in the run's own
folder under `.specify/workflows/runs/`: anywhere else under `.specify/` it would be a stray file that
stops the next Whetstone review, where the review is installed too.
"""
import json
import sys
from pathlib import Path


def _reports(feature):
    return feature / "critiques", {str(p) for p in (feature / "critiques").glob("critique-*.md")}


def mark(feature, baseline):
    _, existing = _reports(feature)
    baseline.write_text(json.dumps(sorted(existing)))


def find(feature, baseline):
    if not baseline.is_file():
        sys.exit(f"no {baseline}: the mark step did not run before critique")
    folder, now = _reports(feature)
    new = sorted(now - set(json.loads(baseline.read_text())))
    if len(new) != 1:
        sys.exit(f"critique wrote no report under {folder}" if not new
                 else f"critique wrote {len(new)} reports under {folder}: {', '.join(new)}")
    print(json.dumps({"path": new[0]}))


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("mark", "find"):
        sys.exit(__doc__)
    {"mark": mark, "find": find}[sys.argv[1]](Path(sys.argv[2]), Path(sys.argv[3]))
