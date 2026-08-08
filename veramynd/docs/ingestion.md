# Veramynd — Document Ingestion & Chunking Architecture

**Scope:** the offline pipeline that turns raw instructional documents into a
structured, linked, queryable knowledge base — the foundation every downstream
stage (normalization, retrieval, the alignment judge) stands on.

**Status:** Historical design — largely superseded by the shipped code. The
implemented ingestion path is Stage-1 export → normalize → chunk → **Qdrant**
embed (see [pipeline-review.md](pipeline-review.md)); the format-router /
graph-loader / Postgres design below was not built. Companion to
[architecture.md](architecture.md) §5–§8, §12.
**Last updated:** 20 July 2026

---

## 0. Ground truth — what the real documents actually are

This design is not written against an idealized PDF. It is written against the
two documents in the repository, inspected byte-for-byte first. **Every decision
below traces to something observed in these files.** That discipline is the whole
difference between a parser that works on one book and one that generalizes.

### 0.1 `ELA Grade 1 Module 2 Teacher Guide.pdf`

| Property | Observed | Consequence for the design |
|---|---|---|
| Publisher / tool | EL Education, produced by **Adobe InDesign** | Consistent, template-driven layout — font hierarchy is reliable |
| Pages | **440** | Big enough that serial page work is too slow (§13) |
| Tagged PDF? | **No** (`Tagged: no`) | No logical structure tree — we recover structure from **layout**, not markup |
| Outline / bookmarks | **43 entries**, complete | Lesson boundaries are *free and exact* here (§5) |
| Bookmark codes | `G1M2U1L1` … | Machine-parseable **grade/module/unit/lesson** — parse once, index forever |
| Structure | 3 units → **40 lessons** (15 / 12 / 13) + 3 unit overviews | Two nesting levels above the lesson |
| Running header | `Grade 1: Module 2: Unit 1: Lesson 1`, recto pages | Per-page **provenance** + a corroborating boundary signal |
| Font hierarchy | 13 pt `MarkPro-Heavy` / 11 pt / 9.5 pt-bold `MercuryTextG2` | Three tiers → section / sub-section / run-in label (§6) |
| Per-lesson standards | Each lesson prints a **`CCS Standards`** block | The publisher's *claim* of alignment — a prior and an eval signal, **not** ground truth |
| Bullet glyph | `\x84` (private-use, MarkPro) | Must be normalized out during text extraction |

### 0.2 `Grade 1 GA ELA Standards.xlsx`

| Property | Observed | Consequence |
|---|---|---|
| Shape | 1 sheet, **188 standard rows**, 3 columns (`Code`, `Standard Text`, `Notes`) | Small, clean, fully in memory |
| Hierarchy | dotted codes: **4 domains → 14 big ideas → 35 standards → 135 substandards** | A tree, encoded entirely in the code string |
| `Notes` (level) column | **empty on 183 of 188 rows** | **The obvious field is a trap.** Derive level from code **dot-depth**, never from `Notes` |
| Domains | `1.F` Foundations · `1.P` Practices · `1.L` Language · `1.T` Texts | Georgia's own framework |
| Known edge case | *"GC.1 substandards use numbers instead of letters"* (noted in the data) | Substandard parsing can't assume `[a-z]` suffixes |

### 0.3 The finding that shapes everything downstream

> The teacher guide declares **CCSS** codes (`RL.1.1`, `W.1.8`, `SL.1.1a`).
> The target framework is **Georgia** codes (`1.F.PA.4.d`).
> **They do not overlap.** `RL.1.1` does not exist in the GA sheet.

You **cannot** join a lesson to a standard on the code. The two documents speak
different vocabularies by design. This is not a data-cleaning problem to be
smoothed over in ingestion — it is the reason the alignment judge exists, and the
reason the Knowledge Graph crosswalk (CCSS ↔ GA) matters. **The ingestion layer's
job is to preserve both vocabularies faithfully and link them explicitly, never to
collapse one into the other.** (See the link graph, §12.)

### 0.4 The teacher guide *is* the lessons — v1 has two inputs, not three

Worth stating plainly, because the naming invites confusion. The **teacher guide is
the source of lessons**: the 40 lessons the product aligns (`G1M2U1L1` … `G1M2U3L13`)
are the units *inside* this one PDF, each a fully structured lesson (§5–§6). There is
no separate "lessons" file.

| v1 input | Role | Yields |
|---|---|---|
| **Teacher Guide** `.pdf` | the published curriculum | **the 40 lessons** — the unit the judge operates on |
| **Standards** `.xlsx` | the target framework | the GA standards to align against |

