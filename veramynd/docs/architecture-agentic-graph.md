# Veramynd — Agentic Graph-Grounded Alignment Architecture

## A second, independent track for Stages 2–7

**Status:** Proposed — parallel alternative to `architecture.md`, not a replacement
**Owner:** Hamyal
**Last updated:** 2026-07-25

---

## 0. What this document is

[`architecture.md`](architecture.md) (call it **iter_2**) designs Stages 2–7 as a
classic coarse-to-fine pipeline: extract → normalize → embed into a hybrid
vector+BM25 knowledge base → retrieve top-30 → cross-encoder rerank to ~10 →
LLM judge each pair → verify → store in Postgres.

This document — call it **iter_3** — is a genuinely different mechanism for
the same problem, so the two tracks can be built and measured independently
against the same gold set before committing to one. The core bet: **this
project's standards corpus is small, stable, and already a tree** (a few
hundred standards per grade; low thousands across all of K–12 ELA). That's
precisely the regime where 2026 evidence says retrieval infrastructure stops
paying for itself — see §1 and Sources at the end.

Both tracks solve the same product problem defined in `architecture.md` §1
(not repeated here) and can share the same Stage 1 output (§2). What changes
starting in Stage 2 is the *mechanism*: no vector database, no embeddings, no
reranker, and no fixed retrieve→rerank→judge→verify pipeline — one agent, per
lesson, with tools, reasoning directly over a standards graph held in context.

### 0.1 What iter_2 got right — carried forward unchanged

"Totally different" should mean a different *mechanism*, not throwing away
ideas that are already correct. These move over as-is:

| Asset | Why it stays |
|---|---|
| The v4_1-style alignment rubric (clause decomposition, strand/genre gating, qualifier handling, student-quote evidence gate) | This is the actual product. It's SME-derived and framework-neutral at its spine. Ports directly into the new agent's system prompt. |
| Pedagogical normalization (standards-agnostic, evidence-backed) | Independently correct regardless of what reads it downstream — validated in this repo against 40 real lessons with 0 hallucinated evidence. Reuse Stage 3 as-is; see §2. |
| Content-addressed caching, "fail loud never silent," structured outputs over prompt-and-repair | These are properties of good engineering, not of any one retrieval mechanism. Keep all three. |
| The gold-set requirement | Non-negotiable in *both* tracks — see §7. Whichever architecture wins gets decided by measurement, not opinion. |
| Evidence grounding as a zero-token string-match gate | Kept — but *moved inline* into the agent's tool contract instead of being a separate downstream stage. See §5.3. |

---

## 1. The core architectural bet

> **A knowledge base you can read in full, cheaply and repeatedly via prompt
> caching, does not need to be searched.**

2026 evidence on long-context vs. RAG is task-dependent, not one-sided:
long-context wins for "tasks requiring complete reasoning across entire
documents" and "bounded, stable knowledge bases" combined with caching; RAG
wins on raw economics when most of a large corpus goes unused per query, and
open-source/weaker models benefit more from retrieval than strong closed
models do (see Sources). Our situation is squarely on the long-context side of
that line:

- **Bounded**: one grade's ELA standards ≈ 150–300 items. Even a whole K–12
  ELA framework is low thousands — not the millions-of-documents regime any
  RAG stack is actually justified for (iter_2 itself already makes this
  argument against Qdrant in favor of pgvector, §8.1 of `architecture.md` —
  this document just carries the same logic one step further).
- **Stable**: a standards framework doesn't change during a project run. It's
  exactly the "stable knowledge base" long-context research calls out as the
  case where caching turns the naive cost objection into a non-issue.
- **Already a tree**: `GradeStandards.parent_code` links (domain → big idea →
  standard → substandard) are a graph, not a bag of chunks. 2026 GraphRAG
  guidance is consistent here too: knowledge graphs earn their complexity
  specifically for taxonomically organized, hierarchical data, and production
  stacks increasingly combine structural narrowing with full-context reasoning
  rather than pure vector similarity for exactly this shape of data.

Separately, 2026 guidance on agentic document processing draws a sharp line
between *sophisticated extraction* (one prompt + schema, however well
engineered) and *agentic* (planning, iterative reasoning, in-loop validation,
self-correction). iter_2's Stage 6 judge — one call per (lesson, candidate
standard) pair, no ability to look anything up, no self-check before
answering — is the former. iter_3's alignment stage (§5) is the latter: one
agent per lesson, with tools, that must pass its own grounding check *before*
it can record a verdict, and can pull more context on demand instead of
hoping the reranker handed it everything relevant.

