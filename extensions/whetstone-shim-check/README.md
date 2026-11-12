# whetstone-shim-check

Decides how big each fix should be, before anyone changes anything. An agent
names the finding's defect class, searches the repository for other occurrences,
and chooses:

- `local_fix`: the defect is isolated; fix it where reported.
- `class_fix`: the same defect occurs elsewhere in the change's files, or shares a
  cause there. A patch or shim at the reported line would leave the class in
  place.
- `simpler_than_suggested`: the reviewer's suggested fix is larger than the
  problem warrants.

It changes no code; the repository is read-only for the agent. It answers with one
JSON document on its standard output, which the workflow's `fetch` step takes from
the run state into `.review/current/shim-check.json`.

## Contract

- **Reads:** `.review/current/findings.json`, `summary.json` (`actionable_ids`),
  `pr-files.txt` (the change's files).
- **Writes:** `.review/current/shim-check.json`
  (`whetstone-core/schemas/shim-check.schema.json`). For each actionable finding:
  - `defect_class`;
  - `occurrences`, each with `file`, `line_start`, `in_pr` and `note`;
  - `strategy`;
  - `rationale`.

An occurrence is where the defect *is*, not where the fix will land. Occurrences
outside the change's files become follow-ups in `.review/report.json`. The core
checks each `in_pr` against the change's file list.

When switched off (`--input shim_check=false` on `whetstone`), no file is
written: the report has no defect classes and no follow-ups.

## Use on its own

```bash
specify workflow run whetstone-shim-check
```

## Requirements

Claude Code, locked down as the repository README describes; whetstone-core.
