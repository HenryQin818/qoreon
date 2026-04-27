    const CHANNEL_MANAGE_UI = {
      menuChannelName: "",
      requestOpen: false,
      requestSubmitting: false,
      requestProjectId: "",
      requestChannelName: "",
      requestChannelDesc: "",
      requestRequirement: "",
      requestResult: null,
      confirmOpen: false,
      deleteOpen: false,
      deleteSubmitting: false,
      deleteProjectId: "",
      deleteChannelName: "",
      deleteChannelDesc: "",
      agentCandidates: [],
      agentCandidatesProjectId: "",
      agentLoading: false,
      agentError: "",
      selectedAgentSessionId: "",
      selectedAgent: null,
      initBound: false,
    };

    function channelManageNormalizeText(value) {
      return String(value || "").trim();
    }

    function channelManageCurrentProjectId() {
      return channelManageNormalizeText(STATE && STATE.project);
    }

    function channelManageProjectRow(projectId, channelName) {
      const proj = typeof projectById === "function" ? projectById(projectId) : null;
      if (!proj) return null;
      const fromChannels = (Array.isArray(proj.channels) ? proj.channels : [])
        .find((row) => channelManageNormalizeText(row && row.name) === channelManageNormalizeText(channelName));
      if (fromChannels) return fromChannels;
      return (Array.isArray(proj.channel_sessions) ? proj.channel_sessions : [])
        .find((row) => channelManageNormalizeText(row && row.name) === channelManageNormalizeText(channelName)) || null;
    }

    function channelManageCurrentDesc(projectId, channelName) {
      const row = channelManageProjectRow(projectId, channelName);
      return channelManageNormalizeText(row && row.desc) || "暂未填写通道说明";
    }

    function channelManageResolveMenuLayerRoot(node) {
      if (!node || typeof node.closest !== "function") return null;
      return node.closest(".channel-row, .conv-channel-group");
    }

    function closeChannelManageMenus() {
      CHANNEL_MANAGE_UI.menuChannelName = "";
      const menus = Array.from(document.querySelectorAll(".channel-row-menu"));
      for (const node of menus) node.classList.remove("show");
      const btns = Array.from(document.querySelectorAll(".channel-row-menu-trigger"));
      for (const btn of btns) btn.setAttribute("aria-expanded", "false");
      const layerRoots = Array.from(document.querySelectorAll(".channel-row.menu-open, .conv-channel-group.menu-open"));
      for (const node of layerRoots) node.classList.remove("menu-open");
    }

    function toggleChannelManageMenu(channelName, forceOpen = null) {
      const name = channelManageNormalizeText(channelName);
      if (!name) return;
      const nextOpen = forceOpen == null
        ? CHANNEL_MANAGE_UI.menuChannelName !== name
        : !!forceOpen;
      closeChannelManageMenus();
      if (!nextOpen) return;
      CHANNEL_MANAGE_UI.menuChannelName = name;
      const menu = document.querySelector(`.channel-row-menu[data-channel-name="${CSS.escape(name)}"]`);
      const btn = document.querySelector(`.channel-row-menu-trigger[data-channel-name="${CSS.escape(name)}"]`);
      if (menu) menu.classList.add("show");
      if (btn) btn.setAttribute("aria-expanded", "true");
      const layerRoot = channelManageResolveMenuLayerRoot(menu) || channelManageResolveMenuLayerRoot(btn);
      if (layerRoot) layerRoot.classList.add("menu-open");
    }

    function buildChannelManageMenuItem(title, desc, onClick, danger = false) {
      const btn = el("button", {
        class: "channel-row-menu-item" + (danger ? " danger" : ""),
        type: "button",
      });
      btn.appendChild(el("div", { class: "channel-row-menu-item-title", text: title }));
      btn.appendChild(el("div", { class: "channel-row-menu-item-desc", text: desc }));
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeChannelManageMenus();
        onClick && onClick();
      });
      return btn;
    }

    function buildChannelManageRow(projectId, channelName, mainButton) {
      const row = el("div", {
        class: "channel-row" + (String(STATE.channel || "") === String(channelName || "") ? " active" : ""),
      });
      if (mainButton) mainButton.classList.add("channel-row-main");
      row.appendChild(mainButton);

      const tools = el("div", { class: "channel-row-tools" });
      const menuBtn = el("button", {
        class: "icon-btn channel-row-menu-trigger",
        type: "button",
        text: "⋯",
        "data-channel-name": String(channelName || ""),
        "aria-haspopup": "menu",
        "aria-expanded": "false",
        "aria-label": "通道操作菜单",
      });
      menuBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleChannelManageMenu(channelName);
      });
      const menu = el("div", {
        class: "channel-row-menu",
        "data-channel-name": String(channelName || ""),
        role: "menu",
        "aria-label": "通道操作",
      });
      menu.appendChild(buildChannelManageMenuItem(
        "找 Agent 编辑",
        "把通道说明与边界整理成正式派发消息",
        () => openChannelEditAgentModal(projectId, channelName),
      ));
      menu.appendChild(buildChannelManageMenuItem(
        "删除通道",
        "删除通道目录与配套文件夹，保留运行历史记录",
        () => openChannelDeleteModal(projectId, channelName),
        true,
      ));
      tools.appendChild(menuBtn);
      tools.appendChild(menu);
      row.appendChild(tools);
      return row;
    }

    function channelManageSetError(id, message) {
      const box = document.getElementById(id);
      if (!box) return;
      const text = channelManageNormalizeText(message);
      box.style.display = text ? "" : "none";
      box.textContent = text || "";
    }

    function channelManageSetVisible(id, visible) {
      const node = document.getElementById(id);
      if (node) node.style.display = visible ? "" : "none";
    }

    function channelManageResetRequestResult() {
      CHANNEL_MANAGE_UI.requestResult = null;
      channelManageSetVisible("channelEditAgentResult", false);
      const body = document.getElementById("channelEditAgentResultBody");
      if (body) body.innerHTML = "";
    }

    function channelManageRenderRequestResult(data, extra = {}) {
      const result = (data && typeof data === "object") ? data : {};
      CHANNEL_MANAGE_UI.requestResult = { data: result, extra };
      const section = document.getElementById("channelEditAgentResult");
      const body = document.getElementById("channelEditAgentResultBody");
      if (!section || !body) return;
      body.innerHTML = "";
      const rows = [];
      const targetAlias = channelManageNormalizeText(extra.agentDisplayName || "");
      const runId = channelManageNormalizeText((result.dispatch && result.dispatch.runId) || extra.runId || "");
      const status = channelManageNormalizeText((result.dispatch && result.dispatch.runStatus) || "");
      if (targetAlias) rows.push({ key: "处理 Agent", value: targetAlias });
      if (runId) rows.push({ key: "派发 run", value: runId });
      if (status) rows.push({ key: "状态", value: status });
      if (!rows.length) rows.push({ key: "结果", value: "已发送正式派发消息" });
      for (const row of rows) {
        const kv = el("div", { class: "channel-manage-kv" });
        kv.appendChild(el("span", { class: "k", text: row.key }));
        kv.appendChild(el("div", { class: "v", text: row.value }));
        body.appendChild(kv);
      }
      section.style.display = "";
    }

    function channelManageNotifyRequestSent(agent, data) {
      const result = (data && typeof data === "object") ? data : {};
      const agentName = String(agent && (agent.alias || agent.displayName || agent.channelName || agent.sessionId) || "目标 Agent");
      const targetChannel = String(agent && agent.channelName || "").trim();
      const runId = channelManageNormalizeText(result && result.dispatch && result.dispatch.runId);
      let message = "已给 " + agentName + " 发送正式消息。";
      if (targetChannel) {
        message += " 请到「" + targetChannel + "」查看处理进展。";
      } else {
        message += " 请到对应 Agent 会话查看处理进展。";
      }
      if (runId) message += " run: " + runId;
      if (typeof toast === "function") {
        toast(message, { tone: "success" });
        return;
      }
      if (typeof setHintText === "function") {
        setHintText((STATE && STATE.panelMode) || "channel", message);
        return;
      }
      alert(message);
    }

    function normalizeChannelManageAgentCandidate(raw) {
      if (typeof normalizeNewChannelAgentCandidate === "function") {
        return normalizeNewChannelAgentCandidate(raw);
      }
      const s = (raw && typeof raw === "object") ? raw : {};
      const sessionId = channelManageNormalizeText(s.sessionId || s.session_id || s.id);
      if (!sessionId) return null;
      return {
        sessionId,
        alias: channelManageNormalizeText(s.alias),
        displayName: channelManageNormalizeText(s.alias || s.display_name || s.displayName || s.channel_name || s.channelName || sessionId),
        channelName: channelManageNormalizeText(s.channel_name || s.primaryChannel || s.channelName),
        cliType: channelManageNormalizeText(s.cli_type || s.cliType || "codex") || "codex",
        model: channelManageNormalizeText(s.model),
        isPrimary: !!s.is_primary,
        runtimeState: s.runtime_state || s.runtimeState || null,
        raw: s,
      };
    }

    function scoreChannelManageAgentCandidate(row) {
      if (typeof scoreNewChannelAgentCandidate === "function") {
        return scoreNewChannelAgentCandidate(row);
      }
      const text = [
        row && row.alias,
        row && row.displayName,
        row && row.channelName,
      ].join(" ").toLowerCase();
      let score = 0;
      if (row && row.isPrimary) score += 1000;
      if (text.includes("辅助01")) score += 800;
      return score;
    }

    function pickDefaultChannelManageAgent(list) {
      if (typeof pickDefaultNewChannelAgent === "function") {
        return pickDefaultNewChannelAgent(list);
      }
      return Array.isArray(list) && list.length ? list[0] : null;
    }

    async function loadChannelManageAgentCandidates(force = false) {
      const projectId = channelManageCurrentProjectId();
      if (!projectId || projectId === "overview") {
        CHANNEL_MANAGE_UI.agentCandidates = [];
        CHANNEL_MANAGE_UI.agentCandidatesProjectId = "";
        CHANNEL_MANAGE_UI.selectedAgentSessionId = "";
        CHANNEL_MANAGE_UI.selectedAgent = null;
        CHANNEL_MANAGE_UI.agentLoading = false;
        CHANNEL_MANAGE_UI.agentError = "";
        renderChannelManageAgentPicker();
        return [];
      }
      if (
        !force
        && CHANNEL_MANAGE_UI.agentCandidatesProjectId === projectId
        && Array.isArray(CHANNEL_MANAGE_UI.agentCandidates)
        && CHANNEL_MANAGE_UI.agentCandidates.length
      ) {
        return CHANNEL_MANAGE_UI.agentCandidates.slice();
      }

      CHANNEL_MANAGE_UI.agentLoading = true;
      CHANNEL_MANAGE_UI.agentError = "";
      renderChannelManageAgentPicker();

      const fetched = typeof fetchProjectAgentTargetRows === "function"
        ? await fetchProjectAgentTargetRows(projectId, force)
        : { rows: [], error: "加载 Agent 候选失败", source: "" };
      CHANNEL_MANAGE_UI.agentError = String((fetched && fetched.error) || "");
      const list = [];
      const seen = new Set();
      for (const raw of (Array.isArray(fetched.rows) ? fetched.rows : [])) {
        const item = normalizeChannelManageAgentCandidate(raw);
        if (!item || seen.has(item.sessionId)) continue;
        seen.add(item.sessionId);
        list.push(item);
      }
      list.sort((a, b) => {
        const sa = scoreChannelManageAgentCandidate(a);
        const sb = scoreChannelManageAgentCandidate(b);
        if (sa !== sb) return sb - sa;
        return String(a.alias || a.displayName || a.channelName || a.sessionId || "").localeCompare(String(b.alias || b.displayName || b.channelName || b.sessionId || ""), "zh-Hans-CN");
      });

      CHANNEL_MANAGE_UI.agentCandidatesProjectId = projectId;
      CHANNEL_MANAGE_UI.agentCandidates = list;
      const defaultAgent = pickDefaultChannelManageAgent(list);
      CHANNEL_MANAGE_UI.selectedAgentSessionId = defaultAgent ? String(defaultAgent.sessionId || "") : "";
      CHANNEL_MANAGE_UI.selectedAgent = defaultAgent;
      CHANNEL_MANAGE_UI.agentLoading = false;
      renderChannelManageAgentPicker();
      return list;
    }

    function getChannelManageSelectedAgent() {
      const list = Array.isArray(CHANNEL_MANAGE_UI.agentCandidates) ? CHANNEL_MANAGE_UI.agentCandidates : [];
      const sid = channelManageNormalizeText(CHANNEL_MANAGE_UI.selectedAgentSessionId);
      return list.find((row) => channelManageNormalizeText(row && row.sessionId) === sid) || pickDefaultChannelManageAgent(list);
    }

    function selectChannelManageAgentSession(sessionId) {
      const sid = channelManageNormalizeText(sessionId);
      const selected = (CHANNEL_MANAGE_UI.agentCandidates || []).find((row) => channelManageNormalizeText(row && row.sessionId) === sid);
      if (!selected) return;
      CHANNEL_MANAGE_UI.selectedAgentSessionId = sid;
      CHANNEL_MANAGE_UI.selectedAgent = selected;
      toggleChannelManageAgentMenu(false);
      renderChannelManageAgentPicker();
    }

    function toggleChannelManageAgentMenu(forceOpen = null) {
      const picker = document.getElementById("channelEditAgentPicker");
      const card = document.getElementById("channelEditAgentCard");
      if (!picker || !card) return;
      const next = forceOpen == null ? !picker.classList.contains("open") : !!forceOpen;
      picker.classList.toggle("open", next);
      card.setAttribute("aria-expanded", next ? "true" : "false");
    }

    function renderChannelManageAgentPicker() {
      const nameEl = document.getElementById("channelEditAgentCardName");
      const tagEl = document.getElementById("channelEditAgentCardTag");
      const metaEl = document.getElementById("channelEditAgentCardMeta");
      const menu = document.getElementById("channelEditAgentMenu");
      const selected = getChannelManageSelectedAgent();

      if (selected && channelManageNormalizeText(CHANNEL_MANAGE_UI.selectedAgentSessionId) !== channelManageNormalizeText(selected.sessionId)) {
        CHANNEL_MANAGE_UI.selectedAgentSessionId = channelManageNormalizeText(selected.sessionId);
        CHANNEL_MANAGE_UI.selectedAgent = selected;
      }

      if (nameEl) nameEl.textContent = selected ? agentDisplayTitle(selected, "-") : "-";
      if (tagEl) tagEl.textContent = selected && selected.isPrimary ? "主会话" : "子会话";
      if (metaEl) {
        if (CHANNEL_MANAGE_UI.agentLoading) metaEl.textContent = "正在加载可选 Agent…";
        else if (CHANNEL_MANAGE_UI.agentError) metaEl.textContent = CHANNEL_MANAGE_UI.agentError;
        else if (selected) metaEl.textContent = agentDisplaySubtitle(selected, { includeSessionIdFallback: true });
        else metaEl.textContent = "当前项目暂无可选 Agent";
      }
      if (!menu) return;
      menu.innerHTML = "";
      if (CHANNEL_MANAGE_UI.agentLoading) {
        menu.appendChild(el("div", { class: "agent-option", text: "正在加载可选 Agent…" }));
        return;
      }
      if (!(CHANNEL_MANAGE_UI.agentCandidates || []).length) {
        menu.appendChild(el("div", { class: "agent-option", text: "当前项目暂无可选 Agent" }));
        return;
      }
      for (const item of CHANNEL_MANAGE_UI.agentCandidates) {
        const option = el("button", {
          class: "agent-option" + (channelManageNormalizeText(item.sessionId) === channelManageNormalizeText(CHANNEL_MANAGE_UI.selectedAgentSessionId) ? " active" : ""),
          type: "button",
          "aria-selected": channelManageNormalizeText(item.sessionId) === channelManageNormalizeText(CHANNEL_MANAGE_UI.selectedAgentSessionId) ? "true" : "false",
        });
        option.appendChild(el("div", {
          class: "agent-card-head",
          children: [
            el("span", { class: "agent-name", text: agentDisplayTitle(item, "-") }),
            el("span", { class: "agent-tag", text: item.isPrimary ? "主会话" : "子会话" }),
          ],
        }));
        option.appendChild(el("div", {
          class: "agent-meta",
          text: agentDisplaySubtitle(item, { includeSessionIdFallback: true }),
        }));
        option.addEventListener("click", (e) => {
          e.preventDefault();
          selectChannelManageAgentSession(item.sessionId);
        });
        menu.appendChild(option);
      }
    }

    function openChannelEditAgentModal(projectId, channelName) {
      CHANNEL_MANAGE_UI.requestOpen = true;
      CHANNEL_MANAGE_UI.requestSubmitting = false;
      CHANNEL_MANAGE_UI.requestProjectId = channelManageNormalizeText(projectId);
      CHANNEL_MANAGE_UI.requestChannelName = channelManageNormalizeText(channelName);
      CHANNEL_MANAGE_UI.requestChannelDesc = channelManageCurrentDesc(projectId, channelName);
      CHANNEL_MANAGE_UI.requestRequirement = "";
      CHANNEL_MANAGE_UI.confirmOpen = false;
      channelManageSetError("channelEditAgentErr", "");
      channelManageSetError("channelEditAgentConfirmErr", "");
      channelManageResetRequestResult();
      const mask = document.getElementById("channelEditAgentMask");
      if (mask) mask.classList.add("show");
      const sub = document.getElementById("channelEditAgentSub");
      const nameEl = document.getElementById("channelEditAgentName");
      const descEl = document.getElementById("channelEditAgentDesc");
      const req = document.getElementById("channelEditAgentRequirement");
      if (sub) sub.textContent = CHANNEL_MANAGE_UI.requestChannelName || "-";
      if (nameEl) nameEl.textContent = CHANNEL_MANAGE_UI.requestChannelName || "-";
      if (descEl) descEl.textContent = CHANNEL_MANAGE_UI.requestChannelDesc || "暂未填写通道说明";
      if (req) req.value = "";
      closeChannelManageMenus();
      void loadChannelManageAgentCandidates(true);
    }

    function closeChannelEditAgentModal() {
      if (CHANNEL_MANAGE_UI.requestSubmitting) return;
      CHANNEL_MANAGE_UI.requestOpen = false;
      CHANNEL_MANAGE_UI.confirmOpen = false;
      channelManageSetError("channelEditAgentErr", "");
      channelManageSetError("channelEditAgentConfirmErr", "");
      toggleChannelManageAgentMenu(false);
      const mask = document.getElementById("channelEditAgentMask");
      const confirmMask = document.getElementById("channelEditAgentConfirmMask");
      if (mask) mask.classList.remove("show");
      if (confirmMask) confirmMask.classList.remove("show");
    }

    function openChannelEditAgentConfirmModal() {
      if (CHANNEL_MANAGE_UI.requestSubmitting) return;
      const requirement = channelManageNormalizeText(document.getElementById("channelEditAgentRequirement") && document.getElementById("channelEditAgentRequirement").value);
      const agent = getChannelManageSelectedAgent();
      if (!requirement) {
        channelManageSetError("channelEditAgentErr", "请填写业务要求说明");
        return;
      }
      if (!agent || !channelManageNormalizeText(agent.sessionId)) {
        channelManageSetError("channelEditAgentErr", "请先选择处理 Agent");
        return;
      }
      CHANNEL_MANAGE_UI.requestRequirement = requirement;
      CHANNEL_MANAGE_UI.confirmOpen = true;
      channelManageSetError("channelEditAgentErr", "");
      channelManageSetError("channelEditAgentConfirmErr", "");
      const channelEl = document.getElementById("channelEditAgentConfirmChannel");
      const targetEl = document.getElementById("channelEditAgentConfirmTarget");
      if (channelEl) channelEl.textContent = CHANNEL_MANAGE_UI.requestChannelName || "-";
      if (targetEl) targetEl.textContent = String(agent.alias || agent.displayName || agent.channelName || agent.sessionId || "-");
      const mask = document.getElementById("channelEditAgentConfirmMask");
      if (mask) mask.classList.add("show");
    }

    function closeChannelEditAgentConfirmModal() {
      if (CHANNEL_MANAGE_UI.requestSubmitting) return;
      CHANNEL_MANAGE_UI.confirmOpen = false;
      channelManageSetError("channelEditAgentConfirmErr", "");
      const mask = document.getElementById("channelEditAgentConfirmMask");
      if (mask) mask.classList.remove("show");
    }

    async function submitChannelEditAgentRequest() {
      if (CHANNEL_MANAGE_UI.requestSubmitting) return;
      const agent = getChannelManageSelectedAgent();
      if (!agent || !channelManageNormalizeText(agent.sessionId)) {
        channelManageSetError("channelEditAgentConfirmErr", "未找到有效的处理 Agent");
        return;
      }
      CHANNEL_MANAGE_UI.requestSubmitting = true;
      channelManageSetError("channelEditAgentConfirmErr", "");
      const submitBtn = document.getElementById("channelEditAgentConfirmSubmitBtn");
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "发送中...";
      }
      try {
        const source = typeof getNewChannelSourceSession === "function"
          ? getNewChannelSourceSession()
          : { sessionId: "", channelName: CHANNEL_MANAGE_UI.requestChannelName };
        const payload = {
          projectId: CHANNEL_MANAGE_UI.requestProjectId,
          channelName: CHANNEL_MANAGE_UI.requestChannelName,
          channelDesc: CHANNEL_MANAGE_UI.requestChannelDesc,
          targetSessionId: channelManageNormalizeText(agent.sessionId),
          businessRequirement: CHANNEL_MANAGE_UI.requestRequirement,
          sourceSessionId: channelManageNormalizeText(source && source.sessionId),
          sourceChannelName: channelManageNormalizeText((source && source.channelName) || CHANNEL_MANAGE_UI.requestChannelName),
          sourceAgentName: "任务看板",
          sourceAgentAlias: "通道管理",
          sourceAgentId: "task_dashboard",
        };
        const r = await fetch("/api/channels/request-edit", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) {
          const msg = String((j && (j.error || j.message)) || (await parseResponseDetail(r)) || "请求失败");
          channelManageSetError("channelEditAgentConfirmErr", msg);
          return;
        }
        CHANNEL_MANAGE_UI.requestSubmitting = false;
        channelManageNotifyRequestSent(agent, j || {});
        closeChannelEditAgentModal();
        return;
      } catch (err) {
        channelManageSetError("channelEditAgentConfirmErr", String((err && err.message) || "网络或服务异常"));
      } finally {
        CHANNEL_MANAGE_UI.requestSubmitting = false;
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "确认发送";
        }
      }
    }

    function openChannelDeleteModal(projectId, channelName) {
      CHANNEL_MANAGE_UI.deleteOpen = true;
      CHANNEL_MANAGE_UI.deleteSubmitting = false;
      CHANNEL_MANAGE_UI.deleteProjectId = channelManageNormalizeText(projectId);
      CHANNEL_MANAGE_UI.deleteChannelName = channelManageNormalizeText(channelName);
      CHANNEL_MANAGE_UI.deleteChannelDesc = channelManageCurrentDesc(projectId, channelName);
      closeChannelManageMenus();
      channelManageSetError("channelDeleteErr", "");
      const nameEl = document.getElementById("channelDeleteName");
      const descEl = document.getElementById("channelDeleteDesc");
      const input = document.getElementById("channelDeleteConfirmInput");
      if (nameEl) nameEl.textContent = CHANNEL_MANAGE_UI.deleteChannelName || "-";
      if (descEl) descEl.textContent = CHANNEL_MANAGE_UI.deleteChannelDesc || "暂未填写通道说明";
      if (input) input.value = "";
      const mask = document.getElementById("channelDeleteMask");
      if (mask) mask.classList.add("show");
    }

    function closeChannelDeleteModal(force = false) {
      if (CHANNEL_MANAGE_UI.deleteSubmitting && !force) return;
      CHANNEL_MANAGE_UI.deleteOpen = false;
      channelManageSetError("channelDeleteErr", "");
      const mask = document.getElementById("channelDeleteMask");
      if (mask) mask.classList.remove("show");
    }

    function pruneDeletedChannelFromLocalState(projectId, channelName) {
      const pid = channelManageNormalizeText(projectId);
      const ch = channelManageNormalizeText(channelName);
      const proj = typeof projectById === "function" ? projectById(pid) : null;
      if (proj) {
        if (Array.isArray(proj.channels)) {
          proj.channels = proj.channels.filter((row) => channelManageNormalizeText(row && row.name) !== ch);
        }
        if (Array.isArray(proj.channel_sessions)) {
          proj.channel_sessions = proj.channel_sessions.filter((row) => channelManageNormalizeText(row && row.name) !== ch);
        }
      }
      if (typeof itemsForProject === "function" && typeof setProjectItems === "function") {
        const nextItems = itemsForProject(pid).filter((row) => channelManageNormalizeText(row && row.channel) !== ch);
        setProjectItems(pid, nextItems);
      }
      if (typeof loadBindings === "function" && typeof saveBindings === "function") {
        const all = loadBindings();
        if (all && all[pid] && all[pid][ch]) {
          delete all[pid][ch];
          saveBindings(all);
        }
      }
      try {
        if (typeof PERSISTENT_BINDINGS === "object" && PERSISTENT_BINDINGS[pid] && PERSISTENT_BINDINGS[pid][ch]) {
          delete PERSISTENT_BINDINGS[pid][ch];
        }
      } catch (_) {}
      try {
        if (PCONV && Array.isArray(PCONV.sessions)) {
          PCONV.sessions = PCONV.sessions.filter((row) => !sessionMatchesChannel(row, ch));
        }
      } catch (_) {}
      try {
        if (PCONV && PCONV.sessionDirectoryByProject && Array.isArray(PCONV.sessionDirectoryByProject[pid])) {
          PCONV.sessionDirectoryByProject[pid] = PCONV.sessionDirectoryByProject[pid]
            .filter((row) => !sessionMatchesChannel(row, ch));
        }
      } catch (_) {}
      if (STATE && channelManageNormalizeText(STATE.channel) === ch) {
        const remaining = typeof unionChannelNames === "function"
          ? unionChannelNames(pid).filter((name) => channelManageNormalizeText(name) !== ch)
          : [];
        STATE.channel = remaining[0] || "";
        STATE.selectedPath = "";
        STATE.selectedSessionId = "";
        STATE.selectedSessionExplicit = false;
      }
    }

    function isMissingChannelDeleteResponse(response, payload) {
      const status = Number((response && response.status) || 0) || 0;
      const body = (payload && typeof payload === "object") ? payload : {};
      const step = channelManageNormalizeText(body.step).toLowerCase();
      const hay = [
        body.error,
        body.message,
      ].map((item) => channelManageNormalizeText(item).toLowerCase()).join(" ");
      return status === 404 && (step === "resolve_channel" || hay.includes("channel not found"));
    }

    async function healMissingDeletedChannel(projectId, channelName) {
      const pid = channelManageNormalizeText(projectId);
      const ch = channelManageNormalizeText(channelName);
      if (!pid || !ch) return;
      pruneDeletedChannelFromLocalState(pid, ch);
      if (
        typeof refreshConversationPanel === "function"
        && STATE
        && channelManageNormalizeText(STATE.project) === pid
      ) {
        try {
          await refreshConversationPanel();
        } catch (_) {}
      }
      if (typeof render === "function") render();
    }

    function notifyMissingDeletedChannel(channelName) {
      const ch = channelManageNormalizeText(channelName) || "当前通道";
      const message = "通道「" + ch + "」在真源中已不存在，页面已自动移除旧项；如仍看到异常，请刷新页面重新拉取通道列表。";
      if (typeof toast === "function") {
        toast(message, { tone: "success", duration: 3600 });
        return;
      }
      if (typeof setHintText === "function") {
        setHintText((STATE && STATE.panelMode) || "channel", message);
      }
    }

    async function submitChannelDelete() {
      if (CHANNEL_MANAGE_UI.deleteSubmitting) return;
      const confirmValue = channelManageNormalizeText(document.getElementById("channelDeleteConfirmInput") && document.getElementById("channelDeleteConfirmInput").value);
      if (confirmValue !== CHANNEL_MANAGE_UI.deleteChannelName) {
        channelManageSetError("channelDeleteErr", "请输入完整通道名后再确认删除");
        return;
      }
      CHANNEL_MANAGE_UI.deleteSubmitting = true;
      channelManageSetError("channelDeleteErr", "");
      const btn = document.getElementById("channelDeleteConfirmBtn");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "删除中...";
      }
      try {
        const r = await fetch("/api/channels/delete", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            projectId: CHANNEL_MANAGE_UI.deleteProjectId,
            channelName: CHANNEL_MANAGE_UI.deleteChannelName,
            confirmChannelName: confirmValue,
          }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) {
          if (isMissingChannelDeleteResponse(r, j)) {
            await healMissingDeletedChannel(CHANNEL_MANAGE_UI.deleteProjectId, CHANNEL_MANAGE_UI.deleteChannelName);
            closeChannelDeleteModal(true);
            notifyMissingDeletedChannel(CHANNEL_MANAGE_UI.deleteChannelName);
            return;
          }
          const msg = String((j && (j.error || j.message)) || (await parseResponseDetail(r)) || "删除失败");
          channelManageSetError("channelDeleteErr", msg);
          return;
        }
        pruneDeletedChannelFromLocalState(CHANNEL_MANAGE_UI.deleteProjectId, CHANNEL_MANAGE_UI.deleteChannelName);
        if (typeof rebuildDashboardAfterStatusChange === "function") rebuildDashboardAfterStatusChange();
        closeChannelDeleteModal(true);
        if (typeof render === "function") render();
        if (typeof toast === "function") {
          toast("已删除通道「" + CHANNEL_MANAGE_UI.deleteChannelName + "」。", { tone: "success" });
        }
      } catch (err) {
        channelManageSetError("channelDeleteErr", String((err && err.message) || "网络或服务异常"));
      } finally {
        CHANNEL_MANAGE_UI.deleteSubmitting = false;
        if (btn) {
          btn.disabled = false;
          btn.textContent = "确认删除";
        }
      }
    }

    function initChannelManageUi() {
      if (CHANNEL_MANAGE_UI.initBound) return;
      CHANNEL_MANAGE_UI.initBound = true;

      const requestMask = document.getElementById("channelEditAgentMask");
      const confirmMask = document.getElementById("channelEditAgentConfirmMask");
      const deleteMask = document.getElementById("channelDeleteMask");
      if (requestMask) requestMask.addEventListener("click", (e) => {
        if (e.target === requestMask) closeChannelEditAgentModal();
      });
      if (confirmMask) confirmMask.addEventListener("click", (e) => {
        if (e.target === confirmMask) closeChannelEditAgentConfirmModal();
      });
      if (deleteMask) deleteMask.addEventListener("click", (e) => {
        if (e.target === deleteMask) closeChannelDeleteModal();
      });

      const requestCancel = document.getElementById("channelEditAgentCancelBtn");
      if (requestCancel) requestCancel.addEventListener("click", (e) => {
        e.preventDefault();
        closeChannelEditAgentModal();
      });
      const requestSubmit = document.getElementById("channelEditAgentSubmitBtn");
      if (requestSubmit) requestSubmit.addEventListener("click", (e) => {
        e.preventDefault();
        openChannelEditAgentConfirmModal();
      });
      const confirmCancel = document.getElementById("channelEditAgentConfirmCancelBtn");
      if (confirmCancel) confirmCancel.addEventListener("click", (e) => {
        e.preventDefault();
        closeChannelEditAgentConfirmModal();
      });
      const confirmSubmit = document.getElementById("channelEditAgentConfirmSubmitBtn");
      if (confirmSubmit) confirmSubmit.addEventListener("click", (e) => {
        e.preventDefault();
        submitChannelEditAgentRequest();
      });
      const deleteCancel = document.getElementById("channelDeleteCancelBtn");
      if (deleteCancel) deleteCancel.addEventListener("click", (e) => {
        e.preventDefault();
        closeChannelDeleteModal();
      });
      const deleteConfirm = document.getElementById("channelDeleteConfirmBtn");
      if (deleteConfirm) deleteConfirm.addEventListener("click", (e) => {
        e.preventDefault();
        submitChannelDelete();
      });

      const agentCard = document.getElementById("channelEditAgentCard");
      if (agentCard) {
        agentCard.addEventListener("click", async (e) => {
          e.preventDefault();
          if (!(CHANNEL_MANAGE_UI.agentCandidates || []).length) {
            await loadChannelManageAgentCandidates(true);
          }
          toggleChannelManageAgentMenu();
        });
      }

      document.addEventListener("click", (e) => {
        const target = e && e.target;
        const row = target && typeof target.closest === "function" ? target.closest(".channel-row-tools") : null;
        if (!row) closeChannelManageMenus();
        const picker = target && typeof target.closest === "function" ? target.closest("#channelEditAgentPicker") : null;
        if (!picker) toggleChannelManageAgentMenu(false);
      });
    }
