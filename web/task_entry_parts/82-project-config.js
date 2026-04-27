    const PROJECT_CONFIG_UI = {
      open: false,
      loading: false,
      saving: false,
      projectId: "",
      error: "",
      note: "",
      cache: Object.create(null),
      sessionStats: Object.create(null),
      liveHealth: null,
      draft: null,
      shareDraft: null,
      shareAdvancedOpen: false,
      shareEditorOpen: false,
      shareEditorMode: "create",
      shareEditorOriginalId: "",
      shareEditorDraft: null,
      shareEditorAdvancedOpen: false,
      activeSection: "config",
      renderHooked: false,
    };

    function projectConfigBtnNode() {
      return document.getElementById("projectConfigBtn");
    }

    function shareProjectBtnNode() {
      return document.getElementById("shareProjectBtn");
    }

    function projectConfigMaskNode() {
      return document.getElementById("projectConfigMask");
    }

    function projectConfigBodyNode() {
      return document.getElementById("projectConfigBody");
    }

    function currentProjectConfigProjectId() {
      const pid = String((STATE && STATE.project) || "").trim();
      return pid && pid !== "overview" ? pid : "";
    }

    function normalizeProjectConfigProfile(raw, fallback = "") {
      const txt = String(raw == null ? "" : raw).trim().toLowerCase();
      if (txt === "sandboxed" || txt === "privileged" || txt === "project_privileged_full") return txt;
      return String(fallback || "").trim().toLowerCase();
    }

    function projectConfigProfileMeta(raw) {
      const profile = normalizeProjectConfigProfile(raw, "sandboxed") || "sandboxed";
      if (profile === "project_privileged_full") {
        return {
          value: "project_privileged_full",
          tone: "warn",
          optionLabel: "project_privileged_full · 完全放开（当前用户态）",
          summary: "后续新发起的 CCB 执行会按当前用户态直接放开，不再继续按目录补权限，默认覆盖项目、Codex 会话、本地服务集成和本机管理动作。",
          effect: "适合你要直接开干的场景；选中后新 run 不再走细碎权限补救，但不会回头改变已在运行的会话。",
        };
      }
      if (profile === "privileged") {
        return {
          value: "privileged",
          tone: "warn",
          optionLabel: "privileged · 真实仓执行（可发布/重启）",
          summary: "后续新发起的 CCB 执行会直接使用项目真实 worktree_root 与真实运行目录，不再走受限 mirror。",
          effect: "适合发布、重启、静态产物重建等需要真实写权限的动作；不会给已在运行的会话即时提权。",
        };
      }
      return {
        value: "sandboxed",
        tone: "info",
        optionLabel: "sandboxed · 受限执行（默认更安全）",
        summary: "后续新发起的 CCB 执行继续走受限 runner / mirror，适合分析、排查、普通协作。",
        effect: "默认更安全；需要真实仓修改、launchctl、发布安装时不适用。",
      };
    }

    function normalizeProjectConfigExecutionContext(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return {
        profile: normalizeProjectConfigProfile(firstNonEmptyText([src.profile, src.execution_profile, src.executionProfile]), ""),
        environment: normalizeEnvironmentName(firstNonEmptyText([src.environment, src.environmentName, "stable"])),
        worktree_root: firstNonEmptyText([src.worktree_root, src.worktreeRoot]),
        workdir: firstNonEmptyText([src.workdir]),
        branch: firstNonEmptyText([src.branch]),
        runtime_root: firstNonEmptyText([src.runtime_root, src.runtimeRoot]),
        sessions_root: firstNonEmptyText([src.sessions_root, src.sessionsRoot]),
        runs_root: firstNonEmptyText([src.runs_root, src.runsRoot]),
        server_port: firstNonEmptyText([src.server_port, src.serverPort]),
        health_source: firstNonEmptyText([src.health_source, src.healthSource]),
        configured: !!src.configured,
        context_source: String(firstNonEmptyText([src.context_source, src.contextSource]) || "").trim().toLowerCase(),
      };
    }

    function normalizeProjectShareSpace(raw, projectId) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const spaces = Array.isArray(src.spaces) ? src.spaces : [];
      const summaries = Array.isArray(src.summaries) ? src.summaries : [];
      const summaryById = new Map();
      summaries.forEach((item) => {
        if (!item || typeof item !== "object") return;
        const shareId = String(firstNonEmptyText([item.share_id, item.shareId, item.id]) || "").trim();
        if (shareId) summaryById.set(shareId, item);
      });
      const normalizeSpace = (item) => {
        const shareId = String(firstNonEmptyText([item.share_id, item.shareId, item.id]) || "").trim();
        const summary = summaryById.get(shareId) || {};
        const allowedSessionIds = Array.isArray(item.allowed_session_ids)
          ? item.allowed_session_ids.map((it) => String(it || "").trim()).filter(Boolean)
          : String(firstNonEmptyText([item.allowed_session_ids, item.allowedSessionIds, item.session_ids]) || "")
            .split(",")
            .map((it) => it.trim())
            .filter(Boolean);
        return {
          share_id: shareId,
          project_id: String(firstNonEmptyText([item.project_id, item.projectId, summary.project_id, summary.projectId, projectId]) || "").trim(),
          name: String(firstNonEmptyText([item.name, summary.name]) || "").trim(),
          title: String(firstNonEmptyText([item.title, summary.title, item.name, summary.name]) || "").trim(),
          allowed_session_ids: allowedSessionIds,
          allowed_session_count: Number(firstNonEmptyText([item.allowed_session_count, item.allowedSessionCount, summary.allowed_session_count, summary.allowedSessionCount]) || allowedSessionIds.length || 0) || 0,
          access_token: String(firstNonEmptyText([item.access_token, item.accessToken]) || "").trim(),
          passcode: String(firstNonEmptyText([item.passcode]) || "").trim(),
          expires_at: String(firstNonEmptyText([item.expires_at, item.expiresAt, summary.expires_at, summary.expiresAt]) || "").trim(),
          revoked_at: String(firstNonEmptyText([item.revoked_at, item.revokedAt, summary.revoked_at, summary.revokedAt]) || "").trim(),
          disabled_at: String(firstNonEmptyText([item.disabled_at, item.disabledAt, summary.disabled_at, summary.disabledAt]) || "").trim(),
          deleted_at: String(firstNonEmptyText([item.deleted_at, item.deletedAt, summary.deleted_at, summary.deletedAt]) || "").trim(),
          enabled: item.enabled !== false && summary.enabled !== false,
          status: String(firstNonEmptyText([item.status, summary.status]) || "").trim().toLowerCase(),
          created_at: String(firstNonEmptyText([item.created_at, item.createdAt, summary.created_at, summary.createdAt]) || "").trim(),
          updated_at: String(firstNonEmptyText([item.updated_at, item.updatedAt, summary.updated_at, summary.updatedAt]) || "").trim(),
          network_scope: String(firstNonEmptyText([item.network_scope, item.networkScope, summary.network_scope, summary.networkScope, "lan_only"]) || "lan_only").trim(),
          permission: String(firstNonEmptyText([item.permission, summary.permission, "read_send"]) || "read_send").trim(),
        };
      };
      return {
        schema_version: String(firstNonEmptyText([src.schema_version, src.schemaVersion, "share_space.v1"]) || "share_space.v1"),
        project_id: String(firstNonEmptyText([src.project_id, src.projectId, projectId]) || "").trim(),
        enabled: !!src.enabled,
        storage_mode: String(firstNonEmptyText([src.storage_mode, src.storageMode, "runtime_local"]) || "runtime_local"),
        storage_path: String(firstNonEmptyText([src.storage_path, src.storagePath]) || "").trim(),
        active_count: Number(src.active_count || src.activeCount || 0) || 0,
        deleted_count: Number(src.deleted_count || src.deletedCount || 0) || 0,
        count: Number(src.count || spaces.length || summaries.length || 0) || 0,
        updated_at: String(firstNonEmptyText([src.updated_at, src.updatedAt]) || "").trim(),
        summaries: summaries.filter((item) => item && typeof item === "object").map(normalizeSpace),
        spaces: (spaces.length ? spaces : summaries).filter((item) => item && typeof item === "object").map(normalizeSpace),
      };
    }

    function defaultShareIdForProject(projectId) {
      const raw = String(projectId || "project").trim().toLowerCase();
      const safe = raw.replace(/[^0-9a-z_.-]+/g, "-").replace(/^-+|-+$/g, "");
      return (safe || "project") + "-share";
    }

    function randomShareToken() {
      const bytes = new Uint8Array(18);
      if (window.crypto && window.crypto.getRandomValues) {
        window.crypto.getRandomValues(bytes);
        return Array.from(bytes).map((b) => b.toString(36).padStart(2, "0")).join("").slice(0, 32);
      }
      return Math.random().toString(36).slice(2) + Date.now().toString(36);
    }

    function projectShareSpacesFromPayload(projectId, payload) {
      const shareSpace = normalizeProjectShareSpace(payload && payload.share_space, projectId);
      return Array.isArray(shareSpace.spaces) ? shareSpace.spaces : [];
    }

    function uniqueProjectShareId(projectId, payload) {
      const existing = new Set(projectShareSpacesFromPayload(projectId, payload).map((item) => String(item.share_id || "").trim()).filter(Boolean));
      const base = defaultShareIdForProject(projectId).replace(/-share$/, "") + "-share";
      if (!existing.has(base)) return base;
      for (let i = 2; i < 100; i += 1) {
        const candidate = base + "-" + i;
        if (!existing.has(candidate)) return candidate;
      }
      return base + "-" + Date.now().toString(36);
    }

    function buildProjectShareSpaceDraft(projectId, payload, source) {
      const shareSpace = normalizeProjectShareSpace(payload && payload.share_space, projectId);
      const first = (source && typeof source === "object") ? source : (shareSpace.spaces[0] || {});
      const shareId = String(first.share_id || uniqueProjectShareId(projectId, payload)).trim();
      return {
        enabled: first.enabled !== false,
        share_id: shareId,
        name: String(first.name || first.title || "共享对象").trim(),
        title: String(first.title || first.name || ((projectById(projectId) || {}).name || projectId || "项目共享空间")).trim(),
        allowed_session_ids: Array.isArray(first.allowed_session_ids) ? [...first.allowed_session_ids] : [],
        access_token: String(first.access_token || randomShareToken()).trim(),
        passcode: String(first.passcode || "").trim(),
        expires_at: String(first.expires_at || "").trim(),
        revoked_at: String(first.revoked_at || "").trim(),
        disabled_at: String(first.disabled_at || "").trim(),
        deleted_at: String(first.deleted_at || "").trim(),
        network_scope: String(first.network_scope || "lan_only").trim() || "lan_only",
        permission: String(first.permission || "read_send").trim() || "read_send",
      };
    }

    function normalizeProjectShareOrigin(raw) {
      const text = String(raw || "").trim();
      if (!text) return "";
      try {
        const target = /^https?:\/\//i.test(text) ? text : ("http://" + text.replace(/^\/+/, ""));
        return new URL(target).origin;
      } catch (_error) {
        return "";
      }
    }

    function projectSharePagePath() {
      const links = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
      const base = String(firstNonEmptyText([
        links.task_page,
        DATA && DATA.task_page,
        links.project_chat_page,
        DATA && DATA.project_chat_page,
        links.share_space_page,
        DATA && DATA.share_space_page,
        "/share/project-task-dashboard.html",
      ]) || "/share/project-task-dashboard.html").trim();
      if (/^https?:\/\//i.test(base)) {
        try {
          const parsed = new URL(base);
          return String(parsed.pathname || "/share/project-task-dashboard.html").trim() || "/share/project-task-dashboard.html";
        } catch (_error) {
          return "/share/project-task-dashboard.html";
        }
      }
      return base.startsWith("/") ? base : "/share/" + base.replace(/^\/+/, "");
    }

    function projectShareCurrentOrigin() {
      const health = (PROJECT_CONFIG_UI.liveHealth && typeof PROJECT_CONFIG_UI.liveHealth === "object") ? PROJECT_CONFIG_UI.liveHealth : {};
      const liveOrigin = normalizeProjectShareOrigin(firstNonEmptyText([health.publicOrigin, health.public_origin]));
      if (liveOrigin) return liveOrigin;
      return normalizeProjectShareOrigin(window.location.origin) || window.location.origin;
    }

    function projectShareSpacePageHref(projectId, draft) {
      const url = new URL(projectSharePagePath(), projectShareCurrentOrigin());
      url.searchParams.set("project_id", String(projectId || "").trim());
      url.searchParams.set("share_id", String((draft && draft.share_id) || "").trim());
      if (draft && draft.access_token) url.searchParams.set("token", String(draft.access_token).trim());
      return url.toString();
    }

    function projectShareSpacePayload(projectId, draft) {
      const src = (draft && typeof draft === "object") ? draft : {};
      return {
        share_id: String(src.share_id || defaultShareIdForProject(projectId)).trim(),
        name: String(src.name || src.title || "共享对象").trim(),
        title: String(src.title || src.name || "项目共享空间").trim(),
        allowed_session_ids: Array.isArray(src.allowed_session_ids) ? src.allowed_session_ids.map((it) => String(it || "").trim()).filter(Boolean) : [],
        access_token: String(src.access_token || randomShareToken()).trim(),
        passcode: String(src.passcode || "").trim(),
        expires_at: String(src.expires_at || "").trim(),
        revoked_at: String(src.revoked_at || "").trim(),
        disabled_at: String(src.disabled_at || "").trim(),
        deleted_at: String(src.deleted_at || "").trim(),
        enabled: src.enabled !== false,
        network_scope: "lan_only",
        permission: String(src.permission || "read_send").trim() || "read_send",
      };
    }

    function normalizeProjectConfigPayload(projectId, payload) {
      const body = (payload && typeof payload === "object") ? payload : {};
      const project = (body.project && typeof body.project === "object") ? body.project : {};
      return {
        project_id: String(projectId || "").trim(),
        config_path: firstNonEmptyText([body.config_path, body.configPath]),
        status: (project.status && typeof project.status === "object") ? project.status : {},
        execution_context: normalizeProjectConfigExecutionContext(project.execution_context || project.executionContext || null),
        share_space: normalizeProjectShareSpace(project.share_space || project.shareSpace || body.share_space || body.shareSpace || null, projectId),
        fetched_at: new Date().toISOString(),
        raw: body,
      };
    }

    function buildFallbackProjectConfigPayload(projectId) {
      const pid = String(projectId || "").trim();
      const project = projectById(pid) || {};
      const execMeta = buildProjectExecutionContextMeta(
        (project && project.project_execution_context) || null
      );
      const target = normalizeProjectExecutionContextRef(execMeta.target || null);
      const source = normalizeProjectExecutionContextRef(execMeta.source || null);
      return {
        project_id: pid,
        config_path: "",
        status: {},
        execution_context: normalizeProjectConfigExecutionContext({
          profile: firstNonEmptyText([
            project && project.execution_context && project.execution_context.profile,
            project && project.executionContext && project.executionContext.profile,
            project && project.execution_profile,
          ]),
          environment: firstNonEmptyText([target.environment, source.environment, project.environment, "stable"]),
          worktree_root: firstNonEmptyText([target.worktree_root, source.worktree_root, project.worktree_root]),
          workdir: firstNonEmptyText([target.workdir, source.workdir, project.workdir]),
          branch: firstNonEmptyText([target.branch, source.branch, project.branch]),
          runtime_root: firstNonEmptyText([project.runtime_root]),
          sessions_root: firstNonEmptyText([project.sessions_root]),
          runs_root: firstNonEmptyText([project.runs_root]),
          server_port: firstNonEmptyText([project.server_port]),
          health_source: firstNonEmptyText([project.health_source]),
          configured: execMeta.available,
          context_source: execMeta.available ? (execMeta.context_source || "project") : "project",
        }),
        fetched_at: new Date().toISOString(),
        raw: {
          project: {
            execution_context: {
              profile: firstNonEmptyText([
                project && project.execution_context && project.execution_context.profile,
                project && project.executionContext && project.executionContext.profile,
                project && project.execution_profile,
              ]),
              environment: firstNonEmptyText([target.environment, source.environment, project.environment, "stable"]),
              worktree_root: firstNonEmptyText([target.worktree_root, source.worktree_root, project.worktree_root]),
              workdir: firstNonEmptyText([target.workdir, source.workdir, project.workdir]),
              branch: firstNonEmptyText([target.branch, source.branch, project.branch]),
            },
          },
        },
      };
    }

    function buildProjectLevelExecutionContext(projectId, executionContext) {
      const ctx = normalizeProjectConfigExecutionContext(executionContext);
      return {
        target: {
          project_id: String(projectId || "").trim(),
          environment: ctx.environment,
          worktree_root: ctx.worktree_root,
          workdir: ctx.workdir || ctx.worktree_root,
          branch: ctx.branch,
        },
        source: {
          project_id: String(projectId || "").trim(),
          environment: ctx.environment,
          worktree_root: ctx.worktree_root,
          workdir: ctx.workdir || ctx.worktree_root,
          branch: ctx.branch,
        },
        context_source: ctx.context_source || "project",
        override: {
          applied: false,
          fields: [],
        },
      };
    }

    function syncProjectConfigToLocal(projectId, payload) {
      const pid = String(projectId || "").trim();
      const project = projectById(pid);
      if (!project || !payload) return;
      const ctx = normalizeProjectConfigExecutionContext(payload.execution_context || null);
      project.execution_context = { ...ctx };
      project.project_execution_context = buildProjectLevelExecutionContext(pid, ctx);
      project.environment = ctx.environment || project.environment;
      if (ctx.worktree_root) project.worktree_root = ctx.worktree_root;
      if (ctx.workdir) project.workdir = ctx.workdir;
      if (ctx.branch) project.branch = ctx.branch;
      if (ctx.runtime_root) project.runtime_root = ctx.runtime_root;
      if (ctx.sessions_root) project.sessions_root = ctx.sessions_root;
      if (ctx.runs_root) project.runs_root = ctx.runs_root;
      if (ctx.server_port) project.server_port = ctx.server_port;
      if (ctx.health_source) project.health_source = ctx.health_source;
    }

    function ensureProjectConfigDrawerNodes() {
      if (projectConfigMaskNode()) return;
      const mask = el("div", {
        class: "project-config-mask",
        id: "projectConfigMask",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": "项目配置",
      });
      const drawer = el("aside", { class: "project-config-drawer", role: "document" });
      const head = el("div", { class: "project-config-head" });
      const titleWrap = el("div", { class: "project-config-titlewrap" });
      titleWrap.appendChild(el("div", { class: "project-config-kicker", text: "Project Configuration" }));
      titleWrap.appendChild(el("div", { class: "project-config-title", id: "projectConfigTitle", text: "项目配置" }));
      titleWrap.appendChild(el("div", {
        class: "project-config-sub",
        id: "projectConfigSub",
        text: "项目配置负责真源默认上下文；Session 弹框只展示继承结果与少量显式例外。",
      }));
      head.appendChild(titleWrap);
      const actions = el("div", { class: "project-config-actions" });
      actions.appendChild(el("button", { class: "btn", id: "projectConfigReloadBtn", type: "button", text: "重新读取" }));
      actions.appendChild(el("button", { class: "btn primary", id: "projectConfigSaveBtn", type: "button", text: "保存并校验" }));
      actions.appendChild(el("button", { class: "btn", id: "projectConfigCloseBtn", type: "button", text: "关闭" }));
      head.appendChild(actions);
      drawer.appendChild(head);
      drawer.appendChild(el("div", { class: "project-config-body", id: "projectConfigBody" }));
      mask.appendChild(drawer);
      mask.addEventListener("click", (event) => {
        if (event && event.target === mask) closeProjectConfigDrawer();
      });
      document.body.appendChild(mask);
      const closeBtn = document.getElementById("projectConfigCloseBtn");
      if (closeBtn) closeBtn.addEventListener("click", closeProjectConfigDrawer);
      const reloadBtn = document.getElementById("projectConfigReloadBtn");
      if (reloadBtn) reloadBtn.addEventListener("click", () => {
        const pid = currentProjectConfigProjectId();
        if (!pid) return;
        void loadProjectConfigData(pid, { force: true, preserveMessage: false });
      });
      const saveBtn = document.getElementById("projectConfigSaveBtn");
      if (saveBtn) saveBtn.addEventListener("click", () => {
        if (PROJECT_CONFIG_UI.activeSection === "share") void saveProjectShareSpaceDraft();
        else void saveProjectConfigDraft();
      });
      document.addEventListener("keydown", (event) => {
        if (!PROJECT_CONFIG_UI.open) return;
        if (event && event.key === "Escape") closeProjectConfigDrawer();
      });
    }

    function updateProjectConfigButtonState() {
      const btn = projectConfigBtnNode();
      const shareBtn = shareProjectBtnNode();
      const pid = currentProjectConfigProjectId();
      const enabled = !!pid;
      if (btn) {
        btn.disabled = !enabled;
        btn.style.display = enabled ? "" : "none";
        btn.classList.toggle("active", !!PROJECT_CONFIG_UI.open && enabled && PROJECT_CONFIG_UI.activeSection !== "share");
        btn.title = enabled ? "打开 项目配置" : "总览视图不提供项目配置";
      }
      if (shareBtn) {
        shareBtn.disabled = !enabled;
        shareBtn.style.display = enabled ? "" : "none";
        shareBtn.classList.toggle("active", !!PROJECT_CONFIG_UI.open && enabled && PROJECT_CONFIG_UI.activeSection === "share");
        shareBtn.title = enabled ? "打开 分享项目" : "总览视图不提供分享项目";
      }
    }

    function hookProjectConfigIntoRender() {
      if (PROJECT_CONFIG_UI.renderHooked || typeof render !== "function") return;
      PROJECT_CONFIG_UI.renderHooked = true;
      const originalRender = render;
      render = function() {
        const result = originalRender.apply(this, arguments);
        updateProjectConfigButtonState();
        if (PROJECT_CONFIG_UI.open) {
          const pid = currentProjectConfigProjectId();
          if (pid && pid !== PROJECT_CONFIG_UI.projectId) {
            PROJECT_CONFIG_UI.projectId = pid;
            void loadProjectConfigData(pid, { force: true, preserveMessage: true });
          } else {
            renderProjectConfigDrawer();
          }
        }
        return result;
      };
    }

    async function fetchProjectContextStats(projectId, force = false) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      if (!force && PROJECT_CONFIG_UI.sessionStats[pid]) return PROJECT_CONFIG_UI.sessionStats[pid];
      const params = new URLSearchParams();
      params.set("project_id", pid);
      const resp = await fetch("/api/sessions?" + params.toString(), {
        headers: authHeaders(),
        cache: "no-store",
      });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      const payload = await resp.json().catch(() => ({}));
      const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
      const stats = {
        total: sessions.length,
        bound: 0,
        override: 0,
        drift: 0,
        unbound: 0,
      };
      sessions.forEach((session) => {
        const status = resolveConversationContextStatus(session);
        if (status.kind === "bound") stats.bound += 1;
        else if (status.kind === "drift") stats.drift += 1;
        else stats.unbound += 1;
        const execMeta = buildProjectExecutionContextMeta(
          session && (session.project_execution_context || session.projectExecutionContext || null)
        );
        if (execMeta.overrideApplied) stats.override += 1;
      });
      PROJECT_CONFIG_UI.sessionStats[pid] = stats;
      return stats;
    }

    async function fetchProjectConfigHealth(force = false) {
      if (!force && PROJECT_CONFIG_UI.liveHealth) return PROJECT_CONFIG_UI.liveHealth;
      const resp = await fetch("/__health", { cache: "no-store" });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      PROJECT_CONFIG_UI.liveHealth = await resp.json().catch(() => ({}));
      return PROJECT_CONFIG_UI.liveHealth;
    }

    async function refreshProjectShareRuntimeHealth() {
      try {
        await fetchProjectConfigHealth(true);
      } catch (_error) {
        return PROJECT_CONFIG_UI.liveHealth;
      }
      if (PROJECT_CONFIG_UI.open) renderProjectConfigDrawer();
      return PROJECT_CONFIG_UI.liveHealth;
    }

    async function loadProjectConfigData(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid) return;
      PROJECT_CONFIG_UI.projectId = pid;
      PROJECT_CONFIG_UI.loading = true;
      if (!(opts && opts.preserveMessage)) {
        PROJECT_CONFIG_UI.error = "";
        PROJECT_CONFIG_UI.note = "";
      }
      renderProjectConfigDrawer();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/config", {
          headers: authHeaders(),
          cache: "no-store",
        });
        if (!resp.ok) {
          if (resp.status === 404) {
            const fallback = buildFallbackProjectConfigPayload(pid);
            PROJECT_CONFIG_UI.cache[pid] = fallback;
            PROJECT_CONFIG_UI.draft = { ...fallback.execution_context };
            PROJECT_CONFIG_UI.shareDraft = buildProjectShareSpaceDraft(pid, fallback);
            syncProjectConfigToLocal(pid, fallback);
            PROJECT_CONFIG_UI.note = "现网服务尚未返回项目配置接口，当前先按静态 project_execution_context 回退展示；保存能力待后端 live 加载后生效。";
            const results = await Promise.allSettled([
              fetchProjectContextStats(pid, !!(opts && opts.force)),
              fetchProjectConfigHealth(!!(opts && opts.force)),
            ]);
            if (results[0] && results[0].status === "rejected") {
              PROJECT_CONFIG_UI.note += " 会话统计读取失败。";
            }
            if (results[1] && results[1].status === "rejected") {
              PROJECT_CONFIG_UI.note += " 服务探活读取失败。";
            }
            return;
          }
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const payload = normalizeProjectConfigPayload(pid, await resp.json().catch(() => ({})));
        PROJECT_CONFIG_UI.cache[pid] = payload;
        PROJECT_CONFIG_UI.draft = { ...payload.execution_context };
        PROJECT_CONFIG_UI.shareDraft = buildProjectShareSpaceDraft(pid, payload);
        syncProjectConfigToLocal(pid, payload);
        const results = await Promise.allSettled([
          fetchProjectContextStats(pid, !!(opts && opts.force)),
          fetchProjectConfigHealth(!!(opts && opts.force)),
        ]);
        if (results[0] && results[0].status === "rejected") {
          PROJECT_CONFIG_UI.note = "会话统计读取失败：" + String(results[0].reason && results[0].reason.message || results[0].reason || "");
        }
        if (results[1] && results[1].status === "rejected") {
          const msg = "服务探活读取失败：" + String(results[1].reason && results[1].reason.message || results[1].reason || "");
          PROJECT_CONFIG_UI.note = PROJECT_CONFIG_UI.note ? (PROJECT_CONFIG_UI.note + "；" + msg) : msg;
        }
      } catch (error) {
        PROJECT_CONFIG_UI.error = "读取项目配置失败：" + String((error && error.message) || error || "未知错误");
      } finally {
        PROJECT_CONFIG_UI.loading = false;
        renderProjectConfigDrawer();
      }
    }

    function projectConfigFieldValue(key) {
      const draft = (PROJECT_CONFIG_UI.draft && typeof PROJECT_CONFIG_UI.draft === "object") ? PROJECT_CONFIG_UI.draft : {};
      return String(draft[key] == null ? "" : draft[key]);
    }

    function setProjectConfigDraftField(key, value) {
      if (!PROJECT_CONFIG_UI.draft || typeof PROJECT_CONFIG_UI.draft !== "object") {
        PROJECT_CONFIG_UI.draft = {};
      }
      PROJECT_CONFIG_UI.draft[key] = String(value == null ? "" : value);
    }

    function buildProjectConfigOverviewSection(project, payload, stats, health) {
      const ctx = normalizeProjectConfigExecutionContext(payload && payload.execution_context);
      const profileMeta = projectConfigProfileMeta(ctx.profile || "sandboxed");
      const section = el("section", { class: "project-config-section hero" });
      const head = el("div", { class: "project-config-section-head" });
      const titleWrap = el("div", { class: "project-config-section-titlewrap" });
      titleWrap.appendChild(el("div", { class: "project-config-section-title", text: "总览" }));
      titleWrap.appendChild(el("div", {
        class: "project-config-section-sub",
        text: "项目配置回答“项目应该跑在哪里”；Session 与 Run 只展示最终继承结果。",
      }));
      head.appendChild(titleWrap);
      section.appendChild(head);

      const chips = el("div", { class: "project-config-chip-row" });
      const sourceMeta = executionContextSourceMeta(ctx.context_source || "project");
      chips.appendChild(el("span", {
        class: "project-config-chip " + String(sourceMeta.tone || "muted"),
        text: "真源: " + String(sourceMeta.text || "待返回"),
      }));
      chips.appendChild(el("span", {
        class: "project-config-chip " + (isStableEnvironment(ctx.environment) ? "good" : "warn"),
        text: "环境 " + String(ctx.environment || "stable"),
      }));
      if (ctx.profile) {
        const profileChipMeta = projectConfigProfileMeta(ctx.profile);
        chips.appendChild(el("span", {
          class: "project-config-chip " + String(profileChipMeta.tone || "good"),
          text: "执行模式 " + String(ctx.profile),
        }));
      }
      if (ctx.server_port) {
        chips.appendChild(el("span", {
          class: "project-config-chip info",
          text: "端口 " + String(ctx.server_port),
        }));
      }
      if (payload && payload.config_path) {
        chips.appendChild(el("span", {
          class: "project-config-chip muted",
          text: "配置已接入",
          title: String(payload.config_path),
        }));
      }
      section.appendChild(chips);

      section.appendChild(el("div", {
        class: "project-config-message " + String(profileMeta.tone || "info"),
        text: "当前执行模式：" + String(profileMeta.value) + "。"
          + String(profileMeta.summary || "")
          + String(profileMeta.effect ? " " + profileMeta.effect : ""),
      }));

      const meta = el("div", { class: "project-config-meta-grid" });
      const addMeta = (k, v) => {
        meta.appendChild(el("div", { class: "k", text: k }));
        const val = el("div", { class: "v" });
        val.textContent = String(v || "-");
        meta.appendChild(val);
      };
      addMeta("项目", firstNonEmptyText([project && project.name, project && project.id]) || payload.project_id || "-");
      addMeta("项目ID", payload.project_id || "-");
      addMeta("执行模式", ctx.profile || "-");
      addMeta("配置文件", payload.config_path || "-");
      addMeta("工作树", ctx.worktree_root || "-");
      addMeta("运行目录", ctx.runtime_root || "-");
      addMeta("Sessions", ctx.sessions_root || "-");
      addMeta("Runs", ctx.runs_root || "-");
      addMeta("健康探活", ctx.health_source || "-");
      if (health && typeof health === "object") {
        addMeta("当前服务", [
          "environment=" + String(firstNonEmptyText([health.environment]) || "-"),
          "port=" + String(firstNonEmptyText([health.port]) || "-"),
          "worktree=" + String(firstNonEmptyText([health.worktreeRoot, health.worktree_root]) || "-"),
        ].join(" · "));
      }
      section.appendChild(meta);

      if (stats) {
        const statGrid = el("div", { class: "project-config-stat-grid" });
        [
          ["已绑定", stats.bound, "已继承项目默认上下文"],
          ["特例覆盖", stats.override, "存在少量显式例外"],
          ["上下文漂移", stats.drift, "需要后续治理清理"],
          ["未完全绑定", stats.unbound, "仍缺少必要绑定字段"],
        ].forEach(([label, value, hint]) => {
          const card = el("div", { class: "project-config-stat-card" });
          card.appendChild(el("div", { class: "value", text: String(value) }));
          card.appendChild(el("div", { class: "label", text: String(label) }));
          card.title = String(hint);
          statGrid.appendChild(card);
        });
        section.appendChild(statGrid);
      }
      return section;
    }

    function buildProjectConfigExecutionSection(payload) {
      const section = el("section", { class: "project-config-section" });
      const head = el("div", { class: "project-config-section-head" });
      const titleWrap = el("div", { class: "project-config-section-titlewrap" });
      titleWrap.appendChild(el("div", { class: "project-config-section-title", text: "执行上下文" }));
      titleWrap.appendChild(el("div", {
        class: "project-config-section-sub",
        text: "第一批直接编辑项目级真源默认上下文；保存后会立即回读配置并做最小 live 校验。",
      }));
      head.appendChild(titleWrap);
      const actionRow = el("div", { class: "project-config-actions-row" });
      const saveBtn = el("button", {
        class: "btn primary",
        type: "button",
        text: PROJECT_CONFIG_UI.saving ? "保存中..." : "保存并校验",
      });
      saveBtn.disabled = !!PROJECT_CONFIG_UI.saving;
      saveBtn.addEventListener("click", () => { void saveProjectConfigDraft(); });
      actionRow.appendChild(saveBtn);
      head.appendChild(actionRow);
      section.appendChild(head);

      const grid = el("div", { class: "project-config-grid" });
      const addField = (label, key, options = {}) => {
        const field = el("div", { class: "project-config-field" + (options.full ? " full" : "") });
        field.appendChild(el("label", { text: label }));
        let input = null;
        if (options.type === "select") {
          input = el("select", { name: key });
          const selectValues = Array.isArray(options.values) && options.values.length
            ? options.values
            : [["stable", "stable"], ["refactor", "refactor"], ["dev", "dev"], ["prod_mirror", "prod_mirror"]];
          selectValues.forEach(([value, text]) => {
            const opt = el("option", { value, text });
            if (String(projectConfigFieldValue(key) || "") === value) opt.selected = true;
            input.appendChild(opt);
          });
        } else {
          input = el("input", {
            type: options.type || "text",
            name: key,
            value: projectConfigFieldValue(key),
            placeholder: options.placeholder || "",
          });
        }
        input.addEventListener("input", (event) => {
          setProjectConfigDraftField(key, event && event.target ? event.target.value : "");
          if (selectionNote && typeof syncSelectionNote === "function") {
            syncSelectionNote(event && event.target ? event.target.value : "");
          }
        });
        field.appendChild(input);
        if (options.help) field.appendChild(el("small", { text: options.help }));
        let selectionNote = null;
        let syncSelectionNote = null;
        if (typeof options.describeSelection === "function") {
          selectionNote = el("div", { class: "project-config-message info" });
          syncSelectionNote = (value) => {
            const meta = options.describeSelection(value) || {};
            selectionNote.className = "project-config-message " + String(meta.tone || "info");
            selectionNote.textContent = String(meta.text || "");
          };
          syncSelectionNote(projectConfigFieldValue(key) || "");
          field.appendChild(selectionNote);
        }
        grid.appendChild(field);
      };
      addField("profile", "profile", {
        type: "select",
        values: [
          ["sandboxed", projectConfigProfileMeta("sandboxed").optionLabel],
          ["privileged", projectConfigProfileMeta("privileged").optionLabel],
          ["project_privileged_full", projectConfigProfileMeta("project_privileged_full").optionLabel],
        ],
        help: "控制当前项目的执行模式；切换后影响保存后的新 run，不会回头改变已在运行的会话。",
        describeSelection: (value) => {
          const meta = projectConfigProfileMeta(value);
          return {
            tone: meta.tone,
            text: "选择效果：" + String(meta.summary || "")
              + String(meta.effect ? " " + meta.effect : ""),
          };
        },
      });
      addField("环境", "environment", { type: "select", help: "当前项目默认执行环境，后续由项目真源统一派生给 Session。" });
      addField("分支", "branch", { help: "默认执行分支；仅特殊 Session 才允许例外覆盖。" });
      addField("工作树", "worktree_root", { full: true, help: "项目默认 worktree_root，建议指向项目根目录。" });
      addField("工作目录", "workdir", { full: true, help: "默认执行 cwd；常态建议与 worktree_root 一致。" });
      addField("运行目录", "runtime_root", { full: true, help: "用于 health / sessions / runs 的运行时根目录。" });
      addField("sessions 目录", "sessions_root", { full: true, help: "项目级 Session 真源目录。" });
      addField("runs 目录", "runs_root", { full: true, help: "项目级 Run 真源目录。" });
      addField("服务端口", "server_port", { help: "当前项目绑定服务端口，如 18765。" });
      addField("探活路径", "health_source", { help: "最小 live 校验时使用的 health 路径。" });
      section.appendChild(grid);
      return section;
    }

    function copyProjectShareText(text) {
      const value = String(text || "");
      if (!value) return;
      if (typeof copyText === "function") {
        copyText(value);
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).catch(() => {});
      }
    }

    function projectShareAgentCandidates(projectId) {
      const pid = String(projectId || "").trim();
      const rows = [];
      const seen = new Set();
      const append = (raw) => {
        if (!raw || typeof raw !== "object") return;
        const rawProjectId = String(firstNonEmptyText([raw.project_id, raw.projectId]) || "").trim();
        if (rawProjectId && pid && rawProjectId !== pid) return;
        const sessionId = String(firstNonEmptyText([raw.id, raw.session_id, raw.sessionId]) || "").trim();
        if (!sessionId || seen.has(sessionId)) return;
        seen.add(sessionId);
        rows.push({
          session_id: sessionId,
          label: String(firstNonEmptyText([
            raw.agent_display_name,
            raw.display_name,
            raw.alias,
            raw.name,
            raw.channel_name,
            sessionId,
          ]) || sessionId).trim(),
          channel_name: String(firstNonEmptyText([raw.channel_name, raw.name]) || "").trim(),
          role: String(firstNonEmptyText([raw.session_role, raw.role]) || "").trim(),
          cli_type: String(firstNonEmptyText([raw.cli_type, raw.cliType, "codex"]) || "codex").trim(),
        });
      };
      const project = projectById(pid) || {};
      (Array.isArray(project.channel_sessions) ? project.channel_sessions : []).forEach(append);
      if (typeof PCONV !== "undefined" && PCONV && Array.isArray(PCONV.sessions)) {
        PCONV.sessions.forEach(append);
      }
      return rows.sort((a, b) => {
        const channelCmp = String(a.channel_name || "").localeCompare(String(b.channel_name || ""), "zh-CN");
        if (channelCmp) return channelCmp;
        return String(a.label || "").localeCompare(String(b.label || ""), "zh-CN");
      });
    }

    function projectShareSelectedSessionSet(draft) {
      const src = (draft && typeof draft === "object") ? draft : {};
      return new Set((Array.isArray(src.allowed_session_ids) ? src.allowed_session_ids : [])
        .map((it) => String(it || "").trim())
        .filter(Boolean));
    }

    function projectShareAgentGroups(projectId, draft) {
      const groups = new Map();
      const knownSessionIds = new Set();
      projectShareAgentCandidates(projectId).forEach((item) => {
        const sessionId = String(item.session_id || "").trim();
        if (sessionId) knownSessionIds.add(sessionId);
        const channelName = String(item.channel_name || "未分组通道").trim() || "未分组通道";
        if (!groups.has(channelName)) groups.set(channelName, { channel_name: channelName, items: [] });
        groups.get(channelName).items.push(item);
      });
      const manualSessionIds = Array.from(projectShareSelectedSessionSet(draft || {}))
        .filter((sessionId) => sessionId && !knownSessionIds.has(sessionId));
      if (manualSessionIds.length) {
        groups.set("历史授权 / 手动 session_id", {
          channel_name: "历史授权 / 手动 session_id",
          items: manualSessionIds.map((sessionId) => ({
            session_id: sessionId,
            label: sessionId,
            channel_name: "历史授权 / 手动 session_id",
            role: "manual",
            cli_type: "session_id",
          })),
        });
      }
      return Array.from(groups.values())
        .map((group) => ({
          ...group,
          items: group.items.sort((a, b) => String(a.label || "").localeCompare(String(b.label || ""), "zh-CN")),
        }))
        .sort((a, b) => String(a.channel_name || "").localeCompare(String(b.channel_name || ""), "zh-CN"));
    }

    function projectShareStatusMeta(space) {
      const item = (space && typeof space === "object") ? space : {};
      let status = String(item.status || "").trim().toLowerCase();
      if (!status) {
        if (item.deleted_at) status = "deleted";
        else if (item.revoked_at) status = "revoked";
        else if (item.disabled_at || item.enabled === false) status = "disabled";
        else if (item.permission === "read") status = "read_only";
        else status = "active";
      }
      const map = {
        active: { label: "可访问", tone: "good" },
        read_only: { label: "只读", tone: "info" },
        disabled: { label: "已禁用", tone: "warn" },
        revoked: { label: "已撤销", tone: "warn" },
        deleted: { label: "已删除", tone: "muted" },
        expired: { label: "已过期", tone: "warn" },
      };
      return { status, ...(map[status] || { label: status || "未知", tone: "muted" }) };
    }

    function updateProjectShareEditorDraft(patch, opts = {}) {
      const pid = String(PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      const base = PROJECT_CONFIG_UI.shareEditorDraft || buildProjectShareSpaceDraft(pid, PROJECT_CONFIG_UI.cache[pid] || null, null);
      PROJECT_CONFIG_UI.shareEditorDraft = { ...base, ...(patch || {}) };
      if (!(opts && opts.silent)) renderProjectConfigDrawer();
    }

    function setProjectShareEditorGroupSelection(sessionIds, checked) {
      const current = projectShareSelectedSessionSet(PROJECT_CONFIG_UI.shareEditorDraft || {});
      (Array.isArray(sessionIds) ? sessionIds : []).forEach((sessionId) => {
        const sid = String(sessionId || "").trim();
        if (!sid) return;
        if (checked) current.add(sid);
        else current.delete(sid);
      });
      updateProjectShareEditorDraft({ allowed_session_ids: Array.from(current) });
    }

    function toggleProjectShareEditorSession(sessionId, checked) {
      const sid = String(sessionId || "").trim();
      if (!sid) return;
      const current = projectShareSelectedSessionSet(PROJECT_CONFIG_UI.shareEditorDraft || {});
      if (checked) current.add(sid);
      else current.delete(sid);
      updateProjectShareEditorDraft({ allowed_session_ids: Array.from(current) });
    }

    function openProjectShareEditor(space) {
      const pid = String(PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      const payload = PROJECT_CONFIG_UI.cache[pid] || null;
      const isEdit = !!(space && space.share_id);
      PROJECT_CONFIG_UI.shareEditorOpen = true;
      PROJECT_CONFIG_UI.shareEditorMode = isEdit ? "edit" : "create";
      PROJECT_CONFIG_UI.shareEditorOriginalId = isEdit ? String(space.share_id || "") : "";
      PROJECT_CONFIG_UI.shareEditorDraft = buildProjectShareSpaceDraft(pid, payload, isEdit ? space : {
        share_id: uniqueProjectShareId(pid, payload),
        name: "新共享对象",
        title: ((projectById(pid) || {}).name || pid || "项目") + "共享空间",
        allowed_session_ids: [],
        enabled: true,
        permission: "read_send",
      });
      PROJECT_CONFIG_UI.shareEditorAdvancedOpen = false;
      PROJECT_CONFIG_UI.error = "";
      PROJECT_CONFIG_UI.note = "";
      renderProjectConfigDrawer();
      void refreshProjectShareRuntimeHealth();
    }

    function closeProjectShareEditor() {
      PROJECT_CONFIG_UI.shareEditorOpen = false;
      PROJECT_CONFIG_UI.shareEditorOriginalId = "";
      PROJECT_CONFIG_UI.shareEditorDraft = null;
      PROJECT_CONFIG_UI.shareEditorAdvancedOpen = false;
      renderProjectConfigDrawer();
    }

    function buildProjectShareEditorField(key, label, opts = {}) {
      const draft = PROJECT_CONFIG_UI.shareEditorDraft || {};
      const field = el("div", { class: "project-config-field" + (opts.full ? " full" : "") });
      field.appendChild(el("label", { for: "shareEditor_" + key, text: label }));
      let input;
      if (opts.type === "textarea") {
        input = el("textarea", { id: "shareEditor_" + key, rows: String(opts.rows || 3) });
        input.value = Array.isArray(draft[key]) ? draft[key].join("\n") : String(draft[key] || "");
      } else if (opts.type === "select") {
        input = el("select", { id: "shareEditor_" + key });
        (opts.options || []).forEach((item) => input.appendChild(el("option", { value: item.value, text: item.label })));
        input.value = key === "enabled"
          ? (draft.enabled === false ? "0" : "1")
          : String(draft[key] || opts.defaultValue || "");
      } else {
        input = el("input", { id: "shareEditor_" + key, type: opts.type || "text", value: String(draft[key] || "") });
      }
      const readValue = (raw) => {
        if (key === "allowed_session_ids") {
          return String(raw || "").split(/[\n,，]+/).map((it) => it.trim()).filter(Boolean);
        }
        if (key === "enabled") return String(raw) === "1";
        return raw;
      };
      input.addEventListener("input", (event) => {
        const raw = event && event.target ? event.target.value : "";
        updateProjectShareEditorDraft({ [key]: readValue(raw) }, { silent: true });
      });
      input.addEventListener("change", (event) => {
        const raw = event && event.target ? event.target.value : "";
        updateProjectShareEditorDraft({ [key]: readValue(raw) });
      });
      field.appendChild(input);
      if (opts.help) field.appendChild(el("small", { text: opts.help }));
      return field;
    }

    function buildProjectShareAgentPicker(projectId, draft) {
      const selected = projectShareSelectedSessionSet(draft);
      const groups = projectShareAgentGroups(projectId, draft);
      const picker = el("div", { class: "project-share-agent-picker" });
      if (!groups.length) {
        picker.appendChild(el("div", {
          class: "project-config-message warn",
          text: "当前静态数据没有可快选的 Agent；可在高级设置里手动填写 session_id。",
        }));
        return picker;
      }
      groups.forEach((group) => {
        const groupSessionIds = group.items.map((item) => item.session_id).filter(Boolean);
        const selectedInGroup = groupSessionIds.filter((sessionId) => selected.has(sessionId)).length;
        const allSelected = groupSessionIds.length > 0 && selectedInGroup === groupSessionIds.length;
        const groupCard = el("div", { class: "project-share-agent-group" });
        const groupHead = el("div", { class: "project-share-agent-group-head" });
        const groupTitle = el("div", { class: "project-share-group-title" });
        groupTitle.appendChild(el("span", { text: group.channel_name }));
        groupTitle.appendChild(el("span", { class: "project-share-count", text: "已选 " + selectedInGroup + "/" + groupSessionIds.length }));
        groupHead.appendChild(groupTitle);
        const groupBtn = el("button", { class: "btn project-share-group-toggle", type: "button", text: allSelected ? "取消本通道" : "全选本通道" });
        groupBtn.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          setProjectShareEditorGroupSelection(groupSessionIds, !allSelected);
        });
        groupHead.appendChild(groupBtn);
        groupCard.appendChild(groupHead);

        const list = el("div", { class: "project-share-agent-list" });
        group.items.forEach((item) => {
          const checked = selected.has(item.session_id);
          const row = el("label", { class: "project-share-agent-row" + (checked ? " selected" : "") });
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.checked = checked;
          checkbox.addEventListener("change", () => toggleProjectShareEditorSession(item.session_id, checkbox.checked));
          row.appendChild(checkbox);
          const body = el("span", { class: "project-share-agent-body" });
          body.appendChild(el("span", { class: "project-share-agent-title", text: item.label || item.session_id }));
          body.appendChild(el("span", {
            class: "project-share-agent-meta",
            text: [item.role || "agent", item.cli_type || "codex", shortId(item.session_id)].filter(Boolean).join(" · "),
          }));
          row.appendChild(body);
          list.appendChild(row);
        });
        groupCard.appendChild(list);
        picker.appendChild(groupCard);
      });
      return picker;
    }

    function buildProjectShareEditorDialog(projectId) {
      if (!PROJECT_CONFIG_UI.shareEditorOpen) return null;
      const draft = PROJECT_CONFIG_UI.shareEditorDraft || buildProjectShareSpaceDraft(projectId, PROJECT_CONFIG_UI.cache[projectId] || null, null);
      const selectedCount = projectShareSelectedSessionSet(draft).size;
      const overlay = el("div", { class: "project-share-editor-overlay" });
      const dialog = el("div", { class: "project-share-editor", role: "dialog", "aria-modal": "true" });
      const head = el("div", { class: "project-share-editor-head" });
      const titleWrap = el("div");
      titleWrap.appendChild(el("div", {
        class: "project-share-editor-kicker",
        text: PROJECT_CONFIG_UI.shareEditorMode === "edit" ? "编辑分享对象" : "新增分享对象",
      }));
      titleWrap.appendChild(el("h3", { text: draft.name || "共享对象" }));
      head.appendChild(titleWrap);
      const closeBtn = el("button", { class: "btn", type: "button", text: "关闭" });
      closeBtn.addEventListener("click", closeProjectShareEditor);
      head.appendChild(closeBtn);
      dialog.appendChild(head);

      const form = el("div", { class: "project-share-editor-body" });
      const nameGrid = el("div", { class: "project-config-grid" });
      nameGrid.appendChild(buildProjectShareEditorField("name", "分享名称", {
        help: "列表中优先展示的对象名称，例如“业务方A”。",
      }));
      form.appendChild(nameGrid);
      form.appendChild(el("div", {
        class: "project-share-editor-section-title",
        text: "授权 Agent",
      }));
      if (!selectedCount) {
        form.appendChild(el("div", {
          class: "project-config-message warn",
          text: "请至少选择 1 个 Agent；未授权对象无法访问聊天。",
        }));
      }
      form.appendChild(buildProjectShareAgentPicker(projectId, draft));

      const advanced = el("details", { class: "project-share-advanced project-share-editor-advanced" });
      if (PROJECT_CONFIG_UI.shareEditorAdvancedOpen) advanced.setAttribute("open", "open");
      advanced.addEventListener("toggle", () => {
        const nextOpen = !!advanced.open;
        if (PROJECT_CONFIG_UI.shareEditorAdvancedOpen === nextOpen) return;
        PROJECT_CONFIG_UI.shareEditorAdvancedOpen = nextOpen;
        renderProjectConfigDrawer();
      });
      const summary = el("summary", { text: "高级设置" });
      summary.appendChild(el("span", { class: "project-share-advanced-hint", text: "share_id / Token / 口令 / 有效期 / 权限 / 手动 session_id" }));
      advanced.appendChild(summary);
      if (PROJECT_CONFIG_UI.shareEditorAdvancedOpen) {
        const grid = el("div", { class: "project-config-grid project-share-advanced-grid" });
        grid.appendChild(buildProjectShareEditorField("share_id", "分享ID", { help: "URL 路径标识。编辑已有对象时不建议修改；需要新链接请新建对象。" }));
        grid.appendChild(buildProjectShareEditorField("title", "分享标题", { help: "share-mode 主聊天页主标题。" }));
        grid.appendChild(buildProjectShareEditorField("enabled", "启用状态", {
          type: "select",
          defaultValue: "1",
          options: [
            { value: "1", label: "启用共享空间" },
            { value: "0", label: "暂不启用" },
          ],
          help: "停用后 bootstrap 网关会拒绝访问。",
        }));
        grid.appendChild(buildProjectShareEditorField("permission", "权限", {
          type: "select",
          defaultValue: "read_send",
          options: [
            { value: "read_send", label: "read_send · 查看并发送" },
            { value: "read", label: "read · 仅查看" },
          ],
          help: "只读链接会隐藏发送能力。",
        }));
        grid.appendChild(buildProjectShareEditorField("access_token", "访问 Token", { help: "保存后作为 share-scoped 凭据，不使用项目全局 Token。" }));
        grid.appendChild(buildProjectShareEditorField("passcode", "访问口令", { help: "可选；不写则只校验 Token。" }));
        grid.appendChild(buildProjectShareEditorField("expires_at", "有效期", { help: "可选 ISO 时间，例如 2026-04-30T23:59:59Z。" }));
        grid.appendChild(buildProjectShareEditorField("allowed_session_ids", "授权 session_id", {
          type: "textarea",
          full: true,
          rows: 4,
          help: "每行一个 session_id；默认建议直接用上方通道/Agent 分组选择。",
        }));
        advanced.appendChild(grid);
      }
      form.appendChild(advanced);
      dialog.appendChild(form);

      const footer = el("div", { class: "project-share-editor-footer" });
      footer.appendChild(el("span", { text: selectedCount ? ("已选择 " + selectedCount + " 个 Agent") : "未选择 Agent" }));
      const saveBtn = el("button", { class: "btn primary", type: "button", text: PROJECT_CONFIG_UI.saving ? "保存中..." : "保存分享对象" });
      saveBtn.disabled = PROJECT_CONFIG_UI.saving || !selectedCount || !String(draft.name || draft.title || "").trim();
      saveBtn.addEventListener("click", () => { void saveProjectShareSpaceDraft(); });
      footer.appendChild(saveBtn);
      dialog.appendChild(footer);
      overlay.appendChild(dialog);
      return overlay;
    }

    function buildProjectShareSpaceSection(project, payload) {
      const pid = String((payload && payload.project_id) || PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      const shareSpace = normalizeProjectShareSpace(payload && payload.share_space, pid);
      const spaces = projectShareSpacesFromPayload(pid, payload);
      const activeCount = Number(shareSpace.active_count || spaces.filter((item) => projectShareStatusMeta(item).status === "active" || projectShareStatusMeta(item).status === "read_only").length || 0) || 0;
      const section = el("section", { class: "project-config-section project-share-section", id: "projectShareSection" });
      const head = el("div", { class: "project-config-section-head" });
      const titleWrap = el("div", { class: "project-config-section-titlewrap" });
      titleWrap.appendChild(el("div", { class: "project-config-section-title", text: "分享项目" }));
      titleWrap.appendChild(el("div", {
        class: "project-config-section-sub",
        text: "V3 支持多个分享对象：每个对象拥有独立链接、Token、授权 Agent 和受限主聊天壳入口。",
      }));
      head.appendChild(titleWrap);
      const chips = el("div", { class: "project-config-chip-row" });
      chips.appendChild(el("span", { class: "project-config-chip good", text: "对象 " + spaces.length }));
      chips.appendChild(el("span", { class: "project-config-chip info", text: "可访问 " + activeCount }));
      chips.appendChild(el("span", { class: "project-config-chip info", text: "lan_only" }));
      head.appendChild(chips);
      section.appendChild(head);

      const toolbar = el("div", { class: "project-share-list-toolbar" });
      toolbar.appendChild(el("div", {
        class: "project-share-quick-sub",
        text: "先管理分享对象；新增/编辑时再选择 Agent。Token、口令、有效期等仍默认折叠。",
      }));
      const newBtn = el("button", { class: "btn primary", type: "button", text: "新增分享对象" });
      newBtn.addEventListener("click", () => openProjectShareEditor(null));
      toolbar.appendChild(newBtn);
      section.appendChild(toolbar);

      const list = el("div", { class: "project-share-object-list" });
      if (!spaces.length) {
        const empty = el("div", { class: "project-share-empty" });
        empty.appendChild(el("strong", { text: "还没有分享对象" }));
        empty.appendChild(el("span", { text: "新增一个对象后，会生成独立链接并只开放所选 Agent。" }));
        const emptyBtn = el("button", { class: "btn primary", type: "button", text: "新增分享对象" });
        emptyBtn.addEventListener("click", () => openProjectShareEditor(null));
        empty.appendChild(emptyBtn);
        list.appendChild(empty);
      } else {
        spaces.forEach((space) => {
          const statusMeta = projectShareStatusMeta(space);
          const isDeleted = statusMeta.status === "deleted";
          const isDisabled = statusMeta.status === "disabled";
          const isUnavailable = isDeleted || statusMeta.status === "revoked" || statusMeta.status === "expired";
          const card = el("article", { class: "project-share-object-card" + (isUnavailable ? " unavailable" : "") });
          const cardHead = el("div", { class: "project-share-object-head" });
          const nameWrap = el("div", { class: "project-share-object-titlewrap" });
          nameWrap.appendChild(el("h3", { text: space.name || space.title || space.share_id || "未命名分享对象" }));
          nameWrap.appendChild(el("div", {
            class: "project-share-object-sub",
            text: [space.title, space.share_id].filter(Boolean).join(" · "),
          }));
          cardHead.appendChild(nameWrap);
          cardHead.appendChild(el("span", { class: "project-config-chip " + statusMeta.tone, text: statusMeta.label }));
          card.appendChild(cardHead);

          const meta = el("div", { class: "project-share-object-meta" });
          meta.appendChild(el("span", { text: "Agent " + (space.allowed_session_count || (space.allowed_session_ids || []).length || 0) }));
          meta.appendChild(el("span", { text: space.permission === "read" ? "只读" : "可发送" }));
          meta.appendChild(el("span", { text: space.updated_at ? ("更新 " + space.updated_at) : "share-scoped" }));
          card.appendChild(meta);

          const actions = el("div", { class: "project-share-object-actions" });
          const copyBtn = el("button", { class: "btn", type: "button", text: "复制 V3 链接" });
          copyBtn.disabled = isUnavailable || !space.access_token;
          copyBtn.addEventListener("click", () => copyProjectShareText(projectShareSpacePageHref(pid, space)));
          actions.appendChild(copyBtn);
          const openBtn = el("button", { class: "btn", type: "button", text: "打开主聊天壳" });
          openBtn.disabled = isUnavailable || !space.access_token;
          openBtn.addEventListener("click", () => window.open(projectShareSpacePageHref(pid, space), "_blank", "noopener,noreferrer"));
          actions.appendChild(openBtn);
          const editBtn = el("button", { class: "btn", type: "button", text: "编辑" });
          editBtn.disabled = isDeleted;
          editBtn.addEventListener("click", () => openProjectShareEditor(space));
          actions.appendChild(editBtn);
          const toggleBtn = el("button", { class: "btn", type: "button", text: isDisabled ? "启用" : "禁用" });
          toggleBtn.disabled = isDeleted;
          toggleBtn.addEventListener("click", () => { void runProjectShareSpaceAction(isDisabled ? "enable" : "disable", space); });
          actions.appendChild(toggleBtn);
          const deleteBtn = el("button", { class: "btn danger", type: "button", text: "删除" });
          deleteBtn.disabled = isDeleted;
          deleteBtn.addEventListener("click", () => {
            if (window.confirm && !window.confirm("确认删除分享对象“" + (space.name || space.share_id) + "”？删除后该链接不可访问。")) return;
            void runProjectShareSpaceAction("delete", space);
          });
          actions.appendChild(deleteBtn);
          card.appendChild(actions);
          list.appendChild(card);
        });
      }
      section.appendChild(list);
      section.appendChild(el("div", {
        class: "project-config-message info",
        text: "安全边界保持不变：分享页只接 /api/share-spaces/* 网关；禁止直连 /api/sessions、/api/channel-sessions、/api/agent-candidates、/api/fs/reveal、/api/codex/announce。",
      }));
      const dialog = buildProjectShareEditorDialog(pid);
      if (dialog) section.appendChild(dialog);
      return section;
    }

    function buildProjectConfigInheritanceSection(payload, stats) {
      const section = el("section", { class: "project-config-section" });
      const head = el("div", { class: "project-config-section-head" });
      const titleWrap = el("div", { class: "project-config-section-titlewrap" });
      titleWrap.appendChild(el("div", { class: "project-config-section-title", text: "继承与异常" }));
      titleWrap.appendChild(el("div", {
        class: "project-config-section-sub",
        text: "统一口径为：项目配置是真源默认上下文，Session 只显示继承结果与少量显式例外。",
      }));
      head.appendChild(titleWrap);
      section.appendChild(head);

      const chips = el("div", { class: "project-config-chip-row" });
      if (stats) {
        chips.appendChild(el("span", { class: "project-config-chip good", text: "已绑定 " + stats.bound }));
        chips.appendChild(el("span", { class: "project-config-chip info", text: "特例覆盖 " + stats.override }));
        chips.appendChild(el("span", { class: "project-config-chip warn", text: "上下文漂移 " + stats.drift }));
        chips.appendChild(el("span", { class: "project-config-chip muted", text: "未完全绑定 " + stats.unbound }));
      } else {
        chips.appendChild(el("span", { class: "project-config-chip muted", text: "会话统计待返回" }));
      }
      section.appendChild(chips);

      const message = el("div", {
        class: "project-config-message info",
        text: "当前主线先保证“项目配置回答项目应该跑在哪里”；历史 override / 漂移清理作为第二批治理，不阻塞入口上线。",
      });
      section.appendChild(message);

      const actions = el("div", { class: "project-config-actions-row" });
      const directoryBtn = el("button", { class: "btn project-config-link-btn", type: "button", text: "打开通讯录" });
      directoryBtn.addEventListener("click", () => {
        if (typeof openProjectAgentDirectory === "function") openProjectAgentDirectory();
      });
      actions.appendChild(directoryBtn);
      const healthBtn = el("button", { class: "btn project-config-link-btn", type: "button", text: "打开会话健康" });
      healthBtn.addEventListener("click", () => {
        if (typeof openSessionHealthPage === "function") openSessionHealthPage();
      });
      actions.appendChild(healthBtn);
      section.appendChild(actions);
      return section;
    }

    function buildProjectConfigCompatibilitySection(project, payload) {
      const section = el("section", { class: "project-config-section" });
      const head = el("div", { class: "project-config-section-head" });
      const titleWrap = el("div", { class: "project-config-section-titlewrap" });
      titleWrap.appendChild(el("div", { class: "project-config-section-title", text: "兼容字段" }));
      titleWrap.appendChild(el("div", {
        class: "project-config-section-sub",
        text: "旧环境标签与会话级环境编辑已降级；这里只保留兼容观察，不再作为项目主真源。",
      }));
      head.appendChild(titleWrap);
      section.appendChild(head);

      const legacy = {
        environment: firstNonEmptyText([project && project.environment]),
        worktree_root: firstNonEmptyText([project && project.worktree_root]),
        workdir: firstNonEmptyText([project && project.workdir]),
        branch: firstNonEmptyText([project && project.branch]),
      };
      const ctx = normalizeProjectConfigExecutionContext(payload && payload.execution_context);
      const changed = [];
      [["环境", legacy.environment, ctx.environment], ["worktree", legacy.worktree_root, ctx.worktree_root], ["workdir", legacy.workdir, ctx.workdir], ["branch", legacy.branch, ctx.branch]].forEach(([label, fromValue, toValue]) => {
        if (fromValue && toValue && String(fromValue) !== String(toValue)) changed.push(String(label));
      });
      const message = el("div", {
        class: "project-config-message",
        text: changed.length
          ? ("兼容字段仍保留用于旧链路和排查历史漂移，不再作为主展示真源。当前观察到差异字段: " + changed.join(" / "))
          : "当前未检测到额外的项目级兼容差异；旧标签仍只保留在 tooltip、详情与审计链路中。",
      });
      section.appendChild(message);
      const code = el("code", { class: "project-config-code" });
      code.textContent = JSON.stringify({
        compatibility_view: legacy,
        effective_execution_context: ctx,
      }, null, 2);
      section.appendChild(code);
      return section;
    }

    function renderProjectConfigDrawer() {
      ensureProjectConfigDrawerNodes();
      updateProjectConfigButtonState();
      const mask = projectConfigMaskNode();
      const body = projectConfigBodyNode();
      const title = document.getElementById("projectConfigTitle");
      const sub = document.getElementById("projectConfigSub");
      const reloadBtn = document.getElementById("projectConfigReloadBtn");
      const saveBtn = document.getElementById("projectConfigSaveBtn");
      if (!mask || !body || !title || !sub || !reloadBtn || !saveBtn) return;
      mask.classList.toggle("show", !!PROJECT_CONFIG_UI.open);
      saveBtn.disabled = !!PROJECT_CONFIG_UI.loading || !!PROJECT_CONFIG_UI.saving;
      saveBtn.textContent = PROJECT_CONFIG_UI.saving ? "保存中..." : "保存并校验";
      reloadBtn.disabled = !!PROJECT_CONFIG_UI.loading || !!PROJECT_CONFIG_UI.saving;
      if (!PROJECT_CONFIG_UI.open) return;

      const pid = String(PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      const project = projectById(pid);
      const shareMode = PROJECT_CONFIG_UI.activeSection === "share";
      body.classList.toggle("share-mode", shareMode);
      saveBtn.textContent = PROJECT_CONFIG_UI.saving
        ? "保存中..."
        : (shareMode ? (PROJECT_CONFIG_UI.shareEditorOpen ? "保存分享对象" : "新增分享对象") : "保存并校验");
      title.textContent = (shareMode ? "分享项目" : "项目配置") + (project && project.name ? " · " + String(project.name) : "");
      sub.textContent = pid
        ? (shareMode
          ? ("管理多个受控外放视窗；每个链接只授权 Agent 聊天与发送能力。当前项目: " + pid)
          : ("项目级 execution_context 真源编辑；Session 只保留身份与有效上下文只读展示。当前项目: " + pid))
        : "当前未选中具体项目。";
      body.innerHTML = "";

      if (PROJECT_CONFIG_UI.loading) {
        body.appendChild(el("div", { class: "project-config-message info", text: "正在读取项目配置..." }));
        return;
      }
      if (PROJECT_CONFIG_UI.error) {
        body.appendChild(el("div", { class: "project-config-message error", text: PROJECT_CONFIG_UI.error }));
      } else if (PROJECT_CONFIG_UI.note) {
        body.appendChild(el("div", { class: "project-config-message success", text: PROJECT_CONFIG_UI.note }));
      }

      const payload = PROJECT_CONFIG_UI.cache[pid] || null;
      if (!payload) {
        body.appendChild(el("div", { class: "project-config-message", text: "当前尚未读取到项目配置。" }));
        return;
      }
      if (shareMode) {
        saveBtn.disabled = !!PROJECT_CONFIG_UI.loading || !!PROJECT_CONFIG_UI.saving;
        body.appendChild(buildProjectShareSpaceSection(project, payload));
        return;
      }

      const stats = PROJECT_CONFIG_UI.sessionStats[pid] || null;
      const health = PROJECT_CONFIG_UI.liveHealth;
      body.appendChild(buildProjectConfigOverviewSection(project, payload, stats, health));
      body.appendChild(buildProjectConfigExecutionSection(payload));
      body.appendChild(buildProjectConfigInheritanceSection(payload, stats));
      body.appendChild(buildProjectConfigCompatibilitySection(project, payload));
    }

    async function saveProjectConfigDraft() {
      const pid = String(PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      if (!pid || PROJECT_CONFIG_UI.saving) return;
      const draft = (PROJECT_CONFIG_UI.draft && typeof PROJECT_CONFIG_UI.draft === "object") ? PROJECT_CONFIG_UI.draft : {};
      const payload = {
        execution_context: {
          profile: normalizeProjectConfigProfile(draft.profile, "sandboxed") || null,
          environment: normalizeEnvironmentName(draft.environment || "stable"),
          worktree_root: String(draft.worktree_root || "").trim() || null,
          workdir: String(draft.workdir || "").trim() || null,
          branch: String(draft.branch || "").trim() || null,
          runtime_root: String(draft.runtime_root || "").trim() || null,
          sessions_root: String(draft.sessions_root || "").trim() || null,
          runs_root: String(draft.runs_root || "").trim() || null,
          server_port: String(draft.server_port || "").trim() || null,
          health_source: String(draft.health_source || "").trim() || null,
        },
      };
      PROJECT_CONFIG_UI.saving = true;
      PROJECT_CONFIG_UI.error = "";
      PROJECT_CONFIG_UI.note = "";
      renderProjectConfigDrawer();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/config", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          if (resp.status === 404) {
            throw new Error("现网服务尚未加载项目配置写接口；请先完成 stable 进程切服后再保存。");
          }
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const body = await resp.json().catch(() => ({}));
        const normalized = normalizeProjectConfigPayload(pid, body);
        PROJECT_CONFIG_UI.cache[pid] = normalized;
        PROJECT_CONFIG_UI.draft = { ...normalized.execution_context };
        PROJECT_CONFIG_UI.shareDraft = buildProjectShareSpaceDraft(pid, normalized);
        syncProjectConfigToLocal(pid, normalized);
        await Promise.allSettled([
          fetchProjectContextStats(pid, true),
          fetchProjectConfigHealth(true),
        ]);
        if (typeof rebuildDashboardAfterStatusChange === "function") rebuildDashboardAfterStatusChange();
        PROJECT_CONFIG_UI.note = "项目配置已保存并完成最小 live 校验；静态看板会在后台重建后同步新展示。";
        if (typeof render === "function") render();
      } catch (error) {
        PROJECT_CONFIG_UI.error = "保存项目配置失败：" + String((error && error.message) || error || "未知错误");
      } finally {
        PROJECT_CONFIG_UI.saving = false;
        renderProjectConfigDrawer();
      }
    }

    async function commitProjectShareSpaceChange(pid, sharePayload, successNote) {
      PROJECT_CONFIG_UI.saving = true;
      PROJECT_CONFIG_UI.error = "";
      PROJECT_CONFIG_UI.note = "";
      renderProjectConfigDrawer();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/config", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ share_space: sharePayload }),
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const body = await resp.json().catch(() => ({}));
        const normalized = normalizeProjectConfigPayload(pid, body);
        PROJECT_CONFIG_UI.cache[pid] = normalized;
        PROJECT_CONFIG_UI.draft = { ...normalized.execution_context };
        PROJECT_CONFIG_UI.shareDraft = buildProjectShareSpaceDraft(pid, normalized);
        syncProjectConfigToLocal(pid, normalized);
        PROJECT_CONFIG_UI.note = successNote || "分享项目配置已更新。";
        if (typeof render === "function") render();
        return true;
      } catch (error) {
        PROJECT_CONFIG_UI.error = "保存分享项目失败：" + String((error && error.message) || error || "未知错误");
        return false;
      } finally {
        PROJECT_CONFIG_UI.saving = false;
        renderProjectConfigDrawer();
      }
    }

    async function runProjectShareSpaceAction(action, space) {
      const pid = String(PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      if (!pid || PROJECT_CONFIG_UI.saving) return false;
      const shareId = String(space && space.share_id || "").trim();
      if (!shareId) return false;
      const labels = {
        enable: "分享对象已启用。",
        disable: "分享对象已禁用，主聊天壳访问会被拒绝。",
        delete: "分享对象已删除，该链接不可访问。",
      };
      return commitProjectShareSpaceChange(pid, {
        action,
        share_id: shareId,
      }, labels[action] || "分享对象状态已更新。");
    }

    async function saveProjectShareEditorDraft() {
      const pid = String(PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      if (!pid || PROJECT_CONFIG_UI.saving) return false;
      const draft = PROJECT_CONFIG_UI.shareEditorDraft || buildProjectShareSpaceDraft(pid, PROJECT_CONFIG_UI.cache[pid] || null, null);
      if (!String(draft.name || draft.title || "").trim()) {
        PROJECT_CONFIG_UI.error = "请填写分享名称。";
        PROJECT_CONFIG_UI.note = "";
        renderProjectConfigDrawer();
        return false;
      }
      if (projectShareSelectedSessionSet(draft).size === 0) {
        PROJECT_CONFIG_UI.error = "请至少选择 1 个 Agent 后再保存分享对象。";
        PROJECT_CONFIG_UI.note = "";
        renderProjectConfigDrawer();
        return false;
      }
      const ok = await commitProjectShareSpaceChange(pid, {
        action: "upsert",
        space: projectShareSpacePayload(pid, draft),
      }, "分享对象已保存；可复制独立链接或打开主聊天壳。");
      if (ok) {
        PROJECT_CONFIG_UI.shareEditorOpen = false;
        PROJECT_CONFIG_UI.shareEditorOriginalId = "";
        PROJECT_CONFIG_UI.shareEditorDraft = null;
        PROJECT_CONFIG_UI.shareEditorAdvancedOpen = false;
        renderProjectConfigDrawer();
      }
      return ok;
    }

    async function saveProjectShareSpaceDraft() {
      const pid = String(PROJECT_CONFIG_UI.projectId || currentProjectConfigProjectId() || "").trim();
      if (!pid || PROJECT_CONFIG_UI.saving) return;
      if (!PROJECT_CONFIG_UI.shareEditorOpen) {
        openProjectShareEditor(null);
        return;
      }
      await saveProjectShareEditorDraft();
    }

    function openProjectConfigDrawer(opts = {}) {
      const pid = currentProjectConfigProjectId();
      if (!pid) return;
      PROJECT_CONFIG_UI.open = true;
      PROJECT_CONFIG_UI.activeSection = String((opts && opts.section) || "config").trim() || "config";
      PROJECT_CONFIG_UI.projectId = pid;
      renderProjectConfigDrawer();
      void loadProjectConfigData(pid, {
        force: PROJECT_CONFIG_UI.activeSection === "share",
        preserveMessage: true,
      });
    }

    function openShareProjectDrawer() {
      openProjectConfigDrawer({ section: "share" });
    }

    function closeProjectConfigDrawer() {
      PROJECT_CONFIG_UI.open = false;
      renderProjectConfigDrawer();
    }

    function initProjectConfigUI() {
      ensureProjectConfigDrawerNodes();
      const btn = projectConfigBtnNode();
      if (btn) {
        btn.addEventListener("click", openProjectConfigDrawer);
      }
      const shareBtn = shareProjectBtnNode();
      if (shareBtn) {
        shareBtn.addEventListener("click", openShareProjectDrawer);
      }
      hookProjectConfigIntoRender();
      updateProjectConfigButtonState();
    }

    window.addEventListener("load", initProjectConfigUI);
