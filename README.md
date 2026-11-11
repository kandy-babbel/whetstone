# Whetstone

Whetstone sharpens a branch before people review it. It is a Spec Kit bundle that:
- reviews the branch with pr-review-toolkit;
- dismisses bikeshedding with a decision model;
- checks whether each fix should be a patch or a class fix;
- applies fixes within the PR's files.

It repeats until nothing important is left. Fixes are committed locally; nothing is
pushed or posted.

## The name

A whetstone is a stone for sharpening blades. The word comes from Old English
*hwetstān*: *hwettan*, "to sharpen" (as in "whet your appetite"), plus *stān*,
"stone". It has nothing to do with "wet". Some whetstones are soaked or oiled
before use, which is why "wetstone" is a common misspelling.

A whetstone does not make the blade. It takes off burrs and dull spots, pass by
pass, until the edge is ready. Whetstone does not write the change either. It
takes a branch someone wrote and works on it, round by round, until it is ready
for people to review.

## How it works

Each round:

1. **review**: pr-review-toolkit's agents review the branch.
2. **triage** (switchable): a decision model dismisses bikeshedding findings.
3. **shim check** (switchable): for each remaining finding, an agent finds where else
   the defect occurs and decides between a local fix, a class fix, or a smaller fix
   than suggested.
4. **apply**: an agent fixes, rejects, defers or escalates each finding, within the
   PR's files. The loop then runs the repository's checks itself, checks the changes
   against the decisions and the PR's files, and commits locally.

The loop ends when no Critical or Important finding is left, or after three rounds
with a gate for a human. Nothing is pushed or posted.

## What leaves your machine

- **Claude:** the review, shim-check and apply agents run in Claude Code and read the
  repository as Claude Code does.
- **Triage (on by default):** for each Critical or Important finding, an evidence file
  goes to the decision step's Jev backend at api.typesafe.ai. The file holds the finding,
  the code around it, and the rule, config and CI files named in
  `whetstone-triage-config.yml`. Only files tracked by git are included. Triage needs
  `TYPESAFE_API_KEY`; without it the run stops before the review starts. Run with
  `--input triage=false` to keep code from going to api.typesafe.ai.

## Components

| Component | Kind | README |
|---|---|---|
| `whetstone-core` | extension | [contracts and the deterministic checker](extensions/whetstone-core/README.md) |
| `whetstone-review` | extension + workflow | [review step](extensions/whetstone-review/README.md) |
| `whetstone-triage` | extension + workflow | [bikeshedding triage](extensions/whetstone-triage/README.md) |
| `whetstone-shim-check` | extension + workflow | [patch or class fix](extensions/whetstone-shim-check/README.md) |
| `whetstone-apply` | extension + workflow | [fixes and checks](extensions/whetstone-apply/README.md) |
| `whetstone` | workflow | composes the modules ([bundle README](bundle/README.md)) |
| `decision` 0.9.0 | workflow step | community step, [markuswondrak/spec-kit-decision-step](https://github.com/markuswondrak/spec-kit-decision-step) |

The modules exchange JSON files under `.review/current/`. Each file has a JSON
Schema in `whetstone-core`. Each module workflow also runs on its own, or from
another workflow through a `workflow` step.

## Install in a repository

**1. Commit or stash your work.** The loop needs a clean working tree.

**2. Register the catalogs and install the bundle:**

```bash
specify init --here --integration claude --script sh      # if not a Spec Kit project yet
C=https://raw.githubusercontent.com/kandy-babbel/whetstone/main/catalog
specify bundle catalog add $C/bundles.json --id whetstone
specify extension catalog add $C/extensions.json --name whetstone --install-allowed --priority 1
specify workflow catalog add $C/workflows.json --name whetstone
specify workflow step catalog add $C/steps.json --name whetstone
specify bundle install whetstone --version 0.3.0
```

Adding the extension, workflow and step catalogs is a trust decision. Spec Kit
installs from them without asking, including the `decision` step's Python code. The
step catalog pins `decision` 0.9.0 by its hashes.

Adding a project catalog of these kinds **hides Spec Kit's built-in ones** for this
project. To keep installing official extensions, workflows and steps, add the
defaults back:

```bash
G=https://raw.githubusercontent.com/github/spec-kit/main
specify extension catalog add $G/extensions/catalog.json --name default --install-allowed --priority 2
specify workflow catalog add $G/workflows/catalog.json --name default
specify workflow step catalog add $G/workflows/step-catalog.json --name default
```

The community catalogs are discovery-only by default. `catalog add` would make them
install-allowed, so add them to `.specify/*-catalogs.yml` by hand with
`install_allowed: false` if you want them.

**3. Configure.** Edit the three files the install created. Each one explains its
settings in comments.

| File | Sets |
|---|---|
| `.specify/extensions/whetstone-core/whetstone-core-config.yml` | `base_ref`, the branch PRs merge into |
| `.specify/extensions/whetstone-triage/whetstone-triage-config.yml` | what the triage evidence contains |
| `.specify/extensions/whetstone-apply/whetstone-apply-config.yml` | `checks`, commands that must pass |

**4. Ignore Spec Kit's and Whetstone's working files** in `.gitignore`:

```gitignore
.review/
.specify/workflows/runs/
.specify/**/.cache/
.specify/.*.lock
```

**5. Commit everything else** the install created under `.specify/` and `.claude/`,
and `.gitignore`.

A run refuses to start on a dirty working tree, or when `.review/` is not ignored.
Each round commits with `git add -A` and refuses changes that no fix claims, so
anything left over would otherwise end up in a round's commit or fail it.

**6. Run:** see [bundle/README.md](bundle/README.md#run). Each run starts fresh; an
earlier run's files move to `.review/previous/`.

## Release (maintainers)

1. Set the same version in every `extensions/*/extension.yml`, every
   `workflows/*.yml`, and in `bundle/bundle.yml`, both its own version and the
   versions it pins.
2. Build:
   ```bash
   python3 tools/build.py \
     --assets-url https://github.com/kandy-babbel/whetstone/releases/download/v0.3.0 \
     --catalog-url https://raw.githubusercontent.com/kandy-babbel/whetstone/main/catalog
   ```
   This empties `dist/`, then writes the extension zips (each with `LICENSE`), the
   workflow files and the bundle zip there. It also rewrites the catalogs in
   `catalog/` with each file's sha256. The version a catalog entry replaces moves to
   the entry's `releases`, so earlier versions stay installable with `--version`.
3. Create release `v0.3.0` with every file in `dist/` as an asset.
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
extensions/<id>/          one Spec Kit extension each (manifest, README, prompts, scripts)
workflows/                the module workflows and whetstone
bundle/                   bundle manifest and README
catalog/                  the catalogs Spec Kit reads (generated, except steps.json)
tools/build.py            builds dist/ and catalog/
```
