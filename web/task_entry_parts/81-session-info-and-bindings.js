    function getBinding(projectId, channelName, options = {}) {
      const pid = String(projectId || "");
      const ch = String(channelName || "");
      if (!pid || !ch) return null;
      const allowLegacyFallback = !!(options && options.allowLegacyFallback);

      // `/api/sessions/bindings` 现在只保留为兼容接口；主链优先使用已加载的服务端绑定缓存。
      if (PERSISTENT_BINDINGS[pid] && PERSISTENT_BINDINGS[pid][ch]) {
        const b = PERSISTENT_BINDINGS[pid][ch];
        const sid = String(b.sessionId || "").trim();
        if (looksLikeSessionId(sid)) {
          return {
            session_id: sid,
            cli_type: b.cliType || "codex",
            updated_at: b.boundAt || "",
            source: "bindings_server",
          };
        }
      }

      // 当前项目已成功加载服务端 bindings 后，兼容 localStorage 不再参与主链兜底。
      if (PERSISTENT_BINDINGS_SERVER_OK && hasPersistentBindingsForProject(pid)) return null;

      // localStorage 只保留给旧入口显式兼容，不再作为默认绑定真源。
      if (!allowLegacyFallback) return null;
      const all = loadBindings();
      const hit = all && all[pid] ? all[pid][ch] : null;
      if (!hit) return null;
      const sid = String(hit.session_id || hit.sessionId || "").trim();
      if (!looksLikeSessionId(sid)) return null;
      const cliType = String(hit.cli_type || hit.cliType || "codex").trim() || "codex";
      return {
        session_id: sid,
        cli_type: cliType,
        updated_at: String(hit.updated_at || ""),
        source: "bindings_local_legacy",
      };
    }

    // Set binding - save to server and localStorage
    async function setBinding(projectId, channelName, sessionId, cliType) {
      const pid = String(projectId || "");
      const ch = String(channelName || "");
      const sid = String(sessionId || "").trim();
      const cli = String(cliType || "codex").trim() || "codex";
      if (!pid || !ch || !looksLikeSessionId(sid)) return false;

      // Save to server first (server-first); if it fails, don't write local-only binding.
      try {
        const resp = await fetch("/api/sessions/bindings/save", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            sessionId: sid,
            projectId: pid,
            channelName: ch,
            cliType: cli,
          }),
        });
        if (!resp.ok) return false;
      } catch (_) { return false; }

      // Also save to localStorage for quick access
      const all = loadBindings();
      if (!all[pid]) all[pid] = {};
      all[pid][ch] = { session_id: sid, cli_type: cli, updated_at: new Date().toISOString() };
      saveBindings(all);

      // Update in-memory cache
      if (!PERSISTENT_BINDINGS[pid]) PERSISTENT_BINDINGS[pid] = {};
      PERSISTENT_BINDINGS[pid][ch] = { sessionId: sid, cliType: cli, boundAt: new Date().toISOString() };
      PERSISTENT_BINDINGS_SERVER_OK = true;

      return true;
    }

    // Clear binding - delete from server and localStorage
    async function clearBinding(projectId, channelName) {
      const pid = String(projectId || "");
      const ch = String(channelName || "");

      // Get sessionId before deleting
      const binding = getBinding(pid, ch);
      const sid = binding ? binding.session_id : null;

      // Delete from server first
      if (sid) {
        try {
          const resp = await fetch("/api/sessions/bindings/delete", {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ sessionId: sid }),
          });
          if (!resp.ok) return false;
        } catch (_) { return false; }
      }

      // Delete from localStorage
      const all = loadBindings();
      if (all && all[pid] && all[pid][ch]) {
        delete all[pid][ch];
        saveBindings(all);
      }

      // Update in-memory cache
      if (PERSISTENT_BINDINGS[pid] && PERSISTENT_BINDINGS[pid][ch]) {
        delete PERSISTENT_BINDINGS[pid][ch];
      }

      return true;
    }

    // 兼容旧入口：绑定对话统一走“接入通道对话”弹窗的“添加已有对话”模式
    function openBindModal(projectId, channelName) {
      openNewConvModal(projectId, channelName, "attach", { legacyBindingEntry: true });
    }
    function closeBindModal() {
      closeNewConvModal();
    }

    // 新增/接入对话弹窗
    const NEW_CONV_UI = {
      open: false,
      projectId: "",
      channelName: "",
      mode: "create",
      legacyBindingEntry: false,
      initMessageDirty: false,
      advancedOpen: false,
      advancedBound: false,
      contextPrefill: null,
    };

    const SESSION_INFO_UI = {
      open: false,
      loading: false,
      saving: false,
      heartbeatSaving: false,
      avatarPickerOpen: false,
      avatarPickerDraftId: "",
      sessionId: "",
      projectId: "",
      base: null,
      form: null,
      error: "",
      heartbeatError: "",
      heartbeatNote: "",
      heartbeatMeta: null,
      heartbeatSummary: null,
      heartbeatTasks: [],
      heartbeatDraft: null,
      heartbeatTaskEditorOpen: false,
      heartbeatTaskEditorMode: "edit",
      heartbeatHistoryByTask: Object.create(null),
      heartbeatHistoryLoadingByTask: Object.create(null),
      heartbeatHistoryErrorByTask: Object.create(null),
      heartbeatHistoryTaskId: "",
      heartbeatActionByTask: Object.create(null),
    };

    const CHANNEL_CONV_MGMT_UI = {
      open: false,
      loading: false,
      saving: false,
      projectId: "",
      channelName: "",
      sessions: [],
      primarySessionId: "",
      error: "",
    };

    function normalizeNewConvMode(mode) {
      return String(mode || "") === "attach" ? "attach" : "create";
    }

    function buildNewConvInitMessage(channelName) {
      if (typeof buildUnifiedAgentInitMessage === "function") {
        return buildUnifiedAgentInitMessage(channelName);
      }
      const channelLabel = String(channelName || "").trim() || "当前通道";
      return [
        "[Agent培训] " + channelLabel,
        "在开始当前协作前，你必须先完成以下初始化训练。未完成前，不要回复“已完成初始化”，也不要直接开始正式任务。",
        "",
        "1. 明确职责边界",
        "- 只围绕当前通道和当前任务主线执行，不自行扩题。",
        "- 默认处理后回原发送 Agent；若消息中有 callback_to.session_id，优先回该 session。",
        "",
        "2. 对齐项目真源",
        "- 项目配置 = 真源默认上下文。",
        "- Agent = 身份，session = 当前承载结果。",
        "- 不清楚工作区、分支、真源时，先查项目内真源，不自行猜测。",
        "",
        "3. 阅读必读入口并学习项目技能",
        "- README.md",
        "- 活动任务/",
        "- 活动反馈/",
        "- 产出物/材料/",
        "- 产出物/沉淀/",
        "- 当前项目 skills 真源/索引文件",
        "- 至少重点学习：agent-init-training-playbook、collab-message-send（或当前项目等效的正式消息技能）、当前通道自己的专项 skill。",
        "",
        "4. 学会怎么发正式消息",
        "- 跨 Agent / 跨通道协作只能走同源 /api/codex/announce（announce_to_channel），不能把内部草稿、内部 spawn、非正式 resume 当成“已通知通道”。",
        "- 正式消息默认用你当前执行 Agent 自己的身份发送，不借用项目主会话、总控或其他通道 Agent 身份。",
        "- 没有 announce_run_id 时，不得写已发出 / 已送达 / 已通知通道。",
        "- 正式通知成功至少分三层判断：已生成待发送正文 / 已提交发送，待验证 / 已完成证据闭环。",
        "",
        "5. 学会什么时候必须回执",
        "- 收到任务先首回执，执行后再回结构化结论。",
        "- 只有 notify_only 才可不回。",
        "- 后续默认按 任务 / 反馈 / 产出物 推进；普通任务优先任务文件收口块，反馈文件仅用于增强验收包。",
        "",
        "6. 完成一次消息能力验证",
        "- 去项目通讯录/CCR 中找到一个“不是你自己”的 Agent，发送 1 条最小初始化验证消息。",
        "- 如果当前项目没有可用通讯录或找不到目标，再回唯一阻塞，不得跳过这一步。",
        "",
        "7. 学习完成后的固定回执格式",
        "已完成初始化",
        "当前职责边界: <一句话>",
        "当前主线: <一句话>",
        "已学习技能: <列出本轮已学习的关键 skills>",
        "通讯录验证: 已向 <agent名称> 发送正式消息",
        "验证证据: <run_id / 目标session_id>",
        "唯一阻塞: <无/一句话>",
        "首个动作: <一句话>",
      ].join("\n");
    }

    function syncNewConvInitMessage(force = false) {
      const input = document.getElementById("newConvInitMessage");
      if (!input) return;
      if (!force && NEW_CONV_UI.initMessageDirty) return;
      input.value = buildNewConvInitMessage(NEW_CONV_UI.channelName);
      NEW_CONV_UI.initMessageDirty = false;
    }

    function selectedOptionText(selectEl, fallback = "") {
      if (!selectEl) return String(fallback || "");
      const idx = Number(selectEl.selectedIndex);
      const option = idx >= 0 ? selectEl.options[idx] : null;
      return String((option && option.text) || selectEl.value || fallback || "");
    }

    function buildNewConvAdvancedSummary() {
      const strategyText = selectedOptionText(
        document.getElementById("newConvReuseStrategy"),
        "总是新建"
      );
      const environmentText = selectedOptionText(
        document.getElementById("newConvEnvironment"),
        "stable"
      );
      return "默认：" + [strategyText, environmentText].filter(Boolean).join(" / ");
    }

    function syncNewConvAdvancedSummary() {
      const summaryEl = document.getElementById("newConvAdvancedSummary");
      if (!summaryEl) return;
      summaryEl.textContent = buildNewConvAdvancedSummary();
    }

    function setNewConvAdvancedOpen(open) {
      const next = !!open;
      NEW_CONV_UI.advancedOpen = next;
      const section = document.getElementById("newConvAdvancedSection");
      const toggle = document.getElementById("newConvAdvancedToggle");
      const body = document.getElementById("newConvAdvancedBody");
      if (section) section.classList.toggle("open", next);
      if (toggle) toggle.setAttribute("aria-expanded", next ? "true" : "false");
      if (body) body.hidden = !next;
      syncNewConvAdvancedSummary();
    }

    function bindNewConvAdvancedControls() {
      if (NEW_CONV_UI.advancedBound) return;
      NEW_CONV_UI.advancedBound = true;

      const toggle = document.getElementById("newConvAdvancedToggle");
      if (toggle) {
        toggle.addEventListener("click", () => {
          setNewConvAdvancedOpen(!NEW_CONV_UI.advancedOpen);
        });
      }

      [
        ["newConvSessionRole", "change"],
        ["newConvReuseStrategy", "change"],
        ["newConvEnvironment", "change"],
        ["newConvModel", "input"],
        ["newConvPurpose", "input"],
        ["newConvWorktreeRoot", "input"],
        ["newConvWorkdir", "input"],
        ["newConvBranch", "input"],
      ].forEach(([id, eventName]) => {
        const node = document.getElementById(id);
        if (!node) return;
        node.addEventListener(eventName, () => {
          syncNewConvAdvancedSummary();
        });
      });
    }

    function setNewConvMode(mode) {
      const next = normalizeNewConvMode(mode);
      NEW_CONV_UI.mode = next;
      const legacyBindingEntry = !!NEW_CONV_UI.legacyBindingEntry;

      const createBtn = document.getElementById("newConvCreateBtn");
      const subEl = document.getElementById("newConvSub");
      const hintEl = document.getElementById("newConvHint");
      const sessionRow = document.getElementById("newConvSessionRow");
      const initRow = document.getElementById("newConvInitRow");
      const createTab = document.getElementById("newConvModeCreate");
      const attachTab = document.getElementById("newConvModeAttach");
      const sidInput = document.getElementById("newConvSessionId");

      if (createTab) createTab.classList.toggle("active", next === "create");
      if (attachTab) attachTab.classList.toggle("active", next === "attach");
      if (sessionRow) sessionRow.style.display = next === "attach" ? "" : "none";
      if (initRow) initRow.style.display = next === "create" ? "grid" : "none";

      if (createBtn) createBtn.textContent = next === "attach"
        ? (legacyBindingEntry ? "兼容绑定已有对话" : "绑定已有对话")
        : "创建并绑定";
      if (subEl) subEl.textContent = next === "attach"
        ? (legacyBindingEntry
          ? "输入已有会话 ID 并绑定到当前通道（兼容管理入口，非主链真源）"
          : "输入已有会话 ID 并绑定到当前通道（兼容管理入口）")
        : "创建新会话并绑定到当前通道";
      if (hintEl) {
        hintEl.textContent = next === "attach"
          ? (legacyBindingEntry
            ? "这是旧入口兼容管理模式：建议先确认 Session ID 与 CLI 类型一致；该绑定接口只保留给兼容维护与历史排查，新链路仍以会话列表与候选接口为准。"
            : "建议先确认 Session ID 与 CLI 类型一致；该绑定接口仅保留为兼容管理入口，新链路仍以会话列表与候选接口为准。")
          : "将创建新的 CLI 会话并自动绑定到通道，并自动发送你设置的首条消息。";
      }
      if (next === "attach" && sidInput) sidInput.value = "";
      if (next === "create") syncNewConvInitMessage(false);
      syncNewConvAdvancedSummary();
    }

    function applyNewConvBindingPreset() {
      const sidInput = document.getElementById("newConvSessionId");
      const cliSelect = document.getElementById("newConvCliType");
      const modelInput = document.getElementById("newConvModel");
      const cur = getBinding(NEW_CONV_UI.projectId, NEW_CONV_UI.channelName);
      const sess = sessionForChannel(NEW_CONV_UI.projectId, NEW_CONV_UI.channelName);
      if (sidInput) sidInput.value = "";
      if (cliSelect && cur && cur.cli_type) cliSelect.value = String(cur.cli_type || "codex");
      if (modelInput) modelInput.value = normalizeSessionModel(sess && sess.model);
      syncNewConvModelUI();
    }

    function collectNewConvEnvironmentOptions(prefill) {
      const base = (prefill && typeof prefill === "object") ? prefill : {};
      const rows = [{
        value: normalizeSessionEnvironmentValue(base.environment || "stable"),
        label: normalizeSessionEnvironmentValue(base.environment || "stable"),
        meta: "当前默认环境",
      }];
      collectKnownSessionContextRows().forEach((row) => {
        rows.push({
          value: normalizeSessionEnvironmentValue(row.environment || "stable"),
          label: normalizeSessionEnvironmentValue(row.environment || "stable"),
          meta: getSessionContextRowMeta(row, base, "环境"),
        });
      });
      return uniqueSessionContextOptions(rows);
    }

    function buildNewConvContextPrefill(projectId, channelName) {
      const currentSession = sessionForChannel(projectId, channelName)
        || findConversationSessionById(STATE.selectedSessionId)
        || null;
      const channelSessions = (typeof conversationSessionsForChannel === "function")
        ? conversationSessionsForChannel(channelName, projectId)
        : [];
      const hasPrimarySession = Array.isArray(channelSessions)
        && channelSessions.some((session) => {
          if (typeof isPrimarySession === "function") return isPrimarySession(session);
          const row = (session && typeof session === "object") ? session : {};
          return boolLike(row.is_primary) || boolLike(row.isPrimary);
        });
      const normalized = normalizeConversationSessionDetail(currentSession || {}, currentSession || null);
      const projectContext = (DATA && DATA.projectContext && typeof DATA.projectContext === "object")
        ? DATA.projectContext
        : {};
      const environment = normalizeSessionEnvironmentValue(
        normalized.environment || projectContext.environment || "stable"
      );
      const worktreeRoot = String(normalized.worktree_root || projectContext.worktreeRoot || "").trim();
      const workdir = String(normalized.workdir || worktreeRoot || "").trim();
      const branch = String(normalized.branch || projectContext.branch || "").trim();
      return {
        environment,
        worktree_root: worktreeRoot,
        workdir,
        branch,
        session_role: hasPrimarySession ? "child" : "primary",
        reuse_strategy: "create_new",
        purpose: channelName ? ("新增" + String(channelName) + "对话") : "新增通道对话",
      };
    }

    function syncNewConvContextFields() {
      const prefill = buildNewConvContextPrefill(NEW_CONV_UI.projectId, NEW_CONV_UI.channelName);
      NEW_CONV_UI.contextPrefill = prefill;
      const envSelect = document.getElementById("newConvEnvironment");
      const worktreeInput = document.getElementById("newConvWorktreeRoot");
      const workdirInput = document.getElementById("newConvWorkdir");
      const branchInput = document.getElementById("newConvBranch");
      const roleSelect = document.getElementById("newConvSessionRole");
      const reuseSelect = document.getElementById("newConvReuseStrategy");
      const purposeInput = document.getElementById("newConvPurpose");

      if (envSelect) {
        envSelect.innerHTML = "";
        collectNewConvEnvironmentOptions(prefill).forEach((row) => {
          const opt = el("option", {
            value: row.value,
            text: row.label,
            title: row.title || row.meta || row.label,
          });
          if (String(row.value || "") === String(prefill.environment || "")) opt.selected = true;
          envSelect.appendChild(opt);
        });
        if (!envSelect.value) envSelect.value = String(prefill.environment || "stable");
      }
      if (worktreeInput) worktreeInput.value = String(prefill.worktree_root || "");
      if (workdirInput) workdirInput.value = String(prefill.workdir || "");
      if (branchInput) branchInput.value = String(prefill.branch || "");
      if (roleSelect) roleSelect.value = String(prefill.session_role || "primary");
      if (reuseSelect) reuseSelect.value = String(prefill.reuse_strategy || "create_new");
      if (purposeInput) purposeInput.value = String(prefill.purpose || "");
      syncNewConvAdvancedSummary();
    }

    function syncNewConvModelUI() {
      const cliSelect = document.getElementById("newConvCliType");
      const modelInput = document.getElementById("newConvModel");
      if (!modelInput) return;
      const cli = String((cliSelect && cliSelect.value) || "codex").trim() || "codex";
      modelInput.placeholder = modelInputPlaceholderByCli(cli);
    }

    function openNewConvModal(preProjectId, preChannelName, preferredMode = "create", options = {}) {
      const pid = String(preProjectId || STATE.project || "");
      const ch = String(preChannelName || STATE.channel || "");
      bindNewConvAdvancedControls();
      NEW_CONV_UI.open = true;
      NEW_CONV_UI.projectId = pid;
      NEW_CONV_UI.channelName = ch;
      NEW_CONV_UI.mode = normalizeNewConvMode(preferredMode);
      NEW_CONV_UI.legacyBindingEntry = !!(options && options.legacyBindingEntry);
      NEW_CONV_UI.advancedOpen = false;

      newConvModalError("");

      // 填充项目列表
      const projSelect = document.getElementById("newConvProject");
      if (projSelect) {
        projSelect.innerHTML = "";
        const projs = pages().filter(x => x.id !== "overview");
        for (const p of projs) {
          const opt = el("option", { value: String(p.id || ""), text: String(p.name || p.id || "") });
          if (String(p.id || "") === pid) opt.selected = true;
          projSelect.appendChild(opt);
        }
        // 在项目页面中固定项目选择，禁止更改
        if (pid && pid !== "overview") {
          projSelect.disabled = true;
        } else {
          projSelect.disabled = false;
        }
      }

      // 填充通道列表
      updateNewConvChannels(pid, ch);

      const sidInput = document.getElementById("newConvSessionId");
      const cliSelect = document.getElementById("newConvCliType");
      if (cliSelect) cliSelect.value = "codex";
      applyNewConvBindingPreset();
      syncNewConvContextFields();
      NEW_CONV_UI.initMessageDirty = false;
      syncNewConvInitMessage(true);
      setNewConvMode(NEW_CONV_UI.mode);
      setNewConvAdvancedOpen(false);

      const mask = document.getElementById("newConvMask");
      if (mask) mask.classList.add("show");

      setTimeout(() => {
        try {
          const focusEl = NEW_CONV_UI.mode === "attach" ? sidInput : document.getElementById("newConvChannel");
          if (focusEl) focusEl.focus();
        } catch (_) {}
      }, 10);
    }

    function updateNewConvChannels(projectId, selectChannel) {
      const chSelect = document.getElementById("newConvChannel");
      if (!chSelect) return;
      chSelect.innerHTML = "";
      const proj = projectById(projectId);
      const channels = (proj && Array.isArray(proj.channels)) ? proj.channels : [];
      if (!channels.length) {
        chSelect.appendChild(el("option", { value: "", text: "无可用通道" }));
        return;
      }
      for (const ch of channels) {
        // channels 可能是字符串数组或对象数组（有 name 属性）
        const chName = (ch && typeof ch === "object") ? String(ch.name || "") : String(ch || "");
        const opt = el("option", { value: chName, text: chName });
        if (chName === String(selectChannel || "")) opt.selected = true;
        chSelect.appendChild(opt);
      }
      NEW_CONV_UI.channelName = String(chSelect.value || "");
    }

    function closeNewConvModal() {
      NEW_CONV_UI.open = false;
      NEW_CONV_UI.legacyBindingEntry = false;
      const mask = document.getElementById("newConvMask");
      if (mask) mask.classList.remove("show");
      const errEl = document.getElementById("newConvErr");
      if (errEl) errEl.style.display = "none";
    }

    function normalizeConversationSessionDetail(raw, fallback = null) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const fb = (fallback && typeof fallback === "object") ? fallback : {};
      const sid = firstNonEmptyText([src.id, src.session_id, src.sessionId, fb.sessionId, fb.id]);
      const srcContext = (src.context && typeof src.context === "object") ? src.context : {};
      const fbContext = (fb.context && typeof fb.context === "object") ? fb.context : {};
      const rawHeartbeat = (src.heartbeat && typeof src.heartbeat === "object") ? src.heartbeat : {};
      const heartbeatItems = normalizeHeartbeatTaskItemsClient(
        Array.isArray(rawHeartbeat.items) ? rawHeartbeat.items : [],
        String(SESSION_INFO_UI.projectId || STATE.project || "").trim(),
        rawHeartbeat
      );
      return {
        sessionId: String(sid || ""),
        id: String(sid || ""),
        alias: firstNonEmptyText([src.alias, fb.alias]),
        channel_name: firstNonEmptyText([src.channel_name, src.channelName, fb.channel_name, fb.primaryChannel]),
        environment: normalizeSessionEnvironmentValue(
          src.environment || src.environmentName || src.environment_obj || src.environment_summary || srcContext.environment,
          fb.environment
        ),
        worktree_root: firstNonEmptyText([src.worktree_root, src.worktreeRoot, srcContext.worktree_root, srcContext.worktreeRoot, fb.worktree_root, fbContext.worktree_root, fbContext.worktreeRoot]),
        workdir: firstNonEmptyText([src.workdir, srcContext.workdir, fb.workdir, fbContext.workdir]),
        branch: firstNonEmptyText([src.branch, srcContext.branch, fb.branch, fbContext.branch]),
        cli_type: firstNonEmptyText([src.cli_type, src.cliType, fb.cli_type], "codex"),
        model: normalizeSessionModel(firstNonEmptyText([src.model, fb.model])),
        reasoning_effort: normalizeReasoningEffort(firstNonEmptyText([src.reasoning_effort, src.reasoningEffort, fb.reasoning_effort])),
        status: firstNonEmptyText([src.status, fb.status], "active"),
        display_name: firstNonEmptyText([
          src.alias,
          fb.alias,
          src.display_name,
          src.displayName,
          fb.displayName,
          fb.displayChannel,
        ]),
        display_name_source: firstNonEmptyText([
          src.alias ? "alias" : "",
          fb.alias ? "alias" : "",
          src.display_name_source,
          src.displayNameSource,
          fb.displayNameSource,
        ]),
        codex_title: firstNonEmptyText([src.codex_title, src.codexTitle, fb.codexTitle]),
        is_primary: boolLike(firstNonEmptyText([src.is_primary, src.isPrimary, fb.is_primary])),
        source: firstNonEmptyText([src.source, fb.source]),
        created_at: firstNonEmptyText([src.created_at, src.createdAt, fb.created_at]),
        last_used_at: firstNonEmptyText([src.last_used_at, src.lastUsedAt, fb.last_used_at]),
        runtime_state: normalizeRuntimeState(src.runtime_state || src.runtimeState || fb.runtime_state || null),
        heartbeat_summary: normalizeHeartbeatSummaryClient(
          src.heartbeat_summary || src.heartbeatSummary || rawHeartbeat.summary || fb.heartbeat_summary || fb.heartbeatSummary || {},
          heartbeatItems
        ),
        project_execution_context: normalizeProjectExecutionContext(
          src.project_execution_context
            || src.projectExecutionContext
            || fb.project_execution_context
            || fb.projectExecutionContext
            || null
        ),
        task_tracking: normalizeTaskTrackingClient(
          src.task_tracking
            || src.taskTracking
            || fb.task_tracking
            || fb.taskTracking
            || null
        ),
      };
    }

    function normalizeSessionInfoResponse(payload, fallback = null) {
      const src = (payload && typeof payload === "object")
        ? ((payload.session && typeof payload.session === "object") ? payload.session : payload)
        : {};
      return normalizeConversationSessionDetail(src, fallback);
    }

    function normalizeHeartbeatSummaryClient(raw, items = []) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const list = Array.isArray(items) ? items : [];
      const totalCount = Math.max(0, Number(
        firstNonEmptyText([
          src.total_count,
          src.totalCount,
          src.count,
          list.length,
        ]) || 0
      ));
      const enabledCount = Math.max(0, Number(
        firstNonEmptyText([
          src.enabled_count,
          src.enabledCount,
          src.active_count,
          src.activeCount,
          list.filter((row) => _coerceBoolClient(row && row.enabled, false)).length,
        ]) || 0
      ));
      return {
        total_count: totalCount,
        enabled_count: Math.min(totalCount || enabledCount, enabledCount),
        has_enabled_tasks: _coerceBoolClient(src.has_enabled_tasks, enabledCount > 0),
        latest_triggered_at: firstNonEmptyText([src.latest_triggered_at, src.latestTriggeredAt]),
        next_due_at: firstNonEmptyText([src.next_due_at, src.nextDueAt]),
        last_error: firstNonEmptyText([src.last_error, src.lastError]),
      };
    }

    function defaultSessionHeartbeatTaskDraft(baseSession = null, taskId = "") {
      const base = (baseSession && typeof baseSession === "object") ? baseSession : (SESSION_INFO_UI.base || {});
      const pid = String(SESSION_INFO_UI.projectId || STATE.project || "").trim();
      const sid = String(base.sessionId || base.id || SESSION_INFO_UI.sessionId || "").trim();
      const draft = defaultHeartbeatTaskDraft(pid, taskId);
      draft.channelName = String(base.channel_name || draft.channelName || "").trim();
      draft.sessionId = sid || draft.sessionId || "";
      draft.heartbeatEnabled = true;
      draft.heartbeatScanIntervalSeconds = Math.max(20, Number(draft.heartbeatScanIntervalSeconds || 30));
      return draft;
    }

    function sessionHeartbeatTaskKey(sessionId, heartbeatTaskId) {
      const sid = String(sessionId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      return sid && tid ? (sid + ":" + tid) : "";
    }

    function normalizeSessionHeartbeatMeta(raw, items = []) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const list = Array.isArray(items) ? items : [];
      const summary = normalizeHeartbeatSummaryClient(
        src.summary || src.heartbeat_summary || src.heartbeatSummary || src,
        list
      );
      return {
        enabled: _coerceBoolClient(src.enabled, summary.enabled_count > 0),
        count: Math.max(0, Number(src.count || summary.total_count || list.length || 0)),
        enabled_count: Math.max(0, Number(src.enabled_count || summary.enabled_count || 0)),
        ready: _coerceBoolClient(src.ready, true),
        errors: Array.isArray(src.errors) ? src.errors : [],
        scan_interval_seconds: Math.max(20, Number(src.scan_interval_seconds || src.scanIntervalSeconds || 30)),
      };
    }

    function extractSessionHeartbeatPayload(payload) {
      const src = (payload && typeof payload === "object")
        ? ((payload.session && typeof payload.session === "object") ? payload.session : payload)
        : {};
      const hb = (src && typeof src.heartbeat === "object")
        ? src.heartbeat
        : ((payload && typeof payload.heartbeat === "object") ? payload.heartbeat : {});
      const rawItems = Array.isArray(hb && hb.items)
        ? hb.items
        : (Array.isArray(hb && hb.tasks) ? hb.tasks : []);
      const items = normalizeHeartbeatTaskItemsClient(
        rawItems,
        String(SESSION_INFO_UI.projectId || STATE.project || "").trim(),
        hb || {}
      );
      const summary = normalizeHeartbeatSummaryClient(
        src.heartbeat_summary
          || src.heartbeatSummary
          || (hb && hb.summary)
          || (payload && payload.heartbeat_summary)
          || {},
        items
      );
      return {
        meta: normalizeSessionHeartbeatMeta(Object.assign({}, hb, summary), items),
        summary,
        items,
      };
    }

    function buildSessionHeartbeatTaskDraft(task, meta = null) {
      const base = SESSION_INFO_UI.base || {};
      const draft = heartbeatTaskDraftFromItem(
        String(SESSION_INFO_UI.projectId || STATE.project || "").trim(),
        task || {},
        meta || SESSION_INFO_UI.heartbeatMeta || {}
      );
      draft.channelName = String(base.channel_name || draft.channelName || "").trim();
      draft.sessionId = String(base.sessionId || base.id || SESSION_INFO_UI.sessionId || draft.sessionId || "").trim();
      return draft;
    }

    function syncSessionHeartbeatDraft(preferredTaskId = "") {
      const base = SESSION_INFO_UI.base || {};
      const meta = SESSION_INFO_UI.heartbeatMeta || normalizeSessionHeartbeatMeta({}, []);
      const tasks = Array.isArray(SESSION_INFO_UI.heartbeatTasks) ? SESSION_INFO_UI.heartbeatTasks : [];
      const current = SESSION_INFO_UI.heartbeatDraft || null;
      const desiredId = String(
        preferredTaskId
        || (current && current.heartbeatTaskId)
        || SESSION_INFO_UI.heartbeatHistoryTaskId
        || (tasks[0] && tasks[0].heartbeat_task_id)
        || ""
      ).trim();
      const matched = desiredId
        ? (tasks.find((row) => String(row.heartbeat_task_id || "").trim() === desiredId) || null)
        : null;
      let next = null;
      if (matched) {
        next = buildSessionHeartbeatTaskDraft(matched, meta);
      } else {
        next = defaultSessionHeartbeatTaskDraft(base, desiredId);
        next.heartbeatEnabled = !!meta.enabled;
        next.heartbeatScanIntervalSeconds = Math.max(20, Number(meta.scan_interval_seconds || 30));
      }
      SESSION_INFO_UI.heartbeatDraft = next;
      return next;
    }

    function applySessionHeartbeatPayload(payload, preferredTaskId = "") {
      const parsed = extractSessionHeartbeatPayload(payload);
      SESSION_INFO_UI.heartbeatMeta = parsed.meta;
      SESSION_INFO_UI.heartbeatSummary = parsed.summary;
      SESSION_INFO_UI.heartbeatTasks = parsed.items;
      syncSessionHeartbeatDraft(preferredTaskId);
    }

    function syncConversationHeartbeatSummaryToStore(sessionId, summary, tasks = []) {
      const sid = String(sessionId || "").trim();
      if (!sid) return;
      const normalized = normalizeHeartbeatSummaryClient(summary || {}, tasks);
      for (let i = 0; i < PCONV.sessions.length; i++) {
        const row = PCONV.sessions[i];
        if (String(getSessionId(row) || "").trim() !== sid) continue;
        row.heartbeat_summary = normalized;
        break;
      }
    }

    function heartbeatDraftMaxExecuteInputValue(draft) {
      const value = Math.max(0, Number((draft && draft.maxExecuteCount) || 0));
      return value > 0 ? String(value) : "";
    }

    function buildConversationHeartbeatLimitFact(label, value, extraClass = "") {
      const item = el("div", { class: "conv-heartbeat-limit-fact" + (extraClass ? (" " + extraClass) : "") });
      item.appendChild(el("span", { class: "k", text: label }));
      item.appendChild(el("span", { class: "v", text: value }));
      return item;
    }

    function buildConversationHeartbeatLimitStatusCard(task, draft = null) {
      const liveTask = (task && typeof task === "object") ? task : null;
      const liveMeta = heartbeatTaskExecuteLimitMeta(liveTask || {});
      const draftObj = (draft && typeof draft === "object") ? draft : {};
      const draftLimit = Math.max(0, Number(draftObj.maxExecuteCount || 0));
      const liveMax = liveMeta.maxExecuteCount;
      const displayMax = liveMeta.hasMeta && liveMax != null
        ? (liveMax > 0 ? (liveMax + " 次") : "不限")
        : (draftLimit > 0 ? (draftLimit + " 次（草稿）") : "不限（草稿）");
      const displayExecuted = liveMeta.executedCount != null ? (liveMeta.executedCount + " 次") : "待回传";
      const displayRemaining = liveMeta.hasMeta
        ? (liveMax === 0 ? "不限" : (liveMeta.remainingExecuteCount != null ? (liveMeta.remainingExecuteCount + " 次") : "待回传"))
        : "待回传";
      const summaryText = liveMeta.hasMeta
        ? (heartbeatTaskExecuteLimitInlineText(liveTask) || "执行次数状态待回传")
        : "live 真源尚未回传执行次数字段；当前先按冻结样例接入 optional 展示。";
      const card = el("section", { class: "conv-heartbeat-limit-card" + (liveMeta.reached ? " is-reached" : "") });
      const head = el("div", { class: "conv-heartbeat-limit-head" });
      head.appendChild(el("div", { class: "conv-heartbeat-limit-title", text: "执行次数状态" }));
      if (liveMeta.reached) head.appendChild(chip("已达上限自动关闭", "warn"));
      card.appendChild(head);

      const facts = el("div", { class: "conv-heartbeat-limit-facts" });
      facts.appendChild(buildConversationHeartbeatLimitFact("最大执行次数", displayMax));
      facts.appendChild(buildConversationHeartbeatLimitFact("已执行次数", displayExecuted));
      facts.appendChild(buildConversationHeartbeatLimitFact("剩余次数", displayRemaining));
      card.appendChild(facts);

      card.appendChild(el("div", { class: "conv-heartbeat-limit-summary", text: summaryText }));
      if (liveMeta.autoDisabledAt) {
        card.appendChild(el("div", {
          class: "conv-heartbeat-limit-meta",
          text: "自动关闭时间："
            + (compactDateTime(liveMeta.autoDisabledAt) || shortDateTime(liveMeta.autoDisabledAt) || liveMeta.autoDisabledAt),
        }));
      }
      if (!liveMeta.hasMeta || (draftLimit !== (liveMax == null ? 0 : liveMax))) {
        card.appendChild(el("div", {
          class: "conv-heartbeat-limit-draft",
          text: "当前草稿上限："
            + (draftLimit > 0 ? (draftLimit + " 次") : "不限")
            + "；`run-now` 不计入执行次数。",
        }));
      } else {
        card.appendChild(el("div", {
          class: "conv-heartbeat-limit-draft",
          text: "`run-now` 不计入执行次数；retry / 恢复不重复计数。",
        }));
      }
      return card;
    }

    // 会话级心跳写回真源时，若 source_scope 缺失但 task 仍绑定当前 session，
    // 也要按 session 任务保留，避免被误判成 project 后在保存时被过滤掉。
    function inferConversationHeartbeatTaskSourceScope(task, sessionId = "") {
      const row = (task && typeof task === "object") ? task : {};
      const explicitScope = String(firstNonEmptyText([row.source_scope, row.sourceScope])).trim().toLowerCase();
      if (explicitScope === "project") return "project";
      if (explicitScope === "session") return "session";
      const taskSessionId = String(firstNonEmptyText([row.session_id, row.sessionId])).trim();
      const currentSessionId = String(sessionId || "").trim();
      if (taskSessionId && (!currentSessionId || taskSessionId === currentSessionId)) return "session";
      return "project";
    }

    function buildSessionHeartbeatPayloadFromDrafts() {
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const channelName = String(SESSION_INFO_UI.base && SESSION_INFO_UI.base.channel_name || "").trim();
      const tasks = (Array.isArray(SESSION_INFO_UI.heartbeatTasks) ? SESSION_INFO_UI.heartbeatTasks : [])
        .filter((task) => inferConversationHeartbeatTaskSourceScope(task, sid) !== "project");
      const enabledCount = tasks.filter((row) => _coerceBoolClient(row && row.enabled, false)).length;
      return {
        heartbeat: {
          enabled: enabledCount > 0,
          tasks: tasks.map((task) => {
            const row = (task && typeof task === "object") ? task : {};
            const contextScope = Object.assign({}, row.context_scope || {});
            return {
              heartbeat_task_id: String(row.heartbeat_task_id || "").trim(),
              title: String(row.title || row.heartbeat_task_id || "").trim(),
              enabled: _coerceBoolClient(row.enabled, true),
              channel_name: String(row.channel_name || row.channelName || channelName).trim(),
              session_id: String(row.session_id || row.sessionId || sid).trim(),
              preset_key: String(row.preset_key || "ops_inspection").trim() || "ops_inspection",
              prompt_template: String(row.prompt_template || "").trim(),
              schedule_type: String(row.schedule_type || "interval").trim() === "daily" ? "daily" : "interval",
              interval_minutes: Math.max(5, Number(row.interval_minutes || 120)),
              daily_time: String(row.daily_time || "09:30").trim() || "09:30",
              weekdays: normalizeHeartbeatWeekdaysClient(row.weekdays),
              busy_policy: String(row.busy_policy || "run_on_next_idle").trim() || "run_on_next_idle",
              max_execute_count: Math.max(0, Number(row.max_execute_count || row.maxExecuteCount || 0)),
              context_scope: {
                recent_tasks_limit: Math.max(0, Number(contextScope.recent_tasks_limit || 10)),
                recent_runs_limit: Math.max(0, Number(contextScope.recent_runs_limit || 10)),
                include_task_counts: _coerceBoolClient(contextScope.include_task_counts, true),
                include_recent_tasks: _coerceBoolClient(contextScope.include_recent_tasks, true),
                include_recent_runs: _coerceBoolClient(contextScope.include_recent_runs, true),
              },
            };
          }).filter((row) => !!row.heartbeat_task_id),
        },
      };
    }

    function buildSessionHeartbeatPayloadForSessionSave() {
      const baseProjectId = String(SESSION_INFO_UI.projectId || STATE.project || "").trim();
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const draft = SESSION_INFO_UI.heartbeatDraft || null;
      let tasks = (Array.isArray(SESSION_INFO_UI.heartbeatTasks) ? SESSION_INFO_UI.heartbeatTasks.slice() : [])
        .filter((task) => inferConversationHeartbeatTaskSourceScope(task, sid) !== "project");
      const existingTaskIds = new Set(
        tasks
          .map((task) => String(task && task.heartbeat_task_id || "").trim())
          .filter(Boolean)
      );
      if (draft) {
        const heartbeatTaskId = String(draft.heartbeatTaskId || "").trim().replace(/[^a-zA-Z0-9._-]+/g, "-");
        // 普通会话保存只允许覆写已存在的会话级任务，不能把默认草稿新建进真源。
        if (heartbeatTaskId && existingTaskIds.has(heartbeatTaskId)) {
          const normalized = normalizeHeartbeatTaskClient({
            heartbeat_task_id: heartbeatTaskId,
            title: String(draft.title || "").trim() || heartbeatTaskId,
            enabled: _coerceBoolClient(draft.enabled, true),
            source_scope: "session",
            preset_key: String(draft.presetKey || "ops_inspection").trim(),
            prompt_template: String(draft.promptTemplate || "").trim(),
            schedule_type: String(draft.scheduleType || "interval").trim(),
            interval_minutes: Math.max(5, Number(draft.intervalMinutes || 120)),
            daily_time: String(draft.dailyTime || "09:30").trim() || "09:30",
            weekdays: normalizeHeartbeatWeekdaysClient(draft.weekdays),
            busy_policy: String(draft.busyPolicy || "run_on_next_idle").trim(),
            max_execute_count: Math.max(0, Number(draft.maxExecuteCount || 0)),
            context_scope: {
              recent_tasks_limit: Math.max(0, Number(draft.contextScope && draft.contextScope.recentTasksLimit || 10)),
              recent_runs_limit: Math.max(0, Number(draft.contextScope && draft.contextScope.recentRunsLimit || 10)),
              include_task_counts: _coerceBoolClient(draft.contextScope && draft.contextScope.includeTaskCounts, true),
              include_recent_tasks: _coerceBoolClient(draft.contextScope && draft.contextScope.includeRecentTasks, true),
              include_recent_runs: _coerceBoolClient(draft.contextScope && draft.contextScope.includeRecentRuns, true),
            },
            channel_name: String(SESSION_INFO_UI.base && SESSION_INFO_UI.base.channel_name || "").trim(),
            session_id: sid,
          }, baseProjectId);
          tasks = tasks.filter((row) => String(row && row.heartbeat_task_id || "").trim() !== heartbeatTaskId);
          tasks.unshift(normalized);
        }
      }
      const channelName = String(SESSION_INFO_UI.base && SESSION_INFO_UI.base.channel_name || "").trim();
      const enabledCount = tasks.filter((row) => _coerceBoolClient(row && row.enabled, false)).length;
      return {
        heartbeat: {
          enabled: enabledCount > 0,
          tasks: tasks.map((task) => {
            const row = (task && typeof task === "object") ? task : {};
            const contextScope = Object.assign({}, row.context_scope || {});
            return {
              heartbeat_task_id: String(row.heartbeat_task_id || "").trim(),
              title: String(row.title || row.heartbeat_task_id || "").trim(),
              enabled: _coerceBoolClient(row.enabled, true),
              channel_name: String(row.channel_name || row.channelName || channelName).trim(),
              session_id: String(row.session_id || row.sessionId || sid).trim(),
              preset_key: String(row.preset_key || "ops_inspection").trim() || "ops_inspection",
              prompt_template: String(row.prompt_template || "").trim(),
              schedule_type: String(row.schedule_type || "interval").trim() === "daily" ? "daily" : "interval",
              interval_minutes: Math.max(5, Number(row.interval_minutes || 120)),
              daily_time: String(row.daily_time || "09:30").trim() || "09:30",
              weekdays: normalizeHeartbeatWeekdaysClient(row.weekdays),
              busy_policy: String(row.busy_policy || "run_on_next_idle").trim() || "run_on_next_idle",
              max_execute_count: Math.max(0, Number(row.max_execute_count || row.maxExecuteCount || 0)),
              context_scope: {
                recent_tasks_limit: Math.max(0, Number(contextScope.recent_tasks_limit || 10)),
                recent_runs_limit: Math.max(0, Number(contextScope.recent_runs_limit || 10)),
                include_task_counts: _coerceBoolClient(contextScope.include_task_counts, true),
                include_recent_tasks: _coerceBoolClient(contextScope.include_recent_tasks, true),
                include_recent_runs: _coerceBoolClient(contextScope.include_recent_runs, true),
              },
            };
          }).filter((row) => !!row.heartbeat_task_id),
        },
      };
    }

    async function reloadConversationSessionHeartbeat(preferredTaskId = "") {
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      if (!looksLikeSessionId(sid)) return false;
      const resp = await fetch("/api/sessions/" + encodeURIComponent(sid), {
        cache: "no-store",
        headers: authHeaders(),
      });
      const payload = await resp.json().catch(() => null);
      if (!resp.ok) {
        throw new Error(String(responseErrorDetailFromJson(payload, "读取会话心跳任务失败（HTTP " + resp.status + "）")));
      }
      SESSION_INFO_UI.base = normalizeSessionInfoResponse(payload, SESSION_INFO_UI.base);
      if (typeof mergeConversationSessionDetailIntoStore === "function") {
        mergeConversationSessionDetailIntoStore(SESSION_INFO_UI.base, sid);
      }
      applySessionHeartbeatPayload(payload, preferredTaskId);
      syncConversationHeartbeatSummaryToStore(sid, SESSION_INFO_UI.heartbeatSummary, SESSION_INFO_UI.heartbeatTasks);
      return true;
    }

    async function saveConversationSessionHeartbeatDraft() {
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const draft = SESSION_INFO_UI.heartbeatDraft || null;
      if (!looksLikeSessionId(sid)) throw new Error("会话ID无效");
      if (!draft) throw new Error("当前没有可保存的心跳任务草稿");
      const heartbeatTaskId = String(draft.heartbeatTaskId || "").trim().replace(/[^a-zA-Z0-9._-]+/g, "-");
      if (!heartbeatTaskId) throw new Error("heartbeat_task_id 不能为空");
      const promptTemplate = String(draft.promptTemplate || "").trim();
      if (!promptTemplate) throw new Error("自定义提示词不能为空");
      const normalized = normalizeHeartbeatTaskClient({
        heartbeat_task_id: heartbeatTaskId,
        title: String(draft.title || "").trim() || heartbeatTaskId,
        enabled: _coerceBoolClient(draft.enabled, true),
        source_scope: "session",
        preset_key: String(draft.presetKey || "ops_inspection").trim(),
        prompt_template: promptTemplate,
        schedule_type: String(draft.scheduleType || "interval").trim(),
        interval_minutes: Math.max(5, Number(draft.intervalMinutes || 120)),
        daily_time: String(draft.dailyTime || "09:30").trim() || "09:30",
        weekdays: normalizeHeartbeatWeekdaysClient(draft.weekdays),
        busy_policy: String(draft.busyPolicy || "run_on_next_idle").trim(),
        max_execute_count: Math.max(0, Number(draft.maxExecuteCount || 0)),
        context_scope: {
          recent_tasks_limit: Math.max(0, Number(draft.contextScope && draft.contextScope.recentTasksLimit || 10)),
          recent_runs_limit: Math.max(0, Number(draft.contextScope && draft.contextScope.recentRunsLimit || 10)),
          include_task_counts: _coerceBoolClient(draft.contextScope && draft.contextScope.includeTaskCounts, true),
          include_recent_tasks: _coerceBoolClient(draft.contextScope && draft.contextScope.includeRecentTasks, true),
          include_recent_runs: _coerceBoolClient(draft.contextScope && draft.contextScope.includeRecentRuns, true),
        },
        channel_name: String(SESSION_INFO_UI.base && SESSION_INFO_UI.base.channel_name || "").trim(),
        session_id: sid,
      }, String(SESSION_INFO_UI.projectId || STATE.project || "").trim());
      const existed = Array.isArray(SESSION_INFO_UI.heartbeatTasks) ? SESSION_INFO_UI.heartbeatTasks.slice() : [];
      const nextTasks = existed.filter((row) => String(row.heartbeat_task_id || "").trim() !== heartbeatTaskId);
      nextTasks.unshift(normalized);
      SESSION_INFO_UI.heartbeatTasks = nextTasks;
      const payload = buildSessionHeartbeatPayloadFromDrafts();
      const resp = await fetch("/api/sessions/" + encodeURIComponent(sid), {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      const detail = await parseResponseDetail(resp);
      if (!resp.ok) {
        throw new Error(String(detail || "保存心跳任务失败（HTTP " + resp.status + "）"));
      }
      await reloadConversationSessionHeartbeat(heartbeatTaskId);
      return detail;
    }

    async function runConversationSessionHeartbeatTaskNow(heartbeatTaskId) {
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      if (!looksLikeSessionId(sid) || !tid) throw new Error("缺少 heartbeat_task_id");
      const resp = await fetch(
        "/api/sessions/" + encodeURIComponent(sid) + "/heartbeat-tasks/" + encodeURIComponent(tid) + "/run-now",
        {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({}),
        }
      );
      const detail = await parseResponseDetail(resp);
      if (!resp.ok) throw new Error(String(detail || "触发心跳任务失败（HTTP " + resp.status + "）"));
      return detail && typeof detail === "object" ? detail : {};
    }

    async function deleteConversationSessionHeartbeatTask(heartbeatTaskId) {
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      if (!looksLikeSessionId(sid) || !tid) throw new Error("缺少 heartbeat_task_id");
      const resp = await fetch(
        "/api/sessions/" + encodeURIComponent(sid) + "/heartbeat-tasks/" + encodeURIComponent(tid) + "/delete",
        {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({}),
        }
      );
      const detail = await parseResponseDetail(resp);
      if (!resp.ok) throw new Error(String(detail || "删除心跳任务失败（HTTP " + resp.status + "）"));
      const key = sessionHeartbeatTaskKey(sid, tid);
      if (key) {
        delete SESSION_INFO_UI.heartbeatHistoryByTask[key];
        delete SESSION_INFO_UI.heartbeatHistoryLoadingByTask[key];
        delete SESSION_INFO_UI.heartbeatHistoryErrorByTask[key];
        delete SESSION_INFO_UI.heartbeatActionByTask[key];
      }
      await reloadConversationSessionHeartbeat("");
      return detail && typeof detail === "object" ? detail : {};
    }

    async function ensureConversationSessionHeartbeatHistory(heartbeatTaskId, force = false) {
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      const key = sessionHeartbeatTaskKey(sid, tid);
      if (!key) return [];
      if (!force && SESSION_INFO_UI.heartbeatHistoryByTask[key] && Array.isArray(SESSION_INFO_UI.heartbeatHistoryByTask[key].items)) {
        return SESSION_INFO_UI.heartbeatHistoryByTask[key].items;
      }
      if (SESSION_INFO_UI.heartbeatHistoryLoadingByTask[key]) {
        return (SESSION_INFO_UI.heartbeatHistoryByTask[key] && SESSION_INFO_UI.heartbeatHistoryByTask[key].items) || [];
      }
      SESSION_INFO_UI.heartbeatHistoryLoadingByTask[key] = true;
      SESSION_INFO_UI.heartbeatHistoryErrorByTask[key] = "";
      try {
        const resp = await fetch(
          "/api/sessions/" + encodeURIComponent(sid) + "/heartbeat-tasks/" + encodeURIComponent(tid) + "/history?limit=20",
          {
            headers: authHeaders({}),
            cache: "no-store",
          }
        );
        const payload = await resp.json().catch(() => null);
        if (!resp.ok) throw new Error(String(responseErrorDetailFromJson(payload, "获取心跳任务历史失败（HTTP " + resp.status + "）")));
        const data = (payload && typeof payload === "object") ? payload : {};
        const items = Array.isArray(data.items) ? data.items : [];
        SESSION_INFO_UI.heartbeatHistoryByTask[key] = {
          items,
          fetchedAt: new Date().toISOString(),
        };
        return items;
      } catch (e) {
        SESSION_INFO_UI.heartbeatHistoryErrorByTask[key] = e && e.message ? String(e.message) : "获取历史失败";
        return (SESSION_INFO_UI.heartbeatHistoryByTask[key] && SESSION_INFO_UI.heartbeatHistoryByTask[key].items) || [];
      } finally {
        SESSION_INFO_UI.heartbeatHistoryLoadingByTask[key] = false;
      }
    }

    function buildConversationHeartbeatSection(opts = {}) {
      const sid = String(opts.sessionId || "").trim();
      const base = (opts.base && typeof opts.base === "object") ? opts.base : {};
      const loading = !!opts.loading;
      const heartbeatSaving = !!opts.heartbeatSaving;
      const heartbeatMeta = opts.heartbeatMeta || normalizeSessionHeartbeatMeta({}, []);
      const heartbeatSummary = opts.heartbeatSummary || normalizeHeartbeatSummaryClient({}, []);
      const heartbeatTasks = Array.isArray(opts.heartbeatTasks) ? opts.heartbeatTasks : [];
      const heartbeatErr = String(opts.heartbeatError || "").trim();
      const heartbeatNote = String(opts.heartbeatNote || "").trim();
      const tasksCount = Math.max(0, Number(heartbeatSummary.total_count || heartbeatMeta.count || heartbeatTasks.length || 0));
      const enabledCount = Math.max(0, Number(heartbeatSummary.enabled_count || heartbeatMeta.enabled_count || heartbeatTasks.filter((task) => _coerceBoolClient(task && task.enabled, false)).length || 0));
      const latestTriggeredAt = sessionHeartbeatLatestTriggeredAt(heartbeatTasks, heartbeatSummary);
      const nextDueAt = sessionHeartbeatNextDueAt(heartbeatTasks, heartbeatSummary);

      const heartbeat = el("section", { class: "conv-session-info-block conv-session-heartbeat-block" });
      heartbeat.appendChild(el("div", { class: "conv-session-info-title", text: "Agent 心跳任务（主入口）" }));
      heartbeat.appendChild(el("div", {
        class: "project-auto-card-desc",
        text: "这里汇总会话级任务和已分配给本 Agent 的项目级任务；项目级任务可在此查看与执行，但需回到项目入口修改定义。",
      }));

      const topBar = el("div", { class: "conv-heartbeat-summary-top" });
      const topFacts = el("div", { class: "project-auto-top-facts conv-heartbeat-summary-facts" });
      [
        ["任务总数", String(tasksCount) + " 条"],
        ["已启用", String(enabledCount) + " 条"],
        ["最近执行", latestTriggeredAt ? compactDateTime(latestTriggeredAt) : "暂无"],
        ["下一次", nextDueAt ? compactDateTime(nextDueAt) : "待计算"],
      ].forEach(([k, v]) => {
        const item = el("div", { class: "project-auto-top-fact" });
        item.appendChild(el("span", { class: "k", text: k }));
        item.appendChild(el("span", { class: "v", text: v }));
        topFacts.appendChild(item);
      });
      topBar.appendChild(topFacts);
      const topActions = el("div", { class: "project-auto-target-actions-inline conv-heartbeat-summary-actions" });
      topActions.appendChild(chip(enabledCount > 0 ? ("已启用 " + enabledCount) : "未启用", enabledCount > 0 ? "good" : "muted"));
      if (Array.isArray(heartbeatMeta.errors) && heartbeatMeta.errors.length) {
        topActions.appendChild(chip("告警 " + heartbeatMeta.errors.length, "bad"));
      }
      const addBtn = el("button", { class: "btn primary", type: "button", text: "新增任务" });
      addBtn.disabled = loading || heartbeatSaving;
      addBtn.addEventListener("click", () => openConversationHeartbeatTaskEditor(null));
      topActions.appendChild(addBtn);
      topBar.appendChild(topActions);
      heartbeat.appendChild(topBar);

      if (heartbeatErr) {
        heartbeat.appendChild(el("div", { class: "project-auto-error", text: "心跳任务失败：" + heartbeatErr }));
      } else if (heartbeatNote) {
        heartbeat.appendChild(el("div", { class: "project-auto-tip", text: heartbeatNote }));
      }

      const listWrap = el("div", { class: "project-auto-target-list heartbeat-task-list conv-heartbeat-task-list" });
      heartbeatTasks.forEach((task) => {
        const taskId = String(task.heartbeat_task_id || "").trim();
        const sourceScope = String(task.source_scope || "").trim();
        const isProjectAssigned = sourceScope === "project";
        const row = el("div", {
          class: "project-auto-target-row heartbeat-task-row" + (_coerceBoolClient(task.enabled, false) ? "" : " is-disabled"),
        });
        const meta = el("div", { class: "project-auto-target-meta" });
        meta.appendChild(el("div", {
          class: "project-auto-target-name",
          text: String(task.title || taskId) + (task.pending_job ? "（待执行）" : ""),
        }));
        const descParts = [
          "ID: " + (taskId || "-"),
          isProjectAssigned ? "来源: 项目分配" : "来源: 会话配置",
          heartbeatScheduleSummary(task),
          heartbeatBusyPolicyLabel(task.busy_policy),
          task.next_due_at ? ("下次: " + compactDateTime(task.next_due_at)) : "下次: -",
        ];
        const limitText = heartbeatTaskExecuteLimitInlineText(task);
        if (limitText) descParts.push(limitText);
        meta.appendChild(el("div", {
          class: "project-auto-target-desc",
          text: descParts.join(" · "),
        }));
        row.appendChild(meta);

        const actions = el("div", { class: "project-auto-target-actions-inline conv-heartbeat-row-actions" });
        actions.appendChild(chip(heartbeatTaskStateLabel(task), heartbeatTaskStateTone(task)));
        if (isProjectAssigned) {
          actions.appendChild(chip("项目分配", "muted"));
        }

        const toggleBtn = el("button", {
          type: "button",
          class: "project-auto-slider conv-heartbeat-mini-toggle" + (_coerceBoolClient(task.enabled, false) ? " on" : ""),
          role: "switch",
          "aria-checked": _coerceBoolClient(task.enabled, false) ? "true" : "false",
          "aria-label": String(task.title || taskId || "心跳任务") + "启停",
          title: _coerceBoolClient(task.enabled, false) ? "已开启" : "已关闭",
        });
        toggleBtn.disabled = loading || heartbeatSaving || isProjectAssigned;
        toggleBtn.appendChild(el("span", { class: "project-auto-slider-knob", "aria-hidden": "true" }));
        toggleBtn.addEventListener("click", async (e) => {
          e.preventDefault();
          try {
            SESSION_INFO_UI.heartbeatSaving = true;
            SESSION_INFO_UI.heartbeatError = "";
            SESSION_INFO_UI.heartbeatDraft = buildSessionHeartbeatTaskDraft(task, heartbeatMeta);
            SESSION_INFO_UI.heartbeatDraft.enabled = !_coerceBoolClient(task.enabled, false);
            renderConversationSessionInfoModal();
            await saveConversationSessionHeartbeatDraft();
            SESSION_INFO_UI.heartbeatNote = String(task.title || taskId || "心跳任务") + (SESSION_INFO_UI.heartbeatDraft.enabled ? " 已开启" : " 已关闭");
          } catch (err) {
            SESSION_INFO_UI.heartbeatError = err && err.message ? String(err.message) : "更新心跳任务开关失败";
          } finally {
            SESSION_INFO_UI.heartbeatSaving = false;
            renderConversationSessionInfoModal();
          }
        });
        actions.appendChild(toggleBtn);

        const editBtn = el("button", { class: "btn", type: "button", text: isProjectAssigned ? "查看" : "编辑" });
        editBtn.disabled = loading || heartbeatSaving;
        editBtn.addEventListener("click", () => openConversationHeartbeatTaskEditor(task));
        actions.appendChild(editBtn);

        const runBtn = el("button", { class: "btn", type: "button", text: "立即执行" });
        runBtn.disabled = loading || heartbeatSaving || !task.ready;
        runBtn.addEventListener("click", async () => {
          try {
            SESSION_INFO_UI.heartbeatActionByTask[sessionHeartbeatTaskKey(sid, taskId)] = "running";
            SESSION_INFO_UI.heartbeatError = "";
            renderConversationSessionInfoModal();
            const data = await runConversationSessionHeartbeatTaskNow(taskId);
            SESSION_INFO_UI.heartbeatNote = "已触发心跳任务：" + taskId + " · run " + String(((data && data.record) || {}).run_id || "-");
            await reloadConversationSessionHeartbeat(taskId);
          } catch (err) {
            SESSION_INFO_UI.heartbeatError = err && err.message ? String(err.message) : "触发心跳任务失败";
          } finally {
            delete SESSION_INFO_UI.heartbeatActionByTask[sessionHeartbeatTaskKey(sid, taskId)];
            renderConversationSessionInfoModal();
          }
        });
        actions.appendChild(runBtn);

        const historyBtn = el("button", { class: "btn", type: "button", text: "记录 " + Math.max(0, Number(task.history_count || 0)) + " 条" });
        historyBtn.disabled = loading || heartbeatSaving;
        historyBtn.addEventListener("click", async () => {
          SESSION_INFO_UI.heartbeatHistoryTaskId = taskId;
          await ensureConversationSessionHeartbeatHistory(taskId, true);
          openConversationHeartbeatTaskEditor(task, "history");
        });
        actions.appendChild(historyBtn);

        row.appendChild(actions);
        listWrap.appendChild(row);
      });
      heartbeat.appendChild(
        buildProjectAutoInputField(
          "任务列表",
          listWrap.childNodes.length
            ? listWrap
            : el("div", { class: "project-auto-record-empty", text: "当前会话还没有心跳任务，点击右上角新增即可创建。" }),
          "每条任务独立启停、独立调度、独立留痕。"
        )
      );
      return heartbeat;
    }

    function buildConversationHeartbeatTaskEditorOverlay(opts = {}) {
      const loading = !!opts.loading;
      const heartbeatSaving = !!opts.heartbeatSaving;
      const base = (opts.base && typeof opts.base === "object") ? opts.base : {};
      const sid = String(opts.sessionId || "").trim();
      const heartbeatMeta = opts.heartbeatMeta || normalizeSessionHeartbeatMeta({}, []);
      const heartbeatSummary = opts.heartbeatSummary || normalizeHeartbeatSummaryClient({}, []);
      const heartbeatTasks = Array.isArray(opts.heartbeatTasks) ? opts.heartbeatTasks : [];
      const heartbeatDraft = SESSION_INFO_UI.heartbeatDraft || syncSessionHeartbeatDraft();
      const draftTaskId = String((heartbeatDraft && heartbeatDraft.heartbeatTaskId) || "").trim();
      const selectedHeartbeatTaskId = String(SESSION_INFO_UI.heartbeatHistoryTaskId || draftTaskId || "").trim();
      const editorMode = String(SESSION_INFO_UI.heartbeatTaskEditorMode || "edit").trim() === "history" ? "history" : "edit";
      const currentTask = heartbeatTasks.find((task) => String(task && task.heartbeat_task_id || "").trim() === selectedHeartbeatTaskId)
        || heartbeatTasks.find((task) => String(task && task.heartbeat_task_id || "").trim() === draftTaskId)
        || null;
      const currentTaskIsProjectAssigned = !!(currentTask && String(currentTask.source_scope || "").trim() === "project");

      const backdrop = el("div", { class: "conv-heartbeat-editor-backdrop" });
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) closeConversationHeartbeatTaskEditor();
      });
      const card = el("section", { class: "conv-heartbeat-editor-modal" });
      backdrop.appendChild(card);

      const head = el("div", { class: "conv-heartbeat-editor-head" });
      const headText = el("div", { class: "conv-heartbeat-editor-headtext" });
      headText.appendChild(el("div", {
        class: "conv-heartbeat-editor-title",
        text: editorMode === "history"
          ? ("执行记录" + (selectedHeartbeatTaskId ? " · " + selectedHeartbeatTaskId : ""))
          : (heartbeatTasks.some((task) => String(task.heartbeat_task_id || "").trim() === draftTaskId) ? "编辑心跳任务" : "新增心跳任务"),
      }));
      headText.appendChild(el("div", {
        class: "conv-heartbeat-editor-sub",
        text: editorMode === "history"
          ? "当前优先展示执行记录；如需改配置，可切换到编辑态。"
          : "详细配置、单任务启停、立即执行和历史记录均在这里维护。",
      }));
      head.appendChild(headText);
      if (editorMode === "history" && currentTask) {
        const editModeBtn = el("button", { class: "btn", type: "button", text: "切到编辑" });
        editModeBtn.addEventListener("click", (e) => {
          e.preventDefault();
          SESSION_INFO_UI.heartbeatTaskEditorMode = "edit";
          SESSION_INFO_UI.heartbeatDraft = buildSessionHeartbeatTaskDraft(currentTask, heartbeatMeta);
          renderConversationSessionInfoModal();
        });
        head.appendChild(editModeBtn);
      }
      const closeBtn = el("button", { class: "btn", type: "button", text: "关闭" });
      closeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        closeConversationHeartbeatTaskEditor();
      });
      head.appendChild(closeBtn);
      card.appendChild(head);
      const body = el("div", { class: "project-auto-form conv-heartbeat-editor-body" });
      if (editorMode === "history" && currentTask) {
        const currentSummary = el("div", { class: "project-auto-summary-card" });
        currentSummary.appendChild(el("div", {
          class: "project-auto-summary-title",
          text: String(currentTask.title || selectedHeartbeatTaskId || "心跳任务"),
        }));
        currentSummary.appendChild(el("div", {
          class: "project-auto-card-desc",
          text: [
            "ID: " + String(currentTask.heartbeat_task_id || "-"),
            currentTaskIsProjectAssigned ? "来源: 项目分配" : "来源: 会话配置",
            heartbeatScheduleSummary(currentTask),
            heartbeatBusyPolicyLabel(currentTask.busy_policy),
            currentTask.next_due_at ? ("下次: " + compactDateTime(currentTask.next_due_at)) : "下次: -",
          ].join(" · "),
        }));
        body.appendChild(currentSummary);
      }
      if (editorMode !== "history") {
        const switchWrap = buildProjectAutoSliderToggle({
          checked: !!(heartbeatDraft && heartbeatDraft.enabled),
          disabled: loading || heartbeatSaving || currentTaskIsProjectAssigned,
          ariaLabel: "单任务启停开关",
          titleOn: "当前任务已启用",
          titleOff: "当前任务已关闭",
          subOn: "到点后会进入执行队列。",
          subOff: "关闭后保留任务定义与历史，但不会继续触发。",
          extraLine: "会话总状态由任务级启用数量自动派生，不再单独维护总开关。",
          onToggle: (nextVal) => {
            if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
            SESSION_INFO_UI.heartbeatDraft.enabled = !!nextVal;
            renderConversationSessionInfoModal();
          },
        });
        body.appendChild(switchWrap);
        if (currentTaskIsProjectAssigned) {
          body.appendChild(el("div", {
            class: "project-auto-tip",
            text: "该任务来自项目级分配，当前弹框只提供查看、立即执行和记录回看；如需修改定义，请到项目心跳任务入口调整。",
          }));
        }
      }
      body.appendChild(buildConversationHeartbeatLimitStatusCard(currentTask, heartbeatDraft));
      if (editorMode === "history" && !selectedHeartbeatTaskId) {
        body.appendChild(el("div", { class: "project-auto-record-empty", text: "当前还没有可查看的执行记录。" }));
      }
      if (editorMode !== "history") {
      const hbTaskIdInput = el("input", {
        class: "project-auto-input",
        value: String((heartbeatDraft && heartbeatDraft.heartbeatTaskId) || ""),
        placeholder: "例如 ops-daily",
      });
      hbTaskIdInput.disabled = loading || heartbeatSaving;
      hbTaskIdInput.addEventListener("change", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.heartbeatTaskId = String(hbTaskIdInput.value || "").trim().replace(/[^a-zA-Z0-9._-]+/g, "-");
      });
      body.appendChild(buildProjectAutoInputField("任务 ID", hbTaskIdInput, "当前会话内唯一；建议使用稳定命名。"));

      const hbTitleInput = el("input", {
        class: "project-auto-input",
        value: String((heartbeatDraft && heartbeatDraft.title) || ""),
        placeholder: "例如 每日巡查",
      });
      hbTitleInput.disabled = loading || heartbeatSaving;
      hbTitleInput.addEventListener("input", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.title = String(hbTitleInput.value || "").trim();
      });
      body.appendChild(buildProjectAutoInputField("任务标题", hbTitleInput, ""));

      const hbPresetSel = el("select", { class: "project-auto-select", "aria-label": "心跳任务模板" });
      HEARTBEAT_PRESET_OPTIONS.forEach(([value, label]) => {
        const opt = el("option", { value, text: label });
        if (String((heartbeatDraft && heartbeatDraft.presetKey) || "") === value) opt.selected = true;
        hbPresetSel.appendChild(opt);
      });
      hbPresetSel.disabled = loading || heartbeatSaving;
      hbPresetSel.addEventListener("change", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.presetKey = String(hbPresetSel.value || "").trim();
      });
      body.appendChild(buildProjectAutoSelectField("任务模板", hbPresetSel, "内置模板负责约束默认输出口径。"));

      const hbScheduleRow = el("div", { class: "project-auto-inline-grid" });
      const hbScheduleSel = el("select", { class: "project-auto-select", "aria-label": "心跳任务调度方式" });
      HEARTBEAT_SCHEDULE_OPTIONS.forEach(([value, label]) => {
        const opt = el("option", { value, text: label });
        if (String((heartbeatDraft && heartbeatDraft.scheduleType) || "") === value) opt.selected = true;
        hbScheduleSel.appendChild(opt);
      });
      hbScheduleSel.disabled = loading || heartbeatSaving;
      hbScheduleSel.addEventListener("change", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.scheduleType = String(hbScheduleSel.value || "interval").trim();
        renderConversationSessionInfoModal();
      });
      hbScheduleRow.appendChild(buildProjectAutoInputField("执行方式", hbScheduleSel, ""));
      if (String((heartbeatDraft && heartbeatDraft.scheduleType) || "") === "daily") {
        const hbDailyInput = el("input", {
          class: "project-auto-input",
          type: "time",
          value: String((heartbeatDraft && heartbeatDraft.dailyTime) || "09:30"),
        });
        hbDailyInput.disabled = loading || heartbeatSaving;
        hbDailyInput.addEventListener("change", () => {
          if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
          SESSION_INFO_UI.heartbeatDraft.dailyTime = String(hbDailyInput.value || "09:30").trim() || "09:30";
        });
        hbScheduleRow.appendChild(buildProjectAutoInputField("执行时点", hbDailyInput, ""));
      } else {
        const hbIntervalInput = el("input", {
          class: "project-auto-input",
          type: "number",
          min: "5",
          step: "5",
          value: String(Math.max(5, Number((heartbeatDraft && heartbeatDraft.intervalMinutes) || 120))),
        });
        hbIntervalInput.disabled = loading || heartbeatSaving;
        hbIntervalInput.addEventListener("change", () => {
          if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
          SESSION_INFO_UI.heartbeatDraft.intervalMinutes = Math.max(5, Number(hbIntervalInput.value || 120));
        });
        hbScheduleRow.appendChild(buildProjectAutoInputField("执行间隔（分钟）", hbIntervalInput, ""));
      }
      body.appendChild(hbScheduleRow);

      const hbWeekdayWrap = el("div", { class: "project-auto-targets heartbeat-weekdays" });
      HEARTBEAT_WEEKDAY_LABELS.forEach((label, idx) => {
        const weekday = idx + 1;
        const row = el("label", { class: "project-auto-target-item" });
        const input = el("input", { type: "checkbox" });
        input.checked = normalizeHeartbeatWeekdaysClient(heartbeatDraft && heartbeatDraft.weekdays).includes(weekday);
        input.disabled = loading || heartbeatSaving || String((heartbeatDraft && heartbeatDraft.scheduleType) || "") !== "daily";
        input.addEventListener("change", () => {
          if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
          const current = normalizeHeartbeatWeekdaysClient(SESSION_INFO_UI.heartbeatDraft.weekdays);
          const next = input.checked ? current.concat([weekday]) : current.filter((n) => n !== weekday);
          SESSION_INFO_UI.heartbeatDraft.weekdays = normalizeHeartbeatWeekdaysClient(next);
        });
        row.appendChild(input);
        row.appendChild(el("span", { text: "周" + label }));
        hbWeekdayWrap.appendChild(row);
      });
      body.appendChild(buildProjectAutoInputField(
        "生效日",
        hbWeekdayWrap,
        String((heartbeatDraft && heartbeatDraft.scheduleType) || "") === "daily" ? "默认工作日，可按需要增删。" : "仅每日定时模式生效。"
      ));

      const hbBusySel = el("select", { class: "project-auto-select", "aria-label": "忙碌策略" });
      HEARTBEAT_BUSY_POLICY_OPTIONS.forEach(([value, label]) => {
        const opt = el("option", { value, text: label });
        if (String((heartbeatDraft && heartbeatDraft.busyPolicy) || "") === value) opt.selected = true;
        hbBusySel.appendChild(opt);
      });
      hbBusySel.disabled = loading || heartbeatSaving;
      hbBusySel.addEventListener("change", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.busyPolicy = String(hbBusySel.value || "run_on_next_idle").trim();
      });
      body.appendChild(buildProjectAutoSelectField("忙碌策略", hbBusySel, "推荐优先使用“忙碌时顺延”。"));

      const hbMaxExecuteInput = el("input", {
        class: "project-auto-input",
        type: "number",
        min: "0",
        step: "1",
        value: heartbeatDraftMaxExecuteInputValue(heartbeatDraft),
        placeholder: "留空或 0 表示不限",
      });
      hbMaxExecuteInput.disabled = loading || heartbeatSaving || currentTaskIsProjectAssigned;
      const assignMaxExecuteCount = () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        const raw = String(hbMaxExecuteInput.value || "").trim();
        SESSION_INFO_UI.heartbeatDraft.maxExecuteCount = raw ? Math.max(0, Number(raw || 0)) : 0;
      };
      hbMaxExecuteInput.addEventListener("input", assignMaxExecuteCount);
      hbMaxExecuteInput.addEventListener("change", () => {
        assignMaxExecuteCount();
        renderConversationSessionInfoModal();
      });
      body.appendChild(buildProjectAutoInputField(
        "最大执行次数",
        hbMaxExecuteInput,
        "0 或留空 = 不限制；只统计自动调度终态次数，`run-now` 不计入。"
      ));

      const hbPromptInput = el("textarea", {
        class: "project-auto-textarea",
        placeholder: "补充这条心跳任务的具体目标、排查重点、输出要求。",
      });
      hbPromptInput.value = String((heartbeatDraft && heartbeatDraft.promptTemplate) || "");
      hbPromptInput.disabled = loading || heartbeatSaving;
      hbPromptInput.addEventListener("input", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.promptTemplate = String(hbPromptInput.value || "").trim();
      });
      body.appendChild(buildProjectAutoInputField("自定义提示词", hbPromptInput, "建议写清结论格式、风险点和动作要求。"));

      const hbContextWrap = el("div", { class: "project-auto-targets" });
      [
        ["includeTaskCounts", "任务计数"],
        ["includeRecentTasks", "最近任务"],
        ["includeRecentRuns", "最近运行"],
      ].forEach(([key, label]) => {
        const item = el("label", { class: "project-auto-target-item" });
        const input = el("input", { type: "checkbox" });
        input.checked = _coerceBoolClient(heartbeatDraft && heartbeatDraft.contextScope && heartbeatDraft.contextScope[key], true);
        input.disabled = loading || heartbeatSaving;
        input.addEventListener("change", () => {
          if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
          const patch = {};
          patch[key] = !!input.checked;
          SESSION_INFO_UI.heartbeatDraft.contextScope = Object.assign({}, SESSION_INFO_UI.heartbeatDraft.contextScope || {}, patch);
        });
        item.appendChild(input);
        item.appendChild(el("span", { text: label }));
        hbContextWrap.appendChild(item);
      });
      body.appendChild(buildProjectAutoInputField("附带上下文", hbContextWrap, ""));

      const hbContextRow = el("div", { class: "project-auto-inline-grid" });
      const hbRecentTasksInput = el("input", {
        class: "project-auto-input",
        type: "number",
        min: "0",
        step: "1",
        value: String(Math.max(0, Number(heartbeatDraft && heartbeatDraft.contextScope && heartbeatDraft.contextScope.recentTasksLimit) || 10)),
      });
      hbRecentTasksInput.disabled = loading || heartbeatSaving;
      hbRecentTasksInput.addEventListener("change", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.contextScope = Object.assign({}, SESSION_INFO_UI.heartbeatDraft.contextScope || {}, {
          recentTasksLimit: Math.max(0, Number(hbRecentTasksInput.value || 10)),
        });
      });
      hbContextRow.appendChild(buildProjectAutoInputField("最近任务数", hbRecentTasksInput, ""));
      const hbRecentRunsInput = el("input", {
        class: "project-auto-input",
        type: "number",
        min: "0",
        step: "1",
        value: String(Math.max(0, Number(heartbeatDraft && heartbeatDraft.contextScope && heartbeatDraft.contextScope.recentRunsLimit) || 10)),
      });
      hbRecentRunsInput.disabled = loading || heartbeatSaving;
      hbRecentRunsInput.addEventListener("change", () => {
        if (!SESSION_INFO_UI.heartbeatDraft) syncSessionHeartbeatDraft();
        SESSION_INFO_UI.heartbeatDraft.contextScope = Object.assign({}, SESSION_INFO_UI.heartbeatDraft.contextScope || {}, {
          recentRunsLimit: Math.max(0, Number(hbRecentRunsInput.value || 10)),
        });
      });
      hbContextRow.appendChild(buildProjectAutoInputField("最近运行数", hbRecentRunsInput, ""));
      body.appendChild(hbContextRow);

      const actionRow = el("div", { class: "project-auto-target-actions-inline conv-heartbeat-editor-actions" });
      const saveBtn = el("button", { class: "btn primary", type: "button", text: heartbeatSaving ? "保存中..." : "保存任务" });
      saveBtn.disabled = loading || heartbeatSaving || currentTaskIsProjectAssigned;
      saveBtn.addEventListener("click", async () => {
        try {
          SESSION_INFO_UI.heartbeatSaving = true;
          SESSION_INFO_UI.heartbeatError = "";
          SESSION_INFO_UI.heartbeatNote = "";
          renderConversationSessionInfoModal();
          await saveConversationSessionHeartbeatDraft();
          SESSION_INFO_UI.heartbeatHistoryTaskId = String((SESSION_INFO_UI.heartbeatDraft && SESSION_INFO_UI.heartbeatDraft.heartbeatTaskId) || "").trim();
          SESSION_INFO_UI.heartbeatNote = "已保存心跳任务：" + (draftTaskId || "-");
        } catch (err) {
          SESSION_INFO_UI.heartbeatError = err && err.message ? String(err.message) : "保存心跳任务失败";
        } finally {
          SESSION_INFO_UI.heartbeatSaving = false;
          renderConversationSessionInfoModal();
        }
      });
      actionRow.appendChild(saveBtn);

      const resetBtn = el("button", { class: "btn", type: "button", text: "重置" });
      resetBtn.disabled = loading || heartbeatSaving || currentTaskIsProjectAssigned;
      resetBtn.addEventListener("click", () => {
        SESSION_INFO_UI.heartbeatDraft = defaultSessionHeartbeatTaskDraft(base);
        SESSION_INFO_UI.heartbeatDraft.heartbeatEnabled = !!(heartbeatSummary.enabled_count > 0 || heartbeatMeta.enabled);
        renderConversationSessionInfoModal();
      });
      actionRow.appendChild(resetBtn);

      const runBtn = el("button", { class: "btn", type: "button", text: "立即执行" });
      runBtn.disabled = loading || heartbeatSaving || !draftTaskId;
      runBtn.addEventListener("click", async () => {
        try {
          SESSION_INFO_UI.heartbeatActionByTask[sessionHeartbeatTaskKey(sid, draftTaskId)] = "running";
          SESSION_INFO_UI.heartbeatError = "";
          renderConversationSessionInfoModal();
          const data = await runConversationSessionHeartbeatTaskNow(draftTaskId);
          SESSION_INFO_UI.heartbeatNote = "已触发心跳任务：" + draftTaskId + " · run " + String(((data && data.record) || {}).run_id || "-");
          await reloadConversationSessionHeartbeat(draftTaskId);
          await ensureConversationSessionHeartbeatHistory(draftTaskId, true);
        } catch (err) {
          SESSION_INFO_UI.heartbeatError = err && err.message ? String(err.message) : "触发心跳任务失败";
        } finally {
          delete SESSION_INFO_UI.heartbeatActionByTask[sessionHeartbeatTaskKey(sid, draftTaskId)];
          renderConversationSessionInfoModal();
        }
      });
      actionRow.appendChild(runBtn);

      const deleteBtn = el("button", { class: "btn", type: "button", text: "删除任务" });
      deleteBtn.disabled = loading || heartbeatSaving || !draftTaskId || currentTaskIsProjectAssigned;
      deleteBtn.addEventListener("click", async () => {
        try {
          SESSION_INFO_UI.heartbeatSaving = true;
          SESSION_INFO_UI.heartbeatError = "";
          renderConversationSessionInfoModal();
          await deleteConversationSessionHeartbeatTask(draftTaskId);
          SESSION_INFO_UI.heartbeatDraft = defaultSessionHeartbeatTaskDraft(base);
          SESSION_INFO_UI.heartbeatTaskEditorOpen = false;
          SESSION_INFO_UI.heartbeatNote = "已删除心跳任务：" + draftTaskId;
        } catch (err) {
          SESSION_INFO_UI.heartbeatError = err && err.message ? String(err.message) : "删除心跳任务失败";
        } finally {
          SESSION_INFO_UI.heartbeatSaving = false;
          renderConversationSessionInfoModal();
        }
      });
      actionRow.appendChild(deleteBtn);
      body.appendChild(actionRow);
      }

      if (selectedHeartbeatTaskId) {
        const historyKey = sessionHeartbeatTaskKey(sid, selectedHeartbeatTaskId);
        const historyPayload = SESSION_INFO_UI.heartbeatHistoryByTask[historyKey] || {};
        const historyItems = Array.isArray(historyPayload.items) ? historyPayload.items : [];
        const historyWrap = el("div", { class: "project-auto-records" });
        const historyTop = el("div", { class: "project-auto-records-head" });
        historyTop.appendChild(el("div", {
          class: "project-auto-records-title",
          text: "执行记录 · " + selectedHeartbeatTaskId,
        }));
        const refreshHistoryBtn = el("button", {
          class: "btn",
          type: "button",
          text: SESSION_INFO_UI.heartbeatHistoryLoadingByTask[historyKey] ? "刷新中..." : "刷新记录",
        });
        refreshHistoryBtn.disabled = !!SESSION_INFO_UI.heartbeatHistoryLoadingByTask[historyKey];
        refreshHistoryBtn.addEventListener("click", async () => {
          await ensureConversationSessionHeartbeatHistory(selectedHeartbeatTaskId, true);
          renderConversationSessionInfoModal();
        });
        historyTop.appendChild(refreshHistoryBtn);
        historyWrap.appendChild(historyTop);
        const historyErr = String(SESSION_INFO_UI.heartbeatHistoryErrorByTask[historyKey] || "").trim();
        if (historyErr) {
          historyWrap.appendChild(el("div", { class: "project-auto-error", text: "记录读取失败：" + historyErr }));
        } else if (!historyItems.length) {
          historyWrap.appendChild(el("div", { class: "project-auto-record-empty", text: "当前尚无执行记录，可先手动执行一次。" }));
        } else {
          const list = el("div", { class: "project-auto-record-list" });
          historyItems.forEach((record) => {
            const statusClass = String((record && (record.result || record.status)) || "").trim().toLowerCase() || "idle";
            const item = el("div", { class: "project-auto-record-item status-" + statusClass });
            const top = el("div", { class: "project-auto-record-top" });
            top.appendChild(chip(heartbeatTaskStateLabel(record), heartbeatTaskStateTone(record)));
            top.appendChild(el("span", { class: "project-auto-record-time", text: formatTsOrDash(record && record.triggered_at) }));
            item.appendChild(top);
            item.appendChild(el("div", {
              class: "project-auto-record-summary",
              text: [
                "触发: " + String((record && record.trigger) || "-"),
                "job: " + String((record && record.job_id) || "-"),
                "run: " + String((record && record.run_id) || "-"),
              ].join(" · "),
            }));
            if (record && record.error) {
              item.appendChild(el("div", { class: "project-auto-record-reason", text: "错误：" + String(record.error || "") }));
            }
            list.appendChild(item);
          });
          historyWrap.appendChild(list);
        }
        body.appendChild(historyWrap);
      }
      if (editorMode !== "history" && currentTaskIsProjectAssigned) {
        Array.from(body.querySelectorAll("input, textarea, select")).forEach((node) => {
          node.disabled = true;
        });
      }
      card.appendChild(body);
      return backdrop;
    }

    function setConversationSessionInfoError(msg) {
      SESSION_INFO_UI.error = String(msg || "");
      const errEl = document.getElementById("convSessionInfoErr");
      if (!errEl) return;
      errEl.textContent = SESSION_INFO_UI.error;
      errEl.style.display = SESSION_INFO_UI.error ? "block" : "none";
    }

    function responseErrorDetailFromJson(payload, fallbackText = "") {
      const src = (payload && typeof payload === "object") ? payload : {};
      const detail = src && (src.detail || src.error || src.message);
      if (detail && typeof detail === "object") {
        return String(detail.error || detail.message || JSON.stringify(detail) || fallbackText || "");
      }
      return String(detail || fallbackText || "");
    }

    function closeConversationSessionInfoModal() {
      SESSION_INFO_UI.open = false;
      SESSION_INFO_UI.loading = false;
      SESSION_INFO_UI.saving = false;
      SESSION_INFO_UI.heartbeatSaving = false;
      SESSION_INFO_UI.avatarPickerOpen = false;
      SESSION_INFO_UI.avatarPickerDraftId = "";
      SESSION_INFO_UI.sessionId = "";
      SESSION_INFO_UI.projectId = "";
      SESSION_INFO_UI.base = null;
      SESSION_INFO_UI.form = null;
      SESSION_INFO_UI.error = "";
      SESSION_INFO_UI.heartbeatError = "";
      SESSION_INFO_UI.heartbeatNote = "";
      SESSION_INFO_UI.heartbeatMeta = null;
      SESSION_INFO_UI.heartbeatSummary = null;
      SESSION_INFO_UI.heartbeatTasks = [];
      SESSION_INFO_UI.heartbeatDraft = null;
      SESSION_INFO_UI.heartbeatTaskEditorOpen = false;
      SESSION_INFO_UI.heartbeatTaskEditorMode = "edit";
      SESSION_INFO_UI.heartbeatHistoryByTask = Object.create(null);
      SESSION_INFO_UI.heartbeatHistoryLoadingByTask = Object.create(null);
      SESSION_INFO_UI.heartbeatHistoryErrorByTask = Object.create(null);
      SESSION_INFO_UI.heartbeatHistoryTaskId = "";
      SESSION_INFO_UI.heartbeatActionByTask = Object.create(null);
      const mask = document.getElementById("convSessionInfoMask");
      if (mask) mask.classList.remove("show");
      const avatarMask = document.getElementById("convAvatarPickerMask");
      if (avatarMask) avatarMask.classList.remove("show");
      setConversationSessionInfoError("");
    }

    function setConversationAvatarPickerError(msg) {
      const errEl = document.getElementById("convAvatarPickerErr");
      if (!errEl) return;
      const text = String(msg || "").trim();
      errEl.textContent = text;
      errEl.style.display = text ? "block" : "none";
    }

    function openConversationAvatarPicker() {
      if (!SESSION_INFO_UI.open) return;
      SESSION_INFO_UI.avatarPickerOpen = true;
      SESSION_INFO_UI.avatarPickerDraftId = String((SESSION_INFO_UI.form && SESSION_INFO_UI.form.avatar_id) || "").trim();
      const mask = document.getElementById("convAvatarPickerMask");
      if (mask) mask.classList.add("show");
      renderConversationAvatarPickerModal();
    }

    function closeConversationAvatarPicker() {
      SESSION_INFO_UI.avatarPickerOpen = false;
      SESSION_INFO_UI.avatarPickerDraftId = "";
      const mask = document.getElementById("convAvatarPickerMask");
      if (mask) mask.classList.remove("show");
      setConversationAvatarPickerError("");
    }

    function persistConversationAvatarAssignment(sessionId, avatarId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return;
      const nextAvatarId = String(avatarId || "").trim();
      const store = getConversationAvatarStoreV2();
      const bySessionId = Object.assign(Object.create(null), store.bySessionId || {});
      const clearedSessionIds = Object.assign(Object.create(null), store.clearedSessionIds || {});
      if (nextAvatarId && CONVERSATION_AVATAR_MAP.has(nextAvatarId)) {
        bySessionId[sid] = nextAvatarId;
        delete clearedSessionIds[sid];
      } else {
        delete bySessionId[sid];
        clearedSessionIds[sid] = true;
      }
      saveConversationAvatarStoreV2({ bySessionId, clearedSessionIds });
    }

    function avatarUsageCountById(projectId = "", ignoreSessionId = "") {
      const usage = Object.create(null);
      const pid = String(projectId || "").trim();
      const sidIgnore = String(ignoreSessionId || "").trim();
      const store = getConversationAvatarStoreV2();
      const bySessionId = (store && store.bySessionId) || {};
      const sessions = Array.isArray(PCONV.sessionDirectoryByProject[pid]) ? PCONV.sessionDirectoryByProject[pid] : [];
      const knownIds = new Set(sessions.map((item) => String(getSessionId(item) || item.sessionId || item.id || "").trim()).filter(Boolean));
      Object.keys(bySessionId).forEach((sid) => {
        const avatarId = String(bySessionId[sid] || "").trim();
        if (!avatarId || sid === sidIgnore) return;
        if (knownIds.size && !knownIds.has(sid)) return;
        usage[avatarId] = (usage[avatarId] || 0) + 1;
      });
      return usage;
    }

    function renderConversationAvatarPickerModal() {
      const body = document.getElementById("convAvatarPickerBody");
      const sub = document.getElementById("convAvatarPickerSub");
      const confirmBtn = document.getElementById("convAvatarPickerConfirmBtn");
      if (!body || !sub || !confirmBtn) return;
      setConversationAvatarPickerError("");
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const projectId = String(SESSION_INFO_UI.projectId || "").trim();
      const base = SESSION_INFO_UI.base || {};
      const draftAvatarId = String(SESSION_INFO_UI.avatarPickerDraftId || "").trim();
      const usage = avatarUsageCountById(projectId, sid);
      sub.textContent = sid ? ("Session: " + sid) : "为当前会话分配一个更易识别的头像";
      confirmBtn.disabled = !SESSION_INFO_UI.avatarPickerOpen;
      body.innerHTML = "";
      if (!SESSION_INFO_UI.avatarPickerOpen || !sid) {
        body.appendChild(el("div", { class: "hint", text: "当前未打开头像选择。" }));
        return;
      }
      const wrap = el("div", { class: "conv-avatar-picker" });
      const current = el("div", { class: "conv-avatar-picker-current" });
      current.appendChild(buildConversationAvatarNode(base, { large: true, avatarId: draftAvatarId }));
      const currentText = el("div", { class: "conv-avatar-picker-current-text" });
      currentText.appendChild(el("div", { class: "conv-avatar-picker-title", text: draftAvatarId ? "已选头像" : "当前为默认占位头像" }));
      currentText.appendChild(el("div", {
        class: "conv-avatar-picker-sub",
        text: draftAvatarId && CONVERSATION_AVATAR_MAP.has(draftAvatarId)
          ? ("当前选择：" + String((CONVERSATION_AVATAR_MAP.get(draftAvatarId) || {}).name || draftAvatarId))
          : "未指定专属头像时，将继续显示默认渐变占位头像。",
      }));
      current.appendChild(currentText);
      wrap.appendChild(current);
      const grid = el("div", { class: "conv-avatar-picker-grid" });
      CONVERSATION_AVATAR_CATALOG.forEach((avatar) => {
        const avatarId = String(avatar.id || "").trim();
        const selected = avatarId && avatarId === draftAvatarId;
        const count = Number(usage[avatarId] || 0);
        const card = el("button", {
          type: "button",
          class: "conv-avatar-option" + (selected ? " selected" : ""),
          title: String(avatar.name || avatarId),
        });
        card.addEventListener("click", (e) => {
          e.preventDefault();
          SESSION_INFO_UI.avatarPickerDraftId = avatarId;
          renderConversationAvatarPickerModal();
        });
        const head = el("div", { class: "conv-avatar-option-head" });
        head.appendChild(buildConversationAvatarNode(base, { avatarId }));
        head.appendChild(el("span", {
          class: "conv-avatar-option-usage" + (count > 0 ? " busy" : ""),
          text: count > 0 ? ("已用 " + count) : "未占用",
        }));
        card.appendChild(head);
        const info = el("div", { class: "conv-avatar-option-info" });
        info.appendChild(el("div", { class: "conv-avatar-option-name", text: String(avatar.name || avatarId) }));
        info.appendChild(el("div", { class: "conv-avatar-option-desc", text: selected ? "当前会话已选中该头像。" : "点击选择后，将写回会话编辑弹框预览区。" }));
        card.appendChild(info);
        grid.appendChild(card);
      });
      wrap.appendChild(grid);
      body.appendChild(wrap);
    }

    async function saveConversationSessionInfo() {
      if (!SESSION_INFO_UI.open || SESSION_INFO_UI.saving) return;
      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      if (!looksLikeSessionId(sid)) return;
      const form = SESSION_INFO_UI.form || {};
      const cliType = String(form.cli_type || "codex").trim().toLowerCase() || "codex";
      const payload = {
        alias: String(form.alias || "").trim(),
        channel_name: String(form.channel_name || "").trim(),
        cli_type: cliType,
        model: normalizeSessionModel(form.model),
        reasoning_effort: cliType === "codex" ? normalizeReasoningEffort(form.reasoning_effort) : "",
      };
      // 历史 status 兼容逻辑由后端统一迁移，前端编辑弹框不再直接改写该字段。
      const heartbeatPayload = buildSessionHeartbeatPayloadForSessionSave();
      if (heartbeatPayload && heartbeatPayload.heartbeat) {
        payload.heartbeat = heartbeatPayload.heartbeat;
      }
      if (!payload.channel_name) {
        setConversationSessionInfoError("通道名称不能为空。");
        return;
      }
      SESSION_INFO_UI.saving = true;
      renderConversationSessionInfoModal();
      try {
        const resp = await fetch("/api/sessions/" + encodeURIComponent(sid), {
          method: "PUT",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        const resultPayload = await resp.json().catch(() => null);
        if (!resp.ok) {
          setConversationSessionInfoError(String(responseErrorDetailFromJson(resultPayload, "保存失败（HTTP " + resp.status + "）")));
          SESSION_INFO_UI.saving = false;
          renderConversationSessionInfoModal();
          return;
        }
        const updated = normalizeSessionInfoResponse(resultPayload, {
          ...(SESSION_INFO_UI.base || {}),
          sessionId: sid,
          runtime_state: SESSION_INFO_UI.base && SESSION_INFO_UI.base.runtime_state,
        });
        persistConversationAvatarAssignment(sid, form.avatar_id);
        SESSION_INFO_UI.base = updated;
        for (let i = 0; i < PCONV.sessions.length; i++) {
          const row = PCONV.sessions[i];
          if (String(getSessionId(row) || "").trim() !== sid) continue;
          const nextDisplayName = firstNonEmptyText([
            updated.alias,
            updated.display_name,
            updated.channel_name,
            row.displayName,
            row.displayChannel,
          ]);
          PCONV.sessions[i] = normalizeConversationSession({
            ...(row || {}),
            id: sid,
            sessionId: sid,
            alias: updated.alias,
            channel_name: updated.channel_name,
            environment: updated.environment,
            worktree_root: updated.worktree_root,
            workdir: updated.workdir,
            branch: updated.branch,
            primaryChannel: updated.channel_name,
            display_name: nextDisplayName,
            displayNameSource: updated.display_name_source,
            codexTitle: updated.codex_title,
            cli_type: updated.cli_type,
            model: updated.model,
            reasoning_effort: updated.reasoning_effort,
            status: updated.status,
            is_primary: updated.is_primary,
            source: updated.source || row.source,
            created_at: updated.created_at || row.created_at,
            last_used_at: updated.last_used_at || row.last_used_at,
            runtime_state: updated.runtime_state || row.runtime_state,
            heartbeat_summary: normalizeHeartbeatSummaryClient(
              SESSION_INFO_UI.heartbeatSummary || {},
              Array.isArray(SESSION_INFO_UI.heartbeatTasks) ? SESSION_INFO_UI.heartbeatTasks : []
            ),
            project_execution_context: (updated && updated.project_execution_context) || (row && row.project_execution_context) || null,
            task_tracking: hasConversationTaskTrackingData(updated && updated.task_tracking)
              ? updated.task_tracking
              : (row && row.task_tracking),
          }) || row;
          break;
        }
        closeConversationSessionInfoModal();
        setHintText(STATE.panelMode, "会话信息已保存。");
        render();
      } catch (_) {
        setConversationSessionInfoError("保存失败：网络或服务异常。");
        SESSION_INFO_UI.saving = false;
        renderConversationSessionInfoModal();
      }
    }

    function renderConversationSessionInfoModal() {
      const body = document.getElementById("convSessionInfoBody");
      const saveBtn = document.getElementById("convSessionInfoSaveBtn");
      const sub = document.getElementById("convSessionInfoSub");
      const statusSlot = document.getElementById("convSessionInfoStatusSlot");
      if (!body || !saveBtn || !sub || !statusSlot) return;

      const sid = String(SESSION_INFO_UI.sessionId || "").trim();
      const base = SESSION_INFO_UI.base || {};
      const form = SESSION_INFO_UI.form || {};
      const saving = !!SESSION_INFO_UI.saving;
      const loading = !!SESSION_INFO_UI.loading;

      sub.textContent = sid ? ("Session: " + sid) : "-";
      saveBtn.disabled = loading || saving || !sid;
      saveBtn.textContent = saving ? "保存中..." : "保存";
      setConversationSessionInfoError(SESSION_INFO_UI.error);
      statusSlot.innerHTML = "";

      body.innerHTML = "";
      if (loading) {
        body.appendChild(el("div", { class: "hint", text: "正在加载会话信息..." }));
        return;
      }
      if (!sid || !base || !Object.keys(base).length) {
        body.appendChild(el("div", { class: "hint", text: "未获取到会话信息。" }));
        return;
      }

      const wrap = el("div", { class: "conv-session-info" });
      const addKv = (host, k, v, asCode = false) => {
        host.appendChild(el("div", { class: "conv-session-k", text: String(k || "") }));
        const val = el("div", { class: "conv-session-v" });
        if (asCode) val.appendChild(el("code", { text: String(v || "-") }));
        else val.textContent = String(v || "-");
        host.appendChild(val);
      };

      const basic = el("section", { class: "conv-session-info-block" });
      basic.appendChild(el("div", { class: "conv-session-info-title", text: "基础信息（只读）" }));
      const basicKv = el("div", { class: "conv-session-kv" });
      addKv(basicKv, "会话类型", normalizeCliTypeLabel(base.cli_type || "codex"));
      addKv(basicKv, "会话ID", sid, true);
      addKv(basicKv, "展示名", firstNonEmptyText([base.display_name], "-"));
      addKv(basicKv, "展示来源", firstNonEmptyText([base.display_name_source], "-"));
      addKv(basicKv, "主会话", base.is_primary ? "是" : "否");
      addKv(basicKv, "来源", firstNonEmptyText([base.source], "-"));
      addKv(basicKv, "创建时间", compactDateTime(base.created_at) || "-");
      addKv(basicKv, "最近使用", compactDateTime(base.last_used_at) || "-");
      basic.appendChild(basicKv);
      wrap.appendChild(basic);

      const execContext = buildProjectExecutionContextMeta(base.project_execution_context || null);
      const targetRef = normalizeProjectExecutionContextRef(execContext.target || null);
      const primaryContext = {
        environment: normalizeSessionEnvironmentValue(
          firstNonEmptyText([targetRef.environment, base.environment, form.environment], "stable")
        ),
        worktree_root: firstNonEmptyText([targetRef.worktree_root, base.worktree_root, form.worktree_root], ""),
        workdir: firstNonEmptyText([targetRef.workdir, base.workdir, form.workdir], ""),
        branch: firstNonEmptyText([targetRef.branch, base.branch, form.branch], ""),
      };
      const legacyContext = {
        environment: normalizeSessionEnvironmentValue(base.environment || form.environment || "stable"),
        worktree_root: firstNonEmptyText([base.worktree_root], ""),
        workdir: firstNonEmptyText([base.workdir], ""),
        branch: firstNonEmptyText([base.branch], ""),
      };
      const legacyMismatchFields = [];
      [["环境", "environment"], ["worktree", "worktree_root"], ["workdir", "workdir"], ["branch", "branch"]].forEach(([label, key]) => {
        const primaryValue = String(primaryContext[key] || "").trim();
        const legacyValue = String(legacyContext[key] || "").trim();
        if (primaryValue && legacyValue && primaryValue !== legacyValue) legacyMismatchFields.push(label);
      });

      const context = el("section", { class: "conv-session-info-block" });
      context.appendChild(el("div", { class: "conv-session-info-title", text: "项目执行上下文（主展示）" }));
      const contextSummary = el("div", { class: "conv-session-exec-summary" });
      contextSummary.appendChild(el("span", {
        class: "detail-context-chip exec-source " + String((execContext.sourceMeta && execContext.sourceMeta.tone) || "muted"),
        text: execContext.available
          ? ("主真源: " + String((execContext.sourceMeta && execContext.sourceMeta.text) || "待返回"))
          : "主真源: 会话字段回退",
      }));
      if (legacyMismatchFields.length) {
        contextSummary.appendChild(el("span", {
          class: "detail-context-chip warn",
          text: "旧字段已降级: " + legacyMismatchFields.join(" / "),
          title: "当前主展示优先使用 project_execution_context；旧 session 字段仅保留为兼容信息。",
        }));
      }
      context.appendChild(contextSummary);
      const contextKv = el("div", { class: "conv-session-kv" });
      addKv(contextKv, "环境", primaryContext.environment);
      addKv(contextKv, "worktree", firstNonEmptyText([primaryContext.worktree_root], "-"), true);
      addKv(contextKv, "workdir", firstNonEmptyText([primaryContext.workdir], "-"), true);
      addKv(contextKv, "branch", firstNonEmptyText([primaryContext.branch], "-"), true);
      context.appendChild(contextKv);
      wrap.appendChild(context);

      const compatibility = el("section", { class: "conv-session-info-block" });
      compatibility.appendChild(el("div", { class: "conv-session-info-title", text: "兼容 / 历史字段（只读）" }));
      compatibility.appendChild(el("div", {
        class: "conv-session-exec-empty",
        text: "以下字段仅用于兼容旧链路或排查历史漂移，不再作为当前主展示真源；/api/sessions/bindings 与绑定写入入口当前统一降级为兼容管理入口，只服务兼容维护与历史排查。",
      }));
      const compatibilityKv = el("div", { class: "conv-session-kv" });
      addKv(compatibilityKv, "环境", legacyContext.environment);
      addKv(compatibilityKv, "worktree", firstNonEmptyText([legacyContext.worktree_root], "-"), true);
      addKv(compatibilityKv, "workdir", firstNonEmptyText([legacyContext.workdir], "-"), true);
      addKv(compatibilityKv, "branch", firstNonEmptyText([legacyContext.branch], "-"), true);
      compatibility.appendChild(compatibilityKv);
      wrap.appendChild(compatibility);

      const inheritance = el("section", { class: "conv-session-info-block" });
      inheritance.appendChild(el("div", { class: "conv-session-info-title", text: "上下文来源 / 继承关系（只读）" }));
      if (!execContext.available) {
        inheritance.appendChild(el("div", {
          class: "conv-session-exec-empty",
          text: "当前接口未返回 project_execution_context；前端已预留展示位，待服务端字段透出后显示。",
        }));
      } else {
        const summary = el("div", { class: "conv-session-exec-summary" });
        summary.appendChild(el("span", {
          class: "detail-context-chip exec-source " + String((execContext.sourceMeta && execContext.sourceMeta.tone) || "muted"),
          text: "来源: " + String((execContext.sourceMeta && execContext.sourceMeta.text) || "待返回"),
        }));
        if (execContext.overrideApplied && execContext.overrideFieldsText) {
          summary.appendChild(el("span", {
            class: "detail-context-chip exec-override warn",
            text: "已覆写: " + execContext.overrideFieldsText,
          }));
          summary.appendChild(el("span", {
            class: "detail-context-chip exec-override-source " + String((execContext.overrideSourceMeta && execContext.overrideSourceMeta.tone) || "muted"),
            text: "覆盖来源: " + String((execContext.overrideSourceMeta && execContext.overrideSourceMeta.text) || "待返回"),
          }));
        }
        inheritance.appendChild(summary);

        const execGrid = el("div", { class: "conv-session-exec-grid" });
        const addExecCol = (title, ref) => {
          const col = el("div", { class: "conv-session-exec-col" });
          col.appendChild(el("div", { class: "conv-session-exec-col-title", text: title }));
          const refKv = el("div", { class: "conv-session-kv" });
          addKv(refKv, "项目", firstNonEmptyText([ref.project_id], "-"));
          addKv(refKv, "通道", firstNonEmptyText([ref.channel_name], "-"));
          addKv(refKv, "会话", firstNonEmptyText([ref.session_id], "-"), !!ref.session_id);
          if (ref.run_id) addKv(refKv, "Run", ref.run_id, true);
          addKv(refKv, "环境", firstNonEmptyText([ref.environment], "-"));
          addKv(refKv, "worktree", firstNonEmptyText([ref.worktree_root], "-"), !!ref.worktree_root);
          addKv(refKv, "workdir", firstNonEmptyText([ref.workdir], "-"), !!ref.workdir);
          addKv(refKv, "branch", firstNonEmptyText([ref.branch], "-"), !!ref.branch);
          col.appendChild(refKv);
          return col;
        };
        execGrid.appendChild(addExecCol("目标上下文", execContext.target || {}));
        execGrid.appendChild(addExecCol("来源上下文", execContext.source || {}));
        inheritance.appendChild(execGrid);
      }
      wrap.appendChild(inheritance);

      const runtime = el("section", { class: "conv-session-info-block" });
      runtime.appendChild(el("div", { class: "conv-session-info-title", text: "运行状态（只读）" }));
      const runtimeKv = el("div", { class: "conv-session-kv" });
      const rt = normalizeRuntimeState(base.runtime_state || null);
      addKv(runtimeKv, "展示状态", statusLabel(rt.display_state, { queueDepth: rt.queue_depth }));
      addKv(runtimeKv, "内部状态", rt.internal_state || "-");
      addKv(runtimeKv, "外部占用", rt.external_busy ? "是" : "否");
      addKv(runtimeKv, "活跃Run", rt.active_run_id ? shortId(rt.active_run_id) : "-");
      addKv(runtimeKv, "排队Run", rt.queued_run_id ? shortId(rt.queued_run_id) : "-");
      addKv(runtimeKv, "队列深度", String(Number(rt.queue_depth || 0)));
      addKv(runtimeKv, "状态更新时间", compactDateTime(rt.updated_at) || "-");
      runtime.appendChild(runtimeKv);
      wrap.appendChild(runtime);

      const editor = el("section", { class: "conv-session-info-block" });
      editor.appendChild(el("div", { class: "conv-session-info-title", text: "可编辑配置（会话身份）" }));
      const formNode = el("div", { class: "conv-session-form" });
      const mkField = (labelText, inputNode) => {
        const field = el("div", { class: "conv-session-field" });
        field.appendChild(el("label", { text: labelText }));
        field.appendChild(inputNode);
        return field;
      };

      const avatarConfig = el("div", { class: "conv-session-avatar-config" });
      const avatarMain = el("div", { class: "conv-session-avatar-main" });
      avatarMain.appendChild(buildConversationAvatarNode(base, { large: true, avatarId: String(form.avatar_id || "").trim() }));
      const avatarMeta = el("div", { class: "conv-session-avatar-meta" });
      const avatarLabel = String(form.avatar_id || "").trim() && CONVERSATION_AVATAR_MAP.has(String(form.avatar_id || "").trim())
        ? String((CONVERSATION_AVATAR_MAP.get(String(form.avatar_id || "").trim()) || {}).name || form.avatar_id)
        : "默认占位头像";
      avatarMeta.appendChild(el("div", { class: "conv-session-avatar-label", text: avatarLabel }));
      avatarMeta.appendChild(el("div", {
        class: "conv-session-avatar-sub",
        text: String(form.avatar_id || "").trim()
          ? "头像将优先按当前 session_id 精确命中，刷新后对话列表、详情头部同步生效。"
          : "当前未设置专属头像，将继续使用默认渐变占位头像。",
      }));
      avatarMain.appendChild(avatarMeta);
      avatarConfig.appendChild(avatarMain);
      const avatarActions = el("div", { class: "conv-session-avatar-actions" });
      const chooseAvatarBtn = el("button", { class: "btn", type: "button", text: "选择头像" });
      chooseAvatarBtn.addEventListener("click", (e) => {
        e.preventDefault();
        openConversationAvatarPicker();
      });
      avatarActions.appendChild(chooseAvatarBtn);
      const clearAvatarBtn = el("button", { class: "btn", type: "button", text: "清除头像" });
      clearAvatarBtn.disabled = !String(form.avatar_id || "").trim();
      clearAvatarBtn.addEventListener("click", (e) => {
        e.preventDefault();
        form.avatar_id = "";
        renderConversationSessionInfoModal();
      });
      avatarActions.appendChild(clearAvatarBtn);
      const avatarLinks = getAvatarLibraryLinks();
      const openAvatarLibBtn = el("button", { class: "btn", type: "button", text: "打开头像库" });
      openAvatarLibBtn.addEventListener("click", (e) => {
        e.preventDefault();
        try {
          window.open(String(avatarLinks.primary), "_blank", "noopener,noreferrer");
        } catch (_) {}
      });
      avatarActions.appendChild(openAvatarLibBtn);
      avatarConfig.appendChild(avatarActions);
      formNode.appendChild(mkField("头像配置", avatarConfig));

      const aliasInput = el("input", { class: "input", value: String(form.alias || "") });
      aliasInput.addEventListener("input", () => { form.alias = String(aliasInput.value || ""); });
      formNode.appendChild(mkField("对话agent名称（alias）", aliasInput));

      const channelSel = el("select", { class: "input" });
      const channelOptions = unionChannelNames(SESSION_INFO_UI.projectId || STATE.project || "");
      const currentChannel = String(form.channel_name || "").trim();
      const optionSet = new Set();
      if (Array.isArray(channelOptions)) {
        channelOptions.forEach((name) => {
          const v = String(name || "").trim();
          if (!v || optionSet.has(v)) return;
          optionSet.add(v);
          channelSel.appendChild(el("option", { value: v, text: v }));
        });
      }
      if (currentChannel && !optionSet.has(currentChannel)) {
        channelSel.appendChild(el("option", { value: currentChannel, text: currentChannel + "（历史）" }));
      }
      if (!channelSel.childNodes.length) {
        channelSel.appendChild(el("option", { value: "", text: "无可选通道" }));
        channelSel.disabled = true;
      }
      if (currentChannel) {
        channelSel.value = currentChannel;
      } else if (channelSel.options && channelSel.options.length) {
        channelSel.selectedIndex = 0;
        form.channel_name = String(channelSel.value || "");
      }
      channelSel.addEventListener("change", () => { form.channel_name = String(channelSel.value || ""); });
      formNode.appendChild(mkField("所属通道（channel_name）", channelSel));

      const modelInput = el("input", {
        class: "input",
        value: String(form.model || ""),
        placeholder: modelInputPlaceholderByCli(form.cli_type || base.cli_type || "codex"),
      });
      modelInput.addEventListener("input", () => { form.model = String(modelInput.value || ""); });
      formNode.appendChild(mkField("模型（model）", modelInput));

      const reasoningField = el("div", { class: "conv-session-field" });
      reasoningField.appendChild(el("label", { text: "推理强度（reasoning_effort，仅 codex）" }));
      const reasoningSel = el("select", { class: "input" });
      reasoningSel.appendChild(el("option", { value: "", text: "默认" }));
      reasoningSel.appendChild(el("option", { value: "low", text: "low" }));
      reasoningSel.appendChild(el("option", { value: "medium", text: "medium" }));
      reasoningSel.appendChild(el("option", { value: "high", text: "high" }));
      reasoningSel.appendChild(el("option", { value: "xhigh", text: "xhigh" }));
      reasoningSel.value = normalizeReasoningEffort(form.reasoning_effort);
      reasoningSel.addEventListener("change", () => { form.reasoning_effort = String(reasoningSel.value || ""); });
      reasoningField.appendChild(reasoningSel);
      formNode.appendChild(reasoningField);

      const syncFormByCli = () => {
        const cliType = String(form.cli_type || base.cli_type || "codex").trim().toLowerCase() || "codex";
        form.cli_type = cliType;
        modelInput.placeholder = modelInputPlaceholderByCli(cliType);
        reasoningField.style.display = cliType === "codex" ? "" : "none";
        if (cliType !== "codex") {
          form.reasoning_effort = "";
          reasoningSel.value = "";
        }
      };
      syncFormByCli();

      const sessionScopeNote = el("section", { class: "conv-session-info-block" });
      sessionScopeNote.appendChild(el("div", { class: "conv-session-info-title", text: "项目 / 会话职责边界" }));
      sessionScopeNote.appendChild(el("div", {
        class: "conv-session-exec-empty",
        text: "项目执行上下文现在以项目配置为唯一默认真源；当前会话弹框仅编辑会话身份信息。运行状态请看上方“运行状态（只读）”；环境、worktree、workdir、branch 已降级为只读继承结果；历史 status 兼容逻辑如仍存在，将由后端统一迁移处理，不在此处手动编辑。",
      }));
      if (execContext.overrideApplied && execContext.overrideFieldsText) {
        const overrideSummary = el("div", { class: "conv-session-exec-summary" });
        overrideSummary.appendChild(el("span", {
          class: "detail-context-chip exec-override warn",
          text: "当前会话存在特例覆盖: " + execContext.overrideFieldsText,
        }));
        sessionScopeNote.appendChild(overrideSummary);
      }
      formNode.appendChild(sessionScopeNote);

      editor.appendChild(formNode);
      wrap.appendChild(editor);

      const heartbeat = buildConversationHeartbeatSection({
        sessionId: sid,
        base,
        loading,
        heartbeatSaving: !!SESSION_INFO_UI.heartbeatSaving,
        heartbeatMeta: SESSION_INFO_UI.heartbeatMeta || normalizeSessionHeartbeatMeta({}, []),
        heartbeatSummary: SESSION_INFO_UI.heartbeatSummary || normalizeHeartbeatSummaryClient({}, []),
        heartbeatTasks: Array.isArray(SESSION_INFO_UI.heartbeatTasks) ? SESSION_INFO_UI.heartbeatTasks : [],
        heartbeatError: SESSION_INFO_UI.heartbeatError,
        heartbeatNote: SESSION_INFO_UI.heartbeatNote,
      });
      wrap.appendChild(heartbeat);
      body.appendChild(wrap);
      if (SESSION_INFO_UI.heartbeatTaskEditorOpen) {
        body.appendChild(buildConversationHeartbeatTaskEditorOverlay({
          sessionId: sid,
          base,
          loading,
          heartbeatSaving: !!SESSION_INFO_UI.heartbeatSaving,
          heartbeatMeta: SESSION_INFO_UI.heartbeatMeta || normalizeSessionHeartbeatMeta({}, []),
          heartbeatSummary: SESSION_INFO_UI.heartbeatSummary || normalizeHeartbeatSummaryClient({}, []),
          heartbeatTasks: Array.isArray(SESSION_INFO_UI.heartbeatTasks) ? SESSION_INFO_UI.heartbeatTasks : [],
        }));
      }

      const statusWrap = el("div", { class: "conv-session-status-wrap" });
      statusWrap.appendChild(chip("运行态只读", "muted"));
      statusWrap.appendChild(el("span", {
        class: "conv-session-status-note",
        text: "运行状态请看上方只读区；是否参与路由由后端统一处理。历史 status 兼容逻辑如仍存在，也不会在这里手动编辑。",
      }));
      statusSlot.appendChild(statusWrap);
    }
