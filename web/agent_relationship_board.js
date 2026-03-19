(() => {
  const DATA = JSON.parse(document.getElementById("data")?.textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const TOKEN_KEY = "taskDashboard.token";
  const STORAGE_PREFIX = "taskDashboard.agentRelationshipBoard.v2";
  const CARD_WIDTH = 228;
  const CARD_HEIGHT = 116;
  const GROUP_PADDING = 24;
  const ROWS = {
    master: { label: "总管", y: 120, accent: "#63dac8" },
    assist: { label: "营运（辅助）", y: 470, accent: "#7db7ff" },
    dev: { label: "开发（子级）", y: 1030, accent: "#f4c86d" },
    other: { label: "新业务（其他）", y: 1590, accent: "#ba9cff" },
  };
  const WINDOW_MS = {
    "1h": 60 * 60 * 1000,
    "3h": 3 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
  };
  const REPLAY_VISIBLE_SPAN_MS = 60 * 60 * 1000;
  const RELATION_TYPES = {
    business: { label: "主责", color: "rgba(99,218,200,0.92)" },
    support: { label: "支撑", color: "rgba(125,183,255,0.9)" },
    dependency: { label: "依赖", color: "rgba(244,200,109,0.92)" },
  };
  const STATE = {
    projectId: "",
    projectName: "",
    channelHint: "",
    sessionHint: "",
    windowKey: "1h",
    customRange: { startMs: 0, endMs: 0 },
    sessions: [],
    runs: [],
    groups: [],
    nodes: [],
    messages: [],
    commLinks: [],
    manualRelations: [],
    activeRelationType: "business",
    visibleRelations: {
      business: true,
      support: true,
      dependency: true,
      message: true,
      labels: true,
    },
    selectedGroupId: "",
    selectedSessionId: "",
    selectedMessageId: "",
    selectedRelationId: "",
    dragNode: null,
    dragGroup: null,
    resizeGroup: null,
    dragLayerGroupId: "",
    relationDraft: null,
    pan: null,
    zoom: 1,
    replayMode: false,
    replayPlaying: false,
    replaySpeed: 1,
    replayCursorTs: null,
  };

  const dom = {
    taskLink: document.getElementById("taskLink"),
    curtainLink: document.getElementById("curtainLink"),
    refreshBtn: document.getElementById("refreshBtn"),
    saveLayoutBtn: document.getElementById("saveLayoutBtn"),
    exportConfigBtn: document.getElementById("exportConfigBtn"),
    copyConfigBtn: document.getElementById("copyConfigBtn"),
    envBadge: document.getElementById("envBadge"),
    timeTabs: Array.from(document.querySelectorAll("[data-window]")),
    customRange: document.getElementById("customRange"),
    customStartInput: document.getElementById("customStartInput"),
    customEndInput: document.getElementById("customEndInput"),
    customApplyBtn: document.getElementById("customApplyBtn"),
    relationTypeButtons: Array.from(document.querySelectorAll("[data-relation-type]")),
    visibilityButtons: Array.from(document.querySelectorAll("[data-visibility]")),
    toggleLayersBtn: document.getElementById("toggleLayersBtn"),
    toggleDetailBtn: document.getElementById("toggleDetailBtn"),
    boardMeta: document.getElementById("boardMeta"),
    summaryMeta: document.getElementById("summaryMeta"),
    statusBanner: document.getElementById("statusBanner"),
    stageWrap: document.getElementById("stageWrap"),
    stageViewport: document.getElementById("stageViewport"),
    stage: document.getElementById("stage"),
    groupsLayer: document.getElementById("groupsLayer"),
    groupChipLayer: document.getElementById("groupChipLayer"),
    nodesLayer: document.getElementById("nodesLayer"),
    linesSvg: document.getElementById("linesSvg"),
    layersPanel: document.getElementById("layersPanel"),
    openLayersBtn: document.getElementById("openLayersBtn"),
    closeLayersBtn: document.getElementById("closeLayersBtn"),
    groupList: document.getElementById("groupList"),
    searchInput: document.getElementById("searchInput"),
    rosterList: document.getElementById("rosterList"),
    detailPanel: document.getElementById("detailPanel"),
    openDetailBtn: document.getElementById("openDetailBtn"),
    closeDetailBtn: document.getElementById("closeDetailBtn"),
    detailTitle: document.getElementById("detailTitle"),
    detailBody: document.getElementById("detailBody"),
    playBtn: document.getElementById("playBtn"),
    pauseBtn: document.getElementById("pauseBtn"),
    replayResetBtn: document.getElementById("replayResetBtn"),
    replaySlider: document.getElementById("replaySlider"),
    replayMarkers: document.getElementById("replayMarkers"),
    replayCurrentTime: document.getElementById("replayCurrentTime"),
    replayEndTime: document.getElementById("replayEndTime"),
    replaySpeedButtons: Array.from(document.querySelectorAll("[data-replay-speed]")),
    miniMap: document.getElementById("miniMap"),
    zoomInBtn: document.getElementById("zoomInBtn"),
    zoomOutBtn: document.getElementById("zoomOutBtn"),
    zoomResetBtn: document.getElementById("zoomResetBtn"),
    bubbleTooltip: document.getElementById("bubbleTooltip"),
    messageDialog: document.getElementById("messageDialog"),
    messageDialogTitle: document.getElementById("messageDialogTitle"),
    messageDialogBody: document.getElementById("messageDialogBody"),
    messageDialogCloseBtn: document.getElementById("messageDialogCloseBtn"),
  };

  function safeText(value, fallback = "") {
    const text = String(value == null ? "" : value).trim();
    return text || fallback;
  }

  function firstText(values, fallback = "") {
    for (const value of values || []) {
      const text = safeText(value);
      if (text) return text;
    }
    return fallback;
  }

  function dateMs(value) {
    if (!value) return 0;
    const n = Date.parse(String(value));
    return Number.isFinite(n) ? n : 0;
  }

  function pad2(value) {
    return String(Math.max(0, Number(value) || 0)).padStart(2, "0");
  }

  function fmtTime(value) {
    const ts = typeof value === "number" ? value : dateMs(value);
    if (!ts) return "--:--";
    return new Date(ts).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function fmtDateTime(value) {
    const ts = typeof value === "number" ? value : dateMs(value);
    if (!ts) return "-";
    return new Date(ts).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).replace(",", " ");
  }

  function formatDateTimeLocal(value) {
    const ts = typeof value === "number" ? value : dateMs(value);
    if (!ts) return "";
    const dt = new Date(ts);
    return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}T${pad2(dt.getHours())}:${pad2(dt.getMinutes())}`;
  }

  function parseDateTimeLocal(value) {
    const text = safeText(value);
    return text ? dateMs(text) : 0;
  }

  function authHeaders(base = {}) {
    const headers = { ...(base || {}) };
    try {
      const token = localStorage.getItem(TOKEN_KEY);
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch (_) {}
    return headers;
  }

  async function fetchJson(url) {
    const resp = await fetch(url, { cache: "no-store", headers: authHeaders() });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  }

  function qs() {
    try {
      const search = new URLSearchParams(window.location.search || "");
      const hash = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
      return {
        projectId: firstText([
          search.get("project_id"),
          search.get("projectId"),
          hash.get("p"),
          DATA.project_id,
          DATA.projectId,
        ]),
        channelName: firstText([
          search.get("channel_name"),
          search.get("channelName"),
          hash.get("c"),
          DATA.channel_name,
          DATA.channelName,
        ]),
        sessionId: firstText([
          search.get("session_id"),
          search.get("sessionId"),
          hash.get("sid"),
          DATA.session_id,
          DATA.sessionId,
        ]),
      };
    } catch (_) {
      return { projectId: "", channelName: "", sessionId: "" };
    }
  }

  function projectCatalog() {
    const primary = Array.isArray(DATA.projects) ? DATA.projects : [];
    const overviewProjects = Array.isArray(DATA.overview && DATA.overview.projects) ? DATA.overview.projects : [];
    const merged = [
      ...primary.map((item) => ({
        project_id: safeText(item.id || item.project_id),
        project_name: firstText([item.name, item.project_name, item.id]),
      })),
      ...overviewProjects.map((item) => ({
        project_id: safeText(item.project_id || item.id),
        project_name: firstText([item.project_name, item.name, item.id]),
      })),
    ].filter((item) => item.project_id);
    const seen = new Set();
    return merged.filter((item) => {
      if (seen.has(item.project_id)) return false;
      seen.add(item.project_id);
      return true;
    });
  }

  function projectMetaById(projectId) {
    const pid = safeText(projectId);
    if (!pid) return null;
    return projectCatalog().find((item) => safeText(item.project_id) === pid) || null;
  }

  function normalizeSession(raw) {
    if (!raw || typeof raw !== "object") return null;
    const sessionId = firstText([raw.id, raw.session_id, raw.sessionId]);
    if (!sessionId) return null;
    const runtimeState = raw.runtime_state && typeof raw.runtime_state === "object" ? raw.runtime_state : {};
    const channelName = firstText([raw.channel_name, raw.channelName]);
    return {
      session_id: sessionId,
      alias: firstText([raw.alias, raw.display_name, raw.displayName, channelName, sessionId]),
      channel_name: channelName,
      project_id: firstText([raw.project_id, raw.projectId], STATE.projectId),
      project_name: firstText([raw.project_name, raw.projectName], STATE.projectName),
      cli_type: firstText([raw.cli_type, raw.cliType], "codex"),
      status: firstText([runtimeState.display_state, runtimeState.internal_state, raw.status], "idle"),
      environment: firstText([raw.environment], DATA.environment || "stable"),
      role: firstText([raw.session_role, raw.sessionRole, raw.desc], "协作Agent"),
      desc: firstText([raw.desc]),
    };
  }

  function normalizeRunStatus(raw) {
    const status = firstText([raw && raw.status], "").toLowerCase();
    const display = firstText([raw && raw.display_state, raw && raw.displayState], "").toLowerCase();
    if (status === "done" || status === "error" || status === "interrupted") return status;
    return display || status || "unknown";
  }

  function normalizeSenderType(raw, fallbackRole = "") {
    const text = safeText(raw).toLowerCase();
    if (["user", "human", "person", "requester", "用户", "人类"].includes(text)) return "user";
    if (["agent", "assistant", "bot", "model", "channel", "智能体", "助手", "模型", "通道"].includes(text)) return "agent";
    if (["system", "runtime", "scheduler", "ccb", "系统", "运行时", "调度器"].includes(text)) return "system";
    if (["legacy", "unknown", "default", "历史", "未知"].includes(text)) return "legacy";
    const role = safeText(fallbackRole).toLowerCase();
    if (role === "user") return "user";
    if (role === "assistant") return "agent";
    return "legacy";
  }

  function readCommunicationViewMeta(raw) {
    if (raw && raw.communication_view && typeof raw.communication_view === "object") return raw.communication_view;
    if (raw && raw.communicationView && typeof raw.communicationView === "object") return raw.communicationView;
    return {};
  }

  function readStructuredSender(raw) {
    const obj = (raw && typeof raw === "object") ? raw : {};
    const nested = (obj.sender && typeof obj.sender === "object") ? obj.sender : {};
    const typeRaw = firstText([
      obj.sender_type, obj.senderType, obj.sender_role, obj.senderRole,
      nested.sender_type, nested.senderType, nested.sender_role, nested.senderRole, nested.type, nested.role,
    ]);
    const id = firstText([
      obj.sender_id, obj.senderId,
      nested.sender_id, nested.senderId, nested.id,
    ]);
    const name = firstText([
      obj.sender_name, obj.senderName,
      nested.sender_name, nested.senderName, nested.name,
    ]);
    return {
      type: normalizeSenderType(typeRaw, ""),
      id,
      name,
    };
  }

  function normalizeMessageKind(raw) {
    const kind = safeText(raw).toLowerCase();
    const allow = new Set([
      "system_callback",
      "system_callback_summary",
      "restart_recovery_summary",
      "user_input",
      "agent_output",
      "system_notice",
      "collab_update",
      "manual_update",
    ]);
    return allow.has(kind) ? kind : "";
  }

  function resolveMessageKind(raw) {
    const run = (raw && typeof raw === "object") ? raw : {};
    const communicationView = readCommunicationViewMeta(run);
    const cvKind = normalizeMessageKind(communicationView.message_kind || communicationView.messageKind);
    if (cvKind) return cvKind;
    const triggerType = firstText([run.trigger_type, run.triggerType]).toLowerCase();
    if (triggerType === "callback_auto") return "system_callback";
    if (triggerType === "callback_auto_summary") return "system_callback_summary";
    if (triggerType === "restart_recovery_summary" || triggerType === "restart_recovery") return "restart_recovery_summary";
    const sender = readStructuredSender(run);
    if (sender.type === "user") return "user_input";
    if (sender.type === "agent") return "agent_output";
    if (sender.type === "system") return "system_notice";
    return "manual_update";
  }

  function messageKindLabel(kind) {
    return ({
      system_callback: "系统回执",
      system_callback_summary: "系统回执汇总",
      restart_recovery_summary: "服务恢复",
      user_input: "用户输入",
      agent_output: "Agent 输出",
      system_notice: "系统提示",
      collab_update: "协同更新",
      manual_update: "兼容消息",
    })[safeText(kind).toLowerCase()] || "消息";
  }

  function interactionModeLabel(mode) {
    return ({
      task_with_receipt: "需回执",
      notify_only: "仅通知",
      task_only: "任务",
    })[safeText(mode).toLowerCase()] || "";
  }

  function formatRefValue(raw) {
    if (raw == null) return "";
    if (typeof raw === "string" || typeof raw === "number" || typeof raw === "boolean") return safeText(raw);
    if (typeof raw === "object" && !Array.isArray(raw)) {
      const channelName = firstText([raw.channel_name, raw.channelName, raw.channel]);
      const sessionId = firstText([raw.session_id, raw.sessionId]);
      const runId = firstText([raw.run_id, raw.runId]);
      const parts = [];
      if (channelName) parts.push(`channel=${channelName}`);
      if (sessionId) parts.push(`session=${sessionId}`);
      if (runId) parts.push(`run=${runId}`);
      if (parts.length) return parts.join(" · ");
      try { return JSON.stringify(raw); } catch (_) {}
    }
    try { return JSON.stringify(raw); } catch (_) {}
    return safeText(raw);
  }

  function displaySenderLabel(run) {
    return firstText([run && run.sender_name, run && run.channel_name, run && run.sender_id, run && run.session_id], "未知发送方");
  }

  function normalizeRun(raw) {
    if (!raw || typeof raw !== "object") return null;
    const runId = firstText([raw.id, raw.run_id, raw.runId]);
    const sessionId = firstText([raw.sessionId, raw.session_id]);
    if (!runId || !sessionId) return null;
    const communicationView = readCommunicationViewMeta(raw);
    const sender = readStructuredSender(raw);
    const callbackTo = raw.callback_to && typeof raw.callback_to === "object"
      ? raw.callback_to
      : ((communicationView.callback_to && typeof communicationView.callback_to === "object") ? communicationView.callback_to : {});
    const sourceRef = raw.source_ref || raw.sourceRef || communicationView.source_ref || communicationView.sourceRef || null;
    return {
      run_id: runId,
      session_id: sessionId,
      project_id: firstText([raw.project_id, raw.projectId], STATE.projectId),
      project_name: firstText([raw.project_name, raw.projectName], STATE.projectName),
      channel_name: firstText([raw.channel_name, raw.channelName]),
      created_at: firstText([raw.createdAt, raw.created_at, raw.lastProgressAt]),
      status: normalizeRunStatus(raw),
      sender_type: sender.type,
      sender_name: firstText([sender.name]),
      sender_id: firstText([sender.id]),
      message_kind: resolveMessageKind(raw),
      interaction_mode: firstText([
        raw.interaction_mode, raw.interactionMode,
        communicationView.interaction_mode, communicationView.interactionMode,
      ]).toLowerCase(),
      reply_to_run_id: firstText([raw.reply_to_run_id, raw.replyToRunId]),
      source_ref: sourceRef,
      source_ref_text: formatRefValue(sourceRef),
      callback_to: callbackTo,
      callback_to_text: formatRefValue(callbackTo),
      message_preview: firstText([raw.messagePreview, raw.message_preview, raw.lastMessage, raw.partialMessage, raw.errorHint], "无摘要消息"),
    };
  }

  function classifyChannel(channelName) {
    const text = safeText(channelName);
    if (!text) return "other";
    if (text.startsWith("主体") || text.includes("总控")) return "master";
    if (text.startsWith("辅助")) return "assist";
    if (text.startsWith("子级")) return "dev";
    return "other";
  }

  function accentFor(text) {
    const value = safeText(text);
    let hash = 0;
    for (let i = 0; i < value.length; i += 1) hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
    const palette = ["#63dac8", "#7db7ff", "#f4c86d", "#ba9cff", "#8ad79c", "#ff6f84", "#f7a8c2"];
    return palette[Math.abs(hash) % palette.length];
  }

  function rgbaFromHex(hex, alpha) {
    const raw = safeText(hex).replace(/^#/, "");
    if (raw.length !== 6) return `rgba(99,218,200,${alpha})`;
    const r = parseInt(raw.slice(0, 2), 16);
    const g = parseInt(raw.slice(2, 4), 16);
    const b = parseInt(raw.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function layoutStorageKey() {
    return `${STORAGE_PREFIX}:${safeText(STATE.projectId || "global")}`;
  }

  function loadLayoutStore() {
    try {
      const raw = localStorage.getItem(layoutStorageKey());
      if (!raw) return { groups: [], relations: [], nodes: [], zoom: 1 };
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : { groups: [], relations: [], nodes: [], zoom: 1 };
    } catch (_) {
      return { groups: [], relations: [], nodes: [], zoom: 1 };
    }
  }

  function persistLayoutStore() {
    try {
      localStorage.setItem(layoutStorageKey(), JSON.stringify({
        groups: STATE.groups,
        relations: STATE.manualRelations,
        nodes: STATE.nodes.map((node) => ({ session_id: node.session_id, x: node.x, y: node.y })),
        zoom: STATE.zoom,
      }));
    } catch (_) {}
  }

  function relationTone(type) {
    return RELATION_TYPES[type] || RELATION_TYPES.business;
  }

  function currentWindowRange() {
    const now = Date.now();
    if (STATE.windowKey === "custom") {
      const startMs = Number(STATE.customRange.startMs) || 0;
      const endMs = Number(STATE.customRange.endMs) || now;
      return { startMs, endMs, label: "自定义" };
    }
    const span = WINDOW_MS[STATE.windowKey] || WINDOW_MS["1h"];
    return { startMs: now - span, endMs: now, label: STATE.windowKey };
  }

  function replayBounds() {
    if (!STATE.messages.length) return null;
    const timestamps = STATE.messages.map((message) => dateMs(message.created_at)).filter(Boolean).sort((a, b) => a - b);
    if (!timestamps.length) return null;
    return { start: timestamps[0], end: timestamps[timestamps.length - 1] };
  }

  function replayVisibleRange() {
    if (!STATE.replayMode || !STATE.replayCursorTs) return null;
    return {
      start: STATE.replayCursorTs - REPLAY_VISIBLE_SPAN_MS,
      end: STATE.replayCursorTs,
    };
  }

  function messageTimestamp(message) {
    return dateMs(message && message.created_at);
  }

  function messageById(messageId) {
    return STATE.messages.find((item) => item.id === messageId) || null;
  }

  function visibleMessages(messages) {
    const range = replayVisibleRange();
    if (!range) return messages;
    return (messages || []).filter((message) => {
      const ts = messageTimestamp(message);
      return ts <= range.end && ts >= range.start;
    });
  }

  function replayAgeMinutes(message) {
    if (!STATE.replayMode || !STATE.replayCursorTs) return -1;
    return (STATE.replayCursorTs - messageTimestamp(message)) / 60000;
  }

  function animatedMessageIds() {
    if (!STATE.replayMode || !STATE.replayCursorTs) return new Set();
    return new Set(
      STATE.messages
        .filter((message) => {
          const ageMin = replayAgeMinutes(message);
          return ageMin >= 0 && ageMin <= 4;
        })
        .map((message) => message.id)
    );
  }

  function visibleCommLinks() {
    const visibleIds = new Set(visibleMessages(STATE.messages).map((message) => message.id));
    return STATE.commLinks.filter((link) => visibleIds.has(link.from_id) && visibleIds.has(link.to_id));
  }

  function groupActivityStats(group) {
    const sessionIds = new Set(group && Array.isArray(group.sessionIds) ? group.sessionIds : []);
    const relevant = visibleMessages(STATE.messages).filter((message) => sessionIds.has(message.session_id));
    const animatedCount = relevant.filter((message) => animatedMessageIds().has(message.id)).length;
    const count = relevant.length;
    return {
      count,
      recent: animatedCount,
      active: count > 0,
      peak: animatedCount >= 2 || count >= 6,
    };
  }

  function replayStatusLabel() {
    if (!STATE.replayMode || !STATE.replayCursorTs) return "静止视图";
    return STATE.replayPlaying ? `播放中 · ${STATE.replaySpeed}x` : `暂停 · ${STATE.replaySpeed}x`;
  }

  function syncTimeControls() {
    dom.timeTabs.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.window === STATE.windowKey);
    });
    if (dom.customRange) dom.customRange.hidden = STATE.windowKey !== "custom";
    if (dom.customStartInput) dom.customStartInput.value = formatDateTimeLocal(STATE.customRange.startMs);
    if (dom.customEndInput) dom.customEndInput.value = formatDateTimeLocal(STATE.customRange.endMs);
  }

  function setStatus(text, tone = "loading") {
    if (!dom.statusBanner) return;
    dom.statusBanner.textContent = safeText(text);
    dom.statusBanner.className = `status-banner is-${tone}`;
    dom.statusBanner.hidden = !text;
  }

  function curvePath(start, end) {
    const dx = end.x - start.x;
    const c1x = start.x + Math.max(60, Math.abs(dx) * 0.34);
    const c2x = end.x - Math.max(60, Math.abs(dx) * 0.34);
    const mid = dx >= 0 ? 18 : -18;
    return `M ${start.x} ${start.y} C ${c1x} ${start.y + mid}, ${c2x} ${end.y - mid}, ${end.x} ${end.y}`;
  }

  function parseBracketValues(text, label) {
    const results = [];
    const source = safeText(text);
    const pattern = new RegExp(`\\[${label}:\\s*([^\\]]+)\\]`, "g");
    let match;
    while ((match = pattern.exec(source))) {
      const value = safeText(match[1]);
      if (value) results.push(value);
    }
    return results;
  }

  function parseMentionTargets(text) {
    const results = [];
    const source = safeText(text);
    const pattern = /@([^\s\]\[，。,:：；;（）()<>]+)/g;
    let match;
    while ((match = pattern.exec(source))) {
      const value = safeText(match[1]);
      if (value) results.push(value);
    }
    return results;
  }

  function resolveTargetSessionIds(preview, sessionMap) {
    const hints = [
      ...parseMentionTargets(preview),
      ...parseBracketValues(preview, "协同对象"),
      ...parseBracketValues(preview, "目标通道"),
      ...parseBracketValues(preview, "主负责Agent"),
    ];
    const resolved = new Set();
    hints.forEach((hint) => {
      const normalized = safeText(hint.split(";")[0]);
      if (!normalized) return;
      sessionMap.forEach((session) => {
        const candidates = [safeText(session.alias), safeText(session.channel_name), safeText(session.desc)];
        if (candidates.some((item) => item && (item === normalized || item.includes(normalized) || normalized.includes(item)))) {
          resolved.add(session.session_id);
        }
      });
    });
    return Array.from(resolved);
  }

  function computeGroupsAndNodes(sessions) {
    const channels = new Map();
    (sessions || []).forEach((session) => {
      const channelName = safeText(session.channel_name, "未分组通道");
      const rowKind = classifyChannel(channelName);
      if (!channels.has(channelName)) {
        channels.set(channelName, {
          id: `group:${channelName}`,
          label: channelName,
          rowKind,
          accent: accentFor(channelName),
          sessions: [],
        });
      }
      channels.get(channelName).sessions.push(session);
    });
    const layoutStore = loadLayoutStore();
    const savedMap = new Map((Array.isArray(layoutStore.groups) ? layoutStore.groups : []).map((group) => [group.id, group]));
    const savedNodeMap = new Map((Array.isArray(layoutStore.nodes) ? layoutStore.nodes : []).map((node) => [safeText(node.session_id || node.sessionId), node]));
    const rows = { master: [], assist: [], dev: [], other: [] };
    Array.from(channels.values())
      .sort((a, b) => a.label.localeCompare(b.label, "zh-Hans-CN"))
      .forEach((group) => rows[group.rowKind].push(group));

    const groups = [];
    Object.entries(rows).forEach(([rowKind, items]) => {
      let cursorX = 140;
      items.forEach((group, index) => {
        const columns = Math.max(1, Math.min(3, Math.ceil(group.sessions.length / 2) || 1));
        const width = Math.max(320, columns * (CARD_WIDTH + 20) + GROUP_PADDING * 2 - 20);
        const height = Math.max(250, Math.ceil(group.sessions.length / columns) * (CARD_HEIGHT + 20) + 116);
        const saved = savedMap.get(group.id);
        groups.push({
          id: group.id,
          label: group.label,
          rowKind,
          accent: group.accent,
          x: Number(saved && saved.x) || cursorX,
          y: Number(saved && saved.y) || (ROWS[rowKind].y + (rowKind === "master" ? 0 : 10)),
          w: Number(saved && saved.w) || width,
          h: Number(saved && saved.h) || height,
          z: Number.isFinite(Number(saved && saved.z)) ? Number(saved.z) : index,
          sessionIds: group.sessions.map((item) => item.session_id),
        });
        cursorX += width + 40;
      });
    });
    groups.sort((a, b) => a.z - b.z);

    const nodes = [];
    groups.forEach((group) => {
      const groupSessions = (sessions || []).filter((session) => group.sessionIds.includes(session.session_id));
      const columns = Math.max(1, Math.floor((group.w - GROUP_PADDING * 2 + 20) / (CARD_WIDTH + 20)));
      groupSessions.forEach((session, index) => {
        const col = index % columns;
        const row = Math.floor(index / columns);
        const savedNode = savedNodeMap.get(session.session_id);
        nodes.push({
          id: session.session_id,
          session_id: session.session_id,
          group_id: group.id,
          x: Number(savedNode && savedNode.x) || (group.x + GROUP_PADDING + col * (CARD_WIDTH + 20)),
          y: Number(savedNode && savedNode.y) || (group.y + 72 + row * (CARD_HEIGHT + 20)),
          w: CARD_WIDTH,
          h: CARD_HEIGHT,
          alias: safeText(session.alias, session.session_id),
          role: safeText(session.desc || session.role, "协作Agent"),
          channel_name: safeText(session.channel_name, "未分组通道"),
          status: safeText(session.status, "idle"),
          accent: group.accent,
        });
      });
    });
    return { groups, nodes };
  }

  function buildRunsUrl() {
    const params = new URLSearchParams();
    params.set("projectId", safeText(STATE.projectId));
    params.set("limit", "240");
    if (STATE.windowKey === "custom") {
      if (STATE.customRange.startMs) params.set("afterCreatedAt", new Date(STATE.customRange.startMs).toISOString());
      if (STATE.customRange.endMs) params.set("beforeCreatedAt", new Date(STATE.customRange.endMs).toISOString());
    }
    return `/api/codex/runs?${params.toString()}`;
  }

  function filterRunsByWindow(runs) {
    const range = currentWindowRange();
    return (runs || []).filter((run) => {
      const ts = dateMs(run.created_at);
      return ts >= range.startMs && ts <= range.endMs;
    }).sort((a, b) => dateMs(a.created_at) - dateMs(b.created_at));
  }

  function heatTier(ts) {
    const ageMin = Math.max(0, (Date.now() - ts) / 60000);
    if (ageMin <= 10) return "strong";
    if (ageMin <= 30) return "mid";
    return "soft";
  }

  function summarizeRun(run) {
    const compact = safeText(run.message_preview)
      .replace(/\[来源通道:[^\]]+\]/g, "")
      .replace(/\[目标通道:[^\]]+\]/g, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!compact) return "无摘要消息";
    return compact.length > 64 ? `${compact.slice(0, 64)}...` : compact;
  }

  function buildMessagesAndLinks(nodes, runs) {
    const nodeMap = new Map(nodes.map((node) => [node.session_id, node]));
    const filteredRuns = filterRunsByWindow(runs);
    const messages = filteredRuns
      .filter((run) => nodeMap.has(run.session_id))
      .map((run) => ({
        id: run.run_id,
        session_id: run.session_id,
        node_id: run.session_id,
        created_at: run.created_at,
        preview: summarizeRun(run),
        detail: safeText(run.message_preview, "无消息详情"),
        tier: heatTier(dateMs(run.created_at)),
        kind: messageKindLabel(run.message_kind || run.sender_type || run.status),
        raw_kind: safeText(run.message_kind || run.sender_type || run.status, "message"),
        sender_name: displaySenderLabel(run),
        sender_type: safeText(run.sender_type),
        sender_id: safeText(run.sender_id),
        interaction_mode: safeText(run.interaction_mode),
        source_ref_text: safeText(run.source_ref_text),
        callback_to_text: safeText(run.callback_to_text),
        reply_to_run_id: safeText(run.reply_to_run_id),
        callback_session_id: firstText([run.callback_to && run.callback_to.session_id, run.callback_to && run.callback_to.sessionId]),
      }));

    const byRunId = new Map(messages.map((message) => [message.id, message]));
    const sessionMap = new Map(STATE.sessions.map((session) => [session.session_id, session]));
    const links = [];
    const seen = new Set();
    function push(fromId, toId, reason) {
      if (!fromId || !toId || fromId === toId) return;
      const key = `${fromId}|${toId}|${reason}`;
      if (seen.has(key)) return;
      seen.add(key);
      links.push({ id: key, from_id: fromId, to_id: toId, reason });
    }
    messages.forEach((message) => {
      if (message.reply_to_run_id && byRunId.has(message.reply_to_run_id)) {
        push(message.reply_to_run_id, message.id, "reply_to_run_id");
      }
      if (message.callback_session_id) {
        const target = messages.find((item) => item.session_id === message.callback_session_id);
        if (target) push(message.id, target.id, "callback_to_session");
      }
      const targetSessionIds = resolveTargetSessionIds(message.detail, sessionMap).filter((sid) => sid !== message.session_id);
      targetSessionIds.forEach((sid) => {
        const target = messages.find((item) => item.session_id === sid);
        if (target) push(message.id, target.id, `hint:${sid}`);
      });
    });
    return { messages, commLinks: links };
  }

  function messagesForNode(sessionId) {
    return visibleMessages(STATE.messages)
      .filter((message) => message.session_id === sessionId)
      .sort((a, b) => dateMs(b.created_at) - dateMs(a.created_at))
      .slice(0, 6);
  }

  function nodeBySessionId(sessionId) {
    return STATE.nodes.find((item) => item.session_id === sessionId) || null;
  }

  function nodeAnchor(node, side) {
    if (!node) return null;
    if (side === "top") return { x: node.x + node.w / 2, y: node.y };
    if (side === "bottom") return { x: node.x + node.w / 2, y: node.y + node.h };
    if (side === "left") return { x: node.x, y: node.y + node.h / 2 };
    return { x: node.x + node.w, y: node.y + node.h / 2 };
  }

  function inferNodeSideFromPoint(nodeEl, clientX, clientY) {
    if (!nodeEl) return "left";
    const rect = nodeEl.getBoundingClientRect();
    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    const dx = localX - rect.width / 2;
    const dy = localY - rect.height / 2;
    if (Math.abs(dx) > Math.abs(dy)) return dx >= 0 ? "right" : "left";
    return dy >= 0 ? "bottom" : "top";
  }

  function defaultRelationLabel(type) {
    return relationTone(type).label;
  }

  function buildStoredRelations(nodes) {
    const layoutStore = loadLayoutStore();
    const validIds = new Set(nodes.map((node) => node.session_id));
    const stored = Array.isArray(layoutStore.relations) ? layoutStore.relations : [];
    return stored
      .filter((edge) => edge && typeof edge === "object")
      .map((edge) => ({
        id: safeText(edge.id) || `relation:${Math.random().toString(36).slice(2, 10)}`,
        from_session_id: safeText(edge.from_session_id || edge.fromSessionId),
        to_session_id: safeText(edge.to_session_id || edge.toSessionId),
        from_side: safeText(edge.from_side || edge.fromSide, "right"),
        to_side: safeText(edge.to_side || edge.toSide, "left"),
        type: safeText(edge.type, "business"),
        label: safeText(edge.label, defaultRelationLabel(safeText(edge.type, "business"))),
      }))
      .filter((edge) => validIds.has(edge.from_session_id) && validIds.has(edge.to_session_id));
  }

  function visibleRelationCount() {
    return STATE.manualRelations.filter((relation) => STATE.visibleRelations[relation.type] !== false).length;
  }

  function showBubbleTooltip(message, clientX, clientY) {
    if (!dom.bubbleTooltip) return;
    dom.bubbleTooltip.innerHTML = `${escapeHtml(message.preview)}<div class="meta">${fmtDateTime(message.created_at)} · ${escapeHtml(message.kind)}</div>`;
    dom.bubbleTooltip.style.left = `${Math.min(window.innerWidth - 300, clientX + 14)}px`;
    dom.bubbleTooltip.style.top = `${Math.min(window.innerHeight - 90, clientY + 14)}px`;
    dom.bubbleTooltip.classList.add("visible");
  }

  function hideBubbleTooltip() {
    dom.bubbleTooltip?.classList.remove("visible");
  }

  function openMessageDialog(messageId) {
    const message = STATE.messages.find((item) => item.id === messageId);
    if (!message || !dom.messageDialog) return;
    STATE.selectedMessageId = message.id;
    dom.messageDialogTitle.textContent = `${message.kind} · ${fmtDateTime(message.created_at)}`;
    dom.messageDialogBody.textContent = [
      `sender_name: ${message.sender_name || "-"}`,
      `sender_type: ${message.sender_type || "-"}`,
      `sender_id: ${message.sender_id || "-"}`,
      `message_kind: ${message.raw_kind || "-"}`,
      `interaction_mode: ${message.interaction_mode || "-"}`,
      `source_ref: ${message.source_ref_text || "-"}`,
      `callback_to: ${message.callback_to_text || "-"}`,
      "",
      message.detail,
    ].join("\n");
    dom.messageDialog.hidden = false;
  }

  function closeMessageDialog() {
    if (dom.messageDialog) dom.messageDialog.hidden = true;
  }

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderHeader() {
    if (dom.envBadge) dom.envBadge.textContent = safeText(DATA.environment, "stable");
    if (dom.taskLink) dom.taskLink.href = `${safeText(LINKS.task_page, "/share/project-task-dashboard.html")}#p=${encodeURIComponent(STATE.projectId)}`;
    if (dom.curtainLink) dom.curtainLink.href = `${safeText(DATA.agent_curtain_page || LINKS.agent_curtain_page, "/share/project-agent-curtain.html")}#p=${encodeURIComponent(STATE.projectId)}`;
    if (dom.boardMeta) {
      const range = currentWindowRange();
      const label = STATE.windowKey === "custom" ? `自定义 ${fmtDateTime(range.startMs)} ~ ${fmtDateTime(range.endMs)}` : `窗口 ${STATE.windowKey}`;
      dom.boardMeta.textContent = `${STATE.projectName || STATE.projectId} · ${STATE.channelHint ? `通道 ${STATE.channelHint}` : "单项目关系视图"} · ${label}`;
    }
    if (dom.summaryMeta) {
      const visibleMsgCount = visibleMessages(STATE.messages).length;
      const visibleComm = STATE.visibleRelations.message ? visibleCommLinks().length : 0;
      dom.summaryMeta.textContent = `背景板 ${STATE.groups.length} · Agent ${STATE.nodes.length} · 业务关系 ${visibleRelationCount()} · 消息 ${visibleMsgCount} · 通讯 ${visibleComm}`;
    }
    dom.relationTypeButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.relationType === STATE.activeRelationType);
    });
    dom.visibilityButtons.forEach((button) => {
      const key = button.dataset.visibility || "";
      button.classList.toggle("is-active", STATE.visibleRelations[key] !== false);
    });
    syncTimeControls();
  }

  function renderReplayMarkers() {
    if (!dom.replayMarkers) return;
    dom.replayMarkers.innerHTML = "";
    const bounds = replayBounds();
    if (!bounds || bounds.end <= bounds.start) return;
    const buckets = 24;
    const counts = new Array(buckets).fill(0);
    const span = bounds.end - bounds.start;
    STATE.messages.forEach((message) => {
      const ts = messageTimestamp(message);
      const index = Math.max(0, Math.min(buckets - 1, Math.floor(((ts - bounds.start) / span) * buckets)));
      counts[index] += 1;
    });
    const peak = Math.max(...counts, 0);
    counts.forEach((count, index) => {
      if (!count) return;
      const marker = document.createElement("button");
      marker.type = "button";
      marker.className = `replay-marker${count >= peak * 0.75 ? " peak" : ""}`;
      marker.style.left = `${((index + 0.5) / buckets) * 100}%`;
      marker.style.height = `${Math.max(18, Math.min(54, 14 + count * 5))}%`;
      marker.title = `该时段消息 ${count} 条`;
      marker.addEventListener("click", () => {
        stopReplay();
        STATE.replayMode = true;
        STATE.replayCursorTs = bounds.start + ((index + 0.5) / buckets) * span;
        renderAll();
      });
      dom.replayMarkers.appendChild(marker);
    });
  }

  function renderReplayControls() {
    const bounds = replayBounds();
    if (!dom.replaySlider || !dom.replayCurrentTime || !dom.replayEndTime) return;
    dom.playBtn?.classList.toggle("is-active", STATE.replayPlaying);
    dom.pauseBtn?.classList.toggle("is-active", !STATE.replayPlaying && STATE.replayMode);
    dom.replayResetBtn?.classList.toggle("is-active", STATE.replayMode && !STATE.replayPlaying);
    dom.replaySpeedButtons.forEach((button) => {
      button.classList.toggle("is-active", Number(button.dataset.replaySpeed) === STATE.replaySpeed);
    });
    if (!bounds) {
      dom.replaySlider.disabled = true;
      dom.replaySlider.value = "0";
      dom.replayCurrentTime.textContent = "无数据";
      dom.replayEndTime.textContent = "--";
      return;
    }
    const current = STATE.replayMode && STATE.replayCursorTs ? STATE.replayCursorTs : bounds.end;
    const progress = bounds.end === bounds.start ? 1 : (current - bounds.start) / (bounds.end - bounds.start);
    dom.replaySlider.disabled = false;
    dom.replaySlider.value = String(Math.max(0, Math.min(1000, Math.round(progress * 1000))));
    dom.replayCurrentTime.textContent = STATE.replayMode && STATE.replayCursorTs ? fmtTime(current) : replayStatusLabel();
    dom.replayEndTime.textContent = fmtTime(bounds.end);
    renderReplayMarkers();
  }

  function syncZoom() {
    if (!dom.stage || !dom.stageViewport || !dom.stageWrap) return;
    const zoom = Math.max(0.55, Math.min(1.6, Number(STATE.zoom) || 1));
    STATE.zoom = zoom;
    const baseW = dom.stage.offsetWidth || 3800;
    const baseH = dom.stage.offsetHeight || 2280;
    const prevZoom = Number(dom.stage.dataset.zoom || 1) || 1;
    const centerRatioX = ((dom.stageWrap.scrollLeft + dom.stageWrap.clientWidth / 2) / Math.max(baseW * prevZoom, 1));
    const centerRatioY = ((dom.stageWrap.scrollTop + dom.stageWrap.clientHeight / 2) / Math.max(baseH * prevZoom, 1));
    dom.stage.style.transform = `scale(${zoom})`;
    dom.stage.dataset.zoom = String(zoom);
    dom.stageViewport.style.width = `${baseW * zoom}px`;
    dom.stageViewport.style.height = `${baseH * zoom}px`;
    dom.stageWrap.scrollLeft = Math.max(0, centerRatioX * baseW * zoom - dom.stageWrap.clientWidth / 2);
    dom.stageWrap.scrollTop = Math.max(0, centerRatioY * baseH * zoom - dom.stageWrap.clientHeight / 2);
    dom.zoomResetBtn && (dom.zoomResetBtn.textContent = `${Math.round(zoom * 100)}%`);
    renderMiniMap();
  }

  function renderMiniMap() {
    if (!dom.miniMap || !dom.stage || !dom.stageWrap) return;
    dom.miniMap.innerHTML = "";
    const baseW = dom.stage.offsetWidth || 3800;
    const baseH = dom.stage.offsetHeight || 2280;
    const scaleX = dom.miniMap.clientWidth / Math.max(baseW, 1);
    const scaleY = dom.miniMap.clientHeight / Math.max(baseH, 1);
    STATE.groups.forEach((group) => {
      const box = document.createElement("div");
      box.className = "mini-group";
      box.style.left = `${group.x * scaleX}px`;
      box.style.top = `${group.y * scaleY}px`;
      box.style.width = `${Math.max(6, group.w * scaleX)}px`;
      box.style.height = `${Math.max(6, group.h * scaleY)}px`;
      dom.miniMap.appendChild(box);
    });
    STATE.nodes.forEach((node) => {
      const mark = document.createElement("div");
      mark.className = "mini-node";
      mark.style.left = `${node.x * scaleX}px`;
      mark.style.top = `${node.y * scaleY}px`;
      dom.miniMap.appendChild(mark);
    });
    const viewport = document.createElement("div");
    viewport.className = "mini-viewport";
    const width = Math.min(dom.miniMap.clientWidth, (dom.stageWrap.clientWidth / Math.max(baseW * STATE.zoom, 1)) * dom.miniMap.clientWidth);
    const height = Math.min(dom.miniMap.clientHeight, (dom.stageWrap.clientHeight / Math.max(baseH * STATE.zoom, 1)) * dom.miniMap.clientHeight);
    const left = (dom.stageWrap.scrollLeft / Math.max(baseW * STATE.zoom, 1)) * dom.miniMap.clientWidth;
    const top = (dom.stageWrap.scrollTop / Math.max(baseH * STATE.zoom, 1)) * dom.miniMap.clientHeight;
    viewport.style.width = `${Math.max(18, width)}px`;
    viewport.style.height = `${Math.max(18, height)}px`;
    viewport.style.left = `${Math.max(0, Math.min(dom.miniMap.clientWidth - width, left))}px`;
    viewport.style.top = `${Math.max(0, Math.min(dom.miniMap.clientHeight - height, top))}px`;
    dom.miniMap.appendChild(viewport);
  }

  function renderGroups() {
    dom.groupsLayer.innerHTML = "";
    dom.groupChipLayer.innerHTML = "";
    const ordered = [...STATE.groups].sort((a, b) => a.z - b.z);
    ordered.forEach((group) => {
      const activity = groupActivityStats(group);
      const box = document.createElement("div");
      box.className = `group-box${group.id === STATE.selectedGroupId ? " selected" : ""}${activity.active ? " active" : ""}${activity.peak ? " peak" : ""}`;
      box.style.left = `${group.x}px`;
      box.style.top = `${group.y}px`;
      box.style.width = `${group.w}px`;
      box.style.height = `${group.h}px`;
      box.style.setProperty("--group-soft", rgbaFromHex(group.accent, 0.1));
      box.style.setProperty("--group-fade", rgbaFromHex(group.accent, 0.05));
      box.addEventListener("click", () => {
        STATE.selectedGroupId = group.id;
        STATE.selectedSessionId = "";
        STATE.selectedRelationId = "";
        renderAll();
      });
      dom.groupsLayer.appendChild(box);

      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `group-chip${group.id === STATE.selectedGroupId ? " selected" : ""}${activity.active ? " active" : ""}${activity.peak ? " peak" : ""}`;
      chip.style.left = `${group.x + 14}px`;
      chip.style.top = `${group.y + 14}px`;
      chip.innerHTML = `<span>${escapeHtml(group.label)}</span><span class="hint">拖动 / 改名</span>`;
      chip.addEventListener("pointerdown", (event) => {
        STATE.selectedGroupId = group.id;
        STATE.selectedRelationId = "";
        STATE.selectedSessionId = "";
        STATE.dragGroup = { id: group.id, pointerId: event.pointerId, originX: group.x, originY: group.y, startX: event.clientX, startY: event.clientY };
        chip.setPointerCapture(event.pointerId);
        renderDetail();
        renderGroups();
      });
      chip.addEventListener("dblclick", () => {
        const next = window.prompt("修改背景板名称", group.label);
        if (!next) return;
        group.label = safeText(next, group.label);
        persistLayoutStore();
        renderAll();
      });
      dom.groupChipLayer.appendChild(chip);

      if (group.id === STATE.selectedGroupId) {
        [
          { corner: "nw", x: group.x - 8, y: group.y - 8 },
          { corner: "ne", x: group.x + group.w - 8, y: group.y - 8 },
          { corner: "sw", x: group.x - 8, y: group.y + group.h - 8 },
          { corner: "se", x: group.x + group.w - 8, y: group.y + group.h - 8 },
        ].forEach((meta) => {
          const handle = document.createElement("div");
          handle.className = `group-resize ${meta.corner}`;
          handle.style.left = `${meta.x}px`;
          handle.style.top = `${meta.y}px`;
          handle.addEventListener("pointerdown", (event) => {
            STATE.resizeGroup = {
              id: group.id,
              corner: meta.corner,
              pointerId: event.pointerId,
              startX: event.clientX,
              startY: event.clientY,
              originX: group.x,
              originY: group.y,
              originW: group.w,
              originH: group.h,
            };
            handle.setPointerCapture(event.pointerId);
            event.stopPropagation();
          });
          dom.groupChipLayer.appendChild(handle);
        });
      }
    });
  }

  function nodeAvatar(node) {
    const text = safeText(node.alias, "Agent");
    return text.length <= 2 ? text : text.slice(0, 2);
  }

  function renderNodes() {
    dom.nodesLayer.innerHTML = "";
    const animatedIds = animatedMessageIds();
    const visibleLinks = visibleCommLinks();
    const linkedTargetIds = new Set(visibleLinks.map((link) => link.to_id));
    STATE.nodes.forEach((node) => {
      const el = document.createElement("div");
      el.className = `node${node.session_id === STATE.selectedSessionId ? " selected" : ""}${STATE.relationDraft && STATE.relationDraft.from_session_id === node.session_id ? " connecting" : ""}`;
      el.dataset.sessionId = node.session_id;
      el.style.left = `${node.x}px`;
      el.style.top = `${node.y}px`;
      el.style.setProperty("--avatar-a", node.accent);
      el.style.setProperty("--avatar-b", rgbaFromHex(node.accent, 0.68));
      const tags = [];
      tags.push(`<span class="tag">${escapeHtml(node.status || "idle")}</span>`);
      tags.push(`<span class="tag">${escapeHtml(node.channel_name)}</span>`);
      const messages = messagesForNode(node.session_id);
      const bubbles = messages.map((message, index) => {
        const classes = ["msg-bubble", message.tier];
        if (animatedIds.has(message.id)) classes.push("animated");
        if (linkedTargetIds.has(message.id)) classes.push("linked-target");
        const ageMin = replayAgeMinutes(message);
        if (ageMin >= 55) classes.push("aging-out");
        else if (ageMin >= 45) classes.push("aging-soft");
        return `
        <button class="${classes.join(" ")}" style="--bubble-delay:${index * 60}ms" data-message-id="${escapeHtml(message.id)}" aria-label="${escapeHtml(message.preview)}">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M5 6.5A3.5 3.5 0 0 1 8.5 3h7A3.5 3.5 0 0 1 19 6.5v4A3.5 3.5 0 0 1 15.5 14H11l-3.6 3.1c-.65.56-1.65.1-1.65-.76V14A3.5 3.5 0 0 1 5 10.5zm3 1.25a1 1 0 0 0 0 2h8a1 1 0 1 0 0-2zm0 3.5a1 1 0 0 0 0 2h5a1 1 0 1 0 0-2z"/></svg>
        </button>`;
      }).join("");
      el.innerHTML = `
        <div class="node-head">
          <div class="avatar">${escapeHtml(nodeAvatar(node))}</div>
          <div>
            <div class="node-title">${escapeHtml(node.alias)}</div>
            <div class="node-sub">${escapeHtml(node.role)}</div>
          </div>
        </div>
        <div class="node-tags">${STATE.visibleRelations.labels !== false ? tags.join("") : ""}</div>
        <div class="bubble-row">${bubbles || '<span class="tag">无消息</span>'}</div>
        <button class="connector top" data-side="top" type="button" aria-label="从上侧连接 ${escapeHtml(node.alias)}"></button>
        <button class="connector right" data-side="right" type="button" aria-label="从右侧连接 ${escapeHtml(node.alias)}"></button>
        <button class="connector bottom" data-side="bottom" type="button" aria-label="从下侧连接 ${escapeHtml(node.alias)}"></button>
        <button class="connector left" data-side="left" type="button" aria-label="从左侧连接 ${escapeHtml(node.alias)}"></button>
      `;
      el.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        if (event.target && event.target.closest && event.target.closest(".msg-bubble, .connector")) return;
        STATE.dragNode = {
          id: node.session_id,
          pointerId: event.pointerId,
          originX: node.x,
          originY: node.y,
          startX: event.clientX,
          startY: event.clientY,
        };
        el.setPointerCapture(event.pointerId);
      });
      el.addEventListener("click", () => {
        STATE.selectedSessionId = node.session_id;
        STATE.selectedGroupId = "";
        STATE.selectedRelationId = "";
        renderAll();
      });
      dom.nodesLayer.appendChild(el);

      el.querySelectorAll(".msg-bubble").forEach((button) => {
        const messageId = button.getAttribute("data-message-id") || "";
        const message = STATE.messages.find((item) => item.id === messageId);
        if (!message) return;
        button.addEventListener("mouseenter", (event) => showBubbleTooltip(message, event.clientX, event.clientY));
        button.addEventListener("mousemove", (event) => showBubbleTooltip(message, event.clientX, event.clientY));
        button.addEventListener("mouseleave", hideBubbleTooltip);
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          openMessageDialog(message.id);
        });
      });
      el.querySelectorAll(".connector").forEach((connector) => {
        connector.addEventListener("click", (event) => {
          event.stopPropagation();
          const side = connector.dataset.side || "right";
          const draft = STATE.relationDraft;
          if (draft) {
            if (draft.from_session_id === node.session_id) {
              STATE.relationDraft = null;
              renderLinks();
              return;
            }
            completeRelationDraft(node.session_id, side);
            return;
          }
          const start = nodeAnchor(node, side);
          STATE.relationDraft = {
            from_session_id: node.session_id,
            from_side: side,
            currentX: start ? start.x : node.x + node.w,
            currentY: start ? start.y : node.y + node.h / 2,
          };
          renderAll();
        });
      });
    });
  }

  function completeRelationDraft(targetSessionId, targetSide) {
    const draft = STATE.relationDraft;
    if (!draft || !targetSessionId) return false;
    if (draft.from_session_id === targetSessionId) {
      STATE.relationDraft = null;
      renderLinks();
      return false;
    }
    STATE.manualRelations.push({
      id: `relation:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 7)}`,
      from_session_id: draft.from_session_id,
      to_session_id: targetSessionId,
      from_side: draft.from_side,
      to_side: safeText(targetSide, "left"),
      type: STATE.activeRelationType,
      label: defaultRelationLabel(STATE.activeRelationType),
    });
    STATE.relationDraft = null;
    persistLayoutStore();
    renderAll();
    return true;
  }

  function bubbleCenter(messageId) {
    const bubble = dom.nodesLayer.querySelector(`[data-message-id="${CSS.escape(messageId)}"]`);
    if (!bubble) return null;
    const rect = bubble.getBoundingClientRect();
    const stageRect = dom.stage.getBoundingClientRect();
    return {
      x: (rect.left - stageRect.left + rect.width / 2) / STATE.zoom,
      y: (rect.top - stageRect.top + rect.height / 2) / STATE.zoom,
    };
  }

  function drawRelation(edge) {
    if (STATE.visibleRelations[edge.type] === false) return;
    const fromNode = nodeBySessionId(edge.from_session_id);
    const toNode = nodeBySessionId(edge.to_session_id);
    const start = nodeAnchor(fromNode, edge.from_side);
    const end = nodeAnchor(toNode, edge.to_side);
    if (!start || !end) return;
    const tone = relationTone(edge.type);
    const selectRelation = (event) => {
      event.stopPropagation();
      STATE.selectedRelationId = edge.id;
      STATE.selectedGroupId = "";
      STATE.selectedSessionId = "";
      renderAll();
    };
    const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
    hit.setAttribute("d", curvePath(start, end));
    hit.setAttribute("class", "relation-hit");
    hit.dataset.relationId = edge.id;
    hit.addEventListener("click", selectRelation);
    dom.linesSvg.appendChild(hit);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", curvePath(start, end));
    path.setAttribute("class", `relation-line ${edge.type}${edge.id === STATE.selectedRelationId ? " selected" : ""}`);
    path.setAttribute("stroke", tone.color);
    path.dataset.relationId = edge.id;
    path.addEventListener("click", selectRelation);
    dom.linesSvg.appendChild(path);
    if (STATE.visibleRelations.labels !== false) {
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("class", "relation-label");
      label.setAttribute("x", String((start.x + end.x) / 2));
      label.setAttribute("y", String((start.y + end.y) / 2 - 10));
      label.setAttribute("text-anchor", "middle");
      label.dataset.relationId = edge.id;
      label.textContent = edge.label || tone.label;
      label.addEventListener("click", selectRelation);
      dom.linesSvg.appendChild(label);
    }
  }

  function renderLinks() {
    dom.linesSvg.innerHTML = `
      <defs>
        <marker id="relationArrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L10,5 L0,10 z" fill="rgba(238,245,255,0.86)"></path>
        </marker>
      </defs>
    `;
    if (STATE.visibleRelations.message === true) {
      const animatedIds = animatedMessageIds();
      visibleCommLinks().forEach((link, index) => {
        const start = bubbleCenter(link.from_id);
        const end = bubbleCenter(link.to_id);
        if (!start || !end) return;
        const source = messageById(link.from_id) || messageById(link.to_id);
        const classes = ["comm-line"];
        if (source && source.tier) classes.push(source.tier);
        if ((animatedIds.has(link.from_id) || animatedIds.has(link.to_id))) classes.push("animated");
        const ageMin = source ? replayAgeMinutes(source) : -1;
        if (ageMin >= 55) classes.push("aging-out");
        else if (ageMin >= 45) classes.push("aging-soft");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", curvePath(start, end));
        path.setAttribute("class", classes.join(" "));
        path.style.setProperty("--line-delay", `${index * 40}ms`);
        dom.linesSvg.appendChild(path);
        if (classes.includes("animated") && !classes.includes("aging-out")) {
          const pulse = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          pulse.setAttribute("r", "3.6");
          pulse.setAttribute("class", "msg-bubble-pulse");
          const motion = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
          motion.setAttribute("dur", "1.15s");
          motion.setAttribute("begin", `${Math.max(0, index * 0.04 + 0.6)}s`);
          motion.setAttribute("path", curvePath(start, end));
          motion.setAttribute("fill", "freeze");
          pulse.appendChild(motion);
          dom.linesSvg.appendChild(pulse);
        }
      });
    }
    STATE.manualRelations.forEach((relation) => drawRelation(relation));
    if (STATE.relationDraft) {
      const fromNode = nodeBySessionId(STATE.relationDraft.from_session_id);
      const start = nodeAnchor(fromNode, STATE.relationDraft.from_side);
      if (start) {
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", curvePath(start, { x: STATE.relationDraft.currentX, y: STATE.relationDraft.currentY }));
        path.setAttribute("class", "draft-line");
        dom.linesSvg.appendChild(path);
      }
    }
  }

  function renderGroupList() {
    dom.groupList.innerHTML = "";
    const ordered = [...STATE.groups].sort((a, b) => b.z - a.z);
    if (!ordered.length) {
      dom.groupList.innerHTML = '<div class="empty-state">当前项目暂无可展示背景板。</div>';
      return;
    }
    ordered.forEach((group) => {
      const item = document.createElement("div");
      item.className = "layer-item";
      item.draggable = true;
      item.dataset.groupId = group.id;
      item.innerHTML = `
        <div class="layer-title">${escapeHtml(group.label)}</div>
        <div class="layer-meta">${Math.round(group.w)} × ${Math.round(group.h)} · ${Math.round(group.x)}, ${Math.round(group.y)}</div>
      `;
      item.addEventListener("click", () => {
        STATE.selectedGroupId = group.id;
        STATE.selectedSessionId = "";
        STATE.selectedRelationId = "";
        renderAll();
      });
      item.addEventListener("dragstart", () => {
        STATE.dragLayerGroupId = group.id;
        item.classList.add("dragging");
      });
      item.addEventListener("dragend", () => {
        item.classList.remove("dragging");
        dom.groupList.querySelectorAll(".layer-item").forEach((node) => node.classList.remove("drop-target"));
      });
      item.addEventListener("dragover", (event) => {
        event.preventDefault();
        if (STATE.dragLayerGroupId && STATE.dragLayerGroupId !== group.id) item.classList.add("drop-target");
      });
      item.addEventListener("dragleave", () => item.classList.remove("drop-target"));
      item.addEventListener("drop", (event) => {
        event.preventDefault();
        item.classList.remove("drop-target");
        if (!STATE.dragLayerGroupId || STATE.dragLayerGroupId === group.id) return;
        const topFirst = [...STATE.groups].sort((a, b) => b.z - a.z);
        const fromIndex = topFirst.findIndex((node) => node.id === STATE.dragLayerGroupId);
        const toIndex = topFirst.findIndex((node) => node.id === group.id);
        if (fromIndex < 0 || toIndex < 0) return;
        const [moved] = topFirst.splice(fromIndex, 1);
        topFirst.splice(toIndex, 0, moved);
        topFirst.forEach((node, index) => { node.z = topFirst.length - index; });
        STATE.groups = [...topFirst].sort((a, b) => a.z - b.z);
        persistLayoutStore();
        renderAll();
      });
      dom.groupList.appendChild(item);
    });
  }

  function centerOnNode(node) {
    if (!node || !dom.stageWrap || !dom.stage) return;
    const targetLeft = Math.max(0, node.x * STATE.zoom - dom.stageWrap.clientWidth / 2 + node.w * STATE.zoom / 2);
    const targetTop = Math.max(0, node.y * STATE.zoom - dom.stageWrap.clientHeight / 2 + node.h * STATE.zoom / 2);
    dom.stageWrap.scrollTo({ left: targetLeft, top: targetTop, behavior: "smooth" });
    renderMiniMap();
  }

  function renderRosterList() {
    if (!dom.rosterList) return;
    const query = safeText(dom.searchInput && dom.searchInput.value).toLowerCase();
    const filtered = STATE.nodes
      .filter((node) => {
        if (!query) return true;
        return [node.alias, node.channel_name, node.role].some((item) => safeText(item).toLowerCase().includes(query));
      })
      .sort((a, b) => a.alias.localeCompare(b.alias, "zh-Hans-CN"));
    dom.rosterList.innerHTML = "";
    if (!filtered.length) {
      dom.rosterList.innerHTML = '<div class="empty-state">没有匹配的 Agent 节点。</div>';
      return;
    }
    filtered.forEach((node) => {
      const item = document.createElement("div");
      item.className = `roster-item${node.session_id === STATE.selectedSessionId ? " selected" : ""}`;
      item.innerHTML = `
        <div class="roster-name">${escapeHtml(node.alias)}</div>
        <div class="roster-meta">${escapeHtml(node.channel_name)} · ${escapeHtml(node.role)}</div>
      `;
      item.addEventListener("click", () => {
        STATE.selectedSessionId = node.session_id;
        STATE.selectedGroupId = "";
        STATE.selectedRelationId = "";
        renderAll();
        centerOnNode(node);
      });
      dom.rosterList.appendChild(item);
    });
  }

  function renderDetail() {
    const group = STATE.groups.find((item) => item.id === STATE.selectedGroupId);
    const node = STATE.nodes.find((item) => item.session_id === STATE.selectedSessionId);
    const relation = STATE.manualRelations.find((item) => item.id === STATE.selectedRelationId);
    if (group) {
      dom.detailTitle.textContent = group.label;
      dom.detailBody.innerHTML = `
        <div class="detail-grid">
          <div class="k">对象</div><div>背景板</div>
          <div class="k">分区</div><div>${escapeHtml(ROWS[group.rowKind].label)}</div>
          <div class="k">尺寸</div><div>${Math.round(group.w)} × ${Math.round(group.h)}</div>
          <div class="k">位置</div><div>${Math.round(group.x)}, ${Math.round(group.y)}</div>
          <div class="k">图层</div><div>${group.z}</div>
        </div>
        <div class="field-stack">
          <label class="field-label" for="groupNameInput">左上角名称</label>
          <input class="field-input" id="groupNameInput" value="${escapeHtml(group.label)}" />
        </div>
        <div class="detail-actions">
          <button class="chip" id="saveGroupNameBtn" type="button">保存名称</button>
        </div>
      `;
      dom.detailBody.querySelector("#saveGroupNameBtn")?.addEventListener("click", () => {
        const input = dom.detailBody.querySelector("#groupNameInput");
        group.label = safeText(input && input.value, group.label);
        persistLayoutStore();
        renderAll();
      });
      dom.detailPanel.classList.remove("collapsed");
      return;
    }
    if (relation) {
      const fromNode = nodeBySessionId(relation.from_session_id);
      const toNode = nodeBySessionId(relation.to_session_id);
      dom.detailTitle.textContent = relation.label || relationTone(relation.type).label;
      dom.detailBody.innerHTML = `
        <div class="detail-grid">
          <div class="k">对象</div><div>关系线</div>
          <div class="k">起点</div><div>${escapeHtml(fromNode ? fromNode.alias : relation.from_session_id)}</div>
          <div class="k">终点</div><div>${escapeHtml(toNode ? toNode.alias : relation.to_session_id)}</div>
        </div>
        <div class="field-stack">
          <label class="field-label" for="relationLabelInput">关系名称</label>
          <input class="field-input" id="relationLabelInput" value="${escapeHtml(relation.label || relationTone(relation.type).label)}" />
          <label class="field-label" for="relationTypeSelect">关系类型</label>
          <select class="field-select" id="relationTypeSelect">
            ${Object.entries(RELATION_TYPES).map(([key, meta]) => `<option value="${escapeHtml(key)}"${relation.type === key ? " selected" : ""}>${escapeHtml(meta.label)}</option>`).join("")}
          </select>
        </div>
        <div class="detail-actions">
          <button class="chip" id="saveRelationBtn" type="button">保存关系</button>
          <button class="chip" id="deleteRelationBtn" type="button">删除关系</button>
        </div>
      `;
      dom.detailBody.querySelector("#saveRelationBtn")?.addEventListener("click", () => {
        const labelInput = dom.detailBody.querySelector("#relationLabelInput");
        const typeSelect = dom.detailBody.querySelector("#relationTypeSelect");
        relation.type = safeText(typeSelect && typeSelect.value, relation.type);
        relation.label = safeText(labelInput && labelInput.value, defaultRelationLabel(relation.type));
        persistLayoutStore();
        renderAll();
      });
      dom.detailBody.querySelector("#deleteRelationBtn")?.addEventListener("click", () => {
        STATE.manualRelations = STATE.manualRelations.filter((item) => item.id !== relation.id);
        STATE.selectedRelationId = "";
        persistLayoutStore();
        renderAll();
      });
      dom.detailPanel.classList.remove("collapsed");
      return;
    }
    if (node) {
      const messages = messagesForNode(node.session_id);
      dom.detailTitle.textContent = node.alias;
      dom.detailBody.innerHTML = `
        <div class="detail-grid">
          <div class="k">对象</div><div>Agent</div>
          <div class="k">通道</div><div>${escapeHtml(node.channel_name)}</div>
          <div class="k">角色</div><div>${escapeHtml(node.role)}</div>
          <div class="k">状态</div><div>${escapeHtml(node.status)}</div>
          <div class="k">消息</div><div>${messages.length} 条</div>
        </div>
        <div style="margin-top:14px;font-size:12px;color:var(--muted);">最近消息</div>
        <div style="margin-top:8px;display:grid;gap:8px;">
          ${messages.map((message) => `<button class="chip" data-open-message="${escapeHtml(message.id)}" type="button">${escapeHtml(fmtTime(message.created_at))} · ${escapeHtml(message.preview)}</button>`).join("") || '<div class="empty-state">当前窗口无消息。</div>'}
        </div>
      `;
      dom.detailBody.querySelectorAll("[data-open-message]").forEach((button) => {
        button.addEventListener("click", () => openMessageDialog(button.getAttribute("data-open-message") || ""));
      });
      dom.detailPanel.classList.remove("collapsed");
      return;
    }
    dom.detailTitle.textContent = "未选中";
    dom.detailBody.innerHTML = '<div class="empty-state">点击背景板、Agent 卡片或关系线查看详情。</div>';
  }

  function renderAll() {
    renderHeader();
    renderGroups();
    renderNodes();
    renderLinks();
    renderGroupList();
    renderRosterList();
    renderDetail();
    renderReplayControls();
    renderMiniMap();
    if (dom.stageWrap.hidden) dom.stageWrap.hidden = false;
  }

  let replayFrameId = 0;
  let replayLastFrame = 0;

  function stopReplay() {
    STATE.replayPlaying = false;
    if (replayFrameId) cancelAnimationFrame(replayFrameId);
    replayFrameId = 0;
    replayLastFrame = 0;
  }

  function resetReplayCursor() {
    stopReplay();
    STATE.replayMode = false;
    STATE.replayCursorTs = null;
    renderAll();
  }

  function startReplay() {
    const bounds = replayBounds();
    if (!bounds) return;
    if (!STATE.replayMode || !STATE.replayCursorTs || STATE.replayCursorTs >= bounds.end) {
      STATE.replayMode = true;
      STATE.replayCursorTs = bounds.start;
    }
    stopReplay();
    STATE.replayPlaying = true;
    renderAll();
    const totalSpan = Math.max(bounds.end - bounds.start, 1);
    const tick = (frameTs) => {
      if (!STATE.replayPlaying) return;
      if (!replayLastFrame) replayLastFrame = frameTs;
      const delta = frameTs - replayLastFrame;
      replayLastFrame = frameTs;
      const advance = delta * (totalSpan / 12000) * STATE.replaySpeed;
      STATE.replayCursorTs = Math.min(bounds.end, (STATE.replayCursorTs || bounds.start) + advance);
      renderAll();
      if ((STATE.replayCursorTs || bounds.start) >= bounds.end) {
        stopReplay();
        STATE.replayMode = true;
        STATE.replayCursorTs = bounds.end;
        renderAll();
        return;
      }
      replayFrameId = requestAnimationFrame(tick);
    };
    replayFrameId = requestAnimationFrame(tick);
  }

  async function loadData() {
    if (!STATE.projectId) {
      setStatus("缺少项目参数，关系画板暂时无法加载。", "error");
      return;
    }
    setStatus(`正在加载 ${STATE.projectId} 的 Agent 关系画板...`, "loading");
    try {
      const [sessionsPayload, runsPayload] = await Promise.all([
        fetchJson(`/api/sessions?project_id=${encodeURIComponent(STATE.projectId)}`),
        fetchJson(buildRunsUrl()),
      ]);
      STATE.sessions = (Array.isArray(sessionsPayload.sessions) ? sessionsPayload.sessions : []).map(normalizeSession).filter(Boolean);
      STATE.runs = (Array.isArray(runsPayload.runs) ? runsPayload.runs : []).map(normalizeRun).filter(Boolean);
      const { groups, nodes } = computeGroupsAndNodes(STATE.sessions);
      STATE.groups = groups;
      STATE.nodes = nodes;
      const layoutStore = loadLayoutStore();
      STATE.zoom = Math.max(0.55, Math.min(1.6, Number(layoutStore.zoom) || 1));
      STATE.manualRelations = buildStoredRelations(STATE.nodes);
      const live = buildMessagesAndLinks(STATE.nodes, STATE.runs);
      STATE.messages = live.messages;
      STATE.commLinks = live.commLinks;
      const bounds = replayBounds();
      if (!bounds) {
        stopReplay();
        STATE.replayMode = false;
        STATE.replayCursorTs = null;
      } else if (STATE.replayMode && STATE.replayCursorTs) {
        STATE.replayCursorTs = Math.max(bounds.start, Math.min(bounds.end, STATE.replayCursorTs));
      }
      renderAll();
      syncZoom();
      if (!STATE.nodes.length) {
        setStatus("当前项目暂无会话数据，保持只读空态。", "empty");
      } else {
        setStatus(`已加载 ${STATE.nodes.length} 个 Agent，${STATE.manualRelations.length} 条业务关系，${STATE.messages.length} 条消息，${STATE.commLinks.length} 条通讯线。`, "ready");
      }
    } catch (error) {
      setStatus(`关系画板加载失败：${safeText(error && error.message, "未知错误")}`, "error");
    }
  }

  function bindEvents() {
    dom.refreshBtn?.addEventListener("click", () => loadData());
    dom.saveLayoutBtn?.addEventListener("click", () => {
      persistLayoutStore();
      setStatus("关系画板布局已保存到本地。", "ready");
    });
    dom.exportConfigBtn?.addEventListener("click", () => {
      const payload = JSON.stringify(loadLayoutStore(), null, 2);
      const blob = new Blob([payload], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${safeText(STATE.projectId || "project")}-relationship-board.json`;
      link.click();
      URL.revokeObjectURL(url);
    });
    dom.copyConfigBtn?.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(JSON.stringify(loadLayoutStore(), null, 2));
        setStatus("关系画板配置已复制到剪贴板。", "ready");
      } catch (_) {
        setStatus("复制失败，请改用导出 JSON。", "error");
      }
    });
    dom.timeTabs.forEach((button) => {
      button.addEventListener("click", () => {
        STATE.windowKey = button.dataset.window || "1h";
        syncTimeControls();
        loadData();
      });
    });
    dom.customApplyBtn?.addEventListener("click", () => {
      const startMs = parseDateTimeLocal(dom.customStartInput?.value || "");
      const endMs = parseDateTimeLocal(dom.customEndInput?.value || "");
      if (!startMs || !endMs || endMs <= startMs) {
        setStatus("自定义时间范围无效，请重新输入。", "error");
        return;
      }
      STATE.windowKey = "custom";
      STATE.customRange = { startMs, endMs };
      syncTimeControls();
      loadData();
    });
    dom.relationTypeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        STATE.activeRelationType = button.dataset.relationType || "business";
        renderHeader();
      });
    });
    dom.visibilityButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.visibility || "";
        if (!key) return;
        STATE.visibleRelations[key] = !STATE.visibleRelations[key];
        renderAll();
      });
    });
    dom.playBtn?.addEventListener("click", startReplay);
    dom.pauseBtn?.addEventListener("click", () => {
      stopReplay();
      STATE.replayMode = true;
      renderAll();
    });
    dom.replayResetBtn?.addEventListener("click", resetReplayCursor);
    dom.replaySpeedButtons.forEach((button) => {
      button.addEventListener("click", () => {
        STATE.replaySpeed = Number(button.dataset.replaySpeed) || 1;
        renderReplayControls();
      });
    });
    dom.replaySlider?.addEventListener("input", (event) => {
      const bounds = replayBounds();
      if (!bounds) return;
      stopReplay();
      STATE.replayMode = true;
      const ratio = Math.max(0, Math.min(1, Number(event.target.value || 0) / 1000));
      STATE.replayCursorTs = bounds.start + ((bounds.end - bounds.start) * ratio);
      renderAll();
    });
    dom.toggleLayersBtn?.addEventListener("click", () => dom.layersPanel?.classList.toggle("collapsed"));
    dom.openLayersBtn?.addEventListener("click", () => dom.layersPanel?.classList.remove("collapsed"));
    dom.closeLayersBtn?.addEventListener("click", () => dom.layersPanel?.classList.add("collapsed"));
    dom.toggleDetailBtn?.addEventListener("click", () => dom.detailPanel?.classList.toggle("collapsed"));
    dom.openDetailBtn?.addEventListener("click", () => dom.detailPanel?.classList.remove("collapsed"));
    dom.closeDetailBtn?.addEventListener("click", () => dom.detailPanel?.classList.add("collapsed"));
    dom.messageDialogCloseBtn?.addEventListener("click", closeMessageDialog);
    dom.messageDialog?.addEventListener("click", (event) => {
      if (event.target === dom.messageDialog) closeMessageDialog();
    });
    dom.searchInput?.addEventListener("input", renderRosterList);
    dom.zoomInBtn?.addEventListener("click", () => {
      STATE.zoom = Math.min(1.6, +(STATE.zoom + 0.1).toFixed(2));
      syncZoom();
      persistLayoutStore();
    });
    dom.zoomOutBtn?.addEventListener("click", () => {
      STATE.zoom = Math.max(0.55, +(STATE.zoom - 0.1).toFixed(2));
      syncZoom();
      persistLayoutStore();
    });
    dom.zoomResetBtn?.addEventListener("click", () => {
      STATE.zoom = 1;
      syncZoom();
      persistLayoutStore();
    });
    dom.stageWrap?.addEventListener("pointerdown", (event) => {
      if (event.target && event.target.closest && event.target.closest(".node, .group-chip, .group-resize, .floating-panel, .edge-handle, .floating-replay, .floating-mini-map, button, input, select, textarea, a")) return;
      STATE.pan = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        left: dom.stageWrap.scrollLeft,
        top: dom.stageWrap.scrollTop,
      };
      dom.stageWrap.setPointerCapture(event.pointerId);
      dom.stageWrap.classList.add("dragging");
    });
    dom.stageWrap?.addEventListener("pointermove", (event) => {
      if (!STATE.pan) return;
      dom.stageWrap.scrollLeft = STATE.pan.left - (event.clientX - STATE.pan.x);
      dom.stageWrap.scrollTop = STATE.pan.top - (event.clientY - STATE.pan.y);
      renderMiniMap();
    });
    dom.stageWrap?.addEventListener("scroll", renderMiniMap);
    dom.miniMap?.addEventListener("click", (event) => {
      const rect = dom.miniMap.getBoundingClientRect();
      const ratioX = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      const ratioY = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
      const baseW = dom.stage.offsetWidth || 3800;
      const baseH = dom.stage.offsetHeight || 2280;
      dom.stageWrap.scrollLeft = ratioX * baseW * STATE.zoom - dom.stageWrap.clientWidth / 2;
      dom.stageWrap.scrollTop = ratioY * baseH * STATE.zoom - dom.stageWrap.clientHeight / 2;
      renderMiniMap();
    });
    dom.stage?.addEventListener("pointermove", (event) => {
      if (STATE.dragNode) {
        const node = STATE.nodes.find((item) => item.session_id === STATE.dragNode.id);
        if (!node) return;
        const dx = (event.clientX - STATE.dragNode.startX) / STATE.zoom;
        const dy = (event.clientY - STATE.dragNode.startY) / STATE.zoom;
        node.x = Math.max(30, STATE.dragNode.originX + dx);
        node.y = Math.max(30, STATE.dragNode.originY + dy);
        renderAll();
        return;
      }
      if (STATE.dragGroup) {
        const group = STATE.groups.find((item) => item.id === STATE.dragGroup.id);
        if (!group) return;
        const dx = (event.clientX - STATE.dragGroup.startX) / STATE.zoom;
        const dy = (event.clientY - STATE.dragGroup.startY) / STATE.zoom;
        group.x = Math.max(40, STATE.dragGroup.originX + dx);
        group.y = Math.max(40, STATE.dragGroup.originY + dy);
        renderAll();
        return;
      }
      if (STATE.relationDraft) {
        const stageRect = dom.stage.getBoundingClientRect();
        STATE.relationDraft.currentX = (event.clientX - stageRect.left) / STATE.zoom;
        STATE.relationDraft.currentY = (event.clientY - stageRect.top) / STATE.zoom;
        renderLinks();
        return;
      }
      if (STATE.resizeGroup) {
        const group = STATE.groups.find((item) => item.id === STATE.resizeGroup.id);
        if (!group) return;
        const dx = (event.clientX - STATE.resizeGroup.startX) / STATE.zoom;
        const dy = (event.clientY - STATE.resizeGroup.startY) / STATE.zoom;
        let nextX = STATE.resizeGroup.originX;
        let nextY = STATE.resizeGroup.originY;
        let nextW = STATE.resizeGroup.originW;
        let nextH = STATE.resizeGroup.originH;
        const corner = STATE.resizeGroup.corner;
        if (corner.includes("e")) nextW = STATE.resizeGroup.originW + dx;
        if (corner.includes("s")) nextH = STATE.resizeGroup.originH + dy;
        if (corner.includes("w")) {
          nextX = STATE.resizeGroup.originX + dx;
          nextW = STATE.resizeGroup.originW - dx;
        }
        if (corner.includes("n")) {
          nextY = STATE.resizeGroup.originY + dy;
          nextH = STATE.resizeGroup.originH - dy;
        }
        group.x = nextX;
        group.y = nextY;
        group.w = Math.max(32, nextW);
        group.h = Math.max(32, nextH);
        renderAll();
      }
    });
    window.addEventListener("pointerup", (event) => {
      if (STATE.dragNode || STATE.dragGroup || STATE.resizeGroup) persistLayoutStore();
      STATE.dragNode = null;
      STATE.dragGroup = null;
      STATE.resizeGroup = null;
      if (STATE.pan) {
        dom.stageWrap?.classList.remove("dragging");
        STATE.pan = null;
      }
      if (STATE.relationDraft) {
        const target = document.elementFromPoint(event.clientX, event.clientY);
        const connector = target && target.closest ? target.closest(".connector") : null;
        const hostNode = connector && connector.closest
          ? connector.closest(".node")
          : (target && target.closest ? target.closest(".node") : null);
        const targetSessionId = hostNode ? safeText(hostNode.getAttribute("data-session-id")) : "";
        const targetSide = connector
          ? safeText(connector.getAttribute("data-side"), "left")
          : inferNodeSideFromPoint(hostNode, event.clientX, event.clientY);
        if (targetSessionId && completeRelationDraft(targetSessionId, targetSide)) return;
        STATE.relationDraft = null;
        renderLinks();
      }
    });
    dom.linesSvg?.addEventListener("click", () => {
      STATE.selectedRelationId = "";
      renderDetail();
    });
    dom.stage?.addEventListener("click", (event) => {
      if (event.target === dom.stage || event.target === dom.groupsLayer || event.target === dom.linesSvg) {
        if (STATE.relationDraft) {
          STATE.relationDraft = null;
        }
        STATE.selectedGroupId = "";
        STATE.selectedSessionId = "";
        STATE.selectedRelationId = "";
        renderAll();
      }
    });
    window.addEventListener("resize", () => {
      syncZoom();
      renderMiniMap();
    });
  }

  function init() {
    const route = qs();
    STATE.projectId = route.projectId;
    STATE.channelHint = route.channelName;
    STATE.sessionHint = route.sessionId;
    const projectMeta = projectMetaById(STATE.projectId);
    STATE.projectName = firstText([projectMeta && projectMeta.project_name, STATE.projectId], STATE.projectId);
    syncTimeControls();
    bindEvents();
    loadData();
  }

  init();
})();
