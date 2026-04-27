    const PROJECT_AUTO = {
      cache: Object.create(null),        // projectId -> { status, records?, fetchedAt }
      loading: Object.create(null),      // projectId -> bool
      toggling: Object.create(null),     // projectId -> bool
      errors: Object.create(null),       // projectId -> string
      saving: Object.create(null),       // projectId -> bool
      saveErrors: Object.create(null),   // projectId -> string
      saveNotes: Object.create(null),    // projectId -> string
      draftByProject: Object.create(null), // projectId -> editable draft
      heartbeatDraftByProject: Object.create(null), // projectId -> heartbeat editable draft
      heartbeatErrors: Object.create(null), // projectId -> string
      heartbeatNotes: Object.create(null), // projectId -> string
      heartbeatSaving: Object.create(null), // projectId -> bool
      heartbeatHistoryByTask: Object.create(null), // projectId:taskId -> { items, fetchedAt }
      heartbeatHistoryLoadingByTask: Object.create(null), // projectId:taskId -> bool
      heartbeatHistoryErrorByTask: Object.create(null), // projectId:taskId -> string
      heartbeatActionByTask: Object.create(null), // projectId:taskId -> action text
      seqByProject: Object.create(null), // projectId -> number
      pollTimer: 0,                      // window.setInterval id
    };
    const PROJECT_AUTO_UI = {
      open: false,
      lastProjectId: "",
      recordDrawerOpen: false,
      recordDrawerProjectId: "",
      recordDrawerInspectionTaskId: "",
      recordDrawerObjectKey: "",
      recordDrawerObjectType: "",
      recordDrawerObjectName: "",
      recordDrawerFallbackAll: false,
      heartbeatHistoryTaskId: "",
    };
    const PROJECT_REBUILD_UI = {
      loading: false,
      lastError: "",
      lastAt: "",
    };
    if (typeof window !== "undefined") {
      window.PROJECT_REBUILD_UI = PROJECT_REBUILD_UI;
    }
    const TASK_PUSH_UI = {
      cacheByProject: Object.create(null),   // projectId -> { items, fetchedAt }
      loadingByProject: Object.create(null), // projectId -> bool
      errorByProject: Object.create(null),   // projectId -> string
      seqByProject: Object.create(null),     // projectId -> number
      draftByTask: Object.create(null),      // taskKey -> draft message
      latestByTask: Object.create(null),     // taskKey -> normalized item
      actionByTask: Object.create(null),     // taskKey -> action key
      noteByTask: Object.create(null),       // taskKey -> hint text
    };
    const TASK_PLAN_UI = {
      cacheByProject: Object.create(null),   // projectId -> { items, fetchedAt, fetchedAtMs }
      loadingByProject: Object.create(null), // projectId -> bool
      errorByProject: Object.create(null),   // projectId -> string
      seqByProject: Object.create(null),     // projectId -> number
      selectedPlanByTask: Object.create(null), // taskKey -> planId
      selectedBatchByTask: Object.create(null), // taskKey -> batchId
      filterByTask: Object.create(null),     // taskKey -> active_pending|all|done|blocked
      draftByTask: Object.create(null),      // taskKey -> json text
      editorOpenByTask: Object.create(null), // taskKey -> bool
      actionByTask: Object.create(null),     // taskKey -> save|activate
      noteByTask: Object.create(null),       // taskKey -> hint
    };
    const PROJECT_SCHEDULE_UI = {
      cacheByProject: Object.create(null),    // projectId -> { queue, fetchedAt, fetchedAtMs }
      loadingByProject: Object.create(null),  // projectId -> bool
      savingByProject: Object.create(null),   // projectId -> bool
      errorByProject: Object.create(null),    // projectId -> string
      noteByProject: Object.create(null),     // projectId -> string
      seqByProject: Object.create(null),      // projectId -> number
      draftAddByProject: Object.create(null), // projectId -> taskPath
      retryAfterByProject: Object.create(null), // projectId -> timestamp(ms)
    };
    const ORG_BOARD_UI = {
      cacheByProject: Object.create(null),      // projectId -> { graph, runtime, fetchedAt, fetchedAtMs }
      loadingByProject: Object.create(null),    // projectId -> bool
      errorByProject: Object.create(null),      // projectId -> string
      noteByProject: Object.create(null),       // projectId -> string
      seqByProject: Object.create(null),        // projectId -> number
      retryAfterByProject: Object.create(null), // projectId -> timestamp(ms)
      relCollapsedByProject: Object.create(null), // projectId -> bool
      viewportByProject: Object.create(null),   // projectId -> { x, y }
      agentFilterByProject: Object.create(null), // projectId -> string|array|object (active/idle/legacy multiselect)
      relationMatterFilterByProject: Object.create(null), // projectId -> string|array (dispatch/inspection/callback/recovery/manual/other)
      manualTypeFilterByProject: Object.create(null), // projectId -> string|array (manual relation type ids)
      manualPanelOpenByProject: Object.create(null), // projectId -> bool
      manualDraftByProject: Object.create(null), // projectId -> { source_agent_id,target_agent_id,type_name,color }
      selectedAgentByProject: Object.create(null), // projectId -> selected agent_id(session_id)
      linkDraftByProject: Object.create(null), // projectId -> { source_agent_id, source_side, pointer_x, pointer_y }
      linkEditorByProject: Object.create(null), // projectId -> { source_agent_id,target_agent_id,relation_type_id,type_name,color,line_style,line_width }
    };
    const ASSIST_UI = {
      cacheByTask: Object.create(null),      // taskKey -> { items, fetchedAt, fetchedAtMs, source }
      loadingByTask: Object.create(null),    // taskKey -> bool
      errorByTask: Object.create(null),      // taskKey -> string
      actionByTask: Object.create(null),     // taskKey -> action key
      draftByRequest: Object.create(null),   // requestKey -> draft reply
      historyExpandedByTask: Object.create(null), // taskKey -> bool
      noteByTask: Object.create(null),       // taskKey -> hint text
      sourceByTask: Object.create(null),     // taskKey -> api|mock
    };
    const TASK_PUSH_MODAL = {
      open: false,
      taskPath: "",
    };
    const TASK_SCHEDULE_DND = {
      draggingPath: "",
      draggingTitle: "",
      active: false,
      hoveringDropZone: false,
    };

    const TOKEN_KEY = "taskDashboard.token";
    const AGENT_RELATIONSHIP_BOARD_PAGE = (DATA && DATA.agent_relationship_board_page)
      ? String(DATA.agent_relationship_board_page)
      : (((DATA && DATA.links) && DATA.links.agent_relationship_board_page)
      ? String(DATA.links.agent_relationship_board_page)
      : "/share/project-agent-relationship-board.html");

    function openProjectRelationshipBoard() {
      const base = String(AGENT_RELATIONSHIP_BOARD_PAGE || "/share/project-agent-relationship-board.html").trim();
      const projectId = String((STATE && STATE.project) || "").trim();
      if (!base || !projectId || projectId === "overview") return;
      const params = new URLSearchParams();
      params.set("p", projectId);
      if (STATE && STATE.channel) params.set("c", String(STATE.channel));
      if (STATE && STATE.selectedSessionId) params.set("sid", String(STATE.selectedSessionId));
      window.open(base + "#" + params.toString(), "_blank", "noopener,noreferrer");
    }

    const projectRelationshipBoardBtn = document.getElementById("projectRelationshipBoardBtn");
    if (projectRelationshipBoardBtn) {
      projectRelationshipBoardBtn.addEventListener("click", openProjectRelationshipBoard);
    }

    function getToken() {
      try { return String(localStorage.getItem(TOKEN_KEY) || "").trim(); } catch (_) {}
      return "";
    }

    function setTokenInteractive() {
      const cur = getToken();
      const next = prompt("设置 Token（用于开启 TASK_DASHBOARD_TOKEN 的服务）。留空则清除。", cur);
      if (next === null) return;
      const v = String(next || "").trim();
      try {
        if (v) localStorage.setItem(TOKEN_KEY, v);
        else localStorage.removeItem(TOKEN_KEY);
      } catch (_) {}
    }

    function authHeaders(base) {
      const h = Object.assign({}, base || {});
      const tok = getToken();
      if (tok) h["X-TaskDashboard-Token"] = tok;
      return h;
    }

    const INSPECTION_TARGET_OPTIONS = [
      { value: "scheduled", label: "排期任务" },
      { value: "in_progress", label: "进行中" },
      { value: "pending", label: "待处理" },
      { value: "todo", label: "待开始" },
      { value: "pending_acceptance", label: "待验收" },
    ];
    const INSPECTION_TARGET_VALUE_SET = new Set(INSPECTION_TARGET_OPTIONS.map((opt) => String(opt.value || "")));
    const INSPECTION_TARGET_LABEL_MAP = INSPECTION_TARGET_OPTIONS.reduce((acc, opt) => {
      const k = String((opt && opt.value) || "").trim();
      if (k) acc[k] = String((opt && opt.label) || k);
      return acc;
    }, {});

    function normalizeInspectionTargetsClient(raw, defaults = ["scheduled", "in_progress"]) {
      const fallback = Array.isArray(defaults) ? defaults : ["scheduled", "in_progress"];
      const values = Array.isArray(raw) ? raw : [raw];
      const out = [];
      values.forEach((item) => {
        if (item == null) return;
        String(item)
          .trim()
          .toLowerCase()
          .replace(/-/g, "_")
          .split(/[\s,|]+/)
          .forEach((x) => {
            const v = String(x || "").trim();
            if (!v) return;
            if (!INSPECTION_TARGET_VALUE_SET.has(v)) return;
            if (out.includes(v)) return;
            out.push(v);
          });
      });
      if (out.length) return out;
      return fallback.filter((x) => INSPECTION_TARGET_VALUE_SET.has(x));
    }

    function normalizeAutoInspectionMatchValuesClient(raw) {
      const rows = Array.isArray(raw) ? raw : [];
      const out = [];
      rows.forEach((item) => {
        const txt = String(item == null ? "" : item).trim();
        if (!txt || out.includes(txt)) return;
        out.push(txt);
      });
      return out.slice(0, 30);
    }

    function buildAutoInspectionObjectForTargetClient(target, enabled = true, source = "auto_inspections") {
      const token = String(target || "").trim().toLowerCase().replace(/-/g, "_");
      if (!INSPECTION_TARGET_VALUE_SET.has(token)) return null;
      return {
        object_key: "ins-" + token,
        object_type: token,
        display_name: INSPECTION_TARGET_LABEL_MAP[token] || token,
        enabled: !!enabled,
        source: String(source || "auto_inspections").trim().toLowerCase() || "auto_inspections",
        match_values: [],
      };
    }

    function buildAutoInspectionObjectsFromTargetsClient(targets, source = "inspection_targets") {
      const normalizedTargets = normalizeInspectionTargetsClient(targets, []);
      return normalizedTargets
        .map((target) => buildAutoInspectionObjectForTargetClient(target, true, source))
        .filter(Boolean);
    }

    function normalizeAutoInspectionObjectsClient(raw, fallbackTargets = []) {
      const rows = Array.isArray(raw) ? raw : [];
      const out = [];
      const seen = new Set();
      rows.forEach((item) => {
        if (!item || typeof item !== "object") return;
        const objectTypeRaw = (
          "object_type" in item ? item.object_type : (
            "objectType" in item ? item.objectType : ""
          )
        );
        const objectType = String(objectTypeRaw || "").trim().toLowerCase().replace(/-/g, "_");
        if (!objectType || (objectType !== "custom" && !INSPECTION_TARGET_VALUE_SET.has(objectType))) return;
        const objectKeyRaw = (
          "object_key" in item ? item.object_key : (
            "objectKey" in item ? item.objectKey : ""
          )
        );
        const objectKey = String(objectKeyRaw || "").trim() || (objectType === "custom" ? "" : ("ins-" + objectType));
        if (!objectKey || seen.has(objectKey)) return;
        seen.add(objectKey);
        const displayNameRaw = (
          "display_name" in item ? item.display_name : (
            "displayName" in item ? item.displayName : ""
          )
        );
        const source = String(item.source || "auto_inspections").trim().toLowerCase() || "auto_inspections";
        const matchValuesRaw = (
          "match_values" in item ? item.match_values : (
            "matchValues" in item ? item.matchValues : []
          )
        );
        const row = {
          object_key: objectKey,
          object_type: objectType,
          display_name: String(displayNameRaw || INSPECTION_TARGET_LABEL_MAP[objectType] || objectKey).trim(),
          enabled: _coerceBoolClient(item.enabled, false),
          source: source,
          match_values: objectType === "custom" ? normalizeAutoInspectionMatchValuesClient(matchValuesRaw) : [],
        };
        out.push(row);
      });
      if (out.length) return out;
      return buildAutoInspectionObjectsFromTargetsClient(fallbackTargets, "inspection_targets");
    }

    function autoInspectionTargetsFromObjectsClient(objects) {
      const rows = Array.isArray(objects) ? objects : [];
      const out = [];
      rows.forEach((item) => {
        if (!item || typeof item !== "object") return;
        if (!_coerceBoolClient(item.enabled, false)) return;
        const objectType = String(item.object_type || item.objectType || "").trim().toLowerCase().replace(/-/g, "_");
        if (!INSPECTION_TARGET_VALUE_SET.has(objectType)) return;
        if (out.includes(objectType)) return;
        out.push(objectType);
      });
      return out;
    }

    function upsertAutoInspectionTargetObjectClient(objects, target, enabled) {
      const token = String(target || "").trim().toLowerCase().replace(/-/g, "_");
      if (!INSPECTION_TARGET_VALUE_SET.has(token)) {
        return normalizeAutoInspectionObjectsClient(objects, []);
      }
      const rows = normalizeAutoInspectionObjectsClient(objects, []);
      let found = false;
      const nextRows = rows.map((row) => {
        const objectType = String(row.object_type || "").trim().toLowerCase().replace(/-/g, "_");
        if (objectType !== token) return row;
        found = true;
        return Object.assign({}, row, { enabled: !!enabled });
      });
      if (!found && enabled) {
        const appended = buildAutoInspectionObjectForTargetClient(token, true, "auto_inspections");
        if (appended) nextRows.push(appended);
      }
      return normalizeAutoInspectionObjectsClient(nextRows, []);
    }

    function normalizeInspectionTaskIdClient(raw, fallback = "") {
      const txt = String(raw || fallback || "").trim();
      return txt || "";
    }

    function normalizeInspectionTaskItemsClient(raw, fallback = {}) {
      const rows = Array.isArray(raw) ? raw : [];
      const fb = (fallback && typeof fallback === "object") ? fallback : {};
      const seen = new Set();
      const out = [];
      rows.forEach((item, idx) => {
        const it = (item && typeof item === "object") ? item : {};
        const taskId = normalizeInspectionTaskIdClient(
          firstNonEmptyText([it.inspection_task_id, it.inspectionTaskId]),
          idx === 0 ? "default" : ""
        );
        if (!taskId || seen.has(taskId)) return;
        seen.add(taskId);
        const title = firstNonEmptyText([it.title, it.name, it.display_name, it.displayName]) || ("巡查任务 " + (idx + 1));
        const channelName = firstNonEmptyText([it.channel_name, it.channelName, fb.channelName]);
        const sessionId = firstNonEmptyText([it.session_id, it.sessionId, fb.sessionId]);
        const intervalMinutes = Number(firstNonEmptyText([it.interval_minutes, it.intervalMinutes, fb.intervalMinutes]));
        const promptTemplate = firstNonEmptyText([it.prompt_template, it.promptTemplate, fb.promptText]);
        const inspectionTargets = normalizeInspectionTargetsClient(
          firstNonEmptyText([it.inspection_targets, it.inspectionTargets]) || it.inspection_targets || it.inspectionTargets,
          normalizeInspectionTargetsClient(fb.inspectionTargets || [], ["scheduled", "in_progress"])
        );
        const autoInspections = normalizeAutoInspectionObjectsClient(
          it.auto_inspections || it.autoInspections || [],
          inspectionTargets
        );
        out.push({
          inspection_task_id: taskId,
          title: title,
          enabled: _coerceBoolClient(it.enabled, true),
          channel_name: channelName,
          session_id: sessionId,
          interval_minutes: Number.isFinite(intervalMinutes) ? Math.max(5, intervalMinutes) : Math.max(5, Number(fb.intervalMinutes || 30)),
          prompt_template: promptTemplate || defaultProjectAutoPrompt(String(fb.projectId || "")),
          inspection_targets: inspectionTargets,
          auto_inspections: autoInspections,
          state: String(firstNonEmptyText([it.state, it.status]) || "idle").trim().toLowerCase(),
          ready: _coerceBoolClient(it.ready, true),
          errors: Array.isArray(it.errors) ? it.errors.map((x) => String(x || "").trim()).filter(Boolean) : [],
        });
      });
      if (out.length) return out;
      return [{
        inspection_task_id: "default",
        title: "默认巡查任务",
        enabled: true,
        channel_name: firstNonEmptyText([fb.channelName]),
        session_id: firstNonEmptyText([fb.sessionId]),
        interval_minutes: Math.max(5, Number(fb.intervalMinutes || 30)),
        prompt_template: firstNonEmptyText([fb.promptText]) || defaultProjectAutoPrompt(String(fb.projectId || "")),
        inspection_targets: normalizeInspectionTargetsClient(fb.inspectionTargets || [], ["scheduled", "in_progress"]),
        auto_inspections: normalizeAutoInspectionObjectsClient(fb.autoInspections || [], fb.inspectionTargets || ["scheduled", "in_progress"]),
        state: "idle",
        ready: true,
        errors: [],
      }];
    }

    function hasTrueish(values) {
      const arr = Array.isArray(values) ? values : [];
      for (const v of arr) {
        if (v == null || v === "") continue;
        return _coerceBoolClient(v, false);
      }
      return false;
    }

    function normalizeProjectAutoState(raw, projectId) {
      const s = (raw && typeof raw === "object") ? raw : {};
      const firstNum = (values, fallback = null) => {
        const arr = Array.isArray(values) ? values : [];
        for (const v of arr) {
          if (v == null || v === "") continue;
          const n = Number(v);
          if (!Number.isNaN(n)) return n;
        }
        return fallback;
      };
      const autoDispatchEnabled = hasTrueish([s.auto_dispatch_enabled, s.autoDispatchEnabled]);
      const autoInspectionEnabled = hasTrueish([s.auto_inspection_enabled, s.autoInspectionEnabled, s.reminder_enabled, s.scheduler_enabled]);
      const autoDispatchState = String(firstNonEmptyText([s.auto_dispatch_state, s.autoDispatchState, s.scheduler_state]) || "disabled").trim().toLowerCase() || "disabled";
      const autoInspectionState = String(firstNonEmptyText([s.auto_inspection_state, s.autoInspectionState, s.reminder_state, s.scheduler_state]) || "disabled").trim().toLowerCase() || "disabled";
      const autoInspectionsRaw = Array.isArray(s.auto_inspections)
        ? s.auto_inspections
        : (Array.isArray(s.autoInspections)
          ? s.autoInspections
          : []);
      const inspectionTargetsRaw = Array.isArray(s.auto_inspection_targets)
        ? s.auto_inspection_targets
        : (Array.isArray(s.autoInspectionTargets)
          ? s.autoInspectionTargets
          : (Array.isArray(s.inspection_targets)
            ? s.inspection_targets
            : (Array.isArray(s.inspectionTargets)
              ? s.inspectionTargets
              : firstNonEmptyText([
                s.auto_inspection_targets,
                s.autoInspectionTargets,
                s.inspection_targets,
                s.inspectionTargets,
              ]))));
      const normalizedAutoInspections = normalizeAutoInspectionObjectsClient(
        autoInspectionsRaw,
        inspectionTargetsRaw
      );
      const targetsFromObjects = autoInspectionTargetsFromObjectsClient(normalizedAutoInspections);
      const out = {
        project_id: String(s.project_id || s.projectId || projectId || "").trim(),
        scheduler_enabled: !!s.scheduler_enabled,
        scheduler_state: String(s.scheduler_state || "disabled").trim().toLowerCase() || "disabled",
        scheduler_last_tick_at: String(s.scheduler_last_tick_at || "").trim(),
        scheduler_last_error: String(s.scheduler_last_error || "").trim(),
        reminder_enabled: !!s.reminder_enabled,
        reminder_state: String(s.reminder_state || "disabled").trim().toLowerCase() || "disabled",
        reminder_interval_minutes: (s.reminder_interval_minutes == null ? null : Number(s.reminder_interval_minutes)),
        reminder_cron: String(s.reminder_cron || "").trim(),
        reminder_stale_after_minutes: (s.reminder_stale_after_minutes == null ? null : Number(s.reminder_stale_after_minutes)),
        reminder_escalate_after_minutes: (s.reminder_escalate_after_minutes == null ? null : Number(s.reminder_escalate_after_minutes)),
        reminder_summary_window_minutes: (s.reminder_summary_window_minutes == null ? null : Number(s.reminder_summary_window_minutes)),
        reminder_last_tick_at: String(s.reminder_last_tick_at || "").trim(),
        reminder_last_sent_at: String(s.reminder_last_sent_at || "").trim(),
        reminder_next_due_at: String(s.reminder_next_due_at || "").trim(),
        reminder_last_error: String(s.reminder_last_error || "").trim(),
        auto_dispatch_enabled: autoDispatchEnabled,
        auto_dispatch_state: autoDispatchState,
        auto_dispatch_last_at: firstNonEmptyText([
          s.auto_dispatch_last_at,
          s.auto_dispatch_last_trigger_at,
          s.auto_dispatch_last_sent_at,
          s.auto_dispatch_last_dispatch_at,
          s.autoDispatchLastAt,
          s.scheduler_last_tick_at,
        ]),
        auto_dispatch_last_error: firstNonEmptyText([
          s.auto_dispatch_last_error,
          s.autoDispatchLastError,
          s.scheduler_last_error,
        ]),
        auto_inspection_enabled: autoInspectionEnabled,
        auto_inspection_state: autoInspectionState,
        auto_inspection_channel_name: firstNonEmptyText([
          s.auto_inspection_channel_name,
          s.autoInspectionChannelName,
          s.channel_name,
          s.channelName,
        ]),
        auto_inspection_session_id: firstNonEmptyText([
          s.auto_inspection_session_id,
          s.autoInspectionSessionId,
          s.session_id,
          s.sessionId,
        ]),
        auto_inspection_interval_minutes: firstNum([
          s.auto_inspection_interval_minutes,
          s.autoInspectionIntervalMinutes,
          s.reminder_interval_minutes,
        ], null),
        auto_inspection_prompt_template: firstNonEmptyText([
          s.auto_inspection_prompt_template,
          s.autoInspectionPromptTemplate,
          s.prompt_template,
          s.promptTemplate,
          s.prompt,
        ]),
        auto_inspection_targets: (targetsFromObjects.length
          ? targetsFromObjects
          : normalizeInspectionTargetsClient(
            inspectionTargetsRaw,
            autoInspectionEnabled ? ["scheduled", "in_progress"] : []
          )),
        auto_inspections: normalizeAutoInspectionObjectsClient(
          normalizedAutoInspections,
          autoInspectionEnabled ? ["scheduled", "in_progress"] : []
        ),
        inspection_tasks: normalizeInspectionTaskItemsClient(
          s.inspection_tasks || s.inspectionTasks || [],
          {
            projectId: projectId,
            channelName: firstNonEmptyText([
              s.auto_inspection_channel_name,
              s.autoInspectionChannelName,
              s.channel_name,
              s.channelName,
            ]),
            sessionId: firstNonEmptyText([
              s.auto_inspection_session_id,
              s.autoInspectionSessionId,
              s.session_id,
              s.sessionId,
            ]),
            intervalMinutes: firstNum([
              s.auto_inspection_interval_minutes,
              s.autoInspectionIntervalMinutes,
              s.reminder_interval_minutes,
            ], 30),
            promptText: firstNonEmptyText([
              s.auto_inspection_prompt_template,
              s.autoInspectionPromptTemplate,
              s.prompt_template,
              s.promptTemplate,
              s.prompt,
            ]),
            inspectionTargets: (targetsFromObjects.length
              ? targetsFromObjects
              : normalizeInspectionTargetsClient(
                inspectionTargetsRaw,
                autoInspectionEnabled ? ["scheduled", "in_progress"] : []
              )),
            autoInspections: normalizeAutoInspectionObjectsClient(
              normalizedAutoInspections,
              autoInspectionEnabled ? ["scheduled", "in_progress"] : []
            ),
          }
        ),
        active_inspection_task_id: normalizeInspectionTaskIdClient(
          firstNonEmptyText([s.active_inspection_task_id, s.activeInspectionTaskId]),
          "default"
        ),
        auto_inspection_last_at: firstNonEmptyText([
          s.auto_inspection_last_at,
          s.auto_inspection_last_tick_at,
          s.auto_inspection_last_run_at,
          s.autoInspectionLastAt,
          s.scheduler_last_tick_at,
          s.reminder_last_tick_at,
          s.reminder_last_sent_at,
        ]),
        auto_inspection_next_due_at: firstNonEmptyText([
          s.auto_inspection_next_due_at,
          s.auto_inspection_next_at,
          s.autoInspectionNextDueAt,
          s.reminder_next_due_at,
        ]),
        auto_inspection_last_error: firstNonEmptyText([
          s.auto_inspection_last_error,
          s.autoInspectionLastError,
          s.reminder_last_error,
          s.scheduler_last_error,
        ]),
        worker_running: ("worker_running" in s ? !!s.worker_running : null),
        config_errors: Array.isArray(s.config_errors)
          ? s.config_errors.map((x) => String(x || "").trim()).filter(Boolean)
          : [],
      };
      // 兼容旧渲染字段：若后端只回新口径，则映射回旧字段供现有 UI 使用。
      if (!("scheduler_enabled" in s)) out.scheduler_enabled = !!autoInspectionEnabled;
      if (!("scheduler_state" in s) && !("schedulerState" in s)) out.scheduler_state = autoInspectionState || "disabled";
      if (!out.scheduler_last_tick_at) out.scheduler_last_tick_at = String(out.auto_inspection_last_at || "").trim();
      if (!out.scheduler_last_error) out.scheduler_last_error = String(out.auto_inspection_last_error || "").trim();
      if (!("reminder_enabled" in s)) out.reminder_enabled = !!autoInspectionEnabled;
      if (!("reminder_state" in s) && !("reminderState" in s)) out.reminder_state = autoInspectionState || "disabled";
      if (out.reminder_interval_minutes == null && out.auto_inspection_interval_minutes != null) {
        out.reminder_interval_minutes = Number(out.auto_inspection_interval_minutes);
      }
      if (!out.reminder_last_sent_at) out.reminder_last_sent_at = String(out.auto_inspection_last_at || "").trim();
      if (!out.reminder_next_due_at) out.reminder_next_due_at = String(out.auto_inspection_next_due_at || "").trim();
      if (!out.reminder_last_error) out.reminder_last_error = String(out.auto_inspection_last_error || "").trim();
      const validScheduler = new Set(["disabled", "idle", "scanning", "error"]);
      const validReminder = new Set(["disabled", "idle", "collecting", "dispatching", "error"]);
      if (!validScheduler.has(out.scheduler_state)) out.scheduler_state = out.scheduler_enabled ? "idle" : "disabled";
      if (!validReminder.has(out.reminder_state)) out.reminder_state = out.reminder_enabled ? "idle" : "disabled";
      const validDispatch = new Set(["disabled", "idle", "queued", "running", "dispatching", "error"]);
      const validInspection = new Set(["disabled", "idle", "queued", "running", "scanning", "collecting", "dispatching", "error"]);
      if (!validDispatch.has(out.auto_dispatch_state)) out.auto_dispatch_state = out.auto_dispatch_enabled ? "idle" : "disabled";
      if (!validInspection.has(out.auto_inspection_state)) out.auto_inspection_state = out.auto_inspection_enabled ? "idle" : "disabled";
      return out;
    }

    function _coerceBoolClient(value, defaultValue) {
      if (typeof value === "boolean") return value;
      if (value == null) return !!defaultValue;
      const t = String(value).trim().toLowerCase();
      if (["1", "true", "yes", "on"].includes(t)) return true;
      if (["0", "false", "no", "off"].includes(t)) return false;
      return !!defaultValue;
    }

    function normalizeReminderRecordsPayload(payload) {
      const p = (payload && typeof payload === "object") ? payload : {};
      const candidates = [
        p.reminder_records,
        p.records,
        p.reminderRecords,
        p.items,
        (p.status && p.status.reminder_records),
      ];
      for (const c of candidates) {
        if (Array.isArray(c)) return c;
      }
      return [];
    }

    function autoStateLabel(kind, state) {
      const s = String(state || "").trim().toLowerCase();
      if (kind === "scheduler" || kind === "dispatch") {
        return ({
          disabled: "已关闭",
          idle: "空闲",
          queued: "排队中",
          running: "执行中",
          scanning: "扫描中",
          dispatching: "派发中",
          error: "异常",
        })[s] || s || "-";
      }
      return ({
        disabled: "已关闭",
        idle: "空闲",
        queued: "排队中",
        running: "执行中",
        scanning: "扫描中",
        collecting: "收集中",
        dispatching: "派发中",
        error: "异常",
      })[s] || s || "-";
    }

    function autoStateTone(state) {
      const s = String(state || "").trim().toLowerCase();
      if (s === "error") return "bad";
      if (s === "scanning" || s === "collecting" || s === "dispatching" || s === "queued" || s === "running") return "warn";
      if (s === "disabled") return "muted";
      return "good";
    }

    function formatTsOrDash(ts) {
      const t = String(ts || "").trim();
      if (!t) return "-";
      return shortDateTime(t) || t;
    }

    function projectAutoPanelNode() {
      return document.getElementById("projectAutoPanel");
    }

    function projectAutoWrapNode() {
      return document.getElementById("projectAutoWrap");
    }

    function projectAutoHeaderBtnNode() {
      return document.getElementById("projectAutoHeaderBtn");
    }

    function projectAutoRecordDrawerMaskNode() {
      return document.getElementById("projectAutoRecordDrawerMask");
    }

    function projectAutoRecordDrawerSubNode() {
      return document.getElementById("projectAutoRecordDrawerSub");
    }

    function projectAutoRecordDrawerListNode() {
      return document.getElementById("projectAutoRecordDrawerList");
    }

    function projectAutoRecordDrawerCloseBtnNode() {
      return document.getElementById("projectAutoRecordDrawerCloseBtn");
    }

    function formatHHMM(ts) {
      const d = parseDateTime(ts);
      if (!d) return "";
      const pad2 = (n) => String(n).padStart(2, "0");
      return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    }

    function projectAutoHeaderNextAtHHMM(status, cached) {
      const s = (status && typeof status === "object") ? status : {};
      const explicit = firstNonEmptyText([
        s.auto_inspection_next_due_at,
        s.auto_inspection_next_at,
        s.autoInspectionNextDueAt,
        s.reminder_next_due_at,
        s.reminderNextDueAt,
      ]);
      if (explicit) return formatHHMM(explicit);

      const patrolEnabled = hasTrueish([s.auto_inspection_enabled, s.reminder_enabled, s.scheduler_enabled]);
      if (!patrolEnabled) return "";

      const intervalRaw = firstNonEmptyText([
        s.auto_inspection_interval_minutes,
        s.autoInspectionIntervalMinutes,
        s.reminder_interval_minutes,
      ]);
      const intervalNum = Number(intervalRaw);
      if (!Number.isFinite(intervalNum) || intervalNum < 5) return "";
      const intervalMinutes = Math.max(5, Math.round(intervalNum));

      const baseTs = firstNonEmptyText([
        s.auto_inspection_last_at,
        s.auto_inspection_last_tick_at,
        s.scheduler_last_tick_at,
        s.reminder_last_tick_at,
        s.reminder_last_sent_at,
        cached && cached.fetchedAt,
      ]);
      const base = parseDateTime(baseTs);
      if (!base) return "";
      const next = new Date(base.getTime() + intervalMinutes * 60 * 1000);
      if (Number.isNaN(next.getTime())) return "";
      return formatHHMM(next);
    }

    function projectAutoHeaderStateMeta(projectId) {
      const pid = String(projectId || "").trim();
      const loading = !!PROJECT_AUTO.loading[pid];
      const errText = String(PROJECT_AUTO.errors[pid] || "").trim();
      const cached = PROJECT_AUTO.cache[pid];
      const status = cached && cached.status ? cached.status : null;
      const activeStates = new Set(["queued", "running", "scanning", "collecting", "dispatching"]);
      let key = "disabled";
      let label = "项目调度";
      let tip = "项目调度与提醒";
      if (!status) {
        if (loading) {
          key = "loading";
          tip = "项目调度状态同步中";
        }
        return { key, label, tip };
      }
      const dispatchEnabled = !!status.auto_dispatch_enabled;
      const inspectEnabled = !!status.auto_inspection_enabled;
      const dispatchState = String(status.auto_dispatch_state || "disabled").trim().toLowerCase();
      const inspectState = String(status.auto_inspection_state || "disabled").trim().toLowerCase();
      const hasError = !!(
        errText
        || dispatchState === "error"
        || inspectState === "error"
        || String(status.auto_dispatch_last_error || "").trim()
        || String(status.auto_inspection_last_error || "").trim()
        || String(status.scheduler_last_error || "").trim()
      );
      const anyEnabled = dispatchEnabled || inspectEnabled;
      const anyRunning = activeStates.has(dispatchState) || activeStates.has(inspectState);
      const nextAtHHMM = projectAutoHeaderNextAtHHMM(status, cached);
      if (nextAtHHMM) label = "项目调度 " + nextAtHHMM;
      if (hasError) {
        key = "error";
        tip = "项目调度存在异常，请点击查看详情";
      } else if (!anyEnabled) {
        key = loading ? "loading" : "disabled";
        tip = "项目调度未开启";
      } else if (anyRunning) {
        key = "running";
        tip = "项目调度运行中：自动任务正在处理";
      } else {
        key = loading ? "loading" : "enabled";
        tip = "项目调度已开启";
      }
      if (nextAtHHMM) tip += " · 下次自动执行 " + nextAtHHMM;
      return { key, label, tip };
    }

    function renderProjectAutoHeaderState(projectId) {
      const btn = projectAutoHeaderBtnNode();
      if (!btn) return;
      const span = btn.querySelector("span");
      const pid = String(projectId || "").trim();
      const states = ["is-disabled", "is-enabled", "is-running", "is-error", "is-loading"];
      states.forEach((c) => btn.classList.remove(c));
      if (!pid || pid === "overview") {
        if (span) span.textContent = "项目调度";
        btn.title = "项目调度与提醒";
        btn.setAttribute("data-auto-state", "disabled");
        return;
      }
      const meta = projectAutoHeaderStateMeta(pid);
      if (meta.key === "enabled") btn.classList.add("is-enabled");
      else if (meta.key === "running") btn.classList.add("is-running");
      else if (meta.key === "error") btn.classList.add("is-error");
      else if (meta.key === "loading") btn.classList.add("is-loading");
      else btn.classList.add("is-disabled");
      if (span) span.textContent = meta.label;
      btn.title = meta.tip;
      btn.setAttribute("data-auto-state", meta.key);
    }

    function renderProjectAutoHeaderOnly(projectId) {
      renderProjectAutoHeaderState(projectId);
      renderProjectRebuildBtn();
    }

    function ensureProjectAutoPolling() {
      if (PROJECT_AUTO.pollTimer) return;
      PROJECT_AUTO.pollTimer = window.setInterval(() => {
        const pid = projectAutoAvailableProjectId();
        if (!pid) return;
        const maxAgeMs = PROJECT_AUTO_UI.open ? 4000 : 12000;
        ensureProjectAutoStatus(pid, { maxAgeMs }).catch(() => {});
      }, 5000);
    }

    function projectRebuildBtnNode() {
      return document.getElementById("projectRebuildBtn");
    }

    function projectRootRevealBtnNode() {
      return document.getElementById("projectRootRevealBtn");
    }

    function resolveProjectRootPath(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return "";
      const proj = projectById(pid);
      const runtimeRoot = String((proj && proj.runtime_root_rel) || "").trim();
      if (runtimeRoot) return runtimeRoot;
      const projectRoot = String((proj && proj.project_root_rel) || "").trim();
      if (projectRoot) return projectRoot;
      const taskRoot = String((proj && proj.task_root_rel) || "").trim();
      if (taskRoot) {
        const compact = taskRoot.replace(/\/+$/, "");
        const markers = ["/任务规划", "/工作开展", "/协同空间/任务规划"];
        for (const marker of markers) {
          if (compact.endsWith(marker)) {
            const base = compact.slice(0, compact.length - marker.length).replace(/\/+$/, "");
            if (base) return base;
          }
        }
        return taskRoot;
      }

      const items = itemsForProject(pid);
      for (const it of items) {
        const p = String((it && it.path) || "").trim();
        if (!p) continue;
        if (p.includes("/任务/")) return p.slice(0, p.indexOf("/任务/"));
        if (p.includes("/需求/")) return p.slice(0, p.indexOf("/需求/"));
        if (p.includes("/问题/")) return p.slice(0, p.indexOf("/问题/"));
        if (p.includes("/反馈/")) return p.slice(0, p.indexOf("/反馈/"));
        if (p.includes("/答复/")) return p.slice(0, p.indexOf("/答复/"));
        if (p.includes("/讨论空间/")) return p.slice(0, p.indexOf("/讨论空间/"));
      }
      return "";
    }

    function renderProjectRootRevealBtn() {
      const btn = projectRootRevealBtnNode();
      if (!btn) return;
      const p = resolveProjectRootPath(STATE.project);
      const hasPath = !!p;
      btn.disabled = !hasPath;
      btn.title = hasPath ? ("打开项目文件夹：" + p) : "当前项目未识别到可打开目录";
      btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!hasPath) return;
        btn.disabled = true;
        try {
          const ok = await apiHealth();
          if (!ok) {
            alert("本机服务不可用，无法打开项目文件夹。");
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
          alert("打开项目文件夹失败：" + String((err && err.message) || err || "未知错误"));
        } finally {
          btn.disabled = !hasPath;
        }
      };
    }

    function defaultProjectAutoPrompt(projectId) {
      const pid = String(projectId || "").trim();
      return "请巡查项目" + (pid ? "「" + pid + "」" : "") + "中进行中的任务，优先识别阻塞、超时未反馈、待确认依赖，并给出简短行动建议。";
    }

    function formatProjectAutoErrorSummary(status) {
      const s = (status && typeof status === "object") ? status : {};
      const chunks = [];
      if (s.auto_dispatch_last_error) chunks.push("任务自动首发：" + String(s.auto_dispatch_last_error));
      if (s.auto_inspection_last_error) chunks.push("定时巡查推进：" + String(s.auto_inspection_last_error));
      if (!s.auto_inspection_last_error && s.scheduler_last_error) chunks.push("巡查引擎：" + String(s.scheduler_last_error));
      if (!s.auto_inspection_last_error && s.reminder_last_error) chunks.push("提醒编排：" + String(s.reminder_last_error));
      if (Array.isArray(s.config_errors) && s.config_errors.length) {
        chunks.push("配置校验：" + s.config_errors.join("，"));
      }
      return chunks.join("；");
    }

    function compactTaskPath(path, keepSegments = 2) {
      const raw = String(path || "").trim();
      if (!raw) return "-";
      const segs = raw.split(/[\\/]+/).filter(Boolean);
      if (!segs.length) return raw;
      if (segs.length <= keepSegments) return segs.join("/");
      return ".../" + segs.slice(-keepSegments).join("/");
    }

    function normalizeProjectAutoRecordStatus(statusRaw) {
      const s = String(statusRaw || "").trim().toLowerCase();
      const mapped = ({
        dispatched: "dispatched",
        dispatching: "dispatched",
        sent: "dispatched",
        done: "effective",
        success: "effective",
        effective: "effective",
        skipped_active: "skipped_active",
        skippedactive: "skipped_active",
        advice_only: "advice_only",
        adviceonly: "advice_only",
        skipped: "skipped",
        error: "error",
        failed: "error",
      })[s] || "unknown";
      const label = ({
        dispatched: "已派发（待回执）",
        effective: "有效执行",
        skipped_active: "跳过（活跃）",
        advice_only: "仅建议（需补执行）",
        skipped: "已跳过",
        error: "错误",
        unknown: "未知",
      })[mapped] || "未知";
      const tone = ({
        dispatched: "warn",
        effective: "good",
        skipped_active: "warn",
        advice_only: "bad",
        skipped: "muted",
        error: "bad",
        unknown: "muted",
      })[mapped] || "muted";
      return { key: mapped, label, tone };
    }

    function projectAutoExecutionActionText(statusKey, reason, summary) {
      const k = String(statusKey || "").trim().toLowerCase();
      const rsn = String(reason || "").trim();
      const sum = String(summary || "").trim();
      if (k === "effective") return "已执行动作并产出证据";
      if (k === "dispatched") return "已触发提醒派发，等待回执";
      if (k === "skipped_active") return "目标会话活跃，本轮跳过";
      if (k === "advice_only") return "仅建议回执，需补执行动作";
      if (k === "skipped") {
        if (rsn === "no_candidate") return "未命中可督办任务，跳过";
        return "本轮跳过（" + (rsn || "条件不满足") + "）";
      }
      if (k === "error") return "执行链路异常，需人工介入";
      return sum ? "执行结果已记录" : "结果待确认";
    }

    function projectAutoEvidencePathText(rec, runId) {
      const r = (rec && typeof rec === "object") ? rec : {};
      const direct = firstNonEmptyText([
        r.feedback_file_path,
        r.feedbackFilePath,
        r.evidence_path,
        r.evidencePath,
        r.feedback_path,
        r.feedbackPath,
      ]);
      if (direct) return String(direct);
      const arr = Array.isArray(r.evidence_paths) ? r.evidence_paths : (Array.isArray(r.evidencePaths) ? r.evidencePaths : []);
      if (arr.length) return String(arr[0] || "");
      const rid = String(runId || "").trim();
      if (rid) return ".runs/" + rid + ".json";
      return "";
    }

    function normalizeProjectAutoRecordOwnership(rec) {
      const r = (rec && typeof rec === "object") ? rec : {};
      const inspectionTaskId = firstNonEmptyText([
        r.inspection_task_id,
        r.inspectionTaskId,
      ]);
      const objectKey = firstNonEmptyText([
        r.inspection_object_key,
        r.inspectionObjectKey,
        r.object_key,
        r.objectKey,
        r.target_object_key,
        r.targetObjectKey,
      ]);
      const objectType = firstNonEmptyText([
        r.inspection_object_type,
        r.inspectionObjectType,
        r.object_type,
        r.objectType,
        r.target_object_type,
        r.targetObjectType,
      ]);
      const objectName = firstNonEmptyText([
        r.inspection_object_name,
        r.inspectionObjectName,
        r.object_name,
        r.objectName,
        r.target_object_name,
        r.targetObjectName,
      ]);
      const normalizedType = String(objectType || "").trim().toLowerCase().replace(/-/g, "_");
      return {
        inspectionTaskId: String(inspectionTaskId || "").trim(),
        objectKey: String(objectKey || "").trim(),
        objectType: normalizedType,
        objectName: String(objectName || "").trim(),
        hasOwner: !!(
          String(inspectionTaskId || "").trim()
          || String(objectKey || "").trim()
          || normalizedType
          || String(objectName || "").trim()
        ),
      };
    }

    function normalizeProjectAutoRecordView(rec) {
      const r = (rec && typeof rec === "object") ? rec : {};
      const ownership = normalizeProjectAutoRecordOwnership(r);
      const statusMeta = normalizeProjectAutoRecordStatus(firstNonEmptyText([
        r.status,
        r.dispatch_state,
        r.dispatchState,
        r.result,
      ]));
      const createdAt = firstNonEmptyText([
        r.created_at,
        r.createdAt,
        r.updated_at,
        r.updatedAt,
        r.ts,
      ]);
      const summary = firstNonEmptyText([
        r.message_summary,
        r.messageSummary,
        r.summary,
      ]) || "（无摘要，后端未返回 message_summary）";
      const targetTaskPath = firstNonEmptyText([
        r.target_task_path,
        r.targetTaskPath,
        r.task_path,
        r.taskPath,
      ]);
      const targetChannel = firstNonEmptyText([
        r.target_channel,
        r.targetChannel,
        r.channel_name,
        r.channelName,
      ]);
      const reason = firstNonEmptyText([
        r.skip_reason,
        r.skipReason,
        r.error,
        r.error_message,
        r.errorMessage,
        r.reason,
      ]);
      const runId = firstNonEmptyText([
        r.run_id,
        r.runId,
        r.dispatch_run_id,
        r.dispatchRunId,
      ]);
      const evidencePath = projectAutoEvidencePathText(r, runId);
      const actionText = projectAutoExecutionActionText(statusMeta.key, reason, summary);
      return {
        statusMeta,
        createdAt,
        summary: String(summary || ""),
        targetTaskPath: String(targetTaskPath || ""),
        targetTaskText: compactTaskPath(targetTaskPath, 3),
        targetChannel: String(targetChannel || ""),
        runId: String(runId || ""),
        evidencePath: String(evidencePath || ""),
        actionText: String(actionText || ""),
        reason: String(reason || ""),
        objectKey: ownership.objectKey,
        objectType: ownership.objectType,
        objectName: ownership.objectName,
        inspectionTaskId: ownership.inspectionTaskId,
        hasOwner: ownership.hasOwner,
      };
    }

    function normalizeHeartbeatHistoryRecordView(rec) {
      const r = (rec && typeof rec === "object") ? rec : {};
      const status = String(firstNonEmptyText([r.status, r.result, r.last_status]) || "").trim().toLowerCase();
      const statusMeta = normalizeProjectAutoRecordStatus(status);
      const triggeredAt = firstNonEmptyText([r.triggered_at, r.triggeredAt, r.created_at, r.createdAt, r.updated_at, r.updatedAt]);
      const trigger = String(firstNonEmptyText([r.trigger, r.trigger_type]) || "manual").trim().toLowerCase();
      const error = String(firstNonEmptyText([r.error, r.error_message, r.errorMessage]) || "").trim();
      const runId = String(firstNonEmptyText([r.run_id, r.runId]) || "").trim();
      const jobId = String(firstNonEmptyText([r.job_id, r.jobId]) || "").trim();
      const activeStatus = String(firstNonEmptyText([r.active_status, r.activeStatus]) || "").trim();
      return {
        statusMeta,
        triggeredAt,
        trigger,
        runId,
        jobId,
        activeStatus,
        error,
        summary: error || ("触发方式：" + trigger + (jobId ? " · job " + shortId(jobId) : "")),
      };
    }

    function buildHeartbeatRecordList(records, opts = {}) {
      const list = Array.isArray(records) ? records : [];
      if (!list.length) {
        return el("div", {
          class: "project-auto-record-empty",
          text: String(opts.emptyText || "当前尚无心跳执行记录。"),
        });
      }
      const wrap = el("div", { class: "project-auto-record-list" });
      list.forEach((row) => {
        const rec = normalizeHeartbeatHistoryRecordView(row);
        const item = el("div", { class: "project-auto-record-item status-" + rec.statusMeta.key });
        const top = el("div", { class: "project-auto-record-top" });
        top.appendChild(chip(rec.statusMeta.label, rec.statusMeta.tone));
        top.appendChild(el("span", { class: "project-auto-record-time", text: formatTsOrDash(rec.triggeredAt) }));
        item.appendChild(top);
        item.appendChild(el("div", {
          class: "project-auto-record-action",
          text: "触发：" + (rec.trigger || "manual") + (rec.activeStatus ? " · 忙碌态：" + rec.activeStatus : ""),
        }));
        item.appendChild(el("div", {
          class: "project-auto-record-summary",
          text: rec.summary,
        }));
        const meta = el("div", { class: "project-auto-record-meta" });
        meta.appendChild(el("span", {
          class: "project-auto-record-meta-item mono",
          text: "job_id：" + (rec.jobId ? shortId(rec.jobId) : "-"),
        }));
        meta.appendChild(el("span", {
          class: "project-auto-record-meta-item mono",
          text: "run_id：" + (rec.runId ? shortId(rec.runId) : "-"),
        }));
        item.appendChild(meta);
        wrap.appendChild(item);
      });
      return wrap;
    }

    function isProtectedInspectionObjectClient(row) {
      const item = (row && typeof row === "object") ? row : {};
      const source = String(item.source || "").trim().toLowerCase();
      return source === "inspection_targets";
    }

    function projectAutoHumanSummary(status, draft) {
      const s = (status && typeof status === "object") ? status : {};
      const d = (draft && typeof draft === "object") ? draft : {};
      const patrolEnabled = !!d.patrolEnabled;
      const intervalMinutes = Number.isFinite(Number(d.intervalMinutes))
        ? Math.max(5, Number(d.intervalMinutes))
        : (Number.isFinite(Number(s.auto_inspection_interval_minutes))
          ? Number(s.auto_inspection_interval_minutes)
          : (Number.isFinite(Number(s.reminder_interval_minutes)) ? Number(s.reminder_interval_minutes) : 30));
      const pieces = [];
      pieces.push("自动巡查" + (patrolEnabled ? "已开启" : "已关闭"));
      if (patrolEnabled) pieces.push("间隔 " + String(intervalMinutes) + " 分钟");
      if (patrolEnabled) {
        const inspectionTasks = normalizeInspectionTaskItemsClient(
          s.inspection_tasks,
          {
            projectId: "",
            channelName: d.channelName,
            sessionId: d.sessionId,
            intervalMinutes: d.intervalMinutes,
            promptText: d.promptText,
            inspectionTargets: d.inspectionTargets,
            autoInspections: d.autoInspections,
          }
        );
        const targets = normalizeInspectionTargetsClient(
          (inspectionTasks[0] && inspectionTasks[0].inspection_targets) || d.inspectionTargets,
          Array.isArray(s.auto_inspection_targets) ? s.auto_inspection_targets : ["scheduled", "in_progress"]
        );
        const labels = targets
          .map((x) => {
            const hit = INSPECTION_TARGET_OPTIONS.find((opt) => opt.value === x);
            return hit ? hit.label : x;
          })
          .filter(Boolean);
        pieces.push("板块 " + inspectionTasks.length + " 个");
        if (labels.length) pieces.push("对象：" + labels.join(" / "));
      }
      if (patrolEnabled && !(s.auto_inspection_last_at || s.scheduler_last_tick_at)) pieces.push("暂无巡查记录");
      return pieces.join(" · ");
    }

    function projectAutoNextInspectionDueText(status, draft, cached) {
      const s = (status && typeof status === "object") ? status : {};
      const d = (draft && typeof draft === "object") ? draft : {};
      const explicit = firstNonEmptyText([
        s.auto_inspection_next_due_at,
        s.auto_inspection_next_at,
        s.autoInspectionNextDueAt,
        s.reminder_next_due_at,
        s.reminderNextDueAt,
      ]);
      if (explicit) return formatTsOrDash(explicit);
      if (!d.patrolEnabled) return "未开启";
      const intervalMinutes = Number.isFinite(Number(d.intervalMinutes))
        ? Math.max(5, Number(d.intervalMinutes))
        : (Number.isFinite(Number(s.auto_inspection_interval_minutes))
          ? Math.max(5, Number(s.auto_inspection_interval_minutes))
          : (Number.isFinite(Number(s.reminder_interval_minutes)) ? Math.max(5, Number(s.reminder_interval_minutes)) : 30));
      const baseTs = firstNonEmptyText([
        s.auto_inspection_last_at,
        s.auto_inspection_last_tick_at,
        s.scheduler_last_tick_at,
        s.reminder_last_tick_at,
        s.reminder_last_sent_at,
        cached && cached.fetchedAt,
      ]);
      const base = parseDateTime(baseTs) || new Date();
      const next = new Date(base.getTime() + intervalMinutes * 60 * 1000);
      if (Number.isNaN(next.getTime())) return "-";
      const pad2 = (n) => String(n).padStart(2, "0");
      return next.getFullYear()
        + "-" + pad2(next.getMonth() + 1)
        + "-" + pad2(next.getDate())
        + " " + pad2(next.getHours())
        + ":" + pad2(next.getMinutes())
        + "（预计）";
    }

    function getProjectAutoChannels(projectId) {
      return unionChannelNames(projectId);
    }

    function getProjectAutoSessions(projectId) {
      return configuredProjectConversations(projectId);
    }

    function sessionIdLooksValid(sessionId) {
      return looksLikeSessionId(String(sessionId || "").trim());
    }

    function pickProjectAutoDefaultChannel(projectId) {
      const names = getProjectAutoChannels(projectId);
      if (!names.length) return "";
      return defaultChannelForProject(projectId) || names[0] || "";
    }

    function pickProjectAutoDefaultSessionId(projectId, channelName) {
      const sessions = getProjectAutoSessions(projectId);
      return pickDefaultConversationSessionId(sessions, channelName || "") || "";
    }

    function hydrateProjectAutoDraftFromStatus(draft, status, projectId) {
      const d = (draft && typeof draft === "object") ? draft : {};
      const s = (status && typeof status === "object") ? status : {};
      const pid = String(projectId || "").trim();
      const taskAutoEnabled = hasTrueish([s.auto_dispatch_enabled, s.task_auto_trigger_enabled]);
      const patrolEnabled = hasTrueish([s.auto_inspection_enabled, s.reminder_enabled, s.scheduler_enabled]);
      const intervalMinutes = Number.isFinite(Number(s.auto_inspection_interval_minutes))
        ? Math.max(5, Number(s.auto_inspection_interval_minutes))
        : (Number.isFinite(Number(s.reminder_interval_minutes))
          ? Math.max(5, Number(s.reminder_interval_minutes))
          : 30);
      const channelName = String(s.auto_inspection_channel_name || "").trim();
      const sessionId = String(s.auto_inspection_session_id || "").trim();
      const promptText = String(s.auto_inspection_prompt_template || "").trim();
      d.taskAutoTriggerEnabled = !!taskAutoEnabled;
      d.patrolEnabled = !!patrolEnabled;
      d.intervalMinutes = intervalMinutes;
      d.channelName = channelName || pickProjectAutoDefaultChannel(pid);
      d.sessionId = sessionId || pickProjectAutoDefaultSessionId(pid, d.channelName);
      d.promptText = promptText || defaultProjectAutoPrompt(pid);
      d.inspectionTargets = normalizeInspectionTargetsClient(
        s.auto_inspection_targets,
        d.patrolEnabled ? ["scheduled", "in_progress"] : []
      );
      d.autoInspections = normalizeAutoInspectionObjectsClient(
        s.auto_inspections,
        Array.isArray(s.auto_inspection_targets) ? s.auto_inspection_targets : ["scheduled", "in_progress"]
      );
      d.inspectionTasks = normalizeInspectionTaskItemsClient(
        s.inspection_tasks,
        {
          projectId: pid,
          channelName: d.channelName,
          sessionId: d.sessionId,
          intervalMinutes: d.intervalMinutes,
          promptText: d.promptText,
          inspectionTargets: d.inspectionTargets,
          autoInspections: d.autoInspections,
        }
      );
      d.activeInspectionTaskId = normalizeInspectionTaskIdClient(s.active_inspection_task_id, "default");
      d._statusHydrated = true;
      d._statusHydratedAt = new Date().toISOString();
      return d;
    }

    function ensureProjectAutoDraft(projectId, status) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      let draft = PROJECT_AUTO.draftByProject[pid];
      const s = (status && typeof status === "object") ? status : null;
      if (!draft) {
        draft = {
          taskAutoTriggerEnabled: false,
          patrolEnabled: false,
          channelName: "",
          sessionId: "",
          intervalMinutes: 30,
          promptText: defaultProjectAutoPrompt(pid),
          inspectionTargets: [],
          autoInspections: [],
          inspectionTasks: [],
          activeInspectionTaskId: "default",
          localOnlyFields: ["taskAutoTriggerEnabled", "channelName", "sessionId", "promptText"],
          _statusHydrated: false,
        };
        if (s) hydrateProjectAutoDraftFromStatus(draft, s, pid);
        PROJECT_AUTO.draftByProject[pid] = draft;
      } else if (!draft._statusHydrated && s) {
        hydrateProjectAutoDraftFromStatus(draft, s, pid);
      }

      const channelOptions = getProjectAutoChannels(pid);
      if (draft.channelName && channelOptions.length && !channelOptions.includes(draft.channelName)) {
        draft.channelName = "";
      }
      if (!draft.channelName) {
        draft.channelName = pickProjectAutoDefaultChannel(pid);
      }
      const sessions = getProjectAutoSessions(pid);
      const inChannelSessions = sessions.filter((x) => {
        const chans = Array.isArray(x && x.channels) ? x.channels : [];
        return !draft.channelName || chans.includes(draft.channelName) || String(x.primaryChannel || "") === String(draft.channelName);
      });
      const allSessionIds = new Set(sessions.map((x) => String((x && x.sessionId) || "").trim()).filter(Boolean));
      const inChannelIds = new Set(inChannelSessions.map((x) => String((x && x.sessionId) || "").trim()).filter(Boolean));
      if (draft.sessionId && ((inChannelIds.size && !inChannelIds.has(draft.sessionId)) || (!inChannelIds.size && !allSessionIds.has(draft.sessionId)))) {
        draft.sessionId = "";
      }
      if (!draft.sessionId) {
        draft.sessionId = pickProjectAutoDefaultSessionId(pid, draft.channelName);
      }
      if (!Number.isFinite(Number(draft.intervalMinutes)) || Number(draft.intervalMinutes) < 5) {
        draft.intervalMinutes = (s && Number.isFinite(Number(s.auto_inspection_interval_minutes)))
          ? Math.max(5, Number(s.auto_inspection_interval_minutes))
          : ((s && Number.isFinite(Number(s.reminder_interval_minutes)))
          ? Math.max(5, Number(s.reminder_interval_minutes))
          : 30);
      }
      if (!String(draft.promptText || "").trim()) {
        draft.promptText = defaultProjectAutoPrompt(pid);
      }
      if (!Array.isArray(draft.inspectionTargets) || !draft.inspectionTargets.length) {
        draft.inspectionTargets = normalizeInspectionTargetsClient(
          draft.inspectionTargets,
          draft.patrolEnabled ? ["scheduled", "in_progress"] : []
        );
      }
      if (!Array.isArray(draft.autoInspections)) {
        draft.autoInspections = normalizeAutoInspectionObjectsClient(
          draft.autoInspections,
          draft.inspectionTargets
        );
      }
      if (!Array.isArray(draft.inspectionTasks)) {
        draft.inspectionTasks = normalizeInspectionTaskItemsClient(
          draft.inspectionTasks,
          {
            projectId: pid,
            channelName: draft.channelName,
            sessionId: draft.sessionId,
            intervalMinutes: draft.intervalMinutes,
            promptText: draft.promptText,
            inspectionTargets: draft.inspectionTargets,
            autoInspections: draft.autoInspections,
          }
        );
      }
      if (!String(draft.activeInspectionTaskId || "").trim()) {
        draft.activeInspectionTaskId = "default";
      }
      return draft;
    }

    function updateProjectAutoDraft(projectId, patch = {}) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      const current = ensureProjectAutoDraft(pid, (PROJECT_AUTO.cache[pid] && PROJECT_AUTO.cache[pid].status) || null);
      if (!current) return null;
      const next = Object.assign({}, current, patch || {});
      PROJECT_AUTO.draftByProject[pid] = next;
      return next;
    }

    function buildProjectAutoSelectField(labelText, selectNode, subText) {
      const row = el("div", { class: "project-auto-field" });
      row.appendChild(el("label", { class: "project-auto-field-label", text: labelText }));
      row.appendChild(selectNode);
      if (subText) row.appendChild(el("div", { class: "project-auto-field-sub", text: subText }));
      return row;
    }

    function buildProjectAutoInputField(labelText, inputNode, subText) {
      const row = el("div", { class: "project-auto-field" });
      row.appendChild(el("label", { class: "project-auto-field-label", text: labelText }));
      row.appendChild(inputNode);
      if (subText) row.appendChild(el("div", { class: "project-auto-field-sub", text: subText }));
      return row;
    }

    function buildProjectAutoSessionOptionLabel(sess) {
      const s = (sess && typeof sess === "object") ? sess : {};
      const alias = String(s.alias || s.displayChannel || s.primaryChannel || "未命名会话").trim();
      const sid = String(s.sessionId || "").trim();
      const cli = String(s.cli_type || "codex").trim() || "codex";
      const model = sessionModelLabel(s.model);
      const channels = Array.isArray(s.channels) ? s.channels.filter(Boolean) : [];
      const suffix = sid ? (" · " + sid.slice(0, 8)) : "";
      const chanPart = channels.length ? (" · " + channels.join(",")) : "";
      return alias + " [" + cli + "/" + model + "]" + chanPart + suffix;
    }

    const HEARTBEAT_PRESET_OPTIONS = [
      ["issue_review", "问题审查"],
      ["work_push", "工作推进"],
      ["team_watch", "团队巡查"],
      ["ops_inspection", "保障巡检"],
      ["acceptance_followup", "待验收催收"],
      ["daily_summary", "每日总结"],
    ];
    const HEARTBEAT_SCHEDULE_OPTIONS = [
      ["interval", "按间隔执行"],
      ["daily", "按日定时执行"],
    ];
    const HEARTBEAT_BUSY_POLICY_OPTIONS = [
      ["run_on_next_idle", "忙碌时顺延"],
      ["skip_if_busy", "忙碌时跳过"],
      ["queue_if_busy", "忙碌时入队"],
    ];
    const HEARTBEAT_WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];

    function normalizeHeartbeatWeekdaysClient(raw) {
      const items = Array.isArray(raw) ? raw : [];
      const picked = [];
      items.forEach((value) => {
        const num = Number(value);
        if (!Number.isFinite(num)) return;
        const weekday = Math.max(1, Math.min(7, Math.round(num)));
        if (!picked.includes(weekday)) picked.push(weekday);
      });
      return picked.length ? picked.sort((a, b) => a - b) : [1, 2, 3, 4, 5];
    }

    function defaultHeartbeatTaskDraft(projectId, taskId = "") {
      const pid = String(projectId || "").trim();
      const channelName = pickProjectAutoDefaultChannel(pid);
      const sessionId = pickProjectAutoDefaultSessionId(pid, channelName);
      const normalizedId = String(taskId || ("heartbeat-" + Date.now())).trim().replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
      return {
        heartbeatTaskId: normalizedId || ("heartbeat-" + Date.now()),
        title: "",
        enabled: true,
        channelName: channelName || "",
        sessionId: sessionId || "",
        presetKey: "ops_inspection",
        promptTemplate: "",
        scheduleType: "interval",
        intervalMinutes: 120,
        dailyTime: "09:30",
        weekdays: [1, 2, 3, 4, 5],
        busyPolicy: "run_on_next_idle",
        maxExecuteCount: 0,
        contextScope: {
          recentTasksLimit: 10,
          recentRunsLimit: 10,
          includeTaskCounts: true,
          includeRecentTasks: true,
          includeRecentRuns: true,
        },
        heartbeatEnabled: true,
        heartbeatScanIntervalSeconds: 30,
        _statusHydrated: true,
      };
    }

    function heartbeatTaskFieldPresent(raw, keys = []) {
      const row = (raw && typeof raw === "object") ? raw : {};
      const list = Array.isArray(keys) ? keys : [];
      return list.some((key) => Object.prototype.hasOwnProperty.call(row, key));
    }

    function heartbeatOptionalNonNegativeNumber(raw, keys = [], opts = {}) {
      const row = (raw && typeof raw === "object") ? raw : {};
      const list = Array.isArray(keys) ? keys : [];
      const emptyAsZero = !!opts.emptyAsZero;
      for (const key of list) {
        if (!Object.prototype.hasOwnProperty.call(row, key)) continue;
        const value = row[key];
        if (value == null || String(value).trim() === "") return emptyAsZero ? 0 : null;
        const num = Number(value);
        if (!Number.isFinite(num)) return emptyAsZero ? 0 : null;
        return Math.max(0, Math.round(num));
      }
      return null;
    }

    function normalizeHeartbeatTaskClient(raw, projectId, defaults = {}) {
      const row = (raw && typeof raw === "object") ? raw : {};
      const base = (defaults && typeof defaults === "object") ? defaults : {};
      const heartbeatTaskId = String(
        firstNonEmptyText([row.heartbeat_task_id, row.heartbeatTaskId, base.heartbeatTaskId])
        || ""
      ).trim();
      const scheduleType = firstNonEmptyText([row.schedule_type, row.scheduleType, base.scheduleType]).toLowerCase();
      const busyPolicy = firstNonEmptyText([row.busy_policy, row.busyPolicy, base.busyPolicy]).toLowerCase();
      const weekdays = normalizeHeartbeatWeekdaysClient(row.weekdays || row.weekDays || base.weekdays);
      const hasMaxExecuteCount = heartbeatTaskFieldPresent(row, ["max_execute_count", "maxExecuteCount"])
        || heartbeatTaskFieldPresent(base, ["max_execute_count", "maxExecuteCount", "maxExecuteCount"]);
      const hasExecutedCount = heartbeatTaskFieldPresent(row, ["executed_count", "executedCount"])
        || heartbeatTaskFieldPresent(base, ["executed_count", "executedCount", "executedCount"]);
      const hasRemainingExecuteCount = heartbeatTaskFieldPresent(row, ["remaining_execute_count", "remainingExecuteCount"])
        || heartbeatTaskFieldPresent(base, ["remaining_execute_count", "remainingExecuteCount", "remainingExecuteCount"]);
      const maxExecuteCount = hasMaxExecuteCount
        ? (heartbeatOptionalNonNegativeNumber(row, ["max_execute_count", "maxExecuteCount"], { emptyAsZero: true })
          ?? heartbeatOptionalNonNegativeNumber(base, ["max_execute_count", "maxExecuteCount", "maxExecuteCount"], { emptyAsZero: true }))
        : null;
      const executedCount = hasExecutedCount
        ? (heartbeatOptionalNonNegativeNumber(row, ["executed_count", "executedCount"])
          ?? heartbeatOptionalNonNegativeNumber(base, ["executed_count", "executedCount", "executedCount"]))
        : null;
      const remainingExecuteCount = hasRemainingExecuteCount
        ? (heartbeatOptionalNonNegativeNumber(row, ["remaining_execute_count", "remainingExecuteCount"])
          ?? heartbeatOptionalNonNegativeNumber(base, ["remaining_execute_count", "remainingExecuteCount", "remainingExecuteCount"]))
        : null;
      const lastCountedJobId = firstNonEmptyText([row.last_counted_job_id, row.lastCountedJobId, base.last_counted_job_id, base.lastCountedJobId]);
      const autoDisabledReason = firstNonEmptyText([row.auto_disabled_reason, row.autoDisabledReason, base.auto_disabled_reason, base.autoDisabledReason]).toLowerCase();
      const autoDisabledAt = firstNonEmptyText([row.auto_disabled_at, row.autoDisabledAt, base.auto_disabled_at, base.autoDisabledAt]);
      const rawSourceScope = firstNonEmptyText([row.source_scope, row.sourceScope]).toLowerCase();
      const inferredSessionId = firstNonEmptyText([row.session_id, row.sessionId, base.session_id, base.sessionId]).trim();
      const sourceScope = rawSourceScope === "session"
        ? "session"
        : (rawSourceScope === "project" ? "project" : (inferredSessionId ? "session" : "project"));
      const hasExecuteLimitMeta = !!(
        _coerceBoolClient(row.has_execute_limit_meta ?? base.has_execute_limit_meta, false)
        || hasMaxExecuteCount
        || hasExecutedCount
        || hasRemainingExecuteCount
        || lastCountedJobId
        || autoDisabledReason
        || autoDisabledAt
      );
      return {
        heartbeat_task_id: heartbeatTaskId,
        title: firstNonEmptyText([row.title, base.title]) || heartbeatTaskId || "心跳任务",
        enabled: _coerceBoolClient(row.enabled, base.enabled == null ? true : base.enabled),
        ready: _coerceBoolClient(row.ready, true),
        channel_name: firstNonEmptyText([row.channel_name, row.channelName, base.channelName]),
        session_id: firstNonEmptyText([row.session_id, row.sessionId, base.sessionId]),
        preset_key: firstNonEmptyText([row.preset_key, row.presetKey, base.presetKey]).toLowerCase() || "ops_inspection",
        prompt_template: firstNonEmptyText([row.prompt_template, row.promptTemplate, base.promptTemplate]),
        effective_prompt_template: firstNonEmptyText([row.effective_prompt_template, row.effectivePromptTemplate, row.prompt_template, row.promptTemplate, base.promptTemplate]),
        schedule_type: (scheduleType === "daily" ? "daily" : "interval"),
        interval_minutes: Math.max(5, Number(firstNonEmptyText([row.interval_minutes, row.intervalMinutes, base.intervalMinutes]) || 120)),
        daily_time: firstNonEmptyText([row.daily_time, row.dailyTime, base.dailyTime]) || "09:30",
        weekdays,
        busy_policy: HEARTBEAT_BUSY_POLICY_OPTIONS.some((x) => x[0] === busyPolicy) ? busyPolicy : "run_on_next_idle",
        context_scope: {
          recent_tasks_limit: Math.max(0, Number(firstNonEmptyText([
            row.context_scope && row.context_scope.recent_tasks_limit,
            row.context_scope && row.context_scope.recentTasksLimit,
            base.contextScope && base.contextScope.recentTasksLimit,
          ]) || 10)),
          recent_runs_limit: Math.max(0, Number(firstNonEmptyText([
            row.context_scope && row.context_scope.recent_runs_limit,
            row.context_scope && row.context_scope.recentRunsLimit,
            base.contextScope && base.contextScope.recentRunsLimit,
          ]) || 10)),
          include_task_counts: _coerceBoolClient(
            row.context_scope && (row.context_scope.include_task_counts ?? row.context_scope.includeTaskCounts),
            true
          ),
          include_recent_tasks: _coerceBoolClient(
            row.context_scope && (row.context_scope.include_recent_tasks ?? row.context_scope.includeRecentTasks),
            true
          ),
          include_recent_runs: _coerceBoolClient(
            row.context_scope && (row.context_scope.include_recent_runs ?? row.context_scope.includeRecentRuns),
            true
          ),
        },
        next_due_at: firstNonEmptyText([row.next_due_at, row.nextDueAt]),
        last_triggered_at: firstNonEmptyText([row.last_triggered_at, row.lastTriggeredAt]),
        last_status: firstNonEmptyText([row.last_status, row.lastStatus]).toLowerCase(),
        last_result: firstNonEmptyText([row.last_result, row.lastResult]).toLowerCase(),
        last_error: firstNonEmptyText([row.last_error, row.lastError]),
        last_job_id: firstNonEmptyText([row.last_job_id, row.lastJobId]),
        last_job_status: firstNonEmptyText([row.last_job_status, row.lastJobStatus]).toLowerCase(),
        last_run_id: firstNonEmptyText([row.last_run_id, row.lastRunId]),
        last_busy_status: firstNonEmptyText([row.last_busy_status, row.lastBusyStatus]).toLowerCase(),
        pending_job: _coerceBoolClient(row.pending_job, false),
        history_count: Math.max(0, Number(firstNonEmptyText([row.history_count, row.historyCount]) || 0)),
        updated_at: firstNonEmptyText([row.updated_at, row.updatedAt]),
        max_execute_count: maxExecuteCount,
        executed_count: executedCount,
        remaining_execute_count: remainingExecuteCount,
        last_counted_job_id: lastCountedJobId,
        auto_disabled_reason: autoDisabledReason,
        auto_disabled_at: autoDisabledAt,
        has_execute_limit_meta: hasExecuteLimitMeta,
        source_scope: sourceScope,
        source: firstNonEmptyText([row.source, "heartbeat_tasks"]),
        project_id: String(projectId || "").trim(),
      };
    }

    function normalizeHeartbeatTaskItemsClient(items, projectId, meta = {}) {
      const list = Array.isArray(items) ? items : [];
      return list
        .map((row) => normalizeHeartbeatTaskClient(row, projectId, meta))
        .filter((row) => !!row.heartbeat_task_id);
    }

    function heartbeatTaskKey(projectId, heartbeatTaskId) {
      const pid = String(projectId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      return pid && tid ? (pid + ":" + tid) : "";
    }

    function ensureHeartbeatTaskDraft(projectId, meta = {}, tasks = []) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      let draft = PROJECT_AUTO.heartbeatDraftByProject[pid];
      if (!draft) {
        const firstTask = Array.isArray(tasks) && tasks.length ? tasks[0] : null;
        draft = defaultHeartbeatTaskDraft(pid, firstTask && firstTask.heartbeat_task_id);
        if (firstTask) {
          draft = Object.assign(draft, {
            heartbeatTaskId: firstTask.heartbeat_task_id,
            title: firstTask.title,
            enabled: !!firstTask.enabled,
            channelName: firstTask.channel_name || draft.channelName,
            sessionId: firstTask.session_id || draft.sessionId,
            presetKey: firstTask.preset_key || draft.presetKey,
            promptTemplate: firstTask.prompt_template || "",
            scheduleType: firstTask.schedule_type || draft.scheduleType,
            intervalMinutes: firstTask.interval_minutes || draft.intervalMinutes,
            dailyTime: firstTask.daily_time || draft.dailyTime,
            weekdays: normalizeHeartbeatWeekdaysClient(firstTask.weekdays),
            busyPolicy: firstTask.busy_policy || draft.busyPolicy,
            contextScope: {
              recentTasksLimit: Number(firstTask.context_scope && firstTask.context_scope.recent_tasks_limit) || draft.contextScope.recentTasksLimit,
              recentRunsLimit: Number(firstTask.context_scope && firstTask.context_scope.recent_runs_limit) || draft.contextScope.recentRunsLimit,
              includeTaskCounts: _coerceBoolClient(firstTask.context_scope && firstTask.context_scope.include_task_counts, true),
              includeRecentTasks: _coerceBoolClient(firstTask.context_scope && firstTask.context_scope.include_recent_tasks, true),
              includeRecentRuns: _coerceBoolClient(firstTask.context_scope && firstTask.context_scope.include_recent_runs, true),
            },
          });
        }
        PROJECT_AUTO.heartbeatDraftByProject[pid] = draft;
      }
      if ("enabled" in meta) draft.heartbeatEnabled = !!meta.enabled;
      if ("scan_interval_seconds" in meta || "scanIntervalSeconds" in meta) {
        draft.heartbeatScanIntervalSeconds = Math.max(20, Number(firstNonEmptyText([meta.scan_interval_seconds, meta.scanIntervalSeconds]) || 30));
      }
      const channels = getProjectAutoChannels(pid);
      if (draft.channelName && channels.length && !channels.includes(draft.channelName)) draft.channelName = "";
      if (!draft.channelName) draft.channelName = pickProjectAutoDefaultChannel(pid);
      const sessionId = String(draft.sessionId || "").trim();
      if (!sessionId || !sessionIdLooksValid(sessionId)) {
        draft.sessionId = pickProjectAutoDefaultSessionId(pid, draft.channelName);
      }
      return draft;
    }

    function updateHeartbeatTaskDraft(projectId, patch = {}) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      const cached = PROJECT_AUTO.cache[pid] || {};
      const draft = ensureHeartbeatTaskDraft(pid, cached.heartbeatMeta || {}, cached.heartbeatTasks || []);
      if (!draft) return null;
      const next = Object.assign({}, draft, patch || {});
      if (patch && patch.contextScope && typeof patch.contextScope === "object") {
        next.contextScope = Object.assign({}, draft.contextScope || {}, patch.contextScope);
      }
      PROJECT_AUTO.heartbeatDraftByProject[pid] = next;
      return next;
    }

    function heartbeatTaskDraftFromItem(projectId, task, meta = {}) {
      const pid = String(projectId || "").trim();
      const row = (task && typeof task === "object") ? task : {};
      const draft = defaultHeartbeatTaskDraft(pid, row.heartbeat_task_id || row.heartbeatTaskId || "");
      draft.heartbeatTaskId = String(row.heartbeat_task_id || row.heartbeatTaskId || draft.heartbeatTaskId).trim();
      draft.title = String(row.title || draft.title || "").trim();
      draft.enabled = _coerceBoolClient(row.enabled, true);
      draft.channelName = String(row.channel_name || row.channelName || draft.channelName).trim();
      draft.sessionId = String(row.session_id || row.sessionId || draft.sessionId).trim();
      draft.presetKey = String(row.preset_key || row.presetKey || draft.presetKey).trim();
      draft.promptTemplate = String(row.prompt_template || row.promptTemplate || "").trim();
      draft.scheduleType = String(row.schedule_type || row.scheduleType || draft.scheduleType).trim() === "daily" ? "daily" : "interval";
      draft.intervalMinutes = Math.max(5, Number(row.interval_minutes || row.intervalMinutes || draft.intervalMinutes || 120));
      draft.dailyTime = String(row.daily_time || row.dailyTime || draft.dailyTime || "09:30").trim() || "09:30";
      draft.weekdays = normalizeHeartbeatWeekdaysClient(row.weekdays || row.weekDays || draft.weekdays);
      draft.busyPolicy = String(row.busy_policy || row.busyPolicy || draft.busyPolicy).trim() || "run_on_next_idle";
      draft.maxExecuteCount = Math.max(0, Number(
        heartbeatOptionalNonNegativeNumber(row, ["max_execute_count", "maxExecuteCount"], { emptyAsZero: true })
        ?? draft.maxExecuteCount
        ?? 0
      ));
      draft.contextScope = {
        recentTasksLimit: Math.max(0, Number(row.context_scope && (row.context_scope.recent_tasks_limit ?? row.context_scope.recentTasksLimit) || draft.contextScope.recentTasksLimit || 10)),
        recentRunsLimit: Math.max(0, Number(row.context_scope && (row.context_scope.recent_runs_limit ?? row.context_scope.recentRunsLimit) || draft.contextScope.recentRunsLimit || 10)),
        includeTaskCounts: _coerceBoolClient(row.context_scope && (row.context_scope.include_task_counts ?? row.context_scope.includeTaskCounts), true),
        includeRecentTasks: _coerceBoolClient(row.context_scope && (row.context_scope.include_recent_tasks ?? row.context_scope.includeRecentTasks), true),
        includeRecentRuns: _coerceBoolClient(row.context_scope && (row.context_scope.include_recent_runs ?? row.context_scope.includeRecentRuns), true),
      };
      draft.heartbeatEnabled = _coerceBoolClient(meta.enabled, true);
      draft.heartbeatScanIntervalSeconds = Math.max(20, Number(meta.scan_interval_seconds || meta.scanIntervalSeconds || draft.heartbeatScanIntervalSeconds || 30));
      return draft;
    }

    function heartbeatPresetLabel(key) {
      const found = HEARTBEAT_PRESET_OPTIONS.find((row) => row[0] === String(key || "").trim().toLowerCase());
      return found ? found[1] : (String(key || "").trim() || "-");
    }

    function heartbeatScheduleSummary(task) {
      const row = (task && typeof task === "object") ? task : {};
      if (String(row.schedule_type || "").trim() === "daily") {
        const weekdays = normalizeHeartbeatWeekdaysClient(row.weekdays).map((n) => "周" + HEARTBEAT_WEEKDAY_LABELS[(n - 1 + 7) % 7]).join("、");
        return "每日 " + (row.daily_time || "09:30") + (weekdays ? " · " + weekdays : "");
      }
      return "每 " + Math.max(5, Number(row.interval_minutes || 120)) + " 分钟";
    }

    function heartbeatBusyPolicyLabel(policy) {
      const key = String(policy || "").trim().toLowerCase();
      const found = HEARTBEAT_BUSY_POLICY_OPTIONS.find((row) => row[0] === key);
      return found ? found[1] : (key || "-");
    }

    function heartbeatTaskStateLabel(task) {
      const limitMeta = heartbeatTaskExecuteLimitMeta(task);
      if (limitMeta.reached) return "已达上限自动关闭";
      const status = String((task && (task.last_status || task.last_job_status || task.last_result || task.result || task.status)) || "").trim().toLowerCase();
      return ({
        disabled: "已关闭",
        idle: "空闲",
        invalid_config: "配置无效",
        dispatched: "已派发",
        scheduled: "已入队",
        created: "已创建",
        retry_waiting: "等待重试",
        waiting_idle: "等待空闲",
        skipped_active: "忙碌跳过",
        error: "异常",
        done: "已完成",
        running: "执行中",
      })[status] || (status || "待执行");
    }

    function heartbeatTaskStateTone(task) {
      const limitMeta = heartbeatTaskExecuteLimitMeta(task);
      if (limitMeta.reached) return "warn";
      const status = String((task && (task.last_status || task.last_job_status || task.last_result || task.result || task.status)) || "").trim().toLowerCase();
      if (["error", "invalid_config"].includes(status)) return "bad";
      if (["dispatched", "scheduled", "created", "retry_waiting", "waiting_idle", "running"].includes(status)) return "warn";
      if (["disabled"].includes(status)) return "muted";
      return "good";
    }

    function heartbeatTaskExecuteLimitMeta(task) {
      const row = (task && typeof task === "object") ? task : {};
      const hasMeta = _coerceBoolClient(row.has_execute_limit_meta, false)
        || row.max_execute_count != null
        || row.executed_count != null
        || row.remaining_execute_count != null
        || String(row.auto_disabled_reason || "").trim()
        || String(row.auto_disabled_at || "").trim();
      const maxExecuteCount = Number.isFinite(Number(row.max_execute_count)) ? Math.max(0, Number(row.max_execute_count)) : null;
      const executedCount = Number.isFinite(Number(row.executed_count)) ? Math.max(0, Number(row.executed_count)) : null;
      const remainingExecuteCount = Number.isFinite(Number(row.remaining_execute_count)) ? Math.max(0, Number(row.remaining_execute_count)) : null;
      const autoDisabledReason = String(row.auto_disabled_reason || "").trim().toLowerCase();
      const autoDisabledAt = String(row.auto_disabled_at || "").trim();
      const reached = autoDisabledReason === "max_execute_count_reached"
        || !!(maxExecuteCount != null && maxExecuteCount > 0 && remainingExecuteCount === 0 && !_coerceBoolClient(row.enabled, true));
      return {
        hasMeta: !!hasMeta,
        maxExecuteCount,
        executedCount,
        remainingExecuteCount,
        lastCountedJobId: String(row.last_counted_job_id || "").trim(),
        autoDisabledReason,
        autoDisabledAt,
        reached,
      };
    }

    function heartbeatTaskExecuteLimitInlineText(task) {
      const meta = heartbeatTaskExecuteLimitMeta(task);
      if (!meta.hasMeta) return "";
      if (meta.reached) {
        if (meta.maxExecuteCount != null && meta.maxExecuteCount > 0 && meta.executedCount != null) {
          return "已执行 " + meta.executedCount + " / " + meta.maxExecuteCount + "，已达上限自动关闭";
        }
        if (meta.maxExecuteCount != null && meta.maxExecuteCount > 0) {
          return "已达 " + meta.maxExecuteCount + " 次上限，任务已自动关闭";
        }
        return "已达上限自动关闭";
      }
      if (meta.maxExecuteCount === 0) {
        return meta.executedCount != null
          ? ("最大执行次数：不限，已执行 " + meta.executedCount + " 次")
          : "最大执行次数：不限";
      }
      if (meta.maxExecuteCount != null && meta.maxExecuteCount > 0) {
        if (meta.executedCount != null && meta.remainingExecuteCount != null) {
          return "已执行 " + meta.executedCount + " / " + meta.maxExecuteCount + "，剩余 " + meta.remainingExecuteCount + " 次";
        }
        if (meta.executedCount != null) {
          return "已执行 " + meta.executedCount + " / " + meta.maxExecuteCount;
        }
        return "最大执行次数：" + meta.maxExecuteCount + " 次";
      }
      if (meta.executedCount != null && meta.remainingExecuteCount != null) {
        return "已执行 " + meta.executedCount + " 次，剩余 " + meta.remainingExecuteCount + " 次";
      }
      if (meta.executedCount != null) return "已执行 " + meta.executedCount + " 次";
      return "执行次数状态待回传";
    }

    function sessionHeartbeatLatestTriggeredAt(tasks = [], summary = null) {
      const picked = firstNonEmptyText([
        summary && (summary.latest_triggered_at || summary.latestTriggeredAt),
        ...((Array.isArray(tasks) ? tasks : []).map((task) => firstNonEmptyText([task.last_triggered_at, task.updated_at]))),
      ]);
      return String(picked || "").trim();
    }

    function sessionHeartbeatNextDueAt(tasks = [], summary = null) {
      const candidates = [];
      if (summary && (summary.next_due_at || summary.nextDueAt)) candidates.push(String(summary.next_due_at || summary.nextDueAt));
      (Array.isArray(tasks) ? tasks : []).forEach((task) => {
        const val = String(task && task.next_due_at || "").trim();
        if (val) candidates.push(val);
      });
      const valid = candidates
        .map((text) => ({ text, ts: Date.parse(text) }))
        .filter((row) => Number.isFinite(row.ts))
        .sort((a, b) => a.ts - b.ts);
      return valid.length ? valid[0].text : "";
    }

    function openConversationHeartbeatTaskEditor(task = null, mode = "edit") {
      const heartbeatMeta = SESSION_INFO_UI.heartbeatMeta || normalizeSessionHeartbeatMeta({}, []);
      SESSION_INFO_UI.heartbeatDraft = task
        ? buildSessionHeartbeatTaskDraft(task, heartbeatMeta)
        : defaultSessionHeartbeatTaskDraft(SESSION_INFO_UI.base || {});
      SESSION_INFO_UI.heartbeatTaskEditorOpen = true;
      SESSION_INFO_UI.heartbeatTaskEditorMode = String(mode || "edit").trim() === "history" ? "history" : "edit";
      SESSION_INFO_UI.heartbeatHistoryTaskId = String(
        (task && task.heartbeat_task_id)
        || (SESSION_INFO_UI.heartbeatDraft && SESSION_INFO_UI.heartbeatDraft.heartbeatTaskId)
        || ""
      ).trim();
      renderConversationSessionInfoModal();
    }

    function closeConversationHeartbeatTaskEditor() {
      SESSION_INFO_UI.heartbeatTaskEditorOpen = false;
      SESSION_INFO_UI.heartbeatTaskEditorMode = "edit";
      renderConversationSessionInfoModal();
    }

    function buildProjectAutoConfigCard(opts = {}) {
      const cardClass = [
        "project-auto-card",
        String(opts.kind || "").trim(),
        String(opts.className || "").trim(),
      ].filter(Boolean).join(" ");
      const card = el("div", { class: cardClass });
      const top = el("div", { class: "project-auto-card-top" });
      const textWrap = el("div", { class: "project-auto-card-text" });
      textWrap.appendChild(el("div", { class: "project-auto-card-title", text: String(opts.title || "") }));
      textWrap.appendChild(el("div", { class: "project-auto-card-desc", text: String(opts.desc || "") }));
      top.appendChild(textWrap);

      const right = el("div", { class: "project-auto-switch-wrap" });
      const chips = Array.isArray(opts.statusChips) ? opts.statusChips : [];
      chips.forEach((c) => {
        if (!c || !c.text) return;
        right.appendChild(chip(String(c.text), String(c.tone || "muted")));
      });
      top.appendChild(right);
      card.appendChild(top);

      if (opts.topControlNode) {
        card.appendChild(opts.topControlNode);
      }

      const topFacts = Array.isArray(opts.topFacts) ? opts.topFacts : [];
      if (topFacts.length) {
        const facts = el("div", { class: "project-auto-topfacts" });
        topFacts.forEach((row) => {
          if (!Array.isArray(row) || row.length < 2) return;
          const k = String(row[0] || "").trim();
          const v = String(row[1] == null ? "" : row[1]).trim();
          if (!k) return;
          const item = el("div", { class: "project-auto-topfact-row" });
          item.appendChild(el("span", { class: "k", text: k }));
          item.appendChild(el("span", { class: "v", text: v || "-" }));
          facts.appendChild(item);
        });
        if (facts.childNodes.length) card.appendChild(facts);
      }

      if (opts.statusLine) {
        card.appendChild(el("div", { class: "project-auto-card-statusline", text: String(opts.statusLine) }));
      }
      if (opts.note) {
        card.appendChild(el("div", { class: "project-auto-card-note", text: String(opts.note) }));
      }
      if (opts.bodyNode) {
        const body = el("div", { class: "project-auto-card-body" });
        body.appendChild(opts.bodyNode);
        card.appendChild(body);
      }

      const extraRows = Array.isArray(opts.extraRows) ? opts.extraRows : [];
      if (extraRows.length) {
        const meta = el("div", { class: "project-auto-card-meta" });
        extraRows.forEach((row) => {
          if (!Array.isArray(row) || row.length < 2) return;
          const k = String(row[0] || "").trim();
          const v = String(row[1] == null ? "" : row[1]).trim();
          if (!k) return;
          const item = el("div", { class: "project-auto-meta-row" });
          item.appendChild(el("span", { class: "project-auto-meta-k", text: k }));
          item.appendChild(el("span", { class: "project-auto-meta-v", text: v || "-" }));
          meta.appendChild(item);
        });
        card.appendChild(meta);
      }
      return card;
    }

    function buildProjectAutoSliderToggle(opts = {}) {
      const checked = !!opts.checked;
      const disabled = !!opts.disabled;
      const titleOn = String(opts.titleOn || "已开启");
      const titleOff = String(opts.titleOff || "已关闭");
      const subOn = String(opts.subOn || "");
      const subOff = String(opts.subOff || "");
      const extraLine = String(opts.extraLine || "").trim();
      const onToggle = typeof opts.onToggle === "function" ? opts.onToggle : null;

      const bar = el("div", { class: "project-auto-switch-bar" + (checked ? " on" : "") + (disabled ? " disabled" : "") });
      const info = el("div", { class: "project-auto-switch-info" });
      info.appendChild(el("div", { class: "project-auto-switch-title", text: checked ? titleOn : titleOff }));
      const sub = checked ? subOn : subOff;
      if (sub) info.appendChild(el("div", { class: "project-auto-switch-sub", text: sub }));
      if (extraLine) info.appendChild(el("div", { class: "project-auto-switch-extra", text: extraLine }));
      bar.appendChild(info);

      const btn = el("button", {
        type: "button",
        class: "project-auto-slider" + (checked ? " on" : ""),
        role: "switch",
        "aria-checked": checked ? "true" : "false",
        "aria-label": String(opts.ariaLabel || "开关"),
      });
      btn.disabled = disabled;
      btn.appendChild(el("span", { class: "project-auto-slider-knob", "aria-hidden": "true" }));
      if (!disabled && onToggle) {
        btn.addEventListener("click", () => onToggle(!checked));
      }
      bar.appendChild(btn);
      return bar;
    }

    function projectAutoCloseBtnNode() {
      return document.getElementById("projectAutoCloseBtn");
    }

    function renderProjectRebuildBtn() {
      const btn = projectRebuildBtnNode();
      if (!btn) return;
      const span = btn.querySelector("span");
      const pid = projectAutoAvailableProjectId();
      if (!pid) {
        btn.style.display = "none";
        btn.disabled = true;
        btn.classList.remove("active");
        if (span) span.textContent = "刷新看板";
        return;
      }
      btn.style.display = "";
      btn.disabled = !!PROJECT_REBUILD_UI.loading;
      btn.classList.toggle("active", !!PROJECT_REBUILD_UI.loading);
      if (span) span.textContent = PROJECT_REBUILD_UI.loading ? "重建中..." : "刷新看板";
    }

    async function triggerProjectDashboardRebuild() {
      const pid = projectAutoAvailableProjectId();
      if (!pid) {
        alert("请先选择具体项目后再刷新看板。");
        return;
      }
      if (PROJECT_REBUILD_UI.loading) return;
      PROJECT_REBUILD_UI.loading = true;
      PROJECT_REBUILD_UI.lastError = "";
      renderProjectRebuildBtn();
      if (typeof render === "function") render();
      let reloadScheduled = false;
      try {
        const resp = await fetch("/api/dashboard/rebuild", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ project_id: pid }),
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const payload = await resp.json().catch(() => ({}));
        PROJECT_REBUILD_UI.lastAt = String(payload && payload.rebuilt_at || "").trim() || new Date().toISOString();
        reloadScheduled = true;
        setTimeout(() => location.reload(), 120);
      } catch (e) {
        PROJECT_REBUILD_UI.lastError = String(e && e.message ? e.message : "重建失败");
        alert("刷新看板失败：" + PROJECT_REBUILD_UI.lastError);
      } finally {
        if (!reloadScheduled) PROJECT_REBUILD_UI.loading = false;
        renderProjectRebuildBtn();
        if (typeof render === "function") render();
      }
    }

    function projectAutoAvailableProjectId() {
      const pid = String(STATE.project || "").trim();
      if (!pid || pid === "overview") return "";
      return pid;
    }

    function projectAutoRecordsByProjectId(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      const cached = PROJECT_AUTO.cache[pid];
      return (cached && Array.isArray(cached.records)) ? cached.records : [];
    }

    function buildProjectAutoRecordList(records, opts = {}) {
      const list = Array.isArray(records) ? records : [];
      const limitRaw = Number(opts.limit);
      const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? Math.floor(limitRaw) : 0;
      const renderItems = limit > 0 ? list.slice(0, limit) : list.slice();
      const emptyText = String(opts.emptyText || "当前尚无巡查记录。");
      if (!renderItems.length) {
        return el("div", {
          class: "project-auto-record-empty",
          text: emptyText,
        });
      }
      const wrap = el("div", { class: "project-auto-record-list" });
      renderItems.forEach((rec) => {
        const r = normalizeProjectAutoRecordView(rec);
        const row = el("div", { class: "project-auto-record-item status-" + r.statusMeta.key });
        const top = el("div", { class: "project-auto-record-top" });
        top.appendChild(chip(r.statusMeta.label, r.statusMeta.tone));
        top.appendChild(el("span", { class: "project-auto-record-time", text: formatTsOrDash(r.createdAt) }));
        row.appendChild(top);
        row.appendChild(el("div", {
          class: "project-auto-record-action",
          text: "执行动作：" + r.actionText,
        }));
        row.appendChild(el("div", {
          class: "project-auto-record-summary",
          text: r.summary,
        }));
        const meta = el("div", { class: "project-auto-record-meta" });
        meta.appendChild(el("span", {
          class: "project-auto-record-meta-item mono",
          text: "板块：" + (r.inspectionTaskId || "-"),
        }));
        if (r.targetTaskPath) {
          const taskBtn = el("button", {
            type: "button",
            class: "project-auto-record-meta-item action mono",
            text: "目标任务：" + r.targetTaskText,
            title: "点击复制任务路径：" + r.targetTaskPath,
          });
          taskBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            copyText(r.targetTaskPath);
            toast("已复制任务路径");
          });
          meta.appendChild(taskBtn);
        } else {
          meta.appendChild(el("span", {
            class: "project-auto-record-meta-item mono",
            text: "目标任务：-",
          }));
        }
        meta.appendChild(el("span", {
          class: "project-auto-record-meta-item",
          text: "目标通道：" + (r.targetChannel || "-"),
        }));
        if (r.runId) {
          const runBtn = el("button", {
            type: "button",
            class: "project-auto-record-meta-item action mono",
            text: "run_id：" + shortId(r.runId),
            title: "点击复制 run_id：" + r.runId,
          });
          runBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            copyText(r.runId);
            toast("已复制 run_id");
          });
          meta.appendChild(runBtn);
        } else {
          meta.appendChild(el("span", {
            class: "project-auto-record-meta-item mono",
            text: "run_id：-",
          }));
        }
        if (r.evidencePath) {
          const evidenceBtn = el("button", {
            type: "button",
            class: "project-auto-record-meta-item action mono",
            text: "证据路径：" + compactTaskPath(r.evidencePath, 2),
            title: "点击复制证据路径：" + r.evidencePath,
          });
          evidenceBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            copyText(r.evidencePath);
            toast("已复制证据路径");
          });
          meta.appendChild(evidenceBtn);
        } else {
          meta.appendChild(el("span", {
            class: "project-auto-record-meta-item mono",
            text: "证据路径：-",
          }));
        }
        row.appendChild(meta);
        if (r.reason) {
          row.appendChild(el("div", { class: "project-auto-record-reason", text: "原因：" + r.reason }));
        }
        wrap.appendChild(row);
      });
      return wrap;
    }

    function closeProjectAutoRecordDrawer() {
      const mask = projectAutoRecordDrawerMaskNode();
      if (mask) mask.classList.remove("show");
      PROJECT_AUTO_UI.recordDrawerOpen = false;
      PROJECT_AUTO_UI.recordDrawerProjectId = "";
      PROJECT_AUTO_UI.recordDrawerInspectionTaskId = "";
      PROJECT_AUTO_UI.recordDrawerObjectKey = "";
      PROJECT_AUTO_UI.recordDrawerObjectType = "";
      PROJECT_AUTO_UI.recordDrawerObjectName = "";
      PROJECT_AUTO_UI.recordDrawerFallbackAll = false;
      PROJECT_AUTO_UI.recordDrawerMode = "inspection";
      PROJECT_AUTO_UI.heartbeatHistoryTaskId = "";
      return true;
    }

    function renderProjectAutoRecordDrawer(projectId) {
      const mask = projectAutoRecordDrawerMaskNode();
      const sub = projectAutoRecordDrawerSubNode();
      const listNode = projectAutoRecordDrawerListNode();
      if (!mask || !sub || !listNode) return;
      const pid = String(projectId || PROJECT_AUTO_UI.recordDrawerProjectId || projectAutoAvailableProjectId()).trim();
      if (!PROJECT_AUTO_UI.recordDrawerOpen || !pid || pid === "overview") {
        mask.classList.remove("show");
        return;
      }
      if (String(PROJECT_AUTO_UI.recordDrawerMode || "inspection") === "heartbeat") {
        const heartbeatTaskId = String(PROJECT_AUTO_UI.heartbeatHistoryTaskId || "").trim();
        const key = heartbeatTaskKey(pid, heartbeatTaskId);
        const historyPack = key ? (PROJECT_AUTO.heartbeatHistoryByTask[key] || null) : null;
        const loading = key ? !!PROJECT_AUTO.heartbeatHistoryLoadingByTask[key] : false;
        const historyErr = key ? String(PROJECT_AUTO.heartbeatHistoryErrorByTask[key] || "").trim() : "";
        const records = historyPack && Array.isArray(historyPack.items) ? historyPack.items : [];
        const taskName = String(PROJECT_AUTO_UI.recordDrawerHeartbeatTaskName || heartbeatTaskId || "心跳任务").trim();
        sub.textContent = loading
          ? ("心跳任务：" + taskName + " · 历史加载中...")
          : ("心跳任务：" + taskName + " · 共 " + records.length + " 条" + (historyErr ? " · " + historyErr : ""));
        listNode.innerHTML = "";
        if (historyErr) {
          listNode.appendChild(el("div", { class: "project-auto-error", text: "心跳历史读取失败：" + historyErr }));
        }
        listNode.appendChild(buildHeartbeatRecordList(records, {
          emptyText: loading ? "心跳历史加载中..." : "当前尚无心跳执行记录。",
        }));
        mask.classList.add("show");
        return;
      }
      PROJECT_AUTO_UI.recordDrawerProjectId = pid;
      const allRecords = projectAutoRecordsByProjectId(pid).map((rec) => normalizeProjectAutoRecordView(rec));
      const filterTaskId = String(PROJECT_AUTO_UI.recordDrawerInspectionTaskId || "").trim();
      const filterKey = String(PROJECT_AUTO_UI.recordDrawerObjectKey || "").trim();
      const filterType = String(PROJECT_AUTO_UI.recordDrawerObjectType || "").trim().toLowerCase().replace(/-/g, "_");
      const filterName = String(PROJECT_AUTO_UI.recordDrawerObjectName || "").trim();
      const fallbackAll = !!PROJECT_AUTO_UI.recordDrawerFallbackAll;
      const filtered = allRecords.filter((rec) => {
        if (!rec || typeof rec !== "object") return false;
        if (filterTaskId && rec.inspectionTaskId && rec.inspectionTaskId === filterTaskId) return true;
        if (fallbackAll && !rec.hasOwner) return true;
        if (filterKey && rec.objectKey && rec.objectKey === filterKey) return true;
        if (filterType && rec.objectType && rec.objectType === filterType) return true;
        return false;
      });
      const records = (filterTaskId || filterKey || filterType || fallbackAll) ? filtered : allRecords;
      const latest = records.length ? records[0] : null;
      const ownerPrefix = filterName ? ("对象：" + filterName + " · ") : (filterTaskId ? ("任务板块：" + filterTaskId + " · ") : "");
      const fallbackHint = fallbackAll ? "（后端未返回归属字段，当前展示全量记录）" : "";
      sub.textContent = records.length
        ? (ownerPrefix + "共 " + records.length + " 条 · 最近 " + formatTsOrDash(latest && latest.createdAt) + fallbackHint)
        : "当前暂无巡查记录";
      listNode.innerHTML = "";
      listNode.appendChild(buildProjectAutoRecordList(records, {
        emptyText: "当前尚无巡查记录（非错误）。",
      }));
      mask.classList.add("show");
    }

    function openProjectAutoRecordDrawer(projectId, opts = {}) {
      const pid = String(projectId || projectAutoAvailableProjectId()).trim();
      if (!pid || pid === "overview") return;
      PROJECT_AUTO_UI.recordDrawerOpen = true;
      PROJECT_AUTO_UI.recordDrawerProjectId = pid;
      PROJECT_AUTO_UI.recordDrawerMode = String(opts.mode || "inspection").trim() || "inspection";
      PROJECT_AUTO_UI.recordDrawerInspectionTaskId = String(opts.inspectionTaskId || "").trim();
      PROJECT_AUTO_UI.recordDrawerObjectKey = String(opts.objectKey || "").trim();
      PROJECT_AUTO_UI.recordDrawerObjectType = String(opts.objectType || "").trim().toLowerCase().replace(/-/g, "_");
      PROJECT_AUTO_UI.recordDrawerObjectName = String(opts.objectName || "").trim();
      PROJECT_AUTO_UI.recordDrawerFallbackAll = !!opts.fallbackAll;
      PROJECT_AUTO_UI.heartbeatHistoryTaskId = String(opts.heartbeatTaskId || "").trim();
      PROJECT_AUTO_UI.recordDrawerHeartbeatTaskName = String(opts.heartbeatTaskName || "").trim();
      renderProjectAutoRecordDrawer(pid);
    }

    function closeProjectAutoModal() {
      closeProjectAutoRecordDrawer();
      const wrap = projectAutoWrapNode();
      if (wrap) wrap.classList.remove("show");
      PROJECT_AUTO_UI.open = false;
      const btn = projectAutoHeaderBtnNode();
      if (btn) btn.classList.remove("active");
      return true;
    }

    function openProjectAutoModal() {
      const pid = projectAutoAvailableProjectId();
      if (!pid) return;
      PROJECT_AUTO_UI.open = true;
      const wrap = projectAutoWrapNode();
      if (wrap) wrap.classList.add("show");
      const btn = projectAutoHeaderBtnNode();
      if (btn) btn.classList.add("active");
      ensureProjectAutoStatus(pid, { force: true, syncDraft: true });
    }

    function renderProjectAutoPanel() {
      const wrap = projectAutoWrapNode();
      const panel = projectAutoPanelNode();
      const headerBtn = projectAutoHeaderBtnNode();
      if (!panel) return;

      const pid = projectAutoAvailableProjectId();
      if (!pid) {
        if (headerBtn) {
          headerBtn.style.display = "none";
          headerBtn.classList.remove("active");
          headerBtn.disabled = true;
        }
        closeProjectAutoRecordDrawer();
        if (wrap) wrap.classList.remove("show");
        PROJECT_AUTO_UI.open = false;
        panel.innerHTML = "";
        renderProjectAutoHeaderState("");
        renderProjectRebuildBtn();
        return;
      }
      if (PROJECT_AUTO_UI.recordDrawerOpen && PROJECT_AUTO_UI.recordDrawerProjectId && PROJECT_AUTO_UI.recordDrawerProjectId !== pid) {
        closeProjectAutoRecordDrawer();
      }
      if (headerBtn) {
        headerBtn.style.display = "";
        headerBtn.disabled = false;
        headerBtn.classList.toggle("active", !!PROJECT_AUTO_UI.open);
      }
      renderProjectAutoHeaderState(pid);
      if (wrap) wrap.classList.toggle("show", !!PROJECT_AUTO_UI.open);
      renderProjectRebuildBtn();
      if (!PROJECT_AUTO_UI.open) return;

      const cached = PROJECT_AUTO.cache[pid] || null;
      const loading = !!PROJECT_AUTO.loading[pid];
      const toggling = !!PROJECT_AUTO.toggling[pid];
      const saving = !!PROJECT_AUTO.saving[pid];
      const err = String(PROJECT_AUTO.errors[pid] || "").trim();
      const saveErr = String(PROJECT_AUTO.saveErrors[pid] || "").trim();
      const saveNote = String(PROJECT_AUTO.saveNotes[pid] || "").trim();
      const status = cached && cached.status ? cached.status : null;
      const records = cached && Array.isArray(cached.records) ? cached.records : [];
      const draft = ensureProjectAutoDraft(pid, status);
      const inspectionTasks = normalizeInspectionTaskItemsClient(
        status && status.inspection_tasks,
        {
          projectId: pid,
          channelName: draft && draft.channelName,
          sessionId: draft && draft.sessionId,
          intervalMinutes: draft && draft.intervalMinutes,
          promptText: draft && draft.promptText,
          inspectionTargets: draft && draft.inspectionTargets,
          autoInspections: draft && draft.autoInspections,
        }
      );
      const activeInspectionTaskId = normalizeInspectionTaskIdClient(
        status && status.active_inspection_task_id,
        "default"
      );
      const channels = getProjectAutoChannels(pid);
      const allSessions = getProjectAutoSessions(pid);
      const filteredSessions = allSessions.filter((s) => {
        if (!draft || !draft.channelName) return true;
        const chans = Array.isArray(s && s.channels) ? s.channels : [];
        return chans.includes(draft.channelName) || String((s && s.primaryChannel) || "") === String(draft.channelName);
      });
      const sessionOptions = filteredSessions.length ? filteredSessions : allSessions;

      panel.innerHTML = "";
      const head = el("div", { class: "project-auto-head" });
      const left = el("div", { class: "project-auto-titlewrap" });
      left.appendChild(el("div", { class: "project-auto-kicker", text: "项目级调度" }));
      left.appendChild(el("div", { class: "project-auto-title", text: "任务自动触发 / 自动巡查调度" }));
      const subText = loading
        ? "状态同步中..."
        : (cached && cached.fetchedAt ? ("最近刷新 " + shortDateTime(cached.fetchedAt)) : "等待获取状态");
      left.appendChild(el("div", { class: "project-auto-sub", text: subText }));
      head.appendChild(left);

      const actions = el("div", { class: "project-auto-actions" });
      const refreshBtn = el("button", { class: "btn", text: loading ? "刷新中..." : "刷新" });
      refreshBtn.disabled = loading || toggling || saving;
      refreshBtn.addEventListener("click", () => ensureProjectAutoStatus(pid, { force: true }));
      actions.appendChild(refreshBtn);
      const resetBtn = el("button", { class: "btn", text: "重置草稿" });
      resetBtn.disabled = loading || toggling || saving;
      resetBtn.addEventListener("click", () => {
        delete PROJECT_AUTO.draftByProject[pid];
        PROJECT_AUTO.saveErrors[pid] = "";
        PROJECT_AUTO.saveNotes[pid] = "已按当前状态/默认值重置编辑草稿。";
        renderProjectAutoPanel();
      });
      actions.appendChild(resetBtn);
      const saveBtn = el("button", { class: "btn primary", text: saving ? "保存中..." : "保存配置" });
      saveBtn.disabled = loading || toggling || saving || !draft;
      saveBtn.addEventListener("click", () => saveProjectAutoConfig(pid));
      actions.appendChild(saveBtn);
      head.appendChild(actions);
      panel.appendChild(head);

      if (err) {
        panel.appendChild(el("div", { class: "project-auto-error", text: "状态获取失败：" + err }));
      }
      if (saveErr) {
        panel.appendChild(el("div", { class: "project-auto-error", text: "配置保存失败：" + saveErr }));
      } else if (saveNote) {
        panel.appendChild(el("div", { class: "project-auto-tip", text: saveNote }));
      }
      if (status && draft) {
        panel.appendChild(el("div", { class: "project-auto-tip", text: "请按卡片逐块配置；每个卡片顶部提供当前核心状态。" }));
      }

      const grid = el("div", { class: "project-auto-grid horizontal-stack" });
      const taskTriggerBody = el("div", { class: "project-auto-form" });
      const taskTriggerSwitch = buildProjectAutoSliderToggle({
        checked: !!(draft && draft.taskAutoTriggerEnabled),
        disabled: loading || saving,
        ariaLabel: "任务自动触发开关",
        titleOn: "自动首发已开启",
        titleOff: "自动首发已关闭",
        subOn: "任务进入“进行中”后自动首发推进",
        subOff: "任务进入“进行中”后仅支持手动首发",
        onToggle: (nextVal) => {
          updateProjectAutoDraft(pid, { taskAutoTriggerEnabled: !!nextVal });
          renderProjectAutoPanel();
        },
      });
      const taskTriggerTopFacts = [];
      if (status) {
        taskTriggerTopFacts.push(["最近自动首发", formatTsOrDash(status.auto_dispatch_last_at || status.scheduler_last_tick_at)]);
        const dispatchErr = String(status.auto_dispatch_last_error || status.scheduler_last_error || "").trim();
        if (dispatchErr) taskTriggerTopFacts.push(["异常摘要", dispatchErr]);
      }
      grid.appendChild(buildProjectAutoConfigCard({
        kind: "task-trigger",
        className: "horizontal",
        title: "任务自动触发",
        desc: "任务状态进入“进行中”时自动首发推进消息（自动首发）",
        statusChips: [
          { text: (draft && draft.taskAutoTriggerEnabled) ? "草稿已开" : "草稿已关", tone: (draft && draft.taskAutoTriggerEnabled) ? "good" : "muted" },
          { text: status ? autoStateLabel("dispatch", status.auto_dispatch_state || status.scheduler_state) : "状态未知", tone: status ? autoStateTone(status.auto_dispatch_state || status.scheduler_state) : "muted" },
        ],
        statusLine: (draft && draft.taskAutoTriggerEnabled)
          ? "任务一旦进入“进行中”会自动首发，适合减少首次推进遗漏。"
          : "关闭后仍可在任务详情里手动发起，适合先人工确认再触发。",
        note: "该卡片仅负责“状态进入进行中自动首发”，不负责定时巡查推进。",
        topControlNode: taskTriggerSwitch,
        bodyNode: taskTriggerBody,
        topFacts: taskTriggerTopFacts,
      }));

      const patrolBody = el("div", { class: "project-auto-form" });
      const nextDueText = projectAutoNextInspectionDueText(status, draft, cached);
      const patrolSwitch = buildProjectAutoSliderToggle({
        checked: !!(draft && draft.patrolEnabled),
        disabled: loading || saving,
        ariaLabel: "自动巡查开关",
        titleOn: "自动巡查已开启",
        titleOff: "自动巡查已关闭",
        subOn: "按固定间隔定时巡查推进进行中任务",
        subOff: "关闭后不再自动巡查，可保留手动推进",
        extraLine: "",
        onToggle: (nextVal) => {
          updateProjectAutoDraft(pid, { patrolEnabled: !!nextVal });
          renderProjectAutoPanel();
        },
      });

      const channelSel = el("select", { class: "project-auto-select", "aria-label": "自动巡查通道" });
      if (!channels.length) {
        channelSel.appendChild(el("option", { value: "", text: "暂无可选通道" }));
      } else {
        channels.forEach((name) => {
          const opt = el("option", { value: name, text: name });
          if (draft && String(draft.channelName || "") === String(name)) opt.selected = true;
          channelSel.appendChild(opt);
        });
      }
      channelSel.disabled = loading || saving || !channels.length;
      channelSel.addEventListener("change", () => {
        const nextChannel = String(channelSel.value || "").trim();
        const nextSessionId = pickProjectAutoDefaultSessionId(pid, nextChannel);
        updateProjectAutoDraft(pid, { channelName: nextChannel, sessionId: nextSessionId || "" });
        renderProjectAutoPanel();
      });
      patrolBody.appendChild(buildProjectAutoSelectField(
        "通道选择",
        channelSel,
        channels.length ? "用于巡查消息默认投递通道（后端字段待回显）。" : "当前项目尚未识别到通道。"
      ));

      const sessionSel = el("select", { class: "project-auto-select", "aria-label": "自动巡查会话" });
      if (!sessionOptions.length) {
        sessionSel.appendChild(el("option", { value: "", text: "暂无可选会话" }));
      } else {
        sessionOptions.forEach((sess) => {
          const sid = String((sess && sess.sessionId) || "").trim();
          if (!sid) return;
          const opt = el("option", { value: sid, text: buildProjectAutoSessionOptionLabel(sess) });
          if (draft && String(draft.sessionId || "") === sid) opt.selected = true;
          sessionSel.appendChild(opt);
        });
      }
      sessionSel.disabled = loading || saving || !sessionOptions.length;
      sessionSel.addEventListener("change", () => {
        updateProjectAutoDraft(pid, { sessionId: String(sessionSel.value || "").trim() });
      });
      patrolBody.appendChild(buildProjectAutoSelectField(
        "会话选择",
        sessionSel,
        sessionOptions.length ? "建议选择该通道主会话；当前默认已预选一条可用会话。" : "当前项目暂无已绑定会话。"
      ));

      const targetsWrap = el("div", { class: "project-auto-target-list" });
      const normalizedRecords = records.map((rec) => normalizeProjectAutoRecordView(rec));
      inspectionTasks.forEach((task, idx) => {
        const row = el("div", { class: "project-auto-target-row" });
        const leftMeta = el("div", { class: "project-auto-target-meta" });
        const taskId = String(task.inspection_task_id || "").trim();
        const title = String(task.title || ("巡查任务 " + (idx + 1))).trim();
        const targetLabels = normalizeInspectionTargetsClient(task.inspection_targets, [])
          .map((x) => INSPECTION_TARGET_LABEL_MAP[x] || x)
          .filter(Boolean);
        leftMeta.appendChild(el("div", { class: "project-auto-target-name", text: (idx + 1) + ". " + title + (taskId === activeInspectionTaskId ? "（当前激活）" : "") }));
        leftMeta.appendChild(el("div", {
          class: "project-auto-target-desc",
          text: "任务ID: " + (taskId || "-")
            + " · 通道: " + (task.channel_name || "-")
            + " · 会话: " + (task.session_id ? shortId(task.session_id) : "-")
            + " · 巡查对象: " + (targetLabels.length ? targetLabels.join(" / ") : "-"),
        }));
        row.appendChild(leftMeta);

        const actions = el("div", { class: "project-auto-target-actions-inline" });
        const enabledLabel = el("label", { class: "project-auto-target-item" });
        const enabledInput = el("input", { type: "checkbox" });
        enabledInput.checked = !!task.enabled;
        enabledInput.disabled = loading || saving;
        enabledInput.addEventListener("change", async () => {
          try {
            PROJECT_AUTO.saveErrors[pid] = "";
            PROJECT_AUTO.saveNotes[pid] = "";
            renderProjectAutoPanel();
            const payloadTask = Object.assign({}, task, { enabled: !!enabledInput.checked });
            await projectAutoUpsertInspectionTask(pid, payloadTask, taskId === activeInspectionTaskId);
            PROJECT_AUTO.saveNotes[pid] = "已更新巡查板块状态：" + title;
            await ensureProjectAutoStatus(pid, { force: true, syncDraft: true });
          } catch (e) {
            PROJECT_AUTO.saveErrors[pid] = e && e.message ? String(e.message) : "更新巡查板块失败";
            renderProjectAutoPanel();
          }
        });
        enabledLabel.appendChild(enabledInput);
        enabledLabel.appendChild(el("span", { text: enabledInput.checked ? "已启用" : "未启用" }));
        actions.appendChild(enabledLabel);

        const ownedRecords = normalizedRecords.filter((rec) => {
          if (!rec || typeof rec !== "object") return false;
          return !!taskId && !!rec.inspectionTaskId && rec.inspectionTaskId === taskId;
        });
        const recordBtnText = "记录 " + ownedRecords.length + " 条";
        const recordBtn = el("button", { class: "btn", type: "button", text: recordBtnText });
        recordBtn.disabled = false;
        recordBtn.addEventListener("click", () => {
          openProjectAutoRecordDrawer(pid, {
            inspectionTaskId: taskId,
            objectName: title,
          });
        });
        actions.appendChild(recordBtn);

        const delBtn = el("button", { class: "btn", type: "button", text: "删除" });
        delBtn.disabled = loading || saving;
        delBtn.addEventListener("click", async () => {
          try {
            PROJECT_AUTO.saveErrors[pid] = "";
            PROJECT_AUTO.saveNotes[pid] = "";
            renderProjectAutoPanel();
            if (taskId === "default") {
              await projectAutoUpsertInspectionTask(pid, Object.assign({}, task, { enabled: false }), true);
              PROJECT_AUTO.saveNotes[pid] = "默认巡查板块受保护，已执行软删（仅关闭）。";
            } else {
              await projectAutoDeleteInspectionTask(pid, taskId);
              PROJECT_AUTO.saveNotes[pid] = "已删除巡查板块：" + title;
            }
            await ensureProjectAutoStatus(pid, { force: true, syncDraft: true });
          } catch (e) {
            PROJECT_AUTO.saveErrors[pid] = e && e.message ? String(e.message) : "删除巡查板块失败";
            renderProjectAutoPanel();
          }
        });
        actions.appendChild(delBtn);
        row.appendChild(actions);
        targetsWrap.appendChild(row);
      });
      patrolBody.appendChild(buildProjectAutoInputField(
        "巡查任务板块",
        targetsWrap,
        "每个巡查任务独立成块：支持启停、删除与按任务板块查看记录。"
      ));
      const targetActionRow = el("div", { class: "project-auto-target-actions" });
      const addTargetBtn = el("button", { class: "btn", type: "button", text: "+ 新增巡查任务" });
      addTargetBtn.disabled = false;
      addTargetBtn.title = "创建独立巡查任务板块（直接写入 inspection-tasks）。";
      addTargetBtn.addEventListener("click", async () => {
        try {
          const now = Date.now();
          const nextId = "board-" + now;
          const nextBoard = {
            inspection_task_id: nextId,
            title: "巡查任务 " + (inspectionTasks.length + 1),
            enabled: true,
            channel_name: String((draft && draft.channelName) || "").trim(),
            session_id: String((draft && draft.sessionId) || "").trim(),
            interval_minutes: Math.max(5, Number((draft && draft.intervalMinutes) || 30)),
            prompt_template: String((draft && draft.promptText) || defaultProjectAutoPrompt(pid)).trim(),
            inspection_targets: normalizeInspectionTargetsClient(draft && draft.inspectionTargets, ["scheduled", "in_progress"]),
            auto_inspections: normalizeAutoInspectionObjectsClient(draft && draft.autoInspections, draft && draft.inspectionTargets),
          };
          PROJECT_AUTO.saveErrors[pid] = "";
          PROJECT_AUTO.saveNotes[pid] = "";
          renderProjectAutoPanel();
          await projectAutoUpsertInspectionTask(pid, nextBoard, true);
          PROJECT_AUTO.saveNotes[pid] = "已新增巡查板块：" + nextBoard.title;
          await ensureProjectAutoStatus(pid, { force: true, syncDraft: true });
        } catch (e) {
          PROJECT_AUTO.saveErrors[pid] = e && e.message ? String(e.message) : "新增巡查任务失败";
          renderProjectAutoPanel();
        }
      });
      targetActionRow.appendChild(addTargetBtn);
      patrolBody.appendChild(targetActionRow);

      const intervalInput = el("input", {
        class: "project-auto-input",
        type: "number",
        min: "5",
        step: "5",
        placeholder: "30",
      });
      intervalInput.value = String((draft && draft.intervalMinutes) || 30);
      intervalInput.disabled = loading || saving;
      intervalInput.addEventListener("input", () => {
        updateProjectAutoDraft(pid, { intervalMinutes: intervalInput.value });
      });
      patrolBody.appendChild(buildProjectAutoInputField(
        "巡查间隔（分钟）",
        intervalInput,
        "默认 30 分钟，可改；保存时写入 reminder.interval_minutes（最小 5 分钟）。"
      ));

      const promptText = el("textarea", {
        class: "project-auto-textarea",
        rows: "4",
        placeholder: "填写巡查提示词",
      });
      promptText.value = String((draft && draft.promptText) || "");
      promptText.disabled = loading || saving;
      promptText.addEventListener("input", () => {
        updateProjectAutoDraft(pid, { promptText: promptText.value });
      });
      patrolBody.appendChild(buildProjectAutoInputField(
        "巡查提示词",
        promptText,
        "定时巡查推进的提示词模板（优先对应 `auto_inspection.prompt_template`）。"
      ));

      const patrolTopFacts = [];
      const targetsForFacts = normalizeInspectionTargetsClient(
        (inspectionTasks[0] && inspectionTasks[0].inspection_targets) || (draft && draft.inspectionTargets),
        []
      )
        .map((x) => {
          const hit = INSPECTION_TARGET_OPTIONS.find((opt) => opt.value === x);
          return hit ? hit.label : x;
        })
        .filter(Boolean);
      patrolTopFacts.push(["巡查板块", String(inspectionTasks.length || 0) + " 个"]);
      patrolTopFacts.push(["巡查对象", targetsForFacts.length ? targetsForFacts.join(" / ") : "-"]);
      patrolTopFacts.push(["下次计划巡查", nextDueText]);
      patrolTopFacts.push(["最近巡查", status ? formatTsOrDash(status.auto_inspection_last_at || status.scheduler_last_tick_at || status.reminder_last_tick_at) : "-"]);
      const errorSummary = formatProjectAutoErrorSummary(status);
      if (errorSummary) patrolTopFacts.push(["异常摘要", errorSummary]);
      grid.appendChild(buildProjectAutoConfigCard({
        kind: "patrol",
        className: "horizontal",
        title: "自动巡查调度",
        desc: "定时巡查推进进行中任务（按通道/会话/间隔/提示词执行）",
        statusChips: [
          { text: (draft && draft.patrolEnabled) ? "草稿已开" : "草稿已关", tone: (draft && draft.patrolEnabled) ? "good" : "muted" },
          { text: status ? autoStateLabel("reminder", status.auto_inspection_state || status.reminder_state || status.scheduler_state) : "巡查未知", tone: status ? autoStateTone(status.auto_inspection_state || status.reminder_state || status.scheduler_state) : "muted" },
        ],
        statusLine: status && draft
          ? projectAutoHumanSummary(status, draft)
          : "状态未就绪，先刷新后再保存配置。",
        topControlNode: patrolSwitch,
        bodyNode: patrolBody,
        topFacts: patrolTopFacts,
      }));

      panel.appendChild(grid);

      const recordsWrap = el("div", { class: "project-auto-record-entry" });
      const recordsTop = el("div", { class: "project-auto-record-entry-top" });
      recordsTop.appendChild(el("div", {
        class: "project-auto-records-title",
        text: "巡查记录（独立入口）",
      }));
      const openRecordBtn = el("button", {
        class: "btn",
        type: "button",
        text: records.length ? ("查看记录（" + records.length + "）") : "查看记录",
      });
      openRecordBtn.disabled = false;
      openRecordBtn.addEventListener("click", () => openProjectAutoRecordDrawer(pid));
      recordsTop.appendChild(openRecordBtn);
      recordsWrap.appendChild(recordsTop);
      if (records.length) {
        const latest = normalizeProjectAutoRecordView(records[0]);
        recordsWrap.appendChild(el("div", {
          class: "project-auto-record-entry-summary",
          text: "最近：" + latest.statusMeta.label + " · " + formatTsOrDash(latest.createdAt) + " · " + latest.summary,
        }));
      } else {
        const lastInspectionTs = status
          ? formatTsOrDash(
            status.auto_inspection_last_at
            || status.scheduler_last_tick_at
            || status.reminder_last_tick_at
          )
          : "-";
        recordsWrap.appendChild(el("div", {
          class: "project-auto-record-entry-summary",
          text: "当前尚无巡查记录（非错误）。最近巡查时间：" + lastInspectionTs,
        }));
      }
      panel.appendChild(recordsWrap);

      const foot = el("div", { class: "project-auto-foot" });
      foot.appendChild(el("div", {
        class: "project-auto-foot-note",
        text: "说明：本轮为前端最小可用版，优先打通状态读取与统一配置保存；通道/会话/提示词/任务自动触发字段的持久化以服务端新增字段接入进度为准。",
      }));
      panel.appendChild(foot);
      if (PROJECT_AUTO_UI.recordDrawerOpen && PROJECT_AUTO_UI.recordDrawerProjectId === pid) {
        renderProjectAutoRecordDrawer(pid);
      }
    }

    function buildProjectAutoToggleCard(opts = {}) {
      const kind = String(opts.kind || "");
      const title = String(opts.title || "");
      const desc = String(opts.desc || "");
      const enabled = !!opts.enabled;
      const state = String(opts.state || "disabled");
      const loading = !!opts.loading;
      const toggling = !!opts.toggling;
      const interactive = !!opts.interactive;
      const interactiveReason = String(opts.interactiveReason || "").trim();
      const onToggle = typeof opts.onToggle === "function" ? opts.onToggle : null;
      const extraRows = Array.isArray(opts.extraRows) ? opts.extraRows : [];

      const card = el("div", { class: "project-auto-card " + kind });
      const top = el("div", { class: "project-auto-card-top" });
      const textWrap = el("div", { class: "project-auto-card-text" });
      textWrap.appendChild(el("div", { class: "project-auto-card-title", text: title }));
      textWrap.appendChild(el("div", { class: "project-auto-card-desc", text: desc }));
      top.appendChild(textWrap);

      const switchWrap = el("div", { class: "project-auto-switch-wrap" });
      const stateChipNode = chip(autoStateLabel(kind, state), autoStateTone(state));
      switchWrap.appendChild(stateChipNode);
      const btnLabel = toggling
        ? "提交中..."
        : (enabled ? "关闭" : "开启");
      const btnCls = "btn " + (enabled ? "" : "primary");
      const toggleBtn = el("button", { class: btnCls.trim(), text: btnLabel });
      toggleBtn.disabled = loading || toggling || !interactive;
      if (!interactive && interactiveReason) toggleBtn.title = interactiveReason;
      if (interactive && onToggle) {
        toggleBtn.addEventListener("click", () => onToggle(!enabled));
      }
      switchWrap.appendChild(toggleBtn);
      top.appendChild(switchWrap);
      card.appendChild(top);

      if (!interactive && interactiveReason) {
        card.appendChild(el("div", { class: "project-auto-card-note", text: interactiveReason }));
      }

      const meta = el("div", { class: "project-auto-card-meta" });
      extraRows.forEach((row) => {
        if (!Array.isArray(row) || row.length < 2) return;
        const k = String(row[0] || "").trim();
        const v = String(row[1] == null ? "" : row[1]).trim();
        if (!k) return;
        const item = el("div", { class: "project-auto-meta-row" });
        item.appendChild(el("span", { class: "project-auto-meta-k", text: k }));
        item.appendChild(el("span", { class: "project-auto-meta-v", text: v || "-" }));
        meta.appendChild(item);
      });
      card.appendChild(meta);
      return card;
    }

    async function saveProjectAutoConfig(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return;
      if (PROJECT_AUTO.saving[pid]) return;
      const cached = PROJECT_AUTO.cache[pid] || null;
      const status = cached && cached.status ? cached.status : null;
      const draft = ensureProjectAutoDraft(pid, status);
      const heartbeatDraft = ensureHeartbeatTaskDraft(
        pid,
        (cached && cached.heartbeatMeta) || {},
        (cached && cached.heartbeatTasks) || []
      );
      if (!draft) return;
      const intervalRaw = Number(draft.intervalMinutes);
      if (!Number.isFinite(intervalRaw) || intervalRaw < 5) {
        PROJECT_AUTO.saveErrors[pid] = "巡查间隔必须是大于等于 5 的数字（分钟）。";
        PROJECT_AUTO.saveNotes[pid] = "";
        renderProjectAutoPanel();
        return;
      }
      const intervalMinutes = Math.max(5, Math.round(intervalRaw));
      const promptText = String(draft.promptText || "").trim();
      const channelName = String(draft.channelName || "").trim();
      const sessionId = String(draft.sessionId || "").trim();
      const inspectionTargets = normalizeInspectionTargetsClient(
        draft.inspectionTargets,
        draft.patrolEnabled ? ["scheduled", "in_progress"] : []
      );
      const autoInspections = normalizeAutoInspectionObjectsClient(
        draft.autoInspections,
        inspectionTargets
      );
      const targetsFromObjects = autoInspectionTargetsFromObjectsClient(autoInspections);
      const effectiveInspectionTargets = targetsFromObjects.length ? targetsFromObjects : inspectionTargets;

      // 主口径：auto_dispatch / auto_inspection；旧口径仅保留最小兼容（scheduler/reminder.enabled+interval）。
      const payload = {
        auto_dispatch: {
          enabled: !!draft.taskAutoTriggerEnabled,
        },
        auto_inspection: {
          enabled: !!draft.patrolEnabled,
          channel_name: channelName || null,
          session_id: sessionIdLooksValid(sessionId) ? sessionId : null,
          interval_minutes: intervalMinutes,
          prompt_template: promptText || null,
          inspection_targets: effectiveInspectionTargets,
          auto_inspections: autoInspections,
        },
        scheduler: {
          enabled: !!draft.patrolEnabled,
        },
        reminder: {
          enabled: !!draft.patrolEnabled,
          interval_minutes: intervalMinutes,
        },
        heartbeat: {
          enabled: !!(heartbeatDraft && heartbeatDraft.heartbeatEnabled),
          scan_interval_seconds: Math.max(20, Number((heartbeatDraft && heartbeatDraft.heartbeatScanIntervalSeconds) || 30)),
        },
      };

      PROJECT_AUTO.saving[pid] = true;
      PROJECT_AUTO.saveErrors[pid] = "";
      PROJECT_AUTO.saveNotes[pid] = "";
      renderProjectAutoPanel();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/config", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        const projectObj = (data && typeof data === "object" && data.project && typeof data.project === "object")
          ? data.project
          : {};
        const statusRaw = (projectObj && typeof projectObj.status === "object") ? projectObj.status : null;
        if (statusRaw) {
          const prev = PROJECT_AUTO.cache[pid] || {};
          PROJECT_AUTO.cache[pid] = {
            status: normalizeProjectAutoState(statusRaw, pid),
            records: Array.isArray(prev.records) ? prev.records : [],
            fetchedAt: new Date().toISOString(),
            fetchedAtMs: Date.now(),
          };
        }
        updateProjectAutoDraft(pid, {
          patrolEnabled: !!draft.patrolEnabled,
          intervalMinutes: intervalMinutes,
          promptText: promptText || defaultProjectAutoPrompt(pid),
          channelName: channelName,
          sessionId: sessionId,
          taskAutoTriggerEnabled: !!draft.taskAutoTriggerEnabled,
          inspectionTargets: effectiveInspectionTargets,
          autoInspections: autoInspections,
        });
        if (heartbeatDraft) {
          updateHeartbeatTaskDraft(pid, {
            heartbeatEnabled: !!heartbeatDraft.heartbeatEnabled,
            heartbeatScanIntervalSeconds: Math.max(20, Number(heartbeatDraft.heartbeatScanIntervalSeconds || 30)),
          });
        }

        const autoDispatchCfg = (projectObj && typeof projectObj.auto_dispatch === "object")
          ? projectObj.auto_dispatch
          : ((data && typeof data === "object" && data.auto_dispatch && typeof data.auto_dispatch === "object") ? data.auto_dispatch : {});
        const autoInspectionCfg = (projectObj && typeof projectObj.auto_inspection === "object")
          ? projectObj.auto_inspection
          : ((data && typeof data === "object" && data.auto_inspection && typeof data.auto_inspection === "object") ? data.auto_inspection : {});
        const heartbeatCfg = (projectObj && typeof projectObj.heartbeat === "object")
          ? projectObj.heartbeat
          : ((data && typeof data === "object" && data.heartbeat && typeof data.heartbeat === "object") ? data.heartbeat : {});
        const missingEcho = [];
        if (!("enabled" in autoDispatchCfg)) {
          missingEcho.push("任务自动触发开关");
        }
        if (!("enabled" in autoInspectionCfg)) {
          missingEcho.push("自动巡查开关");
        }
        if (!("channel_name" in autoInspectionCfg) && !("session_id" in autoInspectionCfg) && !("prompt_template" in autoInspectionCfg)) {
          missingEcho.push("巡查通道/会话/提示词");
        }
        if (!("inspection_targets" in autoInspectionCfg) && !("inspectionTargets" in autoInspectionCfg)) {
          missingEcho.push("巡查对象");
        }
        if (!("auto_inspections" in autoInspectionCfg) && !("autoInspections" in autoInspectionCfg)) {
          missingEcho.push("巡查对象详情");
        }
        if (!("enabled" in heartbeatCfg)) {
          missingEcho.push("心跳任务开关");
        }
        if (!("scan_interval_seconds" in heartbeatCfg) && !("scanIntervalSeconds" in heartbeatCfg)) {
          missingEcho.push("心跳扫描频率");
        }
        PROJECT_AUTO.saveNotes[pid] = missingEcho.length
          ? "已按主口径提交配置；" + missingEcho.join("、") + "暂未在服务端响应中回显（当前按前端草稿展示）。"
          : "项目调度配置已保存。";
        await ensureProjectAutoStatus(pid, { force: true, syncDraft: true });
      } catch (e) {
        PROJECT_AUTO.saveErrors[pid] = e && e.message ? String(e.message) : "配置保存失败";
      } finally {
        PROJECT_AUTO.saving[pid] = false;
        renderProjectAutoPanel();
      }
    }

    async function ensureProjectAutoStatus(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return;
      const force = !!opts.force;
      const syncDraft = !!opts.syncDraft;
      const maxAgeRaw = Number(opts.maxAgeMs);
      const maxAgeMs = Number.isFinite(maxAgeRaw) && maxAgeRaw >= 0 ? maxAgeRaw : 20000;
      if (syncDraft) delete PROJECT_AUTO.draftByProject[pid];
      if (!force && PROJECT_AUTO.cache[pid]) {
        const fetchedAtMs = Number(PROJECT_AUTO.cache[pid].fetchedAtMs || 0);
        const ageMs = fetchedAtMs > 0 ? (Date.now() - fetchedAtMs) : Number.POSITIVE_INFINITY;
        if (ageMs <= maxAgeMs) {
          if (PROJECT_AUTO_UI.open) renderProjectAutoPanel();
          else renderProjectAutoHeaderOnly(pid);
          return;
        }
      }
      if (PROJECT_AUTO.loading[pid]) {
        if (PROJECT_AUTO_UI.open) renderProjectAutoPanel();
        else renderProjectAutoHeaderOnly(pid);
        return;
      }
      PROJECT_AUTO.loading[pid] = true;
      PROJECT_AUTO.errors[pid] = "";
      const seq = Number(PROJECT_AUTO.seqByProject[pid] || 0) + 1;
      PROJECT_AUTO.seqByProject[pid] = seq;
      if (PROJECT_AUTO_UI.open) renderProjectAutoPanel();
      else renderProjectAutoHeaderOnly(pid);
      try {
        const statusPromise = fetch("/api/projects/" + encodeURIComponent(pid) + "/auto-scheduler", {
          headers: authHeaders({}),
          cache: "no-store",
        });
        const tasksPromise = fetch("/api/projects/" + encodeURIComponent(pid) + "/auto-scheduler/inspection-tasks", {
          headers: authHeaders({}),
          cache: "no-store",
        }).catch(() => null);
        const heartbeatPromise = fetch("/api/projects/" + encodeURIComponent(pid) + "/heartbeat-tasks", {
          headers: authHeaders({}),
          cache: "no-store",
        }).catch(() => null);
        const [resp, tasksResp, heartbeatResp] = await Promise.all([statusPromise, tasksPromise, heartbeatPromise]);
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        let taskItems = [];
        let activeTaskId = "";
        if (tasksResp && tasksResp.ok) {
          const tasksJson = await tasksResp.json().catch(() => ({}));
          taskItems = Array.isArray(tasksJson && tasksJson.items) ? tasksJson.items : [];
          activeTaskId = firstNonEmptyText([
            tasksJson && tasksJson.active_inspection_task_id,
            tasksJson && tasksJson.activeInspectionTaskId,
          ]);
        }
        let heartbeatTasks = [];
        let heartbeatMeta = { enabled: false, scan_interval_seconds: 30, count: 0, errors: [], ready: false };
        PROJECT_AUTO.heartbeatErrors[pid] = "";
        if (heartbeatResp) {
          if (heartbeatResp.ok) {
            const heartbeatJson = await heartbeatResp.json().catch(() => ({}));
            heartbeatTasks = normalizeHeartbeatTaskItemsClient(
              Array.isArray(heartbeatJson && heartbeatJson.items) ? heartbeatJson.items : [],
              pid
            );
            heartbeatMeta = {
              enabled: _coerceBoolClient(heartbeatJson && heartbeatJson.enabled, false),
              scan_interval_seconds: Math.max(20, Number((heartbeatJson && heartbeatJson.scan_interval_seconds) || 30)),
              count: Math.max(0, Number((heartbeatJson && heartbeatJson.count) || heartbeatTasks.length || 0)),
              errors: Array.isArray(heartbeatJson && heartbeatJson.errors) ? heartbeatJson.errors : [],
              ready: _coerceBoolClient(heartbeatJson && heartbeatJson.ready, true),
            };
          } else {
            PROJECT_AUTO.heartbeatErrors[pid] = await parseResponseDetail(heartbeatResp);
          }
        }
        if (Number(PROJECT_AUTO.seqByProject[pid] || 0) !== seq) return;
        const statusRaw = (data && typeof data === "object" && data.status && typeof data.status === "object") ? data.status : data;
        if (Array.isArray(taskItems) && taskItems.length) statusRaw.inspection_tasks = taskItems;
        if (activeTaskId) statusRaw.active_inspection_task_id = activeTaskId;
        const records = normalizeReminderRecordsPayload(data);
        PROJECT_AUTO.cache[pid] = {
          status: normalizeProjectAutoState(statusRaw, pid),
          records,
          heartbeatTasks,
          heartbeatMeta,
          fetchedAt: new Date().toISOString(),
          fetchedAtMs: Date.now(),
        };
        if (syncDraft) delete PROJECT_AUTO.draftByProject[pid];
        if (syncDraft) delete PROJECT_AUTO.heartbeatDraftByProject[pid];
      } catch (e) {
        if (Number(PROJECT_AUTO.seqByProject[pid] || 0) === seq) {
          PROJECT_AUTO.errors[pid] = e && e.message ? String(e.message) : "网络或服务异常";
        }
      } finally {
        if (Number(PROJECT_AUTO.seqByProject[pid] || 0) === seq) PROJECT_AUTO.loading[pid] = false;
        if (PROJECT_AUTO_UI.open) renderProjectAutoPanel();
        else renderProjectAutoHeaderOnly(pid);
      }
    }

    async function setProjectAutoSchedulerEnabled(projectId, enabled) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return;
      if (PROJECT_AUTO.toggling[pid]) return;
      PROJECT_AUTO.toggling[pid] = true;
      PROJECT_AUTO.errors[pid] = "";
      renderProjectAutoPanel();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/auto-scheduler", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ enabled: !!enabled }),
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        const statusRaw = (data && typeof data === "object" && data.status && typeof data.status === "object") ? data.status : data;
        const prev = PROJECT_AUTO.cache[pid] || {};
        PROJECT_AUTO.cache[pid] = {
          status: normalizeProjectAutoState(statusRaw, pid),
          records: Array.isArray(prev.records) ? prev.records : [],
          fetchedAt: new Date().toISOString(),
          fetchedAtMs: Date.now(),
        };
        delete PROJECT_AUTO.draftByProject[pid];
      } catch (e) {
        PROJECT_AUTO.errors[pid] = e && e.message ? String(e.message) : "开关更新失败";
      } finally {
        PROJECT_AUTO.toggling[pid] = false;
        renderProjectAutoPanel();
      }
    }

    async function projectAutoUpsertInspectionTask(projectId, task, setActive = false) {
      const pid = String(projectId || "").trim();
      const row = (task && typeof task === "object") ? task : {};
      if (!pid || !row) throw new Error("缺少项目或巡查任务参数");
      const inspectionTaskId = normalizeInspectionTaskIdClient(
        firstNonEmptyText([row.inspection_task_id, row.inspectionTaskId]),
        ""
      );
      if (!inspectionTaskId) throw new Error("inspection_task_id 不能为空");
      const payload = {
        set_active: !!setActive,
        inspection_task: {
          inspection_task_id: inspectionTaskId,
          title: firstNonEmptyText([row.title]) || "巡查任务",
          enabled: _coerceBoolClient(row.enabled, true),
          channel_name: firstNonEmptyText([row.channel_name, row.channelName]),
          session_id: firstNonEmptyText([row.session_id, row.sessionId]),
          interval_minutes: Math.max(5, Number(firstNonEmptyText([row.interval_minutes, row.intervalMinutes]) || 30)),
          prompt_template: firstNonEmptyText([row.prompt_template, row.promptTemplate]),
          inspection_targets: normalizeInspectionTargetsClient(
            row.inspection_targets || row.inspectionTargets || [],
            ["scheduled", "in_progress"]
          ),
          auto_inspections: normalizeAutoInspectionObjectsClient(
            row.auto_inspections || row.autoInspections || [],
            row.inspection_targets || row.inspectionTargets || ["scheduled", "in_progress"]
          ),
        },
      };
      const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/auto-scheduler/inspection-tasks", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return resp.json().catch(() => ({}));
    }

    async function projectAutoDeleteInspectionTask(projectId, inspectionTaskId) {
      const pid = String(projectId || "").trim();
      const tid = normalizeInspectionTaskIdClient(inspectionTaskId, "");
      if (!pid || !tid) throw new Error("缺少项目或 inspection_task_id");
      const resp = await fetch(
        "/api/projects/" + encodeURIComponent(pid) + "/auto-scheduler/inspection-tasks/" + encodeURIComponent(tid) + "/delete",
        {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({}),
        }
      );
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return resp.json().catch(() => ({}));
    }

    async function projectAutoUpsertHeartbeatTask(projectId, draft) {
      const pid = String(projectId || "").trim();
      const row = (draft && typeof draft === "object") ? draft : {};
      if (!pid) throw new Error("缺少 project_id");
      const heartbeatTaskId = String(row.heartbeatTaskId || row.heartbeat_task_id || "").trim();
      if (!heartbeatTaskId) throw new Error("heartbeat_task_id 不能为空");
      const contextScope = Object.assign({}, row.contextScope || {});
      const payload = {
        enabled: _coerceBoolClient(row.heartbeatEnabled, true),
        scan_interval_seconds: Math.max(20, Number(row.heartbeatScanIntervalSeconds || 30)),
        heartbeat_task: {
          heartbeat_task_id: heartbeatTaskId,
          title: String(row.title || "").trim() || heartbeatTaskId,
          enabled: _coerceBoolClient(row.enabled, true),
          channel_name: String(row.channelName || row.channel_name || "").trim(),
          session_id: sessionIdLooksValid(row.sessionId) ? String(row.sessionId || "").trim() : "",
          preset_key: String(row.presetKey || row.preset_key || "ops_inspection").trim(),
          prompt_template: String(row.promptTemplate || row.prompt_template || "").trim(),
          schedule_type: String(row.scheduleType || row.schedule_type || "interval").trim() === "daily" ? "daily" : "interval",
          interval_minutes: Math.max(5, Number(row.intervalMinutes || row.interval_minutes || 120)),
          daily_time: String(row.dailyTime || row.daily_time || "09:30").trim() || "09:30",
          weekdays: normalizeHeartbeatWeekdaysClient(row.weekdays),
          busy_policy: String(row.busyPolicy || row.busy_policy || "run_on_next_idle").trim() || "run_on_next_idle",
          max_execute_count: Math.max(0, Number(row.maxExecuteCount || row.max_execute_count || 0)),
          context_scope: {
            recent_tasks_limit: Math.max(0, Number(contextScope.recentTasksLimit || contextScope.recent_tasks_limit || 10)),
            recent_runs_limit: Math.max(0, Number(contextScope.recentRunsLimit || contextScope.recent_runs_limit || 10)),
            include_task_counts: _coerceBoolClient(contextScope.includeTaskCounts ?? contextScope.include_task_counts, true),
            include_recent_tasks: _coerceBoolClient(contextScope.includeRecentTasks ?? contextScope.include_recent_tasks, true),
            include_recent_runs: _coerceBoolClient(contextScope.includeRecentRuns ?? contextScope.include_recent_runs, true),
          },
        },
      };
      const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/heartbeat-tasks", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return resp.json().catch(() => ({}));
    }

    async function projectAutoDeleteHeartbeatTask(projectId, heartbeatTaskId) {
      const pid = String(projectId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      if (!pid || !tid) throw new Error("缺少项目或 heartbeat_task_id");
      const resp = await fetch(
        "/api/projects/" + encodeURIComponent(pid) + "/heartbeat-tasks/" + encodeURIComponent(tid) + "/delete",
        {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({}),
        }
      );
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return resp.json().catch(() => ({}));
    }

    async function projectAutoRunHeartbeatTaskNow(projectId, heartbeatTaskId) {
      const pid = String(projectId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      if (!pid || !tid) throw new Error("缺少项目或 heartbeat_task_id");
      const resp = await fetch(
        "/api/projects/" + encodeURIComponent(pid) + "/heartbeat-tasks/" + encodeURIComponent(tid) + "/run-now",
        {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({}),
        }
      );
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return resp.json().catch(() => ({}));
    }

    async function ensureProjectAutoHeartbeatHistory(projectId, heartbeatTaskId, force = false) {
      const pid = String(projectId || "").trim();
      const tid = String(heartbeatTaskId || "").trim();
      const key = heartbeatTaskKey(pid, tid);
      if (!key) return [];
      if (!force && PROJECT_AUTO.heartbeatHistoryByTask[key] && Array.isArray(PROJECT_AUTO.heartbeatHistoryByTask[key].items)) {
        return PROJECT_AUTO.heartbeatHistoryByTask[key].items;
      }
      if (PROJECT_AUTO.heartbeatHistoryLoadingByTask[key]) {
        return (PROJECT_AUTO.heartbeatHistoryByTask[key] && PROJECT_AUTO.heartbeatHistoryByTask[key].items) || [];
      }
      PROJECT_AUTO.heartbeatHistoryLoadingByTask[key] = true;
      PROJECT_AUTO.heartbeatHistoryErrorByTask[key] = "";
      try {
        const resp = await fetch(
          "/api/projects/" + encodeURIComponent(pid) + "/heartbeat-tasks/" + encodeURIComponent(tid) + "/history?limit=20",
          {
            headers: authHeaders({}),
            cache: "no-store",
          }
        );
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        const items = Array.isArray(data && data.items) ? data.items : [];
        PROJECT_AUTO.heartbeatHistoryByTask[key] = {
          items,
          fetchedAt: new Date().toISOString(),
        };
        return items;
      } catch (e) {
        PROJECT_AUTO.heartbeatHistoryErrorByTask[key] = e && e.message ? String(e.message) : "获取历史失败";
        return (PROJECT_AUTO.heartbeatHistoryByTask[key] && PROJECT_AUTO.heartbeatHistoryByTask[key].items) || [];
      } finally {
        PROJECT_AUTO.heartbeatHistoryLoadingByTask[key] = false;
      }
    }

    async function openHeartbeatHistoryDrawer(projectId, task) {
      const pid = String(projectId || "").trim();
      const row = (task && typeof task === "object") ? task : {};
      const heartbeatTaskId = String(row.heartbeat_task_id || row.heartbeatTaskId || "").trim();
      if (!pid || !heartbeatTaskId) return;
      openProjectAutoRecordDrawer(pid, {
        mode: "heartbeat",
        heartbeatTaskId,
        heartbeatTaskName: String(row.title || heartbeatTaskId).trim(),
      });
      await ensureProjectAutoHeartbeatHistory(pid, heartbeatTaskId, true);
      if (PROJECT_AUTO_UI.recordDrawerOpen && PROJECT_AUTO_UI.recordDrawerProjectId === pid) {
        renderProjectAutoRecordDrawer(pid);
      }
    }

    function heartbeatEditorSessionOptions(projectId, channelName) {
      const allSessions = getProjectAutoSessions(projectId);
      const inChannel = allSessions.filter((s) => {
        const chans = Array.isArray(s && s.channels) ? s.channels : [];
        return !channelName || chans.includes(channelName) || String((s && s.primaryChannel) || "") === String(channelName);
      });
      return inChannel.length ? inChannel : allSessions;
    }

    async function parseResponseDetail(resp) {
      // Prefer JSON error bodies produced by server.py (detail/error/message).
      try {
        const j = await resp.json().catch(() => null);
        const detail = j && (j.detail || j.error || j.message);
        if (detail) {
          // Handle object-type detail by extracting nested error or stringifying
          if (typeof detail === "object") {
            return detail.error || detail.message || JSON.stringify(detail);
          }
          return String(detail);
        }
      } catch (_) {}
      return String(resp.statusText || "");
    }

    function setHintText(mode, text) {
      const id = (mode === "conv") ? "convHint" : "ccbHint";
      const el = document.getElementById(id);
      if (el) el.textContent = String(text || "");
    }

    function normalizePanelMode(raw) {
      const m = String(raw || "").trim().toLowerCase();
      if (m === "conv") return "conv";
      if (m === "arch" || m === "g" || m === "a") return "arch";
      if (m === "org" || m === "og") return "org";
      if (m === "task" || m === "t") return "task";
      if (m === "channel" || m === "ops" || m === "o") return "channel";
      return "channel";
    }

    function isTaskItem(it) {
      return String((it && it.type) || "").trim() === "任务";
    }

    function isRequirementItem(it) {
      return String((it && it.type) || "").trim() === "需求";
    }

    function el(tag, attrs = {}, children = []) {
      const n = document.createElement(tag);
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") n.className = v;
        else if (k === "text") n.textContent = v;
        else if (k === "html") n.innerHTML = v;
        else if (k === "style") n.setAttribute("style", v);
        else n.setAttribute(k, v);
      }
      for (const c of children) n.appendChild(c);
      return n;
    }

    async function copyText(s) {
      const text = String(s || "");
      if (!text) return false;
      if (window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        try {
          await navigator.clipboard.writeText(text);
          return true;
        } catch (_) {}
      }
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "readonly");
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      ta.style.left = "-9999px";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      let ok = false;
      try {
        ok = !!document.execCommand("copy");
      } catch (_) {
        ok = false;
      }
      ta.remove();
      return ok;
    }

    function isHttpUrl(u) {
      return /^https?:\/\//i.test(String(u || ""));
    }

    function openNew(u) {
      const url = String(u || "").trim();
      if (!url) return;
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.target = "_blank";
        anchor.rel = "noopener";
        anchor.style.display = "none";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        return;
      } catch (_) {}
      try {
        const win = window.open("", "_blank");
        if (win) win.location.href = url;
      } catch (_) {}
    }

    function messageObjectViewerOpenUrl(target, item) {
      const direct = String((target && target.openUrl) || "").trim();
      if (direct) return direct;
      const path = String(((item && item.path) || (target && target.path) || (target && target.value) || "")).trim();
      if (!path) return "";
      if (/^https?:\/\//i.test(path)) return path;
      if (/^(\/\.runs\/|\/share\/)/.test(path)) return String(location.origin || "") + path;
      if (/^\//.test(path)) {
        const previewUrl = messageObjectViewerPreviewBlobUrl(target, item);
        if (previewUrl) return previewUrl;
        return String(location.origin || "") + "/api/fs/open?path=" + encodeURIComponent(path);
      }
      return "";
    }

    function messageObjectViewerPreviewBlobUrl(target, item) {
      const row = (item && typeof item === "object") ? item : null;
      if (!row || String(row.kind || "") !== "file" || !row.is_text) return "";
      const content = String(row.content || "");
      if (!content) return "";
      if (row.truncated) return "";
      let mime = String(row.mime_type || "text/plain").trim() || "text/plain";
      let body = content;
      const previewMode = String(row.preview_mode || "").trim().toLowerCase();
      if (previewMode === "markdown") {
        mime = "text/html;charset=utf-8";
        body = "<!doctype html><html><head><meta charset=\"utf-8\"><title>"
          + escapeHtml(String((target && target.label) || row.name || "预览"))
          + "</title><style>body{margin:24px auto;max-width:960px;padding:0 20px;color:#20242c;font:14px/1.7 -apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;}pre{white-space:pre-wrap;word-break:break-word;background:#f6f8fb;border:1px solid rgba(15,23,42,.08);border-radius:12px;padding:14px;}code{background:rgba(15,23,42,.06);padding:.12em .35em;border-radius:6px;}blockquote{margin:0;padding-left:12px;border-left:3px solid rgba(47,111,237,.28);color:rgba(0,0,0,.62);}</style></head><body>"
          + markdownToHtml(content)
          + "</body></html>";
      } else if (previewMode === "html") {
        mime = "text/html;charset=utf-8";
      } else if (mime.startsWith("text/") && !/charset=/i.test(mime)) {
        mime += ";charset=utf-8";
      } else if (previewMode === "code" || previewMode === "json" || previewMode === "text") {
        mime = "text/plain;charset=utf-8";
      }
      try {
        const blob = new Blob([body], { type: mime });
        const url = URL.createObjectURL(blob);
        window.setTimeout(() => {
          try { URL.revokeObjectURL(url); } catch (_) {}
        }, 60_000);
        return url;
      } catch (_) {
        return "";
      }
    }

    function shortTitle(t) {
      return String(t || "").replace(/^【[^】]+】\s*/, "");
    }

    function itemTypeLabelFromItem(it) {
      const direct = String((it && it.type) || "").trim();
      if (direct) return direct;
      const p = String((it && it.path) || "");
      if (p.includes("/任务/")) return "任务";
      if (p.includes("/需求/")) return "需求";
      if (p.includes("/问题/")) return "问题";
      if (p.includes("/讨论") || p.includes("/讨论空间/")) return "讨论";
      if (p.includes("/答复/")) return "答复";
      if (p.includes("/反馈/")) return "反馈";
      return "";
    }

    function itemTypeIconMeta(typeLabel) {
      const raw = String(typeLabel || "").trim();
      if (!raw) return { key: "other", label: "其他", glyph: "其" };
      if (raw.includes("任务")) return { key: "task", label: raw, glyph: "任" };
      if (raw.includes("需求")) return { key: "requirement", label: raw, glyph: "需" };
      if (raw.includes("问题")) return { key: "issue", label: raw, glyph: "问" };
      if (raw.includes("讨论")) return { key: "discussion", label: raw, glyph: "讨" };
      if (raw.includes("答复")) return { key: "reply", label: raw, glyph: "答" };
      if (raw.includes("反馈")) return { key: "feedback", label: raw, glyph: "反" };
      return { key: "other", label: raw, glyph: String(raw.slice(0, 1) || "其") };
    }

    function typeIconBadgeByLabel(typeLabel, extraClass = "") {
      const meta = itemTypeIconMeta(typeLabel);
      const cls = ["typeicon-badge", "typeicon-" + meta.key, extraClass].filter(Boolean).join(" ");
      const n = el("span", {
        class: cls,
        title: meta.label,
        "aria-label": meta.label,
      });
      n.appendChild(el("span", { class: "g", text: meta.glyph, "aria-hidden": "true" }));
      return n;
    }

    function buildItemTitleNode(it, titleClass = "t", opts = {}) {
      const wrap = el("div", { class: "item-titleline" + (opts.detail ? " detail" : "") });
      const typeLabel = itemTypeLabelFromItem(it);
      wrap.appendChild(typeIconBadgeByLabel(typeLabel || "其他"));
      wrap.appendChild(el("div", {
        class: titleClass,
        text: shortTitle(it && it.title),
        style: "flex:1;min-width:0;",
      }));
      return wrap;
    }

    function shortId(s) {
      const t = String(s || "");
      if (t.length <= 18) return t;
      return t.slice(0, 8) + "…" + t.slice(-4);
    }

    function shortDateTime(ts) {
      const raw = String(ts || "").trim();
      if (!raw) return "";
      const d = parseDateTime(raw);
      if (!d) return raw.replace("T", " ").replace(/\.\d+/, "").slice(0, 19);
      const pad2 = (n) => String(n).padStart(2, "0");
      return d.getFullYear()
        + "-" + pad2(d.getMonth() + 1)
        + "-" + pad2(d.getDate())
        + " " + pad2(d.getHours())
        + ":" + pad2(d.getMinutes())
        + ":" + pad2(d.getSeconds());
    }

    function parseDateTime(ts) {
      const raw = String(ts || "").trim();
      if (!raw) return null;
      let s = raw;
      // Normalize timezone like +0800 -> +08:00 for safer parsing.
      if (/[\+\-]\d{4}$/.test(s)) s = s.replace(/([\+\-]\d{2})(\d{2})$/, "$1:$2");
      const d = new Date(s);
      if (!Number.isNaN(d.getTime())) return d;
      const d2 = new Date(raw.replace(" ", "T"));
      if (!Number.isNaN(d2.getTime())) return d2;
      return null;
    }

    function imTime(ts) {
      const d = parseDateTime(ts);
      if (!d) return String(ts || "");
      const now = new Date();
      const pad2 = (n) => String(n).padStart(2, "0");
      const hm = pad2(d.getHours()) + ":" + pad2(d.getMinutes());

      const sameDay = d.getFullYear() === now.getFullYear()
        && d.getMonth() === now.getMonth()
        && d.getDate() === now.getDate();
      if (sameDay) return hm;

      const y = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
      const diffDays = Math.round((y - x) / 86400000);
      if (diffDays === 1) return "昨天 " + hm;
      if (d.getFullYear() === now.getFullYear()) return (d.getMonth() + 1) + "/" + d.getDate() + " " + hm;
      return d.getFullYear() + "/" + (d.getMonth() + 1) + "/" + d.getDate() + " " + hm;
    }

    function toTimeNum(ts) {
      const d = parseDateTime(ts);
      return d ? d.getTime() : -1;
    }

    function compactDateTime(ts) {
      const t = shortDateTime(ts);
      if (!t) return "";
      const m = t.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
      if (!m) return t;
      return m[2] + "-" + m[3] + " " + m[4] + ":" + m[5];
    }

    function zhDateTime(ts) {
      const d = parseDateTime(ts);
      if (!d) return shortDateTime(ts) || String(ts || "");
      const pad2 = (n) => String(n).padStart(2, "0");
      return d.getFullYear()
        + "年" + pad2(d.getMonth() + 1)
        + "月" + pad2(d.getDate())
        + "日 " + pad2(d.getHours())
        + ":" + pad2(d.getMinutes())
        + ":" + pad2(d.getSeconds());
    }

    function zhDurationBetween(startTs, endTs) {
      const s = toTimeNum(startTs);
      const e = toTimeNum(endTs);
      if (s < 0 || e < 0) return "";
      let sec = Math.round((e - s) / 1000);
      if (!Number.isFinite(sec) || sec < 0) sec = 0;
      const day = Math.floor(sec / 86400);
      sec -= day * 86400;
      const hour = Math.floor(sec / 3600);
      sec -= hour * 3600;
      const min = Math.floor(sec / 60);
      sec -= min * 60;
      if (day > 0) return day + "天" + hour + "小时" + min + "分";
      if (hour > 0) return hour + "小时" + min + "分";
      if (min > 0) return min + "分" + sec + "秒";
      return sec + "秒";
    }

    function truncateText(text, maxLen) {
      const t = String(text || "").trim();
      if (t.length <= maxLen) return t;
      return t.substring(0, maxLen) + "...";
    }

    function escapeHtml(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function mdInline(raw) {
      let s = escapeHtml(raw || "");
      const stash = [];
      const stashPush = (html) => {
        stash.push(String(html || ""));
        return "\u0000" + (stash.length - 1) + "\u0000";
      };
      s = s.replace(/`([^`]+)`/g, (_, code) => {
        return stashPush("<code>" + code + "</code>");
      });
      s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, text, url) => {
        const u = normalizeMarkdownLinkTarget(url);
        if (!u) return text;
        if (/^https?:\/\//i.test(u)) {
          return stashPush('<a href="' + escapeHtml(u) + '" target="_blank" rel="noopener noreferrer">' + text + "</a>");
        }
        const obj = classifyMessageObjectToken(u);
        if (!obj) return text;
        return stashPush(
          '<a href="' + escapeHtml(u) + '" data-msg-object-href="' + escapeHtml(u) + '">' + text + "</a>"
        );
      });
      s = s.replace(/(^|[\s(])(https?:\/\/[^\s<]+)/g, (_, pre, url) => {
        return pre + stashPush('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>");
      });
      s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
      s = s.replace(/~~([^~]+)~~/g, "<del>$1</del>");
      s = s.replace(/(^|[^\*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
      s = s.replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");
      s = s.replace(/\u0000(\d+)\u0000/g, (_, idx) => stash[Number(idx)] || "");
      return s;
    }

    function normalizeMarkdownLinkTarget(raw) {
      let u = String(raw || "").trim();
      if (!u) return "";
      u = u
        .replace(/^&lt;([\s\S]*)&gt;$/i, "$1")
        .replace(/^<([\s\S]*)>$/, "$1")
        .trim();
      return u
        .replace(/&amp;/g, "&")
        .replace(/&quot;/g, "\"")
        .replace(/&#39;/g, "'");
    }

    function splitMarkdownTableCells(raw) {
      let line = String(raw || "").trim();
      if (!line.includes("|")) return [];
      if (line.startsWith("|")) line = line.slice(1);
      if (line.endsWith("|")) line = line.slice(0, -1);
      const cells = [];
      let cell = "";
      let escaped = false;
      let inCode = false;
      for (let i = 0; i < line.length; i += 1) {
        const ch = line[i];
        if (escaped) {
          cell += ch;
          escaped = false;
          continue;
        }
        if (ch === "\\") {
          escaped = true;
          continue;
        }
        if (ch === "`") inCode = !inCode;
        if (ch === "|" && !inCode) {
          cells.push(cell.trim());
          cell = "";
          continue;
        }
        cell += ch;
      }
      if (escaped) cell += "\\";
      cells.push(cell.trim());
      return cells;
    }

    function parseMarkdownTableDivider(raw) {
      const cells = splitMarkdownTableCells(raw);
      if (cells.length < 2) return null;
      const alignments = [];
      for (const cell of cells) {
        const token = String(cell || "").replace(/\s+/g, "");
        if (!/^:?-{3,}:?$/.test(token)) return null;
        if (token.startsWith(":") && token.endsWith(":")) alignments.push("center");
        else if (token.endsWith(":")) alignments.push("right");
        else alignments.push("left");
      }
      return alignments;
    }

    function isMarkdownTableStart(lines, idx) {
      if (!Array.isArray(lines) || idx < 0 || idx + 1 >= lines.length) return false;
      const header = splitMarkdownTableCells(lines[idx]);
      const alignments = parseMarkdownTableDivider(lines[idx + 1]);
      return !!(header.length >= 2 && alignments && alignments.length >= 2);
    }

    function markdownTableCellHtml(tag, value, align) {
      const cls = align ? (' class="md-table-align-' + escapeHtml(align) + '"') : "";
      return "<" + tag + cls + ">" + mdInline(String(value || "")) + "</" + tag + ">";
    }

    function renderMarkdownTable(lines, startIdx) {
      const headers = splitMarkdownTableCells(lines[startIdx]);
      const alignments = parseMarkdownTableDivider(lines[startIdx + 1]) || [];
      const width = Math.max(headers.length, alignments.length);
      const rows = [];
      let idx = startIdx + 2;
      while (idx < lines.length) {
        const raw = String(lines[idx] || "");
        const t = raw.trim();
        if (!t || !t.includes("|")) break;
        if (parseMarkdownTableDivider(t)) break;
        const cells = splitMarkdownTableCells(t);
        if (cells.length < 2) break;
        rows.push(cells);
        idx += 1;
      }
      const normalizedHeaders = headers.slice();
      while (normalizedHeaders.length < width) normalizedHeaders.push("");
      const head = normalizedHeaders
        .slice(0, width)
        .map((cell, cellIdx) => markdownTableCellHtml("th", cell, alignments[cellIdx] || "left"))
        .join("");
      const body = rows
        .map((cells) => {
          const normalizedCells = cells.slice();
          while (normalizedCells.length < width) normalizedCells.push("");
          return "<tr>" + normalizedCells
            .slice(0, width)
            .map((cell, cellIdx) => markdownTableCellHtml("td", cell, alignments[cellIdx] || "left"))
            .join("") + "</tr>";
        })
        .join("");
      return {
        html: '<div class="md-table-wrap"><table class="md-table"><thead><tr>' + head + '</tr></thead><tbody>' + body + "</tbody></table></div>",
        nextIdx: idx,
      };
    }

    function renderMarkdownListItem(raw) {
      const text = String(raw || "").trim();
      const task = text.match(/^\[([ xX])\]\s+(.*)$/);
      if (task) {
        const checked = task[1].toLowerCase() === "x" ? " checked" : "";
        return '<li class="md-task-item"><input type="checkbox" disabled' + checked + "><span>" + mdInline(task[2]) + "</span></li>";
      }
      return "<li>" + mdInline(text) + "</li>";
    }

    function renderMarkdownCodeBlock(lines, lang) {
      const safeLang = String(lang || "").trim().replace(/[^\w-]/g, "").slice(0, 32);
      const langAttr = safeLang ? (' data-lang="' + escapeHtml(safeLang) + '"') : "";
      const codeClass = safeLang ? (' class="language-' + escapeHtml(safeLang) + '"') : "";
      return '<pre class="md-code"' + langAttr + "><code" + codeClass + ">" + escapeHtml(lines.join("\n")) + "</code></pre>";
    }

    function markdownToHtml(input) {
      const src = String(input || "").replace(/\r\n?/g, "\n");
      if (!src.trim()) return "";
      const lines = src.split("\n");
      const out = [];
      let paragraph = [];
      let listType = "";
      let listItems = [];
      let inCode = false;
      let codeLines = [];
      let codeLang = "";
      let quoteLines = [];

      function flushParagraph() {
        if (!paragraph.length) return;
        const text = paragraph.join("\n").trim();
        paragraph = [];
        if (!text) return;
        out.push("<p>" + mdInline(text).replace(/\n/g, "<br>") + "</p>");
      }
      function flushList() {
        if (!listItems.length || !listType) return;
        out.push("<" + listType + ' class="md-list">' + listItems.map((x) => renderMarkdownListItem(x)).join("") + "</" + listType + ">");
        listType = "";
        listItems = [];
      }
      function flushBlockquote() {
        if (!quoteLines.length) return;
        const text = quoteLines.join("\n").trim();
        quoteLines = [];
        if (!text) return;
        out.push("<blockquote>" + mdInline(text).replace(/\n/g, "<br>") + "</blockquote>");
      }
      function flushNormal() {
        flushParagraph();
        flushList();
        flushBlockquote();
      }

      for (let lineIdx = 0; lineIdx < lines.length; lineIdx += 1) {
        const ln = lines[lineIdx];
        const line = String(ln || "");
        if (inCode) {
          if (/^```/.test(line.trim())) {
            out.push(renderMarkdownCodeBlock(codeLines, codeLang));
            inCode = false;
            codeLines = [];
            codeLang = "";
          } else {
            codeLines.push(line);
          }
          continue;
        }

        const codeFence = line.trim().match(/^```([\w-]+)?\s*$/);
        if (codeFence) {
          flushNormal();
          inCode = true;
          codeLines = [];
          codeLang = codeFence[1] || "";
          continue;
        }

        const t = line.trim();
        if (!t) {
          flushNormal();
          continue;
        }

        if (/^[-*_]{3,}\s*$/.test(t)) {
          flushNormal();
          out.push('<hr class="md-hr">');
          continue;
        }

        if (isMarkdownTableStart(lines, lineIdx)) {
          flushNormal();
          const table = renderMarkdownTable(lines, lineIdx);
          out.push(table.html);
          lineIdx = Math.max(lineIdx, table.nextIdx - 1);
          continue;
        }

        let m = t.match(/^(#{1,6})\s+(.*)$/);
        if (m) {
          flushNormal();
          const lv = Math.min(6, Math.max(1, m[1].length));
          out.push("<h" + lv + ">" + mdInline(m[2]) + "</h" + lv + ">");
          continue;
        }

        m = t.match(/^[-*+]\s+(.*)$/);
        if (m) {
          flushParagraph();
          if (listType && listType !== "ul") flushList();
          listType = "ul";
          listItems.push(m[1]);
          continue;
        }

        m = t.match(/^\d+\.\s+(.*)$/);
        if (m) {
          flushParagraph();
          if (listType && listType !== "ol") flushList();
          listType = "ol";
          listItems.push(m[1]);
          continue;
        }

        m = t.match(/^>\s?(.*)$/);
        if (m) {
          flushParagraph();
          flushList();
          quoteLines.push(m[1]);
          continue;
        }

        if (listItems.length) flushList();
        if (quoteLines.length) flushBlockquote();
        paragraph.push(line);
      }

      flushNormal();
      if (inCode) out.push(renderMarkdownCodeBlock(codeLines, codeLang));
      return out.join("");
    }

    function setMarkdown(elNode, text, fallback = "") {
      if (!elNode) return;
      const src = String(text || "").trim() ? String(text || "") : String(fallback || "");
      elNode.innerHTML = markdownToHtml(src);
      if (typeof enhanceMessageInteractiveObjects === "function") {
        enhanceMessageInteractiveObjects(elNode, { force: true });
      }
    }

    const MESSAGE_OBJECT_TOKEN_RE = /(https?:\/\/[^\s<>"']+|\/share\/[^\s<>"']+|\/\.runs\/[^\s<>"']+|\/(?:Users|Volumes|private|tmp|var|opt|Applications|Library|System)[^\s<>"']+|(?:web|docs|tests|static_sites|task_dashboard|任务规划|\.runs|\.run)(?:\/[^\s<>"']+)+)/g;
    const MESSAGE_OBJECT_FILE_EXT_BOUNDARY_RE = /\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)(?:[?#][^\s<>"']*)?(?=$|[\s),.;:!?，。；：！？、」』】》〉])/i;
    const MESSAGE_OBJECT_EXTENDABLE_PATH_ROOT_RE = /^(?:\/(?:Users|Volumes|private|tmp|var|opt|Applications|Library|System)(?:\/|$)|(?:web|docs|tests|static_sites|task_dashboard|任务规划|\.runs|\.run)(?:\/|$))/;
    const MESSAGE_OBJECT_EXTENDED_FORBIDDEN_RE = /[<>"'`]/;
    const MESSAGE_OBJECT_PATH_LINE_SUFFIX_RE = /^(.*\.(?:md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)):(\d+)(?::(\d+))?$/i;
    const MESSAGE_OBJECT_TRAILING_PUNCT_RE = /[),.;:!?，。；：！？、」』】》〉]+$/;
    const MESSAGE_OBJECT_RELATIVE_ROOT_RE = /^(?:web|docs|tests|static_sites|task_dashboard|任务规划|\.runs|\.run)(?:\/.+)+$/;
    const MESSAGE_OBJECT_VIEWER = {
      open: false,
      loading: false,
      target: null,
      item: null,
      error: "",
    };
    let TASK_DASHBOARD_ROOT_PATH_CACHE = "";

    function trimMessageObjectToken(raw) {
      const src = String(raw || "");
      if (!src) return { core: "", tail: "" };
      const tailMatch = src.match(MESSAGE_OBJECT_TRAILING_PUNCT_RE);
      if (!tailMatch) return { core: src, tail: "" };
      const tail = String(tailMatch[0] || "");
      return {
        core: src.slice(0, src.length - tail.length),
        tail,
      };
    }

    function isLikelyWorkspaceRelativePath(token) {
      return MESSAGE_OBJECT_RELATIVE_ROOT_RE.test(String(token || "").trim());
    }

    function guessTaskDashboardRootPath() {
      if (TASK_DASHBOARD_ROOT_PATH_CACHE) return TASK_DASHBOARD_ROOT_PATH_CACHE;
      try {
        if (typeof resolveProjectRootPath === "function") {
          const direct = String(resolveProjectRootPath("task_dashboard") || resolveProjectRootPath(STATE.project) || "").trim();
          if (direct) {
            TASK_DASHBOARD_ROOT_PATH_CACHE = direct.replace(/\/+$/, "");
            return TASK_DASHBOARD_ROOT_PATH_CACHE;
          }
        }
      } catch (_) {}
      const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
      for (const proj of projects) {
        const items = Array.isArray(proj && proj.items) ? proj.items : [];
        for (const it of items) {
          const p = String((it && it.path) || "").trim();
          if (!p || p[0] !== "/") continue;
          const idx = p.lastIndexOf("/task-dashboard/");
          if (idx >= 0) {
            TASK_DASHBOARD_ROOT_PATH_CACHE = p.slice(0, idx + "/task-dashboard".length);
            return TASK_DASHBOARD_ROOT_PATH_CACHE;
          }
        }
      }
      return "";
    }

    function decodeMessageObjectFsPath(raw) {
      let src = String(raw || "").trim();
      if (!src || src.indexOf("%") < 0) return src;
      for (let i = 0; i < 2; i += 1) {
        try {
          const next = decodeURIComponent(src);
          if (!next || next === src) break;
          src = next;
          continue;
        } catch (_) {}
        try {
          const next = decodeURI(src);
          if (!next || next === src) break;
          src = next;
        } catch (_) {}
        break;
      }
      return src;
    }

    function stripMessageObjectPathLineSuffix(raw) {
      const src = String(raw || "").trim();
      if (!src || src.indexOf(":") < 0) return src;
      const match = src.match(MESSAGE_OBJECT_PATH_LINE_SUFFIX_RE);
      return match ? String(match[1] || "") : src;
    }

    function resolveMessageObjectPath(path) {
      const src = stripMessageObjectPathLineSuffix(decodeMessageObjectFsPath(path));
      if (!src || src[0] === "/" || !isLikelyWorkspaceRelativePath(src)) return src;
      const root = guessTaskDashboardRootPath();
      if (!root) return src;
      return root.replace(/\/$/, "") + "/" + src.replace(/^\/+/, "");
    }

    function normalizeMessageObjectLookupText(raw) {
      return decodeMessageObjectFsPath(raw)
        .replace(/[?#].*$/, "")
        .split(/[\\/]/)
        .pop()
        .replace(/\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)$/i, "")
        .toLowerCase()
        .replace(/[^\u4e00-\u9fa5a-z0-9]+/g, "");
    }

    function messageObjectPathExt(raw) {
      const src = stripMessageObjectPathLineSuffix(decodeMessageObjectFsPath(raw).replace(/[?#].*$/, ""));
      const m = src.match(/\.([a-z0-9]+)$/i);
      return m ? String(m[1] || "").toLowerCase() : "";
    }

    function shouldExtendMessageObjectToken(raw) {
      const src = String(raw || "").trim();
      if (!src || /^https?:\/\//i.test(src) || /^\/share\//.test(src)) return false;
      if (!MESSAGE_OBJECT_EXTENDABLE_PATH_ROOT_RE.test(src)) return false;
      return !messageObjectPathExt(src);
    }

    function extendMessageObjectTokenAt(src, start, raw) {
      const initial = String(raw || "");
      if (!shouldExtendMessageObjectToken(initial)) return initial;
      const rest = String(src || "").slice(Number(start) || 0);
      if (rest.length <= initial.length) return initial;
      const lineBreakIndex = rest.search(/\n/);
      const line = lineBreakIndex >= 0 ? rest.slice(0, lineBreakIndex) : rest;
      const match = MESSAGE_OBJECT_FILE_EXT_BOUNDARY_RE.exec(line);
      if (!match) return initial;
      const end = Number(match.index || 0) + String(match[0] || "").length;
      if (end <= initial.length) return initial;
      const candidate = line.slice(0, end);
      if (MESSAGE_OBJECT_EXTENDED_FORBIDDEN_RE.test(candidate)) return initial;
      const trimmed = trimMessageObjectToken(candidate).core;
      if (!trimmed || trimmed.length <= initial.length) return initial;
      return classifyMessageObjectToken(trimmed) ? candidate : initial;
    }

    function isLooseMessageObjectSubsequence(needle, haystack) {
      const a = String(needle || "");
      const b = String(haystack || "");
      if (!a || !b || a.length > b.length) return false;
      let i = 0;
      for (let j = 0; j < b.length; j += 1) {
        if (a[i] === b[j]) i += 1;
        if (i >= a.length) return true;
      }
      return false;
    }

    function scoreMessageObjectFallbackEntry(target, entry) {
      const entryName = String(entry && entry.name || "").trim();
      const entryKey = normalizeMessageObjectLookupText(entryName);
      if (!entryKey) return -1;
      const pathKey = normalizeMessageObjectLookupText((target && (target.path || target.value)) || "");
      const labelKey = normalizeMessageObjectLookupText((target && (target.lookupLabel || target.label)) || "");
      let score = 0;
      if (pathKey && entryKey === pathKey) score = Math.max(score, 100);
      if (labelKey && entryKey === labelKey) score = Math.max(score, 96);
      if (pathKey && (entryKey.includes(pathKey) || pathKey.includes(entryKey))) score = Math.max(score, 88);
      if (labelKey && (entryKey.includes(labelKey) || labelKey.includes(entryKey))) score = Math.max(score, 84);
      if (pathKey && isLooseMessageObjectSubsequence(pathKey, entryKey)) score = Math.max(score, 76);
      if (labelKey && isLooseMessageObjectSubsequence(labelKey, entryKey)) score = Math.max(score, 72);
      const wantExt = messageObjectPathExt((target && (target.path || target.value || target.label)) || "");
      const gotExt = messageObjectPathExt(entryName);
      if (wantExt && gotExt && wantExt === gotExt) score += 4;
      return score;
    }

    async function readMessageObjectPathItem(path) {
      const normalizedPath = resolveMessageObjectPath(path);
      const qs = new URLSearchParams({ path: String(normalizedPath || "") });
      const resp = await fetch("/api/fs/read?" + qs.toString(), {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        const err = new Error(detail || ("HTTP " + resp.status));
        err.status = resp.status;
        err.detail = detail || "";
        err.path = normalizedPath;
        throw err;
      }
      const data = await resp.json().catch(() => ({}));
      return {
        path: normalizedPath,
        item: data && data.item ? data.item : null,
      };
    }

    async function tryResolveMessageObjectPathFallback(target) {
      const basePath = resolveMessageObjectPath((target && (target.path || target.value)) || "");
      if (!basePath || basePath[0] !== "/") return null;
      const slash = basePath.lastIndexOf("/");
      if (slash <= 0) return null;
      const parentPath = basePath.slice(0, slash) || "/";
      let dirRead = null;
      try {
        dirRead = await readMessageObjectPathItem(parentPath);
      } catch (_) {
        return null;
      }
      const dirItem = dirRead && dirRead.item;
      if (!dirItem || String(dirItem.kind || "") !== "dir") return null;
      const entries = Array.isArray(dirItem.entries) ? dirItem.entries : [];
      let best = null;
      entries.forEach((entry) => {
        if (!entry || !String(entry.name || "").trim()) return;
        const score = scoreMessageObjectFallbackEntry(target, entry);
        if (score < 72) return;
        if (!best || score > best.score) best = { entry, score };
      });
      if (!best || !best.entry) return null;
      const correctedPath = parentPath.replace(/\/+$/, "") + "/" + String(best.entry.name || "").trim();
      const correctedRead = await readMessageObjectPathItem(correctedPath);
      const nextTarget = Object.assign({}, target || {}, {
        path: correctedRead.path,
        value: correctedRead.path,
        label: String((target && target.label) || best.entry.name || "").trim() || String(best.entry.name || ""),
      });
      return {
        target: nextTarget,
        item: correctedRead.item,
      };
    }

    function isImagePathLike(value) {
      const src = String(value || "").trim().toLowerCase();
      return /\.(png|jpe?g|gif|webp|bmp|svg)(?:\?.*)?$/.test(src);
    }

    function isShareLikeUrl(value) {
      try {
        const u = new URL(String(value || ""), location.origin);
        return u.origin === location.origin && /^\/share\//.test(u.pathname || "");
      } catch (_) {
        return false;
      }
    }

    function isRunAttachmentLikeUrl(value) {
      try {
        const u = new URL(String(value || ""), location.origin);
        return u.origin === location.origin && /^\/\.runs\//.test(u.pathname || "");
      } catch (_) {
        return false;
      }
    }

    function classifyMessageObjectToken(raw) {
      const token = String(raw || "").trim();
      if (!token) return null;
      if (isHttpUrl(token)) {
        if (isRunAttachmentLikeUrl(token)) {
          const u = new URL(token, location.origin);
          return {
            kind: "attachment_url",
            tone: "attach",
            value: token,
            label: token,
            path: String(u.pathname || ""),
            openUrl: token,
            defaultAction: isImagePathLike(token) ? "preview_image" : "open_url",
          };
        }
        return {
          kind: isShareLikeUrl(token) ? "share_url" : "url",
          tone: "url",
          value: token,
          label: token,
          openUrl: token,
          defaultAction: "open_url",
        };
      }
      if (/^\/\.runs\//.test(token)) {
        const openUrl = location.origin + token;
        return {
          kind: "attachment_path",
          tone: "attach",
          value: token,
          label: token,
          path: token,
          openUrl,
          defaultAction: isImagePathLike(token) ? "preview_image" : "open_url",
        };
      }
      if (/^\/share\//.test(token)) {
        return {
          kind: "share_path",
          tone: "url",
          value: token,
          label: token,
          openUrl: location.origin + token,
          defaultAction: "open_url",
        };
      }
      if (/^\//.test(token)) {
        const path = stripMessageObjectPathLineSuffix(token);
        return {
          kind: "fs_path",
          tone: "file",
          value: token,
          label: token,
          path,
          defaultAction: "preview_path",
        };
      }
      if (isLikelyWorkspaceRelativePath(token)) {
        const path = resolveMessageObjectPath(token);
        return {
          kind: "fs_path",
          tone: token.includes(".") ? "file" : "dir",
          value: token,
          label: token,
          path,
          defaultAction: "preview_path",
        };
      }
      return null;
    }

    function createMessageObjectInlineNode(obj) {
      const node = el("button", {
        class: "msg-object-link tone-" + String(obj.tone || "file"),
        type: "button",
        title: String(obj.value || obj.label || ""),
      });
      node.__messageObject = obj;
      node.textContent = String(obj.label || obj.value || "");
      node.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        activateMessageObject(obj);
      });
      return node;
    }

    function bindMessageObjectActivator(node, obj) {
      if (!node || !obj) return;
      node.__messageObject = obj;
      if (node.__messageObjectBound) return;
      node.__messageObjectBound = true;
      node.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        activateMessageObject(obj);
      });
      node.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        e.stopPropagation();
        activateMessageObject(obj);
      });
    }

    function splitTextByMessageObjects(text) {
      const src = String(text || "");
      if (!src) return null;
      const out = [];
      let matched = false;
      let lastIndex = 0;
      MESSAGE_OBJECT_TOKEN_RE.lastIndex = 0;
      let m;
      while ((m = MESSAGE_OBJECT_TOKEN_RE.exec(src))) {
        const raw = extendMessageObjectTokenAt(src, m.index, String(m[0] || ""));
        const start = Number(m.index || 0);
        const trimmed = trimMessageObjectToken(raw);
        const obj = classifyMessageObjectToken(trimmed.core);
        if (!obj) continue;
        matched = true;
        if (start > lastIndex) out.push({ type: "text", value: src.slice(lastIndex, start) });
        out.push({ type: "object", value: trimmed.core, object: obj });
        if (trimmed.tail) out.push({ type: "text", value: trimmed.tail });
        lastIndex = start + raw.length;
        MESSAGE_OBJECT_TOKEN_RE.lastIndex = lastIndex;
      }
      if (!matched) return null;
      if (lastIndex < src.length) out.push({ type: "text", value: src.slice(lastIndex) });
      return out;
    }

    function enhanceTextNodeWithMessageObjects(textNode) {
      if (!textNode || !textNode.parentNode) return false;
      const segments = splitTextByMessageObjects(textNode.nodeValue || "");
      if (!segments || !segments.length) return false;
      const frag = document.createDocumentFragment();
      segments.forEach((seg) => {
        if (seg.type === "text") frag.appendChild(document.createTextNode(String(seg.value || "")));
        else if (seg.type === "object") frag.appendChild(createMessageObjectInlineNode(seg.object));
      });
      textNode.parentNode.replaceChild(frag, textNode);
      return true;
    }

    function enhanceAnchorMessageObject(anchor) {
      if (!anchor) return;
      const href = String(
        anchor.getAttribute("data-msg-object-href")
        || anchor.getAttribute("href")
        || anchor.href
        || ""
      ).trim();
      const obj = classifyMessageObjectToken(href);
      if (!obj) return;
      anchor.classList.add("msg-object-link", "tone-" + String(obj.tone || "url"), "is-anchor");
      anchor.title = String(obj.value || href || "");
      bindMessageObjectActivator(anchor, obj);
    }

    function enhanceCodeMessageObject(codeEl) {
      if (!codeEl || codeEl.__messageObjectEnhanced) return;
      const raw = String(codeEl.textContent || "").trim();
      if (!raw) return;
      const trimmed = trimMessageObjectToken(raw);
      if (!trimmed.core || trimmed.core !== raw) return;
      const obj = classifyMessageObjectToken(trimmed.core);
      if (!obj) return;
      codeEl.__messageObjectEnhanced = true;
      const parentPre = codeEl.parentElement && codeEl.parentElement.tagName === "PRE" ? codeEl.parentElement : null;
      const target = parentPre && parentPre.childElementCount === 1 ? parentPre : codeEl;
      target.__messageObject = obj;
      target.classList.add("msg-object-code-target", "tone-" + String(obj.tone || "file"));
      target.setAttribute("title", String(obj.value || obj.label || ""));
      if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "0");
      if (!target.hasAttribute("role")) target.setAttribute("role", "button");
      bindMessageObjectActivator(target, obj);
    }

    function enhanceMessageInteractiveObjects(root, opts = {}) {
      const force = !!(opts && opts.force);
      if (!root || !root.querySelectorAll || (root.__messageObjectsEnhanced && !force)) return;
      root.__messageObjectsEnhanced = true;
      Array.from(root.querySelectorAll("a[href]")).forEach((anchor) => enhanceAnchorMessageObject(anchor));
      Array.from(root.querySelectorAll("code")).forEach((codeEl) => enhanceCodeMessageObject(codeEl));
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          if (!node || !node.parentElement) return NodeFilter.FILTER_REJECT;
          const parent = node.parentElement;
          if (parent.closest("a, button, pre, code, script, style")) return NodeFilter.FILTER_REJECT;
          return String(node.nodeValue || "").trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        },
      });
      const nodes = [];
      let current;
      while ((current = walker.nextNode())) nodes.push(current);
      nodes.forEach((node) => { enhanceTextNodeWithMessageObjects(node); });
    }

    function ensureMessageObjectViewer() {
      let mask = document.getElementById("msgObjectViewerMask");
      if (mask) return mask;
      mask = document.createElement("div");
      mask.className = "msgobj-viewer-mask";
      mask.id = "msgObjectViewerMask";
      mask.innerHTML = `
        <div class="msgobj-viewer-dialog" role="dialog" aria-modal="true" aria-label="对象预览">
          <div class="msgobj-viewer-head">
            <div class="msgobj-viewer-titlewrap">
              <div class="msgobj-viewer-kicker" id="msgObjectViewerKicker">对象预览</div>
              <div class="msgobj-viewer-title" id="msgObjectViewerTitle">-</div>
              <div class="msgobj-viewer-sub" id="msgObjectViewerSub">-</div>
            </div>
            <div class="msgobj-viewer-actions">
              <button class="btn msgobj-viewer-star" id="msgObjectViewerStarBtn" type="button">☆ 收藏</button>
              <button class="btn" id="msgObjectViewerOpenTabBtn" type="button">新标签打开</button>
              <button class="btn" id="msgObjectViewerCopyBtn" type="button">复制</button>
              <button class="btn" id="msgObjectViewerRevealBtn" type="button">定位 Finder</button>
              <button class="btn" id="msgObjectViewerCloseBtn" type="button">关闭</button>
            </div>
          </div>
          <div class="msgobj-viewer-body" id="msgObjectViewerBody"></div>
        </div>
      `;
      document.body.appendChild(mask);
      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeMessageObjectViewer();
      });
      const closeBtn = document.getElementById("msgObjectViewerCloseBtn");
      if (closeBtn) closeBtn.addEventListener("click", closeMessageObjectViewer);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && MESSAGE_OBJECT_VIEWER.open) closeMessageObjectViewer();
      });
      return mask;
    }

    function messageObjectViewerConversationFileState(target) {
      const rawTarget = (target && typeof target === "object") ? target : {};
      const sessionKey = typeof currentConvComposerDraftKey === "function"
        ? String(currentConvComposerDraftKey() || "").trim()
        : "";
      let fileKey = String(rawTarget.conversationFileKey || rawTarget.fileKey || "").trim();
      if (!fileKey
        && typeof isCollectableConversationFileObject === "function"
        && typeof buildConversationFileObjectKey === "function"
        && isCollectableConversationFileObject(rawTarget)) {
        fileKey = String(buildConversationFileObjectKey(rawTarget) || "").trim();
      }
      if (!sessionKey || !fileKey || typeof getConversationFileStarredMapByKey !== "function") {
        return {
          available: false,
          sessionKey,
          fileKey,
          starred: false,
        };
      }
      const starredMap = getConversationFileStarredMapByKey(sessionKey);
      return {
        available: true,
        sessionKey,
        fileKey,
        starred: !!(starredMap && starredMap[fileKey]),
      };
    }

    function toggleMessageObjectViewerConversationFileStar() {
      const target = MESSAGE_OBJECT_VIEWER.target;
      const state = messageObjectViewerConversationFileState(target);
      if (!state.available || typeof toggleConversationFileStar !== "function") return;
      const nextStarred = !state.starred;
      toggleConversationFileStar(state.sessionKey, state.fileKey);
      if (typeof refreshConversationFilesFromCurrentTimeline === "function") {
        refreshConversationFilesFromCurrentTimeline();
      } else if (typeof renderConversationFileUi === "function") {
        renderConversationFileUi();
      }
      renderMessageObjectViewer();
      if (typeof setHintText === "function") {
        setHintText("conv", nextStarred ? "已加入会话文件收藏" : "已取消会话文件收藏");
      }
    }

    function isMessageObjectViewerImageEntry(entry) {
      if (!entry || typeof entry !== "object") return false;
      if (String(entry.kind || "file").trim() !== "file") return false;
      if (entry.is_image === true) return true;
      const mimeType = String(entry.mime_type || "").trim().toLowerCase();
      if (mimeType.startsWith("image/")) return true;
      return false;
    }

    function messageObjectViewerImageEntries(item) {
      const entries = Array.isArray(item && item.entries) ? item.entries : [];
      return entries.filter((entry) => String((entry && entry.kind) || "").trim() === "file" && isMessageObjectViewerImageEntry(entry));
    }

    function messageObjectViewerImageCaption(entry) {
      const name = String((entry && entry.name) || "").trim();
      const path = String((entry && entry.path) || "").trim();
      return name || path || "图片";
    }

    function renderMessageObjectViewerImageStage(entry, opts = {}) {
      const target = opts && typeof opts === "object" ? (opts.target || null) : null;
      const item = opts && typeof opts === "object" ? (opts.item || entry || null) : (entry || null);
      const src = String(messageObjectViewerOpenUrl(target, item) || "").trim();
      if (!src) return null;
      const caption = messageObjectViewerImageCaption(entry || item);
      const stage = el("div", { class: "msgobj-image-stage" });
      const imageBtn = el("button", {
        class: "msgobj-image-mainbtn",
        type: "button",
        title: "点击放大预览",
      });
      imageBtn.addEventListener("click", () => {
        openImagePreview(src, caption);
      });
      imageBtn.appendChild(el("img", {
        class: "msgobj-image-main",
        src,
        alt: caption,
      }));
      stage.appendChild(imageBtn);
      const meta = el("div", { class: "msgobj-image-stage-meta" });
      meta.appendChild(el("div", { class: "msgobj-image-stage-name", text: caption }));
      const metaBits = [];
      const mimeType = String(((entry || item) && (entry || item).mime_type) || "").trim();
      if (mimeType) metaBits.push(mimeType);
      const size = Number(((entry || item) && (entry || item).size) || 0);
      if (size > 0) metaBits.push(formatBytes(size));
      if (metaBits.length) {
        meta.appendChild(el("div", { class: "msgobj-image-stage-sub", text: metaBits.join(" · ") }));
      }
      stage.appendChild(meta);
      return stage;
    }

    function renderMessageObjectViewerImageGrid(entries) {
      const rows = Array.isArray(entries) ? entries.filter(Boolean) : [];
      if (!rows.length) return null;
      const wrap = el("div", { class: "msgobj-image-grid-wrap" });
      wrap.appendChild(el("div", { class: "msgobj-image-grid-title", text: "图片预览" }));
      const grid = el("div", { class: "msgobj-image-grid" });
      rows.forEach((entry) => {
        const src = String(messageObjectViewerOpenUrl(null, entry) || "").trim();
        if (!src) return;
        const caption = messageObjectViewerImageCaption(entry);
        const card = el("button", {
          class: "msgobj-image-card",
          type: "button",
          title: "点击放大预览",
        });
        card.addEventListener("click", () => {
          openImagePreview(src, caption);
        });
        card.appendChild(el("img", {
          class: "msgobj-image-thumb",
          src,
          alt: caption,
        }));
        const info = el("div", { class: "msgobj-image-card-info" });
        info.appendChild(el("div", { class: "msgobj-image-name", text: caption }));
        const metaBits = [];
        const mimeType = String(entry.mime_type || "").trim();
        if (mimeType) metaBits.push(mimeType);
        if (metaBits.length) info.appendChild(el("div", { class: "msgobj-image-sub", text: metaBits.join(" · ") }));
        card.appendChild(info);
        grid.appendChild(card);
      });
      if (!grid.childNodes.length) return null;
      wrap.appendChild(grid);
      return wrap;
    }

    function renderMessageObjectViewerBody() {
      const body = document.getElementById("msgObjectViewerBody");
      if (!body) return;
      body.innerHTML = "";
      if (MESSAGE_OBJECT_VIEWER.loading) {
        body.appendChild(el("div", { class: "hint", text: "对象加载中..." }));
        return;
      }
      if (MESSAGE_OBJECT_VIEWER.error) {
        body.appendChild(el("div", { class: "hint", text: MESSAGE_OBJECT_VIEWER.error }));
        return;
      }
      const item = MESSAGE_OBJECT_VIEWER.item;
      if (!item || typeof item !== "object") {
        body.appendChild(el("div", { class: "hint", text: "当前对象暂无可展示内容。" }));
        return;
      }
      if (String(item.kind || "") === "dir") {
        const meta = el("div", { class: "msgobj-meta-grid" });
        meta.appendChild(el("div", { class: "msgobj-meta-card", html: "<div class=\"k\">目录</div><div class=\"v\">" + escapeHtml(String(item.path || "")) + "</div>" }));
        meta.appendChild(el("div", { class: "msgobj-meta-card", html: "<div class=\"k\">条目数</div><div class=\"v\">" + String(item.entry_count || 0) + (item.truncated ? "（已截断）" : "") + "</div>" }));
        body.appendChild(meta);
        const imageGrid = renderMessageObjectViewerImageGrid(messageObjectViewerImageEntries(item));
        if (imageGrid) body.appendChild(imageGrid);
        const list = el("div", { class: "msgobj-dir-list" });
        const entries = Array.isArray(item.entries) ? item.entries : [];
        const listEntries = imageGrid
          ? entries.filter((row) => !isMessageObjectViewerImageEntry(row))
          : entries;
        if (!listEntries.length) {
          list.appendChild(el("div", { class: "hint", text: imageGrid ? "目录内仅包含图片条目。" : "目录为空。" }));
        } else {
          if (imageGrid) {
            body.appendChild(el("div", { class: "msgobj-image-grid-title", text: "其余条目" }));
          }
          listEntries.forEach((row) => {
            const name = String((row && row.name) || "").trim() || "-";
            const kind = String((row && row.kind) || "file").trim();
            const itemNode = el("div", { class: "msgobj-dir-item" });
            itemNode.appendChild(el("span", { class: "msgobj-dir-kind", text: kind === "dir" ? "目录" : "文件" }));
            itemNode.appendChild(el("span", { class: "msgobj-dir-name", text: name }));
            list.appendChild(itemNode);
          });
        }
        body.appendChild(list);
        return;
      }
      if (item.is_image) {
        const imageStage = renderMessageObjectViewerImageStage(item, { target: MESSAGE_OBJECT_VIEWER.target, item });
        if (imageStage) {
          body.appendChild(imageStage);
          return;
        }
        body.appendChild(el("div", {
          class: "hint",
          text: "当前识别为图片文件，但未拿到可访问预览地址；建议直接新标签打开或 Finder 定位。",
        }));
        return;
      }
      if (!item.is_text) {
        body.appendChild(el("div", { class: "hint", text: "当前对象不是文本文件，暂不展示正文预览。" }));
        return;
      }
      const mode = String(item.preview_mode || "text");
      if (mode === "markdown") {
        const box = el("div", { class: "msgobj-preview mdview" });
        box.innerHTML = markdownToHtml(String(item.content || ""));
        if (typeof enhanceMessageInteractiveObjects === "function") {
          enhanceMessageInteractiveObjects(box, { force: true });
        }
        body.appendChild(box);
        return;
      }
      if (mode === "html") {
        if (item.truncated) {
          body.appendChild(el("div", {
            class: "hint",
            text: "当前 HTML 预览内容已截断，下面为截断后的安全渲染结果；如需完整查看，建议直接打开文件。",
          }));
        }
        const frameWrap = el("div", { class: "msgobj-html-preview-wrap" });
        const frame = el("iframe", {
          class: "msgobj-html-preview",
          sandbox: "",
          referrerpolicy: "no-referrer",
          title: String(item.name || item.path || "HTML 预览"),
        });
        try {
          frame.srcdoc = String(item.content || "");
        } catch (_) {
          frame.srcdoc = "<!doctype html><html><body><pre>HTML 预览加载失败</pre></body></html>";
        }
        frameWrap.appendChild(frame);
        body.appendChild(frameWrap);
        return;
      }
      const pre = el("pre", { class: "msgobj-preview-pre" });
      pre.textContent = String(item.content || "");
      body.appendChild(pre);
    }

    function renderMessageObjectViewer() {
      const mask = ensureMessageObjectViewer();
      const title = document.getElementById("msgObjectViewerTitle");
      const sub = document.getElementById("msgObjectViewerSub");
      const kicker = document.getElementById("msgObjectViewerKicker");
      const starBtn = document.getElementById("msgObjectViewerStarBtn");
      const openTabBtn = document.getElementById("msgObjectViewerOpenTabBtn");
      const copyBtn = document.getElementById("msgObjectViewerCopyBtn");
      const revealBtn = document.getElementById("msgObjectViewerRevealBtn");
      if (!mask || !title || !sub || !kicker || !starBtn || !openTabBtn || !copyBtn || !revealBtn) return;
      const target = MESSAGE_OBJECT_VIEWER.target || {};
      title.textContent = String(target.label || target.value || "对象预览");
      kicker.textContent = String(target.kind === "fs_path" ? "路径预览" : "对象预览");
      const item = MESSAGE_OBJECT_VIEWER.item;
      if (item && typeof item === "object") {
        const itemKind = String(item.kind || "file");
        sub.textContent = itemKind === "dir"
          ? ("目录 · " + String(item.path || ""))
          : ([
              String(item.mime_type || "") || "文件",
              Number(item.size || 0) > 0 ? formatBytes(Number(item.size || 0)) : "",
              String(item.path || ""),
            ].filter(Boolean).join(" · "));
      } else if (MESSAGE_OBJECT_VIEWER.error) {
        sub.textContent = MESSAGE_OBJECT_VIEWER.error;
      } else {
        sub.textContent = String(target.value || "");
      }
      const starState = messageObjectViewerConversationFileState(target);
      starBtn.style.display = starState.available ? "" : "none";
      starBtn.disabled = !starState.available;
      starBtn.classList.toggle("active", !!starState.starred);
      starBtn.textContent = starState.starred ? "★ 已收藏" : "☆ 收藏";
      starBtn.title = starState.starred ? "取消会话文件收藏" : "加入会话文件收藏";
      starBtn.onclick = starState.available ? toggleMessageObjectViewerConversationFileStar : null;
      const openUrl = messageObjectViewerOpenUrl(target, item);
      const canOpenInNewTab = !!openUrl && String((item && item.kind) || "").trim() !== "dir";
      openTabBtn.disabled = !canOpenInNewTab;
      openTabBtn.title = canOpenInNewTab ? "在新标签页打开当前对象" : "当前对象暂不支持新标签页打开";
      openTabBtn.onclick = () => {
        if (!canOpenInNewTab) return;
        openNew(openUrl);
      };
      copyBtn.onclick = () => copyText(String((item && item.path) || target.value || ""));
      revealBtn.disabled = !String(target.path || (item && item.path) || "").trim();
      revealBtn.onclick = async () => {
        const path = String(target.path || (item && item.path) || "").trim();
        if (!path) return;
        try {
          const resp = await fetch("/api/fs/reveal", {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ path }),
          });
          if (!resp.ok) throw new Error((await parseResponseDetail(resp)) || ("HTTP " + resp.status));
          setHintText("conv", "已打开 Finder 定位");
        } catch (err) {
          setHintText("conv", "打开 Finder 失败：" + String((err && err.message) || err || "未知错误"));
        }
      };
      renderMessageObjectViewerBody();
      mask.classList.toggle("show", !!MESSAGE_OBJECT_VIEWER.open);
    }

    function closeMessageObjectViewer() {
      MESSAGE_OBJECT_VIEWER.open = false;
      MESSAGE_OBJECT_VIEWER.loading = false;
      MESSAGE_OBJECT_VIEWER.target = null;
      MESSAGE_OBJECT_VIEWER.item = null;
      MESSAGE_OBJECT_VIEWER.error = "";
      renderMessageObjectViewer();
    }

    async function openMessageObjectViewer(target) {
      const obj = (target && typeof target === "object") ? target : null;
      if (!obj) return;
      const nextTarget = Object.assign({}, obj);
      if (typeof isCollectableConversationFileObject === "function"
        && typeof buildConversationFileObjectKey === "function"
        && isCollectableConversationFileObject(obj)) {
        nextTarget.conversationFileKey = String(
          obj.conversationFileKey || obj.fileKey || buildConversationFileObjectKey(obj) || ""
        ).trim();
      }
      const normalizedPath = resolveMessageObjectPath(String(obj.path || obj.value || ""));
      if (normalizedPath) {
        nextTarget.path = normalizedPath;
        if (String(nextTarget.kind || "").trim() === "fs_path") nextTarget.value = normalizedPath;
      }
      MESSAGE_OBJECT_VIEWER.open = true;
      MESSAGE_OBJECT_VIEWER.loading = true;
      MESSAGE_OBJECT_VIEWER.target = nextTarget;
      MESSAGE_OBJECT_VIEWER.item = null;
      MESSAGE_OBJECT_VIEWER.error = "";
      renderMessageObjectViewer();
      try {
        const directRead = await readMessageObjectPathItem(String(nextTarget.path || nextTarget.value || ""));
        MESSAGE_OBJECT_VIEWER.target = Object.assign({}, nextTarget, {
          path: directRead.path,
          value: String(nextTarget.kind || "").trim() === "fs_path" ? directRead.path : nextTarget.value,
        });
        MESSAGE_OBJECT_VIEWER.item = directRead.item;
      } catch (err) {
        const fallback = await tryResolveMessageObjectPathFallback(nextTarget).catch(() => null);
        if (fallback && fallback.item) {
          MESSAGE_OBJECT_VIEWER.target = Object.assign({}, fallback.target || {}, {
            conversationFileKey: String(nextTarget.conversationFileKey || (fallback.target && fallback.target.conversationFileKey) || "").trim(),
          });
          MESSAGE_OBJECT_VIEWER.item = fallback.item;
          MESSAGE_OBJECT_VIEWER.error = "";
        } else {
          MESSAGE_OBJECT_VIEWER.error = "对象预览失败：" + String((err && err.message) || err || "未知错误");
        }
      } finally {
        MESSAGE_OBJECT_VIEWER.loading = false;
        renderMessageObjectViewer();
      }
    }

    function activateMessageObject(obj) {
      const target = (obj && typeof obj === "object") ? obj : null;
      if (!target) return;
      if (target.defaultAction === "open_url") {
        openNew(String(target.openUrl || target.value || ""));
        return;
      }
      if (target.defaultAction === "preview_image") {
        openImagePreview(String(target.openUrl || target.value || ""), String(target.label || ""));
        return;
      }
      openMessageObjectViewer(target);
    }

    function normalizeCliTypeLabel(raw) {
      const t = String(raw || "").trim().toLowerCase();
      if (!t) return "CODEX";
      if (t === "claude") return "CLAUDE";
      if (t === "opencode") return "OPENCODE";
      if (t === "trae") return "TRAE";
      if (t === "codex") return "CODEX";
      return t.toUpperCase();
    }

    function normalizeCliTypeClass(raw) {
      const t = String(raw || "").trim().toLowerCase();
      if (t === "claude") return "claude";
      if (t === "opencode") return "opencode";
      if (t === "gemini") return "gemini";
      if (t === "trae") return "trae";
      if (t === "codex") return "codex";
      return "other";
    }

    function conversationCliBadgeText(raw) {
      const t = String(raw || "").trim().toLowerCase();
      if (!t || t === "codex") return "Codex";
      if (t === "claude") return "ClaudeCode";
      if (t === "opencode") return "OpenCode";
      if (t === "gemini") return "Gemini";
      if (t === "trae") return "Trae";
      return String(raw || "").trim() || "Codex";
    }

    function normalizeSessionModel(raw) {
      return String(raw || "").trim();
    }

    function normalizeReasoningEffort(raw) {
      let t = String(raw || "").trim().toLowerCase();
      if (!t) return "";
      if (t === "extra_high" || t === "very_high" || t === "ultra" || t === "extra") t = "xhigh";
      if (t === "low" || t === "medium" || t === "high" || t === "xhigh") return t;
      return "";
    }

    function sessionModelLabel(raw) {
      const model = normalizeSessionModel(raw);
      return model || "默认模型";
    }

    function modelInputPlaceholderByCli(cliTypeRaw) {
      const t = String(cliTypeRaw || "").trim().toLowerCase();
      if (t === "codex") return "例如：codex-spark（留空使用默认模型）";
      if (t === "claude") return "例如：claude-sonnet（可选，留空默认）";
      if (t === "gemini") return "例如：gemini-2.0-flash（可选，留空默认）";
      if (t === "opencode") return "可选模型标识（留空使用默认模型）";
      if (t === "trae") return "例如：gpt-4.1（需配置 TRAE_CONFIG_FILE）";
      return "留空使用该 CLI 默认模型";
    }

    function stripAnsiEscape(input) {
      const s = String(input || "");
      return s.replace(/\u001b\[[0-9;]*[A-Za-z]/g, "");
    }

    function decodeEscapedSymbolText(input) {
      let out = String(input || "");
      const decodeUnicode = (_, hex) => {
        try { return String.fromCharCode(parseInt(hex, 16)); } catch (_) {}
        return _;
      };
      for (let i = 0; i < 3; i++) {
        const next = out
          .replace(/\\\\r\\\\n/g, "\n")
          .replace(/\\\\n/g, "\n")
          .replace(/\\r\\n/g, "\n")
          .replace(/\\n/g, "\n")
          .replace(/\\\\t/g, "\t")
          .replace(/\\t/g, "\t")
          .replace(/\\"/g, "\"")
          .replace(/\\'/g, "'")
          .replace(/\\\//g, "/")
          .replace(/\\\\([()[\]{}])/g, "$1")
          .replace(/\\([()[\]{}])/g, "$1")
          .replace(/\\u([0-9a-fA-F]{4})/g, decodeUnicode);
        if (next === out) break;
        out = next;
      }
      return out;
    }

    function normalizeDebugLogText(input) {
      let s = stripAnsiEscape(String(input || ""));
      s = s.replace(/\r\n?/g, "\n");
      const escapedHintCount =
        (s.match(/\\n/g) || []).length +
        (s.match(/\\"/g) || []).length +
        (s.match(/\\\(/g) || []).length;
      const realNewlineCount = (s.match(/\n/g) || []).length;
      if (escapedHintCount >= 2 || escapedHintCount > realNewlineCount * 2) {
        s = decodeEscapedSymbolText(s);
      }
      return s;
    }

    function safeParseJsonLine(line) {
      const txt = String(line || "").trim();
      if (!txt) return null;
      let jsonText = txt;
      if (jsonText[0] !== "{") {
        const m = jsonText.match(/^\[[^\]]+\]\s*(\{.*\})$/);
        if (m && m[1]) jsonText = String(m[1]).trim();
      }
      if (!jsonText || jsonText[0] !== "{") return null;
      try {
        const obj = JSON.parse(jsonText);
        return (obj && typeof obj === "object" && !Array.isArray(obj)) ? obj : null;
      } catch (_) {
        return null;
      }
    }

    function normalizeCliDebugLines(input) {
      const text = normalizeDebugLogText(input);
      if (!text.trim()) return { lines: [], truncated: false };

      const srcLines = text.split("\n");
      const lines = [];
      const maxLines = 220;

      const toDebugText = (v) => {
        if (v == null) return "";
        if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
        try { return JSON.stringify(v); } catch (_) {}
        return String(v);
      };

      for (let i = 0; i < srcLines.length; i++) {
        if (lines.length >= maxLines) break;
        const raw = String(srcLines[i] || "");
        if (!raw.trim()) continue;
        const parsed = safeParseJsonLine(raw);
        if (!parsed) {
          lines.push(raw);
          continue;
        }
        const evt = firstNonEmptyText([
          parsed.type,
          parsed.event,
          parsed.kind,
          parsed.level,
          parsed.role,
          parsed.channel,
        ]) || "json";
        let msg = "";
        const fields = [parsed.message, parsed.msg, parsed.text, parsed.content, parsed.error, parsed.detail];
        for (const v of fields) {
          const t = toDebugText(v).trim();
          if (!t) continue;
          msg = t;
          break;
        }
        if (!msg) {
          const clone = Object.assign({}, parsed);
          ["type", "event", "kind", "level", "role", "channel"].forEach((k) => delete clone[k]);
          const body = JSON.stringify(clone);
          msg = body && body !== "{}" ? body : "{}";
        }
        lines.push("[" + evt + "] " + msg);
      }

      return {
        lines,
        truncated: srcLines.length > lines.length && lines.length >= maxLines,
      };
    }

    function makeDebugKv(label, value) {
      const item = el("div", { class: "mdebug-kv" });
      item.appendChild(el("div", { class: "mdebug-k", text: String(label || "") }));
      item.appendChild(el("div", { class: "mdebug-v", text: String(value || "-") }));
      return item;
    }

    function renderDebugPanel(full, opts = {}) {
      const f = (full && typeof full === "object") ? full : {};
      const run = (f.run && typeof f.run === "object") ? f.run : {};
      const cliLabel = normalizeCliTypeLabel(run.cliType || "codex");
      const cliTypeClass = normalizeCliTypeClass(run.cliType || "codex");
      const status = String(run.status || "");
      const started = String(run.startedAt || "");
      const finished = String(run.finishedAt || "");
      const startedZh = started ? zhDateTime(started) : "";
      const finishedZh = finished ? zhDateTime(finished) : "";
      const durationBaseEnd = finished || new Date().toISOString();
      const durationZh = started ? zhDurationBetween(started, durationBaseEnd) : "";
      const runError = String(run.error || "").trim();
      const normalized = normalizeCliDebugLines(String(f.logTail || ""));
      const runId = String(opts.runId || "").trim();

      const root = el("div", { class: "mdebug" });
      const head = el("div", { class: "mdebug-head" });
      head.appendChild(el("span", { class: "mdebug-cli cli-" + cliTypeClass, text: cliLabel }));
      head.appendChild(el("span", { class: "mdebug-title", text: "调试日志（格式化）" }));
      root.appendChild(head);

      const specFields = readConversationSpecFields(run);
      const meta = el("div", { class: "mdebug-meta" });
      meta.appendChild(makeDebugKv("状态", status || "-"));
      if (started) meta.appendChild(makeDebugKv("开始", startedZh || started));
      if (finished) meta.appendChild(makeDebugKv("结束", finishedZh || finished));
      if (durationZh) meta.appendChild(makeDebugKv("耗时", finished ? durationZh : ("已耗时 " + durationZh)));
      if (runError) meta.appendChild(makeDebugKv("错误", runError));
      if (specFields.senderName) meta.appendChild(makeDebugKv("sender_name", specFields.senderName));
      if (specFields.senderType) meta.appendChild(makeDebugKv("sender_type", specFields.senderType));
      if (specFields.senderId) meta.appendChild(makeDebugKv("sender_id", specFields.senderId));
      if (specFields.messageKind) meta.appendChild(makeDebugKv("message_kind", specFields.messageKind));
      if (specFields.interactionMode) meta.appendChild(makeDebugKv("interaction_mode", specFields.interactionMode));
      if (specFields.sourceRefText) meta.appendChild(makeDebugKv("source_ref", specFields.sourceRefText));
      if (specFields.callbackToText) meta.appendChild(makeDebugKv("callback_to", specFields.callbackToText));
      root.appendChild(meta);

      const logWrap = el("div", { class: "mdebug-log-wrap" });
      if (!normalized.lines.length) {
        logWrap.appendChild(el("div", { class: "hint", text: "暂无日志内容" }));
      } else {
        const pre = el("pre", { class: "mdebug-log" });
        if (runId) pre.setAttribute("data-run-id", runId);
        pre.textContent = normalized.lines.join("\n");
        if (runId) {
          const saved = Number((PCONV.debugLogScrollTop && PCONV.debugLogScrollTop[runId]) || 0);
          pre.addEventListener("scroll", () => {
            if (!PCONV.debugLogScrollTop) PCONV.debugLogScrollTop = Object.create(null);
            PCONV.debugLogScrollTop[runId] = pre.scrollTop;
          }, { passive: true });
          if (saved > 0) {
            requestAnimationFrame(() => {
              try { pre.scrollTop = saved; } catch (_) {}
            });
          }
        }
        logWrap.appendChild(pre);
        if (normalized.truncated) {
          logWrap.appendChild(el("div", { class: "hint", text: "日志较长，已显示前 220 行。" }));
        }
      }
      root.appendChild(logWrap);
      return root;
    }

    function firstNonEmptyText(values) {
      const arr = Array.isArray(values) ? values : [];
      for (const v of arr) {
        const s = String(v == null ? "" : v).trim();
        if (s) return s;
      }
      return "";
    }

    function normalizeSenderType(raw, fallbackRole = "") {
      const t = String(raw || "").trim().toLowerCase();
      if (["user", "human", "person", "requester", "用户", "人类"].includes(t)) return "user";
      if (["agent", "assistant", "bot", "model", "channel", "智能体", "助手", "模型", "通道"].includes(t)) return "agent";
      if (["system", "runtime", "scheduler", "ccb", "系统", "运行时", "调度器"].includes(t)) return "system";
      if (["legacy", "unknown", "default", "历史", "未知"].includes(t)) return "legacy";
      const role = String(fallbackRole || "").trim().toLowerCase();
      if (role === "user") return "user";
      if (role === "assistant") return "agent";
      return "legacy";
    }

    function compactSenderLabel(label, maxLen = 18) {
      const t = String(label || "").trim();
      if (!t) return "";
      if (t.length <= maxLen) return t;
      return t.slice(0, maxLen) + "…";
    }

    function extractSourceChannelName(text) {
      const src = String(text || "").trim();
      if (!src) return "";
      const head = src.slice(0, 180);
      let m = head.match(/^\s*\[\s*(?:来源通道|source\s*channel)\s*[:：]\s*([^\]\n]+)\]/i);
      if (m) return String(m[1] || "").trim();
      m = head.match(/^\s*(?:来源通道|source\s*channel)\s*[:：]\s*([^\n]+)/i);
      if (m) return String(m[1] || "").trim();
      return "";
    }

    function readStructuredSender(raw) {
      const obj = (raw && typeof raw === "object") ? raw : {};
      const nested = (obj.sender && typeof obj.sender === "object") ? obj.sender : {};
      const typeRaw = firstNonEmptyText([
        obj.sender_type, obj.senderType, obj.sender_role, obj.senderRole,
        nested.sender_type, nested.senderType, nested.sender_role, nested.senderRole, nested.type, nested.role,
      ]);
      const id = firstNonEmptyText([
        obj.sender_id, obj.senderId,
        nested.sender_id, nested.senderId, nested.id,
      ]);
      const name = firstNonEmptyText([
        obj.sender_name, obj.senderName,
        nested.sender_name, nested.senderName, nested.name,
      ]);
      return {
        typeRaw,
        type: normalizeSenderType(typeRaw, ""),
        id,
        name,
      };
    }

    function mergeRunForDisplay(preferredRun, fallbackRun) {
      const preferred = (preferredRun && typeof preferredRun === "object" && !Array.isArray(preferredRun)) ? preferredRun : {};
      const fallback = (fallbackRun && typeof fallbackRun === "object" && !Array.isArray(fallbackRun)) ? fallbackRun : {};
      const merged = Object.assign({}, fallback, preferred);
      const senderKeys = [
        "sender_type", "senderType",
        "sender_role", "senderRole",
        "sender_id", "senderId",
        "sender_name", "senderName",
      ];
      senderKeys.forEach((k) => {
        const cur = firstNonEmptyText([merged[k]]);
        if (cur) return;
        const restore = firstNonEmptyText([preferred[k], fallback[k]]);
        if (restore) merged[k] = restore;
      });
      if ((!merged.sender || typeof merged.sender !== "object")) {
        if (preferred.sender && typeof preferred.sender === "object") merged.sender = preferred.sender;
        else if (fallback.sender && typeof fallback.sender === "object") merged.sender = fallback.sender;
      }
      return merged;
    }

    function senderDefaultLabel(role, opts = {}) {
      const fallbackRole = String(role || "").trim().toLowerCase();
      const agentName = firstNonEmptyText([
        opts.agentName,
        opts.displayName,
        opts.alias,
        opts.channelName,
        opts.displayChannel,
      ]);
      const cli = String(opts.cliType || "codex").trim().toUpperCase() || "CODEX";
      if (fallbackRole === "user") return "我";
      if (fallbackRole === "assistant") return agentName || cli;
      return "未知发送者";
    }

    function isLegacyUnknownSenderLabel(label) {
      const s = String(label || "").trim();
      if (!s) return true;
      if (s.includes("历史消息") || s.includes("来源未知") || s.includes("未知发送者")) return true;
      const low = s.toLowerCase();
      if (low === "legacy" || low === "unknown") return true;
      return false;
    }

    function resolveMessageSender(raw, opts = {}) {
      const role = String(opts.role || "").trim().toLowerCase();
      const allowSourceChannel = Object.prototype.hasOwnProperty.call(opts, "allowSourceChannel")
        ? !!opts.allowSourceChannel
        : role === "user";
      const displayChannel = firstNonEmptyText([opts.channelName]);
      const agentName = firstNonEmptyText([
        opts.agentName,
        opts.displayName,
        opts.alias,
        opts.displayChannel,
      ]);
      const structured = readStructuredSender(raw);
      const structuredType = normalizeSenderType(structured.type, role);
      const hasStructured = !!(structured.typeRaw || structured.id || structured.name);
      const defaultLabel = senderDefaultLabel(role, opts);
      if (hasStructured) {
        const assistantMismatch = role === "assistant" && structuredType !== "agent";
        const userLegacyUnknown = role === "user"
          && structuredType === "legacy"
          && isLegacyUnknownSenderLabel(firstNonEmptyText([structured.name, structured.id]));
        if (!assistantMismatch && !userLegacyUnknown) {
          // 对 assistant 来说，run.sender_* 在 CCB 场景通常代表“发起方”（用户侧），
          // 不应覆盖当前会话的“响应方”身份展示。
          if (role === "assistant") {
            const structuredLabel = firstNonEmptyText([structured.name, structured.id]);
            if (structuredLabel && defaultLabel && structuredLabel !== defaultLabel) {
              return {
                type: "agent",
                label: defaultLabel,
                id: "",
                source: "assistant-channel",
                subtitle: (displayChannel && displayChannel !== defaultLabel) ? displayChannel : "",
              };
            }
          }
          const label = firstNonEmptyText([
            structured.name,
            structured.id,
            defaultLabel,
          ]);
          return {
            type: structuredType,
            label: label || "未知发送者",
            id: structured.id,
            source: "structured",
            subtitle: (
              role === "assistant"
              && displayChannel
              && displayChannel !== label
              && displayChannel !== agentName
            ) ? displayChannel : "",
          };
        }
      }

      if (allowSourceChannel) {
        const texts = Array.isArray(opts.textCandidates) ? opts.textCandidates : [];
        for (const txt of texts) {
          const sourceChannel = extractSourceChannelName(txt);
          if (!sourceChannel) continue;
          return { type: "agent", label: sourceChannel, id: "", source: "source-channel" };
        }
      }

      const fallbackType = normalizeSenderType("", role);
      const fallbackLabel = (role === "user") ? "用户" : defaultLabel;
      return {
        type: fallbackType,
        label: fallbackLabel,
        id: "",
        source: "legacy",
        subtitle: (
          role === "assistant"
          && displayChannel
          && displayChannel !== fallbackLabel
        ) ? displayChannel : "",
      };
    }

    function buildUiUserSenderFields(source = null) {
      const ctx = resolveSessionContextFields(source);
      return {
        sender_type: "user",
        sender_id: "web-user",
        sender_name: "我",
        environment: ctx.environment,
        worktree_root: ctx.worktree_root,
        workdir: ctx.workdir,
        branch: ctx.branch,
      };
    }

    function buildConversationComposerSenderHint() {
      if (typeof isTaskShareModeActive === "function" && isTaskShareModeActive()) {
        return "发送主体：外部协作者 · " + taskShareModeText(taskShareModeParams && taskShareModeParams().sender_name, "外部协作者");
      }
      const sender = readStructuredSender(buildUiUserSenderFields(currentConversationCtx() || resolveConversationSendCtx()));
      const st = normalizeSenderType(sender.type, "user");
      const kind = st === "system" ? "系统" : (st === "agent" ? "通道Agent" : "用户");
      const who = firstNonEmptyText([sender.name, sender.id]) || "用户";
      return "发送主体：" + kind + " · " + who;
    }

    function senderChipTone(sender) {
      const type = String((sender && sender.type) || "").toLowerCase();
      if (type === "agent") return "good";
      if (type === "user") return "muted";
      return "muted";
    }

    function buildSenderChip(sender) {
      const label = firstNonEmptyText([sender && sender.label]) || "未知发送者";
      const node = chip(label, senderChipTone(sender));
      const source = String((sender && sender.source) || "");
      if (source === "source-channel") node.title = "来源通道标识";
      const subtitle = String((sender && sender.subtitle) || "").trim();
      if (!subtitle) return node;
      const wrap = el("span", { class: "sender-chip-wrap" });
      wrap.appendChild(node);
      wrap.appendChild(el("span", {
        class: "msgmeta-sub",
        text: subtitle,
        title: "通道：" + subtitle,
      }));
      return wrap;
    }

    function readCommunicationViewMeta(run) {
      const r = (run && typeof run === "object") ? run : {};
      const cv = r.communication_view || r.communicationView;
      return (cv && typeof cv === "object" && !Array.isArray(cv)) ? cv : {};
    }

    function normalizeConversationMessageKind(raw) {
      const k = String(raw || "").trim().toLowerCase();
      if (!k) return "";
      const allow = new Set([
        "system_callback",
        "system_callback_summary",
        "restart_recovery_summary",
        "user_input",
        "agent_output",
        "system_notice",
        "collab_update",
        "manual_update",
      ]);
      return allow.has(k) ? k : "";
    }

    // V1 展示优先级：communication_view.message_kind > trigger_type > sender_type > role fallback
    function resolveConversationMessageKind(run, role = "") {
      const r = (run && typeof run === "object") ? run : {};
      const roleText = String(role || "").trim().toLowerCase();
      const cv = readCommunicationViewMeta(r);
      const cvKind = normalizeConversationMessageKind(cv.message_kind || cv.messageKind);
      if (cvKind) {
        // assistant 行仅代表“对方输出”，避免误显示为“用户输入”。
        if (roleText === "assistant" && cvKind === "user_input") return "agent_output";
        return cvKind;
      }

      const triggerType = firstNonEmptyText([r.trigger_type, r.triggerType]).toLowerCase();
      if (triggerType === "callback_auto") return "system_callback";
      if (triggerType === "callback_auto_summary") return "system_callback_summary";
      if (triggerType === "restart_recovery_summary" || triggerType === "restart_recovery") return "restart_recovery_summary";

      const sender = readStructuredSender(r);
      const st = normalizeSenderType(sender.type, roleText);
      if (roleText === "assistant") {
        if (st === "system") return "system_notice";
        if (st === "agent" || st === "user" || st === "legacy") return "agent_output";
      }
      if (st === "user") return "user_input";
      if (st === "agent") return "agent_output";
      if (st === "system") return "system_notice";

      if (roleText === "user") return "user_input";
      if (roleText === "assistant") return "agent_output";
      return "manual_update";
    }

    function conversationMessageKindLabel(kind) {
      const k = normalizeConversationMessageKind(kind) || String(kind || "").trim().toLowerCase();
      return ({
        system_callback: "系统回执",
        system_callback_summary: "系统回执汇总",
        restart_recovery_summary: "服务恢复",
        user_input: "用户输入",
        agent_output: "通道输出",
        system_notice: "系统提示",
        collab_update: "协同更新",
        manual_update: "兼容消息",
      })[k] || "消息";
    }

    function conversationMessageKindTone(kind) {
      const k = normalizeConversationMessageKind(kind) || String(kind || "").trim().toLowerCase();
      if (k === "system_callback" || k === "system_callback_summary") return "warn";
      if (k === "restart_recovery_summary") return "warn";
      if (k === "user_input") return "muted";
      if (k === "agent_output") return "good";
      if (k === "system_notice") return "muted";
      if (k === "manual_update") return "muted";
      return "muted";
    }

    function buildConversationMessageKindChip(kind) {
      const label = conversationMessageKindLabel(kind);
      const tone = conversationMessageKindTone(kind);
      const node = chip(label, tone);
      node.classList.add("msg-kind-chip");
      return node;
    }

    function conversationSenderTypeLabel(raw) {
      const t = normalizeSenderType(raw, "");
      return ({
        user: "用户",
        agent: "Agent",
        system: "系统",
        legacy: "兼容",
      })[t] || "发送方";
    }

    function buildConversationSenderTypeChip(raw) {
      const t = normalizeSenderType(raw, "");
      if (!t) return null;
      const tone = t === "agent" ? "good" : (t === "system" ? "warn" : "muted");
      const node = chip(conversationSenderTypeLabel(t), tone);
      node.classList.add("msg-spec-chip");
      node.title = "sender_type: " + t;
      return node;
    }

    function buildConversationSenderIdChip(raw) {
      const senderId = String(raw || "").trim();
      if (!senderId) return null;
      const node = chip("ID " + shortId(senderId), "muted");
      node.classList.add("msg-spec-chip");
      node.title = senderId;
      return node;
    }

    function buildConversationInteractionModeChip(raw) {
      const mode = String(raw || "").trim().toLowerCase();
      if (!mode) return null;
      const labelMap = {
        task_with_receipt: "需回执",
        notify_only: "仅通知",
        task_only: "任务",
      };
      const node = chip(labelMap[mode] || ("模式 " + mode), mode === "task_with_receipt" ? "warn" : "muted");
      node.classList.add("msg-spec-chip");
      node.title = "interaction_mode: " + mode;
      return node;
    }

    function formatConversationRefValue(raw) {
      if (raw == null) return "";
      if (typeof raw === "string" || typeof raw === "number" || typeof raw === "boolean") {
        return String(raw).trim();
      }
      if (typeof raw === "object" && !Array.isArray(raw)) {
        const sessionId = firstNonEmptyText([raw.session_id, raw.sessionId]);
        const channelName = firstNonEmptyText([raw.channel_name, raw.channelName, raw.channel]);
        const runId = firstNonEmptyText([raw.run_id, raw.runId]);
        const parts = [];
        if (channelName) parts.push("channel=" + channelName);
        if (sessionId) parts.push("session=" + sessionId);
        if (runId) parts.push("run=" + runId);
        if (parts.length) return parts.join(" · ");
        try { return JSON.stringify(raw); } catch (_) {}
      }
      try { return JSON.stringify(raw); } catch (_) {}
      return String(raw || "").trim();
    }

    function readConversationSpecFields(run) {
      const r = (run && typeof run === "object" && !Array.isArray(run)) ? run : {};
      const cv = readCommunicationViewMeta(r);
      const sender = readStructuredSender(r);
      const messageKind = resolveConversationMessageKind(r);
      const interactionMode = firstNonEmptyText([
        r.interaction_mode, r.interactionMode,
        cv.interaction_mode, cv.interactionMode,
      ]).toLowerCase();
      const sourceRef = r.source_ref || r.sourceRef || cv.source_ref || cv.sourceRef || null;
      const callbackTo = r.callback_to || r.callbackTo || cv.callback_to || cv.callbackTo || null;
      return {
        senderName: firstNonEmptyText([sender.name]),
        senderType: normalizeSenderType(sender.type || sender.typeRaw, ""),
        senderId: firstNonEmptyText([sender.id]),
        messageKind,
        interactionMode,
        sourceRef,
        callbackTo,
        sourceRefText: formatConversationRefValue(sourceRef),
        callbackToText: formatConversationRefValue(callbackTo),
      };
    }

    function normalizeCallbackEventType(raw) {
      const t = String(raw || "").trim().toLowerCase();
      if (t === "done" || t === "error" || t === "interrupted") return t;
      return "";
    }

    function readCallbackTarget(raw) {
      const obj = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : {};
      const channelName = firstNonEmptyText([obj.channel_name, obj.channelName]);
      const sessionId = firstNonEmptyText([obj.session_id, obj.sessionId]);
      if (!channelName && !sessionId) return null;
      return { channelName, sessionId };
    }

    function readRouteResolution(raw) {
      const obj = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : {};
      const source = firstNonEmptyText([obj.source]).toLowerCase();
      const fallbackStage = firstNonEmptyText([obj.fallback_stage, obj.fallbackStage]).toLowerCase();
      const degradeReason = firstNonEmptyText([obj.degrade_reason, obj.degradeReason]).toLowerCase();
      const finalTarget = readCallbackTarget(obj.final_target || obj.finalTarget);
      return {
        source: source || "",
        fallbackStage: fallbackStage || "",
        degradeReason: degradeReason || "",
        finalTarget,
      };
    }

    function readCallbackSummaryIds(raw) {
      if (!Array.isArray(raw)) return [];
      const out = [];
      for (const x of raw) {
        const s = String(x || "").trim();
        if (!s) continue;
        if (out.length && out[out.length - 1] === s) continue;
        out.push(s);
        if (out.length >= 50) break;
      }
      return out;
    }

    function readPositiveInt(raw, fallback = 0) {
      const n = Number(raw);
      if (!Number.isFinite(n) || n <= 0) return Math.max(0, Number(fallback) || 0);
      return Math.floor(n);
    }

    function parseCallbackMessageKv(text) {
      const src = String(text || "").replace(/\r\n?/g, "\n");
      if (!src.trim()) return {};
      const out = Object.create(null);
      const lines = src.split("\n");
      for (const line of lines) {
        const m = line.match(/^\s*(?:[-*]\s*)?(?:\[[^\]]+\]\s*)?([^:：\n]{1,24})\s*[:：]\s*(.+?)\s*$/);
        if (!m) continue;
        const rawKey = String(m[1] || "").trim().toLowerCase();
        const val = String(m[2] || "").trim();
        if (!val) continue;
        if (!out[rawKey]) out[rawKey] = val;
      }
      return out;
    }

    function pickCallbackKvValue(kv, aliases) {
      const map = (kv && typeof kv === "object") ? kv : {};
      const keys = Array.isArray(aliases) ? aliases : [];
      for (const key of keys) {
        const k = String(key || "").trim().toLowerCase();
        if (!k) continue;
        const hit = String(map[k] || "").trim();
        if (hit) return hit;
      }
      return "";
    }

    function callbackConclusionDefault(eventType) {
      const t = normalizeCallbackEventType(eventType);
      if (t === "done") return "已完成，可进入验收/收口";
      if (t === "error") return "执行异常，需处理后再推进";
      if (t === "interrupted") return "执行中断，待恢复后继续";
      return "状态待确认";
    }

    function normalizeCallbackStage(stageRaw, eventType) {
      const s = String(stageRaw || "").trim().toLowerCase();
      if (!s) {
        const t = normalizeCallbackEventType(eventType);
        if (t === "done") return "收口";
        if (t === "error") return "联调";
        if (t === "interrupted") return "推进";
        return "推进";
      }
      if (s.includes("启动")) return "启动";
      if (s.includes("联调")) return "联调";
      if (s.includes("收口") || s.includes("验收")) return "收口";
      if (s.includes("推进")) return "推进";
      return String(stageRaw || "").trim();
    }

    function readRunCallbackEventMeta(run, sessionCtx, messageText = "") {
      const r = (run && typeof run === "object") ? run : {};
      const triggerType = firstNonEmptyText([r.trigger_type, r.triggerType]).toLowerCase();
      if (triggerType !== "callback_auto" && triggerType !== "callback_auto_summary") return null;

      const eventType = normalizeCallbackEventType(firstNonEmptyText([r.event_type, r.eventType]));
      if (!eventType) return null;

      const sourceRunId = firstNonEmptyText([r.source_run_id, r.sourceRunId]);
      const routeResolution = readRouteResolution(r.route_resolution || r.routeResolution);
      const feedbackFilePath = firstNonEmptyText([r.feedback_file_path, r.feedbackFilePath]);
      const summaryRunIds = readCallbackSummaryIds(r.callback_summary_of || r.callbackSummaryOf);
      const aggregateSourceRunIds = readCallbackSummaryIds(r.callback_aggregate_source_run_ids || r.callbackAggregateSourceRunIds);
      const callbackMergeMode = firstNonEmptyText([r.callback_merge_mode, r.callbackMergeMode]).toLowerCase();
      const callbackAnchorAction = firstNonEmptyText([r.callback_anchor_action, r.callbackAnchorAction]).toLowerCase();
      const callbackLastMergedAt = firstNonEmptyText([r.callback_last_merged_at, r.callbackLastMergedAt]);
      const aggregateCount = readPositiveInt(
        firstNonEmptyText([r.callback_aggregate_count, r.callbackAggregateCount]),
        Math.max(summaryRunIds.length, aggregateSourceRunIds.length)
      );
      const eventReason = firstNonEmptyText([r.event_reason, r.eventReason]).toLowerCase();
      const projectId = firstNonEmptyText([r.project_id, r.projectId, STATE && STATE.project]);
      const targetSessionId = firstNonEmptyText([sessionCtx && sessionCtx.sessionId]);
      const canDedupe = triggerType === "callback_auto" && !!sourceRunId && !!targetSessionId;
      const dedupeKey = canDedupe
        ? [projectId, sourceRunId, eventType, targetSessionId].join("|")
        : "";
      const kv = parseCallbackMessageKv(messageText);
      const sourceChannelFromText = firstNonEmptyText([
        pickCallbackKvValue(kv, ["来源通道", "source channel", "来源channel"]),
        extractSourceChannelName(messageText),
      ]);
      const sourceChannelFromRun = firstNonEmptyText([
        r.source_channel_name, r.sourceChannelName,
        routeResolution && routeResolution.finalTarget && routeResolution.finalTarget.channelName,
      ]);
      const needConfirm = firstNonEmptyText([
        pickCallbackKvValue(kv, ["需确认", "需总控确认", "需要确认"]),
        r.need_confirm, r.needConfirm,
      ]);
      const stageRaw = firstNonEmptyText([
        pickCallbackKvValue(kv, ["执行阶段", "阶段"]),
        r.execution_stage, r.executionStage, r.stage,
      ]);
      const comm = {
        sourceChannel: firstNonEmptyText([sourceChannelFromText, sourceChannelFromRun]),
        receiptTask: firstNonEmptyText([
          pickCallbackKvValue(kv, ["回执任务", "任务", "关联任务"]),
          r.receipt_task, r.receiptTask, r.task_name, r.taskName,
        ]),
        stage: normalizeCallbackStage(stageRaw, eventType),
        currentConclusion: firstNonEmptyText([
          pickCallbackKvValue(kv, ["当前结论", "执行结论", "结论"]),
          r.current_conclusion, r.currentConclusion,
          callbackConclusionDefault(eventType),
        ]),
        goalProgress: firstNonEmptyText([
          pickCallbackKvValue(kv, ["目标进展", "进展", "本次目标"]),
          r.goal_progress, r.goalProgress, r.progress_summary, r.progressSummary,
        ]),
        systemHandled: firstNonEmptyText([
          pickCallbackKvValue(kv, ["系统已处理", "已完成事项", "执行结果"]),
          r.system_handled, r.systemHandled,
        ]),
        needPeer: firstNonEmptyText([
          pickCallbackKvValue(kv, ["需要对方", "建议动作", "下一步"]),
          r.need_peer, r.needPeer, r.next_action, r.nextAction,
        ]),
        expectedResult: firstNonEmptyText([
          pickCallbackKvValue(kv, ["预期结果", "结果预期"]),
          r.expected_result, r.expectedResult,
        ]),
        needConfirm: needConfirm || "无",
      };

      return {
        triggerType,
        eventType,
        eventReason,
        sourceRunId,
        projectId,
        routeResolution,
        feedbackFilePath,
        feedbackMissing: !feedbackFilePath,
        summaryRunIds,
        summaryCount: summaryRunIds.length,
        aggregateSourceRunIds,
        aggregateCount,
        callbackMergeMode,
        callbackAnchorAction,
        callbackLastMergedAt,
        isSummary: triggerType === "callback_auto_summary",
        dedupeKey,
        comm,
      };
    }

    function callbackEventLabel(eventType) {
      const t = normalizeCallbackEventType(eventType);
      if (t === "done") return "完成";
      if (t === "error") return "异常";
      if (t === "interrupted") return "中断";
      return t || "事件";
    }

    function callbackEventTone(eventType) {
      const t = normalizeCallbackEventType(eventType);
      if (t === "done") return "good";
      if (t === "error") return "bad";
      if (t === "interrupted") return "warn";
      return "muted";
    }

    function callbackEventRouteSummary(meta) {
      const rr = (meta && meta.routeResolution) || {};
      const source = firstNonEmptyText([rr.source]) || "-";
      const targetName = firstNonEmptyText([rr.finalTarget && rr.finalTarget.channelName, rr.finalTarget && rr.finalTarget.sessionId]) || "-";
      return source + " -> " + targetName;
    }

    function callbackEventReasonLabel(reason) {
      const r = String(reason || "").trim().toLowerCase();
      if (!r) return "";
      const map = {
        user_interrupt: "用户打断",
        server_restart: "服务重启",
        process_exit: "进程退出",
        timeout_interrupt: "超时中断",
        unknown: "未知原因",
      };
      return map[r] || r;
    }

    function renderCallbackRawDetails(rawText) {
      const txt = String(rawText || "").trim();
      if (!txt) return null;
      const details = el("details", { class: "callback-raw-details" });
      details.appendChild(el("summary", { text: "展开原文" }));
      const body = el("div", { class: "callback-raw-body md" });
      setMarkdown(body, txt, txt);
      details.appendChild(body);
      return details;
    }

    function readConversationReplyContext(src, fallbackPreview) {
      const raw = (src && typeof src === "object") ? src : {};
      const explicitPreview = firstNonEmptyText([
        raw.reply_to_preview,
        raw.replyToPreview,
      ]);
      const explicitSender = firstNonEmptyText([
        raw.reply_to_sender_name,
        raw.replyToSenderName,
      ]);
      const createdAt = firstNonEmptyText([
        raw.reply_to_created_at,
        raw.replyToCreatedAt,
      ]);
      const runId = firstNonEmptyText([
        raw.reply_to_run_id,
        raw.replyToRunId,
      ]);
      const hasReplyMeta = !!(explicitPreview || explicitSender || createdAt || runId);
      if (!hasReplyMeta) {
        const legacy = parseInjectedConversationReplyText(fallbackPreview);
        return legacy ? normalizeConvReplyContext(legacy.replyContext) : null;
      }
      // 有结构化 reply_to_* 时，不再把整条正文错误兜底为引用预览。
      // 缺 preview 时按契约回退为“(空内容)”。
      const preview = explicitPreview || "(空内容)";
      const senderLabel = explicitSender || "我";
      const timeLabel = createdAt ? (compactDateTime(createdAt) || imTime(createdAt) || "") : "";
      return normalizeConvReplyContext({
        runId,
        bubbleKey: runId || "",
        senderLabel,
        timeLabel,
        preview: preview || "(空内容)",
        createdAt,
      });
    }

    function parseInjectedConversationReplyText(text) {
      const src = String(text || "").replace(/\r\n?/g, "\n");
      if (!src.startsWith("回复「")) return null;
      const titleMatch = src.match(/^回复「([^」]+)」：\n/);
      if (!titleMatch) return null;
      const title = String(titleMatch[1] || "").trim();
      const body = src.slice(titleMatch[0].length);
      const lines = body.split("\n");
      const quoteLines = [];
      let idx = 0;
      while (idx < lines.length) {
        const line = String(lines[idx] || "");
        if (!line.trim()) break;
        if (!line.startsWith("> ")) return null;
        quoteLines.push(line.slice(2));
        idx += 1;
      }
      if (!quoteLines.length) return null;
      while (idx < lines.length && !String(lines[idx] || "").trim()) idx += 1;
      const rest = lines.slice(idx).join("\n").trim();
      let timeLabel = "";
      let senderLabel = title || "我";
      const titleParts = title.match(/^(\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\s+(.+)$/);
      if (titleParts) {
        timeLabel = String(titleParts[1] || "").trim();
        senderLabel = String(titleParts[2] || "").trim() || senderLabel;
      }
      return {
        replyContext: {
          runId: "",
          bubbleKey: "",
          senderLabel,
          timeLabel,
          preview: quoteLines.join("\n").trim(),
          createdAt: "",
        },
        restText: rest,
      };
    }

    function stripInjectedConversationReplyText(text) {
      const parsed = parseInjectedConversationReplyText(text);
      if (!parsed) return String(text || "");
      return String(parsed.restText || "").trim();
    }

    function readRunRestartRecoveryMeta(run, sessionCtx) {
      const r = (run && typeof run === "object") ? run : {};
      const triggerType = firstNonEmptyText([r.trigger_type, r.triggerType]).toLowerCase();
      if (triggerType !== "restart_recovery_summary" && triggerType !== "restart_recovery") return null;

      const sourceIdsRaw = (
        r.restartRecoverySourceRunIds || r.restart_recovery_source_run_ids || r.restart_recovery_source_runids || []
      );
      let sourceRunIds = readCallbackSummaryIds(sourceIdsRaw);
      const legacySource = firstNonEmptyText([r.restartRecoveryOf, r.restart_recovery_of]);
      if (!sourceRunIds.length && legacySource) sourceRunIds = [legacySource];

      const countRaw = Number(firstNonEmptyText([r.restartRecoveryCount, r.restart_recovery_count]));
      const recoveryCount = Number.isFinite(countRaw) && countRaw > 0 ? Math.floor(countRaw) : Math.max(sourceRunIds.length, 1);
      const projectId = firstNonEmptyText([r.project_id, r.projectId, STATE && STATE.project]);
      const sessionId = firstNonEmptyText([sessionCtx && sessionCtx.sessionId, r.session_id, r.sessionId]);
      const batchId = firstNonEmptyText([
        r.restartRecoveryBatchId,
        r.restart_recovery_batch_id,
        r.restartRecoveryRunId,
        r.restart_recovery_run_id,
        r.id,
      ]);
      const dedupeSeed = batchId || firstNonEmptyText([r.restartRecoveryQueuedAt, r.restart_recovery_queued_at, sourceRunIds[0], String(recoveryCount)]);
      const dedupeKey = [projectId, sessionId, "restart_recovery", dedupeSeed].filter(Boolean).join("|");

      return {
        triggerType,
        isSummary: triggerType === "restart_recovery_summary" || recoveryCount > 1,
        recoveryCount,
        sourceRunIds,
        batchId,
        dedupeKey,
      };
    }

    function resolveRunPreview(run, session) {
      const r = (run && typeof run === "object") ? run : {};
      const aiText = firstNonEmptyText([r.lastPreview, r.partialPreview]);
      const userText = firstNonEmptyText([r.messagePreview]);
      const role = aiText ? "assistant" : (userText ? "user" : "assistant");
      const previewText = aiText || userText || "";
      const sender = resolveMessageSender(r, {
        role,
        cliType: firstNonEmptyText([r.cliType, session && session.cli_type]),
        channelName: firstNonEmptyText([r.channelName, session && session.channel_name, session && session.primaryChannel]),
        displayChannel: firstNonEmptyText([session && session.displayChannel, session && session.alias]),
        textCandidates: [previewText, aiText, userText],
      });
      return { role, text: previewText, sender, userText, aiText };
    }

    function conversationPreviewLine(s) {
      const latestSummary = (s && typeof s.latest_run_summary === "object")
        ? s.latest_run_summary
        : ((s && typeof s.latestRunSummary === "object") ? s.latestRunSummary : null);
      const latestEffectiveSummary = getSessionLatestEffectiveRunSummary(s);
      const runtimeState = getSessionRuntimeState(s);
      const sessionDisplayState = String(getSessionStatus(s) || firstNonEmptyText([
        s && s.session_display_state,
        s && s.sessionDisplayState,
        s && s.runtime_state && s.runtime_state.display_state,
        s && s.runtimeState && s.runtimeState.display_state,
      ]) || "").trim().toLowerCase();
      const workingState = (
        sessionDisplayState === "running"
        || sessionDisplayState === "queued"
        || sessionDisplayState === "retry_waiting"
        || sessionDisplayState === "external_busy"
      );
      const activeRunId = String(runtimeState.active_run_id || "").trim();
      const queuedRunId = String(runtimeState.queued_run_id || "").trim();
      const latestSummaryStatus = normalizeDisplayState(firstNonEmptyText([
        latestSummary && latestSummary.status,
        latestSummary && latestSummary.display_state,
        latestSummary && latestSummary.displayState,
      ]), "idle");
      const staleTerminalErrorWhileWorking = workingState
        && latestSummaryStatus === "error"
        && !!(activeRunId || queuedRunId);
      let text = String(getSessionPrimaryPreviewText(s) || "").trim();
      let role = String((s && s.lastSpeaker) || "assistant").toLowerCase() === "user" ? "user" : "assistant";
      const cachedSenderType = firstNonEmptyText([
        s && s.lastSenderType,
        latestSummary && latestSummary.sender_type,
      ]);
      const looksSystemSummary = normalizeSenderType(cachedSenderType, role) === "system";
      const usesSyntheticPreviewSender = sessionUsesSyntheticPreviewSender(s, text);
      let useCachedSender = !usesSyntheticPreviewSender;
      if (usesSyntheticPreviewSender) role = "assistant";
      if (workingState && (!text || looksSystemSummary || staleTerminalErrorWhileWorking)) {
        const aiText = firstNonEmptyText([
          s && s.latestAiMsg,
          latestSummary && latestSummary.latest_ai_msg,
        ]);
        const userText = firstNonEmptyText([
          s && s.latestUserMsg,
          latestSummary && latestSummary.latest_user_msg,
        ]);
        const preferredText = aiText || userText;
        if (preferredText) {
          text = preferredText;
          role = aiText ? "assistant" : "user";
          useCachedSender = false;
        } else {
          text = sessionDisplayState === "queued"
            ? "新消息已进入队列，等待开始"
            : (sessionDisplayState === "retry_waiting"
              ? "当前会话正在等待自动重试"
              : (sessionDisplayState === "external_busy"
                ? "当前会话被外部占用"
                : "当前有消息执行中"));
          role = "assistant";
          useCachedSender = false;
        }
      }
      if (!text) return "系统: 暂无消息";
      const cachedLabel = useCachedSender
        ? firstNonEmptyText([s && s.lastSenderName, latestSummary && latestSummary.sender_name])
        : "";
      const sender = cachedLabel
        ? {
            type: normalizeSenderType(firstNonEmptyText([
              s && s.lastSenderType,
              latestSummary && latestSummary.sender_type,
            ]), role),
            label: cachedLabel,
            source: firstNonEmptyText([
              s && s.lastSenderSource,
              latestSummary && latestSummary.sender_source,
            ]) || "legacy",
          }
        : resolveMessageSender(s, {
            role,
            cliType: String((s && s.cli_type) || "codex"),
            channelName: firstNonEmptyText([s && s.channel_name, s && s.primaryChannel]),
            displayChannel: firstNonEmptyText([s && s.displayChannel, s && s.alias]),
            textCandidates: [text],
          });
      return compactSenderLabel(sender.label || "未知发送者") + ": " + text;
    }

    function looksLikeSessionId(s) {
      const text = String(s || "").trim();
      if (!text) return false;
      return (
        /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(text)
        || /^ses_[A-Za-z0-9]{8,128}$/.test(text)
      );
    }

    // Legacy compatibility management entry for session bindings (per project+channel).
    // 主链真源已切到 /api/sessions 与 /api/agent-candidates；这里只保留兼容读取与维护动作。
    const BINDINGS_KEY = "taskDashboard.sessionBindings.v2";
    let PERSISTENT_BINDINGS_LOADED = false;
    let PERSISTENT_BINDINGS_LOADED_BY_PROJECT = Object.create(null);
    let PERSISTENT_BINDINGS_LOADING_PROMISE = null;
    let PERSISTENT_BINDINGS_LOADING_BY_PROJECT = Object.create(null);
    let PERSISTENT_BINDINGS_RERENDER_BY_PROJECT = Object.create(null);
    let PERSISTENT_BINDINGS_SERVER_OK = false;
    let PERSISTENT_BINDINGS = {}; // In-memory cache: { projectId: { channelName: { sessionId, cliType, boundAt } } }

    // Load bindings from server API
    async function loadBindingsFromServer(projectId) {
      try {
        const qs = projectId ? "?projectId=" + encodeURIComponent(projectId) : "";
        const r = await fetch("/api/sessions/bindings" + qs, {
          headers: authHeaders({}),
          cache: "no-store",
        });
        if (!r.ok) return { ok: false, bindings: [] };
        const data = await r.json();
        return { ok: true, bindings: Array.isArray(data && data.bindings) ? data.bindings : [] };
      } catch (_) { return { ok: false, bindings: [] }; }
    }

    // Initialize persistent bindings from server
    async function initPersistentBindings(projectId) {
      const pid = String(projectId || "").trim();
      if (pid) {
        if (PERSISTENT_BINDINGS_LOADED_BY_PROJECT[pid]) return;
        if (PERSISTENT_BINDINGS_LOADING_BY_PROJECT[pid]) {
          await PERSISTENT_BINDINGS_LOADING_BY_PROJECT[pid];
          return;
        }
        const loader = (async () => {
          const loaded = await loadBindingsFromServer(pid);
          const nextProjectBindings = {};
          for (const b of loaded.bindings) {
            const rowPid = String(b.projectId || "");
            const ch = String(b.channelName || "");
            if (!rowPid || rowPid !== pid || !ch) continue;
            if (nextProjectBindings[ch]) continue;
            nextProjectBindings[ch] = {
              sessionId: String(b.sessionId || ""),
              cliType: String(b.cliType || "codex"),
              boundAt: String(b.boundAt || ""),
            };
          }
          PERSISTENT_BINDINGS[pid] = nextProjectBindings;
          PERSISTENT_BINDINGS_SERVER_OK = !!loaded.ok || PERSISTENT_BINDINGS_SERVER_OK;
          if (loaded.ok) PERSISTENT_BINDINGS_LOADED_BY_PROJECT[pid] = true;
        })();
        PERSISTENT_BINDINGS_LOADING_BY_PROJECT[pid] = loader;
        try {
          await loader;
        } finally {
          delete PERSISTENT_BINDINGS_LOADING_BY_PROJECT[pid];
        }
        return;
      }
      if (PERSISTENT_BINDINGS_LOADED) return;
      if (PERSISTENT_BINDINGS_LOADING_PROMISE) {
        await PERSISTENT_BINDINGS_LOADING_PROMISE;
        return;
      }
      const loader = (async () => {
        const loaded = await loadBindingsFromServer();
        PERSISTENT_BINDINGS = {};
        PERSISTENT_BINDINGS_LOADED_BY_PROJECT = Object.create(null);
        for (const b of loaded.bindings) {
          const rowPid = String(b.projectId || "");
          const ch = String(b.channelName || "");
          if (!rowPid || !ch) continue;
          if (!PERSISTENT_BINDINGS[rowPid]) PERSISTENT_BINDINGS[rowPid] = {};
          // list_bindings() returns newest-first; keep first hit to avoid stale rows overriding latest binding.
          if (PERSISTENT_BINDINGS[rowPid][ch]) continue;
          PERSISTENT_BINDINGS[rowPid][ch] = {
            sessionId: String(b.sessionId || ""),
            cliType: String(b.cliType || "codex"),
            boundAt: String(b.boundAt || ""),
          };
        }
        Object.keys(PERSISTENT_BINDINGS).forEach((loadedPid) => {
          PERSISTENT_BINDINGS_LOADED_BY_PROJECT[loadedPid] = true;
        });
        PERSISTENT_BINDINGS_SERVER_OK = !!loaded.ok;
        PERSISTENT_BINDINGS_LOADED = true;
      })();
      PERSISTENT_BINDINGS_LOADING_PROMISE = loader;
      try {
        await loader;
      } finally {
        PERSISTENT_BINDINGS_LOADING_PROMISE = null;
      }
    }

    function hasPersistentBindingsForProject(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return false;
      return !!(PERSISTENT_BINDINGS_LOADED || PERSISTENT_BINDINGS_LOADED_BY_PROJECT[pid]);
    }

    function ensureBindingsLoadedForProject(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview" || hasPersistentBindingsForProject(pid)) return;
      if (PERSISTENT_BINDINGS_RERENDER_BY_PROJECT[pid]) return;
      PERSISTENT_BINDINGS_RERENDER_BY_PROJECT[pid] = true;
      initPersistentBindings(pid)
        .then(() => {
          if (STATE.project === pid) render();
        })
        .catch(() => {})
        .finally(() => {
          delete PERSISTENT_BINDINGS_RERENDER_BY_PROJECT[pid];
        });
    }

    // Convert server format to localStorage format for backward compatibility
    function loadBindings() {
      try {
        // First try localStorage as fallback
        const raw = localStorage.getItem(BINDINGS_KEY);
        const local = raw ? JSON.parse(raw) : {};
        return (local && typeof local === "object") ? local : {};
      } catch (_) { return {}; }
    }
    function saveBindings(obj) {
      try { localStorage.setItem(BINDINGS_KEY, JSON.stringify(obj || {})); } catch (_) {}
    }

    // Get binding - check server first, then localStorage fallback
