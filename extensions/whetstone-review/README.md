# whetstone-review

The review step of Whetstone. Claude Code runs pr-review-toolkit's
`/pr-review-toolkit:review-pr` on the change, and `reviewer.md` tells it how to
answer: the findings as one JSON document, on its standard output. The workflow's
`fetch` step takes that answer from the run state into
`.review/current/findings.json`.

pr-review-toolkit chooses which of its agents to run from the diff. Whetstone
asks for every applicable review except code-simplifier. The repository is
read-only for the agent.

## Contract

- **Reads:** `.review/base`, `.review/round`, earlier runs' ledgers under
  `.review/previous/` (so it does not report dismissed findings again).
- **Writes:** `.review/current/findings.json`
  (`whetstone-core/schemas/findings.schema.json`). Severity maps from the review
  summary: Critical Issues → `Critical`, Important Issues → `Important`,
  Suggestions → `Minor`. Only Critical and Important findings are acted on.

## Use on its own

```bash
specify workflow run whetstone-review
```

The workflow `whetstone-review` runs the review, takes the answer, then validates
the file with whetstone-core. It expects `.review/` set up by `whetstone.py setup`,
and the lockdown the repository README describes.

## Requirements

Claude Code with the `pr-review-toolkit` plugin enabled; whetstone-core.
