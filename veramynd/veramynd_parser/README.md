# veramynd-parser

Structure-aware curriculum parser and alignment pipeline: teacher-guide PDF →
lessons → pedagogical normalize → standards embed → hybrid retrieve (through
judge/report). Separates a guide into lessons, parses a standards spreadsheet
into a grade-indexed tree, and **verifies** with GO/REVIEW/BLOCK before anything
downstream trusts it.

Built against real documents (in `../data/samples/`):

- `ELA Grade 1 Module 2 Teacher Guide.pdf` — EL Education, 440 pages, 40 lessons
  (**Batch-1 locked** through retrieve; **gold-4 judge measured**)
- `Grade 1 GA ELA Standards.xlsx` — Georgia ELA, 188 standards
- `21111_RBtL_SSManual_L1.pdf` — Reading Roots Shared Story Teacher’s Manual
  Level 1 (**Stage-1 GO** — 14 lessons in `output/stage1_ssmanual/`; normalize →
  retrieve **not** locked yet)

Batch-1 gold retrieve (protected bar): **R@25 = 100%** on
`output/retrieve_gold4/`. Live gold-4 judge uses
[`prompts/assembled_judge_prompt.md`](veramynd_parser/prompts/assembled_judge_prompt.md)
(engine + GA Grade 1 overlay), Anthropic Sonnet batch + Opus escalate,
`--limit 25`. Prior OpenAI `align_judge.v1.1` baseline was **18/19 = 94.7%**.
Assembled re-judge of L3/L6/U3L5 is still open — see
[What's still incomplete](#whats-still-incomplete).

**Dynamic Stage-1 (honest):** routes EL vs generic from document signals; generic
lesson starts are **shared heading patterns** (Lesson / Day / Session /
**Shared Story N** / **Start-Up Lesson**), not `if publisher == …` branches.
Re-running a known shape needs **no code change**. A brand-new heading style may
need a small pattern add — then that shape is reusable.
## Two engines: Docling extracts, PyMuPDF verifies

The parser runs **two independent PDF engines** and plays them against each other:

- **Docling (primary content).** Layout analysis produces semantically labeled
  elements (`section_header`, `list_item`, `page_header`, `table`, …) with page
  provenance, and — via TableFormer — **structured tables**. This is more robust than
  font-threshold guessing and recovers tables a raw text layer destroys. Every parse
  is **content-addressed cached**, so a document is parsed once (~100 s for 440 pages)
  and instant after.
- **PyMuPDF (outline + verifier).** It reads the **bookmarks** Docling doesn't expose
  (the separation index), and independently **cross-verifies** Docling's output — a
  genuine second opinion.

On the 40-lesson reference document the two engines agree **40/40** on every
structural fact (standards codes, agenda timing, section/letter, body blocks,
boundaries). Where their free text differs, Docling is the more complete one — it
rejoins hyphenated wraps and keeps full multi-line titles. Set
`Config(engine="pymupdf")` for a dependency-free, font-tier fallback that needs no ML
models.

### Exported page numbers are printed footers

Internally the parser still uses **PDF page indices** (Docling, bookmarks, verify).
At export (`guide --json`, `export`, `remap-pages`), every `page_start` / `page_end` /
block `page` is remapped via an **exact footer scan** of each PDF page — not a
constant offset. Publisher gaps (e.g. 38, 193, 335) are never invented. Pass
`--pdf-pages` to keep PDF indices in JSON.

### OCR is automatic

The parser converts **any** PDF — born-digital or scanned — without being told
which it is. `ocr_mode="auto"` (the default) samples the pages with PyMuPDF: if they
already carry a text layer it skips OCR (the born-digital fast path, ~0.9 s/page); if
they're image-only it turns OCR on so Docling reads the pixels. Validated on a
synthetic scanned copy of Lesson 1 — with no text layer, auto-detect enabled OCR and
recovered the headings, agenda, and even the standard codes (`W.1.8`, `SL.1.1a`).
Force it either way with `--ocr on|off|auto`. The OCR flag is part of the cache key,
so born-digital and OCR'd parses of the same file cache separately.

## How structure is recovered

The teacher guide is an untagged PDF, so structure comes from the document's own
signals, not markup:

| Concern | Mechanism |
|---|---|
| **Route** | Structure detector → **EL-like** (bookmark codes) or **unknown/generic**. |
| **Separate lessons (EL)** | PyMuPDF bookmarks (`G1M2U1L1` = grade·module·unit·lesson); half-open span to next bookmark. Unit overviews held out. |
| **Separate lessons (generic)** | Outline + page headings: Lesson/Day/Session, **Shared Story N** (title page only), **Start-Up Lesson**; collapse running-header repeats. Lesson ids follow publisher numbers (e.g. Shared Story 4 → `L04`; no `L03` if Story 3 is absent). |
| **Divide a lesson** | EL: Docling labels / PyMuPDF font tiers. Generic: deterministic section-role map (materials aliases include “you will need”; letter-spacing repair for display PDF text). Hollow (no-step) blocks are skipped. |
| **Steps** | Each instructional step carries **page** provenance and `kind: procedure \| scaffold` (core activity vs in-block ELL/UDL/support). Scaffolds stay under the parent block. |
| **Tables** | Docling's TableFormer recovers materials lists, vocabulary and checklist tables as row-major cells. |
| **Standards tree** | Column-role detection → GA or generic adapter → hierarchy (parent column / level / indent / dotted / flat) → existing `GradeStandards` schema. Optional GPT-4.1-mini classifies **ambiguous structure only** (never invents codes/text/parents). |
| **Trust** | Dual gates: teacher-guide verifier **and** standards verifier — each emits **GO / REVIEW / BLOCK**. Only GO is production-trusted. Generic exterior cover/TOC gaps are WARN (not REVIEW). |

Two vocabularies are kept deliberately separate: the guide **declares** standards in
CCSS codes (`RL.1.1`) while the target framework uses Georgia codes (`1.F.PA.4.d`).
The parser preserves the claim and the framework side-by-side; it never joins them on
the code (they don't overlap).

## Install

```bash
cd veramynd_parser
pip install -e .              # lightweight: pymupdf, openpyxl, pydantic
pip install -e '.[docling]'   # + Docling, the default primary content engine
# or: pip install -e '.[test]'
```

Requires Python ≥ 3.11. The base install depends on `pymupdf`, `openpyxl`, `pydantic`
only — `Config.engine` defaults to `"docling"`, so add the `docling` extra unless
you're running with `Config(engine="pymupdf")` / `--engine pymupdf` throughout.

## Use

Command line:

```bash
# parse a teacher guide and print a summary
veramynd-parser guide  "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" --json guide.json

# parse, verify, and write lessons (JSON page numbers = printed footers)
veramynd-parser export "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" \
  --out output/stage1 --standards "../data/samples/Grade 1 GA ELA Standards.xlsx" \
  --framework "GA ELA" --expect 40

# rewrite existing lesson JSON from PDF indices → printed footers (no re-parse)
veramynd-parser remap-pages "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" \
  --lessons-dir output/stage1/lessons --from-pdf-indices

# parse a standards spreadsheet (GO/REVIEW/BLOCK; --json only written on GO unless --allow-block)
veramynd-parser stds "../data/samples/Grade 1 GA ELA Standards.xlsx" \
  --framework "GA ELA" --json output/stage1/standards.json

# parse AND run the teacher-guide safety-net verifier
veramynd-parser verify "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" --expect 40

# Second-publisher example (Shared Story manual) — generic route; PDF page indices
veramynd-parser export "../data/samples/21111_RBtL_SSManual_L1.pdf" \
  --out output/stage1_ssmanual --publisher unknown --engine pymupdf --pdf-pages \
  --standards "../data/samples/Grade 1 GA ELA Standards.xlsx" --framework "GA ELA"
```

Library:

```python
from veramynd_parser import parse_teacher_guide, parse_standards, verify
from veramynd_parser.pdf.document import PdfDocument

guide = parse_teacher_guide("../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf")
for lesson in guide.lessons:
    print(lesson.code, lesson.title, lesson.total_minutes, "min")
    print("  claims:", lesson.declared_standards)

with PdfDocument("../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf") as doc:
    report = verify(guide, doc=doc, expected_count=40)
print(report.render())          # GO / REVIEW / BLOCK
```

## Standards ingestion (dynamic Stage-1)

Standards files are no longer assumed to be a fixed GA `Code | Standard Text` sheet.

Pipeline:

```
spreadsheet → column detection → adapter (GA | generic)
          → hierarchy → GradeStandards → standards verify (GO/REVIEW/BLOCK)
```

| Piece | Behavior |
|---|---|
| **Columns** | Alias detection for code/text/grade/parent/level/subject/domain/strand (any order) |
| **Adapters** | GA for Georgia-shaped frameworks/codes; otherwise generic — never force unknown → GA |
| **Hierarchy** | Parent column → level column → indent → dotted codes → flat (all `standard`) |
| **Grades** | Grade column preferred; multi-grade sheets allowed (`Standard.grade` per row) |
| **LLM (optional)** | GPT-4.1-mini for ambiguous **structure** only (column roles, level labels, framework-shape hint). Cached under `.semantic_standards_cache`. `--no-semantic-standards-llm` disables |
| **Verify** | S1–S12 → `standards_verification_verdict.json`. Non-GO withholds trusted `standards.json` unless `--allow-block` |
| **Downstream gate** | `normalize-standards` requires sibling GO verdict (or `--allow-unverified`) |

GA reference fixture still verifies **GO** with `--framework "GA ELA"`. Structural fixtures live under `tests/fixtures/standards/`.

## The safety-net verifier

Teacher-guide checks use two severities that fold into three verdicts:
**FAIL → BLOCK**, **REVIEW → REVIEW**, soft **WARN** alone still allows **GO**.

| Layer | Checks | Gate |
|---|---|---|
| 1 · Separation integrity | count, page partition, order, spans, unique ids, contiguity | hard |
| 2 · Cross-signal | the running header on each lesson's first page matches its bookmark code | hard |
| 3 · Division completeness | required blocks present; Materials present; agenda time in band; Vocabulary present; **agenda plan matches body blocks; every block has steps** | hard (materials) / soft |
| 4 · Cross-engine | every standard Docling reported is confirmed in PyMuPDF's own text | hard |

Each `Lesson` captures both the **plan** and the **content**: `agenda` is the cover
table-of-contents (`section · letter · title · minutes`), and `instructional_blocks`
is the body — the same sub-blocks with their **`steps`**, the actual teacher/student
procedure the alignment judge reads for evidence. The completeness checks exist
because a structure-only verifier can pass while silently dropping content: the
plan-vs-body check caught a real case where a sub-block Docling mislabeled had its
steps merged into the previous block.

The timing check is not decorative. During development it flagged three lessons whose
agenda durations word-wrapped in the PDF (`(5 min-utes)` and `(20 minutes)` broken
across lines), which had silently under-counted their timing. That surfaced the two
line-stitching rules in `text_utils.py`; afterward all 40 lessons verify clean.

## Package layout

```
veramynd_parser/
├── models.py              # Pydantic contracts (Lesson, Table, Standard, ...)
├── config.py              # one settings object; picks the engine
├── text_utils.py          # normalization + patterns (de-hyphenate, stitch minutes, codes)
├── fonts.py               # 3-tier font classifier (PyMuPDF fallback path)
├── pdf/
│   ├── document.py        # PyMuPDF adapter (outline + verification)
│   ├── docling_parser.py  # Docling adapter — labeled elements + tables, cached
│   ├── separator.py       # bookmarks -> lesson spans (+ font/header fallback)
│   ├── divider.py         # PyMuPDF font-tier division (fallback)
│   ├── docling_divider.py # Docling semantic-label division (primary)
│   ├── page_map.py        # exact PDF index → printed footer page map
│   ├── export_pages.py    # remap page fields at JSON export boundary
│   ├── structure_detector.py  # EL-like vs unknown vs unusable routing
│   ├── lesson_boundaries.py   # generic lesson spans
│   ├── generic_divider.py     # deterministic section → Lesson
│   ├── semantic_section.py    # LLM section-role fallback (ambiguous only)
│   └── teacher_guide.py   # orchestration: detect → EL or generic path
├── standards/
│   ├── spreadsheet.py     # orchestrate parse → GradeStandards
│   ├── columns.py         # header → column-role map
│   ├── hierarchy.py       # generic hierarchy signals
│   ├── grades.py          # grade cell / code-prefix normalization
│   ├── dotted.py          # GA-shaped dotted helpers
│   ├── verify.py          # standards GO / REVIEW / BLOCK
│   ├── semantic.py        # limited LLM structure classification
│   └── adapters/          # GA + generic → to_canonical()
├── verify/
│   └── verifier.py        # teacher-guide safety net (incl. REVIEW)
├── cli.py                 # guide / stds / verify / export / normalize / chunk /
│                          # embed / retrieve / judge / report commands
└── .docling_cache/        # content-addressed Docling parse cache
```

## What's still incomplete

- **Batch-1 retrieve protected bar (met)** — live enterprise defaults on 4 gold
  lessons / 20 FULL+PARTIAL positives (`multi_normalize_focused`):
  **Recall@25 = 100% (20/20)** (protected QA bar — do not tune retrieve knobs
  to hide normalize/parser regressions),
  **Recall@20 = 85% (17/20)**, **Recall@50 = 100% (20/20)**, R@10 = 40%.
  Product cut for the judge is **top-20**. Gold label:
  [`docs/_ga_g1_module2_goldset.md`](../docs/_ga_g1_module2_goldset.md)
  (eval-only — never enters ranking). Residual @20 (all still ≤25, U1L6):
  `1.P.EICC.3.e`, `1.P.EICC.3.f`, `1.T.RA.2.a`. Gold **none** rows outside
  top 25 do not count against R@25.
- **Batch-1 gold-4 judge (measured, not closed)** — live prompt is
  `assembled_judge_prompt.md` (GA overlay includes SME fences F1–F4 / F8).
  Gold eval is always `--limit 25` (do not retune retrieve to hide judge
  misses). After retrieve, a coverage pass can still judge activity-driven
  feedback/present codes that missed top 25. **L1** on the assembled prompt
  (Anthropic batch, `--no-cache --limit 25`): **6/7** gold overlap; leftover
  overlap miss `1.P.EICC.4.c` (gold full / json partial); `1.P.EICC.4.e`
  is outside top 25. **L3 / L6 / U3L5** are not yet re-judged on this prompt
  (current JSON may be older v1 / GPT runs). Prior OpenAI `align_judge.v1.1`
  baseline on unique top-25 pairs: **18/19 (94.7%)**. All 40 EL lessons, and
  Shared Story through judge, are **not** claimed. Close-read comprehension
  can be understated until Read-aloud Guides are in Stage-1 (P4 caveat;
  do not hand-edit labels).
- **Any-publisher / any-framework claim** — architecture is
  curriculum-agnostic (acts + competency bridges + **shared heading patterns**,
  not per-publisher `if/elif` trees or hard-coded lesson IDs).
  **Validated through retrieve** on EL G1M2 + GA ELA; **gold-4 judge** on that
  same stack. **Stage-1 GO** on Reading Roots Shared Story L1
  (`output/stage1_ssmanual/`, 14 lessons). Next proof: that corpus through
  **normalize → retrieve → judge** (and more publishers / grades).
- **Scale / head precision** — broader multi-publisher fixtures and stronger
  **R@10** are still open.
- **Agentic graph track** — design doc only (`docs/architecture-agentic-graph.md`).
- Validated primarily on the sample documents under `../data/samples/` plus
  synthetic standards fixtures.

## Tests

```bash
pytest
```

Tests cover Stage-1 parse/verify (PDF + standards fixtures), normalize sanitizers,
chunk/embed (mocked OpenAI + in-memory Qdrant), retrieve, and judge grounding.
Integration cases that need the real PDF/xlsx are skipped automatically if those
files are absent. Standards structural fixtures:
`tests/fixtures/standards/` (rebuild with `python tests/fixtures/standards/build_fixtures.py`).

Protected recall smoke (existing `retrieve_gold4` artifacts):

```bash
python -m veramynd_parser.scripts.eval_r20            # R@10/20/25/30/50
python -m veramynd_parser.scripts.phase8_regression   # GA standards GO + R@25 == 100%
```

## Pedagogical normalizer (Stage 3 — lessons)

Distills each parsed lesson into **what the student does**, with logistics stripped.
Prompt version: **`normalize_ela.v2.3`**. Uses **OpenAI only** (default model:
`gpt-4.1-mini`, overridable via `OPENAI_MODEL`). Results are **content-addressed
cached**. Runs are **resumable**: if interrupted, re-run the same command and
completed lessons are skipped.

### Versioned artifact reuse (production reproducibility)

Normalize each unique input **once**, then reuse:

1. Fingerprint Stage-1 lessons (or standards tree) + prompt version + model  
2. Look up `.normalize_cache/artifact_registry.json`  
3. **Hit** → reuse stored normalize dir / per-leaf LLM cache (no new LLM)  
4. **Miss** → normalize once → register artifact  

Same PDF/standards again → same fingerprint → same results.  
New publisher or new standards edition → new fingerprint → process once.

```bash
# Seed registry from an existing Batch-1 run (no LLM)
veramynd-parser artifact-register \
  --lessons-dir output/stage1/lessons --out output/normalize \
  --standards output/stage1/standards.json --standards-out output/normalize_standards

veramynd-parser artifact-status

# Normal day-to-day: omit --force so cache + registry reuse
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize
```

**Do not `--force`** unless you intend a new LLM pass (that creates a refreshed
artifact and can move recall). For sanitize-only updates use `repair-normalized`.

Post-LLM **sanitizers** (also via `repair-normalized`) enforce verbatim evidence,
Stage-1 block IDs, and restore under-extracted literacy acts from steps
(ask/answer learning targets, infer/levels of meaning, descriptive words,
collaborative share/listen/feedback) — publisher-agnostic cues, not gold IDs.

```bash
pip install -e '.[normalize]'

# 1) create .env (gitignored) — never commit secrets
copy .env.example .env
# edit .env → set OPENAI_API_KEY=sk-...
# optional: OPENAI_MODEL=gpt-4.1-mini

# 2) run (resume-safe; reuses cache + artifact registry)
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize

# one lesson
veramynd-parser normalize-lessons output/stage1/lessons --one G1M2U1L1 --out output/normalize

# force full re-run (new LLM pass — only when intentional)
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize --force

# re-apply sanitizers only (no LLM) after Stage-1 or sanitize code changes
veramynd-parser repair-normalized output/stage1/lessons --normalize-dir output/normalize
```

API keys are loaded only from `veramynd_parser/.env` or the process environment
(`OPENAI_API_KEY`). There is no `--api-key` CLI flag.

Progress is written to `output/normalize/normalize_progress.json`.
Registry: `.normalize_cache/artifact_registry.json`.

## Incremental vs maintenance (enterprise)

Default runs are **incremental** so adding the next publisher/grade does not
recompute an entire corpus. Pass **`--force`** (and/or embed `--recreate`) for
maintenance recomputation.

| Stage | Incremental default | Maintenance |
|---|---|---|
| `normalize-*` | content-addressed LLM cache | `--force` / `--no-cache` |
| `repair-normalized` | re-sanitizes existing JSON in place | re-run after Stage-1/sanitize changes |
| `chunk-lessons` | skip when `source_fingerprint` matches | `--force` |
| `embed-*` | skip when Qdrant `content_hash`+model+dims match | `--force` / `--recreate` |
| `judge-standards` | content-addressed judge cache | `--no-cache` after prompt/parser changes |
| `batch_align_all` | skip existing retrieve/judge JSON | `--force` (or `--force-retrieve` / `--force-judge`) |

`--recreate`: rebuild the embedding index for the **requested scope**. If no
scope is specified (`--resource-id` / `--code`), rebuild the **entire** collection.
A filtered `--recreate` never deletes points outside that scope.

Examples:

```bash
# Day-to-day: only changed lessons are rebuilt / re-embedded
veramynd-parser chunk-lessons output/stage1/lessons --normalize-dir output/normalize --out output/chunks
veramynd-parser embed-chunks output/chunks --out output/embeddings

# Maintenance: full recompute
veramynd-parser chunk-lessons output/stage1/lessons --normalize-dir output/normalize --out output/chunks --force
veramynd-parser embed-chunks output/chunks --out output/embeddings --force --recreate
python -m veramynd_parser.scripts.batch_align_all --force
```

### Chunk (hierarchical, no LLM)

```bash
veramynd-parser chunk-lessons output/stage1/lessons --normalize-dir output/normalize --out output/chunks
```

Writes lesson + instructional chunks plus evidence join pointers under `output/chunks/`.
Re-runs skip unchanged lessons unless `--force`.

### Embed → Qdrant (OpenAI text-embedding-3-large)

```bash
pip install -e '.[embed]'
veramynd-parser embed-chunks output/chunks --out output/embeddings
```

Uses `OPENAI_API_KEY` from `.env`. Default model: `text-embedding-3-large` (3072-d).  
Stores vectors in Qdrant (`QDRANT_URL` or local `.qdrant_data`). Evidence pointers are not embedded.

Incremental by default (skips unchanged `content_hash`). `--force` re-embeds the
selected scope. `--recreate` rebuilds the embedding index for the requested scope;
with no scope, it rebuilds the entire collection (filtered runs never wipe other
lessons/standards).

### Embed standards → Qdrant

```bash
veramynd-parser embed-standards output/normalize_standards --out output/embeddings --recreate
```

Same model (`text-embedding-3-large`). Collection default: `veramynd_standards`
(does not use `QDRANT_COLLECTION`; override with `--collection` or
`QDRANT_STANDARDS_COLLECTION`).

**Defaults (enterprise):** embed **leaf codes only** (`leaves_only=True`) with
**rich retrieval text** from normalize (`use_rich_text=True` via
`embed/standard_text.py`). Parent standards stay on disk for hierarchy/context
but are out of the retrieve funnel. Re-run with `--recreate` after changing these
modes.

Smoke check (lesson chunk → nearest standards):

```bash
veramynd-parser smoke-retrieve-standards --chunk-file output/chunks/by_lesson/G1M2U2L1.json --family lesson
```

### Hybrid retrieve + cross-encoder rerank

```bash
pip install -e '.[retrieve]'   # adds sentence-transformers for local bge-reranker
veramynd-parser retrieve-standards \
  --chunk-file output/chunks/by_lesson/G1M2U1L3.json \
  --top-k 30 --rerank-k 10 \
  --out output/retrieve/G1M2U1L3.json
```

Dense (Qdrant) + BM25 → RRF, then `BAAI/bge-reranker-base`.
Pass `--no-rerank` to inspect the hybrid list only.

**Enterprise multi-query** (preferred for gold / production runs) builds focused
query arms from **normalized lessons** (`multi_normalize_focused`): objectives,
skills, student actions, tasks, vocabulary, evidence, and **curriculum-agnostic
competency bridges** (e.g. predict, infer, dialogue Q&A, descriptive words,
context clues, create poem — signal-matched from lesson text, not hard-coded
lesson IDs). Chunk files are optional for this path; Batch-1 gold R@25 is driven
by normalize queries against the standards collection. Funnel:

1. Per query: dense (Qdrant) + BM25 → RRF  
2. Multi-query merge (`top_k_sum` + optional **max_blend** depth term; also
   `sum` / `max` / `log_dampened`) into `merge_top_k`  
3. Local CE (`BAAI/bge-reranker-base`), often grade-exhaustive below
   `--exhaustive-ceiling`  
4. Shortlist fusion (CE + merge RRF, parent-cap diversity, **RRF head lock**,
   mild **mid-CE dual-agreement** boost) → `--judge-shortlist-k` (default 50;
   product cut **Recall@20**; protected QA bar **Recall@25**)  
5. Optional `--shortlist-rescue-slots N` (default **0**): classic-sum tail
   injection when needed; Batch-1 enterprise path keeps rescue off.

Batch retrieval uses this multi-query path by default (`--single-query` is the
legacy opt-out). Diagnostics under `output/reports/retrieve_diag_gold4/` (or
`--diag-dir`) record dense, BM25, merge-RRF, reranker, and final rank.

```bash
# Batch-1 gold retrieve (live: R@25=100%, R@20=85%, R@50=100%)
# Requires local Qdrant standards collection + normalize artifacts.
python -m veramynd_parser.scripts.batch_align_all \
  --retrieve-dir output/retrieve_gold4 \
  --diag-dir output/reports/retrieve_diag_gold4 \
  --from-gold output/reports/gold_set_batch1_from_md.jsonl \
  --judge-shortlist-k 50 \
  --skip-judge --skip-report \
  --force-retrieve

# Recall@10/20/25/30/50 vs committed gold prose
python -m veramynd_parser.scripts.eval_r20

# Optional offline merge / rescue sweeps (older tooling still available)
python -m veramynd_parser.scripts.eval_merge_aggregation \
  --gold output/reports/gold_set_batch1_from_md.jsonl \
  --diag-dir output/reports/retrieve_diag_gold4
```

Key flags: `--multi-query`, `--from-gold`, `--arm-limit`, `--merge-top-k`,
`--merge-aggregation`, `--merge-top-arms`, `--merge-log-dampen-base`,
`--pool-membership-mode`, `--rerank-k`, `--exhaustive-ceiling`, `--parent-cap`,
`--blend-rrf`, `--preserve-rrf-top`, `--judge-shortlist-k`,
`--shortlist-rrf-weight`, `--shortlist-rescue-slots`, `--diag-dir`.

The reranker is an unchanged pretrained CrossEncoder. **No gold labels enter
query generation, merge, CE, or shortlist fusion** — gold is eval-only.

### Alignment judge + grounding (enterprise K–12)

Live prompt: [`prompts/assembled_judge_prompt.md`](veramynd_parser/prompts/assembled_judge_prompt.md)
(framework-neutral **engine** + GA Grade 1 **overlay**). Overlay-only SME
fences F1–F4 / F8 are encoded there; do not rewrite the engine. Scores
**student acts** in Stage-1 steps. Ungrounded quotes become `none`.
`align_judge_v1.md` is unused.

Gold-4 eval: `--limit 25` on `output/retrieve_gold4/` (R@25 bar stays;
do not retune retrieve for judge misses). After the retrieve shortlist, a
**coverage pass** appends activity-driven feedback/present codes when the
lesson has those tasks (`1.P.EICC.4.f`, `1.P.CP.1.c`, `1.P.CP.2.a`) even if
they missed top 25. Opt out: `--no-coverage-pass`.

Close-read lessons that only *cite* a supporting Read-aloud Guide (guide body
not in Stage-1) get `input_scope_caveat` on named comprehension codes — scores
are likely understated; **do not hand-edit labels**. Re-run those lessons only
if the client shares the guides.

```bash
pip install -e '.[judge]'   # openai + anthropic + dotenv
veramynd-parser judge-standards \
  --retrieve-file output/retrieve_gold4/G1M2U1L1.json \
  --lesson-file output/stage1/lessons/G1M2U1L1.json \
  --standards-dir output/normalize_standards \
  --out output/judge/G1M2U1L1.json \
  --limit 25 --no-cache
```

**Quality profile `enterprise_k12` (default):**
1. **Batch first** — one Sonnet call for the shortlist (default `max_tokens`
   16384). If Anthropic returns `results` as a JSON string, it is coerced to a
   list. Pair mode is `--no-batch` or automatic fallback if batch JSON is
   invalid.
2. **Escalate** — re-judge `partial`, `needs_review`, or empty-evidence
   positives with `JUDGE_ESCALATE_MODEL` (Opus)
3. **Clause aggregation** — `partial` means at least one required clause met
   and at least one unmet; it is not a confidence label
4. **Grounding** — ungrounded positive claims are rejected to `none`

Provider is chosen from the model id (no extra flag):
- `gpt-*` / `o*` → OpenAI (`OPENAI_API_KEY`)
- `claude-*` → Anthropic (`ANTHROPIC_API_KEY`); live gold-4 defaults:

```
JUDGE_MODEL=claude-sonnet-4-5
JUDGE_ESCALATE_MODEL=claude-opus-4-6
```

Opt out of escalate for smoke/cost: `--no-escalate`.
Opt out of coverage extras: `--no-coverage-pass` (saves judge cost; U3L5
feedback/present codes then stay unjudged if they missed top 25).

Batch all lessons:

```bash
python -m veramynd_parser.scripts.batch_align_all --skip-retrieve
# cheaper smoke: --no-escalate
# gold-scoped multi-query: see retrieve section above
```

### Alignment report (CSV)

```bash
veramynd-parser report-alignments \
  --judge-file output/judge/G1M2U1L1.json \
  --judge-file output/judge/G1M2U1L3.json \
  --judge-file output/judge/G1M2U1L6.json \
  --judge-file output/judge/G1M2U3L5.json \
  --out output/reports/gold4_alignments.csv
```

Or export a whole folder: `--judge-dir output/judge`.  
Use `--aligned-only` for full+partial rows only (still never drops rows for missing confidence).
Also writes an HTML audit dashboard next to the CSV (disable with `--no-html`).
CSV columns include `needs_review`, `coverage_pass`, and `input_scope_caveat`.

Client-facing CSVs (no retrieve scores; includes expert-vs-system compare) live
under `output/reports/client/`.

**Gold metrics:** Batch-1 positives live in
[`docs/_ga_g1_module2_goldset.md`](../docs/_ga_g1_module2_goldset.md). Use
`python -m veramynd_parser.scripts.eval_r20` against `output/retrieve_gold4/` for R@10/20/25/30/50
(protected bar: **R@25 == 100%**). Judge exact vs gold: `output/reports/gold_judge_summary.csv`.
With `--from-gold` JSONL, batch also writes leaf-recall summaries
(`output/reports/retrieve_gold_metrics.json`). Offline
sweeps (`eval_merge_aggregation`, `eval_shortlist_rescue`) still replay cached
diags.

Library:

```python
from veramynd_parser import normalize_lesson, Config

norm = normalize_lesson("output/stage1/lessons/G1M2U1L1.json")
print(norm.resource_id)
print(norm.objective)
print(len(norm.evidence))
```

Output shape: ELA `NormalizedLesson` (`schema_version` `2.0-ela`) with
`objective`, `what_is_taught`, `student_actions`, `evidence`, `subject_profile`, etc.
Cache lives in `.normalize_cache/` (gitignored).

## Extending to a new document type

Structure is recovered per document, so a new publisher or a lesson-plan format is a
new adapter that produces the same `Lesson` / `TeacherGuide` contract. When a
document has no usable bookmarks, `separator.separate_by_font` recovers lesson starts
from a full running header (`Grade N: Module N: Unit N: Lesson N`) — and the same
verifier runs either way.
