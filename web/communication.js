(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const DEFAULT_SCOPES = ["hot", "repo_flat"];
  const STATE = {
    reports: {},
    scopeOrder: [],
    activeScope: "",
    loading: false,
    deepScanned: false,
    health: null,
  };

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

  function fmtNumber(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toLocaleString("zh-CN") : "0";
  }

  function fmtPct(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? `${n.toFixed(n % 1 === 0 ? 0 : 1)}%` : "0%";
  }

  function pctValue(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, n));
  }

  function donutStroke(value) {
    const pct = pctValue(value);
    const circumference = 2 * Math.PI * 42;
    const length = circumference * (pct / 100);
    return {
      circumference,
      dasharray: `${length} ${Math.max(0, circumference - length)}`,
    };
  }

  function toneForRate(value, { warnAt = 35, dangerAt = 15, invert = false } = {}) {
    const pct = pctValue(value);
    if (invert) {
      if (pct >= dangerAt) return "danger";
      if (pct >= warnAt) return "warn";
      return "accent";
    }
    if (pct <= dangerAt) return "danger";
    if (pct <= warnAt) return "warn";
    return "accent";
  }

  function fmtSeconds(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return "-";
    if (n < 60) return `${Math.round(n)}s`;
    if (n < 3600) return `${(n / 60).toFixed(n % 60 === 0 ? 0 : 1)}m`;
    return `${(n / 3600).toFixed(1)}h`;
  }

  async function fetchJson(url) {
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  }

  async function loadHealth() {
    try {
      STATE.health = await fetchJson("/__health");
    } catch (_) {
      STATE.health = null;
    }
    renderHeader();
  }

  function currentProjectId() {
    const params = new URLSearchParams(window.location.search || "");
    const hash = String(window.location.hash || "").replace(/^#/, "").trim();
    if (hash) {
      const hashParams = new URLSearchParams(hash);
      if (hashParams.get("p")) return String(hashParams.get("p") || "").trim();
      if (hashParams.get("project_id")) return String(hashParams.get("project_id") || "").trim();
    }
    return String(params.get("p") || params.get("project_id") || DATA.project_id || "").trim();
  }

  function renderHeader() {
    const envBadge = document.getElementById("envBadge");
    const guardMeta = document.getElementById("guardMeta");
    const overviewLink = document.getElementById("overviewLink");
    const taskLink = document.getElementById("taskLink");
    const statusReportLink = document.getElementById("statusReportLink");
    const sessionHealthLink = document.getElementById("sessionHealthLink");
    if (overviewLink) overviewLink.href = String(LINKS.overview_page || "/share/project-overview-dashboard.html");
    if (taskLink) taskLink.href = String(LINKS.task_page || "/share/project-task-dashboard.html");
    if (statusReportLink) statusReportLink.href = String(
      DATA.status_report_page
      || LINKS.status_report_page
      || "/share/project-status-report.html"
    );
    if (sessionHealthLink) {
      const base = String(
        DATA.session_health_page
        || LINKS.session_health_page
        || "/share/project-session-health-dashboard.html"
      );
      const pid = currentProjectId();
      sessionHealthLink.href = pid ? `${base}#p=${encodeURIComponent(pid)}` : base;
    }
    const health = STATE.health || {};
    const env = String(health.environment || DATA.environment || "stable");
    if (envBadge) envBadge.textContent = `环境 ${env}`;
    if (guardMeta) {
      const parts = [
        "分析页只读",
        `默认范围 ${DEFAULT_SCOPES.join(" + ")}`,
      ];
      if (health.port) parts.push(`端口 ${health.port}`);
      if (health.runsDir) parts.push(`运行根 ${health.runsDir}`);
      guardMeta.textContent = parts.join(" · ");
    }
  }

  async function loadReports(scopes, { append = false } = {}) {
    STATE.loading = true;
    try {
      const query = new URLSearchParams();
      query.set("scopes", scopes.join(","));
      const payload = await fetchJson(`/api/communication/audit?${query.toString()}`);
      const incoming = (payload && payload.reports && typeof payload.reports === "object") ? payload.reports : {};
      if (!append) {
        STATE.reports = {};
        STATE.scopeOrder = [];
      }
      Object.keys(incoming).forEach((scope) => {
        STATE.reports[scope] = incoming[scope];
        if (!STATE.scopeOrder.includes(scope)) STATE.scopeOrder.push(scope);
      });
      if (!STATE.activeScope || !STATE.reports[STATE.activeScope]) {
        STATE.activeScope = STATE.scopeOrder[0] || "";
      }
      if (scopes.includes("runtime_all")) STATE.deepScanned = true;
      renderAll();
    } finally {
      STATE.loading = false;
      updateButtons();
    }
  }

  function updateButtons() {
    const refreshBtn = document.getElementById("refreshBtn");
    const deepScanBtn = document.getElementById("deepScanBtn");
    if (refreshBtn) refreshBtn.disabled = !!STATE.loading;
    if (deepScanBtn) {
      deepScanBtn.disabled = !!STATE.loading || STATE.deepScanned;
      deepScanBtn.textContent = STATE.deepScanned ? "已深扫" : "深扫运行态";
    }
  }

  function card(label, value, note, tone = "") {
    const cls = `summary-card${tone ? ` ${tone}` : ""}`;
    return el("article", { class: cls }, [
      el("div", { class: "summary-label", text: label }),
      el("div", { class: "summary-value", text: value }),
      el("div", { class: "summary-note", text: note }),
    ]);
  }

  function metricCard(name, value, desc, tone = "") {
    return el("article", { class: `metric-card${tone ? ` ${tone}` : ""}` }, [
      el("div", { class: "metric-name", text: name }),
      el("div", { class: "metric-value", text: value }),
      el("div", { class: "metric-desc", text: desc }),
    ]);
  }

  function renderDonutCard({ title, desc, value, label, tone, legends }) {
    const stroke = donutStroke(value);
    const card = el("section", { class: `visual-card ${tone}` }, [
      el("h3", { text: title }),
      el("p", { text: desc }),
    ]);
    const donutRow = el("div", { class: "donut-row" });
    const donut = el("div", { class: "donut" });
    donut.innerHTML = `
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle class="donut-track" cx="50" cy="50" r="42"></circle>
        <circle class="donut-fill" cx="50" cy="50" r="42" stroke-dasharray="${stroke.dasharray}" stroke-dashoffset="0"></circle>
      </svg>
      <div class="donut-center">
        <div>
          <div class="donut-value">${fmtPct(value)}</div>
          <div class="donut-label">${label}</div>
        </div>
      </div>
    `;
    donutRow.appendChild(donut);
    const legend = el("div", { class: "donut-legend" });
    legends.forEach((item) => {
      legend.appendChild(el("div", { class: "legend-row" }, [
        el("span", { class: `legend-dot ${item.tone || "accent"}` }),
        el("div", { class: "legend-text", text: item.label }),
        el("div", { class: "legend-note", text: item.note }),
      ]));
    });
    donutRow.appendChild(legend);
    card.appendChild(donutRow);
    return card;
  }

  function renderBarChartCard({ title, desc, rows, tone = "accent" }) {
    const card = el("section", { class: `visual-card ${tone}` }, [
      el("h3", { text: title }),
      el("p", { text: desc }),
    ]);
    const stack = el("div", { class: "chart-stack" });
    (rows || []).forEach((row) => {
      const pct = pctValue(row.percent);
      const barTone = row.tone || tone;
      stack.appendChild(el("div", { class: "chart-row" }, [
        el("div", { class: "chart-headline" }, [
          el("div", { class: "chart-label", text: row.label }),
          el("div", { class: "chart-value", text: row.value }),
        ]),
        el("div", { class: "chart-bar" }, [
          el("div", { class: `chart-fill ${barTone}` , style: `width:${pct}%;` }),
        ]),
        el("div", { class: "chart-foot" }, [
          el("span", { text: fmtPct(row.percent) }),
          el("span", { text: row.note || "" }),
        ]),
      ]));
    });
    card.appendChild(stack);
    return card;
  }

  function renderOverviewCards(report) {
    const wrap = document.getElementById("overviewCards");
    if (!wrap) return;
    wrap.innerHTML = "";
    const summary = (report && report.summary) || {};
    const totals = summary.totals || {};
    const rates = summary.rates || {};
    wrap.appendChild(card("总样本", fmtNumber(totals.runs || 0), report ? String(report.label || "") : "-"));
    wrap.appendChild(card("显式回复率", fmtPct(rates.reply_to_rate_pct), `reply_to ${fmtNumber(totals.reply_to_runs || 0)} 条`));
    wrap.appendChild(card("结构化沟通覆盖", fmtPct(rates.communication_view_rate_pct), `communication_view ${fmtNumber(totals.communication_view_runs || 0)} 条`, Number(rates.communication_view_rate_pct || 0) < 50 ? "warn" : ""));
    wrap.appendChild(card("legacy 占比", fmtPct(rates.legacy_rate_pct), `legacy ${fmtNumber(totals.legacy_runs || 0)} 条`, Number(rates.legacy_rate_pct || 0) > 10 ? "danger" : ""));
  }

  function renderVisualGrid(report) {
    const wrap = document.getElementById("visualGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const summary = (report && report.summary) || {};
    const totals = summary.totals || {};
    const rates = summary.rates || {};
    const senderRows = (summary.sender_type_breakdown || []).slice(0, 4);
    const statusRows = (summary.status_breakdown || []).slice(0, 4);
    const replyTone = toneForRate(rates.reply_to_rate_pct, { warnAt: 45, dangerAt: 25 });
    const legacyTone = toneForRate(rates.legacy_rate_pct, { warnAt: 8, dangerAt: 16, invert: true });

    wrap.appendChild(renderDonutCard({
      title: "沟通闭环体感",
      desc: "把回复、结构化落盘和 @协同对象 使用合并到一张总览图。",
      value: rates.reply_to_rate_pct,
      label: "reply",
      tone: replyTone,
      legends: [
        { label: "显式回复", note: `${fmtNumber(totals.reply_to_runs || 0)} 条`, tone: "accent" },
        { label: "communication_view", note: fmtPct(rates.communication_view_rate_pct), tone: "warn" },
        { label: "@协同对象", note: fmtPct(rates.mention_target_rate_pct), tone: "danger" },
      ],
    }));

    wrap.appendChild(renderBarChartCard({
      title: "发送主体占比（sender_type）",
      desc: "谁在主导对话推进，一眼看清。",
      tone: "accent",
      rows: senderRows.map((row) => ({
        label: String(row.name || "-"),
        value: fmtNumber(row.count),
        percent: row.percent,
        note: "样本占比",
      })),
    }));

    wrap.appendChild(renderBarChartCard({
      title: "运行状态热区",
      desc: "error / done / running 的当前分布。",
      tone: legacyTone,
      rows: statusRows.map((row) => ({
        label: String(row.name || "-"),
        value: fmtNumber(row.count),
        percent: row.percent,
        note: row.name === "error" ? "需要关注" : "状态占比",
        tone: row.name === "error" ? "danger" : (row.name === "done" ? "accent" : "warn"),
      })),
    }));
  }

  function renderScopeTabs() {
    const tabs = document.getElementById("scopeTabs");
    if (!tabs) return;
    tabs.innerHTML = "";
    STATE.scopeOrder.forEach((scope) => {
      const report = STATE.reports[scope] || {};
      const btn = el("button", {
        class: `tab-btn${scope === STATE.activeScope ? " active" : ""}`,
        type: "button",
        text: String(report.label || scope),
      });
      btn.addEventListener("click", () => {
        STATE.activeScope = scope;
        renderAll();
      });
      tabs.appendChild(btn);
    });
  }

  function renderMetricGrid(report) {
    const grid = document.getElementById("metricGrid");
    const title = document.getElementById("reportTitle");
    const desc = document.getElementById("reportDesc");
    const meta = document.getElementById("reportMeta");
    if (!grid) return;
    const summary = (report && report.summary) || {};
    const rates = summary.rates || {};
    const totals = summary.totals || {};
    if (title) title.textContent = String(report && report.label || "通讯概览");
    if (desc) desc.textContent = String(report && report.description || "-");
    if (meta) {
      const timeRange = summary.time_range || {};
      meta.textContent = `${timeRange.first_created_at || "-"} -> ${timeRange.last_created_at || "-"}`;
    }
    grid.innerHTML = "";
    grid.appendChild(metricCard("communication_view 覆盖率", fmtPct(rates.communication_view_rate_pct), "message_kind/source_ref/callback_to 等结构化沟通字段的落盘覆盖率", Number(rates.communication_view_rate_pct || 0) < 30 ? "warn" : ""));
    grid.appendChild(metricCard("receipt_summary 覆盖率", fmtPct(rates.receipt_summary_rate_pct), "回执摘要能否稳定支撑 task 与分析页的统一解释"));
    grid.appendChild(metricCard("@协同对象使用率", fmtPct(rates.mention_target_rate_pct), `mention_targets ${fmtNumber(totals.mention_target_runs || 0)} 条`));
    grid.appendChild(metricCard("callback 路由错配率", fmtPct(rates.route_mismatch_rate_pct), "只在 communication_view 内统计", Number(rates.route_mismatch_rate_pct || 0) > 20 ? "danger" : ""));
    grid.appendChild(metricCard("错误率", fmtPct(((summary.status_breakdown || []).find((x) => x.name === "error") || {}).percent || 0), "按 run 状态统计"));
    grid.appendChild(metricCard("显式回复数量", fmtNumber(totals.reply_to_runs || 0), "当前样本中真正使用 reply_to 的条数"));
  }

  function renderResponseList(report) {
    const box = document.getElementById("responseList");
    if (!box) return;
    const response = ((report || {}).summary || {}).response_metrics || {};
    const items = [
      { title: "用户消息同通道响应率", value: fmtPct(response.user_responded_same_channel_rate_pct), note: `中位响应 ${fmtSeconds(response.median_user_same_channel_latency_s)}` },
      { title: "用户消息同会话响应率", value: fmtPct(response.user_responded_same_session_rate_pct), note: `样本 ${fmtNumber(response.user_total || 0)}` },
      { title: "Agent 后续系统跟进率", value: fmtPct(response.agent_system_follow_same_session_rate_pct), note: `中位跟进 ${fmtSeconds(response.median_agent_system_follow_latency_s)}` },
      { title: "显式 reply_to 中位时延", value: fmtSeconds(response.median_explicit_reply_latency_s), note: `reply_to ${fmtNumber(response.explicit_reply_count || 0)} 条` },
    ];
    box.innerHTML = "";
    items.forEach((item) => {
      box.appendChild(el("div", { class: "response-item" }, [
        el("strong", { text: item.value }),
        el("div", { text: item.title }),
        el("span", { text: item.note }),
      ]));
    });
  }

  function renderRankCard(title, rows, formatter) {
    const card = el("section", { class: "rank-card" });
    card.appendChild(el("h3", { text: title }));
    const list = el("ol", { class: "rank-list" });
    if (!rows.length) {
      list.appendChild(el("li", { class: "empty", text: "暂无数据" }));
    } else {
      rows.forEach((row) => {
        list.appendChild(el("li", { class: "rank-row" }, [
          el("div", { class: "rank-row-main" }, [
            el("div", { class: "rank-row-name", text: String(row.name || "-") }),
            el("div", { class: "rank-row-bar" }, [
              el("span", { style: `width:${pctValue(row.percent)}%;` }),
            ]),
          ]),
          el("div", { class: "rank-row-meta", text: formatter(row) }),
        ]));
      });
    }
    card.appendChild(list);
    return card;
  }

  function renderDistributionGrid(report) {
    const wrap = document.getElementById("distributionGrid");
    if (!wrap) return;
    const summary = (report && report.summary) || {};
    wrap.innerHTML = "";
    wrap.appendChild(renderRankCard("发送主体（sender_type）", summary.sender_type_breakdown || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
    wrap.appendChild(renderRankCard("状态分布", summary.status_breakdown || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
    wrap.appendChild(renderRankCard("消息类型（message_kind）", summary.communication_message_kind_breakdown || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
    wrap.appendChild(renderRankCard("回执汇总类型", summary.receipt_summary_message_kind_breakdown || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
  }

  function renderRankingGrid(report) {
    const wrap = document.getElementById("rankingGrid");
    if (!wrap) return;
    const summary = (report && report.summary) || {};
    wrap.innerHTML = "";
    wrap.appendChild(renderRankCard("Top 通道", summary.top_channels || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
    wrap.appendChild(renderRankCard("Top 来源通道", summary.top_source_channels || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
    wrap.appendChild(renderRankCard("Top sender_name", summary.top_sender_names || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
    wrap.appendChild(renderRankCard("Top 降级原因", summary.top_degrade_reasons || [], (row) => `${fmtNumber(row.count)} / ${fmtPct(row.percent)}`));
  }

  function renderAll() {
    renderHeader();
    renderScopeTabs();
    const report = STATE.reports[STATE.activeScope] || null;
    renderOverviewCards(report);
    renderVisualGrid(report);
    renderMetricGrid(report);
    renderResponseList(report);
    renderDistributionGrid(report);
    renderRankingGrid(report);
  }

  async function init() {
    updateButtons();
    document.getElementById("refreshBtn")?.addEventListener("click", () => loadReports(STATE.deepScanned ? ["hot", "repo_flat", "runtime_all"] : DEFAULT_SCOPES));
    document.getElementById("deepScanBtn")?.addEventListener("click", () => loadReports(["runtime_all"], { append: true }));
    await loadHealth();
    await loadReports(DEFAULT_SCOPES);
  }

  init().catch((err) => {
    const meta = document.getElementById("guardMeta");
    if (meta) meta.textContent = `分析页加载失败: ${String((err && err.message) || err || "unknown")}`;
  });
})();
