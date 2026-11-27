#!/bin/sh
# Installs Whetstone into a repository, or into a harness around a clone of one.
#
#   sh install.sh                                  # here, in a repository you may commit to
#   sh install.sh --harness <repository> [dir]     # a harness of your own around a clone
#
# Options:
#   --version V     the Whetstone bundle version to install (default: the one below)
#   --base-ref R    the branch pull requests merge into (default: the one already
#                   configured, else what origin/HEAD names, else origin/main)
#   --catalog URL   where the catalogs are (default: this release on GitHub)
#   --no-defaults   do not add Spec Kit's own catalogs back
#
# It runs only Spec Kit, git and the shell. It is safe to run again, and running it
# again over an older Whetstone upgrades it: the catalogs are pointed at --catalog and
# the bundle is updated in place, keeping your config. It commits nothing in a
# repository of yours; in a harness it makes the one commit that holds the install.
# Read it before you run it.
set -eu

VERSION=0.8.1
CATALOG=https://raw.githubusercontent.com/kandy-babbel/whetstone/main/catalog
SPECKIT=https://raw.githubusercontent.com/github/spec-kit/main
HARNESS=
TARGET=
BASE_REF=
DEFAULTS=1

say() { printf '%s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }
usage() {
    cat <<'USAGE'
Installs Whetstone into a repository, or into a harness around a clone of one.

  sh install.sh                                  # here, in a repository you may commit to
  sh install.sh --harness <repository> [dir]     # a harness of your own around a clone

Options:
  --version V     the Whetstone bundle version to install (default: the one below)
  --base-ref R    the branch pull requests merge into (default: the one already
                  configured, else what origin/HEAD names, else origin/main)
  --catalog URL   where the catalogs are (default: this release on GitHub)
  --no-defaults   do not add Spec Kit's own catalogs back

It runs only Spec Kit, git and the shell. It is safe to run again, and running it
again over an older Whetstone upgrades it: the catalogs are pointed at --catalog and
the bundle is updated in place, keeping your config. It commits nothing in a
repository of yours; in a harness it makes the one commit that holds the install.
Read it before you run it.
USAGE
}

while [ $# -gt 0 ]; do
    case $1 in
        --harness) [ $# -ge 2 ] || die "--harness needs the repository to clone"; HARNESS=$2; shift 2
                   if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then TARGET=$1; shift; fi ;;
        --version) [ $# -ge 2 ] || die "--version needs a value"; VERSION=$2; shift 2 ;;
        --base-ref) [ $# -ge 2 ] || die "--base-ref needs a value"; BASE_REF=$2; shift 2 ;;
        --catalog) [ $# -ge 2 ] || die "--catalog needs a URL"; CATALOG=$2; shift 2 ;;
        --no-defaults) DEFAULTS=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

# 0. Spec Kit takes catalogs over HTTPS only, localhost included; refuse anything
# else now, before a catalog is touched.
for u in "$CATALOG" "$SPECKIT"; do
    case $u in
        https://?*) ;;
        *) die "a catalog must be an https:// URL, not $u (Spec Kit refuses anything else)" ;;
    esac
done

# 1. Tools.
for t in git python3 uv specify; do
    command -v "$t" >/dev/null 2>&1 || case $t in
        specify) die "specify is missing. Install Spec Kit: uv tool install specify-cli --from git+https://github.com/github/spec-kit.git" ;;
        uv) die "uv is missing: https://docs.astral.sh/uv/getting-started/installation/" ;;
        *) die "$t is missing" ;;
    esac
done
command -v claude >/dev/null 2>&1 || say "note: claude is not on PATH; the runs need Claude Code 2.1.329 or later"
command -v bwrap >/dev/null 2>&1 || say "note: bwrap (bubblewrap) is not on PATH; Claude Code's sandbox needs it, and every run starts by checking it"

# 2. Where.
if [ -n "$HARNESS" ]; then
    [ -d "$HARNESS" ] && HARNESS=$(cd "$HARNESS" && pwd)     # a local path, before we move
    [ -n "$TARGET" ] || TARGET=whetstone-$(basename "$HARNESS" .git)
    [ -e "$TARGET" ] && [ ! -d "$TARGET/.git" ] && die "$TARGET exists and is not a git repository"
    mkdir -p "$TARGET"
    cd "$TARGET"
    [ -d .git ] || git init -q
    [ -e repo ] && [ ! -d repo/.git ] && die "repo/ exists and is not a clone"
    [ -L repo ] && die "repo/ is a symbolic link; Whetstone refuses that"
