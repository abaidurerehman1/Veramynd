# Veramynd

**Curriculum standards alignment engine.** Given a teacher-guide PDF and a standards
spreadsheet, Veramynd determines which academic standards each lesson in the guide
actually teaches — with auditable, page-referenced evidence pulled straight from the
source document.

Curriculum alignment is normally done by hand by a curriculum specialist: expensive,
slow, and inconsistent between raters. The judgment itself is genuinely subtle — a
standard might say *"ask and answer questions about key details,"* and deciding
whether a lesson meets that standard **fully** or only **partially** requires reading
the standard's clauses precisely and finding real evidence in the lesson that the
student actually performed the act. Veramynd's goal is to apply one rubric
identically, at scale, with a paper trail.

## Project status (honest)

Working **end-to-end through judge + report** on the Batch-1 gold set:
**EL Education G1M2** + **Georgia Grade 1 ELA**. Design stays
**publisher- and framework-agnostic** via **shared structural patterns**
(Lesson / Day / Session / Shared Story / Start-Up, acts + meaning) — **not**
a per-publisher `if Success for All / elif Publisher B` tree.

| Proof point | Status |
|---|---|
| Batch-1 EL → normalize → retrieve (gold R@25) | **Locked** |
| Batch-1 gold-4 judge vs SME (`align_judge.v1.1`) | **Measured** — 18/19 exact (94.7%) on unique pairs in top 25 |
| Second publisher Stage-1 GO (`21111_RBtL_SSManual_L1.pdf`, Reading Roots Shared Story Level 1) | **Done** — 14 lessons in `output/stage1_ssmanual/` |
| Second publisher normalize → retrieve → judge | **Not locked yet** |
| Any PDF / any publisher / any grade with zero pattern work | **Not claimed** — new heading languages may need a small generic-pattern add |

**Batch-1 retrieve (live, enterprise defaults)** — 4 gold lessons
(`G1M2U1L1`, `U1L3`, `U1L6`, `U3L5`), **20** FULL+PARTIAL positives
(`docs/_ga_g1_module2_goldset.md`; gold is **eval-only**, never used in ranking):

| Metric | Result | Role |
|---|---|---|
| **Recall@25** | **100% (20/20)** | Protected QA bar (do not tune retrieve to hide normalize/parser regressions) |
| **Recall@20** | **85% (17/20)** | Product cut → judge shortlist |
| **Recall@50** | **100% (20/20)** | SME / diagnostic shortlist |
| Recall@30 | 100% (20/20) | — |
| Recall@10 | 40% (8/20) | Head precision still open |

Residual @20 (all still ≤25): `1.P.EICC.3.e`, `1.P.EICC.3.f`, `1.T.RA.2.a`
(U1L6). Three gold **none** rows sit outside top 25 and do **not** count against
R@25.

**Batch-1 judge (gold-4, `prompts/align_judge_v1.md`)** — unique
`(lesson, standard)` pairs; FULL wins if both FULL and PARTIAL exist; 3-class
exact only on pairs in the top-25 shortlist (19 judged / 22 unique gold pairs):

| Metric | Result |
|---|---|
| **3-class exact** | **18/19 (94.7%)** |
| Binary recall (FULL+PARTIAL vs NONE) | 94.4% |
| Binary precision | 100% (0 false positives) |
| Leftover miss | U1L6 `1.T.T.1.c` — gold **partial**, judge **none** |

Per lesson (judged pairs): L1 7/7, L3 4/4, L6 6/7, U3L5 1/1. Live judge run:
Sonnet batch + Opus escalate. Broader multi-publisher / all-40-lesson judge
scale is **not** claimed. Agentic/graph track is design-only.

**Through-retrieve design (current):**
- Stage-1 routes **EL-like** vs **unknown/generic**; steps carry **page** +
  `kind: procedure | scaffold`
- Generic boundaries recognize shared curriculum headings (incl. **Shared Story N**,
  **Start-Up Lesson**); letter-spacing repair for display headings (`You will need`)
- Lesson normalize **`normalize_ela.v2.3`** + `repair-normalized` sanitizers
  restore under-extracted literacy acts from Stage-1 — publisher-safe cues,
  not gold hard-codes
- Gold retrieve query mode: **`multi_normalize_focused`** (arms from normalize,
  not lesson chunks)
- Funnel: competency bridges → per-query dense+BM25 RRF → merge (`top_k_sum`) →
  local CE → shortlist fusion; rescue slots **off**. Artifacts:
  `output/retrieve_gold4/`, eval `python -m veramynd_parser.scripts.eval_r20`

