"""Draw a sample of public repos that call an LLM API, and scan them.

The sampling is the whole problem. A count from "whatever the search ranked
first" looks like a population statistic and measures the ranking. So the
sample is split by star count, four groups, each its own query. That is
describable, and it makes the result sharper than one number: "the rate barely
moves as stars go up" is a finding, "seven in ten repos" on its own is not,
because it hides which seven.

    0            learning projects, tutorials, abandoned
    1 to 10      small real projects
    11 to 100    has users
    101 and up   has a community

HOW THIS WORKS, AND THE VERSION THAT DID NOT.

The first version searched code for `import anthropic` and added `stars:` to
the query. It ran, it returned results, and the results were nonsense:

    import anthropic language:python              1,730,560 files
      the same query with stars:0                         2
      the same query with stars:1..10                     0
      the same query with stars:>100                     65

Two plus zero plus 65, out of 1.73 million. `stars:` is not a code search
qualifier. It was silently accepted and silently meaningless, which is the
worst of both. Nothing errored. Two of the four buckets just came back empty
and I only noticed because empty looked wrong.

So it searches REPOSITORIES instead, where `stars:` is real:

    anthropic claude language:python stars:0          5,938
      stars:1..10                                     3,450
      stars:11..100                                     562
      stars:>100                                        207

Then for each repo: one request for the file list, which also answers R4, then
fetch the Python files and run R1 to R3 on each.

WHAT THE SAMPLE ACTUALLY IS, stated because the change matters. Not "files that
import the SDK". It is "repos whose name, description or README mentions
anthropic and claude". That skews toward projects that describe themselves,
which are probably a little more deliberate than average. It is a different
population from the first version and the honest move is to name it rather
than let the headline imply the broader one.

Two rate limits, both free:

    repo search   30 requests per minute
    everything    5000 requests per hour

At most MAX_FILES Python files are read per repo, so a large repo is sampled
rather than scanned. Files over MAX_BYTES are skipped.

What this does NOT do: name repos in any published output, open issues or pull
requests, contact anyone, or look for credentials. See README.

Run:  python3 sample.py [--per-bucket N]
      python3 sample.py --report
"""
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import audit

BUCKETS = [("0", "stars:0"), ("1-10", "stars:1..10"),
           ("11-100", "stars:11..100"), ("101+", "stars:>100")]

REPO_QUERY = "anthropic claude language:python"

MAX_FILES = 15        # Python files read per repo. A big repo is sampled.
MAX_BYTES = 200_000   # skip generated or vendored files

RAW = Path("findings_raw.json")       # gitignored. Holds repo names.
PUBLIC = Path("results.json")         # counts only. Safe to commit.


def gh(args, allow_fail=True):
    """Call the gh CLI and return parsed JSON, or None.

    Wrapped because this is a network call and R3 of this very scanner is
    "the API call is not inside a try". A rate limit, an outage or a deleted
    repo must skip one file, not end the run.
    """
    try:
        out = subprocess.run(["gh"] + args, capture_output=True, text=True,
                             timeout=60)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"      call failed: {e}")
        return None
    if out.returncode != 0:
        if not allow_fail:
            sys.exit(f"gh failed: {out.stderr.strip()[:200]}")
        print(f"      gh said: {out.stderr.strip()[:120]}")
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def search_repos(bucket_q, per_page):
    """Repo full_names in one star bucket.

    Repository search, not code search. Code search accepts `stars:` and
    ignores it, which is how the first version of this file produced two empty
    buckets out of four. See the module docstring.
    """
    data = gh(["api", "-X", "GET", "search/repositories",
               "-f", f"q={REPO_QUERY} {bucket_q}",
               "-f", f"per_page={per_page}"])
    if not data:
        return []
    return [i["full_name"] for i in data.get("items", [])]


