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
guide + Georgia Grade 1 ELA standards. It is **not** a finished product: there is no
gold-set evaluation gate yet, the agentic/graph track is design-only, and production
packaging (hosted Qdrant compose in-tree, eval harness, multi-publisher hardening) is
still open.

| Stage | Status | Location |
|---|---|---|
| **Parse & verify** — teacher-guide PDF → structured lessons; standards spreadsheet → grade tree; layered safety-net verifier | **Implemented** | [`veramynd_parser/`](veramynd_parser/) |
| **Pedagogical normalize (lessons)** — distill each lesson into what the student does, evidence-backed | **Implemented** | [`veramynd_parser/veramynd_parser/normalize/`](veramynd_parser/veramynd_parser/normalize/) |
| **Standards normalize** — retrieval-ready standard leaves (`embed_text`) | **Implemented** | [`normalize/standard.py`](veramynd_parser/veramynd_parser/normalize/standard.py) |
| **Chunk** — hierarchical lesson / instructional / evidence-pointer bundles | **Implemented** | [`chunk/`](veramynd_parser/veramynd_parser/chunk/) |
| **Embed → Qdrant** — OpenAI dense vectors for chunks + standards | **Implemented** | [`embed/`](veramynd_parser/veramynd_parser/embed/) |
| **Hybrid retrieve + rerank** — dense + BM25 → RRF → cross-encoder | **Implemented** | [`retrieve/`](veramynd_parser/veramynd_parser/retrieve/) |
| **Alignment judge + grounding** — LLM rubric; ungrounded claims rejected | **Implemented** | [`judge/`](veramynd_parser/veramynd_parser/judge/) |
| **Report** — CSV + HTML audit dashboard | **Implemented** | [`report/`](veramynd_parser/veramynd_parser/report/) |
| **Gold-set eval harness** — expert-labeled pairs, recall/accuracy gates | **Not built** | Designed in [`docs/architecture.md`](docs/architecture.md) §16 (`eval/` not in repo yet) |
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

**4. Retrieve → judge → report.** Hybrid retrieval proposes candidates; the judge
scores `full` / `partial` / `none` with grounded evidence; CSV/HTML reports export
the audit trail.

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
veramynd-parser embed-standards output/normalize_standards --out output/embeddings --recreate
veramynd-parser retrieve-standards --chunk-file output/chunks/by_lesson/G1M2U1L3.json --out output/retrieve/G1M2U1L3.json
veramynd-parser judge-standards --retrieve-file output/retrieve/G1M2U1L3.json \
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
