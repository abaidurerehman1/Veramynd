# output/ — production pipeline artifacts

Do not commit secrets. This folder is gitignored.

```text
output/
├── stage1/                 # Stage 1 — parse + verify + export (trusted on GO)
│   ├── verification_report.txt
│   ├── teacher_guide.json
│   ├── lessons_index.tsv
│   ├── standards.json
│   └── lessons/            # one JSON file per lesson
├── normalize/              # ELA curriculum normalize (OpenAI) — schema 2.0-ela
├── chunks/                 # hierarchical chunks for grounding / judge
└── embeddings/             # embed run manifest (vectors live in Qdrant)
```

## Stage 1 (`stage1/`)

| Path | Role |
|------|------|
| `verification_report.txt` | GO / BLOCK gate — required before trusting anything else |
| `lessons/*.json` | Per-lesson contracts (primary Stage 1 product) |
| `standards.json` | Standards tree from the XLSX |
| `teacher_guide.json` | Full guide parse (audit / reload) |
| `lessons_index.tsv` | Human-readable lesson summary |

## Normalize (`normalize/`)

| Path | Role |
|------|------|
| `*.json` | Per-lesson ELA curriculum-normalization records |
| `normalize_progress.json` | Resume / status sidecar |

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
