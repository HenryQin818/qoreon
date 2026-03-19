    const DATA = JSON.parse(document.getElementById("data").textContent);
    const OVER = DATA.overview || { totals: {}, projects: [] };
    const taskBase = (DATA.links && DATA.links.task_page) ? String(DATA.links.task_page) : "/share/project-task-dashboard.html";
    const communicationBase = DATA.communication_page
      ? String(DATA.communication_page)
      : ((DATA.links && DATA.links.communication_page)
      ? String(DATA.links.communication_page)
      : "/share/project-communication-audit.html");
    const statusReportBase = DATA.status_report_page
      ? String(DATA.status_report_page)
      : ((DATA.links && DATA.links.status_report_page)
      ? String(DATA.links.status_report_page)
      : "/share/project-status-report.html");
    const TOKEN_KEY = "taskDashboard.token";

    const STATE = {
      q: "",
      showStats: true,
      sort: "risk",
      projectFilters: [],
    };
    const PROJECT_FILTER_UI = {
      draftIds: [],
    };
    const CFG = {
      opened: false,
      savingGlobal: false,
      loading: false,
    };

    function firstNonEmptyText(list, fallback = "") {
      const arr = Array.isArray(list) ? list : [];
      for (const item of arr) {
        const text = String(item == null ? "" : item).trim();
        if (text) return text;
      }
      return String(fallback || "").trim();
    }

    function normalizeEnvironmentName(raw) {
      return String(raw || "").trim().toLowerCase() || "stable";
    }

    function isStableEnvironment(raw) {
      return normalizeEnvironmentName(raw) === "stable";
    }

    function shouldUseStableDisplayCopy() {
      return isStableEnvironment((DATA && DATA.environment) || "stable");
    }

    function formatEnvironmentBadgeLabel(info) {
      const env = normalizeEnvironmentName(info && info.environment);
      if (isStableEnvironment(env)) return "生产环境";
      return "开发环境 · " + env;
    }

    function normalizeProjectSourceKind(raw) {
      const text = String(raw || "").trim().toLowerCase();
      if (!text) return "";
      if (text === "fixture" || text === "fixtures" || text === "demo") return "fixtures";
      if (text === "sandbox" || text === "refactor") return "sandbox";
      if (text === "workspace" || text === "repo" || text === "worktree") return "real";
      if (text === "real" || text === "prod" || text === "stable") return "real";
      return text;
    }

    function inferProjectSourceKind(projectLike) {
      const project = (projectLike && typeof projectLike === "object") ? projectLike : {};
      const explicitKind = normalizeProjectSourceKind(
        project.source_kind || project.sourceKind || project.project_source_kind || project.projectSourceKind
      );
      if (explicitKind) return explicitKind;
      const values = [
        project.project_root_rel,
        project.projectRootRel,
        project.task_root_rel,
        project.taskRootRel,
        project.runtime_root_rel,
        project.runtimeRootRel,
      ].map((value) => String(value || "").toLowerCase());
      if (values.some((value) => value.includes("/fixtures/") || value.includes("fixtures/") || value.includes("（fixtures）") || value.includes("(fixtures)"))) {
        return "fixtures";
      }
      if (values.some((value) => value.includes("/sandbox_projects/") || value.includes("sandbox_projects/") || value.includes("沙箱"))) {
        return "sandbox";
      }
      return "real";
    }

    function projectSourceBadgeText(kind, fallback = "") {
      if (kind === "fixtures") return "演示数据";
      if (kind === "sandbox") return "沙箱项目";
      if (kind === "real") return "真实项目";
      return String(fallback || kind || "").trim() || "项目来源";
    }

    function buildProjectSourceBadge(projectLike) {
      const project = (projectLike && typeof projectLike === "object") ? projectLike : {};
      const kind = inferProjectSourceKind(project);
      const label = String(project.source_label || project.sourceLabel || "").trim();
      const badge = el("span", {
        class: "source-chip" + (kind ? (" is-" + kind) : ""),
        text: projectSourceBadgeText(kind, label),
      });
      const titleParts = ["项目来源: " + projectSourceBadgeText(kind, label)];
      const projectRoot = String(project.project_root_rel || project.projectRootRel || "").trim();
      const taskRoot = String(project.task_root_rel || project.taskRootRel || "").trim();
      if (projectRoot) titleParts.push("project_root: " + projectRoot);
      if (taskRoot) titleParts.push("task_root: " + taskRoot);
      badge.title = titleParts.join("\n");
      return badge;
    }

    function stableProjectDescriptionByKind(projectLike) {
      const kind = inferProjectSourceKind(projectLike);
      if (kind === "fixtures") return "用于演示样例查看与看板展示。";
      if (kind === "sandbox") return "用于测试验证、会话协同与看板联调。";
      return "用于项目任务、会话协同与看板跟踪。";
    }

    function sanitizeStableNameText(raw) {
      let text = String(raw || "").trim();
      if (!text) return "";
      text = text.replace(/\s*[（(]开发[)）]\s*$/u, "");
      text = text.replace(/\s*[（(]refactor[)）]\s*$/iu, "");
      return text.trim();
    }

    function displayProjectName(projectLike) {
      const project = (projectLike && typeof projectLike === "object") ? projectLike : {};
      const raw = String(firstNonEmptyText([
        project.project_name,
        project.projectName,
        project.name,
        project.project_id,
        project.id,
      ]) || "").trim();
      if (!shouldUseStableDisplayCopy()) return raw;
      return sanitizeStableNameText(raw) || raw;
    }

    function displayProjectDescription(projectLike) {
      const project = (projectLike && typeof projectLike === "object") ? projectLike : {};
      const raw = String(firstNonEmptyText([
        project.description,
        project.project_description,
        project.projectDescription,
      ]) || "").trim();
      if (!shouldUseStableDisplayCopy()) return raw;
      if (!raw) return stableProjectDescriptionByKind(project);
      let text = raw;
      text = text.replace(/refactor\s*开发环境/giu, "生产环境");
      text = text.replace(/仅承接研发会话、拆解任务与测试验证，不读取生产项目真源。?/giu, "用于项目任务、会话协同与看板跟踪。");
      text = text.replace(/专用于\s*refactor\s*开发环境测试、初始化验证与冒烟编排，不承接正式业务数据。?/giu, "用于测试验证、会话协同与看板联调。");
      text = text.replace(/专用于开发环境对话创建、派发与回复链路验证，不承接正式业务数据。?/giu, "用于测试验证、会话协同与回复链路联调。");
      text = text.replace(/refactor\s*sandbox\s*数据源，仅承接/giu, "");
      text = text.replace(/refactor\s*fixtures\s*数据源，仅承接/giu, "");
      text = text.replace(/\brefactor\b/giu, "");
      text = text.replace(/\s{2,}/g, " ").trim();
      if (!text || /(?:sandbox|fixtures|开发环境测试)/u.test(text)) {
        return stableProjectDescriptionByKind(project);
      }
      return text;
    }

    function displayDashboardTitle(raw) {
      const title = String(raw || "").trim() || "项目总揽";
      if (!shouldUseStableDisplayCopy()) return title;
      return title
        .replace(/\s*[（(]refactor[)）]\s*$/iu, "")
        .replace(/\s*[（(]开发[)）]\s*$/u, "")
        .trim() || "项目总揽";
    }

    function renderEnvironmentBadge(info) {
      const badge = document.getElementById("envBadge");
      if (!badge) return;
      if (!info || !info.ok) {
        badge.hidden = true;
        badge.textContent = "";
        badge.classList.remove("is-stable", "is-verify");
        badge.removeAttribute("title");
        return;
      }
      const env = normalizeEnvironmentName(info.environment);
      badge.hidden = false;
      badge.textContent = formatEnvironmentBadgeLabel(info);
      badge.classList.toggle("is-stable", isStableEnvironment(env));
      badge.classList.toggle("is-verify", !isStableEnvironment(env));
      const titleParts = [
        "环境: " + env,
        "端口: " + String(info.port || "-"),
      ];
      if (info.worktreeRoot) titleParts.push("工作树: " + String(info.worktreeRoot));
      badge.title = titleParts.join("\n");
    }

    async function loadHealthInfo() {
      try {
        const resp = await fetch("/__health", { cache: "no-store" });
        if (!resp.ok) return null;
        return await resp.json();
      } catch (_) {
        return null;
      }
    }

    function el(tag, attrs = {}, children = []) {
      const n = document.createElement(tag);
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") n.className = v;
        else if (k === "text") n.textContent = v;
        else if (k === "html") n.innerHTML = v;
        else n.setAttribute(k, v);
      }
      for (const c of children) n.appendChild(c);
      return n;
    }

    function toTaskUrl(projectId, channelName) {
      const params = new URLSearchParams();
      params.set("p", String(projectId || ""));
      if (channelName) params.set("c", String(channelName));
      params.set("vm", "w");
      return taskBase + "#" + params.toString();
    }
    function openCommunicationPage() {
      const url = String(communicationBase || "/share/project-communication-audit.html").trim();
      if (!url) return;
      window.open(url, "_blank", "noopener,noreferrer");
    }
    function openStatusReportPage() {
      const url = String(statusReportBase || "/share/project-status-report.html").trim();
      if (!url) return;
      window.open(url, "_blank", "noopener,noreferrer");
    }
    function fmt(v) { return String(v == null ? 0 : v); }

    function applyStateToDom() {
      document.body.classList.toggle("stats-off", !STATE.showStats);
      const sortBtn = document.getElementById("sortBtn");
      if (sortBtn) sortBtn.textContent = STATE.sort === "name" ? "按名称" : "按优先级";
      const statsBtn = document.getElementById("statsBtn");
      if (statsBtn) statsBtn.textContent = STATE.showStats ? "隐藏统计" : "显示统计";
    }

    function setMeta(text) {
      const m = document.getElementById("meta");
      if (m) m.textContent = String(text || "");
    }

    function allProjectIds() {
      return (Array.isArray(OVER.projects) ? OVER.projects : [])
        .map((p) => String((p && p.project_id) || "").trim())
        .filter(Boolean);
    }

    function normalizeProjectFilterIds(raw, validIds = null) {
      let arr = [];
      if (Array.isArray(raw)) {
        arr = raw.map((x) => String(x || "").trim()).filter(Boolean);
      } else if (typeof raw === "string") {
        const s = String(raw || "").trim();
        if (!s) arr = [];
        else {
          try {
            const parsed = JSON.parse(s);
            if (Array.isArray(parsed)) arr = parsed.map((x) => String(x || "").trim()).filter(Boolean);
            else arr = [s];
          } catch (_) {
            arr = [s];
          }
        }
      }
      const uniq = [];
      const seen = new Set();
      for (const id of arr) {
        if (seen.has(id)) continue;
        seen.add(id);
        if (validIds && !validIds.has(id)) continue;
        uniq.push(id);
      }
      return uniq;
    }

    function selectedProjectFilterSet(source = null) {
      const ref = source == null ? STATE.projectFilters : source;
      return new Set(normalizeProjectFilterIds(ref));
    }

    function isProjectFilterNarrowing(ids = null) {
      const selected = normalizeProjectFilterIds(ids == null ? STATE.projectFilters : ids);
      const allIds = allProjectIds();
      if (!allIds.length) return false;
      if (selected.length !== allIds.length) return true;
      const allSet = new Set(allIds);
      return selected.some((id) => !allSet.has(id));
    }

    function projectFilterLabel() {
      const ids = normalizeProjectFilterIds(STATE.projectFilters);
      if (!ids.length) return "";
      const all = Array.isArray(OVER.projects) ? OVER.projects : [];
      const nameMap = new Map(all.map((p) => [String((p && p.project_id) || ""), displayProjectName(p)]));
      if (ids.length === 1) {
        const only = ids[0];
        return nameMap.get(only) || only;
      }
      return ids.length + "个项目";
    }

    function renderProjectFilterOptions() {
      const list = document.getElementById("projectFilterList");
      if (!list) return;
      const checkedSet = selectedProjectFilterSet(PROJECT_FILTER_UI.draftIds);
      const all = Array.isArray(OVER.projects) ? OVER.projects.slice() : [];
      all.sort((a, b) => displayProjectName(a).localeCompare(displayProjectName(b), "zh-Hans-CN"));
      list.innerHTML = "";
      if (!all.length) {
        list.appendChild(el("div", { class: "project-filter-item-name", text: "暂无项目" }));
        return;
      }
      for (const p of all) {
        const pid = String((p && p.project_id) || "").trim();
        if (!pid) continue;
        const label = displayProjectName(p) || pid;
        const row = el("label", { class: "project-filter-item" });
        const ck = document.createElement("input");
        ck.type = "checkbox";
        ck.value = pid;
        ck.checked = checkedSet.has(pid);
        ck.addEventListener("change", () => {
          const nextSet = selectedProjectFilterSet(PROJECT_FILTER_UI.draftIds);
          if (ck.checked) nextSet.add(pid);
          else nextSet.delete(pid);
          PROJECT_FILTER_UI.draftIds = normalizeProjectFilterIds(Array.from(nextSet));
          renderProjectFilterOptions();
        });
        row.appendChild(ck);
        row.appendChild(el("span", { class: "project-filter-item-name", text: label }));
        list.appendChild(row);
      }
    }

    function setProjectFilterPopover(opened) {
      const wrap = document.getElementById("projectFilterWrap");
      const pop = document.getElementById("projectFilterPop");
      if (!wrap || !pop) return;
      pop.hidden = !opened;
      wrap.classList.toggle("open", !!opened);
      if (opened) {
        PROJECT_FILTER_UI.draftIds = normalizeProjectFilterIds(STATE.projectFilters);
        renderProjectFilterOptions();
      }
    }

    function applyProjectFilterFromValues(values) {
      const validIds = new Set((Array.isArray(OVER.projects) ? OVER.projects : []).map((p) => String((p && p.project_id) || "")));
      const next = normalizeProjectFilterIds(values, validIds);
      STATE.projectFilters = next;
      try { localStorage.setItem("overview.projectFilter", JSON.stringify(next)); } catch (_) {}
      const btn = document.getElementById("projectFilterBtn");
      if (btn) {
        const active = isProjectFilterNarrowing(next);
        btn.classList.toggle("active", active);
        btn.title = active ? ("项目筛选：" + projectFilterLabel()) : "项目筛选";
      }
      renderCards();
    }

    function matchesQuery(project, q) {
      const needle = String(q || "").trim().toLowerCase();
      if (!needle) return true;
      const hay = [
        displayProjectName(project) || project.project_id || "",
        displayProjectDescription(project),
      ].join(" ").toLowerCase();
      return hay.includes(needle);
    }

    function num(v) { const n = Number(v || 0); return Number.isFinite(n) ? n : 0; }
    function riskScore(p) {
      const t = (p && p.totals) ? p.totals : {};
      return num(t.supervised) * 1000000 + num(t.in_progress) * 10000 + num(t.active) * 100 + num(t.total);
    }
    function fmtPct(done, total) {
      const d = num(done), t = Math.max(0, num(total));
      if (!t) return "0%";
      const pct = Math.round((d / t) * 100);
      return String(Math.max(0, Math.min(100, pct))) + "%";
    }

    function parseDateTime(ts) {
      const raw = String(ts || "").trim();
      if (!raw) return null;
      let s = raw;
      if (/[\+\-]\d{4}$/.test(s)) s = s.replace(/([\+\-]\d{2})(\d{2})$/, "$1:$2");
      const d = new Date(s);
      if (!Number.isNaN(d.getTime())) return d;
      const d2 = new Date(raw.replace(" ", "T"));
      if (!Number.isNaN(d2.getTime())) return d2;
      return null;
    }
    function dateKeyLocal(d) {
      const pad2 = (n) => String(n).padStart(2, "0");
      return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
    }
    function lastNDaysKeys(n) {
      const out = [];
      const now = new Date();
      const base = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      for (let i = n - 1; i >= 0; i--) {
        const d = new Date(base.getTime() - i * 86400000);
        out.push(dateKeyLocal(d));
      }
      return out;
    }

    function authHeaders(base = {}) {
      const h = Object.assign({}, base || {});
      try {
        const tok = (localStorage.getItem(TOKEN_KEY) || "").trim();
        if (tok) h["X-TaskDashboard-Token"] = tok;
      } catch (_) {}
      return h;
    }

    async function fetchJson(url, options = {}) {
      const opt = Object.assign({}, options || {});
      opt.headers = authHeaders(opt.headers || {});
      const resp = await fetch(url, opt);
      let data = null;
      try {
        data = await resp.json();
      } catch (_) {
        data = null;
      }
      if (!resp.ok) {
        const msg = (data && data.error) ? String(data.error) : ("HTTP " + resp.status);
        throw new Error(msg);
      }
      return data || {};
    }

    function cfgMsg(text, cls = "") {
      const n = document.getElementById("cfgMessage");
      if (!n) return;
      n.className = "cfg-message" + (cls ? (" " + cls) : "");
      n.textContent = String(text || "");
    }

    function setCfgOpened(opened) {
      CFG.opened = !!opened;
      document.body.classList.toggle("cfg-open", CFG.opened);
      const mask = document.getElementById("cfgMask");
      if (mask) mask.hidden = !CFG.opened;
      const drawer = document.getElementById("cfgDrawer");
      if (drawer) drawer.setAttribute("aria-hidden", CFG.opened ? "false" : "true");
      if (!CFG.opened) cfgMsg("");
    }

    function parseOptInt(v) {
      const s = String(v == null ? "" : v).trim();
      if (!s) return null;
      const n = Number(s);
      if (!Number.isFinite(n)) return null;
      return Math.trunc(n);
    }

    function renderCliTools(cliTools) {
      const summaryEl = document.getElementById("cfgCliSummary");
      const listEl = document.getElementById("cfgCliList");
      if (!summaryEl || !listEl) return;

      const available = Array.isArray(cliTools?.available) ? cliTools.available : [];
      const byCli = Array.isArray(cliTools?.configured?.by_cli) ? cliTools.configured.by_cli : [];
      const rows = byCli.length ? byCli : available;
      const linkableCount = available.filter((x) => x && x.enabled !== false).length;
      const configuredCount = byCli.filter((x) => x && x.configured).length;
      summaryEl.textContent = `可联通 ${linkableCount}/${available.length || rows.length}；已配置 ${configuredCount}`;

      listEl.innerHTML = "";
      if (!rows.length) {
        const empty = document.createElement("div");
        empty.className = "cfg-hint";
        empty.textContent = "暂无 CLI 配置数据";
        listEl.appendChild(empty);
        return;
      }
      for (const row of rows) {
        const id = String((row && row.id) || "");
        const name = String((row && row.name) || id || "-");
        const enabled = row && row.enabled !== false;
        const configured = !!(row && row.configured);
        const channelCount = Number((row && row.effective_channel_count) || 0);
        const sessionCount = Number((row && row.session_binding_count) || 0);

        const wrap = document.createElement("div");
        wrap.className = "cfg-cli-row";

        const left = document.createElement("div");
        left.className = "cfg-cli-left";
        const nameEl = document.createElement("span");
        nameEl.className = "cfg-cli-name";
        nameEl.textContent = name;
        const idEl = document.createElement("span");
        idEl.className = "cfg-cli-id";
        idEl.textContent = id;
        left.appendChild(nameEl);
        left.appendChild(idEl);

        const right = document.createElement("div");
        right.className = "cfg-cli-meta";
        const p1 = document.createElement("span");
        p1.className = "cfg-pill " + (enabled ? "ok" : "warn");
        p1.textContent = enabled ? "可联通" : "未启用";
        const p2 = document.createElement("span");
        p2.className = "cfg-pill " + (configured ? "ok" : "");
        p2.textContent = configured ? `已配置 通道${channelCount} 会话${sessionCount}` : "未配置";
        right.appendChild(p1);
        right.appendChild(document.createTextNode(" "));
        right.appendChild(p2);

        wrap.appendChild(left);
        wrap.appendChild(right);
        listEl.appendChild(wrap);
      }
    }

    function fillConfigForm(payload) {
      const global = (payload && payload.global) || {};
      const maxC = document.getElementById("cfgMaxConcurrency");
      if (maxC) maxC.value = String(global.max_concurrency == null ? "" : global.max_concurrency);
      const globalHint = document.getElementById("cfgGlobalHint");
      if (globalHint) {
        const src = String(global.max_concurrency_source || "default");
        globalHint.textContent = "当前来源：" + src + "；保存后需重启本机服务生效";
      }
      const bind = document.getElementById("cfgBind");
      if (bind) bind.textContent = String(global.bind || "-");
      const schedulerEngine = document.getElementById("cfgSchedulerEngine");
      if (schedulerEngine) {
        const enabled = global.scheduler_engine_enabled ? "enabled" : "disabled";
        const source = String(global.scheduler_engine_source || "default");
        schedulerEngine.textContent = `${enabled} (${source})`;
      }
      const tokenRequired = document.getElementById("cfgTokenRequired");
      if (tokenRequired) tokenRequired.textContent = global.token_required ? "开启" : "关闭";
      const withLocal = document.getElementById("cfgWithLocalConfig");
      if (withLocal) withLocal.textContent = global.with_local_config ? "开启" : "关闭";
      renderCliTools(global.cli_tools || {});
    }

    async function loadPlatformConfig() {
      CFG.loading = true;
      cfgMsg("正在读取配置...");
      try {
        const data = await fetchJson("/api/config/effective");
        fillConfigForm(data);
        cfgMsg("配置已加载", "ok");
      } catch (e) {
        cfgMsg("读取失败：" + (e && e.message ? e.message : e), "err");
      } finally {
        CFG.loading = false;
      }
    }

    async function saveGlobalConfig() {
      if (CFG.savingGlobal) return;
      const n = parseOptInt(document.getElementById("cfgMaxConcurrency")?.value);
      if (n == null || n < 1 || n > 32) {
        cfgMsg("并发上限需在 1-32 之间", "err");
        return;
      }
      CFG.savingGlobal = true;
      cfgMsg("正在保存全局配置...");
      try {
        await fetchJson("/api/config/global", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ max_concurrency: n }),
        });
        cfgMsg("全局配置已保存，重启服务后生效", "ok");
      } catch (e) {
        cfgMsg("保存失败：" + (e && e.message ? e.message : e), "err");
      } finally {
        CFG.savingGlobal = false;
      }
    }

    function getAvatarLibraryLinks() {
      const origin = /^https?:\/\//.test(window.location.origin || "")
        ? window.location.origin
        : ((window.location.protocol && window.location.host)
          ? `${window.location.protocol}//${window.location.host}`
          : "http://127.0.0.1:18770");
      return {
        primary: new URL("/share/avatar-library.html", origin).toString(),
        fallback: new URL("/dist/avatar-library.html", origin).toString(),
      };
    }

    function renderAvatarLibraryEntry() {
      const urlEl = document.getElementById("cfgAvatarLibraryUrl");
      if (!urlEl) return;
      const links = getAvatarLibraryLinks();
      urlEl.textContent = links.primary;
      urlEl.title = `主链接: ${links.primary}\n兜底链接: ${links.fallback}`;
    }

    async function copyAvatarLibraryLink() {
      const links = getAvatarLibraryLinks();
      const text = `主链接: ${links.primary}\n兜底链接: ${links.fallback}`;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
          cfgMsg("头像库链接已复制", "ok");
          return;
        }
      } catch (_) {}

      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
      ta.remove();
      cfgMsg(ok ? "头像库链接已复制" : "复制失败，请手动复制", ok ? "ok" : "err");
    }

    // ========== SVG Helpers ==========
    function svgEl(tag, attrs = {}) {
      const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
      return n;
    }

    function createGradient(svg, id, stops, vertical = true) {
      const attrs = vertical
        ? { id, x1: "0%", y1: "0%", x2: "0%", y2: "100%" }
        : { id, x1: "0%", y1: "0%", x2: "100%", y2: "0%" };
      const grad = svgEl("linearGradient", attrs);
      for (const s of stops) {
        grad.appendChild(svgEl("stop", { offset: s.offset + "%", "stop-color": s.color }));
      }
      svg.appendChild(grad);
    }

    // Combined chart: bars + line
    function combinedChartSvg(series, labels, ariaLabel) {
      const w = 600, h = 80, pad = 4;
      const n = labels.length || 1;

      // Find max across all series
      let maxVal = 1;
      for (const s of series) {
        if (s.values) {
          const m = Math.max(...s.values.map(x => num(x)));
          if (m > maxVal) maxVal = m;
        }
      }

      const svg = svgEl("svg", {
        class: "trend-chart",
        viewBox: `0 0 ${w} ${h}`,
        role: "img",
        "aria-label": ariaLabel,
        preserveAspectRatio: "none"
      });

      const sx = (i) => pad + (i * (w - pad * 2)) / Math.max(1, n - 1);
      const sy = (vv) => h - pad - ((h - pad * 2) * vv) / maxVal;

      // Separate bar series and line series
      const barSeries = series.filter(s => s.type === 'bar');
      const lineSeries = series.filter(s => s.type === 'line');

      // Draw bar series first (background)
      const barW = Math.max(4, (w - pad * 2) / n - 6);
      const barOffset = barSeries.length > 1 ? barW / 2 : 0;

      barSeries.forEach((s, si) => {
        const v = s.values || [];
        const color = s.color || "#a3a3a3";
        const gradId = "barGrad" + Math.random().toString(36).slice(2, 8);
        createGradient(svg, gradId, [
          { offset: 0, color: color + "cc" },
          { offset: 100, color: color + "66" }
        ]);

        for (let i = 0; i < v.length; i++) {
          const vv = num(v[i]);
          const barH = Math.max(2, ((h - pad * 2) * vv) / maxVal);
          const x = pad + i * ((w - pad * 2) / n) + (si * barW / barSeries.length) - barOffset / 2;
          const y = h - pad - barH;

          const rect = svgEl("rect", {
            x, y, width: barW / barSeries.length - 1, height: barH,
            rx: 2, ry: 2,
            fill: `url(#${gradId})`,
            opacity: 0.7
          });
          const title = svgEl("title");
          title.textContent = `${labels[i]} · ${s.name}: ${vv}`;
          rect.appendChild(title);
          svg.appendChild(rect);
        }
      });

      // Draw line series (foreground)
      lineSeries.forEach(s => {
        const v = s.values || [];
        if (v.length < 2) return;

        const color = s.color || "#0066ff";
        const areaGradId = "area" + Math.random().toString(36).slice(2, 8);
        createGradient(svg, areaGradId, [
          { offset: 0, color: color + "30" },
          { offset: 100, color: color + "00" }
        ]);

        // Area
        const areaPath = [`M ${sx(0)},${h}`];
        for (let i = 0; i < v.length; i++) {
          areaPath.push(`L ${sx(i)},${sy(num(v[i]))}`);
        }
        areaPath.push(`L ${sx(v.length - 1)},${h} Z`);
        svg.appendChild(svgEl("path", {
          d: areaPath.join(" "),
          fill: `url(#${areaGradId})`
        }));

        // Line
        const linePoints = v.map((vv, i) => `${sx(i)},${sy(num(vv))}`).join(" ");
        svg.appendChild(svgEl("polyline", {
          points: linePoints,
          fill: "none",
          stroke: color,
          "stroke-width": 2.5,
          "stroke-linecap": "round",
          "stroke-linejoin": "round"
        }));

        // End dot
        const lastIdx = v.length - 1;
        svg.appendChild(svgEl("circle", {
          cx: sx(lastIdx),
          cy: sy(num(v[lastIdx])),
          r: 4,
          fill: color,
          stroke: "#fff",
          "stroke-width": 2
        }));
      });

      // Tooltip
      const title = svgEl("title");
      title.textContent = labels.map((lb, i) => {
        const parts = [lb];
        for (const s of series) {
          parts.push(`  ${s.name}: ${num(s.values[i])}`);
        }
        return parts.join("\n");
      }).join("\n\n");
      svg.appendChild(title);

      return svg;
    }

    (function initHead() {
      const t = displayDashboardTitle((DATA.dashboard && DATA.dashboard.title) ? String(DATA.dashboard.title) : "项目总揽");
      document.getElementById("title").textContent = t;
      document.getElementById("sub").textContent = "生成时间：" + String(DATA.generated_at || "");
      loadHealthInfo().then(renderEnvironmentBadge).catch(() => {});
    })();

    (function initControls() {
      try {
        const q = localStorage.getItem("overview.q");
        if (q) STATE.q = String(q || "");
        const st = localStorage.getItem("overview.showStats");
        if (st === "0") STATE.showStats = false;
        const sort = localStorage.getItem("overview.sort");
        if (sort === "name" || sort === "risk") STATE.sort = sort;
        const projectFilter = localStorage.getItem("overview.projectFilter");
        if (projectFilter) STATE.projectFilters = normalizeProjectFilterIds(projectFilter);
      } catch (_) {}
      const validIds = new Set((Array.isArray(OVER.projects) ? OVER.projects : []).map((p) => String((p && p.project_id) || "")));
      STATE.projectFilters = normalizeProjectFilterIds(STATE.projectFilters, validIds);
      if (!STATE.projectFilters.length) {
        STATE.projectFilters = normalizeProjectFilterIds(allProjectIds(), validIds);
      }
      PROJECT_FILTER_UI.draftIds = normalizeProjectFilterIds(STATE.projectFilters, validIds);

      const qEl = document.getElementById("q");
      if (qEl) {
        qEl.value = STATE.q;
        let timer = 0;
        qEl.addEventListener("input", (e) => {
          STATE.q = String(e.target.value || "");
          try { localStorage.setItem("overview.q", STATE.q); } catch (_) {}
          if (timer) clearTimeout(timer);
          timer = setTimeout(() => renderCards(), 150);
        });
        qEl.addEventListener("keydown", (e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            STATE.q = "";
            qEl.value = "";
            try { localStorage.setItem("overview.q", ""); } catch (_) {}
            renderCards();
          }
        });
      }
      const filterWrap = document.getElementById("projectFilterWrap");
      const filterBtn = document.getElementById("projectFilterBtn");
      const filterPop = document.getElementById("projectFilterPop");
      const filterList = document.getElementById("projectFilterList");
      const filterAllBtn = document.getElementById("projectFilterAllBtn");
      const filterClearBtn = document.getElementById("projectFilterClearBtn");
      const filterApplyBtn = document.getElementById("projectFilterApplyBtn");
      renderProjectFilterOptions();
      if (filterBtn) {
        const active = isProjectFilterNarrowing();
        filterBtn.classList.toggle("active", active);
        filterBtn.title = active ? ("项目筛选：" + projectFilterLabel()) : "项目筛选";
        filterBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          setProjectFilterPopover(filterPop ? filterPop.hidden : false);
        });
      }
      if (filterList) {
        filterList.addEventListener("click", (e) => {
          e.stopPropagation();
        });
      }
      if (filterAllBtn) {
        filterAllBtn.addEventListener("click", (e) => {
          e.preventDefault();
          PROJECT_FILTER_UI.draftIds = normalizeProjectFilterIds(allProjectIds());
          renderProjectFilterOptions();
        });
      }
      if (filterClearBtn) {
        filterClearBtn.addEventListener("click", (e) => {
          e.preventDefault();
          PROJECT_FILTER_UI.draftIds = [];
          renderProjectFilterOptions();
        });
      }
      if (filterApplyBtn) {
        filterApplyBtn.addEventListener("click", (e) => {
          e.preventDefault();
          applyProjectFilterFromValues(PROJECT_FILTER_UI.draftIds);
          setProjectFilterPopover(false);
        });
      }
      document.addEventListener("click", (e) => {
        if (!filterWrap || !filterPop || filterPop.hidden) return;
        if (filterWrap.contains(e.target)) return;
        setProjectFilterPopover(false);
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") setProjectFilterPopover(false);
      });

      const sortBtn = document.getElementById("sortBtn");
      if (sortBtn) sortBtn.addEventListener("click", () => {
        STATE.sort = (STATE.sort === "risk") ? "name" : "risk";
        try { localStorage.setItem("overview.sort", STATE.sort); } catch (_) {}
        applyStateToDom();
        renderCards();
      });
      const statsBtn = document.getElementById("statsBtn");
      if (statsBtn) statsBtn.addEventListener("click", () => {
        STATE.showStats = !STATE.showStats;
        try { localStorage.setItem("overview.showStats", STATE.showStats ? "1" : "0"); } catch (_) {}
        applyStateToDom();
      });

      document.addEventListener("keydown", (e) => {
        const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.platform || "");
        const mod = isMac ? e.metaKey : e.ctrlKey;
        if (mod && (e.key === "k" || e.key === "K")) {
          const q = document.getElementById("q");
          if (q) { e.preventDefault(); q.focus(); }
        }
      });

      applyStateToDom();
    })();

    (function initConfigControls() {
      const statusReportBtn = document.getElementById("statusReportBtn");
      const communicationBtn = document.getElementById("communicationBtn");
      const cfgBtn = document.getElementById("configBtn");
      const closeBtn = document.getElementById("cfgCloseBtn");
      const mask = document.getElementById("cfgMask");
      const saveGlobalBtn = document.getElementById("cfgSaveGlobalBtn");
      const openAvatarBtn = document.getElementById("cfgOpenAvatarLibraryBtn");
      const copyAvatarBtn = document.getElementById("cfgCopyAvatarLibraryBtn");

      const openDrawer = async () => {
        setCfgOpened(true);
        renderAvatarLibraryEntry();
        await loadPlatformConfig();
      };
      const closeDrawer = () => setCfgOpened(false);

      if (statusReportBtn) statusReportBtn.addEventListener("click", openStatusReportPage);
      if (communicationBtn) communicationBtn.addEventListener("click", openCommunicationPage);
      if (cfgBtn) cfgBtn.addEventListener("click", openDrawer);
      if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
      if (mask) mask.addEventListener("click", closeDrawer);
      if (saveGlobalBtn) saveGlobalBtn.addEventListener("click", saveGlobalConfig);
      if (openAvatarBtn) openAvatarBtn.addEventListener("click", () => {
        const links = getAvatarLibraryLinks();
        window.open(links.primary, "_blank", "noopener,noreferrer");
      });
      if (copyAvatarBtn) copyAvatarBtn.addEventListener("click", copyAvatarLibraryLink);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && CFG.opened) {
          e.preventDefault();
          closeDrawer();
        }
      });

    })();

    (function renderStats() {
      const s = document.getElementById("stats");
      s.innerHTML = "";
      const t = OVER.totals || {};

      const DONE_STATUSES = new Set(["已完成", "已验收通过", "已消费", "已解决", "已关闭", "已停止"]);
      const PAUSE_STATUSES = new Set(["已暂停", "暂缓"]);
      const items = Array.isArray(DATA.items) ? DATA.items : [];

      const days = lastNDaysKeys(14);
      const mapAll = new Map(days.map((k) => [k, 0]));
      const mapActive = new Map(days.map((k) => [k, 0]));
      const projActive = new Map(days.map((k) => [k, new Set()]));

      for (const it of items) {
        const d = parseDateTime(it && it.updated_at);
        if (!d) continue;
        const key = dateKeyLocal(d);
        if (!mapAll.has(key)) continue;
        mapAll.set(key, mapAll.get(key) + 1);
        const st = String((it && it.status) || "");
        const isActive = !DONE_STATUSES.has(st) && !PAUSE_STATUSES.has(st);
        if (isActive) {
          mapActive.set(key, mapActive.get(key) + 1);
          projActive.get(key).add(String(it && (it.project_id || it.projectId || "") || ""));
        }
      }

      const allSeries = days.map((k) => mapAll.get(k) || 0);
      const activeSeries = days.map((k) => mapActive.get(k) || 0);
      const projActiveSeries = days.map((k) => (projActive.get(k) ? projActive.get(k).size : 0));

      const todayActive = activeSeries.length ? activeSeries[activeSeries.length - 1] : 0;
      const sum7Active = activeSeries.slice(-7).reduce((a, b) => a + b, 0);
      const todayAll = allSeries.length ? allSeries[allSeries.length - 1] : 0;

      const done = num(t.done);
      const total = num(t.total);
      const requirementsTotal = num(t.requirements_total || 0);
      const rate = total > 0 ? Math.round((done / total) * 100) + "%" : "0%";

      // 4 Stat Cards
      function statCard(label, val, sub, highlight) {
        const c = el("div", { class: "stat-card" + (highlight ? " highlight" : "") });
        c.appendChild(el("div", { class: "stat-label", text: label }));
        c.appendChild(el("div", { class: "stat-value", text: val }));
        if (sub) c.appendChild(el("div", { class: "stat-sub", text: sub }));
        return c;
      }

      s.appendChild(statCard("项目", fmt(t.projects), null, true));
      s.appendChild(statCard("总任务", fmt(t.total), null, false));
      s.appendChild(statCard("活跃", fmt(t.active), fmtPct(t.active, t.total), false));
      s.appendChild(statCard("需求", fmt(requirementsTotal), null, false));
      s.appendChild(statCard("完成率", rate, `${done}/${total}`, false));

      // Combined Trend Card (5th column, spans remaining space)
      const trendCard = el("div", { class: "trend-card" });
      const trendHead = el("div", { class: "trend-header" });
      trendHead.appendChild(el("div", { class: "trend-title", text: "14天趋势" }));
      trendHead.appendChild(el("div", { class: "trend-meta", text: `今日活跃 ${todayActive} · 7日 ${sum7Active}` }));
      trendCard.appendChild(trendHead);

      const labels = days.map(x => x.slice(5));
      const chart = combinedChartSvg([
        { name: "全量", values: allSeries, color: "#d1d5db", type: "bar" },
        { name: "项目", values: projActiveSeries, color: "#86efac", type: "bar" },
        { name: "活跃", values: activeSeries, color: "#0066ff", type: "line" },
      ], labels, "14天趋势");
      trendCard.appendChild(chart);

      // Legend
      const legend = el("div", { class: "trend-legend" });
      legend.appendChild(el("div", { class: "legend-item", html: '<span class="legend-dot" style="background:#0066ff"></span>活跃' }));
      legend.appendChild(el("div", { class: "legend-item", html: '<span class="legend-dot" style="background:#10b981"></span>项目' }));
      legend.appendChild(el("div", { class: "legend-item", html: '<span class="legend-dot" style="background:#a3a3a3"></span>全量' }));
      trendCard.appendChild(legend);

      s.appendChild(trendCard);
    })();

    function renderCards() {
      const list = document.getElementById("cards");
      const all = OVER.projects || [];
      list.innerHTML = "";

      if (!all.length) {
        list.appendChild(el("div", { class: "empty-state", text: "暂无可展示项目，请检查配置。" }));
        setMeta("");
        return;
      }

      let projects = all.filter(p => matchesQuery(p, STATE.q));
      const filterIds = normalizeProjectFilterIds(STATE.projectFilters);
      if (filterIds.length) {
        const filterSet = new Set(filterIds);
        projects = projects.filter((p) => filterSet.has(String((p && p.project_id) || "")));
      }
      if (STATE.sort === "name") {
        projects = projects.slice().sort((a, b) =>
          displayProjectName(a).localeCompare(displayProjectName(b), "zh-Hans-CN")
        );
      } else {
        projects = projects.slice().sort((a, b) => riskScore(b) - riskScore(a));
      }
      const filterLabel = projectFilterLabel();
      const filterSeg = isProjectFilterNarrowing() && filterLabel ? (" · 已筛选：" + filterLabel) : "";
      setMeta(`${projects.length} / ${all.length} 项目${filterSeg} · ⌘K 搜索`);

      if (!projects.length) {
        list.appendChild(el("div", { class: "empty-state", text: "没有匹配项目。" }));
        return;
      }

      for (const p of projects) {
        const card = el("article", { class: "card" });

        // Header
        const head = el("div", { class: "card-header" });
        const tg = el("div", { class: "card-title-group" });
        const projectName = displayProjectName(p) || p.project_id;
        const projectDesc = displayProjectDescription(p);
        tg.appendChild(el("a", { class: "card-title", text: projectName, href: toTaskUrl(p.project_id, "") }));
        if (projectDesc) tg.appendChild(el("div", { class: "card-desc", text: projectDesc }));
        tg.appendChild(buildProjectSourceBadge(p));
        head.appendChild(tg);

        const actions = el("div", { class: "card-actions" });
        actions.appendChild(el("button", { class: "btn btn-primary", text: "作战室", onclick: `enterProject('${p.project_id}')` }));
        actions.appendChild(el("a", { class: "btn btn-ghost", text: "看板 →", href: toTaskUrl(p.project_id, "") }));
        head.appendChild(actions);
        card.appendChild(head);

        // Body
        const body = el("div", { class: "card-body" });

        const tt = (p && p.totals) ? p.totals : {};
        const sup = num(tt.supervised);
        const ip = num(tt.in_progress);
        const act = num(tt.active);
        const done = num(tt.done);
        const total = num(tt.total);
        const reqTotal = num(tt.requirements_total || 0);

        // Tags
        const tags = el("div", { class: "tags" });
        if (sup > 0) tags.appendChild(el("span", { class: "tag danger", text: `督办 ${sup}` }));
        if (ip > 0) tags.appendChild(el("span", { class: "tag warning", text: `进行中 ${ip}` }));
        if (reqTotal > 0) tags.appendChild(el("span", { class: "tag", text: `需求 ${reqTotal}` }));
        if (act > 0) tags.appendChild(el("span", { class: "tag primary", text: `活跃 ${act}` }));
        if (total === 0) tags.appendChild(el("span", { class: "tag", text: "无任务" }));
        body.appendChild(tags);

        // Metrics
        const metrics = el("div", { class: "metrics-row" });
        const mItem = (k, v) => {
          const d = el("div", { class: "metric" });
          d.appendChild(el("div", { class: "metric-val", text: v }));
          d.appendChild(el("div", { class: "metric-key", text: k }));
          return d;
        };
        metrics.appendChild(mItem("总计", fmt(total)));
        metrics.appendChild(mItem("活跃", fmt(act)));
        metrics.appendChild(mItem("需求", fmt(reqTotal)));
        metrics.appendChild(mItem("完成", fmt(done)));
        body.appendChild(metrics);

        // Progress
        const pctVal = (total > 0) ? Math.round((done / total) * 100) : 0;
        const prog = el("div", { class: "progress-section" });
        const progHead = el("div", { class: "progress-header" });
        progHead.appendChild(el("span", { text: "进度" }));
        progHead.appendChild(el("span", { text: `${pctVal}%` }));
        prog.appendChild(progHead);

        const bar = el("div", { class: "progress-bar" });
        bar.appendChild(el("div", { class: "progress-fill" + (pctVal >= 100 ? " full" : ""), style: `width:${pctVal}%` }));
        prog.appendChild(bar);
        body.appendChild(prog);

        card.appendChild(body);
        list.appendChild(card);
      }
    }

    renderCards();

    // ========== Global Resource Graph (V1) ==========
    const GRAPH = {
      active: false,
      activeProjectId: null,
      data: null,
      ctx: null,
      width: 0,
      height: 0,
      camera: { x: 0, y: 0, zoom: 1 },
      isDragging: false,
      lastMouse: { x: 0, y: 0 },
      nodes: [],
      nodeMap: new Map(),
      edges: [],
      projectMap: new Map(),
      filters: {
        project: true,
        channel: true,
        agent: true,
        run: true,
        task: true,
        feedback: true,
        risk: false,
        active_agents: false,
        support_low: false,
        assist_in_progress: false,
        assist_waiting_reply: false,
        assist_closed: false,
      },
      selectedNode: null,
      projectAgents: [],
      sceneWalls: [],
      runTaskMap: new Map(),
      taskSupportMap: new Map(),
      taskStatusOptions: [],
      taskStatusEnabled: new Set(),
      rafId: 0,
      // Layout config
      gridSize: 400,
      viewMode: 'warroom', // 'warroom' only (R1 Org Mode removed)
      leftWallMode: 'roster', // 'roster' | 'org'
      // V2-P3-R7: Wall Interaction State
      leftWallView: { x: 0, y: 0, scale: 1 },
      isDraggingWall: false,
      wallHover: false,
      wallContentNodes: [],
      wallContentEdges: [],
      wallHitNodes: [],
      wallHitBubbles: [],
      wallHoverBubble: null,
      runtimeBubblePayload: null,
      runtimeBubbleIndex: new Map(),
      runtimePollTimer: 0,
      runtimePollMs: 4000,
      runtimePollInFlight: false,
      runtimeLastRefreshAt: 0,
      runtimePollTickCount: 0,
      wallFixedSize: { w: 980, h: 720 }, // R9: widen wall container
      wallHeaderHeight: 48
    };

    // Color Palette for Graph
    const G_COLORS = {
      project: "#4fd1c5",
      channel: "#63b3ed",
      agent: "#f6ad55",
      run: "#fc8181",
      task: "#cbd5e0",
      feedback: "#b794f4",
      edge: "rgba(113, 128, 150, 0.3)",
      edgeHighlight: "#fff",
      bg: "#0f1115"
    };

    const STATUS_COLORS = {
      in_progress: "#3b82f6", // Blue
      blocked: "#ef4444",     // Red
      pending_acceptance: "#eab308", // Yellow
      done: "#22c55e",        // Green
      other: "#64748b"        // Gray
    };

    const TASK_STATUS_META = {
      in_progress: { key: "in_progress", label: "进行中", order: 1 },
      pending_acceptance: { key: "pending_acceptance", label: "待验收", order: 2 },
      blocked: { key: "blocked", label: "阻塞", order: 3 },
      done: { key: "done", label: "已完成", order: 4 },
      other: { key: "other", label: "其他", order: 99 },
    };

    const BATCH_STATE_META = {
      in_progress: { key: "in_progress", label: "进行中", color: "#3b82f6" },
      pending: { key: "pending", label: "待处理", color: "#94a3b8" },
      done: { key: "done", label: "已完成", color: "#22c55e" },
      blocked: { key: "blocked", label: "阻塞", color: "#ef4444" },
    };

    const PANEL_FACING_VEC = { x: 0, y: 0, z: 1 };
    const PANEL_STYLE = {
      // Unified Facing Vector (V2-P2-R6)
      leftWallRightVec: PANEL_FACING_VEC,
      rightWallRightVec: { x: 0.52, y: 0, z: 1 }, 
      taskBoardRightVec: PANEL_FACING_VEC,
      upVec: { x: 0, y: 1, z: 0 },
      // Unified shear to eliminate individual twisting (V2-P2-R6)
      textShear: {
        wallAgent: 0,
        wallTask: -0.6,
        task: 0
      }
    };
    const WALL_HEADER_STYLE = {
      // Keep header height proportional to wall panel size (not tied to camera zoom directly).
      headerHRatio: 0.15,
      headerMinH: 64,
      headerMaxH: 160,
      titleFontRatio: 0.44,
      titleMin: 26,
      titleMax: 72,
      toggleFontRatio: 0.30,
      toggleMin: 16,
      toggleMax: 38,
      toggleHeightRatio: 0.52,
      toggleWidthRatio: 0.24,
      headerPadRatio: 0.14,
      titleWeight: 700,
      buttonWeight: 600,
      fontFamily: '"SF Pro Display","PingFang SC","Microsoft YaHei",sans-serif'
    };
    const WALL_ROSTER_LAYOUT = {
      topReserveY: 184,
      bottomReserveY: 64
    };

    function getAgentName(n) {
        return n.display_name || n.channel_display_name || n.channel_name || n.label || n.id;
    }

    function getAgentChannelName(n) {
        return n.channel_display_name || n.channel_name || getAgentName(n);
    }

    function getTaskDisplayTitle(n) {
        const raw = String((n && (n.title || n.label || n.path)) || "Task").trim();
        if (!raw) return "Task";
        return raw
            .replace(/^([【\[].*?[】\]])+\s*/g, "")
            .replace(/\.md$/i, "")
            .trim() || raw;
    }

    function escapeHTML(text) {
        return String(text || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function exitProject() {
      GRAPH.active = false;
      GRAPH.activeProjectId = null;
      stopRuntimeBubblesPolling();
      GRAPH.projectAgents = [];
      GRAPH.taskStatusOptions = [];
      GRAPH.taskStatusEnabled = new Set();
      document.getElementById("listView").hidden = false;
      document.getElementById("graphView").hidden = true;
      const roster = document.getElementById("graphRosterBoard");
      if (roster) roster.hidden = true;
      
      // Restore header and controls
      document.body.classList.remove("warroom-mode");
      
      // Hide drawers
      document.getElementById("graphSidebar").classList.remove("visible");
      document.getElementById("graphDetails").classList.remove("visible");
      
      stopGraphLoop();
    }

    function resetProjectFiltersForWarroom() {
      const resetKeys = {
        project: true,
        channel: true,
        agent: true,
        run: true,
        task: true,
        feedback: true,
        risk: false,
        active_agents: false,
        support_low: false,
        assist_in_progress: false,
        assist_waiting_reply: false,
        assist_closed: false,
      };
      Object.assign(GRAPH.filters, resetKeys);
      const allStatusKeys = (GRAPH.taskStatusOptions || []).map((x) => x.key);
      GRAPH.taskStatusEnabled = new Set(allStatusKeys);
      syncTaskStatusFiltersUI();
      document.querySelectorAll(".graph-filter input[data-filter]").forEach((cb) => {
        const key = cb.dataset.filter;
        if (Object.prototype.hasOwnProperty.call(resetKeys, key)) {
          cb.checked = resetKeys[key];
        }
      });
    }

    window.enterProject = function(projectId) {
      GRAPH.activeProjectId = projectId;
      GRAPH.active = true;
      GRAPH.leftWallView = { x: 0, y: 0, scale: 1 };
      GRAPH.runtimePollTickCount = 0;
      document.getElementById("listView").hidden = true;
      document.getElementById("graphView").hidden = false;
      resetProjectFiltersForWarroom();
      
      // Full screen mode: hide header and controls via body class
      document.body.classList.add("warroom-mode");
      
      resizeGraph();
      loadGraphData(projectId);
      startRuntimeBubblesPolling(projectId);
      startGraphLoop();
    };

    // V2-P3-R7: Wall Interaction Helpers
    function mapScreenToWall(mx, my, wallNode) {
        if (!wallNode || !wallNode._screenQuad) return null;
        const q = wallNode._screenQuad;
        // Inverse Bilinear Interpolation for Quad
        // p0 -- p1
        // |     |
        // p3 -- p2 (Clockwise or standard order?)
        // buildPanelWorldCorners returns: TL, TR, BR, BL.
        // So: 0:TL, 1:TR, 2:BR, 3:BL.
        
        // Check if inside triangle 0-1-3 or 1-2-3?
        // Or simple planar projection assumption since it's an affine transform in Iso (parallelogram).
        // For parallelogram, we can use simple basis vectors.
        const p0 = q[0];
        const p1 = q[1];
        const p3 = q[3];
        
        const uVec = { x: p1.x - p0.x, y: p1.y - p0.y };
        const vVec = { x: p3.x - p0.x, y: p3.y - p0.y };
        const pVec = { x: mx - p0.x, y: my - p0.y };
        
        const det = uVec.x * vVec.y - uVec.y * vVec.x;
        if (Math.abs(det) < 0.0001) return null;
        
        // Wait, pVec = u * uVec + v * vVec
        // x = u * ux + v * vx
        // y = u * uy + v * vy
        // Solve for u, v.
        // v = (x*uy - y*ux) / (vx*uy - vy*ux)
        // Let's re-derive carefully.
        // x = u*ux + v*vx
        // y = u*uy + v*vy
        // x*vy = u*ux*vy + v*vx*vy
        // y*vx = u*uy*vx + v*vy*vx
        // x*vy - y*vx = u * (ux*vy - uy*vx)
        // u = (x*vy - y*vx) / (ux*vy - uy*vx)
        // Let D = ux*vy - uy*vx
        // u = (pVec.x * vVec.y - pVec.y * vVec.x) / D
        // Similarly for v:
        // x*uy = u*ux*uy + v*vx*uy
        // y*ux = u*uy*ux + v*vy*ux
        // x*uy - y*ux = v * (vx*uy - vy*ux) = v * (-D)
        // v = (y*ux - x*uy) / D
        
        const D = uVec.x * vVec.y - uVec.y * vVec.x;
        const uVal = (pVec.x * vVec.y - pVec.y * vVec.x) / D;
        const vVal = (pVec.y * uVec.x - pVec.x * uVec.y) / D;
        
        if (uVal >= 0 && uVal <= 1 && vVal >= 0 && vVal <= 1) {
            const mirrored = D < 0;
            const localU = mirrored ? (1 - uVal) : uVal;
            return {
                u: localU,
                v: vVal,
                x: localU * wallNode._width,
                y: vVal * wallNode._height
            };
        }
        return null;
    }

    function initGraphView() {
      const graph = document.getElementById("graphView");
      const canvas = document.getElementById("graphCanvas");
      
      if (!graph || !canvas) return;

      GRAPH.ctx = canvas.getContext("2d");

      // Floating Buttons
      const menuBtn = document.getElementById("graphMenuBtn");
      const backBtn = document.getElementById("graphBackBtn");
      
      if (menuBtn) {
          menuBtn.addEventListener("click", (e) => {
              e.stopPropagation();
              document.getElementById("graphSidebar").classList.toggle("visible");
          });
      }
      
      if (backBtn) {
          backBtn.addEventListener("click", (e) => {
              e.stopPropagation();
              exitProject();
          });
      }

      // Canvas Interaction
      GRAPH.mousePos = { x: 0, y: 0 }; 

      canvas.addEventListener("mousedown", e => {
        // V2-P3-R7: Wall Interaction (Start Drag)
        const wallBg = GRAPH.nodes.find(n => n.type === 'wall_bg');
        if (wallBg && wallBg._screenQuad) {
            const hit = mapScreenToWall(e.offsetX, e.offsetY, wallBg);
            if (hit && hit.y > GRAPH.wallHeaderHeight) {
                // Hit Body
                GRAPH.isDraggingWall = true;
                GRAPH.wallDragStart = { mx: e.offsetX, my: e.offsetY };
                GRAPH.wallViewStart = { ...GRAPH.leftWallView };
                // Map start mouse to wall local
                GRAPH.wallDragStartLocal = hit;
                return;
            }
        }

        GRAPH.isDragging = true;
        GRAPH.lastMouse = { x: e.offsetX, y: e.offsetY };
      });
      
      window.addEventListener("mouseup", () => {
          GRAPH.isDragging = false;
          GRAPH.isDraggingWall = false;
      });
      
      canvas.addEventListener("mousemove", e => {
        GRAPH.mousePos = { x: e.offsetX, y: e.offsetY };
        GRAPH.wallHoverBubble = null;
        
        // V2-P3-R7: Wall Interaction (Drag)
        if (GRAPH.isDraggingWall) {
            const wallBg = GRAPH.nodes.find(n => n.type === 'wall_bg');
            if (wallBg) {
                // We need to calculate how much the mouse moved in "Wall Local Space".
                // Current Mouse -> Current Wall Local
                // We assume the wall plane doesn't move relative to screen during drag (camera static).
                const hit = mapScreenToWall(e.offsetX, e.offsetY, wallBg);
                if (hit) {
                    const dx = hit.x - GRAPH.wallDragStartLocal.x;
                    const dy = hit.y - GRAPH.wallDragStartLocal.y;
                    
                    GRAPH.leftWallView.x = GRAPH.wallViewStart.x + dx;
                    GRAPH.leftWallView.y = GRAPH.wallViewStart.y + dy;
                    return;
                }
            }
        }

        const wallBg = GRAPH.nodes.find(n => n.type === 'wall_bg');
        if (wallBg && wallBg._screenQuad) {
            const hit = mapScreenToWall(e.offsetX, e.offsetY, wallBg);
            if (hit && hit.y > GRAPH.wallHeaderHeight) {
                const cx = (hit.x - GRAPH.leftWallView.x) / GRAPH.leftWallView.scale;
                const cy = (hit.y - GRAPH.leftWallView.y) / GRAPH.leftWallView.scale;
                const bubble = hitWallBubble(cx, cy);
                if (bubble) {
                    GRAPH.wallHoverBubble = {
                        ...bubble,
                        screenX: e.offsetX,
                        screenY: e.offsetY
                    };
                }
            }
        }

        if (GRAPH.isDragging) {
          const dx = e.offsetX - GRAPH.lastMouse.x;
          const dy = e.offsetY - GRAPH.lastMouse.y;
          GRAPH.camera.x += dx;
          GRAPH.camera.y += dy;
          GRAPH.lastMouse = { x: e.offsetX, y: e.offsetY };
        }
      });
      
      canvas.addEventListener("wheel", e => {
        // 收口口径：主画布仅保留按钮缩放，滚轮不再触发缩放，避免误触。
        e.preventDefault();
      }, { passive: false });

      canvas.addEventListener("mouseleave", () => {
        GRAPH.wallHoverBubble = null;
      });
      
      canvas.addEventListener("click", e => handleGraphClick(e.offsetX, e.offsetY));
      
      // ESC to close drawers/deselect
      window.addEventListener("keydown", (e) => {
          if (!GRAPH.active) return;
          if (e.key === "Escape") {
              const details = document.getElementById("graphDetails");
              const sidebar = document.getElementById("graphSidebar");
              let handled = false;
              
              if (details && details.classList.contains("visible")) {
                  details.classList.remove("visible");
                  handled = true;
              }
              if (sidebar && sidebar.classList.contains("visible")) {
                  sidebar.classList.remove("visible");
                  handled = true;
              }
              
              if (!handled && GRAPH.selectedNode) {
                  GRAPH.selectedNode = null;
                  renderGraph();
                  updateDetailsPanel(null);
              }
          }
      });

      // Resize
      window.addEventListener("resize", () => {
        if (GRAPH.active) resizeGraph();
      });

      // Controls
      const getAnchor = () => {
        if (GRAPH.mousePos && (GRAPH.mousePos.x > 0 || GRAPH.mousePos.y > 0)) {
          return GRAPH.mousePos;
        }
        return { x: GRAPH.width / 2, y: GRAPH.height / 2 };
      };
      document.getElementById("zoomInBtn")?.addEventListener("click", () => {
        const a = getAnchor();
        zoomAtAnchor(1.2, a.x, a.y);
      });
      document.getElementById("zoomOutBtn")?.addEventListener("click", () => {
        const a = getAnchor();
        zoomAtAnchor(1/1.2, a.x, a.y);
      });
      document.getElementById("resetCamBtn")?.addEventListener("click", () => {
        fitCameraToNodes();
      });
      const zoomWallAt = (scaleFactor) => {
        const wallBg = GRAPH.nodes.find((n) => n.type === "wall_bg");
        if (!wallBg) return;
        const oldScale = GRAPH.leftWallView.scale || 1;
        let newScale = oldScale * scaleFactor;
        newScale = Math.max(0.85, Math.min(1.6, newScale));
        if (Math.abs(newScale - oldScale) < 0.0001) return;
        const anchorX = wallBg._width * 0.5;
        const anchorY = wallBg._height * 0.5;
        GRAPH.leftWallView.x = anchorX - (anchorX - GRAPH.leftWallView.x) * (newScale / oldScale);
        GRAPH.leftWallView.y = anchorY - (anchorY - GRAPH.leftWallView.y) * (newScale / oldScale);
        GRAPH.leftWallView.scale = newScale;
      };
      document.getElementById("wallZoomInBtn")?.addEventListener("click", () => zoomWallAt(1.15));
      document.getElementById("wallZoomOutBtn")?.addEventListener("click", () => zoomWallAt(1 / 1.15));
      document.getElementById("wallZoomResetBtn")?.addEventListener("click", () => {
        GRAPH.leftWallView = { x: 0, y: 0, scale: 1 };
      });

      // V2-P2-R10: Zoom at Mouse Anchor
      function zoomAtAnchor(scaleFactor, ax, ay) {
        if (!GRAPH.active || !GRAPH.ctx) return;
        
        const oldZoom = GRAPH.camera.zoom;
        let newZoom = oldZoom * scaleFactor;
        
        // Clamp
        newZoom = Math.max(0.1, Math.min(5, newZoom));
        
        // Avoid drift if no change
        if (Math.abs(newZoom - oldZoom) < 0.0001) return;

        // World coordinate of anchor point
        const worldX = (ax - GRAPH.camera.x) / oldZoom;
        const worldY = (ay - GRAPH.camera.y) / oldZoom;
        
        // Update zoom
        GRAPH.camera.zoom = newZoom;
        
        // Re-center camera to keep worldX,worldY at ax,ay
        GRAPH.camera.x = ax - worldX * newZoom;
        GRAPH.camera.y = ay - worldY * newZoom;
      }

      // Filters
      document.querySelectorAll(".graph-filter input").forEach(cb => {
        cb.addEventListener("change", e => {
          const key = String(e.target.dataset.filter || "");
          if (!key) return;
          GRAPH.filters[key] = e.target.checked;
          renderGraph();
        });
      });
    }

    function resizeGraph() {
      const container = document.querySelector(".graph-stage");
      if (!container || !GRAPH.ctx) return;
      GRAPH.width = container.clientWidth;
      GRAPH.height = container.clientHeight;
      GRAPH.ctx.canvas.width = GRAPH.width;
      GRAPH.ctx.canvas.height = GRAPH.height;
      if (GRAPH.camera.x === 0 && GRAPH.camera.y === 0) {
        GRAPH.camera.x = GRAPH.width / 2;
        GRAPH.camera.y = GRAPH.height / 2;
      }
    }

    async function loadGraphData(projectId) {
      try {
        const url = projectId 
            ? `/api/board/global-resource-graph?project_id=${projectId}&run_limit=600` 
            : "/api/board/global-resource-graph";
        const [res, runtimePayload] = await Promise.all([
          fetchJson(url),
          projectId ? loadRuntimeBubbles(projectId) : Promise.resolve(null),
        ]);
        GRAPH.data = res;
        GRAPH.runtimeBubblePayload = runtimePayload;
        GRAPH.runtimeBubbleIndex = buildRuntimeBubbleIndex(runtimePayload);
        GRAPH.runtimeLastRefreshAt = Date.now();
        processGraphData(res);
        renderGraphStats(res);
        // If Timeline is active, update it
        if (TIMELINE.active) renderTimeline();
      } catch (e) {
        console.error("Failed to load graph", e);
        const fallback = buildFallbackGraphData();
        GRAPH.data = fallback;
        GRAPH.runtimeBubblePayload = null;
        GRAPH.runtimeBubbleIndex = new Map();
        GRAPH.runtimeLastRefreshAt = 0;
        processGraphData(fallback);
        renderGraphStats(fallback);
      }
    }

    async function loadRuntimeBubbles(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      const url = `/api/projects/${encodeURIComponent(pid)}/runtime-bubbles?limit=200&bubbleLimit=120&objectLimit=2`;
      try {
        return await fetchJson(url);
      } catch (e) {
        // 兼容老版本服务：runtime-bubbles 端点可能尚未发布
        console.warn("runtime-bubbles not available, fallback to local bubbles", e);
        return null;
      }
    }

    async function refreshRuntimeBubblesNow(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return false;
      if (!GRAPH.active || GRAPH.activeProjectId !== pid) return false;
      if (GRAPH.runtimePollInFlight) return false;
      GRAPH.runtimePollInFlight = true;
      try {
        const payload = await loadRuntimeBubbles(pid);
        if (!GRAPH.active || GRAPH.activeProjectId !== pid) return false;
        if (payload && typeof payload === "object") {
          GRAPH.runtimeBubblePayload = payload;
          GRAPH.runtimeBubbleIndex = buildRuntimeBubbleIndex(payload);
          GRAPH.runtimeLastRefreshAt = Date.now();
          GRAPH.runtimePollTickCount += 1;
          if (TIMELINE.active) renderTimeline();
          renderGraph();
          return true;
        }
        return false;
      } catch (e) {
        console.warn("runtime-bubbles refresh failed", e);
        return false;
      } finally {
        GRAPH.runtimePollInFlight = false;
      }
    }

    function stopRuntimeBubblesPolling() {
      if (GRAPH.runtimePollTimer) {
        clearInterval(GRAPH.runtimePollTimer);
        GRAPH.runtimePollTimer = 0;
      }
      GRAPH.runtimePollInFlight = false;
    }

    function startRuntimeBubblesPolling(projectId) {
      const pid = String(projectId || "").trim();
      stopRuntimeBubblesPolling();
      if (!pid) return;
      GRAPH.runtimePollTimer = setInterval(() => {
        refreshRuntimeBubblesNow(pid);
      }, Math.max(1000, Number(GRAPH.runtimePollMs || 4000)));
    }

    function parseIsoTs(value) {
      const ts = Date.parse(String(value || "").trim());
      return Number.isFinite(ts) ? ts : 0;
    }

    function addSecondsToIso(baseText, sec) {
      const baseTs = parseIsoTs(baseText);
      if (!baseTs || !Number.isFinite(sec) || sec <= 0) return "";
      return new Date(baseTs + sec * 1000).toISOString();
    }

    function toneToLevel(tone, status) {
      const t = String(tone || "").toLowerCase();
      if (t === "danger" || t === "error") return "error";
      if (t === "warn" || t === "warning") return "warning";
      if (t === "success") return "success";
      const s = String(status || "").toLowerCase();
      if (["error", "failed", "timeout", "interrupted"].includes(s)) return "error";
      if (["queued", "retry_waiting"].includes(s)) return "warning";
      if (["running", "done", "completed"].includes(s)) return "success";
      return "neutral";
    }

    function parseRuntimeBubbleKey(raw) {
      const txt = String(raw || "");
      if (!txt) return { channel_name: "", session_id: "", status: "" };
      const parts = txt.split("|");
      return {
        channel_name: String(parts[0] || ""),
        session_id: String(parts[1] || ""),
        status: String(parts[2] || ""),
      };
    }

    function normalizeRuntimeBubble(item, defaults = {}) {
      const bubbleTypeRaw = String(item.bubble_type || item.event_type || defaults.bubble_type || "").toLowerCase();
      let bubbleType = bubbleTypeRaw;
      if (bubbleType === "run_status") bubbleType = "status";
      if (bubbleType.includes("mention")) bubbleType = "peer_mention";
      if (bubbleType !== "status" && bubbleType !== "elapsed" && bubbleType !== "peer_mention") {
        bubbleType = "status";
      }
      const status = String(item.status || defaults.status || "").toLowerCase();
      const terminal = ["done", "completed", "error", "failed", "timeout", "interrupted", "cancelled"].includes(status);
      const active = Boolean(item.active ?? defaults.active ?? false);
      const ttlDefault = bubbleType === "peer_mention" ? 90 : 60;
      const ttlSeconds = Math.max(1, Number(item.ttl_seconds || item.ttlSeconds || defaults.ttl_seconds || ttlDefault));
      const startedAt = String(item.started_at || item.startedAt || item.created_at || item.updated_at || defaults.started_at || "").trim();
      const finishedAt = String(item.finished_at || item.finishedAt || defaults.finished_at || "").trim();
      const updatedAt = String(item.updated_at || item.updatedAt || defaults.updated_at || "").trim();
      const fallbackExpire = terminal
        ? addSecondsToIso(finishedAt || updatedAt || startedAt, bubbleType === "peer_mention" ? 90 : 60)
        : "";
      const expiresAt = String(
        item.expires_at
        || item.expiresAt
        || item.expire_at
        || item.expireAt
        || defaults.expires_at
        || fallbackExpire
      ).trim();
      const elapsedMs = Number(item.elapsed_ms || item.elapsedMs || 0);
      let text = String(item.text || defaults.text || "").trim();
      if (!text) {
        if (bubbleType === "elapsed") {
          text = `已持续 ${formatDurationLabel(elapsedMs / 1000)}`;
        } else if (bubbleType === "peer_mention") {
          text = "协作提醒";
        } else {
          text = String(item.status_label || defaults.status_label || status || "状态").trim();
        }
      }
      return {
        bubble_type: bubbleType,
        text,
        level: String(item.level || defaults.level || toneToLevel(item.tone || defaults.tone, status)),
        started_at: startedAt,
        updated_at: updatedAt,
        finished_at: finishedAt,
        expires_at: expiresAt,
        ttl_seconds: ttlSeconds,
        source_run_id: String(item.source_run_id || defaults.source_run_id || ""),
        status,
        active,
        terminal,
        related_objects: Array.isArray(item.related_objects) ? item.related_objects : (Array.isArray(defaults.related_objects) ? defaults.related_objects : []),
        related_object_count: Number(item.related_object_count || defaults.related_object_count || 0),
        related_object_extra_count: Number(item.related_object_extra_count || defaults.related_object_extra_count || 0),
      };
    }

    function buildRuntimeBubbleIndex(payload) {
      const idx = new Map();
      if (!payload || typeof payload !== "object") return idx;
      const push = (sessionId, channelName, bubble) => {
        const sid = String(sessionId || "");
        const ch = String(channelName || "");
        if (!sid && !ch) return;
        const key = `${sid}|${ch}`;
        const list = idx.get(key) || [];
        list.push(bubble);
        idx.set(key, list);
      };

      const bubbles = Array.isArray(payload.runtime_bubbles) ? payload.runtime_bubbles : [];
      bubbles.forEach((b) => {
        const fromKey = parseRuntimeBubbleKey(b.bubble_key);
        const sid = String(b.session_id || fromKey.session_id || payload.session_id || "");
        const ch = String(b.channel_name || fromKey.channel_name || payload.channel_name || "");
        const status = String(b.status || fromKey.status || "").toLowerCase();
        const relatedObjects = Array.isArray(b.related_objects) ? b.related_objects : [];
        const common = {
          status,
          status_label: b.status_label,
          tone: b.tone,
          active: Boolean(b.active),
          terminal: Boolean(b.terminal),
          started_at: b.started_at || b.created_at || "",
          updated_at: b.updated_at || "",
          finished_at: b.finished_at || "",
          source_run_id: b.source_run_id || "",
          expires_at: b.expires_at || b.expire_at || "",
          related_objects: relatedObjects,
          related_object_count: Number(b.related_object_count || relatedObjects.length || 0),
          related_object_extra_count: Number(b.related_object_extra_count || 0),
          elapsed_ms: Number(b.elapsed_ms || 0),
        };
        push(sid, ch, normalizeRuntimeBubble({ ...common, bubble_type: "status", text: b.status_label || status || "状态", ttl_seconds: 60 }, common));
        push(sid, ch, normalizeRuntimeBubble({ ...common, bubble_type: "elapsed", text: `已持续 ${formatDurationLabel((Number(b.elapsed_ms || 0)) / 1000)}`, ttl_seconds: 60 }, common));
      });

      const events = Array.isArray(payload.runtime_events) ? payload.runtime_events : [];
      events.forEach((ev) => {
        const eventType = String(ev.event_type || ev.bubble_type || "").toLowerCase();
        if (!eventType.includes("mention")) return;
        const sid = String(ev.session_id || payload.session_id || "");
        const ch = String(ev.channel_name || payload.channel_name || "");
        const common = {
          status: String(ev.status || "").toLowerCase(),
          tone: ev.tone,
          active: Boolean(ev.active),
          terminal: Boolean(ev.terminal),
          started_at: ev.created_at || ev.updated_at || "",
          updated_at: ev.updated_at || "",
          finished_at: ev.finished_at || "",
          source_run_id: ev.source_run_id || "",
          expires_at: ev.expires_at || ev.expire_at || "",
          related_objects: Array.isArray(ev.related_objects) ? ev.related_objects : [],
          related_object_count: Number(ev.related_object_count || 0),
          related_object_extra_count: Number(ev.related_object_extra_count || 0),
          elapsed_ms: Number(ev.elapsed_ms || 0),
        };
        push(sid, ch, normalizeRuntimeBubble({
          ...common,
          bubble_type: "peer_mention",
          text: ev.text || ev.message || "协作提醒",
          ttl_seconds: 90
        }, common));
      });

      idx.forEach((list, key) => {
        list.sort((a, b) => parseIsoTs(b.updated_at || b.started_at) - parseIsoTs(a.updated_at || a.started_at));
        const dedup = new Map();
        list.forEach((b) => {
          const typeKey = String(b.bubble_type || "status");
          if (!dedup.has(typeKey)) dedup.set(typeKey, b);
        });
        idx.set(key, Array.from(dedup.values()));
      });

      return idx;
    }

    function isAgentActive(n) {
      if (!n || n.type !== 'agent') return false;
      // P0: current_run_status priority
      const rs = String(n.current_run_status || "").toLowerCase();
      if (["running", "queued", "retry_waiting"].includes(rs)) return true;
      // Fallback
      const s = String(n.status || "").toLowerCase();
      return ["active", "running"].includes(s);
    }

    function buildFallbackGraphData() {
      const nodes = [];
      const edges = [];
      const projectMap = new Map();
      const channelMap = new Map();
      const items = Array.isArray(DATA.items) ? DATA.items : [];
      const projects = Array.isArray(OVER.projects) ? OVER.projects : [];

      projects.forEach(p => {
        const pid = String(p.project_id || "");
        if (!pid) return;
        const nid = `project:${pid}`;
        projectMap.set(pid, nid);
        nodes.push({
          id: nid,
          type: "project",
          label: displayProjectName(p) || pid,
          project_id: pid,
        });
      });

      items.forEach(it => {
        const pid = String(it.project_id || "").trim();
        const ch = String(it.channel_name || "").trim();
        if (!pid || !ch) return;

        const pidNode = projectMap.get(pid) || `project:${pid}`;
        if (!projectMap.has(pid)) {
          projectMap.set(pid, pidNode);
          nodes.push({ id: pidNode, type: "project", label: pid, project_id: pid });
        }

        const cKey = `${pid}::${ch}`;
        let cNode = channelMap.get(cKey);
        if (!cNode) {
          cNode = `channel:${pid}:${ch}`;
          channelMap.set(cKey, cNode);
          nodes.push({
            id: cNode,
            type: "channel",
            label: ch,
            project_id: pid,
            channel_name: ch,
            risk_score: 0,
          });
          edges.push({ source: pidNode, target: cNode, type: "project_channel" });
        }

        const title = String(it.title || it.filename || "").trim();
        const taskKey = String(it.path || it.relpath || it.filename || title || `${pid}:${ch}:${nodes.length}`).trim();
        const tNode = `task:${pid}:${ch}:${taskKey}`;
        nodes.push({
          id: tNode,
          type: "task",
          label: title || "未命名任务",
          project_id: pid,
          channel_name: ch,
          status: String(it.status || ""),
        });
        edges.push({ source: cNode, target: tNode, type: "channel_item" });
      });

      return {
        version: "v1-fallback",
        generated_at: new Date().toISOString(),
        filters: { project_id: "", channel_name: "", run_limit: 0 },
        stats: {
          projects: nodes.filter(n => n.type === "project").length,
          channels: nodes.filter(n => n.type === "channel").length,
          tasks: nodes.filter(n => n.type === "task").length,
          feedback: 0,
          agents_total: 0,
          agents_active: 0,
          runs_total: 0,
          runs_running: 0,
          feedback_pending_acceptance: 0,
          links_high_risk: 0,
          edges_total: edges.length,
        },
        schema: {
          node_types: ["project", "channel", "task"],
          edge_types: ["project_channel", "channel_item"],
        },
        nodes,
        edges,
        links: [],
        queues: {
          missing_session: [],
          missing_feedback: [],
          high_risk: [],
          naming_issues: [],
        },
        index: {},
      };
    }

    function processGraphData(data) {
      GRAPH.nodes = [];
      GRAPH.edges = [];
      GRAPH.projectMap.clear();
      GRAPH.runTaskMap = new Map();
      GRAPH.taskSupportMap = new Map();

      // Filter for active project if set
      const pid = GRAPH.activeProjectId;
      if (!pid) {
          processGlobalLayout(data);
          renderAgentList([]); // Clear list
          return;
      }

      // Always Warroom View (V2-P3-R2)
      processProjectLayout(data, pid);
    }

    // ========== V2-P3-R1 Org Chart Logic ==========

    function parseChannelOrgMeta(channelName) {
        const name = String(channelName || "").trim();
        // Heuristic: "支撑" or "Support" or "辅助" -> support
        if (name.includes("支撑") || name.includes("Support") || name.includes("辅助")) {
            return { l1: 'support', order: 100 };
        }
        // Default -> exec
        return { l1: 'exec', order: 1 };
    }

    function pickChannelLeader(agents) {
        if (!agents || !agents.length) return null;
        // Sort by ID to be deterministic. 
        // Ideally we'd use a role field, but for now ID is stable.
        // Assuming leader has lower ID or specific pattern?
        // Let's just take the first one after sorting by ID.
        const sorted = agents.slice().sort((a,b) => String(a.id).localeCompare(String(b.id)));
        return sorted[0];
    }

    function processOrgLayout(data, pid) {
        GRAPH.sceneWalls = [];
        const agents = data.nodes.filter(n => n.type === 'agent' && (n.project_id === pid || !n.project_id));
        
        // 1. Build Hierarchy
        // L0: Master Node
        const l0Node = {
            id: 'org:master',
            type: 'org_node',
            subtype: 'L0',
            label: '总控',
            _pos: { x: 0, y: 0, z: -GRAPH.gridSize }, // Top center
            _size: 40
        };
        GRAPH.nodes.push(l0Node);

        // Group by Channel
        const channelGroups = new Map();
        agents.forEach(a => {
            const cName = getAgentChannelName(a) || "Unknown";
            if (!channelGroups.has(cName)) channelGroups.set(cName, []);
            channelGroups.get(cName).push(a);
        });

        // Split L1: Exec vs Support
        const execChannels = [];
        const supportChannels = [];

        channelGroups.forEach((group, cName) => {
            const meta = parseChannelOrgMeta(cName);
            const entry = { name: cName, agents: group, meta };
            if (meta.l1 === 'support') supportChannels.push(entry);
            else execChannels.push(entry);
        });

        // Sort Channels
        const sortChans = (list) => list.sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
        sortChans(execChannels);
        sortChans(supportChannels);

        // Layout Parameters
        const layerH = GRAPH.gridSize * 0.8; // Vertical gap (Z axis)
        const colW = GRAPH.gridSize * 0.6;   // Horizontal gap (X axis)
        
        // Helper to place trees
        // Start L1 at Z = 0
        // Exec on Left (X < 0), Support on Right (X > 0)
        
        const placeBranch = (channels, signX) => {
            let currentX = signX * colW * 0.5; // Start near center
            // If multiple channels, spread them out. 
            // If signX is -1 (Left), we flow Leftwards: -0.5, -1.5, -2.5...
            // If signX is 1 (Right), we flow Rightwards: 0.5, 1.5, 2.5...
            
            channels.forEach((ch, i) => {
                const x = currentX + (signX * i * colW);
                const z = 0; // L1/L2 level
                
                const leader = pickChannelLeader(ch.agents);
                if (!leader) return; // Should not happen
                
                // L2 Node (Leader)
                const l2Node = {
                    id: `org:l2:${leader.id}`,
                    type: 'org_node',
                    subtype: 'L2',
                    label: getAgentName(leader),
                    agent_ref: leader,
                    channel_name: ch.name,
                    _pos: { x, y: 0, z },
                    _size: 30
                };
                GRAPH.nodes.push(l2Node);
                
                // Edge L0 -> L2 (Report Line)
                GRAPH.edges.push({
                    source: l0Node.id,
                    target: l2Node.id,
                    type: 'report_line'
                });

                // L3 Members
                const members = ch.agents.filter(a => a.id !== leader.id);
                // Sort members: Active first
                members.sort((a, b) => {
                    const av = isAgentActive(a) ? 1 : 0;
                    const bv = isAgentActive(b) ? 1 : 0;
                    return bv - av;
                });

                members.forEach((m, mi) => {
                    // Place L3 under L2
                    // Vertical list? Or small grid?
                    // "成员挂在负责人下方"
                    const mz = z + layerH * 0.6 + (mi * layerH * 0.4);
                    // Slight X offset for visual hierarchy? Or straight down?
                    // Straight down is cleaner.
                    
                    const l3Node = {
                        id: `org:l3:${m.id}`,
                        type: 'org_node',
                        subtype: 'L3',
                        label: getAgentName(m),
                        agent_ref: m,
                        _pos: { x, y: 0, z: mz },
                        _size: 20
                    };
                    GRAPH.nodes.push(l3Node);

                    // Edge L2 -> L3
                    GRAPH.edges.push({
                        source: l2Node.id,
                        target: l3Node.id,
                        type: 'report_line'
                    });
                });
            });
        };

        placeBranch(execChannels, -1);
        placeBranch(supportChannels, 1);

        // Index nodes
        GRAPH.nodeMap = new Map();
        GRAPH.nodes.forEach(n => GRAPH.nodeMap.set(n.id, n));
        
        fitCameraToNodes();
    }

    function processGlobalLayout(data) {
      GRAPH.sceneWalls = [];
      GRAPH.runTaskMap = new Map();
      GRAPH.taskSupportMap = new Map();
      GRAPH.taskStatusOptions = [];
      GRAPH.taskStatusEnabled = new Set();
      syncTaskStatusFiltersUI();
      // 1. Group by Project
      const projects = data.nodes.filter(n => n.type === 'project');
      const channels = data.nodes.filter(n => n.type === 'channel');
      const others = data.nodes.filter(n => !['project', 'channel'].includes(n.type));

      // Layout Projects in a Grid
      const cols = Math.ceil(Math.sqrt(projects.length));
      const rows = Math.ceil(projects.length / Math.max(1, cols));
      const colCenter = (cols - 1) / 2;
      const rowCenter = (rows - 1) / 2;
      projects.forEach((p, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;
        const x = (col - colCenter) * GRAPH.gridSize * 1.5;
        const z = (row - rowCenter) * GRAPH.gridSize * 1.5;
        p._pos = { x, y: 0, z };
        GRAPH.nodes.push(p);
        GRAPH.projectMap.set(p.id, p);
      });

      // Layout Channels around Projects
      const channelsByProj = {};
      channels.forEach(c => {
        const pid = c.project_id;
        if (!channelsByProj[pid]) channelsByProj[pid] = [];
        channelsByProj[pid].push(c);
      });

      Object.entries(channelsByProj).forEach(([pid, chans]) => {
        const pNode = projects.find(p => p.project_id === pid || p.id === pid || p.id === `project:${pid}`);
        const center = pNode ? pNode._pos : { x: 0, y: 0, z: 0 };
        const radius = GRAPH.gridSize * 0.4;
        
        chans.forEach((c, i) => {
          const angle = (i / chans.length) * Math.PI * 2;
          c._pos = {
            x: center.x + Math.cos(angle) * radius,
            y: 20, // Raised
            z: center.z + Math.sin(angle) * radius
          };
          GRAPH.nodes.push(c);
        });
      });

      // Layout Others
      others.forEach(n => {
         let parentPos = { x: 0, y: 0, z: 0 };
         const parentEdge = data.edges.find(e => e.target === n.id && e.type.startsWith('channel'));
         if (parentEdge) {
           const p = GRAPH.nodes.find(x => x.id === parentEdge.source);
           if (p) parentPos = p._pos;
         }
         n._pos = {
           x: parentPos.x + (Math.random() - 0.5) * 100,
           y: parentPos.y + 30 + Math.random() * 20,
           z: parentPos.z + (Math.random() - 0.5) * 100
         };
         GRAPH.nodes.push(n);
      });

      GRAPH.edges = data.edges;
      GRAPH.nodeMap = new Map();
      GRAPH.nodes.forEach(n => GRAPH.nodeMap.set(n.id, n));
      fitCameraToNodes();
    }

    function processProjectLayout(data, pid) {
        GRAPH.sceneWalls = [];
        GRAPH.runTaskMap = new Map();
        GRAPH.taskSupportMap = new Map();
        const allProjectTasks = data.nodes.filter(n => n.type === 'task' && (n.project_id === pid || !n.project_id));
        const isTaskCandidateNode = (task) => {
            const path = String(task.path || "").replace(/\\/g, "/");
            const label = String(task.label || task.title || "");
            if (!path) return false;
            if (!path.includes("/任务规划/")) return false;
            if (!path.includes("/任务/")) return false;
            if (!label.includes("【任务】")) return false;
            if (path.includes("/已完成/") || path.includes("/待验收/") || path.includes("/反馈/")) return false;
            return true;
        };
        const isExplicitMasterTaskPath = (task) => {
            const path = String(task.path || "").replace(/\\/g, "/");
            return path.includes("/任务规划/00-主体-总任务批次/任务/");
        };
        const taskCandidates = allProjectTasks.filter(isTaskCandidateNode);
        const explicitMasters = taskCandidates.filter(isExplicitMasterTaskPath);
        const genericZeroLevel = taskCandidates.filter((task) => {
            const path = String(task.path || "").replace(/\\/g, "/");
            return path.includes("/任务规划/00-") && path.includes("/任务/");
        });
        const tasks = explicitMasters.length
            ? explicitMasters
            : (genericZeroLevel.length ? genericZeroLevel : taskCandidates);
        const usingMasterSubset = tasks.length < taskCandidates.length;
        const agents = data.nodes.filter(n => n.type === 'agent' && (n.project_id === pid || !n.project_id));
        const runs = data.nodes.filter(n => n.type === 'run' && (n.project_id === pid || !n.project_id));
        const runById = new Map();
        runs.forEach(r => {
            runById.set(r.id, r);
            if (r.run_id) runById.set(`run:${r.run_id}`, r);
        });

        // --- Hierarchy Pre-processing ---
        // 规则：
        // 1) 优先使用显式父子字段（parent_task_id/parentTaskId/is_subtask/isSubtask/parent_task_path）。
        // 2) 若无显式字段，默认全部按主任务渲染，避免路径推断误伤主任务。
        const normalizeTaskLookup = (value) => String(value || "")
            .replace(/^task:/i, "")
            .replace(/\\/g, "/")
            .replace(/\.md$/i, "")
            .trim();
        const taskLookup = new Map();
        const putTaskLookup = (key, task) => {
            const norm = normalizeTaskLookup(key);
            if (!norm) return;
            taskLookup.set(norm, task);
            taskLookup.set(`task:${norm}`, task);
        };
        tasks.forEach((t) => {
            putTaskLookup(t.id, t);
            putTaskLookup(t.path, t);
        });

        const explicitHierarchy = tasks.some((t) => {
            const parentId = String(t.parent_task_id || t.parentTaskId || "").trim();
            const parentPath = String(t.parent_task_path || t.parentTaskPath || "").trim();
            return Boolean(parentId || parentPath || t.is_subtask === true || t.isSubtask === true);
        });

        const mainTasks = [];
        const subTasks = [];
        const pendingSubs = [];

        const taskTitleBase = (task) => {
            let t = String((task && (task.title || task.label)) || "").trim();
            if (!t) return "";
            t = t.replace(/^(?:【[^】]+】\s*)+/g, "").trim();
            t = t.replace(/\.md$/i, "").trim();
            return t;
        };
        const inferTaskGroupMeta = (task) => {
            const base = taskTitleBase(task);
            const tokens = base.split("-").map((x) => String(x || "").trim()).filter(Boolean);
            if (!tokens.length) return { key: String(task.path || task.id || ""), child: false, childOrder: 0 };
            const first = tokens[0];
            const second = tokens[1] || "";
            if (/^A\d{2,}$/i.test(first)) {
                return { key: first.toUpperCase(), child: /^\d+$/.test(second), childOrder: /^\d+$/.test(second) ? Number(second) : 0 };
            }
            if (/^\d{1,4}$/.test(first)) {
                return { key: first, child: /^\d+$/.test(second), childOrder: /^\d+$/.test(second) ? Number(second) : 0 };
            }
            if (/^\d{8}$/.test(first) && /^\d+$/.test(second) && tokens.length >= 3) {
                return { key: `${first}-${second}`, child: true, childOrder: Number(second) };
            }
            return { key: base || String(task.path || task.id || ""), child: false, childOrder: 0 };
        };
        const toTimeNum = (value) => {
            const ts = Date.parse(String(value || ""));
            return Number.isFinite(ts) ? ts : 0;
        };

        tasks.forEach((t) => {
            t._subtasks = [];
            t._isSubtask = false;
            t._parent = null;
            if (!explicitHierarchy) return;
            const parentId = String(t.parent_task_id || t.parentTaskId || "").trim();
            const parentPath = String(t.parent_task_path || t.parentTaskPath || "").trim();
            const declaredSub = t.is_subtask === true || t.isSubtask === true || Boolean(parentId || parentPath);
            if (!declaredSub) {
                mainTasks.push(t);
                return;
            }
            pendingSubs.push({ task: t, parentId, parentPath });
        });

        if (explicitHierarchy) {
            pendingSubs.forEach(({ task, parentId, parentPath }) => {
                let parent = null;
                if (parentId) {
                    parent = taskLookup.get(normalizeTaskLookup(parentId)) || null;
                }
                if (!parent && parentPath) {
                    parent = taskLookup.get(normalizeTaskLookup(parentPath)) || null;
                }
                if (parent && parent.id !== task.id) {
                    parent._subtasks.push(task);
                    task._isSubtask = true;
                    task._parent = parent;
                    subTasks.push(task);
                } else {
                    // 显式字段异常时回退为主任务，避免节点丢失。
                    mainTasks.push(task);
                }
            });
        } else {
            // 对齐任务看板总任务聚合口径：group_key -> master_task + subtasks
            const groups = new Map();
            tasks.forEach((task) => {
                const meta = inferTaskGroupMeta(task);
                const key = String(meta.key || task.path || task.id || "").trim();
                if (!groups.has(key)) groups.set(key, []);
                groups.get(key).push({ task, meta });
            });
            groups.forEach((members) => {
                if (!Array.isArray(members) || !members.length) return;
                members.sort((a, b) => toTimeNum(b.task && b.task.updated_at) - toTimeNum(a.task && a.task.updated_at));
                const rootCandidates = members.filter((x) => !x.meta.child);
                const masterEntry = rootCandidates[0] || members[0];
                if (!masterEntry || !masterEntry.task) return;
                const master = masterEntry.task;
                mainTasks.push(master);
                members.forEach((entry) => {
                    const child = entry.task;
                    if (!child || child.id === master.id) return;
                    child._isSubtask = true;
                    child._parent = master;
                    master._subtasks.push(child);
                    subTasks.push(child);
                });
            });
        }

        // 若命中“00-主体-总任务批次”目录，则把其余任务尽量归并为子任务（用于详情与数量气泡）
        if (usingMasterSubset) {
            const supplemental = taskCandidates.filter((t) => !tasks.some((m) => m.id === t.id));
            const masterByKey = new Map();
            mainTasks.forEach((m) => {
                const k = String(inferTaskGroupMeta(m).key || "").trim();
                if (k) masterByKey.set(k, m);
            });
            const unmatched = [];
            supplemental.forEach((st) => {
                const mk = String(inferTaskGroupMeta(st).key || "").trim();
                const parent = masterByKey.get(mk);
                if (!parent || parent.id === st.id) {
                    unmatched.push(st);
                    return;
                }
                st._isSubtask = true;
                st._parent = parent;
                parent._subtasks.push(st);
                subTasks.push(st);
            });
            unmatched.forEach((st) => {
                let parent = null;
                if (mainTasks.length === 1) {
                    parent = mainTasks[0];
                } else {
                    const ch = String(st.channel_name || "").trim();
                    if (ch) {
                        const sameChannel = mainTasks.filter((m) => String(m.channel_name || "").trim() === ch);
                        if (sameChannel.length === 1) parent = sameChannel[0];
                    }
                }
                if (!parent && mainTasks.length) parent = mainTasks[0];
                if (!parent || parent.id === st.id) return;
                st._isSubtask = true;
                st._parent = parent;
                parent._subtasks.push(st);
                subTasks.push(st);
            });
        }

        // Use mainTasks for layout instead of all tasks
        const layoutTasks = mainTasks;

        // --- Center Plot (Existing) ---
        const cols = Math.ceil(Math.sqrt(layoutTasks.length || 1));
        const rows = Math.ceil((layoutTasks.length || 1) / cols);
        const gap = GRAPH.gridSize * 0.8;
        const centerCol = (cols - 1) / 2;
        const centerRow = (rows - 1) / 2;

        const taskById = new Map();
        const taskByPath = new Map();
        const runToTask = new Map();
        const channelToTasks = new Map();
        const agentToChannels = new Map();
        const normalizePath = (value) => String(value || "")
            .replace(/^task:/i, "")
            .replace(/\\/g, "/")
            .trim();
        const registerTaskPath = (path, task) => {
            const norm = normalizePath(path);
            if (!norm) return;
            taskByPath.set(norm, task);
            taskByPath.set(`task:${norm}`, task);
            taskByPath.set(norm.replace(/^.*?\/任务规划\//, "任务规划/"), task);
        };
        
        // Layout Main Tasks
        layoutTasks.forEach((t, i) => {
            const col = i % cols;
            const row = Math.floor(i / cols);
            t._pos = {
                x: (col - centerCol) * gap,
                y: 0,
                z: (row - centerRow) * gap
            };
            t._size = gap * 0.6;
            GRAPH.nodes.push(t);
            taskById.set(t.id, t);
            registerTaskPath(t.path, t);
            registerTaskPath(t.id, t);
        });
        
        // Also register subtasks in maps for lookups, but DO NOT push to GRAPH.nodes (so they don't render on board)
        subTasks.forEach(t => {
            taskById.set(t.id, t);
            registerTaskPath(t.path, t);
            registerTaskPath(t.id, t);
        });

        GRAPH.taskStatusOptions = buildTaskStatusOptions(layoutTasks);
        const allStatusKeys = GRAPH.taskStatusOptions.map((x) => x.key);
        if (!GRAPH.taskStatusEnabled.size) {
            GRAPH.taskStatusEnabled = new Set(allStatusKeys);
        } else {
            GRAPH.taskStatusEnabled = new Set(
                Array.from(GRAPH.taskStatusEnabled).filter((key) => allStatusKeys.includes(key))
            );
            if (!GRAPH.taskStatusEnabled.size) {
                GRAPH.taskStatusEnabled = new Set(allStatusKeys);
            }
        }
        syncTaskStatusFiltersUI();
        
        // ... (Keep existing link logic for Center Agents, but we don't render them in Center anymore? 
        // Wait, "Left Project Wall + Central Task Plot + Right Task Wall".
        // The prompt says "Remove Top-Right Floating Agent List" -> "Left Project Wall".
        // It doesn't explicitly say "Remove Center Agents". 
        // But "Scene-based Entity Display" might imply moving them.
        // However, center agents show *relationships* (who is working on what).
        // Left Wall shows *roster* (availability).
        // I'll keep center agents for now as they are part of the "Plot".
        
        data.edges.forEach(e => {
            if (e.type !== "task_run") return;
            const task = taskById.get(e.source);
            if (!task) return;
            runToTask.set(e.target, task);
            const run = runById.get(e.target);
            if (run && run.run_id) runToTask.set(`run:${run.run_id}`, task);
        });
        data.edges.forEach(e => {
            if (e.type === "channel_item") {
                const task = taskById.get(e.target);
                if (!task) return;
                const list = channelToTasks.get(e.source) || [];
                list.push(task);
                channelToTasks.set(e.source, list);
            }
            if (e.type === "channel_agent") {
                const list = agentToChannels.get(e.target) || [];
                list.push(e.source);
                agentToChannels.set(e.target, list);
            }
        });

        const agentsByTask = new Map();
        layoutTasks.forEach(t => agentsByTask.set(t.id, []));
        const standbyAgents = [];
        const agentTaskSetMap = new Map();

        const runStatusWeight = (status) => {
            const s = String(status || "").toLowerCase();
            if (s === "running") return 5;
            if (s === "queued") return 4;
            if (s === "retry_waiting") return 3;
            if (s === "done") return 2;
            if (s === "error") return 1;
            return 0;
        };
        const runScore = (run) => {
            const ts = Date.parse(run.current_run_at || run.started_at || run.created_at || run.finished_at || 0);
            const safeTs = Number.isFinite(ts) ? ts : 0;
            return runStatusWeight(run.status) * 10000000000000 + safeTs;
        };
        const findTaskByPath = (pathValue) => {
            if (!pathValue) return null;
            return taskByPath.get(normalizePath(pathValue)) || null;
        };

        data.edges.forEach((e) => {
            if (e.type !== "agent_run") return;
            const run = runById.get(e.target);
            if (!run) return;
            let relatedTask = runToTask.get(run.id) || runToTask.get(`run:${run.run_id || ""}`) || findTaskByPath(run.task_path);
            if (relatedTask && relatedTask._isSubtask && relatedTask._parent) {
                relatedTask = relatedTask._parent;
            }
            if (!relatedTask) return;
            const set = agentTaskSetMap.get(e.source) || new Set();
            set.add(relatedTask.id);
            agentTaskSetMap.set(e.source, set);
        });

        agents.forEach(a => {
            let foundTask = null;

            foundTask = findTaskByPath(a.current_task_path);
            if (!foundTask && a.current_run_id) {
                foundTask = runToTask.get(`run:${a.current_run_id}`) || runToTask.get(a.current_run_id) || null;
            }

            if (!foundTask) {
                const runEdges = data.edges.filter(e => e.type === 'agent_run' && e.source === a.id);
                let bestTask = null;
                let bestScore = -1;
                for (const re of runEdges) {
                    const run = runById.get(re.target);
                    if (!run) continue;
                    const task = runToTask.get(run.id) || findTaskByPath(run.task_path);
                    if (!task) continue;
                    const score = runScore(run);
                    if (score > bestScore) {
                        bestScore = score;
                        bestTask = task;
                    }
                }
                foundTask = bestTask;
            }
            if (!foundTask) {
                const channels = agentToChannels.get(a.id) || [];
                let candidateTasks = [];
                channels.forEach(ch => {
                    const linkedTasks = channelToTasks.get(ch) || [];
                    candidateTasks = candidateTasks.concat(linkedTasks);
                });
                if (candidateTasks.length) {
                    const unique = Array.from(new Set(candidateTasks.map(t => t.id)))
                        .map(id => taskById.get(id))
                        .filter(Boolean);
                    unique.sort((ta, tb) => {
                        const aCount = (agentsByTask.get(ta.id) || []).length;
                        const bCount = (agentsByTask.get(tb.id) || []).length;
                        if (aCount !== bCount) return aCount - bCount;
                        return String(getTaskDisplayTitle(ta)).localeCompare(String(getTaskDisplayTitle(tb)), "zh-Hans-CN");
                    });
                    foundTask = unique[0] || null;
                }
            }

            if (foundTask) {
                // V2-P2-R16-4: Redirect agents from subtask to main task for visualization
                if (foundTask._isSubtask && foundTask._parent) {
                    foundTask = foundTask._parent;
                }
                
                a._taskRef = foundTask.id;
                if (agentsByTask.has(foundTask.id)) {
                    agentsByTask.get(foundTask.id).push(a);
                } else {
                    standbyAgents.push(a);
                }
            } else {
                a._taskRef = "";
                standbyAgents.push(a);
            }

            const relatedSet = agentTaskSetMap.get(a.id);
            a._related_task_count = relatedSet ? relatedSet.size : (foundTask ? 1 : 0);
        });

        function placeAgentGroup(group, center, areaScale) {
            if (!group.length) return;
            const ordered = group.slice().sort((a, b) => {
                const av = isAgentActive(a) ? 1 : 0;
                const bv = isAgentActive(b) ? 1 : 0;
                if (av !== bv) return bv - av;
                return String(getAgentName(a)).localeCompare(String(getAgentName(b)), "zh-Hans-CN");
            });
            const minSpacing = Math.max(64, gap * 0.24 * areaScale);
            const baseRadius = ordered.length <= 4
                ? minSpacing * 0.55
                : Math.max(minSpacing * 1.12, gap * 0.28 * areaScale);
            const golden = Math.PI * (3 - Math.sqrt(5));
            ordered.forEach((a, i) => {
                let hash = 0;
                const seedSource = String(a.id || i);
                for (let j = 0; j < seedSource.length; j += 1) {
                    hash = ((hash << 5) - hash + seedSource.charCodeAt(j)) >>> 0;
                }
                const phase = (hash % 1000) / 1000;
                const theta = i * golden + phase * 0.8;
                const radius = baseRadius + Math.sqrt(i + 1) * minSpacing * 0.92;
                const yBase = isAgentActive(a) ? 48 : 18;
                a._pos = {
                    x: center.x + Math.cos(theta) * radius,
                    y: yBase + ((phase - 0.5) * 3.5),
                    z: center.z + Math.sin(theta) * radius * 0.86
                };
                GRAPH.nodes.push(a);
            });
        }

        agentsByTask.forEach((group, taskId) => {
            const t = taskById.get(taskId);
            if (!t) return;
            placeAgentGroup(group, t._pos, 0.72);
        });

        if (standbyAgents.length) {
            const standbyCenter = {
                x: gap * (centerCol + Math.max(2.8, cols * 0.65)),
                z: -gap * (centerRow + Math.max(1.9, rows * 0.35))
            };
            placeAgentGroup(standbyAgents, standbyCenter, 1.2);
        }

        // Task-level support/assist derivation (20-2)
        const taskSupportMap = new Map();
        tasks.forEach((t) => {
            taskSupportMap.set(t.id, { active_runs: 0, active_agents: 0 });
        });

        runs.forEach((r) => {
            const linkedTask = runToTask.get(r.id) || findTaskByPath(r.task_path);
            if (!linkedTask || !taskSupportMap.has(linkedTask.id)) return;
            if (isRunActive(r)) {
                taskSupportMap.get(linkedTask.id).active_runs += 1;
            }
            GRAPH.runTaskMap.set(r.id, linkedTask.id);
            if (r.run_id) GRAPH.runTaskMap.set(String(r.run_id), linkedTask.id);
        });

        agents.forEach((a) => {
            if (!a._taskRef || !taskSupportMap.has(a._taskRef)) return;
            if (isAgentActive(a)) {
                taskSupportMap.get(a._taskRef).active_agents += 1;
            }
        });

        taskSupportMap.forEach((metric, taskId) => {
            GRAPH.taskSupportMap.set(taskId, metric);
            const taskNode = taskById.get(taskId);
            if (taskNode) {
                taskNode._support = deriveTaskSupportAssist(taskNode);
            }
        });

        const participantAgentsByTask = new Map();
        layoutTasks.forEach((task) => {
            const directAgents = Array.isArray(agentsByTask.get(task.id)) ? agentsByTask.get(task.id) : [];
            const uniq = [];
            const seen = new Set();
            directAgents.forEach((agent) => {
                if (!agent || seen.has(agent.id)) return;
                seen.add(agent.id);
                uniq.push(agent);
            });
            participantAgentsByTask.set(task.id, uniq);
            task._participantAgents = uniq;
            task._participantAgentCount = uniq.length;
        });
        subTasks.forEach((task) => {
            const parent = task && task._parent;
            const inherited = parent ? (participantAgentsByTask.get(parent.id) || []) : [];
            task._participantAgents = inherited;
            task._participantAgentCount = inherited.length;
        });

        // --- Left Project Wall (Agents): anchor at top-left scene side ---
        const sceneHalfX = (cols * gap) * 0.5;
        const sceneHalfZ = (rows * gap) * 0.5;
        const sceneMinX = -sceneHalfX;
        const sceneMaxX = sceneHalfX;
        const sceneMinZ = -sceneHalfZ;
        const sceneMaxZ = sceneHalfZ;
        
        // Wall Positioning
        const wallX = sceneMinX - 128;
        const wallBaseY = 14;
        const wallCenterZ = ((sceneMinZ + sceneMaxZ) * 0.5);
        
        // V2-P3-R7: Fixed Wall Size & Container
        const wallW = GRAPH.wallFixedSize.w;
        const wallH = GRAPH.wallFixedSize.h;
        const wallCenter = {
            x: wallX,
            y: wallBaseY + wallH * 0.5,
            z: wallCenterZ
        };
        
        // 1. Generate Content
        let layoutRes = null;
        if (GRAPH.leftWallMode === 'org') {
             layoutRes = layoutOrgTreeOnWall(agents);
        } else {
             layoutRes = layoutAgentRosterOnWall(agents);
        }
        
        // 2. Store Content in Virtual State (Not in GRAPH.nodes)
        GRAPH.wallContentNodes = layoutRes.nodes;
        GRAPH.wallContentEdges = layoutRes.edges;
        
        // 3. Create Wall Node (Fixed Container)
        const leftWallCorners = buildPanelWorldCorners(
            wallCenter,
            wallW,
            wallH,
            PANEL_STYLE.leftWallRightVec,
            PANEL_STYLE.upVec
        );
        
        GRAPH.nodes.push({
            id: 'wall:bg:left',
            type: 'wall_bg',
            label: GRAPH.leftWallMode === 'org' ? 'Agents组织架构' : 'Agents资源榜',
            _pos: wallCenter,
            _corners: leftWallCorners,
            _width: wallW,
            _height: wallH
        });

        GRAPH.sceneWalls.push({
            id: "scene:left_agent_wall",
            type: "left",
            corners: leftWallCorners
        });

        /*
        const wallTaskRows = Math.max(1, Math.ceil(Math.max(1, wallTasks.length) / wallTaskCols));
        const rightWallTopY = wallTaskYTop + wallTaskHeight * 0.65 + 76;
        const rightWallBottomY = wallTaskYTop - (wallTaskRows - 1) * (wallTaskHeight + wallTaskGapY) - wallTaskHeight * 0.65 - 90;
        const rightWallZMin = wallTaskZStart - wallTaskWidth * 0.6;
        const rightWallZMax = wallTaskZStart + (wallTaskCols - 1) * (wallTaskWidth + wallTaskGapX) + wallTaskWidth * 0.6;
        GRAPH.sceneWalls.push({
            id: "scene:right_task_wall",
            type: "right",
            corners: [
                { x: rightWallX, y: rightWallTopY, z: rightWallZMin },
                { x: rightWallX, y: rightWallTopY, z: rightWallZMax },
                { x: rightWallX, y: rightWallBottomY, z: rightWallZMax },
                { x: rightWallX, y: rightWallBottomY, z: rightWallZMin },
            ]
        });
        */

        const nodeIds = new Set(GRAPH.nodes.map(n => n.id));
        GRAPH.edges = data.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

        GRAPH.nodeMap = new Map();
        GRAPH.nodes.forEach(n => GRAPH.nodeMap.set(n.id, n));
        GRAPH.projectAgents = agents.slice();

        // renderAgentList(agents); // Removed as per V2-P2
        renderRosterBoard([]); // Hide/Clear roster
        fitCameraToNodes();
    }

    function getAgentAvatarLabel(name) {
      const s = String(name || "").trim();
      // Extract number if present (e.g. "辅助07" -> "07")
      const m = s.match(/\d+/);
      if (m) return m[0];
      // Fallback to first char
      return s.substring(0, 1).toUpperCase();
    }

    function renderAgentList(agents) {
        const list = document.getElementById("agentList");
        if (!list) return;
        list.innerHTML = "";

        if (agents.length === 0) {
            list.innerHTML = '<div class="agent-empty">暂无 Agent</div>';
            return;
        }

        agents.forEach(a => {
            const isActive = isAgentActive(a);
            const row = document.createElement("div");
            row.className = `agent-item ${isActive ? 'active' : ''}`;
            const name = getAgentName(a);
            // V2-P2-R16-3: Avatar digital code
            const label = getAgentAvatarLabel(name);
            const statusText = a.current_run_status || a.status || 'idle';
            row.innerHTML = `
                <div class="agent-avatar">${label}</div>
                <div class="agent-info">
                    <div class="agent-name">${name}</div>
                    <div class="agent-status">${statusText}</div>
                </div>
            `;
            row.onclick = () => {
                GRAPH.selectedNode = a;
                renderGraph();
                updateDetailsPanel(a);
                document.getElementById("graphDetails").classList.add("visible");
            };
            list.appendChild(row);
        });
    }

    function renderRosterBoard(agents) {
        const board = document.getElementById("graphRosterBoard");
        if (!board) return;
        // V2-P2+: Scene walls replace this legacy floating panel.
        board.hidden = true;
        board.style.display = "none";
        board.setAttribute("aria-hidden", "true");
    }

    function fitCameraToNodes() {
      if (!GRAPH.nodes.length || GRAPH.width <= 0 || GRAPH.height <= 0) return;

      const newBounds = () => ({
        minX: Infinity,
        maxX: -Infinity,
        minY: Infinity,
        maxY: -Infinity
      });
      const hasBounds = (b) => Number.isFinite(b.minX) && Number.isFinite(b.maxX)
        && Number.isFinite(b.minY) && Number.isFinite(b.maxY);
      const cloneBounds = (b) => ({
        minX: b.minX,
        maxX: b.maxX,
        minY: b.minY,
        maxY: b.maxY
      });
      const includeIso = (b, isoX, isoY) => {
        b.minX = Math.min(b.minX, isoX);
        b.maxX = Math.max(b.maxX, isoX);
        b.minY = Math.min(b.minY, isoY);
        b.maxY = Math.max(b.maxY, isoY);
      };
      const includePoint = (b, x, y, z) => {
        const isoX = (x - z) * 0.866;
        const isoY = (x + z) * 0.5 - y;
        includeIso(b, isoX, isoY);
      };
      const includeTaskBounds = (b, n) => {
        const size = Math.max(80, Number(n._size) || GRAPH.gridSize * 0.6);
        const half = size * 0.5;
        const boardH = Math.max(120, size * 0.62);
        const x = n._pos.x;
        const y = n._pos.y;
        const z = n._pos.z;
        includePoint(b, x - half, y, z - half);
        includePoint(b, x - half, y, z + half);
        includePoint(b, x + half, y, z + half);
        includePoint(b, x + half, y, z - half);
        // 任务竖牌的近似包围，避免竖牌被裁剪
        includePoint(b, x - half, y + boardH, z);
        includePoint(b, x - half, y + boardH, z + half * 0.2);
      };

      const boundsAll = newBounds();
      const boundsTask = newBounds();
      const boundsWall = newBounds();

      if (GRAPH.activeProjectId) {
        const tasks = GRAPH.nodes.filter((n) => n.type === "task");
        if (tasks.length) {
          tasks.forEach((n) => {
            includeTaskBounds(boundsAll, n);
            includeTaskBounds(boundsTask, n);
          });
        } else {
          GRAPH.nodes.forEach((n) => {
            if (!n._pos || n.type === "wall_bg" || n.type === "wall_agent") return;
            includePoint(boundsAll, n._pos.x, n._pos.y, n._pos.z);
            includePoint(boundsTask, n._pos.x, n._pos.y, n._pos.z);
          });
        }

        if (Array.isArray(GRAPH.sceneWalls)) {
          GRAPH.sceneWalls.forEach((wall) => {
            if (!wall.corners || wall.corners.length < 4) return;
            wall.corners.forEach((c) => {
              includePoint(boundsAll, c.x, c.y, c.z);
              includePoint(boundsWall, c.x, c.y, c.z);
            });
          });
        }
      } else {
        GRAPH.nodes.forEach((n) => {
          if (!n._pos || n.type === "wall_bg" || n.type === "wall_agent") return;
          includePoint(boundsAll, n._pos.x, n._pos.y, n._pos.z);
        });
      }

      if (!hasBounds(boundsAll)) return;

      const pad = GRAPH.activeProjectId ? 72 : 48;
      let fitBounds = boundsAll;
      if (GRAPH.activeProjectId && hasBounds(boundsTask)) {
        fitBounds = cloneBounds(boundsTask);
        const taskW = Math.max(1, boundsTask.maxX - boundsTask.minX);
        const taskH = Math.max(1, boundsTask.maxY - boundsTask.minY);
        const sidePadX = Math.max(120, taskW * 0.16);
        const sidePadY = Math.max(80, taskH * 0.1);

        // Keep task area as primary focus.
        fitBounds.minX -= sidePadX;
        fitBounds.maxX += sidePadX * 0.45;
        fitBounds.minY -= sidePadY;
        fitBounds.maxY += sidePadY * 0.95;

        // Include only a near-to-task slice of wall, avoid letting full wall dominate zoom.
        if (hasBounds(boundsWall)) {
          const wallW = Math.max(1, boundsWall.maxX - boundsWall.minX);
          const wallH = Math.max(1, boundsWall.maxY - boundsWall.minY);
          const wallRevealMinX = boundsWall.maxX - wallW * 0.72;
          const wallRevealMinY = boundsWall.minY + wallH * 0.16;
          const wallRevealMaxY = boundsWall.maxY - wallH * 0.02;
          fitBounds.minX = Math.min(fitBounds.minX, wallRevealMinX);
          fitBounds.minY = Math.min(fitBounds.minY, wallRevealMinY);
          fitBounds.maxY = Math.max(fitBounds.maxY, wallRevealMaxY);
        }
      }

      const worldW = Math.max(1, fitBounds.maxX - fitBounds.minX);
      const worldH = Math.max(1, fitBounds.maxY - fitBounds.minY);
      const viewW = Math.max(1, GRAPH.width - pad * 2);
      const viewH = Math.max(1, GRAPH.height - pad * 2);
      const fitZoom = Math.min(viewW / worldW, viewH / worldH);
      const zoom = Math.max(0.14, Math.min(2, fitZoom));

      let centerX = (fitBounds.minX + fitBounds.maxX) / 2;
      let centerY = (fitBounds.minY + fitBounds.maxY) / 2;

      // 项目态优先把任务区放在视野中心，同时只给墙体少量权重。
      if (GRAPH.activeProjectId && hasBounds(boundsTask)) {
        const taskCenterX = (boundsTask.minX + boundsTask.maxX) / 2;
        const taskCenterY = (boundsTask.minY + boundsTask.maxY) / 2;
        if (hasBounds(boundsWall)) {
          const wallCenterX = (boundsWall.minX + boundsWall.maxX) / 2;
          const wallCenterY = (boundsWall.minY + boundsWall.maxY) / 2;
          centerX = taskCenterX * 0.9 + wallCenterX * 0.1;
          centerY = taskCenterY * 0.94 + wallCenterY * 0.06;
        } else {
          centerX = taskCenterX;
          centerY = taskCenterY;
        }
      }

      GRAPH.camera.zoom = zoom;
      GRAPH.camera.x = GRAPH.width / 2 - centerX * zoom;
      GRAPH.camera.y = GRAPH.height / 2 - centerY * zoom;
    }

    function renderGraphStats(data) {
      const el = document.getElementById("graphStats");
      if (!el || !data || !data.stats) return;
      const s = data.stats;
      const q = data.queues || {};
      const missingSession = (q.missing_session || []).length;
      const masterTaskCount = GRAPH.activeProjectId
        ? GRAPH.nodes.filter((n) => n.type === "task").length
        : Number(s.tasks || 0);
      const subtasksCount = GRAPH.activeProjectId
        ? GRAPH.nodes
            .filter((n) => n.type === "task")
            .reduce((acc, n) => acc + ((Array.isArray(n._subtasks) ? n._subtasks.length : 0)), 0)
        : 0;
      const engagedAgents = GRAPH.activeProjectId
        ? new Set(
            GRAPH.nodes
              .filter((n) => n.type === "agent" && n._taskRef)
              .map((n) => n.id)
          ).size
        : Number(s.agents_active || 0);
      
      el.innerHTML = `
        <div class="hud-item"><span class="hud-val">${s.projects}</span><span class="hud-label">Projects</span></div>
        <div class="hud-item"><span class="hud-val">${s.channels}</span><span class="hud-label">Channels</span></div>
        <div class="hud-item"><span class="hud-val">${masterTaskCount}</span><span class="hud-label">主任务</span></div>
        <div class="hud-item"><span class="hud-val">${subtasksCount}</span><span class="hud-label">子任务</span></div>
        <div class="hud-item"><span class="hud-val">${engagedAgents} <span style="font-size:0.7em;opacity:0.6;font-weight:400">/ ${s.agents_total}</span></span><span class="hud-label">关联Agent</span></div>
        <div class="hud-item"><span class="hud-val">${s.runs_running} <span style="font-size:0.7em;opacity:0.6;font-weight:400">/ ${s.runs_total}</span></span><span class="hud-label">Running</span></div>
        <div class="hud-item"><span class="hud-val" style="color:${s.links_high_risk > 0 ? '#fc8181' : '#fff'}">${s.links_high_risk}</span><span class="hud-label">High Risk</span></div>
        <div class="hud-item"><span class="hud-val" style="color:${missingSession > 0 ? '#f6ad55' : '#fff'}">${missingSession}</span><span class="hud-label">No Session</span></div>
      `;
    }

    // 2.5D Projection
    function projectIso(x, y, z) {
      // Simple Isometric
      // x axis goes right-down, z axis goes left-down
      // y axis goes up
      const isoX = (x - z) * 0.866;
      const isoY = (x + z) * 0.5 - y;
      
      return {
        x: isoX * GRAPH.camera.zoom + GRAPH.camera.x,
        y: isoY * GRAPH.camera.zoom + GRAPH.camera.y
      };
    }

    function drawQuadPath(ctx, corners) {
      if (!corners || corners.length < 4) return;
      ctx.beginPath();
      ctx.moveTo(corners[0].x, corners[0].y);
      for (let i = 1; i < corners.length; i += 1) {
        ctx.lineTo(corners[i].x, corners[i].y);
      }
      ctx.closePath();
    }

    function drawRoundedRectPath(ctx, x, y, w, h, r) {
      const radius = Math.max(0, Math.min(r || 0, w * 0.5, h * 0.5));
      ctx.beginPath();
      ctx.moveTo(x + radius, y);
      ctx.arcTo(x + w, y, x + w, y + h, radius);
      ctx.arcTo(x + w, y + h, x, y + h, radius);
      ctx.arcTo(x, y + h, x, y, radius);
      ctx.arcTo(x, y, x + w, y, radius);
      ctx.closePath();
    }

    function withQuadTransform(ctx, corners, drawFn) {
      if (!corners || corners.length < 4) return;
      let p0 = corners[0];
      let p1 = corners[1];
      const p2 = corners[2];
      const p3 = corners[3];

      let ux = p1.x - p0.x;
      let uy = p1.y - p0.y;
      let vx = p3.x - p0.x;
      let vy = p3.y - p0.y;
      
      // V2-P2-R8: Check for mirroring (Determinant)
      const det = ux * vy - uy * vx;
      
      if (det < 0) {
          // If mirrored, flip the local coordinate system
          // Move origin to p1 (TR)
          const old_p0 = p0;
          p0 = p1;
          
          // New u: points from new origin (old p1) to old p0
          ux = old_p0.x - p0.x;
          uy = old_p0.y - p0.y;
          
          // New v: points from new origin (old p1) to old p2
          vx = p2.x - p0.x;
          vy = p2.y - p0.y;
      }

      const uLen = Math.hypot(ux, uy);
      const vLen = Math.hypot(vx, vy);
      
      if (uLen < 1 || vLen < 1) return;
      
      ctx.save();
      // Transform: map (0,0) -> p0, (1,0) -> p0+u, (0,1) -> p0+v
      ctx.transform(ux / uLen, uy / uLen, vx / vLen, vy / vLen, p0.x, p0.y);
      // Pass isMirrored as false because we corrected it
      drawFn(uLen, vLen, false);
      ctx.restore();
    }

    function normalizeVec3(v) {
      const len = Math.hypot(v.x || 0, v.y || 0, v.z || 0) || 1;
      return { x: (v.x || 0) / len, y: (v.y || 0) / len, z: (v.z || 0) / len };
    }

    function buildPanelWorldCorners(center, width, height, rightVec, upVec) {
      const r = normalizeVec3(rightVec || { x: 1, y: 0, z: 0 });
      const u = normalizeVec3(upVec || { x: 0, y: 1, z: 0 });
      const hw = Math.max(1, width) * 0.5;
      const hh = Math.max(1, height) * 0.5;
      const rx = r.x * hw;
      const ry = r.y * hw;
      const rz = r.z * hw;
      const ux = u.x * hh;
      const uy = u.y * hh;
      const uz = u.z * hh;
      return [
        { x: center.x - rx + ux, y: center.y - ry + uy, z: center.z - rz + uz }, // top-left
        { x: center.x + rx + ux, y: center.y + ry + uy, z: center.z + rz + uz }, // top-right
        { x: center.x + rx - ux, y: center.y + ry - uy, z: center.z + rz - uz }, // bottom-right
        { x: center.x - rx - ux, y: center.y - ry - uy, z: center.z - rz - uz }, // bottom-left
      ];
    }

    function drawTiltedTextOnPanel(ctx, shearOrDrawFn, maybeDrawFn, isMirrored) {
      const drawFn = (typeof shearOrDrawFn === "function") ? shearOrDrawFn : maybeDrawFn;
      const shearX = (typeof shearOrDrawFn === "number") ? shearOrDrawFn : -0.16;
      if (typeof drawFn !== "function") return;
      ctx.save();
      
      // V2-P2-R7: Fix mirrored text - REMOVED scaling, handled in withQuadTransform
      
      ctx.transform(1, 0, shearX, 1, 0, 0);
      drawFn();
      ctx.restore();
    }

    function clampNum(v, minV, maxV) {
      return Math.min(maxV, Math.max(minV, v));
    }

    function isPointInQuad(px, py, corners) {
      if (!corners || corners.length < 4) return false;
      let inside = false;
      for (let i = 0, j = corners.length - 1; i < corners.length; j = i, i += 1) {
        const xi = corners[i].x;
        const yi = corners[i].y;
        const xj = corners[j].x;
        const yj = corners[j].y;
        const intersects = ((yi > py) !== (yj > py)) &&
          (px < ((xj - xi) * (py - yi)) / ((yj - yi) || 1e-6) + xi);
        if (intersects) inside = !inside;
      }
      return inside;
    }

    function resolveTaskStatusColor(taskNode) {
      let statusColor = STATUS_COLORS.other;
      const sb = String((taskNode && taskNode.status_bucket) || "").toLowerCase();
      if (STATUS_COLORS[sb]) return STATUS_COLORS[sb];
      const st = String((taskNode && taskNode.status) || "").toLowerCase();
      if (st.includes("完成") || st === "done" || st === "completed") statusColor = STATUS_COLORS.done;
      else if (st.includes("进行中") || st === "in_progress" || st === "running") statusColor = STATUS_COLORS.in_progress;
      else if (st.includes("督办") || st.includes("阻塞") || st === "blocked") statusColor = STATUS_COLORS.blocked;
      else if (st.includes("待验收") || st === "pending_acceptance") statusColor = STATUS_COLORS.pending_acceptance;
      return statusColor;
    }

    function resolveTaskStatusText(taskNode) {
      const sb = String((taskNode && taskNode.status_bucket) || "").trim();
      const st = String((taskNode && taskNode.status) || "").trim();
      return st || sb || "未标记";
    }

    function formatDurationLabel(secRaw) {
      const sec = Math.max(0, Number(secRaw) || 0);
      if (!sec) return "--";
      if (sec < 60) return `${Math.round(sec)}s`;
      if (sec < 3600) {
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}m${s.toString().padStart(2, "0")}s`;
      }
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      return `${h}h${m.toString().padStart(2, "0")}m`;
    }

    function deriveAgentDurationSeconds(agent) {
      if (!agent) return 0;
      const direct = Number(
        agent.current_run_duration_s
        || agent.current_run_elapsed_s
        || agent.running_seconds
        || 0
      );
      if (Number.isFinite(direct) && direct > 0) return direct;
      const startText = agent.current_run_at || agent.started_at || "";
      const startTs = parseIsoTs(startText);
      const st = String(agent.current_run_status || agent.status || "").toLowerCase();
      if (startTs > 0 && (st === "running" || st === "queued" || st === "retry_waiting")) {
        return Math.max(0, (Date.now() - startTs) / 1000);
      }
      return 0;
    }

    function isRuntimeBubbleVisible(bubble, nowTs) {
      const now = Number(nowTs || Date.now());
      if (!bubble) return false;
      const expTs = parseIsoTs(bubble.expires_at || bubble.expire_at || "");
      if (expTs > 0 && expTs <= now) return false;
      if (Boolean(bubble.active) && expTs <= 0) return true;
      const ttl = Number(bubble.ttl_seconds || 0);
      const stTs = parseIsoTs(bubble.started_at || bubble.updated_at || "");
      if (ttl > 0 && stTs > 0 && expTs <= 0) {
        const hardExpire = stTs + ttl * 1000;
        if (hardExpire <= now) return false;
      }
      return true;
    }

    function getRuntimeBubbleLevelColor(level) {
      const lv = String(level || "").toLowerCase();
      if (lv === "success") return "#22c55e";
      if (lv === "warning" || lv === "warn") return "#f59e0b";
      if (lv === "error" || lv === "danger") return "#ef4444";
      if (lv === "info") return "#0ea5e9";
      return "#64748b";
    }

    function getAgentRuntimeBubbles(agent) {
      if (!agent) return [];
      const sid = String(agent.session_id || "");
      const ch = String(agent.channel_name || "");
      const keys = [
        `${sid}|${ch}`,
        `${sid}|`,
        `|${ch}`,
      ];
      const merged = [];
      const seen = new Set();
      keys.forEach((k) => {
        const list = GRAPH.runtimeBubbleIndex.get(k) || [];
        list.forEach((b) => {
          const uniq = `${b.bubble_type}|${b.source_run_id}|${b.started_at}`;
          if (seen.has(uniq)) return;
          seen.add(uniq);
          merged.push(b);
        });
      });
      const now = Date.now();
      return merged.filter((b) => isRuntimeBubbleVisible(b, now));
    }

    function buildWallAgentBubbles(wn) {
      if (!wn || wn.type !== "wall_agent" || !wn.agent_ref) return [];
      const w = Number(wn._size?.w || 0);
      const h = Number(wn._size?.h || 0);
      if (!w || !h) return [];
      const a = wn.agent_ref;
      const runtimeBubbles = getAgentRuntimeBubbles(a);
      const byType = new Map();
      runtimeBubbles.forEach((b) => {
        const k = String(b.bubble_type || "status");
        if (!byType.has(k)) byType.set(k, b);
      });
      const statusBubble = byType.get("status");
      const elapsedBubble = byType.get("elapsed");
      const peerBubble = byType.get("peer_mention");
      const fallbackDurationSec = deriveAgentDurationSeconds(a);
      const fallbackStatusText = String(a.current_run_status || a.status || "idle");
      const baseX = w * 0.5 - 16;
      const baseY = -h * 0.5 + 12;
      const r = 9;
      const relatedRef = statusBubble || elapsedBubble || peerBubble || null;
      const relatedObjects = Array.isArray(relatedRef?.related_objects) ? relatedRef.related_objects : [];
      const relatedExtra = Math.max(0, Number(relatedRef?.related_object_extra_count || 0));
      const relatedShown = Math.min(2, relatedObjects.length || 0);
      const relatedLabel = relatedExtra > 0 ? `${relatedShown}+${relatedExtra}` : (relatedShown > 0 ? String(relatedShown) : "");
      const relatedTooltipText = relatedShown > 0
        ? `关联对象: ${relatedObjects.slice(0, 2).map((x) => x.label || x.key || x.type).join(" / ")}${relatedExtra > 0 ? ` +${relatedExtra}` : ""}`
        : "";
      const bubbles = [
        {
          id: `${wn.id}:status`,
          ownerId: wn.id,
          kind: "status",
          x: baseX,
          y: baseY,
          r,
          color: getRuntimeBubbleLevelColor(statusBubble?.level || toneToLevel("", fallbackStatusText)),
          text: "S",
          tooltip: `状态: ${String(statusBubble?.text || fallbackStatusText)}`
        },
        {
          id: `${wn.id}:duration`,
          ownerId: wn.id,
          kind: "duration",
          x: baseX - 22,
          y: baseY,
          r,
          color: "#0ea5e9",
          text: "T",
          tooltip: `时长: ${String(elapsedBubble?.text || formatDurationLabel(fallbackDurationSec))}`
        }
      ];
      if (relatedLabel) {
        bubbles.push({
          id: `${wn.id}:relation`,
          ownerId: wn.id,
          kind: "relation",
          x: baseX - 44,
          y: baseY,
          r,
          color: "#8b5cf6",
          text: relatedLabel,
          tooltip: relatedTooltipText || "关联对象"
        });
      }
      if (peerBubble) {
        bubbles.push({
          id: `${wn.id}:mention`,
          ownerId: wn.id,
          kind: "peer_mention",
          x: baseX - 66,
          y: baseY,
          r,
          color: getRuntimeBubbleLevelColor(peerBubble.level || "warning"),
          text: "@",
          tooltip: String(peerBubble.text || "协作提醒")
        });
      }
      return bubbles;
    }

    function hitWallBubble(localX, localY) {
      const nodes = GRAPH.wallContentNodes || [];
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        const wn = nodes[i];
        if (wn.type !== "wall_agent") continue;
        const p = wn._localPos;
        const bubbles = buildWallAgentBubbles(wn);
        for (let j = bubbles.length - 1; j >= 0; j -= 1) {
          const b = bubbles[j];
          const dx = localX - (p.x + b.x);
          const dy = localY - (p.y + b.y);
          if ((dx * dx + dy * dy) <= (b.r * b.r)) {
            return { ...b, ownerNode: wn };
          }
        }
      }
      return null;
    }

    function getTaskStatusMeta(taskNode) {
      const bucket = String((taskNode && taskNode.status_bucket) || "").trim().toLowerCase();
      if (TASK_STATUS_META[bucket]) return TASK_STATUS_META[bucket];

      const statusText = resolveTaskStatusText(taskNode);
      if (!statusText || statusText === "未标记") return TASK_STATUS_META.other;
      const key = `custom:${statusText.toLowerCase()}`;
      return { key, label: statusText, order: 80 };
    }

    function buildTaskStatusOptions(tasks) {
      const map = new Map();
      (Array.isArray(tasks) ? tasks : []).forEach((task) => {
        const meta = getTaskStatusMeta(task);
        const hit = map.get(meta.key) || { ...meta, count: 0 };
        hit.count += 1;
        map.set(meta.key, hit);
      });
      return Array.from(map.values()).sort((a, b) => {
        if (a.order !== b.order) return a.order - b.order;
        return String(a.label).localeCompare(String(b.label), "zh-Hans-CN");
      });
    }

    function syncTaskStatusFiltersUI() {
      const panel = document.getElementById("taskStatusFilters");
      if (!panel) return;
      panel.innerHTML = "";
      const opts = Array.isArray(GRAPH.taskStatusOptions) ? GRAPH.taskStatusOptions : [];
      if (!opts.length) {
        const empty = document.createElement("div");
        empty.className = "agent-hint";
        empty.textContent = "当前项目暂无任务状态";
        panel.appendChild(empty);
        return;
      }

      const statusWrap = document.createElement("div");
      statusWrap.className = "task-status-items";
      opts.forEach((item) => {
        const row = document.createElement("label");
        row.className = "graph-filter";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = GRAPH.taskStatusEnabled.has(item.key);
        checkbox.dataset.taskStatus = item.key;
        checkbox.addEventListener("change", (e) => {
          const key = String(e.target.dataset.taskStatus || "");
          if (!key) return;
          if (e.target.checked) GRAPH.taskStatusEnabled.add(key);
          else GRAPH.taskStatusEnabled.delete(key);
          renderGraph();
        });

        const text = document.createElement("span");
        text.textContent = item.label;
        const count = document.createElement("span");
        count.className = "status-count";
        count.textContent = String(item.count || 0);

        row.appendChild(checkbox);
        row.appendChild(text);
        row.appendChild(count);
        statusWrap.appendChild(row);
      });
      panel.appendChild(statusWrap);
    }

    function isRunActive(runNode) {
      const s = String((runNode && runNode.status) || "").toLowerCase();
      return ["running", "queued", "retry_waiting"].includes(s);
    }

    function mapSupportLevel(rawLevel, rawScore) {
      const level = String(rawLevel || "").toLowerCase();
      if (level === "sufficient" || level === "high") return "high";
      if (level === "watch" || level === "medium") return "medium";
      if (level === "insufficient" || level === "low") return "low";
      const score = Number(rawScore);
      if (Number.isFinite(score) && score >= 0) {
        if (score >= 80) return "high";
        if (score >= 60) return "medium";
        return "low";
      }
      return "";
    }

    function mapAssistState(rawState) {
      const state = String(rawState || "").toLowerCase();
      if (state === "pending_reply" || state === "waiting_reply") return "waiting_reply";
      if (["open", "acknowledged", "in_progress", "replied"].includes(state)) return "in_progress";
      if (["resolved", "closed", "canceled"].includes(state)) return "closed";
      if (state === "none") return "none";
      return "";
    }

    function deriveTaskSupportAssist(taskNode) {
      const metrics = (taskNode && taskNode.id && GRAPH.taskSupportMap.get(taskNode.id)) || null;
      const activeRuns = metrics ? Number(metrics.active_runs || 0) : 0;
      const activeAgents = metrics ? Number(metrics.active_agents || 0) : 0;
      const statusBucket = String((taskNode && taskNode.status_bucket) || "").toLowerCase();
      const supportScoreRaw = Number(taskNode && taskNode.support_score);
      const assistTotal = Number((taskNode && taskNode.assist_total) || 0);
      const pendingReplyCount = Number((taskNode && taskNode.assist_pending_reply_count) || 0);
      const inProgressCount = Number((taskNode && taskNode.assist_in_progress_count) || 0);
      const openCount = Number((taskNode && taskNode.assist_open_count) || 0);
      const resolvedCount = Number((taskNode && taskNode.assist_resolved_count) || 0);

      let supportLevel = mapSupportLevel(taskNode && taskNode.support_level, supportScoreRaw);
      if (!supportLevel) {
        // 回退：兼容旧数据（尚未产出 support_level/support_score）。
        if (activeRuns > 0 && activeAgents > 0) supportLevel = "high";
        else if (activeRuns > 0 || activeAgents > 0) supportLevel = "medium";
        else supportLevel = "low";
      }

      let assistState = mapAssistState(taskNode && taskNode.assist_state);
      if (!assistState && assistTotal > 0) {
        if (pendingReplyCount > 0) assistState = "waiting_reply";
        else if (inProgressCount > 0 || openCount > 0) assistState = "in_progress";
        else if (resolvedCount > 0) assistState = "closed";
      }
      if (!assistState) {
        // 回退：无显式协助对象时沿用旧推导，保障旧项目可读。
        if (statusBucket === "done" && activeRuns === 0) assistState = "closed";
        else if (activeRuns > 0 || activeAgents > 0) assistState = "in_progress";
        else assistState = "none";
      }

      const supportColor = supportLevel === "high" ? "#22c55e" : (supportLevel === "medium" ? "#f59e0b" : "#ef4444");
      const assistColor = assistState === "in_progress"
        ? "#38bdf8"
        : (assistState === "closed" ? "#94a3b8" : (assistState === "waiting_reply" ? "#fb923c" : "#64748b"));
      const supportText = supportLevel === "high" ? "充足" : (supportLevel === "medium" ? "一般" : "不足");
      const assistText = assistState === "in_progress"
        ? "协助中"
        : (assistState === "closed" ? "已收口" : (assistState === "waiting_reply" ? "待回复" : "未触发"));

      return {
        active_runs: activeRuns,
        active_agents: activeAgents,
        support_level: supportLevel,
        support_text: supportText,
        support_color: supportColor,
        support_score: Number.isFinite(supportScoreRaw) ? Math.max(0, Math.min(100, supportScoreRaw)) : "",
        assist_state: assistState,
        assist_text: assistText,
        assist_color: assistColor,
        assist_total: Number.isFinite(assistTotal) ? Math.max(0, assistTotal) : 0,
      };
    }

    function getTaskNodeForFilter(node) {
      if (!node) return null;
      if (node.type === "task") return node;
      if (node.type === "wall_task" && node.task_ref) return node.task_ref;
      if (node.type === "wall_agent" && node.agent_ref && node.agent_ref._taskRef) {
        return GRAPH.nodeMap.get(node.agent_ref._taskRef) || null;
      }
      if (node.type === "agent" && node._taskRef) return GRAPH.nodeMap.get(node._taskRef) || null;
      if (node.type === "run") {
        const taskId = GRAPH.runTaskMap.get(node.id) || GRAPH.runTaskMap.get(String(node.run_id || ""));
        return taskId ? (GRAPH.nodeMap.get(taskId) || null) : null;
      }
      return null;
    }

    function nodePassesAssistFilters(node) {
      const hasAssistFilter = GRAPH.filters.support_low
        || GRAPH.filters.assist_in_progress
        || GRAPH.filters.assist_waiting_reply
        || GRAPH.filters.assist_closed;
      if (!hasAssistFilter) return true;

      const taskNode = getTaskNodeForFilter(node);
      if (!taskNode) {
        return node.type === "project" || node.type === "channel";
      }

      const derived = deriveTaskSupportAssist(taskNode);
      if (GRAPH.filters.support_low && derived.support_level !== "low") return false;

      const assistExpected = [];
      if (GRAPH.filters.assist_in_progress) assistExpected.push("in_progress");
      if (GRAPH.filters.assist_waiting_reply) assistExpected.push("waiting_reply");
      if (GRAPH.filters.assist_closed) assistExpected.push("closed");
      if (assistExpected.length && !assistExpected.includes(derived.assist_state)) return false;

      return true;
    }

    function nodePassesTaskStatusFilters(node) {
      const opts = Array.isArray(GRAPH.taskStatusOptions) ? GRAPH.taskStatusOptions : [];
      if (!opts.length) return true;
      if (GRAPH.taskStatusEnabled.size >= opts.length) return true;

      // 顶部状态筛选仅作用任务卡，不影响 Agent 资源墙/资源点可见性。
      if (!node || (node.type !== "task" && node.type !== "wall_task")) return true;
      const taskNode = node.type === "wall_task" ? node.task_ref : node;
      if (!taskNode) return true;
      const meta = getTaskStatusMeta(taskNode);
      return GRAPH.taskStatusEnabled.has(meta.key);
    }

    function getSelectedBatchKey() { return ""; }

    function nodeMatchesSelectedBatch(node) { return true; }

    function getNodeRenderAlpha(node) { return 1; }

    function getEdgeRenderAlpha(sourceNode, targetNode) { return 1; }

    function wrapCanvasText(ctx, text, maxWidth, maxLines) {
      const raw = String(text || "").trim();
      if (!raw) return [];
      const lines = [];
      const paragraphs = raw.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
      let truncated = false;
      paragraphs.forEach((para) => {
        if (lines.length >= maxLines) {
          truncated = true;
          return;
        }
        const chars = Array.from(para);
        let line = "";
        let idx = 0;
        while (idx < chars.length && lines.length < maxLines) {
          const ch = chars[idx];
          const test = line + ch;
          if (ctx.measureText(test).width > maxWidth && line) {
            lines.push(line);
            line = "";
          } else {
            line = test;
            idx += 1;
          }
        }
        if (line && lines.length < maxLines) lines.push(line);
        if (idx < chars.length) truncated = true;
      });
      if (truncated && lines.length) {
        lines[lines.length - 1] = `${lines[lines.length - 1]}…`;
      }
      return lines;
    }

    function startGraphLoop() {
      if (GRAPH.rafId) return;
      function loop() {
        renderGraph();
        GRAPH.rafId = requestAnimationFrame(loop);
      }
      loop();
    }
    function stopGraphLoop() {
      cancelAnimationFrame(GRAPH.rafId);
      GRAPH.rafId = 0;
    }

    function getVisibleNodes() {
      let nodes = GRAPH.nodes;

      // Active Agents Filter
      if (GRAPH.filters.active_agents) {
          nodes = nodes.filter(n => {
              if (n.type === 'agent') {
                  return isAgentActive(n);
              }
              if (n.type === 'wall_agent' && n.agent_ref) {
                  return isAgentActive(n.agent_ref);
              }
              return true;
          });
      }

      if (GRAPH.filters.risk) {
        const highRiskChannels = nodes.filter(n => n.type === 'channel' && (n.risk_score || 0) >= 50);
        const seeds = new Set(highRiskChannels.map(n => n.id));
        const relevantIds = new Set(seeds);
        GRAPH.edges.forEach(e => {
          if (seeds.has(e.source)) relevantIds.add(e.target);
          if (seeds.has(e.target)) relevantIds.add(e.source);
        });
        return nodes.filter(n => relevantIds.has(n.id) && nodePassesAssistFilters(n) && nodePassesTaskStatusFilters(n));
      } else {
        return nodes.filter(n => {
            if (n.type === "org_node") return true; // Always visible in Org Mode
            if (n.type === "wall_bg") return true;
            if (n.type === 'wall_agent') {
              return GRAPH.filters.agent && nodePassesAssistFilters(n) && nodePassesTaskStatusFilters(n);
            }
            if (n.type === 'wall_task') {
              return GRAPH.filters.task && nodePassesAssistFilters(n) && nodePassesTaskStatusFilters(n);
            }
            const base = Boolean(GRAPH.filters[n.type]);
            return base && nodePassesAssistFilters(n) && nodePassesTaskStatusFilters(n);
        });
      }
    }

    // V2-P2-R14: LOD Hysteresis State
    const LOD = {
        showStatus: false,
        showMeta: false
    };

    function updateLOD(zoom) {
        // Hysteresis for Status
        if (!LOD.showStatus && zoom >= 0.98) LOD.showStatus = true;
        else if (LOD.showStatus && zoom < 0.92) LOD.showStatus = false;

        // Hysteresis for Meta
        if (!LOD.showMeta && zoom >= 1.33) LOD.showMeta = true;
        else if (LOD.showMeta && zoom < 1.27) LOD.showMeta = false;
    }

    function renderGraph() {
      const ctx = GRAPH.ctx;
      ctx.fillStyle = G_COLORS.bg;
      ctx.fillRect(0, 0, GRAPH.width, GRAPH.height);

      updateLOD(GRAPH.camera.zoom); // Update LOD state once per frame

      if (GRAPH.activeProjectId && Array.isArray(GRAPH.sceneWalls)) {
        GRAPH.sceneWalls.forEach(wall => {
          const corners = (wall.corners || []).map(c => projectIso(c.x, c.y, c.z));
          if (corners.length < 4) return;
          ctx.save();
          ctx.fillStyle = wall.type === "left" ? "rgba(20, 28, 43, 0.72)" : "rgba(22, 30, 46, 0.66)";
          ctx.strokeStyle = "rgba(148, 163, 184, 0.28)";
          ctx.lineWidth = 1;
          drawQuadPath(ctx, corners);
          ctx.fill();
          ctx.stroke();
          ctx.restore();
        });
      }

      const visibleNodes = getVisibleNodes();
      const visibleIds = new Set(visibleNodes.map(n => n.id));

      // Draw Edges
      ctx.lineWidth = 1 * GRAPH.camera.zoom;
      GRAPH.edges.forEach(e => {
        if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) return;
        const sNode = GRAPH.nodeMap.get(e.source);
        const tNode = GRAPH.nodeMap.get(e.target);
        if (!sNode || !tNode) return;
        const edgeAlpha = getEdgeRenderAlpha(sNode, tNode);
        if (edgeAlpha <= 0) return;
        ctx.save();
        ctx.globalAlpha = edgeAlpha;

        const s = projectIso(sNode._pos.x, sNode._pos.y, sNode._pos.z);
        const t = projectIso(tNode._pos.x, tNode._pos.y, tNode._pos.z);

        ctx.strokeStyle = G_COLORS.edge;
        
        // V2-P3-R2: Wall Org Lines
        if (e.type === 'wall_org_line') {
            const midY = (sNode._pos.y + tNode._pos.y) / 2;
            const p1 = sNode._pos;
            const p4 = tNode._pos;
            // Manhattan: Down -> Horizontal -> Down
            const p2 = { x: p1.x, y: midY, z: p1.z };
            const p3 = { x: p4.x, y: midY, z: p4.z };
            
            const cp1 = projectIso(p1.x, p1.y, p1.z);
            const cp2 = projectIso(p2.x, p2.y, p2.z);
            const cp3 = projectIso(p3.x, p3.y, p3.z);
            const cp4 = projectIso(p4.x, p4.y, p4.z);
            
            ctx.strokeStyle = "#94a3b8";
            ctx.lineWidth = 1.5 * GRAPH.camera.zoom;
            ctx.beginPath();
            ctx.moveTo(cp1.x, cp1.y);
            ctx.lineTo(cp2.x, cp2.y);
            ctx.lineTo(cp3.x, cp3.y);
            ctx.lineTo(cp4.x, cp4.y);
            ctx.stroke();
            ctx.restore();
            return;
        }

        if (GRAPH.selectedNode && (e.source === GRAPH.selectedNode.id || e.target === GRAPH.selectedNode.id)) {
          ctx.strokeStyle = G_COLORS.edgeHighlight;
          ctx.lineWidth = 2 * GRAPH.camera.zoom;
        }

        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.stroke();
        ctx.lineWidth = 1 * GRAPH.camera.zoom; // reset
        ctx.restore();
      });

      // Draw Nodes (Sort by Z roughly for occlusion)
      visibleNodes.sort((a, b) => (a._pos.x + a._pos.z) - (b._pos.x + b._pos.z)); // Depth sort

      visibleNodes.forEach(n => {
        ctx.save();
        ctx.globalAlpha = getNodeRenderAlpha(n);
        const p = projectIso(n._pos.x, n._pos.y, n._pos.z);
        const size = (n.type === 'project' ? 20 : n.type === 'channel' ? 12 : 6) * GRAPH.camera.zoom;
        n._screenQuad = null;
        
        ctx.fillStyle = G_COLORS[n.type] || '#ccc';
        if (GRAPH.selectedNode && GRAPH.selectedNode.id === n.id) {
            ctx.shadowColor = "#fff";
            ctx.shadowBlur = 10;
        } else {
            ctx.shadowBlur = 0;
        }

        if (n.type === 'org_node') {
            // V2-P3-R1: Org Node Rendering
            const zoom = GRAPH.camera.zoom;
            const size = (n._size || 20) * zoom;
            
            // Draw Card Background
            // L0: Circle/Diamond? User said "L0 总控（主体-总控）"
            // L2: Leader
            // L3: Member
            
            ctx.fillStyle = "rgba(30, 41, 59, 0.9)";
            ctx.strokeStyle = "rgba(148, 163, 184, 0.2)";
            ctx.lineWidth = 1;
            
            if (n.subtype === 'L0') {
                // Diamond
                ctx.beginPath();
                ctx.moveTo(p.x, p.y - size);
                ctx.lineTo(p.x + size * 1.5, p.y);
                ctx.lineTo(p.x, p.y + size);
                ctx.lineTo(p.x - size * 1.5, p.y);
                ctx.closePath();
                ctx.fillStyle = "#2d3748";
                ctx.fill();
                ctx.stroke();
                
                ctx.fillStyle = "#fff";
                ctx.font = `bold ${14 * zoom}px sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(n.label, p.x, p.y);
            } else {
                // Card (Rect)
                // L2 bigger than L3
                const w = (n.subtype === 'L2' ? 120 : 100) * zoom;
                const h = (n.subtype === 'L2' ? 40 : 24) * zoom;
                
                const x = p.x - w / 2;
                const y = p.y - h / 2;
                
                ctx.fillRect(x, y, w, h);
                ctx.strokeRect(x, y, w, h);
                
                // Avatar / Status Dot
                const a = n.agent_ref;
                const isActive = a ? isAgentActive(a) : false;
                
                if (a) {
                    // Status Dot
                    ctx.beginPath();
                    ctx.arc(x + 10 * zoom, y + h / 2, 4 * zoom, 0, Math.PI * 2);
                    ctx.fillStyle = isActive ? "#f59e0b" : "#64748b";
                    ctx.fill();
                    
                    // Name
                    ctx.fillStyle = "#e2e8f0";
                    ctx.font = `${(n.subtype === 'L2' ? 12 : 10) * zoom}px sans-serif`;
                    ctx.textAlign = "left";
                    ctx.textBaseline = "middle";
                    ctx.fillText(n.label, x + 20 * zoom, y + h / 2);
                    
                    // Subtitle for L2 (Channel Name)
                    if (n.subtype === 'L2' && n.channel_name && zoom > 0.8) {
                        ctx.fillStyle = "#94a3b8";
                        ctx.font = `${9 * zoom}px sans-serif`;
                        ctx.textAlign = "right";
                        ctx.fillText(n.channel_name, x + w - 6 * zoom, y + h / 2);
                    }
                }
            }
        } else if (n.type === 'wall_bg') {
            ctx.fillStyle = "rgba(15, 23, 42, 0.4)";
            ctx.strokeStyle = "rgba(148, 163, 184, 0.1)";
            ctx.lineWidth = 1;
            
            const corners = n._screenQuad || n._corners.map(c => projectIso(c.x, c.y, c.z));
            n._screenQuad = corners;
            
            drawQuadPath(ctx, corners);
            ctx.fill();
            ctx.stroke();

            // Transform to Wall Local Space (0,0 at top-left)
            withQuadTransform(ctx, corners, (localW, localH, isMirrored) => {
                const headerH = GRAPH.wallHeaderHeight;
                
                // --- 1. Draw Header (Fixed) ---
                ctx.save();
                ctx.beginPath();
                ctx.rect(0, 0, localW, headerH);
                ctx.clip();
                
                // Draw title bar background
                ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
                ctx.fillRect(0, 0, localW, headerH);
                
                const titleFontSize = 24;
                const wallTitle = n.label || "Agents资源榜";
                
                // Draw title text
                drawTiltedTextOnPanel(ctx, PANEL_STYLE.textShear.wallAgent, () => {
                    ctx.font = `bold ${titleFontSize}px sans-serif`;
                    ctx.fillStyle = "#e2e8f0";
                    ctx.textAlign = "left";
                    ctx.textBaseline = "middle";
                    ctx.fillText(wallTitle, 20, headerH * 0.5);
                }, isMirrored);

                // Draw Toggle Buttons
                const toggleW = 160;
                const toggleH = 32;
                const toggleX = localW - toggleW - 20;
                const toggleY = (headerH - toggleH) / 2;
                const isOrg = GRAPH.leftWallMode === 'org';
                
                ctx.fillStyle = "rgba(30, 41, 59, 0.8)";
                ctx.fillRect(toggleX, toggleY, toggleW, toggleH);
                ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
                ctx.strokeRect(toggleX, toggleY, toggleW, toggleH);
                
                // Button 1: Roster
                ctx.fillStyle = !isOrg ? "#3b82f6" : "transparent";
                ctx.fillRect(toggleX, toggleY, toggleW/2, toggleH);
                ctx.fillStyle = !isOrg ? "#fff" : "#94a3b8";
                ctx.font = `14px sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText("列表", toggleX + toggleW/4, toggleY + toggleH/2);
                
                // Button 2: Org
                ctx.fillStyle = isOrg ? "#3b82f6" : "transparent";
                ctx.fillRect(toggleX + toggleW/2, toggleY, toggleW/2, toggleH);
                ctx.fillStyle = isOrg ? "#fff" : "#94a3b8";
                ctx.fillText("组织", toggleX + toggleW*0.75, toggleY + toggleH/2);
                
                // Store hit region for Toggle UI
                n._toggleUI = {
                    x0: Math.max(0, toggleX - 10),
                    y0: Math.max(0, toggleY - 8),
                    x1: Math.min(localW, toggleX + toggleW + 10),
                    y1: Math.min(localH, toggleY + toggleH + 8),
                    midX: toggleX + toggleW * 0.5
                };
                ctx.restore();

                // --- 2. Draw Body Content (Scrollable) ---
                ctx.save();
                ctx.beginPath();
                ctx.rect(0, headerH, localW, localH - headerH);
                ctx.clip(); // Clip to Body Area

                // 三层分离：连线层 -> 结构层 -> 气泡层（命中优先：结构 > 气泡）
                const structureNodes = GRAPH.wallContentNodes || [];
                const structureMap = new Map(structureNodes.map((x) => [x.id, x]));
                const bubbleNodes = [];
                structureNodes.forEach((wn) => {
                    if (wn.type !== "wall_agent") return;
                    const owned = buildWallAgentBubbles(wn).map((b) => ({ ...b, ownerNode: wn }));
                    bubbleNodes.push(...owned);
                });
                GRAPH.wallHitNodes = structureNodes;
                GRAPH.wallHitBubbles = bubbleNodes;

                // Apply Pan/Zoom View Transform
                ctx.translate(GRAPH.leftWallView.x, GRAPH.leftWallView.y);
                ctx.scale(GRAPH.leftWallView.scale, GRAPH.leftWallView.scale);
                
                // Layer 1: 连线层
                ctx.strokeStyle = "#64748b";
                ctx.lineWidth = 1;
                GRAPH.wallContentEdges.forEach(e => {
                    const s = structureMap.get(e.source);
                    const t = structureMap.get(e.target);
                    if (!s || !t) return;
                    
                    const p1 = s._localPos;
                    const p4 = t._localPos;
                    
                    ctx.beginPath();
                    ctx.moveTo(p1.x, p1.y);
                    if (e.type === 'wall_org_line') {
                        // Orthogonal: Down -> Horizontal -> Down
                        const midY = (p1.y + p4.y) / 2;
                        ctx.lineTo(p1.x, midY);
                        ctx.lineTo(p4.x, midY);
                        ctx.lineTo(p4.x, p4.y);
                    } else {
                        ctx.lineTo(p4.x, p4.y);
                    }
                    ctx.stroke();
                });

                // Layer 2: 结构层（可点击主层）
                structureNodes.forEach(wn => {
                    const p = wn._localPos;
                    const w = wn._size.w;
                    const h = wn._size.h;
                    
                    // Cull if out of view (Optional optimization)
                    // ...
                    
                    ctx.save();
                    ctx.translate(p.x, p.y);
                    
                    if (wn.type === 'wall_org_card') {
                        // L0 / L1 Card
                        ctx.fillStyle = wn.subtype === 'L0' ? "#2d3748" : "rgba(30, 41, 59, 0.9)";
                        ctx.strokeStyle = wn.subtype === 'L0' ? "#cbd5e0" : "#94a3b8";
                        ctx.lineWidth = wn.subtype === 'L0' ? 2 : 1;
                        
                        ctx.beginPath();
                        if (wn.subtype === 'L0') {
                            // Diamond
                            ctx.moveTo(0, -h/2);
                            ctx.lineTo(w/2, 0);
                            ctx.lineTo(0, h/2);
                            ctx.lineTo(-w/2, 0);
                        } else {
                            // Rect
                            ctx.rect(-w/2, -h/2, w, h);
                        }
                        ctx.closePath();
                        ctx.fill();
                        ctx.stroke();
                        
                        ctx.fillStyle = "#e2e8f0";
                        ctx.font = wn.subtype === 'L0' ? "bold 16px sans-serif" : "14px sans-serif";
                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";
                        ctx.fillText(wn.label, 0, 0);
                        
                    } else if (wn.type === 'wall_agent') {
                        // Agent Card
                        const a = wn.agent_ref;
                        const isActive = isAgentActive(a);
                        
                        ctx.fillStyle = isActive ? "rgba(245, 158, 11, 0.1)" : "rgba(30, 41, 59, 0.8)";
                        ctx.strokeStyle = isActive ? "#f59e0b" : "rgba(148, 163, 184, 0.3)";
                        ctx.lineWidth = 1;
                        
                        ctx.beginPath();
                        ctx.rect(-w/2, -h/2, w, h);
                        ctx.fill();
                        ctx.stroke();
                        
                        // Avatar
                        const avatarR = 14;
                        const avatarX = -w/2 + 24;
                        const avatarY = 0;
                        
                        ctx.beginPath();
                        ctx.arc(avatarX, avatarY, avatarR, 0, Math.PI*2);
                        ctx.fillStyle = isActive ? "#f59e0b" : "#64748b";
                        ctx.fill();
                        
                        ctx.fillStyle = "#fff";
                        ctx.font = "bold 12px sans-serif";
                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";
                        ctx.fillText(getAgentAvatarLabel(wn.label), avatarX, avatarY);
                        
                        // Text
                        ctx.fillStyle = "#e2e8f0";
                        ctx.font = "14px sans-serif";
                        ctx.textAlign = "left";
                        ctx.fillText(wn.label, avatarX + 24, -6);
                        
                        ctx.fillStyle = isActive ? "#fcd34d" : "#94a3b8";
                        ctx.font = "11px sans-serif";
                        const st = String(a.current_run_status || a.status || 'idle');
                        ctx.fillText(st, avatarX + 24, 12);
                    }
                    
                    ctx.restore();
                });

                // Layer 3: 气泡层（状态/时长/关联对象）
                bubbleNodes.forEach((b) => {
                    const p = b.ownerNode._localPos;
                    const bx = p.x + b.x;
                    const by = p.y + b.y;
                    const hovered = GRAPH.wallHoverBubble && GRAPH.wallHoverBubble.id === b.id;
                    ctx.save();
                    ctx.beginPath();
                    ctx.arc(bx, by, b.r, 0, Math.PI * 2);
                    ctx.fillStyle = b.color;
                    ctx.fill();
                    ctx.lineWidth = hovered ? 2 : 1;
                    ctx.strokeStyle = hovered ? "rgba(255,255,255,0.95)" : "rgba(255,255,255,0.45)";
                    ctx.stroke();
                    ctx.fillStyle = "#fff";
                    ctx.font = "bold 9px sans-serif";
                    ctx.textAlign = "center";
                    ctx.textBaseline = "middle";
                    ctx.fillText(String(b.text || ""), bx, by);
                    ctx.restore();
                });

                ctx.restore(); // End Body Clip
            });

        } else if (n.type === 'wall_task') {
            const t = n.task_ref;
            const w = n._size.w;
            const h = n._size.h;
            const worldCorners = buildPanelWorldCorners(
                n._pos,
                w,
                h,
                PANEL_STYLE.rightWallRightVec,
                PANEL_STYLE.upVec
            );
            const corners = worldCorners.map(c => projectIso(c.x, c.y, c.z));
            n._screenQuad = corners;
            const statusColor = resolveTaskStatusColor(t);
            ctx.fillStyle = "rgba(30, 41, 59, 0.9)";
            ctx.strokeStyle = statusColor;
            ctx.lineWidth = 1;
            drawQuadPath(ctx, corners);
            ctx.fill();
            ctx.stroke();

            withQuadTransform(ctx, corners, (localW, localH, isMirrored) => {
                const padX = Math.max(6, 8 * GRAPH.camera.zoom);
                const padY = Math.max(6, 7 * GRAPH.camera.zoom);
                const stripW = Math.max(3, 4 * GRAPH.camera.zoom);
                const zoom = GRAPH.camera.zoom;
                const isSelected = GRAPH.selectedNode && GRAPH.selectedNode.id === n.id;
                ctx.fillStyle = statusColor;
                ctx.fillRect(0, 0, stripW, localH);

                const statusText = resolveTaskStatusText(t);
                const support = deriveTaskSupportAssist(t);
                // V2-P2-R16-1: Threshold < 8px
                const statusFont = Math.max(7, 22 * zoom);
                const metaFont = Math.max(6.5, 18 * zoom);
                const titleFont = Math.max(8, 25 * zoom);

                // Threshold Check: titleFont < 8px -> Content Bars
                // Use raw size for threshold to ensure we switch to blocks at low zoom
                const isLowDetail = (25 * zoom) < 8;

                drawTiltedTextOnPanel(ctx, PANEL_STYLE.textShear.wallTask, () => {
                    // V2-P2-R15: Low Zoom Content Bars
                    if (isLowDetail && !isSelected) {
                        ctx.fillStyle = "rgba(148, 163, 184, 0.3)"; // Light stripes
                        const barH = Math.max(2, 3 * zoom);
                        const gap = Math.max(2, 3 * zoom);
                        let y = padY;
                        // Draw 3 bars
                        for(let i=0; i<3; i++) {
                             ctx.fillRect(padX, y, localW - padX - 4 * zoom, barH);
                             y += barH + gap;
                        }
                        if (t._subtasks && t._subtasks.length > 0) {
                             const bubbleR = Math.max(2, 4 * zoom);
                             ctx.beginPath();
                             ctx.arc(localW - 6 * zoom, 6 * zoom, bubbleR, 0, Math.PI * 2);
                             ctx.fillStyle = "#3b82f6";
                             ctx.fill();
                        }
                        return;
                    }

                    let currentY = padY;
                    // V2-P2-R14: Readability - Shadow
                    ctx.shadowColor = "rgba(0,0,0,0.8)";
                    ctx.shadowBlur = 3;

                    // V2-P2-R14: LOD (Level of Detail) - Use Global LOD State
                    const showStatus = LOD.showStatus || isSelected;
                    const showMeta = LOD.showMeta || isSelected;

                    if (showStatus) {
                        ctx.font = `${statusFont}px sans-serif`;
                        ctx.fillStyle = "#94a3b8"; // Neutral Gray
                        ctx.textAlign = "left";
                        ctx.textBaseline = "top";
                        ctx.fillText(`[${statusText}]`, padX, currentY);
                        currentY += statusFont + 4 * zoom;
                    }

                    if (showMeta) {
                        ctx.font = `${metaFont}px sans-serif`;
                        ctx.fillStyle = support.support_color;
                        ctx.fillText(`支撑:${support.support_text}`, padX, currentY);
                        ctx.fillStyle = support.assist_color;
                        ctx.fillText(`协助:${support.assist_text}`, padX + 62 * zoom, currentY);
                        const participantCount = Number(t._participantAgentCount || 0);
                        if (participantCount > 0) {
                            ctx.fillStyle = "#93c5fd";
                            ctx.fillText(`参与:${participantCount}`, padX + 124 * zoom, currentY);
                        }
                        currentY += metaFont + 6 * zoom;
                    } else if (showStatus) {
                        currentY += 4 * zoom;
                    }

                    ctx.font = `${titleFont}px sans-serif`;
                    const lineHeight = titleFont + 4 * zoom;
                    const maxLines = Math.max(3, Math.floor(Math.max(10, localH - currentY - padY) / lineHeight));
                    const lines = wrapCanvasText(ctx, getTaskDisplayTitle(t), Math.max(26, localW - padX * 2), maxLines);
                    ctx.fillStyle = "#e2e8f0"; // Light Gray
                    lines.forEach((line, idx) => {
                        ctx.fillText(line, padX, currentY + idx * lineHeight);
                    });
                    
                    if (t._subtasks && t._subtasks.length > 0) {
                        const count = t._subtasks.length;
                        const bubbleR = Math.max(7, 9 * zoom);
                        const bubbleX = localW - bubbleR - 4;
                        const bubbleY = bubbleR + 4;
                        ctx.beginPath();
                        ctx.arc(bubbleX, bubbleY, bubbleR, 0, Math.PI * 2);
                        ctx.fillStyle = "#3b82f6";
                        ctx.fill();
                        ctx.fillStyle = "#fff";
                        ctx.font = `bold ${Math.max(8, 11 * zoom)}px sans-serif`;
                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";
                        ctx.fillText(String(count), bubbleX, bubbleY);
                    }

                    ctx.shadowBlur = 0; // Reset
                }, isMirrored);
            });
        } else if (n.type === 'task') {
             if (GRAPH.activeProjectId) {
                 const plotWorldSize = n._size || 200;
                 
                 // Ground Plot
                 ctx.fillStyle = "rgba(255, 255, 255, 0.05)";
                 const groundCorners = [
                   projectIso(n._pos.x - plotWorldSize / 2, 0, n._pos.z - plotWorldSize / 2),
                   projectIso(n._pos.x + plotWorldSize / 2, 0, n._pos.z - plotWorldSize / 2),
                   projectIso(n._pos.x + plotWorldSize / 2, 0, n._pos.z + plotWorldSize / 2),
                   projectIso(n._pos.x - plotWorldSize / 2, 0, n._pos.z + plotWorldSize / 2),
                 ];
                 drawQuadPath(ctx, groundCorners);
                 ctx.fill();

                 const statusColor = resolveTaskStatusColor(n);
                 // V2-P2-R12: Alignment & Thickness
                 const boardW = plotWorldSize; // Equal width
                 const boardH = Math.max(plotWorldSize * 0.7, 132);
                 const boardThickness = 12; // 8~16 units

                 const boardX = n._pos.x - plotWorldSize * 0.5 + 1; // Epsilon <= 1
                 const boardZ = n._pos.z;
                 const boardYBottom = 2; // 0~2
                 const boardCenter = { x: boardX, y: boardYBottom + boardH * 0.5, z: boardZ };
                 
                 // Calculate Front Face (World)
                 const frontCornersWorld = buildPanelWorldCorners(
                   boardCenter,
                   boardW,
                   boardH,
                   PANEL_STYLE.taskBoardRightVec,
                   PANEL_STYLE.upVec
                 );
                 
                 // Calculate Back Face (World) - Extrude along -X (Thickness)
                 // Since PANEL_STYLE.taskBoardRightVec is {0,0,1} (Z-axis), and Up is Y, the Normal is X.
                 // We want thickness "behind" the front face. If Front is at boardX, Back is at boardX - thickness.
                 const backCenter = { x: boardX - boardThickness, y: boardCenter.y, z: boardCenter.z };
                 const backCornersWorld = buildPanelWorldCorners(
                   backCenter,
                   boardW,
                   boardH,
                   PANEL_STYLE.taskBoardRightVec,
                   PANEL_STYLE.upVec
                 );

                 // Project all
                 const frontCorners = frontCornersWorld.map(c => projectIso(c.x, c.y, c.z));
                 const backCorners = backCornersWorld.map(c => projectIso(c.x, c.y, c.z));
                 n._screenQuad = frontCorners;

                 // Draw Thickness (Side/Top)
                 // Visible sides depend on view. Usually Top and Right (or Left?)
                 // With Iso view:
                 // Top face: Front-Top-Left, Front-Top-Right, Back-Top-Right, Back-Top-Left
                 // Side face: Front-Top-Right, Front-Bottom-Right, Back-Bottom-Right, Back-Top-Right (if visible)
                 
                 // 1. Draw Shadow (optional, simple ground shadow)
                 // ctx.fillStyle = "rgba(0,0,0,0.3)";
                 // ctx.beginPath();
                 // Shadow logic can be complex, skipping for now or simple rect below
                 
                 // 2. Draw Side/Thickness Faces (Darker)
                 ctx.fillStyle = "rgba(15, 23, 42, 1)"; // Dark slate
                 ctx.strokeStyle = "rgba(255,255,255,0.05)";
                 ctx.lineWidth = 0.5;
                 
                 // Top Face
                 ctx.beginPath();
                 ctx.moveTo(frontCorners[0].x, frontCorners[0].y);
                 ctx.lineTo(frontCorners[1].x, frontCorners[1].y);
                 ctx.lineTo(backCorners[1].x, backCorners[1].y);
                 ctx.lineTo(backCorners[0].x, backCorners[0].y);
                 ctx.closePath();
                 ctx.fill();
                 ctx.stroke();

                 // Right Face (or Left? Check visibility)
                 // Right Vector is Z. So "Right" is +Z side. 
                 // In Iso, +Z is Left-Down. -Z is Right-Up.
                 // We usually see the "Top" and one "Side".
                 // Let's draw the side connecting corner 1 and 2 (Right side)
                 ctx.beginPath();
                 ctx.moveTo(frontCorners[1].x, frontCorners[1].y);
                 ctx.lineTo(frontCorners[2].x, frontCorners[2].y);
                 ctx.lineTo(backCorners[2].x, backCorners[2].y);
                 ctx.lineTo(backCorners[1].x, backCorners[1].y);
                 ctx.closePath();
                 ctx.fill(); // Side color same as top or slightly different?
                 ctx.stroke();

                 // 3. Draw Front Face
                 ctx.fillStyle = "rgba(30, 41, 59, 1)"; // Front brighter
                 // V2-P2-R12: Color Reduction - Only left edge status color
                 ctx.strokeStyle = "rgba(148, 163, 184, 0.2)"; // Neutral edge
                 ctx.lineWidth = 1;
                 drawQuadPath(ctx, frontCorners);
                 ctx.fill();
                 ctx.stroke();

                 // Draw Left Status Strip (on Front Face)
                 withQuadTransform(ctx, frontCorners, (localW, localH, isMirrored) => {
                   const stripW = Math.max(4, 6 * GRAPH.camera.zoom);
                   const zoom = GRAPH.camera.zoom;
                   const isSelected = GRAPH.selectedNode && GRAPH.selectedNode.id === n.id;
                   ctx.fillStyle = statusColor;
                   ctx.fillRect(0, 0, stripW, localH); // Left strip

                   const padX = Math.max(7, 9 * GRAPH.camera.zoom) + stripW; // Offset by strip
                   const padY = Math.max(6, 7 * GRAPH.camera.zoom);

                   const statusText = resolveTaskStatusText(n);
                   const support = deriveTaskSupportAssist(n);
                   
                   // V2-P2-R16-1: Threshold < 8px
                   const statusFont = Math.max(7, 22 * zoom);
                   const metaFont = Math.max(6.5, 18 * zoom);
                   const titleFont = Math.max(8, 25 * zoom);

                   // Threshold Check: titleFont < 8px -> Content Bars
                   // Use raw size for threshold to ensure we switch to blocks at low zoom
                   const isLowDetail = (25 * zoom) < 8;

                   drawTiltedTextOnPanel(ctx, PANEL_STYLE.textShear.task, () => {
                     // V2-P2-R15: Low Zoom Content Bars
                     if (isLowDetail && !isSelected) {
                         ctx.fillStyle = "rgba(148, 163, 184, 0.3)"; // Light stripes
                         const barH = Math.max(2, 3 * zoom);
                         const gap = Math.max(2, 3 * zoom);
                         let y = padY;
                         // Draw 3 bars
                         for(let i=0; i<3; i++) {
                              ctx.fillRect(padX, y, localW - padX - 4 * zoom, barH);
                              y += barH + gap;
                         }
                         // Draw bubble even in low detail? Maybe just a dot.
                         if (n._subtasks && n._subtasks.length > 0) {
                             const bubbleR = Math.max(3, 5 * zoom);
                             ctx.beginPath();
                             ctx.arc(localW - 8 * zoom, 8 * zoom, bubbleR, 0, Math.PI * 2);
                             ctx.fillStyle = "#3b82f6";
                             ctx.fill();
                         }
                         return;
                     }

                     let currentY = padY;
                     // V2-P2-R14: Readability - Shadow
                     ctx.shadowColor = "rgba(0,0,0,0.8)";
                     ctx.shadowBlur = 3;

                     // V2-P2-R14: LOD (Level of Detail) - Use Global LOD State
                     const showStatus = LOD.showStatus || isSelected;
                     const showMeta = LOD.showMeta || isSelected;

                     if (showStatus) {
                         // Status Text - Muted color (V2-P2-R12)
                         ctx.font = `${statusFont}px sans-serif`;
                         ctx.fillStyle = "#94a3b8"; // Muted
                         ctx.textAlign = "left";
                         ctx.textBaseline = "top";
                         ctx.fillText(`[${statusText}]`, padX, currentY);
                         currentY += statusFont + 4 * zoom;
                     }

                     if (showMeta) {
                         ctx.font = `${metaFont}px sans-serif`;
                         ctx.fillStyle = support.support_color;
                         ctx.fillText(`支撑:${support.support_text}`, padX, currentY);
                         ctx.fillStyle = support.assist_color;
                         ctx.fillText(`协助:${support.assist_text}`, padX + 132 * zoom, currentY);
                         const participantCount = Number(n._participantAgentCount || 0);
                         if (participantCount > 0) {
                             ctx.fillStyle = "#93c5fd";
                             ctx.fillText(`参与:${participantCount}`, padX + 264 * zoom, currentY);
                         }
                         currentY += metaFont + 6 * zoom;
                     } else if (showStatus) {
                         currentY += 4 * zoom; // Gap after status
                     }

                     ctx.font = `${titleFont}px sans-serif`;
                     const lineHeight = titleFont + 4 * zoom;
                     const maxLines = Math.max(2, Math.floor(Math.max(12, localH - currentY - padY) / lineHeight));
                     const lines = wrapCanvasText(ctx, getTaskDisplayTitle(n), Math.max(28, localW - padX - 10), maxLines);
                     ctx.fillStyle = "#e2e8f0";
                     lines.forEach((line, idx) => {
                       ctx.fillText(line, padX, currentY + idx * lineHeight);
                     });
                     
                     // V2-P2-R16-4: Subtask Bubble (High Detail)
                     if (n._subtasks && n._subtasks.length > 0) {
                        const count = n._subtasks.length;
                        const bubbleR = Math.max(8, 10 * zoom);
                        const bubbleX = localW - bubbleR - 4;
                        const bubbleY = bubbleR + 4;
                        
                        ctx.beginPath();
                        ctx.arc(bubbleX, bubbleY, bubbleR, 0, Math.PI * 2);
                        ctx.fillStyle = "#3b82f6"; // Blue
                        ctx.fill();
                        
                        ctx.fillStyle = "#fff";
                        ctx.font = `bold ${Math.max(9, 12 * zoom)}px sans-serif`;
                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";
                        ctx.fillText(String(count), bubbleX, bubbleY);
                     }

                     ctx.shadowBlur = 0; // Reset
                   }, isMirrored);
                 });

             } else {
                 // V1 Square
                 ctx.fillRect(p.x - size/2, p.y - size/2, size, size);
             }
        } else if (n.type === 'agent') {
            // Avatar
            const r = (GRAPH.activeProjectId ? 15 : 6) * GRAPH.camera.zoom;
            const isActive = isAgentActive(n);
            
            ctx.fillStyle = isActive ? G_COLORS.agent : '#4a5568';
            
            // Pulse
            if (isActive) {
                const time = performance.now() / 1000;
                const scale = 1 + Math.sin(time * 3) * 0.2;
                ctx.globalAlpha = 0.3;
                ctx.beginPath();
                ctx.arc(p.x, p.y, r * scale, 0, Math.PI * 2);
                ctx.fill();
                ctx.globalAlpha = 1.0;
            }
            
            ctx.beginPath();
            ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
            ctx.fill();
            
            // Letter
            if (GRAPH.camera.zoom > 0.5) {
                ctx.fillStyle = "#fff";
                ctx.font = `bold ${r}px sans-serif`;
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                const avatarLabel = getAgentAvatarLabel(getAgentName(n));
                ctx.fillText(avatarLabel, p.x, p.y);
                
                // Name Label below (hide in low zoom to reduce overlap)
                const shouldShowAgentLabel = GRAPH.activeProjectId
                    ? ((GRAPH.selectedNode && GRAPH.selectedNode.id === n.id) || (isActive && GRAPH.camera.zoom > 1.25) || GRAPH.camera.zoom > 1.58)
                    : (GRAPH.camera.zoom > 1.15 || (GRAPH.selectedNode && GRAPH.selectedNode.id === n.id));
                if (shouldShowAgentLabel) {
                    ctx.font = `${10 * GRAPH.camera.zoom}px sans-serif`;
                    ctx.fillStyle = "#e2e8f0";
                    const channelLabel = getAgentChannelName(n);
                    const cleanName = channelLabel.length > 14 ? `${channelLabel.slice(0, 14)}…` : channelLabel;
                    ctx.fillText(cleanName, p.x, p.y + r + 11 * GRAPH.camera.zoom);
                }
                
                ctx.textAlign = "start"; // reset
                ctx.textBaseline = "alphabetic"; // reset
            }

        } else if (n.type === 'project') {
           // Diamond
           ctx.beginPath();
           ctx.moveTo(p.x, p.y - size/2);
           ctx.lineTo(p.x + size, p.y);
           ctx.lineTo(p.x, p.y + size/2);
           ctx.lineTo(p.x - size, p.y);
           ctx.fill();
        } else if (n.type === 'channel') {
           // Hexagon or Circle with Pole
           ctx.beginPath();
           ctx.arc(p.x, p.y, size/2, 0, Math.PI * 2);
           ctx.fill();
           // Pole
           ctx.strokeStyle = ctx.fillStyle;
           const ground = projectIso(n._pos.x, 0, n._pos.z);
           ctx.beginPath();
           ctx.moveTo(p.x, p.y);
           ctx.lineTo(ground.x, ground.y);
           ctx.globalAlpha = 0.3;
           ctx.stroke();
           ctx.globalAlpha = 1.0;
        } else {
           // Circle
           ctx.beginPath();
           ctx.arc(p.x, p.y, size/2, 0, Math.PI * 2);
           ctx.fill();
        }

        // Label if selected or zoomed in (Common)
        if (!['task', 'agent', 'wall_agent', 'wall_task'].includes(n.type)
            && (GRAPH.camera.zoom > 1.5 || (GRAPH.selectedNode && GRAPH.selectedNode.id === n.id))) {
           ctx.fillStyle = "#fff";
           ctx.font = `${10 * GRAPH.camera.zoom}px sans-serif`;
           ctx.fillText(n.label || n.id, p.x + size, p.y);
        }
        ctx.restore();
      });

      if (GRAPH.wallHoverBubble && GRAPH.activeProjectId) {
        const tip = GRAPH.wallHoverBubble;
        const text = String(tip.tooltip || "");
        if (text) {
          const padX = 10;
          const padY = 7;
          ctx.save();
          ctx.font = "12px sans-serif";
          const w = ctx.measureText(text).width + padX * 2;
          const h = 28;
          const x = clampNum((tip.screenX || 0) + 14, 8, Math.max(8, GRAPH.width - w - 8));
          const y = clampNum((tip.screenY || 0) + 12, 8, Math.max(8, GRAPH.height - h - 8));
          drawRoundedRectPath(ctx, x, y, w, h, 8);
          ctx.fillStyle = "rgba(2, 6, 23, 0.92)";
          ctx.fill();
          ctx.strokeStyle = "rgba(148, 163, 184, 0.55)";
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.fillStyle = "#e2e8f0";
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.fillText(text, x + padX, y + h * 0.5);
          ctx.restore();
        }
      }
    }

    function handleGraphClick(mx, my) {
      // Reverse Hit Test (Simple distance check in screen space)
      let hit = null;
      // Optimized hit radius: larger when zoomed out
      let minD = Math.max(8, 14 / GRAPH.camera.zoom);

      // Check visible nodes
      const visibleNodes = getVisibleNodes();
      visibleNodes.sort((a, b) => (a._pos.x + a._pos.z) - (b._pos.x + b._pos.z));

      // Search in reverse draw order (topmost first)
      for (let i = visibleNodes.length - 1; i >= 0; i--) {
        const n = visibleNodes[i];
        
        // V2-P3-R7: Wall Interaction (Click)
        if (n.type === 'wall_bg') {
            const hit = mapScreenToWall(mx, my, n);
            if (hit) {
                // 1. Header (Toggle UI)
                if (hit.y <= GRAPH.wallHeaderHeight) {
                    if (n._toggleUI) {
                        const ui = n._toggleUI;
                        if (hit.x >= ui.x0 && hit.x <= ui.x1 && hit.y >= ui.y0 && hit.y <= ui.y1) {
                            const isRoster = hit.x < ui.midX;
                            const newMode = isRoster ? 'roster' : 'org';
                            if (GRAPH.leftWallMode !== newMode) {
                                GRAPH.leftWallMode = newMode;
                                GRAPH.leftWallView = { x: 0, y: 0, scale: 1 };
                                processGraphData(GRAPH.data);
                                renderGraph();
                            }
                            return;
                        }
                    }
                    return; // Header background is non-selectable and consumes click.
                }
                
                // 2. Body (Content Nodes)
                // Transform to Content Space
                const cx = (hit.x - GRAPH.leftWallView.x) / GRAPH.leftWallView.scale;
                const cy = (hit.y - GRAPH.leftWallView.y) / GRAPH.leftWallView.scale;
                
                // Hit Rule Priority:
                // 1) 结构层（主卡）优先
                // 2) 气泡层（映射回所属结构）
                const structureNodes = GRAPH.wallHitNodes && GRAPH.wallHitNodes.length
                    ? GRAPH.wallHitNodes
                    : GRAPH.wallContentNodes;

                // 1) Hit Test Structure Nodes (Reverse order)
                for (let k = structureNodes.length - 1; k >= 0; k--) {
                    const wn = structureNodes[k];
                    const w = wn._size.w;
                    const h = wn._size.h;
                    // Centered rect
                    if (cx >= wn._localPos.x - w/2 && cx <= wn._localPos.x + w/2 &&
                        cy >= wn._localPos.y - h/2 && cy <= wn._localPos.y + h/2) {
                        
                        // Select the underlying reference
                        let target = wn;
                        if (wn.agent_ref) target = wn.agent_ref;
                        else if (wn.task_ref) target = wn.task_ref;
                        
                        GRAPH.selectedNode = target;
                        renderGraph();
                        
                        const details = document.getElementById("graphDetails");
                        if (target) {
                            updateDetailsPanel(target);
                            if (details) details.classList.add("visible");
                        }
                        return;
                    }
                }

                // 2) Hit Test Bubble Layer
                const bubble = hitWallBubble(cx, cy);
                if (bubble && bubble.ownerNode) {
                    const owner = bubble.ownerNode;
                    let target = owner;
                    if (owner.agent_ref) target = owner.agent_ref;
                    else if (owner.task_ref) target = owner.task_ref;
                    GRAPH.selectedNode = target;
                    renderGraph();
                    const details = document.getElementById("graphDetails");
                    if (target) {
                      updateDetailsPanel(target);
                      if (details) details.classList.add("visible");
                    }
                    return;
                }
                
                // Click on wall body background -> Consumed (don't select behind)
                // Maybe clear selection if clicked blank area on wall?
                GRAPH.selectedNode = null;
                renderGraph();
                const details = document.getElementById("graphDetails");
                if (details) details.classList.remove("visible");
                return;
            }
            continue;
        }

        if (n._screenQuad && isPointInQuad(mx, my, n._screenQuad)) {
          hit = n;
          break;
        }
        if (n.type === "task" || n.type === "wall_task" || n.type === "wall_bg") {
          continue;
        }
        const p = projectIso(n._pos.x, n._pos.y, n._pos.z);
        const dx = mx - p.x;
        const dy = my - p.y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < minD) {
          hit = n;
          break; // Found top one
        }
      }

      GRAPH.selectedNode = hit;
      renderGraph(); // Re-render highlight
      
      const details = document.getElementById("graphDetails");
      const sidebar = document.getElementById("graphSidebar");
      
      if (hit) {
          updateDetailsPanel(hit);
          if (details) details.classList.add("visible");
      } else {
          // Click blank: Clear selection and hide drawers
          if (details) details.classList.remove("visible");
          if (sidebar) sidebar.classList.remove("visible");
      }
    }

    function updateDetailsPanel(node) {
      // Redirect wall nodes to their references
      if (node.type === 'wall_agent' && node.agent_ref) {
          updateDetailsPanel(node.agent_ref);
          return;
      }
      if (node.type === 'wall_task' && node.task_ref) {
          updateDetailsPanel(node.task_ref);
          return;
      }
      // V2-P3-R1: Org Node Passthrough
      if (node.type === 'org_node') {
          if (node.agent_ref) {
              updateDetailsPanel(node.agent_ref);
              return;
          }
          // L0 or unknown
      }

      const p = document.getElementById("graphDetails");
      const empty = p.querySelector(".details-empty");
      const content = p.querySelector(".details-content");

      if (!node) {
        empty.hidden = false;
        content.hidden = true;
        return;
      }

      empty.hidden = true;
      content.hidden = false;

      document.getElementById("dType").textContent = node.type;
      document.getElementById("dType").style.color = G_COLORS[node.type];
      
      let title = node.label || node.id;
      let sub = node.id;
      
      if (node.type === 'agent') {
          title = getAgentName(node);
          sub = node.channel_display_name || node.channel_name || '-';
      }
      
      document.getElementById("dTitle").textContent = title;
      document.getElementById("dSub").textContent = sub;

      const body = document.getElementById("dBody");
      body.innerHTML = "";

      // KV Helper
      const addKV = (k, v) => {
        const r = document.createElement("div");
        r.className = "kv-row";
        r.innerHTML = `<span class="kv-key">${k}</span><span class="kv-val">${v}</span>`;
        body.appendChild(r);
      };

      if (node.project_id) addKV("Project", node.project_id);
      if (node.channel_name) addKV("Channel", node.channel_name);
      if (node.risk_score != null) addKV("Risk Score", node.risk_score);
      if (node.status) addKV("Status", node.status);
      if (node.type === "task") {
        const support = deriveTaskSupportAssist(node);
        addKV("Support Level", `${support.support_text} (${support.support_level})`);
        if (support.support_score !== "") addKV("Support Score", support.support_score);
        addKV("Assist State", `${support.assist_text} (${support.assist_state})`);
        addKV("Assist Total", support.assist_total);
        addKV("Active Runs", support.active_runs);
        addKV("Active Agents", support.active_agents);
        const participantAgents = Array.isArray(node._participantAgents) ? node._participantAgents : [];
        addKV("参与 Agent", String(node._participantAgentCount || participantAgents.length || 0));
        if (participantAgents.length) {
            const participantWrap = document.createElement("div");
            participantWrap.style.marginTop = "16px";
            participantWrap.innerHTML = `<div style="font-size:10px;color:#718096;text-transform:uppercase;margin-bottom:8px;letter-spacing:0.05em">参与 Agent (${participantAgents.length})</div>`;
            const list = document.createElement("div");
            list.style.cssText = "display:flex;flex-wrap:wrap;gap:8px";
            participantAgents.forEach((agent) => {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.style.cssText = "padding:4px 10px;border-radius:999px;border:1px solid rgba(99,179,237,0.26);background:rgba(99,179,237,0.08);color:#2b6cb0;font-size:12px;cursor:pointer";
                chip.textContent = getAgentName(agent);
                chip.onclick = () => {
                    GRAPH.selectedNode = agent;
                    renderGraph();
                    updateDetailsPanel(agent);
                };
                list.appendChild(chip);
            });
            participantWrap.appendChild(list);
            body.appendChild(participantWrap);
        }

        // V2-P2-R16-4: Subtasks List
        if (node._subtasks && node._subtasks.length > 0) {
            const stContainer = document.createElement("div");
            stContainer.style.marginTop = "16px";
            stContainer.innerHTML = `<div style="font-size:10px;color:#718096;text-transform:uppercase;margin-bottom:8px;letter-spacing:0.05em">Subtasks (${node._subtasks.length})</div>`;
            
            node._subtasks.forEach(st => {
                const row = document.createElement("div");
                row.style.cssText = "display:flex;align-items:center;gap:8px;padding:4px 0;cursor:pointer;font-size:12px;color:#a0aec0";
                const statusColor = resolveTaskStatusColor(st);
                row.innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:${statusColor}"></span> <span>${getTaskDisplayTitle(st)}</span>`;
                row.onclick = () => {
                    updateDetailsPanel(st);
                };
                stContainer.appendChild(row);
            });
            body.appendChild(stContainer);
        }
        
        // Parent Link for subtasks
        if (node._isSubtask && node._parent) {
             const pContainer = document.createElement("div");
             pContainer.style.marginTop = "16px";
             pContainer.innerHTML = `<div style="font-size:10px;color:#718096;text-transform:uppercase;margin-bottom:8px;letter-spacing:0.05em">Parent Task</div>`;
             const row = document.createElement("div");
             row.style.cssText = "display:flex;align-items:center;gap:8px;padding:4px 0;cursor:pointer;font-size:12px;color:#a0aec0";
             row.innerHTML = `<span style="color:#63b3ed">↑</span> <span>${getTaskDisplayTitle(node._parent)}</span>`;
             row.onclick = () => {
                 GRAPH.selectedNode = node._parent;
                 renderGraph();
                 updateDetailsPanel(node._parent);
             };
             pContainer.appendChild(row);
             body.appendChild(pContainer);
        }
      }
      if (node.updated_at) addKV("Updated", node.updated_at);
      if (node.link_status) addKV("Link Status", node.link_status);
      if (node.freshness_level) addKV("Freshness", node.freshness_level);
      
      // Channel Stats from Links
      if (node.type === 'channel' && GRAPH.data.links) {
        const link = GRAPH.data.links.find(l => l.channel_id === node.id);
        if (link && link.counts) {
           addKV("Tasks", `${link.counts.task_active}/${link.counts.task_total}`);
           addKV("Runs", `${link.counts.runs_running}/${link.counts.runs_total}`);
           if (link.counts.runs_error > 0) addKV("Errors", link.counts.runs_error);
        }
      }
      
      // Relations
      const relContainer = document.createElement("div");
      relContainer.style.marginTop = "16px";
      relContainer.innerHTML = `<div style="font-size:10px;color:#718096;text-transform:uppercase;margin-bottom:8px;letter-spacing:0.05em">Relations</div>`;
      
      const incoming = GRAPH.edges.filter(e => e.target === node.id);
      const outgoing = GRAPH.edges.filter(e => e.source === node.id);
      
      const addLink = (edge, isIn) => {
        const otherId = isIn ? edge.source : edge.target;
        const other = GRAPH.nodes.find(n => n.id === otherId);
        if (!other) return;
        
        const row = document.createElement("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;padding:4px 0;cursor:pointer;font-size:12px;color:#a0aec0";
        const otherName = other.type === 'agent' ? getAgentName(other) : (other.label || other.id);
        row.innerHTML = `<span style="color:#63b3ed">${isIn ? '←' : '→'}</span> <span>${otherName}</span> <span style="margin-left:auto;font-family:monospace;font-size:10px;opacity:0.6">${edge.type}</span>`;
        row.onclick = () => {
          GRAPH.selectedNode = other;
          renderGraph();
          updateDetailsPanel(other);
        };
        relContainer.appendChild(row);
      };
      
      incoming.forEach(e => addLink(e, true));
      outgoing.forEach(e => addLink(e, false));
      
      if (incoming.length || outgoing.length) {
        body.appendChild(relContainer);
      }

      const actions = document.getElementById("dActions");
      actions.innerHTML = "";
      if (node.project_id) {
         const btn = document.createElement("a");
         btn.className = "btn btn-primary";
         btn.textContent = "前往任务看板";
         btn.href = toTaskUrl(node.project_id, node.channel_name);
         actions.appendChild(btn);
      }
    }

    // Init Graph
    initGraphView();

    // V2-P3-R7: Wall Org Layout (Grid)
    function layoutOrgTreeOnWall(agents) {
        const nodes = [];
        const edges = [];
        const contentTop = GRAPH.wallHeaderHeight + 28;
        
        // --- 1. Data Prep ---
        const l0Node = {
            id: 'wall:org:L0',
            type: 'wall_org_card',
            subtype: 'L0',
            label: '总控',
            _localPos: { x: GRAPH.wallFixedSize.w / 2, y: contentTop + 12 },
            _size: { w: 160, h: 60 }
        };
        nodes.push(l0Node);

        const channels = {};
        agents.forEach(a => {
            const cName = getAgentChannelName(a) || "Unknown";
            if (!channels[cName]) channels[cName] = { name: cName, agents: [] };
            channels[cName].agents.push(a);
        });

        const channelList = Object.values(channels);
        channelList.sort((a,b) => a.name.localeCompare(b.name, "zh-Hans-CN"));

        // --- 2. Layout Params ---
        const L1_Y = contentTop + 108;
        const L1_WIDTH = 140;
        const L1_HEIGHT = 36;
        const L2_HEIGHT = 80;
        const L3_HEIGHT = 64;
        const COL_GAP = 20;
        const ROW_GAP = 20;
        
        let currentX = 40; // Padding Left
        let maxY = 0;
        
        channelList.forEach(ch => {
            const sorted = ch.agents.slice().sort((a, b) => {
                const aP = (a.is_primary || String(a.role).includes('primary')) ? 1 : 0;
                const bP = (b.is_primary || String(b.role).includes('primary')) ? 1 : 0;
                if (aP !== bP) return bP - aP;
                const aAct = isAgentActive(a) ? 1 : 0;
                const bAct = isAgentActive(b) ? 1 : 0;
                if (aAct !== bAct) return bAct - aAct;
                return String(a.id).localeCompare(String(b.id));
            });
            
            const leader = sorted[0];
            const members = sorted.slice(1);
            
            // Subgrid for members
            const membersCols = 1; // Single column under leader for simplicity in V1? Or 2? 
            // User said "避免长列一坨" -> Grid implies L3 should be grid.
            // Let's do 2 columns if > 4 members? Or always 1 col if small?
            // "硬朗层级树"
            const useGrid = members.length > 4;
            const subCols = useGrid ? 2 : 1;
            const memberW = 220;
            const memberH = L3_HEIGHT;
            
            const blockWidth = Math.max(memberW * subCols + (subCols-1)*COL_GAP, 280);
            const centerX = currentX + blockWidth / 2;
            
            // L1 Channel Node
            const l1Node = {
                id: `wall:org:L1:${ch.name}`,
                type: 'wall_org_card',
                subtype: 'L1',
                label: ch.name,
                _localPos: { x: centerX, y: L1_Y },
                _size: { w: L1_WIDTH, h: L1_HEIGHT }
            };
            nodes.push(l1Node);
            edges.push({ source: l0Node.id, target: l1Node.id, type: 'wall_org_line' });
            
            // L2 Leader
            const l2Y = L1_Y + L1_HEIGHT/2 + 40 + L2_HEIGHT/2;
            const l2Node = {
                id: `wall:org:L2:${leader.id}`,
                type: 'wall_agent',
                subtype: 'L2',
                agent_ref: leader,
                label: getAgentName(leader),
                channel_name: ch.name,
                _localPos: { x: centerX, y: l2Y },
                _size: { w: 260, h: L2_HEIGHT }
            };
            nodes.push(l2Node);
            edges.push({ source: l1Node.id, target: l2Node.id, type: 'wall_org_line' });
            
            // L3 Members
            let startY = l2Y + L2_HEIGHT/2 + 30;
            const gridStartX = centerX - ((Math.min(members.length, subCols) * (memberW + COL_GAP)) - COL_GAP) / 2 + memberW/2;
            
            members.forEach((m, i) => {
                const col = i % subCols;
                const row = Math.floor(i / subCols);
                const px = gridStartX + col * (memberW + COL_GAP);
                const py = startY + row * (memberH + ROW_GAP) + memberH/2;
                
                const l3Node = {
                    id: `wall:org:L3:${m.id}`,
                    type: 'wall_agent',
                    subtype: 'L3',
                    agent_ref: m,
                    label: getAgentName(m),
                    _localPos: { x: px, y: py },
                    _size: { w: memberW, h: memberH }
                };
                nodes.push(l3Node);
                edges.push({ source: l2Node.id, target: l3Node.id, type: 'wall_org_line' });
                maxY = Math.max(maxY, py + memberH/2);
            });
            
            if (members.length === 0) maxY = Math.max(maxY, l2Y + L2_HEIGHT/2);
            
            currentX += blockWidth + 60; // Channel Gap
        });
        
        // If content is narrower than wall, center it
        const totalW = currentX;
        if (totalW < GRAPH.wallFixedSize.w) {
            const offset = (GRAPH.wallFixedSize.w - totalW) / 2;
            nodes.forEach(n => {
                if (n.subtype !== 'L0') n._localPos.x += offset;
            });
        }
        
        return { nodes, edges, width: totalW, height: Math.max(maxY + 100, GRAPH.wallFixedSize.h) };
    }

    function layoutAgentRosterOnWall(agents) {
        const nodes = [];
        const colCount = 3;
        const cardW = 270;
        const cardH = 86;
        const gapX = 16;
        const gapY = 14;
        const padX = 28;
        const padY = GRAPH.wallHeaderHeight + 18;
        
        const sorted = agents.slice().sort((a, b) => {
            const av = isAgentActive(a) ? 1 : 0;
            const bv = isAgentActive(b) ? 1 : 0;
            if (av !== bv) return bv - av;
            return String(getAgentName(a)).localeCompare(String(getAgentName(b)), "zh-Hans-CN");
        });
        
        sorted.forEach((a, i) => {
            const col = i % colCount;
            const row = Math.floor(i / colCount);
            const x = padX + col * (cardW + gapX) + cardW/2;
            const y = padY + row * (cardH + gapY) + cardH/2;
            
            nodes.push({
                id: `wall:agent:${a.id}`,
                type: 'wall_agent',
                agent_ref: a,
                label: getAgentName(a),
                _localPos: { x, y },
                _size: { w: cardW, h: cardH }
            });
        });
        
        const totalH = Math.ceil(sorted.length / colCount) * (cardH + gapY) + padY * 2;
        
        return { nodes, edges: [], width: padX * 2 + colCount * cardW + (colCount-1)*gapX, height: totalH };
    }
