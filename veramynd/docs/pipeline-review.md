# Pipeline review — normalize → chunk → embed → Qdrant

Status of the Stage-1 prep path for EL Education G1M2 (40 lessons).

## 1. Normalization

| | |
|---|---|
| Technique | ELA curriculum normalize (`normalize_ela.v2.1`) |
| Model | OpenAI `gpt-4.1-mini` |
| Strategy | Pedagogical normalize before retrieval — standards-agnostic shared vocabulary (skills + student actions) with verbatim evidence |
| Output | `veramynd_parser/output/normalize/` — schema `2.0-ela` |

## 2. Chunking

| | |
|---|---|
| Technique | 3-level hierarchical, structure-grounded |
| Levels | **Lesson** (normalize competency text) → **Instructional** (Stage-1 Opening / Work Time / Closing blocks) → **Evidence pointer** (quote→block join; not embedded) |
| CLI | `veramynd-parser chunk-lessons` |
| Output | `veramynd_parser/output/chunks/by_lesson/` |

## 3. Embeddings

| | |
|---|---|
| Technique | Dense vectors, Cosine distance |
| Model | OpenAI `text-embedding-3-large` (3072-d) |
| Scope | Lesson + instructional only (242 vectors) |
| CLI | `veramynd-parser embed-chunks` |

## 4. Vector store

| | |
|---|---|
| DB | Qdrant (local path `.qdrant_data/`, no Docker) |
| Collection | `veramynd_chunks` |

## Review checklist

- [ ] Normalize prompt/version and sanitizers (location join, actors, materials/vocab)
- [ ] Chunk ID scheme and evidence→block join integrity
- [ ] Embed only lesson/instructional; evidence pointers excluded
- [ ] Qdrant payload fields (`chunk_id`, `family`, `resource_id`, `text`, `content_hash`)
- [ ] Secrets not committed (`.env`, `.qdrant_data/` gitignored)
