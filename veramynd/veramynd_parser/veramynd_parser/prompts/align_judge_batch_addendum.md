## Batch mode (multiple standards, one lesson)

You will receive **one lesson** and a list of **candidate standards**.
Evaluate **each standard independently** against the same lesson.

Rules for independence (critical for quality):
- Do **not** let one standard's verdict influence another.
- Do **not** share evidence across standards unless the same lesson span
  genuinely supports both (rare — usually different quotes).
- Do **not** soften `none` to `partial` because a neighboring standard was a match.
- Apply hard gates and clause decomposition **per standard**.

## Output (batch) — overrides the single-object Output section above

Return **one JSON object** with a `results` array matching the provided schema.
- Exactly **one** object per input `standard_code` (same codes, no extras, no omissions).
- Each object uses the same fields as the single-pair schema, plus `standard_code`.
- Prefer input list order; codes must match exactly.
- No markdown fences, no extra keys.
