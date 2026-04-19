    function createConversationClientMessageId(ctx = {}) {
      const c = (ctx && typeof ctx === "object") ? ctx : {};
      const sid = String(c.sessionId || c.session_id || "").trim().slice(0, 8) || "session";
      return "cmid-" + sid + "-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
    }

    function conversationRunMatchesOptimistic(run, optimistic) {
      const r = (run && typeof run === "object") ? run : {};
      const o = (optimistic && typeof optimistic === "object") ? optimistic : {};
      const runId = String(r.id || r.run_id || r.runId || "").trim();
      const optimisticRunId = String(o.runId || o.run_id || "").trim();
      if (runId && optimisticRunId && runId === optimisticRunId) return true;
      const cmid = String(o.clientMessageId || o.client_message_id || "").trim();
      const runCmid = String(r.client_message_id || r.clientMessageId || r.ui_client_message_id || "").trim();
      if (cmid && runCmid && cmid === runCmid) return true;
      if (typeof isConversationRunMaterializedForOptimistic === "function") {
        try {
          if (isConversationRunMaterializedForOptimistic(r, o)) return true;
        } catch (_) {}
      }
      const left = String(r.messagePreview || r.preview || "").replace(/\s+/g, " ").trim();
      const right = String(o.message || o.text || "").replace(/\s+/g, " ").trim();
      if (!left || !right || !(left === right || left.startsWith(right) || right.startsWith(left))) return false;
      const ot = conversationStoreTimestamp(o.createdAt || o.created_at);
      const rt = conversationStoreTimestamp(r.createdAt || r.created_at);
      if (ot < 0 || rt < 0) return false;
      const delta = rt - ot;
      return delta >= -3000 && delta <= 120000;
    }

    function recordConversationOptimistic(ctx, optimistic, opts = {}) {
      const event = conversationEventFromOptimisticMessage(ctx, optimistic, opts);
      if (!event) return null;
      return applyConversationStoreEvent(event);
    }

    function acknowledgeConversationOptimistic(ctx, clientMessageId, response, opts = {}) {
      const event = conversationEventFromAnnounceAck(ctx, clientMessageId, response, opts);
      if (!event) return null;
      const result = applyConversationStoreEvent(event);
      const run = response && response.run && typeof response.run === "object" ? response.run : null;
      if (run) {
        conversationStoreUpsertRun(event.projectId, event.sessionId, {
          ...run,
          client_message_id: event.clientMessageId,
        }, { source: "announce-ack" });
      }
      return result;
    }

    function reconcileConversationOptimisticWithRun(ctx, optimistic, run, opts = {}) {
      const context = (ctx && typeof ctx === "object") ? ctx : {};
      const o = (optimistic && typeof optimistic === "object") ? optimistic : {};
      const r = (run && typeof run === "object") ? run : {};
      if (!conversationRunMatchesOptimistic(r, o)) return false;
      const pid = String(context.projectId || o.projectId || o.project_id || r.projectId || r.project_id || "").trim();
      const sid = String(context.sessionId || o.sessionId || o.session_id || conversationStoreRunSessionId(r, "") || "").trim();
      const clientMessageId = String(o.clientMessageId || o.client_message_id || "").trim();
      const runId = String(r.id || r.run_id || r.runId || "").trim();
      conversationStoreRecordMessage({
        projectId: pid,
        sessionId: sid,
        clientMessageId,
        runId,
        status: "materialized",
        materializedAt: conversationStoreNowIso(),
        text: String(o.message || o.text || ""),
      }, { projectId: pid, sessionId: sid, source: String((opts && opts.source) || "reconciler") });
      if (runId) conversationStoreUpsertRun(pid, sid, r, { source: "reconciler" });
      return true;
    }

    function reconcileConversationOptimisticWithRuns(projectId, sessionId, optimistic, runs, opts = {}) {
      const list = Array.isArray(runs) ? runs : [];
      for (const run of list) {
        if (reconcileConversationOptimisticWithRun({ projectId, sessionId }, optimistic, run, opts)) return true;
      }
      return false;
    }
