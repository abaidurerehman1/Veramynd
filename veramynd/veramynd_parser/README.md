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
├── cli.py                 # guide / stds / verify / export commands
└── .docling_cache/        # content-addressed Docling parse cache
```

## Tests

```bash
pytest
```

31 tests run against the real documents (skipped automatically if the source files
are absent): 40-lesson separation, clean page partition, per-lesson division, all
agendas in band, the 188→4/14/35/135 standards tree, and the verifier passing on
good input while blocking corrupted input.

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

### Chunk (hierarchical, no LLM)

```bash
veramynd-parser chunk-lessons output/stage1/lessons --normalize-dir output/normalize --out output/chunks
```

Writes lesson + instructional chunks plus evidence join pointers under `output/chunks/`.

### Embed → Qdrant (OpenAI text-embedding-3-large)

```bash
pip install -e '.[embed]'
veramynd-parser embed-chunks output/chunks --out output/embeddings --recreate
```

Uses `OPENAI_API_KEY` from `.env`. Default model: `text-embedding-3-large` (3072-d).  
Stores vectors in Qdrant (`QDRANT_URL` or local `.qdrant_data`). Evidence pointers are not embedded.

### Embed standards → Qdrant

```bash
veramynd-parser embed-standards output/normalize_standards --out output/embeddings --recreate
```

Same model (`text-embedding-3-large`). Collection default: `veramynd_standards`
(does not use `QDRANT_COLLECTION`; override with `--collection` or
`QDRANT_STANDARDS_COLLECTION`).

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

Dense (Qdrant) + BM25 → RRF top 30, then `BAAI/bge-reranker-v2-m3` to top 10.
Pass `--no-rerank` to inspect the hybrid list only.

### Alignment judge + grounding

```bash
pip install -e '.[judge]'   # openai + dotenv (same as normalize)
veramynd-parser judge-standards \
  --retrieve-file output/retrieve/G1M2U1L3.json \
  --lesson-file output/stage1/lessons/G1M2U1L3.json \
  --standards-dir output/normalize_standards \
  --out output/judge/G1M2U1L3.json
```

Default judge model: `gpt-4.1` (`JUDGE_MODEL`). Pass `--escalate` to re-judge
`partial` / low-confidence pairs with `JUDGE_ESCALATE_MODEL` (default `gpt-5`).
Evidence quotes are string-matched against raw lesson steps; ungrounded
positive claims are rejected to `none`.

### Alignment report (CSV)

```bash
veramynd-parser report-alignments \
  --judge-file output/judge/G1M2U1L3.json \
  --out output/reports/alignments.csv
```

Or export a whole folder: `--judge-dir output/judge`.  
Use `--aligned-only` for full+partial rows only (still never drops rows for missing confidence).
Also writes an HTML audit dashboard next to the CSV (disable with `--no-html`).

**Note:** Gold-set eval harness is next (you fill `eval/gold_set.jsonl`); templates are under `eval/`.

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
