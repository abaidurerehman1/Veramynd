# Flow diagrams

Black-and-white box/diamond flowcharts for the **current locked pipeline**
(no lesson chunking).

```text
PDF + Standards XLSX
  → Stage-1 parse/verify (GO/BLOCK)
  → normalize-lessons + normalize-standards
  → embed-standards → Qdrant veramynd_standards
  → retrieve (multi_normalize_focused)
  → judge (assembled v1.1 + Stage-1 grounding)
  → report / client correlation
```

| File | What it shows |
|------|----------------|
| `01_product_flow.png` | High-level product flow (all stages implemented) |
| `02_full_pipeline_deep.png` | Deep end-to-end pipeline |
| `02_parser_flow.png` | Stage-1 parser techniques & fallbacks |
| `03_query_funnel_deep.png` | Retrieve → rerank → judge → grounding funnel |
| `03_verifier_flow.png` | Verifier GO / BLOCK safety net |
| `04_fallback_map.png` | Stage-1 fallback cheat-sheet |
| `05_lesson_pdf_pipeline.png` | Lesson PDF parse path into the locked pipeline |
| `06_full_pipeline_current.png` | CLI two-track view (lesson + standards → judge) |
| `02_full_pipeline_deep.mmd` | Mermaid source for #2 |
| `03_query_funnel_deep.mmd` | Mermaid source for #3 |
| `build_deep_flow.py` | Regenerates all PNG diagrams |

Regenerate:

```bash
python veramynd/docs/diagrams/flow/build_deep_flow.py
```
