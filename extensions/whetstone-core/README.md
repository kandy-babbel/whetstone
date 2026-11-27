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
| `setup` | refuses a missing lockdown (the agents' flags, `TMPDIR`, `PYTHONPYCACHEPREFIX`, `.claude/` and `.specify/` not equal to `HEAD` or holding compiled Python), an un-ignored `.review/` or `.specify/workflows/runs/`, triage without `TYPESAFE_API_KEY`, a `repo/` that is not a plain local clone, or (in a repository) a change that touches `.claude/` or `.specify/` without `WHETSTONE_ALLOW_PROTECTED`; moves an earlier run to `.review/previous/` (another branch's runs, and its claim cache, to `.review/archive/<branch>/`); records `root`, `branch`, `head`, the base commit (`merge-base <base_ref> HEAD`), the `tree` of the change, the run id, the change's diff (`diff.patch`) and files (`pr-files.txt`), and the repository's conventions at the base commit (every `CLAUDE.md`, the Markdown files under `.claude/rules/`, links followed inside the tree) under `conventions/`, listed in `conventions.txt`; starts `.review/ledger.json` |
| `guard` | before every agent step: the flags, `TMPDIR`, `PYTHONPYCACHEPREFIX`, the integrity check and the repository (`repo/` unchanged, `HEAD` unchanged) again |
| `fetch <file> --command C [--args A]` / `--prompt P` | after an agent step: the answer of the step that ran command `C` (with argument `A`), or whose prompt starts with `P`, taken from the run state into `.review/current/<file>` |
| `canary-open`, `canary-check` | around the canary agent (workflow `whetstone-canary`): the paths are computed from the nonce (and, with `repo/`, include the clone and its `.git`); none may exist, and the agent's answer must be the script's output for that nonce |
| `validate <schema> <file>` | checks one file against one schema |
| `summarize` | validates findings (and triage, if present); requires the review's `head` to be the recorded one and `files_reviewed` to be the change's file list; maps `repo/`-prefixed paths back; counts Critical and Important findings not dismissed as `actionable` |
| `report` | validates the shim check and the claim check (if present), records follow-ups, WRONG claims, UNSURE notes, unread files and unjudged claims in the ledger, writes `.review/report.json` (with the conventions the review was given), and says whether a person must look (`needs_human`, with the gate's `message`) |
| `finish` | records the gate's answer (`WHETSTONE_GATE`) in the ledger and the report |

`python3 -I -B .specify/extensions/whetstone-core/scripts/lockdown.py flags` prints the
value of `SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS` the run requires. An agent uses it in
place of the README's line, whose JSON in a heredoc its shell refuses.

### Agent commands

| Command | Skill | Does |
|---|---|---|
| `speckit.whetstone-core.review` | `speckit-whetstone-core-review` | for a person's coding agent: checks out the branch (in a harness), checks the install, runs `specify workflow run whetstone` locked down, and reports from `.review/report.json`; never answers the gate |
| `speckit.whetstone-core.canary` | `speckit-whetstone-core-canary` | internal: the lockdown canary's agent; not to be run directly |

Every step that touches `.review/` checks that it belongs to the run that set it
up (`.review/run-id`), so resuming an old run after a newer one cannot mix their
files.

## The lockdown rules (`scripts/lockdown.py`)

- `agent_flag_errors`: what `SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS` must contain
  (the repository README's table), and that `SPECKIT_INTEGRATION_CLAUDE_EXECUTABLE`
  is unset.
- `tmpdir_errors`: `TMPDIR` set, a directory `/tmp/whet.*` (what the allow rule
  `Edit(//tmp/whet.*/**)` covers), not a link, at most 60 bytes, and empty at `setup`.
- `pyc_errors`: `PYTHONPYCACHEPREFIX` set, absolute, outside the working directory
  and `TMPDIR`.
- `integrity_errors`: `git status` of `.claude/` and `.specify/` shows nothing but
  Spec Kit's run state, caches and lock files, and Claude Code's empty
  `.claude/.cc-writes/`; no compiled Python there, tracked or not.
- `git`, `git_cmd`, `git_env`: git with `GIT_CONFIG_GLOBAL=/dev/null`,
  `GIT_CONFIG_NOSYSTEM=1`, `core.hooksPath=/dev/null` and `core.fsmonitor=false`, for
  every git call Whetstone makes.
- `clean_text`: agent text made safe to show a person.

`scripts/runstate.py` reads the agents' answers: it walks the run's `execution`
tree in `state.json`, finds a step by the command and argument, or the prompt, that
Spec Kit recorded from the workflow definition, requires exit code 0, no truncation,
and a successful `--output-format json` envelope, and parses the one JSON document
in the answer.

`scripts/repo.py` is the repository under review as the steps see it: the working
directory, or the clone under `repo/` when that directory exists (the harness
layout). It runs git there with the lockdown's environment, checks the clone
(`errors`: a directory, not a link; `repo/.git` a directory of its own; git's root
and `HEAD` as recorded), builds the tree of the change in a temporary index and a
throwaway object store under `.review/tmp/objects` (`change_tree`, `objects_env`),
reads the repository's conventions at a commit (`conventions`: every `CLAUDE.md` and
the Markdown files under `.claude/rules/`, with links followed inside the tree; a link
that leaves the tree, loops or points at an absolute path is skipped with its reason),
and maps a path an agent wrote with the `repo/` prefix back (`canon`).

## Configuration

`.specify/extensions/whetstone-core/whetstone-core-config.yml`, created from
`whetstone-core-config.template.yml` on install and never overwritten:

```yaml
base_ref: origin/main   # the branch pull requests merge into
```

## Requirements

`git`, `python3`, `uv`. jsonschema and PyYAML are fetched by `uv run`;
`lockdown.py`, `runstate.py` and `repo.py` use the standard library only, so the
claim check can import them under plain `python3`.

See `NOTICE.md` for the origin of `finding.schema.json`.
