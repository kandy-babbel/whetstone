#!/usr/bin/env python3
"""Start or resume the whetstone-plan workflow from the project, then print where the run stands as JSON.

    drive.py start <spec file> <issue> <spec dir>      a new scope
    drive.py rescope <spec file> <issue> <spec dir>    a rescope
    drive.py resume <run id> [<input>=<value>]

The workflow, its preset and this extension are installed by the Whetstone bundle and committed with it, so a run
installs nothing.

Values reach specify as argv, never through a shell: issue and ruling text routinely carry backticks.
The report is read from the run's state.json because the specify CLI prints only a generic error for a
failed step; the step's own stderr is recorded nowhere else.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

RUNS = Path(".specify/workflows/runs")
WORKFLOW = "whetstone-plan"
# The headless agent steps get only what they need to write the spec folder. This replaces any review lockdown the
# shell exports: planning agents write the spec folder, which a Whetstone review's agents may never do.
AGENT_ARGS = ('--setting-sources project --allowedTools "Read Grep Glob Write Edit Bash(bash .specify/*) '
              'Bash(.specify/*) Bash(ls:*) Bash(cat:*) Bash(mkdir:*) Bash(date:*)"')
# Spec Kit imports the bundle's `decision` step on every workflow run. Without a prefix, Python compiles it next to its
# source under .specify/, and the next Whetstone review refuses to start. The prefix the README has the review shell
# export is used when the shell exports none.
PYC_ENV = "PYTHONPYCACHEPREFIX"
PYC_DEFAULT = Path.home() / ".cache" / "whetstone-pyc"
OPEN_MARKERS = "Open clarification markers remain"
KIND = {"start": "new", "rescope": "rescope"}


def report(state):
    step = state["current_step_id"]
    out = {"run_id": state["run_id"], "status": state["status"], "step": step}
    # The engine records nothing for a step that raises, and a resumed step keeps its previous
    # attempt's record until it returns, so a record counts only if it matches the run's own outcome.
    record = state["step_results"].get(step)
    if state["status"] == "failed":
        current = record is not None and record["status"] == "failed" and record["error"] == state["error"]
        out["error"] = state["error"]
        out["stderr"] = record["output"].get("stderr", "") if current else ""
        out["open_markers"] = step == "no-open-markers" and OPEN_MARKERS in out["stderr"]
    if state["status"] == "paused" and record is not None and record["output"].get("show_file"):
        out["critique"] = record["output"]["show_file"]
    # The close is the person's to make (Whetstone posts nothing), and the session reads nothing of the run but this
    # report, so the line the run names it with travels here.
    named = state["step_results"].get("name-close")
    if state["status"] == "completed" and named is not None:
        out["close"] = named["output"]["stdout"].strip()
    return out


def _specify(args, env):
    proc = subprocess.run(["specify", "workflow", *args, "--json"], capture_output=True, text=True,
                          env={**os.environ, PYC_ENV: os.environ.get(PYC_ENV) or str(PYC_DEFAULT),
                               "SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS": AGENT_ARGS, **env})
    return proc


def _state(run_id):
    return json.loads((RUNS / run_id / "state.json").read_text())


def _step_env(inputs):
    """The inputs a shell step reads from its environment. A resume re-runs the step the run stopped in, so a
    resume needs them as much as the start does."""
    return {"ISSUE": inputs["issue"], "SPECIFY_FEATURE_DIRECTORY": inputs["spec_dir"]}


def start(kind, spec_file, issue, spec_dir):
    spec = Path(spec_file).read_text()
    if not spec.strip():
        sys.exit(f"{spec_file} is empty")
    if not issue:
        sys.exit("the issue is empty")
    if not spec_dir:
        sys.exit("the spec folder is empty")
    inputs = {"spec": spec, "issue": issue, "spec_dir": spec_dir, "kind": kind}
    before = set(RUNS.iterdir()) if RUNS.is_dir() else set()
    flags = [arg for name, value in inputs.items() for arg in ("-i", f"{name}={value}")]
    proc = _specify(["run", WORKFLOW, *flags], _step_env(inputs))
    new = set(RUNS.iterdir()) - before if RUNS.is_dir() else set()
    if len(new) != 1:
        sys.exit(f"specify started no run:\n{proc.stdout}{proc.stderr}")
    return _state(new.pop().name)


def resume(run_id, verdict):
    if not (RUNS / run_id / "state.json").is_file():
        sys.exit(f"no run {run_id} under {RUNS}")
    inputs = json.loads((RUNS / run_id / "inputs.json").read_text())["inputs"]
    if not (inputs.get("spec_dir") and inputs.get("kind")):
        sys.exit(f"run {run_id} was started before every run took its spec folder and kind, so no step can tell "
                 "which folder it is for. Next step: start the scope again with /speckit-whetstone-plan-scope.")
    proc = _specify(["resume", run_id, *(["-i", verdict] if verdict else [])], _step_env(inputs))
    state = _state(run_id)
    if proc.returncode != 0 and state["status"] not in ("failed", "aborted"):
        sys.exit(f"specify resume failed:\n{proc.stdout}{proc.stderr}")
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in KIND:
        s = sub.add_parser(action)
        s.add_argument("spec_file")
        s.add_argument("issue")
        s.add_argument("spec_dir")
    r = sub.add_parser("resume")
    r.add_argument("run_id")
    r.add_argument("verdict", nargs="?")
    args = parser.parse_args()
    if args.action == "resume":
        state = resume(args.run_id, args.verdict)
    else:
        state = start(KIND[args.action], args.spec_file, args.issue, args.spec_dir)
    print(json.dumps(report(state)))


if __name__ == "__main__":
    main()
