# ELA Normalization Schema — Required-Field Rationale (for the AI engineer)

This handoff is the **resource side** of the standards-alignment pipeline. A normalization record describes one curriculum resource; the scoring engine + a per-grade/per-state overlay then judge how well that resource teaches each standard (met / partial / none). **Every required field exists because the engine needs it to score.** If a field the engine consumes were optional, records could validate but be unscoreable — so the required set is defined by "what the engine reads," not by "what looks like tidy metadata."

## Files

- `curriculum_normalization.ela.schema.json` — ELA profile. Constrains `domain.primary` to
  the eight ELA strands and adds ELA-required fields on top of the universal required
  set + enums described below.
- `ela_normalization_template.blank.json` — fill-in-the-blank template mirroring the schema.

**Not included in this repo:** `curriculum_normalization.core.schema.json` (the
subject-agnostic base the ELA profile's `allOf` composes via `$ref`) and
`ela_normalization_template.filled_example.json` (a passing worked example). The ELA
schema file's `$ref` to the core schema will not resolve without it, so
`curriculum_normalization.ela.schema.json` alone cannot currently validate a full
record with a generic JSON Schema tool — it only carries the ELA-specific
constraints (the `domain.primary` enum, the conditional `genre`/`text_complexity`
requirements, `subject_profile`). The universal required set the core schema was meant
to enforce (`resource_id`, `title`, `provenance.{program,grade,subject}`,
`placement.resource_type`, `objective`, `what_is_taught[>=1]`, `student_actions`,
`evidence[>=1]`) is enforced instead by the Python `NormalizedLesson` Pydantic model at
runtime (`veramynd_parser/normalize/models.py`), which is authoritative for this
pipeline regardless of whether these JSON Schema files are current. If you need to
validate records with an external tool, recover or rewrite the core schema first.

## Why the core requires what it requires

`resource_id`, `title` — identity; lets `part_of`/`children` resolve so supplemental resources attach to what they support.

`provenance.program`, `provenance.grade`, `provenance.subject` — routing. Overlays are cut **per grade and per state**, so `grade` must be present to select the right overlay, and `subject` selects the right profile. `provenance.jurisdiction` (optional) names the state/authority a record should be scored against; fill it when the target overlay is known.

`placement.resource_type` — tells the engine whether it's scoring a whole unit, a single lesson, or a standalone supplemental so it calibrates breadth expectations.

`domain.primary` — a coarse, **framework-neutral** content strand; narrows which standards are even candidates. This is a science-of-reading taxonomy (phonological awareness / phonics / fluency / vocabulary / comprehension / writing / language / speaking & listening), **not** any single state's strand codes — CCSS (RL/RI/RF/W/SL/L), Georgia GSE, and Texas TEKS all carve strands differently and none map 1:1. The record therefore does **not** adopt one framework's strand list; it stays neutral and the **per-state overlay owns the crosswalk** from neutral strand to that state's architecture — exactly the division of labor that keeps the record standards-agnostic. See "Why the strands are framework-neutral" below.

`objective`, `what_is_taught[]` (≥1) — the skill claim, stated in the resource's own framework-neutral words. Each `what_is_taught` item is now a structured object `{skill, cognitive_demand, emphasis?}`, not a bare string, so the engine can (a) match each sub-skill to a **clause** of a decomposed compound standard — RL.1.2 "retell / including key details / demonstrate central message" is three scoreable clauses, and a lesson may cover only one — making **partial-span coverage** expressible, and (b) run the **Webb DOK-consistency check** per clause. `cognitive_demand` (required) is Webb's Depth of Knowledge (`DOK1_recall_reproduction | DOK2_skills_concepts | DOK3_strategic_thinking | DOK4_extended_thinking`): a resource that touches a standard's topic at a **lower DOK than the standard's verb demands is partial, not met** — the schema previously had no signal for this, so a shallow recall task and a strategic-reasoning task looked identical. `emphasis` (optional: `primary | secondary | incidental`) feeds balance-of-representation. Pair with `what_is_NOT_taught` to mark the span the resource deliberately omits.

**No standards field — by design.** The record never declares which standards a resource aligns to. That would be circular: alignment is precisely the engine's output, and a pre-declared code risks leaking back in as a prior and biasing the score. The engine iterates over the candidate standards the per-grade/per-state overlay supplies and asks "does this resource teach it?" using `objective` + `what_is_taught` + `student_actions` + `evidence`. If you ever want the publisher's *claimed* alignment for evaluation, store it in a separate sidecar keyed by `resource_id` so it never touches what the scorer sees.

`student_actions` (all nine + `domain_specific`) — the actions the engine's **student-actor gate** scores. Each is either a description of *how* the student performs it or the literal `NONE OBSERVED`.

`evidence[]` (≥1) — **the single most important part, and the reason the schema is worth enforcing.** The engine justifies every label with a quote and applies the actor gate. Each item now carries six fields, `{quote, location, actor, evidence_role, support, supports_action}` (+ optional `qualifiers`), because `actor` alone is not enough to score correctly:

- `quote` — verbatim source text (task wording, teacher script, sentence frame). Not a paraphrase.
- `location` — where it lives, for audit.
- `actor` — `student | teacher | shared | unspecified`: who performs the act in the quote.
- `evidence_role` — the pedagogical **function** of the quote: `directive_prompt` (an instruction that *calls for* an act — not proof it happened), `student_production` (captured student output), `elicitation_check` (a question eliciting a student response), `teacher_model` (teacher demonstrates), `teacher_scribe` (teacher records student talk, e.g. shared/interactive writing — must not count as student production), `assessment_item`. This feeds the engine's **directive/elicitation exception**: `actor` says who acts, `evidence_role` says whether the quote is a call-for vs. a demonstration. The filled example makes the difference explicit — the "Turn and tell your partner…" quote is `student` + `directive_prompt`, while the note-catcher quote is `student` + `student_production`, and the anchor-chart quote is `teacher` + `teacher_scribe`.
- `support` — per-evidence scaffolding (`independent | with_prompting | modeled | not_applicable`). This is the **authoritative** signal for the "with prompting and support" / "with adult support" qualifier, because scaffolding is per-act, not per-lesson. `teacher_actions.with_prompting_and_support` remains as a coarse record-level summary only.
- `qualifiers` — manner/quality modifiers on the act (`"using key details"`, `"in complete sentences"`, `"orally"`, `"with accuracy"`). The engine's **manner-modifier principle** matches these against a standard's modifiers to decide **met vs. partial**. Without them the engine can't tell "retell a story" from "retell including key details in sequence."
- `supports_action` — the join key from a claimed `student_actions` key to the quote that proves it.

**Coverage rule (enforce in the pipeline).** JSON Schema can't cross-reference, so `supports_action` is required per item but the pipeline must additionally check that **every non-`NONE OBSERVED` student action is named by ≥1 evidence item**. The engine can only score quoted acts; an action claimed in `student_actions` with no backing evidence is unscoreable and must not be silently credited. A record with `student_actions` but thin `evidence` describes what happened without proving it.

## What the ELA profile adds as required

`subject_profile.mode` — the **Interpretation / Construction** axis (`interpretation | construction | both`). Interpretation = student works from given material; Construction = student produces new material. This decides which side of a two-sided standard a resource can satisfy, so the engine needs it on every ELA record.

`teacher_actions.with_prompting_and_support` (`yes | no`) — the scoring twin of CCSS "with prompting and support" / Georgia "with adult support." It moves the line between **partial** and **met** on K–1 standards, so it's required in ELA.

`subject_profile.genre` — **conditionally required**: forced only when `domain.primary` is `Writing` or `Comprehension`, because the Techniques strand is genre-gated (narrative / expository / opinion / poetic). On foundational-skills records (phonics, phonological awareness) genre is irrelevant, so the schema does not demand it there — avoiding `n/a` noise while still guaranteeing genre wherever the engine actually uses it. This is expressed with an `if/then` in the ELA schema.

`subject_profile.text_complexity` (`{quantitative, qualitative, reader_and_task?}`) — **conditionally required** when `domain.primary` is `Comprehension`, expressed as a second `if/then` in the ELA schema. A reading standard's grade-alignment is inseparable from text complexity (the CCSS three-part model, R.10): a grade-appropriate comprehension move performed on a **below-band** text is not grade-aligned, and without this block the engine literally cannot see the text the move was performed on. `quantitative` should carry the measure **and** the band it falls in, and — critically for K–2 — should note when a text is a **read-aloud**, because a read-aloud removes the decoding load and legitimately lets students work above the independent-reading band (the filled example's *Beaks!* is above the grade-1 band but teacher-mediated). Omitted for non-Comprehension records to avoid noise. Fluency (reading connected text) is a plausible future extension of this gate.

