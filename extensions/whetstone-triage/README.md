# whetstone-triage

Decides whether each Critical or Important finding is bikeshedding, using the
community `decision` workflow step (Jev backend), one call per finding.

## Contract

- **Reads:** `.review/current/findings.json`.
- **Writes:** `.review/current/triage.json`
  (`whetstone-core/schemas/triage.schema.json`). For each finding it records:
  - `p_bikeshedding`, the model's probability that the finding is bikeshedding;
  - `basis`, the deciding consideration: `ci_check`, `repo_rule`,
    `correctness`, `security`, `test_coverage`, `doc_accuracy` or `taste`;
  - `basis_probabilities`;
  - `dismissed`.

A finding is dismissed only when `p_bikeshedding` reaches the threshold **and**
the basis is `taste`. A finding a rule or check requires is never dismissed.

## How it works

1. `scripts/gather.py` writes one evidence file per finding to
   `.review/current/triage-evidence/`. Each holds the finding, the code around
   it, the CI check steps, and the repository's rule and tool-config files.
2. The workflow's fan-out sends each evidence file to the `decision` step, four
   at a time.
3. `scripts/collect.py` writes `triage.json` from the results and the item list in
   `.review/current/triage-items.json`.

`gather.py` stops at once if `TYPESAFE_API_KEY` is not set.

## Data leaving the machine

Each evidence file is sent to the decision backend (api.typesafe.ai for Jev).
That includes code excerpts and every file named in the configuration. Only files
tracked by git are read. A finding's path comes from the reviewer, so an
untracked, ignored or outside path is replaced by a note and never sent. Switch
triage off (`--input triage=false` on `whetstone`) where that is not
acceptable.

## Configuration

`.specify/extensions/whetstone-triage/whetstone-triage-config.yml`, created from
`whetstone-triage-config.template.yml` on install and never overwritten:

| Key | Meaning |
|---|---|
| `rule_files` | files that state the repository's rules |
| `config_files` | formatter, linter and task-runner configs |
| `ci_workflow` | CI workflow file whose check steps are included (`""` for none) |
| `ci_run_prefixes` | also include `run:` lines starting with these commands |
| `context_lines` | lines of code on each side of the reported line |

Workflow input `threshold` (default 0.5).

## Use on its own

```bash
TYPESAFE_API_KEY=... specify workflow run whetstone-triage --input threshold=0.5
```

## Requirements

- the `decision` workflow step 0.9.0;
- `TYPESAFE_API_KEY`;
- `uv` (the scripts run with `uv run --with pyyaml`);
- whetstone-core.
