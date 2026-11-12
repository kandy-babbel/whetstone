---
description: "Try to break one claim and rule it CORRECT, WRONG or UNSURE, with path:line evidence"
---

# Claim check: judge one claim

You judge one claim against the code of this checkout, as the change leaves
it. A program reads your final answer; nothing else you write is kept.

Your claim id is: $ARGUMENTS

Read `.review/current/claims/claim-$ARGUMENTS.md` and do exactly what it says.
It gives the claim, how to judge it and the answer format, and ends with the
self-check to run on your draft until it prints OK.

Every piece of evidence is a `path:line` of a file in the checkout. The check
refuses a verdict that cites anything else.

The repository is read-only for you; your draft goes under `$TMPDIR`. Your final
answer is the draft's content: one JSON document, no code fence, nothing else.
Never run `git push`, `gh`, `curl` or anything that contacts a remote service.