A *lesson plan* — a teacher's own authored/adapted document — is a **different
artifact**, not a second copy of the lessons, and is **out of scope for v1** (§10).
Everywhere below, "lesson" means a lesson extracted from the teacher guide.

---

## 1. Design principles

1. **Structure is recovered, then preserved — never invented.** We read the
   document's own signals (outline, fonts, headers) and carry them, with
   provenance, all the way to storage. A chunk always knows its page and bbox.
2. **Every stage is a pure function: artifacts in, artifacts out.** Same rule as
   the main spec — testability, caching and parallelism fall out of it.
3. **One canonical model; format-specific code lives only in adapters.** The
   pipeline downstream of the adapter is blind to whether the source was PDF,
   Excel, or Word.
4. **The claim and the evidence are different edges.** What a document *asserts*
   (declared standards) is stored separately from what is *proven* (a judge
   verdict backed by a quote). Never let one masquerade as the other.
5. **Fail loud, cache correct, resume cheap.** An error is a typed, quarantined
   artifact — never a silently-cached empty result (iter_1's defining defect).
6. **Extensibility is a seam, not a rewrite.** A new document type is one new
   adapter that emits the canonical model.

---

## 2. Pipeline overview

![Master ingestion pipeline: sources flow through a format router into typed parser adapters, a canonical document model, structure recognition, semantic segmentation, chunking, metadata enrichment, and a graph loader into Postgres](diagrams/10-ingestion-pipeline.svg)

*Figure 10 — The ingestion pipeline. Offline, once per document, content-addressed.
The two segmentation steps that the rest of this document zooms into are ④ (lesson
boundaries, Fig. 12) and its intra-lesson counterpart (Fig. 13).*

Seven stages, each a pure function with a typed input and output:

| # | Stage | In → Out | Responsibility |
|---|---|---|---|
| ① | Format Router | `bytes` → `AdapterId` | Classify by MIME + magic bytes; dispatch |
| ② | Parser Adapter | `bytes` → `CanonicalDoc` | Format-specific extraction (the *only* format-aware code) |
| ③ | Structure Recognizer | `CanonicalDoc` → `HeadingTree` | Recover the heading hierarchy from fonts + outline |
| ④ | Semantic Segmenter | `HeadingTree` → `Lesson[]` | Split into lessons (§5) and intra-lesson blocks (§6) |
| ⑤ | Chunker | `Lesson[]` → `Chunk[]` | Structure-aware, hierarchical chunking (§7) |
| ⑥ | Enricher + Normalizer | `Chunk[]` → `EnrichedChunk[]` | Codes, grade, timing, standard tags; typed contract |
| ⑦ | Graph Loader | `EnrichedChunk[]` → nodes + edges | Upsert by content hash into Postgres + pgvector |

---

## 3. Format routing & the adapter seam (extensibility)

![Format router dispatching to PDF, Spreadsheet, Lesson-Plan and a pluggable new adapter, all emitting one canonical model](diagrams/11-format-router.svg)

*Figure 11 — The extensibility seam. Adding a document type is one adapter; nothing
downstream changes.*

The router classifies by **magic bytes first, extension second** (never trust the
extension alone — a `.xlsx` is a ZIP; a mislabeled `.pdf` is common). It then
dispatches to an adapter registered against that type. Each adapter implements a
single interface:

```python
class ParserAdapter(Protocol):
    def can_handle(self, probe: FileProbe) -> float:      # confidence 0..1
        ...
    def parse(self, src: Path, cfg: Config) -> CanonicalDoc:
        ...
```

**Two adapters ship in v1 — because there are two inputs:**

- **`PdfAdapter`** — the **teacher guide, which *is* the lessons** (§0.4). Docling
  primary (table structure, reading order, provenance), **PyMuPDF** for the outline,
  font spans, and page images the segmenter needs. Multimodal PDF salvage as the
  per-page fallback for pages Docling parses poorly.
- **`SpreadsheetAdapter`** — the standards framework; openpyxl, each row → a block,
  hierarchy derived from the code (§9).

A **`LessonPlanAdapter`** is designed but **not a v1 input** — see §10. It exists to
prove the seam generalizes: a third type is added by writing one `ParserAdapter` and
calling `register()`, with nothing downstream changing. The Canonical Document Model
is the contract that makes that safe.

---

## 4. The Canonical Document Model

Every adapter emits the same structure — an ordered list of typed **blocks**, each
carrying its own provenance. This is the widest, most important interface in the
system.

```python
class Provenance(BaseModel):
    source_id: str            # content hash of the origin file
    page: int | None          # 1-indexed, or None for non-paged sources
    bbox: tuple[float, ...] | None
    sheet: str | None         # for spreadsheets
    cell: str | None

class Block(BaseModel):
    kind: Literal["heading", "paragraph", "list_item", "table",
                  "image", "caption", "row", "code_label", "page_header"]
    text: str                 # normalized: bullets stripped, whitespace collapsed
    level: int | None         # heading tier (1=13pt, 2=11pt, 3=run-in) — see §6
    font: FontSpec | None     # size, family, weight — kept for the segmenter
    provenance: Provenance
    payload: dict = {}        # kind-specific: table cells, image ref, etc.

class CanonicalDoc(BaseModel):
    source_id: str
    media_type: str
    outline: list[OutlineEntry]   # PDF bookmarks, if any
    blocks: list[Block]
    assets: list[Asset]           # extracted images/embedded objects
```

Two properties earn their keep immediately: **provenance on every block** is what
makes `evidence_page_number` trustworthy instead of a hardcoded `±7` offset; and
**keeping `font` on blocks** is what lets the segmenter recover structure from an
untagged PDF without re-parsing.

---

## 5. Lesson separation — *where does each lesson begin and end?*

This is the question you asked to pinpoint. The answer is a **ranked resolver**,
not a single trick — because the signal that works best here (the outline) is not
guaranteed on the next publisher's document.

![Lesson separation: four ranked signals — PDF outline, running-header state machine, title font cue, vision fallback — feed a reconciler that asserts count-in equals count-out; the G1M2U1L1 code is parsed into grade/module/unit/lesson](diagrams/12-lesson-separation.svg)

*Figure 12 — Boundary resolution. Ranked most-reliable-first; each lesson's start
page comes from the highest signal present, and boundaries are the half-open span
to the next start.*

### 5.1 The four signals, most-reliable first

1. **PDF outline / bookmarks — authoritative for this document.**
   The teacher guide's outline has one entry per lesson: `G1M2U1L1-ModuleLessons`
   → page 12, `G1M2U1L2` → page 24, and so on. Verified: the destination page's
   first text line is exactly `Grade 1: Module 2: Unit 1: Lesson 1`. The start page
   is the bookmark's destination; the end page is the next bookmark's destination
   minus one — a half-open span, so pages partition with no gaps and no overlaps.

   > **iter_1 had this signal and threw it away** — it read only the *first*
   > outline entry's destination and discarded the rest
   > (`toc_extraction.py:28`). We consume the whole outline.

The span arithmetic, stated once:

```
lesson[i].page_start = outline[i].dest_page
lesson[i].page_end   = outline[i+1].dest_page - 1     # half-open: no gaps, no overlaps
```

2. **Running-header state machine — corroboration.** Every recto page carries
   `Grade N: Module N: Unit N: Lesson N`. Parsing it per page gives an independent
   vote on which lesson a page belongs to, and catches an outline that points a few
   pages off. (It is present on ~50% of pages — recto only — so it is a *check*,
   not the primary.)

3. **Title font cue — the publisher-agnostic fallback.** A lesson's first page
   opens with its title in **13 pt `MarkPro-Heavy`**, the largest text on the page.
   When there is no outline (the next publisher), "largest text on a page that
   matches a lesson-title pattern" recovers boundaries structurally. Costs nothing.

4. **Vision on a low-DPI page image (small multimodal model) — last resort.** *"Does a new lesson
   start on this page? What is its title?"* Robust, costs money, but runs once per
   document and is cached forever.

### 5.2 Reconciliation — and the assertion that would have caught iter_1's bug

The resolver takes the highest-confidence signal present, then **cross-checks**
against the others. Agreement → accept. Disagreement → flag for review and refuse
to emit a silent guess. Finally, a hard invariant:

```python
assert len(lessons) == expected_lesson_count(outline)   # 40 in → 40 out
assert all(l.page_end >= l.page_start for l in lessons)  # no inverted spans
assert no_gaps_or_overlaps(lessons)                      # pages partition cleanly
```

iter_1 emitted the *last page as page 1* and never read the true last page
(`simple_page_extrc.py:106`, a 0- vs 1-indexed off-by-one). A single
`count_in == count_out` assertion turns that class of bug from a silent data loss
into a loud failure.

### 5.3 Parse the code once

The bookmark code is a gift — it encodes the document's position in the curriculum:

```
G1 M2 U1 L1
│  │  │  └── Lesson 1
│  │  └───── Unit 1
│  └──────── Module 2
└─────────── Grade 1
```

Parsed once at segmentation time (`^G(\d+)M(\d+)U(\d+)L(\d+)`), it becomes the
lesson's stable identity and its grade — so we **read the grade from the document**
instead of hardcoding `K` (iter_1's `simple_page_extrc.py:138`).

---

## 6. Lesson division — *how is one lesson split into chunks?*

Once a lesson's page span is known, we divide *within* it using the font
hierarchy. EL Education lessons have a strict, repeating anatomy — the same three
tiers on every lesson.

![Lesson division: a lesson splits into a Cover metadata block, Teaching Notes, and the Instructional Sequence (Opening, Work Time, Closing); the instructional blocks carry student-action evidence, the rest is metadata](diagrams/13-lesson-division.svg)

*Figure 13 — Intra-lesson structure, recovered from the 3-tier font hierarchy. The
shaded blocks carry the student-action evidence the judge reads; everything else is
metadata — including the publisher's alignment claim.*

### 6.1 The three font tiers → three structural roles

| Tier | Font | Role | Examples observed |
|---|---|---|---|
| **13 pt** | `MarkPro-Heavy` | **Major block** | Lesson title, *Teaching Notes*, *Opening*, *Work Time*, *Closing and Assessment* |
| **11 pt** | `MarkPro` | **Section** | *CCS Standards*, *Daily Learning Targets*, *Ongoing Assessment*, *Agenda*, *Vocabulary*, *Materials*, *Meeting Students' Needs* |
| **9.5 pt bold** | `MercuryTextG2-Bold` | **Run-in label** | *Purpose of lesson…*, *In advance:*, *Key:* / *New:* / *Review:* |

> One trap to encode: 9.5 pt **bold** is a real run-in label, but 9.5 pt
> **bold-italic** (`MercuryTextG2-BoldItalic`) is a *sample teacher/student
> utterance* ("…at the sky)"). Gate on the exact font, not just size + weight, or
> the segmenter will mistake scripted dialogue for headings.

### 6.2 The lesson divides into three chunk families

- **A · Cover (metadata).** `CCS Standards`, `Daily Learning Targets` (each printed
  *with its standard codes* — `(SL.1.1a, SL.1.2)`), `Ongoing Assessment` (also
  tagged), and the `Agenda` — which lists every instructional block *with its
  duration*: `Opening A (10 min) · B (10 min)`, `Work Time A (5) · B (10) · C (15)`,
  `Closing A (10)`.
- **B · Teaching Notes (metadata).** Purpose, prior-work, vocabulary, materials,
  ELL/UDL support. Context for the judge, not evidence.
- **C · Instructional Sequence (evidence).** `Opening` → `Work Time` → `Closing`,
  each with lettered sub-blocks that match the Agenda. **This is where the student
  does something** — the only place a quote proving a standard is *taught* can come
  from.

### 6.3 Why this split is the crux of the product

The `CCS Standards` cover block is the publisher's **claim**. The Work Time blocks
are the **evidence**. The alignment judge's entire job is to decide whether the
evidence in C actually satisfies a standard — and the grounding check (main spec
§11) requires the evidence quote to appear in the raw text of a **C** block. So the
chunker must keep C blocks intact and separately addressable, and must tag every
chunk with which family it belongs to. A naïve fixed-window chunker that slices
across the Agenda/Work-Time boundary destroys exactly the structure the judge
depends on.

### 6.4 The parse ruleset — executable, and proven on the real document

The rules below are not aspirational. They were run against all 440 pages of the
teacher guide; the proof is inline. Each rule traces to an observed layout fact,
never an assumption.

**Separation rules — where each lesson begins and ends:**

| # | Rule | Basis |
|---|---|---|
| S1 | Lesson starts = outline entries matching `^G(\d+)M(\d+)U(\d+)L(\d+)`; parse the 4 groups → grade / module / unit / lesson | 43 bookmarks, verified against page-1 text |
| S2 | `page_start = bookmark.dest`; `page_end = next_bookmark.dest − 1` (half-open) | pages partition with no gaps/overlaps |
| S3 | **Assert** `count == 40` ∧ spans monotonic ∧ none inverted, else fail loud | catches iter_1's off-by-one |
| S4 | Grade is read from the code (`G1`), never hardcoded | fixes iter_1's hardcoded `K` |

> **Proof:** 40 lessons found (expected 40) · Unit 1 = 15 (pp. 12–165), Unit 2 = 12
> (pp. 178–307), Unit 3 = 13 (pp. 318–440) · assertions **PASS**.

**Division rules — how one lesson splits into blocks (font hierarchy):**

| Tier | Trigger | Role |
|---|---|---|
| 1 | `size ≥ 12.5` ∧ `MarkPro` | **Major block** — Title, Teaching Notes, Opening, Work Time, Closing & Assessment |
| 2 | `10.4 ≤ size ≤ 11.6` | **Section** — CCS Standards, Daily Learning Target(s), Ongoing Assessment, Agenda, Vocabulary, Materials |
| 3 | `9.0 ≤ size ≤ 9.9` ∧ **bold** ∧ **not italic** | **Run-in label** — Purpose, In advance, Key / New / Review |
| 0 | everything else | Body prose |

- **D1** — A major block runs from its tier-1 header to the next; recurring page-top
  repeats of the same header (a section spanning pages) are de-duplicated.
- **D2** — The tier-3 gate is exact: `MercuryTextG2-Bold` is a label, but
  `MercuryTextG2-BoldItalic` is a *scripted classroom utterance*, not a heading.
  Missing this turns dialogue into false headings.

**Parse rules — what each lesson yields:**

| Field | Rule | Method |
|---|---|---|
| Title | concat consecutive tier-1 lines on cover before the first section | — |
| Declared standards | collect codes under the `CCS Standards` section | `[A-Z]{1,3}\.\d+\.\d+[a-z]?` (CCSS) |
| Learning targets | `I can…` lines under `Daily Learning Target(s)`; strip trailing `(codes)` from text, keep codes | prefix + code regex |
| Agenda blocks | under `Agenda`: `N. <Section>` sets the block; `X. <title> (M minutes)` is a sub-block | `^([A-Z])\.\s*(.+?)\((\d+)\s*minutes?\)` |
| Body sections | tier-1 headers with their page | — |

**Worked example — `G1M2U1L1`, fully parsed by the rules above:**

```json
{
  "code": "G1M2U1L1", "grade": 1, "module": 2, "unit": 1, "lesson": 1,
  "pages": "12–23",
  "title": "Lesson 1: Noticing and Wondering: Observing and Asking Questions
            about the Sun, Moon, and Stars",
  "declared_standards": ["SL.1.1", "SL.1.1a", "SL.1.2", "W.1.8"],   // CCSS — a CLAIM
  "learning_targets": [
    {"text": "I can describe what I observe…", "codes": ["SL.1.1a","SL.1.2","W.1.8"]},
    {"text": "I can ask questions about what I notice…", "codes": ["SL.1.1a","SL.1.2"]}
  ],
  "agenda": [                                    // 6 blocks, sum = 60 min
    {"section":"Opening",                "letter":"A", "minutes":10},
    {"section":"Opening",                "letter":"B", "minutes":10},
    {"section":"Work Time",              "letter":"A", "minutes":5},
    {"section":"Work Time",              "letter":"B", "minutes":10},
    {"section":"Work Time",              "letter":"C", "minutes":15},
    {"section":"Closing and Assessment", "letter":"A", "minutes":10}
  ],
  "body_sections": ["Teaching Notes p13","Opening p16","Work Time p19","Closing p22"]
}
```

**Two edge cases the full sweep surfaced — and the rules that absorb them.** A
parser that only proves itself on Lesson 1 is overfit; running all 40 caught real
layout variation:

1. **Singular header.** A lesson with one target prints `Daily Learning Target`
   (no `s`). → the rule matches `Daily Learning Targets?`.
2. **Agenda spills to page 2.** `G1M2U1L5` declares **13** standards; the long list
   pushes the Agenda off the cover page. → the rule scans the first three pages for
   `Agenda`, not just page 1.

> **Validation after hardening:** all **40 lessons** parse, and **every lesson's
> agenda independently sums to 60 minutes** — a free integrity check, since EL
> Education lessons are one hour. A lesson whose blocks don't sum to ~60 is a parse
> error the loader should flag, not store.

---

## 7. Chunking strategy

**Principle: chunk on structure, never on a fixed token window.** The document
already tells us where the meaningful boundaries are; a 512-token sliding window
would shred them. We emit a *hierarchy* of chunks and let retrieval choose the
granularity.

| Chunk level | Boundary | Embedded? | Used for |
|---|---|---|---|
| `Document` | whole file | no | provenance root |
| `Unit` | outline unit entry | no | navigation, filtering |
| `Lesson` | §5 boundaries | **yes** (the normalized competency view) | coarse retrieval, the judge's unit of work |
| `Block` | §6 major block (Opening / Work Time / Closing) | **yes** | fine retrieval, evidence location |
| `Segment` | lettered sub-block (`Work Time C`) | optional | precise evidence grounding |

Rules that keep chunks judge-ready:

1. **Never split a table, a list, or a lettered sub-block across chunks.**
2. **Every chunk carries its ancestry** (`grade → module → unit → lesson → block`)
   and its provenance span — so a retrieved Work-Time chunk still knows it is
   `G1M2U1L1 · Work Time · C · pp. 19–20`.
3. **Embed the *normalized* text, keep the *raw* text** (main spec §7): retrieval
   matches concept-to-concept; the judge and grounding check read the raw block.
4. **Overlap only at semantic joins** — a Work-Time chunk carries a one-line
   pointer to its lesson's learning targets, so a candidate never arrives at the
   judge context-free.

---

## 8. Tables, images, and embedded content

| Content | Where it appears | Handling |
|---|---|---|
| **Tables** | Standards grids; in-lesson checklists | Docling `TableFormer` → real cell/row/column objects, stored as a `table` block with structured `payload`. **Never** flattened to a token stream (that destroys the row↔grade relationship). |
| **Images / diagrams** | Anchor charts, illustrations | Extracted to `assets`, referenced by block. OCR/caption on demand (vision model) only if a lesson references them as instructional content; otherwise stored with alt-text + provenance. |
| **Bulleted lists** | Standards, targets, materials | `list_item` blocks; the `\x84` private-use bullet glyph is normalized to a real list marker at extraction. |
| **Running headers/footers** | Every page | Captured as `page_header` blocks — used for provenance and the §5 state machine, then excluded from body chunks so they don't pollute embeddings. |
| **Multi-column / callouts** | *Meeting Students' Needs* sidebars | Reading-order from Docling; callouts kept as their own blocks, attached to the parent instructional block. |

---

## 9. Standards ingestion — flat spreadsheet → grade-indexed tree

![Standards spreadsheet parsing: flat rows are turned into a Domain/Big-Idea/Standard/Substandard tree by deriving level from code dot-depth, not the empty Notes column](diagrams/14-standards-tree.svg)

*Figure 14 — The spreadsheet is a tree in disguise; the hierarchy lives in the code
string, not in the (mostly empty) level column.*

The `SpreadsheetAdapter` produces the same `GradeStandards` contract as the main
spec §6.2 — but from a clean tabular source, so no LLM is involved:

```python
def level_of(code: str) -> Level:
    # depth is the number of dots — NOT the Notes column (empty on 183/188 rows)
    return {1: DOMAIN, 2: BIG_IDEA, 3: STANDARD}.get(code.count("."), SUBSTANDARD)

def parent_of(code: str) -> str | None:
    return code.rsplit(".", 1)[0] if "." in code else None
```

- **Hierarchy from the code, not the sheet.** `1.F.PA.4.d`'s parent is `1.F.PA.4`,
  whose parent is `1.F.PA`. Trusting the `Notes` column would mislabel 183 rows.
- **Grade from the code.** Every code begins `1.` → Grade 1. Read it; don't assume.
- **Split the `Standard Text` prefix.** `"Syllables: Identify and manipulate…"` →
  `short_label = "Syllables"`, `text = "Identify and manipulate…"`.
- **Encode the known edge case.** GC.1 substandards are *numbered*, not lettered —
  the leaf detector must not assume an `[a-z]` suffix.
- **Same contract, three possible sources.** Whether standards come from this xlsx,
  a state PDF, or the Learning Commons **Knowledge Graph** API, the adapter emits
  the identical `GradeStandards` tree — so the rest of the system never learns
  where they came from. (KG would additionally supply the CCSS↔GA crosswalk that
  §12 needs.)

---

## 10. Lesson plans — a distinct, future artifact (not a v1 input)

**First, the point that must not be blurred: the teacher guide *is* the lessons.**
The 40 lessons the product aligns (`G1M2U1L1` …) live inside the teacher guide, one
structured lesson each (§0.4, §5–§6). There is no separate "lessons" file, and none
is needed. v1 ingests **two** documents — the teacher guide (the lessons) and the
standards spreadsheet — not three.

A **lesson plan** is a *different artifact*: a teacher's **own** working document —
a Word/Google doc they authored or adapted — as opposed to the published curriculum.
It shares the *shape* of a lesson (declared standards, objectives, a procedure) but
differs in **source and authority**. No such file exists in the current input set,
so it is **out of scope for v1** and lives behind the extensibility seam (§3, §15).

When it does become an input, the `LessonPlanAdapter` handles it with the same
resolver philosophy, and — crucially — it maps onto the **same** `Lesson` node and
the **same** link graph, distinguished only by `source_type`:

- **Structure by template when known, by heading-map when not.** Common LMS/district
  templates (Objective, Standards, Materials, Procedure, Assessment) are matched by a
  small library of heading synonyms; unknown layouts fall back to the font/heading
  heuristics from §5 signal 3.
- **The same three roles.** *Declared standards* (claim), *objectives* (targets),
  *procedure* (evidence) — so it reuses the §6 chunk families unchanged.
- **Weaker provenance, handled honestly.** A reflowed DOCX has no stable page/bbox;
  provenance falls back to paragraph index. The grounding check still works (it
  matches text, not coordinates).

This is why it is documented now but not built now: a clean seam is worth defining
before the type arrives, so its later addition changes nothing downstream.

---

## 11. Metadata generation & normalization

Each chunk is enriched into a typed record before storage:

| Metadata | Source | Example |
|---|---|---|
| Curriculum path | parsed bookmark code | `grade=1, module=2, unit=1, lesson=1` |
| Chunk role | font tier + section name | `family=instructional, block=Work Time, sub=C` |
| Declared standards | Cover `CCS Standards` block | `["W.1.8","SL.1.1","SL.1.1a","SL.1.2"]` (CCSS) |
| Target-level tags | parenthetical codes on each target | target 1 → `["SL.1.1a","SL.1.2"]` |
| Timing | Agenda | `Work Time C = 15 min` |
| Provenance | every block | `pp. 19–20, bbox …` |
| Content hash | normalized text | cache + idempotency key |

**Normalization is deliberately shallow here.** Ingestion standardizes *form*
(whitespace, bullets, code casing, en-dash vs hyphen in codes — the exact class of
bug that broke iter_1's joins). The *pedagogical* normalization (standard →
classroom competency) is a separate, later stage (main spec §7); conflating them
was an iter_1 mistake.

---

## 12. Cross-document normalization & the link graph

This is how relationships across teacher guides, lesson plans, standards, and
assessments are preserved and made queryable. Everything lands in **one property
graph** over Postgres (nodes as rows, relationships as edges) — no separate graph
database needed at this scale (main spec §8).

![Cross-document link graph: Lesson, Learning Target, Instructional Block, Assessment, declared CCSS code, Evidence, and GA Standard, connected by declared/crosswalk edges versus the earned TEACHES edge](diagrams/15-link-graph.svg)

*Figure 15 — One graph, two kinds of edge. Dashed edges are **declared or
crosswalked** — asserted by a document or the KG, and unverified. The single bold
edge, **TEACHES**, is the only one *earned* by grounded evidence. Keeping them
distinct is the integrity of the whole system.*

### 12.1 Node & edge types

| Node | From |
|---|---|
| `Lesson` (teacher guide or lesson plan) | §5 |
| `InstructionalBlock` (Opening/Work Time/Closing) | §6 |
| `LearningTarget`, `Assessment`, `Vocabulary` | Cover blocks |
| `CcssCode` (declared) | Cover `CCS Standards` |
| `StandardsFrameworkItem` (GA) | §9 |
| `Evidence` (quote + provenance) | judge output |

| Edge | Meaning | Verified? |
|---|---|---|
| `Lesson —contains→ Block` | structural | fact |
| `Lesson —declares→ CcssCode` | publisher's claim | **no** |
| `LearningTarget —tagged_with→ CcssCode` | printed tag | **no** |
| `Assessment —measures→ LearningTarget` | printed | **no** |
| `CcssCode —aligns_to→ GA Standard` | Knowledge Graph crosswalk | **no** (external assertion) |
| `Block —yields→ Evidence —grounds→ GA Standard` | judge + grounding check | **yes** |
| **`Lesson —TEACHES→ GA Standard`** | the product's output | **yes**, earned by evidence |

The design rule: **declared/crosswalk edges are inputs and priors; the `TEACHES`
edge is the only output we stand behind.** A `declares` edge to a CCSS code plus an
`aligns_to` crosswalk gives the retriever a strong candidate GA standard — but the
edge only becomes `TEACHES` when a Work-Time quote grounds it.

### 12.2 Why this is queryable both ways, efficiently

Because it is one indexed relational graph, the two questions the product must
answer are both a single join, in either direction:

```sql
-- "Which lessons teach GA standard 1.F.PA.4.d, with evidence?"
SELECT l.code, e.quote, e.page
FROM teaches t
  JOIN lesson l   ON l.id = t.lesson_id
  JOIN evidence e ON e.id = t.evidence_id
WHERE t.ga_standard = '1.F.PA.4.d' AND t.status IN ('full','partial');

-- "For this lesson, what does it teach vs. only claim?"
SELECT ga_standard, status FROM teaches WHERE lesson_id = :id      -- earned
EXCEPT
SELECT ga.code FROM declares d JOIN aligns_to a USING (ccss_code)  -- merely claimed
       JOIN ga_standard ga ON ga.code = a.ga_code WHERE d.lesson_id = :id;
```

The second query — *claimed but not taught* — is a curriculum-gap report that
falls straight out of keeping the two edge kinds separate. It is impossible to
produce if ingestion collapses claim into fact.

---

## 13. Error recovery & resilience

| Failure | iter_1 behavior | This design |
|---|---|---|
| A page/lesson fails to parse | silent; whole run may report success | **quarantine** that unit as a typed `ParseError` artifact; the other 39 lessons proceed; the run summary lists what was quarantined |
| Model/HTTP 429/5xx | no retry; standard silently lost | retry with backoff; on exhaustion, a loud typed failure, never an empty cache entry |
| Malformed cache entry | `{"error": …}` cached as valid forever | cache keys on `hash(prompt+model+input)`; error payloads are **never** cached |
| Boundary miscount | last page lost, no signal | §5.2 assertions fail the run loudly |
| Partial write | half-file counts as complete | write-to-temp + atomic rename; content hash verified on read |

The governing rule (main spec §15): **a wrong answer is more dangerous than no
answer.** Every recovery path preserves that ordering.

---

## 14. Performance & scale

- **Parse is O(once) and content-addressed.** A 440-page book is parsed a single
  time; re-runs hit cache. Editing a prompt downstream invalidates *nothing* in
  ingestion.
- **Concurrency unit = the lesson.** 40 independent lessons parse and enrich in
  parallel behind an async concurrency cap — not iter_1's one-call-at-a-time with a
  superstitious `sleep(2)`.
- **Vision is the only paid step, and it is last-resort + cached.** Signals 1–3 in
  §5 cost nothing; vision salvage runs only where structure is genuinely ambiguous.
- **150 DPI, not 200, when a page image is needed** (main spec §5.2) — the API
  downscales 200 DPI anyway.
- **Batch-friendly.** The whole pipeline is offline, so any model-assisted step
  (vision fallback, normalization) can go through the Batch API at 50% off.

---

## 15. Extensibility for future document types

The seam is the `ParserAdapter` (§3). To add — say — an **assessment bank** or a
**scope-and-sequence** document:

1. Implement `can_handle` + `parse` → `CanonicalDoc`.
2. `register(MyAdapter())`.
3. Add any new node/edge types to the graph schema (additive migration).

Nothing in stages ③–⑦ changes. The canonical model and the link graph absorb the
new type; a scope-and-sequence simply adds `Unit —precedes→ Unit` edges, an
assessment bank adds `Assessment —assesses→ GA Standard` edges — and both become
queryable alongside everything else the moment they load.

---

## 16. Repository layout

```
ingestion/
├── router.py              # classify(bytes) -> AdapterId
├── model.py               # CanonicalDoc, Block, Provenance  (the contract)
├── adapters/
│   ├── base.py            # ParserAdapter protocol + registry
│   ├── pdf.py             # Docling + PyMuPDF
│   ├── spreadsheet.py     # openpyxl -> GradeStandards tree
│   └── lesson_plan.py     # docx / md / pdf
├── structure.py           # font-hierarchy -> heading tree
├── segment/
│   ├── lessons.py         # §5 boundary resolver + assertions
│   └── blocks.py          # §6 intra-lesson division
├── chunk.py               # §7 hierarchical chunker
├── enrich.py              # §11 metadata + shallow normalization
├── graph/
│   ├── nodes.py           # SQLAlchemy models
│   ├── edges.py           # declared vs earned edge types
│   └── load.py            # idempotent upsert by content hash
└── tests/
    ├── test_lessons.py    # 40-in-40-out on the real teacher guide
    └── test_standards.py  # 188 rows -> 4/14/35/135 tree
```

---

## 17. What this deletes from iter_1, and what remains open

**Deletes** (superseded by this design): the `TIMING GOAL` magic-string split, the
`get_toc()` misuse, the hardcoded grade `K`, the page off-by-one, the Markdown
round-trip, and the whole `page_N`/en-dash/`int("1.")` class of shape-drift bugs —
because structure now comes from the document's own signals into a typed contract.

**Open decisions:**

1. **Docling vs. PyMuPDF as primary for this book.** The outline + font signals are
   so clean here that PyMuPDF alone may suffice; Docling earns its place on the
   standards *grids* and on messier lesson plans. Measure on both.
2. **How much of the Cover's declared-standard tags to trust as retrieval priors.**
   They are a strong signal but unverified; likely weight them, don't gate on them.
3. **Lesson-plan template library scope.** Which district/LMS templates to seed
   before falling back to heuristics.
4. **Assessment modeling depth.** Whether `Ongoing Assessment` becomes a first-class
   node in v1 or rides along as lesson metadata until the assessment-bank type lands.
```
