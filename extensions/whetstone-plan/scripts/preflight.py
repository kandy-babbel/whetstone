#!/usr/bin/env python3
"""The planning run's first step: whether this project can scope an issue, checked before any step writes.

Usage: preflight.py <issue>. Run in the project, the directory that holds `.specify/`. Prints one stop per line,
each naming its next step, and exits 1 when there are any; exits 2 when the check cannot run.

It reads nothing outside the project and reaches no network. It stops the run when:
- the issue is not a number as GitHub writes it;
- the project is a Whetstone harness (a clone under `repo/`): planning writes a spec folder into the repository
  it plans for, and a harness exists so that nothing is written there;
- a Spec Kit extension the workflow runs is not installed and enabled: grill (`speckit.grill.me`, run in the
  session) and critique (`speckit.critique.run`, a step of the workflow). Neither is part of Spec Kit or of
  Whetstone, so each is vetted and installed by the person (the whetstone-plan README says how).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REGISTRY = Path(".specify/extensions/.registry")
# The extension that provides it, and the command the run needs from it.
NEEDED = {"grill": "speckit.grill.me", "critique": "speckit.critique.run"}
_ISSUE = re.compile(r"[1-9][0-9]*")


def _commands(registry: dict) -> set[str]:
    """Every command an enabled extension registered, for any integration."""
    found = set()
    for entry in (registry.get("extensions") or {}).values():
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        for names in (entry.get("registered_commands") or {}).values():
            found.update(n for n in names if isinstance(n, str))
    return found


def stops(issue: str, harness: bool, registry: dict) -> list[str]:
    found = []
    if not _ISSUE.fullmatch(issue):
        found.append(f"the issue is `{issue}`, not an issue number as GitHub writes it. Next step: start the run "
                     "with the issue's number.")
    if harness:
        found.append("this project is a Whetstone harness (a clone under `repo/`), and planning writes its spec "
                     "folder into the repository it plans for. Next step: install Whetstone's planning in that "
                     "repository (`install.sh --plan`) and plan there.")
    commands = _commands(registry)
    for extension, command in NEEDED.items():
        if command not in commands:
            found.append(f"the `{extension}` extension is not installed and enabled here; the run needs its "
                         f"`{command}` command. Next step: vet it and install it as the whetstone-plan README says.")
    return found


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    try:
        registry = json.loads(REGISTRY.read_text()) if REGISTRY.is_file() else {}
        if not isinstance(registry, dict):
            raise ValueError(f"{REGISTRY} holds no JSON object")
    except (OSError, ValueError) as exc:
        print(f"The planning preflight could not run: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
    # The rule Whetstone's own steps use to tell a harness (whetstone-core's repo.py): a `repo` entry at the root.
    repo = Path("repo")
    found = stops(sys.argv[1], repo.is_dir() or repo.is_symlink(), registry)
    for stop in found:
        print(stop, file=sys.stderr)
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
