# Whetstone

Sharpens a change before people review it: reviews it, drops bikeshedding, sizes
each fix, and checks every claim the change's text makes against the code. It
reads the repository only and writes a report; a person, or a separate agent, fixes
the change, and Whetstone can run again on the result. See the repository README
for where the name comes from. One run:

1. **setup**: records the repository (the working directory, or the clone under
   `repo/`), its branch and `HEAD`, the base commit, the tree of the change, its diff
   and its files.
2. **canary**: an agent tries to write the repository; the run stops if it can.
3. **review**: pr-review-toolkit reviews the recorded diff; findings are written in
   cc-review's Finding format.
4. **triage** (switchable): a decision model decides whether each blocking
   finding is bikeshedding. A finding is dismissed only when P(bikeshedding)
   reaches the threshold and the model's basis is "taste".
5. **shim check** (switchable): an agent names each finding's defect class, finds its
   other occurrences, and chooses a local fix, a class fix, or a fix simpler
   than suggested. Occurrences outside the change's files become follow-ups.
6. **claim check** (switchable): readers quote every claim the change's text makes;
   a judge per claim about the repo's own code (K1) or about what a test checks
   (K9) tries to break it. A WRONG claim, a file no reader could read and a claim
   no judge ruled on go to a gate for a person.
7. **report**: `.review/report.json` names the repository, branch, `HEAD` and tree,
   and lists the findings and what triage dismissed, each finding's defect class and
   follow-ups, every WRONG claim with its failing case and evidence, UNSURE claims as
   notes, and the unread and unjudged items.

Agents never write the repository (see the repository README's lockdown section).
Each answers on its standard output; the core takes the answer from the run state.

## Components

| Component | Kind | Contract |
|---|---|---|
| `whetstone-core` | extension | `schemas/*.schema.json` (JSON Schema 2020-12) and `scripts/whetstone.py`, which checks the lockdown, validates every module's file, applies fallbacks and writes the report; `lockdown.py`, `runstate.py` and `repo.py` hold the rules |
| `whetstone-review` + workflow `whetstone-review` | extension, workflow | writes `.review/current/findings.json` (`findings.schema.json`, cc-review Findings) |
| `whetstone-triage` + workflow `whetstone-triage` | extension, workflow | reads findings; writes `triage.json` (`triage.schema.json`); input `threshold` |
| `whetstone-shim-check` + workflow `whetstone-shim-check` | extension, workflow | reads findings, summary, the change's files and diff; writes `shim-check.json` (`shim-check.schema.json`) |
| `whetstone-claim-check` + workflows `whetstone-claim-check`, `whetstone-claim-read`, `whetstone-claim-judge` | extension, workflows | reads the change; writes `claim-check.json` (`claim-check.schema.json`); input `model` (default `sonnet`) |
| `whetstone-canary` | workflow | the lockdown canary; input `model` (default `haiku`) |
| `decision` 0.9.0 | workflow step | community step package (markuswondrak/spec-kit-decision-step) |
| `whetstone` | workflow | composes the modules; inputs `triage`, `shim_check`, `claim_check`, `allow_protected` (booleans), `triage_threshold`, `claim_model` |

A switched-off module writes no file. Fallbacks: no `triage.json` means nothing
is dismissed; no `shim-check.json` means no defect classes and no follow-ups; no
`claim-check.json` means no claim is checked.

Each module workflow can be called on its own (`specify workflow run
whetstone-claim-check`) or from another workflow with a `workflow` step. A module
run on its own needs a `.review/` that no full run owns.

## Requirements

- Linux with Claude Code's sandbox working (bubblewrap); see the repository README.
- Spec Kit 1.3.3 or later, Claude integration; Claude Code 2.1.329 or later with the
  `pr-review-toolkit` plugin enabled, locked down as the repository README describes.
- `git`, `python3` and `uv` (the core scripts get PyYAML and jsonschema through
  `uv run`). If `uv` comes from proto, the repository must pin it (`uv = "..."` in
  `.prototools`). Otherwise proto cannot choose a version and every core step fails.
- For triage, `TYPESAFE_API_KEY`. Each blocking finding's evidence, including
  code excerpts and the configured rule files, goes to api.typesafe.ai. Turn
  triage off with `--input triage=false` where that is not acceptable.

## Configuration

Installing creates two files the repository owns and commits. Spec Kit never
overwrites them:

| File | Sets |
|---|---|
| `.specify/extensions/whetstone-core/whetstone-core-config.yml` | `base_ref`, the branch PRs merge into |
| `.specify/extensions/whetstone-triage/whetstone-triage-config.yml` | rule files, tool configs and CI steps in the triage evidence |

## Run

First lock the agents down: set `SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS` and
`PYTHONPYCACHEPREFIX` as the repository README's
[Lock down Claude Code](../README.md#lock-down-claude-code) section shows. Then
give the run a fresh temporary directory and start it, from the repository or from
the harness (the directory that holds `.specify/` and, in the harness layout, the
clone under `repo/`):

```bash
export TYPESAFE_API_KEY=...   # only when triage is on
export TMPDIR=$(mktemp -d /tmp/whet.XXXXXX)
specify workflow run whetstone                      # everything on
specify workflow run whetstone --input shim_check=false --input triage=false --input claim_check=false
rm -rf "$TMPDIR"
```

The run refuses to start without the flags, without `TMPDIR`, with a `TMPDIR` that
is not empty, when `.claude/` or `.specify/` differ from `HEAD`, when `repo/` is not
a plain local clone, or (in a repository) when the change under review touches
`.claude/` or `.specify/` and `--input allow_protected=true` was not given. It
starts with the lockdown canary (a short agent run on `haiku`). Nothing is pushed,
committed or changed. A run that stops at the gate continues with `specify workflow
resume <run id>` in a terminal, from the same shell: the same flags and the same
`TMPDIR`.

To keep a full trace of every agent turn in the run state under
`.specify/workflows/runs/`, replace `--output-format json` with `--output-format
stream-json --verbose` in the variable. Whetstone refuses that by default: the
trace includes anything the agents read, secrets too, so keep that folder ignored
and local, and use it only to debug.
