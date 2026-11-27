#!/usr/bin/env python3
"""Claim check: what the text of a change claims, judged against the tree the change is in.

Adapted from the reviewer plugin's claim check (analitiq-ai/claude-plugins-internal, reviewer/plugin/scripts/
claimcheck.py, claimgate.py and briefs.py). The reader task, the claim categories, the judge prompts and the rules a
reader's and a judge's answers must meet are taken from there. Left out: lineages that follow a claim across commits,
contests, and `unlock`; Whetstone shows a WRONG claim to a person instead.

The checked tree is the working tree as `git add -A` would record it, built in a temporary index and a throwaway
object store under .review/ so the repository is untouched (whetstone-core's repo.py); the change is everything from
the run's base commit (.review/base, else HEAD) to that tree. Every agent answer is checked against that tree: a
quote must be the text around its hunk, and evidence a `path:line` of a file in it. The repository is the working
directory, or the clone under repo/ in the harness layout. Standard library only, so agents can run the self-checks
with python3.

  prepare                      build the tree, list its hunks, reuse earlier reads, write a prompt per reader batch
  check-read <batch> <file>    a reader's self-check of its draft answer
  accept                       take every reader's answer from the run state, reuse earlier CORRECT verdicts, write a
                               prompt per claim to judge
  check-verdict <id> <file>    a judge's self-check of its draft answer
  settle                       take every verdict from the run state and write .review/current/claim-check.json

Agents write no file: each answers on standard output, and Spec Kit keeps the answer in the run state, where accept
and settle find it (whetstone-core's runstate.py). A reader that did not answer leaves its files unread; a judge that
did not answer leaves its claim unjudged. Both go to a person, like a WRONG claim. .review/current/claims/ holds the
prompts and the answers taken; .review/claim-cache.json keeps reads and reusable CORRECT verdicts.
Every subcommand prints one JSON object and exits 1 when the check cannot go on.
"""
from __future__ import annotations

import hashlib, json, re, shutil, subprocess, sys
from pathlib import Path

sys.dont_write_bytecode = True
# whetstone-core's scripts, installed beside this extension (.specify/extensions/whetstone-core/scripts)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "whetstone-core" / "scripts"))
import lockdown, repo, runstate  # noqa: E402

R = Path(".review")
CUR = R / "current"
CL = CUR / "claims"
STATE = CL / "state.json"
OUT = CUR / "claim-check.json"
CACHE = R / "claim-cache.json"
SELF = ".specify/extensions/whetstone-claim-check/scripts/claimcheck.py"
READ_COMMAND = "speckit.whetstone-claim-check.read"
JUDGE_COMMAND = "speckit.whetstone-claim-check.judge"

READ_BATCH = 16  # hunks per reader
WARN_OVER = 20  # judged claims above which the change is worth splitting

CATEGORIES = tuple(f"K{i}" for i in range(1, 10))
# K1, what the repo's own code, contracts, validator or CI does; K9, what a test checks.
JUDGED = ("K1", "K9")
VERDICTS = ("CORRECT", "WRONG", "UNSURE")
KINDS = ("CODE", "PROSE", "MIXED")
# A claim with one of these words is about cases no cited file can close, so its CORRECT is never reused.
_UNIVERSAL = re.compile(r"\b(every|only|all|exactly|always|never)\b", re.I)
_CITATION = re.compile(r"(?<![\w/.:-])(?P<path>[\w./-]+):(?P<line>\d+)\b")
_URL = re.compile(r"https://[^\s<>\"'`)\]]+")
_COMMENT_MARK = re.compile(r"^\s*(?:#+|//+|/\*+|\*+/?|--|>|;+|<!--)\s?")
_WORD = re.compile(r"\S+")

CATEGORY_MEANINGS = {
    "K1": "what our own code, contracts, validator or CI does",
    "K2": "how a vendor tool, cloud platform, language or standard behaves",
    "K3": 'a list, a count, or an "every / the only / complete" claim',
    "K4": "a task tick or a PASS/FAIL status mark",
    "K5": "a recorded observation, such as a date, run ID, commit, count or approval",
    "K6": "a command or code block and what it does",
    "K7": "a citation of a file, field, symbol, rule or requirement",
    "K8": "planned behaviour, meaning what a proposal or design says the system will do once it's built",
    "K9": "what a test checks: a test's name, description or failure message (a comment in a test about the code "
          "it tests is K1)",
}