**What this eliminates:** pgvector, an embedding model, a BM25 index, RRF
fusion, a cross-encoder reranker, and Postgres as a hard Day-1 dependency.
**What this costs:** more input tokens per lesson (a whole strand of standards
in context, not a narrow reranked list) and more round-trips per lesson (tool
calls instead of one shot) — see §6 for the honest trade-off, not a sales
pitch.

---

## 2. Stage 1 — reuse, don't rebuild

Both tracks should share Stage 1. `veramynd_parser/` already does this well —
40/40 lessons on the real reference document, a real four-layer verifier, dual
PDF engines cross-checking each other. There's no "different architecture"
argument for redoing PDF parsing; the interesting divergence starts at what
happens to `TeacherGuide` / `GradeStandards` once they exist.

**Recommendation:** iter_3 should not import `veramynd_parser` as a Python
dependency (that would couple the two tracks). Instead, treat its **on-disk
JSON output** (`output/stage1/teacher_guide.json`, `output/stage1/lessons/*.json`,
`output/stage1/standards.json`) as the interface boundary — the same contract
`architecture.md` §12 already defines (`Lesson`, `GradeStandards`). iter_3
reads those files and owns nothing upstream of them. If iter_3 ever needs to
run against a document Stage 1 can't parse, that's a Stage 1 bug to fix once,
not a reason to fork the parser.

---

## 3. Architecture overview

![Pipeline overview: Stage 1 parsing and Stage 3 pedagogical normalization are reused unchanged from this repo; Stage 2 builds a standards graph with no embeddings or vector DB; Stage 4 is one alignment agent per lesson; Stage 5 writes content-addressed JSONL with Postgres as an optional later load](diagrams/agentic-graph/01-pipeline-overview.svg)

*Figure 1 — Pipeline overview. Blue stages are reused unchanged from this
repo's existing implementation; orange stages are new. Both new-build stages
(2 and 4) replace what was five separate stages (extraction, indexing,
retrieval, rerank, judge) in `architecture.md`.*

---

## 4. Stage 2 — Standards Graph Build

Replaces iter_2's Stage 4 (hybrid RAG knowledge base) entirely.

```python
def build_standards_graph(standards: GradeStandards, cfg: Config) -> StandardsGraph:
    """(GradeStandards, cfg) -> StandardsGraph. Pure function, no I/O beyond cache."""
```

- **Nodes**: every `Standard` in `GradeStandards.standards`, at every level
  (domain / big idea / standard / substandard).
- **Edges**: `parent_code` (already present, from Stage 1 — no re-derivation).
- **Enrichment**: run the *same* standard-normalization idea `architecture.md`
  §7.3 already specifies (`competency_statement`, `observable_behaviors`,
  `pedagogy_terms`) — this step is genuinely good and stays. The difference:
  the output is **attached as text on the graph node**, to be read directly
  by the agent, never embedded into a vector.
- **Grouping**: nodes are indexed by `(grade, top-level domain/strand)` so
  "give me everything in this strand for this grade" is an O(1) dict lookup,
  not a similarity search.

No embeddings are computed. No index is built beyond the in-memory (or
SQLite/JSON-backed, for persistence across runs) graph itself. This is the
single biggest infrastructure deletion versus iter_2: no pgvector extension,
no embedding model to select or version, no re-embedding step when the
normalizer prompt changes.

**Caching**: content-addressed exactly like iter_2 (`hash(prompt_version +
model + standard_code + standard_text)`), forever, per standard — same
principle, smaller surface (no embedding-model-version dimension to track).

---

## 5. Stage 4 — The Alignment Agent

Replaces iter_2's Stages 5+6+7 (retrieve, rerank, judge, verify) as four
separate pipeline stages with **one agentic loop per lesson**.

### 5.1 Why one agent instead of four stages

