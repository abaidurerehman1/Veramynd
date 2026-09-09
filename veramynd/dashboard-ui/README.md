# Veramynd Dashboard UI

React + TypeScript (Vite) frontend for the curriculum–standards alignment dashboard.

Backend: FastAPI in `../dashboard` (Vite proxies `/api` → API, default **:8000**).

## Run

```bash
# Terminal 1 — API
cd veramynd/dashboard
python run.py

# Terminal 2 — UI
cd veramynd/dashboard-ui
npm install
npm run dev
```

Open http://127.0.0.1:5173/

- Demo: `/projects/el-g1-m2-ga-ela`
- Upload run: `/projects/upload-<batch-id>`
- No selection: `/projects/none/…`

## Pages

| Route | Description |
|-------|-------------|
| `/projects/:id` | **Overview** — empty / partial / ready; real output-folder stages; KPIs after judge |
| `/projects/:id/curriculum` | Lesson list from Stage-1 |
| `/projects/:id/curriculum/:lessonCode` | Lesson detail (agenda, instructional blocks, pages) |
| `/projects/:id/standards` | Standards coverage + tree |
| `/projects/:id/alignments` | Filterable alignments + evidence drawer |
| `/projects/:id/review` | Human review queue |
| `/projects/:id/exports` | Download client / CSV packages |
| `/projects/:id/projects` | Project list — open / delete (logs kept until Clear logs) |
| `/projects/:id/ingestion` | Upload PDF + XLSX; confirm before any pipeline run |
| `/projects/:id/pipeline` | Artifact flow + Complete auto / step-by-step (+ resume) |
| `/projects/:id/logging` | Jobs, stage/lesson view, typed errors, Clear logs |
| `/projects/:id/settings` | Health + catalog reload |

Sidebar groups: **Main** (review surfaces) · **Operations** (ingest / run) · **Account**.

## Project model

One Overview = one project (PDF + XLSX + `output_dir`).

| Source | How it appears |
|--------|----------------|
| `dashboard/projects.json` | Registry cards (e.g. Batch-1 demo) |
| `dashboard/uploads/<batch>/` | Virtual `upload-<batch>` projects after ingest / parse |

UI readiness: **empty** / **running** / **ready** from API.  
Pipeline step wizard marks **Done** from `completed_steps` (disk), then highlights the
next stage for **Confirm & run**. Complete auto becomes **Resume complete pipeline**
when prior stages already have output.

## Stack

- React 19 + React Router  
- Vite 8 (proxies `/api` → local API)  
- TypeScript  

## Scripts

```bash
npm run dev       # local UI (:5173)
npm run build     # production build → dist/
npm run preview   # preview build
```

## Notes

- This React app is the only dashboard UI.
- Deleting a project does not clear Logging; use **Clear logs**.
- Do not invent Quality metrics without a per-project corrected master.
- See [`../dashboard/README.md`](../dashboard/README.md) for API, resume, and stage details.
