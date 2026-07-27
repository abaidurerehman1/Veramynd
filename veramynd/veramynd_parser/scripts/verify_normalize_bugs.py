"""Verify normalize bug fixes."""
from __future__ import annotations

import json
import re
from pathlib import Path

from veramynd_parser.models import Lesson
from veramynd_parser.normalize.models import parse_ela_record
from veramynd_parser.normalize.sanitize import (
    lesson_source_corpus,
    quote_is_verbatim,
    redact_standard_codes,
)

ROOT = Path(__file__).resolve().parents[1]
NORM = ROOT / "output" / "normalize"
LESSONS = ROOT / "output" / "stage1" / "lessons"
CODE_RE = re.compile(r"\b(?:RL|RI|RF|W|SL|L)\.\d+[a-zA-Z0-9.]*\b")


def main() -> None:
    files = sorted(NORM.glob("G*.json"))
    bad_pacing = []
    leaks = []
    invented_moon = []
    non_verb = []

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        pacing = data["placement"]["pacing"]
        if not re.fullmatch(r"\d+ minutes", pacing or ""):
            bad_pacing.append((path.name, pacing))

        for i, ev in enumerate(data["evidence"]):
            found = CODE_RE.findall(ev["quote"])
            if found:
                leaks.append((path.name, i, found))

        lesson = Lesson.model_validate_json((LESSONS / path.name).read_text(encoding="utf-8"))
        corpus = lesson_source_corpus(lesson)
        for i, ev in enumerate(data["evidence"]):
            q = ev["quote"]
            if quote_is_verbatim(q, corpus):
                continue
            if any(redact_standard_codes(line) == q for line in corpus.split("\n")):
                continue
            non_verb.append((path.name, i, q[:90]))

        if path.name == "G1M2U2L3.json":
            for i, ev in enumerate(data["evidence"]):
                ql = ev["quote"].lower()
                if "what does the moon look like" in ql:
                    invented_moon.append((i, ev["quote"]))

        parse_ela_record(data)

    print(f"files={len(files)}")
    print(f"bad_pacing={len(bad_pacing)} {bad_pacing[:3]}")
    print(f"code_leaks={len(leaks)} {leaks[:5]}")
    print(f"invented_moon={invented_moon}")
    print(f"non_verbatim={len(non_verb)}")
    for row in non_verb[:5]:
        print(" ", row)
    print("all_parse_ok")


if __name__ == "__main__":
    main()
