/* 第七刀：会话时间线与消息气泡渲染 */
    // assistant-body-prefetch-disabled
    // auto-process-drawer-uses-light-payload
    function resolveConversationAssistantBodyMeta(payload = {}) {
      const src = (payload && typeof payload === "object") ? payload : {};
      const status = String(src.status || "").trim().toLowerCase();
      const displayAssistantText = String(src.displayAssistantText || "").trim();
      const attachments = Array.isArray(src.attachments) ? src.attachments : [];
      const processInfo = (src.processInfo && typeof src.processInfo === "object") ? src.processInfo : {};
      const latestProgress = String(processInfo.latest || "").trim();
      const processCount = Math.max(0, Number(processInfo.count || 0) || 0);
      const reportedCount = Math.max(0, Number(processInfo.reportedCount || 0) || 0);
      if (isRunWorking(status)) {
        if (latestProgress) {
          return {
            bodyTitle: "最新进展",
            inlineText: latestProgress,
            showBody: true,
            placeholder: "",
            needsDetailPrefetch: false,
          };
        }
        return {
          bodyTitle: "最新进展",
          inlineText: "",
          showBody: false,
          placeholder: "",
          needsDetailPrefetch: reportedCount > processCount && !src.detailLoading,
        };
      }
      if (displayAssistantText) {
        return {
          bodyTitle: "正文",
          inlineText: displayAssistantText,
          showBody: true,
          placeholder: "",
          needsDetailPrefetch: false,
        };
      }
      return {
        bodyTitle: "正文",
        inlineText: "",
        showBody: true,
        placeholder: (status === "done" && attachments.length > 0)
          ? "本轮执行已完成，结果见下方附件。"
          : "未生成可展示正文",
        needsDetailPrefetch: false,
      };
    }

    function conversationReceiptProjectionPendingCount(projection) {
      const src = (projection && typeof projection === "object") ? projection : {};
      const pendingActions = Array.isArray(src.pendingActions) ? src.pendingActions : [];
      const rollup = (src.rollup && typeof src.rollup === "object") ? src.rollup : {};
      return Math.max(pendingActions.length, Number(rollup.pendingActionCount || 0) || 0);
    }

    function resolveConversationReceiptProjectionPresentation(payload = {}) {
      const src = (payload && typeof payload === "object") ? payload : {};
      const projection = (src.projection && typeof src.projection === "object") ? src.projection : null;
      const hasProjection = !!projection;
      const pendingCount = hasProjection ? conversationReceiptProjectionPendingCount(projection) : 0;
      const totalCount = hasProjection
        ? Math.max(
          Array.isArray(projection.items) ? projection.items.length : 0,
          Number(((projection.rollup || {}).totalCallbacks) || 0) || 0
        )
        : 0;
      return {
        hasProjection,
        pendingCount,
        totalCount,
        sourceCompact: !!(hasProjection && !src.receiptCardVisible && !src.callbackEventMeta && !src.restartRecoveryMeta),
        assistantStack: false,
      };
    }

    function renderConversationReplyQuote(replyContext) {
      const ctx = normalizeConvReplyContext(replyContext);
      if (!ctx) return null;
      const root = el("div", { class: "convreply-quote" });
      const head = el("div", { class: "convreply-quote-head" });
      head.appendChild(el("span", {
        class: "convreply-quote-lead",
        text: "↩ 回复 " + String(ctx.senderLabel || "我"),
      }));
      if (ctx.timeLabel) {
        head.appendChild(el("span", {
          class: "convreply-quote-time",
          text: String(ctx.timeLabel),
          title: ctx.createdAt ? zhDateTime(ctx.createdAt) : "",
        }));
      }
      const preview = el("div", {
        class: "convreply-quote-preview",
        text: String(ctx.preview || "(空内容)"),
      });
      root.appendChild(head);
      root.appendChild(preview);
      return root;
    }

    function extractConversationChannelFromRefText(text) {
      const src = String(text || "").trim();
      if (!src) return "";
      const matched = src.match(/(?:^|·)\s*channel=([^·\n]+)/i);
      return matched ? String(matched[1] || "").trim() : "";
    }

    function readConversationInboundSummary(text) {
      const src = String(text || "").trim();
      if (!src) {
        return {
          sourceChannel: "",
          currentConclusion: "",
          nextAction: "",
          systemHandled: "",
          expectedResult: "",
          receiptTask: "",
          stage: "",
          needConfirm: "无",
          structuredFieldCount: 0,
        };
      }
      const kv = parseCallbackMessageKv(src);
      const read = (aliases) => firstNonEmptyText([pickCallbackKvValue(kv, aliases)]);
      const currentConclusion = read(["当前结论", "执行结论", "结论"]);
      const nextAction = read(["需要对方", "建议动作", "下一步", "预期结果", "目标进展"]);
      const systemHandled = read(["系统已处理", "已完成事项", "执行结果"]);
      const expectedResult = read(["预期结果", "结果预期", "目标进展"]);
      const receiptTask = read(["回执任务", "任务", "关联任务"]);
      const stage = normalizeCallbackStage(read(["执行阶段", "阶段"]), "");
      const needConfirm = read(["需确认", "需总控确认", "需要确认"]) || "无";
      const structuredFieldCount = [
        currentConclusion,
        read(["是否通过或放行", "是否通过"]),
        read(["唯一阻塞"]),
        read(["关键路径或 run_id", "关键路径", "run_id"]),
        read(["下一步动作", "下一步", "需要对方"]),
      ].filter((x) => String(x || "").trim()).length;
      return {
        sourceChannel: firstNonEmptyText([
          read(["来源通道", "source channel", "来源channel"]),
          extractSourceChannelName(src),
        ]),
        currentConclusion,
        nextAction,
        systemHandled,
        expectedResult,
        receiptTask,
        stage,
        needConfirm,
        structuredFieldCount,
      };
    }

    function normalizeConversationDisplayMode(raw) {
      const mode = String(raw || "").trim().toLowerCase();
      if (mode === "receipt" || mode === "action" || mode === "plain") return mode;
      return "";
    }

    function conversationLooksTerminalReceiptText(text) {
      const src = String(text || "").trim();
      if (!src) return false;
      return /(?:\bdone\b|已完成|已接收|已消费|已同步|已确认|通过|放行|收口|可进入验收(?:\/收口)?|进入验收(?:\/收口)?|按.*收口处理|按通过处理|不再作为活动阻塞|可按.*收口处理)/i.test(src);
    }

    function conversationNeedsPeerAction(text) {
      const src = String(text || "").trim();
      if (!src || src === "无") return false;
      if (/(?:无需|无须|只保留观察|仅保留观察|后续只保留观察|不再作为活动阻塞|进入验收(?:\/收口)?|可进入验收(?:\/收口)?|按.*收口处理|按通过处理|待观察|待样本补送后再校验)/i.test(src)) {
        return false;
      }
      return /(?:请继续|请处理|请确认|请回复|请执行|请排查|请补充|请联调|请核验|请跟进|继续推进|继续处理|继续执行|需要对方|需要你|需要当前|需确认|需处理|需回复|需执行|待确认|待处理|待回复|待执行|待联调|回执请包含)/i.test(src);
    }

    function conversationLooksDirectAgentReplyText(text) {
      const src = String(text || "").trim();
      if (!src) return false;
      if (src.includes("```")) return true;
      const lines = src.split(/\r?\n/).map((line) => String(line || "").trim()).filter(Boolean);
      if (!lines.length) return false;
      const structuredLabelRe = /^(?:\[.+\]|[【（(].+[】)）]|(?:当前结论|是否通过或放行|是否通过|唯一阻塞|关键路径或 run_id|关键路径|run_id|下一步动作|来源通道|回执任务|执行阶段|本次目标|当前进展|目标进展|系统已处理|需要对方|预期结果|需确认|说明|补充|改动文件|验证|回归结果|技术明细|边界|业务要求|文件维度))\s*[:：]/;
      const bulletCount = lines.filter((line) => /^(?:[-*]|\d+\.)\s+/.test(line)).length;
      const paragraphCount = lines.filter((line) => !structuredLabelRe.test(line) && !/^(?:[-*]|\d+\.)\s+/.test(line) && line.length >= 18).length;
      const structuredCount = lines.filter((line) => structuredLabelRe.test(line)).length;
      if (bulletCount >= 2) return true;
      if (paragraphCount >= 2) return true;
      if (paragraphCount >= 1 && structuredCount >= 2) return true;
      return false;
    }

    function resolveConversationSourceText(payload = {}) {
      return firstNonEmptyText([
        payload.sourceText,
        payload.userText,
        payload.displayUserText,
        payload.messagePreview,
        payload.rawText,
      ]);
    }

    function resolveConversationDisplayMode(payload = {}) {
      const senderRun = (payload.senderRun && typeof payload.senderRun === "object") ? payload.senderRun : {};
      const runSpec = (payload.runSpec && typeof payload.runSpec === "object") ? payload.runSpec : {};
      const userSender = payload.userSender || null;
      const userMessageKind = String(payload.userMessageKind || "").trim().toLowerCase();
      const sourceText = resolveConversationSourceText(payload);
      const summary = (payload.summary && typeof payload.summary === "object") ? payload.summary : readConversationInboundSummary(sourceText);
      const senderType = String((userSender && userSender.type) || "").trim().toLowerCase();
      const sourceRef = senderRun.source_ref || senderRun.sourceRef || null;
      const callbackTo = senderRun.callback_to || senderRun.callbackTo || null;
      const explicitMode = normalizeConversationDisplayMode(
        firstNonEmptyText([
          senderRun.display_mode,
          senderRun.displayMode,
          (senderRun.communication_view && senderRun.communication_view.display_mode) || "",
          (senderRun.communicationView && senderRun.communicationView.displayMode) || "",
        ])
      );
      const sourceChannel = firstNonEmptyText([
        summary.sourceChannel,
        firstNonEmptyText([sourceRef && (sourceRef.channel_name || sourceRef.channelName)]),
        extractConversationChannelFromRefText(runSpec.sourceRefText),
      ]);
      const hasRoutingHint = !!(
        sourceRef
        || callbackTo
        || String(runSpec.interactionMode || "").trim().toLowerCase() === "task_with_receipt"
        || runSpec.sourceRefText
        || runSpec.callbackToText
      );
      const pendingActions = []
        .concat(Array.isArray(senderRun.receipt_pending_actions) ? senderRun.receipt_pending_actions : [])
        .concat(Array.isArray(senderRun.receiptPendingActions) ? senderRun.receiptPendingActions : []);
      const hasPendingActions = pendingActions.length > 0;
      const isCollabInbound = !!(
        senderType === "agent"
        || userMessageKind === "collab_update"
        || userMessageKind === "agent_output"
        || (userMessageKind === "manual_update" && (sourceChannel || hasRoutingHint))
        || (senderType !== "user" && (sourceChannel || hasRoutingHint))
      );
      const needConfirm = String(summary.needConfirm || "").trim();
      const directReplyLike = conversationLooksDirectAgentReplyText(sourceText);
      const terminalText = [
        summary.currentConclusion,
        summary.systemHandled,
        summary.expectedResult,
        sourceText,
      ].filter(Boolean).join("\n");
      const receiptScore = (
        (isCollabInbound && hasRoutingHint ? 1 : 0)
        + (summary.structuredFieldCount >= 2 ? 1 : 0)
        + (summary.currentConclusion ? 1 : 0)
        + (conversationLooksTerminalReceiptText(terminalText) ? 2 : 0)
        + (!conversationNeedsPeerAction(summary.nextAction) && !hasPendingActions && (!needConfirm || needConfirm === "无") ? 1 : 0)
      );
      const actionScore = (
        (hasPendingActions ? 3 : 0)
        + (needConfirm && needConfirm !== "无" ? 3 : 0)
        + (conversationNeedsPeerAction(summary.nextAction) ? 2 : 0)
        + (!summary.currentConclusion && conversationNeedsPeerAction(sourceText) ? 1 : 0)
      );
      let displayMode = explicitMode || "plain";
      if (!explicitMode) {
        if (
          userMessageKind === "system_callback"
          || userMessageKind === "system_callback_summary"
          || userMessageKind === "restart_recovery_summary"
        ) {
          displayMode = "receipt";
        } else if (isCollabInbound && !directReplyLike && receiptScore >= 4 && actionScore <= 1) {
          displayMode = "receipt";
        } else if (isCollabInbound) {
          displayMode = "action";
        }
      }
      return {
        displayMode,
        isCollabInbound,
        sourceChannel,
        currentConclusion: String(summary.currentConclusion || "").trim(),
        nextAction: String(summary.nextAction || "").trim(),
        systemHandled: String(summary.systemHandled || "").trim(),
        expectedResult: String(summary.expectedResult || "").trim(),
        receiptTask: String(summary.receiptTask || "").trim(),
        stage: String(summary.stage || "").trim(),
        needConfirm: needConfirm || "无",
        directReplyLike,
        senderType,
      };
    }

    function resolveConversationUserVisualMode(payload = {}) {
      const runSpec = (payload.runSpec && typeof payload.runSpec === "object") ? payload.runSpec : {};
      const senderRun = (payload.senderRun && typeof payload.senderRun === "object") ? payload.senderRun : {};
      const userSender = payload.userSender || null;
      const userMessageKind = String(payload.userMessageKind || "").trim().toLowerCase();
      const sourceText = resolveConversationSourceText(payload);
      const summary = readConversationInboundSummary(sourceText);
      const displayMeta = resolveConversationDisplayMode({
        senderRun,
        runSpec,
        userSender,
        userMessageKind,
        sourceText,
        summary,
      });
      const senderType = String((userSender && userSender.type) || "").trim().toLowerCase();
      let kind = "self-user";
      if (displayMeta.isCollabInbound) {
        if (senderType === "agent") kind = "agent-inbound";
        else if (displayMeta.displayMode === "receipt") kind = "receipt-inbound";
        else kind = "collab-inbound";
      }
      return {
        kind,
        displayMode: displayMeta.displayMode,
        sourceChannel: displayMeta.sourceChannel,
        currentConclusion: displayMeta.currentConclusion,
        nextAction: displayMeta.nextAction,
        systemHandled: displayMeta.systemHandled,
        expectedResult: displayMeta.expectedResult,
        receiptTask: displayMeta.receiptTask,
        stage: displayMeta.stage,
        needConfirm: displayMeta.needConfirm,
        directReplyLike: !!displayMeta.directReplyLike,
        senderType,
      };
    }

    function ensureConversationInlineSnippetExpandedSet() {
      if (!(PCONV.inlineSnippetExpanded instanceof Set)) {
        PCONV.inlineSnippetExpanded = new Set();
      }
      return PCONV.inlineSnippetExpanded;
    }

    function toggleConversationInlineSnippet(expandKey, opts = {}) {
      const key = String(expandKey || "").trim();
      if (!key) return;
      const expandedSet = ensureConversationInlineSnippetExpandedSet();
      if (expandedSet.has(key)) expandedSet.delete(key);
      else {
        expandedSet.add(key);
        const runId = String(opts.runId || "").trim();
        if (runId && opts.needsDetail) ensureConversationRunDetail(runId);
      }
      renderConversationDetail(false);
    }

    function buildConversationInlinePreviewText(rawText, title = "") {
      let src = String(rawText || "").replace(/\r\n?/g, "\n").trim();
      if (!src) return "";
      const titleText = String(title || "").trim();
      if (titleText) {
        const escaped = titleText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        src = src.replace(new RegExp("^当前结论\\s*[:：]\\s*" + escaped + "\\s*(?:\\n+|$)", "i"), "");
      }
      const lines = src
        .split("\n")
        .map((line) => String(line || "").trim())
        .filter(Boolean)
        .slice(0, 6);
      return (lines.join(" ") || src).trim();
    }

    function renderConversationInlineSnippet(rawText, opts = {}) {
      const fullText = String(rawText || "").trim();
      const title = String(opts.title || "").trim();
      const previewText = String(firstNonEmptyText([
        opts.previewText,
        buildConversationInlinePreviewText(fullText, title),
      ]) || "").trim();
      const resolvedText = fullText || previewText;
      if (!resolvedText) return null;
      const runId = String(opts.runId || "").trim();
      const expandKey = String(opts.expandKey || (runId ? (runId + ":inline-snippet") : "")).trim();
      const expanded = !!(expandKey && ensureConversationInlineSnippetExpandedSet().has(expandKey));
      const complete = opts.complete !== false;
      const needsDetail = !!(runId && !complete);
      const shouldToggle = needsDetail || resolvedText.length > previewText.length || resolvedText.indexOf("\n") >= 0 || resolvedText.length > 120;
      if (expanded && needsDetail) ensureConversationRunDetail(runId);

      const box = el("div", {
        class: "conv-inline-snippet" + (expanded ? " expanded" : " collapsed") + (complete ? "" : " pending"),
      });
      const body = el("div", {
        class: "conv-inline-snippet-body" + (expanded ? " expanded" : " preview collapsed") + (complete ? "" : " pending"),
      });
      if (expanded && complete) {
        body.classList.add("md");
        setMarkdown(body, resolvedText, resolvedText);
        enhanceMessageInteractiveObjects(body);
      } else {
        body.textContent = previewText || resolvedText;
      }
      if (!expanded && shouldToggle) {
        const inlineBtn = el("button", {
          class: "btn textbtn bubble-expand-inline",
          type: "button",
          text: String(opts.summaryText || "展开全文"),
        });
        inlineBtn.addEventListener("click", () => {
          toggleConversationInlineSnippet(expandKey, {
            runId,
            needsDetail,
          });
        });
        body.appendChild(inlineBtn);
      }
      box.appendChild(body);

      if (expanded && shouldToggle && expandKey) {
        const foldRow = el("div", { class: "bubble-expand-row user" });
        if (!complete) {
          foldRow.appendChild(el("span", {
            class: "conv-inline-snippet-hint",
            text: "原文加载中...",
          }));
        }
        const btn = el("button", {
          class: "btn textbtn bubble-expand-toggle",
          type: "button",
          text: "收起全文",
        });
        btn.addEventListener("click", () => {
          toggleConversationInlineSnippet(expandKey, {
            runId,
            needsDetail,
          });
        });
        foldRow.appendChild(btn);
        box.appendChild(foldRow);
      }
      return box;
    }

    function resolveConversationInboundCardTitle(summary, rawText, fallback = "Agent 消息") {
      const s = (summary && typeof summary === "object") ? summary : {};
      const rawSummary = readConversationInboundSummary(rawText);
      const raw = String(rawText || "").replace(/\r\n?/g, "\n");
      const firstLine = raw
        .split("\n")
        .map((line) => String(line || "").trim())
        .find(Boolean) || "";
      const normalizedFirstLine = firstLine.replace(/^(?:当前结论|结论|标题|主题)\s*[:：]\s*/i, "").trim();
      return firstNonEmptyText([
        s.currentConclusion,
        rawSummary.currentConclusion,
        s.receiptTask,
        rawSummary.receiptTask,
        normalizedFirstLine,
        fallback,
      ]) || fallback;
    }

    function renderConversationInboundAgentCard(summary, opts = {}) {
      const s = (summary && typeof summary === "object") ? summary : {};
      const rawText = String(opts.rawText || "").trim();
      const title = resolveConversationInboundCardTitle(s, rawText, "Agent 消息");
      const sourceAgentName = String(firstNonEmptyText([opts.sourceAgentName]) || "").trim();
      const sourceChannel = String(firstNonEmptyText([opts.sourceChannel, s.sourceChannel]) || "").trim();
      const root = el("div", { class: "msg-inbound-card" });
      const head = el("div", { class: "msg-inbound-card-head" });
      const headMain = el("div", { class: "msg-inbound-card-main" });
      headMain.appendChild(el("div", { class: "msg-inbound-card-title", text: title }));
      const metaBits = [sourceAgentName, sourceChannel].filter((part, idx, arr) => String(part || "").trim() && arr.indexOf(part) === idx);
      if (metaBits.length) {
        headMain.appendChild(el("div", {
          class: "msg-inbound-card-meta",
          text: metaBits.join(" · "),
        }));
      }
      head.appendChild(headMain);
      if (s.needConfirm && s.needConfirm !== "无") head.appendChild(chip("需确认", "warn"));
      else if (s.stage) head.appendChild(chip(String(s.stage), "muted"));
      root.appendChild(head);

      const brief = firstNonEmptyText([
        s.nextAction,
        s.expectedResult,
        s.systemHandled,
      ]);
      if (brief && brief !== title) {
        root.appendChild(el("div", {
          class: "msg-inbound-card-brief",
          text: brief,
        }));
      }

      const raw = renderConversationInlineSnippet(rawText, {
        runId: opts.runId,
        complete: !!opts.rawTextComplete,
        title,
        summaryText: "展开全文",
        expandKey: String(opts.expandKey || (String(opts.runId || "").trim() + ":agent-inline")).trim(),
      });
      if (raw) root.appendChild(raw);

      if (typeof opts.onReply === "function" && rawText) {
        const ops = el("div", { class: "bubbleops user msg-inbound-card-ops" });
        const replyBtn = el("button", { class: "btn textbtn", type: "button", text: "回复" });
        replyBtn.addEventListener("click", () => {
          try { opts.onReply({ text: rawText }); } catch (_) {}
        });
        ops.appendChild(replyBtn);
        root.appendChild(ops);
      }
      return root;
    }

    function renderConversationInboundReceiptCard(summary, opts = {}) {
      const s = (summary && typeof summary === "object") ? summary : {};
      const rawSummary = readConversationInboundSummary(opts.rawText || "");
      const sourceAgentName = String(firstNonEmptyText([opts.sourceAgentName, s.sourceAgentName]) || "").trim();
      const sourceChannel = String(firstNonEmptyText([opts.sourceChannel, s.sourceChannel]) || "").trim();
      const root = el("div", { class: "callback-event collab-receipt compact-receipt" });
      const leadText = firstNonEmptyText([s.currentConclusion, rawSummary.currentConclusion, "已回执"]);
      const briefText = firstNonEmptyText([
        s.systemHandled,
        s.expectedResult,
        "当前 Agent 无需继续处理",
      ]);
      root.appendChild(el("div", { class: "callback-event-lead", text: leadText }));
      const metaBits = [sourceAgentName, sourceChannel].filter((part, idx, arr) => {
        const text = String(part || "").trim();
        return !!text && arr.findIndex((x) => String(x || "").trim() === text) === idx;
      });
      if (metaBits.length) {
        root.appendChild(el("div", { class: "callback-event-brief compact-meta", text: metaBits.join(" · ") }));
      }
      if (briefText && briefText !== leadText) {
        root.appendChild(el("div", { class: "callback-event-brief", text: briefText }));
      }
      const head = el("div", { class: "callback-event-head" });
      head.appendChild(chip("回执收纳", "muted"));
      if (s.stage) head.appendChild(chip(String(s.stage), "muted"));
      if (s.needConfirm && s.needConfirm !== "无") head.appendChild(chip("需确认", "warn"));
      root.appendChild(head);
      const grid = el("div", { class: "callback-event-grid callback-comm-grid" });
      const addRow = (label, value) => {
        const text = String(value || "").trim();
        if (!text) return;
        const row = el("div", { class: "callback-event-row callback-comm-row" });
        row.appendChild(el("div", { class: "callback-event-k", text: label }));
        row.appendChild(el("div", { class: "callback-event-v", text }));
        grid.appendChild(row);
      };
      if (sourceAgentName && sourceAgentName !== sourceChannel) addRow("来源Agent", sourceAgentName);
      addRow("来源通道", sourceChannel);
      addRow("回执任务", s.receiptTask);
      if (grid.childNodes.length) root.appendChild(grid);
      const rawText = String(opts.rawText || "").trim();
      const raw = renderConversationInlineSnippet(rawText, {
        runId: opts.runId,
        complete: !!opts.rawTextComplete,
        title: leadText,
        summaryText: "展开全文",
        expandKey: String(opts.expandKey || (String(opts.runId || "").trim() + ":receipt-inline")).trim(),
      });
      if (raw) root.appendChild(raw);
      if (typeof opts.onReply === "function" && rawText) {
        const ops = el("div", { class: "bubbleops system callback-event-ops" });
        const replyBtn = el("button", { class: "btn textbtn", type: "button", text: "回复" });
        replyBtn.addEventListener("click", () => {
          try { opts.onReply({ text: rawText }); } catch (_) {}
        });
        ops.appendChild(replyBtn);
        root.appendChild(ops);
      }
      return root;
    }

    function renderCallbackEventCard(meta, opts = {}) {
      const m = (meta && typeof meta === "object") ? meta : {};
      const duplicate = !!opts.duplicate;
      const rawText = String(opts.rawText || "");
      const root = el("div", { class: "callback-event " + normalizeCallbackEventType(m.eventType || "") + (duplicate ? " duplicate" : "") });
      const comm = (m.comm && typeof m.comm === "object") ? m.comm : {};
      const leadText = firstNonEmptyText([
        comm.currentConclusion,
        callbackEventLabel(m.eventType),
      ]);
      const assistText = firstNonEmptyText([
        comm.needPeer,
        comm.expectedResult,
      ]);

      if (leadText) root.appendChild(el("div", { class: "callback-event-lead", text: leadText }));
      if (assistText) root.appendChild(el("div", { class: "callback-event-brief", text: assistText }));

      const head = el("div", { class: "callback-event-head" });
      head.appendChild(chip("系统主动回执", "muted"));
      if (!leadText || leadText !== callbackEventLabel(m.eventType)) {
        head.appendChild(chip(callbackEventLabel(m.eventType), callbackEventTone(m.eventType)));
      }
      const stageText = firstNonEmptyText([m.comm && m.comm.stage]);
      if (stageText && stageText !== comm.currentConclusion) head.appendChild(chip(stageText, "muted"));
      if (m.isSummary) {
        head.appendChild(chip("汇总" + (m.summaryCount > 0 ? (" " + m.summaryCount + " 条") : ""), "warn"));
      }
      if (Number(m.aggregateCount || 0) > 1) {
        const mergedChip = chip("已并入 " + String(m.aggregateCount) + " 条", "warn");
        if (m.callbackLastMergedAt) {
          mergedChip.title = "最近并入: " + zhDateTime(m.callbackLastMergedAt);
        }
        head.appendChild(mergedChip);
      }
      if (duplicate) {
        head.appendChild(chip("重复事件（前端折叠）", "muted"));
      }
      root.appendChild(head);

      const replyQuote = renderConversationReplyQuote(opts.replyContext);
      if (replyQuote) root.appendChild(replyQuote);

      if (duplicate) {
        root.appendChild(el("div", {
          class: "callback-event-note",
          text: "同幂等键事件已展示过，当前仅保留该条记录与原文，避免重复摘要刷屏。",
        }));
        const raw = renderCallbackRawDetails(rawText);
        if (raw) root.appendChild(raw);
        return root;
      }

      const commGrid = el("div", { class: "callback-event-grid callback-comm-grid" });
      const addComm = (label, value, opts = {}) => {
        const fallbackDash = !!opts.fallbackDash;
        const force = !!opts.force;
        const v0 = String(value || "").trim();
        const v = v0 || (fallbackDash ? "-" : "");
        if (!v && !force) return;
        const row = el("div", { class: "callback-event-row callback-comm-row" + (opts.warn ? " warn" : "") });
        row.appendChild(el("div", { class: "callback-event-k", text: label }));
        row.appendChild(el("div", { class: "callback-event-v", text: v }));
        commGrid.appendChild(row);
      };
      addComm("来源通道", comm.sourceChannel, { fallbackDash: true, force: true });
      addComm("回执任务", comm.receiptTask, { fallbackDash: true, force: true });
      addComm("执行阶段", comm.stage, { fallbackDash: true, force: true });
      addComm("当前结论", comm.currentConclusion, { fallbackDash: true, force: true });
      addComm("目标进展", comm.goalProgress, { fallbackDash: true, force: true });
      addComm("系统已处理", comm.systemHandled);
      addComm("需要对方", comm.needPeer, { fallbackDash: true, force: true });
      addComm("预期结果", comm.expectedResult);
      addComm("需确认", comm.needConfirm || "无", { fallbackDash: true, force: true, warn: !!(String(comm.needConfirm || "").trim() && String(comm.needConfirm || "").trim() !== "无") });
      root.appendChild(commGrid);

      const tech = el("details", { class: "callback-tech" });
      tech.appendChild(el("summary", { text: "技术明细" }));
      const grid = el("div", { class: "callback-event-grid callback-tech-grid" });
      const addTech = (label, value, extraClass = "") => {
        const v = String(value || "").trim();
        if (!v) return;
        const row = el("div", { class: "callback-event-row" + (extraClass ? (" " + extraClass) : "") });
        row.appendChild(el("div", { class: "callback-event-k", text: label }));
        row.appendChild(el("div", { class: "callback-event-v", text: v }));
        grid.appendChild(row);
      };
      addTech("触发类型", firstNonEmptyText([m.triggerType]));
      addTech("事件类型", normalizeCallbackEventType(m.eventType));

      if (m.isSummary) {
        addTech("汇总说明", "该条为短窗汇总回执，逐条明细仍以来源 run 与反馈文件轨为准。");
        if (m.summaryCount > 0) addTech("汇总数量", String(m.summaryCount) + " 条");
        if (m.summaryRunIds && m.summaryRunIds.length) {
          const preview = m.summaryRunIds.slice(0, 6).join(", ") + (m.summaryRunIds.length > 6 ? " ..." : "");
          addTech("来源run列表", preview);
        }
      } else {
        addTech("来源run", firstNonEmptyText([m.sourceRunId, "-"]));
      }
      if (Number(m.aggregateCount || 0) > 1) {
        addTech("并入数量", String(m.aggregateCount) + " 条");
      }
      if (m.callbackLastMergedAt) addTech("最近并入", zhDateTime(m.callbackLastMergedAt));
      if (m.callbackMergeMode) addTech("并入模式", m.callbackMergeMode);
      if (m.callbackAnchorAction) addTech("锚点动作", m.callbackAnchorAction);

      addTech("路由结果", callbackEventRouteSummary(m));
      const rr = (m.routeResolution && typeof m.routeResolution === "object") ? m.routeResolution : {};
      if (rr.fallbackStage && rr.fallbackStage !== "none") addTech("回退阶段", rr.fallbackStage);
      if (rr.degradeReason && rr.degradeReason !== "none") addTech("降级原因", rr.degradeReason, "warn");
      else addTech("降级原因", "none");
      if (m.eventType === "interrupted" && m.eventReason) {
        addTech("中断原因", callbackEventReasonLabel(m.eventReason));
      }

      if (m.feedbackFilePath) {
        addTech("反馈文件", m.feedbackFilePath, "path");
      } else {
        const miss = el("div", { class: "callback-event-row warn" });
        miss.appendChild(el("div", { class: "callback-event-k", text: "反馈文件" }));
        miss.appendChild(el("div", {
          class: "callback-event-v callback-event-missing",
          text: "反馈文件待补录（验收仍以反馈目录文件为准）",
        }));
        grid.appendChild(miss);
      }

      tech.appendChild(grid);
      root.appendChild(tech);
      const raw = renderCallbackRawDetails(rawText);
      if (raw) root.appendChild(raw);
      if (typeof opts.onReply === "function" && String(rawText || "").trim()) {
        const ops = el("div", { class: "bubbleops system callback-event-ops" });
        const replyBtn = el("button", { class: "btn textbtn", type: "button", text: "回复" });
        replyBtn.addEventListener("click", () => {
          try {
            opts.onReply({
              text: String(rawText || ""),
            });
          } catch (_) {}
        });
        ops.appendChild(replyBtn);
        root.appendChild(ops);
      }
      return root;
    }

    function renderRestartRecoveryCard(meta, opts = {}) {
      const m = (meta && typeof meta === "object") ? meta : {};
      const duplicate = !!opts.duplicate;
      const rid = String(opts.runId || "").trim();
      const runMeta = (opts.runMeta && typeof opts.runMeta === "object") ? opts.runMeta : (rid ? { id: rid } : {});
      const progressMeta = buildRestartRecoveryProgressMeta(opts.runId, opts.runMeta, opts.detailMeta);
      const root = el("div", { class: "callback-event interrupted restart-recovery" + (duplicate ? " duplicate" : "") });
      root.appendChild(el("div", {
        class: "callback-event-lead",
        text: progressMeta && progressMeta.isWorking ? "恢复处理中" : "已中断待恢复",
      }));
      root.appendChild(el("div", {
        class: "callback-event-brief",
        text: progressMeta && progressMeta.isWorking
          ? "恢复链路已重新启动，当前最新进展如下。"
          : "优先处理本条恢复消息，再按需回收历史中断任务。",
      }));

      const head = el("div", { class: "callback-event-head" });
      head.appendChild(chip("服务重启恢复", "warn"));
      head.appendChild(chip((m.isSummary ? "汇总 " : "") + String(m.recoveryCount || 1) + " 条", "warn"));
      root.appendChild(head);

      const replyQuote = renderConversationReplyQuote(opts.replyContext);
      if (replyQuote) root.appendChild(replyQuote);

      if (duplicate) {
        root.appendChild(el("div", {
          class: "callback-event-note",
          text: "同一恢复批次已展示，当前记录已折叠，避免时间线重复刷屏。",
        }));
        return root;
      }

      if (progressMeta) {
        const live = el("div", { class: "restart-recovery-live" });
        const liveMeta = el("div", { class: "chips restart-recovery-live-meta" });
        liveMeta.appendChild(chip(progressMeta.stateLabel, progressMeta.stateTone));
        if (progressMeta.latestProgressAt) {
          const latestLabel = compactDateTime(progressMeta.latestProgressAt) || shortDateTime(progressMeta.latestProgressAt);
          liveMeta.appendChild(chip("最近进展 " + latestLabel, "muted"));
        }
        if (progressMeta.isWorking && progressMeta.isStale) liveMeta.appendChild(chip("超过5分钟无进展", "bad"));
        else if (progressMeta.isWorking && !progressMeta.latestProgressAt) liveMeta.appendChild(chip("进展待同步", "warn"));
        live.appendChild(liveMeta);

        if (progressMeta.snippet) {
          live.appendChild(el("div", {
            class: "restart-recovery-live-snippet",
            text: progressMeta.snippet,
          }));
        }

        if (progressMeta.rows.length) {
          const list = el("div", { class: "process-list restart-recovery-process-list" });
          progressMeta.rows.forEach((row, idx) => {
            const txt = String((row && row.text) || "").trim();
            if (!txt) return;
            const itemTs = String((row && row.at) || "").trim();
            const rowNode = el("div", { class: "process-item" + (itemTs ? "" : " no-time") });
            rowNode.appendChild(el("span", { class: "process-idx", text: String(idx + 1) }));
            rowNode.appendChild(el("span", { class: "process-txt", text: txt }));
            if (itemTs) {
              rowNode.appendChild(el("span", {
                class: "process-time",
                text: compactDateTime(itemTs),
                title: zhDateTime(itemTs),
              }));
            }
            list.appendChild(rowNode);
          });
          if (list.childNodes.length) live.appendChild(list);
        }
        root.appendChild(live);
      }

      const grid = el("div", { class: "callback-event-grid" });
      const addRow = (label, value, extraClass = "") => {
        if (!String(value || "").trim()) return;
        const row = el("div", { class: "callback-event-row" + (extraClass ? (" " + extraClass) : "") });
        row.appendChild(el("div", { class: "callback-event-k", text: label }));
        row.appendChild(el("div", { class: "callback-event-v", text: value }));
        grid.appendChild(row);
      };
      addRow("恢复批次", firstNonEmptyText([m.batchId, "-"]));
      addRow("影响数量", String(m.recoveryCount || 1) + " 条");
      if (Array.isArray(m.sourceRunIds) && m.sourceRunIds.length) {
        const preview = m.sourceRunIds.slice(0, 6).join(", ") + (m.sourceRunIds.length > 6 ? " ..." : "");
        addRow("来源run", preview, "path");
      }
      addRow("建议动作", "优先处理本条恢复消息，再按需使用“回收结果”收口历史中断任务。");
      root.appendChild(grid);
      const actionBusy = rid ? String((PCONV.runActionBusy && PCONV.runActionBusy[rid]) || "").trim() : "";
      let recoveryActionBtn = null;
      if (progressMeta && progressMeta.state === "running") {
        recoveryActionBtn = el("button", {
          class: "btn textbtn run-action-danger",
          type: "button",
          text: actionBusy === "interrupt" ? "打断中..." : "打断恢复",
        });
        recoveryActionBtn.disabled = !!actionBusy;
        recoveryActionBtn.addEventListener("click", async () => {
          if (recoveryActionBtn.disabled) return;
          recoveryActionBtn.disabled = true;
          try { await interruptRunningRun(runMeta); } finally { recoveryActionBtn.disabled = false; }
        });
      } else if (progressMeta && (progressMeta.state === "retry_waiting" || progressMeta.state === "queued")) {
        recoveryActionBtn = el("button", {
          class: "btn textbtn run-action-danger",
          type: "button",
          text: actionBusy === "cancel_retry" ? "取消中..." : "取消恢复",
        });
        recoveryActionBtn.disabled = !!actionBusy;
        recoveryActionBtn.addEventListener("click", async () => {
          if (recoveryActionBtn.disabled) return;
          recoveryActionBtn.disabled = true;
          try { await cancelRetryWaitingRun(runMeta); } finally { recoveryActionBtn.disabled = false; }
        });
      }
      if (typeof opts.onReply === "function" || recoveryActionBtn) {
        const replyText = firstNonEmptyText([
          String(opts.rawText || "").trim(),
          "请继续处理本条服务恢复后的任务。",
        ]);
        const ops = el("div", { class: "bubbleops system callback-event-ops" });
        if (recoveryActionBtn) ops.appendChild(recoveryActionBtn);
        if (typeof opts.onReply === "function") {
          const replyBtn = el("button", { class: "btn textbtn", type: "button", text: "回复" });
          replyBtn.addEventListener("click", () => {
            try {
              opts.onReply({ text: replyText });
            } catch (_) {}
          });
          ops.appendChild(replyBtn);
        }
        root.appendChild(ops);
      }
      return root;
    }

    function summarizeRestartRecoverySnippet(rawText, maxLen = 140) {
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

    function buildRestartRecoveryProgressMeta(runId, run, detail) {
      const rid = String(runId || "").trim();
      const runMeta = (run && typeof run === "object") ? run : {};
      const detailMeta = detail && typeof detail === "object" ? detail : null;
      const st = String(getRunDisplayState(runMeta, detailMeta) || "").trim().toLowerCase();
      if (!st) return null;
      const processInfo = collectRunProcessInfo(rid, st, runMeta, detailMeta);
      const detailFull = detailMeta && detailMeta.full ? detailMeta.full : null;
      const detailRun = detailFull && detailFull.run && typeof detailFull.run === "object" ? detailFull.run : null;
      const snippet = summarizeRestartRecoverySnippet(firstNonEmptyText([
        processInfo && processInfo.latest,
        detailFull && detailFull.partialMessage,
        detailRun && detailRun.partialPreview,
        runMeta.partialPreview,
        runMeta.lastPreview,
      ]));
      const rows = (Array.isArray(processInfo && processInfo.rows) ? processInfo.rows : [])
        .filter((row) => String((row && row.text) || "").trim())
        .slice(-3);
      const latestProgressAt = String((processInfo && processInfo.latestProgressAt) || "").trim();
      const isWorking = isRunWorking(st) || st === "external_busy";
      if (!isWorking && !snippet && !rows.length && !latestProgressAt) return null;
      let stateLabel = "已恢复";
      let stateTone = "muted";
      if (st === "running") {
        stateLabel = "处理中";
        stateTone = "warn";
      } else if (st === "queued") {
        stateLabel = "排队中";
        stateTone = "warn";
      } else if (st === "retry_waiting") {
        stateLabel = "等待重试";
        stateTone = "warn";
      } else if (st === "external_busy") {
        stateLabel = "外部占用";
        stateTone = "muted";
      } else if (st === "done") {
        stateLabel = "已恢复";
        stateTone = "ok";
      } else if (st === "error" || st === "interrupted") {
        stateLabel = "恢复中断";
        stateTone = "bad";
      }
      return {
        state: st,
        stateLabel,
        stateTone,
        isWorking,
        isStale: isWorking && latestProgressAt ? isProgressStale(latestProgressAt) : false,
        latestProgressAt,
        snippet,
        rows,
      };
    }

    function resolveConversationSourceAgentLabel(raw) {
      const row = (raw && typeof raw === "object") ? raw : {};
      return String(firstNonEmptyText([
        row.source_alias,
        row.sourceAlias,
        row.source_agent_alias,
        row.sourceAgentAlias,
        row.source_agent_name,
        row.sourceAgentName,
        row.sender_name,
        row.senderName,
      ]) || "").trim();
    }

    function normalizeConversationReceiptItem(raw) {
      const row = (raw && typeof raw === "object") ? raw : {};
      const sourceRunId = String(firstNonEmptyText([row.source_run_id, row.sourceRunId]) || "").trim();
      if (!sourceRunId) return null;
      const needConfirm = String(firstNonEmptyText([row.need_confirm, row.needConfirm]) || "").trim() || "无";
      return {
        sourceRunId,
        callbackRunId: String(firstNonEmptyText([row.callback_run_id, row.callbackRunId]) || "").trim(),
        hostRunId: String(firstNonEmptyText([row.host_run_id, row.hostRunId]) || "").trim(),
        hostReason: String(firstNonEmptyText([row.host_reason, row.hostReason]) || "").trim(),
        runtimeStatus: normalizeCallbackEventType(firstNonEmptyText([row.runtime_status, row.runtimeStatus])),
        triggerType: String(firstNonEmptyText([row.trigger_type, row.triggerType]) || "").trim().toLowerCase(),
        eventType: normalizeCallbackEventType(firstNonEmptyText([row.event_type, row.eventType])),
        eventReason: String(firstNonEmptyText([row.event_reason, row.eventReason]) || "").trim().toLowerCase(),
        dispatchStatus: String(firstNonEmptyText([row.dispatch_status, row.dispatchStatus]) || "").trim().toLowerCase(),
        displayHostRunId: String(firstNonEmptyText([row.display_host_run_id, row.displayHostRunId]) || "").trim(),
        sourceChannel: String(firstNonEmptyText([row.source_channel, row.sourceChannel]) || "").trim(),
        sourceAgentName: firstNonEmptyText([
          resolveConversationSourceAgentLabel(row),
          row.agent_name,
          row.agentName,
        ]),
        sourceProjectId: String(firstNonEmptyText([row.source_project_id, row.sourceProjectId]) || "").trim(),
        sourceSessionId: String(firstNonEmptyText([row.source_session_id, row.sourceSessionId]) || "").trim(),
        targetProjectId: String(firstNonEmptyText([row.target_project_id, row.targetProjectId]) || "").trim(),
        targetChannel: String(firstNonEmptyText([row.target_channel, row.targetChannel]) || "").trim(),
        targetSessionId: String(firstNonEmptyText([row.target_session_id, row.targetSessionId]) || "").trim(),
        callbackTask: String(firstNonEmptyText([row.callback_task, row.callbackTask]) || "").trim(),
        executionStage: String(firstNonEmptyText([row.execution_stage, row.executionStage]) || "").trim(),
        currentConclusion: String(firstNonEmptyText([row.current_conclusion, row.currentConclusion]) || "").trim(),
        needPeer: String(firstNonEmptyText([row.need_peer, row.needPeer]) || "").trim(),
        expectedResult: String(firstNonEmptyText([row.expected_result, row.expectedResult]) || "").trim(),
        needConfirm,
        feedbackFilePath: String(firstNonEmptyText([row.feedback_file_path, row.feedbackFilePath]) || "").trim(),
        callbackMergeMode: String(firstNonEmptyText([row.callback_merge_mode, row.callbackMergeMode]) || "").trim().toLowerCase(),
        callbackAnchorAction: String(firstNonEmptyText([row.callback_anchor_action, row.callbackAnchorAction]) || "").trim().toLowerCase(),
        callbackAt: String(firstNonEmptyText([row.callback_at, row.callbackAt]) || "").trim(),
        updatedAt: String(firstNonEmptyText([row.updated_at, row.updatedAt]) || "").trim(),
        routeResolution: readRouteResolution(row.route_resolution || row.routeResolution),
        lateCallback: !!(row.late_callback === true || row.lateCallback === true),
        routeMismatch: !!(row.route_mismatch === true || row.routeMismatch === true),
        isSummary: !!(row.is_summary === true || row.isSummary === true),
        aggregateCount: readPositiveInt(firstNonEmptyText([row.aggregate_count, row.aggregateCount]), 0),
        summaryCount: readPositiveInt(firstNonEmptyText([row.summary_count, row.summaryCount]), 0),
      };
    }

    function normalizeConversationReceiptPendingAction(raw) {
      const row = (raw && typeof raw === "object") ? raw : {};
      const sourceRunId = String(firstNonEmptyText([row.source_run_id, row.sourceRunId]) || "").trim();
      if (!sourceRunId) return null;
      return {
        sourceRunId,
        callbackRunId: String(firstNonEmptyText([row.callback_run_id, row.callbackRunId]) || "").trim(),
        title: String(firstNonEmptyText([row.title]) || "").trim(),
        actionText: String(firstNonEmptyText([row.action_text, row.actionText]) || "").trim(),
        actionKind: String(firstNonEmptyText([row.action_kind, row.actionKind]) || "").trim().toLowerCase(),
        priority: String(firstNonEmptyText([row.priority]) || "").trim().toLowerCase(),
        sourceChannel: String(firstNonEmptyText([row.source_channel, row.sourceChannel]) || "").trim(),
        sourceAgentName: firstNonEmptyText([
          resolveConversationSourceAgentLabel(row),
          row.agent_name,
          row.agentName,
        ]),
        eventType: normalizeCallbackEventType(firstNonEmptyText([row.event_type, row.eventType])),
        callbackAt: String(firstNonEmptyText([row.callback_at, row.callbackAt]) || "").trim(),
        needConfirm: String(firstNonEmptyText([row.need_confirm, row.needConfirm]) || "").trim(),
      };
    }

    function readConversationReceiptProjection(run, detail) {
      const runMeta = (detail && detail.full && detail.full.run && typeof detail.full.run === "object")
        ? detail.full.run
        : ((run && typeof run === "object") ? run : {});
      const rawItems = []
        .concat(Array.isArray(runMeta.receipt_items) ? runMeta.receipt_items : [])
        .concat(Array.isArray(runMeta.receiptItems) ? runMeta.receiptItems : []);
      const rawPending = []
        .concat(Array.isArray(runMeta.receipt_pending_actions) ? runMeta.receipt_pending_actions : [])
        .concat(Array.isArray(runMeta.receiptPendingActions) ? runMeta.receiptPendingActions : []);
      const items = [];
      const pendingActions = [];
      rawItems.forEach((row) => {
        const item = normalizeConversationReceiptItem(row);
        if (item) items.push(item);
      });
      rawPending.forEach((row) => {
        const item = normalizeConversationReceiptPendingAction(row);
        if (item) pendingActions.push(item);
      });
      const rollupRaw = (runMeta.receipt_rollup && typeof runMeta.receipt_rollup === "object")
        ? runMeta.receipt_rollup
        : ((runMeta.receiptRollup && typeof runMeta.receiptRollup === "object") ? runMeta.receiptRollup : null);
      const rollup = rollupRaw ? {
        hostRunId: String(firstNonEmptyText([rollupRaw.host_run_id, rollupRaw.hostRunId]) || "").trim(),
        totalCallbacks: readPositiveInt(firstNonEmptyText([rollupRaw.total_callbacks, rollupRaw.totalCallbacks]), items.length),
        pendingActionCount: readPositiveInt(firstNonEmptyText([rollupRaw.pending_action_count, rollupRaw.pendingActionCount]), pendingActions.length),
        latestStatus: String(firstNonEmptyText([rollupRaw.latest_status, rollupRaw.latestStatus]) || "").trim().toLowerCase(),
        latestConclusion: String(firstNonEmptyText([rollupRaw.latest_conclusion, rollupRaw.latestConclusion]) || "").trim(),
        needConfirmCount: readPositiveInt(firstNonEmptyText([rollupRaw.need_confirm_count, rollupRaw.needConfirmCount]), 0),
        agents: Array.isArray(rollupRaw.agents) ? rollupRaw.agents.slice(0, 20).map((x) => String(x || "").trim()).filter(Boolean) : [],
        lastCallbackAt: String(firstNonEmptyText([rollupRaw.last_callback_at, rollupRaw.lastCallbackAt]) || "").trim(),
      } : null;
      if (!items.length && !pendingActions.length && !rollup) return null;
      return { items, pendingActions, rollup };
    }

    function ensureConversationReceiptViewerState() {
      if (!PCONV.receiptViewer || typeof PCONV.receiptViewer !== "object") {
        PCONV.receiptViewer = {
          open: false,
          kind: "receipt",
          hostRunId: "",
          item: null,
          pendingAction: null,
          bodyScrollTop: 0,
        };
      }
      return PCONV.receiptViewer;
    }

    function closeConversationReceiptViewer() {
      const viewer = ensureConversationReceiptViewerState();
      viewer.open = false;
      viewer.kind = "receipt";
      viewer.hostRunId = "";
      viewer.item = null;
      viewer.pendingAction = null;
      viewer.bodyScrollTop = 0;
      renderConversationDetail(false);
    }

    function openConversationReceiptViewer(payload = {}) {
      const viewer = ensureConversationReceiptViewerState();
      viewer.open = true;
      viewer.kind = String(payload.kind || "receipt").trim() || "receipt";
      viewer.hostRunId = String(payload.hostRunId || "").trim();
      viewer.item = payload.item && typeof payload.item === "object" ? { ...payload.item } : null;
      viewer.pendingAction = payload.pendingAction && typeof payload.pendingAction === "object" ? { ...payload.pendingAction } : null;
      viewer.bodyScrollTop = 0;
      const callbackRunId = String(firstNonEmptyText([
        viewer.item && viewer.item.callbackRunId,
        viewer.pendingAction && viewer.pendingAction.callbackRunId,
      ]) || "").trim();
      if (callbackRunId) {
        const d = PCONV.detailMap && PCONV.detailMap[callbackRunId];
        if (!d || (!d.loading && !String((d.full && d.full.message) || "").trim())) {
          ensureConversationRunDetail(callbackRunId, { force: true, maxAgeMs: 0 });
        }
      }
      renderConversationDetail(false);
    }

    function conversationReceiptOpinionText(item) {
      const needConfirm = String((item && item.needConfirm) || "").trim();
      if (needConfirm && needConfirm !== "无") return needConfirm;
      return firstNonEmptyText([
        item && item.needPeer,
        item && item.currentConclusion,
        item && item.expectedResult,
      ]);
    }

    function conversationReceiptStatusMeta(item) {
      const runtimeStatus = normalizeCallbackEventType(item && item.runtimeStatus);
      const eventType = normalizeCallbackEventType(item && item.eventType);
      const needConfirm = String((item && item.needConfirm) || "").trim();
      if (needConfirm && needConfirm !== "无") return { text: "待确认", tone: "warn" };
      if (runtimeStatus === "running") return { text: "处理中", tone: "waiting" };
      if (runtimeStatus === "queued") return { text: "排队中", tone: "queued" };
      if (runtimeStatus === "retry_waiting") return { text: "等待重试", tone: "waiting" };
      if (runtimeStatus === "external_busy") return { text: "外部处理中", tone: "external" };
      if (eventType === "error") return { text: "异常", tone: "bad" };
      if (eventType === "interrupted") return { text: "已中断", tone: "warn" };
      if (eventType === "done") return { text: "已完成", tone: "good" };
      if (eventType === "running") return { text: "处理中", tone: "waiting" };
      if (eventType === "queued") return { text: "排队中", tone: "queued" };
      if (eventType === "retry_waiting") return { text: "等待重试", tone: "waiting" };
      if (eventType === "external_busy") return { text: "外部处理中", tone: "external" };
      return null;
    }

    function conversationReceiptPrimaryTitle(itemOrAction) {
      const row = (itemOrAction && typeof itemOrAction === "object") ? itemOrAction : {};
      return firstNonEmptyText([
        row.sourceAgentName,
        row.sourceChannel,
        row.targetChannel,
        "未知回执",
      ]) || "未知回执";
    }

    function conversationReceiptMetaLine(item) {
      const row = (item && typeof item === "object") ? item : {};
      const bits = [];
      const sourceChannel = String(row.sourceChannel || "").trim();
      const sourceAgentName = String(row.sourceAgentName || "").trim();
      if (sourceChannel && sourceChannel !== sourceAgentName) bits.push(sourceChannel);
      if (row.callbackAt) bits.push(compactDateTime(row.callbackAt) || "");
      return bits.filter(Boolean).join(" · ");
    }

    function isConversationReceiptSelected(viewer, item) {
      if (!viewer || !viewer.open || viewer.kind !== "receipt" || !viewer.item || !item) return false;
      return String(viewer.item.sourceRunId || "") === String(item.sourceRunId || "")
        && String(viewer.item.callbackRunId || "") === String(item.callbackRunId || "");
    }

    function isConversationPendingSelected(viewer, row) {
      if (!viewer || !viewer.open || viewer.kind !== "pending" || !viewer.pendingAction || !row) return false;
      return String(viewer.pendingAction.sourceRunId || "") === String(row.sourceRunId || "")
        && String(viewer.pendingAction.callbackRunId || "") === String(row.callbackRunId || "")
        && String(viewer.pendingAction.title || "") === String(row.title || "");
    }

    function renderConversationReceiptDetailBlock(title, opts = {}) {
      const block = el("div", { class: "conv-receipt-detail-block" });
      block.appendChild(el("div", {
        class: "conv-receipt-detail-label",
        text: String(title || "").trim(),
      }));
      const mainText = String(opts.mainText || "").trim();
      if (mainText) block.appendChild(el("div", { class: "conv-receipt-detail-main", text: mainText }));
      const subText = String(opts.subText || "").trim();
      if (subText) block.appendChild(el("div", { class: "conv-receipt-detail-sub", text: subText }));
      return block;
    }

    function appendConversationReceiptDetailRow(container, label, value, opts = {}) {
      if (!container || !label) return;
      const node = opts.node || null;
      const text = String(value || "").trim();
      if (!node && !text) return;
      const row = el("div", { class: "conv-receipt-detail-row" + (opts.warn ? " warn" : "") });
      row.appendChild(el("div", { class: "conv-receipt-detail-k", text: String(label || "").trim() }));
      if (node) row.appendChild(node);
      else row.appendChild(el("div", { class: "conv-receipt-detail-v", text }));
      container.appendChild(row);
    }

    function renderConversationReceiptRawContent(rawText) {
      const block = renderConversationReceiptDetailBlock("原始内容");
      const body = el("div", { class: "conv-receipt-raw-body md" });
      const resolvedText = String(rawText || "").trim() || "原始回执暂未同步完成。";
      setMarkdown(body, resolvedText, resolvedText);
      enhanceMessageInteractiveObjects(body);
      block.appendChild(body);
      return block;
    }

    function renderConversationReceiptFallbackDetail(item, pendingAction) {
      const root = el("div", { class: "conv-receipt-viewer-fallback" });
      const overview = renderConversationReceiptDetailBlock("回执信息");
      if (item) {
        const opinion = conversationReceiptOpinionText(item) || "暂无详细意见。";
        const summary = renderConversationReceiptDetailBlock("主意见", {
          mainText: opinion,
          subText: item.currentConclusion && item.currentConclusion !== opinion
            ? ("当前结论：" + item.currentConclusion)
            : "",
        });
        root.appendChild(summary);
        const status = conversationReceiptStatusMeta(item);
        if (status) {
          const statusNode = el("div", { class: "conv-receipt-detail-v" });
          statusNode.appendChild(chip(status.text, status.tone));
          appendConversationReceiptDetailRow(overview, "主状态", "", { node: statusNode });
        }
        appendConversationReceiptDetailRow(overview, "回执对象", conversationReceiptPrimaryTitle(item));
        if (item.sourceAgentName && item.sourceAgentName !== item.sourceChannel) {
          appendConversationReceiptDetailRow(overview, "来源Agent", item.sourceAgentName);
        }
        appendConversationReceiptDetailRow(overview, "来源通道", item.sourceChannel || "");
        appendConversationReceiptDetailRow(overview, "执行阶段", item.executionStage || "");
        appendConversationReceiptDetailRow(overview, "回执时间", item.callbackAt ? (zhDateTime(item.callbackAt) || item.callbackAt) : "");
        appendConversationReceiptDetailRow(overview, "需要确认", item.needConfirm || "", { warn: !!(item.needConfirm && item.needConfirm !== "无") });
        appendConversationReceiptDetailRow(overview, "需要对方", item.needPeer || "");
        appendConversationReceiptDetailRow(overview, "预期结果", item.expectedResult || "");
      }
      if (pendingAction) {
        appendConversationReceiptDetailRow(overview, "待办动作", pendingAction.title || "待处理动作");
        appendConversationReceiptDetailRow(overview, "动作说明", pendingAction.actionText || "");
        appendConversationReceiptDetailRow(overview, "动作类型", pendingAction.actionKind || "");
        appendConversationReceiptDetailRow(overview, "优先级", pendingAction.priority || "");
        if (!item) {
          appendConversationReceiptDetailRow(overview, "来源通道", pendingAction.sourceChannel || "");
        }
      }
      if (overview.childNodes.length) {
        root.appendChild(overview);
      }
      return root;
    }

    function renderConversationReceiptViewer() {
      const viewer = ensureConversationReceiptViewerState();
      if (!viewer.open) return null;
      const item = viewer.item && typeof viewer.item === "object" ? viewer.item : null;
      const pendingAction = viewer.pendingAction && typeof viewer.pendingAction === "object" ? viewer.pendingAction : null;
      const callbackRunId = String(firstNonEmptyText([
        item && item.callbackRunId,
        pendingAction && pendingAction.callbackRunId,
      ]) || "").trim();
      const callbackDetail = callbackRunId ? ((PCONV.detailMap && PCONV.detailMap[callbackRunId]) || null) : null;
      const callbackRun = (callbackDetail && callbackDetail.full && callbackDetail.full.run && typeof callbackDetail.full.run === "object")
        ? callbackDetail.full.run
        : null;
      const callbackRawText = String(firstNonEmptyText([
        callbackDetail && callbackDetail.full && callbackDetail.full.message,
        callbackRun && (callbackRun.message || callbackRun.raw_message || callbackRun.rawMessage),
        callbackDetail && callbackDetail.full && callbackDetail.full.lastMessage,
        callbackDetail && callbackDetail.full && callbackDetail.full.partialMessage,
      ]) || "").trim();
      const titleSource = firstNonEmptyText([
        item && conversationReceiptPrimaryTitle(item),
        pendingAction && conversationReceiptPrimaryTitle(pendingAction),
        "回执详情",
      ]) || "回执详情";
      const subtitle = viewer.kind === "pending"
        ? "点击待办卡后打开；这里只展示这 1 条待办和其关联回执。"
        : "点击回执卡后打开；这里只展示这 1 条回执的完整信息。";

      const mask = el("div", { class: "bmask conv-receipt-viewer-mask show" });
      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeConversationReceiptViewer();
      });
      const dialog = el("div", { class: "bmodal conv-receipt-viewer-modal" });
      const head = el("div", { class: "bmodalh" });
      head.appendChild(el("div", { class: "t", text: (viewer.kind === "pending" ? "待办详情 · " : "回执详情 · ") + titleSource }));
      head.appendChild(el("div", { class: "s", text: subtitle }));
      dialog.appendChild(head);

      const body = el("div", { class: "bmodalb conv-receipt-viewer-body" });
      body.addEventListener("scroll", () => {
        viewer.bodyScrollTop = body.scrollTop;
      }, { passive: true });
      body.appendChild(renderConversationReceiptFallbackDetail(item, pendingAction));
      if (callbackRunId && callbackDetail && callbackDetail.loading) {
        body.appendChild(el("div", { class: "hint", text: "回执详情加载中..." }));
      } else if (callbackRunId || callbackRawText) {
        body.appendChild(renderConversationReceiptRawContent(
          callbackRawText || "原始回执暂未同步完成。"
        ));
      }
      dialog.appendChild(body);

      const foot = el("div", { class: "bmodalf" });
      const closeBtn = el("button", { class: "btn", type: "button", text: "关闭" });
      closeBtn.addEventListener("click", closeConversationReceiptViewer);
      foot.appendChild(closeBtn);
      dialog.appendChild(foot);
      mask.appendChild(dialog);
      return mask;
    }

    function ensureConversationReceiptViewerMountHost() {
      let host = document.getElementById("convReceiptViewerMountHost");
      if (host) return host;
      host = el("div", { id: "convReceiptViewerMountHost" });
      document.body.appendChild(host);
      return host;
    }

    function syncConversationReceiptViewerMount() {
      const viewer = ensureConversationReceiptViewerState();
      const host = ensureConversationReceiptViewerMountHost();
      const oldBody = host.querySelector(".conv-receipt-viewer-body");
      if (oldBody && viewer.open) viewer.bodyScrollTop = oldBody.scrollTop;
      host.replaceChildren();
      const mask = renderConversationReceiptViewer();
      if (!mask) return;
      host.appendChild(mask);
      const nextBody = mask.querySelector(".conv-receipt-viewer-body");
      if (!nextBody) return;
      const savedTop = Math.max(0, Number(viewer.bodyScrollTop || 0) || 0);
      requestAnimationFrame(() => {
        if (!nextBody.isConnected) return;
        const maxTop = Math.max(0, nextBody.scrollHeight - nextBody.clientHeight);
        nextBody.scrollTop = Math.min(savedTop, maxTop);
      });
    }

    function renderConversationReceiptStack(payload = {}) {
      const projection = payload.projection || null;
      if (!projection || (!projection.items.length && !projection.pendingActions.length)) return null;
      const hostRunId = String(payload.runId || "").trim();
      const stack = el("div", { class: "conv-receipt-stack" });
      const pendingBySource = Object.create(null);
      const itemBySource = Object.create(null);
      projection.pendingActions.forEach((row) => {
        const key = String(row.sourceRunId || "").trim();
        if (!key) return;
        pendingBySource[key] = Number(pendingBySource[key] || 0) + 1;
      });
      projection.items.forEach((row) => {
        const key = String(row.sourceRunId || "").trim();
        if (key && !itemBySource[key]) itemBySource[key] = row;
      });

      if (projection.items.length) {
        const section = el("div", { class: "conv-receipt-section" });
        const head = el("div", { class: "conv-receipt-section-label" });
        const titleGroup = el("div", { class: "conv-receipt-section-title" });
        titleGroup.appendChild(el("span", { text: "处理回执" }));
        titleGroup.appendChild(el("span", {
          class: "conv-receipt-section-count",
          text: String(projection.items.length) + " 条",
        }));
        head.appendChild(titleGroup);
        section.appendChild(head);
        const grid = el("div", { class: "conv-receipt-grid" });
        const viewer = ensureConversationReceiptViewerState();
        projection.items.forEach((item) => {
          const pendingCount = Math.max(0, Number(pendingBySource[item.sourceRunId] || 0));
          const status = conversationReceiptStatusMeta(item);
          const metaLine = conversationReceiptMetaLine(item);
          const card = el("button", {
            class: "conv-receipt-card"
              + (pendingCount > 0 ? " has-pending" : "")
              + (isConversationReceiptSelected(viewer, item) ? " selected" : ""),
            type: "button",
            title: [conversationReceiptPrimaryTitle(item), item.currentConclusion || "", item.callbackAt ? zhDateTime(item.callbackAt) : ""].filter(Boolean).join("\n"),
          });
          const headRow = el("div", { class: "conv-receipt-card-head" });
          headRow.appendChild(el("div", { class: "conv-receipt-card-title", text: conversationReceiptPrimaryTitle(item) }));
          if (status) headRow.appendChild(chip(status.text, status.tone));
          card.appendChild(headRow);
          if (metaLine) card.appendChild(el("div", { class: "conv-receipt-card-meta", text: metaLine }));
          card.appendChild(el("div", {
            class: "conv-receipt-card-body",
            text: conversationReceiptOpinionText(item) || item.currentConclusion || "暂无回执意见。",
          }));
          const foot = el("div", { class: "conv-receipt-card-foot" });
          const left = el("span", { class: "left" });
          if (pendingCount > 0) left.appendChild(chip("待办 " + String(pendingCount), "warn"));
          else left.appendChild(el("span", { text: "无待办" }));
          foot.appendChild(left);
          foot.appendChild(el("span", { text: "点击看详情" }));
          card.appendChild(foot);
          card.addEventListener("click", () => {
            openConversationReceiptViewer({
              kind: "receipt",
              hostRunId,
              item,
              pendingAction: pendingCount > 0
                ? (projection.pendingActions.find((row) => String(row.sourceRunId || "") === String(item.sourceRunId || "")) || null)
                : null,
            });
          });
          grid.appendChild(card);
        });
        section.appendChild(grid);
        stack.appendChild(section);
      }

      if (projection.pendingActions.length) {
        const section = el("div", { class: "conv-receipt-section" });
        const head = el("div", { class: "conv-receipt-section-label" });
        const titleGroup = el("div", { class: "conv-receipt-section-title" });
        titleGroup.appendChild(el("span", { text: "待办列表" }));
        titleGroup.appendChild(el("span", {
          class: "conv-receipt-section-count",
          text: String(projection.pendingActions.length) + " 项",
        }));
        head.appendChild(titleGroup);
        section.appendChild(head);
        const grid = el("div", { class: "conv-receipt-grid" });
        const viewer = ensureConversationReceiptViewerState();
        projection.pendingActions.forEach((row) => {
          const relatedItem = itemBySource[String(row.sourceRunId || "").trim()] || null;
          const card = el("button", {
            class: "conv-receipt-card todo" + (isConversationPendingSelected(viewer, row) ? " selected" : ""),
            type: "button",
            title: [row.title || "待办", row.actionText || "", row.sourceChannel || ""].filter(Boolean).join("\n"),
          });
          const headRow = el("div", { class: "conv-receipt-card-head" });
          headRow.appendChild(el("div", { class: "conv-receipt-card-title", text: row.title || "待办动作" }));
          headRow.appendChild(chip(row.priority === "high" ? "高优" : "待处理", row.priority === "high" ? "bad" : "warn"));
          card.appendChild(headRow);
          card.appendChild(el("div", {
            class: "conv-receipt-card-body",
            text: row.actionText || "请查看关联回执详情。",
          }));
          const foot = el("div", { class: "conv-receipt-card-foot" });
          foot.appendChild(el("span", {
            class: "left",
            text: "来源：" + (row.sourceChannel || relatedItem && relatedItem.sourceChannel || "-"),
          }));
          foot.appendChild(el("span", { text: "点击看详情" }));
          card.appendChild(foot);
          card.addEventListener("click", () => {
            openConversationReceiptViewer({
              kind: "pending",
              hostRunId,
              item: relatedItem,
              pendingAction: row,
            });
          });
          grid.appendChild(card);
        });
        section.appendChild(grid);
        stack.appendChild(section);
      }
      return stack;
    }

    function queueConversationReply(payload) {
      const draftKey = String(PCONV.composerBoundDraftKey || currentConvComposerDraftKey() || "").trim();
      if (!draftKey) return false;
      const ok = setConvComposerReplyByKey(draftKey, payload || {});
      if (ok) setHintText("conv", "已带入回复内容，可继续编辑后发送。");
      return ok;
    }

    function maybeStickConversationBottom(force = false) {
      const box = document.getElementById("convTimeline");
      if (!box) return;
      const nearBottom = (box.scrollHeight - box.scrollTop - box.clientHeight) < 80;
      if (force || nearBottom) box.scrollTop = box.scrollHeight;
    }

    function restoreConversationTimelineScroll(box, anchor = {}) {
      if (!box) return;
      const maxTop = Math.max(0, box.scrollHeight - box.clientHeight);
      let top = Number(anchor.scrollTop || 0);
      if (!Number.isFinite(top) || top < 0) top = 0;
      if (top > maxTop) top = maxTop;
      box.scrollTop = top;
    }

    function shouldFoldBubble(text, role) {
      const src = String(text || "");
      if (!src.trim()) return false;
      if (role === "user") {
        const lineCount = src.split(/\r?\n/).filter((line) => line.trim()).length;
        return src.trim().length > 220 || lineCount > 6;
      }
      // AI 消息默认折叠，用户点击后展开
      return true;
    }

    function collectRunSkills(run, detail, assistantText, processInfo) {
      const out = [];
      const seen = new Set();
      const push = (raw) => {
        const tok = normalizeSkillToken(raw);
        if (!tok || seen.has(tok)) return;
        seen.add(tok);
        out.push(tok);
      };
      const runMeta = (detail && detail.full && detail.full.run && typeof detail.full.run === "object")
        ? detail.full.run
        : ((run && typeof run === "object") ? run : {});
      const explicit = []
        .concat(Array.isArray(runMeta.skills_used) ? runMeta.skills_used : [])
        .concat(Array.isArray(runMeta.skillsUsed) ? runMeta.skillsUsed : []);
      explicit.forEach(push);
      if (out.length > 0) return out.slice(0, 20);

      const fallbackTexts = [];
      const at = String(assistantText || "").trim();
      if (at) fallbackTexts.push(at);
      const last = String((detail && detail.full && detail.full.lastMessage) || "").trim();
      if (last) fallbackTexts.push(last);
      const partial = String((runMeta && runMeta.partialPreview) || (run && run.partialPreview) || "").trim();
      if (partial) fallbackTexts.push(partial);
      const processItems = Array.isArray(processInfo && processInfo.items) ? processInfo.items : [];
      processItems.forEach((x) => { if (x) fallbackTexts.push(String(x)); });
      const parsed = [];
      fallbackTexts.forEach((txt) => {
        extractSkillsFromText(txt).forEach((s) => parsed.push(s));
      });
      parsed.forEach(push);
      return out.slice(0, 20);
    }

    function collectRunBusinessRefs(run, detail, assistantText, processInfo) {
      const out = [];
      const seen = new Set();
      const push = (raw) => {
        const it = normalizeBusinessRefItem(raw);
        if (!it) return;
        const key = [it.type, it.path, it.title].join("|");
        if (seen.has(key)) return;
        seen.add(key);
        out.push(it);
      };
      const runMeta = (detail && detail.full && detail.full.run && typeof detail.full.run === "object")
        ? detail.full.run
        : ((run && typeof run === "object") ? run : {});
      const explicit = []
        .concat(Array.isArray(runMeta.business_refs) ? runMeta.business_refs : [])
        .concat(Array.isArray(runMeta.businessRefs) ? runMeta.businessRefs : []);
      explicit.forEach(push);
      if (out.length > 0) return out.slice(0, 24);

      const fallbackTexts = [];
      const at = String(assistantText || "").trim();
      if (at) fallbackTexts.push(at);
      const last = String((detail && detail.full && detail.full.lastMessage) || "").trim();
      if (last) fallbackTexts.push(last);
      const partial = String((runMeta && runMeta.partialPreview) || (run && run.partialPreview) || "").trim();
      if (partial) fallbackTexts.push(partial);
      const processItems = Array.isArray(processInfo && processInfo.items) ? processInfo.items : [];
      processItems.forEach((x) => { if (x) fallbackTexts.push(String(x)); });
      fallbackTexts.forEach((txt) => {
        extractBusinessRefsFromText(txt).forEach((it) => push(it));
      });
      return out.slice(0, 24);
    }

    function collectRunAgentRefs(run, detail, userText, assistantText, processInfo, currentSessionId = "") {
      const out = [];
      const byKey = Object.create(null);
      const currentSid = String(currentSessionId || "").trim().toLowerCase();
      const push = (raw) => {
        const item = (typeof raw === "string")
          ? { sessionId: raw }
          : ((raw && typeof raw === "object") ? raw : null);
        if (!item) return;
        let sid = String(item.sessionId || item.session_id || item.id || "").trim().toLowerCase();
        if (sid && !UUID_TOKEN_RE.test(sid)) sid = "";
        if (sid && currentSid && sid === currentSid) return;
        const mapped = sid ? findSessionLabelById(sid) : "";
        const label = normalizeAgentLabel(firstNonEmptyText([item.label, item.channelName, item.channel_name, mapped]));
        const channelName = normalizeAgentLabel(firstNonEmptyText([
          item.channelName,
          item.channel_name,
          sid ? findSessionChannelById(sid) : "",
          extractSourceChannelName(label),
        ]));
        const display = channelName || label || (sid ? shortAgentSessionId(sid) : "");
        if (!display) return;
        const key = sid ? ("sid:" + sid) : ("ch:" + normalizeChannelKey(display));
        if (!key) return;
        const existing = byKey[key];
        if (existing) {
          existing.hitCount += 1;
          if (!existing.sessionId && sid) existing.sessionId = sid;
          if (!existing.channelName && channelName) existing.channelName = channelName;
          if (!existing.label && label) existing.label = label;
          if (!existing.display && display) existing.display = display;
          return;
        }
        const entry = {
          key,
          sessionId: sid,
          channelName: channelName || "",
          label: label || "",
          display,
          hitCount: 1,
        };
        byKey[key] = entry;
        out.push(entry);
      };
      const runMeta = (detail && detail.full && detail.full.run && typeof detail.full.run === "object")
        ? detail.full.run
        : ((run && typeof run === "object") ? run : {});
      const explicit = []
        .concat(Array.isArray(runMeta.agent_refs) ? runMeta.agent_refs : [])
        .concat(Array.isArray(runMeta.agentRefs) ? runMeta.agentRefs : []);
      explicit.forEach(push);

      const fallbackTexts = [];
      const ut = String(userText || "").trim();
      if (ut) fallbackTexts.push(ut);
      const at = String(assistantText || "").trim();
      if (at) fallbackTexts.push(at);
      const last = String((detail && detail.full && detail.full.lastMessage) || "").trim();
      if (last) fallbackTexts.push(last);
      const partial = String((runMeta && runMeta.partialPreview) || (run && run.partialPreview) || "").trim();
      if (partial) fallbackTexts.push(partial);
      const processItems = Array.isArray(processInfo && processInfo.items) ? processInfo.items : [];
      processItems.forEach((x) => { if (x) fallbackTexts.push(String(x)); });
      fallbackTexts.forEach((txt) => {
        extractAgentRefsFromText(txt, currentSessionId).forEach((it) => push(it));
        const sourceChannel = extractSourceChannelName(txt);
        if (sourceChannel) push({ channelName: sourceChannel, label: sourceChannel });
      });
      out.sort((a, b) => {
        const c = Number(b && b.hitCount || 0) - Number(a && a.hitCount || 0);
        if (c !== 0) return c;
        return String((a && a.display) || "").localeCompare(String((b && b.display) || ""));
      });
      return out.slice(0, 16);
    }

    function renderSkillsRow(runId, skills) {
      const rid = String(runId || "").trim();
      const rows = Array.isArray(skills) ? skills.filter(Boolean) : [];
      if (!rid || rows.length === 0) return null;
      const expanded = !!PCONV.skillsExpandedByRun[rid];
      const maxInline = 2;
      const shown = expanded ? rows : rows.slice(0, maxInline);
      const remain = Math.max(0, rows.length - shown.length);

      const box = el("div", { class: "msgskills" });
      const line = el("div", { class: "msgskills-line " + (expanded ? "expanded" : "collapsed") });
      shown.forEach((name) => {
        const tag = el("span", { class: "skilltag" });
        appendTagContent(tag, { kind: "skill", text: name });
        line.appendChild(tag);
      });
      if (remain > 0 || expanded) {
        const btnText = expanded ? "收起" : ("+" + remain);
        const btn = el("button", { class: "skilltag skilltag-toggle", text: btnText, title: expanded ? "收起 Skills" : ("展开剩余 " + remain + " 个 Skills") });
        btn.addEventListener("click", () => {
          PCONV.skillsExpandedByRun[rid] = !PCONV.skillsExpandedByRun[rid];
          renderConversationDetail();
        });
        line.appendChild(btn);
      }
      box.appendChild(line);
      return box;
    }

    function renderBusinessRefsRow(runId, refs) {
      const rid = String(runId || "").trim();
      const rows = Array.isArray(refs) ? refs.filter(Boolean) : [];
      if (!rid || rows.length === 0) return null;
      const expanded = !!PCONV.businessRefsExpandedByRun[rid];
      const maxInline = 2;
      const shown = expanded ? rows : rows.slice(0, maxInline);
      const remain = Math.max(0, rows.length - shown.length);
      const box = el("div", { class: "msgbusiness" });
      const line = el("div", { class: "msgbusiness-line " + (expanded ? "expanded" : "collapsed") });

      shown.forEach((it) => {
        const typ = String(it.type || "其他");
        const title = String(it.title || "");
        const path = String(it.path || "");
        const iconKind = businessTypeIconKind(typ);
        const text = title || typ;
        const label = typ + " · " + title;
        const objectTarget = (typeof classifyMessageObjectToken === "function")
          ? (classifyMessageObjectToken(path) || classifyMessageObjectToken(title))
          : null;
        const tagTitle = path ? (label + "\n" + path) : label;
        const tag = objectTarget
          ? el("button", { class: "biztag biztag-action", type: "button", title: tagTitle + "\n点击查看详情" })
          : el("span", { class: "biztag", title: tagTitle });
        appendTagContent(tag, { kind: iconKind, text, fallbackTypeText: iconKind ? "" : typ });
        if (objectTarget) {
          objectTarget.label = String(objectTarget.label || title || path || typ || "对象").trim();
          objectTarget.lookupLabel = String(title || objectTarget.label || "").trim();
          if (!String(objectTarget.path || "").trim() && path) objectTarget.path = path;
          if (typeof bindMessageObjectActivator === "function") bindMessageObjectActivator(tag, objectTarget);
          else {
            tag.addEventListener("click", (e) => {
              e.preventDefault();
              e.stopPropagation();
              if (typeof activateMessageObject === "function") activateMessageObject(objectTarget);
            });
          }
        }
        line.appendChild(tag);
      });
      if (remain > 0 || expanded) {
        const btnText = expanded ? "收起" : ("+" + remain);
        const btn = el("button", { class: "biztag biztag-toggle", text: btnText, title: expanded ? "收起业务对象" : ("展开剩余 " + remain + " 个业务对象") });
        btn.addEventListener("click", () => {
          PCONV.businessRefsExpandedByRun[rid] = !PCONV.businessRefsExpandedByRun[rid];
          renderConversationDetail();
        });
        line.appendChild(btn);
      }
      box.appendChild(line);
      return box;
    }

    function renderAgentRefsRow(runId, refs) {
      const rid = String(runId || "").trim();
      const rows = Array.isArray(refs) ? refs.filter(Boolean) : [];
      if (!rid || rows.length === 0) return null;
      const expanded = !!PCONV.agentRefsExpandedByRun[rid];
      const maxInline = 2;
      const shown = expanded ? rows : rows.slice(0, maxInline);
      const remain = Math.max(0, rows.length - shown.length);
      const box = el("div", { class: "msgagents" });
      const line = el("div", { class: "msgagents-line " + (expanded ? "expanded" : "collapsed") });
      shown.forEach((it) => {
        const sid = String(it.sessionId || "").trim();
        const display = String(it.display || it.channelName || it.label || (sid ? shortAgentSessionId(sid) : "")).trim();
        const titleLines = [display];
        if (it.channelName && it.channelName !== display) titleLines.push("通道: " + String(it.channelName));
        if (sid) titleLines.push("session_id: " + sid);
        const tag = el("span", { class: "agenttag", title: titleLines.join("\n") });
        appendTagContent(tag, { kind: "agent", text: display });
        line.appendChild(tag);
      });
      if (remain > 0 || expanded) {
        const btnText = expanded ? "收起" : ("+" + remain);
        const btn = el("button", { class: "agenttag agenttag-toggle", text: btnText, title: expanded ? "收起协同Agent" : ("展开剩余 " + remain + " 个协同Agent") });
        btn.addEventListener("click", () => {
          PCONV.agentRefsExpandedByRun[rid] = !PCONV.agentRefsExpandedByRun[rid];
          renderConversationDetail();
        });
        line.appendChild(btn);
      }
      box.appendChild(line);
      return box;
    }

    function collectRunMentionTargets(run, detail, userText, extraTargets = []) {
      const out = [];
      const seen = new Set();
      const push = (raw) => {
        if (!raw || typeof raw !== "object") return;
        const sessionId = String(firstNonEmptyText([
          raw.session_id,
          raw.sessionId,
          raw.id,
        ]) || "").trim();
        const channelName = String(firstNonEmptyText([
          raw.channel_name,
          raw.channelName,
          raw.channel,
          sessionId ? findSessionChannelById(sessionId) : "",
        ]) || "").trim();
        const displayName = String(firstNonEmptyText([
          raw.alias,
          raw.display_name,
          raw.displayName,
          raw.label,
          channelName,
        ]) || "").trim();
        if (!channelName && !displayName) return;
        const m = {
          channel_name: channelName,
          session_id: sessionId,
          cli_type: String(firstNonEmptyText([raw.cli_type, raw.cliType, ""]) || "").trim(),
          display_name: displayName || channelName,
          project_id: String(firstNonEmptyText([
            raw.project_id,
            raw.projectId,
          ]) || "").trim(),
        };
        const key = (sessionId
          ? ("sid:" + sessionId.toLowerCase())
          : ("ch:" + String(channelName || m.display_name || "").toLowerCase() + "::" + m.display_name.toLowerCase()));
        if (!key || seen.has(key)) return;
        seen.add(key);
        out.push(m);
      };
      const runMeta = (detail && detail.full && detail.full.run && typeof detail.full.run === "object")
        ? detail.full.run
        : ((run && typeof run === "object") ? run : {});
      []
        .concat(Array.isArray(runMeta.mention_targets) ? runMeta.mention_targets : [])
        .concat(Array.isArray(runMeta.mentionTargets) ? runMeta.mentionTargets : [])
        .concat(Array.isArray(run && run.mention_targets) ? run.mention_targets : [])
        .concat(Array.isArray(run && run.mentionTargets) ? run.mentionTargets : [])
        .concat(Array.isArray(extraTargets) ? extraTargets : [])
        .forEach(push);
      if (!out.length) {
        const parsed = extractMentionTargetsFromText(userText);
        parsed.forEach(push);
      }
      return out.slice(0, 12);
    }

    function filterRunAgentRefsAgainstMentions(agentRefs, mentionTargets) {
      const refs = Array.isArray(agentRefs) ? agentRefs.filter(Boolean) : [];
      const mentions = Array.isArray(mentionTargets) ? mentionTargets.filter(Boolean) : [];
      if (!refs.length || !mentions.length) return refs;
      const mentionSessionIds = new Set();
      const mentionNames = new Set();
      mentions.forEach((it) => {
        const sid = String((it && it.session_id) || "").trim().toLowerCase();
        if (sid) mentionSessionIds.add(sid);
        const display = normalizeAgentLabel(firstNonEmptyText([
          it && it.display_name,
          it && it.channel_name,
        ]));
        if (display) mentionNames.add(display.toLowerCase());
      });
      return refs.filter((it) => {
        const sid = String((it && it.sessionId) || "").trim().toLowerCase();
        if (sid && mentionSessionIds.has(sid)) return false;
        const display = normalizeAgentLabel(firstNonEmptyText([
          it && it.display,
          it && it.channelName,
          it && it.label,
        ]));
        if (display && mentionNames.has(display.toLowerCase())) return false;
        return true;
      });
    }

    function renderMentionTargetsRow(targets) {
      const rows = Array.isArray(targets) ? targets.filter(Boolean) : [];
      if (!rows.length) return null;
      const box = el("div", { class: "msgmentions" });
      const line = el("div", { class: "msgmentions-line" });
      line.appendChild(el("span", { class: "mentiontag mentiontag-lead", text: "协同对象 " + rows.length }));
      rows.forEach((it) => {
        const display = String((it && (it.display_name || it.channel_name)) || "协同对象").trim();
        const projectId = String((it && it.project_id) || "").trim();
        const scopedDisplay = projectId ? (projectId + "/" + display) : display;
        const sid = String((it && it.session_id) || "").trim();
        const tag = el("span", {
          class: "mentiontag",
          title: (projectId ? ("project_id: " + projectId + "\n") : "") + (sid ? ("session_id: " + sid) : ""),
        });
        appendTagContent(tag, { kind: "agent", text: scopedDisplay });
        line.appendChild(tag);
      });
      box.appendChild(line);
      return box;
    }

    function resolveConversationBubbleCopyText(role, content, fallback, opts = {}) {
      const primary = String(content || "").trim();
      const fb = String(fallback || "").trim();
      if (String(role || "") !== "assistant") return primary || fb;
      const runId = String((opts && opts.runId) || "").trim();
      if (!runId) return primary || fb;
      const d = PCONV.detailMap && PCONV.detailMap[runId];
      const full = d && d.full ? d.full : null;
      const lastMessage = String((full && full.lastMessage) || "").trim();
      const partialMessage = String((full && full.partialMessage) || "").trim();
      return lastMessage || partialMessage || primary || fb;
    }

    function copyConversationBubbleText(role, content, fallback, opts = {}) {
      const text = resolveConversationBubbleCopyText(role, content, fallback, opts);
      if (!text) return;
      if (typeof copyText === "function") {
        Promise.resolve(copyText(text))
          .then((ok) => {
            setHintText("conv", ok === false ? "复制失败：请手动复制全文" : "已复制全文");
          })
          .catch(() => { setHintText("conv", "复制失败：请手动复制全文"); });
        return;
      }
      navigator.clipboard?.writeText(text)
        .then(() => { setHintText("conv", "已复制全文"); })
        .catch(() => { setHintText("conv", "复制失败：请手动复制全文"); });
    }

    function conversationAttachmentRole(att) {
      return String(firstNonEmptyText([
        att && att.attachment_role,
        att && att.attachmentRole,
      ]) || "").trim().toLowerCase();
    }

    function isConversationAssistantGeneratedMediaAttachment(att) {
      if (!att || typeof att !== "object") return false;
      const attachmentRole = conversationAttachmentRole(att);
      if (attachmentRole && attachmentRole !== "assistant" && attachmentRole !== "agent") return false;
      const generatedBy = String(firstNonEmptyText([
        att.generatedBy,
        att.generated_by,
      ]) || "").trim().toLowerCase();
      const source = String(firstNonEmptyText([att.source]) || "").trim().toLowerCase();
      return generatedBy === "codex_imagegen" || source === "generated";
    }

    function isConversationAssistantGeneratedImageAttachment(att) {
      return isConversationAssistantGeneratedMediaAttachment(att) && isImageAttachment(att);
    }

    function isConversationUserInputAttachment(att) {
      if (!att || typeof att !== "object") return false;
      const attachmentRole = conversationAttachmentRole(att);
      if (attachmentRole && attachmentRole !== "user") return false;
      const generatedBy = String(firstNonEmptyText([
        att.generatedBy,
        att.generated_by,
      ]) || "").trim().toLowerCase();
      const source = String(firstNonEmptyText([att.source]) || "").trim().toLowerCase();
      if (generatedBy === "codex_imagegen" || source === "generated") return false;
      if (isConversationAssistantGeneratedMediaAttachment(att)) return false;
      return true;
    }

    function conversationAttachmentIdentityKey(att, idx = 0) {
      if (!att || typeof att !== "object") return "__att:" + String(idx || 0);
      return String(firstNonEmptyText([
        att.attachment_id,
        att.attachmentId,
        att.local_id,
        att.localId,
        att.path,
        att.url,
        att.dataUrl,
        att.filename,
        att.originalName,
      ]) || ("__att:" + String(idx || 0))).trim();
    }

    function mergeConversationAttachmentLists(lists) {
      const out = [];
      const seen = new Set();
      (Array.isArray(lists) ? lists : []).forEach((list) => {
        (Array.isArray(list) ? list : []).forEach((att, idx) => {
          if (!att || typeof att !== "object") return;
          const key = conversationAttachmentIdentityKey(att, idx);
          if (!key || seen.has(key)) return;
          seen.add(key);
          out.push(att);
        });
      });
      return out;
    }

    function filterConversationBubbleAttachments(role, attachments) {
      const rows = Array.isArray(attachments) ? attachments.filter(Boolean) : [];
      const normalizedRole = String(role || "").trim().toLowerCase();
      if (normalizedRole === "assistant") {
        return rows.filter((att) => isConversationAssistantGeneratedImageAttachment(att));
      }
      if (normalizedRole === "user") {
        return rows.filter((att) => isConversationUserInputAttachment(att));
      }
      return rows;
    }

    function firstConversationGeneratedMediaAttachmentUrl(attachments) {
      const rows = Array.isArray(attachments) ? attachments.filter(Boolean) : [];
      for (const att of rows) {
        if (!isConversationAssistantGeneratedMediaAttachment(att)) continue;
        const src = String(resolveAttachmentUrl(att) || "").trim();
        if (src) return src;
      }
      return "";
    }

    function firstConversationGeneratedMediaCount(values) {
      const rows = Array.isArray(values) ? values : [];
      for (const raw of rows) {
        const num = Number(raw);
        if (Number.isFinite(num) && num > 0) return num;
      }
      return 0;
    }

    function renderConversationGeneratedMediaCard(payload = {}) {
      const count = Math.max(0, Number(payload.count || 0));
      const summary = String(payload.summary || "").trim();
      const openUrl = String(payload.openUrl || "").trim();
      if (!count && !summary) return null;
      const card = el("div", { class: "msg-generated-media-card" });
      const head = el("div", { class: "msg-generated-media-head" });
      head.appendChild(el("div", {
        class: "msg-generated-media-title",
        text: count > 0 ? ("已生成 " + count + " 张图片") : "已生成图片结果",
      }));
      if (summary) {
        head.appendChild(el("div", {
          class: "msg-generated-media-sub",
          text: summary,
        }));
      }
      card.appendChild(head);
      if (openUrl) {
        const actions = el("div", { class: "msg-generated-media-actions" });
        const openBtn = el("button", { class: "btn textbtn", type: "button", text: "打开结果" });
        openBtn.addEventListener("click", () => {
          openNew(openUrl);
        });
        actions.appendChild(openBtn);
        card.appendChild(actions);
      }
      return card;
    }

    function appendConversationBubble(row, role, content, fallback, bubbleKey, opts = {}) {
      const txt = String(content || "");
      const attachments = filterConversationBubbleAttachments(role, opts.attachments || []);
      const replyQuote = renderConversationReplyQuote(opts.replyContext);
      if (replyQuote) row.appendChild(replyQuote);
      const bubble = el("div", { class: "mbubble md" });
      if (opts.bubbleClass) bubble.classList.add(String(opts.bubbleClass));
      const foldable = shouldFoldBubble(txt || fallback || "", role);
      const bubbleKeyText = String(bubbleKey || "");
      const pendingExpandSet = PCONV.bubblePendingExpand instanceof Set
        ? PCONV.bubblePendingExpand
        : (PCONV.bubblePendingExpand = new Set());
      const pendingExpand = pendingExpandSet.has(bubbleKeyText);
      const expanded = PCONV.bubbleExpanded.has(bubbleKeyText);
      const runId = String(opts.runId || "");
      const forceDetailOnExpand = !!opts.forceDetailOnExpand;
      const detailMeta = runId ? ((PCONV.detailMap && PCONV.detailMap[runId]) || null) : null;
      const ensureExpandedBubbleDetail = (extraOpts = {}) => {
        if (!runId) return;
        const mergedOpts = Object.assign({}, extraOpts);
        if (forceDetailOnExpand) {
          mergedOpts.force = true;
          mergedOpts.maxAgeMs = 0;
          ensureConversationRunDetail(runId, mergedOpts);
          return;
        }
        if (typeof mergedOpts.maxAgeMs !== "number") mergedOpts.maxAgeMs = 1200;
        ensureConversationRunDetail(runId, mergedOpts);
      };
      const toggleBubbleExpanded = () => {
        const key = bubbleKeyText;
        if (!key) return;
        if (PCONV.bubbleExpanded.has(key)) {
          PCONV.bubbleExpanded.delete(key);
          pendingExpandSet.delete(key);
        }
        else {
          if (runId && forceDetailOnExpand) {
            pendingExpandSet.add(key);
            ensureExpandedBubbleDetail({
              onLoaded: (_, err) => {
                if (!pendingExpandSet.has(key)) return;
                pendingExpandSet.delete(key);
                if (!err) PCONV.bubbleExpanded.add(key);
                renderConversationDetail();
              },
            });
          } else {
            PCONV.bubbleExpanded.add(key);
            ensureExpandedBubbleDetail();
          }
        }
        renderConversationDetail();
      };
      if (expanded && runId && !detailMeta) ensureExpandedBubbleDetail();
      setMarkdown(bubble, txt, fallback || "");
      enhanceMessageInteractiveObjects(bubble);
      const allowCopy = !!String(resolveConversationBubbleCopyText(role, content, fallback, opts) || "").trim();
      const allowReply = typeof opts.onReply === "function"
        && !!String(txt || fallback || "").trim();
      if (foldable && !expanded) bubble.classList.add("collapsed");
      if (foldable && !expanded) {
        const inlineBtn = el("button", {
          class: "btn textbtn bubble-expand-inline" + (pendingExpand ? " is-loading" : ""),
          type: "button",
          text: pendingExpand ? "加载全文中..." : "展开全文",
        });
        if (pendingExpand) {
          inlineBtn.disabled = true;
          inlineBtn.setAttribute("aria-busy", "true");
        } else {
          inlineBtn.addEventListener("click", toggleBubbleExpanded);
        }
        bubble.appendChild(inlineBtn);
      }
      row.appendChild(bubble);
      if (foldable && expanded) {
        const foldRow = el("div", { class: "bubble-expand-row " + (role === "user" ? "user" : "assistant") });
        const btn = el("button", {
          class: "btn textbtn bubble-expand-toggle",
          type: "button",
          text: "收起正文",
        });
        btn.addEventListener("click", toggleBubbleExpanded);
        foldRow.appendChild(btn);
        row.appendChild(foldRow);
      }

      if (attachments.length > 0 && (role === "user" || role === "assistant")) {
        const attachWrap = el("div", { class: "msg-attachments" });
        for (const att of attachments) {
          const src = resolveAttachmentUrl(att);
          if (!src) continue;
          if (isImageAttachment(att)) {
            const img = el("img", { class: "msg-img", src, alt: att.originalName || "attachment" });
            img.addEventListener("click", (e) => {
              e.stopPropagation();
              openImagePreview(src, att.originalName || "图片");
            });
            attachWrap.appendChild(img);
            continue;
          }
          const fileA = el("a", {
            class: "msg-file",
            href: src,
            target: "_blank",
            rel: "noopener noreferrer",
            title: String(att.originalName || att.filename || "附件"),
          });
          const ico = el("span", { class: "msg-file-ico", text: fileExtTag(att.originalName || att.filename || "") });
          const nm = el("span", { class: "msg-file-name", text: String(att.originalName || att.filename || "附件") });
          fileA.appendChild(ico);
          fileA.appendChild(nm);
          attachWrap.appendChild(fileA);
        }
        if (attachWrap.childNodes.length > 0) {
          enhanceMessageInteractiveObjects(attachWrap);
          row.appendChild(attachWrap);
        }
      }

      if (!foldable && !allowCopy && !allowReply) return;
      const ops = opts.opsContainer || el("div", { class: "bubbleops " + (role === "user" ? "user" : "assistant") });
      const useMiniOps = !!opts.opsContainer && !opts.keepOpsSize;
      if (allowReply) {
        const replyBtn = el("button", { class: "btn textbtn", text: "回复" });
        if (useMiniOps) replyBtn.classList.add("run-mini-btn");
        replyBtn.addEventListener("click", () => {
          try {
            opts.onReply({
              bubbleKey: String(bubbleKey || "").trim(),
              text: String(txt || fallback || ""),
            });
          } catch (_) {}
        });
        ops.appendChild(replyBtn);
      }
      if (allowCopy) {
        const copyBtn = el("button", { class: "btn textbtn", text: "复制全文" });
        if (useMiniOps) copyBtn.classList.add("run-mini-btn");
        copyBtn.addEventListener("click", () => {
          copyConversationBubbleText(role, content, fallback, opts);
        });
        ops.appendChild(copyBtn);
      }
      if (!opts.opsContainer && ops.childNodes.length > 0) row.appendChild(ops);
    }

    function renderConversationSystemFamily(payload = {}) {
      const rid = String(payload.rid || "");
      const r = payload.r || {};
      const runSpec = payload.runSpec || {};
      const displayUserText = String(payload.displayUserText || "");
      const userText = String(payload.userText || "");
      const replyContext = payload.replyContext || null;
      const callbackEventMeta = payload.callbackEventMeta || null;
      const callbackEventDuplicate = !!payload.callbackEventDuplicate;
      const restartRecoveryMeta = payload.restartRecoveryMeta || null;
      const restartRecoveryDuplicate = !!payload.restartRecoveryDuplicate;

      const systemRow = el("div", { class: "msgrow system" });
      systemRow.__conversationFileMeta = {
        runId: rid,
        createdAt: String(r.createdAt || ""),
        senderName: "系统主动回执",
        senderType: "system",
        messageKind: "system_callback",
        sourceRefText: String((runSpec && runSpec.sourceRefText) || ""),
        callbackToText: String((runSpec && runSpec.callbackToText) || ""),
      };

      const systemMeta = el("div", { class: "msgmeta msgmeta-system" });
      systemMeta.appendChild(el("span", { class: "msg-system-receipt-badge", text: "收到回执" }));
      if (r.createdAt) systemMeta.appendChild(el("span", { text: imTime(r.createdAt) }));
      systemRow.appendChild(systemMeta);

      if (callbackEventMeta) {
        systemRow.appendChild(renderCallbackEventCard(callbackEventMeta, {
          duplicate: callbackEventDuplicate,
          rawText: displayUserText || userText || String(r.messagePreview || ""),
          replyContext,
          onReply: ({ text }) => {
            queueConversationReply({
              runId: rid,
              bubbleKey: String(rid + ":system"),
              text: String(text || displayUserText || r.messagePreview || ""),
              senderLabel: "系统回执",
              timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
              createdAt: String(r.createdAt || ""),
            });
          },
        }));
      }

      if (restartRecoveryMeta) {
        systemRow.appendChild(renderRestartRecoveryCard(restartRecoveryMeta, {
          duplicate: restartRecoveryDuplicate,
          replyContext,
          rawText: displayUserText || userText || String(r.messagePreview || ""),
          runId: rid,
          runMeta: r,
          detailMeta: payload.d || null,
          onReply: ({ text }) => {
            queueConversationReply({
              runId: rid,
              bubbleKey: String(rid + ":system"),
              text: String(text || displayUserText || r.messagePreview || ""),
              senderLabel: "服务恢复",
              timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
              createdAt: String(r.createdAt || ""),
            });
          },
        }));
      }
      return systemRow;
    }

    function renderConversationUserFamily(payload = {}) {
      const rid = String(payload.rid || "");
      const r = payload.r || {};
      const d = payload.d || null;
      const senderRun = (payload.senderRun && typeof payload.senderRun === "object") ? payload.senderRun : {};
      const ctx = payload.ctx || {};
      const runSpec = payload.runSpec || {};
      const userSender = payload.userSender || null;
      const userMessageKind = String(payload.userMessageKind || "");
      const displayUserText = String(payload.displayUserText || "");
      const userText = String(payload.userText || "");
      const attachments = Array.isArray(payload.attachments) ? payload.attachments : [];
      const replyContext = payload.replyContext || null;
      const queuedCompactMode = !!payload.queuedCompactMode;
      const callbackEventMeta = payload.callbackEventMeta || null;
      const callbackEventDuplicate = !!payload.callbackEventDuplicate;
      const restartRecoveryMeta = payload.restartRecoveryMeta || null;
      const restartRecoveryDuplicate = !!payload.restartRecoveryDuplicate;
      const currentQueueDepth = Math.max(0, Number(payload.currentQueueDepth || 0));
      const aggregateCount = Math.max(0, Number(payload.aggregateCount || 0));
      const aggregateLastMergedAt = String(payload.aggregateLastMergedAt || "").trim();
      const actionBusy = String(payload.actionBusy || "");
      const userVisualMode = (payload.userVisualMode && typeof payload.userVisualMode === "object")
        ? payload.userVisualMode
        : resolveConversationUserVisualMode({
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

      const userRow = el("div", { class: "msgrow user" });
      userRow.classList.add(userVisualMode.kind);
      if (isAgentInbound) userRow.classList.add("agent-inbound");
      userRow.__conversationFileMeta = {
        runId: rid,
        createdAt: String(r.createdAt || ""),
        senderName: String(firstNonEmptyText([userSender && userSender.label, runSpec && runSpec.senderName]) || ""),
        senderType: String(firstNonEmptyText([userSender && userSender.type, runSpec && runSpec.senderType]) || ""),
        messageKind: userMessageKind,
        sourceRefText: String((runSpec && runSpec.sourceRefText) || ""),
        callbackToText: String((runSpec && runSpec.callbackToText) || ""),
      };

      const userMeta = el("div", { class: "msgmeta" });
      userMeta.appendChild(buildSenderChip(userSender));
      if ((userVisualMode.kind === "collab-inbound" || userVisualMode.kind === "receipt-inbound") && !isAgentInbound) {
        userMeta.appendChild(el("span", {
          class: "msg-collab-badge" + (userVisualMode.kind === "receipt-inbound" ? " receipt" : ""),
          text: userVisualMode.kind === "receipt-inbound" ? "收到回执" : "协作来信",
        }));
        const sourceLabel = String(userVisualMode.sourceChannel || "").trim();
        const senderLabel = String((userSender && userSender.label) || "").trim();
        if (sourceLabel && sourceLabel !== senderLabel) {
          userMeta.appendChild(el("span", { class: "msg-collab-source", text: "来自 " + sourceLabel }));
        }
      }
      if (queuedCompactMode) {
        userMeta.appendChild(el("span", { class: "msg-user-queued-badge", text: "排队中" }));
      }
      if (r.createdAt) userMeta.appendChild(el("span", { text: imTime(r.createdAt) }));
      userRow.appendChild(userMeta);

      let queuedInlineOps = null;
      let queuedInlineActions = null;
      if (queuedCompactMode) {
        queuedInlineOps = el("div", { class: "msg-user-queued-ops" });
        const queuedInlineMeta = el("div", { class: "msg-user-queued-meta" });
        if (currentQueueDepth > 0) {
          queuedInlineMeta.appendChild(chip("队列 " + String(currentQueueDepth), "muted"));
        }
        if (!callbackEventMeta && aggregateCount > 1) {
          const mergedChip = chip("已并入 " + String(aggregateCount) + " 条", "warn");
          if (aggregateLastMergedAt) {
            mergedChip.title = "最近并入: " + zhDateTime(aggregateLastMergedAt);
          }
          queuedInlineMeta.appendChild(mergedChip);
        }
        if (queuedInlineMeta.childNodes.length) queuedInlineOps.appendChild(queuedInlineMeta);
        queuedInlineActions = el("div", { class: "bubbleops user msg-user-queued-actions" });
        queuedInlineOps.appendChild(queuedInlineActions);
      }

      if (callbackEventMeta) {
        userRow.appendChild(renderCallbackEventCard(callbackEventMeta, {
          duplicate: callbackEventDuplicate,
          rawText: displayUserText || userText || String(r.messagePreview || ""),
          replyContext,
          onReply: ({ text }) => {
            queueConversationReply({
              runId: rid,
              bubbleKey: String(rid + ":user"),
              text: String(text || displayUserText || r.messagePreview || ""),
              senderLabel: String(firstNonEmptyText([userSender && userSender.label, "我"]) || "我"),
              timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
              createdAt: String(r.createdAt || ""),
            });
          },
        }));
        if (queuedCompactMode && queuedInlineActions) {
          const replyText = String(displayUserText || r.messagePreview || "").trim();
          if (replyText) {
            const replyBtn = el("button", { class: "btn textbtn", text: "回复" });
            replyBtn.addEventListener("click", () => {
              queueConversationReply({
                bubbleKey: String(rid + ":user"),
                text: replyText,
                senderLabel: String(firstNonEmptyText([userSender && userSender.label, "我"]) || "我"),
                timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
              });
            });
            queuedInlineActions.appendChild(replyBtn);
          }
        }
      }

      if (restartRecoveryMeta) {
        userRow.appendChild(renderRestartRecoveryCard(restartRecoveryMeta, {
          duplicate: restartRecoveryDuplicate,
          replyContext,
          rawText: displayUserText || userText || String(r.messagePreview || ""),
          runId: rid,
          runMeta: r,
          detailMeta: payload.d || null,
          onReply: ({ text }) => {
            queueConversationReply({
              runId: rid,
              bubbleKey: String(rid + ":user"),
              text: String(text || displayUserText || r.messagePreview || ""),
              senderLabel: String(firstNonEmptyText([userSender && userSender.label, "我"]) || "我"),
              timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
              createdAt: String(r.createdAt || ""),
            });
          },
        }));
      } else if (!callbackEventMeta) {
        if (userVisualMode.kind === "receipt-inbound") {
          userRow.appendChild(renderConversationInboundReceiptCard(userVisualMode, {
            runId: rid,
            rawTextComplete: !!(d && d.full && typeof d.full.message === "string"),
            sourceAgentName: String(firstNonEmptyText([userSender && userSender.label, runSpec && runSpec.senderName]) || ""),
            sourceChannel: String(userVisualMode.sourceChannel || ""),
            rawText: displayUserText || userText || String(r.messagePreview || ""),
            onReply: ({ text }) => {
              queueConversationReply({
                runId: rid,
                bubbleKey: String(rid + ":user"),
                text: String(text || displayUserText || userText || r.messagePreview || ""),
                senderLabel: String(firstNonEmptyText([userSender && userSender.label, "我"]) || "我"),
                timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
                createdAt: String(r.createdAt || ""),
              });
            },
          }));
        } else if (isAgentInbound) {
          userRow.appendChild(renderConversationInboundAgentCard(userVisualMode, {
            runId: rid,
            rawText: displayUserText || userText || String(r.messagePreview || ""),
            rawTextComplete: !!(d && d.full && typeof d.full.message === "string"),
            sourceAgentName: String(firstNonEmptyText([userSender && userSender.label, runSpec && runSpec.senderName]) || ""),
            sourceChannel: String(userVisualMode.sourceChannel || ""),
            onReply: ({ text }) => {
              queueConversationReply({
                runId: rid,
                bubbleKey: String(rid + ":agent-inline"),
                text: String(text || displayUserText || userText || ""),
                senderLabel: String(firstNonEmptyText([userSender && userSender.label, "我"]) || "我"),
                timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
                createdAt: String(r.createdAt || ""),
              });
            },
          }));
        } else if (userVisualMode.kind === "collab-inbound" && (userVisualMode.currentConclusion || userVisualMode.nextAction)) {
          const summaryCard = el("div", { class: "msg-collab-summary" });
          if (userVisualMode.currentConclusion) {
            summaryCard.appendChild(el("div", {
              class: "msg-collab-summary-main",
              text: userVisualMode.currentConclusion,
            }));
          }
          if (userVisualMode.nextAction) {
            summaryCard.appendChild(el("div", {
              class: "msg-collab-summary-sub",
              text: userVisualMode.nextAction,
            }));
          }
          userRow.appendChild(summaryCard);
        }
        if (userVisualMode.kind !== "receipt-inbound" && !isAgentInbound) {
          appendConversationBubble(userRow, "user", displayUserText || "", "(空消息)", rid + ":user", {
            runId: rid,
            forceDetailOnExpand: !(d && d.full && typeof d.full.message === "string") && !!String(r.messagePreview || "").trim(),
            attachments,
            bubbleClass: userVisualMode.kind === "collab-inbound" ? "collab-raw" : "",
            opsContainer: queuedInlineActions || undefined,
            keepOpsSize: queuedCompactMode,
            replyContext,
            onReply: ({ bubbleKey, text }) => {
              queueConversationReply({
                runId: rid,
                bubbleKey: String(bubbleKey || rid + ":user"),
                text: String(text || displayUserText || ""),
                senderLabel: String(firstNonEmptyText([userSender && userSender.label, "我"]) || "我"),
                timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
                createdAt: String(r.createdAt || ""),
              });
            },
          });
        }
      }

      if (queuedCompactMode && queuedInlineActions) {
        const cancelBtn = el("button", { class: "btn textbtn", text: actionBusy === "cancel_edit" ? "撤回中..." : "撤回编辑" });
        cancelBtn.disabled = !!actionBusy;
        cancelBtn.addEventListener("click", async () => {
          if (cancelBtn.disabled) return;
          cancelBtn.disabled = true;
          try { await cancelQueuedRunForEdit(r); } finally { cancelBtn.disabled = false; }
        });
        queuedInlineActions.appendChild(cancelBtn);
        const forwardPayload = normalizeQueuedForwardPayload({
          runId: rid,
          sourceSessionId: String(ctx.sessionId || ""),
          sourceChannelName: String(ctx.channelName || ""),
          sourceDisplayName: firstNonEmptyText([
            userSender && userSender.label,
            ctx.displayChannel,
            ctx.alias,
            ctx.channelName,
          ]),
          sourceCliType: String(ctx.cliType || ""),
          message: String(displayUserText || r.messagePreview || "").trim(),
        });
        if (forwardPayload && bindQueuedForwardDragSource(queuedInlineOps, forwardPayload)) {
          const dragHint = el("button", { class: "btn textbtn", text: "拖拽转发" });
          dragHint.disabled = true;
          dragHint.title = "拖拽到左侧目标会话后确认转发";
          queuedInlineActions.appendChild(dragHint);
        }
        if (queuedInlineOps.childNodes.length) userRow.appendChild(queuedInlineOps);
      }

      const mentionTargets = Array.isArray(payload.mentionTargets) ? payload.mentionTargets : collectRunMentionTargets(r, d, userText);
      const mentionRow = renderMentionTargetsRow(mentionTargets);
      if (mentionRow) userRow.appendChild(mentionRow);
      return userRow;
    }

    function renderConversationAssistantFamily(payload = {}) {
      const rid = String(payload.rid || "");
      const r = payload.r || {};
      const d = payload.d || null;
      const ctx = payload.ctx || {};
      const runSpec = payload.runSpec || {};
      const st = String(payload.st || "idle");
      const timeoutLike = !!payload.timeoutLike;
      const actionBusy = String(payload.actionBusy || "");
      const assistantSender = payload.assistantSender || null;
      const assistantMessageKind = String(payload.assistantMessageKind || "");
      const assistantText = String(payload.assistantText || "");
      const displayAssistantText = String(payload.displayAssistantText || "");
      const displayUserText = String(payload.displayUserText || "");
      const err = String(payload.err || "").trim();
      const hint = String(payload.hint || "").trim();
      const callbackEventMeta = payload.callbackEventMeta || null;
      const restartRecoveryMeta = payload.restartRecoveryMeta || null;
      const receiptProjection = payload.receiptProjection || null;
      const currentActiveRunId = String(payload.currentActiveRunId || "").trim();
      const currentQueuedRunId = String(payload.currentQueuedRunId || "").trim();
      const attachments = mergeConversationAttachmentLists([
        payload.attachments,
        d && d.full && d.full.run && d.full.run.attachments,
        d && d.run && d.run.attachments,
        r && r.attachments,
      ]);
      const visibleGeneratedAttachments = filterConversationBubbleAttachments("assistant", attachments);
      const generatedMediaSummary = String(firstNonEmptyText([
        d && d.run && d.run.generated_media_summary,
        d && d.full && d.full.run && d.full.run.generated_media_summary,
        r && r.generated_media_summary,
      ]) || "").trim();
      const generatedMediaCount = firstConversationGeneratedMediaCount([
        d && d.run && d.run.generated_media_count,
        d && d.full && d.full.run && d.full.run.generated_media_count,
        r && r.generated_media_count,
      ]);
      const generatedMediaFallback = (generatedMediaCount > 0 && !visibleGeneratedAttachments.length)
        ? renderConversationGeneratedMediaCard({
            count: generatedMediaCount,
            summary: generatedMediaSummary,
            openUrl: firstConversationGeneratedMediaAttachmentUrl(attachments),
          })
        : null;
      const staleErrorWithActiveRun = st === "error" && currentActiveRunId && currentActiveRunId !== rid;
      const staleErrorWithQueuedRun = st === "error" && !staleErrorWithActiveRun && currentQueuedRunId && currentQueuedRunId !== rid;
      const staleErrorNote = staleErrorWithActiveRun
        ? ("上一条 run 已失败；当前活跃 run " + shortId(currentActiveRunId) + " 仍在执行")
        : (staleErrorWithQueuedRun
          ? "上一条 run 已失败；当前会话仍有排队消息待执行"
          : "");

      const aiRow = el("div", { class: "msgrow assistant" });
      aiRow.__conversationFileMeta = {
        runId: rid,
        createdAt: String(r.createdAt || ""),
        senderName: String(firstNonEmptyText([assistantSender && assistantSender.label, runSpec && runSpec.senderName]) || ""),
        senderType: String(firstNonEmptyText([assistantSender && assistantSender.type, runSpec && runSpec.senderType]) || ""),
        messageKind: assistantMessageKind,
        sourceRefText: String((runSpec && runSpec.sourceRefText) || ""),
        callbackToText: String((runSpec && runSpec.callbackToText) || ""),
      };

      const aiMeta = el("div", { class: "msgmeta" });
      aiMeta.appendChild(buildSenderChip(assistantSender));
      if (r.createdAt) aiMeta.appendChild(el("span", { text: imTime(r.createdAt) }));
      aiRow.appendChild(aiMeta);

      const processInfo = collectRunProcessInfo(rid, st, r, d);
      const processState = ensureRunProcessUi(rid, st);
      const processExpanded = !!(processState && processState.expanded);
      const debugExpanded = PCONV.debugExpanded.has(rid);
      const activeDetailTab = getRunDetailDrawerTab(rid, { debugExpanded });
      const detailDrawerOpen = processExpanded || debugExpanded;
      const processDetailLagging = Number(processInfo.reportedCount || 0) > Number(processInfo.items.length || 0);
      // 只在用户真的展开“过程/调试”抽屉时再补拉详情。
      // 历史 run 若仅存在过程条数缺口，继续显示聚合计数即可，避免进入
      // “detail 返回 -> 整体重渲 -> 再次 force 拉 detail”的循环，导致选中会话后
      // 页面长时间抖动、点击看起来失效。
      if (detailDrawerOpen && (!d || !d.loading)) {
        ensureConversationRunDetail(rid, {
          force: processDetailLagging,
          maxAgeMs: 1200,
          terminalSyncStatus: isRunWorking(st) ? "" : String(st || "").toLowerCase(),
        });
      }

      const assistantBubbleText = String(displayAssistantText || "").trim();
      const noVisibleAssistantOutput = !assistantBubbleText && Number(processInfo.count || 0) <= 0 && !err;
      const assistantBodyPlaceholder = (st === "done" && noVisibleAssistantOutput)
        ? ((visibleGeneratedAttachments.length > 0 || generatedMediaFallback)
            ? "本轮执行已完成，结果见下方图片结果。"
            : "本轮执行已完成，但未生成可展示正文。")
        : "";
      const assistantDetailFull = d && d.full ? d.full : null;
      const assistantDetailState = assistantDetailFull ? deriveRunStateFromSource(assistantDetailFull.run, "") : "";
      const assistantDetailWorking = !!assistantDetailState && isWorkingLikeState(assistantDetailState);
      const assistantHasTerminalDetailText = !!String((assistantDetailFull && assistantDetailFull.lastMessage) || "").trim();
      const assistantHasProgressDetailText = !!String((assistantDetailFull && assistantDetailFull.partialMessage) || "").trim()
        || !!((Array.isArray(assistantDetailFull && assistantDetailFull.agentMessages) ? assistantDetailFull.agentMessages : [])
          .some((item) => String(item || "").trim()));
      const assistantNeedsDetailOnExpand = !!assistantBubbleText
        && !assistantBodyPlaceholder
        && (!assistantDetailFull
          || (isRunWorking(st)
            ? !assistantHasProgressDetailText && !assistantHasTerminalDetailText
            : assistantDetailWorking || (!assistantHasTerminalDetailText && !assistantHasProgressDetailText)));
      const showAssistantBodyCard = (!!assistantBubbleText && !isRunWorking(st)) || !!assistantBodyPlaceholder;
      let bodyCard = null;
      if (showAssistantBodyCard) {
        const isPlaceholderOnly = !assistantBubbleText && !!assistantBodyPlaceholder;
        bodyCard = el("div", { class: "msg-body-card assistant" + (isPlaceholderOnly ? " is-placeholder" : "") });
        const bodyHead = el("div", { class: "msg-body-head" });
        bodyHead.appendChild(el("div", { class: "msg-body-title", text: "正文" }));
        const bodyOps = el("div", { class: "bubbleops assistant msg-body-ops" });
        bodyHead.appendChild(bodyOps);
        bodyCard.appendChild(bodyHead);
        appendConversationBubble(
          bodyCard,
          "assistant",
          assistantBubbleText,
          assistantBodyPlaceholder || "(暂无回复)",
          rid + ":assistant",
          {
            runId: rid,
            forceDetailOnExpand: assistantNeedsDetailOnExpand,
            bubbleClass: isPlaceholderOnly ? "is-placeholder" : "",
            attachments: visibleGeneratedAttachments,
            opsContainer: bodyOps,
            keepOpsSize: true,
            onReply: assistantBubbleText ? ({ bubbleKey, text }) => {
              queueConversationReply({
                runId: rid,
                bubbleKey: String(bubbleKey || (rid + ":assistant")),
                text: String(text || assistantBubbleText || ""),
                senderLabel: String(firstNonEmptyText([assistantSender && assistantSender.label, "通道输出"]) || "通道输出"),
                timeLabel: compactDateTime(r.createdAt) || imTime(r.createdAt) || "",
                createdAt: String(r.createdAt || ""),
              });
            } : null,
          }
        );
      }

      const outcomeMeta = buildRunOutcomeMeta(r, d);
      const stateBar = el("div", {
        class: "run-statebar " + runStateClass(st || "idle", {
          outcomeState: outcomeMeta && outcomeMeta.outcomeState,
        }),
      });
      const stateMain = el("div", { class: "run-state-main" });
      stateMain.appendChild(el("div", {
        class: "run-state-label",
        text: runStateHeadline(st || "idle", {
          timeout: timeoutLike,
          outcomeState: outcomeMeta && outcomeMeta.outcomeState,
        }),
      }));
      const waitingText = retryWaitingRemainText(r);
      const queueReasonText = String(payload.queueReasonText || "").trim();
      const blockedByText = String(payload.blockedByText || "").trim();
      const queuedHint = (st === "queued")
        ? firstNonEmptyText([
            queueReasonText ? ("排队原因: " + queueReasonText) : "",
            blockedByText ? ("被阻塞于 run " + blockedByText) : "",
          ])
        : "";
      const stateSubText = waitingText
        ? waitingText
        : queuedHint
          ? (blockedByText && queueReasonText
              ? ("排队原因: " + queueReasonText + " · 阻塞run: " + blockedByText)
              : queuedHint)
        : (outcomeMeta && outcomeMeta.subtitle && !isRunWorking(st)
            ? outcomeMeta.subtitle
        : (st === "error"
            ? (staleErrorNote || "可查看错误并继续处理")
            : (st === "interrupted"
                ? "可查看过程并继续收口"
                : (st === "done"
                    ? (processInfo.count > 0
                        ? "可查看正文与过程"
                        : (assistantBubbleText ? "可查看正文" : "执行已完成，未生成正文"))
                    : (isRunWorking(st)
                        ? (noVisibleAssistantOutput ? "已启动，等待正文或过程输出" : "过程实时更新")
                        : (processInfo.count > 0 ? "可查看执行过程" : "暂无过程轨迹"))))));
      stateMain.appendChild(el("div", { class: "run-state-sub", text: stateSubText }));
      if (staleErrorNote) {
        stateMain.appendChild(el("div", {
          class: "run-state-note",
          text: staleErrorNote,
          title: staleErrorNote,
        }));
      }
      stateBar.appendChild(stateMain);

      const stateActions = el("div", { class: "run-state-actions" });
      if (st === "queued" && !callbackEventMeta && !restartRecoveryMeta) {
        const forwardPayload = normalizeQueuedForwardPayload({
          runId: rid,
          sourceSessionId: String(ctx.sessionId || ""),
          sourceChannelName: String(ctx.channelName || ""),
          sourceDisplayName: firstNonEmptyText([
            assistantSender && assistantSender.label,
            ctx.displayChannel,
            ctx.alias,
            ctx.channelName,
          ]),
          sourceCliType: String(ctx.cliType || ""),
          message: String(displayUserText || r.messagePreview || "").trim(),
        });
        if (forwardPayload) {
          bindQueuedForwardDragSource(stateBar, forwardPayload);
          const dragHint = el("button", { class: "btn textbtn", text: "拖拽转发" });
          dragHint.disabled = true;
          dragHint.title = "拖拽到左侧目标会话后确认转发";
          stateActions.appendChild(dragHint);
        }
      }
      const processBtn = el("button", {
        class: "btn textbtn",
        text: (detailDrawerOpen && activeDetailTab === "process")
          ? "收起过程"
          : (processInfo.count > 0 ? ("过程 " + processInfo.count) : "展开过程"),
      });
      processBtn.addEventListener("click", () => {
        if (detailDrawerOpen && activeDetailTab === "process") {
          toggleRunProcessUi(rid, st);
          setRunDetailDrawerTab(rid, "process");
        } else {
          openRunDetailDrawer(rid, st, "process");
          if (!PCONV.detailMap[rid]) ensureConversationRunDetail(rid);
        }
        renderConversationDetail();
      });
      stateActions.appendChild(processBtn);

      let stopBtn = null;
      if (st === "retry_waiting") {
        const cancelRetryBtn = el("button", { class: "btn textbtn", text: actionBusy === "cancel_retry" ? "取消中..." : "取消重试" });
        cancelRetryBtn.disabled = !!actionBusy;
        cancelRetryBtn.addEventListener("click", async () => {
          if (cancelRetryBtn.disabled) return;
          cancelRetryBtn.disabled = true;
          try { await cancelRetryWaitingRun(r); } finally { cancelRetryBtn.disabled = false; }
        });
        stateActions.appendChild(cancelRetryBtn);
      }
      if (st === "running") {
        stopBtn = el("button", { class: "btn textbtn run-action-danger", text: actionBusy === "interrupt" ? "打断中..." : "打断执行" });
        stopBtn.disabled = !!actionBusy;
        stopBtn.addEventListener("click", async () => {
          if (stopBtn.disabled) return;
          stopBtn.disabled = true;
          try { await interruptRunningRun(r); } finally { stopBtn.disabled = false; }
        });
      }

      const dbgBtn = el("button", {
        class: "btn textbtn",
        text: (detailDrawerOpen && activeDetailTab === "debug") ? "收起调试" : "展开调试",
      });
      dbgBtn.addEventListener("click", () => {
        if (detailDrawerOpen && activeDetailTab === "debug") {
          PCONV.debugExpanded.delete(rid);
          setRunDetailDrawerTab(rid, "debug");
          renderConversationDetail();
        } else {
          openRunDetailDrawer(rid, st, "debug");
          ensureConversationRunDetail(rid);
          renderConversationDetail();
        }
      });
      stateActions.appendChild(dbgBtn);
      if (stopBtn) stateActions.appendChild(stopBtn);

      const allowRecoveryOps = st === "error" || (st === "interrupted" && outcomeMeta && outcomeMeta.outcomeState === "interrupted_infra");
      if (allowRecoveryOps) {
        const recoverBtn = el("button", { class: "btn textbtn", text: "回收结果" });
        recoverBtn.addEventListener("click", async () => {
          recoverBtn.disabled = true;
          try { await recoverRun(r); } finally { recoverBtn.disabled = false; }
        });
        stateActions.appendChild(recoverBtn);

        const retryBtn = el("button", { class: "btn textbtn", text: "重试" });
        retryBtn.addEventListener("click", async () => {
          retryBtn.disabled = true;
          try { await retryRun(r); } finally { retryBtn.disabled = false; }
        });
        stateActions.appendChild(retryBtn);
      }

      stateBar.appendChild(stateActions);
      aiRow.appendChild(stateBar);

      if (detailDrawerOpen) {
        const detailDrawer = el("div", { class: "run-detail-drawer" });
        const drawerHead = el("div", { class: "run-detail-head" });
        drawerHead.appendChild(el("div", {
          class: "run-detail-title",
          text: activeDetailTab === "debug" ? "运行细节 · 调试" : "运行细节 · 过程",
        }));
        const drawerTabs = el("div", { class: "run-detail-tabs" });
        const processTabBtn = el("button", {
          class: "btn textbtn" + (activeDetailTab === "process" ? " active" : ""),
          text: processInfo.count > 0 ? ("过程 " + processInfo.count) : "过程",
        });
        processTabBtn.addEventListener("click", () => {
          openRunDetailDrawer(rid, st, "process");
          if (!PCONV.detailMap[rid]) ensureConversationRunDetail(rid);
          renderConversationDetail();
        });
        drawerTabs.appendChild(processTabBtn);
        const debugTabBtn = el("button", {
          class: "btn textbtn" + (activeDetailTab === "debug" ? " active" : ""),
          text: "调试",
        });
        debugTabBtn.addEventListener("click", () => {
          openRunDetailDrawer(rid, st, "debug");
          ensureConversationRunDetail(rid);
          renderConversationDetail();
        });
        drawerTabs.appendChild(debugTabBtn);
        drawerHead.appendChild(drawerTabs);
        detailDrawer.appendChild(drawerHead);

        if (activeDetailTab === "debug") {
          if (!d || d.loading) {
            detailDrawer.appendChild(el("div", { class: "hint", text: "加载调试日志中..." }));
          } else if (d.error) {
            detailDrawer.appendChild(el("div", { class: "hint", text: "调试日志加载失败: " + d.error }));
          } else if (d.full) {
            detailDrawer.appendChild(renderDebugPanel(d.full, { runId: rid }));
          }
        } else {
          const processPanel = el("div", { class: "process-panel show embedded" });
          const meta = el("div", { class: "chips process-meta", style: "justify-content:flex-start; gap:6px" });
          meta.appendChild(chip("过程 " + Math.max(processInfo.count, processInfo.items.length) + " 条", "muted"));
          const drawerStateSourceChip = buildRunDisplayStateSourceChip(r, d, { hideNormal: true });
          if (drawerStateSourceChip) meta.appendChild(drawerStateSourceChip);
          if (outcomeMeta) meta.appendChild(chip(outcomeMeta.label, outcomeMeta.tone));
          const drawerExecContext = (
            (d && d.full && d.full.run && d.full.run.project_execution_context)
            || (r && (r.project_execution_context || r.projectExecutionContext))
            || null
          );
          const drawerExecMeta = buildProjectExecutionContextMeta(drawerExecContext);
          if (drawerExecMeta && drawerExecMeta.available && (drawerExecMeta.overrideApplied || String((drawerExecMeta.sourceMeta && drawerExecMeta.sourceMeta.key) || "") !== "project")) {
            const drawerExecSourceChip = buildProjectExecutionContextCompactChip(drawerExecContext, { showMissing: false });
            if (drawerExecSourceChip) meta.appendChild(drawerExecSourceChip);
          }
          if (!isRunWorking(st) && processInfo.latestProgressAt) {
            const latestProgressText = compactDateTime(processInfo.latestProgressAt) || shortDateTime(processInfo.latestProgressAt);
            meta.appendChild(chip("最近进展 " + latestProgressText, "muted"));
          }
          if (isRunWorking(st) && processInfo.latestProgressAt && isProgressStale(processInfo.latestProgressAt)) {
            meta.appendChild(chip("超过5分钟无进展", "bad"));
          } else if (isRunWorking(st) && !processInfo.latestProgressAt) {
            meta.appendChild(chip("进展待同步", "warn"));
          }
          if (d && d.loading) meta.appendChild(chip("同步中", "warn"));
          processPanel.appendChild(meta);

          if (processInfo.items.length > 0) {
            const list = el("div", { class: "process-list" });
            const processRows = Array.isArray(processInfo.rows)
              ? processInfo.rows
              : (Array.isArray(processInfo.items) ? processInfo.items.map((txt) => ({ text: String(txt || ""), at: extractProcessItemTimestamp(txt) })) : []);
            processRows.forEach((row, idx) => {
              const txt = String((row && row.text) || "");
              const itemTs = String((row && row.at) || "").trim() || extractProcessItemTimestamp(txt);
              const rowNode = el("div", { class: "process-item" + (itemTs ? "" : " no-time") });
              rowNode.appendChild(el("span", { class: "process-idx", text: String(idx + 1) }));
              rowNode.appendChild(el("span", { class: "process-txt", text: txt }));
              if (itemTs) {
                rowNode.appendChild(el("span", {
                  class: "process-time",
                  text: compactDateTime(itemTs),
                  title: zhDateTime(itemTs),
                }));
              }
              list.appendChild(rowNode);
            });
            processPanel.appendChild(list);
          } else if (d && d.loading) {
            processPanel.appendChild(el("div", { class: "hint process-empty", text: "过程轨迹同步中..." }));
          } else {
            processPanel.appendChild(el("div", { class: "hint process-empty", text: "当前 run 暂无可回放的过程消息。" }));
          }
          detailDrawer.appendChild(processPanel);
        }
        aiRow.appendChild(detailDrawer);
      }

      if (bodyCard) aiRow.appendChild(bodyCard);
      if (generatedMediaFallback) aiRow.appendChild(generatedMediaFallback);
      const receiptStack = renderConversationReceiptStack({
        runId: rid,
        projection: receiptProjection,
      });
      if (receiptStack) aiRow.appendChild(receiptStack);
      if (st === "error" || (st === "interrupted" && outcomeMeta && outcomeMeta.outcomeState === "interrupted_infra")) {
        aiRow.appendChild(el("div", {
          class: "merr",
          text: outcomeMeta && outcomeMeta.outcomeState === "interrupted_infra"
            ? ("环境中断: " + (err || "执行被基础设施中断，可继续回收结果或重试"))
            : (staleErrorNote
                ? ("上一条 run 失败: " + (err || "执行失败（未返回具体错误文本）"))
                : ("error: " + (err || "执行失败（未返回具体错误文本）"))),
        }));
        if (hint) aiRow.appendChild(el("div", { class: "hint", text: hint }));
      }

      const mentionTargets = Array.isArray(payload.mentionTargets) ? payload.mentionTargets : [];
      const runAgentRefs = filterRunAgentRefsAgainstMentions(
        collectRunAgentRefs(r, d, displayUserText, displayAssistantText, processInfo, ctx.sessionId),
        mentionTargets
      );
      const agentRow = renderAgentRefsRow(rid, runAgentRefs);
      const skillRow = renderSkillsRow(rid, collectRunSkills(r, d, displayAssistantText, processInfo));
      const businessRow = renderBusinessRefsRow(rid, collectRunBusinessRefs(r, d, displayAssistantText, processInfo));
      if (agentRow || skillRow || businessRow) {
        const objectLayer = el("div", { class: "msg-object-layer" });
        if (agentRow) objectLayer.appendChild(agentRow);
        if (skillRow) objectLayer.appendChild(skillRow);
        if (businessRow) objectLayer.appendChild(businessRow);
        aiRow.appendChild(objectLayer);
      }
      return aiRow;
    }

    function renderConversationOptimisticUserFamily(payload = {}) {
      const ctx = payload.ctx || {};
      const m = payload.message || {};
      const userRow = el("div", { class: "msgrow user" });
      userRow.classList.add("self-user");
      const userMeta = el("div", { class: "msgmeta" });
      const optimisticUserSender = resolveMessageSender({}, {
        role: "user",
        cliType: String((ctx && ctx.cliType) || "codex"),
        channelName: String((ctx && ctx.channelName) || ""),
        displayChannel: String((ctx && ctx.displayChannel) || ""),
        textCandidates: [m && m.message],
      });
      userRow.__conversationFileMeta = {
        runId: "",
        createdAt: String(m.createdAt || ""),
        senderName: String(firstNonEmptyText([optimisticUserSender && optimisticUserSender.label, "我"]) || "我"),
        senderType: String(firstNonEmptyText([optimisticUserSender && optimisticUserSender.type, "user"]) || "user"),
        messageKind: "manual_update",
        sourceRefText: "",
        callbackToText: "",
      };
      userMeta.appendChild(buildSenderChip(optimisticUserSender));
      userMeta.appendChild(el("span", { class: "msg-user-queued-badge", text: "排队中" }));
      userMeta.appendChild(el("span", { text: imTime(m.createdAt || "") }));
      userRow.appendChild(userMeta);
      const optimisticAttachments = Array.isArray(m.attachments) ? m.attachments : [];
      appendConversationBubble(userRow, "user", m.message || "", "", "optimistic:user", {
        attachments: optimisticAttachments,
        replyContext: normalizeConvReplyContext(m.replyContext),
        onReply: ({ bubbleKey, text }) => {
          queueConversationReply({
            bubbleKey: String(bubbleKey || "optimistic:user"),
            text: String(text || m.message || ""),
            senderLabel: String(firstNonEmptyText([optimisticUserSender && optimisticUserSender.label, "我"]) || "我"),
            timeLabel: compactDateTime(m.createdAt) || imTime(m.createdAt) || "",
            createdAt: String(m.createdAt || ""),
          });
        },
      });
      const optimisticMentionTargets = collectRunMentionTargets({}, null, m.message || "", m.mentionTargets || []);
      const optimisticMentionRow = renderMentionTargetsRow(optimisticMentionTargets);
      if (optimisticMentionRow) userRow.appendChild(optimisticMentionRow);
      return userRow;
    }
