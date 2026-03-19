(function () {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const TASK_PAGE = (DATA.links && DATA.links.task_page) ? String(DATA.links.task_page) : "project-task-dashboard.html";
  const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
  const COPY_LABEL = Object.create(null);
  const COPY_TIMER = Object.create(null);

  const STATE = {
    projectId: "",
    query: "",
  };

  function text(v) {
    return String(v == null ? "" : v).trim();
  }

  function formatZhDateTime(raw) {
    const value = text(raw);
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const pad = (num) => String(num).padStart(2, "0");
    return [
      date.getFullYear() + "年",
      pad(date.getMonth() + 1) + "月",
      pad(date.getDate()) + "日 ",
      pad(date.getHours()) + ":" + pad(date.getMinutes()),
    ].join("");
  }

  function el(tag, opts = {}, children = []) {
    const node = document.createElement(tag);
    if (opts.class) node.className = opts.class;
    if (opts.text != null) node.textContent = opts.text;
    if (opts.html != null) node.innerHTML = opts.html;
    if (opts.href) node.href = opts.href;
    if (opts.type) node.type = opts.type;
    if (opts.placeholder) node.placeholder = opts.placeholder;
    if (opts.title) node.title = opts.title;
    if (opts.dataset) {
      Object.entries(opts.dataset).forEach(([k, v]) => {
        if (v != null) node.dataset[k] = String(v);
      });
    }
    children.forEach((child) => {
      if (!child) return;
      node.appendChild(child);
    });
    return node;
  }

  function parseHash() {
    const hash = String(window.location.hash || "").replace(/^#/, "");
    const params = new URLSearchParams(hash);
    return {
      projectId: text(params.get("p")),
    };
  }

  function primaryProjectId() {
    const fromHash = parseHash().projectId;
    if (fromHash && projects.some((p) => text(p.id) === fromHash)) return fromHash;
    return text(projects[0] && projects[0].id);
  }

  function getProject(projectId) {
    return projects.find((item) => text(item.id) === text(projectId)) || null;
  }

  function safeContext(raw) {
    const row = raw && typeof raw === "object" ? raw : {};
    return {
      project_id: text(row.project_id),
      channel_name: text(row.channel_name),
      session_id: text(row.session_id),
      environment: text(row.environment),
      worktree_root: text(row.worktree_root),
      workdir: text(row.workdir),
      branch: text(row.branch),
    };
  }

  function safeExecutionContext(raw) {
    const row = raw && typeof raw === "object" ? raw : {};
    const override = row.override && typeof row.override === "object" ? row.override : {};
    return {
      target: safeContext(row.target),
      source: safeContext(row.source),
      context_source: text(row.context_source),
      override: {
        applied: !!override.applied,
        fields: Array.isArray(override.fields) ? override.fields.map((item) => text(item)).filter(Boolean) : [],
        source: text(override.source),
      },
    };
  }

  function badge(nodeClass, label) {
    return el("span", { class: nodeClass, text: label });
  }

  function shortSessionId(value) {
    const sid = text(value);
    if (!sid) return "-";
    if (sid.length <= 16) return sid;
    return sid.slice(0, 8) + "…" + sid.slice(-4);
  }

  function sanitizeMentionLabelSegment(raw) {
    return text(raw).replace(/[^\u4e00-\u9fa5A-Za-z0-9._-]+/g, "");
  }

  function mentionBaseLabel(agent, channel) {
    const display = text(agent && (agent.name || agent.display_name));
    const channelName = text(channel && channel.channel_name);
    if (display && !/\s/.test(display)) return display;
    if (channelName && !/\s/.test(channelName)) return channelName;
    return (display || channelName || "协同对象").replace(/\s+/g, "");
  }

  function buildContactLabel(project, channel, agent) {
    const projectPart = sanitizeMentionLabelSegment(firstProjectText(project));
    const agentPart = sanitizeMentionLabelSegment(mentionBaseLabel(agent, channel));
    if (projectPart && agentPart) return projectPart + "/" + agentPart;
    return agentPart || projectPart || "协同对象";
  }

  function buildContactCopyText(project, channel, agent) {
    return "[协同对象: " + buildContactLabel(project, channel, agent) + "]";
  }

  function collabIdentityLabel(agent) {
    return agent && agent.is_primary ? "主协作" : "协作";
  }

  async function copyTextToClipboard(content) {
    const value = text(content);
    if (!value) return false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(value);
        return true;
      } catch (_) {}
    }
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "readonly");
    area.style.position = "fixed";
    area.style.opacity = "0";
    area.style.pointerEvents = "none";
    document.body.appendChild(area);
    area.focus();
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
    document.body.removeChild(area);
    return ok;
  }

  function setCopyState(key, label) {
    if (!key) return;
    if (label) COPY_LABEL[key] = label;
    else delete COPY_LABEL[key];
    if (COPY_TIMER[key]) clearTimeout(COPY_TIMER[key]);
    if (label) {
      COPY_TIMER[key] = window.setTimeout(() => {
        delete COPY_LABEL[key];
        delete COPY_TIMER[key];
        render();
      }, 1500);
    }
  }

  function firstProjectText(project) {
    return text(project && (project.id || (project.project && project.project.project_id) || project.name || (project.project && project.project.project_name)));
  }

  function buildProjectContext(project) {
    const context = safeExecutionContext(project && project.project_execution_context);
    const target = context.target;
    return {
      environment: target.environment || "stable",
      worktree_root: target.worktree_root || "",
      workdir: target.workdir || target.worktree_root || "",
      branch: target.branch || "",
      context_source: context.context_source || "project",
    };
  }

  function buildSessionMaps(project) {
    const rows = Array.isArray(project && project.channel_sessions) ? project.channel_sessions : [];
    const byChannel = new Map();
    const bySessionId = new Map();
    rows.forEach((row) => {
      const normalized = row && typeof row === "object" ? row : {};
      const channelName = text(normalized.name || normalized.channel_name);
      if (!channelName) return;
      if (!byChannel.has(channelName)) byChannel.set(channelName, []);
      byChannel.get(channelName).push(normalized);
      const sessionId = text(normalized.session_id);
      if (sessionId) bySessionId.set(sessionId, normalized);
    });
    return { byChannel, bySessionId };
  }

  function buildAgentRecord(project, channel, agent, sessionRow, projectContext) {
    const rawAgent = agent && typeof agent === "object" ? agent : {};
    const rawSession = sessionRow && typeof sessionRow === "object" ? sessionRow : {};
    const executionContext = safeExecutionContext(rawSession.project_execution_context);
    const target = executionContext.target.environment || executionContext.target.worktree_root
      ? executionContext.target
      : safeContext({
          project_id: text(project && project.id),
          channel_name: text(channel && channel.channel_name),
          session_id: text(rawSession.session_id || rawAgent.session_id),
          environment: rawSession.environment || rawAgent.environment || projectContext.environment,
          worktree_root: rawSession.worktree_root || projectContext.worktree_root,
          workdir: rawSession.workdir || rawAgent.workdir || projectContext.workdir,
          branch: rawSession.branch || rawAgent.branch || projectContext.branch,
        });
    const source = executionContext.source.environment || executionContext.source.worktree_root
      ? executionContext.source
      : safeContext({
          project_id: text(project && project.id),
          channel_name: text(channel && channel.channel_name),
          environment: projectContext.environment,
          worktree_root: projectContext.worktree_root,
          workdir: projectContext.workdir,
          branch: projectContext.branch,
        });
    const bindingState = (() => {
      const raw = text(rawSession.context_binding_state).toLowerCase();
      if (raw) return raw;
      if (executionContext.override.applied) return "override";
      if (!text(rawSession.session_id || rawAgent.session_id)) return "unbound";
      return "bound";
    })();
    const effectiveWorkdir = target.workdir || rawSession.workdir || rawAgent.workdir || source.workdir;
    const effectiveWorktree = target.worktree_root || rawSession.worktree_root || source.worktree_root;
    const hasWorkdirDrift = !!(effectiveWorkdir && effectiveWorktree && effectiveWorkdir !== effectiveWorktree);
    const stateKind = (() => {
      if (bindingState === "unbound") return "unbound";
      if (bindingState === "override" || executionContext.override.applied) return "override";
      if (bindingState === "drift" || hasWorkdirDrift) return "drift";
      return "bound";
    })();
    const stateLabel = stateKind === "bound"
      ? "已绑定"
      : (stateKind === "override" ? "特例覆盖" : (stateKind === "drift" ? "上下文漂移" : "未完全绑定"));
    const contextBadges = [];
    if (target.environment || source.environment) {
      contextBadges.push(target.environment || source.environment || "stable");
    }
    if (target.branch || source.branch) {
      contextBadges.push("分支 " + (target.branch || source.branch));
    }
    if ((stateKind === "override" || stateKind === "drift") && executionContext.override.fields.length) {
      contextBadges.push("覆盖 " + executionContext.override.fields.join(" / "));
    }
    return {
      name: text(rawSession.display_name || rawAgent.display_name || rawSession.alias || rawAgent.desc || rawAgent.session_id) || "未命名 Agent",
      role: text(channel && channel.channel_role) || "未补角色",
      cli_type: text(rawSession.cli_type || rawAgent.cli_type || channel.primary_cli_type || "codex"),
      desc: text(rawSession.desc || rawAgent.desc),
      session_id: text(rawSession.session_id || rawAgent.session_id),
      is_primary: !!(rawSession.is_primary || rawAgent.is_primary),
      status: text(rawSession.status || rawAgent.status || "active"),
      session_role: text(rawSession.session_role || rawAgent.session_role || (rawSession.is_primary || rawAgent.is_primary ? "primary" : "child")),
      target,
      source,
      context_source: text(executionContext.context_source || projectContext.context_source || "project"),
      override_fields: executionContext.override.fields,
      state_kind: stateKind,
      state_label: stateLabel,
      context_badges: contextBadges,
      effective_worktree: effectiveWorktree,
      effective_workdir: effectiveWorkdir,
    };
  }

  function normalizeChannels(project) {
    const registry = (project && project.registry && typeof project.registry === "object") ? project.registry : {};
    const registryChannels = Array.isArray(registry.channels) ? registry.channels : [];
    const registryAgents = Array.isArray(registry.all_agents) ? registry.all_agents : [];
    const configChannels = Array.isArray(project && project.channels) ? project.channels : [];
    const projectContext = buildProjectContext(project);
    const sessionMaps = buildSessionMaps(project);
    const channelsByName = new Map();
    registryChannels.forEach((channel) => {
      const name = text(channel.channel_name);
      if (name) channelsByName.set(name, channel);
    });
    configChannels.forEach((channel) => {
      const name = text(channel.name || channel.channel_name);
      if (name && !channelsByName.has(name)) {
        channelsByName.set(name, {
          channel_name: name,
          channel_desc: text(channel.desc || channel.channel_desc),
          channel_role: text(channel.channel_role),
          primary_session_id: "",
          primary_session_alias: "",
          primary_cli_type: "",
          startup_ready: false,
          session_candidates_count: 0,
          session_candidates: [],
        });
      }
    });
    sessionMaps.byChannel.forEach((_rows, channelName) => {
      if (!channelsByName.has(channelName)) {
        channelsByName.set(channelName, {
          channel_name: channelName,
          channel_desc: "",
          channel_role: "",
          primary_session_id: "",
          primary_session_alias: "",
          primary_cli_type: "",
          startup_ready: false,
          session_candidates_count: 0,
          session_candidates: [],
        });
      }
    });

    const registryAgentMap = new Map();
    registryAgents.forEach((agent) => {
      const channelName = text(agent.channel_name);
      if (!channelName) return;
      if (!registryAgentMap.has(channelName)) registryAgentMap.set(channelName, []);
      registryAgentMap.get(channelName).push(agent);
    });

    return Array.from(channelsByName.values()).map((channel) => {
      const channelName = text(channel.channel_name || channel.name);
      const sessionRows = sessionMaps.byChannel.get(channelName) || [];
      const channelAgents = registryAgentMap.get(channelName) || [];
      const sessionCandidateRows = channelAgents.length
        ? channelAgents
        : (sessionRows.length ? sessionRows : (Array.isArray(channel.session_candidates) ? channel.session_candidates : []));
      const agents = sessionCandidateRows.map((agent) => {
        const sessionId = text(agent.session_id);
        const sessionRow = sessionId && sessionMaps.bySessionId.has(sessionId)
          ? sessionMaps.bySessionId.get(sessionId)
          : sessionRows.find((row) => text(row.session_id) === sessionId) || null;
        return buildAgentRecord(project, channel, agent, sessionRow, projectContext);
      });
      agents.sort((a, b) => Number(!!b.is_primary) - Number(!!a.is_primary));
      return {
        channel_name: channelName,
        channel_desc: text(channel.channel_desc || channel.desc),
        channel_role: text(channel.channel_role),
        primary_session_id: text(channel.primary_session_id),
        primary_session_alias: text(channel.primary_session_alias),
        primary_cli_type: text(channel.primary_cli_type),
        startup_ready: !!channel.startup_ready,
        session_candidates_count: Number(channel.session_candidates_count || agents.length || 0),
        agents,
      };
    });
  }

  function filterChannels(channels, query) {
    const q = text(query).toLowerCase();
    if (!q) return channels;
    return channels
      .map((channel) => {
        const selfMatched = [
          channel.channel_name,
          channel.channel_desc,
          channel.channel_role,
          channel.primary_session_alias,
        ].some((value) => text(value).toLowerCase().includes(q));
        const agents = channel.agents.filter((agent) => [
          agent.name,
          agent.desc,
          agent.session_id,
          agent.cli_type,
          agent.state_label,
          agent.target.environment,
          agent.target.branch,
          agent.effective_worktree,
        ].some((value) => text(value).toLowerCase().includes(q)));
        if (selfMatched) return channel;
        if (!agents.length) return null;
        return { ...channel, agents };
      })
      .filter(Boolean);
  }

  function updateHeader(project, channels) {
    const title = document.getElementById("pageTitle");
    const subtitle = document.getElementById("pageSubtitle");
    const back = document.getElementById("backToTaskPage");
    const projectName = text(project && project.name) || firstProjectText(project) || "项目通讯录";
    if (title) title.textContent = projectName + " · 通讯录";
    const generatedAt = text(project && project.registry && project.registry.generated_at) || text(DATA.generated_at);
    if (subtitle) {
      subtitle.textContent = generatedAt
        ? `当前项目 ${projectName}，默认只展示项目 / 通道 / Agent / 主协作身份；联系方式可直接复制到输入框使用。最近同步：${formatZhDateTime(generatedAt)}`
        : `当前项目 ${projectName}，默认只展示项目 / 通道 / Agent / 主协作身份；联系方式可直接复制到输入框使用。`;
    }
    if (back && project) back.href = String(TASK_PAGE || "project-task-dashboard.html") + "#p=" + encodeURIComponent(text(project.id));
    document.title = projectName + " · 通讯录";
  }

  function renderProjectList() {
    const list = document.getElementById("projectList");
    if (!list) return;
    list.innerHTML = "";
    projects.forEach((project) => {
      const channels = normalizeChannels(project);
      const agents = channels.reduce((sum, item) => sum + item.agents.length, 0);
      const item = el("button", {
        class: "project-item" + (text(project.id) === text(STATE.projectId) ? " active" : ""),
        type: "button",
        dataset: { projectId: text(project.id) },
      }, [
        el("div", { class: "project-item-title", text: text(project.name) || firstProjectText(project) }),
        el("div", { class: "project-item-meta", text: `项目ID ${firstProjectText(project)} · 通道 ${channels.length} · Agent ${agents}` }),
      ]);
      item.addEventListener("click", () => {
        STATE.projectId = text(project.id);
        syncHash();
        render();
      });
      list.appendChild(item);
    });
  }

  function renderSummary(project, channels) {
    const bar = document.getElementById("summaryBar");
    if (!bar) return;
    const totalAgents = channels.reduce((sum, item) => sum + item.agents.length, 0);
    const primaryAgents = channels.reduce((sum, item) => {
      return sum + item.agents.filter((agent) => agent && agent.is_primary).length;
    }, 0);
    const cards = [
      ["当前项目", text(project && project.name) || firstProjectText(project) || "-"],
      ["通道数", String(channels.length)],
      ["Agent 数", String(totalAgents)],
      ["主协作数", String(primaryAgents)],
    ];
    bar.innerHTML = "";
    cards.forEach(([label, value]) => {
      const valueClass = label === "当前项目" ? "summary-value is-project" : "summary-value";
      bar.appendChild(el("div", { class: "summary-card" }, [
        el("div", { class: "summary-label", text: label }),
        el("div", { class: valueClass, text: value }),
      ]));
    });
  }

  function renderChannels(project, channels) {
    const grid = document.getElementById("channelGrid");
    const empty = document.getElementById("emptyState");
    if (!grid || !empty) return;
    grid.innerHTML = "";
    if (!project || !channels.length) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    const projectName = text(project && project.name) || firstProjectText(project) || "-";
    channels.forEach((channel) => {
      const card = el("article", { class: "channel-card" });
      const head = el("div", { class: "channel-head" }, [
        el("div", {}, [
          el("h2", { class: "channel-title", text: channel.channel_name }),
        ]),
        el("div", { class: "channel-count", text: `${channel.agents.length} 个 Agent` }),
      ]);
      const agentList = el("div", { class: "agent-list" });
      channel.agents.forEach((agent) => {
        const copyKey = text(agent.session_id) || `${firstProjectText(project)}-${channel.channel_name}-${agent.name}`;
        const copyLabel = COPY_LABEL[copyKey] || "复制联系方式";
        const contactText = buildContactCopyText(project, channel, agent);
        const copyBtn = el("button", {
          class: `contact-btn${copyLabel === "已复制" ? " copied" : ""}`,
          type: "button",
          text: copyLabel,
          title: `复制后可直接粘贴到输入框：${contactText}`,
        });
        copyBtn.addEventListener("click", async () => {
          const ok = await copyTextToClipboard(contactText);
          setCopyState(copyKey, ok ? "已复制" : "复制失败");
          render();
        });
        const agentCard = el("div", { class: "agent-card" + (agent.is_primary ? " primary" : "") }, [
          el("div", { class: "agent-main" }, [
            el("div", { class: "agent-name-row" }, [
              el("div", { class: "agent-name", text: agent.name }),
              badge("badge role" + (agent.is_primary ? " primary" : " secondary"), collabIdentityLabel(agent)),
            ]),
            el("div", { class: "agent-field-list" }, [
              el("div", { class: "agent-field-row" }, [
                el("div", { class: "agent-field-label", text: "项目" }),
                el("div", { class: "agent-field-value", text: projectName }),
              ]),
              el("div", { class: "agent-field-row" }, [
                el("div", { class: "agent-field-label", text: "通道" }),
                el("div", { class: "agent-field-value", text: channel.channel_name }),
              ]),
              el("div", { class: "agent-field-row" }, [
                el("div", { class: "agent-field-label", text: "身份" }),
                el("div", { class: "agent-field-value", text: collabIdentityLabel(agent) }),
              ]),
            ]),
            el("div", { class: "agent-contact-row" }, [
              el("div", { class: "agent-contact-label", text: "联系方式" }),
              el("code", { class: "agent-contact-value", text: contactText, title: contactText }),
            ]),
          ]),
          el("div", { class: "agent-actions" }, [
            copyBtn,
          ]),
        ]);
        agentList.appendChild(agentCard);
      });
      card.appendChild(head);
      card.appendChild(agentList);
      grid.appendChild(card);
    });
  }

  function syncHash() {
    const params = new URLSearchParams();
    if (STATE.projectId) params.set("p", STATE.projectId);
    const next = params.toString();
    history.replaceState(null, "", next ? "#" + next : "#");
  }

  function render() {
    const project = getProject(STATE.projectId);
    const channels = filterChannels(normalizeChannels(project), STATE.query);
    renderProjectList();
    updateHeader(project, channels);
    renderSummary(project, channels);
    renderChannels(project, channels);
  }

  function bindSearch() {
    const input = document.getElementById("searchInput");
    if (!input) return;
    input.addEventListener("input", () => {
      STATE.query = text(input.value);
      render();
    });
  }

  function init() {
    STATE.projectId = primaryProjectId();
    bindSearch();
    render();
  }

  init();
})();