_READER_TASK = ("For each hunk, read its file around the hunk, then:\n"
                "1. Label it CODE (only code), PROSE (only text for people: docs, comments, docstrings, messages) or "
                "MIXED (code with comments, docstrings, or a test's name or failure message in it), judging by its "
                "content, not the file's extension.\n"
                "2. List the claims its text makes: every statement a reader could rely on and that could be false. A "
                "removed line counts through the sentence it leaves behind. Quote each claim verbatim from the staged "
                "file, give the line it starts on, and give it the one category that fits best:\n"
                + "\n".join(f"- {k}: {meaning}" for k, meaning in CATEGORY_MEANINGS.items()) + "\n"
                "Code itself states no claim; its comments and docstrings do, and so do a test's name and failure "
                "messages. A hunk with no claim has an empty list.\n\n"
                "Read only, never modify files.")
# A stored read stands only for the task and labels it answered: a changed task, kind or category re-reads the hunk.
READER_BRIEF = hashlib.sha256(json.dumps([_READER_TASK, KINDS, CATEGORIES]).encode()).hexdigest()[:16]

_JUDGE_TAIL = """
Readers will rely on every word of this claim, so a claim that is mostly
true is not correct. Past checkers failed by confirming the easiest part
of a claim (a library is used, a model exists, a counter starts at 1) and
marking the whole claim correct. Your job is to try to break the claim,
and to call it correct only if you can't.

Work in this order:

1. Split the claim into every separate assertion it makes. Include the
   implied ones: words like "exactly", "always", "the same", "already",
   "not", or a list of items each assert something, and so does naming
   which component does the work. If the claim has the form "X, so Y",
   X and Y are separate assertions and Y is the one that matters.

2. For each assertion, read the code that implements the behaviour. Names,
   docstrings, comments and other docs are not evidence: open the function
   or test body and read what it does. If a docstring or comment disagrees
   with the claim, treat that as a lead to follow, not something to explain
   away.

3. For each assertion, look for the case where it fails: empty or zero
   input, optional or omitted fields, items in a list that are handled
   differently from the others, a different component doing the work than
   the one named, paths that skip the check.

4. Give your verdict last, after the evidence:
   - CORRECT: every assertion is confirmed by code you read, and you found
     no failing case.
   - WRONG: at least one assertion is false or has a failing case.
   - UNSURE: you could not find or read the code that would settle at
     least one assertion.

For each assertion, give the file and line that settle it, and for WRONG,
the failing case."""
# A test is often written before the code it drives, so what it says it checks is judged against the test alone.
_TEST_JUDGE_TAIL = """
Judge the claim against its own test only: its assertions and inputs,
and the fixtures and helpers the test body calls. The code under test is
not evidence either way. A test is often written before that code
exists, so code that is missing or behaves differently does not make
the claim wrong.

Readers rely on the claim to know what the test proves, so a test that
checks less than its name or message says makes the claim wrong. Your
job is to try to break the claim, and to call it correct only if you
can't.

Work in this order:

1. Find the test the claim belongs to: the test function, case or
   assertion whose name, description or failure message it is.

2. Split the claim into every separate assertion it makes about what
   the test checks. Include the implied ones: a named value, error or
   outcome, and words like "every", "only", "not" or "rejects".

3. For each assertion, find the input the test passes and the assertion
   that checks it. An outcome the test never asserts, an input it never
   passes, or an assertion weaker than the claim (checking that a call
   fails, where the claim names the error) is a failing case.

4. Give your verdict last, after the evidence:
   - CORRECT: the test's own inputs and assertions check every
     assertion of the claim.
   - WRONG: at least one assertion is not checked by the test, or is
     checked more weakly than the claim says.
   - UNSURE: you could not find the test the claim belongs to.

For each assertion, give the file and line of the test that settle it,
and for WRONG, the failing case."""
_EVIDENCE_RULE = ("\n\nRead and search only, never modify files. Evidence is a path:line of a file the commit will "
                  "record, relative to the checkout's root; an untracked or ignored file is not evidence.")


# --- I/O ---------------------------------------------------------------------------------------------

def out(obj, code=0):
    print(json.dumps(obj))
    sys.exit(code)


