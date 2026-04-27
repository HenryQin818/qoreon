    function channelDialogType(channelName) {
      const ch = String(channelName || "").trim();
      if (/主体-总控/.test(ch)) return { full: "主对话", short: "主" };
      return { full: "子级对话", short: "子级" };
    }

    function buildBootstrapVisibleMessages(channelName) {
      const ch = String(channelName || "").trim() || "当前通道";
      const dialog = channelDialogType(ch);
      const msg1 = "[Qoreon] " + ch + "（" + dialog.full + "）";
      const msg2 = "【连通性验收】通道：" + ch + "；对话类型：" + dialog.full + "。请仅回复：OK（" + ch + "-" + dialog.short + "）";
      return [msg1, msg2];
    }

    async function dedupChannelSessions(projectId, channelName, keepSessionId) {
      try {
        const r = await fetch("/api/sessions/dedup", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            project_id: String(projectId || ""),
            channel_name: String(channelName || ""),
            keep_session_id: String(keepSessionId || ""),
            strategy: "latest",
          }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) return { ok: false, removedCount: 0, error: String((j && (j.error || j.message)) || "请求失败") };
        const result = (j && j.result) || {};
        return {
          ok: true,
          removedCount: Number(result.removed_count || 0),
          keptSessionId: String(result.kept_session_id || ""),
          error: "",
        };
      } catch (_) {
        return { ok: false, removedCount: 0, error: "网络或服务异常" };
      }
    }

    async function verifySessionBindingVisibility(projectId, channelName, sessionId) {
      try {
        const r = await fetch("/api/dashboard/visibility-check", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            project_id: String(projectId || ""),
            channel_name: String(channelName || ""),
            session_id: String(sessionId || ""),
            expected_generated_at: String((DATA && DATA.generated_at) || ""),
            auto_rebuild: true,
          }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) {
          return { ok: false, hardRefreshRequired: false, error: String((j && (j.error || j.message)) || "请求失败") };
        }
        const action = (j && j.action) || {};
        return {
          ok: true,
          hardRefreshRequired: !!action.hard_refresh_required,
          rebuildTriggered: !!action.rebuild_triggered,
          reason: String(action.reason || ""),
          error: "",
        };
      } catch (_) {
        return { ok: false, hardRefreshRequired: false, error: "网络或服务异常" };
      }
    }

    async function tryUpdateSessionModel(sessionId, model) {
      const sid = String(sessionId || "").trim();
      const normalized = normalizeSessionModel(model);
      if (!looksLikeSessionId(sid) || !normalized) return false;
      try {
        const r = await fetch("/api/sessions/" + encodeURIComponent(sid), {
          method: "PUT",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ model: normalized }),
        });
        return !!(r && r.ok);
      } catch (_) {
        return false;
      }
    }

    function sessionCreateChannelNotFound(resp, payload) {
      const body = (payload && typeof payload === "object") ? payload : {};
      const detail = (body && typeof body.detail === "object") ? body.detail : null;
      const raw = [
        body.error,
        body.message,
        detail && detail.error,
        detail && detail.message,
      ].filter(Boolean).join(" | ").toLowerCase();
      return Number((resp && resp.status) || 0) === 404 && raw.indexOf("channel not found") >= 0;
    }

    async function postSessionCreateWithChannelRetry(payload) {
      let retried = false;
      for (let attempt = 0; attempt < 2; attempt++) {
        const resp = await fetch("/api/sessions", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        });
        const json = await resp.json().catch(() => ({}));
        if (resp.ok) return { resp, json, retried };
        if (attempt === 0 && sessionCreateChannelNotFound(resp, json)) {
          retried = true;
          await new Promise((resolve) => setTimeout(resolve, 700));
          continue;
        }
        return { resp, json, retried };
      }
      return { resp: null, json: {}, retried };
    }

    function resolveConversationSessionPresentation(raw, channelName, sessionId) {
      const alias = String((raw && raw.alias) || "").trim();
      const channel = String(channelName || "").trim();
      const sid = String(sessionId || "").trim();
      const contract = readAgentDisplayContract(raw);
      const agentDisplayName = String(resolveAgentDisplayName(raw) || "").trim();
      const agentNameState = normalizeAgentNameState(
        contract.state || (agentDisplayName ? "resolved" : ""),
        ""
      );
      const agentDisplayIssue = String(contract.issue || "").trim();
      const agentStateLabel = String(agentNameStateLabel(agentNameState, agentDisplayIssue) || "").trim();
      const explicitDisplayChannel = String(
        (raw && (
          raw.displayChannel ||
          raw.display_channel ||
          raw.display_name
        )) || ""
      ).trim();
      const explicitDisplayName = String(
        (raw && (
          raw.displayName ||
          raw.display_name ||
          raw.displayChannel ||
          raw.display_channel
        )) || ""
      ).trim();
      let displayNameSource = String(
        (raw && (
          raw.displayNameSource ||
          raw.display_name_source
        )) || ""
      ).trim();
      const displayChannel = alias || explicitDisplayChannel || channel || sid;
      const displayName = agentDisplayName || agentStateLabel || "";
      if (agentDisplayName && !displayNameSource) {
        displayNameSource = String(contract.source || "").trim() || "agent_display_name";
      }
      if (!agentDisplayName) {
        displayNameSource = "";
      }
      return {
        alias,
        displayChannel,
        displayName,
        displayNameSource,
        agentDisplayName,
        agentNameState,
        agentDisplayIssue,
      };
    }

    function normalizeConversationListMetricsClient(raw) {
      const src = (raw && typeof raw === "object") ? raw : null;
      if (!src) return null;
      return {
        task_counts: (src.task_counts && typeof src.task_counts === "object") ? { ...src.task_counts } : {},
        current_task_summary: (src.current_task_summary && typeof src.current_task_summary === "object")
          ? { ...src.current_task_summary }
          : null,
        memo_summary: (src.memo_summary && typeof src.memo_summary === "object")
          ? { ...src.memo_summary }
          : ((src.memoSummary && typeof src.memoSummary === "object") ? { ...src.memoSummary } : null),
        status_badges: Array.isArray(src.status_badges) ? src.status_badges.map((item) => ({ ...(item || {}) })) : [],
        detail_hydration: (src.detail_hydration && typeof src.detail_hydration === "object")
          ? { ...src.detail_hydration }
          : {},
      };
    }

    function hasConversationListMetricsClientData(raw) {
      const metrics = normalizeConversationListMetricsClient(raw);
      return !!(metrics && (
        Object.keys(metrics.task_counts || {}).length
        || (metrics.current_task_summary && Object.keys(metrics.current_task_summary).length)
        || (metrics.memo_summary && Object.keys(metrics.memo_summary).length)
        || (Array.isArray(metrics.status_badges) && metrics.status_badges.length)
      ));
    }

    function mergeConversationListMetricsClient(prevRaw, nextRaw) {
      const prev = normalizeConversationListMetricsClient(prevRaw);
      const next = normalizeConversationListMetricsClient(nextRaw);
      if (!prev && !next) return null;
      if (!prev) return next;
      if (!next) return prev;
      return {
        task_counts: { ...(prev.task_counts || {}), ...(next.task_counts || {}) },
        current_task_summary: next.current_task_summary || prev.current_task_summary || null,
        memo_summary: next.memo_summary || prev.memo_summary || null,
        status_badges: (Array.isArray(next.status_badges) && next.status_badges.length)
          ? next.status_badges
          : (prev.status_badges || []),
        detail_hydration: { ...(prev.detail_hydration || {}), ...(next.detail_hydration || {}) },
      };
    }

    function conversationSessionStateSources(session) {
      const s = (session && typeof session === "object") ? session : {};
      const raw = (s._state_sources && typeof s._state_sources === "object") ? s._state_sources : {};
      return {
        runtime_state: !!raw.runtime_state,
        session_display_state: !!raw.session_display_state,
        latest_run_summary: !!raw.latest_run_summary,
        latest_effective_run_summary: !!raw.latest_effective_run_summary,
      };
    }

    function conversationSessionHasRuntimeStateSource(session) {
      const sources = conversationSessionStateSources(session);
      if (sources.runtime_state) return true;
      const runtimeState = getSessionRuntimeState(session);
      return !!(
        runtimeState.active_run_id
        || runtimeState.queued_run_id
        || String(runtimeState.updated_at || "").trim()
        || (runtimeState.display_state && runtimeState.display_state !== "idle")
      );
    }

    function conversationSessionHasDisplayStateSource(session) {
      const sources = conversationSessionStateSources(session);
      if (sources.session_display_state) return true;
      const s = (session && typeof session === "object") ? session : {};
      return !!String(firstNonEmptyText([s.session_display_state, s.sessionDisplayState]) || "").trim();
    }

    function isConversationActiveDisplayState(raw) {
      const state = normalizeDisplayState(raw, "idle");
      return state === "running" || state === "queued" || state === "retry_waiting" || state === "external_busy";
    }

    function conversationSessionLatestRunSummaryForActivePreserve(session) {
      const s = (session && typeof session === "object") ? session : {};
      return s.latest_run_summary || s.latestRunSummary || null;
    }

    function conversationSessionHasTerminalSummaryForPreviousActive(session, previousSession) {
      const summary = conversationSessionLatestRunSummaryForActivePreserve(session) || {};
      const runId = String(firstNonEmptyText([summary.run_id, summary.runId]) || "").trim();
      const status = normalizeDisplayState(firstNonEmptyText([summary.status, summary.display_state, summary.displayState]) || "", "");
      const previousRuntime = getSessionRuntimeState(previousSession);
      const previousRunIds = new Set([
        String(previousRuntime.active_run_id || "").trim(),
        String(previousRuntime.queued_run_id || "").trim(),
      ].filter(Boolean));
      return !!(runId && previousRunIds.has(runId) && (status === "done" || status === "error" || status === "interrupted"));
    }

    function conversationShouldPreserveActiveSessionState(nextSession, previousSession) {
      const previousDisplayState = normalizeDisplayState(
        firstNonEmptyText([
          previousSession && previousSession.session_display_state,
          previousSession && previousSession.sessionDisplayState,
          previousSession && previousSession.runtime_state && previousSession.runtime_state.display_state,
          previousSession && previousSession.runtimeState && previousSession.runtimeState.display_state,
        ]) || "idle",
        "idle"
      );
      const nextDisplayState = normalizeDisplayState(
        firstNonEmptyText([
          nextSession && nextSession.session_display_state,
          nextSession && nextSession.sessionDisplayState,
          nextSession && nextSession.runtime_state && nextSession.runtime_state.display_state,
          nextSession && nextSession.runtimeState && nextSession.runtimeState.display_state,
        ]) || "idle",
        "idle"
      );
      if (!isConversationActiveDisplayState(previousDisplayState)) return false;
      if (isConversationActiveDisplayState(nextDisplayState)) return false;
      if (conversationSessionHasTerminalSummaryForPreviousActive(nextSession, previousSession)) return false;
      if (!conversationSessionHasRuntimeStateSource(nextSession) && !conversationSessionHasDisplayStateSource(nextSession)) {
        return true;
      }
      const runtimeState = getSessionRuntimeState(nextSession);
      return (
        normalizeDisplayState(runtimeState.display_state, "idle") === "idle"
        && normalizeDisplayState(runtimeState.internal_state, "idle") === "idle"
        && !runtimeState.external_busy
        && !String(runtimeState.active_run_id || "").trim()
        && !String(runtimeState.queued_run_id || "").trim()
        && Math.max(0, Number(runtimeState.queue_depth || 0) || 0) <= 0
      );
    }

    function normalizeConversationTaskOwner(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const state = String(src.state || "missing").trim().toLowerCase();
      return {
        agent_name: String(src.agent_name || src.agentName || "").trim(),
        alias: String(src.alias || "").trim(),
        session_id: firstNonEmptyText([src.session_id, src.sessionId]) || null,
        state: ["confirmed", "pending", "missing"].includes(state) ? state : "missing",
      };
    }

    function normalizeConversationTaskRoleMember(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const name = String(firstNonEmptyText([src.name, src.slot_name, src.slotName]) || "").trim();
      const agentName = String(firstNonEmptyText([src.agent_name, src.agentName]) || "").trim();
      const agentAlias = String(firstNonEmptyText([src.agent_alias, src.agentAlias, src.alias]) || "").trim();
      const displayName = String(firstNonEmptyText([
        src.display_name,
        src.displayName,
        agentAlias,
        agentName,
        name,
      ]) || "").trim();
      const channelName = String(firstNonEmptyText([src.channel_name, src.channelName]) || "").trim();
      const sessionId = firstNonEmptyText([src.session_id, src.sessionId]) || null;
      const responsibility = String(src.responsibility || src.description || "").trim();
      const source = String(firstNonEmptyText([src.source, src.member_source, src.memberSource]) || "").trim();
      if (!displayName && !channelName && !sessionId && !responsibility) return null;
      return {
        name,
        display_name: displayName || name || agentAlias || agentName,
        channel_name: channelName,
        agent_name: agentName,
        agent_alias: agentAlias,
        session_id: sessionId,
        responsibility,
        source,
      };
    }

    function normalizeConversationTaskRoleMemberList(raw) {
      const list = Array.isArray(raw) ? raw : ((raw && typeof raw === "object") ? [raw] : []);
      return list.map(normalizeConversationTaskRoleMember).filter(Boolean);
    }

    function normalizeConversationTaskCustomRole(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const name = String(firstNonEmptyText([
        src.name,
        src.role_name,
        src.roleName,
        src.slot_name,
        src.slotName,
        src.label,
      ]) || "").trim();
      const members = normalizeConversationTaskRoleMemberList(
        src.members || src.member_list || src.memberList || src.items || src.entries || src.agents || null
      );
      const responsibility = String(src.responsibility || src.description || "").trim();
      const source = String(src.source || "").trim();
      if (!name && !members.length && !responsibility) return null;
      return {
        name: name || "自定义责任位",
        members,
        responsibility,
        source,
      };
    }

    function normalizeConversationTaskHarnessRoles(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const managementRaw = src.management_slot || src.managementSlot
        || (src.management && (src.management.members || src.management.items))
        || null;
      const customRolesRaw = src.custom_roles || src.customRoles || null;
      const out = {
        main_owner: normalizeConversationTaskRoleMember(src.main_owner || src.mainOwner || null),
        collaborators: normalizeConversationTaskRoleMemberList(src.collaborators || null),
        validators: normalizeConversationTaskRoleMemberList(src.validators || null),
        challengers: normalizeConversationTaskRoleMemberList(src.challengers || null),
        backup_owners: normalizeConversationTaskRoleMemberList(src.backup_owners || src.backupOwners || null),
        management_slot: normalizeConversationTaskRoleMemberList(managementRaw),
        custom_roles: (Array.isArray(customRolesRaw) ? customRolesRaw : [])
          .map(normalizeConversationTaskCustomRole)
          .filter(Boolean),
      };
      if (!out.main_owner
        && !out.collaborators.length
        && !out.validators.length
        && !out.challengers.length
        && !out.backup_owners.length
        && !out.management_slot.length
        && !out.custom_roles.length) {
        return null;
      }
      return out;
    }

    function normalizeConversationTaskRef(raw, fallbackRelation = "") {
      const src = (raw && typeof raw === "object") ? raw : {};
      const taskId = String(firstNonEmptyText([src.task_id, src.taskId]) || "").trim();
      const parentTaskId = String(firstNonEmptyText([src.parent_task_id, src.parentTaskId]) || "").trim();
      const taskPath = String(firstNonEmptyText([src.task_path, src.taskPath]) || "").trim();
      const taskTitle = String(firstNonEmptyText([src.task_title, src.taskTitle]) || "").trim();
      if (!taskId && !taskPath && !taskTitle) return null;
      const harnessRoles = normalizeConversationTaskHarnessRoles(src);
      return {
        task_id: taskId,
        parent_task_id: parentTaskId,
        task_path: taskPath,
        task_title: taskTitle || taskPath || taskId,
        task_primary_status: String(firstNonEmptyText([src.task_primary_status, src.taskPrimaryStatus]) || "").trim(),
        relation: String(firstNonEmptyText([src.relation, fallbackRelation]) || "tracking").trim().toLowerCase() || "tracking",
        source: String(src.source || "system_merge").trim() || "system_merge",
        first_seen_at: String(firstNonEmptyText([src.first_seen_at, src.firstSeenAt]) || "").trim(),
        last_seen_at: String(firstNonEmptyText([src.last_seen_at, src.lastSeenAt]) || "").trim(),
        latest_action_at: String(firstNonEmptyText([src.latest_action_at, src.latestActionAt]) || "").trim(),
        latest_action_kind: String(firstNonEmptyText([src.latest_action_kind, src.latestActionKind]) || "").trim().toLowerCase(),
        latest_action_text: String(firstNonEmptyText([src.latest_action_text, src.latestActionText]) || "").trim(),
        task_summary_text: String(firstNonEmptyText([src.task_summary_text, src.taskSummaryText]) || "").trim(),
        is_current: boolLike(firstNonEmptyText([src.is_current, src.isCurrent])),
        next_owner: normalizeConversationTaskOwner(src.next_owner || src.nextOwner || null),
        main_owner: harnessRoles ? harnessRoles.main_owner : null,
        collaborators: harnessRoles ? harnessRoles.collaborators : [],
        validators: harnessRoles ? harnessRoles.validators : [],
        challengers: harnessRoles ? harnessRoles.challengers : [],
        backup_owners: harnessRoles ? harnessRoles.backup_owners : [],
        management_slot: harnessRoles ? harnessRoles.management_slot : [],
        custom_roles: harnessRoles ? harnessRoles.custom_roles : [],
      };
    }

    function normalizeConversationTaskAction(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const taskId = String(firstNonEmptyText([src.task_id, src.taskId]) || "").trim();
      const parentTaskId = String(firstNonEmptyText([src.parent_task_id, src.parentTaskId]) || "").trim();
      const taskPath = String(firstNonEmptyText([src.task_path, src.taskPath]) || "").trim();
      const taskTitle = String(firstNonEmptyText([src.task_title, src.taskTitle]) || "").trim();
      if (!taskId && !taskPath && !taskTitle) return null;
      return {
        task_id: taskId,
        parent_task_id: parentTaskId,
        task_path: taskPath,
        task_title: taskTitle || taskPath || taskId,
        action_kind: String(firstNonEmptyText([src.action_kind, src.actionKind]) || "update").trim().toLowerCase() || "update",
        action_text: String(firstNonEmptyText([src.action_text, src.actionText]) || "").trim(),
        status: String(src.status || "").trim().toLowerCase(),
        source_run_id: String(firstNonEmptyText([src.source_run_id, src.sourceRunId]) || "").trim(),
        callback_run_id: String(firstNonEmptyText([src.callback_run_id, src.callbackRunId]) || "").trim(),
        source_channel: String(firstNonEmptyText([src.source_channel, src.sourceChannel]) || "").trim(),
        source_agent_name: String(firstNonEmptyText([src.source_agent_name, src.sourceAgentName]) || "").trim(),
        at: String(src.at || "").trim(),
      };
    }

    function normalizeTaskTrackingClient(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const currentTask = normalizeConversationTaskRef(src.current_task_ref || src.currentTaskRef || null, "current");
      const conversationTaskRefs = (Array.isArray(src.conversation_task_refs) ? src.conversation_task_refs : [])
        .map((row) => normalizeConversationTaskRef(row, "tracking"))
        .filter(Boolean);
      const recentTaskActions = (Array.isArray(src.recent_task_actions) ? src.recent_task_actions : [])
        .map(normalizeConversationTaskAction)
        .filter(Boolean);
      const version = String(src.version || "").trim();
      const updatedAt = String(firstNonEmptyText([src.updated_at, src.updatedAt]) || "").trim();
      if (!version && !updatedAt && !currentTask && !conversationTaskRefs.length && !recentTaskActions.length) {
        return null;
      }
      return {
        version: version || "v1.1",
        current_task_ref: currentTask,
        conversation_task_refs: conversationTaskRefs,
        recent_task_actions: recentTaskActions,
        updated_at: updatedAt,
      };
    }

    function hasConversationTaskTrackingData(raw) {
      const normalized = normalizeTaskTrackingClient(raw);
      return !!(normalized && (
        normalized.version
        || normalized.updated_at
        || normalized.current_task_ref
        || normalized.conversation_task_refs.length
        || normalized.recent_task_actions.length
      ));
    }

    function ensureConversationSessionDirectoryStateMaps() {
      if (!PCONV.sessionDirectoryByProject || typeof PCONV.sessionDirectoryByProject !== "object") {
        PCONV.sessionDirectoryByProject = Object.create(null);
      }
      if (!PCONV.sessionDirectoryMetaByProject || typeof PCONV.sessionDirectoryMetaByProject !== "object") {
        PCONV.sessionDirectoryMetaByProject = Object.create(null);
      }
      if (!PCONV.sessionDirectoryPromiseByProject || typeof PCONV.sessionDirectoryPromiseByProject !== "object") {
        PCONV.sessionDirectoryPromiseByProject = Object.create(null);
      }
      if (!PCONV.sessionFetchPromiseByKey || typeof PCONV.sessionFetchPromiseByKey !== "object") {
        PCONV.sessionFetchPromiseByKey = Object.create(null);
      }
      if (!PCONV.sessionFetchCacheByKey || typeof PCONV.sessionFetchCacheByKey !== "object") {
        PCONV.sessionFetchCacheByKey = Object.create(null);
      }
      if (!PCONV.pollingMetaByProject || typeof PCONV.pollingMetaByProject !== "object") {
        PCONV.pollingMetaByProject = Object.create(null);
      }
    }

    function normalizeConversationPollingNumber(raw, fallback = 0) {
      const num = Number(raw);
      if (!Number.isFinite(num)) return Math.max(0, Number(fallback) || 0);
      return Math.max(0, Math.round(num));
    }

    function normalizeConversationSessionsPollingHints(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return {
        enabled: Object.prototype.hasOwnProperty.call(src, "enabled") ? !!src.enabled : true,
        cache_ttl_ms: normalizeConversationPollingNumber(src.cache_ttl_ms ?? src.cacheTtlMs, 2500),
        inflight_wait_ms: normalizeConversationPollingNumber(src.inflight_wait_ms ?? src.inflightWaitMs, 7000),
        poll_interval_ms: normalizeConversationPollingNumber(src.poll_interval_ms ?? src.pollIntervalMs, 45000),
        hidden_poll_interval_ms: normalizeConversationPollingNumber(src.hidden_poll_interval_ms ?? src.hiddenPollIntervalMs, 90000),
        backoff_step_ms: normalizeConversationPollingNumber(src.backoff_step_ms ?? src.backoffStepMs, 2000),
        backoff_max_ms: normalizeConversationPollingNumber(src.backoff_max_ms ?? src.backoffMaxMs, 15000),
        pause_when_hidden: !!(src.pause_when_hidden ?? src.pauseWhenHidden),
        cross_tab_dedupe_enabled: !!(src.cross_tab_dedupe_enabled ?? src.crossTabDedupeEnabled),
      };
    }

    function updateConversationProjectPollingMeta(projectId, payload = {}) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      ensureConversationSessionDirectoryStateMaps();
      const src = (payload && typeof payload === "object") ? payload : {};
      const perfGovernance = (src.perf_governance && typeof src.perf_governance === "object")
        ? src.perf_governance
        : ((src.perfGovernance && typeof src.perfGovernance === "object") ? src.perfGovernance : {});
      const pollingHints = (src.polling_hints && typeof src.polling_hints === "object")
        ? src.polling_hints
        : ((src.pollingHints && typeof src.pollingHints === "object") ? src.pollingHints : {});
      const sessionsRaw = (pollingHints.sessions && typeof pollingHints.sessions === "object")
        ? pollingHints.sessions
        : ((pollingHints.session_directory && typeof pollingHints.session_directory === "object")
          ? pollingHints.session_directory
          : null);
      const current = (PCONV.pollingMetaByProject && PCONV.pollingMetaByProject[pid]) || {};
      const nextSessions = sessionsRaw ? normalizeConversationSessionsPollingHints(sessionsRaw) : (current.sessions || null);
      if (nextSessions && Object.prototype.hasOwnProperty.call(perfGovernance, "enabled") && !perfGovernance.enabled) {
        nextSessions.enabled = false;
      }
      const next = {
        ...current,
        project_id: pid,
        updated_at: new Date().toISOString(),
        perf_governance: {
          ...(current.perf_governance || {}),
          ...(perfGovernance || {}),
        },
        sessions: nextSessions,
      };
      PCONV.pollingMetaByProject[pid] = next;
      return next;
    }

    function conversationProjectPollingHints(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      ensureConversationSessionDirectoryStateMaps();
      const meta = PCONV.pollingMetaByProject && PCONV.pollingMetaByProject[pid];
      return meta && meta.sessions ? meta.sessions : null;
    }

    function shouldForceConversationSessionDirectoryLiveFetch(projectId, channelName = "", opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return false;
      if (opts && opts.force) return true;
      const channel = String(channelName || "").trim();
      if (channel) return false;
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      if (source === "poll") return true;
      return false;
    }

    function conversationProjectPollingCadenceMs(projectId, channelName = "", opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return 0;
      const policy = typeof conversationProjectPollingHints === "function"
        ? conversationProjectPollingHints(pid)
        : null;
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      if (policy && policy.enabled) {
        if (source === "poll" || !String(channelName || "").trim()) {
          return normalizeConversationPollingNumber(policy.poll_interval_ms, 3000);
        }
      }
      return normalizeConversationPollingNumber((opts && opts.freshnessMs) || 0, 0);
    }

    function resolveConversationSessionsFreshnessMs(projectId, channelName = "", opts = {}) {
      const freshnessMs = normalizeConversationPollingNumber((opts && opts.freshnessMs) || 0, 0);
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      if (source === "poll" && !String(channelName || "").trim()) {
        return Math.max(freshnessMs, 18000);
      }
      const cadenceMs = conversationProjectPollingCadenceMs(projectId, channelName, opts);
      return Math.max(freshnessMs, cadenceMs);
    }

    function shouldDeferConversationSessionDirectoryLiveLoad(opts = {}) {
      const src = (opts && typeof opts === "object") ? opts : {};
      const canSeedSelectedSession = !!src.canSeedSelectedSession;
      const hasSelectedTimelineCache = !!src.hasSelectedTimelineCache;
      const hasServerDirectorySessions = !!src.hasServerDirectorySessions;
      return !!(canSeedSelectedSession && !hasSelectedTimelineCache && !hasServerDirectorySessions);
    }

    function resolveConversationSessionDirectoryLiveMeta(opts = {}) {
      const src = (opts && typeof opts === "object") ? opts : {};
      const existingMeta = (src.existingMeta && typeof src.existingMeta === "object") ? src.existingMeta : {};
      if (shouldDeferConversationSessionDirectoryLiveLoad(src)) {
        return {
          ...existingMeta,
          liveLoaded: false,
          source: "explicit-sid-deferred",
        };
      }
      if (src.hasServerDirectorySessions) {
        return {
          ...existingMeta,
          liveLoaded: true,
          source: "api",
        };
      }
      return {
        ...existingMeta,
        liveLoaded: !!existingMeta.liveLoaded,
        source: String(existingMeta.source || "").trim() || "config",
      };
    }

    function ensureConversationSessionDetailStateMaps() {
      if (!PCONV.sessionDetailPromiseById || typeof PCONV.sessionDetailPromiseById !== "object") {
        PCONV.sessionDetailPromiseById = Object.create(null);
      }
      if (!PCONV.sessionDetailLoadedAtById || typeof PCONV.sessionDetailLoadedAtById !== "object") {
        PCONV.sessionDetailLoadedAtById = Object.create(null);
      }
      if (!PCONV.sessionDetailErrorById || typeof PCONV.sessionDetailErrorById !== "object") {
        PCONV.sessionDetailErrorById = Object.create(null);
      }
    }

    function isConversationSessionDetailLoading(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return false;
      ensureConversationSessionDetailStateMaps();
      return !!PCONV.sessionDetailPromiseById[sid];
    }

    function getConversationSessionDetailError(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return "";
      ensureConversationSessionDetailStateMaps();
      return String(PCONV.sessionDetailErrorById[sid] || "").trim();
    }

    function mergeConversationSessionDetailIntoStore(detail, sessionId = "") {
      const base = (detail && typeof detail === "object") ? detail : {};
      const sid = String(firstNonEmptyText([sessionId, base.sessionId, base.id]) || "").trim();
      if (!sid) return null;
      const prev = typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const merged = normalizeConversationSession({
        ...(prev || {}),
        id: sid,
        sessionId: sid,
        alias: firstNonEmptyText([base.alias, prev && prev.alias]),
        channel_name: firstNonEmptyText([base.channel_name, prev && prev.channel_name, prev && prev.primaryChannel]),
        channels: Array.isArray(prev && prev.channels) ? prev.channels.slice() : [],
        primaryChannel: firstNonEmptyText([base.channel_name, prev && prev.primaryChannel]),
        display_name: firstNonEmptyText([base.display_name, base.displayName, prev && prev.displayName]),
        displayNameSource: firstNonEmptyText([base.display_name_source, base.displayNameSource, prev && prev.displayNameSource]),
        codexTitle: firstNonEmptyText([base.codex_title, base.codexTitle, prev && prev.codexTitle]),
        environment: firstNonEmptyText([base.environment, prev && prev.environment], "stable"),
        worktree_root: firstNonEmptyText([base.worktree_root, prev && prev.worktree_root]),
        workdir: firstNonEmptyText([base.workdir, prev && prev.workdir]),
        branch: firstNonEmptyText([base.branch, prev && prev.branch]),
        cli_type: firstNonEmptyText([base.cli_type, prev && prev.cli_type], "codex"),
        model: normalizeSessionModel(firstNonEmptyText([base.model, prev && prev.model])),
        reasoning_effort: normalizeReasoningEffort(firstNonEmptyText([base.reasoning_effort, prev && prev.reasoning_effort])),
        status: firstNonEmptyText([base.status, prev && prev.status], "active"),
        created_at: firstNonEmptyText([base.created_at, prev && prev.created_at]),
        last_used_at: firstNonEmptyText([base.last_used_at, prev && prev.last_used_at]),
        is_primary: Object.prototype.hasOwnProperty.call(base, "is_primary")
          ? !!base.is_primary
          : !!(prev && prev.is_primary),
        source: firstNonEmptyText([base.source, prev && prev.source]),
        runtime_state: base.runtime_state || (prev && prev.runtime_state) || null,
        heartbeat_summary: base.heartbeat_summary || (prev && prev.heartbeat_summary) || null,
        project_execution_context: base.project_execution_context || (prev && prev.project_execution_context) || null,
        task_tracking: hasConversationTaskTrackingData(base.task_tracking)
          ? base.task_tracking
          : (prev && prev.task_tracking),
      });
      if (!merged) return null;
      let replaced = false;
      for (let i = 0; i < PCONV.sessions.length; i += 1) {
        if (String(getSessionId(PCONV.sessions[i]) || "").trim() !== sid) continue;
        PCONV.sessions[i] = merged;
        replaced = true;
        break;
      }
      if (!replaced) PCONV.sessions.push(merged);
      ensureConversationSessionDetailStateMaps();
      PCONV.sessionDetailLoadedAtById[sid] = Date.now();
      delete PCONV.sessionDetailErrorById[sid];
      return merged;
    }

    async function ensureConversationSessionDetailLoaded(sessionId, opts = {}) {
      const sid = String(sessionId || "").trim();
      if (!looksLikeSessionId(sid)) return null;
      ensureConversationSessionDetailStateMaps();
      const force = !!opts.force;
      const maxAgeMsRaw = Number(opts.maxAgeMs || 0);
      const maxAgeMs = Number.isFinite(maxAgeMsRaw) && maxAgeMsRaw > 0 ? maxAgeMsRaw : 0;
      const current = typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const loadedAt = Number(PCONV.sessionDetailLoadedAtById[sid] || 0);
      if (
        !force
        && hasConversationTaskTrackingData(current && current.task_tracking)
        && loadedAt > 0
        && (!maxAgeMs || (Date.now() - loadedAt) < maxAgeMs)
      ) {
        return current;
      }
      if (PCONV.sessionDetailPromiseById[sid]) return PCONV.sessionDetailPromiseById[sid];
      PCONV.sessionDetailPromiseById[sid] = (async () => {
        try {
          const resp = await fetch("/api/sessions/" + encodeURIComponent(sid), {
            cache: "no-store",
            headers: authHeaders(),
          });
          const payload = await resp.json().catch(() => null);
          if (!resp.ok) {
            throw new Error(String((payload && (payload.error || payload.message)) || ("读取会话详情失败（HTTP " + resp.status + "）")));
          }
          const fallback = current || { sessionId: sid, id: sid };
          const normalized = typeof normalizeSessionInfoResponse === "function"
            ? normalizeSessionInfoResponse(payload, fallback)
            : normalizeConversationSessionDetail(payload, fallback);
          const merged = mergeConversationSessionDetailIntoStore(normalized, sid);
          if (String(STATE.selectedSessionId || "").trim() === sid && typeof renderConversationDetail === "function") {
            renderConversationDetail(false);
          }
          return merged;
        } catch (err) {
          PCONV.sessionDetailErrorById[sid] = err && err.message ? String(err.message) : "读取会话详情失败";
          throw err;
        } finally {
          delete PCONV.sessionDetailPromiseById[sid];
        }
      })();
      return PCONV.sessionDetailPromiseById[sid];
    }

    function markConversationSessionDirectoryMeta(projectId, extra = {}) {
      const pid = String(projectId || "").trim();
      if (!pid) return;
      ensureConversationSessionDirectoryStateMaps();
      const current = (PCONV.sessionDirectoryMetaByProject && PCONV.sessionDirectoryMetaByProject[pid]) || {};
      PCONV.sessionDirectoryMetaByProject[pid] = {
        ...current,
        ...extra,
        liveLoaded: extra && Object.prototype.hasOwnProperty.call(extra, "liveLoaded")
          ? !!extra.liveLoaded
          : !!current.liveLoaded,
        loadedAt: String((extra && extra.loadedAt) || current.loadedAt || new Date().toISOString()),
        source: String((extra && extra.source) || current.source || ""),
        error: String((extra && extra.error) || ""),
      };
    }

    function formatConversationSessionsFromApi(projectId, sessions) {
      const pid = String(projectId || "").trim();
      return (Array.isArray(sessions) ? sessions : []).map((s) => {
        const sid = firstNonEmptyText([s.id, s.session_id, s.sessionId]);
        const channelName = String(s.channel_name || "");
        const presentation = resolveConversationSessionPresentation(s, channelName, sid);
        const runtimeState = normalizeRuntimeState(s.runtime_state || s.runtimeState || null);
        const latestRunSummary = normalizeLatestRunSummary(s.latest_run_summary || s.latestRunSummary || null);
        const latestEffectiveRunSummary = normalizeLatestEffectiveRunSummary(
          s.latest_effective_run_summary || s.latestEffectiveRunSummary || null
        );
        const sessionHealthState = normalizeSessionHealthState(
          firstNonEmptyText([s.session_health_state, s.sessionHealthState]),
          ""
        );
        const rawHeartbeat = (s.heartbeat && typeof s.heartbeat === "object") ? s.heartbeat : {};
        const heartbeatItems = Array.isArray(rawHeartbeat.items)
          ? normalizeHeartbeatTaskItemsClient(rawHeartbeat.items, pid, rawHeartbeat)
          : [];
        const heartbeatSummary = normalizeHeartbeatSummaryClient(
          s.heartbeat_summary || s.heartbeatSummary || rawHeartbeat.summary || {},
          heartbeatItems
        );
        const preferSyntheticPreviewSender = sessionUsesSyntheticPreviewSender({
          latest_run_summary: latestRunSummary,
          latest_effective_run_summary: latestEffectiveRunSummary,
        }, latestEffectiveRunSummary.preview || "");
        const baseSession = {
          sessionId: String(sid || ""),
          id: String(sid || ""),
          project_id: pid,
          channel_name: channelName,
          environment: String(s.environment || "stable"),
          worktree_root: String(s.worktree_root || s.worktreeRoot || ""),
          workdir: String(s.workdir || ""),
          branch: String(s.branch || ""),
          primaryChannel: channelName,
          channels: [channelName],
          alias: presentation.alias,
          displayChannel: presentation.displayChannel,
          displayName: presentation.displayName,
          displayNameSource: presentation.displayNameSource,
          codexTitle: String(s.codex_title || ""),
          cli_type: String(s.cli_type || "codex"),
          model: normalizeSessionModel(s.model),
          reasoning_effort: normalizeReasoningEffort(s.reasoning_effort || s.reasoningEffort),
          status: String(s.status || "active"),
          created_at: String(s.created_at || ""),
          last_used_at: String(s.last_used_at || ""),
          is_primary: !!s.is_primary,
          source: String(s.source || ""),
          lastActiveAt: String(s.lastActiveAt || latestRunSummary.updated_at || s.last_used_at || ""),
          lastStatus: "idle",
          lastPreview: String(latestEffectiveRunSummary.preview || s.lastPreview || latestRunSummary.preview || ""),
          lastTimeout: false,
          lastError: String(s.lastError || latestRunSummary.error || ""),
          lastErrorHint: "",
          lastSpeaker: String(s.lastSpeaker || (preferSyntheticPreviewSender ? "assistant" : (latestRunSummary.speaker || "assistant")) || "assistant"),
          lastSenderType: String(s.lastSenderType || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_type || "legacy"))),
          lastSenderName: String(s.lastSenderName || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_name || ""))),
          lastSenderSource: String(s.lastSenderSource || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_source || "legacy"))),
          runCount: Math.max(0, Number(s.runCount || latestRunSummary.run_count || 0) || 0),
          latestUserMsg: String(s.latestUserMsg || latestRunSummary.latest_user_msg || ""),
          latestAiMsg: String(s.latestAiMsg || latestRunSummary.latest_ai_msg || ""),
          session_health_state: sessionHealthState,
          session_display_state: normalizeDisplayState(
            firstNonEmptyText([s.session_display_state, s.sessionDisplayState, runtimeState.display_state]) || "idle",
            "idle"
          ),
          session_display_reason: String(firstNonEmptyText([s.session_display_reason, s.sessionDisplayReason]) || ""),
          latest_run_summary: latestRunSummary,
          latest_effective_run_summary: latestEffectiveRunSummary,
          runtime_state: runtimeState,
          heartbeat_summary: heartbeatSummary,
          task_tracking: normalizeTaskTrackingClient(s.task_tracking || s.taskTracking || null),
        };
        baseSession.lastStatus = getSessionDisplayState(baseSession);
        return baseSession;
      });
    }

    function conversationSessionFetchKey(projectId, channelName) {
      const pid = String(projectId || "").trim();
      const channel = String(channelName || "").trim();
      return pid + "::" + channel;
    }

    async function fetchConversationSessionsFromApi(projectId, channelName, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      ensureConversationSessionDirectoryStateMaps();
      const force = !!(opts && opts.force);
      const freshnessMsRaw = Number((opts && opts.freshnessMs) || 0);
      const freshnessMs = Number.isFinite(freshnessMsRaw) && freshnessMsRaw > 0 ? freshnessMsRaw : 0;
      const key = conversationSessionFetchKey(pid, channelName);
      const cached = !force ? PCONV.sessionFetchCacheByKey[key] : null;
      if (
        !force
        && freshnessMs > 0
        && cached
        && Array.isArray(cached.sessions)
        && (Date.now() - Number(cached.loadedAt || 0)) < freshnessMs
      ) {
        return cached.sessions.slice();
      }
      if (!force && PCONV.sessionFetchPromiseByKey[key]) {
        return PCONV.sessionFetchPromiseByKey[key];
      }
      const qs = new URLSearchParams();
      qs.set("project_id", pid);
      if (channelName) qs.set("channel_name", String(channelName));
      const task = (async () => {
        const r = await fetch("/api/sessions?" + qs.toString(), { cache: "no-store" });
        if (!r.ok) {
          throw new Error("loadChannelSessions failed: " + String(r.status || "unknown"));
        }
        const j = await r.json();
        updateConversationProjectPollingMeta(pid, j);
        const sessions = formatConversationSessionsFromApi(
          pid,
          Array.isArray(j && j.sessions) ? j.sessions : []
        );
        PCONV.sessionFetchCacheByKey[key] = {
          loadedAt: Date.now(),
          sessions: sessions.slice(),
        };
        return sessions.slice();
      })().finally(() => {
        delete PCONV.sessionFetchPromiseByKey[key];
      });
      PCONV.sessionFetchPromiseByKey[key] = task;
      return task;
    }

    async function ensureConversationProjectSessionDirectory(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      ensureConversationSessionDirectoryStateMaps();
      const force = !!(opts && opts.force);
      const existing = Array.isArray(PCONV.sessionDirectoryByProject[pid])
        ? PCONV.sessionDirectoryByProject[pid].slice()
        : [];
      const meta = PCONV.sessionDirectoryMetaByProject[pid] || null;
      if (!force && meta && meta.liveLoaded && Array.isArray(PCONV.sessionDirectoryByProject[pid])) {
        return existing;
      }
      if (!force && PCONV.sessionDirectoryPromiseByProject[pid]) {
        return PCONV.sessionDirectoryPromiseByProject[pid];
      }
      const task = (async () => {
        try {
          const serverSessions = await fetchConversationSessionsFromApi(pid, "", { force });
          const merged = mergeConversationSessions(configuredProjectConversations(pid), serverSessions);
          PCONV.sessionDirectoryByProject[pid] = merged.slice();
          markConversationSessionDirectoryMeta(pid, {
            ...resolveConversationSessionDirectoryLiveMeta({
              canSeedSelectedSession: !!opts.canSeedSelectedSession,
              hasSelectedTimelineCache: !!opts.hasSelectedTimelineCache,
              hasServerDirectorySessions: !!serverSessions.length,
              existingMeta: meta,
            }),
            loadedAt: new Date().toISOString(),
            error: "",
          });
          return merged.slice();
        } catch (err) {
          const fallback = existing.length ? existing : mergeConversationSessions(configuredProjectConversations(pid), []);
          if (!existing.length) PCONV.sessionDirectoryByProject[pid] = fallback.slice();
          markConversationSessionDirectoryMeta(pid, {
            liveLoaded: false,
            source: existing.length ? "cache" : "config",
            loadedAt: new Date().toISOString(),
            error: String((err && err.message) || err || "unknown"),
          });
          return fallback.slice();
        } finally {
          delete PCONV.sessionDirectoryPromiseByProject[pid];
        }
      })();
      PCONV.sessionDirectoryPromiseByProject[pid] = task;
      return task;
    }

    function buildExistingSessionAttachPayload(options) {
      const opts = options || {};
      return {
        project_id: String(opts.projectId || "").trim(),
        channel_name: String(opts.channelName || "").trim(),
        mode: "attach_existing",
        session_id: String(opts.sessionId || "").trim(),
        cli_type: String(opts.cliType || "codex").trim() || "codex",
        model: normalizeSessionModel(opts.model || ""),
        alias: String(opts.alias || "").trim(),
        purpose: String(opts.purpose || "").trim(),
        session_role: String(opts.sessionRole || "child").trim() || "child",
        reuse_strategy: "attach_existing",
        set_as_primary: String(opts.sessionRole || "child").trim() === "primary",
        environment: normalizeSessionEnvironmentValue(opts.environment || "stable"),
        worktree_root: String(opts.worktreeRoot || "").trim(),
        workdir: String(opts.workdir || "").trim(),
        branch: String(opts.branch || "").trim(),
      };
    }

    async function recoverTimeoutCreatedSession(options) {
      const attachPayload = buildExistingSessionAttachPayload(options);
      const { resp, json, retried } = await postSessionCreateWithChannelRetry(attachPayload);
      const session = json && json.session;
      const sid = String((session && session.id) || attachPayload.session_id || "").trim();
      if (!resp || !resp.ok || !sid) {
        const detail = json && (json.error || json.message || (json.detail && (json.detail.error || json.detail.message)));
        return {
          ok: false,
          sid,
          session,
          json,
          retried: !!retried,
          error: String(detail || "unknown"),
        };
      }
      return {
        ok: true,
        sid,
        session,
        json,
        retried: !!retried,
      };
    }

    async function createNewConversation() {
      const projSelect = document.getElementById("newConvProject");
      const chSelect = document.getElementById("newConvChannel");
      const cliSelect = document.getElementById("newConvCliType");
      const createBtn = document.getElementById("newConvCreateBtn");
      const sidInput = document.getElementById("newConvSessionId");
      const modelInput = document.getElementById("newConvModel");
      const purposeInput = document.getElementById("newConvPurpose");
      const aliasInput = document.getElementById("newConvAlias");
      const sessionRoleInput = document.getElementById("newConvSessionRole");
      const reuseStrategyInput = document.getElementById("newConvReuseStrategy");
      const environmentInput = document.getElementById("newConvEnvironment");
      const worktreeRootInput = document.getElementById("newConvWorktreeRoot");
      const workdirInput = document.getElementById("newConvWorkdir");
      const branchInput = document.getElementById("newConvBranch");
      const initMessageInput = document.getElementById("newConvInitMessage");

      const pid = String((projSelect && projSelect.value) || "");
      const ch = String((chSelect && chSelect.value) || "");
      const cli = String((cliSelect && cliSelect.value) || "codex");
      const mode = normalizeNewConvMode(NEW_CONV_UI.mode);
      const sidFromInput = String((sidInput && sidInput.value) || "").trim();
      const model = normalizeSessionModel(modelInput && modelInput.value);
      const purpose = String((purposeInput && purposeInput.value) || "").trim();
      const alias = String((aliasInput && aliasInput.value) || "").trim();
      const sessionRole = String((sessionRoleInput && sessionRoleInput.value) || "child").trim() || "child";
      const reuseStrategy = String((reuseStrategyInput && reuseStrategyInput.value) || "create_new").trim() || "create_new";
      const environment = normalizeSessionEnvironmentValue((environmentInput && environmentInput.value) || "stable");
      const worktreeRoot = String((worktreeRootInput && worktreeRootInput.value) || "").trim();
      const workdir = String((workdirInput && workdirInput.value) || "").trim();
      const branch = String((branchInput && branchInput.value) || "").trim();
      const initMessage = String((initMessageInput && initMessageInput.value) || "").trim();

      if (!pid || pid === "overview") {
        newConvModalError("请选择项目");
        return;
      }
      if (!ch) {
        newConvModalError("请选择通道");
        return;
      }

      const oldText = createBtn ? createBtn.textContent : "";
      if (createBtn) {
        createBtn.disabled = true;
        createBtn.textContent = mode === "attach" ? "绑定中..." : "创建中...";
      }
      newConvModalError("");

      try {
        let sid = "";
        let effectiveCli = cli;
        let tip = "";
        let timeoutRecovered = false;
        const appendContextHint = (baseTip, payload) => {
          const meta = buildProjectExecutionContextMeta(
            payload && (payload.project_execution_context || payload.projectExecutionContext || null)
          );
          if (!meta.available) return String(baseTip || "");
          return String(baseTip || "") + " 上下文来源：" + String((meta.sourceMeta && meta.sourceMeta.text) || "待返回") + "。";
        };

        if (mode === "attach") {
          if (!looksLikeSessionId(sidFromInput)) {
            newConvModalError("Session ID 格式不正确（支持 UUID 或 ses_...）。");
            return;
          }
          const attachPayload = buildExistingSessionAttachPayload({
            projectId: pid,
            channelName: ch,
            sessionId: sidFromInput,
            cliType: cli,
            model,
            alias,
            purpose,
            sessionRole,
            environment,
            worktreeRoot,
            workdir,
            branch,
          });
          const { resp: r, json: j, retried: attachRetried } = await postSessionCreateWithChannelRetry(attachPayload);
          if (!r.ok) {
            const detail = j && (j.error || j.message || (j.detail && (j.detail.error || j.detail.message)));
            newConvModalError("补登记失败：" + String(detail || "unknown"));
            return;
          }
          const session = j && j.session;
          sid = String((session && session.id) || sidFromInput || "").trim();
          if (!sid) {
            newConvModalError("补登记失败：未获取到 session_id");
            return;
          }
          if (session && session.cli_type) effectiveCli = String(session.cli_type);
          const ok = await setBinding(pid, ch, sid, effectiveCli);
          if (!ok) {
            newConvModalError("补登记成功但绑定失败：未能写入服务端会话绑定（请检查 Token 或服务状态）。");
            return;
          }
          const probe = await fetch("/api/sessions/" + encodeURIComponent(sid), { cache: "no-store" }).catch(() => null);
          if (!probe || !probe.ok) {
            tip = "已补登记并绑定已有对话，但当前详情读取失败，请刷新后重试。";
          } else {
            const probePayload = await probe.json().catch(() => ({}));
            tip = (j && j.imported)
              ? "已补登记并绑定已有对话，可直接发送消息。"
              : "已恢复并绑定已有对话，可直接发送消息。";
            if (model) {
              const modelUpdated = await tryUpdateSessionModel(sid, model);
              if (modelUpdated) tip = "已绑定已有对话，并更新模型配置。";
            }
            tip = appendContextHint(tip, probePayload);
            if (attachRetried) tip += " 已自动等待通道注册生效。";
          }
        } else {
          // 调用新的 POST /api/sessions API 创建会话
          const createPayload = {
            project_id: pid,
            channel_name: ch,
            cli_type: cli,
            model,
            alias,
            purpose,
            session_role: sessionRole,
            reuse_strategy: reuseStrategy,
            set_as_primary: sessionRole === "primary",
            environment,
            worktree_root: worktreeRoot,
            workdir,
            branch,
          };
          const { resp: r, json: j, retried: createRetried } = await postSessionCreateWithChannelRetry(createPayload);
          if (!r.ok) {
            const detailObj = (j && typeof j.detail === "object") ? j.detail : null;
            const timeoutErr = String(
              (detailObj && detailObj.error)
              || (j && j.error)
              || ""
            ).toLowerCase();
            const timeoutSid = String(
              (detailObj && (detailObj.sessionId || detailObj.session_id))
              || ""
            ).trim();
            if (timeoutSid && looksLikeSessionId(timeoutSid) && timeoutErr.indexOf("timeout") >= 0) {
              sid = timeoutSid;
              timeoutRecovered = true;
            }
            const detail = j && (j.detail || j.error || j.message);
            let detailStr;
            if (detail && typeof detail === "object") {
              detailStr = detail.error || detail.message || JSON.stringify(detail);
            } else {
              detailStr = String(detail || "unknown");
            }
            if (!sid) {
              newConvModalError("创建失败：" + detailStr);
              return;
            }
          }
          const session = j && j.session;
          if (!sid) sid = session && session.id ? String(session.id).trim() : "";
          if (!sid) {
            newConvModalError("创建失败：未获取到 session_id");
            return;
          }
          let recoveredSessionPayload = session || j || null;
          let attachRetried = false;
          if (timeoutRecovered) {
            const recovered = await recoverTimeoutCreatedSession({
              projectId: pid,
              channelName: ch,
              sessionId: sid,
              cliType: effectiveCli,
              model,
              alias,
              purpose,
              sessionRole,
              environment,
              worktreeRoot,
              workdir,
              branch,
            });
            if (!recovered.ok) {
              newConvModalError("创建超时后补登记失败：" + String(recovered.error || "unknown"));
              return;
            }
            sid = String(recovered.sid || sid).trim();
            attachRetried = !!recovered.retried;
            recoveredSessionPayload = recovered.session || recovered.json || recoveredSessionPayload;
          }
          const effectiveSession = recoveredSessionPayload && recoveredSessionPayload.session
            ? recoveredSessionPayload.session
            : recoveredSessionPayload;
          if (effectiveSession && effectiveSession.cli_type) effectiveCli = String(effectiveSession.cli_type);
          const ok = await setBinding(pid, ch, sid, effectiveCli);
          if (!ok) {
            newConvModalError("创建成功但绑定失败：请检查 Token 或服务状态后重试绑定。");
            return;
          }
          tip = timeoutRecovered
            ? "已完成 timeout-recovered 补登记并绑定。"
            : (j && j.reused ? "已复用并绑定现有对话。" : "已创建并绑定新对话。");
          if (initMessage) {
            if (createBtn) createBtn.textContent = "首发中...";
            const bootstrapMode = /^\s*--bootstrap-message\s*$/i.test(initMessage);
            if (bootstrapMode) {
              const msgs = buildBootstrapVisibleMessages(ch);
              const sendA = await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, msgs[0], model);
              const sendB = sendA.ok
                ? await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, msgs[1], model)
                : { ok: false };
              if (sendA.ok && sendB.ok) {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "并自动发送两条标准首发消息。";
              } else {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "但标准首发消息发送不完整，请手动补发。";
              }
            } else {
              const sendRet = await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, initMessage, model);
              if (sendRet.ok) {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "并自动发送初始化消息。";
              } else {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "但初始化消息发送失败，请手动发送。";
              }
            }
          }
          if (createRetried || attachRetried) tip += " 已自动等待通道注册生效。";
          tip = appendContextHint(tip, effectiveSession || j || null);
        }

        const visRet = await verifySessionBindingVisibility(pid, ch, sid);
        if (visRet.ok && visRet.hardRefreshRequired) {
          tip += " 已自动重建看板；请按 Cmd+Shift+R 强刷后确认可见性。";
        }

        closeNewConvModal();
        await refreshConversationPanel();
        setSelectedSessionId(sid, true, { explicit: true });
        setHintText(STATE.panelMode, tip);
        render();
      } catch (err) {
        newConvModalError((mode === "attach" ? "绑定失败：" : "创建失败：") + "网络或服务异常");
      } finally {
        if (createBtn) {
          createBtn.disabled = false;
          createBtn.textContent = oldText || (mode === "attach" ? "绑定已有对话" : "创建并绑定");
        }
      }
    }

    // 加载指定通道的会话列表
    async function loadChannelSessions(projectId, channelName, opts = {}) {
      if (!projectId || projectId === "overview") {
        PCONV.sessions = [];
        return;
      }
      try {
        const existingSessions = Array.isArray(PCONV.sessions) ? PCONV.sessions.slice() : [];
        const existingById = new Map();
        existingSessions.forEach((row) => {
          const normalized = normalizeConversationSession(row);
          if (!normalized) return;
          existingById.set(normalized.sessionId, normalized);
        });
        const formatted = (await fetchConversationSessionsFromApi(projectId, channelName, {
          force: !!(opts && opts.force),
          freshnessMs: Number.isFinite(Number((opts && opts.freshnessMs) || 0))
            ? Number((opts && opts.freshnessMs) || 0)
            : (channelName ? 800 : 1200),
        }))
          .map((row) => preserveConversationSessionDetailFields(
            row,
            existingById.get(String((row && (row.sessionId || row.id || row.session_id)) || "").trim()) || null
          ))
          .filter(Boolean);
        // 更新 PCONV.sessions
        if (channelName) {
          // 只更新当前通道的会话，保留其他通道的会话
          const otherSessions = existingSessions.filter(s => s.channel_name !== channelName);
          PCONV.sessions = [...otherSessions, ...formatted];
        } else {
          PCONV.sessions = formatted;
          ensureConversationSessionDirectoryStateMaps();
          PCONV.sessionDirectoryByProject[String(projectId)] = mergeConversationSessions(configuredProjectConversations(projectId), formatted);
          markConversationSessionDirectoryMeta(projectId, {
            liveLoaded: true,
            source: "api",
            loadedAt: new Date().toISOString(),
            error: "",
          });
        }
        PCONV.lastRefreshAt = new Date().toLocaleTimeString("zh-CN", { hour12: false });
      } catch (err) {
        console.error("loadChannelSessions error:", err);
      }
    }

    function normalizeConversationSession(raw) {
      if (!raw) return null;
      const sid = String(raw.sessionId || raw.id || raw.session_id || "").trim();
      if (!looksLikeSessionId(sid)) return null;
      const projectId = String(raw.project_id || raw.projectId || STATE.project || "").trim();
      const channelName = String(
        raw.channel_name || raw.primaryChannel || raw.name ||
        (Array.isArray(raw.channels) && raw.channels.length ? raw.channels[0] : "")
      ).trim();
      const presentation = resolveConversationSessionPresentation(raw, channelName, sid);
      const channels = Array.isArray(raw.channels)
        ? raw.channels.map(x => String(x || "").trim()).filter(Boolean)
        : [];
      if (channelName && !channels.includes(channelName)) channels.unshift(channelName);
      const rawHeartbeat = (raw.heartbeat && typeof raw.heartbeat === "object") ? raw.heartbeat : {};
      const heartbeatItems = Array.isArray(rawHeartbeat.items)
        ? normalizeHeartbeatTaskItemsClient(rawHeartbeat.items, String(STATE.project || "").trim(), rawHeartbeat)
        : [];
      const heartbeatSummary = normalizeHeartbeatSummaryClient(
        raw.heartbeat_summary || raw.heartbeatSummary || rawHeartbeat.summary || {},
        heartbeatItems
      );
      const normalizeConversationListMetricsClientResult = typeof normalizeConversationListMetricsClient === "function"
        ? normalizeConversationListMetricsClient(raw.conversation_list_metrics || raw.conversationListMetrics || null)
        : (((raw.conversation_list_metrics || raw.conversationListMetrics) && typeof (raw.conversation_list_metrics || raw.conversationListMetrics) === "object")
          ? { ...(raw.conversation_list_metrics || raw.conversationListMetrics) }
          : null);
      const memoSummary = (raw.memo_summary && typeof raw.memo_summary === "object")
        ? { ...raw.memo_summary }
        : ((raw.memoSummary && typeof raw.memoSummary === "object")
          ? { ...raw.memoSummary }
          : ((normalizeConversationListMetricsClientResult && normalizeConversationListMetricsClientResult.memo_summary && typeof normalizeConversationListMetricsClientResult.memo_summary === "object")
            ? { ...normalizeConversationListMetricsClientResult.memo_summary }
            : null));

      return {
        sessionId: sid,
        id: sid,
        project_id: projectId,
        projectId,
        channel_name: channelName,
        primaryChannel: channelName || "",
        channels,
        alias: presentation.alias,
        displayChannel: presentation.displayChannel,
        displayName: presentation.displayName,
        displayNameSource: presentation.displayNameSource,
        codexTitle: String(raw.codexTitle || raw.codex_title || ""),
        environment: normalizeSessionEnvironmentValue(raw.environment || raw.environmentName || "stable"),
        worktree_root: String(raw.worktree_root || raw.worktreeRoot || ""),
        workdir: String(raw.workdir || ""),
        branch: String(raw.branch || ""),
        cli_type: String(raw.cli_type || raw.cliType || "codex"),
        model: normalizeSessionModel(raw.model),
        reasoning_effort: normalizeReasoningEffort(raw.reasoning_effort || raw.reasoningEffort),
        status: String(raw.status || "active"),
        created_at: String(raw.created_at || ""),
        last_used_at: String(raw.last_used_at || ""),
        is_primary: boolLike(raw.is_primary || raw.isPrimary),
        is_deleted: boolLike(raw.is_deleted || raw.isDeleted),
        deleted_at: String(raw.deleted_at || raw.deletedAt || ""),
        deleted_reason: String(raw.deleted_reason || raw.deletedReason || ""),
        source: String(raw.source || ""),
        context_binding_state: String(raw.context_binding_state || raw.contextBindingState || ""),
        lastActiveAt: String(raw.lastActiveAt || raw.last_used_at || ""),
        lastStatus: normalizeDisplayState(
          firstNonEmptyText([raw.session_display_state, raw.sessionDisplayState, raw.lastStatus]) || "idle",
          "idle"
        ),
        lastPreview: String(
          normalizeLatestEffectiveRunSummary(raw.latest_effective_run_summary || raw.latestEffectiveRunSummary || null).preview
          || raw.lastPreview
          || normalizeLatestRunSummary(raw.latest_run_summary || raw.latestRunSummary || null).preview
          || ""
        ),
        lastTimeout: boolLike(raw.lastTimeout || raw.last_timeout),
        lastError: String(raw.lastError || raw.last_error || ""),
        lastErrorHint: String(raw.lastErrorHint || raw.last_error_hint || ""),
        lastSpeaker: String(raw.lastSpeaker || "assistant"),
        lastSenderType: String(raw.lastSenderType || "legacy"),
        lastSenderName: String(raw.lastSenderName || ""),
        lastSenderSource: String(raw.lastSenderSource || "legacy"),
        runCount: Number(raw.runCount || 0),
        latestUserMsg: String(raw.latestUserMsg || ""),
        latestAiMsg: String(raw.latestAiMsg || ""),
        session_display_state: normalizeDisplayState(
          firstNonEmptyText([
            raw.session_display_state,
            raw.sessionDisplayState,
            raw.runtime_state && raw.runtime_state.display_state,
            raw.runtimeState && raw.runtimeState.display_state,
          ]) || "idle",
          "idle"
        ),
        session_display_reason: String(firstNonEmptyText([raw.session_display_reason, raw.sessionDisplayReason]) || ""),
        latest_run_summary: normalizeLatestRunSummary(raw.latest_run_summary || raw.latestRunSummary || null),
        runtime_state: normalizeRuntimeState(raw.runtime_state || raw.runtimeState || null),
        heartbeat_summary: heartbeatSummary,
        project_execution_context: normalizeProjectExecutionContext(
          raw.project_execution_context || raw.projectExecutionContext || null
        ),
        task_tracking: normalizeTaskTrackingClient(raw.task_tracking || raw.taskTracking || null),
        conversation_list_metrics: normalizeConversationListMetricsClientResult,
        memo_summary: memoSummary,
        memoSummary: memoSummary,
      };
    }

    function preserveConversationSessionDetailFields(nextRaw, prevRaw) {
      const next = normalizeConversationSession(nextRaw);
      if (!next) return null;
      const prev = normalizeConversationSession(prevRaw);
      if (!prev || prev.sessionId !== next.sessionId) return next;
      const nextExecContext = buildProjectExecutionContextMeta(next.project_execution_context || null);
      const prevExecContext = buildProjectExecutionContextMeta(prev.project_execution_context || null);
      return {
        ...next,
        project_execution_context: nextExecContext.available
          ? next.project_execution_context
          : (prevExecContext.available ? prev.project_execution_context : next.project_execution_context),
        task_tracking: hasConversationTaskTrackingData(next.task_tracking)
          ? next.task_tracking
          : (hasConversationTaskTrackingData(prev.task_tracking) ? prev.task_tracking : null),
        conversation_list_metrics: hasConversationListMetricsClientData(next.conversation_list_metrics)
          ? next.conversation_list_metrics
          : (hasConversationListMetricsClientData(prev.conversation_list_metrics) ? prev.conversation_list_metrics : next.conversation_list_metrics),
        memo_summary: next.memo_summary || next.memoSummary || prev.memo_summary || prev.memoSummary || null,
        memoSummary: next.memoSummary || next.memo_summary || prev.memoSummary || prev.memo_summary || null,
      };
    }

    function mergeConversationSessions(localSessions, serverSessions) {
      const map = new Map();
      const serverChannelSessions = new Map();
      const hiddenServerSessionIds = new Set();
      const isVisibleSessionRow = (row) => {
        const item = (row && typeof row === "object") ? row : {};
        if (typeof isVisibleConversationSession === "function") {
          return isVisibleConversationSession(item);
        }
        const deleted = typeof isDeletedSession === "function"
          ? isDeletedSession(item)
          : boolLike(item.is_deleted || item.isDeleted);
        const inactive = typeof isInactiveSession === "function"
          ? isInactiveSession(item)
          : String(item.status || item.session_status || item.sessionStatus || "").trim().toLowerCase() === "inactive";
        return !deleted && !inactive;
      };

      for (const raw of (Array.isArray(serverSessions) ? serverSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
        if (!isVisibleSessionRow(n)) {
          hiddenServerSessionIds.add(n.sessionId);
          continue;
        }
        const channelKey = String(n.channel_name || n.primaryChannel || "").trim();
        if (channelKey) {
          let bucket = serverChannelSessions.get(channelKey);
          if (!bucket) {
            bucket = new Set();
            serverChannelSessions.set(channelKey, bucket);
          }
          bucket.add(n.sessionId);
        }
      }

      for (const raw of (Array.isArray(localSessions) ? localSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
        if (hiddenServerSessionIds.has(n.sessionId) || !isVisibleSessionRow(n)) continue;
        const channelKey = String(n.channel_name || n.primaryChannel || "").trim();
        const channelBucket = channelKey ? serverChannelSessions.get(channelKey) : null;
        if (channelBucket && channelBucket.size && !channelBucket.has(n.sessionId)) continue;
        map.set(n.sessionId, n);
      }
      for (const raw of (Array.isArray(serverSessions) ? serverSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
        if (hiddenServerSessionIds.has(n.sessionId) || !isVisibleSessionRow(n)) {
          map.delete(n.sessionId);
          continue;
        }
        const prev = map.get(n.sessionId);
        if (!prev) {
          map.set(n.sessionId, n);
          continue;
        }
        const channels = Array.from(new Set([...(prev.channels || []), ...(n.channels || [])].filter(Boolean)));
        const nextRuntime = normalizeRuntimeState(n.runtime_state || n.runtimeState || null);
        const nextExecContext = buildProjectExecutionContextMeta(n.project_execution_context || null);
        const prevExecContext = buildProjectExecutionContextMeta(prev.project_execution_context || null);
        const nextTaskTracking = hasConversationTaskTrackingData(n.task_tracking)
          ? n.task_tracking
          : (hasConversationTaskTrackingData(prev.task_tracking) ? prev.task_tracking : null);
        const nextDisplayState = normalizeDisplayState(
          firstNonEmptyText([n.session_display_state, n.sessionDisplayState, nextRuntime.display_state]) || "idle",
          "idle"
        );
        const prevIsExplicitSidFallback = String(prev.displayNameSource || "").trim().toLowerCase() === "explicit_sid_fallback";
        const mergedAlias = String(n.alias || (prevIsExplicitSidFallback ? "" : prev.alias) || "").trim();
        const mergedChannelName = String(n.channel_name || prev.channel_name || "").trim();
        const mergedPresentation = resolveConversationSessionPresentation({
          alias: mergedAlias,
          displayChannel: n.displayChannel || prev.displayChannel || "",
          displayName: n.displayName || prev.displayName || "",
          display_name_source: n.displayNameSource || prev.displayNameSource || "",
        }, mergedChannelName, n.sessionId);
        map.set(n.sessionId, {
          ...prev,
          ...n,
          channels,
          channel_name: n.channel_name || prev.channel_name,
          primaryChannel: n.primaryChannel || prev.primaryChannel,
          displayChannel: mergedPresentation.displayChannel,
          displayName: mergedPresentation.displayName,
          displayNameSource: mergedPresentation.displayNameSource,
          codexTitle: n.codexTitle || prev.codexTitle,
          alias: mergedAlias,
          cli_type: n.cli_type || prev.cli_type,
          model: normalizeSessionModel(n.model || prev.model),
          reasoning_effort: normalizeReasoningEffort(n.reasoning_effort || prev.reasoning_effort),
          // Prefer server-provided primary flag when present, avoid stale local cache elevating old sessions to primary.
          is_primary: String(n.source || "").trim()
            ? boolLike(n.is_primary)
            : (boolLike(n.is_primary) || boolLike(prev.is_primary)),
          is_deleted: boolLike(n.is_deleted || prev.is_deleted),
          deleted_at: firstNonEmptyText([n.deleted_at, prev.deleted_at]),
          deleted_reason: firstNonEmptyText([n.deleted_reason, prev.deleted_reason]),
          source: firstNonEmptyText([n.source, prev.source]),
          runtime_state: nextRuntime,
          session_display_state: nextDisplayState,
          session_display_reason: firstNonEmptyText([n.session_display_reason, prev.session_display_reason]),
          latest_run_summary: n.latest_run_summary || prev.latest_run_summary || normalizeLatestRunSummary(null),
          lastStatus: nextDisplayState,
          lastPreview: String(getSessionPrimaryPreviewText(n) || getSessionPrimaryPreviewText(prev) || n.lastPreview || prev.lastPreview || ""),
          lastError: String(n.lastError || prev.lastError || ""),
          lastSpeaker: String(n.lastSpeaker || prev.lastSpeaker || "assistant"),
          lastSenderType: String(n.lastSenderType || prev.lastSenderType || "legacy"),
          lastSenderName: String(n.lastSenderName || prev.lastSenderName || ""),
          lastSenderSource: String(n.lastSenderSource || prev.lastSenderSource || "legacy"),
          latestUserMsg: String(n.latestUserMsg || prev.latestUserMsg || ""),
          latestAiMsg: String(n.latestAiMsg || prev.latestAiMsg || ""),
          runCount: Math.max(0, Number(n.runCount || prev.runCount || 0) || 0),
          lastActiveAt: String(n.lastActiveAt || prev.lastActiveAt || n.last_used_at || prev.last_used_at || ""),
          heartbeat_summary: normalizeHeartbeatSummaryClient(
            n.heartbeat_summary || prev.heartbeat_summary || {},
            []
          ),
          conversation_list_metrics: mergeConversationListMetricsClient(
            prev.conversation_list_metrics || null,
            n.conversation_list_metrics || null
          ),
          project_execution_context: nextExecContext.available
            ? n.project_execution_context
            : (prevExecContext.available ? prev.project_execution_context : n.project_execution_context),
          task_tracking: nextTaskTracking,
        });
      }

      return Array.from(map.values());
    }

    const NEW_CHANNEL_UI = {
      open: false,
      submitting: false,
      inputBound: false,
      phase: "form",
      mode: "direct",
      selectedAgentSessionId: "",
      selectedAgent: null,
      agentCandidates: [],
      agentCandidatesProjectId: "",
      agentLoading: false,
      agentError: "",
      agentMenuOpen: false,
    };
