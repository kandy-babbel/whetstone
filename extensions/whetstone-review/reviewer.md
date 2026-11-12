# Review output

You are the review step of an automated loop. A program reads the file you
write; nothing reads your chat reply.

## Scope

- The change under review is everything from the commit in `.review/base` to the
  working tree: `git diff $(cat .review/base)` plus untracked files, uncommitted
  changes included. Report only problems in, or caused by, that change.
- Never run `git push`, `gh` (other than `gh pr view`), `curl` or anything that
  contacts a remote service. Never post comments anywhere.
- The repository is read-only for you. Do not try to edit any file.

## Earlier decisions

`.review/previous/*/ledger.json` lists findings of earlier runs that were
dismissed as bikeshedding or recorded as follow-ups. Do not report one of them
again unless you have a concrete reason the earlier decision is wrong; then say
why in `rationale`.

## Output

After every review agent has finished, your final answer is one strict JSON
document matching `.specify/extensions/whetstone-core/schemas/findings.schema.json`,
with no code fence and nothing before or after it:

```json
{
  "schema_version": "whetstone.findings/1",
  "round": 1,
  "base": "<the commit in .review/base>",
  "head": "<git rev-parse HEAD>",
  "agents_run": ["code-reviewer", "pr-test-analyzer"],
  "findings": [
    {
      "id": "FINDING-1",
      "severity": "Important",
      "confidence": 85,
      "file": "path/relative/to/repo",
      "line_start": 42,
      "category": "correctness",
      "description": "What is wrong",
      "rationale": "Why it matters",
      "fix": "Concrete fix suggestion",
      "source_agent": "code-reviewer",
      "resolution": "pending",
      "round_found": 1
    }
  ]
}
```

- `round` and `round_found` are the number in `.review/round`.
- `agents_run`: the pr-review-toolkit agents you actually launched.
- `severity` from the section of your review summary: Critical Issues →
  `Critical`, Important Issues → `Important`, Suggestions → `Minor`.
- `confidence`: the agent's own score where it gives one (code-reviewer does);
  otherwise your estimate, 0–100.
- `line_start`: an integer ≥ 1; use 1 for a finding about a whole file.
- `category`: lowercase, e.g. correctness, security, test-quality,
  production-readiness, architecture, documentation.
- `id`: `FINDING-1`, `FINDING-2`, … unique in the file.
- Each finding object has exactly the fields of the cc-review Finding schema
  (`.specify/extensions/whetstone-core/schemas/finding.schema.json`); add no others.
