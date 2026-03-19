    function normalizeTaskPlanItem(raw) {
      const p = (raw && typeof raw === "object") ? raw : {};
      const batchesRaw = Array.isArray(p.batches) ? p.batches : [];
      const batches = batchesRaw.map(normalizeTaskPlanBatch)
        .sort((a, b) => Number(a.order_index || 0) - Number(b.order_index || 0));
      return {
        plan_id: String(p.plan_id || p.planId || "").trim(),
        project_id: String(p.project_id || p.projectId || "").trim(),
        name: String(p.name || "").trim(),
        enabled: _coerceBoolClient(p.enabled, false),
        activation_mode: String(p.activation_mode || p.activationMode || "manual").trim().toLowerCase() || "manual",
        auto_dispatch_enabled: ("auto_dispatch_enabled" in p)
          ? _coerceBoolClient(p.auto_dispatch_enabled, false)
          : _coerceBoolClient(p.autoDispatchEnabled, false),
        auto_inspection_enabled: ("auto_inspection_enabled" in p)
          ? _coerceBoolClient(p.auto_inspection_enabled, false)
          : _coerceBoolClient(p.autoInspectionEnabled, false),
        updated_at: String(p.updated_at || p.updatedAt || "").trim(),
        created_at: String(p.created_at || p.createdAt || "").trim(),
        batches,
      };
    }

    async function fetchTaskPlans(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      const force = !!opts.force;
      const maxAgeMs = Number(opts.maxAgeMs || 0);
      const cached = TASK_PLAN_UI.cacheByProject[pid];
      if (!force && cached && maxAgeMs > 0) {
        const age = Date.now() - Number(cached.fetchedAtMs || 0);
        if (age >= 0 && age < maxAgeMs) return cached.items || [];
      }
      if (TASK_PLAN_UI.loadingByProject[pid]) return (cached && cached.items) || [];
      TASK_PLAN_UI.loadingByProject[pid] = true;
      TASK_PLAN_UI.errorByProject[pid] = "";
      const seq = Number(TASK_PLAN_UI.seqByProject[pid] || 0) + 1;
      TASK_PLAN_UI.seqByProject[pid] = seq;
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/task-plans?limit=50", {
          headers: authHeaders({}),
          cache: "no-store",
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        const items = (Array.isArray(data && data.items) ? data.items : [])
          .map(normalizeTaskPlanItem);
        if (Number(TASK_PLAN_UI.seqByProject[pid] || 0) === seq) {
          TASK_PLAN_UI.cacheByProject[pid] = {
            items,
            fetchedAt: new Date().toISOString(),
            fetchedAtMs: Date.now(),
          };
        }
        return items;
      } catch (e) {
        if (Number(TASK_PLAN_UI.seqByProject[pid] || 0) === seq) {
          TASK_PLAN_UI.errorByProject[pid] = e && e.message ? String(e.message) : "网络或服务异常";
        }
        return (cached && cached.items) || [];
      } finally {
        if (Number(TASK_PLAN_UI.seqByProject[pid] || 0) === seq) {
          TASK_PLAN_UI.loadingByProject[pid] = false;
        }
      }
    }

    function taskPlanTaskBucket(task) {
      const t = task || {};
      const st = String(t.status || "").trim().toLowerCase();
      const ds = String(t.dispatch_state || "").trim().toLowerCase();
      const hasErr = !!String(t.last_error || "").trim();
      if (st === "done") return "done";
      if (st === "error" || st === "skipped" || hasErr) return "blocked";
      if (st === "running" || st === "queued" || st === "active") return "running";
      if (st === "planned" || st === "paused") return "pending";
      if (ds === "dispatched") return "running";
      if (ds.includes("block") || ds.includes("error") || ds.includes("fail")) return "blocked";
      return "pending";
    }

    function taskPlanTaskTone(task) {
      const b = taskPlanTaskBucket(task);
      if (b === "done") return "good";
      if (b === "blocked") return "bad";
      if (b === "running") return "warn";
      return "muted";
    }

    function taskPlanTaskLabel(task) {
      const st = String((task && task.status) || "").trim().toLowerCase();
      const ds = String((task && task.dispatch_state) || "").trim().toLowerCase();
      if (st === "done") return "已完成";
      if (st === "running") return "执行中";
      if (st === "queued") return "排队中";
      if (st === "planned") return "待处理";
      if (st === "paused") return "已暂停";
      if (st === "error") return "异常";
      if (st === "skipped") return "已跳过";
      if (ds === "dispatched") return "已派发";
      if (ds && ds !== "none") return ds;
      return st || "待处理";
    }

    function taskPlanBatchLabel(batch) {
      const st = String((batch && batch.status) || "").trim().toLowerCase();
      const map = {
        planned: "待开始",
        active: "进行中",
        paused: "已暂停",
        done: "已完成",
        blocked: "阻塞",
      };
      return map[st] || st || "待开始";
    }

    function taskPlanFindGroupForTask(it) {
      if (!it || !isTaskItem(it)) return null;
      const pid = String((it.project_id || STATE.project) || "").trim();
      const p = String(it.path || "").trim();
      if (!pid || !p) return null;
      const groups = buildTaskGroups(pid);
      for (const g of groups) {
        const masterPath = String((g.master && g.master.path) || "").trim();
        if (masterPath && masterPath === p) return g;
        const hit = (Array.isArray(g.children) ? g.children : []).some((c) => String((c && c.path) || "").trim() === p);
        if (hit) return g;
      }
      return null;
    }

    function taskPlanScopeForTask(it) {
      const group = taskPlanFindGroupForTask(it);
      if (!group) {
        const path = String((it && it.path) || "").trim();
        return {
          masterPath: path,
          allPaths: new Set(path ? [path] : []),
          childPaths: new Set(),
          hasGroup: false,
        };
      }
      const masterPath = String((group.master && group.master.path) || "").trim();
      const allPaths = new Set();
      if (masterPath) allPaths.add(masterPath);
      const childPaths = new Set();
      for (const c of (Array.isArray(group.children) ? group.children : [])) {
        const cp = String((c && c.path) || "").trim();
        if (!cp) continue;
        allPaths.add(cp);
        childPaths.add(cp);
      }
      return { masterPath, allPaths, childPaths, hasGroup: true };
    }

    function taskPlanRelatedTasks(plan, scopeSet) {
      const set = scopeSet instanceof Set ? scopeSet : new Set();
      const out = [];
      const batches = Array.isArray(plan && plan.batches) ? plan.batches : [];
      for (const b of batches) {
        for (const t of (Array.isArray(b.tasks) ? b.tasks : [])) {
          if (!set.size || set.has(String(t.task_path || "").trim())) out.push(t);
        }
      }
      return out;
    }

    function taskPlanStats(tasks, scope) {
      const arr = Array.isArray(tasks) ? tasks : [];
      let running = 0;
      let pending = 0;
      let done = 0;
      let blocked = 0;
      let drift = 0;
      let childTotal = 0;
      let childRunning = 0;
      let childPending = 0;
      let childDone = 0;
      let childBlocked = 0;
      const masterPath = String((scope && scope.masterPath) || "").trim();
      for (const t of arr) {
        const bucket = taskPlanTaskBucket(t);
        if (bucket === "running") running += 1;
        else if (bucket === "done") done += 1;
        else if (bucket === "blocked") blocked += 1;
        else pending += 1;
        if (bucket === "blocked" || String((t && t.dispatch_state) || "").toLowerCase().includes("drift")) drift += 1;
        const tp = String((t && t.task_path) || "").trim();
        const isChild = tp && masterPath && tp !== masterPath;
        if (!masterPath || isChild) {
          childTotal += 1;
          if (bucket === "running") childRunning += 1;
          else if (bucket === "done") childDone += 1;
          else if (bucket === "blocked") childBlocked += 1;
          else childPending += 1;
        }
      }
      return {
        total: arr.length,
        running,
        pending,
        done,
        blocked,
        drift,
        childTotal,
        childRunning,
        childPending,
        childDone,
        childBlocked,
      };
    }

    function taskPlanFilterModeByTask(it) {
      const key = taskPushTaskKey(it);
      const m = String(TASK_PLAN_UI.filterByTask[key] || "active_pending").trim().toLowerCase();
      if (["active_pending", "all", "done", "blocked"].includes(m)) return m;
      return "active_pending";
    }

    function taskPlanMatchFilter(task, mode) {
      const m = String(mode || "active_pending").trim().toLowerCase();
      const b = taskPlanTaskBucket(task);
      if (m === "all") return true;
      if (m === "done") return b === "done";
      if (m === "blocked") return b === "blocked";
      return b === "running" || b === "pending";
    }

    function taskPlanDefaultDraft(it) {
      const now = new Date();
      const y = String(now.getFullYear());
      const m = String(now.getMonth() + 1).padStart(2, "0");
      const d = String(now.getDate()).padStart(2, "0");
      const planId = "tp_" + y + m + d + "_draft";
      const item = it || {};
      const taskPath = String(item.path || "").trim();
      const scope = taskPlanScopeForTask(it);
      const childPaths = Array.from(scope.childPaths || []);
      const taskRows = [];
      if (taskPath) {
        taskRows.push({
          task_path: taskPath,
          task_role: "master",
          dispatch_mode: "immediate",
          retry_max_attempts: 2,
          retry_interval_seconds: 60,
          writeback_enabled: true,
          callback_to: "主体-总控（合并与验收）",
          status: "planned",
        });
      }
      childPaths.slice(0, 8).forEach((cp) => {
        taskRows.push({
          task_path: cp,
          task_role: "child",
          dispatch_mode: "immediate",
          retry_max_attempts: 2,
          retry_interval_seconds: 60,
          writeback_enabled: true,
          callback_to: "主体-总控（合并与验收）",
          status: "planned",
        });
      });
      const payload = {
        plan_id: planId,
        name: shortTitle(item.title || "计划草稿"),
        enabled: true,
        activation_mode: "manual",
        auto_dispatch_enabled: false,
        auto_inspection_enabled: true,
        batches: [
          {
            batch_id: "b01",
            order_index: 1,
            name: "默认批次",
            status: "planned",
            activate_when: "manual",
            tasks: taskRows.length ? taskRows : [{
              task_path: taskPath || "任务规划/xxx.md",
              task_role: "single",
              dispatch_mode: "immediate",
              retry_max_attempts: 2,
              retry_interval_seconds: 60,
              writeback_enabled: true,
              callback_to: "主体-总控（合并与验收）",
              status: "planned",
            }],
          },
        ],
      };
      return JSON.stringify(payload, null, 2);
    }

    function taskPlanResolveSelectedPlan(it, plans, scope) {
      const arr = Array.isArray(plans) ? plans : [];
      if (!arr.length) return null;
      const key = taskPushTaskKey(it);
      const picked = String(TASK_PLAN_UI.selectedPlanByTask[key] || "").trim();
      let plan = picked ? arr.find((x) => String(x.plan_id || "") === picked) : null;
      if (plan) return plan;
      const set = scope && scope.allPaths ? scope.allPaths : new Set();
      plan = arr.find((x) => taskPlanRelatedTasks(x, set).length > 0);
      if (plan) {
        TASK_PLAN_UI.selectedPlanByTask[key] = String(plan.plan_id || "");
        return plan;
      }
      plan = arr[0];
      TASK_PLAN_UI.selectedPlanByTask[key] = String(plan.plan_id || "");
      return plan;
    }

    function taskPlanResolveSelectedBatchId(it, plan) {
      const key = taskPushTaskKey(it);
      const picked = String(TASK_PLAN_UI.selectedBatchByTask[key] || "").trim();
      const batches = Array.isArray(plan && plan.batches) ? plan.batches : [];
      if (!batches.length) return "";
      if (picked && batches.some((b) => String(b.batch_id || "") === picked)) return picked;
      const preferred = batches.find((b) => ["active", "planned", "blocked"].includes(String(b.status || "").toLowerCase())) || batches[0];
      const next = String((preferred && preferred.batch_id) || "");
      TASK_PLAN_UI.selectedBatchByTask[key] = next;
      return next;
    }

    async function taskPlanSaveDraft(it, draftText) {
      const item = it || {};
      const projectId = String((item.project_id || STATE.project) || "").trim();
      if (!projectId || projectId === "overview") throw new Error("项目不可用");
      let body = {};
      try {
        body = JSON.parse(String(draftText || "{}"));
      } catch (e) {
        throw new Error("JSON 格式错误：" + String((e && e.message) || e || "未知错误"));
      }
      if (!body || typeof body !== "object") throw new Error("JSON 必须是对象");
      const resp = await fetch("/api/projects/" + encodeURIComponent(projectId) + "/task-plans", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        const tok = getToken();
        if ((resp.status === 401 || resp.status === 403) && !tok) {
          throw new Error("服务启用了 Token 校验，请先设置 Token");
        }
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return await resp.json().catch(() => ({}));
    }

    async function taskPlanActivateBatch(it, planId, batchId) {
      const item = it || {};
      const projectId = String((item.project_id || STATE.project) || "").trim();
      const pid = String(planId || "").trim();
      const bid = String(batchId || "").trim();
      if (!projectId || !pid) throw new Error("计划信息不完整");
      const resp = await fetch(
        "/api/projects/" + encodeURIComponent(projectId) + "/task-plans/" + encodeURIComponent(pid) + "/activate",
        {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ batch_id: bid, dry_run: false }),
        }
      );
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        const tok = getToken();
        if ((resp.status === 401 || resp.status === 403) && !tok) {
          throw new Error("服务启用了 Token 校验，请先设置 Token");
        }
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return await resp.json().catch(() => ({}));
    }

    function renderTaskPlanCard(it, opts = {}) {
      if (!it || !isTaskItem(it)) return null;
      if (!opts.force && (STATE.panelMode === "conv" || STATE.selectedSessionId)) return null;
      const projectId = String((it.project_id || STATE.project) || "").trim();
      if (!projectId || projectId === "overview") return null;

      const taskKey = taskPushTaskKey(it);
      const cache = TASK_PLAN_UI.cacheByProject[projectId];
      const plans = Array.isArray(cache && cache.items) ? cache.items : [];
      const loading = !!TASK_PLAN_UI.loadingByProject[projectId];
      const err = String(TASK_PLAN_UI.errorByProject[projectId] || "").trim();
      const note = String(TASK_PLAN_UI.noteByTask[taskKey] || "").trim();
      const actionBusy = String(TASK_PLAN_UI.actionByTask[taskKey] || "").trim();
      const draft = String(TASK_PLAN_UI.draftByTask[taskKey] || "").trim();
      const editorOpen = !!TASK_PLAN_UI.editorOpenByTask[taskKey];
      const filterMode = taskPlanFilterModeByTask(it);

      const scope = taskPlanScopeForTask(it);
      const selectedPlan = taskPlanResolveSelectedPlan(it, plans, scope);
      const selectedBatchId = taskPlanResolveSelectedBatchId(it, selectedPlan);
      const selectedPlanId = String((selectedPlan && selectedPlan.plan_id) || "");
      const relatedTasks = taskPlanRelatedTasks(selectedPlan, scope.allPaths);
      const statsSource = relatedTasks.length ? relatedTasks : taskPlanRelatedTasks(selectedPlan, new Set());
      const stats = taskPlanStats(statsSource, scope);
      const planBatches = Array.isArray(selectedPlan && selectedPlan.batches) ? selectedPlan.batches : [];

      const card = el("section", { class: "task-plan-card" });
      const head = el("div", { class: "task-plan-head" });
      const titleWrap = el("div", { class: "task-plan-titlewrap" });
      titleWrap.appendChild(el("div", { class: "task-plan-kicker", text: "计划表管理" }));
      titleWrap.appendChild(el("div", { class: "task-plan-title", text: "批次排期与任务联动（V1）" }));
      const subText = scope.hasGroup
        ? ("当前任务组：" + shortTitle((it && it.title) || "") + " · 跟踪路径 " + scope.allPaths.size + " 条")
        : ("当前任务：" + shortTitle((it && it.title) || ""));
      titleWrap.appendChild(el("div", { class: "task-plan-sub", text: subText }));
      head.appendChild(titleWrap);
      const headOps = el("div", { class: "task-plan-head-ops" });
      const refreshBtn = el("button", { class: "btn", text: loading ? "刷新中..." : "刷新计划" });
      refreshBtn.disabled = loading || !!actionBusy;
      refreshBtn.addEventListener("click", async () => {
        TASK_PLAN_UI.noteByTask[taskKey] = "正在刷新计划表…";
        maybeRerenderTaskDetail(it);
        await fetchTaskPlans(projectId, { force: true });
        maybeRerenderTaskDetail(it);
      });
      headOps.appendChild(refreshBtn);
      const openPushBtn = el("button", { class: "btn", text: "协作派发" });
      openPushBtn.addEventListener("click", () => openTaskPushModalByItem(it));
      headOps.appendChild(openPushBtn);
      head.appendChild(headOps);
      card.appendChild(head);

      if (err) card.appendChild(el("div", { class: "task-plan-error", text: "计划表查询失败：" + err }));
      if (note) card.appendChild(el("div", { class: "task-plan-note" + (note.includes("失败") ? " error" : ""), text: note }));

      const toolbar = el("div", { class: "task-plan-toolbar" });
      const planSelect = el("select", { class: "task-plan-select", title: "选择计划表" });
      if (!plans.length) {
        planSelect.appendChild(el("option", { value: "", text: "暂无计划表" }));
        planSelect.disabled = true;
      } else {
        for (const p of plans) {
          const label = shortTitle(p.name || p.plan_id || "未命名计划");
          const opt = el("option", { value: String(p.plan_id || ""), text: (p.enabled ? "● " : "○ ") + label });
          if (String(p.plan_id || "") === selectedPlanId) opt.selected = true;
          planSelect.appendChild(opt);
        }
      }
      planSelect.addEventListener("change", () => {
        TASK_PLAN_UI.selectedPlanByTask[taskKey] = String(planSelect.value || "");
        TASK_PLAN_UI.selectedBatchByTask[taskKey] = "";
        maybeRerenderTaskDetail(it);
      });
      toolbar.appendChild(planSelect);

      const batchSelect = el("select", { class: "task-plan-select", title: "选择批次" });
      if (!planBatches.length) {
        batchSelect.appendChild(el("option", { value: "", text: "无批次" }));
        batchSelect.disabled = true;
      } else {
        for (const b of planBatches) {
          const bid = String(b.batch_id || "");
          const label = bid + (b.name ? (" · " + shortTitle(b.name)) : "");
          const opt = el("option", { value: bid, text: label });
          if (bid === selectedBatchId) opt.selected = true;
          batchSelect.appendChild(opt);
        }
      }
      batchSelect.addEventListener("change", () => {
        TASK_PLAN_UI.selectedBatchByTask[taskKey] = String(batchSelect.value || "");
      });
      toolbar.appendChild(batchSelect);

      const filterSelect = el("select", { class: "task-plan-select", title: "筛选任务" });
      const filterOptions = [
        { value: "active_pending", label: "进行中+待处理" },
        { value: "blocked", label: "仅阻塞/异常" },
        { value: "done", label: "仅已完成" },
        { value: "all", label: "全部" },
      ];
      filterOptions.forEach((x) => {
        const opt = el("option", { value: x.value, text: x.label });
        if (x.value === filterMode) opt.selected = true;
        filterSelect.appendChild(opt);
      });
      filterSelect.addEventListener("change", () => {
        TASK_PLAN_UI.filterByTask[taskKey] = String(filterSelect.value || "active_pending");
        maybeRerenderTaskDetail(it);
      });
      toolbar.appendChild(filterSelect);

      const activateBtn = el("button", { class: "btn primary", text: actionBusy === "activate" ? "激活中..." : "激活批次" });
      activateBtn.disabled = !selectedPlanId || !selectedBatchId || !!actionBusy;
      activateBtn.addEventListener("click", async () => {
        if (activateBtn.disabled) return;
        TASK_PLAN_UI.actionByTask[taskKey] = "activate";
        TASK_PLAN_UI.noteByTask[taskKey] = "正在激活批次…";
        maybeRerenderTaskDetail(it);
        try {
          const result = await taskPlanActivateBatch(it, selectedPlanId, selectedBatchId);
          const n = Number(result && result.activated_count || 0);
          TASK_PLAN_UI.noteByTask[taskKey] = "批次已激活，本次触发 " + n + " 项。";
          await fetchTaskPlans(projectId, { force: true });
        } catch (e) {
          TASK_PLAN_UI.noteByTask[taskKey] = "激活失败：" + String((e && e.message) || e || "未知错误");
        } finally {
          delete TASK_PLAN_UI.actionByTask[taskKey];
          maybeRerenderTaskDetail(it);
        }
      });
      toolbar.appendChild(activateBtn);
      card.appendChild(toolbar);

      const summary = el("div", { class: "task-plan-summary" });
      summary.appendChild(chip("计划项:" + Number(stats.total || 0), "muted"));
      summary.appendChild(chip("进行中:" + Number(stats.running || 0), Number(stats.running || 0) ? "warn" : "muted"));
      summary.appendChild(chip("待处理:" + Number(stats.pending || 0), Number(stats.pending || 0) ? "muted" : "muted"));
      summary.appendChild(chip("已完成:" + Number(stats.done || 0), Number(stats.done || 0) ? "good" : "muted"));
      summary.appendChild(chip("阻塞:" + Number(stats.blocked || 0), Number(stats.blocked || 0) ? "bad" : "muted"));
      summary.appendChild(chip("偏差:" + Number(stats.drift || 0), Number(stats.drift || 0) ? "bad" : "muted"));
      card.appendChild(summary);

      const subSummary = el("div", { class: "task-plan-subsummary" });
      subSummary.appendChild(el("span", {
        text: "子任务统计：总 " + Number(stats.childTotal || 0)
          + " · 进行中 " + Number(stats.childRunning || 0)
          + " · 待处理 " + Number(stats.childPending || 0)
          + " · 已完成 " + Number(stats.childDone || 0)
          + " · 阻塞 " + Number(stats.childBlocked || 0),
      }));
      card.appendChild(subSummary);

      const listWrap = el("div", { class: "task-plan-batches" });
      if (!selectedPlan) {
        listWrap.appendChild(el("div", { class: "task-plan-empty", text: loading ? "计划表加载中..." : "当前项目暂无计划表，可点击“新建草稿”后保存。" }));
      } else {
        for (const batch of planBatches) {
          const batchCard = el("div", { class: "task-plan-batch" + (String(batch.batch_id || "") === selectedBatchId ? " active" : "") });
          const batchHead = el("div", { class: "task-plan-batch-head" });
          const titleLeft = el("div", { class: "task-plan-batch-title" });
          titleLeft.appendChild(el("strong", { text: String(batch.batch_id || "-") }));
          if (batch.name) titleLeft.appendChild(el("span", { text: " · " + shortTitle(batch.name) }));
          batchHead.appendChild(titleLeft);
          const headMeta = el("div", { class: "task-plan-batch-meta" });
          headMeta.appendChild(chip(taskPlanBatchLabel(batch), taskPlanTaskTone({ status: batch.status })));
          if (batch.planned_start_at) headMeta.appendChild(chip("开始 " + formatTsOrDash(batch.planned_start_at), "muted"));
          if (batch.planned_end_at) headMeta.appendChild(chip("截止 " + formatTsOrDash(batch.planned_end_at), "muted"));
          if (batch.activate_when) headMeta.appendChild(chip("触发 " + batch.activate_when, "muted"));
          batchHead.appendChild(headMeta);
          batchCard.appendChild(batchHead);

          const tasks = (Array.isArray(batch.tasks) ? batch.tasks : [])
            .filter((t) => {
              const inScope = !scope.allPaths.size || scope.allPaths.has(String(t.task_path || "").trim());
              return inScope && taskPlanMatchFilter(t, filterMode);
            });
          if (!tasks.length) {
            batchCard.appendChild(el("div", { class: "task-plan-empty small", text: "当前筛选下无计划项。" }));
          } else {
            const taskList = el("div", { class: "task-plan-tasklist" });
            for (const t of tasks) {
              const taskPath = String(t.task_path || "").trim();
              const taskRow = el("div", { class: "task-plan-task" + (taskPath === String(it.path || "") ? " is-current" : "") });
              const left = el("div", { class: "task-plan-task-main" });
              left.appendChild(el("div", { class: "task-plan-task-title", text: shortTitle(taskPath || "(空路径)") }));
              const meta = el("div", { class: "task-plan-task-meta" });
              meta.appendChild(chip(taskPlanTaskLabel(t), taskPlanTaskTone(t)));
              if (t.dispatch_state) meta.appendChild(chip("派发:" + t.dispatch_state, "muted"));
              if (t.job_id) meta.appendChild(chip("job:" + shortId(t.job_id), "muted"));
              if (t.run_id) meta.appendChild(chip("run:" + shortId(t.run_id), "muted"));
              if (t.scheduled_at) meta.appendChild(chip("计划 " + formatTsOrDash(t.scheduled_at), "muted"));
              if (t.depends_on && t.depends_on.length) meta.appendChild(chip("依赖:" + t.depends_on.length, "warn"));
              left.appendChild(meta);
              taskRow.appendChild(left);

              const rowOps = el("div", { class: "task-plan-task-ops" });
              const targetItem = findItemByPath(taskPath);
              if (targetItem && isTaskItem(targetItem)) {
                const jumpBtn = el("button", { class: "btn", text: "查看" });
                jumpBtn.addEventListener("click", (e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setSelectedPath(taskPath);
                });
                rowOps.appendChild(jumpBtn);
                const pushBtn = el("button", { class: "btn", text: "推动此项" });
                pushBtn.addEventListener("click", (e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  openTaskPushModalByItem(targetItem);
                });
                rowOps.appendChild(pushBtn);
              }
              taskRow.appendChild(rowOps);
              taskList.appendChild(taskRow);
            }
            batchCard.appendChild(taskList);
          }
          listWrap.appendChild(batchCard);
        }
      }
      card.appendChild(listWrap);

      const editorWrap = el("div", { class: "task-plan-editor" + (editorOpen ? " show" : "") });
      const editorOps = el("div", { class: "task-plan-editor-ops" });
      const draftBtn = el("button", { class: "btn", text: "新建草稿" });
      draftBtn.disabled = !!actionBusy;
      draftBtn.addEventListener("click", () => {
        TASK_PLAN_UI.editorOpenByTask[taskKey] = true;
        TASK_PLAN_UI.draftByTask[taskKey] = taskPlanDefaultDraft(it);
        TASK_PLAN_UI.noteByTask[taskKey] = "已生成草稿，可直接保存或调整后保存。";
        maybeRerenderTaskDetail(it);
      });
      editorOps.appendChild(draftBtn);

      const editBtn = el("button", { class: "btn", text: "编辑当前" });
      editBtn.disabled = !selectedPlan || !!actionBusy;
      editBtn.addEventListener("click", () => {
        TASK_PLAN_UI.editorOpenByTask[taskKey] = true;
        TASK_PLAN_UI.draftByTask[taskKey] = JSON.stringify(selectedPlan || {}, null, 2);
        TASK_PLAN_UI.noteByTask[taskKey] = "已加载当前计划，可修改后保存。";
        maybeRerenderTaskDetail(it);
      });
      editorOps.appendChild(editBtn);

      const saveBtn = el("button", { class: "btn primary", text: actionBusy === "save" ? "保存中..." : "保存计划" });
      saveBtn.disabled = !editorOpen || !draft || !!actionBusy;
      saveBtn.addEventListener("click", async () => {
        if (saveBtn.disabled) return;
        TASK_PLAN_UI.actionByTask[taskKey] = "save";
        TASK_PLAN_UI.noteByTask[taskKey] = "正在保存计划…";
        maybeRerenderTaskDetail(it);
        try {
          const data = await taskPlanSaveDraft(it, draft);
          const savedPlanId = String((data && data.item && data.item.plan_id) || "").trim();
          if (savedPlanId) TASK_PLAN_UI.selectedPlanByTask[taskKey] = savedPlanId;
          TASK_PLAN_UI.noteByTask[taskKey] = "计划保存成功。";
          await fetchTaskPlans(projectId, { force: true });
        } catch (e) {
          TASK_PLAN_UI.noteByTask[taskKey] = "保存失败：" + String((e && e.message) || e || "未知错误");
        } finally {
          delete TASK_PLAN_UI.actionByTask[taskKey];
          maybeRerenderTaskDetail(it);
        }
      });
      editorOps.appendChild(saveBtn);

      const toggleBtn = el("button", { class: "btn", text: editorOpen ? "收起编辑区" : "展开编辑区" });
      toggleBtn.disabled = !!actionBusy;
      toggleBtn.addEventListener("click", () => {
        TASK_PLAN_UI.editorOpenByTask[taskKey] = !editorOpen;
        if (!TASK_PLAN_UI.editorOpenByTask[taskKey]) delete TASK_PLAN_UI.draftByTask[taskKey];
        maybeRerenderTaskDetail(it);
      });
      editorOps.appendChild(toggleBtn);
      card.appendChild(editorOps);

      const textarea = el("textarea", {
        class: "task-plan-textarea",
        placeholder: "计划表 JSON（POST /task-plans）",
      });
      textarea.value = draft;
      textarea.addEventListener("input", () => {
        TASK_PLAN_UI.draftByTask[taskKey] = textarea.value;
      });
      editorWrap.appendChild(textarea);
      card.appendChild(editorWrap);

      const cacheTip = cache && cache.fetchedAt
        ? ("计划缓存刷新于 " + compactDateTime(cache.fetchedAt))
        : "";
      if (cacheTip) card.appendChild(el("div", { class: "task-plan-foot", text: cacheTip }));

      return card;
    }

    function assistTaskKey(it) {
      const p = String((it && it.project_id) || STATE.project || "").trim();
      const path = String((it && it.path) || "").trim();
      return [p, path || "unknown"].join("::");
    }

    function assistRequestKey(it, requestId) {
      return assistTaskKey(it) + "::" + String(requestId || "").trim();
    }

    function assistMockEnabled() {
      try { return localStorage.getItem("taskDashboard.assistMockEnabled") === "1"; } catch (_) {}
      return false;
    }

    function setAssistMockEnabled(enabled) {
      try {
        if (enabled) localStorage.setItem("taskDashboard.assistMockEnabled", "1");
        else localStorage.removeItem("taskDashboard.assistMockEnabled");
      } catch (_) {}
    }

    function normalizeAssistStatus(raw) {
      const s = String(raw || "").trim().toLowerCase();
      if ([
        "open",
        "pending_reply",
        "acknowledged",
        "in_progress",
        "replied",
        "resolved",
        "expired",
        "closed",
        "canceled",
        "error",
      ].includes(s)) return s;
      return "open";
    }

    function assistStatusLabel(raw) {
      const s = normalizeAssistStatus(raw);
      return ({
        open: "待处理",
        pending_reply: "待回复",
        acknowledged: "已确认",
        in_progress: "处理中",
        replied: "已回复",
        resolved: "已解决",
        closed: "已关闭",
        expired: "已过期",
        canceled: "已取消",
        error: "异常",
      })[s] || s;
    }

    function assistStatusTone(raw) {
      const s = normalizeAssistStatus(raw);
      if (s === "resolved") return "good";
      if (s === "canceled" || s === "error") return "bad";
      if (s === "pending_reply" || s === "acknowledged" || s === "in_progress" || s === "replied") return "warn";
      if (s === "closed" || s === "expired") return "muted";
      return "muted";
    }

    function assistStatusCanReply(raw) {
      const s = normalizeAssistStatus(raw);
      return ["open", "pending_reply", "acknowledged", "in_progress", "replied"].includes(s);
    }

    function assistStatusCanClose(raw) {
      const s = normalizeAssistStatus(raw);
      return ["open", "pending_reply", "acknowledged", "in_progress", "replied"].includes(s);
    }

    function assistIsPendingReply(raw) {
      const s = normalizeAssistStatus(raw);
      return ["open", "pending_reply", "acknowledged", "in_progress", "replied"].includes(s);
    }

    function assistNormalizeBool(v, fallback = false) {
      if (typeof v === "boolean") return v;
      const s = String(v == null ? "" : v).trim().toLowerCase();
      if (["1", "true", "yes", "y", "on", "是"].includes(s)) return true;
      if (["0", "false", "no", "n", "off", "否"].includes(s)) return false;
      return !!fallback;
    }

    function assistNormalizeInt(v, fallback = 0) {
      const n = Number(v);
      if (!Number.isFinite(n)) return Number(fallback || 0);
      return Math.round(n);
    }

    function assistActorLabel(raw) {
      const s = String(raw || "").trim().toLowerCase();
      if (!s) return "-";
      if (s === "user") return "我";
      if (s === "agent") return "通道Agent";
      if (s === "system") return "系统";
      return s;
    }

    function assistTriggerReasonLabel(raw) {
      const s = String(raw || "").trim().toLowerCase();
      return ({
        support_below_threshold: "支撑度低于阈值",
        evidence_missing: "证据缺失",
        insufficient_evidence: "证据不足",
        impact_unclear: "影响范围不清",
        owner_unclear: "责任人不清",
        deadline_unclear: "截止时间不清",
      })[s] || (s || "未标注");
    }

    function assistMissingDimensionLabel(raw) {
      const s = String(raw || "").trim().toLowerCase();
      return ({
        facts: "事实",
        evidence: "证据",
        impact: "影响",
        owner: "责任人",
        deadline: "截止时间",
      })[s] || s;
    }

    function assistSupportLevelLabel(raw) {
      const s = String(raw || "").trim().toLowerCase();
      return ({
        sufficient: "充分",
        watch: "观察",
        insufficient: "不足",
      })[s] || (s || "未标注");
    }

    function assistCloseActionLabel(raw) {
      const s = String(raw || "").trim().toLowerCase();
      return ({
        resolved: "已解决",
        escalate: "仍不足升级",
        dismissed: "不采纳",
        duplicate: "重复",
        expired: "过期",
      })[s] || (s || "-");
    }

    function assistEvidenceGapText(item) {
      const a = item || {};
      const dims = Array.isArray(a.missing_dimensions) ? a.missing_dimensions : [];
      const dimText = dims.length ? dims.map(assistMissingDimensionLabel).join("、") : "未标注";
      const have = Math.max(0, assistNormalizeInt(a.evidence_count, 0));
      const need = Math.max(0, assistNormalizeInt(a.required_evidence_count, 0));
      if (need > 0) return dimText + "（证据 " + have + "/" + need + "）";
      return dimText;
    }

    function normalizeAssistItem(raw) {
      const a = (raw && typeof raw === "object") ? raw : {};
      const refs = Array.isArray(a.context_refs || a.contextRefs) ? (a.context_refs || a.contextRefs) : [];
      const dims = Array.isArray(a.missing_dimensions || a.missingDimensions)
        ? (a.missing_dimensions || a.missingDimensions)
        : [];
      return {
        assist_request_id: String(a.assist_request_id || a.assistRequestId || "").trim(),
        project_id: String(a.project_id || a.projectId || "").trim(),
        task_path: String(a.task_path || a.taskPath || "").trim(),
        source_channel: String(a.source_channel || a.sourceChannel || "").trim(),
        target_channel: String(a.target_channel || a.targetChannel || "").trim(),
        status: normalizeAssistStatus(a.status),
        priority: String(a.priority || "normal").trim().toLowerCase(),
        question: String(a.question || "").trim(),
        context_refs: refs.map((x) => String(x || "").trim()).filter(Boolean),
        trigger_reason: String(a.trigger_reason || a.triggerReason || "").trim().toLowerCase(),
        decision_required: assistNormalizeBool(a.decision_required != null ? a.decision_required : a.decisionRequired, false),
        missing_dimensions: dims.map((x) => String(x || "").trim().toLowerCase()).filter(Boolean),
        support_score: Math.max(0, assistNormalizeInt(a.support_score != null ? a.support_score : a.supportScore, 0)),
        support_level: String(a.support_level || a.supportLevel || "").trim().toLowerCase(),
        threshold_triggered: assistNormalizeBool(
          a.threshold_triggered != null ? a.threshold_triggered : a.thresholdTriggered,
          false
        ),
        evidence_count: Math.max(0, assistNormalizeInt(a.evidence_count != null ? a.evidence_count : a.evidenceCount, 0)),
        required_evidence_count: Math.max(
          0,
          assistNormalizeInt(a.required_evidence_count != null ? a.required_evidence_count : a.requiredEvidenceCount, 0)
        ),
        help_kind: String(a.help_kind || a.helpKind || "").trim().toLowerCase(),
        created_by: String(a.created_by || a.createdBy || "").trim(),
        created_at: String(a.created_at || a.createdAt || "").trim(),
        updated_at: String(a.updated_at || a.updatedAt || "").trim(),
        last_reply: String(a.last_reply || a.lastReply || "").trim(),
        last_reply_by: String(a.last_reply_by || a.lastReplyBy || "").trim(),
        last_reply_at: String(a.last_reply_at || a.lastReplyAt || "").trim(),
        writeback_run_id: String(a.writeback_run_id || a.writebackRunId || "").trim(),
        close_action: String(a.close_action || a.closeAction || "").trim().toLowerCase(),
        close_by: String(a.close_by || a.closeBy || "").trim().toLowerCase(),
        resolution_summary: String(a.resolution_summary || a.resolutionSummary || "").trim(),
        resolved_at: String(a.resolved_at || a.resolvedAt || "").trim(),
        close_writeback_run_id: String(a.close_writeback_run_id || a.closeWritebackRunId || "").trim(),
        close_note: String(a.close_note || a.closeNote || "").trim(),
        error: String(a.error || "").trim(),
      };
    }

    function assistSortKey(item) {
      return Math.max(toTimeNum(item && item.updated_at), toTimeNum(item && item.created_at), 0);
    }

    function assistMockStorageKey(it) {
      const pid = encodeURIComponent(String((it && it.project_id) || STATE.project || "").trim());
      const path = encodeURIComponent(String((it && it.path) || "").trim());
      return "taskDashboard.assistMock." + pid + "." + path;
    }

    function assistReadMockItems(it) {
      try {
        const key = assistMockStorageKey(it);
        const raw = localStorage.getItem(key);
        if (!raw) return [];
        const arr = JSON.parse(raw);
        if (!Array.isArray(arr)) return [];
        return arr.map(normalizeAssistItem);
      } catch (_) {}
      return [];
    }

    function assistWriteMockItems(it, items) {
      try {
        const key = assistMockStorageKey(it);
        localStorage.setItem(key, JSON.stringify(Array.isArray(items) ? items : []));
      } catch (_) {}
    }

    function assistEnsureMockSeed(it) {
      let items = assistReadMockItems(it);
      if (items.length) return items;
      const ts = new Date();
      const ymd = ts.toISOString().slice(0, 10).replace(/-/g, "");
      const now = ts.toISOString();
      items = [normalizeAssistItem({
        assist_request_id: "asr_mock_" + ymd + "_001",
        project_id: String((it && it.project_id) || STATE.project || ""),
        task_path: String((it && it.path) || ""),
        source_channel: String((it && it.channel) || STATE.channel || ""),
        target_channel: "待协同通道",
        status: "pending_reply",
        priority: "normal",
        question: "请补充当前任务仍缺的证据与下一步计划。",
        context_refs: [String((it && it.path) || "")].filter(Boolean),
        created_by: "system",
        created_at: now,
        updated_at: now,
      })];
      assistWriteMockItems(it, items);
      return items;
    }

    function assistItemsForTask(it) {
      const key = assistTaskKey(it);
      const cache = ASSIST_UI.cacheByTask[key];
      return (cache && Array.isArray(cache.items)) ? cache.items : [];
    }

    function assistActionBusy(it) {
      return String(ASSIST_UI.actionByTask[assistTaskKey(it)] || "");
    }

    function setAssistNote(it, text) {
      ASSIST_UI.noteByTask[assistTaskKey(it)] = String(text || "");
    }

    function assistDraftForRequest(it, requestId, fallback = "") {
      const key = assistRequestKey(it, requestId);
      const hit = String(ASSIST_UI.draftByRequest[key] || "");
      return hit || String(fallback || "");
    }

    function setAssistDraft(it, requestId, text) {
      const key = assistRequestKey(it, requestId);
      ASSIST_UI.draftByRequest[key] = String(text || "");
    }

    function assistApiErrorMessage(status, detail) {
      const s = Number(status || 0);
      if (s === 401 || s === 403) return "鉴权失败，请检查 Token 配置。";
      if (s === 404) return "协助单不存在或已被移除。";
      if (s === 409 || s === 422) return "状态冲突或终态不可操作，请刷新后重试。";
      if (s >= 500) return "服务异常，请稍后重试。";
      return String(detail || "请求失败");
    }

    async function fetchAssistRequestsForTask(it, opts = {}) {
      if (!it || !isTaskItem(it)) return [];
      const key = assistTaskKey(it);
      const force = !!opts.force;
      const maxAgeMs = Number(opts.maxAgeMs || 0);
      const cached = ASSIST_UI.cacheByTask[key];
      if (!force && cached && maxAgeMs > 0) {
        const age = Date.now() - Number(cached.fetchedAtMs || 0);
        if (age >= 0 && age < maxAgeMs) return cached.items || [];
      }
      if (ASSIST_UI.loadingByTask[key]) return (cached && cached.items) || [];

      ASSIST_UI.loadingByTask[key] = true;
      ASSIST_UI.errorByTask[key] = "";
      const projectId = String((it && it.project_id) || STATE.project || "").trim();
      const taskPath = String((it && it.path) || "").trim();
      try {
        if (!projectId || !taskPath) throw new Error("缺少 project_id 或 task_path");
        const qs = new URLSearchParams();
        qs.set("task_path", taskPath);
        qs.set("limit", "50");
        const resp = await fetch("/api/projects/" + encodeURIComponent(projectId) + "/assist-requests?" + qs.toString(), {
          headers: authHeaders({}),
          cache: "no-store",
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          const err = new Error(assistApiErrorMessage(resp.status, detail));
          err.httpStatus = resp.status;
          throw err;
        }
        const data = await resp.json().catch(() => ({}));
        const rawItems = Array.isArray(data && data.items)
          ? data.items
          : (data && data.item ? [data.item] : []);
        const items = rawItems.map(normalizeAssistItem).sort((a, b) => assistSortKey(b) - assistSortKey(a));
        ASSIST_UI.cacheByTask[key] = {
          items,
          fetchedAt: new Date().toISOString(),
          fetchedAtMs: Date.now(),
          source: "api",
        };
        ASSIST_UI.sourceByTask[key] = "api";
        return items;
      } catch (e) {
        ASSIST_UI.errorByTask[key] = String((e && e.message) || "协助单查询失败");
        if (assistMockEnabled()) {
          const items = assistEnsureMockSeed(it).sort((a, b) => assistSortKey(b) - assistSortKey(a));
          ASSIST_UI.cacheByTask[key] = {
            items,
            fetchedAt: new Date().toISOString(),
            fetchedAtMs: Date.now(),
            source: "mock",
          };
          ASSIST_UI.sourceByTask[key] = "mock";
          return items;
        }
        return (cached && cached.items) || [];
      } finally {
        ASSIST_UI.loadingByTask[key] = false;
        maybeRerenderTaskDetail(it);
      }
    }

    async function assistSubmitReply(it, requestId) {
      if (!it || !isTaskItem(it)) return;
      const key = assistTaskKey(it);
      if (ASSIST_UI.actionByTask[key]) return;
      const reqId = String(requestId || "").trim();
      if (!reqId) return;
      const list = assistItemsForTask(it);
      const item = list.find((x) => String(x.assist_request_id || "") === reqId);
      if (!item) {
        setAssistNote(it, "未找到协助单，请先刷新。");
        maybeRerenderTaskDetail(it);
        return;
      }
      if (!assistStatusCanReply(item.status)) {
        setAssistNote(it, "当前状态不可回复。");
        maybeRerenderTaskDetail(it);
        return;
      }
      const reply = String(assistDraftForRequest(it, reqId, item.last_reply || "") || "").trim();
      if (!reply) {
        setAssistNote(it, "回复内容不能为空。");
        maybeRerenderTaskDetail(it);
        return;
      }

      ASSIST_UI.actionByTask[key] = "reply";
      setAssistNote(it, "正在提交回复…");
      maybeRerenderTaskDetail(it);
      try {
        const source = String((ASSIST_UI.sourceByTask[key] || "")).toLowerCase();
        if (assistMockEnabled() || source === "mock") {
          const now = new Date().toISOString();
          const arr = assistReadMockItems(it).map((x) => {
            if (String(x.assist_request_id || "") !== reqId) return x;
            return normalizeAssistItem({
              ...x,
              status: "replied",
              last_reply: reply,
              last_reply_by: "user",
              last_reply_at: now,
              updated_at: now,
              writeback_run_id: x.writeback_run_id || ("mock-run-" + now.replace(/[^\d]/g, "").slice(0, 14)),
              error: "",
            });
          });
          assistWriteMockItems(it, arr);
          ASSIST_UI.cacheByTask[key] = {
            items: arr,
            fetchedAt: now,
            fetchedAtMs: Date.now(),
            source: "mock",
          };
          ASSIST_UI.sourceByTask[key] = "mock";
          setAssistNote(it, "已在 Mock 模式提交回复。");
          return;
        }

        const projectId = String((it && it.project_id) || STATE.project || "").trim();
        const resp = await fetch(
          "/api/projects/" + encodeURIComponent(projectId) + "/assist-requests/" + encodeURIComponent(reqId) + "/reply",
          {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ reply, reply_by: "user" }),
          }
        );
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(assistApiErrorMessage(resp.status, detail));
        }
        const data = await resp.json().catch(() => ({}));
        const updated = data && data.item ? normalizeAssistItem(data.item) : null;
        let next = assistItemsForTask(it).slice();
        if (updated) {
          next = next.map((x) => (String(x.assist_request_id || "") === reqId ? updated : x));
        } else {
          const now = new Date().toISOString();
          next = next.map((x) => {
            if (String(x.assist_request_id || "") !== reqId) return x;
            return normalizeAssistItem({
              ...x,
              status: "replied",
              last_reply: reply,
              last_reply_by: "user",
              last_reply_at: now,
              updated_at: now,
            });
          });
        }
        ASSIST_UI.cacheByTask[key] = {
          items: next.sort((a, b) => assistSortKey(b) - assistSortKey(a)),
          fetchedAt: new Date().toISOString(),
          fetchedAtMs: Date.now(),
          source: "api",
        };
        ASSIST_UI.sourceByTask[key] = "api";
        setAssistNote(it, "回复提交成功。");
      } catch (e) {
        setAssistNote(it, "回复失败：" + String((e && e.message) || "未知错误"));
      } finally {
        delete ASSIST_UI.actionByTask[key];
        maybeRerenderTaskDetail(it);
      }
    }

    async function assistSubmitClose(it, requestId, closeAction) {
      if (!it || !isTaskItem(it)) return;
      const key = assistTaskKey(it);
      if (ASSIST_UI.actionByTask[key]) return;
      const reqId = String(requestId || "").trim();
      const action = String(closeAction || "").trim().toLowerCase();
      if (!reqId || !["resolved", "escalate"].includes(action)) return;
      const list = assistItemsForTask(it);
      const item = list.find((x) => String(x.assist_request_id || "") === reqId);
      if (!item) {
        setAssistNote(it, "未找到协助单，请先刷新。");
        maybeRerenderTaskDetail(it);
        return;
      }
      if (!assistStatusCanClose(item.status)) {
        setAssistNote(it, "当前状态不可收口。");
        maybeRerenderTaskDetail(it);
        return;
      }

      const summary = String(
        assistDraftForRequest(it, reqId, item.resolution_summary || item.last_reply || "")
          || ""
      ).trim();
      if (!summary) {
        setAssistNote(it, "请先填写收口结论。");
        maybeRerenderTaskDetail(it);
        return;
      }

      ASSIST_UI.actionByTask[key] = "close:" + action;
      setAssistNote(it, action === "resolved" ? "正在提交已解决收口…" : "正在提交不足升级…");
      maybeRerenderTaskDetail(it);
      try {
        const source = String((ASSIST_UI.sourceByTask[key] || "")).toLowerCase();
        if (assistMockEnabled() || source === "mock") {
          const now = new Date().toISOString();
          const arr = assistReadMockItems(it).map((x) => {
            if (String(x.assist_request_id || "") !== reqId) return x;
            return normalizeAssistItem({
              ...x,
              status: action === "resolved" ? "resolved" : "closed",
              close_action: action,
              close_by: "user",
              resolution_summary: summary,
              resolved_at: now,
              close_writeback_run_id: x.close_writeback_run_id
                || ("mock-close-" + now.replace(/[^\d]/g, "").slice(0, 14)),
              updated_at: now,
              error: "",
            });
          });
          assistWriteMockItems(it, arr);
          ASSIST_UI.cacheByTask[key] = {
            items: arr,
            fetchedAt: now,
            fetchedAtMs: Date.now(),
            source: "mock",
          };
          ASSIST_UI.sourceByTask[key] = "mock";
          setAssistNote(it, action === "resolved" ? "已在 Mock 模式完成收口。" : "已在 Mock 模式标记不足升级。");
          return;
        }

        const projectId = String((it && it.project_id) || STATE.project || "").trim();
        const resp = await fetch(
          "/api/projects/" + encodeURIComponent(projectId) + "/assist-requests/" + encodeURIComponent(reqId) + "/close",
          {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
              close_action: action,
              close_by: "user",
              resolution_summary: summary,
            }),
          }
        );
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(assistApiErrorMessage(resp.status, detail));
        }
        const data = await resp.json().catch(() => ({}));
        const updated = data && data.item ? normalizeAssistItem(data.item) : null;
        const runId = String(data && data.run && data.run.id || "").trim();
        let next = assistItemsForTask(it).slice();
        if (updated) {
          next = next.map((x) => (String(x.assist_request_id || "") === reqId ? updated : x));
        } else {
          const now = new Date().toISOString();
          next = next.map((x) => {
            if (String(x.assist_request_id || "") !== reqId) return x;
            return normalizeAssistItem({
              ...x,
              status: action === "resolved" ? "resolved" : "closed",
              close_action: action,
              close_by: "user",
              resolution_summary: summary,
              resolved_at: now,
              updated_at: now,
            });
          });
        }
        ASSIST_UI.cacheByTask[key] = {
          items: next.sort((a, b) => assistSortKey(b) - assistSortKey(a)),
          fetchedAt: new Date().toISOString(),
          fetchedAtMs: Date.now(),
          source: "api",
        };
        ASSIST_UI.sourceByTask[key] = "api";
        if (action === "resolved") {
          setAssistNote(it, runId ? ("已解决收口成功，回写 run=" + runId) : "已解决收口成功。");
        } else {
          setAssistNote(it, runId ? ("已标记不足升级，回写 run=" + runId) : "已标记不足升级。");
        }
      } catch (e) {
        setAssistNote(it, "收口失败：" + String((e && e.message) || "未知错误"));
      } finally {
        delete ASSIST_UI.actionByTask[key];
        maybeRerenderTaskDetail(it);
      }
    }

    function renderAssistRequestCard(it) {
      if (!it || !isTaskItem(it)) return null;
      const key = assistTaskKey(it);
      const cache = ASSIST_UI.cacheByTask[key];
      const items = (cache && Array.isArray(cache.items)) ? cache.items : [];
      const loading = !!ASSIST_UI.loadingByTask[key];
      const err = String(ASSIST_UI.errorByTask[key] || "").trim();
      const note = String(ASSIST_UI.noteByTask[key] || "").trim();
      const source = String((cache && cache.source) || ASSIST_UI.sourceByTask[key] || (assistMockEnabled() ? "mock" : "api")).toLowerCase();
      const actionBusy = assistActionBusy(it);

      const card = el("section", { class: "assist-card" });
      const head = el("div", { class: "assist-head" });
      const titleWrap = el("div", { class: "assist-titlewrap" });
      titleWrap.appendChild(el("div", { class: "assist-kicker", text: "证据补全协助单" }));
      titleWrap.appendChild(el("div", { class: "assist-title", text: "提问方 / 回复方分区 + 收口交互（V1）" }));
      titleWrap.appendChild(el("div", { class: "assist-sub", text: "数据源：" + (source === "mock" ? "Mock（联调占位）" : "API") }));
      head.appendChild(titleWrap);

      const ops = el("div", { class: "assist-head-ops" });
      const refreshBtn = el("button", { class: "btn", text: loading ? "刷新中..." : "刷新协助单" });
      refreshBtn.disabled = loading || !!actionBusy;
      refreshBtn.addEventListener("click", () => {
        setAssistNote(it, "正在刷新协助单…");
        maybeRerenderTaskDetail(it);
        fetchAssistRequestsForTask(it, { force: true });
      });
      ops.appendChild(refreshBtn);

      const mockBtn = el("button", { class: "btn", text: assistMockEnabled() ? "Mock:开" : "Mock:关" });
      mockBtn.disabled = !!actionBusy;
      mockBtn.title = "接口不可用时可切换 Mock 联调";
      mockBtn.addEventListener("click", () => {
        setAssistMockEnabled(!assistMockEnabled());
        setAssistNote(it, assistMockEnabled() ? "已开启 Mock 模式。" : "已关闭 Mock 模式。");
        fetchAssistRequestsForTask(it, { force: true });
      });
      ops.appendChild(mockBtn);
      head.appendChild(ops);
      card.appendChild(head);

      if (err && source !== "mock") {
        card.appendChild(el("div", { class: "assist-error", text: "协助单查询失败：" + err }));
      }
      if (note) {
        card.appendChild(el("div", { class: "assist-note" + (note.includes("失败") ? " error" : ""), text: note }));
      }

      const listWrap = el("div", { class: "assist-list" });
      const pendingItems = items.filter((x) => assistIsPendingReply(x.status));
      const historyItems = items.filter((x) => !assistIsPendingReply(x.status));
      const historyExpanded = !!ASSIST_UI.historyExpandedByTask[key];

      const renderAssistRow = (a, opts = {}) => {
        const showReply = opts.showReply !== false;
        const row = el("article", { class: "assist-item" });
        const top = el("div", { class: "assist-item-top" });
        top.appendChild(chip(a.assist_request_id || "-", "muted"));
        top.appendChild(chip(assistStatusLabel(a.status), assistStatusTone(a.status)));
        if (a.close_action) {
          const actionTone = a.close_action === "resolved" ? "good" : "warn";
          top.appendChild(chip("收口:" + assistCloseActionLabel(a.close_action), actionTone));
        }
        if (a.decision_required) top.appendChild(chip("需拍板", "warn"));
        if (a.threshold_triggered) top.appendChild(chip("自动触发", "warn"));
        if (a.priority) top.appendChild(chip("优先级:" + a.priority, "muted"));
        row.appendChild(top);

        const focus = el("div", { class: "assist-focus-grid" });
        const pushFocus = (label, value, cls = "") => {
          const txt = String(value || "").trim() || "-";
          const itemNode = el("div", { class: "assist-focus-item" + (cls ? (" " + cls) : "") });
          itemNode.appendChild(el("div", { class: "assist-focus-k", text: label }));
          itemNode.appendChild(el("div", { class: "assist-focus-v", text: txt }));
          focus.appendChild(itemNode);
        };
        pushFocus("触发原因", assistTriggerReasonLabel(a.trigger_reason));
        pushFocus("证据缺口", assistEvidenceGapText(a));
        pushFocus("需拍板项", a.decision_required ? "需要拍板" : "无需拍板");
        if (a.support_level || Number(a.support_score || 0) > 0) {
          const n = Math.max(0, Number(a.support_score || 0));
          pushFocus("支撑度", n + "（" + assistSupportLevelLabel(a.support_level) + "）");
        }
        row.appendChild(focus);

        const split = el("div", { class: "assist-split" });
        const askPane = el("section", { class: "assist-pane" });
        const replyPane = el("section", { class: "assist-pane" });
        askPane.appendChild(el("div", { class: "assist-pane-title", text: "提问方" }));
        replyPane.appendChild(el("div", { class: "assist-pane-title", text: "回复方" }));

        const addMeta = (parent, k, v, cls = "") => {
          const vv = String(v || "").trim();
          if (!vv) return;
          const mrow = el("div", { class: "assist-meta-row" + (cls ? (" " + cls) : "") });
          mrow.appendChild(el("div", { class: "assist-meta-k", text: k }));
          mrow.appendChild(el("div", { class: "assist-meta-v", text: vv }));
          parent.appendChild(mrow);
        };

        const askMeta = el("div", { class: "assist-meta-grid" });
        addMeta(askMeta, "来源通道", a.source_channel || "-");
        addMeta(askMeta, "提问角色", assistActorLabel(a.created_by));
        addMeta(askMeta, "创建时间", formatTsOrDash(a.created_at));
        addMeta(askMeta, "最近更新", formatTsOrDash(a.updated_at));
        askPane.appendChild(askMeta);
        askPane.appendChild(el("div", {
          class: "assist-question",
          text: a.question || "（未提供具体问题）",
        }));

        if (Array.isArray(a.context_refs) && a.context_refs.length) {
          const refs = el("div", { class: "assist-refs" });
          refs.appendChild(el("div", { class: "assist-refs-title", text: "证据关联" }));
          const ul = el("ul", { class: "assist-refs-list" });
          for (const ref of a.context_refs.slice(0, 4)) {
            ul.appendChild(el("li", { text: ref }));
          }
          refs.appendChild(ul);
          askPane.appendChild(refs);
        }

        const replyMeta = el("div", { class: "assist-meta-grid" });
        addMeta(replyMeta, "目标通道", a.target_channel || "-");
        addMeta(replyMeta, "最近回复人", assistActorLabel(a.last_reply_by));
        addMeta(replyMeta, "最近回复时间", formatTsOrDash(a.last_reply_at));
        addMeta(replyMeta, "回写run", a.writeback_run_id, "mono");
        addMeta(replyMeta, "收口动作", assistCloseActionLabel(a.close_action));
        addMeta(replyMeta, "收口人", assistActorLabel(a.close_by));
        addMeta(replyMeta, "收口时间", formatTsOrDash(a.resolved_at));
        addMeta(replyMeta, "收口回写run", a.close_writeback_run_id, "mono");
        if (a.error) addMeta(replyMeta, "异常", a.error, "error");
        replyPane.appendChild(replyMeta);
        if (a.last_reply) {
          replyPane.appendChild(el("div", { class: "assist-reply-body", text: a.last_reply }));
        }
        if (a.resolution_summary) {
          const sum = el("div", { class: "assist-resolution" });
          sum.appendChild(el("div", { class: "assist-resolution-title", text: "收口结论" }));
          sum.appendChild(el("div", { class: "assist-resolution-body", text: a.resolution_summary }));
          replyPane.appendChild(sum);
        }
        split.appendChild(askPane);
        split.appendChild(replyPane);
        row.appendChild(split);

        if (!showReply) return row;

        const canReply = assistStatusCanReply(a.status);
        const canClose = assistStatusCanClose(a.status);
        const replyBox = el("div", { class: "assist-reply-box" });
        const ta = el("textarea", {
          class: "assist-reply-textarea",
          placeholder: (canReply || canClose) ? "输入回复内容或收口结论..." : "当前状态不可操作",
        });
        ta.value = assistDraftForRequest(it, a.assist_request_id, a.resolution_summary || a.last_reply || "");
        ta.disabled = (!canReply && !canClose) || !!actionBusy;
        ta.addEventListener("input", () => setAssistDraft(it, a.assist_request_id, ta.value));
        replyBox.appendChild(ta);

        const rops = el("div", { class: "assist-reply-ops" });
        if (canReply) {
          const submitBtn = el("button", { class: "btn", text: actionBusy === "reply" ? "提交中..." : "提交回复" });
          submitBtn.disabled = !!actionBusy;
          submitBtn.addEventListener("click", () => {
            setAssistDraft(it, a.assist_request_id, ta.value);
            assistSubmitReply(it, a.assist_request_id);
          });
          rops.appendChild(submitBtn);
        }
        if (canClose) {
          const resolvedBtn = el("button", {
            class: "btn primary",
            text: actionBusy === "close:resolved" ? "收口中..." : "已解决收口",
          });
          resolvedBtn.disabled = !!actionBusy;
          resolvedBtn.addEventListener("click", () => {
            setAssistDraft(it, a.assist_request_id, ta.value);
            assistSubmitClose(it, a.assist_request_id, "resolved");
          });
          rops.appendChild(resolvedBtn);

          const escalateBtn = el("button", {
            class: "btn danger",
            text: actionBusy === "close:escalate" ? "升级中..." : "仍不足升级",
          });
          escalateBtn.disabled = !!actionBusy;
          escalateBtn.addEventListener("click", () => {
            setAssistDraft(it, a.assist_request_id, ta.value);
            assistSubmitClose(it, a.assist_request_id, "escalate");
          });
          rops.appendChild(escalateBtn);
        }
        if (!canReply && !canClose) {
          rops.appendChild(chip("终态不可操作", "muted"));
        }
        replyBox.appendChild(rops);
        row.appendChild(replyBox);
        return row;
      };

      if (!pendingItems.length && !historyItems.length) {
        const txt = loading
          ? "协助单加载中..."
          : (assistMockEnabled() ? "暂无协助单（Mock 模式，待联调后切换真实数据）。" : "暂无协助单。");
        listWrap.appendChild(el("div", { class: "assist-empty", text: txt }));
      } else {
        if (!pendingItems.length) {
          listWrap.appendChild(el("div", {
            class: "assist-empty",
            text: historyItems.length ? "当前无待处理协助单，历史项可展开查看。" : "当前无待处理协助单。",
          }));
        } else {
          for (const a of pendingItems) {
            listWrap.appendChild(renderAssistRow(a, { showReply: true }));
          }
        }

        if (historyItems.length) {
          const historyWrap = el("div", { class: "assist-history-wrap" });
          const toggleBtn = el("button", {
            class: "btn",
            text: historyExpanded ? ("收起历史（" + historyItems.length + "）") : ("展开历史（" + historyItems.length + "）"),
          });
          toggleBtn.disabled = !!actionBusy;
          toggleBtn.addEventListener("click", () => {
            ASSIST_UI.historyExpandedByTask[key] = !historyExpanded;
            maybeRerenderTaskDetail(it);
          });
          historyWrap.appendChild(toggleBtn);
          if (historyExpanded) {
            const historyList = el("div", { class: "assist-history-list" });
            for (const a of historyItems) {
              historyList.appendChild(renderAssistRow(a, { showReply: false }));
            }
            historyWrap.appendChild(historyList);
          }
          listWrap.appendChild(historyWrap);
        }
      }
      card.appendChild(listWrap);
      return card;
    }
