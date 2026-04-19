    function conversationStreamEndpoint(projectId, sessionId) {
      const root = conversationStoreRoot();
      const explicit = root && root.TASK_DASHBOARD_CONVERSATION_WS_ENDPOINT;
      if (!explicit) return "";
      const url = String(explicit || "").trim();
      if (!url) return "";
      const sep = url.indexOf("?") >= 0 ? "&" : "?";
      return url + sep + "projectId=" + encodeURIComponent(String(projectId || "")) + "&sessionId=" + encodeURIComponent(String(sessionId || ""));
    }

    function conversationStreamSupported(projectId, sessionId) {
      const endpoint = conversationStreamEndpoint(projectId, sessionId);
      return !!(endpoint && typeof WebSocket !== "undefined");
    }

    function disconnectFocusedConversationStream(reason = "") {
      const store = ensureConversationStore();
      const meta = store.meta.focusedStream || null;
      if (meta && meta.socket && typeof meta.socket.close === "function") {
        try { meta.socket.close(1000, String(reason || "switch")); } catch (_) {}
      }
      store.meta.focusedStream = {
        projectId: "",
        sessionId: "",
        mode: "http-fallback",
        socket: null,
        updatedAt: conversationStoreNowIso(),
      };
    }

    function normalizeConversationProjectionRunItem(raw) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const runId = String(firstNonEmptyText([item.run_id, item.runId]) || "").trim();
      if (!runId) return null;
      const status = normalizeDisplayState(item.status, "idle");
      const assistantPreview = String(firstNonEmptyText([
        item.response_preview,
        item.responsePreview,
        item.preview,
      ]) || "").trim();
      const working = typeof isRunWorking === "function"
        ? isRunWorking(status)
        : (status === "running" || status === "queued" || status === "retry_waiting" || status === "external_busy");
      return {
        id: runId,
        createdAt: String(firstNonEmptyText([item.created_at, item.createdAt, item.updated_at, item.updatedAt]) || "").trim(),
        updatedAt: String(firstNonEmptyText([item.updated_at, item.updatedAt, item.created_at, item.createdAt]) || "").trim(),
        status,
        display_state: status,
        messagePreview: String(firstNonEmptyText([item.message_preview, item.messagePreview]) || "").trim(),
        lastPreview: working ? "" : assistantPreview,
        partialPreview: working ? assistantPreview : "",
        agentMessagesCount: assistantPreview ? 1 : 0,
        source: "session-snapshot-projection",
      };
    }

    function buildConversationProjectionRuntimeState(summary, runs) {
      const view = (summary && typeof summary === "object") ? summary : {};
      const list = Array.isArray(runs) ? runs : [];
      const latestRun = list[0] || null;
      const latestRunId = String(firstNonEmptyText([
        latestRun && latestRun.id,
        view.latest_run_id,
        view.latestRunId,
      ]) || "").trim();
      const displayState = normalizeDisplayState(firstNonEmptyText([
        view.display_state,
        view.displayState,
        latestRun && latestRun.status,
      ]), "idle");
      const activeLike = displayState === "running" || displayState === "retry_waiting" || displayState === "external_busy";
      const queuedLike = displayState === "queued";
      return {
        internal_state: displayState,
        display_state: displayState,
        active_run_id: activeLike ? latestRunId : "",
        queued_run_id: queuedLike ? latestRunId : "",
        queue_depth: queuedLike && latestRunId ? 1 : 0,
        updated_at: String(firstNonEmptyText([
          latestRun && latestRun.updatedAt,
          view.updated_at,
          view.updatedAt,
          conversationStoreNowIso(),
        ]) || "").trim(),
      };
    }

    function buildConversationProjectionTaskTracking(summaryItem) {
      const item = (summaryItem && typeof summaryItem === "object") ? summaryItem : {};
      const currentTaskRef = item.current_task_ref || item.currentTaskRef || null;
      if (!currentTaskRef || typeof normalizeTaskTrackingClient !== "function") return null;
      return normalizeTaskTrackingClient({
        current_task_ref: currentTaskRef,
        updated_at: conversationStoreNowIso(),
      });
    }

    function installConversationProjectionRuns(projectId, sessionId, runs, opts = {}) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      if (!pid || !sid) return [];
      const projectionRuns = (Array.isArray(runs) ? runs : []).filter(Boolean);
      if (!projectionRuns.length) return [];
      if (!PCONV.runsBySession || typeof PCONV.runsBySession !== "object") {
        PCONV.runsBySession = Object.create(null);
      }
      if (!PCONV.sessionTimelineMap || typeof PCONV.sessionTimelineMap !== "object") {
        PCONV.sessionTimelineMap = Object.create(null);
      }
      if (!PCONV.processTrailByRun || typeof PCONV.processTrailByRun !== "object") {
        PCONV.processTrailByRun = Object.create(null);
      }
      const timelineKey = pid + "::" + sid;
      const existingRuns = Array.isArray(PCONV.sessionTimelineMap[timelineKey])
        ? PCONV.sessionTimelineMap[timelineKey]
        : (Array.isArray(PCONV.runsBySession[sid]) ? PCONV.runsBySession[sid] : []);
      const keepLimit = Math.max(260, Math.min(1200, Number(existingRuns.length || 0) + projectionRuns.length + 40));
      const mergedRuns = typeof mergeRunsById === "function"
        ? mergeRunsById(existingRuns, projectionRuns, keepLimit)
        : projectionRuns.slice();
      PCONV.sessionTimelineMap[timelineKey] = mergedRuns;
      PCONV.runsBySession[sid] = mergedRuns;
      projectionRuns.forEach((run) => {
        const rid = String((run && run.id) || "").trim();
        const progressText = String(firstNonEmptyText([
          run && run.partialPreview,
          run && run.lastPreview,
        ]) || "").trim();
        if (!rid || !progressText) return;
        PCONV.processTrailByRun[rid] = {
          items: [progressText],
          rows: [{
            text: progressText,
            at: String(firstNonEmptyText([run && run.updatedAt, run && run.createdAt]) || "").trim(),
            timeSource: "projection",
          }],
          status: String(run && run.status || "").trim(),
          updatedAt: Date.now(),
        };
      });
      if (typeof conversationStoreUpsertRuns === "function") {
        conversationStoreUpsertRuns(pid, sid, mergedRuns, { source: String((opts && opts.source) || "session-snapshot") });
      }
      if (typeof primeConversationHistoryFromRuns === "function") {
        primeConversationHistoryFromRuns(pid, sid, mergedRuns, { source: String((opts && opts.source) || "session-snapshot") });
      }
      return mergedRuns;
    }

    function applyConversationProjectionSnapshot(projectId, sessionId, projection, opts = {}) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      const snapshot = (projection && typeof projection === "object") ? projection : null;
      if (!pid || !sid || !snapshot) return false;
      const items = Array.isArray(snapshot.items) ? snapshot.items : [];
      const summaryItem = items.find((item) => String(item && item.entity_type || "").trim().toLowerCase() === "session_summary") || null;
      const projectionRuns = items
        .filter((item) => String(item && item.entity_type || "").trim().toLowerCase() === "run_message")
        .map((item) => normalizeConversationProjectionRunItem(item))
        .filter(Boolean);
      const mergedRuns = installConversationProjectionRuns(pid, sid, projectionRuns, opts);
      const latestRun = mergedRuns[0] || projectionRuns[0] || null;
      const runtimeState = buildConversationProjectionRuntimeState(snapshot.summary, mergedRuns);
      const latestRunId = String(firstNonEmptyText([
        latestRun && latestRun.id,
        summaryItem && summaryItem.run_id,
        snapshot.summary && snapshot.summary.latest_run_id,
      ]) || "").trim();
      const latestRunStatus = normalizeDisplayState(firstNonEmptyText([
        latestRun && latestRun.status,
        summaryItem && summaryItem.status,
        snapshot.summary && snapshot.summary.display_state,
      ]), "idle");
      const latestPreview = String(firstNonEmptyText([
        latestRun && latestRun.lastPreview,
        latestRun && latestRun.partialPreview,
        summaryItem && summaryItem.preview,
        snapshot.summary && snapshot.summary.latest_preview,
      ]) || "").trim();
      const latestUserMsg = String(firstNonEmptyText([
        latestRun && latestRun.messagePreview,
      ]) || "").trim();
      const latestEffectiveRunSummary = (latestRunStatus === "done" || latestRunStatus === "error")
        ? {
            run_id: latestRunId,
            outcome_state: latestRunStatus === "done" ? "success" : "failed_business",
            preview: latestPreview,
            created_at: String(firstNonEmptyText([
              latestRun && latestRun.updatedAt,
              latestRun && latestRun.createdAt,
            ]) || "").trim(),
          }
        : null;
      const mergedSession = typeof mergeConversationSessionDetailIntoStore === "function"
        ? mergeConversationSessionDetailIntoStore({
            project_id: pid,
            projectId: pid,
            id: sid,
            sessionId: sid,
            source: String((opts && opts.source) || "session-snapshot"),
            session_display_state: String(firstNonEmptyText([
              snapshot.summary && snapshot.summary.display_state,
              summaryItem && summaryItem.status,
            ]) || "").trim(),
            session_display_reason: String(firstNonEmptyText([
              snapshot.summary && snapshot.summary.display_reason,
              "active_projection",
            ]) || "active_projection").trim(),
            runtime_state: runtimeState,
            latest_run_summary: {
              run_id: latestRunId,
              status: latestRunStatus,
              preview: latestPreview,
              updated_at: String(firstNonEmptyText([
                latestRun && latestRun.updatedAt,
                latestRun && latestRun.createdAt,
                runtimeState.updated_at,
              ]) || "").trim(),
              latest_user_msg: latestUserMsg,
            },
            latest_effective_run_summary: latestEffectiveRunSummary,
            latestUserMsg: latestUserMsg,
            latestAiMsg: latestPreview,
            task_tracking: buildConversationProjectionTaskTracking(summaryItem),
          }, sid)
        : null;
      if (!mergedSession && typeof conversationStoreUpsertSession === "function") {
        conversationStoreUpsertSession({
          project_id: pid,
          projectId: pid,
          id: sid,
          sessionId: sid,
          runtime_state: runtimeState,
          session_display_state: runtimeState.display_state,
        }, { projectId: pid, sessionId: sid, source: String((opts && opts.source) || "session-snapshot") });
      }
      if (
        typeof buildConversationLeftList === "function"
        && isFocusedConversationSession(pid, sid)
      ) {
        buildConversationLeftList();
      }
      return true;
    }

    function connectFocusedConversationStream(projectId, sessionId, opts = {}) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      const store = ensureConversationStore();
      const current = store.meta.focusedStream || null;
      if (!pid || !sid || pid === "overview") {
        disconnectFocusedConversationStream("empty");
        return { ok: false, mode: "http-fallback", reason: "empty-route" };
      }
      if (current && current.projectId === pid && current.sessionId === sid && current.socket) {
        return { ok: true, mode: current.mode || "websocket", reason: "reuse" };
      }
      if (current && current.socket) disconnectFocusedConversationStream("switch");
      if (!conversationStreamSupported(pid, sid)) {
        store.meta.focusedStream = {
          projectId: pid,
          sessionId: sid,
          mode: "http-fallback",
          socket: null,
          updatedAt: conversationStoreNowIso(),
          reason: "endpoint-disabled",
        };
        return { ok: false, mode: "http-fallback", reason: "endpoint-disabled" };
      }
      const endpoint = conversationStreamEndpoint(pid, sid);
      try {
        const socket = new WebSocket(endpoint);
        store.meta.focusedStream = {
          projectId: pid,
          sessionId: sid,
          mode: "websocket",
          socket,
          updatedAt: conversationStoreNowIso(),
        };
        socket.onmessage = (event) => {
          let payload = null;
          try { payload = JSON.parse(String(event && event.data || "")); } catch (_) { payload = null; }
          if (!payload || typeof payload !== "object") return;
          const streamEvent = String(payload.event || payload.event_name || "").trim().toLowerCase();
          if (streamEvent === "stream.keepalive") return;
          if (streamEvent === "session.snapshot") {
            const snapshotPayload = payload.payload && typeof payload.payload === "object"
              ? payload.payload
              : {};
            const projection = snapshotPayload.projection && typeof snapshotPayload.projection === "object"
              ? snapshotPayload.projection
              : null;
            if (projection) {
              applyConversationProjectionSnapshot(pid, sid, projection, { source: "ws-snapshot" });
              if (isFocusedConversationSession(pid, sid) && typeof renderConversationDetail === "function") {
                renderConversationDetail(false);
              }
            }
            return;
          }
          const type = normalizeConversationEventType(payload.type || payload.event_type);
          const eventPayload = payload.payload && typeof payload.payload === "object" ? payload.payload : payload;
          if (type === "session") applyConversationStoreEvent(conversationEventFromSession(eventPayload, { projectId: pid, sessionId: sid, source: "ws" }));
          else if (type === "run") applyConversationStoreEvent(conversationEventFromRun(eventPayload, { projectId: pid, sessionId: sid, source: "ws" }));
          else if (type === "attachment") applyConversationStoreEvent(conversationEventFromAttachment(pid, sid, eventPayload, { source: "ws" }));
          else applyConversationStoreEvent({ type: "message", projectId: pid, sessionId: sid, payload: eventPayload, source: "ws" });
          if (isFocusedConversationSession(pid, sid) && typeof renderConversationDetail === "function") renderConversationDetail(false);
        };
        socket.onerror = () => {
          store.meta.focusedStream = {
            projectId: pid,
            sessionId: sid,
            mode: "http-fallback",
            socket: null,
            updatedAt: conversationStoreNowIso(),
            reason: "socket-error",
          };
        };
        return { ok: true, mode: "websocket", reason: "connected" };
      } catch (err) {
        store.meta.focusedStream = {
          projectId: pid,
          sessionId: sid,
          mode: "http-fallback",
          socket: null,
          updatedAt: conversationStoreNowIso(),
          reason: String((err && err.message) || err || "socket-error"),
        };
        return { ok: false, mode: "http-fallback", reason: "socket-error" };
      }
    }

    function kickFocusedConversationActiveRefresh(projectId, source = "") {
      const pid = String(projectId || (typeof STATE !== "undefined" && STATE ? STATE.project : "") || "").trim();
      const sid = String((typeof STATE !== "undefined" && STATE ? STATE.selectedSessionId : "") || "").trim();
      if (!isFocusedConversationSession(pid, sid)) return false;
      if (typeof restoreConversationHistorySnapshot === "function") {
        restoreConversationHistorySnapshot(pid, sid, { install: true, source: "busy-bypass" });
      }
      if (typeof renderConversationDetail === "function") renderConversationDetail(false);
      if (typeof pushPollingTrace === "function") {
        pushPollingTrace("sessions.detail.skip", {
          project_id: pid,
          session_id: sid,
          source,
          reason: "focused-active-refresh-uses-stream-and-timeline",
        });
      }
      if (typeof refreshConversationTimeline === "function") {
        refreshConversationTimeline(pid, sid, true).catch(() => {});
      }
      return true;
    }
