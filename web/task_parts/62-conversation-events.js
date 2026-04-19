    function normalizeConversationEventType(raw) {
      const text = String(raw || "").trim().toLowerCase();
      if (text === "session" || text === "run" || text === "message" || text === "attachment" || text === "ack") return text;
      return "message";
    }

    function conversationEventSessionId(raw, fallback = "") {
      const src = (raw && typeof raw === "object") ? raw : {};
      return String(src.sessionId || src.session_id || src.codex_session_id || src.codexSessionId || fallback || "").trim();
    }

    function conversationEventProjectId(raw, fallback = "") {
      const src = (raw && typeof raw === "object") ? raw : {};
      return String(src.projectId || src.project_id || fallback || (typeof STATE !== "undefined" && STATE ? STATE.project : "") || "").trim();
    }

    function conversationEventFromSession(session, opts = {}) {
      const src = (session && typeof session === "object") ? session : {};
      const pid = conversationEventProjectId(src, opts && opts.projectId);
      const sid = conversationEventSessionId(src, opts && opts.sessionId);
      if (!pid || !sid) return null;
      return {
        type: "session",
        projectId: pid,
        sessionId: sid,
        payload: src,
        source: String((opts && opts.source) || src.source || ""),
        receivedAt: conversationStoreNowIso(),
      };
    }

    function conversationEventFromRun(run, opts = {}) {
      const src = (run && typeof run === "object") ? run : {};
      const pid = conversationEventProjectId(src, opts && opts.projectId);
      const sid = conversationEventSessionId(src, opts && opts.sessionId);
      const rid = String(src.id || src.run_id || src.runId || "").trim();
      if (!pid || !sid || !rid) return null;
      return {
        type: "run",
        projectId: pid,
        sessionId: sid,
        runId: rid,
        payload: src,
        source: String((opts && opts.source) || src.source || ""),
        receivedAt: conversationStoreNowIso(),
      };
    }

    function conversationEventsFromRuns(projectId, sessionId, runs, opts = {}) {
      return (Array.isArray(runs) ? runs : [])
        .map((run) => conversationEventFromRun(run, { ...(opts || {}), projectId, sessionId }))
        .filter(Boolean);
    }

    function conversationEventFromOptimisticMessage(ctx, optimistic, opts = {}) {
      const context = (ctx && typeof ctx === "object") ? ctx : {};
      const src = (optimistic && typeof optimistic === "object") ? optimistic : {};
      const pid = conversationEventProjectId(context, opts && opts.projectId);
      const sid = conversationEventSessionId(context, src.sessionId || (opts && opts.sessionId));
      const clientMessageId = String(src.clientMessageId || src.client_message_id || (opts && opts.clientMessageId) || "").trim();
      if (!pid || !sid || !clientMessageId) return null;
      return {
        type: "message",
        projectId: pid,
        sessionId: sid,
        clientMessageId,
        payload: {
          ...src,
          clientMessageId,
          projectId: pid,
          sessionId: sid,
          role: String(src.role || "user"),
          status: String(src.status || "optimistic"),
        },
        source: String((opts && opts.source) || "optimistic"),
        receivedAt: conversationStoreNowIso(),
      };
    }

    function conversationEventFromAnnounceAck(ctx, clientMessageId, response, opts = {}) {
      const context = (ctx && typeof ctx === "object") ? ctx : {};
      const body = (response && typeof response === "object") ? response : {};
      const run = body.run && typeof body.run === "object" ? body.run : {};
      const pid = conversationEventProjectId(context, opts && opts.projectId);
      const sid = conversationEventSessionId(context, opts && opts.sessionId);
      const cmid = String(clientMessageId || body.client_message_id || body.clientMessageId || "").trim();
      const runId = String(run.id || body.run_id || body.runId || "").trim();
      if (!pid || !sid || (!cmid && !runId)) return null;
      return {
        type: "ack",
        projectId: pid,
        sessionId: sid,
        clientMessageId: cmid,
        runId,
        payload: body,
        source: String((opts && opts.source) || "announce"),
        receivedAt: conversationStoreNowIso(),
      };
    }

    function conversationEventFromAttachment(projectId, sessionId, attachment, opts = {}) {
      const src = (attachment && typeof attachment === "object") ? attachment : {};
      const pid = String(projectId || src.projectId || src.project_id || "").trim();
      const sid = String(sessionId || src.sessionId || src.session_id || "").trim();
      const aid = String(src.localId || src.local_id || src.attachmentId || src.attachment_id || src.filename || src.url || "").trim();
      if (!pid || !sid || !aid) return null;
      return {
        type: "attachment",
        projectId: pid,
        sessionId: sid,
        attachmentId: aid,
        payload: src,
        source: String((opts && opts.source) || src.source || ""),
        receivedAt: conversationStoreNowIso(),
      };
    }

    function applyConversationStoreEvent(event) {
      const ev = (event && typeof event === "object") ? event : null;
      if (!ev) return null;
      const type = normalizeConversationEventType(ev.type);
      if (type === "session") return conversationStoreUpsertSession(ev.payload, { projectId: ev.projectId, sessionId: ev.sessionId, source: ev.source });
      if (type === "run") return conversationStoreUpsertRun(ev.projectId, ev.sessionId, ev.payload, { source: ev.source });
      if (type === "message") return conversationStoreRecordMessage(ev.payload, { projectId: ev.projectId, sessionId: ev.sessionId, source: ev.source });
      if (type === "attachment") return conversationStoreUpsertAttachment(ev.projectId, ev.sessionId, ev.payload, { source: ev.source });
      if (type === "ack") {
        return conversationStoreRecordMessage({
          projectId: ev.projectId,
          sessionId: ev.sessionId,
          clientMessageId: ev.clientMessageId,
          runId: ev.runId,
          status: "acknowledged",
          acknowledgedAt: ev.receivedAt,
          response: ev.payload,
        }, { projectId: ev.projectId, sessionId: ev.sessionId, source: ev.source });
      }
      return null;
    }
