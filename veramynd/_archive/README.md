# `_archive/` — non-production parking lot

Files here are **kept for reference** but are **not** part of the production
package surface. Do not import them from `veramynd_parser`. Prefer the CLI
(`veramynd-parser …`) and package modules under `veramynd_parser/veramynd_parser/`.

| Path | Why archived |
|------|----------------|
| `one_off_scripts/` | Ad-hoc audit / Qdrant payload dump scripts from development |
| `scripts_standalone/` | Crosswalk / top50 helper scripts superseded by package CLI |
| `docker/docker-compose.qdrant.yml` | Older/alternate compose. Prefer package-root compose if present |
| `pipeline_experiments/` | Experimental retrieve variants (`retrieve_multiquery`, `retrieve_tuned`, `retrieve_top50`, former `retrieve_gold4` snapshot), `chunks/`, `chunk_embeddings/` — production uses `output/retrieve/`; keep `output/embeddings/embed_standards_*` |
| `reports_scratch/` | One-off `_eval_*` / `_export_*` scripts, top50 review dumps, retrieve diags, duplicate alignment CSVs, P9 `dense_score` health, `_from_master` client correlation copies, `gold4_reports/`, `reference_data/` (crosswalk fixtures), P3 consistency summary |
| `docs_superseded/` | Older SME tracker copy, pipeline-review notes, PDF snapshot of an older client DOCX |
| `prompts_unused/` | Legacy `align_judge_v1.md` + unused `align_judge_batch_addendum.md` (live prompt is `assembled_judge_prompt.md`) |
| `notes_scripts_README.md` | Former empty `scripts/` folder note |

## Production layout (keep)

```
veramynd/
  README.md / LICENSE
  data/samples/              # input PDFs / XLSX
  docs/                      # architecture, goldset, client templates, master/tracker
  veramynd_parser/           # installable package + CLI
    veramynd_parser/         # Python package
      prompts/
        assembled_judge_prompt.md   # live judge
        normalize_*.md
        align_judge_batch_addendum.md
    tests/
    examples/
    output/                  # production pipeline artifacts (see output/README.md)
    pyproject.toml
  _archive/                  # this folder
```

## Production `output/` (do not archive)

| Path | Role |
|------|------|
| `stage1/` | Locked Batch-1 Stage-1 lessons + standards |
| `normalize/` / `normalize_standards/` | Normalized lessons + standards leaves |
| `retrieve/` | All-40 shortlist + locked gold-4 R@25 bar |
| `judge/` | Live verdicts |
| `result/` | Per-lesson CSVs |
| `reports/` | All-40 client correlation DOCX/XLSX + gold-set / R@25 metrics |
| `embeddings/` | Standards embed manifests only (`veramynd_standards`) |
