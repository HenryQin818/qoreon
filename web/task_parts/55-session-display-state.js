    function normalizeSessionDisplayState(raw, fallback = "idle") {
      return normalizeDisplayState(raw, fallback);
    }

    function normalizeAgentNameState(raw, fallback = "identity_unresolved") {
      const s = String(raw || "").trim().toLowerCase();
      if (
        s === "resolved"
        || s === "polluted"
        || s === "name_missing"
        || s === "identity_unresolved"
        || s === "identity_pending"
      ) {
        return s;
      }
      return String(fallback || "").trim().toLowerCase();
    }

    function agentNameStateLabel(rawState, issue = "") {
      const state = normalizeAgentNameState(rawState, "");
      if (state === "resolved") return "";
      if (state === "polluted") return "名称异常";
      if (state === "identity_pending") return "身份解析中";
      if (state === "name_missing" || state === "identity_unresolved") return "身份未解析";
      const issueText = String(issue || "").trim().toLowerCase();
      if (issueText.indexOf("polluted") >= 0) return "名称异常";
      return "";
    }

    function compactAgentDisplayId(value) {
      const text = String(value || "").trim();
      if (!text) return "";
      return text.replace(/[^0-9a-z]/ig, "").slice(0, 8).toLowerCase();
    }

    function isSessionDerivedAgentDisplayName(value, session) {
      const text = String(value || "").trim();
      if (!text) return false;
      if (/^(?:会话|session)\s*[0-9a-f-]{4,}$/i.test(text)) return true;
      if (looksLikeSessionId(text)) return true;
      const sid = String(getSessionId(session) || "").trim();
      if (!sid) return false;
      const compactSid = compactAgentDisplayId(sid);
      const compactText = compactAgentDisplayId(text);
      if (text === sid) return true;
      if (compactText && compactSid && compactText === compactSid) return true;
      if (compactText && compactText.length >= 4 && compactSid.indexOf(compactText) >= 0) return true;
      return false;
    }

    function hasAgentDisplayContractFields(session) {
      const s = (session && typeof session === "object") ? session : {};
      return [
        "agent_display_name",
        "agentDisplayName",
        "agent_display_name_source",
        "agentDisplayNameSource",
        "agent_name_state",
        "agentNameState",
        "agent_display_issue",
        "agentDisplayIssue",
      ].some((key) => Object.prototype.hasOwnProperty.call(s, key));
    }

    function readAgentDisplayContract(session) {
      const s = (session && typeof session === "object") ? session : {};
      const registry = (s.agent_registry && typeof s.agent_registry === "object") ? s.agent_registry : {};
      const rawName = String(firstNonEmptyText([
        s.agent_display_name,
        s.agentDisplayName,
        s.agent_name,
        s.agentName,
        registry.alias,
        registry.agent_name,
        registry.agentName,
        registry.name,
      ]) || "").trim();
      const issue = String(firstNonEmptyText([
        s.agent_display_issue,
        s.agentDisplayIssue,
      ]) || "").trim().toLowerCase();
      let state = normalizeAgentNameState(firstNonEmptyText([
        s.agent_name_state,
        s.agentNameState,
      ]), "");
      if (!state) {
        if (issue.indexOf("polluted") >= 0) state = "polluted";
        else if (rawName && !isSessionDerivedAgentDisplayName(rawName, s)) state = "resolved";
        else if (hasAgentDisplayContractFields(s)) state = "identity_unresolved";
      }
      const name = state === "resolved" && !isSessionDerivedAgentDisplayName(rawName, s) ? rawName : "";
      return {
        name,
        source: String(firstNonEmptyText([
          s.agent_display_name_source,
          s.agentDisplayNameSource,
        ]) || "").trim(),
        state,
        issue,
        hasContractFields: hasAgentDisplayContractFields(s),
      };
    }

    function fallbackAgentIdentityName(session) {
      const s = (session && typeof session === "object") ? session : {};
      const registry = (s.agent_registry && typeof s.agent_registry === "object") ? s.agent_registry : {};
      const candidates = [
        registry.alias,
        registry.agent_name,
        registry.agentName,
        registry.name,
        s.agent_name,
        s.agentName,
        s.alias,
      ];
      for (const candidate of candidates) {
        const text = String(candidate || "").trim();
        if (!text) continue;
        if (text === String(getSessionChannelName(s) || "").trim()) continue;
        if (isSessionDerivedAgentDisplayName(text, s)) continue;
        return text;
      }
      return "";
    }

    function resolveAgentDisplayName(session) {
      const contract = readAgentDisplayContract(session);
      if (contract.state === "resolved" && contract.name) return contract.name;
      return fallbackAgentIdentityName(session);
    }

    function getConversationListMetrics(session) {
      const s = (session && typeof session === "object") ? session : {};
      const raw = s.conversation_list_metrics || s.conversationListMetrics || null;
      return (raw && typeof raw === "object") ? raw : null;
    }

    function getConversationListTaskCounts(session) {
      const metrics = getConversationListMetrics(session);
      const counts = (metrics && typeof metrics.task_counts === "object") ? metrics.task_counts : {};
      const total = Math.max(0, Number(firstNonEmptyText([counts.total, 0])) || 0);
      const current = Math.max(0, Number(firstNonEmptyText([counts.current, 0])) || 0);
      const inProgress = Math.max(0, Number(firstNonEmptyText([counts.in_progress, counts.inProgress, 0])) || 0);
      const pending = Math.max(0, Number(firstNonEmptyText([counts.pending, 0])) || 0);
      if (!total && !current && !inProgress && !pending) return null;
      return {
        total,
        current,
        in_progress: inProgress,
        pending,
      };
    }

    function getConversationListCurrentTaskSummary(session) {
      const metrics = getConversationListMetrics(session);
      const summary = (metrics && typeof metrics.current_task_summary === "object") ? metrics.current_task_summary : {};
      const statusText = String(summary.task_primary_status || "").trim();
      const bucketText = String(summary.status_bucket || summary.statusBucket || "").trim();
      const resolveStatus = (typeof resolveTaskPrimaryStatusText === "function")
        ? resolveTaskPrimaryStatusText
        : ((value, fallback = "") => {
          const raw = String(value || "").trim();
          if (!raw) return String(fallback || "").trim();
          if (/(?:进行中|处理中|running|in[_-]?progress)/i.test(raw)) return "进行中";
          if (/(?:待办|待开始|待处理|todo|pending|queued)/i.test(raw)) return "待办";
          if (/(?:已完成|完成|done|success)/i.test(raw)) return "已完成";
          return String(fallback || raw).trim();
        });
      const taskPrimaryStatus = resolveStatus(statusText || bucketText, statusText || bucketText);
      if (
        !String(summary.task_id || summary.taskId || "").trim()
        && !String(summary.task_title || summary.taskTitle || "").trim()
        && !taskPrimaryStatus
      ) {
        return null;
      }
      return {
        task_id: String(firstNonEmptyText([summary.task_id, summary.taskId]) || "").trim(),
        task_title: String(firstNonEmptyText([summary.task_title, summary.taskTitle]) || "").trim(),
        task_path: String(firstNonEmptyText([summary.task_path, summary.taskPath]) || "").trim(),
        task_primary_status: taskPrimaryStatus,
        status_bucket: bucketText,
      };
    }

    function normalizeConversationListMetricBadge(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const state = String(firstNonEmptyText([src.state, src.status_bucket, src.statusBucket]) || "").trim();
      const resolveStatus = (typeof resolveTaskPrimaryStatusText === "function")
        ? resolveTaskPrimaryStatusText
        : ((value, fallback = "") => String(value || fallback || "").trim());
      const normalizedLabel = resolveStatus(firstNonEmptyText([src.label, state]), firstNonEmptyText([src.label, state]));
      return {
        kind: String(src.kind || "").trim(),
        state,
        label: String(normalizedLabel || "").trim(),
        severity: String(firstNonEmptyText([src.severity, src.tone]) || "").trim().toLowerCase(),
        count: Math.max(0, Number(firstNonEmptyText([src.count, 0])) || 0),
      };
    }

    function conversationListMetricBadges(session) {
      const metrics = getConversationListMetrics(session);
      const badges = Array.isArray(metrics && metrics.status_badges) ? metrics.status_badges : [];
      return badges.map(normalizeConversationListMetricBadge).filter((item) => item && item.label);
    }

    function conversationListMetricBadgeTone(badge) {
      const item = normalizeConversationListMetricBadge(badge);
      if (item.severity === "danger" || item.severity === "error") return "error";
      if (item.severity === "warning" || item.severity === "warn") return "warning";
      if (item.severity === "success") return "success";
      if (item.state === "in_progress") return "running";
      if (item.state === "pending") return "queued";
      if (item.state === "done") return "success";
      return "info";
    }

    function pickConversationListPrimaryStatusBadge(session) {
      const badges = conversationListMetricBadges(session);
      if (!badges.length) return null;
      return badges.find((item) => item.kind === "current_task") || badges[0];
    }

    function conversationListMetricBadgeStatusMeta(session) {
      const badge = pickConversationListPrimaryStatusBadge(session);
      if (!badge) return null;
      return {
        text: String(badge.label || "").trim(),
        tone: conversationListMetricBadgeTone(badge),
        title: String(badge.label || "").trim(),
        source: "conversation_list_metrics",
      };
    }

    function conversationListCurrentTaskSummaryMeta(session) {
      const summary = getConversationListCurrentTaskSummary(session);
      if (!summary || !summary.task_primary_status) return null;
      return {
        text: String(summary.task_primary_status || "").trim(),
        tone: /已完成/.test(String(summary.task_primary_status || "")) ? "success" : "info",
        title: String(firstNonEmptyText([summary.task_title, summary.task_path, summary.task_primary_status]) || "").trim(),
        source: "conversation_list_metrics",
      };
    }

    function conversationListDetailHydrationCanSkip(session) {
      const metrics = getConversationListMetrics(session);
      const detail = (metrics && typeof metrics.detail_hydration === "object") ? metrics.detail_hydration : {};
      return !!detail.can_skip_detail_for_list;
    }

    function normalizeLatestRunSummary(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return {
        run_id: String(firstNonEmptyText([src.run_id, src.runId]) || "").trim(),
        status: normalizeSessionDisplayState(firstNonEmptyText([src.status, src.display_state, src.displayState]), "idle"),
        updated_at: String(firstNonEmptyText([src.updated_at, src.updatedAt, src.finished_at, src.finishedAt, src.created_at, src.createdAt]) || "").trim(),
        preview: String(firstNonEmptyText([src.preview, src.last_preview, src.lastPreview]) || "").trim(),
        speaker: String(firstNonEmptyText([src.speaker, src.last_speaker, src.lastSpeaker]) || "assistant").trim() || "assistant",
        sender_type: String(firstNonEmptyText([src.sender_type, src.senderType, src.last_sender_type, src.lastSenderType]) || "").trim(),
        sender_name: String(firstNonEmptyText([src.sender_name, src.senderName, src.last_sender_name, src.lastSenderName]) || "").trim(),
        sender_source: String(firstNonEmptyText([src.sender_source, src.senderSource, src.last_sender_source, src.lastSenderSource]) || "").trim(),
        latest_user_msg: String(firstNonEmptyText([src.latest_user_msg, src.latestUserMsg]) || "").trim(),
        latest_ai_msg: String(firstNonEmptyText([src.latest_ai_msg, src.latestAiMsg]) || "").trim(),
        error: String(firstNonEmptyText([src.error, src.last_error, src.lastError]) || "").trim(),
        run_count: Math.max(0, Number(firstNonEmptyText([src.run_count, src.runCount, 0])) || 0),
      };
    }

    function normalizeSessionHealthState(raw, fallback = "") {
      const s = String(raw || "").trim().toLowerCase();
      if (s === "healthy" || s === "busy" || s === "blocked" || s === "recovering" || s === "attention") {
        return s;
      }
      return String(fallback || "").trim().toLowerCase();
    }

    function normalizeRunOutcomeState(raw, fallback = "") {
      const s = String(raw || "").trim().toLowerCase();
      if (
        s === "success"
        || s === "interrupted_infra"
        || s === "interrupted_user"
        || s === "failed_config"
        || s === "failed_business"
        || s === "recovered_notice"
      ) {
        return s;
      }
      return String(fallback || "").trim().toLowerCase();
    }

    function normalizeRunErrorClass(raw, fallback = "") {
      const s = String(raw || "").trim().toLowerCase();
      if (
        s === "infra_restart"
        || s === "infra_restart_recovered"
        || s === "session_binding"
        || s === "workspace_permission"
        || s === "cli_path"
      ) {
        return s;
      }
      return String(fallback || "").trim().toLowerCase();
    }

    function normalizeLatestEffectiveRunSummary(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return {
        run_id: String(firstNonEmptyText([src.run_id, src.runId]) || "").trim(),
        outcome_state: normalizeRunOutcomeState(firstNonEmptyText([src.outcome_state, src.outcomeState]), ""),
        preview: String(firstNonEmptyText([src.preview, src.last_preview, src.lastPreview]) || "").trim(),
        created_at: String(firstNonEmptyText([src.created_at, src.createdAt, src.updated_at, src.updatedAt]) || "").trim(),
      };
    }

    function getSessionLatestRunSummary(session) {
      const s = (session && typeof session === "object") ? session : {};
      return normalizeLatestRunSummary(s.latest_run_summary || s.latestRunSummary || null);
    }

    function getSessionHealthState(session) {
      const s = (session && typeof session === "object") ? session : {};
      return normalizeSessionHealthState(
        firstNonEmptyText([s.session_health_state, s.sessionHealthState]),
        ""
      );
    }

    function getSessionLatestEffectiveRunSummary(session) {
      const s = (session && typeof session === "object") ? session : {};
      return normalizeLatestEffectiveRunSummary(
        s.latest_effective_run_summary || s.latestEffectiveRunSummary || null
      );
    }

    function getSessionPrimaryPreviewText(session) {
      const s = (session && typeof session === "object") ? session : {};
      const displayState = String(getSessionDisplayState(s) || "").trim().toLowerCase();
      const latestEffectiveRunSummary = getSessionLatestEffectiveRunSummary(s);
      const latestRunSummary = getSessionLatestRunSummary(s);
      if (
        displayState === "running"
        || displayState === "queued"
        || displayState === "retry_waiting"
        || displayState === "external_busy"
      ) {
        return String(firstNonEmptyText([
          latestRunSummary.preview,
          s.lastPreview,
          latestEffectiveRunSummary.preview,
        ]) || "").trim();
      }
      return String(firstNonEmptyText([
        latestEffectiveRunSummary.preview,
        s.lastPreview,
        latestRunSummary.preview,
      ]) || "").trim();
    }

    function sessionUsesSyntheticPreviewSender(session, previewText = "") {
      const s = (session && typeof session === "object") ? session : {};
      const latestEffectiveRunSummary = getSessionLatestEffectiveRunSummary(s);
      const latestRunSummary = getSessionLatestRunSummary(s);
      const effectivePreview = String(latestEffectiveRunSummary.preview || "").trim();
      const currentPreview = String(previewText || "").trim();
      if (!effectivePreview) return false;
      if (currentPreview && currentPreview !== effectivePreview) return false;
      const effectiveRunId = String(latestEffectiveRunSummary.run_id || "").trim();
      const latestRunId = String(latestRunSummary.run_id || "").trim();
      const latestSenderType = String(latestRunSummary.sender_type || "").trim().toLowerCase();
      return (
        (effectiveRunId && latestRunId && effectiveRunId !== latestRunId)
        || latestSenderType === "system"
      );
    }

    function getSessionDisplayState(session) {
      const s = (session && typeof session === "object") ? session : {};
      const raw = firstNonEmptyText([
        s.session_display_state,
        s.sessionDisplayState,
      ]);
      const runtimeState = getSessionRuntimeState(s);
      const rawState = normalizeSessionDisplayState(raw, "");
      const runtimeDisplay = normalizeSessionDisplayState(runtimeState.display_state, "idle");
      const latestRunSummary = getSessionLatestRunSummary(s);
      const sessionHealthState = getSessionHealthState(s);
      const latestEffectiveRunSummary = getSessionLatestEffectiveRunSummary(s);
      const latestEffectiveOutcomeState = normalizeRunOutcomeState(latestEffectiveRunSummary.outcome_state, "");
      const latestStatus = normalizeSessionDisplayState(latestRunSummary.status, "");
      const isActiveLike = (one) => (
        one === "running"
        || one === "queued"
        || one === "retry_waiting"
        || one === "external_busy"
      );

      // 运行时显式态优先，避免旧的 session_display_state 把已恢复/已中断会话继续显示成处理中。
      if (runtimeDisplay === "error" || isActiveLike(runtimeDisplay)) return runtimeDisplay;
      if (runtimeState.active_run_id) return "running";
      if (runtimeState.queued_run_id) return "queued";
      if (sessionHealthState === "busy") {
        if (isActiveLike(latestStatus)) return latestStatus;
        return "running";
      }
      if (sessionHealthState === "recovering") return "retry_waiting";
      if (sessionHealthState === "blocked") return "error";
      if (sessionHealthState === "attention") {
        if (latestEffectiveOutcomeState === "interrupted_infra" || latestEffectiveOutcomeState === "interrupted_user") {
          return "interrupted";
        }
        if (latestEffectiveOutcomeState === "failed_config" || latestEffectiveOutcomeState === "failed_business") {
          return "error";
        }
      }

      if (isExplicitIdleRuntimeState(runtimeState)) {
        if (isActiveLike(rawState)) {
          if (latestStatus === "done" || latestStatus === "error") return latestStatus;
          return "idle";
        }
        if (rawState === "done" || rawState === "error") return rawState;
        if (latestStatus === "done" || latestStatus === "error") return latestStatus;
        return "idle";
      }

      if (rawState) return rawState;
      if (latestStatus === "done" || latestStatus === "error") return latestStatus;
      return runtimeDisplay;
    }

    function getSessionDisplayReason(session) {
      const s = (session && typeof session === "object") ? session : {};
      return String(firstNonEmptyText([s.session_display_reason, s.sessionDisplayReason]) || "").trim();
    }

    function isLatestRunSummaryTerminal(summary) {
      const latest = normalizeLatestRunSummary(summary);
      return latest.status === "done" || latest.status === "error";
    }

    function latestRunSummaryUpdatedAt(session) {
      return String(getSessionLatestRunSummary(session).updated_at || "").trim();
    }
