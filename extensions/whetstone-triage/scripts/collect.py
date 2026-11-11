#!/usr/bin/env python3
"""Turn the fan-out decision results into .review/current/triage.json.

Reads gather's item list from .review/current/triage-items.json.
Env: RESULTS (the fan-out's ordered results, JSON),
THRESHOLD (number), BACKEND (name for the record). Validation happens in the next step.
"""
import json, os
from pathlib import Path

items = json.loads(Path(".review/current/triage-items.json").read_text())["items"]
results = json.loads(os.environ["RESULTS"])
threshold = float(os.environ["THRESHOLD"].split("=")[-1])
if len(items) != len(results):
    raise SystemExit(f"{len(items)} findings but {len(results)} decision results")
rows = []
for it, r in zip(items, results):
    p = r["bikeshedding"]["noul"]
    basis = r["basis"]["choice"]
    rows.append({"finding_id": it["id"], "p_bikeshedding": p, "basis": basis,
                 "basis_probabilities": r["basis"].get("probabilities", {}),
                 "dismissed": p >= threshold and basis == "taste"})
doc = {"schema_version": "whetstone.triage/1", "round": int(Path(".review/round").read_text()),
       "backend": os.environ.get("BACKEND", "decision"), "threshold": threshold, "results": rows}
Path(".review/current/triage.json").write_text(json.dumps(doc, indent=2) + "\n")
print(json.dumps({"valid": True, "results": len(rows), "dismissed": sum(r["dismissed"] for r in rows)}))
