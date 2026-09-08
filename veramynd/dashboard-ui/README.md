# Veramynd Dashboard UI

React + TypeScript (Vite) frontend for the curriculum alignment dashboard.

Backend: FastAPI at `http://127.0.0.1:8765` (`veramynd/dashboard`).

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

Open http://127.0.0.1:5173/projects/el-g1-m2-ga-ela

## Pages

| Route | Description |
|-------|-------------|
| `/projects/:id` | Overview — KPIs, alignment mix, coverage, pipeline flow, lesson heat map |
| `/projects/:id/curriculum` | Lessons from `/api/lessons/coverage` (+ lesson detail) |
| `/projects/:id/standards` | Coverage filters + hierarchy tree |
| `/projects/:id/alignments` | Filterable alignments + evidence drawer |
| `/projects/none` | No project selected — Go to Ingest (when Ingest exists) |

Project switcher: search registered projects or choose **None**.

## Project model

One Overview = one project (PDF + XLSX + `output_dir`), from `dashboard/projects.json`.

UI states: **empty** / **running** / **ready** from API `readiness`.  
`Last reviewed` = latest artifact mtime for that project.

## Stack

- React 19 + React Router  
- Vite 8 (proxies `/api` → `:8765`)  
- TypeScript  

## Scripts

```bash
npm run dev       # local UI
npm run build     # production build → dist/
npm run preview   # preview build
```

## Notes

- Prefer this app over the legacy UI at `:8765`.  
- Ingest / Pipeline nav items are still “coming next”.  
- Do not invent Quality metrics in the UI without a per-project corrected master.
