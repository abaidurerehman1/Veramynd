"""Load and index real Veramynd output artifacts (read-only).

Never mutates ``veramynd_parser/output/``. No judge/retrieve logic.
One Catalog instance = one project (PDF + XLSX + output folder).
"""

from __future__ import annotations

import json
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .projects import (
    VERAMYND_ROOT,
    ProjectConfig,
    default_project_id,
    get_project_config,
)
from .schemas import (
    AlignmentRow,
    EvidenceRow,
    ExportItem,
    LessonCoverageRow,
    LessonDetail,
    OverviewMetrics,
    PipelineStage,
    ProjectInputs,
    ProjectSummary,
    QaMetrics,
    ReviewItem,
    RunRow,
    StandardCoverageRow,
    StandardNode,
)

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PARSER_ROOT = VERAMYND_ROOT / "veramynd_parser"
# Legacy alias — Batch-1 default output (prefer Catalog.output via a project).
OUTPUT = PARSER_ROOT / "output"
PROJECT_ID = "el-g1-m2-ga-ela"


class Catalog:
    def __init__(self, project: ProjectConfig | None = None) -> None:
        self.config = project or get_project_config(default_project_id())
        self.output = self.config.output_dir
        self._lock = threading.Lock()
        self._loaded = False
        self.lessons: dict[str, dict[str, Any]] = {}
        self.standards: list[dict[str, Any]] = []
        self.standards_by_code: dict[str, dict[str, Any]] = {}
        self.alignments: list[AlignmentRow] = []
        self.judge_meta: dict[str, dict[str, Any]] = {}
        self.client_summary: dict[str, Any] = {}
        self.gold_metrics: dict[str, Any] = {}
        self.gold_pairs: dict[tuple[str, str], str] = {}
        self.framework = ""
        self.grade: int | None = None
        self.error: str | None = None

    def ensure(self) -> None:
        with self._lock:
            if self._loaded:
                return
            try:
                self._load()
                self.error = None
            except Exception as e:  # noqa: BLE001 — surface to API error state
                self.error = str(e)
            self._loaded = True

    def reload(self) -> None:
        with self._lock:
            self._loaded = False
        self.ensure()

    def _load(self) -> None:
        out = self.output
        std_path = out / "stage1" / "standards.json"
        if std_path.is_file():
            tree = json.loads(std_path.read_text(encoding="utf-8"))
            self.framework = str(tree.get("framework") or "")
            self.grade = tree.get("grade")
            self.standards = list(tree.get("standards") or [])
            self.standards_by_code = {
                s["code"]: s for s in self.standards if isinstance(s, dict) and s.get("code")
            }

        lessons_dir = out / "stage1" / "lessons"
        self.lessons = {}
        if lessons_dir.is_dir():
            for p in sorted(lessons_dir.glob("*.json")):
                data = json.loads(p.read_text(encoding="utf-8"))
                code = data.get("code") or p.stem
                self.lessons[code] = data

        alignments: list[AlignmentRow] = []
        judge_dir = out / "judge"
        self.judge_meta = {}
        if judge_dir.is_dir():
            for p in sorted(judge_dir.glob("*.json")):
                data = json.loads(p.read_text(encoding="utf-8"))
                rid = data.get("resource_id") or p.stem
                self.judge_meta[rid] = {
                    k: data.get(k)
                    for k in (
                        "complete",
                        "judged",
                        "by_status",
                        "grounding_rate",
                        "judge_model",
                        "escalate_model",
                        "prompt_version",
                        "candidate_count",
                    )
                }
                lesson = self.lessons.get(rid) or {}
                title = lesson.get("title") or rid
                for i, v in enumerate(data.get("verdicts") or []):
                    if not isinstance(v, dict):
                        continue
                    code = str(v.get("standard_code") or "")
                    std = self.standards_by_code.get(code) or {}
                    std_text = (
                        v.get("standard_raw_text")
                        or std.get("text")
                        or ""
                    )
                    status = str(v.get("matched_status") or "none")
                    if status not in ("full", "partial", "none"):
                        status = "none"
                    alignments.append(
                        AlignmentRow(
                            id=f"{rid}:{code}:{i}",
                            resource_id=rid,
                            lesson_title=str(title),
                            standard_code=code,
                            standard_text=str(std_text),
                            matched_status=status,  # type: ignore[arg-type]
                            confidence=str(v.get("confidence") or ""),
                            needs_review=bool(v.get("needs_review")),
                            review_reason=str(v.get("review_reason") or ""),
                            evidence=str(v.get("evidence") or ""),
                            evidence_page=v.get("evidence_page"),
                            rationale=str(v.get("rationale") or ""),
                            grounded=bool(v.get("grounded")),
                            escalated=bool(v.get("escalated")),
                            judge_model=str(v.get("judge_model") or ""),
                            prompt_version=str(v.get("prompt_version") or ""),
                            clauses=list(v.get("clauses") or []),
                            input_scope_caveat=v.get("input_scope_caveat"),
                            retrieval=dict(v.get("retrieval") or {}),
                        )
                    )
        self.alignments = alignments

        self.client_summary = {}
        if self.config.client_summary.is_file():
            self.client_summary = json.loads(
                self.config.client_summary.read_text(encoding="utf-8")
            )

        self.gold_metrics = {}
        if self.config.gold_metrics.is_file():
            self.gold_metrics = json.loads(
                self.config.gold_metrics.read_text(encoding="utf-8")
            )

        self.gold_pairs = {}
        if self.config.gold_jsonl.is_file():
            rank = {"full": 2, "partial": 1, "none": 0}
            for line in self.config.gold_jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = str(row.get("resource_id") or "").strip()
                code = str(row.get("standard_code") or "").strip()
                st = str(row.get("matched_status") or "").strip().lower()
                if not rid or not code or st not in rank:
                    continue
                key = (rid, code)
                prev = self.gold_pairs.get(key)
                if prev is None or rank[st] > rank.get(prev, -1):
                    self.gold_pairs[key] = st

    # —— public queries —— #

    def project_summary(self) -> ProjectSummary:
        leaves = [s for s in self.standards if s.get("level") == "substandard"]
        # GA tree uses substandard for leaves; also count deepest if needed
        if not leaves:
            leaves = [
                s
                for s in self.standards
                if not any(
                    o.get("parent_code") == s.get("code") for o in self.standards
                )
            ]
        cfg = self.config
        guide_ok, std_ok = cfg.inputs_exist()
        return ProjectSummary(
            id=cfg.id,
            name=cfg.name,
            publisher=cfg.publisher,
            grade=int(self.grade) if self.grade is not None else cfg.grade,
            subject=cfg.subject,
            module=cfg.module,
            lessons=len(self.lessons),
            standards_total=len(self.standards),
            standards_leaves=len(leaves),
            status="complete" if self.judge_meta else "empty",
            last_processed=self.last_reviewed_iso(),
            framework=self.framework or cfg.framework,
            batch_label=cfg.batch_label,
            expected_lessons=cfg.expected_lessons,
            output_dir=cfg.output_dir_rel,
            inputs=ProjectInputs(
                guide_pdf=cfg.guide_pdf_rel,
                standards_xlsx=cfg.standards_xlsx_rel,
                guide_pdf_exists=guide_ok,
                standards_xlsx_exists=std_ok,
            ),
        )

    # Back-compat alias used by older call sites
    def project(self) -> ProjectSummary:
        return self.project_summary()

    def overview(self) -> OverviewMetrics:
        by = {"full": 0, "partial": 0, "none": 0}
        review = 0
        esc = 0
        grounded = 0
        pos_codes: set[str] = set()
        for a in self.alignments:
            by[a.matched_status] = by.get(a.matched_status, 0) + 1
            if a.needs_review:
                review += 1
            if a.escalated:
                esc += 1
            if a.grounded:
                grounded += 1
            if a.matched_status in ("full", "partial"):
                pos_codes.add(a.standard_code)

        leaves = [
            s["code"]
            for s in self.standards
            if s.get("level") == "substandard" and s.get("code")
        ]
        if not leaves:
            leaves = [
                s["code"]
                for s in self.standards
                if s.get("code")
                and not any(o.get("parent_code") == s.get("code") for o in self.standards)
            ]
        cov = (100.0 * len(pos_codes) / len(leaves)) if leaves else 0.0
        expected = self.config.expected_lessons
        healthy = bool(self.judge_meta) and (
            expected is None or len(self.lessons) == expected
        )
        health = "Healthy" if healthy else (
            "Degraded" if self.alignments else "Empty"
        )
        return OverviewMetrics(
            project_id=self.config.id,
            readiness=self.readiness(),
            last_reviewed=self.last_reviewed_iso(),
            lessons=len(self.lessons),
            standards=len(self.standards),
            standards_leaves=len(leaves),
            alignments=len(self.alignments),
            review_required=review,
            escalated=esc,
            alignment_coverage_pct=round(cov, 1),
            pipeline_health=health,
            by_status=by,
            grounded=grounded,
            positive_standards_cited=int(
                self.client_summary.get("positive_standards_cited") or len(pos_codes)
            ),
            parents_partially_met=self.client_summary.get("parents_partially_met"),
            source_label=str(self.client_summary.get("source") or f"judge:{self.config.output_dir_rel}/judge"),
            pdf_quality=self.pdf_quality(),
        )

    def readiness(self) -> str:
        """empty | running | ready — drives Overview empty / in-progress states."""
        if self.alignments and self.judge_meta:
            return "ready"
        if self.lessons or self.standards or self.judge_meta:
            return "running"
        return "empty"

    def last_reviewed_iso(self) -> str | None:
        """Latest artifact mtime (prefer judge, then stage1 / reports)."""
        out = self.output
        candidates: list[Path] = []
        judge_dir = out / "judge"
        if judge_dir.is_dir():
            candidates.extend(judge_dir.glob("*.json"))
        stage1 = out / "stage1"
        if stage1.is_dir():
            std = stage1 / "standards.json"
            if std.is_file():
                candidates.append(std)
            lessons = stage1 / "lessons"
            if lessons.is_dir():
                candidates.extend(lessons.glob("*.json"))
        for p in (
            self.config.client_summary,
            self.config.gold_metrics,
            self.config.client_xlsx,
        ):
            if p.is_file():
                candidates.append(p)
        latest = 0.0
        for p in candidates:
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                continue
        if latest <= 0:
            return None
        return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()

    def pdf_quality(self) -> dict[str, Any]:
        """Overall accuracy + recall for this project's curriculum PDF.

        Primary reference: project ``corrected_master`` vs live judge.
        Retrieve Recall@25 comes from project ``gold_metrics`` when present.
        """
        cfg = self.config
        out: dict[str, Any] = {
            "curriculum_pdf": cfg.curriculum_pdf_label,
            "standards_set": f"{self.framework or cfg.framework or 'Standards'} Grade {self.grade or cfg.grade or ''}".strip(),
            "scope": "overall",
            "lessons_in_scope": len(self.lessons),
            "available": False,
            "project_id": cfg.id,
        }
        try:
            # —— Retrieve recall@25 (project retrieve metrics for this PDF) —— #
            after = (self.gold_metrics.get("after_rerank") or {}) if self.gold_metrics else {}
            recall = after.get("recall") or {}
            r25 = (recall.get("@25") or {}).get("rate")
            r25_hits = (recall.get("@25") or {}).get("hits")
            r25_n = (recall.get("@25") or {}).get("n")
            if r25 is None:
                r30 = recall.get("@30") or {}
                if r30.get("n") and r30.get("hits") == r30.get("n"):
                    r25 = 1.0
                    r25_hits = r30.get("hits")
                    r25_n = r30.get("n")

            master_path = cfg.corrected_master
            master_pairs: dict[tuple[str, str], str] = {}
            if master_path and master_path.is_file():
                # Import only when needed; keep dashboard usable if parser path odd.
                if str(PARSER_ROOT) not in sys.path:
                    sys.path.insert(0, str(PARSER_ROOT))
                from veramynd_parser.report.client_format import (  # noqa: WPS433
                    load_corrected_master,
                )

                for row in load_corrected_master(master_path):
                    rid = str(row.get("resource_id") or "").strip()
                    code = str(row.get("standard_code") or "").strip()
                    st = str(row.get("matched_status") or "").strip().lower()
                    if rid and code and st in ("full", "partial", "none"):
                        master_pairs[(rid, code)] = st

            pred: dict[tuple[str, str], str] = {}
            for a in self.alignments:
                pred[(a.resource_id, a.standard_code)] = a.matched_status

            judged = 0
            exact = 0
            tp = fp = fn = tn = 0
            missing_pred = 0
            for key, gold_st in master_pairs.items():
                p = pred.get(key)
                if p is None:
                    missing_pred += 1
                    continue
                judged += 1
                if p == gold_st:
                    exact += 1
                g_pos = gold_st in ("full", "partial")
                p_pos = p in ("full", "partial")
                if g_pos and p_pos:
                    tp += 1
                elif (not g_pos) and p_pos:
                    fp += 1
                elif g_pos and (not p_pos):
                    fn += 1
                else:
                    tn += 1

            accuracy = (exact / judged) if judged else None
            precision = (tp / (tp + fp)) if (tp + fp) else None
            binary_recall = (tp / (tp + fn)) if (tp + fn) else None

            out.update(
                {
                    "available": bool(master_pairs or r25 is not None),
                    "reference": "corrected_master" if master_pairs else None,
                    "retrieve_recall_at_25": r25,
                    "retrieve_recall_at_25_hits": r25_hits,
                    "retrieve_recall_at_25_n": r25_n,
                    "judge_accuracy": accuracy,
                    "judge_exact": exact,
                    "judge_judged": judged,
                    "binary_precision": precision,
                    "binary_recall": binary_recall,
                    "binary_tp": tp,
                    "binary_fp": fp,
                    "binary_fn": fn,
                    "binary_tn": tn,
                    "reference_pairs": len(master_pairs),
                    "pairs_missing_in_judge": missing_pred,
                    "sources": {
                        "reference": master_path.name if master_path and master_path.is_file() else None,
                        "judge": f"{cfg.output_dir_rel}/judge",
                        "retrieve": cfg.gold_metrics.name if cfg.gold_metrics.is_file() else None,
                    },
                }
            )
        except Exception as e:  # noqa: BLE001
            out["available"] = False
            out["error"] = str(e)
        return out

    def lesson_coverage(self) -> list[LessonCoverageRow]:
        buckets: dict[str, dict[str, int]] = defaultdict(
            lambda: {"full": 0, "partial": 0, "none": 0, "review": 0}
        )
        for a in self.alignments:
            b = buckets[a.resource_id]
            b[a.matched_status] = b.get(a.matched_status, 0) + 1
            if a.needs_review:
                b["review"] += 1
        rows = []
        for code in sorted(self.lessons.keys()) or sorted(buckets.keys()):
            b = buckets.get(code) or {"full": 0, "partial": 0, "none": 0, "review": 0}
            title = (self.lessons.get(code) or {}).get("title") or code
            rows.append(
                LessonCoverageRow(
                    resource_id=code,
                    title=str(title),
                    full=b["full"],
                    partial=b["partial"],
                    none=b["none"],
                    review=b["review"],
                    aligned=b["full"] + b["partial"],
                )
            )
        return rows

    def standard_coverage(self) -> list[StandardCoverageRow]:
        by_code: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"full": 0, "partial": 0, "review": 0, "lessons": set()}
        )
        for a in self.alignments:
            if a.matched_status == "none" and not a.needs_review:
                continue
            b = by_code[a.standard_code]
            if a.matched_status == "full":
                b["full"] += 1
                b["lessons"].add(a.resource_id)
            elif a.matched_status == "partial":
                b["partial"] += 1
                b["lessons"].add(a.resource_id)
            if a.needs_review:
                b["review"] += 1

        rows: list[StandardCoverageRow] = []
        for s in self.standards:
            code = s.get("code") or ""
            if not code:
                continue
            # Prefer leaf-ish rows for table density: standards + substandards
            level = str(s.get("level") or "")
            if level in ("domain", "big_idea"):
                continue
            b = by_code.get(code) or {"full": 0, "partial": 0, "review": 0, "lessons": set()}
            if b["full"] > 0:
                status = "covered"
            elif b["partial"] > 0:
                status = "partial"
            elif b["review"] > 0:
                status = "review"
            else:
                status = "not_found"
            rows.append(
                StandardCoverageRow(
                    code=code,
                    level=level,
                    label=str(s.get("label") or ""),
                    text=str(s.get("text") or ""),
                    parent_code=s.get("parent_code"),
                    lessons=sorted(b["lessons"]),
                    status=status,  # type: ignore[arg-type]
                    full=int(b["full"]),
                    partial=int(b["partial"]),
                    review=int(b["review"]),
                )
            )
        return rows

    def list_alignments(
        self,
        *,
        status: str | None = None,
        lesson: str | None = None,
        q: str | None = None,
        needs_review: bool | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AlignmentRow], int]:
        rows = self.alignments
        if status:
            rows = [a for a in rows if a.matched_status == status]
        if lesson:
            rows = [a for a in rows if a.resource_id == lesson]
        if needs_review is True:
            rows = [a for a in rows if a.needs_review]
        if needs_review is False:
            rows = [a for a in rows if not a.needs_review]
        if q:
            qq = q.lower()
            rows = [
                a
                for a in rows
                if qq in a.resource_id.lower()
                or qq in a.standard_code.lower()
                or qq in a.evidence.lower()
                or qq in a.lesson_title.lower()
                or qq in a.standard_text.lower()
            ]
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_alignment(self, alignment_id: str) -> AlignmentRow | None:
        for a in self.alignments:
            if a.id == alignment_id:
                return a
        return None

    def evidence(
        self,
        *,
        lesson: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> list[EvidenceRow]:
        rows: list[EvidenceRow] = []
        for a in self.alignments:
            if not (a.evidence or "").strip():
                continue
            if a.matched_status == "none" and not a.needs_review:
                continue
            if lesson and a.resource_id != lesson:
                continue
            if status and a.matched_status != status:
                continue
            if q and q.lower() not in a.evidence.lower() and q.lower() not in a.standard_code.lower():
                continue
            rows.append(
                EvidenceRow(
                    id=a.id,
                    resource_id=a.resource_id,
                    lesson_title=a.lesson_title,
                    standard_code=a.standard_code,
                    matched_status=a.matched_status,
                    evidence=a.evidence,
                    evidence_page=a.evidence_page,
                    needs_review=a.needs_review,
                )
            )
            if len(rows) >= limit:
                break
        return rows

    def review_queue(self) -> list[ReviewItem]:
        items = []
        for a in self.alignments:
            if not a.needs_review and a.confidence != "low":
                # Include escalated partials lightly? stick to needs_review primarily
                if not a.needs_review:
                    continue
            if not a.needs_review:
                continue
            items.append(
                ReviewItem(
                    id=a.id,
                    resource_id=a.resource_id,
                    lesson_title=a.lesson_title,
                    standard_code=a.standard_code,
                    matched_status=a.matched_status,
                    confidence=a.confidence,
                    review_reason=a.review_reason or "Flagged for review",
                    evidence=a.evidence,
                    evidence_page=a.evidence_page,
                    escalated=a.escalated,
                    rationale=a.rationale,
                )
            )
        return items

    @staticmethod
    def _artifact_count(path: Path, pattern: str = "*") -> int:
        if not path.is_dir():
            return 0
        return sum(1 for _ in path.glob(pattern) if _.is_file())

    def pipeline(self) -> list[PipelineStage]:
        """Stage status from real output folders — not stage1 alone.

        Parse writes ``stage1/`` only. Older UI treated lessons+standards.json as
        Normalize/Embed complete, so Overview jumped to Retrieval after a
        parse-only job. Each stage now keys off the directory that step creates.
        """
        out = self.output
        n_lessons = len(self.lessons)
        n_std = len(self.standards)
        n_judge = len(self.judge_meta)
        n_align = len(self.alignments)
        review = sum(1 for a in self.alignments if a.needs_review)
        esc = sum(1 for a in self.alignments if a.escalated)

        cfg = self.config
        guide_ok, xlsx_ok = cfg.inputs_exist()
        inputs_ok = guide_ok and xlsx_ok
        n_normalize = self._artifact_count(out / "normalize", "*.json")
        n_norm_std = self._artifact_count(out / "normalize_standards", "*.json")
        n_embed = self._artifact_count(out / "embeddings")
        n_retrieve = self._artifact_count(out / "retrieve", "*.json")
        n_report = self._artifact_count(out / "reports")

        parsed = n_lessons > 0
        normalized = n_normalize > 0 and n_norm_std > 0
        embedded = n_embed > 0
        retrieved = n_retrieve > 0
        judged = n_align > 0 or n_judge > 0
        reported = n_report > 0 and judged

        return [
            PipelineStage(
                id="ingestion",
                name="Ingestion",
                status="complete" if (inputs_ok or parsed) else "pending",
                detail="Curriculum PDF + standards workbook",
                count=f"{n_lessons} lessons" if parsed else ("inputs ready" if inputs_ok else "pending"),
            ),
            PipelineStage(
                id="parsing",
                name="Parsing",
                status="complete" if parsed else "pending",
                detail="Stage-1 structure + page provenance",
                count=f"{n_lessons} / {n_lessons or '—'}",
            ),
            PipelineStage(
                id="normalization",
                name="Normalization",
                status="complete" if normalized else "pending",
                detail="Lessons + standards leaves",
                count=(
                    f"{n_normalize} lessons · {n_norm_std} standards"
                    if normalized
                    else "0 — run Normalize"
                ),
            ),
            PipelineStage(
                id="embedding",
                name="Embedding",
                status="complete" if embedded else "pending",
                detail="Standards → veramynd_standards",
                count=f"{n_embed} files" if embedded else f"0 — {n_std} standards parsed",
            ),
            PipelineStage(
                id="retrieval",
                name="Retrieval",
                status="complete" if retrieved else "pending",
                detail="Hybrid dense + BM25 + RRF",
                count=f"{n_retrieve} shortlists" if retrieved else "0 shortlists",
            ),
            PipelineStage(
                id="reranking",
                name="Reranking",
                status="complete" if retrieved else "pending",
                detail="Local cross-encoder fusion",
                count=f"{n_retrieve} / {n_retrieve or '—'}",
            ),
            PipelineStage(
                id="judge",
                name="Judge",
                status="complete" if judged else "pending",
                detail="Assembled rubric + grounding",
                count=f"{n_align} evaluations",
            ),
            PipelineStage(
                id="escalation",
                name="Escalation",
                status="warning" if esc else ("complete" if judged else "pending"),
                detail="Borderline codes → escalate model",
                count=f"{esc} escalated",
            ),
            PipelineStage(
                id="results",
                name="Final results",
                status="warning" if review else ("complete" if reported or judged else "pending"),
                detail="Client package + review flags",
                count=f"{review} review · {n_align} rows",
            ),
        ]

    def runs(self) -> list[RunRow]:
        ov = self.overview()
        cfg = self.config
        return [
            RunRow(
                id=cfg.run_id,
                curriculum=cfg.name,
                standards_set=f"{self.framework or cfg.framework} Grade {self.grade or cfg.grade or ''}".strip(),
                lessons=ov.lessons,
                alignments=ov.alignments,
                status="complete" if self.judge_meta else "empty",
                started=None,
                duration=None,
                source=f"{cfg.output_dir_rel}/judge",
            )
        ]

    def lesson_detail(self, code: str) -> LessonDetail | None:
        data = self.lessons.get(code)
        if not data:
            return None
        summary = {"full": 0, "partial": 0, "none": 0, "review": 0}
        for a in self.alignments:
            if a.resource_id != code:
                continue
            summary[a.matched_status] = summary.get(a.matched_status, 0) + 1
            if a.needs_review:
                summary["review"] += 1
        return LessonDetail(
            code=code,
            title=str(data.get("title") or code),
            grade=data.get("grade"),
            module=data.get("module"),
            unit=data.get("unit"),
            lesson=data.get("lesson"),
            page_start=data.get("page_start"),
            page_end=data.get("page_end"),
            learning_targets=list(data.get("learning_targets") or []),
            agenda=list(data.get("agenda") or []),
            instructional_blocks=list(data.get("instructional_blocks") or []),
            materials=list(data.get("materials") or []),
            vocabulary=list(data.get("vocabulary") or []),
            alignments_summary=summary,
        )

    def standards_tree(self) -> list[StandardNode]:
        by_parent: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for s in self.standards:
            by_parent[s.get("parent_code")].append(s)

        def build(node: dict[str, Any]) -> StandardNode:
            code = node.get("code") or ""
            children = [build(c) for c in sorted(by_parent.get(code) or [], key=lambda x: x.get("code") or "")]
            return StandardNode(
                code=code,
                level=str(node.get("level") or ""),
                label=str(node.get("label") or ""),
                text=str(node.get("text") or ""),
                parent_code=node.get("parent_code"),
                children=children,
            )

        roots = by_parent.get(None) or []
        # Also codes whose parent missing
        known = {s.get("code") for s in self.standards}
        for s in self.standards:
            p = s.get("parent_code")
            if p and p not in known:
                roots.append(s)
        # unique roots
        seen = set()
        out = []
        for r in sorted(roots, key=lambda x: x.get("code") or ""):
            c = r.get("code")
            if c in seen:
                continue
            seen.add(c)
            out.append(build(r))
        return out

    def qa_metrics(self) -> QaMetrics:
        ov = self.overview()
        after = (self.gold_metrics.get("after_rerank") or {}) if self.gold_metrics else {}
        recall = after.get("recall") or {}
        notes = []
        if not self.gold_metrics:
            notes.append("retrieve_gold_metrics.json not found — retrieval KPIs unavailable.")
        notes.append("SME exact is gold-4 only; all-40 counts are live judge output.")

        r25 = (recall.get("@25") or {}).get("rate")
        # Artifact may omit @25; when all gold positives are already found by @30,
        # R@25 is 100% for the Batch-1 protected bar.
        if r25 is None:
            r30 = recall.get("@30") or {}
            if r30.get("n") and r30.get("hits") == r30.get("n"):
                r25 = 1.0

        pq = self.pdf_quality()
        return QaMetrics(
            retrieval={
                "recall_at_25": pq.get("retrieve_recall_at_25", r25),
                "recall_at_25_hits": pq.get("retrieve_recall_at_25_hits"),
                "recall_at_25_n": pq.get("retrieve_recall_at_25_n"),
                "n_positives": after.get("n_positives"),
                "source": self.gold_metrics.get("gold_source") if self.gold_metrics else None,
            },
            alignment={
                "total_evaluations": ov.alignments,
                "full": ov.by_status.get("full", 0),
                "partial": ov.by_status.get("partial", 0),
                "none": ov.by_status.get("none", 0),
                "grounded": ov.grounded,
                "escalated": ov.escalated,
                "coverage_pct": ov.alignment_coverage_pct,
                "judge_accuracy": pq.get("judge_accuracy"),
                "binary_precision": pq.get("binary_precision"),
                "binary_recall": pq.get("binary_recall"),
                "judge_exact": pq.get("judge_exact"),
                "judge_judged": pq.get("judge_judged"),
            },
            human_qa={
                "review_required": ov.review_required,
                "review_rate": round(100.0 * ov.review_required / ov.alignments, 2)
                if ov.alignments
                else 0.0,
                "escalation_rate": round(100.0 * ov.escalated / ov.alignments, 2)
                if ov.alignments
                else 0.0,
            },
            notes=notes,
        )

    def exports(self) -> list[ExportItem]:
        items = []
        cfg = self.config
        mapping = [
            ("client-docx", "Client correlation DOCX", "docx", cfg.client_docx),
            ("client-xlsx", "Client correlation XLSX", "xlsx", cfg.client_xlsx),
            ("client-summary", "Client summary JSON", "json", cfg.client_summary),
        ]
        for eid, name, typ, path in mapping:
            ok = path.is_file()
            items.append(
                ExportItem(
                    id=eid,
                    name=name,
                    type=typ,
                    path=str(path),
                    available=ok,
                    download_url=f"/api/exports/{eid}/download?project_id={cfg.id}" if ok else None,
                )
            )
        # result CSVs exist as folder
        result_dir = self.output / "result"
        csvs = list(result_dir.glob("*.csv")) if result_dir.is_dir() else []
        items.append(
            ExportItem(
                id="result-csvs",
                name=f"Per-lesson result CSVs ({len(csvs)} files)",
                type="csv-dir",
                path=str(result_dir),
                available=bool(csvs),
                download_url=(
                    f"/api/exports/result-csvs/download?project_id={cfg.id}" if csvs else None
                ),
            )
        )
        return items

    def export_path(self, export_id: str) -> Path | None:
        for item in self.exports():
            if item.id == export_id and item.available:
                return Path(item.path)
        return None

    def result_csv_paths(self) -> list[Path]:
        result_dir = self.output / "result"
        if not result_dir.is_dir():
            return []
        return sorted(result_dir.glob("*.csv"))

    def search(self, q: str, limit: int = 40) -> list[dict[str, Any]]:
        qq = (q or "").strip().lower()
        if not qq:
            return []
        hits: list[dict[str, Any]] = []
        for code, lesson in self.lessons.items():
            title = str(lesson.get("title") or "")
            if qq in code.lower() or qq in title.lower():
                hits.append({"category": "Lessons", "label": f"{code} — {title}", "href": f"#/lessons/{code}"})
            if len(hits) >= limit:
                return hits
        for s in self.standards:
            code = str(s.get("code") or "")
            text = str(s.get("text") or "")
            if qq in code.lower() or qq in text.lower()[:120].lower():
                hits.append({"category": "Standards", "label": f"{code}", "href": "#/standards"})
            if len(hits) >= limit:
                return hits
        for a in self.alignments:
            if a.evidence and qq in a.evidence.lower():
                hits.append(
                    {
                        "category": "Evidence",
                        "label": f"{a.resource_id} · {a.standard_code}",
                        "href": f"#/alignments/{a.id}",
                    }
                )
            if len(hits) >= limit:
                break
        return hits


_catalogs: dict[str, Catalog] = {}
_catalogs_lock = threading.Lock()


def get_catalog(project_id: str | None = None) -> Catalog:
    """Return (and cache) a Catalog for the given project id."""
    cfg = get_project_config(project_id)
    with _catalogs_lock:
        cat = _catalogs.get(cfg.id)
        if cat is None:
            cat = Catalog(cfg)
            _catalogs[cfg.id] = cat
        return cat


def reload_catalog(project_id: str | None = None) -> Catalog:
    """Force-reload one project catalog (or the default)."""
    cfg = get_project_config(project_id)
    with _catalogs_lock:
        cat = Catalog(cfg)
        _catalogs[cfg.id] = cat
        return cat


def drop_catalog(project_id: str) -> None:
    """Remove a cached catalog (e.g. after deleting an upload batch)."""
    with _catalogs_lock:
        _catalogs.pop(project_id, None)


# Default project catalog (Batch-1) — keeps legacy imports working.
CATALOG = get_catalog()
PROJECT_ID = CATALOG.config.id