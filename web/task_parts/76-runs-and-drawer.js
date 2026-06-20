    function isTerminalTextCli(cliType) {
      const normalized = String(cliType || "").trim().toLowerCase();
      return normalized === "claude" || normalized === "opencode" || normalized === "codebuddy";
    }

    const CODEBUDDY_RAW_CONTEXT_HIDDEN_TEXT = "CodeBuddy 返回了原始结构化上下文，已隐藏；请查看运行详情或等待修复后重跑。";

    function codeBuddyRawContextTextHasMarker(text) {
      const raw = String(text || "");
      if (!raw.trim()) return false;
      if (/system-reminder/i.test(raw)) return true;
      if (/data-role\s*=\s*["']memory["']/i.test(raw)) return true;
      if (/\brawContent\b|\braw_content\b/i.test(raw)) return true;
      if (/\binput_text\b/i.test(raw)) return true;
      if (/"role"\s*:\s*"user"/i.test(raw) || /\brole\s*=\s*user\b/i.test(raw)) return true;
      if (/"role"\s*:\s*"system"/i.test(raw) || /\brole\s*=\s*system\b/i.test(raw)) return true;
      return /\bmemory\b/i.test(raw) && (/[<>{}\[\]]/.test(raw) || /"role"\s*:|data-role|input_text|rawContent/i.test(raw));
    }

    function codeBuddyRawJsonHasContextShape(value, depth = 0) {
      if (depth > 6 || value == null) return false;
      if (typeof value === "string") return codeBuddyRawContextTextHasMarker(value);
      if (Array.isArray(value)) {
        return value.slice(0, 80).some((item) => codeBuddyRawJsonHasContextShape(item, depth + 1));
      }
      if (typeof value !== "object") return false;
      const keys = Object.keys(value);
      const lowerKeys = keys.map((key) => String(key || "").toLowerCase());
      if (lowerKeys.includes("rawcontent") || lowerKeys.includes("raw_content") || lowerKeys.includes("input_text")) return true;
      const role = String(value.role || "").trim().toLowerCase();
      if ((role === "user" || role === "system") && (value.content !== undefined || value.parts !== undefined || value.text !== undefined)) return true;
      const type = String(value.type || value.item_type || value.itemType || "").trim().toLowerCase();
      if (type === "input_text" || type === "system-reminder" || type === "system_reminder") return true;
      if (String(value["data-role"] || value.dataRole || "").trim().toLowerCase() === "memory") return true;
      return keys.slice(0, 80).some((key) => codeBuddyRawJsonHasContextShape(value[key], depth + 1));
    }

    function isCodeBuddyRawContextLeakText(text) {
      const raw = String(text || "");
      const trimmed = raw.trim();
      if (!trimmed) return false;
      if (codeBuddyRawContextTextHasMarker(trimmed)) return true;
      if (!/^[\[{]/.test(trimmed)) return false;
      if (trimmed.length <= 200000) {
        try {
          return codeBuddyRawJsonHasContextShape(JSON.parse(trimmed));
        } catch (_) {
          // Fall through to the cheap marker check for truncated JSON-like text.
        }
      }
      return /"role"\s*:|"content"\s*:|"type"\s*:|\binput_text\b|\brawContent\b|\braw_content\b|system-reminder|\bmemory\b/i.test(trimmed);
    }

    function isCodeBuddyRunMeta(run, detail, ctx = {}) {
      const detailFull = detail && detail.full ? detail.full : null;
      const detailRun = (detailFull && detailFull.run)
        || (detail && detail.run)
        || null;
      const values = [
        ctx && ctx.cliType,
        ctx && ctx.cli_type,
        run && run.cliType,
        run && run.cli_type,
        detail && detail.cliType,
        detail && detail.cli_type,
        detailRun && detailRun.cliType,
        detailRun && detailRun.cli_type,
      ];
      return values.some((value) => String(value || "").trim().toLowerCase() === "codebuddy");
    }

    function codeBuddySafeRunId(runId, run, detail) {
      const detailFull = detail && detail.full ? detail.full : null;
      const detailRun = (detailFull && detailFull.run)
        || (detail && detail.run)
        || null;
      return String(
        runId
        || (run && run.id)
        || (run && run.run_id)
        || (detailRun && detailRun.id)
        || (detailRun && detailRun.run_id)
        || ""
      ).trim();
    }

    function safeCodeBuddyTextForDisplay(text, runId = "", run = null, detail = null, ctx = {}) {
      const raw = String(text || "");
      if (!raw.trim()) return raw;
      if (!isCodeBuddyRunMeta(run, detail, ctx)) return raw;
      if (!isCodeBuddyRawContextLeakText(raw)) return raw;
      const safeRunId = codeBuddySafeRunId(runId, run, detail);
      return CODEBUDDY_RAW_CONTEXT_HIDDEN_TEXT + (safeRunId ? ("\nrun_id: " + safeRunId) : "");
    }

    function renderRuns(runs) {
      const box = document.getElementById("ccbRuns");
      CCB.runs = Array.isArray(runs) ? runs.slice() : [];
      box.innerHTML = "";
      if (!runs || !runs.length) {
        box.appendChild(el("div", { class: "hint", text: "暂无回溯记录（从这里发送一条消息开始）。" }));
        return;
      }
      for (const r of runs.slice(0, 20)) {
        const detailMeta = CCB.detailMap[String((r && r.id) || "")] || null;
        const row = el("div", { class: "runrow" });
        const top = el("div", { class: "top" });
        top.appendChild(el("div", { class: "id", text: (r.createdAt || "") + " · " + (r.id || "") }));
        const st = String(r.status || "");
        const runDisplayState = getRunDisplayState(r, detailMeta);
        const outcomeMeta = buildRunOutcomeMeta(r, detailMeta);
        const cliType = String(r.cliType || r.cli_type || "").trim().toLowerCase();
        const suppressTerminalTextLegacyPreview = isTerminalTextCli(cliType);
        const chipState = String(runDisplayState || st || "").trim();
        top.appendChild(chip(chipState, chipState === "done" ? "good" : (chipState === "error" || chipState === "interrupted" ? "bad" : "warn")));
        row.appendChild(top);
        const metaBar = el("div", { class: "run-context-meta" });
        const stateSourceChip = buildRunDisplayStateSourceChip(r, detailMeta);
        if (stateSourceChip) metaBar.appendChild(stateSourceChip);
        if (outcomeMeta) metaBar.appendChild(chip(outcomeMeta.label, outcomeMeta.tone));
        const execSourceChip = buildProjectExecutionContextCompactChip(
          (detailMeta && detailMeta.full && detailMeta.full.run && detailMeta.full.run.project_execution_context)
          || (r && (r.project_execution_context || r.projectExecutionContext))
          || null,
          { showMissing: false }
        );
        if (execSourceChip) metaBar.appendChild(execSourceChip);
        if (metaBar.childNodes.length) row.appendChild(metaBar);
        const msg = String(safeCodeBuddyTextForDisplay(r.messagePreview || "", r.id, r, detailMeta, { cliType }) || "").trim();
        if (msg) row.appendChild(el("div", { class: "msg", text: "msg: " + msg }));
        const err = String(r.error || "").trim();
        if (runDisplayState === "error") {
          row.appendChild(el("div", { class: "err", text: runErrorDisplayText(err, outcomeMeta) }));
          const eh = String(r.errorHint || "").trim();
          if (eh) row.appendChild(el("div", { class: "hint", text: eh }));
        } else if (outcomeMeta && outcomeMeta.subtitle && (runDisplayState === "interrupted" || runDisplayState === "done")) {
          row.appendChild(el("div", { class: "hint", text: outcomeMeta.subtitle }));
        }
        const partial = suppressTerminalTextLegacyPreview ? "" : String(r.partialPreview || "").trim();
        if (partial) {
          const pv = el("div", { class: "partial md" });
          setMarkdown(pv, partial);
          row.appendChild(pv);
        }
        const amCount = suppressTerminalTextLegacyPreview ? 0 : Number(r.agentMessagesCount || 0);
        if (amCount > 0) row.appendChild(el("div", { class: "hint", text: "已回捞过程消息 " + amCount + " 条" }));
        const last = String(safeCodeBuddyTextForDisplay(r.lastPreview || "", r.id, r, detailMeta, { cliType }) || "");
        if (last) {
          const lv = el("div", { class: "last reply" });
          setMarkdown(lv, last);
          row.appendChild(lv);
        }
        const log = String(r.logPreview || "").trim();
        if (log) {
          const stLabel = (st === "queued" || st === "running" || st === "retry_waiting") ? "process" : "log";
          row.appendChild(el("div", { class: "last", text: stLabel + ":\n" + log }));
        } else if (runDisplayState === "error") {
          row.appendChild(el("div", { class: "hint", text: "未采集到过程日志（可能是任务启动后进程提前退出，或该记录产生于旧版本服务）。" }));
        }
        const btns = el("div", { class: "chips", style: "justify-content:flex-end; gap:8px" });
        if (st === "retry_waiting") {
          const cancelRetryBtn = el("button", { class: "btn", text: "取消重试" });
          cancelRetryBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            cancelRetryBtn.disabled = true;
            try {
              await callRunAction(r.id, "cancel_retry");
              await refreshCCB();
            } finally {
              cancelRetryBtn.disabled = false;
            }
          });
          btns.appendChild(cancelRetryBtn);
        }
        const allowRecoveryOps = st === "error" || (runDisplayState === "interrupted" && outcomeMeta && outcomeMeta.outcomeState === "interrupted_infra");
        if (allowRecoveryOps) {
          const providerRecovery = !!(outcomeMeta && outcomeMeta.providerTransient);
          const recoverBtn = el("button", { class: "btn", text: providerRecovery ? "补链恢复" : "回收结果" });
          recoverBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            recoverBtn.disabled = true;
            try {
              await recoverRun(r);
            } finally {
              recoverBtn.disabled = false;
            }
          });
          btns.appendChild(recoverBtn);
          if (!providerRecovery) {
            const retryBtn = el("button", { class: "btn", text: "重试" });
            retryBtn.addEventListener("click", async (e) => {
              e.stopPropagation();
              retryBtn.disabled = true;
              try {
                await retryRun(r);
              } finally {
                retryBtn.disabled = false;
              }
            });
            btns.appendChild(retryBtn);
          }
        }
        const isExpanded = CCB.expanded.has(String(r.id || ""));
        const b = el("button", { class: "btn", text: isExpanded ? "收起" : "展开" });
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          const rid = String(r.id || "");
          if (!rid) return;
          if (CCB.expanded.has(rid)) collapseRun(rid);
          else ensureRunExpanded(rid);
        });
        btns.appendChild(b);
        row.appendChild(btns);

        if (isExpanded) {
          const d = CCB.detailMap[String(r.id || "")] || {
            loading: true,
            full: null,
            message: "",
            process: "",
            last: "",
            partial: "",
            errorHint: "",
            agentMessages: [],
            status: "",
            startedAt: "",
            finishedAt: "",
            runError: "",
            error: "",
          };
          if (d.loading) {
            row.appendChild(el("div", { class: "hint", text: "加载详细过程中…" }));
          } else if (d.error) {
            row.appendChild(el("div", { class: "hint", text: "加载失败: " + d.error }));
          } else {
            const detailExecRows = buildProjectExecutionContextDetailRows(
              d && d.full && d.full.run ? d.full.run.project_execution_context : null,
              { showMissing: false }
            );
            detailExecRows.forEach((node) => row.appendChild(node));
            const metaText = "status: " + String(d.status || "") +
              (d.startedAt ? ("\nstarted: " + String(d.startedAt)) : "") +
              (d.finishedAt ? ("\nfinished: " + String(d.finishedAt)) : "");
            const errFull = String(d.runError || "").trim();
            const processText = String(d.process || "");
            let fullText = "meta:\n" + metaText + "\n\n";
            const eh = String(d.errorHint || "").trim();
            if (eh) fullText += "hint:\n" + eh + "\n\n";
            if (errFull) fullText += "error:\n" + errFull + "\n\n";
            const partialFull = String(d.partial || "").trim();
            if (partialFull) fullText += "partial:\n" + partialFull + "\n\n";
            const am = Array.isArray(d.agentMessages) ? d.agentMessages : [];
            if (am.length) fullText += "agent_messages:\n- " + am.join("\n- ") + "\n\n";
            const detailMsg = safeCodeBuddyTextForDisplay(d.message || "", r.id, r, d, { cliType });
            const detailLast = safeCodeBuddyTextForDisplay(d.last || "", r.id, r, d, { cliType });
            fullText += "msg:\n" + String(detailMsg || "") + "\n\nprocess:\n" + processText + "\n\nlast:\n" + String(detailLast || "");
            row.appendChild(el("div", { class: "last", text: fullText }));
          }
        }
        box.appendChild(row);
      }
    }

    function getRunDisplayStateSourceMeta(run, detail) {
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : null;
      const runState = deriveRunStateFromSource(run, "");
      const detailState = deriveRunStateFromSource(detailRun, "");
      const preferDetail = detailRun ? shouldPreferDetailSnapshot(run, detailRun, detail) : false;
      const detailInterrupted = isRunInterruptedByUser(detailRun);
      const runInterrupted = isRunInterruptedByUser(run);
      const outcomeState = getRunOutcomeState(run, detail);
      if (outcomeState === "success" || runInterrupted || runState === "done" || runState === "error") {
        return {
          text: "状态来源: 时间线",
          tone: "good",
          title: "主状态使用 runs 列表返回的终态快照",
        };
      }
      if (
        outcomeState === "interrupted_user"
        || outcomeState === "failed_config"
        || outcomeState === "failed_business"
        || outcomeState === "provider_transient_failed"
      ) {
        return {
          text: "状态来源: 时间线",
          tone: "good",
          title: "主状态使用 runs 列表返回的结果分类",
        };
      }
      if ((isWorkingLikeState(detailState) || detailInterrupted || detailState === "done" || detailState === "error") && preferDetail) {
        return {
          text: "状态来源: 详情纠偏",
          tone: "warn",
          title: "主状态由 run detail 的更新快照纠正旧的时间线状态",
        };
      }
      if (isWorkingLikeState(runState)) {
        return {
          text: "状态来源: 时间线",
          tone: "good",
          title: "主状态直接使用 runs 列表快照",
        };
      }
      if (runInterrupted || runState === "done" || runState === "error") {
        return {
          text: "状态来源: 时间线",
          tone: "good",
          title: "主状态使用 runs 列表返回的终态快照",
        };
      }
      if (detailRun && (isWorkingLikeState(detailState) || detailInterrupted || detailState === "done" || detailState === "error")) {
        return {
          text: "状态来源: 详情",
          tone: "info",
          title: "主状态使用 run detail 返回的状态",
        };
      }
      return {
        text: "状态来源: 合成",
        tone: "muted",
        title: "主状态由前端合成口径决定",
      };
    }

    function buildRunDisplayStateSourceChip(run, detail, opts = {}) {
      const meta = getRunDisplayStateSourceMeta(run, detail);
      if (!meta || !meta.text) return null;
      const hideNormal = !!(opts && opts.hideNormal);
      if (hideNormal && (String(meta.tone || "") === "good" || String(meta.tone || "") === "info")) return null;
      return el("span", {
        class: "conv-subchip exec-source " + String(meta.tone || "muted"),
        text: meta.text,
        title: String(meta.title || meta.text || ""),
      });
    }

    function configuredPrimarySessionEntry(project, channelName) {
      const ch = String(channelName || "").trim();
      if (!project || !ch) return null;
      const isVisible = (row) => {
        if (!row || typeof row !== "object") return false;
        if (typeof isVisibleConversationSession === "function") {
          return isVisibleConversationSession(row);
        }
        const deleted = typeof isDeletedSession === "function"
          ? isDeletedSession(row)
          : boolLike(row.is_deleted || row.isDeleted);
        const inactive = typeof isInactiveSession === "function"
          ? isInactiveSession(row)
          : String(row.status || row.session_status || row.sessionStatus || "").trim().toLowerCase() === "inactive";
        return !deleted && !inactive;
      };
      const isPrimaryCandidate = (row) => {
        if (!row || typeof row !== "object" || !isVisible(row)) return false;
        if (boolLike(row.is_primary || row.isPrimary)) return true;
        const role = String(row.session_role || row.sessionRole || "").trim().toLowerCase();
        return role === "main" || role === "primary" || role === "主会话";
      };
      const registryChannels = Array.isArray(project.registry && project.registry.channels)
        ? project.registry.channels
        : [];
      const registryHit = registryChannels.find((x) => String((x && (x.channel_name || x.name)) || "").trim() === ch);
      const registrySid = String((registryHit && registryHit.primary_session_id) || "").trim();
      if (looksLikeSessionId(registrySid)) {
        return {
          name: ch,
          session_id: registrySid,
          alias: String((registryHit && registryHit.primary_session_alias) || ""),
          cli_type: String((registryHit && registryHit.primary_cli_type) || "codex"),
          source: "registry_primary",
          is_primary: true,
          session_role: "primary",
        };
      }
      const fromChannelSessions = (Array.isArray(project.channel_sessions) ? project.channel_sessions : [])
        .find((x) => isPrimaryCandidate(x) && String((x && x.name) || "").trim() === ch);
      if (fromChannelSessions) return fromChannelSessions;
      return (Array.isArray(project.channels) ? project.channels : [])
        .find((x) => String((x && x.name) || "").trim() === ch) || null;
    }

    function configuredProjectConversations(projectId) {
      const proj = projectById(projectId);
      const names = unionChannelNames(projectId);
      const list = [];
      for (const n of names) {
        const primaryCfg = configuredPrimarySessionEntry(proj, n);
        const primarySid = String((primaryCfg && primaryCfg.session_id) || "").trim();
        if (looksLikeSessionId(primarySid)) {
          list.push({
            ...primaryCfg,
            name: String((primaryCfg && primaryCfg.name) || n),
            alias: String((primaryCfg && primaryCfg.alias) || ""),
            session_id: primarySid,
            cli_type: String((primaryCfg && (primaryCfg.cli_type || primaryCfg.cliType)) || "codex"),
            model: normalizeSessionModel(primaryCfg && primaryCfg.model),
            source: "config-primary",
            is_primary: true,
          });
        }
        const s = sessionForChannel(projectId, n);
        if (s) list.push(s);
      }
      const map = new Map();
      for (const s of list) {
        if (typeof isVisibleConversationSession === "function" && !isVisibleConversationSession(s)) continue;
        const sid = String((s && s.session_id) || "").trim();
        if (!looksLikeSessionId(sid)) continue;
        const ch = String((s && s.name) || "").trim();
        const alias = String((s && s.alias) || "").trim();
        const cliType = String((s && s.cli_type) || "codex").trim() || "codex";
        const primaryCfg = configuredPrimarySessionEntry(proj, ch);
        const primarySid = String((primaryCfg && primaryCfg.session_id) || "").trim();
        const isPrimary = looksLikeSessionId(primarySid) ? (primarySid === sid) : boolLike(s && s.is_primary);
        let it = map.get(sid);
        if (!it) {
          it = {
            sessionId: sid,
            alias: alias || ch || sid,
            channels: [],
            primaryChannel: ch || "",
            displayChannel: ch || alias || sid,
            lastActiveAt: "",
            lastStatus: "idle",
            lastPreview: "",
            lastTimeout: false,
            lastError: "",
            lastErrorHint: "",
            lastSpeaker: "assistant",
            lastSenderType: "legacy",
            lastSenderName: "",
            lastSenderSource: "legacy",
            runCount: 0,
            cli_type: cliType,
            is_primary: !!isPrimary,
            source: String((s && s.source) || ""),
          };
          map.set(sid, it);
        }
        if (ch && !it.channels.includes(ch)) it.channels.push(ch);
        if (!it.primaryChannel && ch) it.primaryChannel = ch;
        if (!it.displayChannel && ch) it.displayChannel = ch;
        if (!it.alias && alias) it.alias = alias;
        if (!it.cli_type && cliType) it.cli_type = cliType;
        if (isPrimary) it.is_primary = true;
      }
      return Array.from(map.values());
    }

    function findConversationSessionById(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return null;
      const sessions = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
      return sessions.find((x) => String((x && (x.sessionId || x.id)) || "") === sid) || null;
    }

    function findPrimaryConversationSession(channelName) {
      const ch = String(channelName || "").trim();
      if (!ch) return null;
      const sessions = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
      const inChannel = sessions.filter((x) => sessionMatchesChannel(x, ch));
      if (!inChannel.length) return null;
      return inChannel.find((x) => isPrimarySession(x)) || null;
    }

    function pickDefaultConversationSessionId(sessions, channelName) {
      const list = (Array.isArray(sessions) ? sessions : []).filter((x) => !isDeletedSession(x));
      if (!list.length) return "";
      const ch = String(channelName || "").trim();
      if (ch) {
        const inChannel = list.filter((x) => sessionMatchesChannel(x, ch));
        if (inChannel.length) {
          const primary = inChannel.find((x) => isPrimarySession(x));
          if (primary) return getSessionId(primary);
          return getSessionId(inChannel[0]);
        }
      }
      const primaryAny = list.find((x) => isPrimarySession(x));
      if (primaryAny) return getSessionId(primaryAny);
      return getSessionId(list[0]);
    }

    function setChannelConversationManageError(msg) {
      CHANNEL_CONV_MGMT_UI.error = String(msg || "").trim();
      const errEl = document.getElementById("channelConvManageErr");
      if (!errEl) return;
      errEl.textContent = CHANNEL_CONV_MGMT_UI.error;
      errEl.style.display = CHANNEL_CONV_MGMT_UI.error ? "block" : "none";
    }

    function closeChannelConversationManageModal() {
      CHANNEL_CONV_MGMT_UI.open = false;
      CHANNEL_CONV_MGMT_UI.loading = false;
      CHANNEL_CONV_MGMT_UI.saving = false;
      CHANNEL_CONV_MGMT_UI.projectId = "";
      CHANNEL_CONV_MGMT_UI.channelName = "";
      CHANNEL_CONV_MGMT_UI.sessions = [];
      CHANNEL_CONV_MGMT_UI.primarySessionId = "";
      CHANNEL_CONV_MGMT_UI.error = "";
      const mask = document.getElementById("channelConvManageMask");
      if (mask) mask.style.display = "none";
      setChannelConversationManageError("");
    }

    function resolveChannelConversationManagePrimaryId(sessions, projectId, channelName) {
      const list = (Array.isArray(sessions) ? sessions : []).filter((s) => !isDeletedSession(s));
      const explicit = list.find((s) => boolLike(s.is_primary));
      if (explicit) return String(getSessionId(explicit) || "").trim();
      const proj = projectById(projectId);
      const primaryCfg = configuredPrimarySessionEntry(proj, channelName);
      const configSid = String((primaryCfg && primaryCfg.session_id) || "").trim();
      if (configSid && list.some((s) => String(getSessionId(s) || "").trim() === configSid)) return configSid;
      const active = list.find((s) => String(s.status || "active").trim().toLowerCase() === "active");
      if (active) return String(getSessionId(active) || "").trim();
      return list.length ? String(getSessionId(list[0]) || "").trim() : "";
    }

    function syncChannelConversationManagePrimaryFallback() {
      const sessions = Array.isArray(CHANNEL_CONV_MGMT_UI.sessions) ? CHANNEL_CONV_MGMT_UI.sessions : [];
      const current = String(CHANNEL_CONV_MGMT_UI.primarySessionId || "").trim();
      if (current && sessions.some((s) => !isDeletedSession(s) && String(getSessionId(s) || "").trim() === current)) return;
      CHANNEL_CONV_MGMT_UI.primarySessionId = resolveChannelConversationManagePrimaryId(
        sessions,
        CHANNEL_CONV_MGMT_UI.projectId,
        CHANNEL_CONV_MGMT_UI.channelName
      );
    }

    function renderChannelConversationManageModal() {
      const body = document.getElementById("channelConvManageBody");
      const hintEl = document.getElementById("channelConvManageHint");
      const saveBtn = document.getElementById("channelConvManageSaveBtn");
      if (!body || !hintEl || !saveBtn) return;
      clearNodeChildren(body);
      saveBtn.disabled = !CHANNEL_CONV_MGMT_UI.open || CHANNEL_CONV_MGMT_UI.loading || CHANNEL_CONV_MGMT_UI.saving;
      hintEl.textContent = CHANNEL_CONV_MGMT_UI.loading
        ? "正在加载当前通道对话…"
        : "每个通道仅允许一个主对话；标记删除不会清除历史消息，只会从默认展示与路由中移除。";
      if (CHANNEL_CONV_MGMT_UI.loading) {
        body.appendChild(el("div", { class: "channel-conv-manage-empty", text: "正在加载…" }));
        return;
      }
      const sessions = Array.isArray(CHANNEL_CONV_MGMT_UI.sessions) ? CHANNEL_CONV_MGMT_UI.sessions.slice() : [];
      if (!sessions.length) {
        body.appendChild(el("div", { class: "channel-conv-manage-empty", text: "当前通道暂无可管理对话。" }));
        return;
      }
      const head = el("div", { class: "channel-conv-manage-head" });
      head.appendChild(el("div", { class: "channel-conv-manage-meta", text: "通道：" + String(CHANNEL_CONV_MGMT_UI.channelName || "-") }));
      head.appendChild(el("div", { class: "channel-conv-manage-meta", text: "对话数：" + String(sessions.length) }));
      body.appendChild(head);
      const list = el("div", { class: "channel-conv-manage-list" });
      sessions.sort((a, b) => conversationSortTime(b) - conversationSortTime(a));
      sessions.forEach((session) => {
        const sid = String(getSessionId(session) || "").trim();
        if (!sid) return;
        const deleted = isDeletedSession(session);
        const row = el("div", { class: "channel-conv-manage-row" + (deleted ? " is-deleted" : "") });
        const radio = el("input", { class: "channel-conv-manage-radio" });
        radio.type = "radio";
        radio.name = "channelConvManagePrimary";
        radio.checked = !deleted && sid === String(CHANNEL_CONV_MGMT_UI.primarySessionId || "").trim();
        radio.disabled = deleted || CHANNEL_CONV_MGMT_UI.saving;
        radio.addEventListener("change", () => {
          CHANNEL_CONV_MGMT_UI.primarySessionId = sid;
          renderChannelConversationManageModal();
        });
        row.appendChild(radio);

        const main = el("div", { class: "channel-conv-manage-main" });
        const title = el("div", { class: "channel-conv-manage-title" });
        title.appendChild(el("div", { class: "channel-conv-manage-name", text: conversationAgentName(session) }));
        title.appendChild(chip(conversationCliBadgeText(session.cli_type || "codex"), "muted"));
        title.appendChild(chip(deleted ? "已标记删除" : (sid === String(CHANNEL_CONV_MGMT_UI.primarySessionId || "").trim() ? "主对话" : "子对话"), deleted ? "bad" : (sid === String(CHANNEL_CONV_MGMT_UI.primarySessionId || "").trim() ? "good" : "muted")));
        title.appendChild(statusChip(getSessionStatus(session)));
        main.appendChild(title);
        const subParts = [
          "会话ID " + shortId(sid),
          session.last_used_at ? ("最近使用 " + compactDateTime(session.last_used_at)) : "",
          session.deleted_at ? ("删除于 " + compactDateTime(session.deleted_at)) : "",
        ].filter(Boolean);
        main.appendChild(el("div", { class: "channel-conv-manage-sub" }));
        main.lastChild.textContent = subParts.join(" · ");
        row.appendChild(main);

        const actions = el("div", { class: "channel-conv-manage-actions" });
        const toggleBtn = el("button", {
          class: "btn",
          text: deleted ? "恢复" : "标记删除",
        });
        toggleBtn.disabled = !!CHANNEL_CONV_MGMT_UI.saving;
        toggleBtn.addEventListener("click", (e) => {
          e.preventDefault();
          const nextSessions = sessions.map((it) => {
            const itSid = String(getSessionId(it) || "").trim();
            if (itSid !== sid) return it;
            const nextDeleted = !deleted;
            return {
              ...it,
              is_deleted: nextDeleted,
              deleted_at: nextDeleted ? new Date().toISOString() : "",
              deleted_reason: nextDeleted ? "channel_conversation_manage" : "",
              is_primary: nextDeleted ? false : boolLike(it.is_primary),
            };
          });
          CHANNEL_CONV_MGMT_UI.sessions = nextSessions;
          syncChannelConversationManagePrimaryFallback();
          renderChannelConversationManageModal();
        });
        actions.appendChild(toggleBtn);
        row.appendChild(actions);
        list.appendChild(row);
      });
      body.appendChild(list);
    }

    async function loadChannelConversationManageData(projectId, channelName) {
      const params = new URLSearchParams({
        project_id: String(projectId || "").trim(),
        channel_name: String(channelName || "").trim(),
        include_deleted: "1",
      });
      const resp = await fetch("/api/channel-sessions?" + params.toString(), { headers: authHeaders() });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      const payload = await resp.json();
      const sessions = Array.isArray(payload && payload.sessions)
        ? payload.sessions.map((s) => normalizeConversationSession(s)).filter(Boolean)
        : [];
      CHANNEL_CONV_MGMT_UI.sessions = sessions;
      CHANNEL_CONV_MGMT_UI.primarySessionId = resolveChannelConversationManagePrimaryId(
        sessions,
        projectId,
        channelName
      );
      setChannelConversationManageError("");
      renderChannelConversationManageModal();
      return payload;
    }

    async function openChannelConversationManageModal(projectId, channelName) {
      const pid = String(projectId || STATE.project || "").trim();
      const ch = String(channelName || STATE.channel || "").trim();
      if (!pid || pid === "overview" || !ch) return;
      const mask = document.getElementById("channelConvManageMask");
      if (!mask) return;
      CHANNEL_CONV_MGMT_UI.open = true;
      CHANNEL_CONV_MGMT_UI.loading = true;
      CHANNEL_CONV_MGMT_UI.saving = false;
      CHANNEL_CONV_MGMT_UI.projectId = pid;
      CHANNEL_CONV_MGMT_UI.channelName = ch;
      CHANNEL_CONV_MGMT_UI.sessions = [];
      CHANNEL_CONV_MGMT_UI.primarySessionId = "";
      setChannelConversationManageError("");
      mask.style.display = "flex";
      renderChannelConversationManageModal();
      try {
        await loadChannelConversationManageData(pid, ch);
      } catch (err) {
        setChannelConversationManageError(err && err.message ? String(err.message) : "加载失败");
      } finally {
        CHANNEL_CONV_MGMT_UI.loading = false;
        renderChannelConversationManageModal();
      }
    }

    async function saveChannelConversationManageModal() {
      if (!CHANNEL_CONV_MGMT_UI.open || CHANNEL_CONV_MGMT_UI.saving) return;
      const pid = String(CHANNEL_CONV_MGMT_UI.projectId || "").trim();
      const channelName = String(CHANNEL_CONV_MGMT_UI.channelName || "").trim();
      if (!pid || !channelName) return;
      const sessions = Array.isArray(CHANNEL_CONV_MGMT_UI.sessions) ? CHANNEL_CONV_MGMT_UI.sessions.slice() : [];
      syncChannelConversationManagePrimaryFallback();
      const primarySessionId = String(CHANNEL_CONV_MGMT_UI.primarySessionId || "").trim();
      CHANNEL_CONV_MGMT_UI.saving = true;
      setChannelConversationManageError("");
      renderChannelConversationManageModal();
      try {
        const updates = sessions.map((session) => ({
          session_id: String(getSessionId(session) || "").trim(),
          is_deleted: isDeletedSession(session),
          deleted_reason: isDeletedSession(session)
            ? String(session.deleted_reason || "channel_conversation_manage").trim()
            : "",
        })).filter((it) => it.session_id);
        const resp = await fetch("/api/channel-sessions/manage", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            project_id: pid,
            channel_name: channelName,
            primary_session_id: primarySessionId,
            updates,
          }),
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        await resp.json();
        await refreshConversationPanel();
        const channelSessions = conversationSessionsForChannel(channelName, pid);
        const selectedSid = String(STATE.selectedSessionId || "").trim();
        if (selectedSid && !channelSessions.some((s) => String(getSessionId(s) || "").trim() === selectedSid)) {
          STATE.selectedSessionId = pickDefaultConversationSessionId(channelSessions, channelName);
          STATE.selectedSessionExplicit = false;
        }
        setHintText(STATE.panelMode, "通道对话管理已保存。");
        closeChannelConversationManageModal();
        render();
      } catch (err) {
        setChannelConversationManageError(err && err.message ? String(err.message) : "保存失败");
      } finally {
        CHANNEL_CONV_MGMT_UI.saving = false;
        renderChannelConversationManageModal();
      }
    }

    function buildConversationChannelManageMenu(projectId, channelName) {
      const channel = String(channelName || "").trim();
      if (!channel) return null;
      const pid = String(projectId || STATE.project || "").trim();
      const menu = el("div", {
        class: "channel-row-menu conv-channel-manage-menu",
        "data-channel-name": channel,
        role: "menu",
        "aria-label": "通道操作",
      });
      const appendMenuItem = (title, desc, onClick, danger = false) => {
        if (typeof buildChannelManageMenuItem === "function") {
          menu.appendChild(buildChannelManageMenuItem(title, desc, onClick, danger));
          return;
        }
        const btn = el("button", {
          class: "channel-row-menu-item" + (danger ? " danger" : ""),
          type: "button",
        });
        btn.appendChild(el("div", { class: "channel-row-menu-item-title", text: title }));
        btn.appendChild(el("div", { class: "channel-row-menu-item-desc", text: desc }));
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          onClick && onClick();
        });
        menu.appendChild(btn);
      };
      appendMenuItem(
        "编辑 AGENTS.md",
        "配置这个通道的长期协作规则",
        () => typeof openChannelAgentsMdModal === "function" && openChannelAgentsMdModal(pid, channel),
      );
      appendMenuItem(
        "找 Agent 编辑",
        "把通道说明与边界整理成正式派发消息",
        () => typeof openChannelEditAgentModal === "function" && openChannelEditAgentModal(pid, channel),
      );
      appendMenuItem(
        "删除通道",
        "删除通道目录与配套文件夹，保留 运行历史记录 历史",
        () => typeof openChannelDeleteModal === "function" && openChannelDeleteModal(pid, channel),
        true,
      );
      return menu;
    }

    function buildConversationLeftList() {
      if (typeof isTaskShareModeActive === "function" && isTaskShareModeActive()) {
        renderTaskShareModeLeftList();
        return;
      }
      const left = document.getElementById("leftList");
      const asideTitle = document.getElementById("asideTitle");
      const asideMeta = document.getElementById("asideMeta");
      const layoutTabs = document.getElementById("convLayoutTabs");
      if (!left || !asideTitle || !asideMeta) return;
      if (typeof closeChannelManageMenus === "function") closeChannelManageMenus();
      const scrollBox = (typeof conversationListScrollBox === "function")
        ? conversationListScrollBox()
        : (left.closest(".aside-scroll") || left);
      const currentScrollTop = Math.max(0, Number((scrollBox && scrollBox.scrollTop) || 0) || 0);
      const storedScrollTop = (typeof readConversationListStoredScrollTop === "function")
        ? readConversationListStoredScrollTop(String(STATE.project || ""), normalizeConversationListLayout(STATE && STATE.convListLayout))
        : 0;
      const prevScrollTop = currentScrollTop > 0 ? currentScrollTop : storedScrollTop;
      const restoreLeftScroll = () => {
        if (!(prevScrollTop > 0)) return;
        if (typeof restoreConversationListScrollTop === "function") {
          restoreConversationListScrollTop(
            prevScrollTop,
            String(STATE.project || ""),
            normalizeConversationListLayout(STATE && STATE.convListLayout)
          );
          return;
        }
        requestAnimationFrame(() => {
          const currentLeft = document.getElementById("leftList");
          if (!currentLeft) return;
          const currentScrollBox = currentLeft.closest(".aside-scroll") || currentLeft;
          const maxScrollTop = Math.max(0, Number(currentScrollBox.scrollHeight || 0) - Number(currentScrollBox.clientHeight || 0));
          currentScrollBox.scrollTop = Math.min(prevScrollTop, maxScrollTop);
        });
      };
      const commitLeftChildren = (fragment, { preserveScroll = true } = {}) => {
        left.replaceChildren(fragment);
        if (preserveScroll) restoreLeftScroll();
      };
      asideTitle.textContent = "对话";
      const currentLayout = normalizeConversationListLayout(STATE && STATE.convListLayout);
      if (layoutTabs) {
        layoutTabs.style.display = "";
        const buttons = Array.from(layoutTabs.querySelectorAll("[data-conv-layout]"));
        buttons.forEach((btn) => {
          const mode = normalizeConversationListLayout(btn.getAttribute("data-conv-layout") || "flat");
          const active = mode === currentLayout;
          btn.classList.toggle("active", active);
          btn.setAttribute("aria-selected", active ? "true" : "false");
        });
      }

      if (STATE.project === "overview") {
        asideMeta.innerHTML = "";
        asideMeta.appendChild(metaPill("请选择具体项目", "warn"));
        const overviewFragment = document.createDocumentFragment();
        overviewFragment.appendChild(el("div", { class: "hint", text: "总揽模式下不展示会话，请先选择具体项目。" }));
        commitLeftChildren(overviewFragment, { preserveScroll: false });
        return;
      }

      const projectId = String(STATE.project || "").trim();
      const sessions = sortedConversationSessions(conversationSessionsForProject(projectId));
      const channelNameSet = new Set(unionChannelNames(projectId));
      sessions.forEach((session) => {
        const channelName = String(getSessionChannelName(session) || "").trim();
        if (channelName) channelNameSet.add(channelName);
      });
      const channelNames = Array.from(channelNameSet).filter(Boolean).sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
      const activeRuns = sessions.filter((s) => {
        const st = String(getSessionStatus(s) || "").trim().toLowerCase();
        return st === "queued" || st === "running" || st === "retry_waiting" || st === "external_busy";
      }).length;

      asideMeta.innerHTML = "";
      asideMeta.appendChild(metaPill("通道 " + channelNames.length, "muted"));
      asideMeta.appendChild(metaPill("会话 " + sessions.length, "muted"));
      asideMeta.appendChild(metaPill("运行 " + activeRuns, activeRuns > 0 ? "warn" : "good"));
      asideMeta.appendChild(metaPill("刷新 " + (PCONV.lastRefreshAt || "-"), "muted"));
      const sortWrap = el("span", { class: "conv-sort-inline" });
      sortWrap.appendChild(el("span", { class: "conv-sort-label", text: "排序" }));
      const sortSel = el("select", { class: "conv-sort-select", "aria-label": "会话排序" });
      const currentSort = normalizeConversationSort(STATE && STATE.convSort);
      for (const opt of CONV_SORT_OPTIONS) {
        const node = el("option", { value: opt.value, text: opt.label });
        if (opt.value === currentSort) node.selected = true;
        sortSel.appendChild(node);
      }
      sortSel.addEventListener("change", () => setConversationSort(sortSel.value));
      sortWrap.appendChild(sortSel);
      asideMeta.appendChild(sortWrap);

      const leftFragment = document.createDocumentFragment();
      if (!channelNames.length) {
        leftFragment.appendChild(el("div", { class: "hint", text: "当前项目没有可用通道，请先新增通道。" }));
        commitLeftChildren(leftFragment, { preserveScroll: false });
        return;
      }

      const appendSessionRow = (session, containerNode) => {
        const sid = getSessionId(session);
        const row = buildConversationRow(session, STATE.selectedSessionId === sid, (nextSid) => {
          setSelectedSessionId(nextSid, true, { explicit: true });
          closeDrawerOnMobile();
        }, { showCountDots: true, projectId });
        containerNode.appendChild(row);
      };

      if (currentLayout === "flat") {
        sessions.forEach((session) => appendSessionRow(session, leftFragment));
        commitLeftChildren(leftFragment);
        return;
      }

      const buildTextAction = (text, title, onClick, extraClass = "") => {
        const btn = el("button", {
          class: "conv-channel-action-btn" + (extraClass ? (" " + extraClass) : ""),
          type: "button",
          text,
          title,
          "aria-label": title || text,
        });
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          onClick && onClick(e);
        });
        return btn;
      };

      channelNames.forEach((channelName) => {
        const channelSessions = conversationSessionsForChannel(channelName, projectId);
        const sessionCount = channelSessions.length;
        const box = el("section", { class: "conv-channel-group" });
        const head = el("div", { class: "conv-channel-group-head" });
        head.appendChild(el("div", {
          class: "conv-channel-group-title",
          text: channelName,
          title: channelName,
        }));

        const headSide = el("div", { class: "channel-row-tools conv-channel-group-side" });
        const actionWrap = el("div", { class: "conv-channel-group-actions" });
        actionWrap.appendChild(buildTextAction(
          "+对话",
          "在“" + channelName + "”中新增对话",
          () => typeof openNewConvModal === "function" && openNewConvModal(projectId, channelName),
        ));
        actionWrap.appendChild(buildTextAction(
          "管理对话",
          "管理“" + channelName + "”下的对话",
          () => typeof openChannelConversationManageModal === "function" && openChannelConversationManageModal(projectId, channelName),
        ));
        const manageBtn = buildTextAction(
          "编辑通道",
          "管理“" + channelName + "”的现有能力",
          () => typeof toggleChannelManageMenu === "function" && toggleChannelManageMenu(channelName),
          "channel-row-menu-trigger"
        );
        manageBtn.setAttribute("data-channel-name", channelName);
        manageBtn.setAttribute("aria-haspopup", "menu");
        manageBtn.setAttribute("aria-expanded", "false");
        actionWrap.appendChild(manageBtn);
        headSide.appendChild(actionWrap);
        headSide.appendChild(el("span", {
          class: "conv-channel-group-count",
          text: "会话 " + sessionCount,
          title: "当前通道会话数量",
        }));
        const manageMenu = buildConversationChannelManageMenu(projectId, channelName);
        if (manageMenu) headSide.appendChild(manageMenu);
        head.appendChild(headSide);
        box.appendChild(head);

        const listNode = el("div", { class: "conv-channel-group-list" });
        if (channelSessions.length) {
          channelSessions.forEach((session) => appendSessionRow(session, listNode));
        } else {
          listNode.appendChild(el("div", {
            class: "conv-channel-empty",
            text: "暂无对话",
            title: "当前通道暂无对话，可从右侧“+对话”开始新增",
          }));
        }
        box.appendChild(listNode);
        leftFragment.appendChild(box);
      });
      commitLeftChildren(leftFragment);
    }

    // 在主列表区域渲染会话列表（供移动端对话模式使用）
    function buildConversationMainList(container) {
      if (typeof isTaskShareModeActive === "function" && isTaskShareModeActive()) {
        renderTaskShareModeMainList(container);
        return;
      }
      if (!container) return;
      container.innerHTML = "";
      if (!isMobileViewport()) return;

      if (STATE.project === "overview") {
        container.appendChild(el("div", { class: "hint", text: "总揽模式下不展示会话，请先选择具体项目。" }));
        return;
      }

      const sessions = sortedConversationSessions(PCONV.sessions);
      if (!sessions.length) {
        container.appendChild(el("div", { class: "hint", text: "当前项目没有可用会话（请先在配置里维护 session_id 或新增对话）。" }));
        return;
      }

      for (const s of sessions) {
        const sid = String(s.sessionId || s.id || "");
        const agentName = conversationAgentName(s);
        const mainTitle = agentName || "未命名会话";
        const displayTitle = typeof agentDisplayTooltip === "function"
          ? agentDisplayTooltip(s, mainTitle)
          : mainTitle;
        const previewText = String(conversationPreviewLine(s) || "").trim() || "暂无消息记录";
        const secondaryParts = conversationSecondaryMeta(s);
        const heatMeta = conversationHeatMeta(s);
        const statusMeta = conversationStatusMeta(s);
        const statusBadge = buildConversationStatusBadge(s);
        const auxBadges = typeof buildConversationAuxStatusBadges === "function"
          ? buildConversationAuxStatusBadges(s)
          : null;
        const countBadges = buildConversationCountBadges(s, { projectId: STATE.project, showUnread: false });
        const row = el("div", {
          class: "frow conv-main-row"
            + (STATE.selectedSessionId === sid ? " active" : "")
            + (heatMeta && heatMeta.tier ? (" is-heat-" + String(heatMeta.tier || "")) : "")
            + (statusMeta && statusMeta.tone ? (" is-status-" + String(statusMeta.tone || "")) : ""),
        });
        row.appendChild(buildConversationAvatarNode(s));
        const body = el("div", { class: "conv-main-card" });
        const head = el("div", { class: "conv-card-head" });
        const titleWrap = el("div", { class: "conv-card-titlewrap" });
        const titleRow = el("div", { class: "conv-title" });
        titleRow.appendChild(el("div", { class: "conv-name", text: mainTitle, title: displayTitle }));
        titleWrap.appendChild(titleRow);
        const envBadge = buildConversationEnvironmentBadge(s, { compact: true });
        const execSourceChip = buildProjectExecutionContextCompactChip(
          s && (s.project_execution_context || s.projectExecutionContext || null)
        );
        const heartbeatBadge = buildConversationHeartbeatBadges(s);
        let metaRow = null;
        if (secondaryParts.length || envBadge || execSourceChip) {
          metaRow = el("div", { class: "conv-card-submeta" });
          metaRow.appendChild(buildConversationRoleBadge(s));
          metaRow.appendChild(buildConversationCliBadge(s));
          if (envBadge) metaRow.appendChild(envBadge);
          if (execSourceChip) metaRow.appendChild(execSourceChip);
          secondaryParts.forEach((part) => metaRow.appendChild(el("span", {
            class: "conv-subchip " + String((part && part.kind) || "").trim(),
            text: String((part && part.text) || "").trim(),
          })));
        }
        if (!metaRow && heartbeatBadge) metaRow = el("div", { class: "conv-card-submeta" });
        if (metaRow && heartbeatBadge) metaRow.appendChild(heartbeatBadge);
        head.appendChild(titleWrap);
        const side = el("div", { class: "conv-card-side" });
        if (statusBadge) side.appendChild(statusBadge);
        if (auxBadges) side.appendChild(auxBadges);
        head.appendChild(side);
        if (metaRow) head.appendChild(metaRow);
        body.appendChild(head);
        const foot = el("div", { class: "conv-card-foot" });
        const previewMeta = el("div", { class: "conv-preview-meta" });
        if (s.lastActiveAt) previewMeta.appendChild(el("span", { class: "conv-time", text: compactDateTime(s.lastActiveAt) }));
        previewMeta.appendChild(el("div", { class: "conv-preview conv-preview-text", text: previewText, title: previewText }));
        foot.appendChild(previewMeta);
        if (countBadges) foot.appendChild(countBadges);
        body.appendChild(foot);
        row.appendChild(body);
        const moreBtn = el("button", {
          class: "conv-row-menu-btn",
          type: "button",
          text: "⋯",
          title: "会话信息",
          "aria-label": "会话信息",
        });
        moreBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          openConversationSessionInfoModal(s, STATE.project);
        });
        row.appendChild(moreBtn);
        bindConversationMentionDragSource(row, s, STATE.project);
        bindQueuedForwardDropTarget(row, s, STATE.project);
        row.addEventListener("click", () => {
          if (consumeQueuedForwardDropHandled(row)) return;
          setSelectedSessionId(sid, true, { explicit: true });
          // 移动端选择会话后切换到详情视图
          if (isMobileViewport()) {
            showDetailView();
          }
        });
        container.appendChild(row);
      }
    }

    // 构建任务模式下的通道对话列表
    function buildChannelConversationList() {
      const box = document.getElementById("channelConvBox");
      const container = document.getElementById("channelConvList");
      if (box) box.style.display = "none";
      if (container) container.innerHTML = "";
      buildChannelKnowledgeList();
    }

    function buildChannelKnowledgeList() {
      const box = document.getElementById("channelKnowledgeBox");
      const listNode = document.getElementById("channelKnowledgeList");
      const toggleBtn = document.getElementById("channelKnowledgeToggleBtn");
      const countChip = document.getElementById("channelKnowledgeCountChip");
      if (!box || !listNode || !toggleBtn || !countChip) return;

      if (STATE.panelMode !== "channel") {
        box.style.display = "none";
        return;
      }
      box.style.display = "";

      const projectId = String(STATE.project || "");
      const channelName = String(STATE.channel || "");
      const collapsed = isChannelKnowledgeCollapsed(projectId, channelName);
      toggleBtn.textContent = collapsed ? "展开" : "收起";
      toggleBtn.onclick = () => {
        setChannelKnowledgeCollapsed(projectId, channelName, !collapsed);
        buildChannelKnowledgeList();
      };

      listNode.innerHTML = "";
      if (!projectId || projectId === "overview" || !channelName) {
        countChip.textContent = "0条";
        listNode.appendChild(el("div", { class: "hint", text: "请先选择项目通道" }));
        return;
      }

      const items = channelKnowledgeItems(projectId, channelName);
      countChip.textContent = String(items.length) + "条";

      if (collapsed) {
        listNode.appendChild(el("div", { class: "hint", text: items.length ? ("已收纳 " + items.length + " 条，点击右上角展开查看") : "当前暂无可展示的知识沉淀" }));
        if (!items.length) listNode.appendChild(el("div", { class: "chknow-empty-note", text: "提示：产出物/沉淀/材料文档接入扫描后会在此自动显示。" }));
        return;
      }

      if (!items.length) {
        listNode.appendChild(el("div", { class: "hint", text: "当前通道暂无已纳入看板的非任务文档" }));
        listNode.appendChild(el("div", { class: "chknow-empty-note", text: "提示：产出物/沉淀/材料文档接入扫描后会在此自动显示。" }));
        return;
      }

      const groups = groupedChannelKnowledge(items);
      for (const group of groups) {
        const groupNode = el("section", { class: "chknow-group" });
        const gh = el("div", { class: "chknow-group-header" });
        const left = el("div", { class: "chknow-group-title" });
        left.appendChild(el("span", { text: group.label }));
        left.appendChild(chip(String(group.rows.length) + "条", "muted"));
        gh.appendChild(left);
        if (group.latest) {
          gh.appendChild(el("div", { class: "chknow-group-meta", text: "更新 " + compactDateTime(group.latest) }));
        }
        groupNode.appendChild(gh);

        const rowsNode = el("div", { class: "chknow-items" });
        for (const it of group.rows.slice(0, 60)) {
          const path = String((it && it.path) || "");
          const itemNode = el("div", { class: "chknow-item" + (path === String(STATE.selectedPath || "") ? " active" : ""), "data-path": path });
          itemNode.appendChild(el("div", { class: "chknow-item-title", text: shortTitle(it.title || path.split("/").pop() || "未命名文档") }));
          const metaNode = el("div", { class: "chknow-item-meta" });
          metaNode.appendChild(el("span", { class: "path", text: stripChannelPrefix(path, channelName) }));
          if (it.updated_at) metaNode.appendChild(el("span", { class: "time", text: compactDateTime(it.updated_at) }));
          itemNode.appendChild(metaNode);
          itemNode.addEventListener("click", () => setSelectedPath(path));
          rowsNode.appendChild(itemNode);
        }
        groupNode.appendChild(rowsNode);
        listNode.appendChild(groupNode);
      }
    }

    function setSelectedSessionId(sessionId, forceScroll = false, opts = {}) {
      const sid = String(sessionId || "").trim();
      if (!sid) return;
      if (typeof captureConversationListScrollTop === "function") {
        captureConversationListScrollTop(String(STATE.project || ""), normalizeConversationListLayout(STATE && STATE.convListLayout));
      }
      if (STATE.panelMode === "channel") {
        STATE.selectedSessionId = "";
        STATE.selectedSessionExplicit = false;
        try { localStorage.removeItem("taskDashboard.selectedSessionId"); } catch (_) {}
        buildChannelConversationList();
        renderDetail(selectedItem());
        updateSelectionUI();
        setHash();
        return;
      }
      const changed = sid !== String(STATE.selectedSessionId || "");
      const hasExplicitFlag = Object.prototype.hasOwnProperty.call(opts || {}, "explicit");
      const explicit = hasExplicitFlag ? !!opts.explicit : STATE.selectedSessionExplicit;
      STATE.selectedSessionId = sid;
      STATE.selectedSessionExplicit = explicit;
      try { localStorage.setItem("taskDashboard.selectedSessionId", STATE.selectedSessionId); } catch (_) {}
      // 只在对话模式下更新左侧对话列表
      if (STATE.panelMode === "conv") {
        buildConversationLeftList();
        buildConversationMainList(document.getElementById("fileList"));
      }
      // 更新通道对话列表（任务模式下）
      if (STATE.panelMode === "channel") {
        buildChannelConversationList();
        renderDetail(null);
      }
      renderConversationDetail(changed || forceScroll);
      if (STATE.project && STATE.project !== "overview") {
        refreshConversationTimeline(String(STATE.project || ""), sid, changed || forceScroll);
      }
      setHash();
    }

    function conversationCtxCodeBuddyPermissionMode(session, fallback = "") {
      const row = (session && typeof session === "object") ? session : {};
      const sid = String(row.sessionId || row.id || row.session_id || "").trim();
      const hasCached = sid
        && PCONV.codeBuddyPermissionModeBySessionId
        && typeof PCONV.codeBuddyPermissionModeBySessionId === "object"
        && Object.prototype.hasOwnProperty.call(PCONV.codeBuddyPermissionModeBySessionId, sid);
      const raw = firstNonEmptyText([
        hasCached ? PCONV.codeBuddyPermissionModeBySessionId[sid] : "",
        row.codebuddy_permission_mode,
        row.codebuddyPermissionMode,
        fallback,
      ]);
      return typeof normalizeCodeBuddyPermissionMode === "function"
        ? normalizeCodeBuddyPermissionMode(raw)
        : String(raw || "default");
    }

    function conversationCtxClaudePermissionMode(session, fallback = "") {
      const row = (session && typeof session === "object") ? session : {};
      const sid = String(row.sessionId || row.id || row.session_id || "").trim();
      const hasCached = sid
        && PCONV.claudePermissionModeBySessionId
        && typeof PCONV.claudePermissionModeBySessionId === "object"
        && Object.prototype.hasOwnProperty.call(PCONV.claudePermissionModeBySessionId, sid);
      const raw = firstNonEmptyText([
        hasCached ? PCONV.claudePermissionModeBySessionId[sid] : "",
        row.claude_permission_mode,
        row.claudePermissionMode,
        row.permission_mode,
        row.permissionMode,
        fallback,
      ]);
      return typeof normalizeClaudePermissionMode === "function"
        ? normalizeClaudePermissionMode(raw)
        : String(raw || "bypassPermissions");
    }

    function currentConversationCtx() {
      if (STATE.panelMode === "channel") return null;
      if (STATE.project === "overview") return null;
      const sid = String(STATE.selectedSessionId || "").trim();
      if (!sid) return null;
      const directorySessions = Array.isArray(((PCONV.sessionDirectoryByProject || {})[String(STATE.project || "")] || null))
        ? ((PCONV.sessionDirectoryByProject || {})[String(STATE.project || "")] || [])
        : [];
      const sessions = Array.isArray(PCONV.sessions) && PCONV.sessions.length ? PCONV.sessions : directorySessions;
      // 兼容 sessionId 和 id 两种字段名
      let cur = sessions.find(x => String(x.sessionId || x.id || "") === sid) || null;
      if (
        !cur
        && STATE.selectedSessionExplicit
        && typeof looksLikeSessionId === "function"
        && looksLikeSessionId(sid)
        && typeof buildExplicitConversationSessionStub === "function"
      ) {
        cur = buildExplicitConversationSessionStub(STATE.project, STATE.channel, sid);
      }
      if (!cur) return null;
      const cliType = cur && cur.cli_type ? String(cur.cli_type).trim() : "codex";
      const scopedChannel = STATE.panelMode === "channel" ? String(STATE.channel || "").trim() : "";
      // 兼容 channel_name 和 primaryChannel 两种字段名
      const channelName = String(scopedChannel || cur.channel_name || cur.primaryChannel || "");
      const agentName = conversationAgentName(cur);
      const normalizeModel = typeof normalizeSessionModel === "function"
        ? normalizeSessionModel
        : (value) => String(value || "").trim();
      const codeBuddyPermissionMode = typeof conversationCtxCodeBuddyPermissionMode === "function"
        ? conversationCtxCodeBuddyPermissionMode(cur)
        : String(cur.codebuddy_permission_mode || cur.codebuddyPermissionMode || "default");
      const codebuddyPermissionMode = codeBuddyPermissionMode;
      const claudePermissionMode = typeof conversationCtxClaudePermissionMode === "function"
        ? conversationCtxClaudePermissionMode(cur)
        : String(cur.claude_permission_mode || cur.claudePermissionMode || cur.permission_mode || cur.permissionMode || "bypassPermissions");
      return {
        projectId: String(STATE.project || ""),
        sessionId: sid,
        channelName: channelName,
        displayChannel: String(agentName || cur.displayChannel || cur.alias || channelName || ""),
        agentName: String(agentName || ""),
        alias: String(cur.alias || ""),
        cliType,
        model: normalizeModel(cur.model),
        codebuddyPermissionMode,
        claudePermissionMode,
      };
    }

    function resolveConversationSendCtx() {
      const current = currentConversationCtx();
      if (!current) return null;
      const selectedSession = findConversationSessionById(current.sessionId);
      const scopedChannel = STATE.panelMode === "channel" ? String(STATE.channel || "").trim() : "";
      const selectedChannel = firstNonEmptyText([
        scopedChannel,
        selectedSession && getSessionChannelName(selectedSession),
        current.channelName,
      ]);
      const primarySession = findPrimaryConversationSession(selectedChannel);
      const selectedIsSub = selectedSession ? !isPrimarySession(selectedSession) : false;
      const useSelectedSub = !!(selectedSession && STATE.selectedSessionExplicit && selectedIsSub);
      const targetSession = useSelectedSub ? selectedSession : (primarySession || selectedSession);
      if (!targetSession) return current;
      const targetChannel = firstNonEmptyText([selectedChannel, getSessionChannelName(targetSession), current.channelName]);
      return {
        projectId: String(STATE.project || ""),
        sessionId: getSessionId(targetSession),
        channelName: targetChannel,
        displayChannel: String(conversationAgentName(targetSession) || targetSession.displayChannel || targetSession.alias || targetChannel || ""),
        agentName: String(conversationAgentName(targetSession) || ""),
        alias: String(targetSession.alias || ""),
        cliType: String(targetSession.cli_type || current.cliType || "codex"),
        model: normalizeSessionModel(targetSession.model || current.model),
        codebuddyPermissionMode: conversationCtxCodeBuddyPermissionMode(targetSession, current.codebuddyPermissionMode || current.codebuddy_permission_mode),
        claudePermissionMode: conversationCtxClaudePermissionMode(targetSession, current.claudePermissionMode || current.claude_permission_mode || current.permissionMode || current.permission_mode),
        isPrimary: isPrimarySession(targetSession),
        routeReason: useSelectedSub ? "explicit-sub" : "default-main",
      };
    }

    function parseConvComposerDraftSessionKey(key) {
      const raw = String(key || "").trim();
      if (!raw) return null;
      const idx = raw.indexOf("::");
      if (idx <= 0) return null;
      const projectId = String(raw.slice(0, idx) || "").trim();
      const sessionId = String(raw.slice(idx + 2) || "").trim();
      if (!projectId || !sessionId) return null;
      return { projectId, sessionId };
    }

    function resolveConversationSendCtxByDraftKey(draftKey, fallbackCtx = null) {
      const parsed = parseConvComposerDraftSessionKey(draftKey);
      if (!parsed) return null;
      const fallback = (fallbackCtx && typeof fallbackCtx === "object") ? fallbackCtx : null;
      const fromLive = findConversationSessionById(parsed.sessionId);
      let fromConfigured = null;
      if (!fromLive) {
        const configured = configuredProjectConversations(parsed.projectId);
        fromConfigured = (configured || []).find((s) => String(getSessionId(s) || "") === parsed.sessionId) || null;
      }
      const matched = fromLive || fromConfigured || null;
      const channelName = firstNonEmptyText([
        matched && getSessionChannelName(matched),
        fallback && fallback.channelName,
        STATE && STATE.channel,
      ]);
      const cliType = firstNonEmptyText([
        matched && matched.cli_type,
        fallback && fallback.cliType,
        "codex",
      ]);
      if (!channelName) return null;
      return {
        projectId: parsed.projectId,
        sessionId: parsed.sessionId,
        channelName: String(channelName || "").trim(),
        displayChannel: String(firstNonEmptyText([
          matched && matched.displayChannel,
          matched && matched.alias,
          fallback && fallback.displayChannel,
          fallback && fallback.alias,
          channelName,
        ]) || "").trim(),
        alias: String(firstNonEmptyText([
          matched && matched.alias,
          fallback && fallback.alias,
          "",
        ]) || "").trim(),
        cliType: String(cliType || "codex").trim() || "codex",
        model: normalizeSessionModel(firstNonEmptyText([
          matched && matched.model,
          fallback && fallback.model,
          "",
        ])),
        codebuddyPermissionMode: conversationCtxCodeBuddyPermissionMode(matched, firstNonEmptyText([
          fallback && fallback.codebuddyPermissionMode,
          fallback && fallback.codebuddy_permission_mode,
        ])),
        claudePermissionMode: conversationCtxClaudePermissionMode(matched, firstNonEmptyText([
          fallback && fallback.claudePermissionMode,
          fallback && fallback.claude_permission_mode,
          fallback && fallback.permissionMode,
          fallback && fallback.permission_mode,
        ])),
        isPrimary: matched ? isPrimarySession(matched) : false,
        routeReason: "draft-session",
      };
    }

    function ensureConversationRunDetail(runId, opts = {}) {
      const rid = String(runId || "");
      if (!rid) return;
      const now = Date.now();
      const loadingStaleMs = 15000;
      const maxAgeMsRaw = Number(opts.maxAgeMs || 0);
      const maxAgeMs = Number.isFinite(maxAgeMsRaw) && maxAgeMsRaw > 0 ? maxAgeMsRaw : 0;
      const force = !!opts.force;
      const syncList = !!opts.syncList;
      const skipRender = !!opts.skipRender;
      const onLoaded = typeof opts.onLoaded === "function" ? opts.onLoaded : null;
      const terminalSyncStatus = String(opts.terminalSyncStatus || "").trim().toLowerCase();
      const prev = PCONV.detailMap[rid] || null;
      if (prev && prev.loading) {
        const loadingStartedAt = Number(prev.loadingStartedAt || 0);
        const loadingTooLong = loadingStartedAt > 0 && (now - loadingStartedAt) >= loadingStaleMs;
        if (!loadingTooLong) {
          if (onLoaded) {
            const pendingCallbacks = Array.isArray(prev.onLoadedQueue) ? prev.onLoadedQueue : [];
            pendingCallbacks.push(onLoaded);
            prev.onLoadedQueue = pendingCallbacks;
          }
          return;
        }
      }
      if (prev && !force) {
        if (terminalSyncStatus && String(prev.terminalSyncStatus || "").toLowerCase() === terminalSyncStatus) {
          const lastSyncAt = Number(prev.terminalSyncAt || 0);
          if (lastSyncAt > 0 && (now - lastSyncAt) < 3000) return;
        }
        if (maxAgeMs <= 0) return;
        const fetchedAt = Number(prev.fetchedAt || 0);
        if (fetchedAt > 0 && (now - fetchedAt) < maxAgeMs) return;
      }
      const requestKey = "detail-" + String(now) + "-" + Math.random().toString(36).slice(2, 8);
      const onLoadedQueue = [];
      if (prev && Array.isArray(prev.onLoadedQueue) && prev.onLoadedQueue.length) {
        onLoadedQueue.push.apply(onLoadedQueue, prev.onLoadedQueue);
      }
      if (onLoaded) onLoadedQueue.push(onLoaded);
      PCONV.detailMap[rid] = {
        loading: true,
        full: prev && prev.full ? prev.full : null,
        error: "",
        fetchedAt: prev && prev.fetchedAt ? prev.fetchedAt : 0,
        loadingStartedAt: now,
        requestKey,
        onLoadedQueue,
        terminalSyncStatus: terminalSyncStatus || (prev && prev.terminalSyncStatus ? prev.terminalSyncStatus : ""),
        terminalSyncAt: terminalSyncStatus ? now : Number((prev && prev.terminalSyncAt) || 0),
      };
      loadRun(rid).then((full) => {
        const current = PCONV.detailMap[rid] || null;
        if (current && current.requestKey && current.requestKey !== requestKey) return;
        const callbackQueue = Array.isArray(current && current.onLoadedQueue) ? current.onLoadedQueue.slice() : [];
        PCONV.detailMap[rid] = {
          loading: false,
          full,
          error: "",
          fetchedAt: Date.now(),
          loadingStartedAt: 0,
          requestKey: "",
          onLoadedQueue: [],
          terminalSyncStatus: terminalSyncStatus || (prev && prev.terminalSyncStatus ? prev.terminalSyncStatus : ""),
          terminalSyncAt: terminalSyncStatus ? Date.now() : Number((prev && prev.terminalSyncAt) || 0),
        };
        if (syncList) refreshConversationCountDots();
        if (callbackQueue.length) {
          callbackQueue.forEach((cb) => {
            try { cb(full, null); } catch (_) {}
          });
        }
        if (!skipRender) renderConversationDetail();
      }).catch((e) => {
        const current = PCONV.detailMap[rid] || null;
        if (current && current.requestKey && current.requestKey !== requestKey) return;
        const callbackQueue = Array.isArray(current && current.onLoadedQueue) ? current.onLoadedQueue.slice() : [];
        PCONV.detailMap[rid] = {
          loading: false,
          full: prev && prev.full ? prev.full : null,
          error: String(e || "load failed"),
          fetchedAt: prev && prev.fetchedAt ? prev.fetchedAt : 0,
          loadingStartedAt: 0,
          requestKey: "",
          onLoadedQueue: [],
          terminalSyncStatus: terminalSyncStatus || (prev && prev.terminalSyncStatus ? prev.terminalSyncStatus : ""),
          terminalSyncAt: terminalSyncStatus ? Date.now() : Number((prev && prev.terminalSyncAt) || 0),
        };
        if (syncList) refreshConversationCountDots();
        if (callbackQueue.length) {
          callbackQueue.forEach((cb) => {
            try { cb(prev && prev.full ? prev.full : null, e); } catch (_) {}
          });
        }
        if (!skipRender) renderConversationDetail();
      });
    }

    function deriveRunStateFromSource(source, fallback = "") {
      const src = (source && typeof source === "object") ? source : null;
      const rawDisplay = firstNonEmptyText([
        src && src.display_state,
        src && src.displayState,
      ]);
      const rawStatus = firstNonEmptyText([
        src && src.status,
      ]);
      const display = normalizeDisplayState(rawDisplay, "");
      const status = normalizeDisplayState(rawStatus, "");
      if ((status === "done" || status === "error") && display !== status) return status;
      return normalizeDisplayState(display || status, fallback || "idle");
    }

    function runSourceProgressTs(source) {
      const src = (source && typeof source === "object") ? source : {};
      return Math.max(
        toTimeNum(firstNonEmptyText([
          src.latestProgressAt,
          src.latest_progress_at,
          src.lastProgressAt,
          src.last_progress_at,
          src.updatedAt,
          src.updated_at,
          src.startedAt,
          src.started_at,
          src.createdAt,
        ])),
        -1
      );
    }

    function processRowProgressTs(row) {
      const src = (row && typeof row === "object") ? row : {};
      const explicitTs = firstNonEmptyText([
        src.at,
        src.ts,
        src.time,
        src.timestamp,
        src.updatedAt,
        src.updated_at,
        src.createdAt,
        src.created_at,
      ]);
      const explicitNum = toTimeNum(explicitTs);
      if (explicitNum >= 0) return explicitNum;
      return toTimeNum(extractProcessItemTimestamp(src.text));
    }

    function runSourceProcessProgressTs(source) {
      const src = (source && typeof source === "object") ? source : {};
      const lists = [
        src.processRows,
        src.process_rows,
        src.processEvents,
        src.process_events,
      ];
      let latest = -1;
      lists.forEach((list) => {
        if (!Array.isArray(list) || !list.length) return;
        list.slice(-80).forEach((row) => {
          const ts = processRowProgressTs(row);
          if (ts > latest) latest = ts;
        });
      });
      return latest;
    }

    function runSourceContinuingProgressTs(source) {
      const src = (source && typeof source === "object") ? source : {};
      return Math.max(
        toTimeNum(firstNonEmptyText([
          src.latestProgressAt,
          src.latest_progress_at,
          src.lastProgressAt,
          src.last_progress_at,
          src.updatedAt,
          src.updated_at,
        ])),
        runSourceProcessProgressTs(src),
        -1
      );
    }

    function latestRunProgressTs(run, detailRun, detailMeta) {
      const detailFull = detailMeta && detailMeta.full && typeof detailMeta.full === "object"
        ? detailMeta.full
        : null;
      return Math.max(
        runSourceContinuingProgressTs(run),
        runSourceContinuingProgressTs(detailRun),
        runSourceContinuingProgressTs(detailFull)
      );
    }

    function latestRunTerminalTs(run, detailRun) {
      return Math.max(
        runSourceFinishedTs(run),
        runSourceFinishedTs(detailRun)
      );
    }

    function runSourceFinishedTs(source) {
      const src = (source && typeof source === "object") ? source : {};
      return Math.max(
        toTimeNum(firstNonEmptyText([
          src.finishedAt,
          src.finished_at,
        ])),
        -1
      );
    }

    function detailFetchedTs(detailMeta) {
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const ts = Number(detail && detail.fetchedAt);
      return Number.isFinite(ts) && ts > 0 ? ts : -1;
    }

    function shouldPreferDetailSnapshot(run, detailRun, detailMeta) {
      const detailState = deriveRunStateFromSource(detailRun, "");
      if (!detailState) return false;
      const detailTs = Math.max(
        detailFetchedTs(detailMeta),
        runSourceProgressTs(detailRun),
        runSourceFinishedTs(detailRun)
      );
      if (detailTs < 0) return false;
      const runTs = Math.max(
        runSourceFinishedTs(run),
        runSourceProgressTs(run)
      );
      return runTs < 0 || detailTs >= runTs;
    }

    function shouldSuppressRunInterruptedInfra(runMeta, detailMeta = null) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : {};
      const runState = deriveRunStateFromSource(run, "");
      const detailState = deriveRunStateFromSource(detailRun, "");
      const preferDetail = detailRun ? shouldPreferDetailSnapshot(run, detailRun, detail) : false;
      if (isWorkingLikeState(detailState) && preferDetail) return true;
      if (isWorkingLikeState(runState)) return true;
      const progressTs = latestRunProgressTs(run, detailRun, detail);
      if (progressTs < 0 || isProgressStale(progressTs)) return false;
      const terminalTs = latestRunTerminalTs(run, detailRun);
      return terminalTs < 0 || progressTs > terminalTs + 1000;
    }

    function isWorkingLikeState(st) {
      const s = String(st || "").toLowerCase();
      return isRunWorking(s) || s === "external_busy";
    }

    function isInterruptedByUserText(raw) {
      const txt = String(raw || "").trim();
      if (!txt) return false;
      return /(?:interrupted by user|user_interrupt|用户打断|用户中断)/i.test(txt);
    }

    function isRunInterruptedByUser(runMeta) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const samples = [
        run.error,
        run.errorHint,
        run.eventReason,
        run.event_reason,
        run.interruptReason,
        run.interrupt_reason,
        run.communication_view && run.communication_view.event_reason,
        run.communicationView && run.communicationView.event_reason,
      ];
      return samples.some((item) => isInterruptedByUserText(item));
    }

    function getRunOutcomeState(runMeta, detailMeta = null) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : {};
      return normalizeRunOutcomeState(firstNonEmptyText([
        detailRun.outcome_state,
        detailRun.outcomeState,
        run.outcome_state,
        run.outcomeState,
      ]), "");
    }

    function getRunErrorClass(runMeta, detailMeta = null) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : {};
      return normalizeRunErrorClass(firstNonEmptyText([
        detailRun.error_class,
        detailRun.errorClass,
        run.error_class,
        run.errorClass,
      ]), "");
    }

    function getRunFailureClass(runMeta, detailMeta = null) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : {};
      return String(firstNonEmptyText([
        detailRun.failure_class,
        detailRun.failureClass,
        run.failure_class,
        run.failureClass,
      ]) || "").trim().toLowerCase();
    }

    function getRunProviderError(runMeta, detailMeta = null) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : {};
      const candidates = [
        detailRun.provider_error,
        detailRun.providerError,
        run.provider_error,
        run.providerError,
      ];
      for (const item of candidates) {
        if (item && typeof item === "object") return item;
      }
      return {};
    }

    function getRunProviderFailureDisplay(runMeta, detailMeta = null) {
      const outcomeState = getRunOutcomeState(runMeta, detailMeta);
      const errorClass = getRunErrorClass(runMeta, detailMeta);
      const failureClass = getRunFailureClass(runMeta, detailMeta);
      const providerError = getRunProviderError(runMeta, detailMeta);
      const providerKind = String((providerError && providerError.kind) || "").trim().toLowerCase();
      const retryable = !!(providerError && providerError.retryable);
      const matched = Array.isArray(providerError && providerError.matched_patterns)
        ? providerError.matched_patterns
        : [];
      const providerLike = failureClass === "provider_transient"
        || outcomeState === "provider_transient_failed"
        || errorClass === "provider_transient"
        || (retryable && !!providerKind);
      if (!providerLike) return null;
      const label = ({
        high_demand: "模型服务高负载",
        model_capacity: "模型容量不足",
        rate_limit: "模型服务限流",
        server_error: "模型服务 5xx",
        network_timeout: "网络超时",
        network_reset: "网络中断",
        upstream_unavailable: "上游不可用",
      }[providerKind]
        || (matched.some((item) => /model[_\s-]?capacity|resource[_\s-]?exhausted|no capacity/i.test(String(item || ""))) ? "模型容量不足" : "")
        || (matched.some((item) => /high demand|temporary errors?/i.test(String(item || ""))) ? "模型服务高负载" : "模型服务临时不可用"));
      return {
        providerTransient: true,
        providerKind,
        label,
        headline: label,
        tone: "warn",
        subtitle: "这不是业务处理失败，模型服务返回临时错误；可能已有部分动作完成，需要补链恢复。",
        recoveryText: "可能已有部分动作完成，需要补链恢复。",
        errorPrefix: label,
      };
    }

    function buildRunOutcomeMeta(runMeta, detailMeta = null) {
      const outcomeState = getRunOutcomeState(runMeta, detailMeta);
      const errorClass = getRunErrorClass(runMeta, detailMeta);
      const providerDisplay = getRunProviderFailureDisplay(runMeta, detailMeta);
      if (providerDisplay) {
        return {
          outcomeState: outcomeState || "provider_transient_failed",
          errorClass: errorClass || "provider_transient",
          ...providerDisplay,
        };
      }
      if (!outcomeState) return null;
      if (outcomeState === "success") {
        return {
          outcomeState,
          errorClass,
          label: "业务结果",
          tone: "good",
          subtitle: "当前结果进入业务摘要主位",
        };
      }
      if (outcomeState === "interrupted_infra") {
        if (shouldSuppressRunInterruptedInfra(runMeta, detailMeta)) return null;
        return {
          outcomeState,
          errorClass,
          label: "环境中断",
          tone: "warn",
          subtitle: "基础设施中断，不按业务失败处理",
        };
      }
      if (outcomeState === "interrupted_user") {
        return {
          outcomeState,
          errorClass,
          label: "人工打断",
          tone: "muted",
          subtitle: "由用户或人工操作打断，不按业务失败处理",
        };
      }
      if (outcomeState === "failed_config") {
        const configText = errorClass === "session_binding"
          ? "会话绑定异常，需修正 session 或路由配置"
          : (errorClass === "workspace_permission"
            ? "工作区权限异常，需修正路径或权限边界"
            : (errorClass === "cli_path"
              ? "CLI 配置异常，需检查执行器或命令路径"
              : "配置或绑定存在异常，需先修正环境"));
        return {
          outcomeState,
          errorClass,
          label: "配置阻塞",
          tone: "bad",
          subtitle: configText,
        };
      }
      if (outcomeState === "failed_business") {
        return {
          outcomeState,
          errorClass,
          label: "业务失败",
          tone: "bad",
          subtitle: "业务处理失败，本条未进入成功摘要主位",
        };
      }
      if (outcomeState === "recovered_notice") {
        return {
          outcomeState,
          errorClass,
          label: "恢复通知",
          tone: "muted",
          subtitle: "系统恢复摘要，不占业务摘要主位",
        };
      }
      return null;
    }

    function runErrorDisplayText(rawError, outcomeMeta = null, fallback = "执行失败（未返回具体错误文本）") {
      const err = String(rawError || "").trim();
      if (outcomeMeta && outcomeMeta.providerTransient) {
        const lead = String(outcomeMeta.errorPrefix || outcomeMeta.label || "模型服务临时不可用").trim();
        const parts = [
          lead + "：这不是业务处理失败。",
          String(outcomeMeta.recoveryText || "可能已有部分动作完成，需要补链恢复。").trim(),
        ].filter(Boolean);
        if (err) parts.push("原始错误：" + err);
        return parts.join(" ");
      }
      return "error: " + (err || fallback);
    }

    function getRunDisplayState(run, detail) {
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : null;
      const runState = deriveRunStateFromSource(run, "");
      const detailState = deriveRunStateFromSource(detailRun, "");
      const preferDetail = detailRun ? shouldPreferDetailSnapshot(run, detailRun, detail) : false;
      const runInterrupted = isRunInterruptedByUser(run);
      const detailInterrupted = isRunInterruptedByUser(detailRun);
      const outcomeState = getRunOutcomeState(run, detail);
      // 同一个 run 一旦列表快照已进入明确终态，不允许 detail 的旧 working 摘要再把它压回处理中。
      if (outcomeState === "success") return "done";
      if (runState === "done") return "done";
      if (outcomeState === "failed_config" || outcomeState === "failed_business" || outcomeState === "provider_transient_failed") return "error";
      if (outcomeState === "interrupted_infra") {
        if (shouldSuppressRunInterruptedInfra(run, detail)) return "running";
        return "interrupted";
      }
      if (runState === "error") return "error";
      if (runInterrupted || outcomeState === "interrupted_user") return "interrupted";
      if (detailInterrupted && preferDetail) return "interrupted";
      if ((detailState === "done" || detailState === "error") && preferDetail) return detailState;
      if (isWorkingLikeState(detailState) && preferDetail) return detailState;
      if (isWorkingLikeState(runState)) return runState;
      if (detailState === "done" || detailState === "error") return detailState;
      if (runInterrupted) return "interrupted";
      if (runState === "done" || runState === "error") return runState;
      if (isWorkingLikeState(detailState)) return detailState;
      return normalizeDisplayState(runState || detailState, "idle");
    }

    function getRunQueueReason(run, detail) {
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : null;
      return String(firstNonEmptyText([
        detailRun && detailRun.queue_reason,
        run && run.queue_reason,
      ]) || "").trim().toLowerCase();
    }

    function getRunBlockedByRunId(run, detail) {
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : null;
      return String(firstNonEmptyText([
        detailRun && detailRun.blocked_by_run_id,
        run && run.blocked_by_run_id,
        detailRun && detailRun.blockedByRunId,
        run && run.blockedByRunId,
      ]) || "").trim();
    }

    function getRunAggregateMeta(run, detail) {
      const detailRun = detail && detail.full && detail.full.run && typeof detail.full.run === "object"
        ? detail.full.run
        : null;
      const mergeMode = String(firstNonEmptyText([
        detailRun && detailRun.callback_merge_mode,
        detailRun && detailRun.callbackMergeMode,
        run && run.callback_merge_mode,
        run && run.callbackMergeMode,
      ]) || "").trim().toLowerCase();
      const sourceIds = readCallbackSummaryIds(
        (detailRun && (detailRun.callback_aggregate_source_run_ids || detailRun.callbackAggregateSourceRunIds))
        || (run && (run.callback_aggregate_source_run_ids || run.callbackAggregateSourceRunIds))
        || []
      );
      const summaryIds = readCallbackSummaryIds(
        (detailRun && (detailRun.callback_summary_of || detailRun.callbackSummaryOf))
        || (run && (run.callback_summary_of || run.callbackSummaryOf))
        || []
      );
      const aggregateCount = readPositiveInt(firstNonEmptyText([
        detailRun && detailRun.callback_aggregate_count,
        detailRun && detailRun.callbackAggregateCount,
        run && run.callback_aggregate_count,
        run && run.callbackAggregateCount,
      ]), Math.max(sourceIds.length, summaryIds.length));
      const lastMergedAt = String(firstNonEmptyText([
        detailRun && detailRun.callback_last_merged_at,
        detailRun && detailRun.callbackLastMergedAt,
        run && run.callback_last_merged_at,
        run && run.callbackLastMergedAt,
      ]) || "").trim();
      return {
        mergeMode,
        aggregateCount,
        lastMergedAt,
      };
    }

    function queueReasonLabel(reason) {
      const r = String(reason || "").trim().toLowerCase();
      if (!r) return "";
      const map = {
        session_serial: "同会话串行，等待前序任务",
        session_busy_external: "会话被外部占用",
        blocked_by_active_run: "前序任务执行中",
        blocked_by_run: "被前序任务阻塞",
        scheduler_busy: "调度器繁忙",
      };
      return map[r] || r;
    }

    function retryWaitingRemainText(run) {
      const st = getRunDisplayState(run, null);
      if (st !== "retry_waiting") return "";
      const dueTs = toTimeNum(run && run.retryScheduledAt);
      if (dueTs > 0) {
        const sec = Math.max(0, Math.ceil((dueTs - Date.now()) / 1000));
        if (sec > 0) return "等待重试中，约 " + sec + "s 后自动继续";
        return "等待重试中，即将自动继续";
      }
      return "等待重试中，稍后自动继续";
    }

    function isRunWorking(st) {
      const s = String(st || "").toLowerCase();
      return s === "running" || s === "queued" || s === "retry_waiting";
    }

    function looksTruncatedSummaryText(text) {
      const t = String(text || "").trim();
      if (!t) return false;
      return t.endsWith("...") || t.endsWith("…");
    }

    function runStateClass(st, opts = {}) {
      const s = String(st || "").toLowerCase();
      const outcomeState = normalizeRunOutcomeState(opts && opts.outcomeState, "");
      if (s === "running") return "running";
      if (s === "queued") return "queued";
      if (s === "retry_waiting") return "retry-waiting";
      if (s === "external_busy") return "queued";
      if (s === "interrupted" && outcomeState === "interrupted_infra") return "queued";
      if (s === "done") return "done";
      if (s === "interrupted") return "error";
      if (s === "error") return "error";
      return "idle";
    }

    function runStateHeadline(st, opts = {}) {
      const s = String(st || "").toLowerCase();
      const outcomeState = normalizeRunOutcomeState(opts && opts.outcomeState, "");
      if (s === "running") return "进行中（实时执行）";
      if (s === "queued") return "排队中（等待执行）";
      if (s === "retry_waiting") return "等待重试中（网络中断）";
      if (s === "external_busy") return "外部占用（探测）";
      if (s === "done" && outcomeState === "recovered_notice") return "恢复通知";
      if (s === "done") return "已完成";
      if (s === "interrupted" && outcomeState === "interrupted_infra") return "环境中断";
      if (s === "interrupted") return "用户打断";
      if (s === "error" && opts && opts.timeout) return "执行超时";
      if (s === "error" && outcomeState === "provider_transient_failed") return String(opts.providerHeadline || "模型服务临时不可用");
      if (s === "error" && outcomeState === "failed_config") return "配置阻塞";
      if (s === "error" && outcomeState === "failed_business") return "业务失败";
      if (s === "error") return "执行异常";
      return "空闲";
    }

    function isNetworkIssueText(raw) {
      const txt = String(raw || "").trim();
      if (!txt) return false;
      if (isTimeoutErrorText(txt)) return true;
      return /(?:network|socket|connection|econn|etimedout|ehostunreach|enetunreach|网络|断网|断线|连接中断|连接超时|超时)/i.test(txt);
    }

    function isRunNetworkIssueLike(runMeta, detailMeta = null) {
      const run = (runMeta && typeof runMeta === "object") ? runMeta : {};
      const detail = (detailMeta && typeof detailMeta === "object") ? detailMeta : null;
      const full = detail && detail.full ? detail.full : null;
      const runFromDetail = (full && full.run && typeof full.run === "object") ? full.run : {};
      const st = getRunDisplayState(run, detail);
      const outcomeState = getRunOutcomeState(run, detail);
      if (st !== "retry_waiting" && st !== "error" && !(st === "interrupted" && outcomeState === "interrupted_infra")) return false;
      if (st === "error" && isRunTimeoutLike(run, detail)) return true;
      if (outcomeState === "interrupted_infra") return true;
      const samples = [
        run.error,
        run.errorHint,
        run.eventReason,
        run.event_reason,
        detail && detail.error,
        full && full.errorHint,
        runFromDetail.error,
        runFromDetail.eventReason,
        runFromDetail.event_reason,
      ];
      const matched = samples.some((x) => isNetworkIssueText(x));
      if (matched) return true;
      return st === "retry_waiting";
    }

    function conversationQuickTipsForRuns(ctx, runs) {
      const list = Array.isArray(runs) ? runs : [];
      if (!ctx || !list.length) return [];
      const latestRun = list[list.length - 1] || null;
      if (!latestRun) return [];
      const rid = String((latestRun && latestRun.id) || "").trim();
      const detail = rid ? (PCONV.detailMap[rid] || null) : null;
      if (isRunNetworkIssueLike(latestRun, detail)) {
        return [{
          id: "network-retry",
          label: "网络中断，请重试",
          message: "网络中断，请重试",
        }];
      }
      return [];
    }

    async function sendConversationQuickMessage(messageText, opts = {}) {
      const options = (opts && typeof opts === "object") ? opts : {};
      const pendingHint = String(options.pendingHint || "").trim() || "发送中（快捷重试）…";
      const successHint = String(options.successHint || "").trim() || "已发送快捷重试消息，等待执行回溯刷新…";
      const onSuccess = typeof options.onSuccess === "function" ? options.onSuccess : null;
      const quickMsg = String(messageText || "").trim();
      if (!quickMsg || PCONV.sending) return false;
      const input = document.getElementById("convMsg");
      const sendBtn = document.getElementById("convSendBtn");
      const hint = document.getElementById("convHint");
      if (!input || !sendBtn || !hint) return false;
      const currentCtx = currentConversationCtx();
      const ctx = currentCtx || resolveConversationSendCtx();
      if (!ctx || !ctx.sessionId || !ctx.channelName) {
        input.placeholder = "该会话缺少通道路由，请先为该 session 绑定通道";
        return false;
      }
      const conversationModel = typeof resolveConversationComposerPayloadModel === "function"
        ? resolveConversationComposerPayloadModel(ctx)
        : "";
      if (String(STATE.selectedSessionId || "") !== String(ctx.sessionId || "")) {
        setSelectedSessionId(ctx.sessionId, true, { explicit: false });
      }
      PCONV.sending = true;
      PCONV.optimistic = {
        sessionId: ctx.sessionId,
        message: quickMsg,
        attachments: [],
        mentionTargets: [],
        createdAt: new Date().toISOString(),
      };
      markSessionPending(ctx.sessionId, quickMsg);
      if (STATE.panelMode === "conv") {
        buildConversationLeftList();
        buildConversationMainList(document.getElementById("fileList"));
      } else {
        buildChannelConversationList();
      }
      sendBtn.disabled = true;
      sendBtn.textContent = "发送中...";
      setHintText("conv", pendingHint);
      renderConversationDetail(true);

      let failedText = "";
      try {
        const r = await fetch("/api/codex/announce", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            projectId: ctx.projectId,
            channelName: ctx.channelName,
            sessionId: ctx.sessionId,
            cliType: ctx.cliType || "codex",
            ...(conversationModel ? { model: conversationModel } : {}),
            message: quickMsg,
            ...buildUiUserSenderFields(),
          }),
        });
        if (!r.ok) {
          const detail = await parseResponseDetail(r);
          const tok = getToken();
          if ((r.status === 401 || r.status === 403) && !tok) {
            failedText = "发送失败：服务启用了 Token 校验，请先点右侧 Token 设置。";
          } else {
            failedText = "发送失败：" + (detail || ("HTTP " + r.status));
          }
        } else {
          const resp = await r.json().catch(() => ({}));
          const runId = resp && resp.run ? String(resp.run.id || "") : "";
          PCONV.optimistic = null;
          PCONV.sending = false;
          if (onSuccess) {
            try {
              await onSuccess({ ctx, runId, response: resp });
            } catch (_) {}
          }
          setHintText("conv", successHint);
          await refreshConversationPanel();
          if (runId) scheduleConversationPoll(5000);
          return true;
        }
      } catch (_) {
        failedText = "发送失败：网络或服务异常，请重试。";
      }
      PCONV.sending = false;
      PCONV.optimistic = null;
      sendBtn.disabled = false;
      sendBtn.textContent = "发送";
      if (failedText) setHintText("conv", failedText);
      renderConversationDetail();
      return false;
    }

    const RUN_PROGRESS_STALE_THRESHOLD_MS = 5 * 60 * 1000;

    function normalizeProcessTimestamp(raw) {
      const text = String(raw || "").trim();
      if (!text) return "";
      const d = parseDateTime(text);
      return d ? d.toISOString() : "";
    }

    function extractProcessItemTimestamp(text) {
      const raw = String(text || "").trim();
      if (!raw) return "";
      const full = raw.match(/\b(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?)\b/);
      if (full && full[1]) {
        const iso = normalizeProcessTimestamp(full[1]);
        if (iso) return iso;
      }
      const mdHm = raw.match(/\b(\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\b/);
      if (mdHm && mdHm[1]) {
        const year = new Date().getFullYear();
        const iso = normalizeProcessTimestamp(year + "-" + mdHm[1].replace(/\s+/, " "));
        if (iso) return iso;
      }
      return "";
    }

    function progressElapsedText(ts) {
      const t = toTimeNum(ts);
      if (t < 0) return "-";
      let diffSec = Math.floor((Date.now() - t) / 1000);
      if (!Number.isFinite(diffSec) || diffSec < 0) diffSec = 0;
      if (diffSec < 10) return "刚刚";
      if (diffSec < 60) return diffSec + "秒前";
      const mins = Math.floor(diffSec / 60);
      if (mins < 60) return mins + "分钟前";
      const hours = Math.floor(mins / 60);
      if (hours < 24) return hours + "小时前";
      const days = Math.floor(hours / 24);
      return days + "天前";
    }

    function isProgressStale(ts, thresholdMs = RUN_PROGRESS_STALE_THRESHOLD_MS) {
      const t = toTimeNum(ts);
      if (t < 0) return false;
      return (Date.now() - t) > Math.max(1000, Number(thresholdMs) || RUN_PROGRESS_STALE_THRESHOLD_MS);
    }

    function ensureRunProcessUi(runId, st) {
      const rid = String(runId || "");
      if (!rid) return { expanded: false, manual: false };
      let state = PCONV.processUi[rid];
      const status = String(st || "").trim().toLowerCase();
      const autoExpanded = status === "running" || status === "queued" || status === "retry_waiting";
      if (!state) {
        state = { expanded: autoExpanded, manual: false };
        PCONV.processUi[rid] = state;
      } else if (!state.manual) {
        state.expanded = autoExpanded;
      }
      return state;
    }

    function toggleRunProcessUi(runId, st) {
      const state = ensureRunProcessUi(runId, st);
      state.manual = true;
      state.expanded = !state.expanded;
      PCONV.processUi[String(runId || "")] = state;
      return state.expanded;
    }

    function getRunDetailDrawerTab(runId, opts = {}) {
      const rid = String(runId || "").trim();
      if (!rid) return "process";
      const preferred = String((PCONV.runDetailTabByRun && PCONV.runDetailTabByRun[rid]) || "").trim().toLowerCase();
      const debugExpanded = !!opts.debugExpanded;
      if (preferred === "debug") return "debug";
      if (preferred === "process") return "process";
      return debugExpanded ? "debug" : "process";
    }

    function setRunDetailDrawerTab(runId, tab) {
      const rid = String(runId || "").trim();
      if (!rid) return;
      const next = String(tab || "").trim().toLowerCase() === "debug" ? "debug" : "process";
      if (!PCONV.runDetailTabByRun) PCONV.runDetailTabByRun = Object.create(null);
      PCONV.runDetailTabByRun[rid] = next;
    }

    function openRunDetailDrawer(runId, st, tab) {
      const rid = String(runId || "").trim();
      if (!rid) return;
      const nextTab = String(tab || "").trim().toLowerCase() === "debug" ? "debug" : "process";
      setRunDetailDrawerTab(rid, nextTab);
      const state = ensureRunProcessUi(rid, st);
      state.manual = true;
      if (nextTab === "debug") {
        state.expanded = false;
        PCONV.debugExpanded.add(rid);
      } else {
        state.expanded = true;
        PCONV.debugExpanded.delete(rid);
      }
      PCONV.processUi[rid] = state;
    }

    function isUnsafeProcessRowKind(raw) {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
      const kindText = firstNonEmptyText([
        raw.type,
        raw.kind,
        raw.event_type,
        raw.eventType,
        raw.item_type,
        raw.itemType,
        raw.source,
        raw.title,
        raw.name,
        raw.label,
      ]).toLowerCase();
      return kindText.indexOf("reasoning") >= 0 || kindText.indexOf("file-history-snapshot") >= 0;
    }

    function containsUnsafeProcessMarker(value) {
      const text = String(value == null ? "" : value).trim().toLowerCase();
      return text.indexOf("file-history-snapshot") >= 0;
    }

    function normalizeProcessMessageText(raw) {
      if (raw == null) return "";
      if (typeof raw === "string" || typeof raw === "number" || typeof raw === "boolean") {
        return String(raw).replace(/\r\n/g, "\n").trim();
      }
      if (typeof raw === "object" && !Array.isArray(raw)) {
        if (isUnsafeProcessRowKind(raw)) return "";
        const txt = firstNonEmptyText([
          raw.text,
          raw.message,
          raw.msg,
          raw.content,
          raw.detail,
          raw.summary,
          raw.label,
          raw.title,
        ]);
        if (containsUnsafeProcessMarker(txt)) return "";
        if (txt) return String(txt).replace(/\r\n/g, "\n").trim();
        if (Array.isArray(raw.lines) && raw.lines.length) {
          const lineText = raw.lines.map((line) => String(line || "")).join("\n").replace(/\r\n/g, "\n").trim();
          return containsUnsafeProcessMarker(lineText) ? "" : lineText;
        }
        const rawType = firstNonEmptyText([raw.type, raw.event_type, raw.eventType]).toLowerCase();
        if (raw.rawContent !== undefined || raw.raw_content !== undefined || rawType.indexOf("reasoning") >= 0) return "";
        try { return JSON.stringify(raw); } catch (_) {}
      }
      return String(raw || "").replace(/\r\n/g, "\n").trim();
    }

    function extractStructuredProcessRowTime(raw) {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) return "";
      return normalizeProcessTimestamp(firstNonEmptyText([
        raw.at,
        raw.ts,
        raw.time,
        raw.timestamp,
        raw.createdAt,
        raw.created_at,
        raw.updatedAt,
        raw.updated_at,
      ]));
    }

    function firstProcessMetaText(values) {
      const list = Array.isArray(values) ? values : [];
      for (let i = 0; i < list.length; i += 1) {
        const txt = String(list[i] == null ? "" : list[i]).trim();
        if (txt) return txt;
      }
      return "";
    }

    function clampRunProcessDisplayText(value, maxLen = 180) {
      const text = String(value == null ? "" : value).replace(/\r\n/g, "\n").trim();
      const compact = text.replace(/\s+/g, " ").trim();
      const limit = Math.max(24, Number(maxLen || 0) || 180);
      if (compact.length <= limit) return compact;
      return compact.slice(0, Math.max(0, limit - 1)).trimEnd() + "…";
    }

    function looksLikeRawProcessJsonText(value) {
      const text = String(value == null ? "" : value).trim();
      if (!text) return false;
      if (text.indexOf("rawContent") >= 0 || text.indexOf("raw_content") >= 0 || text.indexOf("reasoning") >= 0) return true;
      const firstChar = text.charAt(0);
      if (firstChar !== "{" && firstChar !== "[") return false;
      return text.indexOf('"event_type"') >= 0
        || text.indexOf('"item_type"') >= 0
        || text.indexOf('"type"') >= 0
        || text.indexOf('"content"') >= 0
        || text.indexOf('"role"') >= 0;
    }

    function isLowValueRunProcessActionTarget(value) {
      const text = String(value || "").trim().toLowerCase();
      return !text
        || text === "claude"
        || text === "claudecode"
        || text === "claude-code"
        || text === "codex"
        || text === "codebuddy"
        || text === "code-buddy"
        || text === "gemini"
        || text === "opencode";
    }

    function firstRunProcessActionTargetText(values) {
      const list = Array.isArray(values) ? values : [];
      for (let i = 0; i < list.length; i += 1) {
        const text = String(list[i] == null ? "" : list[i]).trim();
        if (!text) continue;
        if (isLowValueRunProcessActionTarget(text)) continue;
        if (looksLikeRawProcessJsonText(text) || containsUnsafeProcessMarker(text)) continue;
        return text;
      }
      return "";
    }

    function structuredProcessRowFallbackText(row) {
      const src = (row && typeof row === "object" && !Array.isArray(row)) ? row : {};
      const eventType = firstProcessMetaText([src.event_type, src.eventType, src.type, src.kind]);
      const itemType = firstProcessMetaText([src.item_type, src.itemType, src.item && src.item.type]);
      const title = firstProcessMetaText([src.title, src.name, src.label, src.toolName, src.tool_name]);
      const target = firstRunProcessActionTargetText([
        src.target,
        src.targetPath,
        src.target_path,
        src.path,
        src.command,
        src.url,
        src.href,
      ]);
      const prefix = firstProcessMetaText([title, eventType, itemType, "结构化动作"]);
      return clampRunProcessDisplayText(target && target !== prefix ? (prefix + ": " + target) : prefix, 180);
    }

    function normalizeRunProcessTimelineRow(raw, index = 0) {
      const row = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : null;
      let text = normalizeProcessMessageText(raw);
      if (row && !isUnsafeProcessRowKind(row)) {
        const fallbackText = structuredProcessRowFallbackText(row);
        if (fallbackText && (!text || looksLikeRawProcessJsonText(text))) text = fallbackText;
      }
      const at = row ? extractStructuredProcessRowTime(row) : "";
      const eventType = row ? firstProcessMetaText([row.event_type, row.eventType]) : "";
      const itemType = row ? firstProcessMetaText([row.item_type, row.itemType, row.type]) : "";
      const title = row ? firstProcessMetaText([row.title, row.name, row.label]) : "";
      const callId = row ? firstProcessMetaText([row.call_id, row.callId, row.raw_ref, row.rawRef]) : "";
      const out = {
        text,
        at,
        timeSource: at ? "structured" : "",
        eventType,
        itemType,
        title,
        callId,
        rowIndex: Math.max(0, Number(index || 0) || 0),
      };
      if (row) {
        [
          "path",
          "source",
          "status",
          "phase",
          "state",
          "outcome",
          "target",
          "targetPath",
          "target_path",
          "command",
          "url",
          "href",
          "name",
          "toolName",
          "tool_name",
          "call_id",
          "callId",
          "raw_ref",
          "rawRef",
          "error",
          "errorSummary",
          "error_summary",
          "failureReason",
          "failure_reason",
        ].forEach((key) => {
          const value = firstProcessMetaText([row[key]]);
          if (value) out[key] = value;
        });
      }
      return out;
    }

    function normalizeRunProcessEventRow(raw, index = 0) {
      const row = (raw && typeof raw === "object" && !Array.isArray(raw)) ? raw : null;
      if (!row) return normalizeRunProcessTimelineRow(raw, index);
      const text = firstProcessMetaText([
        row.text,
        row.message,
        row.msg,
        row.detail,
        row.summary,
        row.label,
        row.title,
      ]);
      if (!text) return null;
      return normalizeRunProcessTimelineRow({
        text,
        at: row.at,
        ts: row.ts,
        time: row.time,
        timestamp: row.timestamp,
        createdAt: row.createdAt,
        created_at: row.created_at,
        updatedAt: row.updatedAt,
        updated_at: row.updated_at,
        event_type: firstProcessMetaText([row.event_type, row.eventType, row.type, row.kind]),
        item_type: firstProcessMetaText([row.item_type, row.itemType, row.item && row.item.type]),
        title: firstProcessMetaText([row.title, row.name, row.label]),
        source: firstProcessMetaText([row.source]),
        status: firstProcessMetaText([row.status]),
        phase: firstProcessMetaText([row.phase]),
        call_id: firstProcessMetaText([row.call_id, row.callId, row.raw_ref, row.rawRef, row.item && (row.item.call_id || row.item.callId)]),
      }, index);
    }

    function copyRunProcessTimelineMeta(row) {
      const src = (row && typeof row === "object") ? row : {};
      const out = {};
      [
        "eventType",
        "itemType",
        "title",
        "path",
        "source",
        "status",
        "phase",
        "state",
        "outcome",
        "target",
        "targetPath",
        "target_path",
        "command",
        "url",
        "href",
        "name",
        "toolName",
        "tool_name",
        "callId",
        "call_id",
        "rawRef",
        "raw_ref",
        "error",
        "errorSummary",
        "error_summary",
        "failureReason",
        "failure_reason",
        "rowIndex",
      ].forEach((key) => {
        if (src[key] !== undefined && src[key] !== null && String(src[key]).trim() !== "") {
          out[key] = src[key];
        }
      });
      return out;
    }

    function isRunProcessActionRow(row) {
      if (!row || typeof row !== "object") return false;
      return !!firstProcessMetaText([row.eventType, row.event_type, row.eventTypeRaw]);
    }

    function normalizeRunProcessActionType(row) {
      const primaryText = [
        row && (row.eventType || row.event_type),
        row && (row.itemType || row.item_type),
      ].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean).join(" ");
      if (primaryText.includes("file_read") || primaryText.includes("read_file") || primaryText.includes("read") || primaryText.includes("view")) return "read";
      const text = [
        row && (row.eventType || row.event_type),
        row && (row.itemType || row.item_type),
        row && row.title,
        row && row.name,
        row && row.path,
        row && row.command,
        row && row.url,
        row && row.text,
      ].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean).join(" ");
      if (!text) return "unknown";
      if (text.includes("collab") || text.includes("announce") || text.includes("receipt") || text.includes("callback") || text.includes("message")) return "message";
      if (text.includes("file_change") || text.includes("apply_patch") || text.includes("patch") || text.includes("edit") || text.includes("write")) return "edit";
      if (text.includes("command") || text.includes("shell") || text.includes("exec") || text.includes("terminal") || text.includes("bash")) return "command";
      if (text.includes("web") || text.includes("browser") || text.includes("http") || text.includes("url") || text.includes("fetch")) return "web";
      if (text.includes("search") || text.includes("grep") || text.includes("rg ") || text.includes("find ")) return "search";
      if (text.includes("read") || text.includes("view") || text.includes("open") || text.includes("cat ")) return "read";
      if (text.includes("tool") || text.includes("mcp") || text.includes("function_call")) return "tool";
      if (text.includes("runtime") || text.includes("system") || text.includes("todo") || text.includes("plan")) return "system";
      return "unknown";
    }

    function runProcessActionLabel(row) {
      const labels = {
        read: "读取",
        edit: "编辑",
        command: "命令",
        search: "检索",
        web: "Web",
        message: "消息",
        tool: "工具",
        system: "系统",
        unknown: "未知",
      };
      const key = normalizeRunProcessActionType(row);
      return labels[key] || labels.unknown;
    }

    function runProcessRowCallId(row) {
      return firstProcessMetaText([
        row && row.callId,
        row && row.call_id,
        row && row.rawRef,
        row && row.raw_ref,
      ]);
    }

    function runProcessActionEventText(row) {
      return [
        row && (row.eventType || row.event_type),
        row && (row.itemType || row.item_type),
        row && row.status,
        row && row.state,
        row && row.phase,
        row && row.outcome,
      ].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean).join(" ");
    }

    function isAssistantProgressProcessRow(row) {
      const eventText = runProcessActionEventText(row);
      return eventText.includes("assistant_progress");
    }

    function isRunProcessToolStartRow(row) {
      const eventText = runProcessActionEventText(row);
      return eventText.includes("tool_started")
        || eventText.includes("tool_call.started")
        || eventText.includes("function_call.started");
    }

    function isRunProcessToolFailedClosingRow(row) {
      const eventText = runProcessActionEventText(row);
      const hasErrorPayload = !!firstProcessMetaText([
        row && row.error,
        row && row.errorSummary,
        row && row.error_summary,
        row && row.failureReason,
        row && row.failure_reason,
      ]);
      return hasErrorPayload
        || eventText.includes("tool_failed")
        || eventText.includes("tool_error")
        || eventText.includes("tool_call.failed")
        || eventText.includes("tool_call.error")
        || eventText.includes("function_call_error")
        || eventText.includes("failed")
        || eventText.includes("error")
        || eventText.includes("exception");
    }

    function isRunProcessToolCompletedClosingRow(row) {
      const eventText = runProcessActionEventText(row);
      return eventText.includes("tool_completed")
        || eventText.includes("tool_call.completed")
        || eventText.includes("function_call_result");
    }

    function buildRunProcessCallStatusIndex(rows) {
      const completed = new Set();
      const failed = new Set();
      (Array.isArray(rows) ? rows : []).forEach((row) => {
        const callId = runProcessRowCallId(row);
        if (!callId) return;
        if (isRunProcessToolFailedClosingRow(row)) {
          failed.add(callId);
          return;
        }
        if (isRunProcessToolCompletedClosingRow(row)) completed.add(callId);
      });
      return { completed, failed };
    }

    function normalizeRunProcessActionStatus(row, callStatusIndex = null) {
      if (isAssistantProgressProcessRow(row)) return "completed";
      const callId = runProcessRowCallId(row);
      if (callId && isRunProcessToolStartRow(row) && callStatusIndex) {
        if (callStatusIndex.failed && callStatusIndex.failed.has(callId)) return "failed";
        if (callStatusIndex.completed && callStatusIndex.completed.has(callId)) return "completed";
      }
      const explicit = firstProcessMetaText([
        row && row.status,
        row && row.state,
        row && row.phase,
        row && row.outcome,
      ]).toLowerCase();
      const mapStatus = (text) => {
        const value = String(text || "").trim().toLowerCase();
        if (!value) return "";
        if (value.includes("fail") || value.includes("error") || value.includes("exception")) return "failed";
        if (value.includes("cancel") || value.includes("interrupt") || value.includes("aborted")) return "cancelled";
        if (value.includes("skip")) return "skipped";
        if (value.includes("pending") || value.includes("queued") || value.includes("wait")) return "pending";
        if (value.includes("running") || value.includes("progress") || value.includes("start") || value.includes("started") || value.includes("execution")) return "running";
        if (value.includes("complete") || value.includes("done") || value.includes("success") || value.includes("succeed") || value.includes("result")) return "completed";
        return "";
      };
      const explicitStatus = mapStatus(explicit);
      if (explicitStatus) return explicitStatus;
      const eventText = [
        row && (row.eventType || row.event_type),
        row && (row.itemType || row.item_type),
        row && row.text,
      ].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean).join(" ");
      const eventStatus = mapStatus(eventText);
      if (eventStatus) return eventStatus;
      return "completed";
    }

    function runProcessActionStatusLabel(status, row = null) {
      if (isAssistantProgressProcessRow(row)) return "进展记录";
      const labels = {
        pending: "待处理",
        running: "进行中",
        completed: "已完成",
        failed: "失败",
        cancelled: "已取消",
        skipped: "已跳过",
      };
      const key = String(status || "").trim().toLowerCase();
      return labels[key] || labels.completed;
    }

    function runProcessActionTarget(row) {
      const directTarget = firstRunProcessActionTargetText([
        row && row.path,
        row && row.targetPath,
        row && row.target_path,
        row && row.target,
        row && row.command,
        row && row.url,
        row && row.href,
      ]);
      if (directTarget) return clampRunProcessDisplayText(directTarget, 120);
      const text = String((row && row.text) || "").trim();
      const stripped = text
        .replace(/^执行命令[:：]\s*/, "")
        .replace(/^调用工具[:：]\s*/, "")
        .replace(/^工具完成[:：]\s*/, "")
        .replace(/^更新文件[:：]\s*/, "")
        .replace(/^读取[:：]\s*/, "")
        .replace(/^编辑[:：]\s*/, "")
        .trim();
      if (stripped && stripped !== text && !isLowValueRunProcessActionTarget(stripped) && !looksLikeRawProcessJsonText(stripped) && !containsUnsafeProcessMarker(stripped)) {
        return clampRunProcessDisplayText(stripped, 120);
      }
      if (text && !isLowValueRunProcessActionTarget(text) && !looksLikeRawProcessJsonText(text) && !containsUnsafeProcessMarker(text)) {
        return clampRunProcessDisplayText(text, 120);
      }
      const titleTarget = firstRunProcessActionTargetText([
        row && row.title,
        row && row.name,
        row && row.toolName,
        row && row.tool_name,
      ]);
      if (titleTarget) return clampRunProcessDisplayText(titleTarget, 120);
      return "当前上下文";
    }

    function runProcessActionErrorSummary(row) {
      const raw = firstProcessMetaText([
        row && row.errorSummary,
        row && row.error_summary,
        row && row.failureReason,
        row && row.failure_reason,
        row && row.error,
      ]);
      if (!raw || looksLikeRawProcessJsonText(raw) || containsUnsafeProcessMarker(raw)) return "";
      return clampRunProcessDisplayText(raw, 240);
    }

    function buildRunProcessActionNode(row, idx, callStatusIndex = null) {
      const typeKey = normalizeRunProcessActionType(row);
      const label = runProcessActionLabel(row);
      const status = normalizeRunProcessActionStatus(row, callStatusIndex);
      const target = runProcessActionTarget(row);
      const callId = runProcessRowCallId(row);
      const rawText = String((row && row.text) || "").trim();
      const safeText = (!rawText || looksLikeRawProcessJsonText(rawText) || containsUnsafeProcessMarker(rawText))
        ? clampRunProcessDisplayText(label + " · " + target, 160)
        : clampRunProcessDisplayText(rawText, 180);
      const detailText = (!rawText || looksLikeRawProcessJsonText(rawText) || containsUnsafeProcessMarker(rawText))
        ? safeText
        : clampRunProcessDisplayText(rawText, 640);
      const action = {
        id: "action-" + idx,
        kind: "action",
        isActionNode: true,
        text: safeText,
        detailText,
        at: String((row && row.at) || "").trim(),
        eventType: row && row.eventType,
        itemType: row && row.itemType,
        title: row && row.title,
        label,
        typeKey,
        status,
        statusLabel: runProcessActionStatusLabel(status, row),
        target,
        callId,
        errorSummary: runProcessActionErrorSummary(row),
        row,
      };
      return {
        id: action.id,
        kind: "action",
        isActionNode: true,
        text: safeText,
        at: action.at,
        row,
        action,
        actions: [],
      };
    }

    function buildRunProcessStepGroups(rows) {
      const normalizedRows = (Array.isArray(rows) ? rows : [])
        .map((row, idx) => normalizeRunProcessTimelineRow(row, idx))
        .filter((row) => String((row && row.text) || "").trim());
      const groups = [];
      let stepCount = 0;
      let actionCount = 0;
      const callStatusIndex = buildRunProcessCallStatusIndex(normalizedRows);
      normalizedRows.forEach((row, idx) => {
        if (isRunProcessActionRow(row)) {
          actionCount += 1;
          groups.push(buildRunProcessActionNode(row, idx, callStatusIndex));
          return;
        }
        stepCount += 1;
        groups.push({
          id: "step-" + idx,
          kind: "step",
          synthetic: false,
          text: row.text,
          at: row.at,
          row,
          actions: [],
        });
      });
      return {
        groups,
        stepCount,
        actionCount,
      };
    }

    function reusableProcessRowTime(raw) {
      if (!raw || typeof raw !== "object") return "";
      const at = String(raw.at || "").trim();
      if (!at) return "";
      const source = String(raw.timeSource || "").trim().toLowerCase();
      if (source === "explicit" || source === "structured") return at;
      const explicit = extractProcessItemTimestamp(String(raw.text || ""));
      return explicit ? at : "";
    }

    function extractDetailProcessMessages(detailFull, cliType) {
      const full = (detailFull && typeof detailFull === "object") ? detailFull : null;
      if (!full) return { items: [], rows: [], exact: false };
      const normalizedCliType = String(cliType || "").trim().toLowerCase();
      const suppressTerminalTextAgentMessages = isTerminalTextCli(normalizedCliType);
      const out = [];
      const rows = [];
      const push = (raw) => {
        const row = normalizeRunProcessTimelineRow(raw, rows.length);
        const txt = String(row.text || "").trim();
        if (!txt) return;
        if (out.length && out[out.length - 1] === txt) return;
        out.push(txt);
        rows.push(row);
      };
      const detailRun = (full.run && typeof full.run === "object") ? full.run : null;
      const topRowLists = [
        full.processRows,
        full.process_rows,
      ];
      const nestedRowLists = [
        detailRun && detailRun.processRows,
        detailRun && detailRun.process_rows,
      ];
      const rowLists = topRowLists.some((list) => Array.isArray(list) && list.length)
        ? topRowLists
        : nestedRowLists;
      rowLists.forEach((list) => {
        if (!Array.isArray(list)) return;
        list.forEach((item) => push(item));
      });
      if (!out.length) {
        const topEventLists = [
          full.processEvents,
          full.process_events,
        ];
        const nestedEventLists = [
          detailRun && detailRun.processEvents,
          detailRun && detailRun.process_events,
        ];
        const eventLists = topEventLists.some((list) => Array.isArray(list) && list.length)
          ? topEventLists
          : nestedEventLists;
        eventLists.forEach((list) => {
          if (!Array.isArray(list)) return;
          list.forEach((item) => {
            const eventRow = normalizeRunProcessEventRow(item, rows.length);
            if (eventRow) push(eventRow);
          });
        });
      }
      if (!out.length) {
        const directLists = [
          full.processMessages,
          full.process_messages,
        ];
        if (!suppressTerminalTextAgentMessages) {
          directLists.unshift(full.agent_messages);
          directLists.unshift(full.agentMessages);
        }
        directLists.forEach((list) => {
          if (!Array.isArray(list)) return;
          list.forEach((item) => push(item));
        });
      }
      return { items: out, rows, exact: out.length > 0 };
    }

    function processListCount(raw) {
      if (Array.isArray(raw)) return raw.length;
      if (typeof raw === "number" && Number.isFinite(raw)) return Math.max(0, raw);
      return 0;
    }

    function reportedProcessCountFromRunAndDetail(run, detailFull) {
      const full = (detailFull && typeof detailFull === "object") ? detailFull : null;
      const detailRun = full && full.run && typeof full.run === "object" ? full.run : null;
      const sources = [
        (run && typeof run === "object") ? run : null,
        full,
        detailRun,
      ];
      let count = 0;
      sources.forEach((source) => {
        if (!source) return;
        count = Math.max(
          count,
          processListCount(source.processRows),
          processListCount(source.process_rows),
          processListCount(source.processEvents),
          processListCount(source.process_events)
        );
      });
      return count;
    }

    function collectRunProcessInfo(runId, runStatus, run, detail) {
      const rid = String(runId || "");
      const stNorm = String(runStatus || "").toLowerCase();
      const isWorking = isRunWorking(stNorm);
      const detailFull = detail && detail.full ? detail.full : null;
      const cliType = String(firstNonEmptyText([
        detailFull && detailFull.run && detailFull.run.cliType,
        detailFull && detailFull.run && detailFull.run.cli_type,
        run && run.cliType,
        run && run.cli_type,
      ]) || "").trim().toLowerCase();
      const suppressTerminalTextLegacyPreview = isTerminalTextCli(cliType);

      const incoming = [];
      const push = (raw) => {
        const txt = String(raw || "").replace(/\r\n/g, "\n").trim();
        if (!txt) return;
        if (incoming.length && incoming[incoming.length - 1] === txt) return;
        incoming.push(txt);
      };
      const detailProcess = extractDetailProcessMessages(detailFull, cliType);
      const detailRows = Array.isArray(detailProcess.rows) ? detailProcess.rows : [];
      detailProcess.items.forEach((msg) => push(msg));
      if (!incoming.length && !suppressTerminalTextLegacyPreview) push(run && run.partialPreview);
      if (!incoming.length && !suppressTerminalTextLegacyPreview) push(detailFull && detailFull.partialMessage);
      const hasExactDetailItems = !!detailProcess.exact;

      const prevState = PCONV.processTrailByRun[rid] || { items: [], rows: [], status: "", updatedAt: 0 };
      const prevItems = Array.isArray(prevState.items) ? prevState.items : [];
      const prevRows = Array.isArray(prevState.rows) ? prevState.rows : [];
      let items = incoming.slice();

      // 运行中避免“过程条目回退”：切会话/轮询时如果拉到的片段更短，保持已有结果。
      if (rid) {
        if (isWorking) {
          if (!items.length) items = prevItems.slice();
          else if (prevItems.length > items.length) items = prevItems.slice();
        } else {
          // 终态若仅拿到预览片段，不覆盖已有完整过程列表，避免切会话后由多条回退到一条。
          if (!hasExactDetailItems && prevItems.length > items.length) {
            items = prevItems.slice();
          }
          // 终态优先使用当前拉取结果；若当前为空则回退已有缓存。
          if (!items.length && prevItems.length) items = prevItems.slice();
        }
        if (items.length > 240) items = items.slice(-240);
        const nextRows = [];
        const usedPrevIdx = new Set();
        const findPrevRowByText = (txt) => {
          for (let i = 0; i < prevRows.length; i += 1) {
            if (usedPrevIdx.has(i)) continue;
            const row = prevRows[i];
            if (!row || String(row.text || "") !== txt) continue;
            usedPrevIdx.add(i);
            return row;
          }
          return null;
        };
        items.forEach((txt, idx) => {
          const text = String(txt || "");
          const detailRow = detailRows[idx] && String(detailRows[idx].text || "") === text ? detailRows[idx] : null;
          const explicitTs = String((detailRow && detailRow.at) || "").trim() || extractProcessItemTimestamp(text);
          const prevByIndex = prevRows[idx] && String(prevRows[idx].text || "") === text ? prevRows[idx] : null;
          if (prevByIndex) usedPrevIdx.add(idx);
          const prevByText = prevByIndex ? null : findPrevRowByText(text);
          const reusedPrevAt = reusableProcessRowTime(prevByIndex) || reusableProcessRowTime(prevByText) || "";
          const metaSource = detailRow || prevByIndex || prevByText || null;
          let timeSource = explicitTs
            ? String((detailRow && detailRow.timeSource) || "").trim().toLowerCase() || "explicit"
            : "";
          if (!timeSource && reusedPrevAt) {
            const prevSource = String(
              ((prevByIndex && prevByIndex.timeSource) || (prevByText && prevByText.timeSource) || "")
            ).trim().toLowerCase();
            timeSource = prevSource || "explicit";
          }
          const at = explicitTs || reusedPrevAt || "";
          nextRows.push(Object.assign(copyRunProcessTimelineMeta(metaSource), { text, at, timeSource }));
        });
        PCONV.processTrailByRun[rid] = {
          items: items.slice(),
          rows: nextRows,
          status: stNorm,
          updatedAt: Date.now(),
        };
      }

      const latest = items.length ? items[items.length - 1] : "";
      const countFromRun = suppressTerminalTextLegacyPreview ? 0 : Number((run && run.agentMessagesCount) || 0);
      const reportedProcessCount = reportedProcessCountFromRunAndDetail(run, detailFull);
      const reportedCount = Math.max(countFromRun, reportedProcessCount);
      // 展示条数以“已解析列表/后端统计”较大值为准，避免切会话时临时回退。
      const count = Math.max(items.length, reportedCount);
      const rows = (rid && PCONV.processTrailByRun[rid] && Array.isArray(PCONV.processTrailByRun[rid].rows))
        ? PCONV.processTrailByRun[rid].rows
        : items.map((txt) => ({ text: String(txt || ""), at: "" }));
      const processStepModel = buildRunProcessStepGroups(rows);
      const detailRun = detailFull && detailFull.run && typeof detailFull.run === "object" ? detailFull.run : null;
      let latestProgressAt = firstNonEmptyText([
        detailRun && detailRun.updatedAt,
        detailRun && detailRun.updated_at,
        detailRun && detailRun.finishedAt,
        detailRun && detailRun.finished_at,
        detailRun && detailRun.startedAt,
        detailRun && detailRun.started_at,
        run && run.updatedAt,
        run && run.updated_at,
        run && run.finishedAt,
        run && run.finished_at,
        run && run.startedAt,
        run && run.started_at,
        run && run.createdAt,
      ]);
      let latestProgressNum = toTimeNum(latestProgressAt);
      const fromLatestItem = extractProcessItemTimestamp(latest);
      const latestItemNum = toTimeNum(fromLatestItem);
      if (latestItemNum >= 0 && (latestProgressNum < 0 || latestItemNum >= latestProgressNum)) {
        latestProgressAt = fromLatestItem;
        latestProgressNum = latestItemNum;
      }
      const fallbackRowTs = rows.length ? String((rows[rows.length - 1] && rows[rows.length - 1].at) || "").trim() : "";
      const fallbackRowNum = toTimeNum(fallbackRowTs);
      if (fallbackRowNum >= 0 && (latestProgressNum < 0 || fallbackRowNum >= latestProgressNum)) {
        latestProgressAt = fallbackRowTs;
        latestProgressNum = fallbackRowNum;
      }
      if (latestProgressNum < 0) latestProgressAt = "";
      return {
        items,
        rows,
        cliType,
        latest,
        count,
        reportedCount,
        latestProgressAt,
        processStepGroups: processStepModel.groups,
        processStepCount: processStepModel.stepCount,
        processActionCount: processStepModel.actionCount,
      };
    }

    function resolveAssistantText(run, detail) {
      const runStatus = getRunDisplayState(run, detail);
      const runWorking = isWorkingLikeState(runStatus);
      const d = detail && detail.full ? detail.full : null;
      const generatedMediaSummary = String(firstNonEmptyText([
        d && d.run && d.run.generated_media_summary,
        d && d.run && d.run.generatedMediaSummary,
        detail && detail.run && detail.run.generated_media_summary,
        detail && detail.run && detail.run.generatedMediaSummary,
        run && run.generated_media_summary,
        run && run.generatedMediaSummary,
      ]) || "");
      if (!runWorking && generatedMediaSummary.trim()) {
        return generatedMediaSummary;
      }
      const cliType = String(firstNonEmptyText([
        d && d.run && d.run.cliType,
        d && d.run && d.run.cli_type,
        run && run.cliType,
        run && run.cli_type,
      ]) || "").trim().toLowerCase();
      const suppressTerminalTextLegacyFallback = isTerminalTextCli(cliType);
      if (d) {
        const effectiveDetailRunStatus = deriveRunStateFromSource(d.run, "idle");
        const detailWorking = isWorkingLikeState(effectiveDetailRunStatus);
        const allowTerminalDetailText = !runWorking && !detailWorking;
        const allowProgressDetailText = runWorking && detailWorking;
        const fullLast = String(d.lastMessage || "");
        if (allowTerminalDetailText && fullLast.trim()) {
          return safeCodeBuddyTextForDisplay(fullLast, run && run.id, run, detail, { cliType });
        }
        if (!suppressTerminalTextLegacyFallback) {
          const fullPartial = String(d.partialMessage || "");
          if ((allowTerminalDetailText || allowProgressDetailText) && fullPartial.trim()) return fullPartial;
          const agentMsgs = Array.isArray(d.agentMessages) ? d.agentMessages : [];
          if ((allowTerminalDetailText || allowProgressDetailText) && agentMsgs.length) {
            const latest = String(agentMsgs[agentMsgs.length - 1] || "");
            if (latest.trim()) return latest;
          }
        }
      }
      const runPartial = String((run && run.partialPreview) || "");
      if (suppressTerminalTextLegacyFallback) {
        const runLastOnly = String((run && run.lastPreview) || "");
        return safeCodeBuddyTextForDisplay(runLastOnly, run && run.id, run, detail, { cliType });
      }
      if (runWorking && runPartial.trim()) return runPartial;
      const runLastForTerminal = String((run && run.lastPreview) || "");
      if (!runWorking && runLastForTerminal.trim()) return safeCodeBuddyTextForDisplay(runLastForTerminal, run && run.id, run, detail, { cliType });
      const runLast = String((run && run.lastPreview) || "");
      if (!runWorking && runLast.trim()) return safeCodeBuddyTextForDisplay(runLast, run && run.id, run, detail, { cliType });
      return runPartial;
    }

    function resolveAttachmentUrl(att) {
      if (!att || typeof att !== "object") return "";
      const url = String(att.url || att.dataUrl || "").trim();
      if (url) return url;
      const filename = String(att.filename || "").trim();
      if (filename) {
        if (filename.startsWith("/") || filename.startsWith("http://") || filename.startsWith("https://")) return filename;
        return "/.runs/attachments/" + encodeURIComponent(filename);
      }
      const p = String(att.path || "").trim();
      if (p) {
        // 兼容历史数据中的绝对路径，尝试转为同源可访问路径。
        const marker = "/.runs/";
        const idx = p.lastIndexOf(marker);
        if (idx >= 0) return p.slice(idx);
      }
      return "";
    }

    function fileExtTag(name) {
      const n = String(name || "").trim();
      const m = n.match(/\.([a-zA-Z0-9]{1,6})$/);
      if (!m) return "F";
      return String(m[1] || "").slice(0, 3).toUpperCase();
    }

    function formatBytes(bytes) {
      const n = Number(bytes || 0);
      if (!Number.isFinite(n) || n <= 0) return "";
      if (n < 1024) return n + "B";
      const kb = n / 1024;
      if (kb < 1024) return kb.toFixed(kb >= 100 ? 0 : 1).replace(/\.0$/, "") + "KB";
      const mb = kb / 1024;
      if (mb < 1024) return mb.toFixed(mb >= 100 ? 0 : 1).replace(/\.0$/, "") + "MB";
      const gb = mb / 1024;
      return gb.toFixed(gb >= 100 ? 0 : 1).replace(/\.0$/, "") + "GB";
    }

    function isImageAttachment(att) {
      if (!att || typeof att !== "object") return false;
      if (att.isImage === true) return true;
      const mime = String(att.mimeType || "").toLowerCase();
      if (mime.startsWith("image/")) return true;
      const name = String(att.originalName || att.filename || "").toLowerCase();
      return /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(name);
    }

    const SKILL_INLINE_RE = /`([A-Za-z0-9][A-Za-z0-9._-]{2,80})`/g;
    const SKILL_DOLLAR_RE = /\$([A-Za-z0-9][A-Za-z0-9._-]{1,80})/g;
    const SKILL_LINK_RE = /\[([^\]]+)\]\(([^)]+?SKILL\.md[^)]*)\)/ig;
    const SKILL_PATH_RE = /\/([^/]+)\/SKILL\.md/i;
    const UUID_TOKEN_RE = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|ses_[a-z0-9]{8,128})$/i;
    const AGENT_SESSION_RE = /\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|ses_[a-z0-9]{8,128})\b/ig;
    const AGENT_LINE_HINT_RE = /(?:^|\n)\s*([0-9]{2}|子级[0-9]{2}|辅助[0-9]{2}|主体|总控)\s*[：:]\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|ses_[a-z0-9]{8,128})\b/ig;
    const TAG_ICON_BY_KIND = {
      skill: "⚙",
      agent: "🤖",
      task: "🗂",
      requirement: "🧾",
      issue: "❗",
      discussion: "💬",
      feedback: "📣",
      sediment: "📚",
      material: "📎",
      other: "◈",
    };
    const BUSINESS_PATH_RE = /\/[^\s"'`<>]+?\.(?:md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)/ig;
    const BUSINESS_MARKER_RE = /(?:\[|【)\s*(任务|需求|问题|讨论|反馈|沉淀|材料)\s*(?:\]|】)\s*[:：]?\s*([^\n]{1,120})/ig;
    const BUSINESS_TYPES = new Set(["任务", "需求", "问题", "讨论", "反馈", "沉淀", "材料", "其他"]);
    const BUSINESS_PATH_SEGMENTS = ["/任务规划/", "/协同空间/", "/产出物/", "/任务/", "/需求/", "/问题/", "/讨论空间/", "/反馈/", "/沉淀/", "/材料/"];

    function normalizeSkillToken(raw) {
      let t = String(raw || "").trim().replace(/^`|`$/g, "").trim();
      if (!t) return "";
      if (t.startsWith("$")) t = t.slice(1).trim();
      if (t.includes("/")) t = t.split("/").pop().trim();
      if (t.toLowerCase().endsWith(".md")) t = t.slice(0, -3).trim();
      t = t.toLowerCase();
      if (!/^[a-z0-9][a-z0-9._-]{1,80}$/.test(t)) return "";
      if (UUID_TOKEN_RE.test(t)) return "";
      if (["task.js", "task.css", "task.html.tpl", "server.py", "task-dashboard", "codex"].includes(t)) return "";
      return t;
    }

    function extractSkillsFromText(text) {
      const src = String(text || "");
      if (!src) return [];
      const out = [];
      const seen = new Set();
      const push = (raw) => {
        const tok = normalizeSkillToken(raw);
        if (!tok || seen.has(tok)) return;
        const likely = tok.includes("skill") || tok.split("-").length >= 3;
        if (!likely) return;
        seen.add(tok);
        out.push(tok);
      };
      let m;
      SKILL_LINK_RE.lastIndex = 0;
      while ((m = SKILL_LINK_RE.exec(src)) !== null) {
        push(m[1] || "");
        const p = String(m[2] || "");
        const mm = p.match(SKILL_PATH_RE);
        if (mm && mm[1]) push(mm[1]);
      }
      SKILL_DOLLAR_RE.lastIndex = 0;
      while ((m = SKILL_DOLLAR_RE.exec(src)) !== null) push(m[1] || "");
      SKILL_INLINE_RE.lastIndex = 0;
      while ((m = SKILL_INLINE_RE.exec(src)) !== null) push(m[1] || "");
      return out;
    }

    function cleanBusinessPath(raw) {
      let p = String(raw || "").trim().replace(/^`|`$/g, "").trim();
      if (!p) return "";
      while (p && ").,;:，。；：】]>}".includes(p[p.length - 1])) p = p.slice(0, -1);
      if (!p.startsWith("/")) return "";
      const idx = p.toLowerCase().indexOf(".md");
      const m = p.toLowerCase().match(/\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)/);
      if (!m || typeof m.index !== "number") return "";
      p = p.slice(0, m.index + m[0].length);
      const low = p.toLowerCase();
      if (low.endsWith("/skill.md") || low.includes("/.codex/" + "skills/")) return "";
      if (!BUSINESS_PATH_SEGMENTS.some((seg) => p.includes(seg))) return "";
      return p;
    }

    function stripBusinessTitleExt(name) {
      return String(name || "").trim().replace(/\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)$/i, "");
    }

    function businessTypeFromPath(path, title) {
      const p = String(path || "");
      const t = String(title || "");
      if (p.includes("/任务/")) return "任务";
      if (p.includes("/需求/")) return "需求";
      if (p.includes("/问题/")) return "问题";
      if (p.includes("/讨论空间/")) return "讨论";
      if (p.includes("/反馈/")) return "反馈";
      if (p.includes("/产出物/沉淀/") || p.includes("/沉淀/")) return "沉淀";
      if (p.includes("/产出物/材料/") || p.includes("/材料/")) return "材料";
      if (t.includes("【任务】")) return "任务";
      if (t.includes("【需求】") || t.includes("需求")) return "需求";
      if (t.includes("【问题】")) return "问题";
      if (t.includes("讨论")) return "讨论";
      if (t.includes("【反馈】") || t.includes("反馈")) return "反馈";
      if (t.includes("沉淀")) return "沉淀";
      if (t.includes("材料")) return "材料";
      return "其他";
    }

    function normalizeBusinessRefItem(raw) {
      if (!raw || typeof raw !== "object") return null;
      const path = cleanBusinessPath(raw.path || raw.filePath || "");
      let title = String(raw.title || raw.name || "").trim();
      if (!title && path) {
        title = path.split("/").pop() || "";
        title = stripBusinessTitleExt(title);
      }
      if (!title) return null;
      let type = String(raw.type || "").trim();
      if (!BUSINESS_TYPES.has(type)) type = businessTypeFromPath(path, title);
      if (!BUSINESS_TYPES.has(type)) type = "其他";
      return { type, title, path };
    }

    function extractBusinessRefsFromText(text) {
      const src = String(text || "");
      if (!src) return [];
      const out = [];
      const seen = new Set();
      const push = (type, title, path) => {
        const p = cleanBusinessPath(path || "");
        let nm = String(title || "").trim();
        if (!nm && p) {
          nm = p.split("/").pop() || "";
          nm = stripBusinessTitleExt(nm);
        }
        if (!nm) return;
        let tp = String(type || "").trim();
        if (!BUSINESS_TYPES.has(tp)) tp = businessTypeFromPath(p, nm);
        if (!BUSINESS_TYPES.has(tp)) tp = "其他";
        const key = [tp, p, nm].join("|");
        if (seen.has(key)) return;
        seen.add(key);
        out.push({ type: tp, title: nm, path: p });
      };

      BUSINESS_PATH_RE.lastIndex = 0;
      let m;
      while ((m = BUSINESS_PATH_RE.exec(src)) !== null) {
        const path = cleanBusinessPath(m[0] || "");
        if (!path) continue;
        let title = path.split("/").pop() || "";
        title = stripBusinessTitleExt(title);
        push(businessTypeFromPath(path, title), title, path);
      }

      BUSINESS_MARKER_RE.lastIndex = 0;
      while ((m = BUSINESS_MARKER_RE.exec(src)) !== null) {
        let title = String(m[2] || "").trim();
        if (!title) continue;
        ["。", "；", ";", "，", ",", "\n"].forEach((sep) => {
          if (title.includes(sep)) title = title.split(sep, 1)[0].trim();
        });
        if (title.length > 80) title = title.slice(0, 80).trim();
        push(String(m[1] || ""), title, "");
      }
      return out;
    }

    function shortAgentSessionId(sessionId) {
      const sid = String(sessionId || "").trim();
      if (sid.length <= 12) return sid;
      return sid.slice(0, 8) + "…" + sid.slice(-4);
    }

    function normalizeChannelKey(raw) {
      return String(raw || "").trim().toLowerCase().replace(/\s+/g, "");
    }

    function normalizeAgentLabel(raw) {
      const t = String(raw || "").trim();
      if (!t) return "";
      return t
        .replace(/^\[?\s*(?:来源通道|source\s*channel)\s*[:：]\s*/i, "")
        .replace(/\s+/g, " ")
        .trim();
    }

    function findSessionLabelById(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return "";
      const list = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
      const hit = list.find((s) => String((s && s.sessionId) || "") === sid);
      if (!hit) return "";
      return firstNonEmptyText([
        hit.displayChannel,
        hit.channelName,
        hit.alias,
        Array.isArray(hit.channels) && hit.channels.length ? String(hit.channels[0]) : "",
      ]);
    }

    function findSessionChannelById(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return "";
      const hit = findConversationSessionById(sid);
      if (!hit) return "";
      return firstNonEmptyText([
        getSessionChannelName(hit),
        hit.channelName,
        hit.primaryChannel,
        hit.displayChannel,
        hit.alias,
        Array.isArray(hit.channels) && hit.channels.length ? String(hit.channels[0]) : "",
      ]);
    }

    function extractAgentRefsFromText(text, currentSessionId = "") {
      const src = String(text || "");
      if (!src) return [];
      const out = [];
      const seen = new Set();
      const curSid = String(currentSessionId || "").trim();
      const push = (sessionId, hint = "") => {
        const sid = String(sessionId || "").trim().toLowerCase();
        if (!UUID_TOKEN_RE.test(sid)) return;
        if (curSid && sid === curSid.toLowerCase()) return;
        if (seen.has(sid)) return;
        seen.add(sid);
        const mappedLabel = findSessionLabelById(sid);
        const label = mappedLabel || String(hint || "").trim();
        out.push({ sessionId: sid, label });
      };
      AGENT_LINE_HINT_RE.lastIndex = 0;
      let m;
      while ((m = AGENT_LINE_HINT_RE.exec(src)) !== null) {
        push(m[2] || "", m[1] || "");
      }
      AGENT_SESSION_RE.lastIndex = 0;
      while ((m = AGENT_SESSION_RE.exec(src)) !== null) {
        push(m[1] || "", "");
      }
      return out;
    }

    function businessTypeIconKind(typ) {
      const t = String(typ || "").trim();
      if (t === "任务") return "task";
      if (t === "需求") return "requirement";
      if (t === "问题") return "issue";
      if (t === "讨论") return "discussion";
      if (t === "反馈") return "feedback";
      if (t === "沉淀") return "sediment";
      if (t === "材料") return "material";
      if (t === "其他") return "other";
      return "";
    }

    function appendTagContent(node, opts = {}) {
      const kind = String((opts && opts.kind) || "").trim();
      const txt = String((opts && opts.text) || "");
      const fallbackTypeText = String((opts && opts.fallbackTypeText) || "").trim();
      const icon = TAG_ICON_BY_KIND[kind] || "";
      if (icon) node.appendChild(el("span", { class: "tagicon", text: icon }));
      else if (fallbackTypeText) node.appendChild(el("span", { class: "tagtype", text: fallbackTypeText }));
      node.appendChild(el("span", { class: "taglabel", text: txt }));
    }
