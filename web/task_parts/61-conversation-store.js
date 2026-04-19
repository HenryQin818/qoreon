    const CONVERSATION_STORE_VERSION_V1 = "20260410-chat-single-source-v1";

    function conversationStoreRoot() {
      if (typeof window !== "undefined") return window;
      if (typeof globalThis !== "undefined") return globalThis;
      return {};
    }

    function conversationStoreNowIso() {
      try { return new Date().toISOString(); } catch (_) { return ""; }
    }

    function conversationStoreSessionKey(projectId, sessionId) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      if (!pid || !sid || pid === "overview") return "";
      return pid + "::" + sid;
    }

    function conversationStoreRunKey(projectId, sessionId, runId) {
      const skey = conversationStoreSessionKey(projectId, sessionId);
      const rid = String(runId || "").trim();
      if (!skey || !rid) return "";
      return skey + "::run::" + rid;
    }

    function conversationStoreMessageKey(projectId, sessionId, messageId) {
      const skey = conversationStoreSessionKey(projectId, sessionId);
      const mid = String(messageId || "").trim();
      if (!skey || !mid) return "";
      return skey + "::msg::" + mid;
    }

    function conversationStoreAttachmentKey(projectId, sessionId, attachmentId) {
      const skey = conversationStoreSessionKey(projectId, sessionId);
      const aid = String(attachmentId || "").trim();
      if (!skey || !aid) return "";
      return skey + "::att::" + aid;
    }

    function ensureConversationStore() {
      const root = conversationStoreRoot();
      if (!root.__taskDashboardConversationStoreV1__ || typeof root.__taskDashboardConversationStoreV1__ !== "object") {
        root.__taskDashboardConversationStoreV1__ = {
          version: CONVERSATION_STORE_VERSION_V1,
          updatedAt: "",
          sessionsByKey: Object.create(null),
          sessionOrderByProject: Object.create(null),
          runsByKey: Object.create(null),
          runOrderBySessionKey: Object.create(null),
          messagesByKey: Object.create(null),
          messageOrderBySessionKey: Object.create(null),
          attachmentsByKey: Object.create(null),
          attachmentOrderByMessageKey: Object.create(null),
          optimisticByClientId: Object.create(null),
          localAttachmentMap: Object.create(null),
          historyBySessionKey: Object.create(null),
          meta: Object.create(null),
        };
      }
      return root.__taskDashboardConversationStoreV1__;
    }

    function conversationStoreEnsureBucket(map, key) {
      if (!map || !key) return [];
      if (!Array.isArray(map[key])) map[key] = [];
      return map[key];
    }

    function conversationStorePutUnique(map, key, value) {
      if (!map || !key || !value) return;
      const bucket = conversationStoreEnsureBucket(map, key);
      const text = String(value || "").trim();
      if (!text || bucket.includes(text)) return;
      bucket.unshift(text);
      if (bucket.length > 500) bucket.length = 500;
    }

    function conversationStoreTimestamp(value) {
      if (typeof toTimeNum === "function") {
        const n = toTimeNum(value);
        if (n >= 0) return n;
      }
      const t = Date.parse(String(value || ""));
      return Number.isFinite(t) ? t : -1;
    }

    function conversationStoreSortKeysByTime(keys, lookup) {
      const src = Array.isArray(keys) ? keys.slice() : [];
      src.sort((a, b) => {
        const left = lookup && lookup[a] ? lookup[a] : {};
        const right = lookup && lookup[b] ? lookup[b] : {};
        const ta = conversationStoreTimestamp(left.updatedAt || left.createdAt || left.acknowledgedAt);
        const tb = conversationStoreTimestamp(right.updatedAt || right.createdAt || right.acknowledgedAt);
        if (ta >= 0 && tb >= 0 && ta !== tb) return tb - ta;
        return String(b || "").localeCompare(String(a || ""));
      });
      return src;
    }

    function conversationStoreUpsertSession(session, opts = {}) {
      const src = (session && typeof session === "object") ? session : {};
      const sid = String(src.sessionId || src.id || src.session_id || (opts && opts.sessionId) || "").trim();
      const pid = String(src.project_id || src.projectId || (opts && opts.projectId) || (typeof STATE !== "undefined" && STATE ? STATE.project : "") || "").trim();
      const key = conversationStoreSessionKey(pid, sid);
      if (!key) return null;
      const store = ensureConversationStore();
      const prev = store.sessionsByKey[key] || {};
      const next = {
        ...prev,
        ...src,
        project_id: pid,
        projectId: pid,
        sessionId: sid,
        id: sid,
        updatedAt: String(src.updatedAt || src.updated_at || src.lastActiveAt || src.last_used_at || prev.updatedAt || conversationStoreNowIso()),
        source: String((opts && opts.source) || src.source || prev.source || ""),
      };
      store.sessionsByKey[key] = next;
      conversationStorePutUnique(store.sessionOrderByProject, pid, key);
      store.updatedAt = conversationStoreNowIso();
      return next;
    }

    function conversationStoreUpsertSessions(projectId, sessions, opts = {}) {
      const list = Array.isArray(sessions) ? sessions : [];
      return list.map((session) => conversationStoreUpsertSession(session, {
        ...(opts || {}),
        projectId,
      })).filter(Boolean);
    }

    function conversationStoreRunSessionId(run, fallbackSessionId = "") {
      const src = (run && typeof run === "object") ? run : {};
      return String(src.sessionId || src.session_id || src.codex_session_id || src.codexSessionId || fallbackSessionId || "").trim();
    }

    function conversationStoreUpsertRun(projectId, sessionId, run, opts = {}) {
      const src = (run && typeof run === "object") ? run : {};
      const rid = String(src.id || src.run_id || src.runId || "").trim();
      const sid = conversationStoreRunSessionId(src, sessionId);
      const pid = String(projectId || src.project_id || src.projectId || (opts && opts.projectId) || "").trim();
      const key = conversationStoreRunKey(pid, sid, rid);
      if (!key) return null;
      const store = ensureConversationStore();
      const prev = store.runsByKey[key] || {};
      const next = {
        ...prev,
        ...src,
        id: rid,
        project_id: pid,
        projectId: pid,
        sessionId: sid,
        session_id: sid,
        updatedAt: String(src.updatedAt || src.updated_at || src.finishedAt || src.finished_at || src.createdAt || prev.updatedAt || conversationStoreNowIso()),
        source: String((opts && opts.source) || src.source || prev.source || ""),
      };
      store.runsByKey[key] = next;
      const skey = conversationStoreSessionKey(pid, sid);
      conversationStorePutUnique(store.runOrderBySessionKey, skey, key);
      store.runOrderBySessionKey[skey] = conversationStoreSortKeysByTime(store.runOrderBySessionKey[skey], store.runsByKey);
      store.updatedAt = conversationStoreNowIso();
      return next;
    }

    function conversationStoreUpsertRuns(projectId, sessionId, runs, opts = {}) {
      const list = Array.isArray(runs) ? runs : [];
      return list.map((run) => conversationStoreUpsertRun(projectId, sessionId, run, opts)).filter(Boolean);
    }

    function conversationStoreRecordMessage(message, opts = {}) {
      const src = (message && typeof message === "object") ? message : {};
      const pid = String(src.projectId || src.project_id || (opts && opts.projectId) || "").trim();
      const sid = String(src.sessionId || src.session_id || (opts && opts.sessionId) || "").trim();
      const mid = String(src.messageId || src.message_id || src.clientMessageId || src.client_message_id || src.runId || src.run_id || "").trim();
      const key = conversationStoreMessageKey(pid, sid, mid);
      if (!key) return null;
      const store = ensureConversationStore();
      const prev = store.messagesByKey[key] || {};
      const next = {
        ...prev,
        ...src,
        projectId: pid,
        project_id: pid,
        sessionId: sid,
        session_id: sid,
        messageId: mid,
        updatedAt: String(src.updatedAt || src.updated_at || src.acknowledgedAt || src.createdAt || prev.updatedAt || conversationStoreNowIso()),
      };
      store.messagesByKey[key] = next;
      const skey = conversationStoreSessionKey(pid, sid);
      conversationStorePutUnique(store.messageOrderBySessionKey, skey, key);
      store.messageOrderBySessionKey[skey] = conversationStoreSortKeysByTime(store.messageOrderBySessionKey[skey], store.messagesByKey);
      if (next.clientMessageId) store.optimisticByClientId[String(next.clientMessageId)] = key;
      store.updatedAt = conversationStoreNowIso();
      return next;
    }

    function conversationStoreUpsertAttachment(projectId, sessionId, attachment, opts = {}) {
      const src = (attachment && typeof attachment === "object") ? attachment : {};
      const aid = String(src.attachmentId || src.attachment_id || src.localId || src.local_id || src.filename || src.url || "").trim();
      const key = conversationStoreAttachmentKey(projectId, sessionId, aid);
      if (!key) return null;
      const store = ensureConversationStore();
      const prev = store.attachmentsByKey[key] || {};
      const next = {
        ...prev,
        ...src,
        attachmentId: aid,
        projectId: String(projectId || "").trim(),
        sessionId: String(sessionId || "").trim(),
        updatedAt: String(src.updatedAt || src.updated_at || prev.updatedAt || conversationStoreNowIso()),
        source: String((opts && opts.source) || src.source || prev.source || ""),
      };
      store.attachmentsByKey[key] = next;
      const messageKey = String((opts && opts.messageKey) || src.messageKey || src.message_key || "").trim();
      if (messageKey) conversationStorePutUnique(store.attachmentOrderByMessageKey, messageKey, key);
      const localId = String(next.localId || next.local_id || "").trim();
      if (localId) store.localAttachmentMap[conversationStoreAttachmentKey(projectId, sessionId, localId)] = key;
      store.updatedAt = conversationStoreNowIso();
      return next;
    }

    function conversationStoreSnapshot(projectId, sessionId) {
      const store = ensureConversationStore();
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      const skey = conversationStoreSessionKey(pid, sid);
      return {
        version: store.version,
        updatedAt: store.updatedAt,
        session: skey ? (store.sessionsByKey[skey] || null) : null,
        runs: skey ? (store.runOrderBySessionKey[skey] || []).map((key) => store.runsByKey[key]).filter(Boolean) : [],
        messages: skey ? (store.messageOrderBySessionKey[skey] || []).map((key) => store.messagesByKey[key]).filter(Boolean) : [],
      };
    }
