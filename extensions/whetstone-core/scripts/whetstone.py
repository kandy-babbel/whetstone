#!/usr/bin/env python3
"""Deterministic core of Whetstone.

Modules exchange files under .review/current/, each checked against its JSON Schema in ../schemas/. Agents answer
on standard output; `fetch` takes an answer from Spec Kit's run state into .review/current/. A module that is
switched off writes no file; this script then applies that module's documented fallback. Every subcommand prints one
JSON object (read by Spec Kit with output_format: json) and exits 1 when a contract is broken, which fails the step
and the run. Whetstone changes nothing in the repository: it writes only .review/.

Run with: uv run --isolated --no-config --no-project --with jsonschema==4.26.0 --with pyyaml==6.0.2 python3 -I whetstone.py <cmd>
Repository settings: whetstone-core-config.yml next to this extension (base_ref).

  setup                      check the lockdown, TMPDIR and the integrity of .claude/ and .specify/; archive an earlier
                             run; record the base commit and the change's files; start the ledger
  guard                      before every agent step: the lockdown flags and the integrity check again
  fetch <file> --command C [--args A] | --prompt P
                             after an agent step: its answer, taken from the run state into .review/current/<file>
  canary-open                a nonce for the canary agent
  canary-check               the canary agent must have run its script with that nonce, and no protected path may
                             have been written
  validate <schema> <file>   validate one file against one schema
  summarize                  validate findings (+ triage if present), count actionable findings
  report                     write .review/report.json; say whether a person must look (WRONG, unread, unjudged claims)
  finish                     record the gate's answer, if there was one
"""
import datetime, json, os, shutil, subprocess, sys, time
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

sys.dont_write_bytecode = True  # no __pycache__ under .specify/: it would fail the integrity check
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lockdown, runstate  # noqa: E402

R = Path(".review")
CUR = R / "current"
EXT = Path(__file__).resolve().parent.parent
SCHEMAS = EXT / "schemas"
CONFIG = EXT / "whetstone-core-config.yml"
BLOCKING = {"Critical", "Important"}
CANARY_COMMAND = "speckit.whetstone-core.canary"
LEDGER_KEYS = ("dismissed", "follow_ups", "warnings", "claims_wrong", "claim_notes", "unread", "unjudged", "gate")


def out(obj, code=0):
    print(json.dumps(obj))
    sys.exit(code)


def fail(msg, **extra):
    print(f"CONTRACT VIOLATION: {msg}", file=sys.stderr)
    out({"valid": False, "error": msg, **extra}, 1)


git = lockdown.git


def git_paths(*args):
    """Paths from a git command run with -z, so names with spaces or non-ASCII characters survive."""
    out_ = subprocess.run(lockdown.git_cmd(*args, "-z"), check=True, capture_output=True, text=True,
                          env=lockdown.git_env()).stdout
    return [p for p in out_.split("\0") if p]


def round_no():
    p = R / "round"
    return int(p.read_text()) if p.exists() else 0  # 0: a module run on its own, with no setup step


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
        fail(f"{path} is older than this run")

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
    def ident(e):
        return e.get("finding_id"), e.get("file"), e.get("line_start"), e.get("claim_id"), e.get("reason")
    if not any(ident(e) == ident(entry) for e in l.setdefault(key, [])):
        l[key].append(entry)


def lockdown_errors(*, fresh_tmpdir=False):
    return lockdown.agent_flag_errors() + lockdown.tmpdir_errors(fresh=fresh_tmpdir) + lockdown.integrity_errors()


def guard():
    errors = lockdown_errors()
    if errors:
        fail("agents would not run locked down: " + "; ".join(errors))
    out({"valid": True})


def changed_files(base):
    """The files the change under review touches: committed since base, changed in the working tree, or new."""
    found = set(git_paths("diff", "--name-only", base)) | set(git_paths("ls-files", "--others", "--exclude-standard"))
    return sorted(found)


