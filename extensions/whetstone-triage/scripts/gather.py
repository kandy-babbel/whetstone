#!/usr/bin/env python3
"""Write one evidence file per blocking finding of the current round and print the list.

Output (stdout, JSON, also written to .review/current/triage-items.json):
  {"items": [{"id": "FINDING-1", "evidence": ".review/current/triage-evidence/FINDING-1.json"}]}
Only files tracked by git are read: the reviewer writes each finding's path, and the
evidence leaves the machine, so an untracked, ignored or outside path is never excerpted.
The evidence holds the finding, the code around it at HEAD, the CI check steps, the repository's
conventions as `setup` recorded them from the base commit (.review/current/conventions/: every
CLAUDE.md and .claude/rules/), and the rules and tool configs named in whetstone-triage-config.yml
(scaffolded by Spec Kit next to this extension; owned by the repository). Paths stay inside the
project, as the decision step requires. The repository is the working directory, or the clone
under repo/ when `setup` recorded that layout in .review/root (the harness layout).
"""
import json, os, re, subprocess, sys
from pathlib import Path
import yaml

if not os.environ.get("TYPESAFE_API_KEY"):
    sys.exit("TYPESAFE_API_KEY is not set; the decision step's Jev backend needs it")
CUR = Path(".review/current")
ROOT = Path((Path(".review/root").read_text().strip() if Path(".review/root").exists() else "."))
CONFIG = Path(__file__).resolve().parent.parent / "whetstone-triage-config.yml"
if not CONFIG.exists():
    sys.exit(f"{CONFIG} missing; copy whetstone-triage-config.template.yml there and edit it")
cfg = {"rule_files": [], "config_files": [], "ci_workflow": "", "ci_run_prefixes": [], "context_lines": 20,
       **(yaml.safe_load(CONFIG.read_text()) or {})}
findings = json.loads((CUR / "findings.json").read_text())["findings"]
blocking = [f for f in findings if f["severity"] in ("Critical", "Important")]
out = CUR / "triage-evidence"
out.mkdir(exist_ok=True)

GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_OPTIONAL_LOCKS": "0"}
TRACKED = set(p for p in subprocess.run(["git", "-C", str(ROOT), "-c", "core.hooksPath=/dev/null", "-c",
                                          "core.fsmonitor=false", "ls-files", "-z"], check=True,
                                         capture_output=True, text=True, env=GIT_ENV).stdout.split("\0") if p)


def tracked(p):
    return isinstance(p, str) and p in TRACKED and (ROOT / p).is_file() and not (ROOT / p).is_symlink()


def read(p):
    return (ROOT / p).read_text(errors="replace") if tracked(p) else f"(not a tracked file: {p})"


def excerpt(path, line, n):
    if not tracked(path):
        return f"(not a tracked file at HEAD: {path})"
    lines = (ROOT / path).read_text(errors="replace").splitlines()
    lo, hi = max(0, line - 1 - n), min(len(lines), line + n)
    return "\n".join(f"{i + 1:5}{'>' if i + 1 == line else ' '} {lines[i]}" for i in range(lo, hi))


prefixes = "|".join(re.escape(p) for p in cfg["ci_run_prefixes"])
ci = "\n".join(l.strip() for l in read(cfg["ci_workflow"]).splitlines()
               if re.match(r"\s+- name: .*(check|test|lint|format)", l, re.I)
               or (prefixes and re.match(rf"\s+run: ({prefixes})\b", l))) if cfg["ci_workflow"] else "(no CI workflow configured)"
rules, sources = {}, set()
for line in ((CUR / "conventions.txt").read_text().splitlines() if (CUR / "conventions.txt").exists() else []):
    if line and not line.startswith("# "):
        name, _, source = line.partition(" -> ")
        rules[name] = (CUR / "conventions" / name).read_text(errors="replace")
        sources.add(source or name)
rules.update({p: read(p) for p in cfg["rule_files"] if p not in sources})  # a file setup already copied is not sent twice
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
