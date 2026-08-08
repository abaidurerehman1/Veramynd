"""Self-contained HTML audit dashboard from judge JSON + CSV."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .exporter import ReportError, build_rows, collect_judge_files, load_judge_report
from ..text_utils import atomic_write_text


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def write_html_dashboard(
    judge_paths: list[Path | str],
    out_html: Path | str,
    *,
    include_none: bool = True,
    grounded_only: bool = False,
) -> Path:
    """Build a single-file HTML audit view for enterprise ops review."""
    files = collect_judge_files(judge_paths)
    statuses = None if include_none else {"full", "partial"}
    rows, summary = build_rows(files, statuses=statuses, grounded_only=grounded_only)

    lessons: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        lessons.setdefault(row["resource_id"], []).append(row)

    cards = []
    for rid, lesson_rows in sorted(lessons.items()):
        counts = {"full": 0, "partial": 0, "none": 0}
        for r in lesson_rows:
            st = r["matched_status"]
            counts[st] = counts.get(st, 0) + 1
        body_rows = []
        for r in lesson_rows:
            status = r["matched_status"]
            cls = {
                "full": "ok",
                "partial": "warn",
                "none": "bad",
            }.get(status, "")
            body_rows.append(
                "<tr class='{cls}'>"
                "<td>{code}</td><td>{status}</td><td>{conf}</td>"
                "<td>{grounded}</td><td>{page}</td>"
                "<td class='ev'>{evidence}</td><td class='rat'>{rationale}</td>"
                "</tr>".format(
                    cls=cls,
                    code=_esc(r["standard_code"]),
                    status=_esc(status),
                    conf=_esc(r["confidence"]),
                    grounded=_esc(r["grounded"]),
                    page=_esc(r["evidence_page"]),
                    evidence=_esc((r["evidence"] or "")[:280]),
                    rationale=_esc((r["rationale"] or "")[:220]),
                )
            )
        cards.append(
            f"<section class='card'><h2>{_esc(rid)}</h2>"
            f"<p class='meta'>full={counts.get('full',0)} "
            f"partial={counts.get('partial',0)} none={counts.get('none',0)}</p>"
            "<table><thead><tr>"
            "<th>Standard</th><th>Status</th><th>Conf</th><th>Grounded</th>"
            "<th>Page</th><th>Evidence</th><th>Rationale</th>"
            "</tr></thead><tbody>"
            + "".join(body_rows)
            + "</tbody></table></section>"
        )

    # Provenance from first judge file when available.
    provenance = ""
    if files:
        try:
            first = load_judge_report(files[0])
            provenance = (
                f"<p class='meta'>prompt={_esc(first.get('prompt_version'))} "
                f"model={_esc(first.get('judge_model'))} "
                f"sources={len(files)}</p>"
            )
        except ReportError:
            provenance = ""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Veramynd Alignment Audit</title>
<style>
body {{ font-family: Georgia, "Times New Roman", serif; margin: 2rem; background: #f7f4ef; color: #1c1a17; }}
h1 {{ font-size: 1.8rem; margin-bottom: 0.25rem; }}
h2 {{ font-size: 1.2rem; margin: 0 0 0.35rem; }}
.meta {{ color: #5c564c; font-size: 0.95rem; }}
.card {{ background: #fff; border: 1px solid #ddd4c6; padding: 1rem 1.1rem; margin: 1rem 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
th, td {{ border-bottom: 1px solid #ece4d8; text-align: left; vertical-align: top; padding: 0.45rem 0.35rem; }}
th {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; color: #6a6258; }}
tr.ok td:nth-child(2) {{ color: #1f6b3a; font-weight: 700; }}
tr.warn td:nth-child(2) {{ color: #9a5b00; font-weight: 700; }}
tr.bad td:nth-child(2) {{ color: #8a1f1f; font-weight: 700; }}
.ev, .rat {{ max-width: 22rem; }}
</style>
</head>
<body>
<h1>Veramynd Alignment Audit</h1>
{provenance}
<p class="meta">rows={summary.get("row_count")} ·
full={summary.get("by_status_all_verdicts", {}).get("full", 0)} ·
partial={summary.get("by_status_all_verdicts", {}).get("partial", 0)} ·
none={summary.get("by_status_all_verdicts", {}).get("none", 0)}</p>
{"".join(cards)}
<script type="application/json" id="summary">{html.escape(json.dumps(summary), quote=False)}</script>
</body>
</html>
"""
    path = Path(out_html)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, page)
    return path


__all__ = ["write_html_dashboard"]
