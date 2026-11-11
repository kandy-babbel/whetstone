#!/usr/bin/env python3
"""Deterministic core of Whetstone.

Modules exchange files under .review/current/, each checked against its JSON
Schema in ../schemas/. A module that is switched off writes no file; this script
then applies that module's documented fallback. Every subcommand prints one
JSON object (read by Spec Kit with output_format: json) and exits 1 when a
contract is broken, which fails the step and the run.

Run with: uv run --no-project --with jsonschema==4.26.0 --with pyyaml==6.0.2 python3 whetstone.py <cmd>
Repository settings: whetstone-core-config.yml next to this extension (base_ref).

  setup         check the working tree, archive an earlier run, record the base commit, start the ledger
  begin-round   archive the previous round, start a new one, list the PR's files
  validate      validate one file against one schema: validate <schema> <file>
  summarize     validate findings (+ triage if present), count actionable findings
  check-apply   validate shim-check (if present) and decisions, check them against the code, commit
  finish        write .review/report.json: dismissed, rejected, deferred, follow-ups, warnings
"""
import datetime, json, os, shutil, subprocess, sys, time
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

R = Path(".review")
CUR = R / "current"
EXT = Path(__file__).resolve().parent.parent
SCHEMAS = EXT / "schemas"
CONFIG = EXT / "whetstone-core-config.yml"
BLOCKING = {"Critical", "Important"}


def out(obj, code=0):
    print(json.dumps(obj))
    sys.exit(code)


def fail(msg, **extra):
    print(f"CONTRACT VIOLATION: {msg}", file=sys.stderr)
    out({"valid": False, "error": msg, **extra}, 1)


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def git_paths(*args):
    """Paths from a git command run with -z, so names with spaces or non-ASCII characters survive."""
    out_ = subprocess.run(["git", *args, "-z"], check=True, capture_output=True, text=True).stdout
    return [p for p in out_.split("\0") if p]


def round_no():
    return int((R / "round").read_text())


_registry = None


