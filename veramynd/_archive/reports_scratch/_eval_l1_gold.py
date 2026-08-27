import json
from collections import defaultdict
from pathlib import Path

gold_path = Path("output/reports/gold_set_batch1_from_md.jsonl")
judge_path = Path("output/judge/G1M2U1L1.json")

allowed: dict[str, set[str]] = defaultdict(set)
for line in gold_path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    if row.get("resource_id") == "G1M2U1L1":
        allowed[row["standard_code"]].add((row.get("matched_status") or "").lower())

judge = json.loads(judge_path.read_text(encoding="utf-8"))
pred = {
    v["standard_code"]: (v.get("matched_status") or "").lower()
    for v in (judge.get("verdicts") or [])
}

print("gold_items_for_L1:")
for code, statuses in sorted(allowed.items()):
    p = pred.get(code, "")
    ok = p in statuses if p else False
    shown = p or "(not judged)"
    print(f"  {code} gold={sorted(statuses)} json={shown} {'OK' if ok else 'MISS'}")

common = sorted(set(allowed) & set(pred))
match = sum(1 for c in common if pred[c] in allowed[c])
full_match = sum(1 for c in allowed if pred.get(c, "") in allowed[c])
print("---")
print("overlap", len(common))
print("overlap_match", match)
print("overlap_accuracy_pct", round(match / len(common) * 100, 2) if common else 0)
print("gold_total", len(allowed))
print("gold_unjudged", len(allowed) - len(common))
print("full_gold_accuracy_pct", round(full_match / len(allowed) * 100, 2) if allowed else 0)
