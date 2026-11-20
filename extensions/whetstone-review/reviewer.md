# Review output

You are the review step of an automated loop. A program reads your final
answer; nothing else you write is kept.

## Where the repository is

- If your working directory has a directory `repo/`, that is the repository under
  review (a local clone). Read its files under `repo/`, run git as
  `git -C repo ...` (`cd repo && git ...` is refused), and give every path in your
  answer relative to that repository's root, **without** the `repo/` prefix.
- Otherwise the repository is your working directory.

## Scope

- The change under review is the diff in `.review/current/diff.patch`: everything
  from the commit in `.review/base` to the working tree, uncommitted changes and
  new files included. Its files are listed in `.review/current/pr-files.txt`. Do
  not compute the diff yourself (`git diff` in your working directory may show
  nothing); review that diff, in the files as they are now.
- Report only problems in, or caused by, that change.
- Never run `git push`, `gh` (other than `gh pr view`), `curl` or anything that
  contacts a remote service. Never post comments anywhere.
- The repository is read-only for you. Do not try to edit any file.

## Earlier decisions

`.review/previous/*/ledger.json` lists findings of earlier runs on this branch
that were dismissed as bikeshedding or recorded as follow-ups. Do not report one
of them again unless you have a concrete reason the earlier decision is wrong;
then say why in `rationale`.

## Output

After every review agent has finished, your final answer is one strict JSON
document matching `.specify/extensions/whetstone-core/schemas/findings.schema.json`,
with no code fence and nothing before or after it:

```json
{
  "schema_version": "whetstone.findings/1",
  "round": 1,
  "base": "<the commit in .review/base>",
  "head": "<the HEAD of the repository under review: git rev-parse HEAD, or git -C repo rev-parse HEAD>",
  "agents_run": ["code-reviewer", "pr-test-analyzer"],
  "files_reviewed": ["every path listed in .review/current/pr-files.txt"],
  "findings": [
    {
      "id": "FINDING-1",
      "severity": "Important",
      "confidence": 85,
      "file": "path/relative/to/the/repository",
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
- `files_reviewed`: the paths in `pr-files.txt`, all of them, as written there. A
  program checks the list against the file; a review that lists fewer files, or
  other files, is refused.
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
