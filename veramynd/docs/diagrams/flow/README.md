# Flow diagrams

Black-and-white box/diamond flowcharts (same style as `01_product_flow.png`).

| File | What it shows |
|------|----------------|
| `01_product_flow.png` | Original high-level product vision (older “Stages 2–7 planned” wording) |
| `02_full_pipeline_deep.png` | **Current** deep end-to-end pipeline (all implemented stages) |
| `03_query_funnel_deep.png` | Deep dive: hybrid retrieve → rerank → judge → grounding |
| `02_full_pipeline_deep.mmd` | Mermaid source for #2 |
| `03_query_funnel_deep.mmd` | Mermaid source for #3 |
| `build_deep_flow.py` | Regenerates the deep PNG diagrams |

Regenerate:

```bash
python veramynd/docs/diagrams/flow/build_deep_flow.py
```
