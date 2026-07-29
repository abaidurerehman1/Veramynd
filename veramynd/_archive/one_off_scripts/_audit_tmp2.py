import json
import re
from pathlib import Path

norm_dir = Path("output/normalize")
stage1_dir = Path("output/stage1/lessons")

student_directive_re = re.compile(
    r"(?i)\b(invite students to|have students|tell students (?:they|to)|"
    r"ask students to|prompt students to)\b"
)

print("=== Mis-tagged teacher_model with empty supports (student directives) ===")
for p in sorted(norm_dir.glob("G*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    for i, ev in enumerate(d["evidence"]):
        if ev["evidence_role"] != "teacher_model":
            continue
        q = ev["quote"]
        if student_directive_re.search(q) and not ev.get("supports_action"):
            # check if any other evidence covers a likely action from the quote
            print(f"{d['resource_id']}[{i}] actor={ev['actor']} support={ev['support']}")
            print(f"  Q: {q[:140]}")

print("\n=== written_production NONE OBSERVED vs strong write steps ===")
write_invite = re.compile(
    r"(?i)(?:invite students to .{0,60}writ|students will .{0,40}writ|"
    r"begin writing|independently .{0,30}writ|write (?:a |their |about ))"
)
for p in sorted(norm_dir.glob("G*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    if d["student_actions"]["written_production"] != "NONE OBSERVED":
        continue
    s1p = stage1_dir / f"{d['resource_id']}.json"
    if not s1p.exists():
        continue
    s1 = json.loads(s1p.read_text(encoding="utf-8"))
    hits = []
    for b in s1["instructional_blocks"]:
        for step in b["steps"]:
            if write_invite.search(step or ""):
                hits.append(f"{b['section']} {b['letter']}: {step[:110]}")
    if hits:
        print(f"\n{d['resource_id']} mode={d['subject_profile']['mode']} domains={d['domain']}")
        for h in hits[:3]:
            print(f"  STEP: {h}")
        # any evidence mentioning write?
        write_ev = [e for e in d["evidence"] if re.search(r"(?i)\bwrit", e["quote"])]
        print(f"  evidence with 'writ': {len(write_ev)}")
        for e in write_ev[:2]:
            print(f"    role={e['evidence_role']} actor={e['actor']} sa={e['supports_action']} :: {e['quote'][:90]}")

print("\n=== support != not_applicable on teacher_model/scribe ===")
n = 0
for p in sorted(norm_dir.glob("G*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    for ev in d["evidence"]:
        if ev["evidence_role"] in ("teacher_model", "teacher_scribe"):
            if ev["support"] != "not_applicable":
                n += 1
                if n <= 5:
                    print(f"{d['resource_id']}: support={ev['support']} role={ev['evidence_role']} {ev['quote'][:80]}")
print(f"total: {n}")

print("\n=== Closing A / orphan-ish locations remaining ===")
for p in sorted(norm_dir.glob("G*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    s1 = json.loads((stage1_dir / f"{d['resource_id']}.json").read_text(encoding="utf-8"))
    ids = {f"{b['section']} {b['letter']}" for b in s1["instructional_blocks"]}
    for ev in d["evidence"]:
        loc = ev["location"]
        m = re.match(r"^(.+?)\s+([A-Z])\b", loc.strip())
        if not m:
            print(f"{d['resource_id']}: unparseable loc {loc!r}")
            continue
        bid = f"{m.group(1)} {m.group(2)}"
        if bid not in ids:
            print(f"{d['resource_id']}: orphan {loc!r} known={sorted(ids)[:5]}...")

print("\n=== prompt_version on outputs ===")
versions = set()
for p in sorted(norm_dir.glob("G*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    versions.add(d.get("_pipeline", {}).get("prompt_version"))
print(versions)
