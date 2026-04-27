    const TASK_CREATE_STAGE_OPTIONS = [
      { value: "draft", label: "待开始 / draft" },
      { value: "review", label: "方案评审 / review" },
      { value: "dispatch", label: "派发执行 / dispatch" },
      { value: "acceptance", label: "验收收口 / acceptance" },
      { value: "done", label: "已完成 / done" },
    ];
    const TASK_CREATE_REQUIRED_ROLES = [
      ["owner", "主负责位"],
      ["executor", "执行位"],
      ["validator", "验收位"],
    ];
    const TASK_CREATE_UI = {
      open: false,
      busyAction: "",
      form: null,
      result: null,
      error: "",
    };

    function taskCreateText(value) {
      return String(value == null ? "" : value).trim();
    }

    function taskCreateFirst(values, fallback = "") {
      const list = Array.isArray(values) ? values : [];
      for (const value of list) {
        const text = taskCreateText(value);
        if (text) return text;
      }
      return taskCreateText(fallback);
    }

    function taskCreateLookupText(value) {
      if (typeof normalizeTaskRoleLookupText === "function") {
        return normalizeTaskRoleLookupText(value);
      }
      return taskCreateText(value).toLowerCase();
    }

    function taskCreateProjectId(projectId = "") {
      const pid = taskCreateText(projectId || (typeof STATE !== "undefined" && STATE && STATE.project));
      return pid && pid !== "overview" ? pid : "";
    }

    function taskCreateRoleCandidateRows(projectId = "") {
      const pid = taskCreateProjectId(projectId);
      if (!pid) return [];
      const out = [];
      const seen = new Set();
      const push = (row, extra = {}) => {
        const src = Object.assign({}, extra || {}, (row && typeof row === "object") ? row : {});
        const sessionId = taskCreateFirst([src.session_id, src.sessionId, src.id]);
        const channelName = taskCreateFirst([src.channel_name, src.channelName, src.primaryChannel, src.name]);
        const alias = taskCreateFirst([src.alias, src.display_name, src.displayName, src.desc]);
        const agentName = taskCreateFirst([src.agent_name, src.agentName, alias, src.name, channelName]);
        const displayName = taskCreateFirst([src.display_name, src.displayName, alias, agentName, channelName, sessionId]);
        if (!displayName && !channelName && !sessionId) return;
        const key = sessionId || [channelName, displayName, agentName].map(taskCreateLookupText).join("::");
        if (!key || seen.has(key)) return;
        seen.add(key);
        const label = channelName && displayName && taskCreateLookupText(channelName) !== taskCreateLookupText(displayName)
          ? channelName + " / " + displayName
          : (displayName || channelName || sessionId);
        out.push({
          label,
          value: label,
          agentName: agentName || displayName,
          channelName,
          sessionId,
          alias: alias || displayName || agentName,
          isPrimary: !!(src.is_primary || src.isPrimary || taskCreateText(src.session_role || src.sessionRole) === "primary"),
        });
      };

      if (typeof getTaskRoleProjectSessionCandidates === "function") {
        getTaskRoleProjectSessionCandidates(pid).forEach((row) => push(row));
      }
      const project = typeof projectById === "function" ? projectById(pid) : null;
      if (project && typeof project === "object") {
        (Array.isArray(project.channel_sessions) ? project.channel_sessions : []).forEach((row) => push(row));
        (Array.isArray(project.channels) ? project.channels : []).forEach((row) => push(row));
        const registryChannels = Array.isArray(project.registry && project.registry.channels)
          ? project.registry.channels
          : [];
        registryChannels.forEach((channel) => {
          const channelName = taskCreateText(channel && channel.channel_name);
          if (channel && channel.primary_session_id) {
            push({
              session_id: channel.primary_session_id,
              channel_name: channelName,
              display_name: channel.primary_session_alias,
              alias: channel.primary_session_alias,
              is_primary: true,
            });
          }
          (Array.isArray(channel && channel.session_candidates) ? channel.session_candidates : []).forEach((candidate) => {
            push(candidate, {
              channel_name: channelName,
              display_name: candidate && (candidate.display_name || candidate.desc || channel.primary_session_alias),
              alias: candidate && (candidate.display_name || candidate.desc || channel.primary_session_alias),
            });
          });
        });
      }
      out.sort((a, b) => {
        if (!!a.isPrimary !== !!b.isPrimary) return a.isPrimary ? -1 : 1;
        return String(a.label || "").localeCompare(String(b.label || ""), "zh-Hans-CN");
      });
      return out;
    }

    function taskCreateDefaultForm(projectId = "") {
      const pid = taskCreateProjectId(projectId);
      let owner = "";
      if (typeof STATE !== "undefined" && STATE && STATE.channel) {
        const targetChannel = taskCreateText(STATE.channel);
        const hit = taskCreateRoleCandidateRows(pid).find((row) => taskCreateText(row.channelName) === targetChannel);
        owner = hit ? String(hit.value || "") : "";
      }
      return {
        title: "",
        kind: "实施任务",
        stage: "draft",
        owner,
        executor: "",
        validator: "",
        reviewer: "",
        visualReviewer: "",
        outputPath: "",
        dryRun: false,
        force: false,
        includeMarkdown: false,
      };
    }

    function ensureTaskCreateForm(projectId = "") {
      if (!TASK_CREATE_UI.form || typeof TASK_CREATE_UI.form !== "object") {
        TASK_CREATE_UI.form = taskCreateDefaultForm(projectId);
      }
      return TASK_CREATE_UI.form;
    }

    function taskCreateFindRoleCandidate(value, projectId = "") {
      const target = taskCreateLookupText(value);
      if (!target) return null;
      return taskCreateRoleCandidateRows(projectId).find((row) => {
        const values = [
          row.value,
          row.label,
          row.agentName,
          row.alias,
          row.channelName,
          row.sessionId,
          row.channelName && row.alias ? row.channelName + " / " + row.alias : "",
          row.channelName && row.agentName ? row.channelName + " / " + row.agentName : "",
        ];
        return values.some((item) => taskCreateLookupText(item) === target);
      }) || null;
    }

    function taskCreateRolePayload(value, projectId = "") {
      const text = taskCreateText(value);
      if (!text) return null;
      const candidate = taskCreateFindRoleCandidate(text, projectId);
      if (candidate) {
        return {
          agentName: candidate.agentName || candidate.alias || text,
          channelName: candidate.channelName || "",
          sessionId: candidate.sessionId || "",
          alias: candidate.alias || candidate.agentName || text,
        };
      }
      const split = text.split(/\s+\/\s+/).map((part) => taskCreateText(part)).filter(Boolean);
      if (split.length >= 2) {
        return { channelName: split[0], agentName: split.slice(1).join(" / "), alias: split.slice(1).join(" / ") };
      }
      return { agentName: text };
    }

    function taskCreateBuildPayload(projectId = "", opts = {}) {
      const pid = taskCreateProjectId(projectId);
      const form = ensureTaskCreateForm(pid);
      const payload = {
        title: taskCreateText(form.title),
        kind: taskCreateText(form.kind) || "实施任务",
        stage: taskCreateText(form.stage) || "draft",
        owner: taskCreateRolePayload(form.owner, pid),
        executor: taskCreateRolePayload(form.executor, pid),
        validator: taskCreateRolePayload(form.validator, pid),
        reviewer: taskCreateRolePayload(form.reviewer, pid),
        visualReviewer: taskCreateRolePayload(form.visualReviewer, pid),
        dryRun: !!form.dryRun,
        force: !!form.force,
        includeMarkdown: !!form.includeMarkdown,
      };
      const outputPath = taskCreateText(form.outputPath);
      if (outputPath) payload.outputPath = outputPath;
      if (opts && opts.forceDryRun) payload.dryRun = true;
      return payload;
    }

    function taskCreateLocalValidation(projectId = "") {
      const form = ensureTaskCreateForm(projectId);
      const errors = [];
      if (!taskCreateText(form.title)) errors.push("请填写任务标题。");
      TASK_CREATE_REQUIRED_ROLES.forEach(([key, label]) => {
        if (!taskCreateText(form[key])) errors.push("请填写" + label + "，必须落到具体 Agent。");
      });
      return errors;
    }

    function taskCreateValidationMessages(payload) {
      const source = (payload && typeof payload === "object") ? payload : {};
      const validation = (source.validation && typeof source.validation === "object") ? source.validation : {};
      const messages = [];
      const seen = new Set();
      const appendList = (items, prefix = "") => {
        (Array.isArray(items) ? items : []).forEach((item) => {
          const text = typeof item === "string"
            ? item
            : taskCreateFirst([item && item.message, item && item.detail, item && item.role_label, item && item.code]);
          const key = taskCreateLookupText(text);
          if (text && !seen.has(key)) {
            seen.add(key);
            messages.push(prefix ? (prefix + text) : text);
          }
        });
      };
      appendList(validation.errors);
      appendList(validation.gaps);
      appendList(validation.warnings, "警告：");
      if (!messages.length) {
        const fallback = taskCreateFirst([source.message, source.error, source.detail]);
        if (fallback) messages.push(fallback);
      }
      return messages;
    }

    function taskCreateSetError(message, result = null) {
      TASK_CREATE_UI.error = taskCreateText(message);
      TASK_CREATE_UI.result = result;
      renderTaskCreateModal();
    }

    async function taskCreateSubmit(action = "validate") {
      const pid = taskCreateProjectId();
      if (!pid) {
        taskCreateSetError("请先选择具体项目后再创建任务。");
        return;
      }
      if (TASK_CREATE_UI.busyAction) return;
      const localErrors = taskCreateLocalValidation(pid);
      if (localErrors.length) {
        taskCreateSetError(localErrors.join(" "), {
          ok: false,
          action: "local_validate",
          validation: { ok: false, errors: localErrors, warnings: [], gaps: [] },
        });
        return;
      }
      const isCreate = action === "create";
      const payload = taskCreateBuildPayload(pid, { forceDryRun: !isCreate });
      TASK_CREATE_UI.busyAction = isCreate ? "create" : "validate";
      TASK_CREATE_UI.error = "";
      TASK_CREATE_UI.result = null;
      renderTaskCreateModal();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/tasks/" + (isCreate ? "create" : "validate"), {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data || data.ok === false) {
          const messages = taskCreateValidationMessages(data);
          const fallback = messages.length ? messages.join("；") : ("请求失败：HTTP " + resp.status);
          TASK_CREATE_UI.error = fallback;
          TASK_CREATE_UI.result = data || { ok: false };
          return;
        }
        TASK_CREATE_UI.result = Object.assign({}, data, { action: isCreate ? "create" : "validate" });
        TASK_CREATE_UI.error = "";
        if (typeof toast === "function") {
          toast(isCreate ? (data.dry_run ? "预览通过，未写入任务文件。" : "任务已创建。") : "校验通过，可以创建任务。");
        }
        const createdPath = taskCreateText(data.path);
        const createdTaskId = taskCreateText(data.task_id);
        if (isCreate && createdPath && typeof STATE !== "undefined" && STATE) {
          STATE.selectedPath = createdPath;
          STATE.selectedTaskId = createdTaskId;
          if (typeof syncSelectedTaskSelectionStorage === "function") syncSelectedTaskSelectionStorage();
          if (typeof setHash === "function") setHash();
        }
      } catch (err) {
        TASK_CREATE_UI.error = "请求失败：" + taskCreateText((err && err.message) || err || "网络或服务异常");
        TASK_CREATE_UI.result = { ok: false, action };
      } finally {
        TASK_CREATE_UI.busyAction = "";
        renderTaskCreateModal();
      }
    }

    function taskCreateResultBlock(result, errorText = "") {
      if (!result && !errorText) return null;
      const ok = !!(result && result.ok) && !errorText;
      const box = el("section", { class: "task-create-result " + (ok ? "is-ok" : "is-error") });
      const title = ok ? "结果可用" : "需要处理";
      box.appendChild(el("div", { class: "task-create-result-title", text: title }));
      const hasStructuredValidation = !!(result && result.validation && typeof result.validation === "object");
      const messages = hasStructuredValidation ? taskCreateValidationMessages(result) : [];
      if (errorText) {
        box.appendChild(el("div", { class: "task-create-result-message", text: messages.length ? "请按以下提示修正后重试。" : errorText }));
      } else if (result) {
        const msg = result.action === "validate_create_payload"
          ? "校验通过，后端按 dryRun=true 预览，不写入文件。"
          : (result.dry_run ? "预览通过，未写入任务文件。" : "创建成功，任务文件已由后端安全写入。");
        box.appendChild(el("div", { class: "task-create-result-message", text: msg }));
      }
      if (messages.length && !ok) {
        const list = el("ul", { class: "task-create-validation-list" });
        messages.slice(0, 8).forEach((msg) => list.appendChild(el("li", { text: msg })));
        box.appendChild(list);
      }
      if (result && result.path) {
        box.appendChild(el("code", { class: "task-create-path", text: String(result.path) }));
      }
      if (ok && result && result.path && !result.dry_run) {
        const ops = el("div", { class: "task-create-result-ops" });
        const refreshBtn = el("button", { class: "btn primary", type: "button", text: "刷新并定位任务" });
        refreshBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (typeof STATE !== "undefined" && STATE) {
            STATE.panelMode = "task";
            STATE.selectedPath = String(result.path || "");
            STATE.selectedTaskId = String(result.task_id || "");
            if (typeof syncSelectedTaskSelectionStorage === "function") syncSelectedTaskSelectionStorage();
            if (typeof setHash === "function") setHash();
          }
          if (typeof triggerProjectDashboardRebuild === "function") {
            triggerProjectDashboardRebuild();
          } else {
            window.location.reload();
          }
        });
        ops.appendChild(refreshBtn);
        box.appendChild(ops);
      }
      return box;
    }

    function taskCreateField(label, key, attrs = {}) {
      const form = ensureTaskCreateForm();
      const field = el("label", { class: "task-create-field" });
      field.appendChild(el("span", { text: label }));
      const input = el("input", Object.assign({
        class: "input",
        value: String(form[key] || ""),
      }, attrs || {}));
      input.addEventListener("input", () => {
        form[key] = input.value;
      });
      field.appendChild(input);
      return field;
    }

    function taskCreateRoleField(label, key, projectId = "") {
      return taskCreateField(label, key, {
        list: "taskCreateRoleCandidates",
        placeholder: "输入或选择具体 Agent，例如：子级04 / 前端-任务业务",
        autocomplete: "off",
      });
    }

    function taskCreateOptionSelect(label, key, options) {
      const form = ensureTaskCreateForm();
      const field = el("label", { class: "task-create-field" });
      field.appendChild(el("span", { text: label }));
      const select = el("select", { class: "input" });
      (Array.isArray(options) ? options : []).forEach((option) => {
        const node = el("option", { value: option.value, text: option.label });
        if (String(option.value) === String(form[key] || "")) node.selected = true;
        select.appendChild(node);
      });
      select.addEventListener("change", () => {
        form[key] = select.value;
      });
      field.appendChild(select);
      return field;
    }

    function taskCreateCheckbox(label, key) {
      const form = ensureTaskCreateForm();
      const field = el("label", { class: "task-create-check" });
      const input = el("input", { type: "checkbox" });
      input.checked = !!form[key];
      input.addEventListener("change", () => {
        form[key] = !!input.checked;
      });
      field.appendChild(input);
      field.appendChild(el("span", { text: label }));
      return field;
    }

    function ensureTaskCreateModal() {
      let mask = document.getElementById("taskCreateMask");
      if (mask) return mask;
      mask = el("div", { class: "bmask task-create-mask", id: "taskCreateMask", role: "dialog", "aria-modal": "true", "aria-label": "创建任务" });
      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeTaskCreateModal();
      });
      document.body.appendChild(mask);
      return mask;
    }

    function renderTaskCreateRoleDatalist(projectId = "") {
      const list = el("datalist", { id: "taskCreateRoleCandidates" });
      taskCreateRoleCandidateRows(projectId).slice(0, 160).forEach((row) => {
        list.appendChild(el("option", { value: row.value, label: row.sessionId ? (row.sessionId + " · " + row.channelName) : row.channelName }));
      });
      return list;
    }

    function renderTaskCreateModal() {
      if (!TASK_CREATE_UI.open) return;
      const pid = taskCreateProjectId();
      const form = ensureTaskCreateForm(pid);
      const mask = ensureTaskCreateModal();
      mask.innerHTML = "";
      mask.appendChild(renderTaskCreateRoleDatalist(pid));
      const modal = el("div", { class: "bmodal task-create-modal", role: "document" });
      const head = el("div", { class: "task-create-head" });
      const titleWrap = el("div", { class: "task-create-head-copy" });
      titleWrap.appendChild(el("div", { class: "task-create-kicker", text: "P2-C · 安全创建入口" }));
      titleWrap.appendChild(el("div", { class: "task-create-title", text: "创建任务" }));
      titleWrap.appendChild(el("div", { class: "task-create-sub", text: "只调用后端 create/validate 接口，不直接写 Markdown，不替代正式派发链路。" }));
      head.appendChild(titleWrap);
      const closeBtn = el("button", { class: "btn", type: "button", text: "关闭" });
      closeBtn.addEventListener("click", closeTaskCreateModal);
      head.appendChild(closeBtn);
      modal.appendChild(head);

      const body = el("div", { class: "task-create-body" });
      const grid = el("div", { class: "task-create-grid" });
      grid.appendChild(taskCreateField("任务标题", "title", { placeholder: "例如：20260427-某模块前端最小修复" }));
      grid.appendChild(taskCreateOptionSelect("阶段", "stage", TASK_CREATE_STAGE_OPTIONS));
      grid.appendChild(taskCreateRoleField("主负责位", "owner", pid));
      grid.appendChild(taskCreateRoleField("执行位", "executor", pid));
      grid.appendChild(taskCreateRoleField("验收位", "validator", pid));
      grid.appendChild(taskCreateRoleField("审核或门禁位", "reviewer", pid));
      grid.appendChild(taskCreateRoleField("视觉审核位", "visualReviewer", pid));
      grid.appendChild(taskCreateField("输出路径（可选）", "outputPath", { placeholder: "留空时由后端按主负责通道和阶段生成" }));
      body.appendChild(grid);
      const checks = el("div", { class: "task-create-checks" });
      checks.appendChild(taskCreateCheckbox("只预览，不写入", "dryRun"));
      checks.appendChild(taskCreateCheckbox("允许覆盖同名文件", "force"));
      checks.appendChild(taskCreateCheckbox("返回 Markdown 预览", "includeMarkdown"));
      body.appendChild(checks);
      const stageHint = taskCreateText(form.stage) === "dispatch"
        ? "当前选择 dispatch 阶段：后端会要求正式 announce_run_id，缺失时返回 422 validation_failed 且不落盘。"
        : "建议先用“校验”确认责任位和阶段门禁，再创建任务。";
      body.appendChild(el("div", { class: "task-create-hint", text: stageHint }));
      const resultBlock = taskCreateResultBlock(TASK_CREATE_UI.result, TASK_CREATE_UI.error);
      if (resultBlock) body.appendChild(resultBlock);
      modal.appendChild(body);

      const foot = el("div", { class: "task-create-foot" });
      const validateBtn = el("button", { class: "btn", type: "button", text: TASK_CREATE_UI.busyAction === "validate" ? "校验中..." : "校验" });
      validateBtn.disabled = !!TASK_CREATE_UI.busyAction;
      validateBtn.addEventListener("click", () => taskCreateSubmit("validate"));
      const createBtn = el("button", { class: "btn primary", type: "button", text: TASK_CREATE_UI.busyAction === "create" ? "创建中..." : (form.dryRun ? "预览创建" : "创建任务") });
      createBtn.disabled = !!TASK_CREATE_UI.busyAction;
      createBtn.addEventListener("click", () => taskCreateSubmit("create"));
      foot.appendChild(validateBtn);
      foot.appendChild(createBtn);
      modal.appendChild(foot);
      mask.appendChild(modal);
      mask.classList.add("show");
    }

    function openTaskCreateModal(projectId = "") {
      const pid = taskCreateProjectId(projectId);
      if (!pid) {
        alert("请先选择具体项目后再创建任务。");
        return;
      }
      TASK_CREATE_UI.open = true;
      TASK_CREATE_UI.busyAction = "";
      TASK_CREATE_UI.error = "";
      TASK_CREATE_UI.result = null;
      TASK_CREATE_UI.form = taskCreateDefaultForm(pid);
      renderTaskCreateModal();
    }

    function closeTaskCreateModal() {
      TASK_CREATE_UI.open = false;
      TASK_CREATE_UI.busyAction = "";
      const mask = document.getElementById("taskCreateMask");
      if (mask) mask.classList.remove("show");
    }

    function buildTaskCreateEntryAction(projectId = "") {
      const pid = taskCreateProjectId(projectId);
      const wrap = el("div", { class: "task-create-entry-wrap" });
      const btn = el("button", {
        type: "button",
        class: "task-create-entry-btn",
        text: "创建任务",
        title: "通过后端安全接口创建标准任务文件",
      });
      btn.disabled = !pid;
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openTaskCreateModal(pid);
      });
      wrap.appendChild(btn);
      return wrap;
    }
