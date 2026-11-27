# whetstone-plan

Scopes a GitHub issue in a spec folder before anyone builds it. Reviews sharpen a
change after it is written; planning settles what the change is before it is
written. The `whetstone-plan` workflow runs Spec Kit's own steps in a fixed order,
and a check stands between each step and the next:

1. **preflight**: the project is a repository, not a harness, and the `grill` and
   `critique` extensions are installed.
2. **premise**: before any spec is written, six questions about the issue (what
   goes wrong if it is never done, whether that can happen today, whether the change
   alters it, what already owns the risk, whether the premise is inherited, whether
   the work has decisions in it). They are answered in your session, each with a
   source, and you pick one of three outcomes: `write the spec`, `no spec needed`,
   `not worth doing`. `premise_report.py` checks the report against your pick.
3. **specify**: `speckit.specify` writes `spec.md` into `specs/<issue>-<short-name>`.
   The spec carries the premise answers and a `## Root cause` section: for a defect,
   the trace from what was observed to the module where the wrong decision is made.
   `rootcause.py` and `premise_report.py spec` check both.
4. **grill**: `/speckit-grill-me`, in your session, until every question is
   answered. No `NEEDS CLARIFICATION` marker may remain, and the root cause and
   premise answers are checked again.
5. **plan**: `speckit.plan`. `plan.md` lists every mechanism it builds or changes,
   each citing a `research.md` decision that records what was chosen, why, and the
   existing tools looked at (`settled_design.py`).
6. **critique**: `speckit.critique.run`; you accept or reject its findings.
7. **tasks**: `speckit.tasks`.

`not worth doing` ends the run and names the close for you to make: Whetstone
closes no issue. `no spec needed` writes a `spec.md` that says so, with the question
it rests on and the reason, so that a later scope of the issue sees it was judged.

**It writes the spec folder and nothing else.** It commits nothing, pushes nothing,
and posts nothing on GitHub. The skill reads the issue with your own `gh`; no step
of the workflow reaches GitHub.

## Run

From an agent session (Claude Code), in the repository, on the branch you want the
spec on:

```
/speckit-whetstone-plan-scope #123
/speckit-whetstone-plan-scope rescope specs/123-ledger-binding #123
```

The skill drives the run with `scripts/drive.py`, answers the premise with you,
runs grill with you, and passes your verdicts on resume. It never gives a verdict
you did not give. Each headless step can take up to about ten minutes.

A change with no issue yet: open one first (`gh issue create`), then scope it.

## Requirements

- The `whetstone-planner` bundle, installed **in the repository** you plan in, from its
  root: `sh install.sh --plan`. It is separate from the review, so the planning
  machine needs nothing the review does (no sandbox, no `uv`, no `base_ref`), and a
  review machine never gets the planner. Both can share a repository. A harness
  cannot plan: planning writes into the repository, and a harness exists so that
  nothing is written there; `install.sh --plan` refuses one.
- Two Spec Kit community extensions. They are part of neither Spec Kit nor Whetstone,
  and Spec Kit's catalog lists them as discovery-only, not vetted. Read each, then
  install it from an archive you have checked, or from a local copy:

  | Extension | Author | Command the run needs |
  |---|---|---|
  | `grill` | [yoshi1220/speckit-grill-me](https://github.com/yoshi1220/speckit-grill-me) | `speckit.grill.me` (run in your session) |
  | `critique` | [arunt14/spec-kit-critique](https://github.com/arunt14/spec-kit-critique) | `speckit.critique.run` (a step of the workflow) |

  ```bash
  specify extension add grill --from <archive-url>      # or: --dev <folder>
  specify extension add critique --from <archive-url>
  ```

  Commit what they install, like the rest of `.specify/` and `.claude/`.
- `gh`, logged in, to read the issue.

## The lockdown does not apply

A review's agents run in Claude Code's sandbox with the working directory
read-only (repository README, *Lock down Claude Code*). Planning agents must write
the spec folder, so they do not run under that lockdown. `drive.py` gives them
its own arguments in place of whatever the shell exports: `--setting-sources
project` and an allow-list of tools (read, write and edit files; run Spec Kit's own
scripts under `.specify/`; `ls`, `cat`, `mkdir`, `date`). That keeps them to the
work of writing a spec. It is not a sandbox. Run planning where you work, and watch
it: the agents read the issue's text and the code, as you would.

## What it leaves behind

- The spec folder, uncommitted. Review it and commit it yourself.
- `.specify/feature.json`, Spec Kit's pointer to the current spec, which Spec Kit's
  own commands (`/speckit-implement` and the rest) read. Where the review is
  installed too, a review refuses to start while any file under `.specify/` differs
  from `HEAD`, so delete it before the next review once you no longer need it.
- The run's state under `.specify/workflows/runs/`, which the install's `.gitignore`
  already excludes.

`drive.py` runs Spec Kit with `PYTHONPYCACHEPREFIX` set (yours, or
`~/.cache/whetstone-pyc`), and every script runs as `python3 -I -B`. So no compiled
Python lands under `.specify/`, which a review in the same repository would refuse.
Without that prefix, Spec Kit would compile the review's `decision` step there on
every planning run.

## The settled-design preset

The `whetstone-planner` bundle also installs the `whetstone-settled-design` preset,
which the workflow's checks rely on. It adds to Spec Kit's spec template the `## Why this is worth doing`
and `## Root cause` sections, and to the plan template a `## Mechanisms` section and
the `research.md` decision format. Like any preset, it applies to every
`/speckit-specify` and `/speckit-plan` in the project, not only to planning runs.
Without a premise report, `speckit.specify` leaves the two sections for you to
fill in.

## Contract

- **Inputs** (`specify workflow run whetstone-plan`, which `drive.py` passes):
  `spec` (the issue's text), `issue`, `spec_dir` (`specs/<issue>-<short-name>`),
  `kind` (`new` or `rescope`); `premise_verdict`, `grill_verdict`,
  `critique_verdict` on resume.
- **Writes:** `spec_dir`, and `.specify/feature.json`. In the run's folder under
  `.specify/workflows/runs/<run id>/`: the premise report the skill writes, and the
  critique baseline.
- Every check prints one problem per line, each naming its next step, and exits 1;
  it exits 2 when it could not run.

## Origin

Ported from the `planner` plugin of
[analitiq-ai/claude-plugins-internal](https://github.com/analitiq-ai/claude-plugins-internal)
(commit `7e63882`), and relicensed under Whetstone's MIT license (see `NOTICE.md`).
The port keeps the workflow, the preset and the checks. It drops what tied them to
that project: the GitHub App that created story issues, committed the spec and
opened its pull request, the project-board lanes, and the `codeworks` front matter.
