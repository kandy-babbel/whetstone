---
description: "Write shim-check.json for the actionable findings of a round"
---

# Shim check: patch or class fix for each actionable finding

You decide how big each fix should be. You do not change any code. A program
checks what you write; nothing reads your chat reply.

## Input

- `.review/current/findings.json`: the round's findings (cc-review format).
- `.review/current/summary.json`: `actionable_ids` lists the findings to check.
- `.review/current/pr-files.txt`: the files the pull request changes.

## For each actionable finding

1. Name the **defect class**: the general mistake, not this instance (for
   example "workflow output read without checking the step ran", not "line 330
   of ci.yml").
2. **Search the repository** for other occurrences of that class: grep, read the
   surrounding code, follow callers. Include the reported location. An
   occurrence is a place where the defect is, not where the fix will land: for
   missing tests, list the untested code, not the test file.
3. For each occurrence set `in_pr` to whether its file is listed in
   `pr-files.txt`. Occurrences outside the PR become follow-ups; they are not
   fixed in this pull request.
4. Choose a **strategy**:
   - `local_fix`: the defect is isolated; fix it where it was reported.
   - `class_fix`: the same defect occurs elsewhere in the PR's files, or the
     reported spot is a symptom of a shared cause in the PR's files; fix the
     cause or every in-PR occurrence, not just the reported line. A patch or
     shim at the reported line would leave the class in place.
   - `simpler_than_suggested`: the reviewer's suggested fix is larger than the
     problem warrants (new abstractions, configuration or tests out of
     proportion); a smaller fix is enough. Say which in `rationale`.
5. Explain the choice in `rationale`, citing the occurrences or code you found.

## Output

Write `.review/current/shim-check.json`, strict JSON, matching
`.specify/extensions/whetstone-core/schemas/shim-check.schema.json`:

```json
{
  "schema_version": "whetstone.shim-check/1",
  "round": 1,
  "results": [
    {
      "finding_id": "FINDING-1",
      "defect_class": "One line",
      "occurrences": [
        {"file": "path", "line_start": 42, "in_pr": true, "note": "the reported spot"}
      ],
      "strategy": "class_fix",
      "rationale": "Why this size of fix, citing what you found."
    }
  ]
}
```

`round` is the number in `.review/round`. Never run `git push`, `gh`, `curl` or
anything that contacts a remote service.
