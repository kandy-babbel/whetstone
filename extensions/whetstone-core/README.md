# whetstone-core

The deterministic part of Whetstone. The other modules write files under
`.review/current/`. This extension holds each file's contract, a JSON Schema, and
`scripts/whetstone.py`, which checks the files and keeps the loop's records. It
calls no model.

## Contracts

| File | Schema | Written by |
|---|---|---|
| `findings.json` | `schemas/findings.schema.json`, each finding a cc-review Finding (`finding.schema.json`) | whetstone-review |
| `triage.json` | `schemas/triage.schema.json` | whetstone-triage |
| `shim-check.json` | `schemas/shim-check.schema.json` | whetstone-shim-check |
| `decisions.json` | `schemas/decisions.schema.json` | whetstone-apply |

A module that is switched off writes no file, and `whetstone.py` applies its
fallback:
- no `triage.json`: nothing is dismissed;
- no `shim-check.json`: every finding is a local fix.

Any other module or extension can read or write these files. The contract is
the schema.

## Commands

Run as `uv run --no-project --with jsonschema==4.26.0 --with pyyaml==6.0.2 python3
.specify/extensions/whetstone-core/scripts/whetstone.py <command>`. Each command
prints one JSON object. It exits 1 when a contract is broken, which fails the
workflow step.

| Command | Does |
|---|---|
| `setup` | refuses a dirty working tree, an un-ignored `.review/`, or triage without `TYPESAFE_API_KEY`; moves an earlier run to `.review/previous/`; records the base commit (`merge-base HEAD <base_ref>`) and starts `.review/ledger.json` |
| `begin-round` | archives the previous round to `.review/history/`, starts a new one, writes `pr-files.txt` |
| `validate <schema> <file>` | checks one file against one schema |
| `summarize` | validates findings (and triage, if present); counts Critical and Important findings not dismissed as `actionable` |
| `check-apply` | validates shim check (if present) and decisions, checks them against the working tree, and commits |
| `finish` | writes `.review/report.json` |

`check-apply` refuses the round, before committing, when:
- an existing file outside the PR changed (new files are allowed);
- a changed file is not claimed by any `fix` decision, or a fix claims a file
  that did not change;
- a reject, defer or clarify decision lists changed files;
- `shim-check.json` marks an occurrence `in_pr` that contradicts `pr-files.txt`.

A class fix that leaves an in-PR occurrence's file untouched is recorded as a
warning, not a failure. A test-coverage fix, for example, lands in a test file.

The commit runs the repository's commit hooks. A hook that rejects the fixes
stops the loop with the fixes staged.

## Configuration

`.specify/extensions/whetstone-core/whetstone-core-config.yml`, created from
`whetstone-core-config.template.yml` on install and never overwritten:

```yaml
base_ref: origin/main   # the branch pull requests merge into
```

## Requirements

`git`, `uv`. jsonschema and PyYAML are fetched by `uv run`.

See `NOTICE.md` for the origin of `finding.schema.json`.