In iter_2, a false negative in retrieval is permanent and invisible — the
judge never even sees the standard the lesson actually teaches, and nothing
downstream can recover from that (`architecture.md` §9.1, §20 Risk #1: "the
system's accuracy ceiling"). Collapsing retrieval into the same reasoning
process as judgment removes that failure class structurally: the agent that
decides *whether* a standard is taught is the same agent that decides *which
standards to look at*, so there's no separate stage that can silently drop a
correct candidate before judgment ever runs.

### 5.2 Tool contract

```python
def list_strands(lesson: NormalizedLesson, grade: int) -> list[StrandSummary]:
    """Cheap, deterministic, free — a dict lookup keyed by (grade, domain),
    narrowed by the lesson's own normalized domain_primary/domain_secondary.
    Not a similarity search: no false-negative risk from an embedding miss."""

def get_standards_in_strand(strand_id: str, grade: int) -> list[EnrichedStandard]:
    """Returns ALL standards in that strand/grade with their normalized
    competency text -- the whole batch goes into context at once. Bounded:
    a strand within one grade is dozens of items, not thousands."""

def get_standard_detail(code: str) -> EnrichedStandard:
    """Pull one standard's full text/substandards on demand -- for when the
    agent needs more than the strand summary gave it."""

def quote_lesson(candidate_quote: str) -> QuoteCheckResult:
    """THE grounding gate, moved in-loop. Reuses this repo's proven
    resolve_verbatim_quote() logic (normalize/sanitize.py) against the raw
    Stage-1 lesson text. Returns ACCEPTED + the exact source span, or
    REJECTED. The agent cannot call record_verdict with a quote it hasn't
    gotten ACCEPTED first -- enforced by the harness, not by prompt instruction."""

def record_verdict(standard_code: str, status: Literal["full","partial","none"],
                    evidence: list[GroundedEvidence], confidence: Literal["high","medium","low"],
                    reasoning: str) -> None:
    """The agent's output for one standard. Schema-validated (structured
    outputs) exactly like iter_2's judge output -- same discipline, applied
    per tool call instead of per pipeline stage."""
```

![The alignment agent's tool-use loop: list strands, load a strand's standards into context, reason with the v4_1 rubric, optionally pull more standard detail, check any candidate quote against the verbatim grounding gate before it can be recorded, and record a schema-validated verdict, looping until the strand is exhausted](diagrams/agentic-graph/02-agent-loop.svg)

*Figure 2 — The per-lesson agentic loop. The grounding gate (red) sits
**before** `record_verdict`, not after it — a rejected quote sends the agent
back to reason again in the same turn, rather than shipping a verdict that a
separate downstream stage has to catch and flag later.*

### 5.3 Grounding moves from "verify after" to "gate before"

iter_2's grounding check (`architecture.md` §11.1) is free and zero-token but
runs **after** the judge has already committed to a verdict — an ungrounded
verdict has to be flagged and escalated after the fact. Here, `quote_lesson`
rejects a fabricated quote *before* `record_verdict` can be called with it, in
the same reasoning turn. The agent sees the rejection and either finds a real
quote or downgrades its own verdict — self-correction inside the loop instead
of a downstream catch. This is the same principle iter_2 already committed to
("evidence must be verbatim, checked") pushed one step earlier in the process.

### 5.4 The rubric, extended thinking, and escalation

- **Rubric**: port `std_alignment_prompt_v4_1.md` into the agent's system
  prompt unchanged. It's the product; nothing about tool-use changes what
  "partial vs. full" means.
- **Extended thinking**: on by default for the agent's reasoning between tool
  calls, same rationale as `architecture.md` §10.3 — this is explicitly a
  multi-step decomposition task.
- **Escalation, simplified**: iter_2's cascade (§10.4) and self-consistency
  voting (§10.5) exist to catch cases a single non-agentic call gets wrong
  with no way to check itself. Because this agent *already* self-verifies
  in-loop (quote gate, on-demand detail lookups), the residual uncertainty is
  smaller. Recommend a lighter mechanism: **the agent self-reports
  `confidence: low`** on `record_verdict` when it is genuinely unsure (not a
  hard-filtered field like iter_1's mistake, §10.5 of `architecture.md` — a
  *routing* signal only); low-confidence verdicts get one automatic re-run
  with a stronger model, and only a persistent disagreement between the two
  runs escalates to human review. Measure whether this actually matches
  iter_2's 3x-vote disagreement signal for cost/accuracy before committing
  further — see §7.

### 5.5 Output

No retrieval-rank or rerank-score columns exist in this design, so storage
simplifies. Recommend the same pattern this repo's Stage 1 and Stage 3
already use successfully: **content-addressed JSONL per lesson**, one line
per `(lesson_id, standard_code)` verdict, atomic-write. At this corpus's
actual scale (tens of lessons × low thousands of standards, and in practice
far fewer since the agent only investigates strands it narrows to) this is
tens of thousands of records at the outside — well within "a directory of
JSON files is a perfectly good database" territory.

**Postgres becomes optional**, not a Day-1 requirement: a later `load-jsonl`
step for the dashboard, not something the MVP needs to stand up before it can
produce a single verdict. CSV export reads directly from the JSONL, with no
join against separate retrieval-diagnostics tables (there are none).

---

## 6. Cost model — an honest trade-off, not a pitch

| | iter_2 (hybrid RAG) | iter_3 (agentic graph) |
|---|---|---|
| Embeddings | Small, ongoing (re-embed on normalizer change) | **Zero** |
| Reranker | Local model, free to run, but infra to maintain | **Zero** |
| Per-lesson judge input tokens | Narrow: reranked ~8–12 candidates (~1–2K tokens) | Wider: a whole strand in context (~5–15K tokens) |
| Cache reuse pattern | Lesson text cached *within* that lesson's N candidate calls only | Standards-graph text cached *once per grade*, reused across **every** lesson in that grade |
| API round-trips per lesson | Fixed, ~N candidate calls | Variable, tool-call loop (higher latency risk — see §8 Risk #3) |
| DB infra to stand up before first result | Postgres + pgvector, Day 1 | None — JSONL, Day 1; Postgres later, optional |

Net: iter_3 trades a **narrower but uncached-across-lessons** prompt for a
**wider but grade-wide-cached** one, and trades retrieval infrastructure cost
for more tool round-trips. Whether that nets out cheaper depends on how many
lessons share a grade (more lessons = more cache reuse = better economics for
iter_3) and how tight the strand narrowing turns out to be in practice. **Do
not assume iter_3 is cheaper — measure it**, same rule as everything else.

---

## 7. Evaluation — shared, not duplicated

Non-negotiable in both tracks, and it should be **the same gold set**
(`architecture.md` §16): ~120–150 expert-labeled (lesson, standard) pairs,
deliberately oversampled on hard/boundary cases. Building two separate gold
sets would be pure waste and would make the two architectures literally
incomparable.

iter_3-specific metrics, analogous to iter_2's but for a different mechanism:

| Metric | iter_2 equivalent | What it measures here |
|---|---|---|
| Strand-narrowing recall | Retrieval recall@30 | Did `list_strands` surface the strand containing the true standard? Caps the whole system exactly like retrieval recall does in iter_2. |
| In-strand judge accuracy, per class | Judge accuracy, per class | Same discipline: report `full`/`partial`/`none` separately, never an aggregate. |
| Grounding rejection rate | Grounding rate | How often `quote_lesson` rejects the agent's first attempt — a live signal of how well the in-loop self-correction is working, not available at all in iter_2's after-the-fact check. |
| Tool-calls and cost per lesson | Cost per lesson | Track both — this is the number that answers §6's open question with data. |

**Gate**: before either track is treated as "the" architecture, both must be
scored against the same gold set and the results compared head-to-head. The
winner is whichever one the numbers say is winning — including the option
that neither fully wins and the real answer is a hybrid (e.g., iter_3's
graph-narrowing feeding iter_2's reranker, or iter_2's vector recall as a
fallback if iter_3's strand-narrowing misses — 2026 production guidance
explicitly notes most real stacks end up combining structural and vector
retrieval rather than picking one absolutely).

---

## 8. Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Corpus grows beyond "fits in context" — the whole bet in §1 depends on a bounded, stable standards set | High if the project expands to many simultaneous state frameworks at once | Explicit revisit trigger: if any single grade's candidate strand exceeds ~2–3K standards, or the project needs many frameworks live concurrently, bring back a first-pass vector filter ahead of the agent — this is exactly the "80% vector / 15% graph / 5% agentic" blend 2026 production guidance converges on, not a fork in the road. |
| 2 | Agent tool-use loops are harder to test deterministically than a fixed pipeline | Medium | Strict tool schemas (structured outputs on every tool return, same discipline as iter_2's judge output); the gold-set gate (§7) catches regressions the same way regardless of mechanism; log every tool call for replay/debugging. |
| 3 | Variable round-trips per lesson → latency and cost variance a fixed pipeline doesn't have | Medium | Cap max tool-call iterations per lesson; a lesson that hits the cap routes to human review rather than looping indefinitely — "fail loud," never silently truncate. |
| 4 | Two parallel architectures split team attention and risk becoming two unmeasured guesses instead of one measured answer | Medium | §7's shared-gold-set gate is mandatory, not optional. Schedule an explicit head-to-head checkpoint once both tracks clear the gold set once each. |
| 5 | Standards-graph-as-cached-prefix assumes grade-level standards text is stable within a run; if the normalizer prompt changes mid-project the whole grade's cache invalidates at once | Low | Same content-addressing discipline as iter_2 (§14.1 of `architecture.md`) — a prompt-version change invalidates exactly the affected cache entries, nothing silently stale. |

---

## 9. Suggested repo layout

```
veramynd_agentic/           # new package, depends on Stage 1's JSON output only
├── config.py                # one settings object, same principle as iter_2
├── graph.py                 # GradeStandards JSON -> StandardsGraph (§4)
├── tools.py                 # the four tool implementations (§5.2)
├── agent.py                 # the per-lesson agentic loop
├── prompts/
│   ├── alignment_rubric.md          # ported from iter_2 unchanged (§0.1)
│   └── normalize_standard.md        # ported from iter_2 unchanged (§4)
├── cache.py                 # content-addressed, same as iter_2's cache.py
├── output.py                # JSONL writer + optional Postgres loader (§5.5)
├── eval/
│   ├── gold_set.jsonl               # SHARED with iter_2 -- do not fork
│   └── run_eval.py                  # strand recall, per-class accuracy, grounding rejection rate
└── tests/
```

## 10. Migration / build plan

1. **Point at existing Stage 1 output.** No new parsing work — read
   `output/stage1/*.json` from this repo directly. Confirms the interface
   boundary (§2) actually holds before building anything new on top of it.
2. **`graph.py`** — load `GradeStandards` JSON into a `StandardsGraph`. Small,
   testable in isolation, no LLM calls.
3. **Port the two prompts** (rubric, standard-normalizer) from iter_2's
   `prompts/` — start from what's already validated, tune from there.
4. **`tools.py` + `agent.py`** — the real new-build item. Start with
   `quote_lesson` (it's pure logic, reuse this repo's `resolve_verbatim_quote`
   almost verbatim) before the agent loop itself, so grounding is provable
   before it's wired into anything that spends tokens.
5. **Gold set work starts in parallel, immediately** — longest lead time in
   either track, exactly as `architecture.md` §19 Phase 2 already argues.
   Shared with iter_2; do not wait for iter_3 to be "ready."
6. **Head-to-head checkpoint** (§7) once both tracks clear the gold set once.

---

## Sources

- [RAG vs Long-Context LLMs: A Comprehensive Comparison](https://medium.com/@rosgluk/rag-vs-long-context-llms-a-comprehensive-comparison-9b30594c445e)
- [RAG vs Large Context Window: Real Trade-offs for AI Apps (Redis)](https://redis.io/blog/rag-vs-large-context-window-ai-apps/)
- [Beyond RAG vs. Long-Context: Learning Distraction-Aware Retrieval for Efficient Knowledge Grounding](https://arxiv.org/pdf/2509.21865)
- [RAG vs long context: what the 2026 data shows (Wire)](https://usewire.io/blog/long-context-vs-rag-what-the-data-shows/)
- [Long-Context Models vs. RAG: When the 1M-Token Window Is the Wrong Tool](https://tianpan.co/blog/2026-04-09-long-context-vs-rag-production-decision-framework)
- [Long Context vs. RAG for LLMs: An Evaluation and Revisits (arXiv)](https://arxiv.org/pdf/2501.01880)
- [What is Agentic Document Extraction? (The 2026 Guide)](https://parseur.com/blog/agentic-document-extraction)
- [LandingAI's DPT-2 in 2026: Why Agentic Document Extraction Finally Makes Sense](https://pub.towardsai.net/landingais-dpt-2-in-2026-why-agentic-document-extraction-finally-makes-sense-629a5115b80f)
- [Graph RAG vs. Vector RAG: Choosing the Right Architecture for Enterprise Use Cases](https://medium.com/@ajaysrinivasan87/graph-rag-vs-vector-rag-choosing-the-right-architecture-for-enterprise-use-cases-f3f6205f959f)
- [Knowledge Graph vs RAG: When Each One Wins (2026)](https://atlan.com/know/knowledge-graphs-vs-rag-for-ai/)
- [AI-Powered Curriculum Mapping Tools Reshape District Planning](https://www.aicerts.ai/news/ai-powered-curriculum-mapping-tools-reshape-district-planning/)
- [From Manual Chaos to Smart Alignment: How AI Is Rewriting U.S. Education Standards](https://stayrelevant.globant.com/en/technology/edtech/from-manual-chaos-to-smart-alignment-how-ai-is-rewriting-u-s-education-standards/)
