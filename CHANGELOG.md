# Changelog

## 0.6.1

- **The claim check runs 16 judges and 8 readers at a time,** up from 4 each. A
  change with hundreds of claims spent most of its time waiting for a judge slot.
  The numbers are the `max_concurrency` of the claim check's two fan-outs; the
  claim-check README says where to change them and what a rate limit does to a run.

## 0.6.0

- **The repository's conventions reach the review.** The agents run with `CLAUDE.md`
  excluded, so the branch under review cannot instruct its own reviewers; until now
  that also kept the repository's rules from them. `setup` now copies every
  `CLAUDE.md` in the tree and the Markdown files under `.claude/rules/`, as they are
  on the base commit, to `.review/current/conventions/` (listed in
  `conventions.txt`, recorded in `report.json`), following links inside the tree and
  skipping a link that leaves it. The reviewer reads them as the repository's rules
  and checks the change against them; triage evidence includes them. Nothing to
  configure, in either layout. New `repo.py` functions `conventions`, `tree_entries`
  and `blob`.
- **`install.sh`.** One command installs Whetstone: `sh install.sh` in a repository,
  `sh install.sh --harness <repository>` for a harness around a clone. It registers
  the catalogs (Whetstone's and Spec Kit's own), installs the pinned bundle version,
  adds the `.gitignore` lines, deletes compiled Python under the install, pins `uv`
  in `.prototools` when it comes from proto, sets `base_ref` from `origin/HEAD`
  (`--base-ref` overrides), and in a harness makes the commit and the clone. It is
  safe to run again and commits nothing in a repository of yours. The README's
  install section is built around it; the commands it runs stay listed under "By
  hand".

## 0.5.0

- **Review from a harness.** Whetstone can run from a small repository of your own,
  with the repository under review cloned into it as `repo/`: for repositories you may
  not add files to. Nothing of Whetstone enters that repository, not even an object in
  its `.git`; its branches cannot reach Whetstone's own files. `setup` checks that
  `repo/` is a plain local clone (no link, no worktree), records its branch and `HEAD`,
  and the guard before every agent step checks both again. Agents read the clone under
  `repo/` and report paths relative to it; the core maps a `repo/`-prefixed path back.
  The canary also tries to write `repo/` and `repo/.git`. The in-repository layout is
  unchanged. New core script `repo.py`.
- **The change is recorded once.** `setup` builds the tree of the change in a
  temporary index and a throwaway object store under `.review/` (the repository's
  `.git` gains no object), and writes its diff to `.review/current/diff.patch`. The
  review agents review that diff; their answer must name the recorded `HEAD` and list
  every file of the change (`files_reviewed`, new in `findings.schema.json`), or it is
  refused. The claim check verifies the tree it builds is the one `setup` recorded.
- **Per-branch history.** `.review/previous/` holds only runs of the branch under
  review; other branches' runs wait under `.review/archive/<branch>/`. The report
  records `root`, `branch`, `head` and `tree`.
- **Compiled Python refused.** Python runs a `.pyc` in `__pycache__` in place of the
  script next to it, even under `-I`. Whetstone's own steps pass `-X pycache_prefix`,
  the lockdown requires `PYTHONPYCACHEPREFIX` (outside the working directory and
  `TMPDIR`), and the integrity check refuses compiled Python under `.claude/` and
  `.specify/`, tracked or not.
- **A change that touches `.claude/` or `.specify/` is refused** in the in-repository
  layout, unless run with `--input allow_protected=true`: those directories hold what
  Whetstone runs, and a branch could otherwise commit a replacement.
- **`sandbox.autoAllowBashIfSandboxed: true` is required.** Claude Code 2.1.329
  stopped allowing sandboxed commands by default; without the setting every command
  of a `claude -p` agent is refused, which the canary reports. `permissions.allow`
  must be empty.
- Triage's evidence gatherer reads the repository under review through pinned git.

## 0.4.0

- **Whetstone now only reads.** It no longer fixes findings, runs the repository's
  checks or commits: the `whetstone-apply` extension and workflow, `check-apply`, the
  claim check's fix step and the fix loop are gone. A run reviews the change from the
  merge-base with `base_ref` to the working tree (uncommitted changes included) and
  writes `.review/report.json` for the person, or the separate agent, who fixes it.
  Two adversarial reviews of the earlier design showed that an agent allowed to edit
  the repository could reach the files the loop trusted; a reviewer that can only read
  removes that whole class.
