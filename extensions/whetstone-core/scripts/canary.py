#!/usr/bin/env python3
"""The canary: run by an agent at the start of a run, it tries to create a file in each place an agent must not be
able to write, the way code an agent runs would, and prints what happened as JSON. The agent repeats that JSON as its
answer; `whetstone.py canary-check` compares the paths with the ones it expects for the nonce and checks that none
of them exists. Every write must fail."""
import json, os, sys

nonce = sys.argv[1] if len(sys.argv) > 1 else ""
if not nonce.isalnum():
    sys.exit("usage: canary.py <nonce>")
targets = [f"canary-{nonce}", f".git/canary-{nonce}", f".review/canary-{nonce}", f".specify/canary-{nonce}",
           f".claude/canary-{nonce}", os.path.expanduser(f"~/.claude/canary-{nonce}")]
if os.path.isdir("repo"):  # the harness layout: the repository under review is a clone in repo/
    targets += [f"repo/canary-{nonce}", f"repo/.git/canary-{nonce}"]
results = {}
for t in targets:
    try:
        with open(t, "x") as f:
            f.write("canary\n")
        results[t] = True
    except OSError:
        results[t] = False
print(json.dumps({"nonce": nonce, "results": results}))
