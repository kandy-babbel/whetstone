"""Agents' answers, read from Spec Kit's run state.

An agent step runs `claude -p ... --output-format json` with `capture: true`; Spec Kit stores the process's standard
output in `.specify/workflows/runs/<run id>/state.json`, a folder agents cannot write. The file holds every step of
the run, nested workflows and fan-out items included, in its `execution` tree. A step is found by what Spec Kit
recorded from the workflow definition: a command step by its command and argument, a prompt step by the start of its
prompt. Standard library only."""
from __future__ import annotations

import json, os, re
from pathlib import Path

RUN_ID_ENV = "WHETSTONE_RUN_ID"
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*?)\n\s*```\s*$", re.S)


def run_id() -> str:
    rid = os.environ.get(RUN_ID_ENV, "")
    if not _RUN_ID.match(rid):
        raise SystemExit(f"{RUN_ID_ENV} must be the run id: set env {RUN_ID_ENV}: '{{{{ context.run_id }}}}' on the step")
    return rid


def bound_run_id() -> str:
    """The run id setup wrote to .review/run-id; a step of another run must not touch these files."""
    rid, mark = run_id(), Path(".review/run-id")
    if not mark.exists():  # a module run on its own, with no setup step: the first step to need it claims .review/
        mark.parent.mkdir(exist_ok=True)
        mark.write_text(rid + "\n")
    recorded = mark.read_text().strip()
    if recorded != rid:
        raise SystemExit(f".review/ belongs to run {recorded or '(none)'}, not to this run {rid}; a later run replaced "
                         "these files. Start a new run instead of resuming this one.")
    return rid


def run_dir() -> Path:
    return Path(".specify/workflows/runs") / bound_run_id()


def _nodes(seq):
    for node in (seq or {}).get("nodes") or []:
        if not isinstance(node, dict):
            continue
        yield node
        for child in node.get("children") or []:
            yield from _nodes(child)


def records(state: dict | None = None) -> list[dict]:
    """Every step record of the run that has a result: {outcome, status, output}."""
    state = json.loads((run_dir() / "state.json").read_text()) if state is None else state
    found = []
    for node in _nodes((state.get("execution") or {}).get("sequence")):
        result = node.get("result")
        if isinstance(result, dict) and isinstance(result.get("output"), dict):
            found.append({"outcome": node.get("outcome"), "status": result.get("status"), "output": result["output"],
                          "error": result.get("error")})
    return found


def find(*, command: str | None = None, args: str | None = None, prompt: str | None = None,
         state: dict | None = None) -> tuple[dict | None, str | None]:
    """The one agent step that ran `command` with `args`, or whose prompt starts with `prompt`."""
    what = f"command {command} {args}" if command else f"prompt starting {prompt[:40]!r}"
    hits = []
    for rec in records(state):
        o = rec["output"]
        if command is not None:
            if o.get("command") == command and (args is None or (o.get("input") or {}).get("args") == args):
                hits.append(rec)
        elif prompt is not None and isinstance(o.get("prompt"), str) and o["prompt"].startswith(prompt):
            hits.append(rec)
    if not hits:
        return None, f"no step of this run ran {what}"
    if len(hits) > 1:
        return None, f"{len(hits)} steps of this run ran {what}; the step cannot be told apart"
    return hits[0], None


def answer(rec: dict, label: str) -> tuple[dict | list | None, str | None]:
    """The JSON document the agent of a step record answered with, or (None, why not)."""
    o = rec["output"]
    if rec.get("status") != "completed" or rec.get("outcome") not in (None, "completed"):
        return None, f"{label}: the step {rec.get('status')}: {str(rec.get('error') or '')[:200]}"
    if o.get("exit_code") != 0:
        return None, f"{label}: the agent exited with code {o.get('exit_code')}"
    if o.get("stdout_truncated") or o.get("timed_out") or o.get("interrupted"):
        return None, f"{label}: the agent's output is incomplete (cut, timed out or interrupted)"
    stdout = o.get("stdout")
    if not isinstance(stdout, str) or not stdout.strip():
        return None, f"{label}: the agent wrote nothing"
    text = stdout
    try:
        envelope = json.loads(text)
    except ValueError:
        envelope = None
    if isinstance(envelope, dict) and envelope.get("type") == "result":
        if envelope.get("is_error") or envelope.get("subtype") != "success":
            return None, f"{label}: the agent ended with {envelope.get('subtype')}: {str(envelope.get('result') or '')[:200]}"
        text = envelope.get("result")
        if not isinstance(text, str):
            return None, f"{label}: the agent's result is not text"
    doc = _parse(text)
    if doc is None:
        return None, f"{label}: the agent's answer is not one JSON document"
    return doc, None


def _parse(text: str):
    """The one JSON document in an answer: as it is, inside a code fence, or between the outermost brackets."""
    for candidate in (text, (_FENCE.match(text) or [None, None])[1]):
        if candidate is None:
            continue
        try:
            return json.loads(candidate, parse_constant=_no_constants)
        except ValueError:
            pass
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    end = max(text.rfind("}"), text.rfind("]"))
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1], parse_constant=_no_constants)
        except ValueError:
            return None
    return None


def _no_constants(name):
    raise ValueError(f"non-standard JSON constant {name}")
