# veramynd-parser

A structure-aware parser for curriculum documents. It separates a teacher-guide PDF
into individual lessons, divides each lesson into its parts, parses a standards
spreadsheet into a grade-indexed tree, and **verifies** the result with a layered
safety net before anything downstream trusts it.

Built and validated against two real documents (in `../data/samples/`):

- `ELA Grade 1 Module 2 Teacher Guide.pdf` — EL Education, 440 pages, 40 lessons
- `Grade 1 GA ELA Standards.xlsx` — Georgia ELA, 188 standards

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
| **Separate lessons** | PyMuPDF reads the embedded bookmarks (`G1M2U1L1` = grade·module·unit·lesson); the boundary is the half-open span to the next bookmark. Unit overviews are held out. |
| **Divide a lesson** | Docling's semantic labels (`section_header` → `list_item`) drive division; the PyMuPDF fallback uses a 3-tier font hierarchy (13 / 11 / 9.5 pt-bold). |
| **Tables** | Docling's TableFormer recovers materials lists, vocabulary and checklist tables as row-major cells. |
| **Standards tree** | Hierarchy is derived from the **code's dot-depth** (`1.F` → `1.F.PA` → `1.F.PA.4` → `1.F.PA.4.d`), not the spreadsheet's (mostly empty) level column. |
| **Trust** | A verifier gates the output — no lesson set is accepted until it passes, including a cross-engine check. |

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
  --out output/stage1 --standards "../data/samples/Grade 1 GA ELA Standards.xlsx" --expect 40

# rewrite existing lesson JSON from PDF indices → printed footers (no re-parse)
veramynd-parser remap-pages "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" \
  --lessons-dir output/stage1/lessons --from-pdf-indices

# parse a standards spreadsheet
veramynd-parser stds   "../data/samples/Grade 1 GA ELA Standards.xlsx" --json standards.json

# parse AND run the safety-net verifier (exit code 1 if any hard check fails)
veramynd-parser verify "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" --expect 40
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
print(report.render())          # GO / BLOCK
```

## The safety-net verifier

Three layers, two severities. A **hard** check that fails blocks the load; a **soft**
check that fails flags the lesson for review but still allows `GO`.

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
│   └── teacher_guide.py   # orchestration: separate + divide by engine
├── standards/
│   └── spreadsheet.py     # xlsx -> GradeStandards tree
├── verify/
│   └── verifier.py        # the 4-layer safety net (incl. cross-engine)
├── cli.py                 # guide / stds / verify / export / normalize / chunk /
│                          # embed / retrieve / judge / report commands
└── .docling_cache/        # content-addressed Docling parse cache
```

## What's still incomplete

- **Enterprise quality bar** — Batch-1 retrieve with `top_k_sum` +
  `--shortlist-rescue-slots 8` reaches **Recall@50 = 100%** and **Recall@10 ≈ 45%**
  (9/20). Pool coverage is no longer the bottleneck; **top-10 fused ranking** is
  (merge rank still dominates final rank; CE wins are often buried). Target remains
  ~90% Recall@10 on a larger multi-grade / multi-publisher gold set. Judge agreement
  vs SME gold is a separate gap, especially for `partial`.
- **Gold-set quality** — the gold set (`output/reports/gold_set_batch1.jsonl`)
  is SME-labeled and **not committed to this repo**; the gold-scoped commands
  below require obtaining or rebuilding it first. A packaged quality gate is
  planned but not yet shipped.
- **Agentic graph track** — design doc only (`docs/architecture-agentic-graph.md`).
- Validated primarily on the two sample documents under `../data/samples/`.

## Tests

```bash
pytest
```

Tests cover Stage-1 parse/verify, normalize sanitizers, chunk/embed (mocked OpenAI +
in-memory Qdrant), retrieve, and judge grounding. Integration cases that need the
real PDF/xlsx are skipped automatically if those files are absent.

## Pedagogical normalizer (Stage 3 — lessons)

Distills each parsed lesson into **what the student does**, with logistics stripped.
Uses **OpenAI only** (default model: `gpt-4.1-mini`, overridable via `OPENAI_MODEL`).
Results are **content-addressed cached**. Runs are **resumable**: if interrupted,
re-run the same command and completed lessons are skipped.

```bash
pip install -e '.[normalize]'

# 1) create .env (gitignored) — never commit secrets
copy .env.example .env
# edit .env → set OPENAI_API_KEY=sk-...
# optional: OPENAI_MODEL=gpt-4.1-mini

# 2) run (resume-safe)
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize

# one lesson
veramynd-parser normalize-lessons output/stage1/lessons --one G1M2U1L1 --out output/normalize

# force full re-run
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize --force
```

API keys are loaded only from `veramynd_parser/.env` or the process environment
(`OPENAI_API_KEY`). There is no `--api-key` CLI flag.

Progress is written to `output/normalize/normalize_progress.json`.

## Incremental vs maintenance (enterprise)

Default runs are **incremental** so adding the next publisher/grade does not
recompute an entire corpus. Pass **`--force`** (and/or embed `--recreate`) for
maintenance recomputation.

| Stage | Incremental default | Maintenance |
|---|---|---|
| `normalize-*` | content-addressed LLM cache | `--force` / `--no-cache` |
| `chunk-lessons` | skip when `source_fingerprint` matches | `--force` |
| `embed-*` | skip when Qdrant `content_hash`+model+dims match | `--force` / `--recreate` |