def fail(msg, **extra):
    print(f"CLAIM CHECK: {msg}", file=sys.stderr)
    out({"valid": False, "error": msg, **extra}, 1)


git = repo.git
_objects = None


def objects_env() -> dict:
    """The git environment that sees the tree built under .review/ (repo.change_tree)."""
    global _objects
    if _objects is None:
        _objects = repo.objects_env()
    return _objects


def git_bytes(*args: str) -> subprocess.CompletedProcess:
    return repo.git_bytes(*args, env=objects_env())


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")


def base_commit() -> str:
    p = R / "base"
    return p.read_text().strip() if p.exists() else git("rev-parse", "HEAD")


def commit_tree() -> str:
    """The tree `git add -A` would record now (repo.change_tree: a temporary index and a throwaway object store
    under .review/, hooks and the file system monitor off). It must be the tree `setup` recorded, if there is one:
    a working tree that changed during the run is not the one the review looked at."""
    try:
        tree = repo.change_tree()
    except subprocess.CalledProcessError as e:
        fail(f"git cannot record the working tree ({(e.stderr or '').strip()[:300]}); a nested repository without "
             "commits, for example, must be removed or committed first")
    if (R / "tree").exists() and (R / "tree").read_text().strip() != tree:
        fail("the working tree changed since this run started (its tree is no longer the one recorded in "
             ".review/tree); start a new run")
    return tree


class Tree:
    """Text and blob ids of files in one tree, each read from git once. A binary or absent file has no text."""

    def __init__(self, tree: str):
        self.tree, self._texts, self._blobs = tree, {}, {}

    def lines(self, path: str) -> list[str] | None:
        if path not in self._texts:
            r = git_bytes("cat-file", "blob", f"{self.tree}:{path}")
            data = r.stdout if r.returncode == 0 else None
            if data is None or b"\0" in data:
                self._texts[path] = None
            else:
                text = data.decode("utf-8", "surrogateescape")
                found = text.split("\n")
                self._texts[path] = found[:-1] if text.endswith("\n") else found
        return self._texts[path]

    def located(self, path: str) -> int | None:
        found = self.lines(path)
        return None if found is None else len(found)

    def blob(self, path: str) -> str | None:
        if path not in self._blobs:
            r = git_bytes("rev-parse", "-q", "--verify", f"{self.tree}:{path}")
            self._blobs[path] = r.stdout.decode().strip() if r.returncode == 0 else None
        return self._blobs[path]


EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def hunks_of(head: str, tree: str) -> tuple[list[dict], list[dict]]:
    """The hunks from `head` to `tree`, with no context lines, and the changed files that could not be read as text
    ({file, reason}). Files are diffed as text whatever .gitattributes says (`-a --no-textconv`), so an attribute
    cannot hide a file. A deleted file, a submodule, an empty file or a mode-only change has no text to read."""
    r = git_bytes("diff", "--raw", "-z", "--no-renames", "--no-abbrev", head, tree)
    if r.returncode != 0:
        fail(f"git diff failed: {r.stderr.decode(errors='replace').strip()[:300]}")
    raw = r.stdout.decode("utf-8", "surrogateescape").split("\0")
    changed = []
    for meta, path in zip(raw[0::2], raw[1::2]):
        if not meta.startswith(":"):
            continue
        _, new_mode, old_blob, new_blob, status = meta[1:].split()
        if status == "D" or new_mode == "160000" or new_blob == EMPTY_BLOB or old_blob == new_blob:
            continue
        changed.append(path)
    reader, hunks, unread = Tree(tree), [], []
    header = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    for path in changed:
        if reader.lines(path) is None:
            unread.append({"file": path, "reason": "the file cannot be read as text (it has NUL bytes)"})
            continue
        d = git_bytes("diff", "-a", "--no-textconv", "-U0", "--no-color", "--no-ext-diff", "--no-renames", head, tree,
                      "--", path)
        if d.returncode != 0:
            fail(f"git diff failed for {path}: {d.stderr.decode(errors='replace').strip()[:300]}")
        diff = d.stdout.decode("utf-8", "surrogateescape")
        before, current = len(hunks), None
        for line in diff.split("\n"):
            m = header.match(line)
            if m:
                current = {"id": f"H{len(hunks) + 1}", "file": path, "new_start": int(m[2]),
                           "new_count": int(m[3]) if m[3] is not None else 1, "removed": [], "added": []}
                hunks.append(current)
            elif current is not None and line.startswith("-") and not line.startswith("---"):
                current["removed"].append(line[1:])
            elif current is not None and line.startswith("+") and not line.startswith("+++"):
                current["added"].append(line[1:])
        if len(hunks) == before:
            unread.append({"file": path, "reason": "git shows no text hunk for the change"})
    return hunks, unread


