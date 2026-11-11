# Changelog

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
