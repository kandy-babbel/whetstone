# Whetstone: planner (`whetstone-planner`)

Scopes a GitHub issue in a spec folder before it is built. It first asks whether the
issue is worth a spec at all, then runs Spec Kit's specify, grill, plan, critique and
tasks, and a check stands between each step and the next. It writes the spec folder
and nothing else: nothing is committed, pushed or posted.

This bundle installs apart from Whetstone's review (the `whetstone` bundle). Planning
runs where you work, in the repository you plan in; the review may run on another
machine, or in a harness. The two can also share a repository.

| Component | Kind | |
|---|---|---|
| `whetstone-plan` | extension | the checks, `drive.py`, and the `/speckit-whetstone-plan-scope` skill |
| `whetstone-plan` | workflow | premise → specify → grill → plan → critique → tasks |
| `whetstone-settled-design` | preset | the spec and plan sections the checks read; applies to every `/speckit-specify` and `/speckit-plan` in the project |

Install, from the repository's root: `sh install.sh --plan`. It also needs the
community `grill` and `critique` extensions, which you vet and install yourself.
Details: [`extensions/whetstone-plan/README.md`](../extensions/whetstone-plan/README.md).
