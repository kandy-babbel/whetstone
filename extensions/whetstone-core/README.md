# whetstone-core

The deterministic part of Whetstone. The other modules write files under
`.review/current/`. This extension holds each file's contract, a JSON Schema, and
`scripts/whetstone.py`, which checks the files, takes the agents' answers from the
run state, keeps the run's records and writes the report. It calls no model and
changes nothing in the repository.

## Contracts

| File | Schema | Written by |
|---|---|---|
| `findings.json` | `schemas/findings.schema.json`, each finding a cc-review Finding (`finding.schema.json`) | whetstone-review |
| `triage.json` | `schemas/triage.schema.json` | whetstone-triage |
| `shim-check.json` | `schemas/shim-check.schema.json` | whetstone-shim-check |
| `claim-check.json` | `schemas/claim-check.schema.json` | whetstone-claim-check |

A module that is switched off writes no file, and `whetstone.py` applies its
fallback:
- no `triage.json`: nothing is dismissed;
- no `shim-check.json`: no defect classes, no follow-ups;
- no `claim-check.json`: no claim is checked.

Any other module or extension can read or write these files. The contract is
the schema.

## Commands

Run as `uv run --isolated --no-config --no-project --with jsonschema==4.26.0 --with
pyyaml==6.0.2 python3 -I .specify/extensions/whetstone-core/scripts/whetstone.py
<command>`. Each command prints one JSON object. It exits 1 when a contract is
broken, which fails the workflow step. Commands that read the run state need the
environment variable `WHETSTONE_RUN_ID` set to `{{ context.run_id }}`.

| Command | Does |
|---|---|
| `setup` | refuses a missing lockdown (the agents' flags, `TMPDIR`, `.claude/` and `.specify/` not equal to `HEAD`), an un-ignored `.review/` or `.specify/workflows/runs/`, or triage without `TYPESAFE_API_KEY`; moves an earlier run to `.review/previous/`; records the base commit (`merge-base <base_ref> HEAD`), the run id, the change's files (`pr-files.txt`) and starts `.review/ledger.json` |
| `guard` | before every agent step: the flags, `TMPDIR` and the integrity check again |
| `fetch <file> --command C [--args A]` / `--prompt P` | after an agent step: the answer of the step that ran command `C` (with argument `A`), or whose prompt starts with `P`, taken from the run state into `.review/current/<file>` |
| `canary-open`, `canary-check` | around the canary agent (workflow `whetstone-canary`): the paths are computed from the nonce; none may exist, and the agent's answer must be the script's output for that nonce |
| `validate <schema> <file>` | checks one file against one schema |
| `summarize` | validates findings (and triage, if present); counts Critical and Important findings not dismissed as `actionable` |
| `report` | validates the shim check and the claim check (if present), records follow-ups, WRONG claims, UNSURE notes, unread files and unjudged claims in the ledger, writes `.review/report.json`, and says whether a person must look (`needs_human`, with the gate's `message`) |
| `finish` | records the gate's answer (`WHETSTONE_GATE`) in the ledger and the report |

Every step that touches `.review/` checks that it belongs to the run that set it
up (`.review/run-id`), so resuming an old run after a newer one cannot mix their
files.

## The lockdown rules (`scripts/lockdown.py`)

- `agent_flag_errors`: what `SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS` must contain
  (the repository README's table), and that `SPECKIT_INTEGRATION_CLAUDE_EXECUTABLE`
  is unset.
- `tmpdir_errors`: `TMPDIR` set, absolute, at most 60 bytes, and empty at `setup`.
- `integrity_errors`: `git status` of `.claude/` and `.specify/` shows nothing but
  Spec Kit's run state, caches and lock files, and Claude Code's empty
  `.claude/.cc-writes/`.
- `git`, `git_cmd`, `git_env`: git with `GIT_CONFIG_GLOBAL=/dev/null`,
  `GIT_CONFIG_NOSYSTEM=1`, `core.hooksPath=/dev/null` and `core.fsmonitor=false`, for
  every git call Whetstone makes.
- `clean_text`: agent text made safe to show a person.

`scripts/runstate.py` reads the agents' answers: it walks the run's `execution`
tree in `state.json`, finds a step by the command and argument, or the prompt, that
Spec Kit recorded from the workflow definition, requires exit code 0, no truncation,
and a successful `--output-format json` envelope, and parses the one JSON document
in the answer.

## Configuration

`.specify/extensions/whetstone-core/whetstone-core-config.yml`, created from
`whetstone-core-config.template.yml` on install and never overwritten:

```yaml
base_ref: origin/main   # the branch pull requests merge into
```

## Requirements

`git`, `python3`, `uv`. jsonschema and PyYAML are fetched by `uv run`;
`lockdown.py` and `runstate.py` use the standard library only, so the claim check
can import them under plain `python3`.

See `NOTICE.md` for the origin of `finding.schema.json`.
