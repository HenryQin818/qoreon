(() => {
  const DATA = JSON.parse(document.getElementById("data")?.textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const TOKEN_KEY = "taskDashboard.token";
  const AVATAR_V1_KEY = "taskDashboard.avatarAssignments.v1";
  const AVATAR_V2_KEY = "taskDashboard.avatarAssignments.v2";
  const SHARED_AVATAR_API = "/api/avatar-assignments";
  const TIME_WIDTH = 108;
  const AGENT_WIDTH = 196;
  const EVENT_WIDTH = 148;
  const CANVAS_RIGHT_GUTTER = 236;
  const CANVAS_BOTTOM_GUTTER = 208;
  const PROJECT_HEADER_HEIGHT = 42;
  const AGENT_HEADER_HEIGHT = 96;
  const BASE_HEIGHT_MIN = 920;
  const MIN_ZOOM = 0.45;
  const MAX_ZOOM = 1.4;
  const ZOOM_STEP = 0.1;
  const TIMELINE_STRETCH_KEY = "taskDashboard.agentCurtain.timelineStretch";
  const MIN_TIMELINE_STRETCH = 1;
  const MAX_TIMELINE_STRETCH = 3.5;
  const TIMELINE_STRETCH_STEP = 0.25;
  const WINDOW_MS = {
    "1h": 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
  };
  const PROJECT_PALETTE = [
    "#63dac8",
    "#7db7ff",
    "#f4c86d",
    "#f7a8c2",
    "#b8a7ff",
    "#86efac",
    "#fb923c",
    "#67e8f9",
    "#c084fc",
    "#fca5a5",
  ];
  const WINDOW_SLOT_MS = {
    "1h": 10 * 60 * 1000,
    "6h": 60 * 60 * 1000,
    "24h": 4 * 60 * 60 * 1000,
  };
  const EVENT_TYPES = {
    dispatch: { label: "dispatch", tone: "dispatch" },
    reply: { label: "reply", tone: "reply" },
    system: { label: "system", tone: "system" },
    close: { label: "close", tone: "close" },
    blocked: { label: "blocked", tone: "blocked" },
  };
  const AVATAR_CATALOG = [
    ["chief", "总控指挥", "🧭", "#dbeafe", "#bfdbfe"],
    ["pmo", "督办PMO", "📣", "#fef3c7", "#fde68a"],
    ["planner", "需求规划", "🗺️", "#e0e7ff", "#c7d2fe"],
    ["prototype", "原型设计", "🧩", "#ede9fe", "#ddd6fe"],
    ["ui", "UI视觉", "🎨", "#fae8ff", "#f5d0fe"],
    ["ux", "交互体验", "🖱️", "#fce7f3", "#fbcfe8"],
    ["frontend", "前端开发", "💻", "#dcfce7", "#bbf7d0"],
    ["backend", "后端开发", "🧱", "#d1fae5", "#a7f3d0"],
    ["api", "接口契约", "🔌", "#cffafe", "#a5f3fc"],
    ["data", "数据治理", "🧮", "#e0f2fe", "#bae6fd"],
    ["runtime", "运行时", "⚙️", "#f1f5f9", "#e2e8f0"],
    ["scheduler", "任务调度", "🕒", "#fef9c3", "#fde047"],
    ["ai-engine", "AI引擎", "🤖", "#ecfccb", "#d9f99d"],
    ["adapter", "多CLI适配", "🔀", "#ccfbf1", "#99f6e4"],
    ["qa", "测试验收", "✅", "#dcfce7", "#86efac"],
    ["regression", "回归测试", "♻️", "#ecfccb", "#bef264"],
    ["release", "发布管控", "🚀", "#ede9fe", "#c4b5fd"],
    ["ops", "运维巡检", "🛠️", "#ffedd5", "#fdba74"],
    ["sre", "稳定性SRE", "🛡️", "#dbeafe", "#93c5fd"],
    ["alarm", "异常告警", "🚨", "#fee2e2", "#fecaca"],
    ["security", "安全审查", "🔐", "#f3e8ff", "#e9d5ff"],
    ["compliance", "合规审查", "📜", "#fae8ff", "#e9d5ff"],
    ["doc", "文档沉淀", "🗂️", "#f8fafc", "#e2e8f0"],
    ["knowledge", "知识库", "📚", "#e0f2fe", "#bae6fd"],
    ["collab", "跨通道协作", "🤝", "#d1fae5", "#6ee7b7"],
    ["announce", "通道通知", "📨", "#fef3c7", "#fcd34d"],
    ["meeting", "对齐会议", "🧑‍💼", "#ede9fe", "#c4b5fd"],
    ["archive", "归档收口", "📦", "#e2e8f0", "#cbd5e1"],
    ["board", "看板可视化", "📊", "#cffafe", "#67e8f9"],
    ["org", "组织架构", "🕸️", "#e0e7ff", "#a5b4fc"],
    ["timeline", "进度时间线", "📈", "#dcfce7", "#86efac"],
    ["message", "消息治理", "💬", "#fee2e2", "#fda4af"],
    ["memo", "备忘提醒", "📝", "#fef9c3", "#fde68a"],
    ["avatar", "头像管理", "🧑", "#fae8ff", "#f5d0fe"],
    ["inspector", "自动巡查", "🔍", "#dbeafe", "#93c5fd"],
    ["heartbeat", "心跳监控", "💓", "#fee2e2", "#fca5a5"],
    ["queue", "队列治理", "🧵", "#ecfccb", "#bef264"],
    ["callback", "系统回执", "📬", "#e0f2fe", "#7dd3fc"],
    ["escalate", "升级处理", "⬆️", "#ffedd5", "#fdba74"],
    ["product", "产品经理", "👩‍💼", "#fce7f3", "#fbcfe8"],
    ["engineer", "工程师", "👨‍💻", "#dcfce7", "#86efac"],
    ["tester", "测试同学", "🧪", "#cffafe", "#67e8f9"],
    ["analyst", "业务分析", "🔎", "#f3e8ff", "#ddd6fe"],
    ["designer", "设计师", "🖌️", "#fae8ff", "#f5d0fe"],
    ["mentor", "协同教练", "🧠", "#fef3c7", "#fde68a"],
    ["finance", "成本评估", "💰", "#ecfccb", "#bef264"],
    ["crm", "客户沟通", "☎️", "#dbeafe", "#bfdbfe"],
    ["contract", "合同流程", "📄", "#f1f5f9", "#cbd5e1"],
    ["delivery", "交付推进", "🚚", "#ffedd5", "#fed7aa"],
    ["risk", "风险管理", "⚠️", "#fee2e2", "#fecaca"],
    ["decision", "决策支持", "🎯", "#e0e7ff", "#c7d2fe"],
    ["customer", "用户成功", "🙋", "#dcfce7", "#bbf7d0"],
    ["growth", "增长运营", "📣", "#fef3c7", "#fcd34d"],
    ["notion", "知识协同", "🗃️", "#e2e8f0", "#cbd5e1"],
    ["github", "代码协同", "🐙", "#e0e7ff", "#a5b4fc"],
    ["chat", "对话协同", "🗨️", "#fce7f3", "#fbcfe8"],
    ["cloud", "云端同步", "☁️", "#cffafe", "#a5f3fc"],
    ["local", "本地运行", "🖥️", "#f1f5f9", "#cbd5e1"],
    ["script", "自动脚本", "📟", "#e0f2fe", "#bae6fd"],
  ].map(([id, name, emoji, c1, c2]) => ({ id, name, emoji, c1, c2 }));
  const AVATAR_MAP = new Map(AVATAR_CATALOG.map((it) => [String(it.id), it]));

  const STATE = {
    mode: "project",
    projectId: "",
    channelHint: "",
    sessionHint: "",
    windowKey: "1h",
    agentOrderMode: "default",
    showLinks: true,
    showSystem: true,
    showDone: true,
    zoom: 1,
    timelineStretch: 1,
    customRange: {
      startMs: 0,
      endMs: 0,
    },
    activeRange: {
      startMs: 0,
      endMs: 0,
      label: "1h",
      isCustom: false,
    },
    health: null,
    sessions: [],
    sharedAvatarStore: { bySessionId: {}, clearedSessionIds: {} },
    sessionMap: new Map(),
    projectCatalog: [],
    agentRows: [],
    events: [],
    links: [],
    layoutEvents: [],
    selectedEventId: "",
    linkTypeVisibility: {
      dispatch: true,
      reply: true,
      system: true,
    },
    canvasWidth: TIME_WIDTH + AGENT_WIDTH,
    canvasHeight: BASE_HEIGHT_MIN,
    dragPan: null,
  };

  const dom = {
    envBadge: document.getElementById("envBadge"),
    overviewLink: document.getElementById("overviewLink"),
    taskLink: document.getElementById("taskLink"),
    toolbarLegend: document.getElementById("toolbarLegend"),
    projectMeta: document.getElementById("projectMeta"),
    summaryMeta: document.getElementById("summaryMeta"),
    stateBanner: document.getElementById("stateBanner"),
    stageWrap: document.getElementById("stageWrap"),
    curtainViewport: document.getElementById("curtainViewport"),
    curtainSizer: document.getElementById("curtainSizer"),
    curtain: document.getElementById("curtain"),
    timeCorner: document.getElementById("timeCorner"),
    timeCol: document.getElementById("timeCol"),
    regionsLayer: document.getElementById("regionsLayer"),
    projectsLayer: document.getElementById("projectsLayer"),
    agentHeadsLayer: document.getElementById("agentHeadsLayer"),
    agentsLayer: document.getElementById("agentsLayer"),
    eventsLayer: document.getElementById("eventsLayer"),
    linksSvg: document.getElementById("linksSvg"),
    refreshBtn: document.getElementById("refreshBtn"),
    orderTabs: document.getElementById("orderTabs"),
    windowTabs: document.getElementById("windowTabs"),
    customRangeBar: document.getElementById("customRangeBar"),
    customStartInput: document.getElementById("customStartInput"),
    customEndInput: document.getElementById("customEndInput"),
    customApplyBtn: document.getElementById("customApplyBtn"),
    customResetBtn: document.getElementById("customResetBtn"),
    toggleLinks: document.getElementById("toggleLinks"),
    toggleSystem: document.getElementById("toggleSystem"),
    toggleDone: document.getElementById("toggleDone"),
    zoomOutBtn: document.getElementById("zoomOutBtn"),
    zoomResetBtn: document.getElementById("zoomResetBtn"),
    zoomInBtn: document.getElementById("zoomInBtn"),
    timeScaleSlider: document.getElementById("timeScaleSlider"),
    timeScaleLabel: document.getElementById("timeScaleLabel"),
    timeScaleShrinkBtn: document.getElementById("timeScaleShrinkBtn"),
    timeScaleExpandBtn: document.getElementById("timeScaleExpandBtn"),
    miniMap: document.getElementById("miniMap"),
    miniViewport: document.getElementById("miniViewport"),
  };

  let viewportSyncFrame = 0;

  function authHeaders(base = {}) {
    const headers = { ...(base || {}) };
    try {
      const token = localStorage.getItem(TOKEN_KEY);
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch (_) {}
    return headers;
  }

  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === "class") node.className = String(value || "");
      else if (key === "text") node.textContent = String(value || "");
      else if (key === "html") node.innerHTML = String(value || "");
      else if (key === "data" && value && typeof value === "object") {
        Object.entries(value).forEach(([dkey, dval]) => { node.dataset[dkey] = String(dval); });
      } else {
        node.setAttribute(key, String(value));
      }
    });
    (children || []).forEach((child) => node.appendChild(child));
    return node;
  }

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

  function shortId(value) {
    const text = safeText(value);
    if (!text) return "-";
    return text.length <= 12 ? text : `${text.slice(0, 8)}...${text.slice(-4)}`;
  }

  function dateMs(value) {
    if (!value) return 0;
    const n = Date.parse(String(value));
    return Number.isFinite(n) ? n : 0;
  }

  function pad2(value) {
    return String(Math.max(0, Number(value) || 0)).padStart(2, "0");
  }

  function clampTimelineStretch(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return MIN_TIMELINE_STRETCH;
    const rounded = Math.round(numeric / TIMELINE_STRETCH_STEP) * TIMELINE_STRETCH_STEP;
    return Math.max(MIN_TIMELINE_STRETCH, Math.min(MAX_TIMELINE_STRETCH, Number(rounded.toFixed(2))));
  }

  function formatTimelineStretch(value) {
    const numeric = clampTimelineStretch(value);
    const text = numeric.toFixed(2).replace(/\.00$/, ".0").replace(/(\.\d)0$/, "$1");
    return `${text}x`;
  }

  function readTimelineStretch() {
    try {
      return clampTimelineStretch(localStorage.getItem(TIMELINE_STRETCH_KEY));
    } catch (_) {
      return MIN_TIMELINE_STRETCH;
    }
  }

  function persistTimelineStretch() {
    try {
      localStorage.setItem(TIMELINE_STRETCH_KEY, String(clampTimelineStretch(STATE.timelineStretch)));
    } catch (_) {}
  }

  function formatDateTimeLocal(value) {
    const ts = typeof value === "number" ? value : dateMs(value);
    if (!ts) return "";
    const dt = new Date(ts);
    return [
      dt.getFullYear(),
      "-",
      pad2(dt.getMonth() + 1),
      "-",
      pad2(dt.getDate()),
      "T",
      pad2(dt.getHours()),
      ":",
      pad2(dt.getMinutes()),
    ].join("");
  }

  function formatRangeLabel(startMs, endMs) {
    if (!startMs || !endMs || endMs <= startMs) return "自定义";
    const start = new Date(startMs);
    const end = new Date(endMs);
    const sameDay = start.toDateString() === end.toDateString();
    const startDate = `${pad2(start.getMonth() + 1)}-${pad2(start.getDate())}`;
    const endDate = `${pad2(end.getMonth() + 1)}-${pad2(end.getDate())}`;
    const startTime = `${pad2(start.getHours())}:${pad2(start.getMinutes())}`;
    const endTime = `${pad2(end.getHours())}:${pad2(end.getMinutes())}`;
    return sameDay ? `自定义 ${startDate} ${startTime}-${endTime}` : `自定义 ${startDate} ${startTime} ~ ${endDate} ${endTime}`;
  }

  function formatIsoTime(value) {
    const ts = typeof value === "number" ? value : dateMs(value);
    if (!ts) return "";
    return new Date(ts).toISOString();
  }

  function parseDateTimeInput(value) {
    const text = safeText(value);
    if (!text) return 0;
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function hashCode(text) {
    const source = safeText(text);
    let hash = 0;
    for (let i = 0; i < source.length; i += 1) hash = ((hash * 31) + source.charCodeAt(i)) >>> 0;
    return hash >>> 0;
  }

  function hexToRgb(hex) {
    const text = safeText(hex).replace(/^#/, "");
    if (!text) return null;
    const normalized = text.length === 3 ? text.split("").map((it) => `${it}${it}`).join("") : text;
    if (!/^[0-9a-f]{6}$/i.test(normalized)) return null;
    return {
      r: parseInt(normalized.slice(0, 2), 16),
      g: parseInt(normalized.slice(2, 4), 16),
      b: parseInt(normalized.slice(4, 6), 16),
    };
  }

  function rgbaFromColor(color, alpha) {
    const rgb = hexToRgb(color);
    if (!rgb) return `rgba(99, 218, 200, ${alpha})`;
    return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
  }

  function fmtDate(value) {
    const ts = dateMs(value);
    if (!ts) return "-";
    return new Date(ts).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  function fmtTime(value) {
    const ts = typeof value === "number" ? value : dateMs(value);
    if (!ts) return "--:--";
    return new Date(ts).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  function fmtTimelineTick(value, spanMs = 0) {
    const ts = typeof value === "number" ? value : dateMs(value);
    if (!ts) return "--:--";
    if (spanMs > (24 * 60 * 60 * 1000)) {
      return new Date(ts).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).replace(",", " ");
    }
    return fmtTime(ts);
  }

  function qs() {
    try {
      const search = new URLSearchParams(window.location.search || "");
      const hash = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
      const rawMode = String(search.get("mode") || hash.get("mode") || "").trim().toLowerCase();
      return {
        mode: rawMode === "global" ? "global" : "project",
        projectId: String(search.get("project_id") || search.get("projectId") || hash.get("p") || DATA.project_id || DATA.projectId || "").trim(),
        channelName: String(search.get("channel_name") || search.get("channelName") || hash.get("c") || DATA.channel_name || DATA.channelName || "").trim(),
        sessionId: String(search.get("session_id") || search.get("sessionId") || hash.get("sid") || DATA.session_id || DATA.sessionId || "").trim(),
      };
    } catch (_) {
      return { mode: "project", projectId: "", channelName: "", sessionId: "" };
    }
  }

  function uniqBy(items, keyFn) {
    const seen = new Set();
    const rows = [];
    (items || []).forEach((item) => {
      const key = safeText(keyFn(item));
      if (!key || seen.has(key)) return;
      seen.add(key);
      rows.push(item);
    });
    return rows;
  }

  function projectCatalog() {
    const primary = Array.isArray(DATA.projects) ? DATA.projects : [];
    const overviewProjects = Array.isArray(DATA.overview && DATA.overview.projects) ? DATA.overview.projects : [];
    const merged = [
      ...primary.map((item) => ({
        project_id: safeText(item.id || item.project_id),
        project_name: firstText([item.name, item.project_name, item.id]),
        color: safeText(item.color),
      })),
      ...overviewProjects.map((item) => ({
        project_id: safeText(item.project_id || item.id),
        project_name: firstText([item.project_name, item.name, item.project_id, item.id]),
        color: safeText(item.color),
      })),
    ].filter((item) => item.project_id);
    return uniqBy(merged, (item) => item.project_id);
  }

  function projectMetaById(projectId) {
    const normalized = safeText(projectId);
    if (!normalized) return null;
    return STATE.projectCatalog.find((item) => safeText(item.project_id) === normalized) || null;
  }

  function projectNameById(projectId) {
    const normalized = safeText(projectId);
    if (!normalized) return "";
    const found = projectMetaById(normalized);
    return firstText([found && found.project_name, normalized], normalized);
  }

  function projectAccent(projectId) {
    const found = projectMetaById(projectId);
    const explicit = safeText(found && found.color);
    if (hexToRgb(explicit)) return explicit.startsWith("#") ? explicit : `#${explicit.replace(/^#/, "")}`;
    return PROJECT_PALETTE[hashCode(projectId) % PROJECT_PALETTE.length];
  }

  function headerStackHeight() {
    return AGENT_HEADER_HEIGHT + (STATE.mode === "global" ? PROJECT_HEADER_HEIGHT : 0);
  }

  function timelineTopOffset() {
    return headerStackHeight() + 24;
  }

  function syncCustomInputs() {
    if (dom.customStartInput) dom.customStartInput.value = formatDateTimeLocal(STATE.customRange.startMs);
    if (dom.customEndInput) dom.customEndInput.value = formatDateTimeLocal(STATE.customRange.endMs);
  }

  function ensureCustomRange(seedEndMs = 0) {
    const currentStart = Number(STATE.customRange.startMs) || 0;
    const currentEnd = Number(STATE.customRange.endMs) || 0;
    if (currentStart && currentEnd && currentEnd > currentStart) {
      syncCustomInputs();
      return;
    }
    const endMs = seedEndMs || Date.now();
    STATE.customRange.endMs = endMs;
    STATE.customRange.startMs = endMs - WINDOW_MS["1h"];
    syncCustomInputs();
  }

  function resolveTimeRange(runs) {
    if (STATE.windowKey === "custom") {
      ensureCustomRange();
      const startMs = Number(STATE.customRange.startMs) || 0;
      const endMs = Number(STATE.customRange.endMs) || 0;
      return {
        startMs,
        endMs: endMs > startMs ? endMs : (startMs + WINDOW_MS["1h"]),
        label: formatRangeLabel(startMs, endMs),
        isCustom: true,
      };
    }
    const windowMs = WINDOW_MS[STATE.windowKey] || WINDOW_MS["1h"];
    const maxTs = (runs || []).reduce((acc, run) => Math.max(acc, dateMs(run.created_at)), 0) || Date.now();
    return {
      startMs: Math.max(0, maxTs - windowMs),
      endMs: maxTs,
      label: STATE.windowKey,
      isCustom: false,
    };
  }

  function slotMsForRange(spanMs) {
    if (spanMs <= (2 * 60 * 60 * 1000)) return 10 * 60 * 1000;
    if (spanMs <= (12 * 60 * 60 * 1000)) return 60 * 60 * 1000;
    if (spanMs <= (2 * 24 * 60 * 60 * 1000)) return 4 * 60 * 60 * 1000;
    if (spanMs <= (7 * 24 * 60 * 60 * 1000)) return 12 * 60 * 60 * 1000;
    return 24 * 60 * 60 * 1000;
  }

  function emptyAvatarStore() {
    return { version: 2, bySessionId: Object.create(null), clearedSessionIds: Object.create(null) };
  }

  function normalizeAvatarStore(data) {
    const src = (data && typeof data === "object") ? data : {};
    return {
      version: 2,
      bySessionId: Object.assign(Object.create(null), src && typeof src.bySessionId === "object" ? src.bySessionId : {}),
      clearedSessionIds: Object.assign(Object.create(null), src && typeof src.clearedSessionIds === "object" ? src.clearedSessionIds : {}),
    };
  }

  function getAvatarAssignmentsV1() {
    try {
      const raw = String(localStorage.getItem(AVATAR_V1_KEY) || "");
      if (!raw) return Object.create(null);
      const data = JSON.parse(raw);
      return Object.assign(Object.create(null), data && typeof data.assignments === "object" ? data.assignments : {});
    } catch (_) {
      return Object.create(null);
    }
  }

  function getAvatarStoreV2() {
    try {
      const raw = String(localStorage.getItem(AVATAR_V2_KEY) || "");
      if (!raw) return emptyAvatarStore();
      return normalizeAvatarStore(JSON.parse(raw));
    } catch (_) {
      return emptyAvatarStore();
    }
  }

  async function fetchSharedAvatarStore(projectId) {
    if (!projectId) return emptyAvatarStore();
    try {
      const resp = await fetch(`${SHARED_AVATAR_API}?project_id=${encodeURIComponent(projectId)}`, { cache: "no-store", headers: authHeaders() });
      if (!resp.ok) return emptyAvatarStore();
      return normalizeAvatarStore(await resp.json());
    } catch (_) {
      return emptyAvatarStore();
    }
  }

  function avatarFallbackLabel(name) {
    const text = safeText(name, "会");
    const digits = text.match(/\d+/);
    if (digits && digits[0]) return digits[0].slice(0, 2);
    return text.slice(0, 1).toUpperCase();
  }

  function sessionDisplayName(sessionLike) {
    return firstText([
      sessionLike.alias,
      sessionLike.display_name,
      sessionLike.displayName,
      sessionLike.sender_name,
      sessionLike.channel_name,
      sessionLike.channelName,
      sessionLike.session_id,
      sessionLike.id,
    ], "未命名会话");
  }

  function getAssignedAvatarId(sessionLike) {
    const sessionId = safeText(sessionLike.session_id || sessionLike.id);
    const storeV2 = getAvatarStoreV2();
    if (sessionId && storeV2.clearedSessionIds && storeV2.clearedSessionIds[sessionId]) return "";
    const localId = sessionId ? safeText(storeV2.bySessionId && storeV2.bySessionId[sessionId]) : "";
    if (localId && AVATAR_MAP.has(localId)) return localId;
    const sharedId = sessionId ? safeText(STATE.sharedAvatarStore.bySessionId && STATE.sharedAvatarStore.bySessionId[sessionId]) : "";
    if (sharedId && AVATAR_MAP.has(sharedId)) return sharedId;
    const v1 = getAvatarAssignmentsV1();
    const candidates = [
      sessionDisplayName(sessionLike),
      safeText(sessionLike.channel_name),
      safeText(sessionLike.channelName),
      safeText(sessionLike.alias),
    ].filter(Boolean);
    for (const key of candidates) {
      const avatarId = safeText(v1[key]);
      if (avatarId && AVATAR_MAP.has(avatarId)) return avatarId;
    }
    return "";
  }

  function avatarMeta(sessionLike) {
    const avatarId = getAssignedAvatarId(sessionLike);
    if (avatarId && AVATAR_MAP.has(avatarId)) {
      const meta = AVATAR_MAP.get(avatarId);
      return {
        text: String(meta.emoji || "🧑"),
        title: `${sessionDisplayName(sessionLike)} · ${meta.name || avatarId}`,
        c1: String(meta.c1 || "#edf2ff"),
        c2: String(meta.c2 || "#dbe5ff"),
        fallback: false,
      };
    }
    return {
      text: avatarFallbackLabel(sessionDisplayName(sessionLike)),
      title: sessionDisplayName(sessionLike),
      c1: "#edf2ff",
      c2: "#dbe5ff",
      fallback: true,
    };
  }

  function readHealth() {
    return fetch("/__health", { cache: "no-store" }).then((resp) => (resp.ok ? resp.json() : null)).catch(() => null);
  }

  async function fetchJson(url) {
    const resp = await fetch(url, { cache: "no-store", headers: authHeaders() });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  }

  function normalizeSession(raw) {
    if (!raw || typeof raw !== "object") return null;
    const sessionId = firstText([raw.id, raw.session_id, raw.sessionId]);
    if (!sessionId) return null;
    const runtimeState = (raw.runtime_state && typeof raw.runtime_state === "object") ? raw.runtime_state : {};
    return {
      session_id: sessionId,
      alias: firstText([raw.alias, raw.channel_name, raw.channelName, raw.display_name, raw.displayName, sessionId]),
      channel_name: firstText([raw.channel_name, raw.channelName]),
      project_id: firstText([raw.project_id, raw.projectId]),
      project_name: firstText([raw.project_name, raw.projectName]),
      cli_type: firstText([raw.cli_type, raw.cliType], "codex"),
      status: firstText([runtimeState.display_state, runtimeState.internal_state, raw.status], "idle"),
      environment: firstText([raw.environment], "stable"),
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
    const topLevelKind = normalizeMessageKind(firstText([run.message_kind, run.messageKind]));
    if (topLevelKind) return topLevelKind;
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

  function normalizeMessageRef(raw) {
    const src = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : {};
    const out = {
      project_id: firstText([src.project_id, src.projectId]),
      channel_name: firstText([src.channel_name, src.channelName, src.channel]),
      session_id: firstText([src.session_id, src.sessionId]),
      run_id: firstText([src.run_id, src.runId]),
    };
    return Object.values(out).some(Boolean) ? out : null;
  }

  function normalizeAgentRef(raw) {
    const src = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : {};
    const out = {
      channel_name: firstText([src.channel_name, src.channelName]),
      agent_name: firstText([src.agent_name, src.agentName, src.name]),
      session_id: firstText([src.session_id, src.sessionId]),
      role: firstText([src.role]).toLowerCase(),
      alias: firstText([src.alias, src.agent_name, src.agentName, src.display_name, src.displayName]),
    };
    return Object.values(out).some(Boolean) ? out : null;
  }

  function normalizeProjectExecutionContextRef(raw) {
    const src = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : {};
    const out = {
      project_id: firstText([src.project_id, src.projectId]),
      channel_name: firstText([src.channel_name, src.channelName]),
      session_id: firstText([src.session_id, src.sessionId]),
      run_id: firstText([src.run_id, src.runId]),
      environment: firstText([src.environment]),
      worktree_root: firstText([src.worktree_root, src.worktreeRoot]),
      workdir: firstText([src.workdir]),
      branch: firstText([src.branch]),
    };
    return Object.values(out).some(Boolean) ? out : null;
  }

  function normalizeProjectExecutionContextMeta(raw) {
    const src = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : {};
    const override = (src.override && typeof src.override === "object" && !Array.isArray(src.override)) ? src.override : {};
    const fields = Array.isArray(override.fields)
      ? override.fields.map((item) => safeText(item)).filter(Boolean)
      : [];
    const out = {
      target: normalizeProjectExecutionContextRef(src.target || src.target_ref || src.targetRef),
      source: normalizeProjectExecutionContextRef(src.source || src.source_ref || src.sourceRef),
      context_source: firstText([src.context_source, src.contextSource]).toLowerCase(),
      override: {
        applied: override.applied === true || fields.length > 0,
        fields,
        source: firstText([override.source, src.override_source, src.overrideSource]).toLowerCase(),
      },
    };
    const hasOverride = out.override.applied || out.override.fields.length || out.override.source;
    return (out.target || out.source || out.context_source || hasOverride) ? out : null;
  }

  function normalizeMentionTargets(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map((item) => {
      const src = (item && typeof item === "object" && !Array.isArray(item)) ? item : {};
      const out = {
        project_id: firstText([src.project_id, src.projectId]),
        channel_name: firstText([src.channel_name, src.channelName]),
        session_id: firstText([src.session_id, src.sessionId]),
        cli_type: firstText([src.cli_type, src.cliType]).toLowerCase(),
        display_name: firstText([src.alias, src.display_name, src.displayName, src.agent_name, src.agentName]),
      };
      return Object.values(out).some(Boolean) ? out : null;
    }).filter(Boolean);
  }

  function normalizeCommunicationView(raw) {
    const src = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : {};
    const routeResolution = (src.route_resolution && typeof src.route_resolution === "object" && !Array.isArray(src.route_resolution))
      ? src.route_resolution
      : ((src.routeResolution && typeof src.routeResolution === "object" && !Array.isArray(src.routeResolution)) ? src.routeResolution : {});
    const out = {
      version: firstText([src.version]),
      message_kind: normalizeMessageKind(firstText([src.message_kind, src.messageKind])),
      event_reason: firstText([src.event_reason, src.eventReason]).toLowerCase(),
      dispatch_state: firstText([src.dispatch_state, src.dispatchState]).toLowerCase(),
      dispatch_run_id: firstText([src.dispatch_run_id, src.dispatchRunId]),
      route_mismatch: src.route_mismatch === true,
      source_project_id: firstText([src.source_project_id, src.sourceProjectId]),
      source_channel: firstText([src.source_channel, src.sourceChannel]),
      source_session_id: firstText([src.source_session_id, src.sourceSessionId]),
      target_project_id: firstText([src.target_project_id, src.targetProjectId]),
      target_channel: firstText([src.target_channel, src.targetChannel]),
      target_session_id: firstText([src.target_session_id, src.targetSessionId]),
      route_resolution: {
        source: firstText([routeResolution.source]).toLowerCase(),
        fallback_stage: firstText([routeResolution.fallback_stage, routeResolution.fallbackStage]).toLowerCase(),
        degrade_reason: firstText([routeResolution.degrade_reason, routeResolution.degradeReason]).toLowerCase(),
        source_ref: normalizeMessageRef(routeResolution.source_ref || routeResolution.sourceRef),
        final_target: normalizeMessageRef(routeResolution.final_target || routeResolution.finalTarget),
      },
    };
    const rr = out.route_resolution;
    const hasRouteResolution = rr.source || rr.fallback_stage || rr.degrade_reason || rr.source_ref || rr.final_target;
    return (
      out.version || out.message_kind || out.event_reason || out.dispatch_state || out.dispatch_run_id
      || out.route_mismatch || out.source_project_id || out.source_channel || out.source_session_id
      || out.target_project_id || out.target_channel || out.target_session_id || hasRouteResolution
    ) ? out : null;
  }

  function displaySenderLabel(run) {
    return firstText([run && run.sender_name, run && run.channel_name, run && run.sender_id, run && run.session_id], "未知发送方");
  }

  function buildRunMetaBits(run) {
    const bits = [];
    if (run && run.sender_type) bits.push(run.sender_type);
    if (run && run.message_kind) bits.push(messageKindLabel(run.message_kind));
    if (run && run.interaction_mode) bits.push(interactionModeLabel(run.interaction_mode) || run.interaction_mode);
    return bits.filter(Boolean);
  }

  function buildRunDetail(run) {
    const summary = safeText(run && run.message_preview, "无可展示详情");
    const lines = [summary];
    const specs = [];
    if (run && run.sender_name) specs.push(`sender_name: ${run.sender_name}`);
    if (run && run.sender_type) specs.push(`sender_type: ${run.sender_type}`);
    if (run && run.sender_id) specs.push(`sender_id: ${run.sender_id}`);
    if (run && run.message_kind) specs.push(`message_kind: ${run.message_kind}`);
    if (run && run.interaction_mode) specs.push(`interaction_mode: ${run.interaction_mode}`);
    if (run && run.source_ref_text) specs.push(`source_ref: ${run.source_ref_text}`);
    if (run && run.callback_to_text) specs.push(`callback_to: ${run.callback_to_text}`);
    if (specs.length) lines.push("", specs.join("\n"));
    return lines.join("\n");
  }

  function normalizeRun(raw) {
    if (!raw || typeof raw !== "object") return null;
    const runId = firstText([raw.id, raw.run_id, raw.runId]);
    const sessionId = firstText([raw.sessionId, raw.session_id]);
    if (!runId || !sessionId) return null;
    const communicationView = normalizeCommunicationView(readCommunicationViewMeta(raw));
    const sender = readStructuredSender(raw);
    const callbackTo = normalizeMessageRef(
      raw.callback_to
      || raw.callbackTo
      || (communicationView && communicationView.callback_to)
      || (communicationView && communicationView.callbackTo)
      || null
    );
    const sourceRef = normalizeMessageRef(
      raw.source_ref
      || raw.sourceRef
      || (communicationView && communicationView.source_ref)
      || (communicationView && communicationView.sourceRef)
      || null
    );
    const targetRef = normalizeMessageRef(
      raw.target_ref
      || raw.targetRef
      || {
        project_id: firstText([raw.project_id, raw.projectId]),
        channel_name: firstText([raw.channel_name, raw.channelName]),
        session_id: sessionId,
      }
    );
    const ownerRef = normalizeAgentRef(raw.owner_ref || raw.ownerRef || null);
    const senderAgentRef = normalizeAgentRef(raw.sender_agent_ref || raw.senderAgentRef || null);
    const projectExecutionContext = normalizeProjectExecutionContextMeta(raw.project_execution_context || raw.projectExecutionContext || null);
    const mentionTargets = normalizeMentionTargets(raw.mention_targets || raw.mentionTargets);
    return {
      run_id: runId,
      session_id: sessionId,
      project_id: firstText([raw.project_id, raw.projectId]),
      project_name: firstText([raw.project_name, raw.projectName]),
      channel_name: firstText([raw.channelName, raw.channel_name]),
      created_at: firstText([raw.createdAt, raw.created_at, raw.lastProgressAt]),
      status: normalizeRunStatus(raw),
      sender_type: sender.type,
      sender_name: firstText([sender.name]),
      sender_id: firstText([sender.id]),
      message_kind: resolveMessageKind(raw),
      interaction_mode: firstText([
        raw.interaction_mode, raw.interactionMode,
        communicationView && communicationView.interaction_mode,
        communicationView && communicationView.interactionMode,
      ]).toLowerCase(),
      reply_to_run_id: firstText([raw.reply_to_run_id, raw.replyToRunId]),
      source_channel: firstText([raw.source_channel, raw.sourceChannel, communicationView && communicationView.source_channel]),
      target_channel: firstText([raw.target_channel, raw.targetChannel, communicationView && communicationView.target_channel]),
      source_ref: sourceRef,
      source_ref_text: formatRefValue(sourceRef),
      target_ref: targetRef,
      target_ref_text: formatRefValue(targetRef),
      owner_ref: ownerRef,
      sender_agent_ref: senderAgentRef,
      project_execution_context: projectExecutionContext,
      mention_targets: mentionTargets,
      communication_view: communicationView,
      callback_to: callbackTo,
      callback_to_text: formatRefValue(callbackTo),
      message_preview: firstText([raw.messagePreview, raw.message_preview, raw.lastMessage, raw.partialMessage, raw.errorHint, raw.lastPreview]),
    };
  }

  function inferEventType(run) {
    const status = safeText(run.status).toLowerCase();
    const kind = safeText(run.message_kind).toLowerCase();
    const senderType = safeText(run.sender_type).toLowerCase();
    if (status === "error") return "blocked";
    if (kind === "system_callback" || senderType === "system") return "system";
    if (run.reply_to_run_id) return "reply";
    if (
      (run.source_ref && run.source_ref.session_id)
      || (run.target_ref && run.target_ref.session_id)
      || (run.sender_agent_ref && run.sender_agent_ref.session_id)
      || (run.owner_ref && run.owner_ref.session_id)
      || (Array.isArray(run.mention_targets) && run.mention_targets.length)
      || run.target_channel
    ) return "dispatch";
    if (status === "done") return "close";
    if (run.callback_to && (run.callback_to.session_id || run.callback_to.channel_name)) return "reply";
    if (senderType === "agent") return "dispatch";
    return "reply";
  }

  function summarizeRun(run) {
    const preview = safeText(run.message_preview);
    if (!preview) return [run.sender_name, run.message_kind, run.status].filter(Boolean).join(" · ") || "无摘要消息";
    const compact = preview.replace(/\[来源通道:[^\]]+\]/g, "").replace(/\[目标通道:[^\]]+\]/g, "").replace(/\s+/g, " ").trim();
    return compact.length > 74 ? `${compact.slice(0, 74)}...` : compact;
  }

  function parseBracketValues(text, label) {
    const results = [];
    const source = safeText(text);
    if (!source || !label) return results;
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
    if (!source) return results;
    const pattern = /@([^\s\]\[，。,:：；;（）()<>]+)/g;
    let match;
    while ((match = pattern.exec(source))) {
      const value = safeText(match[1]);
      if (value) results.push(value);
    }
    return results;
  }

  function parseTargetHints(text) {
    const source = safeText(text);
    const targetAgentBlocks = [
      ...parseBracketValues(source, "目标Agent"),
      ...parseBracketValues(source, "主负责Agent"),
    ];
    const currentSenderBlocks = parseBracketValues(source, "当前发信Agent");
    const callbackBlocks = parseBracketValues(source, "callback_to");
    const sourceRefBlocks = parseBracketValues(source, "source_ref");
    const targetRefBlocks = parseBracketValues(source, "target_ref");
    function collectSessionIds(blocks) {
      const results = [];
      const pattern = /session_id\s*=\s*([0-9a-z-]{8,})/gi;
      (blocks || []).forEach((block) => {
        let match;
        while ((match = pattern.exec(block))) {
          const value = safeText(match[1]);
          if (value) results.push(value);
        }
        pattern.lastIndex = 0;
      });
      return results;
    }
    const targetSessionIds = [
      ...collectSessionIds(targetAgentBlocks),
      ...collectSessionIds(targetRefBlocks),
      ...(() => {
        const results = [];
        const pattern = /target_session_id\s*=\s*([0-9a-z-]{8,})/gi;
        let match;
        while ((match = pattern.exec(source))) {
          const value = safeText(match[1]);
          if (value) results.push(value);
        }
        return results;
      })(),
    ];
    return {
      sourceChannels: parseBracketValues(source, "来源通道"),
      targetChannels: parseBracketValues(source, "目标通道"),
      sourceSessionIds: [
        ...collectSessionIds(currentSenderBlocks),
        ...collectSessionIds(callbackBlocks),
        ...collectSessionIds(sourceRefBlocks),
      ],
      targetSessionIds,
      targetAgents: [
        ...parseBracketValues(source, "协同对象"),
        ...targetAgentBlocks.map((value) => safeText(value.split(";")[0])),
        ...parseMentionTargets(source),
      ],
    };
  }

  function sessionNameCandidates(sessionLike) {
    return [
      safeText(sessionLike.alias),
      safeText(sessionLike.display_name),
      safeText(sessionLike.displayName),
      safeText(sessionLike.sender_name),
      safeText(sessionLike.channel_name),
      safeText(sessionLike.channelName),
    ].filter(Boolean);
  }

  function resolveTargetSessionIds(hints, agentRows) {
    const resolved = new Set();
    const bySessionId = new Map(agentRows.map((agent) => [safeText(agent.session_id), agent]));
    function addSessionId(sessionId) {
      const normalized = safeText(sessionId);
      if (normalized && bySessionId.has(normalized)) resolved.add(normalized);
    }
    function addByName(targetName) {
      const normalized = safeText(targetName);
      if (!normalized) return;
      let exact = agentRows.find((agent) => sessionNameCandidates(agent).some((name) => name === normalized));
      if (!exact) {
        exact = agentRows.find((agent) => sessionNameCandidates(agent).some((name) => name.includes(normalized) || normalized.includes(name)));
      }
      if (exact) addSessionId(exact.session_id);
    }
    (hints.targetSessionIds || []).forEach(addSessionId);
    (hints.targetAgents || []).forEach(addByName);
    return Array.from(resolved);
  }

  function resolveUniqueChannelSessionId(channelName, agentRows) {
    const normalized = safeText(channelName);
    if (!normalized) return "";
    const matches = (agentRows || []).filter((agent) => safeText(agent && agent.channel_name) === normalized);
    return matches.length === 1 ? safeText(matches[0].session_id) : "";
  }

  function resolveUniqueAgentSessionId(agentName, agentRows) {
    const normalized = safeText(agentName);
    if (!normalized) return "";
    const matches = (agentRows || []).filter((agent) => safeText(agent && agent.alias) === normalized);
    return matches.length === 1 ? safeText(matches[0].session_id) : "";
  }

  function nearestEventForSession(events, sessionId, eventTs, direction) {
    const candidates = events.filter((item) => item.session_id === sessionId);
    if (!candidates.length) return null;
    const sorted = candidates.sort((a, b) => dateMs(a.created_at) - dateMs(b.created_at));
    if (direction === "before") {
      const prior = sorted.filter((item) => dateMs(item.created_at) <= eventTs);
      return prior.length ? prior[prior.length - 1] : sorted[0];
    }
    if (direction === "after") {
      const later = sorted.filter((item) => dateMs(item.created_at) >= eventTs);
      return later.length ? later[0] : sorted[sorted.length - 1];
    }
    return sorted[0];
  }

  function filterRunsByVisibleSessions(runs, sessions) {
    const visibleSessionIds = new Set((sessions || []).map((session) => safeText(session && session.session_id)).filter(Boolean));
    if (!visibleSessionIds.size) return [];
    return (runs || []).filter((run) => visibleSessionIds.has(safeText(run && run.session_id)));
  }

  function filterRunsByWindow(runs, range) {
    const startMs = Number(range && range.startMs) || 0;
    const endMs = Number(range && range.endMs) || Date.now();
    return runs.filter((run) => {
      const created = dateMs(run.created_at);
      if (!created) return false;
      if (!STATE.showSystem && run.sender_type === "system") return false;
      if (!STATE.showDone && ["done", "error"].includes(run.status)) return false;
      return created >= startMs && created <= endMs;
    }).sort((a, b) => dateMs(a.created_at) - dateMs(b.created_at));
  }

  function isLinkTypeVisible(type) {
    const key = safeText(type).toLowerCase();
    if (!key) return true;
    return STATE.linkTypeVisibility[key] !== false;
  }

  function filterLinksByType(links) {
    return (links || []).filter((link) => isLinkTypeVisible(link && link.type));
  }

  function visibleLinks() {
    if (!STATE.showLinks) return [];
    return filterLinksByType(STATE.links);
  }

  function compareAgentRowsBase(a, b) {
    const projectCmp = firstText([a.project_name, a.project_id]).localeCompare(firstText([b.project_name, b.project_id]), "zh-Hans-CN");
    if (projectCmp !== 0) return projectCmp;
    return sessionDisplayName(a).localeCompare(sessionDisplayName(b), "zh-Hans-CN");
  }

  function deriveAgentRows(sessions, events) {
    const map = new Map();
    const statsBySession = new Map();
    (events || []).forEach((event) => {
      const sessionId = safeText(event && event.session_id);
      if (!sessionId) return;
      const eventTs = dateMs(event && event.created_at);
      const current = statsBySession.get(sessionId) || { event_count: 0, last_event_ms: 0 };
      current.event_count += 1;
      current.last_event_ms = Math.max(current.last_event_ms, eventTs);
      statsBySession.set(sessionId, current);
    });
    (sessions || []).forEach((session) => {
      const sessionId = safeText(session && session.session_id);
      if (!sessionId) return;
      const stats = statsBySession.get(sessionId) || { event_count: 0, last_event_ms: 0 };
      map.set(sessionId, { ...session, session_id: sessionId, ...stats });
    });
    return Array.from(map.values()).sort((a, b) => {
      if (STATE.agentOrderMode === "volume") {
        const countCmp = (Number(b.event_count) || 0) - (Number(a.event_count) || 0);
        if (countCmp !== 0) return countCmp;
        const lastCmp = (Number(b.last_event_ms) || 0) - (Number(a.last_event_ms) || 0);
        if (lastCmp !== 0) return lastCmp;
      }
      return compareAgentRowsBase(a, b);
    });
  }

  function refreshAgentLayoutState() {
    STATE.agentRows = deriveAgentRows(STATE.sessions, STATE.events);
    STATE.links = buildLinks(STATE.events, STATE.agentRows);
  }

  function buildEventRows(runs) {
    return runs.map((run) => {
      const eventType = inferEventType(run);
      const hints = parseTargetHints(run.message_preview);
      const mentionTargetSessionIds = (run.mention_targets || []).map((item) => safeText(item && item.session_id)).filter(Boolean);
      const mentionTargetNames = (run.mention_targets || []).map((item) => firstText([
        item && item.display_name,
        item && item.channel_name,
      ])).filter(Boolean);
      const relationHints = {
        ...hints,
        targetSessionIds: Array.from(new Set([...(hints.targetSessionIds || []), ...mentionTargetSessionIds])),
        targetAgents: Array.from(new Set([...(hints.targetAgents || []), ...mentionTargetNames])),
      };
      return {
        event_id: `${run.run_id}:${eventType}`,
        run_id: run.run_id,
        session_id: run.session_id,
        project_id: run.project_id,
        project_name: run.project_name,
        channel_name: run.channel_name,
        created_at: run.created_at,
        status: run.status,
        sender_type: run.sender_type,
        sender_name: run.sender_name,
        sender_id: run.sender_id,
        message_kind: run.message_kind,
        interaction_mode: run.interaction_mode,
        type: eventType,
        title: summarizeRun(run),
        detail: buildRunDetail(run),
        meta: [fmtTime(run.created_at), displaySenderLabel(run), ...buildRunMetaBits(run)].filter(Boolean).join(" · "),
        reply_to_run_id: run.reply_to_run_id,
        source_channel: run.source_channel,
        target_channel: run.target_channel,
        source_ref: run.source_ref,
        source_ref_text: run.source_ref_text,
        target_ref: run.target_ref,
        target_ref_text: run.target_ref_text,
        owner_ref: run.owner_ref,
        sender_agent_ref: run.sender_agent_ref,
        project_execution_context: run.project_execution_context,
        mention_targets: run.mention_targets,
        communication_view: run.communication_view,
        callback_to: run.callback_to,
        callback_to_text: run.callback_to_text,
        relation_hints: relationHints,
      };
    });
  }

  function buildLinks(events, agentRows) {
    const byRunId = new Map();
    const bySessionId = new Map((agentRows || []).map((agent) => [safeText(agent && agent.session_id), agent]));
    const links = [];
    const seen = new Set();
    events.forEach((event) => {
      byRunId.set(event.run_id, event);
    });
    function push(fromId, toId, type, reason) {
      if (!fromId || !toId || fromId === toId) return;
      const key = `${fromId}|${toId}|${reason}`;
      if (seen.has(key)) return;
      seen.add(key);
      links.push({ from: fromId, to: toId, type, reason });
    }
    function isKnownSessionId(sessionId) {
      return !!bySessionId.get(safeText(sessionId));
    }
    function uniqueSessionIds(values, exclude) {
      const blocked = safeText(exclude);
      const output = [];
      const seenIds = new Set();
      (values || []).forEach((value) => {
        const normalized = safeText(value);
        if (!normalized || normalized === blocked || seenIds.has(normalized) || !isKnownSessionId(normalized)) return;
        seenIds.add(normalized);
        output.push(normalized);
      });
      return output;
    }
    function counterpartSessionId(currentSessionId, a, b) {
      const current = safeText(currentSessionId);
      const first = safeText(a);
      const second = safeText(b);
      if (current) {
        if (first && first === current && second && second !== current) return second;
        if (second && second === current && first && first !== current) return first;
      }
      return first || second || "";
    }
    function pickAnchoredEvent(sessionId, eventTs, prefer) {
      return nearestEventForSession(events, sessionId, eventTs, prefer)
        || nearestEventForSession(events, sessionId, eventTs, prefer === "before" ? "after" : "before");
    }
    events.forEach((event) => {
      const eventTs = dateMs(event.created_at);
      if (event.reply_to_run_id) {
        const target = byRunId.get(event.reply_to_run_id);
        if (target) push(target.event_id, event.event_id, "reply", "reply_to_run_id");
      }
      const callbackSessionId = firstText([event.callback_to && event.callback_to.session_id, event.callback_to && event.callback_to.sessionId]);
      if (callbackSessionId) {
        const target = nearestEventForSession(events, callbackSessionId, eventTs, "before");
        if (target) push(event.event_id, target.event_id, "reply", "callback_to_session");
      }
      const communicationView = event.communication_view || null;
      const communicationPeerSessionId = counterpartSessionId(
        event.session_id,
        communicationView && communicationView.target_session_id,
        communicationView && communicationView.source_session_id
      );
      const resolvedSourceSessionId = uniqueSessionIds([
        event.source_ref && event.source_ref.session_id,
        communicationPeerSessionId,
        event.callback_to && event.callback_to.session_id,
        event.sender_agent_ref && event.sender_agent_ref.session_id,
        ...(((event.relation_hints && event.relation_hints.sourceSessionIds) || [])),
        resolveUniqueAgentSessionId(event.sender_name, agentRows),
      ], event.session_id)[0] || "";
      const sourceReason = (event.source_ref && event.source_ref.session_id && resolvedSourceSessionId === event.source_ref.session_id)
        ? "source_ref"
        : (communicationPeerSessionId && resolvedSourceSessionId === communicationPeerSessionId)
          ? "communication_view_peer"
          : ((event.callback_to && event.callback_to.session_id && resolvedSourceSessionId === event.callback_to.session_id)
            ? "callback_to"
            : ((event.sender_agent_ref && event.sender_agent_ref.session_id && resolvedSourceSessionId === event.sender_agent_ref.session_id)
              ? "sender_agent_ref"
              : (((event.relation_hints && event.relation_hints.sourceSessionIds) || []).includes(resolvedSourceSessionId) ? "explicit_source" : "sender_name")));
      if (resolvedSourceSessionId && resolvedSourceSessionId !== event.session_id) {
        const sourceEvent = pickAnchoredEvent(resolvedSourceSessionId, eventTs, "before");
        if (sourceEvent) push(sourceEvent.event_id, event.event_id, "dispatch", `${sourceReason}:${resolvedSourceSessionId}`);
      }
      const explicitTargetSessionIds = uniqueSessionIds([
        event.target_ref && event.target_ref.session_id,
        event.owner_ref && event.owner_ref.session_id,
        ...(((event.relation_hints && event.relation_hints.targetSessionIds) || [])),
        ...((event.mention_targets || []).map((item) => item && item.session_id)),
        ...resolveTargetSessionIds(event.relation_hints || {}, agentRows),
      ], "");
      const hintedSessionIds = explicitTargetSessionIds.filter((sessionId) => sessionId !== event.session_id);
      hintedSessionIds.forEach((sessionId) => {
        const hintedTarget = pickAnchoredEvent(sessionId, eventTs, "after");
        if (!hintedTarget) return;
        push(event.event_id, hintedTarget.event_id, "dispatch", `hinted_target:${sessionId}`);
      });
      if (!explicitTargetSessionIds.length) {
        const targetChannel = firstText([event.target_channel, ...(((event.relation_hints && event.relation_hints.targetChannels) || []))]);
        const uniqueTargetSessionId = resolveUniqueChannelSessionId(targetChannel, agentRows);
        if (uniqueTargetSessionId && uniqueTargetSessionId !== event.session_id) {
          const uniqueTarget = pickAnchoredEvent(uniqueTargetSessionId, eventTs, "after");
          if (uniqueTarget) push(event.event_id, uniqueTarget.event_id, "dispatch", `target_channel_unique:${uniqueTargetSessionId}`);
        }
      }
      const systemSourceSessionId = uniqueSessionIds([
        communicationView && communicationView.source_session_id,
        communicationView && communicationView.route_resolution && communicationView.route_resolution.source_ref && communicationView.route_resolution.source_ref.session_id,
      ], "")[0] || "";
      const systemTargetSessionId = uniqueSessionIds([
        communicationView && communicationView.target_session_id,
        communicationView && communicationView.route_resolution && communicationView.route_resolution.final_target && communicationView.route_resolution.final_target.session_id,
      ], "")[0] || "";
      if (
        safeText(communicationView && communicationView.message_kind) === "system_callback"
        && systemSourceSessionId
        && systemTargetSessionId
        && systemSourceSessionId !== systemTargetSessionId
      ) {
        const sourceEvent = pickAnchoredEvent(systemSourceSessionId, eventTs, "before");
        const targetEvent = pickAnchoredEvent(systemTargetSessionId, eventTs, "after");
        if (event.session_id === systemSourceSessionId && targetEvent) {
          push(event.event_id, targetEvent.event_id, "system", `system_callback_target:${systemTargetSessionId}`);
        } else if (event.session_id === systemTargetSessionId && sourceEvent) {
          push(sourceEvent.event_id, event.event_id, "system", `system_callback_source:${systemSourceSessionId}`);
        } else if (sourceEvent && targetEvent) {
          push(sourceEvent.event_id, targetEvent.event_id, "system", `system_callback_pair:${systemSourceSessionId}->${systemTargetSessionId}`);
        }
      }
    });
    return links;
  }

  function setStatus(text, tone = "loading") {
    if (!dom.stateBanner) return;
    dom.stateBanner.textContent = String(text || "");
    dom.stateBanner.className = `state-banner is-${tone}`;
    dom.stateBanner.hidden = !text;
  }

  function syncWindowControls() {
    const showCustomRange = STATE.windowKey === "custom";
    Array.from(dom.windowTabs?.querySelectorAll("[data-window]") || []).forEach((node) => {
      node.classList.toggle("is-active", String(node.getAttribute("data-window") || "") === STATE.windowKey);
    });
    if (dom.customRangeBar) {
      dom.customRangeBar.hidden = !showCustomRange;
      dom.customRangeBar.setAttribute("aria-hidden", showCustomRange ? "false" : "true");
    }
    syncCustomInputs();
  }

  function syncOrderControls() {
    Array.from(dom.orderTabs?.querySelectorAll("[data-order]") || []).forEach((node) => {
      node.classList.toggle("is-active", String(node.getAttribute("data-order") || "") === STATE.agentOrderMode);
    });
  }

  function syncTimeScaleControls() {
    if (dom.timeScaleSlider) dom.timeScaleSlider.value = String(clampTimelineStretch(STATE.timelineStretch));
    if (dom.timeScaleLabel) dom.timeScaleLabel.textContent = formatTimelineStretch(STATE.timelineStretch);
  }

  function syncLegendControls() {
    Array.from(dom.toolbarLegend?.querySelectorAll("[data-link-type]") || []).forEach((node) => {
      const type = safeText(node.getAttribute("data-link-type")).toLowerCase();
      const active = isLinkTypeVisible(type);
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function renderHeader() {
    const health = STATE.health || {};
    if (dom.overviewLink) dom.overviewLink.href = String(LINKS.overview_page || "/share/project-overview-dashboard.html");
    if (dom.taskLink) {
      const taskBase = String(LINKS.task_page || "/share/project-task-dashboard.html").trim();
      dom.taskLink.href = (STATE.mode === "project" && STATE.projectId) ? `${taskBase}#p=${encodeURIComponent(STATE.projectId)}` : taskBase;
    }
    if (dom.envBadge) dom.envBadge.textContent = safeText(health.environment || DATA.environment, "stable");
    if (dom.projectMeta) {
      const parts = STATE.mode === "global"
        ? [
          "全项目拉通回放",
          `项目 ${STATE.projectCatalog.length || 0}`,
          "按项目 / session_id 分列",
          `窗口 ${STATE.activeRange.isCustom ? STATE.activeRange.label : STATE.windowKey}`,
          `排序 ${STATE.agentOrderMode === "volume" ? "消息量" : "默认"}`,
          `时间尺 ${formatTimelineStretch(STATE.timelineStretch)}`,
          `${Math.round(STATE.zoom * 100)}%`,
        ]
        : [
          STATE.projectId || "未指定项目",
          STATE.channelHint ? `通道 ${STATE.channelHint}` : "单项目只读回放",
          STATE.sessionHint ? `会话 ${shortId(STATE.sessionHint)}` : "按 session_id 分列",
          `窗口 ${STATE.activeRange.isCustom ? STATE.activeRange.label : STATE.windowKey}`,
          `排序 ${STATE.agentOrderMode === "volume" ? "消息量" : "默认"}`,
          `时间尺 ${formatTimelineStretch(STATE.timelineStretch)}`,
          `${Math.round(STATE.zoom * 100)}%`,
        ];
      dom.projectMeta.textContent = parts.join(" · ");
    }
    if (dom.summaryMeta) {
      dom.summaryMeta.textContent = `Agent ${STATE.agentRows.length || 0} · 事件 ${STATE.events.length || 0} · 关系 ${visibleLinks().length}`;
    }
    if (dom.zoomResetBtn) dom.zoomResetBtn.textContent = `${Math.round(STATE.zoom * 100)}%`;
    syncWindowControls();
    syncOrderControls();
    syncTimeScaleControls();
    syncLegendControls();
  }

  function buildTimeSlots(minTs, maxTs, timelineHeight) {
    const slots = [];
    const span = Math.max(1, maxTs - minTs);
    const slotMs = STATE.windowKey === "custom"
      ? slotMsForRange(span)
      : (WINDOW_SLOT_MS[STATE.windowKey] || Math.max(1, Math.round(span / 6)));
    const topInset = timelineTopOffset();
    const contentHeight = Math.max(260, timelineHeight - topInset - 100);
    const alignedStart = Math.floor(minTs / slotMs) * slotMs;
    for (let ts = alignedStart; ts <= maxTs + slotMs; ts += slotMs) {
      if (ts < minTs || ts > maxTs) continue;
      const ratio = (ts - minTs) / span;
      slots.push({
        y: topInset + Math.round(ratio * contentHeight),
        label: fmtTimelineTick(ts, span),
      });
    }
    if (!slots.length || slots[0].label !== fmtTimelineTick(minTs, span)) {
      slots.unshift({ y: topInset, label: fmtTimelineTick(minTs, span) });
    }
    const last = slots[slots.length - 1];
    if (!last || last.label !== fmtTimelineTick(maxTs, span)) {
      slots.push({ y: topInset + contentHeight, label: fmtTimelineTick(maxTs, span) });
    }
    return slots;
  }

  function renderTimeSlots(slots, height) {
    dom.timeCol.innerHTML = "";
    dom.timeCol.style.height = `${height}px`;
    slots.forEach((slot) => {
      const row = el("div", { class: "time-slot" });
      row.style.top = `${slot.y}px`;
      row.appendChild(el("span", { class: "time-slot-label", text: slot.label }));
      dom.timeCol.appendChild(row);
    });
  }

  function statusLabel(value) {
    const status = safeText(value).toLowerCase();
    if (!status) return "空闲";
    if (status.includes("running")) return "运行中";
    if (status.includes("queued")) return "排队中";
    if (status.includes("retry")) return "等待重试";
    if (status.includes("done")) return "已完成";
    if (status.includes("error")) return "异常";
    if (status.includes("external")) return "外部占用";
    return status;
  }

  function renderAgents(agentRows, height) {
    dom.agentsLayer.innerHTML = "";
    if (dom.agentHeadsLayer) dom.agentHeadsLayer.innerHTML = "";
    dom.agentsLayer.style.height = `${height}px`;
    if (dom.agentHeadsLayer) dom.agentHeadsLayer.style.height = `${height}px`;
    agentRows.forEach((agent, index) => {
      const col = el("div", { class: `agent-col${agent.session_id === STATE.sessionHint ? " is-active" : ""}` });
      const accent = projectAccent(agent.project_id);
      col.style.left = `${index * AGENT_WIDTH}px`;
      col.style.setProperty("--agent-region-soft", rgbaFromColor(accent, 0.075));
      col.style.setProperty("--agent-region-fade", rgbaFromColor(accent, 0.034));
      col.style.setProperty("--agent-region-border", rgbaFromColor(accent, 0.16));
      const head = el("div", { class: "agent-head" });
      const meta = avatarMeta(agent);
      const avatar = el("div", { class: `avatar${meta.fallback ? " is-fallback" : ""}`, text: meta.text, title: meta.title });
      avatar.style.setProperty("--avatar-c1", meta.c1);
      avatar.style.setProperty("--avatar-c2", meta.c2);
      const top = el("div", { class: "agent-top" }, [
        avatar,
        el("div", {}, [
          el("div", { class: "agent-name", text: sessionDisplayName(agent) }),
          el("div", { class: "agent-meta", text: `${agent.channel_name || shortId(agent.session_id)} · ${safeText(agent.cli_type, "codex")} · ${Number(agent.event_count) || 0} 条消息` }),
        ]),
      ]);
      head.appendChild(top);
      head.appendChild(el("span", { class: "pill", text: statusLabel(agent.status) }));
      head.style.left = `${index * AGENT_WIDTH}px`;
      if (dom.agentHeadsLayer) dom.agentHeadsLayer.appendChild(head);
      else col.appendChild(head);
      dom.agentsLayer.appendChild(col);
    });
  }

  function renderProjects(agentRows) {
    if (!dom.projectsLayer || !dom.regionsLayer) return;
    dom.projectsLayer.innerHTML = "";
    dom.regionsLayer.innerHTML = "";
    if (STATE.mode !== "global") return;
    let cursor = 0;
    let current = null;
    const groups = [];
    agentRows.forEach((agent) => {
      const projectId = safeText(agent.project_id);
      const projectName = firstText([agent.project_name, projectNameById(projectId), projectId], "未归类项目");
      if (!current || current.project_id !== projectId) {
        current = { project_id: projectId, project_name: projectName, start: cursor, count: 0 };
        groups.push(current);
      }
      current.count += 1;
      cursor += 1;
    });
    groups.forEach((group, index) => {
      const accent = projectAccent(group.project_id);
      const region = el("div", { class: "project-region", title: `${group.project_name} 区域` });
      region.style.left = `${group.start * AGENT_WIDTH}px`;
      region.style.width = `${Math.max(AGENT_WIDTH, group.count * AGENT_WIDTH)}px`;
      region.style.setProperty("--project-accent-soft", rgbaFromColor(accent, index % 2 === 0 ? 0.24 : 0.19));
      region.style.setProperty("--project-accent-fade", rgbaFromColor(accent, index % 2 === 0 ? 0.11 : 0.085));
      region.style.setProperty("--project-accent-line", rgbaFromColor(accent, 0.28));
      region.style.setProperty("--project-accent-grid", rgbaFromColor(accent, index % 2 === 0 ? 0.06 : 0.04));
      dom.regionsLayer.appendChild(region);

      const band = el("div", { class: "project-band", title: `${group.project_name} · Agent ${group.count}` }, [
        el("div", { class: "project-band-main" }, [
          el("div", { class: "project-band-name", text: group.project_name }),
          el("div", { class: "project-band-meta", text: `${group.project_id || "unknown"} · Agent ${group.count}` }),
        ]),
        el("div", { class: "project-band-pulse", text: `${group.count}` }),
      ]);
      band.style.left = `${group.start * AGENT_WIDTH}px`;
      band.style.width = `${Math.max(AGENT_WIDTH, group.count * AGENT_WIDTH)}px`;
      band.style.setProperty("--project-accent-soft", rgbaFromColor(accent, 0.2));
      band.style.setProperty("--project-accent-line", rgbaFromColor(accent, 0.36));
      dom.projectsLayer.appendChild(band);
    });
  }

  function updateFrozenAxes() {
    if (!dom.curtainViewport || !dom.curtain) return;
    const scale = Math.max(0.01, STATE.zoom || 1);
    const offsetX = dom.curtainViewport.scrollLeft / scale;
    const offsetY = dom.curtainViewport.scrollTop / scale;
    if (dom.timeCol) {
      dom.timeCol.style.transform = `translate3d(${offsetX}px, 0, 0)`;
    }
    if (dom.timeCorner) {
      dom.timeCorner.style.transform = `translate3d(${offsetX}px, ${offsetY}px, 0)`;
    }
    if (dom.projectsLayer) {
      dom.projectsLayer.style.transform = `translate3d(0, ${offsetY}px, 0)`;
    }
    if (dom.agentHeadsLayer) dom.agentHeadsLayer.style.transform = `translate3d(0, ${offsetY}px, 0)`;
  }

  function scheduleViewportSync() {
    if (viewportSyncFrame) return;
    viewportSyncFrame = window.requestAnimationFrame(() => {
      viewportSyncFrame = 0;
      updateMiniViewport();
      updateFrozenAxes();
    });
  }

  function layoutEvents(agentRows, events, minTs, maxTs, height) {
    const indexBySession = new Map(agentRows.map((agent, index) => [agent.session_id, index]));
    const span = Math.max(1, maxTs - minTs);
    const lastYBySession = new Map();
    return events.map((event, idx) => {
      const agentIndex = indexBySession.has(event.session_id) ? indexBySession.get(event.session_id) : 0;
      const eventTs = dateMs(event.created_at);
      const ratio = (eventTs - minTs) / span;
      const topInset = timelineTopOffset() + 6;
      let top = topInset + Math.round(ratio * Math.max(260, height - topInset - 94));
      const lastY = lastYBySession.get(event.session_id) || 0;
      if (top - lastY < 88) top = lastY + 88;
      lastYBySession.set(event.session_id, top);
      const lane = idx % 2;
      return {
        ...event,
        left: (agentIndex * AGENT_WIDTH) + 18 + (lane * 12),
        top,
      };
    });
  }

  function renderEvents(layoutRows) {
    dom.eventsLayer.innerHTML = "";
    dom.eventsLayer.style.height = `${STATE.canvasHeight}px`;
    layoutRows.forEach((event) => {
      const meta = EVENT_TYPES[event.type] || EVENT_TYPES.reply;
      const card = el("button", {
        class: `event-card ${meta.tone}${STATE.selectedEventId === event.event_id ? " is-active" : ""}`,
        type: "button",
        title: [
          event.title,
          `时间：${fmtDate(event.created_at)}`,
          `发送者：${displaySenderLabel(event)}`,
          event.message_kind ? `消息类型：${messageKindLabel(event.message_kind)} (${event.message_kind})` : "",
          event.interaction_mode ? `交互模式：${interactionModeLabel(event.interaction_mode) || event.interaction_mode}` : "",
          event.source_ref_text ? `source_ref：${event.source_ref_text}` : "",
          event.callback_to_text ? `callback_to：${event.callback_to_text}` : "",
          event.detail,
        ].filter(Boolean).join("\n"),
      }, [
        el("div", { class: "event-type", text: meta.label }),
        el("div", { class: "event-title", text: event.title }),
        el("div", { class: "event-meta", text: event.meta }),
      ]);
      card.style.left = `${event.left}px`;
      card.style.top = `${event.top}px`;
      card.addEventListener("click", () => {
        STATE.selectedEventId = event.event_id;
        setStatus(`${event.title} · ${fmtDate(event.created_at)} · ${displaySenderLabel(event)} · ${messageKindLabel(event.message_kind)}`, "ready");
        renderEvents(STATE.layoutEvents);
      });
      dom.eventsLayer.appendChild(card);
    });
  }

  function curvePath(startX, startY, endX, endY, laneOffset = 0) {
    const deltaX = Math.max(120, endX - startX);
    const exitX = startX + Math.min(54, deltaX * 0.22);
    const enterX = endX - Math.min(54, deltaX * 0.22);
    const midX = startX + deltaX * 0.52;
    const midY = startY + ((endY - startY) * 0.48) + laneOffset;
    return [
      `M ${startX} ${startY}`,
      `C ${exitX} ${startY}, ${midX - 36} ${midY}, ${midX} ${midY}`,
      `S ${enterX} ${endY}, ${endX} ${endY}`,
    ].join(" ");
  }

  function renderLinks(layoutRows) {
    dom.linksSvg.innerHTML = "";
    dom.linksSvg.setAttribute("viewBox", `0 0 ${Math.max(1, STATE.canvasWidth - TIME_WIDTH)} ${STATE.canvasHeight}`);
    dom.linksSvg.style.width = `${Math.max(1, STATE.canvasWidth - TIME_WIDTH)}px`;
    dom.linksSvg.style.height = `${STATE.canvasHeight}px`;
    if (!STATE.showLinks) return;
    const byId = new Map(layoutRows.map((event) => [event.event_id, event]));
    visibleLinks().forEach((link, index) => {
      const from = byId.get(link.from);
      const to = byId.get(link.to);
      if (!from || !to) return;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("class", link.type || "reply");
      path.setAttribute("d", curvePath(from.left + EVENT_WIDTH, from.top + 44, to.left, to.top + 44, ((index % 5) - 2) * 14));
      dom.linksSvg.appendChild(path);
    });
  }

  function updateCanvasSize(width, height) {
    STATE.canvasWidth = Math.max(TIME_WIDTH + AGENT_WIDTH, width);
    STATE.canvasHeight = Math.max(BASE_HEIGHT_MIN, height);
    const zoomedWidth = Math.round(STATE.canvasWidth * STATE.zoom);
    const zoomedHeight = Math.round(STATE.canvasHeight * STATE.zoom);
    dom.curtain.style.width = `${STATE.canvasWidth}px`;
    dom.curtain.style.height = `${STATE.canvasHeight}px`;
    dom.curtain.style.transform = `scale(${STATE.zoom})`;
    dom.curtainSizer.style.width = `${zoomedWidth}px`;
    dom.curtainSizer.style.height = `${zoomedHeight}px`;
    updateFrozenAxes();
  }

  function renderMiniMap() {
    if (!dom.miniMap || !dom.miniViewport) return;
    dom.miniMap.querySelectorAll(".mini-map-agent, .mini-map-event").forEach((node) => node.remove());
    const miniRect = dom.miniMap.getBoundingClientRect();
    const miniW = miniRect.width || 190;
    const miniH = miniRect.height || 116;
    const width = Math.max(1, STATE.canvasWidth);
    const height = Math.max(1, STATE.canvasHeight);
    const scaleX = miniW / width;
    const scaleY = miniH / height;

    STATE.agentRows.forEach((agent, index) => {
      const marker = el("div", { class: "mini-map-agent" });
      marker.style.left = `${TIME_WIDTH * scaleX + index * AGENT_WIDTH * scaleX + 6}px`;
      marker.style.top = `${Math.max(8, (headerStackHeight() * scaleY) * 0.4)}px`;
      dom.miniMap.appendChild(marker);
    });
    STATE.layoutEvents.forEach((event) => {
      const marker = el("div", { class: `mini-map-event ${event.type}` });
      marker.style.left = `${(TIME_WIDTH + event.left) * scaleX}px`;
      marker.style.top = `${event.top * scaleY}px`;
      dom.miniMap.appendChild(marker);
    });
    updateMiniViewport();
  }

  function updateMiniViewport() {
    if (!dom.curtainViewport || !dom.miniMap || !dom.miniViewport) return;
    const totalW = dom.curtainSizer.offsetWidth || 1;
    const totalH = dom.curtainSizer.offsetHeight || 1;
    const miniRect = dom.miniMap.getBoundingClientRect();
    const miniW = miniRect.width || 190;
    const miniH = miniRect.height || 116;
    const left = (dom.curtainViewport.scrollLeft / totalW) * miniW;
    const top = (dom.curtainViewport.scrollTop / totalH) * miniH;
    const width = Math.min(miniW, Math.max(18, (dom.curtainViewport.clientWidth / totalW) * miniW));
    const height = Math.min(miniH, Math.max(18, (dom.curtainViewport.clientHeight / totalH) * miniH));
    dom.miniViewport.style.left = `${Math.max(0, Math.min(miniW - width, left))}px`;
    dom.miniViewport.style.top = `${Math.max(0, Math.min(miniH - height, top))}px`;
    dom.miniViewport.style.width = `${width}px`;
    dom.miniViewport.style.height = `${height}px`;
  }

  function applyZoom(nextZoom, opts = {}) {
    const prevZoom = STATE.zoom;
    STATE.zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Number(nextZoom) || 1));
    const view = dom.curtainViewport;
    if (!view) return;
    const centerX = view.scrollLeft + (view.clientWidth / 2);
    const centerY = view.scrollTop + (view.clientHeight / 2);
    const ratio = STATE.zoom / prevZoom;
    updateCanvasSize(STATE.canvasWidth, STATE.canvasHeight);
    renderHeader();
    if (!opts.skipRecenter) {
      view.scrollLeft = Math.max(0, centerX * ratio - (view.clientWidth / 2));
      view.scrollTop = Math.max(0, centerY * ratio - (view.clientHeight / 2));
    }
    updateMiniViewport();
  }

  function applyTimelineStretch(nextStretch, opts = {}) {
    const view = dom.curtainViewport;
    const prevTotalHeight = dom.curtainSizer?.offsetHeight || Math.round(STATE.canvasHeight * STATE.zoom) || 1;
    const anchorRatio = view
      ? (view.scrollTop + (view.clientHeight / 2)) / Math.max(1, prevTotalHeight)
      : 0;
    STATE.timelineStretch = clampTimelineStretch(nextStretch);
    persistTimelineStretch();
    render();
    if (view && !opts.skipRecenter) {
      const nextTotalHeight = dom.curtainSizer?.offsetHeight || Math.round(STATE.canvasHeight * STATE.zoom) || 1;
      view.scrollTop = Math.max(0, Math.round(anchorRatio * nextTotalHeight - (view.clientHeight / 2)));
      updateMiniViewport();
      updateFrozenAxes();
    }
  }

  function render() {
    renderHeader();
    const events = STATE.events.slice();
    if (dom.curtain) {
      dom.curtain.style.setProperty("--project-h", `${STATE.mode === "global" ? PROJECT_HEADER_HEIGHT : 0}px`);
      dom.curtain.dataset.mode = STATE.mode;
    }
    if (STATE.mode !== "global" && !STATE.projectId) {
      dom.stageWrap.hidden = true;
      setStatus("缺少 project_id。请从项目页入口进入，或在 URL 中带上 project_id。", "error");
      return;
    }
    const activeRange = STATE.activeRange || resolveTimeRange([]);
    const hasEvents = events.length > 0;
    const maxTs = Number(activeRange.endMs) || Date.now();
    const minTs = Math.max(0, Number(activeRange.startMs) || (maxTs - WINDOW_MS["1h"]));
    const baseHeight = hasEvents ? Math.max(BASE_HEIGHT_MIN, 220 + (events.length * 86)) : BASE_HEIGHT_MIN;
    const contentHeight = Math.max(BASE_HEIGHT_MIN, Math.round(baseHeight * clampTimelineStretch(STATE.timelineStretch)));
    const canvasHeight = contentHeight + CANVAS_BOTTOM_GUTTER;
    const contentWidth = TIME_WIDTH + Math.max(1, STATE.agentRows.length) * AGENT_WIDTH;
    const canvasWidth = contentWidth + CANVAS_RIGHT_GUTTER;
    updateCanvasSize(canvasWidth, canvasHeight);
    renderTimeSlots(buildTimeSlots(minTs, maxTs, contentHeight), canvasHeight);
    renderProjects(STATE.agentRows);
    renderAgents(STATE.agentRows, canvasHeight);
    STATE.layoutEvents = hasEvents ? layoutEvents(STATE.agentRows, events, minTs, maxTs, contentHeight) : [];
    renderEvents(STATE.layoutEvents);
    renderLinks(STATE.layoutEvents);
    if (!hasEvents) {
      dom.eventsLayer.innerHTML = `<div class="empty-block">当前窗口暂无可展示的 Agent 对话事件。</div>`;
      setStatus(STATE.mode === "global" ? "当前窗口暂无可展示的全项目消息，保持只读空态。" : "当前窗口暂无可展示的消息，保持只读空态。", "empty");
    } else {
      const prefix = STATE.mode === "global" ? `已加载 ${STATE.projectCatalog.length || 0} 个项目` : `已加载项目 ${STATE.projectId}`;
      setStatus(`${prefix} · ${STATE.agentRows.length} 个 Agent · ${events.length} 条事件 · ${visibleLinks().length} 条关系线。`, "ready");
    }
    dom.stageWrap.hidden = false;
    renderMiniMap();
    updateFrozenAxes();
  }

  function mergeAvatarStores(stores) {
    const merged = emptyAvatarStore();
    (stores || []).forEach((store) => {
      const normalized = normalizeAvatarStore(store);
      Object.assign(merged.bySessionId, normalized.bySessionId || {});
      Object.assign(merged.clearedSessionIds, normalized.clearedSessionIds || {});
    });
    return merged;
  }

  function currentRunLimit() {
    return 200;
  }

  function buildRunsApiUrl(projectId) {
    const params = new URLSearchParams();
    params.set("projectId", safeText(projectId));
    params.set("limit", String(currentRunLimit()));
    params.set("payloadMode", "light");
    if (STATE.windowKey === "custom") {
      const startMs = Number(STATE.customRange.startMs) || 0;
      const endMs = Number(STATE.customRange.endMs) || 0;
      if (startMs > 0) params.set("afterCreatedAt", formatIsoTime(startMs));
      if (endMs > startMs) params.set("beforeCreatedAt", formatIsoTime(endMs));
    }
    return `/api/codex/runs?${params.toString()}`;
  }

  async function loadProjectBundle(project) {
    const projectId = safeText(project && (project.project_id || project.id));
    const projectName = firstText([project && (project.project_name || project.name), projectId], projectId);
    if (!projectId) return { projectId: "", projectName: "", sessions: [], runs: [], sharedAvatarStore: emptyAvatarStore(), error: null };
    try {
      const [sessionsPayload, runsPayload, sharedAvatarStore] = await Promise.all([
        fetchJson(`/api/sessions?project_id=${encodeURIComponent(projectId)}`),
        fetchJson(buildRunsApiUrl(projectId)),
        fetchSharedAvatarStore(projectId),
      ]);
      const sessions = (Array.isArray(sessionsPayload.sessions) ? sessionsPayload.sessions : [])
        .map((item) => normalizeSession({ ...item, project_id: projectId, project_name: projectName }))
        .filter(Boolean);
      const runs = (Array.isArray(runsPayload.runs) ? runsPayload.runs : [])
        .map((item) => normalizeRun({ ...item, project_id: projectId, project_name: projectName }))
        .filter(Boolean);
      return { projectId, projectName, sessions, runs, sharedAvatarStore, error: null };
    } catch (error) {
      return { projectId, projectName, sessions: [], runs: [], sharedAvatarStore: emptyAvatarStore(), error };
    }
  }

  async function loadProjectModeData() {
    const [sessionsPayload, runsPayload, sharedAvatarStore] = await Promise.all([
      fetchJson(`/api/sessions?project_id=${encodeURIComponent(STATE.projectId)}`),
      fetchJson(buildRunsApiUrl(STATE.projectId)),
      fetchSharedAvatarStore(STATE.projectId),
    ]);
    STATE.sharedAvatarStore = sharedAvatarStore;
    STATE.sessions = (Array.isArray(sessionsPayload.sessions) ? sessionsPayload.sessions : [])
      .map((item) => normalizeSession({ ...item, project_id: STATE.projectId, project_name: projectNameById(STATE.projectId) }))
      .filter(Boolean);
    STATE.sessionMap = new Map(STATE.sessions.map((item) => [item.session_id, item]));
    const normalizedRuns = (Array.isArray(runsPayload.runs) ? runsPayload.runs : [])
      .map((item) => normalizeRun({ ...item, project_id: STATE.projectId, project_name: projectNameById(STATE.projectId) }))
      .filter(Boolean);
    const visibleRuns = filterRunsByVisibleSessions(normalizedRuns, STATE.sessions);
    STATE.activeRange = resolveTimeRange(visibleRuns);
    const filteredRuns = filterRunsByWindow(visibleRuns, STATE.activeRange);
    STATE.events = buildEventRows(filteredRuns);
    refreshAgentLayoutState();
  }

  async function loadGlobalModeData() {
    const projects = STATE.projectCatalog.slice();
    const bundles = await Promise.all(projects.map((project) => loadProjectBundle(project)));
    const successful = bundles.filter((item) => !item.error);
    const partialErrors = bundles.filter((item) => item.error);
    STATE.sharedAvatarStore = mergeAvatarStores(successful.map((item) => item.sharedAvatarStore));
    STATE.sessions = successful.flatMap((item) => item.sessions);
    STATE.sessionMap = new Map(STATE.sessions.map((item) => [item.session_id, item]));
    const normalizedRuns = successful.flatMap((item) => item.runs);
    const visibleRuns = filterRunsByVisibleSessions(normalizedRuns, STATE.sessions);
    STATE.activeRange = resolveTimeRange(visibleRuns);
    const filteredRuns = filterRunsByWindow(visibleRuns, STATE.activeRange);
    STATE.events = buildEventRows(filteredRuns);
    refreshAgentLayoutState();
    return { partialErrors };
  }

  async function loadData() {
    setStatus(STATE.mode === "global" ? "正在聚合全部项目的会话与运行消息..." : "正在读取项目会话与运行消息...", "loading");
    try {
      let partialErrors = [];
      if (STATE.mode === "global") {
        const result = await loadGlobalModeData();
        partialErrors = result.partialErrors || [];
      } else {
        await loadProjectModeData();
      }
      render();
      if (partialErrors.length) {
        setStatus(`已加载全项目视图，但有 ${partialErrors.length} 个项目读取失败。其余项目已正常展示。`, "ready");
      }
    } catch (error) {
      console.error("agent curtain load error:", error);
      STATE.sessions = [];
      STATE.agentRows = [];
      STATE.events = [];
      STATE.links = [];
      STATE.layoutEvents = [];
      dom.stageWrap.hidden = true;
      setStatus(`消息瀑布加载失败：${String((error && error.message) || error || "unknown")}`, "error");
    }
  }

  function bindEvents() {
    dom.refreshBtn?.addEventListener("click", () => loadData());
    dom.orderTabs?.addEventListener("click", (event) => {
      const btn = event.target && event.target.closest ? event.target.closest("[data-order]") : null;
      if (!btn) return;
      const next = safeText(btn.getAttribute("data-order")).toLowerCase();
      if (!next || next === STATE.agentOrderMode) return;
      if (!["default", "volume"].includes(next)) return;
      STATE.agentOrderMode = next;
      refreshAgentLayoutState();
      render();
    });
    dom.toolbarLegend?.addEventListener("click", (event) => {
      const btn = event.target && event.target.closest ? event.target.closest("[data-link-type]") : null;
      if (!btn) return;
      const type = safeText(btn.getAttribute("data-link-type")).toLowerCase();
      if (!type || !(type in STATE.linkTypeVisibility)) return;
      STATE.linkTypeVisibility[type] = !isLinkTypeVisible(type);
      render();
    });
    dom.windowTabs?.addEventListener("click", (event) => {
      const btn = event.target && event.target.closest ? event.target.closest("[data-window]") : null;
      if (!btn) return;
      const next = String(btn.getAttribute("data-window") || "").trim();
      if (!(WINDOW_MS[next] || next === "custom") || next === STATE.windowKey) return;
      STATE.windowKey = next;
      if (next === "custom") ensureCustomRange(STATE.activeRange.endMs || Date.now());
      syncWindowControls();
      loadData();
    });
    function applyCustomRange() {
      const startMs = parseDateTimeInput(dom.customStartInput && dom.customStartInput.value);
      const endMs = parseDateTimeInput(dom.customEndInput && dom.customEndInput.value);
      if (!startMs || !endMs || endMs <= startMs) {
        setStatus("自定义时间范围无效，请重新输入开始和结束时间。", "error");
        return;
      }
      STATE.customRange.startMs = startMs;
      STATE.customRange.endMs = endMs;
      STATE.windowKey = "custom";
      syncWindowControls();
      loadData();
    }
    dom.customApplyBtn?.addEventListener("click", applyCustomRange);
    dom.customResetBtn?.addEventListener("click", () => {
      STATE.windowKey = "1h";
      syncWindowControls();
      loadData();
    });
    dom.customStartInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") applyCustomRange();
    });
    dom.customEndInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") applyCustomRange();
    });
    dom.toggleLinks?.addEventListener("change", () => {
      STATE.showLinks = !!dom.toggleLinks.checked;
      render();
    });
    dom.toggleSystem?.addEventListener("change", () => {
      STATE.showSystem = !!dom.toggleSystem.checked;
      loadData();
    });
    dom.toggleDone?.addEventListener("change", () => {
      STATE.showDone = !!dom.toggleDone.checked;
      loadData();
    });
    dom.zoomInBtn?.addEventListener("click", () => applyZoom(STATE.zoom + ZOOM_STEP));
    dom.zoomOutBtn?.addEventListener("click", () => applyZoom(STATE.zoom - ZOOM_STEP));
    dom.zoomResetBtn?.addEventListener("click", () => applyZoom(1));
    dom.timeScaleSlider?.addEventListener("input", (event) => {
      applyTimelineStretch(event && event.target ? event.target.value : MIN_TIMELINE_STRETCH);
    });
    dom.timeScaleShrinkBtn?.addEventListener("click", () => applyTimelineStretch(STATE.timelineStretch - TIMELINE_STRETCH_STEP));
    dom.timeScaleExpandBtn?.addEventListener("click", () => applyTimelineStretch(STATE.timelineStretch + TIMELINE_STRETCH_STEP));
    dom.curtainViewport?.addEventListener("scroll", () => {
      scheduleViewportSync();
    });
    dom.curtainViewport?.addEventListener("pointerdown", (event) => {
      if (!dom.curtainViewport) return;
      const target = event.target;
      if (target && target.closest && target.closest("button, a, input, label")) return;
      STATE.dragPan = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        scrollLeft: dom.curtainViewport.scrollLeft,
        scrollTop: dom.curtainViewport.scrollTop,
      };
      dom.curtainViewport.classList.add("is-dragging");
      if (dom.curtainViewport.setPointerCapture) dom.curtainViewport.setPointerCapture(event.pointerId);
    });
    dom.curtainViewport?.addEventListener("pointermove", (event) => {
      if (!dom.curtainViewport || !STATE.dragPan || STATE.dragPan.pointerId !== event.pointerId) return;
      const dx = event.clientX - STATE.dragPan.startX;
      const dy = event.clientY - STATE.dragPan.startY;
      dom.curtainViewport.scrollLeft = STATE.dragPan.scrollLeft - dx;
      dom.curtainViewport.scrollTop = STATE.dragPan.scrollTop - dy;
      updateMiniViewport();
    });
    function releaseDragPan(event) {
      if (!dom.curtainViewport || !STATE.dragPan) return;
      if (event && STATE.dragPan.pointerId !== event.pointerId) return;
      if (event && dom.curtainViewport.releasePointerCapture) {
        try { dom.curtainViewport.releasePointerCapture(event.pointerId); } catch (_) {}
      }
      STATE.dragPan = null;
      dom.curtainViewport.classList.remove("is-dragging");
    }
    dom.curtainViewport?.addEventListener("pointerup", releaseDragPan);
    dom.curtainViewport?.addEventListener("pointercancel", releaseDragPan);
    dom.curtainViewport?.addEventListener("pointerleave", (event) => {
      if (!STATE.dragPan) return;
      if ((event.buttons || 0) !== 1) releaseDragPan(event);
    });
    dom.miniMap?.addEventListener("click", (event) => {
      if (!dom.curtainViewport || !dom.miniMap) return;
      const rect = dom.miniMap.getBoundingClientRect();
      const ratioX = (event.clientX - rect.left) / Math.max(1, rect.width);
      const ratioY = (event.clientY - rect.top) / Math.max(1, rect.height);
      dom.curtainViewport.scrollLeft = Math.max(0, (ratioX * dom.curtainSizer.offsetWidth) - (dom.curtainViewport.clientWidth / 2));
      dom.curtainViewport.scrollTop = Math.max(0, (ratioY * dom.curtainSizer.offsetHeight) - (dom.curtainViewport.clientHeight / 2));
      updateMiniViewport();
      updateFrozenAxes();
    });
    window.addEventListener("resize", () => {
      updateMiniViewport();
      renderMiniMap();
      updateFrozenAxes();
    });
  }

  async function init() {
    const route = qs();
    STATE.mode = route.mode;
    STATE.projectId = route.projectId;
    STATE.channelHint = route.channelName;
    STATE.sessionHint = route.sessionId;
    STATE.timelineStretch = readTimelineStretch();
    STATE.projectCatalog = projectCatalog();
    STATE.activeRange = resolveTimeRange([]);
    STATE.health = await readHealth();
    renderHeader();
    bindEvents();
    await loadData();
  }

  init().catch((error) => {
    console.error("agent curtain init error:", error);
    setStatus(`消息瀑布初始化失败：${String((error && error.message) || error || "unknown")}`, "error");
  });
})();
