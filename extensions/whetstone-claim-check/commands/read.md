---
description: "Label the hunks of one claim-check batch and quote the claims their text makes"
---

# Claim check: read one batch of hunks

You read hunks of a change and list what their text claims. You do not judge
whether a claim is true; another agent does that. A program reads your final
answer; nothing else you write is kept.

Your batch number is: $ARGUMENTS

Read `.review/current/claims/batch-$ARGUMENTS.md` and do exactly what it says.
It shows the hunks, the categories and the answer format, and ends with the
self-check to run on your draft until it prints OK.

A quote is copied from the file exactly as it stands, starting on the line you
give. The check refuses any quote that does not match the file or lies outside
the text around its hunk. The batch file says where the checkout is: your working
directory, or the clone in `repo/` next to `.review/` (then read files under
`repo/` and run git as `git -C repo ...`).

The repository is read-only for you; your draft goes under `$TMPDIR`. Your final
answer is the draft's content: one JSON document, no code fence, nothing else.
Never run `git push`, `gh`, `curl` or anything that contacts a remote service.