# --- the rules (from claimcheck.py; pure functions) -----------------------------------------------------

def words(text: str) -> list[str]:
    """The words of a text, comment markers at line starts left out."""
    found = []
    for line in text.split("\n"):
        mark = _COMMENT_MARK.match(line)
        found += _WORD.findall(line, mark.end() if mark else 0)
    return found


def plain(text: str) -> str:
    """The words of a text, each run of white space and each comment marker at a line start reduced to one space."""
    return " ".join(words(text))


def text_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8", "surrogateescape")).hexdigest()[:16]


def claim_id(file: str, quote: str) -> str:
    return text_id(file, plain(quote))


def hunk_key(hunk: dict) -> str:
    return text_id(hunk["file"], "\n".join(hunk["removed"]), "\n".join(hunk["added"]))


def paragraph(lines: list[str], hunk: dict) -> tuple[int, int]:
    """The 1-based line range of the text a hunk sits in: its new lines, or the line before what it removed, widened
    to the blank lines around them. A removal is judged by the paragraph it leaves behind."""
    first = max(1, min(hunk["new_start"], len(lines)))
    last = max(first, min(hunk["new_start"] + max(hunk["new_count"], 1) - 1, len(lines)))
    while first > 1 and lines[first - 2].strip():
        first -= 1
    while last < len(lines) and lines[last].strip():
        last += 1
    return first, last


def citations(text: str, located) -> tuple[list[str], list[str]]:
    """The `path:line` citations in `text` that name a line of the checked tree, and those that do not."""
    good, bad = [], []
    for found in _CITATION.finditer(_URL.sub(" ", text or "")):
        path = repo.canon(found["path"], lambda p: located(p) is not None)
        size = located(path)
        if size is not None and 1 <= int(found["line"]) <= size:
            good.append(f"{path}:{found['line']}")
        elif size is not None or "/" in path or "." in path:  # "1:2" or "step:3" is not a citation
            bad.append(found.group(0))
    return good, bad


def _shape(doc, required: dict) -> list[str]:
    if not isinstance(doc, dict):
        return ["the answer must be a JSON object"]
    return [f"{k} must be {t.__name__}" for k, t in required.items() if not isinstance(doc.get(k), t)]


def validate_reader(output, batch: list[dict], tree: Tree) -> list[str]:
    """Reasons a reader's labels and claims for one batch of hunks are not accepted."""
    errors = _shape(output, {"batch": int, "hunks": list})
    if errors:
        return errors
    by_id = {h["id"]: h for h in batch}
    seen = [h.get("id") for h in output["hunks"] if isinstance(h, dict)]
    if sorted(by_id) != sorted(seen) or len(seen) != len(set(seen)) or len(seen) != len(output["hunks"]):
        errors.append(f"label every hunk of your batch exactly once: expected {sorted(by_id)}, got {seen}")
    for entry in output["hunks"]:
        hunk = by_id.get(entry.get("id")) if isinstance(entry, dict) else None
        if hunk is None:
            continue
        if entry.get("kind") not in KINDS:
            errors.append(f"{entry['id']}: kind must be one of {list(KINDS)}")
        claims = entry.get("claims")
        if not isinstance(claims, list):
            errors.append(f"{entry['id']}: claims must be a list")
            continue
        if entry.get("kind") == "CODE" and claims:
            errors.append(f"{entry['id']}: a CODE hunk states no claim; label it MIXED if it holds prose")
        lines = tree.lines(hunk["file"]) or []
        first, last = paragraph(lines, hunk)
        for claim in claims:
            if _shape(claim, {"line": int, "quote": str, "category": str}):
                errors.append(f"{entry['id']}: each claim is {{line: integer, quote: string, category: string}}")
                continue
            where = f"{hunk['file']}:{claim['line']}"
            if claim["category"] not in CATEGORIES:
                errors.append(f"{where}: category must be one of {list(CATEGORIES)}")
            said = plain(claim["quote"])
            if not said:
                errors.append(f"{where}: the quote is empty")
            elif not first <= claim["line"] <= last:
                errors.append(f"{where}: the claim must sit in the text around {entry['id']}, lines {first}-{last}")
            elif (said not in plain("\n".join(lines[claim["line"] - 1:last]))
                  or said.split()[0] not in plain(lines[claim["line"] - 1])):
                errors.append(f"{where}: the quote is not the staged text starting on that line; copy the words exactly")
    return errors


