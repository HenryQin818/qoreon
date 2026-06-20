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

    async function tryUpdateSessionCodeBuddyPermissionMode(sessionId, mode) {
      const sid = String(sessionId || "").trim();
      const normalized = typeof normalizeCodeBuddyPermissionMode === "function"
        ? normalizeCodeBuddyPermissionMode(mode)
        : String(mode || "default").trim();
      if (!looksLikeSessionId(sid) || !normalized) return false;
      try {
        const r = await fetch("/api/sessions/" + encodeURIComponent(sid), {
          method: "PUT",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ codebuddy_permission_mode: normalized }),
        });
        if (!r || !r.ok) return false;
        const payload = await r.json().catch(() => null);
        const session = payload && typeof payload === "object" && payload.session && typeof payload.session === "object"
          ? payload.session
          : payload;
        const echoed = session && typeof session === "object"
          ? (Object.prototype.hasOwnProperty.call(session, "codebuddy_permission_mode")
            ? session.codebuddy_permission_mode
            : session.codebuddyPermissionMode)
          : "";
        const confirmed = typeof normalizeCodeBuddyPermissionMode === "function"
          ? normalizeCodeBuddyPermissionMode(echoed)
          : String(echoed || "default").trim();
        return confirmed === normalized;
      } catch (_) {
        return false;
      }
    }

    async function tryUpdateSessionClaudePermissionMode(sessionId, mode) {
      const sid = String(sessionId || "").trim();
      const normalized = typeof normalizeClaudePermissionMode === "function"
        ? normalizeClaudePermissionMode(mode)
        : String(mode || "bypassPermissions").trim();
      if (!looksLikeSessionId(sid) || !normalized) return false;
      try {
        const r = await fetch("/api/sessions/" + encodeURIComponent(sid), {
          method: "PUT",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            claude_permission_mode: normalized,
            permission_mode: normalized,
          }),
        });
        if (!r || !r.ok) return false;
        const payload = await r.json().catch(() => null);
        const session = payload && typeof payload === "object" && payload.session && typeof payload.session === "object"
          ? payload.session
          : payload;
        const echoed = session && typeof session === "object"
          ? firstNonEmptyText([
            session.claude_permission_mode,
            session.claudePermissionMode,
            session.permission_mode,
            session.permissionMode,
          ])
          : "";
        const confirmed = typeof normalizeClaudePermissionMode === "function"
          ? normalizeClaudePermissionMode(echoed)
          : String(echoed || "bypassPermissions").trim();
        return confirmed === normalized;
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
      const s = (session && typeof session === "object") ? session : {};
      if (s._state_sources && typeof s._state_sources === "object") return !!sources.runtime_state;
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
      const hasSourceMeta = !!(session && typeof session === "object" && session._state_sources && typeof session._state_sources === "object");
      if (hasSourceMeta) return !!sources.session_display_state;
      if (sources.session_display_state) return true;
      const s = (session && typeof session === "object") ? session : {};
      const value = normalizeDisplayState(firstNonEmptyText([s.session_display_state, s.sessionDisplayState]) || "", "");
      return !!(value && value !== "idle");
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

    function preserveConversationActiveSessionStateFields(nextSession, previousSession) {
      const next = (nextSession && typeof nextSession === "object") ? nextSession : {};
      const prev = (previousSession && typeof previousSession === "object") ? previousSession : {};
      if (!conversationShouldPreserveActiveSessionState(next, prev)) return nextSession;
      const prevRuntime = getSessionRuntimeState(prev);
      const displayState = normalizeDisplayState(
        firstNonEmptyText([
          prev.session_display_state,
          prev.sessionDisplayState,
          prevRuntime.display_state,
          prev.lastStatus,
        ]) || "idle",
        "idle"
      );
      const latestRunSummary = prev.latest_run_summary || prev.latestRunSummary || next.latest_run_summary || next.latestRunSummary || null;
      const latestEffectiveRunSummary = prev.latest_effective_run_summary || prev.latestEffectiveRunSummary || next.latest_effective_run_summary || next.latestEffectiveRunSummary || null;
      const preserved = {
        ...next,
        runtime_state: prevRuntime,
        session_display_state: displayState,
        session_display_reason: String(firstNonEmptyText([
          prev.session_display_reason,
          prev.sessionDisplayReason,
          next.session_display_reason,
          next.sessionDisplayReason,
        ]) || ""),
        latest_run_summary: latestRunSummary,
        lastStatus: displayState,
        lastPreview: String(firstNonEmptyText([
          latestEffectiveRunSummary && latestEffectiveRunSummary.preview,
          latestRunSummary && latestRunSummary.preview,
          prev.lastPreview,
          next.lastPreview,
        ]) || ""),
        lastError: String(firstNonEmptyText([prev.lastError, prev.last_error, next.lastError, next.last_error]) || ""),
        lastErrorHint: String(firstNonEmptyText([prev.lastErrorHint, prev.last_error_hint, next.lastErrorHint, next.last_error_hint]) || ""),
        lastActiveAt: String(firstNonEmptyText([prev.lastActiveAt, prev.last_used_at, next.lastActiveAt, next.last_used_at]) || ""),
        _state_sources: {
          ...conversationSessionStateSources(next),
          runtime_state: true,
          session_display_state: true,
          latest_run_summary: !!latestRunSummary,
          latest_effective_run_summary: !!latestEffectiveRunSummary,
        },
      };
      if (latestEffectiveRunSummary) preserved.latest_effective_run_summary = latestEffectiveRunSummary;
      return preserved;
    }

    function conversationRunStatusForRuntimeOverlay(run) {
      const row = (run && typeof run === "object") ? run : {};
      return normalizeDisplayState(firstNonEmptyText([
        row.display_state,
        row.displayState,
        row.status,
      ]) || "", "idle");
    }

    function conversationRunIdForRuntimeOverlay(run) {
      const row = (run && typeof run === "object") ? run : {};
      return String(firstNonEmptyText([row.id, row.runId, row.run_id]) || "").trim();
    }

    function conversationRunIsTerminalForRuntimeOverlay(run) {
      const row = (run && typeof run === "object") ? run : {};
      const raw = String(firstNonEmptyText([
        row.display_state,
        row.displayState,
        row.status,
        row.state,
      ]) || "").trim().toLowerCase();
      return raw === "done" || raw === "error" || raw === "interrupted";
    }

    function conversationRunSessionIdForRuntimeOverlay(run) {
      const row = (run && typeof run === "object") ? run : {};
      return String(firstNonEmptyText([row.sessionId, row.session_id]) || "").trim();
    }

    function conversationRunUpdatedAtForRuntimeOverlay(run) {
      const row = (run && typeof run === "object") ? run : {};
      return String(firstNonEmptyText([
        row.updatedAt,
        row.updated_at,
        row.lastProgressAt,
        row.last_progress_at,
        row.startedAt,
        row.started_at,
        row.createdAt,
        row.created_at,
      ]) || "").trim();
    }

    function conversationRunTimeForRuntimeOverlay(run) {
      const text = conversationRunUpdatedAtForRuntimeOverlay(run);
      if (!text) return -1;
      const normalized = text.replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
      const parsed = Date.parse(normalized);
      return Number.isFinite(parsed) ? parsed : -1;
    }

    function conversationLatestRunBySessionFromRuns(runs) {
      const map = new Map();
      const list = Array.isArray(runs) ? runs : [];
      list.forEach((run) => {
        const sid = conversationRunSessionIdForRuntimeOverlay(run);
        if (!sid) return;
        const time = conversationRunTimeForRuntimeOverlay(run);
        const prev = map.get(sid);
        if (!prev || time >= prev.time) {
          map.set(sid, { run, time });
        }
      });
      return map;
    }

    function conversationRuntimeOverlayBySessionFromRuns(runs) {
      const map = new Map();
      const list = Array.isArray(runs) ? runs : [];
      list.forEach((run) => {
        const sid = conversationRunSessionIdForRuntimeOverlay(run);
        if (!sid) return;
        const status = conversationRunStatusForRuntimeOverlay(run);
        const activeLike = status === "running" || status === "retry_waiting" || status === "external_busy";
        const queuedLike = status === "queued";
        if (!activeLike && !queuedLike) return;
        let entry = map.get(sid);
        if (!entry) {
          entry = {
            activeRun: null,
            activeTime: -1,
            queuedRun: null,
            queuedTime: -1,
            queueDepth: 0,
            updatedAt: "",
            updatedTime: -1,
          };
          map.set(sid, entry);
        }
        const time = conversationRunTimeForRuntimeOverlay(run);
        if (time > entry.updatedTime) {
          entry.updatedTime = time;
          entry.updatedAt = conversationRunUpdatedAtForRuntimeOverlay(run);
        }
        if (activeLike && time >= entry.activeTime) {
          entry.activeRun = run;
          entry.activeTime = time;
        }
        if (queuedLike) {
          entry.queueDepth += 1;
          if (time >= entry.queuedTime) {
            entry.queuedRun = run;
            entry.queuedTime = time;
          }
        }
      });
      return map;
    }

    function conversationRuntimeOverlayStateFromEntry(entry) {
      const src = (entry && typeof entry === "object") ? entry : {};
      const activeRun = src.activeRun || null;
      const queuedRun = src.queuedRun || null;
      const activeStatus = conversationRunStatusForRuntimeOverlay(activeRun);
      const queuedStatus = conversationRunStatusForRuntimeOverlay(queuedRun);
      const displayState = activeRun ? activeStatus : (queuedRun ? queuedStatus : "idle");
      const latestRun = activeRun || queuedRun || null;
      return {
        runtime_state: {
          internal_state: displayState,
          external_busy: displayState === "external_busy",
          display_state: displayState,
          active_run_id: activeRun ? conversationRunIdForRuntimeOverlay(activeRun) : "",
          queued_run_id: queuedRun ? conversationRunIdForRuntimeOverlay(queuedRun) : "",
          queue_depth: Math.max(0, Number(src.queueDepth || 0) || 0),
          updated_at: String(src.updatedAt || conversationRunUpdatedAtForRuntimeOverlay(latestRun) || ""),
        },
        latest_run_summary: {
          run_id: latestRun ? conversationRunIdForRuntimeOverlay(latestRun) : "",
          status: displayState,
          updated_at: String(conversationRunUpdatedAtForRuntimeOverlay(latestRun) || src.updatedAt || ""),
          preview: String(firstNonEmptyText([
            latestRun && latestRun.lastPreview,
            latestRun && latestRun.partialPreview,
            latestRun && latestRun.messagePreview,
            latestRun && latestRun.preview,
          ]) || ""),
          speaker: "assistant",
          sender_type: String(firstNonEmptyText([latestRun && latestRun.sender_type, latestRun && latestRun.senderType]) || ""),
          sender_name: String(firstNonEmptyText([latestRun && latestRun.sender_name, latestRun && latestRun.senderName]) || ""),
          sender_source: String(firstNonEmptyText([latestRun && latestRun.sender_source, latestRun && latestRun.senderSource]) || ""),
        },
        display_state: displayState,
      };
    }

    function conversationShouldClearRuntimeOverlayFromRun(session, run) {
      if (!session || typeof session !== "object" || !run || typeof run !== "object") return false;
      if (!conversationRunIsTerminalForRuntimeOverlay(run)) return false;
      const runtimeState = getSessionRuntimeState(session);
      const currentRunIds = new Set([
        String(runtimeState.active_run_id || "").trim(),
        String(runtimeState.queued_run_id || "").trim(),
      ].filter(Boolean));
      if (!currentRunIds.size) return false;
      const runId = conversationRunIdForRuntimeOverlay(run);
      return !!(runId && currentRunIds.has(runId));
    }

    function conversationClearedRuntimeOverlayStateFromRun(session, run) {
      const s = (session && typeof session === "object") ? session : {};
      const prevSources = conversationSessionStateSources(s);
      const status = conversationRunStatusForRuntimeOverlay(run);
      const updatedAt = String(conversationRunUpdatedAtForRuntimeOverlay(run) || "");
      const runId = conversationRunIdForRuntimeOverlay(run);
      const latestRunSummary = {
        run_id: runId,
        status,
        updated_at: updatedAt,
        preview: String(firstNonEmptyText([
          run && run.lastPreview,
          run && run.partialPreview,
          run && run.messagePreview,
          run && run.preview,
        ]) || ""),
        speaker: "assistant",
        sender_type: String(firstNonEmptyText([run && run.sender_type, run && run.senderType]) || ""),
        sender_name: String(firstNonEmptyText([run && run.sender_name, run && run.senderName]) || ""),
        sender_source: String(firstNonEmptyText([run && run.sender_source, run && run.senderSource]) || ""),
      };
      return {
        ...s,
        runtime_state: {
          internal_state: "idle",
          external_busy: false,
          display_state: "idle",
          active_run_id: "",
          queued_run_id: "",
          queue_depth: 0,
          updated_at: updatedAt,
        },
        session_display_state: "idle",
        session_display_reason: "runs_overlay_terminal",
        latest_run_summary: latestRunSummary,
        lastStatus: "idle",
        lastPreview: String(firstNonEmptyText([
          latestRunSummary.preview,
          s.lastPreview,
        ]) || ""),
        lastActiveAt: String(firstNonEmptyText([
          updatedAt,
          s.lastActiveAt,
          s.last_used_at,
        ]) || ""),
        _state_sources: {
          ...prevSources,
          runtime_state: true,
          session_display_state: true,
          latest_run_summary: true,
        },
      };
    }

    function applyConversationRuntimeOverlayFromRuns(sessions, runs) {
      const list = Array.isArray(sessions) ? sessions : [];
      const overlayBySession = conversationRuntimeOverlayBySessionFromRuns(runs);
      const latestRunBySession = conversationLatestRunBySessionFromRuns(runs);
      if (!overlayBySession.size && !latestRunBySession.size) return list;
      return list.map((session) => {
        const s = (session && typeof session === "object") ? session : {};
        const sid = String(firstNonEmptyText([s.sessionId, s.id, s.session_id]) || "").trim();
        const entry = sid ? overlayBySession.get(sid) : null;
        if (!entry) {
          const latest = sid ? latestRunBySession.get(sid) : null;
          const latestRun = latest && latest.run ? latest.run : null;
          if (conversationShouldClearRuntimeOverlayFromRun(s, latestRun)) {
            return conversationClearedRuntimeOverlayStateFromRun(s, latestRun);
          }
          return session;
        }
        const overlay = conversationRuntimeOverlayStateFromEntry(entry);
        if (!isConversationActiveDisplayState(overlay.display_state)) return session;
        const prevSources = conversationSessionStateSources(s);
        const latestRunSummary = overlay.latest_run_summary || s.latest_run_summary || s.latestRunSummary || null;
        return {
          ...s,
          runtime_state: overlay.runtime_state,
          session_display_state: overlay.display_state,
          session_display_reason: String(firstNonEmptyText([s.session_display_reason, s.sessionDisplayReason, "runs_overlay"]) || "runs_overlay"),
          latest_run_summary: latestRunSummary,
          lastStatus: overlay.display_state,
          lastPreview: String(firstNonEmptyText([
            latestRunSummary && latestRunSummary.preview,
            s.lastPreview,
          ]) || ""),
          lastActiveAt: String(firstNonEmptyText([
            overlay.runtime_state.updated_at,
            s.lastActiveAt,
            s.last_used_at,
          ]) || ""),
          _state_sources: {
            ...prevSources,
            runtime_state: true,
            session_display_state: true,
            latest_run_summary: !!latestRunSummary,
          },
        };
      });
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

    const CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS = 12000;
    const CONVERSATION_SESSIONS_FRESHNESS_FLOOR_MS = 8000;

    function hasConversationOwnOption(opts, key) {
      return !!(opts && Object.prototype.hasOwnProperty.call(opts, key));
    }

    function normalizeConversationVisiblePollIntervalMs(raw, fallback = CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS) {
      return Math.min(
        normalizeConversationPollingNumber(raw, fallback),
        CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS
      );
    }

    function defaultConversationSessionsPollingHints() {
      return {
        enabled: true,
        cache_ttl_ms: 4000,
        inflight_wait_ms: 8000,
        poll_interval_ms: CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS,
        hidden_poll_interval_ms: CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS,
        backoff_step_ms: 2000,
        backoff_max_ms: 15000,
        pause_when_hidden: false,
        cross_tab_dedupe_enabled: false,
      };
    }

    function normalizeConversationSessionsPollingHints(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const fallback = defaultConversationSessionsPollingHints();
      return {
        enabled: Object.prototype.hasOwnProperty.call(src, "enabled") ? !!src.enabled : fallback.enabled,
        cache_ttl_ms: normalizeConversationPollingNumber(src.cache_ttl_ms ?? src.cacheTtlMs, fallback.cache_ttl_ms),
        inflight_wait_ms: normalizeConversationPollingNumber(src.inflight_wait_ms ?? src.inflightWaitMs, fallback.inflight_wait_ms),
        poll_interval_ms: normalizeConversationVisiblePollIntervalMs(src.poll_interval_ms ?? src.pollIntervalMs, fallback.poll_interval_ms),
        hidden_poll_interval_ms: normalizeConversationPollingNumber(src.hidden_poll_interval_ms ?? src.hiddenPollIntervalMs, fallback.hidden_poll_interval_ms),
        backoff_step_ms: normalizeConversationPollingNumber(src.backoff_step_ms ?? src.backoffStepMs, fallback.backoff_step_ms),
        backoff_max_ms: normalizeConversationPollingNumber(src.backoff_max_ms ?? src.backoffMaxMs, fallback.backoff_max_ms),
        pause_when_hidden: Object.prototype.hasOwnProperty.call(src, "pause_when_hidden") || Object.prototype.hasOwnProperty.call(src, "pauseWhenHidden")
          ? !!(src.pause_when_hidden ?? src.pauseWhenHidden)
          : fallback.pause_when_hidden,
        cross_tab_dedupe_enabled: Object.prototype.hasOwnProperty.call(src, "cross_tab_dedupe_enabled") || Object.prototype.hasOwnProperty.call(src, "crossTabDedupeEnabled")
          ? !!(src.cross_tab_dedupe_enabled ?? src.crossTabDedupeEnabled)
          : fallback.cross_tab_dedupe_enabled,
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
      const readModel = (src.sessions_read_model && typeof src.sessions_read_model === "object")
        ? src.sessions_read_model
        : ((src.sessionsReadModel && typeof src.sessionsReadModel === "object") ? src.sessionsReadModel : null);
      const readModelSessionsRaw = readModel ? {
        enabled: true,
        cache_ttl_ms: readModel.cache_ttl_ms ?? readModel.cacheTtlMs,
        inflight_wait_ms: readModel.inflight_wait_ms ?? readModel.inflightWaitMs,
        hidden_poll_interval_ms: readModel.hidden_poll_interval_ms ?? readModel.hiddenPollIntervalMs ?? CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS,
        pause_when_hidden: false,
        cross_tab_dedupe_enabled: false,
      } : null;
      const current = (PCONV.pollingMetaByProject && PCONV.pollingMetaByProject[pid]) || {};
      const nextSessions = sessionsRaw
        ? normalizeConversationSessionsPollingHints(sessionsRaw)
        : (readModelSessionsRaw ? normalizeConversationSessionsPollingHints(readModelSessionsRaw) : (current.sessions || null));
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
      return meta && meta.sessions ? meta.sessions : defaultConversationSessionsPollingHints();
    }

    function normalizeConversationSessionsPayloadMode(raw) {
      const text = String(raw || "").trim().toLowerCase();
      if (text === "full" || text === "summary" || text === "light") return text;
      return "summary";
    }

    function shouldForceConversationSessionDirectoryLiveFetch(projectId, channelName = "", opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return false;
      if (opts && opts.force) return true;
      const channel = String(channelName || "").trim();
      if (channel) return false;
      return false;
    }

    function conversationProjectPollingCadenceMs(projectId, channelName = "", opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return 0;
      const visibleTargetMs = typeof CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS !== "undefined"
        ? CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS
        : 12000;
      const normalizeNumber = typeof normalizeConversationPollingNumber === "function"
        ? normalizeConversationPollingNumber
        : ((raw, fallback = 0) => {
          const num = Number(raw);
          if (!Number.isFinite(num)) return Math.max(0, Number(fallback) || 0);
          return Math.max(0, Math.round(num));
        });
      const normalizeVisibleInterval = typeof normalizeConversationVisiblePollIntervalMs === "function"
        ? normalizeConversationVisiblePollIntervalMs
        : ((raw, fallback = visibleTargetMs) => Math.min(normalizeNumber(raw, fallback), visibleTargetMs));
      const policy = typeof conversationProjectPollingHints === "function"
        ? conversationProjectPollingHints(pid)
        : null;
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      if (policy && policy.enabled) {
        if (source === "poll" || source === "resume" || !String(channelName || "").trim()) {
          return normalizeVisibleInterval(policy.poll_interval_ms, visibleTargetMs);
        }
      }
      return normalizeNumber((opts && opts.freshnessMs) || 0, 0);
    }

    function resolveConversationSessionsFreshnessMs(projectId, channelName = "", opts = {}) {
      if (shouldForceConversationSessionDirectoryLiveFetch(projectId, channelName, opts)) return 0;
      const freshnessFloorMs = typeof CONVERSATION_SESSIONS_FRESHNESS_FLOOR_MS !== "undefined"
        ? CONVERSATION_SESSIONS_FRESHNESS_FLOOR_MS
        : 8000;
      const visibleTargetMs = typeof CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS !== "undefined"
        ? CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS
        : 12000;
      const rawFreshnessMs = Number(opts && opts.freshnessMs);
      const hasOwnOption = typeof hasConversationOwnOption === "function"
        ? hasConversationOwnOption
        : ((source, key) => !!(source && Object.prototype.hasOwnProperty.call(source, key)));
      const normalizeNumber = typeof normalizeConversationPollingNumber === "function"
        ? normalizeConversationPollingNumber
        : ((raw, fallback = 0) => {
          const num = Number(raw);
          if (!Number.isFinite(num)) return Math.max(0, Number(fallback) || 0);
          return Math.max(0, Math.round(num));
        });
      const hasFreshnessOverride = hasOwnOption(opts, "freshnessMs")
        && Number.isFinite(rawFreshnessMs)
        && rawFreshnessMs >= 0;
      const freshnessMs = hasFreshnessOverride
        ? normalizeNumber(rawFreshnessMs, 0)
        : freshnessFloorMs;
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      if ((source === "poll" || source === "resume") && !String(channelName || "").trim()) {
        return Math.max(freshnessMs, 18000, freshnessFloorMs);
      }
      const cadenceMs = conversationProjectPollingCadenceMs(projectId, channelName, opts);
      return hasFreshnessOverride ? freshnessMs : Math.max(freshnessMs, Math.min(cadenceMs, visibleTargetMs));
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
      if (!PCONV.sessionDetailDeferredTimerById || typeof PCONV.sessionDetailDeferredTimerById !== "object") {
        PCONV.sessionDetailDeferredTimerById = Object.create(null);
      }
      if (!PCONV.sessionDetailDeferredReasonById || typeof PCONV.sessionDetailDeferredReasonById !== "object") {
        PCONV.sessionDetailDeferredReasonById = Object.create(null);
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

    function conversationSessionHasDetailPayload(session) {
      const row = (session && typeof session === "object") ? session : {};
      return !!(
        hasConversationTaskTrackingData(row.task_tracking)
        || row.project_execution_context
        || row.projectExecutionContext
      );
    }

    function conversationSessionDetailLoadedRecently(sessionId, maxAgeMs = 0) {
      const sid = String(sessionId || "").trim();
      if (!sid) return false;
      ensureConversationSessionDetailStateMaps();
      const loadedAt = Number(PCONV.sessionDetailLoadedAtById[sid] || 0);
      if (!loadedAt) return false;
      const ttl = Math.max(0, Number(maxAgeMs || 0) || 0);
      return !ttl || (Date.now() - loadedAt) < ttl;
    }

    function conversationSessionDetailHydrationStatus(sessionId, session = null) {
      const sid = String(sessionId || "").trim();
      if (!sid) return { state: "idle", label: "", message: "", canRetry: false };
      ensureConversationSessionDetailStateMaps();
      if (isConversationSessionDetailLoading(sid)) {
        return {
          state: "loading",
          label: "状态更新中",
          message: "后台补全中：完整历史、上下文、任务跟踪和高级配置正在异步读取，不影响发送。",
          canRetry: false,
        };
      }
      const errorText = getConversationSessionDetailError(sid);
      if (errorText) {
        return {
          state: "error",
          label: "状态可能延迟",
          message: "高级状态读取失败；列表和发送入口仍可用。",
          errorText,
          canRetry: true,
        };
      }
      if (conversationSessionDetailLoadedRecently(sid, 60_000) || conversationSessionHasDetailPayload(session)) {
        return { state: "ready", label: "", message: "", canRetry: false };
      }
      if (PCONV.sessionDetailDeferredTimerById && PCONV.sessionDetailDeferredTimerById[sid]) {
        return {
          state: "deferred",
          label: "状态可能延迟",
          message: "后台补全中：当前先使用最近已知状态，完整状态稍后自动补齐。",
          canRetry: true,
        };
      }
      return {
        state: "stale",
        label: "状态可能延迟",
        message: "当前先使用最近已知状态；可点击重试状态读取完整详情。",
        canRetry: true,
      };
    }

    function mergeConversationSessionDetailIntoStore(detail, sessionId = "") {
      const base = (detail && typeof detail === "object") ? detail : {};
      const sid = String(firstNonEmptyText([sessionId, base.sessionId, base.id]) || "").trim();
      if (!sid) return null;
      const prev = typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const projectId = String(firstNonEmptyText([
        base.project_id,
        base.projectId,
        prev && prev.project_id,
        prev && prev.projectId,
        STATE && STATE.project,
      ]) || "").trim();
      let merged = normalizeConversationSession({
        ...(prev || {}),
        id: sid,
        sessionId: sid,
        project_id: projectId,
        projectId,
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
        model: typeof mergeConversationSessionModelValue === "function"
          ? mergeConversationSessionModelValue(base, prev)
          : normalizeSessionModel(firstNonEmptyText([base.model, prev && prev.model])),
        codebuddy_permission_mode: typeof mergeConversationSessionPermissionModeValue === "function"
          ? mergeConversationSessionPermissionModeValue(base, prev)
          : firstNonEmptyText([base.codebuddy_permission_mode, base.codebuddyPermissionMode, prev && prev.codebuddy_permission_mode, prev && prev.codebuddyPermissionMode], "default"),
        codebuddyPermissionMode: typeof mergeConversationSessionPermissionModeValue === "function"
          ? mergeConversationSessionPermissionModeValue(base, prev)
          : firstNonEmptyText([base.codebuddy_permission_mode, base.codebuddyPermissionMode, prev && prev.codebuddy_permission_mode, prev && prev.codebuddyPermissionMode], "default"),
        reasoning_effort: normalizeReasoningEffort(firstNonEmptyText([base.reasoning_effort, prev && prev.reasoning_effort])),
        status: firstNonEmptyText([base.status, prev && prev.status], "active"),
        created_at: firstNonEmptyText([base.created_at, prev && prev.created_at]),
        last_used_at: firstNonEmptyText([base.last_used_at, prev && prev.last_used_at]),
        is_primary: Object.prototype.hasOwnProperty.call(base, "is_primary")
          ? !!base.is_primary
          : !!(prev && prev.is_primary),
        source: firstNonEmptyText([base.source, prev && prev.source]),
        session_display_state: firstNonEmptyText([base.session_display_state, base.sessionDisplayState, prev && prev.session_display_state, prev && prev.sessionDisplayState]),
        session_display_reason: firstNonEmptyText([base.session_display_reason, base.sessionDisplayReason, prev && prev.session_display_reason, prev && prev.sessionDisplayReason]),
        runtime_state: base.runtime_state || (prev && prev.runtime_state) || null,
        latest_run_summary: base.latest_run_summary || base.latestRunSummary || (prev && (prev.latest_run_summary || prev.latestRunSummary)) || null,
        latest_effective_run_summary: base.latest_effective_run_summary || base.latestEffectiveRunSummary || (prev && (prev.latest_effective_run_summary || prev.latestEffectiveRunSummary)) || null,
        heartbeat_summary: base.heartbeat_summary || (prev && prev.heartbeat_summary) || null,
        project_execution_context: base.project_execution_context || (prev && prev.project_execution_context) || null,
        task_tracking: hasConversationTaskTrackingData(base.task_tracking)
          ? base.task_tracking
          : (prev && prev.task_tracking),
        conversation_list_metrics: base.conversation_list_metrics || base.conversationListMetrics || (prev && (prev.conversation_list_metrics || prev.conversationListMetrics)) || null,
        memo_summary: base.memo_summary || base.memoSummary || (prev && (prev.memo_summary || prev.memoSummary)) || null,
      });
      if (!merged) return null;
      const upsertSessionRow = (list) => {
        const rows = Array.isArray(list) ? list.slice() : [];
        for (let i = 0; i < rows.length; i += 1) {
          if (String(getSessionId(rows[i]) || "").trim() !== sid) continue;
          const nextRow = preserveConversationSessionDetailFields(merged, rows[i]) || merged;
          rows[i] = nextRow;
          return { rows, merged: nextRow };
        }
        rows.push(merged);
        return { rows, merged };
      };
      const sessionResult = upsertSessionRow(PCONV.sessions);
      PCONV.sessions = sessionResult.rows;
      merged = sessionResult.merged;
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
            if (typeof buildConversationMainList === "function" && typeof document !== "undefined") {
              buildConversationMainList(document.getElementById("fileList"));
            }
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

    function clearConversationSessionDetailHydrationTimer(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return;
      ensureConversationSessionDetailStateMaps();
      const timer = PCONV.sessionDetailDeferredTimerById[sid];
      if (timer) {
        clearTimeout(timer);
        delete PCONV.sessionDetailDeferredTimerById[sid];
      }
      delete PCONV.sessionDetailDeferredReasonById[sid];
    }

    async function requestConversationSessionDetailHydration(sessionId, opts = {}) {
      const sid = String(sessionId || "").trim();
      if (!looksLikeSessionId(sid)) return null;
      clearConversationSessionDetailHydrationTimer(sid);
      ensureConversationSessionDetailStateMaps();
      return ensureConversationSessionDetailLoaded(sid, {
        ...(opts || {}),
        force: !!(opts && opts.force),
      });
    }

    function scheduleConversationSessionDetailHydration(sessionId, opts = {}) {
      const sid = String(sessionId || "").trim();
      if (!looksLikeSessionId(sid)) return false;
      ensureConversationSessionDetailStateMaps();
      const maxAgeMs = Math.max(0, Number((opts && opts.maxAgeMs) || 0) || 0);
      if (conversationSessionDetailLoadedRecently(sid, maxAgeMs)) return false;
      if (PCONV.sessionDetailPromiseById[sid]) return false;
      if (PCONV.sessionDetailDeferredTimerById[sid]) return false;
      const delayMs = Math.max(0, Number((opts && opts.delayMs) || 0) || 0);
      PCONV.sessionDetailDeferredReasonById[sid] = String((opts && opts.reason) || "background");
      PCONV.sessionDetailDeferredTimerById[sid] = setTimeout(() => {
        delete PCONV.sessionDetailDeferredTimerById[sid];
        delete PCONV.sessionDetailDeferredReasonById[sid];
        requestConversationSessionDetailHydration(sid, {
          maxAgeMs,
          force: false,
          reason: String((opts && opts.reason) || "background"),
        }).catch(() => {});
      }, delayMs);
      return true;
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
        const stateSources = {
          runtime_state: !!(s.runtime_state || s.runtimeState),
          session_display_state: Object.prototype.hasOwnProperty.call(s, "session_display_state")
            || Object.prototype.hasOwnProperty.call(s, "sessionDisplayState"),
          latest_run_summary: !!(s.latest_run_summary || s.latestRunSummary),
          latest_effective_run_summary: !!(s.latest_effective_run_summary || s.latestEffectiveRunSummary),
          communication_status_summary: !!(s.communication_status_summary || s.communicationStatusSummary),
        };
        const presentation = resolveConversationSessionPresentation(s, channelName, sid);
        const runtimeState = normalizeRuntimeState(s.runtime_state || s.runtimeState || null);
        const latestRunSummary = normalizeLatestRunSummary(s.latest_run_summary || s.latestRunSummary || null);
        const latestEffectiveRunSummary = normalizeLatestEffectiveRunSummary(
          s.latest_effective_run_summary || s.latestEffectiveRunSummary || null
        );
        const communicationStatusSummary = normalizeCommunicationStatusSummaryClient(
          s.communication_status_summary || s.communicationStatusSummary || null
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
        const permissionModePresent = Object.prototype.hasOwnProperty.call(s, "codebuddy_permission_mode")
          || Object.prototype.hasOwnProperty.call(s, "codebuddyPermissionMode");
        const claudePermissionModePresent = Object.prototype.hasOwnProperty.call(s, "claude_permission_mode")
          || Object.prototype.hasOwnProperty.call(s, "claudePermissionMode")
          || Object.prototype.hasOwnProperty.call(s, "permission_mode")
          || Object.prototype.hasOwnProperty.call(s, "permissionMode");
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
          codebuddy_permission_mode: typeof normalizeCodeBuddyPermissionMode === "function"
            ? normalizeCodeBuddyPermissionMode(permissionModePresent ? (s.codebuddy_permission_mode || s.codebuddyPermissionMode) : "")
            : String((permissionModePresent ? (s.codebuddy_permission_mode || s.codebuddyPermissionMode) : "") || "default"),
          codebuddyPermissionMode: typeof normalizeCodeBuddyPermissionMode === "function"
            ? normalizeCodeBuddyPermissionMode(permissionModePresent ? (s.codebuddy_permission_mode || s.codebuddyPermissionMode) : "")
            : String((permissionModePresent ? (s.codebuddy_permission_mode || s.codebuddyPermissionMode) : "") || "default"),
          _codebuddy_permission_mode_present: permissionModePresent,
          claude_permission_mode: claudePermissionModePresent && typeof normalizeClaudePermissionMode === "function"
            ? normalizeClaudePermissionMode(firstNonEmptyText([s.claude_permission_mode, s.claudePermissionMode, s.permission_mode, s.permissionMode]))
            : (claudePermissionModePresent ? String(firstNonEmptyText([s.claude_permission_mode, s.claudePermissionMode, s.permission_mode, s.permissionMode]) || "bypassPermissions") : ""),
          claudePermissionMode: claudePermissionModePresent && typeof normalizeClaudePermissionMode === "function"
            ? normalizeClaudePermissionMode(firstNonEmptyText([s.claude_permission_mode, s.claudePermissionMode, s.permission_mode, s.permissionMode]))
            : (claudePermissionModePresent ? String(firstNonEmptyText([s.claude_permission_mode, s.claudePermissionMode, s.permission_mode, s.permissionMode]) || "bypassPermissions") : ""),
          _claude_permission_mode_present: claudePermissionModePresent,
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
          communication_status_summary: communicationStatusSummary,
          runtime_state: runtimeState,
          heartbeat_summary: heartbeatSummary,
          task_tracking: normalizeTaskTrackingClient(s.task_tracking || s.taskTracking || null),
          _state_sources: stateSources,
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
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      const force = !!(opts && opts.force);
      const freshnessMs = resolveConversationSessionsFreshnessMs(pid, channelName, {
        ...(opts || {}),
        source,
      });
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
      const policy = typeof conversationProjectPollingHints === "function"
        ? conversationProjectPollingHints(pid)
        : null;
      const snapshotMaxAgeMs = Math.max(
        normalizeConversationPollingNumber(policy && policy.cache_ttl_ms, 0),
        normalizeConversationPollingNumber(freshnessMs, 0),
        4000
      );
      const useLeader = typeof shouldUseSessionDirectoryLeader === "function"
        ? shouldUseSessionDirectoryLeader(pid, channelName, opts)
        : false;
      if (!force && useLeader && typeof readSessionDirectorySnapshot === "function") {
        const freshSnapshot = readSessionDirectorySnapshot(pid, channelName, { maxAgeMs: snapshotMaxAgeMs });
        if (freshSnapshot && Array.isArray(freshSnapshot.sessions)) {
          if (freshSnapshot.pollingHints || freshSnapshot.perfGovernance) {
            updateConversationProjectPollingMeta(pid, {
              polling_hints: freshSnapshot.pollingHints,
              perf_governance: freshSnapshot.perfGovernance,
            });
          }
          PCONV.sessionFetchCacheByKey[key] = {
            loadedAt: Number(freshSnapshot.loadedAtMs || Date.now()) || Date.now(),
            sessions: freshSnapshot.sessions.slice(),
            source: "storage-snapshot",
          };
          return freshSnapshot.sessions.slice();
        }
        const leader = (typeof tryAcquireSessionDirectoryPollLeader === "function")
          ? tryAcquireSessionDirectoryPollLeader(pid)
          : { isLeader: true };
        if (!leader || !leader.isLeader) {
          if (cached && Array.isArray(cached.sessions)) return cached.sessions.slice();
          const waitMs = Math.min(Math.max(normalizeConversationPollingNumber(policy && policy.inflight_wait_ms, 250), 250), 1200);
          await new Promise((resolve) => setTimeout(resolve, waitMs));
          const lateSnapshot = readSessionDirectorySnapshot(pid, channelName, { maxAgeMs: snapshotMaxAgeMs });
          if (lateSnapshot && Array.isArray(lateSnapshot.sessions)) return lateSnapshot.sessions.slice();
          const staleSnapshot = readSessionDirectorySnapshot(pid, channelName, {
            maxAgeMs: Math.max(snapshotMaxAgeMs, normalizeConversationPollingNumber(policy && policy.poll_interval_ms, 45000) * 2),
          });
          if (staleSnapshot && Array.isArray(staleSnapshot.sessions)) return staleSnapshot.sessions.slice();
        }
      }
      const qs = new URLSearchParams();
      qs.set("project_id", pid);
      if (channelName) qs.set("channel_name", String(channelName));
      const payloadMode = normalizeConversationSessionsPayloadMode(opts && (opts.payloadMode || opts.payload_mode || opts.queryMode || opts.query_mode));
      qs.set("payloadMode", payloadMode);
      const allowStale = hasConversationOwnOption(opts, "allowStale")
        ? !!opts.allowStale
        : (hasConversationOwnOption(opts, "allow_stale") ? !!opts.allow_stale : payloadMode === "summary" || payloadMode === "light");
      if (allowStale && (payloadMode === "summary" || payloadMode === "light")) qs.set("allow_stale", "1");
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
        if (useLeader && typeof publishSessionDirectorySnapshot === "function") {
          publishSessionDirectorySnapshot(pid, channelName, sessions, {
            loadedAtMs: Date.now(),
            pollingHints: (j && (j.polling_hints || j.pollingHints)) || null,
            perfGovernance: (j && (j.perf_governance || j.perfGovernance)) || null,
          });
        }
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
          const existingById = new Map();
          existing.forEach((row) => {
            const normalized = normalizeConversationSession(row);
            if (!normalized) return;
            existingById.set(normalized.sessionId, normalized);
          });
          const serverSessions = (await fetchConversationSessionsFromApi(pid, "", { force }))
            .map((row) => preserveConversationSessionDetailFields(
              row,
              existingById.get(String((row && (row.sessionId || row.id || row.session_id)) || "").trim()) || null
            ))
            .filter(Boolean);
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
      const codeBuddyModelSelect = document.getElementById("newConvCodeBuddyModel");
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
      const codeBuddyModel = String((codeBuddyModelSelect && codeBuddyModelSelect.value) || "").trim();
      const model = String(cli || "").trim().toLowerCase() === "codebuddy"
        ? (codeBuddyModel || normalizeSessionModel(modelInput && modelInput.value) || "deepseek-v4-pro")
        : normalizeSessionModel(modelInput && modelInput.value);
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
            if (createBtn) createBtn.textContent = "发送中...";
            const bootstrapMode = /^\s*--bootstrap-message\s*$/i.test(initMessage);
            if (bootstrapMode) {
              const msgs = buildBootstrapVisibleMessages(ch);
              const sendA = await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, msgs[0], model);
              const sendB = sendA.ok
                ? await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, msgs[1], model)
                : { ok: false };
              if (sendA.ok && sendB.ok) {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "并发送两条标准首发消息。";
              } else {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "但标准首发消息发送不完整，请手动补发。";
              }
            } else {
              const sendRet = await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, initMessage, model);
              if (sendRet.ok) {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "并发送一次性启动消息。";
              } else {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 补登记并绑定，" : "已创建并绑定新对话，") + "但一次性启动消息发送失败，请手动发送。";
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
        const fetchOpts = {
          force: !!(opts && opts.force),
          source: String((opts && opts.source) || "").trim(),
          payloadMode: (opts && (opts.payloadMode || opts.payload_mode || opts.queryMode || opts.query_mode)) || "summary",
        };
        if (hasConversationOwnOption(opts, "freshnessMs")) {
          const explicitFreshnessMs = Number(opts && opts.freshnessMs);
          if (Number.isFinite(explicitFreshnessMs) && explicitFreshnessMs >= 0) {
            fetchOpts.freshnessMs = explicitFreshnessMs;
          }
        }
        const formatted = (await fetchConversationSessionsFromApi(projectId, channelName, fetchOpts))
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
      const rawStateSources = (raw._state_sources && typeof raw._state_sources === "object") ? raw._state_sources : null;
      const stateSources = rawStateSources ? {
        runtime_state: !!rawStateSources.runtime_state,
        session_display_state: !!rawStateSources.session_display_state,
        latest_run_summary: !!rawStateSources.latest_run_summary,
        latest_effective_run_summary: !!rawStateSources.latest_effective_run_summary,
      } : {
        runtime_state: !!(raw.runtime_state || raw.runtimeState),
        session_display_state: Object.prototype.hasOwnProperty.call(raw, "session_display_state")
          || Object.prototype.hasOwnProperty.call(raw, "sessionDisplayState"),
        latest_run_summary: !!(raw.latest_run_summary || raw.latestRunSummary),
        latest_effective_run_summary: !!(raw.latest_effective_run_summary || raw.latestEffectiveRunSummary),
      };
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
      const normalizedConversationListMetrics = typeof normalizeConversationListMetricsClient === "function"
        ? normalizeConversationListMetricsClient(raw.conversation_list_metrics || raw.conversationListMetrics || null)
        : (((raw.conversation_list_metrics || raw.conversationListMetrics) && typeof (raw.conversation_list_metrics || raw.conversationListMetrics) === "object")
          ? { ...(raw.conversation_list_metrics || raw.conversationListMetrics) }
          : null);
      const normalizedCommunicationStatusSummary = typeof normalizeCommunicationStatusSummaryClient === "function"
        ? normalizeCommunicationStatusSummaryClient(raw.communication_status_summary || raw.communicationStatusSummary || null)
        : (((raw.communication_status_summary || raw.communicationStatusSummary) && typeof (raw.communication_status_summary || raw.communicationStatusSummary) === "object")
          ? { ...(raw.communication_status_summary || raw.communicationStatusSummary) }
          : null);
      const memoSummary = (raw.memo_summary && typeof raw.memo_summary === "object")
        ? { ...raw.memo_summary }
        : ((raw.memoSummary && typeof raw.memoSummary === "object")
          ? { ...raw.memoSummary }
          : ((normalizedConversationListMetrics && normalizedConversationListMetrics.memo_summary && typeof normalizedConversationListMetrics.memo_summary === "object")
            ? { ...normalizedConversationListMetrics.memo_summary }
            : null));
      const hasCodeBuddyPermissionMode = typeof conversationSessionHasPermissionMode === "function"
        ? conversationSessionHasPermissionMode(raw)
        : (
          Object.prototype.hasOwnProperty.call(raw, "codebuddy_permission_mode")
          || Object.prototype.hasOwnProperty.call(raw, "codebuddyPermissionMode")
        );
      const rawCodeBuddyPermissionMode = hasCodeBuddyPermissionMode
        ? (raw.codebuddy_permission_mode || raw.codebuddyPermissionMode)
        : "";
      const normalizedCodeBuddyPermissionMode = typeof normalizeCodeBuddyPermissionMode === "function"
        ? normalizeCodeBuddyPermissionMode(rawCodeBuddyPermissionMode)
        : String(rawCodeBuddyPermissionMode || "default");
      const hasClaudePermissionMode = typeof conversationSessionHasClaudePermissionMode === "function"
        ? conversationSessionHasClaudePermissionMode(raw)
        : (
          Object.prototype.hasOwnProperty.call(raw, "claude_permission_mode")
          || Object.prototype.hasOwnProperty.call(raw, "claudePermissionMode")
          || Object.prototype.hasOwnProperty.call(raw, "permission_mode")
          || Object.prototype.hasOwnProperty.call(raw, "permissionMode")
        );
      const rawClaudePermissionMode = hasClaudePermissionMode
        ? firstNonEmptyText([raw.claude_permission_mode, raw.claudePermissionMode, raw.permission_mode, raw.permissionMode])
        : "";
      const normalizedClaudePermissionMode = hasClaudePermissionMode && typeof normalizeClaudePermissionMode === "function"
        ? normalizeClaudePermissionMode(rawClaudePermissionMode)
        : (hasClaudePermissionMode ? String(rawClaudePermissionMode || "bypassPermissions") : "");

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
        codebuddy_permission_mode: normalizedCodeBuddyPermissionMode,
        codebuddyPermissionMode: normalizedCodeBuddyPermissionMode,
        _codebuddy_permission_mode_present: hasCodeBuddyPermissionMode,
        codebuddy_permission_mode_source: firstNonEmptyText([raw.codebuddy_permission_mode_source, raw.codebuddyPermissionModeSource, raw.source]),
        claude_permission_mode: normalizedClaudePermissionMode,
        claudePermissionMode: normalizedClaudePermissionMode,
        _claude_permission_mode_present: hasClaudePermissionMode,
        claude_permission_mode_source: firstNonEmptyText([raw.claude_permission_mode_source, raw.claudePermissionModeSource, raw.source]),
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
        latest_effective_run_summary: normalizeLatestEffectiveRunSummary(raw.latest_effective_run_summary || raw.latestEffectiveRunSummary || null),
        communication_status_summary: normalizedCommunicationStatusSummary,
        runtime_state: normalizeRuntimeState(raw.runtime_state || raw.runtimeState || null),
        heartbeat_summary: heartbeatSummary,
        project_execution_context: normalizeProjectExecutionContext(
          raw.project_execution_context || raw.projectExecutionContext || null
        ),
        task_tracking: normalizeTaskTrackingClient(raw.task_tracking || raw.taskTracking || null),
        conversation_list_metrics: normalizedConversationListMetrics,
        memo_summary: memoSummary,
        memoSummary: memoSummary,
        _state_sources: stateSources,
      };
    }

    function codeBuddySessionDefaultModelValue() {
      if (typeof codeBuddyDefaultModel === "function") return normalizeSessionModel(codeBuddyDefaultModel());
      return "deepseek-v4-pro";
    }

    function codeBuddySessionDefaultPermissionModeValue() {
      if (typeof codeBuddyDefaultPermissionMode === "function") {
        return typeof normalizeCodeBuddyPermissionMode === "function"
          ? normalizeCodeBuddyPermissionMode(codeBuddyDefaultPermissionMode())
          : String(codeBuddyDefaultPermissionMode() || "default");
      }
      return "default";
    }

    function normalizeConversationCodeBuddyPermissionMode(raw) {
      if (typeof normalizeCodeBuddyPermissionMode === "function") return normalizeCodeBuddyPermissionMode(raw);
      return String(raw || "").trim() === "bypassPermissions" ? "bypassPermissions" : "default";
    }

    function conversationSessionModelMergeSource(row) {
      const src = (row && typeof row === "object") ? row : {};
      return String(src.source || src.model_source || src.modelSource || "").trim().toLowerCase();
    }

    function conversationSessionPermissionModeMergeSource(row) {
      const src = (row && typeof row === "object") ? row : {};
      return String(src.source || src.codebuddy_permission_mode_source || src.codebuddyPermissionModeSource || "").trim().toLowerCase();
    }

    function conversationSessionModelMergeCliType(next, prev) {
      return String(firstNonEmptyText([
        next && next.cli_type,
        next && next.cliType,
        prev && prev.cli_type,
        prev && prev.cliType,
      ]) || "").trim().toLowerCase();
    }

    function conversationSessionHasPermissionMode(row) {
      const src = (row && typeof row === "object") ? row : {};
      if (src._codebuddy_permission_mode_present === true || src.codebuddyPermissionModePresent === true) return true;
      return Object.prototype.hasOwnProperty.call(src, "codebuddy_permission_mode")
        || Object.prototype.hasOwnProperty.call(src, "codebuddyPermissionMode");
    }

    function conversationSessionHasClaudePermissionMode(row) {
      const src = (row && typeof row === "object") ? row : {};
      if (src._claude_permission_mode_present === true || src.claudePermissionModePresent === true) return true;
      return Object.prototype.hasOwnProperty.call(src, "claude_permission_mode")
        || Object.prototype.hasOwnProperty.call(src, "claudePermissionMode")
        || Object.prototype.hasOwnProperty.call(src, "permission_mode")
        || Object.prototype.hasOwnProperty.call(src, "permissionMode");
    }

    function conversationSessionModelMergeIsExplicit(row) {
      const source = conversationSessionModelMergeSource(row);
      if (!source) return false;
      return /(?:composer-model-switch|session-info|session-detail|model-save|manual|user|edit|detail)/i.test(source);
    }

    function conversationSessionPermissionModeMergeIsExplicit(row) {
      const source = conversationSessionPermissionModeMergeSource(row);
      if (!source) return false;
      return /(?:composer-permission-switch|session-info|session-detail|permission-save|manual|user|edit|detail)/i.test(source);
    }

    function mergeConversationSessionModelValue(nextRaw, prevRaw) {
      const next = (nextRaw && typeof nextRaw === "object") ? nextRaw : {};
      const prev = (prevRaw && typeof prevRaw === "object") ? prevRaw : {};
      const nextModel = normalizeSessionModel(next.model);
      const prevModel = normalizeSessionModel(prev.model);
      if (!prevModel) return nextModel;
      if (!nextModel) return prevModel;
      const cliType = conversationSessionModelMergeCliType(next, prev);
      if (isCodeBuddyCliType(cliType)) {
        const defaultModel = codeBuddySessionDefaultModelValue();
        const nextIsDefault = nextModel === defaultModel;
        const prevIsNonDefault = prevModel && prevModel !== defaultModel;
        if (nextIsDefault && prevIsNonDefault && !conversationSessionModelMergeIsExplicit(next)) {
          return prevModel;
        }
      }
      return nextModel;
    }

    function mergeConversationSessionPermissionModeValue(nextRaw, prevRaw) {
      const next = (nextRaw && typeof nextRaw === "object") ? nextRaw : {};
      const prev = (prevRaw && typeof prevRaw === "object") ? prevRaw : {};
      const nextHasMode = conversationSessionHasPermissionMode(next);
      const nextMode = normalizeConversationCodeBuddyPermissionMode(
        nextHasMode ? (next.codebuddy_permission_mode || next.codebuddyPermissionMode) : ""
      );
      const prevMode = normalizeConversationCodeBuddyPermissionMode(prev.codebuddy_permission_mode || prev.codebuddyPermissionMode);
      if (!nextHasMode) return prevMode || codeBuddySessionDefaultPermissionModeValue();
      const cliType = conversationSessionModelMergeCliType(next, prev);
      if (isCodeBuddyCliType(cliType)) {
        const defaultMode = codeBuddySessionDefaultPermissionModeValue();
        const nextIsDefault = nextMode === defaultMode;
        const prevIsNonDefault = prevMode && prevMode !== defaultMode;
        if (nextIsDefault && prevIsNonDefault && !conversationSessionPermissionModeMergeIsExplicit(next)) {
          return prevMode;
        }
      }
      return nextMode || codeBuddySessionDefaultPermissionModeValue();
    }

    function preserveConversationSessionDetailFields(nextRaw, prevRaw) {
      const next = normalizeConversationSession(nextRaw);
      if (!next) return null;
      const prev = normalizeConversationSession(prevRaw);
      if (!prev || prev.sessionId !== next.sessionId) return next;
      const nextExecContext = buildProjectExecutionContextMeta(next.project_execution_context || null);
      const prevExecContext = buildProjectExecutionContextMeta(prev.project_execution_context || null);
      const merged = {
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
        communication_status_summary: hasCommunicationStatusSummaryClientData(next.communication_status_summary)
          ? next.communication_status_summary
          : (hasCommunicationStatusSummaryClientData(prev.communication_status_summary) ? prev.communication_status_summary : next.communication_status_summary),
        model: mergeConversationSessionModelValue(nextRaw, prevRaw),
        codebuddy_permission_mode: mergeConversationSessionPermissionModeValue(nextRaw, prevRaw),
        codebuddyPermissionMode: mergeConversationSessionPermissionModeValue(nextRaw, prevRaw),
        claude_permission_mode: firstNonEmptyText([
          next.claude_permission_mode,
          next.claudePermissionMode,
          next.permission_mode,
          next.permissionMode,
          prev.claude_permission_mode,
          prev.claudePermissionMode,
          prev.permission_mode,
          prev.permissionMode,
        ]),
        claudePermissionMode: firstNonEmptyText([
          next.claude_permission_mode,
          next.claudePermissionMode,
          next.permission_mode,
          next.permissionMode,
          prev.claude_permission_mode,
          prev.claudePermissionMode,
          prev.permission_mode,
          prev.permissionMode,
        ]),
        memo_summary: next.memo_summary || next.memoSummary || prev.memo_summary || prev.memoSummary || null,
        memoSummary: next.memoSummary || next.memo_summary || prev.memoSummary || prev.memo_summary || null,
      };
      return preserveConversationActiveSessionStateFields(merged, prev);
    }

    function mergeConversationSessions(localSessions, serverSessions) {
      const map = new Map();
      const serverChannelSessions = new Map();
      const visibleSession = (session) => {
        if (!session) return false;
        if (typeof isVisibleConversationSession === "function") return isVisibleConversationSession(session);
        const deleted = typeof boolLike === "function"
          ? boolLike(session.is_deleted || session.isDeleted)
          : ["1", "true", "yes", "y"].includes(String(session.is_deleted || session.isDeleted || "").trim().toLowerCase());
        const inactive = String(session.status || session.session_status || session.sessionStatus || "").trim().toLowerCase() === "inactive";
        return !deleted && !inactive;
      };

      for (const raw of (Array.isArray(serverSessions) ? serverSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
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
        if (!visibleSession(n)) continue;
        const channelKey = String(n.channel_name || n.primaryChannel || "").trim();
        const channelBucket = channelKey ? serverChannelSessions.get(channelKey) : null;
        if (channelBucket && channelBucket.size && !channelBucket.has(n.sessionId)) continue;
        map.set(n.sessionId, n);
      }
      for (const raw of (Array.isArray(serverSessions) ? serverSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
        if (!visibleSession(n)) {
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
        const merged = {
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
          model: mergeConversationSessionModelValue(n, prev),
          codebuddy_permission_mode: typeof mergeConversationSessionPermissionModeValue === "function"
            ? mergeConversationSessionPermissionModeValue(n, prev)
            : firstNonEmptyText([n.codebuddy_permission_mode, n.codebuddyPermissionMode, prev.codebuddy_permission_mode, prev.codebuddyPermissionMode], "default"),
          codebuddyPermissionMode: typeof mergeConversationSessionPermissionModeValue === "function"
            ? mergeConversationSessionPermissionModeValue(n, prev)
            : firstNonEmptyText([n.codebuddy_permission_mode, n.codebuddyPermissionMode, prev.codebuddy_permission_mode, prev.codebuddyPermissionMode], "default"),
          claude_permission_mode: firstNonEmptyText([
            n.claude_permission_mode,
            n.claudePermissionMode,
            n.permission_mode,
            n.permissionMode,
            prev.claude_permission_mode,
            prev.claudePermissionMode,
            prev.permission_mode,
            prev.permissionMode,
          ]),
          claudePermissionMode: firstNonEmptyText([
            n.claude_permission_mode,
            n.claudePermissionMode,
            n.permission_mode,
            n.permissionMode,
            prev.claude_permission_mode,
            prev.claudePermissionMode,
            prev.permission_mode,
            prev.permissionMode,
          ]),
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
          latest_effective_run_summary: n.latest_effective_run_summary || prev.latest_effective_run_summary || normalizeLatestEffectiveRunSummary(null),
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
          communication_status_summary: mergeCommunicationStatusSummaryClient(
            prev.communication_status_summary || null,
            n.communication_status_summary || null
          ),
          project_execution_context: nextExecContext.available
            ? n.project_execution_context
            : (prevExecContext.available ? prev.project_execution_context : n.project_execution_context),
          task_tracking: nextTaskTracking,
        };
        map.set(n.sessionId, preserveConversationActiveSessionStateFields(merged, prev));
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
      agentsMdDirty: false,
    };