def fetch(repo, path):
    """Raw file text, or None. Uses the 5000/hour budget, not the search one."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/{path}",
             "-H", "Accept: application/vnd.github.raw"],
            capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return out.stdout if out.returncode == 0 else None


def repo_tree(repo):
    """One request for the file list. Answers R4 and picks the files to read.

    Returns (no_checks, python_paths) or (None, []) when the tree is
    unavailable, which is not a finding.
    """
    data = gh(["api", f"repos/{repo}/git/trees/HEAD?recursive=1"])
    if not data:
        return None, []
    no_checks, py = True, []
    for entry in data.get("tree", []):
        p = entry.get("path", "")
        name = p.rsplit("/", 1)[-1]
        if (name.startswith("test_") or name.endswith("_test.py")
                or p.startswith("tests/") or "/tests/" in p
                or p.startswith("test/") or p.startswith(".github/workflows/")):
            no_checks = False
        if (entry.get("type") == "blob" and p.endswith(".py")
                and (entry.get("size") or 0) <= MAX_BYTES
                and "/site-packages/" not in p and not p.startswith("vendor/")):
            py.append(p)
    return no_checks, py[:MAX_FILES]


def scan_source(src):
    """R1 to R3 on one file's text. Reuses audit.py so there is one definition."""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    hits = []
    for code, rule in audit.FILE_RULES:
        for line, detail in rule(tree):
            hits.append({"rule": code, "line": line, "detail": detail})
    return hits


def collect(per_bucket):
    rows, seen = [], set()
    for label, bucket_q in BUCKETS:
        repos = [r for r in search_repos(bucket_q, per_bucket) if r not in seen]
        seen.update(repos)
        print(f"\n  bucket {label}: {len(repos)} repo(s)")
        time.sleep(3)                  # 30 repo searches a minute
        scanned = 0
        for repo in repos:
            no_checks, paths = repo_tree(repo)
            if no_checks is None:
                continue
            got_any = False
            for path in paths:
                src = fetch(repo, path)
                if src is None:
                    continue
                # Same cheap gate audit.py uses: do not parse files that do
                # not touch an SDK at all.
                if not any(k in src for k in ("anthropic", "Anthropic",
                                              "openai", "OpenAI")):
                    continue
                hits = scan_source(src)
                if hits is None:
                    continue
                got_any = True
                rows.append({"bucket": label, "repo": repo, "path": path,
                             "hits": hits, "no_checks": no_checks})
            if got_any:
                scanned += 1
            else:
                # Repo matched on metadata but no file touches an SDK. R4 alone
                # would be a finding about a repo that may not call an LLM at
                # all, so it is dropped rather than counted.
                pass
        print(f"    {scanned} repo(s) with SDK code")
    return rows


def report(rows):
    """Counts only. This is what gets published."""
    out = {"n_files": len(rows), "buckets": {}}
    for label, _ in BUCKETS:
        sub = [r for r in rows if r["bucket"] == label]
        repos = {}
        for r in sub:
            s = repos.setdefault(r["repo"], set())
            s.update(h["rule"] for h in r["hits"])
            if r["no_checks"]:
                s.add("R4")
        counts = Counter()
        for rules in repos.values():
            for code in rules:
                counts[code] += 1
        out["buckets"][label] = {
            "n_repos": len(repos),
            "n_files": len(sub),
            "any_rule": sum(1 for v in repos.values() if v),
            "by_rule": {c: counts.get(c, 0) for c in ("R1", "R2", "R3", "R4")},
        }
    return out


def show(summary):
    print(f"\n  {'bucket':<10} {'repos':>6} {'any':>6} {'R1':>5} {'R2':>5} {'R3':>5} {'R4':>5}")
    print("  " + "-" * 50)
    for label, _ in BUCKETS:
        b = summary["buckets"].get(label)
        if not b:
            continue
        r = b["by_rule"]
        print(f"  {label:<10} {b['n_repos']:>6} {b['any_rule']:>6} "
              f"{r['R1']:>5} {r['R2']:>5} {r['R3']:>5} {r['R4']:>5}")
    print("\n  Counts from an unchecked detector. Precision is not measured yet.")
    print("  See README step F.\n")


def main():
    if "--report" in sys.argv:
        if not RAW.exists():
            sys.exit("No findings_raw.json. Run without --report first.")
        show(report(json.loads(RAW.read_text())))
        return
    per = 30
    if "--per-bucket" in sys.argv:
        per = int(sys.argv[sys.argv.index("--per-bucket") + 1])
    gh(["auth", "status"], allow_fail=False)
    rows = collect(per)
    RAW.write_text(json.dumps(rows, indent=2) + "\n")
    summary = report(rows)
    PUBLIC.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\n  repo names in {RAW} (gitignored)")
    print(f"  counts only in {PUBLIC}")
    show(summary)


if __name__ == "__main__":
    main()
