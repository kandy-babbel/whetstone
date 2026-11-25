"""The repository under review, as Whetstone's own steps see it. Standard library only.

Whetstone runs in one of two layouts:
- in-repo: the working directory is the repository, with Whetstone installed and committed in it;
- harness: the working directory is a small repository of your own that holds the install, and the repository under
  review is a local clone in the directory `repo/` next to it (MOUNT). Nothing of Whetstone is in that clone.

Agents run with the working directory as their cwd in both layouts. In the harness layout they read the change under
`repo/` and report paths relative to that repository; `canon` maps a path they wrote with the `repo/` prefix back.
Every git call here runs in the repository (`git -C repo`) with the lockdown's git environment. The tree of the change
(`change_tree`) is built in a throwaway object store under .review/, so not even a loose object lands in the clone.
"""
from __future__ import annotations

import posixpath, shutil, subprocess
from pathlib import Path

import lockdown

MOUNT = "repo"
R = Path(".review")
OBJECTS = R / "tmp" / "objects"
_mount = Path(MOUNT)
ROOT = _mount if (_mount.is_dir() or _mount.is_symlink()) else Path(".")
CONVENTIONS_FILE = "CLAUDE.md"  # what Claude Code loads as instructions: every CLAUDE.md in the tree...
CONVENTIONS_DIR = ".claude/rules"  # ...and the Markdown files under the root's .claude/rules/
CONVENTION_MAX = 1_000_000  # bytes; a rule file larger than this is not a rule file
LINK_HOPS = 8  # how many symbolic links are followed inside the tree before a path counts as a loop


def harness() -> bool:
    return ROOT != Path(".")


def git_cmd(*args: str) -> list[str]:
    return lockdown.git_cmd("-C", str(ROOT), *args)


def git(*args: str, env: dict | None = None) -> str:
    return lockdown.git("-C", str(ROOT), *args, env=env)


