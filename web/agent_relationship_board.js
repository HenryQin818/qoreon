(() => {
  const DATA = JSON.parse(document.getElementById("data")?.textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const TOKEN_KEY = "taskDashboard.token";
  const AVATAR_V1_KEY = "taskDashboard.avatarAssignments.v1";
  const AVATAR_V2_KEY = "taskDashboard.avatarAssignments.v2";
  const STORAGE_PREFIX = "taskDashboard.agentRelationshipBoard.v2";
  const CARD_WIDTH = 228;
  const CARD_HEIGHT = 116;
  const GROUP_PADDING = 24;
  const PROJECT_LAYOUT_VERSION = "project-layout-v4";
  const STAGE_MIN = {
    project: { width: 5600, height: 3400 },
    platform: { width: 14800, height: 9200 },
  };
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
  const PLATFORM_HIGH_FREQ_COUNT = 5;
  const PLATFORM_RUNS_PAGE_LIMIT = 200;
  const PLATFORM_RUNS_MAX_PAGES = 12;
  const PLATFORM_PROJECT_LAYOUT_BASE_SCALE = 0.58;
  const PLATFORM_PROJECT_LAYOUT_MAX_WIDTH = 2600;
  const PLATFORM_PROJECT_LAYOUT_MAX_HEIGHT = 1720;
  const PLATFORM_PROJECT_LAYOUT_COMPACT_SCALE = 1;
  const AVATAR_CATALOG = [
    ["user", "用户", "🙋", "#fde7f3", "#f9c7dd"],
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
  const AVATAR_MAP = new Map(AVATAR_CATALOG.map((item) => [String(item.id), item]));
  const USER_NODE_ID = "user::global";
  const USER_NODE_LABEL = "用户";
  const STATE = {
    projectId: "",
    projectName: "",
    viewMode: "project",
    platformLayoutMode: "project",
    platformCommScope: "all",
    commLineCountMin: 0,
    commVisibility: {
      user: true,
      agent: true,
    },
    platformProjects: [],
    platformProjectFilterInitialized: false,
    platformProjectFilterSelected: [],
    platformProjectFilterDraft: [],
    platformProjectFilterDraftDirty: false,
    platformProjectFilterOpen: false,
    platformCommLinks: [],
    channelHint: "",
    sessionHint: "",
    projectRowLayout: {},
    windowKey: "24h",
    customRange: { startMs: 0, endMs: 0 },
    sessions: [],
    runs: [],
    groups: [],
    channelSections: [],
    nodes: [],
    commLinks: [],
    selectedGroupId: "",
    selectedSessionId: "",
    selectedPlatformCommLinkId: "",
    dragNode: null,
    dragGroup: null,
    resizeGroup: null,
    dragLayerGroupId: "",
    pan: null,
    zoom: 1,
    platformLoadToken: 0,
    sharedAvatarStore: { bySessionId: {}, clearedSessionIds: {} },
  };

  const dom = {
    platformModeTabsWrap: document.getElementById("platformModeTabs"),
    platformModeButtons: Array.from(document.querySelectorAll("[data-platform-layout]")),
    platformProjectFilterWrap: document.getElementById("platformProjectFilterWrap"),
    platformProjectFilterBtn: document.getElementById("platformProjectFilterBtn"),
    platformProjectFilterPanel: document.getElementById("platformProjectFilterPanel"),
    platformProjectFilterList: document.getElementById("platformProjectFilterList"),
    platformProjectFilterSummary: document.getElementById("platformProjectFilterSummary"),
    platformProjectSelectAllBtn: document.getElementById("platformProjectSelectAllBtn"),
    platformProjectInvertBtn: document.getElementById("platformProjectInvertBtn"),
    platformProjectClearBtn: document.getElementById("platformProjectClearBtn"),
    platformProjectCancelBtn: document.getElementById("platformProjectCancelBtn"),
    platformProjectApplyBtn: document.getElementById("platformProjectApplyBtn"),
    platformCommScopeFilters: document.getElementById("platformCommScopeFilters"),
    platformScopeButtons: Array.from(document.querySelectorAll("[data-comm-scope]")),
    commTypeFilters: document.getElementById("commTypeFilters"),
    commTypeButtons: Array.from(document.querySelectorAll("[data-comm-kind]")),
    timeTabs: Array.from(document.querySelectorAll("[data-window]")),
    customRange: document.getElementById("customRange"),
    customStartInput: document.getElementById("customStartInput"),
    customEndInput: document.getElementById("customEndInput"),
    customApplyBtn: document.getElementById("customApplyBtn"),
    platformCommCountFilters: document.getElementById("platformCommCountFilters"),
    platformCountButtons: Array.from(document.querySelectorAll("[data-comm-count-min]")),
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
    rosterSectionTitle: document.getElementById("rosterSectionTitle"),
    miniMap: document.getElementById("miniMap"),
    zoomInBtn: document.getElementById("zoomInBtn"),
    zoomOutBtn: document.getElementById("zoomOutBtn"),
    zoomResetBtn: document.getElementById("zoomResetBtn"),
    bubbleTooltip: document.getElementById("bubbleTooltip"),
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

  async function fetchJson(url, options = {}) {
    const timeoutMs = Math.max(0, Number(options && options.timeoutMs) || 0);
    const controller = timeoutMs > 0 ? new AbortController() : null;
    let timer = 0;
    if (controller && timeoutMs > 0) {
      timer = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
    }
    const resp = await fetch(url, {
      cache: "no-store",
      headers: authHeaders(),
      signal: controller ? controller.signal : undefined,
    }).finally(() => {
      if (timer) window.clearTimeout(timer);
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  }

  function emptyAvatarStore() {
    return {
      bySessionId: Object.create(null),
      clearedSessionIds: Object.create(null),
    };
  }

  function normalizeAvatarStore(raw) {
    return {
      bySessionId: Object.assign(Object.create(null), raw && typeof raw.bySessionId === "object" ? raw.bySessionId : {}),
      clearedSessionIds: Object.assign(Object.create(null), raw && typeof raw.clearedSessionIds === "object" ? raw.clearedSessionIds : {}),
    };
  }

  function getAvatarAssignmentsV1() {
    try {
      const raw = String(localStorage.getItem(AVATAR_V1_KEY) || "");
      if (!raw) return Object.create(null);
      const data = JSON.parse(raw);
      const assignments = data && typeof data === "object" && data.assignments && typeof data.assignments === "object"
        ? data.assignments
        : {};
      return Object.assign(Object.create(null), assignments);
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

  function payloadAvatarStores() {
    const candidates = [
      DATA.avatar_assignments_by_project,
      DATA.avatarAssignmentsByProject,
      DATA.shared_avatar_store_by_project,
      DATA.sharedAvatarStoreByProject,
    ];
    for (const item of candidates) {
      if (item && typeof item === "object") return item;
    }
    return Object.create(null);
  }

  async function fetchSharedAvatarStore(projectId) {
    const pid = safeText(projectId);
    if (!pid) return emptyAvatarStore();
    const stores = payloadAvatarStores();
    return normalizeAvatarStore(stores[pid]);
  }

  async function fetchSharedAvatarStores(projectIds) {
    const ids = [...new Set((Array.isArray(projectIds) ? projectIds : []).map((item) => safeText(item)).filter(Boolean))];
    if (!ids.length) return emptyAvatarStore();
    const stores = await Promise.all(ids.map((projectId) => fetchSharedAvatarStore(projectId)));
    const merged = emptyAvatarStore();
    stores.forEach((store) => {
      Object.assign(merged.bySessionId, store.bySessionId || {});
      Object.assign(merged.clearedSessionIds, store.clearedSessionIds || {});
    });
    return merged;
  }

  function sessionDisplayName(sessionLike) {
    return firstText([
      sessionLike && sessionLike.alias,
      sessionLike && sessionLike.display_name,
      sessionLike && sessionLike.displayName,
      sessionLike && sessionLike.sender_name,
      sessionLike && sessionLike.channel_name,
      sessionLike && sessionLike.channelName,
      sessionLike && sessionLike.session_id,
      sessionLike && sessionLike.id,
    ], "未命名会话");
  }

  function avatarFallbackLabel(name) {
    const text = safeText(name, "会");
    const digits = text.match(/\d+/);
    if (digits && digits[0]) return digits[0].slice(0, 2);
    return text.slice(0, 1).toUpperCase();
  }

  function getAssignedAvatarId(sessionLike) {
    const sessionId = safeText(sessionLike && (sessionLike.session_id || sessionLike.id));
    const storeV2 = getAvatarStoreV2();
    if (sessionId && storeV2.clearedSessionIds && storeV2.clearedSessionIds[sessionId]) return "";
    const localId = sessionId ? safeText(storeV2.bySessionId && storeV2.bySessionId[sessionId]) : "";
    if (localId && AVATAR_MAP.has(localId)) return localId;
    const sharedId = sessionId ? safeText(STATE.sharedAvatarStore.bySessionId && STATE.sharedAvatarStore.bySessionId[sessionId]) : "";
    if (sharedId && AVATAR_MAP.has(sharedId)) return sharedId;
    const v1 = getAvatarAssignmentsV1();
    const candidates = [
      sessionDisplayName(sessionLike),
      safeText(sessionLike && sessionLike.channel_name),
      safeText(sessionLike && sessionLike.channelName),
      safeText(sessionLike && sessionLike.alias),
    ].filter(Boolean);
    for (const key of candidates) {
      const avatarId = safeText(v1[key]);
      if (avatarId && AVATAR_MAP.has(avatarId)) return avatarId;
    }
    return "";
  }

  function avatarMeta(sessionLike) {
    if (safeText(sessionLike && sessionLike.kind) === "user" && AVATAR_MAP.has("user")) {
      const meta = AVATAR_MAP.get("user");
      return {
        text: String(meta.emoji || "🙋"),
        title: USER_NODE_LABEL,
        c1: String(meta.c1 || "#fde7f3"),
        c2: String(meta.c2 || "#f9c7dd"),
        fallback: false,
      };
    }
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

  function qs() {
    try {
      const search = new URLSearchParams(window.location.search || "");
      const hash = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
      const explicitMode = firstText([
        hash.get("mode"),
        search.get("mode"),
      ], "").toLowerCase();
      const explicitLayout = firstText([
        hash.get("layout"),
        search.get("layout"),
      ], "").toLowerCase();
      const explicitProjectId = firstText([
        hash.get("p"),
        search.get("project_id"),
        search.get("projectId"),
      ], "");
      const mode = firstText([
        explicitMode,
        DATA.mode,
      ], "project").toLowerCase();
      return {
        projectId: mode === "platform"
          ? explicitProjectId
          : firstText([
            explicitProjectId,
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
        mode,
        layout: firstText([
          explicitLayout,
          DATA.layout,
        ], "project").toLowerCase(),
      };
    } catch (_) {
      return { projectId: "", channelName: "", sessionId: "", mode: "project", layout: "project" };
    }
  }

  function isPlatformMode() {
    return safeText(STATE.viewMode).toLowerCase() === "platform";
  }

  function syncRouteLayout() {
    if (!isPlatformMode()) return;
    try {
      const hash = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
      hash.set("mode", "platform");
      hash.set("layout", safeText(STATE.platformLayoutMode || "project"));
      window.history.replaceState(null, "", `#${hash.toString()}`);
    } catch (_) {}
  }

  function projectCatalog() {
    const map = new Map();
    const primary = Array.isArray(DATA.projects) ? DATA.projects : [];
    const overviewProjects = Array.isArray(DATA.overview && DATA.overview.projects) ? DATA.overview.projects : [];

    primary.forEach((item) => {
      const projectId = safeText(item.id || item.project_id);
      if (!projectId) return;
      map.set(projectId, {
        ...item,
        project_id: projectId,
        project_name: firstText([item.name, item.project_name, item.id], projectId),
      });
    });

    overviewProjects.forEach((item) => {
      const projectId = safeText(item.project_id || item.id);
      if (!projectId) return;
      const prev = map.get(projectId) || {};
      map.set(projectId, {
        ...prev,
        ...item,
        project_id: projectId,
        project_name: firstText([
          item.project_name,
          item.name,
          prev.project_name,
          prev.name,
          projectId,
        ], projectId),
        color: firstText([item.color, prev.color]),
        description: firstText([item.description, prev.description]),
        source_kind: firstText([item.source_kind, item.sourceKind, prev.source_kind, prev.sourceKind]),
        source_label: firstText([item.source_label, item.sourceLabel, prev.source_label, prev.sourceLabel]),
        channel_sessions: Array.isArray(prev.channel_sessions) ? prev.channel_sessions : [],
        channels: Array.isArray(prev.channels) ? prev.channels : [],
        registry: prev.registry || {},
        agent_directory_summary: prev.agent_directory_summary || {},
        session_health_config: prev.session_health_config || {},
      });
    });

    return Array.from(map.values());
  }

  function platformProjectIds() {
    return sortProjects(STATE.platformProjects).map((item) => safeText(item.project_id)).filter(Boolean);
  }

  function normalizePlatformProjectSelection() {
    const allIds = platformProjectIds();
    if (!allIds.length) {
      STATE.platformProjectFilterInitialized = false;
      STATE.platformProjectFilterSelected = [];
      STATE.platformProjectFilterDraft = [];
      STATE.platformProjectFilterDraftDirty = false;
      return;
    }
    if (!STATE.platformProjectFilterInitialized) {
      const stored = loadLayoutStore();
      STATE.platformProjectFilterInitialized = Boolean(stored.platform_project_filter_initialized);
      const persisted = Array.isArray(stored.platform_project_selected)
        ? stored.platform_project_selected.map((item) => safeText(item)).filter(Boolean)
        : [];
      if (STATE.platformProjectFilterInitialized) {
        STATE.platformProjectFilterSelected = [...persisted];
      } else if (persisted.length) {
        STATE.platformProjectFilterSelected = [...persisted];
      }
    }
    const current = new Set((Array.isArray(STATE.platformProjectFilterSelected) ? STATE.platformProjectFilterSelected : []).map((item) => safeText(item)).filter(Boolean));
    const next = allIds.filter((id) => current.has(id));
    STATE.platformProjectFilterSelected = STATE.platformProjectFilterInitialized
      ? next
      : (next.length ? next : [...allIds]);
    if (!STATE.platformProjectFilterInitialized && STATE.platformProjectFilterSelected.length) {
      STATE.platformProjectFilterInitialized = true;
    }
    const draft = new Set((Array.isArray(STATE.platformProjectFilterDraft) ? STATE.platformProjectFilterDraft : []).map((item) => safeText(item)).filter(Boolean));
    const nextDraft = allIds.filter((id) => draft.has(id));
    STATE.platformProjectFilterDraft = STATE.platformProjectFilterDraftDirty
      ? nextDraft
      : [...STATE.platformProjectFilterSelected];
  }

  function selectedPlatformProjectIds() {
    normalizePlatformProjectSelection();
    return new Set((STATE.platformProjectFilterSelected || []).map((item) => safeText(item)).filter(Boolean));
  }

  function visiblePlatformProjects() {
    const selected = selectedPlatformProjectIds();
    return sortProjects(STATE.platformProjects).filter((item) => selected.has(safeText(item.project_id)));
  }

  function projectMetaById(projectId) {
    const pid = safeText(projectId);
    if (!pid) return null;
    return projectCatalog().find((item) => safeText(item.project_id) === pid) || null;
  }

  function projectPayloadById(projectId) {
    const pid = safeText(projectId);
    if (!pid) return null;
    const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
    return projects.find((item) => safeText(item && (item.id || item.project_id)) === pid) || null;
  }

  function buildProjectSessionsFromRegistry(project) {
    if (!project || typeof project !== "object") return [];
    const registry = (project.registry && typeof project.registry === "object") ? project.registry : {};
    const channels = Array.isArray(registry.channels) ? registry.channels : [];
    const projectId = safeText(project.project_id || project.id);
    const projectName = firstText([project.project_name, project.name], projectId);
    const rows = [];
    const seen = new Set();
    channels.forEach((channel, index) => {
      const channelName = firstText([channel.channel_name, channel.name], `未命名通道${index + 1}`);
      const candidates = Array.isArray(channel.session_candidates) ? channel.session_candidates : [];
      candidates.forEach((item) => {
        const session = normalizeSession({
          ...item,
          id: firstText([item.id, item.session_id, item.sessionId]),
          session_id: firstText([item.session_id, item.sessionId, item.id]),
          channel_name: channelName,
          alias: firstText([item.alias, item.display_name, item.displayName]),
          display_name: firstText([item.display_name, item.displayName, item.alias]),
          project_id: projectId,
          project_name: projectName,
          status: firstText([item.session_display_state, item.display_state, item.status], "active"),
          desc: firstText([item.session_role, channel.channel_desc, item.cli_type], "协作Agent"),
        });
        if (!session || seen.has(session.session_id)) return;
        seen.add(session.session_id);
        rows.push(session);
      });
    });
    return rows;
  }

  function buildProjectSessionsFromPayload(projectId) {
    const project = projectPayloadById(projectId);
    if (!project) return [];
    const registrySessions = buildProjectSessionsFromRegistry(project);
    if (registrySessions.length) return registrySessions;
    const rows = Array.isArray(project.channel_sessions) ? project.channel_sessions : [];
    return rows
      .map((item) => normalizeSession({
        ...item,
        channel_name: firstText([item.channel_name, item.channelName, item.name]),
        alias: sessionDisplayName(item),
        project_id: projectId,
        project_name: firstText([project.name, project.project_name], projectId),
        status: firstText([item.status], "active"),
        desc: firstText([item.desc, item.session_role, item.cli_type], "协作Agent"),
      }))
      .filter(Boolean);
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

  function buildPlatformSessionsFromPayload(projects) {
    const sessions = [];
    const seen = new Set();
    (Array.isArray(projects) ? projects : []).forEach((project) => {
      const projectId = safeText(project.project_id || project.id);
      const projectName = firstText([project.project_name, project.name], projectId);
      const registrySessions = buildProjectSessionsFromRegistry(project);
      if (registrySessions.length) {
        registrySessions.forEach((session) => {
          const sessionId = safeText(session.session_id);
          if (!sessionId || seen.has(sessionId)) return;
          seen.add(sessionId);
          sessions.push({
            ...session,
            project_id: projectId,
            project_name: projectName,
          });
        });
        return;
      }
      const rows = Array.isArray(project.channel_sessions) ? project.channel_sessions : [];
      rows.forEach((row, index) => {
        const channelName = firstText([row.name, row.channel_name, row.channelName], `未命名通道${index + 1}`);
        const realSessionId = safeText(row.session_id || row.sessionId);
        const syntheticSessionId = `virtual:${projectId}:${channelName}:${index}`;
        const sessionId = realSessionId || syntheticSessionId;
        if (!sessionId || seen.has(sessionId)) return;
        seen.add(sessionId);
        sessions.push({
          session_id: sessionId,
          alias: firstText([
            row.alias,
            row.display_name,
            row.displayName,
            row.name,
            channelName,
            sessionId,
          ], channelName),
          channel_name: channelName,
          project_id: projectId,
          project_name: projectName,
          cli_type: firstText([row.cli_type, row.cliType], "codex"),
          status: firstText([row.status], realSessionId ? "idle" : "unbound"),
          environment: firstText([row.environment], DATA.environment || "stable"),
          role: firstText([row.desc, row.session_role, row.sessionRole], "协作Agent"),
          desc: firstText([row.desc]),
          is_virtual: !realSessionId,
        });
      });
    });
    return sessions;
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
    if (text.startsWith("子级") || text.startsWith("业务")) return "dev";
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
    let scope = "";
    if (isPlatformMode()) {
      const mode = safeText(STATE.platformLayoutMode || "project");
      const version = mode === "agent" ? "v5" : "v3";
      scope = `platform:${mode}:${version}`;
    } else {
      scope = `${safeText(STATE.projectId || "global")}:${PROJECT_LAYOUT_VERSION}`;
    }
    return `${STORAGE_PREFIX}:${scope}`;
  }

  function projectLayoutStorageKey(projectId) {
    return `${STORAGE_PREFIX}:${safeText(projectId || "global")}:${PROJECT_LAYOUT_VERSION}`;
  }

  function compactNodeCardSize(alias, mode = "project") {
    const length = safeText(alias, "Agent").length;
    const baseWidth = mode === "platform" ? 136 : 188;
    const extraWidth = mode === "platform"
      ? Math.min(84, Math.max(0, length - 3) * 10)
      : Math.min(168, Math.max(0, length - 4) * 11);
    return {
      w: baseWidth + extraWidth,
      h: mode === "platform" ? 52 : 68,
    };
  }

  function projectGroupColumns(count) {
    const total = Math.max(0, Number(count) || 0);
    if (total <= 2) return 1;
    if (total <= 4) return 2;
    if (total <= 8) return 3;
    return 4;
  }

  function projectGroupSpec(group) {
    const sessions = Array.isArray(group && group.sessions) ? group.sessions : [];
    const sizes = sessions.map((session) => compactNodeCardSize(safeText(session.alias, session.session_id), "project"));
    const count = Math.max(1, sessions.length);
    const columns = projectGroupColumns(count);
    const rows = Math.max(1, Math.ceil(count / columns));
    const nodeGapX = 18;
    const nodeGapY = 16;
    const headerH = 96;
    const footerH = 26;
    const innerPadX = 28;
    const innerPadY = 22;
    const cellW = Math.max(212, ...sizes.map((item) => Number(item.w || 212)));
    const cellH = Math.max(68, ...sizes.map((item) => Number(item.h || 68)));
    const width = Math.max(312, innerPadX * 2 + columns * cellW + Math.max(0, columns - 1) * nodeGapX);
    const height = Math.max(188, headerH + footerH + innerPadY * 2 + rows * cellH + Math.max(0, rows - 1) * nodeGapY);
    return {
      columns,
      rows,
      headerH,
      footerH,
      innerPadX,
      innerPadY,
      nodeGapX,
      nodeGapY,
      cellW,
      cellH,
      width,
      height,
      sizes,
    };
  }

  function buildProjectRowLanes(items, maxWidth, gapX) {
    const lanes = [];
    let lane = [];
    let laneWidth = 0;
    items.forEach((group) => {
      const spec = group.spec || projectGroupSpec(group);
      const groupWidth = Number(spec.width || 0);
      const nextWidth = lane.length ? (laneWidth + gapX + groupWidth) : groupWidth;
      if (lane.length && nextWidth > maxWidth) {
        lanes.push({ items: lane, width: laneWidth });
        lane = [group];
        laneWidth = groupWidth;
      } else {
        lane.push(group);
        laneWidth = nextWidth;
      }
    });
    if (lane.length) lanes.push({ items: lane, width: laneWidth });
    return lanes;
  }

  function loadLayoutStoreByKey(key) {
    const fallback = {
      groups: [],
      nodes: [],
      zoom: 1,
      platform_project_selected: [],
      platform_project_filter_initialized: false,
      platform_comm_scope: "all",
      comm_kind_visibility: { user: true, agent: true },
      comm_count_min: 0,
    };
    try {
      const raw = localStorage.getItem(safeText(key));
      if (!raw) return fallback;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function loadLayoutStore() {
    return loadLayoutStoreByKey(layoutStorageKey());
  }

  function persistLayoutStore() {
    try {
      const groups = isPlatformMode() ? [] : STATE.groups;
      localStorage.setItem(layoutStorageKey(), JSON.stringify({
        groups,
        nodes: isPlatformMode() ? [] : STATE.nodes.map((node) => ({ session_id: node.session_id, x: node.x, y: node.y })),
        zoom: STATE.zoom,
        platform_project_selected: isPlatformMode() ? [...(STATE.platformProjectFilterSelected || [])] : [],
        platform_project_filter_initialized: isPlatformMode() ? Boolean(STATE.platformProjectFilterInitialized) : false,
        platform_comm_scope: safeText(STATE.platformCommScope, "all"),
        comm_kind_visibility: {
          user: STATE.commVisibility.user !== false,
          agent: STATE.commVisibility.agent !== false,
        },
        comm_count_min: Math.max(0, Number(STATE.commLineCountMin) || 0),
      }));
    } catch (_) {}
  }

  function restoreCommFilterStateFromStore() {
    const stored = loadLayoutStore();
    const visibility = (stored && stored.comm_kind_visibility && typeof stored.comm_kind_visibility === "object")
      ? stored.comm_kind_visibility
      : {};
    const scope = safeText(stored && stored.platform_comm_scope, "all");
    STATE.platformCommScope = ["all", "cross", "high"].includes(scope) ? scope : "all";
    STATE.commVisibility.user = visibility.user !== false;
    STATE.commVisibility.agent = visibility.agent !== false;
    STATE.commLineCountMin = Math.max(0, Number(stored && stored.comm_count_min) || 0);
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

  function currentWindowLabel() {
    const range = currentWindowRange();
    return STATE.windowKey === "custom"
      ? `自定义 ${fmtDateTime(range.startMs)} ~ ${fmtDateTime(range.endMs)}`
      : `窗口 ${STATE.windowKey}`;
  }

  function totalCommCount(links) {
    return (Array.isArray(links) ? links : []).reduce((sum, link) => sum + Number(link.count || 0), 0);
  }

  function isUserCommLink(link) {
    return safeText(link && link.from_id) === USER_NODE_ID || safeText(link && link.to_id) === USER_NODE_ID;
  }

  function platformCommScopeLabel(scope = STATE.platformCommScope) {
    const value = safeText(scope, "all");
    if (value === "cross") return "只看跨项目";
    if (value === "high") return `只看高频(${PLATFORM_HIGH_FREQ_COUNT}+)`;
    return "全部沟通";
  }

  function platformCommScopeSummaryLabel(scope = STATE.platformCommScope) {
    const value = safeText(scope, "all");
    if (value === "cross") return "跨项目";
    if (value === "high") return `高频(${PLATFORM_HIGH_FREQ_COUNT}+)`;
    return "全部";
  }

  function filteredCommLinks(links) {
    const min = Math.max(0, Number(STATE.commLineCountMin) || 0);
    const showUser = STATE.commVisibility.user !== false;
    const showAgent = STATE.commVisibility.agent !== false;
    return (Array.isArray(links) ? links : []).filter((link) => {
      const count = Number(link.count || 0);
      if (count < min) return false;
      const isUserLink = isUserCommLink(link);
      if (isUserLink) return showUser;
      return showAgent;
    });
  }

  function groupActivityStats(group) {
    const sessionIds = new Set(group && Array.isArray(group.sessionIds) ? group.sessionIds : []);
    if (isPlatformMode()) {
      const relevant = (STATE.platformCommLinks || []).filter((link) => {
        const fromHit = sessionIds.has(link.from_id) || sessionIds.has(`project::${safeText(link.source_project_id)}`);
        const toHit = sessionIds.has(link.to_id) || sessionIds.has(`project::${safeText(link.target_project_id)}`);
        return fromHit || toHit;
      });
      const count = relevant.reduce((sum, link) => sum + Number(link.count || 0), 0);
      return {
        count,
        recent: relevant.filter((link) => Number(link.count || 0) >= 5).length,
        active: relevant.length > 0,
        peak: relevant.some((link) => Number(link.count || 0) >= 10),
      };
    }
    const relevant = (STATE.commLinks || []).filter((link) => sessionIds.has(link.from_id) || sessionIds.has(link.to_id));
    const count = relevant.reduce((sum, link) => sum + Number(link.count || 0), 0);
    return {
      count,
      recent: relevant.length,
      active: count > 0,
      peak: relevant.some((link) => Number(link.count || 0) >= PLATFORM_HIGH_FREQ_COUNT),
    };
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

  function stableHash(input) {
    const source = safeText(input);
    let hash = 0;
    for (let index = 0; index < source.length; index += 1) {
      hash = ((hash << 5) - hash) + source.charCodeAt(index);
      hash |= 0;
    }
    return Math.abs(hash);
  }

  function communicationGeometry(start, end, link, mode = "project") {
    const userLink = safeText(link && link.from_id) === USER_NODE_ID || safeText(link && link.to_id) === USER_NODE_ID;
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);
    const horizontal = absDx >= absDy * 0.9;
    const signX = dx === 0 ? 1 : Math.sign(dx);
    const signY = dy === 0 ? 1 : Math.sign(dy);
    const seed = `${safeText(link && link.id)}:${safeText(link && link.from_id)}:${safeText(link && link.to_id)}:${mode}`;
    const laneIndex = (stableHash(seed) % 5) - 2;
    const laneOffset = laneIndex * (horizontal ? 22 : 18);
    const centerX = (start.x + end.x) / 2;
    const centerY = (start.y + end.y) / 2;
    if (userLink) {
      const userIsStart = safeText(link && link.from_id) === USER_NODE_ID;
      const userPoint = userIsStart ? start : end;
      const peerPoint = userIsStart ? end : start;
      const spanX = peerPoint.x - userPoint.x;
      const spanY = peerPoint.y - userPoint.y;
      const signX = spanX === 0 ? 1 : Math.sign(spanX);
      const fanX = userPoint.x + signX * Math.max(96, Math.min(260, Math.abs(spanX) * 0.22 + 44)) + laneOffset;
      const dropY = userPoint.y + Math.max(68, Math.min(156, Math.abs(spanY) * 0.22 + 26));
      const approachY = peerPoint.y - Math.max(48, Math.min(132, Math.abs(spanY) * 0.16 + 18));
      const path = `M ${userPoint.x} ${userPoint.y} C ${userPoint.x} ${dropY}, ${fanX} ${dropY}, ${fanX} ${(dropY + approachY) / 2} C ${fanX} ${approachY}, ${peerPoint.x} ${approachY}, ${peerPoint.x} ${peerPoint.y}`;
      return {
        path: userIsStart ? path : `M ${peerPoint.x} ${peerPoint.y} C ${peerPoint.x} ${approachY}, ${fanX} ${approachY}, ${fanX} ${(dropY + approachY) / 2} C ${fanX} ${dropY}, ${userPoint.x} ${dropY}, ${userPoint.x} ${userPoint.y}`,
        labelPoint: {
          x: Math.round((fanX + peerPoint.x) / 2),
          y: Math.round((dropY + approachY) / 2 - 16),
        },
      };
    }
    if (horizontal) {
      const reach = Math.max(84, Math.min(220, absDx * 0.28 + absDy * 0.12));
      const bow = Math.max(42, Math.min(170, absDx * 0.12 + absDy * 0.16));
      const bendY = centerY - signY * bow + laneOffset;
      const midLeftX = centerX - Math.max(46, Math.min(140, absDx * 0.16));
      const midRightX = centerX + Math.max(46, Math.min(140, absDx * 0.16));
      return {
        path: `M ${start.x} ${start.y} C ${start.x + signX * reach} ${start.y}, ${midLeftX} ${bendY}, ${centerX} ${bendY} C ${midRightX} ${bendY}, ${end.x - signX * reach} ${end.y}, ${end.x} ${end.y}`,
        labelPoint: {
          x: Math.round(centerX),
          y: Math.round(bendY - (signY >= 0 ? 14 : -14)),
        },
      };
    }
    const reach = Math.max(84, Math.min(220, absDy * 0.28 + absDx * 0.12));
    const bow = Math.max(52, Math.min(180, absDy * 0.14 + absDx * 0.18));
    const bendX = centerX - signX * bow + laneOffset;
    const midTopY = centerY - Math.max(52, Math.min(150, absDy * 0.16));
    const midBottomY = centerY + Math.max(52, Math.min(150, absDy * 0.16));
    return {
      path: `M ${start.x} ${start.y} C ${start.x} ${start.y + signY * reach}, ${bendX} ${midTopY}, ${bendX} ${centerY} C ${bendX} ${midBottomY}, ${end.x} ${end.y - signY * reach}, ${end.x} ${end.y}`,
      labelPoint: {
        x: Math.round(bendX + (signX >= 0 ? 16 : -16)),
        y: Math.round(centerY - 10),
      },
    };
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

  function computeGroupsAndNodes(sessions, layoutStore = loadLayoutStore(), options = {}) {
    const includeUserNode = options.includeUserNode !== false;
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
    channels.forEach((group) => {
      group.sessions.sort((a, b) => safeText(a.alias, a.session_id).localeCompare(safeText(b.alias, b.session_id), "zh-Hans-CN"));
      group.spec = projectGroupSpec(group);
    });
    const savedMap = new Map((Array.isArray(layoutStore.groups) ? layoutStore.groups : []).map((group) => [group.id, group]));
    const savedNodeMap = new Map((Array.isArray(layoutStore.nodes) ? layoutStore.nodes : []).map((node) => [safeText(node.session_id || node.sessionId), node]));
    const rows = { master: [], assist: [], dev: [], other: [] };
    Array.from(channels.values())
      .sort((a, b) => {
        const countDiff = Number(b.sessions.length || 0) - Number(a.sessions.length || 0);
        if (countDiff !== 0) return countDiff;
        return a.label.localeCompare(b.label, "zh-Hans-CN");
      })
      .forEach((group) => rows[group.rowKind].push(group));

    const groups = [];
    const rowLayout = {};
    const layoutOrder = ["master", "assist", "dev", "other"];
    let cursorY = 156;
    layoutOrder.forEach((rowKind) => {
      const items = rows[rowKind] || [];
      if (!items.length) {
        rowLayout[rowKind] = { top: cursorY, labelY: cursorY - 54, height: 0, empty: true };
        return;
      }
      const boardInnerLeft = 420;
      const boardInnerRight = 420;
      const maxRowWidth = Math.max(2200, STAGE_MIN.project.width - boardInnerLeft - boardInnerRight);
      const groupGapX = rowKind === "master" ? 112 : 96;
      const groupGapY = rowKind === "master" ? 92 : 84;
      const bandGap = rowKind === "master" ? 112 : 132;
      let laneY = cursorY;
      const rowTop = cursorY;
      let maxLaneHeight = 0;
      let runningIndex = 0;
      buildProjectRowLanes(items, maxRowWidth, groupGapX).forEach((lane) => {
        const laneWidth = Number(lane.width || 0);
        const laneStartX = boardInnerLeft + Math.max(0, Math.round((maxRowWidth - laneWidth) / 2));
        let cursorX = laneStartX;
        let laneHeight = 0;
        lane.items.forEach((group) => {
          const spec = group.spec || projectGroupSpec(group);
          const width = spec.width;
          const height = spec.height;
          const saved = savedMap.get(group.id);
          groups.push({
            id: group.id,
            label: group.label,
            rowKind,
            accent: group.accent,
            x: Number(saved && saved.x) || cursorX,
            y: Number(saved && saved.y) || laneY,
            w: Number(saved && saved.w) || width,
            h: Number(saved && saved.h) || height,
            z: Number.isFinite(Number(saved && saved.z)) ? Number(saved.z) : runningIndex,
            sessionIds: group.sessions.map((item) => item.session_id),
            layout: spec,
          });
          cursorX += width + groupGapX;
          laneHeight = Math.max(laneHeight, height);
          runningIndex += 1;
        });
        maxLaneHeight = Math.max(maxLaneHeight, laneHeight);
        laneY += laneHeight + groupGapY;
      });
      const rowHeight = Math.max(0, laneY - rowTop - groupGapY) || maxLaneHeight;
      rowLayout[rowKind] = {
        top: rowTop,
        labelY: Math.max(56, rowTop - 54),
        height: rowHeight,
        empty: false,
      };
      cursorY = rowTop + rowHeight + bandGap;
    });
    groups.sort((a, b) => a.z - b.z);

    const nodes = [];
    groups.forEach((group) => {
      const groupSessions = (sessions || []).filter((session) => group.sessionIds.includes(session.session_id));
      const spec = group.layout || projectGroupSpec({ sessions: groupSessions });
      const columns = Math.max(1, Number(spec.columns) || 1);
      groupSessions.forEach((session, index) => {
        const col = index % columns;
        const row = Math.floor(index / columns);
        const savedNode = savedNodeMap.get(session.session_id);
        const size = compactNodeCardSize(safeText(session.alias, session.session_id), "project");
        const offsetX = Math.round((spec.cellW - size.w) / 2);
        nodes.push({
          id: session.session_id,
          session_id: session.session_id,
          group_id: group.id,
          x: Number(savedNode && savedNode.x) || (group.x + spec.innerPadX + col * (spec.cellW + spec.nodeGapX) + offsetX),
          y: Number(savedNode && savedNode.y) || (group.y + spec.headerH + spec.innerPadY + row * (spec.cellH + spec.nodeGapY)),
          w: size.w,
          h: size.h,
          alias: safeText(session.alias, session.session_id),
          role: safeText(session.desc || session.role, "协作Agent"),
          channel_name: safeText(session.channel_name, "未分组通道"),
          status: safeText(session.status, "idle"),
          accent: group.accent,
        });
      });
    });
    return { groups, nodes: includeUserNode ? attachTopUserNode(groups, nodes, STATE.projectId) : nodes, rowLayout };
  }

  function projectStatusFromTotals(totals) {
    const info = (totals && typeof totals === "object") ? totals : {};
    const inProgress = Number(info.in_progress || 0);
    const active = Number(info.active || 0);
    const total = Number(info.total || 0);
    const done = Number(info.done || 0);
    if (inProgress > 0) return "进行中";
    if (active > 0) return "活跃";
    if (total > 0 && done >= total) return "已完成";
    return "待启动";
  }

  function projectAccent(project) {
    return safeText(project && project.color) || accentFor(firstText([
      project && project.project_name,
      project && project.project_id,
    ], "项目"));
  }

  function sortProjects(projects) {
    return [...(Array.isArray(projects) ? projects : [])].sort((a, b) => {
      const aTotals = (a && a.totals && typeof a.totals === "object") ? a.totals : {};
      const bTotals = (b && b.totals && typeof b.totals === "object") ? b.totals : {};
      const aScore = Number(aTotals.in_progress || 0) * 100 + Number(aTotals.active || 0) * 10 + Number(aTotals.channels || 0);
      const bScore = Number(bTotals.in_progress || 0) * 100 + Number(bTotals.active || 0) * 10 + Number(bTotals.channels || 0);
      if (aScore !== bScore) return bScore - aScore;
      return firstText([a.project_name, a.name, a.project_id]).localeCompare(firstText([b.project_name, b.name, b.project_id]), "zh-Hans-CN");
    });
  }

  function computeBoardBounds(groups, nodes) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = 0;
    let maxY = 0;
    (Array.isArray(groups) ? groups : []).forEach((group) => {
      minX = Math.min(minX, Number(group.x || 0));
      minY = Math.min(minY, Number(group.y || 0));
      maxX = Math.max(maxX, Number(group.x || 0) + Number(group.w || 0));
      maxY = Math.max(maxY, Number(group.y || 0) + Number(group.h || 0));
    });
    (Array.isArray(nodes) ? nodes : []).forEach((node) => {
      minX = Math.min(minX, Number(node.x || 0));
      minY = Math.min(minY, Number(node.y || 0));
      maxX = Math.max(maxX, Number(node.x || 0) + Number(node.w || CARD_WIDTH));
      maxY = Math.max(maxY, Number(node.y || 0) + Number(node.h || CARD_HEIGHT));
    });
    if (!Number.isFinite(minX) || !Number.isFinite(minY)) {
      return { minX: 0, minY: 0, maxX: 0, maxY: 0, width: 0, height: 0 };
    }
    return {
      minX,
      minY,
      maxX,
      maxY,
      width: Math.max(0, maxX - minX),
      height: Math.max(0, maxY - minY),
    };
  }

  function buildUserNode(x, y, projectId = "") {
    return {
      id: USER_NODE_ID,
      session_id: USER_NODE_ID,
      group_id: "",
      x: Math.round(x),
      y: Math.round(y),
      w: 172,
      h: 52,
      alias: USER_NODE_LABEL,
      role: "发起者",
      channel_name: "用户维度",
      status: "在线",
      accent: "#f7a8c2",
      kind: "user",
      readonly: true,
      project_id: safeText(projectId),
      metric_items: [],
    };
  }

  function attachTopUserNode(groups, nodes, projectId = "") {
    const list = Array.isArray(nodes) ? nodes.slice() : [];
    const bounds = computeBoardBounds(groups, list);
    const fallbackWidth = isPlatformMode() ? STAGE_MIN.platform.width : STAGE_MIN.project.width;
    const centerX = bounds.width > 0 ? (bounds.minX + bounds.maxX) / 2 : fallbackWidth / 2;
    const topY = bounds.height > 0 ? Math.max(36, bounds.minY - 110) : 42;
    list.unshift(buildUserNode(centerX - 86, topY, projectId));
    return list;
  }

  function visibleAgentNodeCount() {
    return (STATE.nodes || []).filter((node) => {
      const kind = safeText(node && node.kind);
      return kind !== "project" && kind !== "user";
    }).length;
  }

  function platformSectionMeta(channelName) {
    const name = safeText(channelName, "未分组通道");
    if (/^(主体|总控|总任务|总管)/.test(name) || name.includes("合并与验收")) {
      return { key: "core", label: "主体分工", order: 0 };
    }
    if (/^辅助/.test(name) || name.includes("skills") || name.includes("文档") || name.includes("项目管理") || name.includes("运维")) {
      return { key: "assist", label: "辅助支撑", order: 1 };
    }
    if (/^子级/.test(name) || name.includes("项目开发")) {
      return { key: "dev", label: "子级执行", order: 2 };
    }
    if (/^(业务|运营|游戏|日志)/.test(name) || name.includes("可视化") || name.includes("内容")) {
      return { key: "biz", label: "业务分工", order: 3 };
    }
    return { key: "other", label: "其他分工", order: 4 };
  }

  function stageMetrics() {
    let maxX = 0;
    let maxY = 0;
    STATE.groups.forEach((group) => {
      maxX = Math.max(maxX, Number(group.x || 0) + Number(group.w || 0));
      maxY = Math.max(maxY, Number(group.y || 0) + Number(group.h || 0));
    });
    STATE.nodes.forEach((node) => {
      maxX = Math.max(maxX, Number(node.x || 0) + Number(node.w || CARD_WIDTH));
      maxY = Math.max(maxY, Number(node.y || 0) + Number(node.h || CARD_HEIGHT));
    });
    return {
      width: Math.max(isPlatformMode() ? STAGE_MIN.platform.width : STAGE_MIN.project.width, Math.ceil(maxX + 520)),
      height: Math.max(isPlatformMode() ? STAGE_MIN.platform.height : STAGE_MIN.project.height, Math.ceil(maxY + 460)),
    };
  }

  function contentBounds() {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = 0;
    let maxY = 0;
    STATE.groups.forEach((group) => {
      minX = Math.min(minX, Number(group.x || 0));
      minY = Math.min(minY, Number(group.y || 0));
      maxX = Math.max(maxX, Number(group.x || 0) + Number(group.w || 0));
      maxY = Math.max(maxY, Number(group.y || 0) + Number(group.h || 0));
    });
    STATE.nodes.forEach((node) => {
      minX = Math.min(minX, Number(node.x || 0));
      minY = Math.min(minY, Number(node.y || 0));
      maxX = Math.max(maxX, Number(node.x || 0) + Number(node.w || CARD_WIDTH));
      maxY = Math.max(maxY, Number(node.y || 0) + Number(node.h || CARD_HEIGHT));
    });
    if (!Number.isFinite(minX) || !Number.isFinite(minY)) return null;
    return {
      minX,
      minY,
      maxX,
      maxY,
      width: Math.max(0, maxX - minX),
      height: Math.max(0, maxY - minY),
    };
  }

  function restoreViewportForFreshLayout(layoutStore) {
    const hasSavedGroups = Array.isArray(layoutStore && layoutStore.groups) && layoutStore.groups.length > 0;
    const hasSavedNodes = Array.isArray(layoutStore && layoutStore.nodes) && layoutStore.nodes.length > 0;
    if (hasSavedGroups || hasSavedNodes || !dom.stageWrap) return;
    requestAnimationFrame(() => {
      const bounds = contentBounds();
      if (!bounds) return;
      const centerX = (bounds.minX + bounds.maxX) / 2;
      const centerY = (bounds.minY + bounds.maxY) / 2;
      dom.stageWrap.scrollLeft = Math.max(0, centerX * STATE.zoom - dom.stageWrap.clientWidth / 2);
      dom.stageWrap.scrollTop = Math.max(0, centerY * STATE.zoom - dom.stageWrap.clientHeight / 2);
      renderMiniMap();
    });
  }

  function applyStageMetrics() {
    if (!dom.stage || !dom.stageViewport) return;
    const metrics = stageMetrics();
    dom.stage.style.width = `${metrics.width}px`;
    dom.stage.style.minHeight = `${metrics.height}px`;
    dom.stageViewport.style.width = `${metrics.width * STATE.zoom}px`;
    dom.stageViewport.style.minHeight = `${metrics.height * STATE.zoom}px`;
  }

  function collectRunCommunicationPairs(sessions, runs) {
    const sessionMap = new Map((sessions || []).map((session) => [session.session_id, session]));
    const filteredRuns = filterRunsByWindow(runs).filter((run) => sessionMap.has(run.session_id));
    const runMap = new Map(filteredRuns.map((run) => [run.run_id, run]));
    const pairs = [];
    filteredRuns.forEach((run) => {
      const sourceSessionId = safeText(run.session_id);
      if (!sourceSessionId) return;
      if (safeText(run.sender_type) === "user" || safeText(run.message_kind) === "user_input") {
        pairs.push({
          source_session_id: USER_NODE_ID,
          target_session_id: sourceSessionId,
          created_at: safeText(run.created_at),
          ts: dateMs(run.created_at),
          run_id: safeText(run.run_id),
        });
        return;
      }
      const targets = new Set();
      if (run.reply_to_run_id && runMap.has(run.reply_to_run_id)) {
        targets.add(safeText(runMap.get(run.reply_to_run_id).session_id));
      }
      const callbackSessionId = firstText([
        run.callback_to && run.callback_to.session_id,
        run.callback_to && run.callback_to.sessionId,
      ]);
      if (callbackSessionId) targets.add(callbackSessionId);
      resolveTargetSessionIds(
        [
          safeText(run.message_preview),
          safeText(run.source_ref_text),
          safeText(run.callback_to_text),
        ].filter(Boolean).join("\n"),
        sessionMap,
      ).forEach((sid) => targets.add(sid));
      targets.forEach((targetSessionId) => {
        if (!targetSessionId || targetSessionId === sourceSessionId) return;
        if (!sessionMap.has(targetSessionId)) return;
        pairs.push({
          source_session_id: sourceSessionId,
          target_session_id: targetSessionId,
          created_at: safeText(run.created_at),
          ts: dateMs(run.created_at),
          run_id: safeText(run.run_id),
        });
      });
    });
    return { filteredRuns, pairs };
  }

  function aggregatePlatformCommunication(mode, projects, sessions, runs) {
    const orderedProjects = sortProjects(projects);
    const sessionMap = new Map((sessions || []).map((session) => [session.session_id, session]));
    const projectMap = new Map(orderedProjects.map((project) => [safeText(project.project_id), project]));
    const { filteredRuns, pairs } = collectRunCommunicationPairs(sessions, runs);
    const messageCountBySession = new Map();
    filteredRuns.forEach((run) => {
      const key = safeText(run.session_id);
      if (!key) return;
      messageCountBySession.set(key, Number(messageCountBySession.get(key) || 0) + 1);
    });

    if (mode === "project") {
      const linkMap = new Map();
      pairs.forEach((pair) => {
        const source = sessionMap.get(pair.source_session_id);
        const target = sessionMap.get(pair.target_session_id);
        const sourceProjectId = pair.source_session_id === USER_NODE_ID ? USER_NODE_ID : safeText(source && source.project_id);
        const targetProjectId = pair.target_session_id === USER_NODE_ID ? USER_NODE_ID : safeText(target && target.project_id);
        if (!sourceProjectId || !targetProjectId || sourceProjectId === targetProjectId) return;
        const [endpointA, endpointB] = [sourceProjectId, targetProjectId].sort((a, b) => a.localeCompare(b, "en"));
        const key = `${endpointA}|${endpointB}`;
        if (!linkMap.has(key)) {
          linkMap.set(key, {
            id: `project-link:${key}`,
            from_id: endpointA === USER_NODE_ID ? USER_NODE_ID : `project::${endpointA}`,
            to_id: endpointB === USER_NODE_ID ? USER_NODE_ID : `project::${endpointB}`,
            count: 0,
            from_to_count: 0,
            to_from_count: 0,
            cross_project: true,
            last_ts: 0,
            source_project_id: endpointA,
            target_project_id: endpointB,
          });
        }
        const link = linkMap.get(key);
        link.count += 1;
        if (sourceProjectId === endpointA) link.from_to_count += 1;
        else link.to_from_count += 1;
        link.last_ts = Math.max(link.last_ts, Number(pair.ts || 0));
      });
      const links = Array.from(linkMap.values()).sort((a, b) => b.count - a.count || a.from_id.localeCompare(b.from_id, "en"));
      const metricsByProject = new Map(orderedProjects.map((project) => [safeText(project.project_id), {
        message_count: 0,
        peer_count: 0,
        line_count: 0,
        cross_count: 0,
        session_count: 0,
      }]));
      (sessions || []).forEach((session) => {
        const pid = safeText(session.project_id);
        const metrics = metricsByProject.get(pid);
        if (!metrics) return;
        metrics.session_count += 1;
        metrics.message_count += Number(messageCountBySession.get(session.session_id) || 0);
      });
      links.forEach((link) => {
        [link.source_project_id, link.target_project_id].forEach((pid) => {
          const metrics = metricsByProject.get(pid);
          if (!metrics) return;
          metrics.peer_count += 1;
          metrics.line_count += 1;
          metrics.cross_count += link.count;
        });
      });
      return { links, messageCountBySession, metricsByProject };
    }

    const linkMap = new Map();
    pairs.forEach((pair) => {
      const source = sessionMap.get(pair.source_session_id);
      const target = sessionMap.get(pair.target_session_id);
      const sourceIsUser = pair.source_session_id === USER_NODE_ID;
      const targetIsUser = pair.target_session_id === USER_NODE_ID;
      if ((!source && !sourceIsUser) || (!target && !targetIsUser)) return;
      const [endpointA, endpointB] = [pair.source_session_id, pair.target_session_id].sort((a, b) => a.localeCompare(b, "en"));
      const key = `${endpointA}|${endpointB}`;
      if (!linkMap.has(key)) {
        linkMap.set(key, {
          id: `agent-link:${key}`,
          from_id: endpointA,
          to_id: endpointB,
          count: 0,
          from_to_count: 0,
          to_from_count: 0,
          cross_project: sourceIsUser || targetIsUser || safeText(source && source.project_id) !== safeText(target && target.project_id),
          last_ts: 0,
          source_project_id: sourceIsUser ? USER_NODE_ID : safeText(source && source.project_id),
          target_project_id: targetIsUser ? USER_NODE_ID : safeText(target && target.project_id),
        });
      }
      const link = linkMap.get(key);
      link.count += 1;
      if (pair.source_session_id === endpointA) link.from_to_count += 1;
      else link.to_from_count += 1;
      link.last_ts = Math.max(link.last_ts, Number(pair.ts || 0));
    });
    const links = Array.from(linkMap.values()).sort((a, b) => b.count - a.count || a.from_id.localeCompare(b.from_id, "en"));
    const peerMap = new Map();
    const commCountBySession = new Map();
    links.forEach((link) => {
      peerMap.set(link.from_id, Number(peerMap.get(link.from_id) || 0) + 1);
      peerMap.set(link.to_id, Number(peerMap.get(link.to_id) || 0) + 1);
      commCountBySession.set(link.from_id, Number(commCountBySession.get(link.from_id) || 0) + Number(link.count || 0));
      commCountBySession.set(link.to_id, Number(commCountBySession.get(link.to_id) || 0) + Number(link.count || 0));
    });
    return { links, messageCountBySession, peerMap, commCountBySession };
  }

  function aggregateNodeCommunicationLinks(nodes, runs) {
    const nodeIds = new Set((nodes || []).map((node) => safeText(node.session_id)).filter(Boolean));
    const scopedSessions = (STATE.sessions || []).filter((session) => nodeIds.has(safeText(session.session_id)));
    const { filteredRuns, pairs } = collectRunCommunicationPairs(scopedSessions, runs);
    const messageCountBySession = new Map();
    filteredRuns.forEach((run) => {
      const sid = safeText(run.session_id);
      if (!nodeIds.has(sid)) return;
      messageCountBySession.set(sid, Number(messageCountBySession.get(sid) || 0) + 1);
    });
    const linkMap = new Map();
    pairs.forEach((pair) => {
      const sourceId = safeText(pair.source_session_id);
      const targetId = safeText(pair.target_session_id);
      if (!nodeIds.has(sourceId) || !nodeIds.has(targetId) || sourceId === targetId) return;
      const [endpointA, endpointB] = [sourceId, targetId].sort((a, b) => a.localeCompare(b, "en"));
      const key = `${endpointA}|${endpointB}`;
      if (!linkMap.has(key)) {
        linkMap.set(key, {
          id: `node-link:${key}`,
          from_id: endpointA,
          to_id: endpointB,
          count: 0,
          from_to_count: 0,
          to_from_count: 0,
          cross_project: false,
          last_ts: 0,
        });
      }
      const link = linkMap.get(key);
      link.count += 1;
      if (sourceId === endpointA) link.from_to_count += 1;
      else link.to_from_count += 1;
      link.last_ts = Math.max(link.last_ts, Number(pair.ts || 0));
    });
    const links = Array.from(linkMap.values()).sort((a, b) => b.count - a.count || a.from_id.localeCompare(b.from_id, "en"));
    const peerMap = new Map();
    const commCountBySession = new Map();
    links.forEach((link) => {
      peerMap.set(link.from_id, Number(peerMap.get(link.from_id) || 0) + 1);
      peerMap.set(link.to_id, Number(peerMap.get(link.to_id) || 0) + 1);
      commCountBySession.set(link.from_id, Number(commCountBySession.get(link.from_id) || 0) + Number(link.count || 0));
      commCountBySession.set(link.to_id, Number(commCountBySession.get(link.to_id) || 0) + Number(link.count || 0));
    });
    return { links, messageCountBySession, peerMap, commCountBySession };
  }

  function buildPlatformProjectGroupsAndNodes(projects, sessions, metricsByProject) {
    const groups = [];
    const nodes = [];
    const orderedProjects = sortProjects(projects);
    const maxRowWidth = 12800;
    const startX = 520;
    const startY = 340;
    const colGap = 360;
    const rowGap = 320;
    const shellWidth = 620;
    const shellHeight = 356;
    const usableRowWidth = Math.max(2400, maxRowWidth - startX * 2);
    const shellItems = orderedProjects.map((project, index) => ({
      project,
      index,
      spec: { width: shellWidth, height: shellHeight },
    }));
    const lanes = buildProjectRowLanes(shellItems, usableRowWidth, colGap);
    let cursorY = startY;

    lanes.forEach((lane) => {
      let cursorX = startX + Math.max(0, Math.round((usableRowWidth - Number(lane.width || 0)) / 2));
      const laneHeight = lane.items.reduce((max, item) => Math.max(max, Number(item.spec && item.spec.height) || shellHeight), shellHeight);
      lane.items.forEach(({ project, index }) => {
      const projectId = safeText(project.project_id);
      const groupId = `group:platform:project:${projectId}`;
      const groupX = cursorX;
      const groupY = cursorY;
      cursorX += shellWidth + colGap;
      const group = {
        id: groupId,
        label: safeText(project.project_name || project.name || project.project_id, projectId),
        rowKind: "other",
        accent: projectAccent(project),
        x: groupX,
        y: groupY,
        w: shellWidth,
        h: shellHeight,
        z: index,
        sessionIds: [`project::${projectId}`],
        kind: "project-shell",
        project_id: projectId,
      };
      groups.push(group);
      const totals = (project && project.totals && typeof project.totals === "object") ? project.totals : {};
      const metrics = metricsByProject.get(projectId) || { session_count: 0, line_count: 0, cross_count: 0, message_count: 0, peer_count: 0 };
      nodes.push({
        id: `project::${projectId}`,
        session_id: `project::${projectId}`,
        group_id: group.id,
        x: group.x + 36,
        y: group.y + 104,
        w: 412,
        h: 160,
        alias: safeText(project.project_name || project.name || project.project_id, projectId),
        role: `${Number(metrics.session_count || totals.channels || 0)} Agent · ${Number(totals.active || 0)} 活跃`,
        channel_name: "平台项目",
        status: projectStatusFromTotals(totals),
        accent: group.accent,
        kind: "project",
        project_id: projectId,
        metric_items: [
          { label: "Agent", value: Number(metrics.session_count || 0) },
          { label: "沟通线", value: Number(metrics.line_count || 0) },
          { label: "沟通量", value: Number(metrics.cross_count || 0) },
          { label: "进行中", value: Number(totals.in_progress || 0) },
        ],
        project_summary: {
          source: safeText(project.source_kind || project.sourceKind || "real"),
          description: safeText(project.description),
          totals,
          metrics,
        },
      });
      });
      cursorY += laneHeight + rowGap;
    });
    return { groups, nodes: attachTopUserNode(groups, nodes), channelSections: [] };
  }

  function buildRunsUrl(projectId = STATE.projectId, limit = 200) {
    const params = new URLSearchParams();
    const pid = safeText(projectId);
    if (pid) params.set("projectId", pid);
    params.set("limit", String(Math.max(1, Math.min(200, Number(limit) || 200))));
    params.set("payloadMode", "light");
    const range = currentWindowRange();
    if (range.startMs) params.set("afterCreatedAt", new Date(range.startMs).toISOString());
    if (range.endMs) params.set("beforeCreatedAt", new Date(range.endMs).toISOString());
    return `/api/codex/runs?${params.toString()}`;
  }

  function buildPlatformRunsPageUrl({ limit = PLATFORM_RUNS_PAGE_LIMIT, beforeCreatedAt = "", afterCreatedAt = "" } = {}) {
    const params = new URLSearchParams();
    params.set("limit", String(Math.max(1, Math.min(PLATFORM_RUNS_PAGE_LIMIT, Number(limit) || PLATFORM_RUNS_PAGE_LIMIT))));
    params.set("payloadMode", "light");
    const range = currentWindowRange();
    const afterIso = safeText(afterCreatedAt) || (range.startMs ? new Date(range.startMs).toISOString() : "");
    const beforeIso = safeText(beforeCreatedAt) || (range.endMs ? new Date(range.endMs).toISOString() : "");
    if (afterIso) params.set("afterCreatedAt", afterIso);
    if (beforeIso) params.set("beforeCreatedAt", beforeIso);
    return `/api/codex/runs?${params.toString()}`;
  }

  function filterRunsByWindow(runs) {
    const range = currentWindowRange();
    return (runs || []).filter((run) => {
      const ts = dateMs(run.created_at);
      return ts >= range.startMs && ts <= range.endMs;
    }).sort((a, b) => dateMs(a.created_at) - dateMs(b.created_at));
  }

  function filteredPlatformCommLinks() {
    const scope = safeText(STATE.platformCommScope, "all");
    return filteredCommLinks(STATE.platformCommLinks || []).filter((link) => {
      if (scope === "cross") return Boolean(link.cross_project);
      if (scope === "high") return Number(link.count || 0) >= PLATFORM_HIGH_FREQ_COUNT;
      return true;
    });
  }

  function filteredProjectCommLinks() {
    return filteredCommLinks(STATE.commLinks || []);
  }

  function currentViewportRect() {
    if (!dom.stageWrap) return null;
    if (dom.stageWrap.hidden || dom.stageWrap.clientWidth < 24 || dom.stageWrap.clientHeight < 24) return null;
    return {
      left: dom.stageWrap.scrollLeft / STATE.zoom,
      top: dom.stageWrap.scrollTop / STATE.zoom,
      right: (dom.stageWrap.scrollLeft + dom.stageWrap.clientWidth) / STATE.zoom,
      bottom: (dom.stageWrap.scrollTop + dom.stageWrap.clientHeight) / STATE.zoom,
    };
  }

  function lineNearViewport(start, end, viewport, padding = 260) {
    if (!viewport) return true;
    const minX = Math.min(start.x, end.x);
    const maxX = Math.max(start.x, end.x);
    const minY = Math.min(start.y, end.y);
    const maxY = Math.max(start.y, end.y);
    return !(
      maxX < viewport.left - padding
      || minX > viewport.right + padding
      || maxY < viewport.top - padding
      || minY > viewport.bottom + padding
    );
  }

  function nodeCommunicationStats(sessionId, links = STATE.commLinks) {
    return (Array.isArray(links) ? links : []).reduce((acc, link) => {
      const endpointA = safeText(link.from_id);
      const endpointB = safeText(link.to_id);
      if (sessionId !== endpointA && sessionId !== endpointB) return acc;
      acc.peer_count += 1;
      acc.total_count += Number(link.count || 0);
      if (sessionId === endpointA) {
        acc.outbound_count += Number(link.from_to_count || 0);
        acc.inbound_count += Number(link.to_from_count || 0);
      } else {
        acc.outbound_count += Number(link.to_from_count || 0);
        acc.inbound_count += Number(link.from_to_count || 0);
      }
      return acc;
    }, { peer_count: 0, total_count: 0, outbound_count: 0, inbound_count: 0 });
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

  function buildProjectLayoutSnapshot(projectId, sessions) {
    const scopedStore = loadLayoutStoreByKey(projectLayoutStorageKey(projectId));
    const { groups, nodes } = computeGroupsAndNodes(sessions, scopedStore, { includeUserNode: false });
    return {
      project_id: safeText(projectId),
      groups,
      nodes,
      bounds: computeBoardBounds(groups, nodes),
      zoom: Math.max(0.55, Math.min(1.6, Number(scopedStore.zoom) || 1)),
    };
  }

  function platformShellCount() {
    return STATE.groups.filter((group) => safeText(group.kind) === "project-shell").length;
  }

  function platformLayoutGroupCount() {
    return STATE.groups.filter((group) => safeText(group.kind) === "project-layout-group").length;
  }

  function buildPlatformComposedAgentLayout(projects, sessions, messageCountBySession, peerMap, commCountBySession) {
    const groups = [];
    const nodes = [];
    const layoutGroups = [];
    const orderedProjects = sortProjects(projects);
    const maxRowWidth = 15600;
    const startX = 620;
    const startY = 420;
    const colGap = 680;
    const rowGap = 640;
    const shellPadX = 180;
    const shellPadY = 120;
    const shellHeaderH = 124;
    const usableRowWidth = Math.max(3200, maxRowWidth - startX * 2);
    const shellItems = orderedProjects.map((project, index) => {
      const projectId = safeText(project.project_id);
      const projectSessions = (sessions || []).filter((session) => safeText(session.project_id) === projectId);
      const snapshot = buildProjectLayoutSnapshot(projectId, projectSessions);
      const bounds = snapshot.bounds && snapshot.bounds.width >= 0
        ? snapshot.bounds
        : computeBoardBounds(snapshot.groups, snapshot.nodes);
      const rawWidth = Math.max(480, Number(bounds && bounds.width) || 0);
      const rawHeight = Math.max(320, Number(bounds && bounds.height) || 0);
      const baseScale = Math.max(
        0.22,
        Math.min(
          PLATFORM_PROJECT_LAYOUT_BASE_SCALE,
          PLATFORM_PROJECT_LAYOUT_MAX_WIDTH / rawWidth,
          PLATFORM_PROJECT_LAYOUT_MAX_HEIGHT / rawHeight,
        ),
      ) * PLATFORM_PROJECT_LAYOUT_COMPACT_SCALE;
      const mappedScale = Math.max(0.34, baseScale);
      const shellWidth = Math.ceil(rawWidth * mappedScale + shellPadX * 2);
      const shellHeight = Math.ceil(rawHeight * mappedScale + shellHeaderH + shellPadY * 2);
      return {
        project,
        index,
        projectId,
        projectSessions,
        snapshot,
        bounds,
        scale: mappedScale,
        shellWidth,
        shellHeight,
        spec: { width: shellWidth, height: shellHeight },
      };
    });
    const lanes = buildProjectRowLanes(shellItems, usableRowWidth, colGap);
    let cursorY = startY;

    lanes.forEach((lane) => {
      let cursorX = startX + Math.max(0, Math.round((usableRowWidth - Number(lane.width || 0)) / 2));
      const laneHeight = lane.items.reduce((max, item) => Math.max(max, Number(item.shellHeight) || 0), 0);
      lane.items.forEach((item) => {
      const { project, index, projectId, projectSessions, snapshot, bounds, scale, shellWidth, shellHeight } = item;
      const shellGroup = {
        id: `group:platform:project:${projectId}`,
        label: safeText(project.project_name || project.name || project.project_id, projectId),
        rowKind: "other",
        accent: projectAccent(project),
        x: cursorX,
        y: cursorY,
        w: shellWidth,
        h: shellHeight,
        z: index * 100,
        sessionIds: projectSessions.map((session) => session.session_id),
        kind: "project-shell",
        project_id: projectId,
        readonly: true,
      };
      groups.push(shellGroup);
      cursorX += shellWidth + colGap;

      const offsetX = shellGroup.x + shellPadX - Number(bounds && bounds.minX || 0) * scale;
      const offsetY = shellGroup.y + shellHeaderH + shellPadY - Number(bounds && bounds.minY || 0) * scale;

      snapshot.groups.forEach((group, groupIndex) => {
        const mapped = {
          ...group,
          id: `platform:${projectId}:${group.id}`,
          parent_group_id: shellGroup.id,
          x: Math.round(offsetX + Number(group.x || 0) * scale),
          y: Math.round(offsetY + Number(group.y || 0) * scale),
          w: Math.max(140, Math.round(Number(group.w || 0) * scale)),
          h: Math.max(96, Math.round(Number(group.h || 0) * scale)),
          z: shellGroup.z + 1 + groupIndex,
          kind: "project-layout-group",
          project_id: projectId,
          readonly: true,
          accent: safeText(group.accent) || shellGroup.accent,
        };
        groups.push(mapped);
        layoutGroups.push(mapped);
      });

      snapshot.nodes.forEach((node) => {
        const fallbackSize = compactNodeCardSize(node.alias, "project");
        const mappedWidth = Math.max(96, Math.min(188, Math.round(Number(node.w || fallbackSize.w) * scale * 0.94)));
        const mappedHeight = Math.max(46, Math.min(84, Math.round(Number(node.h || fallbackSize.h) * scale * 0.94)));
        nodes.push({
          ...node,
          group_id: node.group_id ? `platform:${projectId}:${node.group_id}` : shellGroup.id,
          x: Math.round(offsetX + Number(node.x || 0) * scale),
          y: Math.round(offsetY + Number(node.y || 0) * scale),
          w: mappedWidth,
          h: mappedHeight,
          project_id: projectId,
          readonly: true,
          metric_items: [
            { label: "消息", value: Number(messageCountBySession.get(node.session_id) || 0) },
            { label: "对象", value: Number(peerMap.get(node.session_id) || 0) },
            { label: "往来", value: Number(commCountBySession.get(node.session_id) || 0) },
          ],
        });
      });
    });
      cursorY += laneHeight + rowGap;
    });

    groups.sort((a, b) => a.z - b.z);
    return { groups, nodes: attachTopUserNode(groups, nodes), layoutGroups };
  }

  function showHoverTooltip(contentHtml, clientX, clientY) {
    if (!dom.bubbleTooltip) return;
    dom.bubbleTooltip.innerHTML = contentHtml;
    dom.bubbleTooltip.style.left = `${Math.min(window.innerWidth - 300, clientX + 14)}px`;
    dom.bubbleTooltip.style.top = `${Math.min(window.innerHeight - 90, clientY + 14)}px`;
    dom.bubbleTooltip.classList.add("visible");
  }

  function hideHoverTooltip() {
    dom.bubbleTooltip?.classList.remove("visible");
  }

  function communicationDetailHtml(link, fromLabel, toLabel) {
    const total = Number(link.count || 0);
    const fromTo = Number(link.from_to_count || 0);
    const toFrom = Number(link.to_from_count || 0);
    return `
      <div>${escapeHtml(fromLabel)} ↔ ${escapeHtml(toLabel)}</div>
      <div class="meta">总量 ${total} · ${escapeHtml(fromLabel)}→${escapeHtml(toLabel)} ${fromTo} · ${escapeHtml(toLabel)}→${escapeHtml(fromLabel)} ${toFrom}</div>
    `;
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
    const toggleVisible = (el, visible) => {
      if (!el) return;
      el.classList.toggle("is-hidden", !visible);
      el.hidden = !visible;
    };
    toggleVisible(dom.platformModeTabsWrap, isPlatformMode());
    toggleVisible(dom.platformProjectFilterWrap, isPlatformMode());
    toggleVisible(dom.platformCommScopeFilters, isPlatformMode());
    toggleVisible(dom.commTypeFilters, true);
    toggleVisible(dom.platformCommCountFilters, true);
    if (dom.rosterSectionTitle) {
      dom.rosterSectionTitle.textContent = isPlatformMode()
        ? (STATE.platformLayoutMode === "project" ? "项目节点池" : "通道节点池（项目级布局拼接）")
        : "Agent 节点池";
    }
    document.querySelectorAll(".row-label").forEach((label) => {
      label.hidden = isPlatformMode();
    });
    if (dom.boardMeta) {
      dom.boardMeta.textContent = isPlatformMode()
        ? `平台组织战略 · ${STATE.platformLayoutMode === "agent" ? "Agent模式（项目壳 + 项目级布局拼接）" : "项目模式"} · ${currentWindowLabel()}`
        : `${STATE.projectName || STATE.projectId} · ${STATE.channelHint ? `通道 ${STATE.channelHint}` : "单项目组织视图"} · ${currentWindowLabel()}`;
    }
    if (dom.summaryMeta) {
      const visiblePlatformLinks = filteredCommLinks(STATE.platformCommLinks || []);
      const filteredPlatformLinks = filteredPlatformCommLinks();
      const filteredProjectLinks = filteredProjectCommLinks();
      const activeProjectCount = visiblePlatformProjects().length;
      const totalProjectCount = platformProjectIds().length;
      dom.summaryMeta.textContent = isPlatformMode()
        ? `项目 ${activeProjectCount}/${totalProjectCount} · ${STATE.platformLayoutMode === "agent" ? `Agent ${visibleAgentNodeCount()} + 用户` : `项目节点 ${STATE.nodes.length}`} · 沟通线 ${filteredPlatformLinks.length}/${visiblePlatformLinks.length} · 总量 ${totalCommCount(filteredPlatformLinks)}${safeText(STATE.platformCommScope, "all") !== "all" ? ` · 范围 ${platformCommScopeSummaryLabel()}` : ""}${STATE.commLineCountMin > 0 ? ` · 数量 ${STATE.commLineCountMin}+` : ""}`
        : `背景板 ${STATE.groups.length} · Agent ${visibleAgentNodeCount()} + 用户 · 沟通线 ${filteredProjectLinks.length} · 总量 ${totalCommCount(filteredProjectLinks)}${STATE.commLineCountMin > 0 ? ` · 数量 ${STATE.commLineCountMin}+` : ""}`;
    }
    if (dom.platformProjectFilterBtn && isPlatformMode()) {
      const activeProjectCount = visiblePlatformProjects().length;
      const totalProjectCount = platformProjectIds().length;
      dom.platformProjectFilterBtn.textContent = totalProjectCount && activeProjectCount !== totalProjectCount
        ? `项目筛选 ${activeProjectCount}/${totalProjectCount}`
        : "项目筛选";
    }
    if (dom.platformProjectFilterPanel) {
      dom.platformProjectFilterPanel.hidden = !STATE.platformProjectFilterOpen || !isPlatformMode();
    }
    dom.platformModeButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.platformLayout === STATE.platformLayoutMode);
    });
    dom.platformScopeButtons.forEach((button) => {
      button.classList.toggle("is-active", safeText(button.dataset.commScope, "all") === STATE.platformCommScope);
    });
    dom.commTypeButtons.forEach((button) => {
      const kind = safeText(button.dataset.commKind);
      button.classList.toggle("is-active", STATE.commVisibility[kind] !== false);
    });
    dom.platformCountButtons.forEach((button) => {
      button.classList.toggle("is-active", Number(button.dataset.commCountMin || 0) === Number(STATE.commLineCountMin || 0));
    });
    syncTimeControls();
    renderPlatformProjectFilterPanel();
  }

  function renderRowLabels() {
    const rowMeta = STATE.projectRowLayout || {};
    Object.entries(ROWS).forEach(([rowKind, config]) => {
      const label = document.querySelector(`.row-${rowKind}`);
      if (!label) return;
      if (isPlatformMode()) {
        label.hidden = true;
        return;
      }
      const meta = rowMeta[rowKind] || {};
      label.hidden = Boolean(meta.empty);
      label.textContent = safeText(config.label);
      if (!meta.empty && Number.isFinite(Number(meta.labelY))) {
        label.style.top = `${Math.round(Number(meta.labelY))}px`;
      } else {
        label.style.top = `${Math.round(Number(config.y || 0) - 50)}px`;
      }
    });
  }

  function renderPlatformProjectFilterPanel() {
    if (!dom.platformProjectFilterList || !dom.platformProjectFilterSummary) return;
    if (!isPlatformMode()) {
      dom.platformProjectFilterList.innerHTML = "";
      dom.platformProjectFilterSummary.textContent = "";
      return;
    }
    normalizePlatformProjectSelection();
    const projects = sortProjects(STATE.platformProjects);
    const draft = new Set((STATE.platformProjectFilterDraft || []).map((item) => safeText(item)).filter(Boolean));
    dom.platformProjectFilterSummary.textContent = `已选 ${draft.size} / ${projects.length}`;
    dom.platformProjectFilterList.innerHTML = "";
    projects.forEach((project) => {
      const projectId = safeText(project.project_id);
      const row = document.createElement("label");
      row.className = "project-filter-item";
      row.innerHTML = `
        <input type="checkbox" value="${escapeHtml(projectId)}" ${draft.has(projectId) ? "checked" : ""} />
        <div class="project-filter-item-main">
          <div class="project-filter-item-name">${escapeHtml(firstText([project.project_name, project.name], projectId))}</div>
          <div class="project-filter-item-meta">${escapeHtml(projectId)}</div>
        </div>
      `;
      const input = row.querySelector("input");
      input?.addEventListener("change", () => {
        const next = new Set((STATE.platformProjectFilterDraft || []).map((item) => safeText(item)).filter(Boolean));
        if (input.checked) next.add(projectId);
        else next.delete(projectId);
        STATE.platformProjectFilterDraft = projects.map((item) => safeText(item.project_id)).filter((id) => next.has(id));
        STATE.platformProjectFilterDraftDirty = true;
        dom.platformProjectFilterSummary.textContent = `已选 ${STATE.platformProjectFilterDraft.length} / ${projects.length}`;
      });
      dom.platformProjectFilterList.appendChild(row);
    });
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
      const kind = safeText(group.kind);
      const readonly = Boolean(isPlatformMode() && group.readonly);
      box.className = `group-box${group.id === STATE.selectedGroupId ? " selected" : ""}${activity.active ? " active" : ""}${activity.peak ? " peak" : ""}${kind === "project-shell" ? " project-shell" : ""}${kind === "project-layout-group" ? " layout-group" : ""}${readonly ? " readonly" : ""}`;
      box.style.left = `${group.x}px`;
      box.style.top = `${group.y}px`;
      box.style.width = `${group.w}px`;
      box.style.height = `${group.h}px`;
      box.style.setProperty("--group-soft", rgbaFromHex(group.accent, 0.1));
      box.style.setProperty("--group-fade", rgbaFromHex(group.accent, 0.05));
      box.addEventListener("click", () => {
        STATE.selectedGroupId = group.id;
        STATE.selectedSessionId = "";
        STATE.selectedPlatformCommLinkId = "";
        renderAll();
      });
      dom.groupsLayer.appendChild(box);

      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `group-chip${group.id === STATE.selectedGroupId ? " selected" : ""}${activity.active ? " active" : ""}${activity.peak ? " peak" : ""}${readonly ? " readonly" : ""}`;
      chip.style.left = `${group.x + 14}px`;
      chip.style.top = `${group.y + 14}px`;
      const groupCount = Array.isArray(group.sessionIds) ? group.sessionIds.length : 0;
      chip.innerHTML = `<span>${escapeHtml(group.label)}</span><span class="hint">${readonly ? "只读查看" : `${groupCount} 个Agent`}</span>`;
      if (!readonly) {
        chip.addEventListener("pointerdown", (event) => {
          STATE.selectedGroupId = group.id;
          STATE.selectedSessionId = "";
          STATE.selectedPlatformCommLinkId = "";
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
      } else {
        chip.addEventListener("click", () => {
          STATE.selectedGroupId = group.id;
          STATE.selectedSessionId = "";
          STATE.selectedPlatformCommLinkId = "";
          renderAll();
        });
      }
      dom.groupChipLayer.appendChild(chip);

      if (!readonly && group.id === STATE.selectedGroupId) {
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
    return avatarMeta(node).text;
  }

  function renderNodes() {
    dom.nodesLayer.innerHTML = "";
    STATE.nodes.forEach((node) => {
      const el = document.createElement("div");
      const isPlatformNode = isPlatformMode();
      const nodeKind = safeText(node.kind || (isPlatformNode ? "agent" : ""), "agent");
      const readonly = Boolean(isPlatformNode && node.readonly);
      const compactAgentNode = nodeKind !== "project";
      const avatar = avatarMeta(node);
      el.className = `node${node.session_id === STATE.selectedSessionId ? " selected" : ""}${compactAgentNode ? " compact-name-only" : ""}${isPlatformNode ? ` platform-node ${nodeKind === "project" ? "project-node" : "agent-node"}` : ""}${readonly ? " readonly" : ""}`;
      el.dataset.sessionId = node.session_id;
      el.style.left = `${node.x}px`;
      el.style.top = `${node.y}px`;
      el.style.width = `${Number(node.w || CARD_WIDTH)}px`;
      el.style.minHeight = `${Number(node.h || CARD_HEIGHT)}px`;
      el.style.setProperty("--avatar-a", avatar.c1 || node.accent);
      el.style.setProperty("--avatar-b", avatar.c2 || rgbaFromHex(node.accent, 0.68));
      const metricItems = Array.isArray(node.metric_items) ? node.metric_items : [];
      const showPlatformStats = !(isPlatformNode && STATE.platformLayoutMode === "agent" && nodeKind !== "project");
      const platformStats = showPlatformStats
        ? (metricItems.length
          ? `<div class="platform-stat-grid">${metricItems.map((item) => `<div class="platform-stat-card"><span class="platform-stat-label">${escapeHtml(safeText(item.label))}</span><span class="platform-stat-value">${escapeHtml(String(item.value == null ? 0 : item.value))}</span></div>`).join("")}</div>`
          : '<div class="empty-platform-hint">当前时间窗口暂无通讯统计。</div>')
        : "";
      const compactHead = `
        <div class="compact-head">
          <div class="avatar${avatar.fallback ? " is-fallback" : ""}" title="${escapeHtml(avatar.title)}">${escapeHtml(nodeAvatar(node))}</div>
          <div class="compact-title" title="${escapeHtml(node.alias)}">${escapeHtml(node.alias)}</div>
        </div>
      `;
      const sharedNodeBody = isPlatformNode
        ? (compactAgentNode
          ? compactHead
          : `
          <div class="node-head">
            <div class="avatar${avatar.fallback ? " is-fallback" : ""}" title="${escapeHtml(avatar.title)}">${escapeHtml(nodeAvatar(node))}</div>
            <div>
              <div class="node-title">${escapeHtml(node.alias)}</div>
              <div class="node-sub">${escapeHtml(node.role)}</div>
            </div>
          </div>
          ${platformStats || '<div class="empty-platform-hint">当前时间窗口暂无统计。</div>'}
          `)
        : "";
      el.innerHTML = `
        ${isPlatformNode ? sharedNodeBody : compactHead}
      `;
      if (!readonly) {
        el.addEventListener("pointerdown", (event) => {
          if (event.button !== 0) return;
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
      }
      el.addEventListener("click", () => {
        STATE.selectedSessionId = node.session_id;
        STATE.selectedGroupId = "";
        STATE.selectedPlatformCommLinkId = "";
        renderAll();
      });
      dom.nodesLayer.appendChild(el);
    });
  }

  function nodeCenter(node) {
    if (!node) return null;
    return {
      x: Number(node.x || 0) + Number(node.w || CARD_WIDTH) / 2,
      y: Number(node.y || 0) + Number(node.h || CARD_HEIGHT) / 2,
    };
  }

  function nodeLinkAnchor(fromNode, toNode) {
    if (!fromNode || !toNode) return null;
    const fromCenter = nodeCenter(fromNode);
    const toCenter = nodeCenter(toNode);
    if (!fromCenter || !toCenter) return null;
    const dx = toCenter.x - fromCenter.x;
    const dy = toCenter.y - fromCenter.y;
    if (Math.abs(dx) >= Math.abs(dy)) {
      return nodeAnchor(fromNode, dx >= 0 ? "right" : "left");
    }
    return nodeAnchor(fromNode, dy >= 0 ? "bottom" : "top");
  }

  function communicationTone(count) {
    if (count >= 10) return "strong";
    if (count >= 5) return "mid";
    return "soft";
  }

  function communicationStrokeWidth(count, mode = "project") {
    const base = mode === "platform" ? 4.2 : 3.2;
    const max = mode === "platform" ? 10.8 : 8.4;
    return Math.min(max, base + Math.log2(Math.max(1, Number(count || 1))));
  }

  function communicationEndpointLabels(link) {
    const fromNode = nodeBySessionId(link.from_id);
    const toNode = nodeBySessionId(link.to_id);
    return {
      fromNode,
      toNode,
      fromLabel: safeText(fromNode && fromNode.alias, link.from_id),
      toLabel: safeText(toNode && toNode.alias, link.to_id),
    };
  }

  function bindCommunicationHover(target, link, labels) {
    target.addEventListener("mouseenter", (event) => {
      showHoverTooltip(communicationDetailHtml(link, labels.fromLabel, labels.toLabel), event.clientX, event.clientY);
    });
    target.addEventListener("mousemove", (event) => {
      showHoverTooltip(communicationDetailHtml(link, labels.fromLabel, labels.toLabel), event.clientX, event.clientY);
    });
    target.addEventListener("mouseleave", hideHoverTooltip);
  }

  function drawAggregatedCommLink(link, index, viewport, mode = "project") {
    const { fromNode, toNode, fromLabel, toLabel } = communicationEndpointLabels(link);
    if (!fromNode || !toNode) return;
    const start = nodeLinkAnchor(fromNode, toNode);
    const end = nodeLinkAnchor(toNode, fromNode);
    if (!start || !end) return;
    const tone = communicationTone(Number(link.count || 0));
    const userLink = safeText(link.from_id) === USER_NODE_ID || safeText(link.to_id) === USER_NODE_ID;
    const geometry = communicationGeometry(start, end, link, mode);
    const selectLink = (event) => {
      event.stopPropagation();
      STATE.selectedPlatformCommLinkId = link.id;
      STATE.selectedGroupId = "";
      STATE.selectedSessionId = "";
      renderAll();
    };
    const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
    hit.setAttribute("d", geometry.path);
    hit.setAttribute("class", "relation-hit");
    hit.dataset.commId = link.id;
    hit.addEventListener("click", selectLink);
    bindCommunicationHover(hit, link, { fromLabel, toLabel });
    dom.linesSvg.appendChild(hit);

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", geometry.path);
    path.setAttribute("class", `comm-line ${mode} ${tone}${userLink ? " user-link" : ""}${link.cross_project ? " cross-project" : ""}${link.id === STATE.selectedPlatformCommLinkId ? " selected" : ""}`);
    path.style.setProperty("--comm-width", String(communicationStrokeWidth(link.count, mode) + (userLink ? (mode === "platform" ? 1.8 : 1.2) : 0)));
    path.addEventListener("click", selectLink);
    bindCommunicationHover(path, link, { fromLabel, toLabel });
    dom.linesSvg.appendChild(path);

    if (Number(link.count || 0) > 0) {
      const labelPoint = geometry.labelPoint;
      const labelText = String(Number(link.count || 0));
      const badgeWidth = Math.max(24, 16 + labelText.length * 8);
      const badge = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      badge.setAttribute("class", `comm-badge${userLink ? " user-link" : ""}${link.cross_project ? " cross-project" : ""}${link.id === STATE.selectedPlatformCommLinkId ? " selected" : ""}`);
      badge.setAttribute("x", String(Math.round(labelPoint.x - badgeWidth / 2)));
      badge.setAttribute("y", String(Math.round(labelPoint.y - 11)));
      badge.setAttribute("width", String(badgeWidth));
      badge.setAttribute("height", "22");
      badge.setAttribute("rx", "11");
      badge.setAttribute("ry", "11");
      badge.addEventListener("click", selectLink);
      bindCommunicationHover(badge, link, { fromLabel, toLabel });
      dom.linesSvg.appendChild(badge);
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("class", `comm-label ${tone}${userLink ? " user-link" : ""}${link.cross_project ? " cross-project" : ""}${link.id === STATE.selectedPlatformCommLinkId ? " selected" : ""}`);
      label.setAttribute("x", String(labelPoint.x));
      label.setAttribute("y", String(labelPoint.y + 1));
      label.setAttribute("text-anchor", "middle");
      label.textContent = labelText;
      label.addEventListener("click", selectLink);
      bindCommunicationHover(label, link, { fromLabel, toLabel });
      dom.linesSvg.appendChild(label);
    }
  }

  function renderLinks() {
    dom.linesSvg.innerHTML = "";
    if (isPlatformMode()) {
      const visibleLinks = filteredPlatformCommLinks()
        .slice()
        .sort((a, b) => {
          const aUser = isUserCommLink(a);
          const bUser = isUserCommLink(b);
          if (aUser !== bUser) return aUser ? 1 : -1;
          return Number(a.count || 0) - Number(b.count || 0) || safeText(a.id).localeCompare(safeText(b.id), "en");
        });
      const viewport = currentViewportRect();
      visibleLinks.forEach((link, index) => drawAggregatedCommLink(link, index, viewport, "platform"));
      return;
    }
    const viewport = currentViewportRect();
    filteredProjectCommLinks()
      .slice()
      .sort((a, b) => {
        const aUser = isUserCommLink(a);
        const bUser = isUserCommLink(b);
        if (aUser !== bUser) return aUser ? 1 : -1;
        return Number(a.count || 0) - Number(b.count || 0) || safeText(a.id).localeCompare(safeText(b.id), "en");
      })
      .forEach((link, index) => drawAggregatedCommLink(link, index, viewport, "project"));
  }

  function renderGroupList() {
    dom.groupList.innerHTML = "";
    const ordered = (isPlatformMode()
      ? STATE.groups.filter((group) => safeText(group.kind) === "project-shell")
      : STATE.groups
    ).sort((a, b) => b.z - a.z);
    if (!ordered.length) {
      dom.groupList.innerHTML = '<div class="empty-state">当前项目暂无可展示背景板。</div>';
      return;
    }
    ordered.forEach((group) => {
      const item = document.createElement("div");
      item.className = "layer-item";
      item.draggable = !isPlatformMode();
      item.dataset.groupId = group.id;
      item.innerHTML = `
        <div class="layer-title">${escapeHtml(group.label)}</div>
        <div class="layer-meta">${Math.round(group.w)} × ${Math.round(group.h)} · ${Math.round(group.x)}, ${Math.round(group.y)}</div>
      `;
      item.addEventListener("click", () => {
        STATE.selectedGroupId = group.id;
        STATE.selectedSessionId = "";
        STATE.selectedPlatformCommLinkId = "";
        renderAll();
      });
      if (!isPlatformMode()) {
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
      }
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
        STATE.selectedPlatformCommLinkId = "";
        renderAll();
        centerOnNode(node);
      });
      dom.rosterList.appendChild(item);
    });
  }

  function renderDetail() {
    const group = STATE.groups.find((item) => item.id === STATE.selectedGroupId);
    const node = STATE.nodes.find((item) => item.session_id === STATE.selectedSessionId);
    const selectedCommLink = (isPlatformMode() ? STATE.platformCommLinks : STATE.commLinks || []).find((item) => item.id === STATE.selectedPlatformCommLinkId);
    if (group) {
      dom.detailTitle.textContent = group.label;
      const readonly = Boolean(isPlatformMode() && group.readonly);
      if (readonly) {
        dom.detailBody.innerHTML = `
          <div class="detail-grid">
            <div class="k">对象</div><div>${safeText(group.kind) === "project-shell" ? "项目外壳" : "项目内背景板"}</div>
            <div class="k">项目</div><div>${escapeHtml(group.project_id || "-")}</div>
            <div class="k">尺寸</div><div>${Math.round(group.w)} × ${Math.round(group.h)}</div>
            <div class="k">位置</div><div>${Math.round(group.x)}, ${Math.round(group.y)}</div>
            <div class="k">模式</div><div>只读拼接</div>
          </div>
          <div style="margin-top:14px;font-size:12px;color:var(--muted);">平台组织战略沿用项目级布局快照，平台页不允许直接修改项目内部背景板。</div>
        `;
        dom.detailPanel.classList.remove("collapsed");
        return;
      }
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
    if (selectedCommLink) {
      const { fromNode, toNode, fromLabel, toLabel } = communicationEndpointLabels(selectedCommLink);
      dom.detailTitle.textContent = "沟通线详情";
      dom.detailBody.innerHTML = `
        <div class="detail-grid">
          <div class="k">对象</div><div>${isPlatformMode() && STATE.platformLayoutMode === "project" ? "项目沟通线" : "Agent 沟通线"}</div>
          <div class="k">节点A</div><div>${escapeHtml(fromLabel)}</div>
          <div class="k">节点B</div><div>${escapeHtml(toLabel)}</div>
          <div class="k">沟通量</div><div>${Number(selectedCommLink.count || 0)}</div>
          <div class="k">${escapeHtml(fromLabel)} → ${escapeHtml(toLabel)}</div><div>${Number(selectedCommLink.from_to_count || 0)}</div>
          <div class="k">${escapeHtml(toLabel)} → ${escapeHtml(fromLabel)}</div><div>${Number(selectedCommLink.to_from_count || 0)}</div>
          <div class="k">类型</div><div>${isUserCommLink(selectedCommLink) ? "用户参与" : "Agent之间"}</div>
          <div class="k">范围</div><div>${selectedCommLink.cross_project ? "跨项目" : "项目内"}</div>
          ${isPlatformMode() ? `<div class="k">范围过滤</div><div>${escapeHtml(platformCommScopeLabel())}</div>` : ""}
          <div class="k">最近时间</div><div>${fmtDateTime(selectedCommLink.last_ts)}</div>
        </div>
      `;
      dom.detailPanel.classList.remove("collapsed");
      return;
    }
    if (node) {
      if (node.kind === "user") {
        dom.detailTitle.textContent = node.alias;
        const stats = nodeCommunicationStats(node.session_id, isPlatformMode() ? filteredPlatformCommLinks() : filteredProjectCommLinks());
        dom.detailBody.innerHTML = `
          <div class="detail-grid">
            <div class="k">对象</div><div>用户</div>
            <div class="k">角色</div><div>消息发起者</div>
            <div class="k">沟通对象</div><div>${stats.peer_count}</div>
            <div class="k">往来总量</div><div>${stats.total_count}</div>
            <div class="k">发出</div><div>${stats.outbound_count}</div>
            <div class="k">收到</div><div>${stats.inbound_count}</div>
          </div>
          <div style="margin-top:14px;font-size:12px;color:var(--muted);">当前时间窗口内，所有由用户发起的消息都会汇总连到这个用户节点。</div>
        `;
        dom.detailPanel.classList.remove("collapsed");
        return;
      }
      if (node.kind === "project") {
        const summary = (node.project_summary && typeof node.project_summary === "object") ? node.project_summary : {};
        const totals = (summary.totals && typeof summary.totals === "object") ? summary.totals : {};
        const metrics = (summary.metrics && typeof summary.metrics === "object") ? summary.metrics : {};
        dom.detailTitle.textContent = node.alias;
        dom.detailBody.innerHTML = `
          <div class="detail-grid">
            <div class="k">对象</div><div>项目节点</div>
            <div class="k">项目ID</div><div>${escapeHtml(node.project_id || "-")}</div>
            <div class="k">来源</div><div>${escapeHtml(summary.source || "-")}</div>
            <div class="k">Agent数</div><div>${Number(metrics.session_count || 0)}</div>
            <div class="k">通道数</div><div>${Number(totals.channels || 0)}</div>
            <div class="k">活跃任务</div><div>${Number(totals.active || 0)}</div>
            <div class="k">进行中</div><div>${Number(totals.in_progress || 0)}</div>
            <div class="k">已完成</div><div>${Number(totals.done || 0)}</div>
            <div class="k">沟通线</div><div>${Number(metrics.line_count || 0)}</div>
            <div class="k">沟通量</div><div>${Number(metrics.cross_count || 0)}</div>
          </div>
          <div style="margin-top:14px;font-size:12px;color:var(--muted);">${escapeHtml(summary.description || "平台组织战略：项目外壳保留，内部再按视角切换项目摘要或 Agent 结构。")}</div>
        `;
        dom.detailPanel.classList.remove("collapsed");
        return;
      }
      if (isPlatformMode()) {
        const metricItems = Array.isArray(node.metric_items) ? node.metric_items : [];
        dom.detailTitle.textContent = node.alias;
        dom.detailBody.innerHTML = `
          <div class="detail-grid">
            <div class="k">对象</div><div>Agent</div>
            <div class="k">项目</div><div>${escapeHtml(node.project_id || "-")}</div>
            <div class="k">通道</div><div>${escapeHtml(node.channel_name)}</div>
            <div class="k">角色</div><div>${escapeHtml(node.role)}</div>
            <div class="k">状态</div><div>${escapeHtml(node.status)}</div>
            ${metricItems.map((item) => `<div class="k">${escapeHtml(String(item.label))}</div><div>${escapeHtml(String(item.value == null ? 0 : item.value))}</div>`).join("")}
          </div>
        `;
        dom.detailPanel.classList.remove("collapsed");
        return;
      }
      const stats = nodeCommunicationStats(node.session_id, filteredProjectCommLinks());
      dom.detailTitle.textContent = node.alias;
      dom.detailBody.innerHTML = `
        <div class="detail-grid">
          <div class="k">对象</div><div>Agent</div>
          <div class="k">通道</div><div>${escapeHtml(node.channel_name)}</div>
          <div class="k">角色</div><div>${escapeHtml(node.role)}</div>
          <div class="k">状态</div><div>${escapeHtml(node.status)}</div>
          <div class="k">消息总量</div><div>${Number((node.metric_items || []).find((item) => item.label === "消息")?.value || 0)}</div>
          <div class="k">沟通对象</div><div>${stats.peer_count}</div>
          <div class="k">往来总量</div><div>${stats.total_count}</div>
          <div class="k">发出</div><div>${stats.outbound_count}</div>
          <div class="k">收到</div><div>${stats.inbound_count}</div>
        </div>
        <div style="margin-top:14px;font-size:12px;color:var(--muted);">当前节点的沟通线已经按时间窗口聚合，不再逐条展示消息回放。</div>
      `;
      dom.detailPanel.classList.remove("collapsed");
      return;
    }
    dom.detailTitle.textContent = "未选中";
    dom.detailBody.innerHTML = '<div class="empty-state">点击背景板、Agent 卡片或关系线查看详情。</div>';
  }

  function renderAll() {
    if (dom.stageWrap && dom.stageWrap.hidden) dom.stageWrap.hidden = false;
    applyStageMetrics();
    renderHeader();
    renderRowLabels();
    renderGroups();
    renderNodes();
    renderLinks();
    renderGroupList();
    renderRosterList();
    renderDetail();
    renderMiniMap();
  }

  async function fetchPlatformRuns(projects) {
    const validProjectIds = new Set(
      sortProjects(projects)
        .map((project) => safeText(project.project_id))
        .filter(Boolean)
    );
    try {
      const dedup = new Map();
      const range = currentWindowRange();
      let beforeIso = range.endMs ? new Date(range.endMs).toISOString() : "";
      let pageCount = 0;
      let truncated = false;
      while (pageCount < PLATFORM_RUNS_MAX_PAGES && beforeIso) {
        const payload = await fetchJson(
          buildPlatformRunsPageUrl({
            limit: PLATFORM_RUNS_PAGE_LIMIT,
            beforeCreatedAt: beforeIso,
            afterCreatedAt: range.startMs ? new Date(range.startMs).toISOString() : "",
          }),
          { timeoutMs: 12000 }
        );
        const rawBatch = Array.isArray(payload && payload.runs) ? payload.runs : [];
        const batch = rawBatch
          .filter((item) => validProjectIds.has(safeText(item.project_id || item.projectId)));
        batch.forEach((item) => {
          const rid = safeText(item.run_id || item.id);
          if (rid && !dedup.has(rid)) dedup.set(rid, item);
        });
        pageCount += 1;
        if (rawBatch.length < PLATFORM_RUNS_PAGE_LIMIT) break;
        const oldestTs = rawBatch.reduce((min, item) => {
          const ts = dateMs(item.created_at || item.createdAt);
          return ts > 0 ? Math.min(min, ts) : min;
        }, Number.POSITIVE_INFINITY);
        if (!Number.isFinite(oldestTs) || oldestTs <= range.startMs) break;
        beforeIso = new Date(Math.max(range.startMs + 1, oldestTs - 1)).toISOString();
      }
      if (pageCount >= PLATFORM_RUNS_MAX_PAGES) truncated = true;
      const runs = Array.from(dedup.values())
        .sort((a, b) => dateMs(b.created_at || b.createdAt) - dateMs(a.created_at || a.createdAt));
      return {
        runs,
        failedProjects: [],
        truncated,
        pageCap: PLATFORM_RUNS_PAGE_LIMIT * PLATFORM_RUNS_MAX_PAGES,
      };
    } catch (error) {
      return {
        runs: [],
        failedProjects: [],
        truncated: false,
        pageCap: PLATFORM_RUNS_PAGE_LIMIT * PLATFORM_RUNS_MAX_PAGES,
        error,
      };
    }
  }

  function hydratePlatformView() {
    const projects = visiblePlatformProjects();
    if (!projects.length) {
      STATE.projectRowLayout = {};
      STATE.groups = [];
      STATE.nodes = [];
      STATE.commLinks = [];
      STATE.platformCommLinks = [];
      STATE.channelSections = [];
      STATE.selectedPlatformCommLinkId = "";
      renderAll();
      syncZoom();
      setStatus("当前没有选中项目，请在顶部项目筛选中至少选择一个项目。", "empty");
      return;
    }
    const projectIdSet = new Set(projects.map((item) => safeText(item.project_id)));
    const sessions = (STATE.sessions || []).filter((session) => projectIdSet.has(safeText(session.project_id)));
    const layoutStore = loadLayoutStore();
    STATE.zoom = Math.max(0.55, Math.min(1.6, Number(layoutStore.zoom) || 1));
    const aggregate = aggregatePlatformCommunication(STATE.platformLayoutMode, projects, sessions, STATE.runs);
    STATE.projectRowLayout = {};
    STATE.platformCommLinks = aggregate.links;
    STATE.commLinks = [];
    STATE.channelSections = [];
    STATE.selectedPlatformCommLinkId = "";
    if (STATE.platformLayoutMode === "agent") {
      const { groups, nodes, layoutGroups } = buildPlatformComposedAgentLayout(
        projects,
        sessions,
        aggregate.messageCountBySession || new Map(),
        aggregate.peerMap || new Map(),
        aggregate.commCountBySession || new Map(),
      );
      STATE.groups = groups;
      STATE.channelSections = layoutGroups;
      STATE.nodes = nodes;
      setStatus(`已进入平台 Agent 模式，加载 ${projects.length} 个项目外壳、${platformLayoutGroupCount()} 个项目内背景板、${visibleAgentNodeCount()} 个 Agent 节点、1 个用户节点、${STATE.platformCommLinks.length} 根沟通线。`, "ready");
    } else {
      const { groups, nodes } = buildPlatformProjectGroupsAndNodes(
        projects,
        sessions,
        aggregate.metricsByProject || new Map(),
      );
      STATE.groups = groups;
      STATE.nodes = nodes;
      setStatus(`已进入平台项目模式，加载 ${projects.length} 个项目外壳、${STATE.platformCommLinks.length} 根跨项目沟通线。`, "ready");
    }
    renderAll();
    syncZoom();
    restoreViewportForFreshLayout(layoutStore);
  }

  function applyProjectViewState(sessions, runs, sessionSource, options = {}) {
    STATE.sessions = Array.isArray(sessions) ? sessions.slice() : [];
    STATE.runs = Array.isArray(runs) ? runs.slice() : [];
    const { groups, nodes, rowLayout } = computeGroupsAndNodes(STATE.sessions);
    const aggregate = aggregateNodeCommunicationLinks(nodes, STATE.runs);
    STATE.groups = groups;
    STATE.projectRowLayout = rowLayout || {};
    STATE.nodes = nodes.map((node) => ({
      ...node,
      ...compactNodeCardSize(node.alias, "project"),
      metric_items: [
        { label: "消息", value: Number(aggregate.messageCountBySession.get(node.session_id) || 0) },
        { label: "对象", value: Number(aggregate.peerMap.get(node.session_id) || 0) },
        { label: "往来", value: Number(aggregate.commCountBySession.get(node.session_id) || 0) },
      ],
    }));
    const layoutStore = loadLayoutStore();
    STATE.zoom = Math.max(0.55, Math.min(1.6, Number(layoutStore.zoom) || 1));
    STATE.commLinks = aggregate.links;
    renderAll();
    syncZoom();
    if (!STATE.nodes.length) {
      setStatus("当前项目暂无会话数据，保持只读空态。", "empty");
      return;
    }
    const note = safeText(options.note);
    setStatus(
      `已加载 ${visibleAgentNodeCount()} 个 Agent、1 个用户节点、${STATE.commLinks.length} 根聚合沟通线 · ${safeText(sessionSource, "构建快照")}${note}`,
      "ready",
    );
  }

  async function loadData() {
    if (isPlatformMode()) {
      setStatus("正在加载平台组织战略...", "loading");
      try {
        const projects = projectCatalog().map((item) => ({
          ...item,
          project_id: safeText(item.project_id || item.id),
          project_name: firstText([item.project_name, item.name, item.id]),
          totals: (item.totals && typeof item.totals === "object") ? item.totals : {},
          source_kind: firstText([item.source_kind, item.sourceKind], "real"),
        })).filter((item) => item.project_id);
        STATE.platformProjects = sortProjects(projects);
        normalizePlatformProjectSelection();
        STATE.sessions = buildPlatformSessionsFromPayload(STATE.platformProjects);
        STATE.sharedAvatarStore = await fetchSharedAvatarStores(STATE.platformProjects.map((item) => item.project_id));
        STATE.runs = [];
        hydratePlatformView();
        setStatus("平台组织战略骨架已加载，正在补充沟通数据...", "loading");
        STATE.platformLoadToken += 1;
        const loadToken = STATE.platformLoadToken;
        const runsResult = await fetchPlatformRuns(STATE.platformProjects);
        if (loadToken !== STATE.platformLoadToken) return;
        STATE.runs = (Array.isArray(runsResult && runsResult.runs) ? runsResult.runs : [])
          .map(normalizeRun)
          .filter(Boolean);
        hydratePlatformView();
        if (runsResult && runsResult.error) {
          const current = safeText(dom.statusBanner && dom.statusBanner.textContent);
          setStatus(`${current || "平台组织战略骨架已加载。"} 沟通数据拉取失败：${safeText(runsResult.error && runsResult.error.message, "未知错误")}。`, "empty");
        } else if (runsResult && runsResult.truncated) {
          const current = safeText(dom.statusBanner && dom.statusBanner.textContent);
          setStatus(`${current || "平台组织战略已加载。"} 当前窗口沟通数据达到分页上限 ${Number(runsResult.pageCap || 0)} 条，统计可能被截断。`, "empty");
        }
      } catch (error) {
        setStatus(`组织战略加载失败：${safeText(error && error.message, "未知错误")}`, "error");
      }
      return;
    }
    if (!STATE.projectId) {
      setStatus("缺少项目参数，组织战略暂时无法加载。", "error");
      return;
    }
    setStatus(`正在加载 ${STATE.projectId} 的 Agent 组织战略...`, "loading");
    try {
      const payloadSessions = buildProjectSessionsFromPayload(STATE.projectId);
      if (payloadSessions.length) {
        applyProjectViewState(payloadSessions, [], "构建快照", { note: " · 正在补充实时会话" });
      }
      const [sessionsResult, runsResult, sharedAvatarStore] = await Promise.allSettled([
        fetchJson(`/api/sessions?project_id=${encodeURIComponent(STATE.projectId)}`, { timeoutMs: 45000 }),
        fetchJson(buildRunsUrl(), { timeoutMs: 12000 }),
        fetchSharedAvatarStore(STATE.projectId),
      ]);
      STATE.sharedAvatarStore = sharedAvatarStore.status === "fulfilled" ? sharedAvatarStore.value : emptyAvatarStore();
      const runtimeSessions = sessionsResult.status === "fulfilled"
        ? (Array.isArray(sessionsResult.value && sessionsResult.value.sessions) ? sessionsResult.value.sessions : []).map(normalizeSession).filter(Boolean)
        : [];
      const nextRuns = runsResult.status === "fulfilled"
        ? (Array.isArray(runsResult.value && runsResult.value.runs) ? runsResult.value.runs : []).map(normalizeRun).filter(Boolean)
        : [];
      const sessionSource = runtimeSessions.length ? "实时会话" : (payloadSessions.length ? "构建快照" : "空态");
      const runsHint = runsResult.status === "fulfilled" ? "" : " · runs接口超时";
      const sessionHint = sessionsResult.status === "fulfilled"
        ? (runtimeSessions.length > payloadSessions.length ? ` · 会话已从 ${payloadSessions.length} 升级到 ${runtimeSessions.length}` : "")
        : " · sessions接口超时已回退";
      applyProjectViewState(runtimeSessions.length ? runtimeSessions : payloadSessions, nextRuns, sessionSource, {
        note: `${sessionHint}${runsHint}`,
      });
    } catch (error) {
      setStatus(`组织战略加载失败：${safeText(error && error.message, "未知错误")}`, "error");
    }
  }

  function bindEvents() {
    dom.timeTabs.forEach((button) => {
      button.addEventListener("click", () => {
        const nextWindow = safeText(button.dataset.window, "1h");
        if (nextWindow === "custom") {
          const nextRange = currentWindowRange();
          if (!STATE.customRange.startMs || !STATE.customRange.endMs || STATE.customRange.endMs <= STATE.customRange.startMs) {
            STATE.customRange = {
              startMs: nextRange.startMs,
              endMs: nextRange.endMs,
            };
          }
          STATE.windowKey = "custom";
          syncTimeControls();
          setStatus("已切换到自定义时间范围，请设置开始和结束时间后点击应用。", "ready");
          return;
        }
        STATE.windowKey = nextWindow;
        syncTimeControls();
        loadData();
      });
    });
    dom.platformModeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const next = button.dataset.platformLayout === "agent" ? "agent" : "project";
        if (STATE.platformLayoutMode === next) return;
        STATE.platformLayoutMode = next;
        STATE.selectedGroupId = "";
        STATE.selectedSessionId = "";
        STATE.selectedPlatformCommLinkId = "";
        syncRouteLayout();
        if (STATE.platformProjects.length && STATE.sessions.length) {
          hydratePlatformView();
          return;
        }
        loadData();
      });
    });
    dom.platformScopeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const next = safeText(button.dataset.commScope, "all");
        if (STATE.platformCommScope === next) return;
        STATE.platformCommScope = next;
        STATE.selectedPlatformCommLinkId = "";
        persistLayoutStore();
        renderAll();
      });
    });
    dom.commTypeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const kind = safeText(button.dataset.commKind);
        if (!kind) return;
        STATE.commVisibility[kind] = !(STATE.commVisibility[kind] !== false);
        STATE.selectedPlatformCommLinkId = "";
        persistLayoutStore();
        renderAll();
      });
    });
    dom.platformCountButtons.forEach((button) => {
      button.addEventListener("click", () => {
        STATE.commLineCountMin = Math.max(0, Number(button.dataset.commCountMin) || 0);
        STATE.selectedPlatformCommLinkId = "";
        persistLayoutStore();
        renderAll();
      });
    });
    dom.platformProjectFilterBtn?.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!isPlatformMode()) return;
      normalizePlatformProjectSelection();
      if (!STATE.platformProjectFilterOpen) {
        STATE.platformProjectFilterDraft = [...STATE.platformProjectFilterSelected];
        STATE.platformProjectFilterDraftDirty = false;
      }
      STATE.platformProjectFilterOpen = !STATE.platformProjectFilterOpen;
      renderHeader();
    });
    dom.platformProjectSelectAllBtn?.addEventListener("click", () => {
      STATE.platformProjectFilterDraft = platformProjectIds();
      STATE.platformProjectFilterDraftDirty = true;
      renderPlatformProjectFilterPanel();
    });
    dom.platformProjectInvertBtn?.addEventListener("click", () => {
      const allIds = platformProjectIds();
      const current = new Set((STATE.platformProjectFilterDraft || []).map((item) => safeText(item)).filter(Boolean));
      STATE.platformProjectFilterDraft = allIds.filter((id) => !current.has(id));
      STATE.platformProjectFilterDraftDirty = true;
      renderPlatformProjectFilterPanel();
    });
    dom.platformProjectClearBtn?.addEventListener("click", () => {
      STATE.platformProjectFilterDraft = [];
      STATE.platformProjectFilterDraftDirty = true;
      renderPlatformProjectFilterPanel();
    });
    dom.platformProjectCancelBtn?.addEventListener("click", () => {
      STATE.platformProjectFilterDraft = [...STATE.platformProjectFilterSelected];
      STATE.platformProjectFilterDraftDirty = false;
      STATE.platformProjectFilterOpen = false;
      renderHeader();
    });
    dom.platformProjectApplyBtn?.addEventListener("click", () => {
      normalizePlatformProjectSelection();
      STATE.platformProjectFilterInitialized = true;
      STATE.platformProjectFilterSelected = [...STATE.platformProjectFilterDraft];
      STATE.platformProjectFilterDraftDirty = false;
      STATE.platformProjectFilterOpen = false;
      STATE.selectedPlatformCommLinkId = "";
      STATE.selectedGroupId = "";
      STATE.selectedSessionId = "";
      persistLayoutStore();
      hydratePlatformView();
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
    dom.openLayersBtn?.addEventListener("click", () => dom.layersPanel?.classList.remove("collapsed"));
    dom.closeLayersBtn?.addEventListener("click", () => dom.layersPanel?.classList.add("collapsed"));
    dom.openDetailBtn?.addEventListener("click", () => dom.detailPanel?.classList.remove("collapsed"));
    dom.closeDetailBtn?.addEventListener("click", () => dom.detailPanel?.classList.add("collapsed"));
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
      if (event.target && event.target.closest && event.target.closest(".node, .group-chip, .group-resize, .floating-panel, .edge-handle, .floating-mini-map, button, input, select, textarea, a")) return;
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
    });
    dom.linesSvg?.addEventListener("click", () => {
      STATE.selectedPlatformCommLinkId = "";
      renderDetail();
    });
    dom.stage?.addEventListener("click", (event) => {
      if (event.target === dom.stage || event.target === dom.groupsLayer || event.target === dom.linesSvg) {
        STATE.selectedGroupId = "";
        STATE.selectedSessionId = "";
        STATE.selectedPlatformCommLinkId = "";
        renderAll();
      }
    });
    document.addEventListener("click", (event) => {
      if (!STATE.platformProjectFilterOpen) return;
      const wrap = dom.platformProjectFilterWrap;
      if (wrap && !wrap.contains(event.target)) {
        STATE.platformProjectFilterDraft = [...STATE.platformProjectFilterSelected];
        STATE.platformProjectFilterDraftDirty = false;
        STATE.platformProjectFilterOpen = false;
        renderHeader();
      }
    });
    window.addEventListener("resize", () => {
      syncZoom();
      renderMiniMap();
    });
  }

  function init() {
    bindEvents();
    const applyRoute = (force = false) => {
      const route = qs();
      const next = {
        projectId: route.projectId,
        viewMode: route.mode === "platform" ? "platform" : "project",
        platformLayoutMode: route.layout === "agent" ? "agent" : "project",
        channelHint: route.channelName,
        sessionHint: route.sessionId,
        windowKey: "24h",
      };
      const changed = force
        || STATE.projectId !== next.projectId
        || STATE.viewMode !== next.viewMode
        || STATE.platformLayoutMode !== next.platformLayoutMode
        || STATE.channelHint !== next.channelHint
        || STATE.sessionHint !== next.sessionHint
        || (force && STATE.windowKey !== next.windowKey);
      if (!changed) return;
      STATE.projectId = next.projectId;
      STATE.viewMode = next.viewMode;
      STATE.platformLayoutMode = next.platformLayoutMode;
      STATE.channelHint = next.channelHint;
      STATE.sessionHint = next.sessionHint;
      if (force) STATE.windowKey = next.windowKey;
      const projectMeta = projectMetaById(STATE.projectId);
      STATE.projectName = isPlatformMode()
        ? "Qoreon 平台"
        : firstText([projectMeta && projectMeta.project_name, STATE.projectId], STATE.projectId);
      restoreCommFilterStateFromStore();
      syncTimeControls();
      loadData();
    };
    window.addEventListener("hashchange", () => applyRoute(false));
    applyRoute(true);
    window.setTimeout(() => applyRoute(false), 0);
  }

  init();
})();
