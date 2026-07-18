    const RESULTS_SERVICES_DEFAULT_TYPE = "service";
    const RESULTS_SERVICES_RESOURCE_TYPES = {
      service: "服务",
      doc_page: "文档/页面",
    };

    const RESULTS_SERVICES_STATE = {
      open: false,
      activeTab: RESULTS_SERVICES_DEFAULT_TYPE,
      items: [],
      loadedProjectId: "",
      loading: false,
      saving: false,
      error: "",
      notice: "",
      editorMode: "",
      editingId: "",
      form: null,
    };

    function resultsServicesText(value, maxLen = 1000) {
      let text = value == null ? "" : String(value);
      text = text.trim();
      if (maxLen > 0 && text.length > maxLen) return text.slice(0, maxLen - 1) + "…";
      return text;
    }

    function resultsServicesCurrentProjectId() {
      try {
        const pid = resultsServicesText(typeof STATE !== "undefined" && STATE ? STATE.project : "", 160);
        if (pid && pid !== "overview") return pid;
      } catch (_) {}
      try {
        const pid = resultsServicesText(typeof DATA !== "undefined" && DATA ? (DATA.project_id || DATA.projectId) : "", 160);
        if (pid && pid !== "overview") return pid;
      } catch (_) {}
      return "";
    }

    function resultsServicesApiBase(projectId = "") {
      const pid = resultsServicesText(projectId || resultsServicesCurrentProjectId(), 160);
      return pid ? "/api/projects/" + encodeURIComponent(pid) + "/resources" : "";
    }

    function resultsServicesAuthHeaders(extra = {}) {
      const headers = Object.assign({}, extra || {});
      if (typeof authHeaders === "function") return authHeaders(headers);
      return headers;
    }

    async function resultsServicesResponseDetail(resp) {
      try {
        const data = await resp.clone().json();
        return resultsServicesText(data && (data.message || data.error || data.detail), 240);
      } catch (_) {}
      try {
        return resultsServicesText(await resp.text(), 240);
      } catch (_) {}
      return "";
    }

    function resultsServicesApiErrorMessage(resp, detail = "") {
      const status = Number(resp && resp.status || 0);
      if (status === 404) return "成果与服务清单接口未就绪，等待后端资源 API 加载。";
      if (status === 401 || status === 403) return "没有清单写入权限，请检查本机服务 Token。";
      return detail || ("资源清单请求失败（HTTP " + (status || "-") + "）。");
    }

    async function resultsServicesFetchJson(url, options = {}) {
      const resp = await fetch(url, Object.assign({ cache: "no-store" }, options || {}));
      if (!resp.ok) {
        const detail = await resultsServicesResponseDetail(resp);
        const err = new Error(resultsServicesApiErrorMessage(resp, detail));
        err.status = resp.status;
        err.detail = detail;
        throw err;
      }
      return resp.json().catch(() => ({}));
    }

    function normalizeResultsServicesType(type) {
      const raw = resultsServicesText(type, 80).toLowerCase();
      if (raw === "service" || raw === "services" || raw === "svc") return "service";
      return "doc_page";
    }

    function normalizeResultsServicesStatus(raw) {
      const source = raw && typeof raw === "object" ? raw : { status: raw };
      const normalizedKey = resultsServicesText(source.key, 80).toLowerCase();
      if (normalizedKey === "up") return { key: "up", label: "UP" };
      if (normalizedKey === "not_started") return { key: "not_started", label: "未启" };
      if (normalizedKey === "unknown") return { key: "unknown", label: "未知" };
      const value = resultsServicesText(
        source.status || source.state || source.service_status || source.serviceStatus || source.health,
        80
      ).toLowerCase();
      if (["up", "running", "healthy", "ok", "online", "alive"].includes(value)) {
        return { key: "up", label: "UP" };
      }
      if (["down", "stopped", "stop", "not_started", "not-started", "inactive", "offline", "idle"].includes(value)) {
        return { key: "not_started", label: "未启" };
      }
      return { key: "unknown", label: "未知" };
    }

    function resultsServicesTitleFromUrl(url, fallback = "") {
      const raw = resultsServicesText(url, 2200);
      const fb = resultsServicesText(fallback, 160);
      if (!raw) return fb;
      try {
        const parsed = new URL(raw, location.origin);
        const last = decodeURIComponent(String(parsed.pathname || "").split("/").filter(Boolean).pop() || "");
        return resultsServicesText(last || parsed.host || fb || raw, 160);
      } catch (_) {}
      const clean = raw.replace(/[?#].*$/, "").replace(/\/+$/, "");
      const last = clean.split(/[\\/]/).filter(Boolean).pop();
      return resultsServicesText(last || fb || raw, 160);
    }

    function normalizeResultsServicesItem(raw) {
      const src = raw && typeof raw === "object" ? raw : {};
      const url = resultsServicesText(src.url || src.href || src.path || src.link, 2200);
      const type = normalizeResultsServicesType(src.type || src.kind);
      const statusSource = src.service_status || src.serviceStatus || src.status || src.state || "";
      return {
        id: resultsServicesText(src.id, 120),
        project_id: resultsServicesText(src.project_id || src.projectId, 160),
        title: resultsServicesText(src.title || src.name || resultsServicesTitleFromUrl(url), 160),
        type,
        url,
        note: resultsServicesText(src.note || src.remark || src.description, 1000),
        source: resultsServicesText(src.source, 80),
        created_at: resultsServicesText(src.created_at || src.createdAt, 80),
        updated_at: resultsServicesText(src.updated_at || src.updatedAt, 80),
        sort_order: Number(src.sort_order || src.sortOrder || 0) || 0,
        service_status: normalizeResultsServicesStatus(statusSource),
      };
    }

    function normalizeResultsServicesListPayload(payload) {
      const rows = Array.isArray(payload && payload.resources)
        ? payload.resources
        : (Array.isArray(payload && payload.items) ? payload.items : []);
      return rows.map(normalizeResultsServicesItem).filter((item) => item.id || item.url || item.title);
    }

    function resultsServicesUrlObject(value) {
      const raw = resultsServicesText(value, 2200);
      if (!raw) return null;
      try {
        return new URL(raw, location.origin);
      } catch (_) {
        return null;
      }
    }

    function resultsServicesHasExplicitPort(value) {
      const parsed = resultsServicesUrlObject(value);
      return !!(parsed && /^https?:$/i.test(parsed.protocol) && parsed.port);
    }

    function resultsServicesFileLike(value) {
      const raw = resultsServicesText(value, 2200);
      if (!raw) return false;
      if (/\.(html?|md|markdown|png|jpe?g|webp|gif|svg|pdf|txt)(?:[?#].*)?$/i.test(raw)) return true;
      if (/^(\/|\.\/|\.\.\/|web\/|docs\/|dist\/|share\/|static_sites\/|task_dashboard\/|任务规划\/)/.test(raw)) return true;
      return false;
    }

    function resultsServicesIsHttpUrl(value) {
      return /^https?:\/\//i.test(resultsServicesText(value, 2200));
    }

    function resultsServicesDecodeFsApiPath(value) {
      const raw = resultsServicesText(value, 2200);
      if (!raw) return "";
      try {
        const parsed = new URL(raw, location.origin);
        if (parsed.pathname === "/api/fs/open" || parsed.pathname === "/api/fs/read") {
          return resultsServicesText(parsed.searchParams.get("path"), 2200);
        }
      } catch (_) {}
      return "";
    }

    function resultsServicesViewerPath(value) {
      const raw = resultsServicesText(value, 2200);
      if (!raw || resultsServicesIsHttpUrl(raw)) return "";
      const fsApiPath = resultsServicesDecodeFsApiPath(raw);
      if (fsApiPath) return fsApiPath;
      const clean = raw.replace(/[?#].*$/, "");
      if (/^\/share\//.test(clean)) return "static_sites" + clean;
      if (/^share\//.test(clean)) return "static_sites/" + clean;
      if (/^\/dist\//.test(clean)) return clean.replace(/^\/+/, "");
      if (/^\/(?:Users|Volumes|private|tmp|var|opt|Applications|Library|System)\//.test(clean)) return clean;
      if (/^(?:\.\/|\.\.\/|web\/|docs\/|dist\/|static_sites\/|task_dashboard\/|任务规划\/|产出物\/|材料\/|沉淀\/|证据\/|附件\/|图片\/|截图\/|文档\/|草稿\/|临时\/|任务\/|问题\/|反馈\/|答复\/|讨论空间\/|已完成\/|暂缓\/|归档\/)/.test(clean)) {
        return clean.replace(/^\.\//, "");
      }
      if (/^\/(?:产出物|材料|沉淀|证据|附件|图片|截图|文档|草稿|临时|任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档)\//.test(clean)) {
        return clean;
      }
      if (/\.(html?|md|markdown|png|jpe?g|webp|gif|svg|pdf|txt|json|csv|toml|ya?ml)(?::\d+(?::\d+)?)?$/i.test(clean)) {
        return clean.replace(/^\/+/, "");
      }
      return "";
    }

    function resultsServicesMessageObjectBridge() {
      if (typeof window === "undefined") return null;
      const bridge = window.__messageObjectViewer__;
      return bridge && typeof bridge.open === "function" ? bridge : null;
    }

    function resultsServicesViewerTarget(item) {
      const src = item && typeof item === "object" ? item : {};
      const raw = resultsServicesText(src.url || src.href || src.path || src.link, 2200);
      if (!raw || resultsServicesIsHttpUrl(raw)) return null;
      const bridge = resultsServicesMessageObjectBridge();
      if (bridge && typeof bridge.classify === "function") {
        const classified = bridge.classify(raw);
        if (classified && classified.defaultAction !== "open_url") {
          return Object.assign({}, classified, {
            label: resultsServicesText(src.title || classified.label || raw, 160),
          });
        }
      }
      const path = resultsServicesViewerPath(raw);
      if (!path) return null;
      return {
        kind: "fs_path",
        tone: /\.(png|jpe?g|webp|gif|svg)$/i.test(path) ? "attach" : "file",
        value: raw,
        label: resultsServicesText(src.title || resultsServicesTitleFromUrl(raw), 160),
        path,
        defaultAction: "preview_path",
      };
    }

    function resultsServicesOpenMode(item) {
      const raw = resultsServicesText(item && item.url, 2200);
      if (!raw) return { mode: "none", href: "", target: null };
      const target = resultsServicesViewerTarget(item);
      if (target && resultsServicesMessageObjectBridge()) return { mode: "viewer", href: "", target };
      return { mode: "new_tab", href: resultsServicesNewTabHref(item), target: null };
    }

    function resultsServicesShouldShowNewTabButton(mode) {
      return !!(mode && mode.mode === "viewer");
    }

    function resultsServicesNewTabHref(item) {
      const raw = resultsServicesText(item && item.url, 2200);
      if (!raw) return "";
      const fsApiPath = resultsServicesDecodeFsApiPath(raw);
      if (fsApiPath) return "/api/fs/open?path=" + encodeURIComponent(fsApiPath);
      if (resultsServicesIsHttpUrl(raw) || /^\/(?:share|\.runs)\//.test(raw)) return raw;
      return "/api/fs/open?path=" + encodeURIComponent(resultsServicesViewerPath(raw) || raw);
    }

    function resultsServicesStopEvent(event) {
      if (!event) return;
      if (typeof event.preventDefault === "function") event.preventDefault();
      if (typeof event.stopPropagation === "function") event.stopPropagation();
    }

    function resultsServicesKnownServiceUrl(url, items = RESULTS_SERVICES_STATE.items) {
      const parsed = resultsServicesUrlObject(url);
      if (!parsed) return false;
      const hostPort = parsed.host;
      return (Array.isArray(items) ? items : []).some((item) => {
        if (normalizeResultsServicesType(item && item.type) !== "service") return false;
        const itemUrl = resultsServicesUrlObject(item && item.url);
        return !!(itemUrl && itemUrl.host === hostPort);
      });
    }

    function inferResultsServicesType(value, opts = {}) {
      const raw = resultsServicesText(value, 2200);
      const status = normalizeResultsServicesStatus(opts.serviceStatus || opts.status || "");
      if (resultsServicesHasExplicitPort(raw) && status.key !== "unknown") return "service";
      if (resultsServicesHasExplicitPort(raw) && resultsServicesKnownServiceUrl(raw, opts.items || RESULTS_SERVICES_STATE.items)) return "service";
      if (resultsServicesFileLike(raw)) return "doc_page";
      return "doc_page";
    }

    function resultsServicesDefaultForm(seed = {}) {
      const src = seed && typeof seed === "object" ? seed : {};
      const url = resultsServicesText(src.url || src.href || src.path || src.link, 2200);
      const title = resultsServicesText(src.title || src.name || resultsServicesTitleFromUrl(url), 160);
      const explicitType = resultsServicesText(src.type, 80);
      const type = explicitType ? normalizeResultsServicesType(explicitType) : inferResultsServicesType(url, src);
      return {
        title,
        type,
        url,
        note: resultsServicesText(src.note || src.description, 1000),
        source: resultsServicesText(src.source || "manual", 80),
        autoType: !explicitType,
      };
    }

    async function loadResultsServicesResources(opts = {}) {
      const projectId = resultsServicesCurrentProjectId();
      if (!projectId) {
        RESULTS_SERVICES_STATE.error = "当前没有可维护的项目上下文。";
        renderResultsServicesPanel();
        return;
      }
      if (RESULTS_SERVICES_STATE.loading) return;
      if (!opts.force && RESULTS_SERVICES_STATE.loadedProjectId === projectId) {
        renderResultsServicesPanel();
        return;
      }
      const base = resultsServicesApiBase(projectId);
      RESULTS_SERVICES_STATE.loading = true;
      RESULTS_SERVICES_STATE.error = "";
      renderResultsServicesPanel();
      try {
        const payload = await resultsServicesFetchJson(base, {
          method: "GET",
          headers: resultsServicesAuthHeaders({ Accept: "application/json" }),
        });
        RESULTS_SERVICES_STATE.items = normalizeResultsServicesListPayload(payload);
        RESULTS_SERVICES_STATE.loadedProjectId = projectId;
      } catch (err) {
        RESULTS_SERVICES_STATE.error = resultsServicesText(err && err.message, 260) || "资源清单加载失败。";
      } finally {
        RESULTS_SERVICES_STATE.loading = false;
        renderResultsServicesPanel();
      }
    }

    function resultsServicesEl(tag, attrs = {}, children = []) {
      const node = document.createElement(tag);
      Object.entries(attrs || {}).forEach(([key, value]) => {
        if (value === false || value == null) return;
        if (key === "class") node.className = String(value || "");
        else if (key === "text") node.textContent = String(value == null ? "" : value);
        else if (key === "html") node.innerHTML = String(value == null ? "" : value);
        else if (key === "disabled" && value) node.disabled = true;
        else if (key === "hidden" && value) node.hidden = true;
        else node.setAttribute(key, String(value));
      });
      (Array.isArray(children) ? children : [children]).filter(Boolean).forEach((child) => node.appendChild(child));
      return node;
    }

    function ensureResultsServicesModal() {
      let mask = document.getElementById("resultsServicesMask");
      if (mask) return mask;
      mask = resultsServicesEl("div", {
        class: "bmask results-services-mask",
        id: "resultsServicesMask",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": "成果与服务清单",
      });
      mask.addEventListener("click", (event) => {
        if (event.target === mask) closeResultsServicesPanel();
      });
      document.body.appendChild(mask);
      return mask;
    }

    function resultsServicesPanelType(opts = {}) {
      return opts && opts.type
        ? normalizeResultsServicesType(opts.type)
        : RESULTS_SERVICES_DEFAULT_TYPE;
    }

    function openResultsServicesPanel(opts = {}) {
      RESULTS_SERVICES_STATE.open = true;
      RESULTS_SERVICES_STATE.notice = "";
      RESULTS_SERVICES_STATE.activeTab = resultsServicesPanelType(opts);
      ensureResultsServicesModal();
      renderResultsServicesPanel();
      void loadResultsServicesResources({ force: RESULTS_SERVICES_STATE.loadedProjectId !== resultsServicesCurrentProjectId() });
    }

    function closeResultsServicesPanel() {
      RESULTS_SERVICES_STATE.open = false;
      RESULTS_SERVICES_STATE.editorMode = "";
      RESULTS_SERVICES_STATE.editingId = "";
      RESULTS_SERVICES_STATE.form = null;
      const mask = document.getElementById("resultsServicesMask");
      if (mask) mask.classList.remove("show");
    }

    function openResultsServicesEditor(seed = {}, mode = "create") {
      const form = resultsServicesDefaultForm(seed);
      RESULTS_SERVICES_STATE.editorMode = mode;
      RESULTS_SERVICES_STATE.editingId = resultsServicesText(seed && seed.id, 120);
      RESULTS_SERVICES_STATE.form = form;
      RESULTS_SERVICES_STATE.activeTab = normalizeResultsServicesType(form.type);
      RESULTS_SERVICES_STATE.notice = "";
      RESULTS_SERVICES_STATE.error = "";
      renderResultsServicesPanel();
    }

    function openResultsServicesQuickAdd(seed = {}) {
      const nextSeed = Object.assign({}, seed || {}, { source: "message_quick_add" });
      openResultsServicesPanel({ type: inferResultsServicesType(nextSeed.url || nextSeed.path || nextSeed.href, nextSeed) });
      openResultsServicesEditor(nextSeed, "create");
    }

    function resultsServicesFormPayload() {
      const form = RESULTS_SERVICES_STATE.form || {};
      return {
        title: resultsServicesText(form.title, 160),
        type: normalizeResultsServicesType(form.type),
        url: resultsServicesText(form.url, 2200),
        note: resultsServicesText(form.note, 1000),
        source: resultsServicesText(form.source || (RESULTS_SERVICES_STATE.editorMode === "edit" ? "manual" : "manual"), 80),
      };
    }

    async function saveResultsServicesForm() {
      if (RESULTS_SERVICES_STATE.saving) return;
      const projectId = resultsServicesCurrentProjectId();
      const payload = resultsServicesFormPayload();
      if (!projectId) {
        RESULTS_SERVICES_STATE.error = "当前没有可维护的项目上下文。";
        renderResultsServicesPanel();
        return;
      }
      if (!payload.title || !payload.url) {
        RESULTS_SERVICES_STATE.error = "请补齐标题和链接。";
        renderResultsServicesPanel();
        return;
      }
      const isEdit = RESULTS_SERVICES_STATE.editorMode === "edit" && RESULTS_SERVICES_STATE.editingId;
      const url = resultsServicesApiBase(projectId) + (isEdit ? ("/" + encodeURIComponent(RESULTS_SERVICES_STATE.editingId)) : "");
      RESULTS_SERVICES_STATE.saving = true;
      RESULTS_SERVICES_STATE.error = "";
      renderResultsServicesPanel();
      try {
        await resultsServicesFetchJson(url, {
          method: isEdit ? "PATCH" : "POST",
          headers: resultsServicesAuthHeaders({ "Content-Type": "application/json", Accept: "application/json" }),
          body: JSON.stringify(payload),
        });
        RESULTS_SERVICES_STATE.notice = isEdit ? "已更新清单项。" : "已加入成果与服务清单。";
        RESULTS_SERVICES_STATE.editorMode = "";
        RESULTS_SERVICES_STATE.editingId = "";
        RESULTS_SERVICES_STATE.form = null;
        RESULTS_SERVICES_STATE.loadedProjectId = "";
        await loadResultsServicesResources({ force: true });
      } catch (err) {
        RESULTS_SERVICES_STATE.error = resultsServicesText(err && err.message, 260) || "保存失败。";
      } finally {
        RESULTS_SERVICES_STATE.saving = false;
        renderResultsServicesPanel();
      }
    }

    async function deleteResultsServicesItem(item) {
      const id = resultsServicesText(item && item.id, 120);
      const projectId = resultsServicesCurrentProjectId();
      if (!id || !projectId) return;
      const title = resultsServicesText(item && item.title, 120) || "该清单项";
      if (!window.confirm("确认从清单删除「" + title + "」？不会删除真实文件、页面或服务。")) return;
      RESULTS_SERVICES_STATE.error = "";
      try {
        await resultsServicesFetchJson(resultsServicesApiBase(projectId) + "/" + encodeURIComponent(id), {
          method: "DELETE",
          headers: resultsServicesAuthHeaders({ Accept: "application/json" }),
        });
        RESULTS_SERVICES_STATE.notice = "已删除清单项。";
        RESULTS_SERVICES_STATE.loadedProjectId = "";
        await loadResultsServicesResources({ force: true });
      } catch (err) {
        RESULTS_SERVICES_STATE.error = resultsServicesText(err && err.message, 260) || "删除失败。";
        renderResultsServicesPanel();
      }
    }

    function openResultsServicesItem(item) {
      const mode = resultsServicesOpenMode(item);
      if (mode.mode === "viewer" && mode.target) {
        const bridge = resultsServicesMessageObjectBridge();
        if (bridge) bridge.open(mode.target);
        return;
      }
      if (mode.href) window.open(mode.href, "_blank", "noopener,noreferrer");
    }

    function openResultsServicesItemNewTab(item) {
      const href = resultsServicesNewTabHref(item);
      if (href) window.open(href, "_blank", "noopener,noreferrer");
    }

    function renderResultsServicesTabs(parent) {
      const tabs = resultsServicesEl("div", { class: "results-services-tabs", role: "tablist", "aria-label": "成果与服务类型" });
      Object.entries(RESULTS_SERVICES_RESOURCE_TYPES).forEach(([type, label]) => {
        const count = RESULTS_SERVICES_STATE.items.filter((item) => normalizeResultsServicesType(item.type) === type).length;
        const btn = resultsServicesEl("button", {
          class: "results-services-tab" + (RESULTS_SERVICES_STATE.activeTab === type ? " active" : ""),
          type: "button",
          role: "tab",
          "aria-selected": RESULTS_SERVICES_STATE.activeTab === type ? "true" : "false",
          text: label + (count ? " " + count : ""),
        });
        btn.addEventListener("click", () => {
          RESULTS_SERVICES_STATE.activeTab = type;
          renderResultsServicesPanel();
        });
        tabs.appendChild(btn);
      });
      parent.appendChild(tabs);
    }

    function renderResultsServicesEditor(parent) {
      const form = RESULTS_SERVICES_STATE.form;
      if (!form) return;
      const card = resultsServicesEl("section", { class: "results-services-editor" });
      card.appendChild(resultsServicesEl("div", {
        class: "results-services-editor-title",
        text: RESULTS_SERVICES_STATE.editorMode === "edit" ? "编辑清单项" : "添加到清单",
      }));
      const grid = resultsServicesEl("div", { class: "results-services-form-grid" });
      const field = (label, control) => {
        const wrap = resultsServicesEl("label", { class: "results-services-field" });
        wrap.appendChild(resultsServicesEl("span", { text: label }));
        wrap.appendChild(control);
        return wrap;
      };
      const titleInput = resultsServicesEl("input", { class: "input", value: form.title || "", placeholder: "例如：验收报告、18765 服务" });
      titleInput.addEventListener("input", () => { form.title = titleInput.value; });
      const typeSelect = resultsServicesEl("select", { class: "input" });
      Object.entries(RESULTS_SERVICES_RESOURCE_TYPES).forEach(([type, label]) => {
        const opt = resultsServicesEl("option", { value: type, text: label });
        if (normalizeResultsServicesType(form.type) === type) opt.selected = true;
        typeSelect.appendChild(opt);
      });
      typeSelect.addEventListener("change", () => {
        form.type = normalizeResultsServicesType(typeSelect.value);
        form.autoType = false;
        RESULTS_SERVICES_STATE.activeTab = form.type;
      });
      const urlInput = resultsServicesEl("input", { class: "input", value: form.url || "", placeholder: "URL、文件路径或页面路径" });
      urlInput.addEventListener("input", () => {
        form.url = urlInput.value;
        if (form.autoType) form.type = inferResultsServicesType(form.url);
      });
      const noteInput = resultsServicesEl("textarea", { class: "input", rows: "3", placeholder: "备注，可选" });
      noteInput.value = form.note || "";
      noteInput.addEventListener("input", () => { form.note = noteInput.value; });
      grid.appendChild(field("标题", titleInput));
      grid.appendChild(field("类型", typeSelect));
      grid.appendChild(field("链接", urlInput));
      grid.appendChild(field("备注", noteInput));
      card.appendChild(grid);
      const actions = resultsServicesEl("div", { class: "results-services-editor-actions" });
      const cancelBtn = resultsServicesEl("button", { class: "btn", type: "button", text: "取消" });
      cancelBtn.addEventListener("click", () => {
        RESULTS_SERVICES_STATE.editorMode = "";
        RESULTS_SERVICES_STATE.editingId = "";
        RESULTS_SERVICES_STATE.form = null;
        RESULTS_SERVICES_STATE.error = "";
        renderResultsServicesPanel();
      });
      const saveBtn = resultsServicesEl("button", {
        class: "btn primary",
        type: "button",
        text: RESULTS_SERVICES_STATE.saving ? "保存中..." : "确认保存",
        disabled: RESULTS_SERVICES_STATE.saving,
      });
      saveBtn.addEventListener("click", () => { void saveResultsServicesForm(); });
      actions.appendChild(cancelBtn);
      actions.appendChild(saveBtn);
      card.appendChild(actions);
      parent.appendChild(card);
    }

    function renderResultsServicesList(parent) {
      const list = resultsServicesEl("div", { class: "results-services-list" });
      const rows = RESULTS_SERVICES_STATE.items
        .filter((item) => normalizeResultsServicesType(item.type) === RESULTS_SERVICES_STATE.activeTab)
        .sort((a, b) => (Number(a.sort_order || 0) - Number(b.sort_order || 0)) || String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
      if (RESULTS_SERVICES_STATE.loading && !rows.length) {
        list.appendChild(resultsServicesEl("div", { class: "results-services-empty", text: "清单加载中..." }));
      } else if (!rows.length) {
        list.appendChild(resultsServicesEl("div", {
          class: "results-services-empty",
          text: RESULTS_SERVICES_STATE.activeTab === "service" ? "暂无服务清单，可手动添加常用服务地址。" : "暂无文档/页面，可从消息正文或右上角添加。",
        }));
      }
      rows.forEach((item) => {
        const mode = resultsServicesOpenMode(item);
        const row = resultsServicesEl("article", {
          class: "results-services-item type-" + normalizeResultsServicesType(item.type) + " open-" + mode.mode,
          role: "button",
          tabindex: "0",
          "data-open-mode": mode.mode,
          title: mode.mode === "viewer" ? "点击在系统查看弹框中打开" : "点击在新标签打开",
        });
        row.addEventListener("click", () => openResultsServicesItem(item));
        row.addEventListener("keydown", (event) => {
          if (event.target && event.target.closest && event.target.closest("button, a, input, select, textarea")) return;
          if (event.key !== "Enter" && event.key !== " ") return;
          resultsServicesStopEvent(event);
          openResultsServicesItem(item);
        });
        const main = resultsServicesEl("div", { class: "results-services-item-main" });
        main.appendChild(resultsServicesEl("div", { class: "results-services-item-title", text: item.title || item.url || "未命名" }));
        main.appendChild(resultsServicesEl("div", { class: "results-services-item-url", text: item.url || "-" }));
        if (item.note) main.appendChild(resultsServicesEl("div", { class: "results-services-item-note", text: item.note }));
        row.appendChild(main);
        if (normalizeResultsServicesType(item.type) === "service") {
          const status = normalizeResultsServicesStatus(item.service_status);
          row.appendChild(resultsServicesEl("span", {
            class: "results-services-status is-" + status.key,
            title: "服务状态：" + status.label,
            text: status.label,
          }));
        }
        const actions = resultsServicesEl("div", { class: "results-services-item-actions" });
        if (resultsServicesShouldShowNewTabButton(mode)) {
          const openBtn = resultsServicesEl("button", { class: "btn textbtn", type: "button", text: "新窗口打开" });
          openBtn.addEventListener("click", (event) => {
            resultsServicesStopEvent(event);
            openResultsServicesItemNewTab(item);
          });
          actions.appendChild(openBtn);
        }
        const editBtn = resultsServicesEl("button", { class: "btn textbtn", type: "button", text: "编辑" });
        editBtn.addEventListener("click", (event) => {
          resultsServicesStopEvent(event);
          openResultsServicesEditor(item, "edit");
        });
        const deleteBtn = resultsServicesEl("button", { class: "btn textbtn danger", type: "button", text: "删除" });
        deleteBtn.addEventListener("click", (event) => {
          resultsServicesStopEvent(event);
          void deleteResultsServicesItem(item);
        });
        actions.appendChild(editBtn);
        actions.appendChild(deleteBtn);
        row.appendChild(actions);
        list.appendChild(row);
      });
      parent.appendChild(list);
    }

    function renderResultsServicesPanel() {
      const mask = document.getElementById("resultsServicesMask");
      if (!mask) return;
      mask.innerHTML = "";
      mask.classList.toggle("show", !!RESULTS_SERVICES_STATE.open);
      if (!RESULTS_SERVICES_STATE.open) return;
      const modal = resultsServicesEl("div", { class: "bmodal results-services-modal", role: "document" });
      const head = resultsServicesEl("div", { class: "results-services-head" });
      const titleWrap = resultsServicesEl("div", { class: "results-services-titlewrap" });
      titleWrap.appendChild(resultsServicesEl("div", { class: "results-services-kicker", text: "Project Resources" }));
      titleWrap.appendChild(resultsServicesEl("div", { class: "results-services-title", text: "成果与服务" }));
      titleWrap.appendChild(resultsServicesEl("div", { class: "results-services-sub", text: "手动维护重要文档、页面与常用服务入口；服务状态只读展示。" }));
      head.appendChild(titleWrap);
      const headActions = resultsServicesEl("div", { class: "results-services-head-actions" });
      const addBtn = resultsServicesEl("button", { class: "btn primary", type: "button", text: "+ 添加" });
      addBtn.addEventListener("click", () => openResultsServicesEditor({ type: RESULTS_SERVICES_STATE.activeTab, source: "manual" }, "create"));
      const closeBtn = resultsServicesEl("button", { class: "btn", type: "button", text: "关闭" });
      closeBtn.addEventListener("click", closeResultsServicesPanel);
      headActions.appendChild(addBtn);
      headActions.appendChild(closeBtn);
      head.appendChild(headActions);
      modal.appendChild(head);
      const body = resultsServicesEl("div", { class: "results-services-body" });
      renderResultsServicesTabs(body);
      if (RESULTS_SERVICES_STATE.notice) {
        body.appendChild(resultsServicesEl("div", { class: "results-services-notice", text: RESULTS_SERVICES_STATE.notice }));
      }
      if (RESULTS_SERVICES_STATE.error) {
        body.appendChild(resultsServicesEl("div", { class: "results-services-error", text: RESULTS_SERVICES_STATE.error }));
      }
      renderResultsServicesEditor(body);
      renderResultsServicesList(body);
      modal.appendChild(body);
      const foot = resultsServicesEl("div", { class: "results-services-foot" });
      foot.appendChild(resultsServicesEl("span", { text: "删除仅移出清单，不影响真实文件、页面或服务。" }));
      const refreshBtn = resultsServicesEl("button", { class: "btn textbtn", type: "button", text: "刷新清单" });
      refreshBtn.addEventListener("click", () => { void loadResultsServicesResources({ force: true }); });
      foot.appendChild(refreshBtn);
      modal.appendChild(foot);
      mask.appendChild(modal);
    }

    function initResultsServicesEntry() {
      const systemWrap = document.getElementById("systemSettingsWrap");
      const host = systemWrap && systemWrap.parentNode;
      let wrap = document.getElementById("resultsServicesEntryWrap");
      let trigger = document.getElementById("resultsServicesTrigger");
      if (!wrap && host && systemWrap) {
        wrap = resultsServicesEl("div", { class: "results-services-entry-wrap", id: "resultsServicesEntryWrap" });
        trigger = resultsServicesEl("button", {
          class: "results-services-entry-btn",
          id: "resultsServicesTrigger",
          type: "button",
          title: "打开成果与服务清单",
          html: "<span class=\"results-services-entry-icon\" aria-hidden=\"true\">+</span><span>成果与服务</span>",
        });
        wrap.appendChild(trigger);
        host.insertBefore(wrap, systemWrap);
      }
      if (!trigger || trigger.__resultsServicesBound) return;
      trigger.__resultsServicesBound = true;
      trigger.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openResultsServicesPanel();
      });
    }

    function resultsServicesQuickAddTargetFromNode(node) {
      if (!node) return null;
      const obj = node.__messageObject && typeof node.__messageObject === "object" ? node.__messageObject : {};
      const href = resultsServicesText(
        obj.path || obj.value || obj.openUrl || node.getAttribute && (node.getAttribute("href") || node.getAttribute("data-msg-object-href")),
        2200
      );
      if (!href) return null;
      const title = resultsServicesText(obj.label || obj.title || node.textContent || resultsServicesTitleFromUrl(href), 160);
      const type = inferResultsServicesType(href);
      return { title: title || resultsServicesTitleFromUrl(href), url: href, type, source: "message_quick_add" };
    }

    function createResultsServicesQuickAddButton(seed) {
      const wrap = resultsServicesEl("span", { class: "results-services-quickadd-wrap" });
      const btn = resultsServicesEl("button", { class: "results-services-quickadd-btn", type: "button", text: "+加入清单", title: "加入成果与服务清单" });
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        void openResultsServicesQuickAdd(seed);
      });
      wrap.appendChild(btn);
      return wrap;
    }

    function enhanceResultsServicesQuickAdd(root) {
      if (!root || !root.querySelectorAll || root.__resultsServicesQuickAddEnhanced) return;
      root.__resultsServicesQuickAddEnhanced = true;
      const nodes = Array.from(root.querySelectorAll(".msg-object-link, .msg-object-code-target"));
      nodes.forEach((node) => {
        if (!node || node.__resultsServicesQuickAddBound) return;
        if (node.closest && node.closest(".results-services-mask, .msgobj-viewer-mask, .results-services-quickadd-wrap")) return;
        const seed = resultsServicesQuickAddTargetFromNode(node);
        if (!seed || !seed.url) return;
        node.__resultsServicesQuickAddBound = true;
        const btn = createResultsServicesQuickAddButton(seed);
        if (node.parentNode) node.parentNode.insertBefore(btn, node.nextSibling);
      });
    }

    function installResultsServicesMessageObjectHook() {
      if (typeof enhanceMessageInteractiveObjects !== "function") return false;
      if (enhanceMessageInteractiveObjects.__resultsServicesWrapped) return true;
      const original = enhanceMessageInteractiveObjects;
      const wrapped = function resultsServicesWrappedEnhanceMessageInteractiveObjects(root, opts = {}) {
        const result = original.apply(this, arguments);
        try { enhanceResultsServicesQuickAdd(root, opts); } catch (_) {}
        return result;
      };
      wrapped.__resultsServicesWrapped = true;
      wrapped.__resultsServicesOriginal = original;
      enhanceMessageInteractiveObjects = wrapped;
      return true;
    }

    function initResultsServicesPanelV1() {
      initResultsServicesEntry();
      installResultsServicesMessageObjectHook();
      if (!document.__resultsServicesEscBound) {
        document.__resultsServicesEscBound = true;
        document.addEventListener("keydown", (event) => {
          if (event.key === "Escape" && RESULTS_SERVICES_STATE.open) closeResultsServicesPanel();
        });
      }
    }

    if (typeof window !== "undefined") {
      window.__resultsServicesPanelV1__ = {
        state: RESULTS_SERVICES_STATE,
        defaultType: RESULTS_SERVICES_DEFAULT_TYPE,
        resourceTypes: RESULTS_SERVICES_RESOURCE_TYPES,
        panelType: resultsServicesPanelType,
        normalizeType: normalizeResultsServicesType,
        normalizeStatus: normalizeResultsServicesStatus,
        inferType: inferResultsServicesType,
        normalizeItem: normalizeResultsServicesItem,
        normalizeListPayload: normalizeResultsServicesListPayload,
        apiBase: resultsServicesApiBase,
        openModeForItem: resultsServicesOpenMode,
        viewerTargetForItem: resultsServicesViewerTarget,
        newTabHrefForItem: resultsServicesNewTabHref,
        shouldShowNewTabButton: resultsServicesShouldShowNewTabButton,
        quickAddTargetFromNode: resultsServicesQuickAddTargetFromNode,
        enhanceQuickAdd: enhanceResultsServicesQuickAdd,
      };
    }

    if (typeof document !== "undefined") {
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initResultsServicesPanelV1);
      } else {
        initResultsServicesPanelV1();
      }
    }