def validate_verdict(output, cid: str, located) -> list[str]:
    """Reasons a judge's verdict is not accepted. Evidence is a `path:line` of the checked tree."""
    errors = _shape(output, {"claim_id": str, "verdict": str, "basis": str, "assertions": list})
    if errors:
        return errors
    if output["claim_id"] != cid:
        return [f"claim_id must be {cid}, the claim you were given"]
    if output["verdict"] not in VERDICTS:
        return [f"verdict must be one of {list(VERDICTS)}"]
    assertions = output["assertions"]
    if not assertions:
        errors.append("split the claim into its assertions; there must be at least one")
    if any(_shape(e, {"text": str, "confirmed": bool, "evidence": str}) for e in assertions):
        return errors + ["each assertion is {text: string, confirmed: boolean, evidence: string}"]

    def supported(evidence: str) -> bool:
        return bool(citations(evidence, located)[0])

    for entry in assertions:
        bad = citations(entry["evidence"], located)[1]
        if bad:
            errors.append(f"{', '.join(bad)} is not a line of a file in the staged tree; cite only what will be committed")
        if _URL.search(entry["evidence"] or ""):
            errors.append("a web page is not evidence here; cite the file and line of the staged tree that settles it")
    kind = output["verdict"]
    # In an UNSURE verdict an unconfirmed assertion is the open question, so it has nothing to cite.
    if not all(supported(e["evidence"]) for e in assertions if e["confirmed"] or kind != "UNSURE"):
        errors.append("every assertion you settled needs the path:line that settles it; a conclusion drawn from "
                      "another assertion is not one, so leave it out")
    if kind == "CORRECT" and not all(e["confirmed"] for e in assertions):
        errors.append("CORRECT needs every assertion confirmed")
    if kind == "WRONG":
        if not (output.get("failing_case") or "").strip():
            errors.append("WRONG needs failing_case: the input or situation in which the claim is false")
        if not any(not e["confirmed"] and supported(e["evidence"]) for e in assertions):
            errors.append("WRONG needs an assertion that is not confirmed, with the path:line that breaks it")
    if kind == "UNSURE" and not (output.get("gap") or "").strip():
        errors.append("UNSURE needs gap: what you could not find or read")
    return errors


def cited_paths(verdict: dict, located) -> set[str]:
    return {c.rsplit(":", 1)[0] for e in verdict["assertions"] for c in citations(e["evidence"], located)[0]}


def cacheable(claim: dict, verdict: dict) -> bool:
    return verdict["verdict"] == "CORRECT" and not _UNIVERSAL.search(claim["quote"])


def broken(verdict: dict) -> dict:
    return next((e for e in verdict["assertions"] if not e["confirmed"]), verdict["assertions"][0])


# --- prompts ---------------------------------------------------------------------------------------------

# How an agent makes its draft. The shell refuses JSON in a heredoc (a brace next to a quote reads as expansion
# obfuscation), and the agents' file tools may write only under TMPDIR (lockdown.REQUIRED_ALLOW).
_DRAFT_HOW = ("Learn your temporary directory with `echo $TMPDIR`, then write your draft to `{name}` in it with the "
              "Write tool, giving the full path. Do not write it with the shell: a heredoc holding JSON is refused. "
              "Correct the draft with the Edit or Write tool.")


def where(root: str) -> str:
    """Where the checkout is, as told to an agent whose cwd is the working directory."""
    if repo.harness():
        return (f"the checkout at {root} (the directory `{repo.MOUNT}/` in your working directory; read its files "
                f"under `{repo.MOUNT}/`, run git as `git -C {repo.MOUNT} ...`, and give every path in your answer "
                f"relative to that checkout's root, without the `{repo.MOUNT}/` prefix)")
    return f"the checkout at {root} (your working directory)"


