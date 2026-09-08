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
**publisher- and framework-agnostic** via acts + meaning and shared structural
patterns — **not** a per-publisher `if Success for All / elif Publisher B` tree.

| Proof point | Status |
|---|---|
| Batch-1 EL → normalize → retrieve (gold R@25) | **Locked** |
| Batch-1 gold-4 judge vs SME (live assembled prompt `v1.1`) | **Measured** — **20/20 (100%)** 3-class exact on judged unique pairs. vs corrected master (4-lesson overlap): **95/102 (93.1%)**. Prior OpenAI `align_judge.v1.1`: 18/19 exact (94.7%) |
| Batch-1 all 40 EL lessons retrieve → judge (top 25) | **Run** — `output/retrieve/` (50-standard shortlist) + `output/judge/` + per-lesson CSVs in `output/result/`. SME exact is gold-4 only |
| Second publisher / Shared Story Stage-1 | **Not in this tree** — samples are EL G1M2 + GA ELA only |
| Any PDF / any publisher / any grade with zero pattern work | **Not claimed** |

**Batch-1 retrieve (live, enterprise defaults)** — 4 gold lessons
(`G1M2U1L1`, `U1L3`, `U1L6`, `U3L5`), **20** FULL+PARTIAL positives
(`docs/_ga_g1_module2_goldset.md`; gold is **eval-only**, never used in ranking):

| Metric | Result | Role |
|---|---|---|
| **Recall@25** | **100% (20/20)** | Protected QA bar (do not tune retrieve to hide normalize/parser regressions) |
| **Recall@20** | **90% (18/20)** | Product cut → judge shortlist |
| **Recall@50** | **100% (20/20)** | SME / diagnostic shortlist |
| Recall@30 | 100% (20/20) | — |
| Recall@10 | 35% (7/20) | Head precision still open |

Residual @20 (all still ≤25): L3 `1.P.CP.2.d`, L6 `1.P.EICC.3.f`.
Gold **none** rows outside top 25 do **not** count against R@25.

**Batch-1 judge (gold-4, live `prompts/assembled_judge_prompt.md` `v1.1`)** — engine +
GA Grade 1 overlay (SME fences F1–F20, R3 supplemental cap; publisher-agnostic
principles with GA worked instances). Gold eval is always `--limit 25` (do not
retune retrieve to hide judge misses). Anthropic Sonnet batch + **Opus
escalate-batch** (one call for all borderline codes; pair fallback if that
batch fails); default `max_tokens` 16384. Short exact evidence quotes expand to
a grounded window when needed. A coverage pass after top 25 can still judge
activity-driven feedback/present codes. Close-read comprehension can be
understated until Read-aloud Guides are in Stage-1 (`input_scope_caveat`; do
not hand-edit labels).

| Metric | Result |
|---|---|
| **3-class exact** (unique pairs, judged shortlist + coverage pass) | **20/20 (100%)** |
| vs corrected master (4-lesson overlap) | **95/102 (93.1%)** |
| Binary precision / recall (pos = full\|partial) | **100%** / **100%** |
| Per lesson (SME) | L1 **7/7**, L3 **5/5**, L6 **7/7**, U3L5 **1/1** |
| Unjudged gold | L1 + L3 `1.P.EICC.4.e` (gold none, outside top 25) |
| Prior OpenAI `align_judge.v1.1` (unused) | **18/19 (94.7%)** 3-class exact |

All **40** EL G1M2 lessons have live assembled verdicts (`--limit 25`); SME exact is **gold-4 only**. Multi-publisher through judge is **not** claimed. Agentic/graph track is design-only.

**Locked pipeline (current — no lesson chunking):**

```text
Teacher Guide PDF + Standards XLSX
  → Stage-1 parse / verify (GO / BLOCK)
  → normalize-lessons + normalize-standards
  → embed-standards → Qdrant veramynd_standards
  → retrieve (multi_normalize_focused from NormalizedLesson)
  → judge (assembled v1.1 + Stage-1 raw grounding)
  → report / client-correlation
```

- Lesson normalize **`normalize_ela.v2.3`** + `repair-normalized` sanitizers
- Retrieve builds query arms from **normalize** (not stored lesson embeddings);
  query text is embedded **on the fly** for dense search
- Standards only live in Qdrant (`veramynd_standards`); there is no
  `chunk-lessons` / `embed-chunks` / `veramynd_chunks`
- Funnel: competency bridges → per-query dense+BM25 RRF → merge (`top_k_sum`) →
  local CE → shortlist fusion; rescue slots **off**
- Flow diagrams: [`docs/diagrams/flow/`](docs/diagrams/flow/)

