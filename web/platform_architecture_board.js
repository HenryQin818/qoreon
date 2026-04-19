(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const BOARD = (DATA && DATA.platform_architecture_board && typeof DATA.platform_architecture_board === "object")
    ? DATA.platform_architecture_board
    : {};

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

  function texts(value) {
    return Array.isArray(value) ? value.map((item) => text(item)).filter(Boolean) : [];
  }

  function toneKey(raw) {
    const value = text(raw).toLowerCase();
    const map = {
      accent: "accent",
      good: "good",
      warn: "warn",
      danger: "danger",
      "目标态": "accent",
      "原型态": "warn",
      "已实现": "good"
    };
    return map[value] || "accent";
  }

  function toneClass(raw) {
    return "tone-" + toneKey(raw);
  }

  function statusTone(raw) {
    const value = text(raw).toLowerCase();
    const map = {
      done: "good",
      completed: "good",
      todo: "warn",
      open: "warn",
      tracking: "accent",
      doing: "accent",
      "已完成": "good",
      "进行中": "accent",
      "待开始": "warn",
      "待办": "warn"
    };
    return map[value] || "accent";
  }

  function setQuickLink(id, key, fallback) {
    const node = document.getElementById(id);
    if (!node) return;
    node.href = text(LINKS[key], fallback);
  }

  function renderHero() {
    const hero = (BOARD.hero && typeof BOARD.hero === "object") ? BOARD.hero : {};
    const deliveryStateChip = document.getElementById("deliveryStateChip");
    const generatedAtChip = document.getElementById("generatedAtChip");
    const sourceFileChip = document.getElementById("sourceFileChip");

    const kickerNode = document.getElementById("heroKicker");
    const titleNode = document.getElementById("heroTitle");
    const subtitleNode = document.getElementById("heroSubtitle");
    document.title = text(BOARD.title, "Qoreon 平台业务架构画板");

    if (kickerNode) kickerNode.textContent = text(hero.kicker, "Platform Vision Board");
    if (titleNode) titleNode.textContent = text(hero.headline, text(BOARD.title, "Qoreon 平台业务架构画板"));
    if (subtitleNode) subtitleNode.textContent = text(hero.summary || BOARD.subtitle, "—");

    if (deliveryStateChip) {
      const state = text(BOARD.delivery_state, "目标态");
      deliveryStateChip.textContent = state;
      deliveryStateChip.className = "hero-chip hero-chip-strong " + toneClass(state);
    }
    if (generatedAtChip) generatedAtChip.textContent = "生成时间 · " + text(DATA.generated_at, "—");
    if (sourceFileChip) {
      const sourceError = text(BOARD.source_error);
      sourceFileChip.textContent = sourceError
        ? "数据源异常 · " + sourceError
        : "数据源 · " + text(BOARD.source_file, "—");
    }
  }

  function renderSummaryCards() {
    const wrap = document.getElementById("summaryGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const cards = rows(BOARD.summary_cards);
    if (!cards.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前还没有摘要卡片。" }));
      return;
    }
    cards.forEach((item) => {
      wrap.appendChild(el("article", { class: "summary-card " + toneClass(item.tone) }, [
        el("div", { class: "summary-label", text: text(item.label, "摘要") }),
        el("div", { class: "summary-value", text: text(item.value, "-") }),
        el("p", { class: "summary-note", text: text(item.detail, "") })
      ]));
    });
  }

  function renderGoalPoints() {
    const wrap = document.getElementById("goalPointList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const items = texts(BOARD.goal_points);
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前还没有业务目标。" }));
      return;
    }
    items.forEach((item, index) => {
      wrap.appendChild(el("article", { class: "goal-item" }, [
        el("span", { class: "goal-index", text: String(index + 1).padStart(2, "0") }),
        el("div", { class: "goal-text", text: item })
      ]));
    });
  }

  function renderScopeCards() {
    const wrap = document.getElementById("scopeGrid");
    if (!wrap) return;
    wrap.innerHTML = "";
    const cards = rows(BOARD.scope_cards);
    if (!cards.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前还没有范围边界定义。" }));
      return;
    }
    cards.forEach((item) => {
      wrap.appendChild(el("article", { class: "scope-card " + toneClass(item.tone) }, [
        el("h3", { text: text(item.title, "范围") }),
        el("ul", { class: "scope-list" }, texts(item.bullets).map((bullet) =>
          el("li", { text: bullet })
        ))
      ]));
    });
  }

  function renderPositioning() {
    const positioningText = document.getElementById("positioningText");
    const freezeNoteText = document.getElementById("freezeNoteText");
    if (positioningText) positioningText.textContent = text(BOARD.positioning, "—");
    if (freezeNoteText) freezeNoteText.textContent = text(BOARD.freeze_note, "—");
  }

  function renderDrawerStage() {
    const drawerStack = document.getElementById("drawerStack");
    const railGrid = document.getElementById("railGrid");
    if (drawerStack) drawerStack.innerHTML = "";
    if (railGrid) railGrid.innerHTML = "";

    const layers = rows(BOARD.drawer_layers);
    if (drawerStack) {
      if (!layers.length) {
        drawerStack.appendChild(el("div", { class: "empty-state", text: "当前还没有平台层级数据。" }));
      } else {
        layers.forEach((layer, index) => {
          const compartments = rows(layer.compartments);
          const highlights = texts(layer.highlights);
          const layerClasses = [
            "drawer-layer",
            toneClass(layer.tone),
            index === 1 ? "drawer-layer-central" : ""
          ].filter(Boolean).join(" ");
          drawerStack.appendChild(el("article", { class: layerClasses }, [
            el("div", { class: "drawer-handle", "aria-hidden": "true" }),
            el("div", { class: "drawer-kicker", text: text(layer.label, "层级") }),
            el("h3", { class: "drawer-headline", text: text(layer.headline, "平台层级") }),
            el("p", { class: "drawer-summary", text: text(layer.summary, "") }),
            highlights.length
              ? el("div", { class: "highlight-strip" }, highlights.map((item) =>
                el("span", { class: "tone-chip " + toneClass(layer.tone), text: item })
              ))
              : el("div"),
            compartments.length
              ? el("div", { class: "compartment-grid" }, compartments.map((item) =>
                el("article", { class: "compartment-card" }, [
                  el("h3", { text: text(item.title, "板块") }),
                  el("ul", { class: "compartment-list" }, texts(item.bullets).map((bullet) =>
                    el("li", { text: bullet })
                  ))
                ])
              ))
              : el("div")
          ]));
          if (index < layers.length - 1) {
            drawerStack.appendChild(el("div", { class: "drawer-connector", "aria-hidden": "true" }));
          }
        });
      }
    }

    if (railGrid) {
      const rails = rows(BOARD.cross_layer_rails);
      if (!rails.length) {
        railGrid.appendChild(el("div", { class: "empty-state", text: "当前还没有跨层治理数据。" }));
      } else {
        rails.forEach((item) => {
          railGrid.appendChild(el("article", { class: "rail-card " + toneClass(item.tone) }, [
            el("div", { class: "rail-label", text: text(item.label, "治理项") }),
            el("p", { class: "rail-detail", text: text(item.detail, "") })
          ]));
        });
      }
    }
  }

  function renderFlow() {
    const wrap = document.getElementById("flowLane");
    if (!wrap) return;
    wrap.innerHTML = "";
    const steps = rows(BOARD.flow_steps);
    if (!steps.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前还没有平台流转步骤。" }));
      return;
    }
    steps.forEach((item) => {
      wrap.appendChild(el("article", { class: "flow-card " + toneClass(item.tone) }, [
        el("div", { class: "flow-step-no", text: text(item.step, "00") }),
        el("div", { class: "flow-title", text: text(item.title, "步骤") }),
        el("p", { class: "flow-detail", text: text(item.detail, "") })
      ]));
    });
  }

  function renderMiniCards(targetId, items, emptyText) {
    const wrap = document.getElementById(targetId);
    if (!wrap) return;
    wrap.innerHTML = "";
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: emptyText }));
      return;
    }
    items.forEach((item) => {
      wrap.appendChild(el("article", { class: "mini-card " + toneClass(item.tone) }, [
        el("h3", { text: text(item.title, "条目") }),
        el("p", { text: text(item.summary || item.detail, "") })
      ]));
    });
  }

  function renderTracker() {
    const tracker = (BOARD.tracker && typeof BOARD.tracker === "object") ? BOARD.tracker : {};
    const trackerMeta = document.getElementById("trackerMeta");
    const milestoneLane = document.getElementById("milestoneLane");
    const trackerConclusion = document.getElementById("trackerConclusion");
    const trackerNextAction = document.getElementById("trackerNextAction");

    if (trackerConclusion) trackerConclusion.textContent = text(tracker.current_conclusion, "—");
    if (trackerNextAction) trackerNextAction.textContent = text(tracker.next_action, "—");

    if (trackerMeta) {
      trackerMeta.innerHTML = "";
      const chips = [
        { label: "当前阶段", value: text(tracker.stage) },
        { label: "完成度", value: text(tracker.progress) },
        { label: "下一里程碑", value: text(tracker.next_milestone) }
      ].filter((item) => item.value);
      if (!chips.length) {
        trackerMeta.appendChild(el("div", { class: "empty-state", text: "当前还没有推进信息。" }));
      } else {
        chips.forEach((item) => {
          trackerMeta.appendChild(el("article", { class: "tracker-chip" }, [
            el("div", { class: "tracker-chip-label", text: item.label }),
            el("div", { class: "tracker-chip-value", text: item.value })
          ]));
        });
      }
    }

    if (milestoneLane) {
      milestoneLane.innerHTML = "";
      const milestones = rows(BOARD.milestones);
      if (!milestones.length) {
        milestoneLane.appendChild(el("div", { class: "empty-state", text: "当前还没有里程碑。" }));
      } else {
        milestones.forEach((item) => {
          const status = text(item.status, "Tracking");
          milestoneLane.appendChild(el("article", { class: "milestone-card" }, [
            el("div", { class: "milestone-meta" }, [
              el("span", { class: "milestone-date", text: text(item.date, "—") }),
              el("span", { class: "milestone-status tone-chip " + toneClass(statusTone(status)), text: status })
            ]),
            el("h3", { class: "milestone-title", text: text(item.title, "里程碑") }),
            el("p", { class: "milestone-owner", text: text(item.owner, "") })
          ]));
        });
      }
    }
  }

  function renderTalkTrack() {
    const wrap = document.getElementById("talkTrackList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const tracks = texts(BOARD.talk_track);
    if (!tracks.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前还没有口播内容。" }));
      return;
    }
    tracks.forEach((item) => {
      wrap.appendChild(el("p", { class: "talk-track-line", text: item }));
    });
  }

  function renderRules() {
    const wrap = document.getElementById("alignmentRuleList");
    const rebuildCommand = document.getElementById("rebuildCommand");
    if (rebuildCommand) rebuildCommand.textContent = text(BOARD.rebuild_command, "-");
    if (!wrap) return;
    wrap.innerHTML = "";
    const rules = texts(BOARD.alignment_rules);
    if (!rules.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前还没有统一口径。" }));
      return;
    }
    rules.forEach((item, index) => {
      wrap.appendChild(el("article", { class: "rule-item" }, [
        el("span", { class: "rule-index", text: String(index + 1) }),
        el("div", { class: "rule-text", text: item })
      ]));
    });
  }

  function renderReferences() {
    const wrap = document.getElementById("referenceList");
    if (!wrap) return;
    wrap.innerHTML = "";
    const items = rows(BOARD.references);
    if (!items.length) {
      wrap.appendChild(el("div", { class: "empty-state", text: "当前没有参考资料。" }));
      return;
    }
    items.forEach((item) => {
      wrap.appendChild(el("article", { class: "reference-item" }, [
        el("div", { class: "reference-title", text: text(item.label, "资料") }),
        el("div", { class: "reference-path", text: text(item.path, "-") }),
        el("p", { class: "reference-note", text: text(item.note, "") })
      ]));
    });
  }

  function bindQuickLinks() {
    setQuickLink("overviewLink", "overview_page", "/share/project-overview-dashboard.html");
    setQuickLink("taskLink", "task_page", "/share/project-task-dashboard.html");
    setQuickLink("statusReportLink", "status_report_page", "/share/project-status-report.html");
    setQuickLink("openSourceSyncLink", "open_source_sync_page", "/share/project-open-source-sync-board.html");
    setQuickLink("communicationLink", "communication_page", "/share/project-communication-audit.html");
    setQuickLink("sessionHealthLink", "session_health_page", "/share/project-session-health-dashboard.html");
  }

  function boot() {
    bindQuickLinks();
    renderHero();
    renderSummaryCards();
    renderPositioning();
    renderGoalPoints();
    renderScopeCards();
    renderDrawerStage();
    renderFlow();
    renderMiniCards("scenarioGrid", rows(BOARD.scenario_cards), "当前还没有业务形态定义。");
    renderMiniCards("boundaryGrid", rows(BOARD.boundary_cards), "当前还没有边界定义。");
    renderTracker();
    renderTalkTrack();
    renderRules();
    renderReferences();
  }

  boot();
})();
