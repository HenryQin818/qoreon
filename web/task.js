    const DATA = JSON.parse(document.getElementById('data').textContent);
    const OVERVIEW_PAGE = (DATA.links && DATA.links.overview_page) ? String(DATA.links.overview_page) : "/share/project-overview-dashboard.html";
    const AGENT_CURTAIN_PAGE = DATA.agent_curtain_page
      ? String(DATA.agent_curtain_page)
      : ((DATA.links && DATA.links.agent_curtain_page) ? String(DATA.links.agent_curtain_page) : "/share/project-agent-curtain.html");
    const SESSION_HEALTH_PAGE = DATA.session_health_page
      ? String(DATA.session_health_page)
      : ((DATA.links && DATA.links.session_health_page) ? String(DATA.links.session_health_page) : "/share/project-session-health-dashboard.html");
    const STATUS_REPORT_PAGE = DATA.status_report_page
      ? String(DATA.status_report_page)
      : ((DATA.links && DATA.links.status_report_page) ? String(DATA.links.status_report_page) : "/share/project-status-report.html");
    const AGENT_DIRECTORY_PAGE = DATA.agent_directory_page
      ? String(DATA.agent_directory_page)
      : ((DATA.links && DATA.links.agent_directory_page) ? String(DATA.links.agent_directory_page) : "/share/project-agent-directory.html");
    const ITEM_BUNDLE = (DATA && DATA.item_bundle && typeof DATA.item_bundle === "object") ? DATA.item_bundle : null;

    function initBackLink() {
      const link = document.getElementById("backToOverview");
      if (link) link.href = OVERVIEW_PAGE;
      initSystemSettingsMenu();
      const sessionHealthBtn = document.getElementById("sessionHealthBtn");
      if (sessionHealthBtn) sessionHealthBtn.addEventListener("click", openSessionHealthPage);
      const statusReportBtn = document.getElementById("statusReportBtn");
      if (statusReportBtn) statusReportBtn.addEventListener("click", openStatusReportPage);
      const projectAgentDirectoryBtn = document.getElementById("projectAgentDirectoryBtn");
      if (projectAgentDirectoryBtn) projectAgentDirectoryBtn.addEventListener("click", openProjectAgentDirectory);
      const projectAgentCurtainBtn = document.getElementById("projectAgentCurtainBtn");
      if (projectAgentCurtainBtn) projectAgentCurtainBtn.addEventListener("click", openProjectAgentCurtain);
    }

    function initSystemSettingsMenu() {
      const wrap = document.getElementById("systemSettingsWrap");
      const trigger = document.getElementById("systemSettingsTrigger");
      const popover = document.getElementById("systemSettingsPopover");
      const countEl = trigger && trigger.querySelector(".system-settings-count");
      if (!wrap || !trigger || !popover || wrap.__systemSettingsBound) return;
      wrap.__systemSettingsBound = true;

      const syncSettingsCount = () => {
        if (!countEl) return;
        const count = popover.querySelectorAll(".system-settings-item:not([hidden])").length;
        countEl.textContent = `${count}项`;
      };

      const setOpen = (open) => {
        wrap.classList.toggle("show", !!open);
        trigger.setAttribute("aria-expanded", open ? "true" : "false");
      };

      trigger.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        setOpen(!wrap.classList.contains("show"));
      });

      popover.addEventListener("click", (event) => {
        const btn = event.target && event.target.closest("button");
        if (!btn) return;
        queueMicrotask(() => setOpen(false));
      });

      document.addEventListener("click", (event) => {
        if (!wrap.contains(event.target)) setOpen(false);
      });

      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setOpen(false);
      });

      syncSettingsCount();
    }

    function openProjectAgentDirectory() {
      const base = String(AGENT_DIRECTORY_PAGE || "/share/project-agent-directory.html").trim();
      const projectId = String(STATE.project || "").trim();
      if (!base || !projectId || projectId === "overview") return;
      const params = new URLSearchParams();
      params.set("p", projectId);
      if (STATE.channel) params.set("c", String(STATE.channel));
      window.open(base + "#" + params.toString(), "_blank", "noopener,noreferrer");
    }

    function openProjectAgentCurtain() {
      const base = String(AGENT_CURTAIN_PAGE || "/share/project-agent-curtain.html").trim();
      const projectId = String(STATE.project || "").trim();
      if (!base || !projectId || projectId === "overview") return;
      const params = new URLSearchParams();
      params.set("p", projectId);
      if (STATE.channel) params.set("c", String(STATE.channel));
      if (STATE.selectedSessionId) params.set("sid", String(STATE.selectedSessionId));
      window.open(base + "#" + params.toString(), "_blank", "noopener,noreferrer");
    }

    function openSessionHealthPage() {
      const base = String(SESSION_HEALTH_PAGE || "/share/project-session-health-dashboard.html").trim();
      if (!base) return;
      const params = new URLSearchParams();
      const projectId = String(STATE.project || "").trim();
      if (projectId && projectId !== "overview") params.set("p", projectId);
      if (STATE.channel) params.set("c", String(STATE.channel));
      const target = params.toString() ? `${base}#${params.toString()}` : base;
      window.open(target, "_blank", "noopener,noreferrer");
    }

    function openStatusReportPage() {
      const base = String(STATUS_REPORT_PAGE || "/share/project-status-report.html").trim();
      if (!base) return;
      window.open(base, "_blank", "noopener,noreferrer");
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

    function normalizeProjectExecutionProfile(raw, fallback = "") {
      const text = String(raw == null ? "" : raw).trim().toLowerCase();
      if (text === "sandboxed" || text === "privileged" || text === "project_privileged_full") return text;
      return String(fallback || "").trim().toLowerCase();
    }

    function projectProfileBadgeMeta(raw) {
      const profile = normalizeProjectExecutionProfile(raw, "");
      if (profile === "project_privileged_full") {
        return {
          profile,
          text: "执行 全放开",
          tone: "is-privileged",
          title: "执行模式: project_privileged_full\n口径: 完全放开（当前用户态）",
        };
      }
      if (profile === "privileged") {
        return {
          profile,
          text: "执行 privileged",
          tone: "is-privileged",
          title: "执行模式: privileged\n口径: 真实仓执行（可发布 / 重启）",
        };
      }
      if (profile === "sandboxed") {
        return {
          profile,
          text: "执行 sandboxed",
          tone: "is-sandboxed",
          title: "执行模式: sandboxed\n口径: 受限执行（默认更安全）",
        };
      }
      return {
        profile,
        text: profile ? ("执行 " + profile) : "",
        tone: "",
        title: profile ? ("执行模式: " + profile) : "",
      };
    }

    function resolveProjectDisplayContext(projectLike) {
      const project = (projectLike && typeof projectLike === "object") ? projectLike : {};
      const execMeta = buildProjectExecutionContextMeta(
        project.project_execution_context || project.projectExecutionContext || null
      );
      const target = normalizeProjectExecutionContextRef(execMeta.target || null);
      const source = normalizeProjectExecutionContextRef(execMeta.source || null);
      const environment = normalizeEnvironmentName(firstNonEmptyText([
        target.environment,
        source.environment,
        project.environment,
        DATA && DATA.environment,
        "stable",
      ]));
      const worktreeRoot = firstNonEmptyText([target.worktree_root, source.worktree_root, project.worktree_root], "");
      const workdir = firstNonEmptyText([target.workdir, source.workdir, project.workdir, worktreeRoot], "");
      const branch = firstNonEmptyText([target.branch, source.branch, project.branch], "");
      const sourceKind = inferProjectSourceKind(project);
      const label = String(project.source_label || project.sourceLabel || "").trim();
      const profile = normalizeProjectExecutionProfile(firstNonEmptyText([
        project.execution_context && project.execution_context.profile,
        project.executionContext && project.executionContext.profile,
        project.execution_profile,
      ]));
      const profileMeta = projectProfileBadgeMeta(profile);
      const productionMainline = shouldUseStableDisplayCopy()
        && sourceKind === "real"
        && isStableEnvironment(environment)
        && (profile === "privileged" || profile === "project_privileged_full");
      const sourceText = productionMainline ? "生产主项目" : projectSourceBadgeText(sourceKind, label);
      const sourceTitleParts = [
        productionMainline ? "项目定位: 生产主项目" : ("项目来源: " + projectSourceBadgeText(sourceKind, label)),
      ];
      if (worktreeRoot) sourceTitleParts.push("project_root: " + worktreeRoot);
      if (workdir && workdir !== worktreeRoot) sourceTitleParts.push("workdir: " + workdir);
      if (branch) sourceTitleParts.push("branch: " + branch);
      return {
        productionMainline,
        environment,
        worktree_root: worktreeRoot,
        workdir,
        branch,
        sourceKind,
        sourceText,
        sourceTone: productionMainline ? "is-mainline" : (sourceKind ? ("is-" + sourceKind) : ""),
        sourceTitle: sourceTitleParts.join("\n"),
        profile,
        profileMeta,
      };
    }

    function resolveProjectLikeForEntity(entityLike) {
      const entity = (entityLike && typeof entityLike === "object") ? entityLike : {};
      const pid = String(firstNonEmptyText([
        entity.project_id,
        entity.projectId,
        entity.target && entity.target.project_id,
        entity.target && entity.target.projectId,
        entity.source && entity.source.project_id,
        entity.source && entity.source.projectId,
        STATE && STATE.project,
      ]) || "").trim();
      return pid ? projectById(pid) : null;
    }

    function shouldUseProjectMainlineDisplay(entityLike) {
      const project = resolveProjectLikeForEntity(entityLike);
      return !!(project && resolveProjectDisplayContext(project).productionMainline);
    }

    function buildProjectMainlineDetailChips(projectLike) {
      const display = resolveProjectDisplayContext(projectLike);
      if (!display.productionMainline) return [];
      const chips = [];
      chips.push(el("span", {
        class: "detail-context-chip good",
        text: "生产主项目",
        title: display.sourceTitle || "项目定位: 生产主项目",
      }));
      if (display.profileMeta && display.profileMeta.text) {
        chips.push(el("span", {
          class: "detail-context-chip info",
          text: String(display.profileMeta.text || ""),
          title: String(display.profileMeta.title || ""),
        }));
      }
      chips.push(el("span", {
        class: "detail-context-chip env stable",
        text: formatEnvironmentBadgeLabel({ environment: display.environment }),
        title: "环境: " + String(display.environment || "stable"),
      }));
      return chips;
    }

    function projectSourceBadgeTitle(projectLike, kind, label) {
      const project = (projectLike && typeof projectLike === "object") ? projectLike : {};
      const display = resolveProjectDisplayContext(project);
      const titleParts = [
        display.productionMainline
          ? "项目定位: 生产主项目"
          : ("项目来源: " + projectSourceBadgeText(kind, label)),
      ];
      const projectRoot = firstNonEmptyText([
        project.project_root_rel,
        project.projectRootRel,
        display.worktree_root,
      ], "");
      const taskRoot = String(project.task_root_rel || project.taskRootRel || "").trim();
      if (projectRoot) titleParts.push("project_root: " + projectRoot);
      if (taskRoot) titleParts.push("task_root: " + taskRoot);
      if (display.branch) titleParts.push("branch: " + display.branch);
      return titleParts.join("\n");
    }

    function fallbackProjectName(projectLike) {
      const project = (projectLike && typeof projectLike === "object") ? projectLike : {};
      return String(firstNonEmptyText([
        project.name,
        project.project_name,
        project.projectName,
        project.id,
        project.project_id,
      ]) || "").trim();
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
      const raw = fallbackProjectName(projectLike);
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

    function ensureProjectSourceBadge(projectLike) {
      const row = document.querySelector(".project-meta-row");
      if (!row) return;
      let badge = document.getElementById("projectSourceBadge");
      if (!badge) {
        badge = el("span", { class: "source-chip", id: "projectSourceBadge" });
        const envBadge = document.getElementById("envBadge");
        if (envBadge && envBadge.parentNode === row) row.insertBefore(badge, envBadge);
        else row.appendChild(badge);
      }
      badge.hidden = true;
      badge.textContent = "";
      badge.className = "source-chip";
      badge.removeAttribute("title");
    }

    function ensureProjectModeBadge(projectLike) {
      const row = document.querySelector(".project-meta-row");
      if (!row) return;
      let badge = document.getElementById("projectModeBadge");
      if (!badge) {
        badge = el("span", { class: "project-mode-chip", id: "projectModeBadge" });
        const envBadge = document.getElementById("envBadge");
        if (envBadge && envBadge.parentNode === row) row.insertBefore(badge, envBadge);
        else row.appendChild(badge);
      }
      badge.hidden = true;
      badge.textContent = "";
      badge.className = "project-mode-chip";
      badge.removeAttribute("title");
    }

    function updateProjectInfo() {
      const titleEl = document.getElementById("projectTitle");
      const descEl = document.getElementById("projectDesc");
      const p = projectById(STATE.project);
      const name = displayProjectName(p) || "未知项目";
      if (titleEl) titleEl.textContent = name;
      if (descEl) {
        descEl.textContent = "";
        descEl.hidden = true;
      }
      ensureProjectSourceBadge(p);
      ensureProjectModeBadge(p);
      try { document.title = name + " · Qoreon"; } catch (_) {}
    }

    function shortContextPath(raw) {
      const full = String(raw || "").trim();
      if (!full) return "";
      const normalized = full.replace(/\\/g, "/").replace(/\/+$/, "");
      const parts = normalized.split("/").filter(Boolean);
      return parts.length ? parts[parts.length - 1] : normalized;
    }

    function buildSessionContextSummary(sessionLike) {
      const info = (sessionLike && typeof sessionLike === "object") ? sessionLike : {};
      const environment = normalizeSessionEnvironmentValue(info.environment || "stable");
      const worktreeRoot = firstNonEmptyText([info.worktree_root, info.worktreeRoot], "");
      const workdir = firstNonEmptyText([info.workdir], "");
      const branch = firstNonEmptyText([info.branch], "");
      const summaryParts = [formatEnvironmentBadgeLabel({ environment })];
      const titleParts = ["环境: " + environment];
      if (worktreeRoot) {
        summaryParts.push("worktree: " + shortContextPath(worktreeRoot));
        titleParts.push("worktree: " + worktreeRoot);
      }
      if (branch) {
        summaryParts.push("branch: " + branch);
        titleParts.push("branch: " + branch);
      }
      if (workdir && workdir !== worktreeRoot) {
        summaryParts.push("cwd: " + shortContextPath(workdir));
        titleParts.push("workdir: " + workdir);
      }
      return {
        text: summaryParts.join(" · "),
        title: titleParts.join("\n"),
        missing: !(worktreeRoot && branch),
      };
    }

    function resolveSessionContextFields(source, fallback = null) {
      const src = (source && typeof source === "object") ? source : {};
      const fb = (fallback && typeof fallback === "object") ? fallback : null;
      const bySessionId = src.sessionId ? findConversationSessionById(src.sessionId) : null;
      const byChannel = (!bySessionId && src.projectId && src.channelName)
        ? sessionForChannel(String(src.projectId || ""), String(src.channelName || ""))
        : null;
      const normalized = normalizeConversationSessionDetail(src, bySessionId || byChannel || fb || null);
      const environment = normalizeSessionEnvironmentValue(normalized.environment || "stable");
      const worktreeRoot = String(normalized.worktree_root || "").trim();
      const workdir = String(normalized.workdir || "").trim();
      const branch = String(normalized.branch || "").trim();
      return {
        environment,
        worktree_root: worktreeRoot,
        workdir,
        branch,
        missingBinding: !(worktreeRoot && branch),
      };
    }

    function normalizeProjectExecutionContextRef(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return {
        project_id: firstNonEmptyText([src.project_id, src.projectId]),
        channel_name: firstNonEmptyText([src.channel_name, src.channelName]),
        session_id: firstNonEmptyText([src.session_id, src.sessionId]),
        run_id: firstNonEmptyText([src.run_id, src.runId]),
        environment: firstNonEmptyText([src.environment]),
        worktree_root: firstNonEmptyText([src.worktree_root, src.worktreeRoot]),
        workdir: firstNonEmptyText([src.workdir]),
        branch: firstNonEmptyText([src.branch]),
      };
    }

    function normalizeProjectExecutionContext(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const override = (src.override && typeof src.override === "object") ? src.override : {};
      const fields = Array.isArray(override.fields)
        ? override.fields.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      const target = normalizeProjectExecutionContextRef(src.target || src.target_ref || null);
      const source = normalizeProjectExecutionContextRef(src.source || src.source_ref || null);
      const contextSource = String(firstNonEmptyText([src.context_source, src.contextSource]) || "").trim().toLowerCase();
      const overrideSource = String(firstNonEmptyText([override.source, src.override_source, src.overrideSource]) || "").trim().toLowerCase();
      const available = !!(
        contextSource
        || fields.length
        || Object.values(target).some(Boolean)
        || Object.values(source).some(Boolean)
      );
      return {
        available,
        target,
        source,
        context_source: contextSource,
        override: {
          applied: boolLike(override.applied) || fields.length > 0,
          fields,
          source: overrideSource,
        },
      };
    }

    function executionContextSourceMeta(raw) {
      const key = String(raw || "").trim().toLowerCase();
      if (key === "project") return { key, text: "项目继承", tone: "good" };
      if (key === "server_default") return { key, text: "服务默认", tone: "warn" };
      if (key === "server_runtime") return { key, text: "当前服务", tone: "info" };
      if (key === "session") return { key, text: "会话绑定", tone: "info" };
      if (key === "override") return { key, text: "显式覆盖", tone: "warn" };
      return { key, text: key ? ("来源:" + key) : "来源待返回", tone: key ? "muted" : "muted" };
    }

    function executionContextOverrideSourceMeta(raw) {
      const key = String(raw || "").trim().toLowerCase();
      if (key === "session") return { key, text: "来自会话配置", tone: "info" };
      if (key === "request") return { key, text: "来自请求透传", tone: "warn" };
      if (key === "run") return { key, text: "来自运行态落盘", tone: "info" };
      return { key, text: key ? ("覆盖来源:" + key) : "覆盖来源待返回", tone: key ? "muted" : "muted" };
    }

    function executionContextFieldLabel(key) {
      const txt = String(key || "").trim();
      if (txt === "environment") return "环境";
      if (txt === "worktree_root") return "worktree";
      if (txt === "workdir") return "cwd";
      if (txt === "branch") return "branch";
      return txt || "-";
    }

    function summarizeExecutionContextFields(fields) {
      const list = Array.isArray(fields) ? fields : [];
      return list.map((item) => executionContextFieldLabel(item)).filter(Boolean).join(" / ");
    }

    function buildProjectExecutionContextMeta(raw) {
      const normalized = normalizeProjectExecutionContext(raw);
      const sourceMeta = executionContextSourceMeta(normalized.context_source);
      const overrideApplied = !!(normalized.override && normalized.override.applied);
      const overrideFieldsText = summarizeExecutionContextFields(normalized.override && normalized.override.fields);
      const overrideSourceMeta = executionContextOverrideSourceMeta(normalized.override && normalized.override.source);
      return {
        ...normalized,
        sourceMeta,
        overrideApplied,
        overrideFieldsText,
        overrideSourceMeta,
      };
    }

    function buildProjectExecutionContextCompactChip(raw, opts = {}) {
      const meta = buildProjectExecutionContextMeta(raw);
      const project = resolveProjectLikeForEntity(meta);
      const projectDisplay = project ? resolveProjectDisplayContext(project) : null;
      if (!meta.available && !(opts && opts.showMissing)) return null;
      if (projectDisplay && projectDisplay.productionMainline && meta.available && !meta.overrideApplied && meta.sourceMeta.key === "project") {
        return null;
      }
      const compactTone = (
        projectDisplay
        && projectDisplay.productionMainline
        && meta.overrideApplied
      )
        ? "warn"
        : String((meta.sourceMeta && meta.sourceMeta.tone) || "muted");
      const label = meta.available
        ? (
            projectDisplay && projectDisplay.productionMainline && meta.overrideApplied
              ? "会话覆写"
              : ("上下文·" + String(meta.sourceMeta.text || "来源待返回"))
          )
        : "上下文待返回";
      return el("span", {
        class: "conv-subchip exec-source" + (compactTone ? (" " + compactTone) : ""),
        text: label,
        title: meta.available
          ? [
              "上下文来源: " + String(meta.sourceMeta.text || "-"),
              meta.overrideApplied && meta.overrideFieldsText ? ("已覆写: " + meta.overrideFieldsText) : "",
              meta.overrideApplied ? ("覆盖来源: " + String(meta.overrideSourceMeta.text || "-")) : "",
            ].filter(Boolean).join("\n")
          : "接口暂未返回 project_execution_context",
      });
    }

    function buildProjectExecutionContextDetailRows(raw, opts = {}) {
      const meta = buildProjectExecutionContextMeta(raw);
      const showMissing = !!(opts && opts.showMissing);
      if (!meta.available && !showMissing) return [];
      const rows = [];
      const summaryRow = el("div", { class: "detail-context-row execution" });
      summaryRow.appendChild(el("span", {
        class: "detail-context-chip exec-source " + String((meta.sourceMeta && meta.sourceMeta.tone) || "muted"),
        text: "来源: " + String((meta.sourceMeta && meta.sourceMeta.text) || "待返回"),
      }));
      if (meta.overrideApplied && meta.overrideFieldsText) {
        summaryRow.appendChild(el("span", {
          class: "detail-context-chip exec-override warn",
          text: "已覆写: " + meta.overrideFieldsText,
        }));
        summaryRow.appendChild(el("span", {
          class: "detail-context-chip exec-override-source " + String((meta.overrideSourceMeta && meta.overrideSourceMeta.tone) || "muted"),
          text: "覆盖来源: " + String((meta.overrideSourceMeta && meta.overrideSourceMeta.text) || "待返回"),
        }));
      }
      if (!meta.available) {
        summaryRow.appendChild(el("span", {
          class: "detail-context-chip muted",
          text: "project_execution_context 待服务返回",
        }));
      }
      rows.push(summaryRow);
      return rows;
    }

    function normalizeConversationBindingState(raw) {
      const key = String(raw || "").trim().toLowerCase();
      if (!key) return "";
      if (key === "unbound" || key === "defaulted" || key === "missing") return "unbound";
      if (key === "override") return "override";
      if (key === "drift") return "drift";
      if (key === "bound" || key === "project" || key === "session") return "bound";
      return key;
    }

    function resolveConversationContextStatus(sessionLike) {
      const session = (sessionLike && typeof sessionLike === "object") ? sessionLike : {};
      const info = resolveSessionContextFields(session);
      const execMeta = buildProjectExecutionContextMeta(
        session.project_execution_context || session.projectExecutionContext || null
      );
      const bindingState = normalizeConversationBindingState(
        firstNonEmptyText([session.context_binding_state, session.contextBindingState], "")
      );
      const effectiveWorktree = firstNonEmptyText([
        execMeta.target && execMeta.target.worktree_root,
        info.worktree_root,
        execMeta.source && execMeta.source.worktree_root,
      ], "");
      const effectiveWorkdir = firstNonEmptyText([
        execMeta.target && execMeta.target.workdir,
        info.workdir,
        execMeta.source && execMeta.source.workdir,
        effectiveWorktree,
      ], "");
      const effectiveBranch = firstNonEmptyText([
        execMeta.target && execMeta.target.branch,
        info.branch,
        execMeta.source && execMeta.source.branch,
      ], "");
      const effectiveEnvironment = normalizeEnvironmentName(firstNonEmptyText([
        execMeta.target && execMeta.target.environment,
        info.environment,
        execMeta.source && execMeta.source.environment,
        "stable",
      ]));
      const missingBinding = !(effectiveWorktree && effectiveBranch);
      const hasWorkdirDrift = !!(
        effectiveWorktree &&
        effectiveWorkdir &&
        effectiveWorkdir !== effectiveWorktree
      );
      const stateKind = (() => {
        if (missingBinding || bindingState === "unbound") return "unbound";
        if (bindingState === "override" || execMeta.overrideApplied) return "override";
        if (bindingState === "drift" || hasWorkdirDrift) return "drift";
        return "bound";
      })();
      const stateLabel = stateKind === "bound"
        ? "已绑定"
        : (stateKind === "override" ? "特例覆盖" : (stateKind === "drift" ? "上下文漂移" : "未完全绑定"));
      const titleParts = [
        "状态: " + stateLabel,
        "环境: " + effectiveEnvironment,
      ];
      if (effectiveWorktree) titleParts.push("项目工作树: " + effectiveWorktree);
      if (effectiveWorkdir) titleParts.push("实际工作目录: " + effectiveWorkdir);
      if (effectiveBranch) titleParts.push("分支: " + effectiveBranch);
      if (execMeta.sourceMeta && execMeta.sourceMeta.text) {
        titleParts.push("上下文来源: " + String(execMeta.sourceMeta.text || "-"));
      }
      if (execMeta.overrideApplied && execMeta.overrideFieldsText) {
        titleParts.push("已覆写: " + execMeta.overrideFieldsText);
      }
      return {
        kind: stateKind,
        label: stateLabel,
        title: titleParts.join("\n"),
      };
    }

    function buildConversationContextStatusBadge(sessionLike, opts = {}) {
      const status = resolveConversationContextStatus(sessionLike);
      if (shouldUseProjectMainlineDisplay(sessionLike) && status.kind === "bound") return null;
      const compact = !!(opts && opts.compact);
      return el("span", {
        class: "conv-context-badge"
          + " is-" + String(status.kind || "bound")
          + (compact ? " compact" : ""),
        text: status.label,
        title: status.title,
      });
    }

    function buildExecutionContextRefSummary(ref) {
      const row = normalizeProjectExecutionContextRef(ref);
      const parts = [];
      if (row.project_id) parts.push("项目: " + row.project_id);
      if (row.channel_name) parts.push("通道: " + row.channel_name);
      if (row.session_id) parts.push("会话: " + row.session_id);
      if (row.run_id) parts.push("Run: " + row.run_id);
      if (row.environment) parts.push("环境: " + row.environment);
      if (row.worktree_root) parts.push("worktree: " + row.worktree_root);
      if (row.workdir) parts.push("cwd: " + row.workdir);
      if (row.branch) parts.push("branch: " + row.branch);
      return parts;
    }

    function buildConversationEnvironmentBadge(sessionLike, opts = {}) {
      const info = resolveSessionContextFields(sessionLike);
      const status = resolveConversationContextStatus(sessionLike);
      if (shouldUseProjectMainlineDisplay(sessionLike) && status.kind === "bound") return null;
      const env = normalizeEnvironmentName(info.environment || "stable");
      const compact = !!(opts && opts.compact);
      const badge = el("span", {
        class: "conv-env-badge"
          + (isStableEnvironment(env) ? " env-stable" : " env-verify")
          + (info.missingBinding ? " env-missing" : "")
          + (compact ? " compact" : ""),
        text: env,
      });
      const titleParts = ["环境: " + env];
      if (info.worktree_root) titleParts.push("worktree: " + info.worktree_root);
      if (info.workdir) titleParts.push("workdir: " + info.workdir);
      if (info.branch) titleParts.push("branch: " + info.branch);
      if (info.missingBinding) titleParts.push("工作上下文未完全绑定");
      badge.title = titleParts.join("\n");
      return badge;
    }

    function renderConversationContextLine(container, sessionLike) {
      if (!container) return;
      const project = resolveProjectLikeForEntity(sessionLike);
      const projectDisplay = project ? resolveProjectDisplayContext(project) : null;
      const info = resolveSessionContextFields(sessionLike);
      const status = resolveConversationContextStatus(sessionLike);
      const execMeta = buildProjectExecutionContextMeta(
        sessionLike && typeof sessionLike === "object"
          ? (sessionLike.project_execution_context || sessionLike.projectExecutionContext || null)
          : null
      );
      if (projectDisplay && projectDisplay.productionMainline) {
        const row = el("div", { class: "detail-context-row" });
        row.appendChild(el("span", {
          class: "detail-context-chip env" + (isStableEnvironment(projectDisplay.environment) ? " stable" : " verify"),
          text: String(projectDisplay.environment || "stable"),
        }));
        if (status.kind !== "bound") {
          row.appendChild(el("span", {
            class: "detail-context-chip warn",
            text: status.label,
            title: status.title,
          }));
          if (execMeta.overrideApplied && execMeta.overrideFieldsText) {
            row.appendChild(el("span", {
              class: "detail-context-chip warn",
              text: "会话覆写: " + execMeta.overrideFieldsText,
              title: [
                "会话覆写: " + execMeta.overrideFieldsText,
                execMeta.overrideSourceMeta && execMeta.overrideSourceMeta.text
                  ? ("覆盖来源: " + String(execMeta.overrideSourceMeta.text || "-"))
                  : "",
              ].filter(Boolean).join("\n"),
            }));
          }
        }
        container.innerHTML = "";
        container.appendChild(row);
        const titleParts = [
          projectDisplay.sourceTitle || "项目定位: 生产主项目",
          projectDisplay.profileMeta && projectDisplay.profileMeta.title ? projectDisplay.profileMeta.title : "",
          "环境: " + String(projectDisplay.environment || "stable"),
        ];
        if (projectDisplay.worktree_root) titleParts.push("worktree: " + projectDisplay.worktree_root);
        if (projectDisplay.workdir && projectDisplay.workdir !== projectDisplay.worktree_root) {
          titleParts.push("workdir: " + projectDisplay.workdir);
        }
        if (projectDisplay.branch) titleParts.push("branch: " + projectDisplay.branch);
        if (status.kind !== "bound") titleParts.push(status.title);
        container.title = titleParts.filter(Boolean).join("\n");
        return;
      }
      const row = el("div", { class: "detail-context-row" });
      row.appendChild(el("span", {
        class: "detail-context-chip env" + (isStableEnvironment(info.environment) ? " stable" : " verify"),
        text: String(info.environment || "stable"),
      }));
      if (info.missingBinding) {
        row.appendChild(el("span", {
          class: "detail-context-chip warn",
          text: "未完全绑定",
          title: "缺少 worktree_root 或 branch，发送时会显式透传已知上下文。",
        }));
      }
      container.innerHTML = "";
      container.appendChild(row);
      const titleParts = ["环境: " + String(info.environment || "stable")];
      if (info.worktree_root) titleParts.push("worktree: " + info.worktree_root);
      if (info.workdir) titleParts.push("workdir: " + info.workdir);
      if (info.branch) titleParts.push("branch: " + info.branch);
      if (info.missingBinding) titleParts.push("未完全绑定");
      container.title = titleParts.join("\n");
    }

    function normalizeSessionEnvironmentValue(raw, fallback = "stable") {
      if (raw && typeof raw === "object") {
        return normalizeEnvironmentName(firstNonEmptyText([
          raw.id,
          raw.environment,
          raw.name,
          raw.label,
          raw.value,
          fallback,
        ]));
      }
      return normalizeEnvironmentName(firstNonEmptyText([raw, fallback]));
    }

    function applyEnvironmentBadge(info) {
      const badge = document.getElementById("envBadge");
      if (!badge) return;
      badge.hidden = true;
      badge.textContent = "";
      badge.removeAttribute("title");
      badge.classList.remove("is-stable", "is-verify");
    }

    async function fetchHealthInfo() {
      try {
        const r = await fetch("/__health", { cache: "no-store" });
        if (!r.ok) return null;
        return await r.json();
      } catch (_) {
        return null;
      }
    }

    async function initEnvironmentBadge() {
      const info = await fetchHealthInfo();
      applyEnvironmentBadge(info);
    }

    function uniqueSessionContextOptions(rows) {
      const out = [];
      const seen = new Set();
      (Array.isArray(rows) ? rows : []).forEach((row) => {
        if (!row) return;
        const src = typeof row === "string" ? { value: row } : row;
        const value = String((src && src.value) || "").trim();
        if (!value || seen.has(value)) return;
        seen.add(value);
        out.push({
          value,
          label: String((src && (src.label || src.value)) || value).trim() || value,
          display: String((src && (src.display || src.value || src.label)) || value).trim() || value,
          title: String((src && (src.title || src.meta || src.label || src.value)) || value).trim() || value,
          meta: String((src && src.meta) || "").trim(),
        });
      });
      return out;
    }

    function firstSessionContextOptionValue(rows, fallback = "") {
      const options = Array.isArray(rows) ? rows : [];
      return String((options[0] && options[0].value) || fallback || "").trim();
    }

    function getSessionContextRowDisplayName(row) {
      const candidate = firstNonEmptyText([
        row.alias,
        row.display_name,
        row.channel_name,
      ], "");
      if (candidate) return candidate;
      const sid = String(row.sessionId || "").trim();
      return sid ? shortId(sid) : "系统已知会话";
    }

    function getSessionContextRowMeta(row, base, kindLabel) {
      const currentId = String((base && (base.sessionId || base.id)) || "").trim();
      const rowId = String((row && row.sessionId) || "").trim();
      if (rowId && currentId && rowId === currentId) return "当前会话已绑定的" + kindLabel;
      return "来自会话 " + getSessionContextRowDisplayName(row || {}) + " 的" + kindLabel;
    }

    function buildSessionEnvironmentPresetOptions(base) {
      const normalizedBase = (base && typeof base === "object") ? base : {};
      const rows = [];
      const baseEnv = String(normalizedBase.environment || "").trim();
      if (baseEnv) {
        const env = normalizeSessionEnvironmentValue(baseEnv);
        rows.push({
          value: env,
          display: env,
          label: env,
          meta: "当前会话已绑定的环境",
        });
      }
      collectKnownSessionContextRows().forEach((row) => {
        const env = String(row.environment || "").trim();
        if (!env) return;
        rows.push({
          value: env,
          display: env,
          label: env,
          meta: getSessionContextRowMeta(row, normalizedBase, "环境"),
        });
      });
      return uniqueSessionContextOptions(rows);
    }

    function collectKnownSessionContextRows() {
      const rows = [];
      const sessions = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
      sessions.forEach((raw) => {
        const session = normalizeConversationSession(raw);
        if (!session) return;
        rows.push({
          sessionId: String(session.sessionId || "").trim(),
          environment: normalizeSessionEnvironmentValue(session.environment || "stable"),
          worktree_root: String(session.worktree_root || "").trim(),
          branch: String(session.branch || "").trim(),
          alias: String(session.alias || "").trim(),
          display_name: String(session.display_name || session.displayName || "").trim(),
          channel_name: String(session.channel_name || session.primaryChannel || "").trim(),
        });
      });
      return rows;
    }

    function buildSessionWorktreePresetOptions(base, form) {
      const normalizedBase = (base && typeof base === "object") ? base : {};
      const normalizedForm = (form && typeof form === "object") ? form : {};
      const env = normalizeSessionEnvironmentValue(normalizedForm.environment || normalizedBase.environment || "stable");
      const rows = [];
      collectKnownSessionContextRows().forEach((row) => {
        const root = String(row.worktree_root || "").trim();
        if (!root || normalizeSessionEnvironmentValue(row.environment || "stable") !== env) return;
        rows.push({
          value: root,
          display: root,
          label: root,
          meta: getSessionContextRowMeta(row, normalizedBase, "worktree 根目录"),
        });
      });
      const baseRoot = String(normalizedBase.worktree_root || "").trim();
      if (baseRoot) {
        rows.unshift({
          value: baseRoot,
          display: baseRoot,
          label: baseRoot,
          meta: "当前会话已绑定的 worktree 根目录",
        });
      }
      return uniqueSessionContextOptions(rows);
    }

    function buildSessionBranchPresetOptions(base, form) {
      const normalizedBase = (base && typeof base === "object") ? base : {};
      const normalizedForm = (form && typeof form === "object") ? form : {};
      const worktreeRoot = String(normalizedForm.worktree_root || normalizedBase.worktree_root || "").trim();
      const rows = [];
      const baseBranch = String(normalizedBase.branch || "").trim();
      if (baseBranch) {
        rows.push({
          value: baseBranch,
          display: baseBranch,
          label: baseBranch,
          meta: "当前会话已绑定的分支",
        });
      }
      collectKnownSessionContextRows().forEach((row) => {
        const branch = String(row.branch || "").trim();
        const root = String(row.worktree_root || "").trim();
        if (!branch || !root || root !== worktreeRoot) return;
        rows.push({
          value: branch,
          display: branch,
          label: branch,
          meta: getSessionContextRowMeta(row, normalizedBase, "分支"),
        });
      });
      return uniqueSessionContextOptions(rows);
    }

    function buildSessionPresetField(labelText, fieldKey, options, currentValue, config = {}) {
      const wrap = el("div", { class: "conv-session-field" });
      wrap.appendChild(el("label", { text: labelText }));
      const holder = el("div", { class: "conv-session-preset-wrap" });
      const select = el("select", { class: "input", "aria-label": labelText });
      const rows = Array.isArray(options) ? options : [];
      rows.forEach((opt) => {
        const option = el("option", {
          value: String(opt.value || ""),
          text: String(opt.display || opt.label || opt.value || ""),
        });
        if (opt.title) option.title = String(opt.title || "");
        select.appendChild(option);
      });
      select.appendChild(el("option", { value: "__custom__", text: "自定义…" }));
      const current = String(currentValue || "").trim();
      const hasPreset = rows.some((opt) => String(opt.value || "") === current);
      const customState = SESSION_INFO_UI.contextCustom || (SESSION_INFO_UI.contextCustom = Object.create(null));
      const customActive = !!customState[fieldKey] || (!hasPreset && !!current) || !rows.length;
      select.value = customActive ? "__custom__" : (current || (rows[0] && rows[0].value) || "__custom__");
      holder.appendChild(select);

      const selectedMeta = findSessionContextOption(rows, current);
      const summary = el("div", {
        class: "conv-session-preset-summary",
        text: customActive
          ? String(config.customMeta || "当前使用自定义值。")
          : String((selectedMeta && selectedMeta.meta) || (config.hint || "")),
      });
      holder.appendChild(summary);

      const customInput = el("input", {
        class: "input",
        value: current,
        placeholder: String(config.placeholder || ""),
      });
      customInput.style.display = customActive ? "" : "none";
      holder.appendChild(customInput);

      const updateSummary = () => {
        const latestValue = String(customInput.value || "").trim();
        const activePreset = findSessionContextOption(rows, latestValue);
        summary.textContent = (select.value === "__custom__")
          ? String(config.customMeta || "当前使用自定义值。")
          : String((activePreset && activePreset.meta) || (config.hint || ""));
      };
      select.addEventListener("change", () => {
        const nextCustom = select.value === "__custom__";
        customState[fieldKey] = nextCustom;
        customInput.style.display = nextCustom ? "" : "none";
        if (nextCustom) {
          if (!String(customInput.value || "").trim() && rows.length) {
            customInput.value = String((rows[0] && rows[0].value) || "");
          }
          if (typeof config.onCustomInput === "function") config.onCustomInput(customInput.value);
        } else {
          customInput.value = String(select.value || "");
          if (typeof config.onPresetSelect === "function") config.onPresetSelect(select.value);
        }
        updateSummary();
        renderConversationSessionInfoModal();
      });
      customInput.addEventListener("input", () => {
        if (typeof config.onCustomInput === "function") config.onCustomInput(customInput.value);
        updateSummary();
      });

      wrap.appendChild(holder);
      if (config.hint) wrap.appendChild(el("div", { class: "conv-session-field-hint", text: String(config.hint) }));
      return wrap;
    }

    function findSessionContextOption(rows, currentValue) {
      const needle = String(currentValue || "").trim();
      return (Array.isArray(rows) ? rows : []).find((opt) => String((opt && opt.value) || "").trim() === needle) || null;
    }

    function setMessageInputHeight(textarea) {
      if (!textarea) return;
      // 重置高度以获取正确的 scrollHeight
      textarea.style.height = "40px";
      const scrollHeight = textarea.scrollHeight;
      const maxHeight = 120; // 约6行

      if (scrollHeight > maxHeight) {
        textarea.style.height = maxHeight + "px";
        textarea.classList.add("scroll");
      } else {
        textarea.style.height = scrollHeight + "px";
        textarea.classList.remove("scroll");
      }
    }

    function resetMessageInputHeight(textarea) {
      if (!textarea) return;
      textarea.style.height = "40px";
      textarea.classList.remove("scroll");
    }

    // 消息输入组件 - 自动撑高
    function initMessageInput(textarea) {
      if (!textarea) return;

      const adjustHeight = () => setMessageInputHeight(textarea);
      // 给外部逻辑复用（发送后立即回落）
      textarea.__adjustHeight = adjustHeight;

      // 监听输入事件
      textarea.addEventListener("input", adjustHeight);

      // 粘贴后调整高度
      textarea.addEventListener("paste", () => setTimeout(adjustHeight, 0));

      // 初始化高度
      adjustHeight();
    }

    // 初始化所有消息输入组件
    function initAllMessageInputs() {
      const ccbMsg = document.getElementById('ccbMsg');
      const convMsg = document.getElementById('convMsg');
      if (ccbMsg) initMessageInput(ccbMsg);
      if (convMsg) initMessageInput(convMsg);
    }

    // 移动端视图状态管理
    const MOBILE_VIEW = { current: "list" }; // "list" | "detail"

    function isMobileViewport() {
      try { return window.matchMedia("(max-width: 760px)").matches; } catch (_) {}
      return Number(window.innerWidth || 0) <= 760;
    }

    // 当前布局已改为移动端下拉通道选择器，无抽屉；保留该函数以兼容历史调用点。
    function closeDrawerOnMobile() {}

    function showListView() {
      MOBILE_VIEW.current = "list";
      const listView = document.getElementById("listView");
      const detailView = document.getElementById("detailView");
      if (listView) listView.classList.remove("hidden");
      if (detailView) detailView.classList.remove("show");
    }

    function showDetailView() {
      MOBILE_VIEW.current = "detail";
      const listView = document.getElementById("listView");
      const detailView = document.getElementById("detailView");
      if (listView) listView.classList.add("hidden");
      if (detailView) detailView.classList.add("show");
    }

    function enforceMobileTaskOnlyMode() {
      // 旧逻辑曾在移动端强制禁用“对话”模式。
      // 现在移动端已经具备对话列表/详情双态能力，这里保留兼容调用点但不再改写 panelMode。
    }

    function initMobileViewSwitch() {
      const backBtn = document.getElementById("backToList");
      if (backBtn) {
        backBtn.addEventListener("click", () => {
          if (typeof isTaskSingleCanvasMode === "function" && isTaskSingleCanvasMode()) {
            if (typeof closeTaskCanvasDetail === "function") closeTaskCanvasDetail();
            showListView();
            return;
          }
          showListView();
          // 清除选中状态
          STATE.selectedPath = "";
          STATE.selectedTaskId = "";
          STATE.selectedSessionId = "";
          STATE.selectedSessionExplicit = false;
          syncSelectedTaskSelectionStorage();
          updateSelectionUI();
          // 对话模式下需要重新渲染列表
          if (STATE.panelMode === "conv") {
            buildConversationMainList(document.getElementById("fileList"));
          }
          renderDetail(null);
        });
      }
    }

    // 通道选择器
    function initChannelSelector() {
      const selector = document.getElementById("channelSelector");
      const btn = document.getElementById("channelSelectorBtn");
      const dropdown = document.getElementById("channelDropdown");

      if (!selector || !btn || !dropdown) return;

      // 点击按钮切换下拉
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        selector.classList.toggle("show");
      });

      // 点击外部关闭
      document.addEventListener("click", (e) => {
        if (!selector.contains(e.target)) {
          selector.classList.remove("show");
        }
      });

      // 渲染通道列表
      renderChannelSelectorList();
    }

    function renderChannelSelectorList() {
      const list = document.getElementById("channelList");
      const nameEl = document.getElementById("channelName");
      if (!list) return;

      const names = unionChannelNames(STATE.project);
      if (!names.length) {
        list.innerHTML = '<div class="channel-item" style="color:var(--muted);">无通道</div>';
        if (nameEl) nameEl.textContent = "选择通道";
        return;
      }

      list.innerHTML = "";
      for (const chName of names) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "channel-item" + (STATE.channel === chName ? " active" : "");
        item.textContent = chName;
        item.addEventListener("click", async () => {
          STATE.channel = chName;
          STATE.selectedPath = "";
          STATE.selectedTaskId = "";
          STATE.selectedSessionId = "";  // 切换通道时清除对话选中状态
          STATE.selectedSessionExplicit = false;
          syncSelectedTaskSelectionStorage();
          if (nameEl) nameEl.textContent = chName;
          document.getElementById("channelSelector").classList.remove("show");
          // 在对话模式下，切换通道后加载该通道的会话列表
          if (STATE.panelMode === "conv") {
            await loadChannelSessions(STATE.project, chName);
            // 如果有会话，自动选中第一个
            if (PCONV.sessions.length > 0) {
              const channelSessions = PCONV.sessions.filter((s) => sessionMatchesChannel(s, chName));
              if (channelSessions.length > 0) {
                STATE.selectedSessionId = pickDefaultConversationSessionId(channelSessions, chName);
                STATE.selectedSessionExplicit = false;
              }
            }
          }
          render();
        });
        list.appendChild(item);
      }

      // 更新当前显示
      if (nameEl) {
        nameEl.textContent = STATE.channel || "选择通道";
      }
    }

    function updateChannelSelectorName() {
      const nameEl = document.getElementById("channelName");
      if (nameEl) {
        nameEl.textContent = STATE.channel || "选择通道";
      }
    }

    function updateCurrentChannelName() {
      const el = document.getElementById("currentChannelName");
      if (el) {
        el.textContent = STATE.channel || "-";
      }
    }

    const DONE_STATUSES = new Set(["已完成", "已验收通过", "已消费", "已解决", "已关闭", "已停止", "已合并", "完成", "已归档"]);
    const PAUSE_STATUSES = new Set(["已暂停", "暂缓"]);
    const STATUS_ORDER = ["督办", "进行中", "待开始", "待处理", "待验收", "待消费", "其他", "已暂停", "已完成"];
    const PRIMARY_TASK_STATUSES = ["待办", "进行中", "待验收", "已完成", "暂缓"];
    function loadSessionScopedMap(storageKey) {
      try {
        const raw = localStorage.getItem(String(storageKey || ""));
        if (!raw) return Object.create(null);
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return Object.create(null);
        return Object.assign(Object.create(null), parsed);
      } catch (_) {}
      return Object.create(null);
    }

    function loadTaskCompletedViewedMap() {
      try {
        const raw = localStorage.getItem(TASK_COMPLETED_VIEWED_KEY);
        if (!raw) return Object.create(null);
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return Object.create(null);
        const out = Object.create(null);
        Object.keys(parsed).forEach((pid) => {
          const row = parsed[pid];
          if (!row || typeof row !== "object") return;
          const next = Object.create(null);
          Object.keys(row).forEach((taskPath) => {
            const key = normalizeScheduleTaskPathForProject(pid, taskPath);
            if (!key) return;
            next[key] = Number(row[taskPath] || Date.now()) || Date.now();
          });
          out[String(pid || "")] = next;
        });
        return out;
      } catch (_) {}
      return Object.create(null);
    }

    const TASK_COMPLETED_VIEWED = loadTaskCompletedViewedMap();

    function persistTaskCompletedViewedMap() {
      try {
        localStorage.setItem(TASK_COMPLETED_VIEWED_KEY, JSON.stringify(TASK_COMPLETED_VIEWED));
      } catch (_) {}
    }

    function isTaskCompletedStatus(statusRaw) {
      return bucketKeyForStatus(statusRaw) === "已完成";
    }

    function completedViewedMapForProject(projectId, create) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      if (!Object.prototype.hasOwnProperty.call(TASK_COMPLETED_VIEWED, pid)) {
        if (!create) return null;
        TASK_COMPLETED_VIEWED[pid] = Object.create(null);
      }
      const row = TASK_COMPLETED_VIEWED[pid];
      if (!row || typeof row !== "object") {
        if (!create) return null;
        TASK_COMPLETED_VIEWED[pid] = Object.create(null);
      }
      return TASK_COMPLETED_VIEWED[pid];
    }

    function isTaskCompletedViewed(projectId, taskPath, statusRaw) {
      const path = normalizeScheduleTaskPathForProject(projectId, taskPath);
      if (!path || !isTaskCompletedStatus(statusRaw)) return false;
      const row = completedViewedMapForProject(projectId, false);
      if (!row) return false;
      return !!row[path];
    }

    function setTaskCompletedViewed(projectId, taskPath, viewed) {
      const path = normalizeScheduleTaskPathForProject(projectId, taskPath);
      if (!path) return;
      const row = completedViewedMapForProject(projectId, true);
      if (!row) return;
      if (viewed) row[path] = Date.now();
      else delete row[path];
      persistTaskCompletedViewedMap();
    }

    function persistSessionScopedMap(storageKey, mapObj) {
      try {
        localStorage.setItem(String(storageKey || ""), JSON.stringify(mapObj || {}));
      } catch (_) {}
    }

    function genLocalId(prefix) {
      const p = String(prefix || "id").trim() || "id";
      return p + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
    }

    const ORG_RELATION_COLOR_PALETTE = [
      "#2f6fed",
      "#0f85ba",
      "#20935f",
      "#b36a00",
      "#7c3aed",
      "#c91d3b",
      "#15803d",
      "#0369a1",
      "#7f1d1d",
      "#1d4ed8",
    ];

    function nextOrgRelationColor(index) {
      const idx = Math.max(0, Number(index || 0));
      return ORG_RELATION_COLOR_PALETTE[idx % ORG_RELATION_COLOR_PALETTE.length];
    }

    function normalizeOrgRelationLineStyle(style) {
      const raw = String(style || "").trim().toLowerCase();
      if (raw === "dash" || raw === "dot") return raw;
      return "solid";
    }

    function normalizeOrgRelationLineWidth(width, fallback = 4) {
      const base = Number(width);
      if (!Number.isFinite(base)) return Math.max(2, Math.min(10, Number(fallback || 4) || 4));
      return Math.max(2, Math.min(10, base));
    }

    function normalizeOrgRelationTypes(raw) {
      const src = Array.isArray(raw) ? raw : [];
      const out = [];
      const seen = new Set();
      src.forEach((row, idx) => {
        if (!row || typeof row !== "object") return;
        const id = String(row.id || "").trim() || genLocalId("reltype");
        const name = String(row.name || "").trim();
        if (!name || seen.has(id)) return;
        seen.add(id);
        out.push({
          id,
          name,
          color: String(row.color || "").trim() || nextOrgRelationColor(idx),
          line_style: normalizeOrgRelationLineStyle(row.line_style),
          line_width: normalizeOrgRelationLineWidth(row.line_width, 4),
          enabled: row.enabled !== false,
          order: Number(row.order || idx + 1) || (idx + 1),
          updated_at: String(row.updated_at || new Date().toISOString()),
        });
      });
      out.sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
      return out;
    }

    function normalizeOrgManualRelations(raw) {
      const src = Array.isArray(raw) ? raw : [];
      const out = [];
      const seen = new Set();
      src.forEach((row) => {
        if (!row || typeof row !== "object") return;
        const id = String(row.id || "").trim() || genLocalId("rel");
        const sourceAgentId = String(row.source_agent_id || row.sourceAgentId || "").trim();
        const targetAgentId = String(row.target_agent_id || row.targetAgentId || "").trim();
        const relationTypeId = String(row.relation_type_id || row.relationTypeId || "").trim();
        if (!id || !sourceAgentId || !targetAgentId || !relationTypeId) return;
        if (sourceAgentId === targetAgentId || seen.has(id)) return;
        seen.add(id);
        out.push({
          id,
          source_agent_id: sourceAgentId,
          target_agent_id: targetAgentId,
          relation_type_id: relationTypeId,
          status: String(row.status || "enabled").trim() || "enabled",
          updated_at: String(row.updated_at || new Date().toISOString()),
        });
      });
      return out;
    }

    function loadOrgManualRelationStoreMap() {
      try {
        const raw = localStorage.getItem(ORG_MANUAL_RELATIONS_KEY);
        if (!raw) return Object.create(null);
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return Object.create(null);
        const out = Object.create(null);
        Object.keys(parsed).forEach((pidRaw) => {
          const pid = String(pidRaw || "").trim();
          if (!pid) return;
          const row = parsed[pidRaw];
          if (!row || typeof row !== "object") return;
          out[pid] = {
            types: normalizeOrgRelationTypes(row.types),
            relations: normalizeOrgManualRelations(row.relations),
            updated_at: String(row.updated_at || ""),
          };
        });
        return out;
      } catch (_) {}
      return Object.create(null);
    }

    const ORG_MANUAL_RELATION_STORE = loadOrgManualRelationStoreMap();

    function persistOrgManualRelationStoreMap() {
      try {
        localStorage.setItem(ORG_MANUAL_RELATIONS_KEY, JSON.stringify(ORG_MANUAL_RELATION_STORE));
      } catch (_) {}
    }

    function orgProjectRelationStore(projectId, create = false) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      if (!Object.prototype.hasOwnProperty.call(ORG_MANUAL_RELATION_STORE, pid)) {
        if (!create) return null;
        ORG_MANUAL_RELATION_STORE[pid] = {
          types: [],
          relations: [],
          updated_at: "",
        };
      }
      const row = ORG_MANUAL_RELATION_STORE[pid];
      if (!row || typeof row !== "object") {
        if (!create) return null;
        ORG_MANUAL_RELATION_STORE[pid] = { types: [], relations: [], updated_at: "" };
      }
      const normalized = ORG_MANUAL_RELATION_STORE[pid];
      normalized.types = normalizeOrgRelationTypes(normalized.types);
      normalized.relations = normalizeOrgManualRelations(normalized.relations);
      return normalized;
    }

    function ensureOrgRelationTypeForProject(projectId, typeName, color, opts = {}) {
      const store = orgProjectRelationStore(projectId, true);
      if (!store) return null;
      const normalizedName = String(typeName || "").trim();
      if (!normalizedName) return null;
      const nextColor = String(color || "").trim() || nextOrgRelationColor((store.types || []).length);
      const nextLineStyle = normalizeOrgRelationLineStyle(opts && opts.line_style);
      const nextLineWidth = normalizeOrgRelationLineWidth(opts && opts.line_width, 4.2);
      const hit = (store.types || []).find((it) => String(it.name || "").trim().toLowerCase() === normalizedName.toLowerCase());
      if (hit) {
        const changed = (
          String(hit.color || "") !== nextColor
          || normalizeOrgRelationLineStyle(hit.line_style) !== nextLineStyle
          || normalizeOrgRelationLineWidth(hit.line_width, 4.2) !== nextLineWidth
        );
        if (changed) {
          hit.color = nextColor;
          hit.line_style = nextLineStyle;
          hit.line_width = nextLineWidth;
          hit.updated_at = new Date().toISOString();
          store.updated_at = hit.updated_at;
          persistOrgManualRelationStoreMap();
        }
        return hit;
      }
      const created = {
        id: genLocalId("reltype"),
        name: normalizedName,
        color: nextColor,
        line_style: nextLineStyle,
        line_width: nextLineWidth,
        enabled: true,
        order: (store.types || []).length + 1,
        updated_at: new Date().toISOString(),
      };
      store.types = normalizeOrgRelationTypes([...(store.types || []), created]);
      store.updated_at = created.updated_at;
      persistOrgManualRelationStoreMap();
      return created;
    }

    function addOrgManualRelation(projectId, payload) {
      const store = orgProjectRelationStore(projectId, true);
      if (!store) throw new Error("projectId不能为空");
      const sourceAgentId = String(payload && payload.source_agent_id || "").trim();
      const targetAgentId = String(payload && payload.target_agent_id || "").trim();
      const relationTypeId = String(payload && payload.relation_type_id || "").trim();
      if (!sourceAgentId || !targetAgentId || !relationTypeId) throw new Error("关系字段不完整");
      if (sourceAgentId === targetAgentId) throw new Error("源/目标Agent不能相同");
      const now = new Date().toISOString();
      const created = {
        id: genLocalId("rel"),
        source_agent_id: sourceAgentId,
        target_agent_id: targetAgentId,
        relation_type_id: relationTypeId,
        status: "enabled",
        updated_at: now,
      };
      store.relations = normalizeOrgManualRelations([...(store.relations || []), created]);
      store.updated_at = now;
      persistOrgManualRelationStoreMap();
      return created;
    }

    function deleteOrgManualRelation(projectId, relationId) {
      const store = orgProjectRelationStore(projectId, false);
      if (!store) return false;
      const rid = String(relationId || "").trim();
      if (!rid) return false;
      const before = (store.relations || []).length;
      store.relations = normalizeOrgManualRelations((store.relations || []).filter((it) => String((it && it.id) || "") !== rid));
      const changed = (store.relations || []).length !== before;
      if (changed) {
        store.updated_at = new Date().toISOString();
        persistOrgManualRelationStoreMap();
      }
      return changed;
    }

    function readWindowFeatureFlag(flagName, defaultValue) {
      try {
        if (typeof window === "undefined") return !!defaultValue;
        if (!Object.prototype.hasOwnProperty.call(window, String(flagName || ""))) return !!defaultValue;
        return _coerceBoolClient(window[String(flagName || "")], defaultValue);
      } catch (_) {}
      return !!defaultValue;
    }

    function isUnreadMonotonicEnabled() {
      return readWindowFeatureFlag(FEATURE_UNREAD_MONOTONIC_KEY, true);
    }

    function isUnreadCrossTabSyncEnabled() {
      return readWindowFeatureFlag(FEATURE_UNREAD_CROSS_TAB_SYNC_KEY, true);
    }

    function normalizeUnreadCursorMap(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const out = Object.create(null);
      Object.keys(src).forEach((k) => {
        const key = String(k || "").trim();
        const createdAt = String(src[k] || "").trim();
        if (!key || !createdAt) return;
        out[key] = createdAt;
      });
      return out;
    }

    function normalizeMemoConsumedMap(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const out = Object.create(null);
      Object.keys(src).forEach((k) => {
        const key = String(k || "").trim();
        if (!key) return;
        const row = src[k];
        if (!row || typeof row !== "object") return;
        const consumed = Object.create(null);
        Object.keys(row).forEach((memoId) => {
          const id = String(memoId || "").trim();
          if (!id) return;
          if (_coerceBoolClient(row[memoId], false)) consumed[id] = true;
        });
        out[key] = consumed;
      });
      return out;
    }

    function equalUnreadCursorMap(a, b) {
      const mapA = normalizeUnreadCursorMap(a);
      const mapB = normalizeUnreadCursorMap(b);
      const keysA = Object.keys(mapA);
      const keysB = Object.keys(mapB);
      if (keysA.length !== keysB.length) return false;
      for (const k of keysA) {
        if (!Object.prototype.hasOwnProperty.call(mapB, k)) return false;
        if (String(mapA[k] || "") !== String(mapB[k] || "")) return false;
      }
      return true;
    }

    function equalMemoConsumedMap(a, b) {
      const mapA = normalizeMemoConsumedMap(a);
      const mapB = normalizeMemoConsumedMap(b);
      const keysA = Object.keys(mapA);
      const keysB = Object.keys(mapB);
      if (keysA.length !== keysB.length) return false;
      for (const k of keysA) {
        if (!Object.prototype.hasOwnProperty.call(mapB, k)) return false;
        const rowA = mapA[k] || {};
        const rowB = mapB[k] || {};
        const rowAKeys = Object.keys(rowA);
        const rowBKeys = Object.keys(rowB);
        if (rowAKeys.length !== rowBKeys.length) return false;
        for (const memoId of rowAKeys) {
          if (!Object.prototype.hasOwnProperty.call(rowB, memoId)) return false;
          if (!!rowA[memoId] !== !!rowB[memoId]) return false;
        }
      }
      return true;
    }

    function applyConversationStateStorageSync(storageKey, rawValue) {
      const key = String(storageKey || "").trim();
      if (!key) return false;
      let parsed = Object.create(null);
      if (typeof rawValue === "string" && rawValue.trim()) {
        try {
          parsed = JSON.parse(rawValue);
        } catch (_) {
          return false;
        }
      }
      if (key === CONV_UNREAD_CURSOR_KEY) {
        const nextMap = normalizeUnreadCursorMap(parsed);
        if (equalUnreadCursorMap(PCONV.unreadCursorBySessionKey, nextMap)) return false;
        PCONV.unreadCursorBySessionKey = nextMap;
        return true;
      }
      if (key === CONV_MEMO_CONSUMED_KEY) {
        const nextMap = normalizeMemoConsumedMap(parsed);
        if (equalMemoConsumedMap(PCONV.memoConsumedBySessionKey, nextMap)) return false;
        PCONV.memoConsumedBySessionKey = nextMap;
        return true;
      }
      return false;
    }

    function initConversationCrossTabSync() {
      window.addEventListener("storage", (ev) => {
        const key = String((ev && ev.key) || "").trim();
        if (!key) return;
        if (key !== CONV_UNREAD_CURSOR_KEY && key !== CONV_MEMO_CONSUMED_KEY) return;
        if (!isUnreadCrossTabSyncEnabled()) return;
        const changed = applyConversationStateStorageSync(key, ev && ev.newValue);
        if (!changed) return;
        refreshConversationCountDots();
        const ctx = currentConversationCtx();
        if (ctx && ctx.projectId && ctx.sessionId) {
          renderConversationMemoEntry(ctx);
        }
        if (PCONV.memoDrawerOpen) {
          renderConversationMemoDrawer();
        }
      });
    }

    async function openConversationSessionInfoModal(session, projectId = "") {
      const sid = String(getSessionId(session) || "").trim();
      if (!looksLikeSessionId(sid)) {
        alert("会话ID无效，无法打开会话信息。");
        return;
      }
      const mask = document.getElementById("convSessionInfoMask");
      if (!mask) return;
      SESSION_INFO_UI.open = true;
      SESSION_INFO_UI.loading = true;
      SESSION_INFO_UI.saving = false;
      SESSION_INFO_UI.sessionId = sid;
      SESSION_INFO_UI.projectId = String(projectId || STATE.project || "");
      SESSION_INFO_UI.base = normalizeConversationSessionDetail(session, session);
      SESSION_INFO_UI.form = {
        alias: String(SESSION_INFO_UI.base.alias || ""),
        avatar_id: getAssignedAvatarIdForSession(SESSION_INFO_UI.base),
        status: String(SESSION_INFO_UI.base.status || "active"),
        channel_name: String(SESSION_INFO_UI.base.channel_name || ""),
        environment: normalizeSessionEnvironmentValue(SESSION_INFO_UI.base.environment || "stable"),
        worktree_root: String(SESSION_INFO_UI.base.worktree_root || ""),
        workdir: String(SESSION_INFO_UI.base.workdir || ""),
        branch: String(SESSION_INFO_UI.base.branch || ""),
        cli_type: String(SESSION_INFO_UI.base.cli_type || "codex"),
        model: String(SESSION_INFO_UI.base.model || ""),
        reasoning_effort: String(SESSION_INFO_UI.base.reasoning_effort || ""),
      };
      SESSION_INFO_UI.error = "";
      SESSION_INFO_UI.heartbeatError = "";
      SESSION_INFO_UI.heartbeatNote = "";
      SESSION_INFO_UI.heartbeatMeta = null;
      SESSION_INFO_UI.heartbeatSummary = null;
      SESSION_INFO_UI.heartbeatTasks = [];
      SESSION_INFO_UI.heartbeatDraft = null;
      SESSION_INFO_UI.heartbeatTaskEditorOpen = false;
      SESSION_INFO_UI.heartbeatHistoryByTask = Object.create(null);
      SESSION_INFO_UI.heartbeatHistoryLoadingByTask = Object.create(null);
      SESSION_INFO_UI.heartbeatHistoryErrorByTask = Object.create(null);
      SESSION_INFO_UI.heartbeatHistoryTaskId = "";
      SESSION_INFO_UI.heartbeatActionByTask = Object.create(null);
      mask.classList.add("show");
      renderConversationSessionInfoModal();
      try {
        const resp = await fetch("/api/sessions/" + encodeURIComponent(sid), {
          cache: "no-store",
          headers: authHeaders(),
        });
        const payload = await resp.json().catch(() => null);
        if (!resp.ok) {
          SESSION_INFO_UI.loading = false;
          setConversationSessionInfoError(String(responseErrorDetailFromJson(payload, "读取会话信息失败（HTTP " + resp.status + "）")));
          renderConversationSessionInfoModal();
          return;
        }
        SESSION_INFO_UI.base = normalizeSessionInfoResponse(payload, SESSION_INFO_UI.base);
        SESSION_INFO_UI.form = {
          alias: String(SESSION_INFO_UI.base.alias || ""),
          avatar_id: getAssignedAvatarIdForSession(SESSION_INFO_UI.base),
          status: String(SESSION_INFO_UI.base.status || "active"),
          channel_name: String(SESSION_INFO_UI.base.channel_name || ""),
          environment: normalizeSessionEnvironmentValue(SESSION_INFO_UI.base.environment || "stable"),
          worktree_root: String(SESSION_INFO_UI.base.worktree_root || ""),
          workdir: String(SESSION_INFO_UI.base.workdir || ""),
          branch: String(SESSION_INFO_UI.base.branch || ""),
          cli_type: String(SESSION_INFO_UI.base.cli_type || "codex"),
          model: String(SESSION_INFO_UI.base.model || ""),
          reasoning_effort: String(SESSION_INFO_UI.base.reasoning_effort || ""),
        };
        applySessionHeartbeatPayload(payload);
        syncConversationHeartbeatSummaryToStore(sid, SESSION_INFO_UI.heartbeatSummary, SESSION_INFO_UI.heartbeatTasks);
        SESSION_INFO_UI.loading = false;
        setConversationSessionInfoError("");
        renderConversationSessionInfoModal();
      } catch (_) {
        SESSION_INFO_UI.loading = false;
        setConversationSessionInfoError("读取会话信息失败：网络或服务异常。");
        renderConversationSessionInfoModal();
      }
    }

    function newConvModalError(msg) {
      const errEl = document.getElementById("newConvErr");
      if (errEl) {
        errEl.textContent = String(msg || "");
        errEl.style.display = msg ? "block" : "none";
      }
    }

    async function sendNewConversationInitMessage(projectId, channelName, sessionId, cliType, message, model = "") {
      try {
        const r = await fetch("/api/codex/announce", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            projectId,
            channelName,
            sessionId,
            cliType: cliType || "codex",
            model: normalizeSessionModel(model),
            message,
            ...buildUiUserSenderFields(),
          }),
        });
        if (!r.ok) {
          const detail = await parseResponseDetail(r);
          let msg = "";
          if (detail && typeof detail === "object") {
            msg = String(detail.error || detail.message || JSON.stringify(detail) || "");
          } else {
            msg = String(detail || "");
          }
          if (!msg) msg = "HTTP " + r.status;
          return { ok: false, error: msg || "请求失败" };
        }
        return { ok: true, error: "" };
      } catch (_) {
        return { ok: false, error: "网络或服务异常" };
      }
    }


    function newChannelFieldValue(id) {
      const n = document.getElementById(id);
      return String((n && n.value) || "");
    }

    function setNewChannelVisible(id, show) {
      const n = document.getElementById(id);
      if (n) n.style.display = show ? "" : "none";
    }

    const NEW_CHANNEL_MODE_COPY = {
      direct: {
        foot: "直接创建只生成空通道框架，不创建主任务或主对话。",
        action: "开始创建",
        subtitle: "创建空通道框架，或发起 Agent 辅助创建",
      },
      agent_assist: {
        foot: "系统会先创建空通道框架，再把要求正式派发给所选 Agent。",
        action: "发送给 Agent",
        subtitle: "创建空通道框架，或发起 Agent 辅助创建",
      },
    };

    function normalizeNewChannelMode(raw) {
      return String(raw || "").trim() === "agent_assist" ? "agent_assist" : "direct";
    }

    function normalizeNewChannelKindMode(raw) {
      const value = String(raw || "").trim();
      return value === "__custom__" || value === "custom" ? "custom" : "preset";
    }

    function normalizeNewChannelKind(raw) {
      return String(raw || "").trim().replace(/\s+/g, " ");
    }

    function normalizeNewChannelIndex(raw) {
      return String(raw || "").trim();
    }

    function normalizeNewChannelNamePart(raw) {
      return String(raw || "").trim().replace(/\s+/g, " ");
    }

    function normalizeNewChannelText(raw) {
      return String(raw || "").trim();
    }

    function normalizeNewChannelAgentText(raw) {
      return String(raw || "").trim();
    }

    function resolveNewChannelKind(form) {
      if (!form || typeof form !== "object") return "";
      const mode = normalizeNewChannelKindMode(form.channelKindMode || form.channelKind);
      if (mode === "custom") {
        return normalizeNewChannelKind(form.channelKindCustom || form.channelKind);
      }
      return normalizeNewChannelKind(form.channelKind);
    }

    function buildNewChannelName(form) {
      const kind = resolveNewChannelKind(form) || "业务";
      const idx = String(form.channelIndex || "").trim();
      const topic = String(form.channelName || "").trim();
      const core = [kind + (idx || ""), topic].filter(Boolean).join("-");
      return core || "";
    }

    function buildNewChannelDirectPreview(form) {
      const name = buildNewChannelName(form);
      const desc = String(form.channelDesc || "").trim();
      return {
        channelName: name || "-",
        channelDesc: desc || "通道说明留空时，会用通道名作为基础说明。",
      };
    }

    function getNewChannelWorkflowForm() {
      const selectedKind = String(newChannelFieldValue("newChannelKind") || "业务").trim();
      const kindMode = normalizeNewChannelKindMode(selectedKind);
      const customKind = normalizeNewChannelKind(newChannelFieldValue("newChannelKindCustom"));
      const resolvedKind = kindMode === "custom" ? customKind : normalizeNewChannelKind(selectedKind);
      return {
        projectId: String(STATE.project || "").trim(),
        mode: normalizeNewChannelMode(NEW_CHANNEL_UI.mode || "direct"),
        channelKindMode: kindMode,
        channelKind: resolvedKind,
        channelKindCustom: customKind,
        channelIndex: normalizeNewChannelIndex(newChannelFieldValue("newChannelIndex")),
        channelName: normalizeNewChannelNamePart(newChannelFieldValue("newChannelName")),
        channelDesc: normalizeNewChannelText(newChannelFieldValue("newChannelDesc")),
        requirement: normalizeNewChannelText(newChannelFieldValue("newChannelRequirement")),
        selectedAgentSessionId: String(NEW_CHANNEL_UI.selectedAgentSessionId || "").trim(),
      };
    }

    function getNewChannelResultBody() {
      return document.getElementById("newChannelResultBody");
    }

    function resetNewChannelResult() {
      const body = getNewChannelResultBody();
      if (body) body.innerHTML = "";
      setNewChannelVisible("newChannelResult", false);
    }

    function appendNewChannelResultRow(parent, label, value, opts = {}) {
      const row = el("div", { class: "ncresult-row" });
      row.appendChild(el("div", { class: "k", text: String(label || "") }));
      const cell = opts.code ? el("code", { class: "v" }) : el("div", { class: "v" });
      cell.textContent = String(value == null || value === "" ? "-" : value);
      row.appendChild(cell);
      parent.appendChild(row);
    }

    function renderNewChannelResult(mode, payload, extra = {}) {
      const body = getNewChannelResultBody();
      if (!body) return;
      body.innerHTML = "";
      const isError = !!extra.error;
      body.appendChild(el("div", {
        class: isError ? "ncresult-bad" : "ncresult-ok",
        text: isError ? "处理失败，请根据错误信息调整后重试。" : "处理完成，可继续下一步。",
      }));
      appendNewChannelResultRow(body, "模式", mode === "agent_assist" ? "Agent辅助创建" : "直接创建", { code: true });
      if (mode === "direct") {
        const framework = (payload && payload.framework) || {};
        appendNewChannelResultRow(body, "状态", payload && payload.status, { code: true });
        appendNewChannelResultRow(body, "通道名", payload && payload.channelName, { code: true });
        appendNewChannelResultRow(body, "说明", payload && payload.channelDesc, { code: true });
        appendNewChannelResultRow(body, "结果", framework.created ? "已创建空通道框架" : "创建处理中", {});
        appendNewChannelResultRow(body, "通道目录", framework.channelRootPath || payload && payload.resultPath, { code: true });
        appendNewChannelResultRow(body, "README", framework.readmePath, { code: true });
        appendNewChannelResultRow(body, "沟通-收件箱", framework.inboxPath, { code: true });
      } else {
        const dispatch = (payload && payload.dispatch) || {};
        const targetSession = (payload && payload.targetSession) || {};
        appendNewChannelResultRow(body, "状态", payload && payload.status, { code: true });
        appendNewChannelResultRow(body, "通道名", payload && payload.channelName, { code: true });
        appendNewChannelResultRow(body, "目标Agent", extra.agentDisplayName || targetSession.alias || targetSession.channelName || targetSession.sessionId || "-", { code: true });
        appendNewChannelResultRow(body, "目标会话ID", extra.agentSessionId || targetSession.sessionId || "-", { code: true });
        appendNewChannelResultRow(body, "派发 run", [extra.runId || dispatch.runId || "", dispatch.runStatus || ""].filter(Boolean).join(" / "), { code: true });
        appendNewChannelResultRow(body, "结果", dispatch.runId ? "已创建空通道框架并正式派发 Agent 辅助任务" : "派发处理中", {});
      }

      if (isError) {
        appendNewChannelResultRow(body, "错误信息", extra.error || "-", {});
        if (extra.detail) {
          const details = el("details", { class: "ncerr-detail" });
          details.appendChild(el("summary", { text: "错误详情（展开查看）" }));
          details.appendChild(el("pre", { text: JSON.stringify(extra.detail, null, 2) }));
          body.appendChild(details);
        }
      }
      setNewChannelVisible("newChannelResult", true);
    }

    function notifyNewChannelAgentAssistSuccess(form, payload, agent) {
      const createdChannelName = String((payload && payload.channelName) || buildNewChannelName(form) || "").trim();
      const agentName = String((agent && (agent.alias || agent.displayName || agent.channelName || agent.sessionId)) || "目标 Agent").trim();
      const dispatch = (payload && payload.dispatch) || {};
      const runId = String(dispatch.runId || "").trim();
      let message = "已创建通道";
      if (createdChannelName) message += "「" + createdChannelName + "」";
      message += "，并已给 " + agentName + " 发送正式消息。";
      if (createdChannelName) {
        message += " 请到「" + createdChannelName + "」或对应 Agent 会话查看进展。";
      } else {
        message += " 请到对应 Agent 会话查看进展。";
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

    function finalizeNewChannelAgentAssistSuccess(form, payload, agent) {
      if (typeof upsertCreatedChannelIntoLocalState === "function") {
        upsertCreatedChannelIntoLocalState(payload);
      }
      if (typeof rebuildDashboardAfterStatusChange === "function") rebuildDashboardAfterStatusChange();
      if (typeof render === "function") render();
      notifyNewChannelAgentAssistSuccess(form, payload, agent);
      if (typeof closeNewChannelModal === "function") closeNewChannelModal(true);
    }

    function newChannelModalError(msg) {
      const errEl = document.getElementById("newChannelErr");
      if (errEl) {
        errEl.textContent = String(msg || "");
        errEl.style.display = msg ? "block" : "none";
      }
    }

    function setNewChannelCreateSubmitting(submitting) {
      NEW_CHANNEL_UI.submitting = !!submitting;
      const createBtn = document.getElementById("newChannelCreateBtn");
      const cancelBtn = document.getElementById("newChannelCancelBtn");
      if (createBtn) {
        createBtn.disabled = !!submitting;
        createBtn.textContent = submitting
          ? (normalizeNewChannelMode(NEW_CHANNEL_UI.mode) === "agent_assist" ? "发送中..." : "创建中...")
          : (NEW_CHANNEL_MODE_COPY[normalizeNewChannelMode(NEW_CHANNEL_UI.mode)] || NEW_CHANNEL_MODE_COPY.direct).action;
      }
      if (cancelBtn) cancelBtn.disabled = !!submitting;
    }

    function renderNewChannelModeUi() {
      const mode = normalizeNewChannelMode(NEW_CHANNEL_UI.mode || "direct");
      NEW_CHANNEL_UI.mode = mode;
      const panels = document.querySelectorAll("#newChannelMask [data-new-channel-mode]");
      for (const panel of panels) {
        const panelMode = normalizeNewChannelMode(panel.getAttribute("data-new-channel-mode"));
        panel.classList.toggle("active", panelMode === mode);
      }
      const buttons = document.querySelectorAll("#newChannelMask [data-new-channel-mode]");
      for (const btn of buttons) {
        const btnMode = normalizeNewChannelMode(btn.getAttribute("data-new-channel-mode"));
        const active = btnMode === mode;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      }
      const subEl = document.getElementById("newChannelSub");
      if (subEl) subEl.textContent = (NEW_CHANNEL_MODE_COPY[mode] || NEW_CHANNEL_MODE_COPY.direct).subtitle;
      const footEl = document.getElementById("newChannelFootNote");
      if (footEl) footEl.textContent = (NEW_CHANNEL_MODE_COPY[mode] || NEW_CHANNEL_MODE_COPY.direct).foot;
      const createBtn = document.getElementById("newChannelCreateBtn");
      if (createBtn && !NEW_CHANNEL_UI.submitting) {
        createBtn.textContent = (NEW_CHANNEL_MODE_COPY[mode] || NEW_CHANNEL_MODE_COPY.direct).action;
      }
    }

    function renderNewChannelDirectPreview(form) {
      const preview = buildNewChannelDirectPreview(form || getNewChannelWorkflowForm());
      const nameEl = document.getElementById("newChannelPreviewName");
      const descEl = document.getElementById("newChannelPreviewDirectItems");
      const skipEl = document.getElementById("newChannelPreviewDirectSkip");
      if (nameEl) nameEl.textContent = preview.channelName || "-";
      if (descEl) descEl.textContent = "空通道框架 / README / 沟通-收件箱 / 基础目录";
      if (skipEl) skipEl.textContent = "主任务 / 主对话 / Agent";
    }

    function renderNewChannelAgentPicker() {
      const card = document.getElementById("newChannelAgentCard");
      const nameEl = document.getElementById("newChannelAgentName");
      const tagEl = document.getElementById("newChannelAgentTag");
      const metaEl = document.getElementById("newChannelAgentMeta");
      const menu = document.getElementById("newChannelAgentMenu");
      const candidates = Array.isArray(NEW_CHANNEL_UI.agentCandidates) ? NEW_CHANNEL_UI.agentCandidates : [];
      const selected = candidates.find((x) => String(x && x.sessionId || "") === String(NEW_CHANNEL_UI.selectedAgentSessionId || "")) || candidates[0] || null;

      if (selected && (!NEW_CHANNEL_UI.selectedAgentSessionId || String(NEW_CHANNEL_UI.selectedAgentSessionId) !== String(selected.sessionId || ""))) {
        NEW_CHANNEL_UI.selectedAgentSessionId = String(selected.sessionId || "");
        NEW_CHANNEL_UI.selectedAgent = selected;
      }

      if (card) card.classList.toggle("active", !!selected);
      if (nameEl) nameEl.textContent = selected ? agentDisplayTitle(selected, "-") : "-";
      if (tagEl) tagEl.textContent = selected && selected.isPrimary ? "主会话" : "子会话";
      if (metaEl) {
        if (NEW_CHANNEL_UI.agentLoading) metaEl.textContent = "正在加载可选 Agent…";
        else if (NEW_CHANNEL_UI.agentError) metaEl.textContent = NEW_CHANNEL_UI.agentError;
        else if (selected) metaEl.textContent = agentDisplaySubtitle(selected, { includeSessionIdFallback: true });
        else metaEl.textContent = "当前项目暂无可选 Agent";
      }
      if (menu) {
        menu.innerHTML = "";
        if (NEW_CHANNEL_UI.agentLoading) {
          menu.appendChild(el("div", { class: "agent-option", text: "正在加载可选 Agent…" }));
        } else if (!candidates.length) {
          menu.appendChild(el("div", { class: "agent-option", text: "当前项目暂无可选 Agent" }));
        } else {
          for (const item of candidates) {
            const option = el("button", {
              class: "agent-option" + (String(item.sessionId || "") === String(NEW_CHANNEL_UI.selectedAgentSessionId || "") ? " active" : ""),
              type: "button",
              "data-session-id": String(item.sessionId || ""),
              "aria-selected": String(item.sessionId || "") === String(NEW_CHANNEL_UI.selectedAgentSessionId || "") ? "true" : "false",
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
              selectNewChannelAgentSession(String(item.sessionId || ""));
            });
            menu.appendChild(option);
          }
        }
      }
    }

    function pickDefaultNewChannelAgent(candidates) {
      const list = Array.isArray(candidates) ? candidates.slice() : [];
      if (!list.length) return null;
      const normalized = (text) => String(text || "").trim();
      const isAssist01 = (row) => {
        const hay = [
          row && row.alias,
          row && row.displayName,
          row && row.display_name,
          row && row.channelName,
          row && row.channel_name,
        ].map((x) => normalized(x)).join(" ");
        return hay.includes("辅助01");
      };
      const primaryCandidates = list.filter((row) => !!(row && row.isPrimary));
      const assist01 = list.find((row) => isAssist01(row) && !!(row && row.isPrimary))
        || list.find((row) => isAssist01(row));
      if (assist01) return assist01;
      if (primaryCandidates.length) return primaryCandidates[0];
      return list[0];
    }

    function scoreNewChannelAgentCandidate(row) {
      const text = [
        row && row.alias,
        row && row.displayName,
        row && row.display_name,
        row && row.channelName,
        row && row.channel_name,
      ].join(" ").toLowerCase();
      let score = 0;
      if (row && row.isPrimary) score += 1000;
      if (text.includes("辅助01")) score += 800;
      if (text.includes("主会话") || text.includes("主对话")) score += 200;
      if (String((row && row.runtimeState && row.runtimeState.display_state) || "").toLowerCase() === "running") score += 40;
      if (String((row && row.runtimeState && row.runtimeState.internal_state) || "").toLowerCase() === "running") score += 20;
      return score;
    }

    function normalizeNewChannelAgentCandidate(raw) {
      const s = (raw && typeof raw === "object") ? raw : {};
      const normalized = typeof normalizeConversationSession === "function"
        ? normalizeConversationSession(s)
        : s;
      if (!normalized) return null;
      const sessionId = String(normalized.sessionId || normalized.id || "").trim();
      if (!sessionId) return null;
      return {
        sessionId,
        alias: String(normalized.alias || "").trim(),
        displayName: String((typeof conversationDisplayName === "function" ? conversationDisplayName(normalized) : (normalized.display_name || normalized.displayName || "")) || "").trim(),
        channelName: String(normalized.channel_name || normalized.primaryChannel || "").trim(),
        cliType: String(normalized.cli_type || normalized.cliType || "codex").trim() || "codex",
        model: String(normalized.model || "").trim(),
        isPrimary: !!normalized.is_primary,
        runtimeState: normalized.runtime_state || normalized.runtimeState || null,
        raw: normalized,
      };
    }

    async function loadNewChannelAgentCandidates(force = false) {
      const projectId = String(STATE.project || "").trim();
      if (!projectId || projectId === "overview") {
        NEW_CHANNEL_UI.agentCandidates = [];
        NEW_CHANNEL_UI.agentCandidatesProjectId = "";
        NEW_CHANNEL_UI.selectedAgentSessionId = "";
        NEW_CHANNEL_UI.selectedAgent = null;
        NEW_CHANNEL_UI.agentLoading = false;
        NEW_CHANNEL_UI.agentError = "";
        renderNewChannelAgentPicker();
        return [];
      }
      if (
        !force
        && NEW_CHANNEL_UI.agentCandidatesProjectId === projectId
        && Array.isArray(NEW_CHANNEL_UI.agentCandidates)
        && NEW_CHANNEL_UI.agentCandidates.length
      ) {
        return NEW_CHANNEL_UI.agentCandidates.slice();
      }
      NEW_CHANNEL_UI.agentLoading = true;
      NEW_CHANNEL_UI.agentError = "";
      renderNewChannelAgentPicker();

      const fetched = typeof fetchProjectAgentTargetRows === "function"
        ? await fetchProjectAgentTargetRows(projectId, force)
        : { rows: [], error: "加载 Agent 候选失败", source: "" };
      NEW_CHANNEL_UI.agentError = String((fetched && fetched.error) || "");
      const list = [];
      const seen = new Set();
      for (const raw of (Array.isArray(fetched.rows) ? fetched.rows : [])) {
        const item = normalizeNewChannelAgentCandidate(raw);
        if (!item || seen.has(item.sessionId)) continue;
        seen.add(item.sessionId);
        list.push(item);
      }
      list.sort((a, b) => {
        const sa = scoreNewChannelAgentCandidate(a);
        const sb = scoreNewChannelAgentCandidate(b);
        if (sa !== sb) return sb - sa;
        return String(a.alias || a.displayName || a.channelName || a.sessionId || "").localeCompare(String(b.alias || b.displayName || b.channelName || b.sessionId || ""), "zh-Hans-CN");
      });

      NEW_CHANNEL_UI.agentCandidatesProjectId = projectId;
      NEW_CHANNEL_UI.agentCandidates = list;
      const defaultAgent = pickDefaultNewChannelAgent(list);
      NEW_CHANNEL_UI.selectedAgentSessionId = defaultAgent ? String(defaultAgent.sessionId || "") : "";
      NEW_CHANNEL_UI.selectedAgent = defaultAgent;
      NEW_CHANNEL_UI.agentLoading = false;
      renderNewChannelAgentPicker();
      return list;
    }

    function getNewChannelSelectedAgent() {
      const list = Array.isArray(NEW_CHANNEL_UI.agentCandidates) ? NEW_CHANNEL_UI.agentCandidates : [];
      const sid = String(NEW_CHANNEL_UI.selectedAgentSessionId || "").trim();
      const selected = list.find((x) => String(x.sessionId || "") === sid) || null;
      return selected || pickDefaultNewChannelAgent(list);
    }

    function selectNewChannelAgentSession(sessionId) {
      const sid = String(sessionId || "").trim();
      const list = Array.isArray(NEW_CHANNEL_UI.agentCandidates) ? NEW_CHANNEL_UI.agentCandidates : [];
      const selected = list.find((x) => String(x.sessionId || "") === sid) || null;
      if (!selected) return;
      NEW_CHANNEL_UI.selectedAgentSessionId = sid;
      NEW_CHANNEL_UI.selectedAgent = selected;
      const picker = document.getElementById("newChannelAgentPicker");
      if (picker) picker.classList.remove("open");
      const card = document.getElementById("newChannelAgentCard");
      if (card) card.setAttribute("aria-expanded", "false");
      renderNewChannelAgentPicker();
    }

    function toggleNewChannelAgentMenu(forceOpen = null) {
      const picker = document.getElementById("newChannelAgentPicker");
      const card = document.getElementById("newChannelAgentCard");
      if (!picker || !card) return;
      const next = forceOpen == null ? !picker.classList.contains("open") : !!forceOpen;
      picker.classList.toggle("open", next);
      card.setAttribute("aria-expanded", next ? "true" : "false");
    }

    function getNewChannelSourceSession() {
      const projectId = String(STATE.project || "").trim();
      const channelName = String(STATE.channel || "").trim();
      let session = null;
      if (channelName && typeof findPrimaryConversationSession === "function") {
        session = findPrimaryConversationSession(channelName);
      }
      if (!session && typeof findConversationSessionById === "function" && STATE.selectedSessionId) {
        session = findConversationSessionById(STATE.selectedSessionId);
      }
      if (!session && projectId && typeof conversationSessionsForProject === "function") {
        const sessions = conversationSessionsForProject(projectId);
        session = (Array.isArray(sessions) ? sessions : []).find((x) => !!(x && x.is_primary)) || (Array.isArray(sessions) ? sessions[0] : null) || null;
      }
      const sessionId = String((session && (session.sessionId || session.session_id || session.id)) || "").trim();
      return {
        projectId,
        channelName: String((session && (session.channel_name || session.primaryChannel || session.channelName)) || channelName || "").trim(),
        sessionId,
        session,
      };
    }

    function buildNewChannelAgentPrompt(form, agent) {
      const source = getNewChannelSourceSession();
      const agentSessionId = String((agent && agent.sessionId) || "").trim();
      const agentDisplayName = String((agent && (agent.alias || agent.displayName || agent.channelName)) || "").trim();
      const agentChannelName = String((agent && agent.channelName) || agentDisplayName || "").trim();
      const requirement = String(form.requirement || "").trim();
      const callbackSessionId = String(source.sessionId || "").trim();
      const callbackChannelName = String(source.channelName || "").trim();
      const lines = [
        "[当前项目: " + String(form.projectId || STATE.project || "") + "]",
        "[来源通道: " + String(STATE.channel || callbackChannelName || "新增通道") + "]",
        "[目标通道: " + String(agentChannelName || "处理Agent") + "]",
        "[目标Agent: " + agentDisplayName + "; session_id=" + agentSessionId + "; role=" + (agent && agent.isPrimary ? "主" : "子") + "; alias=" + String((agent && agent.alias) || "") + "]",
        "[当前发信Agent: 用户; session_id=web-user; role=user; alias=我]",
        "[当前会话: session_id=" + String(callbackSessionId || "none") + "; binding_state=active]",
        "source_ref: project_id=" + String(form.projectId || STATE.project || "") + "; channel_name=" + String(callbackChannelName || STATE.channel || "") + "; session_id=" + String(callbackSessionId || "none") + "; run_id=none",
        "callback_to: session_id=" + String(callbackSessionId || "none"),
        "联系类型: announce_to_channel",
        "交互模式: task_with_receipt",
        "展示分类: collab_update",
        "回执任务: 20260318-新增通道最终弹框仿真稿-v3",
        "执行阶段: 启动",
        "本次目标: 根据业务要求，辅助生成新增通道创建方案并继续推进",
        "当前进展: 已完成处理Agent选择；已收集业务要求",
        "需要对方: 先拆出可执行的通道创建建议，并继续推进创建",
        "预期结果: 输出清晰的通道创建策略与必须字段建议",
        "project_execution_context: source=project; binding_state=已绑定",
        "业务要求:",
        requirement || "（未填写）",
      ];
      return lines.join("\n");
    }

    function renderNewChannelWorkflowUi() {
      renderNewChannelModeUi();
      const form = getNewChannelWorkflowForm();
      renderNewChannelKindUi(form);
      renderNewChannelDirectPreview(form);
      renderNewChannelAgentPicker();
      const result = document.getElementById("newChannelResult");
      if (result && NEW_CHANNEL_UI.phase === "form") {
        result.style.display = "none";
      }
    }

    function resetNewChannelFormForOpen() {
      const defaults = {
        newChannelKind: "业务",
        newChannelKindCustom: "",
        newChannelIndex: "",
        newChannelName: "",
        newChannelDesc: "",
        newChannelRequirement: "",
      };
      for (const [id, value] of Object.entries(defaults)) {
        const node = document.getElementById(id);
        if (node) node.value = value;
      }
      NEW_CHANNEL_UI.mode = "direct";
      NEW_CHANNEL_UI.selectedAgentSessionId = "";
      NEW_CHANNEL_UI.selectedAgent = null;
      NEW_CHANNEL_UI.agentCandidates = [];
      NEW_CHANNEL_UI.agentCandidatesProjectId = "";
      NEW_CHANNEL_UI.agentLoading = false;
      NEW_CHANNEL_UI.agentError = "";
      NEW_CHANNEL_UI.agentMenuOpen = false;
      NEW_CHANNEL_UI.phase = "form";
      const menu = document.getElementById("newChannelAgentMenu");
      const picker = document.getElementById("newChannelAgentPicker");
      const card = document.getElementById("newChannelAgentCard");
      if (menu) menu.innerHTML = "";
      if (picker) picker.classList.remove("open");
      if (card) card.setAttribute("aria-expanded", "false");
    }

    function resetNewChannelUiState() {
      NEW_CHANNEL_UI.phase = "form";
      newChannelModalError("");
      resetNewChannelResult();
      setNewChannelVisible("newChannelReloadBtn", false);
      setNewChannelCreateSubmitting(false);
      renderNewChannelWorkflowUi();
    }

    function handleNewChannelFormFieldChange() {
      if (!NEW_CHANNEL_UI.open) return;
      renderNewChannelWorkflowUi();
      if (NEW_CHANNEL_UI.phase !== "form") {
        NEW_CHANNEL_UI.phase = "form";
        setNewChannelVisible("newChannelReloadBtn", false);
      }
    }

    function bindNewChannelFormInputs() {
      if (NEW_CHANNEL_UI.inputBound) return;
      NEW_CHANNEL_UI.inputBound = true;

      const modeButtons = Array.from(document.querySelectorAll("#newChannelMask [data-new-channel-mode]"));
      for (const btn of modeButtons) {
        btn.addEventListener("click", async () => {
          const nextMode = normalizeNewChannelMode(btn.getAttribute("data-new-channel-mode"));
          if (NEW_CHANNEL_UI.mode === nextMode) return;
          NEW_CHANNEL_UI.mode = nextMode;
          renderNewChannelWorkflowUi();
          if (nextMode === "agent_assist") {
            await loadNewChannelAgentCandidates(false);
          }
        });
      }

      const ids = ["newChannelKind", "newChannelKindCustom", "newChannelIndex", "newChannelName", "newChannelDesc", "newChannelRequirement"];
      for (const id of ids) {
        const node = document.getElementById(id);
        if (!node) continue;
        const evt = node.tagName === "SELECT" ? "change" : "input";
        node.addEventListener(evt, handleNewChannelFormFieldChange);
      }

      const agentCard = document.getElementById("newChannelAgentCard");
      if (agentCard) {
        agentCard.addEventListener("click", async (e) => {
          e.preventDefault();
          if (NEW_CHANNEL_UI.mode !== "agent_assist") return;
          if (!Array.isArray(NEW_CHANNEL_UI.agentCandidates) || !NEW_CHANNEL_UI.agentCandidates.length) {
            await loadNewChannelAgentCandidates(true);
          }
          toggleNewChannelAgentMenu();
        });
      }

      const agentMenu = document.getElementById("newChannelAgentMenu");
      if (agentMenu && !agentMenu.__boundClickAway) {
        agentMenu.__boundClickAway = true;
        document.addEventListener("click", (e) => {
          const picker = document.getElementById("newChannelAgentPicker");
          if (!picker || !picker.contains(e.target)) {
            toggleNewChannelAgentMenu(false);
          }
        });
      }

      const headerCloseBtn = document.getElementById("newChannelHeaderCloseBtn");
      if (headerCloseBtn) {
        headerCloseBtn.addEventListener("click", (e) => {
          e.preventDefault();
          closeNewChannelModal();
        });
      }
    }

    function openNewChannelModal() {
      NEW_CHANNEL_UI.open = true;
      resetNewChannelFormForOpen();
      resetNewChannelUiState();
      const mask = document.getElementById("newChannelMask");
      if (mask) mask.classList.add("show");
      void loadNewChannelAgentCandidates(true);
    }

    function closeNewChannelModal(force = false) {
      if (NEW_CHANNEL_UI.submitting && !force) return;
      NEW_CHANNEL_UI.open = false;
      const mask = document.getElementById("newChannelMask");
      if (mask) mask.classList.remove("show");
      toggleNewChannelAgentMenu(false);
      newChannelModalError("");
    }

    function validateNewChannelForm(form) {
      const actualKind = resolveNewChannelKind(form);
      const missing = [];
      if (!form.projectId) missing.push("projectId");
      if (!form.mode) missing.push("mode");
      if (!actualKind) missing.push(form.channelKindMode === "custom" ? "自定义类型名称" : "通道类型");
      if (!form.channelIndex) missing.push("通道编号");
      if (!form.channelName) missing.push("业务主题");
      if (form.mode === "agent_assist") {
        if (!form.requirement) missing.push("业务要求说明");
        if (!String(form.selectedAgentSessionId || "").trim()) missing.push("处理Agent");
      }
      if (missing.length) return "请填写：" + missing.join("、");
      if (/[\/\\:*?"<>|]/.test(actualKind)) return "自定义类型名称不能包含 / \\\\ : * ? \" < > |";
      if (typeof validateNewChannelDuplicateConflict === "function") {
        const duplicateForm = Object.assign({}, form, { channelKind: actualKind });
        const duplicateMsg = String(validateNewChannelDuplicateConflict(duplicateForm) || "").trim();
        if (duplicateMsg) return duplicateMsg;
      }
      return "";
    }

    function renderNewChannelKindUi(form) {
      const mode = normalizeNewChannelKindMode(form && form.channelKindMode);
      const wrap = document.getElementById("newChannelKindCustomWrap");
      if (wrap) {
        wrap.classList.toggle("show", mode === "custom");
        wrap.style.display = mode === "custom" ? "grid" : "none";
      }
    }

    async function createNewChannel() {
      if (NEW_CHANNEL_UI.submitting) return;
      const form = getNewChannelWorkflowForm();
      const mode = normalizeNewChannelMode(form.mode);
      renderNewChannelWorkflowUi();
      const validationMsg = validateNewChannelForm(form);
      if (validationMsg) {
        newChannelModalError(validationMsg);
        renderNewChannelResult(mode, {}, { error: validationMsg });
        return;
      }

      newChannelModalError("");
      resetNewChannelResult();
      setNewChannelVisible("newChannelReloadBtn", false);
      setNewChannelCreateSubmitting(true);
      setNewChannelVisible("newChannelResult", false);

      try {
        const agent = mode === "agent_assist" ? getNewChannelSelectedAgent() : null;
        if (mode === "agent_assist" && !agent) {
          newChannelModalError("请先选择处理 Agent");
          renderNewChannelResult(mode, {}, { error: "请先选择处理 Agent" });
          NEW_CHANNEL_UI.phase = "error";
          return;
        }
        const source = getNewChannelSourceSession();
        const payload = {
          projectId: form.projectId,
          mode,
          channelKind: form.channelKind,
          channelKindMode: form.channelKindMode,
          channelKindCustom: form.channelKindCustom,
          channelIndex: form.channelIndex,
          channelName: form.channelName,
          channelDesc: form.channelDesc || "",
          sourceSessionId: String(source.sessionId || "").trim(),
          sourceChannelName: String(source.channelName || STATE.channel || "").trim(),
          sourceAgentName: "任务看板",
          sourceAgentAlias: "新增通道",
          sourceAgentId: "task_dashboard",
        };
        if (mode === "agent_assist") {
          payload.targetSessionId = String(agent.sessionId || "").trim();
          payload.businessRequirement = String(form.requirement || "").trim();
          payload.promptPreset = "channel_create_assist_v1";
        }

        const r = await fetch("/api/channels/bootstrap-v3", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        let j = null;
        try { j = await r.json(); } catch (_) {}
        if (!r.ok) {
          const fallback = String((j && (j.message || j.error)) || (await parseResponseDetail(r)) || "").trim();
          const duplicateConflict = r.status === 409 || /already exists/i.test(fallback);
          if (duplicateConflict && typeof syncExistingChannelConflictToLocalState === "function") {
            const healed = await syncExistingChannelConflictToLocalState(form, Object.assign({}, j || {}, {
              projectId: form.projectId,
              channelDesc: form.channelDesc || "",
            }));
            if (healed) {
              NEW_CHANNEL_UI.phase = "result";
              closeNewChannelModal(true);
              return;
            }
          }
          const info = typeof normalizeNewChannelFailureInfo === "function"
            ? normalizeNewChannelFailureInfo(mode, r, j || {}, form)
            : {
                message: (mode === "agent_assist" ? "创建/派发失败：" : "创建失败：") + (fallback || "unknown"),
                detail: j || {},
              };
          const msg = String((info && info.message) || fallback || "unknown");
          newChannelModalError(msg);
          renderNewChannelResult(mode, j || {}, {
            error: msg,
            detail: info && Object.prototype.hasOwnProperty.call(info, "detail") ? info.detail : (j || {}),
            agentDisplayName: agent ? String(agent.alias || agent.displayName || agent.channelName || agent.sessionId || "-") : "",
            agentSessionId: agent ? String(agent.sessionId || "") : "",
          });
          NEW_CHANNEL_UI.phase = "error";
          return;
        }
        const data = (j && typeof j === "object") ? j : {};
        const dispatch = (data && data.dispatch) || {};
        if (mode === "agent_assist") {
          setNewChannelCreateSubmitting(false);
          NEW_CHANNEL_UI.phase = "result";
          finalizeNewChannelAgentAssistSuccess(form, data, agent);
          return;
        }
        NEW_CHANNEL_UI.phase = "result";
        finalizeDirectNewChannelSuccess(form, data);
        return;
      } catch (err) {
        const msg = (err && err.message) ? String(err.message) : "网络或服务异常";
        newChannelModalError((mode === "agent_assist" ? "创建/派发失败：" : "创建失败：") + msg);
        renderNewChannelResult(mode, {}, { error: msg, detail: null });
        NEW_CHANNEL_UI.phase = "error";
      } finally {
        setNewChannelCreateSubmitting(false);
      }
    }

    function bucketKeyForStatus(status) {
      const s = String(status || "");
      if (s.includes("督办")) return "督办";
      if (s.includes("进行中")) return "进行中";
      if (s.includes("待开始")) return "待开始";
      if (s.includes("待处理")) return "待处理";
      if (s.includes("待验收")) return "待验收";
      if (s.includes("待消费")) return "待消费";
      if (DONE_STATUSES.has(s)) return "已完成";
      if (PAUSE_STATUSES.has(s)) return "已暂停";
      return "其他";
    }

    function taskStatusFlags(it) {
      const row = (it && typeof it === "object") ? it : {};
      const flags = (row && typeof row.status_flags === "object") ? row.status_flags : {};
      const raw = String((row && row.status) || it || "").trim();
      return {
        supervised: !!(flags.supervised || raw.includes("督办")),
        blocked: !!(flags.blocked || raw.includes("阻塞") || raw.includes("异常")),
      };
    }

    function resolveTaskPrimaryStatusText(raw, fallback = "") {
      const row = (raw && typeof raw === "object") ? raw : null;
      const direct = String(firstNonEmptyText([
        row && row.primary_status,
        row && row.task_primary_status,
      ], "") || "").trim();
      const source = direct || String((row && row.status) || raw || "").trim();
      const text = String(source || "").trim();
      if (!text) return String(fallback || "").trim();
      if (PRIMARY_TASK_STATUSES.includes(text)) return text;
      if (DONE_STATUSES.has(text) || /(?:已完成|完成|done)/i.test(text)) return "已完成";
      if (PAUSE_STATUSES.has(text) || /(?:暂停|暂缓|pause|paused)/i.test(text)) return "暂缓";
      if (/(?:待验收|验收|审核|review)/i.test(text)) return "待验收";
      if (/(?:进行中|处理中|阻塞|异常|running|in[_-]?progress|confirmed)/i.test(text)) return "进行中";
      if (/(?:待办|待开始|待处理|todo|pending|queued)/i.test(text)) return "待办";
      return String(fallback || "待办").trim() || "待办";
    }

    function taskDisplayStatusMeta(value, fallback = "待办") {
      const text = resolveTaskPrimaryStatusText(value, fallback);
      if (text === "进行中") return { text, key: "in_progress", tone: "warn" };
      if (text === "待验收") return { text, key: "review", tone: "warn" };
      if (text === "已完成") return { text, key: "done", tone: "good" };
      if (text === "暂缓") return { text, key: "paused", tone: "muted" };
      return { text: text || "待办", key: "todo", tone: "muted" };
    }

    function buildTaskStatusChip(value, fallback = "待办", extraClass = "") {
      const meta = taskDisplayStatusMeta(value, fallback);
      return el("span", {
        class: "chip task-status-chip status-" + meta.key + (extraClass ? " " + extraClass : ""),
        text: meta.text,
      });
    }

    function normalizeTaskRoleMemberDisplayText(value) {
      return String(value == null ? "" : value)
        .replace(/`+/g, "")
        .replace(/\s+/g, " ")
        .trim();
    }

    function taskRoleMemberDisplayMeta(rawMember) {
      if (rawMember == null) {
        return { text: "", meta: "", sessionId: "", channelName: "", raw: null };
      }
      if (typeof rawMember === "string") {
        const text = normalizeTaskRoleMemberDisplayText(rawMember);
        return {
          text,
          meta: "",
          sessionId: "",
          channelName: "",
          raw: text ? { display_name: text, alias: text, agent_name: text } : null,
        };
      }
      const member = (rawMember && typeof rawMember === "object") ? rawMember : {};
      const resolved = resolveTaskRoleMemberSession(member);
      const text = normalizeTaskRoleMemberDisplayText(firstNonEmptyText([
        member.display_name,
        member.agent_alias,
        member.alias,
        member.agent_name,
        member.name,
        resolved && resolved.display_name,
        resolved && resolved.alias,
        resolved && resolved.desc,
      ], ""));
      const metaParts = [];
      const channelName = String(firstNonEmptyText([
        member.channel_name,
        member.channelName,
        resolved && resolved.channel_name,
        resolved && resolved.primaryChannel,
        resolved && resolved.name,
      ], "") || "").trim();
      const responsibilityText = String(member.responsibility || "").trim();
      if (channelName) metaParts.push(channelName);
      if (responsibilityText) metaParts.push(responsibilityText);
      return {
        text,
        meta: metaParts.join(" · "),
        sessionId: String(firstNonEmptyText([
          member.session_id,
          member.sessionId,
          resolved && resolved.session_id,
          resolved && resolved.sessionId,
          resolved && resolved.id,
        ], "") || "").trim(),
        channelName,
        raw: resolved && typeof resolved === "object" ? resolved : member,
      };
    }

    function taskRoleMemberKey(rawMember) {
      const meta = taskRoleMemberDisplayMeta(rawMember);
      const member = (meta.raw && typeof meta.raw === "object") ? meta.raw : {};
      return [
        meta.sessionId,
        String(firstNonEmptyText([member.agent_id, member.agentId], "") || "").trim(),
        meta.text.toLowerCase(),
        meta.channelName,
      ].filter(Boolean).join("::");
    }

    function normalizeTaskRoleLookupText(value) {
      return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "");
    }

    function uniqueTaskRoleValues(values) {
      const out = [];
      const seen = new Set();
      (Array.isArray(values) ? values : []).forEach((value) => {
        const text = String(value || "").trim();
        if (!text || seen.has(text)) return;
        seen.add(text);
        out.push(text);
      });
      return out;
    }

    function taskRoleMemberIdentityHints(rawMember) {
      if (rawMember == null) {
        return {
          projectId: "",
          sessionId: "",
          fullNames: [],
          agentNames: [],
          channelNames: [],
        };
      }
      if (typeof rawMember === "string") {
        const text = String(rawMember || "").trim();
        const split = text.match(/^(.+?)\s*\/\s*(.+)$/);
        return {
          projectId: String(STATE.project || DATA.project_id || "").trim(),
          sessionId: "",
          fullNames: text ? [text] : [],
          agentNames: uniqueTaskRoleValues([text, split && split[2]]),
          channelNames: uniqueTaskRoleValues([split && split[1]]),
        };
      }
      const member = (rawMember && typeof rawMember === "object") ? rawMember : {};
      const names = uniqueTaskRoleValues([
        member.display_name,
        member.agent_alias,
        member.alias,
        member.agent_name,
        member.name,
      ]);
      const channelNames = uniqueTaskRoleValues([
        member.channel_name,
        member.channelName,
      ]);
      const agentNames = [];
      names.forEach((name) => {
        agentNames.push(name);
        const split = String(name || "").match(/^(.+?)\s*\/\s*(.+)$/);
        if (!split) return;
        channelNames.push(String(split[1] || "").trim());
        agentNames.push(String(split[2] || "").trim());
      });
      return {
        projectId: String(firstNonEmptyText([
          member.project_id,
          member.projectId,
          STATE.project,
          DATA.project_id,
        ], "") || "").trim(),
        sessionId: String(firstNonEmptyText([member.session_id, member.sessionId], "") || "").trim(),
        fullNames: names,
        agentNames: uniqueTaskRoleValues(agentNames),
        channelNames: uniqueTaskRoleValues(channelNames),
      };
    }

    function getTaskRoleProjectSessionCandidates(projectId = "") {
      const pid = String(projectId || STATE.project || DATA.project_id || "").trim();
      if (!pid || pid === "overview") return [];
      if (!PCONV.taskRoleSessionCandidateCache || typeof PCONV.taskRoleSessionCandidateCache !== "object") {
        PCONV.taskRoleSessionCandidateCache = Object.create(null);
      }
      if (Array.isArray(PCONV.taskRoleSessionCandidateCache[pid])) {
        return PCONV.taskRoleSessionCandidateCache[pid];
      }
      const project = projectById(pid);
      if (!project || typeof project !== "object") {
        PCONV.taskRoleSessionCandidateCache[pid] = [];
        return [];
      }
      const rows = [];
      const seen = new Set();
      const push = (raw, fallback = {}) => {
        const src = (raw && typeof raw === "object") ? raw : {};
        const sid = String(firstNonEmptyText([
          src.session_id,
          src.sessionId,
          src.id,
        ], "") || "").trim();
        if (!looksLikeSessionId(sid)) return;
        const row = {
          project_id: pid,
          projectId: pid,
          session_id: sid,
          sessionId: sid,
          id: sid,
          channel_name: String(firstNonEmptyText([
            src.channel_name,
            src.channelName,
            src.name,
            fallback.channel_name,
            fallback.channelName,
          ], "") || "").trim(),
          alias: String(firstNonEmptyText([
            src.alias,
            src.display_name,
            src.displayName,
            src.desc,
            fallback.alias,
            fallback.display_name,
            fallback.displayName,
            fallback.desc,
          ], "") || "").trim(),
          display_name: String(firstNonEmptyText([
            src.display_name,
            src.displayName,
            src.alias,
            src.desc,
            fallback.display_name,
            fallback.displayName,
            fallback.alias,
            fallback.desc,
          ], "") || "").trim(),
          desc: String(firstNonEmptyText([
            src.desc,
            src.display_name,
            src.displayName,
            src.alias,
            fallback.desc,
            fallback.display_name,
            fallback.displayName,
            fallback.alias,
          ], "") || "").trim(),
          session_role: String(firstNonEmptyText([
            src.session_role,
            src.sessionRole,
            fallback.session_role,
            fallback.sessionRole,
            boolLike(src.is_primary || src.isPrimary || fallback.is_primary || fallback.isPrimary) ? "primary" : "",
          ], "") || "").trim(),
          is_primary: boolLike(src.is_primary || src.isPrimary || fallback.is_primary || fallback.isPrimary),
          cli_type: String(firstNonEmptyText([src.cli_type, src.cliType, fallback.cli_type, fallback.cliType], "codex") || "codex").trim() || "codex",
          source: String(firstNonEmptyText([src.source, fallback.source], "") || "").trim(),
        };
        const key = [
          row.session_id,
          row.channel_name,
          row.display_name,
          row.alias,
          row.session_role,
        ].join("::");
        if (seen.has(key)) return;
        seen.add(key);
        rows.push(row);
      };
      (Array.isArray(project.channel_sessions) ? project.channel_sessions : []).forEach((row) => push(row));
      (Array.isArray(project.channels) ? project.channels : []).forEach((row) => push(row));
      const registryChannels = Array.isArray(project.registry && project.registry.channels)
        ? project.registry.channels
        : [];
      registryChannels.forEach((channel) => {
        const channelName = String((channel && channel.channel_name) || "").trim();
        const primarySessionId = String((channel && channel.primary_session_id) || "").trim();
        const primaryAlias = String((channel && channel.primary_session_alias) || "").trim();
        if (primarySessionId) {
          push({
            session_id: primarySessionId,
            channel_name: channelName,
            display_name: primaryAlias,
            alias: primaryAlias,
            desc: primaryAlias,
            session_role: "primary",
            is_primary: true,
            cli_type: channel && channel.primary_cli_type,
            source: "registry_primary",
          });
        }
        (Array.isArray(channel && channel.session_candidates) ? channel.session_candidates : []).forEach((candidate) => {
          push(candidate, {
            channel_name: channelName,
            display_name: candidate && (candidate.display_name || candidate.desc || primaryAlias),
            alias: candidate && (candidate.display_name || candidate.desc || primaryAlias),
            desc: candidate && (candidate.desc || candidate.display_name || primaryAlias),
            session_role: candidate && (candidate.session_role || (candidate.is_primary ? "primary" : "")),
            is_primary: !!(candidate && candidate.is_primary),
            cli_type: candidate && candidate.cli_type,
            source: "registry_candidate",
          });
        });
      });
      if (typeof conversationRuntimeSessionsForProject === "function") {
        conversationRuntimeSessionsForProject(pid).forEach((row) => push(row, { source: "runtime" }));
      }
      PCONV.taskRoleSessionCandidateCache[pid] = rows;
      return rows;
    }

    function resolveTaskRoleMemberSession(rawMember) {
      const hints = taskRoleMemberIdentityHints(rawMember);
      const member = (rawMember && typeof rawMember === "object") ? rawMember : {};
      const projectId = String(hints.projectId || "").trim();
      const sessionId = String(hints.sessionId || "").trim();
      const candidates = getTaskRoleProjectSessionCandidates(projectId);
      const bySessionId = sessionId
        ? candidates.find((row) => String(row.session_id || row.sessionId || row.id || "").trim() === sessionId)
        : null;
      if (bySessionId) {
        return Object.assign({}, member, bySessionId, {
          alias: String(firstNonEmptyText([member.alias, member.agent_alias, bySessionId.alias], "") || "").trim(),
          display_name: String(firstNonEmptyText([member.display_name, bySessionId.display_name, bySessionId.alias, bySessionId.desc], "") || "").trim(),
          project_id: projectId || bySessionId.project_id || "",
          projectId: projectId || bySessionId.projectId || "",
        });
      }
      const normalizedFull = new Set(hints.fullNames.map(normalizeTaskRoleLookupText).filter(Boolean));
      const normalizedAgent = new Set(hints.agentNames.map(normalizeTaskRoleLookupText).filter(Boolean));
      const normalizedChannel = new Set(hints.channelNames.map(normalizeTaskRoleLookupText).filter(Boolean));
      let best = null;
      let bestScore = -1;
      const scoreCandidate = (candidate) => {
        const current = (candidate && typeof candidate === "object") ? candidate : {};
        const candidateChannel = String(firstNonEmptyText([
          current.channel_name,
          current.channelName,
          current.name,
        ], "") || "").trim();
        const candidateNames = uniqueTaskRoleValues([
          current.display_name,
          current.displayName,
          current.alias,
          current.desc,
          current.name,
        ]);
        const normalizedCandidateChannel = normalizeTaskRoleLookupText(candidateChannel);
        const normalizedCandidateNames = candidateNames.map(normalizeTaskRoleLookupText).filter(Boolean);
        const normalizedComposite = candidateNames
          .map((name) => normalizeTaskRoleLookupText(candidateChannel ? (candidateChannel + " / " + name) : name))
          .filter(Boolean);
        let score = 0;
        if (normalizedCandidateChannel && normalizedChannel.has(normalizedCandidateChannel)) score += 40;
        if (normalizedComposite.some((value) => normalizedFull.has(value))) score += 120;
        if (normalizedCandidateNames.some((value) => normalizedAgent.has(value))) score += 80;
        if (normalizedCandidateNames.some((value) => normalizedFull.has(value))) score += 60;
        if (!normalizedAgent.size && normalizedCandidateChannel && normalizedChannel.has(normalizedCandidateChannel)) {
          if (boolLike(current.is_primary) || String(current.session_role || "").trim().toLowerCase() === "primary") {
            score += 24;
          }
        }
        return score;
      };
      candidates.forEach((candidate) => {
        const score = scoreCandidate(candidate);
        if (score <= 0) return;
        if (score > bestScore) {
          best = candidate;
          bestScore = score;
        }
      });
      if (best) {
        return Object.assign({}, member, best, {
          alias: String(firstNonEmptyText([member.alias, member.agent_alias, best.alias], "") || "").trim(),
          display_name: String(firstNonEmptyText([member.display_name, best.display_name, best.alias, best.desc], "") || "").trim(),
          project_id: projectId || best.project_id || "",
          projectId: projectId || best.projectId || "",
        });
      }
      const fallbackChannel = hints.channelNames[0];
      if (fallbackChannel && typeof sessionForChannel === "function") {
        const fallbackSession = sessionForChannel(projectId, fallbackChannel);
        if (fallbackSession && typeof fallbackSession === "object") {
          return Object.assign({}, member, fallbackSession, {
            channel_name: String(member.channel_name || member.channelName || fallbackChannel || fallbackSession.name || "").trim(),
            alias: String(firstNonEmptyText([member.alias, member.agent_alias, fallbackSession.alias], "") || "").trim(),
            display_name: String(firstNonEmptyText([member.display_name, fallbackSession.display_name, fallbackSession.alias, fallbackSession.desc], "") || "").trim(),
            project_id: projectId || fallbackSession.project_id || fallbackSession.projectId || "",
            projectId: projectId || fallbackSession.projectId || fallbackSession.project_id || "",
          });
        }
      }
      if (!member || typeof member !== "object") return null;
      return Object.assign({}, member, {
        project_id: projectId || member.project_id || member.projectId || "",
        projectId: projectId || member.projectId || member.project_id || "",
      });
    }

    function taskRoleGroups(raw, opts = {}) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const fallbackMain = item.main_owner
        || (item.owner ? { display_name: String(item.owner || "").trim(), alias: String(item.owner || "").trim(), agent_name: String(item.owner || "").trim() } : null)
        || item.next_owner
        || null;
      const groups = [
        { label: "主", members: fallbackMain ? [fallbackMain] : [] },
        { label: "管", members: Array.isArray(item.management_slot) ? item.management_slot : [] },
        { label: "协", members: Array.isArray(item.collaborators) ? item.collaborators : [] },
        { label: "验", members: Array.isArray(item.validators) ? item.validators : [] },
      ];
      return groups.map((group) => {
        const seen = new Set();
        const members = [];
        (Array.isArray(group.members) ? group.members : []).forEach((member) => {
          const key = taskRoleMemberKey(member);
          if (!key || seen.has(key)) return;
          const display = taskRoleMemberDisplayMeta(member);
          if (!display.text) return;
          seen.add(key);
          members.push(member);
        });
        return { label: group.label, members };
      }).filter((group) => group.members.length > 0 || !!opts.includeEmpty);
    }

    function buildTaskRoleAvatar(member, opts = {}) {
      const meta = taskRoleMemberDisplayMeta(member);
      if (!meta.text) return null;
      const sessionLike = Object.assign({}, (meta.raw && typeof meta.raw === "object") ? meta.raw : {}, {
        sessionId: meta.sessionId || "",
        session_id: meta.sessionId || "",
        alias: meta.text,
        displayName: meta.text,
        display_name: meta.text,
        agentDisplayName: meta.text,
        agent_display_name: meta.text,
        codexTitle: meta.text,
        channel_name: meta.channelName || "",
        primaryChannel: meta.channelName || "",
        project_id: String((meta.raw && typeof meta.raw === "object" && (meta.raw.project_id || meta.raw.projectId)) || STATE.project || DATA.project_id || "").trim(),
      });
      const node = typeof buildConversationAvatarNode === "function"
        ? buildConversationAvatarNode(sessionLike)
        : el("div", { class: "conv-avatar fallback", text: meta.text.slice(0, 1) || "任" });
      node.classList.add("task-role-avatar");
      if (opts.avatarClassName) {
        String(opts.avatarClassName || "").split(/\s+/).filter(Boolean).forEach((cls) => node.classList.add(cls));
      }
      node.title = meta.meta ? (meta.text + " · " + meta.meta) : meta.text;
      node.setAttribute("aria-label", meta.text);
      return node;
    }

    function buildTaskRoleGroups(raw, opts = {}) {
      const groups = taskRoleGroups(raw, opts);
      if (!groups.length) return null;
      const wrap = el("div", {
        class: "task-role-groups" + (opts.className ? " " + String(opts.className || "").trim() : ""),
      });
      groups.forEach((group) => {
        const block = el("div", { class: "task-role-group" });
        block.appendChild(el("span", {
          class: "task-role-group-label",
          text: group.label,
        }));
        const avatars = el("div", { class: "task-role-group-avatars" });
        group.members.forEach((member) => {
          const avatar = buildTaskRoleAvatar(member, { avatarClassName: opts.avatarClassName || "" });
          if (avatar) avatars.appendChild(avatar);
        });
        if (avatars.childNodes.length) {
          block.appendChild(avatars);
          wrap.appendChild(block);
        }
      });
      return wrap.childNodes.length ? wrap : null;
    }

    function normalizeTaskSummarySnippet(value, maxLength = 110) {
      const limit = Math.max(24, Number(maxLength || 0) || 110);
      const text = String(value || "").trim();
      if (!text) return "";
      const skipPlainLine = (line) => /^(?:更新时间|当前项目|主负责通道|主负责Agent|闭环方式|关联任务|需求来源|交付物|回执要求|关键路径(?:或 run_id)?|是否通过或放行|唯一阻塞|下一步动作|验收要点|本轮材料|当前说明|关键证据|执行阶段|本次目标|需要对方|预期结果|非必要问题|状态样本|参考文档)\s*[:：]?\s*$/u.test(line);
      const stripLeadLabel = (line) => String(line || "")
        .replace(/^(?:当前结论|执行结论|当前进展|最近进展|任务目标|目标|结论|说明)\s*[:：]\s*/u, "")
        .trim();
      const isTaskTitleLine = (line) => /^(?:【[^】]+】\s*){1,4}.*任务/u.test(line) || /^\d{8}(?:[-—].*)?任务/u.test(line);
      const isBareMetaValue = (line) => /^[A-Za-z0-9_@./-]{1,48}$/u.test(line);
      const isTrailingLabel = (line) => /^.{1,12}[：:]$/u.test(line);
      const isPreferredSummaryLine = (line) => /^(?:本任务|当前|已|将|需要|用于|支持|让|解决|修复|升级|改为|回到|保留)/u.test(line)
        || /(?:解决|修复|升级|支持|进入|改为|回到|保留|统一|补齐|确认|避免|处理)/u.test(line);
      const cleaned = text
        .replace(/```[\s\S]*?```/g, " ")
        .replace(/`([^`]+)`/g, "$1")
        .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
        .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
        .replace(/<\/?[^>]+>/g, " ")
        .replace(/^\s{0,3}#{1,6}\s*/gm, "")
        .replace(/(?:^|\s)#{1,6}\s+/g, " ")
        .replace(/^\s*>\s?/gm, "")
        .replace(/^\s*(?:[-*+]\s+|\d+\.\s+)/gm, "")
        .replace(/[*_~]+/g, "")
        .replace(/\|/g, " ")
        .replace(/\r/g, "\n");
      const lines = cleaned
        .split(/\n+/)
        .map((line) => line.replace(/^\s*(?:[-*+]\s+|\d+\.\s+)+/u, "").replace(/\s+/g, " ").trim())
        .filter(Boolean);
      const candidates = lines
        .map(stripLeadLabel)
        .filter((line) => line && !skipPlainLine(line) && !isTaskTitleLine(line) && !isBareMetaValue(line) && !isTrailingLabel(line) && !/^\d{8}(?:[-—].*)?$/u.test(line));
      const preferred = candidates.filter((line) => isPreferredSummaryLine(line));
      const chosen = [];
      let chosenLength = 0;
      for (const line of (preferred.length ? preferred : (candidates.length ? candidates : lines))) {
        if (!line || skipPlainLine(line)) continue;
        chosen.push(line);
        chosenLength += line.length;
        if (chosenLength >= 42 || chosen.length >= 2) break;
      }
      const merged = (chosen.length ? chosen : lines).join(" ").replace(/\s+/g, " ").trim();
      if (!merged) return "";
      if (merged.length <= limit) return merged;
      return merged.slice(0, Math.max(0, limit - 1)).trimEnd() + "…";
    }

    function taskSummaryText(raw, fallback = "") {
      const item = (raw && typeof raw === "object") ? raw : {};
      const text = normalizeTaskSummarySnippet(firstNonEmptyText([
        item.latest_action_text,
        item.task_summary_text,
        item.excerpt,
      ], ""), 110);
      return text || normalizeTaskSummarySnippet(fallback, 110);
    }

    function taskPrimaryStatus(it) {
      return resolveTaskPrimaryStatusText(it, "");
    }

    function taskPrimaryTone(status) {
      return taskDisplayStatusMeta(status, "待办").tone;
    }

    function emptyPrimaryTaskCounts() {
      return {
        todo: 0,
        in_progress: 0,
        pending_acceptance: 0,
        done: 0,
        paused: 0,
      };
    }

    function primaryTaskCountsFromItems(items) {
      const counts = emptyPrimaryTaskCounts();
      for (const it of (Array.isArray(items) ? items : [])) {
        const primary = taskPrimaryStatus(it);
        if (primary === "待办") counts.todo += 1;
        else if (primary === "进行中") counts.in_progress += 1;
        else if (primary === "待验收") counts.pending_acceptance += 1;
        else if (primary === "已完成") counts.done += 1;
        else if (primary === "暂缓") counts.paused += 1;
      }
      return counts;
    }

    function primaryTaskCountsFromTotals(totals) {
      const row = (totals && typeof totals === "object") ? totals : {};
      const payload = (row.primary_status_counts && typeof row.primary_status_counts === "object")
        ? row.primary_status_counts
        : null;
      if (payload) {
        return {
          todo: toNonNegativeInt(payload.todo, 0),
          in_progress: toNonNegativeInt(payload.in_progress, 0),
          pending_acceptance: toNonNegativeInt(payload.pending_acceptance, 0),
          done: toNonNegativeInt(payload.done, 0),
          paused: toNonNegativeInt(payload.paused, 0),
        };
      }
      return {
        todo: toNonNegativeInt(row.todo, 0),
        in_progress: toNonNegativeInt(row.in_progress, 0),
        pending_acceptance: toNonNegativeInt(row.pending_acceptance, 0),
        done: toNonNegativeInt(row.done, 0),
        paused: toNonNegativeInt(row.paused, 0),
      };
    }

    function toneForBucket(bucket) {
      if (bucket === "督办") return "bad";
      if (bucket === "进行中") return "warn";
      if (bucket === "待处理") return "warn";
      if (bucket === "待验收") return "warn";
      if (bucket === "待消费") return "warn";
      if (bucket === "待办") return "muted";
      if (bucket === "暂缓") return "muted";
      if (bucket === "已完成") return "good";
      return "muted";
    }

    function chip(text, cls = "") {
      return el("span", { class: "chip " + (cls || ""), text });
    }

    function metaPill(text, tone = "muted") {
      return el("span", { class: "metapill " + (tone || "muted"), text: String(text || "") });
    }

    function statusLabel(st, opts = {}) {
      const s = String(st || "").toLowerCase();
      if (opts && opts.timeout) return "超时";
      if (s === "done") return "已完成";
      if (s === "interrupted") return "打断";
      if (s === "running") return "处理中";
      if (s === "queued") {
        const depth = Math.max(0, Number(opts && opts.queueDepth) || 0);
        return depth > 0 ? ("排队(" + depth + ")") : "排队";
      }
      if (s === "retry_waiting") return "待重试";
      if (s === "external_busy") return "外部占用";
      if (s === "error") return "异常";
      return "空闲";
    }

    function statusTone(st, opts = {}) {
      const s = String(st || "").toLowerCase();
      if (opts && opts.timeout) return "bad";
      if (s === "done") return "good";
      if (s === "interrupted") return "bad";
      if (s === "running") return "warn";
      if (s === "queued") return "queued";
      if (s === "retry_waiting") return "waiting";
      if (s === "external_busy") return "external";
      if (s === "error") return "bad";
      return "muted";
    }

    function statusChip(st, opts = {}) {
      return el("span", { class: "stchip " + statusTone(st, opts), text: statusLabel(st, opts) });
    }

    function isTimeoutErrorText(raw) {
      const txt = String(raw || "").trim();
      if (!txt) return false;
      return /(?:\btimeout\b|timed out|operation timed out|os error 60|timeout>)/i.test(txt);
    }

    function isRunTimeoutLike(runMeta, detailMeta = null) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const full = detail && detail.full ? detail.full : null;
      const runFromDetail = (full && full.run && typeof full.run === "object") ? full.run : {};
      const status = String(firstNonEmptyText([
        run.status,
        runFromDetail.status,
      ]) || "").trim().toLowerCase();
      if (status && status !== "error") return false;
      const samples = [
        run.error,
        run.errorHint,
        run.eventReason,
        run.event_reason,
        run.logPreview,
        run.partialPreview,
        detail && detail.error,
        full && full.errorHint,
        full && full.logTail,
        full && full.partialMessage,
        runFromDetail.error,
        runFromDetail.eventReason,
        runFromDetail.event_reason,
      ];
      for (const sample of samples) {
        if (isTimeoutErrorText(sample)) return true;
      }
      return false;
    }

    function sessionHasTimeoutState(session) {
      const s = (session && typeof session === "object") ? session : {};
      const latestRunSummary = getSessionLatestRunSummary(s);
      if (boolLike(s.lastTimeout)) return true;
      const st = String(getSessionStatus(s) || "").toLowerCase();
      if (st !== "error") return false;
      if (isTimeoutErrorText(s.lastError) || isTimeoutErrorText(s.lastErrorHint) || isTimeoutErrorText(latestRunSummary.error)) return true;
      const sid = String(getSessionId(s) || "").trim();
      if (!sid) return false;
      const runs = Array.isArray(PCONV.runsBySession[sid]) ? PCONV.runsBySession[sid] : [];
      const top = runs[0] || null;
      return !!(top && isRunTimeoutLike(top));
    }

    function compactTimeoutHint(raw, maxLen = 96) {
      const text = String(raw || "").replace(/\s+/g, " ").trim();
      if (!text) return "";
      if (text.length <= maxLen) return text;
      return text.slice(0, Math.max(8, maxLen - 1)).trimEnd() + "…";
    }

    function sessionTimeoutHint(session) {
      const s = (session && typeof session === "object") ? session : {};
      const latestRunSummary = getSessionLatestRunSummary(s);
      const sid = String(getSessionId(s) || "").trim();
      const runs = sid && Array.isArray(PCONV.runsBySession[sid]) ? PCONV.runsBySession[sid] : [];
      const top = runs[0] || null;
      const samples = [
        latestRunSummary.error,
        s.lastErrorHint,
        s.lastError,
        top && top.errorHint,
        top && top.error,
        top && top.eventReason,
        top && top.event_reason,
        top && top.logPreview,
      ];
      for (const sample of samples) {
        if (!isTimeoutErrorText(sample)) continue;
        const oneLine = compactTimeoutHint(sample);
        if (oneLine) return oneLine;
      }
      return "";
    }

    function getSessionId(s) {
      return String((s && (s.sessionId || s.id)) || "");
    }

    function normalizeDisplayState(raw, fallback = "idle") {
      const s = String(raw || "").trim().toLowerCase();
      if (s === "running" || s === "queued" || s === "retry_waiting" || s === "done" || s === "error" || s === "idle" || s === "external_busy") {
        return s;
      }
      return String(fallback || "idle").trim().toLowerCase() || "idle";
    }

    function normalizeRuntimeState(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const internal = normalizeDisplayState(firstNonEmptyText([src.internal_state, src.internalState, src.status]), "idle");
      const externalBusy = (() => {
        if (typeof src.external_busy === "boolean") return src.external_busy;
        if (typeof src.externalBusy === "boolean") return src.externalBusy;
        const txt = String(firstNonEmptyText([src.external_busy, src.externalBusy]) || "").trim().toLowerCase();
        return txt === "1" || txt === "true" || txt === "yes" || txt === "y";
      })();
      const display = normalizeDisplayState(firstNonEmptyText([src.display_state, src.displayState]), (externalBusy ? "external_busy" : internal));
      return {
        internal_state: internal,
        external_busy: externalBusy,
        display_state: display,
        active_run_id: String(firstNonEmptyText([src.active_run_id, src.activeRunId]) || "").trim(),
        queued_run_id: String(firstNonEmptyText([src.queued_run_id, src.queuedRunId]) || "").trim(),
        queue_depth: Math.max(0, Number(firstNonEmptyText([src.queue_depth, src.queueDepth, 0])) || 0),
        updated_at: String(firstNonEmptyText([src.updated_at, src.updatedAt]) || "").trim(),
      };
    }

    function getSessionRuntimeState(s) {
      if (!s || typeof s !== "object") return normalizeRuntimeState(null);
      const rs = (s.runtime_state && typeof s.runtime_state === "object")
        ? s.runtime_state
        : ((s.runtimeState && typeof s.runtimeState === "object") ? s.runtimeState : null);
      return normalizeRuntimeState(rs);
    }

    function isExplicitIdleRuntimeState(raw) {
      const rs = normalizeRuntimeState(raw);
      return rs.display_state === "idle"
        && rs.internal_state === "idle"
        && !rs.external_busy
        && !rs.active_run_id
        && !rs.queued_run_id
        && rs.queue_depth <= 0;
    }

    function getSessionStatus(s) {
      return getSessionDisplayState(s);
    }

    function getSessionChannelName(s) {
      return String((s && (s.channel_name || s.primaryChannel || (s.channels && s.channels[0]))) || "");
    }

    function sessionMatchesChannel(session, channelName) {
      const target = String(channelName || "").trim();
      if (!target) return false;
      const primary = String(getSessionChannelName(session) || "").trim();
      if (primary === target) return true;
      const channels = Array.isArray(session && session.channels) ? session.channels : [];
      for (const ch of channels) {
        if (String(ch || "").trim() === target) return true;
      }
      return false;
    }

    function boolLike(v) {
      if (typeof v === "boolean") return v;
      const s = String(v == null ? "" : v).trim().toLowerCase();
      return s === "1" || s === "true" || s === "yes" || s === "y";
    }

    function isDeletedSession(session) {
      const s = (session && typeof session === "object") ? session : {};
      return boolLike(s.is_deleted || s.isDeleted);
    }

    function isInactiveSession(session) {
      const s = (session && typeof session === "object") ? session : {};
      if (boolLike(s.is_inactive || s.isInactive)) return true;
      const status = String(
        s.status || s.session_status || s.sessionStatus || s.binding_state || s.bindingState || ""
      ).trim().toLowerCase();
      return status === "inactive";
    }

    function isVisibleConversationSession(session) {
      return !isDeletedSession(session) && !isInactiveSession(session);
    }

    function isPrimarySession(session) {
      const s = (session && typeof session === "object") ? session : {};
      if (boolLike(s.is_primary) || boolLike(s.isPrimary)) return true;
      const role = String(s.session_role || s.sessionRole || "").trim().toLowerCase();
      if (role === "main" || role === "primary" || role === "主会话") return true;
      const sid = String(getSessionId(s) || s.session_id || s.id || "").trim();
      const projectId = String(s.project_id || s.projectId || STATE.project || "").trim();
      const channelName = String(getSessionChannelName(s) || "").trim();
      if (sid && projectId && channelName) {
        const proj = projectById(projectId);
        const primaryCfg = configuredPrimarySessionEntry(proj, channelName);
        const primarySid = String((primaryCfg && primaryCfg.session_id) || "").trim();
        if (primarySid && primarySid === sid) return true;
      }
      return false;
    }

    function sessionRoleLabel(session) {
      return isPrimarySession(session) ? "主会话" : "子会话";
    }

    function hasSessionRoleSignal(session) {
      const s = (session && typeof session === "object") ? session : {};
      if (typeof s.is_primary === "boolean" || typeof s.isPrimary === "boolean" || typeof s.isPrimarySession === "boolean") return true;
      const role = String(s.session_role || s.sessionRole || "").trim();
      return !!role;
    }

    function sessionRoleDisplayLabel(session) {
      return hasSessionRoleSignal(session) ? sessionRoleLabel(session) : "";
    }

    function agentDisplayTitle(session, fallback = "-") {
      const s = (session && typeof session === "object") ? session : {};
      const resolved = typeof resolveAgentDisplayName === "function"
        ? String(resolveAgentDisplayName(s) || "").trim()
        : "";
      if (resolved) return resolved;
      const stateLabel = String(conversationAgentName(s) || "").trim();
      if (stateLabel) return stateLabel;
      return String(fallback || "-").trim() || "-";
    }

    function agentDisplaySubtitle(session, opts = {}) {
      const s = (session && typeof session === "object") ? session : {};
      const parts = [];
      const channelLabel = String(
        getSessionChannelName(s)
        || s.channelName
        || s.channel_name
        || s.primaryChannel
        || ""
      ).trim();
      if (channelLabel) parts.push(channelLabel);
      const roleLabel = String(sessionRoleDisplayLabel(s) || "").trim();
      if (roleLabel) {
        parts.push(roleLabel);
      } else if (opts.includeSessionIdFallback !== false) {
        const sid = String(getSessionId(s) || s.sessionId || s.session_id || s.id || "").trim();
        if (sid) parts.push(sid);
      }
      return parts.filter(Boolean).join(" · ");
    }

    function sessionRoleTone(session) {
      return isPrimarySession(session) ? "good" : "muted";
    }

    const CONVERSATION_AVATAR_STORAGE_KEY = "taskDashboard.avatarAssignments.v1";
    const CONVERSATION_AVATAR_STORAGE_KEY_V2 = "taskDashboard.avatarAssignments.v2";
    const CONVERSATION_AVATAR_CATALOG = [
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
    const CONVERSATION_AVATAR_MAP = new Map(CONVERSATION_AVATAR_CATALOG.map((it) => [String(it.id || ""), it]));

    function normalizeSharedConversationAvatarStore(rawStore) {
      const out = {
        version: 2,
        bySessionId: Object.create(null),
        clearedSessionIds: Object.create(null),
      };
      const src = (rawStore && typeof rawStore === "object") ? rawStore : {};
      const bySessionId = (src.bySessionId && typeof src.bySessionId === "object") ? src.bySessionId : {};
      Object.keys(bySessionId).forEach((rawSid) => {
        const sid = String(rawSid || "").trim();
        const avatarId = String(bySessionId[rawSid] || "").trim();
        if (sid && avatarId && CONVERSATION_AVATAR_MAP.has(avatarId)) {
          out.bySessionId[sid] = avatarId;
        }
      });
      const clearedSessionIds = (src.clearedSessionIds && typeof src.clearedSessionIds === "object") ? src.clearedSessionIds : {};
      Object.keys(clearedSessionIds).forEach((rawSid) => {
        const sid = String(rawSid || "").trim();
        if (sid && clearedSessionIds[rawSid]) out.clearedSessionIds[sid] = true;
      });
      return out;
    }

    function resolveConversationAvatarProjectId(sessionLike) {
      const s = (sessionLike && typeof sessionLike === "object") ? sessionLike : {};
      const candidates = [
        s.project_id,
        s.projectId,
        s.project,
        STATE.project,
        DATA.project_id,
      ];
      for (const raw of candidates) {
        const pid = String(raw || "").trim();
        if (pid && pid !== "overview") return pid;
      }
      return "";
    }

    function getSharedConversationAvatarStore(projectId = "") {
      const pid = String(projectId || "").trim() || resolveConversationAvatarProjectId({});
      if (!pid) {
        return {
          version: 2,
          bySessionId: Object.create(null),
          clearedSessionIds: Object.create(null),
        };
      }
      if (!PCONV.sharedAvatarStoreCache || typeof PCONV.sharedAvatarStoreCache !== "object") {
        PCONV.sharedAvatarStoreCache = Object.create(null);
      }
      if (PCONV.sharedAvatarStoreCache[pid]) return PCONV.sharedAvatarStoreCache[pid];
      const projectRows = Array.isArray(DATA.projects) ? DATA.projects : [];
      const project = projectRows.find((row) => String((row && row.id) || "").trim() === pid) || null;
      const rawStore = project && typeof project.avatar_assignments === "object"
        ? project.avatar_assignments
        : (project && typeof project.avatarAssignments === "object" ? project.avatarAssignments : null);
      const normalized = normalizeSharedConversationAvatarStore(rawStore);
      PCONV.sharedAvatarStoreCache[pid] = normalized;
      return normalized;
    }

    function getConversationAvatarAssignments() {
      const empty = Object.create(null);
      let raw = "";
      try {
        raw = String(localStorage.getItem(CONVERSATION_AVATAR_STORAGE_KEY) || "");
      } catch (_) {
        raw = "";
      }
      if (raw === String(PCONV.avatarAssignmentsRaw || "")) {
        return PCONV.avatarAssignmentsCache || empty;
      }
      let parsed = empty;
      if (raw) {
        try {
          const data = JSON.parse(raw);
          const assignments = data && typeof data === "object" && data.assignments && typeof data.assignments === "object"
            ? data.assignments
            : {};
          parsed = Object.assign(Object.create(null), assignments);
        } catch (_) {
          parsed = empty;
        }
      }
      PCONV.avatarAssignmentsRaw = raw;
      PCONV.avatarAssignmentsCache = parsed;
      return parsed;
    }

    function getConversationAvatarStoreV2() {
      const empty = {
        version: 2,
        bySessionId: Object.create(null),
        clearedSessionIds: Object.create(null),
      };
      let raw = "";
      try {
        raw = String(localStorage.getItem(CONVERSATION_AVATAR_STORAGE_KEY_V2) || "");
      } catch (_) {
        raw = "";
      }
      if (raw === String(PCONV.avatarStoreV2Raw || "")) {
        return PCONV.avatarStoreV2Cache || empty;
      }
      let parsed = empty;
      if (raw) {
        try {
          const data = JSON.parse(raw);
          parsed = {
            version: 2,
            bySessionId: Object.assign(Object.create(null), data && typeof data.bySessionId === "object" ? data.bySessionId : {}),
            clearedSessionIds: Object.assign(Object.create(null), data && typeof data.clearedSessionIds === "object" ? data.clearedSessionIds : {}),
          };
        } catch (_) {
          parsed = empty;
        }
      }
      PCONV.avatarStoreV2Raw = raw;
      PCONV.avatarStoreV2Cache = parsed;
      return parsed;
    }

    function saveConversationAvatarStoreV2(store) {
      const normalized = {
        version: 2,
        bySessionId: Object.assign({}, (store && store.bySessionId) || {}),
        clearedSessionIds: Object.assign({}, (store && store.clearedSessionIds) || {}),
        updatedAt: new Date().toISOString(),
      };
      const raw = JSON.stringify(normalized);
      try {
        localStorage.setItem(CONVERSATION_AVATAR_STORAGE_KEY_V2, raw);
      } catch (_) {}
      PCONV.avatarStoreV2Raw = raw;
      PCONV.avatarStoreV2Cache = {
        version: 2,
        bySessionId: Object.assign(Object.create(null), normalized.bySessionId),
        clearedSessionIds: Object.assign(Object.create(null), normalized.clearedSessionIds),
      };
    }

    function getAvatarLibraryLinks() {
      const origin = /^https?:\/\//.test(window.location.origin || "")
        ? window.location.origin
        : ((window.location.protocol && window.location.host)
          ? `${window.location.protocol}//${window.location.host}`
          : "http://localhost:18770");
      return {
        primary: new URL("/share/avatar-library.html", origin).toString(),
        fallback: new URL("/dist/avatar-library.html", origin).toString(),
      };
    }

    function getAssignedAvatarIdForSession(sessionLike) {
      const s = (sessionLike && typeof sessionLike === "object") ? sessionLike : {};
      const sid = String(getSessionId(s) || s.sessionId || s.id || "").trim();
      const sharedStore = getSharedConversationAvatarStore(resolveConversationAvatarProjectId(s));
      if (sid) {
        const storeV2 = getConversationAvatarStoreV2();
        if (storeV2.clearedSessionIds && storeV2.clearedSessionIds[sid]) return "";
        const exactAvatarId = String((storeV2.bySessionId && storeV2.bySessionId[sid]) || "").trim();
        if (exactAvatarId && CONVERSATION_AVATAR_MAP.has(exactAvatarId)) return exactAvatarId;
      }
      const assignments = getConversationAvatarAssignments();
      const candidates = [];
      [
        conversationAgentName(s),
        s.alias,
        s.displayName,
        s.display_name,
        s.codexTitle,
        s.displayChannel,
        getSessionChannelName(s),
        s.primaryChannel,
      ].forEach((value) => {
        const text = String(value || "").trim();
        if (!text || candidates.includes(text)) return;
        candidates.push(text);
      });
      for (const key of candidates) {
        const avatarId = String(assignments[key] || "").trim();
        if (avatarId && CONVERSATION_AVATAR_MAP.has(avatarId)) return avatarId;
      }
      if (sid) {
        if (sharedStore.clearedSessionIds && sharedStore.clearedSessionIds[sid]) return "";
        const sharedAvatarId = String((sharedStore.bySessionId && sharedStore.bySessionId[sid]) || "").trim();
        if (sharedAvatarId && CONVERSATION_AVATAR_MAP.has(sharedAvatarId)) return sharedAvatarId;
      }
      return "";
    }

    function conversationAvatarFallbackLabel(name) {
      const s = typeof normalizeTaskRoleMemberDisplayText === "function"
        ? normalizeTaskRoleMemberDisplayText(name)
        : String(name || "").replace(/`+/g, "").trim();
      if (!s) return "会";
      const matched = s.match(/\d+/);
      if (matched && matched[0]) return matched[0];
      return s.slice(0, 1).toUpperCase();
    }

    function conversationAvatarMeta(sessionLike) {
      const s = (sessionLike && typeof sessionLike === "object") ? sessionLike : {};
      const sid = String(getSessionId(s) || s.sessionId || s.id || "").trim();
      const channelName = String(getSessionChannelName(s) || s.channel_name || s.primaryChannel || "").trim();
      const agentName = String(conversationAgentName(s) || "").trim();
      const storeV2 = getConversationAvatarStoreV2();
      const sharedStore = getSharedConversationAvatarStore(resolveConversationAvatarProjectId(s));
      if (sid && storeV2.clearedSessionIds && storeV2.clearedSessionIds[sid]) {
        const fallbackBase = agentName || sid || "未命名会话";
        return {
          mode: "fallback",
          text: conversationAvatarFallbackLabel(fallbackBase),
          accent: "#edf2ff",
          accent2: "#dbe5ff",
          title: fallbackBase,
          label: "",
          matchedOn: "cleared",
          avatarId: "",
        };
      }
      const exactAvatarId = sid ? String((storeV2.bySessionId && storeV2.bySessionId[sid]) || "").trim() : "";
      if (exactAvatarId) {
        const exactAvatar = CONVERSATION_AVATAR_MAP.get(exactAvatarId);
        if (exactAvatar) {
          return {
            mode: "assigned",
            text: String(exactAvatar.emoji || "🧑"),
            accent: String(exactAvatar.c1 || "#e0e7ff"),
            accent2: String(exactAvatar.c2 || "#c7d2fe"),
            title: (agentName || sid || "当前会话") + " · " + String(exactAvatar.name || exactAvatarId),
            label: String(exactAvatar.name || exactAvatarId),
            matchedOn: sid,
            avatarId: exactAvatarId,
          };
        }
      }
      const assignments = getConversationAvatarAssignments();
      const candidates = [];
      [
        agentName,
        s.alias,
        s.displayName,
        s.display_name,
        s.codexTitle,
        s.displayChannel,
        channelName,
        s.primaryChannel,
      ].forEach((value) => {
        const text = String(value || "").trim();
        if (!text || candidates.includes(text)) return;
        candidates.push(text);
      });
      for (const key of candidates) {
        const avatarId = String(assignments[key] || "").trim();
        if (!avatarId) continue;
        const avatar = CONVERSATION_AVATAR_MAP.get(avatarId);
        if (!avatar) continue;
        return {
          mode: "assigned",
          text: String(avatar.emoji || "🧑"),
          accent: String(avatar.c1 || "#e0e7ff"),
          accent2: String(avatar.c2 || "#c7d2fe"),
          title: key + " · " + String(avatar.name || avatarId),
          label: String(avatar.name || avatarId),
          matchedOn: key,
          avatarId,
        };
      }
      if (sid && sharedStore.clearedSessionIds && sharedStore.clearedSessionIds[sid]) {
        const fallbackBase = agentName || sid || "未命名会话";
        return {
          mode: "fallback",
          text: conversationAvatarFallbackLabel(fallbackBase),
          accent: "#edf2ff",
          accent2: "#dbe5ff",
          title: fallbackBase,
          label: "",
          matchedOn: "shared_cleared",
          avatarId: "",
        };
      }
      if (sid) {
        const sharedAvatarId = String((sharedStore.bySessionId && sharedStore.bySessionId[sid]) || "").trim();
        if (sharedAvatarId) {
          const sharedAvatar = CONVERSATION_AVATAR_MAP.get(sharedAvatarId);
          if (sharedAvatar) {
            return {
              mode: "assigned",
              text: String(sharedAvatar.emoji || "🧑"),
              accent: String(sharedAvatar.c1 || "#e0e7ff"),
              accent2: String(sharedAvatar.c2 || "#c7d2fe"),
              title: (agentName || sid || "当前会话") + " · " + String(sharedAvatar.name || sharedAvatarId),
              label: String(sharedAvatar.name || sharedAvatarId),
              matchedOn: "shared:" + sid,
              avatarId: sharedAvatarId,
            };
          }
        }
      }
      const fallbackBase = candidates[0] || sid || "未命名会话";
      return {
        mode: "fallback",
        text: conversationAvatarFallbackLabel(fallbackBase),
        accent: "#edf2ff",
        accent2: "#dbe5ff",
        title: fallbackBase,
        label: "",
        matchedOn: "",
        avatarId: "",
      };
    }

    function buildConversationAvatarNode(sessionLike, opts = {}) {
      const forcedAvatarId = String(opts.avatarId || "").trim();
      const meta = forcedAvatarId && CONVERSATION_AVATAR_MAP.has(forcedAvatarId)
        ? {
            mode: "assigned",
            text: String((CONVERSATION_AVATAR_MAP.get(forcedAvatarId) || {}).emoji || "🧑"),
            accent: String((CONVERSATION_AVATAR_MAP.get(forcedAvatarId) || {}).c1 || "#e0e7ff"),
            accent2: String((CONVERSATION_AVATAR_MAP.get(forcedAvatarId) || {}).c2 || "#c7d2fe"),
            title: String((CONVERSATION_AVATAR_MAP.get(forcedAvatarId) || {}).name || forcedAvatarId),
            label: String((CONVERSATION_AVATAR_MAP.get(forcedAvatarId) || {}).name || forcedAvatarId),
            matchedOn: "forced",
            avatarId: forcedAvatarId,
          }
        : conversationAvatarMeta(sessionLike);
      const node = el("div", {
        class: "conv-avatar " + (meta.mode === "assigned" ? "assigned" : "fallback") + (opts.large ? " large" : ""),
        text: meta.text,
        title: meta.title || "",
      });
      node.style.setProperty("--avatar-c1", meta.accent);
      node.style.setProperty("--avatar-c2", meta.accent2);
      return node;
    }

    function buildConversationRoleBadge(session) {
      const primary = isPrimarySession(session);
      const text = primary ? "主" : "子";
      const title = primary ? "主对话" : "子对话";
      return el("span", {
        class: "conv-role-badge " + (primary ? "primary" : "child"),
        text,
        title,
        "aria-label": title,
      });
    }

    function buildConversationCliBadge(sessionLike, opts = {}) {
      const s = (sessionLike && typeof sessionLike === "object") ? sessionLike : {};
      const cliType = String(s.cli_type || s.cliType || "codex").trim().toLowerCase();
      const text = conversationCliBadgeText(cliType);
      return el("span", {
        class: "conv-type-badge cli-" + normalizeCliTypeClass(cliType) + (opts.detail ? " detail" : ""),
        text,
        title: "对话类型：" + text,
        "aria-label": "对话类型：" + text,
      });
    }

    function ensureConversationPendingCreateStore(projectId = "") {
      if (!PCONV.pendingCreateBlocksByProject || typeof PCONV.pendingCreateBlocksByProject !== "object") {
        PCONV.pendingCreateBlocksByProject = Object.create(null);
      }
      const pid = String(projectId || "").trim();
      if (!pid) return [];
      if (!Array.isArray(PCONV.pendingCreateBlocksByProject[pid])) {
        PCONV.pendingCreateBlocksByProject[pid] = [];
      }
      return PCONV.pendingCreateBlocksByProject[pid];
    }

    function listConversationPendingCreateBlocks(projectId = "") {
      return ensureConversationPendingCreateStore(projectId).slice();
    }

    function upsertConversationPendingCreateBlock(block) {
      const source = (block && typeof block === "object") ? block : {};
      const pid = String(source.projectId || source.project_id || "").trim();
      const id = String(source.id || "").trim();
      if (!pid || !id) return null;
      const bucket = ensureConversationPendingCreateStore(pid);
      const next = {
        id,
        projectId: pid,
        channelName: String(source.channelName || source.channel_name || "").trim(),
        state: String(source.state || "creating").trim() || "creating",
        error: String(source.error || "").trim(),
        submittedAt: String(source.submittedAt || source.submitted_at || new Date().toISOString()).trim(),
        updatedAt: String(source.updatedAt || source.updated_at || new Date().toISOString()).trim(),
        formDraft: (source.formDraft && typeof source.formDraft === "object") ? { ...source.formDraft } : null,
      };
      const idx = bucket.findIndex((it) => String((it && it.id) || "") === id);
      if (idx >= 0) bucket[idx] = { ...bucket[idx], ...next };
      else bucket.unshift(next);
      return bucket[idx >= 0 ? idx : 0];
    }

    function markConversationPendingCreateBlockFailed(projectId, blockId, error = "", formDraft = null) {
      const pid = String(projectId || "").trim();
      const id = String(blockId || "").trim();
      if (!pid || !id) return null;
      const bucket = ensureConversationPendingCreateStore(pid);
      const idx = bucket.findIndex((it) => String((it && it.id) || "") === id);
      const next = {
        id,
        projectId: pid,
        state: "failed",
        error: String(error || "创建失败").trim() || "创建失败",
        updatedAt: new Date().toISOString(),
      };
      if (formDraft && typeof formDraft === "object") next.formDraft = { ...formDraft };
      if (idx >= 0) {
        bucket[idx] = { ...bucket[idx], ...next };
        return bucket[idx];
      }
      bucket.unshift({
        ...next,
        channelName: String((formDraft && formDraft.channelName) || "").trim(),
        submittedAt: new Date().toISOString(),
      });
      return bucket[0];
    }

    function removeConversationPendingCreateBlock(projectId, blockId) {
      const pid = String(projectId || "").trim();
      const id = String(blockId || "").trim();
      if (!pid || !id || !PCONV.pendingCreateBlocksByProject) return;
      const bucket = ensureConversationPendingCreateStore(pid);
      PCONV.pendingCreateBlocksByProject[pid] = bucket.filter((it) => String((it && it.id) || "") !== id);
      if (!PCONV.pendingCreateBlocksByProject[pid].length) delete PCONV.pendingCreateBlocksByProject[pid];
    }

    function isConversationPendingCreateSession(session) {
      return !!(session && typeof session === "object" && session.__pendingCreate === true);
    }

    function conversationPendingCreateBlockMeta(session) {
      if (!isConversationPendingCreateSession(session)) return null;
      const block = (session.pendingCreate && typeof session.pendingCreate === "object")
        ? session.pendingCreate
        : {};
      return {
        id: String(block.id || session.pendingCreateId || "").trim(),
        projectId: String(block.projectId || session.project_id || session.projectId || "").trim(),
        channelName: String(block.channelName || session.channel_name || "").trim(),
        state: String(block.state || "creating").trim() || "creating",
        error: String(block.error || "").trim(),
        formDraft: (block.formDraft && typeof block.formDraft === "object") ? block.formDraft : null,
      };
    }

    function buildConversationPendingCreateSession(block) {
      const meta = (block && typeof block === "object") ? block : {};
      const id = String(meta.id || "").trim();
      const draft = (meta.formDraft && typeof meta.formDraft === "object") ? meta.formDraft : {};
      const channelName = String(meta.channelName || draft.channelName || "").trim();
      const alias = String(draft.alias || "").trim();
      const sessionRole = String(draft.sessionRole || "child").trim() || "child";
      const cliType = String(draft.cliType || "codex").trim() || "codex";
      const lastActiveAt = String(meta.updatedAt || meta.submittedAt || new Date().toISOString()).trim();
      const syntheticId = "pending-create:" + id;
      return {
        __pendingCreate: true,
        pendingCreateId: id,
        pendingCreate: {
          ...meta,
          formDraft: draft,
        },
        id: syntheticId,
        sessionId: syntheticId,
        session_id: syntheticId,
        project_id: String(meta.projectId || "").trim(),
        projectId: String(meta.projectId || "").trim(),
        channel_name: channelName,
        channelName,
        primaryChannel: channelName,
        channels: channelName ? [channelName] : [],
        alias,
        displayName: alias || "新建Agent对话",
        cli_type: cliType,
        cliType,
        model: String(draft.model || "").trim(),
        session_role: sessionRole,
        sessionRole,
        purpose: String(draft.purpose || "").trim(),
        environment: String(draft.environment || "").trim(),
        worktree_root: String(draft.worktreeRoot || "").trim(),
        workdir: String(draft.workdir || "").trim(),
        branch: String(draft.branch || "").trim(),
        lastActiveAt,
        created_at: String(meta.submittedAt || lastActiveAt).trim(),
      };
    }

    function conversationPendingCreateSessionsForProject(projectId = "") {
      const pid = String(projectId || "").trim();
      if (!pid) return [];
      return listConversationPendingCreateBlocks(pid)
        .map((block) => buildConversationPendingCreateSession(block))
        .filter(Boolean);
    }

    function buildConversationPendingCreateRow(session, projectId = "") {
      const meta = conversationPendingCreateBlockMeta(session);
      const row = el("div", {
        class: "rowbtn conv-row conv-create-row is-create-" + String((meta && meta.state) || "creating"),
      });
      row.appendChild(buildConversationAvatarNode(session));
      const mainDiv = el("div", { class: "conv-main" });
      const headRow = el("div", { class: "conv-card-head" });
      const titleWrap = el("div", { class: "conv-card-titlewrap" });
      const titleRow = el("div", { class: "conv-title" });
      const displayName = conversationAgentName(session);
      titleRow.appendChild(el("span", {
        class: "conv-name",
        text: displayName,
        title: displayName,
      }));
      titleWrap.appendChild(titleRow);
      const metaRow = el("div", { class: "conv-card-submeta" });
      metaRow.appendChild(buildConversationRoleBadge(session));
      metaRow.appendChild(buildConversationCliBadge(session));
      conversationSecondaryMeta(session).forEach((part) => {
        metaRow.appendChild(el("span", {
          class: "conv-subchip " + String((part && part.kind) || "").trim(),
          text: String((part && part.text) || "").trim(),
        }));
      });
      titleWrap.appendChild(metaRow);
      headRow.appendChild(titleWrap);
      headRow.appendChild(el("div", { class: "conv-card-side" }, [
        el("span", {
          class: "conv-create-badge " + (meta && meta.state === "failed" ? "failed" : "creating"),
          text: meta && meta.state === "failed" ? "创建失败" : "创建中",
          title: meta && meta.state === "failed" ? "创建失败" : "正在接入通道对话",
        }),
      ]));
      mainDiv.appendChild(headRow);

      const detail = el("div", {
        class: "conv-create-detail" + (meta && meta.state === "failed" ? " failed" : ""),
      });
      detail.appendChild(el("div", {
        class: "conv-create-detail-title",
        text: meta && meta.state === "failed" ? "创建未完成" : "正在接入通道对话",
      }));
      detail.appendChild(el("div", {
        class: "conv-create-detail-text",
        text: meta && meta.state === "failed"
          ? (meta.error || "创建失败，请重试。")
          : "弹框已关闭，当前会话正在创建并等待正式卡片替换。",
        title: meta && meta.state === "failed" ? (meta.error || "创建失败，请重试。") : "",
      }));
      if (meta && meta.state === "failed") {
        const actions = el("div", { class: "conv-create-actions" });
        const retryBtn = el("button", {
          class: "conv-create-action-btn warn",
          type: "button",
          text: "重试",
        });
        retryBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          openNewConvModal(meta.projectId || projectId || STATE.project || "", meta.channelName || "", "create", {
            presetDraft: meta.formDraft || null,
            retryPendingBlockId: meta.id,
            forceAdvancedOpen: true,
          });
        });
        const closeBtn = el("button", {
          class: "conv-create-action-btn ghost",
          type: "button",
          text: "关闭",
        });
        closeBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          removeConversationPendingCreateBlock(meta.projectId || projectId || STATE.project || "", meta.id);
          render();
        });
        actions.appendChild(retryBtn);
        actions.appendChild(closeBtn);
        detail.appendChild(actions);
      }
      mainDiv.appendChild(detail);
      row.appendChild(mainDiv);
      return row;
    }

    function conversationSecondaryMeta(session) {
      const s = (session && typeof session === "object") ? session : {};
      const parts = [];
      const channelLabel = String(getSessionChannelName(s) || "").trim();
      if (channelLabel) {
        parts.push({ text: channelLabel, kind: "channel" });
      } else {
        const sid = String(getSessionId(s) || s.sessionId || s.id || "").trim();
        if (sid) parts.push({ text: sid, kind: "session" });
      }
      return parts.filter(Boolean).slice(0, 1);
    }

    function conversationTaskCountsKnownForSession(session) {
      const s = (session && typeof session === "object") ? session : {};
      return !!getConversationListTaskCounts(s);
    }

    function conversationTaskCountsForSession(session, projectId) {
      const s = (session && typeof session === "object") ? session : {};
      const counts = getConversationListTaskCounts(s);
      if (counts) {
        return {
          in_progress: Math.max(0, Number(counts.in_progress || 0) || 0),
          pending: Math.max(0, Number(counts.pending || 0) || 0),
        };
      }
      if (typeof countConversationAssociatedTasks === "function" && hasConversationTaskTrackingData(s.task_tracking)) {
        return countConversationAssociatedTasks(s, projectId);
      }
      return { in_progress: 0, pending: 0 };
    }

    function appendConversationListMetricSubchips(metaRow, session) {
      const row = metaRow;
      const s = (session && typeof session === "object") ? session : {};
      const counts = getConversationListTaskCounts(s);
      if (!row || !counts) return row;
      row.taskCounts = counts;
      return row;
    }

    function shouldDeferConversationTaskCountWarmup(projectId, sessions) {
      const pid = String(projectId || "").trim();
      const sid = String((STATE && STATE.selectedSessionId) || "").trim();
      if (!pid || !sid || !STATE || !STATE.selectedSessionExplicit) return false;
      if (!looksLikeSessionId(sid)) return false;
      const list = Array.isArray(sessions) ? sessions : [];
      if (!list.some((item) => String(getSessionId(item) || "").trim() === sid)) return false;
      const meta = ((((PCONV || {}).sessionDirectoryMetaByProject || {})[pid]) || {});
      if (!meta.liveLoaded) return false;
      const timelineKey = pid + "::" + sid;
      if (String((PCONV && PCONV.timelineLoadingKey) || "").trim() === timelineKey) return true;
      const timelineMap = (PCONV && PCONV.sessionTimelineMap) || {};
      return !Object.prototype.hasOwnProperty.call(timelineMap, timelineKey);
    }

    function conversationStatusMeta(session) {
      const s = (session && typeof session === "object") ? session : {};
      const listMetricStatusMeta = conversationListMetricBadgeStatusMeta(s) || conversationListCurrentTaskSummaryMeta(s);
      const runtimeState = getSessionRuntimeState(s);
      const effectiveStatus = getSessionStatus(s);
      const sessionHealthState = getSessionHealthState(s);
      const latestRunSummary = getSessionLatestRunSummary(s);
      const latestEffectiveRunSummary = getSessionLatestEffectiveRunSummary(s);
      const latestEffectiveOutcomeState = normalizeRunOutcomeState(
        latestEffectiveRunSummary && latestEffectiveRunSummary.outcome_state,
        ""
      );
      const latestSummaryStatus = normalizeDisplayState(firstNonEmptyText([
        latestRunSummary && latestRunSummary.status,
        latestRunSummary && latestRunSummary.display_state,
        latestRunSummary && latestRunSummary.displayState,
      ]), "idle");
      const latestSummaryRunId = String(firstNonEmptyText([
        latestRunSummary && latestRunSummary.run_id,
        latestRunSummary && latestRunSummary.runId,
      ]) || "").trim();
      const timeoutLike = effectiveStatus === "error" && sessionHasTimeoutState(s);
      if (effectiveStatus === "running" || effectiveStatus === "queued" || effectiveStatus === "retry_waiting" || effectiveStatus === "external_busy") {
        const tone = effectiveStatus === "running"
          ? "running"
          : (effectiveStatus === "queued"
            ? "queued"
            : (effectiveStatus === "retry_waiting" ? "waiting" : "external"));
        const titleParts = [];
        if (runtimeState.queue_depth > 0) titleParts.push("队列深度: " + runtimeState.queue_depth);
        if (runtimeState.active_run_id) titleParts.push("活跃run: " + shortId(runtimeState.active_run_id));
        if (runtimeState.queued_run_id) titleParts.push("排队run: " + shortId(runtimeState.queued_run_id));
        if (runtimeState.updated_at) titleParts.push("更新: " + compactDateTime(runtimeState.updated_at));
        if (runtimeState.external_busy && effectiveStatus !== "external_busy") titleParts.push("外部占用");
        if (latestRunSummary.run_id && !runtimeState.active_run_id && !runtimeState.queued_run_id) {
          titleParts.push("最近run: " + shortId(latestRunSummary.run_id));
        }
        const hasRuntimePriority = !!(runtimeState.active_run_id || runtimeState.queued_run_id);
        const staleLatestErrorWhileWorking = latestSummaryStatus === "error"
          && hasRuntimePriority
          && (!latestSummaryRunId
            || (latestSummaryRunId !== String(runtimeState.active_run_id || "").trim()
              && latestSummaryRunId !== String(runtimeState.queued_run_id || "").trim()));
        if (staleLatestErrorWhileWorking) {
          titleParts.push(
            latestSummaryRunId
              ? ("上一条 run 异常: " + shortId(latestSummaryRunId))
              : "上一条 run 状态: 异常"
          );
        }
        const reason = getSessionDisplayReason(s);
        if (reason) titleParts.push("来源: " + reason);
        return {
          text: statusLabel(effectiveStatus, { queueDepth: runtimeState.queue_depth }),
          tone,
          title: titleParts.join("\n"),
          source: "runtime_state",
        };
      }
      if (listMetricStatusMeta && listMetricStatusMeta.text) {
        const metaRow = {
          text: listMetricStatusMeta.text,
          tone: listMetricStatusMeta.tone || "info",
          title: listMetricStatusMeta.title || "",
          source: "conversation_list_metrics",
        };
        return typeof appendConversationListMetricSubchips === "function"
          ? appendConversationListMetricSubchips(metaRow, session)
          : metaRow;
      }
      if (timeoutLike) {
        const timeoutTitle = sessionTimeoutHint(s);
        return {
          text: statusLabel(effectiveStatus, { timeout: true }),
          tone: "timeout",
          title: timeoutTitle ? ("超时摘要：" + timeoutTitle) : "超时",
          source: "runtime_state",
        };
      }
      if (effectiveStatus === "interrupted") {
        const interruptedTitleParts = [];
        if (latestEffectiveRunSummary.run_id) interruptedTitleParts.push("最近有效 run: " + shortId(latestEffectiveRunSummary.run_id));
        if (latestEffectiveRunSummary.created_at) interruptedTitleParts.push("时间: " + compactDateTime(latestEffectiveRunSummary.created_at));
        const terminalHint = String(
          latestRunSummary.error
          || s.lastError
          || s.error
          || ""
        ).trim();
        if (latestEffectiveOutcomeState === "interrupted_infra") {
          interruptedTitleParts.push("基础设施中断，不按业务失败处理");
          if (terminalHint) interruptedTitleParts.push(terminalHint);
          return {
            text: "环境中断",
            tone: "external",
            title: interruptedTitleParts.join("\n"),
            source: "runtime_state",
          };
        }
        interruptedTitleParts.push("用户或人工操作打断");
        if (terminalHint) interruptedTitleParts.push(terminalHint);
        return {
          text: "已打断",
          tone: "waiting",
          title: interruptedTitleParts.join("\n"),
          source: "runtime_state",
        };
      }
      if (effectiveStatus === "error") {
        const terminalHint = String(latestRunSummary.error || s.lastError || s.error || "").trim();
        if (sessionHealthState === "blocked" || latestEffectiveOutcomeState === "failed_config") {
          return {
            text: "配置阻塞",
            tone: "error",
            title: terminalHint || "会话绑定、工作区权限或 CLI 配置存在问题",
            source: "runtime_state",
          };
        }
        if (sessionHealthState === "attention" && latestEffectiveOutcomeState === "failed_business") {
          return {
            text: "业务失败",
            tone: "error",
            title: terminalHint || "业务处理失败",
            source: "runtime_state",
          };
        }
        return {
          text: "异常",
          tone: "error",
          title: terminalHint || "执行异常",
          source: "runtime_state",
        };
      }
      return null;
    }

    function conversationHeatMeta(session) {
      const s = (session && typeof session === "object") ? session : {};
      const ts = toTimeNum(String(s.lastActiveAt || ""));
      if (ts < 0) return null;
      const diffMs = Math.max(0, Date.now() - ts);
      const diffMin = diffMs / 60000;
      if (diffMin > 60) return null;
      if (diffMin <= 10) return { tier: "strong", score: Math.max(0, Math.round(60 - diffMin)) };
      if (diffMin <= 30) return { tier: "mid", score: Math.max(0, Math.round(60 - diffMin)) };
      return { tier: "soft", score: Math.max(0, Math.round(60 - diffMin)) };
    }

    function buildConversationStatusBadge(session) {
      const meta = conversationStatusMeta(session);
      if (!meta || !meta.text) return null;
      return el("span", {
        class: "conv-status-badge " + String(meta.tone || "idle"),
        text: meta.text,
        title: meta.title || "",
      });
    }

    function conversationHeartbeatSummary(session) {
      const s = (session && typeof session === "object") ? session : {};
      return normalizeHeartbeatSummaryClient(
        s.heartbeat_summary || s.heartbeatSummary || {},
        []
      );
    }

    function buildConversationHeartbeatBadges(session) {
      const summary = conversationHeartbeatSummary(session);
      const enabledCount = Math.max(0, Number(summary.enabled_count || 0));
      if (!enabledCount) return null;
      const wrap = el("span", {
        class: "conv-heartbeat-badges",
        title: "已启用 " + enabledCount + " 条心跳任务",
      });
      wrap.appendChild(el("span", { class: "conv-heartbeat-icon", text: "❤", "aria-hidden": "true" }));
      wrap.appendChild(el("span", { class: "conv-heartbeat-count", text: String(enabledCount) }));
      return wrap;
    }

    function buildConversationCountBadges(session, opts = {}) {
      const s = (session && typeof session === "object") ? session : {};
      const sid = String(getSessionId(s) || "").trim();
      const projectId = String((opts && opts.projectId) || STATE.project || "").trim();
      const showUnread = !!(opts && opts.showUnread);
      const wrap = el("div", { class: "conv-counts" });
      let hasAny = false;
      const draftMeta = conversationDraftMetaBySession(projectId, sid);
      if (draftMeta.hasDraft) {
        wrap.appendChild(el("span", {
          class: "conv-count-dot draft",
          text: "草稿",
          title: conversationDraftTitle(draftMeta),
        }));
        hasAny = true;
      }
      if (showUnread && sid && projectId && projectId !== "overview") {
        const key = convComposerDraftKey(projectId, sid);
        const unreadMsg = countUnreadConversationMessagesByKey(key, sid);
        const memoState = getConversationMemoStateByKey(key);
        const unreadMemo = countUnreadConversationMemosByKey(key, memoState);
        const memoDisplayCount = (typeof resolveConversationMemoDisplayCount === "function")
          ? resolveConversationMemoDisplayCount(s, key, memoState)
          : unreadMemo;
        const memoTitle = (typeof conversationMemoCountTitle === "function")
          ? conversationMemoCountTitle(s, key, memoState)
          : (unreadMemo > 0 ? ("备忘未消费：" + unreadMemo) : "");
        if (unreadMsg > 0) {
          wrap.appendChild(el("span", {
            class: "conv-count-dot new",
            text: memoCountText(unreadMsg),
            title: "新消息未消费：" + unreadMsg,
          }));
          hasAny = true;
        }
        if (memoDisplayCount > 0) {
          wrap.appendChild(el("span", {
            class: "conv-count-dot memo",
            text: memoCountText(memoDisplayCount),
            title: memoTitle || ("备忘未消费：" + unreadMemo),
          }));
          hasAny = true;
        }
      }
      return hasAny ? wrap : null;
    }

    function normalizeConversationSort(raw) {
      const s = String(raw || "").trim().toLowerCase();
      if (s === "time_desc" || s === "time_asc" || s === "name_asc" || s === "name_desc") return s;
      return "time_desc";
    }

    function normalizeItemSort(raw) {
      const s = String(raw || "").trim().toLowerCase();
      if (s === "time_desc" || s === "time_asc" || s === "name_asc" || s === "name_desc") return s;
      return "time_desc";
    }

    function itemSortName(it) {
      const title = shortTitle((it && it.title) || "");
      if (title) return title;
      const path = String((it && it.path) || "");
      const seg = path.split("/").pop() || path;
      return String(seg || "").replace(/\.md$/i, "");
    }

    function itemSortTime(it) {
      return Math.max(toTimeNum(it && it.updated_at), 0);
    }

    function compareListItem(a, b, mode) {
      const nameA = itemSortName(a);
      const nameB = itemSortName(b);
      const ta = itemSortTime(a);
      const tb = itemSortTime(b);
      if (mode === "time_asc") {
        if (ta !== tb) return ta - tb;
        return nameA.localeCompare(nameB, "zh-Hans-CN");
      }
      if (mode === "name_asc") {
        const byName = nameA.localeCompare(nameB, "zh-Hans-CN");
        if (byName !== 0) return byName;
        return tb - ta;
      }
      if (mode === "name_desc") {
        const byName = nameB.localeCompare(nameA, "zh-Hans-CN");
        if (byName !== 0) return byName;
        return tb - ta;
      }
      if (ta !== tb) return tb - ta;
      return nameA.localeCompare(nameB, "zh-Hans-CN");
    }

    function sortListItems(items) {
      const mode = normalizeItemSort(STATE && STATE.itemSort);
      return (Array.isArray(items) ? items : []).slice().sort((a, b) => compareListItem(a, b, mode));
    }

    function setItemSort(mode) {
      const next = normalizeItemSort(mode);
      if (next === STATE.itemSort) return;
      STATE.itemSort = next;
      try { localStorage.setItem("taskDashboard.itemSort", next); } catch (_) {}
      render();
    }

    function conversationAgentName(session) {
      const s = (session && typeof session === "object") ? session : {};
      const resolved = typeof resolveAgentDisplayName === "function"
        ? String(resolveAgentDisplayName(s) || "").trim()
        : "";
      if (resolved) return resolved;
      if (typeof readAgentDisplayContract === "function" && typeof agentNameStateLabel === "function") {
        const contract = readAgentDisplayContract(s);
        const stateLabel = agentNameStateLabel(contract.state, contract.issue);
        if (stateLabel) return stateLabel;
      }
      const displayNameSource = String(firstNonEmptyText([
        s.displayNameSource,
        s.display_name_source,
      ]) || "").trim().toLowerCase();
      const displayName = String(firstNonEmptyText([
        s.displayName,
        s.display_name,
        s.alias,
      ]) || "").trim();
      const sessionDerived = typeof isSessionDerivedAgentDisplayName === "function"
        ? isSessionDerivedAgentDisplayName(displayName, s)
        : (displayNameSource === "explicit_sid_fallback");
      if (displayNameSource === "explicit_sid_fallback" || sessionDerived) {
        if (typeof readAgentDisplayContract === "function" && typeof agentNameStateLabel === "function") {
          return "身份未解析";
        }
        const channelName = String(getSessionChannelName(s) || s.channel_name || s.primaryChannel || "").trim();
        return channelName || "身份未解析";
      }
      const fallbackName = typeof fallbackAgentIdentityName === "function"
        ? String(fallbackAgentIdentityName(s) || "").trim()
        : "";
      if (fallbackName) return fallbackName;
      return "未命名会话";
    }

    function conversationDisplayName(session) {
      return conversationAgentName(session);
    }

    function conversationSortTime(session) {
      return Math.max(
        toTimeNum(session && session.lastActiveAt),
        toTimeNum(session && session.last_used_at),
        toTimeNum(session && session.created_at),
        0
      );
    }

    function compareConversationSession(a, b, mode) {
      const nameA = conversationDisplayName(a);
      const nameB = conversationDisplayName(b);
      const ta = conversationSortTime(a);
      const tb = conversationSortTime(b);
      if (mode === "time_asc") {
        if (ta !== tb) return ta - tb;
        return nameA.localeCompare(nameB, "zh-Hans-CN");
      }
      if (mode === "name_asc") {
        const byName = nameA.localeCompare(nameB, "zh-Hans-CN");
        if (byName !== 0) return byName;
        return tb - ta;
      }
      if (mode === "name_desc") {
        const byName = nameB.localeCompare(nameA, "zh-Hans-CN");
        if (byName !== 0) return byName;
        return tb - ta;
      }
      if (ta !== tb) return tb - ta;
      return nameA.localeCompare(nameB, "zh-Hans-CN");
    }

    function sortedConversationSessions(list) {
      const mode = normalizeConversationSort(STATE && STATE.convSort);
      return (Array.isArray(list) ? list : []).slice().sort((a, b) => compareConversationSession(a, b, mode));
    }

    function setConversationSort(mode) {
      const next = normalizeConversationSort(mode);
      if (next === STATE.convSort) return;
      STATE.convSort = next;
      try { localStorage.setItem("taskDashboard.convSort", next); } catch (_) {}
      buildConversationLeftList();
      buildConversationMainList(document.getElementById("fileList"));
    }

    function normalizeConversationListLayout(raw) {
      const s = String(raw || "").trim().toLowerCase();
      if (s === "flat" || s === "channel") return s;
      return "flat";
    }

    function setConversationListLayout(mode) {
      const next = normalizeConversationListLayout(mode);
      if (next === STATE.convListLayout) return;
      STATE.convListLayout = next;
      try { localStorage.setItem("taskDashboard.convListLayout", next); } catch (_) {}
      try { setHash(); } catch (_) {}
      buildConversationLeftList();
    }

    function groupedConversationSessionsByChannel(sessions) {
      const rows = Array.isArray(sessions) ? sessions : [];
      const map = new Map();
      rows.forEach((s) => {
        const channelName = String(getSessionChannelName(s) || "").trim() || "未命名通道";
        if (!map.has(channelName)) map.set(channelName, []);
        map.get(channelName).push(s);
      });
      const out = Array.from(map.entries()).map(([channelName, items]) => ({
        channelName,
        sessions: sortedConversationSessions(items),
      }));
      out.sort((a, b) => String(a.channelName || "").localeCompare(String(b.channelName || ""), "zh-Hans-CN"));
      return out;
    }

    function buildMentionTargetFromSession(session, projectId = "") {
      const sid = getSessionId(session);
      const channelName = firstNonEmptyText([
        getSessionChannelName(session),
        session && session.channelName,
        session && session.primaryChannel,
      ]);
      if (!sid || !channelName) return null;
      const pid = String(projectId || STATE.project || "").trim();
      return normalizeMentionTargetItem({
        project_id: pid,
        channel_name: channelName,
        session_id: sid,
        cli_type: firstNonEmptyText([session && session.cli_type, "codex"]),
        display_name: conversationDisplayName(session),
      });
    }

    function bindConversationMentionDragSource(node, session, projectId = "") {
      if (!node || !session) return;
      const target = buildMentionTargetFromSession(session, projectId);
      if (!target) return;
      node.setAttribute("draggable", "true");
      node.classList.add("mention-drag-source");
      node.addEventListener("dragstart", (e) => {
        try {
          const payload = JSON.stringify(target);
          if (e && e.dataTransfer) {
            e.dataTransfer.setData(CONV_MENTION_DND_MIME, payload);
            e.dataTransfer.setData("text/plain", "@" + String(target.display_name || target.channel_name || "协同对象"));
            e.dataTransfer.effectAllowed = "copy";
          }
          node.classList.add("is-dragging");
        } catch (_) {}
      });
      node.addEventListener("dragend", () => {
        node.classList.remove("is-dragging");
      });
    }

    function normalizeQueuedForwardPayload(raw) {
      if (!raw || typeof raw !== "object") return null;
      const runId = String(raw.runId || raw.run_id || "").trim();
      const sourceSessionId = String(raw.sourceSessionId || raw.source_session_id || "").trim();
      const sourceChannelName = String(raw.sourceChannelName || raw.source_channel_name || "").trim();
      const sourceDisplayName = String(raw.sourceDisplayName || raw.source_display_name || sourceChannelName || "").trim();
      const sourceCliType = String(raw.sourceCliType || raw.source_cli_type || "codex").trim() || "codex";
      const message = String(raw.message || raw.text || "").trim();
      if (!runId || !sourceSessionId || !sourceChannelName) return null;
      return {
        runId,
        sourceSessionId,
        sourceChannelName,
        sourceDisplayName,
        sourceCliType,
        message,
      };
    }

    function queuedForwardPayloadFromDataTransfer(dataTransfer) {
      if (!dataTransfer || typeof dataTransfer.getData !== "function") return null;
      const raw = String(dataTransfer.getData(CONV_QUEUE_FORWARD_DND_MIME) || "").trim();
      if (!raw) return null;
      try {
        return normalizeQueuedForwardPayload(JSON.parse(raw));
      } catch (_) {
        return null;
      }
    }

    function clearQueuedForwardDropHighlight() {
      document.querySelectorAll(".forward-drop-active").forEach((node) => node.classList.remove("forward-drop-active"));
    }

    function setQueuedForwardDragPayload(payload) {
      const next = normalizeQueuedForwardPayload(payload);
      if (!next) return;
      PCONV.queueForwardDrag.active = true;
      PCONV.queueForwardDrag.payload = next;
      try { document.body.classList.add("queued-forward-drag-active"); } catch (_) {}
    }

    function clearQueuedForwardDragPayload() {
      PCONV.queueForwardDrag.active = false;
      PCONV.queueForwardDrag.payload = null;
      clearQueuedForwardDropHighlight();
      try { document.body.classList.remove("queued-forward-drag-active"); } catch (_) {}
    }

    function queuedForwardSourceText(payload) {
      const p = normalizeQueuedForwardPayload(payload);
      if (!p) return "";
      const parts = [];
      if (p.sourceDisplayName) parts.push(p.sourceDisplayName);
      if (p.sourceSessionId) parts.push(shortId(p.sourceSessionId));
      if (p.runId) parts.push(shortId(p.runId));
      return parts.join(" / ");
    }

    function queuedForwardDefaultMessage(payload) {
      const p = normalizeQueuedForwardPayload(payload);
      if (!p) return "";
      const source = queuedForwardSourceText(p);
      const head = "[转发来源: " + (source || "未知来源") + "]";
      const body = String(p.message || "").trim();
      return body ? (head + "\n" + body) : head;
    }

    function bindQueuedForwardDragSource(node, payload, opts = {}) {
      const sourceNode = node || null;
      const normalizedPayload = normalizeQueuedForwardPayload(payload);
      if (!sourceNode || !normalizedPayload) return false;
      sourceNode.setAttribute("draggable", "true");
      sourceNode.classList.add("forward-drag-source");
      sourceNode.title = firstNonEmptyText([
        opts && opts.title,
        "将该排队消息拖拽到左侧目标会话可转发",
      ]) || "将该排队消息拖拽到左侧目标会话可转发";
      sourceNode.addEventListener("dragstart", (e) => {
        if (!e.dataTransfer) return;
        try {
          const text = queuedForwardDefaultMessage(normalizedPayload);
          e.dataTransfer.setData(CONV_QUEUE_FORWARD_DND_MIME, JSON.stringify(normalizedPayload));
          if (text) e.dataTransfer.setData("text/plain", text);
          e.dataTransfer.effectAllowed = "move";
        } catch (_) {}
        setQueuedForwardDragPayload(normalizedPayload);
        sourceNode.classList.add("is-dragging");
      });
      sourceNode.addEventListener("dragend", () => {
        sourceNode.classList.remove("is-dragging");
        clearQueuedForwardDragPayload();
      });
      return true;
    }

    function buildQueueForwardTargetSession(session, projectId = "") {
      if (!session) return null;
      const sid = getSessionId(session);
      const channelName = String(getSessionChannelName(session) || "").trim();
      const pid = String(projectId || STATE.project || "").trim();
      if (!pid || !sid || !channelName || pid === "overview") return null;
      return {
        projectId: pid,
        sessionId: sid,
        channelName: channelName,
        cliType: String(session.cli_type || "codex").trim() || "codex",
        displayName: conversationDisplayName(session),
      };
    }

    function markQueuedForwardDropHandled(node) {
      if (!node || typeof node.setAttribute !== "function") return;
      node.setAttribute("data-queued-forward-drop-ts", String(Date.now()));
    }

    function consumeQueuedForwardDropHandled(node) {
      if (!node || typeof node.getAttribute !== "function") return false;
      const ts = Number(node.getAttribute("data-queued-forward-drop-ts") || 0);
      if (!ts) return false;
      node.removeAttribute("data-queued-forward-drop-ts");
      return (Date.now() - ts) < 600;
    }

    function queueForwardMaskNode() {
      return document.getElementById("queueForwardMask");
    }

    function queueForwardSourceNode() {
      return document.getElementById("queueForwardSource");
    }

    function queueForwardTargetNode() {
      return document.getElementById("queueForwardTarget");
    }

    function queueForwardTextareaNode() {
      return document.getElementById("queueForwardTextarea");
    }

    function queueForwardHintNode() {
      return document.getElementById("queueForwardHint");
    }

    function queueForwardConfirmBtnNode() {
      return document.getElementById("queueForwardConfirmBtn");
    }

    function queueForwardCancelBtnNode() {
      return document.getElementById("queueForwardCancelBtn");
    }

    function ensureQueueForwardModalDom() {
      if (queueForwardMaskNode()) return;
      const mask = document.createElement("div");
      mask.className = "bmask";
      mask.id = "queueForwardMask";
      mask.setAttribute("role", "dialog");
      mask.setAttribute("aria-modal", "true");
      mask.setAttribute("aria-label", "排队消息拖拽转发确认");
      mask.innerHTML = [
        '<div class="bmodal queue-forward-modal">',
        '  <div class="bmodalh">',
        '    <div class="t">转发排队消息</div>',
        '    <div class="s">先撤回来源 queued，再发送到目标会话</div>',
        "  </div>",
        '  <div class="bmodalb queue-forward-body">',
        '    <div class="queue-forward-meta">',
        '      <div class="queue-forward-line"><span class="k">来源</span><span class="v" id="queueForwardSource">-</span></div>',
        '      <div class="queue-forward-line"><span class="k">目标</span><span class="v" id="queueForwardTarget">-</span></div>',
        "    </div>",
        '    <label for="queueForwardTextarea">转发消息（可二次编辑）</label>',
        '    <textarea class="input nctextarea queue-forward-textarea" id="queueForwardTextarea" placeholder="请输入要转发的消息内容"></textarea>',
        '    <div class="queue-forward-hint" id="queueForwardHint"></div>',
        "  </div>",
        '  <div class="bmodalf">',
        '    <button class="btn" id="queueForwardCancelBtn" type="button">取消</button>',
        '    <button class="btn primary" id="queueForwardConfirmBtn" type="button">确认转发</button>',
        "  </div>",
        "</div>",
      ].join("");
      document.body.appendChild(mask);
      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeQueueForwardModal();
      });
      const cancelBtn = queueForwardCancelBtnNode();
      if (cancelBtn) cancelBtn.addEventListener("click", () => closeQueueForwardModal());
      const confirmBtn = queueForwardConfirmBtnNode();
      if (confirmBtn) confirmBtn.addEventListener("click", () => confirmQueueForwardTransfer());
      const textarea = queueForwardTextareaNode();
      if (textarea) {
        textarea.addEventListener("input", () => {
          PCONV.queueForwardModal.userEdited = true;
        });
      }
    }

    function setQueueForwardModalHint(text, tone = "muted") {
      const hint = queueForwardHintNode();
      if (!hint) return;
      hint.className = "queue-forward-hint " + String(tone || "muted");
      hint.textContent = String(text || "");
    }

    function setQueueForwardModalBusy(busy) {
      const isBusy = !!busy;
      PCONV.queueForwardModal.busy = isBusy;
      const confirmBtn = queueForwardConfirmBtnNode();
      const cancelBtn = queueForwardCancelBtnNode();
      const textarea = queueForwardTextareaNode();
      if (confirmBtn) {
        confirmBtn.disabled = isBusy;
        confirmBtn.textContent = isBusy ? "转发中..." : "确认转发";
      }
      if (cancelBtn) cancelBtn.disabled = isBusy;
      if (textarea) textarea.disabled = isBusy;
    }

    function closeQueueForwardModal() {
      const mask = queueForwardMaskNode();
      if (mask) mask.classList.remove("show");
      PCONV.queueForwardModal.open = false;
      PCONV.queueForwardModal.busy = false;
      PCONV.queueForwardModal.payload = null;
      PCONV.queueForwardModal.target = null;
      PCONV.queueForwardModal.userEdited = false;
      PCONV.queueForwardModal.loadToken = Number(PCONV.queueForwardModal.loadToken || 0) + 1;
      const textarea = queueForwardTextareaNode();
      if (textarea) {
        textarea.value = "";
        textarea.disabled = false;
      }
      setQueueForwardModalHint("", "muted");
      setQueueForwardModalBusy(false);
    }

    async function confirmQueueForwardTransfer() {
      const state = PCONV.queueForwardModal || {};
      const payload = normalizeQueuedForwardPayload(state.payload);
      const target = state.target && typeof state.target === "object" ? state.target : null;
      const textarea = queueForwardTextareaNode();
      if (!payload || !target || !textarea) return;
      const message = String(textarea.value || "").trim();
      if (!message) {
        setQueueForwardModalHint("请输入转发消息内容。", "bad");
        return;
      }
      if (state.busy) return;
      setQueueForwardModalHint("正在执行转发…", "warn");
      setQueueForwardModalBusy(true);
      let sourceCanceled = false;
      try {
        await callRunAction(payload.runId, "cancel_edit");
        sourceCanceled = true;
        const r = await fetch("/api/codex/announce", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            projectId: target.projectId,
            channelName: target.channelName,
            sessionId: target.sessionId,
            cliType: target.cliType || "codex",
            message,
            ...buildUiUserSenderFields(),
          }),
        });
        if (!r.ok) {
          const detail = await parseResponseDetail(r);
          const tok = getToken();
          if ((r.status === 401 || r.status === 403) && !tok) {
            throw new Error("发送失败：服务启用了 Token 校验，请先设置 Token。");
          }
          throw new Error(detail || ("HTTP " + r.status));
        }
        const resp = await r.json().catch(() => ({}));
        const runId = resp && resp.run ? String(resp.run.id || "") : "";
        closeQueueForwardModal();
        markSessionPending(target.sessionId, message);
        if (STATE.panelMode === "conv") buildConversationLeftList();
        setHintText("conv", "已转发到 " + String(target.displayName || target.channelName || "目标会话") + "。");
        await refreshConversationPanel();
        if (runId) scheduleConversationPoll(5000);
      } catch (err) {
        const msg = String((err && err.message) || err || "未知错误");
        const hint = sourceCanceled
          ? ("转发发送失败：" + msg + "。来源 queued 已撤回，可直接重试。")
          : ("撤回来源 queued 失败：" + msg);
        setQueueForwardModalHint(hint, "bad");
        setHintText("conv", hint);
      } finally {
        setQueueForwardModalBusy(false);
      }
    }

    function openQueueForwardModal(payload, targetSession) {
      const normalizedPayload = normalizeQueuedForwardPayload(payload);
      if (!normalizedPayload) return;
      const target = targetSession && typeof targetSession === "object" ? targetSession : null;
      if (!target || !target.projectId || !target.sessionId || !target.channelName) {
        setHintText("conv", "目标会话缺少路由信息，无法转发。");
        return;
      }
      ensureQueueForwardModalDom();
      const state = PCONV.queueForwardModal;
      state.open = true;
      state.payload = Object.assign({}, normalizedPayload);
      state.target = Object.assign({}, target);
      state.userEdited = false;
      state.loadToken = Number(state.loadToken || 0) + 1;
      const loadToken = state.loadToken;
      const sourceNode = queueForwardSourceNode();
      const targetNode = queueForwardTargetNode();
      const textarea = queueForwardTextareaNode();
      if (sourceNode) sourceNode.textContent = queuedForwardSourceText(normalizedPayload) || "-";
      if (targetNode) {
        targetNode.textContent = String(target.displayName || target.channelName || "目标会话") + " / " + shortId(target.sessionId);
      }
      if (textarea) {
        textarea.value = queuedForwardDefaultMessage(normalizedPayload);
      }
      setQueueForwardModalHint("确认后将先撤回来源 queued，再向目标会话发送。", "muted");
      setQueueForwardModalBusy(false);
      const mask = queueForwardMaskNode();
      if (mask) mask.classList.add("show");
      if (textarea) {
        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      }
      loadRun(normalizedPayload.runId).then((full) => {
        const latestState = PCONV.queueForwardModal || {};
        if (!latestState.open || Number(latestState.loadToken || 0) !== loadToken) return;
        const fullMsg = String((full && full.message) || "").trim();
        if (!fullMsg) return;
        latestState.payload = Object.assign({}, latestState.payload || {}, { message: fullMsg });
        if (!latestState.userEdited) {
          const nextText = queuedForwardDefaultMessage(latestState.payload);
          const nextArea = queueForwardTextareaNode();
          if (nextArea) nextArea.value = nextText;
        }
      }).catch(() => {});
    }

    function bindQueuedForwardDropTarget(node, session, projectId = "") {
      if (!node || !session) return;
      const target = buildQueueForwardTargetSession(session, projectId);
      if (!target) return;
      node.addEventListener("dragenter", (e) => {
        const payload = queuedForwardPayloadFromDataTransfer(e && e.dataTransfer) || normalizeQueuedForwardPayload(PCONV.queueForwardDrag.payload);
        if (!payload) return;
        if (String(payload.sourceSessionId || "") === String(target.sessionId || "")) return;
        e.preventDefault();
        node.classList.add("forward-drop-active");
      });
      node.addEventListener("dragover", (e) => {
        const payload = queuedForwardPayloadFromDataTransfer(e && e.dataTransfer) || normalizeQueuedForwardPayload(PCONV.queueForwardDrag.payload);
        if (!payload) return;
        if (String(payload.sourceSessionId || "") === String(target.sessionId || "")) return;
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
        node.classList.add("forward-drop-active");
      });
      node.addEventListener("dragleave", (e) => {
        const current = e.currentTarget;
        const related = e.relatedTarget;
        if (current && related && current.contains && current.contains(related)) return;
        node.classList.remove("forward-drop-active");
      });
      node.addEventListener("drop", (e) => {
        const payload = queuedForwardPayloadFromDataTransfer(e && e.dataTransfer) || normalizeQueuedForwardPayload(PCONV.queueForwardDrag.payload);
        if (!payload) return;
        e.preventDefault();
        e.stopPropagation();
        markQueuedForwardDropHandled(node);
        clearQueuedForwardDragPayload();
        if (String(payload.sourceSessionId || "") === String(target.sessionId || "")) {
          setHintText("conv", "目标会话与来源会话相同，未执行转发。");
          return;
        }
        openQueueForwardModal(payload, target);
      });
    }

    function buildConversationRow(session, isActive, onSelect, opts = {}) {
      if (isConversationPendingCreateSession(session)) {
        return buildConversationPendingCreateRow(session, (opts && opts.projectId) || STATE.project || "");
      }
      const sid = getSessionId(session);
      const showCountDots = !!(opts && opts.showCountDots);
      const projectId = String((opts && opts.projectId) || STATE.project || "").trim();
      const displayName = conversationAgentName(session);
      const previewText = conversationPreviewLine(session);
      const previewLine = String(previewText || "").trim() || "暂无消息记录";
      const secondaryParts = conversationSecondaryMeta(session);
      const statusMeta = conversationStatusMeta(session);
      const heatMeta = conversationHeatMeta(session);
      const statusBadge = statusMeta && statusMeta.text
        ? el("span", {
            class: "conv-status-badge " + String(statusMeta.tone || "idle"),
            text: statusMeta.text,
            title: statusMeta.title || "",
          })
        : null;
      const countBadges = buildConversationCountBadges(session, {
        projectId,
        showUnread: showCountDots,
      });
      const row = el("div", {
        class: "rowbtn conv-row"
          + (isActive ? " active" : "")
          + (heatMeta && heatMeta.tier ? (" is-heat-" + String(heatMeta.tier || "")) : "")
          + (statusMeta && statusMeta.tone ? (" is-status-" + String(statusMeta.tone || "")) : ""),
        role: "button",
        tabindex: "0",
      });
      if (heatMeta && heatMeta.tier) {
        row.appendChild(el("span", {
          class: "conv-heat-wash heat-" + String(heatMeta.tier || ""),
          "aria-hidden": "true",
        }));
      }
      row.appendChild(buildConversationAvatarNode(session));

      const mainDiv = el("div", { class: "conv-main" });
      const headRow = el("div", { class: "conv-card-head" });
      const titleWrap = el("div", { class: "conv-card-titlewrap" });
      const titleRow = el("div", { class: "conv-title" });
      titleRow.appendChild(el("span", { class: "conv-name", text: displayName, title: displayName }));
      titleWrap.appendChild(titleRow);
      const contextStatusBadge = buildConversationContextStatusBadge(session, { compact: true });
      const execSourceChip = buildProjectExecutionContextCompactChip(
        session && (session.project_execution_context || session.projectExecutionContext || null)
      );
      const heartbeatBadge = buildConversationHeartbeatBadges(session);
      let metaRow = null;
      if (secondaryParts.length || heartbeatBadge || contextStatusBadge || execSourceChip) {
        metaRow = el("div", { class: "conv-card-submeta" });
        metaRow.appendChild(buildConversationRoleBadge(session));
        metaRow.appendChild(buildConversationCliBadge(session));
        if (contextStatusBadge) metaRow.appendChild(contextStatusBadge);
        if (execSourceChip) metaRow.appendChild(execSourceChip);
        secondaryParts.forEach((part) => {
          metaRow.appendChild(el("span", {
            class: "conv-subchip " + String((part && part.kind) || "").trim(),
            text: String((part && part.text) || "").trim(),
          }));
        });
        if (heartbeatBadge) metaRow.appendChild(heartbeatBadge);
      }
      headRow.appendChild(titleWrap);
      const headSide = el("div", { class: "conv-card-side" });
      if (statusBadge) headSide.appendChild(statusBadge);
      headRow.appendChild(headSide);
      if (metaRow) headRow.appendChild(metaRow);
      mainDiv.appendChild(headRow);

      const footRow = el("div", { class: "conv-card-foot" });
      const previewMeta = el("div", { class: "conv-preview-meta" });
      if (session && session.lastActiveAt) {
        previewMeta.appendChild(el("span", { class: "conv-time", text: compactDateTime(session.lastActiveAt) }));
      }
      previewMeta.appendChild(el("div", { class: "conv-preview", text: previewLine, title: previewLine }));
      footRow.appendChild(previewMeta);
      if (countBadges) footRow.appendChild(countBadges);
      mainDiv.appendChild(footRow);

      row.appendChild(mainDiv);

      const moreBtn = el("button", {
        class: "conv-row-menu-btn",
        type: "button",
        text: "⋯",
        title: "会话信息",
        "aria-label": "会话信息",
      });
      moreBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openConversationSessionInfoModal(session, projectId);
      });
      headSide.appendChild(moreBtn);

      bindConversationMentionDragSource(row, session, projectId);
      bindQueuedForwardDropTarget(row, session, projectId);
      row.addEventListener("click", () => {
        if (consumeQueuedForwardDropHandled(row)) return;
        onSelect && onSelect(sid);
      });
      row.addEventListener("keydown", (e) => {
        if (!e) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (consumeQueuedForwardDropHandled(row)) return;
          onSelect && onSelect(sid);
        }
      });
      return row;
    }

    function markSessionPending(sessionId, message) {
      const sid = String(sessionId || "").trim();
      if (!sid) return;
      const now = new Date().toISOString();
      for (const s of (Array.isArray(PCONV.sessions) ? PCONV.sessions : [])) {
        const cur = getSessionId(s);
        if (cur !== sid) continue;
        const projectId = String((s && s.project_id) || STATE.project || "").trim();
        s.lastStatus = "queued";
        s.lastTimeout = false;
        s.lastError = "";
        s.lastErrorHint = "";
        s.lastActiveAt = now;
        s.session_display_state = "queued";
        const runtimeState = (s.runtime_state && typeof s.runtime_state === "object")
          ? { ...s.runtime_state }
          : {};
        runtimeState.display_state = "queued";
        runtimeState.queue_depth = Math.max(1, Number(runtimeState.queue_depth || 0) || 0);
        runtimeState.updated_at = String(runtimeState.updated_at || now);
        s.runtime_state = runtimeState;
        const latestRunSummary = (s.latest_run_summary && typeof s.latest_run_summary === "object")
          ? { ...s.latest_run_summary }
          : {};
        latestRunSummary.status = "queued";
        latestRunSummary.display_state = "queued";
        latestRunSummary.updated_at = String(latestRunSummary.updated_at || now);
        const msg = String(message || "").trim();
        if (msg) {
          // 保持左侧预览为“稳定反馈态”，避免排队阶段误判为已处理结果。
          s.latestUserMsg = msg;
          latestRunSummary.latest_user_msg = msg;
        }
        s.latest_run_summary = latestRunSummary;
        if (typeof conversationStoreUpsertSession === "function") {
          conversationStoreUpsertSession(s, {
            projectId,
            sessionId: sid,
            source: "local-pending",
          });
        }
      }
    }

    function chipLink(label, url) {
      const u = String(url || "");
      const b = el("button", { class: "chip link", text: String(label || "链接"), title: u || "" });
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        if (isHttpUrl(u)) openNew(u);
        else if (u) copyText(u);
      });
      return b;
    }

    // 任务状态选择器
    const TASK_STATUSES = ["待处理", "待开始", "进行中", "待验收", "已完成", "已验收通过", "暂缓"];
    let STATUS_SELECTOR_OUTSIDE_BOUND = false;

    function ensureStatusSelectorOutsideClose() {
      if (STATUS_SELECTOR_OUTSIDE_BOUND) return;
      STATUS_SELECTOR_OUTSIDE_BOUND = true;
      document.addEventListener("click", (e) => {
        const t = e && e.target;
        if (t && t.closest && t.closest(".status-selector")) return;
        document.querySelectorAll(".status-selector.show").forEach((node) => {
          node.classList.remove("show");
        });
      });
    }

    function createStatusSelector(currentStatus, taskPath, onStatusChanged) {
      ensureStatusSelectorOutsideClose();
      let liveStatus = String(currentStatus || "");
      const wrap = el("div", { class: "status-selector" });
      const btn = el("button", { class: "status-btn", "data-status": liveStatus, type: "button" });
      btn.innerHTML = `
        <span>${liveStatus || "状态"}</span>
        <svg viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      `;

      const dropdown = el("div", { class: "status-dropdown" });
      for (const status of TASK_STATUSES) {
        const opt = el("button", {
          class: "status-option" + (status === liveStatus ? " current" : ""),
          text: status,
          type: "button"
        });
        opt.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (status === liveStatus) {
            wrap.classList.remove("show");
            return;
          }
          // 标记加载状态
          opt.classList.add("loading");
          btn.disabled = true;

          try {
            const result = await changeTaskStatus(taskPath, status);
            if (!result || !result.ok) {
              throw new Error("状态更新未成功");
            }
            applyTaskStatusChangeLocal(result, status);
            rebuildDashboardAfterStatusChange();
            liveStatus = status;
            wrap.classList.remove("show");
            // 更新按钮显示
            btn.querySelector("span").textContent = status;
            btn.setAttribute("data-status", status);
            // 更新下拉选项
            dropdown.querySelectorAll(".status-option").forEach(o => {
              o.classList.toggle("current", o.textContent === status);
            });
            // 回调
            if (onStatusChanged) onStatusChanged(result);
          } catch (err) {
            console.error("Failed to change status:", err);
            alert("修改状态失败: " + err.message);
          } finally {
            opt.classList.remove("loading");
            btn.disabled = false;
          }
        });
        dropdown.appendChild(opt);
      }

      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        // 关闭其他选择器
        document.querySelectorAll(".status-selector.show").forEach(s => {
          if (s !== wrap) s.classList.remove("show");
        });
        wrap.classList.toggle("show");
      });

      wrap.appendChild(btn);
      wrap.appendChild(dropdown);
      return wrap;
    }

    function applyTaskStatusChangeLocal(result, newStatus) {
      const oldPath = String((result && result.old_path) || "").trim();
      const newPath = String((result && result.new_path) || oldPath).trim();
      const newFilename = String((result && result.new_filename) || "").trim();
      let changedTaskId = normalizeTaskStableId((result && (result.task_id || result.taskId)) || "");
      const now = new Date().toISOString().slice(0, 19).replace("T", " ");
      const items = allItems();
      let changed = false;
      for (const it of items) {
        const p = String((it && it.path) || "").trim();
        if (!p) continue;
        if (p === oldPath || p === newPath) {
          if (!changedTaskId) changedTaskId = taskStableIdOfItem(it);
          if (newPath) it.path = newPath;
          if (newStatus) it.status = String(newStatus);
          if (newFilename) it.title = newFilename.replace(/\.md$/i, "");
          if (now) it.updated_at = now;
          changed = true;
        }
      }
      // 若当前选中的是同一条任务，自动切到新路径，避免详情丢失。
      const selectedTaskId = normalizeTaskStableId(STATE && STATE.selectedTaskId || "");
      if (STATE && changedTaskId && selectedTaskId === changedTaskId) {
        STATE.selectedTaskId = changedTaskId;
      }
      if (STATE && newPath && (
        String(STATE.selectedPath || "").trim() === oldPath
        || (changedTaskId && selectedTaskId && changedTaskId === selectedTaskId)
      )) {
        STATE.selectedPath = newPath;
        syncSelectedTaskSelectionStorage();
      }
      return changed;
    }

    function rebuildDashboardAfterStatusChange() {
      // 后台重建静态看板，确保手动刷新页面后状态一致。
      fetch("/api/dashboard/rebuild", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ reason: "task_status_changed" }),
      }).catch(() => {});
    }

    function summarizeTaskStatusGateFailure(gate) {
      const src = (gate && typeof gate === "object") ? gate : {};
      const rules = Array.isArray(src.rules) ? src.rules : [];
      const failed = rules
        .filter((rule) => rule && rule.passed === false)
        .map((rule) => String(rule.detail || rule.label || "").trim())
        .filter(Boolean);
      return String(src.summary || failed.join("；") || "任务状态软门禁未通过");
    }

    async function changeTaskStatus(taskPath, newStatus, opts = {}) {
      const force = !!(opts && opts.force);
      const r = await fetch("/api/tasks/status", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ path: taskPath, status: newStatus, force })
      });
      if (!r.ok) {
        let payload = null;
        try { payload = await r.json(); } catch (_) {}
        const gate = payload && payload.gate && typeof payload.gate === "object" ? payload.gate : null;
        if (r.status === 409 && gate && gate.force_allowed && !force) {
          const message = summarizeTaskStatusGateFailure(gate);
          const confirmed = window.confirm(message + "\n\n是否强制继续推进到“" + newStatus + "”？");
          if (confirmed) return await changeTaskStatus(taskPath, newStatus, { force: true });
        }
        const detail = String((payload && (payload.error || payload.message)) || r.statusText || "").trim();
        throw new Error(detail || "Request failed");
      }
      return await r.json();
    }

    // 解析任务文件名中的状态标签
    function parseStatusFromTitle(title) {
      const m = String(title || "").match(/^【([^】]+)】/);
      if (m && TASK_STATUSES.includes(m[1])) {
        return m[1];
      }
      // 尝试从 status 字段推断
      return null;
    }

    function explicitProjectIdFromHash() {
      try {
        const h = String(location.hash || "").replace(/^#/, "");
        const params = new URLSearchParams(h || "");
        return String(params.get("p") || "").trim();
      } catch (_) {
        return "";
      }
    }

    function resolveImplicitProjectPageId() {
      const pid = explicitProjectIdFromHash();
      if (!pid) return "";
      return (DATA.projects || []).some((item) => String(item && item.id || "") === pid) ? "" : pid;
    }

    function buildImplicitProjectPage(id) {
      const pid = String(id || "").trim();
      if (!pid) return null;
      return { id: pid, name: pid, color: "#2f6fed", implicit: true };
    }

    function pages() {
      const out = [];
      for (const p of (DATA.projects || [])) out.push({ id: p.id, name: p.name, color: p.color || "#2f6fed" });
      const implicit = buildImplicitProjectPage(resolveImplicitProjectPageId());
      if (implicit && !out.some((item) => item.id === implicit.id)) out.push(implicit);
      return out;
    }

    function projectById(id) {
      return pages().find(x => x.id === id) || null;
    }

    const ITEM_INDEX = {
      ready: false,
      all: [],
      byProject: new Map(),
      loadedProjects: new Set(),
      loadingByProject: new Map(),
      loadErrors: new Map(),
      overviewLoaded: false,
      overviewLoading: null,
    };

    function rebuildItemIndexAll() {
      if (ITEM_INDEX.overviewLoaded) return;
      const all = [];
      for (const rows of ITEM_INDEX.byProject.values()) {
        if (Array.isArray(rows) && rows.length) all.push(...rows);
      }
      ITEM_INDEX.all = all;
    }

    function setProjectItems(projectId, items) {
      const pid = String(projectId || "").trim();
      if (!pid) return;
      const rows = Array.isArray(items) ? items : [];
      ITEM_INDEX.byProject.set(pid, rows);
      ITEM_INDEX.loadedProjects.add(pid);
      ITEM_INDEX.loadErrors.delete(pid);
      rebuildItemIndexAll();
    }

    function setOverviewItems(items) {
      const rows = Array.isArray(items) ? items : [];
      const byProject = new Map();
      for (const it of rows) {
        const pid = String((it && it.project_id) || "").trim();
        if (!byProject.has(pid)) byProject.set(pid, []);
        byProject.get(pid).push(it);
      }
      ITEM_INDEX.all = rows;
      ITEM_INDEX.byProject = byProject;
      ITEM_INDEX.loadedProjects = new Set(Array.from(byProject.keys()).filter(Boolean));
      ITEM_INDEX.loadErrors.delete("overview");
      ITEM_INDEX.overviewLoaded = true;
    }

    function itemBundleUrlForProject(projectId) {
      if (!ITEM_BUNDLE || !ITEM_BUNDLE.projects || typeof ITEM_BUNDLE.projects !== "object") return "";
      const pid = String(projectId || "").trim();
      if (!pid) return "";
      return String(ITEM_BUNDLE.projects[pid] || "").trim();
    }

    function itemBundleUrlForOverview() {
      return ITEM_BUNDLE ? String(ITEM_BUNDLE.overview || "").trim() : "";
    }

    async function fetchItemsBundle(url) {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error("items_bundle_http_" + r.status);
      const payload = await r.json();
      return Array.isArray(payload && payload.items) ? payload.items : [];
    }

    function ensureProjectItemsLoaded(projectId) {
      ensureItemIndex();
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return;
      if (ITEM_INDEX.loadedProjects.has(pid) || ITEM_INDEX.loadingByProject.has(pid)) return;
      const url = itemBundleUrlForProject(pid);
      if (!url) {
        setProjectItems(pid, []);
        return;
      }
      const promise = fetchItemsBundle(url)
        .then((items) => {
          setProjectItems(pid, items);
        })
        .catch((err) => {
          ITEM_INDEX.loadErrors.set(pid, String((err && err.message) || err || "load_failed"));
        })
        .finally(() => {
          ITEM_INDEX.loadingByProject.delete(pid);
          render();
        });
      ITEM_INDEX.loadingByProject.set(pid, promise);
    }

    function ensureOverviewItemsLoaded() {
      ensureItemIndex();
      if (ITEM_INDEX.overviewLoaded || ITEM_INDEX.overviewLoading) return;
      const url = itemBundleUrlForOverview();
      if (!url) {
        ITEM_INDEX.overviewLoaded = true;
        return;
      }
      ITEM_INDEX.overviewLoading = fetchItemsBundle(url)
        .then((items) => {
          setOverviewItems(items);
        })
        .catch((err) => {
          ITEM_INDEX.loadErrors.set("overview", String((err && err.message) || err || "load_failed"));
        })
        .finally(() => {
          ITEM_INDEX.overviewLoading = null;
          render();
        });
    }

    function ensureItemsLoadedForState(projectId) {
      const pid = String(projectId || (STATE && STATE.project) || "").trim();
      if (!pid) return;
      if (pid === "overview") {
        ensureOverviewItemsLoaded();
        return;
      }
      ensureProjectItemsLoaded(pid);
    }

    function isProjectItemsLoading(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return false;
      if (pid === "overview") return !!ITEM_INDEX.overviewLoading;
      return ITEM_INDEX.loadingByProject.has(pid);
    }

    function itemLoadErrorForProject(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return "";
      return String(ITEM_INDEX.loadErrors.get(pid) || "").trim();
    }

    function ensureItemIndex() {
      if (ITEM_INDEX.ready) return;
      const all = Array.isArray(DATA.items) ? DATA.items : [];
      const byProject = new Map();
      for (const it of all) {
        const pid = String((it && it.project_id) || "").trim();
        if (!byProject.has(pid)) byProject.set(pid, []);
        byProject.get(pid).push(it);
      }
      ITEM_INDEX.all = all;
      ITEM_INDEX.byProject = byProject;
      ITEM_INDEX.loadedProjects = new Set(Array.from(byProject.keys()).filter(Boolean));
      ITEM_INDEX.overviewLoaded = all.length > 0 || !ITEM_BUNDLE;
      ITEM_INDEX.ready = true;
    }

    function allItems() {
      ensureItemIndex();
      return ITEM_INDEX.all;
    }

    function itemsForProject(projectId) {
      ensureItemIndex();
      if (projectId === "overview") return ITEM_INDEX.all;
      const pid = String(projectId || "").trim();
      return ITEM_INDEX.byProject.get(pid) || [];
    }

    function isDiscussionSpaceItem(it) {
      const p = String((it && it.path) || "");
      if (p.includes("/讨论空间/")) return true;
      return String((it && it.type) || "") === "讨论";
    }

    function matchesQuery(it) {
      const q = String(STATE.q || "").trim().toLowerCase();
      if (!q) return true;
      const hay = (String(it.title || "") + " " + String(it.code || "") + " " + String(it.owner || "") + " " + String(it.path || "")).toLowerCase();
      return hay.includes(q);
    }

    function matchesStatus(it, statusFilter) {
      const f = String(statusFilter || "待办");
      if (f === "全部") return true;
      return taskPrimaryStatus(it) === f;
    }

    function isKnowledgeItem(it) {
      return !!it && !isTaskItem(it);
    }

    function inferKnowledgeGroupLabel(it) {
      const p = String((it && it.path) || "");
      const t = String((it && it.type) || "").trim();
      if (p.includes("/产出物/沉淀/")) return "沉淀";
      if (p.includes("/产出物/材料/")) return "材料";
      if (p.includes("/产出物/证据/")) return "证据";
      if (t === "需求" || p.includes("/需求/")) return "需求";
      if (t === "反馈") return "反馈";
      if (t === "答复") return "答复";
      if (t === "问题") return "问题";
      if (t === "讨论") return "讨论";
      if (t === "文档") return "文档";
      return t || "其他";
    }

    function channelKnowledgeItems(projectId, channelName) {
      if (!projectId || projectId === "overview" || !channelName) return [];
      const list = channelFileItems(projectId, channelName, { applyQuery: true }).slice();
      list.sort((a, b) => {
        const ta = String((a && a.updated_at) || "");
        const tb = String((b && b.updated_at) || "");
        if (ta !== tb) return tb.localeCompare(ta);
        return String((a && a.title) || "").localeCompare(String((b && b.title) || ""), "zh-Hans-CN");
      });
      return list;
    }

    function groupedChannelKnowledge(items) {
      const map = new Map();
      const order = ["沉淀", "材料", "证据", "需求", "反馈", "答复", "问题", "讨论", "文档", "其他"];
      for (const it of (items || [])) {
        const label = inferKnowledgeGroupLabel(it);
        if (!map.has(label)) map.set(label, []);
        map.get(label).push(it);
      }
      const groups = Array.from(map.entries()).map(([label, rows]) => {
        const sortedRows = rows.slice().sort((a, b) => String((b && b.updated_at) || "").localeCompare(String((a && a.updated_at) || "")));
        return {
          label,
          rows: sortedRows,
          latest: sortedRows.length ? String((sortedRows[0] && sortedRows[0].updated_at) || "") : "",
        };
      });
      groups.sort((a, b) => {
        const ia = order.indexOf(a.label);
        const ib = order.indexOf(b.label);
        if (ia !== ib) return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
        return a.label.localeCompare(b.label, "zh-Hans-CN");
      });
      return groups;
    }

    function stripChannelPrefix(path, channelName) {
      const raw = String(path || "");
      const ch = String(channelName || "");
      if (!raw || !ch) return raw;
      const marker = "/" + ch + "/";
      const idx = raw.indexOf(marker);
      if (idx < 0) return raw;
      return raw.slice(idx + marker.length);
    }

    // Content filters (type/status/search) apply ONLY to the main list/detail, not to the left "channel directory" layer.
    function filteredItemsForProject(projectId) {
      let items = itemsForProject(projectId);
      items = items.filter(matchesQuery);
      if (STATE.type && STATE.type !== "全部") items = items.filter(x => x.type === STATE.type);
      items = items.filter(x => matchesStatus(x, STATE.status));
      return items;
    }

    function unionChannelNames(projectId) {
      const s = new Set();
      const proj = projectById(projectId);
      if (proj && Array.isArray(proj.channels)) for (const c of proj.channels) if (c && c.name) s.add(String(c.name));
      if (proj && Array.isArray(proj.channel_sessions)) for (const cs of proj.channel_sessions) if (cs && cs.name) s.add(String(cs.name));
      for (const it of itemsForProject(projectId)) if (it && it.channel) s.add(String(it.channel));
      return Array.from(s).sort((a,b) => a.localeCompare(b, "zh-Hans-CN"));
    }

    function sessionForChannel(projectId, channelName) {
      const proj = projectById(projectId);
      if (!proj) return null;
      const pid = String(projectId || "").trim();
      const isVisibleRow = (row) => {
        const current = (row && typeof row === "object") ? row : {};
        if (typeof isVisibleConversationSession === "function") {
          return isVisibleConversationSession(current);
        }
        const deleted = String(current.is_deleted || current.isDeleted || "").trim().toLowerCase();
        const inactive = String(current.status || current.session_status || current.sessionStatus || "").trim().toLowerCase();
        return !["1", "true", "yes", "y"].includes(deleted) && inactive !== "inactive";
      };
      // bindings 只保留兼容补洞，不再反向覆盖 runtime/store/config 的主链会话信息。
      const local = getBinding(projectId, channelName);
      const list = Array.isArray(proj.channel_sessions) ? proj.channel_sessions : [];
      const runtimeList = (typeof conversationRuntimeSessionsForProject === "function")
        ? conversationRuntimeSessionsForProject(pid)
        : (Array.isArray(PCONV.sessions) ? PCONV.sessions : []);
      const runtimeHit = runtimeList.find((s) => {
        const ch = String((s && (s.channel_name || s.primaryChannel || ((Array.isArray(s.channels) && s.channels[0]) || ""))) || "");
        const sid = String((s && (s.sessionId || s.id || "")) || "").trim();
        return ch === String(channelName) && looksLikeSessionId(sid);
      });
      const hit = list.find((x) => isVisibleRow(x) && String(x.name || "") === String(channelName));
      if (hit) {
        const existingSessionId = String(hit.session_id || hit.sessionId || "").trim();
        if (!existingSessionId && local && local.session_id) {
          return {
            ...hit,
            project_id: pid,
            projectId: pid,
            session_id: local.session_id,
            cli_type: local.cli_type,
            source: "bindings_compat",
          };
        }
        return {
          ...hit,
          project_id: pid,
          projectId: pid,
          cli_type: hit.cli_type || hit.cliType || "codex",
          model: normalizeSessionModel(hit.model),
        };
      }
      if (runtimeHit) {
        const sid = String(runtimeHit.sessionId || runtimeHit.id || "").trim();
        const cli = String(runtimeHit.cli_type || "codex").trim() || "codex";
        const model = normalizeSessionModel(runtimeHit.model);
        const base = {
          name: channelName,
          alias: "",
          project_id: pid,
          projectId: pid,
          session_id: sid,
          desc: "",
          cli_type: cli,
          model,
          source: "runtime",
        };
        return base;
      }
      const cfg = Array.isArray(proj.channels) ? proj.channels : [];
      const hit2 = cfg.find(x => String(x.name || "") === String(channelName));
      if (hit2) {
        const base = {
          name: hit2.name,
          alias: hit2.alias || "",
          project_id: pid,
          projectId: pid,
          session_id: hit2.session_id || "",
          desc: hit2.desc || "",
          cli_type: hit2.cli_type || hit2.cliType || "codex",
          model: normalizeSessionModel(hit2.model),
          source: "config",
        };
        if (!String(base.session_id || "").trim() && local && local.session_id) {
          return { ...base, session_id: local.session_id, cli_type: local.cli_type, source: "bindings_compat" };
        }
        return base;
      }
      const base = {
        name: channelName,
        alias: "",
        project_id: pid,
        projectId: pid,
        session_id: "",
        desc: "",
        cli_type: "codex",
        model: "",
        source: "",
      };
      if (local && local.session_id) return { ...base, session_id: local.session_id, cli_type: local.cli_type, source: "bindings_compat" };
      return base;
    }

    function toNonNegativeInt(v, fallback = 0) {
      const n = Number(v);
      if (!Number.isFinite(n) || n < 0) return Math.max(0, Number(fallback) || 0);
      return Math.round(n);
    }

    function overviewProjectCard(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      const ov = (DATA && DATA.overview && typeof DATA.overview === "object") ? DATA.overview : null;
      const rows = Array.isArray(ov && ov.projects) ? ov.projects : [];
      return rows.find((x) => String((x && x.project_id) || "").trim() === pid) || null;
    }

    function overviewChannelCard(projectId, channelName) {
      const ch = String(channelName || "").trim();
      if (!ch) return null;
      const proj = overviewProjectCard(projectId);
      const rows = Array.isArray(proj && proj.channels_data) ? proj.channels_data : [];
      return rows.find((x) => String((x && x.name) || "").trim() === ch) || null;
    }

    function fallbackTaskTotals(items) {
      const src = Array.isArray(items) ? items : [];
      const tasks = src.filter(isTaskItem);
      const primaryCounts = primaryTaskCountsFromItems(tasks);
      return {
        total: tasks.length,
        active: primaryCounts.todo + primaryCounts.in_progress + primaryCounts.pending_acceptance,
        done: primaryCounts.done,
        supervised: tasks.reduce((sum, it) => sum + (taskStatusFlags(it).supervised ? 1 : 0), 0),
        in_progress: primaryCounts.in_progress,
        todo: primaryCounts.todo,
        pending_acceptance: primaryCounts.pending_acceptance,
        paused: primaryCounts.paused,
        primary_status_counts: primaryCounts,
        requirements_total: src.filter(isRequirementItem).length,
        requirements_active: src.filter((x) => isRequirementItem(x) && !DONE_STATUSES.has(x.status) && !PAUSE_STATUSES.has(x.status)).length,
      };
    }

    function projectTaskRequirementTotals(projectId) {
      const card = overviewProjectCard(projectId);
      const totals = (card && typeof card.totals === "object") ? card.totals : null;
      if (totals) {
        const primaryCounts = primaryTaskCountsFromTotals(totals);
        return {
          total: toNonNegativeInt(totals.total, 0),
          active: toNonNegativeInt(totals.active, 0),
          done: toNonNegativeInt(totals.done, 0),
          supervised: toNonNegativeInt(totals.supervised, 0),
          in_progress: toNonNegativeInt(totals.in_progress, 0),
          todo: primaryCounts.todo,
          pending_acceptance: primaryCounts.pending_acceptance,
          paused: primaryCounts.paused,
          primary_status_counts: primaryCounts,
          requirements_total: toNonNegativeInt(totals.requirements_total, 0),
          requirements_active: toNonNegativeInt(totals.requirements_active, 0),
        };
      }
      return fallbackTaskTotals(itemsForProject(projectId));
    }

    function channelTaskRequirementTotals(projectId, channelName) {
      const card = overviewChannelCard(projectId, channelName);
      const totals = (card && typeof card.totals === "object") ? card.totals : null;
      if (totals) {
        const primaryCounts = primaryTaskCountsFromTotals(totals);
        return {
          total: toNonNegativeInt(totals.total, 0),
          active: toNonNegativeInt(totals.active, 0),
          done: toNonNegativeInt(totals.done, 0),
          supervised: toNonNegativeInt(totals.supervised, 0),
          in_progress: toNonNegativeInt(totals.in_progress, 0),
          todo: primaryCounts.todo,
          pending_acceptance: primaryCounts.pending_acceptance,
          paused: primaryCounts.paused,
          primary_status_counts: primaryCounts,
          requirements_total: toNonNegativeInt(totals.requirements_total, 0),
          requirements_active: toNonNegativeInt(totals.requirements_active, 0),
        };
      }
      const src = itemsForProject(projectId).filter((x) => String((x && x.channel) || "") === String(channelName || ""));
      return fallbackTaskTotals(src);
    }

    function parseOptionalBool(value) {
      if (typeof value === "boolean") return value;
      if (value == null) return null;
      const t = String(value).trim().toLowerCase();
      if (["1", "true", "yes", "on"].includes(t)) return true;
      if (["0", "false", "no", "off"].includes(t)) return false;
      return null;
    }

    function channelRequirementCapability(projectId, channelName) {
      const sess = sessionForChannel(projectId, channelName) || {};
      const explicit = parseOptionalBool(
        Object.prototype.hasOwnProperty.call(sess, "enable_requirements")
          ? sess.enable_requirements
          : sess.enableRequirements
      );
      let effective = parseOptionalBool(
        Object.prototype.hasOwnProperty.call(sess, "requirements_enabled_effective")
          ? sess.requirements_enabled_effective
          : sess.requirementsEnabledEffective
      );
      let source = String(
        Object.prototype.hasOwnProperty.call(sess, "requirements_source")
          ? sess.requirements_source
          : sess.requirementsSource || ""
      ).trim().toLowerCase();
      const totals = channelTaskRequirementTotals(projectId, channelName);
      if (effective == null) effective = totals.requirements_total > 0;
      if (!source) {
        if (explicit != null) source = "config";
        else source = effective ? "legacy_detect" : "default_false";
      }
      return {
        enabled: !!effective,
        explicit: explicit == null ? null : !!explicit,
        source,
      };
    }

    function requirementCapabilityText(capability) {
      const cap = capability || {};
      if (String(cap.source || "") === "legacy_detect") return "需求:历史兼容";
      if (String(cap.source || "") === "config") return cap.enabled ? "需求:已启用" : "需求:已关闭";
      return cap.enabled ? "需求:已启用" : "需求:未启用";
    }

    function requirementCapabilityTone(capability) {
      const cap = capability || {};
      if (String(cap.source || "") === "legacy_detect") return "warn";
      if (cap.enabled) return "good";
      return "muted";
    }

    function defaultChannelForProject(projectId) {
      const names = unionChannelNames(projectId);
      if (!names.length) return "";
      // Default channel selection must be stable and must not change due to content filters.
      const items = itemsForProject(projectId);
      const byChan = new Map();
      for (const n of names) byChan.set(n, []);
      for (const it of items) {
        const k = String(it.channel || "");
        if (!byChan.has(k)) byChan.set(k, []);
        byChan.get(k).push(it);
      }
      function score(list) {
        let s = 0;
        for (const it of list) {
          const flags = taskStatusFlags(it);
          const primary = taskPrimaryStatus(it);
          if (flags.supervised) s += 1000;
          else if (flags.blocked) s += 360;
          else if (primary === "进行中") s += 300;
          else if (primary === "待验收") s += 180;
          else if (primary === "待办") s += 120;
          else if (primary === "暂缓") s += 5;
          else if (primary === "已完成") s += 1;
        }
        return s;
      }
      let best = names[0];
      let bestScore = -1;
      for (const n of names) {
        const sc = score(byChan.get(n) || []);
        if (sc > bestScore) { bestScore = sc; best = n; }
      }
      return best;
    }

    function ensureChannel() {
      if (STATE.project === "overview") { STATE.channel = ""; return; }
      const names = unionChannelNames(STATE.project);
      if (!names.length) { STATE.channel = ""; return; }
      if (!STATE.channel || !names.includes(STATE.channel)) {
        if (HASH_BOOTSTRAP.projectOnly && !STATE.channel) return;
        STATE.channel = defaultChannelForProject(STATE.project);
      }
    }

    // buildTabs function removed - tabs replaced with back link and project info in header

    function countByBucket(items) {
      const m = new Map();
      for (const it of items) {
        const k = bucketKeyForStatus(it.status);
        m.set(k, (m.get(k) || 0) + 1);
      }
      return m;
    }

    function conversationRuntimeSessionsForProject(projectId = "") {
      const pid = String(projectId || STATE.project || "").trim();
      if (!pid || pid === "overview") return [];
      const normalizeList = (list) => {
        const src = Array.isArray(list) ? list : [];
        const currentPid = String(pid || "").trim();
        const lastPid = String(PCONV.lastProjectId || "").trim();
        return src.filter((session) => {
          const row = (session && typeof session === "object") ? session : {};
          const deleted = typeof isDeletedSession === "function"
            ? isDeletedSession(row)
            : ["1", "true", "yes", "y"].includes(String(row.is_deleted || row.isDeleted || "").trim().toLowerCase());
          if (deleted) return false;
          const inactive = typeof isInactiveSession === "function"
            ? isInactiveSession(row)
            : String(row.status || row.session_status || row.sessionStatus || "").trim().toLowerCase() === "inactive";
          if (inactive) return false;
          const rowProjectId = String(row.project_id || row.projectId || "").trim();
          if (rowProjectId) return rowProjectId === currentPid;
          return lastPid === currentPid;
        });
      };
      return normalizeList(Array.isArray(PCONV.sessions) ? PCONV.sessions.slice() : []);
    }

    function conversationSessionsForProject(projectId = "") {
      const pid = String(projectId || STATE.project || "").trim();
      if (!pid || pid === "overview") return [];
      const normalizeList = (list) => {
        const src = Array.isArray(list) ? list : [];
        return src.filter((session) => {
          const row = (session && typeof session === "object") ? session : {};
          const deleted = typeof isDeletedSession === "function"
            ? isDeletedSession(row)
            : ["1", "true", "yes", "y"].includes(String(row.is_deleted || row.isDeleted || "").trim().toLowerCase());
          if (deleted) return false;
          const inactive = typeof isInactiveSession === "function"
            ? isInactiveSession(row)
            : String(row.status || row.session_status || row.sessionStatus || "").trim().toLowerCase() === "inactive";
          if (inactive) return false;
          const rowProjectId = String(row.project_id || row.projectId || "").trim();
          return !rowProjectId || rowProjectId === pid;
        });
      };
      const pending = conversationPendingCreateSessionsForProject(pid);
      const liveMeta = PCONV.sessionDirectoryMetaByProject && PCONV.sessionDirectoryMetaByProject[pid];
      const localDirectory = PCONV.sessionDirectoryByProject && PCONV.sessionDirectoryByProject[pid];
      const runtimeSessions = (typeof conversationRuntimeSessionsForProject === "function")
        ? conversationRuntimeSessionsForProject(pid)
        : [];
      if (runtimeSessions.length) {
        return pending.concat(runtimeSessions);
      }
      if (Array.isArray(localDirectory) && (localDirectory.length || (liveMeta && liveMeta.liveLoaded))) {
        return pending.concat(normalizeList(localDirectory.slice()));
      }
      return pending.concat(normalizeList(configuredProjectConversations(pid)));
    }

    function conversationSessionsForChannel(channelName, projectId = "") {
      const target = String(channelName || "").trim();
      if (!target) return [];
      const source = conversationSessionsForProject(projectId);
      const out = [];
      const seenSid = new Set();
      for (const s of source) {
        if (!sessionMatchesChannel(s, target)) continue;
        const sid = String(getSessionId(s) || "").trim();
        if (sid) {
          if (seenSid.has(sid)) continue;
          seenSid.add(sid);
        }
        out.push(s);
      }
      return sortedConversationSessions(out);
    }

    function countConversationByChannel(channelName, projectId = "") {
      return conversationSessionsForChannel(channelName, projectId).length;
    }

    function joinRelPath(base, leaf) {
      const a = String(base || "").trim().replace(/^\/+|\/+$/g, "");
      const b = String(leaf || "").trim().replace(/^\/+|\/+$/g, "");
      if (a && b) return a + "/" + b;
      return a || b || "";
    }

    function inferChannelRootFromItemPath(path, channelName) {
      const p = String(path || "").trim();
      const ch = String(channelName || "").trim();
      if (!p || !ch) return "";
      const segs = p.split("/").map((x) => String(x || "").trim()).filter(Boolean);
      if (!segs.length) return "";
      const idx = segs.findIndex((x) => x === ch);
      if (idx < 0) return "";
      return segs.slice(0, idx + 1).join("/");
    }

    function resolveChannelRootPath(project, channelName, channelItems) {
      const ch = String(channelName || "").trim();
      if (!ch) return "";
      const cfgRoot = joinRelPath(project && project.task_root_rel, ch);
      if (cfgRoot) return cfgRoot;
      const items = Array.isArray(channelItems) ? channelItems : [];
      for (const it of items) {
        const inferred = inferChannelRootFromItemPath(it && it.path, ch);
        if (inferred) return inferred;
      }
      return "";
    }

    function getChannelDesc(project, channelName, session) {
      const ch = String(channelName || "").trim();
      const channels = Array.isArray(project && project.channels) ? project.channels : [];
      const fromChannels = channels.find((x) => String((x && x.name) || "") === ch);
      const channelSessions = Array.isArray(project && project.channel_sessions) ? project.channel_sessions : [];
      const fromSessions = channelSessions.find((x) => String((x && x.name) || "") === ch);
      return firstNonEmptyText([
        fromChannels && fromChannels.desc,
        fromSessions && fromSessions.desc,
        session && session.desc,
      ]);
    }

    function clearNodeChildren(node) {
      if (!node) return;
      while (node.firstChild) node.removeChild(node.firstChild);
    }

    function appendCliChip(node, cliTypeRaw) {
      if (!node) return;
      const cliTypeClass = normalizeCliTypeClass(cliTypeRaw);
      const cliTypeLabel = normalizeCliTypeLabel(cliTypeRaw);
      node.appendChild(el("span", { class: "chip cli-chip cli-" + cliTypeClass, text: "CLI:" + cliTypeLabel }));
    }

    function renderChannelInfoCard() {
      const infoLabel = document.getElementById("channelInfoLabel");
      const nameEl = document.getElementById("currentChannelName");
      const subEl = document.getElementById("channelInfoSub");
      const statsEl = document.getElementById("channelInfoStats");
      const pathRow = document.getElementById("channelPathRow");
      const pathText = document.getElementById("channelPathText");
      const copyBtn = document.getElementById("channelPathCopyBtn");
      const revealBtn = document.getElementById("channelPathRevealBtn");
      const manageBtn = document.getElementById("channelConversationManageBtn");
      if (!infoLabel || !nameEl || !subEl || !statsEl || !pathRow || !pathText || !copyBtn || !revealBtn) return;

      const project = projectById(STATE.project);
      const projectItems = itemsForProject(STATE.project);
      const channelName = String(STATE.channel || "").trim();
      const channelItems = (STATE.project !== "overview" && channelName)
        ? projectItems.filter((x) => String((x && x.channel) || "") === channelName)
        : [];

      const setPathActions = (targetPath) => {
        const p = String(targetPath || "").trim();
        pathText.textContent = p || "未识别通道目录路径";
        pathText.classList.toggle("is-empty", !p);
        pathText.title = p ? "点击复制路径" : "当前无可用路径";
        pathText.onclick = p ? (() => copyText(p)) : (() => {});
        copyBtn.disabled = !p;
        copyBtn.onclick = p ? (() => copyText(p)) : (() => {});
        revealBtn.disabled = !p;
        revealBtn.onclick = async (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (!p) return;
          revealBtn.disabled = true;
          try {
            const ok = await apiHealth();
            if (!ok) {
              alert("本机服务不可用，无法打开通道文件夹。");
              return;
            }
            const resp = await fetch("/api/fs/reveal", {
              method: "POST",
              headers: authHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ path: p }),
            });
            if (!resp.ok) {
              const detail = await parseResponseDetail(resp);
              throw new Error(detail || ("HTTP " + resp.status));
            }
          } catch (err) {
            alert("打开通道文件夹失败：" + String((err && err.message) || err || "未知错误"));
          } finally {
            revealBtn.disabled = false;
          }
        };
      };

      infoLabel.style.display = "";
      nameEl.title = "";
      subEl.style.display = "";
      subEl.title = "";
      copyBtn.style.display = "";
      clearNodeChildren(statsEl);
      pathRow.style.display = "none";
      setPathActions("");
      if (manageBtn) {
        manageBtn.disabled = true;
        manageBtn.onclick = null;
        manageBtn.style.display = "none";
      }

      if (STATE.panelMode === "arch") {
        const orgSnapshot = orgBoardSnapshot(STATE.project);
        const orgRuntime = orgBoardRuntime(STATE.project);
        const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
        const orgEdgeCount = Array.isArray(orgSnapshot.edges) ? orgSnapshot.edges.length : 0;
        const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
        infoLabel.textContent = "当前维度：";
        nameEl.textContent = "架构";
        subEl.textContent = "全屏单板画布：按架构快照展示结构关系，并叠加运行态关系。";
        statsEl.appendChild(chip("节点:" + orgNodeCount, orgNodeCount ? "good" : "muted"));
        statsEl.appendChild(chip("结构边:" + orgEdgeCount, orgEdgeCount ? "muted" : "muted"));
        statsEl.appendChild(chip("运行态关系:" + orgRelCount, orgRelCount ? "warn" : "muted"));
        return;
      }

      if (STATE.panelMode === "org") {
        const orgSnapshot = orgBoardSnapshot(STATE.project);
        const orgRuntime = orgBoardRuntime(STATE.project);
        const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
        const orgEdgeCount = Array.isArray(orgSnapshot.edges) ? orgSnapshot.edges.length : 0;
        const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
        infoLabel.textContent = "当前维度：";
        nameEl.textContent = "组织";
        subEl.textContent = "组织认知页：按组织树、关系主视图、节点详情三栏展示稳定信息，架构编辑能力已剥离到“架构”页。";
        statsEl.appendChild(chip("节点:" + orgNodeCount, orgNodeCount ? "good" : "muted"));
        statsEl.appendChild(chip("结构边:" + orgEdgeCount, orgEdgeCount ? "muted" : "muted"));
        statsEl.appendChild(chip("运行态关系:" + orgRelCount, orgRelCount ? "warn" : "muted"));
        return;
      }

      if (STATE.panelMode === "task") {
        const moduleMode = normalizeTaskModule(STATE.taskModule);
        const orgSnapshot = orgBoardSnapshot(STATE.project);
        const orgRuntime = orgBoardRuntime(STATE.project);
        const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
        const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
        const projectTotals = projectTaskRequirementTotals(STATE.project);
        infoLabel.textContent = "当前维度：";
        nameEl.textContent = moduleMode === "org" ? "组织2D画板" : "全项目任务";
        const names = unionChannelNames(STATE.project);
        const activeTotal = toNonNegativeInt(projectTotals.active, 0);
        const projectPrimaryCounts = primaryTaskCountsFromTotals(projectTotals);
        const taskTotal = toNonNegativeInt(projectTotals.total, 0);
        const requirementsTotal = toNonNegativeInt(projectTotals.requirements_total, 0);
        subEl.textContent = moduleMode === "org"
          ? "组织2D画板按统一结构模型展示节点与运行态关系，并保留3D图谱入口。"
          : "按主任务批次查看。切换到“知识”后可查看通道目录路径并快速打开文件夹。";
        statsEl.appendChild(chip("通道:" + names.length, names.length ? "muted" : "warn"));
        statsEl.appendChild(chip("任务:" + taskTotal, taskTotal ? "good" : "muted"));
        statsEl.appendChild(chip("待办:" + projectPrimaryCounts.todo, projectPrimaryCounts.todo ? "muted" : "muted"));
        statsEl.appendChild(chip("进行中:" + projectPrimaryCounts.in_progress, projectPrimaryCounts.in_progress ? "warn" : "muted"));
        if (projectPrimaryCounts.pending_acceptance) statsEl.appendChild(chip("待验收:" + projectPrimaryCounts.pending_acceptance, "warn"));
        statsEl.appendChild(chip("需求:" + requirementsTotal, requirementsTotal ? "good" : "muted"));
        statsEl.appendChild(chip("组织节点:" + orgNodeCount, orgNodeCount ? "good" : "muted"));
        statsEl.appendChild(chip("运行态关系:" + orgRelCount, orgRelCount ? "warn" : "muted"));
        statsEl.appendChild(chip("活跃:" + activeTotal, activeTotal ? "warn" : "muted"));
        return;
      }

      if (STATE.project === "overview" || !channelName) {
        infoLabel.textContent = "当前通道：";
        nameEl.textContent = "-";
        subEl.textContent = "请选择左侧通道，查看文件资料、知识沉淀和目录路径。";
        return;
      }

      const sess = sessionForChannel(STATE.project, channelName);
      const desc = getChannelDesc(project, channelName, sess);
      const fileItems = channelFileItems(STATE.project, channelName, { applyQuery: false });
      const visibleFileItems = channelFileItems(STATE.project, channelName, { applyQuery: true });
      const sedimentCount = fileItems.filter((x) => String((x && x.path) || "").includes("/产出物/沉淀/")).length;
      const materialCount = fileItems.filter((x) => String((x && x.path) || "").includes("/产出物/材料/")).length;
      const channelRootPath = resolveChannelRootPath(project, channelName, channelItems);

      infoLabel.textContent = "当前通道：";
      infoLabel.style.display = "";
      nameEl.textContent = channelName;
      nameEl.title = [
        desc ? ("说明: " + desc) : "说明: 未配置",
        channelRootPath ? ("目录: " + channelRootPath) : "目录: 未识别",
      ].join("\n");
      subEl.textContent = desc || "当前通道仅保留文件资料、知识沉淀与目录入口。";
      subEl.style.display = "";

      statsEl.appendChild(chip("文件:" + fileItems.length, fileItems.length ? "good" : "muted"));
      statsEl.appendChild(chip("沉淀:" + sedimentCount, sedimentCount ? "good" : "muted"));
      statsEl.appendChild(chip("材料:" + materialCount, materialCount ? "muted" : "muted"));
      if (String(STATE.q || "").trim()) statsEl.appendChild(chip("命中:" + visibleFileItems.length, visibleFileItems.length ? "warn" : "muted"));
      if (!channelRootPath) statsEl.appendChild(chip("目录缺失", "warn"));
      if (!desc) statsEl.appendChild(chip("未配置说明", "muted"));

      setPathActions(channelRootPath);
    }

    function buildLeftList() {
      const left = document.getElementById("leftList");
      const asideTitle = document.getElementById("asideTitle");
      const asideMeta = document.getElementById("asideMeta");
      const layoutTabs = document.getElementById("convLayoutTabs");
      left.innerHTML = "";

      if (STATE.panelMode === "conv") {
        buildConversationLeftList();
        return;
      }
      if (layoutTabs) layoutTabs.style.display = "none";

      if (STATE.panelMode === "arch") {
        asideTitle.textContent = "架构";
        asideMeta.innerHTML = "";
        const orgSnapshot = orgBoardSnapshot(STATE.project);
        const orgRuntime = orgBoardRuntime(STATE.project);
        const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
        const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
        asideMeta.appendChild(metaPill("节点 " + orgNodeCount, orgNodeCount ? "good" : "muted"));
        asideMeta.appendChild(metaPill("关系 " + orgRelCount, orgRelCount ? "warn" : "muted"));
        return;
      }

      if (STATE.panelMode === "org") {
        asideTitle.textContent = "组织";
        asideMeta.innerHTML = "";
        const orgSnapshot = orgBoardSnapshot(STATE.project);
        const orgRuntime = orgBoardRuntime(STATE.project);
        const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
        const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
        asideMeta.appendChild(metaPill("节点 " + orgNodeCount, orgNodeCount ? "good" : "muted"));
        asideMeta.appendChild(metaPill("关系 " + orgRelCount, orgRelCount ? "warn" : "muted"));
        return;
      }

      if (STATE.panelMode === "task") {
        asideTitle.textContent = "任务模块";
        const groups = buildTaskGroups(STATE.project);
        const byLane = { "进行中": 0, "待办": 0, "待验收": 0, "已完成": 0, "暂缓": 0, "已归档": 0 };
        groups.forEach((g) => {
          const lane = String((g && g.lane) || "已归档");
          if (!Object.prototype.hasOwnProperty.call(byLane, lane)) return;
          byLane[lane] = Number(byLane[lane] || 0) + 1;
        });
        const orgSnapshot = orgBoardSnapshot(STATE.project);
        const orgRuntime = orgBoardRuntime(STATE.project);
        const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
        const orgRelationCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
        asideMeta.innerHTML = "";
        asideMeta.appendChild(metaPill("总任务 " + groups.length, "muted"));
        asideMeta.appendChild(metaPill("组织 " + orgNodeCount, orgNodeCount ? "good" : "muted"));

        const taskBtn = el("button", {
          class: "rowbtn task-module-card" + (normalizeTaskModule(STATE.taskModule) === "tasks" ? " active" : ""),
        });
        taskBtn.appendChild(el("div", { class: "name", text: "任务模块" }));
        const taskChips = el("div", { class: "chips" });
        taskChips.appendChild(chip("总任务:" + groups.length, "muted"));
        taskChips.appendChild(chip("进行中:" + byLane["进行中"], byLane["进行中"] ? "warn" : "muted"));
        taskChips.appendChild(chip("待办:" + byLane["待办"], byLane["待办"] ? "muted" : "muted"));
        taskChips.appendChild(chip("待验收:" + byLane["待验收"], byLane["待验收"] ? "warn" : "muted"));
        taskChips.appendChild(chip("已完成:" + byLane["已完成"], byLane["已完成"] ? "good" : "muted"));
        if (byLane["暂缓"]) taskChips.appendChild(chip("暂缓:" + byLane["暂缓"], "muted"));
        taskBtn.appendChild(taskChips);
        taskBtn.addEventListener("click", () => {
          STATE.taskModule = "tasks";
          setHash();
          render();
        });
        left.appendChild(taskBtn);

        const orgCache = orgBoardCache(STATE.project);
        const orgStale = !orgCache || ((Date.now() - Number(orgCache.fetchedAtMs || 0)) > 10000);
        if (orgStale && !ORG_BOARD_UI.loadingByProject[String(STATE.project || "").trim()]) {
          fetchOrgBoardData(STATE.project, { maxAgeMs: 10000 }).then(() => render()).catch(() => {});
        }
        return;
      }

      if (STATE.project === "overview") {
        asideTitle.textContent = "项目";
        // Left is a "parent layer": do NOT change its spec/counters due to main content filters.
        const overviewTotals = (DATA && DATA.overview && DATA.overview.totals && typeof DATA.overview.totals === "object")
          ? DATA.overview.totals
          : null;
        const overviewTaskTotal = overviewTotals
          ? toNonNegativeInt(overviewTotals.total, 0)
          : allItems().filter(isTaskItem).length;
        const overviewReqTotal = overviewTotals
          ? toNonNegativeInt(overviewTotals.requirements_total, 0)
          : allItems().filter(isRequirementItem).length;
        asideMeta.innerHTML = "";
        asideMeta.appendChild(metaPill("项目 " + (pages().length - 1), "muted"));
        asideMeta.appendChild(metaPill("任务 " + overviewTaskTotal, overviewTaskTotal ? "good" : "muted"));
        asideMeta.appendChild(metaPill("需求 " + overviewReqTotal, overviewReqTotal ? "good" : "muted"));
        for (const p of pages().filter(x => x.id !== "overview")) {
          const pTotals = projectTaskRequirementTotals(p.id);
          const active = toNonNegativeInt(pTotals.active, 0);
          const done = toNonNegativeInt(pTotals.done, 0);
          const reqCount = toNonNegativeInt(pTotals.requirements_total, 0);
          const btn = el("button", { class: "rowbtn" });
          btn.appendChild(el("div", { class: "name", text: p.name }));
          const chips = el("div", { class: "chips" });
          chips.appendChild(chip("需求:" + reqCount, reqCount ? "good" : "muted"));
          chips.appendChild(chip("活跃:" + active, active ? "warn" : "muted"));
          chips.appendChild(chip("已完成:" + done, done ? "good" : "muted"));
          btn.appendChild(chips);
          btn.addEventListener("click", () => {
            STATE.project = p.id;
            ensureChannel();
            STATE.selectedPath = "";
            STATE.selectedTaskId = "";
            syncSelectedTaskSelectionStorage();
            setHash();
            render();
            closeDrawerOnMobile();
          });
          left.appendChild(btn);
        }
        return;
      }

      asideTitle.textContent = "知识";
      asideMeta.innerHTML = "";
      const names = unionChannelNames(STATE.project);
      const totalFiles = names.reduce((sum, name) => sum + channelFileItems(STATE.project, name, { applyQuery: false }).length, 0);
      const totalSediments = names.reduce((sum, name) => (
        sum + channelFileItems(STATE.project, name, { applyQuery: false })
          .filter((x) => String((x && x.path) || "").includes("/产出物/沉淀/")).length
      ), 0);
      asideMeta.appendChild(metaPill("通道 " + names.length, "muted"));
      asideMeta.appendChild(metaPill("文件 " + totalFiles, totalFiles ? "good" : "muted"));
      asideMeta.appendChild(metaPill("沉淀 " + totalSediments, totalSediments ? "good" : "muted"));

      for (const name of names) {
        const fileItems = channelFileItems(STATE.project, name, { applyQuery: false });
        const sedimentCount = fileItems.filter((x) => String((x && x.path) || "").includes("/产出物/沉淀/")).length;
        const materialCount = fileItems.filter((x) => String((x && x.path) || "").includes("/产出物/材料/")).length;
        const channelRoot = resolveChannelRootPath(projectById(STATE.project), name, fileItems);
        const btn = el("button", { class: "rowbtn" + (STATE.channel === name ? " active" : "") });
        btn.appendChild(el("div", { class: "name", text: name }));
        const chips = el("div", { class: "chips" });
        chips.appendChild(chip("文件:" + fileItems.length, fileItems.length ? "good" : "muted"));
        chips.appendChild(chip("沉淀:" + sedimentCount, sedimentCount ? "good" : "muted"));
        if (materialCount) chips.appendChild(chip("材料:" + materialCount, "muted"));
        if (!channelRoot) chips.appendChild(chip("目录缺失", "warn"));
        btn.appendChild(chips);
        btn.addEventListener("click", () => {
          STATE.channel = name;
          STATE.selectedPath = "";
          STATE.selectedTaskId = "";
          STATE.selectedSessionId = "";
          STATE.selectedSessionExplicit = false;
          syncSelectedTaskSelectionStorage();
          setHash();
          render();
          closeDrawerOnMobile();
        });
        if (typeof buildChannelManageRow === "function") left.appendChild(buildChannelManageRow(STATE.project, name, btn));
        else left.appendChild(btn);
      }
    }

    function panel(title, rightNode, bodyNodes) {
      const p = el("section", { class: "panel" });
      const h = el("div", { class: "ph" });
      h.appendChild(el("h2", { text: title }));
      if (rightNode) h.appendChild(rightNode);
      p.appendChild(h);
      const b = el("div", { class: "pb" });
      for (const n of (bodyNodes || [])) b.appendChild(n);
      p.appendChild(b);
      return p;
    }

    function kvRow(k, v, btnText, btnAction, primary) {
      const wrap = el("div", { class: "rowbtn", style: "cursor:default" });
      const rt = el("div", { class: "rt" });
      rt.appendChild(el("div", { class: "name", text: String(k || "") }));
      if (btnText) {
        const b = el("button", { class: "btn" + (primary ? " primary" : ""), text: btnText });
        b.addEventListener("click", (e) => { e.stopPropagation(); btnAction && btnAction(); });
        rt.appendChild(b);
      }
      wrap.appendChild(rt);
      if (v) wrap.appendChild(el("div", { class: "mono", text: String(v) }));
      return wrap;
    }

    function isItemVisible(it) {
      if (!it || !it.path) return false;
      const p = String(it.path);
      return scopeItems().some(x => String(x.path) === p);
    }

    function normalizeTaskStableId(value) {
      return String(value || "").trim();
    }

    function taskStableIdOfItem(item) {
      return normalizeTaskStableId(firstNonEmptyText([
        item && item.task_id,
        item && item.taskId,
      ]) || "");
    }

    function taskSelectionMatchesItem(item, selectedPath = "", selectedTaskId = "") {
      const stableTaskId = taskStableIdOfItem(item);
      if (selectedTaskId && stableTaskId && stableTaskId === selectedTaskId) return true;
      const itemPath = normalizeScheduleTaskPath(item && item.path);
      const pathKey = normalizeScheduleTaskPath(selectedPath);
      return !!(pathKey && itemPath && itemPath === pathKey);
    }

    function syncSelectedTaskSelectionStorage() {
      try {
        if (STATE.selectedPath) localStorage.setItem("taskDashboard.selectedPath", STATE.selectedPath);
        else localStorage.removeItem("taskDashboard.selectedPath");
        if (STATE.selectedTaskId) localStorage.setItem("taskDashboard.selectedTaskId", STATE.selectedTaskId);
        else localStorage.removeItem("taskDashboard.selectedTaskId");
      } catch (_) {}
    }

    function resolveTaskIdByPath(pathValue) {
      const normalizedPath = normalizeScheduleTaskPath(pathValue);
      if (!normalizedPath) return "";
      const items = allItems();
      const hit = items.find((x) => normalizeScheduleTaskPath(x && x.path) === normalizedPath) || null;
      return taskStableIdOfItem(hit);
    }

    function selectedItem() {
      const selectedTaskId = normalizeTaskStableId(STATE.selectedTaskId || "");
      const p = String(STATE.selectedPath || "");
      const items = allItems();
      if (!items.length) return null;
      if (selectedTaskId) {
        const byId = items.find((x) => taskStableIdOfItem(x) === selectedTaskId) || null;
        if (byId) return byId;
      }
      const exact = p ? (items.find((x) => String((x && x.path) || "") === p) || null) : null;
      if (exact) return exact;
      const normalized = normalizeScheduleTaskPath(p);
      if (normalized) {
        const byPath = items.find((x) => normalizeScheduleTaskPath(x && x.path) === normalized) || null;
        if (byPath) return byPath;
      }
      return null;
    }

    function chooseDefaultItem() {
      if (STATE.project === "overview") {
        const all = sortListItems(filteredItemsForProject("overview"));
        return all[0] || null;
      }
      if (STATE.view === "comms") {
        const base = itemsForProject(STATE.project).filter(x => String(x.channel || "") === String(STATE.channel));
        const comms = sortListItems(base.filter(isDiscussionSpaceItem).filter(matchesQuery));
        return comms[0] || null;
      }
      const base = sortListItems(filteredItemsForProject(STATE.project).filter(x => String(x.channel || "") === String(STATE.channel)));
      return base[0] || null;
    }

    function ensureSelection() {
      if (STATE.panelMode === "conv") return;
      if (STATE.panelMode === "org" || STATE.panelMode === "arch") {
        STATE.selectedPath = "";
        STATE.selectedTaskId = "";
        return;
      }
      if (STATE.panelMode === "task") {
        const moduleMode = normalizeTaskModule(STATE.taskModule);
        if (moduleMode === "org") {
          STATE.selectedPath = "";
          STATE.selectedTaskId = "";
          return;
        }
        const cur = selectedItem();
        if (cur && isTaskItem(cur)) {
          const currentPath = normalizeScheduleTaskPath(cur.path);
          const currentTaskId = taskStableIdOfItem(cur);
          if (currentPath && currentPath !== normalizeScheduleTaskPath(STATE.selectedPath || "")) {
            STATE.selectedPath = currentPath;
          }
          if (currentTaskId && currentTaskId !== normalizeTaskStableId(STATE.selectedTaskId || "")) {
            STATE.selectedTaskId = currentTaskId;
          }
          return;
        }
        const groups = buildTaskGroups(STATE.project);
        const filtered = STATE.taskLane === "全部" ? groups : groups.filter((g) => g.lane === STATE.taskLane);
        const first = filtered.length ? filtered[0] : null;
        if (first && first.master) {
          STATE.selectedPath = String(first.master.path || "");
          STATE.selectedTaskId = taskStableIdOfItem(first.master);
        }
        return;
      }
      const cur = selectedItem();
      if (cur && isItemVisible(cur)) {
        const currentPath = normalizeScheduleTaskPath(cur.path);
        const currentTaskId = taskStableIdOfItem(cur);
        if (currentPath && currentPath !== normalizeScheduleTaskPath(STATE.selectedPath || "")) {
          STATE.selectedPath = currentPath;
        }
        if (currentTaskId && currentTaskId !== normalizeTaskStableId(STATE.selectedTaskId || "")) {
          STATE.selectedTaskId = currentTaskId;
        }
        return;
      }
      const d = chooseDefaultItem();
      if (d) {
        STATE.selectedPath = String(d.path);
        STATE.selectedTaskId = taskStableIdOfItem(d);
      }
    }

    function setSelectedPath(p) {
      return setSelectedTaskRef(p, "");
    }

    function taskDetailForceTypeForSelection(item, opts = {}) {
      const explicit = String((opts && opts.forceTaskType) || "").trim();
      if (explicit) return explicit;
      if (!item || !isTaskItem(item) || typeof buildTaskGroups !== "function") return "";
      const projectId = String(item.project_id || STATE.project || "").trim();
      const selectedPath = normalizeScheduleTaskPath(item.path || item.task_path || "");
      const selectedTaskId = taskStableIdOfItem(item);
      if (!projectId || (!selectedPath && !selectedTaskId)) return "";
      const groups = buildTaskGroups(projectId);
      for (const group of Array.isArray(groups) ? groups : []) {
        if (group && group.master && taskSelectionMatchesItem(group.master, selectedPath, selectedTaskId)) return "parent";
        const children = Array.isArray(group && group.children) ? group.children : [];
        if (children.some((child) => taskSelectionMatchesItem(child, selectedPath, selectedTaskId))) return "child";
      }
      return "";
    }

    function openUnifiedTaskDetailForSelection(item, opts = {}) {
      if (!item || !isTaskItem(item) || typeof openUnifiedTaskDetail !== "function") return false;
      const projectId = String(item.project_id || STATE.project || "").trim();
      const project = projectId && projectId !== "overview" ? projectById(projectId) : null;
      return openUnifiedTaskDetail(item, {
        source: opts.source || "task-selection",
        projectId,
        projectName: project ? (project.name || project.id || "") : "",
        channelName: item.channel || STATE.channel || "",
        groupTitle: opts.groupTitle || item.__groupTitle || "",
        forceTaskType: taskDetailForceTypeForSelection(item, opts),
      });
    }

    function setSelectedTaskRef(pathValue, taskIdValue = "", opts = null) {
      if (STATE.panelMode === "conv" || STATE.panelMode === "org" || STATE.panelMode === "arch") return;
      STATE.selectedPath = normalizeScheduleTaskPath(pathValue);
      STATE.selectedTaskId = normalizeTaskStableId(taskIdValue || resolveTaskIdByPath(STATE.selectedPath));
      const openCanvasDetail = !!(opts && opts.openCanvasDetail);
      const forceUnifiedDetail = !!(opts && opts.openUnifiedDetail);
      // 选择任务时清除对话选中状态
      STATE.selectedSessionId = "";
      STATE.selectedSessionExplicit = false;
      syncSelectedTaskSelectionStorage();
      const selected = selectedItem();
      renderDetail(selected);
      refreshCCB();
      updateSelectionUI();
      buildChannelConversationList();
      if (selected && isTaskItem(selected) && (forceUnifiedDetail || STATE.panelMode === "task" || openCanvasDetail)) {
        if (typeof closeTaskCanvasDetail === "function") closeTaskCanvasDetail();
        openUnifiedTaskDetailForSelection(selected, {
          source: "task-list-selection",
          forceTaskType: opts && opts.forceTaskType,
        });
        return;
      }
      if (typeof isTaskSingleCanvasMode === "function" && isTaskSingleCanvasMode()) {
        if (openCanvasDetail && typeof openTaskCanvasDetail === "function") {
          openTaskCanvasDetail();
        }
        if (isMobileViewport() && pathValue) showDetailView();
        return;
      }
      // 移动端切换到详情视图
      if (isMobileViewport() && pathValue) {
        showDetailView();
      }
    }

    function updateSelectionUI() {
      const p = normalizeScheduleTaskPath(STATE.selectedPath || "");
      for (const n of document.querySelectorAll("[data-path]")) {
        const np = normalizeScheduleTaskPath(n.getAttribute("data-path") || "");
        if (np === p) n.classList.add("active");
        else n.classList.remove("active");
      }
    }

    function chipButton(label, active, onClick) {
      const b = el("button", { class: "chipbtn" + (active ? " active" : ""), text: label });
      b.addEventListener("click", onClick);
      return b;
    }

    function taskTitleBase(it) {
      let t = String((it && it.title) || "").trim();
      if (!t) return "";
      t = t.replace(/^(?:【[^】]+】\s*)+/g, "").trim();
      t = t.replace(/\.md$/i, "").trim();
      return t;
    }

    function taskParentStableIdOfItem(item) {
      return normalizeTaskStableId(firstNonEmptyText([
        item && item.parent_task_id,
        item && item.parentTaskId,
      ]) || "");
    }

    function taskParentPathOfItem(item, projectId = "") {
      return normalizeScheduleTaskPathForProject(projectId, firstNonEmptyText([
        item && item.parent_task_path,
        item && item.parentTaskPath,
      ]) || "");
    }

    function itemDeclaresExplicitTaskParent(item, projectId = "") {
      const row = (item && typeof item === "object") ? item : {};
      if (taskParentStableIdOfItem(row)) return true;
      if (taskParentPathOfItem(row, projectId)) return true;
      return row.is_subtask === true || row.isSubtask === true;
    }

    function inferTaskGroupMeta(it) {
      const base = taskTitleBase(it);
      const tokens = base.split("-").map((x) => String(x || "").trim()).filter(Boolean);
      if (!tokens.length) return { key: String((it && it.path) || ""), child: false, childOrder: 0 };
      const first = tokens[0];
      const second = tokens[1] || "";

      // A01 / A01-1
      if (/^A\d{2,}$/i.test(first)) {
        return { key: first.toUpperCase(), child: /^\d+$/.test(second), childOrder: /^\d+$/.test(second) ? Number(second) : 0 };
      }
      // 19 / 19-2
      if (/^\d{1,4}$/.test(first)) {
        return { key: first, child: /^\d+$/.test(second), childOrder: /^\d+$/.test(second) ? Number(second) : 0 };
      }
      // 20260223-33-...，保留前两段做组，降低误聚合
      if (/^\d{8}$/.test(first) && /^\d+$/.test(second) && tokens.length >= 3) {
        return { key: first + "-" + second, child: true, childOrder: Number(second) };
      }
      // 其他默认独立成组
      return { key: base || String((it && it.path) || ""), child: false, childOrder: 0 };
    }

    function taskLaneFromMasterBucket(bucket) {
      const b = String(bucket || "");
      if (b === "进行中") return "进行中";
      if (b === "待办") return "待办";
      if (b === "待验收") return "待验收";
      if (b === "已完成") return "已完成";
      if (b === "暂缓") return "暂缓";
      return "已归档";
    }

    function buildTaskGroups(projectId) {
      const allTasks = itemsForProject(projectId).filter(isTaskItem);
      const matchedTasks = allTasks.filter(matchesQuery);
      const matchedTaskIds = new Set(
        matchedTasks.map((it) => taskStableIdOfItem(it)).filter(Boolean)
      );
      const matchedTaskPaths = new Set(
        matchedTasks.map((it) => normalizeScheduleTaskPathForProject(projectId, it && it.path)).filter(Boolean)
      );
      const explicitHierarchy = allTasks.some((it) => itemDeclaresExplicitTaskParent(it, projectId));
      const groups = [];

      if (explicitHierarchy) {
        const taskByStableId = new Map();
        const taskByPath = new Map();
        allTasks.forEach((it) => {
          const stableId = taskStableIdOfItem(it);
          if (stableId) taskByStableId.set(stableId, it);
          const normPath = normalizeScheduleTaskPathForProject(projectId, it && it.path);
          if (normPath) taskByPath.set(normPath, it);
        });

        const parentByTask = new Map();
        allTasks.forEach((it) => {
          let parent = null;
          const parentStableId = taskParentStableIdOfItem(it);
          if (parentStableId) parent = taskByStableId.get(parentStableId) || null;
          if (!parent) {
            const parentPath = taskParentPathOfItem(it, projectId);
            if (parentPath) parent = taskByPath.get(parentPath) || null;
          }
          if (parent && parent !== it) parentByTask.set(it, parent);
        });

        const rootCache = new Map();
        const resolveRootTask = (task) => {
          if (!task) return null;
          if (rootCache.has(task)) return rootCache.get(task) || null;
          const seen = new Set();
          let current = task;
          while (current && parentByTask.has(current) && !seen.has(current)) {
            seen.add(current);
            const parent = parentByTask.get(current);
            if (!parent || parent === current) break;
            current = parent;
          }
          const root = current || task;
          seen.forEach((node) => rootCache.set(node, root));
          rootCache.set(task, root);
          return root;
        };

        const grouped = new Map();
        allTasks.forEach((it) => {
          const root = resolveRootTask(it) || it;
          const key = taskStableIdOfItem(root)
            || normalizeScheduleTaskPathForProject(projectId, root && root.path)
            || String((root && root.path) || "");
          if (!grouped.has(key)) {
            grouped.set(key, {
              key,
              master: root,
              members: [],
              matched: false,
            });
          }
          const group = grouped.get(key);
          group.members.push(it);
          const stableId = taskStableIdOfItem(it);
          const normPath = normalizeScheduleTaskPathForProject(projectId, it && it.path);
          if ((stableId && matchedTaskIds.has(stableId)) || (normPath && matchedTaskPaths.has(normPath))) {
            group.matched = true;
          }
        });

        grouped.forEach((group) => {
          if (!group.matched) return;
          const master = group.master || null;
          const children = group.members
            .filter((it) => !master || String((it && it.path) || "") !== String((master && master.path) || ""))
            .map((it) => ({ item: it, meta: inferTaskGroupMeta(it) }))
            .sort((a, b) => {
              const ao = Number(a.meta.childOrder || 0);
              const bo = Number(b.meta.childOrder || 0);
              if (ao !== bo) return ao - bo;
              return toTimeNum(b.item && b.item.updated_at) - toTimeNum(a.item && a.item.updated_at);
            })
            .map((entry) => entry.item);
          const childCounts = Object.create(null);
          for (const child of children) {
            const bucket = taskPrimaryStatus(child);
            childCounts[bucket] = Number(childCounts[bucket] || 0) + 1;
          }
          const masterBucket = taskPrimaryStatus(master);
          const lane = taskLaneFromMasterBucket(masterBucket);
          groups.push({
            key: group.key,
            lane,
            master,
            masterBucket,
            children,
            childCounts,
            childTotal: children.length,
            total: group.members.length,
            latestAt: String((master && master.updated_at) || ""),
            latestTs: toTimeNum(master && master.updated_at),
          });
        });
      } else {
        const grouped = new Map();
        allTasks.forEach((it) => {
          const meta = inferTaskGroupMeta(it);
          const key = String(meta.key || "").trim() || String(it.path || "");
          if (!grouped.has(key)) {
            grouped.set(key, {
              key,
              members: [],
              matched: false,
            });
          }
          const group = grouped.get(key);
          group.members.push({ item: it, meta });
          const stableId = taskStableIdOfItem(it);
          const normPath = normalizeScheduleTaskPathForProject(projectId, it && it.path);
          if ((stableId && matchedTaskIds.has(stableId)) || (normPath && matchedTaskPaths.has(normPath))) {
            group.matched = true;
          }
        });

        grouped.forEach((g) => {
          if (!g.matched) return;
          const members = g.members.slice();
          const rootCandidates = members.filter((x) => !x.meta.child).sort((a, b) => toTimeNum(b.item.updated_at) - toTimeNum(a.item.updated_at));
          const sortedByFresh = members.slice().sort((a, b) => toTimeNum(b.item.updated_at) - toTimeNum(a.item.updated_at));
          const master = (rootCandidates[0] || sortedByFresh[0] || {}).item || null;
          const children = members
            .filter((x) => !master || String(x.item.path || "") !== String(master.path || ""))
            .sort((a, b) => {
              const ao = Number(a.meta.childOrder || 0);
              const bo = Number(b.meta.childOrder || 0);
              if (ao !== bo) return ao - bo;
              return toTimeNum(b.item.updated_at) - toTimeNum(a.item.updated_at);
            })
            .map((x) => x.item);

          const childCounts = Object.create(null);
          for (const child of children) {
            const bucket = taskPrimaryStatus(child);
            childCounts[bucket] = Number(childCounts[bucket] || 0) + 1;
          }
          const masterBucket = taskPrimaryStatus(master);
          const lane = taskLaneFromMasterBucket(masterBucket);
          const masterTs = toTimeNum(master && master.updated_at);
          groups.push({
            key: g.key,
            lane,
            master,
            masterBucket,
            children,
            childCounts,
            childTotal: children.length,
            total: g.members.length,
            latestAt: String((master && master.updated_at) || ""),
            latestTs: masterTs,
          });
        });
      }

      const laneOrder = { "进行中": 0, "待办": 1, "待验收": 2, "已完成": 3, "暂缓": 4, "已归档": 5 };
      groups.sort((a, b) => {
        const ao = Object.prototype.hasOwnProperty.call(laneOrder, a.lane) ? laneOrder[a.lane] : 99;
        const bo = Object.prototype.hasOwnProperty.call(laneOrder, b.lane) ? laneOrder[b.lane] : 99;
        if (ao !== bo) return ao - bo;
        return Number(b.latestTs || -1) - Number(a.latestTs || -1);
      });
      return groups;
    }

    function taskLaneOrderList() {
      return ["进行中", "待办", "待验收", "已完成", "暂缓", "已归档"];
    }

    function taskLaneTone(lane) {
      if (lane === "进行中") return "warn";
      if (lane === "待验收") return "warn";
      if (lane === "待办") return "muted";
      if (lane === "已完成") return "good";
      return "muted";
    }

    function normalizeTaskModule(raw) {
      const v = String(raw || "").trim().toLowerCase();
      if (v === "org") return "org";
      return "tasks";
    }

    function projectScheduleCache(projectId) {
      const pid = String(projectId || "").trim();
      const cached = PROJECT_SCHEDULE_UI.cacheByProject[pid];
      return (cached && typeof cached === "object") ? cached : null;
    }

    function projectScheduleItems(projectId) {
      const cached = projectScheduleCache(projectId);
      const queue = cached && cached.queue && typeof cached.queue === "object" ? cached.queue : {};
      const items = Array.isArray(queue.items) ? queue.items : [];
      return items.map((x) => {
        const row = (x && typeof x === "object") ? Object.assign({}, x) : {};
        row.task_path = normalizeScheduleTaskPath(row.task_path);
        return row;
      });
    }

    function projectScheduleTaskPaths(projectId) {
      return projectScheduleItems(projectId)
        .map((x) => normalizeScheduleTaskPath(x && x.task_path))
        .filter(Boolean);
    }

    function schedulePathTaskStem(rawPath) {
      const p = String(rawPath || "").trim();
      if (!p) return "";
      const name = p.split("/").pop() || "";
      return String(name || "")
        .replace(/\.md$/i, "")
        .replace(/^(?:【[^】]+】\s*)+/g, "")
        .trim();
    }

    function normalizeScheduleTaskPathForProject(projectId, raw) {
      let p = String(raw || "").trim();
      if (!p) return "";
      try { p = decodeURIComponent(p); } catch (_) {}
      p = p.replace(/\\/g, "/");
      p = p.split("#")[0].split("?")[0].trim();
      p = p.replace(/^file:\/+/i, "/");
      p = p.replace(/\/{2,}/g, "/");
      p = p.replace(/^\.\/+/, "");
      p = p.trim().replace(/^\/+/, "");

      // 兼容绝对路径：.../任务规划/... -> 任务规划/...
      // 老数据可能写入本机绝对路径，选中后会导致详情无法命中。
      if (!p.startsWith("任务规划/")) {
        const marker = "/任务规划/";
        const idx = p.indexOf(marker);
        if (idx >= 0) p = p.slice(idx + 1);
      }

      // 兼容旧前端写入的短路径：任务规划/...；若能在当前项目任务池命中，则回填为后端规范全路径。
      if (p.startsWith("任务规划/")) {
        const pid = String(projectId || "").trim();
        const pool = pid && pid !== "overview" ? itemsForProject(pid) : allItems();
        const targetStem = schedulePathTaskStem(p);
        const targetParent = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";
        let stemFallback = "";
        let stemFallbackCount = 0;
        for (const it of (pool || [])) {
          if (!isTaskItem(it)) continue;
          let ip = String((it && it.path) || "").trim();
          if (!ip) continue;
          try { ip = decodeURIComponent(ip); } catch (_) {}
          ip = ip.replace(/\\/g, "/").replace(/\/{2,}/g, "/").replace(/^\.\/+/, "").replace(/^\/+/, "");
          if (!ip) continue;
          if (ip === p || ip.endsWith("/" + p)) return ip;
          if (!targetStem) continue;
          const ipStem = schedulePathTaskStem(ip);
          if (!ipStem || ipStem !== targetStem) continue;
          const ipParent = ip.includes("/") ? ip.slice(0, ip.lastIndexOf("/")) : "";
          if (targetParent && ipParent && (ipParent === targetParent || ipParent.endsWith("/" + targetParent) || targetParent.endsWith("/" + ipParent))) {
            return ip;
          }
          if (!stemFallback) stemFallback = ip;
          stemFallbackCount += 1;
        }
        if (stemFallback && stemFallbackCount === 1) return stemFallback;
      }
      return p;
    }

    function normalizeScheduleTaskPath(raw) {
      return normalizeScheduleTaskPathForProject(String((STATE && STATE.project) || "").trim(), raw);
    }

    function projectScheduleTaskPathSet(projectId) {
      return new Set(projectScheduleTaskPaths(projectId).map((x) => normalizeScheduleTaskPath(x)).filter(Boolean));
    }

    function isTaskInProjectSchedule(projectId, taskPath) {
      const p = normalizeScheduleTaskPath(taskPath);
      if (!p) return false;
      return projectScheduleTaskPathSet(projectId).has(p);
    }

    function taskGroupMasterPathSet(projectId) {
      const pid = String(projectId || "").trim();
      const set = new Set();
      if (!pid || pid === "overview") return set;
      const groups = buildTaskGroups(pid);
      groups.forEach((g) => {
        const path = normalizeScheduleTaskPath(g && g.master && g.master.path);
        if (path) set.add(path);
      });
      return set;
    }

    function isMasterTaskPath(projectId, taskPath) {
      const p = normalizeScheduleTaskPath(taskPath);
      if (!p) return false;
      return taskGroupMasterPathSet(projectId).has(p);
    }

    function taskScheduleProjectIdForItem(it) {
      const pid = String((it && it.project_id) || STATE.project || "").trim();
      if (!pid || pid === "overview") return "";
      return pid;
    }

    function isSchedulableMasterTaskItem(it) {
      if (!it || !isTaskItem(it)) return false;
      const pid = taskScheduleProjectIdForItem(it);
      const path = normalizeScheduleTaskPath(it.path);
      if (!pid || !path) return false;
      return isMasterTaskPath(pid, path);
    }

    function isTaskScheduledByItem(it) {
      const pid = taskScheduleProjectIdForItem(it);
      const path = normalizeScheduleTaskPath(it && it.path);
      if (!pid || !path) return false;
      return isTaskInProjectSchedule(pid, path);
    }

    function bindTaskScheduleDragSource(node, it) {
      return false;
    }

    function createTaskScheduleToggleBtn(it, compact = false) {
      return null;
    }

    function setTaskScheduleDragPayload(taskPath, title) {
      TASK_SCHEDULE_DND.draggingPath = normalizeScheduleTaskPath(taskPath);
      TASK_SCHEDULE_DND.draggingTitle = String(title || "").trim();
      TASK_SCHEDULE_DND.active = !!TASK_SCHEDULE_DND.draggingPath;
      TASK_SCHEDULE_DND.hoveringDropZone = false;
      refreshTaskScheduleDragUi();
    }

    function clearTaskScheduleDragPayload() {
      TASK_SCHEDULE_DND.draggingPath = "";
      TASK_SCHEDULE_DND.draggingTitle = "";
      TASK_SCHEDULE_DND.active = false;
      TASK_SCHEDULE_DND.hoveringDropZone = false;
      refreshTaskScheduleDragUi();
    }

    function ensureTaskScheduleDragOverlay() {
      const existing = document.getElementById("taskScheduleDragOverlay");
      if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
      return null;
    }

    function refreshTaskScheduleDragUi() {
      const body = document.body;
      if (!body) return;
      TASK_SCHEDULE_DND.active = false;
      TASK_SCHEDULE_DND.hoveringDropZone = false;
      TASK_SCHEDULE_DND.draggingPath = "";
      TASK_SCHEDULE_DND.draggingTitle = "";
      body.classList.remove("task-schedule-drag-active");
      body.classList.remove("task-schedule-drag-hovering");
      ensureTaskScheduleDragOverlay();
      const zones = Array.from(document.querySelectorAll("[data-schedule-drop-zone='1']"));
      zones.forEach((zone) => {
        zone.classList.remove("is-drop-target");
        zone.classList.remove("is-drop-active");
        zone.classList.remove("is-drop-ready");
      });
    }

    function setTaskScheduleDropHoverState(node, hovering) {
      const target = node && typeof node.classList !== "undefined" ? node : null;
      if (target) {
        target.classList.toggle("is-drop-active", !!hovering);
        target.classList.toggle("is-drop-ready", !!hovering);
      }
      TASK_SCHEDULE_DND.hoveringDropZone = !!hovering;
      refreshTaskScheduleDragUi();
    }

    function scheduleDraggedTaskPathFromEvent(ev) {
      const e = ev || {};
      const dt = e.dataTransfer;
      const fromDataTransfer = dt
        ? normalizeScheduleTaskPath(
            (typeof dt.getData === "function" && (dt.getData("application/x-task-path") || dt.getData("text/plain"))) || ""
          )
        : "";
      return fromDataTransfer || normalizeScheduleTaskPath(TASK_SCHEDULE_DND.draggingPath);
    }

    function bindCardSelectSemantics(node, onSelect) {
      if (!node || typeof onSelect !== "function") return;
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "button");
      node.classList.add("task-clickable-card");
      const shouldIgnore = (target) => {
        if (!target || typeof target.closest !== "function") return false;
        return !!target.closest("button,select,input,textarea,a,label,summary,details,[contenteditable='true']");
      };
      node.addEventListener("click", (e) => {
        if (shouldIgnore(e && e.target)) return;
        onSelect();
      });
      node.addEventListener("keydown", (e) => {
        const key = e && e.key;
        if (key !== "Enter" && key !== " ") return;
        if (shouldIgnore(e && e.target)) return;
        e.preventDefault();
        e.stopPropagation();
        onSelect();
      });
    }

    function projectScheduleLaneCounts(projectId) {
      const base = { "进行中": 0, "待处理": 0, "待开始": 0, "已完成": 0, "已归档": 0 };
      const cached = projectScheduleCache(projectId);
      const queue = cached && cached.queue && typeof cached.queue === "object" ? cached.queue : {};
      const laneCounts = queue && typeof queue.lane_counts === "object" ? queue.lane_counts : {};
      Object.keys(base).forEach((k) => {
        const n = Number(laneCounts[k]);
        if (Number.isFinite(n) && n >= 0) base[k] = n;
      });
      return base;
    }

    function orgBoardCache(projectId) {
      const pid = String(projectId || "").trim();
      const cached = ORG_BOARD_UI.cacheByProject[pid];
      return (cached && typeof cached === "object") ? cached : null;
    }

    function orgBoardSnapshot(projectId) {
      const cached = orgBoardCache(projectId);
      const graph = cached && cached.graph && typeof cached.graph === "object" ? cached.graph : {};
      const snapshot = graph && graph.org_snapshot && typeof graph.org_snapshot === "object" ? graph.org_snapshot : {};
      return snapshot;
    }

    function orgBoardRuntime(projectId) {
      const cached = orgBoardCache(projectId);
      return (cached && cached.runtime && typeof cached.runtime === "object") ? cached.runtime : {};
    }

    function orgNodeType(row) {
      const r = (row && typeof row === "object") ? row : {};
      const metaType = String((r.meta && r.meta.node_type) || "").trim().toLowerCase();
      if (metaType) return metaType;
      const id = String(r.node_id || "").trim();
      if (id.startsWith("agent:")) return "agent";
      if (id.startsWith("channel:")) return "channel";
      if (id.startsWith("project:")) return "project";
      return "other";
    }

    function normalizeOrgNodeLabel(row) {
      const r = (row && typeof row === "object") ? row : {};
      const label = firstNonEmptyText([r.label, r.name, r.node_id], "节点");
      return String(label || "节点");
    }

    function relationIsActive(rel) {
      const row = (rel && typeof rel === "object") ? rel : {};
      if (row.active === true) return true;
      const exp = firstNonEmptyText([row.expires_at, row.expire_at], "");
      const ts = toTimeNum(exp);
      if (ts > 0) return ts > Date.now();
      return false;
    }

    function findOrgNodeByAgentId(nodes, agentId) {
      const aid = String(agentId || "").trim();
      if (!aid) return null;
      for (const node of (Array.isArray(nodes) ? nodes : [])) {
        if (String((node && node.agent_id) || "").trim() === aid) return node;
      }
      return null;
    }

    function extractOrgLevelTag(text) {
      const s = String(text || "").trim();
      if (!s) return "";
      const m = s.match(/(?:子级|业务|辅助|sub)\s*[-_ ]*0*(\d{1,3})/i);
      if (!m) return "";
      return String(Number(m[1] || 0));
    }

    function buildOrgAgentLookup(nodes) {
      const byAgentId = new Map();
      const byChannelName = new Map();
      const byLevelTag = new Map();
      for (const node of (Array.isArray(nodes) ? nodes : [])) {
        const aid = String((node && node.agent_id) || "").trim();
        if (!aid) continue;
        byAgentId.set(aid, aid);
        const channelName = String(((node && node.meta && node.meta.channel_name) || "")).trim();
        if (channelName) byChannelName.set(channelName, aid);
        const label = String((node && node.label) || "").trim();
        const lv = extractOrgLevelTag(channelName) || extractOrgLevelTag(label);
        if (lv && !byLevelTag.has(lv)) byLevelTag.set(lv, aid);
      }
      return { byAgentId, byChannelName, byLevelTag };
    }

    function resolveRuntimeAgentId(nodes, rel, side, lookup) {
      const key = side === "target" ? "target_agent_id" : "source_agent_id";
      const aidRaw = String((rel && rel[key]) || "").trim();
      if (!aidRaw) return "";
      const maps = (lookup && typeof lookup === "object") ? lookup : buildOrgAgentLookup(nodes);
      if (maps.byAgentId && maps.byAgentId.has(aidRaw)) return aidRaw;

      const channelKey = side === "target" ? "target_channel_name" : "source_channel_name";
      const channelName = String((rel && rel[channelKey]) || "").trim();
      if (channelName && maps.byChannelName && maps.byChannelName.has(channelName)) {
        return String(maps.byChannelName.get(channelName) || "");
      }

      const levelTag = extractOrgLevelTag(aidRaw);
      if (levelTag && maps.byLevelTag && maps.byLevelTag.has(levelTag)) {
        return String(maps.byLevelTag.get(levelTag) || "");
      }
      return aidRaw;
    }

    function labelForRuntimeAgent(nodes, rel, side, lookup) {
      const key = side === "target" ? "target_agent_id" : "source_agent_id";
      const aidRaw = String((rel && rel[key]) || "").trim();
      const aid = resolveRuntimeAgentId(nodes, rel, side, lookup);
      const fallback = String((rel && (side === "target" ? rel.target_channel_name : rel.source_channel_name)) || "").trim();
      const node = findOrgNodeByAgentId(nodes, aid);
      if (node) return normalizeOrgNodeLabel(node);
      return fallback || shortId(aid) || shortId(aidRaw) || "未知节点";
    }

    function labelForAgentId(nodes, agentId) {
      const aid = String(agentId || "").trim();
      if (!aid) return "未知节点";
      const node = findOrgNodeByAgentId(nodes, aid);
      if (node) return normalizeOrgNodeLabel(node);
      return shortId(aid) || aid;
    }


    function taskPushTaskKey(it) {
      const p = String((it && it.project_id) || STATE.project || "").trim();
      const path = String((it && it.path) || "").trim();
      const ch = String((it && it.channel) || STATE.channel || "").trim();
      return [p, path || ch || "unknown"].join("::");
    }

    function normalizeTaskPushAttempt(raw) {
      const a = (raw && typeof raw === "object") ? raw : {};
      return {
        attempt: Number(a.attempt || 0) || 0,
        trigger: String(a.trigger || "").trim(),
        due_at: String(a.due_at || a.dueAt || "").trim(),
        attempted_at: String(a.attempted_at || a.attemptedAt || "").trim(),
        active: !!a.active,
        active_status: String(a.active_status || a.activeStatus || "").trim(),
        active_run_id: String(a.active_run_id || a.activeRunId || "").trim(),
        result: String(a.result || "").trim(),
        run_id: String(a.run_id || a.runId || "").trim(),
        error: String(a.error || "").trim(),
      };
    }

    function normalizeTaskPushItem(raw) {
      const obj = (raw && typeof raw === "object") ? raw : {};
      const st0 = (obj.status && typeof obj.status === "object") ? obj.status : obj;
      const target0 = (st0.target && typeof st0.target === "object") ? st0.target : {};
      const attemptsRaw = Array.isArray(obj.attempts) ? obj.attempts : [];
      const attempts = attemptsRaw.map(normalizeTaskPushAttempt);
      const status = {
        job_id: String(st0.job_id || st0.jobId || "").trim(),
        project_id: String(st0.project_id || st0.projectId || "").trim(),
        mode: String(st0.mode || "").trim().toLowerCase(),
        status: String(st0.status || "").trim().toLowerCase(),
        created_at: String(st0.created_at || st0.createdAt || "").trim(),
        updated_at: String(st0.updated_at || st0.updatedAt || "").trim(),
        scheduled_at: String(st0.scheduled_at || st0.scheduledAt || "").trim(),
        next_due_at: String(st0.next_due_at || st0.nextDueAt || "").trim(),
        finished_at: String(st0.finished_at || st0.finishedAt || "").trim(),
        canceled_at: String(st0.canceled_at || st0.canceledAt || "").trim(),
        max_attempts: Number(st0.max_attempts || st0.maxAttempts || 0) || 0,
        attempt_count: Number(st0.attempt_count || st0.attemptCount || attempts.length || 0) || 0,
        last_result: String(st0.last_result || st0.lastResult || "").trim(),
        last_run_id: String(st0.last_run_id || st0.lastRunId || "").trim(),
        last_error: String(st0.last_error || st0.lastError || "").trim(),
        retryable: !!st0.retryable,
        target: {
          channel_name: String(target0.channel_name || target0.channelName || "").trim(),
          session_id: String(target0.session_id || target0.sessionId || "").trim(),
        },
      };
      return { status, attempts };
    }

    function taskPushStatusLabel(st) {
      const s = String(st || "").trim().toLowerCase();
      return ({
        created: "已创建",
        scheduled: "已计划",
        retry_waiting: "等待重试",
        skipped_active: "已跳过（会话活跃）",
        dispatched: "已发出",
        exhausted: "重试耗尽",
        canceled: "已取消",
        error: "异常",
      })[s] || (s || "未知");
    }

    function taskPushStatusTone(st) {
      const s = String(st || "").trim().toLowerCase();
      if (s === "dispatched") return "good";
      if (s === "error" || s === "exhausted") return "bad";
      if (s === "skipped_active") return "warn";
      if (s === "scheduled" || s === "retry_waiting" || s === "created") return "warn";
      return "muted";
    }

    function taskPushHasPlannedRetry(statusObj) {
      const st = (statusObj && typeof statusObj === "object") ? statusObj : {};
      const s = String(st.status || "").trim().toLowerCase();
      const hasNext = !!String(st.next_due_at || "").trim();
      if (!hasNext) return false;
      return s === "scheduled" || s === "retry_waiting" || s === "created";
    }

    function taskPushIsImmediateActiveSkipPlaceholder(item) {
      const st = (item && item.status) || {};
      const mode = String(st.mode || "").trim().toLowerCase();
      const status = String(st.status || "").trim().toLowerCase();
      if (mode !== "immediate") return false;
      if (status !== "retry_waiting" && status !== "created") return false;
      if (taskPushHasPlannedRetry(st)) return false;
      const attempts = Array.isArray(item && item.attempts) ? item.attempts : [];
      const last = attempts.length ? attempts[attempts.length - 1] : null;
      const lastResult = String((last && last.result) || st.last_result || "").trim().toLowerCase();
      return lastResult === "skipped_active";
    }

    function taskPushDisplayStatusLabel(item) {
      if (taskPushIsImmediateActiveSkipPlaceholder(item)) return "已跳过（会话活跃）";
      return taskPushStatusLabel(item && item.status && item.status.status);
    }

    function taskPushDisplayStatusTone(item) {
      if (taskPushIsImmediateActiveSkipPlaceholder(item)) return "warn";
      return taskPushStatusTone(item && item.status && item.status.status);
    }

    function taskAutoKickoffStateForTask(it) {
      const latest = taskPushFindLatestForTask(it);
      const st = (latest && latest.status && typeof latest.status === "object") ? latest.status : {};
      const rawStatus = String(st.status || "").trim().toLowerCase();
      const lastResult = String(st.last_result || "").trim().toLowerCase();
      const hasRetryPlan = taskPushHasPlannedRetry(st);
      const isDispatched = rawStatus === "dispatched" || lastResult === "dispatched";
      const activeToSchedule = hasRetryPlan
        || rawStatus === "retry_waiting"
        || rawStatus === "scheduled"
        || taskPushIsImmediateActiveSkipPlaceholder(latest)
        || lastResult === "skipped_active";
      const failed = rawStatus === "error"
        || rawStatus === "exhausted"
        || rawStatus === "canceled"
        || lastResult === "dispatch_error";

      if (!latest) {
        return {
          key: "need_takeover",
          label: "失败待接管",
          tone: "bad",
          desc: "未检测到自动派发记录，请手动接管。",
          latest: null,
          status: st,
          allowTakeover: true,
        };
      }
      if (isDispatched) {
        return {
          key: "dispatched",
          label: "已派发",
          tone: "good",
          desc: "自动派发已成功投递到目标会话。",
          latest,
          status: st,
          allowTakeover: false,
        };
      }
      if (activeToSchedule) {
        return {
          key: "active_retry",
          label: "命中活跃转定时",
          tone: "warn",
          desc: "目标会话活跃，系统已转入定时重试链路。",
          latest,
          status: st,
          allowTakeover: false,
        };
      }
      if (failed) {
        return {
          key: "need_takeover",
          label: "失败待接管",
          tone: "bad",
          desc: "自动派发未成功，需要手动接管。",
          latest,
          status: st,
          allowTakeover: true,
        };
      }
      return {
        key: "pending",
        label: "派发处理中",
        tone: "muted",
        desc: "派发状态回写中，请稍后刷新。",
        latest,
        status: st,
        allowTakeover: false,
      };
    }

    function normalizeTaskPlanTask(raw) {
      const t = (raw && typeof raw === "object") ? raw : {};
      const dependsOn = Array.isArray(t.depends_on)
        ? t.depends_on
        : (Array.isArray(t.dependsOn) ? t.dependsOn : []);
      return {
        task_id: String(t.task_id || t.taskId || "").trim(),
        parent_task_id: String(t.parent_task_id || t.parentTaskId || "").trim(),
        task_path: String(t.task_path || t.taskPath || "").trim(),
        group_key: String(t.group_key || t.groupKey || "").trim(),
        task_role: String(t.task_role || t.taskRole || "single").trim().toLowerCase() || "single",
        depends_on: dependsOn.map((x) => String(x || "").trim()).filter(Boolean),
        channel_name: String(t.channel_name || t.channelName || "").trim(),
        session_id: String(t.session_id || t.sessionId || "").trim(),
        dispatch_mode: String(t.dispatch_mode || t.dispatchMode || "immediate").trim().toLowerCase() || "immediate",
        scheduled_at: String(t.scheduled_at || t.scheduledAt || "").trim(),
        status: String(t.status || "planned").trim().toLowerCase() || "planned",
        dispatch_state: String(t.dispatch_state || t.dispatchState || "").trim().toLowerCase(),
        job_id: String(t.job_id || t.jobId || "").trim(),
        run_id: String(t.run_id || t.runId || "").trim(),
        last_error: String(t.last_error || t.lastError || "").trim(),
      };
    }

    function normalizeTaskPlanBatch(raw) {
      const b = (raw && typeof raw === "object") ? raw : {};
      const tasksRaw = Array.isArray(b.tasks) ? b.tasks : [];
      return {
        batch_id: String(b.batch_id || b.batchId || "").trim(),
        order_index: Number(b.order_index || b.orderIndex || 0) || 0,
        name: String(b.name || "").trim(),
        status: String(b.status || "planned").trim().toLowerCase() || "planned",
        activate_when: String(b.activate_when || b.activateWhen || "manual").trim().toLowerCase() || "manual",
        planned_start_at: String(b.planned_start_at || b.plannedStartAt || "").trim(),
        planned_end_at: String(b.planned_end_at || b.plannedEndAt || "").trim(),
        tasks: tasksRaw.map(normalizeTaskPlanTask),
      };
    }
