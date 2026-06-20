(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const STATE = {
    health: null,
    runs: [],
    runOffset: 0,
    runHasMore: false,
    loadingHealth: false,
    loadingRuns: false,
    dryRun: null,
    executeResult: null,
    sessionSearch: "",
    sessionSort: "hot",
    runSession: "",
    runStatus: "",
    runGroup: "",
    error: "",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function safeText(value) {
    return String(value == null ? "" : value).trim();
  }

  function fmtNumber(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toLocaleString("zh-CN") : "0";
  }

  function fmtBytes(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n) || n <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = n;
    let idx = 0;
    while (size >= 1024 && idx < units.length - 1) {
      size /= 1024;
      idx += 1;
    }
    return `${size.toFixed(size >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
  }

  function shortId(value, head = 8, tail = 6) {
    const text = safeText(value);
    if (text.length <= head + tail + 3) return text || "-";
    return `${text.slice(0, head)}...${text.slice(-tail)}`;
  }

  function pageParams() {
    const out = new URLSearchParams(window.location.search || "");
    const hash = safeText(window.location.hash).replace(/^#/, "");
    if (hash) {
      const hashParams = new URLSearchParams(hash);
      hashParams.forEach((value, key) => {
        if (!out.has(key)) out.set(key, value);
      });
    }
    return out;
  }

  function defaultProjectId() {
    const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
    const ids = projects.map((item) => safeText(item && item.project_id)).filter(Boolean);
    if (ids.includes("task_dashboard")) return "task_dashboard";
    return safeText(DATA.project_id) || ids[0] || "task_dashboard";
  }

  function currentProjectId() {
    const params = pageParams();
    return safeText(params.get("p") || params.get("projectId") || params.get("project_id") || defaultProjectId()) || "task_dashboard";
  }

  function currentProjectName() {
    const pid = currentProjectId();
    const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
    const row = projects.find((item) => safeText(item && item.project_id) === pid);
    return safeText((row && row.project_name) || DATA.project_name || pid) || pid;
  }

  function authHeaders(base = {}) {
    const headers = { ...base };
    try {
      const token = safeText(window.localStorage.getItem("taskDashboard.token"));
      if (token) headers["X-TaskDashboard-Token"] = token;
    } catch (_) {}
    return headers;
  }

  async function fetchJson(url, options = {}) {
    const resp = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: authHeaders(options.headers || {}),
    });
    let payload = {};
    try {
      payload = await resp.json();
    } catch (_) {}
    if (!resp.ok) {
      const err = new Error(safeText(payload.error) || `HTTP ${resp.status}`);
      err.status = resp.status;
      err.payload = payload;
      throw err;
    }
    return payload;
  }

  function linkHref(key, fallback) {
    const raw = safeText(LINKS[key] || DATA[key] || fallback);
    if (!raw) return fallback;
    return raw.startsWith("/") ? raw : `/share/${raw}`;
  }

  function healthUrl() {
    const params = new URLSearchParams();
    params.set("projectId", currentProjectId());
    return `/api/runstore/health?${params.toString()}`;
  }

  function hotRunsUrl(reset = false) {
    const params = new URLSearchParams();
    params.set("projectId", currentProjectId());
    params.set("limit", "50");
    params.set("offset", reset ? "0" : String(STATE.runOffset || 0));
    if (STATE.runSession) params.set("session_id", STATE.runSession);
    if (STATE.runStatus) params.set("status", STATE.runStatus);
    if (STATE.runGroup) params.set("state_group", STATE.runGroup);
    return `/api/runstore/hot-runs?${params.toString()}`;
  }

  function setQuickLinks() {
    const overview = $("overviewLink");
    const task = $("taskLink");
    const session = $("sessionHealthLink");
    if (overview) overview.href = linkHref("overview_page", "/share/project-overview-dashboard.html");
    if (task) task.href = linkHref("task_page", "/share/project-task-dashboard.html");
    if (session) session.href = linkHref("session_health_page", "/share/project-session-health-dashboard.html");
  }

  function renderHero() {
    const projectName = $("projectNameBadge");
    const projectId = $("projectIdMeta");
    const generated = $("generatedAtBadge");
    const apiState = $("apiStateText");
    if (projectName) projectName.textContent = currentProjectName();
    if (projectId) projectId.textContent = currentProjectId();
    if (generated) {
      generated.textContent = safeText((STATE.health && STATE.health.generated_at) || DATA.generated_at || "等待刷新");
    }
    if (apiState) {
      if (STATE.loadingHealth) apiState.textContent = "正在读取 RunStore API";
      else if (STATE.error) apiState.textContent = STATE.error;
      else apiState.textContent = "同源 RunStore API";
    }
    const refresh = $("refreshButton");
    if (refresh) refresh.disabled = !!STATE.loadingHealth;
  }

  function renderNotice() {
    const wrap = $("noticePanel");
    if (!wrap) return;
    if (STATE.error) {
      wrap.innerHTML = `
        <div>
          <div class="notice-title">RunStore API 当前不可用</div>
          <div class="muted">页面已加载，但真实健康摘要和归档操作依赖后端 /api/runstore/*。错误：${escapeHtml(STATE.error)}</div>
        </div>
        <span class="risk-pill critical">blocked</span>
      `;
      return;
    }
    const health = STATE.health || {};
    const hot = health.hot_summary || {};
    wrap.innerHTML = `
      <div>
        <div class="notice-title">治理边界</div>
        <div class="muted">本页只治理 hot 终态 run：不删除数据、不移动 attachments、不清理 archive、不改写 /api/codex/runs 语义。</div>
      </div>
      <span class="risk-pill ${escapeHtml((health.risk && health.risk.level) || "healthy")}">${escapeHtml((health.risk && health.risk.level) || "healthy")}</span>
    `;
    if (!Number(hot.run_count || 0)) {
      wrap.querySelector(".muted").textContent = "当前 hot 未读取到可展示 run；如果这是新环境，属于正常空态。";
    }
  }

  function metric(label, value, note) {
    return `
      <div class="metric-card">
        <span class="meta-label">${escapeHtml(label)}</span>
        <strong class="metric-value">${escapeHtml(value)}</strong>
        <span class="metric-note">${escapeHtml(note)}</span>
      </div>
    `;
  }

  function renderMetrics() {
    const wrap = $("metricGrid");
    if (!wrap) return;
    const health = STATE.health || {};
    const hot = health.hot_summary || {};
    const archive = health.archive_summary || {};
    wrap.innerHTML = [
      metric("hot run", fmtNumber(hot.run_count), `文件 ${fmtNumber(hot.file_count)} 个`),
      metric("终态可治理", fmtNumber(hot.terminal_run_count), `保护态 ${fmtNumber(hot.protected_run_count)}`),
      metric("hot 体积", fmtBytes(hot.bytes), "不含 attachments 移动范围"),
      metric("最老终态", shortTime(hot.oldest_terminal_at), "建议优先看 48h 前"),
      metric("archive", fmtNumber(archive.run_count), `${fmtBytes(archive.bytes)} · ${safeText(archive.scan_mode || "exact")}`),
      metric("会话数", fmtNumber((health.session_summaries || []).length), "按 hot 分布聚合"),
    ].join("");
  }

  function renderRisk() {
    const wrap = $("riskPanel");
    if (!wrap) return;
    const risk = (STATE.health && STATE.health.risk) || { level: "healthy", reasons: [], recommendation: "等待健康摘要" };
    const reasons = Array.isArray(risk.reasons) && risk.reasons.length ? risk.reasons.join(" / ") : "无触发项";
    wrap.innerHTML = `
      <div>
        <div class="risk-title">风险判断：${escapeHtml(risk.recommendation || "当前可继续观察")}</div>
        <div class="muted">触发原因：${escapeHtml(reasons)}</div>
      </div>
      <span class="risk-pill ${escapeHtml(risk.level || "healthy")}">${escapeHtml(risk.level || "healthy")}</span>
    `;
  }

  function sessionRows() {
    const rows = Array.isArray(STATE.health && STATE.health.session_summaries) ? STATE.health.session_summaries.slice() : [];
    const q = safeText(STATE.sessionSearch).toLowerCase();
    const filtered = q
      ? rows.filter((row) => `${safeText(row.channel_name)} ${safeText(row.agent_display_name)} ${safeText(row.session_id)}`.toLowerCase().includes(q))
      : rows;
    const sort = STATE.sessionSort;
    filtered.sort((a, b) => {
      if (sort === "terminal") return Number(b.terminal_run_count || 0) - Number(a.terminal_run_count || 0);
      if (sort === "bytes") return Number(b.bytes || 0) - Number(a.bytes || 0);
      if (sort === "oldest") return String(a.oldest_terminal_at || "9999").localeCompare(String(b.oldest_terminal_at || "9999"));
      return Number(b.hot_run_count || 0) - Number(a.hot_run_count || 0);
    });
    return filtered;
  }

  function renderSessions() {
    const body = $("sessionTableBody");
    if (!body) return;
    const rows = sessionRows();
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="7" class="empty-note">暂无会话级 hot 记录。</td></tr>`;
      return;
    }
    body.innerHTML = rows.map((row) => {
      const sid = safeText(row.session_id);
      const action = Number(row.terminal_run_count || 0) > 0 ? "可 dry-run" : "仅观察";
      return `
        <tr>
          <td>
            <div class="primary-cell">
              <span class="primary-title">${escapeHtml(row.agent_display_name || row.channel_name || "未命名会话")}</span>
              <span class="muted">${escapeHtml(row.channel_name || "-")}</span>
              <span class="mono muted" title="${escapeHtml(sid)}">${escapeHtml(shortId(sid))}</span>
            </div>
          </td>
          <td>${fmtNumber(row.hot_run_count)}</td>
          <td>${fmtNumber(row.terminal_run_count)}</td>
          <td>${fmtNumber(row.protected_run_count)}</td>
          <td>${fmtBytes(row.bytes)}</td>
          <td>${escapeHtml(shortTime(row.oldest_terminal_at))}</td>
          <td><button class="ghost-btn use-session-btn" type="button" data-session="${escapeHtml(sid)}">${escapeHtml(action)}</button></td>
        </tr>
      `;
    }).join("");
    body.querySelectorAll(".use-session-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sid = safeText(btn.getAttribute("data-session"));
        if (!sid) return;
        const scope = $("archiveScopeSelect");
        const session = $("archiveSessionSelect");
        if (scope) scope.value = "session";
        if (session) session.value = sid;
        STATE.runSession = sid;
        const filter = $("runSessionFilter");
        if (filter) filter.value = sid;
        refreshRunList(true);
      });
    });
  }

  function populateSessionSelects() {
    const rows = Array.isArray(STATE.health && STATE.health.session_summaries) ? STATE.health.session_summaries : [];
    const options = rows
      .filter((row) => safeText(row.session_id))
      .map((row) => `<option value="${escapeHtml(row.session_id)}">${escapeHtml((row.agent_display_name || row.channel_name || "会话") + " · " + shortId(row.session_id))}</option>`)
      .join("");
    const archiveSelect = $("archiveSessionSelect");
    const runSelect = $("runSessionFilter");
    if (archiveSelect) {
      archiveSelect.innerHTML = options || `<option value="">暂无会话</option>`;
      archiveSelect.disabled = !options;
    }
    if (runSelect) {
      const current = runSelect.value;
      runSelect.innerHTML = `<option value="">全部会话</option>${options}`;
      runSelect.value = current;
    }
  }

  function renderRunTable() {
    const body = $("runTableBody");
    if (!body) return;
    const rows = Array.isArray(STATE.runs) ? STATE.runs : [];
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="6" class="empty-note">${STATE.loadingRuns ? "正在加载..." : "暂无 hot run 摘要。"}</td></tr>`;
    } else {
      body.innerHTML = rows.map((row) => `
        <tr>
          <td>
            <div class="primary-cell">
              <span class="mono primary-title">${escapeHtml(shortId(row.run_id, 12, 8))}</span>
              <span class="muted">${escapeHtml(row.summary || row.channel_name || "-")}</span>
            </div>
          </td>
          <td><span class="state-pill ${escapeHtml(row.state_group || "unknown")}">${escapeHtml(row.status || "unknown")}</span></td>
          <td><span class="mono" title="${escapeHtml(row.session_id)}">${escapeHtml(shortId(row.session_id))}</span></td>
          <td>${escapeHtml(shortTime(row.anchor_at))}</td>
          <td>${fmtBytes(row.bytes)}</td>
          <td>${row.archive_eligible ? "可归档" : escapeHtml(row.archive_excluded_reason || "不可归档")}</td>
        </tr>
      `).join("");
    }
    const more = $("loadMoreRunsButton");
    if (more) {
      more.disabled = STATE.loadingRuns || !STATE.runHasMore;
      more.textContent = STATE.runHasMore ? "加载更多" : "没有更多";
    }
  }

  function archiveWindowPayload() {
    const value = safeText($("archiveWindowSelect") && $("archiveWindowSelect").value) || "48h";
    if (value === "24h") return { older_than_hours: 24 };
    if (value === "48h") return { older_than_hours: 48 };
    if (value === "7d") return { older_than_days: 7 };
    const days = Math.max(1, Math.min(Number($("customDaysInput") && $("customDaysInput").value) || 3, 365));
    return { older_than_days: days };
  }

  function renderDryRun() {
    const wrap = $("dryRunResult");
    const box = $("executeBox");
    const execute = $("executeButton");
    if (!wrap) return;
    const plan = STATE.dryRun;
    if (!plan) {
      wrap.classList.remove("show");
      if (box) box.classList.remove("active");
      if (execute) execute.disabled = true;
      return;
    }
    wrap.classList.add("show");
    wrap.innerHTML = `
      <div class="notice-title">Dry-run 结果 · ${escapeHtml(plan.job_id || "-")}</div>
      <div class="result-grid">
        ${resultCard("预计归档", fmtNumber(plan.eligible_count), "eligible run")}
        ${resultCard("预计体积", fmtBytes(plan.estimated_bytes), "hot 文件组")}
        ${resultCard("排除", fmtNumber(plan.excluded_count), `保护态 ${fmtNumber(plan.excluded_active_count)}`)}
        ${resultCard("cutoff", shortTime(plan.cutoff_at), plan.cutoff_source || "-")}
        ${resultCard("过期时间", shortTime(plan.expires_at), "execute 前有效")}
      </div>
      <p class="result-note">样本 run：${escapeHtml((plan.sample_run_ids || []).slice(0, 8).map((x) => shortId(x, 12, 6)).join(" / ") || "无")}</p>
      <p class="result-note">安全边界：will_move_attachments=${String(!!plan.will_move_attachments)}，will_delete_files=${String(!!plan.will_delete_files)}</p>
    `;
    renderExecuteState();
  }

  function resultCard(label, value, note) {
    return `<div class="result-card"><span class="meta-label">${escapeHtml(label)}</span><strong class="meta-value">${escapeHtml(value)}</strong><span class="meta-note">${escapeHtml(note)}</span></div>`;
  }

  function renderExecuteState() {
    const execute = $("executeButton");
    const confirm = $("executeConfirmInput");
    const plan = STATE.dryRun;
    if (execute) {
      execute.disabled = !plan || !Number(plan.eligible_count || 0) || !(confirm && confirm.checked);
    }
  }

  function renderExecuteResult() {
    const wrap = $("executeResult");
    if (!wrap) return;
    const result = STATE.executeResult;
    if (!result) {
      wrap.classList.remove("show");
      return;
    }
    wrap.classList.add("show");
    wrap.innerHTML = `
      <div class="notice-title">执行结果 · ${escapeHtml(result.execute_state || "-")}</div>
      <div class="result-grid">
        ${resultCard("已归档", fmtNumber(result.archived_count), fmtBytes(result.archived_bytes))}
        ${resultCard("跳过", fmtNumber(result.skipped_count), "重验保护")}
        ${resultCard("失败", fmtNumber(result.failed_count), "需人工查看")}
        ${resultCard("manifest", shortId(result.manifest_id, 16, 6), "已写入")}
        ${resultCard("附件移动", String(!!result.will_move_attachments), "必须为 false")}
      </div>
      <p class="result-note mono">${escapeHtml(result.manifest_path || "")}</p>
      <p class="result-note">${escapeHtml((result.rollback_hint && result.rollback_hint.summary) || "")}</p>
    `;
  }

  function renderAll() {
    renderHero();
    renderNotice();
    renderMetrics();
    renderRisk();
    populateSessionSelects();
    renderSessions();
    renderRunTable();
    renderDryRun();
    renderExecuteResult();
  }

  async function loadHealth() {
    STATE.loadingHealth = true;
    STATE.error = "";
    renderHero();
    try {
      STATE.health = await fetchJson(healthUrl());
    } catch (err) {
      STATE.error = (err && err.message) ? String(err.message) : "unknown";
    } finally {
      STATE.loadingHealth = false;
    }
    renderAll();
  }

  async function refreshRunList(reset = false) {
    STATE.loadingRuns = true;
    if (reset) {
      STATE.runOffset = 0;
      STATE.runs = [];
    }
    renderRunTable();
    try {
      const payload = await fetchJson(hotRunsUrl(reset));
      const rows = Array.isArray(payload.runs) ? payload.runs : [];
      STATE.runs = reset ? rows : STATE.runs.concat(rows);
      const page = payload.pagination || {};
      STATE.runOffset = Number(page.offset || 0) + Number(page.returned || rows.length || 0);
      STATE.runHasMore = !!page.has_more;
    } catch (err) {
      STATE.error = (err && err.message) ? String(err.message) : "unknown";
    } finally {
      STATE.loadingRuns = false;
    }
    renderAll();
  }

  async function runDryRun() {
    const scope = safeText($("archiveScopeSelect") && $("archiveScopeSelect").value) || "all";
    const sessionId = safeText($("archiveSessionSelect") && $("archiveSessionSelect").value);
    if (scope === "session" && !sessionId) {
      STATE.error = "请选择会话";
      renderAll();
      return;
    }
    STATE.error = "";
    STATE.executeResult = null;
    const body = {
      project_id: currentProjectId(),
      scope,
      session_id: scope === "session" ? sessionId : "",
      limit: 500,
      reason: "manual_cleanup_from_runstore_health",
      ...archiveWindowPayload(),
    };
    const btn = $("dryRunButton");
    if (btn) btn.disabled = true;
    try {
      STATE.dryRun = await fetchJson("/api/runstore/archive/dry-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const confirm = $("executeConfirmInput");
      if (confirm) confirm.checked = false;
    } catch (err) {
      STATE.error = (err && err.message) ? String(err.message) : "unknown";
    } finally {
      if (btn) btn.disabled = false;
    }
    renderAll();
  }

  async function executeArchive() {
    const plan = STATE.dryRun || {};
    if (!plan.job_id) return;
    const btn = $("executeButton");
    if (btn) btn.disabled = true;
    STATE.error = "";
    try {
      STATE.executeResult = await fetchJson("/api/runstore/archive/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: plan.job_id,
          confirm: true,
          expected_eligible_count: Number(plan.eligible_count || 0),
        }),
      });
      await loadHealth();
      await refreshRunList(true);
    } catch (err) {
      STATE.error = (err && err.message) ? String(err.message) : "unknown";
    } finally {
      renderAll();
    }
  }

  function shortTime(value) {
    const text = safeText(value);
    if (!text) return "-";
    return text.replace("T", " ").replace(/([+-]\d{2}:?\d{2}|Z)$/i, "");
  }

  function escapeHtml(value) {
    return safeText(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function bindEvents() {
    const refresh = $("refreshButton");
    const loadRuns = $("loadRunsButton");
    const loadMore = $("loadMoreRunsButton");
    const dryRun = $("dryRunButton");
    const execute = $("executeButton");
    const confirm = $("executeConfirmInput");
    const search = $("sessionSearchInput");
    const sort = $("sessionSortSelect");
    const runSession = $("runSessionFilter");
    const runStatus = $("runStatusFilter");
    const runGroup = $("runGroupFilter");
    if (refresh) refresh.addEventListener("click", loadHealth);
    if (loadRuns) loadRuns.addEventListener("click", () => refreshRunList(true));
    if (loadMore) loadMore.addEventListener("click", () => refreshRunList(false));
    if (dryRun) dryRun.addEventListener("click", runDryRun);
    if (execute) execute.addEventListener("click", executeArchive);
    if (confirm) confirm.addEventListener("change", renderExecuteState);
    if (search) search.addEventListener("input", () => {
      STATE.sessionSearch = search.value;
      renderSessions();
    });
    if (sort) sort.addEventListener("change", () => {
      STATE.sessionSort = sort.value;
      renderSessions();
    });
    if (runSession) runSession.addEventListener("change", () => {
      STATE.runSession = runSession.value;
      refreshRunList(true);
    });
    if (runStatus) runStatus.addEventListener("change", () => {
      STATE.runStatus = runStatus.value;
      refreshRunList(true);
    });
    if (runGroup) runGroup.addEventListener("change", () => {
      STATE.runGroup = runGroup.value;
      refreshRunList(true);
    });
  }

  setQuickLinks();
  bindEvents();
  renderAll();
  loadHealth().then(() => refreshRunList(true));
})();
