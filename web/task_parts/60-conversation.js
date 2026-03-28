// 第六刀：会话详情壳层与会话 API/缓存桥接
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
        const callbackLike = info.triggerType === "callback_auto"
          || info.triggerType === "callback_auto_summary"
          || info.messageKind === "system_callback"
          || info.messageKind === "system_callback_summary"
          || info.messageKind === "restart_recovery_summary";
        if (info.senderType === "system" || callbackLike) continue;
        let score = 0;
        if (idx < callbackIndex) score += 40;
        else score += 10;
        score -= Math.min(Math.abs(callbackIndex - idx), 30);
        if (relatedRunIds.has(candidateRunId)) score += 160;
        if (sourceChannel && info.sourceChannel && info.sourceChannel === sourceChannel) score += 120;
        if (sourceRunId && candidateRunId === sourceRunId) score += 200;
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

    function renderConversationDetail(forceScroll = false) {
      const titleEl = document.getElementById("detailTitle");
      const subEl = document.getElementById("detailSub");
      const hintEl = document.getElementById("convHint");
      const senderHintEl = document.getElementById("convSenderHint");
      const timeline = document.getElementById("convTimeline");
      const input = document.getElementById("convMsg");
      const sendBtn = document.getElementById("convSendBtn");
      const memoSaveBtn = document.getElementById("convMemoSaveBtn");
      const pathBar = document.getElementById("detailPathBar");
      const basePlaceholder = conversationComposerPlaceholder("Codex");
      if (pathBar) pathBar.style.display = "none";
      if (!titleEl || !timeline || !input || !sendBtn || !hintEl || !subEl) return;
      bindConvComposerToSelectedSession();

      captureDebugLogScrollPositions(timeline);
      const wasNearBottom = (timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight) < 80;
      const scrollAnchor = {
        scrollTop: Number(timeline.scrollTop || 0),
      };

      timeline.innerHTML = "";
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
        PCONV.fileDrawerOpen = false;
        hideConversationFileEntry();
        renderConversationFileDrawer();
        timeline.appendChild(el("div", { class: "hint", text: "总揽模式不展示会话详情。" }));
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
        PCONV.fileDrawerOpen = false;
        hideConversationFileEntry();
        renderConversationFileDrawer();
        timeline.appendChild(el("div", { class: "hint", text: "无可用会话。" }));
        return;
      }

      const cliChipName = ctx && ctx.cliType ? String(ctx.cliType).toUpperCase() : "Codex";
      const agentDisplay = firstNonEmptyText([ctx.agentName, ctx.alias, ctx.displayChannel]) || "未命名会话";
      const currentSession = findConversationSessionById(String(ctx.sessionId || ""));
      titleEl.innerHTML = "";
      const titleRow = el("div", { class: "detail-title-row" });
      titleRow.appendChild(buildConversationAvatarNode(currentSession || ctx));
      const titleLine = el("div", { class: "detail-title-line" });
      titleLine.appendChild(el("span", { class: "detail-title-text", text: agentDisplay, title: agentDisplay }));
      titleLine.appendChild(buildConversationRoleBadge(currentSession || ctx));
      titleLine.appendChild(buildConversationCliBadge(currentSession || ctx, { detail: true }));
      const detailHeartbeatBadge = buildConversationHeartbeatBadges(currentSession || ctx);
      if (detailHeartbeatBadge) titleLine.appendChild(detailHeartbeatBadge);
      const titleStatus = buildConversationStatusBadge(currentSession || ctx);
      if (titleStatus) titleLine.appendChild(titleStatus);
      const sessionIdText = String(ctx.sessionId || "");
      if (sessionIdText) {
        titleLine.appendChild(el("span", {
          class: "detail-inline-id",
          text: sessionIdText,
          title: sessionIdText,
        }));
      }
      titleRow.appendChild(titleLine);
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

      const timelineKey = String(STATE.project || "") + "::" + String(ctx.sessionId || "");
      if (PCONV.autoExpandTimelineKey !== timelineKey) {
        // 每次进入一个会话：重置展开状态（仅最新消息默认展开）
        PCONV.autoExpandTimelineKey = timelineKey;
        PCONV.autoExpandDone = false;
        PCONV.autoExpandedLatestBubbleKey = "";
        PCONV.bubbleExpanded = new Set();
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
      hintEl.textContent = "";
      hintEl.title = "";
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
      if (
        latestExpandableBubbleKey
        && (
          !PCONV.autoExpandDone
          || PCONV.autoExpandedLatestBubbleKey !== latestExpandableBubbleKey
        )
      ) {
        // 每次进入会话，或同一会话出现新的最后一条可展开消息时，
        // 默认只展开最新一条，其他全部收起。
        PCONV.bubbleExpanded = new Set([latestExpandableBubbleKey]);
        PCONV.autoExpandDone = true;
        PCONV.autoExpandedLatestBubbleKey = latestExpandableBubbleKey;
      }

      if (!runs.length && !(PCONV.optimistic && PCONV.optimistic.sessionId === ctx.sessionId)) {
        timeline.appendChild(el("div", { class: "hint", text: timelineLoading ? "加载会话记录中..." : "该会话暂无消息记录，可直接在下方发送消息。" }));
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
        timeline.appendChild(historyBar);
      }

      const seenCallbackEventKeys = new Set();
      const seenRestartRecoveryKeys = new Set();
      const visibleRunIds = new Set(runs.map((item) => String((item && item.id) || "").trim()).filter(Boolean));
      const runsById = new Map(runs.map((item) => [String((item && item.id) || "").trim(), item]));
      const localReceiptAnchorMaps = buildConversationLocalReceiptAnchorMaps(runs, visibleRunIds, runsById, PCONV.detailMap, ctx);
      const localReceiptProjectionByRunId = (localReceiptAnchorMaps && localReceiptAnchorMaps.anchoredByHostRunId) || Object.create(null);
      const localAnchoredCallbackRunIds = (localReceiptAnchorMaps && localReceiptAnchorMaps.anchoredCallbackRunIds) || new Set();
      const newestRunId = runs.length ? String((runs[0] && runs[0].id) || "") : "";
      const latestRunId = runs.length ? String((runs[runs.length - 1] && runs[runs.length - 1].id) || "") : "";
      let autoTerminalDetailFetches = 0;

      for (const r of runs) {
        const rid = String(r.id || "");
        const isLatestRun = !!(rid && latestRunId && rid === latestRunId);
        const d = PCONV.detailMap[rid] || null;
        const st = getRunDisplayState(r, d);
        const queueReason = getRunQueueReason(r, d);
        const queueReasonText = queueReasonLabel(queueReason);
        const blockedByRunId = getRunBlockedByRunId(r, d);
        const blockedByText = blockedByRunId ? shortId(blockedByRunId) : "";
        const actionBusy = String(PCONV.runActionBusy[rid] || "");
        const stNorm = String(st || "").toLowerCase();
        const timeoutLike = stNorm === "error" && isRunTimeoutLike(r, d);
        // 终态且仅有截断摘要时，自动补一次 full 详情拉取，用于展示完整结论正文。
        if (
          !d
          && !isRunWorking(stNorm)
          && looksTruncatedSummaryText(r && r.lastPreview)
          && rid
          && rid === newestRunId
          && autoTerminalDetailFetches < 1
        ) {
          autoTerminalDetailFetches += 1;
          ensureConversationRunDetail(rid, { maxAgeMs: 2000, terminalSyncStatus: stNorm });
        }
        const detailRunDisplay = normalizeDisplayState(firstNonEmptyText([
          d && d.full && d.full.run && d.full.run.display_state,
        ]), "idle");
        const detailRunStatus = normalizeDisplayState(firstNonEmptyText([
          d && d.full && d.full.run && d.full.run.status,
        ]), "");
        const effectiveDetailRunStatus = (detailRunStatus === "done" || detailRunStatus === "error")
          ? detailRunStatus
          : normalizeDisplayState(detailRunDisplay || detailRunStatus, "idle");
        // run 进入终态后，若缓存 detail 仍停留在运行态/旧态，触发一次轻量同步，避免正文与调试区滞后。
        if (d && !d.loading && !isRunWorking(stNorm)) {
          const lastTerminalSyncAt = Number(d.terminalSyncAt || 0);
          const allowTerminalSync = !lastTerminalSyncAt || (Date.now() - lastTerminalSyncAt) > 3000;
          const detailLagging = !effectiveDetailRunStatus || effectiveDetailRunStatus !== stNorm;
          if (detailLagging && allowTerminalSync) {
            ensureConversationRunDetail(rid, { force: true, terminalSyncStatus: stNorm });
          }
        }
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
        const projectedHostReceiptProjection = projectedReceiptHostRunId
          ? readConversationReceiptProjection(projectedHostRun, projectedHostDetail)
          : null;
        const callbackProjectedToVisibleHost = !!(
          callbackEventMeta
          && projectedReceiptHostRunId
          && projectedReceiptHostRunId !== rid
          && visibleRunIds.has(projectedReceiptHostRunId)
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
          timeline.appendChild(systemRow);
          continue;
        }

        const userRow = renderConversationUserFamily({
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
          attachments,
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
        });
        timeline.appendChild(userRow);
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
          callbackEventMeta,
          restartRecoveryMeta,
          queueReasonText,
          blockedByText,
          receiptProjection,
          mentionTargets,
        });
        timeline.appendChild(aiRow);
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
          receiptProjection: null,
          mentionTargets: [],
        });
        shadowAiRow.classList.add("runtime-shadow");
        timeline.appendChild(shadowAiRow);
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
        timeline.appendChild(shadowUserRow);
      }

      if (PCONV.optimistic && PCONV.optimistic.sessionId === ctx.sessionId) {
        const m = PCONV.optimistic;
        const userRow = renderConversationOptimisticUserFamily({
          ctx,
          message: m,
        });
        timeline.appendChild(userRow);
      }

      const receiptViewer = renderConversationReceiptViewer();
      if (receiptViewer) timeline.appendChild(receiptViewer);

      refreshConversationFilesFromTimeline(ctx, timeline);
      renderConversationFileUi();

      if (forceScroll || wasNearBottom) {
        maybeStickConversationBottom(true);
      } else {
        restoreConversationTimelineScroll(timeline, scrollAnchor);
        requestAnimationFrame(() => restoreConversationTimelineScroll(timeline, scrollAnchor));
      }
    }

    async function refreshConversationTimeline(projectId, sessionId, forceScroll = false) {
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
          s.lastActiveAt = String(s.lastActiveAt || latestRunSummary.updated_at || s.last_used_at || "");
          s.lastStatus = getSessionStatus(s);
          s.lastError = String(s.lastError || latestRunSummary.error || "");
          s.lastPreview = String(s.lastPreview || latestRunSummary.preview || "");
          s.lastSpeaker = String(s.lastSpeaker || latestRunSummary.speaker || "assistant");
          s.lastSenderType = String(s.lastSenderType || latestRunSummary.sender_type || "legacy");
          s.lastSenderName = String(s.lastSenderName || latestRunSummary.sender_name || "");
          s.lastSenderSource = String(s.lastSenderSource || latestRunSummary.sender_source || "legacy");
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
        hydrateConversationGlobalMentionDirectory(pid);
      } catch (e) {
        console.error("loadProjectConversations error:", e);
      }
    }

    async function refreshConversationPanel() {
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
          s.lastActiveAt = String(s.lastActiveAt || latestRunSummary.updated_at || s.last_used_at || "");
          s.lastStatus = getSessionStatus(s);
          s.lastError = String(s.lastError || latestRunSummary.error || "");
          s.lastErrorHint = String(s.lastErrorHint || "");
          s.lastSpeaker = String(s.lastSpeaker || latestRunSummary.speaker || "assistant");
          s.lastPreview = String(s.lastPreview || latestRunSummary.preview || "");
          s.lastSenderType = String(s.lastSenderType || latestRunSummary.sender_type || "legacy");
          s.lastSenderName = String(s.lastSenderName || latestRunSummary.sender_name || "");
          s.lastSenderSource = String(s.lastSenderSource || latestRunSummary.sender_source || "legacy");
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
        hydrateConversationGlobalMentionDirectory(projectId);

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
