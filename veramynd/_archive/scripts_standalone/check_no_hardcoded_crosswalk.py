#!/usr/bin/env python3
"""Guardrail: fail if any .py file contains a hardcoded standard-to-standard
crosswalk dict literal.

This exists because the crosswalk-correction layer regressed into exactly
this pattern twice in one session, after being explicitly told not to. A
human catching it by re-reading code is not a guardrail -- this is.

DETECTION
---------
Parse every .py file with `ast` (no execution, no imports needed) and walk
every dict literal. A dict entry is "crosswalk-shaped" when its key AND
value(s) both look like standard codes (matched against two independent
regexes, one CCSS-ish, one GA-ish, deliberately permissive since the point is
to catch this shape from ANY two frameworks, not just these two). A dict with
three or more crosswalk-shaped entries is flagged -- one or two coincidental
code-like strings can happen in a docstring example; three in one literal
dict is a mapping table.

Run standalone: `python3 check_no_hardcoded_crosswalk.py [dir ...]`
Exit code 0 = clean, 1 = found hardcoded mapping(s) (message printed).

Also importable: `from check_no_hardcoded_crosswalk import scan_file` for use
from a pytest test (see tests/test_no_hardcoded_crosswalk.py).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Two independent code-shape patterns, not tied to one specific framework:
# "LETTERS.grade.number[suffix]" (CCSS-ish: L.1.1c, RL.1.7, W.1.8 -- same
# shape as text_utils.STANDARD_CODE elsewhere in this repo) and
# "grade.LETTERS(.LETTERS/number)+[suffix]" (GA-ish: 1.L.GC.2.c, 1.T.SS.1.b,
# variable depth). Any source/target standard framework using dotted
# hierarchical codes will match one of these -- that's the point, this isn't
# specific to CCSS/GA.
_CODE_LIKE = re.compile(
    r"^(?:"
    r"[A-Z]{1,4}\.(?:K|\d+)\.\d+[a-z]{0,3}"          # L.1.1c, RL.1.7, W.1.8
    r"|"
    r"\d+\.[A-Za-z]+(?:\.[A-Za-z0-9]+)+"             # 1.L.GC.2.c, 1.T.SS.1.b
    r")$"
)

MIN_ENTRIES_TO_FLAG = 3


def _looks_like_code(s: str) -> bool:
    return bool(_CODE_LIKE.match(s.strip()))


def _value_codes(node: ast.AST) -> list[str]:
    """Pull code-like strings out of a dict value, whether it's a bare
    string or a list/tuple of strings (the multi-candidate mapping shape)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value] if _looks_like_code(node.value) else []
    if isinstance(node, (ast.List, ast.Tuple)):
        out = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and _looks_like_code(elt.value):
                out.append(elt.value)
        return out
    return []


def scan_source(source: str, filename: str = "<string>") -> list[str]:
    """Return a list of human-readable findings; empty means clean."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        crosswalk_entries = 0
        examples: list[str] = []
        for key_node, val_node in zip(node.keys, node.values):
            if key_node is None or not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
                continue
            if not _looks_like_code(key_node.value):
                continue
            val_codes = _value_codes(val_node)
            if val_codes:
                crosswalk_entries += 1
                examples.append(f"{key_node.value!r}: {val_codes!r}")
        if crosswalk_entries >= MIN_ENTRIES_TO_FLAG:
            line = getattr(node, "lineno", "?")
            findings.append(
                f"{filename}:{line}: dict literal with {crosswalk_entries} standard-code-to-"
                f"standard-code entries -- looks like a hardcoded crosswalk. Examples: "
                f"{'; '.join(examples[:3])}"
            )
    return findings


def scan_file(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_source(source, filename=str(path))


def scan_paths(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.py")):
                findings.extend(scan_file(f))
        elif p.suffix == ".py":
            findings.extend(scan_file(p))
    return findings


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    targets = [Path(a) for a in argv] if argv else [Path(__file__).parent]
    findings = scan_paths(targets)
    if findings:
        print("HARDCODED CROSSWALK DETECTED -- move this data to a CSV and read it at runtime:")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"Clean: no hardcoded standard-to-standard mappings found in {[str(t) for t in targets]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