def reader_prompt(root: str, batch: int, hunks: list[dict]) -> str:
    shown = "\n\n".join(
        f"{h['id']}: {h['file']}, staged lines {h['new_start']}-{h['new_start'] + max(h['new_count'], 1) - 1}\n"
        + "".join(f"- {line}\n" for line in h["removed"]) + "".join(f"+ {line}\n" for line in h["added"])
        for h in hunks)
    return (f"These are hunks of a change in {where(root)}. The files there are as the change leaves them.\n\n"
            f"{shown}\n\n{_READER_TASK}\n\n"
            "## Answer\n\n"
            "Your answer is one strict JSON document:\n\n"
            '{"batch": ' + str(batch) + ', "hunks": [{"id": "H1", "kind": "MIXED", "claims": '
            '[{"line": 12, "quote": "exact words from the file", "category": "K1"}]}]}\n\n'
            "List every hunk above exactly once. `line` is the line the quote starts on in the file as it is now. "
            "The repository is read-only for you. " + _DRAFT_HOW.format(name=f"read-{batch}.json") + " Then run "
            f"`python3 {SELF} check-read {batch} $TMPDIR/read-{batch}.json`. It checks every quote against the file "
            "and every hunk against this batch. Correct the draft until it prints OK. Then reply with the draft's "
            "exact content as your final answer: the JSON alone, no code fence, nothing before or after it.")


def judge_prompt(root: str, claim: dict) -> str:
    if claim["category"] == "K9":
        head = ("You are checking what a test says it checks, in the codebase in\n"
                f"{where(root)}, as the change leaves it.\n"
                "That checkout is the source of truth. The claim is a test's name,\n"
                f"description or failure message, from `{claim['file']}` line {claim['line']}.\n\n"
                f"Claim: {claim['quote']}\n" + _TEST_JUDGE_TAIL)
    else:
        head = ("You are checking a claim made in the documentation of the codebase in\n"
                f"{where(root)}, as the change leaves it.\n"
                f"That checkout is the source of truth. The claim comes from `{claim['file']}`\n"
                f"line {claim['line']}.\n\nClaim: {claim['quote']}\n" + _JUDGE_TAIL)
    cid = claim["id"]
    return (head + _EVIDENCE_RULE + "\n\n## Answer\n\n"
            "Your answer is one strict JSON document:\n\n"
            '{"claim_id": "' + cid + '", "verdict": "CORRECT | WRONG | UNSURE", "basis": "one paragraph", '
            '"assertions": [{"text": "one assertion", "confirmed": true, "evidence": "path/to/file.py:42"}], '
            '"failing_case": "for WRONG: the input or situation in which the claim is false", '
            '"gap": "for UNSURE: what you could not find or read"}\n\n'
            "The repository is read-only for you. " + _DRAFT_HOW.format(name=f"verdict-{cid}.json") + " Then run "
            f"`python3 {SELF} check-verdict {cid} $TMPDIR/verdict-{cid}.json`. It checks every path:line against the "
            "checked tree. Correct the draft until it prints OK. Then reply with the draft's exact content as your "
            "final answer: the JSON alone, no code fence, nothing before or after it.")


# --- subcommands -----------------------------------------------------------------------------------------

def round_no() -> int:
    p = R / "round"
    return int(p.read_text()) if p.exists() else 0


def state() -> dict:
    s = load(STATE)
    if s is None:
        fail(f"{STATE} missing; run `claimcheck.py prepare` first")
    return s