def setup():
    errors = lockdown_errors(fresh_tmpdir=True)
    if errors:
        fail("the lockdown is not in place (see the README's Install section): " + "; ".join(errors))
    if not CONFIG.exists():
        fail(f"{CONFIG} missing; copy whetstone-core-config.template.yml there and set base_ref")
    base_ref = (yaml.safe_load(CONFIG.read_text()) or {}).get("base_ref")
    if not isinstance(base_ref, str) or not base_ref:
        fail(f"{CONFIG}: base_ref must be a non-empty string")
    # Triage sends evidence to the decision backend; without a key it would fail after a paid review.
    if os.environ.get("WHETSTONE_TRIAGE", "").split("=")[-1].lower() == "true" and not os.environ.get("TYPESAFE_API_KEY"):
        fail("triage is on but TYPESAFE_API_KEY is not set; set it, or run with --input triage=false")
    for d in (".review/", ".specify/workflows/runs/"):
        if subprocess.run(lockdown.git_cmd("check-ignore", "-q", d + "x"), env=lockdown.git_env()).returncode != 0:
            fail(f"{d} is not ignored by git; add `{d}` to .gitignore")
    R.mkdir(exist_ok=True)
    # A new run starts fresh: an earlier run's files move to .review/previous/.
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
    (R / "run-id").write_text(runstate.run_id() + "\n")  # later steps refuse to touch another run's files
    save_ledger({k: [] for k in LEDGER_KEYS})
    (R / "round").write_text("1\n")
    CUR.mkdir(parents=True)
    (CUR / ".started").write_text(f"{time.time()}\n")
    files = changed_files(base)
    (CUR / "pr-files.txt").write_text("".join(f + "\n" for f in files))
    out({"valid": True, "base": base, "base_ref": base_ref, "head": git("rev-parse", "HEAD"), "changed_files": len(files)})


def _find(argv):
    if "--command" in argv:
        command = argv[argv.index("--command") + 1]
        args = argv[argv.index("--args") + 1] if "--args" in argv else None
        return runstate.find(command=command, args=args)
    if "--prompt" in argv:
        return runstate.find(prompt=argv[argv.index("--prompt") + 1])
    fail("fetch needs --command C [--args A] or --prompt P")


def fetch():
    name = sys.argv[2]
    if "/" in name or name.startswith("."):
        fail(f"fetch: {name} is not a plain file name")
    rec, err = _find(sys.argv[3:])
    doc, err = runstate.answer(rec, "the agent step") if rec else (None, err)
    if err:
        fail(f"no answer to take: {err}")
    CUR.mkdir(parents=True, exist_ok=True)
    (CUR / name).write_text(json.dumps(doc, indent=2) + "\n")
    out({"valid": True, "file": str(CUR / name)})


def canary_targets(nonce):
    return [f"canary-{nonce}", f".git/canary-{nonce}", f".review/canary-{nonce}", f".specify/canary-{nonce}",
            f".claude/canary-{nonce}", os.path.expanduser(f"~/.claude/canary-{nonce}")]


def canary_open():
    import secrets
    R.mkdir(exist_ok=True)
    nonce = secrets.token_hex(8)
    (R / "canary-nonce").write_text(nonce + "\n")
    out({"valid": True, "nonce": nonce})


def canary_check():
    nonce = (R / "canary-nonce").read_text().strip()
    expected = canary_targets(nonce)
    # The paths come from the nonce, never from the agent: an agent cannot make this step delete anything else.
    leaked = [t for t in expected if os.path.lexists(t)]
    for t in leaked:
        Path(t).unlink()
    if leaked:
        fail(f"an agent's command could write protected paths {leaked}: the sandbox is not in effect")
    rec, err = runstate.find(command=CANARY_COMMAND, args=nonce)
    doc, err = runstate.answer(rec, "the canary") if rec else (None, err)
    if err:
        fail(f"the canary agent did not report: {err}")
    if not isinstance(doc, dict) or doc.get("nonce") != nonce or not isinstance(doc.get("results"), dict):
        fail("the canary agent did not run its script (its answer does not carry this run's nonce)")
    if sorted(doc["results"]) != sorted(expected):
        fail("the canary agent's answer does not list the script's paths; it did not run the script as it is")
    if any(doc["results"].values()):
        fail(f"the canary could write {[p for p, w in doc['results'].items() if w]}: the sandbox is not in effect")
    out({"valid": True, "protected_paths_checked": len(expected)})


def summarize():
    runstate.bound_run_id()
    n = round_no()
    f = validate("findings.schema.json", CUR / "findings.json")
    if f["base"] != (R / "base").read_text().strip():
        fail(f"findings.json base {f['base']} is not this run's base")
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


