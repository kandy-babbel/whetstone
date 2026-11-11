---
description: "Act on the actionable findings of a round and write decisions.json"
---

# Act on the actionable findings

A program checks what you write and the code you change; nothing reads your
chat reply.

## Input

- `.review/current/findings.json`: the round's findings (cc-review format).
- `.review/current/summary.json`: `actionable_ids` lists the findings to act on.
- `.review/current/pr-files.txt`: the files the pull request changes.
- `.review/current/shim-check.json`, **if it exists**: for each finding, the defect
  class, its occurrences and the chosen strategy. If it does not exist, treat
  every finding as `local_fix`.
- `.specify/extensions/whetstone-apply/whetstone-apply-config.yml`: `checks`, the commands that must pass.

## For each actionable finding, decide one of

- `fix`: change the code. Follow the shim-check strategy:
  - `local_fix`: fix the reported spot.
  - `class_fix`: fix every occurrence with `in_pr: true`, or their shared cause.
    Do not patch only the reported line. The fix may land in a different file
    from the occurrences (a test for untested code, one shared cause); in
    `reason`, say for each in-PR occurrence how your change covers it.
  - `simpler_than_suggested`: make the smaller fix the rationale describes.
  Change only files listed in `pr-files.txt`; you may add new files (for
  example a new test). Never change other existing files: occurrences outside
  the PR are follow-ups, recorded by the loop from shim-check.json.
- `reject`: the finding is wrong. The reason must cite the code that shows it.
- `defer`: the finding is right but belongs outside this pull request.
- `clarify`: you cannot decide without a human; say what question they must answer.

Keep the repository's conventions (its agent instructions, such as `AGENTS.md`
or `CLAUDE.md`, and the rule files listed in
`.specify/extensions/whetstone-triage/whetstone-triage-config.yml` if it exists);
update tests and docs your fix makes wrong.

## Then run every command in `checks`

Make them all pass. Record each command's result in `tests`. If `checks` is
empty, run none and write `"tests": {}`. After you finish, the loop runs every
check again itself; if one fails, the round fails and nothing is committed.

## Output

Write `.review/current/decisions.json`, strict JSON, matching
`.specify/extensions/whetstone-core/schemas/decisions.schema.json`:

```json
{
  "schema_version": "whetstone.decisions/1",
  "round": 1,
  "tests": {"npm test": "42 passed"},
  "decisions": [
    {"finding_id": "FINDING-1", "decision": "fix", "reason": "What you changed and why",
     "files_changed": ["path/one", "path/two"]}
  ]
}
```

`round` is the number in `.review/round`. `files_changed` lists every file you
changed for that finding (empty for reject, defer and clarify). Every file you
change must appear in some fix's `files_changed`; the loop refuses to commit
unclaimed changes and any change to an existing file outside `pr-files.txt`. Do not commit;
the loop commits for you. Never run `git push`, `gh`, `curl` or anything that
contacts a remote service.
