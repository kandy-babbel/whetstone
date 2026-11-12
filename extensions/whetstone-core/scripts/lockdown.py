"""Whetstone's lockdown: the rules that keep agents away from everything the checker trusts.

Whetstone only reads a repository. Its agents run in Claude Code's sandbox with the whole working directory
read-only (the flags in SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS, checked by `agent_flag_errors`); they answer on
standard output, which Spec Kit stores in the run state. The deterministic steps execute nothing from the repository:
they run with Python isolated (`python3 -I`, `uv run --isolated --no-config --no-project`), call git with the user's
and the system's configuration ignored and hooks off (`git_cmd`, `git_env`), and show agent text to people only
through `clean_text`. Standard library only, so the claim check can import it under plain python3.
"""
from __future__ import annotations

import json, os, shlex, subprocess, unicodedata
from pathlib import Path

ENV = "SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS"
EXECUTABLE_ENV = "SPECKIT_INTEGRATION_CLAUDE_EXECUTABLE"
TMPDIR_MAX = 60  # bytes; the sandbox puts a unix socket under TMPDIR, and a socket path is limited to 108 bytes
PROTECTED = (".claude", ".specify")  # what agents are launched from; must equal HEAD when a run starts
REQUIRED_DENY = "Edit(./**)"  # the whole working directory; `Edit(**)` does not make the sandbox mount it read-only
REQUIRED_CLAUDE_MD_EXCLUDES = ("**/CLAUDE.md", "**/CLAUDE.local.md")
REQUIRED_FLAGS = ("--strict-mcp-config",)
FORBIDDEN_FLAGS = ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions", "--dangerously-disable-sandbox")
FORBIDDEN_MODES = ("bypassPermissions", "auto")
SETTINGS = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True},
            "disableAllHooks": True, "claudeMdExcludes": list(REQUIRED_CLAUDE_MD_EXCLUDES),
            "permissions": {"deny": [REQUIRED_DENY]}}
SETTINGS_JSON = json.dumps(SETTINGS, separators=(",", ":"))
EXTRA_ARGS = (f"--permission-mode acceptEdits --no-session-persistence --strict-mcp-config --output-format json "
              f"--settings '{SETTINGS_JSON}'")

# git, as the trusted steps call it: no user or system configuration, no hooks, no file system monitor.
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
           "GIT_OPTIONAL_LOCKS": "0"}
GIT_OPTS = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "advice.addEmbeddedRepo=false")


def git_cmd(*args: str) -> list[str]:
    return ["git", *GIT_OPTS, *args]


def git_env(extra: dict | None = None) -> dict:
    return {**os.environ, **GIT_ENV, **(extra or {})}


def git(*args: str, env: dict | None = None) -> str:
    return subprocess.run(git_cmd(*args), check=True, capture_output=True, text=True, env=git_env(env)).stdout.strip()


def _settings_values(tokens: list[str]) -> list[str]:
    found = [tokens[i + 1] for i, t in enumerate(tokens) if t == "--settings" and i + 1 < len(tokens)]
    return found + [t.split("=", 1)[1] for t in tokens if t.startswith("--settings=")]


def _flag_value(tokens: list[str], flag: str) -> list[str]:
    found = [tokens[i + 1] for i, t in enumerate(tokens) if t == flag and i + 1 < len(tokens)]
    return found + [t.split("=", 1)[1] for t in tokens if t.startswith(flag + "=")]