def git_bytes(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(git_cmd(*args), capture_output=True, env=lockdown.git_env(env))


def git_paths(*args: str, env: dict | None = None) -> list[str]:
    """Paths from a git command run with -z, so names with spaces or non-ASCII characters survive."""
    found = subprocess.run(git_cmd(*args, "-z"), check=True, capture_output=True, text=True,
                           env=lockdown.git_env(env)).stdout
    return [p for p in found.split("\0") if p]


def _recorded(name: str) -> str | None:
    p = R / name
    return p.read_text().strip() if p.exists() else None


def errors() -> list[str]:
    """Why the repository under review is not where and what Whetstone expects; empty when it is."""
    recorded_root = _recorded("root")
    if not harness():
        if recorded_root not in (None, "."):
            return [f"this run was set up with the repository under {MOUNT}/, which is no longer there"]
    else:
        if _mount.is_symlink():
            return [f"{MOUNT} is a symbolic link; it must be a directory holding a local clone of the repository"]
        dot_git = _mount / ".git"
        if dot_git.is_symlink() or not dot_git.is_dir():
            return [f"{MOUNT}/.git must be a directory: use a local clone (git clone), not a worktree or a link"]
        try:
            top = git("rev-parse", "--show-toplevel")
            common = git("rev-parse", "--git-common-dir")
        except subprocess.CalledProcessError as e:
            return [f"{MOUNT} is not a usable git repository: {(e.stderr or '').strip()[:200]}"]
        if Path(top).resolve() != _mount.resolve():
            return [f"git sees {top} as the repository under {MOUNT}, not {_mount.resolve()}"]
        if (_mount / common).resolve() != dot_git.resolve():
            return [f"{MOUNT} shares its git directory with {(_mount / common).resolve()}; use a local clone"]
        if recorded_root not in (None, MOUNT):
            return [f"this run was set up with the repository in the working directory, but {MOUNT}/ exists now"]
    head = _recorded("head")
    if head is not None:
        try:
            now = git("rev-parse", "HEAD")
        except subprocess.CalledProcessError:
            return ["the repository under review has no HEAD"]
        if now != head:
            return [f"the repository's HEAD moved during the run ({head[:12]} -> {now[:12]}); start a new run"]
    return []


def objects_env() -> dict:
    """Git environment that writes new objects under .review/ and reads the repository's own objects through
    alternates: a tree built with it leaves the repository's object store untouched."""
    alt = (ROOT / git("rev-parse", "--git-path", "objects")).resolve()
    return {"GIT_OBJECT_DIRECTORY": str(OBJECTS.resolve()), "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(alt)}


def change_tree() -> str:
    """The tree `git add -A` would record now, built in a temporary index and a throwaway object store under
    .review/: neither the repository's index nor its objects are touched. Hooks and the file system monitor are off."""
    tmp = R / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    OBJECTS.mkdir(parents=True)
    env = {**objects_env(), "GIT_INDEX_FILE": str((tmp / "index").resolve())}
    try:
        git("read-tree", "HEAD", env=env)
        git("add", "-A", env=env)
        return git("write-tree", env=env)
    finally:
        (tmp / "index").unlink(missing_ok=True)


def canon(path: str, has) -> str:
    """A path as an agent wrote it, relative to the repository. In the harness layout an agent reads files under
    `repo/`, so a path it prefixed with `repo/` is mapped back when that is the only reading that exists."""
    p = str(path).strip()
    while p.startswith("./"):
        p = p[2:]
    if harness() and p.startswith(MOUNT + "/"):
        inner = p[len(MOUNT) + 1:]
        if not has(p) and has(inner):
            return inner
    return p


def tree_entries(commit: str) -> dict[str, tuple[str, str, str]]:
    """Every entry of the commit's tree, directories and links included: path -> (mode, type, sha)."""
    out = subprocess.run(git_cmd("ls-tree", "-r", "-t", "-z", commit), check=True, capture_output=True,
                         env=lockdown.git_env()).stdout
    entries = {}
    for rec in out.decode("utf-8", "surrogateescape").split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            mode, kind, sha = meta.split(" ")
            entries[path] = (mode, kind, sha)
    return entries


def blob(sha: str) -> bytes:
    return subprocess.run(git_cmd("cat-file", "blob", sha), check=True, capture_output=True, env=lockdown.git_env()).stdout


def _resolve(entries: dict, path: str) -> tuple[tuple[str, str, str] | None, str, str]:
    """The entry a path names once symbolic links inside the tree are followed: (entry, path, reason). The entry is
    None, with the reason, when the path is missing, a link leaves the tree, loops, or is absolute."""
    for _ in range(LINK_HOPS + 1):
        e = entries.get(path)
        if e is None:
            return None, path, "missing"
        if e[0] != "120000":
            return e, path, ""
        target = blob(e[2]).decode("utf-8", "replace").strip()
        if target.startswith("/"):
            return None, path, f"link to an absolute path ({target})"
        path = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        if path == ".." or path.startswith("../"):
            return None, path, "link leaves the repository"
    return None, path, "link loop"


def conventions(commit: str) -> tuple[list[tuple[str, str, bytes]], list[tuple[str, str]]]:
    """The repository's conventions at a commit: the files Claude Code would load as instructions, read as the
    repository's rules for its code. Every CLAUDE.md in the tree and every Markdown file under .claude/rules/, with
    links followed inside the tree (a CLAUDE.md that links to AGENTS.md, a .claude/rules that links to another
    directory). Returns (files, skipped): files as (name, source, content), where name is the path Claude Code
    would load and source the path of the content in the tree; skipped as (name, reason)."""
    entries = tree_entries(commit)
    wanted = [(p, p) for p in sorted(entries) if posixpath.basename(p) == CONVENTIONS_FILE]
    rules, rules_path, reason = _resolve(entries, CONVENTIONS_DIR)
    if rules is None and reason != "missing":
        skipped_dir = [(CONVENTIONS_DIR, reason)]
    elif rules is not None and rules[1] != "tree":
        skipped_dir = [(CONVENTIONS_DIR, "not a directory")]
    else:
        skipped_dir = []
        if rules is not None:
            prefix = rules_path + "/"
            wanted += [(CONVENTIONS_DIR + "/" + p[len(prefix):], p) for p in sorted(entries)
                       if p.startswith(prefix) and p.endswith(".md") and entries[p][1] == "blob"]
    files, skipped = [], skipped_dir
    for name, path in wanted:
        e, source, reason = _resolve(entries, path)
        if e is None:
            skipped.append((name, reason))
        elif e[1] != "blob":
            skipped.append((name, "not a file"))
        else:
            data = blob(e[2])
            if len(data) > CONVENTION_MAX:
                skipped.append((name, f"larger than {CONVENTION_MAX} bytes"))
            else:
                files.append((name, source, data))
    return files, skipped
