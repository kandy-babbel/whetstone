#!/usr/bin/env python3
"""Write one evidence file per blocking finding of the current round and print the list.

Output (stdout, JSON, also written to .review/current/triage-items.json):
  {"items": [{"id": "FINDING-1", "evidence": ".review/current/triage-evidence/FINDING-1.json"}]}
Only files tracked by git are read: the reviewer writes each finding's path, and the
evidence leaves the machine, so an untracked, ignored or outside path is never excerpted.
The evidence holds the finding, the code around it at HEAD, the CI check steps, and the
repository's rules and tool configs named in whetstone-triage-config.yml
(scaffolded by Spec Kit next to this extension; owned by the repository). Paths stay inside the
project, as the decision step requires.
"""
import json, re, subprocess, sys
from pathlib import Path
import yaml

if not __import__("os").environ.get("TYPESAFE_API_KEY"):
    sys.exit("TYPESAFE_API_KEY is not set; the decision step's Jev backend needs it")
CUR = Path(".review/current")
CONFIG = Path(__file__).resolve().parent.parent / "whetstone-triage-config.yml"
if not CONFIG.exists():
    sys.exit(f"{CONFIG} missing; copy whetstone-triage-config.template.yml there and edit it")
cfg = {"rule_files": [], "config_files": [], "ci_workflow": "", "ci_run_prefixes": [], "context_lines": 20,
       **(yaml.safe_load(CONFIG.read_text()) or {})}
findings = json.loads((CUR / "findings.json").read_text())["findings"]
blocking = [f for f in findings if f["severity"] in ("Critical", "Important")]
out = CUR / "triage-evidence"
out.mkdir(exist_ok=True)


TRACKED = set(p for p in subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True,
                                          text=True).stdout.split("\0") if p)


def tracked(p):
    return isinstance(p, str) and p in TRACKED and Path(p).is_file()


def read(p):
    return Path(p).read_text(errors="replace") if tracked(p) else f"(not a tracked file: {p})"


def excerpt(path, line, n):
    p = Path(path)
    if not tracked(path):
        return f"(not a tracked file at HEAD: {path})"
    lines = p.read_text(errors="replace").splitlines()
    lo, hi = max(0, line - 1 - n), min(len(lines), line + n)
    return "\n".join(f"{i + 1:5}{'>' if i + 1 == line else ' '} {lines[i]}" for i in range(lo, hi))


prefixes = "|".join(re.escape(p) for p in cfg["ci_run_prefixes"])
ci = "\n".join(l.strip() for l in read(cfg["ci_workflow"]).splitlines()
               if re.match(r"\s+- name: .*(check|test|lint|format)", l, re.I)
               or (prefixes and re.match(rf"\s+run: ({prefixes})\b", l))) if cfg["ci_workflow"] else "(no CI workflow configured)"
rules = {p: read(p) for p in cfg["rule_files"]}
configs = {p: read(p) for p in cfg["config_files"]}
items = []
for f in blocking:
    ev = {"finding": {k: f[k] for k in ("id", "severity", "category", "file", "line_start", "description", "rationale", "fix")},
          "code": excerpt(f["file"], f["line_start"], cfg["context_lines"]),
          "ci_checks": ci, "repo_rules": rules, "tool_configs": configs}
    p = out / f"{f['id']}.json"
    p.write_text(json.dumps(ev, indent=1))
    items.append({"id": f["id"], "evidence": str(p)})
(CUR / "triage-items.json").write_text(json.dumps({"items": items}, indent=1) + "\n")
print(json.dumps({"items": items}))
