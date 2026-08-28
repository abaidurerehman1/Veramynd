"""Regenerate black-and-white flow PNGs for the current locked Veramynd pipeline.

No lesson chunking. Path:
  PDF+XLSX → parse/verify → normalize → embed-standards → retrieve → judge → report

Run from repo root or this folder:
  python veramynd/docs/diagrams/flow/build_deep_flow.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
W = 1100
BG = (255, 255, 255)
INK = (20, 20, 20)
SOFT = (90, 90, 90)
FILL = (248, 248, 248)
ACCENT = (230, 230, 230)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = font(22, bold=True)
F_H = font(14, bold=True)
F_B = font(12)
F_S = font(11)


def measure(draw: ImageDraw.ImageDraw, text: str, f) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=f)
    return box[2] - box[0], box[3] - box[1]


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if measure(draw, trial, f)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def box(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    lines: list[str] | None = None,
    *,
    diamond: bool = False,
) -> tuple[int, int, int, int]:
    """Draw a rectangle (or diamond) and return (cx, top, bottom, mid_y)."""
    if diamond:
        pts = [(x + w // 2, y), (x + w, y + h // 2), (x + w // 2, y + h), (x, y + h // 2)]
        draw.polygon(pts, fill=FILL, outline=INK)
        tw, th = measure(draw, title, F_B)
        draw.text((x + (w - tw) // 2, y + (h - th) // 2), title, fill=INK, font=F_B)
        return x + w // 2, y, y + h, y + h // 2

    draw.rectangle([x, y, x + w, y + h], fill=FILL, outline=INK, width=2)
    pad = 10
    ty = y + pad
    for i, line in enumerate([title] + (lines or [])):
        f = F_H if i == 0 else F_S
        for wrapped in wrap(draw, line, f, w - 2 * pad):
            draw.text((x + pad, ty), wrapped, fill=INK if i == 0 else SOFT, font=f)
            ty += measure(draw, wrapped, f)[1] + 3
    return x + w // 2, y, y + h, y + h // 2


def arrow(draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, label: str = "") -> None:
    """Draw a connector with an arrowhead at (x2, y2)."""
    draw.line([(x1, y1), (x2, y2)], fill=INK, width=2)
    dx, dy = x2 - x1, y2 - y1
    if abs(dy) >= abs(dx):
        # mostly vertical
        if dy >= 0:
            draw.polygon([(x2, y2), (x2 - 6, y2 - 10), (x2 + 6, y2 - 10)], fill=INK)
        else:
            draw.polygon([(x2, y2), (x2 - 6, y2 + 10), (x2 + 6, y2 + 10)], fill=INK)
    else:
        if dx >= 0:
            draw.polygon([(x2, y2), (x2 - 10, y2 - 6), (x2 - 10, y2 + 6)], fill=INK)
        else:
            draw.polygon([(x2, y2), (x2 + 10, y2 - 6), (x2 + 10, y2 + 6)], fill=INK)
    if label:
        tw, th = measure(draw, label, F_S)
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
        draw.rectangle([mx - tw // 2 - 4, my - th - 8, mx + tw // 2 + 4, my - 2], fill=BG)
        draw.text((mx - tw // 2, my - th - 6), label, fill=INK, font=F_S)


def v_arrow(draw: ImageDraw.ImageDraw, cx: int, y1: int, y2: int, label: str = "") -> None:
    """Short vertical connector between stacked boxes."""
    if y2 <= y1 + 4:
        return
    arrow(draw, cx, y1, cx, y2, label)


def elbow(
    draw: ImageDraw.ImageDraw,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    label: str = "",
) -> None:
    """Right-angle connector: down/side then into target."""
    mid_y = (y1 + y2) // 2 if abs(y2 - y1) > 20 else y1
    draw.line([(x1, y1), (x1, mid_y)], fill=INK, width=2)
    draw.line([(x1, mid_y), (x2, mid_y)], fill=INK, width=2)
    arrow(draw, x2, mid_y, x2, y2, label)


def branch_side(
    draw: ImageDraw.ImageDraw,
    tip_x: int,
    tip_y: int,
    box_x: int,
    box_y: int,
    box_w: int,
    box_h: int,
    *,
    side: str,
    label: str = "",
) -> None:
    """Connect diamond tip into a side box (same row or below via elbow).

    side='left'  → arrow into the box's right edge
    side='right' → arrow into the box's left edge
    """
    box_mid = box_y + box_h // 2
    if side == "left":
        edge_x = box_x + box_w
        target_x = edge_x
    else:
        edge_x = box_x
        target_x = edge_x

    if abs(box_mid - tip_y) <= 8:
        # same row — straight horizontal into the box edge
        arrow(draw, tip_x, tip_y, target_x, box_mid)
    else:
        # elbow: across at tip_y, then down/up into box mid
        draw.line([(tip_x, tip_y), (target_x, tip_y)], fill=INK, width=2)
        arrow(draw, target_x, tip_y, target_x, box_mid)

    if label:
        tw, th = measure(draw, label, F_S)
        if side == "left":
            lx = (tip_x + target_x) // 2 - tw // 2
        else:
            lx = (tip_x + target_x) // 2 - tw // 2
        ly = min(tip_y, box_mid) - th - 6
        draw.rectangle([lx - 3, ly - 1, lx + tw + 3, ly + th + 1], fill=BG)
        draw.text((lx, ly), label, fill=INK, font=F_S)


def section_banner(draw: ImageDraw.ImageDraw, y: int, text: str) -> int:
    draw.rectangle([40, y, W - 40, y + 28], fill=ACCENT, outline=INK, width=1)
    tw, th = measure(draw, text, F_H)
    draw.text(((W - tw) // 2, y + (28 - th) // 2), text, fill=INK, font=F_H)
    return y + 28


def save(img: Image.Image, name: str) -> None:
    path = OUT / name
    img.save(path, "PNG")
    print(f"wrote {path}")


def build_01_product_flow() -> None:
    h = 980
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "1. Full Product Flow — Current Locked Pipeline"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 24), title, fill=INK, font=F_TITLE)

    y = 70
    section_banner(d, y, "INPUTS")
    y += 40
    lx, _, lbot, _ = box(d, 120, y, 360, 70, "Teacher Guide PDF", ["EL-style / generic Stage-1 route"])
    rx, _, rbot, _ = box(d, 620, y, 360, 70, "Standards XLSX", ["Code | Standard Text | Notes"])
    y = max(lbot, rbot) + 28
    v_arrow(d, lx, lbot, y)
    v_arrow(d, rx, rbot, y)

    section_banner(d, y, "STAGE 1 — PARSE + VERIFY  [IMPLEMENTED]")
    y += 40
    mx, _, pbot, _ = box(d, 80, y, 940, 90, "Separate lessons → Divide each lesson → Parse standards tree", [
        "Docling primary · PyMuPDF fallback · dotted grade-prefixed codes · GO / BLOCK gate"
    ])
    y = pbot + 28
    v_arrow(d, mx, pbot, y)

    dia_x, dia_w, dia_h = 380, 340, 80
    cx, _, bot, mid = box(d, dia_x, y, dia_w, dia_h, "Verifier: any hard FAIL?", diamond=True)
    # YES → BLOCK beside diamond (same row) so the arrow reaches the box
    bx, by, bw, bh = 60, y, 240, dia_h
    box(d, bx, by, bw, bh, "YES → BLOCK", ["Do not trust. Withhold lessons."])
    branch_side(d, cx - dia_w // 2, mid, bx, by, bw, bh, side="left", label="YES")

    y = bot + 28
    v_arrow(d, cx, bot, y, "NO → GO")

    section_banner(d, y, "DOWNSTREAM — LOCKED PATH  [IMPLEMENTED]")
    y += 40
    mx, _, dbot, _ = box(d, 80, y, 940, 120, "Normalize → Embed standards → Retrieve → Judge → Report", [
        "normalize-lessons + normalize-standards",
        "Qdrant veramynd_standards only (no lesson chunks)",
        "multi_normalize_focused retrieve · assembled judge v1.1 · Stage-1 grounding",
        "CSV / HTML + client correlation DOCX/XLSX",
    ])
    y = dbot + 28
    v_arrow(d, mx, dbot, y)
    box(d, 250, y, 600, 60, "OUTPUT: trusted alignment artifacts", [
        "output/judge · output/result · output/reports"
    ])
    save(img.crop((0, 0, W, y + 100)), "01_product_flow.png")


def build_02_full_pipeline_deep() -> None:
    h = 1760
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "1. Full Product Flow (Deep) — Current Locked Pipeline"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 20), title, fill=INK, font=F_TITLE)
    sub = "No lesson chunking · queries from normalize · judge grounds on Stage-1 raw text"
    sw, _ = measure(d, sub, F_S)
    d.text(((W - sw) // 2, 48), sub, fill=SOFT, font=F_S)

    y = 80
    section_banner(d, y, "INPUTS")
    y += 40
    lx, _, lbot, _ = box(d, 90, y, 420, 70, "Teacher Guide PDF", ["K–12 curriculum lessons"])
    rx, _, rbot, _ = box(d, 590, y, 420, 70, "Standards XLSX", ["GA ELA Grade 1 leaves (reference)"])
    y = max(lbot, rbot) + 28
    v_arrow(d, lx, lbot, y)
    v_arrow(d, rx, rbot, y)

    section_banner(d, y, "STAGE 1 — PARSE  [IMPLEMENTED]")
    y += 40
    lx, _, lbot, _ = box(d, 90, y, 420, 110, "PDF path", [
        "Separate lessons (bookmarks → font header)",
        "Divide: agenda · steps · materials · vocab",
        "Docling primary · PyMuPDF fallback",
    ])
    rx, _, rbot, _ = box(d, 590, y, 420, 110, "Standards path", [
        "Parse tree by dotted code depth",
        "One grade per sheet · digit/K prefix",
        "Notes ignored for level",
    ])
    y = max(lbot, rbot) + 28
    # merge into verifier
    mx = W // 2
    d.line([(lx, lbot), (lx, y - 10)], fill=INK, width=2)
    d.line([(rx, rbot), (rx, y - 10)], fill=INK, width=2)
    d.line([(lx, y - 10), (rx, y - 10)], fill=INK, width=2)
    arrow(d, mx, y - 10, mx, y)

    dia_x, dia_w, dia_h = 360, 380, 90
    cx, _, bot, mid = box(d, dia_x, y, dia_w, dia_h, "Verifier: any hard FAIL?", diamond=True)
    # YES → BLOCK beside diamond (same row)
    bx, by, bw, bh = 40, y, 250, dia_h
    box(d, bx, by, bw, bh, "YES → BLOCK", [
        "Do not trust.", "Withhold lessons. Report only."
    ])
    branch_side(d, cx - dia_w // 2, mid, bx, by, bw, bh, side="left", label="YES")

    go_y = bot + 28
    v_arrow(d, cx, bot, go_y, "NO → GO")
    y = go_y

    section_banner(d, y, "NORMALIZE  [IMPLEMENTED]")
    y += 40
    mx, _, nbot, _ = box(d, 90, y, 920, 100, "normalize-lessons + normalize-standards", [
        "Lessons → NormalizedLesson (skills, domains, student actions)",
        "Standards → leaf/substandard records (raw_text kept for judge)",
        "OpenAI gpt-4.1-mini · content-addressed cache · fail loud",
    ])
    y = nbot + 28
    v_arrow(d, mx, nbot, y)

    section_banner(d, y, "EMBED + INDEX  [IMPLEMENTED]")
    y += 40
    mx, _, ebot, _ = box(d, 90, y, 920, 100, "embed-standards → Qdrant veramynd_standards", [
        "text-embedding-3-large · 3072-d Cosine",
        "Leaf-only filter · rich retrieval text",
        "No veramynd_chunks · no lesson chunk embeds",
    ])
    y = ebot + 28
    v_arrow(d, mx, ebot, y)

    section_banner(d, y, "RETRIEVE  [IMPLEMENTED]")
    y += 40
    mx, _, rbot, _ = box(d, 90, y, 920, 110, "Lesson → standards shortlist", [
        "Query arms from NormalizedLesson (multi_normalize_focused)",
        "Dense (Qdrant) + BM25 → RRF / top_k_sum merge",
        "Local CE rerank · judge shortlist ~25–50",
        "Gold bar: R@25 = 100% on locked gold-4",
    ])
    y = rbot + 28
    v_arrow(d, mx, rbot, y)

    section_banner(d, y, "JUDGE + GROUNDING  [IMPLEMENTED]")
    y += 40
    mx, _, jbot, _ = box(d, 90, y, 920, 120, "assembled_judge_prompt.md v1.1", [
        "Anthropic batch + Opus escalate-batch",
        "full / partial / none + verbatim evidence quote",
        "Grounding: quote must appear in Stage-1 lesson raw text",
        "Ungrounded / empty quote → force none (fail closed)",
    ])
    y = jbot + 28
    v_arrow(d, mx, jbot, y)

    section_banner(d, y, "REPORT  [IMPLEMENTED]")
    y += 40
    mx, _, pbot, _ = box(d, 90, y, 920, 110, "Trusted alignment artifacts", [
        "output/judge/*.json · output/result/*.csv",
        "CSV + HTML audit · gold metrics",
        "Client correlation DOCX/XLSX with skill-named parent roll-ups",
        "Gold-4 vs SME 20/20 · vs corrected master ~93%",
    ])
    y = pbot + 28
    v_arrow(d, mx, pbot, y)
    box(d, 250, y, 600, 55, "OUTPUT ready for review / client delivery")
    save(img.crop((0, 0, W, y + 90)), "02_full_pipeline_deep.png")


def build_03_query_funnel() -> None:
    h = 1280
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "2. Query Funnel Deep Dive — Lesson → Standards"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 22), title, fill=INK, font=F_TITLE)
    sub = "Current path: NormalizedLesson queries (no lesson_chunk)"
    sw, _ = measure(d, sub, F_S)
    d.text(((W - sw) // 2, 50), sub, fill=SOFT, font=F_S)

    y = 90
    mx, _, sbot, _ = box(d, 200, y, 700, 70, "START: NormalizedLesson query arms", [
        "multi_normalize_focused · competency / skills / actions"
    ])
    y = sbot + 28
    v_arrow(d, mx, sbot, y)

    # split to two arms
    arm_y = y
    lx, _, lbot, _ = box(d, 80, arm_y, 420, 110, "DENSE ARM", [
        "Embed query → veramynd_standards",
        "Cosine top ~50",
        "Reject zero query vectors",
    ])
    rx, _, rbot, _ = box(d, 600, arm_y, 420, 110, "BM25 ARM", [
        "Tokenize query",
        "Score leaf embed text",
        "Word-overlap top ~50",
    ])
    # fork from start into arms
    fork = sbot + 14
    d.line([(mx, sbot), (mx, fork)], fill=INK, width=2)
    d.line([(lx, fork), (rx, fork)], fill=INK, width=2)
    arrow(d, lx, fork, lx, arm_y)
    arrow(d, rx, fork, rx, arm_y)

    y = max(lbot, rbot) + 28
    # merge into RRF
    d.line([(lx, lbot), (lx, y - 10)], fill=INK, width=2)
    d.line([(rx, rbot), (rx, y - 10)], fill=INK, width=2)
    d.line([(lx, y - 10), (rx, y - 10)], fill=INK, width=2)
    arrow(d, mx, y - 10, mx, y)

    mx, _, mbot, _ = box(d, 200, y, 700, 70, "RRF / top_k_sum merge → over-include pool", [
        "Recall-oriented fusion across arms"
    ])
    y = mbot + 28
    v_arrow(d, mx, mbot, y)

    mx, _, cbot, _ = box(d, 200, y, 700, 70, "Local CE rerank → judge shortlist ~25–50", [
        "bge-reranker · shortlist fusion / rescue slots off"
    ])
    y = cbot + 28
    v_arrow(d, mx, cbot, y)

    mx, _, jbot, _ = box(d, 200, y, 700, 90, "JUDGE shortlist", [
        "Stage-1 raw lesson + standard raw_text",
        "assembled prompt v1.1 · Anthropic batch + escalate",
        "full / partial / none + evidence quote",
    ])
    y = jbot + 28
    v_arrow(d, mx, jbot, y)

    dia_x, dia_w, dia_h = 360, 380, 90
    cx, _, bot, mid = box(d, dia_x, y, dia_w, dia_h, "Quote grounded in Stage-1 lesson?", diamond=True)
    # NO → force none beside diamond; still feeds ship as none
    bx, by, bw, bh = 40, y, 260, dia_h
    box(d, bx, by, bw, bh, "NO → force none", ["Keep quote for audit"])
    branch_side(d, cx - dia_w // 2, mid, bx, by, bw, bh, side="left", label="NO")

    y = bot + 28
    v_arrow(d, cx, bot, y, "YES")
    # also route forced-none into ship (verdict still written)
    ship_top = y
    elbow(d, bx + bw // 2, by + bh, W // 2, ship_top)
    box(d, 200, y, 700, 70, "SHIP VERDICT → CSV / HTML / client DOCX+XLSX", [
        "judge_model · prompt_version · ranks · grounded flag"
    ])
    save(img.crop((0, 0, W, y + 100)), "03_query_funnel_deep.png")


def build_06_full_pipeline_current() -> None:
    """Two-track CLI pipeline with explicit arrow connections."""
    h = 1600
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "Veramynd — Full Locked Pipeline (CLI)"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 18), title, fill=INK, font=F_TITLE)
    sub = "veramynd-parser · no chunk-lessons / embed-chunks"
    sw, _ = measure(d, sub, F_S)
    d.text(((W - sw) // 2, 46), sub, fill=SOFT, font=F_S)

    y = 80
    section_banner(d, y, "LESSON TRACK                          |                          STANDARDS TRACK")
    y += 40

    # Row 0: inputs
    lx, _, lbot, _ = box(d, 60, y, 480, 55, "Teacher Guide PDF")
    rx, _, rbot, _ = box(d, 560, y, 480, 55, "Standards XLSX")
    y = max(lbot, rbot) + 28
    v_arrow(d, lx, lbot, y)
    v_arrow(d, rx, rbot, y)

    # Row 1: export / stds
    lx, _, lbot, _ = box(d, 60, y, 480, 85, "1. export / verify", [
        "Docling + PyMuPDF · GO/BLOCK",
        "output/stage1/lessons + standards.json",
    ])
    rx, _, rbot, _ = box(d, 560, y, 480, 85, "1. stds / export --standards", [
        "GradeStandards tree",
        "dotted hierarchy codes",
    ])
    y = max(lbot, rbot) + 28
    v_arrow(d, lx, lbot, y)
    v_arrow(d, rx, rbot, y)

    # Row 2: normalize
    lx, _, lbot, _ = box(d, 60, y, 480, 85, "2. normalize-lessons", [
        "OpenAI · ELA schema · cache",
        "output/normalize/",
    ])
    rx, _, rbot, _ = box(d, 560, y, 480, 85, "2. normalize-standards", [
        "OpenAI · leaves only",
        "output/normalize_standards/",
    ])
    y = max(lbot, rbot) + 36

    # Merge into embed
    mx = W // 2
    # lines from both normalize bottoms into embed top
    embed_top = y
    draw_merge = d
    draw_merge.line([(lx, lbot), (lx, embed_top - 8)], fill=INK, width=2)
    draw_merge.line([(rx, rbot), (rx, embed_top - 8)], fill=INK, width=2)
    draw_merge.line([(lx, embed_top - 8), (rx, embed_top - 8)], fill=INK, width=2)
    arrow(d, mx, embed_top - 8, mx, embed_top)

    mx, _, ebot, _ = box(d, 310, y, 480, 85, "3. embed-standards", [
        "OpenAI + Qdrant veramynd_standards",
        "leaf-only · rich retrieval text",
    ])
    y = ebot + 28
    v_arrow(d, mx, ebot, y)

    mx, _, rbot, _ = box(d, 150, y, 800, 100, "4. retrieve (batch_align_all / retrieve-standards)", [
        "Queries from NormalizedLesson (multi_normalize_focused)",
        "Dense + BM25 → RRF → CE rerank → shortlist",
        "output/retrieve/",
    ])
    y = rbot + 28
    v_arrow(d, mx, rbot, y)

    mx, _, jbot, _ = box(d, 150, y, 800, 110, "5. judge-standards", [
        "assembled_judge_prompt.md v1.1",
        "Anthropic batch + escalate · Stage-1 raw grounding",
        "output/judge/",
    ])
    y = jbot + 28
    v_arrow(d, mx, jbot, y)

    mx, _, pbot, _ = box(d, 150, y, 800, 100, "6. report / client-correlation", [
        "CSV + HTML · gold metrics",
        "Client DOCX/XLSX skill-named parent roll-ups",
        "output/reports/ · output/result/",
    ])
    y = pbot + 28
    v_arrow(d, mx, pbot, y)

    mx, _, bbot, _ = box(d, 200, y, 700, 70, "Locked bars", [
        "Retrieve R@25 = 100% · Gold-4 vs SME 20/20 · vs master ~93%"
    ])
    y = bbot + 24
    note = "Hard gate: Stage-1 GO before normalize. Soft gate: lesson provenance on judge."
    nw, _ = measure(d, note, F_S)
    d.text(((W - nw) // 2, y), note, fill=SOFT, font=F_S)
    save(img.crop((0, 0, W, y + 50)), "06_full_pipeline_current.png")


def build_02_parser_flow() -> None:
    h = 1400
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "2. Stage 1 Parser — techniques & fallbacks"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 22), title, fill=INK, font=F_TITLE)

    y = 70
    steps = [
        ("START: CLI", ["guide · stds · verify · export"]),
        ("Load Config", ["engine · ocr_mode · fonts · section names"]),
        ("Open Teacher Guide PDF", ["stds: openpyxl · dotted hierarchy → GradeStandards"]),
        ("engine == docling?", ["YES → Docling path", "NO → FALLBACK A: pymupdf"]),
        ("OCR policy", ["auto / on / off · text-layer detection"]),
        ("PDF has bookmarks?", ["YES → PRIMARY separation", "NO → FALLBACK B: separate_by_font"]),
        ("Divide content", ["PRIMARY: Docling labels", "FALLBACK C: 3-tier fonts"]),
        ("Lesson objects → TeacherGuide", ["agenda · blocks+steps · materials · vocab"]),
        ("Next: Verifier safety net", ["GO / BLOCK before normalize"]),
    ]
    prev_bot = None
    prev_cx = W // 2
    for title_s, lines in steps:
        h_box = 70 + 14 * max(0, len(lines) - 1)
        if prev_bot is not None:
            v_arrow(d, prev_cx, prev_bot, y)
        cx, _, bot, _ = box(d, 180, y, 740, h_box, title_s, lines)
        prev_bot, prev_cx = bot, cx
        y = bot + 28
    save(img.crop((0, 0, W, y + 20)), "02_parser_flow.png")


def build_03_verifier_flow() -> None:
    h = 1050
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "3. Verifier safety net — GO / BLOCK"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 22), title, fill=INK, font=F_TITLE)

    y = 70
    mx, _, ibot, _ = box(d, 180, y, 740, 70, "Input: TeacherGuide + standards + expected lesson count")
    y = ibot + 28
    v_arrow(d, mx, ibot, y)

    mx, _, hbot, _ = box(d, 180, y, 740, 100, "Hard checks (FAIL → BLOCK)", [
        "Lesson count · page partition · order · unique ids",
        "Materials present · agenda/body integrity · steps present",
    ])
    y = hbot + 28
    v_arrow(d, mx, hbot, y)

    mx, _, sbot, _ = box(d, 180, y, 740, 80, "Soft checks (WARN still GO)", [
        "Timing band · vocab presence · cross-engine notes"
    ])
    y = sbot + 28
    v_arrow(d, mx, sbot, y)

    dia_x, dia_w, dia_h = 360, 380, 90
    cx, _, bot, mid = box(d, dia_x, y, dia_w, dia_h, "Any hard FAIL?", diamond=True)
    # BLOCK / GO beside diamond so horizontal arrows land on the boxes
    bx, by, bw, bh = 40, y, 260, dia_h
    gx, gy, gw, gh = 800, y, 260, dia_h
    box(d, bx, by, bw, bh, "BLOCK", [
        "Withhold trusted lessons/", "Write report + verdict only"
    ])
    box(d, gx, gy, gw, gh, "GO", [
        "Write lessons/ + standards.json", "Unlock normalize → judge"
    ])
    branch_side(d, cx - dia_w // 2, mid, bx, by, bw, bh, side="left", label="YES")
    branch_side(d, cx + dia_w // 2, mid, gx, gy, gw, gh, side="right", label="NO")

    y = max(by + bh, gy + gh, bot) + 28
    v_arrow(d, gx, gy + gh, y)
    box(d, 180, y, 740, 70, "Downstream trust_gate", [
        "normalize / retrieve / judge refuse non-GO unless --allow-unverified"
    ])
    save(img.crop((0, 0, W, y + 100)), "03_verifier_flow.png")


def build_04_fallback_map() -> None:
    h = 900
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "4. Fallback map — Stage 1 resilience"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 22), title, fill=INK, font=F_TITLE)

    y = 70
    rows = [
        ("PRIMARY engine", "Docling (labels + tables, cached)"),
        ("FALLBACK A", "engine=pymupdf — skip Docling entirely"),
        ("OCR", "auto: off if text layer, on if scanned"),
        ("PRIMARY separation", "PDF bookmarks → half-open page spans"),
        ("FALLBACK B", "separate_by_font — Unit N Lesson N headers"),
        ("PRIMARY division", "Docling section_header + TableFormer"),
        ("FALLBACK C", "3-tier fonts (~13 / 11 / 9.5 pt)"),
        ("After GO", "normalize → embed-standards → retrieve → judge"),
    ]
    for left, right in rows:
        box(d, 80, y, 300, 55, left)
        box(d, 420, y, 600, 55, right)
        arrow(d, 380, y + 27, 420, y + 27)
        y += 75
    save(img.crop((0, 0, W, y + 40)), "04_fallback_map.png")


def build_05_lesson_pdf_pipeline() -> None:
    h = 1100
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    title = "Lesson PDF Parse Pipeline (Stage 1)"
    tw, _ = measure(d, title, F_TITLE)
    d.text(((W - tw) // 2, 22), title, fill=INK, font=F_TITLE)
    sub = "Feeds locked path: normalize → embed-standards → retrieve → judge"
    sw, _ = measure(d, sub, F_S)
    d.text(((W - sw) // 2, 50), sub, fill=SOFT, font=F_S)

    y = 90
    steps = [
        ("Lesson PDF", ["Teacher Guide, untagged"]),
        ("Docling parse (PRIMARY)", ["labels · tables · content-addressed cache"]),
        ("VISION / OCR FALLBACK", ["ocr_mode auto|on|off"]),
        ("Recover structure", ["1 bookmarks · 2 headings · 3 font hierarchy"]),
        ("Cover fields", ["standards · targets · agenda · materials · vocab"]),
        ("Body fields", ["instructional_blocks + steps"]),
        ("Pydantic contract", ["TeacherGuide → Unit[] → Lesson"]),
        ("verify() safety net", ["GO unlocks normalize; BLOCK withholds"]),
    ]
    prev_bot = None
    prev_cx = W // 2
    for t, lines in steps:
        if prev_bot is not None:
            v_arrow(d, prev_cx, prev_bot, y)
        cx, _, bot, _ = box(d, 200, y, 700, 70, t, lines)
        prev_bot, prev_cx = bot, cx
        y = bot + 28
    save(img.crop((0, 0, W, y + 30)), "05_lesson_pdf_pipeline.png")

def main() -> None:
    build_01_product_flow()
    build_02_full_pipeline_deep()
    build_02_parser_flow()
    build_03_query_funnel()
    build_03_verifier_flow()
    build_04_fallback_map()
    build_05_lesson_pdf_pipeline()
    build_06_full_pipeline_current()
    print("done")


if __name__ == "__main__":
    main()
