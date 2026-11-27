---
description: "Scope or re-scope a GitHub issue in a spec folder before it is built, by running the whetstone-plan workflow (premise → specify → grill → plan → critique → tasks; a re-scope of a spec starts at grill). It first asks whether the issue is worth a spec at all. Use for an issue that needs scoping (`#<issue>`) or a spec folder that needs re-scoping (`rescope <spec folder> #<issue>`)."
---

# Scope an issue with Whetstone

The request: $ARGUMENTS

Drive the `whetstone-plan` Spec Kit workflow. The workflow owns the step order and the checks; you pick the inputs,
run the three interactive steps in this session, and pass the person's verdicts on resume. Never do a workflow
step's work yourself in its place.

Whetstone writes the spec folder and nothing else: it commits nothing, pushes nothing, and posts nothing on GitHub.

## Stop first if

- You are one of a Whetstone run's agents: another `speckit-whetstone-*` skill gave you your task, or `$TMPDIR`
  starts with `/tmp/whet.`. Then do nothing with this skill.
- The project root has a clone at `repo/` (a Whetstone harness). Planning writes into the repository it plans for,
  and a harness exists so that nothing is written there: tell the person, and stop.

## Paths

Work from the project root, the directory that holds `.specify/`, and run every command below from there.
`DRIVE` is `.specify/extensions/whetstone-plan/scripts/drive.py` and `PREMISE` is
`.specify/extensions/whetstone-plan/scripts/premise_report.py`; run each as `python3 -I -B <script> ...`.

Do not switch branches, stash or commit. If the person wants the spec on a branch of its own, they switch to it
first.

## 1. Resolve the entry point

`$ARGUMENTS` is one of:

- **`#<issue>`**: scope a new bug or feature. `ISSUE` is the issue number. Write the issue to `SPEC_FILE`:
  `repo=$(git remote get-url origin) && gh issue view <ISSUE> --repo "$repo" --json url,title,body --jq '"\(.url)\n# \(.title)\n\n\(.body)"' > <SPEC_FILE>`.
  `SPEC_DIR` is `specs/<ISSUE>-<short name>`, picked once, here, and never changed for the run: the workflow's
  `specify` step writes the spec there. `<short name>` is 1 to 4 words of the issue title, lowercased, each a run
  of `[a-z0-9]`, joined by single hyphens: the words that name the change. A title with no such word: stop before
  writing anything, and tell the person to retitle the issue.
- **`rescope <spec folder> #<issue>`**: re-scope that spec folder in place; both are required. `ISSUE` is as above,
  and `SPEC_DIR` is the folder, `specs/<feature>`. The folder may hold the wrong scope, so the issue is re-read as
  first stated: write it to `SPEC_FILE` with the same `gh issue view` command, then append, with the Edit tool, a
  blank line and `Open decision: …`, the decision to re-scope as this conversation states it. If the conversation
  states none, ask the person for it.

Anything else, a folder whose parent is not named `specs` included: tell the person the two forms and stop. A
change with no issue yet: ask the person to open one first (`gh issue create`), then scope it.

`SPEC_FILE` is a new file in your scratchpad or a fresh temporary directory. Issue and conversation text never go
into a command line.

## 2. Run it

`DRIVE` passes the inputs to `specify workflow`, and prints one JSON report: `run_id`, `status`, `step`; on a
failed step also `stderr` and `open_markers`; paused at `review-critique` also `critique`; completed after
`not worth doing` also `close`, the close to make and its reason. Run every `DRIVE` call in the background if your
tools allow, or with the longest timeout they allow: headless steps take up to about ten minutes each.

1. **Start.** `python3 -I -B DRIVE start <SPEC_FILE> <ISSUE> <SPEC_DIR>` on a new scope,
   `python3 -I -B DRIVE rescope <SPEC_FILE> <ISSUE> <SPEC_DIR>` on a rescope. Note the `run_id`.
   Expect `paused` at `premise`; on a rescope of a spec, `paused` at `grill`, and the next step is 4; on a rescope
   of a folder whose spec.md says no spec is needed, `paused` at `premise`.
