# output/ — production pipeline artifacts

Do not commit secrets. This folder is **tracked in git** as a reference-run
snapshot of the Grade 1 Module 2 sample corpus — regenerating changes these
files, so keep committed snapshots deliberate (or gitignore the folder if the
churn stops being worth it).

```text
output/
├── stage1/                 # Batch-1 EL G1M2 — parse + verify (GO, locked stack)
├── stage1_ssmanual/        # Shared Story L1 manual — Stage-1 GO (2nd publisher)
├── normalize/              # Batch-1 ELA normalize — schema 2.0-ela
├── normalize_standards/    # GA leaf normalize (shared by retrieve)
├── retrieve_gold4/         # Batch-1 gold retrieve (R@25 bar)
├── judge/                  # alignment verdicts (live assembled prompt; gold-4 16/20)
├── reports/                # gold4_alignments.csv, gold_judge_*.csv, client/
├── chunks/                 # hierarchical chunks for grounding / judge
└── embeddings/             # embed run manifest (vectors live in Qdrant)
```

## Stage 1 (`stage1/` and `stage1_ssmanual/`)

| Path | Role |
|------|------|
| `stage1/` | EL Module 2 — **Batch-1 locked** (40 lessons) |
| `stage1_ssmanual/` | `21111_RBtL_SSManual_L1.pdf` — **Stage-1 GO** (14 lessons: L01–L02 Start-Up, L04–L15 Shared Stories; no L03 — Story 3 absent in source) |
| `verification_report.txt` | Human-readable GO / BLOCK report |
| `verification_verdict.json` | Machine-readable gate verdict — downstream commands check this |
| `lessons/*.json` | Per-lesson contracts (primary Stage 1 product) |
| `standards.json` | Standards tree from the XLSX |
| `teacher_guide.json` | Full guide parse (audit / reload) |
| `lessons_index.tsv` | Human-readable lesson summary |

Normalize → retrieve for `stage1_ssmanual/` is **not** production-locked yet.

## Normalize (`normalize/`)

| Path | Role |
|------|------|
| `*.json` | Per-lesson ELA curriculum-normalization records |
| `normalize_progress.json` | Resume / status sidecar |

**Reuse:** content-addressed LLM cache (`.normalize_cache/`) + versioned
**artifact registry** (`.normalize_cache/artifact_registry.json`). Same Stage-1
input + prompt + model → reuse; do not `--force` unless intentional.

```bash
veramynd-parser artifact-status
veramynd-parser artifact-register --lessons-dir output/stage1/lessons --out output/normalize
```

## Chunks (`chunks/`)

| Path | Role |
|------|------|
| `by_lesson/*.json` | Per-lesson bundle: lesson + instructional + evidence pointers |
| `chunk_manifest.json` | Counts + strategy summary |
| `chunk_progress.json` | Status sidecar |

Hierarchy: **lesson** (normalize competency text) → **instructional** (Stage-1 block steps) → **evidence_pointer** (join metadata; quote string-match inside block).

## Embeddings (`embeddings/` + Qdrant)

| Path | Role |
|------|------|
| `embed_manifest.json` | Model, dims, collection, counts |
| `embed_progress.json` | Status sidecar |
| `.qdrant_data/` (package root) | Local Qdrant store when `QDRANT_URL` unset |

Default: OpenAI **`text-embedding-3-large`** (3072-d, Cosine) → collection `veramynd_chunks`.
Standards: same model → collection `veramynd_standards` (`embed-standards`).

## Judge (`judge/`)

Live prompt: [`../veramynd_parser/prompts/assembled_judge_prompt.md`](../veramynd_parser/prompts/assembled_judge_prompt.md)
(engine + GA Grade 1 overlay). `align_judge.v1.1` / `align_judge_v1.md` is unused.

Gold eval is always `--limit 25` on `output/retrieve_gold4/` (do not retune
retrieve). After the retrieve shortlist, a coverage pass may append
feedback/present codes that missed top 25 (`coverage_pass_injected` in the
JSON). Close-read rows that cite a missing Read-aloud Guide get
`input_scope_caveat` — scores are likely understated; **do not hand-edit
labels**. Re-run those lessons only if the client shares the guides.

| Artifact | Honest status |
|----------|----------------|
| Gold-4 overall | Assembled Anthropic batch `--limit 25` — **16/20 (80%)** unique 3-class |
| `G1M2U1L1.json` | **6/7** — miss `1.P.EICC.4.c` (gold full / json partial) |
| `G1M2U1L3.json` | **4/5** — miss `1.T.SS.2.a` (gold partial / json none); P4 caveats |
| `G1M2U1L6.json` | **5/7** — miss `1.L.V.3.a` (gold partial / json full), `1.T.T.1.c` (gold partial / json none); P4 caveats; coverage `1.P.CP.2.a` |
| `G1M2U3L5.json` | **1/1**; coverage `1.P.EICC.4.f`, `1.P.CP.1.c`, `1.P.CP.2.a` |

```bash
veramynd-parser judge-standards \
  --retrieve-file output/retrieve_gold4/G1M2U1L1.json \
  --lesson-file output/stage1/lessons/G1M2U1L1.json \
  --standards-dir output/normalize_standards \
  --out output/judge/G1M2U1L1.json \
  --limit 25 --no-cache
# opt out of coverage extras: --no-coverage-pass
```

## Reports (`reports/`)

CSV/HTML from `report-alignments`. Columns include `needs_review`,
`coverage_pass`, and `input_scope_caveat`. Per-lesson judge CSVs (no
retrieve scores, with `page`): `G1M2U1L1_judge.csv`, `G1M2U1L3_judge.csv`,
`G1M2U1L6_judge.csv`, `G1M2U3L5_judge.csv` (and `*_judge_aligned.csv` for
full+partial only). All four gold JSON files are the live assembled run.

```bash
veramynd-parser report-alignments --judge-dir output/judge --out output/reports/gold4_alignments.csv
```

## Regenerate

```bash
# Stage 1 (default --out is output/stage1)
veramynd-parser export <guide.pdf> --out output/stage1 --standards <stds.xlsx> --expect 40

# ELA normalize (only after GO)
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize

# Hierarchical chunks (no LLM)
veramynd-parser chunk-lessons output/stage1/lessons --normalize-dir output/normalize --out output/chunks

# Embed + Qdrant upsert (lessons)
pip install -e '.[embed]'
veramynd-parser embed-chunks output/chunks --out output/embeddings --recreate

# Embed + Qdrant upsert (standards)
veramynd-parser embed-standards output/normalize_standards --out output/embeddings --recreate

# Smoke: lesson chunk → nearest GA standards
veramynd-parser smoke-retrieve-standards --chunk-file output/chunks/by_lesson/G1M2U2L1.json --family lesson
```