| Stage | Status | Location |
|---|---|---|
| **Parse & verify (PDF)** — EL path locked; generic Stage-1 GO on Shared Story L1 manual; per-step page + scaffold; GO/REVIEW/BLOCK | **Implemented (EL locked; 2nd publisher Stage-1 proven)** | [`veramynd_parser/`](veramynd_parser/) |
| **Parse & verify (standards)** — column detection, GA/generic adapters, hierarchy, GO/REVIEW/BLOCK | **Implemented (GA validated)** | [`standards/`](veramynd_parser/veramynd_parser/standards/) |
| **Pedagogical normalize (lessons)** — `normalize_ela.v2.3` + sanitize / `repair-normalized` | **Implemented** (Batch-1 locked; SSManual not locked) | [`normalize/`](veramynd_parser/veramynd_parser/normalize/) |
| **Standards normalize** — retrieval-ready leaves (`embed_text`) | **Implemented** | [`normalize/standard.py`](veramynd_parser/veramynd_parser/normalize/standard.py) |
| **Chunk** — hierarchical lesson / instructional / evidence-pointer bundles | **Implemented** (optional for gold R@25; normalize drives queries) | [`chunk/`](veramynd_parser/veramynd_parser/chunk/) |
| **Embed → Qdrant** — leaf-only standards + rich retrieval text | **Implemented** | [`embed/`](veramynd_parser/veramynd_parser/embed/) |
| **Hybrid retrieve + rerank** — `multi_normalize_focused` competency funnel | **Implemented (Batch-1 R@25/R@50 met)** | [`retrieve/`](veramynd_parser/veramynd_parser/retrieve/) |
| **Alignment judge + grounding** — `align_judge.v1.1`; `(scaffold)` = supplemental; ungrounded quotes rejected | **Implemented** (gold-4 measured) | [`judge/`](veramynd_parser/veramynd_parser/judge/), [`prompts/align_judge_v1.md`](veramynd_parser/veramynd_parser/prompts/align_judge_v1.md) |
| **Report** — CSV + HTML; gold-4 + client (no retrieve scores) | **Implemented** | [`report/`](veramynd_parser/veramynd_parser/report/), `output/reports/` |
| **Gold-set metrics** — leaf recall @k + judge exact vs SME | **Retrieve locked; judge 94.7% on gold-4** | gold: [`docs/_ga_g1_module2_goldset.md`](docs/_ga_g1_module2_goldset.md) |
| **Agentic + standards-graph track** | **Design only** | [`docs/architecture-agentic-graph.md`](docs/architecture-agentic-graph.md) |

## How it works

**1. Parse (PDF).** Structure detection routes **EL-like** guides to the EL path
and **unknown** layouts to a generic divider (pattern-based lesson starts —
Lesson/Day/Session/Shared Story/Start-Up — not publisher name switches). Steps
keep **page provenance** and `procedure` vs in-block **scaffold** (ELL/UDL/support).
Docling is layout-only; optional GPT-4.1-mini classifies ambiguous section roles
only. Same upload shape → re-run without code changes; brand-new heading language
may need one generic pattern extension.

**2. Parse (standards).** Column-role detection → GA or generic adapter →
hierarchy → `GradeStandards`. Optional LLM assists **structure only** — never
invents codes/text/parents.

**3. Verify.** Teacher-guide and standards each emit **GO / REVIEW / BLOCK**.
Only **GO** is production-trusted unless explicitly overridden.

**4. Normalize → (chunk) → embed.** Lessons become standards-agnostic
`NormalizedLesson` records; standards become leaf `embed_text`. Sanitizers
re-apply literacy signals from Stage-1 after LLM normalize. Standards leaves
embed into Qdrant (`text-embedding-3-large`).

**5. Retrieve → judge → report.** Enterprise path builds focused query arms from
**normalize** (objective, skills, actions, evidence, competency bridges) →
dense+BM25 → RRF → CE → fused shortlist (`judge_shortlist_k=50`, product cut
**top-20**, protected bar **Recall@25**). Judge (`align_judge.v1.1`) scores
`full` / `partial` / `none` from **student acts** in Stage-1 steps
(`(scaffold)` never yields `full`); ungrounded quotes become `none`. CSV/HTML
reports export the audit trail (`output/reports/gold4_alignments.csv`;
client-facing CSVs under `output/reports/client/`).

## Design principles

- **Fail loud, never silently.** Structural problems block the pipeline.
- **Pattern-based publishers, not name switches.** Extend shared heading /
  section signals — do not grow `if publisher == "…" / elif …` trees.
- **Content-addressed caching** for Docling parses and LLM normalizations.
- **Evidence is mandatory and checked** — fabricated quotes are rejected.
- **Two vocabularies, kept apart** (publisher claims vs target framework codes).
- **Gold is eval-only** — never enters query generation, merge, CE, or fusion.
- **Do not tune retrieve to hide normalize/parser regressions** — protect R@25.
- **Normalize once per input version** — artifact registry + content-addressed
  cache; same upload → reuse; `--force` only when intentionally refreshing.

## Quick start

```bash
cd veramynd_parser
pip install -e '.[test]'          # Python >= 3.11

# Parse + verify (expects 40 lessons for the sample guide)
veramynd-parser verify "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" --expect 40

# Full Stage-1 export (PDF + standards; pass --framework for trusted standards GO)
veramynd-parser export "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" \
  --out output/stage1 --expect 40 \
  --standards "../data/samples/Grade 1 GA ELA Standards.xlsx" \
  --framework "GA ELA"

# Standards-only parse + GO/REVIEW/BLOCK gate
veramynd-parser stds "../data/samples/Grade 1 GA ELA Standards.xlsx" \
  --framework "GA ELA" --json output/stage1/standards.json

pytest
# Protected recall bar (gold4 artifacts):
python -m veramynd_parser.scripts.eval_r20          # includes R@25
python -m veramynd_parser.scripts.phase8_regression # GA GO + R@25 gate
```

