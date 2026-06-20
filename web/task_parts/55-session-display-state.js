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

    function agentIdentityExplanationMeta(session) {
      const s = (session && typeof session === "object") ? session : {};
      const contract = readAgentDisplayContract(s);
      const state = normalizeAgentNameState(contract.state, "");
      const issue = String(contract.issue || "").trim().toLowerCase();
      if (state !== "identity_unresolved" && state !== "name_missing") return null;
      const channelName = String(getSessionChannelName(s) || s.channel_name || s.channelName || s.primaryChannel || "").trim();
      const sessionId = String(getSessionId(s) || s.session_id || s.sessionId || s.id || "").trim();
      const missingItems = state === "name_missing"
        ? ["可展示 Agent 名称"]
        : ["alias / purpose / Agent 可读身份"];
      const suggestions = state === "name_missing"
        ? ["补充 alias 或 agent_name 后刷新身份"]
        : ["补 alias/purpose，或重新生成该 Agent 身份"];
      return {
        key: "identity_unresolved",
        tone: "warn",
        heading: "Agent 可读身份缺失或不可用",
        body: "发生什么：系统没有解析到稳定的 Agent 可读身份；影响：列表、@ 协同对象和回执来源只能显示“身份未解析”，容易影响派发判断；怎么修：补齐 alias/purpose，或重新生成该 Agent 身份后刷新。",
        title: [
          "状态: " + (state || "identity_unresolved"),
          issue ? ("问题: " + issue) : "",
          channelName ? ("通道: " + channelName) : "",
          sessionId ? ("session: " + sessionId) : "",
        ].filter(Boolean).join("\n"),
        chips: ["身份未解析", state || "identity_unresolved"].filter(Boolean),
        missingItems,
        suggestions,
        details: [
          { label: "发生什么", text: "系统没有解析到稳定的 Agent 可读身份。" },
          { label: "影响什么", text: "列表、@ 协同对象和回执来源只能显示“身份未解析”，容易影响派发判断。" },
          { label: "怎么修", text: suggestions.join("；") },
        ],
      };
    }

    function agentDisplayTooltip(session, fallback = "-") {
      const resolved = String(resolveAgentDisplayName(session) || "").trim();
      const contract = readAgentDisplayContract(session);
      const stateLabel = String(agentNameStateLabel(contract.state, contract.issue) || "").trim();
      const title = String(resolved || stateLabel || fallback || "-").trim() || "-";
      const explanation = agentIdentityExplanationMeta(session);
      if (!explanation) return title;
      const missing = (Array.isArray(explanation.missingItems) ? explanation.missingItems : [])
        .map((item) => String(item || "").trim())
        .filter(Boolean)
        .join("、");
      const suggestions = (Array.isArray(explanation.suggestions) ? explanation.suggestions : [])
        .map((item) => String(item || "").trim())
        .filter(Boolean)
        .join("；");
      return [
        title,
        explanation.body,
        missing ? ("缺失项: " + missing) : "",
        suggestions ? ("修复建议: " + suggestions) : "",
      ].filter(Boolean).join("\n");
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

    function normalizeRunSummaryBool(value) {
      if (typeof value === "boolean") return value;
      if (typeof value === "number") return value !== 0;
      const text = String(value == null ? "" : value).trim().toLowerCase();
      return text === "1" || text === "true" || text === "yes" || text === "y";
    }

    function normalizeLatestRunSummary(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const providerError = (src.provider_error && typeof src.provider_error === "object")
        ? src.provider_error
        : (src.providerError && typeof src.providerError === "object" ? src.providerError : null);
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
        error_class: typeof normalizeRunErrorClass === "function"
          ? normalizeRunErrorClass(firstNonEmptyText([src.error_class, src.errorClass]), "")
          : String(firstNonEmptyText([src.error_class, src.errorClass]) || "").trim().toLowerCase(),
        failure_class: String(firstNonEmptyText([src.failure_class, src.failureClass]) || "").trim().toLowerCase(),
        provider_error: providerError ? {
          kind: String(firstNonEmptyText([providerError.kind, providerError.error_kind, providerError.errorKind]) || "").trim(),
          retryable: normalizeRunSummaryBool(providerError.retryable),
          matched_patterns: Array.isArray(providerError.matched_patterns)
            ? providerError.matched_patterns.map((item) => String(item || "").trim()).filter(Boolean)
            : Array.isArray(providerError.matchedPatterns)
              ? providerError.matchedPatterns.map((item) => String(item || "").trim()).filter(Boolean)
              : [],
        } : {},
        side_effect_risk: String(firstNonEmptyText([src.side_effect_risk, src.sideEffectRisk]) || "").trim().toLowerCase(),
        recovery_mode: String(firstNonEmptyText([src.recovery_mode, src.recoveryMode]) || "").trim().toLowerCase(),
        recovery_required: normalizeRunSummaryBool(firstNonEmptyText([src.recovery_required, src.recoveryRequired, false])),
        retry_exhausted: normalizeRunSummaryBool(firstNonEmptyText([src.retry_exhausted, src.retryExhausted, false])),
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
        || s === "provider_transient_failed"
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
        || s === "provider_transient"
      ) {
        return s;
      }
      return String(fallback || "").trim().toLowerCase();
    }

    function normalizeLatestEffectiveRunSummary(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      const providerError = (src.provider_error && typeof src.provider_error === "object")
        ? src.provider_error
        : (src.providerError && typeof src.providerError === "object" ? src.providerError : null);
      return {
        run_id: String(firstNonEmptyText([src.run_id, src.runId]) || "").trim(),
        outcome_state: normalizeRunOutcomeState(firstNonEmptyText([src.outcome_state, src.outcomeState]), ""),
        preview: String(firstNonEmptyText([src.preview, src.last_preview, src.lastPreview]) || "").trim(),
        error: String(firstNonEmptyText([src.error, src.last_error, src.lastError]) || "").trim(),
        created_at: String(firstNonEmptyText([src.created_at, src.createdAt, src.updated_at, src.updatedAt]) || "").trim(),
        error_class: typeof normalizeRunErrorClass === "function"
          ? normalizeRunErrorClass(firstNonEmptyText([src.error_class, src.errorClass]), "")
          : String(firstNonEmptyText([src.error_class, src.errorClass]) || "").trim().toLowerCase(),
        failure_class: String(firstNonEmptyText([src.failure_class, src.failureClass]) || "").trim().toLowerCase(),
        provider_error: providerError ? {
          kind: String(firstNonEmptyText([providerError.kind, providerError.error_kind, providerError.errorKind]) || "").trim(),
          retryable: normalizeRunSummaryBool(providerError.retryable),
          matched_patterns: Array.isArray(providerError.matched_patterns)
            ? providerError.matched_patterns.map((item) => String(item || "").trim()).filter(Boolean)
            : Array.isArray(providerError.matchedPatterns)
              ? providerError.matchedPatterns.map((item) => String(item || "").trim()).filter(Boolean)
              : [],
        } : {},
        side_effect_risk: String(firstNonEmptyText([src.side_effect_risk, src.sideEffectRisk]) || "").trim().toLowerCase(),
        recovery_mode: String(firstNonEmptyText([src.recovery_mode, src.recoveryMode]) || "").trim().toLowerCase(),
        recovery_required: normalizeRunSummaryBool(firstNonEmptyText([src.recovery_required, src.recoveryRequired, false])),
        retry_exhausted: normalizeRunSummaryBool(firstNonEmptyText([src.retry_exhausted, src.retryExhausted, false])),
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
      const latestRunId = String(latestRunSummary.run_id || "").trim();
      const latestEffectiveRunId = String(latestEffectiveRunSummary.run_id || "").trim();
      const latestRunSupersedesEffective = !!(latestRunId && latestEffectiveRunId && latestRunId !== latestEffectiveRunId);
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
        if (isActiveLike(latestStatus)) return latestStatus;
        if (latestStatus === "done" || latestEffectiveOutcomeState === "success") return "done";
        if (latestRunSupersedesEffective && (latestStatus === "error" || latestStatus === "done")) return latestStatus;
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

    function sessionBindingErrorClassMatches(raw) {
      const normalized = normalizeRunErrorClass(raw, "");
      return normalized === "session_binding" || String(raw || "").trim().toLowerCase() === "session_binding";
    }

    function sessionBindingErrorTextMatches(raw) {
      const text = String(raw || "").trim().toLowerCase();
      if (!text) return false;
      return (
        text.indexOf("no conversation found with session id") >= 0
        || text.indexOf("session_binding") >= 0
        || text.indexOf("session binding") >= 0
        || /conversation\s+(?:not\s+found|missing|lost)/i.test(text)
      );
    }

    function conversationCliTypeForSession(session) {
      const s = (session && typeof session === "object") ? session : {};
      return String(firstNonEmptyText([
        s.cli_type,
        s.cliType,
        s.primary_cli_type,
        s.primaryCliType,
      ]) || "codex").trim().toLowerCase() || "codex";
    }

    function conversationSessionBindingBlockMeta(session) {
      const s = (session && typeof session === "object") ? session : {};
      if (!s || !Object.keys(s).length) return null;
      const latestRunSummary = getSessionLatestRunSummary(s);
      const latestEffectiveRunSummary = getSessionLatestEffectiveRunSummary(s);
      const sessionHealthState = getSessionHealthState(s);
      const displayState = getSessionDisplayState(s);
      const latestOutcomeState = normalizeRunOutcomeState(latestEffectiveRunSummary.outcome_state, "");
      const latestStatus = normalizeSessionDisplayState(latestRunSummary.status, "");
      const classes = [
        s.error_class,
        s.errorClass,
        s.failure_class,
        s.failureClass,
        latestRunSummary.error_class,
        latestRunSummary.failure_class,
        latestEffectiveRunSummary.error_class,
        latestEffectiveRunSummary.failure_class,
      ];
      const textCandidates = [
        s.error,
        s.last_error,
        s.lastError,
        s.session_display_reason,
        s.sessionDisplayReason,
        s.status_reason,
        s.statusReason,
        latestRunSummary.error,
        latestRunSummary.preview,
        latestEffectiveRunSummary.error,
        latestEffectiveRunSummary.preview,
      ];
      const hasBindingClass = classes.some(sessionBindingErrorClassMatches);
      const hasBindingText = textCandidates.some(sessionBindingErrorTextMatches);
      const isErrorLike = (
        sessionHealthState === "blocked"
        || displayState === "error"
        || latestOutcomeState === "failed_config"
        || latestStatus === "error"
      );
      if (!hasBindingClass && !(hasBindingText && isErrorLike)) return null;
      const cliType = conversationCliTypeForSession(s);
      const cliLabel = /^(?:claude|claudecode|claude_code|claude-code)$/.test(cliType) ? "ClaudeCode" : "CLI";
      const runId = String(firstNonEmptyText([
        latestEffectiveRunSummary.run_id,
        latestRunSummary.run_id,
      ]) || "").trim();
      const baseDetail = cliLabel + " conversation 未完成初始化或已丢失；请重试初始化或等待后端修复。";
      return {
        blocked: true,
        reason: "session_binding",
        cliType,
        heading: "配置阻塞：会话绑定失败",
        body: baseDetail,
        message: "会话绑定失败，已暂停普通发送。",
        action: "请刷新状态，或等待后端完成绑定修复后再发送。",
        runId,
        title: [
          "配置阻塞：会话绑定失败",
          baseDetail,
          runId ? ("run_id: " + runId) : "",
        ].filter(Boolean).join("\n"),
      };
    }

    function isConversationSessionBindingBlocked(session) {
      return !!conversationSessionBindingBlockMeta(session);
    }

    function conversationSessionBindingBlockMessage(session) {
      const meta = conversationSessionBindingBlockMeta(session);
      return meta ? (meta.heading + "；" + meta.body) : "";
    }
