(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const page = $("#page");
  const crumbs = $("#crumbs");
  const workspaceChip = $("#workspaceChip");
  const appShell = $("#app");
  const drawer = $("#drawer");
  const drawerPanel = $("#drawerPanel");
  const searchPop = $("#searchPop");

  const state = {
    project: null,
    overview: null,
  };

  function toggleNav() {
    appShell?.classList.toggle("nav-collapsed");
  }

  async function api(path) {
    const res = await fetch(path);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }
    return res.json();
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function badge(status) {
    const s = (status || "").toLowerCase();
    const cls =
      s === "full" || s === "covered" || s === "complete" || s === "healthy" || s === "ok"
        ? "full"
        : s === "partial" || s === "warning" || s === "warn" || s === "review"
          ? "partial"
          : s === "none" || s === "not_found" || s === "failed" || s === "bad"
            ? "none"
            : s === "skipped"
              ? "skipped"
              : "neutral";
    return `<span class="badge ${cls}">${esc((status || "").toUpperCase())}</span>`;
  }

  function pageHeader(title, subtitle, actionsHtml = "") {
    return `
      <div class="page-header">
        <div>
          <h1>${esc(title)}</h1>
          <p>${esc(subtitle)}</p>
        </div>
        <div class="header-actions">${actionsHtml}</div>
      </div>`;
  }

  function empty(title, body, action = "") {
    return `<div class="empty"><h3>${esc(title)}</h3><p>${esc(body)}</p>${action}</div>`;
  }

  function errorBox(err) {
    return `<div class="error-box"><h3>Unable to load data</h3><p>${esc(err.message || err)}</p>
      <button class="btn" onclick="location.reload()">Retry</button></div>`;
  }

  function setCrumbs(parts) {
    if (crumbs) crumbs.textContent = ["Veramynd", ...parts].join(" / ");
    const greet = $("#greetTitle");
    if (greet) {
      const hour = new Date().getHours();
      const hi = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
      greet.textContent = hi;
    }
  }

  function setActiveNav(key) {
    $$(".sidebar a[data-nav]").forEach((a) => {
      a.classList.toggle("active", a.dataset.nav === key);
    });
  }

  function closeDrawer() {
    drawer.hidden = true;
    drawerPanel.innerHTML = "";
  }

  function openDrawer(html) {
    drawer.hidden = false;
    drawerPanel.innerHTML = html;
  }

  async function showAlignmentDrawer(id) {
    try {
      const a = await api(`/api/alignments/${encodeURIComponent(id)}`);
      const clauses = (a.clauses || [])
        .map(
          (c) =>
            `<li><strong>${c.met ? "Met" : "Unmet"}:</strong> ${esc(c.clause || "")}
            ${c.note ? `<div style="color:var(--muted);margin-top:2px">${esc(c.note)}</div>` : ""}</li>`
        )
        .join("");
      openDrawer(`
        <button class="btn ghost" id="closeDrawerBtn">Close</button>
        <h2 style="margin-top:12px">${esc(a.resource_id)} → ${esc(a.standard_code)}</h2>
        <p style="color:var(--muted);margin:4px 0 12px">${esc(a.lesson_title)}</p>
        <div class="meta-grid">
          <div class="cell"><div class="k">Alignment</div><div class="v">${badge(a.matched_status)}</div></div>
          <div class="cell"><div class="k">Confidence</div><div class="v">${esc(a.confidence || "—")}</div></div>
          <div class="cell"><div class="k">Grounded</div><div class="v">${a.grounded ? "Yes" : "No"}</div></div>
          <div class="cell"><div class="k">Review</div><div class="v">${a.needs_review ? "Required" : "No"}</div></div>
        </div>
        <h3 style="font-size:13px;margin:16px 0 6px">Standard</h3>
        <p style="margin:0;font-size:13px;line-height:1.5">${esc(a.standard_text || "—")}</p>
        <h3 style="font-size:13px;margin:16px 0 6px">Evidence</h3>
        ${
          a.evidence
            ? `<div class="evidence-quote">${esc(a.evidence)}
               <div style="margin-top:8px;font-size:12px;color:var(--muted)">Curriculum · p. ${esc(
                 a.evidence_page ?? "—"
               )}</div></div>`
            : `<p style="color:var(--muted)">No evidence quote.</p>`
        }
        <h3 style="font-size:13px;margin:16px 0 6px">Alignment reasoning</h3>
        <p style="margin:0;font-size:13px;color:#374151">${esc(a.rationale || "—")}</p>
        ${
          clauses
            ? `<h3 style="font-size:13px;margin:16px 0 6px">Clauses</h3><ul style="margin:0;padding-left:18px;font-size:13px">${clauses}</ul>`
            : ""
        }
        ${
          a.review_reason
            ? `<h3 style="font-size:13px;margin:16px 0 6px">Review reason</h3><p style="margin:0;font-size:13px">${esc(
                a.review_reason
              )}</p>`
            : ""
        }
        <p style="margin-top:16px;font-size:12px;color:var(--muted)">Model: ${esc(
          a.judge_model || "—"
        )} · ${esc(a.prompt_version || "")}${a.escalated ? " · Escalated" : ""}</p>
      `);
      $("#closeDrawerBtn")?.addEventListener("click", closeDrawer);
    } catch (e) {
      openDrawer(`<button class="btn ghost" id="closeDrawerBtn">Close</button>${errorBox(e)}`);
      $("#closeDrawerBtn")?.addEventListener("click", closeDrawer);
    }
  }

  // —— Pages —— //

  async function renderOverview() {
    setActiveNav("overview");
    setCrumbs(["Overview"]);
    const [ov, cov, pipe] = await Promise.all([
      api("/api/overview"),
      api("/api/lessons/coverage"),
      api("/api/pipeline"),
    ]);
    state.overview = ov;
    const total = ov.alignments || 1;
    const f = ov.by_status.full || 0;
    const p = ov.by_status.partial || 0;
    const n = ov.by_status.none || 0;
    const r = ov.review_required || 0;
    const p1 = (f / total) * 100;
    const p2 = p1 + (p / total) * 100;
    const p3 = p2 + (r / total) * 100;
    const fullPct = Math.round((100 * f) / total);

    function lessonMeta(rid) {
      const m = String(rid || "").match(/U(\d+)L(\d+)/i);
      if (!m) return { unit: 0, lesson: 0, short: String(rid || "").replace(/^G1M2/i, "") || "—" };
      return { unit: Number(m[1]), lesson: Number(m[2]), short: `U${m[1]}L${m[2]}` };
    }

    const lessonRows = [...cov.rows]
      .map((row) => ({ ...row, meta: lessonMeta(row.resource_id) }))
      .sort((a, b) => a.meta.unit - b.meta.unit || a.meta.lesson - b.meta.lesson);
    const units = [...new Set(lessonRows.map((x) => x.meta.unit).filter(Boolean))];
    const maxAligned = Math.max(1, ...lessonRows.map((x) => x.aligned || 0));

    const unitStats = units.map((u) => {
      const rows = lessonRows.filter((x) => x.meta.unit === u);
      const aligned = rows.reduce((s, x) => s + (x.aligned || 0), 0);
      const avg = Math.round(aligned / Math.max(1, rows.length));
      return { unit: u, rows, aligned, avg, count: rows.length };
    });
    const maxUnitAvg = Math.max(1, ...unitStats.map((x) => x.avg));

    const pq = ov.pdf_quality;
    const qualityStrip =
      pq && pq.available
        ? `<div class="metric-strip">
            <div class="metric-pill"><span>Accuracy</span><strong>${fmtPct(pq.judge_accuracy)}</strong></div>
            <div class="metric-pill"><span>Precision</span><strong>${fmtPct(pq.binary_precision)}</strong></div>
            <div class="metric-pill"><span>Recall</span><strong>${fmtPct(pq.binary_recall)}</strong></div>
            <div class="metric-pill"><span>Recall@25</span><strong>${fmtPct(pq.retrieve_recall_at_25)}</strong></div>
          </div>`
        : "";

    page.innerHTML = `
      <div class="analytics">
        <div class="kpi-grid kpi-4">
          <div class="kpi"><div class="label">Alignments</div><div class="value">${ov.alignments.toLocaleString()}</div></div>
          <div class="kpi"><div class="label">Coverage</div><div class="value">${ov.alignment_coverage_pct}%</div></div>
          <div class="kpi"><div class="label">Review</div><div class="value">${ov.review_required}</div></div>
          <div class="kpi"><div class="label">Lessons</div><div class="value">${ov.lessons}</div></div>
        </div>

        ${qualityStrip}

        <div class="grid-2">
          <section class="card">
            <div class="card-h"><h2>Alignment mix</h2></div>
            <div class="card-b">
              <div class="donut-wrap compact">
                <div class="donut-center">
                  <div class="donut" style="--p1:${p1}%;--p2:${p2}%;--p3:${p3}%"></div>
                  <div class="donut-label"><strong>${fullPct}%</strong><span>Full</span></div>
                </div>
                <div class="legend tight">
                  <div class="legend-row"><span><span class="swatch" style="background:var(--ok)"></span>Full</span><strong>${f}</strong></div>
                  <div class="legend-row"><span><span class="swatch" style="background:var(--warn)"></span>Partial</span><strong>${p}</strong></div>
                  <div class="legend-row"><span><span class="swatch" style="background:var(--blue)"></span>Review</span><strong>${r}</strong></div>
                  <div class="legend-row"><span><span class="swatch" style="background:var(--bad)"></span>None</span><strong>${n}</strong></div>
                </div>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="card-h"><h2>Coverage by unit</h2></div>
            <div class="card-b">
              <div class="unit-chart">
                ${unitStats
                  .map((u) => {
                    const w = Math.round((100 * u.avg) / maxUnitAvg);
                    return `<div class="unit-bar-row">
                      <span class="unit-lab">Unit ${u.unit}</span>
                      <div class="unit-track"><div class="unit-fill" style="width:${w}%"></div></div>
                      <span class="unit-val">${u.avg}<small> avg</small></span>
                    </div>`;
                  })
                  .join("")}
              </div>
            </div>
          </section>
        </div>

        <section class="card">
          <div class="card-h"><h2>Pipeline flow</h2><span class="badge info">${esc(ov.pipeline_health)}</span></div>
          <div class="card-b">
            <div class="flow-diagram">
              ${pipe.stages
                .map(
                  (s, i) => `${i ? `<div class="flow-join" aria-hidden="true"></div>` : ""}
                  <div class="flow-node ${esc(s.status)}" title="${esc(s.detail)}">
                    <div class="flow-name">${esc(s.name)}</div>
                    <div class="flow-meta">${esc(s.count)}</div>
                  </div>`
                )
                .join("")}
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-h">
            <h2>Lesson coverage map</h2>
            <div class="heat-scale"><span>Low</span><div class="heat-grad"></div><span>High</span></div>
          </div>
          <div class="card-b">
            <div class="heat-board" id="lessonBars">
              ${unitStats
                .map(
                  (u) => `<div class="heat-unit">
                    <div class="heat-unit-lab">U${u.unit}</div>
                    <div class="heat-grid">
                      ${u.rows
                        .map((row) => {
                          const intensity = (row.aligned || 0) / maxAligned;
                          return `<button type="button" class="heat-cell" style="background:rgba(31,111,91,${(0.12 + intensity * 0.68).toFixed(3)})"
                            data-lesson="${esc(row.resource_id)}"
                            title="${esc(row.meta.short)} · ${row.aligned} aligned · F${row.full}/P${row.partial}/N${row.none}">
                            ${esc(row.meta.short.replace(/^U\d+L/i, "L"))}
                          </button>`;
                        })
                        .join("")}
                    </div>
                  </div>`
                )
                .join("")}
            </div>
          </div>
        </section>
      </div>
    `;

    $("#lessonBars")?.addEventListener("click", (e) => {
      const cell = e.target.closest("[data-lesson]");
      if (cell) location.hash = `#/lessons/${cell.dataset.lesson}`;
    });
  }

  async function renderAlignments() {
    setActiveNav("alignments");
    setCrumbs(["Projects", state.project?.name || "…", "Alignments"]);
    const ov = state.overview || (await api("/api/overview").catch(() => null));
    if (ov) state.overview = ov;
    const by = (ov && ov.by_status) || {};
    page.innerHTML = `
      ${pageHeader("Alignment List", "Browse lesson–standard evaluations — filter, open evidence, and review flags.")}
      <div class="filter-tabs" id="alignTabs">
        <button type="button" class="filter-tab active" data-status="" data-tone="all">All <span class="count">${ov ? ov.alignments : "—"}</span></button>
        <button type="button" class="filter-tab" data-status="full" data-tone="full">Full <span class="count">${by.full || 0}</span></button>
        <button type="button" class="filter-tab" data-status="partial" data-tone="partial">Partial <span class="count">${by.partial || 0}</span></button>
        <button type="button" class="filter-tab" data-status="none" data-tone="none">None <span class="count">${by.none || 0}</span></button>
        <button type="button" class="filter-tab" data-status="__review__" data-tone="review">Review <span class="count">${ov ? ov.review_required : 0}</span></button>
      </div>
      <div class="filters">
        <input id="fQ" placeholder="Search lessons, standards, evidence…" />
        <button class="btn" id="fApply">Search</button>
      </div>
      <div id="alignTable">${empty("Loading", "Fetching alignments…")}</div>`;

    let activeStatus = "";
    async function load() {
      const q = ($("#fQ") && $("#fQ").value.trim()) || "";
      const params = new URLSearchParams({ limit: "60" });
      if (q) params.set("q", q);
      if (activeStatus === "__review__") params.set("needs_review", "true");
      else if (activeStatus) params.set("status", activeStatus);
      const data = await api(`/api/alignments?${params}`);
      if (!data.rows.length) {
        $("#alignTable").innerHTML = empty("No alignments match", "Try another filter or clear search.");
        return;
      }
      $("#alignTable").innerHTML = `<div class="tile-grid">
        ${data.rows
          .map((a) => {
            const action =
              a.needs_review
                ? "Open review"
                : a.matched_status === "full"
                  ? "View evidence"
                  : a.matched_status === "partial"
                    ? "Inspect partial"
                    : "View details";
            return `<article class="tile clickable" data-id="${esc(a.id)}">
              <div class="tile-top">
                <div class="tile-id">${esc(a.resource_id)}</div>
                ${badge(a.matched_status)}
              </div>
              <div class="tile-meta">
                <div class="row">📘 ${esc(a.lesson_title || "Lesson")}</div>
                <div class="row">🎯 ${esc(a.standard_code)}</div>
                <div class="row">★ Confidence: ${esc(a.confidence || "—")}${a.needs_review ? " · Needs review" : ""}</div>
              </div>
              <div class="tile-foot">
                <div class="tile-price">${a.evidence_page != null ? `p. ${esc(a.evidence_page)}` : "—"}</div>
                <button type="button" class="btn ${a.matched_status === "full" ? "primary" : "outline-green"}">${esc(action)}</button>
              </div>
            </article>`;
          })
          .join("")}
      </div>
      <p style="margin:12px 0 0;color:var(--muted);font-size:12px">Showing ${data.rows.length} of ${data.total}</p>`;
      $$("#alignTable .tile.clickable").forEach((tile) => {
        tile.addEventListener("click", () => showAlignmentDrawer(tile.dataset.id));
      });
    }

    $$("#alignTabs .filter-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$("#alignTabs .filter-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        activeStatus = tab.dataset.status || "";
        load().catch((e) => ($("#alignTable").innerHTML = errorBox(e)));
      });
    });
    $("#fApply").addEventListener("click", () => load().catch((e) => ($("#alignTable").innerHTML = errorBox(e))));
    await load();
  }

  async function renderEvidence() {
    setActiveNav("evidence");
    setCrumbs(["Projects", state.project?.name || "…", "Evidence"]);
    const data = await api("/api/evidence?limit=60");
    page.innerHTML = `
      ${pageHeader("Evidence", "Browse supporting curriculum evidence across alignments.")}
      ${
        data.rows.length
          ? `<div class="tile-grid">
              ${data.rows
                .map(
                  (e) => `<article class="tile">
                  <div class="tile-top">
                    <div class="tile-id">${esc(e.resource_id)}</div>
                    ${badge(e.matched_status)}
                  </div>
                  <div class="tile-meta">
                    <div class="row">📘 ${esc(e.lesson_title)}</div>
                    <div class="row">🎯 ${esc(e.standard_code)}</div>
                    <div class="row">📄 Page ${esc(e.evidence_page ?? "—")}</div>
                  </div>
                  <div class="evidence-quote" style="margin:0">${esc((e.evidence || "").slice(0, 160))}${
                    (e.evidence || "").length > 160 ? "…" : ""
                  }</div>
                  <div class="tile-foot">
                    <span class="tile-price">Evidence</span>
                    <button type="button" class="btn primary" data-open="${esc(e.id)}">View alignment</button>
                  </div>
                </article>`
                )
                .join("")}
            </div>`
          : empty("No evidence yet", "Evidence appears when alignments include grounded quotes.")
      }`;
    $$("[data-open]").forEach((b) => b.addEventListener("click", () => showAlignmentDrawer(b.dataset.open)));
  }

  async function renderReview() {
    setActiveNav("review");
    setCrumbs(["Projects", state.project?.name || "…", "QA / Review"]);
    const data = await api("/api/review");
    page.innerHTML = `
      ${pageHeader("Review Queue", "Results flagged for human verification.")}
      ${
        data.rows.length
          ? `<div class="tile-grid">
              ${data.rows
                .map(
                  (r) => `<article class="tile">
                  <div class="tile-top">
                    <div class="tile-id">${esc(r.resource_id)}</div>
                    ${badge(r.matched_status)}
                  </div>
                  <div class="tile-meta">
                    <div class="row">🎯 ${esc(r.standard_code)}</div>
                    <div class="row">★ Confidence: ${esc(r.confidence || "—")}</div>
                    <div class="row">⚠ ${esc((r.review_reason || "Needs review").slice(0, 90))}${
                      (r.review_reason || "").length > 90 ? "…" : ""
                    }</div>
                  </div>
                  <div class="tile-foot">
                    <span class="tile-price">Review</span>
                    <button type="button" class="btn primary" data-open="${esc(r.id)}">Open review</button>
                  </div>
                  <p style="margin:8px 0 0;font-size:11px;color:var(--muted)">Approve / change / note are display-ready; write-back is disabled to protect production data.</p>
                </article>`
                )
                .join("")}
            </div>`
          : empty("You're all caught up", "No items currently flagged for review.")
      }`;
    $$("[data-open]").forEach((b) => b.addEventListener("click", () => showAlignmentDrawer(b.dataset.open)));
  }

  async function renderStandards() {
    setActiveNav("standards");
    setCrumbs(["Projects", state.project?.name || "…", "Standards"]);
    const [cov, tree] = await Promise.all([api("/api/standards/coverage"), api("/api/standards/tree")]);
    const counts = { covered: 0, partial: 0, not_found: 0, review: 0 };
    cov.rows.forEach((r) => {
      counts[r.status] = (counts[r.status] || 0) + 1;
    });
    function renderNode(n) {
      const kids = (n.children || []).map(renderNode).join("");
      return `<details open="${n.level === "domain" ? "open" : null}"><summary>${esc(n.code)} ${
        n.label ? `— ${esc(n.label)}` : ""
      }</summary>
        <div class="node-text">${esc((n.text || "").slice(0, 180))}</div>${kids}</details>`;
    }
    let filterStatus = "";
    page.innerHTML = `
      ${pageHeader("Standards", `${state.project?.framework || "Standards"} hierarchy and coverage.`)}
      <div class="filter-tabs" id="stdTabs">
        <button type="button" class="filter-tab active" data-status="" data-tone="all">All <span class="count">${cov.rows.length}</span></button>
        <button type="button" class="filter-tab" data-status="covered" data-tone="full">Covered <span class="count">${counts.covered || 0}</span></button>
        <button type="button" class="filter-tab" data-status="partial" data-tone="partial">Partial <span class="count">${counts.partial || 0}</span></button>
        <button type="button" class="filter-tab" data-status="not_found" data-tone="none">Not found <span class="count">${counts.not_found || 0}</span></button>
      </div>
      <div id="stdTiles"></div>
      <section class="card" style="margin-top:18px"><div class="card-h"><h2>Hierarchy</h2></div>
        <div class="card-b tree" style="max-height:420px;overflow:auto">
          ${(tree.roots || []).map(renderNode).join("") || empty("No standards", "Import a standards workbook.")}
        </div>
      </section>`;

    function paint() {
      const rows = filterStatus ? cov.rows.filter((r) => r.status === filterStatus) : cov.rows;
      const slice = rows.slice(0, 90);
      $("#stdTiles").innerHTML = slice.length
        ? `<div class="tile-grid">${slice
            .map(
              (r) => `<article class="tile">
              <div class="tile-top">
                <div class="tile-id">${esc(r.code)}</div>
                ${badge(r.status)}
              </div>
              <div class="tile-meta">
                <div class="row">📘 ${esc((r.text || r.label || "—").slice(0, 100))}</div>
                <div class="row">▤ ${r.lessons.length} lesson(s)</div>
              </div>
              <div class="tile-foot">
                <span class="tile-price">${esc(r.status)}</span>
                <a class="btn outline-green" href="#/alignments">See alignments</a>
              </div>
            </article>`
            )
            .join("")}</div>
          <p style="margin:12px 0 0;color:var(--muted);font-size:12px">Showing ${slice.length} of ${rows.length}</p>`
        : empty("No standards in this filter", "Try another coverage status.");
    }
    $$("#stdTabs .filter-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$("#stdTabs .filter-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        filterStatus = tab.dataset.status || "";
        paint();
      });
    });
    paint();
  }

  async function renderCurriculum() {
    setActiveNav("curriculum");
    setCrumbs(["Projects", state.project?.name || "…", "Curriculum"]);
    const cov = await api("/api/lessons/coverage");
    const p = state.project;
    page.innerHTML = `
      ${pageHeader("Curriculum", "Curriculum packages and lessons in this workspace.")}
      <section class="card"><div class="card-b">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap">
          <div>
            <h2 style="margin:0 0 4px;font-size:16px">${esc(p?.name || "—")}</h2>
            <p style="margin:0;color:var(--muted)">${esc(p?.publisher)} · Grade ${esc(
      p?.grade
    )} · ${esc(p?.subject)} · ${esc(p?.module)}</p>
          </div>
          <div>${badge(p?.status || "—")} · ${p?.lessons || 0} lessons</div>
        </div>
      </div></section>
      <div class="tile-grid">
        ${cov.rows
          .map((r) => {
            const status =
              r.review > 0 ? "review" : r.full > 0 ? "full" : r.partial > 0 ? "partial" : "none";
            return `<article class="tile clickable" data-href="#/lessons/${esc(r.resource_id)}">
              <div class="tile-top">
                <div class="tile-id">${esc(r.resource_id)}</div>
                ${badge(status)}
              </div>
              <div class="tile-meta">
                <div class="row">📘 ${esc(r.title)}</div>
                <div class="row">✓ Full ${r.full} · ◐ Partial ${r.partial}</div>
                <div class="row">○ None ${r.none}${r.review ? ` · Review ${r.review}` : ""}</div>
              </div>
              <div class="tile-foot">
                <div class="tile-price">${r.aligned} aligned</div>
                <a class="btn primary" href="#/lessons/${esc(r.resource_id)}">Open lesson</a>
              </div>
            </article>`;
          })
          .join("")}
      </div>`;
    $$(".tile.clickable[data-href]").forEach((tile) => {
      tile.addEventListener("click", (e) => {
        if (e.target.closest("a,button")) return;
        location.hash = tile.dataset.href;
      });
    });
  }

  async function renderLesson(code) {
    setActiveNav("curriculum");
    setCrumbs(["Projects", state.project?.name || "…", "Curriculum", code]);
    const d = await api(`/api/lessons/${encodeURIComponent(code)}`);
    const blocks = (d.instructional_blocks || [])
      .map(
        (b) => `<div style="padding:10px 0;border-bottom:1px solid var(--line)">
        <strong>${esc(b.section || "")} ${esc(b.letter || "")}</strong> — ${esc(b.title || "")}
        <div style="color:var(--muted);font-size:12px">p. ${esc(b.page ?? "—")} · ${
          Array.isArray(b.steps) ? b.steps.length : 0
        } steps</div>
      </div>`
      )
      .join("");
    page.innerHTML = `
      ${pageHeader(d.title || code, `Pages ${d.page_start ?? "—"}–${d.page_end ?? "—"} · Unit ${d.unit ?? "—"}`)}
      <div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)">
        <div class="kpi"><div class="label">Full</div><div class="value">${d.alignments_summary.full || 0}</div></div>
        <div class="kpi"><div class="label">Partial</div><div class="value">${d.alignments_summary.partial || 0}</div></div>
        <div class="kpi"><div class="label">None</div><div class="value">${d.alignments_summary.none || 0}</div></div>
        <div class="kpi"><div class="label">Review</div><div class="value">${d.alignments_summary.review || 0}</div></div>
      </div>
      <div class="grid-2">
        <section class="card"><div class="card-h"><h2>Instructional structure</h2></div><div class="card-b">${
          blocks || empty("No blocks", "Stage-1 lesson has no instructional blocks.")
        }</div></section>
        <section class="card"><div class="card-h"><h2>Materials & vocabulary</h2></div>
          <div class="card-b">
            <h3 style="font-size:12px;color:var(--muted);margin:0 0 6px">MATERIALS</h3>
            <ul>${(d.materials || [])
              .slice(0, 12)
              .map((m) => `<li>${esc(typeof m === "string" ? m : m.text || JSON.stringify(m))}</li>`)
              .join("")}</ul>
            <h3 style="font-size:12px;color:var(--muted);margin:16px 0 6px">VOCABULARY</h3>
            <ul>${(d.vocabulary || [])
              .slice(0, 12)
              .map((m) => `<li>${esc(typeof m === "string" ? m : m.term || m.text || JSON.stringify(m))}</li>`)
              .join("")}</ul>
            <p style="margin-top:12px"><a href="#/alignments">View alignments for this lesson</a> (filter manually) ·
            <a href="#/evidence">Evidence</a></p>
          </div>
        </section>
      </div>`;
  }

  async function renderIngestion() {
    setActiveNav("ingestion");
    setCrumbs(["Operations", "Ingestion"]);
    let status = { batches: [], note: "" };
    try {
      status = await api("/api/ingest");
    } catch {
      /* optional */
    }
    const batches = status.batches || [];
    page.innerHTML = `
      <div class="analytics">
        <div class="kpi-grid kpi-4">
          <div class="kpi"><div class="label">Upload batches</div><div class="value">${batches.length}</div></div>
          <div class="kpi"><div class="label">Storage</div><div class="value" style="font-size:18px">Local</div></div>
          <div class="kpi"><div class="label">Writes to output/</div><div class="value" style="font-size:18px">Never</div></div>
          <div class="kpi"><div class="label">Next step</div><div class="value" style="font-size:18px">CLI run</div></div>
        </div>

        <div class="grid-2">
          <section class="card">
            <div class="card-h"><h2>New inputs</h2></div>
            <div class="card-b">
              <form id="ingestForm" class="ingest-form">
                <label>Program name
                  <input name="program_name" value="EL Education Curriculum" required />
                </label>
                <div class="ingest-row">
                  <label>Guide label
                    <input name="guide_label" value="Module 2" required />
                  </label>
                  <label>Grade label
                    <input name="grade_label" value="Grade 1" required />
                  </label>
                </div>
                <label>Curriculum PDF
                  <input type="file" name="guide_pdf" accept=".pdf,application/pdf" />
                </label>
                <label>Standards XLSX
                  <input type="file" name="standards_xlsx" accept=".xlsx,.xlsm" />
                </label>
                <div class="ingest-actions">
                  <button type="submit" class="btn primary" id="ingestSubmit">Save inputs</button>
                  <span id="ingestMsg" class="ingest-msg"></span>
                </div>
              </form>
            </div>
          </section>

          <section class="card">
            <div class="card-h"><h2>How uploads work</h2></div>
            <div class="card-b">
              <div class="flow-diagram vertical">
                <div class="flow-node complete"><div class="flow-name">1. Upload</div><div class="flow-meta">PDF + XLSX</div></div>
                <div class="flow-join vert" aria-hidden="true"></div>
                <div class="flow-node complete"><div class="flow-name">2. Store</div><div class="flow-meta">dashboard/uploads</div></div>
                <div class="flow-join vert" aria-hidden="true"></div>
                <div class="flow-node warn"><div class="flow-name">3. Process</div><div class="flow-meta">CLI pipeline</div></div>
                <div class="flow-join vert" aria-hidden="true"></div>
                <div class="flow-node"><div class="flow-name">4. Analytics</div><div class="flow-meta">Locked Batch-1 output</div></div>
              </div>
              <p class="pipe-note">Uploads never overwrite locked <code>veramynd_parser/output/</code>. Dashboard analytics keep reading the Batch-1 artifacts until you run a new pipeline.</p>
            </div>
          </section>
        </div>

        <section class="card">
          <div class="card-h"><h2>Recent uploads</h2><span class="badge info">${batches.length}</span></div>
          <div class="card-b">
            ${
              batches.length
                ? `<div class="batch-grid">
                    ${batches
                      .map(
                        (b) => `<article class="batch-card">
                          <div class="batch-id">${esc(b.id)}</div>
                          <div class="batch-files">${esc((b.files || []).join(" · ") || "—")}</div>
                        </article>`
                      )
                      .join("")}
                  </div>`
                : empty("No uploads yet", "Add a PDF and/or standards workbook with the form.")
            }
          </div>
        </section>
      </div>`;

    $("#ingestForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = $("#ingestMsg");
      const btn = $("#ingestSubmit");
      const fd = new FormData(e.target);
      const hasFile =
        (fd.get("guide_pdf") && fd.get("guide_pdf").size > 0) ||
        (fd.get("standards_xlsx") && fd.get("standards_xlsx").size > 0);
      if (!hasFile) {
        msg.textContent = "Choose a PDF and/or standards XLSX first.";
        msg.style.color = "var(--bad)";
        return;
      }
      btn.disabled = true;
      msg.textContent = "Saving…";
      msg.style.color = "var(--muted)";
      try {
        const res = await fetch("/api/ingest", { method: "POST", body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          let detail = data.detail || data.message || `HTTP ${res.status}`;
          if (Array.isArray(detail)) detail = detail.map((d) => d.msg || d).join("; ");
          throw new Error(detail);
        }
        msg.textContent = `Saved batch ${data.batch_id}`;
        msg.style.color = "var(--ok)";
        setTimeout(() => renderIngestion().catch(() => {}), 400);
      } catch (err) {
        msg.textContent = String(err.message || err);
        msg.style.color = "var(--bad)";
        btn.disabled = false;
      }
    });
  }

  async function renderPipeline() {
    setActiveNav("pipeline");
    setCrumbs(["Operations", "Pipeline"]);
    const [pipe, ov] = await Promise.all([api("/api/pipeline"), api("/api/overview").catch(() => null)]);
    const stages = pipe.stages || [];
    const done = stages.filter((s) => /complete|ok|healthy/i.test(s.status || "")).length;
    const warn = stages.filter((s) => /warn/i.test(s.status || "")).length;
    const pending = stages.length - done - warn;
    const pct = stages.length ? Math.round((100 * done) / stages.length) : 0;

    page.innerHTML = `
      <div class="analytics">
        <div class="kpi-grid kpi-4">
          <div class="kpi"><div class="label">Stages complete</div><div class="value">${done}<span class="kpi-of">/${stages.length}</span></div></div>
          <div class="kpi"><div class="label">Warnings</div><div class="value">${warn}</div></div>
          <div class="kpi"><div class="label">Pending</div><div class="value">${pending}</div></div>
          <div class="kpi"><div class="label">Health</div><div class="value" style="font-size:18px">${esc(
            (ov && ov.pipeline_health) || "—"
          )}</div></div>
        </div>

        <section class="card">
          <div class="card-h">
            <h2>End-to-end flow</h2>
            <span class="badge info">${pct}% complete</span>
          </div>
          <div class="card-b">
            <div class="pipe-progress"><div class="pipe-progress-fill" style="width:${pct}%"></div></div>
            <div class="flow-diagram">
              ${stages
                .map(
                  (s, i) => `${i ? `<div class="flow-join" aria-hidden="true"></div>` : ""}
                  <div class="flow-node ${esc(s.status)}">
                    <div class="flow-step">${i + 1}</div>
                    <div class="flow-name">${esc(s.name)}</div>
                    <div class="flow-meta">${esc(s.count)}</div>
                  </div>`
                )
                .join("")}
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-h"><h2>Stage detail</h2></div>
          <div class="card-b pipe-rail">
            ${stages
              .map(
                (s, i) => `<div class="pipe-rail-row">
                  <div class="pipe-rail-axis">
                    <span class="pipe-rail-dot ${esc(s.status)}"></span>
                    ${i < stages.length - 1 ? `<span class="pipe-rail-line"></span>` : ""}
                  </div>
                  <div class="pipe-rail-body">
                    <div class="pipe-rail-top">
                      <strong>${esc(s.name)}</strong>
                      ${badge(s.status)}
                    </div>
                    <div class="pipe-rail-detail">${esc(s.detail)}</div>
                    <div class="pipe-rail-count">${esc(s.count)}</div>
                  </div>
                </div>`
              )
              .join("")}
          </div>
        </section>
      </div>`;
  }

  async function renderRetrieval() {
    setActiveNav("retrieval");
    setCrumbs(["Pipeline", "Retrieval"]);
    const [qa, pq] = await Promise.all([api("/api/qa"), api("/api/quality")]);
    const r = qa.retrieval || {};
    page.innerHTML = `
      ${pageHeader("Retrieval analytics", "Protected retrieve quality for this curriculum PDF.")}
      ${qualityCard(pq)}
      <div class="kpi-grid" style="grid-template-columns:repeat(2,1fr);max-width:480px">
        <div class="kpi"><div class="label">Recall@25</div><div class="value">${fmtPct(r.recall_at_25)}</div><div class="hint">${
          r.recall_at_25_hits != null ? `${r.recall_at_25_hits}/${r.recall_at_25_n}` : "Protected QA bar"
        }</div></div>
        <div class="kpi"><div class="label">Gold positives</div><div class="value">${esc(r.n_positives ?? "—")}</div><div class="hint">Eval set size</div></div>
      </div>
      <section class="card"><div class="card-h"><h2>Retrieval funnel</h2></div>
        <div class="card-b">
          <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px;font-weight:500">
            ${["Query", "Dense", "BM25", "RRF", "Merge", "Cross-encoder", "Final candidates"]
              .map((x) => `<span class="badge info">${x}</span>`)
              .join('<span style="color:var(--muted)">→</span>')}
          </div>
          <p style="margin:12px 0 0;color:var(--muted);font-size:13px">Source: ${esc(r.source || "—")}</p>
          ${(qa.notes || []).map((n) => `<p style="margin:6px 0 0;font-size:12px;color:var(--muted)">• ${esc(n)}</p>`).join("")}
        </div>
      </section>`;
  }

  function fmtPct(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return "—";
    const pct = n <= 1 ? n * 100 : n;
    return `${Math.round(pct)}%`;
  }

  function qualityCard(pq) {
    if (!pq || !pq.available) {
      return `<section class="card"><div class="card-h"><h2>Accuracy &amp; recall (this PDF)</h2></div>
        <div class="card-b">${empty("Quality metrics unavailable", "Corrected master or retrieve metrics are missing for this curriculum.")}</div></section>`;
    }
    const acc = fmtPct(pq.judge_accuracy);
    const prec = fmtPct(pq.binary_precision);
    const brec = fmtPct(pq.binary_recall);
    const r25 = fmtPct(pq.retrieve_recall_at_25);
    const exact =
      pq.judge_exact != null && pq.judge_judged != null
        ? `${pq.judge_exact}/${pq.judge_judged}`
        : "—";
    const r25detail =
      pq.retrieve_recall_at_25_hits != null && pq.retrieve_recall_at_25_n != null
        ? `${pq.retrieve_recall_at_25_hits}/${pq.retrieve_recall_at_25_n}`
        : "";
    return `
      <section class="card">
        <div class="card-h">
          <h2>Accuracy &amp; recall — overall (this PDF)</h2>
          <span class="badge info">${esc(pq.lessons_in_scope || 40)} lessons</span>
        </div>
        <div class="card-b">
          <p style="margin:0 0 12px;color:var(--muted);font-size:13px">
            ${esc(pq.curriculum_pdf)} · ${esc(pq.standards_set)} · vs corrected master (all lessons)
          </p>
          <div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)">
            <div class="kpi"><div class="label">Judge accuracy</div><div class="value">${acc}</div><div class="hint">3-class exact ${esc(exact)}</div></div>
            <div class="kpi"><div class="label">Binary precision</div><div class="value">${prec}</div><div class="hint">pos = full | partial</div></div>
            <div class="kpi"><div class="label">Binary recall</div><div class="value">${brec}</div><div class="hint">pos = full | partial</div></div>
            <div class="kpi"><div class="label">Recall@25</div><div class="value">${r25}</div><div class="hint">Retrieve ${esc(r25detail)}</div></div>
          </div>
          <p style="margin:12px 0 0;font-size:12px;color:var(--muted)">
            Overall design for this curriculum PDF — not gold-4-only.
            Reference: ${esc((pq.sources && pq.sources.reference) || "corrected master")} · live judge.
            ${pq.pairs_missing_in_judge ? ` · ${pq.pairs_missing_in_judge} master pair(s) missing in judge` : ""}
          </p>
        </div>
      </section>`;
  }

  async function renderJudge() {
    setActiveNav("judge");
    setCrumbs(["Pipeline", "Judge"]);
    const qa = await api("/api/qa");
    const a = qa.alignment || {};
    const h = qa.human_qa || {};
    page.innerHTML = `
      ${pageHeader("Judge performance", "Evaluation outcomes from assembled judge artifacts.")}
      <div class="kpi-grid">
        <div class="kpi"><div class="label">Evaluations</div><div class="value">${a.total_evaluations ?? "—"}</div></div>
        <div class="kpi"><div class="label">Full</div><div class="value">${a.full ?? "—"}</div></div>
        <div class="kpi"><div class="label">Partial</div><div class="value">${a.partial ?? "—"}</div></div>
        <div class="kpi"><div class="label">None</div><div class="value">${a.none ?? "—"}</div></div>
        <div class="kpi"><div class="label">Escalated</div><div class="value">${a.escalated ?? "—"}</div><div class="hint">${h.escalation_rate ?? 0}% rate</div></div>
        <div class="kpi"><div class="label">Review required</div><div class="value">${h.review_required ?? "—"}</div><div class="hint">${h.review_rate ?? 0}% rate</div></div>
      </div>
      <section class="card"><div class="card-b">
        <p style="margin:0;color:var(--muted);font-size:13px">Batch judge vs escalate model are recorded per verdict (<code>escalated</code> flag). Prompts and API keys are not exposed.</p>
      </div></section>`;
  }

  async function renderQa() {
    setActiveNav("qa");
    setCrumbs(["Pipeline", "QA metrics"]);
    const [qa, pq] = await Promise.all([api("/api/qa"), api("/api/quality")]);
    page.innerHTML = `
      ${pageHeader("QA metrics", "Accuracy and recall for this curriculum PDF, plus review indicators.")}
      ${qualityCard(pq)}
      <div class="grid-3">
        <section class="card"><div class="card-h"><h2>Retrieval</h2></div><div class="card-b">
          <div>Recall@25: <strong>${fmtPct(qa.retrieval.recall_at_25)}</strong></div>
          <div>Gold positives: <strong>${esc(qa.retrieval.n_positives ?? "—")}</strong></div>
        </div></section>
        <section class="card"><div class="card-h"><h2>Final alignment</h2></div><div class="card-b">
          <div>Full / Partial / None: <strong>${qa.alignment.full} / ${qa.alignment.partial} / ${qa.alignment.none}</strong></div>
          <div>Grounded: <strong>${qa.alignment.grounded}</strong></div>
          <div>Coverage: <strong>${qa.alignment.coverage_pct}%</strong></div>
        </div></section>
        <section class="card"><div class="card-h"><h2>Human QA</h2></div><div class="card-b">
          <div>Review required: <strong>${qa.human_qa.review_required}</strong></div>
          <div>Review rate: <strong>${qa.human_qa.review_rate}%</strong></div>
          <div>Escalation rate: <strong>${qa.human_qa.escalation_rate}%</strong></div>
        </div></section>
      </div>
      <section class="card"><div class="card-b">${(qa.notes || [])
        .map((n) => `<p style="margin:0 0 6px;color:var(--muted);font-size:13px">• ${esc(n)}</p>`)
        .join("")}</div></section>`;
  }

  async function renderRuns() {
    setActiveNav("runs");
    setCrumbs(["Pipeline", "Runs"]);
    const runs = await api("/api/runs");
    page.innerHTML = `
      ${pageHeader("Runs", "Processing runs derived from available output artifacts.")}
      <div class="tile-grid">
        ${runs.rows
          .map(
            (r) => `<article class="tile">
            <div class="tile-top">
              <div class="tile-id">${esc(r.id)}</div>
              ${badge(r.status)}
            </div>
            <div class="tile-meta">
              <div class="row">📘 ${esc(r.curriculum)}</div>
              <div class="row">🎯 ${esc(r.standards_set)}</div>
              <div class="row">▤ ${r.lessons} lessons · ${r.alignments} alignments</div>
              <div class="row">📁 ${esc(r.source)}</div>
            </div>
            <div class="tile-foot">
              <a class="btn outline-green" href="#/exports">Export</a>
              <a class="btn primary" href="#/alignments">View results</a>
            </div>
          </article>`
          )
          .join("")}
      </div>`;
  }

  async function renderExports() {
    setActiveNav("exports");
    setCrumbs(["Administration", "Exports"]);
    const data = await api("/api/exports");
    page.innerHTML = `
      ${pageHeader("Exports", "Download client packages and evaluation artifacts.")}
      <div class="tile-grid">
        ${data.rows
          .map(
            (e) => `<article class="tile">
            <div class="tile-top">
              <div class="tile-id">${esc(e.name)}</div>
              ${e.available ? badge("ok") : badge("none")}
            </div>
            <div class="tile-meta">
              <div class="row">📄 Type: ${esc(e.type)}</div>
              ${e.path ? `<div class="row">📁 ${esc(e.path)}</div>` : ""}
            </div>
            <div class="tile-foot">
              <span class="tile-price">${e.available ? "Ready" : "Missing"}</span>
              ${
                e.download_url
                  ? `<a class="btn primary" href="${esc(e.download_url)}">Download</a>`
                  : `<span class="btn outline-green" style="opacity:.5;pointer-events:none">Unavailable</span>`
              }
            </div>
          </article>`
          )
          .join("")}
      </div>`;
  }

  async function renderProjects() {
    setActiveNav("projects");
    setCrumbs(["Projects"]);
    const p = state.project;
    page.innerHTML = `
      ${pageHeader("Projects", "Workspace projects available from local artifacts.")}
      <div class="tile-grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
        <article class="tile">
          <div class="tile-top">
            <div class="tile-id">${esc(p.name)}</div>
            ${badge(p.status)}
          </div>
          <div class="tile-meta">
            <div class="row">🏛 ${esc(p.publisher)}</div>
            <div class="row">📚 ${esc(p.framework)} · Grade ${esc(p.grade)}</div>
            <div class="row">▤ ${p.lessons} lessons · ${p.standards_total} standards</div>
          </div>
          <div class="tile-foot">
            <div class="tile-price">${esc(p.module)}</div>
            <a class="btn primary" href="#/overview">Open project</a>
          </div>
        </article>
      </div>`;
  }

  async function renderSettings() {
    setActiveNav("settings");
    setCrumbs(["Administration", "Settings"]);
    const health = await api("/api/health");
    page.innerHTML = `
      ${pageHeader("Settings", "Dashboard reads locked Batch-1 artifacts; it does not mutate the pipeline.")}
      <div class="tile-grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
        <article class="tile">
          <div class="tile-top"><div class="tile-id">Mode</div>${badge("ok")}</div>
          <div class="tile-meta"><div class="row">Read-only artifact viewer</div></div>
        </article>
        <article class="tile">
          <div class="tile-top"><div class="tile-id">Health</div>${health.ok ? badge("ok") : badge("none")}</div>
          <div class="tile-meta">
            <div class="row">▤ Lessons: ${health.lessons}</div>
            <div class="row">◎ Alignments: ${health.alignments}</div>
            ${health.error ? `<div class="row">⚠ ${esc(health.error)}</div>` : ""}
          </div>
          <div class="tile-foot">
            <span class="tile-price">Catalog</span>
            <button class="btn primary" id="reloadBtn2">Reload catalog</button>
          </div>
        </article>
      </div>`;
    $("#reloadBtn2")?.addEventListener("click", async () => {
      try {
        await postReload();
        state.project = null;
        location.hash = "#/overview";
        await route();
      } catch (e) {
        alert(e.message || e);
      }
    });
  }

  // Fix reload - api() is GET only. Use fetch for POST.
  async function postReload() {
    const res = await fetch("/api/reload", { method: "POST" });
    if (!res.ok) throw new Error("Reload failed");
    return res.json();
  }

  async function route() {
    closeDrawer();
    const hash = location.hash || "#/overview";
    const path = hash.replace(/^#\/?/, "");
    const [seg, ...rest] = path.split("/");
    try {
      if (!state.project) {
        state.project = await api("/api/project");
        if (workspaceChip) workspaceChip.textContent = state.project.name;
      }
      if (seg === "overview" || seg === "") await renderOverview();
      else if (seg === "alignments" && rest[0]) await showAlignmentDrawer(decodeURIComponent(rest.join("/")));
      else if (seg === "alignments") await renderAlignments();
      else if (seg === "evidence") await renderEvidence();
      else if (seg === "review") await renderReview();
      else if (seg === "standards") await renderStandards();
      else if (seg === "curriculum") await renderCurriculum();
      else if (seg === "lessons" && rest[0]) await renderLesson(decodeURIComponent(rest[0]));
      else if (seg === "ingestion") await renderIngestion();
      else if (seg === "pipeline") await renderPipeline();
      else if (seg === "retrieval") await renderRetrieval();
      else if (seg === "judge") await renderJudge();
      else if (seg === "qa") await renderQa();
      else if (seg === "runs") await renderRuns();
      else if (seg === "exports") await renderExports();
      else if (seg === "projects") await renderProjects();
      else if (seg === "settings") await renderSettings();
      else page.innerHTML = empty("Not found", "This view is not available.", `<a class="btn" href="#/overview">Back to overview</a>`);
    } catch (e) {
      page.innerHTML = errorBox(e);
    }
  }

  // Search
  let searchTimer = null;
  $("#globalSearch")?.addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim();
    if (!q) {
      searchPop.hidden = true;
      return;
    }
    searchTimer = setTimeout(async () => {
      try {
        const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
        if (!data.hits.length) {
          searchPop.innerHTML = `<div style="padding:10px;color:var(--muted)">No results</div>`;
        } else {
          searchPop.innerHTML = data.hits
            .map(
              (h) =>
                `<a href="${esc(h.href)}"><span class="cat">${esc(h.category)}</span>${esc(h.label)}</a>`
            )
            .join("");
        }
        searchPop.hidden = false;
      } catch {
        searchPop.hidden = true;
      }
    }, 200);
  });
  searchPop?.addEventListener("click", () => {
    searchPop.hidden = true;
  });
  $("#drawerBackdrop")?.addEventListener("click", closeDrawer);
  $("#menuBtn")?.addEventListener("click", toggleNav);
  $("#menuBtnTop")?.addEventListener("click", toggleNav);
  $$(".sidebar a[data-nav]").forEach((a) => {
    a.addEventListener("click", () => {
      if (window.matchMedia("(max-width: 900px)").matches) {
        appShell?.classList.add("nav-collapsed");
      }
    });
  });
  if (window.matchMedia("(max-width: 900px)").matches) {
    appShell?.classList.add("nav-collapsed");
  }
  $("#reloadBtn")?.addEventListener("click", async () => {
    try {
      await postReload();
      state.project = null;
      await route();
    } catch (e) {
      alert(e.message || e);
    }
  });

  window.addEventListener("hashchange", route);
  route();
})();
