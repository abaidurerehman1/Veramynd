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

## What's implemented

| Stage | Status | Location |
|---|---|---|
| **Parse & verify** — turn a teacher-guide PDF into structured lessons, parse a standards spreadsheet into a grade-indexed tree, and pass both through a layered safety-net verifier | **Implemented** | [`veramynd_parser/`](veramynd_parser/) |
| **Pedagogical normalization** — distill each parsed lesson into what the student actually does, standards-agnostic, evidence-backed | **Implemented** | [`veramynd_parser/veramynd_parser/normalize/`](veramynd_parser/veramynd_parser/normalize/) |
| **Retrieval, alignment judge, reporting** | Designed, not built | [`docs/architecture.md`](docs/architecture.md) |

## How it works

**1. Parse.** The teacher guide is an untagged PDF, so lesson structure has to be
recovered from the document's own signals, not markup. Two independent PDF engines
run against each other:

- **Docling** (primary) — layout analysis and table-structure recovery. Produces
  semantically labeled elements (headings, list items, tables) with page provenance.
- **PyMuPDF** (outline + fallback) — reads the PDF's embedded bookmarks to find lesson
  boundaries, and independently re-derives each lesson's structure from font-size
  tiers as a lightweight, dependency-free path and a cross-check on Docling's output.

Every parse is content-addressed and cached, so a 440-page document parses once
(~100s) and is instant after.

**2. Verify.** No parsed lesson set is trusted until it clears a four-layer safety
net — separation integrity (page counts, contiguity, unique IDs), a cross-signal
check (does the running header on each lesson's first page agree with its bookmark?),
division completeness (are all required sections and instructional steps present?),
and cross-engine agreement (does PyMuPDF's independent read confirm every standard
code Docling reported?). A hard-check failure blocks the load outright rather than
silently shipping a corrupted parse.

**3. Normalize.** Each verified lesson is distilled by an LLM into a
standards-agnostic pedagogical record — what's taught, what the student does, and
verbatim evidence quotes for every claim — validated against a strict schema and
grounded against the real lesson text so a claim with no matching source quote is
either repaired against the real source or dropped, never fabricated.

## Design principles

- **Fail loud, never silently.** A structural problem blocks the pipeline with a
  clear reason; nothing downstream ever trusts data that hasn't passed verification.
- **Content-addressed caching**, not existence-based — a prompt or model change
  invalidates exactly the affected cached results, nothing more; a failed call is
  never cached as if it succeeded.
- **Evidence is mandatory and checked.** Every claim in the normalized output must be
  backed by a verbatim quote from the source lesson; quotes that can't be grounded
  are repaired against the real text or dropped, never left un-checked.
- **Two vocabularies, kept apart.** A teacher guide declares standards in one
  framework (e.g. CCSS codes like `RL.1.1`); the target standards spreadsheet may use
  another (e.g. state-specific codes). Veramynd preserves the publisher's *claim* and
  the target framework's tree side by side and never silently joins them.

See [`docs/architecture.md`](docs/architecture.md) for the full design spec, including
the roadmap for retrieval, the alignment judge, and reporting.

## Quick start

```bash
cd veramynd_parser
pip install -e '.[test]'          # Python >= 3.11

# Parse + verify a teacher guide (expects 40 lessons in this example)
veramynd-parser verify "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" --expect 40

# Parse a standards spreadsheet
veramynd-parser stds "../data/samples/Grade 1 GA ELA Standards.xlsx" --json output/stage1/standards.json

# Full export: lessons + standards + verification report
veramynd-parser export "../data/samples/ELA Grade 1 Module 2 Teacher Guide.pdf" \
  --out output/stage1 --expect 40 \
  --standards "../data/samples/Grade 1 GA ELA Standards.xlsx"

pytest
```

Pedagogical normalization (OpenAI only, resumable, cached):

```bash
pip install -e '.[normalize]'
cp .env.example .env               # set OPENAI_API_KEY — never commit .env
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize
```

## Repository map

```
veramynd/
├── README.md / LICENSE
├── docs/                       # design & flow documentation
├── data/samples/               # reference PDF + standards spreadsheet
├── _archive/                   # non-production one-offs (do not import)
└── veramynd_parser/            # installable package + CLI
    ├── veramynd_parser/        # library (pdf/, normalize/, chunk/, embed/, …)
    │   ├── prompts/            # runtime LLM prompts
    │   └── schemas/
    ├── tests/
    ├── examples/
    ├── output/                 # pipeline artifacts (local)
    ├── docker-compose.yml      # local Qdrant
    ├── .env.example
    ├── pyproject.toml
    └── requirements.lock
```

## Docs

| Doc | Use it for |
|---|---|
| [docs/flow.md](docs/flow.md) | How the implemented pipeline works end-to-end |
| [docs/architecture.md](docs/architecture.md) | Full product design, including unimplemented stages (hybrid RAG track) |
| [docs/architecture-agentic-graph.md](docs/architecture-agentic-graph.md) | Alternative design for Stages 2-7 — agentic + standards-graph, no vector DB (parallel track) |
| [docs/complete-project-flow.md](docs/complete-project-flow.md) | Deep onboarding walkthrough |
| [docs/lesson-segmentation.md](docs/lesson-segmentation.md) | Separation + division design detail |
| [docs/ingestion.md](docs/ingestion.md) | Ingestion pipeline detail |
| [veramynd_parser/README.md](veramynd_parser/README.md) | Install, CLI reference, package layout |
| [veramynd_parser/veramynd_parser/schemas/ela_schema_README.md](veramynd_parser/veramynd_parser/schemas/ela_schema_README.md) | Why each field in the normalized record is required |

## Requirements

- Python >= 3.11
- Primary path: Docling + PyMuPDF + openpyxl + pydantic
- Lite path (no Docling): `pip install -e '.[lite]'`, then `Config(engine="pymupdf")`

## License

MIT — see [LICENSE](LICENSE).
