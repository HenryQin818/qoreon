    function isFocusedConversationSession(projectId, sessionId) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      return !!(
        pid
        && sid
        && typeof STATE !== "undefined"
        && STATE
        && String(STATE.panelMode || "").trim() === "conv"
        && String(STATE.project || "").trim() === pid
        && String(STATE.selectedSessionId || "").trim() === sid
      );
    }

    function shouldDeferFocusedConversationRefresh(projectId, sessionId, opts = {}) {
      const pid = String(projectId || (opts && opts.projectId) || "").trim();
      const sid = String(sessionId || (opts && opts.sessionId) || "").trim();
      if (isFocusedConversationSession(pid, sid)) return false;
      return true;
    }

    function shouldBypassConversationPanelBusyGate(source, opts = {}) {
      const src = String(source || "").trim().toLowerCase();
      if (src === "poll" || src === "resume") return false;
      const pid = String((opts && opts.projectId) || (typeof STATE !== "undefined" && STATE ? STATE.project : "") || "").trim();
      const sid = String((opts && opts.sessionId) || (typeof STATE !== "undefined" && STATE ? STATE.selectedSessionId : "") || "").trim();
      if (!isFocusedConversationSession(pid, sid)) return false;
      return src === "manual" || src === "send" || src === "select" || src === "user" || src === "detail";
    }

    function selectConversationTimelineRuns(projectId, sessionId) {
      const snapshot = conversationStoreSnapshot(projectId, sessionId);
      return Array.isArray(snapshot.runs) ? snapshot.runs.slice() : [];
    }

    function selectConversationMessages(projectId, sessionId) {
      const snapshot = conversationStoreSnapshot(projectId, sessionId);
      return Array.isArray(snapshot.messages) ? snapshot.messages.slice() : [];
    }

    function selectConversationSessionPreview(projectId, sessionId) {
      const snapshot = conversationStoreSnapshot(projectId, sessionId);
      const session = snapshot.session || {};
      const messages = Array.isArray(snapshot.messages) ? snapshot.messages : [];
      const runs = Array.isArray(snapshot.runs) ? snapshot.runs : [];
      const firstMessage = messages.find((m) => String((m && m.status) || "").toLowerCase() === "optimistic") || messages[0] || null;
      const firstRun = runs[0] || null;
      const latestRunSummary = session && typeof getSessionLatestRunSummary === "function"
        ? getSessionLatestRunSummary(session)
        : {};
      const preview = String(
        (firstMessage && (firstMessage.text || firstMessage.message))
        || (session && typeof getSessionPrimaryPreviewText === "function" ? getSessionPrimaryPreviewText(session) : "")
        || (latestRunSummary && latestRunSummary.preview)
        || (firstRun && (firstRun.messagePreview || firstRun.preview))
        || ""
      ).trim();
      return {
        projectId: String(projectId || "").trim(),
        sessionId: String(sessionId || "").trim(),
        preview,
        status: String((firstMessage && firstMessage.status) || (session && (session.lastStatus || session.session_display_state)) || (firstRun && firstRun.status) || "idle"),
        latestAt: String((firstMessage && (firstMessage.updatedAt || firstMessage.createdAt)) || (session && (session.lastActiveAt || session.updatedAt)) || (firstRun && (firstRun.updatedAt || firstRun.createdAt)) || ""),
        source: firstMessage ? "message" : (session ? "session" : (firstRun ? "run" : "")),
      };
    }

    function selectConversationAttachmentList(projectId, sessionId) {
      const store = ensureConversationStore();
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      const prefix = conversationStoreSessionKey(pid, sid);
      if (!prefix) return [];
      return Object.keys(store.attachmentsByKey)
        .filter((key) => key.indexOf(prefix + "::att::") === 0)
        .map((key) => store.attachmentsByKey[key])
        .filter(Boolean)
        .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
    }

    function selectConversationRuntimeState(projectId, sessionId) {
      const snapshot = conversationStoreSnapshot(projectId, sessionId);
      const session = snapshot.session || {};
      const runtime = (session.runtime_state && typeof session.runtime_state === "object") ? session.runtime_state : {};
      return {
        projectId: String(projectId || "").trim(),
        sessionId: String(sessionId || "").trim(),
        displayState: String(runtime.display_state || session.session_display_state || session.lastStatus || "idle"),
        activeRunId: String(runtime.active_run_id || runtime.activeRunId || ""),
        queuedRunId: String(runtime.queued_run_id || runtime.queuedRunId || ""),
        source: session ? "store" : "",
      };
    }
