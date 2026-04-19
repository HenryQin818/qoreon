    const CONVERSATION_HISTORY_CACHE_PREFIX_V1 = "taskDashboard.conversationHistory.v1::";

    function conversationHistoryCacheKey(projectId, sessionId) {
      const skey = conversationStoreSessionKey(projectId, sessionId);
      return skey ? (CONVERSATION_HISTORY_CACHE_PREFIX_V1 + skey) : "";
    }

    function compactConversationHistoryRuns(runs, limit = 220) {
      const max = Math.max(20, Math.min(500, Number(limit || 220) || 220));
      return (Array.isArray(runs) ? runs : [])
        .filter((run) => run && typeof run === "object")
        .slice(0, max)
        .map((run) => ({
          ...run,
          logPreview: String(run.logPreview || "").slice(0, 1200),
          messagePreview: String(run.messagePreview || run.preview || "").slice(0, 2000),
        }));
    }

    function writeConversationHistorySnapshot(projectId, sessionId, runs, opts = {}) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      const key = conversationHistoryCacheKey(pid, sid);
      if (!key) return null;
      const snapshot = {
        version: CONVERSATION_STORE_VERSION_V1,
        projectId: pid,
        sessionId: sid,
        updatedAt: conversationStoreNowIso(),
        source: String((opts && opts.source) || "timeline"),
        runs: compactConversationHistoryRuns(runs, opts && opts.limit),
      };
      const store = ensureConversationStore();
      const skey = conversationStoreSessionKey(pid, sid);
      store.historyBySessionKey[skey] = snapshot;
      try {
        if (typeof localStorage !== "undefined") {
          localStorage.setItem(key, JSON.stringify(snapshot));
        }
      } catch (_) {}
      return snapshot;
    }

    function readConversationHistorySnapshot(projectId, sessionId, opts = {}) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      const skey = conversationStoreSessionKey(pid, sid);
      const key = conversationHistoryCacheKey(pid, sid);
      if (!skey || !key) return null;
      const maxAgeMs = Math.max(0, Number((opts && opts.maxAgeMs) || 6 * 60 * 60 * 1000) || 0);
      const store = ensureConversationStore();
      let snapshot = store.historyBySessionKey[skey] || null;
      if (!snapshot && typeof localStorage !== "undefined") {
        try {
          const raw = localStorage.getItem(key);
          snapshot = raw ? JSON.parse(raw) : null;
        } catch (_) {
          snapshot = null;
        }
      }
      if (!snapshot || typeof snapshot !== "object") return null;
      const updatedTs = conversationStoreTimestamp(snapshot.updatedAt);
      if (maxAgeMs > 0 && updatedTs >= 0 && (Date.now() - updatedTs) > maxAgeMs) return null;
      const runs = Array.isArray(snapshot.runs) ? snapshot.runs : [];
      if (!runs.length) return null;
      store.historyBySessionKey[skey] = snapshot;
      return snapshot;
    }

    function primeConversationHistoryFromRuns(projectId, sessionId, runs, opts = {}) {
      const list = Array.isArray(runs) ? runs : [];
      if (!list.length) return null;
      conversationStoreUpsertRuns(projectId, sessionId, list, { source: String((opts && opts.source) || "history-prime") });
      return writeConversationHistorySnapshot(projectId, sessionId, list, opts);
    }

    function restoreConversationHistorySnapshot(projectId, sessionId, opts = {}) {
      const snapshot = readConversationHistorySnapshot(projectId, sessionId, opts);
      if (!snapshot || !Array.isArray(snapshot.runs) || !snapshot.runs.length) return null;
      const install = !!(opts && opts.install);
      if (install && typeof PCONV !== "undefined" && PCONV) {
        const key = conversationStoreSessionKey(projectId, sessionId);
        if (key && (!Array.isArray(PCONV.sessionTimelineMap[key]) || !PCONV.sessionTimelineMap[key].length)) {
          PCONV.sessionTimelineMap[key] = snapshot.runs.slice();
        }
      }
      conversationStoreUpsertRuns(projectId, sessionId, snapshot.runs, { source: String((opts && opts.source) || "history-cache") });
      return snapshot;
    }
