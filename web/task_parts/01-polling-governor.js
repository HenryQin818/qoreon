    const POLLING_GOVERNOR = {
      instanceId: "poll-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8),
      sessionLeaderKeyPrefix: "taskDashboard.sessionsPollLeader.v1::",
      sessionSnapshotKeyPrefix: "taskDashboard.sessionsPollSnapshot.v1::",
      sessionLeaderLeaseMs: 15000,
      sessionLeaderProjects: Object.create(null),
    };

    function isPollingVisibilityGovernorEnabled() {
      if (typeof readWindowFeatureFlag === "function") {
        return readWindowFeatureFlag(FEATURE_POLLING_VISIBILITY_GOVERNOR_KEY, true);
      }
      return true;
    }

    function isSessionsCrossTabLeaderEnabled() {
      if (typeof readWindowFeatureFlag === "function") {
        return readWindowFeatureFlag(FEATURE_SESSIONS_CROSS_TAB_LEADER_KEY, true);
      }
      return true;
    }

    function isPollingSchedulerEnabled() {
      if (typeof readWindowFeatureFlag === "function") {
        return readWindowFeatureFlag(FEATURE_POLLING_SCHEDULER_KEY, true);
      }
      return true;
    }

    function pollingGovernorPageHidden() {
      return !!(typeof document !== "undefined" && document.hidden);
    }

    function pollingGovernorPageFocused() {
      if (typeof document === "undefined" || typeof document.hasFocus !== "function") return false;
      try {
        return !!document.hasFocus();
      } catch (_) {
        return false;
      }
    }

    function pollingGovernorCurrentPageState() {
      return {
        hidden: pollingGovernorPageHidden(),
        visible: !pollingGovernorPageHidden(),
        hasFocus: pollingGovernorPageFocused(),
      };
    }

    function normalizePollingDelayMs(raw, fallback = 0) {
      const num = Number(raw);
      if (!Number.isFinite(num)) return Math.max(0, Number(fallback) || 0);
      return Math.max(0, num);
    }

    function stopManagedPollTimer(owner, fieldName) {
      if (!owner || !fieldName) return;
      if (owner[fieldName]) {
        clearTimeout(owner[fieldName]);
        owner[fieldName] = 0;
      }
    }

    function resolveManagedPollingDelay(requestedMs, opts = {}) {
      let delay = normalizePollingDelayMs(requestedMs, 0);
      if (!isPollingSchedulerEnabled()) return delay;
      const minMs = normalizePollingDelayMs(opts.minMs, 0);
      if (minMs > 0) delay = delay > 0 ? Math.max(delay, minMs) : minMs;
      if (pollingGovernorPageHidden() && isPollingVisibilityGovernorEnabled()) {
        if (opts.pauseWhenHidden) return 0;
        const hiddenMinMs = normalizePollingDelayMs(opts.hiddenMinMs, 0);
        if (hiddenMinMs > 0) delay = delay > 0 ? Math.max(delay, hiddenMinMs) : hiddenMinMs;
      }
      return delay;
    }

    function scheduleManagedPollTimer(owner, fieldName, requestedMs, callback, opts = {}) {
      stopManagedPollTimer(owner, fieldName);
      const delay = resolveManagedPollingDelay(requestedMs, opts);
      if (!(delay > 0) || typeof callback !== "function") return 0;
      owner[fieldName] = window.setTimeout(() => {
        owner[fieldName] = 0;
        callback();
      }, delay);
      return delay;
    }

    function pollingSessionFetchKey(projectId, channelName) {
      const pid = String(projectId || "").trim();
      const channel = String(channelName || "").trim();
      return pid + "::" + channel;
    }

    function sessionDirectoryLeaderStorageKey(projectId) {
      const pid = String(projectId || "").trim();
      return pid ? (POLLING_GOVERNOR.sessionLeaderKeyPrefix + pid) : "";
    }

    function sessionDirectorySnapshotStorageKey(projectId, channelName) {
      const key = pollingSessionFetchKey(projectId, channelName);
      return key ? (POLLING_GOVERNOR.sessionSnapshotKeyPrefix + key) : "";
    }

    function readLocalJsonStorage(key) {
      const storageKey = String(key || "").trim();
      if (!storageKey || typeof localStorage === "undefined") return null;
      try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === "object" ? parsed : null;
      } catch (_) {
        return null;
      }
    }

    function writeLocalJsonStorage(key, value, opts = {}) {
      const storageKey = String(key || "").trim();
      if (!storageKey || typeof localStorage === "undefined") return false;
      try {
        const text = JSON.stringify(value || {});
        const maxChars = normalizePollingDelayMs(opts.maxChars, 0);
        if (maxChars > 0 && text.length > maxChars) return false;
        localStorage.setItem(storageKey, text);
        return true;
      } catch (_) {
        return false;
      }
    }

    function shouldUseSessionDirectoryLeader(projectId, channelName, opts = {}) {
      const pid = String(projectId || "").trim();
      const channel = String(channelName || "").trim();
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      if (!pid || pid === "overview" || channel) return false;
      if (!!(opts && opts.force)) return false;
      if (!isSessionsCrossTabLeaderEnabled()) return false;
      if (typeof conversationProjectPollingHints === "function") {
        const policy = conversationProjectPollingHints(pid);
        if (!policy || !policy.enabled || !policy.cross_tab_dedupe_enabled) return false;
      }
      return source === "poll" || source === "resume";
    }

    function tryAcquireSessionDirectoryPollLeader(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return { isLeader: true, record: null };
      if (!isSessionsCrossTabLeaderEnabled()) return { isLeader: true, record: null };
      const storageKey = sessionDirectoryLeaderStorageKey(pid);
      const now = Date.now();
      const pageState = pollingGovernorCurrentPageState();
      const pageEligibleForLeadership = !!(pageState.visible && pageState.hasFocus);
      let leaseMs = normalizePollingDelayMs(POLLING_GOVERNOR.sessionLeaderLeaseMs, 15000) || 15000;
      let preferredFreshLeaderMs = 0;
      if (typeof conversationProjectPollingHints === "function") {
        const hints = conversationProjectPollingHints(pid);
        if (hints && hints.enabled) {
          const policyIntervalMs = normalizePollingDelayMs(hints.poll_interval_ms, 0);
          if (policyIntervalMs > 0) {
            // 保持 lease 明显长于单次 poll 周期，但不要让失效主标签长期霸占 leader。
            leaseMs = Math.max(policyIntervalMs * 3, 6000);
            preferredFreshLeaderMs = Math.max(policyIntervalMs * 2, 4000);
          }
        }
      }
      const current = readLocalJsonStorage(storageKey);
      const currentOwner = String(current && current.owner || "").trim();
      const expiresAt = Number(current && current.expires_at_ms || 0);
      const currentUpdatedAtMs = Number(
        (current && current.updated_at_ms)
        || (current && current.updatedAtMs)
        || Date.parse(String((current && current.updated_at) || (current && current.updatedAt) || ""))
        || 0
      );
      if (!pageEligibleForLeadership) {
        if (currentOwner === POLLING_GOVERNOR.instanceId) {
          releaseSessionDirectoryPollLeader(pid);
        }
        pushPollingTrace("sessions.leader", {
          project_id: pid,
          state: "skip-ineligible",
          visible: !!pageState.visible,
          focused: !!pageState.hasFocus,
          current_owner: currentOwner,
        });
        return { isLeader: false, record: current };
      }
      const currentVisible = !!(current && current.visible);
      const currentHasFocus = !!(current && (current.has_focus || current.hasFocus));
      const canPreemptForVisibility = (
        pageState.visible
        && pageState.hasFocus
        && currentOwner
        && currentOwner !== POLLING_GOVERNOR.instanceId
        && (!currentVisible || !currentHasFocus)
      );
      const canPreemptForStaleLeader = (
        pageState.visible
        && pageState.hasFocus
        && preferredFreshLeaderMs > 0
        && currentOwner
        && currentOwner !== POLLING_GOVERNOR.instanceId
        && currentUpdatedAtMs > 0
        && (now - currentUpdatedAtMs) > preferredFreshLeaderMs
      );
      const reusable = (
        !currentOwner
        || expiresAt <= now
        || currentOwner === POLLING_GOVERNOR.instanceId
        || canPreemptForVisibility
        || canPreemptForStaleLeader
      );
      if (!reusable) {
        pushPollingTrace("sessions.leader", {
          project_id: pid,
          state: "follower",
          visible: !!pageState.visible,
          focused: !!pageState.hasFocus,
          current_owner: currentOwner,
          current_visible: currentVisible,
          current_focused: currentHasFocus,
        });
        return { isLeader: false, record: current };
      }
      const next = {
        owner: POLLING_GOVERNOR.instanceId,
        project_id: pid,
        updated_at_ms: now,
        updated_at: new Date(now).toISOString(),
        expires_at_ms: now + leaseMs,
        visible: !!pageState.visible,
        has_focus: !!pageState.hasFocus,
      };
      writeLocalJsonStorage(storageKey, next);
      const confirmed = readLocalJsonStorage(storageKey) || next;
      const confirmedOwner = String(confirmed && confirmed.owner || "").trim();
      const confirmedExpiresAt = Number(confirmed && confirmed.expires_at_ms || 0);
      const isLeader = confirmedOwner === POLLING_GOVERNOR.instanceId && confirmedExpiresAt > now;
      if (isLeader) POLLING_GOVERNOR.sessionLeaderProjects[pid] = true;
      pushPollingTrace("sessions.leader", {
        project_id: pid,
        state: isLeader ? "leader" : "lost-after-write",
        visible: !!pageState.visible,
        focused: !!pageState.hasFocus,
        can_preempt_visibility: !!canPreemptForVisibility,
        can_preempt_stale: !!canPreemptForStaleLeader,
        lease_ms: leaseMs,
        preferred_fresh_leader_ms: preferredFreshLeaderMs,
      });
      return { isLeader, record: confirmed };
    }

    function releaseSessionDirectoryPollLeader(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid || typeof localStorage === "undefined") return;
      const storageKey = sessionDirectoryLeaderStorageKey(pid);
      const current = readLocalJsonStorage(storageKey);
      if (!current) return;
      if (String(current.owner || "").trim() !== POLLING_GOVERNOR.instanceId) return;
      try {
        localStorage.removeItem(storageKey);
      } catch (_) {}
      delete POLLING_GOVERNOR.sessionLeaderProjects[pid];
    }

    function releaseAllSessionDirectoryPollLeaders() {
      Object.keys(POLLING_GOVERNOR.sessionLeaderProjects || {}).forEach((projectId) => {
        releaseSessionDirectoryPollLeader(projectId);
      });
    }

    function publishSessionDirectorySnapshot(projectId, channelName, sessions, meta = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return false;
      const storageKey = sessionDirectorySnapshotStorageKey(pid, channelName);
      if (!storageKey) return false;
      const safeSessions = Array.isArray(sessions) ? sessions : [];
      const loadedAtMs = normalizePollingDelayMs(meta.loadedAtMs, Date.now()) || Date.now();
      const pollingHints = (meta && meta.pollingHints && typeof meta.pollingHints === "object")
        ? meta.pollingHints
        : null;
      const perfGovernance = (meta && meta.perfGovernance && typeof meta.perfGovernance === "object")
        ? meta.perfGovernance
        : null;
      const ok = writeLocalJsonStorage(storageKey, {
        owner: POLLING_GOVERNOR.instanceId,
        project_id: pid,
        channel_name: String(channelName || "").trim(),
        loaded_at_ms: loadedAtMs,
        loaded_at: new Date(loadedAtMs).toISOString(),
        polling_hints: pollingHints,
        perf_governance: perfGovernance,
        sessions: safeSessions,
      }, { maxChars: 1_500_000 });
      pushPollingTrace("sessions.snapshot.publish", {
        project_id: pid,
        channel_name: String(channelName || "").trim(),
        session_count: safeSessions.length,
        loaded_at_ms: loadedAtMs,
        ok: !!ok,
        has_polling_hints: !!pollingHints,
        has_perf_governance: !!perfGovernance,
      });
      return ok;
    }

    function readSessionDirectorySnapshot(projectId, channelName, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return null;
      const storageKey = sessionDirectorySnapshotStorageKey(pid, channelName);
      if (!storageKey) return null;
      const payload = readLocalJsonStorage(storageKey);
      if (!payload) return null;
      const loadedAtMs = Number(payload.loaded_at_ms || 0);
      const maxAgeMs = normalizePollingDelayMs(opts.maxAgeMs, 0);
      if (maxAgeMs > 0 && loadedAtMs > 0 && (Date.now() - loadedAtMs) > maxAgeMs) return null;
      const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
      return {
        loadedAtMs,
        pollingHints: (payload.polling_hints && typeof payload.polling_hints === "object")
          ? payload.polling_hints
          : null,
        perfGovernance: (payload.perf_governance && typeof payload.perf_governance === "object")
          ? payload.perf_governance
          : null,
        sessions: sessions.slice(),
      };
    }

    function applySessionDirectorySnapshotCacheFromStorageEvent(key, rawValue) {
      const storageKey = String(key || "").trim();
      if (!storageKey || storageKey.indexOf(POLLING_GOVERNOR.sessionSnapshotKeyPrefix) !== 0) return false;
      if (typeof ensureConversationSessionDirectoryStateMaps !== "function") return false;
      if (typeof rawValue !== "string" || !rawValue.trim()) return false;
      let payload = null;
      try {
        payload = JSON.parse(rawValue);
      } catch (_) {
        return false;
      }
      if (!payload || typeof payload !== "object") return false;
      const projectId = String(payload.project_id || "").trim();
      const channelName = String(payload.channel_name || "").trim();
      const fetchKey = pollingSessionFetchKey(projectId, channelName);
      if (!projectId || !fetchKey) return false;
      const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
      const loadedAtMs = Number(payload.loaded_at_ms || Date.now()) || Date.now();
      if (typeof updateConversationProjectPollingMeta === "function") {
        try {
          updateConversationProjectPollingMeta(projectId, {
            polling_hints: payload.polling_hints,
            perf_governance: payload.perf_governance,
          }, {
            source: "storage-snapshot",
            loadedAt: new Date(loadedAtMs).toISOString(),
          });
        } catch (_) {}
      }
      ensureConversationSessionDirectoryStateMaps();
      PCONV.sessionFetchCacheByKey[fetchKey] = {
        loadedAt: loadedAtMs,
        sessions: sessions.slice(),
        source: "storage-snapshot",
      };
      pushPollingTrace("sessions.snapshot.consume", {
        project_id: projectId,
        channel_name: channelName,
        source: "storage-event",
        session_count: sessions.length,
        loaded_at_ms: loadedAtMs,
        has_polling_hints: !!(payload && payload.polling_hints),
        has_perf_governance: !!(payload && payload.perf_governance),
      });
      return true;
    }

    if (typeof window !== "undefined") {
      window.addEventListener("storage", (ev) => {
        applySessionDirectorySnapshotCacheFromStorageEvent(ev && ev.key, ev && ev.newValue);
      });
      window.addEventListener("pagehide", releaseAllSessionDirectoryPollLeaders);
      window.addEventListener("beforeunload", releaseAllSessionDirectoryPollLeaders);
    }
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) releaseAllSessionDirectoryPollLeaders();
      });
    }
