"""Tests for the four rules, including the cases that fooled them.

Every false positive the scanner has produced is pinned here. The first run on
my own code was right one time in five, and the only thing that caught it was
reading the hits by hand. A test file is how that stops being luck.

Snippets are typed by hand, never copied from a scanned repo. A real fragment
is searchable and would identify the repo as surely as naming it.

Run:  python3 test_rules.py
"""
import ast
import sys

import audit

# (name, source, rules that must fire)
CASES = [
    # R1, and the spellings a text search would miss
    ("r1 plain", "x = response.content[0].text", {"R1"}),
    ("r1 spaced", "x = resp.content[ 0 ].text", {"R1"}),
    ("r1 split", "x = msg.content[0] \\\n    .text", {"R1"}),
    ("r1 correct code is clean",
     "x = next(b.text for b in response.content if b.type == 'text')", set()),
    ("r1 not a zero index", "x = response.content[1].text", set()),

    # R2 and the false positive that cost it four of five hits
    ("r2 client in a worker",
     "def ask(q):\n"
     "    client = Anthropic(api_key=k)\n"
     "    return client.messages.create(model=m, messages=q)", {"R2", "R3"}),
    ("r2 client in main is fine",
     "def main():\n"
     "    client = Anthropic(api_key=k)\n", set()),
    ("r2 module level is fine", "client = Anthropic(api_key=k)", set()),
    ("r2 dotted constructor",
     "def ask(q):\n    c = anthropic.Anthropic(api_key=k)", {"R2"}),

    # R3
    ("r3 guarded is clean",
     "try:\n"
     "    r = client.messages.create(model=m, messages=q)\n"
     "except Exception:\n"
     "    r = None", set()),
    ("r3 unguarded", "r = client.messages.create(model=m, messages=q)", {"R3"}),
    ("r3 openai shape", "r = client.chat.completions.create(model=m)", {"R3"}),
    ("r3 unrelated create is clean", "r = db.table.create(name='x')", set()),
]


def fired(src):
    tree = ast.parse(src)
    out = set()
    for code, rule in audit.FILE_RULES:
        if any(True for _ in rule(tree)):
            out.add(code)
    return out


def main():
    failed = 0
    print(f"  {'case':<32} {'want':<12} got")
    print("  " + "-" * 56)
    for name, src, want in CASES:
        got = fired(src)
        ok = got == want
        failed += not ok
        mark = "" if ok else "   <- FAIL"
        print(f"  {name:<32} {str(sorted(want)):<12} {sorted(got)}{mark}")
    print(f"\n  {len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