## Why the strands are framework-neutral

`domain.primary` is deliberately **not** any state's strand architecture. Every framework carves ELA differently — CCSS uses RL / RI / RF / W / SL / L; Georgia GSE, Texas TEKS, and others differ again, and "Comprehension" alone spans CCSS's separate RL and RI strands. If the record hard-coded one framework's strands, then (a) it would stop being framework-neutral — the same leakage risk that made us drop the standards field — and (b) candidate-narrowing for any *other* state would be a cross-ontology match, quietly injecting error into the one step the field exists to serve.

So the strands stay a coarse, framework-neutral science-of-reading taxonomy whose only job is cheap candidate-narrowing (don't score a phonics resource against a writing standard). The **per-grade/per-state overlay owns the crosswalk** from neutral strand to that state's strands — the identical division of labor that lets the overlay, not the record, supply the standards. Finer distinctions inside a neutral strand (literary vs. informational within `Comprehension`, for instance) are recovered downstream from `subject_profile.mode`, `subject_profile.genre`, and `what_is_taught`, so the coarse enum never needs to mirror a framework. Bottom line: **don't remove the strands — removing them would throw away a cheap, high-precision filter and force the engine to narrow candidates purely semantically. Keep them neutral and let the overlay translate.**

## Extending to other subjects later

Add a sibling profile (e.g. `curriculum_normalization.math.schema.json`) that `allOf`-`$ref`s the same core, constrains `domain.primary` to its strands, and requires whatever its overlay reads (for math, likely a representation/model requirement rather than the I/C axis). The core — including the required `evidence[]` block and actor gate — stays identical, so cross-subject records remain comparable.
