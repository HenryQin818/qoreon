    // Unified task detail renderer shared by task homepage cards and conversation task drawer.
    const UNIFIED_TASK_DETAIL_VIEW = {
      currentModel: null,
      currentContext: null,
      filePreviewCache: Object.create(null),
    };

    function unifiedTaskDetailTone(statusText) {
      if (typeof taskDisplayStatusMeta === "function") return taskDisplayStatusMeta(statusText, "待办").tone;
      const text = unifiedTaskDetailText(statusText);
      if (/完成|done/i.test(text)) return "good";
      if (/阻塞|异常|验收|review/i.test(text)) return "warn";
      return "muted";
    }

    function unifiedTaskDetailFormatTime(value) {
      const text = unifiedTaskDetailText(value);
      if (!text) return "";
      if (typeof compactDateTime === "function") return compactDateTime(text) || text;
      if (typeof shortDateTime === "function") return shortDateTime(text) || text;
      return text;
    }

    function unifiedTaskDetailResolveFsPath(taskPath, context = {}) {
      const raw = unifiedTaskDetailText(taskPath).replace(/\\/g, "/");
      if (!raw) return "";
      if (raw[0] === "/" || /^https?:\/\//i.test(raw)) return raw;
      if (typeof resolveConversationTaskFsPath === "function") {
        const fromConversation = unifiedTaskDetailText(resolveConversationTaskFsPath(raw));
        if (fromConversation) return fromConversation;
      }
      const projects = (typeof DATA !== "undefined" && Array.isArray(DATA.projects))
        ? DATA.projects
        : [];
      const projectId = unifiedTaskDetailText(context.projectId || (typeof STATE !== "undefined" && STATE.project) || "");
      const project = projects.find((row) => unifiedTaskDetailText(row && row.id) === projectId)
        || projects.find((row) => unifiedTaskDetailText(row && row.project_id) === projectId)
        || null;
      const root = unifiedTaskDetailFirstNonEmpty([
        context.projectRoot,
        project && project.runtime_root_rel,
        project && project.project_root_rel,
      ], "");
      const normalizedRoot = root.replace(/\/+$/, "");
      if (normalizedRoot && (raw === normalizedRoot || raw.startsWith(normalizedRoot + "/"))) return raw;
      return normalizedRoot ? (normalizedRoot + "/" + raw.replace(/^\/+/, "")) : raw;
    }

    function unifiedTaskDetailPreviewKey(taskPath, context = {}) {
      const fsPath = unifiedTaskDetailResolveFsPath(taskPath, context);
      return fsPath || unifiedTaskDetailText(taskPath);
    }

    function getUnifiedTaskDetailFilePreviewEntry(taskPath, context = {}) {
      const key = unifiedTaskDetailPreviewKey(taskPath, context);
      if (!key) return null;
      const cache = UNIFIED_TASK_DETAIL_VIEW.filePreviewCache;
      if (!cache[key] || typeof cache[key] !== "object") {
        cache[key] = {
          key,
          taskPath: unifiedTaskDetailText(taskPath),
          resolvedPath: key,
          loading: false,
          loaded: false,
          error: "",
          item: null,
        };
      }
      return cache[key];
    }

    function rerenderUnifiedTaskDetailForPath(taskPath) {
      const current = UNIFIED_TASK_DETAIL_VIEW.currentModel;
      if (current && current.taskPath && current.taskPath === taskPath) {
        renderUnifiedTaskDetailModal();
        return;
      }
      try {
        if (typeof STATE !== "undefined" && STATE && typeof selectedItem === "function" && typeof renderDetail === "function") {
          const item = selectedItem();
          if (item && unifiedTaskDetailText(item.path) === unifiedTaskDetailText(taskPath)) renderDetail(item);
        }
      } catch (_) {}
    }

    function requestUnifiedTaskDetailFilePreview(taskPath, context = {}, opts = {}) {
      const entry = getUnifiedTaskDetailFilePreviewEntry(taskPath, context);
      if (!entry) return null;
      const force = !!opts.force;
      if (entry.loading) return entry;
      if (!force && (entry.loaded || entry.error)) return entry;
      entry.loading = true;
      entry.error = "";
      if (force) {
        entry.loaded = false;
        entry.item = null;
      }
      (async () => {
        try {
          const resp = await fetch("/api/fs/read?path=" + encodeURIComponent(entry.resolvedPath), {
            headers: typeof authHeaders === "function" ? authHeaders({}) : {},
            credentials: "same-origin",
          });
          if (!resp.ok) {
            const detail = typeof parseResponseDetail === "function" ? await parseResponseDetail(resp) : "";
            throw new Error(detail || ("HTTP " + resp.status));
          }
          const data = await resp.json().catch(() => null);
          const item = data && data.ok && data.item && typeof data.item === "object" ? data.item : null;
          if (!item) throw new Error("只读文件链路未返回任务正文。");
          entry.item = {
            path: unifiedTaskDetailText(item.path || entry.resolvedPath),
            is_text: !!item.is_text,
            preview_mode: unifiedTaskDetailText(item.preview_mode).toLowerCase(),
            truncated: !!item.truncated,
            content: String(item.content || ""),
          };
          entry.loaded = true;
        } catch (err) {
          entry.loaded = false;
          entry.item = null;
          entry.error = unifiedTaskDetailText((err && err.message) || err || "正文读取失败") || "正文读取失败";
        } finally {
          entry.loading = false;
          rerenderUnifiedTaskDetailForPath(entry.taskPath);
        }
      })();
      return entry;
    }

    function buildUnifiedTaskDetailRoleMemberNode(member) {
      const meta = typeof taskRoleMemberDisplayMeta === "function"
        ? taskRoleMemberDisplayMeta(member)
        : {
            text: unifiedTaskDetailFirstNonEmpty([
              member && member.display_name,
              member && member.agent_alias,
              member && member.alias,
              member && member.agent_name,
              member && member.name,
            ], "待补充"),
            meta: unifiedTaskDetailFirstNonEmpty([member && member.channel_name, member && member.responsibility], ""),
          };
      const node = el("div", { class: "unified-task-role-member" });
      const avatar = typeof buildTaskRoleAvatar === "function"
        ? buildTaskRoleAvatar(member)
        : el("span", { class: "unified-task-role-avatar", text: unifiedTaskDetailText(meta.text).slice(0, 1) || "任" });
      if (avatar) node.appendChild(avatar);
      const text = el("div", { class: "unified-task-role-text" });
      text.appendChild(el("div", { class: "unified-task-role-name", text: meta.text || "待补充" }));
      if (meta.meta) text.appendChild(el("div", { class: "unified-task-role-meta", text: meta.meta }));
      node.appendChild(text);
      return node;
    }

    function buildUnifiedTaskDetailRoleGroup(label, members, roleKey) {
      const list = Array.isArray(members) ? members : [];
      const group = el("div", { class: "unified-task-role-group role-" + roleKey });
      group.appendChild(el("div", { class: "unified-task-role-label", text: label }));
      const body = el("div", { class: "unified-task-role-members" });
      if (!list.length) {
        body.appendChild(el("div", { class: "unified-task-role-empty", text: "未配置" }));
      } else {
        list.forEach((member) => body.appendChild(buildUnifiedTaskDetailRoleMemberNode(member)));
      }
      group.appendChild(body);
      return group;
    }

    function buildUnifiedTaskDetailRoles(model) {
      const roles = model && model.roles ? model.roles : unifiedTaskDetailResponsibilityModel(null);
      const section = el("section", { class: "unified-task-detail-section unified-task-detail-roles" });
      section.appendChild(el("div", { class: "unified-task-detail-section-title", text: "责任位" }));
      const grid = el("div", { class: "unified-task-role-grid" });
      grid.appendChild(buildUnifiedTaskDetailRoleGroup("主负责位", roles.main_owner ? [roles.main_owner] : [], "main-owner"));
      grid.appendChild(buildUnifiedTaskDetailRoleGroup("执行位", roles.executors || [], "executor"));
      grid.appendChild(buildUnifiedTaskDetailRoleGroup("管理位", roles.management_slot || [], "management"));
      grid.appendChild(buildUnifiedTaskDetailRoleGroup("验证位", roles.validators || [], "validator"));
      grid.appendChild(buildUnifiedTaskDetailRoleGroup("用户审核位", roles.user_reviewers || [], "user-reviewer"));
      section.appendChild(grid);
      return section;
    }

    function buildUnifiedTaskDetailFacts(model) {
      const details = el("details", { class: "unified-task-detail-section unified-task-detail-fields" });
      details.appendChild(el("summary", { class: "unified-task-detail-section-title", text: "任务字段" }));
      const grid = el("div", { class: "unified-task-fields-grid" });
      (Array.isArray(model.facts) ? model.facts : []).forEach((row) => {
        const item = el("div", { class: "unified-task-field-row" + (row.label === "任务路径" ? " is-path" : "") });
        item.appendChild(el("div", { class: "unified-task-field-label", text: row.label }));
        item.appendChild(el("div", { class: "unified-task-field-value", text: row.value, title: row.value }));
        grid.appendChild(item);
      });
      if (!grid.childNodes.length) {
        grid.appendChild(el("div", { class: "unified-task-field-empty", text: "当前任务暂无额外字段。" }));
      }
      details.appendChild(grid);
      return details;
    }

    function buildUnifiedTaskDetailReadingBody(entry) {
      const state = entry && typeof entry === "object" ? entry : null;
      const item = state && state.item && typeof state.item === "object" ? state.item : null;
      if (!state) return el("div", { class: "unified-task-reading-empty", text: "当前任务缺少 task_path，暂时无法读取正文。" });
      if (state.loading) return el("div", { class: "unified-task-reading-loading", text: "正在读取任务正文…" });
      if (state.error) return el("div", { class: "unified-task-reading-error", text: "正文读取失败：" + state.error });
      if (!item || !unifiedTaskDetailText(item.content)) return el("div", { class: "unified-task-reading-empty", text: "只读链路尚未返回可显示正文。" });
      if (!item.is_text) return el("div", { class: "unified-task-reading-empty", text: "当前任务文件不是文本类型，请打开源文件阅读。" });
      const body = el("div", { class: "unified-task-reading-body" });
      if (item.preview_mode === "markdown" && typeof markdownToHtml === "function") {
        body.classList.add("is-markdown");
        body.innerHTML = markdownToHtml(String(item.content || ""));
      } else {
        body.classList.add("is-plain");
        body.appendChild(el("pre", { class: "unified-task-reading-pre", text: String(item.content || "") }));
      }
      return body;
    }

    function buildUnifiedTaskDetailReading(model, context = {}) {
      const details = el("details", { class: "unified-task-detail-section unified-task-detail-reading" });
      const summary = el("summary", { class: "unified-task-detail-section-title", text: "完整任务正文" });
      if (model.taskPath) summary.appendChild(el("span", { class: "unified-task-readonly-chip", text: "只读" }));
      details.appendChild(summary);
      const entry = model.taskPath ? requestUnifiedTaskDetailFilePreview(model.taskPath, context) : null;
      details.appendChild(buildUnifiedTaskDetailReadingBody(entry));
      if (entry && entry.item && entry.item.truncated) {
        details.appendChild(el("div", { class: "unified-task-reading-note", text: "当前预览已截断，可通过“打开源文件”继续阅读。" }));
      }
      return details;
    }

    function buildUnifiedTaskDetailInteraction(model) {
      const section = el("section", { class: "unified-task-detail-section unified-task-detail-interaction" });
      section.appendChild(el("div", { class: "unified-task-detail-section-title", text: "最新状态与互动区" }));
      const card = el("div", { class: "unified-task-interaction-card" });
      const head = el("div", { class: "unified-task-interaction-head" });
      head.appendChild(chip(model.statusText || "待办", unifiedTaskDetailTone(model.statusText)));
      if (model.latestActionKind) head.appendChild(chip(model.latestActionKind, "muted"));
      if (model.latestActionAt) head.appendChild(el("span", { class: "unified-task-interaction-time", text: unifiedTaskDetailFormatTime(model.latestActionAt) }));
      card.appendChild(head);
      card.appendChild(el("div", {
        class: "unified-task-interaction-text" + (!model.latestActionText ? " is-placeholder" : ""),
        text: model.latestActionText || "当前暂无最新动作补充。",
      }));
      const source = unifiedTaskDetailText(model.latestActionSource);
      if (source) card.appendChild(el("div", { class: "unified-task-interaction-source", text: "来源 " + source }));
      section.appendChild(card);
      return section;
    }

    function buildUnifiedTaskDetailContent(model, context = {}) {
      const root = el("article", { class: "unified-task-detail" });
      const hero = el("section", { class: "unified-task-detail-hero" });
      const top = el("div", { class: "unified-task-detail-topline" });
      top.appendChild(el("span", { class: "unified-task-type-fallback is-" + model.typeKey, text: model.typeKey === "child" ? "子任务" : "主任务" }));
      top.appendChild(chip(model.statusText || "待办", unifiedTaskDetailTone(model.statusText)));
      if (model.groupTitle) top.appendChild(chip(model.groupTitle, "muted"));
      hero.appendChild(top);
      hero.appendChild(el("h2", { class: "unified-task-detail-title", text: model.title, title: model.taskPath || model.title }));
      hero.appendChild(el("p", {
        class: "unified-task-detail-summary" + (!model.summaryText ? " is-placeholder" : ""),
        text: model.summaryText || model.summaryPlaceholder,
      }));
      root.appendChild(hero);
      root.appendChild(buildUnifiedTaskDetailRoles(model));
      root.appendChild(buildUnifiedTaskDetailFacts(model));
      root.appendChild(buildUnifiedTaskDetailInteraction(model));
      root.appendChild(buildUnifiedTaskDetailReading(model, context));
      return root;
    }

    function renderUnifiedTaskDetailInline(container, raw, context = {}) {
      if (!container) return false;
      const model = unifiedTaskDetailModelFromTaskItem(raw, context);
      container.innerHTML = "";
      container.appendChild(buildUnifiedTaskDetailContent(model, context));
      return true;
    }

    function closeUnifiedTaskDetail(opts = {}) {
      const ctx = UNIFIED_TASK_DETAIL_VIEW.currentContext;
      const existing = document.getElementById("unifiedTaskDetailMask");
      if (existing) existing.remove();
      UNIFIED_TASK_DETAIL_VIEW.currentModel = null;
      UNIFIED_TASK_DETAIL_VIEW.currentContext = null;
      if (opts.notify !== false && ctx && typeof ctx.onClose === "function") {
        ctx.onClose();
      }
    }

    function renderUnifiedTaskDetailModal() {
      const model = UNIFIED_TASK_DETAIL_VIEW.currentModel;
      const context = UNIFIED_TASK_DETAIL_VIEW.currentContext || {};
      if (!model) {
        closeUnifiedTaskDetail({ notify: false });
        return;
      }
      const mask = el("div", { id: "unifiedTaskDetailMask", class: "bmask unified-task-detail-mask show" });
      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeUnifiedTaskDetail();
      });
      const dialog = el("div", { class: "bmodal unified-task-detail-modal" });
      const head = el("div", { class: "bmodalh unified-task-detail-modal-head" });
      const headMain = el("div", { class: "unified-task-detail-modal-titlewrap" });
      headMain.appendChild(el("div", { class: "t", text: "统一任务详情" }));
      headMain.appendChild(el("div", { class: "s", text: model.taskPath || "当前任务未提供源文件路径。" }));
      head.appendChild(headMain);
      const actions = el("div", { class: "unified-task-detail-modal-actions" });
      const openBtn = el("button", { class: "btn", type: "button", text: "打开源文件" });
      openBtn.disabled = !model.taskPath;
      openBtn.addEventListener("click", () => {
        if (!model.taskPath) return;
        if (typeof context.onOpenSource === "function") {
          context.onOpenSource(model);
          return;
        }
        const fsPath = unifiedTaskDetailResolveFsPath(model.taskPath, context);
        if (typeof openNew === "function") openNew("/api/fs/open?path=" + encodeURIComponent(fsPath || model.taskPath));
      });
      actions.appendChild(openBtn);
      const closeBtn = el("button", { class: "btn", type: "button", text: "关闭" });
      closeBtn.addEventListener("click", () => closeUnifiedTaskDetail());
      actions.appendChild(closeBtn);
      head.appendChild(actions);
      dialog.appendChild(head);
      const body = el("div", { class: "bmodalb unified-task-detail-modal-body" });
      body.appendChild(buildUnifiedTaskDetailContent(model, context));
      dialog.appendChild(body);
      mask.appendChild(dialog);
      const existing = document.getElementById("unifiedTaskDetailMask");
      if (existing) existing.replaceWith(mask);
      else document.body.appendChild(mask);
    }

    function openUnifiedTaskDetail(raw, context = {}) {
      const model = unifiedTaskDetailModelFromConversationDetail(raw, context);
      if (!model) return false;
      UNIFIED_TASK_DETAIL_VIEW.currentModel = model;
      UNIFIED_TASK_DETAIL_VIEW.currentContext = { ...context };
      renderUnifiedTaskDetailModal();
      return true;
    }
