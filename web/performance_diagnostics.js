(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const BOARD = (DATA && DATA.performance_diagnostics && typeof DATA.performance_diagnostics === "object")
    ? DATA.performance_diagnostics
    : {};
  const HERO = (BOARD.hero && typeof BOARD.hero === "object") ? BOARD.hero : {};
  const LIVE = {
    snapshot: null,
    error: "",
  };

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

  function clamp(value, min = 0, max = 100) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return min;
    return Math.min(max, Math.max(min, n));
  }

  function toneClass(value) {
    const tone = text(value).toLowerCase();
    return tone ? `tone-${tone}` : "";
  }

  function toneFromScore(score) {
    if (score >= 78) return "danger";
    if (score >= 52) return "warn";
    return "good";
  }

  function numericFromText(value) {
    const match = String(value == null ? "" : value).match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : 0;
  }

  function numberFromPattern(value, pattern) {
    const match = String(value == null ? "" : value).match(pattern);
    return match ? Number(match[1]) : 0;
  }

  function parseTime(value) {
    const ts = Date.parse(String(value || "").trim());
    return Number.isFinite(ts) ? ts : null;
  }

  function formatZhDateTime(value) {
    const ts = parseTime(value);
    if (!ts) return "未更新";
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(ts));
  }

  function severityLabel(snapshot) {
    const severity = text(snapshot && snapshot.diagnosis && snapshot.diagnosis.severity, "good");
    if (severity === "danger") return "高压";
    if (severity === "warn") return "预警";
    return "正常";
  }

  function authHeaders() {
    try {
      const token = String(window.localStorage.getItem("taskDashboard.token") || "").trim();
      if (!token) return {};
      return { "X-TaskDashboard-Token": token };
    } catch (_err) {
      return {};
    }
  }

  function apiPath() {
    return text(BOARD.api_path, "/api/runtime/perf-snapshot");
  }

  function currentSnapshot() {
    return LIVE.snapshot && typeof LIVE.snapshot === "object" ? LIVE.snapshot : {};
  }

  function placeholderSummaryCards() {
    return [
      { label: "当前诊断", value: LIVE.error ? "采样异常" : "--", note: LIVE.error ? text(LIVE.error) : "等待 live 快照回传。", tone: "warn" },
      { label: "Chrome 聚合 CPU", value: "--", note: "浏览器 / GPU 主热点", tone: "good" },
      { label: "stable 服务 CPU", value: "--", note: "当前 runtime 压力", tone: "good" },
      { label: "Swap 已用", value: "--", note: "历史换页压力", tone: "good" },
      { label: "15 分钟请求量", value: "--", note: "轮询与请求总量", tone: "good" },
      { label: "自动化残留", value: "--", note: "Playwright / mcp / automation", tone: "good" },
    ];
  }

  function placeholderPanels() {
    return [
      { title: "机器层", tone: "good", summary: "浏览器/GPU、WindowServer、内存与 swap 的综合压力。", metrics: [] },
      { title: "服务层", tone: "good", summary: "stable runtime 的 CPU、RSS 与运行时长。", metrics: [] },
      { title: "请求层", tone: "good", summary: "多项目轮询与会话请求叠加情况。", metrics: [] },
      { title: "残留层", tone: "good", summary: "自动化浏览器、调试代理和孤儿进程残留。", metrics: [] },
    ];
  }

  function placeholderWindows() {
    return [
      { label: "5 分钟", value: "--", count: 0, note: "等待 5 分钟窗口数据。" },
      { label: "15 分钟", value: "--", count: 0, note: "等待 15 分钟窗口数据。" },
      { label: "60 分钟", value: "--", count: 0, note: "等待 60 分钟窗口数据。" },
    ];
  }

  function findPanel(snapshot, title) {
    return rows(snapshot && snapshot.panels).find((item) => text(item.title) === title) || null;
  }

  function findMetric(panel, label) {
    return rows(panel && panel.metrics).find((item) => text(item.label) === label) || null;
  }

  function metricValue(panel, label) {
    const metric = findMetric(panel, label);
    return text(metric && metric.value);
  }

  function metricNote(panel, label) {
    const metric = findMetric(panel, label);
    return text(metric && metric.note);
  }

  function createGauge(score, value, label, tone, extraClass = "") {
    const node = el("div", { class: `gauge-ring ${toneClass(tone)} ${extraClass}`.trim() });
    node.style.setProperty("--pct", `${clamp(score)}`);
    node.appendChild(el("div", { class: "gauge-core" }, [
      el("div", { class: "gauge-value", text: text(value, "--") }),
      el("div", { class: "gauge-label", text: text(label, "") }),
    ]));
    return node;
  }

  function cardScore(card) {
    const label = text(card && card.label);
    const valueText = text(card && card.value);
    const note = text(card && card.note);
    if (label === "当前诊断") {
      return severityLabel({ diagnosis: { severity: text(card && card.tone, "good") } }) === "高压" ? 92
        : (text(card && card.tone) === "warn" ? 68 : 32);
    }
    if (label === "Chrome 聚合 CPU") return clamp((numericFromText(valueText) / 140) * 100);
    if (label === "stable 服务 CPU") return clamp((numericFromText(valueText) / 100) * 100);
    if (label === "Swap 已用") return clamp(numberFromPattern(note, /(\d+(?:\.\d+)?)%/));
    if (label === "15 分钟请求量") {
      const rpm = numberFromPattern(note, /(\d+(?:\.\d+)?)\s*req\/min/);
      const polling = numberFromPattern(note, /轮询占比\s*(\d+(?:\.\d+)?)%/);
      return clamp(Math.max((rpm / 70) * 100, polling));
    }
    if (label === "自动化残留") {
      const cpu = numericFromText(note);
      const count = numericFromText(valueText);
      return clamp(Math.max((cpu / 30) * 100, (count / 6) * 100));
    }
    return clamp(numericFromText(valueText));
  }

  function buildRadarAxes(snapshot) {
    const machine = findPanel(snapshot, "机器层");
    const service = findPanel(snapshot, "服务层");
    const request = findPanel(snapshot, "请求层");
    const residue = findPanel(snapshot, "残留层");

    const machineScore = clamp(Math.max(
      numericFromText(metricValue(machine, "Chrome 聚合 CPU")) / 1.4,
      numericFromText(metricValue(machine, "WindowServer CPU")) / 0.8,
      numericFromText(metricValue(machine, "物理内存估算")),
      numericFromText(metricNote(machine, "Swap 已用"))
    ));
    const serviceScore = clamp(Math.max(
      numericFromText(metricValue(service, "服务 CPU")),
      numericFromText(metricValue(service, "服务 RSS")) / 24
    ));
    const requestScore = clamp(Math.max(
      numberFromPattern(metricNote(request, "5 分钟请求"), /(\d+(?:\.\d+)?)\s*req\/min/) / 0.7,
      numberFromPattern(metricNote(request, "15 分钟请求"), /轮询\s*(\d+(?:\.\d+)?)%/),
      numericFromText(metricValue(request, "最近错误率")) * 2
    ));
    const residueScore = clamp(Math.max(
      numericFromText(metricValue(residue, "残留 CPU")) / 0.3,
      numericFromText(metricValue(residue, "残留实例数")) / 0.06
    ));

    return [
      {
        label: "机器层",
        score: machineScore,
        tone: toneFromScore(machineScore),
        note: text(machine && machine.summary, "浏览器/GPU、WindowServer、内存与 swap 共同决定机器层体感。"),
      },
      {
        label: "服务层",
        score: serviceScore,
        tone: toneFromScore(serviceScore),
        note: text(service && service.summary, "当前 stable runtime 的 CPU、RSS 与运行时长。"),
      },
      {
        label: "请求层",
        score: requestScore,
        tone: toneFromScore(requestScore),
        note: text(request && request.summary, "多项目轮询是否在持续顶高 stable 服务。"),
      },
      {
        label: "残留层",
        score: residueScore,
        tone: toneFromScore(residueScore),
        note: text(residue && residue.summary, "自动化浏览器、调试代理与孤儿进程的残留压力。"),
      },
    ];
  }

  function renderHero(snapshot) {
    const diagnosis = (snapshot && snapshot.diagnosis && typeof snapshot.diagnosis === "object") ? snapshot.diagnosis : {};
    const axes = buildRadarAxes(snapshot);
    const tone = text(diagnosis.severity, LIVE.error ? "warn" : "good");
    const averageScore = axes.length
      ? axes.reduce((sum, item) => sum + Number(item.score || 0), 0) / axes.length
      : 0;
    const severityBase = tone === "danger" ? 92 : (tone === "warn" ? 68 : 34);
    const overallScore = Math.round((averageScore * 0.65) + (severityBase * 0.35));

    const heroKicker = document.getElementById("heroKicker");
    const heroTitle = document.getElementById("heroTitle");
    const heroSubtitle = document.getElementById("heroSubtitle");
    const generatedAtChip = document.getElementById("generatedAtChip");
    const severityChip = document.getElementById("severityChip");
    const runtimeChip = document.getElementById("runtimeChip");
    const summaryCard = document.getElementById("heroSummaryCard");
    const summaryTitle = document.getElementById("heroSummaryTitle");
    const severityBadge = document.getElementById("severityBadge");
    const overallGauge = document.getElementById("overallGauge");
    const overallScoreNode = document.getElementById("overallScore");
    const heroSummaryText = document.getElementById("heroSummaryText");
    const heroSignalGrid = document.getElementById("heroSignalGrid");

    if (heroKicker) heroKicker.textContent = text(HERO.kicker, "Ops Pressure Board");
    if (heroTitle) heroTitle.textContent = text(HERO.headline, "生产性能压力诊断看板");
    if (heroSubtitle) {
      heroSubtitle.textContent = LIVE.error
        ? `采样暂时失败，页面会按 ${text(BOARD.refresh_interval_seconds, "15")} 秒继续自动重试。`
        : text(diagnosis.summary, text(HERO.summary, text(BOARD.subtitle, "")));
    }
    if (generatedAtChip) generatedAtChip.textContent = formatZhDateTime(snapshot.generated_at || DATA.generated_at);
    if (severityChip) severityChip.textContent = `严重度 ${severityLabel(snapshot)}`;
    if (runtimeChip) runtimeChip.textContent = `${text(snapshot.environment, "-")} · ${text(snapshot.port, "-")}`;

    if (summaryCard) summaryCard.className = `hero-summary-card ${toneClass(tone)}`.trim();
    if (summaryTitle) summaryTitle.textContent = text(diagnosis.headline, "正在汇总当前性能结论");
    if (severityBadge) severityBadge.textContent = severityLabel(snapshot);
    if (overallGauge) {
      overallGauge.className = `gauge-ring gauge-ring-hero ${toneClass(tone)}`.trim();
      overallGauge.style.setProperty("--pct", `${clamp(overallScore)}`);
    }
    if (overallScoreNode) overallScoreNode.textContent = `${overallScore}`;
    if (heroSummaryText) {
      heroSummaryText.textContent = LIVE.error
        ? text(LIVE.error, "当前无法读取运行时压力快照。")
        : `${text(diagnosis.recommended_first_action, text(HERO.summary, ""))} 当前主结论为“${text(diagnosis.headline, "正常")}”。`;
    }

    if (heroSignalGrid) {
      heroSignalGrid.innerHTML = "";
      axes.forEach((item) => {
        const scoreText = `${Math.round(item.score)}`;
        const block = el("div", { class: `mini-signal ${toneClass(item.tone)}`.trim() }, [
          el("div", { class: "mini-signal-head" }, [
            el("span", { class: "mini-signal-label", text: item.label }),
            el("span", { class: "mini-signal-value", text: scoreText }),
          ]),
          el("div", { class: "mini-signal-track" }, [
            el("div", { class: "mini-signal-fill" }),
          ]),
        ]);
        const fill = block.querySelector(".mini-signal-fill");
        if (fill) fill.style.setProperty("--pct", `${clamp(item.score)}`);
        heroSignalGrid.appendChild(block);
      });
    }
  }

  function renderStatusBanner(snapshot) {
    const node = document.getElementById("statusBanner");
    if (!node) return;
    const diagnosis = (snapshot && snapshot.diagnosis && typeof snapshot.diagnosis === "object") ? snapshot.diagnosis : {};
    const tone = text(diagnosis.severity, LIVE.error ? "warn" : "good");
    node.className = `headline-band ${toneClass(tone)}`.trim();
    if (LIVE.error) {
      node.innerHTML = [
        `<strong>采样失败</strong>`,
        `<p>${text(LIVE.error, "无法读取运行时压力快照")}。页面会继续按 ${text(BOARD.refresh_interval_seconds, "15")} 秒自动重试。</p>`,
      ].join("");
      return;
    }
    const activeLabels = Array.isArray(diagnosis.active_labels)
      ? diagnosis.active_labels.map((item) => text(item)).filter(Boolean)
      : [];
    const chips = [
      `<span class="headline-pill">主判定 ${text(diagnosis.headline, "正常")}</span>`,
      `<span class="headline-pill">建议动作 ${text(diagnosis.recommended_first_action, "维持观察")}</span>`,
      ...activeLabels.slice(1).map((label) => `<span class="headline-pill">次级因素 ${label}</span>`),
    ];
    node.innerHTML = [
      `<strong>${text(diagnosis.headline, "当前压力整体可控")}</strong>`,
      `<p>${text(diagnosis.summary, text(HERO.summary, ""))}</p>`,
      `<div class="headline-meta">${chips.join("")}</div>`,
    ].join("");
  }

  function renderSignalGrid(snapshot) {
    const wrap = document.getElementById("signalGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const cards = rows(snapshot.summary_cards).length ? rows(snapshot.summary_cards) : placeholderSummaryCards();
    cards.forEach((item) => {
      const score = cardScore(item);
      const tone = text(item.tone, toneFromScore(score));
      const card = el("article", { class: `signal-card ${toneClass(tone)}`.trim() }, [
        createGauge(score, Math.round(score), text(item.label, "信号"), tone, ""),
        el("div", { class: "signal-meta" }, [
          el("div", { class: "signal-label", text: text(item.label, "-") }),
          el("div", { class: "signal-value", text: text(item.value, "-") }),
          el("div", { class: "signal-note", text: text(item.note, "") }),
          el("div", { class: "signal-chip", text: `${severityLabel({ diagnosis: { severity: tone } })} 信号` }),
        ]),
      ]);
      wrap.appendChild(card);
    });
  }

  function panelScore(snapshot, panel) {
    const title = text(panel && panel.title);
    return (buildRadarAxes(snapshot).find((item) => item.label === title) || {}).score || 0;
  }

  function renderPanels(snapshot) {
    const wrap = document.getElementById("panelGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const panels = rows(snapshot.panels).length ? rows(snapshot.panels) : placeholderPanels();
    panels.forEach((panel) => {
      const score = panelScore(snapshot, panel);
      const tone = text(panel.tone, toneFromScore(score));
      const card = el("article", { class: `panel-card ${toneClass(tone)}`.trim() });
      const trackFill = el("div", { class: "panel-meter-fill" });
      trackFill.style.setProperty("--pct", `${clamp(score)}`);
      card.appendChild(el("div", { class: "panel-card-head" }, [
        el("div", {}, [
          el("div", { class: "panel-title", text: text(panel.title, "-") }),
          el("div", { class: "panel-summary", text: text(panel.summary, "") }),
        ]),
        el("div", { class: "panel-meter" }, [
          el("div", { class: "panel-meter-value", text: `${Math.round(score)}` }),
          el("div", { class: "panel-meter-track" }, [trackFill]),
        ]),
      ]));
      const list = el("div", { class: "metric-grid" });
      rows(panel.metrics).forEach((metric) => {
        list.appendChild(el("div", { class: "metric-row" }, [
          el("div", { class: "metric-row-label", text: text(metric.label, "-") }),
          el("div", { class: "metric-row-value", text: text(metric.value, "-") }),
          el("div", { class: "metric-row-note", text: text(metric.note, "") }),
        ]));
      });
      card.appendChild(list);
      wrap.appendChild(card);
    });
  }

  function renderRadar(snapshot) {
    const svg = document.getElementById("radarChart");
    const legend = document.getElementById("radarLegend");
    if (!svg || !legend) return;
    const axes = buildRadarAxes(snapshot);
    svg.innerHTML = "";
    legend.innerHTML = "";
    if (!axes.length) {
      legend.appendChild(el("div", { class: "empty-state", text: "当前没有足够数据生成雷达图。" }));
      return;
    }
    const size = 360;
    const center = size / 2;
    const radius = 112;
    const labelRadius = 148;
    const total = axes.length;
    const colors = ["#56d8ff", "#8c9cff", "#49e0a4", "#ffbf61"];

    function point(index, scale) {
      const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / total);
      return {
        x: center + Math.cos(angle) * radius * scale,
        y: center + Math.sin(angle) * radius * scale,
      };
    }

    function pointString(scale) {
      return axes.map((_item, index) => {
        const p = point(index, scale);
        return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
      }).join(" ");
    }

    const labelMarkup = axes.map((item, index) => {
      const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / total);
      const x = center + Math.cos(angle) * labelRadius;
      const y = center + Math.sin(angle) * labelRadius;
      const anchor = Math.cos(angle) > 0.2 ? "start" : (Math.cos(angle) < -0.2 ? "end" : "middle");
      const baseline = Math.sin(angle) > 0.6 ? "hanging" : (Math.sin(angle) < -0.6 ? "auto" : "middle");
      return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" fill="#d9eeff" font-size="13" text-anchor="${anchor}" dominant-baseline="${baseline}">${item.label}</text>`;
    }).join("");

    const axisMarkup = axes.map((_item, index) => {
      const p = point(index, 1);
      return `<line x1="${center}" y1="${center}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}" stroke="rgba(113,214,255,0.18)" stroke-width="1"/>`;
    }).join("");

    const gridMarkup = [0.25, 0.5, 0.75, 1].map((scale, index) => (
      `<polygon points="${pointString(scale)}" fill="none" stroke="rgba(113,214,255,${0.08 + (index * 0.04)})" stroke-width="1"/>`
    )).join("");

    const dataPoints = axes.map((item, index) => {
      const p = point(index, clamp(item.score) / 100);
      return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    }).join(" ");

    const nodeMarkup = axes.map((item, index) => {
      const p = point(index, clamp(item.score) / 100);
      return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="5" fill="${colors[index % colors.length]}" stroke="#07111f" stroke-width="2"/>`;
    }).join("");

    svg.innerHTML = [
      `<defs>`,
      `<filter id="radarGlow"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`,
      `</defs>`,
      gridMarkup,
      axisMarkup,
      `<polygon points="${dataPoints}" fill="rgba(86,216,255,0.18)" stroke="#56d8ff" stroke-width="2" filter="url(#radarGlow)"/>`,
      nodeMarkup,
      labelMarkup,
      `<circle cx="${center}" cy="${center}" r="3.5" fill="#8bf3ff"/>`,
    ].join("");

    axes.forEach((item, index) => {
      const tone = text(item.tone, toneFromScore(item.score));
      const dot = el("span", { class: "radar-dot" });
      dot.style.color = colors[index % colors.length];
      legend.appendChild(el("article", { class: `radar-legend-card ${toneClass(tone)}`.trim() }, [
        el("div", { class: "radar-legend-head" }, [
          el("div", { class: "radar-legend-title" }, [
            dot,
            el("span", { text: item.label }),
          ]),
          el("div", { class: "radar-legend-score", text: `${Math.round(item.score)}` }),
        ]),
        el("div", { class: "radar-legend-note", text: text(item.note, "") }),
      ]));
    });
  }

  function renderWindows(snapshot) {
    const wrap = document.getElementById("windowChart");
    if (!wrap) return;
    wrap.innerHTML = "";
    const list = rows(snapshot.windows).length ? rows(snapshot.windows) : placeholderWindows();
    const maxCount = Math.max(...list.map((item) => Number(item.count || 0)), 1);
    list.forEach((item) => {
      const tone = toneFromScore(Math.max(
        (numberFromPattern(item.note, /(\d+(?:\.\d+)?)\s*req\/min/) / 0.7),
        numberFromPattern(item.note, /轮询\s*(\d+(?:\.\d+)?)%/),
        numberFromPattern(item.note, /错误\s*(\d+(?:\.\d+)?)%/) * 2
      ));
      const pct = Math.max(10, clamp((Number(item.count || 0) / maxCount) * 100));
      const fill = el("div", { class: "column-fill" });
      fill.style.setProperty("--pct", `${pct}`);
      wrap.appendChild(el("article", { class: `window-column ${toneClass(tone)}`.trim() }, [
        el("div", { class: "window-head" }, [
          el("div", { class: "window-title", text: text(item.label, "-") }),
          el("div", { class: "window-value", text: text(item.value, "-") }),
        ]),
        el("div", { class: "column-track" }, [fill]),
        el("div", { class: "window-note", text: text(item.note, "") }),
      ]));
    });
  }

  function renderBarList(id, rowsData, emptyText) {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    wrap.innerHTML = "";
    const list = rows(rowsData);
    if (!list.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: emptyText }));
      return;
    }
    list.forEach((item) => {
      const pct = clamp(item.percent);
      const tone = toneFromScore(pct);
      const fill = el("div", { class: "bar-fill" });
      fill.style.setProperty("--pct", `${pct}`);
      const card = el("article", { class: `bar-item ${toneClass(tone)}`.trim() }, [
        el("div", { class: "bar-head" }, [
          el("div", { class: "bar-title", text: text(item.label, "-") }),
          el("span", { class: "metric-pill", text: `${text(item.value, "-")} · ${pct.toFixed(1)}%` }),
        ]),
        el("div", { class: "bar-track" }, [fill]),
        el("div", { class: "bar-note", text: text(item.note, "") }),
      ]);
      wrap.appendChild(card);
    });
  }

  function renderProcessList(id, rowsData, emptyText) {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    wrap.innerHTML = "";
    const list = rows(rowsData);
    if (!list.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: emptyText }));
      return;
    }
    list.forEach((item) => {
      const pct = clamp(item.percent);
      const tone = text(item.tone, toneFromScore(pct));
      const fill = el("div", { class: "process-fill" });
      fill.style.setProperty("--pct", `${pct}`);
      const card = el("article", { class: `process-card ${toneClass(tone)}`.trim() }, [
        el("div", { class: "process-head" }, [
          el("div", { class: "process-title", text: text(item.label, "-") }),
          el("span", { class: "process-pill", text: `${text(item.value, "-")} · ${pct.toFixed(1)}%` }),
        ]),
        el("div", { class: "process-track" }, [fill]),
        el("div", { class: "process-note", text: text(item.note, "") }),
      ]);
      if (text(item.command)) {
        card.appendChild(el("div", { class: "process-command", text: text(item.command, "") }));
      }
      wrap.appendChild(card);
    });
  }

  function renderActions(snapshot) {
    const wrap = document.getElementById("actionList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const list = rows(snapshot.recommendations);
    if (!list.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有额外建议动作。" }));
      return;
    }
    list.forEach((item, index) => {
      wrap.appendChild(el("article", { class: "action-item" }, [
        el("div", { class: "action-head" }, [
          el("div", { class: "action-title", text: `${text(item.priority, `P${Math.min(index, 2)}`)} · ${text(item.title, "-")}` }),
          el("span", { class: "metric-pill", text: `步骤 ${index + 1}` }),
        ]),
        el("div", { class: "action-detail", text: text(item.detail, "") }),
      ]));
    });
  }

  function renderReferences(snapshot) {
    const wrap = document.getElementById("referenceList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const list = rows(snapshot.references);
    if (!list.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有参考真源。" }));
      return;
    }
    list.forEach((item) => {
      wrap.appendChild(el("article", { class: "reference-item" }, [
        el("div", { class: "reference-head" }, [
          el("div", { class: "reference-title", text: text(item.label, "-") }),
          el("span", { class: "metric-pill", text: "真源" }),
        ]),
        el("div", { class: "reference-note", text: text(item.note, "") }),
        el("div", { class: "reference-path", text: text(item.path, "-") }),
      ]));
    });
  }

  function formatDurationMs(value, fallback = "--") {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return fallback;
    if (n < 1000) return `${Math.round(n)} ms`;
    if (n < 60000) {
      const seconds = n / 1000;
      const rounded = seconds >= 10 ? Math.round(seconds) : Number(seconds.toFixed(1));
      return `${rounded} s`;
    }
    const minutes = n / 60000;
    if (minutes < 60) {
      const rounded = minutes >= 10 ? Math.round(minutes) : Number(minutes.toFixed(1));
      return `${rounded} min`;
    }
    const hours = n / 3600000;
    return `${Number(hours.toFixed(hours >= 10 ? 0 : 1))} h`;
  }

  function snapshotDiagnosticTone(buildSource, refreshState, fallbackReason) {
    const source = text(buildSource).toLowerCase();
    const refresh = text(refreshState).toLowerCase();
    const fallback = text(fallbackReason).toLowerCase();
    if (fallback || source === "fallback") return "danger";
    if (source === "stale_snapshot" || refresh === "started" || refresh === "running") return "warn";
    return "good";
  }

  function buildSnapshotBackgroundSummaryMeta(summary) {
    const payload = summary && typeof summary === "object" ? summary : {};
    const sessionsCount = Number(payload.sessions_count);
    const runtimeCount = Number(payload.runtime_state_count);
    const metricsCount = Number(payload.conversation_list_metrics_count);
    const heartbeatCount = Number(payload.heartbeat_summary_count);
    const generatedAt = text(payload.generated_at, "");
    const noteParts = [];

    if (Number.isFinite(runtimeCount)) noteParts.push(`runtime ${runtimeCount}`);
    if (Number.isFinite(metricsCount)) noteParts.push(`metrics ${metricsCount}`);
    if (Number.isFinite(heartbeatCount)) noteParts.push(`heartbeat ${heartbeatCount}`);

    return {
      value: Number.isFinite(sessionsCount) ? `${sessionsCount} 会话` : "未记录",
      note: noteParts.length ? noteParts.join(" · ") : "后台摘要尚未返回聚合计数",
      generatedAt,
    };
  }

  function describeSnapshotDiagnosticEvent(item, index) {
    const badge = text(item.event_type || item.kind || item.phase || item.state, "事件");
    const title = text(item.title || item.summary || item.label || item.detail, `结构化事件 ${index + 1}`);
    const eventAt = text(
      item.occurred_at || item.at || item.created_at || item.updated_at || item.finished_at,
      ""
    );
    const buildSource = text(item.build_source || item.source, "");
    const refreshState = text(item.refresh_state || item.background_refresh_state || item.state, "");
    const fallbackReason = text(item.fallback_reason || item.reason, "");
    const deliveryMode = text(item.delivery_mode || item.last_delivery_mode, "");
    const refreshTrigger = text(item.refresh_trigger || item.last_refresh_trigger, "");
    const chips = [];

    if (text(item.query_mode)) chips.push(`模式 ${text(item.query_mode)}`);
    if (buildSource) chips.push(`来源 ${buildSource}`);
    if (typeof item.hit === "boolean") chips.push(item.hit ? "命中" : "未命中");
    if (item.age_ms != null && text(item.age_ms) !== "") chips.push(`年龄 ${formatDurationMs(item.age_ms)}`);
    if (item.build_elapsed_ms != null && text(item.build_elapsed_ms) !== "") chips.push(`构建 ${formatDurationMs(item.build_elapsed_ms)}`);
    if (refreshState) chips.push(`刷新 ${refreshState}`);
    if (fallbackReason) chips.push(`回退 ${fallbackReason}`);
    if (Number.isFinite(Number(item.count)) && Number(item.count) > 1) chips.push(`聚合 ${Number(item.count)} 次`);
    if (item.window_ms != null && text(item.window_ms) !== "") chips.push(`窗口 ${formatDurationMs(item.window_ms)}`);
    if (deliveryMode) chips.push(`交付 ${deliveryMode}`);
    if (refreshTrigger) chips.push(`触发 ${refreshTrigger}`);

    const windowSummaryParts = [];
    if (text(item.first_at)) windowSummaryParts.push(`首条 ${formatZhDateTime(item.first_at)}`);
    if (text(item.last_at)) windowSummaryParts.push(`末条 ${formatZhDateTime(item.last_at)}`);

    const detailParts = [
      text(item.detail, ""),
      text(item.note, ""),
      windowSummaryParts.join(" · "),
    ].filter(Boolean);

    return {
      badge,
      title,
      at: eventAt ? formatZhDateTime(eventAt) : "未记录",
      note: detailParts.join(" "),
      chips,
      tone: snapshotDiagnosticTone(buildSource, refreshState, fallbackReason),
    };
  }

  function buildSnapshotDiagnosticsViewModel(snapshot) {
    const diagnostics = (snapshot && snapshot.sessions_snapshot_diagnostics
      && typeof snapshot.sessions_snapshot_diagnostics === "object")
      ? snapshot.sessions_snapshot_diagnostics
      : null;
    if (!diagnostics) {
      return {
        available: false,
        tone: LIVE.error ? "warn" : "good",
        cards: [],
        timeline: [],
        events: [],
      };
    }

    const enabledText = diagnostics.enabled === true ? "已开启"
      : diagnostics.enabled === false ? "已关闭"
        : "未声明";
    const queryMode = text(diagnostics.default_query_mode, "未声明");
    const buildSource = text(diagnostics.last_build_source, "未记录");
    const hitText = diagnostics.last_hit === true ? "命中"
      : diagnostics.last_hit === false ? "未命中"
        : "未知";
    const ageText = formatDurationMs(diagnostics.last_age_ms);
    const ttlText = formatDurationMs(diagnostics.ttl_ms);
    const staleTtlText = formatDurationMs(diagnostics.stale_ttl_ms);
    const buildElapsedText = formatDurationMs(diagnostics.last_build_elapsed_ms);
    const refreshState = text(diagnostics.refresh_state, "未记录");
    const fallbackReason = text(diagnostics.last_fallback_reason, "");
    const foregroundIntervalText = formatDurationMs(diagnostics.foreground_interval_ms);
    const backgroundIntervalText = formatDurationMs(diagnostics.background_interval_ms);
    const invalidationWindowText = formatDurationMs(diagnostics.invalidation_window_ms);
    const lastDeliveryMode = text(diagnostics.last_delivery_mode, "未记录");
    const lastRefreshTrigger = text(diagnostics.last_refresh_trigger, "未记录");
    const functionalLogMode = text(diagnostics.functional_log_mode, "未记录");
    const backgroundSummary = buildSnapshotBackgroundSummaryMeta(diagnostics.background_summary);
    const tone = snapshotDiagnosticTone(buildSource, refreshState, fallbackReason);

    return {
      available: true,
      tone,
      cards: [
        {
          label: "Snapshot 开关",
          value: enabledText,
          note: `默认查询模式 ${queryMode}`,
        },
        {
          label: "前台 / 后台节奏",
          value: `${foregroundIntervalText} / ${backgroundIntervalText}`,
          note: `失效聚合窗口 ${invalidationWindowText}`,
        },
        {
          label: "最近构建来源",
          value: buildSource,
          note: `最近请求 ${hitText}`,
        },
        {
          label: "快照年龄 / TTL",
          value: `${ageText} / ${ttlText}`,
          note: `stale TTL ${staleTtlText}`,
        },
        {
          label: "最近构建耗时",
          value: buildElapsedText,
          note: fallbackReason ? `回退原因 ${fallbackReason}` : "当前未记录 fallback 原因",
        },
        {
          label: "最终交付模式",
          value: lastDeliveryMode,
          note: `刷新触发 ${lastRefreshTrigger}`,
        },
        {
          label: "功能日志模式",
          value: functionalLogMode,
          note: "当前只展示结构化 registry，不展开 raw log。",
        },
        {
          label: "后台摘要",
          value: backgroundSummary.value,
          note: backgroundSummary.note,
        },
        {
          label: "刷新状态",
          value: refreshState,
          note: fallbackReason ? `当前诊断含回退 ${fallbackReason}` : "当前未见回退链条",
        },
      ],
      timeline: [
        {
          label: "最近失效",
          value: text(diagnostics.last_invalidated_at) ? formatZhDateTime(diagnostics.last_invalidated_at) : "未记录",
          note: text(diagnostics.last_invalidated_reason, ""),
        },
        {
          label: "最近刷新启动",
          value: text(diagnostics.last_refresh_started_at) ? formatZhDateTime(diagnostics.last_refresh_started_at) : "未记录",
          note: lastRefreshTrigger === "未记录" ? "" : `触发 ${lastRefreshTrigger}`,
        },
        {
          label: "最近刷新完成",
          value: text(diagnostics.last_refresh_finished_at) ? formatZhDateTime(diagnostics.last_refresh_finished_at) : "未记录",
          note: diagnostics.last_refresh_elapsed_ms != null
            ? `耗时 ${formatDurationMs(diagnostics.last_refresh_elapsed_ms)}`
            : "",
        },
        {
          label: "后台摘要生成",
          value: backgroundSummary.generatedAt ? formatZhDateTime(backgroundSummary.generatedAt) : "未记录",
          note: backgroundSummary.generatedAt
            ? `最终交付 ${lastDeliveryMode}`
            : "当前尚未返回后台摘要生成时间",
        },
      ],
      events: rows(diagnostics.recent_events).slice(0, 20).map((item, index) => describeSnapshotDiagnosticEvent(item, index)),
    };
  }

  function renderSnapshotDiagnostics(snapshot) {
    const section = document.getElementById("snapshotDiagnosticsSection");
    const grid = document.getElementById("snapshotDiagnosticGrid");
    const meta = document.getElementById("snapshotDiagnosticMeta");
    const eventsWrap = document.getElementById("snapshotEventList");
    if (!section || !grid || !meta || !eventsWrap) return;

    const view = buildSnapshotDiagnosticsViewModel(snapshot);
    section.className = `section-block snapshot-board ${toneClass(view.tone)}`.trim();
    grid.innerHTML = "";
    meta.innerHTML = "";
    eventsWrap.innerHTML = "";

    if (!view.available) {
      const emptyText = "当前 stable 尚未回传 sessions_snapshot_diagnostics 结构化字段；前端消费链已预留，字段到位后会自动展示。";
      grid.appendChild(el("div", { class: "empty-state", text: emptyText }));
      meta.appendChild(el("div", { class: "empty-state", text: "最近失效、刷新与回退时间线会在 additive 字段可用后直接出现。" }));
      eventsWrap.appendChild(el("div", { class: "empty-state", text: "当前没有可展示的 snapshot 结构化事件。" }));
      return;
    }

    view.cards.forEach((item) => {
      grid.appendChild(el("article", { class: `snapshot-diagnostic-card ${toneClass(view.tone)}`.trim() }, [
        el("div", { class: "snapshot-diagnostic-head" }, [
          el("div", { class: "snapshot-diagnostic-label", text: item.label }),
          el("span", { class: "metric-pill", text: "snapshot" }),
        ]),
        el("div", { class: "snapshot-diagnostic-value", text: text(item.value, "--") }),
        el("div", { class: "snapshot-diagnostic-note", text: text(item.note, "") }),
      ]));
    });

    view.timeline.forEach((item) => {
      meta.appendChild(el("article", { class: "snapshot-meta-item" }, [
        el("div", { class: "snapshot-meta-head" }, [
          el("div", { class: "snapshot-meta-label", text: item.label }),
          el("span", { class: "metric-pill", text: "时间点" }),
        ]),
        el("div", { class: "snapshot-meta-value", text: text(item.value, "未记录") }),
        el("div", { class: "snapshot-meta-note", text: text(item.note, "") }),
      ]));
    });

    if (!view.events.length) {
      eventsWrap.appendChild(el("div", { class: "empty-state", text: "当前没有最近事件，说明本轮尚未形成结构化 snapshot 诊断记录。" }));
      return;
    }

    view.events.forEach((item) => {
      const card = el("article", { class: `snapshot-event-item ${toneClass(item.tone)}`.trim() }, [
        el("div", { class: "snapshot-event-head" }, [
          el("div", {}, [
            el("div", { class: "snapshot-event-title", text: item.title }),
            el("div", { class: "snapshot-event-note", text: item.badge }),
          ]),
          el("div", { class: "snapshot-event-time", text: item.at }),
        ]),
      ]);
      if (text(item.note)) {
        card.appendChild(el("div", { class: "snapshot-event-note", text: item.note }));
      }
      if (item.chips.length) {
        const chipList = el("div", { class: "snapshot-event-chip-list" });
        item.chips.forEach((chip) => {
          chipList.appendChild(el("span", { class: "snapshot-event-chip", text: chip }));
        });
        card.appendChild(chipList);
      }
      eventsWrap.appendChild(card);
    });
  }

  function render() {
    const snapshot = currentSnapshot();
    renderHero(snapshot);
    renderStatusBanner(snapshot);
    renderSignalGrid(snapshot);
    renderPanels(snapshot);
    renderRadar(snapshot);
    renderWindows(snapshot);
    renderBarList("endpointList", snapshot.top_endpoints, "最近 15 分钟没有高频接口。");
    renderBarList("projectList", snapshot.top_projects, "最近 15 分钟没有热点项目。");
    renderBarList("sessionList", snapshot.top_sessions, "最近 15 分钟没有热点会话。");
    renderProcessList("processList", snapshot.top_processes, "当前没有显著高占用进程。");
    renderProcessList("automationList", snapshot.automation_processes, "当前没有识别到自动化残留。");
    renderActions(snapshot);
    renderReferences(snapshot);
    renderSnapshotDiagnostics(snapshot);
  }

  async function fetchSnapshot() {
    try {
      const resp = await fetch(apiPath(), { headers: authHeaders(), cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = await resp.json();
      if (!body || body.ok === false) throw new Error(text(body && body.error, "接口返回异常"));
      LIVE.snapshot = body;
      LIVE.error = "";
    } catch (err) {
      LIVE.error = text(err && err.message, "无法读取运行时压力快照");
    } finally {
      render();
    }
  }

  render();
  fetchSnapshot();
  const refreshMs = Math.max(5000, Number(BOARD.refresh_interval_seconds || 15) * 1000);
  window.setInterval(fetchSnapshot, refreshMs);
})();
