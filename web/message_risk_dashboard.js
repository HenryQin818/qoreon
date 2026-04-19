(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const REPORT = (DATA && DATA.message_risk_report && typeof DATA.message_risk_report === "object")
    ? DATA.message_risk_report
    : {};
  const SNAPSHOT = (REPORT.snapshot && typeof REPORT.snapshot === "object") ? REPORT.snapshot : {};
  const HERO = (REPORT.hero && typeof REPORT.hero === "object") ? REPORT.hero : {};

  function text(value, fallback = "") {
    const out = String(value == null ? "" : value).trim();
    return out || fallback;
  }

  function rows(value) {
    return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
  }

  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === "class") node.className = String(value || "");
      else if (key === "text") node.textContent = String(value || "");
      else if (key === "html") node.innerHTML = String(value || "");
      else node.setAttribute(key, String(value));
    });
    (children || []).forEach((child) => node.appendChild(child));
    return node;
  }

  function setQuickLink(id, key, fallback) {
    const node = document.getElementById(id);
    if (!node) return;
    node.href = String(LINKS[key] || fallback || node.getAttribute("href") || "");
  }

  function toneClass(value) {
    const tone = String(value || "").trim().toLowerCase();
    if (!tone) return "";
    return "tone-" + tone;
  }

  function severityClass(value) {
    return "severity-" + text(value, "p2").toLowerCase();
  }

  function priorityClass(value) {
    return "priority-" + text(value, "p2").toLowerCase();
  }

  function barTone(row) {
    const tone = text(row.tone, "").toLowerCase();
    if (tone === "warn" || tone === "danger") return tone;
    return "";
  }

  function renderHero() {
    const heroKicker = document.getElementById("heroKicker");
    const heroTitle = document.getElementById("heroTitle");
    const heroSubtitle = document.getElementById("heroSubtitle");
    const generatedAtChip = document.getElementById("generatedAtChip");
    const branchChip = document.getElementById("branchChip");
    const scopeChip = document.getElementById("scopeChip");
    if (heroKicker) heroKicker.textContent = text(HERO.kicker, "Message Risk Dashboard");
    if (heroTitle) heroTitle.textContent = text(HERO.headline, "消息风险看板");
    if (heroSubtitle) heroSubtitle.textContent = text(HERO.summary, "");
    if (generatedAtChip) generatedAtChip.textContent = text(DATA.generated_at, "生成中");
    if (branchChip) branchChip.textContent = "branch " + text(SNAPSHOT.current_branch, "-");
    if (scopeChip) scopeChip.textContent = "样本 " + text(SNAPSHOT.runs_dir, "-");
  }

  function renderSummaryCards() {
    const wrap = document.getElementById("summaryGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.summary_cards).forEach((item) => {
      wrap.appendChild(el("article", { class: "metric-card " + toneClass(item.tone) }, [
        el("div", { class: "metric-label", text: text(item.label, "-") }),
        el("div", { class: "metric-value", text: text(item.value, "-") }),
        el("div", { class: "metric-note", text: text(item.note, "") }),
      ]));
    });
  }

  function renderPipeline() {
    const wrap = document.getElementById("pipelineGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.pipeline).forEach((item, index) => {
      const fields = Array.isArray(item.fields) ? item.fields : [];
      const refs = Array.isArray(item.refs) ? item.refs : [];
      const card = el("article", { class: "pipeline-card" }, [
        el("div", { class: "pipeline-step", text: "STEP " + String(index + 1).padStart(2, "0") }),
        el("div", { class: "pipeline-title", text: text(item.name, "-") }),
        el("div", { class: "pipeline-summary", text: text(item.summary, "") }),
      ]);
      if (fields.length) {
        const list = el("div", { class: "pipeline-list" });
        fields.forEach((field) => list.appendChild(el("span", { text: text(field, "") })));
        card.appendChild(list);
      }
      if (refs.length) {
        card.appendChild(el("div", { class: "reference-note", text: "参考: " + refs.join(" · ") }));
      }
      wrap.appendChild(card);
    });
  }

  function renderComparisons() {
    const wrap = document.getElementById("comparisonGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.comparisons).forEach((panel) => {
      const card = el("article", { class: "comparison-card" }, [
        el("h3", { text: text(panel.title, "-") }),
        el("p", { text: text(panel.description, "") }),
      ]);
      const stack = el("div", { class: "bar-stack" });
      rows(panel.rows).forEach((row) => {
        stack.appendChild(el("div", { class: "bar-row" }, [
          el("div", { class: "bar-head" }, [
            el("div", { class: "bar-label", text: text(row.label, "-") }),
            el("div", { class: "bar-value", text: `${text(row.value, "-")} · ${text(row.percent, "0")}%` }),
          ]),
          el("div", { class: "bar-bg" }, [
            el("div", { class: "bar-fill " + barTone(row), style: `width:${Math.max(0, Math.min(100, Number(row.percent || 0)))}%;` }),
          ]),
          el("div", { class: "bar-note", text: text(row.note, "") }),
        ]));
      });
      card.appendChild(stack);
      wrap.appendChild(card);
    });
  }

  function renderFindings() {
    const wrap = document.getElementById("findingGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.findings).forEach((item) => {
      const card = el("article", { class: "finding-card" }, [
        el("div", { class: "finding-head" }, [
          el("div", { class: "finding-title", text: text(item.title, "-") }),
          el("span", { class: "severity-chip " + severityClass(item.severity), text: text(item.severity, "P2") }),
        ]),
        el("div", { class: "finding-summary", text: text(item.summary, "") }),
        el("div", { class: "finding-impact", html: `<strong>影响</strong> ${text(item.impact, "")}` }),
        el("div", { class: "finding-action", html: `<strong>建议</strong> ${text(item.recommendation, "")}` }),
      ]);
      const evidence = el("div", { class: "finding-evidence" });
      rows((item.evidence || []).map((value) => ({ value }))).forEach((row) => {
        evidence.appendChild(el("div", { class: "evidence-item", text: text(row.value, "") }));
      });
      card.appendChild(evidence);
      const refs = Array.isArray(item.refs) ? item.refs : [];
      if (refs.length) {
        const refWrap = el("div", { class: "evidence-list" });
        refs.forEach((ref) => refWrap.appendChild(el("span", { text: text(ref, "") })));
        card.appendChild(refWrap);
      }
      wrap.appendChild(card);
    });
  }

  function renderTables() {
    const wrap = document.getElementById("tableStack");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.tables).forEach((table) => {
      const card = el("section", { class: "table-card" }, [
        el("h3", { text: text(table.title, "-") }),
        el("p", { text: text(table.description, "") }),
      ]);
      const stack = el("div", { class: "bar-stack" });
      rows(table.rows).forEach((row) => {
        stack.appendChild(el("div", { class: "bar-row" }, [
          el("div", { class: "bar-head" }, [
            el("div", { class: "bar-label", text: text(row.label, "-") }),
            el("div", { class: "bar-value", text: `${text(row.value, "-")} · ${text(row.percent, "0")}%` }),
          ]),
          el("div", { class: "bar-bg" }, [
            el("div", { class: "bar-fill", style: `width:${Math.max(0, Math.min(100, Number(row.percent || 0)))}%;` }),
          ]),
        ]));
      });
      card.appendChild(stack);
      wrap.appendChild(card);
    });
  }

  function renderActions() {
    const wrap = document.getElementById("actionList");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.actions).forEach((item) => {
      wrap.appendChild(el("article", { class: "action-item" }, [
        el("div", { class: "action-head" }, [
          el("div", { class: "action-title", text: text(item.title, "-") }),
          el("span", { class: "priority-chip " + priorityClass(item.priority), text: text(item.priority, "P2") }),
        ]),
        el("div", { class: "action-detail", text: text(item.detail, "") }),
      ]));
    });
  }

  function renderReferences() {
    const wrap = document.getElementById("referenceList");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.references).forEach((item) => {
      wrap.appendChild(el("article", { class: "reference-item" }, [
        el("div", { class: "reference-head" }, [
          el("div", { class: "reference-title", text: text(item.label, "资料") }),
          el("span", { class: "ref-chip", text: "证据" }),
        ]),
        el("div", { class: "reference-path", text: text(item.path, "-") }),
        el("div", { class: "reference-note", text: text(item.note, "") }),
      ]));
    });
  }

  renderHero();
  setQuickLink("overviewLink", "overview_page", "/share/project-overview-dashboard.html");
  setQuickLink("taskLink", "task_page", "/share/project-task-dashboard.html");
  setQuickLink("communicationLink", "communication_page", "/share/project-communication-audit.html");
  setQuickLink("statusReportLink", "status_report_page", "/share/project-status-report.html");
  setQuickLink("sessionHealthLink", "session_health_page", "/share/project-session-health-dashboard.html");
  renderSummaryCards();
  renderPipeline();
  renderComparisons();
  renderFindings();
  renderTables();
  renderActions();
  renderReferences();
})();
