# output/ — production pipeline artifacts

Do not commit secrets. This folder is **tracked in git** as a reference-run
snapshot of the Grade 1 Module 2 sample corpus — regenerating changes these
files, so keep committed snapshots deliberate.

Experimental retrieve variants, top50 dumps, and one-off report scripts live in
[`../../_archive/`](../../_archive/) — not here.

```text
output/
├── stage1/                 # Batch-1 EL G1M2 — parse + verify (GO, locked stack)
├── normalize/              # Batch-1 ELA normalize — schema 2.0-ela
├── normalize_standards/    # GA leaf normalize (shared by retrieve)
├── retrieve/               # all 40 EL + locked gold-4 shortlists (R@25 bar)
├── judge/                  # alignment verdicts (assembled prompt v1.1)
├── result/                 # per-lesson CSVs (G1M2U*.csv)
├── reports/                # gold metrics + client correlation DOCX/XLSX
└── embeddings/             # standards embed manifests (Qdrant veramynd_standards)
```

## Stage 1 (`stage1/`)

| Path | Role |
|------|------|
| `stage1/` | EL Module 2 — **Batch-1 locked** (40 lessons) |
| `verification_report.txt` | Human-readable GO / BLOCK report |
| `verification_verdict.json` | Machine-readable gate verdict — downstream commands check this |
| `lessons/*.json` | Per-lesson contracts (primary Stage 1 product) |
| `standards.json` | Standards tree from the XLSX |
| `teacher_guide.json` | Full guide parse (audit / reload) |
| `lessons_index.tsv` | Human-readable lesson summary |

## Normalize (`normalize/`)

| Path | Role |
|------|------|
| `*.json` | Per-lesson ELA curriculum-normalization records |
| `normalize_progress.json` | Resume / status sidecar |

**Reuse:** content-addressed LLM cache (`.normalize_cache/`) + versioned
**artifact registry**. Same Stage-1 input + prompt + model → reuse; do not
`--force` unless intentional.

## Embeddings (`embeddings/` + Qdrant)

Lesson chunks + `veramynd_chunks` embed manifests are archived under
`_archive/pipeline_experiments/chunks/` and `chunk_embeddings/`. Keep standards only:

| Path | Role |
|------|------|
| `embed_standards_manifest.json` | Standards collection upsert summary |
| `embed_standards_progress.json` | Status sidecar |
| `.qdrant_data/` / Qdrant URL | `veramynd_standards` vectors |

## Judge (`judge/`)

Live prompt: [`../veramynd_parser/prompts/assembled_judge_prompt.md`](../veramynd_parser/prompts/assembled_judge_prompt.md)
(engine + GA Grade 1 overlay `v1.1`). Legacy `align_judge_v1.md` is archived.

Gold eval uses `--limit 25` on `output/retrieve/` (gold-4 lesson files). Coverage pass may
append feedback/present codes. Close-read rows may carry `input_scope_caveat`
when Read-aloud Guides were not in the input — **do not hand-edit labels**.

| Artifact | Honest status |
|----------|----------------|
| All 40 EL lessons | Assembled Anthropic batch `--limit 25` |
| Gold-4 vs SME | **20/20 (100%)** 3-class exact (`v1.1`) |
| Gold-4 vs corrected master | **95/102 (93.1%)** |

## Reports (`reports/` and `result/`)

Keep production reports here:

- `GA_ELA_G1_Module2_client_correlation.docx` / `.xlsx` (+ `.summary.json`) — all-40 client ship
- `gold_set_batch1_from_md.jsonl`, `retrieve_gold_metrics.json` — gold-4 R@25 eval fixtures/metrics

Gold-4 reports, `reference_data/`, P3/P9 scratch live in
[`../../_archive/reports_scratch/`](../../_archive/reports_scratch/).

```bash
veramynd-parser report-alignments --judge-dir output/judge --out output/reports/gold4_alignments.csv

veramynd-parser client-correlation \
  --judge-dir output/judge \
  --standards output/stage1/standards.json \
  --lessons-dir output/stage1/lessons \
  --out-docx output/reports/GA_ELA_G1_Module2_client_correlation.docx \
  --out-xlsx output/reports/GA_ELA_G1_Module2_client_correlation.xlsx
```
## Regenerate

```bash
veramynd-parser export <guide.pdf> --out output/stage1 --standards <stds.xlsx> --expect 40
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize
veramynd-parser embed-standards output/normalize_standards --out output/embeddings
```
