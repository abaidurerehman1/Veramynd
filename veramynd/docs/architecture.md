# Veramynd — Curriculum Standards Alignment Engine
## Architecture Specification (iter_2)

**Status:** Proposed
**Supersedes:** `iter_1/` (prototype)
**Last updated:** 2026-07-16

> A second, independent design for Stages 2-7 — agentic + standards-graph,
> no vector DB — is being explored in parallel: see
> [`architecture-agentic-graph.md`](architecture-agentic-graph.md). Both
> tracks share Stage 1 and are meant to be measured against the same gold set
> before either is treated as final.

---

## Table of Contents

1. [What the system does](#1-what-the-system-does)
2. [Why rebuild — assessment of iter_1](#2-why-rebuild--assessment-of-iter_1)
3. [Scope](#3-scope)
4. [Architecture overview](#4-architecture-overview)
5. [Stage 1 — Document parsing (Docling)](#5-stage-1--document-parsing-docling)
6. [Stage 2 — Extraction](#6-stage-2--extraction)
7. [Stage 3 — Pedagogical normalization](#7-stage-3--pedagogical-normalization)
8. [Stage 4 — Knowledge base (hybrid RAG)](#8-stage-4--knowledge-base-hybrid-rag)
9. [Stage 5 — Retrieval and rerank](#9-stage-5--retrieval-and-rerank)
10. [Stage 6 — The alignment judge](#10-stage-6--the-alignment-judge)
11. [Stage 7 — Verification and output](#11-stage-7--verification-and-output)
12. [Cross-cutting: data contracts](#12-cross-cutting-data-contracts)
13. [Cross-cutting: configuration](#13-cross-cutting-configuration)
14. [Cross-cutting: caching](#14-cross-cutting-caching)
15. [Cross-cutting: concurrency and resilience](#15-cross-cutting-concurrency-and-resilience)
16. [Evaluation — the gold set](#16-evaluation--the-gold-set)
17. [Cost engineering](#17-cost-engineering)
18. [Repository layout](#18-repository-layout)
19. [Migration plan](#19-migration-plan)
20. [Risk register](#20-risk-register)
21. [Open decisions](#21-open-decisions)

---

## 1. What the system does

Given two documents:

1. **A standards document** — e.g. Common Core ELA standards, K–12.
2. **A curriculum document** — e.g. a publisher's teacher guide for one grade/unit.

The system determines, for every lesson in the curriculum, **which academic standards that lesson actually teaches**, and produces for each (lesson, standard) pair:

| Field | Meaning |
|---|---|
| `matched_status` | `full` / `partial` / `none` |
| `evidence` | A quote from the lesson showing the student performing the standard's act |
| `evidence_page_number` | Where in the source document |
| `confidence` | `high` / `medium` / `low` |

Final deliverable: a per-unit report (CSV / dashboard) linking each standard to the lessons that teach it, with auditable evidence.

**Why this is hard.** This is the work a curriculum specialist does by hand. It is expensive, slow, and inconsistent between raters. The judgment is genuinely subtle — a standard says *"ask and answer questions about key details"*, and deciding whether a lesson in which the teacher asks and students answer meets that standard **fully** or only **partially** requires reading the standard's clauses precisely. The value of this system is applying one rubric identically at scale.

**Why it is not a search problem.** Retrieval narrows the field. The actual determination is a reasoning task against a rubric. Any design that treats similarity score as the answer will be confidently wrong.

---

## 2. Why rebuild — assessment of iter_1

`iter_1` is a working prototype that proved the concept. It has one genuinely excellent asset and a set of structural problems that block productization.

### 2.1 What iter_1 got right (carry forward)

| Asset | Why it matters |
|---|---|
| **`std_alignment_prompt_v4_1.md`** | ~350-line SME-derived rubric. Forces clause decomposition, handles verb-splitting (`ask` *and* `answer` = 2 clauses) vs. manner-modifiers (`speak audibly` = 1), gates on strand/genre, requires student-action evidence. **This is the product.** It ports directly into iter_2's judge. |
| **Coarse-to-fine funnel** | Cheap filter → expensive judge. Avoids the lessons × standards combinatorial blowup. Architecturally correct; iter_2 keeps the shape and upgrades the filter. |
| **Vision-on-tables for standards** | Standards pages are grids; the text layer destroys the row/column relationship that says *which grade* a criteria belongs to. Rasterizing was the right instinct. |
| **Prompt caching, `json_repair` fallback, resume-on-restart** | Practical production instincts already present. |

### 2.2 Structural problems (the reason for iter_2)

**A. No data contract between stages.** Each stage writes JSON to disk; the next stage hopes the shape is right. The LLM produces those shapes and it drifts. This single root cause produces:
- `page_N` wrapper hacks (`standard_extractor.py:98`, `std_aggregator.py:159`)
- Join failures when `cluster_name` differs by an en-dash between two prompts
- `int("1.")` crashing the merge
- `prompt_cluster_summary.md` documenting an input schema the code never sends

**B. Silent failure reported as success.** `std_aggregator.merge_anchor_standards` wraps everything in one `try` whose `except` only logs. `standard_extractor.py:220` then prints `"🎉 Successfully merged standards"` unconditionally. **An entire grade's standards can vanish while the log says it worked.** This is the most dangerous defect in the codebase.

**C. Global mutable state as the inter-module channel.** `standard_extractor.py:144` mutates `os.environ["STD_EXTRC_OUTPUT_DIR"]` mid-loop so downstream modules pick it up. It only works because other modules snapshot env at *import* time. Moving one import inside a function breaks the pipeline untraceably. Modules are rituals, not functions — hence untestable.

**D. Fragile, single-document parsing.** Lesson detection is `text.split("TIMING GOAL")` — a publisher-specific magic string. Title detection is "the last non-noise line before it." Grade is **hardcoded to `K`** (`simple_page_extrc.py:138`). Page indexing is off by one (`simple_page_extrc.py:106` passes 0-indexed pages to a 1-indexed helper → the last page is emitted as page 1 and the true last page is never read).

**E. Existence-based caching.** "Does the file exist?" is the entire caching/resume/idempotency strategy. Consequences: `{"error": ...}` payloads get cached as valid forever; editing a prompt doesn't invalidate anything; a half-written file counts as complete.

**F. Serial execution.** One LLM call at a time with `time.sleep(2)` between. The calls are independent. A run that should take minutes takes hours. The `sleep` is a superstition, not a rate limiter — there is no retry on 429.

**G. No evaluation.** Three prompt versions (`std_alignment_prompt.md`, `_v4`, `_v4_1`) coexist with **no way to know which is best.** Every improvement is a shot in the dark. (Worse: only `_v4_1` emits `confidence`, and `json_to_csv.py:143` silently drops rows lacking it — so pointing the pipeline at an older prompt yields an **empty CSV with no error**.)

### 2.3 Verdict

> **The brain is excellent; the skeleton is a prototype.**

The AI design — the rubric and the funnel — was the hard part and it was done well. The engineering around it fails quietly, is hardcoded to one Kindergarten PDF, and cannot be measured. iter_2 keeps the brain and rebuilds the skeleton.

---

## 3. Scope

### 3.1 In scope

- Ingest a standards PDF → structured, grade-indexed standards.
- Ingest a curriculum PDF → structured lessons.
- Retrieve candidate standards per lesson (hybrid search + rerank).
- Judge each candidate pair against the rubric → status + evidence + confidence.
- Verify evidence is grounded in the source.
- Persist to Postgres; export CSV; serve a dashboard.
- **Generalize to a second publisher's document** — the real product test.
- A measurement harness (gold set) covering retrieval recall and judge accuracy.

### 3.2 Out of scope (v1)

- Real-time / interactive alignment (this is a batch system; nothing waits on it).
- Automatic curriculum *authoring* or gap remediation suggestions.
- Non-ELA subjects (the rubric's overlay is ELA/CCSS-specific — the spine is framework-neutral, the overlay is not).
- Multi-tenant / customer-facing SaaS surface.

### 3.3 Explicitly abandoned from iter_1

| Component | Reason |
|---|---|
| `text_rag.py`, `keyword_rag.py`, `keyword_generation.py` | Unwired experiment, broken end-to-end (`keyword_generation.py` writes `*_keywords.json`; `keyword_rag.py` reads `unit01_lessons.json`). **The *idea* — LLM-distilled keywords to bridge vocabulary mismatch — is promoted to a first-class stage (§7). The code is discarded.** |
| `client_code/` | Demo only. Has a real bug (`json_repair(...)` called as a function; the callable is `json_repair.loads`), a placeholder API key in source, and duplicated helpers. Rebuild as a thin CLI over iter_2 if still needed. |
| `lesson_extraction/toc_extraction.py` | Mostly dead; its TOC regex matches any line ending in digits (`"Lesson 3"` → `{"title": "Lesson", "page_number": 3}`). |
| `token_cost_estimation.py` | Standalone spike against an unrelated chemistry PDF. |
| Markdown round-trip | Lesson data is built as Markdown, written to disk, then re-parsed back to JSON. Lossy serialization of data already in memory; source of the `TIMING GOAL` vs `TIMING GOAL:` mismatch. |

---

## 4. Architecture overview

![Ingest pipeline: standards and lesson PDFs are parsed by Docling, extracted into Pydantic contracts, normalized into a shared pedagogical vocabulary, then embedded and indexed](diagrams/01-ingest.svg)

*Figure 1 — Ingest. Offline, once per document, content-addressed. Both documents are normalized into the same conceptual vocabulary before anything is embedded; §7 explains why this step decides whether the system works.*

![Query pipeline: hybrid search retrieves ~30 candidates, a cross-encoder reranks to 8-12, the alignment judge issues a verdict with evidence, and a grounding check rejects fabricated quotes](diagrams/02-query.svg)

*Figure 2 — Query, per lesson. Coarse-to-fine: a wide recall-oriented net, narrowed by a reranker, decided by the judge, then checked for fabrication at zero token cost.*

![Cross-cutting concerns: gold eval set, content-addressed cache, config as arguments, retry and concurrency](diagrams/03-cross-cutting.svg)

*Figure 3 — Cross-cutting concerns. These are properties of every stage, not stages of their own.*

### 4.1 Core principle

**Every stage is a pure function: artifacts in, artifacts out.**

```python
def extract_standards(pdf: Path, cfg: Config) -> GradeStandards: ...
def normalize_standard(std: Standard, cfg: Config) -> NormalizedStandard: ...
def judge(lesson: Lesson, standard: Standard, cfg: Config) -> AlignmentVerdict: ...
```

No env mutation. No import-order dependency. No hidden disk reads. **Testability, parallelism, and caching all fall out of this one property** — they are not separate features to build.

---

## 5. Stage 1 — Document parsing (Docling)

### 5.1 Why Docling

The two documents need different things, and Docling handles both:

| Document | Challenge | Why Docling |
|---|---|---|
| **Standards** | Dense tables. Grade columns, standard rows, merged cells for bands (`9–10`). The text layer destroys the spatial relationship that says *which grade owns this row*. | Docling's `TableFormer` model does structure recovery — outputs real table objects with cell/row/column identity, not a flat token stream. This is exactly what iter_1 needed vision for. |
| **Lessons** | Prose, but lesson *boundaries* are the problem. iter_1 split on the literal string `TIMING GOAL`. | Docling emits a `DoclingDocument` with heading hierarchy, reading order, and per-element provenance (page + bbox). Headings give us lesson boundaries **structurally** instead of by magic string. |

**Additional reasons:**
- Runs **locally** — no per-page API cost, no data leaving the environment (relevant if curriculum PDFs are licensed).
- Emits **provenance** (page number + bounding box) per element — this is what makes `evidence_page_number` trustworthy instead of a guess with a hardcoded `±7` offset.
- Deterministic and cacheable — parse once per document, forever.

### 5.2 Alternatives considered

| Option | Verdict |
|---|---|
| **Azure Document Intelligence** | Excellent table extraction, but per-page cost and data leaves the environment. Keep as fallback for pathological scanned documents. |
| **Mistral OCR** | Fast, cheap, good. Weaker table structure recovery than Docling's TableFormer for the grid-heavy standards doc. |
| **OpenAI multimodal PDF (optional future)** | Not wired in Stage 1. Stage 1 stays Docling-primary with an explicit PyMuPDF engine path. |
| **iter_1's approach** (manual PyMuPDF rasterize at 200 DPI → vision) | Superseded. Also note: 200 DPI renders ~2200×1700px which the API downscales anyway (~1568px long edge) — paying to render, encode, and upload pixels that get thrown away. 150 DPI is the practical sweet spot. |

**Decision: Docling primary, PyMuPDF as the lightweight / fallback engine, Azure DI reserved as an escape hatch for scanned docs (not implemented in Stage 1).**

### 5.3 Lesson boundary detection — the fallback chain

This is the piece that decides whether the system works on a second publisher's document. iter_1's `TIMING GOAL` split works on exactly one book. Replace with a chain, most reliable first:

![Lesson boundary fallback chain: PDF outline, then Docling headings, then font and layout heuristics, then vision on page images](diagrams/04-fallback-chain.svg)

*Figure 4 — Lesson boundary detection. Try the cheapest, most reliable signal first; fall through only as far as needed.*

Two notes on step 1: many publisher PDFs carry an outline, and **iter_1 already calls `get_toc()` but misuses it** — it grabs the first entry's destination page and discards the rest (`lesson_extraction/toc_extraction.py:28`). Step 3 generalizes across publishers and costs nothing: a lesson title is reliably the largest text on its page.

**Also: read the grade from the document.** It is on the cover page. iter_1 hardcodes `**Grade:** K` and will silently mislabel a Grade 3 unit as Kindergarten, corrupting every downstream alignment.

### 5.4 Bugs from iter_1 that must not survive

| Bug | Location | Fix |
|---|---|---|
| Page off-by-one | `simple_page_extrc.py:106` — `range(total_pages)` → 0-indexed list handed to a 1-indexed helper. `doc[-1]` returns the **last page as page 1**; the true last page is never read. | `range(1, total_pages + 1)`. Add an assertion that page count in == page count out. |
| Hardcoded grade | `simple_page_extrc.py:138` | Extract from document. |
| Magic-string lesson split | `simple_page_extrc.py:28` | Fallback chain above. |
| `TIMING GOAL` vs `TIMING GOAL:` | splitter (no colon) vs extractor (requires colon) | Eliminated with the Markdown round-trip. |
| Appendix cutoff | `simple_page_extrc.py:116` — everything after `^Appendix$` silently dropped, guarded by a magic `page > 5` | Explicit, configurable, logged. |

---

## 6. Stage 2 — Extraction

### 6.1 Structured outputs, not prompt-and-repair

**This is the highest-leverage single change in iter_2.**

iter_1 asks the model to "reply with JSON," then strips markdown fences by slicing (`cleaned[7:]`, `cleaned[:-3]`), then falls back to `json_repair`. This is why the `page_N` wrapper, the en-dash join failures, and the `int("1.")` crash all exist.

Replace with **tool-use / structured outputs**: define the Pydantic schema, pass it to the API, and the schema is enforced at the API layer with retry on mismatch.

**What disappears entirely:**
- `clean_llm_json_output` (3 copy-pasted versions across the repo)
- `json_repair` fallback paths
- The whole class of "the model returned a slightly different key" failures
- The `page_N` unwrap hacks

### 6.2 What gets extracted

**Standards** → `GradeStandards`:
```
{grade: [{
    standard_id, standard_number, section_title, cluster_name,
    anchor_standard, standard_criteria, substandards[],
    provenance: {page, bbox}
}]}
```

**Grade bands must be expanded once, in one place.** iter_1 has **two independent mechanisms** for splitting `9–10` into grade 9 and grade 10 — the prompt tells the model to do it, *and* `indiv_grade_std_extractor._split_banded_grade` does it in Python. The Python one is buggy (returns band *endpoints*, so `"6-8"` → `["6", "8"]` and **grade 7 is lost**; `"K-5"` → `[]`). Pick one mechanism. Recommend: **the model expands, the schema validates, Python does not re-derive.**

**Lessons** → `Unit`:
```
{grade, unit, lessons: [{
    lesson_id, lesson_title, day, page_number, text,
    provenance: {page_start, page_end}
}]}
```

---

## 7. Stage 3 — Pedagogical normalization

> **This is the make-or-break stage of the new architecture. If you skip it, retrieval will have *worse* recall than iter_1's LLM filter, and you will not notice, because there is no error — the standard simply never gets retrieved.**

### 7.1 The problem: vocabulary mismatch

A standard is written in **abstract assessment language**:

> *"Blend and segment syllables in spoken words."* — RF.K.2b

A lesson is written in **concrete classroom language**:

> *"Have children clap out the beats in their names. Ask: how many claps did we hear?"*

These are a **perfect pedagogical match**. They share almost no vocabulary. In embedding space they are **distant**. BM25 finds no overlapping terms. **Both retrieval arms miss it.** The cross-encoder can only rerank what retrieval surfaced — it cannot recover a candidate that was never fetched.

This matters enormously here because it is *structural to the domain*: the entire point of a standard is to describe a competency abstractly enough to be assessment-neutral, while the entire point of a teacher's guide is to be concrete enough to execute in a classroom. **The two corpora are written to be lexically dissimilar.**

iter_1's `keyword_generation.py` was an attempt at exactly this bridge. The idea was right; the implementation was unwired and broken. **Promote the idea; discard the code.**

### 7.2 Why iter_1's dumb filter was accidentally robust here

iter_1's Pipeline 1 used an **LLM** to read cluster summaries and decide relevance. An LLM can make the pedagogical leap:

> *clapping beats in names → syllable awareness → phonological awareness → RF.K.2*

**An embedding model cannot make that inference.** It measures surface semantic similarity, not domain reasoning. This is the specific way a "more sophisticated" retrieval stack can regress against a naive one.

### 7.3 The solution: embed concepts, not prose

Normalize **both sides** into a shared conceptual vocabulary *before* embedding.

**For each standard** (OpenAI small model, cached forever):
```
Input:  standard_criteria + anchor_standard + substandards
Output: NormalizedStandard {
          competency_statement: "what the student must be able to do,
                                 in plain classroom language",
          observable_behaviors: [...],   # what it looks like in a room
          pedagogy_terms: [...],         # standardized terminology
          exact_codes: [...]             # RF.K.2b — preserved for BM25
        }
```

**For each lesson** (OpenAI small model, cached forever):
```
Input:  raw lesson text
Output: NormalizedLesson {
          student_competencies: [...],   # what the STUDENT does
          pedagogy_terms: [...],
          instructional_text: "..."      # logistics stripped
        }
```

**Then embed the normalized representations.** Concept ↔ concept, not prose ↔ prose.

### 7.4 Secondary benefit: cost

The normalizer strips **teacher logistics** — materials lists, timing, room setup, "distribute the worksheets." None of it is evidence of a standard being taught, and iter_1 pays for every token of it, **N times per lesson** (once per candidate standard).

iter_1's own `lesson_keyword_generation_prompt.md` already articulates this filter in its Step 1. Plausibly **halves** lesson token count. That saving then multiplies across every judge call for that lesson.

### 7.5 What NOT to normalize away

The judge must still see the **raw lesson text**. Normalization is for *retrieval only*. The rubric requires quoting real evidence from the actual lesson, and the grounding check (§11.1) string-matches against the real text.

![Normalized text feeds retrieval; raw text feeds the judge, the evidence quote and the grounding check](diagrams/07-normalized-vs-raw.svg)

*Figure 5 — Two lanes. Normalization serves retrieval only; the judge always reads the real lesson.*

Keep both. Never let the normalized version reach the judge.

---

## 8. Stage 4 — Knowledge base (hybrid RAG)

### 8.1 Postgres + pgvector, not Qdrant

**Corpus size reality check:** one grade's standards ≈ a few hundred items. All of K–12 ELA ≈ low thousands. This is **small**.

| | Verdict |
|---|---|
| **pgvector** | ✅ Handles millions of vectors. Postgres is already in the stack for results storage. One service instead of two. Transactional consistency between standards and their alignments — no dual-write problem. |
| **Qdrant** | Reach for it at **>1M vectors** or when you need advanced payload filtering / distributed sharding. **Not justified at this scale.** Adding it now is operational cost with no benefit. |

**Decision: pgvector. Revisit if the corpus grows two orders of magnitude.**

### 8.2 Hybrid = vector + BM25. Both are necessary.

This is not cargo-culting — the domain specifically requires both arms:

| Arm | Catches | Misses |
|---|---|---|
| **BM25** | Exact codes (`RL.K.1`, `RF.K.2a`), precise terminology (`"with prompting and support"`, `"segment phonemes"`) | Paraphrase; the clapping/syllables case |
| **Vector** | Conceptual paraphrase (post-normalization) | Exact code lookup — embeddings are notoriously bad at alphanumeric identifiers |

Standards documents are **saturated with exact identifiers**. A pure-vector system will fail to retrieve `RF.K.2b` when the query mentions `RF.K.2b`. A pure-BM25 system fails on every paraphrase. **Hybrid is required, not optional.**

**Fusion: Reciprocal Rank Fusion (RRF).** Rank-based, so it needs no score normalization between two incomparable scoring systems. Simple, robust, well-established default.

### 8.3 Schema sketch

```sql
standards (
  standard_id PK, grade, section_title, cluster_name,
  anchor_standard, standard_criteria, substandards JSONB,
  provenance JSONB,
  -- normalization
  competency_statement TEXT,
  pedagogy_terms TEXT[],
  embedding vector(N),           -- of competency_statement
  bm25_tsv tsvector              -- GIN index
)

lessons (
  lesson_id PK, grade, unit, day, page_number,
  raw_text TEXT,                 -- for the judge + grounding
  student_competencies TEXT,     -- for retrieval
  embedding vector(N),
  provenance JSONB
)

alignments (
  lesson_id FK, standard_id FK,
  matched_status, evidence, evidence_page_number, confidence,
  grounded BOOL,                 -- §11.1
  judge_model, prompt_version,   -- provenance: which rubric produced this
  retrieval_rank, rerank_score,  -- for funnel diagnostics
  created_at,
  PRIMARY KEY (lesson_id, standard_id, prompt_version)
)
```

**`prompt_version` in the primary key is deliberate.** It lets you re-run `v4_2` alongside `v4_1` and diff them on the same corpus — impossible in iter_1.

---

## 9. Stage 5 — Retrieval and rerank

### 9.1 Tune the first stage for RECALL, not precision

**The funnel has a fatal asymmetry: a false negative in the cheap stage is permanent and invisible.** If retrieval misses a standard, the judge never sees it. No error. No warning. The standard simply never appears in the report.

This is the most common way to get a three-stage funnel wrong: tuning stage 1 as if it were the final answer. **It is not. Its only job is to over-include.** Let the expensive, accurate judge do the rejecting — that is what it is for.

**Retrieve top ~30.** The corpus is small enough that this is nearly free. Being generous here is the cheapest insurance in the system.

### 9.2 Cross-encoder rerank — the biggest accuracy lever

A bi-encoder (what retrieval uses) embeds lesson and standard **separately** and compares vectors. A cross-encoder feeds the **pair together** through the model and scores relevance jointly. It sees interactions a vector distance cannot.

![Retrieval funnel narrowing from top 30 hybrid search results, to 8-12 cross-encoder results, to a judged verdict](diagrams/05-funnel.svg)

*Figure 6 — The coarse-to-fine funnel. Each stage is slower and more accurate than the one above it, so each must hand down fewer items.*

Each stage is ~10× more expensive and ~10× more accurate than the last, over ~3× fewer candidates. That is a well-formed funnel.

**Options:** Cohere Rerank (hosted, strong, per-call cost) or a local `bge-reranker` / `mxbai-rerank` (free, self-hosted, competitive). At this corpus size, **local is likely sufficient** — start there.

### 9.3 Measure recall@K explicitly

For each gold-set pair, record: **was the true standard in the top 30? in the top 10?**

> **If retrieval recall is 85%, the system's ceiling is 85% — no matter how good the rubric is.**

This number must be tracked on every change. It is the single most likely place for silent quality loss, and nobody would ever notice it from the output.

---

## 10. Stage 6 — The alignment judge

**This is where the value is. Everything upstream exists to feed this stage well; everything downstream exists to verify it.**

### 10.1 Keep the v4_1 rubric

Port `std_alignment_prompt_v4_1.md` essentially as-is. It encodes real SME knowledge that would take months to rediscover:

- Clause decomposition rules (split on genuinely independent verbs; **do not** split manner-modifiers)
- Strand/genre gating (a Literature lesson does not satisfy an Informational Text standard)
- Output-type discrimination (opinion vs. informative vs. narrative writing)
- Qualifier handling (`"with prompting and support"` loosens *how much help*, never *who performs the act*)
- The student-quote evidence gate

**Retire `std_alignment_prompt.md` and `_v4.md`.** They emit no `confidence` field, and `json_to_csv.py:143` silently drops rows without it → **empty CSV, no error**. One prompt version, tracked in `prompt_version`, validated by schema.

### 10.2 Model selection

| Stage | Model | Why |
|---|---|---|
| Normalization | **OpenAI** (`gpt-4.1-mini` default via `OPENAI_MODEL`) | Mechanical distillation. Cached forever. OpenAI only. |
| Judge (default) | **OpenAI** (model TBD for Stages 2–7) | The accuracy bottleneck. Deep rubric reasoning. |
| Judge (escalated) | **OpenAI** (stronger model TBD) | Hard cases only — see cascade below. |

> **Note:** Stage 1 normalization uses OpenAI exclusively. There is no alternate-provider path in this codebase.

### 10.3 Extended thinking — ON

The rubric is *explicitly a multi-step reasoning procedure*: decompose into clauses → judge each independently → check strand → check output type → aggregate. It even instructs the model to do all of this **silently**.

That is precisely the workload extended thinking exists for. Forcing multi-step reasoning to happen invisibly inside a normal response leaves accuracy on the table.

**Expectation: one of the largest single accuracy wins available.** Validate against the gold set. Composes well with the cascade — think hardest only on escalated cases.

### 10.4 Cascade — accuracy per dollar

Do not run every pair on the frontier model. **Errors concentrate at the boundary**: `full` and `none` are usually obvious; `partial` is where raters (human and model) disagree.

![Judge cascade: clear-cut verdicts are accepted from the default judge model; partial or low-agreement verdicts escalate to a stronger judge model with extended thinking](diagrams/06-cascade.svg)

*Figure 7 — The cascade. Errors concentrate at the boundary, so the frontier model is spent only there.*

If ~70% of pairs are easy, you pay frontier prices on 30% of calls and capture most of the frontier accuracy.

### 10.5 Uncertainty: use disagreement, not self-reported confidence

**iter_1's `confidence` field is not measuring what it appears to.** Self-reported LLM confidence is poorly calibrated — models say `high` for things they get wrong. And iter_1 uses it as a **hard filter** (`json_to_csv.py:143` drops rows), meaning a miscalibrated field is **silently deleting real results**.

**Better signal — self-consistency:** sample the same pair 3× at temperature ~0.7 and measure disagreement.

- `full / full / full` → genuinely easy, accept.
- `full / partial / none` → **genuinely hard.** *That* is the escalation signal.

Disagreement is an empirical measurement; self-assessment is a guess. On rubric-heavy judgment tasks, self-consistency voting reliably beats a single sample.

Apply **selectively** (only where the cheap pass looks uncertain) to control cost. Keep `confidence` in the output for the report, but **do not use it as a hard filter** — route on disagreement instead.

### 10.6 Do NOT batch multiple standards into one call

Tempting for cost. **Wrong.** The v4_1 rubric is designed to reason about **one** standard in depth. Cramming five into one call degrades clause decomposition and costs accuracy — the one thing you cannot buy back.

**Save money on the prefix (§17.1), not on the reasoning.**

---

## 11. Stage 7 — Verification and output

### 11.1 Evidence grounding check — free hallucination detection

The rubric **requires** the judge to quote evidence from the lesson. So: **string-match the quote against the raw lesson text.**

```python
def is_grounded(evidence: str, lesson_raw_text: str) -> bool:
    # normalize whitespace/quotes/dashes, then check containment
    # (fuzzy match with a high threshold to tolerate minor transcription drift)
```

If the quote is not there, **the model fabricated it.**

| Property | Value |
|---|---|
| API cost | **Zero tokens** |
| Catches | The most embarrassing failure mode: a confident, well-reasoned, entirely **invented** alignment |
| Produces | A **grounding rate** metric, trackable per prompt version |

**Build this early.** It is the highest-leverage item in the entire specification relative to what it costs to build, and it does not depend on the gold set.

Ungrounded verdicts → flag and escalate (or reject outright). Never ship them silently.

### 11.2 Output

- **Postgres** — system of record. Enables diffing prompt versions, funnel diagnostics, incremental re-runs.
- **CSV export** — the client deliverable. Preserve iter_1's parent-row/child-row structure, **but fix**:
  - The `seen_criteria` set is tested with a *stripped* string and inserted with an *unstripped* one (`json_to_csv.py:84` vs `:97`) → duplicate parent rows.
  - Hardcoded `+ 6` page offset (`json_to_csv.py:162`) — and Pipeline 2 uses `- 7` (`standard_matching.py:227`). **Two different magic offsets for the same document.** Replace with real provenance from Docling (§5.1).
  - Non-numeric page falls back to integer `0`, then silently links to page 6.
  - Rows silently dropped unless `confidence ∈ {high,medium,low}` — a filter that hides data loss.
- **Dashboard** — reads Postgres.

---

## 12. Cross-cutting: data contracts

**Root cause of ~6 iter_1 bugs: no schema at stage boundaries.**

Define Pydantic models as the **only** way data crosses a boundary:

```
DocumentParse      # Docling output + provenance
Standard           # one standard, one grade
GradeStandards     # {grade: [Standard]}
Lesson             # one lesson + raw text + provenance
Unit               # {grade, unit, [Lesson]}
NormalizedStandard # competency representation for retrieval
NormalizedLesson   # competency representation for retrieval
Candidate          # (lesson, standard, retrieval_rank, rerank_score)
AlignmentVerdict   # status, evidence, page, confidence, grounded
```

Combined with structured outputs (§6.1), the LLM **cannot** return a shape the next stage does not expect. The API enforces it and retries on mismatch.

**This is not a cleanup task. It eliminates an entire bug class.**

---

## 13. Cross-cutting: configuration

**Kill `os.environ` mutation.** One `Config` object (Pydantic Settings), constructed once in `main()`, **passed down as an argument**.

```python
# iter_1 — a ritual
os.environ["STD_EXTRC_OUTPUT_DIR"] = str(anchor_dir)   # global side channel
saved = process_anchor_standard(anchor)                 # reads it via getenv

# iter_2 — a function
saved = process_anchor_standard(anchor, out_dir=anchor_dir, cfg=cfg)
```

Consequences of the change:
- Stages become callable from tests, notebooks, queue workers.
- Concurrency becomes possible (no shared mutable global).
- Import order stops mattering.
- `PROJECT_ROOT / os.getenv(...)` at module scope disappears — no more `TypeError: unsupported operand` at import time when a var is unset.

**Also eliminate:** `if not some_path:` guards on `Path` objects. A `Path` is **always truthy** — iter_1's entire Step-0 validation block (`standard_extractor.py:70-80`) is unreachable dead code, and none of it checks `.exists()`. Validate with Pydantic at config construction; fail fast with a real message.

---

## 14. Cross-cutting: caching

### 14.1 Content-addressed, not existence-based

```
cache_key = hash(prompt_text + model_id + input_payload + params)
```

| Property | iter_1 | iter_2 |
|---|---|---|
| Prompt edit | **Nothing invalidates.** Stale results served forever. | Exactly the affected calls invalidate. Nothing else. |
| LLM error | `{"error": ...}` **written to disk, cached as valid forever.** Only recovery: delete the file by hand. | **Only successes are written.** Errors are never cached. |
| Partial write | Counts as complete | Atomic write; checksummed |

**~30 lines of code.** It pays for itself the first time you tune `v4_2` and do not have to re-extract the entire standards PDF.

**This directly serves the core goal:** the prompt is the product; the scaffolding's job is to let you iterate on it quickly and safely. Today the scaffolding fights that — a prompt tweak means a full re-extraction, and a failed run reports success.

### 14.2 What to cache

| Artifact | Lifetime |
|---|---|
| Docling parse | Forever (deterministic, per document hash) |
| Extraction | Until schema or prompt changes |
| Normalization | Until normalizer prompt changes |
| Embeddings | Until normalization or embedding model changes |
| Judge verdicts | Until rubric or judge model changes (keyed by `prompt_version`) |

---

## 15. Cross-cutting: concurrency and resilience

**iter_1 is serial with `time.sleep(2)` between calls. The calls are independent. A run that should take minutes takes hours.**

Worse, the sleeps are misplaced: `cluster_summary.py:395` has its `time.sleep(2)` at the **file** loop level, not the per-section LLM loop — so there is *no* pacing between the actual API calls at all. **That is where the 429s come from.**

**Replace with:**
- `asyncio` + `ainvoke`, concurrency capped by a `Semaphore`.
- **Real retry with exponential backoff** on 429/529 (`tenacity`). iter_1 has none — a single rate-limit response **silently loses that standard**. The `sleep` is a superstition, not a rate limiter.
- Explicit request timeouts.
- **Concurrency unit = the lesson** (all standards for one lesson processed together) — this is required for prefix caching to hit (§17.1). Do not reorder that loop.

**Fail loudly.** Every `except` that only logs must either re-raise or record a structured failure that surfaces in the run summary.

> iter_1's worst defect is not a crash — it is `std_aggregator.merge_anchor_standards` failing silently while `standard_extractor.py:220` prints **"🎉 Successfully merged standards"** and an entire grade's standards vanish. **Never report a failure as a success.** A wrong answer is more dangerous than no answer.

---

## 16. Evaluation — the gold set

> **This is the #1 missing piece, and the highest-ROI item in this document. Everything else is guesswork until it exists.**

### 16.1 The problem

Three prompt versions sit in `iter_1/lsn_std_alignment/prompts/`. **There is no way to know which is best.** Every future improvement — a new model, extended thinking, a rubric tweak, a retrieval change — is unmeasurable.

iter_2 makes this **worse** before it makes it better: the new architecture has *more* stages that can fail silently (retrieval recall, rerank cutoff, judge accuracy, grounding). **You cannot tune a three-stage funnel blind.**

### 16.2 Build it

- **~120–150 (lesson, standard) pairs**, labeled `full`/`partial`/`none` by a curriculum expert.
- **Deliberately over-sample hard cases**: near-misses, wrong-genre pairs, partial credit, the boundary between `partial` and `full`. A gold set of easy pairs measures nothing.
- Include **known-negative** pairs (plausible-looking but genuinely unaligned) to measure over-crediting.

### 16.3 What it measures

| Metric | Stage | Why it matters |
|---|---|---|
| **Retrieval recall@30** | Hybrid search | Is the true standard even fetched? **Caps the entire system.** |
| **Rerank recall@10** | Cross-encoder | Does it survive the cut to the judge? |
| **Judge accuracy — per class** | Judge | `full` / `partial` / `none` separately |
| **Grounding rate** | Verification | Fabricated evidence rate |
| **Cost per lesson** | All | Tracked alongside quality |

**Report per-class, never overall accuracy.** `partial` is where models are worst and where the product's value concentrates. An aggregate number will hide exactly the failure you most need to see.

### 16.4 Use it as a gate

Every prompt/model/retrieval change is scored against the gold set **before** merge. No exceptions. This is what turns "we think v4_1 is better" into a fact.

---

## 17. Cost engineering

### 17.1 Restructure the cache prefix — the single biggest win

**Nearly free to implement. Roughly 5–10× reduction in judge input cost.**

For one lesson, the judge makes N calls (one per candidate standard). Look at what is in each:

| Component | Size | Varies? |
|---|---|---|
| v4_1 rubric | ~6k tokens | **Never** |
| Lesson text | 3–8k tokens | **Same across all N calls for this lesson** |
| The standard | few hundred tokens | ← **the only thing that changes** |

iter_1 caches **the system prompt only**. So it pays full price to re-send the lesson text N times.

**Fix:** make the cached prefix `[rubric + lesson text]`, and put the **standard last** as the varying suffix.

For a lesson with 30 candidates: pay full price for the lesson **once**, get a ~90% discount on the other 29. Input tokens dominate here (output is a tiny JSON object), so this is most of the bill.

**Constraint:** the cache TTL (5 min default, 1 hour available). **Process all standards for one lesson consecutively.** iter_1 already does this — do not reorder the loop when going async (§15).

### 17.2 Batch API — 50% off, no downside

This pipeline is **entirely offline. Nothing waits on a response.** That is exactly the Message Batches API's use case: submit up to 100k requests, results within 24h (usually much faster), **50% off both input and output.**

The judge stage is embarrassingly parallel and latency-insensitive. **There is essentially no reason not to use it.** Combined with §17.1, this is a large multiple off the current bill.

### 17.3 Model tiering

iter_1 is already half-doing this (cheap model for TOC/summaries, stronger model for the judge). Push further:

- **Normalization → OpenAI small model** (Stage 1 already uses `gpt-4.1-mini` via `OPENAI_MODEL`). Mechanical distillation, cached forever.
- **Retrieval → free.** Local embeddings + local cross-encoder. **This is the big structural saving vs. iter_1**, which spends an LLM call per (lesson, standard-batch) just to filter.
- **Judge → stronger OpenAI model, cascade to frontier** on hard cases only (§10.4).

> **Check what iter_1's Pipeline 1 actually points at.** Older notes may still mention other-provider model env vars — Stage 1 in this repo is OpenAI-only (`OPENAI_API_KEY` / `OPENAI_MODEL`).

### 17.4 Shrink the lesson before it hits the API

The normalizer (§7.4) strips logistics. Halving lesson tokens multiplies across every judge call for that lesson. Free accuracy-neutral saving.

### 17.5 Right-size the rasterization

Where images are still used: **150 DPI, not 200.** At 200 DPI a Letter page is ~2200×1700px which the API downscales anyway (~1568px long edge). Rendering, encoding, and uploading discarded pixels. A/B against extraction accuracy — free if quality holds.

### 17.6 Cost priority order

| # | Change | Payoff | Quality risk |
|---|---|---|---|
| 1 | Cache prefix = `[rubric + lesson]` | **Large** | None |
| 2 | Batch API for the judge | **50%** | None |
| 3 | Local retrieval replaces LLM filter | Large | Managed via §7 + §16 |
| 4 | OpenAI small model for normalization | Moderate | None |
| 5 | Cascade | Best accuracy/$ | Improves quality |

**Items 1, 2, 4 are pure win — cheaper with no quality downside. Ship them first.**

---

## 18. Repository layout

```
iter_2/
├── config.py              # ONE Pydantic Settings object, passed everywhere
├── schemas.py             # Pydantic models = the contracts between stages
├── llm.py                 # ONE client: structured output, retry, async, cache
├── cache.py               # content-addressed: hash(prompt + model + input)
├── db/
│   ├── models.py          # SQLAlchemy / Postgres + pgvector
│   └── migrations/
├── stages/
│   ├── parse.py           # (pdf, cfg) -> DocumentParse          [Docling]
│   ├── extract_standards.py  # (DocumentParse, cfg) -> GradeStandards
│   ├── extract_lessons.py    # (DocumentParse, cfg) -> Unit
│   ├── normalize.py       # (Standard|Lesson, cfg) -> Normalized*  [OpenAI]
│   ├── index.py           # (Normalized*, cfg) -> writes KB        [pgvector+BM25]
│   ├── retrieve.py        # (Lesson, cfg) -> [Candidate]           [hybrid+RRF]
│   ├── rerank.py          # ([Candidate], cfg) -> [Candidate]      [cross-encoder]
│   ├── judge.py           # (Lesson, Standard, cfg) -> AlignmentVerdict
│   ├── verify.py          # (AlignmentVerdict, Lesson) -> grounded?
│   └── report.py          # (verdicts, cfg) -> CSV / dashboard
├── prompts/
│   ├── v4_1_alignment.md          # PORTED FROM iter_1 — the crown jewel
│   ├── normalize_standard.md
│   └── normalize_lesson.md
├── eval/
│   ├── gold_set.jsonl     # ~120 expert-labeled pairs
│   ├── run_eval.py        # recall@K, per-class accuracy, grounding rate
│   └── reports/
├── main.py                # composes stages; no logic of its own
└── tests/
```

**Every `stages/*.py` module exposes pure functions.** Artifacts in, artifacts out, `cfg` as an argument. No env mutation. No import-order dependency. No hidden disk reads.

**Deliberately absent:** a workflow engine (Airflow/Prefect/Dagster). Five stages and one input document does not justify it. Pure functions + a content-addressed cache gets ~90% of the benefit at ~5% of the cost. Revisit when there are many documents and real scheduling needs.

---

## 19. Migration plan

Sequenced so each phase is independently shippable and de-risks the next.

### Phase 0 — Stop the bleeding
Applies to `iter_1` directly; buys correctness while iter_2 is built.

1. **Silent merge failure** (`std_aggregator.py` / `standard_extractor.py:220`) — never report failure as success.
2. **Page off-by-one** (`simple_page_extrc.py:106`) — the last page is currently lost.
3. **Hardcoded grade `K`** (`simple_page_extrc.py:138`).
4. **`load_json_from_path` returning `None`** — it never raises, **no caller checks**, and this is the root of the `NoneType` crashes that look like data problems but are missing files. (`curriculum_extractor.py` logs *"Successfully loaded standards JSON"* when the file is absent.)
5. Fix `client_code/main.py`: `json_repair.loads` (currently `json_repair(...)` — a module called as a function, so the repair path **can only crash**); read the API key from env; import shared helpers instead of re-pasting them.

### Phase 1 — Foundation
6. **`schemas.py` + structured outputs.** Kills the largest bug class. Unblocks everything.
7. **`config.py`, passed as arguments.** Kills env mutation; makes stages testable.
8. **`cache.py`, content-addressed.** Makes prompt iteration cheap — the thing that matters most.
9. **Evidence grounding check.** Zero tokens, catches fabrication, does not need the gold set.

### Phase 2 — Measurement (parallel with Phase 1)
10. **GOLD SET — ~120 expert-labeled pairs.** *Blocking dependency for every tuning decision below.* Start the human labeling **now**; it has the longest lead time and nothing else can be validated without it.
11. `eval/run_eval.py` — recall@K, per-class accuracy, grounding rate.
12. **Baseline iter_1 against it.** Establishes the bar iter_2 must beat, and finally answers whether `v4_1` beats `v4`.

### Phase 3 — Cost (ships anytime after Phase 1)
13. Cache prefix = `[rubric + lesson]`.
14. Batch API for the judge.
15. OpenAI small model for normalization; verify Pipeline 1 is not on judge-tier pricing.
16. Async + retry/backoff.

### Phase 4 — The new pipeline
17. **Docling parsing** + lesson-boundary fallback chain.
18. **Pedagogical normalization** (§7) — the make-or-break stage.
19. **pgvector + BM25 + RRF**; **cross-encoder rerank**.
20. **Measure retrieval recall against the gold set.** ⚠️ **Gate:** if recall < iter_1's LLM filter, the normalization step is inadequate — fix it before proceeding. Do not ship a regression behind a better-looking diagram.
21. Extended thinking on the judge; validate.
22. Cascade + self-consistency on hard cases.

### Phase 5 — The real test
23. **Point it at a second publisher's document.** This is what proves the rebuild worked. Everything in Phase 4 exists to make this possible; doing it before Phase 4 would be painful.

---

## 20. Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **Retrieval recall regresses vs. iter_1's LLM filter** (vocabulary mismatch, §7.1) | **Critical** — silent, permanent false negatives; the system's accuracy ceiling | Pedagogical normalization (§7); generous top-30; measure recall@K as a **gate** (Phase 4 step 20) |
| 2 | **Gold set slips** | **Critical** — every tuning decision below it is blind | Start labeling in Phase 2, in parallel. Longest lead time in the plan. |
| 3 | Docling parses the standards tables poorly | High | PyMuPDF fallback path; Azure DI escape hatch (future); validate table structure against known standards counts |
| 4 | v4_1 rubric underperforms on a non-CCSS framework | Medium | The rubric's **spine** is framework-neutral; the **overlay** is CCSS-ELA-specific. Budget for a per-framework overlay. |
| 5 | Cross-encoder is a poor fit for pedagogical relevance | Medium | It is trained for general relevance, not "does this teach that." Normalization (§7) is what makes it work. Measure; consider fine-tuning on the gold set. |
| 6 | Prefix cache misses due to loop reordering under async | Medium | Concurrency unit = the lesson. Assert cache-hit rate in telemetry. |
| 7 | Second publisher's document breaks lesson extraction anyway | Medium | The fallback chain (§5.3) is the mitigation; Phase 5 is the test. Expect at least one iteration. |
| 8 | Scope creep into a workflow engine / Qdrant / multi-tenant | Low | Explicitly out of scope (§3.2, §8.1, §18). Revisit on evidence, not on aesthetics. |

---

## 21. Open decisions

| # | Decision | Owner | Needed by |
|---|---|---|---|
| 1 | Who labels the gold set, and what is their availability? | Product / SME | **Immediately** — longest lead time |
| 2 | Embedding model — general (`text-embedding-3`, `bge`) vs. domain-tuned? | Eng | Phase 4 |
| 3 | Cross-encoder — Cohere Rerank (hosted) vs. local `bge-reranker`? Recommend local at this scale. | Eng | Phase 4 |
| 4 | Is `client_code/` still a client deliverable, or can it be retired? | Product | Phase 0 |
| 5 | Target frameworks beyond CCSS ELA? Drives the overlay budget (risk #4). | Product | Phase 4 |
| 6 | Where does this run — laptop, VM, cloud? Drives Docling/local-model resourcing. | Eng | Phase 4 |
| 7 | Is the CSV still the deliverable, or does the dashboard replace it? | Product | Phase 4 |

---

## Appendix A — The one-line summary

> **iter_1's brain is excellent and its skeleton is a prototype. iter_2 keeps the brain — the v4_1 rubric and the coarse-to-fine funnel — and rebuilds everything around it so the rubric can be iterated on quickly, safely, and measurably.**

Three things determine whether iter_2 is actually better than iter_1:

1. **Pedagogical normalization before embedding** (§7) — without it, the sophisticated retrieval stack has *worse* recall than the naive LLM filter it replaces, and no error will tell you.
2. **The gold set** (§16) — without it, nothing above is verifiable, and "better architecture" is an aesthetic claim.
3. **Never reporting failure as success** (§15) — iter_1's defining defect. A wrong answer is more dangerous than no answer.

Everything else in this document is engineering. Those three are the product.

---

## Appendix B — iter_1 defect index

Retained for migration reference. Every item below must be verified absent in iter_2.

| Defect | Location | § |
|---|---|---|
| Failed merge logged as "🎉 Successfully merged standards" | `std_aggregator.py:232` / `standard_extractor.py:220` | §2.2B, §15 |
| `NameError` on `grade_standards_path` masks the real upstream error | `standard_extractor.py:246` | §2.2B |
| Page off-by-one — last page lost, phantom page 1 | `simple_page_extrc.py:106` | §5.4 |
| Grade hardcoded to `K` | `simple_page_extrc.py:138` | §5.4 |
| Lesson split on magic string `TIMING GOAL` | `simple_page_extrc.py:28` | §5.3 |
| `TIMING GOAL` vs `TIMING GOAL:` mismatch | `simple_page_extrc.py:28` vs `markdown_to_json.py:89` | §5.4 |
| `get_native_toc_page` returns first outline **destination**, not the TOC page | `toc_extraction.py:28` (both modules) | §5.3 |
| TOC regex matches any line ending in digits | `lesson_extraction/toc_extraction.py:92` | §3.3 |
| `_split_banded_grade` returns endpoints — **grade 7 lost** from `"6-8"`; `"K-5"` → `[]` | `indiv_grade_std_extractor.py:162` | §6.2 |
| `os.environ` mutated mid-loop as the inter-module channel | `standard_extractor.py:144`; `finally:229` restores the **wrong** value | §2.2C, §13 |
| Step-0 validation unreachable (`Path` always truthy); wrong env var names in messages | `standard_extractor.py:70-80` | §13 |
| `{"error": ...}` cached to disk as a valid result, forever | `toc_extraction.py:106`, `anchor_standard_extraction.py:71` | §14.1 |
| `load_json_from_path` returns `None`, never raises, **no caller checks** | `utils/load_json.py` (all 3 copies) | §19 Phase 0 |
| "Successfully loaded standards JSON" logged when the file is absent | `curriculum_extractor.py:40` | §19 Phase 0 |
| `time.sleep(2)` at the **file** loop level — no pacing between actual API calls | `cluster_summary.py:395` | §15 |
| No retry/backoff on 429/529 — a rate limit **silently loses that standard** | `llm.py` | §15 |
| Full LLM response logged at INFO on every call | `llm.py:81,146`; `page_extraction_vllm.py:205` | — |
| Prompt/payload schema mismatch — `anchor_standard` dropped, prompt still asks for it | `cluster_summary.py` vs `prompt_cluster_summary.md:3-14` | §12 |
| Rows silently dropped without valid `confidence` → **empty CSV, no error**, on older prompts | `json_to_csv.py:143` | §10.1, §11.2 |
| `seen_criteria` stripped-vs-unstripped → duplicate parent rows | `json_to_csv.py:84` vs `:97` | §11.2 |
| Magic page offsets `+6` and `-7` for the same document | `json_to_csv.py:162`; `standard_matching.py:227` | §11.2 |
| Non-numeric page → integer `0` → silently links to page 6 | `json_to_csv.py:159-160` | §11.2 |
| `json_repair(...)` — module called as a function; repair path **can only crash** | `client_code/main.py:185` | §3.3, §19 |
| API key placeholder in source | `client_code/main.py:9` | §19 |
| Stale / wrong model IDs in older notes | `.env` / Readmes / `normalize/llm.py` | Stage 1 uses OpenAI only (`OPENAI_MODEL`) |
| RAG experiment broken end-to-end (writes `*_keywords.json`, reads `unit01_lessons.json`) | `keyword_generation.py:144` vs `keyword_rag.py:28` | §3.3 |
