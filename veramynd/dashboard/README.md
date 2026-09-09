# Veramynd — Alignment Dashboard

Operational UI over the curriculum–standards alignment pipeline. One **project** =
one curriculum PDF + one standards workbook + that project’s `output/` tree.

The **React app** (`dashboard-ui`, port **5173**) is the front door. The FastAPI
process (default port **8000**) serves `/api/*` and can also host the built SPA
from `/` after `npm run build`.

## What you can do

- Register or upload a PDF + XLSX (publisher labels optional)
- Run the real CLI pipeline: **Complete auto** or **step-by-step** (confirm each stage)
- **Resume** after power-off / API restart — finished stages skipped from disk;
  Normalize / Judge continue from cached progress where the CLI supports it
- Review Overview → Curriculum → Standards → Alignments → Review → Exports
- Inspect jobs on **Logging**; **Clear logs** is the only path that deletes job logs
  (deleting a project does **not** wipe Logging)

## Stack

| Layer | Path | Role |
|-------|------|------|
| FastAPI | `dashboard/` | `/api/*`, ingest, pipeline jobs |
| React UI | `dashboard-ui/` | All operator pages (Vite → proxies `/api`) |
| Registry | `dashboard/projects.json` | Demo / locked projects |
| Uploads | `dashboard/uploads/` | Ingest batches + `output/` |
| Jobs | `dashboard/runs/` | Job JSON + logs (gitignored) |
| Batch-1 artifacts | `veramynd_parser/output/` | Locked EL G1M2 × GA ELA demo |

## Run

**Terminal 1 — API**

```bash
cd veramynd/dashboard
pip install -r requirements.txt
python run.py
```

Default: `http://127.0.0.1:8000` (`VERAMYND_API_PORT` / `VERAMYND_API_URL` to override).

**Terminal 2 — React UI**

```bash
cd veramynd/dashboard-ui
npm install
npm run dev
```

Open: http://127.0.0.1:5173/

Demo project: `/projects/el-g1-m2-ga-ela`  
Upload projects: `/projects/upload-<batch-id>`

After `npm run build` in `dashboard-ui`, the API can serve `dist/` at `/`.

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
| **Exports** | Download reports / CSV packages for the active project |
| **Projects** | List runs; open or delete |
| **Ingestion** | Upload PDF + XLSX (save only — pipeline never auto-starts) |
| **Pipeline** | Artifact flow + Complete auto / step-by-step run controls |
| **Logging** | All jobs, stage/lesson view, typed errors, Clear logs |
| **Settings** | Health + catalog reload |

## Pipeline stages (runnable)

Order used by Complete auto and step-by-step:

1. **Parse** → `stage1/`
2. **Normalize** → `normalize/` + `normalize_standards/`
3. **Embed** → `embeddings/` (+ Qdrant)
4. **Retrieve + rerank** → `retrieve/`
5. **Judge + escalation** → `judge/`
6. **Final report** → `reports/` / result CSVs

Overview also shows Ingestion / Reranking / Escalation / Final results as
**artifact** stages (derived from those folders — not guesses after Parse alone).

### Resume

- On API startup, orphaned `running`/`queued` jobs become **cancelled** (logs kept).
- **Resume complete pipeline** / re-run skips stages whose outputs are already
  complete for every Stage-1 lesson.
- Partial **Normalize** / **Judge** re-runs continue from CLI caches (per lesson).

## Readiness

| State | Meaning |
|-------|---------|
| `empty` | No lessons / standards / judge yet |
| `running` | Partial artifacts (e.g. stage1 only) — or a live job |
| `ready` | Judge alignments present |

## API (project-scoped)

Most GETs take `?project_id=…`:

- `GET /api/projects`, `GET /api/projects/{id}`, `DELETE /api/projects/{id}`
- `GET /api/overview` — KPIs, readiness, optional `live_job`
- `GET /api/lessons/coverage`, `GET /api/lessons/{code}`
- `GET /api/standards/coverage`, `GET /api/standards/tree`
- `GET /api/alignments`, `GET /api/review`, `GET /api/exports`
- `GET /api/pipeline` — stages + `runnable_steps` + `completed_steps` + `next_step`
- `POST /api/pipeline/run` — `{ confirm: true, mode: "full"|"step", step?, batch_id?|project_id? }`
- `GET /api/pipeline/jobs`, `GET /api/pipeline/jobs/{id}`
- `GET /api/pipeline/logs`, `DELETE /api/pipeline/logs` — Clear logs
- `GET/POST /api/ingest`, `DELETE /api/ingest/{batch_id}`
- `POST /api/reload` — refresh registry + catalog

## Layout

```
dashboard/
├── api/
│   ├── app.py              # FastAPI routes
│   ├── catalog.py          # Artifact adapters / stage status
│   ├── pipeline_runner.py  # CLI jobs, resume, recover interrupted
│   ├── projects.py         # registry + upload-* projects
│   └── schemas.py
├── projects.json
├── uploads/                # ingest batches + output/
├── runs/                   # job JSON + logs
├── web/                    # legacy static (not primary UI)
├── run.py
└── requirements.txt
```

## Notes

- Use **React on :5173** for day-to-day work; do not treat the bare API process as the product UI.
- Metrics must come from artifacts — do not invent accuracy without a corrected master.
- Client-facing retrieve bar remains **Recall@25** when discussing retrieve quality.
- Trust gate: Parse must **GO**; product path does not rely on `--allow-block`.