| Stage | Status | Location |
|---|---|---|
| **Parse & verify (PDF)** — Docling primary · PyMuPDF bookmarks/fallback · GO/BLOCK | **Implemented (EL Batch-1 locked)** | [`veramynd_parser/`](veramynd_parser/) |
| **Parse (standards)** — `Code \| Standard Text \| Notes`; hierarchy from dotted grade-prefixed codes | **Implemented (GA validated)** | [`standards/spreadsheet.py`](veramynd_parser/veramynd_parser/standards/spreadsheet.py) |
| **Pedagogical normalize (lessons)** — `normalize_ela.v2.3` + sanitize / `repair-normalized` | **Implemented** (Batch-1 locked) | [`normalize/`](veramynd_parser/veramynd_parser/normalize/) |
| **Standards normalize** — retrieval-ready leaves (`embed_text`) | **Implemented** | [`normalize/standard.py`](veramynd_parser/veramynd_parser/normalize/standard.py) |
| **Embed → Qdrant** — leaf-only standards + rich retrieval text (`veramynd_standards`) | **Implemented** | [`embed/`](veramynd_parser/veramynd_parser/embed/) |
| **Hybrid retrieve + rerank** — `multi_normalize_focused` competency funnel | **Implemented (Batch-1 R@25/R@50 met)** | [`retrieve/`](veramynd_parser/veramynd_parser/retrieve/) |
| **Alignment judge + grounding** — assembled prompt `v1.1`; ungrounded quotes → `none`; Opus escalate-batch | **Implemented** (gold-4: **20/20**; vs master **95/102**; all 40 EL judged) | [`judge/`](veramynd_parser/veramynd_parser/judge/), [`prompts/assembled_judge_prompt.md`](veramynd_parser/veramynd_parser/prompts/assembled_judge_prompt.md) |
| **Report** — CSV + HTML + client DOCX/XLSX | **Implemented** | [`report/`](veramynd_parser/veramynd_parser/report/), `output/reports/`, `output/result/` |
| **Gold-set metrics** — leaf recall @k + judge exact vs SME | **Retrieve locked; assembled gold-4 20/20 (100%)** | gold: [`docs/_ga_g1_module2_goldset.md`](docs/_ga_g1_module2_goldset.md) |
| **Agentic + standards-graph track** | **Design only** | [`docs/architecture-agentic-graph.md`](docs/architecture-agentic-graph.md) |

## How it works

**1. Parse (PDF).** Separate lessons (PyMuPDF bookmarks → font-header fallback),
then divide each lesson (Docling labels primary · PyMuPDF font tiers fallback)
into agenda / materials / vocab / instructional blocks + steps with page
provenance. Docling parses are content-addressed cached.

**2. Parse (standards).** Expects `Code | Standard Text | Notes`. Hierarchy comes
from **dotted grade-prefixed codes** (e.g. `1.F.PA.4.d`); Notes are ignored for
level. Output: `GradeStandards` tree → `standards.json`.

**3. Verify.** Teacher-guide safety net emits **GO / BLOCK** (soft WARN still
allows GO). Only **GO** unlocks trusted `lessons/` for normalize unless
explicitly overridden (`--allow-unverified` / `--allow-block`).

**4. Normalize → embed standards.** Lessons → standards-agnostic
`NormalizedLesson`; standards leaves → retrieval-ready `embed_text`. Sanitizers
re-apply literacy signals from Stage-1 after LLM normalize. **Only standards**
are upserted into Qdrant (`text-embedding-3-large`, collection
`veramynd_standards`). Lesson query vectors are **not** stored.

**5. Retrieve → judge → report.** Build focused query arms from **normalize**
(`multi_normalize_focused`) → embed query text on the fly → dense+BM25 → RRF →
CE → fused shortlist (`judge_shortlist_k=50`, product cut **top-20**, protected
bar **Recall@25**). Judge (assembled engine + overlay) scores
`full` / `partial` / `none` from **student acts** in Stage-1 raw text;
ungrounded quotes become `none`. Coverage pass can add feedback/present codes
after top 25. CSV/HTML + client DOCX/XLSX export the audit trail
(`output/reports/`, `output/result/`).

## Design principles

- **Fail loud, never silently.** Structural problems block the pipeline.
- **Pattern-based publishers, not name switches.** Prefer shared heading /
  section signals over `if publisher == "…" / elif …` trees.
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

# Standards-only parse
veramynd-parser stds "../data/samples/Grade 1 GA ELA Standards.xlsx" \
  --framework "GA ELA" --json output/stage1/standards.json

pytest
# Protected recall bar (gold4 artifacts):
python -m veramynd_parser.scripts.eval_r20          # includes R@25
python -m veramynd_parser.scripts.phase8_regression # GA GO + R@25 gate
```

Downstream (needs OpenAI key for normalize/embed; Anthropic key for live judge):

```bash
pip install -e '.[normalize,embed,retrieve,judge]'
cp .env.example .env               # set OPENAI_API_KEY — never commit .env

veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize
veramynd-parser normalize-standards output/stage1/standards.json --out output/normalize_standards
veramynd-parser embed-standards output/normalize_standards --out output/embeddings --recreate

# Single-query hybrid (CLI) or enterprise multi-query batch:
veramynd-parser retrieve-standards --normalize-file output/normalize/G1M2U1L3.json --out output/retrieve/G1M2U1L3.json

# After normalize changes: re-apply sanitizers without a full LLM re-run
veramynd-parser repair-normalized output/stage1/lessons --normalize-dir output/normalize

# Batch-1 gold retrieve (live: R@25=100%, R@20=90%, R@50=100%)
# Gold list: docs/_ga_g1_module2_goldset.md (FULL+PARTIAL = positives)
python -m veramynd_parser.scripts.batch_align_all \
  --retrieve-dir output/retrieve \
  --diag-dir output/reports/retrieve_diag_gold4 \
  --from-gold output/reports/gold_set_batch1_from_md.jsonl \
  --judge-shortlist-k 50 \
  --skip-judge --skip-report --force-retrieve
python -m veramynd_parser.scripts.eval_r20

# Gold-4 judge (limit 25 = protected shortlist). Assembled prompt is live.
# Set JUDGE_MODEL / ANTHROPIC_API_KEY in .env (claude-sonnet-4-5 + opus escalate).
# --no-cache after prompt/parser changes; extra judge cost if coverage pass injects.
veramynd-parser judge-standards --retrieve-file output/retrieve/G1M2U1L1.json \
  --lesson-file output/stage1/lessons/G1M2U1L1.json \
  --standards-dir output/normalize_standards --out output/judge/G1M2U1L1.json \
  --limit 25 --no-cache
veramynd-parser report-alignments \
  --judge-file output/judge/G1M2U1L1.json \
  --judge-file output/judge/G1M2U1L3.json \
  --judge-file output/judge/G1M2U1L6.json \
  --judge-file output/judge/G1M2U3L5.json \
  --out output/reports/gold4_alignments.csv
# Per-lesson CSVs for the full 40-lesson run:
veramynd-parser report-alignments --judge-dir output/judge --out output/result/alignments.csv --no-html
```

Partial embeds (`--resource-id` / `--code`) refresh only those standards points.
`--recreate` rebuilds the embedding index for the requested scope; if no scope
is specified, it rebuilds the entire `veramynd_standards` collection (a filtered
run never deletes the rest of the collection).

**Incremental by default / force for maintenance:** day-to-day embed runs skip
unchanged Qdrant `content_hash` values. Use `--force` (and embed `--recreate`
when rebuilding) for full recomputation after a model/schema change. See
[`veramynd_parser/README.md`](veramynd_parser/README.md).

## Repository map

```
veramynd/
├── README.md / LICENSE
├── docs/                       # design & flow documentation
├── data/samples/               # reference PDF + standards spreadsheet
├── dashboard/                  # FastAPI read-only API + projects.json
├── dashboard-ui/               # React (Vite) Overview / Curriculum / Standards / Alignments
├── _archive/                   # non-production one-offs (do not import)
└── veramynd_parser/            # installable package + CLI
    ├── veramynd_parser/        # library (pdf/, normalize/, embed/, …)
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
| [docs/diagrams/flow/](docs/diagrams/flow/) | Current locked pipeline PNGs (regenerate via `build_deep_flow.py`) |
| [docs/flow.md](docs/flow.md) | Pipeline narrative (prefer this README + diagrams for status) |
| [docs/architecture.md](docs/architecture.md) | Product design history + gold-set / roadmap (may lag code) |
| [docs/architecture-agentic-graph.md](docs/architecture-agentic-graph.md) | Parallel agentic design (not coded) |
| [docs/complete-project-flow.md](docs/complete-project-flow.md) | Deep onboarding walkthrough |
| [veramynd_parser/README.md](veramynd_parser/README.md) | Install, CLI reference, package layout |
| [veramynd_parser/output/README.md](veramynd_parser/output/README.md) | Artifact layout under `output/` |
| [dashboard/README.md](dashboard/README.md) | FastAPI dashboard API + project registry |
| [dashboard-ui/README.md](dashboard-ui/README.md) | React UI (run Overview at :5173) |

## Requirements

- Python >= 3.11
- Primary path: Docling + PyMuPDF + openpyxl + pydantic
- Lite path (no Docling): `pip install -e '.[lite]'`, then `Config(engine="pymupdf")`
- Embed / retrieve: OpenAI API key + optional `sentence-transformers` for rerank
- Judge: Anthropic (`claude-*` + `ANTHROPIC_API_KEY`) is the live gold-4 path; OpenAI (`gpt-*`) still works if `JUDGE_MODEL` is a GPT id

## License

MIT — see [LICENSE](LICENSE).