2. **Premise.** Write the output of `python3 -I -B PREMISE form` to
   `.specify/workflows/runs/<run_id>/premise-report.md`. Answer each of its questions in this session, from the
   issue and the code, each with its source. Ask the person only what the issue and the code cannot answer. Show
   the person the answers and your recommendation, and write it in `Recommendation:`. It is one of the three
   outcomes: `write the spec`, `no spec needed`, `not worth doing`. Ask the person to pick one of the three by
   name. Never ask for approve or reject at this step. Write the person's pick in `Pick:`, and for either of the
   two stop picks the question it rests on and the reason, as the form says.
3. **Resume past premise.** `python3 -I -B DRIVE resume <run_id> "premise_verdict=<pick>"`. After `write the spec`,
   expect `paused` at `grill`. After either stop pick, expect `completed`. After `not worth doing`, the run names
   the close: tell the person to close the issue as not planned with that reason, and stop. After
   `no spec needed`, the workflow has written `SPEC_DIR` with a spec.md that says no spec is needed: tell the
   person to commit it, so that a later scope of the issue sees it was judged, and stop.
4. **Grill.** Invoke `/speckit-grill-me` in this session. On a rescope, give grill the open decision first: it is
   the first question. The person answers every question. Do not answer for the person.
5. **Resume past grill.** Only after grill finished: `python3 -I -B DRIVE resume <run_id> grill_verdict=approve`.
   If the person wants to stop, pass `grill_verdict=reject`. Expect `paused` at `review-critique`.
6. **Critique review.** Read the report's `critique` file and show the person its findings. Apply to
   spec.md/plan.md only the findings the person accepts.
7. **Resume past critique.** Only when the person approves:
   `python3 -I -B DRIVE resume <run_id> critique_verdict=approve` (or `reject`). Expect `completed`.
8. **Done.** When the report says `completed`, the spec folder is in the working tree and nothing is committed.
   End with `Spec folder: <SPEC_DIR>` and tell the person:
   - to review it and commit it themselves;
   - that Spec Kit recorded the folder in `.specify/feature.json`. Where Whetstone's review is installed too, a
     review refuses to start while an uncommitted file sits under `.specify/`: delete it once the spec needs no
     more `/speckit-*` work, before the next review.

A verdict is the person's decision. Never pass `approve`, or a premise pick, without the person saying so in this
session.

## Stops

`DRIVE` exiting non-zero, or a report other than the one the step expects: show the person the message or the
report (`stderr` included) and stop. The exceptions, each resumed with `python3 -I -B DRIVE resume <run_id>`:
- `step: preflight`, with `stderr` lines that each name a Next step: show them to the person. The person takes
  each step, not you; resume only once they say it is done.
- `step: premise-report`, with `stderr` lines that each name a Next step: complete the report as they say. An
  answer only the person has is the person's to give.
- `step: root-cause`, `root-cause-after-grill` or `root-cause-of-rescope`, with a `stderr` line that names a
  Next step: fix the `## Root cause` section of spec.md as it says.
- `step: premise-answers` or `premise-answers-after-grill`, with `stderr` lines that each name a Next step: copy
  the premise report's answers into the `## Why this is worth doing` section of spec.md as they say.
- `step: write-no-spec`, with a `stderr` line that names a Next step: show the person the message. When it names a
  path to clear or make writable, the person does that, not you; resume only once they say it is done. When it
  names `premise_report.py check`, complete the report as it says.
- `open_markers: true` goes back to step 4 first.
- `step: settled-design`: settle each `stderr` line with the person as its Next step says; do not fill in a
  decision for them.

A run that is rejected or fails leaves whatever its steps wrote in the working tree; `git status` shows it.
