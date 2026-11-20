# whetstone-review

The review step of Whetstone. Claude Code runs pr-review-toolkit's
`/pr-review-toolkit:review-pr` on the change, and `reviewer.md` tells it how to
answer: the findings as one JSON document, on its standard output. The workflow's
`fetch` step takes that answer from the run state into
`.review/current/findings.json`.

pr-review-toolkit chooses which of its agents to run from the diff. Whetstone
asks for every applicable review except code-simplifier, on the diff `setup`
recorded in `.review/current/diff.patch`, not on one the agent computes. The
repository is read-only for the agent. In the harness layout it is the clone under
`repo/`; the agent reports paths relative to it.

## Contract

- **Reads:** `.review/base`, `.review/round`, `.review/current/diff.patch` and
  `pr-files.txt`, earlier runs' ledgers under `.review/previous/` (runs of this
  branch, so it does not report dismissed findings again).
- **Writes:** `.review/current/findings.json`
  (`whetstone-core/schemas/findings.schema.json`). `head` must be the `HEAD`
  `setup` recorded and `files_reviewed` the change's whole file list, or the core
  refuses the review. Severity maps from the review summary: Critical Issues →
  `Critical`, Important Issues → `Important`, Suggestions → `Minor`. Only Critical
  and Important findings are acted on.

## Use on its own

```bash
specify workflow run whetstone-review
```

The workflow `whetstone-review` runs the review, takes the answer, then validates
the file with whetstone-core. It expects `.review/` set up by `whetstone.py setup`,
and the lockdown the repository README describes.

## Requirements

Claude Code with the `pr-review-toolkit` plugin enabled; whetstone-core.
