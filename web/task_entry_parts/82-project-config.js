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
      renderHooked: false,
    };

    function projectConfigBtnNode() {
      return document.getElementById("projectConfigBtn");
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
          summary: "后续新发起的 CCB 执行会按当前用户态直接放开，不再继续按目录补权限，默认覆盖项目目录、CLI 会话目录和本机管理动作。",
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
        effect: "默认更安全；需要真实仓修改、系统级控制或发布安装时不适用。",
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

    function normalizeProjectConfigPayload(projectId, payload) {
      const body = (payload && typeof payload === "object") ? payload : {};
      const project = (body.project && typeof body.project === "object") ? body.project : {};
      return {
        project_id: String(projectId || "").trim(),
        config_path: firstNonEmptyText([body.config_path, body.configPath]),
        status: (project.status && typeof project.status === "object") ? project.status : {},
        execution_context: normalizeProjectConfigExecutionContext(project.execution_context || project.executionContext || null),
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
        void saveProjectConfigDraft();
      });
      document.addEventListener("keydown", (event) => {
        if (!PROJECT_CONFIG_UI.open) return;
        if (event && event.key === "Escape") closeProjectConfigDrawer();
      });
    }

    function updateProjectConfigButtonState() {
      const btn = projectConfigBtnNode();
      if (!btn) return;
      const pid = currentProjectConfigProjectId();
      const enabled = !!pid;
      btn.disabled = !enabled;
      btn.style.display = enabled ? "" : "none";
      btn.classList.toggle("active", !!PROJECT_CONFIG_UI.open && enabled);
      btn.title = enabled ? "打开 项目配置" : "总览视图不提供项目配置";
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
      addField("服务端口", "server_port", { help: "当前项目绑定服务端口，如 18770。" });
      addField("探活路径", "health_source", { help: "最小 live 校验时使用的 health 路径。" });
      section.appendChild(grid);
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
      title.textContent = "项目配置" + (project && project.name ? " · " + String(project.name) : "");
      sub.textContent = pid
        ? ("项目级 execution_context 真源编辑；Session 只保留身份与有效上下文只读展示。当前项目: " + pid)
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

    function openProjectConfigDrawer() {
      const pid = currentProjectConfigProjectId();
      if (!pid) return;
      PROJECT_CONFIG_UI.open = true;
      PROJECT_CONFIG_UI.projectId = pid;
      renderProjectConfigDrawer();
      void loadProjectConfigData(pid, { force: false, preserveMessage: true });
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
      hookProjectConfigIntoRender();
      updateProjectConfigButtonState();
    }

    window.addEventListener("load", initProjectConfigUI);
