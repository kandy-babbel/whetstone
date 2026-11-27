# Whetstone

Whetstone sharpens a change before people review it. It is a Spec Kit bundle that
reads a repository and reports:
- the review findings of pr-review-toolkit;
- which of them are bikeshedding, decided by a decision model;
- for each remaining finding, whether the fix should be a patch or a class fix, and
  where else the defect occurs;
- which claims the change's comments, docs and test names make about the code, and
  which of those claims are wrong.

Whetstone **changes nothing**: it never edits the repository, runs its tests or
commits. The report in `.review/report.json` is for the person, or the separate agent,
who fixes the change; run Whetstone again on the result. That split is what makes the
lockdown below hold: the agents that judge a change can only read it.

It runs in one of two layouts:
- **in a repository**: Whetstone is installed and committed in the repository it
  reviews ([Install](#install));
- **from a harness**: Whetstone lives in a small repository of your own, and the
  repository under review is a local clone next to it. Nothing of Whetstone enters
  that repository, not even an object in its `.git`. For repositories you cannot add
  files to ([Review from a harness](#review-from-a-harness)).

## The name

A whetstone is a stone for sharpening blades. The word comes from Old English
*hwetstān*: *hwettan*, "to sharpen" (as in "whet your appetite"), plus *stān*,
"stone". It has nothing to do with "wet". Some whetstones are soaked or oiled
before use, which is why "wetstone" is a common misspelling.

A whetstone does not make the blade. It takes off burrs and dull spots, pass by
pass, until the edge is ready. Whetstone does not write the change either, nor fix
it. It shows where the edge is still dull.

## How it works

One run, on the change from the merge-base with `base_ref` to the working tree
(committed and uncommitted changes, new files included):

1. **setup**: checks the lockdown (next sections), that `.claude/` and `.specify/`
   are exactly what `HEAD` records, and where the repository is; records its branch,
   `HEAD`, the base commit, the tree of the change, its diff
   (`.review/current/diff.patch`) and its files (`pr-files.txt`); copies the
   repository's conventions, every `CLAUDE.md` and the files under `.claude/rules/`
   as they are on the base commit, to `.review/current/conventions/`.
2. **canary**: a short agent run that tries to write the repository and the other
   protected paths. The run stops if any write succeeds.
3. **review**: pr-review-toolkit's agents review that diff against the repository's
   conventions.
4. **triage** (switchable): a decision model dismisses bikeshedding findings.
5. **shim check** (switchable): for each remaining Critical or Important finding, an
   agent names the defect class, finds its other occurrences, and decides between a
   local fix, a class fix, or a smaller fix than suggested. Occurrences outside the
   change's files become follow-ups.
6. **claim check** (switchable): readers quote every claim the change's text makes;
   a judge per claim about the repo's own code (K1) or about what a test checks (K9)
   tries to break it, citing `path:line` evidence that is checked against the tree.
7. **report**: `.review/report.json`. If a claim is WRONG, a file could not be read or
   a claim could not be judged, a gate shows them to you before the run ends.

Nothing is pushed or posted. Every agent answers on its standard output; Spec Kit
keeps the answer in the run state, and Whetstone's own steps take it from there.

## What leaves your machine

- **Claude:** the canary, review, shim-check, reader and judge agents run in Claude
  Code and read the repository as Claude Code does.
- **Triage (on by default):** for each Critical or Important finding, an evidence file
  goes to the decision step's Jev backend at api.typesafe.ai. The file holds the finding,
  the code around it, the repository's conventions `setup` recorded, and the rule,
  config and CI files named in `whetstone-triage-config.yml`. Only files tracked by
  git are included. Triage needs
  `TYPESAFE_API_KEY`; without it the run stops before the review starts. Run with
  `--input triage=false` to keep code from going to api.typesafe.ai.

## Components

| Component | Kind | README |
|---|---|---|
| `whetstone-core` | extension | [contracts, the checker, the lockdown rules](extensions/whetstone-core/README.md) |
| `whetstone-review` | extension + workflow | [review step](extensions/whetstone-review/README.md) |
| `whetstone-triage` | extension + workflow | [bikeshedding triage](extensions/whetstone-triage/README.md) |
| `whetstone-shim-check` | extension + workflow | [patch or class fix](extensions/whetstone-shim-check/README.md) |
| `whetstone-claim-check` | extension + workflows | [claims checked against the code](extensions/whetstone-claim-check/README.md); `whetstone-claim-read` and `whetstone-claim-judge` run one reader or judge each |
| `whetstone-canary` | workflow | the lockdown canary ([lockdown](#lock-down-claude-code)) |
| `whetstone` | workflow | composes the modules ([bundle README](bundle/README.md)) |
| `decision` 0.9.0 | workflow step | community step, [markuswondrak/spec-kit-decision-step](https://github.com/markuswondrak/spec-kit-decision-step) |

The modules exchange JSON files under `.review/current/`. Each file has a JSON
Schema in `whetstone-core`. Each module workflow also runs on its own, or from
another workflow through a `workflow` step.

## Install

**Requirements.**

- **Linux**, with Claude Code's sandbox working: it uses bubblewrap (`bwrap`,
  Debian/Ubuntu: `apt install bubblewrap`) and unprivileged user namespaces. The
  canary at the start of every run tells you if it does not.
- Spec Kit 1.3.3 or later (`uv tool install specify-cli --from
  git+https://github.com/github/spec-kit.git`); Claude Code 2.1.329 or later with the
  `pr-review-toolkit` plugin enabled.
- `git`, `python3` and `uv`.
- For triage, `TYPESAFE_API_KEY` (see [What leaves your machine](#what-leaves-your-machine)).

**One command.** [`install.sh`](install.sh) does the whole install. Download it and
read it first: it runs Spec Kit, git and the shell, nothing else, and it is safe to
run again.

```bash
curl -fsSLO https://raw.githubusercontent.com/kandy-babbel/whetstone/main/install.sh
```

*In a repository you may add files to*, from its root:

```bash
sh install.sh
git add -A && git commit -m "Install Whetstone"       # on the branch other branches start from
```

*For a repository you may not add files to*, such as a company repository, in a
harness of your own (see [Review from a harness](#review-from-a-harness)):

```bash
sh install.sh --harness git@github.com:org/app.git    # makes ./whetstone-app, commits the install, clones the repository into repo/
cd whetstone-app
```

The script registers the catalogs (Whetstone's and Spec Kit's own, so the official
extensions stay installable), installs the pinned bundle version, ignores the working
files, deletes compiled Python under the install, pins `uv` in `.prototools` when
`uv` comes from proto, and sets `base_ref` to the branch `origin/HEAD` names
(`--base-ref` overrides it). It commits nothing in a repository of yours. Then
[lock down the agents](#lock-down-claude-code) and run.

**Upgrading.** Download the new `install.sh` and run it the way you first did, in
the same place (in a harness, `sh install.sh --harness <repository>` from the
directory that holds the harness). It points the catalogs it registered at the new
ones, replacing a catalog of the same name whose URL differs, and updates the bundle
in place with `specify bundle update`. Your two config files and the `base_ref` in
them are kept; `--base-ref` still overrides it. Then read the
[changelog](CHANGELOG.md) for flags you must export again. By hand, remove and
re-add the catalogs, then run `specify bundle update whetstone`: `bundle install`
refuses a bundle that is already installed.

**What the install is.** Spec Kit installs from the catalogs without asking,
including the `decision` step's Python code; adding them is a trust decision. The
step catalog pins `decision` 0.9.0 by its hashes. The install creates two files you
own and may edit; each explains its settings in comments:

| File | Sets |
|---|---|
| `.specify/extensions/whetstone-core/whetstone-core-config.yml` | `base_ref`, the branch PRs merge into |
| `.specify/extensions/whetstone-triage/whetstone-triage-config.yml` | what the triage evidence contains |

**Why it is committed.** A run refuses to start unless `.claude/` and `.specify/`
are exactly what `HEAD` records: they hold the skills, workflows and scripts the
agents and Whetstone's own steps run from, so a stray file there, tracked or not,
stops the run. It also refuses a change under review that touches those directories
(`--input allow_protected=true` overrides that, for when you change Whetstone's own
files on purpose). Your own uncommitted changes elsewhere are fine; they are the
change under review. Whetstone also refuses compiled Python under `.specify/` and
`.claude/`, tracked or not: Python would run it in place of the script next to it.
With `PYTHONPYCACHEPREFIX` exported (next section) none is created.

<details>
<summary><b>By hand</b>, what the script does</summary>

```bash
specify init --here --integration claude --script sh      # if not a Spec Kit project yet
C=https://raw.githubusercontent.com/kandy-babbel/whetstone/main/catalog
specify bundle catalog add $C/bundles.json --id whetstone
specify extension catalog add $C/extensions.json --name whetstone --install-allowed --priority 1
specify workflow catalog add $C/workflows.json --name whetstone
specify workflow step catalog add $C/steps.json --name whetstone
G=https://raw.githubusercontent.com/github/spec-kit/main                 # Spec Kit's own catalogs back:
specify extension catalog add $G/extensions/catalog.json --name default --install-allowed --priority 2
specify workflow catalog add $G/workflows/catalog.json --name default    # a project catalog hides them
specify workflow step catalog add $G/workflows/step-catalog.json --name default
specify bundle install whetstone --version 0.7.1
```

Then add to `.gitignore` (and `repo/` in a harness):

```gitignore
.review/
.specify/workflows/runs/
.specify/**/.cache/
.specify/.*.lock
__pycache__/
```

Delete any `__pycache__` directory under `.specify/` (installing the `decision` step
compiles its Python), set `base_ref` in the core config, pin `uv` in `.prototools`
if it comes from proto, and commit. The community catalogs are discovery-only by
default; `catalog add` would make them install-allowed, so add them to
`.specify/*-catalogs.yml` by hand with `install_allowed: false` if you want them.

</details>

## Review from a harness

For a repository you may not add files to, such as a company repository, Whetstone
runs from a **harness**: a small git repository of your own that holds the install,
with the repository under review cloned into it as `repo/`. The company repository
never sees Whetstone: no file in its working tree, nothing in its `.git`, no change
to its `.gitignore`. Its branches cannot change Whetstone's own files either, because
those are not in that repository.

`sh install.sh --harness <repository> [dir]` makes one: the directory (default
`whetstone-<name>`), the install, `repo/` ignored, one commit, and a plain local
clone at `repo/` (never a worktree). A harness serves one repository.

To review a branch:

```bash
git -C repo fetch && git -C repo checkout -B feature origin/feature
# then run Whetstone from the harness, as bundle/README.md#run shows
```

`setup` prints the clone's branch and `HEAD`, and the report records them. Review
runs of one branch keep their history in `.review/previous/`; other branches' runs
wait under `.review/archive/<branch>/` and come back when that branch is reviewed
again, so one branch's dismissals never silence findings on another.

What Whetstone checks about `repo/`, before every agent step: it is a directory, not
a link; `repo/.git` is a directory of its own, not a worktree's file; git agrees it is
the repository's root; its `HEAD` is the one `setup` recorded. Agents read the clone
under `repo/` and run git as `git -C repo`; they report paths relative to the clone's
root, and Whetstone's own steps map a path an agent wrote with the `repo/` prefix
back. Nothing is written into `repo/`: the tree of the change is built in a
throwaway object store under `.review/`, and the canary tries to write `repo/` and
`repo/.git` too.

Keep `.review/` and the run state out of any repository you push: the install's
`.gitignore` lines already exclude them.

## Lock down Claude Code

Whetstone's agents read code that someone else wrote, and that code may try to
talk to them. The lockdown makes sure that whatever an agent does, it can change
nothing Whetstone's own steps rely on: not the repository, not the scripts, not the
run state, not the report.

**Set this in the shell you run Whetstone from:**

```bash
export SPECKIT_INTEGRATION_CLAUDE_EXTRA_ARGS=$(cat <<'EOF'
--permission-mode acceptEdits --no-session-persistence --strict-mcp-config --output-format json --settings '{"sandbox":{"enabled":true,"allowUnsandboxedCommands":false,"failIfUnavailable":true,"autoAllowBashIfSandboxed":true},"disableAllHooks":true,"claudeMdExcludes":["**/CLAUDE.md","**/CLAUDE.local.md"],"permissions":{"allow":["Edit(//tmp/whet.*/**)"],"deny":["Edit(./**)"]}}'
EOF
)
export PYTHONPYCACHEPREFIX=$HOME/.cache/whetstone-pyc
```

Spec Kit adds these flags to every `claude -p` command it launches. Whetstone
requires each of them:

| Flag or setting | Why |
|---|---|
| `sandbox.enabled: true` | Every command an agent runs, and everything it starts, runs in Claude Code's sandbox. |
| `sandbox.allowUnsandboxedCommands: false` | No command may run outside the sandbox. |
| `sandbox.failIfUnavailable: true` | If the sandbox cannot start, the agent's commands fail instead of running unsandboxed. Without this setting they run unsandboxed, silently. |
| `sandbox.autoAllowBashIfSandboxed: true` | A command runs without a permission prompt because the sandbox confines it. Since Claude Code 2.1.329, without this setting every command of a `claude -p` agent is refused for want of a prompt; the canary then stops the run. |
| `permissions.deny: ["Edit(./**)"]` | The whole working directory. Inside the sandbox it is mounted read-only, so neither the agent's file tools nor any command it runs can write it; `.git`, `.specify`, `.claude`, `.review` and the clone under `repo/` included. It must be this exact pattern: `Edit(**)` does not make the sandbox mount anything read-only. |
| `permissions.allow: ["Edit(//tmp/whet.*/**)"]` | Exactly this, nothing else. The agents' file tools may write only in a run's `TMPDIR`, where the claim check's readers and judges draft their answers: the shell refuses JSON in a heredoc, so the Write tool is the only way to make a draft. Claude Code checks the rule at a path's real location: a link planted there that leads elsewhere, or into the working directory, is refused. |
| `disableAllHooks: true` | A hook in the repository's `.claude/settings.json` would run outside the sandbox. |
| `claudeMdExcludes` | A `CLAUDE.md` in the repository is not loaded as instructions: the change under review could have edited it. The repository's conventions reach the agents another way, see [The repository's conventions](#the-repositorys-conventions). |
| `--strict-mcp-config` | A `.mcp.json` in the repository does not start a server outside the sandbox. |
| `--output-format json` | The agent's answer comes back as structured output, with its error state. |
| `--permission-mode acceptEdits` | Not `bypassPermissions` or `auto`, which Whetstone refuses. |
| `PYTHONPYCACHEPREFIX` | Python keeps compiled files there, outside the working directory and `TMPDIR`, and never reads a `.pyc` planted next to a script. Whetstone's own steps also pass `-X pycache_prefix`. |

Also required: **a fresh `TMPDIR` per run, made with `mktemp -d /tmp/whet.XXXXXX`**
(see [Run](bundle/README.md#run)). Agents can write their temporary directory, so
each run gets its own, and nothing Whetstone's own steps do reads it. It must be a
directory `/tmp/whet.*`, which is what the allow rule above covers, and short: the
sandbox needs a path under 60 bytes.

**This affects only the agents Whetstone starts.** Claude Code itself does not read
the variable. Your own Claude Code sessions, in this repository or any other, are
unchanged, and nothing is written to your settings files. A `.claude/settings.json`
in the repository cannot weaken these flags: the inline `--settings` wins. In the
harness layout the clone's `.claude/` and `CLAUDE.md` are not loaded at all: Claude
Code reads them from its working directory, which is the harness.

### The repository's conventions

A repository's `CLAUDE.md` and `.claude/rules/` state the rules its code follows,
and a review should check the change against them. They are also text an agent
would obey, and the branch under review can edit them. Whetstone separates the two:

- The agents are launched with `CLAUDE.md` excluded, so the branch's version of it
  never becomes the reviewers' instructions.
- `setup` reads every `CLAUDE.md` in the tree and the Markdown files under
  `.claude/rules/` **from the base commit**, the merge-base with `base_ref`, which is
  content already merged. It follows links inside the tree (a `CLAUDE.md` that links
  to `AGENTS.md`, a `.claude/rules` that links to another directory) and refuses a
  link that leaves the repository. The copies go to `.review/current/conventions/`,
  listed in `conventions.txt`; `report.json` records the list.
- The reviewer reads them as the repository's rules for its code and checks the
  change against them; a finding a rule requires is not bikeshedding, and triage sees
  the same files. A change to one of these files on the branch is in the diff and is
  reviewed like any other file.

Nothing to configure: this works in both layouts, for any repository that has such
files, and needs no copy of them in the harness.

**What Whetstone checks** (it refuses to run otherwise):
- `setup`, and a guard step before every agent step, check the variable: exactly one
  inline `--settings` with all of the above, the required flags, and no
  `--dangerously-skip-permissions`, `bypassPermissions` or `auto`;
  `SPECKIT_INTEGRATION_CLAUDE_EXECUTABLE` unset; `TMPDIR` a directory `/tmp/whet.*`,
  not a link (empty at `setup`); `PYTHONPYCACHEPREFIX` set, outside the working directory and `TMPDIR`;
  `.claude/` and `.specify/` equal to `HEAD`, with no compiled Python; the repository
  under review where `setup` found it, with the same `HEAD`.
- At the start of each run, the **canary** agent runs a script that tries to create a
  file in the working directory, in `.git`, `.review`, `.specify`, `.claude`, `~/.claude`
  and, in the harness layout, in `repo/` and `repo/.git`. Whetstone checks that none of
  those files exists and that the agent's answer is the script's output for this run's
  nonce. If a write succeeded, the run stops and names it.
- The review's answer must name the `HEAD` `setup` recorded and list every file of the
  change (`files_reviewed`); a review that looked at another tree, or at nothing, is
  refused.

**What Whetstone does itself:**
- Its own steps run Python isolated (`python3 -I`, `uv run --isolated --no-config
  --no-project`), so nothing in the repository or your home directory is imported.
- Its own `git` calls ignore your and the system's git configuration and run no hooks
  and no file system monitor, so a repository's `core.hooksPath` or a planted config
  cannot run code.
- The tree of the change is built in a temporary index and a throwaway object store
  under `.review/`, not in the repository's `.git` and not in `TMPDIR`. The diff the
  agents review comes from that tree, so no agent has to compute it.
- Agents answer on standard output. Whetstone reads each answer from the run state
  under `.specify/workflows/runs/`, which agents cannot write, and finds a step by
  what Spec Kit recorded from the workflow, never by what the agent wrote.
- Every agent-written text shown to you (the gate, the report) has control, format
  and separator characters removed and is capped in length, so it cannot imitate the
  gate or hide a line.
- A reader or judge that fails, answers badly or is cut off leaves its files **unread**
  or its claim **unjudged**. Both go to the gate; neither counts as correct.

## What Whetstone guarantees, and what it does not

Given a working directory whose `.claude/` and `.specify/` equal `HEAD`, a trusted
shell, and the flags above, then during a run:
- the commands an agent runs cannot write the repository, its `.git`, your home
  directory, the scripts, the run state or the report;
- the report describes exactly the tree Whetstone's own step recorded, and names the
  branch and `HEAD` it came from;
- an agent that fails, answers badly or is cut off appears as UNREAD or UNJUDGED,
  never as CORRECT;
- a WRONG, unread or unjudged claim always stops at a gate;
- in the harness layout, nothing of Whetstone is in the repository under review, and
  no branch of it can alter what Whetstone runs.

Not covered:
- **The agents' judgement.** A judge reads the code it judges, and that code can be
  written to mislead it; a reader can miss a claim. This is the same limit a human
  reviewer has, and the reason the report is for a person.
- **What the clean working directory already contains.** A skill in `.claude/skills/`,
  a `.mcp.json` or a `.claude/settings.json` that you committed is trusted, like any
  code you committed. Whetstone's own skills are among them, so review that folder.
  In a repository, a branch that commits a change there is refused unless you allow
  it; in the harness layout the branch cannot reach it.
- **Your own tools.** Anything you run outside Whetstone, in the repository or the
  harness, runs with your rights: a package's install script or your own interactive
  Claude Code session could edit the install. A change shows as a difference from
  `HEAD`, which stops the next run, or as a commit in your history.
- **What agents can read.** The sandbox limits writes, not reads: an agent can read
  the whole clone, every branch in it, and files elsewhere on the machine that your
  user can read. Clone only what you want reviewed, and keep secrets out of the
  clone's `.git/config`.
- **Resuming a run from another shell.** `specify workflow resume` restarts at the
  step that stopped; the flags and `TMPDIR` must be the same as when the run started.
  Whetstone's guards check again before every agent step that follows, but not the
  step being resumed itself.
- **Agents' shared temporary directory.** Within a run, agents can read what earlier
  agents left in `TMPDIR`. Their file tools can also write another run's
  `/tmp/whet.*` directory owned by your user, since the allow rule names them all.
  Nothing Whetstone's own steps do reads any of them, and every answer is checked
  again by Whetstone's own steps, whatever a draft said.
- **Network access** from inside the sandbox. In the tests on this project it was
  refused, but Whetstone does not require a setting that guarantees that.

## Release (maintainers)

1. Set the same version in every `extensions/*/extension.yml`, every
   `workflows/*.yml`, and in `bundle/bundle.yml`, both its own version and the
   versions it pins.
2. Build:
   ```bash
   python3 tools/build.py \
     --assets-url https://github.com/kandy-babbel/whetstone/releases/download/v0.7.1 \
     --catalog-url https://raw.githubusercontent.com/kandy-babbel/whetstone/main/catalog
   ```
   This empties `dist/`, then writes the extension zips (each with `LICENSE`), the
   workflow files and the bundle zip there. It also rewrites the catalogs in
   `catalog/` with each file's sha256. The version a catalog entry replaces moves to
   the entry's `releases`, so earlier versions stay installable with `--version`.
3. Create release `v0.7.1` with every file in `dist/` as an asset.
   Never change a release's assets after publishing. Spec Kit checks each download
   against the catalog's sha256 and caches catalogs for an hour, so a changed file
   fails to install. Fix by releasing a new version.
4. Commit `catalog/` and push. Repositories with the catalogs registered see the
   new version.

`catalog/steps.json` is maintained by hand. It is a copy of the community catalog's
entry for the `decision` step, pinned to 0.9.0; the build fails if `bundle.yml` pins
another version.

The repository is public, so installing needs no GitHub login. For a private fork,
see Spec Kit's authentication guide (`~/.specify/auth.json`).

## Layout

```
install.sh                the installer, for a repository or a harness
extensions/<id>/          one Spec Kit extension each (manifest, README, prompts, scripts)
workflows/                the module workflows and whetstone
bundle/                   bundle manifest and README
catalog/                  the catalogs Spec Kit reads (generated, except steps.json)
tools/build.py            builds dist/ and catalog/
```
