# whetstone-claim-check

Checks what the text of a change claims. Changes come with comments, docstrings,
docs or test names that describe what the code does. This module tries to break
each such claim against the code itself. It reads the repository only.

Adapted from the reviewer plugin's claim check in
[analitiq-ai/claude-plugins-internal](https://github.com/analitiq-ai/claude-plugins-internal)
(`reviewer/plugin`): its reader task, claim categories, judge prompts and the
rules for a reader's and a judge's answers are taken over as they are.

## How it works

1. **prepare** builds the tree `git add -A` would record, in a temporary index under
   `.review/` (the real index is untouched). It lists the hunks from the run's base
   commit (`.review/base`, else `HEAD`) to that tree.
2. **read**: readers (16 hunks each, one `whetstone-claim-read` workflow per batch)
   label every hunk `CODE`, `PROSE` or `MIXED` and quote every claim its text makes,
   with one category:

   | | Category | Judged |
   |---|---|---|
   | K1 | what the repo's own code, contracts, validator or CI does | against the code |
   | K2 | how a vendor tool, platform, language or standard behaves | counted |
   | K3 | a list, a count, or an "every / the only / complete" claim | counted |
   | K4 | a task tick or a PASS/FAIL mark | counted |
   | K5 | a recorded observation (date, run ID, commit, count, approval) | counted |
   | K6 | a command or code block and what it does | counted |
   | K7 | a citation of a file, field, symbol, rule or requirement | counted |
   | K8 | planned behaviour | counted |
   | K9 | what a test checks (its name, description or failure message) | against that test alone |

3. **judge**: one judge per K1 or K9 claim (one `whetstone-claim-judge` workflow
   each) splits it into assertions and tries to break each. It rules the claim
   `CORRECT`, `WRONG` (with a failing case) or `UNSURE` (with the gap), citing a
   `path:line` of the checked tree for every assertion it settles. What a test says
   it checks is judged against the test alone, since the code it drives may not exist
   yet.
4. **settle** writes `.review/current/claim-check.json`.

**Agents write nothing.** Each reader and judge drafts its answer under its own
`TMPDIR`, runs the self-check on the draft, and gives the draft's content as its
final answer. Spec Kit keeps that answer in the run state; `accept` and `settle`
take it from there (whetstone-core's `runstate.py`).

**A failed agent never counts as correct.** A reader that does not answer, or whose
answer breaks the rules, leaves every file of its batch **unread**. A judge that
does not answer, or whose verdict breaks the rules, leaves its claim **unjudged**.
Each reader and judge runs as its own workflow with `continue_on_error`, so one
failure does not stop the others. Unread files and unjudged claims go to the gate,
like WRONG claims.

**Every changed file is read as text,** whatever `.gitattributes` says (`git diff -a
--no-textconv`): an attribute such as `-diff` cannot hide a file. A changed file that
still cannot be read (it has NUL bytes) is listed in `unread`.

Readers and judges run on Sonnet by default (input `model`), as in the source.

**Every answer is checked against the tree.** A quote must be the file's text,
starting on the line given, within the paragraph around its hunk. Evidence must
be a line of a file in the checked tree; a web page or an untracked file is not
evidence. Each agent runs that check on its draft (`claimcheck.py check-read
<batch> <file>` / `check-verdict <id> <file>`) until it passes; `accept` and `settle`
check the final answer again.

**Reuse.** A hunk read once is not read again while its words are unchanged. A
`CORRECT` verdict is reused while every file it cited is unchanged, except for
claims with *every, only, all, exactly, always* or *never*: no cited file can
close those.

## In the loop

The `whetstone` workflow runs the check after the shim check. The core's `report`
step then records every WRONG claim (with its failing case and evidence), UNSURE
claims as notes, unread files and unjudged claims in `.review/ledger.json` and
`.review/report.json`. If there is anything WRONG, unread or unjudged, a gate shows
each item, cleaned of control characters and capped, and asks you to approve
(recorded in the ledger) or reject (the run stops). Nothing is committed either way.

Switch it off with `--input claim_check=false`. No file is written, and no claim
is checked.

## Contract

- **Reads:** the working tree, `HEAD`, the run's base in `.review/base` if there is
  one (`HEAD` otherwise) and its round in `.review/round` (0 otherwise); the run
  state (`WHETSTONE_RUN_ID`).
- **Writes:** `.review/current/claim-check.json`
  (`whetstone-core/schemas/claim-check.schema.json`):
  - `base` and `tree`, the commits the change was measured between;
  - `hunks`, each with its `kind` (`null` when no reader labelled it);
  - `claims`, each with `file`, `line`, `quote`, `category`, `judged`, `reused` and
    `verdict` (`null` for categories not judged);
  - `counts`, `not_judged` per category, `unread` (`file`, `reason`), `unjudged`
    (`id`, `file`, `line`, `quote`, `reason`), and a `warning` when more than 20 claims
    were judged.
- **Working files:** `.review/current/claims/` holds the prompts and the answers
  taken; `.review/claim-cache.json` holds reads and reusable verdicts.

## Use on its own

```bash
specify workflow run whetstone-claim-check                 # the change from HEAD to the working tree
specify workflow run whetstone-claim-check --input model=opus
```

It needs the lockdown (repository README) and a `HEAD` commit. With no change it
records no claims.

## Left out from the source

The source is a commit gate with records kept across commits. Whetstone keeps the
check and leaves out:
- lineages that follow a claim's words from commit to commit;
- contests of a verdict with evidence;
- `unlock`, and the gate's blocking of a commit: Whetstone commits nothing, so a
  WRONG claim is shown to a person instead.

## Requirements

Claude Code, locked down as the repository README describes; `python3` (standard
library only, so agents can run the self-checks); whetstone-core, whose
`lockdown.py` and `runstate.py` this module imports.
