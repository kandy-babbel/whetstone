# Changelog

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
