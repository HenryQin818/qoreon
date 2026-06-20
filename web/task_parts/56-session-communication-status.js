    function sessionStatusBool(value) {
      if (typeof value === "boolean") return value;
      if (typeof value === "number") return value !== 0;
      const text = String(value || "").trim().toLowerCase();
      return text === "1" || text === "true" || text === "yes" || text === "y";
    }

    function normalizeCommunicationProjectionSummaryClient(raw) {
      const src = (raw && typeof raw === "object") ? raw : null;
      if (!src) return {};
      return {
        reason: String(firstNonEmptyText([src.reason, src.projection_reason, src.projectionReason]) || "").trim().toLowerCase(),
        source_run_id: String(firstNonEmptyText([src.source_run_id, src.sourceRunId, src.run_id, src.runId]) || "").trim(),
        visible: sessionStatusBool(firstNonEmptyText([src.visible, src.is_visible, src.isVisible, false])),
        projectable: sessionStatusBool(firstNonEmptyText([src.projectable, src.can_project, src.canProject, false])),
        degraded: sessionStatusBool(firstNonEmptyText([src.degraded, false])),
        degraded_reason: String(firstNonEmptyText([src.degraded_reason, src.degradedReason]) || "").trim(),
      };
    }

    function hasCommunicationProjectionSummaryClientData(raw) {
      const summary = normalizeCommunicationProjectionSummaryClient(raw);
      return !!(
        summary.reason
        || summary.source_run_id
        || summary.visible
        || summary.projectable
        || summary.degraded
        || summary.degraded_reason
      );
    }

    function normalizeCommunicationStatusSummaryClient(raw) {
      const src = (raw && typeof raw === "object") ? raw : null;
      if (!src) return null;
      return {
        delivery_state: String(firstNonEmptyText([src.delivery_state, src.deliveryState]) || "").trim().toLowerCase(),
        receipt_state: String(firstNonEmptyText([src.receipt_state, src.receiptState]) || "").trim().toLowerCase(),
        receipt_required: sessionStatusBool(firstNonEmptyText([src.receipt_required, src.receiptRequired, false])),
        source_run_id: String(firstNonEmptyText([src.source_run_id, src.sourceRunId]) || "").trim(),
        updated_at: String(firstNonEmptyText([src.updated_at, src.updatedAt]) || "").trim(),
        degraded: sessionStatusBool(firstNonEmptyText([src.degraded, false])),
        degraded_reason: String(firstNonEmptyText([src.degraded_reason, src.degradedReason]) || "").trim(),
        projection_summary: normalizeCommunicationProjectionSummaryClient(
          src.projection_summary || src.projectionSummary || null
        ),
      };
    }

    function hasCommunicationStatusSummaryClientData(raw) {
      const summary = normalizeCommunicationStatusSummaryClient(raw);
      return !!(summary && (
        summary.delivery_state
        || summary.receipt_state
        || summary.receipt_required
        || summary.source_run_id
        || hasCommunicationProjectionSummaryClientData(summary.projection_summary)
      ));
    }

    function mergeCommunicationStatusSummaryClient(prevRaw, nextRaw) {
      const prev = normalizeCommunicationStatusSummaryClient(prevRaw);
      const next = normalizeCommunicationStatusSummaryClient(nextRaw);
      if (!prev && !next) return null;
      if (!prev) return next;
      if (!next) return prev;
      return {
        ...prev,
        ...next,
        delivery_state: next.delivery_state || prev.delivery_state,
        receipt_state: next.receipt_state || prev.receipt_state,
        receipt_required: next.receipt_required || prev.receipt_required,
        source_run_id: next.source_run_id || prev.source_run_id,
        updated_at: next.updated_at || prev.updated_at,
        degraded: next.degraded || prev.degraded,
        degraded_reason: next.degraded_reason || prev.degraded_reason,
        projection_summary: hasCommunicationProjectionSummaryClientData(next.projection_summary)
          ? next.projection_summary
          : (prev.projection_summary || {}),
      };
    }

    function getSessionCommunicationStatusSummary(session) {
      const s = (session && typeof session === "object") ? session : {};
      return normalizeCommunicationStatusSummaryClient(
        s.communication_status_summary || s.communicationStatusSummary || null
      );
    }

    function readConversationBusyProjectionFields(session, currentRuntimeState = null) {
      const s = (session && typeof session === "object") ? session : {};
      const rawRuntime = (s.runtime_state && typeof s.runtime_state === "object")
        ? s.runtime_state
        : ((s.runtimeState && typeof s.runtimeState === "object") ? s.runtimeState : {});
      const runtimeState = (currentRuntimeState && typeof currentRuntimeState === "object")
        ? currentRuntimeState
        : (typeof getSessionRuntimeState === "function" ? getSessionRuntimeState(s) : rawRuntime);
      const communicationSummary = getSessionCommunicationStatusSummary(s);
      const projectionSummary = (communicationSummary && communicationSummary.projection_summary)
        ? communicationSummary.projection_summary
        : normalizeCommunicationProjectionSummaryClient(
          ((s.communication_status_summary || s.communicationStatusSummary || {}).projection_summary)
          || ((s.communication_status_summary || s.communicationStatusSummary || {}).projectionSummary)
          || null
        );
      return {
        busy_source: String(firstNonEmptyText([runtimeState.busy_source, rawRuntime.busy_source, rawRuntime.busySource]) || "").trim().toLowerCase(),
        display_secondary_state: String(firstNonEmptyText([runtimeState.display_secondary_state, rawRuntime.display_secondary_state, rawRuntime.displaySecondaryState]) || "").trim().toLowerCase(),
        external_busy_reason: String(firstNonEmptyText([runtimeState.external_busy_reason, rawRuntime.external_busy_reason, rawRuntime.externalBusyReason]) || "").trim(),
        active_run_message_kind: String(firstNonEmptyText([runtimeState.active_run_message_kind, rawRuntime.active_run_message_kind, rawRuntime.activeRunMessageKind]) || "").trim().toLowerCase(),
        active_run_sender_type: String(firstNonEmptyText([runtimeState.active_run_sender_type, rawRuntime.active_run_sender_type, rawRuntime.activeRunSenderType]) || "").trim().toLowerCase(),
        active_run_trigger_type: String(firstNonEmptyText([runtimeState.active_run_trigger_type, rawRuntime.active_run_trigger_type, rawRuntime.activeRunTriggerType]) || "").trim().toLowerCase(),
        active_run_visibility: String(firstNonEmptyText([runtimeState.active_run_visibility, rawRuntime.active_run_visibility, rawRuntime.activeRunVisibility]) || "").trim().toLowerCase(),
        active_run_projection_reason: String(firstNonEmptyText([runtimeState.active_run_projection_reason, rawRuntime.active_run_projection_reason, rawRuntime.activeRunProjectionReason]) || "").trim().toLowerCase(),
        active_run_id: String(firstNonEmptyText([runtimeState.active_run_id, rawRuntime.active_run_id, rawRuntime.activeRunId]) || "").trim(),
        queued_run_id: String(firstNonEmptyText([runtimeState.queued_run_id, rawRuntime.queued_run_id, rawRuntime.queuedRunId]) || "").trim(),
        display_state: String(firstNonEmptyText([runtimeState.display_state, rawRuntime.display_state, rawRuntime.displayState]) || "").trim().toLowerCase(),
        external_busy: sessionStatusBool(firstNonEmptyText([
          runtimeState.external_busy,
          rawRuntime.external_busy,
          rawRuntime.externalBusy,
          false,
        ])),
        degraded: sessionStatusBool(firstNonEmptyText([
          runtimeState.degraded,
          rawRuntime.degraded,
          communicationSummary && communicationSummary.degraded,
          projectionSummary.degraded,
          false,
        ])),
        degraded_reason: String(firstNonEmptyText([
          runtimeState.degraded_reason,
          rawRuntime.degraded_reason,
          rawRuntime.degradedReason,
          communicationSummary && communicationSummary.degraded_reason,
          projectionSummary.degraded_reason,
        ]) || "").trim(),
        projection_summary: projectionSummary,
      };
    }

    function normalizeAgentBusyProjectionMeta(session, currentRuntimeState = null) {
      const fields = readConversationBusyProjectionFields(session, currentRuntimeState);
      const projection = fields.projection_summary || {};
      const status = String(firstNonEmptyText([
        (typeof getSessionStatus === "function" ? getSessionStatus(session || {}) : ""),
        fields.display_state,
      ]) || "").trim().toLowerCase();
      const reason = String(firstNonEmptyText([
        fields.active_run_projection_reason,
        projection.reason,
        fields.display_secondary_state,
      ]) || "").trim().toLowerCase();
      const tokens = new Set([
        fields.busy_source,
        fields.display_secondary_state,
        fields.active_run_message_kind,
        fields.active_run_sender_type,
        fields.active_run_trigger_type,
        fields.active_run_visibility,
        reason,
      ].map((item) => String(item || "").trim().toLowerCase()).filter(Boolean));
      const runId = String(firstNonEmptyText([
        fields.active_run_id,
        fields.queued_run_id,
        projection.source_run_id,
      ]) || "").trim();
      const titleDetails = [];
      if (reason) titleDetails.push("投影原因: " + reason);
      if (fields.busy_source) titleDetails.push("忙态来源: " + fields.busy_source);
      if (fields.display_secondary_state) titleDetails.push("副状态: " + fields.display_secondary_state);
      if (runId) titleDetails.push("run: " + runId);
      if (fields.external_busy_reason) titleDetails.push(fields.external_busy_reason);
      const makeMeta = (key, text, tone, heading, body, opts = {}) => ({
        key,
        text: opts.hideBadge ? "" : text,
        tone: tone || "muted",
        title: [heading || text].concat(titleDetails).filter(Boolean).join("\n"),
        heading: heading || text,
        body,
        details: Array.isArray(opts.details) ? opts.details : [],
        reason,
        runId,
      });
      const isDegradedProjection = !!(
        fields.degraded
        || tokens.has("degraded_unknown")
        || reason === "degraded_runtime_index"
        || reason === "cache_hit_no_runtime"
        || reason === "stale_cache_inflight"
      );

      if (tokens.has("provider_transient") || tokens.has("provider_transient_failure") || tokens.has("provider_transient_failed")) {
        return makeMeta(
          "provider_transient",
          "远端临时失败",
          "warn",
          "模型服务临时不可用",
          "这不是业务处理失败，可能已有部分动作完成；需要查看运行结果并按补链恢复处理。"
        );
      }
      if (tokens.has("external_cli") || tokens.has("external_busy") || reason === "external_busy_no_run" || (fields.external_busy && !fields.active_run_id)) {
        return makeMeta(
          "external_busy",
          "外部占用",
          "external",
          "会话被外部 CLI 占用",
          fields.external_busy_reason || "当前忙态来自系统外部探测，系统内没有可投影的普通消息正文。"
        );
      }
      if (
        tokens.has("system_callback")
        || tokens.has("system_callback_summary")
        || fields.active_run_sender_type === "system"
        || reason === "system_callback_projection_gap"
      ) {
        return makeMeta(
          "system_callback",
          "系统回执",
          "info",
          "当前为系统回执或自动回调",
          "这类消息不等同于用户或 Agent 的普通正文，因此右侧可能没有对应聊天气泡。"
        );
      }
      if (reason === "missing_source_ref" || tokens.has("missing_source_ref")) {
        return makeMeta(
          "missing_source_ref",
          "来源缺失",
          "warn",
          "消息来源字段不完整",
          "这条协作消息缺少 source_ref，前端保留真实原因并提示补字段后重发。",
          {
            details: [
              { label: "发生什么", text: "消息缺少 source_ref，系统无法稳定确认它从哪个项目、通道和会话发起。" },
              { label: "影响什么", text: "会影响回执追踪、消息归因和右侧普通消息投影，后续排查会看到 missing_source_ref。" },
              { label: "怎么修", text: "补齐 source_ref/callback_to 后重发；若无法判断来源，请联系消息治理位处理。" },
            ],
          }
        );
      }
      if (tokens.has("legacy_run") || reason === "legacy_missing_refs") {
        return makeMeta(
          "legacy_run",
          "旧链路",
          "muted",
          "旧链路消息缺少标准投影字段",
          "历史 run 缺少完整协作引用，暂不能稳定投影成普通消息。"
        );
      }
      if (tokens.has("hidden") || reason === "hidden_message") {
        return makeMeta(
          "hidden_message",
          "无消息投影",
          "muted",
          "当前 run 不作为普通正文展示",
          "该运行结果按可见性规则隐藏，列表忙态保留为运行状态提示。"
        );
      }
      if (tokens.has("missing_projection") || reason === "missing_projection" || reason === "no_projection" || reason === "no_projectable_message") {
        return makeMeta(
          "missing_projection",
          "无消息投影",
          "muted",
          "当前忙态没有可投影消息",
          "运行态来自轻量摘要，但没有可展示为普通聊天正文的消息。"
        );
      }
      if (reason === "queued_no_active_run" || (!fields.active_run_id && fields.queued_run_id && !isDegradedProjection)) {
        return makeMeta(
          "queued_no_active_run",
          "排队等待",
          "muted",
          "消息仍在排队",
          "当前暂无执行正文，开始运行后会更新为处理过程或结果。",
          { hideBadge: true }
        );
      }
      if (isDegradedProjection) {
        const badgeEligibleStates = ["active", "running", "queued", "retry_waiting", "external_busy"];
        const showDegradedBadge = !!(
          fields.active_run_id
          || fields.queued_run_id
          || badgeEligibleStates.includes(status)
          || badgeEligibleStates.includes(fields.display_state)
        );
        if (reason === "degraded_runtime_index") {
          return makeMeta(
            "degraded_runtime_index",
            "状态降级",
            "warn",
            "运行时索引缺失或已降级",
            "发生什么：通讯录或运行时索引没有返回可用的实时投影；影响：列表忙态、活跃 run 和消息入口可能延迟或不完整；怎么修：重建通讯录/运行时索引，或联系治理位处理。",
            {
              hideBadge: !showDegradedBadge,
              details: [
                { label: "发生什么", text: "通讯录或运行时索引没有返回可用的实时投影。" },
                { label: "影响什么", text: "列表忙态、活跃 run 和消息入口可能延迟或不完整。" },
                { label: "怎么修", text: "重建通讯录/运行时索引，或联系治理位处理。" },
              ],
            }
          );
        }
        return makeMeta(
          "degraded_unknown",
          "状态降级",
          "warn",
          "当前状态来自降级数据",
          "轻量摘要暂不能稳定判断消息投影，列表忙态仅作为运行态提示。",
          { hideBadge: !showDegradedBadge }
        );
      }
      return null;
    }

    function conversationBusyProjectionAuxStatusMeta(session) {
      const meta = normalizeAgentBusyProjectionMeta(session);
      if (!meta || !meta.text) return null;
      return {
        key: "busy_projection_" + meta.key,
        text: meta.text,
        tone: meta.tone,
        title: meta.title || meta.heading || meta.text,
      };
    }

    function conversationProjectionExplanationMeta(session, currentRuntimeState = null, runs = [], opts = {}) {
      const meta = normalizeAgentBusyProjectionMeta(session, currentRuntimeState);
      if (!meta) return null;
      if (opts && opts.timelineLoading) return null;
      const s = (session && typeof session === "object") ? session : {};
      const fields = readConversationBusyProjectionFields(s, currentRuntimeState);
      const status = String(
        (typeof getSessionStatus === "function" ? getSessionStatus(s) : "")
        || fields.display_state
        || ""
      ).trim().toLowerCase();
      const activeLike = status === "running"
        || status === "queued"
        || status === "retry_waiting"
        || status === "external_busy"
        || !!fields.active_run_id
        || !!fields.queued_run_id
        || !!meta.reason;
      if (!activeLike && meta.key !== "provider_transient" && meta.key !== "degraded_unknown") return null;
      const visibleRunIds = new Set(
        (Array.isArray(runs) ? runs : [])
          .map((item) => String((item && item.id) || "").trim())
          .filter(Boolean)
      );
      if (
        meta.key === "missing_projection"
        && fields.active_run_id
        && visibleRunIds.has(fields.active_run_id)
        && !meta.reason
      ) {
        return null;
      }
      const chips = [];
      if (meta.text) chips.push(meta.text);
      if (fields.busy_source) chips.push("来源 " + fields.busy_source);
      if (meta.reason) chips.push("原因 " + meta.reason);
      if (meta.runId) chips.push("run " + meta.runId.slice(0, 8));
      return {
        key: meta.key,
        tone: meta.tone,
        heading: meta.heading,
        body: meta.body,
        details: Array.isArray(meta.details) ? meta.details : [],
        title: meta.title,
        chips,
      };
    }

    function conversationRecoveryAuxStatusMeta(session) {
      const s = (session && typeof session === "object") ? session : {};
      const latest = getSessionLatestRunSummary(s);
      const effective = getSessionLatestEffectiveRunSummary(s);
      const retryExhausted = sessionStatusBool(firstNonEmptyText([
        s.retry_exhausted,
        s.retryExhausted,
        latest.retry_exhausted,
        latest.retryExhausted,
        effective.retry_exhausted,
        effective.retryExhausted,
      ]));
      if (retryExhausted) {
        return {
          key: "retry_exhausted",
          text: "重试耗尽",
          tone: "error",
          title: "自动重试已达到上限，需要人工补链恢复",
        };
      }
      const recoveryMode = String(firstNonEmptyText([
        s.recovery_mode,
        s.recoveryMode,
        latest.recovery_mode,
        latest.recoveryMode,
        effective.recovery_mode,
        effective.recoveryMode,
      ]) || "").trim().toLowerCase();
      const recoveryRequired = sessionStatusBool(firstNonEmptyText([
        s.recovery_required,
        s.recoveryRequired,
        latest.recovery_required,
        latest.recoveryRequired,
        effective.recovery_required,
        effective.recoveryRequired,
      ]));
      if (recoveryRequired || recoveryMode === "manual_recovery") {
        return {
          key: "recovery_required",
          text: "需补链",
          tone: "warn",
          title: "最近运行需要补链恢复或人工收口",
        };
      }
      return null;
    }

    function conversationCommunicationAuxStatusMeta(session) {
      const summary = getSessionCommunicationStatusSummary(session);
      if (!summary) return null;
      const receiptState = String(summary.receipt_state || "").trim().toLowerCase();
      const deliveryState = String(summary.delivery_state || "").trim().toLowerCase();
      if (receiptState === "receipt_timeout") {
        return {
          key: "receipt_timeout",
          text: "回执超时",
          tone: "error",
          title: "任务已要求回执，但等待回执超时",
        };
      }
      if (deliveryState === "delivery_unverified") {
        return {
          key: "delivery_unverified",
          text: "送达待核验",
          tone: "warn",
          title: "消息已提交，但送达可见性证据尚未闭环",
        };
      }
      if (receiptState === "receipt_pending" || (summary.receipt_required && !receiptState)) {
        return {
          key: "receipt_pending",
          text: "待回执",
          tone: "warn",
          title: "消息已送达并要求处理后回执",
        };
      }
      if (receiptState === "receipt_done") {
        return {
          key: "receipt_done",
          text: "已回执",
          tone: "muted",
          title: "已收到正式回执",
        };
      }
      return null;
    }

    function conversationAuxStatusMeta(session) {
      const result = [];
      const recovery = conversationRecoveryAuxStatusMeta(session);
      const communication = conversationCommunicationAuxStatusMeta(session);
      const busyProjection = conversationBusyProjectionAuxStatusMeta(session);
      if (recovery) result.push(recovery);
      if (communication && !result.some((item) => item.key === communication.key)) result.push(communication);
      if (busyProjection && !result.some((item) => item.key === busyProjection.key)) result.push(busyProjection);
      return result.slice(0, 3);
    }

    function buildConversationAuxStatusBadges(session) {
      const items = conversationAuxStatusMeta(session);
      if (!items.length) return null;
      const wrap = el("span", { class: "conv-aux-badges" });
      items.forEach((item) => {
        const isDegradedIconOnly = item.key === "busy_projection_degraded_unknown"
          || item.key === "busy_projection_degraded_runtime_index";
        const label = item.text || "";
        wrap.appendChild(el("span", {
          class: "conv-aux-badge " + String(item.tone || "muted") + (isDegradedIconOnly ? " is-icon-only is-degraded-icon" : ""),
          text: isDegradedIconOnly ? "!" : label,
          title: item.title || label,
          "aria-label": label,
        }));
      });
      return wrap;
    }
