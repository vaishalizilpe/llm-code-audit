"""Four mistakes in code that calls an LLM API, found by reading the syntax tree.

Why a syntax tree and not a search. Every one of these four rules is a question
about structure, not about characters. "Is the client built inside a function"
is a question about nesting, and a text search has no concept of nesting. Three
of the four also survive reformatting, renamed variables and line breaks only
because the tree ignores all of that.

Why no language model. These are static questions with exact answers. A model
here would add cost, non-determinism and a second grader nobody has measured.
The scanner runs with no API key and gives the same answer every time, which is
the opposite of the project this one grew out of.

The rules come from mistakes I made and fixed, not from a style guide:

  R1  response.content[0].text    assumes the first block is text. It is not
                                  when extended thinking is on, and the failure
                                  is an AttributeError at runtime.
  R2  client built inside a       a new client, and a new connection, on every
      function                    call.
  R3  the API call is not inside  the network call fails and the program either
      a try                       dies or silently degrades.
  R4  the repo has no tests       a system calling a non-deterministic API with
                                  nothing measuring it.

A fifth rule was written and dropped. See README.

Every rule here can be wrong. Precision is measured by hand, not asserted.
Run:  python3 audit.py <path> [path ...]
"""
import ast
import sys
from pathlib import Path

# Constructors that create an LLM client. Deliberately short: these are the
# ones whose misuse I can speak to. Adding every provider would widen the
# claim past what has been hand-checked.
CLIENTS = {"Anthropic", "AsyncAnthropic", "OpenAI", "AsyncOpenAI"}

# Attribute chains that mean "this is the network call", as in
# client.messages.create(...) or client.chat.completions.create(...)
CALL_PARENTS = {"messages", "completions", "responses"}


def walk(node, stack=()):
    """Yield every node with the list of nodes enclosing it.

    ast.walk does not tell you what a node sits inside, and three of the four
    rules are entirely about what a node sits inside.
    """
    yield node, stack
    for child in ast.iter_child_nodes(node):
        yield from walk(child, stack + (node,))


def r1_first_block_is_text(tree):
    """.text on a [0] on a .content, however it is spelled or spaced."""
    for node, _ in walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr == "text"
                and isinstance(node.value, ast.Subscript)
                and isinstance(node.value.slice, ast.Constant)
                and node.value.slice.value == 0
                and isinstance(node.value.value, ast.Attribute)
                and node.value.value.attr == "content"):
            yield node.lineno, "response.content[0].text"


# Functions that run once by convention, so building a client in them is fine.
# Narrowed 2026-11-10 after the first run of this scanner on my own repo
# returned five R2 hits of which four were a client built in main(). The rule
# had asked "is it inside a function" when the question is "is it inside
# something that runs repeatedly". Precision went from 1 in 5 to 1 in 1 on
# that sample.
#
# This is a name-based heuristic and names are not behaviour. A main() called
# in a loop would be missed. It is kept because it is honest about one thing:
# a rule that fires four times for every real hit is not a detector, it is
# noise with line numbers.
RUN_ONCE = {"main", "cli", "run", "setup", "__init__"}


def r2_client_inside_function(tree):
    """A client constructor inside a function that is not a one-shot entry point.

    Known false positive that remains: a factory whose whole job is to build
    and return a client. This is why precision is hand-checked, not claimed.
    """
    for node, stack in walk(tree):
        if not (isinstance(node, ast.Call) and _ctor_name(node.func) in CLIENTS):
            continue
        enclosing = [a for a in stack
                     if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if enclosing and enclosing[-1].name not in RUN_ONCE:
            yield node.lineno, f"{_ctor_name(node.func)}() inside {enclosing[-1].name}()"


def r3_call_not_guarded(tree):
    """A .create() on a messages/completions chain with no Try above it."""
    for node, stack in walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr in CALL_PARENTS):
            continue
        if not any(isinstance(a, ast.Try) for a in stack):
            yield node.lineno, f".{node.func.value.attr}.create() outside a try"


def _ctor_name(func):
    """Anthropic(...) and anthropic.Anthropic(...) are the same thing here."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


FILE_RULES = [("R1", r1_first_block_is_text),
              ("R2", r2_client_inside_function),
              ("R3", r3_call_not_guarded)]


def scan_file(path):
    """Findings for one file, or None when it does not call an LLM API at all."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Cheap gate before parsing. A repo-wide scan reads far more files than it
    # cares about, and parsing every one of them is the slow part.
    if not any(k in src for k in ("anthropic", "Anthropic", "openai", "OpenAI")):
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None          # python 2, templates, partial files. Not a finding.
    out = []
    for code, rule in FILE_RULES:
        for line, detail in rule(tree):
            out.append((code, line, detail))
    return out


def r4_nothing_measures_it(root):
    """Repo level. Is there anything at all that checks this code?

    Widened 2026-11-10. The first version looked only for files named like
    tests, and it fired on a repo of mine that has a GitHub Actions workflow
    running a checker on every pull request. Nothing was named test, and
    something was very much measuring it.

    Still crude. A workflow that only lints, or a single empty test file,
    both count as "measured" here. The rule is a floor: when it fires, there
    is genuinely nothing, and that is the claim worth making.
    """
    for p in root.rglob("*.py"):
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            return False
        if "test" in p.parts or "tests" in p.parts:
            return False
    if any((root / ".github" / "workflows").glob("*.y*ml")):
        return False
    return True


def scan_repo(root):
    root = Path(root)
    findings, touched = [], 0
    for p in sorted(root.rglob("*.py")):
        if ".git" in p.parts or "node_modules" in p.parts:
            continue
        res = scan_file(p)
        if res is None:
            continue
        touched += 1
        for code, line, detail in res:
            findings.append((code, p.relative_to(root), line, detail))
    if touched and r4_nothing_measures_it(root):
        findings.append(("R4", Path("."), 0, "no tests and no CI workflow"))
    return findings, touched


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip().splitlines()[-1])
    for target in sys.argv[1:]:
        findings, touched = scan_repo(target)
        print(f"\n  {target}")
        print(f"  {touched} file(s) calling an LLM API, {len(findings)} finding(s)")
        for code, rel, line, detail in findings:
            where = f"{rel}:{line}" if line else str(rel)
            print(f"    {code}  {where:<34} {detail}")
    print()


if __name__ == "__main__":
    main()
