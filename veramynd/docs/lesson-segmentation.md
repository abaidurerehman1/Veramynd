# Veramynd — Lesson Segmentation & Verification

**How the system separates a teacher guide into individual lessons, divides each
lesson into its parts, and verifies — with a safety net — that it did so correctly.**

**Status:** Proposed · **Last updated:** 20 July 2026

---

## 1. What we analyzed

The reference document is `ELA Grade 1 Module 2 Teacher Guide.pdf` — a **440-page**
published curriculum. Before designing anything, we inspected it directly. Three
structural signals in the file make lesson segmentation reliable:

| Signal | What we found | Why it matters |
|---|---|---|
| **Embedded outline** | The PDF ships with 43 **bookmarks**; every lesson is one bookmark, coded `G1M2U1L1` (Grade 1 · Module 2 · Unit 1 · Lesson 1) | Gives the exact start page and a unique identity for each lesson |
| **Running header** | Every lesson page prints `Grade 1: Module 2: Unit 1: Lesson N` | An independent confirmation of which lesson a page belongs to |
| **Font hierarchy** | A strict 3-tier type system — 13 pt headings, 11 pt sections, 9.5 pt-bold labels | Lets us divide a lesson into its parts by layout, not guesswork |

The document is organized as **3 units → 40 lessons** (15 + 12 + 13), each unit
preceded by a Unit Overview. Every finding below was verified by running the
extraction against all 440 pages.

---

## 2. How the system separates lessons

The publisher already marked where every lesson begins — the same way a binder has
tabs. The system **reads those marks**; it never scans the prose hoping to find a
lesson start.