`--recreate`: rebuild the embedding index for the **requested scope**. If no
scope is specified (`--resource-id` / `--code`), rebuild the **entire** collection.
A filtered `--recreate` never deletes points outside that scope.
| `batch_align_all` | skip existing retrieve/judge JSON | `--force` (or `--force-retrieve` / `--force-judge`) |

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

**Enterprise multi-query** (preferred for gold / production runs) uses focused
queries from normalized learning targets, objectives, purpose, skills, actions,
tasks, vocabulary, and evidence. Funnel:

1. Per query: dense (Qdrant) + BM25 → RRF  
2. Multi-query merge (`--merge-aggregation`: `sum` default | `max` | `top_k_sum` |
   `log_dampened`) into `merge_top_k`  
3. Local CE (`BAAI/bge-reranker-base`), often grade-exhaustive below
   `--exhaustive-ceiling`  
4. Shortlist fusion (CE + merge RRF, parent-cap diversity) →
   `--judge-shortlist-k` (default 50)  
5. Optional `--shortlist-rescue-slots N` (default **0**): keep fused core of
   size `50−N`, fill the tail with best classic-`sum` candidates not already in
   core (`rescued_via: "sum"`). Does not reorder the core; N=0 is unchanged.

Batch retrieval uses this multi-query path by default (`--single-query` is the
legacy opt-out). Diagnostics under `output/reports/retrieve_diag/` record dense,
BM25, merge-RRF, reranker, and final rank for every candidate.

```bash
# Recommended Batch-1 retrieve profile (offline-validated):
#   Recall@10 ≈ 45% (held), Recall@50 = 100% (sum rescue recovers ~3 golds)
# NOTE: gold_set_batch1.jsonl is an SME-labeled artifact NOT committed to this
# repo — obtain it separately (or build your own gold JSONL with rows of
# {resource_id, standard_code, matched_status}) before running gold-scoped
# commands.
python -m veramynd_parser.scripts.batch_align_all \
  --multi-query \
  --from-gold output/reports/gold_set_batch1.jsonl \
  --merge-aggregation top_k_sum \
  --merge-top-arms 2 \
  --shortlist-rescue-slots 8 \
  --judge-shortlist-k 50 \
  --skip-judge --skip-report \
  --force-retrieve

# Offline sweeps (no re-embed / no CE re-run — uses cached diag / retrieve JSON)
python -m veramynd_parser.scripts.eval_merge_aggregation \
  --gold output/reports/gold_set_batch1.jsonl \
  --diag-dir output/reports/retrieve_diag
python -m veramynd_parser.scripts.eval_shortlist_rescue \
  --gold output/reports/gold_set_batch1.jsonl \
  --retrieve-dir output/retrieve
```

Key flags: `--multi-query`, `--from-gold`, `--arm-limit`, `--merge-top-k`,
`--merge-aggregation`, `--merge-top-arms`, `--merge-log-dampen-base`,
`--pool-membership-mode`, `--rerank-k`, `--exhaustive-ceiling`, `--parent-cap`,
`--blend-rrf`, `--preserve-rrf-top`, `--judge-shortlist-k`,
`--shortlist-rrf-weight`, `--shortlist-rescue-slots`, `--diag-dir`.

The reranker is an unchanged pretrained CrossEncoder. No gold labels enter
ranking or shortlist rescue — gold is eval-only.

### Alignment judge + grounding (enterprise K–12)

```bash
pip install -e '.[judge]'   # openai + dotenv (same as normalize)
veramynd-parser judge-standards \
  --retrieve-file output/retrieve/G1M2U1L3.json \
  --lesson-file output/stage1/lessons/G1M2U1L3.json \
  --standards-dir output/normalize_standards \
  --out output/judge/G1M2U1L3.json
```

**Quality profile `enterprise_k12` (default):**
1. **Pair depth** — one focused call per lesson-standard pair (`gpt-4.1`)
2. **Escalate** — re-judge `partial`, low/medium confidence, or empty-evidence
   positives with `JUDGE_ESCALATE_MODEL` (default `gpt-5`)
3. **Clause aggregation** — `partial` means at least one required clause met
   and at least one unmet; it is not a confidence label
4. **Grounding** — ungrounded positive claims are rejected to `none`

Opt out of escalate for smoke/cost: `--no-escalate`.  
Opt into the cheaper batch judge with `--batch`.

Batch all lessons:

```bash
python -m veramynd_parser.scripts.batch_align_all --skip-retrieve
# cheaper smoke: --no-escalate
# gold-scoped multi-query: see retrieve section above
```

### Alignment report (CSV)

```bash
veramynd-parser report-alignments \
  --judge-file output/judge/G1M2U1L3.json \
  --out output/reports/alignments.csv
```

Or export a whole folder: `--judge-dir output/judge`.  
Use `--aligned-only` for full+partial rows only (still never drops rows for missing confidence).
Also writes an HTML audit dashboard next to the CSV (disable with `--no-html`).

**Gold metrics:** with `--multi-query --from-gold`, batch writes leaf-recall
summaries (`output/reports/retrieve_gold_metrics.json`). The offline sweeps
(`eval_merge_aggregation`, `eval_shortlist_rescue` — see the retrieve section)
replay cached artifacts against the gold set; a packaged pass/fail quality
gate is planned but not yet shipped.

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
