# Veramynd — Backend API

FastAPI service for curriculum–standards alignment: ingest, pipeline jobs, and
artifact APIs. The **React frontend** (`../frontend`, port **5173**) is the
operator UI. This process (default port **8000**) serves `/api/*` and can host
the built SPA from `/` after `npm run build` in `frontend/`.

## Stack

| Layer | Path | Role |
|-------|------|------|
| Backend API | `backend/` | `/api/*`, ingest, pipeline jobs |
| Frontend | `frontend/` | Operator pages (Vite proxies `/api`) |
| Registry | `backend/projects.json` | Demo / locked projects |
| Uploads | `backend/uploads/` | Ingest batches + `output/` |
| Jobs | `backend/runs/` | Job JSON + logs (gitignored) |
| Pipeline package | `veramynd_parser/` | CLI stages + Batch-1 demo output |

Path discovery lives in [`api/layout.py`](api/layout.py) (override with
`VERAMYND_FRONTEND_ROOT`, `VERAMYND_PARSER_ROOT`, `VERAMYND_UI_DIST` if needed).

## Run

**Terminal 1 — API**

```bash
cd veramynd/backend
pip install -r requirements.txt
python run.py
```

Default: `http://127.0.0.1:8000` (`VERAMYND_API_PORT` / `VERAMYND_API_URL` to override).

**Terminal 2 — React UI**

```bash
cd veramynd/frontend
npm install
npm run dev
```

Open: http://127.0.0.1:5173/

Demo project: `/projects/el-g1-m2-ga-ela`  
Upload projects: `/projects/upload-<batch-id>`

After `npm run build` in `frontend`, the API can serve `dist/` at `/`.

## Projects

| Kind | ID shape | Notes |
|------|----------|--------|
| Registry | e.g. `el-g1-m2-ga-ela` | From `projects.json`; Batch-1 demo points at `veramynd_parser/output` |
| Upload | `upload-<batch-id>` | Created under `uploads/`; output under `uploads/<batch>/output/` |
| None | `none` | No project selected — Ingestion / Pipeline / Logging still available |

PDF + XLSX are required to ingest. Program / grade / module labels are optional
(publisher-agnostic storage).

Delete project / batch removes inputs (and upload output) from the list; **job
logs stay** until **Logging → Clear logs**.

## Pages (UI)

| Page | Task |
|------|------|
| **Overview** | Empty → partial → ready; stage bars from real output folders; KPIs after judge |
| **Curriculum** | Parsed lessons; open lesson detail (agenda, blocks, steps, pages) |
| **Standards** | Framework tree + coverage |
| **Alignments** | Browse `full` / `partial` / `none` verdicts + evidence drawer |
| **Review** | Alignments flagged for human review |
| **Exports** | Client correlation DOCX/XLSX + CSVs |
| **Projects** | Switch / delete projects |
| **Ingestion** | Upload PDF + XLSX |
| **Pipeline** | Complete auto or step-by-step (+ resume) |
| **Logging** | All jobs, stage/lesson view, typed errors, Clear logs |
| **Settings** | Health + catalog reload |

## Pipeline stages (runnable)

Order used by Complete auto and step-by-step:

1. **Parse** → `stage1/`
2. **Normalize** → `normalize/` + `normalize_standards/`
3. **Embed** → `embeddings/` (+ Qdrant)
4. **Retrieve + rerank** → `retrieve/` (**top 25** shortlist)
5. **Judge + escalation** → `judge/` (**top 25 + coverage pass**)
6. **Final report** → `reports/alignments_all.csv` + **client correlation**
   DOCX/XLSX (listed on Exports)

Overview also shows Ingestion / Reranking / Escalation / Final results as
**artifact** stages (derived from those folders — not guesses after Parse alone).

### Resume

- On API startup, orphaned `running`/`queued` jobs become **cancelled** (logs kept).
- **Resume complete pipeline** / re-run skips stages whose outputs are already
  complete for every Stage-1 lesson.
- Partial **Normalize** / **Judge** re-runs continue from CLI caches (per lesson).

## Cost in Logging

- Normalize / Embed print **OpenAI** usage + estimated USD.
- Judge prints **Anthropic** usage + estimated USD (per lesson and stage total).
- Each pipeline step appends `COST stage=… estimated_usd=…`; a finished run appends
  `COST_TOTAL` and **Pipeline total estimated cost**.
- Logging shows per-stage cost on stage cards and job / all-jobs totals.

## Readiness

| State | Meaning |
|-------|---------|
| `empty` | No lessons / standards / judge yet |
| `running` | Partial artifacts (e.g. stage1 only) — or a live job |
| `ready` | Judge alignments present |

## Layout

```
backend/
  api/           # FastAPI routes + pipeline runner
  uploads/       # ingest batches (gitignored contents)
  runs/          # job JSON + logs (gitignored)
  projects.json  # registry
  run.py
  requirements.txt
```