def report():
    """Everything a person needs from this run, in .review/report.json; and the gate's text, if a person must look."""
    runstate.bound_run_id()
    n = round_no()
    clean = lockdown.clean_text
    l = ledger()
    summary = json.loads((CUR / "summary.json").read_text()) if (CUR / "summary.json").exists() else None
    pr_files = set((CUR / "pr-files.txt").read_text().splitlines()) - {""}
    shim = None
    if (CUR / "shim-check.json").exists():  # fallback when the shim check is off: no classes, no follow-ups
        s = validate("shim-check.schema.json", CUR / "shim-check.json")
        shim = {r["finding_id"]: r for r in s["results"]}
        actionable = summary["actionable_ids"] if summary else []
        missing = [i for i in actionable if i not in shim]
        if missing:
            fail(f"shim-check.json has no result for actionable findings {missing}")
        for r in shim.values():
            for o in r["occurrences"]:
                if o["in_pr"] != (o["file"] in pr_files):
                    fail(f"shim-check.json {r['finding_id']}: {o['file']} in_pr={o['in_pr']} contradicts the change's file list")
                if not o["in_pr"]:
                    record(l, "follow_ups", {"round": n, "finding_id": r["finding_id"], "defect_class": r["defect_class"],
                                            "file": o["file"], "line_start": o["line_start"]})
    claims = None
    lines = []
    if (CUR / "claim-check.json").exists():  # fallback when the claim check is off: no claim is checked
        claims = validate("claim-check.schema.json", CUR / "claim-check.json")
        for c in claims["claims"]:
            v = c["verdict"]
            if v and v["verdict"] == "WRONG":
                evidence = next((e["evidence"] for e in v["assertions"] if not e["confirmed"]), "")
                record(l, "claims_wrong", {"round": n, "claim_id": c["id"], "file": c["file"], "line": c["line"],
                                           "quote": c["quote"], "failing_case": v.get("failing_case", ""), "evidence": evidence})
                lines.append(f"WRONG  {clean(c['file'])}:{c['line']} \"{clean(c['quote'], 160)}\" | fails when: "
                             f"{clean(v.get('failing_case', ''), 200)} | evidence: {clean(evidence, 80)}")
            elif v and v["verdict"] == "UNSURE":
                record(l, "claim_notes", {"round": n, "claim_id": c["id"], "file": c["file"], "line": c["line"],
                                          "quote": c["quote"], "gap": v.get("gap", "")})
        for f in claims["unread"]:
            record(l, "unread", {"round": n, "file": f["file"], "reason": f["reason"]})
            lines.append(f"UNREAD {clean(f['file'])}: {clean(f['reason'], 120)}")
        for u in claims["unjudged"]:
            record(l, "unjudged", {"round": n, "claim_id": u["id"], "file": u["file"], "line": u["line"],
                                   "quote": u["quote"], "reason": u["reason"]})
            lines.append(f"UNJUDGED {clean(u['file'])}:{u['line']} \"{clean(u['quote'], 160)}\": {clean(u['reason'], 120)}")
        if claims.get("warning"):
            record(l, "warnings", {"round": n, "warning": claims["warning"]})
    save_ledger(l)
    doc = {"round": n, "base": (R / "base").read_text().strip(), "head": git("rev-parse", "HEAD"),
           "changed_files": sorted(pr_files), "findings": summary, "shim_check": list(shim.values()) if shim else None,
           "claim_check": {k: claims[k] for k in ("tree", "counts", "not_judged", "unread", "unjudged")} if claims else None,
           **{k: l[k] for k in LEDGER_KEYS}}
    (R / "report.json").write_text(json.dumps(doc, indent=2) + "\n")
    needs_human = bool(lines)
    message = ""
    if needs_human:
        head = (f"Whetstone: the claim check found {len(lines)} item(s) a person must look at. Each line below is "
                "quoted from the repository (agent-written text, cleaned):")
        message = "\n".join([head] + [f"  | {x}" for x in lines[:40]] +
                            ([f"  | ... and {len(lines) - 40} more"] if len(lines) > 40 else []) +
                            ["Details: .review/report.json and .review/current/claim-check.json. Approve to record "
                             "that you have seen them; reject to stop the run."])
    counts = {k: len(l[k]) for k in LEDGER_KEYS}
    out({"valid": True, "needs_human": needs_human, "message": message, "actionable": (summary or {}).get("actionable"),
         **counts})


def finish():
    runstate.bound_run_id()
    choice = os.environ.get("WHETSTONE_GATE", "").strip()
    l = ledger()
    if choice:
        record(l, "gate", {"round": round_no(), "reason": choice,
                           "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})
        save_ledger(l)
        rep = json.loads((R / "report.json").read_text())
        rep["gate"] = l["gate"]
        (R / "report.json").write_text(json.dumps(rep, indent=2) + "\n")
    out({"valid": True, "gate": choice or None, **{k: len(l[k]) for k in LEDGER_KEYS}})


def validate_cmd():
    validate(sys.argv[2], Path(sys.argv[3]), fresh=False)
    out({"valid": True})


if __name__ == "__main__":
    {"setup": setup, "guard": guard, "fetch": fetch, "canary-open": canary_open, "canary-check": canary_check,
     "validate": validate_cmd, "summarize": summarize, "report": report, "finish": finish}[sys.argv[1]]()
