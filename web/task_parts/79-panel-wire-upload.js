    function isTaskSingleCanvasMode() {
      return normalizePanelMode(STATE.panelMode) === "task"
        && normalizeTaskModule(STATE.taskModule) === "tasks";
    }

    function syncTaskCanvasDetailState() {
      const active = isTaskSingleCanvasMode() && !!STATE.taskCanvasDetailOpen;
      try {
        document.body.classList.toggle("task-canvas-detail-open", active);
      } catch (_) {}
      return active;
    }

    function openTaskCanvasDetail() {
      if (!isTaskSingleCanvasMode()) return false;
      STATE.taskCanvasDetailOpen = true;
      syncTaskCanvasDetailState();
      return true;
    }

    function closeTaskCanvasDetail() {
      STATE.taskCanvasDetailOpen = false;
      syncTaskCanvasDetailState();
      return true;
    }

    function applyPanelMode() {
      const mode = normalizePanelMode(STATE.panelMode);
      const taskSingleCanvas = mode === "task" && normalizeTaskModule(STATE.taskModule) === "tasks";
      if (!taskSingleCanvas) STATE.taskCanvasDetailOpen = false;
      document.body.classList.toggle("panel-conv", mode === "conv");
      document.body.classList.toggle("panel-task", mode === "task");
      document.body.classList.toggle("panel-org-info", mode === "org");
      document.body.classList.toggle("panel-org", mode === "arch");
      document.body.classList.toggle("panel-task-single-canvas", taskSingleCanvas);
      syncTaskCanvasDetailState();
      const segBtns = Array.from(document.querySelectorAll("[data-panel-mode]"));
      for (const btn of segBtns) {
        const btnMode = normalizePanelMode(btn.getAttribute("data-panel-mode") || "channel");
        const active = btnMode === mode;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      }
      // 根据模式切换侧边栏按钮显示
      const newChannelAsideBtn = document.getElementById("newChannelAsideBtn");
      if (newChannelAsideBtn) newChannelAsideBtn.style.display = (mode === "channel" || mode === "conv") ? "" : "none";
    }

    const ASIDE_WIDTH_KEY = "taskDashboard.asideW";
    const ASIDE_MIN_W = 320;
    const ASIDE_MAX_W = 560;
    const CONV_ASIDE_WIDTH_KEY = "taskDashboard.convAsideW";
    const CONV_ASIDE_MIN_W = 320;
    const CONV_ASIDE_MAX_W = 760;
    const CONV_LIST_SCROLL_IDLE_MS = 180;

    function clampAsideWidth(width, viewportWidth = 0) {
      const vp = Math.max(0, Number(viewportWidth || window.innerWidth || 0));
      const hardMax = vp > 0 ? Math.max(ASIDE_MIN_W, Math.min(ASIDE_MAX_W, vp - 520)) : ASIDE_MAX_W;
      const num = Number(width || 0);
      if (!Number.isFinite(num) || num <= 0) return Math.min(Math.max(336, ASIDE_MIN_W), hardMax);
      return Math.max(ASIDE_MIN_W, Math.min(hardMax, Math.round(num)));
    }

    function applyAsideWidth(width, persist = false) {
      const next = clampAsideWidth(width);
      try {
        document.documentElement.style.setProperty("--asideW", next + "px");
        if (persist) localStorage.setItem(ASIDE_WIDTH_KEY, String(next));
      } catch (_) {}
      return next;
    }

    function restoreAsideWidthFromStorage() {
      try {
        const raw = localStorage.getItem(ASIDE_WIDTH_KEY);
        if (!raw) return;
        const n = Number(raw);
        if (!Number.isFinite(n) || n <= 0) return;
        applyAsideWidth(n, false);
      } catch (_) {}
    }

    function clampConvAsideWidth(width, viewportWidth = 0) {
      const vp = Math.max(0, Number(viewportWidth || window.innerWidth || 0));
      const hardMax = vp > 0 ? Math.max(CONV_ASIDE_MIN_W, Math.min(CONV_ASIDE_MAX_W, vp - 360)) : CONV_ASIDE_MAX_W;
      const num = Number(width || 0);
      if (!Number.isFinite(num) || num <= 0) return Math.min(Math.max(360, CONV_ASIDE_MIN_W), hardMax);
      return Math.max(CONV_ASIDE_MIN_W, Math.min(hardMax, Math.round(num)));
    }

    function applyConvAsideWidth(width, persist = false) {
      const next = clampConvAsideWidth(width);
      try {
        document.documentElement.style.setProperty("--convAsideW", next + "px");
        if (persist) localStorage.setItem(CONV_ASIDE_WIDTH_KEY, String(next));
      } catch (_) {}
      return next;
    }

    function restoreConvAsideWidthFromStorage() {
      try {
        const raw = localStorage.getItem(CONV_ASIDE_WIDTH_KEY);
        if (!raw) return;
        const n = Number(raw);
        if (!Number.isFinite(n) || n <= 0) return;
        applyConvAsideWidth(n, false);
      } catch (_) {}
    }

    function initConversationResizeHandle() {
      const handle = document.getElementById("convResizeHandle");
      const aside = document.getElementById("channelAside");
      if (!handle || !aside || handle.__boundResize) return;
      handle.__boundResize = true;
      let dragging = false;
      let resizeMode = "";
      let startX = 0;
      let startW = 0;
      const onMove = (ev) => {
        if (!dragging) return;
        const dx = Number(ev.clientX || 0) - startX;
        if (resizeMode === "conv") applyConvAsideWidth(startW + dx, false);
        else applyAsideWidth(startW + dx, false);
      };
      const onUp = (ev) => {
        if (!dragging) return;
        dragging = false;
        const mode = resizeMode;
        resizeMode = "";
        handle.classList.remove("active");
        try { document.body.classList.remove("conv-resizing"); } catch (_) {}
        const dx = Number((ev && ev.clientX) || 0) - startX;
        if (mode === "conv") applyConvAsideWidth(startW + dx, true);
        else applyAsideWidth(startW + dx, true);
        window.removeEventListener("mousemove", onMove, true);
        window.removeEventListener("mouseup", onUp, true);
      };
      handle.addEventListener("mousedown", (ev) => {
        if (isMobileViewport()) return;
        const panelMode = normalizePanelMode(STATE.panelMode);
        if (panelMode === "org" || panelMode === "arch") return;
        ev.preventDefault();
        resizeMode = panelMode === "conv" ? "conv" : "default";
        const rect = aside.getBoundingClientRect();
        startW = Math.max(resizeMode === "conv" ? CONV_ASIDE_MIN_W : ASIDE_MIN_W, Number(rect.width || 0));
        startX = Number(ev.clientX || 0);
        dragging = true;
        handle.classList.add("active");
        try { document.body.classList.add("conv-resizing"); } catch (_) {}
        window.addEventListener("mousemove", onMove, true);
        window.addEventListener("mouseup", onUp, true);
      });
      window.addEventListener("resize", () => {
        const asideRaw = getComputedStyle(document.documentElement).getPropertyValue("--asideW");
        const asideNum = Number(String(asideRaw || "").replace("px", "").trim());
        if (Number.isFinite(asideNum) && asideNum > 0) applyAsideWidth(asideNum, false);
        const cssRaw = getComputedStyle(document.documentElement).getPropertyValue("--convAsideW");
        const cssNum = Number(String(cssRaw || "").replace("px", "").trim());
        if (Number.isFinite(cssNum) && cssNum > 0) applyConvAsideWidth(cssNum, false);
      });
    }

    // 布局功能已移除 - 使用固定的响应式布局

    const CCB = {
      lastChannelId: "",
      busy: false,
      pollTimer: 0,
      runs: [],
      expanded: new Set(),
      detailMap: Object.create(null),
    };

    const PCONV = {
      lastProjectId: "",
      busy: false,
      pollTimer: 0,
      sessions: [],
      sessionDirectoryByProject: Object.create(null), // projectId -> all sessions (unfiltered)
      sessionDirectoryMetaByProject: Object.create(null), // projectId -> { liveLoaded, loadedAt, source, error }
      sessionDirectoryPromiseByProject: Object.create(null), // projectId -> Promise
      runsBySession: Object.create(null),
      sessionTimelineMap: Object.create(null),
      projectRuns: [],
      detailMap: Object.create(null),
      debugExpanded: new Set(),
      bubbleExpanded: new Set(),
      processUi: Object.create(null), // { [runId]: { expanded:boolean, manual:boolean } }
      runDetailTabByRun: Object.create(null), // { [runId]: "process" | "debug" }
      processTrailByRun: Object.create(null), // { [runId]: { items:string[], rows:[{text,at}], status:string, updatedAt:number } }
      sending: false,
      optimistic: null,
      lastRefreshAt: "",
      timelineRequestSeq: 0,
      timelineLoadingKey: "",
      timelineBeforeLoadingKey: "",
      timelineBeforeHasMoreByKey: Object.create(null), // key -> bool
      timelineBeforeErrorByKey: Object.create(null), // key -> error text
      autoExpandTimelineKey: "",
      autoExpandDone: false,
      autoExpandedLatestBubbleKey: "",
      runActionBusy: Object.create(null),
      locallyHiddenRunIds: new Set(), // runId -> locally hidden after accepted UI actions
      skillsExpandedByRun: Object.create(null),
      businessRefsExpandedByRun: Object.create(null),
      agentRefsExpandedByRun: Object.create(null),
      debugLogScrollTop: Object.create(null),
      draftBySessionKey: Object.create(null), // projectId::sessionId -> { text, attachments, updatedAt }
      composerBoundDraftKey: "",
      mentionSuggest: {
        open: false,
        mode: "project",
        query: "",
        activeIndex: 0,
        anchorStart: -1,
        anchorEnd: -1,
        candidates: [],
        groups: [],
        draftKey: "",
      },
      memoBySessionKey: Object.create(null), // projectId::sessionId -> { count, items, updatedAt, fetchedAt }
      memoLoadingBySessionKey: Object.create(null),
      memoActionBusyBySessionKey: Object.create(null), // save|delete|clear|apply
      memoSelectedBySessionKey: Object.create(null), // projectId::sessionId -> { memoId: true }
      memoHintBySessionKey: Object.create(null),
      memoRequestSeqBySessionKey: Object.create(null),
      memoDrawerOpen: false,
      memoDrawerSessionKey: "",
      taskDrawerOpen: false,
      taskDrawerSessionKey: "",
      taskDetailViewer: {
        open: false,
        sessionKey: "",
        taskId: "",
        taskPath: "",
        groupTitle: "",
        showActionContext: false,
        fallbackRef: null,
      },
      recentAgentsEnabled: true,
      recentAgentsBySessionKey: Object.create(null), // projectId::sessionId -> { count, items, updatedAt }
      recentAgentExpandedBySessionKey: Object.create(null), // projectId::sessionId -> bool
      filesBySessionKey: Object.create(null), // projectId::sessionId -> { count, items, updatedAt, fetchedAt }
      fileStarredBySessionKey: loadSessionScopedMap(CONV_FILE_STARRED_KEY), // projectId::sessionId -> { fileKey:true }
      trainingSentBySessionKey: loadSessionScopedMap(CONV_TRAINING_SENT_KEY), // projectId::sessionId -> sentAt
      trainingDismissedBySessionKey: Object.create(null), // projectId::sessionId -> true
      trainingManualOpenBySessionKey: Object.create(null), // projectId::sessionId -> true
      fileOnlyStarredBySessionKey: Object.create(null),
      fileSortBySessionKey: Object.create(null),
      fileTypeFilterBySessionKey: Object.create(null),
      fileDrawerOpen: false,
      fileDrawerSessionKey: "",
      unreadCursorBySessionKey: loadSessionScopedMap(CONV_UNREAD_CURSOR_KEY), // projectId::sessionId -> createdAt
      memoConsumedBySessionKey: loadSessionScopedMap(CONV_MEMO_CONSUMED_KEY), // projectId::sessionId -> { memoId:true }
      queueForwardDrag: {
        active: false,
        payload: null,
      },
      queueForwardModal: {
        open: false,
        busy: false,
        payload: null,
        target: null,
        userEdited: false,
        loadToken: 0,
      },
      listScrollTopByKey: Object.create(null),
      listScrollActiveUntil: 0,
      listScrollIdleTimer: 0,
      deferredPanelRender: false,
      deferredTimeline: null,
      userMessageViewer: {
        open: false,
        title: "",
        text: "",
        attachments: [],
      },
      assistantMessageViewer: {
        open: false,
        title: "",
        text: "",
        fallbackText: "",
        runId: "",
      },
      assistantMessageViewerNode: null,
      enterSendEnabled: true,
    };

    function loadConversationRecentAgentsEnabled() {
      try {
        const raw = String(localStorage.getItem("taskDashboard.convRecentAgentsEnabled.v1") || "").trim().toLowerCase();
        if (!raw) return true;
        return !(raw === "0" || raw === "false" || raw === "off");
      } catch (_) {
        return true;
      }
    }

    function setConversationRecentAgentsEnabled(enabled) {
      const next = !!enabled;
      PCONV.recentAgentsEnabled = next;
      try {
        localStorage.setItem("taskDashboard.convRecentAgentsEnabled.v1", next ? "1" : "0");
      } catch (_) {}
      return next;
    }

    PCONV.recentAgentsEnabled = loadConversationRecentAgentsEnabled();

    function loadConversationEnterSendEnabled() {
      try {
        const raw = String(localStorage.getItem("taskDashboard.convEnterSendEnabled.v1") || "").trim().toLowerCase();
        if (!raw) return true;
        return !(raw === "0" || raw === "false" || raw === "off");
      } catch (_) {
        return true;
      }
    }

    function setConversationEnterSendEnabled(enabled) {
      const next = !!enabled;
      PCONV.enterSendEnabled = next;
      try {
        localStorage.setItem("taskDashboard.convEnterSendEnabled.v1", next ? "1" : "0");
      } catch (_) {}
      return next;
    }

    PCONV.enterSendEnabled = loadConversationEnterSendEnabled();

    function isConversationDesktopMode() {
      return normalizePanelMode(STATE.panelMode) === "conv" && !isMobileViewport();
    }

    function conversationListScrollKey(projectId = "", layout = "") {
      const pid = String(projectId || (typeof STATE !== "undefined" && STATE ? STATE.project : "") || "").trim();
      if (!pid || pid === "overview") return "";
      const normalizedLayout = normalizeConversationListLayout(layout || (typeof STATE !== "undefined" && STATE ? STATE.convListLayout : ""));
      return pid + "::" + normalizedLayout;
    }

    function readConversationListStoredScrollTop(projectId = "", layout = "") {
      const key = conversationListScrollKey(projectId, layout);
      if (!key) return 0;
      const raw = Number((PCONV.listScrollTopByKey && PCONV.listScrollTopByKey[key]) || 0);
      return Number.isFinite(raw) && raw > 0 ? raw : 0;
    }

    function rememberConversationListScrollTop(top, projectId = "", layout = "") {
      const key = conversationListScrollKey(projectId, layout);
      if (!key) return 0;
      const next = Math.max(0, Number(top || 0) || 0);
      if (!PCONV.listScrollTopByKey || typeof PCONV.listScrollTopByKey !== "object") {
        PCONV.listScrollTopByKey = Object.create(null);
      }
      PCONV.listScrollTopByKey[key] = next;
      return next;
    }

    function conversationListScrollBox() {
      const left = document.getElementById("leftList");
      if (left) return left.closest(".aside-scroll") || left;
      return document.querySelector("#channelAside .aside-scroll");
    }

    function captureConversationListScrollTop(projectId = "", layout = "") {
      const box = conversationListScrollBox();
      const top = Math.max(0, Number((box && box.scrollTop) || 0) || 0);
      return rememberConversationListScrollTop(top, projectId, layout);
    }

    function restoreConversationListScrollTop(top, projectId = "", layout = "") {
      const desiredTop = rememberConversationListScrollTop(top, projectId, layout);
      if (!(desiredTop > 0)) return;
      requestAnimationFrame(() => {
        const box = conversationListScrollBox();
        if (!box) return;
        const maxTop = Math.max(0, Number(box.scrollHeight || 0) - Number(box.clientHeight || 0));
        box.scrollTop = Math.min(desiredTop, maxTop);
      });
    }

    function isConversationListScrollActive() {
      return false;
    }

    function queueDeferredConversationRender(opts = {}) {
      if (!isConversationDesktopMode()) return;
      if (opts.panelRender) PCONV.deferredPanelRender = true;
      const pid = String(opts.projectId || "").trim();
      const sid = String(opts.sessionId || "").trim();
      if (pid && sid) {
        const prev = (PCONV.deferredTimeline && typeof PCONV.deferredTimeline === "object")
          ? PCONV.deferredTimeline
          : null;
        PCONV.deferredTimeline = {
          projectId: pid,
          sessionId: sid,
          forceScroll: !!(opts.forceScroll || (prev && prev.forceScroll)),
        };
      }
    }

    function flushDeferredConversationRender() {
      if (!isConversationDesktopMode()) return;
      try { document.body.classList.remove("conv-list-scrolling"); } catch (_) {}
      const shouldRenderPanel = !!PCONV.deferredPanelRender;
      const deferredTimeline = (PCONV.deferredTimeline && typeof PCONV.deferredTimeline === "object")
        ? { ...PCONV.deferredTimeline }
        : null;
      if (!shouldRenderPanel && !deferredTimeline) return;
      PCONV.deferredPanelRender = false;
      PCONV.deferredTimeline = null;
      buildConversationLeftList();
      buildConversationMainList(document.getElementById("fileList"));
      if (!STATE.selectedSessionId) renderConversationDetail(true);
      if (deferredTimeline && deferredTimeline.projectId && deferredTimeline.sessionId) {
        refreshConversationTimeline(deferredTimeline.projectId, deferredTimeline.sessionId, !!deferredTimeline.forceScroll);
      } else if (String(STATE.selectedSessionId || "").trim()) {
        refreshConversationTimeline(String(STATE.project || ""), String(STATE.selectedSessionId || ""), false);
      }
    }

    function markConversationListScrollActive() {
      if (PCONV.listScrollIdleTimer) {
        clearTimeout(PCONV.listScrollIdleTimer);
        PCONV.listScrollIdleTimer = 0;
      }
      PCONV.listScrollActiveUntil = 0;
      try { document.body.classList.remove("conv-list-scrolling"); } catch (_) {}
    }

    function initConversationListScrollMonitor() {
      const scroller = document.querySelector("#channelAside .aside-scroll");
      if (!scroller || scroller.__convListScrollBound) return;
      scroller.__convListScrollBound = true;
      scroller.addEventListener("scroll", () => {
        captureConversationListScrollTop();
        markConversationListScrollActive();
      }, { passive: true });
    }

    function convComposerDraftKey(projectId, sessionId) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      if (!pid || !sid || pid === "overview") return "";
      return pid + "::" + sid;
    }

    function currentConvComposerDraftKey() {
      return convComposerDraftKey(STATE.project, STATE.selectedSessionId);
    }

    function ensureConvComposerDraftByKey(key) {
      const k = String(key || "").trim();
      if (!k) return null;
      if (!PCONV.draftBySessionKey[k]) {
        PCONV.draftBySessionKey[k] = {
          text: "",
          attachments: [],
          mentions: [],
          replyContext: null,
          updatedAt: "",
        };
      }
      return PCONV.draftBySessionKey[k];
    }

    function cloneConvComposerAttachment(att) {
      if (!att) return null;
      const mimeType = String(att.mimeType || "");
      const originalName = String(att.originalName || att.filename || "attachment");
      const src = String(att.dataUrl || att.url || "");
      const isImage = !!(String(att.isImage || "") === "true" || String(att.isImage || "") === "1" || mimeType.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(originalName));
      return {
        filename: String(att.filename || ""),
        originalName,
        url: String(att.url || ""),
        dataUrl: src,
        mimeType,
        size: Number(att.size || 0) > 0 ? Number(att.size || 0) : 0,
        isImage,
      };
    }

    function cloneConvComposerAttachments(list) {
      return (Array.isArray(list) ? list : [])
        .map(cloneConvComposerAttachment)
        .filter(Boolean);
    }

    function normalizeMentionTargetItem(raw) {
      if (!raw || typeof raw !== "object") return null;
      const channelName = String(firstNonEmptyText([
        raw.channel_name,
        raw.channelName,
        raw.channel,
      ]) || "").trim();
      const sessionId = String(firstNonEmptyText([
        raw.session_id,
        raw.sessionId,
        raw.id,
      ]) || "").trim();
      if (!channelName || !sessionId) return null;
      const issue = String(firstNonEmptyText([
        raw.agent_display_issue,
        raw.agentDisplayIssue,
      ]) || "").trim();
      const rawState = firstNonEmptyText([
        raw.agent_name_state,
        raw.agentNameState,
      ]);
      const derivedState = (typeof normalizeAgentNameState === "function")
        ? normalizeAgentNameState(rawState, "")
        : String(rawState || "").trim().toLowerCase();
      const explicitAgentName = String(firstNonEmptyText([
        raw.agent_display_name,
        raw.agentDisplayName,
        raw.agent_name,
        raw.agentName,
        raw.sender_name,
        raw.senderName,
        raw.alias,
      ]) || "").trim();
      const legacyDisplayName = String(firstNonEmptyText([
        raw.display_name,
        raw.displayName,
        raw.label,
      ]) || "").trim();
      const probe = {
        channel_name: channelName,
        channelName,
        session_id: sessionId,
        sessionId,
      };
      const safeLegacyDisplayName = legacyDisplayName
        && legacyDisplayName !== channelName
        && !(typeof isSessionDerivedAgentDisplayName === "function"
          && isSessionDerivedAgentDisplayName(legacyDisplayName, probe))
        ? legacyDisplayName
        : "";
      const resolvedName = explicitAgentName || safeLegacyDisplayName;
      let agentNameState = derivedState;
      if (!agentNameState) {
        if (issue) {
          agentNameState = (typeof normalizeAgentNameState === "function")
            ? normalizeAgentNameState("", issue.indexOf("polluted") >= 0 ? "polluted" : "identity_unresolved")
            : (issue.indexOf("polluted") >= 0 ? "polluted" : "identity_unresolved");
        } else if (resolvedName) {
          agentNameState = "resolved";
        } else {
          agentNameState = "identity_unresolved";
        }
      }
      const stateLabel = (typeof agentNameStateLabel === "function")
        ? String(agentNameStateLabel(agentNameState, issue) || "").trim()
        : "";
      const displayName = agentNameState === "resolved" && resolvedName
        ? resolvedName
        : (stateLabel || "身份未解析");
      return {
        channel_name: channelName,
        session_id: sessionId,
        cli_type: String(firstNonEmptyText([raw.cli_type, raw.cliType, "codex"]) || "codex").trim() || "codex",
        display_name: displayName,
        agent_display_name: agentNameState === "resolved" ? resolvedName : "",
        agent_display_name_source: String(firstNonEmptyText([
          raw.agent_display_name_source,
          raw.agentDisplayNameSource,
        ]) || (explicitAgentName ? "agent_display_name" : (safeLegacyDisplayName ? "display_name" : ""))).trim(),
        agent_name_state: agentNameState,
        agent_display_issue: issue,
        alias: String(firstNonEmptyText([raw.alias]) || "").trim(),
        agent_name: String(firstNonEmptyText([raw.agent_name, raw.agentName]) || "").trim(),
        project_id: String(firstNonEmptyText([
          raw.project_id,
          raw.projectId,
        ]) || "").trim(),
        project_name: String(firstNonEmptyText([
          raw.project_name,
          raw.projectName,
        ]) || "").trim(),
        mention_label: String(firstNonEmptyText([
          raw.mention_label,
          raw.mentionLabel,
          raw.scoped_label,
          raw.scopedLabel,
        ]) || "").trim(),
      };
    }

    function mentionTargetKey(raw) {
      const m = normalizeMentionTargetItem(raw);
      if (!m) return "";
      return String(m.channel_name || "").trim().toLowerCase() + "::" + String(m.session_id || "").trim().toLowerCase();
    }

    function cloneConvComposerMentionTargets(list) {
      const out = [];
      const seen = new Set();
      (Array.isArray(list) ? list : []).forEach((raw) => {
        const m = normalizeMentionTargetItem(raw);
        if (!m) return;
        const key = mentionTargetKey(m);
        if (!key || seen.has(key)) return;
        seen.add(key);
        out.push(m);
      });
      return out;
    }

    function normalizeConvReplyContext(raw) {
      if (!raw || typeof raw !== "object") return null;
      const bubbleKey = String(raw.bubbleKey || "").trim();
      const runId = String(raw.runId || raw.reply_to_run_id || raw.replyToRunId || "").trim();
      const senderLabel = String(raw.senderLabel || "我").trim() || "我";
      const timeLabel = String(raw.timeLabel || "").trim();
      const preview = String(raw.preview || "").trim();
      const injectedText = String(raw.injectedText || "").trim();
      if (!preview && !injectedText) return null;
      return {
        bubbleKey,
        runId,
        senderLabel,
        timeLabel,
        preview: preview || injectedText,
        injectedText,
        createdAt: String(raw.createdAt || "").trim(),
      };
    }

    function hasConvComposerDraftContent(draftLike) {
      const d = (draftLike && typeof draftLike === "object") ? draftLike : {};
      const text = String(d.text || "").trim();
      const attachments = Array.isArray(d.attachments) ? d.attachments : [];
      const mentions = Array.isArray(d.mentions) ? d.mentions : [];
      return !!text || attachments.length > 0 || mentions.length > 0;
    }

    function conversationDraftMetaBySession(projectId, sessionId) {
      const key = convComposerDraftKey(projectId, sessionId);
      if (!key) return { hasDraft: false, hasText: false, attachmentCount: 0, mentionCount: 0 };
      const draft = getConvComposerDraftByKey(key);
      const text = String(draft.text || "").trim();
      const attachmentCount = Array.isArray(draft.attachments) ? draft.attachments.length : 0;
      const mentionCount = Array.isArray(draft.mentions) ? draft.mentions.length : 0;
      return {
        hasDraft: !!text || attachmentCount > 0 || mentionCount > 0,
        hasText: !!text,
        attachmentCount,
        mentionCount,
      };
    }

    function conversationDraftTitle(meta) {
      const m = (meta && typeof meta === "object") ? meta : {};
      if (!m.hasDraft) return "";
      const parts = [];
      if (m.hasText) parts.push("含文本");
      if (Number(m.attachmentCount || 0) > 0) parts.push("含附件" + Number(m.attachmentCount || 0) + "个");
      if (Number(m.mentionCount || 0) > 0) parts.push("协同对象" + Number(m.mentionCount || 0) + "个");
      return "未发送草稿：" + (parts.length ? parts.join("，") : "待发送");
    }

    function getConvComposerDraftByKey(key) {
      const k = String(key || "").trim();
      if (!k) return { text: "", attachments: [], mentions: [], updatedAt: "" };
      const d = ensureConvComposerDraftByKey(k);
      return {
        text: String(d && d.text || ""),
        attachments: cloneConvComposerAttachments(d && d.attachments),
        mentions: cloneConvComposerMentionTargets(d && d.mentions),
        replyContext: normalizeConvReplyContext(d && d.replyContext),
        updatedAt: String(d && d.updatedAt || ""),
      };
    }

    function updateConvComposerDraftByKey(key, updater) {
      const d = ensureConvComposerDraftByKey(key);
      if (!d) return null;
      const hadDraft = hasConvComposerDraftContent(d);
      if (typeof updater === "function") updater(d);
      d.text = String(d.text || "");
      d.attachments = cloneConvComposerAttachments(d.attachments);
      d.mentions = cloneConvComposerMentionTargets(d.mentions);
      d.replyContext = normalizeConvReplyContext(d.replyContext);
      d.updatedAt = new Date().toISOString();
      const hasDraft = hasConvComposerDraftContent(d);
      if (hadDraft !== hasDraft) refreshConversationCountDots();
      return d;
    }

    function convComposerUiElements() {
      const input = document.getElementById("convMsg");
      const attachmentContainer = document.getElementById("convAttachments");
      const composer = document.querySelector(".convcomposer");
      const senderRow = document.getElementById("convSenderRow");
      const trainingContainer = document.getElementById("convTraining");
      const trainingCount = document.getElementById("convTrainingCount");
      const trainingDesc = document.getElementById("convTrainingDesc");
      const trainingSendBtn = document.getElementById("convTrainingSendBtn");
      const trainingCloseBtn = document.getElementById("convTrainingCloseBtn");
      let trainingReopenBtn = document.getElementById("convTrainingReopenBtn");
      const senderActions = senderRow ? senderRow.querySelector(".convsenderactions") : null;
      let recentAgentContainer = document.getElementById("convRecentAgents");
      let recentAgentToggle = document.getElementById("convRecentAgentsGlobalToggle");
      let mentionContainer = document.getElementById("convMentions");
      let replyContainer = document.getElementById("convReplyContext");
      let mentionSuggest = document.getElementById("convMentionSuggest");
      if (senderActions && !trainingReopenBtn) {
        trainingReopenBtn = document.createElement("button");
        trainingReopenBtn.id = "convTrainingReopenBtn";
        trainingReopenBtn.className = "conv-training-toggle";
        trainingReopenBtn.type = "button";
        trainingReopenBtn.title = "重新显示 Agent 培训";
        trainingReopenBtn.setAttribute("aria-label", "重新显示 Agent 培训");
        trainingReopenBtn.style.display = "none";
        trainingReopenBtn.innerHTML = [
          '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">',
          '<path d="M4 8.8 12 5l8 3.8-8 3.8L4 8.8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
          '<path d="M7 11.4V15c0 .9 2 2.4 5 2.4s5-1.5 5-2.4v-3.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
          '</svg>',
        ].join("");
        senderActions.insertBefore(trainingReopenBtn, senderActions.firstChild || null);
      }
      if (trainingReopenBtn && !trainingReopenBtn.__convTrainingReopenBound) {
        trainingReopenBtn.__convTrainingReopenBound = true;
        trainingReopenBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (typeof reopenConversationTrainingPrompt === "function") reopenConversationTrainingPrompt();
        });
      }
      if (composer && !mentionContainer) {
        mentionContainer = document.createElement("div");
        mentionContainer.id = "convMentions";
        mentionContainer.className = "convmentions";
        const attachNode = attachmentContainer || null;
        if (attachNode && attachNode.parentNode === composer) {
          composer.insertBefore(mentionContainer, attachNode);
        } else {
          composer.appendChild(mentionContainer);
        }
      }
      if (composer && !recentAgentContainer) {
        recentAgentContainer = document.createElement("div");
        recentAgentContainer.id = "convRecentAgents";
        recentAgentContainer.className = "convrecentagents";
        recentAgentContainer.style.display = "none";
        const mentionNode = mentionContainer || null;
        if (mentionNode && mentionNode.parentNode === composer) {
          composer.insertBefore(recentAgentContainer, mentionNode);
        } else {
          const attachNode = attachmentContainer || null;
          if (attachNode && attachNode.parentNode === composer) {
            composer.insertBefore(recentAgentContainer, attachNode);
          } else {
            composer.appendChild(recentAgentContainer);
          }
        }
      }
      if (composer && !recentAgentToggle) {
        recentAgentToggle = document.createElement("button");
        recentAgentToggle.id = "convRecentAgentsGlobalToggle";
        recentAgentToggle.className = "convrecentagents-global-toggle";
        recentAgentToggle.type = "button";
        recentAgentToggle.title = "切换最近联系显示";
        recentAgentToggle.setAttribute("aria-label", "切换最近联系显示");
        recentAgentToggle.innerHTML = [
          '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">',
          '<path d="M8 11.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z" stroke="currentColor" stroke-width="1.6"/>',
          '<path d="M16.8 10.1a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" stroke="currentColor" stroke-width="1.5" opacity="0.72"/>',
          '<path d="M4.5 18.2c.6-2.4 2.6-3.9 5.1-3.9s4.4 1.5 5 3.9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
          '<path d="M14.4 17.1c.4-1.6 1.8-2.6 3.4-2.6 1 0 1.9.4 2.5 1.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.72"/>',
          '</svg>',
          '<span class="convrecentagents-global-toggle-count" aria-hidden="true" hidden></span>',
        ].join("");
        if (senderRow && senderRow.parentNode === composer) senderRow.appendChild(recentAgentToggle);
        else composer.appendChild(recentAgentToggle);
      }
      if (recentAgentToggle && !recentAgentToggle.querySelector(".convrecentagents-global-toggle-count")) {
        recentAgentToggle.insertAdjacentHTML("beforeend", '<span class="convrecentagents-global-toggle-count" aria-hidden="true" hidden></span>');
      }
      if (recentAgentToggle && !recentAgentToggle.__recentAgentToggleBound) {
        recentAgentToggle.__recentAgentToggleBound = true;
        recentAgentToggle.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          setConversationRecentAgentsEnabled(!PCONV.recentAgentsEnabled);
          const draftKey = String(PCONV.composerBoundDraftKey || currentConvComposerDraftKey() || "").trim();
          if (draftKey && !PCONV.recentAgentsEnabled) delete PCONV.recentAgentExpandedBySessionKey[draftKey];
          renderConversationRecentAgentsByKey(draftKey);
        });
      }
      if (composer && !mentionSuggest) {
        mentionSuggest = document.createElement("div");
        mentionSuggest.id = "convMentionSuggest";
        mentionSuggest.className = "convmention-suggest";
        mentionSuggest.style.display = "none";
        composer.appendChild(mentionSuggest);
      }
      if (composer && !replyContainer) {
        replyContainer = document.createElement("div");
        replyContainer.id = "convReplyContext";
        replyContainer.className = "convreply";
        replyContainer.style.display = "none";
        const quickTips = document.getElementById("convQuickTips");
        if (quickTips && quickTips.parentNode === composer) {
          composer.insertBefore(replyContainer, quickTips);
        } else {
          composer.appendChild(replyContainer);
        }
      }
      return {
        input,
        container: attachmentContainer,
        recentAgentContainer,
        recentAgentToggle,
        trainingContainer,
        trainingCount,
        trainingDesc,
        trainingSendBtn,
        trainingCloseBtn,
        trainingReopenBtn,
        mentionContainer,
        replyContainer,
        mentionSuggest,
        composer,
      };
    }

    function saveConvComposerUiToBoundDraft() {
      const boundKey = String(PCONV.composerBoundDraftKey || "").trim();
      if (!boundKey) return;
      const { input } = convComposerUiElements();
      if (!input) return;
      updateConvComposerDraftByKey(boundKey, (d) => {
        const nextText = String(input.value || "");
        d.text = nextText;
        d.mentions = deriveConvComposerMentionTargetsFromText(nextText, STATE.project);
      });
    }

    function renderConvComposerAttachmentsByKey(key) {
      const { container } = convComposerUiElements();
      if (!container) return;
      container.innerHTML = "";
      const draft = getConvComposerDraftByKey(key);
      const draftKey = String(key || "").trim();
      draft.attachments.forEach((att, index) => {
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "remove-btn";
        removeBtn.textContent = "×";
        removeBtn.title = "移除附件";
        removeBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          updateConvComposerDraftByKey(draftKey, (d) => {
            if (index >= 0 && index < d.attachments.length) d.attachments.splice(index, 1);
          });
          renderAttachments();
        });

        const isImage = !!att.isImage;
        if (isImage) {
          const thumb = document.createElement("div");
          thumb.className = "attach-thumb";
          const img = document.createElement("img");
          img.src = String(att.dataUrl || att.url || "");
          img.alt = String(att.originalName || "attachment");
          img.addEventListener("click", (e) => {
            e.stopPropagation();
            openImagePreview(String(att.dataUrl || att.url || ""), String(att.originalName || "图片"));
          });
          thumb.appendChild(img);
          thumb.appendChild(removeBtn);
          container.appendChild(thumb);
          return;
        }

        const card = document.createElement("div");
        card.className = "attach-file";
        const ext = fileExtTag(att.originalName || att.filename || "");
        const ico = document.createElement("span");
        ico.className = "attach-file-ico";
        ico.textContent = ext;
        const main = document.createElement("div");
        main.className = "attach-file-main";
        const name = document.createElement("div");
        name.className = "attach-file-name";
        name.textContent = String(att.originalName || att.filename || "附件");
        name.title = name.textContent;
        const meta = document.createElement("div");
        meta.className = "attach-file-meta";
        const metaParts = [];
        if (att.mimeType) metaParts.push(String(att.mimeType));
        if (Number(att.size || 0) > 0) metaParts.push(formatBytes(Number(att.size || 0)));
        meta.textContent = metaParts.join(" · ");
        main.appendChild(name);
        main.appendChild(meta);
        card.appendChild(ico);
        card.appendChild(main);
        card.appendChild(removeBtn);
        container.appendChild(card);
      });
    }

    async function refreshCCB() {
      if (STATE.panelMode === "conv") return;
      if (CCB.busy) return;
      const hint = document.getElementById("ccbHint");
      const sendBtn = document.getElementById("ccbSendBtn");
      const refreshBtn = document.getElementById("ccbRefreshBtn");
      const sidChip = document.getElementById("ccbSidChip");
      const copySidBtn = document.getElementById("ccbCopySidBtn");
      const bindBtn = document.getElementById("ccbBindBtn");
      const editBtn = document.getElementById("ccbEditBindBtn");
      const unbindBtn = document.getElementById("ccbUnbindBtn");
      if (!hint || !sendBtn || !refreshBtn) return;

      const it = selectedItem();
      const ctx = currentChannelCtx(it);
      const channelId = ctx.channelId;
      if (CCB.lastChannelId !== channelId) {
        CCB.lastChannelId = channelId;
        CCB.expanded = new Set();
        CCB.detailMap = Object.create(null);
        CCB.runs = [];
      }
      if (sidChip) {
        sidChip.style.display = ctx.sessionId ? "" : "none";
        if (ctx.sessionId) sidChip.textContent = "通道绑定:" + shortId(ctx.sessionId);
      }
      if (copySidBtn) {
        copySidBtn.style.display = ctx.sessionId ? "" : "none";
        copySidBtn.onclick = ctx.sessionId ? (() => copyText(ctx.sessionId)) : (() => {});
      }
      if (bindBtn) {
        bindBtn.style.display = ctx.sessionId ? "none" : "";
        bindBtn.onclick = (!ctx.sessionId && ctx.projectId && ctx.channelName && ctx.projectId !== "overview")
          ? (() => openBindModal(ctx.projectId, ctx.channelName))
          : (() => {});
      }
      if (editBtn) {
        editBtn.style.display = ctx.sessionId ? "" : "none";
        editBtn.onclick = (ctx.projectId && ctx.channelName && ctx.projectId !== "overview")
          ? (() => openBindModal(ctx.projectId, ctx.channelName))
          : (() => {});
      }
      if (unbindBtn) {
        const hasLocal = !!getBinding(ctx.projectId, ctx.channelName);
        unbindBtn.style.display = (ctx.sessionId && hasLocal) ? "" : "none";
        unbindBtn.onclick = (ctx.projectId && ctx.channelName && ctx.projectId !== "overview")
          ? (async () => {
            const ok = confirm("确认解绑？只会清除本机浏览器保存的绑定，不会写入 config.toml。");
            if (!ok) return;
            const cleared = await clearBinding(ctx.projectId, ctx.channelName);
            if (!cleared) {
              alert("解绑失败：服务端未确认，请检查 Token 或服务状态。");
              return;
            }
            render();
          })
          : (() => {});
      }
      if (!channelId || channelId.includes("overview::")) {
        stopCCBPoll();
        hint.textContent = "CCB：请进入具体项目并选择通道后使用。";
        sendBtn.disabled = true;
        refreshBtn.disabled = true;
        renderRuns([]);
        return;
      }

      CCB.busy = true;
      try {
        const ok = await apiHealth();
        if (!ok) {
          stopCCBPoll();
          hint.textContent = "CCB API 未启用：请启动本地开发服务（需要同源 API 才能发消息/回看回复）。";
          sendBtn.disabled = true;
          refreshBtn.disabled = true;
          renderRuns([]);
          return;
        }

        refreshBtn.disabled = false;
        if (!ctx.sessionId) {
          stopCCBPoll();
          hint.textContent = "该通道未绑定 session_id：点击右上角【绑定对话】填写 Codex session_id（保存在本机浏览器）后即可发送。";
          sendBtn.disabled = true;
          renderRuns([]);
          return;
        }

        hint.textContent = "发送后会调用 `codex exec resume <sessionId>`，并在回溯列表实时显示处理过程和最后回复。";
        sendBtn.disabled = false;

        const j = await loadRuns({ channelId, limit: 30, payloadMode: "light" });
        const runs = (j && j.runs) ? j.runs : [];
        renderRuns(runs);
        const hasRunning = runs.some((x) => {
          const s = String((x && x.status) || "");
          return s === "queued" || s === "running" || s === "retry_waiting";
        });
        if (hasRunning) {
          hint.textContent = "Codex 正在处理该通道消息，日志会自动刷新。";
          scheduleCCBPoll(ccbPollDelay(true));
        } else {
          stopCCBPoll();
        }
      } finally {
        CCB.busy = false;
      }
    }

    async function sendCCB() {
      if (STATE.panelMode === "conv") return;
      const it = selectedItem();
      const ctx = currentChannelCtx(it);
      const msgEl = document.getElementById("ccbMsg");
      const sendBtn = document.getElementById("ccbSendBtn");
      const refreshBtn = document.getElementById("ccbRefreshBtn");
      const hint = document.getElementById("ccbHint");
      if (!msgEl || !sendBtn || !refreshBtn) return;

      const message = String(msgEl.value || "").trim();
      if (!message) return;
      if (!ctx.sessionId) return;

      sendBtn.disabled = true;
      refreshBtn.disabled = true;
      if (hint) hint.textContent = "发送中…";
      try {
        const r = await fetch("/api/codex/announce", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            projectId: ctx.projectId,
            channelName: ctx.channelName,
            sessionId: ctx.sessionId,
            cliType: ctx.cliType || "codex",
            message,
            ...buildUiUserSenderFields(),
          }),
        });
        if (!r.ok) {
          const detail = await parseResponseDetail(r);
          const tok = getToken();
          if ((r.status === 401 || r.status === 403) && !tok) {
            if (hint) hint.textContent = "发送失败：服务启用了 Token 校验，请先点右上角 Token 设置。";
          } else {
            if (hint) hint.textContent = "发送失败：" + (detail || ("HTTP " + r.status));
          }
          return;
        }
        const resp = await r.json().catch(() => ({}));
        const runId = resp && resp.run ? String(resp.run.id || "") : "";
        msgEl.value = "";
        resetMessageInputHeight(msgEl);
        if (hint) hint.textContent = "已发送，刷新回溯中…";
        await refreshCCB();
        if (runId) scheduleCCBPoll(5000);
      } catch (_) {
        if (hint) hint.textContent = "发送失败：网络或服务异常，请重试。";
      } finally {
        sendBtn.disabled = false;
        refreshBtn.disabled = false;
      }
    }

    async function retryRun(runMeta) {
      const rid = String((runMeta && runMeta.id) || "").trim();
      if (!rid) return;
      try {
        const full = await loadRun(rid);
        const run = (full && full.run) ? full.run : {};
        const message = String((full && full.message) || "").trim();
        const projectId = String(run.projectId || runMeta.projectId || "").trim();
        const channelName = String(run.channelName || runMeta.channelName || "").trim();
        const sessionId = String(run.sessionId || runMeta.sessionId || "").trim();
        const cliType = String(run.cliType || runMeta.cliType || "codex").trim() || "codex";
        if (!projectId || !channelName || !sessionId || !message) return;

        setHintText(STATE.panelMode, "重试中…");
        const r = await fetch("/api/codex/announce", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ projectId, channelName, sessionId, cliType, message, ...buildUiUserSenderFields() }),
        });
        if (!r.ok) {
          const detail = await parseResponseDetail(r);
          setHintText(STATE.panelMode, "重试失败：" + (detail || ("HTTP " + r.status)));
          return;
        }
        const resp = await r.json().catch(() => ({}));
        const runId = resp && resp.run ? String(resp.run.id || "") : "";
        if (STATE.panelMode === "conv") {
          await refreshConversationPanel();
          if (runId) scheduleConversationPoll(5000);
        } else {
          await refreshCCB();
          if (runId) scheduleCCBPoll(5000);
        }
      } catch (_) {
        setHintText(STATE.panelMode, "重试失败：网络或服务异常。");
      }
    }

    async function recoverRun(runMeta) {
      const rid = String((runMeta && runMeta.id) || "").trim();
      if (!rid) return;
      try {
        const full = await loadRun(rid);
        const run = (full && full.run) ? full.run : {};
        const original = String((full && full.message) || "").trim();
        const partial = String((full && full.partialMessage) || "").trim();
        const err = String((run && run.error) || (runMeta && runMeta.error) || "").trim();
        const hint = String((full && full.errorHint) || "").trim();
        const projectId = String(run.projectId || runMeta.projectId || "").trim();
        const channelName = String(run.channelName || runMeta.channelName || "").trim();
        const sessionId = String(run.sessionId || runMeta.sessionId || "").trim();
        if (!projectId || !channelName || !sessionId || !original) return;

        let recoveryMsg = "";
        recoveryMsg += "上一次执行已发生超时/中断，请做结果回收。\n";
        recoveryMsg += "要求：不要整段重跑耗时浏览器流程，优先基于已完成步骤做最终收口；如确需补测，仅补最小必要步骤后直接给最终结论。\n";
        recoveryMsg += "输出：\n";
        recoveryMsg += "1) 本次已完成事实（按步骤）\n";
        recoveryMsg += "2) 最终结论/判断\n";
        recoveryMsg += "3) 风险与待补项（如有）\n";
        recoveryMsg += "4) 下一步可执行动作（最多3条）\n";
        recoveryMsg += "\n原始消息：\n" + original + "\n";
        if (err) recoveryMsg += "\n错误信息：\n" + err + "\n";
        if (hint) recoveryMsg += "\n错误提示：\n" + hint + "\n";
        if (partial) recoveryMsg += "\n已回捞片段：\n" + partial + "\n";

        setHintText(STATE.panelMode, "回收中…");
        const r = await fetch("/api/codex/announce", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ projectId, channelName, sessionId, cliType: "codex", message: recoveryMsg, ...buildUiUserSenderFields() }),
        });
        if (!r.ok) {
          const detail = await parseResponseDetail(r);
          setHintText(STATE.panelMode, "回收失败：" + (detail || ("HTTP " + r.status)));
          return;
        }
        const resp = await r.json().catch(() => ({}));
        const runId = resp && resp.run ? String(resp.run.id || "") : "";
        if (STATE.panelMode === "conv") {
          await refreshConversationPanel();
          if (runId) scheduleConversationPoll(5000);
        } else {
          await refreshCCB();
          if (runId) scheduleCCBPoll(5000);
        }
      } catch (_) {
        setHintText(STATE.panelMode, "回收失败：网络或服务异常。");
      }
    }

    function setPanelMode(nextMode) {
      const mode = normalizePanelMode(nextMode);
      if (STATE.panelMode === mode) return;
      STATE.panelMode = mode;
      if (mode === "task") {
        STATE.taskModule = "tasks";
      }
      if (mode !== "conv") {
        PCONV.memoDrawerOpen = false;
        PCONV.memoDrawerSessionKey = "";
      }
      if (mode === "task" || mode === "org" || mode === "arch") {
        STATE.selectedSessionId = "";
        STATE.selectedSessionExplicit = false;
      }
      try {
        localStorage.setItem("taskDashboard.panelMode", STATE.panelMode);
        localStorage.setItem("taskDashboard.panelModeVer", "2");
      } catch (_) {}
      if (STATE.panelMode === "conv") {
        stopCCBPoll();
      } else {
        // 任务模式下仍可能在看会话详情：仅在没有会话上下文时停止轮询。
        if (!STATE.selectedSessionId && !PCONV.sending) stopConversationPoll();
      }
      setHash();
      render();
      // 移动端切换模式时回到列表视图
      if (isMobileViewport()) {
        showListView();
      }
    }

    function wire() {
      const qEl = document.getElementById("q");
      let qTimer = 0;
      qEl.addEventListener("input", (e) => {
        STATE.q = e.target.value || "";
        if (STATE.panelMode !== "conv") {
          STATE.selectedPath = "";
          STATE.selectedTaskId = "";
        }
        if (qTimer) clearTimeout(qTimer);
        qTimer = setTimeout(() => {
          setHash();
          render();
        }, 120);
      });
      const panelModeBtns = Array.from(document.querySelectorAll("[data-panel-mode]"));
      for (const btn of panelModeBtns) {
        const mode = normalizePanelMode(btn.getAttribute("data-panel-mode") || "channel");
        btn.addEventListener("click", () => setPanelMode(mode));
      }
      const convLayoutBtns = Array.from(document.querySelectorAll("[data-conv-layout]"));
      convLayoutBtns.forEach((btn) => {
        const mode = normalizeConversationListLayout(btn.getAttribute("data-conv-layout") || "flat");
        btn.addEventListener("click", () => setConversationListLayout(mode));
      });

      // viewTabs event listeners removed - viewTabs HTML removed from template

      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          const autoRecordMask = projectAutoRecordDrawerMaskNode();
          if (PROJECT_AUTO_UI.recordDrawerOpen && autoRecordMask && autoRecordMask.classList.contains("show")) {
            closeProjectAutoRecordDrawer();
            return;
          }
          const autoMask = projectAutoWrapNode();
          if (PROJECT_AUTO_UI.open && autoMask && autoMask.classList.contains("show")) {
            closeProjectAutoModal();
            return;
          }
          const memoMask = document.getElementById("convMemoDrawerMask");
          if (PCONV.memoDrawerOpen && memoMask && memoMask.classList.contains("show")) {
            closeConversationMemoDrawer();
            return;
          }
          const taskPushMask = document.getElementById("taskPushMask");
          if (TASK_PUSH_MODAL.open && taskPushMask && taskPushMask.classList.contains("show")) {
            closeTaskPushModal();
            return;
          }
          const queueForwardMask = queueForwardMaskNode();
          if (PCONV.queueForwardModal.open && queueForwardMask && queueForwardMask.classList.contains("show")) {
            closeQueueForwardModal();
            return;
          }
          // 移动端：如果详情视图打开，则返回列表
          if (isMobileViewport() && MOBILE_VIEW.current === "detail") {
            showListView();
            STATE.selectedPath = "";
            STATE.selectedTaskId = "";
            STATE.selectedSessionId = "";
            STATE.selectedSessionExplicit = false;
            updateSelectionUI();
            renderDetail(null);
            return;
          }
          setSelectedPath("");
        }
        const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.platform || "");
        const mod = isMac ? e.metaKey : e.ctrlKey;
        if (mod && (e.key === "k" || e.key === "K")) {
          e.preventDefault();
          const q = document.getElementById("q");
          if (q) q.focus();
        }
      });

      const rb = document.getElementById("ccbRefreshBtn");
      const sb = document.getElementById("ccbSendBtn");
      const tb = document.getElementById("ccbTokenBtn");
      const projectAutoHeaderBtn = projectAutoHeaderBtnNode();
      const projectRebuildBtn = projectRebuildBtnNode();
      const projectAutoCloseBtn = projectAutoCloseBtnNode();
      const projectAutoMask = projectAutoWrapNode();
      const projectAutoRecordDrawerMask = projectAutoRecordDrawerMaskNode();
      const projectAutoRecordDrawerCloseBtn = projectAutoRecordDrawerCloseBtnNode();
      const taskPushMask = document.getElementById("taskPushMask");
      const taskPushCloseBtn = document.getElementById("taskPushCloseBtn");
      if (rb) rb.addEventListener("click", (e) => { e.preventDefault(); refreshCCB(); });
      if (sb) sb.addEventListener("click", (e) => { e.preventDefault(); sendCCB(); });
      if (tb) tb.addEventListener("click", (e) => { e.preventDefault(); setTokenInteractive(); });
      if (projectAutoHeaderBtn) projectAutoHeaderBtn.addEventListener("click", (e) => {
        e.preventDefault();
        if (PROJECT_AUTO_UI.open) closeProjectAutoModal();
        else openProjectAutoModal();
      });
      if (projectRebuildBtn) projectRebuildBtn.addEventListener("click", (e) => {
        e.preventDefault();
        triggerProjectDashboardRebuild();
      });
      if (projectAutoCloseBtn) projectAutoCloseBtn.addEventListener("click", (e) => {
        e.preventDefault();
        closeProjectAutoModal();
      });
      if (projectAutoMask) projectAutoMask.addEventListener("click", (e) => {
        if (e.target === projectAutoMask) closeProjectAutoModal();
      });
      if (projectAutoRecordDrawerMask) projectAutoRecordDrawerMask.addEventListener("click", (e) => {
        if (e.target === projectAutoRecordDrawerMask) closeProjectAutoRecordDrawer();
      });
      if (projectAutoRecordDrawerCloseBtn) projectAutoRecordDrawerCloseBtn.addEventListener("click", (e) => {
        e.preventDefault();
        closeProjectAutoRecordDrawer();
      });
      if (taskPushMask) taskPushMask.addEventListener("click", (e) => {
        if (e.target === taskPushMask) closeTaskPushModal();
      });
      if (taskPushCloseBtn) taskPushCloseBtn.addEventListener("click", (e) => {
        e.preventDefault();
        closeTaskPushModal();
      });

      // CCB 输入框 Enter 发送
      const ccbMsgEl = document.getElementById("ccbMsg");
      if (ccbMsgEl) ccbMsgEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendCCB();
        }
      });

      const csb = document.getElementById("convSendBtn");
      if (csb) csb.addEventListener("click", (e) => { e.preventDefault(); sendConversationMessage(); });
      const ctb = document.getElementById("convTrainingSendBtn");
      if (ctb && !ctb.__convTrainingBound) {
        ctb.__convTrainingBound = true;
        ctb.addEventListener("click", (e) => {
          e.preventDefault();
          sendConversationTrainingMessage();
        });
      }
      const ccb = document.getElementById("convTrainingCloseBtn");
      if (ccb && !ccb.__convTrainingCloseBound) {
        ccb.__convTrainingCloseBound = true;
        ccb.addEventListener("click", (e) => {
          e.preventDefault();
          dismissConversationTrainingPrompt();
        });
      }
      const cms = document.getElementById("convMemoSaveBtn");
      if (cms) cms.addEventListener("click", (e) => { e.preventDefault(); saveCurrentComposerAsMemo(); });
      const cet = document.getElementById("convEnterSendToggle");
      if (cet && !cet.__convEnterSendBound) {
        cet.__convEnterSendBound = true;
        cet.addEventListener("click", (e) => {
          e.preventDefault();
          const next = setConversationEnterSendEnabled(!PCONV.enterSendEnabled);
          if (typeof renderConversationEnterSendToggle === "function") renderConversationEnterSendToggle(next);
          if (typeof refreshConversationComposerPlaceholder === "function") refreshConversationComposerPlaceholder();
        });
      }
      const cmsg = document.getElementById("convMsg");
      if (cmsg) cmsg.addEventListener("keydown", (e) => {
        if (handleConvMentionInputKeydown(e)) return;
        if (e.key === "Enter" && !e.shiftKey && PCONV.enterSendEnabled !== false) {
          e.preventDefault();
          sendConversationMessage();
        }
      });

      // 新增对话弹窗事件绑定
      const newConvMask = document.getElementById("newConvMask");
      const newConvCancel = document.getElementById("newConvCancelBtn");
      const newConvCreate = document.getElementById("newConvCreateBtn");
      const newConvModeCreate = document.getElementById("newConvModeCreate");
      const newConvModeAttach = document.getElementById("newConvModeAttach");
      const newConvProject = document.getElementById("newConvProject");
      const newConvChannel = document.getElementById("newConvChannel");
      const newConvCliType = document.getElementById("newConvCliType");
      const newConvModel = document.getElementById("newConvModel");
      const newConvSessionId = document.getElementById("newConvSessionId");
      const newConvInitMessage = document.getElementById("newConvInitMessage");
      const ccbNewConvBtn = document.getElementById("ccbNewConvBtn");
      const newConvMobileBtn = document.getElementById("newConvMobileBtn");
      const convSessionInfoMask = document.getElementById("convSessionInfoMask");
      const convSessionInfoCancelBtn = document.getElementById("convSessionInfoCancelBtn");
      const convSessionInfoSaveBtn = document.getElementById("convSessionInfoSaveBtn");
      const convAvatarPickerMask = document.getElementById("convAvatarPickerMask");
      const convAvatarPickerCancelBtn = document.getElementById("convAvatarPickerCancelBtn");
      const convAvatarPickerConfirmBtn = document.getElementById("convAvatarPickerConfirmBtn");
      const channelConvManageMask = document.getElementById("channelConvManageMask");
      const channelConvManageCancelBtn = document.getElementById("channelConvManageCancelBtn");
      const channelConvManageSaveBtn = document.getElementById("channelConvManageSaveBtn");

      if (newConvMask) newConvMask.addEventListener("click", (e) => {
        if (e.target === newConvMask) closeNewConvModal();
      });
      if (convSessionInfoMask) convSessionInfoMask.addEventListener("click", (e) => {
        if (e.target === convSessionInfoMask) closeConversationSessionInfoModal();
      });
      if (convSessionInfoCancelBtn) convSessionInfoCancelBtn.addEventListener("click", (e) => {
        e.preventDefault();
        closeConversationSessionInfoModal();
      });
      if (convSessionInfoSaveBtn) convSessionInfoSaveBtn.addEventListener("click", (e) => {
        e.preventDefault();
        saveConversationSessionInfo();
      });
      if (convAvatarPickerMask) convAvatarPickerMask.addEventListener("click", (e) => {
        if (e.target === convAvatarPickerMask) closeConversationAvatarPicker();
      });
      if (convAvatarPickerCancelBtn) convAvatarPickerCancelBtn.addEventListener("click", (e) => {
        e.preventDefault();
        closeConversationAvatarPicker();
      });
      if (convAvatarPickerConfirmBtn) convAvatarPickerConfirmBtn.addEventListener("click", (e) => {
        e.preventDefault();
        if (!SESSION_INFO_UI.open || !SESSION_INFO_UI.form) return;
        SESSION_INFO_UI.form.avatar_id = String(SESSION_INFO_UI.avatarPickerDraftId || "").trim();
        closeConversationAvatarPicker();
        renderConversationSessionInfoModal();
      });
      if (channelConvManageMask) channelConvManageMask.addEventListener("click", (e) => {
        if (e.target === channelConvManageMask) closeChannelConversationManageModal();
      });
      if (channelConvManageCancelBtn) channelConvManageCancelBtn.addEventListener("click", (e) => {
        e.preventDefault();
        closeChannelConversationManageModal();
      });
      if (channelConvManageSaveBtn) channelConvManageSaveBtn.addEventListener("click", (e) => {
        e.preventDefault();
        saveChannelConversationManageModal();
      });
      if (newConvCancel) newConvCancel.addEventListener("click", (e) => { e.preventDefault(); closeNewConvModal(); });
      if (newConvCreate) newConvCreate.addEventListener("click", (e) => { e.preventDefault(); createNewConversation(); });
      if (newConvModeCreate) newConvModeCreate.addEventListener("click", () => setNewConvMode("create"));
      if (newConvModeAttach) newConvModeAttach.addEventListener("click", () => setNewConvMode("attach"));

      // 项目选择变化时更新通道列表
      if (newConvProject) {
        newConvProject.addEventListener("change", () => {
          NEW_CONV_UI.projectId = String(newConvProject.value || "");
          updateNewConvChannels(newConvProject.value, "");
          applyNewConvBindingPreset();
          syncNewConvContextFields();
          syncNewConvInitMessage(false);
          if (NEW_CONV_UI.mode === "attach") setNewConvMode("attach");
        });
      }
      if (newConvChannel) {
        newConvChannel.addEventListener("change", () => {
          NEW_CONV_UI.channelName = String(newConvChannel.value || "");
          applyNewConvBindingPreset();
          syncNewConvContextFields();
          syncNewConvInitMessage(false);
          if (NEW_CONV_UI.mode === "attach") setNewConvMode("attach");
        });
      }
      if (newConvCliType) {
        newConvCliType.addEventListener("change", () => {
          syncNewConvModelUI();
        });
      }
      if (newConvSessionId) {
        newConvSessionId.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            createNewConversation();
          }
        });
      }
      if (newConvModel) {
        newConvModel.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            createNewConversation();
          }
        });
      }
      if (newConvInitMessage) {
        newConvInitMessage.addEventListener("input", () => {
          NEW_CONV_UI.initMessageDirty = true;
        });
      }

      // CCB区块的新增对话按钮
      if (ccbNewConvBtn) {
        ccbNewConvBtn.addEventListener("click", () => {
          openNewConvModal(STATE.project, STATE.channel);
        });
      }

      // 移动端的新增对话按钮
      if (newConvMobileBtn) {
        newConvMobileBtn.addEventListener("click", () => {
          openNewConvModal(STATE.project, STATE.channel);
        });
      }

      initConversationResizeHandle();

      // 新增通道弹窗事件绑定
      const newChannelMask = document.getElementById("newChannelMask");
      const newChannelCancel = document.getElementById("newChannelCancelBtn");
      const newChannelCreate = document.getElementById("newChannelCreateBtn");
      const newChannelReload = document.getElementById("newChannelReloadBtn");
      const newChannelAsideBtn = document.getElementById("newChannelAsideBtn");

      if (newChannelMask) newChannelMask.addEventListener("click", (e) => {
        if (e.target === newChannelMask) closeNewChannelModal();
      });
      if (newChannelCancel) newChannelCancel.addEventListener("click", (e) => { e.preventDefault(); closeNewChannelModal(); });
      if (newChannelCreate) newChannelCreate.addEventListener("click", (e) => { e.preventDefault(); createNewChannel(); });
      if (newChannelReload) newChannelReload.addEventListener("click", (e) => {
        e.preventDefault();
        location.reload();
      });
      bindNewChannelFormInputs();
      if (newChannelMask) {
        const syncNewChannelForm = (e) => {
          const target = e && e.target;
          const id = target && target.id;
          if (!id || !["newChannelKind", "newChannelKindCustom", "newChannelIndex", "newChannelName", "newChannelDesc", "newChannelRequirement"].includes(id)) return;
          if (!NEW_CHANNEL_UI.open) return;
          renderNewChannelWorkflowUi();
          if (NEW_CHANNEL_UI.phase !== "form") {
            NEW_CHANNEL_UI.phase = "form";
            setNewChannelVisible("newChannelReloadBtn", false);
          }
        };
        newChannelMask.addEventListener("input", syncNewChannelForm);
        newChannelMask.addEventListener("change", syncNewChannelForm);
      }
      if (typeof initChannelManageUi === "function") initChannelManageUi();

      // 侧边栏的新增通道按钮
      if (newChannelAsideBtn) {
        newChannelAsideBtn.addEventListener("click", () => {
          openNewChannelModal();
        });
      }

      // 通道对话区块的新增按钮
      const channelConvNewBtn = document.getElementById("channelConvNewBtn");
      if (channelConvNewBtn) {
        channelConvNewBtn.addEventListener("click", () => {
          openNewConvModal(STATE.project, STATE.channel);
        });
      }

      // Allow manual hash edits/back-forward (when there are history entries) to rehydrate state.
      window.addEventListener("hashchange", () => {
        parseHash();
        ensureBindingsLoadedForProject(STATE.project);
        render();
      });
      window.addEventListener("dragend", () => {
        clearTaskScheduleDragPayload();
        clearQueuedForwardDragPayload();
      });
      window.addEventListener("drop", () => {
        if (TASK_SCHEDULE_DND.active || TASK_SCHEDULE_DND.draggingPath) clearTaskScheduleDragPayload();
        if (PCONV.queueForwardDrag && (PCONV.queueForwardDrag.active || PCONV.queueForwardDrag.payload)) {
          clearQueuedForwardDragPayload();
        }
      });

      // Keep native scrolling behavior for the right panel.
    }

    function parseHash(opts = {}) {
      const preferredProjectId = String((opts && opts.preferredProjectId) || "").trim();
      const h = String(location.hash || "").replace(/^#/, "");
      const params = new URLSearchParams(h || "");
      let shouldNormalizeHash = false;
      const hasProjectParam = params.has("p");
      const hasChannelParam = params.has("c");
      const p = params.get("p");
      const c = params.get("c");
      const q = params.get("q");
      const t = params.get("t");
      const s = params.get("s");
      const vm = params.get("vm");
      const pm = params.get("pm");
      const tm = params.get("tm");
      const tl = params.get("tl");
      const cl = params.get("cl");
      const sid = params.get("sid");
      const sp = params.get("sp") || params.get("task_path");
      const tid = params.get("tid") || params.get("task_id");
      const ud = params.get("ud") || params.get("unified_detail");
      HASH_BOOTSTRAP.projectOnly = false;
      if (p && pages().some(x => x.id === p)) STATE.project = p;
      else if (!hasProjectParam && preferredProjectId && pages().some(x => x.id === preferredProjectId)) {
        STATE.project = preferredProjectId;
      }
      if (hasProjectParam && !hasChannelParam) {
        STATE.channel = "";
        HASH_BOOTSTRAP.projectOnly = true;
      }
      if (q !== null) STATE.q = q;
      if (t) STATE.type = t;
      if (s) STATE.status = s;
      if (tm) {
        const normalizedTaskModule = normalizeTaskModule(tm);
        STATE.taskModule = normalizedTaskModule;
        if (String(tm || "").trim().toLowerCase() !== normalizedTaskModule) {
          shouldNormalizeHash = true;
        }
      }
      if (tl) {
        const lane = String(tl || "").trim();
        const allowed = new Set(["全部", ...taskLaneOrderList()]);
        if (allowed.has(lane)) STATE.taskLane = lane;
      }
      if (cl) STATE.convListLayout = normalizeConversationListLayout(cl);
      else if (pm === "c") STATE.convListLayout = "channel";
      if (sid !== null) {
        STATE.selectedSessionId = String(sid || "").trim();
        STATE.selectedSessionExplicit = !!String(STATE.selectedSessionId || "").trim();
      }
      if (sp !== null) {
        STATE.selectedPath = normalizeScheduleTaskPath(sp);
        if (tid === null) STATE.selectedTaskId = "";
      }
      if (tid !== null) STATE.selectedTaskId = normalizeTaskStableId(tid);
      STATE.unifiedDetailRequested = ud === "1" || ud === "true";
      if (vm === "c") STATE.view = "comms";
      if (vm === "w") STATE.view = "work";
      if (pm === "c") STATE.panelMode = "conv";
      else if (pm === "g" || pm === "a" || pm === "arch") STATE.panelMode = "arch";
      else if (pm === "og" || pm === "org") STATE.panelMode = "org";
      else if (pm === "t") STATE.panelMode = "task";
      else if (pm === "o" || pm === "ch") STATE.panelMode = "channel";
      if (STATE.panelMode === "task" && !tm) {
        // 一级任务入口在未显式给出 tm 时，统一回到任务主视图；
        // 不能继续沿用本地缓存里的 schedule/org 子视图。
        STATE.taskModule = "tasks";
      }
      if (STATE.panelMode === "task" && normalizeTaskModule(STATE.taskModule) === "org") {
        STATE.panelMode = "org";
      }
      // layout 参数已废弃，不再处理
      if (!STATE.project || !pages().some(x => x.id === STATE.project)) {
        const ps = pages();
        if (preferredProjectId && ps.some(x => String(x.id || "") === preferredProjectId)) {
          STATE.project = preferredProjectId;
        } else {
          STATE.project = ps.length ? String(ps[0].id || "") : "";
        }
      }
      ensureChannel();
      if (STATE.project !== "overview") {
        const names = unionChannelNames(STATE.project);
        if (c) {
          const legacyMap = {
            "子级01-Agent编排": "子级01-智能体系统-Agent编排",
            "子级02-场景编排": "子级02-智能体系统-场景编排",
            "子级03-任务蓝图": "子级03-智能体系统-任务蓝图",
            "子级04-模型与安全": "子级04-智能体系统-模型与安全",
            "子级05-验证与指标": "子级05-智能体系统-验证与指标",
            "子级06-客户沟通训练": "子级06-智能体系统-客户沟通训练"
          };
          const mapped = legacyMap[c] || c;
          if (names.includes(mapped)) {
            STATE.channel = mapped;
            HASH_BOOTSTRAP.projectOnly = false;
          }
        }
      }
      if (shouldNormalizeHash) setHash();
    }

    function setHash() {
      try {
        const params = new URLSearchParams();
        params.set("p", STATE.project);
        if (STATE.channel) params.set("c", STATE.channel);
        if (STATE.q) params.set("q", STATE.q);
        if (STATE.type && STATE.type !== "全部") params.set("t", STATE.type);
        if (STATE.status && STATE.status !== "待办") params.set("s", STATE.status);
        if (STATE.view === "comms") params.set("vm", "c");
        if (STATE.panelMode === "conv") params.set("pm", "c");
        else if (STATE.panelMode === "arch") params.set("pm", "g");
        else if (STATE.panelMode === "org") params.set("pm", "og");
        else if (STATE.panelMode === "task") params.set("pm", "t");
        const convLayout = normalizeConversationListLayout(STATE.convListLayout);
        if (convLayout !== "channel") params.set("cl", convLayout);
        const moduleMode = normalizeTaskModule(STATE.taskModule);
        if (moduleMode !== "tasks") params.set("tm", moduleMode);
        if (STATE.taskLane && STATE.taskLane !== "全部") params.set("tl", STATE.taskLane);
        if (STATE.panelMode === "task" && STATE.selectedPath) params.set("sp", STATE.selectedPath);
        if (STATE.panelMode === "task" && STATE.selectedTaskId) params.set("tid", STATE.selectedTaskId);
        // layout 参数已废弃
        const s = params.toString();
        history.replaceState(null, "", s ? ("#" + s) : "#");
        localStorage.setItem("taskDashboard.taskModule", moduleMode);
        localStorage.setItem("taskDashboard.taskLane", String(STATE.taskLane || "全部"));
        localStorage.setItem("taskDashboard.convListLayout", convLayout);
      } catch (_) {}
    }

    // applyViewTabs function removed - viewTabs HTML removed from template

    function render() {
      if (typeof isTaskShareModeActive === "function" && isTaskShareModeActive()) {
        renderTaskShareModePage();
        return;
      }
      const qEl = document.getElementById("q");
      if (document.activeElement !== qEl) qEl.value = STATE.q;

      ensureBindingsLoadedForProject(STATE.project);
      ensureItemsLoadedForState(STATE.project);
      enforceMobileTaskOnlyMode();
      ensureChannel();
      renderChannelSelectorList();
      updateProjectInfo();
      renderProjectRootRevealBtn();
      renderProjectAutoPanel();
      renderProjectRebuildBtn();
      const autoPid = projectAutoAvailableProjectId();
      const autoProjectSwitched = autoPid && autoPid !== PROJECT_AUTO_UI.lastProjectId;
      PROJECT_AUTO_UI.lastProjectId = autoPid || "";
      if (autoPid) {
        const hasAutoCache = !!(PROJECT_AUTO.cache[autoPid] && PROJECT_AUTO.cache[autoPid].status);
        if (autoProjectSwitched || !hasAutoCache) {
          ensureProjectAutoStatus(autoPid, { maxAgeMs: 0 }).catch(() => {});
        }
      }
      ensureProjectAutoPolling();
      updateChannelSelectorName();
      updateCurrentChannelName();
      buildLeftList();
      buildMainList();
      applyPanelMode();
      renderTaskPushModal();
      refreshTaskScheduleDragUi();

      if (STATE.panelMode === "conv") {
        stopCCBPoll();
        renderDetail(null);
        refreshConversationPanel();
      } else if (STATE.panelMode === "org" || STATE.panelMode === "arch") {
        STATE.selectedPath = "";
        STATE.selectedTaskId = "";
        STATE.selectedSessionId = "";
        STATE.selectedSessionExplicit = false;
        stopCCBPoll();
        if (!PCONV.sending) stopConversationPoll();
        renderDetail(null);
        updateSelectionUI();
      } else {
        if (STATE.panelMode === "channel") {
          STATE.selectedSessionId = "";
          STATE.selectedSessionExplicit = false;
          buildChannelConversationList();
        } else {
          buildChannelConversationList();
        }
        ensureSelection();
        const selected = selectedItem();
        renderDetail(selected);
        if (STATE.unifiedDetailRequested && selected && isTaskItem(selected)) {
          STATE.unifiedDetailRequested = false;
          openUnifiedTaskDetailForSelection(selected, { source: "task-deeplink" });
        }
        stopCCBPoll();
        updateSelectionUI();
      }
    }

    async function bootstrapTaskPage() {
      // 清理旧的布局相关缓存（已废弃的功能）
      try {
        localStorage.removeItem("taskDashboard.layout");
        // 清理 URL hash 中的 layout 参数
        if (window.location.hash && window.location.hash.includes("l=")) {
          const hash = window.location.hash.slice(1);
          const params = new URLSearchParams(hash);
          params.delete("l");
          const newHash = params.toString();
          history.replaceState(null, "", newHash ? ("#" + newHash) : window.location.pathname + window.location.search);
        }
      } catch (_) {}

      const shareModeRequested = typeof isTaskShareModeRequested === "function" && isTaskShareModeRequested();
      const rawHash = String(window.location.hash || "").replace(/^#/, "").trim();
      const shouldRewriteLegacyTaskHash = /(?:^|&)(?:tm|mode)=schedule(?:&|$)/.test(rawHash);
      const hasConvLayoutInHash = /(?:^|&)cl=/.test(rawHash);
      const shouldUseDefaultChannelLanding = !rawHash && !shareModeRequested;
      try {
        const vm = localStorage.getItem("taskDashboard.view");
        if (vm === "work" || vm === "comms") STATE.view = vm;
        const convSort = localStorage.getItem("taskDashboard.convSort");
        if (convSort) STATE.convSort = normalizeConversationSort(convSort);
        const convListLayout = localStorage.getItem("taskDashboard.convListLayout");
        if (convListLayout && hasConvLayoutInHash) STATE.convListLayout = normalizeConversationListLayout(convListLayout);
        const itemSort = localStorage.getItem("taskDashboard.itemSort");
        if (itemSort) STATE.itemSort = normalizeItemSort(itemSort);
        const pm = localStorage.getItem("taskDashboard.panelMode");
        const pmVer = localStorage.getItem("taskDashboard.panelModeVer");
        if (pm === "ops") STATE.panelMode = "channel";
        else if (pm === "channel" || pm === "task" || pm === "conv" || pm === "arch") STATE.panelMode = pm;
        else if (pm === "org") STATE.panelMode = (pmVer === "2" ? "org" : "arch");
        const tm = localStorage.getItem("taskDashboard.taskModule");
        if (tm) STATE.taskModule = normalizeTaskModule(tm);
        if (STATE.panelMode === "task" && normalizeTaskModule(STATE.taskModule) === "org") {
          STATE.panelMode = "org";
        }
        const tl = localStorage.getItem("taskDashboard.taskLane");
        if (tl) {
          const allowed = new Set(["全部", ...taskLaneOrderList()]);
          if (allowed.has(tl)) STATE.taskLane = tl;
        }
        const sp = localStorage.getItem("taskDashboard.selectedPath");
        if (sp) STATE.selectedPath = normalizeScheduleTaskPath(sp);
        const stid = localStorage.getItem("taskDashboard.selectedTaskId");
        if (stid) STATE.selectedTaskId = String(stid || "").trim();
        const ss = localStorage.getItem("taskDashboard.selectedSessionId");
        if (ss) STATE.selectedSessionId = ss;
        if (shouldUseDefaultChannelLanding) {
          STATE.panelMode = "channel";
          STATE.selectedPath = "";
          STATE.selectedTaskId = "";
          STATE.selectedSessionId = "";
          STATE.selectedSessionExplicit = false;
          localStorage.setItem("taskDashboard.panelMode", "channel");
          localStorage.setItem("taskDashboard.panelModeVer", "2");
          localStorage.removeItem("taskDashboard.selectedPath");
          localStorage.removeItem("taskDashboard.selectedTaskId");
          localStorage.removeItem("taskDashboard.selectedSessionId");
        }
      } catch (_) {}
      restoreAsideWidthFromStorage();
      restoreConvAsideWidthFromStorage();
      initBackLink();
      let healthInfo = null;
      if (!shareModeRequested) {
        healthInfo = await fetchHealthInfo();
        applyEnvironmentBadge(healthInfo);
      }
      // Initialize message input components
      initAllMessageInputs();
      // Initialize mobile view switch
      initMobileViewSwitch();
      // Initialize channel selector
      initChannelSelector();
      // Initialize cross-tab unread/memo count sync
      initConversationCrossTabSync();
      const preferredProjectId = shareModeRequested
        ? taskShareModeText((taskShareModeParams && taskShareModeParams().project_id) || "")
        : String(
          (healthInfo && (healthInfo.project_id || healthInfo.projectId)) || ""
        ).trim();
      if (shareModeRequested) {
        await loadTaskShareModeBootstrap();
      } else {
        parseHash({ preferredProjectId });
        if (shouldRewriteLegacyTaskHash) {
          try {
            const rewriteParams = new URLSearchParams(String(window.location.hash || "").replace(/^#/, "").trim());
            rewriteParams.delete("tm");
            rewriteParams.delete("mode");
            rewriteParams.set("p", STATE.project);
            rewriteParams.set("pm", "t");
            if (STATE.channel) rewriteParams.set("c", STATE.channel);
            else rewriteParams.delete("c");
            if (STATE.taskLane && STATE.taskLane !== "全部") rewriteParams.set("tl", STATE.taskLane);
            else rewriteParams.delete("tl");
            history.replaceState(null, "", "#" + rewriteParams.toString());
          } catch (_) {
            setHash();
          }
        }
      }
      wire();
      // Initialize file upload handling
      initFileUpload();
      initConversationListScrollMonitor();
      initConversationMemoUi();
      initConversationFileUi();
      initConversationTaskUi();
      render();
      setTimeout(() => {
        if (
          STATE.panelMode === "task"
          && normalizeTaskModule(STATE.taskModule) === "tasks"
          && /(?:^|&)(?:tm|mode)=schedule(?:&|$)/.test(String(window.location.hash || "").replace(/^#/, "").trim())
        ) {
          setHash();
        }
      }, 0);
    }

    queueMicrotask(() => {
      bootstrapTaskPage().catch((err) => {
        try { console.error("task bootstrap failed:", err); } catch (_) {}
      });
    });

    // File upload handling for conversation composer attachments (per session draft)

    function initFileUpload() {
      const uploadBtn = document.getElementById("convUploadBtn");
      const fileInput = document.getElementById("convFileInput");
      const convMsg = document.getElementById("convMsg");
      const composer = document.querySelector(".convcomposer");
      const convWrap = document.getElementById("convWrap");
      const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
      const CONV_COMPOSER_DROP_HOTZONE = { top: 52, right: 16, bottom: 14, left: 16 };

      if (!uploadBtn || !fileInput) return;

      function readFileAsDataUrl(file) {
        return new Promise((resolve) => {
          try {
            const reader = new FileReader();
            reader.onload = (ev) => resolve(String((ev && ev.target && ev.target.result) || ""));
            reader.onerror = () => resolve("");
            reader.readAsDataURL(file);
          } catch (_) {
            resolve("");
          }
        });
      }

      function hasTransferFiles(dataTransfer) {
        if (!dataTransfer) return false;
        const files = dataTransfer.files;
        if (files && files.length > 0) return true;
        const types = dataTransfer.types;
        if (!types) return false;
        return Array.from(types).includes("Files");
      }

      function collectFilesFromPasteEvent(e) {
        const out = [];
        const seenStrong = new Set();
        const seenLoose = new Set();
        const dt = e && e.clipboardData;
        if (!dt) return out;
        const listA = dt.files ? Array.from(dt.files) : [];
        const listB = dt.items ? Array.from(dt.items).map((it) => (it && it.kind === "file" ? it.getAsFile() : null)).filter(Boolean) : [];
        for (const f of [...listA, ...listB]) {
          const name = String((f && f.name) || "").trim().toLowerCase();
          const size = String((f && f.size) || 0);
          const type = String((f && f.type) || "").trim().toLowerCase();
          const lm = String((f && f.lastModified) || 0);
          // 同一张剪贴板图片常会同时出现在 files/items，两者 lastModified 可能不同。
          // 先用强指纹，再用不含 lastModified 的弱指纹做一次兜底去重。
          const strongKey = [name, size, type, lm].join("|");
          const looseKey = [name, size, type].join("|");
          if (seenStrong.has(strongKey) || seenLoose.has(looseKey)) continue;
          seenStrong.add(strongKey);
          seenLoose.add(looseKey);
          out.push(f);
        }
        return out;
      }

      function parseMentionTargetFromDataTransfer(dataTransfer) {
        if (!dataTransfer || typeof dataTransfer.getData !== "function") return null;
        const raw = String(dataTransfer.getData(CONV_MENTION_DND_MIME) || "").trim();
        if (!raw) return null;
        try {
          return normalizeMentionTargetItem(JSON.parse(raw));
        } catch (_) {
          return null;
        }
      }

      function getComposerTransferPayload(dataTransfer) {
        const mentionTarget = parseMentionTargetFromDataTransfer(dataTransfer);
        const hasFiles = hasTransferFiles(dataTransfer);
        if (!hasFiles && !mentionTarget) return null;
        return { mentionTarget, hasFiles };
      }

      function composerDropHotzoneRect() {
        if (!composer || typeof composer.getBoundingClientRect !== "function") return null;
        const rect = composer.getBoundingClientRect();
        return {
          top: rect.top - CONV_COMPOSER_DROP_HOTZONE.top,
          right: rect.right + CONV_COMPOSER_DROP_HOTZONE.right,
          bottom: rect.bottom + CONV_COMPOSER_DROP_HOTZONE.bottom,
          left: rect.left - CONV_COMPOSER_DROP_HOTZONE.left,
        };
      }

      function isPointInComposerDropHotzone(clientX, clientY) {
        const rect = composerDropHotzoneRect();
        if (!rect) return false;
        const x = Number(clientX || 0);
        const y = Number(clientY || 0);
        return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
      }

      function setComposerDropActive(active) {
        if (!composer) return;
        composer.classList.toggle("drop-active", !!active);
      }

      async function handleComposerDrop(e, mentionTarget) {
        const files = e && e.dataTransfer && e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
        if (!files.length && !mentionTarget) return;
        e.preventDefault();
        e.stopPropagation();
        setComposerDropActive(false);
        if (mentionTarget) {
          const draftKey = currentConvComposerDraftKey();
          if (!draftKey) {
            setHintText("conv", "请先选择对话后再添加协同对象。");
            return;
          }
          const inserted = insertMentionToComposerInput(mentionTarget);
          if (inserted.ok) {
            setHintText("conv", "已插入协同对象：@" + String(inserted.label || mentionInsertLabel(mentionTarget) || ""));
          }
          return;
        }
        await uploadFilesToComposer(files, "拖拽");
      }

      async function uploadFilesToComposer(files, sourceLabel) {
        const list = (Array.isArray(files) ? files : []).filter(Boolean);
        if (!list.length) return;
        const draftKeyAtStart = currentConvComposerDraftKey();
        if (!draftKeyAtStart) {
          alert("请先选择对话后再上传附件");
          return;
        }
        let okCount = 0;
        for (const file of list) {
          const name = String(file && file.name || "").trim() || "file";
          const size = Number(file && file.size || 0);
          if (size <= 0) {
            alert("附件为空：" + name);
            continue;
          }
          if (size > MAX_UPLOAD_BYTES) {
            alert("附件超限（最大20MB）：" + name);
            continue;
          }
          const formData = new FormData();
          formData.append("file", file);
          try {
            const token = localStorage.getItem("taskDashboard.token");
            const headers = {};
            if (token) headers["Authorization"] = "Bearer " + token;
            const resp = await fetch("/api/codex/upload", {
              method: "POST",
              headers,
              body: formData,
            });
            const result = await resp.json().catch(() => ({}));
            if (!resp.ok || !result.ok) {
              const msg = String(result.message || result.error || ("HTTP " + resp.status));
              alert("上传失败：" + name + "（" + msg + "）");
              continue;
            }
            const mimeType = String(result.mimeType || file.type || "");
            const isImage = mimeType.startsWith("image/");
            const dataUrl = isImage ? await readFileAsDataUrl(file) : "";
            appendConvComposerAttachmentByKey(draftKeyAtStart, {
              filename: String(result.filename || ""),
              originalName: String(result.originalName || name || "attachment"),
              url: String(result.url || ""),
              dataUrl,
              mimeType,
              size: Number(result.size || size || 0),
              isImage,
            });
            okCount += 1;
          } catch (err) {
            alert("上传失败：" + name + "（" + String((err && err.message) || err || "未知错误") + "）");
          }
        }
        if (okCount > 0) {
          const source = String(sourceLabel || "上传");
          setHintText("conv", source + "成功 " + okCount + " 个附件。");
        }
      }

      uploadBtn.addEventListener("click", () => fileInput.click());

      if (convMsg) {
        convMsg.addEventListener("input", () => {
          setConvComposerTextForCurrentSession(convMsg.value || "");
          updateConvMentionSuggestByInput();
        });
        convMsg.addEventListener("click", () => updateConvMentionSuggestByInput());
        convMsg.addEventListener("keyup", (e) => {
          const key = String((e && e.key) || "");
          if (key === "ArrowDown" || key === "ArrowUp" || key === "Enter" || key === "Escape") return;
          updateConvMentionSuggestByInput();
        });
        convMsg.addEventListener("paste", async (e) => {
          const files = collectFilesFromPasteEvent(e);
          if (!files.length) return;
          e.preventDefault();
          e.stopPropagation();
          await uploadFilesToComposer(files, "粘贴");
        });
      }

      fileInput.addEventListener("change", async (e) => {
        const files = e && e.target && e.target.files ? Array.from(e.target.files) : [];
        if (!files.length) return;
        await uploadFilesToComposer(files, "选择");
        fileInput.value = "";
      });

      if (composer) {
        document.addEventListener("click", (e) => {
          const target = e && e.target;
          if (target && composer.contains(target)) return;
          hideConvMentionSuggest();
        });
        composer.addEventListener("dragenter", (e) => {
          const payload = getComposerTransferPayload(e.dataTransfer);
          if (!payload) return;
          e.preventDefault();
          setComposerDropActive(true);
        });
        composer.addEventListener("dragover", (e) => {
          const payload = getComposerTransferPayload(e.dataTransfer);
          if (!payload) return;
          e.preventDefault();
          if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
          setComposerDropActive(true);
        });
        composer.addEventListener("dragleave", (e) => {
          const current = e.currentTarget;
          const related = e.relatedTarget;
          if (current && related && current.contains && current.contains(related)) return;
          setComposerDropActive(false);
        });
        composer.addEventListener("drop", async (e) => {
          const payload = getComposerTransferPayload(e.dataTransfer);
          if (!payload) return;
          await handleComposerDrop(e, payload.mentionTarget);
        });
      }
      if (convWrap && composer && convWrap !== composer) {
        convWrap.addEventListener("dragenter", (e) => {
          const payload = getComposerTransferPayload(e.dataTransfer);
          if (!payload) return;
          if (!isPointInComposerDropHotzone(e.clientX, e.clientY)) return;
          e.preventDefault();
          setComposerDropActive(true);
        });
        convWrap.addEventListener("dragover", (e) => {
          const payload = getComposerTransferPayload(e.dataTransfer);
          if (!payload) return;
          const inHotzone = isPointInComposerDropHotzone(e.clientX, e.clientY);
          setComposerDropActive(inHotzone);
          if (!inHotzone) return;
          e.preventDefault();
          if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
        });
        convWrap.addEventListener("dragleave", (e) => {
          const current = e.currentTarget;
          const related = e.relatedTarget;
          if (current && related && current.contains && current.contains(related)) return;
          setComposerDropActive(false);
        });
        convWrap.addEventListener("drop", async (e) => {
          if (e.defaultPrevented) return;
          const payload = getComposerTransferPayload(e.dataTransfer);
          if (!payload) return;
          if (!isPointInComposerDropHotzone(e.clientX, e.clientY)) {
            setComposerDropActive(false);
            return;
          }
          await handleComposerDrop(e, payload.mentionTarget);
        });
        window.addEventListener("dragend", () => setComposerDropActive(false), true);
        window.addEventListener("drop", () => setComposerDropActive(false), true);
      }
    }

    function renderAttachments() {
      const key = PCONV.composerBoundDraftKey || currentConvComposerDraftKey();
      renderConvComposerMentionsByKey(key);
      renderConvComposerAttachmentsByKey(key);
      renderConvComposerReplyContextByKey(key);
    }

    function clearAttachments() {
      const key = String(PCONV.composerBoundDraftKey || currentConvComposerDraftKey() || "").trim();
      if (!key) {
        renderAttachments();
        return;
      }
      updateConvComposerDraftByKey(key, (d) => { d.attachments = []; });
      renderAttachments();
    }

    let IMAGE_PREVIEW_READY = false;
    function ensureImagePreview() {
      if (IMAGE_PREVIEW_READY) return;
      IMAGE_PREVIEW_READY = true;
      const mask = document.createElement("div");
      mask.className = "img-preview-mask";
      mask.id = "imgPreviewMask";
      mask.innerHTML = `
        <div class="img-preview-dialog" role="dialog" aria-modal="true" aria-label="图片预览">
          <button type="button" class="img-preview-close" id="imgPreviewClose" aria-label="关闭">×</button>
          <img class="img-preview-img" id="imgPreviewImg" alt="preview" />
          <div class="img-preview-cap" id="imgPreviewCap"></div>
        </div>
      `;
      document.body.appendChild(mask);

      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeImagePreview();
      });
      const closeBtn = document.getElementById("imgPreviewClose");
      if (closeBtn) closeBtn.addEventListener("click", closeImagePreview);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeImagePreview();
      });
    }

    function openImagePreview(src, caption = "") {
      const url = String(src || "").trim();
      if (!url) return;
      ensureImagePreview();
      const mask = document.getElementById("imgPreviewMask");
      const img = document.getElementById("imgPreviewImg");
      const cap = document.getElementById("imgPreviewCap");
      if (!mask || !img || !cap) return;
      img.src = url;
      cap.textContent = String(caption || "");
      mask.classList.add("show");
    }

    function closeImagePreview() {
      const mask = document.getElementById("imgPreviewMask");
      const img = document.getElementById("imgPreviewImg");
      if (mask) mask.classList.remove("show");
      if (img) img.src = "";
    }

    window.addEventListener("focus", triggerConversationRefreshOnResume);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) triggerConversationRefreshOnResume();
    });
    window.addEventListener("pageshow", triggerConversationRefreshOnResume);
  

    // Ambient blobs (low-energy). No-op when user prefers reduced motion.
    (function () {
      const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion) return;

      class Blob {
        constructor(el, index) {
          this.el = el;
          const w = window.innerWidth;
          const h = window.innerHeight;
          this.x = (index % 3) * (w / 3) - (w * 0.15);
          this.y = (Math.floor(index / 3) % 3) * (h / 3) - (h * 0.15);
          this.vx = (Math.random() - 0.5) * 0.08;
          this.vy = (Math.random() - 0.5) * 0.08;
          this.z = 0.9 + Math.random() * 0.2;
          this.vz = (Math.random() - 0.5) * 0.0005;
          this.bounds = () => {
            const ww = window.innerWidth;
            const hh = window.innerHeight;
            return { minX: -ww * 0.3, maxX: ww * 1.0, minY: -hh * 0.3, maxY: hh * 1.0 };
          };
        }
        update() {
          this.x += this.vx; this.y += this.vy; this.z += this.vz;
          const b = this.bounds();
          if (this.x < b.minX || this.x > b.maxX) this.vx *= -1;
          if (this.y < b.minY || this.y > b.maxY) this.vy *= -1;
          if (this.z < 0.8) this.vz += 0.001;
          if (this.z > 1.2) this.vz -= 0.001;
          this.render();
        }
        render() {
          let blur = 0;
          let opacity = 0.8;
          if (this.z > 1.1) {
            const t = (this.z - 1.1) / 0.1;
            blur = Math.max(0, 5 * (1 - t));
            opacity = 0.9 + t * 0.1;
          } else {
            const t = (1.1 - this.z) / 0.3;
            blur = 5 + t * 15;
            opacity = 0.9 - t * 0.3;
          }
          blur = Math.min(20, Math.max(0, blur));
          opacity = Math.min(1, Math.max(0.4, opacity));
          this.el.style.transform = `translate3d(${this.x}px, ${this.y}px, 0) scale(1)`;
          this.el.style.filter = `blur(${blur}px)`;
          this.el.style.opacity = String(opacity);
        }
      }

      const blobs = Array.from(document.querySelectorAll(".blob")).map((el, i) => new Blob(el, i));
      function animate() {
        blobs.forEach((b) => b.update());
        requestAnimationFrame(animate);
      }
      animate();
    })();
  
