// 第六刀：会话详情壳层与会话 API/缓存桥接
    function conversationSyntheticRunStatusFromOutcomeState(raw) {
      const outcome = String(raw || "").trim().toLowerCase();
      if (!outcome || outcome === "success" || outcome === "done" || outcome === "recovered_notice") return "done";
      if (
        outcome === "interrupted_infra"
        || outcome === "interrupted_user"
        || outcome === "failed_config"
        || outcome === "failed_business"
      ) {
        return "error";
      }
      return "done";
    }

    function conversationSyntheticRunStatusFromAction(actionKind, rawStatus = "") {
      const status = String(rawStatus || "").trim().toLowerCase();
      if (status === "done" || status === "success") return "done";
      if (status === "error" || status === "failed" || status === "blocked") return "error";
      const action = String(actionKind || "").trim().toLowerCase();
      if (action === "block") return "error";
      if (action === "update" || action === "done") return "done";
      return "done";
    }

    function buildConversationSyntheticTimelineRunsFromSessionDetail(session, ctx = {}) {
      const s = (session && typeof session === "object") ? session : {};
      const tracking = (s.task_tracking && typeof s.task_tracking === "object") ? s.task_tracking : {};
      const actions = Array.isArray(tracking.recent_task_actions) ? tracking.recent_task_actions : [];
      const rows = [];
      const seen = new Set();
      const blockedSourceRunIds = [];
      actions.forEach((item) => {
        const action = (item && typeof item === "object") ? item : {};
        const runId = String(action.source_run_id || "").trim();
        if (!runId || seen.has(runId)) return;
        const status = conversationSyntheticRunStatusFromAction(action.action_kind, action.status);
        const row = {
          id: runId,
          status,
          display_state: status,
          createdAt: String(action.at || "").trim(),
          updatedAt: String(action.at || "").trim(),
          lastPreview: String(action.action_text || "").trim(),
          preview: String(action.action_text || "").trim(),
          channelName: String(action.source_channel || ctx.channelName || s.channel_name || "").trim(),
          cliType: String(ctx.cliType || s.cli_type || "codex").trim() || "codex",
          sourceAgentName: String(action.source_agent_name || "").trim(),
        };
        if (status === "error") blockedSourceRunIds.push(runId);
        if (String(action.source_agent_name || "").trim() === "系统") {
          row.trigger_type = "restart_recovery_summary";
          row.restartRecoverySourceRunIds = blockedSourceRunIds.filter((one) => one && one !== runId);
        }
        rows.push(row);
        seen.add(runId);
      });
      return rows;
    }

    function resolvePreferredConversationSelection(allSessions, visibleSessions, explicitSessionId, explicitSelected, rememberedSessionId, channelName) {
      const explicitSid = String(explicitSessionId || "").trim();
      if (explicitSelected && explicitSid) {
        return {
          sessionId: explicitSid,
          explicit: true,
          rememberSelection: false,
          channelName: String(channelName || "").trim(),
        };
      }
      const rememberedSid = String(rememberedSessionId || "").trim();
      const all = Array.isArray(allSessions) ? allSessions : [];
      const visible = Array.isArray(visibleSessions) ? visibleSessions : [];
      if (rememberedSid && all.some((item) => String((item && item.sessionId) || "").trim() === rememberedSid)) {
        return {
          sessionId: rememberedSid,
          explicit: false,
          rememberSelection: true,
          channelName: String(channelName || "").trim(),
        };
      }
      const fallbackPool = visible.length ? visible : all;
      const defaultSid = typeof pickDefaultConversationSessionId === "function"
        ? String(pickDefaultConversationSessionId(fallbackPool) || "").trim()
        : String((((fallbackPool || [])[0] || {}).sessionId) || "").trim();
      return {
        sessionId: defaultSid,
        explicit: false,
        rememberSelection: !!defaultSid,
        channelName: String(channelName || "").trim(),
      };
    }

    function buildExplicitConversationSessionStub(projectId, channelName, sessionId) {
      const sid = String(sessionId || "").trim();
      const channel = String(channelName || "").trim();
      const shortId = sid.replace(/[^0-9a-z]/ig, "").slice(0, 8).toLowerCase() || sid.slice(0, 8);
      const displayName = channel || (shortId ? ("会话 " + shortId) : "显式会话");
      return {
        id: sid,
        sessionId: sid,
        session_id: sid,
        project_id: String(projectId || "").trim(),
        channel_name: channel,
        channelName: channel,
        displayName,
        display_name: displayName,
        displayNameSource: channel ? "channel_name" : "explicit_sid_fallback",
        display_name_source: channel ? "channel_name" : "explicit_sid_fallback",
        agent_name_state: "identity_pending",
        agent_display_issue: "pending_resolution",
        alias: "",
      };
    }

    function renderConversationQuickTips(ctx, runs) {
      const box = document.getElementById("convQuickTips");
      if (!box) return;
      box.innerHTML = "";
      const tips = conversationQuickTipsForRuns(ctx, runs);
      if (!tips.length) {
        box.style.display = "none";
        return;
      }
      box.style.display = "flex";
      tips.forEach((tip) => {
        box.appendChild(el("span", {
          class: "convquicktip-label",
          text: String(tip.label || tip.message || "快捷发送"),
          title: String(tip.label || tip.message || ""),
        }));
        const sendQuickBtn = el("button", {
          class: "btn textbtn convquicktip-send",
          type: "button",
          text: PCONV.sending ? "发送中..." : "发送",
        });
        sendQuickBtn.disabled = !!PCONV.sending;
        sendQuickBtn.addEventListener("click", async (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (sendQuickBtn.disabled) return;
          sendQuickBtn.disabled = true;
          await sendConversationQuickMessage(String(tip.message || ""));
        });
        box.appendChild(sendQuickBtn);
      });
    }

    function renderConvComposerRunActions(ctx, runs) {
      const box = document.getElementById("convComposerRunActions");
      if (!box) return;
      box.innerHTML = "";
      box.style.display = "none";
    }

    function summarizeConversationLivePreview(rawText, maxLen = 120) {
      const text = String(rawText || "").replace(/\r\n?/g, "\n").trim();
      if (!text) return "";
      const compact = text
        .split("\n")
        .map((line) => String(line || "").trim())
        .filter(Boolean)
        .join(" ");
      if (!compact) return "";
      return compact.length > maxLen ? (compact.slice(0, maxLen) + "…") : compact;
    }

    function buildConversationLiveRunHint(runs) {
      const list = Array.isArray(runs) ? runs : [];
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const run = list[i] || {};
        const rid = String(run.id || "").trim();
        if (!rid) continue;
        const detail = PCONV.detailMap[rid] || null;
        const st = String(getRunDisplayState(run, detail) || "").trim().toLowerCase();
        if (!isWorkingLikeState(st)) continue;
        const assistantText = stripInjectedConversationReplyText(resolveAssistantText(run, detail));
        const processInfo = collectRunProcessInfo(rid, st, run, detail);
        const preview = summarizeConversationLivePreview(firstNonEmptyText([
          assistantText,
          run.partialPreview,
          run.lastPreview,
          processInfo && processInfo.latest,
        ]));
        return {
          runId: rid,
          state: st,
          preview,
          latestProgressAt: String(firstNonEmptyText([
            processInfo && processInfo.latestProgressAt,
            run.lastProgressAt,
            run.updatedAt,
            run.updated_at,
            run.createdAt,
          ]) || "").trim(),
        };
      }
      return null;
    }

    function buildConversationSessionRunSummary(currentSession, currentRuntimeState, liveRunHint = null) {
      const session = (currentSession && typeof currentSession === "object") ? currentSession : {};
      const runtimeState = (currentRuntimeState && typeof currentRuntimeState === "object") ? currentRuntimeState : {};
      const latestRunSummary = getSessionLatestRunSummary(session);
      const sessionStatus = String(getSessionStatus(session) || runtimeState.display_state || "").trim().toLowerCase();
      const activeRunId = String(firstNonEmptyText([
        runtimeState.active_run_id,
        liveRunHint && liveRunHint.runId,
      ]) || "").trim();
      const queuedRunId = String(runtimeState.queued_run_id || "").trim();
      const activeLike = isWorkingLikeState(sessionStatus) || !!activeRunId || !!queuedRunId;
      if (!activeLike) return null;

      let headline = "";
      if (sessionStatus === "queued" || (!activeRunId && queuedRunId)) {
        headline = "当前会话有消息排队中";
      } else if (sessionStatus === "retry_waiting") {
        headline = "当前会话正在等待自动重试";
      } else if (sessionStatus === "external_busy") {
        headline = "当前会话当前被外部占用";
      } else if (activeRunId) {
        headline = "当前活跃 run " + shortId(activeRunId) + " 正在执行";
      } else {
        headline = "当前会话正在执行";
      }

      const detailParts = [];
      if (liveRunHint && liveRunHint.preview) {
        detailParts.push(String(liveRunHint.preview || "").trim());
      } else if (liveRunHint && liveRunHint.latestProgressAt) {
        const progressText = compactDateTime(liveRunHint.latestProgressAt) || shortDateTime(liveRunHint.latestProgressAt);
        if (progressText) detailParts.push("最近进展 " + progressText);
      }
      if (runtimeState.queue_depth > 1) detailParts.push("队列 " + runtimeState.queue_depth);

      const latestSummaryStatus = normalizeDisplayState(firstNonEmptyText([
        latestRunSummary && latestRunSummary.status,
        latestRunSummary && latestRunSummary.display_state,
        latestRunSummary && latestRunSummary.displayState,
      ]), "idle");
      const latestSummaryRunId = String(firstNonEmptyText([
        latestRunSummary && latestRunSummary.run_id,
        latestRunSummary && latestRunSummary.runId,
      ]) || "").trim();
      const staleLatestError = latestSummaryStatus === "error"
        && (
          (activeRunId && latestSummaryRunId !== activeRunId)
          || (!activeRunId && queuedRunId && latestSummaryRunId !== queuedRunId)
          || (!latestSummaryRunId && (activeRunId || queuedRunId))
        );
      if (staleLatestError) {
        detailParts.push(
          latestSummaryRunId
            ? ("上一条 run " + shortId(latestSummaryRunId) + " 已异常")
            : "上一条 run 已异常"
        );
      }

      const titleParts = [headline];
      if (activeRunId) titleParts.push("active_run_id: " + activeRunId);
      if (queuedRunId) titleParts.push("queued_run_id: " + queuedRunId);
      if (runtimeState.updated_at) titleParts.push("runtime.updated_at: " + runtimeState.updated_at);
      if (latestSummaryRunId) titleParts.push("latest_run_summary.run_id: " + latestSummaryRunId);
      if (detailParts.length) titleParts.push(detailParts.join(" · "));
      return {
        text: [headline].concat(detailParts).join(" · "),
        title: titleParts.filter(Boolean).join("\n"),
      };
    }

    function buildConversationRuntimeShadowMeta(currentRuntimeState, runs) {
      const runtimeState = (currentRuntimeState && typeof currentRuntimeState === "object") ? currentRuntimeState : {};
      const visibleRunIds = new Set(
        (Array.isArray(runs) ? runs : [])
          .map((item) => String((item && item.id) || "").trim())
          .filter(Boolean)
      );
      const activeRunId = String(runtimeState.active_run_id || "").trim();
      const queuedRunId = String(runtimeState.queued_run_id || "").trim();
      return {
        activeRunId,
        queuedRunId,
        missingActiveRunId: activeRunId && !visibleRunIds.has(activeRunId) ? activeRunId : "",
        missingQueuedRunId: queuedRunId && !visibleRunIds.has(queuedRunId) ? queuedRunId : "",
        queueDepth: Math.max(0, Number(runtimeState.queue_depth || 0) || 0),
        updatedAt: String(runtimeState.updated_at || "").trim(),
      };
    }

    function buildConversationRuntimeShadowHint(shadowMeta) {
      const meta = (shadowMeta && typeof shadowMeta === "object") ? shadowMeta : {};
      if (!meta.missingActiveRunId && !meta.missingQueuedRunId) return null;
      const parts = [];
      if (meta.missingActiveRunId) parts.push("当前有 1 条活跃消息正在处理");
      if (meta.missingQueuedRunId) parts.push(meta.queueDepth > 0 ? ("另有 " + meta.queueDepth + " 条消息排队中") : "另有排队消息等待开始");
      return {
        text: parts.join(" · "),
        title: [
          meta.missingActiveRunId ? ("active_run_id: " + meta.missingActiveRunId) : "",
          meta.missingQueuedRunId ? ("queued_run_id: " + meta.missingQueuedRunId) : "",
          meta.updatedAt ? ("updated_at: " + meta.updatedAt) : "",
        ].filter(Boolean).join("\n"),
      };
    }

    function buildConversationRuntimeShadowRuns(ctx, currentSession, currentRuntimeState, shadowMeta) {
      const meta = (shadowMeta && typeof shadowMeta === "object") ? shadowMeta : {};
      const createdAt = String(firstNonEmptyText([
        meta.updatedAt,
        currentRuntimeState && currentRuntimeState.updated_at,
        currentSession && currentSession.lastActiveAt,
        new Date().toISOString(),
      ]) || "").trim();
      const queuedText = String(firstNonEmptyText([
        currentSession && currentSession.latestUserMsg,
        "新消息已进入队列，等待前序任务完成后自动开始。",
      ]) || "").trim();
      return {
        activeRun: meta.missingActiveRunId ? {
          id: meta.missingActiveRunId,
          createdAt,
          startedAt: createdAt,
          updatedAt: createdAt,
          status: "running",
          display_state: "running",
          channelName: String((ctx && ctx.channelName) || ""),
          cliType: String((ctx && ctx.cliType) || "codex"),
          runtime_state_shadow: true,
        } : null,
        queuedRun: meta.missingQueuedRunId ? {
          id: meta.missingQueuedRunId,
          createdAt,
          status: "queued",
          display_state: "queued",
          channelName: String((ctx && ctx.channelName) || ""),
          cliType: String((ctx && ctx.cliType) || "codex"),
          messagePreview: queuedText,
          queue_reason: "session_serial",
          blocked_by_run_id: meta.activeRunId || "",
          runtime_state_shadow: true,
        } : null,
      };
    }

    function captureDebugLogScrollPositions(container) {
      if (!container) return;
      if (!PCONV.debugLogScrollTop) PCONV.debugLogScrollTop = Object.create(null);
      const nodes = Array.from(container.querySelectorAll(".mdebug-log[data-run-id]"));
      for (const n of nodes) {
        const runId = String(n.getAttribute("data-run-id") || "").trim();
        if (!runId) continue;
        const top = Number(n.scrollTop || 0);
        if (top > 0) PCONV.debugLogScrollTop[runId] = top;
      }
    }

    function conversationComposerPlaceholder(cliChipName = "Codex") {
      const cliLabel = String(cliChipName || "Codex").trim() || "Codex";
      if (PCONV.enterSendEnabled === false) {
        return "输入要发给该会话 " + cliLabel + " 的消息（回车不发送，Shift+Enter 换行）";
      }
      return "输入要发给该会话 " + cliLabel + " 的消息（Enter 发送）";
    }

    function renderConversationEnterSendToggle(enabled = PCONV.enterSendEnabled !== false) {
      const btn = document.getElementById("convEnterSendToggle");
      if (!btn) return;
      const active = !!enabled;
      btn.classList.toggle("active", active);
      btn.classList.toggle("off", !active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
      btn.title = active ? "已启用回车发送，点击关闭" : "已关闭回车发送，点击启用";
      btn.setAttribute("aria-label", active ? "关闭回车发送" : "启用回车发送");
    }

    function refreshConversationComposerPlaceholder() {
      const input = document.getElementById("convMsg");
      if (!input) return;
      const ctx = currentConversationCtx();
      const cliChipName = ctx && ctx.cliType ? String(ctx.cliType).toUpperCase() : "Codex";
      input.placeholder = conversationComposerPlaceholder(cliChipName);
    }

    function collectConversationReceiptHostRunIds(run) {
      const meta = (run && typeof run === "object") ? run : {};
      const ids = new Set();
      const pushId = (value) => {
        const id = String(value || "").trim();
        if (id) ids.add(id);
      };
      const sourceRef = (meta.source_ref && typeof meta.source_ref === "object")
        ? meta.source_ref
        : ((meta.sourceRef && typeof meta.sourceRef === "object") ? meta.sourceRef : null);
      const routeResolution = (meta.route_resolution && typeof meta.route_resolution === "object")
        ? meta.route_resolution
        : ((meta.routeResolution && typeof meta.routeResolution === "object") ? meta.routeResolution : null);
      const routeSourceRef = routeResolution && routeResolution.source_ref && typeof routeResolution.source_ref === "object"
        ? routeResolution.source_ref
        : ((routeResolution && routeResolution.sourceRef && typeof routeResolution.sourceRef === "object") ? routeResolution.sourceRef : null);
      pushId(meta.host_run_id || meta.hostRunId);
      pushId(meta.display_host_run_id || meta.displayHostRunId);
      pushId(sourceRef && (sourceRef.run_id || sourceRef.runId));
      pushId(routeSourceRef && (routeSourceRef.run_id || routeSourceRef.runId));
      pushId(meta.source_run_id || meta.sourceRunId);
      readCallbackSummaryIds(meta.callback_summary_of || meta.callbackSummaryOf).forEach(pushId);
      readCallbackSummaryIds(meta.callback_aggregate_source_run_ids || meta.callbackAggregateSourceRunIds).forEach(pushId);
      return Array.from(ids);
    }

    function conversationReceiptProjectionMatchesHost(projection, opts = {}) {
      if (!projection || typeof projection !== "object") return false;
      const callbackRunId = String(opts.callbackRunId || "").trim();
      const relatedRunIds = new Set(
        (Array.isArray(opts.relatedRunIds) ? opts.relatedRunIds : [])
          .map((id) => String(id || "").trim())
          .filter(Boolean)
      );
      const items = Array.isArray(projection.items) ? projection.items : [];
      if (callbackRunId && items.some((row) => String((row && row.callbackRunId) || "").trim() === callbackRunId)) {
        return true;
      }
      if (relatedRunIds.size && items.some((row) => {
        const sourceRunId = String((row && row.sourceRunId) || "").trim();
        const hostRunId = String((row && row.hostRunId) || "").trim();
        return relatedRunIds.has(sourceRunId) || relatedRunIds.has(hostRunId);
      })) {
        return true;
      }
      const rollup = (projection.rollup && typeof projection.rollup === "object") ? projection.rollup : null;
      if (rollup) {
        const rollupHostRunId = String(rollup.hostRunId || "").trim();
        if (rollupHostRunId && relatedRunIds.has(rollupHostRunId)) return true;
      }
      return false;
    }

    function resolveConversationReceiptHostRunId(run, runId, visibleRunIds, runsById, detailMap) {
      const currentRunId = String(runId || "").trim();
      const candidateIds = collectConversationReceiptHostRunIds(run)
        .map((id) => String(id || "").trim())
        .filter((id, index, list) => !!id && id !== currentRunId && list.indexOf(id) === index);
      const relatedRunIds = [currentRunId].concat(candidateIds);
      for (const candidateId of candidateIds) {
        if (!(visibleRunIds && visibleRunIds.has(candidateId))) continue;
        const candidateRun = runsById && runsById.get ? (runsById.get(candidateId) || null) : null;
        const candidateDetail = detailMap ? (detailMap[candidateId] || null) : null;
        const projection = readConversationReceiptProjection(candidateRun, candidateDetail);
        if (conversationReceiptProjectionMatchesHost(projection, {
          callbackRunId: currentRunId,
          relatedRunIds,
        })) {
          return candidateId;
        }
      }
      for (const candidateId of candidateIds) {
        if (!(visibleRunIds && visibleRunIds.has(candidateId))) continue;
        const candidateRun = runsById && runsById.get ? (runsById.get(candidateId) || null) : null;
        const candidateDetail = detailMap ? (detailMap[candidateId] || null) : null;
        if (readConversationReceiptProjection(candidateRun, candidateDetail)) return candidateId;
      }
      return candidateIds[0] || "";
    }

    function mergeConversationReceiptProjection(baseProjection, extraProjection) {
      const base = (baseProjection && typeof baseProjection === "object") ? baseProjection : null;
      const extra = (extraProjection && typeof extraProjection === "object") ? extraProjection : null;
      if (!base && !extra) return null;
      const items = [];
      const pendingActions = [];
      const itemKeys = new Set();
      const pendingKeys = new Set();
      const pushItem = (row) => {
        if (!row || typeof row !== "object") return;
        const key = [
          String(row.callbackRunId || "").trim(),
          String(row.sourceRunId || "").trim(),
          String(row.hostRunId || "").trim(),
        ].join("|");
        if (!key || itemKeys.has(key)) return;
        itemKeys.add(key);
        items.push(row);
      };
      const pushPending = (row) => {
        if (!row || typeof row !== "object") return;
        const key = [
          String(row.callbackRunId || "").trim(),
          String(row.sourceRunId || "").trim(),
          String(row.title || "").trim(),
        ].join("|");
        if (!key || pendingKeys.has(key)) return;
        pendingKeys.add(key);
        pendingActions.push(row);
      };
      (Array.isArray(base && base.items) ? base.items : []).forEach(pushItem);
      (Array.isArray(extra && extra.items) ? extra.items : []).forEach(pushItem);
      (Array.isArray(base && base.pendingActions) ? base.pendingActions : []).forEach(pushPending);
      (Array.isArray(extra && extra.pendingActions) ? extra.pendingActions : []).forEach(pushPending);
      const baseRollup = (base && base.rollup && typeof base.rollup === "object") ? base.rollup : null;
      const extraRollup = (extra && extra.rollup && typeof extra.rollup === "object") ? extra.rollup : null;
      const agentSet = new Set();
      const collectAgents = (rollup) => {
        (Array.isArray(rollup && rollup.agents) ? rollup.agents : []).forEach((name) => {
          const token = String(name || "").trim();
          if (token) agentSet.add(token);
        });
      };
      collectAgents(baseRollup);
      collectAgents(extraRollup);
      const needConfirmCount = items.reduce((count, row) => {
        const needConfirm = String((row && row.needConfirm) || "").trim();
        return count + ((needConfirm && needConfirm !== "无") ? 1 : 0);
      }, 0);
      const rollup = (baseRollup || extraRollup || items.length || pendingActions.length) ? {
        hostRunId: String(firstNonEmptyText([
          extraRollup && extraRollup.hostRunId,
          baseRollup && baseRollup.hostRunId,
          items[0] && items[0].hostRunId,
        ]) || "").trim(),
        totalCallbacks: Math.max(
          items.length,
          Number((baseRollup && baseRollup.totalCallbacks) || 0),
          Number((extraRollup && extraRollup.totalCallbacks) || 0)
        ),
        pendingActionCount: Math.max(
          pendingActions.length,
          Number((baseRollup && baseRollup.pendingActionCount) || 0),
          Number((extraRollup && extraRollup.pendingActionCount) || 0)
        ),
        latestStatus: String(firstNonEmptyText([
          extraRollup && extraRollup.latestStatus,
          baseRollup && baseRollup.latestStatus,
        ]) || "").trim(),
        latestConclusion: String(firstNonEmptyText([
          extraRollup && extraRollup.latestConclusion,
          baseRollup && baseRollup.latestConclusion,
          items[0] && items[0].currentConclusion,
        ]) || "").trim(),
        needConfirmCount,
        agents: Array.from(agentSet).slice(0, 20),
        lastCallbackAt: String(firstNonEmptyText([
          extraRollup && extraRollup.lastCallbackAt,
          baseRollup && baseRollup.lastCallbackAt,
          items[0] && items[0].callbackAt,
        ]) || "").trim(),
      } : null;
      if (!items.length && !pendingActions.length && !rollup) return null;
      return { items, pendingActions, rollup };
    }

    function readConversationTimelineAnchorInfo(run, detail) {
      const mergedRun = mergeRunForDisplay(
        (detail && detail.full && detail.full.run && typeof detail.full.run === "object") ? detail.full.run : null,
        (run && typeof run === "object") ? run : null
      );
      const senderType = String(firstNonEmptyText([
        mergedRun && mergedRun.sender_type,
        mergedRun && mergedRun.senderType,
      ]) || "").trim().toLowerCase();
      const triggerType = String(firstNonEmptyText([
        mergedRun && mergedRun.trigger_type,
        mergedRun && mergedRun.triggerType,
      ]) || "").trim().toLowerCase();
      const messageKind = String(resolveConversationMessageKind(mergedRun) || "").trim().toLowerCase();
      const sourceRef = (mergedRun.source_ref && typeof mergedRun.source_ref === "object")
        ? mergedRun.source_ref
        : ((mergedRun.sourceRef && typeof mergedRun.sourceRef === "object") ? mergedRun.sourceRef : null);
      const routeResolution = readRouteResolution(mergedRun.route_resolution || mergedRun.routeResolution);
      const routeSourceRef = routeResolution && routeResolution.sourceRef && typeof routeResolution.sourceRef === "object"
        ? routeResolution.sourceRef
        : ((routeResolution && routeResolution.source_ref && typeof routeResolution.source_ref === "object") ? routeResolution.source_ref : null);
      const callbackTo = (mergedRun.callback_to && typeof mergedRun.callback_to === "object")
        ? mergedRun.callback_to
        : ((mergedRun.callbackTo && typeof mergedRun.callbackTo === "object") ? mergedRun.callbackTo : null);
      const messageText = String(firstNonEmptyText([
        detail && detail.full && detail.full.message,
        run && run.messagePreview,
      ]) || "");
      const inboundSummary = readConversationInboundSummary(messageText);
      return {
        run: mergedRun,
        senderType,
        triggerType,
        messageKind,
        sourceChannel: String(firstNonEmptyText([
          sourceRef && (sourceRef.channel_name || sourceRef.channelName),
          routeSourceRef && (routeSourceRef.channel_name || routeSourceRef.channelName),
          inboundSummary && inboundSummary.sourceChannel,
        ]) || "").trim(),
        sourceSessionId: String(firstNonEmptyText([
          sourceRef && (sourceRef.session_id || sourceRef.sessionId),
          routeSourceRef && (routeSourceRef.session_id || routeSourceRef.sessionId),
        ]) || "").trim(),
        targetSessionId: String(firstNonEmptyText([
          callbackTo && (callbackTo.session_id || callbackTo.sessionId),
        ]) || "").trim(),
      };
    }

    function resolveConversationLocalReceiptAnchorRunId(payload = {}) {
      const runs = Array.isArray(payload.runs) ? payload.runs : [];
      const callbackRunId = String(payload.callbackRunId || "").trim();
      const callbackEventMeta = (payload.callbackEventMeta && typeof payload.callbackEventMeta === "object")
        ? payload.callbackEventMeta
        : null;
      if (!callbackRunId || !callbackEventMeta || !runs.length) return "";
      const explicitHostRunId = String(firstNonEmptyText([
        payload.callbackRun && (payload.callbackRun.display_host_run_id || payload.callbackRun.displayHostRunId),
      ]) || "").trim();
      if (explicitHostRunId && explicitHostRunId !== callbackRunId) {
        const visible = runs.some((row) => String((row && row.id) || "").trim() === explicitHostRunId);
        if (visible) return explicitHostRunId;
      }
      const detailMap = payload.detailMap || null;
      const currentSessionId = String(payload.currentSessionId || "").trim();
      const callbackIndex = runs.findIndex((row) => String((row && row.id) || "").trim() === callbackRunId);
      if (callbackIndex < 0) return "";
      const sourceChannel = String(firstNonEmptyText([
        callbackEventMeta.comm && callbackEventMeta.comm.sourceChannel,
      ]) || "").trim();
      const sourceRunId = String(callbackEventMeta.sourceRunId || "").trim();
      const relatedRunIds = new Set([callbackRunId, sourceRunId].filter(Boolean));
      collectConversationReceiptHostRunIds(payload.callbackRun || null).forEach((id) => {
        const token = String(id || "").trim();
        if (token) relatedRunIds.add(token);
      });
      let bestId = "";
      let bestScore = -Infinity;
      for (let idx = 0; idx < runs.length; idx += 1) {
        const row = runs[idx] || null;
        const candidateRunId = String((row && row.id) || "").trim();
        if (!candidateRunId || candidateRunId === callbackRunId) continue;
        const info = readConversationTimelineAnchorInfo(row, detailMap ? detailMap[candidateRunId] : null);
        const candidateStatus = String(getRunDisplayState(row, detailMap ? detailMap[candidateRunId] : null) || "").trim().toLowerCase();
        const callbackLike = info.triggerType === "callback_auto"
          || info.triggerType === "callback_auto_summary"
          || info.messageKind === "system_callback"
          || info.messageKind === "system_callback_summary"
          || info.messageKind === "restart_recovery_summary";
        const workingCandidate = isRunWorking(candidateStatus);
        const isRelatedWorkingCandidate = workingCandidate && (
          (sourceRunId && candidateRunId === sourceRunId)
          || relatedRunIds.has(candidateRunId)
        );
        if (info.senderType === "system" || callbackLike || (workingCandidate && !isRelatedWorkingCandidate)) continue;
        let score = 0;
        if (idx < callbackIndex) score += 40;
        else score += 10;
        score -= Math.min(Math.abs(callbackIndex - idx), 30);
        if (relatedRunIds.has(candidateRunId)) score += 160;
        if (sourceChannel && info.sourceChannel && info.sourceChannel === sourceChannel) score += 120;
        if (sourceRunId && candidateRunId === sourceRunId) score += 200;
        if (workingCandidate) score += 180;
        if (info.messageKind === "collab_update" || info.messageKind === "manual_update") score += 20;
        if (info.senderType === "agent") score += 12;
        if (currentSessionId && info.targetSessionId && info.targetSessionId === currentSessionId) score += 8;
        if (score > bestScore) {
          bestScore = score;
          bestId = candidateRunId;
        }
      }
      return bestId;
    }

    function buildConversationLocalReceiptProjectionFromCallback(payload = {}) {
      const callbackEventMeta = (payload.callbackEventMeta && typeof payload.callbackEventMeta === "object")
        ? payload.callbackEventMeta
        : null;
      const senderRun = (payload.senderRun && typeof payload.senderRun === "object") ? payload.senderRun : {};
      const anchorRunId = String(payload.anchorRunId || "").trim();
      if (!callbackEventMeta || !anchorRunId) return null;
      const callbackRunId = String(payload.callbackRunId || "").trim();
      const ctx = payload.ctx || {};
      const callbackAt = String(firstNonEmptyText([
        senderRun.updated_at,
        senderRun.updatedAt,
        senderRun.created_at,
        senderRun.createdAt,
      ]) || "").trim();
      const needConfirm = String(firstNonEmptyText([
        callbackEventMeta.comm && callbackEventMeta.comm.needConfirm,
        senderRun.need_confirm,
        senderRun.needConfirm,
        "无",
      ]) || "无").trim() || "无";
      const needPeer = String(firstNonEmptyText([
        callbackEventMeta.comm && callbackEventMeta.comm.needPeer,
        senderRun.need_peer,
        senderRun.needPeer,
      ]) || "").trim();
      const expectedResult = String(firstNonEmptyText([
        callbackEventMeta.comm && callbackEventMeta.comm.expectedResult,
        senderRun.expected_result,
        senderRun.expectedResult,
      ]) || "").trim();
      const currentConclusion = String(firstNonEmptyText([
        callbackEventMeta.comm && callbackEventMeta.comm.currentConclusion,
        senderRun.current_conclusion,
        senderRun.currentConclusion,
        callbackConclusionDefault(callbackEventMeta.eventType),
      ]) || "").trim();
      const sourceAgentName = String(firstNonEmptyText([
        senderRun.source_alias,
        senderRun.sourceAlias,
        senderRun.source_agent_alias,
        senderRun.sourceAgentAlias,
        senderRun.source_agent_name,
        senderRun.sourceAgentName,
      ]) || "").trim();
      const item = normalizeConversationReceiptItem({
        source_run_id: String(callbackEventMeta.sourceRunId || callbackRunId || anchorRunId).trim(),
        callback_run_id: callbackRunId,
        host_run_id: anchorRunId,
        host_reason: "local_timeline_anchor",
        trigger_type: callbackEventMeta.triggerType,
        event_type: callbackEventMeta.eventType,
        event_reason: callbackEventMeta.eventReason,
        dispatch_status: "local_anchor",
        source_channel: callbackEventMeta.comm && callbackEventMeta.comm.sourceChannel,
        source_agent_name: sourceAgentName,
        source_project_id: callbackEventMeta.projectId || STATE.project,
        source_session_id: firstNonEmptyText([
          senderRun.source_session_id,
          senderRun.sourceSessionId,
        ]),
        target_project_id: String(firstNonEmptyText([ctx.projectId, STATE.project]) || "").trim(),
        target_channel: String(firstNonEmptyText([ctx.channelName, ctx.displayChannel, ctx.alias]) || "").trim(),
        target_session_id: String(firstNonEmptyText([ctx.sessionId]) || "").trim(),
        callback_task: callbackEventMeta.comm && callbackEventMeta.comm.receiptTask,
        execution_stage: callbackEventMeta.comm && callbackEventMeta.comm.stage,
        current_conclusion: currentConclusion,
        need_peer: needPeer,
        expected_result: expectedResult,
        need_confirm: needConfirm,
        feedback_file_path: callbackEventMeta.feedbackFilePath,
        callback_merge_mode: callbackEventMeta.callbackMergeMode || "local_timeline_anchor",
        callback_anchor_action: "anchored_to_visible_timeline",
        callback_at: callbackAt,
        updated_at: callbackAt,
        route_resolution: callbackEventMeta.routeResolution,
        late_callback: false,
        route_mismatch: false,
        is_summary: !!callbackEventMeta.isSummary,
        aggregate_count: Number(callbackEventMeta.aggregateCount || 0),
        summary_count: Number(callbackEventMeta.summaryCount || 0),
      });
      if (!item) return null;
      const needsAction = !!(
        (needConfirm && needConfirm !== "无")
        || conversationNeedsPeerAction(needPeer)
        || callbackEventMeta.eventType === "error"
        || callbackEventMeta.eventType === "interrupted"
      );
      const pendingAction = needsAction
        ? normalizeConversationReceiptPendingAction({
            source_run_id: item.sourceRunId,
            callback_run_id: item.callbackRunId,
            title: firstNonEmptyText([
              callbackEventMeta.comm && callbackEventMeta.comm.receiptTask,
              sourceAgentName ? (sourceAgentName + " 回执待处理") : "",
              item.sourceChannel ? (item.sourceChannel + " 回执待处理") : "",
              "待处理回执",
            ]),
            action_text: firstNonEmptyText([
              needConfirm && needConfirm !== "无" ? needConfirm : "",
              conversationNeedsPeerAction(needPeer) ? needPeer : "",
              expectedResult,
              currentConclusion,
            ]),
            action_kind: (needConfirm && needConfirm !== "无")
              ? "confirm"
              : ((callbackEventMeta.eventType === "error" || callbackEventMeta.eventType === "interrupted") ? "follow_up" : "receipt"),
            priority: (callbackEventMeta.eventType === "error" || callbackEventMeta.eventType === "interrupted" || (needConfirm && needConfirm !== "无"))
              ? "high"
              : "normal",
            source_channel: item.sourceChannel,
            source_agent_name: item.sourceAgentName,
            event_type: item.eventType,
            callback_at: item.callbackAt,
            need_confirm: item.needConfirm,
          })
        : null;
      return {
        items: item ? [item] : [],
        pendingActions: pendingAction ? [pendingAction] : [],
        rollup: {
          hostRunId: anchorRunId,
          totalCallbacks: 1,
          pendingActionCount: pendingAction ? 1 : 0,
          latestStatus: String(item.eventType || "").trim().toLowerCase(),
          latestConclusion: currentConclusion,
          needConfirmCount: (needConfirm && needConfirm !== "无") ? 1 : 0,
          agents: [item.sourceAgentName || item.sourceChannel].filter(Boolean),
          lastCallbackAt: item.callbackAt,
        },
      };
    }

    function buildConversationLocalReceiptAnchorMaps(runs, visibleRunIds, runsById, detailMap, ctx) {
      const anchoredByHostRunId = Object.create(null);
      const anchoredCallbackRunIds = new Set();
      const list = Array.isArray(runs) ? runs : [];
      for (const row of list) {
        const rid = String((row && row.id) || "").trim();
        if (!rid) continue;
        const detail = detailMap ? (detailMap[rid] || null) : null;
        const senderRun = mergeRunForDisplay(
          (detail && detail.full && detail.full.run && typeof detail.full.run === "object") ? detail.full.run : null,
          row
        );
        const userText = String(firstNonEmptyText([
          detail && detail.full && detail.full.message,
          row && row.messagePreview,
        ]) || "");
        const callbackEventMeta = readRunCallbackEventMeta(senderRun, ctx, userText);
        if (!callbackEventMeta) continue;
        const projectedReceiptHostRunId = resolveConversationReceiptHostRunId(senderRun, rid, visibleRunIds, runsById, detailMap);
        const projectedHostRun = projectedReceiptHostRunId
          ? (runsById && runsById.get ? (runsById.get(projectedReceiptHostRunId) || null) : null)
          : null;
        const projectedHostDetail = projectedReceiptHostRunId ? (detailMap ? (detailMap[projectedReceiptHostRunId] || null) : null) : null;
        const projectedHostReceiptProjection = projectedReceiptHostRunId
          ? readConversationReceiptProjection(projectedHostRun, projectedHostDetail)
          : null;
        const callbackProjectedToVisibleHost = !!(
          projectedReceiptHostRunId
          && projectedReceiptHostRunId !== rid
          && visibleRunIds.has(projectedReceiptHostRunId)
          && conversationReceiptProjectionMatchesHost(projectedHostReceiptProjection, {
            callbackRunId: rid,
            relatedRunIds: [rid].concat(collectConversationReceiptHostRunIds(senderRun)),
          })
        );
        if (callbackProjectedToVisibleHost) continue;
        const anchorRunId = resolveConversationLocalReceiptAnchorRunId({
          runs: list,
          callbackRun: senderRun,
          callbackRunId: rid,
          callbackEventMeta,
          detailMap,
          currentSessionId: ctx && ctx.sessionId,
        });
        if (!anchorRunId) continue;
        const localProjection = buildConversationLocalReceiptProjectionFromCallback({
          callbackEventMeta,
          callbackRunId: rid,
          senderRun,
          anchorRunId,
          ctx,
        });
        if (!localProjection) continue;
        anchoredByHostRunId[anchorRunId] = mergeConversationReceiptProjection(
          anchoredByHostRunId[anchorRunId] || null,
          localProjection
        );
        anchoredCallbackRunIds.add(rid);
      }
      return {
        anchoredByHostRunId,
        anchoredCallbackRunIds,
      };
    }

    function conversationTaskStatusTone(statusText) {
      const text = String(statusText || "").trim();
      if (!text) return "muted";
      if (/(完成|已完成|done)/i.test(text)) return "good";
      if (/(异常|阻塞|失败|error)/i.test(text)) return "bad";
      if (/(暂停|中断)/i.test(text)) return "warn";
      if (/(进行|待办|处理中|排队|跟进)/i.test(text)) return "warn";
      return "muted";
    }

    function conversationTaskActionLabel(kind) {
      const key = String(kind || "").trim().toLowerCase();
      const map = {
        create: "新产生",
        link: "已关联",
        start: "开始推进",
        update: "有更新",
        confirm: "待确认",
        block: "受阻",
        done: "已完成",
        pause: "已暂停",
        follow_up: "待跟进",
      };
      return map[key] || (key ? String(kind) : "");
    }

    function conversationTaskActionTone(kind, status = "") {
      const key = String(kind || "").trim().toLowerCase();
      const normalizedStatus = String(status || "").trim().toLowerCase();
      if (normalizedStatus === "error" || key === "block") return "bad";
      if (key === "done" || normalizedStatus === "done") return "good";
      if (key === "confirm" || key === "follow_up" || key === "create" || key === "start" || key === "pause") return "warn";
      return "muted";
    }

    function conversationTaskOwnerDisplayMeta(rawOwner) {
      const owner = (rawOwner && typeof rawOwner === "object") ? rawOwner : {};
      const state = String(owner.state || "missing").trim().toLowerCase();
      const text = String(firstNonEmptyText([owner.agent_name, owner.alias]) || "待明确").trim() || "待明确";
      let meta = "";
      if (state === "pending") meta = owner.session_id ? "等待该会话回执" : "等待对方处理";
      else if (state === "missing") meta = "责任人待补充";
      else if (owner.alias && owner.agent_name && owner.alias !== owner.agent_name) meta = String(owner.alias || "").trim();
      return {
        text,
        meta,
        state: ["confirmed", "pending", "missing"].includes(state) ? state : "missing",
      };
    }

    function conversationTaskTitleText(row) {
      const raw = String(firstNonEmptyText([
        row && row.title,
        row && row.task_title,
        row && row.taskTitle,
        row && row.name,
        row && row.path,
        row && row.task_path,
        row && row.taskPath,
      ]) || "").trim();
      return raw ? shortTitle(raw) : "未命名任务";
    }

    function buildConversationTaskOwnerNode(rawOwner, label = "下一责任人") {
      const info = conversationTaskOwnerDisplayMeta(rawOwner);
      const box = el("div", { class: "convtaskowner" });
      box.appendChild(el("div", { class: "convtaskowner-label", text: String(label || "").trim() || "下一责任人" }));
      box.appendChild(el("div", { class: "convtaskowner-name", text: info.text }));
      if (info.meta) box.appendChild(el("div", { class: "convtaskowner-meta", text: info.meta }));
      return box;
    }

    function cloneConversationTaskRoleMember(rawMember) {
      if (typeof rawMember === "string") {
        const text = String(rawMember || "").trim();
        return text ? { display_name: text, alias: text, agent_name: text } : null;
      }
      const member = (rawMember && typeof rawMember === "object") ? rawMember : null;
      return member ? { ...member } : null;
    }

    function cloneConversationTaskCustomRole(rawRole) {
      const role = (rawRole && typeof rawRole === "object") ? rawRole : null;
      if (!role) return null;
      return {
        ...role,
        members: Array.isArray(role.members) ? role.members.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
      };
    }

    function conversationTaskRoleMemberDisplayMeta(rawMember) {
      const member = (rawMember && typeof rawMember === "object") ? rawMember : {};
      const normalizeRoleText = typeof normalizeTaskRoleMemberDisplayText === "function"
        ? normalizeTaskRoleMemberDisplayText
        : (value) => String(value == null ? "" : value).replace(/`+/g, "").replace(/\s+/g, " ").trim();
      const text = normalizeRoleText(firstNonEmptyText([
        member.display_name,
        member.agent_alias,
        member.agent_name,
        member.name,
      ]) || "待补充") || "待补充";
      const metaParts = [];
      const channelText = String(member.channel_name || "").trim();
      const responsibilityText = String(member.responsibility || "").trim();
      if (channelText) metaParts.push(channelText);
      if (responsibilityText) metaParts.push(responsibilityText);
      return {
        text,
        meta: metaParts.join(" · "),
      };
    }

    function conversationTaskIdentityText(value) {
      return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[`"'“”‘’]/g, "")
        .replace(/\s+/g, "");
    }

    function pushConversationTaskIdentityText(target, value) {
      const raw = String(value || "").trim();
      if (!raw) return;
      const normalized = conversationTaskIdentityText(raw);
      if (normalized) target.add(normalized);
      raw.split(/\s*\/\s*/).forEach((part) => {
        const text = String(part || "").trim();
        if (!text || /^session[_\s-]?id\s*=/i.test(text)) return;
        const partNormalized = conversationTaskIdentityText(text);
        if (partNormalized) target.add(partNormalized);
      });
    }

    function conversationTaskRoleMemberIdentity(rawMember) {
      const member = typeof rawMember === "string"
        ? { display_name: rawMember, alias: rawMember, agent_name: rawMember }
        : ((rawMember && typeof rawMember === "object") ? rawMember : {});
      const meta = typeof taskRoleMemberDisplayMeta === "function"
        ? taskRoleMemberDisplayMeta(member)
        : conversationTaskRoleMemberDisplayMeta(member);
      const sessionIds = new Set();
      [
        member.session_id,
        member.sessionId,
        meta && meta.sessionId,
      ].forEach((value) => {
        const text = String(value || "").trim();
        if (text) sessionIds.add(text);
      });
      const agentNames = new Set();
      [
        member.display_name,
        member.displayName,
        member.agent_alias,
        member.alias,
        member.agent_name,
        member.agentName,
        member.name,
        meta && meta.text,
      ].forEach((value) => pushConversationTaskIdentityText(agentNames, value));
      const channelNames = new Set();
      [
        member.channel_name,
        member.channelName,
        meta && meta.channelName,
      ].forEach((value) => pushConversationTaskIdentityText(channelNames, value));
      const fullNames = new Set(agentNames);
      channelNames.forEach((channel) => {
        agentNames.forEach((agent) => {
          const composite = channel && agent ? (channel + "/" + agent) : "";
          if (composite) fullNames.add(composite);
        });
      });
      return { sessionIds, agentNames, channelNames, fullNames };
    }

    function conversationTaskSessionIdentity(session, ctx = {}) {
      const s = (session && typeof session === "object") ? session : {};
      const currentCtx = (ctx && typeof ctx === "object") ? ctx : {};
      const sessionIds = new Set();
      [
        currentCtx.sessionId,
        currentCtx.session_id,
        s.sessionId,
        s.session_id,
        s.id,
      ].forEach((value) => {
        const text = String(value || "").trim();
        if (text) sessionIds.add(text);
      });
      const agentNames = new Set();
      [
        typeof conversationAgentName === "function" ? conversationAgentName(s) : "",
        s.alias,
        s.display_name,
        s.displayName,
        s.agent_name,
        s.agentName,
      ].forEach((value) => pushConversationTaskIdentityText(agentNames, value));
      const channelNames = new Set();
      [
        currentCtx.channelName,
        currentCtx.channel_name,
        s.channel_name,
        s.channelName,
        s.primaryChannel,
        s.name,
      ].forEach((value) => pushConversationTaskIdentityText(channelNames, value));
      const fullNames = new Set(agentNames);
      channelNames.forEach((channel) => {
        agentNames.forEach((agent) => {
          const composite = channel && agent ? (channel + "/" + agent) : "";
          if (composite) fullNames.add(composite);
        });
      });
      return { sessionIds, agentNames, channelNames, fullNames };
    }

    function conversationTaskIdentityIntersects(left, right) {
      const a = left instanceof Set ? left : new Set();
      const b = right instanceof Set ? right : new Set();
      for (const value of a) {
        if (b.has(value)) return true;
      }
      return false;
    }

    function conversationTaskMainOwnerMembers(raw) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const responsibility = item.responsibilityModel && typeof item.responsibilityModel === "object"
        ? item.responsibilityModel
        : (item.responsibility_model && typeof item.responsibility_model === "object" ? item.responsibility_model : null);
      const candidates = [
        item.main_owner,
        item.mainOwner,
        responsibility && responsibility.main_owner,
        responsibility && responsibility.mainOwner,
      ];
      const mainOwner = candidates.find((value) => {
        if (Array.isArray(value)) return value.length > 0;
        if (value && typeof value === "object") return true;
        return String(value || "").trim();
      });
      if (!mainOwner) return [];
      return (Array.isArray(mainOwner) ? mainOwner : [mainOwner]).filter(Boolean);
    }

    function conversationTaskMainOwnerMatchesSession(row, session, ctx = {}) {
      const owners = conversationTaskMainOwnerMembers(row);
      if (!owners.length) return false;
      const sessionIdentity = conversationTaskSessionIdentity(session, ctx);
      return owners.some((owner) => {
        const ownerIdentity = conversationTaskRoleMemberIdentity(owner);
        if (conversationTaskIdentityIntersects(ownerIdentity.sessionIds, sessionIdentity.sessionIds)) return true;
        if (conversationTaskIdentityIntersects(ownerIdentity.agentNames, sessionIdentity.agentNames)) return true;
        if (conversationTaskIdentityIntersects(ownerIdentity.fullNames, sessionIdentity.fullNames)) return true;
        return false;
      });
    }

    function conversationTaskResponsibilityModel(raw) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const model = {
        main_owner: cloneConversationTaskRoleMember(conversationTaskMainOwnerMembers(item)[0]),
        collaborators: Array.isArray(item.collaborators) ? item.collaborators.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        validators: Array.isArray(item.validators) ? item.validators.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        challengers: Array.isArray(item.challengers) ? item.challengers.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        backup_owners: Array.isArray(item.backup_owners) ? item.backup_owners.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        management_slot: Array.isArray(item.management_slot) ? item.management_slot.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        custom_roles: Array.isArray(item.custom_roles) ? item.custom_roles.map(cloneConversationTaskCustomRole).filter(Boolean) : [],
      };
      model.hasData = !!(model.main_owner
        || model.collaborators.length
        || model.validators.length
        || model.challengers.length
        || model.backup_owners.length
        || model.management_slot.length
        || model.custom_roles.length);
      return model;
    }

    function buildConversationTaskRoleCard(rawMember, opts = {}) {
      const info = conversationTaskRoleMemberDisplayMeta(rawMember);
      const card = el("div", { class: "convtaskrolecard" + (opts.compact ? " is-compact" : "") });
      card.appendChild(el("div", {
        class: "convtaskrolecard-label",
        text: String(opts.label || "").trim() || "责任位",
      }));
      card.appendChild(el("div", { class: "convtaskrolecard-name", text: info.text }));
      if (info.meta) card.appendChild(el("div", { class: "convtaskrolecard-meta", text: info.meta }));
      return card;
    }

    function conversationTaskRolePreviewText(members, emptyText = "未配置") {
      const list = Array.isArray(members) ? members.filter(Boolean) : [];
      if (!list.length) return emptyText;
      const names = list
        .map((member) => conversationTaskRoleMemberDisplayMeta(member).text)
        .filter(Boolean);
      if (!names.length) return emptyText;
      if (names.length <= 2) return names.join(" · ");
      return names.slice(0, 2).join(" · ") + " 等 " + names.length + " 项";
    }

    function buildConversationTaskManagementOverviewNode(model) {
      const data = (model && typeof model === "object") ? model : conversationTaskResponsibilityModel(null);
      const members = Array.isArray(data.management_slot) ? data.management_slot : [];
      const card = el("div", { class: "convtaskroleoverview" });
      card.appendChild(el("div", { class: "convtaskroleoverview-label", text: "管理位概览" }));
      card.appendChild(el("div", {
        class: "convtaskroleoverview-text" + (!members.length ? " is-placeholder" : ""),
        text: conversationTaskRolePreviewText(members, "管理位待接入正式读模型"),
      }));
      card.appendChild(el("div", {
        class: "convtaskroleoverview-meta",
        text: members.length ? ("共 " + members.length + " 项") : "只读展示，不拆固定槽位",
      }));
      return card;
    }

    function buildConversationTaskResponsibilityRail(raw) {
      const model = conversationTaskResponsibilityModel(raw);
      if (!model.hasData) return null;
      const rail = el("div", { class: "convtaskrole-rail" });
      rail.appendChild(
        model.main_owner
          ? buildConversationTaskRoleCard(model.main_owner, { label: "主负责位", compact: true })
          : buildConversationTaskRoleCard({ display_name: "主负责位待接入正式读模型" }, { label: "主负责位", compact: true })
      );
      rail.appendChild(buildConversationTaskManagementOverviewNode(model));
      return rail;
    }

    function buildConversationTaskResponsibilitySummaryLine(raw) {
      const model = conversationTaskResponsibilityModel(raw);
      if (!model.hasData) return null;
      const line = el("div", { class: "convtaskrole-inline" });
      const mainOwnerText = model.main_owner
        ? conversationTaskRoleMemberDisplayMeta(model.main_owner).text
        : "待接入";
      const parts = ["主负责位 " + mainOwnerText];
      if (model.management_slot.length) {
        parts.push("管理位 " + conversationTaskRolePreviewText(model.management_slot, "未配置"));
      }
      line.appendChild(el("span", { class: "k", text: "责任位" }));
      line.appendChild(el("span", { class: "v", text: parts.join(" · ") }));
      return line;
    }

    function conversationTaskRoleLabel(roleKey = "") {
      const key = String(roleKey || "").trim().toLowerCase();
      if (key === "main_owner") return "主负责位";
      if (key === "collaborators") return "协同位";
      if (key === "validators") return "验证位";
      if (key === "challengers") return "质疑位";
      if (key === "backup_owners") return "备份位";
      if (key === "management_slot") return "管理位";
      return key ? "责任位" : "";
    }

    function conversationTaskCoreAgentEntryKey(roleKey, member, info) {
      const raw = (member && typeof member === "object") ? member : {};
      const display = (info && typeof info === "object") ? info : conversationTaskRoleMemberDisplayMeta(raw);
      const parts = [
        String(raw.session_id || raw.sessionId || "").trim(),
        String(raw.agent_id || raw.agentId || "").trim(),
        String(raw.agent_name || raw.agentName || "").trim(),
        String(display.text || "").trim().toLowerCase(),
      ].filter(Boolean);
      return parts.join("::");
    }

    function conversationTaskCoreAgentEntries(raw) {
      const model = conversationTaskResponsibilityModel(raw);
      const out = [];
      const seen = new Set();
      function push(roleKey, label, member, opts = {}) {
        const rawMember = (member && typeof member === "object") ? member : null;
        if (!rawMember) return;
        const info = conversationTaskRoleMemberDisplayMeta(rawMember);
        const text = String(info.text || "").trim();
        if (!text) return;
        const dedupeKey = conversationTaskCoreAgentEntryKey(roleKey, rawMember, info);
        if (dedupeKey && seen.has(dedupeKey)) return;
        if (dedupeKey) seen.add(dedupeKey);
        out.push({
          roleKey: String(roleKey || "").trim().toLowerCase(),
          roleLabel: String(label || "").trim() || conversationTaskRoleLabel(roleKey) || "责任位",
          text,
          meta: String(info.meta || "").trim(),
          emphasis: String(opts.emphasis || "secondary").trim().toLowerCase() || "secondary",
        });
      }

      if (model.main_owner) push("main_owner", "主负责位", model.main_owner, { emphasis: "primary" });
      model.collaborators.forEach((member) => push("collaborators", "协同位", member));
      model.validators.forEach((member) => push("validators", "验证位", member));
      model.challengers.forEach((member) => push("challengers", "质疑位", member));
      model.backup_owners.forEach((member) => push("backup_owners", "备份位", member));
      model.custom_roles.forEach((role) => {
        const label = String(role && role.name || "").trim() || "自定义责任位";
        (Array.isArray(role && role.members) ? role.members : []).forEach((member) => push("custom_role", label, member));
      });

      if (!out.length) {
        const owner = conversationTaskOwnerDisplayMeta((raw && raw.next_owner) || null);
        if (owner.text) {
          out.push({
            roleKey: "next_owner",
            roleLabel: "下一责任人",
            text: owner.text,
            meta: owner.meta,
            emphasis: "primary",
          });
        }
      }
      return out;
    }

    function buildConversationTaskAgentChip(entry) {
      const item = (entry && typeof entry === "object") ? entry : {};
      const chipNode = el("div", { class: "convtaskagentchip" });
      chipNode.appendChild(el("span", {
        class: "convtaskagentchip-role",
        text: String(item.roleLabel || "").trim() || "责任位",
      }));
      chipNode.appendChild(el("span", {
        class: "convtaskagentchip-name",
        text: String(item.text || "").trim() || "待补充",
      }));
      return chipNode;
    }

    function buildConversationTaskManagementHint(model) {
      const data = (model && typeof model === "object") ? model : conversationTaskResponsibilityModel(null);
      if (!Array.isArray(data.management_slot) || !data.management_slot.length) return null;
      return el("div", {
        class: "convtaskagents-management",
        text: "管理位概览 · " + conversationTaskRolePreviewText(data.management_slot, "未配置"),
      });
    }

    function buildConversationTaskCoreAgentCluster(raw, opts = {}) {
      const entries = conversationTaskCoreAgentEntries(raw);
      if (!entries.length) return null;
      const model = conversationTaskResponsibilityModel(raw);
      const secondaryLimit = Math.max(0, Number(opts.secondaryLimit || 3) || 3);
      const cluster = el("div", { class: "convtaskagents" + (opts.compact ? " is-compact" : "") });
      const primary = entries[0];
      const primaryNode = el("div", { class: "convtaskagents-primary" });
      primaryNode.appendChild(el("div", {
        class: "convtaskagents-primary-label",
        text: String(primary.roleLabel || "").trim() || "主负责位",
      }));
      primaryNode.appendChild(el("div", {
        class: "convtaskagents-primary-name",
        text: String(primary.text || "").trim() || "待补充",
      }));
      if (primary.meta) {
        primaryNode.appendChild(el("div", {
          class: "convtaskagents-primary-meta",
          text: String(primary.meta || "").trim(),
        }));
      }
      cluster.appendChild(primaryNode);

      const secondaryEntries = entries.slice(1);
      if (secondaryEntries.length) {
        const chips = el("div", { class: "convtaskagents-secondary" });
        secondaryEntries.slice(0, secondaryLimit).forEach((entry) => chips.appendChild(buildConversationTaskAgentChip(entry)));
        if (secondaryEntries.length > secondaryLimit) {
          chips.appendChild(el("div", {
            class: "convtaskagentchip is-overflow",
            text: "+" + (secondaryEntries.length - secondaryLimit),
          }));
        }
        cluster.appendChild(chips);
      }

      const managementHint = buildConversationTaskManagementHint(model);
      if (managementHint) cluster.appendChild(managementHint);
      return cluster;
    }

    function conversationTaskProgressText(raw) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const latestActionText = String(item.latest_action_text || "").trim();
      if (latestActionText) return latestActionText;
      const summaryText = String(item.task_summary_text || "").trim();
      if (summaryText) return summaryText;
      return "最近暂无补充进展。";
    }

    function buildConversationTaskRoleGroup(label, members, opts = {}) {
      const list = Array.isArray(members) ? members.filter(Boolean) : [];
      if (!list.length) return null;
      const block = el("div", { class: "conv-task-role-group" });
      const title = String(opts.title || label || "").trim();
      block.appendChild(el("div", {
        class: "conv-task-role-group-title",
        text: title + (list.length > 1 ? (" · " + list.length + " 项") : ""),
      }));
      const items = el("div", { class: "conv-task-role-members" });
      list.forEach((member) => items.appendChild(buildConversationTaskRoleCard(member, { label })));
      block.appendChild(items);
      return block;
    }

    function buildConversationTaskCustomRoleGroup(role) {
      const item = (role && typeof role === "object") ? role : null;
      if (!item) return null;
      const block = buildConversationTaskRoleGroup(item.name || "自定义责任位", item.members || [], {
        title: String(item.name || "自定义责任位").trim(),
      });
      if (!block) return null;
      const responsibilityText = String(item.responsibility || "").trim();
      if (responsibilityText) {
        block.appendChild(el("div", { class: "conv-task-role-group-note", text: responsibilityText }));
      }
      return block;
    }

    function buildConversationTaskResponsibilitySection(raw) {
      const model = conversationTaskResponsibilityModel(raw);
      if (!model.hasData) return null;
      const section = el("section", { class: "conv-task-detail-section" });
      section.appendChild(el("div", { class: "conv-task-detail-section-title", text: "责任位" }));
      const mainRow = el("div", { class: "conv-task-role-main" });
      mainRow.appendChild(
        model.main_owner
          ? buildConversationTaskRoleCard(model.main_owner, { label: "主负责位" })
          : buildConversationTaskRoleCard({ display_name: "主负责位待接入正式读模型" }, { label: "主负责位" })
      );
      if (model.management_slot.length) mainRow.appendChild(buildConversationTaskManagementOverviewNode(model));
      section.appendChild(mainRow);
      const groups = el("div", { class: "conv-task-role-groups" });
      [
        buildConversationTaskRoleGroup("协同位", model.collaborators),
        buildConversationTaskRoleGroup("验证位", model.validators),
        buildConversationTaskRoleGroup("质疑位", model.challengers),
        buildConversationTaskRoleGroup("备份位", model.backup_owners),
        buildConversationTaskRoleGroup("管理位", model.management_slot),
      ].filter(Boolean).forEach((node) => groups.appendChild(node));
      model.custom_roles.forEach((role) => {
        const node = buildConversationTaskCustomRoleGroup(role);
        if (node) groups.appendChild(node);
      });
      if (groups.childNodes.length) section.appendChild(groups);
      return section;
    }

    function buildConversationTaskMetaLine(parts = []) {
      const bits = (Array.isArray(parts) ? parts : []).map((part) => String(part || "").trim()).filter(Boolean);
      if (!bits.length) return null;
      return el("div", { class: "convtaskmeta", text: bits.join(" · ") });
    }

    function conversationTaskGroupLabel(groupTitle = "", relation = "") {
      const explicit = String(groupTitle || "").trim();
      if (explicit) return explicit;
      const key = String(relation || "").trim().toLowerCase();
      if (key === "current") return "当前任务";
      if (key === "created" || key === "tracking") return "相关任务";
      return "会话任务";
    }

    function conversationTaskRelationLabel(relation = "") {
      const key = String(relation || "").trim().toLowerCase();
      if (key === "created") return "本轮新建";
      if (key === "tracking") return "后续跟进";
      if (key === "current") return "当前任务";
      return "";
    }

    function conversationTaskActivityCountText(value) {
      const count = Math.max(0, Number(value || 0) || 0);
      if (!count) return "";
      return count > 99 ? "99+条动态" : (count + "条动态");
    }

    function buildConversationTaskActionSummaryMap(actions = []) {
      const map = Object.create(null);
      (Array.isArray(actions) ? actions : []).forEach((row) => {
        const key = conversationTaskStableKey(row);
        if (!key) return;
        if (!map[key]) map[key] = { count: 0, latest: null };
        map[key].count += 1;
        if (!map[key].latest) map[key].latest = row;
      });
      return map;
    }

    function mergeConversationTaskActivity(row, actionMap) {
      const item = (row && typeof row === "object") ? { ...row } : {};
      const key = conversationTaskStableKey(item);
      const summary = key && actionMap ? actionMap[key] : null;
      const latest = summary && summary.latest && typeof summary.latest === "object" ? summary.latest : null;
      if (latest) {
        if (String(latest.action_kind || "").trim()) item.latest_action_kind = String(latest.action_kind || "").trim();
        if (String(latest.action_text || "").trim()) item.latest_action_text = String(latest.action_text || "").trim();
        if (String(latest.at || "").trim()) item.latest_action_at = String(latest.at || "").trim();
        item.latest_action_source = String(firstNonEmptyText([
          latest.source_agent_name,
          latest.source_channel,
        ]) || "").trim();
      }
      const fallbackCount = (item.latest_action_kind || item.latest_action_text || item.latest_action_at) ? 1 : 0;
      item.activity_count = summary ? Math.max(summary.count, fallbackCount) : fallbackCount;
      item.relation_label = conversationTaskRelationLabel(item.relation);
      return item;
    }

    function cloneConversationTaskDetailFallback(row) {
      const item = (row && typeof row === "object") ? row : null;
      if (!item) return null;
      return {
        ...item,
        next_owner: item.next_owner && typeof item.next_owner === "object"
          ? { ...item.next_owner }
          : item.next_owner || null,
        main_owner: cloneConversationTaskRoleMember(conversationTaskMainOwnerMembers(item)[0]),
        collaborators: Array.isArray(item.collaborators) ? item.collaborators.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        validators: Array.isArray(item.validators) ? item.validators.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        challengers: Array.isArray(item.challengers) ? item.challengers.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        backup_owners: Array.isArray(item.backup_owners) ? item.backup_owners.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        management_slot: Array.isArray(item.management_slot) ? item.management_slot.map(cloneConversationTaskRoleMember).filter(Boolean) : [],
        custom_roles: Array.isArray(item.custom_roles) ? item.custom_roles.map(cloneConversationTaskCustomRole).filter(Boolean) : [],
        task_summary_text: String(firstNonEmptyText([item.task_summary_text, item.summary, item.excerpt]) || "").trim(),
        task_title: String(firstNonEmptyText([item.task_title, item.taskTitle, item.title, item.name]) || "").trim(),
        task_path: String(firstNonEmptyText([item.task_path, item.taskPath, item.path]) || "").trim(),
        task_primary_status: String(firstNonEmptyText([item.task_primary_status, item.primary_status, item.status]) || "").trim(),
        latest_action_text: String(firstNonEmptyText([item.latest_action_text, item.latestActionText]) || "").trim(),
        latest_action_at: String(firstNonEmptyText([item.latest_action_at, item.latestActionAt, item.updated_at]) || "").trim(),
      };
    }

    function normalizeConversationTaskStableId(value) {
      return String(value || "").trim();
    }

    function conversationTaskStableId(row) {
      const item = (row && typeof row === "object") ? row : null;
      return normalizeConversationTaskStableId(firstNonEmptyText([
        item && item.task_id,
        item && item.taskId,
        item && item.id,
      ]) || "");
    }

    function conversationTaskStablePath(row) {
      const item = (row && typeof row === "object") ? row : null;
      return String(firstNonEmptyText([
        item && item.task_path,
        item && item.taskPath,
        item && item.path,
      ]) || "").trim();
    }

    function conversationTaskStableKey(row) {
      const taskId = conversationTaskStableId(row);
      if (taskId) return "task_id::" + taskId;
      const taskPath = conversationTaskStablePath(row);
      if (taskPath) return "task_path::" + taskPath;
      return "";
    }

    function ensureConversationTaskDetailViewerState() {
      const base = (PCONV.taskDetailViewer && typeof PCONV.taskDetailViewer === "object") ? PCONV.taskDetailViewer : {};
      const state = {
        open: !!base.open,
        sessionKey: String(base.sessionKey || "").trim(),
        taskId: normalizeConversationTaskStableId(base.taskId || ""),
        taskPath: String(base.taskPath || "").trim(),
        groupTitle: String(base.groupTitle || "").trim(),
        showActionContext: !!base.showActionContext,
        fallbackRef: cloneConversationTaskDetailFallback(base.fallbackRef),
      };
      PCONV.taskDetailViewer = state;
      return state;
    }

    function ensureConversationTaskDrawerRenderState() {
      const base = (PCONV.taskDrawerRenderState && typeof PCONV.taskDrawerRenderState === "object")
        ? PCONV.taskDrawerRenderState
        : {};
      const state = {
        sessionKey: String(base.sessionKey || "").trim(),
        signature: String(base.signature || "").trim(),
      };
      PCONV.taskDrawerRenderState = state;
      return state;
    }

    function resetConversationTaskDrawerRenderState() {
      const state = ensureConversationTaskDrawerRenderState();
      state.sessionKey = "";
      state.signature = "";
      return state;
    }

    function ensureConversationTaskFilePreviewCache() {
      if (!PCONV.taskFilePreviewCache || typeof PCONV.taskFilePreviewCache !== "object") {
        PCONV.taskFilePreviewCache = Object.create(null);
      }
      return PCONV.taskFilePreviewCache;
    }

    function getConversationTaskFilePreviewEntry(taskPath) {
      const key = String(taskPath || "").trim();
      if (!key) return null;
      const cache = ensureConversationTaskFilePreviewCache();
      if (!cache[key] || typeof cache[key] !== "object") {
        cache[key] = {
          taskPath: key,
          loading: false,
          loaded: false,
          error: "",
          item: null,
          loadedAt: "",
        };
      }
      return cache[key];
    }

    function rerenderConversationTaskDetailViewerForPath(taskPath) {
      const viewer = ensureConversationTaskDetailViewerState();
      const key = String(taskPath || "").trim();
      if (!viewer.open || !key || viewer.taskPath !== key) return;
      renderConversationTaskDetailViewer(currentConversationTaskPayload());
    }

    function requestConversationTaskFilePreview(taskPath, opts = {}) {
      const entry = getConversationTaskFilePreviewEntry(taskPath);
      if (!entry) return null;
      const force = !!opts.force;
      if (entry.loading) return entry;
      if (!force && (entry.loaded || entry.error)) return entry;
      entry.loading = true;
      entry.error = "";
      if (force) {
        entry.loaded = false;
        entry.item = null;
      }
      (async () => {
        try {
          const resp = await fetch("/api/fs/read?path=" + encodeURIComponent(entry.taskPath), {
            headers: authHeaders({}),
            credentials: "same-origin",
          });
          if (!resp.ok) {
            throw new Error(await parseResponseDetail(resp) || ("HTTP " + resp.status));
          }
          const data = await resp.json().catch(() => null);
          const item = (data && data.ok && data.item && typeof data.item === "object") ? data.item : null;
          if (!item) throw new Error("只读文件链路未返回可读取正文。");
          entry.item = {
            path: String(item.path || entry.taskPath).trim() || entry.taskPath,
            name: String(item.name || "").trim(),
            kind: String(item.kind || "").trim(),
            is_text: !!item.is_text,
            mime_type: String(item.mime_type || "").trim(),
            preview_mode: String(item.preview_mode || "").trim().toLowerCase(),
            truncated: !!item.truncated,
            content: String(item.content || ""),
          };
          entry.loaded = true;
          entry.loadedAt = new Date().toISOString();
        } catch (err) {
          entry.loaded = false;
          entry.item = null;
          entry.error = String((err && err.message) || err || "正文读取失败").trim() || "正文读取失败";
        } finally {
          entry.loading = false;
          rerenderConversationTaskDetailViewerForPath(entry.taskPath);
        }
      })();
      return entry;
    }

    function resetConversationTaskDetailViewer(opts = {}) {
      const viewer = ensureConversationTaskDetailViewerState();
      const clearSession = opts.clearSession !== false;
      viewer.open = false;
      viewer.taskId = "";
      viewer.taskPath = "";
      viewer.groupTitle = "";
      viewer.showActionContext = false;
      viewer.fallbackRef = null;
      if (clearSession) viewer.sessionKey = "";
      return viewer;
    }

    function removeConversationTaskDetailViewerMask() {
      const existing = document.getElementById("convTaskDetailViewerMask");
      if (existing) existing.remove();
    }

    function conversationTaskSelectionTitle(viewer) {
      const item = viewer && viewer.fallbackRef && typeof viewer.fallbackRef === "object"
        ? viewer.fallbackRef
        : null;
      return String(firstNonEmptyText([
        item && item.task_title,
        item && item.taskTitle,
      ]) || "").trim();
    }

    function conversationTaskMatchesViewerSelection(row, viewer) {
      const item = (row && typeof row === "object") ? row : null;
      if (!item) return false;
      const selectedTaskId = normalizeConversationTaskStableId((viewer && viewer.taskId) || "");
      const selectedPath = String((viewer && viewer.taskPath) || "").trim();
      const selectedTitle = conversationTaskSelectionTitle(viewer);
      const rowTaskId = conversationTaskStableId(item);
      const rowPath = conversationTaskStablePath(item);
      const rowTitle = String(firstNonEmptyText([item.task_title, item.taskTitle]) || "").trim();
      if (selectedTaskId && rowTaskId && rowTaskId === selectedTaskId) return true;
      if (selectedPath && rowPath && rowPath === selectedPath) return true;
      if (selectedTitle && rowTitle && rowTitle === selectedTitle) return true;
      return false;
    }

    function buildConversationTaskDetailLatestActionFromRef(item) {
      const ref = (item && typeof item === "object") ? item : null;
      if (!ref) return null;
      const actionKind = String(ref.latest_action_kind || "").trim();
      const actionText = String(ref.latest_action_text || "").trim();
      const actionAt = String(ref.latest_action_at || "").trim();
      if (!actionKind && !actionText && !actionAt) return null;
      return {
        task_id: conversationTaskStableId(ref),
        task_path: String(ref.task_path || "").trim(),
        task_title: String(ref.task_title || "").trim(),
        action_kind: actionKind,
        action_text: actionText,
        status: String(ref.task_primary_status || "").trim().toLowerCase(),
        source_channel: "",
        source_agent_name: "",
        at: actionAt,
      };
    }

    function buildConversationTaskDetailContextItems(actions, latestAction) {
      const rows = Array.isArray(actions) ? actions.slice() : [];
      const fallback = latestAction && typeof latestAction === "object" ? latestAction : null;
      if (!fallback) return rows;
      const fallbackKey = [
        conversationTaskStableKey(fallback),
        String(fallback.action_kind || "").trim(),
        String(fallback.action_text || "").trim(),
        String(fallback.at || "").trim(),
      ].join("::");
      const exists = rows.some((row) => [
        conversationTaskStableKey(row),
        String(row && row.action_kind || "").trim(),
        String(row && row.action_text || "").trim(),
        String(row && row.at || "").trim(),
      ].join("::") === fallbackKey);
      if (!exists) rows.unshift(fallback);
      return rows;
    }

    function resolveConversationTaskDetailView(view, viewerState = null) {
      const viewer = viewerState || ensureConversationTaskDetailViewerState();
      const payload = (view && typeof view === "object") ? view : {};
      const fallback = viewer.fallbackRef && typeof viewer.fallbackRef === "object"
        ? viewer.fallbackRef
        : null;
      const refs = [];
      if (payload.currentRef) refs.push({ ...payload.currentRef, __groupTitle: "当前任务" });
      (Array.isArray(payload.createdRows) ? payload.createdRows : []).forEach((row) => refs.push({ ...row, __groupTitle: "相关任务" }));
      (Array.isArray(payload.trackingRows) ? payload.trackingRows : []).forEach((row) => refs.push({ ...row, __groupTitle: "相关任务" }));
      const matchedRef = refs.find((row) => conversationTaskMatchesViewerSelection(row, viewer))
        || (fallback && (fallback.task_primary_status
          || fallback.next_owner
          || (conversationTaskResponsibilityModel(fallback).hasData)
          || fallback.latest_action_kind
          || fallback.latest_action_text)
          ? fallback
          : null);
      const matchedActions = (Array.isArray(payload.actions) ? payload.actions : [])
        .filter((row) => conversationTaskMatchesViewerSelection(row, viewer));
      const fallbackAction = (fallback && (fallback.action_kind || fallback.action_text || fallback.status || fallback.at))
        ? fallback
        : null;
      const latestAction = matchedActions[0]
        || fallbackAction
        || buildConversationTaskDetailLatestActionFromRef(matchedRef);
      const titleSource = matchedRef || latestAction || fallback || null;
      if (!titleSource) return null;
      const taskId = String(firstNonEmptyText([
        matchedRef && matchedRef.task_id,
        matchedRef && matchedRef.taskId,
        matchedRef && matchedRef.id,
        latestAction && latestAction.task_id,
        fallback && fallback.task_id,
        fallback && fallback.taskId,
        fallback && fallback.id,
      ]) || "").trim();
      const taskPath = String(firstNonEmptyText([
        matchedRef && matchedRef.task_path,
        matchedRef && matchedRef.taskPath,
        matchedRef && matchedRef.path,
        latestAction && latestAction.task_path,
        fallback && fallback.task_path,
        fallback && fallback.taskPath,
        fallback && fallback.path,
      ]) || "").trim();
      const relation = String(firstNonEmptyText([
        matchedRef && matchedRef.relation,
        fallback && fallback.relation,
      ]) || "").trim().toLowerCase();
      const groupTitle = conversationTaskGroupLabel(
        firstNonEmptyText([
          viewer.groupTitle,
          matchedRef && matchedRef.__groupTitle,
        ]) || "",
        relation
      );
      const relationLabel = conversationTaskRelationLabel(relation);
      const statusText = String(firstNonEmptyText([
        matchedRef && matchedRef.task_primary_status,
        matchedRef && matchedRef.primary_status,
        matchedRef && matchedRef.status,
        latestAction && latestAction.status,
        fallback && fallback.task_primary_status,
        fallback && fallback.primary_status,
        fallback && fallback.status,
      ]) || "").trim();
      const latestActionLabel = conversationTaskActionLabel(firstNonEmptyText([
        latestAction && latestAction.action_kind,
        matchedRef && matchedRef.latest_action_kind,
      ]) || "");
      const latestActionText = String(firstNonEmptyText([
        latestAction && latestAction.action_text,
        matchedRef && matchedRef.latest_action_text,
        matchedRef && matchedRef.latestActionText,
        fallback && fallback.latest_action_text,
        fallback && fallback.latestActionText,
      ]) || "").trim();
      const latestActionAt = String(firstNonEmptyText([
        latestAction && latestAction.at,
        matchedRef && matchedRef.latest_action_at,
        matchedRef && matchedRef.latestActionAt,
        matchedRef && matchedRef.updated_at,
        fallback && fallback.latest_action_at,
        fallback && fallback.latestActionAt,
        fallback && fallback.updated_at,
      ]) || "").trim();
      const latestActionSource = String(firstNonEmptyText([
        latestAction && latestAction.source_agent_name,
        latestAction && latestAction.source_channel,
      ]) || "").trim();
      const sourceText = String(firstNonEmptyText([
        matchedRef && matchedRef.source,
        latestAction && latestAction.source_channel,
      ]) || "").trim();
      const owner = matchedRef && matchedRef.next_owner ? matchedRef.next_owner : null;
      const responsibilityModel = conversationTaskResponsibilityModel(matchedRef || fallback || null);
      const taskSummaryText = String(firstNonEmptyText([
        matchedRef && matchedRef.task_summary_text,
        matchedRef && matchedRef.summary,
        matchedRef && matchedRef.excerpt,
        fallback && fallback.task_summary_text,
        fallback && fallback.summary,
        fallback && fallback.excerpt,
      ]) || "").trim();
      const taskSummaryPlaceholder = "任务一句话说明待接入正式真源。";
      const whyParts = [];
      if (groupTitle) whyParts.push("当前在“" + groupTitle + "”中展示。");
      if (relationLabel && relationLabel !== groupTitle) whyParts.push("关联关系为“" + relationLabel + "”。");
      if (sourceText) whyParts.push("来源标记为 " + sourceText + "。");
      const contextItems = buildConversationTaskDetailContextItems(matchedActions, latestAction);
      return {
        title: conversationTaskTitleText(titleSource),
        taskId,
        taskPath,
        groupTitle,
        relationLabel,
        statusText,
        latestActionLabel,
        latestActionText: latestActionText || "最近暂无任务动作补充。",
        latestActionAt,
        latestActionSource,
        taskSummaryText,
        taskSummaryPlaceholder,
        sourceText,
        whyAppearsText: whyParts.join(" "),
        firstSeenAt: String(matchedRef && matchedRef.first_seen_at || "").trim(),
        lastSeenAt: String(matchedRef && matchedRef.last_seen_at || "").trim(),
        owner,
        responsibilityModel,
        latestAction,
        contextItems,
        hasActionContext: contextItems.length > 0,
      };
    }

    function renderConversationTaskDetailInfoRow(label, value, opts = {}) {
      const text = String(value || "").trim();
      if (!text) return null;
      const row = el("div", { class: "conv-task-detail-info-row" + (opts.stack ? " is-stack" : "") });
      row.appendChild(el("div", { class: "conv-task-detail-info-label", text: String(label || "").trim() || "-" }));
      row.appendChild(el("div", { class: "conv-task-detail-info-value" + (opts.mono ? " is-mono" : ""), text }));
      return row;
    }

    function buildConversationTaskDetailReadingBody(entry) {
      const state = (entry && typeof entry === "object") ? entry : {};
      const item = (state.item && typeof state.item === "object") ? state.item : null;
      const body = el("div", { class: "conv-task-detail-reading-body" });
      if (!item || !String(item.content || "")) {
        body.appendChild(el("div", {
          class: "conv-task-detail-reading-empty",
          text: "只读链路尚未返回可显示的正文内容。",
        }));
        return body;
      }
      if (!item.is_text) {
        body.appendChild(el("div", {
          class: "conv-task-detail-reading-empty",
          text: "当前任务文件不是文本类型，页内不做二次解析，请直接打开原任务文件阅读。",
        }));
        return body;
      }
      const mode = String(item.preview_mode || "").trim().toLowerCase();
      if (mode === "markdown" && typeof markdownToHtml === "function") {
        body.classList.add("is-markdown");
        body.innerHTML = markdownToHtml(String(item.content || ""));
        if (typeof enhanceMessageInteractiveObjects === "function") {
          enhanceMessageInteractiveObjects(body, { force: true });
        }
        return body;
      }
      body.classList.add("is-plain");
      const pre = el("pre", {
        class: "conv-task-detail-reading-pre",
        text: String(item.content || ""),
      });
      body.appendChild(pre);
      return body;
    }

    function buildConversationTaskDetailReadingSection(detail) {
      const taskPath = String(detail && detail.taskPath || "").trim();
      const section = el("section", { class: "conv-task-detail-section conv-task-detail-reading" });
      const titleRow = el("div", { class: "conv-task-detail-reading-head" });
      titleRow.appendChild(el("div", { class: "conv-task-detail-section-title", text: "完整任务正文" }));
      if (taskPath) titleRow.appendChild(chip("只读接线", "muted"));
      section.appendChild(titleRow);
      if (!taskPath) {
        section.appendChild(el("div", {
          class: "conv-task-detail-reading-empty",
          text: "当前任务缺少 task_path，暂时无法接入正文阅读层。",
        }));
        return section;
      }

      const entry = requestConversationTaskFilePreview(taskPath);
      const item = (entry && entry.item && typeof entry.item === "object") ? entry.item : null;
      const meta = buildConversationTaskMetaLine([
        taskPath,
        item && item.preview_mode ? ("预览 " + item.preview_mode) : "",
        item && item.truncated ? "当前预览已截断" : "",
      ]);
      if (meta) meta.classList.add("conv-task-detail-reading-meta");
      if (meta) section.appendChild(meta);

      if (entry && entry.loading) {
        section.appendChild(el("div", {
          class: "conv-task-detail-reading-loading",
          text: "正在通过 /api/fs/read 读取任务正文…",
        }));
      } else if (entry && entry.error) {
        section.appendChild(el("div", {
          class: "conv-task-detail-reading-error",
          text: "正文读取失败：" + entry.error,
        }));
      } else {
        section.appendChild(buildConversationTaskDetailReadingBody(entry));
      }

      const noteText = item && item.truncated
        ? "当前只读预览已截断；若要继续深读，请使用底部“查看原任务文件”。"
        : "当前正文按只读文件链路接入，不在页面侧生成第二套正文真源。";
      section.appendChild(el("div", {
        class: "conv-task-detail-reading-note",
        text: noteText,
      }));
      return section;
    }

    function closeConversationTaskDetailViewer() {
      if (typeof closeUnifiedTaskDetail === "function") closeUnifiedTaskDetail({ notify: false });
      resetConversationTaskDetailViewer();
      renderConversationTaskDetailViewer();
    }

    function toggleConversationTaskDetailActionContext() {
      const viewer = ensureConversationTaskDetailViewerState();
      if (!viewer.open) return;
      viewer.showActionContext = !viewer.showActionContext;
      renderConversationTaskDetailViewer(currentConversationTaskPayload());
    }

    function openConversationTaskDetailViewer(row, opts = {}) {
      const viewer = ensureConversationTaskDetailViewerState();
      const item = (row && typeof row === "object") ? row : null;
      viewer.open = true;
      viewer.sessionKey = String(firstNonEmptyText([
        opts.sessionKey,
        PCONV.taskDrawerSessionKey,
        currentConvComposerDraftKey(),
      ]) || "").trim();
      viewer.taskId = conversationTaskStableId(item);
      viewer.taskPath = conversationTaskStablePath(item);
      viewer.groupTitle = conversationTaskGroupLabel(opts.groupTitle || "", item && item.relation);
      viewer.showActionContext = false;
      viewer.fallbackRef = cloneConversationTaskDetailFallback(item);
      renderConversationTaskDetailViewer(currentConversationTaskPayload());
    }

    function bindConversationTaskCardOpenDetail(node, row, opts = {}) {
      if (!node || typeof opts.onOpenDetail !== "function") return;
      node.classList.add("is-clickable");
      node.tabIndex = 0;
      node.setAttribute("role", "button");
      node.addEventListener("click", () => opts.onOpenDetail(row, opts));
      node.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        opts.onOpenDetail(row, opts);
      });
    }

    function buildConversationTaskRefCard(row, opts = {}) {
      const item = (row && typeof row === "object") ? row : {};
      const compact = !!opts.compact;
      const relationLabel = String(item.relation_label || conversationTaskRelationLabel(item.relation) || "").trim();
      if (typeof buildUnifiedTaskListCard === "function") {
        const activityCountText = conversationTaskActivityCountText(item.activity_count);
        const metaItems = [];
        if (activityCountText) metaItems.push([activityCountText, "muted"]);
        if (item.latest_action_kind) {
          metaItems.push([
            conversationTaskActionLabel(item.latest_action_kind),
            conversationTaskActionTone(item.latest_action_kind),
          ]);
        }
        return buildUnifiedTaskListCard({
          ...item,
          title: conversationTaskTitleText(item),
          latest_action_text: String(item.latest_action_text || "").trim() || "最近暂无补充说明。",
        }, {
          source: "conversation-task-panel",
          projectId: typeof STATE !== "undefined" && STATE ? STATE.project : "",
          groupTitle: relationLabel && relationLabel !== "当前任务" ? relationLabel : "",
          compact: true,
          panel: true,
          metaItems,
          onOpen: () => {
            if (typeof opts.onOpenDetail === "function") opts.onOpenDetail(item, opts);
          },
        });
      }
      const card = el("div", { class: "convtaskcard" + (compact ? " compact" : "") });
      const titleRow = el("div", { class: "convtaskcard-title-row" });
      titleRow.appendChild(el("div", {
        class: "convtaskcard-title",
        text: conversationTaskTitleText(item),
        title: String(item.task_title || item.task_path || "").trim(),
      }));
      if (item.task_primary_status) {
        titleRow.appendChild(chip(String(item.task_primary_status || ""), conversationTaskStatusTone(item.task_primary_status)));
      }
      if (relationLabel && relationLabel !== "当前任务") {
        titleRow.appendChild(chip(relationLabel, "muted"));
      }
      const activityCountText = conversationTaskActivityCountText(item.activity_count);
      if (activityCountText) {
        titleRow.appendChild(chip(activityCountText, "muted"));
      }
      if (item.latest_action_kind) {
        titleRow.appendChild(chip(
          conversationTaskActionLabel(item.latest_action_kind),
          conversationTaskActionTone(item.latest_action_kind)
        ));
      }
      card.appendChild(titleRow);

      const agentCluster = buildConversationTaskCoreAgentCluster(item, { compact, secondaryLimit: compact ? 2 : 3 });
      if (agentCluster) card.appendChild(agentCluster);

      const activity = el("div", { class: "convtaskcard-activity" });
      activity.appendChild(el("div", { class: "convtaskcard-activity-label", text: "最近活动" }));
      activity.appendChild(el("div", {
        class: "convtaskcard-activity-text",
        text: String(item.latest_action_text || "").trim() || "最近暂无补充说明。",
      }));
      const actionAt = compactDateTime(item.latest_action_at) || shortDateTime(item.latest_action_at);
      const activityMeta = buildConversationTaskMetaLine([
        actionAt ? ("时间 " + actionAt) : "",
        firstNonEmptyText([
          item.latest_action_source,
          item.source,
        ]) ? ("来源 " + firstNonEmptyText([
          item.latest_action_source,
          item.source,
        ])) : "",
      ]);
      if (activityMeta) {
        activityMeta.classList.add("convtaskcard-activity-meta");
        activity.appendChild(activityMeta);
      }
      card.appendChild(activity);
      bindConversationTaskCardOpenDetail(card, item, opts);
      return card;
    }

    function buildConversationTaskActionCard(row, opts = {}) {
      const item = (row && typeof row === "object") ? row : {};
      const card = el("div", { class: "convtaskaction" });
      const titleRow = el("div", { class: "convtaskaction-title-row" });
      titleRow.appendChild(el("div", {
        class: "convtaskaction-title",
        text: conversationTaskTitleText(item),
        title: String(item.task_title || item.task_path || "").trim(),
      }));
      if (item.action_kind) titleRow.appendChild(chip(conversationTaskActionLabel(item.action_kind), conversationTaskActionTone(item.action_kind, item.status)));
      if (item.status && item.status !== "done" && item.status !== "pending") {
        titleRow.appendChild(chip(String(item.status || ""), conversationTaskActionTone(item.action_kind, item.status)));
      }
      card.appendChild(titleRow);
      card.appendChild(el("div", {
        class: "convtaskaction-text",
        text: String(item.action_text || "").trim() || "最近暂无补充说明。",
      }));
      const meta = buildConversationTaskMetaLine([
        firstNonEmptyText([item.source_agent_name, item.source_channel]),
        compactDateTime(item.at) || shortDateTime(item.at),
      ]);
      if (meta) card.appendChild(meta);
      if (item.task_path) card.appendChild(el("div", { class: "convtaskpath", text: item.task_path, title: item.task_path }));
      bindConversationTaskCardOpenDetail(card, item, opts);
      return card;
    }

    function renderConversationTaskGroup(title, rows, builder, opts = {}) {
      const list = Array.isArray(rows) ? rows : [];
      const limit = Math.max(1, Number(opts.limit || list.length || 1));
      const visible = list.slice(0, limit);
      const block = el("section", { class: "convtaskgroup" + (opts.compact ? " is-compact" : "") });
      const head = el("div", { class: "convtaskgroup-head" });
      head.appendChild(el("div", { class: "convtaskgroup-title", text: String(title || "").trim() }));
      head.appendChild(el("div", {
        class: "convtaskgroup-count",
        text: list.length ? ("共 " + list.length + " 项") : "当前为空",
      }));
      block.appendChild(head);
      if (!visible.length) {
        block.appendChild(el("div", {
          class: opts.error ? "convtaskerror" : (opts.loading ? "convtaskloading" : "convtaskempty"),
          text: String(opts.emptyText || "").trim() || "当前没有可展示内容。",
        }));
        return block;
      }
      const listNode = el("div", { class: "convtaskgroup-list" + (opts.singleColumn ? " single-column" : "") });
      visible.forEach((row) => {
        const node = builder(row);
        if (node) listNode.appendChild(node);
      });
      block.appendChild(listNode);
      if (list.length > visible.length) {
        block.appendChild(el("div", {
          class: "convtaskoverflow",
          text: "其余 " + (list.length - visible.length) + " 项已收起。",
        }));
      }
      return block;
    }

    function resolveConversationTaskTrackingPayload(payload = {}) {
      const src = (payload && typeof payload === "object") ? payload : {};
      const tracking = normalizeTaskTrackingClient(src.taskTracking || null);
      const normalizeCurrentTaskSummaryRef = (raw) => {
        if (!raw || typeof raw !== "object") return null;
        if (typeof normalizeConversationTaskRef === "function") {
          return normalizeConversationTaskRef(raw, "current");
        }
        const taskId = String(firstNonEmptyText([raw.task_id, raw.taskId]) || "").trim();
        const taskPath = String(firstNonEmptyText([raw.task_path, raw.taskPath]) || "").trim();
        const taskTitle = String(firstNonEmptyText([raw.task_title, raw.taskTitle]) || "").trim();
        if (!taskId && !taskPath && !taskTitle) return null;
        return {
          task_id: taskId,
          task_path: taskPath,
          task_title: taskTitle || taskPath || taskId,
          task_primary_status: String(firstNonEmptyText([raw.task_primary_status, raw.taskPrimaryStatus]) || "").trim(),
          task_summary_text: String(firstNonEmptyText([raw.task_summary_text, raw.taskSummaryText]) || "").trim(),
          latest_action_at: String(firstNonEmptyText([raw.latest_action_at, raw.latestActionAt]) || "").trim(),
          latest_action_kind: String(firstNonEmptyText([raw.latest_action_kind, raw.latestActionKind]) || "").trim().toLowerCase(),
          latest_action_text: String(firstNonEmptyText([raw.latest_action_text, raw.latestActionText]) || "").trim(),
          relation: "current",
        };
      };
      const loading = !!src.loading;
      const errorText = String(src.error || "").trim();
      const currentTaskSummaryRef = normalizeCurrentTaskSummaryRef(src.currentTaskSummary || null);
      const currentTaskUpdatedAt = String(firstNonEmptyText([src.currentTaskUpdatedAt, src.current_task_updated_at]) || "").trim();
      let effectiveTracking = tracking && typeof tracking === "object"
        ? {
          ...tracking,
          conversation_task_refs: Array.isArray(tracking.conversation_task_refs) ? tracking.conversation_task_refs.slice() : [],
          recent_task_actions: Array.isArray(tracking.recent_task_actions) ? tracking.recent_task_actions.slice() : [],
        }
        : null;
      let currentRef = effectiveTracking && effectiveTracking.current_task_ref ? effectiveTracking.current_task_ref : null;
      if (currentTaskSummaryRef) {
        currentRef = currentRef
          ? { ...currentRef, ...currentTaskSummaryRef, relation: "current" }
          : { ...currentTaskSummaryRef, relation: "current" };
      }
      if (currentRef || currentTaskUpdatedAt) {
        effectiveTracking = effectiveTracking || {
          version: "v1.1",
          current_task_ref: null,
          conversation_task_refs: [],
          recent_task_actions: [],
          updated_at: "",
        };
        effectiveTracking.current_task_ref = currentRef || null;
        if (currentTaskUpdatedAt && (currentTaskSummaryRef || !String(effectiveTracking.updated_at || "").trim())) {
          effectiveTracking.updated_at = currentTaskUpdatedAt;
        }
      }
      const refs = effectiveTracking && Array.isArray(effectiveTracking.conversation_task_refs)
        ? effectiveTracking.conversation_task_refs
        : [];
      const actions = effectiveTracking && Array.isArray(effectiveTracking.recent_task_actions)
        ? effectiveTracking.recent_task_actions
        : [];
      const currentKey = conversationTaskStableKey(currentRef);
      const actionMap = buildConversationTaskActionSummaryMap(actions);
      const createdRows = refs.filter((row) => {
        const relation = String(row && row.relation || "").trim().toLowerCase();
        return relation === "created" && conversationTaskStableKey(row) !== currentKey;
      }).map((row) => mergeConversationTaskActivity(row, actionMap));
      const trackingRows = refs.filter((row) => {
        const relation = String((row && row.relation) || "").trim().toLowerCase();
        return relation !== "created" && relation !== "current" && conversationTaskStableKey(row) !== currentKey;
      }).map((row) => mergeConversationTaskActivity(row, actionMap));
      const relatedRows = createdRows.concat(trackingRows);
      return {
        tracking: effectiveTracking,
        loading,
        errorText,
        currentRef: currentRef ? mergeConversationTaskActivity(currentRef, actionMap) : null,
        createdRows,
        trackingRows,
        relatedRows,
        actions,
      };
    }

    function conversationTaskOwnedStatusText(row) {
      const item = (row && typeof row === "object") ? row : {};
      if (typeof resolveTaskPrimaryStatusText === "function") {
        return resolveTaskPrimaryStatusText(item, "待办") || "待办";
      }
      const text = String(firstNonEmptyText([
        item.task_primary_status,
        item.primary_status,
        item.status,
      ]) || "").trim();
      if (!text) return "待办";
      if (/(?:已完成|完成|done)/i.test(text)) return "已完成";
      if (/(?:待验收|验收|review)/i.test(text)) return "待验收";
      if (/(?:进行中|处理中|running|in[_-]?progress)/i.test(text)) return "进行中";
      if (/(?:待开始|待办|待处理|todo|pending|queued)/i.test(text)) return "待办";
      return text;
    }

    function conversationTaskOwnedStatusRank(row) {
      const status = conversationTaskOwnedStatusText(row);
      if (status === "进行中") return 10;
      if (status === "待验收") return 20;
      if (status === "待办" || status === "待开始") return 30;
      if (status === "已完成") return 90;
      return 70;
    }

    function conversationTaskOwnedIsActive(row) {
      const status = conversationTaskOwnedStatusText(row);
      return status === "进行中" || status === "待验收" || status === "待办" || status === "待开始";
    }

    function conversationTaskOwnedIsDone(row) {
      const status = conversationTaskOwnedStatusText(row);
      return status === "已完成" || /(?:已完成|完成|done)/i.test(String(row && row.status || ""));
    }

    function conversationTaskOwnedTime(row) {
      const item = (row && typeof row === "object") ? row : {};
      const value = firstNonEmptyText([
        item.latest_action_at,
        item.latestActionAt,
        item.updated_at,
        item.updatedAt,
        item.created_at,
        item.createdAt,
      ]) || "";
      if (typeof toTimeNum === "function") return toTimeNum(value);
      const parsed = Date.parse(String(value || ""));
      return Number.isFinite(parsed) ? parsed : 0;
    }

    function conversationTaskOwnedStableKey(row) {
      const item = (row && typeof row === "object") ? row : {};
      const taskId = typeof taskStableIdOfItem === "function"
        ? taskStableIdOfItem(item)
        : String(firstNonEmptyText([item.task_id, item.taskId, item.id]) || "").trim();
      if (taskId) return "task_id::" + taskId;
      const taskPath = conversationTaskStablePath(item);
      if (taskPath) return "task_path::" + taskPath;
      return "";
    }

    function conversationTaskOwnedForceTaskType(row, explicitType = "") {
      const explicit = String(explicitType || "").trim();
      if (explicit) return explicit;
      const item = (row && typeof row === "object") ? row : {};
      if (typeof unifiedTaskDetailTypeKey === "function") {
        const typeKey = String(unifiedTaskDetailTypeKey(item) || "").trim();
        if (typeKey) return typeKey;
      }
      if (item._isSubtask === true || item.is_subtask === true || item.isSubtask === true) return "child";
      if (firstNonEmptyText([item.parent_task_id, item.parentTaskId, item.parent_task_path, item.parentTaskPath])) return "child";
      return "parent";
    }

    function normalizeConversationAgentOwnedTaskRow(raw, forceType = "") {
      const item = (raw && typeof raw === "object") ? raw : {};
      const statusText = conversationTaskOwnedStatusText(item);
      const forceTaskType = conversationTaskOwnedForceTaskType(item, forceType || item.__forceTaskType);
      return {
        ...item,
        relation: "main_owner",
        relation_label: "当前主负责",
        __groupTitle: "当前主负责",
        __forceTaskType: forceTaskType,
        task_id: String(firstNonEmptyText([item.task_id, item.taskId, item.id]) || "").trim(),
        task_path: conversationTaskStablePath(item),
        task_title: conversationTaskTitleText(item),
        task_primary_status: statusText,
        task_summary_text: conversationTaskOwnedSnippet([item.task_summary_text, item.summary, item.excerpt]),
        latest_action_text: conversationTaskOwnedSnippet([item.latest_action_text, item.latestActionText, item.summary, item.excerpt]),
        latest_action_at: String(firstNonEmptyText([item.latest_action_at, item.latestActionAt, item.updated_at, item.updatedAt]) || "").trim(),
      };
    }

    function conversationTaskOwnedForceTypeMap(projectId) {
      const map = new Map();
      if (typeof buildTaskGroups !== "function") return map;
      const groups = buildTaskGroups(projectId);
      (Array.isArray(groups) ? groups : []).forEach((group) => {
        const master = group && group.master;
        const masterKey = conversationTaskOwnedStableKey(master);
        if (masterKey) map.set(masterKey, "parent");
        (Array.isArray(group && group.children) ? group.children : []).forEach((child) => {
          const childKey = conversationTaskOwnedStableKey(child);
          if (childKey) map.set(childKey, "child");
        });
      });
      return map;
    }

    function conversationAgentOwnedTaskOwnerLabel(session, ctx = {}) {
      const s = (session && typeof session === "object") ? session : {};
      return String(firstNonEmptyText([
        typeof conversationAgentName === "function" ? conversationAgentName(s) : "",
        s.alias,
        s.display_name,
        s.displayName,
        ctx && ctx.channelName,
        s.name,
      ]) || "").trim() || "当前 Agent";
    }

    function conversationTaskOwnedSnippet(values, fallback = "") {
      const text = String(firstNonEmptyText(Array.isArray(values) ? values : [values]) || fallback || "").trim();
      if (!text) return "";
      if (typeof normalizeTaskSummarySnippet === "function") return normalizeTaskSummarySnippet(text, 120);
      return text.length > 120 ? (text.slice(0, 119).trimEnd() + "…") : text;
    }

    function resolveConversationAgentOwnedTaskPayload(payload = {}) {
      const src = (payload && typeof payload === "object") ? payload : {};
      const ctx = (src.ctx && typeof src.ctx === "object") ? src.ctx : currentConversationCtx();
      const sessionId = String((ctx && ctx.sessionId) || "").trim();
      const currentSession = sessionId ? findConversationSessionById(sessionId) : null;
      const projectId = String(firstNonEmptyText([
        ctx && ctx.projectId,
        typeof STATE !== "undefined" && STATE ? STATE.project : "",
        typeof DATA !== "undefined" && DATA ? DATA.project_id : "",
      ]) || "").trim();
      if (projectId && typeof ensureProjectItemsLoaded === "function") ensureProjectItemsLoaded(projectId);
      const loading = projectId && typeof isProjectItemsLoading === "function"
        ? isProjectItemsLoading(projectId)
        : !!src.loading;
      const errorText = projectId && typeof itemLoadErrorForProject === "function"
        ? itemLoadErrorForProject(projectId)
        : String(src.error || "").trim();
      const pool = projectId && typeof itemsForProject === "function"
        ? itemsForProject(projectId)
        : [];
      const forceTypeMap = conversationTaskOwnedForceTypeMap(projectId);
      const rows = [];
      const seen = new Set();
      (Array.isArray(pool) ? pool : []).forEach((item) => {
        if (typeof isTaskItem === "function" ? !isTaskItem(item) : String(item && item.type || "") !== "任务") return;
        if (!conversationTaskMainOwnerMatchesSession(item, currentSession, ctx)) return;
        const key = conversationTaskOwnedStableKey(item);
        const row = normalizeConversationAgentOwnedTaskRow(item, forceTypeMap.get(key) || "");
        if (key && seen.has(key)) return;
        if (key) seen.add(key);
        rows.push(row);
      });
      rows.sort((a, b) => {
        const rankA = conversationTaskOwnedStatusRank(a);
        const rankB = conversationTaskOwnedStatusRank(b);
        if (rankA !== rankB) return rankA - rankB;
        const timeA = conversationTaskOwnedTime(a);
        const timeB = conversationTaskOwnedTime(b);
        if (timeA !== timeB) return timeB - timeA;
        return conversationTaskTitleText(a).localeCompare(conversationTaskTitleText(b), "zh-Hans-CN");
      });
      const activeRows = rows.filter(conversationTaskOwnedIsActive);
      const doneRows = rows.filter(conversationTaskOwnedIsDone);
      const inactiveRows = rows.filter((row) => !conversationTaskOwnedIsActive(row) && !conversationTaskOwnedIsDone(row));
      return {
        ctx,
        projectId,
        sessionId,
        ownerLabel: conversationAgentOwnedTaskOwnerLabel(currentSession, ctx),
        loading,
        errorText,
        rows,
        activeRows,
        doneRows,
        inactiveRows,
      };
    }

    function buildConversationAgentOwnedTaskCard(row, opts = {}) {
      const item = normalizeConversationAgentOwnedTaskRow(row);
      if (typeof buildUnifiedTaskListCard === "function") {
        return buildUnifiedTaskListCard(item, {
          source: "conversation-agent-main-owner-task-panel",
          projectId: String(opts.projectId || item.project_id || (typeof STATE !== "undefined" && STATE ? STATE.project : "") || "").trim(),
          groupTitle: "当前主负责",
          forceTaskType: item.__forceTaskType,
          compact: true,
          panel: true,
          latestText: item.latest_action_text || item.task_summary_text || "当前任务暂无摘要。",
          updatedAt: item.latest_action_at || item.updated_at || item.updatedAt,
          onOpen: () => {
            openConversationTaskDetailViewer(item, {
              sessionKey: PCONV.taskDrawerSessionKey,
              groupTitle: "当前主负责",
            });
          },
        });
      }
      return buildConversationTaskRefCard(item, {
        compact: true,
        onOpenDetail: () => openConversationTaskDetailViewer(item, {
          sessionKey: PCONV.taskDrawerSessionKey,
          groupTitle: "当前主负责",
        }),
      });
    }

    function buildConversationAgentOwnedCollapsedNote(view) {
      const doneCount = Array.isArray(view && view.doneRows) ? view.doneRows.length : 0;
      const inactiveCount = Array.isArray(view && view.inactiveRows) ? view.inactiveRows.length : 0;
      if (!doneCount && !inactiveCount) return null;
      const parts = [];
      if (doneCount) parts.push("已完成主负责任务 " + doneCount + " 项已收起");
      if (inactiveCount) parts.push("非当前态主负责任务 " + inactiveCount + " 项不默认平铺");
      return el("div", {
        class: "convtask-owned-collapsed-note",
        text: parts.join("；") + "。",
      });
    }

    function buildConversationTaskSummaryCard(data, opts = {}) {
      const view = (data && typeof data === "object") ? data : {};
      const tracking = view.tracking || null;
      const loading = !!view.loading;
      const errorText = String(view.errorText || "").trim();
      const currentRef = view.currentRef || null;
      const card = el("div", { class: "convtasksummary-card" });
      if (currentRef) {
        if (typeof buildUnifiedTaskListCard === "function") {
          const trackingTime = tracking && tracking.updated_at
            ? ("tracking " + (compactDateTime(tracking.updated_at) || shortDateTime(tracking.updated_at)))
            : "";
          const activityCountText = conversationTaskActivityCountText(currentRef.activity_count);
          const metaItems = [];
          if (activityCountText) metaItems.push([activityCountText, "muted"]);
          if (trackingTime) metaItems.push([trackingTime, "muted"]);
          return buildUnifiedTaskListCard({
            ...currentRef,
            title: conversationTaskTitleText(currentRef),
            latest_action_text: String(currentRef.latest_action_text || "").trim() || "当前任务已建立，最近活动待补充。",
          }, {
            source: "conversation-current-task-panel",
            projectId: typeof STATE !== "undefined" && STATE ? STATE.project : "",
            groupTitle: "当前任务",
            forceTaskType: "parent",
            compact: true,
            panel: true,
            metaItems,
            onOpen: () => {
              if (typeof opts.onOpenDetail === "function") opts.onOpenDetail(currentRef, { groupTitle: "当前任务" });
            },
          });
        }
        const main = el("div", { class: "convtasksummary-main" });
        main.appendChild(el("div", { class: "convtasksummary-label", text: "当前任务" }));
        const titleRow = el("div", { class: "convtasksummary-title-row" });
        titleRow.appendChild(el("div", {
          class: "convtasksummary-title",
          text: conversationTaskTitleText(currentRef),
          title: String(currentRef.task_title || currentRef.task_path || "").trim(),
        }));
        if (currentRef.task_primary_status) {
          titleRow.appendChild(chip(String(currentRef.task_primary_status || ""), conversationTaskStatusTone(currentRef.task_primary_status)));
        }
        const activityCountText = conversationTaskActivityCountText(currentRef.activity_count);
        if (activityCountText) {
          titleRow.appendChild(chip(activityCountText, "muted"));
        }
        if (currentRef.latest_action_kind) {
          titleRow.appendChild(chip(
            conversationTaskActionLabel(currentRef.latest_action_kind),
            conversationTaskActionTone(currentRef.latest_action_kind)
          ));
        }
        main.appendChild(titleRow);
        main.appendChild(el("div", {
          class: "convtasksummary-progress",
          text: String(currentRef.latest_action_text || "").trim() || "当前任务已建立，最近活动待补充。",
        }));
        const meta = buildConversationTaskMetaLine([
          compactDateTime(currentRef.latest_action_at) || shortDateTime(currentRef.latest_action_at),
          tracking && tracking.updated_at ? ("tracking " + (compactDateTime(tracking.updated_at) || shortDateTime(tracking.updated_at))) : "",
        ]);
        if (meta) main.appendChild(meta);
        if (typeof opts.onOpenDetail === "function") {
          const actions = el("div", { class: "convtasksummary-actions" });
          const detailBtn = el("button", {
            class: "btn convtasksummary-action-btn",
            type: "button",
            text: "查看详情",
          });
          detailBtn.addEventListener("click", () => opts.onOpenDetail(currentRef, { groupTitle: "当前任务" }));
          actions.appendChild(detailBtn);
          main.appendChild(actions);
        }
        card.appendChild(main);
        const roleRail = buildConversationTaskResponsibilityRail(currentRef);
        card.appendChild(roleRail || buildConversationTaskOwnerNode(currentRef.next_owner || null));
        return card;
      }
      const main = el("div", { class: "convtasksummary-main" });
      main.appendChild(el("div", { class: "convtasksummary-label", text: "当前任务" }));
      main.appendChild(el("div", {
        class: "convtasksummary-title",
        text: loading ? "任务上下文同步中…" : "当前会话尚未形成稳定当前任务",
      }));
      main.appendChild(el("div", {
        class: errorText ? "convtaskerror" : "convtasksummary-progress",
        text: errorText || (loading
          ? "正在读取会话 task_tracking 真源。"
          : "本轮对话暂未汇总出 current_task_ref。"),
      }));
      card.appendChild(main);
      card.appendChild(buildConversationTaskRoleCard({ display_name: "主负责位待接入正式读模型" }, { label: "主负责位", compact: true }));
      return card;
    }

    function compactConversationTimelineSignatureText(raw, limit = 160) {
      const text = String(raw || "").replace(/\s+/g, " ").trim();
      if (!text) return "";
      const maxLen = Math.max(16, Number(limit) || 160);
      if (text.length <= maxLen) return text;
      return text.slice(0, maxLen - 1).trimEnd() + "…";
    }

    function conversationAttachmentSignature(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return [
        String(src.localId || src.local_id || "").trim(),
        String(src.attachment_id || src.attachmentId || "").trim(),
        String(src.url || src.dataUrl || src.preview_url || src.path || "").trim(),
        String(src.originalName || src.filename || "").trim(),
      ].filter(Boolean).join("|");
    }

    function buildConversationTimelineRenderSignature(ctx = {}, payload = {}) {
      const context = (ctx && typeof ctx === "object") ? ctx : {};
      const src = (payload && typeof payload === "object") ? payload : {};
      const displayRuns = Array.isArray(src.displayRuns) ? src.displayRuns : [];
      const runtimeState = (src.runtimeState && typeof src.runtimeState === "object") ? src.runtimeState : {};
      const runs = displayRuns.map((run) => {
        const row = (run && typeof run === "object") ? run : {};
        const runId = String(row.id || "").trim();
        const detail = runId && PCONV.detailMap ? PCONV.detailMap[runId] : null;
        const processTrail = runId && PCONV.processTrailByRun ? PCONV.processTrailByRun[runId] : null;
        return {
          id: runId,
          status: String(row.status || "").trim(),
          createdAt: String(row.createdAt || "").trim(),
          messagePreview: compactConversationTimelineSignatureText(row.messagePreview || row.preview || ""),
          lastPreview: compactConversationTimelineSignatureText(row.lastPreview || ""),
          attachments: (Array.isArray(row.attachments) ? row.attachments : []).map(conversationAttachmentSignature),
          detail: detail ? {
            loading: !!detail.loading,
            status: String((((detail.full || {}).run || {}).status) || "").trim(),
            lastMessage: compactConversationTimelineSignatureText(((detail.full || {}).lastMessage) || ""),
          } : null,
          processTrail: processTrail ? {
            status: String(processTrail.status || "").trim(),
            updatedAt: Number(processTrail.updatedAt || 0) || 0,
            latest: compactConversationTimelineSignatureText(
              processTrail.latest
              || (Array.isArray(processTrail.rows) && processTrail.rows.length ? processTrail.rows[processTrail.rows.length - 1].text : "")
              || ""
            ),
          } : null,
        };
      });
      return JSON.stringify({
        projectId: String(context.projectId || "").trim(),
        sessionId: String(context.sessionId || "").trim(),
        runtimeState: {
          status: String(runtimeState.status || runtimeState.display_state || "").trim(),
          active_run_id: String(runtimeState.active_run_id || "").trim(),
          queued_run_id: String(runtimeState.queued_run_id || "").trim(),
        },
        runs,
      });
    }

    function shouldReuseConversationTimelineDom(timeline, timelineRenderSignature, opts = {}) {
      const node = (timeline && typeof timeline === "object") ? timeline : null;
      const signature = String(timelineRenderSignature || "").trim();
      if (!node || !signature) return false;
      if (opts && opts.forceScroll) return false;
      const prev = String((node.dataset && node.dataset.conversationTimelineRenderSignature) || "").trim();
      return !!prev && prev === signature;
    }

    function markConversationTimelineRenderSignature(timeline, timelineRenderSignature) {
      const node = (timeline && typeof timeline === "object") ? timeline : null;
      if (!node) return;
      if (!node.dataset || typeof node.dataset !== "object") node.dataset = {};
      node.dataset.conversationTimelineRenderSignature = String(timelineRenderSignature || "").trim();
    }

    function conversationTimelineStableAttachmentKey(raw, index = 0) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return String(
        src.localId
        || src.local_id
        || src.attachment_id
        || src.attachmentId
        || src.url
        || src.dataUrl
        || src.preview_url
        || src.path
        || src.originalName
        || src.filename
        || ("attachment-" + Number(index || 0))
      ).trim();
    }

    function conversationStableAttachmentSignature(list) {
      return (Array.isArray(list) ? list : [])
        .map((item, index) => conversationTimelineStableAttachmentKey(item, index))
        .join("||");
    }

    function conversationGeneratedAttachmentRole(raw) {
      const att = (raw && typeof raw === "object") ? raw : null;
      if (!att) return "";
      return String(firstNonEmptyText([
        att.attachment_role,
        att.attachmentRole,
      ]) || "").trim().toLowerCase();
    }

    function isConversationGeneratedAssistantMediaAttachment(raw) {
      const att = (raw && typeof raw === "object") ? raw : null;
      if (!att) return false;
      const attachmentRole = conversationGeneratedAttachmentRole(att);
      if (attachmentRole && attachmentRole !== "assistant" && attachmentRole !== "agent") return false;
      const generatedBy = String(firstNonEmptyText([
        att.generatedBy,
        att.generated_by,
      ]) || "").trim().toLowerCase();
      const source = String(firstNonEmptyText([
        att.source,
      ]) || "").trim().toLowerCase();
      if (generatedBy !== "codex_imagegen" && source !== "generated") return false;
      return true;
    }

    function isConversationGeneratedAssistantImageAttachment(raw) {
      const att = (raw && typeof raw === "object") ? raw : null;
      if (!att) return false;
      if (!isConversationGeneratedAssistantMediaAttachment(att)) return false;
      return typeof isImageAttachment === "function" ? !!isImageAttachment(att) : false;
    }

    function collectConversationGeneratedAssistantImageAttachments(list) {
      return (Array.isArray(list) ? list : []).filter((item) => isConversationGeneratedAssistantImageAttachment(item));
    }

    function isConversationUserInputAttachment(raw) {
      const att = (raw && typeof raw === "object") ? raw : null;
      if (!att) return false;
      const attachmentRole = conversationGeneratedAttachmentRole(att);
      if (attachmentRole && attachmentRole !== "user") return false;
      const generatedBy = String(firstNonEmptyText([
        att.generatedBy,
        att.generated_by,
      ]) || "").trim().toLowerCase();
      const source = String(firstNonEmptyText([
        att.source,
      ]) || "").trim().toLowerCase();
      if (generatedBy === "codex_imagegen" || source === "generated") return false;
      if (isConversationGeneratedAssistantMediaAttachment(att)) return false;
      return true;
    }

    function collectConversationUserInputAttachments(list) {
      return (Array.isArray(list) ? list : []).filter((item) => isConversationUserInputAttachment(item));
    }

    function buildConversationStableAttachmentPatchMap(list) {
      const map = new Map();
      (Array.isArray(list) ? list : []).forEach((item, index) => {
        const key = conversationTimelineStableAttachmentKey(item, index);
        if (!key) return;
        map.set(key, {
          src: typeof resolveAttachmentUrl === "function"
            ? String(resolveAttachmentUrl(item) || "").trim()
            : String((item && (item.url || item.dataUrl || item.preview_url || item.path)) || "").trim(),
          alt: String((item && (item.originalName || item.filename)) || "").trim(),
        });
      });
      return map;
    }

    function syncConversationStableTimelineRowAttachments(row, attachments) {
      if (!row || typeof row.querySelectorAll !== "function") return;
      const patchMap = buildConversationStableAttachmentPatchMap(attachments);
      const nodes = row.querySelectorAll("[data-conversation-attachment-key], img, source");
      Array.from(nodes || []).forEach((node) => {
        const key = String((node && node.dataset && node.dataset.conversationAttachmentKey) || "").trim();
        if (!key || !patchMap.has(key)) return;
        const patch = patchMap.get(key) || {};
        if (patch.src && typeof node.setAttribute === "function") {
          node.setAttribute("src", patch.src);
          if (node.dataset && typeof node.dataset === "object") node.dataset.conversationAttachmentSrc = patch.src;
        }
        if (patch.alt && typeof node.setAttribute === "function" && String(node.tagName || "").toUpperCase() === "IMG") {
          node.setAttribute("alt", patch.alt);
        }
      });
    }

    function conversationTimelineBubbleExpansionSignature(keys) {
      return (Array.isArray(keys) ? keys : []).map((item) => String(item || "").trim()).filter(Boolean).sort().join("|");
    }

    function conversationTimelineStableRowSignature(payload = {}) {
      const src = (payload && typeof payload === "object") ? payload : {};
      return JSON.stringify({
        kind: String(src.kind || "").trim(),
        runId: String(src.runId || "").trim(),
        status: String(src.status || (src.run && src.run.status) || "").trim(),
        text: compactConversationTimelineSignatureText(src.text || ""),
        attachments: conversationStableAttachmentSignature(src.attachments),
        bubbleKeys: conversationTimelineBubbleExpansionSignature(src.bubbleKeys),
        meta: src.meta && typeof src.meta === "object" ? src.meta : null,
      });
    }

    function isConversationTimelineTerminalStatus(raw) {
      const status = String(raw || "").trim().toLowerCase();
      return status !== "running" && status !== "queued" && status !== "retry_waiting" && status !== "external_busy";
    }

    function canReuseConversationStableTimelineRow(run, detail, status, opts = {}) {
      if (!isConversationTimelineTerminalStatus(status || (run && run.status) || "")) return false;
      if (detail && detail.loading) return false;
      if (opts && opts.forceRefresh) return false;
      return true;
    }

    function buildConversationStableTimelineRowKey(kind, runId) {
      const family = String(kind || "").trim();
      const id = String(runId || "").trim();
      if (!family || !id) return "";
      return family + ":" + id;
    }

    function markConversationStableTimelineRow(row, key, signature) {
      const node = (row && typeof row === "object") ? row : null;
      const stableKey = String(key || "").trim();
      const stableSignature = String(signature || "").trim();
      if (!node || !stableKey || !stableSignature) return node;
      if (!node.dataset || typeof node.dataset !== "object") node.dataset = {};
      node.dataset.conversationStableRowKey = stableKey;
      node.dataset.conversationStableRowSignature = stableSignature;
      return node;
    }

    function buildConversationStableTimelineRowReuseMap(timeline) {
      const node = (timeline && typeof timeline === "object") ? timeline : null;
      const map = new Map();
      if (!node || typeof node.querySelectorAll !== "function") return map;
      const rows = node.querySelectorAll(".msgrow[data-conversation-stable-row-key]");
      Array.from(rows || []).forEach((row) => {
        const key = String((row && row.dataset && row.dataset.conversationStableRowKey) || "").trim();
        const signature = String((row && row.dataset && row.dataset.conversationStableRowSignature) || "").trim();
        if (!key || !signature || map.has(key)) return;
        map.set(key, { row, signature });
      });
      return map;
    }

    function reuseConversationStableTimelineRow(reuseMap, key, signature, attachments = null) {
      const map = reuseMap instanceof Map ? reuseMap : null;
      const stableKey = String(key || "").trim();
      const stableSignature = String(signature || "").trim();
      if (!map || !stableKey || !stableSignature) return null;
      const record = map.get(stableKey);
      if (!record || record.signature !== stableSignature) return null;
      map.delete(stableKey);
      const row = record.row || null;
      if (!row) return null;
      if (Array.isArray(attachments) && attachments.length) {
        syncConversationStableTimelineRowAttachments(row, attachments);
      }
      return markConversationStableTimelineRow(row, stableKey, stableSignature);
    }

    function buildConversationUserStableRowMeta(payload = {}) {
      const src = (payload && typeof payload === "object") ? payload : {};
      const run = (src.run && typeof src.run === "object") ? src.run : null;
      const detail = (src.detail && typeof src.detail === "object") ? src.detail : null;
      const status = String(src.status || (run && run.status) || "").trim();
      const attachments = Array.isArray(src.attachments) ? src.attachments : [];
      const runId = String(src.runId || (run && run.id) || "").trim();
      if (!runId || attachments.length <= 0) return null;
      if (!canReuseConversationStableTimelineRow(run, detail, status, src.opts || {})) return null;
      if (src.systemLike || src.queuedCompactMode || src.agentInbound || src.receiptInbound) return null;
      const mentionTargets = (Array.isArray(src.mentionTargets) ? src.mentionTargets : []).map((item) => ({
        channel_name: String((item && item.channel_name) || "").trim(),
        session_id: String((item && item.session_id) || "").trim(),
        display_name: String((item && item.display_name) || "").trim(),
      }));
      const visualMode = src.userVisualMode && typeof src.userVisualMode === "object"
        ? src.userVisualMode
        : {};
      const bubbleKey = String(src.bubbleKey || "").trim();
      const signature = conversationTimelineStableRowSignature({
        kind: "user",
        runId,
        run,
        status,
        text: String(src.text || "").trim(),
        attachments,
        bubbleKeys: bubbleKey ? [bubbleKey] : [],
        meta: {
          visualKind: String(visualMode.kind || "").trim(),
          displayMode: String(visualMode.displayMode || "").trim(),
          currentConclusion: compactConversationTimelineSignatureText(visualMode.currentConclusion || "", 96),
          nextAction: compactConversationTimelineSignatureText(visualMode.nextAction || "", 96),
          replyRunId: String((src.replyContext && src.replyContext.runId) || "").trim(),
          replyText: compactConversationTimelineSignatureText((src.replyContext && src.replyContext.text) || "", 96),
          mentions: mentionTargets,
        },
      });
      return {
        key: buildConversationStableTimelineRowKey("user", runId),
        signature,
      };
    }

    function syncConversationTimelineChildren(timeline, nextChildren) {
      const host = (timeline && typeof timeline === "object") ? timeline : null;
      const desired = Array.isArray(nextChildren) ? nextChildren.filter(Boolean) : [];
      if (!host) return;
      let cursor = host.firstChild;
      desired.forEach((node) => {
        if (!node) return;
        if (node === cursor) {
          cursor = cursor && cursor.nextSibling;
          return;
        }
        host.insertBefore(node, cursor || null);
      });
      while (cursor) {
        const next = cursor.nextSibling;
        host.removeChild(cursor);
        cursor = next;
      }
    }

    function resolveConversationRestartRecoveryAnchorRunId(payload = {}) {
      const runs = Array.isArray(payload.runs) ? payload.runs : [];
      const targetRun = (payload.run && typeof payload.run === "object") ? payload.run : null;
      const target = targetRun || null;
      const meta = typeof readRunRestartRecoveryMeta === "function" ? readRunRestartRecoveryMeta(target) : null;
      if (!target || !meta || !Array.isArray(meta.sourceRunIds) || !meta.sourceRunIds.length) return "";
      const visibleRunIds = new Set(runs.map((item) => String((item && item.id) || "").trim()).filter(Boolean));
      for (const runId of meta.sourceRunIds) {
        const id = String(runId || "").trim();
        if (id && visibleRunIds.has(id)) return id;
      }
      return "";
    }

    function reorderConversationDisplayRunsForTimeline(runs, detailMap = {}, ctx = {}) {
      const list = (Array.isArray(runs) ? runs : []).slice().sort((a, b) => {
        const ta = Date.parse(String((a && a.createdAt) || "")) || 0;
        const tb = Date.parse(String((b && b.createdAt) || "")) || 0;
        if (ta !== tb) return ta - tb;
        return String((a && a.id) || "").localeCompare(String((b && b.id) || ""));
      });
      for (let idx = 0; idx < list.length; idx += 1) {
        const run = mergeRunForDisplay((detailMap && detailMap[String((list[idx] && list[idx].id) || "")]) || null, list[idx]);
        const anchorRunId = resolveConversationRestartRecoveryAnchorRunId({ run, runs: list, detailMap, ctx });
        if (!anchorRunId) continue;
        const currentIndex = idx;
        const anchorIndex = list.findIndex((item) => String((item && item.id) || "").trim() === anchorRunId);
        if (anchorIndex < 0 || anchorIndex + 1 === currentIndex) continue;
        const [row] = list.splice(currentIndex, 1);
        const insertAt = anchorIndex < currentIndex ? anchorIndex + 1 : anchorIndex;
        list.splice(insertAt, 0, row);
      }
      return list;
    }

    function warmConversationTimelineWorkingRunDetails(projectId, sessionId, runs) {
      // assistant-body-prefetch-disabled: 时间线运行态正文默认依赖 light payload，
      // 不再为了 working run 额外触发 detail 预热。
      return [];
    }

    function renderConversationTaskSummaryAndTracking(summaryEl, trackingEl, payload = {}) {
      const summaryBox = summaryEl || null;
      const trackingBox = trackingEl || null;
      if (summaryBox) {
        summaryBox.innerHTML = "";
        summaryBox.hidden = true;
      }
      if (trackingBox) {
        trackingBox.innerHTML = "";
        trackingBox.hidden = true;
      }
      if (!summaryBox && !trackingBox) return;

      const view = resolveConversationTaskTrackingPayload(payload);
      const tracking = view.tracking;
      const loading = view.loading;
      const errorText = view.errorText;
      const currentRef = view.currentRef;
      const relatedRows = view.relatedRows;

      if (summaryBox) {
        summaryBox.hidden = false;
        summaryBox.appendChild(buildConversationTaskSummaryCard(view));
      }

      if (trackingBox) {
        trackingBox.hidden = false;
        const head = el("div", { class: "convtasktracking-head" });
        head.appendChild(el("div", { class: "convtasktracking-title", text: "相关任务" }));
        head.appendChild(el("div", {
          class: "convtasktracking-sub",
          text: tracking && tracking.updated_at
            ? ("更新于 " + (compactDateTime(tracking.updated_at) || shortDateTime(tracking.updated_at)))
            : (loading ? "同步中…" : "等待首轮任务真源"),
        }));
        trackingBox.appendChild(head);
        if (errorText && !tracking) {
          trackingBox.appendChild(el("div", { class: "convtaskerror", text: "任务跟踪读取失败：" + errorText }));
        }
        const groups = el("div", { class: "convtaskgroups" });
        groups.appendChild(renderConversationTaskGroup(
          "相关任务",
          relatedRows,
          (row) => buildConversationTaskRefCard(row),
          {
            limit: 4,
            emptyText: loading && !relatedRows.length ? "相关任务同步中…" : "当前没有其他相关任务。",
            loading: loading && !relatedRows.length,
          }
        ));
        trackingBox.appendChild(groups);
      }
    }

    function currentConversationTaskPayload() {
      const ctx = currentConversationCtx();
      const sessionId = String((ctx && ctx.sessionId) || "").trim();
      const currentSession = sessionId ? findConversationSessionById(sessionId) : null;
      const currentTaskSummary = currentSession && typeof getConversationListCurrentTaskSummary === "function"
        ? getConversationListCurrentTaskSummary(currentSession)
        : null;
      return {
        ctx,
        taskTracking: currentSession && currentSession.task_tracking,
        currentTaskSummary,
        currentTaskUpdatedAt: String(firstNonEmptyText([
          currentTaskSummary && currentTaskSummary.latest_action_at,
          currentSession && currentSession.task_tracking && currentSession.task_tracking.updated_at,
        ]) || "").trim(),
        loading: sessionId
          ? (typeof isConversationSessionDetailLoading === "function"
            ? isConversationSessionDetailLoading(sessionId)
            : false)
          : false,
        error: sessionId && typeof getConversationSessionDetailError === "function"
          ? getConversationSessionDetailError(sessionId)
          : "",
      };
    }

    function buildConversationTaskDrawerRenderSignature(view, sessionKey = "") {
      const currentView = (view && typeof view === "object") ? view : {};
      const activeRows = Array.isArray(currentView.activeRows) ? currentView.activeRows : [];
      const doneRows = Array.isArray(currentView.doneRows) ? currentView.doneRows : [];
      const inactiveRows = Array.isArray(currentView.inactiveRows) ? currentView.inactiveRows : [];
      const rowSignature = (row) => {
        const item = (row && typeof row === "object") ? row : {};
        return {
          key: conversationTaskOwnedStableKey(item),
          status: conversationTaskOwnedStatusText(item),
          updatedAt: String(firstNonEmptyText([item.latest_action_at, item.updated_at, item.updatedAt]) || "").trim(),
        };
      };
      return JSON.stringify({
        sessionKey: String(sessionKey || "").trim(),
        ownerLabel: String(currentView.ownerLabel || "").trim(),
        loading: !!currentView.loading,
        errorText: String(currentView.errorText || "").trim(),
        activeRows: activeRows.map(rowSignature),
        doneCount: doneRows.length,
        inactiveCount: inactiveRows.length,
      });
    }

    function renderConversationTaskDetailViewer(payload = null) {
      const viewer = ensureConversationTaskDetailViewerState();
      const currentKey = String(firstNonEmptyText([
        PCONV.taskDrawerSessionKey,
        currentConvComposerDraftKey(),
      ]) || "").trim();
      if (!PCONV.taskDrawerOpen || !viewer.open || !currentKey || viewer.sessionKey !== currentKey) {
        removeConversationTaskDetailViewerMask();
        if (typeof closeUnifiedTaskDetail === "function") closeUnifiedTaskDetail({ notify: false });
        if (!PCONV.taskDrawerOpen || !currentKey || viewer.sessionKey !== currentKey) {
          resetConversationTaskDetailViewer();
        }
        return;
      }
      const detail = resolveConversationTaskDetailView(
        resolveConversationTaskTrackingPayload(payload || currentConversationTaskPayload()),
        viewer
      );
      if (!detail) {
        removeConversationTaskDetailViewerMask();
        if (typeof closeUnifiedTaskDetail === "function") closeUnifiedTaskDetail({ notify: false });
        return;
      }
      if (typeof openUnifiedTaskDetail === "function") {
        removeConversationTaskDetailViewerMask();
        openUnifiedTaskDetail(detail, {
          source: "conversation-task-detail",
          projectId: typeof STATE !== "undefined" && STATE ? STATE.project : "",
          groupTitle: detail.groupTitle,
          onOpenSource: (model) => openConversationTaskSourceFile(model.taskPath, model.title),
          onClose: () => {
            resetConversationTaskDetailViewer();
            renderConversationTaskDetailViewer();
          },
        });
        return;
      }
      const mask = el("div", {
        id: "convTaskDetailViewerMask",
        class: "bmask conv-task-detail-mask show",
      });
      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeConversationTaskDetailViewer();
      });
      const dialog = el("div", { class: "bmodal conv-task-detail-modal" });
      const head = el("div", { class: "bmodalh conv-task-detail-head" });
      head.appendChild(el("div", { class: "t", text: "任务详情 · " + detail.title }));
      head.appendChild(el("div", {
        class: "s",
        text: detail.groupTitle
          ? ("当前位于“" + detail.groupTitle + "”，保持只读轻下钻。")
          : "当前任务详情仅提供只读轻下钻。",
      }));
      dialog.appendChild(head);

      const body = el("div", { class: "bmodalb conv-task-detail-body" });
      const hero = el("section", { class: "conv-task-detail-hero" });
      const titleRow = el("div", { class: "conv-task-detail-title-row" });
      titleRow.appendChild(el("div", {
        class: "conv-task-detail-title",
        text: detail.title,
        title: detail.taskPath || detail.title,
      }));
      if (detail.statusText) titleRow.appendChild(chip(detail.statusText, conversationTaskStatusTone(detail.statusText)));
      if (detail.latestActionLabel) {
        titleRow.appendChild(chip(
          detail.latestActionLabel,
          conversationTaskActionTone(detail.latestAction && detail.latestAction.action_kind, detail.latestAction && detail.latestAction.status)
        ));
      }
      if (detail.groupTitle) titleRow.appendChild(chip(detail.groupTitle, "muted"));
      hero.appendChild(titleRow);
      const summaryBlock = el("div", { class: "conv-task-detail-summary-block" });
      summaryBlock.appendChild(el("div", { class: "conv-task-detail-summary-label", text: "任务一句话说明" }));
      summaryBlock.appendChild(el("div", {
        class: "conv-task-detail-summary-text" + (!detail.taskSummaryText ? " is-placeholder" : ""),
        text: detail.taskSummaryText || detail.taskSummaryPlaceholder,
      }));
      hero.appendChild(summaryBlock);
      const snapshot = el("div", { class: "conv-task-detail-snapshot" });
      const ownerCard = el("div", { class: "conv-task-detail-panel" });
      if (detail.responsibilityModel && detail.responsibilityModel.hasData) {
        ownerCard.appendChild(
          detail.responsibilityModel.main_owner
            ? buildConversationTaskRoleCard(detail.responsibilityModel.main_owner, { label: "主负责位" })
            : buildConversationTaskRoleCard({ display_name: "主负责位待接入正式读模型" }, { label: "主负责位" })
        );
      } else {
        ownerCard.appendChild(buildConversationTaskOwnerNode(detail.owner || null));
      }
      snapshot.appendChild(ownerCard);
      const actionCard = el("div", { class: "conv-task-detail-panel conv-task-detail-panel-action" });
      actionCard.appendChild(el("div", { class: "conv-task-detail-panel-label", text: "最近动作摘要" }));
      actionCard.appendChild(el("div", { class: "conv-task-detail-action-text", text: detail.latestActionText }));
      const actionMeta = buildConversationTaskMetaLine([
        detail.latestActionAt ? ("时间 " + (compactDateTime(detail.latestActionAt) || shortDateTime(detail.latestActionAt))) : "",
        detail.latestActionSource ? ("来源 " + detail.latestActionSource) : "",
      ]);
      if (actionMeta) actionCard.appendChild(actionMeta);
      snapshot.appendChild(actionCard);
      hero.appendChild(snapshot);
      body.appendChild(hero);

      const sourceBlock = el("section", { class: "conv-task-detail-section" });
      sourceBlock.appendChild(el("div", { class: "conv-task-detail-section-title", text: "来源说明" }));
      if (detail.whyAppearsText) {
        sourceBlock.appendChild(el("div", { class: "conv-task-detail-why", text: detail.whyAppearsText }));
      }
      const infoRows = [
        renderConversationTaskDetailInfoRow("所在分组", detail.groupTitle),
        renderConversationTaskDetailInfoRow("关联关系", detail.relationLabel),
        renderConversationTaskDetailInfoRow("来源标记", detail.sourceText),
        renderConversationTaskDetailInfoRow("首次纳入", compactDateTime(detail.firstSeenAt) || shortDateTime(detail.firstSeenAt)),
        renderConversationTaskDetailInfoRow("最近观察", compactDateTime(detail.lastSeenAt) || shortDateTime(detail.lastSeenAt)),
        renderConversationTaskDetailInfoRow("任务路径", detail.taskPath, { mono: true, stack: true }),
      ].filter(Boolean);
      if (infoRows.length) {
        const info = el("div", { class: "conv-task-detail-info" });
        infoRows.forEach((row) => info.appendChild(row));
        sourceBlock.appendChild(info);
      }
      body.appendChild(sourceBlock);

      const responsibilitySection = buildConversationTaskResponsibilitySection(detail.responsibilityModel || null);
      if (responsibilitySection) body.appendChild(responsibilitySection);

      if (viewer.showActionContext) {
        const contextBlock = el("section", { class: "conv-task-detail-section" });
        contextBlock.appendChild(el("div", { class: "conv-task-detail-section-title", text: "最近动作上下文" }));
        if (!detail.contextItems.length) {
          contextBlock.appendChild(el("div", { class: "convtaskempty", text: "当前没有可展示的动作上下文。" }));
        } else {
          const list = el("div", { class: "conv-task-detail-context-list" });
          detail.contextItems.slice(0, 5).forEach((row) => {
            const item = el("div", { class: "conv-task-detail-context-item" });
            const itemHead = el("div", { class: "conv-task-detail-context-head" });
            if (row.action_kind) itemHead.appendChild(chip(conversationTaskActionLabel(row.action_kind), conversationTaskActionTone(row.action_kind, row.status)));
            const whenText = compactDateTime(row.at) || shortDateTime(row.at);
            if (whenText) itemHead.appendChild(el("div", { class: "conv-task-detail-context-time", text: whenText }));
            item.appendChild(itemHead);
            item.appendChild(el("div", {
              class: "conv-task-detail-context-text",
              text: String(row.action_text || "").trim() || "最近暂无补充说明。",
            }));
            const rowMeta = buildConversationTaskMetaLine([
              firstNonEmptyText([row.source_agent_name, row.source_channel]),
              row.callback_run_id ? ("回执 " + row.callback_run_id) : "",
            ]);
            if (rowMeta) item.appendChild(rowMeta);
            list.appendChild(item);
          });
          contextBlock.appendChild(list);
        }
        body.appendChild(contextBlock);
      }

      body.appendChild(buildConversationTaskDetailReadingSection(detail));
      dialog.appendChild(body);

      const foot = el("div", { class: "bmodalf conv-task-detail-foot" });
      const openBtn = el("button", {
        class: "btn primary",
        type: "button",
        text: "查看原任务文件",
      });
      openBtn.disabled = !detail.taskPath;
      openBtn.addEventListener("click", () => {
        if (!detail.taskPath) return;
        openNew(String(location.origin || "") + "/api/fs/open?path=" + encodeURIComponent(detail.taskPath));
      });
      foot.appendChild(openBtn);
      const contextBtn = el("button", {
        class: "btn",
        type: "button",
        text: viewer.showActionContext ? "收起最近动作上下文" : "查看最近动作上下文",
      });
      contextBtn.disabled = !detail.hasActionContext;
      contextBtn.addEventListener("click", toggleConversationTaskDetailActionContext);
      foot.appendChild(contextBtn);
      const closeBtn = el("button", { class: "btn", type: "button", text: "关闭" });
      closeBtn.addEventListener("click", closeConversationTaskDetailViewer);
      foot.appendChild(closeBtn);
      dialog.appendChild(foot);
      mask.appendChild(dialog);

      const existing = document.getElementById("convTaskDetailViewerMask");
      if (existing) existing.replaceWith(mask);
      else document.body.appendChild(mask);
    }

    function renderConversationTaskDrawer(payload = {}) {
      const mask = document.getElementById("convTaskDrawerMask");
      const list = document.getElementById("convTaskDrawerList");
      const sub = document.getElementById("convTaskDrawerSub");
      const hint = document.getElementById("convTaskHint");
      if (!mask || !list || !sub || !hint) return;
      if (!PCONV.taskDrawerOpen) {
        resetConversationTaskDrawerRenderState();
        mask.classList.remove("show");
        renderConversationTaskDetailViewer();
        return;
      }
      const sessionKey = String(PCONV.taskDrawerSessionKey || "").trim();
      const view = resolveConversationAgentOwnedTaskPayload(payload);
      const renderState = ensureConversationTaskDrawerRenderState();
      const loading = view.loading;
      const errorText = view.errorText;
      const displayLoading = !!loading;
      const displayErrorText = String(errorText || "").trim();
      const renderView = {
        ...view,
        loading: displayLoading,
        errorText: displayErrorText,
      };
      const renderSignature = buildConversationTaskDrawerRenderSignature(renderView, sessionKey);
      const activeRows = renderView.activeRows;
      sub.textContent = "主负责位 · " + (renderView.ownerLabel || "当前 Agent") + " · 当前 " + activeRows.length + " 项";
      hint.textContent = displayErrorText
        ? ("主负责任务读取失败：" + displayErrorText)
        : "这里只展示当前 Agent 作为 main_owner 的待开始/进行中/待验收任务；点击任务会打开中间统一详情弹框。";
      if (
        renderState.sessionKey === sessionKey
        && renderState.signature === renderSignature
        && list.childElementCount > 0
      ) {
        mask.classList.add("show");
        return;
      }
      const prevScrollTop = Number(list.scrollTop || 0);
      list.innerHTML = "";
      const stack = el("div", { class: "conv-task-drawer-stack" });
      const groups = el("div", { class: "convtaskgroups" });
      groups.appendChild(renderConversationTaskGroup(
        "当前主负责",
        activeRows,
        (row) => buildConversationAgentOwnedTaskCard(row, { projectId: renderView.projectId }),
        {
          limit: 12,
          singleColumn: true,
          emptyText: displayLoading && !activeRows.length
            ? "主负责任务同步中…"
            : "当前没有该 Agent 主负责的待开始/进行中/待验收任务。",
          loading: displayLoading && !activeRows.length,
          error: !!displayErrorText && !activeRows.length,
        }
      ));
      stack.appendChild(groups);
      const collapsedNote = buildConversationAgentOwnedCollapsedNote(renderView);
      if (collapsedNote) stack.appendChild(collapsedNote);
      list.appendChild(stack);
      if (prevScrollTop > 0) {
        requestAnimationFrame(() => {
          const currentList = document.getElementById("convTaskDrawerList");
          if (!currentList) return;
          currentList.scrollTop = prevScrollTop;
        });
      }
      renderState.sessionKey = sessionKey;
      renderState.signature = renderSignature;
      mask.classList.add("show");
      renderConversationTaskDetailViewer(payload);
    }

    function hideConversationTaskEntry() {
      const btn = document.getElementById("detailTaskTrackingBtn");
      if (btn) {
        btn.style.display = "none";
        btn.onclick = null;
        btn.classList.remove("active");
      }
      if (PCONV.taskDrawerOpen) {
        PCONV.taskDrawerOpen = false;
        PCONV.taskDrawerSessionKey = "";
        resetConversationTaskDrawerRenderState();
        renderConversationTaskDrawer();
      }
      resetConversationTaskDetailViewer();
      renderConversationTaskDetailViewer();
    }

    function renderConversationTaskEntry(ctx, payload = {}) {
      const btn = document.getElementById("detailTaskTrackingBtn");
      if (!btn) return;
      if (!ctx || !ctx.projectId || !ctx.sessionId) {
        hideConversationTaskEntry();
        return;
      }
      const key = convComposerDraftKey(ctx.projectId, ctx.sessionId);
      btn.style.display = "";
      btn.classList.toggle("active", !!(PCONV.taskDrawerOpen && String(PCONV.taskDrawerSessionKey || "") === key));
      btn.onclick = () => {
        const same = PCONV.taskDrawerOpen && String(PCONV.taskDrawerSessionKey || "") === key;
        if (same) {
          PCONV.taskDrawerOpen = false;
          resetConversationTaskDetailViewer();
          renderConversationTaskDrawer();
          renderConversationTaskEntry(ctx, payload);
          return;
        }
        PCONV.memoDrawerOpen = false;
        renderConversationMemoDrawer();
        renderConversationMemoEntry(ctx);
        PCONV.fileDrawerOpen = false;
        renderConversationFileDrawer();
        renderConversationFileEntry(ctx);
        PCONV.taskDrawerOpen = true;
        PCONV.taskDrawerSessionKey = key;
        renderConversationTaskDrawer(payload);
        renderConversationTaskEntry(ctx, payload);
      };
    }

    function closeConversationTaskDrawer() {
      const payload = currentConversationTaskPayload();
      PCONV.taskDrawerOpen = false;
      PCONV.taskDrawerSessionKey = "";
      resetConversationTaskDrawerRenderState();
      resetConversationTaskDetailViewer();
      renderConversationTaskDrawer();
      renderConversationTaskEntry(payload.ctx, payload);
    }

    function initConversationTaskUi() {
      const mask = document.getElementById("convTaskDrawerMask");
      const closeBtn = document.getElementById("convTaskCloseBtn");
      if (mask) {
        mask.addEventListener("click", (e) => {
          if (e.target === mask) closeConversationTaskDrawer();
        });
      }
      if (closeBtn) closeBtn.addEventListener("click", closeConversationTaskDrawer);
    }

    function copyConversationSessionId(sessionId) {
      const text = String(sessionId || "").trim();
      if (!text) return;
      if (typeof copyText === "function") {
        Promise.resolve(copyText(text))
          .then((ok) => {
            setHintText("conv", ok === false ? "复制失败：请手动复制 session ID" : "已复制 session ID");
          })
          .catch(() => { setHintText("conv", "复制失败：请手动复制 session ID"); });
        return;
      }
      navigator.clipboard?.writeText(text)
        .then(() => { setHintText("conv", "已复制 session ID"); })
        .catch(() => { setHintText("conv", "复制失败：请手动复制 session ID"); });
    }

    function buildConversationDetailSessionMeta(sessionId) {
      const text = String(sessionId || "").trim();
      if (!text) return null;
      const row = el("div", { class: "detail-title-meta" });
      row.appendChild(el("span", {
        class: "detail-inline-id",
        text,
        title: text,
      }));
      const copyBtn = el("button", {
        class: "detail-inline-copy-btn",
        type: "button",
        title: "复制 session ID",
        "aria-label": "复制 session ID",
        html: [
          '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">',
          '  <rect x="9" y="9" width="10" height="10" rx="2" stroke="currentColor" stroke-width="1.8"></rect>',
          '  <path d="M7 15H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>',
          '</svg>',
        ].join(""),
      });
      copyBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        copyConversationSessionId(text);
      });
      row.appendChild(copyBtn);
      return row;
    }

    function ensureConversationLocallyHiddenRunIds() {
      if (!PCONV.locallyHiddenRunIds || !(PCONV.locallyHiddenRunIds instanceof Set)) {
        PCONV.locallyHiddenRunIds = new Set();
      }
      return PCONV.locallyHiddenRunIds;
    }

    function markConversationRunLocallyHidden(runId, hidden = true) {
      const rid = String(runId || "").trim();
      if (!rid) return;
      const ids = ensureConversationLocallyHiddenRunIds();
      if (hidden) ids.add(rid);
      else ids.delete(rid);
    }

    function isConversationRunLocallyHidden(runId) {
      const rid = String(runId || "").trim();
      if (!rid) return false;
      const ids = ensureConversationLocallyHiddenRunIds();
      return ids.has(rid);
    }

    function renderConversationDetail(forceScroll = false) {
      const titleEl = document.getElementById("detailTitle");
      const subEl = document.getElementById("detailSub");
      const hintEl = document.getElementById("convHint");
      const senderHintEl = document.getElementById("convSenderHint");
      const taskSummaryEl = document.getElementById("convTaskSummary");
      const taskTrackingEl = document.getElementById("convTaskTracking");
      const timeline = document.getElementById("convTimeline");
      const input = document.getElementById("convMsg");
      const sendBtn = document.getElementById("convSendBtn");
      const memoSaveBtn = document.getElementById("convMemoSaveBtn");
      const pathBar = document.getElementById("detailPathBar");
      const convWrap = document.getElementById("convWrap");
      const basePlaceholder = conversationComposerPlaceholder("Codex");
      if (pathBar) pathBar.style.display = "none";
      if (!titleEl || !timeline || !input || !sendBtn || !hintEl || !subEl) return;
      if (convWrap && (STATE.panelMode === "conv" || STATE.selectedSessionId)) {
        convWrap.classList.add("show");
      }
      bindConvComposerToSelectedSession();

      captureDebugLogScrollPositions(timeline);
      const wasNearBottom = (timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight) < 80;
      const scrollAnchor = {
        scrollTop: Number(timeline.scrollTop || 0),
      };
      renderConversationTaskSummaryAndTracking(taskSummaryEl, taskTrackingEl, null);
      if (STATE.project === "overview") {
        titleEl.textContent = "项目对话";
        subEl.textContent = "";
        hintEl.textContent = "";
        if (senderHintEl) senderHintEl.textContent = "";
        renderConversationEnterSendToggle(false);
        renderConversationQuickTips(null, []);
        renderConversationTrainingPrompt(null, []);
        renderConvComposerRunActions(null, []);
        input.placeholder = "请先选择具体项目，再发送会话消息";
        input.disabled = true;
        sendBtn.disabled = true;
        if (memoSaveBtn) {
          memoSaveBtn.disabled = true;
          memoSaveBtn.textContent = "记录";
        }
        hideConvMentionSuggest();
        renderConversationRecentAgentsByKey("");
        hideConversationMemoEntry();
        hideConversationTaskEntry();
        PCONV.fileDrawerOpen = false;
        hideConversationFileEntry();
        renderConversationFileDrawer();
        renderConversationTaskDrawer();
        syncConversationTimelineChildren(timeline, [
          el("div", { class: "hint", text: "总揽模式不展示会话详情。" }),
        ]);
        markConversationTimelineRenderSignature(timeline, "");
        return;
      }

      const ctx = currentConversationCtx();
      if (!ctx) {
        titleEl.textContent = "项目对话";
        subEl.textContent = "";
        hintEl.textContent = "";
        if (senderHintEl) senderHintEl.textContent = "";
        renderConversationEnterSendToggle(false);
        renderConversationQuickTips(null, []);
        renderConversationTrainingPrompt(null, []);
        renderConvComposerRunActions(null, []);
        input.placeholder = "当前项目没有可用会话，请先维护 session_id";
        input.disabled = true;
        sendBtn.disabled = true;
        if (memoSaveBtn) {
          memoSaveBtn.disabled = true;
          memoSaveBtn.textContent = "记录";
        }
        hideConvMentionSuggest();
        renderConversationRecentAgentsByKey("");
        hideConversationMemoEntry();
        hideConversationTaskEntry();
        PCONV.fileDrawerOpen = false;
        hideConversationFileEntry();
        renderConversationFileDrawer();
        renderConversationTaskDrawer();
        syncConversationTimelineChildren(timeline, [
          el("div", { class: "hint", text: "无可用会话。" }),
        ]);
        markConversationTimelineRenderSignature(timeline, "");
        return;
      }

      const cliChipName = ctx && ctx.cliType ? String(ctx.cliType).toUpperCase() : "Codex";
      const agentDisplay = firstNonEmptyText([ctx.agentName, ctx.alias, ctx.displayChannel]) || "未命名会话";
      const currentSession = findConversationSessionById(String(ctx.sessionId || ""));
      const currentSessionId = String(ctx.sessionId || "").trim();
      if (currentSessionId && typeof ensureConversationSessionDetailLoaded === "function") {
        ensureConversationSessionDetailLoaded(currentSessionId, { maxAgeMs: 15_000 }).catch(() => {});
      }
      titleEl.innerHTML = "";
      const titleRow = el("div", { class: "detail-title-row" });
      titleRow.appendChild(buildConversationAvatarNode(currentSession || ctx));
      const titleStack = el("div", { class: "detail-title-stack" });
      const titleLine = el("div", { class: "detail-title-line" });
      titleLine.appendChild(el("span", { class: "detail-title-text", text: agentDisplay, title: agentDisplay }));
      titleLine.appendChild(buildConversationRoleBadge(currentSession || ctx));
      titleLine.appendChild(buildConversationCliBadge(currentSession || ctx, { detail: true }));
      const detailHeartbeatBadge = buildConversationHeartbeatBadges(currentSession || ctx);
      if (detailHeartbeatBadge) titleLine.appendChild(detailHeartbeatBadge);
      const titleStatus = buildConversationStatusBadge(currentSession || ctx);
      if (titleStatus) titleLine.appendChild(titleStatus);
      titleStack.appendChild(titleLine);
      const titleMeta = buildConversationDetailSessionMeta(ctx.sessionId);
      if (titleMeta) titleStack.appendChild(titleMeta);
      titleRow.appendChild(titleStack);
      titleEl.appendChild(titleRow);
      subEl.textContent = "";
      subEl.title = "";
      hintEl.textContent = "";
      if (senderHintEl) senderHintEl.textContent = buildConversationComposerSenderHint();
      renderConversationEnterSendToggle(PCONV.enterSendEnabled !== false);
      input.placeholder = conversationComposerPlaceholder(cliChipName);
      input.disabled = false;
      sendBtn.disabled = PCONV.sending;
      sendBtn.textContent = PCONV.sending ? "发送中..." : "发送";
      const memoKey = convComposerDraftKey(ctx.projectId, ctx.sessionId);
      const memoBusy = String(PCONV.memoActionBusyBySessionKey[memoKey] || "");
      if (memoSaveBtn) {
        memoSaveBtn.disabled = !!memoBusy;
        memoSaveBtn.textContent = memoBusy === "save" ? "记录中..." : "记录";
      }
      renderConversationMemoEntry(ctx);
      renderConversationFileEntry(ctx);
      const taskPayload = currentConversationTaskPayload();
      renderConversationTaskEntry(ctx, taskPayload);
      const consumedUnread = consumeConversationUnreadByCtx(ctx);
      if (consumedUnread) refreshConversationCountDots();
      ensureConversationMemosLoaded(ctx.projectId, ctx.sessionId, { maxAgeMs: 10_000 });
      if (PCONV.memoDrawerOpen) {
        PCONV.memoDrawerSessionKey = memoKey;
        renderConversationMemoDrawer();
      }
      if (PCONV.fileDrawerOpen) {
        PCONV.fileDrawerSessionKey = memoKey;
        renderConversationFileDrawer();
      }
      if (PCONV.taskDrawerOpen) {
        PCONV.taskDrawerSessionKey = memoKey;
      }
      renderConversationTaskDrawer(taskPayload);
      const stableRowReuseMap = buildConversationStableTimelineRowReuseMap(timeline);
      const nextTimelineNodes = [];
      const appendTimelineNode = (node) => {
        if (node) nextTimelineNodes.push(node);
      };

      const timelineKey = String(STATE.project || "") + "::" + String(ctx.sessionId || "");
      if (PCONV.autoExpandTimelineKey !== timelineKey) {
        // 每次进入一个会话：重置展开状态（仅最新消息默认展开）
        PCONV.autoExpandTimelineKey = timelineKey;
        PCONV.autoExpandDone = false;
        PCONV.autoExpandedLatestBubbleKey = "";
        PCONV.bubbleExpanded = new Set();
        PCONV.bubblePendingExpand = new Set();
        PCONV.inlineSnippetExpanded = new Set();
        PCONV.skillsExpandedByRun = Object.create(null);
        PCONV.businessRefsExpandedByRun = Object.create(null);
        PCONV.agentRefsExpandedByRun = Object.create(null);
      }
      const runSource = Array.isArray(PCONV.sessionTimelineMap[timelineKey])
        ? PCONV.sessionTimelineMap[timelineKey]
        : (PCONV.runsBySession[ctx.sessionId] || []);
      const runs = runSource.slice().sort((a, b) => {
        const ta = toTimeNum(a.createdAt);
        const tb = toTimeNum(b.createdAt);
        if (ta >= 0 && tb >= 0 && ta !== tb) return ta - tb; // oldest first (newest at bottom)
        return String(a.createdAt || "").localeCompare(String(b.createdAt || ""));
      });
      const currentRuntimeState = getSessionRuntimeState(currentSession);
      const timelineRenderSignature = buildConversationTimelineRenderSignature(ctx, {
        displayRuns: runs,
        runtimeState: currentRuntimeState,
      });
      if (shouldReuseConversationTimelineDom(timeline, timelineRenderSignature, { forceScroll })) {
        markConversationTimelineRenderSignature(timeline, timelineRenderSignature);
      }
      const currentQueueDepth = (() => {
        const runtimeDepth = Math.max(0, Number((currentRuntimeState && currentRuntimeState.queue_depth) || 0));
        const fallbackDepth = runs.reduce((count, item) => {
          const oneStatus = getRunDisplayState(item, PCONV.detailMap[String((item && item.id) || "")] || null);
          return count + ((oneStatus === "queued" || oneStatus === "retry_waiting") ? 1 : 0);
        }, 0);
        return Math.max(runtimeDepth, fallbackDepth);
      })();
      const runtimeShadowMeta = buildConversationRuntimeShadowMeta(currentRuntimeState, runs);
      const runtimeShadowRuns = buildConversationRuntimeShadowRuns(ctx, currentSession, currentRuntimeState, runtimeShadowMeta);
      const liveRunHint = buildConversationLiveRunHint(runs);
      const sessionRunSummary = buildConversationSessionRunSummary(currentSession, currentRuntimeState, liveRunHint);
      const currentActiveRunId = String(firstNonEmptyText([
        currentRuntimeState && currentRuntimeState.active_run_id,
        liveRunHint && liveRunHint.runId,
      ]) || "").trim();
      const currentQueuedRunId = String((currentRuntimeState && currentRuntimeState.queued_run_id) || "").trim();
      hintEl.textContent = "";
      hintEl.title = "";
      subEl.textContent = sessionRunSummary ? String(sessionRunSummary.text || "") : "";
      subEl.title = sessionRunSummary ? String(sessionRunSummary.title || sessionRunSummary.text || "") : "";
      const timelineLoading = PCONV.timelineLoadingKey === timelineKey;
      const timelineLoadingBefore = PCONV.timelineBeforeLoadingKey === timelineKey;
      const timelineBeforeError = String(PCONV.timelineBeforeErrorByKey[timelineKey] || "");
      const hasStoredBeforeFlag = Object.prototype.hasOwnProperty.call(PCONV.timelineBeforeHasMoreByKey, timelineKey);
      const hasSessionTimelineCache = Array.isArray(PCONV.sessionTimelineMap[timelineKey]);
      const timelineHasMoreBefore = hasStoredBeforeFlag
        ? !!PCONV.timelineBeforeHasMoreByKey[timelineKey]
        : (hasSessionTimelineCache ? runs.length >= CONV_PAGE.timelineInitial : runs.length > 0);
      renderConversationQuickTips(ctx, runs);
      renderConversationTrainingPrompt(ctx, runs, { timelineReady: hasSessionTimelineCache });
      refreshConversationRecentAgentsFromRuns(ctx, runs);
      renderConvComposerRunActions(ctx, runs);
      // 找到“最新可展开”的 AI 正文：
      // 1) 只考虑终态消息；
      // 2) 系统回执/恢复摘要不抢自动展开位；
      // 3) 短消息不自动展开，继续向上找最近一条真正需要展开的正文。
      let latestExpandableBubbleKey = "";
      for (let i = runs.length - 1; i >= 0; i--) {
        const rr = runs[i] || {};
        const rid = String(rr.id || "");
        if (!rid) continue;
        const detail = PCONV.detailMap[rid] || null;
        const rs = String(getRunDisplayState(rr, detail) || rr.status || "");
        if (isRunWorking(rs)) continue;
        const senderType = String(firstNonEmptyText([
          rr && rr.sender_type,
          rr && rr.senderType,
          detail && detail.full && detail.full.run && detail.full.run.sender_type,
          detail && detail.full && detail.full.run && detail.full.run.senderType,
        ]) || "").trim().toLowerCase();
        const messageKind = String(firstNonEmptyText([
          rr && rr.communication_view && rr.communication_view.message_kind,
          rr && rr.communicationView && rr.communicationView.message_kind,
          rr && rr.trigger_type,
          rr && rr.triggerType,
          detail && detail.full && detail.full.run && detail.full.run.trigger_type,
          detail && detail.full && detail.full.run && detail.full.run.triggerType,
        ]) || "").trim().toLowerCase();
        const callbackLike = messageKind === "system_callback"
          || messageKind === "system_callback_summary"
          || messageKind === "restart_recovery_summary";
        if (senderType === "system" || callbackLike) continue;
        const assistantPreview = String(resolveAssistantText(rr, detail) || "").trim();
        if (!shouldFoldBubble(assistantPreview, "assistant")) continue;
        latestExpandableBubbleKey = rid + ":assistant";
        break;
      }
      if (latestExpandableBubbleKey) {
        PCONV.autoExpandDone = true;
        PCONV.autoExpandedLatestBubbleKey = latestExpandableBubbleKey;
      }

      if (!runs.length && !(PCONV.optimistic && PCONV.optimistic.sessionId === ctx.sessionId)) {
        appendTimelineNode(el("div", { class: "hint", text: timelineLoading ? "加载会话记录中..." : "该会话暂无消息记录，可直接在下方发送消息。" }));
      }

      if (runs.length || timelineLoadingBefore || timelineBeforeError) {
        const historyBar = el("div", { class: "conv-historybar" });
        const loadOlderBtn = el("button", {
          class: "btn conv-history-btn",
          text: timelineLoadingBefore
            ? "加载更早消息中..."
            : (timelineHasMoreBefore ? "加载更早消息" : "已到最早消息"),
        });
        loadOlderBtn.disabled = !!timelineLoadingBefore || !timelineHasMoreBefore;
        loadOlderBtn.addEventListener("click", () => {
          if (loadOlderBtn.disabled) return;
          loadOlderConversationTimeline(String(ctx.projectId || STATE.project || ""), String(ctx.sessionId || ""));
        });
        historyBar.appendChild(loadOlderBtn);
        if (timelineBeforeError) {
          historyBar.appendChild(el("span", { class: "conv-history-error", text: timelineBeforeError }));
        } else if (!timelineHasMoreBefore && runs.length > 0) {
          historyBar.appendChild(el("span", { class: "conv-history-done", text: "历史消息已全部加载" }));
        }
        appendTimelineNode(historyBar);
      }

      const seenCallbackEventKeys = new Set();
      const seenRestartRecoveryKeys = new Set();
      const visibleRuns = runs.filter((item) => !isConversationRunLocallyHidden(item && item.id));
      const visibleRunIds = new Set(visibleRuns.map((item) => String((item && item.id) || "").trim()).filter(Boolean));
      const runsById = new Map(visibleRuns.map((item) => [String((item && item.id) || "").trim(), item]));
      const localReceiptAnchorMaps = buildConversationLocalReceiptAnchorMaps(visibleRuns, visibleRunIds, runsById, PCONV.detailMap, ctx);
      const localReceiptProjectionByRunId = (localReceiptAnchorMaps && localReceiptAnchorMaps.anchoredByHostRunId) || Object.create(null);
      const localAnchoredCallbackRunIds = (localReceiptAnchorMaps && localReceiptAnchorMaps.anchoredCallbackRunIds) || new Set();
      for (const r of visibleRuns) {
        const rid = String(r.id || "");
        const d = PCONV.detailMap[rid] || null;
        const st = getRunDisplayState(r, d);
        const queueReason = getRunQueueReason(r, d);
        const queueReasonText = queueReasonLabel(queueReason);
        const blockedByRunId = getRunBlockedByRunId(r, d);
        const blockedByText = blockedByRunId ? shortId(blockedByRunId) : "";
        const actionBusy = String(PCONV.runActionBusy[rid] || "");
        const stNorm = String(st || "").toLowerCase();
        const timeoutLike = stNorm === "error" && isRunTimeoutLike(r, d);
        const userText = (d && d.full && d.full.message) ? String(d.full.message) : String(r.messagePreview || "");
        const assistantText = resolveAssistantText(r, d);
        const displayUserText = stripInjectedConversationReplyText(userText);
        const displayAssistantText = stripInjectedConversationReplyText(assistantText);
        const err = String(r.error || "").trim();
        const hint = String(r.errorHint || "").trim();
        const senderRun = mergeRunForDisplay(
          (d && d.full && d.full.run && typeof d.full.run === "object") ? d.full.run : null,
          r
        );
        const userMessageKind = resolveConversationMessageKind(senderRun, "user");
        const assistantMessageKind = resolveConversationMessageKind(senderRun, "assistant");
        const userSender = resolveMessageSender(senderRun, {
          role: "user",
          cliType: firstNonEmptyText([senderRun && senderRun.cliType, r && r.cliType, ctx && ctx.cliType]),
          channelName: firstNonEmptyText([senderRun && senderRun.channelName, r && r.channelName, ctx && ctx.channelName]),
          displayChannel: firstNonEmptyText([ctx && ctx.alias, ctx && ctx.displayChannel]),
          textCandidates: [userText, String(r.messagePreview || "")],
        });
        const assistantSender = resolveMessageSender(senderRun, {
          role: "assistant",
          cliType: firstNonEmptyText([senderRun && senderRun.cliType, r && r.cliType, ctx && ctx.cliType]),
          agentName: firstNonEmptyText([ctx && ctx.agentName, ctx && ctx.alias, ctx && ctx.displayName, ctx && ctx.displayChannel]),
          channelName: firstNonEmptyText([senderRun && senderRun.channelName, r && r.channelName, ctx && ctx.channelName]),
          displayChannel: firstNonEmptyText([ctx && ctx.alias, ctx && ctx.displayChannel]),
          textCandidates: [assistantText, String(r.lastPreview || ""), String(r.partialPreview || "")],
        });
        const runSpec = readConversationSpecFields(senderRun);
        // Get attachments from run data
        const attachments = Array.isArray(r.attachments) ? r.attachments : [];
        const userInputAttachments = collectConversationUserInputAttachments(attachments);
        const assistantGeneratedAttachments = collectConversationGeneratedAssistantImageAttachments(attachments);
        const callbackEventMeta = readRunCallbackEventMeta(senderRun, ctx, userText || String(r.messagePreview || ""));
        const receiptProjection = mergeConversationReceiptProjection(
          readConversationReceiptProjection(senderRun, d),
          rid ? (localReceiptProjectionByRunId[rid] || null) : null
        );
        const projectedReceiptHostRunId = callbackEventMeta
          ? resolveConversationReceiptHostRunId(senderRun, rid, visibleRunIds, runsById, PCONV.detailMap)
          : "";
        const projectedHostRun = projectedReceiptHostRunId
          ? (runsById.get(projectedReceiptHostRunId) || null)
          : null;
        const projectedHostDetail = projectedReceiptHostRunId
          ? (PCONV.detailMap[projectedReceiptHostRunId] || null)
          : null;
        const projectedHostStatus = projectedReceiptHostRunId
          ? String(getRunDisplayState(projectedHostRun, projectedHostDetail) || "").trim().toLowerCase()
          : "";
        const projectedHostReceiptProjection = projectedReceiptHostRunId
          ? readConversationReceiptProjection(projectedHostRun, projectedHostDetail)
          : null;
        const callbackProjectedToVisibleHost = !!(
          callbackEventMeta
          && projectedReceiptHostRunId
          && projectedReceiptHostRunId !== rid
          && visibleRunIds.has(projectedReceiptHostRunId)
          && !isRunWorking(projectedHostStatus)
          && conversationReceiptProjectionMatchesHost(projectedHostReceiptProjection, {
            callbackRunId: rid,
            relatedRunIds: [rid].concat(collectConversationReceiptHostRunIds(senderRun)),
          })
        );
        const callbackLocallyAnchored = !!(callbackEventMeta && rid && localAnchoredCallbackRunIds.has(rid));
        let callbackEventDuplicate = false;
        if (callbackEventMeta && callbackEventMeta.dedupeKey) {
          if (seenCallbackEventKeys.has(callbackEventMeta.dedupeKey)) callbackEventDuplicate = true;
          else seenCallbackEventKeys.add(callbackEventMeta.dedupeKey);
        }
        const restartRecoveryMeta = readRunRestartRecoveryMeta(senderRun, ctx);
        let restartRecoveryDuplicate = false;
        if (restartRecoveryMeta && restartRecoveryMeta.dedupeKey) {
          if (seenRestartRecoveryKeys.has(restartRecoveryMeta.dedupeKey)) restartRecoveryDuplicate = true;
          else seenRestartRecoveryKeys.add(restartRecoveryMeta.dedupeKey);
        }

        const aggregateMeta = getRunAggregateMeta(senderRun, d);
        const aggregateCount = callbackEventMeta
          ? Math.max(Number(callbackEventMeta.aggregateCount || 0), Number(aggregateMeta.aggregateCount || 0))
          : Number(aggregateMeta.aggregateCount || 0);
        const aggregateLastMergedAt = firstNonEmptyText([
          callbackEventMeta && callbackEventMeta.callbackLastMergedAt,
          aggregateMeta && aggregateMeta.lastMergedAt,
        ]);
        const replyContext = readConversationReplyContext(senderRun, userText || assistantText || String(r.messagePreview || ""));
        const mentionTargets = collectRunMentionTargets(senderRun, d, userText);
        const queuedCompactMode = (st === "queued" && !restartRecoveryMeta);
        const systemFamilyMode = !!(callbackEventMeta || restartRecoveryMeta);
        const userVisualMode = resolveConversationUserVisualMode({
          senderRun,
          runSpec,
          userSender,
          userMessageKind,
          displayUserText,
          userText,
          sourceText: firstNonEmptyText([
            userText,
            displayUserText,
            r.messagePreview,
            d && d.full && d.full.lastMessage,
            d && d.full && d.full.message,
          ]),
        });
        const userSenderType = String(firstNonEmptyText([userSender && userSender.type, runSpec && runSpec.senderType]) || "").trim().toLowerCase();
        const isAgentInbound = userVisualMode.kind === "agent-inbound" || (userSenderType === "agent" && userVisualMode.displayMode !== "receipt" && userVisualMode.kind === "collab-inbound");
        if (systemFamilyMode) {
          if ((callbackProjectedToVisibleHost || callbackLocallyAnchored) && !restartRecoveryMeta) continue;
          const systemRow = renderConversationSystemFamily({
            rid,
            r,
            d,
            ctx,
            runSpec,
            userSender,
            displayUserText,
            userText,
            attachments,
            replyContext,
            callbackEventMeta,
            callbackEventDuplicate,
            restartRecoveryMeta,
            restartRecoveryDuplicate,
            queuedCompactMode,
            currentQueueDepth,
            aggregateCount,
            aggregateLastMergedAt,
            actionBusy,
            mentionTargets,
          });
          appendTimelineNode(systemRow);
          continue;
        }

        const stableUserRowMeta = buildConversationUserStableRowMeta({
          run: r,
          detail: d,
          runId: rid,
          status: st,
          attachments: userInputAttachments,
          text: displayUserText || userText || String(r.messagePreview || ""),
          bubbleKey: rid + ":user",
          userVisualMode,
          replyContext,
          mentionTargets,
          queuedCompactMode,
          systemLike: !!callbackEventMeta || !!restartRecoveryMeta,
          agentInbound: isAgentInbound,
          receiptInbound: userVisualMode.kind === "receipt-inbound",
          opts: { forceRefresh: forceScroll },
        });
        const reusedUserRow = stableUserRowMeta
          ? reuseConversationStableTimelineRow(stableRowReuseMap, stableUserRowMeta.key, stableUserRowMeta.signature, userInputAttachments)
          : null;
        const userRow = reusedUserRow || renderConversationUserFamily({
          rid,
          r,
          d,
          senderRun,
          ctx,
          runSpec,
          userSender,
          userMessageKind,
          displayUserText,
          userText,
          attachments: userInputAttachments,
          replyContext,
          queuedCompactMode,
          callbackEventMeta,
          callbackEventDuplicate,
          restartRecoveryMeta,
          restartRecoveryDuplicate,
          currentQueueDepth,
          aggregateCount,
          aggregateLastMergedAt,
          actionBusy,
          mentionTargets,
          userVisualMode,
        });
        if (!reusedUserRow && stableUserRowMeta) {
          markConversationStableTimelineRow(userRow, stableUserRowMeta.key, stableUserRowMeta.signature);
        }
        appendTimelineNode(userRow);
        if (queuedCompactMode) continue;
        const aiRow = renderConversationAssistantFamily({
          rid,
          r,
          d,
          ctx,
          runSpec,
          st,
          timeoutLike,
          actionBusy,
          assistantSender,
          assistantMessageKind,
          assistantText,
          displayAssistantText,
          displayUserText,
          err,
          hint,
          attachments: assistantGeneratedAttachments,
          callbackEventMeta,
          restartRecoveryMeta,
          queueReasonText,
          blockedByText,
          receiptProjection: isRunWorking(stNorm) ? null : receiptProjection,
          mentionTargets,
          currentActiveRunId,
          currentQueuedRunId,
        });
        appendTimelineNode(aiRow);
      }

      if (runtimeShadowRuns.activeRun) {
        const shadowRun = runtimeShadowRuns.activeRun;
        const shadowSender = resolveMessageSender(shadowRun, {
          role: "assistant",
          cliType: firstNonEmptyText([shadowRun.cliType, ctx && ctx.cliType]),
          agentName: firstNonEmptyText([ctx && ctx.agentName, ctx && ctx.alias, ctx && ctx.displayName, ctx && ctx.displayChannel]),
          channelName: firstNonEmptyText([shadowRun.channelName, ctx && ctx.channelName]),
          displayChannel: firstNonEmptyText([ctx && ctx.alias, ctx && ctx.displayChannel]),
          textCandidates: [],
        });
        const shadowAiRow = renderConversationAssistantFamily({
          rid: String(shadowRun.id || ""),
          r: shadowRun,
          d: null,
          ctx,
          runSpec: readConversationSpecFields(shadowRun),
          st: "running",
          timeoutLike: false,
          actionBusy: "",
          assistantSender: shadowSender,
          assistantMessageKind: resolveConversationMessageKind(shadowRun, "assistant"),
          assistantText: "",
          displayAssistantText: "",
          displayUserText: "",
          err: "",
          hint: "",
          callbackEventMeta: null,
          restartRecoveryMeta: null,
          queueReasonText: "",
          blockedByText: "",
          attachments: Array.isArray(shadowRun.attachments) ? shadowRun.attachments : [],
          receiptProjection: null,
          mentionTargets: [],
        });
        shadowAiRow.classList.add("runtime-shadow");
        appendTimelineNode(shadowAiRow);
      }

      if (runtimeShadowRuns.queuedRun) {
        const shadowRun = runtimeShadowRuns.queuedRun;
        const shadowSender = resolveMessageSender(shadowRun, {
          role: "user",
          cliType: firstNonEmptyText([shadowRun.cliType, ctx && ctx.cliType]),
          channelName: firstNonEmptyText([shadowRun.channelName, ctx && ctx.channelName]),
          displayChannel: firstNonEmptyText([ctx && ctx.displayChannel, ctx && ctx.alias]),
          textCandidates: [shadowRun.messagePreview],
        });
        const shadowUserRow = renderConversationUserFamily({
          rid: String(shadowRun.id || ""),
          r: shadowRun,
          d: null,
          senderRun: shadowRun,
          ctx,
          runSpec: readConversationSpecFields(shadowRun),
          userSender: shadowSender,
          userMessageKind: resolveConversationMessageKind(shadowRun, "user"),
          displayUserText: String(shadowRun.messagePreview || ""),
          userText: String(shadowRun.messagePreview || ""),
          attachments: [],
          replyContext: null,
          queuedCompactMode: true,
          callbackEventMeta: null,
          callbackEventDuplicate: false,
          restartRecoveryMeta: null,
          restartRecoveryDuplicate: false,
          currentQueueDepth,
          aggregateCount: 0,
          aggregateLastMergedAt: "",
          actionBusy: "",
          mentionTargets: [],
        });
        shadowUserRow.classList.add("runtime-shadow");
        appendTimelineNode(shadowUserRow);
      }

      if (PCONV.optimistic && PCONV.optimistic.sessionId === ctx.sessionId) {
        const m = PCONV.optimistic;
        const userRow = renderConversationOptimisticUserFamily({
          ctx,
          message: m,
        });
        appendTimelineNode(userRow);
      }

      syncConversationTimelineChildren(timeline, nextTimelineNodes);

      syncConversationReceiptViewerMount();

      refreshConversationFilesFromTimeline(ctx, timeline);
      renderConversationFileUi();
      markConversationTimelineRenderSignature(timeline, timelineRenderSignature);

      if (forceScroll || wasNearBottom) {
        maybeStickConversationBottom(true);
      } else {
        restoreConversationTimelineScroll(timeline, scrollAnchor);
        requestAnimationFrame(() => restoreConversationTimelineScroll(timeline, scrollAnchor));
      }
    }

    async function refreshConversationTimeline(projectId, sessionId, forceScroll = false) {
      if (typeof isTaskShareModeActive === "function" && isTaskShareModeActive()) {
        const pid = String(projectId || STATE.project || "").trim();
        const sid = String(sessionId || STATE.selectedSessionId || "").trim();
        if (!pid || !sid) return;
        await loadTaskShareModeSession(sid, { force: true });
        renderConversationDetail(forceScroll);
        return;
      }
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      if (!pid || !sid || pid === "overview") return;
      if (
        isConversationListScrollActive()
        && String(STATE.project || "").trim() === pid
        && String(STATE.selectedSessionId || "").trim() === sid
      ) {
        queueDeferredConversationRender({
          panelRender: true,
          projectId: pid,
          sessionId: sid,
          forceScroll,
        });
        return;
      }
      const key = pid + "::" + sid;
      const shouldForce = forceScroll || !Array.isArray(PCONV.sessionTimelineMap[key]);
      let shouldRefreshCountDots = false;
      const seq = ++PCONV.timelineRequestSeq;
      PCONV.timelineLoadingKey = key;
      try {
        const hasSessionTimelineCache = Array.isArray(PCONV.sessionTimelineMap[key]);
        const existingRuns = hasSessionTimelineCache
          ? PCONV.sessionTimelineMap[key]
          : (Array.isArray(PCONV.runsBySession[sid]) ? PCONV.runsBySession[sid] : []);
        const prevUnreadTerminalAt = latestUnreadTerminalCreatedAt(existingRuns);
        // Only use incremental pull after this session has its own dedicated timeline cache.
        const canIncremental = hasSessionTimelineCache && existingRuns.length > 0 && !hasWorkingRun(existingRuns);
        const cursor = canIncremental ? incrementalAfterCursorWithOverlap(existingRuns, 1000) : "";
        const requestLimit = canIncremental
          ? CONV_PAGE.timelineIncremental
          : CONV_PAGE.timelineInitial;
        const resp = await loadRuns({
          projectId: pid,
          sessionId: sid,
          limit: requestLimit,
          afterCreatedAt: cursor,
          payloadMode: "light",
        });
        if (seq !== PCONV.timelineRequestSeq) return;
        const incoming = Array.isArray(resp && resp.runs) ? resp.runs : [];
        const keepLimit = Math.max(260, Math.min(1200, Number(existingRuns.length || 0) + 120));
        const mergedRuns = mergeRunsById(existingRuns, incoming, keepLimit);
        PCONV.sessionTimelineMap[key] = mergedRuns;
        const nextUnreadTerminalAt = latestUnreadTerminalCreatedAt(mergedRuns);
        if (nextUnreadTerminalAt && nextUnreadTerminalAt !== prevUnreadTerminalAt) {
          shouldRefreshCountDots = true;
        }
        if (canIncremental) {
          if (!Object.prototype.hasOwnProperty.call(PCONV.timelineBeforeHasMoreByKey, key)) {
            PCONV.timelineBeforeHasMoreByKey[key] = existingRuns.length >= CONV_PAGE.timelineInitial;
          }
        } else {
          PCONV.timelineBeforeHasMoreByKey[key] = (incoming.length >= requestLimit) || (mergedRuns.length > incoming.length);
        }
        PCONV.timelineBeforeErrorByKey[key] = "";
      } catch (_) {
        if (seq !== PCONV.timelineRequestSeq) return;
        // Keep fallback timeline from project-level grouping.
      } finally {
        if (seq === PCONV.timelineRequestSeq) PCONV.timelineLoadingKey = "";
        if (shouldRefreshCountDots) refreshConversationCountDots();
        renderConversationDetail(shouldForce);
      }
    }

    async function loadOlderConversationTimeline(projectId, sessionId) {
      const pid = String(projectId || "").trim();
      const sid = String(sessionId || "").trim();
      if (!pid || !sid || pid === "overview") return;
      const key = pid + "::" + sid;
      if (PCONV.timelineBeforeLoadingKey === key) return;
      const existingRuns = Array.isArray(PCONV.sessionTimelineMap[key])
        ? PCONV.sessionTimelineMap[key].slice()
        : (Array.isArray(PCONV.runsBySession[sid]) ? PCONV.runsBySession[sid].slice() : []);
      if (!existingRuns.length) return;
      const beforeCursor = runsOldestCreatedAt(existingRuns);
      if (!beforeCursor) return;

      const timelineBox = document.getElementById("convTimeline");
      const prevHeight = timelineBox ? Number(timelineBox.scrollHeight || 0) : 0;
      const prevTop = timelineBox ? Number(timelineBox.scrollTop || 0) : 0;
      let needRestoreScroll = false;

      const beforeLimit = CONV_PAGE.timelineBefore;
      PCONV.timelineBeforeLoadingKey = key;
      PCONV.timelineBeforeErrorByKey[key] = "";
      renderConversationDetail(false);
      try {
        const resp = await loadRuns({
          projectId: pid,
          sessionId: sid,
          limit: beforeLimit,
          beforeCreatedAt: beforeCursor,
          payloadMode: "light",
        });
        const incoming = Array.isArray(resp && resp.runs) ? resp.runs : [];
        const keepLimit = Math.max(320, Math.min(1200, existingRuns.length + beforeLimit + 40));
        PCONV.sessionTimelineMap[key] = mergeRunsById(existingRuns, incoming, keepLimit);
        PCONV.timelineBeforeHasMoreByKey[key] = incoming.length >= beforeLimit;
        PCONV.timelineBeforeErrorByKey[key] = "";
        needRestoreScroll = incoming.length > 0;
      } catch (e) {
        PCONV.timelineBeforeErrorByKey[key] = "历史加载失败：" + String((e && e.message) || e || "unknown");
      } finally {
        if (PCONV.timelineBeforeLoadingKey === key) PCONV.timelineBeforeLoadingKey = "";
        renderConversationDetail(false);
        if (needRestoreScroll) {
          requestAnimationFrame(() => {
            const box = document.getElementById("convTimeline");
            if (!box) return;
            const delta = Math.max(0, Number(box.scrollHeight || 0) - prevHeight);
            box.scrollTop = Math.max(0, prevTop + delta);
          });
        }
      }
    }

    // 加载项目会话数据（不依赖 panelMode，可供任务模式和对话模式共用）
    async function loadProjectConversations(projectId) {
      const pid = String(projectId || STATE.project || "");
      if (!pid || pid === "overview") {
        PCONV.sessions = [];
        PCONV.sessionDirectoryByProject = Object.create(null);
        PCONV.sessionDirectoryMetaByProject = Object.create(null);
        PCONV.sessionDirectoryPromiseByProject = Object.create(null);
        PCONV.projectRuns = [];
        PCONV.runsBySession = Object.create(null);
        PCONV.sessionTimelineMap = Object.create(null);
        PCONV.timelineRequestSeq = 0;
        PCONV.timelineLoadingKey = "";
        PCONV.timelineBeforeLoadingKey = "";
        PCONV.timelineBeforeHasMoreByKey = Object.create(null);
        PCONV.timelineBeforeErrorByKey = Object.create(null);
        PCONV.memoDrawerOpen = false;
        PCONV.memoDrawerSessionKey = "";
        PCONV.taskDrawerOpen = false;
        PCONV.taskDrawerSessionKey = "";
        resetConversationTaskDrawerRenderState();
        resetConversationTaskDetailViewer();
        PCONV.fileDrawerOpen = false;
        PCONV.fileDrawerSessionKey = "";
        return;
      }

      // 始终重置项目切换时的缓存
      if (PCONV.lastProjectId !== pid) {
        PCONV.lastProjectId = pid;
        PCONV.sessions = [];
        PCONV.detailMap = Object.create(null);
        PCONV.debugExpanded = new Set();
        PCONV.debugLogScrollTop = Object.create(null);
        PCONV.bubbleExpanded = new Set();
        PCONV.bubblePendingExpand = new Set();
        PCONV.processUi = Object.create(null);
        PCONV.runDetailTabByRun = Object.create(null);
        PCONV.skillsExpandedByRun = Object.create(null);
        PCONV.businessRefsExpandedByRun = Object.create(null);
        PCONV.agentRefsExpandedByRun = Object.create(null);
        PCONV.processTrailByRun = Object.create(null);
        PCONV.sessionTimelineMap = Object.create(null);
        PCONV.timelineRequestSeq = 0;
        PCONV.timelineLoadingKey = "";
        PCONV.timelineBeforeLoadingKey = "";
        PCONV.timelineBeforeHasMoreByKey = Object.create(null);
        PCONV.timelineBeforeErrorByKey = Object.create(null);
        PCONV.autoExpandTimelineKey = "";
        PCONV.autoExpandDone = false;
        PCONV.autoExpandedLatestBubbleKey = "";
        PCONV.memoDrawerOpen = false;
        PCONV.memoDrawerSessionKey = "";
        PCONV.taskDrawerOpen = false;
        PCONV.taskDrawerSessionKey = "";
        resetConversationTaskDrawerRenderState();
        resetConversationTaskDetailViewer();
        PCONV.fileDrawerOpen = false;
        PCONV.fileDrawerSessionKey = "";
      }

      // 如果已经加载过且没有变化，直接返回
      if (PCONV.sessions && PCONV.sessions.length > 0 && PCONV.lastProjectId === pid) {
        return;
      }

      try {
        await loadChannelSessions(pid, null);
        const serverSessions = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
        let baseSessions = mergeConversationSessions(configuredProjectConversations(pid), serverSessions);
        PCONV.projectRuns = [];
        PCONV.runsBySession = Object.create(null);
        for (const s of baseSessions) {
          const latestRunSummary = getSessionLatestRunSummary(s);
          const preferSyntheticPreviewSender = sessionUsesSyntheticPreviewSender(s, getSessionPrimaryPreviewText(s));
          s.lastActiveAt = String(s.lastActiveAt || latestRunSummary.updated_at || s.last_used_at || "");
          s.lastStatus = getSessionStatus(s);
          s.lastError = String(s.lastError || latestRunSummary.error || "");
          s.lastPreview = String(getSessionPrimaryPreviewText(s) || s.lastPreview || latestRunSummary.preview || "");
          s.lastSpeaker = String(s.lastSpeaker || (preferSyntheticPreviewSender ? "assistant" : (latestRunSummary.speaker || "assistant")) || "assistant");
          s.lastSenderType = String(s.lastSenderType || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_type || "legacy")));
          s.lastSenderName = String(s.lastSenderName || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_name || "")));
          s.lastSenderSource = String(s.lastSenderSource || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_source || "legacy")));
          s.latestUserMsg = String(s.latestUserMsg || latestRunSummary.latest_user_msg || "");
          s.latestAiMsg = String(s.latestAiMsg || latestRunSummary.latest_ai_msg || "");
          s.runCount = Math.max(0, Number(s.runCount || latestRunSummary.run_count || 0) || 0);
          if (!s.primaryChannel) s.primaryChannel = (s.channels && s.channels[0]) ? String(s.channels[0]) : "";
          if (!s.displayChannel) s.displayChannel = s.primaryChannel || s.alias || s.sessionId;
        }

        seedConversationUnreadCursorsForSessions(pid, baseSessions);

        PCONV.sessionDirectoryByProject[pid] = baseSessions.slice();
        markConversationSessionDirectoryMeta(pid, {
          liveLoaded: true,
          source: "panel",
          loadedAt: new Date().toISOString(),
          error: "",
        });
        PCONV.sessions = baseSessions;
        PCONV.lastRefreshAt = new Date().toISOString().slice(0, 16).replace("T", " ");
      } catch (e) {
        console.error("loadProjectConversations error:", e);
      }
    }

    async function refreshConversationPanel() {
      if (typeof isTaskShareModeActive === "function" && isTaskShareModeActive()) {
        await refreshTaskShareModeConversationPanel();
        return;
      }
      if (PCONV.busy) return;
      const projectId = String(STATE.project || "");
      if (!projectId || projectId === "overview") {
        stopConversationPoll();
        PCONV.sessions = [];
        PCONV.sessionDirectoryByProject = Object.create(null);
        PCONV.sessionDirectoryMetaByProject = Object.create(null);
        PCONV.sessionDirectoryPromiseByProject = Object.create(null);
        PCONV.projectRuns = [];
        PCONV.runsBySession = Object.create(null);
        PCONV.sessionTimelineMap = Object.create(null);
        PCONV.debugLogScrollTop = Object.create(null);
        PCONV.bubbleExpanded = new Set();
        PCONV.bubblePendingExpand = new Set();
        PCONV.processUi = Object.create(null);
        PCONV.runDetailTabByRun = Object.create(null);
        PCONV.skillsExpandedByRun = Object.create(null);
        PCONV.businessRefsExpandedByRun = Object.create(null);
        PCONV.agentRefsExpandedByRun = Object.create(null);
        PCONV.processTrailByRun = Object.create(null);
        PCONV.timelineRequestSeq = 0;
        PCONV.timelineLoadingKey = "";
        PCONV.timelineBeforeLoadingKey = "";
        PCONV.timelineBeforeHasMoreByKey = Object.create(null);
        PCONV.timelineBeforeErrorByKey = Object.create(null);
        PCONV.autoExpandTimelineKey = "";
        PCONV.autoExpandDone = false;
        PCONV.autoExpandedLatestBubbleKey = "";
        PCONV.memoDrawerOpen = false;
        PCONV.memoDrawerSessionKey = "";
        PCONV.taskDrawerOpen = false;
        PCONV.taskDrawerSessionKey = "";
        resetConversationTaskDrawerRenderState();
        resetConversationTaskDetailViewer();
        PCONV.fileDrawerOpen = false;
        PCONV.fileDrawerSessionKey = "";
        if (STATE.panelMode === "conv") {
          buildConversationLeftList();
          buildConversationMainList(document.getElementById("fileList"));
          renderConversationDetail(true);
        } else {
          buildChannelConversationList();
          renderDetail(selectedItem());
        }
        return;
      }

      if (PCONV.lastProjectId !== projectId) {
        PCONV.lastProjectId = projectId;
        PCONV.detailMap = Object.create(null);
        PCONV.debugExpanded = new Set();
        PCONV.debugLogScrollTop = Object.create(null);
        PCONV.bubbleExpanded = new Set();
        PCONV.bubblePendingExpand = new Set();
        PCONV.processUi = Object.create(null);
        PCONV.runDetailTabByRun = Object.create(null);
        PCONV.skillsExpandedByRun = Object.create(null);
        PCONV.businessRefsExpandedByRun = Object.create(null);
        PCONV.agentRefsExpandedByRun = Object.create(null);
        PCONV.processTrailByRun = Object.create(null);
        PCONV.sessionTimelineMap = Object.create(null);
        PCONV.timelineRequestSeq = 0;
        PCONV.timelineLoadingKey = "";
        PCONV.timelineBeforeLoadingKey = "";
        PCONV.timelineBeforeHasMoreByKey = Object.create(null);
        PCONV.timelineBeforeErrorByKey = Object.create(null);
        PCONV.autoExpandTimelineKey = "";
        PCONV.autoExpandDone = false;
        PCONV.autoExpandedLatestBubbleKey = "";
        PCONV.memoDrawerOpen = false;
        PCONV.memoDrawerSessionKey = "";
        PCONV.taskDrawerOpen = false;
        PCONV.taskDrawerSessionKey = "";
        resetConversationTaskDrawerRenderState();
        resetConversationTaskDetailViewer();
        PCONV.fileDrawerOpen = false;
        PCONV.fileDrawerSessionKey = "";
      }

      PCONV.busy = true;
      try {
        // 先加载服务端会话，再与本地绑定会话合并，避免“绑定成功但列表不可见”。
        await loadChannelSessions(projectId, null);
        const serverSessions = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
        const localSessions = configuredProjectConversations(projectId);
        let baseSessions = mergeConversationSessions(localSessions, serverSessions);
        PCONV.projectRuns = [];
        PCONV.runsBySession = Object.create(null);
        for (const s of baseSessions) {
          const latestRunSummary = getSessionLatestRunSummary(s);
          const preferSyntheticPreviewSender = sessionUsesSyntheticPreviewSender(s, getSessionPrimaryPreviewText(s));
          s.lastActiveAt = String(s.lastActiveAt || latestRunSummary.updated_at || s.last_used_at || "");
          s.lastStatus = getSessionStatus(s);
          s.lastError = String(s.lastError || latestRunSummary.error || "");
          s.lastErrorHint = String(s.lastErrorHint || "");
          s.lastSpeaker = String(s.lastSpeaker || (preferSyntheticPreviewSender ? "assistant" : (latestRunSummary.speaker || "assistant")) || "assistant");
          s.lastPreview = String(getSessionPrimaryPreviewText(s) || s.lastPreview || latestRunSummary.preview || "");
          s.lastSenderType = String(s.lastSenderType || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_type || "legacy")));
          s.lastSenderName = String(s.lastSenderName || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_name || "")));
          s.lastSenderSource = String(s.lastSenderSource || (preferSyntheticPreviewSender ? "" : (latestRunSummary.sender_source || "legacy")));
          s.latestUserMsg = String(s.latestUserMsg || latestRunSummary.latest_user_msg || "");
          s.latestAiMsg = String(s.latestAiMsg || latestRunSummary.latest_ai_msg || "");
          s.runCount = Math.max(0, Number(s.runCount || latestRunSummary.run_count || 0) || 0);
          // 兼容新旧字段名
          const channelName = s.channel_name || s.primaryChannel;
          if (channelName) {
            s.primaryChannel = String(channelName);
            s.channel_name = String(channelName);
            if (!s.displayChannel) s.displayChannel = channelName;
          }
          if (!s.primaryChannel) s.primaryChannel = (s.channels && s.channels[0]) ? String(s.channels[0]) : "";
          if (!s.displayChannel) s.displayChannel = s.primaryChannel || s.alias || (s.sessionId || s.id);
        }

        seedConversationUnreadCursorsForSessions(projectId, baseSessions);

        PCONV.sessionDirectoryByProject[projectId] = baseSessions.slice();
        markConversationSessionDirectoryMeta(projectId, {
          liveLoaded: true,
          source: "panel",
          loadedAt: new Date().toISOString(),
          error: "",
        });
        const q = String(STATE.q || "").trim().toLowerCase();
        let sessions = baseSessions.slice();
        if (q) {
          sessions = sessions.filter((s) => {
            const hay = [
              s.alias,
              (s.sessionId || s.id),
              (s.channels || []).join(" "),
              s.lastSenderName || "",
              s.lastPreview || "",
            ].join(" ").toLowerCase();
            return hay.includes(q);
          });
        }
        sessions.sort((a, b) => {
          const ta = String(a.lastActiveAt || "");
          const tb = String(b.lastActiveAt || "");
          if (ta !== tb) return tb.localeCompare(ta);
          return String(a.alias || "").localeCompare(String(b.alias || ""), "zh-Hans-CN");
        });
        PCONV.sessions = sessions;
        PCONV.lastRefreshAt = new Date().toLocaleTimeString("zh-CN", { hour12: false });
        if (sessions.length) {
          const selectedSid = String(STATE.selectedSessionId || "");
          const ok = sessions.some((x) => String(x.sessionId || x.id || "") === selectedSid);
          if (STATE.panelMode === "conv") {
            if (!ok) {
              STATE.selectedSessionId = pickDefaultConversationSessionId(sessions, STATE.channel);
              STATE.selectedSessionExplicit = false;
            } else if (!selectedSid) {
              // 仅在未选中会话时回退默认会话；若已存在选中（含刷新恢复），保持当前选中不被轮询覆盖。
              STATE.selectedSessionId = pickDefaultConversationSessionId(sessions, STATE.channel);
            }
          } else if (!ok && selectedSid) {
            // 任务模式下不自动抢占右侧详情，仅在原会话已失效时清掉失效选中。
            STATE.selectedSessionId = "";
            STATE.selectedSessionExplicit = false;
          }
        } else {
          STATE.selectedSessionId = "";
          STATE.selectedSessionExplicit = false;
        }

        const deferConvRender = STATE.panelMode === "conv" && isConversationListScrollActive();
        if (STATE.panelMode === "conv") {
          if (deferConvRender) {
            queueDeferredConversationRender({
              panelRender: true,
              projectId,
              sessionId: String(STATE.selectedSessionId || "").trim(),
            });
          } else {
            buildConversationLeftList();
            buildConversationMainList(document.getElementById("fileList"));
            // 由 refreshConversationTimeline 统一驱动右侧重绘，避免轮询周期内重复全量重绘导致抖动。
            if (!STATE.selectedSessionId) renderConversationDetail(true);
          }
        } else {
          buildChannelConversationList();
          // 任务模式下如果正在查看会话详情，需要刷新右侧消息区域。
          if (STATE.selectedSessionId) renderDetail(selectedItem());
        }
        if (STATE.selectedSessionId) {
          if (deferConvRender) {
            queueDeferredConversationRender({
              panelRender: true,
              projectId,
              sessionId: String(STATE.selectedSessionId || "").trim(),
              forceScroll: false,
            });
          } else {
            refreshConversationTimeline(projectId, STATE.selectedSessionId, !STATE.selectedSessionId);
          }
        }

        const hasRuntimeWorking = baseSessions.some((s) => {
          const st = String(getSessionStatus(s) || "").trim().toLowerCase();
          return st === "running" || st === "queued" || st === "retry_waiting" || st === "external_busy";
        });
        const selectedSessionId = String(STATE.selectedSessionId || "").trim();
        const selectedSession = selectedSessionId
          ? baseSessions.find((s) => String((s && (s.sessionId || s.id)) || "").trim() === selectedSessionId)
          : null;
        const selectedRuntimeState = getSessionRuntimeState(selectedSession);
        const selectedSessionHasRuntimeWork = !!(
          selectedRuntimeState
          && (
            String(selectedRuntimeState.active_run_id || "").trim()
            || String(selectedRuntimeState.queued_run_id || "").trim()
          )
        );
        const nextPollMs = selectedSessionHasRuntimeWork ? 1200 : conversationPollDelay(hasRuntimeWorking);
        scheduleConversationPoll(nextPollMs);
      } catch (err) {
        console.error("refreshConversationPanel error:", err);
        if (String(STATE.project || "").trim() && String(STATE.project || "").trim() !== "overview") {
          scheduleConversationPoll(5000);
        } else {
          stopConversationPoll();
        }
      } finally {
        PCONV.busy = false;
      }
    }
