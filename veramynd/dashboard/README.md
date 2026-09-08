# Veramynd — Alignment Dashboard

Read-only dashboard over pipeline artifacts. One **project** = one curriculum PDF + one standards XLSX + that project’s output folder.

Does **not** run parse / retrieve / judge. Does **not** mutate production `output/` trees.

## Stack

| Layer | Path | Role |
|-------|------|------|
| FastAPI | `dashboard/` | `/api/*` over registered projects |
| React UI | `dashboard-ui/` | Project Overview, Curriculum, Standards, Alignments |
| Registry | `dashboard/projects.json` | PDF / XLSX / `output_dir` per project |
| Artifacts | `veramynd_parser/output/` (Batch-1) | stage1, judge, reports |

## Run

**Terminal 1 — API**

```bash
cd veramynd/dashboard
pip install -r requirements.txt
python run.py
```

API: http://127.0.0.1:8765

**Terminal 2 — React UI**

```bash
cd veramynd/dashboard-ui
npm install
npm run dev
```

UI: http://127.0.0.1:5173/projects/el-g1-m2-ga-ela  
Vite proxies `/api` → `http://127.0.0.1:8765`.

Legacy vanilla UI (older pages) is still served at http://127.0.0.1:8765 — prefer the React app.

## Projects

Register projects in [`projects.json`](projects.json):

```json
{
  "id": "el-g1-m2-ga-ela",
  "inputs": { "guide_pdf": "...", "standards_xlsx": "..." },
  "output_dir": "veramynd_parser/output"
}
```

Current registry:

| ID | Role |
|----|------|
| `el-g1-m2-ga-ela` | Batch-1 ready (EL G1M2 × GA ELA) |
| `demo-running` | Fixture: pipeline in progress (stage1 only) |

**None** in the project switcher = no project selected (placeholder for future Ingest). Empty demo projects are not registered.

After editing `projects.json`, call `POST /api/reload` or restart `python run.py`.

## Readiness

Per project, Overview uses:

| State | Meaning |
|-------|---------|
| `empty` | No lessons / standards / judge yet |
| `running` | Partial artifacts (e.g. stage1) |
| `ready` | Judge alignments present |

## API (project-scoped)

Most routes take `?project_id=…`:

- `GET /api/projects` — registry cards  
- `GET /api/overview` — KPIs + readiness + `last_reviewed`  
- `GET /api/lessons/coverage`, `GET /api/lessons/{code}`  
- `GET /api/standards/coverage`, `GET /api/standards/tree`  
- `GET /api/alignments`, `GET /api/alignments/{id}`  
- `GET /api/pipeline` — stage status from artifacts  
- `POST /api/reload` — refresh registry + catalog  
- `POST /api/ingest` — store uploads under `dashboard/uploads/` only (no pipeline run)

## Layout

```
dashboard/
├── api/
│   ├── app.py          # FastAPI routes
│   ├── catalog.py      # Artifact adapters
│   ├── projects.py     # projects.json loader
│   └── schemas.py
├── projects.json
├── fixtures/           # demo-running (and optional empty fixtures)
├── uploads/            # ingest storage only
├── web/                # legacy static UI
├── run.py
└── requirements.txt
```

## Notes

- Metrics must come from artifacts — do not invent accuracy without a corrected master.  
- Quality / gold metrics are API-available when gold files exist; the React Overview does not show a Quality card by default.  
- Client-facing retrieve bar remains **Recall@25** only when discussing retrieve quality.
