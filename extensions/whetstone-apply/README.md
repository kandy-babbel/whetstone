# whetstone-apply

Acts on each actionable finding and runs the repository's checks. For each
finding the agent decides:
- `fix`, following the shim check's strategy if there is one;
- `reject`, citing the code that shows the finding is wrong;
- `defer`, when the finding is right but belongs outside the PR;
- `clarify`, naming the question a human must answer.

## Contract

- **Reads:** `.review/current/findings.json`, `summary.json`, `pr-files.txt`,
  and `shim-check.json` if present.
- **Writes:** `.review/current/decisions.json`
  (`whetstone-core/schemas/decisions.schema.json`): `tests` (command → result)
  and one decision per actionable finding with `reason` and `files_changed`.
- **Changes:** files the PR already touches, plus new files. It does not commit;
  whetstone-core's `check-apply` checks the working tree against the decisions and
  commits.
- **Checks:** after the agent, the workflow step `checks` (`scripts/run_checks.py`)
  runs every configured command itself and writes `.review/current/checks.json`.
  If one fails, the step fails and nothing is committed. The agent's own `tests`
  report is kept but not trusted.

## Configuration

`.specify/extensions/whetstone-apply/whetstone-apply-config.yml`, created from
`whetstone-apply-config.template.yml` on install and never overwritten:

```yaml
checks:            # commands that must pass, run from the repository root
  - npm test
```

Claude Code must be allowed to run these commands, for example through
`--allowedTools` in `SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS`.

## Use on its own

```bash
specify workflow run whetstone-apply
```

## Requirements

Claude Code (with `--permission-mode acceptEdits` so it can edit files);
whetstone-core.
