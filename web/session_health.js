(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const STATE = {
    q: "",
    risk: "all",
    sort: "baseline",
  };
  const INTERVAL_OPTIONS = [15, 30, 60, 120, 240, 360, 720, 1440];
  const COPY_LABEL = Object.create(null);
  const CLI_LABELS = {
    codex: "Codex",
    claude: "Claude Code",
    gemini: "Gemini CLI",
    opencode: "OpenCode",
    trae: "Trae Agent CLI",
  };
  const SUPPORTED_HEALTH_TYPES = ["codex"];
  const PLANNED_HEALTH_TYPES = ["claude", "gemini", "opencode", "trae"];
  const LIVE = {
    rows: null,
    syncAt: "",
    error: "",
    syncing: false,
    savingConfig: false,
  };

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

  function fmtNumber(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toLocaleString("zh-CN") : "0";
  }

  function fmtFloat(value, digits = 1) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toFixed(digits) : "-";
  }

  function formatPct(value, digits = 1) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";
    return n
      .toFixed(digits)
      .replace(/\.0+$/, "")
      .replace(/(\.\d*[1-9])0+$/, "$1");
  }

  function pageParams() {
    const out = new URLSearchParams(window.location.search || "");
    const hash = String(window.location.hash || "").replace(/^#/, "").trim();
    if (hash) {
      const hashParams = new URLSearchParams(hash);
      hashParams.forEach((value, key) => {
        if (!out.has(key)) out.set(key, value);
      });
    }
    return out;
  }

  function defaultProjectIdFromData() {
    const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
    const ids = projects
      .map((item) => String(item && item.project_id || "").trim())
      .filter(Boolean);
    if (ids.includes("task_dashboard")) return "task_dashboard";
    if (String(DATA.project_id || "").trim()) return String(DATA.project_id || "").trim();
    if (ids.length) return ids[0];
    return "task_dashboard";
  }

  function currentProjectId() {
    const params = pageParams();
    const fromUrl = String(
      params.get("p")
      || params.get("project_id")
      || params.get("projectId")
      || ""
    ).trim();
    return String(fromUrl || defaultProjectIdFromData()).trim() || "task_dashboard";
  }

  function currentProjectSummary() {
    const pid = currentProjectId();
    const rows = Array.isArray(DATA.projects) ? DATA.projects : [];
    return rows.find((item) => item && String(item.project_id || "").trim() === pid) || null;
  }

  function currentProjectName() {
    const summary = currentProjectSummary();
    return String(
      (summary && summary.project_name)
      || DATA.project_name
      || currentProjectId()
    ).trim() || currentProjectId();
  }

  function currentProjectSessionHealth() {
    const pid = currentProjectId();
    const summary = currentProjectSummary();
    const fromSummary = (summary && summary.session_health && typeof summary.session_health === "object")
      ? summary.session_health
      : {};
    const fromTop = (DATA.session_health && typeof DATA.session_health === "object" && String(DATA.project_id || "").trim() === pid)
      ? DATA.session_health
      : {};
    return {
      project_id: pid,
      project_name: currentProjectName(),
      enabled: true,
      interval_minutes: 120,
      configured: false,
      ...fromSummary,
      ...fromTop,
    };
  }

  function liveSessionsEndpoint() {
    return `/api/sessions?project_id=${encodeURIComponent(currentProjectId())}`;
  }

  function healthEndpoint({ refresh = false } = {}) {
    const url = new URL(`/api/session-health`, window.location.origin);
    url.searchParams.set("project_id", currentProjectId());
    if (refresh) url.searchParams.set("refresh", "1");
    return url.toString();
  }

  function linkValue(name, fallback) {
    const direct = DATA[name];
    if (direct) return String(direct);
    const nested = LINKS[name];
    if (nested) return String(nested);
    return fallback;
  }

  function parseTime(value) {
    const text = String(value || "").trim();
    if (!text) return null;
    const ms = Date.parse(text);
    return Number.isFinite(ms) ? ms : null;
  }

  function formatZhDateTime(value) {
    const ts = parseTime(value);
    if (!ts) return "未统计";
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(ts));
  }

  function formatZhDateTimeShort(value) {
    const ts = parseTime(value);
    if (!ts) return "-";
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(ts));
  }

  function cliLabel(value) {
    const key = String(value || "").trim().toLowerCase();
    return CLI_LABELS[key] || (key ? key : "未识别");
  }

  function intervalLabel(minutes) {
    const n = Number(minutes || 0);
    if (!Number.isFinite(n) || n <= 0) return "-";
    if (n < 60) return `每 ${fmtNumber(n)} 分钟`;
    if (n % 60 === 0 && n < 1440) return `每 ${fmtNumber(n / 60)} 小时`;
    if (n === 1440) return "每 24 小时";
    return `每 ${fmtNumber(n)} 分钟`;
  }

  function authHeaders() {
    try {
      const token = String(window.localStorage.getItem("taskDashboard.token") || "").trim();
      if (!token) return {};
      return { "X-TaskDashboard-Token": token };
    } catch (_err) {
      return {};
    }
  }

  function timeAgo(value) {
    const ts = parseTime(value);
    const now = parseTime(DATA.generated_at);
    if (!ts || !now) return "-";
    const diff = Math.max(0, now - ts);
    const hours = diff / 3600000;
    if (hours < 1) return "1h内";
    if (hours < 24) return `${Math.round(hours)}h前`;
    const days = hours / 24;
    if (days < 7) return `${Math.round(days)}d前`;
    return `${fmtFloat(days, 1)}d前`;
  }

  function riskClass(level) {
    if (level === "high") return "high";
    if (level === "medium") return "medium";
    if (level === "low") return "low";
    return "unsupported";
  }

  function riskTitle(row) {
    if (row.risk_level === "unsupported") return "未支持";
    return String(row.baseline_floor_status || "-");
  }

  function baselineFloor(row) {
    return Number(row.baseline_floor_pct || row.risk_score || 0);
  }

  function baselineText(row) {
    if (row.risk_level === "unsupported") return "-";
    return `${fmtNumber(baselineFloor(row))}%`;
  }

  function baselineQualifier(row) {
    if (row.risk_level === "unsupported") return "";
    if (row.baseline_floor_source === "observed") return "实测";
    return row.baseline_floor_estimated ? "估算" : "直读";
  }

  function baselineIsPriority(row) {
    return Boolean(row.sustained_high_floor) && baselineFloor(row) >= 60;
  }

  function baselineStatusNote(row) {
    if (row.risk_level === "unsupported") return "当前页只支持 Codex 日志自动判定";
    if (baselineIsPriority(row)) return "连续多次 compact 后仍处高位";
    if (row.baseline_floor_source === "observed") return "按最近几次 compact 后的实测占用判定";
    return "缺少 token_count，按 compact 节奏估算";
  }

  function baselineHint(row) {
    if (row.risk_level === "unsupported") return "未支持";
    if (baselineFloor(row) <= 35) return "回落健康";
    if (baselineFloor(row) < 55) return "需要观察";
    if (baselineFloor(row) < 70) return "回落偏弱";
    return "建议轮换";
  }

  function riskWeight(row) {
    if (baselineIsPriority(row)) return 5000;
    if (row.risk_level === "high") return 4000;
    if (row.risk_level === "medium") return 2000;
    if (row.risk_level === "low") return 1000;
    return 0;
  }

  function agentDisplayName(row) {
    const text = [
      row.alias,
      row.display_name,
      row.displayName,
      row.codex_title,
      row.codexTitle,
      row.channel_name,
      row.session_id,
    ].find((item) => String(item || "").trim());
    return String(text || "-").trim() || "-";
  }

  function normalizeBindingState(value) {
    const text = String(value || "").trim().toLowerCase();
    if (text === "override") return "override";
    if (text === "drift") return "drift";
    if (text === "unbound") return "unbound";
    return "bound";
  }

  function bindingStateLabel(state) {
    if (state === "override") return "特例覆盖";
    if (state === "drift") return "上下文漂移";
    if (state === "unbound") return "未完全绑定";
    return "已绑定";
  }

  function bindingStateTone(state) {
    if (state === "override") return "warning";
    if (state === "drift") return "danger";
    if (state === "unbound") return "muted";
    return "good";
  }

  function rowContextBindingState(row) {
    return normalizeBindingState(
      row && (row.context_binding_state || row.contextBindingState)
    );
  }

  function rowContextHint(row) {
    const state = rowContextBindingState(row);
    const context = (row && row.project_execution_context && typeof row.project_execution_context === "object")
      ? row.project_execution_context
      : {};
    const target = (context.target && typeof context.target === "object") ? context.target : {};
    const environment = String(
      target.environment
      || row.environment
      || "-"
    ).trim() || "-";
    const branch = String(
      target.branch
      || row.branch
      || "-"
    ).trim() || "-";
    if (state === "override") return `项目继承 + 特例覆盖 · ${environment} · ${branch}`;
    if (state === "drift") return `项目真源与会话实际值不一致 · ${environment} · ${branch}`;
    if (state === "unbound") return `上下文信息未补齐 · ${environment} · ${branch}`;
    return `按项目默认上下文运行 · ${environment} · ${branch}`;
  }

  function createRiskPill(level, text) {
    return el("span", { class: `pill ${riskClass(level)}`, text });
  }

  function dangerWeight(row) {
    const levelWeight = riskWeight(row) || 0;
    const baseline = baselineFloor(row) * 100;
    const compactions24h = Number(row.recent_compactions_24h || 0) * 25;
    const compacted = Number(row.compacted_count || 0) * 4;
    return levelWeight + baseline + compactions24h + compacted;
  }

  function baselineReasons(row) {
    if (row.risk_level === "unsupported") return "当前页只支持 Codex 日志自动判定";
    const reasons = Array.isArray(row.baseline_floor_reasons) ? row.baseline_floor_reasons.filter(Boolean) : [];
    return reasons.length ? reasons.join(" · ") : "暂无 compact 记录";
  }

  function recentAfterSeries(row) {
    const values = Array.isArray(row.recent_after_usage_pcts) ? row.recent_after_usage_pcts.filter((item) => item != null) : [];
    if (!values.length) return "";
    return values.map((item) => `${fmtNumber(item)}%`).join(" · ");
  }

  function latestTransitionText(row) {
    const observations = Array.isArray(row.compaction_observations) ? row.compaction_observations : [];
    if (!observations.length) return "";
    const latest = observations[observations.length - 1] || {};
    const before = latest.before_pct;
    const after = latest.after_pct;
    if (before == null || after == null) return "";
    return `最近一次 ${fmtNumber(before)}% → ${fmtNumber(after)}%`;
  }

  function pressureDetail(row) {
    if (row.risk_level === "unsupported") return "当前页只支持 Codex 日志自动判定";
    const series = recentAfterSeries(row);
    if (series) return `最近压缩后占用: ${series}`;
    return "最近压缩后占用: 暂无可观测 token_count";
  }

  function transitionDetail(row) {
    if (row.risk_level === "unsupported") return "";
    const latest = latestTransitionText(row);
    if (latest) return latest;
    if (row.baseline_floor_source === "estimated") return "当前为估算基线，尚未拿到压缩前后实测值";
    return "";
  }

  function historyNote(row) {
    if (row.risk_level === "unsupported") return "仅展示绑定";
    return `总压缩 ${fmtNumber(row.compacted_count)} · 上下文轮次 ${fmtNumber(row.turn_context_count)}`;
  }

  function paceTitle(row) {
    if (row.risk_level === "unsupported") return "未支持";
    if (!Number(row.compacted_count || 0)) return "暂无 compact";
    const avgHours = row.avg_hours_between_compactions;
    if (avgHours == null) return "仅发生过 1 次 compact";
    return `近几次压缩间隔 ${fmtFloat(avgHours, 1)}h`;
  }

  function paceNote(row) {
    if (row.risk_level === "unsupported") return "当前页只支持 Codex";
    if (!Number(row.compacted_count || 0)) return "当前还没有出现 compact";
    const bits = [];
    if (row.avg_turns_between_compactions != null) bits.push(`压缩间推进 ${fmtFloat(row.avg_turns_between_compactions, 0)} 轮`);
    if (row.turns_since_last_compaction != null) bits.push(`最近压缩后推进 ${fmtNumber(row.turns_since_last_compaction)} 轮`);
    if (row.last_compacted_at) bits.push(`最近压缩 ${timeAgo(row.last_compacted_at)}`);
    return bits.join(" · ") || "暂无更多节奏数据";
  }

  function recentCompactionItems(row, limit = 4) {
    const observations = Array.isArray(row.compaction_observations) ? row.compaction_observations : [];
    return observations
      .filter((item) => item && typeof item === "object" && item.compacted_at)
      .slice(-limit)
      .reverse();
  }

  function createPaceHistoryBlock(row) {
    if (row.risk_level === "unsupported") {
      return el("div", { class: "pace-history-empty", text: "当前页只支持 Codex compact 历史" });
    }
    const items = recentCompactionItems(row);
    if (!items.length) {
      return el("div", { class: "pace-history-empty", text: "最近几次压缩记录暂缺" });
    }
    return el("div", { class: "pace-history-wrap" }, [
      el("div", { class: "pace-history-label", text: "最近几次压缩记录" }),
      el("div", { class: "pace-history" }, items.map((item) => {
        const before = formatPct(item.before_pct);
        const after = formatPct(item.after_pct);
        const compactedAt = String(item.compacted_at || "").trim();
        return el("div", { class: "pace-history-item" }, [
          el("span", {
            class: "pace-history-time",
            text: formatZhDateTimeShort(compactedAt),
            title: formatZhDateTime(compactedAt),
          }),
          el("span", {
            class: "pace-history-change",
            text: `${before}% → ${after}%`,
          }),
        ]);
      })),
    ]);
  }

  function recentCompactionText(row) {
    if (row.risk_level === "unsupported") return "-";
    const count = Number(row.recent_compactions_24h || 0);
    return String(count);
  }

  function resetButtonThresholdPct() {
    const value = Number(DATA.thresholds && DATA.thresholds.reset_button_threshold_pct);
    if (Number.isFinite(value)) return value;
    return 20;
  }

  function shouldShowReset(row) {
    if (row.risk_level === "unsupported") return false;
    return baselineFloor(row) >= resetButtonThresholdPct();
  }

  function normalizeTaskTracking(src) {
    if (!src || typeof src !== "object") {
      return {
        current_task_ref: null,
        conversation_task_refs: [],
        recent_task_actions: [],
      };
    }
    return {
      current_task_ref: (src.current_task_ref && typeof src.current_task_ref === "object") ? src.current_task_ref : null,
      conversation_task_refs: Array.isArray(src.conversation_task_refs) ? src.conversation_task_refs.filter((item) => item && typeof item === "object") : [],
      recent_task_actions: Array.isArray(src.recent_task_actions) ? src.recent_task_actions.filter((item) => item && typeof item === "object") : [],
    };
  }

  function taskTrackingSummary(row) {
    const tracking = normalizeTaskTracking(row && row.task_tracking);
    const currentRef = tracking.current_task_ref || null;
    const currentTitle = String(
      (currentRef && (currentRef.task_title || currentRef.title || currentRef.task_path || currentRef.path)) || ""
    ).trim();
    const refsCount = tracking.conversation_task_refs.length;
    const actionsCount = tracking.recent_task_actions.length;
    const bits = [];
    if (currentTitle) bits.push(`current_task_ref=${currentTitle}`);
    else bits.push("current_task_ref=待复核");
    bits.push(`conversation_task_refs=${refsCount}条`);
    bits.push(`recent_task_actions=${actionsCount}条`);
    return bits.join("；");
  }

  function readTaskRefIdentity(ref) {
    if (!ref || typeof ref !== "object") {
      return { taskId: "", taskPath: "" };
    }
    return {
      taskId: String(ref.task_id || ref.taskId || "").trim(),
      taskPath: String(ref.task_path || ref.taskPath || "").trim(),
    };
  }

  function taskHandoffState(row) {
    const tracking = normalizeTaskTracking(row && row.task_tracking);
    const currentRef = readTaskRefIdentity(tracking.current_task_ref);
    const recentAction = readTaskRefIdentity(
      Array.isArray(tracking.recent_task_actions) && tracking.recent_task_actions.length ? tracking.recent_task_actions[0] : null
    );
    const relatedCount = tracking.conversation_task_refs.length;

    if (!currentRef.taskId && !currentRef.taskPath) {
      return {
        tone: "warning",
        label: "待核对",
        title: "live task_tracking 尚未给出 current_task_ref",
        currentRef,
        recentAction,
        relatedCount,
      };
    }

    if (currentRef.taskId && recentAction.taskId && currentRef.taskId !== recentAction.taskId) {
      return {
        tone: "danger",
        label: "错位",
        title: "最近任务动作的 task_id 与当前任务不一致",
        currentRef,
        recentAction,
        relatedCount,
      };
    }

    if (!currentRef.taskId || !currentRef.taskPath) {
      return {
        tone: "warning",
        label: "待核对",
        title: "当前任务仍缺少 task_id 或 task_path，无法完成完整承接判断",
        currentRef,
        recentAction,
        relatedCount,
      };
    }

    return {
      tone: "good",
      label: "已核对",
      title: "当前任务身份与位置字段已具备最小承接判断条件",
      currentRef,
      recentAction,
      relatedCount,
    };
  }

  function taskIdentityText(identity) {
    const taskId = String(identity && identity.taskId || "").trim();
    const taskPath = String(identity && identity.taskPath || "").trim();
    return `task_id=${taskId || "-"} · task_path=${taskPath || "-"}`;
  }

  function buildResetMessage(row) {
    const agent = agentDisplayName(row);
    const role = row.is_primary ? "主会话" : "子会话";
    return [
      `请对这个 Codex 对话执行标准会话重置，使用技能 \`agent-session-rotation-handoff\`。`,
      `- 目标 agent：@${agent}`,
      `- 通道：${String(row.channel_name || "-")}`,
      `- 当前异常会话 session_id：${String(row.session_id || "-")}`,
      `- 会话角色：${role}`,
      `- 异常判断：压缩后占用基线=${baselineText(row)}（${baselineQualifier(row) || "估算"}）；${pressureDetail(row)}；${transitionDetail(row) || baselineReasons(row)}`,
      `- 处理要求：`,
      `  0. 旧会话先自行整理一版工作转交资料；若旧会话不可用，必须回执 \`旧会话自交接: skipped\`、跳过原因和替代资料来源。`,
      `  1. 创建新会话并完成项目内对话替换；若当前为主会话则替换正式主绑定。`,
      `  2. 新会话必须先学习继承旧会话上下文，再完成接管初始化训练，然后才能继续推进。`,
      `  2.1 接管初始化训练至少覆盖：正式消息发送链路、开始任务顺序（先读 README/任务/反馈/材料/沉淀，再回“已完成初始化”）、回执时机与 notify_only 例外、声称“已发送”时必须带 announce_run_id。`,
      `  2.2 若发生 session 换绑，还必须同步处理任务承接链路：确认当前正式主绑定是否需要替换，说明旧/新 session 交接关系，并把当前主任务、相关任务、交接锚点一起纳入接管。`,
      `  2.3 至少检查 \`current_task_ref / conversation_task_refs / recent_task_actions\` 是否仍正确指向当前业务主线；若存在活动任务、交接锚点或待验收回执，要求同步确认任务文件、反馈文件与协作链路是否需要补口。`,
      `  2.4 不能只重置会话，不处理任务承接链路；若判断无需补口，也必须在回执里明确写“当前任务承接链路已核对，无需补口”。`,
      `  2.5 当前任务跟踪线索：${taskTrackingSummary(row)}`,
      `  3. 旧会话从当前列表移除；若不能删除则明确标记冻结/历史，并说明旧会话处理策略。`,
      `  4. 回执给我：旧会话自交接状态、新 session_id、继承/初始化 run_id、验收 run_id、已完成继承、已完成初始化、当前主线、唯一阻塞、主绑定是否已替换、当前任务承接链路是否已核对。`,
    ].join("\n");
  }

  async function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "readonly");
    ta.style.position = "fixed";
    ta.style.top = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }

  function bindHeader() {
    const generatedAtBadge = document.getElementById("generatedAtBadge");
    const heroSub = document.getElementById("heroSub");
    const projectNameBadge = document.getElementById("projectNameBadge");
    const projectIdMeta = document.getElementById("projectIdMeta");
    const autoStatusText = document.getElementById("autoStatusText");
    const overviewLink = document.getElementById("overviewLink");
    const taskLink = document.getElementById("taskLink");
    const statusReportLink = document.getElementById("statusReportLink");
    const communicationLink = document.getElementById("communicationLink");
    const agentCurtainLink = document.getElementById("agentCurtainLink");
    const refreshButton = document.getElementById("refreshButton");
    const saveConfigButton = document.getElementById("saveConfigButton");
    const autoEnabledInput = document.getElementById("autoEnabledInput");
    const intervalSelect = document.getElementById("intervalSelect");
    const config = currentProjectSessionHealth();
    const latestTime = config.latest_generated_at || config.last_completed_at || DATA.generated_at || "";
    const saving = Boolean(LIVE.savingConfig);

    if (generatedAtBadge) {
      generatedAtBadge.textContent = LIVE.syncing ? "正在重算日志…" : formatZhDateTime(latestTime);
    }
    if (projectNameBadge) projectNameBadge.textContent = currentProjectName();
    if (projectIdMeta) projectIdMeta.textContent = `项目 ID：${currentProjectId()}`;
    if (autoStatusText) {
      const parts = [
        config.enabled ? "自动统计已开启" : "自动统计已关闭",
        intervalLabel(config.interval_minutes),
      ];
      if (config.next_due_at && config.enabled) parts.push(`下次预计 ${formatZhDateTime(config.next_due_at)}`);
      if (LIVE.error) parts.push(`异常：${LIVE.error}`);
      autoStatusText.textContent = parts.join(" · ");
    }
    if (heroSub) {
      heroSub.textContent = `当前只展示项目 ${currentProjectName()} 的 agent 会话数据；后台已纳入全局项目自动统计，当前项目可在右侧修改自动统计开关与频率。压缩后占用基线达到 ${fmtNumber(resetButtonThresholdPct())}% 时，会提前开放重置按钮。`;
    }
    if (overviewLink) overviewLink.href = linkValue("overview_page", "/share/project-overview-dashboard.html");
    if (taskLink) taskLink.href = linkValue("task_page", "/share/project-task-dashboard.html");
    if (statusReportLink) statusReportLink.href = linkValue("status_report_page", "/share/project-status-report.html");
    if (communicationLink) communicationLink.href = linkValue("communication_page", "/share/project-communication-audit.html");
    if (agentCurtainLink) agentCurtainLink.href = linkValue("agent_curtain_page", "/share/project-agent-curtain.html");
    if (autoEnabledInput) {
      autoEnabledInput.checked = Boolean(config.enabled);
      autoEnabledInput.disabled = Boolean(LIVE.syncing || saving);
    }
    if (intervalSelect) {
      const target = String(config.interval_minutes || 120);
      if (!Array.from(intervalSelect.options).some((opt) => opt.value === target)) {
        intervalSelect.appendChild(el("option", { value: target, text: intervalLabel(target) }));
      }
      intervalSelect.value = target;
      intervalSelect.disabled = Boolean(LIVE.syncing || saving);
    }
    if (refreshButton) {
      refreshButton.disabled = Boolean(LIVE.syncing);
      refreshButton.textContent = LIVE.syncing ? "重算中..." : "立即重算";
    }
    if (saveConfigButton) {
      saveConfigButton.disabled = Boolean(LIVE.syncing || saving);
      saveConfigButton.textContent = saving ? "保存中..." : "保存配置";
    }
  }

  function defaultRowFromLive(session) {
    const cliType = String(session.cli_type || "codex");
    const supported = cliType === "codex";
    return {
      project_id: currentProjectId(),
      project_name: currentProjectId(),
      channel_name: String(session.channel_name || session.name || "-"),
      alias: String(session.alias || ""),
      display_name: String(session.display_name || session.displayName || ""),
      display_name_source: String(session.display_name_source || session.displayNameSource || ""),
      codex_title: String(session.codex_title || session.codexTitle || ""),
      session_id: String(session.id || session.session_id || ""),
      cli_type: cliType,
      model: String(session.model || ""),
      reasoning_effort: String(session.reasoning_effort || session.reasoningEffort || ""),
      source: "live_session_store",
      environment: String(session.environment || ""),
      branch: String(session.branch || ""),
      worktree_root: String(session.worktree_root || session.worktreeRoot || ""),
      workdir: String(session.workdir || ""),
      context_binding_state: normalizeBindingState(session.context_binding_state || session.contextBindingState || "bound"),
      project_execution_context: (session.project_execution_context && typeof session.project_execution_context === "object")
        ? session.project_execution_context
        : null,
      is_primary: Boolean(session.is_primary),
      session_role: String(session.session_role || (session.is_primary ? "primary" : "child")),
      status: String(session.status || "active"),
      is_deleted: Boolean(session.is_deleted),
      created_at: String(session.created_at || ""),
      last_used_at: String(session.last_used_at || ""),
      supported,
      has_log: false,
      log_paths: [],
      log_paths_count: 0,
      log_size_bytes: 0,
      log_size_mb: 0,
      turn_context_count: 0,
      compacted_count: 0,
      first_event_at: "",
      last_event_at: "",
      last_compacted_at: "",
      compaction_timestamps: [],
      compaction_observations: [],
      recent_after_usage_pcts: [],
      last_after_usage_pct: null,
      avg_turns_between_compactions: null,
      avg_hours_between_compactions: null,
      turns_since_last_compaction: null,
      age_days: 0,
      hours_since_last_compacted: null,
      recent_compaction: false,
      recent_compactions_24h: 0,
      recent_compactions_7d: 0,
      risk_score: 0,
      risk_level: supported ? "low" : "unsupported",
      risk_reasons: supported ? ["暂无 compact 记录"] : ["当前页只支持 Codex 日志自动判定"],
      baseline_floor_pct: 0,
      baseline_floor_reasons: supported ? ["暂无 compact 记录"] : ["当前页只支持 Codex 日志自动判定"],
      baseline_floor_status: supported ? "健康" : "未支持",
      baseline_floor_estimated: supported,
      baseline_floor_source: supported ? "estimated" : "unsupported",
      sustained_high_floor: false,
      health_action: supported ? "继续观察" : "仅展示绑定",
      task_tracking: normalizeTaskTracking(session.task_tracking || session.taskTracking || null),
    };
  }

  function mergeLiveRows(liveSessions) {
    const embedded = Array.isArray(DATA.sessions) ? DATA.sessions : [];
    const embeddedById = new Map(
      embedded
        .filter((row) => row && row.session_id)
        .map((row) => [String(row.session_id), row]),
    );
    return (Array.isArray(liveSessions) ? liveSessions : [])
      .filter((session) => session && !session.is_deleted)
      .map((session) => {
        const id = String(session.id || session.session_id || "").trim();
        const base = embeddedById.get(id) || defaultRowFromLive(session);
        return {
          ...base,
          project_id: currentProjectId(),
          project_name: currentProjectName(),
          session_id: id,
          channel_name: String(session.channel_name || base.channel_name || "-"),
          alias: String(session.alias || base.alias || ""),
          display_name: String(session.display_name || session.displayName || base.display_name || ""),
          display_name_source: String(session.display_name_source || session.displayNameSource || base.display_name_source || ""),
          codex_title: String(session.codex_title || session.codexTitle || base.codex_title || ""),
          cli_type: String(session.cli_type || base.cli_type || "codex"),
          model: String(session.model || base.model || ""),
          reasoning_effort: String(session.reasoning_effort || session.reasoningEffort || base.reasoning_effort || ""),
          environment: String(session.environment || base.environment || ""),
          branch: String(session.branch || base.branch || ""),
          worktree_root: String(session.worktree_root || session.worktreeRoot || base.worktree_root || ""),
          workdir: String(session.workdir || base.workdir || ""),
          context_binding_state: normalizeBindingState(
            session.context_binding_state
            || session.contextBindingState
            || base.context_binding_state
            || base.contextBindingState
            || "bound"
          ),
          project_execution_context: (session.project_execution_context && typeof session.project_execution_context === "object")
            ? session.project_execution_context
            : ((base.project_execution_context && typeof base.project_execution_context === "object") ? base.project_execution_context : null),
          task_tracking: normalizeTaskTracking(
            session.task_tracking
            || session.taskTracking
            || base.task_tracking
            || base.taskTracking
            || null
          ),
          is_primary: Boolean(session.is_primary),
          session_role: String(session.session_role || base.session_role || (session.is_primary ? "primary" : "child")),
          status: String(session.status || base.status || "active"),
          is_deleted: Boolean(session.is_deleted),
          created_at: String(session.created_at || base.created_at || ""),
          last_used_at: String(session.last_used_at || base.last_used_at || ""),
          source: "live_session_store",
        };
      });
  }

  function activeSessions() {
    const pid = currentProjectId();
    const rows = Array.isArray(LIVE.rows) ? LIVE.rows.slice() : (Array.isArray(DATA.sessions) ? DATA.sessions.slice() : []);
    return rows.filter((row) => row && !row.is_deleted && String(row.project_id || DATA.project_id || "").trim() === pid);
  }

  function applyHealthPayload(payload) {
    if (!payload || typeof payload !== "object") return;
    DATA.generated_at = String(payload.generated_at || DATA.generated_at || "");
    DATA.project_id = String(payload.project_id || DATA.project_id || currentProjectId());
    DATA.project_name = String(payload.project_name || DATA.project_name || currentProjectName());
    DATA.summary = payload.summary || DATA.summary || {};
    DATA.thresholds = payload.thresholds || DATA.thresholds || {};
    DATA.sessions = Array.isArray(payload.sessions) ? payload.sessions : (DATA.sessions || []);
    DATA.projects = Array.isArray(payload.projects) ? payload.projects : (DATA.projects || []);
    DATA.session_health = (payload.session_health && typeof payload.session_health === "object") ? payload.session_health : (DATA.session_health || {});
    DATA.global_automation = (payload.global_automation && typeof payload.global_automation === "object") ? payload.global_automation : (DATA.global_automation || {});
    DATA.links = (payload.links && typeof payload.links === "object") ? payload.links : (DATA.links || {});
    updateProjectSummarySessionHealth({
      ...(DATA.session_health && typeof DATA.session_health === "object" ? DATA.session_health : {}),
      project_id: currentProjectId(),
      project_name: currentProjectName(),
    });
  }

  function buildLiveSummary(rows) {
    const list = Array.isArray(rows) ? rows : [];
    const supported = list.filter((row) => row && row.supported);
    return {
      session_count: list.length,
      codex_supported_count: supported.length,
      recent_compaction_count: supported.filter((row) => row.recent_compaction).length,
      deleted_skipped_count: Number((DATA.summary && DATA.summary.deleted_skipped_count) || 0),
      risk_counts: {
        high: supported.filter((row) => row.risk_level === "high").length,
        medium: supported.filter((row) => row.risk_level === "medium").length,
        low: supported.filter((row) => row.risk_level === "low").length,
      },
    };
  }

  function renderSummaryLine() {
    const wrap = document.getElementById("summaryLine");
    if (!wrap) return;
    const summary = buildLiveSummary(activeSessions());
    const riskCounts = summary.risk_counts || {};
    const cfg = currentProjectSessionHealth();
    const globalAutomationRaw = (DATA.global_automation && typeof DATA.global_automation === "object") ? DATA.global_automation : {};
    const projectRows = Array.isArray(DATA.projects) ? DATA.projects : [];
    const globalAutomation = {
      project_count: Number(globalAutomationRaw.project_count || projectRows.length || 0),
      enabled_count: Number(
        globalAutomationRaw.enabled_count
        || projectRows.filter((item) => item && item.session_health && item.session_health.enabled).length
        || 0
      ),
    };
    const items = [
      `总会话 ${fmtNumber(summary.session_count)}`,
      `可判定 ${fmtNumber(summary.codex_supported_count)}`,
      `优先轮换 ${fmtNumber(riskCounts.high)}`,
      `继续观察/准备轮换 ${fmtNumber(riskCounts.medium)}`,
      `24h发生压缩 ${fmtNumber(summary.recent_compaction_count)}`,
    ];
    wrap.innerHTML = "";
    wrap.appendChild(el("div", { class: "summary-line-title", text: "当前口径" }));
    wrap.appendChild(el("div", { class: "summary-line-body", text: items.join(" · ") }));
    const syncNote = LIVE.syncAt ? `已对齐当前 agent 列表 ${LIVE.syncAt}` : "当前展示以构建时快照为准";
    const errorNote = LIVE.error ? `；实时同步失败：${LIVE.error}` : "";
    wrap.appendChild(el("div", {
      class: "summary-line-note",
      text: `当前项目 ${currentProjectName()}；自动统计 ${cfg.enabled ? "已开启" : "已关闭"}，频率 ${intervalLabel(cfg.interval_minutes)}；最新统计 ${formatZhDateTime(cfg.latest_generated_at || cfg.last_completed_at || DATA.generated_at)}。全局项目纳入自动统计 ${fmtNumber(globalAutomation.enabled_count || 0)}/${fmtNumber(globalAutomation.project_count || 0)} 个。仅统计当前 agent 列表中的现存会话；已删除排除 ${fmtNumber(summary.deleted_skipped_count)} 条。${syncNote}${errorNote}。主指标=压缩后占用基线；健康 ${String(DATA.thresholds && DATA.thresholds.healthy || "-")} · 可观察 ${String(DATA.thresholds && DATA.thresholds.observe || "-")} · 偏危险 ${String(DATA.thresholds && DATA.thresholds.warning || "-")} · 轮换 ${String(DATA.thresholds && DATA.thresholds.rotate || "-")} · ${String(DATA.thresholds && DATA.thresholds.note || "")}`,
    }));
  }

  function renderSupportMatrix() {
    const wrap = document.getElementById("supportMatrix");
    if (!wrap) return;
    const observed = Array.from(new Set(
      activeSessions()
        .map((row) => String(row && row.cli_type || "").trim().toLowerCase())
        .filter(Boolean)
    ));
    const observedText = observed.length
      ? observed.map((item) => cliLabel(item)).join(" / ")
      : "当前项目暂无会话";
    const unsupportedObserved = observed.filter((item) => !SUPPORTED_HEALTH_TYPES.includes(item));

    wrap.innerHTML = "";
    wrap.appendChild(el("div", { class: "capability-grid" }, [
      el("section", { class: "capability-card current" }, [
        el("span", { class: "capability-title", text: "当前支持自动健康判定" }),
        el("p", { class: "capability-main", text: SUPPORTED_HEALTH_TYPES.map((item) => cliLabel(item)).join(" / ") }),
        el("div", { class: "capability-note", text: "目前只有这些类型会自动读取日志，计算 compact、token_count、压缩后占用基线等健康指标。" }),
      ]),
      el("section", { class: "capability-card plan" }, [
        el("span", { class: "capability-title", text: "后续计划支持" }),
        el("p", { class: "capability-main", text: PLANNED_HEALTH_TYPES.map((item) => cliLabel(item)).join(" / ") }),
        el("div", { class: "capability-note", text: "这些类型后续会接入各自稳定日志源，再纳入同一张健康页做自动判定。" }),
      ]),
      el("section", { class: "capability-card observed" }, [
        el("span", { class: "capability-title", text: "当前项目已接入类型" }),
        el("p", { class: "capability-main", text: observedText }),
        el("div", {
          class: "capability-note",
          text: unsupportedObserved.length
            ? `其中 ${unsupportedObserved.map((item) => cliLabel(item)).join(" / ")} 当前只做会话绑定展示，暂不自动计算健康分。`
            : "当前项目里已接入的会话类型都已纳入自动健康判定。",
        }),
      ]),
    ]));
  }

  function renderChrome() {
    bindHeader();
    renderSummaryLine();
    renderSupportMatrix();
  }

  function rawSessions() {
    return activeSessions();
  }

  function filteredSessions() {
    const q = String(STATE.q || "").trim().toLowerCase();
    return rawSessions().filter((row) => {
      const level = String(row.risk_level || "unsupported");
      if (STATE.risk !== "all" && level !== STATE.risk) return false;
      if (!q) return true;
      const hay = [
        agentDisplayName(row),
        row.channel_name,
        row.session_id,
        row.health_action,
      ].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }

  function sortRows(rows) {
    const out = rows.slice();
    out.sort((a, b) => {
      if (STATE.sort === "name") {
        return agentDisplayName(a).localeCompare(agentDisplayName(b), "zh-CN");
      }
      if (STATE.sort === "recent24h") {
        return Number(b.recent_compactions_24h || 0) - Number(a.recent_compactions_24h || 0) || dangerWeight(b) - dangerWeight(a);
      }
      if (STATE.sort === "recent") {
        return (parseTime(b.last_compacted_at) || 0) - (parseTime(a.last_compacted_at) || 0) || dangerWeight(b) - dangerWeight(a);
      }
      return dangerWeight(b) - dangerWeight(a);
    });
    return out;
  }

  function renderTable() {
    const tbody = document.getElementById("sessionTableBody");
    if (!tbody) return;
    const rows = sortRows(filteredSessions());
    tbody.innerHTML = "";

    if (!rows.length) {
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "empty-row", colspan: "8", text: "当前筛选条件下没有匹配的 agent 对话。" }),
      ]));
      return;
    }

    rows.forEach((row, index) => {
      const copyKey = String(row.session_id || `row-${index}`);
      const sessionId = String(row.session_id || "-");
      const agentMeta = row.is_primary ? "主会话" : "子会话";
      const baseline = baselineFloor(row);
      const risk = createRiskPill(String(row.risk_level || "unsupported"), riskTitle(row));
      const copyTextLabel = COPY_LABEL[copyKey] || "复制重置消息";
      const bindingState = rowContextBindingState(row);
      const handoff = taskHandoffState(row);
      const bindingPill = el("span", {
        class: `metric-badge ${bindingStateTone(bindingState)}`,
        text: bindingStateLabel(bindingState),
      });

      tbody.appendChild(el("tr", {}, [
        el("td", { class: "rank-cell" }, [
          el("div", { class: "rank-number", text: String(index + 1) }),
        ]),
        el("td", { class: "agent-cell" }, [
          el("div", { class: "agent-title", text: agentDisplayName(row) }),
          el("div", { class: "agent-meta", text: agentMeta }),
          el("div", { class: "agent-session-id", title: sessionId }, [
            el("span", { class: "agent-session-id-label", text: "session_id" }),
            el("code", { class: "agent-session-id-value", text: sessionId }),
          ]),
        ]),
        el("td", { class: "channel-cell" }, [
          el("div", { class: "channel-title", text: String(row.channel_name || "-") }),
          el("div", { class: "channel-meta" }, [
            bindingPill,
            el("span", { text: rowContextHint(row) }),
          ]),
        ]),
        el("td", { class: "pressure-cell" }, [
          el("div", { class: "pressure-head" }, [
            el("span", { class: "pressure-score", text: baselineText(row) }),
            risk,
            ...(baselineQualifier(row) ? [el("span", { class: "metric-badge", text: baselineQualifier(row) })] : []),
          ]),
          el("div", { class: "pressure-bar-track" }, [
            el("div", {
              class: `pressure-bar-fill ${riskClass(row.risk_level || "unsupported")}`,
              style: `width:${row.risk_level === "unsupported" ? 0 : Math.max(0, Math.min(100, baseline))}%`,
            }),
          ]),
          el("div", { class: "health-note", text: `${baselineStatusNote(row)} · ${baselineHint(row)}` }),
          el("div", { class: "health-note", text: pressureDetail(row) }),
          el("div", { class: "health-note", text: transitionDetail(row) || baselineReasons(row) }),
        ]),
        el("td", { class: "metric-cell" }, [
          el("div", { class: "stat-number", text: recentCompactionText(row) }),
          el("div", {
            class: "stat-meta",
            text: row.last_compacted_at ? `${timeAgo(row.last_compacted_at)} · ${formatZhDateTimeShort(row.last_compacted_at)}` : "暂无 recent compact",
          }),
        ]),
        el("td", { class: "pace-cell" }, [
          el("div", { class: "pace-title", text: paceTitle(row) }),
          el("div", { class: "pace-note", text: paceNote(row) }),
          createPaceHistoryBlock(row),
        ]),
        el("td", { class: "advice-cell" }, [
          el("div", { class: "advice-title", text: String(row.health_action || "继续观察") }),
          el("div", { class: "advice-note", text: historyNote(row) }),
          el("div", { class: "task-handoff-block" }, [
            el("div", { class: "task-handoff-head" }, [
              el("span", { class: `metric-badge ${handoff.tone}`, text: `任务承接 ${handoff.label}` }),
              el("span", { class: "task-handoff-title", text: handoff.title }),
            ]),
            el("div", { class: "advice-note", text: `当前任务：${taskIdentityText(handoff.currentRef)}` }),
            el("div", { class: "advice-note", text: `最近动作：${taskIdentityText(handoff.recentAction)}` }),
            el("div", { class: "advice-note", text: `相关任务：${fmtNumber(handoff.relatedCount)} 条` }),
          ]),
        ]),
        el("td", { class: "action-cell" }, shouldShowReset(row) ? [
          el("button", {
            class: `copy-btn${copyTextLabel === "已复制" ? " copied" : ""}`,
            type: "button",
            "data-copy-key": copyKey,
            text: copyTextLabel,
          }),
          el("div", { class: "tiny-note", text: `复制后可直接发给执行 agent 做标准重置，已包含 session 换绑与任务承接要求；当前按钮提前开放门槛>=${fmtNumber(resetButtonThresholdPct())}%` }),
        ] : [
          el("div", { class: "tiny-note", text: `当前无需直接重置（按钮门槛>=${fmtNumber(resetButtonThresholdPct())}%）` }),
        ]),
      ]));
    });
  }

  function bindFilters() {
    const searchInput = document.getElementById("searchInput");
    const sortSelect = document.getElementById("sortSelect");
    const riskWrap = document.getElementById("riskFilters");
    const tbody = document.getElementById("sessionTableBody");

    if (searchInput) {
      searchInput.addEventListener("input", (event) => {
        STATE.q = event.target.value || "";
        renderTable();
      });
    }

    if (sortSelect) {
      sortSelect.value = STATE.sort;
      sortSelect.addEventListener("change", (event) => {
        STATE.sort = event.target.value || "baseline";
        renderTable();
      });
    }

    if (riskWrap) {
      riskWrap.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-risk]");
        if (!btn) return;
        STATE.risk = btn.getAttribute("data-risk") || "all";
        Array.from(riskWrap.querySelectorAll("[data-risk]")).forEach((node) => {
          node.classList.toggle("active", node === btn);
        });
        renderTable();
      });
    }

    if (tbody) {
      tbody.addEventListener("click", async (event) => {
        const btn = event.target.closest("[data-copy-key]");
        if (!btn) return;
        const key = String(btn.getAttribute("data-copy-key") || "").trim();
        if (!key) return;
        const row = rawSessions().find((item) => String(item.session_id || "") === key);
        if (!row) return;
        try {
          await copyText(buildResetMessage(row));
          COPY_LABEL[key] = "已复制";
          renderTable();
          setTimeout(() => {
            if (COPY_LABEL[key] === "已复制") {
              COPY_LABEL[key] = "复制重置消息";
              renderTable();
            }
          }, 1600);
        } catch (_err) {
          COPY_LABEL[key] = "复制失败";
          renderTable();
          setTimeout(() => {
            if (COPY_LABEL[key] === "复制失败") {
              COPY_LABEL[key] = "复制重置消息";
              renderTable();
            }
          }, 1600);
        }
      });
    }
  }

  async function syncLiveSessionRows() {
    try {
      const resp = await fetch(liveSessionsEndpoint(), { credentials: "same-origin", cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      LIVE.rows = mergeLiveRows(payload.sessions || []);
      LIVE.syncAt = formatZhDateTime(new Date().toISOString());
      LIVE.error = "";
    } catch (err) {
      LIVE.error = (err && err.message) ? String(err.message) : "unknown";
    }
    renderChrome();
    renderTable();
  }

  async function loadHealthSnapshot() {
    try {
      const resp = await fetch(healthEndpoint(), { credentials: "same-origin", cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      applyHealthPayload(payload);
      LIVE.error = "";
    } catch (err) {
      LIVE.error = (err && err.message) ? String(err.message) : "unknown";
    }
    renderChrome();
    renderTable();
  }

  function updateProjectSummarySessionHealth(sessionHealth) {
    if (!sessionHealth || typeof sessionHealth !== "object") return;
    const pid = String(sessionHealth.project_id || currentProjectId()).trim();
    if (!Array.isArray(DATA.projects)) return;
    DATA.projects = DATA.projects.map((item) => {
      if (!item || String(item.project_id || "").trim() !== pid) return item;
      return {
        ...item,
        session_health: {
          ...(item.session_health && typeof item.session_health === "object" ? item.session_health : {}),
          ...sessionHealth,
        },
      };
    });
    if (String(DATA.project_id || "").trim() === pid) {
      DATA.session_health = {
        ...(DATA.session_health && typeof DATA.session_health === "object" ? DATA.session_health : {}),
        ...sessionHealth,
      };
    }
  }

  async function refreshHealthData() {
    LIVE.syncing = true;
    LIVE.error = "";
    renderChrome();
    try {
      const resp = await fetch(healthEndpoint({ refresh: true }), { credentials: "same-origin", cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      applyHealthPayload(payload);
      LIVE.rows = Array.isArray(DATA.sessions) ? DATA.sessions.filter((row) => row && !row.is_deleted) : [];
      LIVE.syncAt = formatZhDateTime(new Date().toISOString());
    } catch (err) {
      LIVE.error = (err && err.message) ? String(err.message) : "unknown";
    } finally {
      LIVE.syncing = false;
    }
    renderChrome();
    renderTable();
  }

  async function saveSessionHealthConfig() {
    const autoEnabledInput = document.getElementById("autoEnabledInput");
    const intervalSelect = document.getElementById("intervalSelect");
    const enabled = autoEnabledInput ? Boolean(autoEnabledInput.checked) : true;
    const intervalMinutes = intervalSelect ? Number(intervalSelect.value || 120) : 120;
    LIVE.savingConfig = true;
    LIVE.error = "";
    renderChrome();
    try {
      const resp = await fetch(healthEndpoint(), {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          project_id: currentProjectId(),
          enabled,
          interval_minutes: intervalMinutes,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      const sessionHealth = (payload.session_health && typeof payload.session_health === "object") ? payload.session_health : {};
      updateProjectSummarySessionHealth({
        ...sessionHealth,
        project_id: currentProjectId(),
        project_name: currentProjectName(),
      });
      if (!enabled) {
        LIVE.syncAt = new Date().toLocaleString("zh-CN", { hour12: false });
      }
    } catch (err) {
      LIVE.error = (err && err.message) ? String(err.message) : "unknown";
    } finally {
      LIVE.savingConfig = false;
    }
    renderChrome();
    renderTable();
  }

  renderChrome();
  bindFilters();
  renderTable();
  const refreshButton = document.getElementById("refreshButton");
  if (refreshButton) {
    refreshButton.addEventListener("click", () => {
      refreshHealthData();
    });
  }
  const saveConfigButton = document.getElementById("saveConfigButton");
  if (saveConfigButton) {
    saveConfigButton.addEventListener("click", () => {
      saveSessionHealthConfig();
    });
  }
  (async () => {
    await loadHealthSnapshot();
    await syncLiveSessionRows();
  })();
})();