Downstream (needs OpenAI key; extras as noted):

```bash
pip install -e '.[normalize,embed,retrieve,judge]'
cp .env.example .env               # set OPENAI_API_KEY — never commit .env

veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize
veramynd-parser normalize-standards output/stage1/standards.json --out output/normalize_standards
veramynd-parser chunk-lessons output/stage1/lessons --normalize-dir output/normalize --out output/chunks
veramynd-parser embed-chunks output/chunks --out output/embeddings --recreate
# Leaf-only + rich text (defaults); recreate after switching modes
veramynd-parser embed-standards output/normalize_standards --out output/embeddings --recreate

# Single-query hybrid (CLI) or enterprise multi-query batch:
veramynd-parser retrieve-standards --chunk-file output/chunks/by_lesson/G1M2U1L3.json --out output/retrieve/G1M2U1L3.json

# After normalize changes: re-apply sanitizers without a full LLM re-run
veramynd-parser repair-normalized output/stage1/lessons --normalize-dir output/normalize

# Batch-1 gold retrieve (live: R@25=100%, R@20=85%, R@50=100%)
# Gold list: docs/_ga_g1_module2_goldset.md (FULL+PARTIAL = positives)
python -m veramynd_parser.scripts.batch_align_all \
  --retrieve-dir output/retrieve_gold4 \
  --diag-dir output/reports/retrieve_diag_gold4 \
  --from-gold output/reports/gold_set_batch1_from_md.jsonl \
  --judge-shortlist-k 50 \
  --skip-judge --skip-report --force-retrieve
python -m veramynd_parser.scripts.eval_r20

# Gold-4 judge (limit 25 = protected shortlist). Set JUDGE_MODEL / ANTHROPIC_API_KEY
# in .env for Claude (claude-sonnet-4-5 + claude-opus-4-6 escalate).
veramynd-parser judge-standards --retrieve-file output/retrieve_gold4/G1M2U1L3.json \
  --lesson-file output/stage1/lessons/G1M2U1L3.json \
  --standards-dir output/normalize_standards --out output/judge/G1M2U1L3.json \
  --limit 25
veramynd-parser report-alignments \
  --judge-file output/judge/G1M2U1L1.json \
  --judge-file output/judge/G1M2U1L3.json \
  --judge-file output/judge/G1M2U1L6.json \
  --judge-file output/judge/G1M2U3L5.json \
  --out output/reports/gold4_alignments.csv
```

Partial embeds (`--resource-id` / `--code`) refresh only those points.
`--recreate` rebuilds the embedding index for the requested scope; if no scope
is specified, it rebuilds the entire collection (a filtered run never deletes
the rest of the collection).

**Incremental by default / force for maintenance:** day-to-day runs skip unchanged
chunk fingerprints and matching Qdrant `content_hash` values. Use `--force`
(and embed `--recreate` when rebuilding the index for a scope or the full
collection) for full recomputation when onboarding the next publisher or after
a model/schema change. See [`veramynd_parser/README.md`](veramynd_parser/README.md).

## Repository map

```
veramynd/
├── README.md / LICENSE
├── docs/                       # design & flow documentation
├── data/samples/               # reference PDF + standards spreadsheet
├── _archive/                   # non-production one-offs (do not import)
└── veramynd_parser/            # installable package + CLI
    ├── veramynd_parser/        # library (pdf/, normalize/, chunk/, embed/, …)
    ├── tests/
    ├── examples/
    ├── output/                 # pipeline artifacts (local)
    ├── .env.example
    ├── pyproject.toml
    └── requirements.lock
```

Local Qdrant: path mode (`.qdrant_data`) by default, or set `QDRANT_URL`. A Docker
compose file lives under [`_archive/docker/`](_archive/docker/) for optional HTTP mode.

## Docs

| Doc | Use it for |
|---|---|
| [docs/flow.md](docs/flow.md) | Pipeline flow (some stage tables may lag the code — prefer this README for status) |
| [docs/architecture.md](docs/architecture.md) | Full product design + gold-set / roadmap |
| [docs/architecture-agentic-graph.md](docs/architecture-agentic-graph.md) | Parallel agentic design (not coded) |
| [docs/complete-project-flow.md](docs/complete-project-flow.md) | Deep onboarding walkthrough |
| [veramynd_parser/README.md](veramynd_parser/README.md) | Install, CLI reference, package layout |

## Requirements

- Python >= 3.11
- Primary path: Docling + PyMuPDF + openpyxl + pydantic
- Lite path (no Docling): `pip install -e '.[lite]'`, then `Config(engine="pymupdf")`
- Embed / retrieve: OpenAI API key + optional `sentence-transformers` for rerank
- Judge: OpenAI (`gpt-*`) or Anthropic (`claude-*` + `ANTHROPIC_API_KEY`)

## License

MIT — see [LICENSE](LICENSE).