![Separation: the PDF's own bookmarks name each lesson and point to its start page; a boundary rule turns them into 40 lessons that partition all 440 pages with no gap or overlap](diagrams/20-separation.svg)

*Figure 1 — Separation. Each lesson bookmark gives a start page; the boundary is the
half-open span to the next bookmark. The three Unit Overviews are held out, and the
440 pages partition cleanly.*

**The rule, in three parts:**

1. **Start page** = the lesson bookmark's destination. `G1M2U1L1` → page 12,
   `G1M2U1L2` → page 24.
2. **End page** = the next bookmark's start − 1. So Lesson 1 = pages 12–23, Lesson 2
   = pages 24–33. A half-open span — no page is shared, none is skipped.
3. **Identity** = the full four-part code. Lesson numbers reset each unit (there is a
   Lesson 1 in every unit), so the system never uses the bare number. `G1M2U1L1`,
   `G1M2U2L1`, and `G1M2U3L1` are three distinct lessons, and all 40 codes are unique.

**The document partitions perfectly:**

```
pp.   1– 11   Unit 1 Overview      (held out — not a lesson)
pp.  12–165   Unit 1 · Lessons 1–15
pp. 166–177   Unit 2 Overview      (held out)
pp. 178–307   Unit 2 · Lessons 1–12
pp. 308–317   Unit 3 Overview      (held out)
pp. 318–440   Unit 3 · Lessons 1–13
```

Every one of the 440 pages belongs to exactly one segment.

**If a future document has no bookmarks,** the same lesson start is recovered from
the running header (`Unit N: Lesson N` on the page) or the 13 pt title on the
lesson's first page — and the verifier in §4 runs identically either way.

---

## 3. How the system divides each lesson

Once a lesson's page span is known, the system divides *within* it using the font
hierarchy. The type sizes map cleanly onto structural roles.

![Division: the three font tiers map to major blocks, sections, and run-in labels; a lesson splits into a Cover (the claim), Teaching Notes, and the Instructional Sequence (the evidence)](diagrams/21-division.svg)

*Figure 2 — Division. Font tier determines role. A lesson resolves into three block
families; the shaded Instructional Sequence is where the student acts.*

A lesson divides into three families:

- **Cover — the claim.** `CCS Standards` (the standards the lesson targets), `Daily
  Learning Target(s)` (each tagged with its standard codes), `Ongoing Assessment`,
  and the `Agenda` — which lists every instructional block *with its duration*.
- **Teaching Notes — context.** Purpose, vocabulary, materials, and differentiation
  support. Background, not the lesson itself.
- **Instructional Sequence — the evidence.** `Opening → Work Time → Closing and
  Assessment`, each with lettered sub-blocks matching the Agenda. This is where the
  student *does* something.

The distinction between the last two families is deliberate and central: the Cover
is what the lesson **claims** to teach; the Instructional Sequence is the **evidence**
of what it actually teaches. The system keeps them separately addressable so the two
are never confused.

Each parsed lesson therefore yields: its code and grade, the declared standards, the
tagged learning targets, the timed agenda, and the instructional blocks with their
page locations.

---

## 4. The safety net — verifying the division is correct

Separation and division are only trustworthy if the system can **prove** it got them
right. So no lesson set is stored until it passes a layered verifier. Each check has
a severity: a **FAIL** blocks the load; a **WARN** flags the lesson for review.

![Safety-net verifier: three layers of checks — separation integrity, cross-signal confirmation, division completeness — feed a gate; all pass loads the graph, any fail quarantines](diagrams/22-verifier.svg)

*Figure 3 — The verifier gate. The lesson set must clear all hard checks before it is
stored; anything that fails is quarantined for review rather than silently trusted.*

**Layer 1 — Separation integrity** (any failure blocks the run):

| Check | What it guarantees |
|---|---|
| Count = bookmarks | No lesson dropped or invented |
| Pages partition | Every page in exactly one segment — no gap, no overlap |
| Starts increasing | Lessons are in order |
| No inverted span | Every end ≥ its start |
| IDs unique | No two lessons share an identity |
| Contiguous within a unit | Lessons within a unit touch; only overviews sit between units |

**Layer 2 — Cross-signal confirmation** (blocks the run):

- The running header printed on each lesson's first page must name the **same** unit
  and lesson as its bookmark code. This catches a bookmark that points a few pages
  off — the outline and the page content have to agree.

**Layer 3 — Division completeness** (flags for review):

- Each lesson must contain a `CCS Standards` block and all three instructional
  majors (Opening, Work Time, Closing).
- Each lesson's Agenda timing must fall in a sane band (45–75 minutes).

### 4.1 The verifier run — and a real defect it caught

Run against all 40 lessons: **8 hard checks passed, 1 warning.** The result was
`GO` — but the warning is the point.

```
LAYER 1  count · partition · order · spans · ids · contiguity ....... PASS
LAYER 2  running header matches bookmark code (40/40) ............... PASS
LAYER 3  required blocks present (40/40) ........................... PASS
LAYER 3  agenda time in band ....................................... WARN  G1M2U1L12 = 35 min
RESULT   9 checks · 0 FAIL · 1 WARN → GO
```

Lesson 12 came back at 35 minutes, below the band. Investigating the warning
revealed a genuine text-extraction defect, not a short lesson: two of its agenda
lines wrapped across a line break with a **soft hyphen** —

```
A. Song and Movement … Version 2 Song (5 min-
utes)
A. Focused Read-aloud, Session 1 … Live in the Sky (20 min-
utes)
```

The word `minutes` split as `min-utes`, so the timing pattern missed the `(5…)` and
`(20…)` tokens and under-counted the lesson to 35. The true total is
5 + 20 + 15 + 15 + 5 = **60 minutes** — a perfectly normal lesson.

The fix is a single normalization step: stitch soft-hyphen line-wraps
(`min-\nutes` → `minutes`) before reading the timing. After it, **all 40 lessons
fall in band** — 37 at exactly 60 minutes, and 50 / 55 / 65 once each, all real
lesson lengths.

This is exactly why the safety net exists. Without the agenda-timing check, two
lessons would have carried wrong timing metadata silently, and nobody would have
noticed. With it, the anomaly surfaced, the root cause was found, and the fix was
one rule. A verifier that only ever says "PASS" is not verifying anything — a good
one earns its keep by catching the thing you did not think to look for.

---

## 5. Summary

- **Separation is exact and evidence-based.** The document's own bookmarks name each
  of the 40 lessons and pin its start page; a half-open boundary rule turns them into
  a clean partition of all 440 pages, with each lesson identified by a unique
  four-part code.
- **Division follows the document's own typography.** A strict font hierarchy splits
  each lesson into its claim (Cover), context (Teaching Notes), and evidence
  (Instructional Sequence).
- **Verification is not optional.** A layered verifier gates the load: hard checks on
  separation integrity and cross-signal agreement, softer checks on division
  completeness. It already caught a real, silent defect on this document — and every
  lesson now passes.

The result is a segmentation the system can not only perform but **prove** — on this
document today, and on the next publisher's document through the same checks.
