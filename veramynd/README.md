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

This repo is a **working end-to-end pipeline** for the reference EL Education G1M2
teacher guide + Georgia Grade 1 ELA standards. Retrieve for Batch-1 gold now meets
the **product shortlist bar** (judge/operator cut = top-20):

**Batch-1 retrieve (live, enterprise defaults)** — 4 gold lessons
(`G1M2U1L1`, `U1L3`, `U1L6`, `U3L5`), **20** FULL+PARTIAL positives
(`docs/_ga_g1_module2_goldset.md`; gold is **eval-only**, never used in ranking):

| Metric | Result | Role |
|---|---|---|
| **Recall@20** | **90% (18/20)** | Product cut → judge shortlist |
| **Recall@50** | **100% (20/20)** | SME / diagnostic shortlist |
| Recall@30 | 100% (20/20) | — |
| Recall@10 | 35% (7/20) | Head precision still open |

Remaining misses @20 (both still in top 30): `1.P.CP.2.d` (U1L3) and
`1.P.EICC.3.f` (U1L6). Multi-grade / multi-publisher scale-up and ~90% judge
agreement vs SME labels are **not** claimed yet. The agentic/graph track is
design-only.

**Retrieve design (current defaults):** multi-query competency bridges from
lesson text → per-query dense+BM25 RRF → multi-arm merge (`top_k_sum`,
`top_arms=3`, `max_blend=1.0`) → local CE → shortlist fusion with RRF head lock
(1–12) + mild mid-list CE dual-agreement polish (`mid_ce_boost=3`,
`mid_ce_max=26`). Rescue slots / arm–skill–domain priors off by default.
Artifacts: `output/retrieve_gold4/`, Liz package
`output/reports/liz_top50_review/`, eval `output/reports/_eval_r20.py`.

| Stage | Status | Location |
|---|---|---|
| **Parse & verify** — teacher-guide PDF → structured lessons; standards spreadsheet → grade tree; layered safety-net verifier | **Implemented** | [`veramynd_parser/`](veramynd_parser/) |
| **Pedagogical normalize (lessons)** — distill each lesson into what the student does, evidence-backed | **Implemented** | [`veramynd_parser/veramynd_parser/normalize/`](veramynd_parser/veramynd_parser/normalize/) |
| **Standards normalize** — retrieval-ready standard leaves (`embed_text`) | **Implemented** | [`normalize/standard.py`](veramynd_parser/veramynd_parser/normalize/standard.py) |
| **Chunk** — hierarchical lesson / instructional / evidence-pointer bundles | **Implemented** | [`chunk/`](veramynd_parser/veramynd_parser/chunk/) |
| **Embed → Qdrant** — leaf-only standards + rich retrieval text; chunk vectors | **Implemented** | [`embed/`](veramynd_parser/veramynd_parser/embed/) |
| **Hybrid retrieve + rerank** — multi-query competency funnel, max-blend merge, CE, mid-CE shortlist fusion | **Implemented (Batch-1 R@20/R@50 bar met)** | [`retrieve/`](veramynd_parser/veramynd_parser/retrieve/) |
| **Alignment judge + grounding** — LLM rubric; ungrounded claims rejected | **Implemented** | [`judge/`](veramynd_parser/veramynd_parser/judge/) |
| **Report** — CSV + HTML audit dashboard | **Implemented** | [`report/`](veramynd_parser/veramynd_parser/report/) |
| **Gold-set metrics** — leaf recall @k + SME review package | **Partial** | gold: [`docs/_ga_g1_module2_goldset.md`](docs/_ga_g1_module2_goldset.md); [`retrieve/gold_metrics.py`](veramynd_parser/veramynd_parser/retrieve/gold_metrics.py); Liz CSVs under `output/reports/liz_top50_review/` |
| **Agentic + standards-graph track** — alternate Stages 2–7 (no vector DB) | **Design only** | [`docs/architecture-agentic-graph.md`](docs/architecture-agentic-graph.md) |

## How it works

**1. Parse.** The teacher guide is an untagged PDF, so lesson structure is recovered
from the document's own signals. Two PDF engines run against each other:

- **Docling** (primary) — layout analysis and table-structure recovery.
- **PyMuPDF** (outline + fallback) — bookmarks for lesson boundaries, font-tier
  cross-check, and verifier input.

**2. Verify.** Hard checks block a bad load (separation, headers, division,
cross-engine standards). Soft checks flag review without blocking `GO`.

**3. Normalize → chunk → embed.** Lessons and standards become retrieval-ready text;
chunks land in Qdrant (`text-embedding-3-large`).

**4. Retrieve → judge → report.** Leaf-only standards index. Enterprise multi-query
retrieve: lesson-driven query arms (targets, skills, **competency bridges**) →
per-query dense+BM25 → RRF → multi-arm merge (`top_k_sum` + depth `max_blend`) →
local CE → fused shortlist (`judge_shortlist_k=50`, product cut **top-20**).
The judge scores `full` / `partial` / `none` with grounded evidence; CSV/HTML
reports export the audit trail.

## Design principles

- **Fail loud, never silently.** Structural problems block the pipeline.
- **Content-addressed caching** for Docling parses and LLM normalizations.
- **Evidence is mandatory and checked** — fabricated quotes are rejected.
- **Two vocabularies, kept apart** (publisher claims vs target framework codes).

## Quick start

```bash
cd veramynd_parser
pip install -e '.[test]'          # Python >= 3.11

# Parse + verify (expects 40 lessons for the sample guide)
veramynd-parser verify "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" --expect 40

# Full Stage-1 export
veramynd-parser export "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" \
  --out output/stage1 --expect 40 \
  --standards "../data/samples/Grade 1 GA ELA Standards.xlsx"

pytest
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

# Batch-1 gold lessons (enterprise defaults: R@20≈90%, R@50=100% on live re-run)
# Gold list: docs/_ga_g1_module2_goldset.md (FULL+PARTIAL = positives)
python -m veramynd_parser.scripts.batch_align_all \
  --retrieve-dir output/retrieve_gold4 \
  --diag-dir output/reports/retrieve_diag_gold4 \
  --only G1M2U1L1 --only G1M2U1L3 --only G1M2U1L6 --only G1M2U3L5 \
  --skip-judge --skip-report --force-retrieve
python output/reports/_eval_r20.py

# Optional SME package (rank, code, official standard raw_text only)
python output/reports/_export_liz_top50.py

veramynd-parser judge-standards --retrieve-file output/retrieve_gold4/G1M2U1L3.json \
  --lesson-file output/stage1/lessons/G1M2U1L3.json \
  --standards-dir output/normalize_standards --out output/judge/G1M2U1L3.json
veramynd-parser report-alignments --judge-file output/judge/G1M2U1L3.json --out output/reports/alignments.csv
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
- Embed / retrieve / judge: OpenAI API key + optional `sentence-transformers` for rerank

## License

MIT — see [LICENSE](LICENSE).