- New module `whetstone-claim-check` (extension; workflows `whetstone-claim-check`,
  `whetstone-claim-read`, `whetstone-claim-judge`), adapted from the reviewer plugin's
  claim check in analitiq-ai/claude-plugins-internal. Readers quote every claim the
  change's text makes (categories K1-K9); a judge per K1 claim (what the repo's own
  code does) or K9 claim (what a test checks) tries to break it, citing `path:line`
  evidence checked against the exact tree. Each reader and judge runs as its own
  workflow with `continue_on_error`: one that fails, answers badly or is cut off leaves
  its files `unread` or its claim `unjudged`, never counted as correct. Readers and
  judges run on Sonnet by default (`claim_model`). New contract `claim-check.json`
  (`claim-check.schema.json`, `whetstone.claim-check/1`).
- A gate shows every WRONG claim (with failing case and evidence), unread file and
  unjudged claim before the run ends; agent-written text is cleaned of control, format
  and separator characters and capped. The ledger records `claims_wrong`,
  `claim_notes`, `unread`, `unjudged`, `follow_ups`, `dismissed`, `warnings` and the
  gate's answer.
- Agents answer on standard output. Whetstone reads each answer from Spec Kit's run
  state (`runstate.py`), finding the step by the command or prompt Spec Kit recorded;
  `.review-inbox/` is gone.
- Lockdown (`lockdown.py`), checked by `setup` and by a guard before every agent step:
  - `SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS` must carry `--settings` with the sandbox
    on, `allowUnsandboxedCommands` off, `failIfUnavailable` on, hooks off,
    `claudeMdExcludes` for `CLAUDE.md`, and `permissions.deny` `Edit(./**)`, plus
    `--strict-mcp-config` and `--output-format json`; no skip-permissions flags,
    `bypassPermissions` or `auto`; `SPECKIT_INTEGRATION_CLAUDE_EXECUTABLE` unset.
  - `TMPDIR` must be set, short, and empty at `setup`: one per run.
  - `.claude/` and `.specify/` must equal `HEAD`.
  - The canary tries to write the repository itself as well as `.git`, `.review`,
    `.specify`, `.claude` and `~/.claude`; the paths come from the nonce, never from
    the agent's answer.
  - Whetstone's own steps run `python3 -I` and `uv run --isolated --no-config
    --no-project`; its git calls ignore user and system configuration and run no hooks
    or file system monitor; the claim check's temporary index lives under `.review/`.
  - Every step that touches `.review/` checks it belongs to the run that set it up.
- `whetstone-apply-config.yml` and its `checks` are no longer read. `.review-inbox/`
  and `bwrap` are no longer required; `.specify/workflows/runs/` must be ignored.

## 0.3.0

- Renamed from prloop to Whetstone:
  - ids `prloop-*` become `whetstone-*`;
  - the main workflow `pr-review-loop` becomes `whetstone`;
  - schema versions `prloop.*/1` become `whetstone.*/1`;
  - `prloop.py` becomes `whetstone.py`.
- The scope module is renamed to shim check: extension and workflow
  `whetstone-shim-check`, file `shim-check.json`, schema version
  `whetstone.shim-check/1`, loop input `shim_check`.
- Repository settings move out of the extensions into files the repository owns:
  `whetstone-core-config.yml` (`base_ref`, previously fixed to `origin/main`),
  `whetstone-triage-config.yml` (previously `triage-config.yml`, now with
  `ci_run_prefixes`), and `whetstone-apply-config.yml` (previously `checks.yml`).
  Spec Kit creates them from templates on install and never overwrites them.
- MIT licensed (`LICENSE`).
- Checks are verified: after the apply agent, the `checks` step runs every configured
  command itself and fails the round if one fails.
- A run refuses to start on a dirty working tree, an un-ignored `.review/`, or triage
  without `TYPESAFE_API_KEY`. An earlier run moves to `.review/previous/`, and the base
  is recomputed every run.
- Triage reads only files tracked by git, and runs through `uv`.
- Commits run the repository's hooks (no `--no-verify`).
- Paths are read with `git -z`; ledger entries are recorded once even when a step is retried.
- The bundle declares the Claude integration and the tools it needs.
- The build adds sha256 digests and release history to the catalogs, publishes a bundle
  catalog, and puts `LICENSE` in every extension zip.
- `decisions.json` `tests` may be empty, for repositories with no checks.

## 0.2.1

- `check-apply` checks the whole working tree:
  - no existing file outside the PR may change;
  - every change must be claimed by a fix.
- A class fix that leaves an in-PR occurrence untouched is a warning, not a failure.
- Follow-ups are recorded only for findings that were fixed or deferred.

## 0.2.0

- First modular version: review, triage, scope and apply modules with JSON
  Schema contracts.
