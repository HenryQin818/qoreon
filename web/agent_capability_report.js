(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const REPORT = (DATA && DATA.agent_capability_report && typeof DATA.agent_capability_report === "object")
    ? DATA.agent_capability_report
    : {};
  const HERO = (REPORT.hero && typeof REPORT.hero === "object") ? REPORT.hero : {};
  const SNAPSHOT = (REPORT.snapshot && typeof REPORT.snapshot === "object") ? REPORT.snapshot : {};

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
    const tone = text(value).toLowerCase();
    return tone ? "tone-" + tone : "";
  }

  function severityClass(value) {
    return "severity-" + text(value, "P2").toLowerCase();
  }

  function barTone(row) {
    const tone = text(row.tone).toLowerCase();
    if (tone === "warn" || tone === "danger") return tone;
    return "";
  }

  function renderHero() {
    const heroKicker = document.getElementById("heroKicker");
    const heroTitle = document.getElementById("heroTitle");
    const heroSubtitle = document.getElementById("heroSubtitle");
    const generatedAtChip = document.getElementById("generatedAtChip");
    const overallChip = document.getElementById("overallChip");
    const scopeChip = document.getElementById("scopeChip");

    if (heroKicker) heroKicker.textContent = text(HERO.kicker, "Agent Capability Check");
    if (heroTitle) heroTitle.textContent = text(HERO.headline, "对话Agent功能体检看板");
    if (heroSubtitle) heroSubtitle.textContent = text(HERO.summary, "");
    if (generatedAtChip) generatedAtChip.textContent = text(DATA.generated_at, "生成中");
    if (overallChip) overallChip.textContent = `总体 ${text(SNAPSHOT.overall_label, "-")} · ${text(SNAPSHOT.overall_score, "-")}/100`;
    if (scopeChip) scopeChip.textContent = `${text(SNAPSHOT.project_count, "0")} 项目 / ${text(SNAPSHOT.session_count, "0")} 会话`;
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

  function renderHealthGrid() {
    const wrap = document.getElementById("healthGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.health_panels).forEach((panel) => {
      const card = el("article", { class: "health-card " + toneClass(panel.tone) }, [
        el("div", { class: "health-head" }, [
          el("div", { class: "health-title", text: text(panel.title, "-") }),
          el("div", { class: "health-score", text: `${text(panel.score, "-")} · ${text(panel.label, "-")}` }),
        ]),
        el("div", { class: "health-summary", text: text(panel.summary, "") }),
      ]);
      const metricList = el("div", { class: "metric-list" });
      rows(panel.metrics).forEach((metric) => {
        metricList.appendChild(el("div", { class: "metric-row" }, [
          el("div", { class: "metric-row-label", text: text(metric.label, "-") }),
          el("div", { class: "metric-row-value", text: text(metric.value, "-") }),
          el("div", { class: "metric-row-note", text: text(metric.note, "") }),
        ]));
      });
      card.appendChild(metricList);
      wrap.appendChild(card);
    });
  }

  function renderComparisons() {
    const wrap = document.getElementById("comparisonGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    rows(REPORT.comparison_panels).forEach((panel) => {
      const card = el("article", { class: "comparison-card" }, [
        el("h3", { text: text(panel.title, "-") }),
        el("p", { text: text(panel.description, "") }),
      ]);
      const stack = el("div", { class: "bar-stack" });
      rows(panel.rows).forEach((row) => {
        const percent = Math.max(0, Math.min(100, Number(row.percent || 0)));
        stack.appendChild(el("div", { class: "bar-row" }, [
          el("div", { class: "bar-head" }, [
            el("div", { class: "bar-label", text: text(row.label, "-") }),
            el("div", { class: "bar-value", text: `${text(row.value, "-")} · ${text(row.percent, "0")}%` }),
          ]),
          el("div", { class: "bar-bg" }, [
            el("div", { class: `bar-fill ${barTone(row)}`.trim(), style: `width:${percent}%;` }),
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
        el("div", { class: "finding-block", html: `<strong>影响</strong> ${text(item.impact, "")}` }),
        el("div", { class: "finding-block", html: `<strong>建议</strong> ${text(item.recommendation, "")}` }),
      ]);
      const evidence = el("div", { class: "evidence-list" });
      (Array.isArray(item.evidence) ? item.evidence : []).forEach((value) => {
        evidence.appendChild(el("div", { class: "evidence-item", text: text(value, "") }));
      });
      card.appendChild(evidence);
      const refs = Array.isArray(item.refs) ? item.refs : [];
      if (refs.length) {
        const refRow = el("div", { class: "evidence-list" });
        refs.forEach((ref) => {
          refRow.appendChild(el("div", { class: "evidence-item", text: text(ref, "") }));
        });
        card.appendChild(refRow);
      }
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
          el("div", { class: "action-title", text: `${text(item.priority, "P2")} · ${text(item.title, "-")}` }),
          el("span", { class: `severity-chip ${severityClass(item.priority)}`.trim(), text: text(item.priority, "P2") }),
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
          el("div", { class: "reference-title", text: text(item.label, "参考资料") }),
          el("span", { class: "ref-chip", text: "真源" }),
        ]),
        el("div", { class: "reference-note", text: text(item.note, "") }),
        el("div", { class: "reference-path", text: text(item.path, "-") }),
      ]));
    });
  }

  renderHero();
  setQuickLink("overviewLink", "overview_page", "/share/project-overview-dashboard.html");
  setQuickLink("taskLink", "task_page", "/share/project-task-dashboard.html");
  setQuickLink("statusReportLink", "status_report_page", "/share/project-status-report.html");
  setQuickLink("sessionHealthLink", "session_health_page", "/share/project-session-health-dashboard.html");
  setQuickLink("messageRiskLink", "message_risk_page", "/share/project-message-risk-dashboard.html");
  setQuickLink("performanceLink", "performance_page", "/share/project-performance-diagnostics.html");
  renderSummaryCards();
  renderHealthGrid();
  renderComparisons();
  renderFindings();
  renderActions();
  renderReferences();
})();