def agent_flag_errors(value: str | None = None, executable: str | None = None) -> list[str]:
    """Why the flags Spec Kit passes to every agent do not lock it down; empty when they do."""
    raw = os.environ.get(ENV, "") if value is None else value
    exe = os.environ.get(EXECUTABLE_ENV) if executable is None else executable
    errors = []
    if exe:
        errors.append(f"{EXECUTABLE_ENV} is set; it would replace the claude program the agents run as")
    try:
        tokens = shlex.split(raw)  # as Spec Kit splits them
    except ValueError as e:
        return errors + [f"{ENV} is not parseable: {e}"]
    errors += [f"{ENV} contains {t}" for t in tokens if t in FORBIDDEN_FLAGS]
    for mode in _flag_value(tokens, "--permission-mode"):
        if mode in FORBIDDEN_MODES:
            errors.append(f"{ENV} sets --permission-mode {mode}")
    for flag in REQUIRED_FLAGS:
        if flag not in tokens:
            errors.append(f"{ENV} must contain {flag}")
    if _flag_value(tokens, "--output-format") != ["json"]:
        errors.append(f"{ENV} must contain --output-format json, once")
    settings = _settings_values(tokens)
    if len(settings) != 1:
        return errors + [f"{ENV} must contain exactly one --settings with inline JSON; found {len(settings)}"]
    try:
        s = json.loads(settings[0])
    except ValueError:
        return errors + ["--settings must be inline JSON (a settings file in the repository could be edited)"]
    if not isinstance(s, dict):
        return errors + ["--settings must be a JSON object"]
    sandbox = s.get("sandbox")
    if not isinstance(sandbox, dict) or sandbox.get("enabled") is not True:
        errors.append("--settings must set sandbox.enabled to true")
    else:
        if sandbox.get("allowUnsandboxedCommands") is not False:
            errors.append("--settings must set sandbox.allowUnsandboxedCommands to false")
        if sandbox.get("failIfUnavailable") is not True:
            errors.append("--settings must set sandbox.failIfUnavailable to true (without it, an agent whose sandbox "
                          "cannot start runs with no sandbox at all)")
    if s.get("disableAllHooks") is not True:
        errors.append("--settings must set disableAllHooks to true")
    excludes = s.get("claudeMdExcludes") or []
    if not isinstance(excludes, list) or any(e not in excludes for e in REQUIRED_CLAUDE_MD_EXCLUDES):
        errors.append(f"--settings claudeMdExcludes must include {list(REQUIRED_CLAUDE_MD_EXCLUDES)}")
    deny = ((s.get("permissions") or {}).get("deny") or []) if isinstance(s.get("permissions"), dict) else []
    if REQUIRED_DENY not in deny:
        errors.append(f"--settings permissions.deny must include {REQUIRED_DENY}")
    return errors


def tmpdir_errors(*, fresh: bool = False) -> list[str]:
    """TMPDIR must be a short private directory: agents can write it, so it is one per run and never read back."""
    raw = os.environ.get("TMPDIR")
    if not raw:
        return ["TMPDIR is not set; run Whetstone with a fresh one: TMPDIR=$(mktemp -d /tmp/whet.XXXXXX)"]
    if len(raw.encode()) > TMPDIR_MAX:
        return [f"TMPDIR is longer than {TMPDIR_MAX} bytes ({raw}); the agents' sandbox needs a short one"]
    p = Path(raw)
    if not p.is_absolute() or not p.is_dir():
        return [f"TMPDIR {raw} is not an absolute path to a directory"]
    if fresh and any(p.iterdir()):
        return [f"TMPDIR {raw} is not empty; give each run a fresh one: TMPDIR=$(mktemp -d /tmp/whet.XXXXXX)"]
    return []


_IGNORED_OK = (".specify/workflows/runs/", "/.cache/", "__pycache__/", ".specify/.")


def integrity_errors() -> list[str]:
    """Why .claude/ and .specify/ (the skills, workflows and scripts agents and steps run from) are not exactly what
    HEAD records: a modified, untracked or ignored file there, except Spec Kit's own run state and caches."""
    r = subprocess.run(git_cmd("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching",
                               "--", *PROTECTED), capture_output=True, env=git_env())
    if r.returncode != 0:
        return [f"git status failed: {r.stderr.decode(errors='replace').strip()[:200]}"]
    bad = []
    for entry in r.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code == "!!" and (path.startswith(_IGNORED_OK[0]) or any(m in path for m in _IGNORED_OK[1:])):
            continue
        # Claude Code itself creates this folder, empty, in every project it runs in; anything inside it counts.
        if path == ".claude/.cc-writes/" and Path(path).is_dir() and not any(Path(path).iterdir()):
            continue
        bad.append(f"{code.strip() or 'M'} {path}")
    if bad:
        return [f"{' and '.join(PROTECTED)} differ from HEAD; commit or remove these first: {bad[:8]}"]
    return []


def clean_text(text, cap: int = 240) -> str:
    """Agent text made safe to show a person: control, format and separator characters out, one line, capped."""
    kept = "".join(" " if unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn") else ch
                   for ch in str(text))
    kept = " ".join(kept.split())
    return kept if len(kept) <= cap else kept[:cap - 1] + "…"
