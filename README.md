# Veramynd

Curriculum–standards alignment engine (teacher-guide PDF + standards workbook →
auditable lesson × standard verdicts).

All product code lives under [`veramynd/`](veramynd/).

## Layout

```
veramynd/
  frontend/          React + Vite operator UI (:5173)
  backend/           FastAPI API, uploads, jobs (:8000)
  veramynd_parser/   Pipeline package + CLI + .env
  data/samples/      Reference PDF / XLSX
  docs/              Design & flow docs
```

| Layer | Path | Start |
|-------|------|--------|
| **Frontend** | `veramynd/frontend` | `npm run dev` |
| **Backend** | `veramynd/backend` | `python run.py` |
| **Parser** | `veramynd/veramynd_parser` | `pip install -e ".[…]"`, CLI via backend jobs |

## Quick start

```bash
# Terminal 1 — API
cd veramynd/backend
pip install -r requirements.txt
python run.py

# Terminal 2 — UI
cd veramynd/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173/

Optional helpers (from repo root):

```powershell
.\scripts\dev-backend.ps1
.\scripts\dev-frontend.ps1
```

See [`veramynd/README.md`](veramynd/README.md) for pipeline status, gold metrics, and deeper docs.