def validate(schema_name, path, fresh=True):
    """Return the document at path after checking it is fresh, strict JSON and schema-valid."""
    global _registry
    if _registry is None:
        resources = []
        for p in SCHEMAS.glob("*.schema.json"):
            s = json.loads(p.read_text())
            resources.append((s["$id"], Resource.from_contents(s, default_specification=DRAFT202012)))
        _registry = Registry().with_resources(resources)
    if not path.exists():
        fail(f"{path} missing (the step that should write it wrote nothing)")
    if fresh and path.stat().st_mtime < float((CUR / ".started").read_text()):
        fail(f"{path} is older than this round")

    def bad_const(c):
        raise ValueError(f"non-standard JSON constant {c}")
    try:
        doc = json.loads(path.read_text(), parse_constant=bad_const)
    except ValueError as e:
        fail(f"{path} is not strict JSON: {e}")
    schema = json.loads((SCHEMAS / schema_name).read_text())
    errors = sorted(Draft202012Validator(schema, registry=_registry).iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        fail(f"{path} does not match {schema_name}: " + "; ".join(
            f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors[:5]))
    if doc.get("round") not in (None, round_no()):
        fail(f"{path}: round {doc.get('round')} but this is round {round_no()}")
    return doc


def ledger():
    return json.loads((R / "ledger.json").read_text())


def save_ledger(l):
    (R / "ledger.json").write_text(json.dumps(l, indent=2) + "\n")


def record(l, key, entry):
    """Append to the ledger once: a retried or resumed step does not record the same entry twice."""
    ident = (entry.get("round"), entry.get("finding_id"), entry.get("file"))
    if not any((e.get("round"), e.get("finding_id"), e.get("file")) == ident for e in l.setdefault(key, [])):
        l[key].append(entry)


def setup():
    if not CONFIG.exists():
        fail(f"{CONFIG} missing; copy whetstone-core-config.template.yml there and set base_ref")
    base_ref = (yaml.safe_load(CONFIG.read_text()) or {}).get("base_ref")
    if not isinstance(base_ref, str) or not base_ref:
        fail(f"{CONFIG}: base_ref must be a non-empty string")
    # Triage sends evidence to the decision backend; without a key it would fail after a paid review.
    if os.environ.get("WHETSTONE_TRIAGE", "").split("=")[-1].lower() == "true" and not os.environ.get("TYPESAFE_API_KEY"):
        fail("triage is on but TYPESAFE_API_KEY is not set; set it, or run with --input triage=false")
    # Each round commits with `git add -A` and refuses changes no fix claims, so the run must start clean.
    if subprocess.run(["git", "check-ignore", "-q", ".review/x"]).returncode != 0:
        fail(".review/ is not ignored by git; add `.review/` to .gitignore")
    dirty = git_paths("status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        fail("the working tree is not clean; commit or ignore these first (a Spec Kit install creates "
             f"files under .specify/ and .claude/ to commit, and caches to ignore): {dirty[:10]}")
    R.mkdir(exist_ok=True)
    # A new run starts fresh: an earlier run's base, ledger and rounds move to .review/previous/.
    earlier = [p for p in R.iterdir() if p.name != "previous"]
    if earlier:
        dest = R / "previous" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        dest.mkdir(parents=True)
        for p in earlier:
            shutil.move(str(p), str(dest / p.name))
    try:
        base = git("merge-base", base_ref, "HEAD")
    except subprocess.CalledProcessError as e:
        fail(f"git merge-base {base_ref} HEAD failed ({e.stderr.strip() or e.returncode}); "
             f"set base_ref in {CONFIG} to the branch pull requests merge into")
    (R / "base").write_text(base + "\n")
    save_ledger({"dismissed": [], "rejected": [], "deferred": [], "clarify": [], "follow_ups": [], "warnings": []})
    (R / "round").write_text("0\n")
    out({"valid": True, "base": base, "base_ref": base_ref, "head": git("rev-parse", "HEAD")})


def begin_round():
    n = round_no() + 1
    if CUR.exists():
        shutil.move(str(CUR), str(R / "history" / f"round-{n - 1}"))
    CUR.mkdir(parents=True)
    (R / "round").write_text(f"{n}\n")
    (CUR / ".started").write_text(f"{time.time()}\n")
    base = (R / "base").read_text().strip()
    files = git_paths("diff", "--name-only", f"{base}...HEAD")
    (CUR / "pr-files.txt").write_text("\n".join(files) + "\n")
    out({"valid": True, "round": n, "head": git("rev-parse", "HEAD"), "pr_files": len(files)})


def summarize():
    n = round_no()
    f = validate("findings.schema.json", CUR / "findings.json")
    if f["base"] != (R / "base").read_text().strip():
        fail(f"findings.json base {f['base']} is not the loop's base")
    ids = [x["id"] for x in f["findings"]]
    if len(ids) != len(set(ids)):
        fail("findings.json has duplicate finding ids")
    blocking = [x["id"] for x in f["findings"] if x["severity"] in BLOCKING]
    dismissed, triage_used = [], (CUR / "triage.json").exists()
    if triage_used:  # fallback when triage is off: nothing is dismissed
        t = validate("triage.schema.json", CUR / "triage.json")
        by = {r["finding_id"]: r for r in t["results"]}
        missing = [i for i in blocking if i not in by]
        if missing:
            fail(f"triage.json has no result for blocking findings {missing}")
        dismissed = [i for i in blocking if by[i]["dismissed"]]
        l = ledger()
        for i in dismissed:
            x = next(y for y in f["findings"] if y["id"] == i)
            record(l, "dismissed", {"round": n, "finding_id": i, "file": x["file"], "description": x["description"],
                                   "p_bikeshedding": by[i]["p_bikeshedding"], "basis": by[i]["basis"]})
        save_ledger(l)
    actionable = [i for i in blocking if i not in dismissed]
    summary = {"valid": True, "round": n, "findings": len(ids), "blocking": len(blocking),
               "dismissed": len(dismissed), "actionable": len(actionable), "triage_used": triage_used,
               "agents_run": f["agents_run"]}
    (CUR / "summary.json").write_text(json.dumps({**summary, "actionable_ids": actionable,
                                                  "dismissed_ids": dismissed}, indent=2) + "\n")
    out(summary)


def check_apply():
    n = round_no()
    summary = json.loads((CUR / "summary.json").read_text())
    actionable = summary["actionable_ids"]
    pr_files = set((CUR / "pr-files.txt").read_text().splitlines()) - {""}
    shim = {}
    if (CUR / "shim-check.json").exists():  # fallback when the shim check is off: every finding is a local fix
        s = validate("shim-check.schema.json", CUR / "shim-check.json")
        shim = {r["finding_id"]: r for r in s["results"]}
        missing = [i for i in actionable if i not in shim]
        if missing:
            fail(f"shim-check.json has no result for actionable findings {missing}")
        for r in shim.values():
            for o in r["occurrences"]:
                if o["in_pr"] != (o["file"] in pr_files):
                    fail(f"shim-check.json {r['finding_id']}: {o['file']} in_pr={o['in_pr']} contradicts the PR's file list")
    d = validate("decisions.schema.json", CUR / "decisions.json")
    by = {x["finding_id"]: x for x in d["decisions"]}
    missing = [i for i in actionable if i not in by]
    if missing:
        fail(f"decisions.json has no decision for {missing}")
    new_files = set(git_paths("ls-files", "--others", "--exclude-standard"))
    changed = set(git_paths("diff", "--name-only", "HEAD")) | new_files
    # The PR boundary holds for the whole working tree, whatever decisions.json lists:
    # only files the PR already touches may change; new files (e.g. a new test) are allowed.
    outside = sorted(changed - new_files - pr_files)
    if outside:
        fail(f"existing files outside the PR changed {outside}; those must be follow-ups")
    claimed_all = set()
    for i in actionable:
        x = by[i]
        claimed = set(x["files_changed"])
        if x["decision"] == "fix":
            if not claimed:
                fail(f"{i}: decision fix lists no files_changed")
            if not claimed <= changed:
                fail(f"{i}: files_changed {sorted(claimed - changed)} are not changed in the working tree")
            claimed_all |= claimed
        elif claimed:
            fail(f"{i}: decision {x['decision']} lists files_changed {sorted(claimed)}")
    # Every change must belong to a fix decision; nothing unclaimed is committed.
    unclaimed = sorted(changed - claimed_all)
    if unclaimed:
        fail(f"changed files no fix decision claims {unclaimed}")
    # Not checkable from files (a test-coverage fix lands in a test file, a shared cause may be
    # fixed once): a class fix that left an in-PR occurrence's file untouched is reported, not failed.
    warnings = []
    for i in actionable:
        if by[i]["decision"] == "fix" and i in shim and shim[i]["strategy"] == "class_fix":
            untouched = sorted({o["file"] for o in shim[i]["occurrences"] if o["in_pr"]} - set(by[i]["files_changed"]))
            if untouched:
                warnings.append({"round": n, "finding_id": i, "warning":
                                 f"class_fix left in-PR occurrence files untouched {untouched}; see the decision's reason"})
    l = ledger()
    for w in warnings:
        record(l, "warnings", w)
    for i in actionable:
        x = by[i]
        if x["decision"] in ("reject", "defer", "clarify"):
            key = {"reject": "rejected", "defer": "deferred", "clarify": "clarify"}[x["decision"]]
            record(l, key, {"round": n, "finding_id": i, "reason": x["reason"]})
        # Follow-ups only from findings judged right (fixed here or deferred), not rejected or open.
        if i in shim and x["decision"] in ("fix", "defer"):
            for o in shim[i]["occurrences"]:
                if not o["in_pr"]:
                    record(l, "follow_ups", {"round": n, "finding_id": i, "defect_class": shim[i]["defect_class"],
                                            "file": o["file"], "line_start": o["line_start"]})
    save_ledger(l)
    commit = None
    if changed:
        git("add", "-A")
        # The repository's commit hooks run (no --no-verify): a hook that rejects the fixes stops the loop.
        c = subprocess.run(["git", "-c", "user.name=whetstone", "-c", "user.email=whetstone@localhost",
                            "commit", "-q", "-m", f"whetstone round {n}: fixes"], capture_output=True, text=True)
        if c.returncode != 0:
            fail(f"git commit failed, probably a commit hook; the fixes are staged, not committed: "
                 f"{(c.stderr or c.stdout).strip()[-1500:]}")
        commit = git("rev-parse", "HEAD")
    counts = {k: sum(1 for i in actionable if by[i]["decision"] == k) for k in ("fix", "reject", "defer", "clarify")}
    checks = json.loads((CUR / "checks.json").read_text()) if (CUR / "checks.json").exists() else None
    out({"valid": True, "round": n, "shim_check_used": bool(shim), **counts, "warnings": len(warnings),
         "checks": checks, "commit": commit})


def finish():
    l = ledger()
    report = {"rounds": round_no(), **{k: l[k] for k in l},
              "final": json.loads((CUR / "summary.json").read_text()) if (CUR / "summary.json").exists() else None}
    (R / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    out({"valid": True, "rounds": report["rounds"], **{k: len(l[k]) for k in l}})


def validate_cmd():
    validate(sys.argv[2], Path(sys.argv[3]), fresh=False)
    out({"valid": True})


if __name__ == "__main__":
    {"setup": setup, "begin-round": begin_round, "validate": validate_cmd, "summarize": summarize,
     "check-apply": check_apply, "finish": finish}[sys.argv[1]]()
