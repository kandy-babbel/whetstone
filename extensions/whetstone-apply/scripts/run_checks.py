#!/usr/bin/env python3
"""Run the checks in whetstone-apply-config.yml after the apply agent, and fail if any fails.

The agent reports its own test results in decisions.json; this step does not rely on them.
Writes .review/current/checks.json: {"checks": [{"cmd", "exit_code", "passed", "output_tail"}], "passed"}.
Each command runs from the repository root through the shell, with a 30-minute limit.
"""
import json, subprocess, sys
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "whetstone-apply-config.yml"
if not CONFIG.exists():
    sys.exit(f"{CONFIG} missing; copy whetstone-apply-config.template.yml there and edit it")
cmds = (yaml.safe_load(CONFIG.read_text()) or {}).get("checks") or []
if not isinstance(cmds, list) or not all(isinstance(c, str) and c.strip() for c in cmds):
    sys.exit(f"{CONFIG}: checks must be a list of commands")
results = []
for cmd in cmds:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=1800)
        code, output = r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired as e:
        code, output = -1, f"timed out after 1800 s\n{e.stdout or ''}{e.stderr or ''}"
    results.append({"cmd": cmd, "exit_code": code, "passed": code == 0, "output_tail": output[-2000:]})
doc = {"passed": all(r["passed"] for r in results), "checks": results}
Path(".review/current/checks.json").write_text(json.dumps(doc, indent=2) + "\n")
failed = [r["cmd"] for r in results if not r["passed"]]
if failed:
    for r in results:
        if not r["passed"]:
            print(f"CHECK FAILED: {r['cmd']} (exit {r['exit_code']})\n{r['output_tail']}", file=sys.stderr)
print(json.dumps({"valid": not failed, "checks": len(results), "failed": failed}))
sys.exit(1 if failed else 0)
