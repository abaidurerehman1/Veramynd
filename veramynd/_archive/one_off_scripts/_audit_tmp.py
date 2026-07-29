import json
import re
from collections import Counter
from pathlib import Path

norm_dir = Path(__file__).resolve().parent / "output" / "normalize"
stage1_dir = Path(__file__).resolve().parent / "output" / "stage1" / "lessons"

directive_re = re.compile(
    r"(?i)\b(invite students|have students|tell students they will|"
    r"ask students|direct students' attention|"
    r"encourage students)\b"
)
# Stronger: student-act eliciting verbs often mis-tagged as teacher_model
student_directive_re = re.compile(
    r"(?i)\b(invite students to|have students|tell students (?:they|to)|"
    r"ask students to|prompt students to)\b"
)
ready_re = re.compile(
    r"(?i)(?:"
    r"thumbs[- ]up.{0,80}ready to begin"
    r"|ready to begin (?:writing|drawing|reading|listening)"
    r"|are you ready\b"
    r"|show (?:me |a )?thumbs[- ]up if (?:you|they) are ready"
    r")"
)
question_re = re.compile(r"(?i)^\s*[-'\"]?\s*(what|how|why|who|where|when)\b.+\?")

issues = []
for p in sorted(norm_dir.glob("G*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    code = d["resource_id"]
    domains = {d["domain"]["primary"], *d["domain"].get("secondary", [])}
    genre = d["subject_profile"]["genre"]
    tc = d["subject_profile"].get("text_complexity")
    if domains & {"Writing", "Comprehension"} and genre == "n/a":
        issues.append((code, "genre_n/a", genre))
    if "Comprehension" in domains:
        if not tc or (
            (tc.get("quantitative") or "").lower() in ("", "n/a")
            or (tc.get("qualitative") or "").lower() in ("", "n/a")
        ):
            issues.append((code, "tc_bad", tc))
    if "domain_specific" not in d.get("student_actions", {}):
        issues.append((code, "missing_domain_specific", None))

    mode = d["subject_profile"]["mode"]
    sa = d["student_actions"]

    ids = set()
    writing_steps = []
    s1p = stage1_dir / f"{code}.json"
    if s1p.exists():
        s1 = json.loads(s1p.read_text(encoding="utf-8"))
        for b in s1.get("instructional_blocks", []):
            ids.add(f"{b['section']} {b['letter']}")
            for step in b.get("steps", []):
                if re.search(
                    r"(?i)\b(write|drawing|draw|retell|role[- ]?play|act out)\b",
                    step or "",
                ):
                    writing_steps.append(step)

    for ev in d.get("evidence", []):
        role = ev.get("evidence_role")
        actor = ev.get("actor")
        quote = ev.get("quote", "")
        loc = (ev.get("location") or "").strip()
        m = re.match(r"^(.+?)\s+([A-Z])\b", loc)
        if m and ids:
            bid = f"{m.group(1)} {m.group(2)}"
            if bid not in ids:
                issues.append((code, "loc_orphan", loc))
        if actor == "teacher" and role in (
            "directive_prompt",
            "elicitation_check",
            "student_production",
        ):
            issues.append((code, "actor_teacher_on_student_role", role))
        if role == "teacher_model" and student_directive_re.search(quote):
            issues.append((code, "student_directive_as_teacher_model", quote[:100]))
        if role == "teacher_model" and question_re.search(quote) and ev.get("supports_action") == []:
            issues.append((code, "question_as_teacher_model", quote[:100]))
        if ready_re.search(quote) and ev.get("supports_action"):
            issues.append(
                (code, "readiness_with_actions", (quote[:90], ev.get("supports_action")))
            )
        # teacher_model with non-empty supports_action (prompt says [] only)
        if role in ("teacher_model", "teacher_scribe") and ev.get("supports_action"):
            issues.append(
                (code, "teacher_role_with_supports", (role, ev.get("supports_action"), quote[:80]))
            )
        # support mismatch
        if role in ("teacher_model", "teacher_scribe") and ev.get("support") != "not_applicable":
            issues.append((code, "teacher_role_bad_support", (role, ev.get("support"))))

    if writing_steps and sa.get("written_production") == "NONE OBSERVED":
        strong = [
            s
            for s in writing_steps
            if re.search(
                r"(?i)\b(begin writing|write (?:a |about|the )|independently .{0,40}writ)",
                s,
            )
        ]
        if strong:
            issues.append((code, "written_NONE_but_steps", strong[0][:120]))

    # construction mode check: writing/role-play claimed but mode interpretation
    if mode == "interpretation":
        has_construction_claim = (
            sa.get("written_production", "NONE OBSERVED") != "NONE OBSERVED"
            or any(
                re.search(r"(?i)\b(role[- ]?play|act out|retell)\b", e.get("quote", ""))
                for e in d.get("evidence", [])
            )
        )
        if has_construction_claim:
            issues.append(
                (
                    code,
                    "mode_interpretation_with_construction",
                    (sa.get("written_production"), mode),
                )
            )

print("ISSUE COUNTS:")
c = Counter(t for _, t, _ in issues)
for k, v in c.most_common():
    print(f"  {k}: {v}")
print("\nSAMPLES:")
shown = Counter()
for code, t, ev in issues:
    if shown[t] < 4:
        print(f"  [{t}] {code}: {ev!r}")
        shown[t] += 1

# Domain/genre/tc summary
print("\nDOMAIN/GENRE/TC OK CHECK:")
ok = 0
for p in sorted(norm_dir.glob("G*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    domains = {d["domain"]["primary"], *d["domain"].get("secondary", [])}
    genre = d["subject_profile"]["genre"]
    tc = d["subject_profile"].get("text_complexity")
    bad = False
    if domains & {"Writing", "Comprehension"} and genre == "n/a":
        bad = True
    if "Comprehension" in domains and (
        not tc
        or (tc.get("quantitative") or "").lower() in ("", "n/a")
        or (tc.get("qualitative") or "").lower() in ("", "n/a")
    ):
        bad = True
    if not bad:
        ok += 1
print(f"  {ok}/{len(list(norm_dir.glob('G*.json')))} pass genre/tc conditionals")
