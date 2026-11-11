# Whetstone

Sharpens a branch before people review it: reviews it, drops bikeshedding,
chooses patch or class fixes, and fixes within the PR until nothing important
is left. See the repository README for where the name comes from. Each round:

1. **review**: pr-review-toolkit reviews the branch; findings are written in
   cc-review's Finding format.
2. **triage** (switchable): a decision model decides whether each blocking
   finding is bikeshedding. A finding is dismissed only when P(bikeshedding)
   reaches the threshold and the model's basis is "taste".
3. **shim check** (switchable): an agent names each finding's defect class, finds its
   other occurrences, and chooses a local fix, a class fix, or a fix simpler
   than suggested. Occurrences outside the PR's files become follow-ups.
4. **apply**: an agent fixes, rejects, defers or escalates each finding, only in
   the PR's files, and runs the checks.

Up to three rounds; if actionable findings remain, one more review, then a
gate for a human. `.review/report.json` lists everything dismissed, rejected,
deferred, escalated, every follow-up, and a warning for each class fix that left
an in-PR occurrence's file untouched (for a human or the next review to judge).

Before each commit the core refuses the round if any existing file outside the
PR changed, or if any changed file is not claimed by a fix decision.

## Components

| Component | Kind | Contract |
|---|---|---|
| `whetstone-core` | extension | `schemas/*.schema.json` (JSON Schema 2020-12) and `scripts/whetstone.py`, which validates every module's file, applies fallbacks, checks apply against the shim check and the PR's files, and commits each round |
| `whetstone-review` + workflow `whetstone-review` | extension, workflow | writes `.review/current/findings.json` (`findings.schema.json`, cc-review Findings) |
| `whetstone-triage` + workflow `whetstone-triage` | extension, workflow | reads findings; writes `triage.json` (`triage.schema.json`); input `threshold` |
| `whetstone-shim-check` + workflow `whetstone-shim-check` | extension, workflow | reads findings, summary, PR files; writes `shim-check.json` (`shim-check.schema.json`) |
| `whetstone-apply` + workflow `whetstone-apply` | extension, workflow | reads findings, summary, shim-check.json if present; writes `decisions.json` (`decisions.schema.json`) |
| `decision` 0.9.0 | workflow step | community step package (markuswondrak/spec-kit-decision-step) |
| `whetstone` | workflow | composes the modules; inputs `triage`, `shim_check` (booleans), `triage_threshold` |

A switched-off module writes no file. Fallbacks: no `triage.json` means nothing
is dismissed; no `shim-check.json` means every finding is a local fix.

Each module workflow can be called on its own (`specify workflow run
whetstone-triage`) or from another workflow with a `workflow` step.

## Requirements

- Spec Kit 1.3.3 or later, Claude integration; Claude Code with the
  `pr-review-toolkit` plugin enabled.
- `git` and `uv` (the scripts get PyYAML and jsonschema through `uv run`).
  If `uv` comes from proto, the repository must pin it (`uv = "..."` in
  `.prototools`). Otherwise proto cannot choose a version and every core step fails.
- For triage, `TYPESAFE_API_KEY`. Each blocking finding's evidence, including
  code excerpts and the configured rule files, goes to api.typesafe.ai. Turn
  triage off with `--input triage=false` where that is not acceptable.

## Configuration

Installing creates three files the repository owns and commits. Spec Kit never
overwrites them:

| File | Sets |
|---|---|
| `.specify/extensions/whetstone-core/whetstone-core-config.yml` | `base_ref`, the branch PRs merge into |
| `.specify/extensions/whetstone-triage/whetstone-triage-config.yml` | rule files, tool configs and CI steps in the triage evidence |
| `.specify/extensions/whetstone-apply/whetstone-apply-config.yml` | `checks`, the commands that must pass |

## Run

```bash
export SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS='--permission-mode acceptEdits --strict-mcp-config --output-format stream-json --verbose --no-session-persistence --allowedTools "Bash(npm test:*)" --disallowedTools "Bash(git push:*)" "Bash(gh pr comment:*)" "Bash(gh pr review:*)" "Bash(gh api:*)"'
export TYPESAFE_API_KEY=...   # only when triage is on
specify workflow run whetstone                      # everything on
specify workflow run whetstone --input shim_check=false --input triage=false
```

In `--allowedTools`, list the commands in your `checks`. Fixes are committed
locally, one commit per round. Nothing is pushed.

What these settings do and don't do:
- **`--allowedTools` is the real control.** In `-p` mode Claude Code may only run
  shell commands on its allow list (plus its own read-only ones). `--disallowedTools`
  is a backstop only: `git -C . push` or `sh -c 'git push'` would not match it.
- **`--output-format stream-json --verbose` keeps a full trace** of every agent turn
  in the run state under `.specify/workflows/runs/`. That includes anything the
  agents read, secrets too. Keep that folder ignored and local, or drop these two
  flags if you don't want the trace.