def prepare():
    CUR.mkdir(parents=True, exist_ok=True)
    if CL.exists():
        shutil.rmtree(CL)
    OUT.unlink(missing_ok=True)
    CL.mkdir(parents=True)
    head = base_commit()
    tree = commit_tree()
    hunks, unread = hunks_of(head, tree)
    cache = load(CACHE, {"reads": {}, "verdicts": {}})
    tree_r = Tree(tree)
    reads, to_read = {}, []
    for h in hunks:
        cached = cache["reads"].get(hunk_key(h))
        if cached and cached["brief"] == READER_BRIEF:
            claims = [{"line": h["new_start"] + c["offset"], "quote": c["quote"], "category": c["category"]}
                      for c in cached["claims"]]
            entry = {"id": h["id"], "kind": cached["kind"], "claims": claims}
            if not validate_reader({"batch": 0, "hunks": [entry]}, [h], tree_r):
                reads[h["id"]] = entry
                continue
        to_read.append(h)
    batches = [[h["id"] for h in to_read[i:i + READ_BATCH]] for i in range(0, len(to_read), READ_BATCH)]
    by_id = {h["id"]: h for h in hunks}
    root = git("rev-parse", "--show-toplevel")
    for b, ids in enumerate(batches):
        (CL / f"batch-{b}.md").write_text(reader_prompt(root, b, [by_id[i] for i in ids]) + "\n")
    save(STATE, {"round": round_no(), "head": head, "tree": tree, "hunks": hunks, "unread": unread,
                 "batches": batches, "reads": reads, "reused_reads": sorted(reads), "claims": {}, "judge": [],
                 "verdicts": {}, "reused_verdicts": [], "unjudged": []})
    out({"valid": True, "round": round_no(), "base": head, "tree": tree, "hunks": len(hunks), "unread": len(unread),
         "reused_reads": len(reads), "batches": [str(b) for b in range(len(batches))]})


def _batch(s: dict, b: int) -> list[dict]:
    by_id = {h["id"]: h for h in s["hunks"]}
    return [by_id[i] for i in s["batches"][b]]