else
    [ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$(pwd -P)" ] || die "run this from the root of a git repository, or use --harness <repository>"
    [ -d repo ] && [ -d repo/.git ] && die "there is a clone under repo/: this looks like a harness, so run with --harness"
fi
ROOT=$(pwd)

# 2b. uv from proto needs a pinned version here, or every core step fails.
case $(command -v uv) in
    */.proto/shims/*|"${PROTO_HOME:-$HOME/.proto}"/shims/*)
        if ! grep -qs '^uv *=' .prototools; then
            UV=$(ls "${PROTO_HOME:-$HOME/.proto}/tools/uv" 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
            [ -n "$UV" ] || die "uv comes from proto but no version is installed: proto install uv"
            printf 'uv = "%s"\n' "$UV" >> .prototools
            say "note: uv comes from proto; pinned uv = $UV in .prototools (commit it)"
        fi ;;
esac

# 3. Spec Kit project.
if [ ! -d .specify ]; then
    specify init --here --force --non-interactive --integration claude --script sh --ignore-agent-tools
fi

# 4. Catalogs and the bundle.
# A catalog already registered under our name is replaced when its URL differs,
# and left alone when it is the same. Bundle and extension catalogs are removed by
# name, workflow and step catalogs by their index in the list.
catalog_url() {   # file key name -> "index url" of that entry, or nothing
    [ -f "$1" ] || return 0
    python3 -I - "$@" <<'EOF'
import sys
path, key, name = sys.argv[1:4]
entries, cur = [], None
for line in open(path, encoding="utf-8"):
    s = line.rstrip("\n")
    if s.startswith("- "):
        cur = {}
        entries.append(cur)
        s = "  " + s[2:]
    if cur is not None and s.startswith("  ") and not s.startswith("   ") and ":" in s:
        k, v = s.strip().split(":", 1)
        cur[k.strip()] = v.strip().strip("'\"")
for i, e in enumerate(entries):
    if e.get(key) == name:
        print(i, e.get("url", ""))
        break
EOF
}
add_catalog() {   # kind url -- add arguments (own variable names: sh functions share variables with their caller)
    ac_kind=$1 ac_url=$2; shift 3
    case $ac_kind in
        step) specify workflow step catalog add "$ac_url" "$@" ;;
        *) specify $ac_kind catalog add "$ac_url" "$@" ;;
    esac
}
set_catalog() {   # kind file key name url -- add arguments
    kind=$1 file=$2 key=$3 name=$4 url=$5; shift 6
    found=$(catalog_url "$file" "$key" "$name")
    was=
    if [ -n "$found" ]; then
        was=${found#* }
        [ "$was" = "$url" ] && return 0
        case $kind in
            bundle|extension) specify $kind catalog remove "$name" ;;
            workflow) specify workflow catalog remove "${found%% *}" ;;
            step) specify workflow step catalog remove "${found%% *}" ;;
        esac
    fi
    # Spec Kit can only refuse a catalog once the old one is gone (same name): put the old one back then.
    if ! add_catalog "$kind" "$url" -- "$@"; then
        if [ -n "$was" ] && add_catalog "$kind" "$was" -- "$@"; then
            die "Spec Kit refused the $kind catalog $url; the one it replaced ($was) is back in place"
        fi
        die "Spec Kit refused the $kind catalog $url${was:+, and the one it replaced ($was) could not be put back: add it again or run this again with a good --catalog}"
    fi
    [ -z "$was" ] || say "replaced the $kind catalog '$name' (was $was)"
}
set_catalog bundle .specify/bundle-catalogs.yml id whetstone "$CATALOG/bundles.json" -- --id whetstone
set_catalog extension .specify/extension-catalogs.yml name whetstone "$CATALOG/extensions.json" -- --name whetstone --install-allowed --priority 1
set_catalog workflow .specify/workflow-catalogs.yml name whetstone "$CATALOG/workflows.json" -- --name whetstone
set_catalog step .specify/step-catalogs.yml name whetstone "$CATALOG/steps.json" -- --name whetstone
if [ "$DEFAULTS" = 1 ]; then
    set_catalog extension .specify/extension-catalogs.yml name default "$SPECKIT/extensions/catalog.json" -- --name default --install-allowed --priority 2
    set_catalog workflow .specify/workflow-catalogs.yml name default "$SPECKIT/workflows/catalog.json" -- --name default
    set_catalog step .specify/step-catalogs.yml name default "$SPECKIT/workflows/step-catalog.json" -- --name default
fi

installed() {
    [ -f .specify/bundle-records.json ] || return 0
    python3 -I - <<'EOF'
import json
recs = json.load(open(".specify/bundle-records.json")).get("bundles", [])
print(next((b.get("version", "") for b in recs if b.get("bundle_id") == "whetstone"), ""))
EOF
}
CONFIG=.specify/extensions/whetstone-core/whetstone-core-config.yml
OLD=$(installed)
if [ "$OLD" = "$VERSION" ]; then
    say "Whetstone $VERSION is already installed here."
elif [ -n "$OLD" ]; then
    # bundle install refuses an installed bundle; update keeps the config files.
    say "Upgrading Whetstone $OLD to $VERSION."
    specify bundle update whetstone
    NOW=$(installed)
    [ "$NOW" = "$VERSION" ] || die "the catalog at $CATALOG gave Whetstone $NOW, not $VERSION; point --catalog at the $VERSION release"
else
    specify bundle install whetstone --version "$VERSION"
fi

# 5. Working files stay out of git; no compiled Python under the install.
touch .gitignore
for line in '.review/' '.specify/workflows/runs/' '.specify/**/.cache/' '.specify/.*.lock' '__pycache__/'; do
    grep -qxF -- "$line" .gitignore || printf '%s\n' "$line" >> .gitignore
done
for d in .specify .claude; do
    [ -d "$d" ] || continue
    find "$d" -name __pycache__ -type d -prune -exec rm -rf {} +
done

# 6. The clone, in a harness.
if [ -n "$HARNESS" ]; then
    grep -qxF -- 'repo/' .gitignore || printf 'repo/\n' >> .gitignore
    if [ ! -d repo/.git ]; then
        git clone "$HARNESS" repo
    fi
    REPO=repo
else
    REPO=.
fi

# 7. base_ref.
[ -f "$CONFIG" ] || die "$CONFIG is missing after the install"
# An install that was here before keeps its base_ref; a new one gets origin's default.
[ -n "$BASE_REF" ] || [ -z "$OLD" ] || BASE_REF=$(sed -n 's/^base_ref: *//p' "$CONFIG" | head -1)
if [ -z "$BASE_REF" ]; then
    BASE_REF=$(git -C "$REPO" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)
    [ -n "$BASE_REF" ] || BASE_REF=origin/main
fi
if grep -q '^base_ref:' "$CONFIG"; then
    sed -i.bak "s|^base_ref:.*|base_ref: $BASE_REF|" "$CONFIG" && rm -f "$CONFIG.bak"
else
    printf 'base_ref: %s\n' "$BASE_REF" >> "$CONFIG"
fi

# 7b. In a harness, point agents at the review skill. The harness is yours, so
# AGENTS.md gets a short section and CLAUDE.md imports it (Claude Code reads only
# CLAUDE.md). A repository's own AGENTS.md and CLAUDE.md are left alone. Neither
# reaches Whetstone's agents: their flags exclude every CLAUDE.md.
if [ -n "$HARNESS" ]; then
    if ! grep -qs 'speckit-whetstone-core-review' AGENTS.md; then
        [ -s AGENTS.md ] && printf '\n' >> AGENTS.md
        cat >> AGENTS.md <<'EOF'
## Code review with Whetstone

This directory is a Whetstone harness around the clone in `repo/`. To review a
branch of that repository, use the `speckit-whetstone-core-review` skill
(`/speckit-whetstone-core-review <branch>`). The other `speckit-whetstone-*` skills
are steps of a run: do not run them directly.
EOF
    fi
    grep -qsxF '@AGENTS.md' CLAUDE.md || printf '@AGENTS.md\n' >> CLAUDE.md
fi

# 8. The commit, in a harness only.
if [ -n "$HARNESS" ]; then
    git add -A
    if ! git diff --cached --quiet; then
        if git config user.email >/dev/null; then
            git commit -q -m "Whetstone $VERSION harness"
        else
            git -c user.name=whetstone -c user.email=whetstone@localhost commit -q -m "Whetstone $VERSION harness"
        fi
    fi
fi

say ""
say "Whetstone $VERSION is installed in $ROOT"
say "  base_ref: $BASE_REF  ($CONFIG)"
if [ -n "$HARNESS" ]; then
    say "  the repository under review is cloned at $ROOT/repo"
    say ""
    say "Next:"
    say "  1. Lock down Claude Code: README, section 'Lock down Claude Code'."
    say "  2. Check out the branch to review:  git -C repo fetch && git -C repo checkout -B <branch> origin/<branch>"
    say "  3. Run, from $ROOT:  specify workflow run whetstone"
else
    say ""
    say "Next:"
    say "  1. Commit .specify/, .claude/, .gitignore (and .prototools if written) to the branch other branches start from."
    say "  2. Lock down Claude Code: README, section 'Lock down Claude Code'."
    say "  3. Run, on a branch with a change:  specify workflow run whetstone"
fi
