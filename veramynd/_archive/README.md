# `_archive/` — non-production parking lot

Files here are **kept for reference** but are **not** part of the production
package surface. Do not import them from `veramynd_parser`. Prefer the CLI
(`veramynd-parser …`) and package modules under `veramynd_parser/veramynd_parser/`.

| Path | Why archived |
|------|----------------|
| `one_off_scripts/` | Ad-hoc audit / Qdrant payload dump scripts from development |
| `docker/docker-compose.qdrant.yml` | Older/alternate compose (volume under `output/qdrant`). Use package-root `docker-compose.yml` instead |
| `notes_scripts_README.md` | Former empty `scripts/` folder note |

## Production layout (keep)

```
veramynd/
  README.md / LICENSE
  data/samples/          # input PDFs / XLSX
  docs/                  # architecture & design
  veramynd_parser/       # installable package + CLI
    veramynd_parser/     # Python package (normalize, chunk, embed, …)
    tests/
    examples/
    output/              # pipeline artifacts (local / CI)
    docker-compose.yml   # Qdrant
    pyproject.toml
  _archive/              # this folder
```