def _draft(path: str):
    """An agent's draft answer: a file it names, under its own TMPDIR."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        print(f"NOT OK: {path} is not readable strict JSON: {e}")
        sys.exit(1)


def check_read():
    s, b = state(), int(sys.argv[2])
    if not 0 <= b < len(s["batches"]):
        fail(f"there is no batch {b}")
    doc = _draft(sys.argv[3])
    errors = validate_reader(doc, _batch(s, b), Tree(s["tree"]))
    if doc.get("batch") != b:
        errors.insert(0, f"batch must be {b}")
    print("OK" if not errors else "NOT OK, correct these and run me again:\n- " + "\n- ".join(errors))
    sys.exit(1 if errors else 0)


def accept():
    """Every reader's answer, from the run state. A reader that did not answer, or answered wrongly, leaves the files
    of its hunks unread: that goes to a person, never to a verdict."""
    s = state()
    tree = Tree(s["tree"])
    cache = load(CACHE, {"reads": {}, "verdicts": {}})
    not_read = []
    for b in range(len(s["batches"])):
        batch = _batch(s, b)
        rec, err = runstate.find(command=READ_COMMAND, args=str(b))
        doc, err = runstate.answer(rec, f"reader of batch {b}") if rec else (None, err)
        if doc is not None:
            save(CL / f"read-{b}.json", doc)
            errors = validate_reader(doc, batch, tree) or ([] if doc.get("batch") == b else [f"batch must be {b}"])
            if errors:
                err = f"reader of batch {b}: " + "; ".join(errors[:3])
        if err:
            not_read.append(err)
            for f in dict.fromkeys(h["file"] for h in batch):
                s["unread"].append({"file": f, "reason": err})
            continue
        hunks = {h["id"]: h for h in batch}
        for entry in doc["hunks"]:
            s["reads"][entry["id"]] = {"id": entry["id"], "kind": entry["kind"], "claims": entry["claims"]}
            h = hunks[entry["id"]]
            cache["reads"][hunk_key(h)] = {"brief": READER_BRIEF, "kind": entry["kind"], "claims": [
                {"offset": c["line"] - h["new_start"], "quote": c["quote"], "category": c["category"]}
                for c in entry["claims"]]}
    save(CACHE, cache)
    by_hunk = {h["id"]: h for h in s["hunks"]}
    claims = {}
    for hid, read in s["reads"].items():
        for c in read["claims"]:
            cid = claim_id(by_hunk[hid]["file"], c["quote"])
            claims.setdefault(cid, {"id": cid, "hunk": hid, "file": by_hunk[hid]["file"], "line": c["line"],
                                    "quote": c["quote"], "category": c["category"]})
    s["claims"], s["verdicts"], s["reused_verdicts"] = claims, {}, []
    for cid, c in claims.items():
        cached = cache["verdicts"].get(cid) if c["category"] in JUDGED else None
        # A cached CORRECT stands while the claim keeps its category and every file it cited is unchanged.
        if (cached and cached["category"] == c["category"] and cached["evidence_blobs"]
                and all(tree.blob(p) == b for p, b in cached["evidence_blobs"].items())):
            s["verdicts"][cid] = cached["verdict"]
            s["reused_verdicts"].append(cid)
    root = git("rev-parse", "--show-toplevel")
    s["judge"] = [cid for cid, c in claims.items() if c["category"] in JUDGED and cid not in s["verdicts"]]
    for cid in s["judge"]:
        (CL / f"claim-{cid}.md").write_text(judge_prompt(root, claims[cid]) + "\n")
    save(STATE, s)
    out({"valid": True, "claims": len(claims), "judge": s["judge"], "reused_verdicts": len(s["reused_verdicts"]),
         "not_read": not_read})


def check_verdict():
    s, cid = state(), sys.argv[2]
    if cid not in s["claims"]:
        fail(f"{cid} is not a claim of this check")
    doc = _draft(sys.argv[3])
    errors = validate_verdict(doc, cid, Tree(s["tree"]).located)
    print("OK" if not errors else "NOT OK, correct these and run me again:\n- " + "\n- ".join(errors))
    sys.exit(1 if errors else 0)


def settle():
    """Every judge's verdict, from the run state, into .review/current/claim-check.json. A judge that did not answer,
    or whose answer the rules refuse, leaves its claim unjudged: that goes to a person, never counts as CORRECT."""
    s = state()
    tree = Tree(s["tree"])
    cache = load(CACHE, {"reads": {}, "verdicts": {}})
    for cid in s["judge"]:
        c = s["claims"][cid]
        rec, err = runstate.find(command=JUDGE_COMMAND, args=cid)
        doc, err = runstate.answer(rec, f"judge of {c['file']}:{c['line']}") if rec else (None, err)
        if doc is not None:
            save(CL / f"verdict-{cid}.json", doc)
            errors = validate_verdict(doc, cid, tree.located)
            if errors:
                err = f"judge of {c['file']}:{c['line']}: " + "; ".join(errors[:3])
        if err:
            s["unjudged"].append({"id": cid, "file": c["file"], "line": c["line"], "quote": c["quote"], "reason": err})
            continue
        verdict = {k: doc[k] for k in ("verdict", "basis", "assertions", "failing_case", "gap") if k in doc}
        s["verdicts"][cid] = verdict
        if cacheable(c, verdict):
            cache["verdicts"][cid] = {"category": c["category"], "verdict": verdict, "evidence_blobs": {
                p: tree.blob(p) for p in cited_paths(verdict, tree.located)}}
    save(CACHE, cache)
    save(STATE, s)
    claims = []
    for cid, c in sorted(s["claims"].items(), key=lambda kv: (kv[1]["file"], kv[1]["line"], kv[0])):
        claims.append({**{k: c[k] for k in ("id", "file", "line", "quote", "category")},
                       "judged": c["category"] in JUDGED, "reused": cid in s["reused_verdicts"],
                       "verdict": s["verdicts"].get(cid)})
    rulings = [c["verdict"]["verdict"] for c in claims if c["verdict"]]
    not_judged = {}
    for c in claims:
        if not c["judged"]:
            not_judged[c["category"]] = not_judged.get(c["category"], 0) + 1
    counts = {"claims": len(claims), "judged": len(rulings), "reused": len(s["reused_verdicts"]),
              "correct": rulings.count("CORRECT"), "wrong": rulings.count("WRONG"), "unsure": rulings.count("UNSURE"),
              "unjudged": len(s["unjudged"]), "unread": len(s["unread"])}
    doc = {"schema_version": "whetstone.claim-check/1", "round": s["round"], "base": s["head"], "tree": s["tree"],
           "status": "complete",
           "hunks": [{"id": h["id"], "file": h["file"], "new_start": h["new_start"], "new_count": h["new_count"],
                      "kind": s["reads"][h["id"]]["kind"] if h["id"] in s["reads"] else None} for h in s["hunks"]],
           "claims": claims, "counts": counts, "not_judged": not_judged, "unread": s["unread"],
           "unjudged": s["unjudged"]}
    if counts["judged"] > WARN_OVER:
        doc["warning"] = f"{counts['judged']} claims were judged; consider splitting the change into several PRs"
    save(OUT, doc)
    out({"valid": True, **counts})


if __name__ == "__main__":
    cmds = {"prepare": prepare, "check-read": check_read, "accept": accept, "check-verdict": check_verdict,
            "settle": settle}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]]()
