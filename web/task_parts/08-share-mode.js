    const TASK_SHARE_MODE = {
      requested: false,
      active: false,
      params: null,
      bootstrap: null,
      sessionPayloadById: Object.create(null),
      sessionLoadedAtById: Object.create(null),
      error: "",
      sending: false,
    };

    function taskShareModeText(value, fallback = "") {
      const text = String(value == null ? "" : value).trim();
      return text || fallback;
    }

    function taskShareModeFirst(values, fallback = "") {
      const list = Array.isArray(values) ? values : [values];
      for (const value of list) {
        const text = taskShareModeText(value);
        if (text) return text;
      }
      return fallback;
    }

    function taskShareModeReadParams() {
      const params = new URLSearchParams(window.location.search || "");
      return {
        project_id: taskShareModeText(params.get("project_id")),
        share_id: taskShareModeText(params.get("share_id")),
        token: taskShareModeText(params.get("token")),
        passcode: taskShareModeText(params.get("passcode")),
        session_id: taskShareModeText(params.get("session_id")),
        sender_name: taskShareModeText(params.get("sender_name"), "外部协作者"),
      };
    }

    function isTaskShareModeRequested() {
      TASK_SHARE_MODE.params = taskShareModeReadParams();
      TASK_SHARE_MODE.requested = !!taskShareModeText(TASK_SHARE_MODE.params.share_id);
      return TASK_SHARE_MODE.requested;
    }

    function isTaskShareModeActive() {
      return !!TASK_SHARE_MODE.active;
    }

    function taskShareModeParams() {
      if (!TASK_SHARE_MODE.params || typeof TASK_SHARE_MODE.params !== "object") {
        TASK_SHARE_MODE.params = taskShareModeReadParams();
      }
      return TASK_SHARE_MODE.params;
    }

    function taskShareModeBootstrapPath() {
      const shareMode = (TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.share_mode) || {};
      const endpoints = (shareMode && typeof shareMode === "object") ? (shareMode.endpoints || {}) : {};
      const direct = taskShareModeText(endpoints.bootstrap_path);
      if (direct) return direct;
      const shareId = taskShareModeText(taskShareModeParams().share_id);
      return "/api/share-spaces/" + encodeURIComponent(shareId) + "/bootstrap";
    }

    function taskShareModeSessionPath(sessionId) {
      const shareMode = (TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.share_mode) || {};
      const endpoints = (shareMode && typeof shareMode === "object") ? (shareMode.endpoints || {}) : {};
      const template = taskShareModeText(endpoints.session_path_template || endpoints.session_path);
      if (template && taskShareModeText(sessionId)) {
        return template.replace(":session_id", encodeURIComponent(taskShareModeText(sessionId)));
      }
      const shareId = taskShareModeText(taskShareModeParams().share_id);
      return "/api/share-spaces/" + encodeURIComponent(shareId) + "/sessions/" + encodeURIComponent(taskShareModeText(sessionId));
    }

    function taskShareModeAnnouncePath() {
      const shareMode = (TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.share_mode) || {};
      const endpoints = (shareMode && typeof shareMode === "object") ? (shareMode.endpoints || {}) : {};
      const direct = taskShareModeText(endpoints.announce_path);
      if (direct) return direct;
      const shareId = taskShareModeText(taskShareModeParams().share_id);
      return "/api/share-spaces/" + encodeURIComponent(shareId) + "/announce";
    }

    function taskShareModeQueryString(extra = {}) {
      const params = new URLSearchParams();
      const merged = { ...taskShareModeParams(), ...(extra || {}) };
      Object.entries(merged).forEach(([key, value]) => {
        if (value == null) return;
        const text = taskShareModeText(value);
        if (text) params.set(key, text);
      });
      return params.toString();
    }

    function taskShareModeCurrentPayload(sessionId = "") {
      const sid = taskShareModeText(sessionId || STATE.selectedSessionId);
      return sid ? (TASK_SHARE_MODE.sessionPayloadById[sid] || null) : null;
    }

    function taskShareModeRunRowsFromPayload(payload, sessionId = "") {
      const body = (payload && typeof payload === "object") ? payload : {};
      const projectId = taskShareModeText(body.project_id || STATE.project);
      const shareId = taskShareModeText(body.share_id || (TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.share_id) || taskShareModeParams().share_id);
      const currentSid = taskShareModeText(sessionId || (body.session && (body.session.session_id || body.session.sessionId)) || STATE.selectedSessionId);
      const session = (body.session && typeof body.session === "object") ? body.session : {};
      const source = Array.isArray(body.runs)
        ? body.runs
        : (Array.isArray(body.run_summaries) ? body.run_summaries : []);
      return source.map((row) => {
        const item = (row && typeof row === "object") ? row : {};
        const rid = taskShareModeText(item.id);
        const createdAt = taskShareModeText(item.createdAt);
        const finishedAt = taskShareModeText(item.finishedAt || item.finished_at);
        const startedAt = taskShareModeText(item.startedAt || item.started_at);
        const preview = taskShareModeText(item.lastPreview || item.preview);
        return {
          id: rid,
          projectId,
          channelName: taskShareModeText(item.channelName || session.channel_name),
          sessionId: taskShareModeText(item.sessionId || currentSid),
          cliType: taskShareModeText(item.cliType || session.cli_type, "codex"),
          status: taskShareModeText(item.status, "done"),
          display_state: taskShareModeText(item.status, "done"),
          createdAt,
          startedAt,
          finishedAt,
          updatedAt: taskShareModeFirst([finishedAt, startedAt, createdAt]),
          error: taskShareModeText(item.error),
          messagePreview: taskShareModeText(item.messagePreview),
          partialPreview: taskShareModeText(item.partialPreview),
          lastPreview: preview,
          preview,
          sender_type: taskShareModeText(item.sender_type, "user"),
          sender_id: taskShareModeText(item.sender_id, "share:" + shareId),
          sender_name: taskShareModeText(item.sender_name, taskShareModeParams().sender_name),
          message_kind: taskShareModeText(item.message_kind, "manual_update"),
          interaction_mode: taskShareModeText(item.interaction_mode, "task_with_receipt"),
          visible_in_channel_chat: !!item.visible_in_channel_chat,
          attachments: Array.isArray(item.attachments) ? item.attachments.slice() : [],
          mention_targets: Array.isArray(item.mention_targets)
            ? item.mention_targets.slice()
            : (Array.isArray(item.mentionTargets) ? item.mentionTargets.slice() : []),
          reply_to_run_id: taskShareModeText(item.reply_to_run_id || item.replyToRunId),
          reply_to_sender_name: taskShareModeText(item.reply_to_sender_name || item.replyToSenderName),
          reply_to_created_at: taskShareModeText(item.reply_to_created_at || item.replyToCreatedAt),
          reply_to_preview: taskShareModeText(item.reply_to_preview || item.replyToPreview),
          communication_view: (item.communication_view && typeof item.communication_view === "object")
            ? { ...item.communication_view }
            : ((item.communicationView && typeof item.communicationView === "object")
              ? { ...item.communicationView }
              : null),
          trigger_type: taskShareModeText(item.trigger_type || item.triggerType),
          share_mode: true,
          _share_scoped: true,
        };
      });
    }

    function taskShareModeLatestRunSummary(runs) {
      const list = Array.isArray(runs) ? runs.slice() : [];
      if (!list.length) return null;
      list.sort((a, b) => {
        const ta = toTimeNum(taskShareModeFirst([a && a.finishedAt, a && a.startedAt, a && a.createdAt]));
        const tb = toTimeNum(taskShareModeFirst([b && b.finishedAt, b && b.startedAt, b && b.createdAt]));
        if (ta >= 0 && tb >= 0 && ta !== tb) return tb - ta;
        return taskShareModeFirst([b && b.finishedAt, b && b.startedAt, b && b.createdAt]).localeCompare(
          taskShareModeFirst([a && a.finishedAt, a && a.startedAt, a && a.createdAt])
        );
      });
      const latest = list[0] || {};
      return {
        run_id: taskShareModeText(latest.id),
        status: taskShareModeText(latest.status, "done"),
        updated_at: taskShareModeFirst([latest.finishedAt, latest.startedAt, latest.createdAt]),
        preview: taskShareModeText(latest.lastPreview || latest.preview),
        latest_user_msg: taskShareModeText(latest.messagePreview),
        latest_ai_msg: taskShareModeText(latest.lastPreview || latest.preview),
        run_count: list.length,
        sender_type: taskShareModeText(latest.sender_type),
        sender_name: taskShareModeText(latest.sender_name),
        sender_source: "share_mode",
        speaker: "assistant",
      };
    }

    function taskShareModeComposerState(sessionId = "") {
      const payload = taskShareModeCurrentPayload(sessionId);
      const composer = (payload && payload.composer && typeof payload.composer === "object") ? payload.composer : {};
      const chat = (payload && payload.chat && typeof payload.chat === "object") ? payload.chat : {};
      const permission = taskShareModeText(chat.permission || (TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.share_status && TASK_SHARE_MODE.bootstrap.share_status.permission), "read_send");
      const enabled = composer.enabled !== false && permission !== "read" && permission !== "read_only";
      return {
        enabled,
        readOnly: !enabled,
        permission,
        placeholder: taskShareModeText(
          composer.placeholder,
          enabled ? "输入要发送给授权 Agent 的消息" : "当前链接为只读访问"
        ),
        submitLabel: taskShareModeText(composer.submit_label, "发送"),
      };
    }

    function taskShareModeSessionRow(raw, projectId = "") {
      const source = (raw && typeof raw === "object") ? raw : {};
      const sid = taskShareModeText(source.session_id || source.sessionId);
      const channelName = taskShareModeText(source.channel_name);
      const payload = sid ? taskShareModeCurrentPayload(sid) : null;
      const runs = taskShareModeRunRowsFromPayload(payload, sid);
      const latest = taskShareModeLatestRunSummary(runs);
      const displayName = taskShareModeFirst([
        source.agent_display_name,
        source.conversation_title,
        source.alias,
        channelName,
        sid,
      ], "未命名 Agent");
      const permissionState = taskShareModeComposerState(sid);
      return {
        sessionId: sid,
        id: sid,
        session_id: sid,
        project_id: taskShareModeText(projectId || source.project_id || STATE.project),
        channel_name: channelName,
        primaryChannel: channelName,
        channels: channelName ? [channelName] : [],
        alias: taskShareModeText(source.alias),
        displayChannel: displayName,
        displayName,
        displayNameSource: "share_mode",
        agent_display_name: taskShareModeText(source.agent_display_name, displayName),
        conversation_title: taskShareModeFirst([source.conversation_title, displayName]),
        cli_type: taskShareModeText(source.cli_type, "codex"),
        is_primary: !!source.is_primary,
        status: "active",
        created_at: "",
        last_used_at: taskShareModeText(latest && latest.updated_at),
        source: "share_mode",
        lastActiveAt: taskShareModeText(latest && latest.updated_at),
        lastStatus: taskShareModeText(latest && latest.status, "idle"),
        lastPreview: taskShareModeText(latest && latest.preview),
        lastSpeaker: "assistant",
        lastSenderType: taskShareModeText(latest && latest.sender_type),
        lastSenderName: taskShareModeText(latest && latest.sender_name),
        lastSenderSource: "share_mode",
        latestUserMsg: taskShareModeText(latest && latest.latest_user_msg),
        latestAiMsg: taskShareModeText(latest && latest.latest_ai_msg),
        runCount: Array.isArray(runs) ? runs.length : 0,
        latest_run_summary: latest,
        latest_effective_run_summary: latest,
        runtime_state: {
          display_state: "idle",
          internal_state: "idle",
          queue_depth: 0,
          active_run_id: "",
          queued_run_id: "",
          updated_at: taskShareModeText(latest && latest.updated_at),
        },
        session_display_state: permissionState.enabled ? "idle" : "active",
        _share_scoped: true,
      };
    }

    function taskShareModeSyncSessionStore() {
      if (!TASK_SHARE_MODE.bootstrap || !TASK_SHARE_MODE.bootstrap.project_id) return [];
      const projectId = taskShareModeText(TASK_SHARE_MODE.bootstrap.project_id || STATE.project);
      const agents = Array.isArray(TASK_SHARE_MODE.bootstrap.agents) ? TASK_SHARE_MODE.bootstrap.agents : [];
      const prevRows = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
      const prevMap = Object.create(null);
      prevRows.forEach((row) => {
        const sid = taskShareModeText(row && (row.sessionId || row.id));
        if (sid) prevMap[sid] = row;
      });
      const rows = agents.map((agent) => {
        const nextRow = taskShareModeSessionRow(agent, projectId);
        const sid = taskShareModeText(nextRow && nextRow.sessionId);
        if (!sid) return null;
        const prev = prevMap[sid];
        if (!prev || typeof prev !== "object") return nextRow;
        return {
          ...prev,
          ...nextRow,
          task_tracking: nextRow.task_tracking || prev.task_tracking || null,
          heartbeat_summary: nextRow.heartbeat_summary || prev.heartbeat_summary || null,
          project_execution_context: nextRow.project_execution_context || prev.project_execution_context || null,
        };
      }).filter((row) => row && taskShareModeText(row.sessionId));
      const activeSid = taskShareModeText(STATE.selectedSessionId);
      if (!activeSid && rows.length) {
        STATE.selectedSessionId = taskShareModeFirst([
          taskShareModeParams().session_id,
          TASK_SHARE_MODE.bootstrap.default_session_id,
          TASK_SHARE_MODE.bootstrap.share_mode && TASK_SHARE_MODE.bootstrap.share_mode.default_session_id,
          rows[0].sessionId,
        ]);
      }
      PCONV.sessions = rows.slice();
      ensureConversationSessionDirectoryStateMaps();
      PCONV.sessionDirectoryByProject[projectId] = rows.slice();
      markConversationSessionDirectoryMeta(projectId, {
        liveLoaded: true,
        source: "share_mode",
        loadedAt: new Date().toISOString(),
        error: "",
      });
      return rows;
    }

    async function loadTaskShareModeBootstrap(opts = {}) {
      if (!isTaskShareModeRequested()) return false;
      const params = taskShareModeParams();
      if (!params.project_id || !params.share_id) {
        TASK_SHARE_MODE.error = "缺少 project_id 或 share_id，无法进入 share-mode。";
        TASK_SHARE_MODE.active = true;
        return false;
      }
      try {
        const resp = await fetch(taskShareModeBootstrapPath() + "?" + taskShareModeQueryString({
          session_id: undefined,
          sender_name: undefined,
        }), {
          cache: "no-store",
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(taskShareModeText(body.error || body.message, "HTTP " + resp.status));
        }
        TASK_SHARE_MODE.bootstrap = body;
        TASK_SHARE_MODE.error = "";
        TASK_SHARE_MODE.active = true;
        STATE.project = taskShareModeText(body.project_id || params.project_id);
        STATE.panelMode = "conv";
        STATE.channel = "";
        STATE.selectedPath = "";
        STATE.selectedTaskId = "";
        STATE.selectedSessionId = taskShareModeFirst([
          params.session_id,
          body.share_mode && body.share_mode.selected_session_id,
          body.default_session_id,
          body.share_mode && body.share_mode.default_session_id,
          body.default_session && body.default_session.session_id,
        ]);
        STATE.selectedSessionExplicit = !!taskShareModeText(params.session_id);
        taskShareModeSyncSessionStore();
        if (!(opts && opts.skipBodyClass)) {
          try { document.body.classList.add("share-mode"); } catch (_) {}
        }
        return true;
      } catch (err) {
        TASK_SHARE_MODE.error = "读取分享入口失败：" + taskShareModeText(err && err.message ? err.message : err, "未知错误");
        TASK_SHARE_MODE.active = true;
        try { document.body.classList.add("share-mode"); } catch (_) {}
        return false;
      }
    }

    async function loadTaskShareModeSession(sessionId, opts = {}) {
      const sid = taskShareModeText(sessionId || STATE.selectedSessionId);
      if (!sid) return null;
      const force = !!(opts && opts.force);
      const loadedAt = Number(TASK_SHARE_MODE.sessionLoadedAtById[sid] || 0);
      if (!force && TASK_SHARE_MODE.sessionPayloadById[sid] && loadedAt > 0 && (Date.now() - loadedAt) < 1200) {
        return TASK_SHARE_MODE.sessionPayloadById[sid];
      }
      try {
        const resp = await fetch(taskShareModeSessionPath(sid) + "?" + taskShareModeQueryString({
          session_id: undefined,
          limit: 50,
          sender_name: undefined,
        }), {
          cache: "no-store",
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(taskShareModeText(body.error || body.message, "HTTP " + resp.status));
        }
        TASK_SHARE_MODE.sessionPayloadById[sid] = body;
        TASK_SHARE_MODE.sessionLoadedAtById[sid] = Date.now();
        TASK_SHARE_MODE.error = "";
        const runs = taskShareModeRunRowsFromPayload(body, sid);
        const projectId = taskShareModeText(body.project_id || STATE.project);
        const timelineKey = projectId + "::" + sid;
        PCONV.sessionTimelineMap[timelineKey] = runs.slice().sort((a, b) => {
          const ta = toTimeNum(taskShareModeText(a && a.createdAt));
          const tb = toTimeNum(taskShareModeText(b && b.createdAt));
          if (ta >= 0 && tb >= 0 && ta !== tb) return ta - tb;
          return taskShareModeText(a && a.createdAt).localeCompare(taskShareModeText(b && b.createdAt));
        });
        PCONV.runsBySession[sid] = runs.slice();
        taskShareModeSyncSessionStore();
        return body;
      } catch (err) {
        TASK_SHARE_MODE.error = "读取聊天详情失败：" + taskShareModeText(err && err.message ? err.message : err, "未知错误");
        return null;
      }
    }

    function taskShareModeSelectedLabel(session = null) {
      const current = (session && typeof session === "object") ? session : (taskShareModeCurrentPayload() && taskShareModeCurrentPayload().session) || {};
      return taskShareModeFirst([
        current.conversation_title,
        current.agent_display_name,
        current.alias,
        current.channel_name,
        STATE.selectedSessionId,
      ], "未选择授权 Agent");
    }

    function taskShareModeSyncChannelBySelection() {
      const current = typeof findConversationSessionById === "function"
        ? findConversationSessionById(STATE.selectedSessionId)
        : null;
      STATE.channel = taskShareModeText(current && current.channel_name);
    }

    function selectTaskShareModeSession(sessionId) {
      const sid = taskShareModeText(sessionId);
      if (!sid) return;
      STATE.selectedSessionId = sid;
      STATE.selectedSessionExplicit = true;
      taskShareModeSyncChannelBySelection();
      buildConversationLeftList();
      buildConversationMainList(document.getElementById("fileList"));
      setHash();
      void refreshConversationTimeline(String(STATE.project || ""), sid, true);
    }

    function renderTaskShareModeLeftList() {
      const left = document.getElementById("leftList");
      const asideTitle = document.getElementById("asideTitle");
      const asideMeta = document.getElementById("asideMeta");
      const layoutBar = document.getElementById("convLayoutBar");
      if (!left || !asideTitle || !asideMeta) return;
      if (layoutBar) layoutBar.style.display = "none";
      asideTitle.textContent = "对话";
      asideMeta.innerHTML = "";
      const rows = taskShareModeSyncSessionStore();
      const groups = Array.isArray(TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.agent_groups)
        ? TASK_SHARE_MODE.bootstrap.agent_groups
        : [];
      left.innerHTML = "";
      if (TASK_SHARE_MODE.error && !groups.length) {
        left.appendChild(el("div", { class: "hint", text: TASK_SHARE_MODE.error }));
        return;
      }
      if (!groups.length) {
        left.appendChild(el("div", { class: "hint", text: "当前没有可访问的 Agent。" }));
        return;
      }
      const fragment = document.createDocumentFragment();
      groups.forEach((group) => {
        const card = el("section", { class: "conv-channel-group" });
        const head = el("div", { class: "conv-channel-group-head" });
        head.appendChild(el("div", {
          class: "conv-channel-group-title",
          text: taskShareModeText(group.title || group.channel_name, "未分组通道"),
          title: taskShareModeText(group.title || group.channel_name, "未分组通道"),
        }));
        card.appendChild(head);
        const list = el("div", { class: "conv-channel-group-list" });
        (Array.isArray(group.agents) ? group.agents : []).forEach((agent) => {
          const sid = taskShareModeText(agent.session_id || agent.sessionId);
          const session = rows.find((row) => taskShareModeText(row && row.sessionId) === sid) || taskShareModeSessionRow(agent, STATE.project);
          const row = typeof buildConversationRow === "function"
            ? buildConversationRow(session, taskShareModeText(STATE.selectedSessionId) === sid, (nextSid) => {
              selectTaskShareModeSession(nextSid);
              if (typeof closeDrawerOnMobile === "function") closeDrawerOnMobile();
            }, {
              showCountDots: false,
              projectId: STATE.project,
            })
            : el("button", {
              class: "frow" + (taskShareModeText(STATE.selectedSessionId) === sid ? " active" : ""),
              type: "button",
              text: taskShareModeSelectedLabel(agent),
            });
          list.appendChild(row);
        });
        card.appendChild(list);
        fragment.appendChild(card);
      });
      left.appendChild(fragment);
    }

    function renderTaskShareModeMainList(container) {
      if (!container) return;
      container.innerHTML = "";
      if (!isMobileViewport()) return;
      const groups = Array.isArray(TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.agent_groups)
        ? TASK_SHARE_MODE.bootstrap.agent_groups
        : [];
      const rows = taskShareModeSyncSessionStore();
      if (!groups.length) {
        container.appendChild(el("div", { class: "hint", text: TASK_SHARE_MODE.error || "当前没有可访问的 Agent。" }));
        return;
      }
      groups.forEach((group) => {
        const section = el("section", { class: "conv-channel-group" });
        section.appendChild(el("div", {
          class: "conv-channel-group-title",
          text: taskShareModeText(group.title || group.channel_name, "未分组通道"),
        }));
        const list = el("div", { class: "conv-channel-group-list" });
        (Array.isArray(group.agents) ? group.agents : []).forEach((agent) => {
          const sid = taskShareModeText(agent.session_id || agent.sessionId);
          const session = rows.find((row) => taskShareModeText(row && row.sessionId) === sid) || taskShareModeSessionRow(agent, STATE.project);
          const row = typeof buildConversationRow === "function"
            ? buildConversationRow(session, taskShareModeText(STATE.selectedSessionId) === sid, (nextSid) => selectTaskShareModeSession(nextSid), {
              showCountDots: false,
              projectId: STATE.project,
            })
            : el("button", { class: "frow", type: "button", text: taskShareModeSelectedLabel(agent) });
          list.appendChild(row);
        });
        section.appendChild(list);
        container.appendChild(section);
      });
    }

    async function sendTaskShareModeMessage() {
      const input = document.getElementById("convMsg");
      const sendBtn = document.getElementById("convSendBtn");
      const sid = taskShareModeText(STATE.selectedSessionId);
      const composer = taskShareModeComposerState(sid);
      if (!input || !sendBtn || !sid || !composer.enabled || TASK_SHARE_MODE.sending) return false;
      if (typeof saveConvComposerUiToBoundDraft === "function") {
        saveConvComposerUiToBoundDraft();
      }
      const composeDraftKey = typeof currentConvComposerDraftKey === "function"
        ? String(currentConvComposerDraftKey() || "").trim()
        : String(PCONV.composerBoundDraftKey || "").trim();
      const composeDraft = (composeDraftKey && typeof getConvComposerDraftByKey === "function")
        ? getConvComposerDraftByKey(composeDraftKey)
        : { text: String(input.value || ""), mentions: [], attachments: [], replyContext: null };
      const composeAttachments = typeof cloneConvComposerAttachments === "function"
        ? cloneConvComposerAttachments(composeDraft.attachments)
        : [];
      const mentionTargets = typeof serializeMentionTargetsForSend === "function"
        ? serializeMentionTargetsForSend(composeDraft.mentions)
        : [];
      const replyContext = typeof normalizeConvReplyContext === "function"
        ? normalizeConvReplyContext(composeDraft.replyContext)
        : null;
      const ctx = (typeof currentConversationCtx === "function" ? currentConversationCtx() : null)
        || (typeof resolveConversationSendCtx === "function" ? resolveConversationSendCtx() : null);
      if (!ctx || !ctx.sessionId) return false;
      const baseMessage = taskShareModeText(composeDraft.text, taskShareModeText(input.value));
      if (!baseMessage && composeAttachments.length === 0) return false;
      const message = typeof appendMentionCompatToMessage === "function"
        ? taskShareModeText(appendMentionCompatToMessage(baseMessage, mentionTargets), baseMessage)
        : baseMessage;
      TASK_SHARE_MODE.sending = true;
      PCONV.sending = true;
      PCONV.optimistic = {
        sessionId: ctx.sessionId,
        message,
        attachments: composeAttachments.map((a) => ({ url: a.url || a.dataUrl || "", originalName: a.originalName })),
        mentionTargets,
        replyToRunId: String((replyContext && replyContext.runId) || ""),
        createdAt: new Date().toISOString(),
      };
      if (typeof markSessionPending === "function") {
        markSessionPending(ctx.sessionId, message);
      }
      renderTaskShareModeLeftList();
      renderTaskShareModeMainList(document.getElementById("fileList"));
      if (typeof setHintText === "function") {
        setHintText("conv", "发送中…");
      }
      if (typeof renderConversationDetail === "function") {
        renderConversationDetail(true);
      }
      try {
        const params = taskShareModeParams();
        const resp = await fetch(taskShareModeAnnouncePath(), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: params.project_id,
            token: params.token,
            passcode: params.passcode,
            session_id: sid,
            sender_name: params.sender_name,
            message,
            attachments: composeAttachments.map((a) => ({
              filename: a.filename,
              originalName: a.originalName,
              url: a.url || a.dataUrl || "",
            })),
            mention_targets: mentionTargets,
            reply_to_run_id: String((replyContext && replyContext.runId) || ""),
          }),
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(taskShareModeText(body.error || body.message, "HTTP " + resp.status));
        }
        if (composeDraftKey && typeof clearConvComposerDraftByKey === "function") {
          clearConvComposerDraftByKey(composeDraftKey);
          if (String(PCONV.composerBoundDraftKey || "") === composeDraftKey && typeof resetMessageInputHeight === "function") {
            resetMessageInputHeight(input);
          }
        } else if (input) {
          input.value = "";
          if (typeof resetMessageInputHeight === "function") {
            resetMessageInputHeight(input);
          }
        }
        TASK_SHARE_MODE.error = "";
        if (typeof injectConversationAckRunToTimeline === "function") {
          injectConversationAckRunToTimeline(
            ctx,
            PCONV.optimistic || {},
            body || {},
            { source: "share-announce-ack" }
          );
        }
        const shareRunId = body && body.run ? String(body.run.id || body.run.run_id || "") : "";
        if (typeof triggerConversationEasterEggForText === "function") {
          triggerConversationEasterEggForText(message, {
            sessionId: sid,
            runId: shareRunId,
            source: "share-send-ack",
          });
        }
        PCONV.optimistic = null;
        PCONV.sending = false;
        await refreshTaskShareModeConversationPanel();
        const runId = shareRunId;
        if (typeof setHintText === "function") {
          setHintText("conv", "已发送，等待执行回溯刷新…");
        }
        if (runId) scheduleConversationPoll(2500);
        return true;
      } catch (err) {
        TASK_SHARE_MODE.error = "发送失败：" + taskShareModeText(err && err.message ? err.message : err, "未知错误");
        if (typeof setHintText === "function") {
          setHintText("conv", TASK_SHARE_MODE.error);
        }
        return false;
      } finally {
        TASK_SHARE_MODE.sending = false;
        PCONV.sending = false;
        PCONV.optimistic = null;
        if (typeof renderConversationDetail === "function") {
          renderConversationDetail(false);
        }
      }
    }

    async function refreshTaskShareModeConversationPanel() {
      if (!isTaskShareModeActive()) return;
      const projectId = taskShareModeText(STATE.project || (TASK_SHARE_MODE.bootstrap && TASK_SHARE_MODE.bootstrap.project_id));
      if (!TASK_SHARE_MODE.bootstrap) {
        await loadTaskShareModeBootstrap();
      }
      taskShareModeSyncSessionStore();
      taskShareModeSyncChannelBySelection();
      renderTaskShareModeLeftList();
      renderTaskShareModeMainList(document.getElementById("fileList"));
      const sid = taskShareModeText(STATE.selectedSessionId);
      if (sid) {
        await loadTaskShareModeSession(sid, { force: true });
      }
      if (typeof renderConversationDetail === "function") {
        renderConversationDetail(false);
      }
      const payload = taskShareModeCurrentPayload(sid);
      const runs = taskShareModeRunRowsFromPayload(payload, sid);
      const hasWorking = runs.some((row) => {
        const status = taskShareModeText(row && row.status).toLowerCase();
        return status === "queued" || status === "running" || status === "retry_waiting" || status === "external_busy";
      });
      const nextPollMs = hasWorking ? 1800 : 5000;
      if (projectId && sid) scheduleConversationPoll(nextPollMs);
    }

    function renderTaskShareModePage() {
      try { document.body.classList.add("share-mode"); } catch (_) {}
      STATE.panelMode = "conv";
      stopCCBPoll();
      taskShareModeSyncSessionStore();
      updateProjectInfo();
      updateChannelSelectorName();
      updateCurrentChannelName();
      applyPanelMode();
      renderTaskShareModeLeftList();
      renderTaskShareModeMainList(document.getElementById("fileList"));
      void refreshTaskShareModeConversationPanel();
    }
