# Veramynd Batch-1 top-50 export — summary for Liz / SME review

**Date:** 2026-08-10  
**Product:** Veramynd GA Grade 1 ELA standards alignment  
**Curriculum:** EL Education G1 Module 2 (Sun, Moon, and Stars)

---

## What this package is

CSV exports of the **top 50 standards** the current retrieval system returns for each **Batch-1 gold lesson**. Purpose: human review of full shortlists so we can see whether automated recall under-credits the system when unlabeled-but-correct alignments exist.

## Files (send these)

Folder: `veramynd/veramynd_parser/output/reports/liz_top50_review/`

| File | Lesson |
|------|--------|
| `G1M2U1L1_top50.csv` | Unit 1, Lesson 1 |
| `G1M2U1L3_top50.csv` | Unit 1, Lesson 3 |
| `G1M2U1L6_top50.csv` | Unit 1, Lesson 6 |
| `G1M2U3L5_top50.csv` | Unit 3, Lesson 5 |
| `ALL_gold_lessons_top50.csv` | All four combined (`lesson_id` + same columns) |

Each per-lesson file has **only**:

| Column | Meaning |
|--------|---------|
| `rank` | 1–50 (1 = strongest system pick) |
| `standard_code` | GA Grade 1 leaf code (e.g. `1.L.V.1.a`) |
| `standard_text` | Official framework wording (`normalize_standards` → `raw_text`) |

UTF-8 with BOM — opens cleanly in Excel.

## What the system did (one sentence)

For each lesson, multi-query hybrid retrieval (dense + BM25 + RRF, cross-encoder on) builds an enterprise shortlist of 50 standards; these CSVs are that shortlist ordered by retrieval rank.

## Why we are asking for review

Automated eval measures **Recall@k**: “Is each *already-labeled* gold standard in the top k?”

- **k = 20** is the planned product cut (what the judge / SME shortlist should see first).  
- Current Batch-1 numbers on **labeled** positives only (n = 20 full+partial):

| Metric | Score |
|--------|------:|
| R@10 | ~50% |
| **R@20** | **~75%** |
| R@30 | ~85% |
| R@50 | ~90% |

That does **not** mean 75% of “all true alignments” are found. It only scores codes already in the Batch-1 gold set. A lesson can map to several standards; anything the system returns that is **good but not labeled yet counts as a miss or noise** in auto-metrics. Reviewing the full top 50 tells us:

1. Misses that are **real** (system should improve) vs  
2. Rows that should be **KEEP / FULL / PARTIAL** on gold (eval was too harsh).

## How to review (suggested)

For each lesson file, walk ranks 1–50 (start with top 20):

| Tag | Meaning |
|-----|---------|
| **KEEP** or **FULL / PARTIAL** | Legitimate alignment — add / confirm on gold |
| **DROP** / **NONE** | Not a real match for this lesson |
| *(already in gold)* | Confirm code still matches your ruling |

No need to re-type standard text; codes + official text are on the sheet.

## Scope note

- Four lessons only = **Batch-1 gold lessons** used in the current recall eval.  
- Text is **official GA language** (same source of truth as framework documentation), not internal “competency / skills / embed” packaging.  
- System ranks can change if retrieval is re-run; this export matches the **current** `retrieve_gold4` fold used for the 75% R@20 numbers.

## One-line ask

Please review each top-50 list and mark which codes are real lesson alignments (especially outside the existing Batch-1 gold set), so we can separate labeling gaps from true retrieval errors.
