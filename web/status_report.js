(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const REPORT = (DATA && DATA.status_report && typeof DATA.status_report === "object") ? DATA.status_report : {};

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

  function text(value, fallback = "") {
    const out = String(value || "").trim();
    return out || fallback;
  }

  function rows(value) {
    return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
  }

  function toneClass(raw) {
    const key = text(raw, "muted").toLowerCase();
    const map = {
      accent: "tone-accent",
      good: "tone-good",
      warn: "tone-warn",
      danger: "tone-danger",
      online: "tone-good",
      offline: "tone-muted",
      degraded: "tone-warn",
      configured: "tone-muted",
      present: "tone-muted",
      frozen: "tone-muted",
      retired: "tone-muted",
      backup: "tone-muted",
      stale: "tone-muted",
      done: "tone-good",
      doing: "tone-doing",
      todo: "tone-muted",
      next: "tone-accent",
      later: "tone-muted",
      high: "tone-danger",
      medium: "tone-warn",
      low: "tone-good"
    };
    return map[key] || "tone-muted";
  }

  function toneLabel(raw) {
    const key = text(raw, "信息").toLowerCase();
    const map = {
      accent: "主线",
      good: "已就绪",
      warn: "需关注",
      danger: "高风险",
      online: "在线",
      offline: "离线",
      degraded: "异常",
      configured: "已配置",
      present: "已存在",
      frozen: "冻结",
      retired: "退役",
      backup: "备份",
      stale: "历史态",
      done: "已完成",
      doing: "进行中",
      todo: "待处理",
      next: "下一步",
      later: "后续",
      high: "高风险",
      medium: "中风险",
      low: "低风险"
    };
    return map[key] || text(raw, "信息");
  }

  function setQuickLink(id, key, fallback) {
    const node = document.getElementById(id);
    if (!node) return;
    node.href = text(LINKS[key], fallback);
  }

  function renderHero() {
    const hero = REPORT.hero || {};
    const heroKicker = document.getElementById("heroKicker");
    const heroTitle = document.getElementById("heroTitle");
    const heroSubtitle = document.getElementById("heroSubtitle");
    const generatedAtChip = document.getElementById("generatedAtChip");
    const sourceFileChip = document.getElementById("sourceFileChip");
    if (heroKicker) heroKicker.textContent = text(hero.kicker, "Project Status Brief");
    if (heroTitle) heroTitle.textContent = text(hero.headline, text(REPORT.title, "项目情况汇报"));
    if (heroSubtitle) heroSubtitle.textContent = text(hero.summary || REPORT.subtitle, "—");
    if (generatedAtChip) generatedAtChip.textContent = "生成时间 · " + text(DATA.generated_at, "—");
    if (sourceFileChip) sourceFileChip.textContent = "数据源 · " + text(REPORT.source_file, "—");
  }

  function renderSummaryCards() {
    const wrap = document.getElementById("summaryGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const cards = rows(REPORT.summary_cards);
    if (!cards.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前还没有汇报摘要卡片。" }));
      return;
    }
    cards.forEach((item) => {
      wrap.appendChild(el("article", { class: "card " + toneClass(item.tone) }, [
        el("div", { class: "summary-label", text: text(item.label, "摘要") }),
        el("div", { class: "summary-value", text: text(item.value, "-") }),
        el("p", { class: "mini-note", text: text(item.detail, "") })
      ]));
    });
  }

  function renderRepoSnapshot() {
    const wrap = document.getElementById("repoSnapshot");
    if (!wrap) return;
    wrap.innerHTML = "";
    const repo = REPORT.repo_snapshot || {};
    const rowsOut = [
      ["仓库根", text(repo.repo_root, "-")],
      ["当前分支", text(repo.branch, "-")],
      ["当前 HEAD", text(repo.head, "-")],
      ["origin", text(repo.remote_origin, "-")],
      ["未提交改动数", String(Number(repo.dirty_count || 0))]
    ];
    rowsOut.forEach(([label, value]) => {
      wrap.appendChild(el("div", { class: "kv-item" }, [
        el("div", { class: "mini-label", text: label }),
        el("div", { class: "kv-value", text: value })
      ]));
    });
    const dirtyPreview = Array.isArray(repo.dirty_preview) ? repo.dirty_preview : [];
    if (dirtyPreview.length) {
      wrap.appendChild(el("div", { class: "kv-item" }, [
        el("div", { class: "mini-label", text: "改动预览" }),
        el("div", { class: "kv-value", text: dirtyPreview.join("\n") })
      ]));
    }
  }

  function renderUpdateRules() {
    const wrap = document.getElementById("updateRules");
    const rebuild = document.getElementById("rebuildCommand");
    if (rebuild) rebuild.textContent = text(REPORT.rebuild_command, "-");
    if (!wrap) return;
    wrap.innerHTML = "";
    const rules = Array.isArray(REPORT.update_rules) ? REPORT.update_rules : [];
    if (!rules.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有配置更新规则。" }));
      return;
    }
    rules.forEach((item, index) => {
      wrap.appendChild(el("div", { class: "rule-item" }, [
        el("span", { class: "rule-index", text: String(index + 1) }),
        el("div", { class: "mini-note", text: text(item, "-") })
      ]));
    });
  }

  function renderEnvironmentMatrix() {
    const wrap = document.getElementById("environmentGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const items = rows(REPORT.environment_matrix);
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有环境矩阵数据。" }));
      return;
    }
    items.forEach((item) => {
      wrap.appendChild(el("article", { class: "card env-card" }, [
        el("div", { class: "env-head" }, [
          el("div", {}, [
            el("div", { class: "env-title", text: text(item.label, "环境") })
          ]),
          el("span", { class: "tone-chip " + toneClass(item.status), text: toneLabel(item.status) })
        ]),
        el("div", { class: "env-meta-grid" }, [
          metaBlock("仓库", item.repo),
          metaBlock("分支", item.branch),
          metaBlock("Runtime", item.runtime),
          metaBlock("端口", item.port)
        ]),
        el("p", { class: "env-note", text: text(item.note, "") })
      ]));
    });
  }

  function metaBlock(label, value) {
    return el("div", { class: "env-meta" }, [
      el("div", { class: "env-meta-label", text: text(label, "-") }),
      el("div", { class: "env-meta-value", text: text(value, "-") })
    ]);
  }

  function renderWorkstreams() {
    const wrap = document.getElementById("workstreamGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const items = rows(REPORT.workstreams);
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有工作流数据。" }));
      return;
    }
    items.forEach((item) => {
      const bullets = Array.isArray(item.bullets) ? item.bullets : [];
      wrap.appendChild(el("article", { class: "card" }, [
        el("div", { class: "stack-head" }, [
          el("div", { class: "stack-title", text: text(item.title, "工作流") }),
          el("span", { class: "tone-chip " + toneClass(item.status), text: toneLabel(item.status) })
        ]),
        el("p", { class: "mini-note", text: text(item.summary, "") }),
        bullets.length
          ? el("ul", { class: "workstream-bullets" }, bullets.map((bullet) => el("li", { text: text(bullet, "") })))
          : el("div")
      ]));
    });
  }

  function renderStackList(targetId, items, noteBuilder) {
    const wrap = document.getElementById(targetId);
    if (!wrap) return;
    wrap.innerHTML = "";
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有内容。" }));
      return;
    }
    items.forEach((item) => {
      wrap.appendChild(el("article", { class: "stack-item" }, [
        el("div", { class: "stack-head" }, [
          el("div", { class: "stack-title", text: text(item.title, "条目") }),
          el("span", { class: "tone-chip " + toneClass(item.level || item.status), text: toneLabel(item.level || item.status) })
        ]),
        el("p", { class: "mini-note", text: noteBuilder(item) })
      ]));
    });
  }

  function renderMilestones() {
    const wrap = document.getElementById("milestoneList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const items = rows(REPORT.milestones);
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有里程碑数据。" }));
      return;
    }
    items.forEach((item) => {
      wrap.appendChild(el("article", { class: "timeline-item" }, [
        el("span", { class: "timeline-date", text: text(item.date, "-") }),
        el("div", { class: "timeline-head" }, [
          el("div", { class: "timeline-title", text: text(item.title, "里程碑") }),
          el("span", { class: "tone-chip " + toneClass(item.status), text: toneLabel(item.status) })
        ]),
        el("p", { class: "timeline-detail", text: text(item.detail, "") })
      ]));
    });
  }

  function renderUpdates() {
    const wrap = document.getElementById("updateList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const items = rows(REPORT.updates);
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有最近更新。" }));
      return;
    }
    items.forEach((item) => {
      wrap.appendChild(el("article", { class: "timeline-item" }, [
        el("span", { class: "timeline-date", text: text(item.date, "-") }),
        el("div", { class: "timeline-head" }, [
          el("div", { class: "timeline-title", text: text(item.title, "更新") }),
          el("span", { class: "tone-chip " + toneClass(item.status), text: toneLabel(item.status) })
        ]),
        el("p", { class: "timeline-detail", text: text(item.summary, "") })
      ]));
    });
  }

  function renderReferences() {
    const wrap = document.getElementById("referenceList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const items = rows(REPORT.references);
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有参考资料。" }));
      return;
    }
    items.forEach((item) => {
      wrap.appendChild(el("article", { class: "reference-item" }, [
        el("div", { class: "reference-head" }, [
          el("div", { class: "reference-title", text: text(item.label, "资料") })
        ]),
        el("div", { class: "reference-path", text: text(item.path, "-") }),
        el("p", { class: "reference-note", text: text(item.note, "") })
      ]));
    });
  }

  function initQuickLinks() {
    setQuickLink("overviewLink", "overview_page", "/share/project-overview-dashboard.html");
    setQuickLink("taskLink", "task_page", "/share/project-task-dashboard.html");
    setQuickLink("communicationLink", "communication_page", "/share/project-communication-audit.html");
    setQuickLink("sessionHealthLink", "session_health_page", "/share/project-session-health-dashboard.html");
  }

  renderHero();
  initQuickLinks();
  renderSummaryCards();
  renderRepoSnapshot();
  renderUpdateRules();
  renderEnvironmentMatrix();
  renderWorkstreams();
  renderStackList("riskList", rows(REPORT.risks), (item) => {
    const parts = [text(item.impact, ""), text(item.action, "")].filter(Boolean);
    return parts.join(" 应对：");
  });
  renderStackList("nextActionList", rows(REPORT.next_actions), (item) => {
    const owner = text(item.owner, "");
    return owner ? "Owner: " + owner : "待补充负责人";
  });
  renderMilestones();
  renderUpdates();
  renderReferences();
})();
