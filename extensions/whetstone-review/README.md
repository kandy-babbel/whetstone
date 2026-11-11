# whetstone-review

The review step of Whetstone. Claude Code runs pr-review-toolkit's
`/pr-review-toolkit:review-pr` on the branch, and `reviewer.md` tells it how to
write the result as `.review/current/findings.json`.

pr-review-toolkit chooses which of its agents to run from the diff. The loop
asks for every applicable review except code-simplifier.

## Contract

- **Reads:** `.review/base`, `.review/round`, `.review/ledger.json` (earlier
  decisions, so it does not report them again).
- **Writes:** `.review/current/findings.json`
  (`whetstone-core/schemas/findings.schema.json`). Severity maps from the review
  summary: Critical Issues → `Critical`, Important Issues → `Important`,
  Suggestions → `Minor`. Only Critical and Important findings are acted on.

## Use on its own

```bash
specify workflow run whetstone-review
```

The workflow `whetstone-review` runs the review, then validates the file with
whetstone-core. It expects `.review/` set up by `whetstone.py setup` and `begin-round`.

## Requirements

Claude Code with the `pr-review-toolkit` plugin enabled; whetstone-core.
